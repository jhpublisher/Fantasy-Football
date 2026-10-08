# Derive the GitHub Pages dashboard (index.html, reads data/bundle.json) from the fixed claude.ai source, so the two never drift.
import sys,re
SRC,OUT=sys.argv[1],sys.argv[2]
s=open(SRC,encoding='utf-8').read()
def rep(a,b):
    global s
    assert s.count(a)==1,(s.count(a),a[:100]); s=s.replace(a,b)
rep('<div class="brand"><h1>Legal Troubles <span>BI</span></h1><span class="eyebrow" id="stamp">Loading data…</span></div>',
    '<div class="brand"><h1>Legal Troubles <span>BI</span></h1><span class="eyebrow"><a href="briefing.html" style="color:var(--brass);font-weight:600;margin-right:12px">CEO Briefing →</a><span id="stamp">Loading data…</span></span></div>')
NEW="(async()=>{\n  let db=null;" in s   # newer page (Oct 7): db listeners report their own errors; punting loaded separately
a=s.index("  let db=null;\n  try{db=window.claude") if NEW else s.index("  const db=window.claude?await window.claude.use('db'):null;");b=s.index("})();\n})();\n</script>")
s=s[:a]+"""  async function load(){
    try{const r=await fetch('data/bundle.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const b=await r.json();
      S.meta=b.meta;S.odds=b.odds||{};S.scores=b.scores||{};S.raw=b.players||{};S.extras=b.extras?.current||null;S.waivers=b.waivers;S.news=b.news||{};S.practice=b.practice;S.memos=b.memos||{};
      S.league=b.league||b.meta?.league||b.extras?.current?.league||null;S.validation=b.validation||null;S.sections=b.sections||null;S.builtAt=b.builtAt||null;S.returns=b.returns?.current||S.returns||null;S.loadError=null;S.dbError=null;S.dbErrors={};S.dbWait=null;
      try{const pr=await fetch('data/punting.json?t='+Date.now(),{cache:'no-store'});S.punting=pr.ok?await pr.json():S.punting||null}catch(e){}
      try{const sr=await fetch('data/schedule.json?t='+Date.now(),{cache:'no-store'});S.sched=sr.ok?await sr.json():S.sched||null}catch(e){}
      // data/validation.json is written every run, even when a run was blocked, so it can be newer than bundle.validation
      try{const v=await fetch('data/validation.json?t='+Date.now(),{cache:'no-store'});if(v.ok){const V=await v.json();if(!S.validation||!S.validation.checkedAt||(V.checkedAt&&new Date(V.checkedAt)>=new Date(S.validation.checkedAt)))S.validation=V}}catch(e){}
      render();}
    catch(e){if(!S.meta){$('#view').innerHTML=`<div class="empty">Couldn't load data/bundle.json (${esc(e.message||e)}). The refresh may not have published yet; this page retries every 10 minutes.</div>`;$('#stamp').textContent='Offline'}else{S.loadError=String(e.message||e);render()}}
  }
  try{S.plans=JSON.parse(localStorage.getItem('lt-plans')||'{}')}catch(e){S.plans={}}
  savePlan=async()=>{try{localStorage.setItem('lt-plans',JSON.stringify(S.plans))}catch(e){}};
  await load(); setInterval(load,10*60*1000);
"""+s[b:]
HEAD0='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
'''
if not s.lstrip().lower().startswith('<!doctype'): s=HEAD0+s+'\n</body></html>\n'
open(OUT,'w',encoding='utf-8').write(s);print('ok',len(s))
