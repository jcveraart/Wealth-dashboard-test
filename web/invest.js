'use strict';
/* Investing: the holdings page (table, treemap, rings), the investment charts, one holding in detail, and account pages. */

const INV = {openList: store.get('hold.open', false), news: null, newsAt: 0, newsFilter: 'all', newsMore: false, newsTimer: null, hist: null, histAt: 0, view: store.get('hold.view', 'table'), group: store.get('hold.group', 'none'), info: {}, acctDaily: null, acctSel: null, hRange: '1y'};
const posId = p => p.isin || 'n:' + p.name.trim().toLowerCase();
const proxyWeights = weights => (Array.isArray(weights)?weights:Object.entries(weights||{}).map(([symbol,weight])=>({symbol,weight}))).filter(p=>p?.symbol&&Number.isFinite(p.weight)&&p.weight>0);

async function loadHist(force) {
  if (INV.hist && !force && Date.now() - INV.histAt < 10 * 60e3 && !INV.hist.updating) return INV.hist;
  try { INV.hist = await cachedJSON('/api/prices/history',{ttl:600e3,force:!!force}); INV.histAt = Date.now(); } catch { INV.hist = {series: {}, proxy: {}, benchmark: {dates: []}}; }
  if (INV.hist.updating && !INV.histTimer) INV.histTimer=setTimeout(() => { INV.histTimer=null;INV.histAt=0;if(['holdings','account'].includes(view))loadHist(true).then(()=>quietInvestmentCharts()); },15000);
  return INV.hist;
}
async function loadAcctDaily() {
  if (INV.acctDaily) return INV.acctDaily;
  try { INV.acctDaily = await cachedJSON('/api/account-history?name=*',{ttl:300e3}); } catch { INV.acctDaily = {}; }
  return INV.acctDaily;
}
const closeAt = (h, iso) => { // last close on or before a date
  let lo = 0, hi = h.dates.length - 1, best = null;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (h.dates[m] <= iso) { best = m; lo = m + 1; } else hi = m - 1; }
  return best == null ? (h.close.length ? h.close[0] : null) : h.close[best];
};

/* the value of today's investments over time, as if held the whole period */
function mixSeries(H, accountName) {
  const bench = H.benchmark && H.benchmark.dates.length ? H.benchmark : null;
  const cal = bench ? bench.dates : [...new Set(Object.values(H.series).flatMap(s => s.dates))].sort();
  if (!cal.length) return [];
  const units = {}, fixed = {value: 0};
  for (const p of S.positions) {
    if (accountName && p.account !== accountName) continue;
    const id = posId(p);
    if (H.series[id] && H.series[id].dates.length) units[id] = (units[id] || 0) + p.units;
    else if (!p.managed || accountName) fixed.value += p.value; // bonds and anything without history count at today's value
  }
  let managed = null;
  const m = S.managed;
  if ((!accountName || accountName === m.name) && !S.positions.some(p => p.managed) && Object.keys(H.proxy || {}).length) {
    const w = proxyWeights(m.proxy).map(p => ({h: H.proxy[p.symbol], w: p.weight})).filter(x => x.h && x.h.dates.length);
    if (w.length) managed = iso => m.value * w.reduce((s, x) => s + x.w * closeAt(x.h, iso) / x.h.close[x.h.close.length - 1], 0) / w.reduce((s, x) => s + x.w, 0);
  } else if (accountName === m.name && !S.positions.some(p => p.managed)) return [];
  const ids = Object.keys(units);
  if (!ids.length && !managed) return [];
  return cal.map(d => [tOf(d), ids.reduce((s, id) => s + units[id] * (closeAt(H.series[id], d) || 0), 0) + fixed.value + (managed ? managed(d) : 0)]);
}
const inRange = (pts, r) => pts.filter(([t]) => t >= tOf(r.from === '0000-01-01' ? '1900-01-01' : r.from) && t <= tOf(r.to.startsWith('9999') ? '2999-01-01' : r.to));

/* ---------- the investments page ----------
   Everything that is not day to day money: brokers, the managed portfolio, bonds, and the savings accounts and
   deposits you count as investments. A lens (asset class) and an account pick drive every number below.
   Top to bottom: today, then how it went over time, then what you hold, then the deeper numbers in one card. */
const INVF = {mode:store.get('inv.mode','daily'), compare:[], cls: store.get('inv.cls', 'all'), acct: store.get('inv.acct', ''), q: '', chart: store.get('inv.chart', 'value'), deep: store.get('inv.deep', 'returns')};
const CLASSES = [['all', 'All'], ['shares', 'Shares & funds'], ['bonds', 'Bonds'], ['cash', 'Savings & deposits'], ['crypto', 'Crypto'], ['other', 'Gold & other']];
const className = c => (CLASSES.find(x => x[0] === c) || [0, 'Other'])[1];
function classOf(it) {
  if (it.kind === 'savings') return 'cash';
  const c = (it.category || '').toLowerCase();
  if (/bond|obligat|treasur|money market|geldmarkt/.test(c)) return 'bonds';
  if (/crypto|bitcoin|ether/.test(c) || /\b(bitcoin|ethereum)\b/i.test(it.name)) return 'crypto';
  if (/gold|silver|commod|real estate|reit|property/.test(c)) return 'other';
  return 'shares';
}
function investItems() {
  // positions, the managed portfolio when its holdings are not imported, and the savings and deposits that count, in one shape
  const pos = S.positions.map(p => ({...p, type: TYPE_OF(p.category), kind: 'position'}));
  const m = S.managed, managed = S.positions.some(p => p.managed) ? [] : [{name: m.name, account: m.name, category: 'Managed portfolio', type: 'Managed', kind: 'managed',
    value: m.value, day_change: m.day_change || 0, profit: m.profit, since_buy_pct: m.start_value ? (m.value / m.start_value - 1) * 100 : null, live: false, units: null}];
  const sav = S.savings.filter(s => s.invest).map(s => ({name: s.name, account: s.name, bank: s.bank, category: s.maturity ? 'Deposit' : 'Savings account', type: s.maturity ? 'Deposits' : 'Savings',
    value: s.value, region:s.region||s.country||null, day_change: 0, profit: s.accrued || 0, since_buy_pct: null, rate: s.rate_pct, maturity: s.maturity, live: false, kind: 'savings', units: null, price: null}));
  return [...pos, ...managed, ...sav].map(it => ({...it, cls: classOf(it)}));
}
const invAccounts = () => INVF.cls === 'all' ? [...new Set([...S.accounts.filter(a=>a.value || a.cash).map(a=>a.name), S.managed.name, ...S.savings.filter(s=>s.invest).map(s=>s.name)])] : [...new Set(investItems().filter(it=>it.cls===INVF.cls).map(accountOfItem))];
const accountOfItem = it => it.managed ? S.managed.name : it.account;
const itemOpen = it => it.kind === 'position' ? 'holding:' + posId(it) : 'account:' + accountOfItem(it);
const holdingLiveKey = p => JSON.stringify([itemOpen(p),accountOfItem(p)]);
function invFiltered(items = investItems(), {cls = INVF.cls, acct = INVF.acct} = {}) {
  const q = INVF.q.toLowerCase();
  return items.filter(it => (cls === 'all' || it.cls === cls) && (!acct || accountOfItem(it) === acct)
    && (!q || it.name.toLowerCase().includes(q) || (it.isin || '').toLowerCase().includes(q)));
}
const BENCHES = [['IWDA.AS', 'MSCI World'], ['VWCE.DE', 'FTSE All-World'], ['CSPX.AS', 'S&P 500'], ['^AEX', 'AEX'], ['EUNA.AS', 'Global bonds']];
const DEEP = [['returns', 'Monthly returns'], ['income', 'Dividends'], ['coming', 'Coming up'], ['costs', 'Costs'], ['money', 'Money put in']];

function holdings() {
  const items=investItems();
  if (INVF.cls!=='all' && !items.some(i=>i.cls===INVF.cls)) INVF.cls='all';
  const accounts=invAccounts();
  if(INVF.acct && !accounts.includes(INVF.acct)) { INVF.acct=''; store.set('inv.acct',''); }
  const list=invFiltered(items), daily=!['cash','bonds'].includes(INVF.cls) && INVF.mode!=='history';
  const brokerCash=INVF.cls==='all' ? S.accounts.filter(a=>!INVF.acct || a.name===INVF.acct).reduce((s,a)=>s+a.cash,0):0;
  const total=list.reduce((s,p)=>s+p.value,0), day=list.reduce((s,p)=>s+(p.day_change||0),0), profit=list.reduce((s,p)=>s+(p.profit||0),0);
  const classes=CLASSES.filter(([c])=>c==='all' || items.some(i=>i.cls===c));
  const deepTabs=['cash','bonds'].includes(INVF.cls)?[]:DEEP.filter(([k])=>k!=='returns' && (k==='income' && list.some(p=>p.kind==='position') || k==='coming' && list.some(p=>p.maturity) || ['costs','money','plans'].includes(k)&&INVF.cls==='all'));
  if(deepTabs.length && !deepTabs.some(([k])=>k===INVF.deep)) INVF.deep=deepTabs[0][0];
  const lensCard=INVF.cls==='bonds'?'Bond ladder':INVF.cls==='cash'?'Interest rates':'Year by year';
  const unknown=S.savings.filter(s=>s.invest_unknown);
  $('#view').innerHTML=`<div class="stack-y inv">
    ${unknown.length?`<details class="card inv-unclear"><summary>${unknown.length===1?`Does ${esc(unknown[0].name)} count as an investment?`:`Do these ${unknown.length} savings accounts count as investments?`}</summary>${unknown.map(s=>`<div class="list-row"><span>${esc(s.name)} ${eur(s.value)}</span><span><button class="btn ghost sm" data-inv-yes="${esc(s.name)}">Investment</button> <button class="btn ghost sm" data-inv-no="${esc(s.name)}">Cash</button></span></div>`).join('')}</details>`:''}
    <div class="inv-bar"><div class="fchips investment-filter-chips" role="group" aria-label="Investment filters">${classes.map(([c,label])=>`<button type="button" data-invest-class="${c}" aria-pressed="${INVF.cls===c}">${esc(label)}</button>`).join('')}<span class="chip-divider" aria-hidden="true"></span>${[['','All accounts'],...accounts.map(n=>[n,n])].map(([n,label])=>`<button type="button" data-invest-account="${esc(n)}" aria-pressed="${INVF.acct===n}">${esc(label)}</button>`).join('')}</div></div>
    <section class="card inv-hero" data-card="inv-hero"><div class="ih-main"><div class="label">${INVF.cls==='all'?'Investments':esc(className(INVF.cls))}${INVF.acct?' · '+esc(INVF.acct):''}</div>
      <div class="big" data-count="${total+brokerCash}">${eur(total+brokerCash)}</div><div class="day">${INVF.cls==='cash'?'Interest, no daily prices':dayc(day,total)+' today'}</div>
      <div class="ih-sub muted small">${profit?`${sgn(profit)} profit since you started`:''}${brokerCash?' · '+eur(brokerCash)+' cash':''}<span id="incomeLine"></span></div></div><div class="ih-rets" id="invRets"></div></section>
    ${!['cash','bonds'].includes(INVF.cls)?`<div class="inv-viewbar" data-mode-controls>${seg('invMode',[['daily','Daily'],['history','History']],daily?'daily':'history')}</div>`:''}
    ${daily?`<section class="card" data-card="inv-recent"><div class="card-head"><h2>Last 20 trading days</h2></div><div id="dailyTrend"></div></section>
      <div class="grid g2 inv-daily-bottom"><section class="card" data-card="inv-moving"><div class="card-head"><h2>Movers</h2><span class="muted small" id="todayNote"></span></div><div id="movers"></div></section>
        <section class="card" id="dailyNewsCard" data-card="inv-news"><div class="card-head"><h2>News</h2></div><div id="dailyNews"></div></section></div>
      <section class="card" id="dailyIdeasCard" data-card="inv-opportunities"><div class="card-head"><h2>Worth a look</h2><a class="linkish small" href="#explore">All opportunities →</a></div><div id="dailyIdeas"></div></section>`:
      `<section class="card inv-main" data-card="inv-chart"><div class="card-head"><h2>${{value:'Value over time',market:'Against the market',drawdown:'Below the high'}[INVF.chart]}</h2><div class="controls" style="margin:0">${seg('invChart',[['value','Value'],['market','Vs market'],['drawdown','Drawdown']],INVF.chart)}${INVF.chart==='market'?`<select id="benchSel" aria-label="Benchmark">${BENCHES.map(([v,l])=>`<option value="${v}" ${((S.profile||{}).benchmark||'IWDA.AS')===v?'selected':''}>${l}</option>`).join('')}</select>`:''}</div></div><div id="invChart"></div><div class="muted small" id="invChartNote"></div></section>
      ${!['cash','bonds'].includes(INVF.cls)?`<section class="card" data-card="inv-statistics"><div id="historyStats" class="inv-stats"></div><p class="sub">Price-based analysis at today’s holdings; deposits, earlier sales and fees are not investment returns.</p></section>`:''}
      <div class="grid ${!['cash','bonds'].includes(INVF.cls)?'g2':''}"><section class="card" data-card="inv-lens"><div class="card-head"><h2>${lensCard}</h2><span class="muted small" id="lensNote"></span></div><div id="lensBox"></div></section>
        ${!['cash','bonds'].includes(INVF.cls)?'<section class="card" data-card="inv-months"><div class="card-head"><h2>Monthly returns</h2></div><div id="historyMonthly"></div></section>':''}</div>
      ${!['cash','bonds'].includes(INVF.cls)?`<details class="card inv-more"><summary>Compare holdings & explore monthly moves</summary><div id="compareChoices" class="fchips"></div><div id="historyCompare"></div><p class="sub">Changes from each series’ first available closing price in the selected period.</p><h4>Monthly price moves</h4><div id="historyDistribution"></div></details>`:''}`}
    <details class="card inv-more" data-card="inv-spread"><summary>How it is spread</summary><select id="hgroup" aria-label="Group allocation">${[['class','By asset class'],['account','By account'],['region','By region'],['sector','By sector'],['currency','By currency']].map(([v,l])=>`<option value="${v}" ${INV.group===v?'selected':''}>${l}</option>`).join('')}</select><div id="spread"></div></details>
    <details class="card inv-more" id="allHold" data-card="inv-list" ${!daily?'open':''}><summary>What you hold <span class="muted small">${list.length} investments</span></summary><div class="controls"><input type="search" id="hq" placeholder="Search investments" value="${esc(INVF.q)}" aria-label="Search investments"><select id="hgroup2" aria-label="Group holdings">${[['class','By asset class'],['account','By account'],['region','By region'],['none','No groups']].map(([v,l])=>`<option value="${v}" ${(INV.listGroup||'class')===v?'selected':''}>${l}</option>`).join('')}</select><label class="check"><input type="checkbox" id="hcomb" ${ui.hold.combine?'checked':''}> Combine accounts</label></div><div id="hbody"></div></details>
    ${deepTabs.length?`<details class="card inv-more" data-card="inv-deep"><summary>Income & account details</summary>${seg('invDeep',deepTabs,INVF.deep)}<div id="deepBox"></div></details>`:''}
  </div>`;
  const setF=(k,v)=>{INVF[k]=v;store.set('inv.'+k,v);holdings();};
  onSeg('invCls',v=>setF('cls',v));onSeg('invMode',v=>setF('mode',v));onSeg('invChart',v=>setF('chart',v));
  $$('[data-invest-class]').forEach(b=>b.onclick=()=>setF('cls',b.dataset.investClass));$$('[data-invest-account]').forEach(b=>b.onclick=()=>setF('acct',b.dataset.investAccount));
  $$('[data-inv-yes],[data-inv-no]').forEach(b=>b.onclick=()=>{const yes=!!b.dataset.invYes,name=b.dataset.invYes||b.dataset.invNo;edit({section:'savings',index:S.savings.findIndex(s=>s.name===name),fields:{invest:yes}});});
  if($('#benchSel')) $('#benchSel').onchange=e=>{INV.hist=null;edit({section:'profile',fields:{benchmark:e.target.value}});};
  $('#hgroup').onchange=e=>{INV.group=e.target.value;store.set('hold.group',INV.group);drawSpread(list);};
  $('#hgroup2').onchange=e=>{INV.listGroup=e.target.value;holdingsBody();};
  $('#hq').oninput=e=>{INVF.q=e.target.value;holdingsBody();};
  $('#hcomb').onchange=e=>{ui.hold.combine=e.target.checked;store.set('combine',ui.hold.combine);holdingsBody();};
  onSeg('invDeep',v=>{INVF.deep=v;store.set('inv.deep',v);drawDeep(list);});
  holdingsBody();drawSpread(list);drawDeep(list);
  if(daily) {drawMovers(list);drawDailyNews(list);}
  investCharts(list);
}

function drawDailyCharts(H,list) {
  const all=mixOf(H,list), recent=all.slice(-20), trend=$('#dailyTrend');
  if(trend) timeChart(trend,{series:[{name:'Selected investments',pts:recent,color:'var(--s1)',area:true}],pct:'index',height:180,sync:true,label:'Last 20 closing prices'});
  const slot=$('#dailyContributions');
  if(slot){const ps=combined(list.filter(p=>p.kind==='position' && p.live)).sort((a,b)=>Math.abs(b.day_change)-Math.abs(a.day_change)).slice(0,8);
    slot.closest('.card').hidden=!ps.length;
    slot.innerHTML=ps.length?chartHtml({type:'hbar',unit:'€',labels:ps.map(p=>p.name),series:[{name:'Today',values:ps.map(p=>Math.round(p.day_change*100)/100)}]},Math.max(280,slot.clientWidth||500)):'';}
}
async function drawDailyNews(list) {
  const selection=JSON.stringify([INVF.cls,INVF.acct]);
  const N=await loadNews(), slot=$('#dailyNews');if(!slot || INVF.mode==='history' || selection!==JSON.stringify([INVF.cls,INVF.acct])) return;
  const ids=new Set(list.filter(p=>p.kind==='position' && /stock/i.test(p.category)).map(posId));
  const seen=new Set(), items=(N.items||[]).filter(n=>ids.has(n.pid) && !seen.has(n.id) && seen.add(n.id));
  if(!items.length){$('#dailyNewsCard').hidden=true;$('#dailyNewsCard').parentElement.classList.remove('g2');return;}
  slot.innerHTML=items.slice(0,3).map(newsRow).join('')+(items.length>3?`<details class="opp-more news-fold"><summary>More headlines</summary>${items.slice(3,15).map(newsRow).join('')}</details>`:'');
}
async function drawDailyIdeas(list) {
  try{const data=await (await fetch('/api/opportunities',{cache:'no-store'})).json(), slot=$('#dailyIdeas');if(!slot || INVF.mode==='history')return;
    const ids=new Set(list.filter(p=>p.kind==='position').map(posId));
    const signals=(data.signals||[]).filter(r=>r.open?.startsWith('holding:')?ids.has(r.open.slice(8)):INVF.cls==='all').slice(0,3);
    const ideas=INVF.cls==='shares' && !INVF.acct?(data.ideas?.ideas||[]).filter(r=>['ETF','Stock'].includes(r.type)).slice(0,Math.max(0,3-signals.length)):[];
    if(!signals.length && !ideas.length){$('#dailyIdeasCard').hidden=true;return;}
    slot.innerHTML=[...signals,...ideas].map((r,i)=>`<div class="list-row"><div><b>${esc(r.title)}</b><div class="muted small">${esc(r.detail||r.why||'')}</div></div><button type="button" class="linkish small" data-daily-idea="${i}">Discuss</button></div>`).join('');
    const rows=[...signals,...ideas];$$('[data-daily-idea]',slot).forEach(b=>b.onclick=()=>talkAbout({...rows[+b.dataset.dailyIdea],id:rows[+b.dataset.dailyIdea].id||'idea-'+b.dataset.dailyIdea}));
  }catch{if($('#dailyIdeasCard')) $('#dailyIdeasCard').hidden=true;}
}
async function drawHistoricalAnalysis(H,list,pts) {
  const identity=JSON.stringify([INVF.cls,INVF.acct,INVF.mode,INVF.chart,RANGE.p,RANGE.from,RANGE.to]);
  const analysis=await post('/api/intelligence/history_metrics',{points:pts});
  if(!$('#historyCompare') || identity!==JSON.stringify([INVF.cls,INVF.acct,INVF.mode,INVF.chart,RANGE.p,RANGE.from,RANGE.to]))return;
  if($('#historyMonthly')) drawMonthly(pts,$('#historyMonthly'),analysis);
  const stats=$('#historyStats');
  if(stats){if(pts.length<2){stats.innerHTML='<div class="empty">More closing-price history is needed for this selection.</div>';return;}
    const positive=analysis.positive_months;
    stats.innerHTML=`<div><span class="muted small">Period price change</span><b>${pct(analysis.period_change_pct,1)}</b></div><div><span class="muted small">Largest drawdown</span><b>${pct(analysis.drawdown,1)}</b></div><div><span class="muted small">Annualised volatility</span><b>${analysis.vol==null?'Not enough daily data':analysis.vol.toFixed(1)+'%'}</b></div><div><span class="muted small">Positive months</span><b>${positive} / ${analysis.monthly.length}</b></div>`;
  }
  const distribution=$('#historyDistribution');if(distribution){const edges=[-Infinity,-10,-5,0,5,10,Infinity], labels=['Below −10%','−10 to −5%','−5 to 0%','0 to 5%','5 to 10%','Above 10%'];
    const counts=labels.map((_,i)=>analysis.monthly.filter(m=>m.value>=edges[i] && m.value<edges[i+1]).length);
    distribution.innerHTML=analysis.monthly.length?chartHtml({type:'bar',labels,unit:'months',series:[{name:'Months',values:counts}]},Math.max(280,distribution.clientWidth||800)):'<div class="empty">At least two months of history are needed.</div>';}
  const choices=$('#compareChoices'), chart=$('#historyCompare');if(!choices || !chart)return;
  const unique=[...new Map(list.filter(p=>p.kind==='position' && H.series[posId(p)]?.dates?.length).map(p=>[posId(p),p])).values()].sort((a,b)=>b.value-a.value);
  INVF.compare=(INVF.compare||[]).filter(id=>unique.some(p=>posId(p)===id));if(!INVF.compare.length)INVF.compare=unique.slice(0,3).map(posId);
  const draw=()=>{const r=rangeFor(), series=unique.filter(p=>INVF.compare.includes(posId(p))).map((p,i)=>({name:p.name,pts:inRange(H.series[posId(p)].dates.map((d,n)=>[tOf(d),H.series[posId(p)].close[n]]),r),color:col(i)}));
    timeChart(chart,{series,pct:'index',height:260,sync:true,select:true,label:'Compare closing-price performance'});};
  choices.innerHTML=`<select id="compareAdd" aria-label="Add an investment to compare"><option value="">Compare up to 3 investments</option>${unique.filter(p=>!INVF.compare.includes(posId(p))).map(p=>`<option value="${esc(posId(p))}">${esc(p.name)}</option>`).join('')}</select>`+unique.filter(p=>INVF.compare.includes(posId(p))).map(p=>`<button type="button" data-remove-compare="${esc(posId(p))}" aria-label="Remove ${esc(p.name)}">${esc(p.name)} ×</button>`).join('');
  $('#compareAdd').onchange=e=>{if(e.target.value){if(INVF.compare.length===3)INVF.compare.shift();INVF.compare.push(e.target.value);drawHistoricalAnalysis(H,list,pts);}};
  $$('[data-remove-compare]',choices).forEach(b=>b.onclick=()=>{INVF.compare=INVF.compare.filter(id=>id!==b.dataset.removeCompare);drawHistoricalAnalysis(H,list,pts);});draw();
}

/* today: what each account did, or each investment when there is only one account with prices */
function drawToday(list) {
  const box = $('#todayBox'); if (!box) return;
  const live = list.filter(p => p.kind === 'position' || (p.kind === 'managed' && p.day_change));
  const byAcct = {};
  for (const p of live) { const a = accountOfItem(p); (byAcct[a] = byAcct[a] || {v: 0, d: 0, items: []}); byAcct[a].v += p.value; byAcct[a].d += p.day_change || 0; byAcct[a].items.push(p); }
  const accts = Object.entries(byAcct).filter(([, x]) => x.items.some(p => p.live || p.kind === 'managed'));
  const perHolding = accts.length < 2;
  const rows = perHolding ? combined(live.filter(p => p.live)).map(p => ({name: p.name, v: p.value, d: p.day_change, items: [p]})) : accts.map(([name, x]) => ({name, ...x}));
  rows.sort((a, b) => b.d - a.d);
  if (!rows.length) { box.innerHTML = '<div class="empty">No live prices yet. They come in while the app runs with internet.</div>'; return; }
  // one row per account: a bar that grows left for a loss and right for a gain, scaled to the biggest move
  const top = Math.max(1, ...rows.map(r => Math.abs(r.d))), sum = rows.reduce((s, r) => s + r.d, 0), val = rows.reduce((s, r) => s + r.v, 0);
  box.innerHTML = `<div class="today-rows" data-pick="invday">${rows.map((r, i) => `<button type="button" class="today-row" data-pt="${i}|0">
      <span class="acc-n"><b>${esc(r.name)}</b><span class="muted small">${eur(r.v)}</span></span>
      <span class="dv-bar"><i class="${r.d < 0 ? 'neg' : 'pos'}" style="width:${(Math.abs(r.d) / top * 50).toFixed(1)}%"></i></span>
      <span class="num">${dayc(r.d, r.v)}</span></button>`).join('')}</div>
    ${rows.length > 1 ? `<div class="today-sum"><span>Together</span><span class="num">${dayc(sum, val)}</span></div>` : ''}`;
  PICKS.invday = i => ({title: `${rows[i].name}, today`, rows: rows[i].items.map(p => ({t: p.name, s: `${eur(p.value).replace(/<[^>]+>/g, '')}${p.live ? '' : ', no live price'}`, v: p.day_change || 0, sign: true, open: itemOpen(p)})).sort((a, b) => Math.abs(b.v) - Math.abs(a.v))});
  const when = S.status.last_refresh ? new Date(S.status.last_refresh).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'}) : '';
  $('#todayNote').textContent = `${perHolding ? 'Per investment' : 'Per account'}${when ? ', prices of ' + when : ''}`;
}
function drawMovers(list) {
  const box = $('#movers'); if (!box) return;
  if (!$('#todayBox') && $('#todayNote')) { const when = S.status.last_refresh ? new Date(S.status.last_refresh).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'}) : ''; $('#todayNote').textContent = when ? 'Prices of ' + when : ''; }
  const rel = p => p.value - p.day_change ? p.day_change / (p.value - p.day_change) * 100 : 0;
  const movers = combined(list.filter(p => p.kind === 'position' && p.live && Math.abs(p.day_change) >= 0.5)).sort((a, b) => Math.abs(rel(b)) - Math.abs(rel(a))).slice(0, 6);
  box.closest('.card').hidden=!list.some(p=>p.live);
  const top = Math.max(1, ...movers.map(p => Math.abs(rel(p))));
  box.innerHTML = movers.map(p => `<button type="button" class="list-row row-btn mover" data-open="holding:${esc(posId(p))}" data-ctx="holding:${esc(posId(p))}">
      <div><b>${esc(p.name)}</b><div class="muted small">${eur(p.value)} · ${sgn(p.day_change)}</div></div>
      <div class="mv-bar"><i class="${rel(p) < 0 ? 'neg' : 'pos'}" style="width:${(Math.abs(rel(p)) / top * 100).toFixed(0)}%"></i></div>
      <div class="num">${pct(rel(p), 2)}</div></button>`).join('') || '<div class="empty">Nothing has moved much today.</div>';

}

/* the period returns under the big number: as if you had held today's investments, so money you add doesn't count */
function drawReturns(all, list) {
  const box = $('#invRets'); if (!box) return;
  const total = list.reduce((s, p) => s + p.value, 0), day = list.reduce((s, p) => s + (p.day_change || 0), 0);
  if (INVF.cls === 'cash') {
    const rate = total ? list.reduce((s, p) => s + p.value * (p.rate || 0), 0) / total : 0;
    box.innerHTML = `<div class="ret"><span class="k">Average rate</span><span class="v">${rate.toFixed(2)}%</span></div><div class="ret"><span class="k">Interest a year</span><span class="v">${eur(total * rate / 100)}</span></div>`;
    return;
  }
  if (all.length < 2) { box.innerHTML = ''; return; }
  const last = all[all.length - 1], at = t => { let v = null; for (const [x, y] of all) { if (x <= t) v = y; else break; } return v; };
  const ago = d => last[0] - d * 864e5, y0 = Date.parse(`${new Date().getFullYear() - 1}-12-31`);
  const spans = [['Today', null, null], ['1W', ago(7), {p: 'custom', from: isoD(new Date(ago(7)))}], ['1M', ago(30), {p: 'custom', from: isoD(new Date(ago(30)))}], ['3M', ago(91), {p: '3m'}],
    ['YTD', y0, {p: 'ytd'}], ['1Y', ago(365), {p: '12m'}], ['3Y', ago(1096), {p: 'custom', from: isoD(new Date(ago(1096)))}], ['5Y', ago(1826), {p: 'custom', from: isoD(new Date(ago(1826)))}]];
  box.innerHTML = spans.map(([l, t, r]) => {
    const v = t == null ? (total - day > 0 ? day / (total - day) * 100 : null) : all[0][0] <= t + 5 * 864e5 && at(t) ? (last[1] / at(t) - 1) * 100 : null;
    if (v == null) return '';
    return `<button type="button" class="ret ${r && RANGE.p === r.p && (r.p !== 'custom' || RANGE.from === r.from) ? 'on' : ''}" ${r ? `data-rng="${esc(JSON.stringify(r))}"` : 'disabled'}><span class="k">${l}</span><span class="v">${pct(v, Math.abs(v) < 10 ? 2 : 1)}</span></button>`;
  }).join('');
  $$('[data-rng]', box).forEach(b => b.onclick = () => { const r = JSON.parse(b.dataset.rng); INVF.mode='history'; store.set('inv.mode','history'); setRange(r.p, {from: r.from || '', to: ''}); });
}

function drawSpread(list) {
  const box = $('#spread'); if (!box) return;
  const g = INV.group === 'none' || INV.group === 'type' ? 'class' : INV.group, groups = {};
  for (const it of list) (groups[groupName(it, g)] = groups[groupName(it, g)] || []).push(it);
  const W = Math.max(280, box.clientWidth || 480);
  box.innerHTML = treemap(Object.entries(groups).map(([name, ps]) => ({name, items: ps.map(p => ({id: p.kind === 'position' ? posId(p) : 's:' + p.name, label: p.name, value: p.value,
    change: p.live && p.value - p.day_change ? p.day_change / (p.value - p.day_change) * 100 : null, open: itemOpen(p),
    tip: `${p.name}: ${fmtV(p.value, '€')}${p.live ? `, today ${p.day_change < 0 ? '−' : '+'}${fmtV(Math.abs(p.day_change), '€')}` : ''}`}))})), W, 250);
  $$('.tm-cell', box).forEach(c => { if (c.dataset.open.startsWith('holding:')) c.setAttribute('data-ctx', 'holding:' + c.dataset.open.slice(8)); });
}
/* the card that fits the lens: results per year, a bond ladder, or what each savings account pays */
function drawLens(all, list) {
  const box = $('#lensBox'); if (!box) return;
  const W = Math.max(280, box.clientWidth || 480);
  if (INVF.cls === 'bonds') {
    const dated = list.filter(p => p.maturity), years = {};
    for (const p of dated) { const y = p.maturity.slice(0, 4); years[y] = (years[y] || 0) + p.value; }
    const ys = Object.keys(years).sort();
    box.innerHTML = ys.length ? chartHtml({type: 'bar', unit: '€', labels: ys, series: [{name: 'Matures', values: ys.map(y => Math.round(years[y]))}]}, W) + maturityRows(list)
      : '<div class="empty">None of your bonds has a maturity date. Bond funds never mature, they roll over.</div>';
    return;
  }
  if (INVF.cls === 'cash') {
    const rows = [...list].sort((a, b) => (b.rate || 0) - (a.rate || 0));
    box.innerHTML = rows.length ? chartHtml({type: 'hbar', unit: '%', labels: rows.map(r => r.name), series: [{name: 'Rate', values: rows.map(r => r.rate || 0)}]}, W) + maturityRows(list) : '<div class="empty">No savings counted as investments.</div>';
    loadEcon().then(E => { const n = $('#lensNote'); if (n && E && E.inflation_nl != null) n.textContent = `Inflation ${E.inflation_nl.toFixed(1)}%${E.ecb_rate != null ? `, ECB ${E.ecb_rate.toFixed(2)}%` : ''}`; }).catch(() => {});
    return;
  }
  drawResults(all, list, box);
}
function maturityRows(list) {
  const now = Date.now();
  return [...list.filter(p => p.maturity).map(p => ({name: p.name, date: p.maturity.length === 7 ? p.maturity + '-01' : p.maturity, value: p.value, note: p.kind === 'savings' ? `${p.rate || 0}% a year` : p.category, open: itemOpen(p)}))]
    .filter(r => Date.parse(r.date) >= now - 864e5).sort((a, b) => a.date.localeCompare(b.date)).map(r => { const mo = Math.max(0, (Date.parse(r.date) - now) / 2629800000);
      return `<button type="button" class="list-row row-btn" data-open="${esc(r.open)}"><div><b>${esc(r.name)}</b><div class="muted small">${esc(r.note)} · ${fdate(r.date)}</div></div>
        <div class="num">${eur(r.value)}<div class="muted small">${mo < 1 ? 'this month' : mo < 12 ? `in ${Math.round(mo)} months` : `in ${(mo / 12).toFixed(1)} years`}</div></div></button>`; }).join('');
}
/* one card for the deeper numbers, one tab at a time */
async function drawDeep(list) {
  const box = $('#deepBox'); if (!box) return;
  const W = Math.max(300, box.clientWidth || 900), t = INVF.deep;
  if (t === 'returns') { const H = await loadHist(); drawMonthly(mixOf(H, list), box); }
  else if (t === 'income') { const H = await loadHist(); drawDividends(H, list, box); }
  else if (t === 'coming') box.innerHTML = maturityRows(list) || '<div class="empty">No bonds or deposits with a maturity date.</div>';
  else if (t === 'costs') drawCosts(box, INVF.acct || null, W);
  else if (t === 'money') {
    const names = invAccounts().filter(n => n === INVF.acct || (!INVF.acct && (S.accounts.some(a => a.name === n) || n === S.managed.name)));
    if (!INV.acctSel || !names.includes(INV.acctSel)) INV.acctSel = names[0];
    box.innerHTML = `${names.length > 1 ? `<div class="controls" style="margin:0 0 8px">${seg('vmAcct', names.map(n => [n, n === S.managed.name ? 'Managed' : n]), INV.acctSel)}</div>` : ''}<div id="vm"></div>`;
    onSeg('vmAcct', v => { INV.acctSel = v; $$('[data-seg="vmAcct"] button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v)); drawValueVsMoney($('#vm'), v); });
    drawValueVsMoney($('#vm'), INV.acctSel);
  } else if (t === 'plans') {
    const plans = (S.savings_plans || []).filter(x => x.active);
    box.innerHTML = `<div class="card-head" style="margin-bottom:4px"><p class="sub">${plans.length ? `${eur(plans.reduce((s, x) => s + x.per_month, 0))} a month` : 'None running'}</p><button class="btn ghost" id="planAdd">Add</button></div>
      ${plans.map(x => `<div class="list-row plan-row"><div><b>${esc(x.instrument)}</b><div class="muted small">${esc(x.account)} · ${esc(FREQ[x.frequency] || x.frequency)}${x.next ? ` · next ${fdate(x.next)}` : ''}</div></div>
        <div class="num">${eur(x.amount_eur, x.amount_eur % 1 ? 2 : 0)}<button class="linkish small" data-plan="${S.savings_plans.indexOf(x)}">Edit</button></div></div>`).join('') || '<div class="empty">Automatic monthly buys show here.</div>'}`;
    wirePlans();
  }
}
function talkAbout(r) {
  // a recommendation gets its own conversation, picked up again next time
  const id = 'rec-' + String(r.id).replace(/[^a-z0-9-]/gi, '-').slice(0, 60);
  openChat({conv: id, ctx: {title: r.title, text: `${r.title}. ${r.detail || ''}${r.why ? ' Why it matters: ' + r.why : ''}${r.impact_eur ? ` Worth about €${r.impact_eur} a year.` : ''}`}});
}

/* ---------- the shared parts of the list ---------- */
function holdRows() {
  let rows = invFiltered();
  if (ui.hold.combine) rows = [...combined(rows.filter(r => r.kind === 'position')).map(p => ({...p, type: TYPE_OF(p.category), kind: 'position', cls: classOf(p)})), ...rows.filter(r => r.kind !== 'position')];
  return rows;
}
const groupName = (p, g) => g === 'class' ? className(p.cls || classOf(p)) : g === 'type' ? (p.type || TYPE_OF(p.category)) : g === 'account' ? accountOfItem(p)
  : p.kind === 'savings' ? (g === 'currency' ? 'EUR' : g === 'region' ? (p.region || 'Bank jurisdiction unclassified') : 'Savings') : (!p[g] || /^(other|unknown)$/i.test(p[g]) ? 'Unclassified' : p[g]);
function holdingsBody() {
  const box = $('#hbody'); if (!box) return;
  holdingsTable(box, holdRows());
  if(typeof intBind==='function')intBind(box);
}
function holdingsTable(box, rows) {
  const h = ui.hold, T = S.targets || {}, totalAll = rows.reduce((s, p) => s + p.value, 0) || 1, grp = INV.listGroup || 'class';
  const val = v => v == null ? -Infinity : v;
  rows.sort((a, b) => h.sort === 'name' ? h.dir * -a.name.localeCompare(b.name) : h.dir * (val(a[h.sort]) - val(b[h.sort])));
  const total = rows.reduce((s, p) => s + p.value, 0), day = rows.reduce((s, p) => s + (p.day_change || 0), 0), profit = rows.reduce((s, p) => s + (p.profit || 0), 0);
  const th = (k, l, num = true) => `<th class="sortable ${num ? 'num' : ''}" data-k="${k}">${l}${h.sort === k ? (h.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`;
  const H = INV.hist || {series: {}};
  const trend = p => { const s = p.kind === 'position' && H.series[posId(p)]; return s && s.close.length > 20 ? spark(s.close.slice(-66), {w: 72, h: 22}) : ''; };
  const row = p => `<tr data-live-id="${esc(holdingLiveKey(p))}" ${p.kind === 'position' ? `data-ctx="holding:${esc(posId(p))}"` : ''}>
    <td><button type="button" class="nm linkish" data-open="${esc(itemOpen(p))}">${p.kind === 'position' ? `<span class="dot ${p.live ? '' : 'off'}"></span> ` : ''}${esc(p.name)}</button>
      <div class="meta"><span class="tag">${esc(p.category)}</span>${p.classification_note?`<span class="tag" title="${esc(p.classification_note)} · ${esc(p.classification_date)}">Region: ${esc(p.region||'unknown')} · AI</span>`:''}${typeof investmentBadge==='function'?investmentBadge(p):''}${planFor(p) ? '<span class="tag plan">plan</span>' : ''}${esc(p.kind === 'savings' ? p.bank || '' : p.kind === 'managed' ? (S.managed.mode === 'proxy' ? 'estimated from similar funds' : 'value of ' + fdate(S.managed.last_real_date)) : p.account)}${T[posId(p)] != null ? ` · target ${T[posId(p)]}%` : ''}</div></td>
    <td class="num"><b>${eur(p.value)}</b><div class="wbar"><i style="width:${Math.max(1, p.value / totalAll * 100).toFixed(1)}%"></i></div><div class="meta">${(p.value / totalAll * 100).toFixed(1)}%</div></td>
    <td class="num">${p.kind === 'savings' ? '<span class="muted">·</span>' : p.live === false ? sgn(p.day_change) : dayc(p.day_change, p.value)}</td>
    <td class="num">${sgn(p.profit)}<div class="meta">${p.kind === 'savings' ? `${p.rate || 0}% a year` : pct(p.since_buy_pct)}</div></td>
    <td class="num trend-col">${trend(p)}</td></tr>`;
  let body;
  if (grp === 'none') body = rows.map(row).join('');
  else {
    const groups = {};
    for (const p of rows) (groups[groupName(p, grp)] = groups[groupName(p, grp)] || []).push(p);
    body = Object.entries(groups).sort((a, b) => b[1].reduce((s, p) => s + p.value, 0) - a[1].reduce((s, p) => s + p.value, 0)).map(([g, ps]) => {
      const v = ps.reduce((s, p) => s + p.value, 0);
      return `<tr class="grp-row" data-live-group="${esc(g)}"><td>${esc(g)}</td><td class="num">${eur(v)}<div class="meta">${(v / totalAll * 100).toFixed(1)}%</div></td><td class="num">${dayc(ps.reduce((s, p) => s + (p.day_change || 0), 0), v)}</td><td class="num">${sgn(ps.reduce((s, p) => s + (p.profit || 0), 0))}</td><td></td></tr>${ps.map(row).join('')}`;
    }).join('');
  }
  box.innerHTML = `<div class="table-wrap" data-cap="tall"><table id="htable" class="compact"><thead><tr>${th('name', 'Investment', false)}${th('value', 'Value')}${th('day_change', 'Today')}${th('profit', 'Profit')}<th class="num trend-col">3 months</th></tr></thead>
    <tbody>${body || '<tr><td colspan="5" class="empty">No investments match.</td></tr>'}</tbody>
    <tfoot><tr><td>${rows.length} investments</td><td class="num">${eur(total)}</td><td class="num">${dayc(day, total)}</td><td class="num">${sgn(profit)}</td><td></td></tr></tfoot></table></div>`;
  $$('#htable th.sortable').forEach(th => th.onclick = () => { const k = th.dataset.k; if (h.sort === k) h.dir *= -1; else { h.sort = k; h.dir = k === 'name' ? 1 : -1; } holdingsBody(); });
}
function setTarget(id) {
  const p = S.positions.find(x => posId(x) === id);
  form(`Target for ${p ? p.name : 'this investment'}`, [{k: 'pct', label: 'Share of your self directed investments (%). Leave empty to remove.', type: 'number', value: (S.targets || {})[id] ?? ''}],
    v => edit({section: 'targets', fields: {[id]: v.pct}}, v.pct == null ? 'Target removed' : 'Target saved'));
}

/* ---------- investment charts ---------- */
function mixOf(H, items) {
  // the value of these investments over time as if held the whole period; savings and anything without prices at today's value
  const bench = H.benchmark && H.benchmark.dates.length ? H.benchmark : null;
  const cal = bench ? bench.dates : [...new Set(Object.values(H.series).flatMap(s => s.dates))].sort();
  if (!cal.length) return [];
  const units = {}; let fixed = 0, managed = null;
  const m = S.managed, hasManaged = items.some(p => p.kind === 'managed');
  for (const p of items) {
    const id = p.kind === 'position' ? posId(p) : null;
    if (id && H.series[id] && H.series[id].dates.length) units[id] = (units[id] || 0) + p.units;
    else if (p.kind !== 'managed') fixed += p.value;
  }
  if (hasManaged) {
    // the managed portfolio follows the funds it resembles; without their prices it counts at today's value
    const w = proxyWeights(m.proxy).map(p => ({h: (H.proxy || {})[p.symbol], w: p.weight})).filter(x => x.h && x.h.dates.length);
    if (w.length) managed = iso => m.value * w.reduce((s, x) => s + x.w * closeAt(x.h, iso) / x.h.close[x.h.close.length - 1], 0) / w.reduce((s, x) => s + x.w, 0);
    else fixed += m.value;
  }
  const ids = Object.keys(units);
  if (!ids.length && !managed) return [];
  return cal.map(d => [tOf(d), ids.reduce((s, id) => s + units[id] * (closeAt(H.series[id], d) || 0), 0) + fixed + (managed ? managed(d) : 0)]);
}
async function actualValue(r) {
  // what the selected accounts were really worth each day, from the daily record and the yearly statements
  const daily = await loadAcctDaily(), names = INVF.acct ? [INVF.acct] : invAccounts();
  const dates = [...new Set(names.flatMap(n => (daily[n] || []).map(x => x.date)))].sort();
  // an account missing on a day counts at its last known value (or its first, or today's when it has no record yet)
  const now = n => { const a = S.accounts.find(x => x.name === n); return a ? a.value + a.cash : n === S.managed.name ? S.managed.value : (S.savings.find(x => x.name === n) || {}).value || 0; };
  const series = names.map(n => { const m = new Map((daily[n] || []).map(x => [x.date, x.value])); return {m, first: (daily[n] || [])[0], now: now(n)}; });
  const last = series.map(x => x.first ? x.first.value : x.now);
  let pts = dates.map(d => [tOf(d), series.reduce((sum, x, i) => { if (x.m.has(d)) last[i] = x.m.get(d); return sum + last[i]; }, 0)]);
  if (!INVF.acct && (S.history || []).length) {
    // before the daily record started, the overall history: brokers, managed and the share of savings that counts
    const share = S.totals.savings ? S.totals.invested_savings / S.totals.savings : 0, first = pts.length ? pts[0][0] : Infinity;
    const early = S.history.filter(h => tOf(h.date) < first).map(h => [tOf(h.date), (+h.self_directed || 0) + (+h.managed || 0) + (+h.savings || 0) * share]);
    pts = [...early, ...pts];
  }
  return inRange(pts, r);
}
async function investCharts(list) {
  const identity=JSON.stringify([INVF.cls,INVF.acct,INVF.mode,INVF.chart,RANGE.p,RANGE.from,RANGE.to]);
  const H = await loadHist();
  if (view !== 'holdings' || INT.tab!=='overview' || identity!==JSON.stringify([INVF.cls,INVF.acct,INVF.mode,INVF.chart,RANGE.p,RANGE.from,RANGE.to])) return;
  const all = mixOf(H,list);
  drawReturns(all,list); incomeLine(H,list);
  if ($('#dailyTrend')) { drawDailyCharts(H,list); return; }
  const r = rangeFor(), box = $('#invChart'), note = $('#invChartNote');
  if (!box) return;
  const W = Math.max(300, box.clientWidth || 900);
  const mixAll = mixOf(H, list), mix = inRange(mixAll, r);
  const none = msg => `<div class="empty">${msg}</div>`;
  const offline = !Object.values(H.series).some(s => s.dates.length) && !(H.benchmark && H.benchmark.dates.length);
  const noHist = H.updating ? 'Fetching five years of prices. This takes a minute the first time.' : offline ? 'Price history needs an internet connection. It is fetched once a day.' : 'Not enough price history for this period.';
  if (INVF.chart === 'value') {
    const typed = INVF.cls !== 'all', pts = typed ? mix : await actualValue(r);
    if (!box.isConnected || identity!==JSON.stringify([INVF.cls,INVF.acct,INVF.mode,INVF.chart,RANGE.p,RANGE.from,RANGE.to])) return;
    if (pts.length > 1) {
      timeChart(box, {series: [{name: typed ? 'Value as if held all along' : 'Value', pts, color: 'var(--s1)', area: true}], sync: true, select: true, height: 200, label: 'Value over time'});
      const ch = pts[pts.length - 1][1] - pts[0][1];
      note.innerHTML = `${sgn(ch)} (${pct(ch / pts[0][1] * 100, 1)}) over ${esc(rangeLabel().toLowerCase())}${typed ? ', at today\'s units' : ', including money you added'}. Drag across the chart to read any stretch.`;
    } else if (typed) { box.innerHTML = none(noHist); note.innerHTML = ''; }
    else { box.innerHTML = none('No history yet for this selection. Every day the app runs adds a point, and yearly statements fill in the past.'); note.innerHTML = ''; }
  } else if (INVF.chart === 'market') {
    const b = H.benchmark && H.benchmark.dates.length ? H.benchmark : null;
    if (mix.length > 2 && b) {
      const bpts = inRange(b.dates.map((d, i) => [tOf(d), b.close[i]]), r), base = mix[0][1] / (bpts[0] || [0, 1])[1];
      timeChart(box, {series: [{name: 'Your investments', pts: mix, color: 'var(--s1)'}, {name: H.benchmark_name || 'Benchmark', pts: bpts.map(([t, v]) => [t, v * base]), color: 'var(--muted)'}],
        pct: 'index', sync: true, select: true, height: 200, label: 'Your investments against the market'});
      const me = mix[mix.length - 1][1] / mix[0][1] - 1, mk = bpts.length ? bpts[bpts.length - 1][1] / bpts[0][1] - 1 : 0;
      note.innerHTML = `You ${pct(me * 100, 1)}, ${esc(H.benchmark_name || 'the benchmark')} ${pct(mk * 100, 1)}, ${esc(rangeLabel().toLowerCase())}. As if you had held today's investments the whole time.`;
    } else { box.innerHTML = none(noHist); note.innerHTML = ''; }
  } else {
    if (mix.length > 2) {
      let peak = -Infinity, worst = 0;
      const dd = mix.map(([t, v]) => { peak = Math.max(peak, v); const x = (v / peak - 1) * 100; worst = Math.min(worst, x); return [t, x]; });
      timeChart(box, {series: [{name: 'Below the previous high', pts: dd, area: true, color: 'var(--loss)'}], unit: '%', sync: true, height: 200, zero: true, label: 'Drawdown'});
      note.innerHTML = `Deepest fall from a high: <b>${worst.toFixed(1)}%</b>. A drawdown is how far your investments sat below their best point.`;
    } else { box.innerHTML = none(noHist); note.innerHTML = ''; }
  }
  drawHistoricalAnalysis(H,list,mix);
  drawReturns(mixAll, list);
  drawLens(mixAll, list);
  drawDeep(list);
  incomeLine(H, list);
  holdingsBody();  // again, now the price history is there for the trend column
}
function drawResults(all, list, box) {
  // what your investments earned per year: recorded results from statements, this year from prices
  if (!box) return;
  if (INVF.cls !== 'all') {
    // statements report whole accounts, so a lens uses prices: the change in each calendar year at today's units
    const end = {};
    for (const [t, v] of all) end[new Date(t).getFullYear()] = v;
    const ys = Object.keys(end).sort(), vals = ys.map((y, i) => i ? end[y] - end[ys[i - 1]] : null);
    if (ys.length < 2) { box.innerHTML = '<div class="empty">Not enough price history yet.</div>'; return; }
    box.innerHTML = chartHtml({type: 'bar', unit: '€', labels: ys.slice(1), series: [{name: 'Change', values: vals.slice(1).map(Math.round)}]}, Math.max(280, box.clientWidth || 480))
      + `<div class="muted small">Price change per year, as if you had held today's ${esc(className(INVF.cls).toLowerCase())} all year.</div>`;
    return;
  }
  const accts = INVF.acct ? [INVF.acct] : invAccounts();
  const yf = (S.yearly_flows || []).filter(x => accts.includes(x.account) && (x.profit_eur != null));
  const years = [...new Set(yf.map(x => x.year))].sort();
  const thisYear = new Date().getFullYear();
  const ytd = (() => { const pts = all.filter(([t]) => new Date(t).getFullYear() === thisYear); return pts.length > 1 ? pts[pts.length - 1][1] - pts[0][1] : null; })();
  const interest = list.filter(it => it.kind === 'savings').reduce((s, it) => s + it.value * (it.rate || 0) / 100 * (new Date().getMonth() + 1) / 12, 0);
  const labels = [...years.filter(y => y !== thisYear).map(String), String(thisYear)];
  const vals = [...years.filter(y => y !== thisYear).map(y => yf.filter(x => x.year === y).reduce((s, x) => s + x.profit_eur, 0)), ytd != null ? ytd + interest : (yf.filter(x => x.year === thisYear).reduce((s, x) => s + x.profit_eur, 0) || 0)];
  if (labels.length < 2 && !vals[0]) { box.innerHTML = '<div class="empty">Yearly statements fill this in: import them on the Import page.</div>'; return; }
  box.innerHTML = chartHtml({type: 'bar', unit: '€', labels, series: [{name: 'Result', values: vals.map(v => Math.round(v))}]}, Math.max(280, box.clientWidth || 480))
    + `<div class="muted small">${thisYear} so far is an estimate from prices${interest ? ' and interest' : ''}.</div>`;
}
async function drawMonthly(all, box, cached) {
  if (!box) return;
  if (all.length < 40) { box.innerHTML = '<div class="empty">Not enough price history yet.</div>'; return; }
  const calculated=cached||await post('/api/intelligence/history_metrics',{points:all});
  if(!box.isConnected)return;
  const ret=Object.fromEntries(calculated.monthly.map(m=>[m.month,m.value]));
  const years=Object.keys(calculated.yearly).sort().reverse().slice(0,INV.allYears?99:3);
  const yr=y=>calculated.yearly[y];
  box.innerHTML = heatTable(years, [...MONTHS, 'Year'], (ri, ci) => ci === 12 ? yr(years[ri]) : ret[`${years[ri]}-${String(ci + 1).padStart(2, '0')}`] ?? null, {diverging: true, fmt: v => `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}%`, max: 6})
    + `<button type="button" class="linkish small" id="allYears">${INV.allYears ? 'Last three years' : 'All years'}</button>`;
  $('#allYears').onclick = () => { INV.allYears = !INV.allYears; drawMonthly(all, box, calculated); };
}
function dividendData(H, list) {
  const divs = {}, names = {}, cut = isoD(new Date(Date.now() - 365 * 864e5));
  const pos = list.filter(p => p.kind === 'position');
  for (const p of pos) {
    const s = H.series[posId(p)];
    if (!s || !s.divs) continue;
    for (const [d, a] of s.divs) if (d >= cut) { const m = d.slice(0, 7); divs[m] = divs[m] || {}; divs[m][p.name] = (divs[m][p.name] || 0) + a * p.units; names[p.name] = (names[p.name] || 0) + a * p.units; }
  }
  for (const p of pos) for (const tr of p.trades || []) if ((tr.type === 'dividend' || tr.type === 'distribution') && tr.date >= cut && !(H.series[posId(p)] || {}).divs?.length) {
    const m = tr.date.slice(0, 7); divs[m] = divs[m] || {}; divs[m][p.name] = (divs[m][p.name] || 0) + tr.amount; names[p.name] = (names[p.name] || 0) + tr.amount;
  }
  return {divs, names, year: Object.values(names).reduce((a, b) => a + b, 0)};
}
function incomeLine(H, list) {
  const el = $('#incomeLine'); if (!el) return;
  const d = dividendData(H, list).year, i = list.filter(it => it.kind === 'savings').reduce((s, it) => s + it.value * (it.rate || 0) / 100, 0);
  el.innerHTML = d + i >= 1 ? ` · ${eur(d + i)} a year in ${[d >= 1 ? 'dividends' : '', i >= 1 ? 'interest' : ''].filter(Boolean).join(' and ')}` : '';
}
function drawDividends(H, list, box) {
  if (!box) return;
  const W = Math.max(280, box.clientWidth || 480);
  const {divs, names, year: sumYear} = dividendData(H, list);
  const months = []; for (let i = 11; i >= 0; i--) { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i); months.push(isoD(d).slice(0, 7)); }
  const top = Object.entries(names).sort((a, b) => b[1] - a[1]).map(x => x[0]), keep = top.slice(0, 5);
  if (!top.length) { box.innerHTML = `<div class="empty">${H.updating ? 'Fetching prices and dividends…' : 'No dividends in the last 12 months, or your funds reinvest them.'}</div>`; return; }
  const series = keep.map(n => ({name: n, values: months.map(m => (divs[m] || {})[n] || 0)}));
  if (top.length > 5) series.push({name: 'Other', values: months.map(m => Object.entries(divs[m] || {}).filter(([n]) => !keep.includes(n)).reduce((s, x) => s + x[1], 0))});
  PICKS.divs = (i, k) => ({title: `${mLabel(months[i])}, ${series[k].name}`, rows: Object.entries(divs[months[i]] || {}).filter(([n]) => series[k].name === 'Other' ? !keep.includes(n) : n === series[k].name).map(([n, v]) => ({t: n, s: 'Dividend', v}))});
  box.innerHTML = `<div data-pick="divs">${chartHtml({type: 'stacked', unit: '€', labels: months.map(mLabel), xkeys: months, series, pick: true}, W)}</div><div class="muted small">${fmtV(sumYear, '€')} in the last 12 months</div>`;
}

function drawCosts(box, account, W) {
  if (!box) return;
  const yf = (S.yearly_flows || []).filter(r => !account || r.account === account);
  const years = [...new Set(yf.map(r => r.year))].sort();
  const fees = years.map(y => yf.filter(r => r.year === y).reduce((s, r) => s + (r.fees_eur || 0) + (r.taxes_eur || 0), 0));
  const endVal = y => (S.account_history || []).filter(r => r.date.startsWith(String(y)) && (!account || r.account === account)).reduce((m, r) => { m[r.account] = r; return m; }, {});
  const pctOf = (y, v) => { const vals = Object.values(endVal(y)).reduce((s, r) => s + r.value_eur, 0); return vals ? v / vals * 100 : null; };
  // running costs now, from what Claude knows of each fund
  const terKnown = S.positions.filter(p => (!account || p.account === account) && INV.info[posId(p)] && INV.info[posId(p)].ter_pct != null);
  const running = terKnown.reduce((s, p) => s + p.value * INV.info[posId(p)].ter_pct / 100, 0);
  const managedYear = !account || account === S.managed.name ? S.managed.fees_paid / Math.max(0.5, (Date.now() - Date.parse(S.managed.start_date)) / 31557600000) : 0;
  box.innerHTML = (years.length && fees.some(Boolean) ? chartHtml({type: 'bar', unit: '€', labels: years.map(String), series: [{name: 'Fees and taxes', values: fees}]}, W)
    + `<div class="cost-pcts">${years.map((y, i) => { const p = pctOf(y, fees[i]); return p == null ? '' : `<span><b>${y}</b> ${p.toFixed(2)}% of value</span>`; }).join('')}</div>` : '<div class="empty" style="padding:16px 0">No yearly costs recorded. Yearly statements fill this in.</div>')
    + `<div class="kv">${managedYear ? `<span>Managed portfolio, average per year</span><span>${eur(managedYear)} (${(managedYear / Math.max(1, S.managed.value) * 100).toFixed(2)}%)</span>` : ''}
      ${terKnown.length ? `<span>Fund running costs now, ${terKnown.length} fund${terKnown.length === 1 ? '' : 's'}</span><span>${eur(running)} a year</span>` : ''}</div>`;
}
async function drawValueVsMoney(box, name) {
  if (!box) return;
  const daily = (await loadAcctDaily())[name] || [];
  const r = rangeFor();
  const hist = (S.account_history || []).filter(x => x.account === name).map(x => [tOf(x.date), x.value_eur]);
  const a = S.accounts.find(x => x.name === name);
  const nowVal = a ? a.value + a.cash : name === S.managed.name ? S.managed.value : null;
  const vals = [...hist, ...daily.map(x => [tOf(x.date), x.value]), ...(nowVal != null ? [[Date.now(), nowVal]] : [])].sort((x, y) => x[0] - y[0]);
  // money in: deposits minus withdrawals per year, then today's net money in
  const flows = (S.yearly_flows || []).filter(x => x.account === name && (x.deposits_eur != null || x.withdrawals_eur != null)).sort((x, y) => x.year - y.year);
  let run = 0;
  const money = flows.map(x => { run += (x.deposits_eur || 0) - (x.withdrawals_eur || 0); return [tOf(`${x.year}-12-31`), run]; });
  if (a && a.money_in) money.push([Date.now(), a.money_in]);
  else if (name === S.managed.name) { money.unshift([tOf(S.managed.start_date), S.managed.start_value]); money.push([Date.now(), S.managed.start_value]); }
  const sv = inRange(vals, r), sm = inRange(money, r);
  if (sv.length < 2) { box.innerHTML = `<div class="empty">Not enough history for ${esc(name)} yet. Yearly statements fill this in, and every day the app runs adds a point.</div>`; return; }
  timeChart(box, {series: [{name: 'Value', pts: sv, color: 'var(--s1)', area: true}, ...(sm.length ? [{name: 'Money put in', pts: sm, color: 'var(--muted)', step: true}] : [])], sync: true, select: true, height: 230, label: 'Value against money put in'});
}

/* ---------- one holding ---------- */
async function openHolding(id) {
  const rows = S.positions.filter(p => posId(p) === id);
  if (!rows.length) return toast('That investment is no longer in your data');
  const p = combined(rows)[0];
  closeDrawer();
  const d = document.createElement('aside');
  d.className = 'drawer'; d.id = 'drawer'; d.setAttribute('aria-label', p.name);
  document.body.appendChild(d);
  document.body.classList.add('drawer-open');
  const tot = S.positions.filter(x => !x.managed).reduce((s, x) => s + x.value, 0) || 1, target = (S.targets || {})[id];
  const trades = rows.flatMap(r => r.trades || []), buys = trades.filter(t => t.type === 'buy');
  const avgCost = p.cost && p.units ? p.cost / p.units : null;
  d.innerHTML = `<div class="panel-head"><div class="panel-title">${esc(p.name)}</div><div class="panel-tools">
      <button type="button" class="icon-btn sm" id="hdAsk" title="Ask Claude about this" aria-label="Ask Claude about this">${ICON.ask}</button>
      <button type="button" class="icon-btn sm" id="hdClose" aria-label="Close">${ICON.x}</button></div></div>
    <div class="panel-body">
      <div class="muted small">${esc(p.category)} · ${esc(p.account)}${p.isin ? ' · ' + esc(p.isin) : ''}</div>
      <div class="hd-value"><span class="big2 amt">${eur(p.value)}</span><span>${dayc(p.day_change, p.value)} today</span></div>
      <div class="kv">
        <span>Profit</span><span>${sgn(p.profit)}${p.since_buy_pct != null ? ` (${pct(p.since_buy_pct)})` : ''}</span>
        <span>Units</span><span>${p.units.toLocaleString('en-GB', {maximumFractionDigits: 4})}</span>
        <span>Price</span><span>${eur(p.price, 2)}</span>
        ${avgCost ? `<span>Average cost</span><span>${eur(avgCost, 2)}</span>` : ''}
        <span>Share of investments</span><span>${(p.value / tot * 100).toFixed(1)}%</span>
        <span>Target</span><span><button type="button" class="linkish" id="hdTarget">${target != null ? target + '%' : 'Set a target'}</button></span>
      </div>
      <div class="hd-chart-head"><b>Price</b>${seg('hdr', [['1m', '1M'], ['3m', '3M'], ['1y', '1Y'], ['5y', '5Y']], INV.hRange)}</div>
      <div id="hdChart"><div class="skel-card" style="height:200px"></div></div>
      <div id="hdDivs"></div>
      <div class="hd-claude" id="hdInfo"><div class="skel-line"></div><div class="skel-line short"></div></div>
      <div id="hdFund"></div>
      <div id="hdNews"></div>
      <div class="hd-asks">${[`Is ${p.name} cheap or expensive right now?`, `What are the risks of ${p.name}?`, `Should I buy more ${p.name}, hold or sell?`].map(q =>
        `<button type="button" class="btn ghost small" data-hdq="${esc(q)}">${esc(q)}</button>`).join('')}</div>
      ${trades.length ? `<h4 class="grp">Trades</h4>${[...trades].reverse().slice(0, 30).map(t => `<div class="list-row small"><span>${fdate(t.date)}</span><span class="muted">${t.type}${t.units ? ' ' + Math.abs(t.units).toLocaleString('en-GB', {maximumFractionDigits: 4}) + ' units' : ''}</span><span class="num">${sgn(t.amount, 2)}</span></div>`).join('')}` : ''}
    </div>`;
  const close = () => closeDrawer();
  $('#hdClose').onclick = close;
  $('#hdAsk').onclick = () => openChat({ctx: {title: p.name, text: `${p.name} (${p.category}) in ${p.account}: value €${p.value.toFixed(0)}, ${p.units} units at €${p.price.toFixed(2)}, profit ${p.profit == null ? 'unknown' : '€' + p.profit.toFixed(0)}, ${(p.value / tot * 100).toFixed(1)}% of investments.`}});
  $('#hdTarget').onclick = () => setTarget(id);
  onSeg('hdr', v => { INV.hRange = v; drawHoldingChart(id, p, buys, avgCost); });
  drawHoldingChart(id, p, buys, avgCost);
  holdingInfo(id, p);
  $$('[data-hdq]').forEach(b => b.onclick = () => openChat({text: b.dataset.hdq, send: true, ctx: {title: p.name, text: `${p.name} (${p.category}${p.isin ? ', ISIN ' + p.isin : ''}) in ${p.account}: value €${p.value.toFixed(0)}, ${p.units} units at €${p.price.toFixed(2)}, profit ${p.profit == null ? 'unknown' : '€' + p.profit.toFixed(0)}, ${(p.value / tot * 100).toFixed(1)}% of investments.`}}));
  loadFund().then(F => {
    // figures from the company's own annual report, for US listed stocks
    const f = F && F[id], box = $('#hdFund');
    if (!box) return;
    if (!f) {
      const e = F && F._error;  // nothing could be fetched at all, so say why rather than show nothing
      if (e) box.innerHTML = `<h4 class="grp">The company</h4><div class="muted small">${e.contact
        ? 'The SEC answers only when the app says who is asking. Put a contact address in Settings to see company figures and insider trading.'
        : 'Company figures could not be fetched. ' + esc(e.message)}</div>`;
      return;
    }
    const big = v => `${f.currency === 'USD' ? '$' : f.currency === 'EUR' ? '€' : f.currency + ' '}${Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + 'bn' : (v / 1e6).toFixed(0) + 'm'}`;
    box.innerHTML = `<h4 class="grp">The company${f.year ? ', fiscal ' + esc(f.year) : ''}</h4><div class="kv">
      ${f.revenue ? `<span>Revenue</span><span>${big(f.revenue)}${f.revenue_growth_pct != null ? ` <span class="dpct ${f.revenue_growth_pct < 0 ? 'neg' : 'pos'}">(${f.revenue_growth_pct > 0 ? '+' : ''}${f.revenue_growth_pct}%)</span>` : ''}</span>` : ''}
      ${f.revenue_cagr3_pct != null ? `<span>Growth over 3 years</span><span>${f.revenue_cagr3_pct > 0 ? '+' : ''}${f.revenue_cagr3_pct}% a year</span>` : ''}
      ${f.net_margin_pct != null ? `<span>Profit margin</span><span>${f.net_margin_pct}%</span>` : ''}
      ${f.pe ? `<span title="Share price against profit per share">Price to earnings</span><span>${f.pe}</span>` : ''}
      ${f.industry_pe ? `<span title="What US companies in ${esc(f.industry)} trade at on average (Aswath Damodaran, NYU)">${esc(f.industry)}, typical P/E</span><span>${f.industry_pe}${f.pe ? ` <span class="muted small">${f.pe < f.industry_pe * 0.8 ? 'cheaper' : f.pe > f.industry_pe * 1.25 ? 'pricier' : 'in line'}</span>` : ''}</span>` : ''}
      ${f.pb ? `<span title="Share price against book value per share">Price to book</span><span>${f.pb}</span>` : ''}
      ${f.insiders && (f.insiders.buys_usd || f.insiders.sells_usd) ? `<span title="Directors and officers trading their own company's shares on the open market, last ${Math.round(f.insiders.days / 30)} months">Insiders</span><span>bought $${fmtN(f.insiders.buys_usd)}, sold $${fmtN(f.insiders.sells_usd)}</span>` : ''}</div>
      <div class="muted small" style="margin-top:6px">${f.revenue ? 'From annual reports filed with the SEC' : ''}${f.revenue && f.industry_pe ? '; ' : ''}${f.industry_pe ? 'industry figures by Aswath Damodaran (NYU)' : ''}</div>`;
  });
  loadNews().then(N => {
    const mine = N.items.filter(n => n.pid === id).slice(0, 5), box = $('#hdNews');
    if (box && mine.length) box.innerHTML = `<h4 class="grp">News</h4>${mine.map(newsRow).join('')}`;
  });
}

/* ---------- news about what you own ---------- */
async function loadNews(force) {
  if (!force && INV.news && Date.now() - INV.newsAt < 120000) return INV.news;
  try { INV.news = await cachedJSON('/api/news',{ttl:120000,force:!!force}); } catch { INV.news = {items: [], picks: {}}; }
  INV.newsAt = Date.now();
  if (INV.news.updating && !INV.newsTimer) INV.newsTimer=setTimeout(()=>{INV.newsTimer=null;loadNews(true).then(()=>{if($('#dailyNews'))drawDailyNews(invFiltered());else if($('#newsSlot'))newsCard($('#newsSlot'));});},8000);
  return INV.news;
}
const newsRow = n => `<a class="news-row" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">
  <span class="news-t">${esc(n.title)}</span><span class="news-m"><span class="chip">${esc(n.holding)}</span>${esc(n.source)}${n.date ? ' · ' + ago(n.date) : ''}</span></a>`;
async function newsCard(slot) {
  if (!slot) return;
  if (!INV.news) slot.innerHTML = `<section class="card" data-card="news"><h2>News</h2><div class="skel-line"></div><div class="skel-line short"></div></section>`;
  const N = await loadNews();
  if (!slot.isConnected) return;
  const held = [...new Map(N.items.map(n => [n.pid, n.holding])).entries()];
  const f = INV.newsFilter && held.some(([k]) => k === INV.newsFilter) ? INV.newsFilter : 'all';
  const byId = Object.fromEntries(N.items.map(n => [n.id, n]));
  const picks = ((N.picks || {}).picks || []).filter(p => byId[p.id]);
  const picked = new Set(f === 'all' ? picks.map(p => p.id) : []);
  const list = N.items.filter(n => (f === 'all' || n.pid === f) && !picked.has(n.id));
  slot.innerHTML = `<section class="card" data-card="news">
    <div class="card-head"><div><h2>News</h2><p class="sub">Recent headlines about what you own, from Yahoo Finance</p></div>
      <div class="controls" style="margin:0">${held.length > 1 ? `<select id="newsF" aria-label="Investment"><option value="all">All investments</option>${held.map(([k, n]) => `<option value="${esc(k)}" ${f === k ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>` : ''}
        ${S.status.ai_mode && N.items.length ? `<button type="button" class="btn" id="newsPick"><span class="claude-mark sm">${CLAUDE_ICON}</span>What matters</button>` : ''}</div></div>
    ${picks.length && f === 'all' ? `<div class="news-picks"><div class="news-picks-h"><span class="claude-mark">${CLAUDE_ICON}</span><b>What matters for you</b><span class="ago">${N.picks.time ? ago(N.picks.time) : ''}</span></div>
      ${picks.map(p => `${newsRow(byId[p.id])}<div class="news-why">${esc(p.why)}</div>`).join('')}</div>` : ''}
    <div class="news-list">${list.slice(0, INV.newsMore ? 40 : 8).map(newsRow).join('') || `<div class="empty">${N.offline ? 'News loads when the app runs with internet.' : N.updating ? 'Fetching the news…' : 'No recent news about your investments.'}</div>`}</div>
    ${list.length > 8 && !INV.newsMore ? `<button type="button" class="btn ghost" id="newsMore">Show more (${Math.min(40, list.length) - 8})</button>` : ''}
  </section>`;
  if ($('#newsF')) $('#newsF').onchange = e => { INV.newsFilter = e.target.value; newsCard(slot); };
  if ($('#newsMore')) $('#newsMore').onclick = () => { INV.newsMore = true; newsCard(slot); };
  if ($('#newsPick')) $('#newsPick').onclick = async e => {
    const b = e.currentTarget; b.disabled = true; b.lastChild.textContent = 'Claude is reading…';
    try { N.picks = await post('/api/news/picks', {}); } catch (err) { toast(err.message); }
    newsCard(slot);
  };
}
async function drawHoldingChart(id, p, buys, avgCost) {
  const H = await loadHist(), s = H.series[id], box = $('#hdChart');
  if (!box) return;
  $$('[data-seg="hdr"] button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === INV.hRange));
  if (!s || s.dates.length < 2) { box.innerHTML = `<div class="empty">${H.updating ? 'Fetching price history…' : 'No price history for this investment.'}</div>`; return; }
  const days = {'1m': 31, '3m': 92, '1y': 366, '5y': 1830}[INV.hRange], cut = Date.now() - days * 864e5;
  const pts = s.dates.map((d, i) => [tOf(d), s.close[i]]).filter(([t]) => t >= cut);
  const dots = buys.filter(b => tOf(b.date) >= cut && b.price).map(b => ({t: tOf(b.date), v: b.price, label: `Bought ${Math.abs(b.units).toLocaleString('en-GB', {maximumFractionDigits: 4})} on ${fdate(b.date)} at €${b.price.toFixed(2)}`, color: 'var(--gain)'}));
  timeChart(box, {series: [{name: 'Price', pts, color: 'var(--s1)', area: true}], dots, hline: avgCost ? {v: avgCost, label: `Average cost €${avgCost.toFixed(2)}`} : null, height: 200, label: 'Price'});
  const cut12 = isoD(new Date(Date.now() - 365 * 864e5)), d12 = (s.divs || []).filter(([d]) => d >= cut12);
  if (d12.length && $('#hdDivs')) $('#hdDivs').innerHTML = `<div class="kv"><span>Dividends, last 12 months</span><span>${eur(d12.reduce((a, [, v]) => a + v, 0) * p.units)} (${d12.length} payment${d12.length === 1 ? '' : 's'})</span></div>`;
}
async function holdingInfo(id, p, force) {
  const box = $('#hdInfo'); if (!box) return;
  let info = INV.info[id];
  if (!info || force) {
    try { info = await (await fetch('/api/holding-info?id=' + encodeURIComponent(id), {cache: 'no-store'})).json(); } catch { info = {}; }
    if ((!info.summary || force) && S.status.ai_mode) {
      box.innerHTML = `<div class="hd-claude-h"><span class="claude-mark">${CLAUDE_ICON}</span><b>Claude</b><span class="ago">reading up on it</span></div><div class="skel-line"></div><div class="skel-line short"></div>`;
      try { info = await post('/api/holding-info', {id, force: !!force}); } catch (e) { info = {error: e.message}; }
    }
    INV.info[id] = info;
  }
  if (!$('#hdInfo')) return;
  const tot = info.ter_pct != null ? p.value * info.ter_pct / 100 : null;
  box.innerHTML = info.summary ? `<div class="hd-claude-h"><span class="claude-mark">${CLAUDE_ICON}</span><b>Claude</b>${info.date ? `<span class="ago">${fdate(info.date)}</span>` : ''}<button type="button" class="icon-btn sm" id="hdRe" title="Look again" aria-label="Look again"><svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/></svg></button></div>
      <p>${esc(info.summary)}</p>${info.overlap ? `<p class="muted">${esc(info.overlap)}</p>` : ''}
      <div class="kv">${info.ter_pct != null ? `<span>Running costs</span><span>${info.ter_pct}% a year${tot ? `, about ${eur(tot)}` : ''}</span>` : ''}
        ${info.region ? `<span>Region</span><span>${esc(info.region)}</span>` : ''}${info.sector ? `<span>Sector</span><span>${esc(info.sector)}</span>` : ''}${info.currency ? `<span>Main currency</span><span>${esc(info.currency)}</span>` : ''}</div>`
    : `<p class="muted small">${info.error ? esc(info.error) : 'Claude can describe this investment and its costs once Claude Code or an API key is set up.'}</p>`;
  if ($('#hdRe')) $('#hdRe').onclick = () => holdingInfo(id, p, true);
}
function closeDrawer() { const d = $('#drawer'); if (d) d.remove(); document.body.classList.remove('drawer-open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#drawer') && !$('#dlg').open && !$('.menu')) closeDrawer(); });

/* ---------- one account ---------- */
async function accountPage() {
  const name = ui.account, a = S.accounts.find(x => x.name === name), m = S.managed.name === name ? S.managed : null, s = S.savings.find(x => x.name === name);
  if (!a && !m && !s) { $('#view').innerHTML = `<section class="card"><div class="empty">No account called ${esc(name)}. <a href="#accounts">All accounts</a></div></section>`; return; }
  const value = a ? a.value + a.cash : m ? m.value : s.value;
  const pos = S.positions.filter(p => m ? p.managed : p.account === name);
  const flows = (S.yearly_flows || []).filter(r => r.account === name).sort((x, y) => y.year - x.year);
  const hist = (S.account_history || []).filter(r => r.account === name).sort((x, y) => y.date.localeCompare(x.date));
  const updated = a ? (a.updated ? `Updated ${fdate(a.updated)}${a.source ? ' from ' + esc(a.source) : ''}` : hist.length ? `Last statement value ${fdate(hist[0].date)}${hist[0].source ? ' (' + esc(hist[0].source) + ')' : ''}` : 'Prices update live')
    : m ? `${m.mode === 'positions' ? 'Priced live' : 'Last real value'} ${fdate(m.last_real_date)}` : `Balance on ${fdate(s.snapshot_date)}`;
  const W = Math.max(320, $('#view').clientWidth - 42), half = innerWidth > 900 ? (W - 58) / 2 : W;
  $('#view').innerHTML = `<div class="stack-y">
    <div class="status-bar"><span class="dot ${a || m ? '' : 'off'}"></span>${updated}<a href="#accounts" class="linkish small" style="margin-left:auto">All accounts</a></div>
    <div class="grid g4">
      <div class="card tile"><div class="k">Value</div><div class="v" data-count="${value}">${eur(value)}</div></div>
      ${a ? `<div class="card tile"><div class="k">Profit</div><div class="v">${sgn(a.profit)}</div></div><div class="card tile"><div class="k">Money in</div><div class="v">${eur(a.money_in)}</div></div><div class="card tile"><div class="k">Today</div><div class="v">${sgn(a.day_change)}</div></div>` : ''}
      ${m ? `<div class="card tile"><div class="k">Profit</div><div class="v">${sgn(m.profit)}</div></div><div class="card tile"><div class="k">Started with</div><div class="v">${eur(m.start_value)}</div><div class="n">${fdate(m.start_date)}</div></div><div class="card tile"><div class="k">Fees paid</div><div class="v">${eur(m.fees_paid)}</div></div>` : ''}
      ${s ? `<div class="card tile"><div class="k">Interest rate</div><div class="v">${s.rate_pct ? s.rate_pct.toFixed(2) + '%' : '–'}</div></div><div class="card tile"><div class="k">Interest per year</div><div class="v">${eur(s.value * (s.rate_pct || 0) / 100)}</div></div><div class="card tile"><div class="k">Matures</div><div class="v small-v">${s.maturity ? fdate(s.maturity) : 'flexible'}</div></div>` : ''}
    </div>
    <section class="card" data-card="acct-vm"><h2>${s ? 'Balance over time' : 'Value against money put in'}</h2><div id="avm"></div></section>
    <div class="grid g2">
      <section class="card" data-pick="amonth"><h2>Change per month</h2><p class="sub">Includes money you added or took out</p><div id="amonth"></div></section>
      ${s ? '' : `<section class="card"><h2>Costs per year</h2><div id="acost"></div></section>`}
    </div>
    ${pos.length ? `<section class="card"><h2>Investments</h2><div class="table-wrap"><table><thead><tr><th>Investment</th><th class="num">Value</th><th class="num">Today</th><th class="num">Profit</th></tr></thead><tbody>
      ${pos.sort((x, y) => y.value - x.value).map(p => `<tr data-ctx="holding:${esc(posId(p))}"><td><button type="button" class="nm linkish" data-open="holding:${esc(posId(p))}">${esc(p.name)}</button><div class="meta">${esc(p.category)}</div></td><td class="num">${eur(p.value)}</td><td class="num">${dayc(p.day_change, p.value)}</td><td class="num">${sgn(p.profit)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
    ${flows.length || hist.length ? `<section class="card"><h2>History</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>What</th><th class="num">Amount</th><th>Source</th></tr></thead><tbody>
      ${[...hist.map(r => ({d: r.date, w: 'Value', v: eur(r.value_eur), src: r.source || ''})), ...flows.flatMap(r => [['deposits_eur', 'Deposits'], ['withdrawals_eur', 'Withdrawals'], ['dividends_eur', 'Dividends'], ['fees_eur', 'Fees'], ['taxes_eur', 'Taxes'], ['profit_eur', 'Result']]
        .filter(([k]) => r[k] != null).map(([k, l]) => ({d: `${r.year}`, w: `${l} in ${r.year}`, v: k === 'profit_eur' ? sgn(r[k]) : eur(r[k]), src: r.note || ''})))].sort((x, y) => y.d.localeCompare(x.d)).map(r => `<tr><td>${r.d.length > 4 ? fdate(r.d) : r.d}</td><td>${r.w}</td><td class="num">${r.v}</td><td class="meta">${esc(r.src)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
    <section class="card"><h2>Imports and documents</h2><div id="aimports"><div class="skel-line"></div></div></section>
  </div>`;
  drawValueVsMoney($('#avm'), name);
  if (!s) drawCosts($('#acost'), name, half);
  const daily = (await loadAcctDaily())[name] || [];
  const me = {};
  for (const r of [...(S.account_history || []).filter(x => x.account === name).map(x => ({date: x.date, value: x.value_eur})), ...daily]) me[r.date.slice(0, 7)] = r.value;
  const ms = Object.keys(me).sort(), ch = ms.slice(1).map((mm, i) => me[mm] - me[ms[i]]);
  if ($('#amonth')) $('#amonth').innerHTML = ch.length ? chartHtml({type: 'bar', unit: '€', labels: ms.slice(1).map(mLabel), xkeys: ms.slice(1), series: [{name: 'Change', values: ch}]}, half) : '<div class="empty">Needs values from at least two months.</div>';
  const imps = await (await fetch('/api/imports')).json().catch(() => []);
  const low = name.toLowerCase(), mine = imps.filter(i => (i.summary + ' ' + i.files.join(' ')).toLowerCase().includes(low.split(' ')[0]));
  if ($('#aimports')) $('#aimports').innerHTML = mine.length ? mine.map(i => `<div class="list-row small"><div><b>${esc(i.files.join(', '))}</b><div class="muted">${fdate(i.date.slice(0, 10))}, ${esc(i.summary.slice(0, 160))}</div></div></div>`).join('')
    : `<div class="empty">No imports mention ${esc(name)} yet. <a href="#import">Import a statement</a></div>`;
  countUp();
}
