"""Legal Troubles BI refresh (Rich/Maya). Run weekly: python3 bi_refresh.py <out_dir> [sims]
Pulls live ESPN data, runs the playoff sim, and writes one JSON file per dashboard document:
  meta/current, odds/wNN, scores/wNN (every completed week), players/<espnId>
Then load them with ArtifactData action 'batch' (op 'set', file_path) into the BI dashboard.
Market tags and notes come from Tony's Market Watch: edit TAGS below each week."""
import json, os, sys, random, statistics, urllib.request
from collections import defaultdict
LG = 293318; YR = 2026
B = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}/segments/0/leagues/{LG}"
def get(q, hdr=None):
    req = urllib.request.Request(f"{B}?{q}", headers=hdr or {})
    return json.load(urllib.request.urlopen(req, timeout=90))
# ---- Tony's Market Watch: name -> (tag, note, return/when) ----
TAGS = {
 "Aaron Jones Sr.": ("sell", "Bell-cow only while Jordan Mason (thumb surgery, IR) is out. Mason eligible Wk 7; Jones bye Wk 6. Sell this week.", "Mason back Wk 7"),
 "Brian Robinson Jr.": ("sell", "3 TDs Monday night: value at its peak. RB surplus once Charbonnet (~Wk 7-8) and Price (Wk 8) return.", "Sell this week"),
 "Dohnte Meyers": ("claim", "Bengals' top target while Ja'Marr Chase is in concussion protocol. ~29 pts in Wk 4 with 170 return yds.", "Chase: no timeline"),
 "Drake Maye": ("claim", "Covers Josh Allen's Wk 7 bye. Starting QB = trade chip with 6-pt pass TDs.", "Allen bye Wk 7"),
 "Joe Mixon": ("claim", "Seahawks planned a practice-squad deal (Oct 5) pending a physical; one Oct 6 report says it fell through. If he signs, he threatens our Seattle stashes (Charbonnet, Price) and owning him locks up the backfield.", "Physical pending"),
 "Will Shipley": ("rental", "Eagles lead back now: Saquon Barkley (hamstring) is week-to-week and Tank Bigsby (core surgery) is going on IR. Cut when Barkley returns.", "Barkley 1-3 wks"),
 "Rashid Shaheed": ("target", "Returner + deep threat: return yards and 40+ yd TD bonuses score extra for us. Team RM is RB-starved.", ""),
 "A.J. Brown": ("buy", "IR, high-ankle sprain since Sep 13. Owner gets nothing now; healthy for the playoffs.", "Back Wk 7-8"),
 "Justin Jefferson": ("buy", "Missed Wk 4 (ankle). JV Squad is 1-3 and may sell before he returns.", "Back Wk 5-6"),
 "Marcus Mariota": ("drop", "MCL sprain, multi-week; Jayden Daniels returns. No role.", ""),
 "Dalton Schultz": ("drop", "Backup TE; Kraft starts. Stream a TE for Kraft's Wk 11 bye.", ""),
 "Zach Charbonnet": ("stash", "ACL recovery; practice window opened Oct 1. Playoff RB.", "Activation ~Wk 7"),
 "Jadarian Price": ("stash", "IR (chest). Eligible Wk 8.", "Eligible Wk 8"),
 "Jordyn Tyson": ("stash", "IR (hamstring). Week 7 at the soonest.", "Wk 7+"),
 "Josh Jacobs": ("stash", "Commissioner's Exempt List; GB expects him back in 2026. Cut if a ban covers Wks 15-17.", "Unknown"),
}
# ---- Tony's waiver plan: name -> (priority, odds, competition note, drop) ----
CLAIMS = {
 "Dohnte Meyers": (1, "Unlikely", "Now the #2 add in all of fantasy (1.6M Sleeper adds in 24h). Several WR-needy teams pick ahead of us. Claim anyway; backup is the free-agent sprint when waivers clear.", "Marcus Mariota"),
 "Drake Maye": (2, "Unlikely", "We pick 14th of 14. Monty's (#4, Lamar questionable), Oviedo (#10, Mayfield out) and El' Político (#11, Caleb Williams out) need a QB and pick first. Backup: a Wk 7 QB on next week's waivers or the free-agent sprint.", "Kyle Williams"),
 "Joe Mixon": (3, "Hold", "Seahawks' deal is a practice-squad contract pending a physical, and one report (Oct 6) says it fell through after the physical. Claim only if the signing is confirmed before waivers run.", "Dalton Schultz"),
 "Will Shipley": (None, "Unlikely", "#5 add in fantasy (632K Sleeper adds). Team RM picks 3rd with no healthy RB. Watch only.", ""),
}
QB_NEED = {"Monty's": "Lamar Jackson questionable", "Pop A TD": "Jayden Daniels out (back Wk 5)", "Oviedo Roosters": "Baker Mayfield out", "El' Político": "Caleb Williams out", "Team RM": "No healthy RB", "JV Squad": "Justin Jefferson out"}
# ---- curated overrides (GitHub site): JSON files written by the front office ----
CUR = os.environ.get("LT_CURATED")
if CUR and os.path.isdir(CUR):
    def _j(n, d):
        f = os.path.join(CUR, n); return json.load(open(f)) if os.path.exists(f) else d
    TAGS = {k: tuple(v) for k, v in _j("tags.json", {k: list(v) for k, v in TAGS.items()}).items()}
    CLAIMS = {k: tuple(v) for k, v in _j("claims.json", {k: list(v) for k, v in CLAIMS.items()}).items()}
    QB_NEED = _j("needs.json", QB_NEED)
out = sys.argv[1] if len(sys.argv) > 1 else "bi_out"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
t = get("view=mTeam&view=mStatus&view=mSettings"); m = get("view=mMatchupScore&view=mMatchup"); r = get("view=mRoster")
pro = json.load(urllib.request.urlopen(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}?view=proTeamSchedules_wl", timeout=90))
wk = t["status"]["currentMatchupPeriod"]; REG = t["settings"]["scheduleSettings"]["matchupPeriodCount"]; PO = t["settings"]["scheduleSettings"]["playoffTeamCount"]
names = {x["id"]: x["name"].strip() for x in t["teams"]}
me = [k for k, v in names.items() if "Legal" in v][0]
ab = {p["id"]: p["abbrev"] for p in pro["settings"]["proTeams"]}; bye = {p["id"]: p["byeWeek"] for p in pro["settings"]["proTeams"]}
def po_sched(tid):
    g = next((p for p in pro["settings"]["proTeams"] if p["id"] == tid), None)
    if not g: return []
    s = []
    for w in ("15", "16", "17"):
        gl = g.get("proGamesByScoringPeriod", {}).get(w, [])
        if not gl: s.append("BYE"); continue
        x = gl[0]; o = x["awayProTeamId"] if x["homeProTeamId"] == tid else x["homeProTeamId"]
        s.append(("@" if x["awayProTeamId"] == tid else "") + ab.get(o, "?"))
    return s
# ---- scores + standings ----
POS = {1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
weekly = defaultdict(dict); W = defaultdict(int); L = defaultdict(int); PF = defaultdict(float); H = defaultdict(int); rem = []; sc = defaultdict(list)
for g in m["schedule"]:
    p = g["matchupPeriodId"]
    if p > REG: continue
    h, a = g["home"]["teamId"], g["away"]["teamId"]
    if g["winner"] != "UNDECIDED":
        hs, as_ = g["home"]["totalPoints"], g["away"]["totalPoints"]
        weekly[p][names[h]] = round(hs, 2); weekly[p][names[a]] = round(as_, 2)
        sc[h].append(hs); sc[a].append(as_); PF[h] += hs; PF[a] += as_
        w, l = (h, a) if hs > as_ else (a, h); W[w] += 1; L[l] += 1; H[(w, l)] += 1
    else: rem.append((h, a))
# ---- strength + sim ----
def best(pl):
    by = defaultdict(list)
    for p, v in pl: by[p].append(v)
    for k in by: by[k].sort(reverse=True)
    tot = sum(by[p][0] for p in ["QB","RB","WR","TE","D/ST","K"] if by[p])
    return tot + sum(sorted(by["RB"][1:] + by["WR"][1:] + by["TE"][1:], reverse=True)[:2])
def played(p): return {s["scoringPeriodId"] for s in p.get("stats", []) if s.get("seasonId", YR) == YR and s["statSourceId"] == 0 and s["statSplitTypeId"] == 1 and s.get("stats")}
def stats(p): return {(s["statSourceId"], s["statSplitTypeId"], s["scoringPeriodId"]): s.get("appliedTotal", 0) for s in p.get("stats", []) if s.get("seasonId", YR) == YR}
proj = {}
for tm in r["teams"]:
    proj[tm["id"]] = best([(POS[e["playerPoolEntry"]["player"]["defaultPositionId"]], stats(e["playerPoolEntry"]["player"]).get((1,1,wk), 0) or 0)
                         for e in tm["roster"]["entries"] if e["playerPoolEntry"]["player"]["defaultPositionId"] in POS])
lg = statistics.mean(x for v in sc.values() for x in v)
mu = {k: 0.35*statistics.mean(sc[k]) + 0.65*proj[k] for k in names}; adj = lg - statistics.mean(mu.values()); mu = {k: v+adj for k, v in mu.items()}
def rank(w, pf, hh):
    gr = defaultdict(list)
    for k in names: gr[w.get(k, 0)].append(k)
    o = []
    for x in sorted(gr, reverse=True):
        g = gr[x]; o += sorted(g, key=lambda k: (-sum(hh.get((k, z), 0) for z in g), -pf[k]))
    return o
made = defaultdict(int); top = defaultdict(int); cush = []
for _ in range(N):
    w = dict(W); pf = dict(PF); hh = dict(H)
    for h, a in rem:
        hs, as_ = random.gauss(mu[h], 21), random.gauss(mu[a], 21); pf[h] += hs; pf[a] += as_
        x, y = (h, a) if hs > as_ else (a, h); w[x] = w.get(x, 0)+1; hh[(x, y)] = hh.get((x, y), 0)+1
    o = rank(w, pf, hh)
    for k in o[:PO]: made[k] += 1
    top[o[0]] += 1; cush.append(w.get(me, 0) - w.get(o[PO], 0))
order = rank(W, PF, H)
teams = [{"id": k, "name": names[k], "w": W[k], "l": L[k], "pf": round(PF[k], 2), "seed": order.index(k)+1,
          "playoffPct": round(100*made[k]/N), "byePct": round(100*top[k]/N), "strength": round(mu[k], 1),
          "hundreds": sum(1 for x in sc[k] if x >= 100)} for k in names]
# ---- players: our roster + every tagged player ----
all_p = get(f"scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps({"players": {"limit": 800, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": {"value": 17, "additionalValue": [f"00{YR}", f"10{YR}", f"01{YR}", f"11{YR}", f"11{YR}{wk}"]}}})})
SLOTS = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 16: "D/ST", 17: "K", 20: "Bench", 21: "IR"}
slot_of = {e["playerId"]: SLOTS.get(e["lineupSlotId"], str(e["lineupSlotId"])) for tm in r["teams"] if tm["id"] == me for e in tm["roster"]["entries"]}
players = {}
for pe in all_p["players"]:
    p = pe["player"]; own = pe.get("onTeamId", 0)
    if own != me and p["fullName"] not in TAGS: continue
    st = stats(p); pos = POS.get(p["defaultPositionId"], "?"); nfl = p.get("proTeamId")
    tag, note, ret = TAGS.get(p["fullName"], ("roster", "", ""))
    if own == me and tag in ("claim", "buy", "target", "rental"): tag = "roster"
    players[str(p["id"])] = {"name": p["fullName"], "pos": pos, "nfl": ab.get(nfl, "FA"), "owner": names.get(own, "Free agent"),
        "ownerId": own, "ours": own == me, "slot": slot_of.get(p["id"]) if own == me else None, "status": p.get("injuryStatus") or "ACTIVE", "tag": tag, "note": note, "ret": ret,
        "weekly": {str(w): (round(st.get((0, 1, w)) or 0, 1) if w in played(p) and w != bye.get(nfl) else None) for w in range(1, wk)},  # None = did not play (bye/inactive/IR)
        "total": round(st.get((0, 0, YR)) or st.get((0, 0, 0)) or 0, 1),
        "nextProj": round(st.get((1, 1, wk), 0) or 0, 1), "seasonProj": round(st.get((1, 0, YR)) or st.get((1, 0, 0)) or 0, 1),
        "bye": bye.get(nfl), "playoffs": po_sched(nfl)}
    if p["fullName"] in CLAIMS and own != me:
        pr, odds, cn, dp = CLAIMS[p["fullName"]]
        players[str(p["id"])]["claim"] = {"priority": pr, "odds": odds, "note": cn, "drop": dp}
mine = next(x for x in teams if x["id"] == me)
os.makedirs(out, exist_ok=True)
def dump(coll, did, data):
    os.makedirs(f"{out}/{coll}", exist_ok=True); json.dump(data, open(f"{out}/{coll}/{did}.json", "w"))
from datetime import datetime, timezone
dump("meta", "current", {"week": wk, "updatedAt": datetime.now(timezone.utc).isoformat(timespec="minutes"), "team": names[me],
     "record": f'{mine["w"]}-{mine["l"]}', "seed": mine["seed"], "playoffPct": mine["playoffPct"], "byePct": mine["byePct"],
     "cushion": round(statistics.mean(cush), 1), "pf": mine["pf"], "sims": N})
dump("odds", f"w{wk:02d}", {"week": wk, "teams": teams})
for w, s in weekly.items(): dump("scores", f"w{w:02d}", {"week": w, "scores": s})
dump("waivers", "current", {"week": wk, "order": [{"rank": x.get("waiverRank"), "team": x["name"].strip(), "record": f'{x["record"]["overall"]["wins"]}-{x["record"]["overall"]["losses"]}', "need": QB_NEED.get(x["name"].strip(), "")} for x in sorted(t["teams"], key=lambda x: x.get("waiverRank", 99))]})
for pid, d in players.items(): dump("players", pid, d)
# ---- extras: this week's matchup, KPI change vs last week, seed race, bye/playoff grids, free agents, key dates ----
try:
    import math
    def _get(u, h=None): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=h or {}), timeout=90))
    games = [g_ for g_ in m["schedule"] if g_["matchupPeriodId"] <= REG]
    def res_through(w_):
        W_ = defaultdict(int); L_ = defaultdict(int); PF_ = defaultdict(float); H_ = defaultdict(int)
        for g_ in games:
            if g_["matchupPeriodId"] > w_ or g_["winner"] == "UNDECIDED": continue
            h_, a_ = g_["home"]["teamId"], g_["away"]["teamId"]; hs_, as2 = g_["home"]["totalPoints"], g_["away"]["totalPoints"]
            PF_[h_] += hs_; PF_[a_] += as2; x_, y_ = (h_, a_) if hs_ > as2 else (a_, h_); W_[x_] += 1; L_[y_] += 1; H_[(x_, y_)] += 1
        return W_, L_, PF_, H_
    def prev_kpis(w_done, n_=N):
        W_, L_, PF_, H_ = res_through(w_done); rem_ = [(g_["home"]["teamId"], g_["away"]["teamId"]) for g_ in games if g_["matchupPeriodId"] > w_done]
        made_ = defaultdict(int); top_ = defaultdict(int); rng = random.Random(7)
        for _ in range(n_):
            w_ = dict(W_); pf_ = dict(PF_); hh_ = dict(H_)
            for h_, a_ in rem_:
                hs_, as2 = rng.gauss(mu[h_], 21), rng.gauss(mu[a_], 21); pf_[h_] = pf_.get(h_, 0) + hs_; pf_[a_] = pf_.get(a_, 0) + as2
                x_, y_ = (h_, a_) if hs_ > as2 else (a_, h_); w_[x_] = w_.get(x_, 0) + 1; hh_[(x_, y_)] = hh_.get((x_, y_), 0) + 1
            o_ = rank(w_, pf_, hh_)
            for k_ in o_[:PO]: made_[k_] += 1
            top_[o_[0]] += 1
        o_ = rank(W_, PF_, H_)
        return {"record": f"{W_[me]}-{L_[me]}", "seed": o_.index(me) + 1, "playoffPct": round(100 * made_[me] / n_), "byePct": round(100 * top_[me] / n_),
                "pf": round(PF_[me], 2), "gamesAhead8": ((W_[me] - W_[o_[PO]]) + (L_[o_[PO]] - L_[me])) / 2}
    prev = prev_kpis(wk - 2) if wk > 2 else None
    def starters(tid):
        tm = next(x for x in r["teams"] if x["id"] == tid); out_ = []
        for e in tm["roster"]["entries"]:
            p = e["playerPoolEntry"]["player"]; sl = SLOTS.get(e["lineupSlotId"], "?")
            if sl in ("Bench", "IR"): continue
            st = stats(p); out_.append({"name": p["fullName"], "slot": sl, "pos": POS.get(p["defaultPositionId"], "?"), "nfl": ab.get(p.get("proTeamId"), "FA"),
                "proj": round(st.get((1, 1, wk), 0) or 0, 1), "status": p.get("injuryStatus") or "ACTIVE", "bye": bye.get(p.get("proTeamId")) == wk})
        return out_
    tby = {x["id"]: x for x in teams}
    g0 = next((g_ for g_ in games if g_["matchupPeriodId"] == wk and me in (g_["home"]["teamId"], g_["away"]["teamId"])), None)
    matchup = None
    if g0:
        opp = g0["away"]["teamId"] if g0["home"]["teamId"] == me else g0["home"]["teamId"]
        us_s, op_s = starters(me), starters(opp); pu, po_ = sum(x["proj"] for x in us_s), sum(x["proj"] for x in op_s)
        wp = 0.5 * (1 + math.erf((pu - po_) / (21 * math.sqrt(2)) / math.sqrt(2)))
        matchup = {"week": wk, "opp": names[opp], "oppRecord": f'{tby[opp]["w"]}-{tby[opp]["l"]}', "oppSeed": tby[opp]["seed"], "projUs": round(pu, 1), "projOpp": round(po_, 1),
                   "winPct": round(100 * wp), "flags": [x for x in us_s if x["bye"] or x["status"] in ("OUT", "INJURY_RESERVE", "DOUBTFUL", "SUSPENSION", "QUESTIONABLE")],
                   "usStarters": us_s, "oppStarters": op_s}
    sb = _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={wk}&dates={YR}")
    fa_raw = get(f"scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps({"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 400, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})})["players"]
    wpd = [x.get("waiverProcessDate") for x in fa_raw if x.get("waiverProcessDate")]
    dates = {"waivers": datetime.fromtimestamp(min(wpd) / 1000, timezone.utc).isoformat() if wpd else None,
             "kickoff": min((e["date"] for e in sb["events"]), default=None),
             "tradeDeadline": datetime.fromtimestamp(t["settings"]["tradeSettings"]["deadlineDate"] / 1000, timezone.utc).isoformat() if t["settings"].get("tradeSettings", {}).get("deadlineDate") else None}
    fas = defaultdict(list)
    for x in fa_raw:
        p = x["player"]; pos = POS.get(p["defaultPositionId"])
        if not pos: continue
        st = stats(p); pr = round(st.get((1, 1, wk), 0) or 0, 1)
        if bye.get(p.get("proTeamId")) == wk or pr <= 0: continue
        fas[pos].append({"name": p["fullName"], "nfl": ab.get(p.get("proTeamId"), "FA"), "proj": pr, "pct": round(p.get("ownership", {}).get("percentOwned", 0), 1), "status": x.get("status"), "inj": p.get("injuryStatus") or "ACTIVE"})
    free_agents = {k: sorted(v, key=lambda z: -z["proj"])[:4] for k, v in fas.items()}
    first, seventh, eighth = order[0], order[PO - 1], order[PO]
    remaining = defaultdict(list); h2h = {}
    for g_ in games:
        h_, a_ = g_["home"]["teamId"], g_["away"]["teamId"]
        if g_["winner"] == "UNDECIDED": remaining[h_].append(a_); remaining[a_].append(h_)
        if me in (h_, a_):
            o_ = a_ if h_ == me else h_
            h2h[o_] = f'Wk {g_["matchupPeriodId"]}' if g_["winner"] == "UNDECIDED" else ("W" if (g_["winner"] == "HOME") == (h_ == me) else "L") + f' Wk {g_["matchupPeriodId"]}'
    gb = lambda a_, b_: ((W[a_] - W[b_]) + (L[b_] - L[a_])) / 2
    race = [{"name": names[k], "seed": i + 1, "w": W[k], "l": L[k], "gb1": gb(first, k), "vs7": gb(k, eighth) if i < PO else -gb(seventh, k),
             "sos": round(statistics.mean(mu[o_] for o_ in remaining[k]), 1) if remaining[k] else None, "h2h": h2h.get(k, "—" if k == me else ""),
             "po": tby[k]["playoffPct"], "bye": tby[k]["byePct"]} for i, k in enumerate(order)]
    pa = defaultdict(list); pscored = defaultdict(list)
    for w_ in range(1, wk):
        s_ = _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w_}&dates={YR}")
        for e in s_["events"]:
            if not e["status"]["type"]["completed"]: continue
            a_, b_ = e["competitions"][0]["competitors"]
            pa[a_["team"]["abbreviation"]].append(int(b_["score"])); pa[b_["team"]["abbreviation"]].append(int(a_["score"]))
            pscored[a_["team"]["abbreviation"]].append(int(a_["score"])); pscored[b_["team"]["abbreviation"]].append(int(b_["score"]))
    ppa = {k: round(statistics.mean(v), 1) for k, v in pa.items()}; ppf = {k: round(statistics.mean(v), 1) for k, v in pscored.items()}
    def opp_v(code, d):
        c = code.lstrip("@"); return d.get(c) or d.get({"WSH": "WAS", "WAS": "WSH"}.get(c, c))
    roster_x = [{"name": p["name"], "pos": p["pos"], "nfl": p["nfl"], "slot": p.get("slot"), "bye": p.get("bye"),
                 "playoffs": [{"opp": o_, "pa": opp_v(o_, ppa) if o_ != "BYE" else None, "ps": opp_v(o_, ppf) if o_ != "BYE" else None} for o_ in (p.get("playoffs") or [])]}
                for p in players.values() if p.get("ours")]
    dump("extras", "current", {"week": wk, "builtAt": datetime.now(timezone.utc).isoformat(timespec="minutes"), "prev": prev, "matchup": matchup, "dates": dates,
         "freeAgents": free_agents, "race": race, "roster": roster_x, "leaguePA": round(statistics.mean(ppa.values()), 1) if ppa else None, "regWeeks": REG})
except Exception as _e:
    print("extras skipped:", _e)
print(f"week {wk}: {len(players)} players, {len(weekly)} score weeks -> {out}")
