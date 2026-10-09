'use strict';
/* Price, business and AI context first; detailed evidence remains available below. */
const COMPANY_VIEW={range:'1y',symbol:'',prices:null,timer:null,notesTimer:null};
const compactResearch=intResearch;
intResearch=function(r){
  clearTimeout(COMPANY_VIEW.timer);clearTimeout(COMPANY_VIEW.notesTimer);COMPANY_VIEW.prices=null;COMPANY_VIEW.symbol=INT.symbol;
  compactResearch(r);if(!r||r.status==='unavailable')return;
  const root=$('#intBody>.stack-y');root.classList.add('company-research');
  const head=$('.int-company-head',root),metrics=head.nextElementSibling,questions=metrics.nextElementSibling;
  const hero=document.createElement('section');hero.className='card research-hero';head.before(hero);hero.append(head,metrics);
  const search=$('#intResearchSearch');search.classList.add('research-search');$('#intTicker').type='text';
  const cap=$$('.int-metric b',metrics)[2];if(cap&&Number.isFinite(r.fundamentals.market_cap))cap.textContent=new Intl.NumberFormat('en-GB',{notation:'compact',maximumFractionDigits:1}).format(r.fundamentals.market_cap)+' '+(r.fundamentals.currency||'');
  const prime=document.createElement('div');prime.className='research-primary';hero.after(prime);
  prime.innerHTML=`<section class="card research-price" data-card="company-price"><div class="card-head"><h2>Stock price</h2>${seg('companyRange',[['1m','1M'],['3m','3M'],['1y','1Y'],['3y','3Y'],['all','All']],COMPANY_VIEW.range)}</div><div id="companyPriceChart"><p class="muted small">Reading recorded market prices…</p></div><p class="muted small" id="companyPriceSource"></p></section><section class="card research-brief brief page-ai-card no-tools" id="companyBrief"><div class="brief-head"><span class="claude-mark">${CLAUDE_ICON}</span><b>Claude</b><span class="muted small" id="companyBriefAge"></span></div><div id="companyBriefBody">${pageBriefNotes(initialCompanyBrief(r))}</div><span class="muted small" id="companyBriefStatus">${pageBriefStatus(initialCompanyBrief(r))}</span><form id="companyAsk" class="research-ask"><input type="text" aria-label="Ask about this company" placeholder="Ask about ${esc(r.name||INT.symbol)}…" autocomplete="off"><button class="btn ghost sm" type="submit">Ask Claude</button></form></section>`;
  // Existing research prompts become compact follow-ups inside the briefing.
  questions.classList.add('research-prompts');$('#companyBrief').append(questions);moveBriefToTop(hero,$('#companyBrief'),{className:'company-ai-top'});prime.classList.add('company-chart-row');
  const sections=[...root.children].filter(n=>n.matches('section.card'));
  const business=sections.find(n=>n.querySelector('h2')?.textContent==='Business overview'),news=sections.find(n=>n.querySelector('h2')?.textContent==='Recent developments');
  if(business&&news){const row=document.createElement('div');row.className='grid g2 research-business-news';prime.after(row);row.append(business,news);business.classList.add('research-business');news.classList.add('research-news');
    const p=$('.int-business',business);if(p&&p.textContent.length>520){const text=p.textContent; p.textContent=text.slice(0,520).replace(/\s+\S*$/,'')+'…';const more=document.createElement('button');more.className='linkish small';more.type='button';more.textContent='Read full business overview';p.after(more);more.onclick=()=>{p.textContent=text;more.remove();};}
    const rows=$$('.list-row',news);rows.slice(4).forEach(n=>n.hidden=true);if(rows.length>4){const more=document.createElement('button');more.className='linkish small';more.type='button';more.textContent='More headlines';news.append(more);more.onclick=()=>{rows.forEach(n=>n.hidden=false);more.remove();};}
  }
  const scores=[...root.querySelectorAll('section.card')].find(c=>c.querySelector('h2')?.textContent==='Opportunity components');
  if(scores){const heading=scores.querySelector('h2');scores.replaceChildren(heading);scores.insertAdjacentHTML('beforeend',`<div class="research-scores">${(r.score.components||[]).map(c=>`<div class="research-score"><span>${esc(c.name)}</span><div class="int-track"><i style="width:${Math.max(0,Math.min(100,c.score||0))}%"></i></div><b>${c.score==null?'—':intNum(c.score,0)}</b></div>`).join('')}</div><p class="muted small">Screening rules · ${intPct(r.score.coverage_pct,0)} data coverage. Missing evidence stays unavailable; the score is not an expected return.</p>`);}
  onSeg('companyRange',range=>{COMPANY_VIEW.range=range;$$('[data-seg="companyRange"] button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===range));drawCompanyPrice();});
  $('#companyAsk').onsubmit=e=>{e.preventDefault();const input=e.target.querySelector('input'),question=input.value.trim();if(!question)return;openChat({text:`About ${INT.symbol} (${r.name}): ${question}\nUse the company tools and current sources; consider my current portfolio and distinguish source dates, facts and assumptions.`,send:true});};
  intBind(root);loadCompanyPrice(INT.symbol);loadCompanyBrief(INT.symbol);
};
function companyPageStill(symbol,owner){return owner?.isConnected&&view==='explore'&&EXP.tab==='research'&&INT.symbol===symbol;}
async function loadCompanyPrice(symbol,attempt=0){
  const owner=$('#companyPriceChart');if(!owner)return;
  try{const data=await cachedJSON('/api/company-price?symbol='+encodeURIComponent(symbol),{ttl:60000,force:attempt>0});if(!companyPageStill(symbol,owner))return;
    COMPANY_VIEW.prices=data;
    const selected=owner.querySelector('.tc-sel')?.getAttribute('width');
    if(!owner.matches(':hover')&&!(selected&&Number(selected)>0))drawCompanyPrice();
    $('#companyPriceSource').textContent=(data.source||'Market data')+' · '+(data.currency||data.rows?.[0]?.currency||'Quote currency unavailable')+(data.retrieved_at?' · retrieved '+intDate(data.retrieved_at):'')+(data.stale?' · cached':'')+(data.adjusted?' · adjusted close (fallback)':' · daily close')+(data.updating?' · updating':'');
    if(data.updating&&attempt<12)COMPANY_VIEW.timer=setTimeout(()=>{if(companyPageStill(symbol,owner))loadCompanyPrice(symbol,attempt+1);},10000);
  }catch{if(companyPageStill(symbol,owner))owner.innerHTML='<p class="muted small">Market-price history is unavailable. Update company data to retrieve public prices.</p>';}
}
intDatasetHtml=function(r){
  const statements=r.statements||{};
  const table=(title,rows,columns)=>`<div class="research-dataset"><h4>${esc(title)}</h4>${intTable(columns,rows,row=>`<tr>${columns.map(([key])=>`<td>${row[key]==null?'—':typeof row[key]==='number'?intNum(row[key],0):esc(row[key])}</td>`).join('')}</tr>`,'company-'+title.toLowerCase().replace(/[^a-z0-9]+/g,'-'))}</div>`;
  const annual=(key,fields)=>table(key.charAt(0).toUpperCase()+key.slice(1),(statements[key]||[]).map(row=>({period:row.period,currency:row.currency,...Object.fromEntries(fields.map(([k,label])=>[label,row.items?.[k]??null]))})),[['period','Period'],['currency','Currency'],...fields.map(([,label])=>[label,label])]);
  const generic=(title,rows)=>{rows=Array.isArray(rows)?rows:[];const keys=[...new Set(rows.flatMap(row=>Object.keys(row)))].filter(k=>rows.some(row=>row[k]!=null&&typeof row[k]!=='object')).slice(0,6);return table(title,rows.slice(0,12),keys.map(k=>[k,k.replaceAll('_',' ')]));};
  return annual('income',[['Total Revenue','Revenue'],['Operating Income','Operating income'],['Net Income','Net income']])+annual('balance',[['Total Assets','Assets'],['Total Debt','Debt'],['Cash And Cash Equivalents','Cash']])+annual('cashflow',[['Operating Cash Flow','Operating cash flow'],['Capital Expenditure','Capital expenditure'],['Free Cash Flow','Free cash flow']])+generic('Analyst estimates',r.analyst_estimates)+generic('Estimate revisions',r.estimate_changes)+generic('Institutional holders',r.institutional_ownership)+`<p class="muted small">Other datasets: ${r.sec_statements?'SEC statements available':'SEC statements unavailable'} · ${r.openbb?'OpenBB snapshot available':'OpenBB unavailable'} · ${Object.values(r.alternative||{}).filter(Boolean).length} alternative source snapshots. Use the company conversation to inspect source evidence in context.</p>`;
};
function drawCompanyPrice(){
  const owner=$('#companyPriceChart'),data=COMPANY_VIEW.prices;if(!owner||!data)return;
  const days={ '1m':31,'3m':93,'1y':366,'3y':1096},cutoff=days[COMPANY_VIEW.range]?isoD(new Date(Date.now()-days[COMPANY_VIEW.range]*864e5)):'';
  const rows=(data.rows||[]).filter(r=>Number.isFinite(r.close)&&r.close>0&&(!cutoff||r.date>=cutoff));
  if(rows.length<2){owner.innerHTML='<p class="muted small">Not enough recorded price history for this period. Try a longer range or update company data.</p>';return;}
  timeChart(owner,{series:[{name:COMPANY_VIEW.symbol,pts:rows.map(r=>[tOf(r.date),r.close]),color:'var(--s1)',area:true}],height:260,unit:data.currency||rows[0].currency||'',select:true,label:'Daily stock price'});
}
async function loadCompanyBrief(symbol,attempt=0){
  const owner=$('#companyBrief');if(!owner)return;
  try{const d=await cachedJSON('/api/company-briefing?symbol='+encodeURIComponent(symbol),{ttl:60000,force:attempt>0});if(!companyPageStill(symbol,owner))return;
    $('#companyBriefBody').innerHTML=pageBriefNotes(d);$('#companyBriefStatus').textContent=pageBriefStatus(d);$('#companyBriefAge').textContent=d.source_time?'Evidence '+intDate(d.source_time):'';
    if(d.updating&&attempt<16)COMPANY_VIEW.notesTimer=setTimeout(()=>{if(companyPageStill(symbol,owner))loadCompanyBrief(symbol,attempt+1);},15000);
  }catch{if(companyPageStill(symbol,owner))$('#companyBriefStatus').textContent='Showing saved observations · Ask Claude to look further';}
}
