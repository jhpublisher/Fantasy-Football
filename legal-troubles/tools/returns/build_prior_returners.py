# One-time reference (locked): last season's kick/punt return volume for every player who could matter to a 2026 return job:
# all 2026 returners, every WR/RB/CB/S/TE on an official injury report or inactive list, and every depth-chart KR/PR.
# Usage: python3 build_prior_returners.py <store_dir> <prior_season>   -> <store>/reference/<prior>-returners.json (create-only;
# rerun with --add only appends ids not yet covered). Source: ESPN athlete season statistics (category returning).
import json,os,sys,glob,urllib.request,concurrent.futures as cf,hashlib,time
STORE=os.path.abspath(sys.argv[1]);P=int(sys.argv[2]);ADD='--add' in sys.argv
def get(u):
    for k in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except urllib.error.HTTPError as e:
            if e.code==404: return None
            if k==2: raise
        except Exception:
            if k==2: raise
        time.sleep(2*(k+1))
ids=set()
for f in glob.glob(os.path.join(STORE,'weeks','*.json')):
    W=json.load(open(f,encoding='utf-8'));ids|={int(r['espn_id']) for t in ('kick_returns','punt_returns') for r in W['tables'][t]}
for f in glob.glob(os.path.join(STORE,'injuries','20*.json')):
    J=json.load(open(f,encoding='utf-8'))
    for t,rows in J['report'].items(): ids|={r['espn_id'] for r in rows if r.get('espn_id') and r['pos'] in ('WR','RB','CB','S','TE','FB','DB')}
    for t,x in J['inactives'].items(): ids|={p['espn_id'] for p in x['did_not_play'] if p['pos'] in ('WR','RB','CB','S','TE','FB','DB')}
try:
    E=json.load(open(os.path.join(STORE,'current','espn_depth.json'),encoding='utf-8'))
    for t,x in E.items():
        if isinstance(x,dict): ids|={int(i) for k in ('kr','pr') for _,i,_n in x.get(k,[])}
except FileNotFoundError: pass
out=os.path.join(STORE,'reference',f'{P}-returners.json');os.makedirs(os.path.dirname(out),exist_ok=True)
old=json.load(open(out)) if os.path.exists(out) else None
if old and not ADD: sys.exit(f'{out} exists (locked); use --add to append new ids only')
have=set(int(i) for i in (old or {}).get('checked',[]));need=sorted(ids-have)
def one(i):
    s=get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{P}/types/2/athletes/{i}/statistics")
    if not s: return i,None
    R={x['name']:x['value'] for c in s['splits']['categories'] if c['name']=='returning' for x in c['stats']}
    return i,{'kr':int(R.get('kickReturns',0)),'kr_yds':int(R.get('kickReturnYards',0)),'pr':int(R.get('puntReturns',0)),'pr_yds':int(R.get('puntReturnYards',0))}
res=dict((old or {}).get('players',{}))
with cf.ThreadPoolExecutor(10) as ex:
    for i,v in ex.map(one,need):
        if v and (v['kr'] or v['pr']): res[str(i)]=v
doc={'season':P,'source':'ESPN athlete season statistics (returning)','checked':sorted(have|set(need)),'players':res,'updatedAt':time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime())}
json.dump(doc,open(out,'w'),indent=0);print(json.dumps({'checked':len(doc['checked']),'new':len(need),'with_returns':len(res)}))
