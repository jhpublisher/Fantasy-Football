# Game scores for the Return Game store (Oct 8, Joe): final score, winner and loser for every completed NFL game.
# Usage: python3 add_scores.py <store_dir> <tools_dir>     writes <store_dir>/scores.json (create-only per game; a final score never changes)
# Source: ESPN NFL scoreboard, one call per week 1..current. Only FINAL games are stored.
# Checks (fail loudly, nothing written): both teams have a numeric score; winner flag agrees with the scores (ties: no winner);
#   an already-stored game must match exactly; for stored weeks, scores must equal the score in the locked ESPN game summary (raw archive)
#   and the game ids must equal the kickoff-coverage game ids; a stored week must have every game scored.
import json,os,sys,gzip,time,urllib.request
STORE,TD=(os.path.abspath(x) for x in sys.argv[1:3]);sys.path.insert(0,TD)
from rg_store import *
def get(u):
    for k in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except Exception:
            if k==2: raise
            time.sleep(2*(k+1))
def fail(msg): print(json.dumps({'ok':False,'error':msg}));sys.exit(1)
idx=load_index(STORE);S=idx.get('season',2026);have=sorted(int(w) for w in idx['weeks'])
SB="https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
cp=os.path.join(STORE,'current','ownership.json')
CUR=(json.load(open(cp)).get('currentWeek') if os.path.exists(cp) else None) or (max(have)+1 if have else 1)
path=os.path.join(STORE,'scores.json')
old=json.load(open(path))['games'] if os.path.exists(path) else {}
games=dict(old);new=0;problems=[]
for w in range(1,int(CUR)+1):
    try: ev=get(f"{SB}?seasontype=2&week={w}&dates={S}").get('events',[])
    except Exception as e: fail(f'scoreboard week {w} unreachable: {e}')
    for e in ev:
        if not e['status']['type']['completed']: continue
        c=e['competitions'][0]['competitors']
        if len(c)!=2: problems.append((w,e['id'],'competitors',len(c)));continue
        try: sc={x['homeAway']:(x['team']['abbreviation'],int(x['score']),x.get('winner')) for x in c}
        except Exception: problems.append((w,e['id'],'score not numeric'));continue
        if set(sc)!={'home','away'}: problems.append((w,e['id'],'home/away missing'));continue
        h,a=sc['home'],sc['away']
        win=h[0] if h[1]>a[1] else a[0] if a[1]>h[1] else None
        flagged=[x[0] for x in (h,a) if x[2]]
        if (win is None and flagged) or (win and flagged!=[win]): problems.append((w,e['id'],'winner flag disagrees with score',h,a));continue
        g={'week':w,'date':e['date'],'home':h[0],'away':a[0],'homeScore':h[1],'awayScore':a[1],'winner':win,'loser':(a[0] if win==h[0] else h[0]) if win else None,'tie':win is None}
        if e['id'] in old:
            if old[e['id']]!=g: problems.append((w,e['id'],'stored game differs from ESPN',old[e['id']],g))
            continue
        games[e['id']]=g;new+=1
# cross-checks against the locked weeks
for w in have:
    W=check_week_file(STORE,S,w,idx['weeks'][str(w)])
    ids={r['game_id'] for r in W['tables']['kickoff_coverage']}
    got={i for i,g in games.items() if g['week']==w}
    if ids!=got: problems.append((w,'game ids differ from kickoff coverage',sorted(ids^got)[:6]))
    raw=json.loads(gzip.open(os.path.join(STORE,W['rawArchive'])).read())
    for i,s in raw.items():
        if i not in games: continue
        cc={x['homeAway']:int(x['score']) for x in s['header']['competitions'][0]['competitors']}
        g=games[i]
        if cc.get('home')!=g['homeScore'] or cc.get('away')!=g['awayScore']: problems.append((w,i,'score differs from locked game summary',cc,(g['homeScore'],g['awayScore'])))
if problems: fail(f'{len(problems)} problem(s): {problems[:5]}')
if new or not os.path.exists(path):
    json.dump({'season':S,'source':'ESPN NFL scoreboard (final games only), checked against the locked ESPN game summaries','games':dict(sorted(games.items(),key=lambda kv:(kv[1]['week'],kv[0])))},open(path,'w'),indent=0)
print(json.dumps({'ok':True,'games':len(games),'added':new,'throughWeek':CUR}))
