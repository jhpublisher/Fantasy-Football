# Build returns.json (what the dashboard reads) from the stored weeks + current state. NO network: fill_rg.py runs offline.
# Usage: python3 assemble_rg.py <store_dir> <out_dir> <tools_dir>     (Oct 7 redesign; stored week files are only read)
import json,os,sys,csv,shutil,subprocess
STORE,OUT,TD=(os.path.abspath(x) for x in sys.argv[1:4]);sys.path.insert(0,TD)
from rg_store import *
os.makedirs(OUT,exist_ok=True);C=os.path.join(STORE,'current')
idx=load_index(STORE);S=idx.get('season',2026);weeks=sorted(int(w) for w in idx['weeks'])
WK={w:check_week_file(STORE,S,w,idx['weeks'][str(w)]) for w in weeks}
OW=json.load(open(os.path.join(C,'ownership.json'),encoding='utf-8'));own=OW['players']
def owner(i): return own.get(str(i),['not in ESPN fantasy','Not in ESPN fantasy'])
for t in TABLES:
    rows=[dict(r) for w in weeks for r in WK[w]['tables'][t]]
    if t in ('kick_returns','punt_returns'):
        for r in rows: r['fantasy_pos'],r['owner']=owner(r['espn_id'])
    cols=list(rows[0].keys()) if rows else []
    with open(os.path.join(OUT,t+'.csv'),'w',newline='',encoding='utf-8') as f: w_=csv.DictWriter(f,cols);w_.writeheader();w_.writerows(rows)
last=WK[weeks[-1]]
M={'season':S,'currentWeek':OW['currentWeek'],'regSeasonWeeks':OW['regSeasonWeeks'],'weeks':weeks,'byes':{str(w):WK[w]['byes'] for w in weeks},
   'scoring':last['scoring'],'gamesPerWeek':{str(w):WK[w]['games'] for w in weeks},
   'fairCatches':{'source':last['fairCatches'].get('source'),'unmatched':sum((WK[w]['fairCatches'].get('unmatched',[]) for w in weeks),[]),'gamesWithoutPlayByPlay':sum((WK[w]['fairCatches'].get('gamesWithoutPlayByPlay',[]) for w in weeks),[])}}
json.dump(M,open(os.path.join(OUT,'box_meta.json'),'w'),indent=1)
for f in ('espn_depth.json','team_sites.json'): shutil.copy(os.path.join(C,f),os.path.join(OUT,f))
r=subprocess.run([sys.executable,os.path.join(TD,'fill_rg.py')],cwd=OUT,env={**os.environ,'RG_CURRENT':C},capture_output=True,text=True)
print(r.stdout[-800:],r.stderr[-800:])
if r.returncode: sys.exit(f'FAIL: fill_rg.py exit {r.returncode}')
R=json.load(open(os.path.join(OUT,'returns.json'),encoding='utf-8'))
R['store']={'weeks':weeks,'sha256':{str(w):idx['weeks'][str(w)]['sha256'] for w in weeks}}
# injuries (official) + injury checker, compact for the page
POSK={'WR','RB','TE','FB','CB','S','DB'}
INJ={}
ii=os.path.join(STORE,'injuries','index.json')
if os.path.exists(ii):
    for w,e in json.load(open(ii))['weeks'].items():
        J=json.load(open(os.path.join(STORE,'injuries',e['file']),encoding='utf-8'));INJ[w]={}
        for t in set(J['report'])|set(J['inactives']):
            INJ[w][t]={'out':[[p['name'],p['pos']] for p in J['inactives'].get(t,{}).get('did_not_play',[]) if p['pos'] in POSK],
                       'report':[[r['player'],r['pos'],r['injury'],r['practice'],r['game_status']] for r in J['report'].get(t,[]) if r['pos'] in POSK and r['game_status']]}
cr=os.path.join(C,'injury_report.json');CUR={}
if os.path.exists(cr):
    J=json.load(open(cr,encoding='utf-8'));CUR={'week':J['week'],'asOf':J.get('_asOf'),'teams':{t:[[r['player'],r['pos'],r['injury'],r['practice'],r['game_status']] for r in rows if r['pos'] in POSK] for t,rows in J['report'].items()}}
R['injuries']={'source':'NFL.com official injury reports + game-day inactives','weeks':INJ,'current':CUR}
r2=subprocess.run([sys.executable,os.path.join(TD,'rg_checker.py'),STORE,'--json',os.path.join(OUT,'checker.json')],capture_output=True,text=True)
if r2.returncode: sys.exit(f'FAIL: rg_checker.py {r2.stderr[-300:]}')
R['checker']=json.load(open(os.path.join(OUT,'checker.json')))
R['currentState']=json.load(open(os.path.join(C,'status.json'))) if os.path.exists(os.path.join(C,'status.json')) else {}
json.dump(R,open(os.path.join(OUT,'returns.json'),'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
print('assembled weeks',weeks,'bytes',os.path.getsize(os.path.join(OUT,'returns.json')))
