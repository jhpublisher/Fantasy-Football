# Refresh the Return Game "current state" (changes during the week; NOT history). Each part on its own cadence and its own
# failure: a failure keeps the last good file and is reported, never touching stored weeks. (Oct 7 redesign)
# Usage: python3 refresh_current.py <store_dir> <tools_dir> [--force]     writes <store>/current/*.json + current/status.json
#   ownership.json  every run   league owner + fantasy position for every returner in stored weeks and on depth charts; league current week
#   espn_depth.json  daily       ESPN depth-chart feed (KR/PR)          rosters.json  daily   32 team rosters (name -> ESPN id, position)
#   team_sites.json  daily Tue-Sat (ET)  32 team-site depth charts      schedule.json  Tuesdays (or if missing/older than 6 days)
import json,os,sys,time,subprocess,tempfile,shutil,datetime,urllib.request,concurrent.futures as cf
STORE,TD=(os.path.abspath(x) for x in sys.argv[1:3]);FORCE='--force' in sys.argv
C=os.path.join(STORE,'current');os.makedirs(C,exist_ok=True)
now=datetime.datetime.now(datetime.timezone.utc);et=now.astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
def get(u,h=None):
    for k in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0",**(h or {})}),timeout=60))
        except Exception:
            if k==2: raise
            time.sleep(2*(k+1))
def age_h(f):
    p=os.path.join(C,f)
    try: return (now-datetime.datetime.fromisoformat(json.load(open(p,encoding='utf-8'))['_asOf'])).total_seconds()/3600
    except Exception: return 1e9
def save(f,d): d['_asOf']=now.isoformat(timespec='minutes');tmp=os.path.join(C,f+'.tmp');json.dump(d,open(tmp,'w',encoding='utf-8'),ensure_ascii=False);os.replace(tmp,os.path.join(C,f))
ST=json.load(open(os.path.join(C,'status.json'))) if os.path.exists(os.path.join(C,'status.json')) else {}
def part(name,due,fn):
    if not (FORCE or due):
        ST.setdefault(name,{})['skipped']=f'not due ({age_h(name+".json"):.0f}h old)';return
    try: fn();ST[name]={'ok':True,'asOf':now.isoformat(timespec='minutes')}
    except Exception as e: ST[name]={**ST.get(name,{}),'ok':False,'error':str(e)[:300],'failedAt':now.isoformat(timespec='minutes')};print('WARN',name,e)
def script(s,out):
    T=tempfile.mkdtemp();r=subprocess.run([sys.executable,os.path.join(TD,s)],cwd=T,capture_output=True,text=True)
    if r.returncode or not os.path.exists(os.path.join(T,out)): raise RuntimeError(f'{s} exit {r.returncode}: {(r.stdout+r.stderr)[-200:]}')
    d=json.load(open(os.path.join(T,out),encoding='utf-8'));shutil.rmtree(T);return d
TEAMS=None
def teams():
    global TEAMS
    if TEAMS is None: TEAMS={t['team']['abbreviation']:t['team']['id'] for t in get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]}
    return TEAMS
def do_depth(): save('espn_depth.json',script('espn_depth.py','espn_depth.json'))
def do_sites(): save('team_sites.json',script('team_sites.py','team_sites.json'))
def do_rosters():
    def one(t):
        ro=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{teams()[t]}/roster")
        return t,[[a['fullName'],int(a['id']),(a.get('position') or {}).get('abbreviation')] for g in ro.get('athletes',[]) for a in g.get('items',[])]
    with cf.ThreadPoolExecutor(8) as ex: R=dict(ex.map(one,sorted(teams())))
    if len(R)!=32 or any(not v for v in R.values()): raise RuntimeError('roster missing for some team')
    save('rosters.json',{'teams':R})
def do_schedule():
    idx=json.load(open(os.path.join(STORE,'index.json')));S=idx.get('season',2026);out={t:{} for t in teams()};w=0
    while True:
        w+=1;ev=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w}&dates={S}").get('events',[])
        if not ev or w>25: break
        seen=set()
        for e in ev:
            ab={x['homeAway']:x['team']['abbreviation'] for x in e['competitions'][0]['competitors']}
            for side,o in (('home','away'),('away','home')): seen.add(ab[side]);out[ab[side]][str(w)]={'opp':ab[o],'home':side=='home','kickoff':e['date']}
        for t in out:
            if t not in seen: out[t][str(w)]={'bye':True}
    if w-1<17: raise RuntimeError(f'only {w-1} schedule weeks')
    save('schedule.json',{'weeks':w-1,'teams':out})
def do_ownership():
    B="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/293318"
    L=get(f"{B}?view=mTeam&view=mStatus&view=mSettings");names={x['id']:(x.get('name') or '').strip() for x in L['teams']}
    POS={1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"};ids=set()
    idx=json.load(open(os.path.join(STORE,'index.json')))
    for w,e in idx['weeks'].items():
        W=json.load(open(os.path.join(STORE,e['file']),encoding='utf-8'))
        for t in ('kick_returns','punt_returns'): ids|={int(r['espn_id']) for r in W['tables'][t]}
    try:
        E=json.load(open(os.path.join(C,'espn_depth.json'),encoding='utf-8'))
        for t,x in E.items():
            if not t.startswith('_') and isinstance(x,dict):
                for k in ('kr','pr'): ids|={int(i) for _,i,_n in x.get(k,[])}
    except FileNotFoundError: pass
    try:   # team-site depth names -> ESPN ids through today's rosters (same name normalization as fill_rg.py)
        import re,unicodedata
        def norm(s):
            s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower();s=re.sub(r"[.'’`,-]",' ',s);s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b',' ',s);return re.sub(r'[^a-z]','',s)
        RO=json.load(open(os.path.join(C,'rosters.json'),encoding='utf-8'))['teams'];TS=json.load(open(os.path.join(C,'team_sites.json'),encoding='utf-8'))
        for t,x in TS.items():
            if t.startswith('_') or not isinstance(x,dict): continue
            m={norm(fn):i for fn,i,_p in RO.get(t,[])}
            for k in ('KR','PR'):
                for n in x.get(k) or []:
                    if norm(n) in m: ids.add(int(m[norm(n)]))
    except FileNotFoundError: pass
    ids=sorted(ids);P={}
    for i in range(0,len(ids),50):
        for p in get(f"{B}?view=kona_player_info&scoringPeriodId={L.get('scoringPeriodId') or L['status']['latestScoringPeriod']}",{"X-Fantasy-Filter":json.dumps({"players":{"filterIds":{"value":ids[i:i+50]}}})})["players"]:
            P[str(p['player']['id'])]=[POS.get(p['player']['defaultPositionId'],'Other'),names.get(p.get('onTeamId',0),'Free agent')]
    save('ownership.json',{'currentWeek':L.get('scoringPeriodId') or L['status']['latestScoringPeriod'],'regSeasonWeeks':L['settings']['scheduleSettings'].get('matchupPeriodCount',14),
        'queried':ids,'players':P,'note':'ids queried but absent from players = not in ESPN fantasy'})
part('espn_depth', age_h('espn_depth.json')>20, do_depth)
part('rosters', age_h('rosters.json')>20, do_rosters)
part('team_sites', age_h('team_sites.json')>20 and (et.weekday() in (1,2,3,4,5) or age_h('team_sites.json')>96), do_sites)
part('schedule', (et.weekday()==1 and age_h('schedule.json')>12) or age_h('schedule.json')>144, do_schedule)
part('ownership', True, do_ownership)
for n in ('espn_depth','rosters','team_sites','schedule','ownership'): ST.setdefault(n,{})['ageHours']=round(age_h(n+'.json'),1)
json.dump(ST,open(os.path.join(C,'status.json'),'w'),indent=1);print(json.dumps(ST))
sys.exit(0 if all(ST[n].get('ok',True) for n in ST) else 2)   # 2 = some part failed (last good kept)
