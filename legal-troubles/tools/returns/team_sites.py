# Team-site depth charts: KR and PR rows for all 32 teams.
# PR: PR_status ok | no_pr_row (chart read, no punt-return row); no_chart/unread apply to both kinds.
# Each team ends as: ok (KR row read) | no_kr_row (chart read, no KR row) | no_chart (page loads, no depth table) | unread (fetch/parse failed, with reason)
import urllib.request,re,json,html,datetime,concurrent.futures as cf
SITES={"ARI":"azcardinals.com","ATL":"atlantafalcons.com","BAL":"baltimoreravens.com","BUF":"buffalobills.com","CAR":"panthers.com","CHI":"chicagobears.com","CIN":"bengals.com","CLE":"clevelandbrowns.com",
"DAL":"dallascowboys.com","DEN":"denverbroncos.com","DET":"detroitlions.com","GB":"packers.com","HOU":"houstontexans.com","IND":"colts.com","JAX":"jaguars.com","KC":"chiefs.com","LAC":"chargers.com","LAR":"therams.com",
"LV":"raiders.com","MIA":"miamidolphins.com","MIN":"vikings.com","NE":"patriots.com","NO":"neworleanssaints.com","NYG":"giants.com","NYJ":"newyorkjets.com","PHI":"philadelphiaeagles.com","PIT":"steelers.com",
"SEA":"seahawks.com","SF":"49ers.com","TB":"buccaneers.com","TEN":"tennesseetitans.com","WSH":"commanders.com"}
def clean(x):return html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',x))).strip()
# tolerant labels: KR, KOR, K/R, K-R, "Kick Return", "Kickoff Returner(s)", "KR/PR" counts for both
KR=re.compile(r'^(K\s*O?\s*[/-]?\s*R\b|KICK\s*(OFF\s*)?RET\w*)',re.I)
PR=re.compile(r'^(P\s*[/-]?\s*R\b|PUNT\s*RET\w*)',re.I)
BOTH=re.compile(r'^(KR\s*/\s*PR|PR\s*/\s*KR|RETURNERS?|RET)\b',re.I)
POSROW=re.compile(r'^(QB|RB|WR|TE|LT|LG|C|RG|RT|DE|DT|LB|CB|S|FS|SS|K|P|LS|H)\b')
MON='(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\\.?'
ASOF=[re.compile(p,re.I) for p in (rf'(?:updated|as of|effective)[:\s]*({MON}\s+\d{{1,2}},?\s+\d{{4}})',r'(?:updated|as of|effective)[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})',
      rf'(?:unofficial)[^<]{{0,40}}?({MON}\s+\d{{1,2}},?\s+\d{{4}})',r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})',r'(Week\s+\d+)\s+(?:unofficial\s+)?depth chart')]
def names_of(cells):
    out=[]
    for t in cells:
        n=re.sub(r'^\d+\s+','',t).strip(' ,*-–—')                      # jersey numbers, stray punctuation
        n=re.sub(r'\s*\((?:inj|ir|q|out|susp|pup|nfi)[^)]*\)\s*$','',n,flags=re.I).strip()
        if n and not re.fullmatch(r'[-–—\s]*',n): out.append(n)
    return out[:3]
def one(ab):
    u=f"https://www.{SITES[ab]}/team/depth-chart"
    try:
        h=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=40).read().decode('utf-8','ignore')
    except Exception as e: return ab,{"url":u,"status":"unread","reason":f"page fetch failed: {str(e)[:80]}"}
    out={"url":u}
    for rx in ASOF:
        m=rx.search(h)
        if m: out["asof"]=m.group(1).strip();break
    rows=[]
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',h,re.S):
        tds=[clean(t) for t in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',tr,re.S)]
        tds=[t for t in tds if t]
        if tds: rows.append(tds)
    if not rows:
        out["status"]="no_chart";out["reason"]="page loads but has no depth chart table";return ab,out
    if not any(POSROW.match(r[0]) for r in rows):
        out["status"]="unread";out["reason"]=f"{len(rows)} table rows but none look like positions";return ab,out
    for r in rows:
        lab=r[0]
        for key,rx in (("KR",KR),("PR",PR)):
            if key not in out and (rx.match(lab) or BOTH.match(lab)):
                ns=names_of(r[1:])
                if ns: out[key]=ns;out[key+"_label"]=lab
    out["status"]="ok" if out.get("KR") else "no_kr_row"
    if out["status"]=="no_kr_row": out["reason"]="depth chart read; no kick-return row"
    out["PR_status"]="ok" if out.get("PR") else "no_pr_row"
    if out["PR_status"]=="no_pr_row": out["PR_reason"]="depth chart read; no punt-return row (labels tried: PR, P/R, Punt Return*, KR/PR, Returner)"
    return ab,out
res={}
with cf.ThreadPoolExecutor(8) as ex:
    for ab,o in ex.map(one,SITES): res[ab]=o
res["_checked"]=datetime.date.today().isoformat()
json.dump(res,open('team_sites.json','w'),indent=0)
from collections import Counter
print('KR',Counter(o["status"] for k,o in res.items() if k[0]!='_'),'PR',Counter(o.get("PR_status",o["status"]) for k,o in res.items() if k[0]!='_'))
for ab in sorted(SITES):
    o=res[ab]
    if o.get("PR_status")!="ok" or o.get("PR_label") not in ("PR",): print(f"{ab:4} PR {o.get('PR_status',o['status']):9} {o.get('PR_label','')} {o.get('PR','')} {o.get('PR_reason',o.get('reason',''))}")
    if o["status"]!="ok" or o.get("KR_label") not in ("KR",): print(f"{ab:4} {o['status']:9} {o.get('KR_label','')} {o.get('KR','')} {o.get('reason','')} asof={o.get('asof')}")
