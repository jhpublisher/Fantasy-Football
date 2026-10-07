# Kick- AND punt-return box scores for every completed NFL week, in OUR league's scoring.
# Outputs: kick_returns.csv + team_game_kick_totals.csv (unchanged shape), punt_returns.csv + team_game_punt_totals.csv, box_meta.json.
# Punt fair catches come from play-by-play ("fair catch by X.Name" on punt plays); ESPN's box has no fair-catch column.
# Weeks come from the league's current scoring period + the NFL scoreboard (never hard-coded).
# Stats are read by key/label, not by column position. Fails loudly if a week is incomplete.
import json,urllib.request,csv,sys,concurrent.futures as cf
def get(u,h=None,tries=3):   # retry transient errors, then raise
    import time
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0",**(h or {})}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
LG=293318;SEASON=2026;B=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LG}"
SB="https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
POS={1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
# 1) league: current week + scoring for kick returns (statId 114 = KR yards, 101 = KR TD)
L=get(f"{B}?view=mSettings&view=mStatus&view=mTeam")
CUR=L.get("scoringPeriodId") or L["status"]["latestScoringPeriod"]
REG=L["settings"]["scheduleSettings"].get("matchupPeriodCount",14)
SC={x["statId"]:x["points"] for x in L["settings"]["scoringSettings"]["scoringItems"]}
if 114 not in SC or 101 not in SC: sys.exit(f"FAIL: league scoring has no kick-return items (114/101): {sorted(SC)[:20]}")
if 115 not in SC or 102 not in SC: sys.exit(f"FAIL: league scoring has no punt-return items (115/102): {sorted(SC)[:20]}")
PER_YD,PER_TD=SC[114],SC[101]
PR_YD,PR_TD=SC[115],SC[102]
names={x["id"]:(x.get("name") or "").strip() for x in L["teams"]}
ALL_TEAMS=None
# 2) weeks: every week before the current one must be complete; the current week counts only when all its games are final
games=[];weeks=[];byes={};problems=[]
for w in range(1,CUR+1):
    sb=get(f"{SB}?seasontype=2&week={w}&dates={SEASON}")
    ev=sb["events"];done=[e for e in ev if e["status"]["type"]["completed"]]
    playing={c["team"]["abbreviation"] for e in ev for c in e["competitions"][0]["competitors"]}
    if ALL_TEAMS is None:
        ALL_TEAMS=sorted(t["team"]["abbreviation"] for t in get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"])
    if len(done)<len(ev):
        if w<CUR: problems.append(f"Week {w}: {len(done)} of {len(ev)} scheduled games final")
        else: print(f"Week {w} in progress ({len(done)}/{len(ev)} final): left out until all games are final")
        continue
    weeks.append(w);byes[w]=[t for t in ALL_TEAMS if t not in playing]
    games+=[(w,e["id"],e["date"]) for e in done]
if problems: sys.exit("FAIL: "+"; ".join(problems))
EXPECT={w:sum(1 for g in games if g[0]==w) for w in weeks}
KEYS=("kickReturns","kickReturnYards","longKickReturn","kickReturnTouchdowns")
def stat(cat,a,key,label):
    ks=cat.get("keys") or [];ls=cat.get("labels") or []
    i=ks.index(key) if key in ks else (ls.index(label) if label in ls else None)
    if i is None: raise ValueError(f"{cat.get('name')} has no {key}/{label}: keys={ks} labels={ls}")
    v=a["stats"][i];return int(float(v)) if v not in ("","--") else 0
# team rosters: map play-by-play "D.Duvernay" to a full name + ESPN id (initial + normalized last name, unique per team)
import re,unicodedata
def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=re.sub(r"[.'’`,-]",' ',s);s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b',' ',s);return re.sub(r'[^a-z]','',s)
def abbr_key(first,last):return (first[:1].lower(),norm(last))
TID={t["team"]["abbreviation"]:t["team"]["id"] for t in get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]}
ROST={}
def roster(ab):
    try: ro=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{TID[ab]}/roster")
    except Exception as e: return ab,None
    m={}
    for grp in ro.get("athletes",[]):
        for a in grp.get("items",[]):
            k=abbr_key(a.get("firstName") or a["fullName"],a.get("lastName") or a["fullName"].split()[-1]);m.setdefault(k,[]).append((a["fullName"],int(a["id"])))
    return ab,m
with cf.ThreadPoolExecutor(8) as ex:
    for ab,m in ex.map(roster,list(TID)): ROST[ab]=m
FCRX=re.compile(r"fair catch by ([A-Z][A-Za-z']*)\.\s?((?:St\.\s?)?[A-Z][A-Za-z'\-]+)")
def game(g):
    w,gid,dt=g;d=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={gid}")
    comp=d["header"]["competitions"][0]["competitors"];ab={c["team"]["id"]:c["team"]["abbreviation"] for c in comp}
    rows=[];tots=[];prow=[];ptots=[]
    idab={c["team"]["id"]:c["team"]["abbreviation"] for c in comp}
    # fair catches by receiving team (punting team = play start.team, receiver = the other team); None = no play-by-play
    drives=(d.get("drives") or {}).get("previous")
    fc={a:0 for a in ab.values()} if drives else None;fcp={a:{} for a in ab.values()};fc_unmatched=[]
    BOXP={}   # every athlete in this game's box, by team, keyed like the play-by-play abbreviation
    for tm in d["boxscore"]["players"]:
        for c in tm["statistics"]:
            for a in c.get("athletes",[]):
                n=a["athlete"]["displayName"];p=n.split();k=abbr_key(p[0]," ".join(p[1:]) or n)
                L=BOXP.setdefault(tm["team"]["abbreviation"],{}).setdefault(k,[])
                if (n,int(a["athlete"]["id"])) not in L: L.append((n,int(a["athlete"]["id"])))
    for dr in drives or []:
        for pl in dr.get("plays",[]):
            tx=pl.get("text") or "";ty=((pl.get("type") or {}).get("text") or "").lower()
            if "punt" not in ty or "fair catch by" not in tx.lower() or "no play" in tx.lower(): continue
            kick=idab.get(((pl.get("start") or {}).get("team") or {}).get("id")) or idab.get((dr.get("team") or {}).get("id"))
            rec=[a for a in ab.values() if a!=kick]
            if not kick or len(rec)!=1: fc_unmatched.append(f"game {gid}: no punting team for: {tx[:80]}");continue
            rec=rec[0];fc[rec]+=1
            m=FCRX.search(tx);k=abbr_key(m.group(1),m.group(2)) if m else None
            hits=(BOXP.get(rec) or {}).get(k) or (ROST.get(rec) or {}).get(k) if k else None   # this game's box first, then today's roster
            if hits and len(hits)==1: n,i=hits[0];x=fcp[rec].setdefault(i,{"name":n,"fc":0});x["fc"]+=1
            else: fc_unmatched.append(f"{rec} wk {w} game {gid}: fair catch not matched to one player ({tx[-90:]})");fcp[rec].setdefault(None,{"name":None,"fc":0})["fc"]+=1
    for tm in d["boxscore"]["players"]:
        t=tm["team"]["abbreviation"];opp=[a for a in ab.values() if a!=t][0]
        cat=next((c for c in tm["statistics"] if c["name"]=="kickReturns"),None)
        ath=cat["athletes"] if cat else []
        P=[(a,stat(cat,a,"kickReturns","NO"),stat(cat,a,"kickReturnYards","YDS"),stat(cat,a,"longKickReturn","LONG"),stat(cat,a,"kickReturnTouchdowns","TD")) for a in ath]
        tot_n=sum(p[1] for p in P);tot_y=sum(p[2] for p in P)
        ct=(cat.get("totals") if cat else None) or []
        ci=lambda key,lab:(cat["keys"].index(key) if key in (cat.get("keys") or []) else cat["labels"].index(lab))
        tots.append({"week":w,"game_id":gid,"date":dt[:10],"team":t,"opp":opp,"team_kr":tot_n,"team_kr_yds":tot_y,
                     "espn_total_kr":(ct[ci("kickReturns","NO")] if ct else "0"),"espn_total_yds":(ct[ci("kickReturnYards","YDS")] if ct else "0")})
        for a,n,y,lg,td in P:
            rows.append({"week":w,"game_id":gid,"date":dt[:10],"team":t,"opp":opp,"player":a["athlete"]["displayName"],"espn_id":int(a["athlete"]["id"]),"kr":n,"kr_yds":y,"long":lg,"td":td,"team_kr":tot_n})
        # punt returns (same rules: read by key/label; no block = 0 returns, the team-game is kept)
        pc=next((c for c in tm["statistics"] if c["name"]=="puntReturns"),None)
        Q=[(a,stat(pc,a,"puntReturns","NO"),stat(pc,a,"puntReturnYards","YDS"),stat(pc,a,"longPuntReturn","LONG"),stat(pc,a,"puntReturnTouchdowns","TD")) for a in (pc["athletes"] if pc else [])]
        pn=sum(q[1] for q in Q);py=sum(q[2] for q in Q);pt=(pc.get("totals") if pc else None) or []
        pi=lambda key,lab:(pc["keys"].index(key) if key in (pc.get("keys") or []) else pc["labels"].index(lab))
        tfc=fc[t] if fc is not None else None
        ptots.append({"week":w,"game_id":gid,"date":dt[:10],"team":t,"opp":opp,"team_pr":pn,"team_pr_yds":py,"team_pr_td":sum(q[4] for q in Q),
                      "espn_total_pr":(pt[pi("puntReturns","NO")] if pt else "0"),"espn_total_yds":(pt[pi("puntReturnYards","YDS")] if pt else "0"),
                      "team_fc":("" if tfc is None else tfc)})
        seen=set()
        for a,n,y,lg,td in Q:
            i=int(a["athlete"]["id"]);seen.add(i);f=(fcp[t].get(i) or {}).get("fc",0) if fc is not None else ""
            prow.append({"week":w,"game_id":gid,"date":dt[:10],"team":t,"opp":opp,"player":a["athlete"]["displayName"],"espn_id":i,"pr":n,"pr_yds":y,"long":lg,"td":td,"fc":f,"team_pr":pn})
        if fc is not None:   # fair-catch-only returners (no return in the box) still count: they held the job
            for i,x in fcp[t].items():
                if i is not None and i not in seen: prow.append({"week":w,"game_id":gid,"date":dt[:10],"team":t,"opp":opp,"player":x["name"],"espn_id":i,"pr":0,"pr_yds":0,"long":0,"td":0,"fc":x["fc"],"team_pr":pn})
    if len(tots)!=2: raise ValueError(f"game {gid}: {len(tots)} team boxes, expected 2")
    for r in rows: r["share"]=round(r["kr"]/r["team_kr"],3) if r["team_kr"] else 0; r["fpts"]=round(r["kr_yds"]*PER_YD+PER_TD*r["td"],1)
    for r in prow: r["share"]=round(r["pr"]/r["team_pr"],3) if r["team_pr"] else 0; r["fpts"]=round(r["pr_yds"]*PR_YD+PR_TD*r["td"],1)
    return rows,tots,prow,ptots,fc_unmatched,(fc is None)
R=[];TT=[];PR=[];PT=[];FCW=[];NOPBP=[]
with cf.ThreadPoolExecutor(8) as ex:
    for (rows,tots,prow,ptots,fcu,nopbp),g in zip(ex.map(game,games),games): R+=rows;TT+=tots;PR+=prow;PT+=ptots;FCW+=fcu;NOPBP+=[g[1]] if nopbp else []
def fant(ids):
    out={}
    for i in range(0,len(ids),50):
        for p in get(f"{B}?view=kona_player_info&scoringPeriodId={CUR}",{"X-Fantasy-Filter":json.dumps({"players":{"filterIds":{"value":ids[i:i+50]}}})})["players"]:
            out[p["player"]["id"]]=(POS.get(p["player"]["defaultPositionId"],"Other"),names.get(p.get("onTeamId",0),"Free agent"))
    return out
F=fant(sorted({r["espn_id"] for r in R+PR}))
for r in R+PR: r["fantasy_pos"],r["owner"]=F.get(r["espn_id"],("not in ESPN fantasy","Not in ESPN fantasy"))
R.sort(key=lambda r:(r["week"],r["team"],-r["kr"]));TT.sort(key=lambda r:(r["week"],r["team"]))
PR.sort(key=lambda r:(r["week"],r["team"],-r["pr"],-(r["fc"] or 0)));PT.sort(key=lambda r:(r["week"],r["team"]))
for fn,data in (("kick_returns.csv",R),("team_game_kick_totals.csv",TT),("punt_returns.csv",PR),("team_game_punt_totals.csv",PT)):
    with open(fn,"w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
json.dump({"currentWeek":CUR,"regSeasonWeeks":REG,"weeks":weeks,"byes":byes,"scoring":{"krYd":PER_YD,"krTd":PER_TD,"prYd":PR_YD,"prTd":PR_TD},"gamesPerWeek":EXPECT,
           "fairCatches":{"source":"ESPN play-by-play (punt plays, 'fair catch by')","gamesWithoutPlayByPlay":NOPBP,"unmatched":FCW}},open("box_meta.json","w"),indent=1)
# checks: every scheduled game has two team boxes; ESPN totals match our sums; 32 teams each week (playing + bye)
bad=[t for t in TT if str(t["team_kr"])!=str(t["espn_total_kr"]) or str(t["team_kr_yds"])!=str(t["espn_total_yds"])]
bad+=[t for t in PT if str(t["team_pr"])!=str(t["espn_total_pr"]) or str(t["team_pr_yds"])!=str(t["espn_total_yds"])]
for w in weeks:
    n=sum(1 for t in TT if t["week"]==w)
    assert n==2*EXPECT[w],f"Week {w}: {n} team boxes for {EXPECT[w]} games"
    assert sum(1 for t in PT if t["week"]==w)==n,f"Week {w}: punt team boxes != kick team boxes"
    assert n+len(byes[w])==len(ALL_TEAMS)==32,f"Week {w}: {n} playing + {len(byes[w])} bye != 32"
if bad: sys.exit(f"FAIL: ESPN totals disagree with player sums: {bad[:5]}")
print(f"current week {CUR}; weeks {weeks}; games/week {EXPECT}; byes {({w:b for w,b in byes.items() if b})}; scoring {PER_YD}/yd {PER_TD}/TD; {len(R)} KR player rows, {len(PR)} PR player rows OK; fair catches: {sum(int(t['team_fc'] or 0) for t in PT)} ({len(FCW)} not matched to a player, {len(NOPBP)} games without play-by-play)")
for m in FCW[:10]: print("WARN",m)
