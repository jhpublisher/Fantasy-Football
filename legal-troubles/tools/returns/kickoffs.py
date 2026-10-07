# Kickoff coverage per team per week (Joe, Oct 7): how often each team kicks off, how many of those are returned, return yards allowed.
# Kicking-team view. Source: ESPN game summaries (play-by-play for kickoffs; box score for returns/yards, cross-checked).
# Reads team_game_kick_totals.csv + box_meta.json (box.py output). Writes kickoff_coverage.csv. Fails loudly on any mismatch.
#   onside = onside kicks not returned; onside_attempts = all onside kicks (an onside kick the receiving team returns counts as returned)
#   kickoffs = every kickoff play (incl. onside, free kicks after a safety); "No Play" kicks (penalty, re-kicked) are not counted, re-kicks are.
#   outcome per kickoff: returned (incl. muffs the receiving team recovers; ESPN's box counts those as returns) | touchback | out_of_bounds |
#   short_of_landing_zone (penalty, ball at the 40) | onside | fair_catch | muff_lost (kicking team recovers) | other (each listed with its text; run fails if any)
#   returned/ret_yds_allowed/ret_td_allowed = the receiving team's box-score kick returns (ESPN totals); play-by-play returned count must match.
import json,urllib.request,csv,re,sys,os,time
def get(u,tries=3):
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
M=json.load(open('box_meta.json'))
TOT={};GAMES={}
for r in csv.DictReader(open('team_game_kick_totals.csv')):
    TOT[(r['game_id'],r['team'])]=r;GAMES.setdefault(r['game_id'],[]).append(r)
CACHE=json.load(open(sys.argv[1])) if len(sys.argv)>1 and os.path.exists(sys.argv[1]) else {}
OUTS=('returned','touchback','out_of_bounds','short_of_landing_zone','onside','fair_catch','muff_lost','other')
rows=[];bad=[];others=[]
for gid,tr in GAMES.items():
    if len(tr)!=2: bad.append((gid,'expected 2 team rows',len(tr)));continue
    d=CACHE.get(gid) or get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={gid}")
    comp=d['header']['competitions'][0]['competitors'];ab={c['team']['id']:c['team']['abbreviation'] for c in comp};ha={c['team']['abbreviation']:c['homeAway'] for c in comp}
    cnt={t['team']:{**{k:0 for k in OUTS},'onside_attempts':0} for t in tr}
    seen=set()
    for dr in d.get('drives',{}).get('previous',[]):
        for p in dr['plays']:
            x=p.get('text','')
            if p.get('id') in seen: continue
            seen.add(p.get('id'))
            if not re.search(r'\bkicks (\d+ yards|onside|-?\d+)',x) or re.search(r'punts',x): continue
            if 'No Play' in x: continue
            kt=ab.get(p.get('start',{}).get('team',{}).get('id'))
            if kt not in cnt:   # fall back to "from XXX 35" (ESPN uses ARZ/CLV etc. in text, so map via the other team)
                bad.append((gid,'kickoff with unknown kicking team',x[:120]));continue
            head=x.split('PENALTY')[0]
            kab=(re.search(r'from (\w+) -?\d+',head) or [None,None])[1]
            ons=bool(re.search(r'onside',head,re.I))
            if 'MUFF' in head.upper(): r_=re.search(r'recovered by (\w+)-',head);o='muff_lost' if r_ and r_[1]==kab else 'returned'
            elif 'short of landing zone' in head: o='short_of_landing_zone'
            elif 'Touchback' in head: o='touchback'
            elif re.search(r'out of bounds',head) and not re.search(r' to \S+ \S+ for ',head): o='out_of_bounds'
            elif 'fair catch' in head.lower(): o='fair_catch'
            elif ons and "didn't try to advance" in head: o='onside'
            elif re.search(r'\. [A-Z][\w\'\-]*\.[\w\'\-]+.* (to|ran ob at|pushed ob at) .*(for -?\d+ yards?|for no gain)|TOUCHDOWN',head): o='returned'
            elif ons: o='onside'
            else: o='other';others.append((gid,kt,x[:200]))
            cnt[kt][o]+=1
            if ons: cnt[kt]['onside_attempts']+=1
    for t in tr:   # t = receiving team's box row; kicking team = its opponent
        k=t['opp'];c=cnt.get(k)
        if c is None: bad.append((gid,'kicking team missing',k));continue
        rec=t; ko=sum(c[o] for o in OUTS)
        if c['returned']!=int(rec['team_kr']): bad.append((gid,k,'play-by-play returned',c['returned'],'box',rec['team_kr']))
        if ko==0: bad.append((gid,k,'0 kickoffs'))
        rows.append({'week':int(t['week']),'game_id':gid,'date':t['date'],'team':k,'opp':t['team'],'home_away':ha.get(k,''),'kickoffs':ko,
            'returned':int(rec['team_kr']),'ret_yds_allowed':int(rec['team_kr_yds']),**{o:c[o] for o in OUTS if o!='returned'},'onside_attempts':c['onside_attempts']})
# TDs allowed from kick_returns.csv
td={}
for r in csv.DictReader(open('kick_returns.csv')): td[(r['game_id'],r['opp'])]=td.get((r['game_id'],r['opp']),0)+int(r['td'] or 0)
for r in rows: r['ret_td_allowed']=td.get((r['game_id'],r['team']),0)
# every week: every playing team appears exactly once
for w in M['weeks']:
    teams=[r['team'] for r in rows if r['week']==w]
    if len(teams)!=len(set(teams)) or len(teams)+len(M['byes'][str(w)])!=32: bad.append((w,'teams',len(teams),'byes',len(M['byes'][str(w)])))
if others: bad.append(('unclassified kickoffs',others[:10]))
if bad: sys.exit(f"FAIL: {bad[:15]}")
F=['week','game_id','date','team','opp','home_away','kickoffs','returned','ret_yds_allowed','ret_td_allowed','touchback','out_of_bounds','short_of_landing_zone','fair_catch','muff_lost','onside','onside_attempts','other']
rows.sort(key=lambda r:(r['week'],r['team']))
with open('kickoff_coverage.csv','w',newline='') as f: w=csv.DictWriter(f,F);w.writeheader();w.writerows(rows)
k=sum(r['kickoffs'] for r in rows);rt=sum(r['returned'] for r in rows)
print(f"OK {len(rows)} team-games, {k} kickoffs, {rt} returned ({rt/k:.0%}), {sum(r['ret_yds_allowed'] for r in rows)} yds allowed, {sum(r['other'] for r in rows)} other")
