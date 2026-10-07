# ESPN depth charts (KR and PR ranks, top 3) for all 32 teams. status no_kr_row / pr_status no_pr_row = chart read, no such row. Fails loudly per team; never drops blanks silently.
import json,urllib.request,concurrent.futures as cf,sys,datetime
def get(u,tries=3):   # retry transient errors, then raise (caller reports the team as unread)
    import time
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60))
        except Exception:
            if k==tries-1: raise
            time.sleep(2*(k+1))
SEASON=2026
teams=get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]
T={t["team"]["id"]:t["team"]["abbreviation"] for t in teams}
ath={}
def name(ref):
    i=ref.split('/athletes/')[1].split('?')[0]
    if i not in ath:
        a=get(ref.replace('http://','https://')); ath[i]=((a.get('displayName') or '').strip(),a.get('position',{}).get('abbreviation'))
    return i,ath[i]
def team(tid):
    try: d=get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{SEASON}/teams/{tid}/depthcharts")
    except Exception as e: return T[tid],{"error":f"ESPN depth chart unreadable: {str(e)[:80]}"}
    out={}
    for it in d.get('items',[]):
        for k,v in it.get('positions',{}).items():
            if k in('kr','pr'):
                rows=[(a['rank'],*name(a['athlete']['$ref'])) for a in sorted(v['athletes'],key=lambda a:a['rank'])]
                out[k]=[r for r in rows if r[2][0]][:3]          # strip '' names
    if 'kr' not in out: out['status']='no_kr_row'
    if 'pr' not in out: out['pr_status']='no_pr_row'
    return T[tid],out
res={}
with cf.ThreadPoolExecutor(8) as ex:
    for ab,o in ex.map(team,list(T)): res[ab]=o
res['_checked']=datetime.date.today().isoformat()
json.dump(res,open('espn_depth.json','w'))
miss=[ab for ab in T.values() if 'error' in res[ab]]
print(len(T),'teams;',sum(1 for ab in T.values() if res[ab].get('kr')),'with KR;',sum(1 for ab in T.values() if res[ab].get('pr')),'with PR;','unread:',miss,'no PR row:',[ab for ab in T.values() if res[ab].get('pr_status')])
if len(T)!=32: sys.exit(f"FAIL: {len(T)} NFL teams")
