# Injury checker (Oct 7): who should get a team's kick returns this week, and why it changed. Uses only data available
# before each game: earlier weeks' returns + offensive usage, last season's return history, and that week's official
# inactives / injury report. No network. Usage: python3 rg_checker.py <store_dir> [--backtest] [--json out.json]
# Flags per team-week:
#   RETURNER_BACK   a proven returner who missed the last game is active again -> expect him to take the job back
#   RETURNER_OUT    last game's main returner is out -> next man up
#   OFFENSE_NEED    a top offensive teammate is out and the returner has a real offensive role -> his returns may drop
import json,os,sys,gzip,glob,collections
STORE=os.path.abspath(sys.argv[1]);BT='--backtest' in sys.argv
OUT=sys.argv[sys.argv.index('--json')+1] if '--json' in sys.argv else None
idx=json.load(open(os.path.join(STORE,'index.json')));S=idx.get('season',2026);weeks=sorted(int(w) for w in idx['weeks'])
WK={w:json.load(open(os.path.join(STORE,idx['weeks'][str(w)]['file']),encoding='utf-8')) for w in weeks}
II=json.load(open(os.path.join(STORE,'injuries','index.json')))
INJ={int(w):json.load(open(os.path.join(STORE,'injuries',e['file']),encoding='utf-8')) for w,e in II['weeks'].items()}
refs=sorted(glob.glob(os.path.join(STORE,'reference','*-returners.json')))
PRIOR={int(k):v for k,v in json.load(open(refs[-1]))['players'].items()} if refs else {}
def usage_from_raw(w):
    U=collections.defaultdict(dict);N={}
    for gid,g in json.load(gzip.open(os.path.join(STORE,WK[w]['rawArchive']))).items():
        for tm in g['boxscore']['players']:
            t=tm['team']['abbreviation']
            for c in tm['statistics']:
                if c['name'] not in ('receiving','rushing'): continue
                k=c.get('keys') or [];i=k.index('receivingTargets') if c['name']=='receiving' and 'receivingTargets' in k else (k.index('rushingAttempts') if 'rushingAttempts' in k else None)
                if i is None: continue
                for a in c['athletes']:
                    pid=int(a['athlete']['id']);N[pid]=a['athlete']['displayName']
                    try: v=int(float(a['stats'][i]))
                    except Exception: v=0
                    U[t][pid]=U[t].get(pid,0)+v
    return U,N
G={}   # (team, week) -> game facts
NAME={}
for w in weeks:
    U,N=usage_from_raw(w);NAME.update(N)
    kr=collections.defaultdict(lambda:collections.Counter());tot={}
    for r in WK[w]['tables']['kick_returns']: kr[r['team']][int(r['espn_id'])]+=int(r['kr']);NAME[int(r['espn_id'])]=r['player']
    for r in WK[w]['tables']['team_game_kick_totals']: tot[r['team']]=int(r['team_kr'])
    J=INJ.get(w,{})
    for t in tot:
        inact={p['espn_id'] for p in J.get('inactives',{}).get(t,{}).get('did_not_play',[])}
        for p in J.get('inactives',{}).get(t,{}).get('did_not_play',[]): NAME.setdefault(p['espn_id'],p['name'])
        status={r['espn_id']:r['game_status'] for r in J.get('report',{}).get(t,[]) if r.get('espn_id')}
        for r in J.get('report',{}).get(t,[]):
            if r.get('espn_id'): NAME.setdefault(r['espn_id'],r['player'])
        G[(t,w)]={'kr':dict(kr[t]),'team_kr':tot[t],'usage':U.get(t,{}),'inactive':inact,'status':status,'injuries_known':w in INJ}
# upcoming week: expected inactives = Out or Doubtful on this week's official report (refresh_current injury_report.json)
UP=None;cp=os.path.join(STORE,'current','injury_report.json')
if os.path.exists(cp):
    CR=json.load(open(cp,encoding='utf-8'));UP=CR['week']
    if UP in weeks: UP=None
    else:
        for g in CR.get('games',[]):
            for t in (g['home'],g['away']):
                rows_=CR['report'].get(t,[]);exp={r['espn_id'] for r in rows_ if r.get('espn_id') and r['game_status'] in ('Out','Doubtful')}
                for r in rows_:
                    if r.get('espn_id'): NAME.setdefault(r['espn_id'],r['player'])
                G[(t,UP)]={'kr':{},'team_kr':0,'usage':{},'inactive':exp,'status':{r['espn_id']:r['game_status'] for r in rows_ if r.get('espn_id')},'injuries_known':True,'upcoming':True}
        weeks=weeks+[UP]
teams=sorted({t for t,_ in G})
def leader(c): return max(c.items(),key=lambda x:(x[1],x[0]))[0] if c and max(c.values())>0 else None
def nm(p): return NAME.get(p,str(p))
def predict(t,w):
    """Prediction for team t's game in week w using only earlier weeks + week-w inactives."""
    past=[x for x in weeks if x<w and (t,x) in G];g=G[(t,w)];flags=[]
    if not past: return None,flags
    prev=G[(t,past[-1])];season=collections.Counter()
    for x in past: season.update(G[(t,x)]['kr'])
    def proven(p):
        played=[x for x in past if p not in G[(t,x)]['inactive'] and G[(t,x)]['team_kr']]
        if played and season.get(p): return G[(t,played[-1])]['kr'].get(p,0)/G[(t,played[-1])]['team_kr']>=0.5
        return not season.get(p) and PRIOR.get(p,{}).get('kr',0)>=15
    seen_on_team={p for x in past+[w] for p in (set(G[(t,x)]['kr'])|G[(t,x)]['inactive']|set(G[(t,x)]['status'])|set(G[(t,x)]['usage']))}
    known={p for p in seen_on_team if season.get(p) or PRIOR.get(p,{}).get('kr',0)>=5}
    active=lambda p:p not in g['inactive']
    pred=None
    back=[p for p in known if proven(p) and p in prev['inactive'] and active(p)]
    if back:
        pred=max(back,key=lambda p:(season.get(p,0),PRIOR.get(p,{}).get('kr',0)))
        flags.append(('RETURNER_BACK',f"{nm(pred)} missed the last game and is active again"+(f" ({PRIOR[pred]['kr']} kick returns last season)" if PRIOR.get(pred,{}).get('kr') else '')+"; expect him to take the job back"))
    W2=collections.Counter()
    for i,x in enumerate(past): 
        for p,n in G[(t,x)]['kr'].items(): W2[p]+=n*(1+i)   # later games weigh more
    LG=leader(prev['kr']);L=LG if LG and prev['team_kr'] and prev['kr'][LG]/prev['team_kr']>=0.6 else (leader(W2) or LG)   # a clear leader last game wins; otherwise weighted season
    if pred is None:
        if L and active(L): pred=L
        else:
            cands=[p for p in known if active(p)]
            pred=max(cands,key=lambda p:(season.get(p,0),PRIOR.get(p,{}).get('kr',0))) if cands else None
            if L: flags.append(('RETURNER_OUT',f"{nm(L)} (last game's main returner) is out; next up: {nm(pred) if pred else 'nobody with return history'}"))
    if L and L!=pred and active(L) and back: flags.append(('SHARE_AT_RISK',f"{nm(L)} likely loses returns to {nm(pred)}"))
    # offensive need: a top-3 offensive teammate (targets + carries per game so far) is out and a returner has a real offensive role
    avgU=collections.Counter()
    for x in past: avgU.update(G[(t,x)]['usage'])
    avg={p:v/len(past) for p,v in avgU.items()};top=sorted(avg,key=avg.get,reverse=True)[:3]
    outs=[p for p in top if p in g['inactive']]
    for R in {x for x in (pred,L) if x}:
        if outs and avg.get(R,0)>=3 and R not in outs:
            flags.append(('OFFENSE_NEED',f"{', '.join(nm(p) for p in outs)} out; {nm(R)} averages {avg[R]:.1f} touches/targets a game, so the team may protect him from returns"))
    return pred,flags
rows=[]
for t in teams:
    for w in weeks:
        if (t,w) not in G: continue
        g=G[(t,w)];pred,flags=predict(t,w);act=leader(g['kr']);top=[p for p,n in g['kr'].items() if g['kr'] and n==max(g['kr'].values()) and n>0]
        shares={nm(p):round(n/g['team_kr'],2) for p,n in sorted(g['kr'].items(),key=lambda x:-x[1])} if g['team_kr'] else {}
        rows.append({'team':t,'week':w,'predicted':nm(pred) if pred else None,'actual':nm(act) if act else None,'hit':(pred in top) if pred and act else None,'team_kr':g['team_kr'],'shares':shares,'flags':flags})
done=[r for r in rows if not G[(r['team'],r['week'])].get('upcoming')]
sc=[r for r in done if r['hit'] is not None]
flagstats={f:{'flagged':sum(1 for r in sc if any(x[0]==f for x in r['flags'])),'right':sum(1 for r in sc if r['hit'] and any(x[0]==f for x in r['flags']))} for f in ('RETURNER_BACK','RETURNER_OUT','OFFENSE_NEED')}
result={'upcomingWeek':UP,'upcoming':{r['team']:{'predicted':r['predicted'],'flags':r['flags'],'expectedOut':sorted(nm(p) for p in G[(r['team'],UP)]['inactive'])} for r in rows if UP and r['week']==UP},
        'history':done,'backtest':{'right':sum(r['hit'] for r in sc),'games':len(sc),'flags':flagstats,
        'note':'main returner = most kick returns in the game (ties count); weeks 2+ only; uses only information available before each game'}}
if BT:
    print(f"backtest: predicted the main kick returner in {sum(r['hit'] for r in sc)} of {len(sc)} team-games (weeks 2+, games with returns)")
    for t in ('NYJ','MIA'):
        for r in rows:
            if r['team']==t: print(t,'wk',r['week'],'pred',r['predicted'],'| actual',r['actual'],r['shares'],'|',r['flags'])
    miss=[r for r in sc if not r['hit']];print('misses:',len(miss))
    for r in miss[:40]: print('  ',r['team'],r['week'],'pred',r['predicted'],'actual',r['actual'],r['shares'],[f[0] for f in r['flags']])
if OUT: json.dump(result,open(OUT,'w'),indent=0)
