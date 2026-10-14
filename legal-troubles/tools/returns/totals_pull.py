#!/usr/bin/env python3
"""totals_pull.py (Rich, Oct 13 2026): total fantasy points per week for every returner, for the Returner rankings
"Ttl pts / GM (3)" column. Reads returns/current (ids), asks the ESPN fantasy API for each player's actual weekly points
in OUR scoring (appliedTotal; return, rushing, receiving, everything), writes <out>/returns/totals.json:
  {asOf, week, weeks:[..], players:{"<espnId>":{"name","team","w":{"1":pts,...},"played":[weeks with an ESPN actual entry]}},
   missing:{"<id or name>": reason}}
Usage: python3 totals_pull.py <returns_current.json> <out_dir>
Fails loudly: exit 1 if ESPN returns nothing, or any returner with an id is neither in the result nor listed in missing with a reason."""
import json,sys,os,time,urllib.request,datetime
B="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/293318"
def get(u,h=None,tries=3):
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0",**(h or {})}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
R=json.load(open(sys.argv[1])); R=R.get('data',R) if isinstance(R,dict) and 'data' in R and 'teams' not in R else R
OUT=sys.argv[2]; cur=R.get('currentWeek') or max(R['weeks'])+1; weeks=R['weeks']
people={}
for p in (R.get('players') or [])+((R.get('pr') or {}).get('players') or []):
    if p.get('name'): people.setdefault(str(p['id']) if p.get('id') else 'name:'+p['name'],{'name':p['name'],'team':p.get('team')})
ids=[int(k) for k in people if not k.startswith('name:')]
out={};missing={}
for k,v in people.items():
    if k.startswith('name:'): missing[v['name']]='no ESPN id for this returner (not matched to an ESPN player)'
flt={"value":cur,"additionalValue":[f"00{2026}",f"10{2026}",f"01{2026}",f"11{2026}",f"11{2026}{cur}"]}
for i in range(0,len(ids),50):
    chunk=ids[i:i+50]
    d=get(f"{B}?view=kona_player_info&scoringPeriodId={cur}",{"X-Fantasy-Filter":json.dumps({"players":{"filterIds":{"value":chunk},"filterStatsForTopScoringPeriodIds":flt}})})
    for p in d.get("players",[]):
        pl=p["player"];pid=str(pl["id"]);w={}
        for s in pl.get("stats",[]):
            if s.get("seasonId",2026)==2026 and s.get("statSourceId")==0 and s.get("statSplitTypeId")==1 and s.get("scoringPeriodId") in weeks and s.get("stats"):
                w[str(s["scoringPeriodId"])]=round(s.get("appliedTotal") or 0,1)
        out[pid]={"name":pl.get("fullName") or people[pid]["name"],"team":people[pid]["team"],"w":w,"played":sorted(int(x) for x in w)}
for k in people:
    if not k.startswith('name:') and k not in out: missing[k]=f"{people[k]['name']}: ESPN fantasy pool does not list this player (no points to show)"
if not out: print("FAIL: ESPN returned no players");sys.exit(1)
os.makedirs(os.path.join(OUT,'returns'),exist_ok=True)
doc={"asOf":datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ'),"week":cur,"weeks":weeks,"players":out,"missing":missing,"source":"ESPN fantasy API kona_player_info, actual weekly points in league scoring (appliedTotal)"}
json.dump(doc,open(os.path.join(OUT,'returns','totals.json'),'w'),indent=0)
print(f"ok: {len(out)} players with points, {sum(1 for v in out.values() if v['w'])} with at least one week, {len(missing)} explained missing")
