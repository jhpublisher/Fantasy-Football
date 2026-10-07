# Official injury data for ONE week (Joe, Oct 7: official league sources only, never news outlets).
#   1) NFL.com weekly injury report (team filings to the league): https://www.nfl.com/injuries/league/<season>/reg<week>
#      per player: position, injury, final practice status, game status (Out / Doubtful / Questionable / none)
#   2) Game-day inactives: ESPN competitor game rosters (didNotPlay) for every game of the week
#   (League transactions were tried and dropped Oct 7: NFL.com serves only the newest 25 per month without a browser.)
#   3) Names tied to ESPN ids through the game roster first, then current team rosters; unmatched names are listed, never guessed
# Usage: python3 injuries.py <week> <out.json> [season] [--report-only]   (--report-only: this week's report before games; no inactives)     Exit 1 on any failure (missing team, unreadable page, unmatched Out player).
import json,re,sys,html,time,unicodedata,urllib.request,urllib.parse,concurrent.futures as cf
RO='--report-only' in sys.argv;A=[a for a in sys.argv[1:] if a!='--report-only']
W=int(A[0]);OUT=A[1];S=int(A[2]) if len(A)>2 else 2026
def fetch(u,js=True):
    for k in range(3):
        try:
            r=urllib.request.urlopen(urllib.request.Request(u.replace('http://','https://'),headers={"User-Agent":"Mozilla/5.0"}),timeout=60).read()
            return json.loads(r) if js else r.decode('utf-8','ignore')
        except Exception:
            if k==2: raise
            time.sleep(2*(k+1))
def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower();s=re.sub(r"[.'’`,-]",' ',s);s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b',' ',s);return re.sub(r'[^a-z]','',s)
fails=[]
TEAMS=fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]
NICK={t['team']['name']:t['team']['abbreviation'] for t in TEAMS};TID={t['team']['abbreviation']:t['team']['id'] for t in TEAMS}
# --- 1) NFL.com report
url=f"https://www.nfl.com/injuries/league/{S}/reg{W}";page=fetch(url,js=False)
rep={}
for m in re.finditer(r'd3-o-section-sub-title"><span>([^<]+)</span>.*?<tbody>(.*?)</tbody>',page,re.S):
    nick=html.unescape(m.group(1)).strip();t=NICK.get(nick)
    if not t: fails.append(f'NFL.com team name not recognised: {nick}');continue
    rows=[]
    for tr in re.findall(r'<tr>(.*?)</tr>',m.group(2),re.S):
        td=[html.unescape(re.sub(r'<[^>]+>','',x)).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
        slug=re.search(r'href="/players/([^/"]+)/',tr)
        if len(td)<5: fails.append(f'{t}: short row {td}');continue
        rows.append({'player':td[0],'pos':td[1],'injury':td[2],'practice':td[3],'game_status':td[4],'nfl_slug':slug.group(1) if slug else None})
    if t in rep: rep[t]+=rows
    else: rep[t]=rows
if not rep: fails.append(f'NFL.com report empty or unreadable: {url}')
# --- 2) games + inactives (ESPN game rosters)
ev=fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={W}&dates={S}").get('events',[])
games=[];playing=set()
for e in ev:
    c={x['homeAway']:x['team']['abbreviation'] for x in e['competitions'][0]['competitors']};games.append({'game_id':e['id'],'home':c['home'],'away':c['away'],'date':e['date'],'final':e['status']['type']['completed']});playing|=set(c.values())
ROS={}
def roster(t): return t,fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{TID[t]}/roster")
with cf.ThreadPoolExecutor(8) as ex:
    for t,ro in ex.map(roster,sorted(TID)): ROS[t]={norm(a['fullName']):(int(a['id']),a['fullName'],(a.get('position') or {}).get('abbreviation')) for g in ro.get('athletes',[]) for a in g.get('items',[])}
ath_cache={}
def athlete(ref):
    if ref not in ath_cache: a=fetch(ref);ath_cache[ref]=(int(a['id']),a.get('fullName') or a.get('displayName'),(a.get('position') or {}).get('abbreviation'))
    return ath_cache[ref]
INACT={};GRNAMES={}
def game_team(arg):
    g,t=arg;gid=g['game_id']
    ro=fetch(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{gid}/competitions/{gid}/competitors/{TID[t]}/roster")
    ent=ro.get('entries',[]);dnp=[]
    for x in ent:
        if x.get('didNotPlay'):
            i,n,p=athlete(x['athlete']['$ref']);dnp.append({'espn_id':i,'name':n,'pos':p})
    return t,gid,len(ent),dnp,{int(x['playerId']):x.get('displayName') for x in ent if x.get('playerId')}
jobs=[] if RO else [(g,t) for g in games if g['final'] for t in (g['home'],g['away'])]
if not RO and len(jobs)!=2*len(games): fails.append(f'week {W}: only {len(jobs)//2} of {len(games)} games final')
with cf.ThreadPoolExecutor(8) as ex:
    for t,gid,n,dnp,names in ex.map(game_team,jobs):
        if n<40: fails.append(f'{t} game {gid}: game roster has only {n} players')
        INACT[t]={'game_id':gid,'roster_size':n,'did_not_play':dnp};GRNAMES[t]=names
# --- 3) tie report names to ESPN ids
unmatched=[]
for t,rows in rep.items():
    if t not in playing: fails.append(f'{t}: on the injury report but not playing week {W}');continue
    dnp={norm(x['name']):x['espn_id'] for x in INACT.get(t,{}).get('did_not_play',[])}
    for r in rows:
        k=norm(r['player']);hit=dnp.get(k) or (ROS.get(t,{}).get(k) or (None,))[0]
        if not hit and r['nfl_slug']: hit=(ROS.get(t,{}).get(norm(r['nfl_slug'].rsplit('-',1)[0] if r['nfl_slug'][-1].isdigit() else r['nfl_slug'])) or (None,))[0]
        r['match']='game roster/team roster' if hit else None
        if not hit:   # ESPN player search; accepted only if exactly one NFL player with the same last name comes back
            q=urllib.parse.quote(r['player']);items=fetch(f"https://site.web.api.espn.com/apis/common/v3/search?query={q}&type=player&sport=football&league=nfl&limit=5").get('items',[])
            last=norm(r['player'].split()[-1]) if r['player'].split() else ''
            c=[i for i in items if norm((i.get('displayName') or '').split()[-1] if i.get('displayName') else '')==last]
            if len(c)==1: hit=int(c[0]['id']);r['match']=f"ESPN search ({c[0].get('displayName')})"
        r['espn_id']=hit
        if not hit: unmatched.append(f"{t} {r['player']} ({r['game_status'] or 'no status'})")
        r['inactive']=bool(hit) and any(x['espn_id']==hit for x in INACT.get(t,{}).get('did_not_play',[]))
# --- checks: every team that played has inactives; every Out player is inactive (or not on the game roster at all)
for t in playing:
    if t not in INACT and not RO: fails.append(f'{t}: no game roster')
    if t not in rep: rep[t]=[]   # a team may file no injuries; recorded as an empty list
outs=[];warns=[]
for t,rows in rep.items():
    for r in rows:
        if r['game_status']=='Out':
            on_roster=r['espn_id'] in GRNAMES.get(t,{})
            if r['espn_id'] is None: fails.append(f"{t} {r['player']} Out but not matched to an ESPN id")
            elif not RO and on_roster and not r['inactive']: warns.append(f"{t} {r['player']}: official report Out; ESPN game roster doesn't flag did-not-play (official report kept)")
            outs.append(r['player'])
res={'season':S,'week':W,'reportOnly':RO,'sources':{'injury_report':url,'inactives':'ESPN game rosters (didNotPlay), sports.core.api.espn.com competitions/{id}/competitors/{team}/roster'},
     'byes':sorted(set(TID)-playing),'games':games,'report':rep,'inactives':INACT,'unmatched':unmatched,
     'checks':{'teams_reporting':len([t for t in rep if rep[t]]),'teams_playing':len(playing),'out_players':len(outs),'failures':fails,'warnings':warns}}
json.dump(res,open(OUT,'w',encoding='utf-8'),ensure_ascii=False,indent=0)
print(json.dumps({'week':W,'teams_playing':len(playing),'report_rows':sum(len(v) for v in rep.values()),'inactive':sum(len(v['did_not_play']) for v in INACT.values()),'unmatched':unmatched[:10],'fails':fails[:15]}))
sys.exit(1 if fails else 0)
