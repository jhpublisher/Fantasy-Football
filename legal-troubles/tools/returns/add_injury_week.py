# Store the official injury data for every stored stats week that doesn't have it yet (create-only; never rewrites).
# Usage: python3 add_injury_week.py <store_dir> <tools_dir>     -> <store>/injuries/<season>-wNN.json + injuries/index.json
# Each file: NFL.com official injury report (final practice status + game status), game-day inactives (ESPN game rosters),
# ESPN ids for every name, checks (every Out player inactive or off the game roster; warnings kept), sha256 of the data.
import json,os,sys,subprocess,tempfile,hashlib,time
STORE,TD=(os.path.abspath(x) for x in sys.argv[1:3])
idx=json.load(open(os.path.join(STORE,'index.json')));S=idx.get('season',2026)
D=os.path.join(STORE,'injuries');os.makedirs(D,exist_ok=True)
ip=os.path.join(D,'index.json');II=json.load(open(ip)) if os.path.exists(ip) else {'season':S,'weeks':{}}
def fp(d): return hashlib.sha256(json.dumps({k:d[k] for k in ('report','inactives')},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
for w,e in II['weeks'].items():   # stored injury weeks must still match their fingerprints
    d=json.load(open(os.path.join(D,e['file']),encoding='utf-8'))
    if fp(d)!=d['sha256'] or d['sha256']!=e['sha256']: sys.exit(f'FAIL: injury week {w} changed since it was stored')
todo=sorted(int(w) for w in idx['weeks'] if w not in II['weeks']);added=[];failed=[]
for w in todo:
    out=os.path.join(tempfile.mkdtemp(),'inj.json')
    r=subprocess.run([sys.executable,os.path.join(TD,'injuries.py'),str(w),out,str(S)],capture_output=True,text=True);print(r.stdout[-600:],r.stderr[-400:])
    if r.returncode: failed.append({'week':w,'error':(r.stdout+r.stderr)[-400:]});continue
    d=json.load(open(out,encoding='utf-8'));d['createdAt']=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime());d['sha256']=fp(d)
    f=f'{S}-w{w:02d}.json'
    with open(os.path.join(D,f),'x',encoding='utf-8') as fh: json.dump(d,fh,ensure_ascii=False,indent=0)
    II['weeks'][str(w)]={'file':f,'sha256':d['sha256'],'addedAt':d['createdAt'],'outPlayers':d['checks']['out_players'],'warnings':len(d['checks']['warnings']),'unmatched':len(d['unmatched'])};added.append(w)
json.dump(II,open(ip,'w'),indent=1)
st={'ok':not failed,'added':added,'failed':failed,'weeks':sorted(int(w) for w in II['weeks'])};print(json.dumps(st));sys.exit(0 if not failed else 1)
