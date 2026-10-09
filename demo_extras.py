"""Enrich newly generated fictional data using local SQLite only. No account/API lookup."""
from contextlib import closing
import csv,hashlib,json,math,sqlite3,time
from datetime import date,datetime,timedelta
from pathlib import Path
def enrich(root):
    root=Path(root);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    def write(n,value):
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    cfg=read('portfolio.json');today=date.fromisoformat(read('manifest.json')['anchor_date']);stamp=today.isoformat()+'T09:00:00+00:00';epoch=time.time()
    cfg['profile']['risk']='medium'
    for s in cfg['savings']:
        s.update(cash_role='spending' if s.get('kind')=='payment' else 'emergency' if 'Emergency' in s['name'] else 'unallocated',cash_access='instant' if s.get('kind')=='payment' else 'transfer',platform='Example savings platform' if not s.get('kind')=='payment' else '',withdrawal_days=0 if s.get('kind')=='payment' else 1)
    for a in cfg['accounts']:a.update(cash_rate_pct=0,cash_role='investing',cash_access='transfer',withdrawal_days=2)
    for debt in cfg['debts']:debt.update(repayment_regime='SF35' if 'Student' in debt['name'] else None,rate_fixed_until=(today+timedelta(days=700)).isoformat())
    plans=cfg['savings_plans'];plans.append({'account':cfg['accounts'][0]['name'],'instrument':'ASML','isin':'DEMO-ASML','amount_eur':25,'frequency':'weekly','active':True,'starts_on':today.isoformat(),'source':'manual','note':'Fictional plan for testing'})
    write('portfolio.json',cfg)
    offers=[]
    for i,(name,rate) in enumerate([('Example Flexible Bank',2.8),('Example Reserve Bank',2.6),('Example Local Savings',2.3),('Example Introductory Bank',3.5)]):
        offers.append({'id':'demo-bank-'+str(i),'provider':'Fictional marketplace','name':name,'legal_bank':name+' (fictional)','country':'Example country','currency':'EUR','rate_pct':rate,'effective_date':today.isoformat(),'variable':True,'promotional':i==3,'new_customers_only':i==3,'promo_months':3 if i==3 else None,'minimum_eur':1,'maximum_eur':100000,'access':'transfer','withdrawal':'Illustrative flexible account; not an actual offer.','payout':'Illustrative monthly payout','guarantee_limit_eur':100000,'guarantee_amount':100000,'guarantee_currency':'EUR','guarantee_scheme':'Fictional example only','source_url':'https://example.com','product_url':'https://example.com','retrieved_at':stamp,'retrieved_at_epoch':epoch,'source_key':'demo','_demo':True})
    write('cache/savings-rates.json',{'offers':offers,'at':epoch,'retrieved_at':stamp,'coverage':'Invented example rates only. Do not use these as real offers.','sources':[{'source':'demo','status':'fictional','products':len(offers)}],'_demo':True})
    from intelligence import store as research
    db=root/'cache/intelligence.sqlite3';db.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.executescript(research.SCHEMA)
        all_positions=[p for a in cfg['accounts'] for p in a['positions']]+cfg['managed']['positions']
        for p in all_positions:
            symbol=p['tickers'][0];h=read('cache/history/'+symbol+'.json');price=p['ref_price_eur'];name=p['name']
            info={'shortName':name,'longBusinessSummary':f'Fictional financial snapshot for {name}. This company profile is supplied only to demonstrate the research layout. Prices, ratios, statements and headlines are invented.','currency':'EUR','financialCurrency':'EUR','sector':p.get('sector','Diversified'),'industry':'Illustrative industry','country':p.get('region','Global'),'website':'https://example.com','regularMarketPrice':price,'trailingPE':22,'forwardPE':19,'marketCap':12000000000,'freeCashflow':480000000,'totalRevenue':2400000000,'revenueGrowth':.08,'earningsGrowth':.11,'profitMargins':.18,'operatingMargins':.22,'returnOnEquity':.17,'totalDebt':1400000000,'totalCash':1800000000,'fiftyTwoWeekHigh':price*1.15}
            income=[{'period':f'{today.year-k}-12-31','currency':'EUR','items':{'Total Revenue':2400000000*(1-.07*k),'Operating Income':480000000*(1-.06*k),'Net Income':360000000*(1-.05*k)}} for k in (1,2,3)]
            co={'info':info,'statements':{'income':income,'balance':[],'cashflow':[]},'news':[{'title':f'DEMO ONLY: {name} reports an illustrative quarter','source':'Fictional news example','url':'https://example.com','date':stamp}],'analyst_estimates':[],'lookthrough':[],'_demo':True};raw=json.dumps(co,sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest()
            conn.execute('INSERT OR REPLACE INTO observations(kind,entity,source,retrieved_at,period,currency,url,digest,payload) VALUES(?,?,?,?,?,?,?,?,?)',('company',symbol,'Fictional demo provider',stamp,'Example period','EUR','https://example.com',digest,raw))
            conn.executemany('INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?,?,?)',[(symbol,d,'Fictional demo provider',v,'EUR',1,stamp) for d,v in zip(h['dates'],h['close'])])
            path='cache/company-prices/'+hashlib.sha256(symbol.encode()).hexdigest()[:24]+'.json';write(path,{'symbol':symbol,'rows':[{'date':d,'close':v} for d,v in zip(h['dates'],h['close'])],'currency':'EUR','source':'Fictional daily-close series','adjusted':False,'at':epoch,'retrieved_at':stamp,'stale':False,'_demo':True})
        conn.execute('INSERT OR REPLACE INTO watchlist VALUES(?,?,?,?,?)',('ASML.AS','ASML','Fictional watchlist','Illustrative research thesis',today.isoformat()))
    from workspace import store
    with closing(sqlite3.connect(root/'cache/workspace.sqlite3')) as conn, conn:
        conn.executescript(store.SCHEMA)
        records=[('budget','demo-food',{'name':'Example groceries budget','category':'groceries','limit_eur':350,'period':'monthly','carryover':False,'since':today.isoformat()}),('goal','demo-travel',{'name':'Example holiday','saved_eur':1600,'target_eur':2500,'due':(today+timedelta(days=220)).isoformat(),'account':'Emergency Savings','note':'Fictional planning record'}),('decision','demo-thesis',{'name':'Example fund thesis','symbol':'IWDA.AS','date':today.isoformat(),'thesis':'Illustrative diversified long-term holding','risk':'Market drawdowns','review_date':(today+timedelta(days=120)).isoformat(),'status':'held'}),('bill','demo-rent',{'name':'Example rent','amount_eur':950,'due':(today+timedelta(days=20)).isoformat(),'frequency':'monthly','active':True,'category':'rent','account':'demo-checking'}),('policy','demo-warranty',{'name':'Example laptop warranty','expiry':(today+timedelta(days=200)).isoformat(),'note':'Fictional warranty','status':'active'})]
        for kind,ident,payload in records:conn.execute('INSERT OR REPLACE INTO records(kind,id,payload,updated) VALUES(?,?,?,?)',(kind,ident,json.dumps(payload),stamp))
    payment=read('spending.json');tid='demo-invoice-payment';payment['transactions'].append({'id':tid,'account':'demo-checking','date':today.isoformat(),'amount':-84,'description':'DEMO ONLY: Example invoice purchase','merchant':'Example Demo Shop','key':'exampledemoshop','category':'electronics','checked':True,'category_source':'user','country':'NL'})
    write('spending.json',payment)
    invoice=b'DEMO ONLY: Example invoice DEMO-INV-100\nExample keyboard EUR 54\nExample cable EUR 30\nTotal EUR 84\n';digest=hashlib.sha256(invoice).hexdigest();path=root/'attachments/receipts'/(digest+'.txt');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(invoice)
    attachment={'id':digest,'name':'demo-invoice.txt','path':str(path.relative_to(root)),'media_type':'text/plain','size':len(invoice)}
    write('receipts.json',{'version':1,'sources':[{**attachment,'kind':'receipt'}],'documents':[{'id':'demo-receipt','supplier':'Example Demo Shop','invoice_number':'DEMO-INV-100','order_number':'DEMO-ORDER-100','date':today.isoformat(),'currency':'EUR','total':84,'items':[{'id':'demo-keyboard','description':'Example keyboard','quantity':1,'unit_price':54,'total':54,'category':'electronics','sku':'DEMO-KEY'},{'id':'demo-cable','description':'Example cable','quantity':1,'unit_price':30,'total':30,'category':'electronics','sku':'DEMO-CABLE'}],'attachments':[attachment],'links':[{'transaction_id':tid,'amount_eur':84,'confirmed':True}],'reconciled':True,'uploaded':stamp}]})
    write('cache/briefing.json',{'date':today.isoformat(),'time':stamp,'by':'demo','version':'overview-v2','items':[{'text':'Saved demo example: compare the income/spending balance and the cash reserve before increasing regular investments.','link':{'kind':'page','page':'cash'}},{'text':'Saved demo example: your fictional portfolio combines funds, shares, bonds and crypto. Compare concentration in Investments.','link':{'kind':'page','page':'holdings'}}]})
    # Samples are deliberately marked and can be imported in the disconnected demo.
    example=root/'web/samples';example.mkdir(parents=True,exist_ok=True)
    (example/'demo-bank-transactions.csv').write_text('Date,Amount,Description,Counterparty,Account\n'+today.isoformat()+',-18.50,DEMO ONLY: Example bookstore,Example Bookstore,demo-checking\n'+today.isoformat()+',-9.95,DEMO ONLY: Example coffee,Example Coffee,demo-checking\n'+today.isoformat()+',4.25,DEMO ONLY: Example refund,Example Refund,demo-checking\n',encoding='utf-8')
    (example/'demo-invoice.txt').write_bytes(invoice)
    manifest=read('manifest.json');manifest.update(transactions=len(payment['transactions']),features=['investments','spending','cash','debt','plans','receipts','research','budgets','goals','saved demo briefing']);write('manifest.json',manifest)
