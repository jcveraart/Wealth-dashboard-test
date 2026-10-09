"""Bounded public-data adapters. No private ledger content is sent to research sources."""
import csv
import hashlib
import io
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime,timezone
from . import store

SOURCES={
 'fred':('FRED public data','Selected official US economic CSV series','https://fred.stlouisfed.org/help/data/downloading/using-the-download-data-link/'),
 'fda':('openFDA Drugs@FDA','Reported applications, products and regulatory submissions','https://open.fda.gov/apis/drug/drugsfda/how-to-use-the-endpoint/'),
 'krakenhistory':('Kraken daily history','Public daily cryptocurrency candles','https://docs.kraken.com/api/docs/rest-api/get-ohlc-data'),
 'afmshort':('AFM short positions','Disclosed Dutch net short positions','https://www.afm.nl/nl-nl/sector/registers/meldingenregisters/netto-shortposities-actueel'),
 'afminsider':('AFM MAR 19','Disclosed Dutch management transactions','https://www.afm.nl/nl-nl/sector/registers/meldingenregisters/transacties-leidinggevenden-mar19-'),
 'bis':('Bank for International Settlements','Real effective exchange-rate index','https://data.bis.org/topics/EER'),
 'oecd':('OECD','Composite leading indicator','https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html'),
 'ecb':('European Central Bank','Rates, inflation and FX','https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0'),
 'worldbank':('World Bank','Country economic indicators','https://datahelpdesk.worldbank.org/knowledgebase/articles/889392'),
 'eurostat':('Eurostat','European consumer-price inflation','https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction'),
 'cbs':('CBS StatLine','Dutch consumer-price statistics','https://www.cbs.nl/en-gb/our-services/open-data/statline-as-open-data'),
 'openfigi':('OpenFIGI','Security identifier candidates','https://www.openfigi.com/api/documentation'),
 'gleif':('GLEIF','Legal entities and available relationships','https://www.gleif.org/en/lei-data/gleif-api/'),
 'gdelt':('GDELT','Worldwide public news discovery','https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/'),
 'trials':('ClinicalTrials.gov','Registered clinical studies','https://clinicaltrials.gov/data-api/api'),
 'usaspending':('USAspending','Disclosed US government awards','https://api.usaspending.gov/docs/'),
 'ted':('TED','Published European procurement notices','https://docs.ted.europa.eu/api/latest/search.html'),
 'kraken':('Kraken public markets','Public cryptocurrency quotes','https://docs.kraken.com/api/'),
}
HOSTS={'api.worldbank.org','ec.europa.eu','opendata.cbs.nl','api.openfigi.com','api.gleif.org','api.gdeltproject.org','clinicaltrials.gov','api.usaspending.gov','api.ted.europa.eu','api.kraken.com','data-api.ecb.europa.eu'}
HOSTS.update({'www.afm.nl','stats.bis.org','sdmx.oecd.org'})
HOSTS.update({'fred.stlouisfed.org','api.fda.gov'})
_query_lock=threading.Lock()

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlparse(newurl)
        if u.scheme!='https' or u.hostname not in HOSTS:raise ValueError('Unexpected public-data redirect.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def request(url,payload=None,empty_not_found=False):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS:raise ValueError('Unsupported data endpoint.')
    data=json.dumps(payload,allow_nan=False).encode() if payload is not None else None
    req=urllib.request.Request(url,data=data,headers={'User-Agent':'WealthDashboard/2.0 public research','Accept':'application/json','Content-Type':'application/json'})
    opener=urllib.request.build_opener(Redirect)
    try:
        with opener.open(req,timeout=25) as r:
            raw=r.read(8*1024*1024+1)
    except urllib.error.HTTPError as e:
        if empty_not_found and e.code==404:
            body=json.loads(e.read(8192))
            if body.get('error',{}).get('code')=='NOT_FOUND' and 'No matches' in body.get('error',{}).get('message',''):
                return {'results':[]}
        raise
    if len(raw)>8*1024*1024:raise ValueError('Public-data response exceeds supported size.')
    return json.loads(raw)

def request_text(url,accept='text/csv'):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS:raise ValueError('Unsupported public endpoint.')
    req=urllib.request.Request(url,headers={'User-Agent':'WealthDashboard/2.0 public research','Accept':accept})
    with urllib.request.build_opener(Redirect).open(req,timeout=25) as r:raw=r.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Public response exceeds supported size.')
    if raw[:2] in (b'\xff\xfe',b'\xfe\xff'):return raw.decode('utf-16')
    try:return raw.decode('utf-8-sig')
    except UnicodeDecodeError:return raw.decode('cp1252')

def public_term(value):
    value=str(value or '').strip()
    if not 2<=len(value)<=100 or not re.fullmatch(r'[A-Za-z0-9 .&()_-]+',value):raise ValueError('Enter a public company name or identifier, 2–100 characters.')
    if re.search(r'\b[A-Z]{2}\d{2}[A-Z0-9]{10,}\b',value) or '@' in value:raise ValueError('Use a public company name, not an email or bank account.')
    return value

def rows_worldbank(payload):
    rows=payload[1] if isinstance(payload,list) and len(payload)>1 else []
    return [{'date':r['date'],'value':r['value'],'country':r['country']['value'],'indicator':r['indicator']['value'],'unit':'% annual change','source_url':'https://data.worldbank.org/indicator/'+r['indicator']['id']} for r in rows or [] if r.get('value') is not None]

def query(source,term='',force=False):
    if source not in SOURCES:raise ValueError('Choose an available public source.')
    term=str(term or '').strip();key=hashlib.sha256((source+'|'+term).encode()).hexdigest()
    cached=store.rows('SELECT * FROM public_cache WHERE id=?',(key,))
    if cached:
        old={**json.loads(cached[0]['payload']),'retrieved_at':cached[0]['retrieved']}
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(cached[0]['retrieved'])).total_seconds()
        if not force and age<21600:return {**old,'cached':True}
    import app
    if app.OFFLINE:
        if cached:return {**old,'cached':True,'stale':True,'warning':'Offline mode; last available observation.'}
        raise ValueError('Public research requires online mode. Local records remain available.')
    title,desc,docs=SOURCES[source];rows=[];series=[];url=docs;scope=desc
    with _query_lock:
        try:
            if source=='fred':
                code=(term or 'CPIAUCSL').upper();known={'CPIAUCSL':('US consumer price index','Index 1982–1984=100, seasonally adjusted'),'DGS10':('US 10-year Treasury yield','Percent, daily'),'UNRATE':('US unemployment rate','Percent, seasonally adjusted'),'FEDFUNDS':('Effective federal funds rate','Percent, monthly')}
                if code not in known:raise ValueError('Choose CPIAUCSL, DGS10, UNRATE or FEDFUNDS.')
                url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urllib.parse.urlencode({'id':code,'cosd':'2016-01-01'});payload=list(csv.DictReader(io.StringIO(request_text(url))))
                rows=[{'date':r.get('observation_date') or r.get('DATE'),'value':float(r[code]),'unit':known[code][1],'series':code,'source_url':'https://fred.stlouisfed.org/series/'+code} for r in payload if r.get(code) not in (None,'','.','NA')]
                series=[{'date':r['date'],'value':r['value']} for r in rows];scope=known[code][0]+'. Public chart CSV download; values retain the series units. API functions still require a registered key.'
            elif source=='fda':
                name=public_term(term);url='https://api.fda.gov/drug/drugsfda.json?'+urllib.parse.urlencode({'search':'sponsor_name:"'+name+'"','limit':30})
                payload=request(url,empty_not_found=True)
                for r in payload.get('results',[]):
                    submissions=sorted(r.get('submissions',[]),key=lambda r:r.get('submission_status_date',''),reverse=True)
                    last=submissions[0] if submissions else {}
                    rows.append({'application':r.get('application_number'),'sponsor':r.get('sponsor_name'),'products':', '.join(p.get('brand_name','') for p in r.get('products',[])),'last_submission_type':last.get('submission_type'),'last_status':last.get('submission_status'),'status_date':last.get('submission_status_date'),'source_url':url})
                scope='Reported Drugs@FDA applications and submission statuses. Sponsor names may be abbreviated (for example NOVO); zero matches are not evidence of no regulatory activity. Not every submission is an approval. Public no-key quota applies.'
            elif source=='krakenhistory':
                pair=(term or 'XBTEUR').upper()
                if not re.fullmatch(r'[A-Z0-9]{5,18}',pair):raise ValueError('Use a public market pair, for example XBTEUR.')
                url='https://api.kraken.com/0/public/OHLC?'+urllib.parse.urlencode({'pair':pair,'interval':1440});payload=request(url)
                if payload.get('error'):raise ValueError('; '.join(payload['error']))
                result=payload.get('result',{});candles=next((v for k,v in result.items() if k!='last'),[])
                # The final row represents the uncommitted current interval, so exclude it.
                rows=[{'date':datetime.fromtimestamp(r[0],timezone.utc).date().isoformat(),'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4]),'volume':float(r[6]),'pair':pair,'source_url':docs} for r in candles[:-1]]
                series=[{'date':r['date'],'value':r['close']} for r in rows];scope='Completed daily candles only. Kraken limits the recent window to 720 intervals; quotes are in the pair currency, not automatically converted to EUR.'
            elif source in ('afmshort','afminsider'):
                register='8a46a4ef-f196-4467-a7ab-1ae1cb58f0e7' if source=='afmshort' else '0ee836dc-5520-459d-bcf4-a4a689de6614'
                url='https://www.afm.nl/export.aspx?format=csv&type='+register
                text=request_text(url);dialect=csv.Sniffer().sniff(text[:10000],delimiters=';,\t');rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
                if term:
                    name=public_term(term).lower();rows=[r for r in rows if name in ' '.join(str(x) for x in r.values()).lower()]
                for r in rows:r['source_url']=docs
                scope='Original AFM register fields and transaction/position dates. Disclosures are threshold-dependent; no estimate of undisclosed shorts and no automatic claim that management transactions are discretionary buys.'
            elif source=='bis':
                country=(term or 'NL').upper()
                if not re.fullmatch('[A-Z]{2}',country):raise ValueError('Use a two-letter country code, such as NL.')
                url='https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/M.R.B.'+country+'?lastNObservations=60'
                text=request_text(url,'application/vnd.sdmx.data+csv;version=1.0.0');raw_rows=list(csv.DictReader(io.StringIO(text)))
                rows=[{'date':r.get('TIME_PERIOD'),'value':float(r['OBS_VALUE']),'unit':'Real effective exchange rate index, 2020 = 100','source_url':'https://data.bis.org/topics/EER/BIS%2CWS_EER%2C1.0/M.R.B.'+country} for r in raw_rows if r.get('OBS_VALUE')]
                series=[{'date':r['date']+'-01','value':r['value']} for r in rows];scope='BIS broad real effective exchange-rate index, monthly. Macro context, not the currency exposure of your investments.'
            elif source=='oecd':
                country={'NL':'NLD','US':'USA','DE':'DEU'}.get(term.upper(),term.upper()) if term else 'USA'
                if not re.fullmatch('[A-Z]{3}',country):raise ValueError('Use a three-letter OECD country code, such as NLD or USA.')
                if country=='NLD':raise ValueError('This leading-indicator dataset no longer covers the Netherlands. Use USA, DEU, FRA or another covered country.')
                url='https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI/'+country+'.M.LI...AA...H?startPeriod=2021-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels'
                text=request_text(url);raw_rows=list(csv.DictReader(io.StringIO(text)));rows=[{'date':r.get('TIME_PERIOD'),'value':float(r['OBS_VALUE']),'unit':r.get('Unit of measure') or r.get('UNIT_MEASURE'),'source_url':docs} for r in raw_rows if r.get('OBS_VALUE')]
                series=[{'date':r['date']+'-01','value':r['value']} for r in rows];scope='OECD composite leading indicator, amplitude adjusted. A statistical business-cycle indicator, not an investment prediction.'
            elif source=='ecb':
                import public
                # Reuse the app's already verified and cached official ECB adapter.
                public._fetch_economy();payload=public.economy(True);rows=[{'metric':k,'value':v} for k,v in payload.items() if not isinstance(v,(dict,list))]
                scope='Official ECB observations with their reported dates; rates/inflation are percentages, FX fields follow existing adapter conventions.'
            elif source=='worldbank':
                country=(term or 'NL').upper()
                if not re.fullmatch(r'[A-Z]{2,3}',country):raise ValueError('Use a country code, for example NL or US.')
                url='https://api.worldbank.org/v2/country/'+country+'/indicator/FP.CPI.TOTL.ZG?format=json&per_page=80'
                payload=request(url);rows=rows_worldbank(payload);series=[{'date':r['date']+'-01-01','value':r['value']} for r in reversed(rows)]
                scope='Annual consumer-price inflation, percent. Country-level context, not your personal realised inflation.'
            elif source=='eurostat':
                country=(term or 'NL').upper()
                if not re.fullmatch(r'[A-Z0-9_]{2,6}',country):raise ValueError('Use a Eurostat geography code, for example NL or EA20.')
                url='https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?'+urllib.parse.urlencode({'geo':country,'coicop':'CP00','freq':'M','lang':'EN','sinceTimePeriod':'2021-01'})
                payload=request(url);dims=payload.get('dimension',{});values=payload.get('value',{});time=dims.get('time',{}).get('category',{}).get('index',{})
                # Only render a series when every non-time dimension has size 1.
                ids=payload.get('id',[]);sizes=payload.get('size',[])
                if not all(n==1 for k,n in zip(ids,sizes) if k!='time'):raise ValueError('This query returns multiple statistical series; a narrower selection is required.')
                for stamp,index in sorted(time.items()):
                    value=values.get(str(index)) if isinstance(values,dict) else values[index]
                    if value is not None:rows.append({'date':stamp,'value':value,'unit':'% annual change','status':payload.get('status',{}).get(str(index)) if isinstance(payload.get('status',{}),dict) else None})
                series=[{'date':r['date']+'-01','value':r['value']} for r in rows];scope='All-items monthly HICP annual rate of change; published Eurostat statuses retained.'
            elif source=='cbs':
                url='https://opendata.cbs.nl/ODataApi/OData/83131NED/TypedDataSet?$top=80&$orderby=ID%20desc'
                payload=request(url);rows=payload.get('value',[]);scope='Raw CBS consumer-price table rows. Category/period codes are retained; no ambiguous code is interpreted as your own spending category.'
            elif source=='openfigi':
                ident=public_term(term).upper()
                typ='ID_ISIN' if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{10}',ident) else 'TICKER'
                url='https://api.openfigi.com/v3/mapping';payload=request(url,[{'idType':typ,'idValue':ident}]);rows=payload[0].get('data',[]) if payload else []
                scope='Mapping candidates, not a confirmed match. Verify the exchange, currency and share class before changing an instrument.'
            elif source=='gleif':
                name=public_term(term);url='https://api.gleif.org/api/v1/lei-records?'+urllib.parse.urlencode({'filter[entity.legalName]':name,'page[size]':20})
                payload=request(url);rows=[{'lei':r['id'],'name':r['attributes'].get('entity',{}).get('legalName',{}).get('name'),'jurisdiction':r['attributes'].get('entity',{}).get('jurisdiction'),'status':r['attributes'].get('entity',{}).get('status'),'source_url':r.get('links',{}).get('self')} for r in payload.get('data',[])]
                scope='Legal-entity candidates. A similar company name alone does not establish a subsidiary or issuer match.'
            elif source=='gdelt':
                name=public_term(term);url='https://api.gdeltproject.org/api/v2/doc/doc?'+urllib.parse.urlencode({'query':'"'+name+'"','mode':'artlist','format':'json','maxrecords':50,'sort':'datedesc','timespan':'1month'})
                payload=request(url);rows=[{'title':r.get('title'),'date':r.get('seendate'),'source':r.get('domain'),'language':r.get('language'),'source_url':r.get('url')} for r in payload.get('articles',[])];scope='News discovery results. Original reporting must be reviewed; repeated coverage is not independent confirmation.'
            elif source=='trials':
                name=public_term(term);url='https://clinicaltrials.gov/api/v2/studies?'+urllib.parse.urlencode({'query.spons':name,'pageSize':30,'format':'json'})
                payload=request(url)
                for item in payload.get('studies',[]):
                    p=item.get('protocolSection',{});i=p.get('identificationModule',{});s=p.get('statusModule',{})
                    rows.append({'id':i.get('nctId'),'title':i.get('briefTitle'),'status':s.get('overallStatus'),'phase':', '.join(p.get('designModule',{}).get('phases',[])),'sponsor':p.get('sponsorCollaboratorsModule',{}).get('leadSponsor',{}).get('name'),'updated':s.get('lastUpdatePostDateStruct',{}).get('date'),'source_url':'https://clinicaltrials.gov/study/'+str(i.get('nctId'))})
                scope='Registered study records, not evidence that a treatment works or a predicted approval. Results limited to the first 30 matching records.'
            elif source=='usaspending':
                name=public_term(term);url='https://api.usaspending.gov/api/v2/search/spending_by_award/'
                payload=request(url,{'filters':{'keywords':[name],'award_type_codes':['A','B','C','D']},'fields':['Award ID','Recipient Name','Award Amount','Description','Awarding Agency','Start Date','End Date'],'page':1,'limit':30,'sort':'Award Amount','order':'desc'})
                rows=payload.get('results',[]);scope='Keyword-matched disclosed awards, amounts in USD. Matching is not proof that an award belongs to a particular listed parent company.'
            elif source=='ted':
                name=public_term(term);url='https://api.ted.europa.eu/v3/notices/search'
                payload=request(url,{'query':'FT="'+name+'"','fields':['publication-number','notice-title','publication-date','organisation-name-buyer'],'page':1,'limit':30,'scope':'ALL'})
                rows=payload.get('notices',payload.get('results',[]));scope='Matching published procurement notices; a notice does not necessarily represent an awarded contract or realised revenue.'
            elif source=='kraken':
                pair=(term or 'XBTEUR').upper()
                if not re.fullmatch(r'[A-Z0-9]{5,18}',pair):raise ValueError('Use a public market pair, for example XBTEUR.')
                url='https://api.kraken.com/0/public/Ticker?'+urllib.parse.urlencode({'pair':pair});payload=request(url)
                if payload.get('error'):raise ValueError('; '.join(payload['error']))
                rows=[{'pair':k,'last':v['c'][0],'bid':v['b'][0],'ask':v['a'][0],'volume_24h':v['v'][1]} for k,v in payload.get('result',{}).items()];scope='Public exchange quotes, not wallet balances or a consolidated best execution price.'
            series=sorted(series,key=lambda r:r['date'])
            result={'source':source,'name':title,'description':desc,'query':term,'rows':rows[-100:] if source in ('fred','krakenhistory') else rows[:100],'series':series,'source_url':url,'documentation':docs,'scope':scope,'total_rows':len(rows),'truncated':len(rows)>100,'retrieved_at':store.now()}
            store.put('source-status',{'ok':True,'checked':store.now()},source,audit=False)
            store.execute('INSERT OR REPLACE INTO public_cache VALUES(?,?,?,?)',(key,source,result['retrieved_at'],json.dumps(result,allow_nan=False)))
            return result
        except Exception as e:
            store.put('source-status',{'ok':False,'checked':store.now(),'error':str(e)[:250]},source,audit=False)
            if cached:return {**old,'cached':True,'stale':True,'warning':'Refresh failed; last cached evidence retained: '+str(e)[:250]}
            raise ValueError(title+' could not supply this query: '+str(e)[:250])

def history():
    return [{**json.loads(r['payload']),'retrieved_at':r['retrieved']} for r in store.rows('SELECT * FROM public_cache ORDER BY retrieved DESC LIMIT 100')]
