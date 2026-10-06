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
print(f"week {wk}: {len(players)} players, {len(weekly)} score weeks -> {out}")
