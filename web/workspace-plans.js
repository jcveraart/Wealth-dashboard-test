'use strict';
FREQ.twice_monthly='twice a month';
INT_TABS.splice(2,0,['plans','Savings plans']);
const wsPlanHoldings=holdings;
holdings=function(){if(INT.tab!=='plans')return wsPlanHoldings();wsInvestmentPlans();};
async function wsInvestmentPlans(){
 const generation=++INT.generation;const range=$('#rangeSlot');if(range)range.innerHTML='';
 $('#view').innerHTML=`<div class="stack-y">${intNav()}<div class="ws-header"><div><h2>Savings plans</h2><p class="muted small">Recurring investments, with their own place beside your holdings.</p></div><button type="button" class="btn ghost" id="planAdd">Add plan</button></div><div id="wsPlansBody">${skeleton()}</div></div>`;intBind();
 try{const d=await wsGet('plans');if(view!=='holdings'||INT.tab!=='plans'||generation!==INT.generation)return;
  const accounts=Object.keys(d.accounts);const rows=d.items.filter(x=>x.active),stopped=d.items.filter(x=>!x.active);
  const table=items=>wsTable([['instrument','Investment',(v,r)=>`<b>${esc(v)}</b><div class="muted small">${esc(r.asset_class||'')}${r.starts_on?' · starts '+fdate(r.starts_on):''}${r.execution_fee_eur!=null?' · '+eur(r.execution_fee_eur,2)+' execution fee':''}${r.note?' · '+esc(r.note):''}</div>`],['account','Account'],['amount_eur','Per execution',v=>eur(v,2)],['frequency','Frequency',v=>esc(FREQ[v]||v)],['per_month','Monthly average',v=>eur(v,2)],['next','Next execution',(v,r)=>!r.active?'Stopped':v?fdate(v):'Schedule incomplete'],['index','',v=>`<button type="button" class="linkish small" data-plan="${v}">Edit</button>`]],items);
  $('#wsPlansBody').innerHTML=`<div class="stack-y"><div class="int-metrics">${intMetric('Active plans',rows.length)}${intMetric('Monthly average',eur(d.monthly_eur,2))}${intMetric('Annual planned contributions',eur(d.monthly_eur*12,2))}</div>${intCard('Scheduled investments',table(rows))}${accounts.length?intCard('By account',accounts.map(a=>`<div class="list-row"><span>${esc(a)}</span><b>${eur(d.accounts[a],2)} / month</b></div>`).join('')):''}<details class="card"><summary>Stopped plans (${stopped.length})</summary>${table(stopped)}</details>${wsScope(d.scope)}<p class="muted small">If the broker gives two monthly execution days, record both. Until then only the supplied starting date is shown. A zero execution fee does not mean a fund has zero ongoing costs.</p></div>`;wirePlans();
 }catch(e){if($('#wsPlansBody'))$('#wsPlansBody').innerHTML=wsEmpty(e.message);}
}
