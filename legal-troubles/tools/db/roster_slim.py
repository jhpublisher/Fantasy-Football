#!/usr/bin/env python3
"""Build slim weekly roster copy (dashboard rosters/<wNN> shape) from frozen data/db/weeks/wNN/roster.json.
Usage: roster_slim.py <week> <out.json>"""
import json,sys,datetime,os
wk=int(sys.argv[1]); out=sys.argv[2]
B=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
r=json.load(open(f'{B}/db/weeks/w{wk:02d}/roster.json'))
names={t['id']:t['name'] for t in json.load(open(f'{B}/db/league/mTeam.json'))['teams']}
ab={p['id']:p['abbrev'] for p in json.load(open(f'{B}/db/league/nfl_schedule.json'))['settings']['proTeams']}
SLOT={0:'QB',2:'RB',3:'RB/WR',4:'WR',5:'WR/TE',6:'TE',7:'OP',23:'FLEX',16:'D/ST',17:'K',20:'Bench',21:'IR'}
POS={1:'QB',2:'RB',3:'WR',4:'TE',5:'K',16:'D/ST'}
teams={};n=0
for t in r['teams']:
    L=[]
    for e in t['roster']['entries']:
        p=e['playerPoolEntry']['player']
        L.append({'id':e['playerId'],'name':p['fullName'],'pos':POS[p['defaultPositionId']],'nfl':ab.get(p.get('proTeamId'),'FA'),'slot':SLOT[e['lineupSlotId']],'status':p.get('injuryStatus') or e.get('injuryStatus')})
    teams[names[t['id']].strip()]=L;n+=len(L)
assert len(teams)==14==len(r['teams'])
assert n==sum(len(t['roster']['entries']) for t in r['teams'])
json.dump({'week':wk,'updatedAt':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M+00:00'),'teams':teams},open(out,'w'),ensure_ascii=False,separators=(',',':'))
print('ok',len(teams),'teams',n,'players')
