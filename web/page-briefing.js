'use strict';
/* One home-style briefing surface: ready observations, quiet updates and a scoped conversation. */
function briefObservationText(text,limit=300){
  text=String(text||'');if(text.length<=limit)return text;
  const part=text.slice(0,limit),end=part.lastIndexOf('. ');
  return end>limit*.55?part.slice(0,end+1):part.replace(/\s+\S*$/,'')+'…';
}
function pageBriefNotes(d={}){
  const sources=new Map((d.sources||[]).map(s=>[s.id,s]));
  return `<ul class="brief-lines">${(d.items||[]).slice(0,3).map(item=>`<li><p class="brief-line">${esc(briefObservationText(item.text))}</p>${(item.sources||[]).map(id=>sources.get(id)).filter(Boolean).slice(0,1).map(s=>`<a class="small h-link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}${s.date?' · '+intDate(s.date):''} ↗</a>`).join('')}${item.risk?`<p class="muted small brief-risk">Risk: ${esc(briefObservationText(item.risk,150))}</p>`:''}${item.source_date?`<span class="muted small">Idea recorded ${fdate(item.source_date)}</span>`:''}${item.url?`<a class="small h-link" href="${esc(item.url)}" target="_blank" rel="noopener">Source ↗</a>`:''}</li>`).join('')}</ul>`;
}
function pageBriefStatus(d={}){if(S?.status?.demo)return 'Fictional demo observations · no live AI';if(d.by==='demo')return 'Saved demo example · no live AI request';return d.updating?'Claude is looking again…':'';}
function initialCashBrief(){
  return cachedData('/api/cash-briefing')||S.page_briefings?.cash||{items:[{text:'Your withdrawable balances and recorded debt rates are shown here. Keep your emergency buffer available before considering an extra repayment.'}],by:'facts'};
}
function initialPortfolioBrief(){
  const account=INVF.acct||'',asset=INVF.cls,url='/api/investment-briefing?'+new URLSearchParams({account,asset}),cached=cachedData(url);
  if(cached?.items?.length)return cached;
  if(!account&&asset==='all'&&S.page_briefings?.investments?.items?.length)return S.page_briefings.investments;
  const rows=invFiltered(investItems()),total=rows.reduce((n,p)=>n+p.value,0),items=[];
  if(rows.length&&total>0){const largest=rows.reduce((a,b)=>a.value>b.value?a:b);items.push({text:`${largest.name} makes up ${(largest.value/total*100).toFixed(1)}% of this investment selection.`});}
  const priced=rows.filter(p=>p.live&&Number.isFinite(p.day_change));
  if(priced.length){const move=priced.reduce((a,b)=>Math.abs(a.day_change)>Math.abs(b.day_change)?a:b);items.push({text:`${move.name} has the largest recorded price contribution today: ${sgn(move.day_change)}. Price moves are different from your cash-flow-adjusted return.`});}
  if(!items.length)items.push({text:'Review this selection’s recorded values, interest and upcoming maturities. Ask Claude to look at the trade-offs with current sources.'});
  return {items,by:'facts'};
}
function initialCompanyBrief(r){
  const cached=cachedData('/api/company-briefing?symbol='+encodeURIComponent(INT.symbol));if(cached)return cached;
  if(r.briefing)return r.briefing;
  const items=[];if(r.overview)items.push({text:r.overview});if(r.news?.[0])items.push({text:r.news[0].title+' · '+(r.news[0].date||'Date unavailable')});
  items.push({text:'The portfolio-fit panel compares concentration and exposure with your current holdings. Treat this as context alongside valuation, business risks and source dates.'});return {items,by:'facts'};
}
function moveBriefToTop(summary,brief,{className=''}={}){
  const row=document.createElement('div');row.className='page-ai-top '+className;summary.before(row);row.append(summary,brief);
  summary.classList.add('page-ai-summary');brief.classList.add('brief','page-ai-card');return row;
}
function initialPageBrief(page){
  const ready=cachedData('/api/page-briefing?page='+page)||S.page_briefings?.[page];if(ready?.items?.length)return ready;
  let items=[];
  if(page==='advice')items=(S.advice||[]).slice(0,2).map(r=>({text:r.title+'. '+(r.detail||r.why||'')}));
  if(!items.length)items=[{text:page==='advice'?'Review your recorded goals and open actions. Ask Claude what deserves attention next.':'Use your current portfolio as context for new opportunities. Check diversification, valuation, risks and the date of the evidence before making a decision.'}];
  return {items,by:'facts'};
}
function pageBriefCard(page,label){
  const initial=initialPageBrief(page);
  return `<section class="card brief page-ai-card no-tools" id="pageBrief-${page}"><div class="brief-head"><span class="claude-mark">${CLAUDE_ICON}</span><b>Claude</b><span class="ago">${esc(label)}</span></div><div data-page-notes>${pageBriefNotes(initial)}</div><span class="muted small" data-page-status>${pageBriefStatus(initial)}</span><button type="button" class="linkish brief-ask" data-page-ask>Ask about this →</button></section>`;
}
async function wirePageBrief(page,label,attempt=0){
  const card=$('#pageBrief-'+page);if(!card)return;
  let observations=initialPageBrief(page);
  $('[data-page-ask]',card).onclick=()=>openChat({ctx:{title:label,text:JSON.stringify(observations.items||[])},text:'Review the information on this '+label+' page. Help me identify the most useful next step and any important missing evidence.'});
  try{const d=await cachedJSON('/api/page-briefing?page='+page,{ttl:60000,force:attempt>0});if(!card.isConnected)return;observations=d;$('[data-page-notes]',card).innerHTML=pageBriefNotes(d);$('[data-page-status]',card).textContent=pageBriefStatus(d);
    if(d.updating&&attempt<12)setTimeout(()=>{if(card.isConnected)wirePageBrief(page,label,attempt+1);},15000);
  }catch{if(card.isConnected)$('[data-page-status]',card).textContent='Showing saved observations · Ask Claude to look further';}
}
