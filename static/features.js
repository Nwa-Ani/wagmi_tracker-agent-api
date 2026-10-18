// Lazy-loaded extras: Wrapped, Roast, Copy Simulator, Paperhands Pain, Wallet vs Wallet, Rug Check, Cabal Detector,
// Smart Money Radar, Leaderboard, Watchlist, Alerts. Share cards carry no creator credit.
(function(){
const P=()=>$('#fpanel');
const sheet=(html,cls='')=>{clearTimeout(window.__shT);const s=$('#sheet');s.className='sheet '+cls;s.innerHTML=`<div class="scard anim"><button class="sx" onclick="closeSheet()" aria-label="Close">✕</button>${html}</div>`;document.body.classList.add('gated');s.onclick=e=>{if(e.target===s)closeSheet()}};
const panel=(html)=>{const p=P();if(!p)return sheet(html);p.innerHTML=`<div class="fp anim">${html}</div>`;if(!document.body.classList.contains('shot'))p.scrollIntoView({behavior:'smooth',block:'start'})};
const priced=r=>(r.positions||[]).filter(p=>p.x_now!=null);
const u=r=>r.unit||'SOL';
const sym=(r,p)=>p.symbol?(r.asset==='nft'?'':'$')+p.symbol:sh(p.mint);
function wrapStats(r){const Q=priced(r),D=degen(r);const best=Q.slice().sort((a,b)=>b.x_now-a.x_now)[0],worst=Q.slice().sort((a,b)=>a.x_now-b.x_now)[0];
 const missed=(r.positions||[]).filter(p=>p.missed>0).sort((a,b)=>b.missed-a.missed)[0];return {Q,D,best,worst,missed}}
// ================= Wallet Wrapped =================
function wrapped(){const r=WRES;if(!r)return;const {Q,D,best,worst,missed}=wrapStats(r),U=u(r),nft=r.asset==='nft';
 const S=[
  {bg:'s1',h:`<div class="wk">${CFG.APP_NAME} Wrapped</div><div class="wbig mono">${sh(r.wallet)}</div><div class="wsub">${chOf(r).n}${nft?' NFTs':''} · ${r.sampled_txs} txs looked at</div><div class="wsub dim">Tap or swipe →</div>`},
  {bg:'s2',h:`<div class="wk">Your degen title</div><div class="wbig">${esc(D.title)}</div><div class="wnum">${D.score}<span>/1000</span></div><div class="wbadges">${D.badges.slice(0,4).map(b=>`<span class="bdg">${b.e} ${esc(b.t)}</span>`).join('')}</div>`},
  best?{bg:'s3',h:`<div class="wk">Best call</div><div class="wbig">${esc(sym(r,best))}</div><div class="wnum g">${cx(best.x_now)}</div><div class="wsub">${money(best.sol_in,U)} in · ${when(best.first_buy)}</div>`}:null,
  worst&&worst!==best?{bg:worst.x_now<1?'s4':'s3',h:`<div class="wk">${worst.x_now<1?'Worst bag':'Weakest win (no losers!)'}</div><div class="wbig">${esc(sym(r,worst))}</div><div class="wnum ${worst.x_now<1?'r':'g'}">${cx(worst.x_now)}</div><div class="wsub">${money(worst.sol_in,U)} in. ${worst.x_now<1?'It happens.':'Even the worst one made money.'}</div>`}:null,
  missed?{bg:'s5',h:`<div class="wk">Sold too early</div><div class="wbig">${esc(sym(r,missed))}</div><div class="wnum y">${money(missed.missed,U)}</div><div class="wsub">left on the table if you'd never sold (estimate, price now)</div>`}:null,
  {bg:'s6',h:`<div class="wk">The numbers</div><div class="wgrid"><div><b>${r.win_rate==null?'n/a':Math.round(r.win_rate*100)+'%'}</b><span>${nft?'floor ≥ mint':'win rate'}</span></div><div><b>${(r.positions||[]).length}</b><span>${nft?'collections':'tokens'}</span></div><div><b>${money(r.pnl_sol,U,true)}</b><span>est. P/L</span></div><div><b>${dur(r.median_delay)}</b><span>typical entry</span></div></div>`},
  {bg:'s7',h:`<div class="wk">Verdict</div><div class="wbig ${VERD(r.verdict).c}">${VERD(r.verdict).e} ${VERD(r.verdict).t}</div><div class="wsub">confidence ${String(r.confidence).toLowerCase()}</div><button class="btn share" onclick="FEAT.wrappedPng()">⬇ Save Wrapped card</button><div class="wsub dim small">Not financial advice.</div>`}].filter(Boolean);
 sheet(`<div class="wrap"><div class="wbars">${S.map(()=>'<i><b></b></i>').join('')}</div><div class="wslides">${S.map((s,i)=>`<div class="wslide ${s.bg}" data-i="${i}">${s.h}</div>`).join('')}</div><button class="wnav l" aria-label="Back">‹</button><button class="wnav r" aria-label="Next">›</button></div>`,'wrapsheet');
 let i=0,t=null;const go=n=>{i=Math.max(0,Math.min(S.length-1,n));$$('.wslide').forEach((e,k)=>{e.classList.toggle('on',k===i);e.classList.toggle('past',k<i)});const cur=$$('.wslide')[i];if(cur&&window.countUp)cur.querySelectorAll('.wnum').forEach(countUp);$$('.wbars i').forEach((e,k)=>{e.className=k<i?'done':k===i?'run':''});clearTimeout(t);if(i<S.length-1&&!FIXED)t=setTimeout(()=>go(i+1),4500)};const FIXED=new URLSearchParams(location.search).has('slide');
 $('.wnav.l').onclick=e=>{e.stopPropagation();go(i-1)};$('.wnav.r').onclick=e=>{e.stopPropagation();go(i+1)};
 $('.wslides').onclick=e=>{if(e.target.closest('button'))return;const x=e.clientX/window.innerWidth;go(x<.3?i-1:i+1)};
 let sx=null;$('.wslides').addEventListener('touchstart',e=>sx=e.touches[0].clientX,{passive:true});$('.wslides').addEventListener('touchend',e=>{if(sx==null)return;const d=e.changedTouches[0].clientX-sx;if(Math.abs(d)>40)go(d<0?i+1:i-1);sx=null});
 document.onkeydown=e=>{if(!$('.wrap'))return;if(e.key==='ArrowRight')go(i+1);if(e.key==='ArrowLeft')go(i-1);if(e.key==='Escape')closeSheet()};go(+(new URLSearchParams(location.search).get('slide')||0))}
function wrappedPng(inline){const r=WRES,{D,best,worst,missed}=wrapStats(r),U=u(r),c=$('#card'),g=c.getContext('2d');cardBase(g,'Wrapped · '+chOf(r).n,'#b07cff');
 g.fillStyle='#fff';g.font='800 50px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillText(sh(r.wallet),70,175);
 g.fillStyle='#b07cff';g.font='900 58px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(D.title.toUpperCase(),70,255);const tw=g.measureText(D.title.toUpperCase()).width;
 g.fillStyle='#ffc94a';g.font='800 34px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`${D.score}/1000`,90+tw,252);
 stat(g,72,330,'BEST CALL',best?`${(best.symbol||'?').slice(0,8)} ${cx(best.x_now)}`:'n/a','#39ff88');stat(g,620,330,worst&&worst.x_now>=1?'WEAKEST WIN':'WORST BAG',worst?`${(worst.symbol||'?').slice(0,8)} ${cx(worst.x_now)}`:'n/a','#ff5f73');
 g.fillStyle='#8b95a5';g.font='700 20px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText('SOLD TOO EARLY',72,470);g.fillStyle='#ffc94a';g.font='800 36px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(missed?`${missed.symbol||'?'}: missed ~${money(missed.missed,U)}`:'nothing big missed',72,515);
 foot(g,`${D.badges.slice(0,4).map(b=>b.t).join(' · ')||'no badges'} · estimates · not financial advice`,585);finish(c,`${CFG.APP_NAME}-wrapped-${sh(r.wallet)}.png`,inline)}
// ================= Roast Mode =================
const pick=a=>a[Math.floor(Math.random()*a.length)];
function roastLines(r){const {Q,D,best,worst,missed}=wrapStats(r),L=[],U=u(r),a=r.activity||{};
 if(r.win_rate!=null&&r.win_rate<.3)L.push(pick([`A ${Math.round(r.win_rate*100)}% win rate. A coin flip would like a word.`,`Win rate ${Math.round(r.win_rate*100)}%. You're not trading, you're donating.`]));
 if(r.win_rate!=null&&r.win_rate>=.6)L.push(pick([`${Math.round(r.win_rate*100)}% win rate. Suspiciously good. Do you know the dev?`,`Winning ${Math.round(r.win_rate*100)}% of the time and still checking charts at 3am.`]));
 if(worst&&worst.x_now<.3)L.push(`${sym(r,worst)} at ${cx(worst.x_now)}. That bag isn't heavy, it's load-bearing.`);
 if(best&&best.x_now>=3)L.push(`One ${cx(best.x_now)} on ${sym(r,best)} and you've been talking about it ever since.`);
 if(missed&&missed.missed>0)L.push(`Sold ${sym(r,missed)} early and left about ${money(missed.missed,U)} on the table. Paper hands, laminated.`);
 if(r.median_hold!=null&&r.median_hold<300)L.push(`Median hold ${dur(r.median_hold)}. Commitment issues, but make it on-chain.`);
 if((r.sniper_share||0)>=.3)L.push('Buys in the first seconds. Either a bot or someone who has never blinked.');
 if((a.tx_per_day||0)>=200)L.push(`${Math.round(a.tx_per_day)} txs a day. Touch grass. Then touch it again.`);
 if(r.median_delay!=null&&r.median_delay>86400)L.push(`Usually buys ${dur(r.median_delay)} after launch. Fashionably late, financially later.`);
 if(r.asset==='nft'&&(a.mints||0)>=10)L.push(`${a.mints} mints. Your wallet is a JPEG storage unit with gas fees.`);
 if(r.asset==='nft'&&r.self_share!=null&&r.self_share<.5)L.push('Half these NFTs were airdropped to you. Even your collection is unsolicited.');
 if((r.pnl_sol||0)<0)L.push(`Net ${money(r.pnl_sol,U,true)}. The market thanks you for your service.`);
 if(!L.length)L.push('Not enough history to roast. Even the blockchain forgot about this wallet.');
 L.push(`Degen title: ${D.title}. Score ${D.score}/1000.`);return L.slice(0,5)}
function roast(){const r=WRES;const L=roastLines(r);
 panel(`<div class="fh">🔥 Roast Mode <span class="dim small">all in good fun</span></div><ul class="roast">${L.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
 <div class="actions">${CFG.ROAST_LLM?'<button class="btn ghost" id="spicy">✨ Spicier (AI)</button>':''}<button class="btn ghost" id="again">🎲 Roast again</button><button class="btn share" id="rpng">⬇ Roast card</button><button class="btn ghost" id="rcopy">Copy text</button></div><div id="ai" class="roast ai"></div>`);
 $('#again').onclick=roast;$('#rcopy').onclick=()=>{navigator.clipboard?.writeText(L.join('\n'));toast('Copied.')};$('#rpng').onclick=()=>roastPng(L);
 if($('#spicy'))$('#spicy').onclick=async()=>{$('#ai').textContent='Cooking…';const s={win_rate:r.win_rate,pnl:r.pnl_sol,unit:u(r),best_x:r.best_x_now,median_hold_s:r.median_hold,median_entry_s:r.median_delay,tx_per_day:(r.activity||{}).tx_per_day,title:degen(r).title};
  const j=await fetch('/api/roast',{method:'POST',body:JSON.stringify({stats:s})}).then(r=>r.json()).catch(()=>({}));$('#ai').textContent=j.text||'AI roast is unavailable right now.'}}
function roastPng(L,inline){const r=WRES,c=$('#card'),g=c.getContext('2d');cardBase(g,'roast · '+chOf(r).n,'#ff8a3d');g.fillStyle='#fff';g.font='800 46px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillText('🔥 '+sh(r.wallet),70,175);
 g.font='600 30px "Space Grotesk",Inter,system-ui,sans-serif';let y=245;for(const line of L.slice(0,4)){const words=line.split(' ');let cur='';for(const w of words){if(g.measureText(cur+w).width>1040){g.fillStyle='#e9eef5';g.fillText(cur,72,y);y+=40;cur=''}cur+=w+' '}g.fillStyle='#e9eef5';g.fillText(cur,72,y);y+=54;if(y>560)break}
 foot(g,'Playful roast from public stats · estimates · not financial advice',600);finish(c,`${CFG.APP_NAME}-roast-${sh(r.wallet)}.png`,inline)}
// ================= Copy Simulator =================
function copysim(){const r=WRES;panel(`<div class="fh">🧪 Copy Simulator</div><div class="simrow">If I had copied every trade with <span class="pre">$</span><input id="amt" type="number" value="100" min="1"> over the last <select id="days"><option>7</option><option selected>30</option><option>90</option></select> days…</div><div id="simout"></div>`);
 const run=()=>{const amt=+$('#amt').value||100,days=+$('#days').value,cut=Date.now()/1000-days*86400;const Q=priced(r).filter(p=>(p.first_buy||0)>=cut&&!p.soulbound);
  if(!Q.length){$('#simout').innerHTML=`<div class="dim">No priced ${r.asset==='nft'?'mints':'trades'} in that window to simulate.</div>`;return}
  const per=amt/Q.length,end=Q.reduce((s,p)=>s+per*Math.min(p.x_now,r.asset==='nft'&&p.free_mint?3:1e6),0),x=end/amt;
  $('#simout').innerHTML=`<div class="simbig ${x>=1?'g':'r'}">$${amt.toLocaleString()} → $${end.toFixed(2)}</div><div class="dim">${cx(x)} · ${Q.length} ${r.asset==='nft'?'mints':'trades'} copied, $${per.toFixed(2)} each, same entries and exits</div>
  <div class="simbars">${Q.slice(0,16).map(p=>`<div class="sb"><span>${esc(sym(r,p))}</span><i style="width:${Math.min(100,p.x_now*33)}%" class="${p.x_now>=1?'g':'r'}"></i><b>${cx(p.x_now)}</b></div>`).join('')}</div>
  <div class="dim small">Estimate: no fees, slippage or copy delay; free mints capped at 3x. Not financial advice.</div><div class="actions"><button class="btn share" id="simpng">⬇ Share card</button></div>`;
  $('#simpng').onclick=()=>simPng(amt,end,days,Q.length)};$('#amt').oninput=run;$('#days').onchange=run;run()}
function simPng(amt,end,days,n,inline){const r=WRES,c=$('#card'),g=c.getContext('2d'),up=end>=amt;cardBase(g,'copy simulator · '+chOf(r).n,up?'#39ff88':'#ff5f73');
 g.fillStyle='#8b95a5';g.font='28px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`Copying ${sh(r.wallet)} for ${days} days`,72,180);
 g.fillStyle=up?'#39ff88':'#ff5f73';g.font='900 120px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`$${amt} → $${end.toFixed(0)}`,66,330);
 g.fillStyle='#e9eef5';g.font='600 32px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`${cx(end/amt)} across ${n} copied trades`,72,400);foot(g,'Estimate · no fees, slippage or copy delay · public on-chain data · not financial advice',560);finish(c,`${CFG.APP_NAME}-copysim-${sh(r.wallet)}.png`,inline)}
// ================= Paperhands Pain =================
function paperhands(){const r=WRES,U=u(r);const S=(r.positions||[]).filter(p=>p.hold_value!=null&&p.n_sells);
 if(!S.length)return panel('<div class="fh">🧻 Paperhands Pain</div><div class="dim">No sold positions with a price today, so nothing to compare.</div>');
 const pain=S.filter(p=>p.missed>0).sort((a,b)=>b.missed-a.missed),saved=S.filter(p=>p.missed<0).sort((a,b)=>a.missed-b.missed),tot=pain.reduce((s,p)=>s+p.missed,0),tsave=-saved.reduce((s,p)=>s+p.missed,0);
 const row=p=>`<div class="ph"><span class="sym">${esc(sym(r,p))}</span><span>got <b>${money(p.sol_out+(p.value_left||0),U)}</b></span><span>if held <b>${money(p.hold_value,U)}</b></span><span class="${p.missed>0?'r':'g'}">${p.missed>0?'missed':'saved'} ${money(Math.abs(p.missed),U)}</span></div>`;
 panel(`<div class="fh">🧻 Paperhands Pain</div><div class="simbig r">${money(tot,U)} missed</div><div class="dim">across ${pain.length} sold position(s), vs holding until today. Selling saved ${money(tsave,U)} on ${saved.length} other(s).</div>
 ${pain.length?`<div class="topmiss">Biggest miss: <b>${esc(sym(r,pain[0]))}</b>, sold for ${money(pain[0].sol_out,U)}, would be ${money(pain[0].hold_value,U)} today</div>`:''}
 <div class="phl">${pain.slice(0,10).map(row).join('')}${saved.slice(0,5).map(row).join('')}</div><div class="dim small">Estimate: tokens × price now vs what the wallet got.</div>
 <div class="actions"><button class="btn share" id="phpng">⬇ Share card</button></div>`);$('#phpng').onclick=()=>phPng(pain,tot)}
function phPng(pain,tot,inline){const r=WRES,U=u(r),c=$('#card'),g=c.getContext('2d');cardBase(g,'paperhands pain · '+chOf(r).n,'#ffc94a');
 g.fillStyle='#fff';g.font='800 50px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillText('🧻 '+sh(r.wallet),70,180);
 const top=pain[0];g.fillStyle='#ffc94a';g.font='900 54px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(top?`Sold $${(top.symbol||'?').slice(0,10)} too early`:'No painful sells',70,275);
 if(top){g.fillStyle='#e9eef5';g.font='600 34px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`Got ${money(top.sol_out,U)} · would be ${money(top.hold_value,U)} today`,72,335)}
 stat(g,72,410,'TOTAL MISSED',money(tot,U),'#ff5f73');stat(g,620,410,'PAINFUL SELLS',''+pain.length,'#ffc94a');foot(g,'Estimate · tokens x price now vs proceeds · not financial advice',585);finish(c,`${CFG.APP_NAME}-paperhands-${sh(r.wallet)}.png`,inline)}
// ================= Wallet vs Wallet =================
let VS=null;
function vs(arg){const L=WRES;panel(`<div class="fh">⚔️ Wallet vs Wallet <span class="dim small">${chOf(L).n}${L.asset==='nft'?' · NFTs':''}</span></div>
 <div class="vsin"><div class="vsl mono">${sh(L.wallet)}</div><b class="vsx">VS</b><input id="vs2" class="mono" placeholder="Paste a second wallet…" value="${esc(arg||'')}"><button class="btn share" id="fight">Fight</button></div><div id="vsprog" class="dim small"></div><div id="vsout"></div>`);
 $('#fight').onclick=async()=>{const a=$('#vs2').value.trim();if(!a)return;$('#fight').disabled=true;$('#vsprog').textContent='Checking the challenger…';
  try{const R=await runJob('wallet',a,false,j=>{$('#vsprog').textContent=j.status||''},L.chain||'sol',L.asset||'coin');$('#vsprog').textContent='';battle(L,R)}catch(e){$('#vsprog').textContent=e.message}$('#fight').disabled=false};
 if(arg)$('#fight').click()}
function battle(A,B){const U=u(A),dA=degen(A),dB=degen(B);
 const rows=[['Win rate',A.win_rate,B.win_rate,x=>x==null?'n/a':Math.round(x*100)+'%',1],['Net P/L',A.pnl_sol,B.pnl_sol,x=>money(x,U,true),1],['Early entry',A.median_delay,B.median_delay,dur,-1],['Best x',A.best_x_now,B.best_x_now,cx,1],['5x+ peaks',A.n5,B.n5,x=>x??0,1],['Degen Score',dA.score,dB.score,x=>x,1]];
 let sa=0,sb=0;const R=rows.map(([k,a,b,f,dir])=>{let w=0;if(a!=null&&b!=null&&a!==b)w=(a>b)===(dir>0)?1:2;else if(a!=null&&b==null)w=1;else if(b!=null&&a==null)w=2;if(w===1)sa++;if(w===2)sb++;return {k,a:f(a),b:f(b),w}});
 const win=sa===sb?0:sa>sb?1:2;VS={A,B,R,sa,sb,win};
 $('#vsout').innerHTML=`<div class="vsgrid"><div class="vh ${win===1?'win':''}">${sh(A.wallet)}<span>${esc(dA.title)}</span></div><div></div><div class="vh ${win===2?'win':''}">${sh(B.wallet)}<span>${esc(dB.title)}</span></div>
 ${R.map((x,i)=>`<div class="vc l ${x.w===1?'win':''}" style="animation-delay:${i*260}ms">${x.a}</div><div class="vk" style="animation-delay:${i*260}ms">${x.k}</div><div class="vc r ${x.w===2?'win':''}" style="animation-delay:${i*260}ms">${x.b}</div>`).join('')}</div>
 <div class="banner" style="animation-delay:${R.length*260+200}ms">${win?`🏆 ${sh(win===1?A.wallet:B.wallet)} wins ${Math.max(sa,sb)}-${Math.min(sa,sb)}`:`🤝 Draw ${sa}-${sb}`}</div>
 <div class="dim small">Estimates from sampled history. Not financial advice.</div><div class="actions"><button class="btn share" onclick="FEAT.vsPng()">⬇ Battle card</button></div>`}
function vsPng(inline){const {A,B,R,sa,sb,win}=VS,c=$('#card'),g=c.getContext('2d');cardBase(g,'wallet vs wallet · '+chOf(A).n,'#ffc94a');
 g.font='800 44px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillStyle=win===1?'#39ff88':'#e9eef5';g.fillText(sh(A.wallet),70,180);g.fillStyle='#ffc94a';g.font='900 44px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText('VS',548,180);
 g.font='800 44px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillStyle=win===2?'#39ff88':'#e9eef5';const bw=g.measureText(sh(B.wallet)).width;g.fillText(sh(B.wallet),1130-bw,180);
 let y=245;for(const x of R){g.font='700 22px "Space Grotesk",Inter,system-ui,sans-serif';g.fillStyle='#8b95a5';const kw=g.measureText(x.k.toUpperCase()).width;g.fillText(x.k.toUpperCase(),600-kw/2,y);
  g.font='800 32px "Space Grotesk",Inter,system-ui,sans-serif';g.fillStyle=x.w===1?'#39ff88':'#e9eef5';g.fillText(String(x.a),72,y+4);g.fillStyle=x.w===2?'#39ff88':'#e9eef5';const w=g.measureText(String(x.b)).width;g.fillText(String(x.b),1130-w,y+4);y+=50}
 g.fillStyle='#ffc94a';g.font='900 44px "Space Grotesk",Inter,system-ui,sans-serif';const t=win?`🏆 ${sh(win===1?A.wallet:B.wallet)} WINS ${Math.max(sa,sb)}-${Math.min(sa,sb)}`:`DRAW ${sa}-${sb}`;const tw=g.measureText(t).width;g.fillText(t,600-tw/2,580);
 foot(g,'Estimates from public on-chain data · not financial advice',625);finish(c,`${CFG.APP_NAME}-vs-${sh(A.wallet)}-${sh(B.wallet)}.png`,inline)}
// ================= Rug Check =================
async function rug(){const r=TRES;panel('<div class="fh">🚦 Rug Check</div><div class="dim">Checking…</div>');
 const j=await fetch(`/api/rug?chain=${r.chain||'sol'}&addr=${encodeURIComponent(r.mint)}`).then(x=>x.json()).catch(e=>({error:e.message}));
 if(j.error)return panel(`<div class="fh">🚦 Rug Check</div><div class="errbox">${esc(j.error)}</div>`);
 panel(`<div class="fh">🚦 Rug Check</div><div class="light ${j.light}"><span class="lamp r"></span><span class="lamp y"></span><span class="lamp g"></span><b>${j.label}</b><span class="dim small">${j.known} checks with data</span></div>
 <div class="checks">${j.checks.map(c=>`<div class="ck ${c.status}"><span class="dot"></span><b>${esc(c.name)}</b><span>${esc(c.detail)}</span></div>`).join('')}</div><div class="dim small">${esc(j.note)}</div>`)}
// ================= Cabal Detector =================
async function cabal(){const r=TRES,C=chOf(r);panel('<div class="fh">🕸️ Cabal Detector</div><div class="dim">Looking for linked wallets (funders, same-block buys, repeat co-buyers)…</div>');
 const j=await fetch(`/api/cabal?chain=${r.chain||'sol'}&addr=${encodeURIComponent(r.mint)}`).then(x=>x.json()).catch(e=>({error:e.message}));
 if(j.error)return panel(`<div class="fh">🕸️ Cabal Detector</div><div class="errbox">${esc(j.error)}</div>`);
 panel(`<div class="fh">🕸️ Cabal Detector</div><div class="simbig ${j.groups.length?'y':'g'}">${j.groups.length?`${j.groups.length} possible group(s)`:'No groups found'}</div><div class="dim">${j.flagged} of ${j.checked} early wallets are in a group.</div>
 <div class="cabals">${j.groups.slice(0,12).map(g=>`<div class="cb"><div><span class="tag">${esc(g.type)}</span> ${esc(g.why)}</div><div class="cbw">${g.wallets.slice(0,14).map(w=>`<a class="mono" target="_blank" href="${C.acct}${w}">${sh(w)}</a>`).join('')}${g.wallets.length>14?`<span class="dim">+${g.wallets.length-14}</span>`:''}</div></div>`).join('')}</div><div class="dim small">${esc(j.note)}</div>`)}
// ================= Radar / Leaderboard / Watchlist / Alerts (global menu) =================
const row=(x,inner)=>`<button class="lrow" data-k="wallet" data-a="${x.wallet}" data-c="${x.chain}" data-as="${x.asset||'coin'}">${inner}</button>`;
const bindRows=()=>$$('.lrow').forEach(b=>b.onclick=()=>openItem({k:b.dataset.k,a:b.dataset.a,c:b.dataset.c,as:b.dataset.as}));
async function radar(refresh){sheet('<div class="fh">📡 Smart Money Radar</div><div class="dim">Loading…</div>');
 const j=await (refresh?fetch('/api/radar',{method:'POST'}):fetch('/api/radar')).then(x=>x.json());
 sheet(`<div class="fh">📡 Smart Money Radar</div><div class="dim small">${esc(j.note)}${j.refreshed?' Last live refresh '+when(j.refreshed)+'.':''}</div><div class="actions"><button class="btn ghost" id="rref">↻ Refresh live buys</button></div>
 <div class="feed">${j.items.map(x=>`<div class="fi"><span class="cbadge c-${x.chain}">${x.chain.slice(0,3)}</span><button class="linkb mono" data-a="${x.wallet}" data-c="${x.chain}">${sh(x.wallet)}</button><span class="dim">score ${x.score}</span><span>bought <a target="_blank" href="${(CH[x.chain]||CH.sol).tok(x.mint)}">${x.symbol?'$'+esc(x.symbol):sh(x.mint)}</a></span>${x.spent?`<span class="dim">${money(x.spent,x.chain==='sol'?'SOL':'USD')}</span>`:''}${x.x_now!=null?fx(x.x_now):''}<span class="dim small">${when(x.ts)}${x.src==='live'?' · live':''}</span></div>`).join('')||`<div class="dim">No recent buys from top wallets yet. Scan a few coins first, then come back.</div>`}</div>`);
 $('#rref').onclick=()=>radar(true);$$('.linkb').forEach(b=>b.onclick=()=>openItem({k:'wallet',a:b.dataset.a,c:b.dataset.c,as:'coin'}))}
async function leaderboard(){sheet('<div class="fh">🏆 Leaderboard</div><div class="dim">Loading…</div>');const j=await fetch('/api/leaderboard').then(x=>x.json());
 sheet(`<div class="fh">🏆 Leaderboard <span class="dim small">best early wallets found so far</span></div><div class="lb">${j.rows.map((x,i)=>row(x,`<span class="lr">${i<3?['🥇','🥈','🥉'][i]:'#'+(i+1)}</span><span class="cbadge c-${x.chain}">${x.chain.slice(0,3)}</span><span class="mono">${sh(x.wallet)}</span><span class="dim small">${esc(x.from)}</span><span>${pct(x.win_rate)}</span><span>${fx(x.best_x)}</span><b>${x.score}</b>`)).join('')||'<div class="dim">Nothing yet. Scan a coin to start the board.</div>'}</div><div class="dim small">${esc(j.note)}</div>`);bindRows()}
function watchlist(){const L=WL();sheet(`<div class="fh">★ Watchlist <span class="dim small">saved in this browser</span></div><div class="lb">${L.map((x,i)=>`<div class="lrow2"><button class="lrow" data-i="${i}"><span class="cbadge c-${x.c}">${x.c.slice(0,3)}</span>${x.k==='wallet'?`<span class="d ${x.v||''}"></span>`:''}<span>${esc(x.l)}</span><span class="dim small mono">${sh(x.a)}</span><span class="dim small">${x.k==='wallet'?'wallet':'coin/collection'}</span></button><button class="xbtn" data-x="${i}" title="Remove">✕</button></div>`).join('')||'<div class="dim">Nothing saved yet. Tap ☆ on any result to save it here.</div>'}</div>`);
 $$('.lrow[data-i]').forEach(b=>b.onclick=()=>openItem(L[+b.dataset.i]));$$('.xbtn').forEach(b=>b.onclick=()=>{L.splice(+b.dataset.x,1);localStorage.setItem('watchlist',JSON.stringify(L));watchlist()})}
async function alerts(){const j=await fetch('/api/alerts').then(x=>x.json()).catch(()=>({enabled:false}));const w0=WRES&&$('#fpanel')&&$('#out .degen')?WRES:null,w=w0&&w0.chain!=='btc'?w0:null;
 const body=j.enabled&&j.bot?`<p>Get a Telegram ping when a wallet buys or mints. Nothing is ever posted for you.</p>${w?`<a class="btn share" target="_blank" href="https://t.me/${j.bot}?start=watch_${w.wallet}_${w.chain||'sol'}">🔔 Alert me about ${sh(w.wallet)}</a>`:w0?'<p class="dim small">Bitcoin wallets are not covered by alerts yet.</p>':''}<p class="dim small">Or open <a target="_blank" href="https://t.me/${j.bot}">@${j.bot}</a> and send <code>/watch &lt;wallet&gt; sol|eth|base|robinhood</code>. Checked about every ${Math.round(j.interval/60)} min. Alerts can be late or missed.</p>`
 :`<p>Telegram alerts are switched off on this server.</p><p class="dim small">The site owner can turn them on by setting <code>TELEGRAM_BOT_TOKEN</code>. Meanwhile, save wallets to your ★ Watchlist and check them here.</p>`;
 (w?panel:sheet)(`<div class="fh">🔔 Alerts</div>${body}`)}
async function png(k){window.INLINE_PNG=1;const [n,a]=String(k).split(':');const click=s=>setTimeout(()=>$(s)&&$(s).click(),300);
 if(n==='wrapped')return wrappedPng(1);if(n==='roast')return roastPng(roastLines(WRES),1);if(n==='sim'){copysim();return click('#simpng')}if(n==='ph'){paperhands();return click('#phpng')}
 if(n==='vs'){window.INLINE_PNG=0;vs(a);const t=setInterval(()=>{if(VS){clearInterval(t);window.INLINE_PNG=1;vsPng(1)}},300)}}
window.FEAT={png,wrapped,wrappedPng,roast,copysim,paperhands,vs,vsPng,rug,cabal,radar,leaderboard,watchlist,alerts};
})();
