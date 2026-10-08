"""Legal Troubles BI refresh (Rich/Maya). Run: python3 bi_refresh.py <out_dir> [sims]
Env: LT_CURATED=<curated dir> (tags.json, claims.json, needs.json; required; ir_returns.json optional),
     LT_TEAM_ID (default 31 = Legal Troubles), LT_ODDS_HISTORY=<json file> (odds history kept across runs; project copy claude/data/odds_history.json; unset = history not written).
Pulls live ESPN data, runs the playoff sim (odds_model.py, model v2), and writes one JSON file per dashboard document:
  meta/current (incl. `league` and `model` blocks), odds/wNN, odds/history, scores/wNN (every completed week), players/<espnId>,
  waivers/current, extras/current, nfl/current, curated/current
Odds model v2 (Oct 7 outside-review item 1; details in odds_model.py): ESPN per-game projections week by week
  (this week = ESPN weekly projection; later weeks = rest-of-season projection / games left), byes, IR return weeks,
  free-agent streamers at replacement level, team-strength uncertainty, seeding = record -> head-to-head (two teams) ->
  points for (multi-team ties head-to-head can't settle). odds/history keeps every run (week, time, model, per-team odds).
Fail-loudly rules (Oct 6 org review; Oct 7 quality gates):
  - core ESPN pulls raise (no output written -> build_bundle keeps last good copy, marked stale)
  - quality gates raise: all-zero ESPN weekly projections, any team with a 0 projection this week or any remaining week,
    no free agents with a projection (no replacement level), team count != league size
  - each extras feature is wrapped on its own; a failure writes {"error": "<reason>"} for that feature
    and the run exits non-zero after writing everything else
  - league facts (playoff teams/weeks, season length, starters) come from ESPN mSettings, never hard-coded
  - curated items carry asOf/expiresWeek; past expiresWeek they are marked expired:true, never shown as current.
    Old-format entries (list, or no asOf/expiresWeek) are accepted as current with legacy:true,
    asOf = the file's date, expiresWeek = current week + 1 (the validator warns about them)
claude.ai db layout (load every file under <out_dir> as <collection>/<doc>):
  extras/current.league  = the league block (also meta/current.league)
  meta/current.sections  = per-section status from this run {name: {ok, stale, updatedAt, error?}}
  validation/current     = written by validate_bundle.py --out <out_dir>/validation/current.json
  extras/current.scouting = {week, asOf, usSeed, regWeeks, league} for the Scouting Report data
Curated tags/claims/needs live in LT_CURATED; there are no hard-coded defaults (stale defaults hid problems)."""
import json, os, sys, random, statistics, urllib.request, math
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odds_model as om
LG = 293318; YR = 2026; ET = ZoneInfo("America/New_York")
TEAM_ID = int(os.environ.get("LT_TEAM_ID", "31"))
B = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}/segments/0/leagues/{LG}"
ERRORS = {}  # feature -> reason (required features only)
def get(q, hdr=None):
    req = urllib.request.Request(f"{B}?{q}", headers=hdr or {})
    return json.load(urllib.request.urlopen(req, timeout=90))
def _get(u, h=None): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=h or {}), timeout=90))
def now_iso(): return datetime.now(timezone.utc).isoformat(timespec="minutes")
out = sys.argv[1] if len(sys.argv) > 1 else "bi_out"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
# ---- core pulls (any failure raises: no partial output) ----
t = get("view=mTeam&view=mStatus&view=mSettings"); m = get("view=mMatchupScore&view=mMatchup"); r = get("view=mRoster")
pro = _get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}?view=proTeamSchedules_wl")
S = t["settings"]; SS = S["scheduleSettings"]
wk = t["status"]["currentMatchupPeriod"]; REG = SS["matchupPeriodCount"]; PO = SS["playoffTeamCount"]
# matchup period -> scoring periods (NFL weeks); playoff periods are those after the regular season
MP = {int(k): v for k, v in SS["matchupPeriods"].items()}
PLAYOFF_WEEKS = sorted(w for k, v in MP.items() if k > REG for w in v)
SLOT_COUNTS = {int(k): v for k, v in S["rosterSettings"]["lineupSlotCounts"].items() if v}
STARTERS = sum(v for k, v in SLOT_COUNTS.items() if k not in (20, 21))
names = {x["id"]: x["name"].strip() for x in t["teams"]}
if TEAM_ID not in names: raise SystemExit(f"team id {TEAM_ID} not in league teams {sorted(names)}")
me = TEAM_ID
ab = {p["id"]: p["abbrev"] for p in pro["settings"]["proTeams"] if p["id"] != 0}
bye = {p["id"]: p["byeWeek"] for p in pro["settings"]["proTeams"] if p["id"] != 0}
if len(ab) != 32: raise SystemExit(f"expected 32 NFL teams from proTeamSchedules, got {len(ab)}")
if len(r["teams"]) != len(names): raise SystemExit(f"mRoster has {len(r['teams'])} teams, league has {len(names)}")
def abbr(tid):
    """NFL abbreviation for an ESPN proTeamId. 0/None = genuinely unsigned (FA). Anything else unknown raises."""
    if tid in (0, None): return "FA"
    if tid not in ab: raise KeyError(f"unknown NFL proTeamId {tid}")
    return ab[tid]
# ---- curated (asOf / expiresWeek; legacy entries accepted as current until next week, flagged legacy) ----
CUR = os.environ.get("LT_CURATED")
def load_cur(fname, fields):
    if not CUR or not os.path.isdir(CUR): raise FileNotFoundError(f"LT_CURATED not set or missing ({CUR})")
    f = os.path.join(CUR, fname)
    if not os.path.exists(f): raise FileNotFoundError(f)
    raw = json.load(open(f)); outd = {}
    fdate = datetime.fromtimestamp(os.path.getmtime(f), ET).date().isoformat()
    for k, v in raw.items():
        if isinstance(v, dict): d = dict(v)
        elif isinstance(v, (list, tuple)): d = dict(zip(fields, v))
        else: d = {fields[0]: v}
        if d.get("expiresWeek") is None or not d.get("asOf"):
            d["legacy"] = True; d["asOf"] = d.get("asOf") or fdate
            if d.get("expiresWeek") is None: d["expiresWeek"] = wk + 1
        d["expired"] = wk > int(d["expiresWeek"])
        outd[k] = d
    return outd
cur_status = {}
def cur_feature(name, fname, fields, optional=False):
    if optional and not (CUR and os.path.exists(os.path.join(CUR, fname))):
        cur_status[name] = {"total": 0, "expired": 0, "legacy": 0, "note": f"no {fname} (optional): return weeks inferred from ESPN status"}; return {}
    try:
        d = load_cur(fname, fields)
        cur_status[name] = {"total": len(d), "expired": sum(1 for x in d.values() if x["expired"]), "legacy": sum(1 for x in d.values() if x.get("legacy")), "legacyNames": [k for k, x in d.items() if x.get("legacy")],
                            "expiredNames": [k for k, x in d.items() if x["expired"]]}
        return d
    except Exception as e:
        cur_status[name] = {"error": f"{type(e).__name__}: {e}"}; ERRORS[f"curated.{name}"] = cur_status[name]["error"]; return {}
TAGS = cur_feature("tags", "tags.json", ["tag", "note", "ret"])
CLAIMS = cur_feature("claims", "claims.json", ["priority", "odds", "note", "drop"])
NEEDS = cur_feature("needs", "needs.json", ["need"])
IR_RET = cur_feature("irReturns", "ir_returns.json", ["returnWeek", "note"], optional=True)
def po_sched(tid):
    if tid in (0, None): return []
    g = next((p for p in pro["settings"]["proTeams"] if p["id"] == tid), None)
    if not g: raise KeyError(f"no schedule for proTeamId {tid}")
    s = []
    for w in PLAYOFF_WEEKS:
        gl = g.get("proGamesByScoringPeriod", {}).get(str(w), [])
        if not gl: s.append("BYE"); continue
        x = gl[0]; o = x["awayProTeamId"] if x["homeProTeamId"] == tid else x["homeProTeamId"]
        s.append(("@" if x["awayProTeamId"] == tid else "") + abbr(o))
    return s
# ---- scores + standings (ties are ties: not wins, not losses) ----
POS = om.POS
weekly = defaultdict(dict); nmatch = defaultdict(int)
W = defaultdict(int); L = defaultdict(int); T = defaultdict(int); PF = defaultdict(float); H = defaultdict(int); rem = []; sc = defaultdict(list)
def result(g):
    """(winner, loser) or None for a tie. Uses ESPN's winner field, falls back to points."""
    h, a = g["home"]["teamId"], g["away"]["teamId"]; hs, as_ = g["home"]["totalPoints"], g["away"]["totalPoints"]
    if g["winner"] == "TIE" or hs == as_: return None
    return (h, a) if (g["winner"] == "HOME" if g["winner"] in ("HOME", "AWAY") else hs > as_) else (a, h)
for g in m["schedule"]:
    p = g["matchupPeriodId"]
    if p > REG: continue
    h, a = g["home"]["teamId"], g["away"]["teamId"]
    if g["winner"] != "UNDECIDED":
        hs, as_ = g["home"]["totalPoints"], g["away"]["totalPoints"]
        weekly[p][names[h]] = round(hs, 2); weekly[p][names[a]] = round(as_, 2); nmatch[p] += 1
        sc[h].append(hs); sc[a].append(as_); PF[h] += hs; PF[a] += as_
        res = result(g)
        if res: W[res[0]] += 1; L[res[1]] += 1; H[res] += 1
        else: T[h] += 1; T[a] += 1
    else: rem.append((p, h, a))
done_weeks = sorted(weekly)
def stats(p): return om.stats_map(p, YR)
def played(p): return om.played_weeks(p, YR)
# ---- player pool (weekly stats for every rostered player; used for return weeks and the players docs) ----
FLT_STATS = {"value": 17, "additionalValue": [f"00{YR}", f"10{YR}", f"01{YR}", f"11{YR}", f"11{YR}{wk}"]}
all_p = get(f"scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps({"players": {"limit": 800, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": FLT_STATS}})})["players"]
league_ids = [e["playerId"] for tm in r["teams"] for e in tm["roster"]["entries"]]
seen_ids = {pe["player"]["id"] for pe in all_p}
missing_any = [i for i in league_ids if i not in seen_ids]
for i in range(0, len(missing_any), 50):  # rostered player outside the top-800 pull: fetch by id, never drop silently
    all_p += get(f"scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps({"players": {"filterIds": {"value": missing_any[i:i + 50]}, "filterStatsForTopScoringPeriodIds": FLT_STATS}})})["players"]
PLAYED = {pe["player"]["id"]: played(pe["player"]) for pe in all_p}
still_missing = [i for i in league_ids if i not in PLAYED]
fa_cache = {}
def fa_raw():
    if "x" not in fa_cache:
        fa_cache["x"] = get(f"scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps({"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 400, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})})["players"]
    return fa_cache["x"]
# ---- odds model v2: week-by-week strength from per-game projections ----
if not any(stats(e["playerPoolEntry"]["player"]).get((1, 1, wk)) for tm in r["teams"] for e in tm["roster"]["entries"]):
    raise SystemExit(f"all-zero projections for week {wk}: ESPN projections missing")
fa_by = defaultdict(list)
for x in fa_raw():
    q = x["player"]; pos = POS.get(q["defaultPositionId"])
    if pos and bye.get(q.get("proTeamId")) != wk: fa_by[pos].append(stats(q).get((1, 1, wk), 0) or 0)
REPL = {pos: round(sorted(v, reverse=True)[2], 2) for pos, v in fa_by.items() if len(v) > 2}
missing_repl = [p for p in POS.values() if p not in REPL]
if missing_repl: raise SystemExit(f"quality gate: no free-agent replacement level for {missing_repl} (free-agent pull returned {len(fa_raw())} players)")
GW = om.nfl_game_weeks(pro)
last_nfl = max(w for v in GW.values() for w in v)
wproj, full, injured = {}, {}, {}
for tm in r["teams"]:
    wproj[tm["id"]], full[tm["id"]], injured[tm["id"]] = om.team_week_projections(tm["roster"]["entries"], wk, REG, SLOT_COUNTS, GW, YR, IR_RET, PLAYED, REPL, last_nfl)
zero = [f"{names[k]} wk {w}" for k, v in wproj.items() for w, x in v.items() if x <= 0]
if zero: raise SystemExit(f"quality gate: zero team projection for {zero}")
mu, calib = om.strengths(list(names), wproj, full, sc)
SD = om.weekly_sd(sc)
GP = statistics.mean(len(v) for v in sc.values()) if sc else 0
made, top, cush, seeds = om.simulate(list(names), me, PO, W, T, PF, H, rem, mu, SD, GP, N, random.Random())
order = om.rank(list(names), {k: W[k] + 0.5 * T[k] for k in names}, PF, H)
esp_seed = {x["id"]: x.get("playoffSeed") for x in t["teams"]}
seed_check = {"matchesEspn": all(esp_seed.get(k) in (None, i + 1) for i, k in enumerate(order)),
              "mismatch": [f"{names[k]}: ours {i + 1}, ESPN {esp_seed.get(k)}" for i, k in enumerate(order) if esp_seed.get(k) not in (None, i + 1)]}
def strength(k): return round(statistics.mean(mu[k].values()), 1)
teams = [{"id": k, "name": names[k], "w": W[k], "l": L[k], "t": T[k], "pf": round(PF[k], 2), "seed": order.index(k)+1,
          "playoffPct": round(100*made[k]/N), "byePct": round(100*top[k]/N), "strength": strength(k), "strengthNow": round(mu[k][wk], 1),
          "strengthByWeek": {str(w): round(v, 1) for w, v in mu[k].items()}, "fullStrength": round(full[k] + calib["bias"] + calib["adj"][k], 1),
          "seedPct": {str(s): round(100 * c / N, 1) for s, c in sorted(seeds[k].items())},
          "hundreds": sum(1 for x in sc[k] if x >= 100)} for k in names]
rec = lambda k: f"{W[k]}-{L[k]}" + (f"-{T[k]}" if T[k] else "")
MODEL = {"name": om.MODEL, "sd": round(SD, 2), "teamSd": round(SD / math.sqrt(GP + om.K_SHRINK), 2), "bias": calib["bias"], "leagueActualMean": calib["leagueActualMean"],
         "replacement": REPL, "seedCheck": seed_check, "sims": N, "irOverrides": sorted(k for k, v in IR_RET.items() if not v.get("expired")),
         "returns": {names[k]: v for k, v in injured.items() if v}}
# ---- players: our roster + every tagged player ----
SLOTS = {0: "QB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE", 7: "OP", 23: "FLEX", 16: "D/ST", 17: "K", 20: "Bench", 21: "IR"}
my_entries = [e for tm in r["teams"] if tm["id"] == me for e in tm["roster"]["entries"]]
roster_ids = [e["playerId"] for e in my_entries]
slot_of = {e["playerId"]: SLOTS.get(e["lineupSlotId"], str(e["lineupSlotId"])) for e in my_entries}
ret_of = {d["name"]: d for v in injured.values() for d in v}
players = {}
for pe in all_p:
    p = pe["player"]; own = pe.get("onTeamId", 0)
    if own != me and p["fullName"] not in TAGS: continue
    st = stats(p); pos = POS.get(p["defaultPositionId"], "?"); nfl = p.get("proTeamId")
    tg = TAGS.get(p["fullName"], {"tag": "roster", "note": "", "ret": ""})
    tag = tg.get("tag", "roster")
    if own == me and tag in ("claim", "buy", "target", "rental"): tag = "roster"
    d = {"name": p["fullName"], "pos": pos, "nfl": abbr(nfl), "owner": names.get(own, "Free agent"),
        "ownerId": own, "ours": own == me, "slot": slot_of.get(p["id"]) if own == me else None, "status": p.get("injuryStatus") or "ACTIVE", "tag": tag, "note": tg.get("note", ""), "ret": tg.get("ret", ""),
        "weekly": {str(w): (round(st.get((0, 1, w)) or 0, 1) if w in played(p) and w != bye.get(nfl) else None) for w in range(1, wk)},  # None = did not play (bye/inactive/IR)
        "total": round(st.get((0, 0, YR)) or st.get((0, 0, 0)) or 0, 1),
        "nextProj": round(st.get((1, 1, wk), 0) or 0, 1), "seasonProj": round(st.get((1, 0, YR)) or st.get((1, 0, 0)) or 0, 1),
        "bye": bye.get(nfl), "playoffs": po_sched(nfl)}
    if p["fullName"] in ret_of: d["modelReturnWeek"] = ret_of[p["fullName"]]["returnWeek"]; d["modelReturnWhy"] = ret_of[p["fullName"]]["why"]
    if p["fullName"] in TAGS:
        d.update({"tagAsOf": tg.get("asOf"), "tagExpiresWeek": tg.get("expiresWeek"), "tagExpired": tg["expired"], "tagLegacy": bool(tg.get("legacy"))})
    if p["fullName"] in CLAIMS and own != me:
        c = CLAIMS[p["fullName"]]
        d["claim"] = {"priority": c.get("priority"), "odds": c.get("odds"), "note": c.get("note", ""), "drop": c.get("drop", ""),
                      "asOf": c.get("asOf"), "expiresWeek": c.get("expiresWeek"), "expired": c["expired"], "legacy": bool(c.get("legacy"))}
    players[str(p["id"])] = d
unresolved_roster = [i for i in roster_ids if str(i) not in players]
unresolved_tags = sorted(set(TAGS) - {d["name"] for d in players.values()})
mine = next(x for x in teams if x["id"] == me)
os.makedirs(out, exist_ok=True)
def dump(coll, did, data):
    os.makedirs(f"{out}/{coll}", exist_ok=True); json.dump(data, open(f"{out}/{coll}/{did}.json", "w"))
# ---- extras: each feature on its own; failure -> {"error": reason} and non-zero exit ----
extras = {}
def feature(name, fn, required=True):
    try: extras[name] = fn()
    except Exception as e:
        extras[name] = {"error": f"{type(e).__name__}: {e}"}
        if required: ERRORS[f"extras.{name}"] = extras[name]["error"]
        print(f"FEATURE FAILED {name}: {extras[name]['error']}", file=sys.stderr)
    return extras[name]
games = [g_ for g_ in m["schedule"] if g_["matchupPeriodId"] <= REG]
def res_through(w_):
    W_ = defaultdict(int); L_ = defaultdict(int); T_ = defaultdict(int); PF_ = defaultdict(float); H_ = defaultdict(int)
    for g_ in games:
        if g_["matchupPeriodId"] > w_ or g_["winner"] == "UNDECIDED": continue
        h_, a_ = g_["home"]["teamId"], g_["away"]["teamId"]; PF_[h_] += g_["home"]["totalPoints"]; PF_[a_] += g_["away"]["totalPoints"]
        rs = result(g_)
        if rs: W_[rs[0]] += 1; L_[rs[1]] += 1; H_[rs] += 1
        else: T_[h_] += 1; T_[a_] += 1
    return W_, L_, T_, PF_, H_
def f_prev():
    """Last week's odds re-run with today's strengths (weeks already played use each team's full-strength level)."""
    if wk <= 2: return None
    w_done = wk - 2
    W_, L_, T_, PF_, H_ = res_through(w_done); rem_ = [(g_["matchupPeriodId"], g_["home"]["teamId"], g_["away"]["teamId"]) for g_ in games if g_["matchupPeriodId"] > w_done]
    mu_p = {k: {w_: mu[k].get(w_, full[k] + calib["bias"] + calib["adj"][k]) for w_ in range(w_done + 1, REG + 1)} for k in names}
    gp_ = statistics.mean(sum(1 for g_ in games if g_["matchupPeriodId"] <= w_done and k in (g_["home"]["teamId"], g_["away"]["teamId"])) for k in names)
    made_, top_, _, _ = om.simulate(list(names), me, PO, W_, T_, PF_, H_, rem_, mu_p, SD, gp_, N, random.Random(7))
    wp_ = {k: W_[k] + 0.5 * T_[k] for k in names}; o_ = om.rank(list(names), wp_, PF_, H_)
    return {"record": f"{W_[me]}-{L_[me]}" + (f"-{T_[me]}" if T_[me] else ""), "seed": o_.index(me) + 1, "playoffPct": round(100 * made_[me] / N), "byePct": round(100 * top_[me] / N),
            "pf": round(PF_[me], 2), "gamesAhead8": wp_[me] - wp_[o_[PO]], "throughWeek": w_done}
def starters(tid):
    tm = next(x for x in r["teams"] if x["id"] == tid); out_ = []
    for e in tm["roster"]["entries"]:
        p = e["playerPoolEntry"]["player"]; sl = SLOTS.get(e["lineupSlotId"])
        if sl is None: raise KeyError(f"unknown lineup slot {e['lineupSlotId']}")
        if sl in ("Bench", "IR"): continue
        st = stats(p); out_.append({"name": p["fullName"], "slot": sl, "pos": POS.get(p["defaultPositionId"], "?"), "nfl": abbr(p.get("proTeamId")),
            "proj": round(st.get((1, 1, wk), 0) or 0, 1), "status": p.get("injuryStatus") or "ACTIVE", "bye": bye.get(p.get("proTeamId")) == wk})
    return out_
tby = {x["id"]: x for x in teams}
def f_matchup():
    g0 = next((g_ for g_ in games if g_["matchupPeriodId"] == wk and me in (g_["home"]["teamId"], g_["away"]["teamId"])), None)
    if not g0:
        if wk > REG: return None  # regular season over; playoff bracket not modelled here
        raise LookupError(f"no week {wk} matchup for team {me}")
    opp = g0["away"]["teamId"] if g0["home"]["teamId"] == me else g0["home"]["teamId"]
    us_s, op_s = starters(me), starters(opp); pu, po_ = sum(x["proj"] for x in us_s), sum(x["proj"] for x in op_s)
    wp = 0.5 * (1 + math.erf((pu - po_) / (SD * math.sqrt(2)) / math.sqrt(2)))
    # ESPN's own win probability and projected totals (Joe, Oct 8: the Overview shows ESPN's number only; winPct stays as our model's, unused by the page)
    side = lambda t_: g0["home"] if g0["home"]["teamId"] == t_ else g0["away"]
    ew = side(me).get("winProbability"); ep_us = side(me).get("totalProjectedPoints"); ep_op = side(opp).get("totalProjectedPoints")
    if ew is None: raise ValueError("ESPN matchup has no winProbability")
    return {"espnWinPct": round(100 * ew), "espnProjUs": round(ep_us, 2) if ep_us is not None else None, "espnProjOpp": round(ep_op, 2) if ep_op is not None else None, "espnWinAsOf": now_iso(), "week": wk, "opp": names[opp], "oppRecord": rec(opp), "oppSeed": tby[opp]["seed"], "projUs": round(pu, 1), "projOpp": round(po_, 1),
            "winPct": round(100 * wp), "flags": [x for x in us_s if x["bye"] or x["status"] in ("OUT", "INJURY_RESERVE", "DOUBTFUL", "SUSPENSION", "QUESTIONABLE")],
            "usStarters": us_s, "oppStarters": op_s, "starterCount": len(us_s), "starterSlots": STARTERS}
SB = {}
def f_nfl():
    """NFL scoreboards for weeks 1..wk; per-week scheduled vs scoreboard vs completed game counts."""
    sched = defaultdict(set)
    for p in pro["settings"]["proTeams"]:
        for w_, gl in p.get("proGamesByScoringPeriod", {}).items():
            for x in gl: sched[int(w_)].add(x["id"])
    weeks = {}
    for w_ in range(1, wk + 1):
        s_ = _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w_}&dates={YR}"); SB[w_] = s_
        weeks[str(w_)] = {"scheduled": len(sched[w_]), "scoreboard": len(s_["events"]), "completed": sum(1 for e in s_["events"] if e["status"]["type"]["completed"]),
                          "final": w_ < wk}
    return weeks
def f_dates():
    fr = fa_raw(); wpd = [x.get("waiverProcessDate") for x in fr if x.get("waiverProcessDate")]
    sb = SB.get(wk) or _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={wk}&dates={YR}")
    dl = S.get("tradeSettings", {}).get("deadlineDate")
    return {"waivers": datetime.fromtimestamp(min(wpd) / 1000, timezone.utc).isoformat() if wpd else None,
            "waiversET": datetime.fromtimestamp(min(wpd) / 1000, ET).isoformat() if wpd else None,
            "kickoff": min((e["date"] for e in sb["events"]), default=None),
            "tradeDeadline": datetime.fromtimestamp(dl / 1000, timezone.utc).isoformat() if dl else None,
            "tradeDeadlineET": datetime.fromtimestamp(dl / 1000, ET).isoformat() if dl else None}
def f_free_agents():
    fas = defaultdict(list)
    for x in fa_raw():
        p = x["player"]; pos = POS.get(p["defaultPositionId"])
        if not pos: continue
        st = stats(p); pr = round(st.get((1, 1, wk), 0) or 0, 1)
        if bye.get(p.get("proTeamId")) == wk or pr <= 0: continue
        fas[pos].append({"name": p["fullName"], "nfl": abbr(p.get("proTeamId")), "proj": pr, "pct": round(p.get("ownership", {}).get("percentOwned", 0), 1), "status": x.get("status"), "inj": p.get("injuryStatus") or "ACTIVE"})
    if not fas: raise ValueError("no free agents with a projection > 0")
    return {k: sorted(v, key=lambda z: -z["proj"])[:4] for k, v in fas.items()}
def f_race():
    wp = {k: W[k] + 0.5 * T[k] for k in names}; first, last_in, first_out = order[0], order[PO - 1], order[PO]
    remaining = defaultdict(list); h2h = {}
    for g_ in games:
        h_, a_ = g_["home"]["teamId"], g_["away"]["teamId"]
        if g_["winner"] == "UNDECIDED": remaining[h_].append((g_["matchupPeriodId"], a_)); remaining[a_].append((g_["matchupPeriodId"], h_))
        if me in (h_, a_):
            o_ = a_ if h_ == me else h_
            if g_["winner"] == "UNDECIDED": h2h[o_] = f'Wk {g_["matchupPeriodId"]}'
            else:
                rs = result(g_); h2h[o_] = ("T" if not rs else "W" if rs[0] == me else "L") + f' Wk {g_["matchupPeriodId"]}'
    gb = lambda a_, b_: wp[a_] - wp[b_]
    return [{"name": names[k], "seed": i + 1, "w": W[k], "l": L[k], "t": T[k], "gb1": gb(first, k), "vsCut": gb(k, first_out) if i < PO else -gb(last_in, k),
             "vs7": gb(k, first_out) if i < PO else -gb(last_in, k),  # legacy key; same as vsCut
             "sos": round(statistics.mean(mu[o_][w_] for w_, o_ in remaining[k]), 1) if remaining[k] else None, "h2h": h2h.get(k, "—" if k == me else ""),
             "po": tby[k]["playoffPct"], "bye": tby[k]["byePct"]} for i, k in enumerate(order)]
def f_roster_grid():
    if "error" in (extras.get("nfl") or {}): raise RuntimeError("needs nfl scoreboards: " + extras["nfl"]["error"])
    pa = defaultdict(list); pscored = defaultdict(list)
    for w_ in range(1, wk):
        for e in SB[w_]["events"]:
            if not e["status"]["type"]["completed"]: continue
            a_, b_ = e["competitions"][0]["competitors"]
            pa[a_["team"]["abbreviation"]].append(int(b_["score"])); pa[b_["team"]["abbreviation"]].append(int(a_["score"]))
            pscored[a_["team"]["abbreviation"]].append(int(a_["score"])); pscored[b_["team"]["abbreviation"]].append(int(b_["score"]))
    ppa = {k: round(statistics.mean(v), 1) for k, v in pa.items()}; ppf = {k: round(statistics.mean(v), 1) for k, v in pscored.items()}
    def opp_v(code, d):
        c = code.lstrip("@"); v = d.get(c) or d.get({"WSH": "WAS", "WAS": "WSH"}.get(c, c))
        if v is None: raise KeyError(f"no points-allowed for {c}")
        return v
    # ESPN opponent rank by position (the OPRK column on ESPN's roster page, Oct 7 Joe): view=mPositionalRatings,
    # positionalRatings[posId].ratingsByOpponent[proTeamId] = {rank, average}; rank 1 = allows the fewest fantasy points to that position
    PR = get("view=mPositionalRatings").get("positionAgainstOpponent", {}).get("positionalRatings", {})
    if not PR: raise RuntimeError("ESPN positional ratings (OPRK) empty")
    POSID = {"QB": "1", "RB": "2", "WR": "3", "TE": "4", "K": "5", "D/ST": "16"}
    abid = {v.upper(): k for k, v in ab.items()}
    def oprk(code, pos):
        c = code.lstrip("@").upper(); tid = abid.get(c) or abid.get({"WSH": "WAS", "WAS": "WSH"}.get(c, c))
        r_ = PR.get(POSID.get(pos, ""), {}).get("ratingsByOpponent", {}).get(str(tid))
        if r_ is None: raise KeyError(f"no OPRK for {pos} vs {c}")
        return int(r_["rank"]), round(float(r_["average"]), 1)
    def pentry(o_, pos):
        if o_ == "BYE": return {"opp": o_, "pa": None, "ps": None, "oprk": None, "oavg": None}
        rk, av = oprk(o_, pos)
        return {"opp": o_, "pa": opp_v(o_, ppa), "ps": opp_v(o_, ppf), "oprk": rk, "oavg": av}
    grid = [{"name": p["name"], "pos": p["pos"], "nfl": p["nfl"], "slot": p.get("slot"), "bye": p.get("bye"),
             "playoffs": [pentry(o_, p["pos"]) for o_ in (p.get("playoffs") or [])]}
            for p in players.values() if p.get("ours")]
    return {"grid": grid, "leaguePA": round(statistics.mean(ppa.values()), 1) if ppa else None, "paWeeks": [1, wk - 1] if wk > 1 else None}
feature("prev", f_prev)
feature("matchup", f_matchup)
feature("nfl", f_nfl)
feature("dates", f_dates)
feature("freeAgents", f_free_agents)
feature("race", f_race)
rg_raw = feature("rosterGrid", f_roster_grid)
nfl_weeks_raw = extras["nfl"]
# ---- league block: everything a page needs instead of hard-coding league facts ----
league = {"playoffTeams": PO, "regSeasonWeeks": REG, "playoffWeeks": PLAYOFF_WEEKS, "starters": STARTERS, "slotCounts": {str(k): v for k, v in SLOT_COUNTS.items()},
          "teams": len(names), "currentWeek": wk, "teamId": me,
          "waiverProcessET": (extras["dates"] or {}).get("waiversET") if "error" not in (extras["dates"] or {}) else None,
          "avgWeeksRange": [done_weeks[0], done_weeks[-1]] if done_weeks else None, "completedWeeks": done_weeks,
          "seedingRule": SS.get("playoffSeedingRule"), "tradeDeadlineET": (extras["dates"] or {}).get("tradeDeadlineET") if "error" not in (extras["dates"] or {}) else None}
if unresolved_roster: ERRORS["players.unresolvedRoster"] = f"{len(unresolved_roster)} rostered ids not resolved: {unresolved_roster}"
if still_missing: ERRORS["players.leaguePool"] = f"{len(still_missing)} league-rostered ids missing from the weekly-stats pull: {still_missing[:10]}"
# ESPN's league setting breaks every tie by points for; our rule (Joe, Oct 6) settles two-team ties head-to-head first, so a
# mismatch can be correct. It is reported (meta.model.seedCheck + a printed note), not failed.
if not seed_check["matchesEspn"]: print("NOTE seeding differs from ESPN's playoffSeed (two-team head-to-head rule?): " + "; ".join(seed_check["mismatch"]), file=sys.stderr)
stamp = now_iso()
sections = {k: {"ok": True, "stale": False, "updatedAt": stamp} for k in ("meta", "players", "scores", "odds", "waivers", "nfl")}
sections["curated"] = {"ok": not any(k.startswith("curated.") for k in ERRORS), "stale": False, "updatedAt": stamp, **({"error": "; ".join(v for k, v in ERRORS.items() if k.startswith("curated."))} if any(k.startswith("curated.") for k in ERRORS) else {})}
if "error" in nfl_weeks_raw: sections["nfl"] = {"ok": False, "stale": False, "error": nfl_weeks_raw["error"]}
if unresolved_roster: sections["players"] = {"ok": False, "stale": False, "updatedAt": stamp, "error": ERRORS["players.unresolvedRoster"]}
for k, v in [(k, v) for k, v in extras.items() if k not in ("nfl", "rosterGrid")] + [("roster", rg_raw)]:
    sections[f"extras.{k}"] = {"ok": False, "stale": False, "error": v["error"]} if isinstance(v, dict) and "error" in v else {"ok": True, "stale": False, "updatedAt": stamp}
sections["extras"] = {"ok": all(v["ok"] for k, v in sections.items() if k.startswith("extras.")), "stale": False, "updatedAt": stamp}
dump("meta", "current", {"week": wk, "updatedAt": stamp, "team": names[me], "teamId": me,
     "record": rec(me), "seed": mine["seed"], "playoffPct": mine["playoffPct"], "byePct": mine["byePct"],
     "cushion": round(statistics.mean(cush), 1), "pf": mine["pf"], "sims": N, "league": league, "model": MODEL,
     "rosterIds": roster_ids, "unresolvedRoster": unresolved_roster, "unresolvedTags": unresolved_tags, "errors": ERRORS, "sections": sections})
dump("odds", f"w{wk:02d}", {"week": wk, "updatedAt": stamp, "model": om.MODEL, "sd": MODEL["sd"], "teamSd": MODEL["teamSd"], "sims": N, "teams": teams})
# ---- odds history: one entry per run, kept across runs (LT_ODDS_HISTORY), never rewritten ----
HIST = os.environ.get("LT_ODDS_HISTORY")  # project copy: claude/data/odds_history.json (read it in, write it back after the run)
hist = {"runs": []}
if not HIST: print("NOTE LT_ODDS_HISTORY not set: odds/history not written this run (a fresh file would overwrite the stored history)", file=sys.stderr)
if HIST and os.path.exists(HIST):
    hist = json.load(open(HIST))
    if not isinstance(hist.get("runs"), list): raise SystemExit(f"odds history file {HIST} has no runs list")
hist["runs"].append({"at": stamp, "week": wk, "model": om.MODEL, "sims": N,
                     "teams": {names[k]: {"po": tby[k]["playoffPct"], "bye": tby[k]["byePct"], "seed": tby[k]["seed"], "rec": rec(k)} for k in names}})
hist["updatedAt"] = stamp
if HIST: json.dump(hist, open(HIST, "w"), indent=1); dump("odds", "history", hist)
for w, s in weekly.items(): dump("scores", f"w{w:02d}", {"week": w, "updatedAt": stamp, "matchups": nmatch[w], "scores": s})
def need_of(team):
    n = NEEDS.get(team)
    return ({"need": n.get("need", ""), "needAsOf": n.get("asOf"), "needExpiresWeek": n.get("expiresWeek"), "needExpired": n["expired"], "needLegacy": bool(n.get("legacy"))} if n else {"need": ""})
dump("waivers", "current", {"week": wk, "updatedAt": stamp, "order": [{"rank": x.get("waiverRank"), "team": x["name"].strip(), "record": f'{x["record"]["overall"]["wins"]}-{x["record"]["overall"]["losses"]}' + (f'-{x["record"]["overall"]["ties"]}' if x["record"]["overall"].get("ties") else ""), **need_of(x["name"].strip())} for x in sorted(t["teams"], key=lambda x: x.get("waiverRank", 99))]})
for pid, d in players.items(): dump("players", pid, d)
dump("curated", "current", {"updatedAt": stamp, "week": wk, **cur_status})
nfl_weeks = extras.pop("nfl")  # team list comes from the core schedule pull; game counts need the scoreboards
dump("nfl", "current", {"updatedAt": stamp, "teams": sorted(ab.values()), "byes": {ab[k]: v for k, v in bye.items()},
     **({"weeks": {}, "weeksError": nfl_weeks["error"]} if "error" in nfl_weeks else {"weeks": nfl_weeks})})
POSN = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
dump("rosters", "current", {"week": wk, "updatedAt": stamp, "teams": {names[x["id"]]: [
    {"id": e["playerId"], "name": e["playerPoolEntry"]["player"]["fullName"], "pos": POSN.get(e["playerPoolEntry"]["player"]["defaultPositionId"], "?"),
     "nfl": abbr(e["playerPoolEntry"]["player"].get("proTeamId")), "slot": SLOTS.get(e["lineupSlotId"], str(e["lineupSlotId"])),
     "status": e["playerPoolEntry"]["player"].get("injuryStatus") or "ACTIVE"} for e in x["roster"]["entries"]] for x in r["teams"]}})
g = extras.pop("rosterGrid")
dump("extras", "current", {"week": wk, "updatedAt": stamp, "builtAt": stamp, **extras,
     "roster": g if "error" in g else g["grid"], "leaguePA": None if "error" in g else g["leaguePA"], "paWeeks": None if "error" in g else g["paWeeks"],
     "regWeeks": REG, "league": league,
     "scouting": {"week": wk, "asOf": datetime.now(ET).date().isoformat(), "usSeed": mine["seed"], "regWeeks": REG, "league": league},
     "errors": {k.split(".", 1)[1]: v for k, v in ERRORS.items() if k.startswith("extras.")}})
print(f"week {wk}: {len(players)} players, {len(weekly)} score weeks, me={me} ({names[me]}) -> {out} | model sd {SD:.1f}, bias {calib['bias']:+.1f}, seeds match ESPN: {seed_check['matchesEspn']}")
if ERRORS:
    print("FAILED features: " + "; ".join(f"{k}: {v}" for k, v in ERRORS.items()), file=sys.stderr); sys.exit(2)
