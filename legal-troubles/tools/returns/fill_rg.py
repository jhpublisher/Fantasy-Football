# Build returns.json from box.py + espn_depth.py + team_sites.py output, with no blanks.
# Kick returns keep the original shape (teams[t].weeks/site/espn with .kr, players[]). Punt returns (Oct 7, Joe) sit beside them:
#   teams[t].pr = {weeks:{w:{team_pr,team_pr_yds,espn_pr,espn_pr_yds,fc,opp,ret:[{p,pr,y,td,fc}]}|{bye}}, site:{pr,raw,url,status,reason,asof}, espn:{pr,url,status,reason}}
#   pr = {players:[{name,id,team,pos,owner,wk:{w:{pr,y,td,fc,share,pts,team_pr}}}], fairCatches:{source,unmatched,gamesWithoutPlayByPlay}}
#   PR statuses: ok | no_pr_row (read, not listed) | no_chart | unread (with reason). fc = fair catches (play-by-play); '' never appears: no play-by-play -> null + reason
# - every team: site/espn status = ok | no_kr_row (read, not listed) | no_chart (team publishes none, verified) | unread (with reason)
# - names matched across sources after normalizing (Jr./Sr./II/III, punctuation, accents): "Brian Robinson" == "Brian Robinson Jr."
# - bye weeks recorded per team (excluded from averages in the page)
# - updatedAt (UTC ISO) = when this build ran; build_bundle/validator use it for freshness (never file mtime)
import json,urllib.request,re,unicodedata,csv,sys,datetime
def get(u,h=None,tries=3):   # retry transient errors, then raise
    import time
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0",**(h or {})}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
import os
# Offline mode (Oct 7 redesign): RG_CURRENT=<data/rg/current> -> rosters, ownership and schedule come from refresh_current.py files; no network at all.
CURD=os.environ.get('RG_CURRENT')
if CURD:
    def get(u,h=None,tries=3): raise RuntimeError(f'offline assemble tried the network: {u[:80]}')
    _cur=lambda f:json.load(open(os.path.join(CURD,f),encoding='utf-8'))
M=json.load(open('box_meta.json'));S=json.load(open('team_sites.json'));E=json.load(open('espn_depth.json'))
SUF=re.compile(r'\b(jr|sr|ii|iii|iv|v)\b')
def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=re.sub(r"[.'’`,-]",' ',s);s=SUF.sub(' ',s);return re.sub(r'[^a-z]','',s)
W=M['weeks'];CUR=M['currentWeek']
teams=sorted(k for k in E if not k.startswith('_'))
assert len(teams)==32,f"{len(teams)} teams in ESPN depth"
# 1) box scores -> team weeks + players
R={'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),'weeks':W,'currentWeek':CUR,'regSeasonWeeks':M['regSeasonWeeks'],'scoring':M['scoring'],'checked':datetime.date.today().strftime('%b %-d, %Y'),'teams':{},'players':[]}
R['kinds']=['kr','pr']
for t in teams: R['teams'][t]={'weeks':{},'byes':[w for w in W if t in M['byes'][str(w)]],'pr':{'weeks':{}}}
for row in csv.DictReader(open('team_game_kick_totals.csv')):
    R['teams'][row['team']]['weeks'][row['week']]={'team_kr':int(row['team_kr']),'opp':row['opp'],'ret':[]}
for t in teams:
    for w in W:
        x=R['teams'][t]['weeks']
        if str(w) not in x:
            if w in R['teams'][t]['byes']: x[str(w)]={'bye':True,'team_kr':0,'opp':'Bye','ret':[]}
            else: sys.exit(f"FAIL: {t} has no game and no bye in Week {w}")
# punt returns: team-games (ESPN totals kept so the validator can re-check them) + players
NOPBP=set(M.get('fairCatches',{}).get('gamesWithoutPlayByPlay') or [])
for row in csv.DictReader(open('team_game_punt_totals.csv')):
    R['teams'][row['team']]['pr']['weeks'][row['week']]={'team_pr':int(row['team_pr']),'team_pr_yds':int(row['team_pr_yds']),'espn_pr':int(row['espn_total_pr']),'espn_pr_yds':int(row['espn_total_yds']),
        'fc':(int(row['team_fc']) if row['team_fc']!='' else None),'opp':row['opp'],'ret':[]}
    if row['team_fc']=='': R['teams'][row['team']]['pr']['weeks'][row['week']]['fcReason']='no play-by-play for this game'
for t in teams:
    for w in W:
        x=R['teams'][t]['pr']['weeks']
        if str(w) not in x:
            if w in R['teams'][t]['byes']: x[str(w)]={'bye':True,'team_pr':0,'opp':'Bye','ret':[]}
            else: sys.exit(f"FAIL: {t} has no punt-return team-game and no bye in Week {w}")
Q={}
for r in csv.DictReader(open('punt_returns.csv')):
    w=r['week'];g=R['teams'][r['team']]['pr']['weeks'][w];fc=int(r['fc']) if r['fc']!='' else None
    g['ret'].append({'p':r['player'],'pr':int(r['pr']),'y':int(r['pr_yds']),'td':int(r['td']),'fc':fc})
    k=int(r['espn_id']);p=Q.setdefault(k,{'name':r['player'],'id':k,'team':r['team'],'pos':r['fantasy_pos'],'owner':r['owner'],'wk':{}})
    p['team']=r['team']
    p['wk'][w]={'pr':int(r['pr']),'y':int(r['pr_yds']),'td':int(r['td']),'fc':fc,'share':float(r['share']),'pts':float(r['fpts']),'team_pr':int(r['team_pr'])}
P={}
for r in csv.DictReader(open('kick_returns.csv')):
    w=r['week'];g=R['teams'][r['team']]['weeks'][w]
    g['ret'].append({'p':r['player'],'kr':int(r['kr']),'y':int(r['kr_yds']),'td':int(r['td'])})
    k=int(r['espn_id']);p=P.setdefault(k,{'name':r['player'],'id':k,'team':r['team'],'pos':r['fantasy_pos'],'owner':r['owner'],'wk':{}})
    p['team']=r['team']   # latest team (rows sorted by week)
    p['wk'][w]={'kr':int(r['kr']),'y':int(r['kr_yds']),'td':int(r['td']),'share':float(r['share']),'pts':float(r['fpts']),'team_kr':int(r['team_kr'])}
# 2) ids/positions per team: box players, ESPN depth, team rosters -> canonical name per (team, norm)
canon={};ids={};poss={}
for p in list(P.values())+list(Q.values()): canon.setdefault((p['team'],norm(p['name'])),p['name']);ids.setdefault((p['team'],norm(p['name'])),p['id'])
for t in teams:
    for kk in ('kr','pr'):
        for _,i,(n,ps) in E[t].get(kk,[]): canon.setdefault((t,norm(n)),n);ids.setdefault((t,norm(n)),int(i));poss[int(i)]=ps
roster_fail=[]
if CURD:
    RO=_cur('rosters.json')['teams']
    for t in teams:
        if t not in RO: roster_fail.append(t);continue
        for fn,i,ps in RO[t]: k=(t,norm(fn));canon.setdefault(k,fn);ids.setdefault(k,int(i));poss.setdefault(int(i),ps)
tm={} if CURD else {x['team']['abbreviation']:x['team']['id'] for x in get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")['sports'][0]['leagues'][0]['teams']}
for t,tid in tm.items():
    try: ro=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster")
    except Exception as e: roster_fail.append(t);continue
    for grp in ro.get('athletes',[]):
        for a in grp.get('items',[]):
            k=(t,norm(a['fullName']));canon.setdefault(k,a['fullName']);ids.setdefault(k,int(a['id']));poss.setdefault(int(a['id']),a.get('position',{}).get('abbreviation'))
C=lambda t,n:canon.get((t,norm(n)),n)
# 3) depth chart sources with explicit status
for t in teams:
    s=S.get(t,{"status":"unread","reason":"team site not checked"});x=R['teams'][t]
    raw=[n for n in (s.get('KR') or []) if n and n.strip()]
    x['site']={'kr':[C(t,n) for n in raw],'raw':raw,'url':s.get('url'),'status':s.get('status') or ('ok' if raw else 'unread')}
    if s.get('reason'): x['site']['reason']=s['reason']
    if s.get('asof'): x['site']['asof']=s['asof']
    if x['site']['status']=='ok' and not raw: x['site'].update(status='unread',reason='KR row found but no names')
    e=E[t];ekr=[C(t,n) for _,i,(n,ps) in e.get('kr',[]) if n]
    x['espn']={'kr':ekr,'url':f"https://www.espn.com/nfl/team/depth/_/name/{t.lower()}",'status':'unread' if e.get('error') else ('ok' if ekr else 'no_kr_row')}
    if e.get('error'): x['espn']['reason']=e['error']
    elif not ekr: x['espn']['reason']='ESPN depth chart has no kick-return row'
    # punt returners: same sources, same states
    praw=[n for n in (s.get('PR') or []) if n and n.strip()];xp=x['pr']
    sst=s.get('status') or 'unread'
    pst='ok' if praw else (sst if sst in ('no_chart','unread') else 'no_pr_row')
    xp['site']={'pr':[C(t,n) for n in praw],'raw':praw,'url':s.get('url'),'status':pst}
    if pst=='no_pr_row': xp['site']['reason']=s.get('PR_reason') or 'depth chart read; no punt-return row'
    elif pst!='ok': xp['site']['reason']=s.get('reason') or 'team site not checked'
    if s.get('PR_label'): xp['site']['label']=s['PR_label']
    if s.get('asof'): xp['site']['asof']=s['asof']
    epr=[C(t,n) for _,i,(n,ps) in e.get('pr',[]) if n]
    xp['espn']={'pr':epr,'url':x['espn']['url'],'status':'unread' if e.get('error') else ('ok' if epr else 'no_pr_row')}
    if e.get('error'): xp['espn']['reason']=e['error']
    elif not epr: xp['espn']['reason']='ESPN depth chart has no punt-return row'
# 4) depth-only names become players (0 returns so far)
have={(p['team'],norm(p['name'])) for p in P.values()}
add=[]
for t in teams:
    for src in ('site','espn'):
        for n in R['teams'][t][src]['kr']:
            k=(t,norm(n))
            if k not in have: have.add(k);add.append({'name':n,'id':ids.get(k),'team':t,'pos':None,'owner':None,'wk':{}})
haveq={(p['team'],norm(p['name'])) for p in Q.values()};addq=[]
for t in teams:
    for src in ('site','espn'):
        for n in R['teams'][t]['pr'][src]['pr']:
            k=(t,norm(n))
            if k not in haveq: haveq.add(k);addq.append({'name':n,'id':ids.get(k),'team':t,'pos':None,'owner':None,'wk':{}})
print('depth-only added KR',len(add),'PR',len(addq),'without ESPN id:',[a['name'] for a in add+addq if not a['id']])
# 5) fantasy owner/pos for anyone missing one
LG=293318;B=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/{LG}"
POS={1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
names={} if CURD else {x["id"]:x["name"].strip() for x in get(f"{B}?view=mTeam")["teams"]}
allp=list(P.values())+add;allq=list(Q.values())+addq
need=[p for p in allp+allq if p['id'] and p['owner'] in (None,'—','Not in ESPN fantasy')]
idl=sorted({p['id'] for p in need})
F={}
if CURD: OW=_cur('ownership.json');F={int(i):tuple(v) for i,v in OW['players'].items()};idl=[]
for k in range(0,len(idl),50):
    for p in get(f"{B}?view=kona_player_info&scoringPeriodId={CUR}",{"X-Fantasy-Filter":json.dumps({"players":{"filterIds":{"value":idl[k:k+50]}}})})["players"]:
        F[p["player"]["id"]]=(POS.get(p["player"]["defaultPositionId"],"Other"),names.get(p.get("onTeamId",0),"Free agent"))
for p in allp+allq:
    if p['owner'] in (None,'—','Not in ESPN fantasy'):
        if p['id'] in F: p['pos'],p['owner']=F[p['id']]
        elif not p['id']: p['pos']='Pos. unknown';p['owner']='No ESPN id match'   # depth-chart name we couldn't tie to an ESPN player
        else: p['pos']=poss.get(p['id']) or 'DEF';p['owner']='Not in ESPN fantasy'
    if p['pos'] in (None,'—','not in ESPN fantasy'): p['pos']=poss.get(p['id']) or ('DEF' if p['id'] else 'Pos. unknown')
R['players']=allp
R['pr']={'players':allq,'fairCatches':M.get('fairCatches') or {'source':'not recorded by box.py'}}
# 6) checks: no blanks, every team accounted for
bad=[(p['name'],k) for p in allp+allq for k in ('name','team','pos','owner') if not p.get(k) or p[k] in ('—','not in ESPN fantasy')]
st={}
for t,x in R['teams'].items():
    for src in ('site','espn'):
        s=x[src]['status'];st[(src,s)]=st.get((src,s),0)+1
        if s!='ok' and not x[src].get('reason'): bad.append((t,src,'status without reason'))
        if '' in x[src]['kr']: bad.append((t,src,"blank name"))
        y=x['pr'][src];s=y['status'];st[('pr.'+src,s)]=st.get(('pr.'+src,s),0)+1
        if s!='ok' and not y.get('reason'): bad.append((t,'pr.'+src,'status without reason'))
        if '' in y['pr']: bad.append((t,'pr.'+src,'blank name'))
    for w,g in x['pr']['weeks'].items():   # player sums = team total = ESPN total
        if g.get('bye'): continue
        mine=(sum(r['pr'] for r in g['ret']),sum(r['y'] for r in g['ret']))
        if not (mine==(g['team_pr'],g['team_pr_yds'])==(g['espn_pr'],g['espn_pr_yds'])): bad.append((t,w,'punt totals mismatch',mine,g['espn_pr'],g['espn_pr_yds']))
if roster_fail: print('WARN roster unreadable:',roster_fail)
print('status counts',st)
# 5b) Kickoff coverage (Oct 7, Joe): kickoffs[t][w] = {opp, kickoffs, returned, ret_yds_allowed, ret_td_allowed, touchback, out_of_bounds,
#     short_of_landing_zone, fair_catch, muff_lost, onside, onside_attempts} for the KICKING team, or {bye:true}. From kickoffs.py (kickoff_coverage.csv).
import os
if not os.path.exists('kickoff_coverage.csv'): bad.append(('kickoffs','kickoff_coverage.csv missing: run kickoffs.py after box.py'))
else:
    R['kickoffs']={t:{} for t in teams}
    for r in csv.DictReader(open('kickoff_coverage.csv')):
        if r['team'] not in R['kickoffs']: bad.append((r['team'],r['week'],'kickoff team not in teams'));continue
        R['kickoffs'][r['team']][r['week']]={'opp':r['opp'],'home':r['home_away']=='home',**{k:int(r[k]) for k in ('kickoffs','returned','ret_yds_allowed','ret_td_allowed','touchback','out_of_bounds','short_of_landing_zone','fair_catch','muff_lost','onside','onside_attempts','other')}}
    for t in teams:
        for wk in W:
            if wk in R['teams'][t]['byes']: R['kickoffs'][t].setdefault(str(wk),{'bye':True})
            elif str(wk) not in R['kickoffs'][t]: bad.append((t,wk,'no kickoff row'))
            else:
                x=R['kickoffs'][t][str(wk)];g=R['teams'].get(x['opp'],{}).get('weeks',{}).get(str(wk)) or R['teams'].get(x['opp'],{}).get('weeks',{}).get(wk)
                if not g: bad.append((t,wk,'opponent week missing'))
                elif g.get('team_kr')!=x['returned']: bad.append((t,wk,'kickoffs returned != opponent kick returns',x['returned'],g.get('team_kr')))
# 6) NFL schedule, whole regular season (Oct 7, Joe): schedule[t][w] = {opp, home, kickoff} or {bye:true}. The Returns tab shows only currentWeek.
SEASON=M.get('season',2026);SB="https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
R['schedule']={t:{} for t in teams};w=0
if CURD:
    SC=_cur('schedule.json');R['schedule']={t:SC['teams'].get(t,{}) for t in teams};w=SC['weeks']+1
while not CURD:
    w+=1;ev=get(f"{SB}?seasontype=2&week={w}&dates={SEASON}").get('events',[])
    if not ev: break
    seen=set()
    for e in ev:
        c=e['competitions'][0]['competitors'];ab={x['homeAway']:x['team']['abbreviation'] for x in c}
        for side,o in (('home','away'),('away','home')):
            t=ab[side]
            if t not in R['schedule']: bad.append((t,w,'schedule team not in depth-chart teams'));continue
            if t in seen: bad.append((t,w,'two games in one week'))
            seen.add(t);R['schedule'][t][str(w)]={'opp':ab[o],'home':side=='home','kickoff':e['date']}
    for t in teams:
        if t not in seen: R['schedule'][t][str(w)]={'bye':True}
    if w>=25: bad.append(('schedule','more than 25 weeks returned'));break
R['scheduleWeeks']=w-1
if R['scheduleWeeks']<R['regSeasonWeeks']: bad.append(('schedule',f"only {R['scheduleWeeks']} NFL weeks found"))
for t in teams:   # bye weeks from the schedule must agree with box.py's byes for completed weeks
    for wk in W:
        if R['schedule'][t].get(str(wk),{}).get('bye',False)!=(wk in R['teams'][t]['byes']): bad.append((t,wk,'schedule bye disagrees with box scores'))
    if str(CUR) not in R['schedule'][t]: bad.append((t,CUR,'no current-week schedule entry'))
print('schedule:',R['scheduleWeeks'],'weeks; week',CUR,'byes:',[t for t in teams if R['schedule'][t].get(str(CUR),{}).get('bye')])
if bad: sys.exit(f"FAIL blanks: {bad[:10]}")
json.dump(R,open('returns.json','w'))
mm=[(t,x['site']['raw'][0],x['espn']['kr'][0]) for t,x in R['teams'].items() if x['site']['raw'] and x['espn']['kr'] and x['site']['raw'][0]!=x['espn']['kr'][0] and x['site']['kr'][0]==x['espn']['kr'][0]]
print(len(allp),'KR players,',len(allq),'PR players; name-normalized agreements:',mm)
