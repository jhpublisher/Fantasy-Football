#!/usr/bin/env python3
"""Build the NFL schedule board data (Rich). Usage: python3 schedule_pull.py <out.json> [--prev <old.json>]
Writes one JSON: teams, games, tv, mine (our players by NFL team), opp (each regular-season week's opponent roster), asOf, defaultWeek.
Sources: ESPN fantasy API (proTeamSchedules_wl, mTeam, mMatchup, mRoster) and the ESPN site scoreboard (TV networks).
Exit 1 if counts are wrong (272 games, 32 teams, one bye each, our roster empty). A week with no TV listing keeps the previous file's listing for the same game, else is left empty (shown as 'TV to be announced')."""
import json, sys, urllib.request, datetime
LG=293318; ME=31
B=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/{LG}"
POS={1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=120).read())
def fail(m): print("FAIL:",m); sys.exit(1)
out=sys.argv[1]; prev=None
if "--prev" in sys.argv:
    try: prev=json.load(open(sys.argv[sys.argv.index("--prev")+1]))
    except Exception: prev=None
st=get(B+"?view=mStatus")["status"]; cur=st["currentMatchupPeriod"]
pro=get("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026?view=proTeamSchedules_wl")["settings"]["proTeams"]
teams={}; games=[]
for t in pro:
    if t["id"]==0: continue
    bye=t.get("byeWeek") or 0
    teams[str(t["id"])]={"a":t["abbrev"].upper(),"n":f'{t["location"]} {t["name"]}',"b":bye}
    for w,gl in (t.get("proGamesByScoringPeriod") or {}).items():
        for g in gl:
            if g["awayProTeamId"]==t["id"]: games.append([int(w),g["awayProTeamId"],g["homeProTeamId"],int(g["date"])])
games.sort(key=lambda g:(g[0],g[3],g[1]))
if len(teams)!=32: fail(f"{len(teams)} teams")
if len(games)!=272: fail(f"{len(games)} games")
for tid,t in teams.items():
    n=sum(1 for g in games if int(tid) in (g[1],g[2]))
    if n!=17 or not t["b"]: fail(f"team {tid}: {n} games, bye {t['b']}")
# TV
name2id={t["n"]:int(i) for i,t in teams.items()}
old={}
if prev:
    pg=prev.get("games",[])
    for i,g in enumerate(pg):
        if i<len(prev.get("tv",[])): old[(g[0],g[1],g[2])]=prev["tv"][i]
tvmap={}; tvfail=[]
for w in range(1,19):
    try:
        ev=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w}&dates=2026")["events"]
    except Exception as e:
        tvfail.append(w); continue
    for e in ev:
        c=e["competitions"][0]; names=[]
        for b in c.get("broadcasts") or []: names+=b.get("names",[])
        if not names:
            for b in c.get("geoBroadcasts") or []:
                if (b.get("market") or {}).get("type")=="National": names.append(b["media"]["shortName"])
        away=home=None
        for k in c["competitors"]:
            tid=name2id.get(k["team"]["displayName"])
            if k["homeAway"]=="home": home=tid
            else: away=tid
        if away and home: tvmap[(w,away,home)]=list(dict.fromkeys(names))
NORM={'NFL Net':'NFL Network'}
tvmap={k:[NORM.get(n,n) for n in v] for k,v in tvmap.items()}
tv=[tvmap.get((g[0],g[1],g[2])) or old.get((g[0],g[1],g[2])) or [] for g in games]
# rosters
def roster(entries):
    pl=[]
    for e in entries:
        p=e["playerPoolEntry"]["player"]; slot=e["lineupSlotId"]
        pl.append({"n":p["fullName"],"p":POS.get(p["defaultPositionId"],"?"),"s":"IR" if slot==21 else "B" if slot==20 else "S","t":p.get("proTeamId")})
    return pl
def team_rosters(week=None):
    u=B+"?view=mRoster"+(f"&scoringPeriodId={week}" if week else "")
    return {t["id"]:roster(t["roster"]["entries"]) for t in get(u)["teams"]}
names={t["id"]:(t.get("name") or f'{t.get("location","")} {t.get("nickname","")}').strip() for t in get(B+"?view=mTeam")["teams"]}
cr=team_rosters()
mine={}
for p in cr[ME]:
    mine.setdefault(str(p["t"]),[]).append({"n":p["n"],"p":p["p"],"s":p["s"]})
if not mine: fail("our roster empty")
sched=get(B+"?view=mMatchup")["schedule"]
oppw={}
for m in sched:
    h,a=m["home"]["teamId"],m["away"]["teamId"]
    if ME in (h,a): oppw[m["matchupPeriodId"]]=a if h==ME else h
opp={}
wk_cache={}
for w,o in sorted(oppw.items()):
    if w<cur:
        if w not in wk_cache: wk_cache[w]=team_rosters(w)
        pl,src=wk_cache[w][o],"week roster"
    else: pl,src=cr[o],"current roster"
    opp[str(w)]={"team":names[o],"src":src,"pl":[x for x in pl if x["t"]]}
if not opp: fail("no opponents found")
d=datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
res={"teams":teams,"games":games,"tv":tv,"mine":mine,"opp":opp,"asOf":d.strftime("%b %-d, %Y"),"defaultWeek":cur}
json.dump(res,open(out,"w"),separators=(",",":"),ensure_ascii=False)
print(f"ok: {len(games)} games, tv listed for {sum(1 for x in tv if x)}, weeks without scoreboard {tvfail}, our players {sum(len(v) for v in mine.values())}, opp weeks {len(opp)}")
