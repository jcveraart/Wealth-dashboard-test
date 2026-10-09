import hashlib
import json
import re
from collections import defaultdict
from datetime import date,datetime,timedelta
from . import store,cashflow,performance,documents,resources,backups

def field(label,kind='text',required=False,options=None):return {'label':label,'type':kind,'required':required,**({'options':options} if options else {})}
SCHEMAS={
 'ratepoint':{'account':field('Savings account',required=True),'date':field('Effective date','date',True),'rate_pct':field('Annual rate %','number',True),'source_id':field('Rate notice document ID'),'note':field('Notes','textarea')},
 'bill':{'name':field('Name',required=True),'amount_eur':field('Cash amount € (expense negative)','number',True),'due':field('Next due date','date',True),'frequency':field('Repeats','select',True,['once','weekly','biweekly','monthly','quarterly','yearly']),'account':field('Account'),'active':field('Active','checkbox'),'recurrence_id':field('Detected pattern ID')},
 'budget':{'name':field('Name',required=True),'category':field('Category','category'),'limit_eur':field('Limit €','number',True),'period':field('Period','select',True,['monthly','yearly']),'carryover':field('Carry unused monthly budget forward','checkbox'),'since':field('Carryover begins','date')},
 'goal':{'name':field('Goal',required=True),'target_eur':field('Target €','number',True),'saved_eur':field('Reserved so far €','number',True),'due':field('Target date','date',True),'account':field('Account or pot'),'note':field('Notes','textarea')},
 'claim':{'name':field('Reimbursement / money owed',required=True),'amount_eur':field('Expected €','number',True),'due':field('Expected date','date'),'status':field('Status','select',True,['open','received','cancelled']),'transaction_id':field('Original payment ID'),'received_transaction_id':field('Received payment ID'),'note':field('Notes','textarea')},
 'project':{'name':field('Trip or project',required=True),'budget_eur':field('Budget €','number'),'from':field('From','date'),'to':field('To','date'),'transaction_ids':field('Payment IDs, one per line','lines'),'note':field('Notes','textarea')},
 'policy':{'name':field('Insurance / warranty',required=True),'expiry':field('Expiry','date'),'renewal':field('Renewal date','date'),'monthly_eur':field('Monthly cost €','number'),'source_id':field('Evidence document ID'),'note':field('Coverage / notes','textarea')},
 'property':{'name':field('Property',required=True),'value_eur':field('Documented value €','number',True),'valued_at':field('Valuation date','date',True),'mortgage_eur':field('Mortgage balance €','number'),'source_id':field('Evidence document ID'),'note':field('Notes','textarea')},
 'decision':{'name':field('Decision',required=True),'symbol':field('Ticker'),'date':field('Decision date','date',True),'thesis':field('Why / expected developments','textarea'),'risk':field('What would change your mind','textarea'),'review_date':field('Review on','date'),'status':field('Status','select',True,['considering','bought','held','sold','reviewed'])},
 'prompt':{'name':field('Saved question',required=True),'text':field('Question','textarea',True),'context':field('Context','select',True,['investments','spending','planning','documents'])},
 'note':{'name':field('Title',required=True),'type':field('Type','select',True,['fact','assumption','question']),'text':field('Text','textarea',True),'source_id':field('Evidence document ID'),'symbol':field('Ticker')},
 'flow':{'account':field('Account',required=True),'date':field('Date','date',True),'amount_eur':field('External flow € (deposit positive)','number',True),'source_id':field('Evidence document ID'),'note':field('Notes','textarea')},
 'valuation':{'account':field('Account',required=True),'date':field('Date','date',True),'value_eur':field('Recorded value €','number',True),'source_id':field('Evidence document ID')},
 'coverage':{'account':field('Account',required=True),'from':field('Complete external flows from','date',True),'to':field('Complete external flows through','date',True),'confirmed':field('I have checked all external flows for this period','checkbox')},
 'refund':{'name':field('Refund / return',required=True),'document_id':field('Original invoice ID',required=True),'item_id':field('Product item ID'),'transaction_id':field('Bank refund payment ID',required=True),'amount_eur':field('Allocated refund €','number',True),'note':field('Notes','textarea')},
 'institution':{'name':field('Legal deposit institution',required=True),'accounts':field('Account names, one per line','lines',True),'limit_eur':field('Verified protection limit €','number'),'source_url':field('Official terms URL'),'verified_at':field('Checked on','date'),'note':field('Protection scheme / conditions','textarea')},
 'fundholding':{'fund_isin':field('Held fund ISIN',required=True),'instrument':field('Underlying ISIN or ticker',required=True),'name':field('Holding name',required=True),'weight_pct':field('Disclosed weight %','number',True),'sector':field('Sector'),'country':field('Country'),'currency':field('Currency'),'as_of':field('Holdings date','date',True),'source_id':field('Original holdings file ID',required=True)},
 'taxsnapshot':{'name':field('Snapshot name',required=True),'date':field('Evidence date','date',True),'year':field('Tax year','number',True),'source_id':field('Annual statement ID'),'note':field('Notes','textarea')},
 'feed':{'name':field('Research feed',required=True),'url':field('Public RSS / Atom URL',required=True),'symbol':field('Related ticker'),'enabled':field('Enabled','checkbox')},
 'rule':{'name':field('Document layout rule',required=True),'supplier':field('Supplier'),'pattern':field('Text to recognise',required=True),'mode':field('Import mode','select',True,['auto','receipts']),'note':field('Correction / instruction','textarea')},
}

def cfg():
    import app
    return app.load(app.CONFIG,{})

def state():
    import app
    return app.compute_state(cfg(),record=False,include_intelligence=False)

def spending_data():
    import spending
    with spending.lock:return spending.load()

def choices():
    import receipts
    st=state();data=spending_data();evidence=receipts.read()
    accounts=list(dict.fromkeys([a['name'] for a in st.get('accounts',[])]+[st['managed']['name']]+[a['name'] for a in st.get('savings',[])]+[a['name'] for a in st.get('debts',[])]))
    return {'accounts':accounts,'sources':[{'id':s['id'],'label':s['name']} for s in evidence['sources']],
      'invoices':[{'id':d['id'],'label':str(d.get('supplier') or 'Invoice')+' · '+str(d.get('date') or '')+' · '+str(d.get('total'))+' '+str(d.get('currency') or '')} for d in evidence['documents']],
      'products':[{'id':i['id'],'document_id':d['id'],'label':i.get('description') or 'Product'} for d in evidence['documents'] for i in d['items']],
      'payments':[{'id':t['id'],'amount':t['amount'],'label':t['date']+' · '+str(t.get('merchant') or t.get('description') or 'Payment')[:80]+' · €'+str(t['amount'])} for t in sorted(cashflow.payment_rows(data),key=lambda t:t['date'],reverse=True)[:5000]]}

def validate(kind,data,ident=None):
    if kind not in SCHEMAS:raise ValueError('Unsupported record type.')
    schema=SCHEMAS[kind];out={}
    if set(data)-set(schema)-{'id','updated'}:raise ValueError('Unexpected record fields.')
    for k,f in schema.items():
        value=data.get(k)
        if f['required'] and (value is None or value=='' or f['type']=='lines' and not value):raise ValueError(f['label']+' is required.')
        if f['type']=='number':value=store.finite(value,nullable=not f['required'])
        elif f['type']=='date':value=store.iso(value,nullable=not f['required'])
        elif f['type']=='checkbox':
            if not isinstance(value,(bool,type(None))):raise ValueError('Checkbox value must be true or false.')
            value=bool(value)
        elif f['type']=='lines':
            value=value.splitlines() if isinstance(value,str) else value or []
            if not isinstance(value,list) or len(value)>5000:raise ValueError('Too many entries.')
            value=list(dict.fromkeys(str(x).strip()[:200] for x in value if str(x).strip()))
        else:
            value=str(value or '').strip()[:20000 if f['type']=='textarea' else 500]
            if f['type']=='select' and value not in f['options']:raise ValueError('Choose an available '+f['label'].lower()+'.')
        out[k]=value
    for k in ('limit_eur','target_eur','saved_eur','value_eur','mortgage_eur','monthly_eur','budget_eur'):
        if out.get(k) is not None and out[k]<0:raise ValueError('This amount cannot be negative.')
    if out.get('from') and out.get('to') and out['from']>out['to']:raise ValueError('The end date must follow the start date.')
    if kind=='coverage' and not out['confirmed']:raise ValueError('Confirm completeness only after checking the evidence.')
    if kind=='fundholding':
        if not 0<out['weight_pct']<=100:raise ValueError('Fund weight must be above zero and at most 100%.')
        total=sum(r['weight_pct'] for r in store.records(kind) if r['fund_isin']==out['fund_isin'] and r['as_of']==out['as_of'] and r['id']!=ident)+out['weight_pct']
        if total>100.005:raise ValueError('Disclosed holdings exceed 100%; review the source weights.')
    if kind in ('project','claim','refund'):
        tx={t['id']:t for t in spending_data()['transactions']}
        for k in ('transaction_id','received_transaction_id'):
            if out.get(k) and out[k] not in tx:raise ValueError('Payment ID was not found.')
        if kind=='project' and any(i not in tx for i in out['transaction_ids']):raise ValueError('A project payment ID was not found.')
        if kind=='refund':
            import receipts
            doc=next((d for d in receipts.read()['documents'] if d['id']==out['document_id']),None)
            if not doc:raise ValueError('Original invoice was not found.')
            if out['item_id'] and not any(i['id']==out['item_id'] for i in doc['items']):raise ValueError('Product item was not found.')
            t=tx[out['transaction_id']]
            if t['amount']<=0 or out['amount_eur']<=0:raise ValueError('Choose an incoming bank refund and a positive allocation.')
            used=sum(r['amount_eur'] for r in store.records('refund') if r['transaction_id']==t['id'] and r['id']!=ident)
            if used+out['amount_eur']>t['amount']+.0049:raise ValueError('Refund allocations exceed the actual bank credit.')
    if kind=='feed':
        from .feeds import validate_url
        validate_url(out['url'])
    if kind=='taxsnapshot':out['year']=int(store.finite(out['year'],2000,2100))
    return out

def save_record(kind,data,ident=None):
    out=validate(kind,data,ident)
    if kind=='coverage':ident=out['account']
    if kind=='valuation':ident=out['account']+'|'+out['date']
    if kind=='taxsnapshot':
        out['snapshot']=state();out['created_at']=store.now()
    return store.put(kind,out,ident)

def review():
    import receipts,spending
    data=spending_data();tasks=[]
    for item in documents.intake():
        if item['status']=='ready':tasks.append({'id':'intake:'+item['id'],'kind':'intake','title':item['name'],'detail':item['kind']+' · '+str(item['rows'])+' detected records','target':item['id'],'priority':1})
    for doc in receipts.view()['documents']:
        if not doc.get('links'):tasks.append({'id':'receipt:'+doc['id'],'kind':'receipt','title':doc.get('supplier') or 'Unmatched invoice','detail':str(doc.get('total'))+' '+doc.get('currency','')+' · '+str(len(doc['candidates']))+' suggested payments','target':doc['id'],'priority':2})
        elif not doc.get('reconciled'):tasks.append({'id':'receipt-lines:'+doc['id'],'kind':'receipt','title':'Check product totals: '+str(doc.get('supplier') or 'invoice'),'detail':'Product lines do not reconcile with the document total.','target':doc['id'],'priority':2})
    pending=defaultdict(list)
    for t in cashflow.payment_rows(data):
        if not t.get('category'):pending[t.get('merchant') or t.get('description') or 'Uncategorised'].append(t)
    for name,rows in pending.items():tasks.append({'id':'category:'+hashlib.sha256(name.encode()).hexdigest()[:16],'kind':'payment','title':name,'detail':str(len(rows))+' payments need a category','target':rows[0]['id'],'priority':2,'transaction_ids':[t['id'] for t in rows]})
    today=date.today().isoformat()
    for kind,datekey in [('claim','due'),('policy','expiry'),('decision','review_date')]:
        for r in store.records(kind):
            due=r.get(datekey)
            if due and due<=(date.today()+timedelta(days=30)).isoformat() and r.get('status') not in ('received','cancelled','reviewed'):
                tasks.append({'id':kind+':'+r['id'],'kind':kind,'title':r['name'],'detail':datekey.replace('_',' ')+' '+due,'target':r['id'],'priority':1 if due<today else 3})
    try:
        from intelligence import service as investments
        for s in investments.alerts()['items']:
            if not s['seen']:tasks.append({'id':'signal:'+s['id'],'kind':'signal','title':s['title'],'detail':s['detail'],'target':s['id'],'symbol':s.get('symbol'),'priority':3})
    except Exception:pass
    dismissed=set(store.record('prefs','dismissed',{}).get('ids',[]));tasks=[t for t in tasks if t['id'] not in dismissed]
    counts=defaultdict(int)
    for t in tasks:counts[t['kind']]+=1
    return {'tasks':sorted(tasks,key=lambda t:(t['priority'],t['title']))[:1000],'total':len(tasks),'counts':dict(counts),'intake':documents.intake(),'folder':'import-inbox','scope':'Suggestions and unresolved evidence. Nothing here invents or duplicates financial transactions.'}

def summary():
    r=review();rec=cashflow.recurring(spending_data());events=store.rows('SELECT * FROM events WHERE seen=0 ORDER BY created DESC LIMIT 10')
    return {'review_count':r['total'],'review_counts':r['counts'],'upcoming':sorted([x for x in rec if x['active']],key=lambda r:r['next_date'])[:4],
      'events':[{**e,'payload':json.loads(e['payload'])} for e in events],'available_sources':len(resources.SOURCES),'version':'2026.10-workflows'}

def search(q='',limit=60):
    import receipts,extras,spending
    raw=str(q or '').strip()[:200];low=raw.lower();tokens=[];filters={}
    amount=re.search(r'(?:>|above\s+|over\s+)(?:€\s*)?(\d+(?:[.,]\d+)?)',low)
    if amount:filters['above']=float(amount.group(1).replace(',','.'));low=low[:amount.start()]+low[amount.end():]
    if 'missing:invoice' in low or 'without an invoice' in low or 'without invoice' in low:
        filters['missing_invoice']=True;low=re.sub(r'missing:invoice|without an invoice|without invoice','',low)
    for key in ('after','before','account','category','type'):
        match=re.search(r'\b'+key+r':(?:"([^"]+)"|([^\s]+))',low)
        if match:filters[key]=match.group(1) or match.group(2);low=low[:match.start()]+low[match.end():]
    for key in ('after','before'):
        if filters.get(key):filters[key]=store.iso(filters[key])
    low=re.sub(r'\b(purchases|payments|transactions|euros|euro)\b','',low).strip();tokens=low.split()
    matches=[];data=spending_data();docs=receipts.read();linked={l['transaction_id'] for d in docs['documents'] for l in d.get('links',[])}
    def add(kind,ident,title,text,extra=None):
        hay=(title+' '+text).lower()
        if all(t in hay for t in tokens):matches.append({'kind':kind,'id':ident,'title':title,'snippet':text[:220],**(extra or {})})
    for t in cashflow.payment_rows(data):
        if filters.get('type') not in (None,'payment','payments','transaction'):continue
        if filters.get('after') and t['date']<filters['after'] or filters.get('before') and t['date']>filters['before']:continue
        if filters.get('account') and filters['account'] not in (t.get('account','')+' '+data['accounts'].get(t.get('account'),{}).get('name','')).lower():continue
        if filters.get('category') and filters['category'] not in str(t.get('category') or '').lower():continue
        if filters.get('above') is not None and abs(t['amount'])<=filters['above']:continue
        if filters.get('missing_invoice') and (t['amount']>=0 or t['id'] in linked):continue
        add('payment',t['id'],t.get('merchant') or t.get('description') or 'Payment',t['date']+' · €'+str(t['amount'])+' · '+str(t.get('description') or '')+' · '+t.get('account',''))
    if not filters or set(filters)=={'type'}:
        for d in docs['documents']:
            add('receipt',d['id'],d.get('supplier') or 'Invoice',' '.join(str(d.get(k) or '') for k in ('invoice_number','order_number','date','total','currency'))+' '+' '.join(i.get('description','') for i in d['items']))
        for d in store.records('document'):
            text=d.get('text','');pos=text.lower().find(tokens[0]) if tokens else 0
            if all(t in (d['name']+' '+text).lower() for t in tokens):
                matches.append({'kind':'document','id':d['id'],'title':d['name'],'snippet':text[max(0,pos-70):max(0,pos-70)+220],'source_id':d['source_id']})
        for kind in SCHEMAS:
            if kind=='taxsnapshot':continue  # Tax UI is disabled; retain historical records.
            for r in store.records(kind):add(kind,r['id'],r.get('name') or r.get('account') or kind,' '.join(str(v) for k,v in r.items() if k not in ('snapshot','id','updated')))
        for chat in extras.read(extras.CHATS,[]):
            content=' '.join(str(m.get('content') or '') for m in chat.get('messages',[]));add('chat',chat['id'],chat.get('title') or 'Conversation',content)
        st=state()
        for p in st['positions']:add('holding',p.get('isin') or 'n:'+p['name'].lower(),p['name'],p['account']+' '+str(p.get('isin') or '')+' '+str(p.get('symbol') or ''))
        for kind in ('accounts','savings','debts'):
            for a in st.get(kind,[]):add('account',a['name'],a['name'],kind)
        import app
        notes=app.read_notes()
        if notes:add('notes-text','notes','Personal notes',notes,{'text':notes[:40000]})
        try:
            from intelligence import store as research
            for row in research.rows("SELECT entity,payload,url FROM observations WHERE kind='company' ORDER BY retrieved_at DESC LIMIT 100"):
                co=json.loads(row['payload'])
                for news in co.get('news',[]):
                    if str(news.get('url') or '').startswith(('http://','https://')):add('public-link',news['url'],news.get('title') or 'Company headline',row['entity']+' '+str(news.get('date') or ''),{'url':news['url']})
            for r in research.rows('SELECT accession,form,filed,cik,url FROM filings ORDER BY filed DESC LIMIT 500'):
                add('public-link',r['accession'],r['form']+' · '+r['cik'],r['filed']+' '+r['accession'],{'url':r['url']})
            for r in research.rows('SELECT symbol,name,note,thesis FROM watchlist'):add('research-company',r['symbol'],r['name'] or r['symbol'],r['symbol']+' '+str(r.get('note') or '')+' '+str(r.get('thesis') or ''))
        except Exception:pass
    if filters.get('type'):
        requested={'invoice':'receipt','payments':'payment','transaction':'payment','news':'public-link','filing':'public-link','company':'research-company'}.get(filters['type'],filters['type'])
        matches=[r for r in matches if r['kind']==requested]
    return {'items':matches[:limit],'total':len(matches),'filters':filters,'query':raw,'scope':'Local data only. Search terms are not transmitted to public research providers.'}

def planning():
    st=state();c=cfg();goals=[cashflow.goal_projection(r) for r in store.records('goal')];existing=[]
    for g in c.get('goals',[]):
        saved=g.get('saved_eur')
        if saved is None:saved=st.get('totals',{}).get({'net_worth':'net_worth','savings':'savings','investments':'investments'}.get(g.get('source'),'unknown'))
        if g.get('date') and saved is not None:existing.append(cashflow.goal_projection({'name':g['name'],'target_eur':g['target_eur'],'saved_eur':saved,'due':g['date'],'source':'Existing portfolio goal'}))
    return {'goals':goals,'existing_goals':existing,'claims':store.records('claim'),'policies':store.records('policy'),'properties':store.records('property'),'projects':project_report(),
      'decisions':store.records('decision'),'notes':store.records('note'),'taxsnapshots':[{k:v for k,v in r.items() if k!='snapshot'} for r in store.records('taxsnapshot')],
      'scope':'Planning records do not add assets to net worth or duplicate existing balances.'}

def project_report():
    import spending
    data=spending_data();tx={t['id']:t for t in cashflow.payment_rows(data)};out=[]
    for project in store.records('project'):
        rows=[tx[i] for i in project['transaction_ids'] if i in tx]
        cats={c['id']:c for c in data['categories']};parts=[p for t in rows for p in spending.parts(t) if cats.get(p.get('category'),{}).get('kind')!='transfer']
        expenses=sum(-p['amount'] for p in parts if p['amount']<0);incoming=sum(p['amount'] for p in parts if p['amount']>0)
        out.append({**project,'expenses_eur':round(expenses,2),'incoming_eur':round(incoming,2),'net_outflow_eur':round(expenses-incoming,2),'remaining_budget_eur':round(project['budget_eur']-expenses+incoming,2) if project.get('budget_eur') is not None else None,'payments':rows})
    return out

def coverage_report():
    import spending,receipts
    data=spending_data();groups=defaultdict(list)
    for t in cashflow.payment_rows(data):groups[t['account']].append(t)
    accounts=[]
    for aid,rows in groups.items():
        dates=sorted(t['date'] for t in rows);months=sorted(set(d[:7] for d in dates));gaps=[]
        if months:
            y,m=map(int,months[0].split('-'));end=months[-1]
            for _ in range(600):
                key=f'{y:04d}-{m:02d}'
                if key>end:break
                if key not in months:gaps.append(key)
                m+=1
                if m==13:y+=1;m=1
        accounts.append({'account':aid,'name':data['accounts'].get(aid,{}).get('name',aid),'from':dates[0],'to':dates[-1],'transactions':len(rows),'months':months,'months_without_records':gaps,
          'imports':[i for i in data.get('imports',[]) if i.get('account')==aid],'scope':'Months without transactions are gaps to check, not proof that a statement is missing. Opening/closing statement balances are needed for full reconciliation.'})
    return {'accounts':accounts,'documents':len(receipts.read()['documents']),'sources':len(receipts.read()['sources'])}

def connections():
    from intelligence import service as investments
    import app,providers,local
    s=app.load(app.SETTINGS,{});flags=investments.connection_status();cache=resources.history();latest={}
    for r in cache:latest.setdefault(r['source'],r)
    items=[{'id':k,'name':v[0],'supplies':v[1],'status':'Cached data available' if k in latest else 'Available to query','access':'Public endpoint; source limits apply','url':v[2],'last_retrieved':latest.get(k,{}).get('retrieved_at')} for k,v in resources.SOURCES.items()]
    items += [
      {'id':'sec','name':'SEC EDGAR','supplies':'Filings, company financials, 13F and Form 4','status':'Configured' if flags['sec_configured'] else 'Contact identification needed','access':'Public data','url':'https://www.sec.gov/search-filings/edgar-application-programming-interfaces'},
      {'id':'openbb','name':'OpenBB / Yahoo','supplies':'Market prices and supported company datasets','status':'Installed' if flags['openbb_installed'] else 'Yahoo adapter available','access':'Provider-dependent','url':'https://docs.openbb.co/'},
      {'id':'quiver','name':'Quiver','supplies':'Supported alternative datasets','status':'Configured' if flags['quiver_configured'] else 'API token / suitable subscription needed','access':'Optional paid data','url':'https://www.quiverquant.com/api-setup/'},
      {'id':'supabase','name':'Supabase','supplies':'Existing optional financial-data sync','status':'Configured' if s.get('supabase_url') and (s.get('supabase_key') or s.get('supabase_secret_key')) else 'Check existing cloud settings','access':'Your project','url':'https://supabase.com/'},
      {'id':'ollama','name':'Local AI','supplies':'Existing local categorisation and briefing tasks','status':'Available' if local.models() else 'Local model needed','access':'Local model; hardware-dependent','url':'https://ollama.com/'},
    ]
    for ident,name,supplies,url,access in [
      ('enablebanking','Enable Banking','Authorised bank transactions','https://enablebanking.com/docs/api/linked-accounts/','Bank authorisation and app registration needed'),
      ('tink','Tink','Bank aggregation','https://www.tink.com/account-aggregation/','Commercial onboarding and bank authorisation'),
      ('bunq','bunq','Direct bank account integration','https://doc.bunq.com/','Your account and API authorisation'),
      ('ibkr','Interactive Brokers','Flex reporting','https://www.interactivebrokers.com/docs/web-api/flex-web-service/client-portal-configuration/enable-and-create-access-token','Your account and Flex token'),
      ('gmail','Gmail','Invoice attachments','https://developers.google.com/workspace/gmail/api/','Separate dashboard OAuth connection'),
      ('outlook','Outlook','Invoice attachments and calendars','https://learn.microsoft.com/en-us/graph/','Separate dashboard OAuth connection'),
      ('eodhd','EODHD','Broader prices and fundamentals','https://eodhd.com/financial-apis/','API key and dataset-specific entitlement'),
      ('fmp','Financial Modeling Prep','Fundamentals, screening and transcripts','https://site.financialmodelingprep.com/developer/docs','API key and dataset-specific entitlement'),
      ('fred','FRED','Economic API series','https://fred.stlouisfed.org/docs/api/fred/','API key needed'),
      ('epo','EPO','Patent records','https://www.epo.org/en/searching-for-patents/data/web-services/ops','Registration and credentials'),
      ('eia','EIA','Energy statistics','https://www.eia.gov/opendata/','Free API key registration'),
      ('afm','AFM','Dutch insider and short-position registers','https://www.afm.nl/nl-nl/sector/registers','Public registers; automated dataset extraction needs a verified feed'),
      ('esef','European company reports','ESEF statutory financial reports','https://www.esma.europa.eu/issuer-disclosure/electronic-reporting','Issuer report acquisition / mapping needed'),
      ('bis','BIS','Credit, banking and property indicators','https://data.bis.org/','Public data; series-specific adapter pending'),
      ('oecd','OECD','International economic series','https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html','Public data; series-specific adapter pending'),
      ('paperless','Paperless-ngx','Local document archive','https://docs.paperless-ngx.com/','Your archive URL and authorisation'),
      ('tailscale','Private phone access','Authenticated private network access','https://tailscale.com/','Device setup and authenticated serving needed'),
    ]:
        if ident not in resources.SOURCES and ident!='afm':items.append({'id':ident,'name':name,'supplies':supplies,'status':'Not connected','access':access,'url':url})
    for item in items:
        health=store.record('source-status',item['id'])
        if health and not health['ok']:item.update(status='Last request unavailable',access=health.get('error','Provider did not respond'),last_retrieved=health['checked'])
    investment=investments.status();job=store.record('research-job','batch',{})
    if job:investment['jobs'].append({'name':'Selected companies','status':job['status'],'cursor':str(len(job.get('done',[])))+'/'+str(len(job.get('symbols',[]))),'finished_at':job.get('finished')})
    return {'items':items,'ai':providers.status(),'investment':investment,'scope':'Availability is distinct from connection. No new external account was created and no paid provider is activated automatically.'}

def document_view():
    import receipts
    return {'indexed':[{**r,'text':r.get('text','')[:15000]} for r in store.records('document')],'invoices':receipts.view()['documents'],'refunds':store.records('refund'),'layouts':store.records('rule'),'coverage':coverage_report()}

def research_overview():
    from intelligence import service as investments
    data=investments.opportunities();items=data['items'];groups=defaultdict(list)
    for r in items:
        co=store_record_company(r['symbol']);industry=co.get('profile',{}).get('industry') or co.get('info',{}).get('industry') or 'Unclassified';groups[industry].append(r['symbol'])
    return {'opportunities':items,'peers':dict(groups),'decisions':store.records('decision'),'notes':store.records('note'),'prompts':store.records('prompt'),'public_queries':resources.history(),'scope':'Held, watched and cached researched companies. A full-market provider/universe is not connected.'}

def store_record_company(symbol):
    from intelligence import store as investments
    r=investments.latest('company',symbol);return r['data'] if r else {}

def annual_pack(year):
    import receipts
    year=str(int(store.finite(year,2000,2100)));c=cfg();docs=receipts.read();ledger=performance.ledger()
    st=state();accounts=[a['name'] for a in st.get('accounts',[])]+[st.get('managed',{}).get('name','Managed portfolio')]+[a['name'] for a in st.get('savings',[])]+[a['name'] for a in st.get('debts',[])]
    evidence=store.records('document');checklist=[]
    for name in dict.fromkeys(accounts):
        matching=[{'id':d['id'],'name':d['name'],'source_id':d['source_id']} for d in evidence if year in d['name']+' '+d.get('text','') and name.lower() in (d['name']+' '+d.get('text','')).lower()]
        checklist.append({'account':name,'evidence_candidates':matching,'status':'Candidate documents to verify' if matching else 'No matching annual statement indexed'})
    return {'year':year,'generated':store.now(),'checklist':checklist,'yearly_flows':[r for r in c.get('yearly_flows',[]) if str(r['year'])==year],
      'account_history':[r for r in c.get('account_history',[]) if r['date'].startswith(year)],'ledger':[r for r in ledger if r['date'].startswith(year)],
      'snapshots':[{k:v for k,v in r.items() if k!='snapshot'} for r in store.records('taxsnapshot') if str(r['year'])==year],
      'scope':'Evidence preparation, not a submitted tax return. Candidate document matches require review; missing records are not estimated.'}

def digest():
    summary_data=summary();analysis=cashflow.spending_analysis(spending_data());rec=cashflow.recurring(spending_data())
    return {'generated':store.now(),'review':summary_data,'spending_changes':analysis['categories'][:5],
      'recurring_price_changes':[r for r in rec if r['active'] and abs(r['change_eur'])>.01],'upcoming':summary_data['upcoming'],
      'decisions_due':[r for r in store.records('decision') if r.get('review_date') and r['review_date']<=date.today().isoformat()],
      'scope':'Calculated locally from imported history and saved records. No email or public upload is performed.'}

def get(name,q):
    if name=='plans':
        from .plans import view
        return view(cfg())
    if name=='universe':
        from .research import universe
        return {**universe(q.get('q','')),'job':store.record('research-job','batch',{})}
    if name=='filing-text':
        from .research import filing_text
        return filing_text(q.get('accession'))
    if name=='filing-options':
        from intelligence import store as research
        return {'items':research.rows("SELECT accession,cik,form,filed,period,url FROM filings WHERE form NOT IN ('4','4/A','13F-HR','13F-HR/A') ORDER BY filed DESC LIMIT 300")}
    if name=='esef':return {'items':store.records('esef-facts')}
    if name in ('products','funds','savings'):
        from . import assets
        return {'products':assets.products,'funds':assets.fund_overlap,'savings':assets.savings}[name]()
    if name=='summary':return summary()
    if name=='review':return review()
    if name=='search':return search(q.get('q',''),min(100,max(1,int(q.get('limit',60)))))
    if name=='schemas':return {'schemas':SCHEMAS,'categories':spending_data()['categories']}
    if name=='choices':return choices()
    if name=='records':
        kind=q.get('kind','goal')
        if kind not in SCHEMAS:raise ValueError('Choose an available record type.')
        return {'kind':kind,'items':store.records(kind)}
    if name=='cashflow':
        d=spending_data();st=state();rec=cashflow.recurring(d);opening=store.record('prefs','cashflow',{}).get('opening_eur')
        return {'forecast':cashflow.forecast(d,st['savings'],store.records('bill'),recurrences=rec,starting=opening),
          'recurring':rec,'analysis':cashflow.spending_analysis(d,q.get('month'),store.records('budget')),'bills':store.records('bill'),'claims':store.records('claim'),'projects':project_report()}
    if name=='planning':return planning()
    if name=='documents':return document_view()
    if name=='connections':return connections()
    if name=='performance':
        st=state();accounts=[a['name'] for a in st['accounts']]+[st['managed']['name']];account=q.get('account') or accounts[0]
        if account not in accounts:raise ValueError('Choose an investment account.')
        return {'accounts':accounts,**performance.account_report(cfg(),st,account,q.get('from'),q.get('to'))}
    if name=='research':return research_overview()
    if name=='backups':return {'items':backups.listing(),'maintenance':store.record('prefs','maintenance',{}),'audit':store.rows('SELECT id,created,action,kind,record_id FROM audit ORDER BY id DESC LIMIT 50')}
    if name=='annual':return annual_pack(q.get('year',date.today().year-1))
    if name=='digest':return digest()
    if name=='events':return {'items':store.rows('SELECT id,type,title,created,seen FROM events ORDER BY created DESC LIMIT 100')}
    if name=='public':return {'items':resources.history(),'sources':resources.SOURCES}
    if name=='institutions':
        values={a['name']:a['value'] for a in state()['savings']};rows=[]
        for r in store.records('institution'):
            amount=sum(values.get(n,0) for n in r['accounts']);rows.append({**r,'total_eur':round(amount,2),'above_limit_eur':round(max(0,amount-r['limit_eur']),2) if r.get('limit_eur') is not None else None,'missing_accounts':[n for n in r['accounts'] if n not in values]})
        return {'items':rows,'scope':'Only user-verified legal institutions and protection terms; no assumed protection limit.'}
    raise ValueError('Unknown workflow endpoint.')

def action(name,body):
    if name in ('cloud-preview','source-updates'):
        from . import sync_review
        return sync_review.cloud_preview() if name=='cloud-preview' else sync_review.updates(True)
    if name=='chat-write':
        from .changes import commit
        return commit(body)
    if name=='research-batch':
        from .research import batch
        return batch(body.get('symbols'))
    if name=='loan':
        from .assets import loan_schedule
        return loan_schedule(body.get('principal_eur'),body.get('rate_pct'),body.get('monthly_eur'),body.get('lump_eur',0))
    if name=='benchmark':
        from .assets import benchmark
        return benchmark(body.get('account'),body.get('symbol'),body.get('from'),body.get('to'))
    if name=='record':
        kind=body.get('kind');ident=body.get('id')
        if kind not in SCHEMAS:raise ValueError('Choose an available record type.')
        if body.get('delete'):store.delete(kind,str(ident));return {'ok':True}
        return save_record(kind,body.get('data') or {},ident)
    if name=='scan':return documents.scan()
    if name=='intake':return documents.import_item(body.get('id'),body.get('provider'),body.get('mode','auto'))
    if name=='intake-dismiss':store.execute("UPDATE files SET status='dismissed' WHERE id=?",(str(body.get('id')),));return {'ok':True}
    if name=='dismiss':
        r=store.record('prefs','dismissed',{'ids':[]});r['ids']=list(dict.fromkeys(r['ids']+[str(body.get('id'))]))[-3000:];store.put('prefs',r,'dismissed');return {'ok':True}
    if name=='opening':
        value=store.finite(body.get('opening_eur'),nullable=True);return store.put('prefs',{'opening_eur':value},'cashflow')
    if name=='index':return {'indexed':documents.index_sources()}
    if name=='compare':return documents.comparison(body.get('first'),body.get('second'))
    if name=='public':return resources.query(body.get('source'),body.get('term',''),bool(body.get('force')))
    if name=='backup':return backups.create(body.get('password') or None)
    if name=='restore-preview':return backups.restore_preview(body.get('name'),body.get('password') or None)
    if name=='stress':
        assumptions={k:store.finite(body.get(k,d),-100 if 'pct' in k else 0,100 if 'pct' in k else 120 if k=='income_loss_months' else 1000000) for k,d in [('equity_pct',-20),('bonds_pct',-5),('crypto_pct',-40),('income_loss_months',3),('monthly_expense_eur',0)]}
        return cashflow.stress(state(),assumptions)
    if name=='bond':
        return performance.bond_metrics(store.finite(body.get('face_eur'),.01),store.finite(body.get('price_eur'),.01),store.finite(body.get('coupon_pct'),0,100),store.iso(body.get('maturity')),int(store.finite(body.get('frequency',1),1,4)),accrued=store.finite(body.get('accrued_eur',0),0),fee=store.finite(body.get('fee_eur',0),0))
    if name=='seen':
        for ident in body.get('ids',[])[:100]:store.execute('UPDATE events SET seen=1 WHERE id=?',(str(ident),))
        return {'ok':True}
    if name=='feed-refresh':
        from .feeds import refresh
        return refresh()
    raise ValueError('Unknown workflow action.')

def start():
    documents.start()
    from . import maintenance
    maintenance.start()
