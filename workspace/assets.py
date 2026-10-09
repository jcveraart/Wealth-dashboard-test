"""Asset-class tools from recorded evidence, without estimated missing transactions."""
import hashlib
from collections import defaultdict
from datetime import date,timedelta
from . import store,service,performance

def products():
    import receipts
    evidence=receipts.view();refunds=store.records('refund');groups=defaultdict(list);chains=[]
    for d in evidence['documents']:
        doc_refunds=[r for r in refunds if r['document_id']==d['id']]
        chains.append({'id':d['id'],'supplier':d.get('supplier'),'order_number':d.get('order_number'),'invoice_number':d.get('invoice_number'),'date':d.get('date'),'total':d.get('total'),'currency':d.get('currency'),'payments':d.get('links',[]),'refunds':doc_refunds,'source_id':d.get('source_id'),'items':d['items'],
         'fields':{k:'Present' if d.get(k) not in (None,'',[]) else 'Missing' for k in ('supplier','date','currency','total','invoice_number','source_id','items')},'reconciled':d.get('reconciled')})
        for i in d['items']:
            sku=str(i.get('sku') or '').strip()
            if not sku or not d.get('date') or not i.get('quantity') or i.get('unit_price') is None:continue
            groups[(str(d.get('supplier') or ''),sku,d.get('currency'))].append({'date':d['date'],'quantity':i['quantity'],'unit_price':i['unit_price'],'name':i['description'],'invoice_id':d['id'],'source_id':d.get('source_id')})
    series=[]
    for (supplier,sku,currency),rows in groups.items():
        rows.sort(key=lambda r:r['date']);prior=rows[-2]['unit_price'] if len(rows)>1 else None;last=rows[-1]['unit_price']
        series.append({'supplier':supplier,'sku':sku,'currency':currency,'name':rows[-1]['name'],'observations':rows,'latest_unit_price':last,'change_pct':round((last/prior-1)*100,2) if prior and prior>0 else None})
    return {'chains':chains,'unit_prices':series,'scope':'Exact supplier + SKU + currency matches only. Quantities, prices, bank links and refunds remain source evidence; similar descriptions are not silently merged.'}

def fund_overlap():
    st=service.state();funds=[p for p in st['positions'] if p.get('isin') and any(x in p.get('category','').lower() for x in ('etf','fund'))]
    disclosures=store.records('fundholding');versions=defaultdict(lambda:defaultdict(list))
    for r in disclosures:versions[r['fund_isin']][r['as_of']].append(r)
    latest={i:rows[max(rows)] for i,rows in versions.items()};underlying=defaultdict(lambda:{'value_eur':0,'funds':[]});coverage=[]
    total=sum(p['value'] for p in funds)
    for p in funds:
        rows=latest.get(p['isin'],[]);covered=sum(r['weight_pct'] for r in rows)
        coverage.append({'name':p['name'],'isin':p['isin'],'value_eur':p['value'],'covered_pct':round(covered,4),'as_of':rows[0]['as_of'] if rows else None,'versions':len(versions.get(p['isin'],{}))})
        for r in rows:
            key=r['instrument'].upper();out=underlying[key];out['instrument']=key;out['name']=r['name'];out['value_eur']+=p['value']*r['weight_pct']/100;out['funds'].append(p['name'])
    exposure=[{**r,'value_eur':round(r['value_eur'],2),'weight_of_selected_funds_pct':round(r['value_eur']/total*100,3) if total else None} for r in underlying.values()]
    overlap=[]
    for n,a in enumerate(funds):
        left={r['instrument'].upper():r['weight_pct'] for r in latest.get(a['isin'],[])}
        for b in funds[n+1:]:
            right={r['instrument'].upper():r['weight_pct'] for r in latest.get(b['isin'],[])}
            overlap.append({'first':a['name'],'second':b['name'],'disclosed_overlap_pct':round(sum(min(left[k],right[k]) for k in set(left)&set(right)),4),'first_covered_pct':sum(left.values()),'second_covered_pct':sum(right.values())})
    changes=[]
    for isin,versions_for in versions.items():
        dates=sorted(versions_for)
        if len(dates)<2:continue
        before={r['instrument'].upper():r for r in versions_for[dates[-2]]};after={r['instrument'].upper():r for r in versions_for[dates[-1]]}
        for ident in set(before)|set(after):
            old=before.get(ident);new=after.get(ident)
            # Missing from a partial disclosure is unknown, not a sale.
            changes.append({'fund_isin':isin,'name':(new or old)['name'],'from':dates[-2],'to':dates[-1],'previous_pct':old['weight_pct'] if old else None,'latest_pct':new['weight_pct'] if new else None,'change_pp':round(new['weight_pct']-old['weight_pct'],4) if new and old else None})
    return {'coverage':coverage,'exposure':sorted(exposure,key=lambda r:r['value_eur'],reverse=True),'overlap':overlap,'changes':changes,'scope':'Verified uploaded holdings only. Incomplete disclosure yields partial exposure and a lower bound for overlap; absent positions remain unknown. Current fund values are used for current exposure.'}

def parse_fund_csv(raw):
    import spending
    from ai import decode_text
    rows=spending.table_from_text(decode_text(raw))
    if not rows:return None
    names=[str(x).lower().strip() for x in rows[0]]
    if not {'fund_isin','instrument','name','weight_pct','as_of'}<=set(names):return None
    return [{**dict(zip(names,r)),'weight_pct':spending.parse_amount(dict(zip(names,r))['weight_pct'])} for r in rows[1:]]

def ingest_funds(rows,source_id):
    normalized=[];groups=defaultdict(float);identities=set()
    for r in rows:
        data={k:r.get(k) or '' for k in service.SCHEMAS['fundholding']};data['source_id']=source_id
        data['weight_pct']=store.finite(data['weight_pct'],.000001,100);data['as_of']=store.iso(data['as_of'])
        if any(not data[k] for k in ('fund_isin','instrument','name')):raise ValueError('Fund, instrument and name are required.')
        key=(data['fund_isin'],data['as_of']);groups[key]+=data['weight_pct']
        ident='|'.join((data['fund_isin'],data['as_of'],data['instrument']))
        if ident in identities:raise ValueError('Duplicate underlying holding in the same fund disclosure.')
        identities.add(ident);normalized.append((hashlib.sha256(ident.encode()).hexdigest()[:30],data))
    if any(total>100.005 for total in groups.values()):raise ValueError('Fund disclosure weights exceed 100%.')
    # All validation precedes writes; replace the affected dated disclosures only.
    with store.connect() as c:
        import json
        existing=[(r['id'],json.loads(r['payload'])) for r in c.execute("SELECT id,payload FROM records WHERE kind='fundholding'")]
        for ident,r in existing:
            if (r['fund_isin'],r['as_of']) in groups:
                c.execute("DELETE FROM records WHERE kind='fundholding' AND id=?",(ident,))
                c.execute('INSERT INTO audit(created,action,kind,record_id,before_json) VALUES(?,?,?,?,?)',(store.now(),'replace-disclosure','fundholding',ident,json.dumps(r)))
        for ident,r in normalized:
            raw=json.dumps(r,allow_nan=False);c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)',('fundholding',ident,raw,store.now()));c.execute('INSERT INTO audit(created,action,kind,record_id,after_json) VALUES(?,?,?,?,?)',(store.now(),'import-disclosure','fundholding',ident,raw))
    return {'rows':len(normalized),'disclosures':len(groups)}

def savings():
    c=service.cfg();points=store.records('ratepoint');out=[]
    for a in c.get('savings',[]):
        known=[r for r in points if r['account']==a['name']];known.sort(key=lambda r:r['date'])
        rate=a.get('rate_pct');principal=a['principal_eur']
        out.append({'name':a['name'],'principal_eur':principal,'rate_pct':rate,'snapshot_date':a['snapshot_date'],'maturity':a.get('maturity'),'history':known,'projected_year_interest_eur':round(principal*rate/100,2) if rate is not None else None})
    return {'accounts':out,'scope':'Interest uses the entered annual rate and principal, with simple daily accrual; variable rates can change. Historical rates are recorded prospectively or entered from source evidence.'}

def record_rates():
    for a in service.cfg().get('savings',[]):
        if a.get('rate_pct') is None:continue
        ident=hashlib.sha256((a['name']+'|'+str(a['rate_pct'])+'|'+a['snapshot_date']).encode()).hexdigest()[:30]
        if not store.record('ratepoint',ident):store.put('ratepoint',{'account':a['name'],'date':a['snapshot_date'],'rate_pct':a['rate_pct'],'source_id':'','note':'Rate entered in portfolio settings; recorded prospectively on '+date.today().isoformat()},ident)

def loan_schedule(principal,rate,monthly,lump=0):
    principal=store.finite(principal,0);rate=store.finite(rate,0,100);monthly=store.finite(monthly,0);lump=store.finite(lump,0,principal)
    balance=principal-lump;interest=0;curve=[{'month':0,'balance_eur':round(balance,2),'interest_eur':0}]
    if balance==0:return {'months':0,'interest_eur':0,'curve':curve}
    if monthly<=balance*rate/1200:return {'months':None,'interest_eur':None,'curve':curve,'reason':'The payment does not cover monthly interest.'}
    for m in range(1,1201):
        cost=balance*rate/1200;interest+=cost;balance=max(0,balance+cost-monthly);curve.append({'month':m,'balance_eur':round(balance,2),'interest_eur':round(interest,2)})
        if balance<.005:return {'months':m,'interest_eur':round(interest,2),'curve':curve,'scope':'Fixed-rate monthly repayment scenario, excluding lender-specific or income-based repayment rules.'}
    return {'months':None,'interest_eur':None,'curve':curve,'reason':'Repayment exceeds the supported 100-year horizon.'}

def benchmark(account,symbol,start=None,end=None):
    from intelligence import store as prices
    from intelligence.data import symbol as validate_symbol
    symbol=validate_symbol(symbol);r=service.get('performance',{'account':account,'from':start,'to':end});p=r['performance']
    if not p['complete'] or not p.get('start'):raise ValueError('Confirm account cash-flow coverage and record valuations first.')
    observations=prices.rows('SELECT * FROM prices WHERE symbol=? AND currency=? AND adjusted=1 ORDER BY date,retrieved_at',(symbol,'EUR'))
    values={v['date']:v['close'] for v in observations};dates=sorted(values)
    def price(stamp):
        valid=[d for d in dates if d<=stamp and (date.fromisoformat(stamp)-date.fromisoformat(d)).days<=4]
        if not valid or values[valid[-1]]<=0:raise ValueError('Verified adjusted EUR price is missing near '+stamp+'. Refresh the security first; no FX is assumed.')
        return values[valid[-1]]
    units=p['opening_eur']/price(p['start']);events=defaultdict(float)
    for f in r['flows']:
        if p['start']<f['date']<=p['end']:events[f['date']]+=f['amount_eur']
    curve=[]
    for stamp in sorted(set(v['date'] for v in r['valuations'])|set(events)):
        units+=events[stamp]/price(stamp)
        if units<0:raise ValueError('Withdrawals exhaust the hypothetical benchmark; comparison is unavailable.')
        curve.append({'date':stamp,'value_eur':round(units*price(stamp),2)})
    closing=curve[-1]['value_eur'];return {'symbol':symbol,'curve':curve,'benchmark_profit_eur':round(closing-p['opening_eur']-sum(events.values()),2),'account_profit_eur':p['profit_eur'],'difference_eur':round(p['closing_eur']-closing,2),'scope':'Identical dated EUR external cash flows, adjusted EUR price proxy, end-of-day convention. No fees, taxes or execution slippage in the hypothetical benchmark.'}
