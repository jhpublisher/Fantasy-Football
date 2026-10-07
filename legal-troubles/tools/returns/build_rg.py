import sys,os
HERE=os.path.dirname(os.path.abspath(__file__))
INP,OUT,MODE=sys.argv[1],sys.argv[2],sys.argv[3]   # MODE: mock | github | claude
s=open(INP,encoding='utf-8').read()
# Output is always a complete page: keep the input's skeleton (doctype, charset, viewport, [hidden] rule) or add the standard one.
SKEL_HEAD='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
'''
SKEL_TAIL='\n</body></html>\n'
if s.lstrip().lower().startswith('<!doctype') or '<body>' in s[:2000]:
    HEAD,TAIL=s[:s.index('<title>')],s[s.rindex('</body>'):]
    s=s[s.index('<title>'):s.rindex('</body>')]
else: HEAD,TAIL=SKEL_HEAD,SKEL_TAIL
if '[hidden]{display:none!important}' not in HEAD.replace(' ',''):
    HEAD=HEAD.replace('</head>','<style>[hidden]{display:none!important}</style></head>',1) if '</head>' in HEAD else SKEL_HEAD
def rep(a,b):
    global s
    assert s.count(a)==1,(s.count(a),a[:80]); s=s.replace(a,b)
rep('''<button class="tab" role="tab" id="tab-roster"''','''<button class="tab" role="tab" id="tab-returns" aria-selected="false" data-v="returns">Returns</button>
      <button class="tab" role="tab" id="tab-roster"''')
rep(".heat td.h{",""".rg-ok{color:var(--good)} .rg-warn{color:var(--warn)} .rg-bad{color:var(--bad)} .rg-muted{color:var(--muted)}
.rgcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.rgcard{border:1px solid var(--line);border-left:4px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;gap:6px;background:var(--surface)}
.rgcard.rg-b-ok{border-left-color:var(--good)} .rgcard.rg-b-warn{border-left-color:var(--warn)} .rgcard.rg-b-bad{border-left-color:var(--bad)}
.rgrow{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center;font-size:.88rem}
.rgw{display:inline-flex;gap:3px}
.rgw i{font-style:normal;font-family:var(--mono);font-size:.7rem;min-width:34px;text-align:center;padding:2px 3px;border-radius:4px;background:var(--sunk);color:var(--muted)}
.rgw i.hi{background:color-mix(in srgb,var(--good) 30%,transparent);color:var(--ink);font-weight:700}
.rgw i.lo{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--ink)}
td.rgcell{font-size:.82rem;white-space:normal;min-width:120px}
.rgtools{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.rgcolw{position:relative;display:flex;justify-content:flex-end;margin-left:auto}
.rgcolbtn{font:inherit;font-size:.82rem;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;padding:5px 12px;cursor:pointer;display:inline-flex;gap:8px;align-items:center}
.rgcolbtn i{font-style:normal;color:var(--muted)}
.rgcolpanel{position:absolute;right:0;top:calc(100% + 6px);z-index:6;background:var(--surface);border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 24px color-mix(in srgb,var(--ink) 18%,transparent);padding:12px 14px;display:grid;gap:8px;min-width:260px;max-width:calc(100vw - 40px)}
.rgcolpanel label{display:flex;gap:8px;align-items:center;font-size:.88rem;cursor:pointer}
.rgcolpanel input{accent-color:var(--brass);width:16px;height:16px}
.rgcolact{display:flex;gap:14px;align-items:center;justify-content:flex-end;border-top:1px solid var(--line);padding-top:8px}
.rgl{font-family:var(--mono);font-size:.72rem;padding:1px 6px;border-radius:4px;background:var(--sunk);color:var(--muted);margin-left:2px}
.heat td.h{""")
s=s.replace("const v={overview,league,roster,market,news:newsView,notes:notesView}[S.view]","const v={overview,returns:returnsView,league,roster,market,news:newsView,notes:notesView}[S.view]")
assert 'returns:returnsView' in s
s=s.replace("['overview','league','roster','market','news','notes'].includes(v)","['overview','returns','league','roster','market','news','notes'].includes(v)")
rep("document.addEventListener('click',e=>{if(e.target.closest('select'))return;","""document.addEventListener('click',e=>{if(e.target.closest('select'))return;
  const rf=e.target.closest('[data-rf]');if(rf){RF.k=rf.dataset.rf;RF.n=25;return render()}
  const rk=e.target.closest('[data-rk]');if(rk){RF.kind=rk.dataset.rk;RF.n=25;try{localStorage.setItem('lt-rg-kind',RF.kind)}catch(x){}return render()}
  if(e.target.closest('[data-rmore]')){RF.n=999;return render()}
  if(e.target.closest('[data-rmine]')){RF.mine=!RF.mine;try{localStorage.setItem('lt-rg-mine',RF.mine?'1':'0')}catch(x){}return render()}
  const rgo=e.target.closest('[data-rgopp]');if(rgo){e.stopPropagation();return openRgOpp(rgo.dataset.rgopp)}
  if(e.target.closest('[data-rgcolopen]')){RG_COLOPEN=!RG_COLOPEN;return render()}
  if(e.target.closest('[data-rgcolall]')){RG_HIDE=new Set();try{localStorage.setItem('lt-rg-hide','[]')}catch(x){}return render()}
  if(e.target.closest('[data-rgcoldef]')){RG_HIDE=new Set(RG_COLS.filter(c=>c.off).map(c=>c.k));try{localStorage.removeItem('lt-rg-hide')}catch(x){}return render()}
  if(RG_COLOPEN&&!e.target.closest('.rgcolw')&&document.querySelector('.rgcolpanel')){RG_COLOPEN=false;render()}
  const rgc=e.target.closest('[data-rgcol]');if(rgc){const k=rgc.dataset.rgcol;RG_HIDE.has(k)?RG_HIDE.delete(k):RG_HIDE.add(k);try{localStorage.setItem('lt-rg-hide',JSON.stringify([...RG_HIDE]))}catch(x){}return render()}
  const rgp=e.target.closest('[data-rgplayer]');if(rgp&&!e.target.closest('a,button')){return openRgPlayer(rgp.dataset.rgplayer)}
  const rgt=e.target.closest('[data-rgteam]');if(rgt){return openRgTeam(rgt.dataset.rgteam)}""")
rep("if(e.key==='Enter'&&e.target.matches('tr.row')){const t=e.target;t.dataset.player?openPlayer(t.dataset.player):openTeam(t.dataset.team)}",
    "if(e.key==='Enter'&&e.target.matches('tr.row')){const t=e.target;t.dataset.rgplayer?openRgPlayer(t.dataset.rgplayer):t.dataset.rgteam?openRgTeam(t.dataset.rgteam):t.dataset.player?openPlayer(t.dataset.player):openTeam(t.dataset.team)}")
rep("const SORT_DEF={sr:{k:'seed',d:1},","const SORT_DEF={rp:{k:'pts3',d:-1},sr:{k:'seed',d:1},")
rep("s.d=(['seed','name','line','pos','player','nfl','plan','bye','pri','drop','rank','team','need','ord'].includes(k)","s.d=(['seed','name','line','pos','player','nfl','plan','bye','pri','drop','rank','team','need','ord','owner','site','espn'].includes(k)")
rep("function datesStrip(){",open(os.path.join(HERE,'returns_tab.js'),encoding='utf-8').read()+"\nfunction datesStrip(){")
if MODE=='mock':
    rep("    try{const r=await fetch('data/bundle.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const b=await r.json();","    try{const b=window.__BUNDLE;")
    rep("S.raw=b.players||{};","S.raw=b.players||{};S.returns=window.__RET;")
    # the github page also reads b.returns; in the mock the embedded returns.json must win
    s=s.replace("S.returns=b.returns?.current||S.returns||null","S.returns=window.__RET||b.returns?.current||null")
    rep("  await load(); setInterval(load,10*60*1000);","  await load();")
    s=s.replace('<header class="top">','<div style="background:var(--ink);color:var(--bg);font-family:var(--mono);font-size:.74rem;padding:7px 20px;text-align:center">MOCK · Returns tab (kick + punt returns) · real ESPN data · nothing here changes the live dashboard</div>\n<header class="top">',1)
    B=open(os.environ.get('RG_BUNDLE','bundle.json')).read();RT=open(os.environ.get('RG_RETURNS','returns.json')).read()
    s=s.replace('<script>\n(function(){','<script>window.__BUNDLE='+B.replace('</','<\\/')+';window.__RET='+RT.replace('</','<\\/')+';</script>\n<script>\n(function(){',1)
    s=s.replace("<title>Legal Troubles Front Office BI</title>","<title>Legal Troubles Returns Mock</title>")
    s=s.replace("let v=localStorage","let v=localStorage")
elif MODE=='github':
    rep("S.raw=b.players||{};","S.raw=b.players||{};S.returns=b.returns?.current||null;")
else:
    rep("  db.doc('practice/current').onSnapshot(","  db.doc('returns/current').onSnapshot(s=>{S.returns=s.exists?s.data():null;soon()},err);\n  db.doc('practice/current').onSnapshot(")
s=HEAD+s+TAIL
assert s.lstrip().lower().startswith('<!doctype html>') and '[hidden]{display:none!important}' in s and s.rstrip().endswith('</html>')
open(OUT,'w',encoding='utf-8').write(s);print('ok',MODE,len(s))
