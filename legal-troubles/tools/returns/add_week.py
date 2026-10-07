# Add the newest completed NFL week to the Return Game store (Oct 7 redesign; Joe: stored weeks are never touched).
# Usage: python3 add_week.py <store_dir> <tools_dir>     store_dir = data/rg (index.json, weeks/, raw/, exceptions.json)
# 1) every existing week file must still match its fingerprint (read-only check, no network)
# 2) N = last stored week + 1; if any week-N game isn't final, stop: status "waiting" (nothing written)
# 3) fetch week N once: box.py (RG_WEEK=N, saves each game summary) + kickoffs.py (reads those summaries, no refetch)
# 4) verify week N only: verify_week.py (ESPN per-game team stats + ESPN fantasy weekly player stats)
# 5) write weeks/<season>-wNN.json + raw/<season>-wNN-summaries.json.gz with create-only mode, then append to index.json
# Writes <store_dir>/../rg_status.json-like status to stdout and ./add_week_status.json. Exit 0 = added/waiting/done, 1 = failure (nothing written).
import json,os,sys,gzip,hashlib,subprocess,tempfile,time,urllib.request
STORE,TD=(os.path.abspath(x) for x in sys.argv[1:3]);sys.path.insert(0,TD)
from rg_store import *
def get(u):
    for k in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except Exception:
            if k==2: raise
            time.sleep(2*(k+1))
def status(**k):
    k['at']=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime());json.dump(k,open('add_week_status.json','w'),indent=1);print(json.dumps(k));sys.exit(0 if k.get('ok') else 1)
idx=load_index(STORE);SEASON=idx.get('season',2026);have=sorted(int(w) for w in idx['weeks'])
for w in have: check_week_file(STORE,SEASON,w,idx['weeks'][str(w)])
N=(have[-1] if have else 0)+1
if os.path.exists(week_path(STORE,SEASON,N)): status(ok=False,error=f'week {N} file exists but is not in index.json; investigate (nothing changed)')
ev=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={N}&dates={SEASON}").get('events',[])
if not ev: status(ok=True,added=None,note=f'no week {N} on the NFL schedule: regular season complete',weeks=have)
notdone=[(e['shortName'],e['status']['type']['name']) for e in ev if not e['status']['type']['completed']]
if notdone: status(ok=True,added=None,waiting=N,note=f'week {N}: {len(ev)-len(notdone)} of {len(ev)} games final; nothing added',notFinal=notdone[:20],weeks=have)
T=tempfile.mkdtemp(prefix=f'rg_w{N}_')
def run(script,*args,env=None):
    r=subprocess.run([sys.executable,os.path.join(TD,script),*args],cwd=T,env={**os.environ,**(env or {})},capture_output=True,text=True)
    print(r.stdout[-1200:],r.stderr[-800:])
    if r.returncode: status(ok=False,error=f'{script} failed for week {N} (exit {r.returncode}); nothing written',detail=(r.stdout+r.stderr)[-600:])
run('box.py',env={'RG_WEEK':str(N),'RG_SUMMARY_CACHE':os.path.join(T,'summaries.json')})
run('kickoffs.py','summaries.json')
run('verify_week.py',T,str(N),env={'RG_EXCEPTIONS':os.path.join(STORE,'exceptions.json')})
M=json.load(open(os.path.join(T,'box_meta.json')));rep=json.load(open(os.path.join(T,'verify_report.json')))
if M['weeks']!=[N] or not rep.get('ok'): status(ok=False,error=f'week {N}: unexpected weeks {M["weeks"]} or failed verify; nothing written')
tab=tables_from_csv(T,N);raw=open(os.path.join(T,'summaries.json'),'rb').read();rawb=gzip.compress(raw,mtime=0)
fc=M.get('fairCatches',{})
W={'season':SEASON,'week':N,'createdAt':time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime()),'byes':M['byes'][str(N)] if str(N) in M['byes'] else M['byes'][N],
   'games':M['gamesPerWeek'].get(str(N),M['gamesPerWeek'].get(N)),'scoring':M['scoring'],
   'fairCatches':{'source':fc.get('source'),'unmatched':fc.get('unmatched',[]),'gamesWithoutPlayByPlay':fc.get('gamesWithoutPlayByPlay',[])},
   'verify':rep,'rawArchive':f'raw/{SEASON}-w{N:02d}-summaries.json.gz','rawSha256':hashlib.sha256(rawb).hexdigest(),'tables':tab,'sha256':sha(tab)}
os.makedirs(os.path.join(STORE,'weeks'),exist_ok=True);os.makedirs(os.path.join(STORE,'raw'),exist_ok=True)
with open(os.path.join(STORE,W['rawArchive']),'xb') as f: f.write(rawb)          # 'x' = create only; never overwrite
with open(week_path(STORE,SEASON,N),'x',encoding='utf-8') as f: json.dump(W,f,ensure_ascii=False,indent=0)
idx['weeks'][str(N)]={'file':f'weeks/{SEASON}-w{N:02d}.json','sha256':W['sha256'],'addedAt':W['createdAt'],'verify':{'ok':True,'checked':rep['checked']}}
json.dump(idx,open(os.path.join(STORE,'index.json'),'w'),indent=1)
K=tab['kickoff_coverage']
status(ok=True,added=N,weeks=have+[N],kickoffs=sum(int(x['kickoffs']) for x in K),returned=sum(int(x['returned']) for x in K),checked=rep['checked'],explained=len(rep.get('explained',[])))
