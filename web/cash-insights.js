'use strict';
async function drawCashHistory(rows){
  const owner=$('#cashHistory');if(!owner)return;
  let daily={};try{daily=await loadAcctDaily();}catch{}
  if(!owner.isConnected)return;
  // Broker account histories contain holdings plus cash, so they cannot stand in for cash history.
  const names=new Set(rows.filter(r=>r.source==='savings').map(r=>r.name)),history=S.account_history||[],series=[];
  const recorded=name=>{const points=new Map((daily[name]||[]).filter(r=>Number.isFinite(r.value)).map(r=>[r.date,r.value]));for(const r of history.filter(r=>r.account===name&&Number.isFinite(r.value_eur)))points.set(r.date,r.value_eur);return [...points].sort(([a],[b])=>a.localeCompare(b));};
  for(const name of names){const points=recorded(name);if(points.length>1)series.push({name,pts:points.map(([date,value])=>[tOf(date),value])});}
  if(series.length)timeChart($('#cashHistory'),{series,height:210,unit:'€',select:true});
  else $('#cashHistory').innerHTML='<p class="muted small">Import dated account balances to build cash history. Fixed deposits and securities are excluded.</p>';
  const debts=S.debts.filter(d=>!d.expected_gift),debtSeries=[];
  for(const d of debts){const points=recorded(d.name);if(points.length>1)debtSeries.push({name:d.name,pts:points.map(([date,value])=>[tOf(date),Math.abs(value)])});}
  if(debtSeries.length)timeChart($('#debtHistory'),{series:debtSeries,height:210,unit:'€',select:true});
  else {const recorded=(S.history||[]).filter(h=>Number.isFinite(h.debt)),span=recorded.length?(tOf(recorded.at(-1).date)-tOf(recorded[0].date))/864e5:0;
    // a few days of a balance that barely moves says nothing yet: leave the card out until there is a month to show
    if(span<30){$('#debtHistory').closest('.card').hidden=true;return;}
    if(recorded.length>1)timeChart($('#debtHistory'),{series:[{name:'Total counted debt',pts:recorded.map(h=>[tOf(h.date),h.debt])}],height:210,unit:'€',select:true});else $('#debtHistory').innerHTML='<p class="muted small">More dated debt balances will build this graph. No earlier balances are estimated.</p>';}
}
function drawCashDebtScenario(d,i){
  const box=$('#debtProjection'+i),note=$('#debtScenarioSummary'+i),payInput=$(`[data-scenario-pay="${i}"]`),extraInput=$(`[data-scenario-extra="${i}"]`);
  const pay=payInput.value===''?NaN:Number(payInput.value),extra=extraInput.value===''?NaN:Number(extraInput.value),months=Number($(`[data-scenario-years="${i}"]`).value)*12;
  const base=projectDebt(d.balance,d.rate_pct,pay,months),fast=projectDebt(d.balance,d.rate_pct,pay,months,extra),keep=projectDebt(d.balance,d.rate_pct,0,months);
  if(!base||!fast||!keep){box.innerHTML='';note.textContent=d.rate_pct==null?'Add your confirmed interest rate to project this debt.':'Enter valid, nonnegative repayment amounts.';return;}
  const pts=r=>r.points.filter((_,n)=>n%3===0||n===r.points.length-1).map(p=>[tOf(p.date),p.balance]);
  timeChart(box,{series:[{name:'No repayment (illustration)',pts:pts(keep),color:'var(--muted)'},{name:'Monthly repayment',pts:pts(base),color:'var(--s1)'},...(extra?[{name:'With extra repayment',pts:pts(fast),color:'var(--s3)'}]:[])],height:220,unit:'€',zero:true,select:true});
  const end=base.points.at(-1).date;
  note.innerHTML=`Balance in ${fdate(end)}: <b>${eur(base.balance)}</b> with ${eur(pay)} / month · <b>${eur(base.interest)}</b> projected interest.${base.payoff!=null?' Cleared '+fdate(base.points[base.payoff].date)+'.':' Not fully repaid within this horizon.'}${extra?` With ${eur(extra)} extra: <b>${eur(fast.balance)}</b> remaining, ${eur(base.interest-fast.interest)} less interest over the same horizon.${fast.payoff!=null?' Cleared '+fdate(fast.points[fast.payoff].date)+'.':''}`:''}`;
}
async function loadCashNotes(){
  const card=$('#cashNotes');if(!card)return;
  try{const d=await cachedJSON('/api/cash-briefing',{ttl:60000});if(!card.isConnected)return;
    $('#cashNotesBody').innerHTML=pageBriefNotes(d);$('#cashBriefStatus').textContent=pageBriefStatus(d);
    if(d.updating)setTimeout(async()=>{if(card.isConnected){DATA_CACHE.delete('/api/cash-briefing');await loadCashNotes();}},15000);
  }catch{if(card.isConnected)$('#cashBriefStatus').textContent='Showing saved observations · Ask Claude to look further';}
}
