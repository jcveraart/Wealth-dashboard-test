"""Application-facing services; expensive ingestion never runs during page rendering."""
import json
import math
import os
import statistics
import threading
import time
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from . import analytics as a,store,sec
from .data import Yahoo,OpenBB,Quiver,config,symbol,market_prices,connection_status,clean
from . import normalize

_refresh_lock=threading.Lock();_started=False;_stop=threading.Event()
DEFAULT_RULES=[('concentration',20),('new_position',0),('investor_add',20),('consensus',2),('insider_buy',100000),
               ('cluster_buy',3),('insider_sell',1000000),('valuation',20),('price_drop',15),('filing',0),('earnings_change',20),('estimate_change',25),('news',0),('investor_exit',0)]

def initialize():
    if store.setting('initialized')==2:return
    with store.connect() as c:
        c.execute("INSERT OR IGNORE INTO managers VALUES('1067983','Berkshire Hathaway',1)")
        for typ,threshold in DEFAULT_RULES:c.execute('INSERT OR IGNORE INTO alert_rules VALUES(?,?,?, ?,1,?)',(typ,typ,'',threshold,'{}'))
    store.set_setting('initialized',2)

def state():
    import app
    cfg=app.load(app.CONFIG,None);s=app.compute_state(cfg,record=False,include_intelligence=False)
    tickers=app.load(app.TICKERS,{})
    originals={app.pid(p):p for p in app.all_priced_positions(cfg)}
    for p in s['positions']:
        orig=originals.get(app.pid(p),{});sym=tickers.get(app.pid(p)) or (orig.get('tickers') or [None])[0]
        if isinstance(sym,dict):sym=sym.get('symbol')
        p['symbol']=sym
    return s

def watchlist():
    import app
    cfg=app.load(app.CONFIG,{})
    existing={r['symbol']:r for r in store.rows('SELECT * FROM watchlist')}
    deleted=set(store.setting('removed_watchlist',[]))
    for r in cfg.get('watchlist',[]):
        try:s=symbol(r.get('symbol'))
        except ValueError:continue
        if s not in existing and s not in deleted:existing[s]={**r,'thesis':r.get('note','')}
    return list(existing.values())

def companies():
    out={}
    for r in store.rows("SELECT DISTINCT entity FROM observations WHERE kind='company'"):
        obs=store.latest('company',r['entity']);out[r['entity']]=obs['data']
    return out

def history(s):
    rows=store.rows('SELECT * FROM prices WHERE symbol=? ORDER BY date',(s,));out={}
    # The chosen market adapter writes one canonical series, preserving source per row.
    for r in rows:out[r['date']]=r['close']
    return out

def euro_series(s,currency):
    prices=history(s)
    if currency=='EUR':return prices
    cc='GBP' if currency=='GBp' else currency
    if not cc:return {}
    fx=history('EUR'+cc+'=X')
    if not fx:return {}
    fxdates=sorted(fx);out={};j=0
    for d in sorted(prices):
        while j+1<len(fxdates) and fxdates[j+1]<=d:j+=1
        fd=fxdates[j]
        if fd>d or (date.fromisoformat(d)-date.fromisoformat(fd)).days>5:continue
        if fx[fd]>0:out[d]=prices[d]/fx[fd]/(100 if currency=='GBp' else 1)
    return out

def analyze(account='',asset_class='all'):
    co=companies();s=state();series={}
    for p in s['positions']:
        sym=p.get('symbol')
        if sym:
            currency=co.get(sym,{}).get('info',{}).get('currency') or p.get('currency')
            series[sym]=euro_series(sym,currency)
    benchmark=config().get('intelligence_benchmark') or s.get('profile',{}).get('benchmark') or 'IWDA.AS'
    risk_free=float(config().get('intelligence_risk_free_pct',0))/100
    bench_rows=store.rows('SELECT currency FROM prices WHERE symbol=? ORDER BY date DESC LIMIT 1',(benchmark,))
    benchmark_series=euro_series(benchmark,bench_rows[0]['currency']) if bench_rows else {}
    out=a.portfolio(s,co,series,benchmark_series,risk_free,account,asset_class)
    out['benchmark']=benchmark;out['as_of']=store.now();out['source']='Local holdings + persisted market observations'
    out['data_status']=[{'symbol':p.get('symbol'),'name':p['name'],'company':store.latest('company',p['symbol'])['freshness'] if p.get('symbol') and store.latest('company',p['symbol']) else 'unavailable',
                         'price_source':p.get('source'),'price_time':p.get('price_time'),'historical_prices':len(series.get(p.get('symbol'),{}))} for p in s['positions']]
    return clean(out)

def insider_activity(s=''):
    query='SELECT payload FROM insider_trades';args=()
    if s:query+=' WHERE symbol=?';args=(symbol(s),)
    trades=[json.loads(r['payload']) for r in store.rows(query,args)]
    # An amended filing supersedes the original's same issuer/date/owner/code/quantity record.
    amended={(t['symbol'],t['insider'],t['date'],t['code'],t['shares']) for t in trades if next(iter(store.rows('SELECT form FROM filings WHERE accession=?',(t['accession'],))),{}).get('form')=='4/A'}
    trades=[t for t in trades if (t['symbol'],t['insider'],t['date'],t['code'],t['shares']) not in amended or next(iter(store.rows('SELECT form FROM filings WHERE accession=?',(t['accession'],))),{}).get('form')=='4/A']
    trades.sort(key=lambda t:t['date'],reverse=True);cut=(date.today()-timedelta(days=90)).isoformat()
    genuine=[t for t in trades if t['open_market'] and t['date']>=cut];buys=[t for t in genuine if t['code']=='P'];sells=[t for t in genuine if t['code']=='S']
    buyers=set(t['insider'] for t in buys);value=sum(t.get('value') or 0 for t in buys);score=a.clamp(len(buyers)*20+math.log10(1+value/10000)*20)
    groups=defaultdict(list)
    for t in buys:groups[t['symbol']].append(t)
    clusters=[{'symbol':sym,'buyers':len(set(t['insider'] for t in ts)),'value':sum(t.get('value') or 0 for t in ts),'transactions':len(ts)} for sym,ts in groups.items() if len(set(t['insider'] for t in ts))>=3]
    trend=defaultdict(lambda:{'buy_value_usd':0.,'sell_value_usd':0.,'purchases':0,'sales':0})
    relative=[]
    for t in genuine:
        r=trend[t['date'][:7]];r['buy_value_usd' if t['code']=='P' else 'sell_value_usd']+=t.get('value') or 0;r['purchases' if t['code']=='P' else 'sales']+=1
    for sym,ts in groups.items():
        co=store.latest('company',sym);f=a.fundamentals(co['data']) if co else {};cap=f.get('market_cap');currency=f.get('currency')
        capusd=cap if currency=='USD' else None
        usd=history('EURUSD=X');fx=history('EUR'+str(currency)+'=X')
        if cap and usd and currency=='EUR':capusd=cap*usd[max(usd)]
        elif cap and usd and fx and currency!='GBp':
            common=sorted(set(usd)&set(fx))
            if common and fx[common[-1]]:capusd=cap*usd[common[-1]]/fx[common[-1]]
        bought=sum(t.get('value') or 0 for t in ts)
        relative.append({'symbol':sym,'buy_value_usd':bought,'market_cap_usd':capusd,'buy_to_market_cap_pct':bought/capusd*100 if capusd and capusd>0 else None,
                         'basis':'Latest recorded market cap and FX versus trailing 90-day purchases; not ownership growth.'})
    return {'trades':trades,'summary':{'buyers':len(buyers),'buy_value_usd':value,'sell_value_usd':sum(t.get('value') or 0 for t in sells),
      'score':score if trades else None,'clusters':clusters,'repeated_buyers':[{'insider':n,'purchases':sum(t['insider']==n for t in buys)} for n in buyers if sum(t['insider']==n for t in buys)>1]},
      'coverage':'Ingested issuer filings only, last 180 days, up to 60 filings per company per refresh. P/S codes without a disclosed plan; discretion cannot be proven from absence of plan disclosure.',
      'trend':[{'month':k,**v} for k,v in sorted(trend.items())],'relative_size':relative,
      'amendment_caveat':'Exact matched amended transactions replace originals; corrected identities/quantities may require manual review.'}

def investors(cik=None):
    initialize();managers=store.rows('SELECT * FROM managers ORDER BY name');out=[];consensus=defaultdict(lambda:{'owners':[],'adding':[],'reducing':[],'weight_sum':0.,'name':''})
    for m in managers:
        hist=sec.manager_history(m['cik']);latest=hist[0] if hist else None
        out.append({**m,'history':hist if cik==m['cik'] else [{'period':h['period'],'filed':h['filed'],'accession':h['accession']} for h in hist],
                    'latest':latest,'status':'available' if latest else 'Awaiting SEC refresh'})
        if not m['enabled'] or not latest:continue
        moves={r['security']:r for r in latest['changes']}
        for h in latest['holdings']:
            if h['option_type'] or h['share_type']!='SH':continue
            r=consensus[h['cusip']];r['name']=h['name'];r['owners'].append(m['name']);r['weight_sum']+=h['weight_pct'] or 0
            move=moves.get(h['security'],{}).get('move')
            if move in ('new','added'):r['adding'].append(m['name'])
            if move=='reduced':r['reducing'].append(m['name'])
    return {'managers':out,'consensus':[{'cusip':k,**v,'owner_count':len(v['owners']),'average_weight_pct':v['weight_sum']/len(v['owners'])} for k,v in sorted(consensus.items(),key=lambda x:(-len(x[1]['owners']),-x[1]['weight_sum']))],
            'disclosure':'13F holdings are quarter-end disclosures, normally filed up to 45 days later. They omit shorts and many assets; share changes are not proof of trades or conviction.'}

def ownership(s,company):
    # Join by an exact configured or provider CUSIP only. Never fuzzy-match issuer names.
    cusip=company.get('info',{}).get('cusip') or store.setting('cusip_map',{}).get(s)
    if not cusip:
        matches=[p.get('isin') for p in state()['positions'] if p.get('symbol')==s]
        cusip=next((isin[2:11] for isin in matches if isinstance(isin,str) and len(isin)==12 and isin.startswith(('US','CA'))),None)
    if not cusip:return {'score':None,'coverage':'No verified CUSIP mapping. Add the company CUSIP in Research to join institutional filings.'}
    r=next((r for r in investors()['consensus'] if r['cusip']==cusip),None)
    available=[m for m in investors()['managers'] if m['enabled'] and m['latest']]
    enabled=[m for m in investors()['managers'] if m['enabled']]
    if not r:return {'score':0 if available and len(available)==len(enabled) else None,'cusip':cusip,'owners':[],
                     'coverage':'Not present in complete ingested enabled-manager portfolios.' if available and len(available)==len(enabled) else 'Institutional filing coverage is incomplete.'}
    return {**r,'score':a.clamp(len(r['owners'])*15+len(r['adding'])*10-len(r['reducing'])*10),'coverage':'Latest available disclosed quarters; check manager dates.'}

def estimate_revision(co):
    values=[]
    for r in co.get('estimate_changes',[]):
        up=a.number(r.get('upLast30days'));down=a.number(r.get('downLast30days'))
        if up is not None and down is not None and up+down>0:values.append((up-down)/(up+down))
    return statistics.mean(values) if values else None

def opportunity(s,analysis=None):
    s=symbol(s);obs=store.latest('company',s)
    if not obs:return {'symbol':s,'status':'unavailable','score':{'overall':None,'coverage_pct':0,'components':[]},'reason':'Refresh this company to retrieve public data.'}
    co=obs['data'];f=a.fundamentals(co);analysis=analysis or analyze();fit=portfolio_fit(s,co,analysis);own=ownership(s,co);inside=insider_activity(s)
    vals=[a.fundamentals(x['data']).get('trailing_pe') for x in store.history('company',s)]
    vals=[v for v in vals if v and v>0]
    f['valuation_vs_recorded_median']=f['trailing_pe']/statistics.median(vals)-1 if len(vals)>=2 and f.get('trailing_pe') else None
    score=a.score(f,fit['score'],own.get('score'),inside['summary']['score'],estimate_revision(co))
    previous=store.history('company',s,limit=2);change={}
    if len(previous)>1:
        old=a.fundamentals(previous[1]['data'])
        for key in ('price','trailing_pe','revenue_growth','earnings_growth','profit_margin'):
            if f.get(key) is not None and old.get(key) is not None:change[key]={'before':old[key],'now':f[key],'difference':f[key]-old[key]}
        nowrev=estimate_revision(co);prevrev=estimate_revision(previous[1]['data'])
        if nowrev is not None and prevrev is not None:change['estimate_revision_balance']={'before':prevrev,'now':nowrev,'difference':nowrev-prevrev}
    flags=[]
    if f.get('drawdown_52w') is not None and f['drawdown_52w']<-.2 and f.get('revenue_growth') is not None:
        flags.append('Price dislocation with positive reported revenue growth' if f['revenue_growth']>=0 else 'Price weakness and declining reported revenue')
    if f.get('earnings_growth') is not None and f['earnings_growth']<-.2:flags.append('Earnings deterioration')
    if own.get('adding'):flags.append('Tracked manager additions (delayed)')
    if inside['summary']['buyers']:flags.append('Open-market insider purchases')
    if fit['hhi_after']<fit['hhi_before']:flags.append('Improves modeled security diversification')
    info=co.get('info',{})
    return clean({'symbol':s,'name':info.get('shortName',s),'status':obs['freshness'],'metadata':{k:v for k,v in obs.items() if k!='data'},'fundamentals':f,
      'score':score,'portfolio_fit':fit,'smart_money':own,'insiders':inside['summary'],'changes':change,'signals':flags,'sparkline':list(history(s).values())[-60:]})

def opportunities():
    analysis=analyze();co=companies();held={p.get('symbol') for p in analysis['positions'] if p.get('symbol')};watched={r['symbol'] for r in watchlist()}
    rows=[]
    for s in sorted(set(co)|held|watched):
        r=opportunity(s,analysis);r['held']=s in held;r['watched']=s in watched;rows.append(r)
    rows.sort(key=lambda r:-(r['score'].get('overall') if r['score'].get('overall') is not None else -1))
    return {'items':rows,'portfolio_warnings':analysis['warnings'],'coverage':'Held, watched and researched companies; not a whole-market screener. Scores are explainable screening rules.'}

def portfolio_fit(s,co,analysis=None):
    analysis=analysis or analyze();out=a.fit(analysis,co,s)
    out.update({'correlation_to_portfolio':None,'modeled_volatility_before_pct':None,'modeled_volatility_after_pct':None,
                'risk_model_scope':'Optional 5% blend with the covered current-holdings model; historical illustration, not predicted risk. Requires at least 90% coverage and 60 aligned returns.'})
    if analysis['risk']['coverage_pct']<90:return out
    prices=euro_series(s,co.get('info',{}).get('currency'));cr=a.returns(prices);pr={}
    previous=100.
    for row in analysis['curve']:pr[row['date']]=row['value']/previous-1;previous=row['value']
    dates=sorted(set(pr)&set(cr))
    if len(dates)<60:return out
    old=[pr[d] for d in dates];candidate=[cr[d] for d in dates];combined=[x*.95+y*.05 for x,y in zip(old,candidate)]
    out.update({'correlation_to_portfolio':a.correlation(old,candidate),'modeled_volatility_before_pct':math.sqrt(a.cov(old,old)*252)*100,
                'modeled_volatility_after_pct':math.sqrt(a.cov(combined,combined)*252)*100})
    return out

def research(s):
    s=symbol(s);r=opportunity(s);obs=store.latest('company',s)
    if not obs:return r
    co=obs['data'];info=co.get('info',{});edgar=store.latest('sec_company',s,days=2)
    r.update({'overview':info.get('longBusinessSummary'),'industry':info.get('industry'),'website':info.get('website'),
       'management':info.get('companyOfficers',[]),'statements':co.get('statements',{}),'analyst_estimates':co.get('analyst_estimates',[]),
       'estimate_changes':co.get('estimate_changes',[]),'institutional_ownership':co.get('institutional_ownership',[]),
       'news':co.get('news',[]),'lookthrough':co.get('lookthrough',[]),'sec':edgar,'filings':edgar['data'].get('filings',[]) if edgar else [],
       'insider_activity':insider_activity(s),'valuation_history':[{'retrieved_at':x['retrieved_at'],'period':x.get('period'),**{k:v for k,v in a.fundamentals(x['data']).items() if k in ('price','trailing_pe','forward_pe','fcf_yield')}} for x in store.history('company',s)],
       'openbb':store.latest('openbb',s),'sec_statements':store.latest('sec_statements',s),'alternative':{k:store.latest('quiver_'+k,s) for k in Quiver.routes},
       'thesis':store.setting('thesis:'+s,{'notes':'','cases':[]}),
       'unavailable':['Competitive moat, competitors, catalysts, risk cases and thesis changes require source-grounded research; they are not inferred from a ticker.',
                      'Historical valuation is captured prospectively from real snapshots. No synthetic backfill. Revenue segments/geography require supported OpenBB datasets or company filings.']})
    import company_notes
    r['briefing']=company_notes.peek(r)
    return clean(r)

def persist_prices(s,currency):
    rows=store.rows('SELECT MAX(date) AS last FROM prices WHERE symbol=?',(s,));last=rows[0]['last']
    start=(date.fromisoformat(last)-timedelta(days=7)).isoformat() if last else (date.today()-timedelta(days=365*3)).isoformat()
    data,source=market_prices(s,start)
    # Re-fetch all adjusted history if a new split/dividend changes historical adjustment factors.
    if last and any(float(r.get('split') or r.get('stock_splits') or 0)!=0 or float(r.get('dividend') or 0)!=0 for r in data):
        data,source=market_prices(s,(date.today()-timedelta(days=365*3)).isoformat())
    with store.connect() as c:
        for r in data:
            close=a.number(r.get('close') or r.get('adj_close'));dt=str(r.get('date',''))[:10]
            if close is None or close<=0:continue
            date.fromisoformat(dt)
            c.execute('DELETE FROM prices WHERE symbol=? AND date=?',(s,dt))
            c.execute('INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?,?,?)',(s,dt,source,close,currency,1,store.now()))
    store.observe('corporate_actions',s,[r for r in data if r.get('dividend') or r.get('split')],source,currency=currency)

def refresh_company(s,force=False):
    obs=store.latest('company',s,days=.25)
    if not force and obs and obs['freshness']=='current':return
    co=Yahoo().company(s);f=a.fundamentals(co)
    errors=[]
    try:persist_prices(s,f['currency'])
    except Exception as e:errors.append('Price history: '+str(e))
    cc='GBP' if f['currency']=='GBp' else f['currency']
    if cc and cc!='EUR':
        try:persist_prices('EUR'+cc+'=X',cc)
        except Exception as e:errors.append('Historical FX: '+str(e))
    try:
        previous=store.latest('sec_company',s,days=1)
        if force or not previous or previous['freshness']=='stale':
            out=sec.company(s);store.observe('sec_company',s,out,'SEC EDGAR',filing_date=out.get('filings',[{}])[0].get('filingDate') if out.get('filings') else None);errors.extend(out.get('errors',[]))
        facts=store.latest('sec_facts',s)
        if facts:
            annual=normalize.sec_statements(facts['data'],f['financial_currency'])
            store.observe('sec_statements',s,annual,'SEC EDGAR',facts.get('url'),currency=f['financial_currency'])
            for kind,rows in annual.items():
                if not co['statements'].get(kind):co['statements'][kind]=rows
    except Exception as e:errors.append(str(e))
    if OpenBB().available() and config().get('openbb_enabled',True):
        try:
            datasets=OpenBB().company(s);store.observe('openbb',s,datasets,'OpenBB',currency=f['currency'])
            for kind,rows in normalize.openbb_statements(datasets,f['financial_currency']).items():
                if not co['statements'].get(kind):co['statements'][kind]=rows
        except Exception:errors.append('OpenBB datasets are unavailable; Yahoo and SEC continue to work.')
    if Quiver().key():
        for k in Quiver.routes:
            try:
                payload,url=Quiver().fetch(s,k);store.observe('quiver_'+k,s,payload,Quiver.name,url)
            except Exception as e:errors.append(f'Quiver {k}: {e}')
    store.observe('provider_errors',s,errors,'Ingestion')
    f=a.fundamentals(co)
    store.observe('company',s,co,Yahoo.name,'https://finance.yahoo.com/quote/'+s,period=f['period'],currency=f['currency'])

def rules():
    initialize();return store.rows('SELECT * FROM alert_rules')

def evaluate_signals():
    enabled={r['type']:r for r in rules() if r['enabled'] and not r['symbol']};custom=[r for r in rules() if r['enabled'] and r['symbol']]
    analysis=analyze();opps=opportunities()['items']
    aliases={}
    for r in opps:
        co=store.latest('company',r['symbol']);cusip=(co or {}).get('data',{}).get('info',{}).get('cusip') or store.setting('cusip_map',{}).get(r['symbol'])
        if cusip:aliases[cusip]=r['symbol']
    for p in analysis['positions']:
        isin=p.get('isin') or ''
        if len(isin)==12 and isin.startswith(('US','CA')) and p.get('symbol'):aliases[isin[2:11]]=p['symbol']
    def emit(typ,s,title,detail,evidence,value=0):
        s=aliases.get(s,s)
        matched=[r for r in custom if r['type']==typ and r['symbol']==s] or ([enabled[typ]] if typ in enabled else [])
        if any(value>=r['threshold'] for r in matched):store.signal(typ,s,title,detail,evidence)
    combined={}
    for p in analysis['positions']:
        key=p.get('symbol') or p['name'];combined[key]=combined.get(key,0)+p['weight_pct']
    for key,weight in combined.items():
        emit('concentration',key,'Portfolio concentration',f"{key} is {weight:.1f}% of selected investments across accounts.",{'name':key,'above':int(weight//5)*5},weight)
    for r in opps:
        s=r['symbol'];f=r.get('fundamentals',{});changes=r.get('changes',{})
        if f.get('drawdown_52w') is not None and f.get('revenue_growth') is not None and f['revenue_growth']>=0:
            emit('price_drop',s,'Price below recent high','Price drawdown with nonnegative reported revenue growth; investigate before acting.',{'date':date.today().isoformat(),'drawdown_bucket':int(-f['drawdown_52w']*100//5)*5},-f['drawdown_52w']*100)
        for rule in [x for x in custom if x['symbol']==s and x['type']=='valuation'] or ([enabled['valuation']] if 'valuation' in enabled else []):
            key='valuation-state:'+rule['id']+':'+s;previous=store.setting(key,{'active':False,'episode':0})
            if f.get('trailing_pe') is not None:
                active=0<f['trailing_pe']<=rule['threshold'];episode=previous['episode']+(1 if active and not previous['active'] else 0)
                if active and not previous['active']:store.signal('valuation',s,'Valuation threshold crossed',f"Trailing P/E {f['trailing_pe']:.1f}× is at or below {rule['threshold']}×.",{'threshold':rule['threshold'],'episode':episode})
                store.set_setting(key,{'active':active,'episode':episode})
        if changes.get('earnings_growth'):
            value=abs(changes['earnings_growth']['difference'])*100;emit('earnings_change',s,'Reported earnings growth changed','Review the earnings release and your thesis.',{'after':f.get('earnings_growth'),'period':f.get('period')},value)
        if changes.get('estimate_revision_balance'):
            change=changes['estimate_revision_balance'];emit('estimate_change',s,'Analyst revision balance changed','Review revised estimates and the latest guidance.',{'after':change['now']},abs(change['difference'])*100)
        co=store.latest('company',s)
        for n in (co or {}).get('data',{}).get('news',[])[:5]:
            # News is a review prompt, not a claim of materiality or a thesis verdict.
            emit('news',s,'Company headline to review',n.get('title') or 'Company news',{'url':n['url'],'published':n.get('date')})
        for t in insider_activity(s)['trades']:
            if not t['open_market']:continue
            emit('insider_buy' if t['code']=='P' else 'insider_sell',s,'Open-market insider '+('purchase' if t['code']=='P' else 'sale'),
                 f"{t['insider']} · {t['role']} · {t.get('value') or 0:,.0f} USD",{'id':t['id'],'url':t['url']},t.get('value') or 0)
        for c in insider_activity(s)['summary']['clusters']:emit('cluster_buy',s,'Clustered insider purchases',f"{c['buyers']} distinct buyers in 90 days.",{'date':date.today().isoformat(),'buyers':c['buyers']},c['buyers'])
        edgar=store.latest('sec_company',s)
        for frow in (edgar or {}).get('data',{}).get('filings',[])[:10]:
            if frow['form'] in ('8-K','6-K','10-Q','10-K','20-F'):emit('filing',s,'New company filing',f"{frow['form']} · {frow['filingDate']}",{'accession':frow['accessionNumber'],'url':frow['url']})
    data=investors()
    for m in data['managers']:
        for move in (m.get('latest') or {}).get('changes',[]):
            if move['move']=='new':emit('new_position',move['cusip'],'Tracked investor disclosed a new position',m['name']+' · '+move['name'],{'accession':m['latest']['accession'],'security':move['security']})
            elif move['move']=='added':emit('investor_add',move['cusip'],'Tracked investor increased disclosed shares',m['name']+' · '+move['name'],{'accession':m['latest']['accession'],'security':move['security']},move.get('change_pct') or 0)
            elif move['move']=='exit':emit('investor_exit',move['cusip'],'Tracked investor no longer discloses a position',m['name']+' · '+move['name'],{'accession':m['latest']['accession'],'security':move['security']})
    for c in data['consensus']:
        emit('consensus',c['cusip'],'Tracked investors adding the same company',c['name']+' · '+', '.join(c['adding']),{'owners':c['adding'],'date':date.today().isoformat()},len(c['adding']))

def refresh(symbols=None,force=False):
    initialize()
    if not _refresh_lock.acquire(False):return {'running':True,'message':'An update is already running.'}
    def run():
        errors=[];started=store.now()
        try:
            store.execute("INSERT OR REPLACE INTO jobs VALUES('ingestion',?,NULL,'running',NULL,NULL)",(started,))
            if symbols:target=list(dict.fromkeys(symbol(s) for s in symbols))[:50]
            else:
                target=list(dict.fromkeys([p['symbol'] for p in state()['positions'] if p.get('symbol')]+[r['symbol'] for r in watchlist()]+[r['entity'] for r in store.rows("SELECT DISTINCT entity FROM observations WHERE kind='company'")]))[:100]
            for s in target:
                store.execute("UPDATE jobs SET cursor=? WHERE name='ingestion'",(s,))
                try:refresh_company(s,force)
                except Exception as e:errors.append(s+': '+str(e))
            bench=config().get('intelligence_benchmark') or state().get('profile',{}).get('benchmark') or 'IWDA.AS'
            try:
                bench=symbol(bench);bi=companies().get(bench)
                if not bi:bi=Yahoo().company(bench)
                currency=bi.get('info',{}).get('currency')
                if not currency:raise ValueError('Benchmark quote currency unavailable.')
                persist_prices(bench,currency)
                if currency!='EUR':persist_prices('EUR'+('GBP' if currency=='GBp' else currency)+'=X',currency)
            except Exception as e:errors.append('Benchmark: '+str(e))
            if not symbols:
                for m in store.rows('SELECT * FROM managers WHERE enabled=1'):
                    try:
                        job=store.latest('manager_refresh',m['cik'],days=1)
                        if force or not job or job['freshness']=='stale':
                            r=sec.manager(m['cik']);errors.extend(r['errors']);store.observe('manager_refresh',m['cik'],r,'SEC EDGAR')
                    except Exception as e:errors.append(m['name']+': '+str(e))
            evaluate_signals()
        except Exception as e:errors.append(str(e))
        finally:
            store.execute("UPDATE jobs SET finished_at=?,status=?,error=?,cursor=NULL WHERE name='ingestion'",(store.now(),'partial' if errors else 'complete',json.dumps(errors)))
            _refresh_lock.release()
    threading.Thread(target=run,name='investment-ingestion',daemon=True).start()
    return {'running':True,'message':'Updating public investment data in the background.'}

def start(offline=False):
    global _started
    if _started:return
    initialize();_started=True
    store.execute("UPDATE jobs SET status='interrupted',error='Application restarted during ingestion.' WHERE status='running'")
    if offline:return
    def loop():
        if _stop.wait(15):return
        while not _stop.is_set():
            job=next(iter(store.rows("SELECT * FROM jobs WHERE name='ingestion'")),{})
            due=not job.get('finished_at') or (datetime.now(timezone.utc)-datetime.fromisoformat(job['finished_at'])).total_seconds()>max(3600,int(config().get('intelligence_refresh_hours',6))*3600)
            if due:refresh()
            _stop.wait(60)
    threading.Thread(target=loop,name='investment-scheduler',daemon=True).start()

def alerts():
    return {'items':store.rows('SELECT * FROM signals ORDER BY created_at DESC LIMIT 150'),'rules':rules(),'unread':store.rows('SELECT COUNT(*) AS n FROM signals WHERE seen=0')[0]['n'],'delivery':'In-app only. Persistent outbox supports future notification adapters.'}

def status():
    initialize();jobs=store.rows('SELECT * FROM jobs');last=next((j for j in jobs if j['name']=='ingestion'),{})
    errors=json.loads(last.get('error') or '[]')
    return {'connections':connection_status(),'jobs':jobs,'errors':errors,'company_count':store.rows("SELECT COUNT(DISTINCT entity) AS n FROM observations WHERE kind='company'")[0]['n'],
      'price_rows':store.rows('SELECT COUNT(*) AS n FROM prices')[0]['n'],'filing_count':store.rows('SELECT COUNT(*) AS n FROM filings')[0]['n'],'storage':'Local SQLite database in cache/intelligence.sqlite3; excluded from Git and Supabase sync.'}

def summary():
    initialize();signals=alerts();badges={}
    analysis=analyze()
    for r in store.rows("SELECT DISTINCT entity FROM observations WHERE kind='company'"):
        opp=opportunity(r['entity'],analysis);sc=opp['score']
        badges[r['entity']]={'score':sc['overall'],'coverage_pct':sc['coverage_pct'],'status':opp['status'],
                             'insider_buyers':opp['insiders']['buyers'],'tracked_owners':len(opp['smart_money'].get('owners',[]))}
    return {'unread':signals['unread'],'signals':signals['items'][:3],'badges':badges,'connections':connection_status(),'risks':analysis['warnings'][:2]}

def action(name,body):
    initialize()
    if name=='history_metrics':return a.price_summary(body.get('points'))
    if name=='refresh':
        import app
        if app.OFFLINE:raise ValueError('The app is in offline mode; turn off offline mode before updating public data.')
        return refresh([symbol(body['symbol'])] if body.get('symbol') else None,True)
    if name=='manager':
        cik=str(body.get('cik','')).strip()
        if not cik.isdigit() or len(cik)>10:raise ValueError('Enter the SEC manager CIK, using digits only.')
        if body.get('delete'):store.execute('DELETE FROM managers WHERE cik=?',(str(int(cik)),))
        else:
            label=str(body.get('name','')).strip()[:120]
            if not label:raise ValueError('Enter an investor name.')
            store.execute('INSERT OR REPLACE INTO managers VALUES(?,?,?)',(str(int(cik)),label,1 if body.get('enabled',True) else 0))
    elif name=='watchlist':
        s=symbol(body.get('symbol'));removed=set(store.setting('removed_watchlist',[]))
        if body.get('delete'):store.execute('DELETE FROM watchlist WHERE symbol=?',(s,));removed.add(s)
        else:
            removed.discard(s);store.execute('INSERT OR REPLACE INTO watchlist VALUES(?,?,?,?,?)',(s,str(body.get('name') or s)[:120],str(body.get('note',''))[:5000],str(body.get('thesis',''))[:10000],store.now()))
        store.set_setting('removed_watchlist',sorted(removed))
    elif name=='rule':
        typ=body.get('type')
        if typ not in dict(DEFAULT_RULES):raise ValueError('Unknown alert type.')
        s=symbol(body['symbol']) if body.get('symbol') else '';threshold=float(body.get('threshold',dict(DEFAULT_RULES)[typ]))
        if not math.isfinite(threshold) or threshold<0:raise ValueError('Threshold must be a nonnegative number.')
        rid=typ+(':'+s if s else '')
        if body.get('delete'):store.execute('DELETE FROM alert_rules WHERE id=?',(rid,))
        else:store.execute('INSERT OR REPLACE INTO alert_rules VALUES(?,?,?,?,?,?)',(rid,typ,s,threshold,1 if body.get('enabled',True) else 0,'{}'))
    elif name=='seen':
        for ident in body.get('ids',[])[:150]:store.execute('UPDATE signals SET seen=1 WHERE id=?',(str(ident),))
    elif name=='thesis':
        s=symbol(body.get('symbol'));cases=body.get('cases',[])
        if len(cases)>3:raise ValueError('Use at most three scenarios.')
        obs=store.latest('company',s)
        computed=a.scenarios(a.fundamentals(obs['data']) if obs else {},cases)
        value={'notes':str(body.get('notes',''))[:20000],'cases':cases,'computed':computed,'saved_at':store.now()}
        store.set_setting('thesis:'+s,value)
        if body.get('cusip'):
            cusip=str(body['cusip']).upper().strip()
            if len(cusip)!=9 or not cusip.isalnum():raise ValueError('CUSIP must contain nine letters/digits.')
            mapping=store.setting('cusip_map',{});mapping[s]=cusip;store.set_setting('cusip_map',mapping)
        return value
    elif name=='connections':
        import extras
        s=config()
        for key in ('sec_user_agent','quiver_api_key','intelligence_market_provider','openbb_data_provider','intelligence_benchmark','intelligence_risk_free_pct','intelligence_refresh_hours'):
            if key in body:
                value=body[key]
                if key=='quiver_api_key' and value=='':continue
                if key=='sec_user_agent' and value and '@' not in str(value):raise ValueError('SEC identification must include a contact email.')
                if key=='intelligence_market_provider' and value not in ('auto','yahoo','openbb'):raise ValueError('Choose Auto, Yahoo or OpenBB.')
                if key=='intelligence_benchmark':value=symbol(value)
                if key=='intelligence_risk_free_pct':
                    value=float(value)
                    if not -5<=value<=30:raise ValueError('Risk-free assumption must be -5% through 30%.')
                if key=='intelligence_refresh_hours':value=max(1,min(168,int(value)))
                s[key]=value
        if body.get('sec_user_agent'):s['sec_enabled']=True
        if body.get('disable_sec'):s['sec_enabled']=False
        if body.get('clear_quiver'):s.pop('quiver_api_key',None)
        extras.atomic_write(store.ROOT/'settings.json',json.dumps(s,indent=2))
    else:raise ValueError('Unknown investment action.')
    return {'ok':True}

def get(name,q):
    if name=='status':return status()
    if name=='portfolio':return analyze(q.get('account',''),q.get('class','all'))
    if name=='opportunities':return opportunities()
    if name=='investors':return investors(q.get('cik'))
    if name=='insiders':return insider_activity(q.get('symbol',''))
    if name=='watchlist':return {'items':watchlist(),'opportunities':opportunities()['items'],'alerts':alerts()}
    if name=='research':return research(q.get('symbol'))
    if name=='prices':
        s=symbol(q.get('symbol'));return {'symbol':s,'rows':store.rows('SELECT * FROM prices WHERE symbol=? ORDER BY date',(s,))}
    if name=='alerts':return alerts()
    if name=='summary':return summary()
    raise ValueError('Unknown investment endpoint.')
