const CFG=window.APP_CONFIG||{APP_NAME:'wagmi_tracker',TAGLINE:'Your own personal wallet and coin tracker. Anywhere, anytime.',CREDIT:'@heisevo'};
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
document.title=CFG.APP_NAME;$('#appname').textContent=CFG.APP_NAME;if(CFG.CREDIT){const c=$('#credit');c.textContent='by '+CFG.CREDIT;c.href='https://x.com/'+CFG.CREDIT.replace(/^@/,'')}
let MODE='token',CHAIN=localStorage.getItem('chain')||'sol',ASSET=localStorage.getItem('asset')||'coin',TRES=null,WRES=null,timer=null,TABLE=false;
// ---------- chains ----------
const CH={sol:{n:'Solana',acct:'https://solscan.io/account/',tok:a=>'https://dexscreener.com/solana/'+a,ex:'Solscan'},
 eth:{n:'Ethereum',acct:'https://etherscan.io/address/',tok:a=>'https://dexscreener.com/ethereum/'+a,nft:a=>'https://opensea.io/assets/ethereum/'+a,ex:'Etherscan'},
 base:{n:'Base',acct:'https://basescan.org/address/',tok:a=>'https://dexscreener.com/base/'+a,nft:a=>'https://opensea.io/assets/base/'+a,ex:'Basescan'},
 robinhood:{n:'Robinhood Chain',acct:'https://robinhoodchain.blockscout.com/address/',tok:a=>'https://dexscreener.com/robinhood/'+a,ex:'Blockscout'},
 btc:{n:'Bitcoin',acct:'https://mempool.space/address/',tok:a=>a.includes('i')&&a.length>60?'https://ordinals.com/inscription/'+a:'https://ordinals.com/rune/'+a,ex:'mempool'}};
const chOf=r=>CH[(r&&r.chain)||'sol']||CH.sol;
const assetLink=(r,m)=>r.asset==='nft'?(chOf(r).nft?chOf(r).nft(m):r.chain==='sol'?'https://magiceden.io/item-details/'+m:chOf(r).tok(m)):chOf(r).tok(m);
const rkey=(c,a,k,x)=>c==='sol'&&a==='coin'?(k==='token'?x:'wallet_'+x):`${c}-${a}-${k==='wallet'?'wallet_':''}${x.replace(/[^0-9A-Za-z:._-]/g,'_')}`;
// ---------- formatting ----------
const sh=a=>!a?'?':a.length>14?a.slice(0,4)+'…'+a.slice(-4):a;
const fx=x=>x==null?'<span class="dim">n/a</span>':`<span class="${x>=1?'g':'r'}">${x>=100?x.toFixed(0):x.toFixed(x>=10?1:2)}x</span>`;
const pct=x=>x==null?'<span class="dim">n/a</span>':`<span class="${x>=.5?'g':x>=.3?'y':'r'}">${Math.round(x*100)}%</span>`;
const money=(x,u,signed)=>{if(x==null||isNaN(x))return 'n/a';const s=signed&&x>=0?'+':x<0?'-':'';const v=Math.abs(x);
 return u==='USD'?s+'$'+(v>=1000?Math.round(v).toLocaleString():v.toFixed(2)):s+(v>=100?v.toFixed(0):v>=1?v.toFixed(2):v.toPrecision(2))+' '+(u||'SOL')};
const dur=s=>s==null?'n/a':s<90?Math.round(s)+'s':s<5400?Math.round(s/60)+'m':s<172800?(s/3600).toFixed(1)+'h':Math.round(s/86400)+'d';
const when=t=>t?new Date(t*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
const VERD=v=>!v?null:/^(Good for copy|Copy)/.test(v)?{c:'g',t:v.startsWith('Copy-mint')?'Copy-mint it':'Copy it',e:'✅'}:/^(Good for alpha|Watch)/.test(v)?{c:'y',t:'Watch for alpha',e:'👀'}:{c:'r',t:'Skip',e:'⛔'};
const tier=w=>w.n_tokens==null?null:(w.score>=55&&w.n_tokens>=4)?{c:'g',t:'Strong'}:w.score>=35?{c:'y',t:'Mixed'}:{c:'r',t:'Weak'};
const meter=c=>{const n=c==='High'?3:c==='Medium'?2:1;return `<span class="meter">${[1,2,3].map(i=>`<i class="${i<=n?'on':''}"></i>`).join('')}</span>`};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// ---------- Degen Score 0-1000 + badges (shared by features) ----------
function degen(r){const P=r.positions||[],a=r.activity||{},nft=r.asset==='nft';
 const wr=r.win_rate??0,bx=r.best_x_now||0,n5=r.n5||0,md=r.median_delay,tx=a.tx_per_day||0;
 let s=wr*300+Math.min(Math.log10(Math.max(bx,1))*130,200)+Math.min(n5,5)*30+(md==null?40:md<=60?150:md<=600?120:md<=3600?90:md<=86400?50:20)+Math.min(tx,100)+((r.pnl_sol||0)>0?100:30);
 if(nft)s=s*0.8+Math.min((a.mints||0)*8,200);s=Math.max(0,Math.min(1000,Math.round(s)));
 const B=[];const add=(e,t,why)=>B.push({e,t,why});
 if((r.sniper_share||0)>=.3)add('🎯','Sniper','buys in the first seconds');if((r.share_first_hour||0)>=.5)add('🐣','Early Bird','most entries in the first hour');
 if(r.n10>=1)add('🚀','10x Hunter','a token ran 10x+ after its entry');if(r.median_hold!=null&&r.median_hold<300)add('🧻','Paper Hands','median hold under 5 minutes');
 if((r.median_hold||0)>=86400||(r.holding_now||0)>=Math.max(3,P.length*.5))add('💎','Diamond Hands','holds for days');
 if(r.win_rate!=null&&r.win_rate<.3&&r.n_tokens>=3)add('🩸','Exit Liquidity','most bags went down');if(tx>=300)add('🤖','Bot-like','hundreds of txs a day');
 if(nft&&(a.mints||0)>=10)add('🖼️','Mint Machine','mints a lot');if((r.spent_sol||0)>=(r.unit==='USD'?20000:100))add('🐋','Whale','big size');
 if(r.win_rate>=.6&&r.n_tokens>=5)add('🧠','Smart Money','wins most trades');
 const title=(B[0]||{t:s>=700?'Degen Royalty':s>=450?'Seasoned Degen':'Tourist'}).t;
 return {score:s,badges:B,title}}
// ---------- tabs / pickers / search ----------
function setMode(m,keep){MODE=m;$$('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t===m));$('.tabs').classList.toggle('w',m==='wallet');refreshCopy();if(!keep){$('#out').innerHTML='';hideProg()}}
function refreshCopy(){const nft=ASSET==='nft',m=MODE;$('#chain').value=CHAIN;$$('.asset button').forEach(b=>b.classList.toggle('on',b.dataset.a===ASSET));
 $('.asset').classList.toggle('lock',CHAIN==='btc');
 const what=CHAIN==='btc'?(m==='token'?'Paste a rune name or inscription id…':'Paste a Bitcoin address (bc1p…)…'):m==='token'?(nft?'Paste an NFT collection address…':'Paste a token address…'):'Paste a wallet address…';
 $('#q').placeholder=what;$('#go span').textContent=m==='token'?'Scan':'Check';
 $$('.tab')[0].innerHTML=(nft||CHAIN==='btc')?'🖼️ Scan a collection':'🪙 Scan a coin';
 const hl=m==='token'?(nft||CHAIN==='btc'?'Who minted this first?':'Who bought this coin first?'):'Is this wallet worth following?',H=$('#headline');if(H.textContent!==hl){H.textContent=hl;swapAnim(H);swapAnim($('#q'))}}
function swapAnim(e){if(!e)return;e.classList.remove('swap');void e.offsetWidth;e.classList.add('swap')}
$$('.tab').forEach(b=>b.onclick=()=>setMode(b.dataset.t));
$('#chain').onchange=e=>{CHAIN=e.target.value;if(CHAIN==='btc')ASSET='nft';localStorage.setItem('chain',CHAIN);localStorage.setItem('asset',ASSET);refreshCopy()};
$$('.asset button').forEach(b=>b.onclick=()=>{if(CHAIN==='btc')return toast('Bitcoin mode covers Ordinals and Runes.');ASSET=b.dataset.a;localStorage.setItem('asset',ASSET);refreshCopy()});
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3800)}
$('#search').onsubmit=async e=>{e.preventDefault();const a=$('#q').value.trim();if(!a)return;
 $('#go').disabled=true;$('#err').classList.add('hidden');
 try{const d=await fetch(`/api/detect?addr=${encodeURIComponent(a)}&chain=${CHAIN}`).then(r=>r.json());
  if(d.error){showErr(d.error);$('#go').disabled=false;return}
  const msgs=[];if(d.chain&&d.chain!==CHAIN){CHAIN=d.chain;msgs.push(CH[CHAIN].n)}if(CHAIN==='btc')ASSET='nft';
  if(d.asset&&d.kind==='token'&&d.asset!==ASSET){ASSET=d.asset;msgs.push(ASSET==='nft'?'NFTs':'Memecoins')}
  if(d.kind&&d.kind!==MODE){MODE=d.kind;msgs.push(d.kind==='token'?'Scan':'Check a wallet')}
  localStorage.setItem('chain',CHAIN);localStorage.setItem('asset',ASSET);setMode(MODE,true);if(msgs.length)toast('Switched to '+msgs.join(' · ')+' for that address.')}catch(_){}
 start(MODE,a,$('#fresh').checked)};
$('#q').addEventListener('paste',()=>setTimeout(()=>$('#q').value.trim().length>=26&&$('#search').requestSubmit(),50));
async function fetchResult(c,as,k,a){const j=await fetch('/api/result/'+encodeURIComponent(rkey(c,as,k,a))).then(r=>r.ok?r.json():null).catch(()=>null);return j&&j.result}
async function runJob(kind,a,fresh,onProg,c=CHAIN,as=ASSET){
 if(!fresh){const r=await fetchResult(c,as,kind,c in{eth:1,base:1,robinhood:1}?a.toLowerCase():a);if(r)return r}
 const r=await fetch(kind==='token'?'/api/analyze':'/api/wallet',{method:'POST',body:JSON.stringify({addr:a,chain:c,asset:as,fresh})}).then(r=>r.json());
 if(r.error)throw new Error(r.error);
 for(;;){await new Promise(z=>setTimeout(z,1500));const j=await fetch('/api/job/'+r.job).then(r=>r.json()).catch(()=>({state:'running',status:'Reconnecting…'}));
  if(onProg)onProg(j);if(j.state==='done')return j.result;if(j.state==='error'||j.state==='missing')throw new Error(j.status||'Job lost, try again')}}
async function start(kind,a,fresh){history.replaceState(null,'',`?chain=${CHAIN}&asset=${ASSET}&${kind==='token'?'mint':'wallet'}=${encodeURIComponent(a)}`);$('#out').innerHTML='';LASTK=null;
 prog('Starting…',2);
 try{const r=await runJob(kind,a,fresh,j=>{if(j.result&&(kind==='token'?j.result.wallets:j.result.positions))show(kind,j.result,true);if(j.state==='running')prog(j.status,estimate(kind,j.status))});
  prog('Done',100);setTimeout(hideProg,700);show(kind,r,false)}catch(e){hideProg();showErr(e.message)}
 $('#go').disabled=false}
function estimate(kind,s){s=s||'';const f=(re,a,b)=>{const m=s.match(re);return m?a+(b-a)*Math.min(1,(+m[1].replace(/,/g,''))/(+m[2].replace(/,/g,''))):null};let v;
 if((v=f(/(\d+)\/(\d+) wallets/,42,80))!=null)return v;if((v=f(/Peak prices.*?(\d+)\/(\d+)/,84,98))!=null)return v;if((v=f(/Collections: (\d+)\/(\d+)/,30,95))!=null)return v;if((v=f(/(\d+)\/(\d+) windows/,8,40))!=null)return v;
 if((v=f(/sells outside the sample: (\d+)\/(\d+)/,50,64))!=null)return v;if((v=f(/Launch times: (\d+)\/(\d+)/,64,84))!=null)return v;
 const m=s.match(/(\d+) unique buyers/);if(m)return 10+28*Math.min(1,m[1]/40);
 return /DexScreener|Looking/.test(s)?3:/first|Scanning|Reading/.test(s)?8:/activity|Checking/.test(s)?30:/Track|history|holdings/.test(s)?45:/Pric|Paperhands/.test(s)?85:5}
let pctNow=0;function prog(t,p){$('#progress').classList.remove('hidden');pctNow=Math.max(pctNow,p||0);$('#pstep').textContent=t;$('#ppct').textContent=Math.round(pctNow)+'%';$('#pfill').style.transform=`scaleX(${pctNow/100})`}
function hideProg(){$('#progress').classList.add('hidden');pctNow=0}
function showErr(t){const e=$('#err');e.textContent=t;e.classList.remove('hidden')}
let LASTK=null;function show(kind,r,partial){const k=kind+':'+(r.mint||r.wallet),o=$('#out'),same=k===LASTK&&o.childElementCount>0;o.classList.toggle('still',same);LASTK=k;kind==='token'?renderToken(r,partial):renderWallet(r,partial);if(!same)o.querySelectorAll('.tile .v:not(.small2),.st .v,.ds .n').forEach(countUp);if(!partial)remember(kind,r)}
// ---------- recent scans ----------
function label(kind,r){return kind==='token'?((r.asset==='nft'?'🖼️ ':'$')+((r.token||{}).symbol||sh(r.mint))):sh(r.wallet)}
function remember(kind,r){let L=JSON.parse(localStorage.getItem('recent')||'[]');const addr=kind==='token'?r.mint:r.wallet;
 const v=kind==='wallet'?VERD(r.verdict):null;L=L.filter(x=>x.a!==addr);L.unshift({k:kind,a:addr,c:r.chain||'sol',as:r.asset||'coin',l:label(kind,r),v:v?v.c:''});
 localStorage.setItem('recent',JSON.stringify(L.slice(0,10)));drawRecent()}
function drawRecent(){const L=JSON.parse(localStorage.getItem('recent')||'[]');$('#recent').innerHTML=L.length?`<span class="lbl">Recent</span>`+L.map((x,i)=>`<button class="chip" data-i="${i}"><span class="cbadge c-${x.c||'sol'}">${(x.c||'sol').slice(0,3)}</span>${x.k==='token'?'':`<span class="d ${x.v}"></span>`}${esc(x.l)}</button>`).join(''):'';
 $$('#recent .chip').forEach(b=>b.onclick=()=>openItem(L[+b.dataset.i]))}
function openItem(x){CHAIN=x.c||'sol';ASSET=x.as||'coin';setMode(x.k,true);$('#q').value=x.a;closeSheet();window.scrollTo({top:0,behavior:'smooth'});start(x.k,x.a,false)}
drawRecent();
// ---------- token / collection scan ----------
function renderToken(r,partial){document.body.classList.add('results');TRES=r;const t=r.token||{},o=$('#out'),ws=r.wallets||[],u=r.unit||'SOL',nft=r.asset==='nft',C=chOf(r);
 const facts=t.facts?`<div class="tiles">${Object.entries(t.facts).slice(0,12).map(([k,v])=>`<div class="tile anim"><div class="k">${esc(k)}</div><div class="v small2">${esc(v)}</div></div>`).join('')}</div>`:'';
 o.innerHTML=`<div class="head anim">${t.image?`<img src="${esc(t.image)}" alt="">`:''}<div style="min-width:0"><div class="t">${esc(t.name||'')} <span class="dim">${nft?'':'$'}${esc(t.symbol||'?')}</span> <span class="cbadge big c-${(r&&r.chain)||'sol'}">${C.n}</span></div><div class="s mono">${esc(r.mint)}</div>
 <div class="pills">${t.mcap?`<span class="pill">mcap $${Math.round(t.mcap).toLocaleString()}</span>`:''}${t.floor!=null?`<span class="pill">floor ${money(t.floor,r.chain==='sol'?'SOL':'ETH')}</span>`:''}${t.soulbound?'<span class="pill y">soulbound</span>':''}${r.launch_ts?`<span class="pill">${nft?'first mint':'launched'} ${when(r.launch_ts)}</span>`:''}${r.n_early?`<span class="pill">${r.n_early} first ${nft?'minters':'buyers'}</span><span class="pill">${(r.excluded||[]).length} ${nft?'bots/farms':'snipers/bots'} removed</span>`:''}${partial?'<span class="pill y">updating…</span>':''}</div></div>
 <button class="star" title="Add to watchlist" onclick="watchToggle('token')">${isWatched(r.mint)?'★':'☆'}</button></div>
 ${!nft&&!partial&&r.chain!=='btc'?`<div class="fbar anim"><button class="fbtn" onclick="feat('rug')">🚦 Rug Check</button><button class="fbtn" onclick="feat('cabal')">🕸️ Cabal</button></div><div id="fpanel"></div>`:''}
 ${facts}
 <div class="bar2"><h2>${r.chain==='btc'?'What we can see':nft?'Early minters, best first':'Early buyers, best first'}</h2>${ws.length?`<button class="toggle ${TABLE?'on':''}" id="tt">${TABLE?'▦ Cards':'☰ Table'}</button>`:''}</div>
 ${TABLE?tokenTable(r,ws):`<div class="grid">${ws.map((w,i)=>walletCard(r,w,i)).join('')||`<div class="dim">${partial?'Working…':'No wallets to show.'}</div>`}</div>`}
 ${(r.excluded||[]).length?`<details class="notes excl"><summary>${r.excluded.length} early wallets removed (${nft?'bots, airdrops, farms':'dev, snipers, bots'})</summary>${r.excluded.map(w=>`<div class="small" style="padding:4px 0">#${w.rank} <a class="mono" target="_blank" href="${C.acct}${w.wallet}">${sh(w.wallet)}</a> +${dur(w.secs)} · ${money(w.sol,u)} · ${esc(w.flags.join(', '))}</div>`).join('')}<br></details>`:''}
 <details class="notes"><summary>ⓘ How to read this</summary><ul>${(r.notes||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details>`;
 if($('#tt'))$('#tt').onclick=()=>{TABLE=!TABLE;renderToken(TRES,partial)};
 $$('.wc').forEach(c=>c.onclick=e=>{if(e.target.closest('button,a'))return;c.classList.toggle('open')})}
function walletCard(r,w,i){const done=w.n_tokens!=null,b=tier(w),u=r.unit||'SOL',nft=r.asset==='nft',C=chOf(r);return `<div class="wc anim" style="animation-delay:${Math.min(i,12)*45}ms">
 <div class="row"><div><span class="rank">#${i+1}</span><span class="addr mono">${sh(w.wallet)}</span></div>${b?`<span class="badge ${b.c}">${b.t} · ${w.score}</span>`:w.note?`<span class="dim small">${esc(w.note)}</span>`:'<span class="dim small">no history read</span>'}</div>
 <div class="mini"><span>${nft?'Minter':'Buyer'} <b>#${w.rank}</b>, <b>+${dur(w.secs)}</b></span><span>${money(w.sol,u)} ${nft?'paid':'in'}</span>${w.minted>1?`<span>${w.minted} minted</span>`:''}${w.x_this!=null?`<span>This ${nft?'mint':'coin'} ${fx(w.x_this)} now</span>`:''}${(w.flags||[]).map(f=>`<span class="tag">${esc(f)}</span>`).join('')}${w.tx_per_day>=150?`<span class="tag">~${Math.round(w.tx_per_day)} tx/day</span>`:''}</div>
 ${done?`<div class="stats">${nft?`<div class="st"><div class="k">Collections</div><div class="v">${w.n_tokens}</div></div><div class="st"><div class="k">Mints</div><div class="v">${w.mints_total??'n/a'}</div></div>`:`<div class="st"><div class="k">Win rate</div><div class="v">${pct(w.win_rate)}</div></div><div class="st"><div class="k">Best x</div><div class="v">${fx(w.best_x)}</div></div><div class="st"><div class="k">5x+ peaks</div><div class="v">${w.n5}<span class="dim small">/${w.peak_checked}</span></div></div><div class="st"><div class="k">Tokens</div><div class="v">${w.n_tokens}</div></div>`}</div>`:''}
 <div class="actions">${done?`<button class="btn share" onclick="card(${i})">⬇ Card</button>`:''}<button class="btn ghost" onclick="checkWallet('${w.wallet}')">👛 Check wallet</button><a class="btn ghost" target="_blank" href="${C.acct}${w.wallet}">${C.ex} ↗</a></div>
 ${done&&!nft?`<div class="more">${posTable(r,w.positions||[])}</div>`:''}</div>`}
function tokenTable(r,ws){const C=chOf(r);return `<div class="tablewrap anim"><table><tr><th>#</th><th>Wallet</th><th>Entry</th><th>This one</th><th>Tokens</th><th>Win</th><th>Best</th><th>5x/10x</th><th>Score</th><th></th></tr>${ws.map((w,i)=>`<tr><td>${i+1}</td><td><a class="mono" target="_blank" href="${C.acct}${w.wallet}">${sh(w.wallet)}</a></td><td>#${w.rank} +${dur(w.secs)}</td><td>${fx(w.x_this)}</td><td>${w.n_tokens??'…'}</td><td>${pct(w.win_rate)}</td><td>${fx(w.best_x)}</td><td>${w.n5??0}/${w.n10??0}</td><td><b>${w.score??'…'}</b></td><td>${w.n_tokens!=null?`<button class="btn share" style="padding:6px 10px" onclick="card(${i})">Share</button>`:''}</td></tr>`).join('')}</table></div>`}
function posTable(r,P){const u=r.unit||'SOL';if(!P.length)return '<div class="dim small" style="margin-top:10px">No clean trades in the sample.</div>';
 return `<div class="tablewrap" style="margin-top:10px"><table><tr><th>Token</th><th>First buy</th><th>Spent</th><th>Got back</th><th>x now</th><th>x peak</th></tr>${P.slice().sort((a,b)=>(b.first_buy||0)-(a.first_buy||0)).map(p=>`<tr><td><a target="_blank" href="${chOf(r).tok(p.mint)}">${p.symbol?'$'+esc(p.symbol):sh(p.mint)}</a>${p.no_pair?' <span class="dim small">dead</span>':''}</td><td class="dim">${when(p.first_buy)}</td><td>${money(p.sol_in,u)}</td><td>${money(p.sol_out,u)}</td><td>${fx(p.x_now)}</td><td>${p.x_peak?fx(p.x_peak):'<span class="dim">n/a</span>'}</td></tr>`).join('')}</table></div>`}
function checkWallet(a){const r=TRES||{};CHAIN=r.chain||CHAIN;ASSET=r.chain==='btc'?'nft':(r.asset||ASSET);setMode('wallet',true);$('#q').value=a;window.scrollTo({top:0,behavior:'smooth'});start('wallet',a,false)}
// ---------- wallet check ----------
function renderWallet(r,partial){document.body.classList.add('results');WRES=r;const o=$('#out'),a=r.activity||{},v=VERD(r.verdict),u=r.unit||'SOL',nft=r.asset==='nft',C=chOf(r),D=degen(r);
 const tile=(k,val,s='',d=0)=>`<div class="tile anim" style="animation-delay:${d*40}ms"><div class="k">${k}</div><div class="v">${val}</div><div class="s">${s}</div></div>`;
 o.innerHTML=`<div class="head anim"><div style="min-width:0"><div class="t mono">${sh(r.wallet)} <span class="cbadge big c-${(r&&r.chain)||'sol'}">${C.n}${nft?' · NFTs':''}</span></div><div class="s mono"><a target="_blank" href="${C.acct}${r.wallet}">${r.wallet}</a></div>
 <div class="pills"><span class="pill">${r.sampled_txs} ${nft?'items/txs':'txs'} read</span><span class="pill">~${a.tx_per_day??'?'} ${a.basis||'txs'}/day</span>${a.raw_tx_per_day?`<span class="pill">${Math.round(a.raw_tx_per_day).toLocaleString()} incl. spam</span>`:''}${a.contract?'<span class="pill y">contract wallet</span>':''}${partial?'<span class="pill y">updating…</span>':''}</div></div>
 <button class="star" title="Add to watchlist" onclick="watchToggle('wallet')">${isWatched(r.wallet)?'★':'☆'}</button></div>
 ${v?`<div class="verdict ${v.c} anim"><div class="big">${v.e} ${v.t}</div><div class="conf ${v.c}">Confidence: <b>${r.confidence}</b>${meter(r.confidence)}${r.confidence_why?`<span class="info" tabindex="0" role="note" aria-label="Why" data-tip="${esc(r.confidence_why)}">ⓘ</span>`:''}</div>
 <ul class="reasons">${(r.reasons||[]).slice(0,2).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>${(r.reasons||[]).length>2?`<details class="morer"><summary>+${r.reasons.length-2} more reasons</summary><ul class="reasons">${r.reasons.slice(2).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}<div class="actions" style="justify-content:center"><button class="btn share" onclick="wcard()">⬇ Share card</button><a class="btn ghost" target="_blank" href="${C.acct}${r.wallet}">${C.ex} ↗</a></div></div>
 ${partial?'':`<div class="fbar anim"><button class="fbtn hot" onclick="feat('wrapped')">🎁 Wrapped</button><button class="fbtn" onclick="feat('roast')">🔥 Roast</button><button class="fbtn" onclick="feat('copysim')" title="Copy Simulator">🧪 Copy Sim</button>${nft?'':`<button class="fbtn" onclick="feat('paperhands')" title="Paperhands Pain">🧻 Paperhands</button>`}<button class="fbtn" onclick="feat('vs')" title="Wallet vs Wallet">⚔️ VS</button><button class="fbtn" onclick="feat('alerts')" title="Telegram alerts">🔔 Alert</button></div><div id="fpanel"></div>`}
 <div class="degen anim"><div class="ds"><div class="k">Degen Score</div><div class="n">${D.score}<span>/1000</span></div><div class="dim small">${esc(D.title)}</div></div><div class="badges">${D.badges.map(b=>`<span class="bdg" title="${esc(b.why)}">${b.e} ${esc(b.t)}</span>`).join('')||'<span class="dim small">No badges yet</span>'}</div></div>
 <div class="tiles">${nft?tile('Collections',r.collections??(r.positions||[]).length,`${a.mints??'?'} mints`,0)+tile('Floor ≥ mint',pct(r.win_rate),`${r.wins}/${r.n_tokens} priced`,1)+tile('Best x',fx(r.best_x_now),'floor vs mint',2)+tile('Self-initiated',r.self_share==null?'n/a':Math.round(r.self_share*100)+'%','not airdrops',3)+tile('Typical mint',dur(r.median_delay),'after first mint',4)+tile('Spent',money(r.spent_sol,u),'mint cost',5)+tile('Holding now',r.holding_now??'n/a','collections',6)+tile('Mints/day',a.tx_per_day??'n/a','in sample',7)
 :tile('Win rate',pct(r.win_rate),`${r.wins}/${r.n_tokens} tokens`,0)+tile('Net P/L',`<span class="${r.pnl_sol>=0?'g':'r'}">${money(r.pnl_sol,u,true)}</span>`,`on ${money(r.spent_sol,u)}`,1)+tile('Best x',fx(r.best_x_now),'sold + held',2)+tile('5x+ peaks',`${r.n5}<span class="dim small"> / ${r.peak_checked}</span>`,`${r.n10} hit 10x+`,3)+tile('Typical entry',dur(r.median_delay),'after launch/pool',4)+tile('Median hold',dur(r.median_hold),'buy → last sell',5)+tile('Snipes',r.sniper_share==null?'n/a':Math.round(r.sniper_share*100)+'%','first seconds',6)+tile('Holding now',r.holding_now,'tokens',7)}</div>`:'<div class="dim" style="margin:14px 0">Verdict appears when the check finishes…</div>'}
 <div class="bar2"><h2>${nft?'Recent mints':'Recent trades'}</h2><button class="toggle ${TABLE?'on':''}" id="tt">${TABLE?'▦ Cards':'☰ Table'}</button></div>
 ${TABLE?tradeTable(r,r.positions||[]):`<div class="grid">${(r.positions||[]).map((p,i)=>tradeCard(r,p,i)).join('')||'<div class="dim">Nothing found in the sample.</div>'}</div>`}
 <details class="notes"><summary>ⓘ How to read this</summary><ul>${(r.notes||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details>`;
 $('#tt').onclick=()=>{TABLE=!TABLE;renderWallet(WRES,partial)};$$('.tc').forEach(c=>c.onclick=e=>{if(e.target.closest('a'))return;c.classList.toggle('open')})}
function tradeCard(r,p,i){const u=r.unit||'SOL',nft=r.asset==='nft';return `<div class="tc wc anim" style="animation-delay:${Math.min(i,14)*35}ms"><div class="row"><span class="sym">${p.symbol?(nft?'':'$')+esc(p.symbol):sh(p.mint)}</span><span>${fx(p.x_now)}</span></div>
 <div class="mini"><span>${when(p.first_buy)}</span>${p.delay!=null?`<span>entry <b>${dur(p.delay)}</b> after ${esc(p.delay_ref)}</span>`:p.pre_pool?'<span>bought on the curve, before the pool</span>':''}${p.holding?'<span class="g">holding</span>':''}${p.sniped?'<span class="tag">sniped</span>':''}${p.soulbound?'<span class="tag">soulbound</span>':''}${p.free_mint?'<span class="tag">free mint</span>':''}${p.how?`<span class="tag">${esc(p.how)}</span>`:''}${p.kind?`<span class="tag">${esc(p.kind)}</span>`:''}${p.transferred?'<span class="tag">moved out</span>':''}${p.no_pair?'<span class="tag">dead, valued 0</span>':''}</div>
 <div class="more"><div class="mini" style="margin-top:10px"><span>Spent <b>${money(p.sol_in,u)}</b></span>${nft?`<span>Floor <b>${p.floor!=null?money(p.floor,u):'n/a'}</b></span><span>${p.n_buys} item(s)</span>`:`<span>Got back <b>${money(p.sol_out,u)}</b></span><span>Realized ${p.realized_x!=null?fx(p.realized_x):'<span class="dim">no sells</span>'}</span><span>Peak ${p.x_peak?fx(p.x_peak):'n/a'}</span><span>Hold <b>${dur(p.hold_secs)}</b></span><span>${p.n_buys} buys / ${p.n_sells} sells</span>`}<a target="_blank" href="${assetLink(r,p.mint)}">view ↗</a></div></div></div>`}
function tradeTable(r,P){const u=r.unit||'SOL';return `<div class="tablewrap anim"><table><tr><th>Item</th><th>First buy</th><th>Entry after</th><th>Spent</th><th>Got back</th><th>Realized</th><th>x now</th><th>x peak</th><th>Hold</th><th>Holding</th></tr>${P.map(p=>`<tr><td><a target="_blank" href="${assetLink(r,p.mint)}">${p.symbol?esc(p.symbol):sh(p.mint)}</a></td><td class="dim">${when(p.first_buy)}</td><td>${p.delay!=null?dur(p.delay)+' '+esc(p.delay_ref):'n/a'}</td><td>${money(p.sol_in,u)}</td><td>${money(p.sol_out,u)}</td><td>${p.realized_x!=null?fx(p.realized_x):'none'}</td><td>${fx(p.x_now)}</td><td>${p.x_peak?fx(p.x_peak):'n/a'}</td><td>${dur(p.hold_secs)}</td><td>${p.holding?'yes':'no'}</td></tr>`).join('')}</table></div>`}
// ---------- share cards (no creator credit on cards) ----------
function cardBase(g,sub,accent){const grd=g.createLinearGradient(0,0,1200,675);grd.addColorStop(0,'#05080a');grd.addColorStop(1,'#08261a');g.fillStyle=grd;g.fillRect(0,0,1200,675);
 const rg=g.createRadialGradient(1040,90,0,1040,90,620);rg.addColorStop(0,'rgba(57,255,136,.22)');rg.addColorStop(1,'rgba(57,255,136,0)');g.fillStyle=rg;g.fillRect(0,0,1200,675);
 const rg2=g.createRadialGradient(120,640,0,120,640,520);rg2.addColorStop(0,'rgba(124,92,255,.16)');rg2.addColorStop(1,'rgba(124,92,255,0)');g.fillStyle=rg2;g.fillRect(0,0,1200,675);
 g.strokeStyle='rgba(120,255,180,.05)';g.lineWidth=1;for(let x=0;x<=1200;x+=40){g.beginPath();g.moveTo(x,0);g.lineTo(x,675);g.stroke()}for(let y=0;y<=675;y+=40){g.beginPath();g.moveTo(0,y);g.lineTo(1200,y);g.stroke()}
 g.save();g.strokeStyle=accent;g.shadowColor=accent;g.shadowBlur=24;g.globalAlpha=.75;g.lineWidth=3;if(g.roundRect){g.beginPath();g.roundRect(28,28,1144,619,28);g.stroke()}else g.strokeRect(28,28,1144,619);g.restore();
 g.save();g.shadowColor='#39ff88';g.shadowBlur=18;g.fillStyle='#39ff88';g.font='800 30px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText('◎ '+CFG.APP_NAME,70,100);g.restore();g.font='800 30px "Space Grotesk",Inter,system-ui,sans-serif';const nw=g.measureText('◎ '+CFG.APP_NAME).width;g.fillStyle='#8b9bb0';g.font='24px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(sub,70+nw+16,100)}
function stat(g,x,y,lab,val,col){g.fillStyle='#8b95a5';g.font='700 20px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(lab,x,y);g.fillStyle=col;g.font='900 62px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(val,x,y+70)}
const cx=x=>x==null?'n/a':(x>=100?x.toFixed(0):x.toFixed(1))+'x';
function finish(c,name,inline){const url=c.toDataURL('image/png');if(inline||window.INLINE_PNG){document.body.innerHTML=`<img src="${url}" style="display:block;max-width:100%">`;return}const a=document.createElement('a');a.download=name;a.href=url;a.click()}
function foot(g,t,y=560){g.fillStyle='#7d8899';g.font='20px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(t,72,y)}
function card(i,inline){const w=TRES.wallets[i],t=TRES.token||{},nft=TRES.asset==='nft',c=$('#card'),g=c.getContext('2d');cardBase(g,(nft?'early minter':'early buyer')+' · '+chOf(TRES).n,`#22e58b`);
 g.fillStyle='#fff';g.font='800 64px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillText(sh(w.wallet),70,205);g.fillStyle='#8b95a5';g.font='26px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`${nft?'Minter':'Buyer'} #${w.rank} of ${nft?'':'$'}${t.symbol||'?'}, ${dur(w.secs)} after ${nft?'first mint':'launch'}`,72,252);
 if(nft){stat(g,72,345,'COLLECTIONS',''+(w.n_tokens??'n/a'),'#39ff88');stat(g,400,345,'THIS MINT NOW',cx(w.x_this),'#6cc4ff');stat(g,760,345,'SCORE',''+w.score,'#ffc94a')}
 else{stat(g,72,345,'WIN RATE',w.win_rate==null?'n/a':Math.round(w.win_rate*100)+'%',w.win_rate>=.5?'#39ff88':'#ffc94a');stat(g,400,345,'BEST MULTIPLE',cx(w.best_x),'#39ff88');stat(g,760,345,'5X+ PEAKS',''+w.n5,'#6cc4ff')}
 foot(g,`Estimate · ${w.n_tokens??0} ${nft?'collections':'tokens'} checked · public on-chain data · not financial advice`,520);
 finish(c,`${CFG.APP_NAME}-${sh(w.wallet)}.png`,inline)}
function wcard(inline){const r=WRES,v=VERD(r.verdict),col={g:'#39ff88',y:'#ffc94a',r:'#ff5f73'}[v.c],c=$('#card'),g=c.getContext('2d');cardBase(g,'wallet check · '+chOf(r).n,col);
 g.fillStyle='#fff';g.font='800 56px "JetBrains Mono",ui-monospace,Menlo,monospace';g.fillText(sh(r.wallet),70,190);
 g.fillStyle=col;g.font='900 64px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(v.t.toUpperCase(),70,292);
 const vw=g.measureText(v.t.toUpperCase()).width;g.fillStyle='#8b95a5';g.font='26px "Space Grotesk",Inter,system-ui,sans-serif';g.fillText(`confidence: ${r.confidence.toLowerCase()}`,90+vw,290);
 const D=degen(r);stat(g,72,365,r.asset==='nft'?'FLOOR ≥ MINT':'WIN RATE',r.win_rate==null?'n/a':Math.round(r.win_rate*100)+'%',r.win_rate>=.5?'#39ff88':'#ffc94a');stat(g,340,365,'BEST X',cx(r.best_x_now),'#39ff88');stat(g,580,365,'TYPICAL ENTRY',dur(r.median_delay),'#6cc4ff');stat(g,900,365,'DEGEN',''+D.score,'#ffc94a');
 foot(g,`Estimate · ${r.sampled_txs} txs read · ${r.n_tokens} priced · public on-chain data · not financial advice`,530);
 finish(c,`${CFG.APP_NAME}-wallet-${sh(r.wallet)}.png`,inline)}
// ---------- watchlist ----------
const WL=()=>JSON.parse(localStorage.getItem('watchlist')||'[]');const isWatched=a=>WL().some(x=>x.a===a);
function watchToggle(kind){const r=kind==='token'?TRES:WRES,a=kind==='token'?r.mint:r.wallet;let L=WL();
 if(L.some(x=>x.a===a)){L=L.filter(x=>x.a!==a);toast('Removed from your watchlist.')}else{L.unshift({k:kind,a,c:r.chain||'sol',as:r.asset||'coin',l:label(kind,r),v:kind==='wallet'?(VERD(r.verdict)||{}).c:'',at:Date.now()});toast('Saved to your watchlist (this browser only).')}
 localStorage.setItem('watchlist',JSON.stringify(L.slice(0,100)));kind==='token'?renderToken(r):renderWallet(r)}
// ---------- lazy feature loader ----------
let featP=null;function loadFeatures(){return featP||(featP=new Promise((ok,no)=>{const s=document.createElement('script');s.src='features.js?v=4';s.onload=ok;s.onerror=no;document.head.appendChild(s)}))}
async function feat(name,arg){try{await loadFeatures();window.FEAT[name](arg)}catch(e){showErr('Could not load that feature: '+e.message)}}
function closeSheet(){const s=$('#sheet');document.body.classList.remove('gated');clearTimeout(window.__shT);if(s.classList.contains('hidden'))return;if(RM()){s.classList.add('hidden');s.innerHTML='';return}s.classList.add('closing');window.__shT=setTimeout(()=>{s.classList.add('hidden');s.classList.remove('closing');s.innerHTML=''},240)}
$$('.menu button').forEach(b=>b.onclick=()=>feat(b.dataset.f));
// ---------- deep links ----------
if(new URLSearchParams(location.search).get('shot'))document.body.classList.add('shot');
{const P=new URLSearchParams(location.search),m=P.get('mint'),w=P.get('wallet'),ci=P.get('card');if(P.get('table'))TABLE=true;
 if(P.get('chain'))CHAIN=P.get('chain');if(P.get('asset'))ASSET=P.get('asset');
 const go=(k,a)=>{setMode(k,true);$('#q').value=a;fetchResult(CHAIN,ASSET,k,a).then(r=>{if(r){show(k,r,false);if(P.get('open'))$$('.wc')[0]?.classList.add('open');if(ci!=null)setTimeout(()=>k==='token'?card(+ci,true):wcard(true),300);const f=P.get('f');if(f)setTimeout(()=>feat(f,P.get('arg')),200)}else start(k,a,false)})};
 if(m)go('token',m);else if(w)go('wallet',w);else{setMode(P.get('tab')==='wallet'?'wallet':'token');if(P.get('f'))feat(P.get('f'))}}
// ---------- disclaimer gate ----------
const TERMS_VERSION='2026-10-18.1';
function openGate(){$('#gate').classList.remove('hidden');document.body.classList.add('gated');$('#gaccept').checked=false;$('#genter').disabled=true}
function closeGate(){$('#gate').classList.add('hidden');document.body.classList.remove('gated')}
$('#gaccept').onchange=e=>$('#genter').disabled=!e.target.checked;
$('#genter').onclick=()=>{localStorage.setItem('terms_accepted',JSON.stringify({v:TERMS_VERSION,at:Date.now()}));closeGate()};
$('#openterms').onclick=e=>{e.preventDefault();openGate()};
{let ok=false;try{ok=JSON.parse(localStorage.getItem('terms_accepted')||'null')?.v===TERMS_VERSION}catch(_){}
 if(!ok)openGate()}
// warm the brand fonts so share cards draw with them on first click
if(document.fonts&&document.fonts.load)['700 30px "Space Grotesk"','400 24px "Space Grotesk"','700 50px "JetBrains Mono"'].forEach(f=>document.fonts.load(f).catch(()=>{}));

// ---------- motion helpers ----------
function RM(){return matchMedia('(prefers-reduced-motion: reduce)').matches||document.body.classList.contains('shot')}
function countUp(el){if(RM()||!el||el.dataset.cu)return;const n=[...el.childNodes].find(x=>x.nodeType===3&&/\d/.test(x.nodeValue));if(!n)return;
 const m=n.nodeValue.match(/^(\D*?)([+\-−]?)([\d,]*\.?\d+)(.*)$/s);if(!m)return;const end=parseFloat(m[3].replace(/,/g,''));if(!isFinite(end)||end===0)return;
 const dec=(m[3].split('.')[1]||'').length,com=m[3].includes(','),fmt=v=>{let t=v.toFixed(dec);if(com)t=Number(t).toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec});return m[1]+m[2]+t+m[4]};
 el.dataset.cu=1;const t0=performance.now(),D=650;const step=t=>{if(!n.isConnected)return;const p=Math.min(1,(t-t0)/D),e=1-Math.pow(1-p,3);n.nodeValue=fmt(end*e);if(p<1)requestAnimationFrame(step);else n.nodeValue=m[0]};n.nodeValue=fmt(0);requestAnimationFrame(step)}
