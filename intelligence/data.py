"""Replaceable data adapters. All outbound requests concern public securities only."""
import importlib.util
import json
import math
import os
import re
import threading
import time
import subprocess
import sys
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlencode
from datetime import date, timedelta
from . import store

def config():
    try: return json.loads((store.ROOT/'settings.json').read_text())
    except (OSError,ValueError): return {}

def symbol(value):
    s=str(value or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=\-]{0,24}',s): raise ValueError('Enter a valid market symbol, for example ASML.AS.')
    return s

def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value): return None
    if hasattr(value,'item'): return clean(value.item())
    if hasattr(value,'isoformat'): return value.isoformat()
    return value

class HTTP:
    _lock=threading.Lock();_last=0.;_blocked=0.
    @classmethod
    def get(cls,url,sec=False,headers=None):
        h={'User-Agent':'WealthDashboard/1.0','Accept':'application/json'}
        if sec:
            cfg=config()
            if not os.getenv('SEC_USER_AGENT') and not cfg.get('sec_enabled',False):raise RuntimeError('SEC downloads are disabled until you allow your contact email to identify SEC requests.')
            ua=os.getenv('SEC_USER_AGENT') or cfg.get('sec_user_agent')
            if not ua and cfg.get('contact_email'): ua='WealthDashboard '+cfg['contact_email']
            if not ua or '@' not in ua: raise RuntimeError('SEC needs an identifying contact email in Data connections before downloading filings.')
            h['User-Agent']=ua
        h.update(headers or {})
        for attempt in range(3):
            if sec:
                with cls._lock:
                    # Reserve a slot across HTTP threads and separate MCP processes.
                    with store.connect() as c:
                        c.execute('BEGIN IMMEDIATE')
                        rows=c.execute("SELECT payload FROM settings WHERE key='sec_rate_limit'").fetchone()
                        gate=json.loads(rows[0]) if rows else {}
                        wall=time.time()
                        if wall<gate.get('blocked_until',0):raise RuntimeError('SEC temporarily restricted access; cached data remains available. Retry later.')
                        slot=max(wall,gate.get('next_request',wall))
                        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('sec_rate_limit',json.dumps({'next_request':slot+.22,'blocked_until':0})))
                    time.sleep(max(0,slot-time.time()))
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=25) as r: return r.read().decode('utf-8-sig')
            except urllib.error.HTTPError as e:
                if e.code in (403,429) and sec:
                    cls._blocked=time.monotonic()+300
                    store.set_setting('sec_rate_limit',{'next_request':time.time()+300,'blocked_until':time.time()+300})
                    raise RuntimeError('SEC temporarily restricted access; cached data remains available. Retry later.') from None
                if e.code not in (429,500,502,503,504) or attempt==2: raise RuntimeError(f'Public data source returned HTTP {e.code}.') from None
                time.sleep(min(8,2**attempt))
        raise RuntimeError('Public data source unavailable.')

class Yahoo:
    name='Yahoo Finance (delayed)'
    def company(self,s):
        import yfinance as yf
        t=yf.Ticker(symbol(s));info=clean(t.info)
        if not info or not info.get('regularMarketPrice') and not info.get('currentPrice'): raise RuntimeError('Yahoo has no quote for this symbol.')
        holdings=[];segments=[]
        if info.get('quoteType') in ('ETF','MUTUALFUND'):
            try:
                for k,r in t.funds_data.top_holdings.iterrows():
                    holdings.append({'symbol':str(k),'name':r.get('Name',str(k)),'weight':float(r['Holding Percent'])})
            except Exception: pass
        financials={}
        for name,attribute in [('income','income_stmt'),('balance','balance_sheet'),('cashflow','cashflow')]:
            try:
                df=getattr(t,attribute)
                financials[name]=[{'period':str(k.date()),'currency':info.get('financialCurrency'),'items':clean(r.dropna().to_dict())} for k,r in df.items()]
            except Exception: financials[name]=[]
        def frame(attr):
            try: return clean(getattr(t,attr).reset_index().to_dict('records'))
            except Exception: return []
        news=[]
        try:
            for n in t.news[:15]:
                n=n.get('content',n);url=(n.get('canonicalUrl') or {}).get('url') or n.get('link')
                if url and url.startswith('https://'):news.append({'title':n.get('title'),'url':url,'date':n.get('pubDate'),'source':(n.get('provider') or {}).get('displayName')})
        except Exception:pass
        return {'info':info,'statements':financials,'lookthrough':holdings,'news':news,'analyst_estimates':frame('earnings_estimate'),
                'revenue_estimates':frame('revenue_estimate'),'estimate_changes':frame('eps_revisions'),'institutional_ownership':frame('institutional_holders')}
    def prices(self,s,start):
        import yfinance as yf
        t=yf.Ticker(symbol(s)); df=t.history(start=start,auto_adjust=True,actions=True,raise_errors=True)
        if df.empty: raise RuntimeError('No historical prices returned.')
        return [{'date':str(k.date()),'close':float(r['Close']),'dividend':float(r.get('Dividends',0)),'split':float(r.get('Stock Splits',0))} for k,r in df.iterrows() if math.isfinite(float(r['Close'])) and r['Close']>0]

class OpenBB:
    name='OpenBB'
    def python(self):
        configured=config().get('openbb_python') or os.getenv('OPENBB_PYTHON')
        path=Path(configured) if configured else store.ROOT/'.openbb-env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        return path if path.is_file() else None
    def available(self):return importlib.util.find_spec('openbb') is not None or self.python() is not None
    def worker(self,request):
        proc=subprocess.run([str(self.python()),'-X','utf8',str(store.ROOT/'intelligence/openbb_worker.py')],
            input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',timeout=180,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:out=json.loads(proc.stdout)
        except ValueError:raise RuntimeError('The isolated OpenBB runtime could not answer. Check its installed extensions.') from None
        if out.get('error'):raise RuntimeError('OpenBB dataset unavailable: '+out['error'])
        return clean(out['data'])
    def query(self,command,**kwargs):
        if not self.available(): raise RuntimeError('OpenBB is not installed. Install the optional integration requirements.')
        if not re.fullmatch(r'[a-z_]+(?:\.[a-z_]+){1,5}',command): raise ValueError('Invalid OpenBB command')
        if self.python() or importlib.util.find_spec('openbb') is None:
            return self.worker({'command':command,'kwargs':kwargs})
        from openbb_core.app import constants
        constants.OPENBB_DIRECTORY=store.ROOT/'cache'/'openbb'
        constants.USER_SETTINGS_PATH=constants.OPENBB_DIRECTORY/'user_settings.json'
        constants.SYSTEM_SETTINGS_PATH=constants.OPENBB_DIRECTORY/'system_settings.json'
        from openbb import obb
        node=obb
        for part in command.split('.'):node=getattr(node,part)
        result=node(**kwargs)
        return clean(result.to_df().reset_index().to_dict('records'))
    def prices(self,s,start):
        c=config();command=c.get('openbb_price_command','equity.price.historical')
        kwargs={'symbol':symbol(s),'start_date':start,'adjustment':'splits_and_dividends'}
        if c.get('openbb_data_provider','yfinance'):kwargs['provider']=c.get('openbb_data_provider','yfinance')
        rows=self.query(command,**kwargs)
        return [{**r,'dividend':r.get('dividend') or r.get('dividends') or 0,'split':r.get('split') or r.get('stock_splits') or r.get('split_ratio') or 0} for r in rows]
    def company(self,s):
        cfg=config();routes={'profile':'equity.profile','income':'equity.fundamental.income','balance':'equity.fundamental.balance',
          'cashflow':'equity.fundamental.cash','ratios':'equity.fundamental.ratios','estimates':'equity.estimates.historical',
          'ownership':'equity.ownership.institutional','segments':'equity.fundamental.revenue_per_segment',
          'geography':'equity.fundamental.revenue_per_geography','macro':'economy.interest_rates'}
        out={};errors={}
        if self.python():
            queries={}
            for k,cmd in {**routes,**cfg.get('openbb_commands',{})}.items():
                if not re.fullmatch(r'[a-z_]+(?:\.[a-z_]+){1,5}',cmd):raise ValueError('Invalid OpenBB command')
                queries[k]={'command':cmd,'kwargs':{'symbol':symbol(s),'provider':cfg.get('openbb_data_provider','yfinance')} if k!='macro' else {}}
            return self.worker({'queries':queries})
        for k,cmd in {**routes,**cfg.get('openbb_commands',{})}.items():
            try:
                kw={'symbol':symbol(s),'provider':cfg.get('openbb_data_provider','yfinance')}
                if k=='macro':kw={}
                out[k]=self.query(cmd,**kw)
            except Exception:errors[k]='Dataset unavailable from the configured OpenBB provider/version.'
        return {'datasets':out,'unavailable':errors}

class Quiver:
    name='Quiver Quantitative'
    # Each route can be changed for the user's subscription/API version without UI changes.
    # Verified against the official /docs/schema.json. Live endpoints accept ticker
    # as a query parameter; historical endpoints place it in the path.
    routes={'institutional':'live/sec13f','insiders':'live/insiders','congress':'historical/congresstrading/{ticker}',
            'contracts':'historical/govcontractsall/{ticker}','lobbying':'historical/lobbying/{ticker}',
            'patents':'historical/allpatents/{ticker}','compensation':'historical/executivecompensation/{ticker}'}
    def key(self):return os.getenv('QUIVER_API_KEY') or config().get('quiver_api_key','')
    def fetch(self,s,dataset):
        if not self.key():raise RuntimeError('Quiver is optional; add QUIVER_API_KEY or save it in Data connections.')
        route=config().get('quiver_routes',{}).get(dataset,self.routes.get(dataset))
        if not route or not re.fullmatch(r'(live|historical)/[a-z0-9_]+(?:/\{ticker\})?',route):raise ValueError('Unsupported Quiver dataset')
        url='https://api.quiverquant.com/beta/'+route.replace('{ticker}',symbol(s))
        query={} if '{ticker}' in route else {'ticker':symbol(s)}
        paginated=dataset in ('institutional','insiders','lobbying','patents','compensation');records=[]
        for page in range(1,21):
            params={**query,**({'page':page,'page_size':500} if paginated else {})}
            address=url+('?'+urlencode(params) if params else '')
            data=json.loads(HTTP.get(address,headers={'Authorization':'Bearer '+self.key()}))
            if not isinstance(data,list):raise RuntimeError('Quiver returned an unsupported response; check the dataset subscription.')
            records.extend(data)
            if not paginated or len(data)<500:break
        return {'records':records,'pages':page,'possibly_truncated':paginated and page==20 and len(data)==500,
                'coverage':'Subscription-dependent Quiver public dataset; capped at 10,000 rows per refresh.'},url

def market_prices(s,start):
    cfg=config();openbb=OpenBB()
    if cfg.get('intelligence_market_provider','auto') in ('auto','openbb') and openbb.available():
        try:
            rows=openbb.prices(s,start)
            return rows,openbb.name
        except Exception:
            if cfg.get('intelligence_market_provider')=='openbb':raise
    return Yahoo().prices(s,start),Yahoo.name

def connection_status():
    c=config()
    return {'market':c.get('intelligence_market_provider','auto'),'openbb_installed':OpenBB().available(),
            'openbb_provider':c.get('openbb_data_provider','yfinance'),'quiver_configured':bool(Quiver().key()),
            'sec_configured':bool(os.getenv('SEC_USER_AGENT') or c.get('sec_enabled') and (c.get('sec_user_agent') or c.get('contact_email'))),
            'credentials':'Saved locally; never returned to the browser.'}
