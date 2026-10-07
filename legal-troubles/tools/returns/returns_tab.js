/* ---------- Returns tab (Return Game department): Kick / Punt / Both ---------- */
// One normalized model per kind so every section renders the same way for kick returns, punt returns, or both combined.
const RF={k:'elig',open:null,n:25,kind:'kr',mine:false};
try{RF.mine=localStorage.getItem('lt-rg-mine')==='1'}catch(e){}
try{const v=localStorage.getItem('lt-rg-kind');if(['kr','pr','both'].includes(v))RF.kind=v}catch(e){}
SORT_DEF.rt={k:'team',d:1};SORT.rt={k:'team',d:1};
if(typeof ASC!=='undefined')['site1','espn1','agree','site','espn','opp','lastg'].forEach(k=>ASC.add(k));
const rgMin=o=>{const v=Object.values(o||{}).filter(x=>x!=null);return v.length?Math.min(...v):null};
const RG_KIND={kr:{L:'KR',noun:'kick returns',one:'kick returner',short:'kick'},pr:{L:'PR',noun:'punt returns',one:'punt returner',short:'punt'},both:{L:'KR+PR',noun:'kick and punt returns',one:'returner',short:'return'}};
// Same normalization as fill_rg.py: accents, punctuation and Jr./Sr./II/III/IV/V ignored ("Brian Robinson" == "Brian Robinson Jr.")
const rgNorm=s=>String(s||'').normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[.'’`,-]/g,' ').replace(/\b(jr|sr|ii|iii|iv|v)\b/g,' ').replace(/[^a-z]/g,'');
const rgLast=n=>{const w=String(n||'').split(' ').filter(x=>!/^(jr|sr|ii|iii|iv|v)\.?$/i.test(x));return w[w.length-1]||String(n||'Unknown')};
const rgSame=(a,b)=>!!a&&!!b&&rgNorm(a)===rgNorm(b);
const rgIdx=(list,n)=>{const k=rgNorm(n);return (list||[]).findIndex(x=>rgNorm(x)===k)};
// a source "read" a team when its status is ok or no_kr_row / no_pr_row (read, nobody listed)
const rgRead=s=>!!s&&(s.status==='ok'||s.status==='no_kr_row'||s.status==='no_pr_row'||(!s.status&&(s.list||[]).length>0));
const rgKey=p=>p.id?'i'+p.id:p.team+':'+rgNorm(p.name);
// this week's opponent (schedule from fill_rg.py: whole season stored, only currentWeek shown)
const rgWk=()=>S.returns?.currentWeek;
function rgOpp(t){const R=S.returns,w=R?.currentWeek;if(!R?.schedule)return {txt:'Schedule not in this refresh',key:null,miss:true};
  const g=R.schedule[t]?.[String(w)];if(!g)return {txt:`No Wk ${w} game found for ${t}`,key:null,miss:true};if(g.bye)return {txt:'Bye',key:null,bye:true};
  let when='';try{when=new Date(g.kickoff).toLocaleString('en-US',{weekday:'short',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' ET'}catch(e){when='Kickoff time unknown'}
  return {txt:`${g.home?'vs':'@'} ${g.opp}`,key:g.opp,when,home:g.home}}
const rgOppHtml=(t,noTime)=>{const o=rgOpp(t);return o.bye?'<span class="chip rg-bad">Bye</span>':o.miss?`<span class="chip rg-bad">${esc(o.txt)}</span>`:noTime?`<b>${esc(o.txt)}</b>`:`<b>${esc(o.txt)}</b> <span class="note">${esc(o.when)}</span>`};
/* ---- model: {kind, kinds:['kr'] | ['pr'] | ['kr','pr'], W, teams:{t:{byes, weeks:{w:{bye,opp,n,y,fc,ret:[{p,n,y,td,fc,kr,pr}]}}, src:{site:{kr,pr}, espn:{kr,pr}}}}, players:[{name,id,team,pos,owner,wk:{w:{n,y,td,fc,pts,team_n,team_fc,kr,pr}}}]} ---- */
function rgSrc(s,list,kind){if(!s)return null;return {list:(list||[]).filter(Boolean),status:s.status,reason:s.reason,url:s.url,asof:s.asof,label:s.label,kind}}
function rgSingle(R,kind){const W=R.weeks||[],teams={};
  for(const [t,x] of Object.entries(R.teams||{})){const k=kind==='kr'?x:x.pr;if(!k)return {error:`team ${t} has no punt-return data`};const weeks={};
    for(const w of W){const g=k.weeks?.[w];if(!g){weeks[w]=null;continue}
      if(g.bye){weeks[w]={bye:true,opp:'Bye',n:0,y:0,fc:0,ret:[]};continue}
      const n=kind==='kr'?g.team_kr:g.team_pr;
      weeks[w]={opp:g.opp,n:n??0,y:(g.ret||[]).reduce((a,r)=>a+(r.y||0),0),fc:kind==='pr'?(g.fc??null):0,fcReason:g.fcReason,
        ret:(g.ret||[]).map(r=>({p:r.p,n:kind==='kr'?r.kr:r.pr,y:r.y,td:r.td,fc:kind==='pr'?(r.fc??0):0,kr:kind==='kr'?r.kr:0,pr:kind==='pr'?r.pr:0}))}}
    teams[t]={byes:x.byes||[],weeks,src:{site:{[kind]:rgSrc(k.site,k.site?.[kind],kind)},espn:{[kind]:rgSrc(k.espn,k.espn?.[kind],kind)}}}}
  const raw=kind==='kr'?R.players:R.pr?.players;
  const players=(Array.isArray(raw)?raw:[]).filter(p=>p&&p.name).map(p=>{const wk={};
    for(const [w,x] of Object.entries(p.wk&&typeof p.wk==='object'?p.wk:{})){const n=kind==='kr'?x.kr:x.pr,tn=kind==='kr'?x.team_kr:x.team_pr,tfc=kind==='pr'?(teams[p.team]?.weeks?.[w]?.fc??null):0;
      wk[w]={n:n||0,y:x.y||0,td:x.td||0,fc:kind==='pr'?(x.fc??null):0,pts:x.pts||0,team_n:tn||0,team_fc:tfc,kr:kind==='kr'?n||0:0,pr:kind==='pr'?n||0:0,ptsK:kind==='kr'?x.pts||0:0,ptsP:kind==='pr'?x.pts||0:0}}
    return {name:p.name,id:p.id,team:p.team||'NFL team n/a',pos:p.pos||'Pos. n/a',owner:p.owner||'Owner unknown',wk}});
  return {kind,kinds:[kind],W,teams,players}}
function rgBoth(K,P){const W=K.W,teams={};
  for(const t of Object.keys(K.teams)){const a=K.teams[t],b=P.teams[t]||{weeks:{},src:{site:{},espn:{}}},weeks={};
    for(const w of W){const x=a.weeks[w],y=b.weeks?.[w];if(!x&&!y){weeks[w]=null;continue}if(x?.bye||y?.bye){weeks[w]={bye:true,opp:'Bye',n:0,y:0,fc:0,ret:[]};continue}
      const m=new Map();for(const r of [...(x?.ret||[]),...(y?.ret||[])]){const k=rgNorm(r.p),o=m.get(k)||{p:r.p,n:0,y:0,td:0,fc:0,kr:0,pr:0};o.n+=r.n;o.y+=r.y;o.td+=r.td;o.fc+=r.fc||0;o.kr+=r.kr;o.pr+=r.pr;m.set(k,o)}
      weeks[w]={opp:(x||y).opp,n:(x?.n||0)+(y?.n||0),nK:x?.n||0,nP:y?.n||0,y:(x?.y||0)+(y?.y||0),fc:y?.fc??null,fcReason:y?.fcReason,ret:[...m.values()].sort((p,q)=>q.n-p.n)}}
    teams[t]={byes:a.byes,weeks,src:{site:{kr:a.src.site.kr,pr:b.src.site.pr},espn:{kr:a.src.espn.kr,pr:b.src.espn.pr}}}}
  const by=new Map();
  for(const p of [...K.players,...P.players]){const k=rgKey(p),q=by.get(k)||by.get(p.team+':'+rgNorm(p.name));
    if(!q){const c={...p,wk:{}};for(const [w,x] of Object.entries(p.wk))c.wk[w]={...x};by.set(k,c);by.set(p.team+':'+rgNorm(p.name),c);continue}
    if(q.owner==='Owner unknown'||q.owner==='No ESPN id match')q.owner=p.owner;
    for(const [w,x] of Object.entries(p.wk)){const o=q.wk[w];if(!o){q.wk[w]={...x};continue}
      q.wk[w]={n:o.n+x.n,y:o.y+x.y,td:o.td+x.td,fc:(o.fc??0)+(x.fc??0),pts:+(o.pts+x.pts).toFixed(1),team_n:o.team_n+x.team_n,team_fc:(o.team_fc??0)+(x.team_fc??0),kr:o.kr+x.kr,pr:o.pr+x.pr,ptsK:o.ptsK+x.ptsK,ptsP:o.ptsP+x.ptsP}}}
  // team_n for weeks where the player only appears in one kind: use the combined team total
  const players=[...new Set(by.values())];
  for(const p of players)for(const [w,x] of Object.entries(p.wk)){const g=teams[p.team]?.weeks?.[w];if(g&&!g.bye){x.team_n=g.n;x.team_fc=g.fc}}
  return {kind:'both',kinds:['kr','pr'],W,teams,players}}
function rgModel(kind){const R=S.returns;if(!R)return null;
  if(kind==='kr')return rgSingle(R,'kr');
  if(!R.pr||!Array.isArray(R.pr.players))return {error:'Punt returns are not in this refresh (the return data was built before punt tracking started). Ask Rich to re-run the returns refresh.'};
  const P=rgSingle(R,'pr');if(P.error||kind==='pr')return P;
  const K=rgSingle(R,'kr');return K.error?K:rgBoth(K,P)}
const rgBye=(M_,t,w)=>!!M_.teams[t]?.weeks?.[w]?.bye||(M_.teams[t]?.byes||[]).includes(+w);
// fielded share: punts = returns + fair catches (a fair catch still means he held the job)
function rgShare(x,kind){if(!x)return 0;if(kind==='kr')return x.team_n?x.n/x.team_n:0;const f=x.fc??0,tf=x.team_fc??0,d=x.team_n+tf;return d?(x.n+f)/d:0}
function rgRows(M_){const W=M_.W,ours=new Set(Object.values(S.players).filter(p=>p.ours).map(p=>rgNorm(p.name)));
  return M_.players.map(p=>{const wk=W.map(w=>p.wk[w]||null);
    const played=W.filter(w=>!rgBye(M_,p.team,w)),last3=played.slice(-3);   // byes never count as a 0
    const avg=f=>last3.length?last3.reduce((a,w)=>a+f(p.wk[w],w),0)/last3.length:0;
    const pts3=avg(x=>x?x.pts:0),sh3=avg(x=>rgShare(x,M_.kind));
    const fc3=M_.kind==='kr'?null:last3.some(w=>(M_.teams[p.team]?.weeks?.[w]?.fc)==null)?null:last3.reduce((a,w)=>a+(p.wk[w]?.fc??0),0);
    const t=M_.teams[p.team]||{src:{site:{},espn:{}}};
    const rank=src=>{const o={};for(const k of M_.kinds){const i=rgIdx(t.src[src]?.[k]?.list,p.name);o[k]=i<0?null:i+1}return o};
    const site=rank('site'),espn=rank('espn'),minR=rgMin;
    const LW=played[played.length-1],lw=LW!=null?p.wk[LW]:null,g=LW!=null?t.weeks?.[LW]:null;
    const lwTxt=LW==null?'no games yet':lw?`${lw.n}/${lw.team_n}${M_.kind!=='kr'&&lw.fc?` +${lw.fc} FC`:''}`:`0/${g?.n??0}`;
    const tot=+(wk.reduce((a,x)=>a+(x?x.pts:0),0)).toFixed(1);
    return {...p,ours:ours.has(rgNorm(p.name)),wkA:wk,n3:last3.length,lastW:LW,lwSh:lw?Math.round(rgShare(lw,M_.kind)*100):0,lwPts:lw?lw.pts:0,lwTxt,pts3:+pts3.toFixed(1),sh3:Math.round(sh3*100),fc3,
      tot,totK:+(wk.reduce((a,x)=>a+(x?x.ptsK||0:0),0)).toFixed(1),totP:+(wk.reduce((a,x)=>a+(x?x.ptsP||0:0),0)).toFixed(1),site,espn,siteMin:minR(site),espnMin:minR(espn),elig:['RB','WR'].includes(p.pos)}})}
// status for one kind (row computed on that kind's model)
function rgStatus1(p,M_,k){const L=RG_KIND[k].L,t=M_.teams[p.team]||{src:{site:{},espn:{}}},ss=t.src.site[k],es=t.src.espn[k],siteRead=rgRead(ss),espnRead=rgRead(es),sr=p.site[k],er=p.espn[k];
  if(!siteRead&&espnRead){   // only one source could be read: say so, never "disagree"
    if(er===1)return[p.sh3>=60?'ok':'warn',p.sh3>=60?`${L}1 (ESPN only), full-time`:`${L}1 (ESPN only), sharing`];
    return er?['muted',`${L}${er} (ESPN only)`]:['bad','Not on ESPN chart (no team chart)']}
  if(siteRead&&!espnRead){
    if(sr===1)return[p.sh3>=60?'ok':'warn',`${L}1 (team site only)`];
    return sr?['muted',`${L}${sr} (team site only)`]:['bad','Not on team chart (ESPN unread)']}
  if(!siteRead&&!espnRead)return['bad','No depth chart could be read'];
  const both=sr===1&&er===1,one=sr===1||er===1;
  if(both&&p.sh3>=60)return['ok',`Full-time ${RG_KIND[k].one}`];
  if(both)return['warn',`Listed ${L}1, sharing`];
  if(one)return['warn',`${L}: sources disagree`];
  if(sr||er)return['muted',`${L} backup on depth chart`];
  return['bad',`Not on the ${L} depth chart`]}
const rgChip=([c,t])=>`<span class="chip rg-${c}">${esc(t)}</span>`;
// rank cell: listed / read-but-not-listed / verified no chart / couldn't read (reason)
function rgSrcNote(s,src){if(!s)return `<span class="chip rg-bad" title="No ${src} data in this refresh">Not checked</span>`;
  if(s.status==='no_chart')return `<span class="note" title="${esc(s.reason||'')}">Team publishes no chart</span>`;
  if(s.status==='unread'||s.status==='error')return `<span class="chip rg-bad" title="${esc(s.reason||'')}">Couldn't read${s.reason?': '+esc(s.reason):''}</span>`;
  return null}
function rgRank(M_,p,src){const t=M_.teams[p.team]||{src:{site:{},espn:{}}},nm=src==='site'?'team site':'ESPN';
  const one=k=>{const r=p[src][k],s=t.src[src]?.[k],L=RG_KIND[k].L;return r?`<b>${L}${r}</b>`:(rgSrcNote(s,nm)||`<span class="note">${M_.kinds.length>1?L+' not listed':'Not listed'}</span>`)};
  if(M_.kinds.length===1)return one(M_.kinds[0]);
  const ks=M_.kinds,a=ks.map(k=>t.src[src]?.[k]);if(a.every(s=>s&&s.status==='no_chart'))return rgSrcNote(a[0],nm);
  return ks.map(one).join(' · ')}
function rgWeeks(M_,p){return `<span class="rgw">${M_.W.map((w,i)=>{if(rgBye(M_,p.team,w))return `<i title="Wk ${w}: bye (not counted in averages)">Bye</i>`;
  const x=p.wkA[i],g=M_.teams[p.team]?.weeks?.[w],n=g?.n??0,fcT=M_.kind!=='kr'&&x?.fc?` + ${x.fc} fair catch${x.fc>1?'es':''}`:'';
  const det=M_.kind==='both'&&x?` (${x.kr} KR, ${x.pr} PR)`:'';
  return `<i class="${x?(rgShare(x,M_.kind)>=.6?'hi':'lo'):''}" title="Wk ${w}: ${x?`${x.n} of ${x.team_n} returns${det}${fcT}, ${x.y} yds, ${x.pts} pts`:`0 of the team's ${n} returns`}">${x?x.n+'/'+x.team_n:'0/'+n}</i>`}).join('')}</span>`}
function rgList(M_,t,src){const nm=src==='site'?'team site':'ESPN',one=(k,lab)=>{const s=M_.teams[t].src[src]?.[k],l=(s?.list||[]).filter(Boolean);
    const body=l.length?l.map((n,i)=>i?esc(n):`<b>${esc(n)}</b>`).join(' / '):(rgSrcNote(s,nm)||`<span class="note">Chart read; no ${RG_KIND[k].L} listed</span>`);return lab?`<div><span class="dim">${RG_KIND[k].L}</span> ${body}</div>`:body};
  if(M_.kinds.length===1)return one(M_.kinds[0]);
  const a=M_.kinds.map(k=>M_.teams[t].src[src]?.[k]);if(a.every(s=>s&&s.status==='no_chart'))return rgSrcNote(a[0],nm);
  return M_.kinds.map(k=>one(k,true)).join('')}
function rgAgree1(M_,t,k){const s=M_.teams[t].src.site[k],e=M_.teams[t].src.espn[k],sr=rgRead(s),er=rgRead(e),a=s?.list?.[0],b=e?.list?.[0];
  if(!sr&&er)return[3,'<span class="note">ESPN only</span>'];if(sr&&!er)return[3,'<span class="note">Team site only</span>'];if(!sr&&!er)return[5,'<span class="chip rg-bad">Neither read</span>'];
  if(!a||!b)return[4,`<span class="note">${!a&&!b?`Neither lists a ${RG_KIND[k].L}`:!a?`Only ESPN lists a ${RG_KIND[k].L}`:`Only team site lists a ${RG_KIND[k].L}`}</span>`];
  return rgSame(a,b)?[0,'<span class="chip rg-ok">Yes</span>']:[1,'<span class="chip rg-warn">No</span>']}
function rgAgree(M_,t){const r=M_.kinds.map(k=>[k,...rgAgree1(M_,t,k)]);return [r.reduce((a,x)=>a+x[1],0),r.length===1?r[0][2]:r.map(([k,,h])=>`<div><span class="dim">${RG_KIND[k].L}</span> ${h}</div>`).join('')]}
function rgCell(M_,g){if(!g)return '<span class="note">No game data</span>';if(g.bye)return '<span class="note">Bye</span>';
  const fcN=M_.kind!=='kr'&&g.fc!=null?g.fc:null;
  const who=g.ret.filter(r=>r.n||r.fc).map(r=>{const b=M_.kind==='both'?[r.kr?`${r.kr} KR`:'',r.pr?`${r.pr} PR`:''].filter(Boolean).join(' · '):`${r.n}/${g.n}`;return `${esc(rgLast(r.p))} ${b||'0 returns'}${M_.kind!=='kr'&&r.fc?` (${r.fc} FC)`:''}`}).join(', ');
  const none=M_.kind==='pr'?`0 returns${fcN?` · ${fcN} fair catch${fcN>1?'es':''}`:''}`:'0 returns';
  return (who||`<span class="note">${none}</span>`)+(M_.kind!=='kr'&&g.fc==null?` <span class="note" title="${esc(g.fcReason||'')}">(fair catches unknown)</span>`:'')}
function rgToggle(){return `<div class="filters rgkind" role="group" aria-label="Return type">${[['kr','Kick returns'],['pr','Punt returns'],['both','Both']].map(([k,l])=>`<button data-rk="${k}" aria-pressed="${RF.kind===k}">${l}</button>`).join('')}</div>`}
function returnsView(){const R=S.returns;if(!R)return `<div class="empty">No return data loaded: the Returns refresh has not run or failed. Ask Rich to re-run box.py and fill_rg.py.</div>`;
  if(R.error)return `<div class="empty">Return data failed to load: ${esc(R.error)}</div>`;
  if(!R.teams||typeof R.teams!=='object'||!Object.keys(R.teams).length)return `<div class="empty">Return data has no team table in this refresh${R.stale?' (stale copy)':''}; ask Rich to re-run fill_rg.py.</div>`;
  const W=R.weeks||[];if(!W.length)return `<div class="empty">No completed NFL weeks yet; returns fill in after Week 1.</div>`;
  const M_=rgModel(RF.kind);if(!M_||M_.error)return `<section class="panel"><div class="ph"><h2>Returns</h2>${rgToggle()}</div><div class="secmsg err">${esc(M_?.error||'No return data')}</div></section>`;
  const K=RG_KIND[RF.kind],L=K.L,P=rgRows(M_),sc=R.scoring||{krYd:.1,krTd:6};
  const perKind=RF.kind==='both'?Object.fromEntries(['kr','pr'].map(k=>{const m=rgModel(k);return [k,{M:m,rows:rgRows(m)}]})):null;
  const kindRow=(k,p)=>perKind[k].rows.find(q=>rgKey(q)===rgKey(p)||(q.team===p.team&&rgSame(q.name,p.name)));
  const status=p=>RF.kind!=='both'?[rgStatus1(p,M_,RF.kind)]:['kr','pr'].map(k=>{const q=kindRow(k,p);return q&&(q.site[k]||q.espn[k]||q.tot||q.sh3)?rgStatus1(q,perKind[k].M,k):null}).filter(Boolean);
  const ourNames=Object.values(S.players).filter(p=>p.ours).map(p=>p.name);
  const ours=P.filter(p=>p.ours);
  // our players listed on a depth chart but with no returns yet are in the players list already (fill_rg adds depth-only names); this catches any it missed
  ourNames.forEach(n=>{if(ours.some(p=>rgSame(p.name,n)))return;Object.entries(M_.teams).forEach(([tm,t])=>{const site={},espn={};let hit=false;
    for(const k of M_.kinds){const s=rgIdx(t.src.site[k]?.list,n),e=rgIdx(t.src.espn[k]?.list,n);site[k]=s>=0?s+1:null;espn[k]=e>=0?e+1:null;hit=hit||s>=0||e>=0}
    if(hit){const pp=Object.values(S.players).find(p=>p.name===n);ours.push({name:n,team:tm,pos:pp?.pos||'Pos. n/a',ours:true,wk:{},wkA:W.map(()=>null),n3:0,pts3:0,sh3:0,fc3:null,lwSh:0,lwTxt:'0/'+(t.weeks?.[W[W.length-1]]?.n??0),tot:0,totK:0,totP:0,site,espn,siteMin:rgMin(site),espnMin:rgMin(espn),elig:true})}})});
  const filt={elig:p=>p.elig,fa:p=>p.elig&&p.owner==='Free agent',all:()=>true}[RF.k];
  const base=P.filter(filt).sort((a,b)=>b.pts3-a.pts3||b.tot-a.tot), ix=new Map(base.map((p,i)=>[rgKey(p),i]));
  const rpVal=(p,k)=>({player:p.name.toLowerCase(),team:p.team,pts3:p.pts3,sh3:p.sh3,lw:p.lwSh,tot:p.tot,totK:p.totK,totP:p.totP,fc3:p.fc3,site:p.siteMin,espn:p.espnMin,owner:p.owner.toLowerCase(),opp:rgOpp(p.team).key,oppk:rgExp(p).k?.ret3??null,oppy:rgExp(p).k?.yd3??null,exp:rgExp(p).ep??null})[k];
  const rowsF=sortRows(RF.mine?base.filter(p=>!p.ours):base,'rp',rpVal,(a,b)=>ix.get(rgKey(a))-ix.get(rgKey(b)));
  const mineRows=RF.mine?sortRows(P.filter(p=>p.ours),'rp',rpVal,(a,b)=>b.pts3-a.pts3||b.tot-a.tot):[];
  const rows=[...mineRows,...rowsF];
  const teams=Object.keys(M_.teams).sort();
  // disagreement count per kind (both charts read and both list someone)
  const dis=M_.kinds.map(k=>{const both=teams.filter(t=>{const s=M_.teams[t].src.site[k],e=M_.teams[t].src.espn[k];return rgRead(s)&&rgRead(e)&&s.list[0]&&e.list[0]});
    return `${both.filter(t=>!rgSame(M_.teams[t].src.site[k].list[0],M_.teams[t].src.espn[k].list[0])).length} of ${both.length} disagree on ${RG_KIND[k].L}1`}).join(' · ');
  const cant=[],noChart=new Set();
  teams.forEach(t=>M_.kinds.forEach(k=>{for(const src of ['site','espn']){const s=M_.teams[t].src[src]?.[k];if(s?.status==='no_chart')noChart.add(t);else if(!rgRead(s))cant.push(`${t} ${src==='site'?'team site':'ESPN'} ${RG_KIND[k].L} (${s?.reason||'not checked'})`)}}));
  const lastN=Math.min(3,W.length),hasFc=RF.kind!=='kr';
  const teamRows=sortRows(teams,'rt',(t,k)=>{const x=M_.teams[t];if(k==='team')return t;if(k==='opp')return rgOpp(t).key;if(k==='split')return rgSplit(M_,t)?.topS??null;if(k==='lastg'){const sp=rgSplit(M_,t);return sp?.LG.list[0]?.p?.toLowerCase()??null}if(k==='trend')return rgSplit(M_,t)?.changed?1:0;if(k==='chk')return (rgChk(t)?.flags?.length||0);
    const first=src=>{for(const kk of M_.kinds){const n=x.src[src]?.[kk]?.list?.[0];if(n)return n.toLowerCase()}return null};
    if(k==='site1')return first('site');if(k==='espn1')return first('espn');if(k==='agree')return rgAgree(M_,t)[0];
    if(k.startsWith('w')){const g=x.weeks?.[k.slice(1)];return !g||g.bye?null:g.n??null}return null},(a,b)=>a.localeCompare(b));
  const ptsNote=RF.kind==='kr'?`${sc.krYd} per kick-return yard + ${sc.krTd} per return TD`:RF.kind==='pr'?`${sc.prYd??sc.krYd} per punt-return yard + ${sc.prTd??sc.krTd} per return TD`:`${sc.krYd} per kick-return yard and ${sc.prYd??sc.krYd} per punt-return yard + ${sc.krTd} per return TD`;
  const chartWord=RF.kind==='both'?'KR1–KR3 and PR1–PR3':`${L}1–${L}3`;
  return `<section class="panel"><div class="ph"><h2>Return type</h2>${rgToggle()}</div><p class="note">${RF.kind==='kr'?'Kick returns only.':RF.kind==='pr'?'Punt returns only. Fair catches (FC) earn nothing, so they cap a punt returner\'s value; share counts punts he fielded (returns + fair catches).':'Kick and punt returns combined: points, returns and share add both together; tap a week chip for the split.'} League scoring: ${ptsNote}.</p></section>
  <section class="panel"><div class="ph"><h2>Our returners</h2><span class="eyebrow">Is our guy the ${K.one} this week?</span></div>
    ${ours.length?`<div class="rgcards">${ours.map(p=>{const st=status(p),top=st.length?st.reduce((a,b)=>({ok:0,warn:1,muted:2,bad:3}[a[0]]<={ok:0,warn:1,muted:2,bad:3}[b[0]]?a:b)):['muted','Not listed, no returns'];return `<div class="rgcard rg-b-${top[0]}"><div class="ph"><b>${esc(p.name)}</b><span class="chips">${(st.length?st:[top]).map(rgChip).join('')}</span></div>
      <div class="rgrow"><span>Week ${rgWk()}: ${rgOppHtml(p.team)}</span></div>
      ${RF.kind!=='pr'?`<div class="rgrow"><span>Opp kick returns allowed/game (last 3): ${rgOppCell(p)}</span><span>Return yds allowed/game: ${rgYdsCell(p)}</span></div><div class="rgrow"><span>Expected: <b>${rgExpTxt(p)}</b></span></div>`:''}
      ${rgChk(p.team)?.flags?.length?`<div class="rgrow"><span>${rgFlagChips(rgChk(p.team).flags)}</span><span class="note">${esc(rgChk(p.team).flags.map(f=>f[1]).join(' · '))}</span></div>`:''}
      <span class="note">${esc(p.pos||'Pos. n/a')} · ${esc(p.team||'Team n/a')} · Team site ${rgRank(M_,p,'site')} · ESPN ${rgRank(M_,p,'espn')}</span>
      <div class="rgrow"><span>Last game: <b>${p.lwSh}%</b> · Last ${p.n3??lastN} games: <b>${p.sh3}%</b> of ${K.noun}${hasFc?` · <b>${p.fc3??'unknown'}</b> fair catches`:''} · <b>${p.pts3}</b> return pts/game</span>${rgWeeks(M_,p)}</div></div>`}).join('')}</div>`:`<p class="note">None of our players is listed at ${RF.kind==='both'?'kick or punt':K.short} returner or has returned a ${RF.kind==='both'?'kick or punt':K.short} this season.</p>`}
  </section>
  <section class="panel"><div class="ph"><h2>Returner rankings</h2><span class="phr">${resetBtn('rp')}<span class="eyebrow">${K.noun} · ranked by return points per game, last ${lastN} games played · click a column to sort</span></span></div>
    <div class="rgtools"><div class="filters">${[['elig','Startable (RB/WR)'],['fa','Free agents only'],['all','Everyone']].map(([k,l])=>`<button data-rf="${k}" aria-pressed="${RF.k===k}">${l}</button>`).join('')}<button data-rmine="1" aria-pressed="${RF.mine}" title="On: our players pinned to the top, then the filter you picked">My team</button></div>${rgColBar(hasFc)}</div>
    ${rgRankTable(M_,rows,hasFc)}${rows.length>RF.n?`<button class="showmore" data-rmore="1">Show all ${rows.length} returners</button>`:''}<p class="note">Returns by week = his ${K.noun} / team's ${K.noun} (green = 60%+ share${hasFc?' of punts fielded':''}); Bye weeks are skipped, not counted as zero.${hasFc?' Fair catches come from ESPN play-by-play.':''} Team site / ESPN = where each depth chart lists him today (${chartWord}); "Not listed" = chart read and he isn't on it; "Couldn't read" = we failed to read that chart.</p></section>
  <section class="panel"><div class="ph"><h2>All ${teams.length} teams</h2><span class="phr">${resetBtn('rt')}<span class="eyebrow">${dis} · tap a team for history · click a column to sort</span></span></div>
    ${cant.length?`<div class="flag"><b>Charts we couldn't read:</b> ${esc(cant.join('; '))}</div>`:''}
    <div class="tw"><table><thead><tr>${sh('rt','team','Team')}${sh('rt','opp',`Wk ${rgWk()} opponent`)}${sh('rt','split','Split (last 3)',1)}${sh('rt','lastg','Last game')}${sh('rt','trend','Trend')}${sh('rt','chk',`Injury check (wk ${S.returns?.checker?.upcomingWeek??rgWk()})`)}${sh('rt','site1',`Team site ${RF.kind==='both'?'KR / PR':L+'1 / '+L+'2 / '+L+'3'}`)}${sh('rt','espn1',`ESPN ${RF.kind==='both'?'KR / PR':L+'1 / '+L+'2 / '+L+'3'}`)}${sh('rt','agree','Agree?')}${W.map(w=>sh('rt','w'+w,`Wk ${w} returners`)).join('')}</tr></thead><tbody>
    ${teamRows.map(t=>{const x=M_.teams[t];return `<tr class="row" tabindex="0" data-rgteam="${t}"><td><b>${t}</b></td><td>${rgOppHtml(t,true)}</td>${(()=>{const sp=rgSplit(M_,t);return sp?`<td class="rgcell">${rgChip(sp.pat)} ${rgShareTxt(sp.L3)}</td><td class="rgcell">${rgShareTxt(sp.LG)} <span class="note">wk ${sp.lw}</span></td><td>${sp.changed?'<span class="chip rg-warn">Changed</span>':'<span class="note">Steady</span>'}</td>`:'<td class="note">No games</td><td class="note">No games</td><td class="note">No games</td>'})()}<td class="rgcell">${rgChkCell(t)}</td><td class="rgcell">${rgList(M_,t,'site')}</td><td class="rgcell">${rgList(M_,t,'espn')}</td>
      <td>${rgAgree(M_,t)[1]}</td>${W.map(w=>`<td class="rgcell">${rgCell(M_,x.weeks?.[w])}</td>`).join('')}</tr>`}).join('')}
    </tbody></table></div><p class="note">Opponent = Week ${rgWk()} NFL schedule (vs = home, @ = away; kickoff in Eastern). Depth charts checked ${esc(R.checked||'date not recorded')}.${noChart.size?` ${[...noChart].join(', ')} publish${noChart.size===1?'es':''} no depth chart on the team site (verified), so only ESPN counts there.`:''} Weeks shown: ${W[0]}–${W[W.length-1]} (completed weeks only).${hasFc?' FC = fair catches.':''} Which source is more accurate for each team starts scoring once a week of games is played after we begin checking.</p></section>`;
}
function openRgTeam(t){const R=S.returns,M_=rgModel(RF.kind);if(!M_||M_.error||!M_.teams[t])return;const x=M_.teams[t],nm=s=>s==='site'?'team site':'ESPN';
  const cell=(k,src,i)=>{const s=x.src[src]?.[k];return s?.list?.[i]?esc(s.list[i]):(rgSrcNote(s,nm(src))||(i===0?`Chart read; no ${RG_KIND[k].L} listed`:'Not listed'))};
  const link=k=>{const s=x.src.site[k];return s?.url?`<a href="${esc(s.url)}" target="_blank" rel="noopener">Team site</a> (${s.asof?'as of '+esc(s.asof):'site gives no date'}; checked ${esc(R.checked||'date not recorded')})`:'No team site link'};
  const espnUrl=x.src.espn.kr?.url||x.src.espn.pr?.url;
  drawer(`<div class="dh"><div><div class="eyebrow">${esc(RG_KIND[RF.kind].noun)} · ${t}</div><h2 id="dtitle">${t}</h2><div class="note">Week ${rgWk()}: ${rgOppHtml(t)}</div></div><button class="x" aria-label="Close" data-close>×</button></div>
   <section class="panel"><div class="ph"><h2>Depth chart today</h2></div><div class="tw"><table><thead><tr><th>Rank</th><th>Team site</th><th>ESPN</th></tr></thead><tbody>
   ${M_.kinds.map(k=>[0,1,2].map(i=>`<tr><td>${RG_KIND[k].L}${i+1}</td><td>${cell(k,'site',i)}</td><td>${cell(k,'espn',i)}</td></tr>`).join('')).join('')}</tbody></table></div>
   <p class="note">${link(M_.kinds[0])} · ${espnUrl?`<a href="${esc(espnUrl)}" target="_blank" rel="noopener">ESPN</a>`:'No ESPN link'}</p></section>
   ${(()=>{const sp=rgSplit(M_,t);return sp?`<section class="panel"><div class="ph"><h2>Who returns</h2><span class="eyebrow">${esc(RG_KIND[RF.kind].noun)}</span></div><div class="tw"><table><thead><tr><th>Span</th><th>Pattern</th><th>Shares</th></tr></thead><tbody>
     <tr><td>Last game (wk ${sp.lw})</td><td></td><td>${rgShareTxt(sp.LG)}</td></tr><tr><td>Last 3 games</td><td>${rgChip(sp.pat)}</td><td>${rgShareTxt(sp.L3)}</td></tr><tr><td>Season</td><td></td><td>${rgShareTxt(sp.SE)}</td></tr></tbody></table></div>
     ${sp.changed?'<p class="note">Changed: last game\'s leader or share differs from the last 3 games by 30+ points.</p>':''}</section>`:''})()}
   ${rgInjTeam(t)}
   <section class="panel"><div class="ph"><h2>Week by week</h2></div><ul class="list">${M_.W.map(w=>{const g=x.weeks?.[w];if(!g)return `<li><b>Wk ${w}</b> · <span class="note">No game data</span></li>`;if(g.bye)return `<li><b>Wk ${w}</b> · <span class="note">Bye</span></li>`;
     const head=RF.kind==='both'?`${g.nK} kick + ${g.nP} punt returns`:`${g.n} ${RF.kind==='kr'?'kick':'punt'} returns`;
     const fcT=RF.kind!=='kr'?(g.fc==null?' · fair catches unknown':` · ${g.fc} fair catch${g.fc===1?'':'es'}`):'';
     const lines=(g.ret||[]).map(r=>`${esc(r.p)}: ${RF.kind==='both'?[r.kr?`${r.kr} KR`:'',r.pr?`${r.pr} PR`:''].filter(Boolean).join(' + ')||'0 returns':r.n} ${RF.kind==='both'?'':'for '}${r.y} yds${r.td?`, ${r.td} TD`:''}${RF.kind!=='kr'&&r.fc?`, ${r.fc} FC`:''}`).join('<br>');
     return `<li><b>Wk ${w}</b> vs ${esc(g.opp||'opponent unknown')} · ${head}${fcT}<br>${lines||`<span class="note">${RF.kind==='kr'?'No kick returns (all touchbacks or none kicked)':RF.kind==='pr'?'No punt returns (fair catches, touchbacks, out of bounds or no punts)':'No returns'}</span>`}</li>`}).join('')}</ul></section>`)}

/* ---------- Opponent kickoffs, team return splits, injury checker (Oct 7, Joe) ---------- */
// Opponent numbers are kick returns only (kickoff coverage); last 3 games + last game, tap for the season and weekly detail.
const rgF=(v,d=1)=>v==null||isNaN(v)?'n/a':(+v).toFixed(d);
function rgKO(t){const K=S.returns?.kickoffs?.[t];if(!K)return null;
  const ws=Object.keys(K).map(Number).sort((a,b)=>a-b).filter(w=>!K[w].bye);if(!ws.length)return null;
  const l3=ws.slice(-3),lw=ws[ws.length-1],sum=(a,f)=>a.reduce((s,w)=>s+f(K[w]),0);
  const r3=sum(l3,x=>x.returned),y3=sum(l3,x=>x.ret_yds_allowed),rS=sum(ws,x=>x.returned),yS=sum(ws,x=>x.ret_yds_allowed);
  return {K,ws,l3,lw,yd3:y3/l3.length,ydL:K[lw].ret_yds_allowed,ydS:yS/ws.length,ko3:sum(l3,x=>x.kickoffs)/l3.length,ret3:r3/l3.length,ypr3:r3?y3/r3:null,koL:K[lw].kickoffs,retL:K[lw].returned,
    koS:sum(ws,x=>x.kickoffs)/ws.length,retS:rS/ws.length,yprS:rS?yS/rS:null}}
let RG_LG=null;function rgLeague(){if(RG_LG)return RG_LG;const v=Object.keys(S.returns?.kickoffs||{}).map(rgKO).filter(Boolean);
  RG_LG={ret3:v.length?v.reduce((a,x)=>a+x.ret3,0)/v.length:null,ypr3:v.length?v.reduce((a,x)=>a+(x.ypr3||0),0)/v.length:null};return RG_LG}
function rgLvl(x){const L=rgLeague().ret3;if(x==null||!L)return['muted','n/a'];return x>=L*1.2?['ok','High']:x<=L*0.8?['bad','Low']:['muted','Average']}
const rgLvlChip=x=>{const[c,t]=rgLvl(x);return `<span class="chip rg-${c}" title="League average ${rgF(rgLeague().ret3)} kick returns allowed per game (last 3)">${t}</span>`};
// player's kick-return share, last 3 games played (from the kick model regardless of the toggle)
let RG_KS=null;function rgKrShare(p){if(!RG_KS){RG_KS=new Map();const m=rgModel('kr');if(m&&!m.error)rgRows(m).forEach(q=>{RG_KS.set(rgKey(q),q.sh3);RG_KS.set(q.team+':'+rgNorm(q.name),q.sh3)})}
  return RG_KS.get(rgKey(p))??RG_KS.get(p.team+':'+rgNorm(p.name))??0}
function rgExp(p){const o=rgOpp(p.team);if(o.bye)return {bye:true};if(o.miss||!o.key)return {miss:o.txt};const k=rgKO(o.key);if(!k)return {miss:`No kickoff data for ${o.key}`};
  const sh=rgKrShare(p)/100,er=k.ret3*sh;return {opp:o.key,k,sh,er,ep:er*(k.ypr3||rgLeague().ypr3||0)*(S.returns?.scoring?.krYd??.1)}}
function rgOppCell(p){const x=rgExp(p);if(x.bye)return '<span class="chip rg-bad">Bye</span>';if(x.miss)return `<span class="chip rg-bad">${esc(x.miss)}</span>`;
  return `<button class="link" data-rgopp="${x.opp}" title="Tap for ${x.opp}'s kickoffs by week and season average">${rgF(x.k.ret3)}</button> <span class="rgl" title="Last game">${x.k.retL}</span> ${rgLvlChip(x.k.ret3)}`}
function rgYdsCell(p){const x=rgExp(p);if(x.bye)return '<span class="chip rg-bad">Bye</span>';if(x.miss)return `<span class="chip rg-bad">${esc(x.miss)}</span>`;
  return `<button class="link" data-rgopp="${x.opp}" title="Return yards allowed per game, last 3 games; second number = last game. Tap for season and week by week">${rgF(x.k.yd3,0)}</button> <span class="rgl" title="Last game">${x.k.ydL}</span>`}
const rgExpTxt=p=>{const x=rgExp(p);return x.bye?'Bye':x.miss?'n/a':`${rgF(x.er)} returns · ${rgF(x.ep)} pts`};
function openRgOpp(t){const k=rgKO(t);if(!k)return;const K=k.K,W=S.returns.weeks||[];
  drawer(`<div class="dh"><div><div class="eyebrow">Kickoff coverage · ${t}</div><h2 id="dtitle">${t} kickoffs</h2></div><button class="x" aria-label="Close" data-close>×</button></div>
  <div class="facts"><div class="fact"><b>${rgF(k.ret3)}</b><span>Kick returns allowed / game, last ${k.l3.length}</span></div><div class="fact"><b>${k.retL}</b><span>Last game (wk ${k.lw})</span></div><div class="fact"><b>${rgF(k.retS)}</b><span>Season average</span></div>
   <div class="fact"><b>${rgF(k.yd3,0)}</b><span>Return yards allowed / game, last ${k.l3.length}</span></div><div class="fact"><b>${k.ydL}</b><span>Return yards allowed, last game</span></div><div class="fact"><b>${rgF(k.ydS,0)}</b><span>Return yards allowed / game, season</span></div><div class="fact"><b>${rgF(k.ko3)}</b><span>Kickoffs / game, last ${k.l3.length}</span></div><div class="fact"><b>${rgF(k.ypr3)}</b><span>Yards allowed per return, last ${k.l3.length}</span></div><div class="fact"><b>${rgF(k.yprS)}</b><span>Yards / return, season</span></div></div>
  <p class="note">${rgLvl(k.ret3)[1]} vs the league average of ${rgF(rgLeague().ret3)} kick returns allowed per game (last 3).</p>
  <section class="panel"><div class="ph"><h2>Week by week</h2></div><div class="tw"><table><thead><tr><th>Wk</th><th>Vs</th><th class="num">Kickoffs</th><th class="num">Returned</th><th class="num">Yds allowed</th><th class="num">Touchback</th><th class="num">Short of zone</th><th class="num">Out of bounds</th><th class="num">Onside</th></tr></thead><tbody>
  ${W.map(w=>{const x=K[w];if(!x)return `<tr><td>${w}</td><td colspan="8" class="note">No data</td></tr>`;if(x.bye)return `<tr><td>${w}</td><td colspan="8" class="note">Bye</td></tr>`;
    return `<tr><td>${w}</td><td>${x.home?'vs':'@'} ${esc(x.opp)}</td><td class="num">${x.kickoffs}</td><td class="num">${x.returned}</td><td class="num">${x.ret_yds_allowed}</td><td class="num">${x.touchback}</td><td class="num">${x.short_of_landing_zone}</td><td class="num">${x.out_of_bounds}</td><td class="num">${x.onside_attempts}</td></tr>`}).join('')}
  </tbody></table></div><p class="note">Returned = kickoffs the other team ran back (this is what a returner needs). Short of zone = penalty, ball placed at the 40, no return. Source: ESPN play-by-play, checked against ESPN team stats.</p></section>`)}
// team split from the current model (kick / punt / both)
function rgSplit(M_,t){const x=M_.teams[t];if(!x)return null;const played=M_.W.filter(w=>{const g=x.weeks?.[w];return g&&!g.bye});if(!played.length)return null;
  const agg=ws=>{const m=new Map();let n=0;ws.forEach(w=>{const g=x.weeks[w];n+=g.n||0;(g.ret||[]).forEach(r=>{if(r.n)m.set(r.p,(m.get(r.p)||0)+r.n)})});return {n,list:[...m.entries()].sort((a,b)=>b[1]-a[1]).map(([p,c])=>({p,c,s:n?c/n:0}))}};
  const L3=agg(played.slice(-3)),LG=agg(played.slice(-1)),SE=agg(played),top=L3.list[0];
  const pat=!top?['muted','No returns']:top.s>=.8?['ok','One man']:top.s>=.5?['warn','Split']:['bad','Committee'];
  const changed=!!(LG.list[0]&&top&&(LG.list[0].p!==top.p||Math.abs((LG.list.find(z=>z.p===top.p)?.s||0)-top.s)>=.3));
  return {L3,LG,SE,pat,changed,lw:played[played.length-1],topS:top?top.s:0}}
const rgShareTxt=a=>a.list.length?a.list.slice(0,3).map(z=>`${esc(rgLast(z.p))} ${Math.round(z.s*100)}%`).join(' / '):`<span class="note">0 returns</span>`;
// injury checker (official reports + inactives); upcoming = this week
function rgChk(t){const C=S.returns?.checker;return C?.upcoming?.[t]||null}
const RG_FL={RETURNER_BACK:['ok','Returner back'],RETURNER_OUT:['bad','Returner out'],OFFENSE_NEED:['warn','Needed on offense'],SHARE_AT_RISK:['warn','Share at risk']};
const rgFlagChips=fl=>(fl||[]).map(([k,txt])=>`<span class="chip rg-${(RG_FL[k]||['muted'])[0]}" title="${esc(txt)}">${esc((RG_FL[k]||[0,k])[1])}</span>`).join(' ');
function rgChkCell(t){const c=rgChk(t);if(!c)return S.returns?.checker?.upcomingWeek?'<span class="note">Bye or no report</span>':'<span class="note">This week\'s report not in yet</span>';
  return `<span>${c.predicted?`Likely: <b>${esc(rgLast(c.predicted))}</b>`:'<span class="note">No returner with history</span>'}</span> ${rgFlagChips(c.flags)}`}
function rgInjTeam(t){const I=S.returns?.injuries;if(!I)return '<p class="note">No injury data in this refresh.</p>';const C=S.returns.checker,cur=I.current?.teams?.[t]||[],up=rgChk(t);
  const hist=(C?.history||[]).filter(r=>r.team===t);
  return `<section class="panel"><div class="ph"><h2>Injury check</h2><span class="eyebrow">Official NFL injury reports + game-day inactives</span></div>
   ${up?`<p>Week ${C.upcomingWeek}: likely main kick returner <b>${esc(up.predicted||'unknown')}</b> ${rgFlagChips(up.flags)}</p>${(up.flags||[]).map(f=>`<p class="note">• ${esc(f[1])}</p>`).join('')}`:''}
   <div class="tw"><table><thead><tr><th>Week ${I.current?.week??''} report</th><th>Pos</th><th>Injury</th><th>Practice</th><th>Status</th></tr></thead><tbody>
   ${cur.length?cur.map(r=>`<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2]||'Not listed')}</td><td>${esc(r[3]||'Not listed')}</td><td>${esc(r[4]||'No status')}</td></tr>`).join(''):`<tr><td colspan="5" class="note">No skill-position or DB players on this week's official report yet${I.current?.asOf?` (checked ${esc(I.current.asOf)})`:''}.</td></tr>`}
   </tbody></table></div>
   <ul class="list">${hist.map(r=>{const o=I.weeks?.[r.week]?.[t]?.out||[];return `<li><b>Wk ${r.week}</b> · out: ${o.length?o.map(x=>esc(x[0])+' ('+esc(x[1])+')').join(', '):'none at RB/WR/TE/DB'}<br>${r.actual?`Main returner: <b>${esc(r.actual)}</b>${r.predicted?` · checker said ${esc(r.predicted)} ${r.hit?'✓':'✗'}`:''}`:'No kick returns'} ${rgFlagChips(r.flags)}</li>`}).join('')}</ul>
   <p class="note">Checker record so far: right on ${C?.backtest?.right??'n/a'} of ${C?.backtest?.games??'n/a'} games (main kick returner, weeks 2+, using only what was known before kickoff).</p></section>`}

/* ---------- Returner rankings: column picker + player detail (Oct 7, Joe) ---------- */
// Every column except Player can be switched off; depth-chart columns start off. Choice remembered in this browser.
const RG_COLS=[
 {k:'team',l:'NFL',sort:'team',cell:p=>`<td>${esc(p.team)}</td>`},
 {k:'opp',l:()=>`Wk ${rgWk()} opponent`,sort:'opp',cell:p=>`<td>${rgOppHtml(p.team,true)}</td>`},
 {k:'oppk',l:'Opp kick returns/gm (last 3)',num:1,kr:1,sort:'oppk',cell:p=>`<td class="num">${rgOppCell(p)}</td>`},
 {k:'oppy',l:'Opp return yds/gm (last 3)',num:1,kr:1,sort:'oppy',cell:p=>`<td class="num">${rgYdsCell(p)}</td>`},
 {k:'exp',l:'Expected this week',num:1,kr:1,sort:'exp',cell:p=>`<td class="num">${rgExpTxt(p)}</td>`},
 {k:'owner',l:'Owner',sort:'owner',cell:p=>`<td>${p.owner==='Free agent'?'<span class="chip rg-ok">Free agent</span>':p.owner==='Not in ESPN fantasy'?'<span class="note">Not in ESPN fantasy (defender)</span>':p.owner==='No ESPN id match'?'<span class="note">Not matched to an ESPN player</span>':esc(p.owner||'Owner unknown')}</td>`},
 {k:'site',l:'Team site',sort:'site',off:1,cell:(p,M_)=>`<td>${rgRank(M_,p,'site')}</td>`},
 {k:'espn',l:'ESPN',sort:'espn',off:1,cell:(p,M_)=>`<td>${rgRank(M_,p,'espn')}</td>`},
 {k:'lw',l:'Last game',num:1,sort:'lw',cell:p=>`<td class="num">${p.lwSh}% <span class="note">(${p.lwTxt})</span></td>`},
 {k:'sh3',l:'Share (3 games)',num:1,sort:'sh3',cell:p=>`<td class="num">${p.sh3}%</td>`},
 {k:'fc3',l:'Fair catches (3)',num:1,fc:1,sort:'fc3',cell:p=>`<td class="num">${p.fc3??'<span class="note">Unknown</span>'}</td>`},
 {k:'pts3',l:'Pts/game (3)',num:1,sort:'pts3',cell:p=>`<td class="num"><b>${p.pts3}</b></td>`},
 {k:'totK',l:'KR pts',num:1,both:1,sort:'totK',cell:p=>`<td class="num">${p.totK}</td>`},
 {k:'totP',l:'PR pts',num:1,both:1,sort:'totP',cell:p=>`<td class="num">${p.totP}</td>`},
 {k:'tot',l:'Season pts',num:1,sort:'tot',cell:p=>`<td class="num">${p.tot}</td>`},
 {k:'weeks',l:'Returns by week',cell:(p,M_)=>`<td>${rgWeeks(M_,p)}</td>`}];
let RG_HIDE=new Set(RG_COLS.filter(c=>c.off).map(c=>c.k));
try{const v=localStorage.getItem('lt-rg-hide');if(v)RG_HIDE=new Set(JSON.parse(v))}catch(e){}
const rgColLabel=c=>typeof c.l==='function'?c.l():c.l;
const rgColsFor=hasFc=>RG_COLS.filter(c=>(!c.kr||RF.kind!=='pr')&&(!c.fc||hasFc)&&(!c.both||RF.kind==='both'));
let RG_COLOPEN=false;
function rgColBar(hasFc){const cs=rgColsFor(hasFc),on=cs.filter(c=>!RG_HIDE.has(c.k)).length;
  return `<div class="rgcolw"><button class="rgcolbtn" data-rgcolopen="1" aria-expanded="${RG_COLOPEN}">Columns <span class="note">${on} of ${cs.length}</span> <i>${RG_COLOPEN?'▴':'▾'}</i></button>
  ${RG_COLOPEN?`<div class="rgcolpanel" role="group" aria-label="Show columns">${cs.map(c=>`<label><input type="checkbox" data-rgcol="${c.k}" ${RG_HIDE.has(c.k)?'':'checked'}> ${esc(rgColLabel(c))}</label>`).join('')}
   <div class="rgcolact"><button class="link" data-rgcolall="1">Show all</button><button class="link" data-rgcoldef="1">Default</button><button class="rst" data-rgcolopen="1">Done</button></div></div>`:''}</div>`}
let RG_ROWMAP=new Map();
function rgRankTable(M_,rows,hasFc){const cols=rgColsFor(hasFc).filter(c=>!RG_HIDE.has(c.k));RG_ROWMAP=new Map(rows.map(p=>[rgKey(p),p]));
  return `<div class="tw"><table><thead><tr>${sh('rp','player','Player')}${cols.map(c=>c.sort?sh('rp',c.sort,rgColLabel(c),c.num?1:0):`<th>${esc(rgColLabel(c))}</th>`).join('')}</tr></thead><tbody>
  ${rows.slice(0,RF.n).map(p=>`<tr class="row ${p.ours?'me':''}" tabindex="0" data-rgplayer="${esc(rgKey(p))}" title="Tap for depth charts and details"><td><b>${esc(p.name)}</b> <span class="note">${esc(p.pos)}</span></td>${cols.map(c=>c.cell(p,M_)).join('')}</tr>`).join('')||`<tr><td colspan="${cols.length+1}" class="note">No returners match this filter.</td></tr>`}
  </tbody></table></div>`}
function openRgPlayer(key){const p=RG_ROWMAP.get(key);const M_=rgModel(RF.kind);if(!p||!M_||M_.error)return;
  const st=RF.kind!=='both'?[rgStatus1(p,M_,RF.kind)]:['kr','pr'].map(k=>{const m=rgModel(k),q=rgRows(m).find(q=>rgKey(q)===rgKey(p)||(q.team===p.team&&rgSame(q.name,p.name)));return q&&(q.site[k]||q.espn[k]||q.tot||q.sh3)?rgStatus1(q,m,k):null}).filter(Boolean);
  const x=rgExp(p),c=rgChk(p.team);
  drawer(`<div class="dh"><div><div class="eyebrow">${esc(p.pos)} · ${esc(p.team)} · ${esc(p.owner)}</div><h2 id="dtitle">${esc(p.name)}</h2><div class="note">Week ${rgWk()}: ${rgOppHtml(p.team)}</div></div><button class="x" aria-label="Close" data-close>×</button></div>
  <div class="chips">${st.map(rgChip).join('')}</div>
  <section class="panel"><div class="ph"><h2>Depth charts today</h2></div><div class="tw"><table><tbody>
    <tr><td>Team site</td><td>${rgRank(M_,p,'site')}</td></tr><tr><td>ESPN</td><td>${rgRank(M_,p,'espn')}</td></tr></tbody></table></div>
    <p class="note">Depth charts checked ${esc(S.returns.checked||'date not recorded')}. <button class="link" data-rgteam="${esc(p.team)}">Open ${esc(p.team)} team detail</button></p></section>
  <div class="facts"><div class="fact"><b>${p.lwSh}%</b><span>Last game share (${esc(p.lwTxt)})</span></div><div class="fact"><b>${p.sh3}%</b><span>Share, last ${p.n3??3} games</span></div><div class="fact"><b>${p.pts3}</b><span>Return pts/game, last 3</span></div>
   <div class="fact"><b>${p.tot}</b><span>Season return pts</span></div>${RF.kind!=='pr'&&x.k?`<div class="fact"><b>${rgF(x.er)}</b><span>Expected kick returns vs ${x.opp}</span></div><div class="fact"><b>${rgF(x.ep)}</b><span>Expected kick-return pts</span></div>`:''}</div>
  ${RF.kind!=='pr'?`<p>Opponent: kick returns allowed/game ${rgOppCell(p)} · return yds allowed/game ${rgYdsCell(p)}</p>`:''}
  <p>${rgWeeks(M_,p)}</p>
  ${c?`<p>Injury check: likely main kick returner <b>${esc(c.predicted||'unknown')}</b> ${rgFlagChips(c.flags)}</p>${(c.flags||[]).map(f=>`<p class="note">• ${esc(f[1])}</p>`).join('')}`:''}`)}
