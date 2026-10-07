# Punt coverage per team per week (Joe, Oct 7): punts made, punt yards, touchbacks, inside 20, plus punt returns allowed (what the other team ran back).
# Punting-team view. Source: ESPN game summary box score (boxscore.players[].statistics: 'punting' for the punter's team, 'puntReturns' for the receiving team).
# Writes punting_doc.json = dashboard db returns/punting. Cross-check: punt returns/yards allowed must equal the receiving team's team_pr / team_pr_yds in returns.json (0 mismatches over weeks 1-4). Fails loudly on any mismatch.
# Usage: python3 punting.py returns.json punting_doc.json
# Zero-punt games are real (TB wk1 and CHI wk4: no punt plays in play-by-play); ESPN omits the totals, so they are read as 0.
import json,urllib.request,time,sys,datetime
def get(u):
    for k in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except Exception:
            if k==2: raise
            time.sleep(2*(k+1))
R=json.load(open(sys.argv[1]));out={};bad=[]
f=lambda x,k:int(float(x.get(k,0) or 0))
for w in R['weeks']:
    sb=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={w}&seasontype=2&dates={R.get('season',2026)}")
    for e in sb['events']:
        if e['status']['type']['name']!='STATUS_FINAL': continue
        d=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={e['id']}");P={}
        for t in d['boxscore']['players']:
            P[t['team']['abbreviation']]={c['name']:(dict(zip(c['keys'],c['totals'])) if c.get('totals') else {}) for c in t['statistics'] if c['name'] in('punting','puntReturns')}
        a,b=list(P)
        for x,y in((a,b),(b,a)):
            pu,pr=P[x].get('punting',{}),P[y].get('puntReturns',{})
            g={'game':e['id'],'opp':y,'punts':f(pu,'punts'),'punt_yds':f(pu,'puntYards'),'tb':f(pu,'touchbacks'),'in20':f(pu,'puntsInside20'),'long':f(pu,'longPunt'),'ret':f(pr,'puntReturns'),'ret_yds':f(pr,'puntReturnYards'),'ret_td':f(pr,'puntReturnTouchdowns')}
            h=R['teams'][y]['pr']['weeks'].get(str(w))
            if not h or h.get('bye') or h['team_pr']!=g['ret'] or h['team_pr_yds']!=g['ret_yds']: bad.append((x,w,g['ret'],g['ret_yds'],h and h.get('team_pr'),h and h.get('team_pr_yds')))
            out.setdefault(x,{})[str(w)]=g
for t in R['teams']:
    n=sum(1 for w in R['weeks'] if not R['kickoffs'][t].get(str(w),{}).get('bye'))
    if len(out.get(t,{}))!=n: bad.append((t,'games',len(out.get(t,{})),n))
if bad: sys.exit(f"FAIL: {bad[:10]}")
json.dump({'builtAt':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),'weeks':R['weeks'],'source':'ESPN box score (punting, puntReturns) per game; cross-checked against returns.json punt returns allowed','teams':out},open(sys.argv[2],'w'))
print('OK',sum(len(v) for v in out.values()),'team-games',sum(g['punts'] for v in out.values() for g in v.values()),'punts')
