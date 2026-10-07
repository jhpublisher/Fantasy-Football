# Verify ONE week against ESPN sources we did not build it from (Oct 7 redesign). No timing window: works any day.
# Usage: python3 verify_week.py <dir> <week>   (dir has that week's 5 CSVs from box.py + kickoffs.py)
# A) ESPN per-game team stats (core API competitor statistics), every team-game: kick returns + yds, punt returns + yds,
#    punt fair catches, kickoffs, touchbacks.
# B) ESPN fantasy weekly player stats for every returner ESPN fantasy knows: 114 KR yds, 101 KR TD, 115 PR yds, 102 PR TD.
#    (Returners ESPN fantasy doesn't carry, e.g. defensive backs, are covered by the team totals in A.)
# Approved ESPN-side inconsistencies: env RG_EXCEPTIONS=<exceptions.json> (see below).
# Writes verify_report.json; exit 1 on any mismatch or missing source.
import json,urllib.request,csv,sys,os,time,collections,concurrent.futures as cf
def get(u,h=None,tries=3):
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u.replace('http://','https://'),headers={"User-Agent":"Mozilla/5.0",**(h or {})}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
D,W=sys.argv[1],int(sys.argv[2])
rd=lambda f:[r for r in csv.DictReader(open(os.path.join(D,f),newline='')) if int(r['week'])==W]
KT,PT,KO,KR,PR=rd('team_game_kick_totals.csv'),rd('team_game_punt_totals.csv'),rd('kickoff_coverage.csv'),rd('kick_returns.csv'),rd('punt_returns.csv')
fails=[];checked=collections.Counter();explained=[]
# exceptions.json (next to the weeks/ folder): ESPN-side inconsistencies a person investigated and approved, e.g.
# {"week":1,"game_id":"401872924","team":"TEN","field":"kickoffs","ours":3,"espn":2,"reason":"..."}. Anything else that differs fails.
EXC=json.load(open(os.environ['RG_EXCEPTIONS'])) if os.environ.get('RG_EXCEPTIONS') and os.path.exists(os.environ['RG_EXCEPTIONS']) else []
def excused(gid,t,f,o,e): 
    for x in EXC:
        if (x['week'],str(x['game_id']),x['team'],x['field'],x['ours'],x['espn'])==(W,str(gid),t,f,o,e): explained.append(x);return True
    return False
TID={t['team']['abbreviation']:t['team']['id'] for t in get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]}
ours={}
for r in KT: ours.setdefault((r['game_id'],r['team']),{}).update(kickReturns=int(r['team_kr']),kickReturnYards=int(r['team_kr_yds']))
for r in PT: ours.setdefault((r['game_id'],r['team']),{}).update(puntReturns=int(r['team_pr']),puntReturnYards=int(r['team_pr_yds']),**({'puntReturnFairCatches':int(r['team_fc'])} if r['team_fc']!='' else {}))
for r in KO: ours.setdefault((r['game_id'],r['team']),{}).update(kickoffs=int(r['kickoffs']),touchbacks=int(r['touchback']))
SRC={'kickReturns':'returning','kickReturnYards':'returning','puntReturns':'returning','puntReturnYards':'returning','puntReturnFairCatches':'returning','kickoffs':'kicking','touchbacks':'kicking'}
def team_game(k):
    gid,t=k
    try: s=get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{gid}/competitions/{gid}/competitors/{TID[t]}/statistics")
    except Exception as e: return k,None,str(e)
    return k,{c['name']:{x['name']:x.get('value') for x in c['stats']} for c in s['splits']['categories']},None
with cf.ThreadPoolExecutor(8) as ex:
    for k,S,err in ex.map(team_game,sorted(ours)):
        if err: fails.append(f"{k}: ESPN per-game stats unavailable ({err[:80]})");continue
        for f,v in ours[k].items():
            e=S.get(SRC[f],{}).get(f)
            if e is None: fails.append(f"{k} {f}: ESPN has no value");continue
            checked['team-game values']+=1
            if int(round(e))!=v and not excused(k[0],k[1],f,v,int(round(e))): fails.append(f"wk {W} game {k[0]} {k[1]} {f}: ours {v} vs ESPN {int(round(e))}")
if len(ours)!=len(KT): fails.append(f"team-games: {len(ours)} keys vs {len(KT)} kick rows")
P=collections.defaultdict(collections.Counter)
for r in KR: P[int(r['espn_id'])]['114']+=int(r['kr_yds']);P[int(r['espn_id'])]['101']+=int(r['td'])
for r in PR: P[int(r['espn_id'])]['115']+=int(r['pr_yds']);P[int(r['espn_id'])]['102']+=int(r['td'])
B="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/293318";ids=sorted(P);known=0
for i in range(0,len(ids),50):
    for p in get(f"{B}?view=kona_player_info&scoringPeriodId={W}",{"X-Fantasy-Filter":json.dumps({"players":{"filterIds":{"value":ids[i:i+50]}}})})["players"]:
        pl=p['player'];known+=1
        st=next((s['stats'] for s in pl.get('stats',[]) if s.get('scoringPeriodId')==W and s.get('statSourceId')==0 and s.get('statSplitTypeId')==1),{})
        for k,v in P[pl['id']].items():
            checked['player values']+=1;e=int(round(st.get(k,0)))
            if e!=v: fails.append(f"wk {W} {pl.get('fullName')} stat {k}: ours {v} vs ESPN fantasy {e}")
rep={'week':W,'ok':not fails,'checked':dict(checked),'teamGames':len(ours),'returners':len(ids),'returnersInEspnFantasy':known,'fails':fails,'explained':explained,'at':time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime())}
json.dump(rep,open(os.path.join(D,'verify_report.json'),'w'),indent=1)
print(json.dumps({k:rep[k] for k in ('week','ok','checked','teamGames','returners','returnersInEspnFantasy')}));[print('FAIL',f) for f in fails[:30]]
sys.exit(0 if rep['ok'] else 1)
