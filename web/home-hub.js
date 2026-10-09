'use strict';
/* The home page below the top: net worth, accounts, then one summary card per area, each ending in its links. */
const hubCard=(id,title,href,body)=>`<section class="card home-hub-card" data-card="${id}"><div class="card-head"><h2>${title}</h2><a class="linkish small" href="#${href}">Open →</a></div>${body}</section>`;
const hubMetric=(label,value)=>`<div><span class="muted small">${label}</span><b>${value}</b></div>`;
const hubLink=(href,label)=>`<a class="linkish small" href="#${href}">${label} →</a>`;
function hubAdvice(){
  const dismissed=new Set([...(S.advice_dismissed||[]),...(S.advice_done||[])].map(r=>r.id));
  const advice=(S.advice||[]).filter(r=>!dismissed.has(r.id));
  const review=WS.summary?.review_count;
  return `${advice.slice(0,3).map(r=>`<a class="home-hub-line hub-rec" href="#advice"><b>${esc(r.title)}</b>${r.impact_eur?`<span class="tag good">${eur(r.impact_eur)} a year</span>`:''}</a>`).join('')||'<p class="muted small">Nothing to act on right now.</p>'}<div class="home-hub-links">${hubLink('advice',`${advice.length} recommendation${advice.length===1?'':'s'}`)}${review?hubLink('review',`${review} to review`):''}</div>`;
}
function hubGoals(){
  const goals=(S.goals||[]).slice(0,2);
  return goals.map(g=>{const saved=g.source==='manual'&&g.saved_eur==null?null:goalAmount(g),target=g.target_eur;return `<div class="home-hub-line"><b>${esc(g.name)}</b><span class="small">${eur(saved)} of ${eur(target)}${g.date?' · '+fdate(g.date):''}</span>${target>0&&saved!=null?`<div class="int-track"><i style="width:${Math.max(0,Math.min(100,saved/target*100)).toFixed(1)}%"></i></div>`:''}</div>`;}).join('')||'<p class="muted small">Goals, policies and decision records help connect today’s choices to your plans.</p>';
}
function hubSavings(){
  const cash=liquidCashRows(S).reduce((n,r)=>n+r.value,0),debts=(S.debts||[]).filter(d=>!d.expected_gift);
  const deposits=(S.savings||[]).filter(x=>x.maturity).sort((a,b)=>a.maturity.localeCompare(b.maturity));
  return `<div class="home-hub-metrics">${hubMetric('Available cash',eur(cash))}${hubMetric('Debt',eur(S.totals.debt))}</div>
    ${debts.map(d=>`<div class="home-hub-line"><b>${esc(d.name)}</b><span class="muted small">${eur(d.balance)}${d.rate_pct!=null?` · ${(+d.rate_pct).toFixed(2)}%`:''}${d.monthly_payment_eur?` · ${eur(d.monthly_payment_eur)} a month`:''}</span></div>`).join('')}
    ${deposits.slice(0,1).map(x=>`<div class="home-hub-line"><b>${esc(x.name)}</b><span class="muted small">${eur(x.value)} · matures ${fdate(x.maturity)}</span></div>`).join('')}
    <div class="home-hub-links">${hubLink('cash','Cash & repayments')}</div>`;
}
async function fillHomeHub(){
  const owner=$('#homeHub');if(!owner)return;
  try{await ensureSpending();if(!owner.isConnected)return;
    const all=SP.rows,month=today().slice(0,7),rows=all.filter(t=>t.date.startsWith(month)),t=totals(rows);
    $('#homeSpendingBody').innerHTML=`<div class="home-hub-metrics">${hubMetric('Spent · '+mLabel(month),eur(t.spent))}${hubMetric('Income recorded',eur(t.income))}${hubMetric('Left over',sgn(t.saved))}</div><div id="homeSpendingChart"></div><div class="home-hub-links">${hubLink('spending','Payments')}${hubLink('cashflow','Cash flow')}${hubLink('documents','Documents')}</div>`;
    const months=[...new Set(all.map(r=>r.date.slice(0,7)))].sort().slice(-6),data=months.map(m=>({month:m,...totals(all.filter(r=>r.date.startsWith(m)))}));
    if(months.length){const name='homeSpending';PICKS[name]=(i,k)=>({title:mLabel(months[i])+' · '+(k?'Income':'Spending'),list:all.filter(t=>t.date.startsWith(months[i])&&kindOf(t)===(k?'income':'expense')),filter:{from:months[i]+'-01',to:isoD(new Date(+months[i].slice(0,4),+months[i].slice(5,7),0))}});$('#homeSpendingChart').innerHTML=chartHtml({type:'bar',unit:'€',labels:months.map(mLabel),pick:name,series:[{name:'Spending',values:data.map(t=>t.spent),color:'var(--s1)'},{name:'Income',values:data.map(t=>t.income),color:'var(--s2)'}]},Math.max(260,$('#homeSpendingChart').clientWidth));}
  }catch{if(owner.isConnected)$('#homeSpendingBody').innerHTML='<p class="muted small">Payment history is unavailable right now.</p>'+hubLink('spending','Open spending');}
  try{const planning=await wsGet('planning');if(!owner.isConnected)return;const records=planning.goals||[];if(records.length)$('#homeGoals').innerHTML=records.slice(0,2).map(g=>`<div class="home-hub-line"><b>${esc(g.name)}</b><span class="small">${eur(g.saved_eur)} of ${eur(g.target_eur)}${g.due?' · '+fdate(g.due):''}</span>${g.monthly_needed_eur!=null?`<span class="muted small">${eur(g.monthly_needed_eur)} a month needed</span>`:''}</div>`).join('')+((S.goals||[]).length?hubGoals():'')+`<div class="home-hub-links">${hubLink('plan','Plan')}${hubLink('planning','Records')}</div>`;
  }catch{}
}
const hubOverview=overview;
overview=function(){
  hubOverview();const home=$('#view>.home');if(!home)return;
  const hero=$('.home-top .hero');
  if(hero){hero.insertAdjacentHTML('beforeend','<div class="hero-history" id="heroHistory" aria-label="Recorded net worth trend"></div>');const h=(S.history||[]).filter(p=>Number.isFinite(Number(p.net_worth))).slice(-120);$('#heroHistory').innerHTML=h.length>1?`<span class="muted small">Since ${fdate(h[0].date)}</span>${spark(h.map(p=>Number(p.net_worth)),{w:300,h:88})}`:'';}
  const plans=(S.savings_plans||[]).filter(p=>p.active),items=investItems(),groups={};items.forEach(p=>{groups[className(p.cls)]=(groups[className(p.cls)]||0)+p.value;});const invested=S.totals.invested,day=items.reduce((s,p)=>s+(p.day_change||0),0),groupRows=Object.entries(groups).sort((a,b)=>b[1]-a[1]);
  const investment=`<div class="home-hub-metrics">${hubMetric('Invested','<span id="homeInvested">'+eur(invested)+'</span>')}${hubMetric('Today','<span id="homeInvestmentDay">'+dayc(day,invested)+'</span>')}${hubMetric('Plans / month',eur(plans.reduce((s,p)=>s+p.per_month,0)))}</div><div class="home-invest-allocation">${groupRows.map(([name,v],i)=>`<div style="flex:${Math.max(0,v)};background:var(${SERIES[i%SERIES.length]})" title="${esc(name)}: ${fmtN(v)} EUR"></div>`).join('')}</div><div class="home-hub-allocation">${groupRows.map(([name,v],i)=>`<span><i style="background:var(${SERIES[i%SERIES.length]})"></i>${esc(name)} · ${eur(v)}</span>`).join('')}</div><div class="home-hub-links">${hubLink('holdings','Investments')}<button class="linkish small" type="button" data-int-tab="performance">Performance →</button>${hubLink('explore','Explore')}</div>`;
  const hub=document.createElement('div');hub.id='homeHub';hub.className='stack-y';hub.innerHTML=`<div class="grid g2 home-priorities">${hubCard('home-spending','Spending & income','spending','<div id="homeSpendingBody"><p class="muted small">Reading your payment history…</p></div>')}${hubCard('home-investments','Investments','holdings',investment)}</div><div class="grid g3">${hubCard('home-advice','Advice','advice',hubAdvice())}${hubCard('home-goals','Goals','plan','<div id="homeGoals">'+((S.goals||[]).length?hubGoals():'<p class="muted small">No goals yet.</p>')+`<div class="home-hub-links">${hubLink('plan','Plan')}</div></div>`)}${hubCard('home-savings','Savings & debt','cash',hubSavings())}</div>`;
  $('#askbar').after(hub);
  const recorded=(S.history||[]).filter(h=>Number.isFinite(h.self_directed)&&Number.isFinite(h.managed)).slice(-120);
  if(recorded.length>1)$('[data-card="home-investments"] .home-hub-links',hub).insertAdjacentHTML('beforebegin',`<div class="home-invest-trend">${spark(recorded.map(h=>h.self_directed+h.managed),{w:380,h:48})}</div>`);
  // Retain detailed history, accounts and personal pins below the broad summary.
  const history=$('#nwCard'),accounts=$('#acctCard'),pins=$('#pinsSlot');
  if(accounts)hub.before(accounts);if(history)accounts?accounts.before(history):hub.before(history);if(pins)home.append(pins);
  $('#intHome')?.remove();$('#monthStrip')?.remove();
  const oldAlloc=[...home.querySelectorAll(':scope>.grid.g3')].find(g=>g.querySelector('[data-pick="alloc"]'));oldAlloc?.remove();
  intBind(hub);fillHomeHub();openPageSections();
};
const hubQuietNumbers=quietNumbers;
quietNumbers=function(){hubQuietNumbers();if(view==='overview'){setHTML($('#homeInvested'),eur(S.totals.invested));const items=investItems();setHTML($('#homeInvestmentDay'),dayc(items.reduce((s,p)=>s+(p.day_change||0),0),S.totals.invested));}};
const hubBriefHtml=briefHtml;
briefHtml=function(){return hubBriefHtml()+`<div class="brief-prompts">${['Where could I save money?','Review my portfolio balance','What needs attention next?'].map(q=>`<button type="button" class="linkish small" data-home-question="${esc(q)}">${esc(q)}</button>`).join('')}</div>`;};
const hubWireBrief=wireBrief;
wireBrief=function(){hubWireBrief();$$('[data-home-question]').forEach(b=>b.onclick=()=>openChat({text:b.dataset.homeQuestion,send:true}));};
