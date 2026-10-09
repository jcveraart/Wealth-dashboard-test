'use strict';
/* Cash excludes securities and fixed deposits, regardless of net-worth classification. */
function liquidCashRows(state){
  const rows=(state.savings||[]).filter(s=>!s.maturity&&s.kind!=='deposit').map(s=>({...s,source:'savings',index:state.savings.indexOf(s)}));
  const names=new Set(rows.map(r=>r.name.trim().toLowerCase()));
  for(const a of state.accounts||[]){if(!names.has(a.name.trim().toLowerCase())&&Number.isFinite(a.cash)&&a.cash!==0)rows.push({name:a.name,value:a.cash,rate_pct:a.cash_rate_pct??null,source:'broker',snapshot_date:a.updated});}
  return rows;
}
function projectDebt(balance,rate,payment,months=120,extra=0,start=today()){
  if(!Number.isFinite(balance)||balance<0||!Number.isFinite(rate)||rate<0||!Number.isFinite(payment)||payment<0||!Number.isFinite(extra)||extra<0)return null;
  const [year,month,day]=start.split('-').map(Number),points=[{date:start,balance,interest:0,paid:0}],r=rate/1200;
  let interest=0,paid=0,payoff=balance===0?0:null;
  for(let i=1;i<=months;i++){
    const charge=balance*r,pay=Math.min(balance+charge,payment+extra);interest+=charge;paid+=pay;balance=Math.max(0,balance+charge-pay);
    const last=new Date(Date.UTC(year,month-1+i+1,0)).getUTCDate(),date=new Date(Date.UTC(year,month-1+i,Math.min(day,last))).toISOString().slice(0,10);
    points.push({date,balance,interest,paid});if(payoff===null&&balance<=.005)payoff=i;
  }
  return {points,balance,interest,paid,payoff};
}
