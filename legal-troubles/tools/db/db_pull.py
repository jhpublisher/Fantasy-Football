#!/usr/bin/env python3
"""Freeze one completed fantasy week into data/db/weeks/wNN (create-only).
Usage: python3 db_pull.py <week> [--dry]   Run from legal-troubles/. Exit 1 on any failure.
Pulls roster, boxscore, matchups, player pool, per-player actuals/projections; verifies that every team's
starter points equal ESPN's team score; refuses to overwrite an existing file; refreshes data/db/league/ (overwritten).
"""
import json, os, sys, hashlib, urllib.request
B="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/293318"
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","data","db")
def get(url, filt=None):
    h={"User-Agent":"Mozilla/5.0"}
    if filt: h["X-Fantasy-Filter"]=json.dumps(filt)
    return urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=180).read()
def fail(m): print("FAIL:",m); sys.exit(1)
w=int(sys.argv[1]); dry="--dry" in sys.argv
cur=json.loads(get(B+"?view=mStatus"))["status"]["currentMatchupPeriod"]
if w>=cur: fail(f"week {w} is not complete (current week {cur})")
d=os.path.join(ROOT,"weeks",f"w{w:02d}")
if os.path.exists(os.path.join(d,"boxscore.json")) and not dry: fail(f"week {w} already frozen")
rost=get(f"{B}?view=mRoster&scoringPeriodId={w}"); box=get(f"{B}?view=mBoxscore&scoringPeriodId={w}")
mat=get(f"{B}?view=mMatchup&scoringPeriodId={w}")
# Pool pulled at the CURRENT period so completed weeks' stats are included (pulling at period w omits them).
flt=lambda: {"players":{"limit":4000,"sortPercOwned":{"sortPriority":1,"sortAsc":False},"filterStatsForTopScoringPeriodIds":{"value":w,"additionalValue":["002026","102026",f"112026{w}"]}}}
pool=get(f"{B}?view=kona_player_info&scoringPeriodId={cur}",flt())
pj=json.loads(pool)["players"]
if len(pj)<1000: fail(f"pool only {len(pj)} players")
players={}
for x in pj:
    pl=x["player"]; row={"name":pl["fullName"],"pos":pl.get("defaultPositionId"),"proTeam":pl.get("proTeamId")}
    for s in pl.get("stats",[]):
        if s["statSplitTypeId"]==1 and s["scoringPeriodId"]==w:
            row["actual" if s["statSourceId"]==0 else "proj"]=round(s.get("appliedTotal",0),2)
    players[str(x["id"])]=row
nact=sum("actual" in v for v in players.values())
if nact<500: fail(f"only {nact} players with week-{w} actuals")
bj=json.loads(box); n=bad=0
for m in bj["schedule"]:
    if m["matchupPeriodId"]!=w: continue
    for side in("home","away"):
        t=m[side]; n+=1
        s=sum(players[str(e["playerId"])].get("actual",0) for e in t["rosterForCurrentScoringPeriod"]["entries"] if e["lineupSlotId"] not in(20,21))
        if abs(s-t["totalPoints"])>0.05: bad+=1; print("mismatch team",t["teamId"],round(s,2),t["totalPoints"])
if n!=14 or bad: fail(f"reconcile: {n} team-games, {bad} mismatches")
print(f"week {w}: reconciled {n} team-games to ESPN, {nact} actuals, pool {len(pj)}")
if dry: sys.exit(0)
os.makedirs(d); man={}
for name,data in (("roster.json",rost),("boxscore.json",box),("matchups_all.json",mat),("pool.json",pool)):
    open(os.path.join(d,name),"wb").write(data); man[name]=hashlib.sha256(data).hexdigest()
pw=json.dumps({"week":w,"players":players},separators=(",",":")).encode()
open(os.path.join(d,"players_week.json"),"wb").write(pw); man["players_week.json"]=hashlib.sha256(pw).hexdigest()
json.dump({"week":w,"files":man},open(os.path.join(d,"SHA256.json"),"w"),indent=1)
L=os.path.join(ROOT,"league"); os.makedirs(L,exist_ok=True)
for v in("mSettings","mTeam","mStandings","mTransactions2","mDraftDetail","mStatus","mNav","mPositionalRatings"):
    open(os.path.join(L,v+".json"),"wb").write(get(f"{B}?view={v}"))
open(os.path.join(L,"nfl_schedule.json"),"wb").write(get("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026?view=proTeamSchedules_wl"))
print("frozen",d)
