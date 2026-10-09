"""Read-only local workflow tools. Public research never receives private records."""
from . import service,cashflow,store
SPECS={
 'get_cash_workspace':('Read cash accounts, recorded balances and rates, access/purpose, reserves, payment movements, paid-interest evidence and source-dated flexible savings offers. No money is moved.',{}),
 'get_flexible_savings_rates':('Read the cached public EUR flexible-savings catalogue, including Raisin, ABN and Trade Republic. Promotions and new-customer offers are separate; saved personal rates are not overwritten.',{}),
 'compare_cash_and_debt':('Calculate equal-budget keep-cash versus extra-repayment scenarios. Rates are explicit user/model assumptions from verified evidence. No records or real transactions are changed.',{k:{'type':'number'} for k in ('balance_eur','debt_rate_pct','monthly_payment_eur','lump_eur','extra_monthly_eur','cash_rate_pct','years')}),
 'get_product_price_history':('Read exact SKU purchase-price observations, invoice/payment chains and evidence-field checks. Missing products are never inferred.',{}),
 'get_disclosed_fund_exposure':('Read source-backed underlying fund disclosures, known overlap, coverage and dated weight changes.',{}),
 'search_local_records':('Search local payments, purchase evidence, document text, holdings, plans and conversations. Supports above € amounts and missing:invoice.',{'query':{'type':'string'}}),
 'get_cashflow_outlook':('Get backend-calculated scheduled cashflow, recurring patterns, spending changes and budgets. Forecast assumptions and missing balances remain explicit.',{'month':{'type':['string','null'],'description':'YYYY-MM, or null for current month'}}),
 'get_purchase_evidence':('Trace invoices, products, payment allocations and refunds. Evidence creates no extra bank expense.',{'query':{'type':['string','null']},'limit':{'type':['integer','null'],'minimum':1,'maximum':30}}),
 'get_financial_planning':('Read goals, reimbursements, policies, projects, property evidence and decision notes; planning entries are not added to net worth.',{}),
 'get_account_performance':('Calculate recorded investment-account TWR, MWR, cashflows, fees and FIFO. Missing flow coverage withholds adjusted returns.',{'account':{'type':'string','description':'Exact investment account name'}}),
 'get_review_queue':('Read unresolved imports, payment categories, unmatched invoices and due reviews.',{}),
 'get_annual_evidence':('Prepare annual evidence checklist and recorded cashflows without inventing tax data or filing a return.',{'year':{'type':'integer','minimum':2000,'maximum':2100}}),
 'get_public_research':('Query available public economic, identifiers, clinical-study, procurement, news and crypto sources. Supply only public company names or identifiers, never personal financial data.',{'source':{'type':'string','enum':['fred','fda','krakenhistory','afmshort','afminsider','bis','oecd','ecb','worldbank','eurostat','cbs','openfigi','gleif','gdelt','trials','usaspending','ted','kraken']},'term':{'type':['string','null']}}),
 'calculate_financial_stress':('Backend-only hypothetical wealth shock and expense-reserve calculation. Assumptions are chosen by the user and never applied to records.',{k:{'type':'number'} for k in ('equity_pct','bonds_pct','crypto_pct','income_loss_months','monthly_expense_eur')})
}

def definitions():return [{'name':k,'description':v[0],'inputSchema':{'type':'object','properties':v[1],'required':list(v[1]),'additionalProperties':False}} for k,v in SPECS.items()]

def call(name,args):
    if name not in SPECS or not isinstance(args,dict) or set(args)-set(SPECS[name][1]):raise ValueError('Invalid workflow tool arguments.')
    if name=='get_cash_workspace':
        import cash_workspace
        report=cash_workspace.report(service.state(),offline=__import__('app').OFFLINE)
        for account in report['accounts']:
            account['history']=account['history'][-12:]
            for key in ('recent_payments','month_in_eur','month_out_eur','payment_count','payment_link_status'):account.pop(key,None)
        report.pop('payment_accounts',None)
        return report
    if name=='get_flexible_savings_rates':
        import savings_rates
        return savings_rates.snapshot(offline=__import__('app').OFFLINE)
    if name=='compare_cash_and_debt':
        import cash_workspace
        result=cash_workspace.scenario(args);result['curve']=result['curve'][::12]+[result['curve'][-1]];return result
    if name=='search_local_records':return service.search(args.get('query',''),30)
    if name in ('get_product_price_history','get_disclosed_fund_exposure'):
        r=service.get('products' if name=='get_product_price_history' else 'funds',{})
        return {k:v[:25] if isinstance(v,list) else v for k,v in r.items()}
    if name=='get_cashflow_outlook':
        r=service.get('cashflow',{'month':args.get('month')});r['forecast']['curve']=r['forecast']['curve'][::7];r['forecast']['events']=r['forecast']['events'][:40];r['recurring']=r['recurring'][:25];r['analysis']['merchants']=r['analysis']['merchants'][:15];return r
    if name=='get_purchase_evidence':
        import receipts
        q=str(args.get('query') or '').lower();limit=int(args.get('limit') or 15)
        if not 1<=limit<=30:raise ValueError('Choose a page size from 1 to 30.')
        all_docs=receipts.view()['documents'];docs=[d for d in all_docs if q in (str(d.get('supplier') or '')+' '+str(d.get('invoice_number') or '')+' '+str(d.get('order_number') or '')+' '+' '.join(i.get('description','') for i in d['items'])).lower()]
        rows=[]
        for d in docs[:limit]:
            rows.append({k:d.get(k) for k in ('id','supplier','invoice_number','order_number','date','currency','total','items','links','source_id','reconciled')})
        return {'documents':rows,'total':len(docs),'refunds':[r for r in store.records('refund') if r['document_id'] in {d['id'] for d in docs[:limit]}],'scope':'Original evidence and existing bank payment links only. Invoice totals do not create a new expense.'}
    if name=='get_financial_planning':
        r=service.planning()
        for key in ('projects','goals','existing_goals','claims','policies','properties','decisions','notes','taxsnapshots'):r[key]=r[key][:30]
        for p in r['projects']:p.pop('payments',None)
        return r
    if name=='get_account_performance':
        r=service.get('performance',{'account':args.get('account')});r['events']=r['events'][:30];r['valuations']=r['valuations'][-40:];r['flows']=r['flows'][-30:];r['performance']['curve']=r['performance']['curve'][-30:]
        for l in r['lots']:l['lots']=l['lots'][:10]
        r['lots']=r['lots'][:25];return r
    if name=='get_review_queue':
        r=service.review();r['tasks']=r['tasks'][:30];return {k:r[k] for k in ('tasks','total','counts','scope')}
    if name=='get_annual_evidence':
        r=service.annual_pack(args.get('year'));r['ledger']=r['ledger'][:30];r['account_history']=r['account_history'][-30:];return r
    if name=='get_public_research':
        r=service.resources.query(args.get('source'),args.get('term') or '');r['rows']=r['rows'][:25];r['series']=r['series'][-30:];return r
    if name=='calculate_financial_stress':return service.action('stress',args)
