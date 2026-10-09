"""Cash-flow accounting with explicit completeness requirements and no inferred trades."""
import csv
import hashlib
import io
import json
import math
from collections import defaultdict, deque
from datetime import date, timedelta
from . import store

TYPES={'buy','sell','dividend','interest','fee','tax','deposit','withdrawal','split','transfer-in','transfer-out','redemption'}

def xirr(flows):
    merged=defaultdict(float)
    for d,v in flows:merged[date.fromisoformat(d)]+=float(v)
    values=sorted((d,v) for d,v in merged.items() if abs(v)>.0000001)
    if len(values)<2 or not any(v<0 for _,v in values) or not any(v>0 for _,v in values):return {'value_pct':None,'reason':'Dated positive and negative investor cash flows are required.'}
    start=values[0][0];years=[((d-start).days/365.25,v) for d,v in values]
    if years[-1][0]<=0:return {'value_pct':None,'reason':'Cash flows must span more than one date.'}
    # Scan in log(1+r) space and report ambiguous roots rather than silently selecting one.
    def f(z):
        try:return sum(v*math.exp(-z*t) for t,v in years)
        except OverflowError:return None
    grid=[-12+i*24/960 for i in range(961)];roots=[]
    for left,right in zip(grid,grid[1:]):
        fl,fr=f(left),f(right)
        if fl is None or fr is None or not math.isfinite(fl) or not math.isfinite(fr):continue
        if fl==0:roots.append(left);continue
        if fl*fr>=0:continue
        for _ in range(100):
            mid=(left+right)/2;fm=f(mid)
            if abs(fm)<1e-8:break
            if fl*fm<0:right=mid
            else:left=mid;fl=fm
        roots.append((left+right)/2)
    unique=[]
    for r in roots:
        if not any(abs(r-u)<1e-6 for u in unique):unique.append(r)
    if len(unique)!=1:return {'value_pct':None,'reason':'Multiple possible money-weighted returns.' if unique else 'No supported money-weighted return root found.'}
    return {'value_pct':round(math.expm1(unique[0])*100,5),'reason':None,'annualized':True,'days':(values[-1][0]-start).days}

def calculate(valuations,flows,complete=False):
    vals={str(r['date'])[:10]:float(r.get('value_eur',r.get('value'))) for r in valuations}
    vals=sorted(vals.items());out={'twr_pct':None,'money_weighted':{'value_pct':None},'modified_dietz_pct':None,'profit_eur':None,'curve':[],
      'scope':'Account-level valuation history. External cash flows are positive into the account; end-of-day flow convention. TWR requires valuations on each intervening flow date.',
      'complete':bool(complete),'reason':None}
    if len(vals)<2:out['reason']='At least two recorded account valuations are required.';return out
    start,end=vals[0][0],vals[-1][0];opening,closing=vals[0][1],vals[-1][1]
    out.update(start=start,end=end,opening_eur=round(opening,2),closing_eur=round(closing,2))
    if not complete:out['reason']='External flow coverage has not been confirmed for this period. Recorded value is available; adjusted performance is withheld.';return out
    relevant=[r for r in flows if start<r['date']<=end]
    amounts=defaultdict(float)
    for r in relevant:amounts[r['date']]+=float(r['amount_eur'])
    net=sum(amounts.values());out['net_contributions_eur']=round(net,2);out['profit_eur']=round(closing-opening-net,2)
    out['money_weighted']=xirr([(start,-opening)]+[(d,-v) for d,v in amounts.items()]+[(end,closing)])
    duration=(date.fromisoformat(end)-date.fromisoformat(start)).days
    weighted=sum(v*(date.fromisoformat(end)-date.fromisoformat(d)).days/duration for d,v in amounts.items()) if duration else 0
    denominator=opening+weighted
    if denominator>0:out['modified_dietz_pct']=round((closing-opening-net)/denominator*100,5)
    if any(d not in dict(vals) for d in amounts):out['reason']='A valuation is missing on an external cash-flow date; TWR is withheld. Modified Dietz is an approximation.';return out
    index=100.;out['curve']=[{'date':start,'index':100.,'value_eur':opening,'external_flow_eur':0}]
    previous=opening
    for d,value in vals[1:]:
        if previous<=0:out['reason']='An opening subperiod valuation is nonpositive; TWR is unavailable.';out['curve']=[];return out
        growth=(value-amounts[d])/previous
        if growth<0:out['reason']='Recorded values and flows produce a negative subperiod growth factor; review the evidence.';out['curve']=[];return out
        index*=growth;out['curve'].append({'date':d,'index':round(index,6),'value_eur':value,'external_flow_eur':round(amounts[d],2)})
        previous=value
    out['twr_pct']=round(index-100,5)
    return out

def normalize(row):
    account=str(row.get('account') or '').strip()[:150];typ=str(row.get('type') or '').lower()
    if not account or typ not in TYPES:raise ValueError('Ledger rows need an account and a supported transaction type.')
    d=store.iso(row.get('date'));currency=str(row.get('currency') or '').upper()
    if not len(currency)==3 or not currency.isalpha():raise ValueError('Ledger currency is required.')
    amount=store.finite(row.get('amount'),nullable=True);units=store.finite(row.get('units'),nullable=True)
    executed=str(row.get('executed_at') or '').strip()
    if executed:
        from datetime import datetime
        try:
            moment=datetime.fromisoformat(executed.replace('Z','+00:00'))
            if moment.date().isoformat()!=d:raise ValueError()
        except ValueError:raise ValueError('Execution time must be an ISO timestamp on the ledger date.')
    if typ in ('buy','sell') and (units is None or not units or amount is None):raise ValueError('Trades require nonzero units and cash amount.')
    if amount is not None and (typ in ('buy','withdrawal','fee','tax') and amount>0 or typ in ('sell','deposit') and amount<0):raise ValueError('Cash direction does not agree with the transaction type.')
    return {'account':account,'date':d,'executed_at':executed,'type':typ,'currency':currency,'amount':amount,'units':units,
      'instrument':str(row.get('instrument') or row.get('isin') or '')[:100], 'name':str(row.get('name') or '')[:250],
      'source_id':str(row.get('source_id') or '')[:100], 'reference':str(row.get('reference') or '')[:250],
      'amount_eur':store.finite(row.get('amount_eur',amount if currency=='EUR' else None),nullable=True),
      'fee_eur':store.finite(row.get('fee_eur'),0,nullable=True),'tax_eur':store.finite(row.get('tax_eur'),0,nullable=True),
      'split_ratio':store.finite(row.get('split_ratio'),.000001,nullable=True),
      'gross_eur':store.finite(row.get('gross_eur'),nullable=True)}

def ingest(rows,source_id=''):
    checked=[normalize({**r,'source_id':r.get('source_id') or source_id}) for r in rows]
    seen=defaultdict(int);added=0
    with store.connect() as c:
        for r in checked:
            identity={k:r[k] for k in ('account','date','executed_at','type','currency','amount','units','instrument','reference')}
            raw=json.dumps(identity,sort_keys=True);seen[raw]+=1
            ident=hashlib.sha256((raw+'|'+str(seen[raw])).encode()).hexdigest()[:32]
            result=c.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,r['account'],r['date'],r['type'],r['instrument'],r['currency'],r['amount'],r['units'],r['source_id'],json.dumps(r,allow_nan=False)))
            added+=result.rowcount
    return {'added':added,'duplicates':len(checked)-added,'rows':len(checked)}

def ledger(account=''):
    rows=store.rows('SELECT * FROM ledger WHERE account=? ORDER BY date,id',(account,)) if account else store.rows('SELECT * FROM ledger ORDER BY date,id')
    return [{**json.loads(r['payload']),'id':r['id']} for r in rows]

def from_tr(rows,source_id=''):
    import app
    out=[];mapping={'BUY':'buy','SELL':'sell','DIVIDEND':'dividend','DISTRIBUTION':'dividend','INTEREST_PAYMENT':'interest','DEPOSIT':'deposit','WITHDRAWAL':'withdrawal','FINAL_MATURITY':'redemption'}
    for r in rows:
        typ=mapping.get(r.get('type'))
        if not typ:continue
        amt=app.num(r.get('amount'))+app.num(r.get('fee'))+app.num(r.get('tax'))
        out.append({'account':'Trade Republic','date':r['datetime'][:10],'executed_at':r['datetime'] if 'T' in r['datetime'] else '', 'type':typ,'instrument':r.get('symbol') or '',
          'name':r.get('name') or '', 'amount':amt,'units':app.num(r.get('shares')) or None,'currency':r.get('currency') or 'EUR',
          'fee_eur':abs(app.num(r.get('fee'))) if (r.get('currency') or 'EUR')=='EUR' else None,'tax_eur':abs(app.num(r.get('tax'))) if (r.get('currency') or 'EUR')=='EUR' else None,
          'gross_eur':app.num(r.get('amount')) if (r.get('currency') or 'EUR')=='EUR' else None,'reference':r.get('id') or r.get('reference') or '', 'source_id':source_id})
    return ingest(out,source_id)

def parse_csv(raw):
    from ai import decode_text
    import spending
    rows=spending.table_from_text(decode_text(raw))
    if not rows:return None
    names=[str(x).strip().lower() for x in rows[0]]
    if not {'account','date','type','currency','amount'}.issubset(names):return None
    result=[]
    for row in rows[1:]:
        item=dict(zip(names,row))
        for k in ('amount','units','amount_eur','fee_eur','tax_eur','gross_eur','split_ratio'):
            if k in item:item[k]=spending.parse_amount(item[k]) if item[k].strip() else None
        item['date']=spending.parse_date(item['date'])
        result.append(item)
    return result

def fifo(rows,current_units=None):
    lots=deque();realized=0.;sold=0.;errors=[]
    grouped=defaultdict(list)
    for r in rows:grouped[r['date']].append(r)
    for stamp,group in grouped.items():
        if {'buy','sell'}<={r['type'] for r in group} and not all(r.get('executed_at') for r in group if r['type'] in ('buy','sell')):errors.append('Mixed buys and sales on '+stamp+' need verified execution timestamps for FIFO.')
    for r in sorted(rows,key=lambda r:(r['date'],r.get('executed_at') or '',r.get('id',''))):
        typ=r['type'];u=abs(r.get('units') or 0);amt=r.get('amount_eur')
        if typ in ('buy','sell') and (amt is None or not u):errors.append('Missing EUR trade value or units on '+r['date']);continue
        if typ=='buy':lots.append([u,abs(amt)/u,r['date']])
        elif typ in ('sell','redemption') and u:
            left=u;cost=0
            while left>1e-8 and lots:
                n=min(left,lots[0][0]);cost+=n*lots[0][1];lots[0][0]-=n;left-=n
                if lots[0][0]<=1e-8:lots.popleft()
            if left>1e-8:errors.append('A sale has no complete opening lots on '+r['date'])
            elif amt is not None:realized+=amt-cost;sold+=u
        elif typ=='split':
            ratio=r.get('split_ratio')
            if not ratio:errors.append('Unverified split ratio on '+r['date'])
            else:
                for lot in lots:lot[0]*=ratio;lot[1]/=ratio
        elif typ in ('transfer-in','transfer-out'):errors.append('Transferred opening lots require their verified cost basis on '+r['date'])
    units=sum(l[0] for l in lots)
    if current_units is not None and abs(units-current_units)>max(1e-6,abs(current_units)*1e-6):errors.append('Imported remaining units do not reconcile with the current position.')
    return {'remaining_units':round(units,8),'remaining_cost_eur':round(sum(l[0]*l[1] for l in lots),2) if not errors else None,
      'realized_eur':round(realized,2) if not errors else None,'sold_units':sold,'lots':[{'units':u,'cost_per_unit_eur':p,'date':d} for u,p,d in lots],
      'complete':not errors,'issues':errors,'method':'FIFO; EUR execution cash including explicitly imported fees. An incomplete history withholds gains.'}

def account_report(cfg,state,account,start=None,end=None):
    import app
    positions=[p for p in state['positions'] if p['account']==account]
    events=ledger(account)
    # Existing held-position trade records are usable evidence but do not certify the account's external flows.
    for a in cfg.get('accounts',[])+[cfg.get('managed',{})]:
        if a.get('name','Managed portfolio')!=account:continue
        for p in a.get('positions',[]):
            instrument=p.get('isin') or p.get('name','')
            if any(r['instrument']==instrument for r in events):continue
            for t in p.get('trades',[]):
                if t.get('type') not in ('buy','sell','dividend','interest'):continue
                events.append({'id':'held:'+hashlib.sha256(json.dumps(t,sort_keys=True).encode()).hexdigest()[:20],
                  'account':account,'instrument':instrument,'name':p['name'],'date':t['date'],'type':t['type'],
                  'amount_eur':t.get('amount'),'amount':t.get('amount'),'units':t.get('units'),'currency':'EUR',
                  'source_id':'','source':'Existing imported holding trades','fee_eur':None,'tax_eur':None})
    valuations=app.account_history(account)
    valuations += [{'date':h['date'],'value':h['value_eur']} for h in cfg.get('account_history',[]) if h.get('account')==account and h.get('value_eur') is not None and h['date'] not in {v['date'] for v in valuations}]
    valuations += [r for r in store.records('valuation') if r['account']==account]
    flows=[{'date':r['date'],'amount_eur':r['amount_eur'],'source':r.get('source_id')} for r in events if r['type'] in ('deposit','withdrawal') and r.get('amount_eur') is not None]
    flows += [r for r in store.records('flow') if r['account']==account]
    valuations=[{**r,'value':r.get('value_eur',r.get('value'))} for r in valuations]
    valuations=list({r['date']:r for r in valuations}.values())
    start=store.iso(start) if start else None
    end=store.iso(end) if end else None
    if start and end and start>end:raise ValueError('The period start must precede its end.')
    within=lambda r:(not start or r['date']>=start) and (not end or r['date']<=end)
    valuations=[r for r in valuations if within(r)]
    flows=[r for r in flows if within(r)]
    manual_flows=store.records('flow');duplicates=[r for r in manual_flows if r['account']==account and within(r) and any(e['type'] in ('deposit','withdrawal') and e['date']==r['date'] and e.get('amount_eur')==r['amount_eur'] for e in events)]
    declaration=store.record('coverage',account,{})
    dates=sorted(v['date'] for v in valuations)
    complete=bool(not duplicates and declaration.get('confirmed') and dates and declaration.get('from','9999')<=dates[0] and declaration.get('to','')>=dates[-1])
    result=calculate(valuations,flows,complete)
    if duplicates:result['reason']='A manually recorded flow may duplicate an imported deposit or withdrawal. Review the flow records before calculating adjusted returns.'
    groups=defaultdict(list)
    for r in events:groups[r['instrument']].append(r)
    holdings={p.get('isin') or p['name']:p for p in positions}
    lots=[]
    for instrument,rows in groups.items():
        if not instrument:continue
        current=holdings.get(instrument)
        item=fifo(rows,current.get('units') if current else 0)
        lots.append({'instrument':instrument,'name':rows[-1].get('name') or instrument,**item,
          'current_value_eur':current['value'] if current else 0,
          'unrealized_eur':round(current['value']-item['remaining_cost_eur'],2) if current and item['complete'] else None})
    sums=defaultdict(float);months=defaultdict(lambda:defaultdict(float))
    for r in [r for r in events if within(r)]:
        if r.get('amount_eur') is not None:sums[r['type']]+=r['amount_eur'];months[r['date'][:7]][r['type']]+=r['amount_eur']
        for k in ('fee_eur','tax_eur'):
            if r.get(k) is not None:sums[k]+=r[k]
    return {'account':account,'performance':result,'valuations':sorted(valuations,key=lambda r:r['date']),
      'flows':sorted(flows,key=lambda r:r['date']),'events':sorted(events,key=lambda r:r['date'],reverse=True),
      'lots':lots,'totals':{k:round(v,2) for k,v in sums.items()},
      'monthly':[{'month':m,**{k:round(v,2) for k,v in values.items()}} for m,values in sorted(months.items())],
      'flow_records':[r for r in manual_flows if r['account']==account and within(r)],'potential_duplicate_flows':duplicates,
      'period':{'from':start,'to':end},'coverage':declaration,'scope':'Returns, flows and cash totals use the selected period and actual recorded endpoint valuations. FIFO lots and execution evidence retain the full available history; unknown fields remain unavailable.'}

def bond_metrics(face,price,coupon_pct,maturity,frequency=1,settlement=None,accrued=0,fee=0):
    settlement=settlement or date.today();mat=date.fromisoformat(maturity)
    if mat<=settlement:raise ValueError('Maturity must be after settlement.')
    if frequency not in (1,2,4):raise ValueError('Use annual, semiannual or quarterly coupons.')
    flows=[];cursor=mat
    from .cashflow import advance
    step=12//frequency
    while cursor>settlement:
        flows.append((cursor,face*coupon_pct/100/frequency+(face if cursor==mat else 0)))
        y,m=divmod(cursor.year*12+cursor.month-1-step,12);m+=1
        import calendar
        cursor=date(y,m,min(mat.day,calendar.monthrange(y,m)[1]))
    cash=[(settlement.isoformat(),-(price+accrued+fee))]+[(d.isoformat(),v) for d,v in sorted(flows)]
    result=xirr(cash);ytm=result['value_pct'];duration=None
    if ytm is not None:
        discounted=[((d-settlement).days/365.25,v/(1+ytm/100)**((d-settlement).days/365.25)) for d,v in flows]
        total=sum(v for _,v in discounted)
        duration=sum(t*v for t,v in discounted)/total/(1+ytm/100) if total else None
    return {'yield_to_maturity_pct':ytm,'modified_duration_years':duration,'cashflows':[{'date':d.isoformat(),'amount_eur':round(v,2)} for d,v in sorted(flows)],
      'cost_eur':round(price+accrued+fee,2),'scope':'Fixed-coupon bond, verified cash price and face value, regular coupons counted backward from maturity. No default, call, tax or reinvestment assumptions.'}
