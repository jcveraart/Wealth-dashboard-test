'use strict';
/* Page ownership, session preloading and small updates that keep analysis in place. */
const INVESTMENT_TABS=[['overview','Overview'],['performance','Performance'],['portfolio','Allocation & risk'],['plans','Savings plans'],['alerts','Signals']];
const EXPLORE_TABS=[['opportunities','Opportunities'],['watchlist','Watchlist'],['investors','Superinvestors'],['insiders','Insiders'],['research','Company research'],['desk','Research desk']];
const EXP={tab:store.get('explore.tab','opportunities')};
if(!EXPLORE_TABS.some(([k])=>k===EXP.tab))EXP.tab='opportunities';
const UTILITY={cashflow:['Cash flow','spending'],planning:['Planning records','plan'],documents:['Documents & evidence','import'],connections:['Connections','settings'],backups:['Backups','settings']};
for(const [name,[title]] of Object.entries(UTILITY))TITLES[name]=title;
const intOwner=tab=>EXPLORE_TABS.some(([k])=>k===tab)?'explore':'holdings';
function pageTabs(rows,selected,attribute,label){return `<nav class="seg tabs page-tabs" aria-label="${esc(label)}">${rows.map(([k,l])=>`<button type="button" ${attribute}="${k}" aria-current="${k===selected?'page':'false'}" aria-pressed="${k===selected}" class="${k===selected?'active':''}">${l}</button>`).join('')}</nav>`;}
intNav=function(){return view==='explore'?pageTabs(EXPLORE_TABS,EXP.tab,'data-explore-tab','Explore'):pageTabs(INVESTMENT_TABS,INT.tab,'data-int-tab','Investments');};
intNavigate=function(tab,s){
  if(s){INT.symbol=s;store.set('int.symbol',s);}
  if(intOwner(tab)==='explore'){
    EXP.tab=tab;store.set('explore.tab',tab);INT.tab=tab;
    if(view!=='explore')location.hash='explore';else explorePage();
  }else{
    INT.tab=tab;store.set('int.tab',tab);
    if(view!=='holdings')location.hash='holdings';else holdings();
  }
};
const polishIntBind=intBind;
intBind=function(root=$('#view')){polishIntBind(root);$$('[data-explore-tab]',root).forEach(b=>b.onclick=()=>intNavigate(b.dataset.exploreTab));};
const polishIntWorkspace=intWorkspace;
intWorkspace=async function(){await polishIntWorkspace();if($('#intConnections'))$('#intConnections').remove();if($('#intFresh')&&!$('#intSourceLink'))$('#intFresh').insertAdjacentHTML('afterend','<a class="linkish small" id="intSourceLink" href="#connections">Connections & coverage →</a>');openPageSections();};
function explorePage(){
  INT.tab=EXP.tab;
  if(EXP.tab==='desk'){WS.tab='research';workspacePage();}else intWorkspace();
}
wsNavigate=function(tab){
  WS.tab=tab;store.set('ws.tab',tab);
  if(tab==='performance')return intNavigate('performance');
  if(tab==='research'){EXP.tab='desk';store.set('explore.tab','desk');if(view!=='explore')location.hash='explore';else explorePage();return;}
  if(!UTILITY[tab])return;
  if(view!==tab)location.hash=tab;else workspacePage();
};
workspacePage=async function(){
  const tab=view==='holdings'?'performance':view==='explore'?'research':view;
  WS.tab=tab;
  const gen=++WS.generation,owner=view;
  const nav=owner==='holdings'?intNav():owner==='explore'?intNav():`<div class="utility-back"><a class="linkish small" href="#${UTILITY[tab]?.[1]||'overview'}">← ${esc(TITLES[UTILITY[tab]?.[1]]||'Overview')}</a></div>`;
  $('#view').innerHTML=`<div class="stack-y">${nav}<div id="wsBody">${skeleton()}</div></div>`;intBind();
  try{
    const q=tab==='performance'?{account:WS.account,...WS.period}:tab==='cashflow'?{month:WS.month}:{};
    const d=await wsGet(tab,q);
    if(gen!==WS.generation||owner!==view)return;
    WS.data=d;
    ({cashflow:wsCashflow,performance:wsPerformance,research:wsResearch,planning:wsPlanning,documents:wsDocuments,connections:wsConnections,backups:wsBackups})[tab](d);
    wsBind();intBind();openPageSections();
  }catch(e){if(gen===WS.generation&&$('#wsBody'))$('#wsBody').innerHTML=intCard('This view is unavailable',wsEmpty(e.message)+wsButton('Try again','reload'));wsBind();}
};
wsRefresh=async function(){
  if(view==='review')reviewPage();else if(view==='explore')explorePage();else if(UTILITY[view]||view==='holdings'&&INT.tab==='performance')workspacePage();
  await wsLoadSummary();
};
holdings=function(){
  if(!INVESTMENT_TABS.some(([k])=>k===INT.tab)){INT.tab='overview';store.set('int.tab','overview');}
  if(INT.tab==='performance'){WS.tab='performance';if(INVF.acct)WS.account=INVF.acct;return workspacePage();}
  if(INT.tab==='plans')return wsInvestmentPlans();
  if(INT.tab!=='overview')return intWorkspace();
  originalHoldings();
  const root=$('#view>.inv');
  root.insertAdjacentHTML('afterbegin',intNav());
  $('#dailyIdeasCard')?.remove();
  const hero=$('.inv-hero'),chart=$('[data-card="inv-chart"]')||$('[data-card="inv-recent"]');
  const mode=$('[data-mode-controls]');
  if(chart){
    const primary=document.createElement('div');primary.className='inv-primary';
    hero.before(primary);primary.append(hero,chart);
    if(mode){mode.querySelector('.muted')?.remove();$('.card-head',chart)?.append(mode);}
    if($('#dailyContributions'))$('#dailyContributions').closest('.card').classList.add('compact-chart');
    hero.insertAdjacentHTML('afterend','<section class="card portfolio-brief brief page-ai-card no-tools" id="portfolioBrief"><div class="brief-head"><span class="claude-mark">'+CLAUDE_ICON+'</span><b>Claude</b><span class="ago">Investments</span></div><div id="portfolioNotes">'+pageBriefNotes(initialPortfolioBrief())+'</div><span class="muted small" id="portfolioBriefStatus">'+pageBriefStatus(initialPortfolioBrief())+'</span><button type="button" class="linkish brief-ask" id="portfolioAsk">Ask about this →</button></section>');
    const briefingTop=moveBriefToTop(hero,$('#portfolioBrief'),{className:'investment-ai-top'});primary.before(briefingTop);
    primary.classList.add('investment-chart-row');
    loadPortfolioNotes();
  }
  // These are already inside the chart; keep the two navigation rows at the top.
  root.querySelectorAll('.grid').forEach(g=>{if(!g.children.length)g.remove();else if(g.children.length===1)g.classList.remove('g2');});
  const spread=$('[data-card="inv-spread"]');if(spread){
    spread.insertAdjacentHTML('beforeend','<p class="muted small">Regions describe investment exposure. AI classifications are inferred; exact fund weights require a disclosed holdings file.</p><button type="button" class="linkish small" id="classifyRegions">Classify missing regions with Claude</button><div id="classificationStatus" class="muted small" role="status"></div>');
    $('#classifyRegions').onclick=async e=>{const b=e.currentTarget;b.disabled=true;$('#classificationStatus').textContent='Claude is checking the investment identities…';try{const r=await post('/api/classify',{});await load();holdings();toast(r.done+' classifications reviewed');}catch(error){$('#classificationStatus').textContent=error.message;b.disabled=false;}};
  }
  intBind();openPageSections();
};
const polishRenderView=renderView;
renderView=function(){
  if(view==='explore')return explorePage();
  if(UTILITY[view])return workspacePage();
  return polishRenderView();
};
const polishRoute=route;
route=function(){polishRoute();if(UTILITY[view]){$$('#nav a').forEach(a=>a.setAttribute('aria-current',a.getAttribute('href')==='#'+UTILITY[view][1]?'page':'false'));}};
function openPageSections(){
  // main sections start open; settings, evidence and method notes inside them stay folded until asked for
  // calculators (sections holding a form) are tools: they stay folded too
  $$('#view details.card:not(.int-details)').forEach(d=>{if(!d.dataset.opened){d.dataset.opened='1';if(!d.querySelector('form'))d.open=true;}});
}
function showQuietUpdate(text='New data available'){
  let b=$('#quietUpdate');
  if(!b){b=document.createElement('button');b.id='quietUpdate';b.type='button';b.className='linkish small quiet-update';$('.topbar .tools').prepend(b);b.onclick=()=>{b.remove();const y=window.scrollY;renderView();requestAnimationFrame(()=>window.scrollTo(0,y));};}
  b.textContent=text+' · Apply';b.title='Update this view when you are ready. Your current analysis stays in place.';
}
function setHTML(el,html){if(el&&el.innerHTML!==html)el.innerHTML=html;}
function quietNumbers(){
  if(view==='holdings'&&INT.tab==='overview'){
    const list=invFiltered(),cash=INVF.cls==='all'?S.accounts.filter(a=>!INVF.acct||a.name===INVF.acct).reduce((s,a)=>s+a.cash,0):0;
    const value=list.reduce((s,p)=>s+p.value,0),day=list.reduce((s,p)=>s+(p.day_change||0),0),hero=$('.inv-hero');
    if(hero){const big=$('.big',hero);big.dataset.count=value+cash;setHTML(big,eur(value+cash));setHTML($('.day',hero),INVF.cls==='cash'?'Interest, no daily prices':dayc(day,value)+' today');}
    const rows=holdRows(),byId=new Map(rows.map(p=>[holdingLiveKey(p),p])),total=rows.reduce((s,p)=>s+p.value,0),profit=rows.reduce((s,p)=>s+(p.profit||0),0);
    $$('[data-live-id]').forEach(row=>{const p=byId.get(row.dataset.liveId);if(!p)return;const cells=row.cells;if(cells.length<4)return;setHTML($('b',cells[1]),eur(p.value));setHTML($('.meta',cells[1]),(total?(p.value/total*100).toFixed(1):0)+'%');const bar=$('.wbar i',cells[1]);if(bar)bar.style.width=Math.max(1,total?p.value/total*100:0).toFixed(1)+'%';setHTML(cells[2],p.kind==='savings'?'<span class="muted">·</span>':p.live===false?sgn(p.day_change):dayc(p.day_change,p.value));setHTML(cells[3],sgn(p.profit)+`<div class="meta">${p.kind==='savings'?`${p.rate||0}% a year`:pct(p.since_buy_pct)}</div>`);});
    if(hero){const income=$('#incomeLine')?.innerHTML||'';setHTML($('.ih-sub',hero),(profit?`${sgn(profit)} profit since you started`:'')+(cash?' · '+eur(cash)+' cash':'')+`<span id="incomeLine">${income}</span>`);}
    $$('[data-live-group]').forEach(row=>{const ps=rows.filter(p=>groupName(p,INV.listGroup||'class')===row.dataset.liveGroup),v=ps.reduce((s,p)=>s+p.value,0);setHTML(row.cells[1],eur(v)+`<div class="meta">${total?(v/total*100).toFixed(1):0}%</div>`);setHTML(row.cells[2],dayc(ps.reduce((s,p)=>s+(p.day_change||0),0),v));setHTML(row.cells[3],sgn(ps.reduce((s,p)=>s+(p.profit||0),0)));});
    const footer=$('#htable tfoot tr');if(footer){setHTML(footer.cells[1],eur(total));setHTML(footer.cells[2],dayc(rows.reduce((s,p)=>s+(p.day_change||0),0),total));setHTML(footer.cells[3],sgn(profit));}
    if(rows.length!==$$('[data-live-id]').length)showQuietUpdate('Holdings changed');
  }else if(view==='overview'){
    const hero=$('.hero .big');if(hero){hero.dataset.count=S.totals.net_worth;setHTML(hero,eur(S.totals.net_worth));}
    const live=allPositions().filter(p=>p.live).reduce((s,p)=>s+p.value,0);setHTML($('.hero .day'),dayc(S.totals.day_change,live)+' today on listed investments');
    const values=[S.totals.gross,S.totals.debt,S.totals.investing_profit,S.totals.savings];
    $$('.home .tile .v').forEach((e,i)=>{if(i<values.length){e.dataset.count=values[i];setHTML(e,i===2?sgn(values[i]):eur(values[i]));}});
  }
  // No background refresh replaces the active page, tables, menus or selected charts.
}
function quietInvestmentCharts(){
  if(view!=='holdings'||INT.tab!=='overview'||$('.picking,.picked,.pop,.fs,.menu')||$('#view svg:hover')||$('#view .tc-sel')?.getClientRects().length)return;
  const list=invFiltered();
  if(INVF.mode!=='history')drawDailyCharts(INV.hist,list);else if($('#invChart'))investCharts(list);
}
let notesGeneration=0,notesTimer;
async function loadPortfolioNotes(){
  const generation=++notesGeneration,account=INVF.acct,asset=INVF.cls;
  const paint=incoming=>{if(generation!==notesGeneration||!$('#portfolioNotes'))return;const d=incoming.items?.length?incoming:initialPortfolioBrief();setHTML($('#portfolioNotes'),pageBriefNotes(d));$('#portfolioBriefStatus').textContent=pageBriefStatus(d);$('#portfolioAsk').onclick=()=>openChat({ctx:{title:'Investment overview',text:JSON.stringify({account:account||'All investment accounts',asset,notes:d.items,prices_at:d.prices_at})},text:'Review what has been doing well in this portfolio selection, and one thing worth checking. Use current evidence and distinguish price moves from my actual returns.'});};
  paint(initialPortfolioBrief());
  try{const url='/api/investment-briefing?'+new URLSearchParams({account,asset});const d=await cachedJSON(url,{ttl:300e3});paint(d);clearTimeout(notesTimer);if(d.updating)notesTimer=setTimeout(async()=>{try{const next=await cachedJSON(url,{force:true});paint(next);}catch{}},10000);}catch{if(generation===notesGeneration&&$('#portfolioBriefStatus'))$('#portfolioBriefStatus').textContent='Showing saved observations · Ask Claude to look further';}
}
const polishOpportunities=intOpportunities;
intOpportunities=function(d){polishOpportunities(d);$('#intBody>.stack-y').insertAdjacentHTML('afterbegin',oppCard());wireOpp();openPageSections();};
const polishSettings=settings;
settings=async function(){await polishSettings();if(view==='settings')openPageSections();};
const polishSpendingPage=spendingPage;
spendingPage=async function(){await polishSpendingPage();if(view!=='spending'||!$('#sp'))return;const focus=$('#sp .focus-chips'),card=$('#spBody .card');if(focus&&card)card.append(focus);if(!$('#spWorkflowLinks'))$('#sp').insertAdjacentHTML('beforeend',`<div class="utility-links" id="spWorkflowLinks"><a class="linkish small" href="#cashflow">Cash-flow outlook →</a><a class="linkish small" href="#documents">Documents & payment evidence →</a></div>`);openPageSections();};
const polishPlanPage=planPage;
planPage=function(){polishPlanPage();$('#view').insertAdjacentHTML('beforeend','<div class="utility-links"><a class="linkish small" href="#planning">Goals, policies & planning records →</a></div>');openPageSections();};
const polishImportView=importView;
importView=function(){polishImportView();$('#view').insertAdjacentHTML('beforeend','<div class="utility-links"><a class="linkish small" href="#documents">Search original documents & purchase evidence →</a></div>');openPageSections();};
async function preloadDashboard(){
  // Two jobs at a time; cached local reads, never launch paid imports or a public refresh.
  const jobs=[()=>cachedJSON('/api/cash-workspace',{ttl:60000}),()=>ensureSpending(),()=>loadHist(),()=>loadAcctDaily(),()=>loadFund(),()=>intGet('portfolio',{account:'',class:'all'}),()=>wsGet('plans'),()=>wsGet('performance',{account:WS.account,...WS.period}),()=>intGet('opportunities'),()=>intGet('watchlist'),()=>intGet('investors',{cik:INT.manager}),()=>intGet('insiders',{symbol:''}),()=>wsGet('cashflow',{month:WS.month}),()=>wsGet('research'),()=>wsGet('planning'),()=>wsGet('documents'),()=>wsGet('connections'),()=>wsGet('backups')];
  let cursor=0;async function worker(){while(cursor<jobs.length){const job=jobs[cursor++];try{await job();}catch{}}}
  await Promise.all([worker(),worker()]);
}
const polishPerformance=wsPerformance;
wsPerformance=function(d){polishPerformance(d);const account=$('#wsAccount'),period=$('#wsPeriod');if(account&&period){const label=document.createElement('label');label.className='small';label.append('Account ',account);period.prepend(label);}const value=$('#wsAccountValue')?.closest('.card'),adjusted=$('#wsAdjusted')?.closest('.card');if(value&&adjusted){const row=document.createElement('div');row.className='grid g2';value.before(row);row.append(value,adjusted);}openPageSections();};
window.addEventListener('hashchange',()=>{$('#quietUpdate')?.remove();if(UTILITY[view])$$('#nav a').forEach(a=>a.setAttribute('aria-current',a.getAttribute('href')==='#'+UTILITY[view][1]?'page':'false'));});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load({background:true});});
// Warm a likely next view on intent without competing with the page currently opening.
$('#nav').addEventListener('pointerover',e=>{const href=e.target.closest('a')?.getAttribute('href');if(href==='#holdings')loadHist().catch(()=>{});if(href==='#spending')ensureSpending().catch(()=>{});if(href==='#explore')intGet('opportunities').catch(()=>{});});
