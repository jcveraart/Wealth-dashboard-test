'use strict';
function paymentRangeError(f={}) {
  if(f.from&&f.to&&f.from>f.to)return 'Choose an end date on or after the start date.';
  const present=v=>v!==''&&v!=null;
  if([f.min,f.max].some(v=>present(v)&&(!Number.isFinite(Number(v))||Number(v)<0)))return 'Enter a positive amount or zero.';
  if(present(f.min)&&present(f.max)&&Number(f.min)>Number(f.max))return 'The maximum amount must be at least the minimum.';
  return '';
}
function filterPaymentRows(list,f={}) {
  if(paymentRangeError(f))return [];
  const min=f.min===''||f.min==null?null:Number(f.min),max=f.max===''||f.max==null?null:Number(f.max);
  return list.filter(t=>(!f.from||t.date>=f.from)&&(!f.to||t.date<=f.to)&&(min==null||Math.abs(t.amount)+1e-9>=min)&&(max==null||Math.abs(t.amount)-1e-9<=max));
}

function sortPaymentRows(list,sort={key:'date',direction:'desc'}) {
  const key=sort.key==='price'?'price':'date',sign=sort.direction==='asc'?1:-1;
  return [...list].sort((a,b)=>sign*(key==='price'?Math.abs(a.amount)-Math.abs(b.amount):a.date.localeCompare(b.date))||String(a.id).localeCompare(String(b.id)));
}
