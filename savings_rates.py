"""Public flexible-savings offers, fetched without customer data or credentials."""
import hashlib,html,json,math,re,threading,time,urllib.request
from datetime import date,datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
from pathlib import Path
import extras

SOURCES={'raisin':'https://www.raisin.com/nl-nl/spaarrekening/', 'abn':'https://www.abnamro.nl/nl/prive/rente/actuele-rente.html', 'trade_republic':'https://traderepublic.com/nl-nl/rente'}
_busy=False;_lock=threading.Lock()
def number(value):
    try:
        n=float(str(value).replace(',','.'));return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def safe_url(value):
    try:return value if urlparse(value).scheme in ('http','https') and urlparse(value).netloc else None
    except Exception:return None
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag in ('td','tr','p','div','br'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,text):
        if not self.skip:self.parts.append(text)
def plain(body):
    parser=Text();parser.feed(body);return re.sub(r'\s+',' ',' '.join(parser.parts)).strip()
def parse_raisin(body):
    match=re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',body,re.S)
    if not match:raise ValueError('Raisin public product data was not found')
    payload=json.loads(match[1]);products=[]
    def walk(value):
        if isinstance(value,dict):
            if 'initialCatalogProducts' in value:products.extend(value['initialCatalogProducts'])
            else:
                for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(payload);out={}
    for p in products:
        if p.get('productType')!='OVERNIGHT' or p.get('currency')!='EUR':continue
        conditions=p.get('conditions') or {};withdrawal=conditions.get('withdrawal') or {};termination=conditions.get('termination') or {}
        if withdrawal.get('enabled') is not True or termination.get('noticePeriod'):continue
        rates=p.get('interestRates') or {};rate=number(rates.get('interestRateNominal'));effective=rates.get('effectiveDate')
        if rate is None or not 0<=rate<=20 or effective and effective>date.today().isoformat():continue
        bank=p.get('depositTakingBank') or {};opening=conditions.get('opening') or {};scheme=bank.get('statutoryDepositGuaranteeScheme') or {};term=p.get('termNormalized') or {}
        promo=bool(opening.get('restrictedToNewCustomers')) or bool(term.get('months'))
        docs=p.get('documents') or p.get('productDocuments') or []
        document=next((safe_url(d.get('url')) for d in docs if isinstance(d,dict) and d.get('documentType')=='PRODUCT_INFORMATION_SHEET' and safe_url(d.get('url'))),None)
        key='raisin:'+str(p['id'])
        out[key]={'id':key,'provider':'Raisin','name':bank.get('name') or str(p['id']),'legal_bank':bank.get('legalName'),'bank_id':bank.get('id'),'country':(bank.get('branchCountry') or {}).get('name'),'currency':'EUR','rate_pct':rate,'effective_date':effective,'variable':p.get('interestRateModality')=='VARIABLE','promotional':promo,'new_customers_only':bool(opening.get('restrictedToNewCustomers')),'promo_months':number(term.get('months')) if promo else None,'minimum_eur':number(opening.get('minimumAmount')),'maximum_eur':number(conditions.get('maximumBalance')),'access':'transfer','withdrawal':'Withdrawable without a notice period; transfer timing depends on the bank.','payout':p.get('interestTreatment'),'guarantee_limit_eur':number(scheme.get('insuredAmount')),'guarantee_currency':scheme.get('currency'),'guarantee_scheme':scheme.get('name'),'guarantee_country':(scheme.get('country') or {}).get('name'),'source_url':SOURCES['raisin'],'product_url':document or SOURCES['raisin'],'terms':'New-customer offer; the introductory period is not a guaranteed annual rate.' if promo else 'Variable rate. Check product conditions and transfer timing before opening.'}
    if not out:raise ValueError('No verified flexible EUR products in the public catalogue')
    for row in out.values():
        row['guarantee_amount']=row['guarantee_limit_eur']
        if row.get('guarantee_currency')!='EUR':row['guarantee_limit_eur']=None
    return list(out.values())
def parse_abn(body):
    text=plain(body);match=re.search(r'Direct Sparen\s*€\s*0\s*tot en met\s*€\s*500[.\s]?000\s*(\d+[,.]\d+)\s*%',text,re.I)
    if not match:raise ValueError('ABN Direct Sparen first balance tier could not be verified')
    rate=number(match[1]);assert rate is not None and 0<=rate<=20
    return [{'id':'abn:direct','provider':'ABN AMRO','name':'Direct Sparen','legal_bank':'ABN AMRO Bank N.V.','country':'Netherlands','currency':'EUR','rate_pct':rate,'variable':True,'promotional':False,'new_customers_only':False,'minimum_eur':0,'maximum_eur':500000,'access':'instant','withdrawal':'Deposits and withdrawals allowed; an ABN AMRO payment account is required.','payout':'Quarterly','source_url':SOURCES['abn'],'product_url':'https://www.abnamro.nl/nl/prive/sparen/spaarvormen/direct-sparen/index.html','terms':'Rate shown for the first published balance tier; other tiers have separate rates.','guarantee_limit_eur':None}]
def parse_trade_republic(body):
    class Description(HTMLParser):
        def __init__(self):super().__init__();self.items=[]
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            if tag=='meta' and (values.get('name')=='description' or values.get('property')=='og:description'):self.items.append(values.get('content',''))
    description=Description();description.feed(body)
    text=plain(body)+' '+' '.join(description.items);match=re.search(r'Activeer\s*(\d+[,.]?\d*)\s*%\s*rente\s*op je kassaldo tot\s*€\s*([\d.]+)\s*,?\s*voor nieuwe klanten',text,re.I)
    if not match:raise ValueError('Trade Republic published cash offer could not be verified')
    rate=number(match[1]);maximum=number(match[2].replace('.',''))
    if rate is None or not 0<=rate<=20:raise ValueError('Invalid cash rate')
    return [{'id':'trade_republic:published','provider':'Trade Republic','name':'Published new-customer cash offer','currency':'EUR','rate_pct':rate,'variable':True,'promotional':True,'new_customers_only':True,'promo_months':None,'minimum_eur':None,'maximum_eur':maximum,'access':'transfer','withdrawal':'Published as withdrawable; activation and personal eligibility must be checked in the app.','payout':'Monthly','source_url':SOURCES['trade_republic'],'product_url':SOURCES['trade_republic'],'terms':'New customers only. Duration and existing-customer rate are not verified; excluded from ongoing-rate recommendations.','guarantee_limit_eur':None}]
PARSERS={'raisin':parse_raisin,'abn':parse_abn,'trade_republic':parse_trade_republic}
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'WealthDashboard/1.0','Accept':'text/html','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=25) as response:
        if urlparse(response.geturl()).hostname not in {urlparse(u).hostname for u in SOURCES.values()}:raise ValueError('Unexpected rate-source redirect')
        raw=response.read(3_000_001)
    if len(raw)>3_000_000:raise ValueError('Public rate page is too large')
    return raw.decode('utf-8')
def snapshot(offline=False,force=False):
    global _busy
    old=extras.read(extras.CACHE/'savings-rates.json',{});stale=time.time()-old.get('at',0)>86400
    if not offline and (force or stale) and time.time()-old.get('attempt_at',0)>60:
        with _lock:
            if not _busy:_busy=True;threading.Thread(target=_refresh,daemon=True).start()
    out={**old,'offers':old.get('offers',[]),'updating':_busy,'stale':stale,'coverage':'Publicly loaded Raisin flexible-EUR catalogue plus ABN AMRO and Trade Republic pages; not the entire savings market.'}
    for offer in out['offers']:
        offer['stale']=time.time()-offer.get('retrieved_at_epoch',0)>86400
        if offer.get('guarantee_currency') and offer['guarantee_currency']!='EUR':
            offer['guarantee_amount']=offer.get('guarantee_amount',offer.get('guarantee_limit_eur'));offer['guarantee_limit_eur']=None
    return out
def _refresh():
    global _busy
    old=extras.read(extras.CACHE/'savings-rates.json',{});previous={k:[o for o in old.get('offers',[]) if o.get('source_key')==k] for k in SOURCES};offers=[];errors=[];states=[]
    try:
        for key,url in SOURCES.items():
            try:
                body=fetch(url);rows=PARSERS[key](body);stamp=datetime.now().isoformat(timespec='seconds')
                for row in rows:row.update(source_key=key,retrieved_at=stamp,retrieved_at_epoch=time.time())
                offers.extend(rows);states.append({'source':key,'status':'updated','products':len(rows),'url':url})
            except Exception as error:
                offers.extend(previous[key]);errors.append({'source':key,'message':str(error)[:160]});states.append({'source':key,'status':'cached' if previous[key] else 'unavailable','products':len(previous[key]),'url':url})
        extras.write(extras.CACHE/'savings-rates.json',{'offers':offers,'sources':states,'errors':errors,'at':time.time() if all(s['status']=='updated' for s in states) else old.get('at',0),'attempt_at':time.time(),'retrieved_at':datetime.now().isoformat(timespec='seconds')})
    finally:
        with _lock:_busy=False
def estimate(offer,amount,months=12):
    amount=number(amount);rate=number(offer.get('rate_pct'))
    if amount is None or amount<0 or rate is None:return {'eligible':False,'interest_eur':None,'reason':'Amount or rate unavailable'}
    if offer.get('minimum_eur') is not None and amount<offer['minimum_eur'] or offer.get('maximum_eur') is not None and amount>offer['maximum_eur']:return {'eligible':False,'interest_eur':None,'reason':'Outside the published balance tier'}
    duration=months
    if offer.get('promotional'):
        if not offer.get('promo_months'):return {'eligible':None,'interest_eur':None,'reason':'Offer duration or eligibility needs checking'}
        duration=min(months,offer['promo_months'])
    return {'eligible':None if offer.get('new_customers_only') else True,'interest_eur':round(amount*rate/100*duration/12,2),'months':duration,'reason':'Introductory period only' if offer.get('promotional') else 'At a constant published rate, before costs; variable rates may change'}
