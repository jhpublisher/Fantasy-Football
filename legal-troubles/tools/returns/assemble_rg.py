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
R['currentState']=json.load(open(os.path.join(C,'status.json'))) if os.path.exists(os.path.join(C,'status.json')) else {}
json.dump(R,open(os.path.join(OUT,'returns.json'),'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
print('assembled weeks',weeks,'bytes',os.path.getsize(os.path.join(OUT,'returns.json')))
