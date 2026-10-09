"""Incremental EDGAR ingestion, source-linked filings and conservative ownership signals."""
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import date,timedelta
from . import store
from .data import HTTP

def local(el):return el.tag.rsplit('}',1)[-1]
def text(el,name,default=''):
    for x in el.iter():
        if local(x)==name:
            v=next((v.text for v in x.iter() if local(v)=='value' and v.text),None)
            return (v or x.text or default).strip()
    return default
def num(v):
    try:return float(v)
    except (TypeError,ValueError):return None

def lookup(symbol):
    cached=store.latest('sec_symbols','all',days=30)
    if not cached or cached['freshness']=='stale':
        url='https://www.sec.gov/files/company_tickers.json'
        raw=json.loads(HTTP.get(url,sec=True));store.observe('sec_symbols','all',raw,'SEC EDGAR',url);cached=store.latest('sec_symbols','all',30)
    ticker=symbol.upper().replace('-','.')
    hit=next((r for r in cached['data'].values() if r['ticker'].upper()==ticker),None)
    return str(hit['cik_str']) if hit else None

def submissions(cik,history=True):
    url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
    raw=json.loads(HTTP.get(url,sec=True));recent=raw.get('filings',{}).get('recent',{})
    packs=[recent]
    if history:
        for old in raw.get('filings',{}).get('files',[])[:8]:
            if old.get('filingTo','')>=(date.today()-timedelta(days=365*5)).isoformat():
                key='sec_submissions_history';cached=store.latest(key,old['name'],days=36500)
                if cached:packs.append(cached['data'])
                else:
                    oldurl='https://data.sec.gov/submissions/'+old['name'];r=json.loads(HTTP.get(oldurl,sec=True))
                    store.observe(key,old['name'],r,'SEC EDGAR',oldurl);packs.append(r)
    out={}
    for pack in packs:
        for i,acc in enumerate(pack.get('accessionNumber',[])):
            row={k:vs[i] for k,vs in pack.items() if isinstance(vs,list) and i<len(vs)}
            row['cik']=str(int(cik));row['url']=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{row.get('primaryDocument','')}"
            out[acc]=row
    return raw,sorted(out.values(),key=lambda r:r.get('filingDate',''),reverse=True)

def save_filing(r,payload=None):
    store.execute('INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?)',(r['accessionNumber'],r['cik'],r['form'],r.get('reportDate'),r['filingDate'],r['url'],json.dumps(payload or r)))

def parse_13f(raw,filed):
    root=ET.fromstring(raw);out={};mult=1000 if filed<'2023-01-03' else 1
    for row in root.iter():
        if local(row)!='infoTable':continue
        cusip=text(row,'cusip');opt=text(row,'putCall');typ=text(row,'sshPrnamtType');key='|'.join([cusip,typ,opt])
        if not cusip:continue
        r=out.setdefault(key,{'security':key,'cusip':cusip,'name':text(row,'nameOfIssuer'),'class':text(row,'titleOfClass'),
              'share_type':typ,'option_type':opt,'value':0.,'shares':0.})
        r['value']+=(num(text(row,'value')) or 0)*mult;r['shares']+=num(text(row,'sshPrnamt')) or 0
    return list(out.values())

def parse_form4(raw,symbol,filing):
    root=ET.fromstring(raw);owners=[x for x in root.iter() if local(x)=='reportingOwner']
    # Joint owners are retained together; avoid counting the same transaction twice.
    names=' / '.join(text(x,'rptOwnerName') for x in owners)
    roles=' / '.join(filter(None,[text(x,'officerTitle') or ('Director' if text(x,'isDirector') in ('1','true') else '10% owner' if text(x,'isTenPercentOwner') in ('1','true') else 'Other') for x in owners]))
    footnotes={x.attrib.get('id'):(x.text or '') for x in root.iter() if local(x)=='footnote'}
    out=[]
    for i,row in enumerate(x for x in root.iter() if local(x) in ('nonDerivativeTransaction','derivativeTransaction')):
        derivative=local(row)=='derivativeTransaction';code=text(row,'transactionCode');shares=num(text(row,'transactionShares'));price=num(text(row,'transactionPricePerShare'))
        refs=[footnotes.get(x.attrib.get('id'),'') for x in row.iter() if local(x)=='footnoteId']
        note=' '.join(refs);plan=text(root,'aff10b5One') in ('1','true') or any(w in note.lower() for w in ('10b5-1','10b5 1','automatic','trading plan'))
        label={'P':'Purchase','S':'Sale','A':'Award / grant','M':'Option exercise / conversion','C':'Conversion','F':'Tax withholding','G':'Gift','D':'Disposition to issuer','J':'Other'}.get(code,'Other')
        eligible=code in ('P','S') and not derivative and not plan
        out.append({'id':hashlib.sha256((filing['accessionNumber']+':'+str(i)).encode()).hexdigest()[:24],
          'symbol':symbol,'insider':names,'role':roles,'code':code,'type':label,'derivative':derivative,'automatic_plan':plan,
          'open_market':eligible,'classification':'Open-market code; no disclosed plan' if eligible else 'Disclosed plan' if plan else 'Derivative' if derivative else label,
          'shares':shares,'price':price,'value':shares*price if shares is not None and price is not None else None,
          'ownership_after':num(text(row,'sharesOwnedFollowingTransaction')),'ownership_type':text(row,'directOrIndirectOwnership'),
          'date':text(row,'transactionDate'),'filed':filing['filingDate'],'currency':'USD','url':filing['url'],
          'footnotes':note,'source':'SEC Form 4','accession':filing['accessionNumber']})
    return out

def company(symbol,cik=None):
    cik=cik or lookup(symbol)
    if not cik:return {'cik':None,'coverage':'No SEC issuer match; international issuers may lack US disclosures.'}
    raw,filings=submissions(cik)
    for r in filings[:150]:save_filing(r)
    errors=[]
    # Recent issuer transactions; process only accessions without a parsed Form 4 observation.
    cutoff=(date.today()-timedelta(days=180)).isoformat()
    for r in [r for r in filings if r['form'] in ('4','4/A') and r['filingDate']>=cutoff][:60]:
        if store.latest('form4',r['accessionNumber'],36500):continue
        try:
            url=r['url'];parts=url.split('/');parts=[p for p in parts if not p.startswith('xsl')];url='/'.join(parts)
            xml=HTTP.get(url,sec=True);trades=parse_form4(xml,symbol,r)
            with store.connect() as c:
                c.execute('DELETE FROM insider_trades WHERE accession=?',(r['accessionNumber'],))
                for t in trades:c.execute('INSERT OR REPLACE INTO insider_trades VALUES(?,?,?,?)',(t['id'],r['accessionNumber'],symbol,json.dumps(t)))
            store.observe('form4',r['accessionNumber'],trades,'SEC EDGAR',url,filing_date=r['filingDate'])
        except Exception as e:errors.append(str(e));break
    url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
    facts=json.loads(HTTP.get(url,sec=True));store.observe('sec_facts',symbol,facts,'SEC EDGAR',url)
    corporate=[r for r in filings if r['form'] not in ('4','4/A','3','3/A','5','5/A')][:60]
    for r in corporate:save_filing(r)
    return {'cik':str(cik),'name':raw.get('name'),'sic':raw.get('sicDescription'),'filings':corporate,'errors':errors}

def manager(cik):
    raw,filings=submissions(cik)
    relevant=[r for r in filings if r['form'] in ('13F-HR','13F-HR/A')][:20]
    errors=[]
    for r in reversed(relevant):
        if store.latest('13f',r['accessionNumber'],36500):continue
        folder=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{r['accessionNumber'].replace('-','')}/"
        try:
            primary_url=folder+r.get('primaryDocument','').rsplit('/',1)[-1]
            primary=HTTP.get(primary_url,sec=True);doc=ET.fromstring(primary)
            amendment=text(doc,'amendmentType')
            items=json.loads(HTTP.get(folder+'index.json',sec=True)).get('directory',{}).get('item',[])
            tables=[]
            for item in items:
                name=item['name']
                if name.lower().endswith('.xml') and name!=r.get('primaryDocument','').rsplit('/',1)[-1]:
                    xml=HTTP.get(folder+name,sec=True)
                    if 'infoTable' in xml:tables.extend(parse_13f(xml,r['filingDate']))
            if not tables:raise RuntimeError('No disclosed information table was available.')
            # Store every amendment. Additions-only amendments cannot replace a full quarter.
            payload={**r,'amendment_type':amendment,'holdings':tables,'value_units':'USD dollars','delayed':True}
            save_filing(r,payload)
            with store.connect() as c:
                for t in tables:c.execute('INSERT OR REPLACE INTO holdings VALUES(?,?,?,?,?,?,?,?)',(r['accessionNumber'],t['security'],t['name'],t['cusip'],t['shares'],t['value'],t['share_type'],t['option_type']))
            store.observe('13f',r['accessionNumber'],payload,'SEC EDGAR',r['url'],r.get('reportDate'),'USD',r['filingDate'])
        except Exception as e:errors.append(str(e));break
    return {'cik':str(cik),'name':raw.get('name'),'errors':errors,'filings':len(relevant)}

def manager_history(cik):
    filings=store.rows("SELECT * FROM filings WHERE cik=? AND form IN ('13F-HR','13F-HR/A') ORDER BY period DESC,filed DESC",(str(int(cik)),))
    quarters={}
    for f in filings:
        payload=json.loads(f['payload'])
        if payload.get('amendment_type')=='NEW HOLDINGS':continue
        if not payload.get('holdings'):continue
        quarters.setdefault(f['period'],f)
    out=[]
    for quarter,f in quarters.items():
        h=store.rows('SELECT * FROM holdings WHERE accession=?',(f['accession'],));total=sum(r['value'] for r in h)
        for r in h:r['weight_pct']=r['value']/total*100 if total else None
        out.append({**f,'payload':None,'total_usd':total,'holdings':sorted(h,key=lambda r:-r['value'])})
    for i,cur in enumerate(out):
        previous={r['security']:r for r in out[i+1]['holdings']} if i+1<len(out) else None
        cur['changes']=changes(cur['holdings'],previous) if previous is not None else []
    return out

def changes(holdings,previous):
    current={r['security']:r for r in holdings};out=[]
    for k,r in current.items():
        b=previous.get(k);pct=(r['shares']/b['shares']-1)*100 if b and b['shares'] else None
        out.append({**r,'move':'new' if not b else 'added' if pct is not None and pct>.01 else 'reduced' if pct is not None and pct<-.01 else 'unchanged','change_pct':pct,
                    'caveat':'Share-count changes may include splits, mergers or reporting changes.'})
    for k,r in previous.items():
        if k not in current:out.append({**r,'move':'exit','change_pct':-100,'weight_pct':0})
    return sorted(out,key=lambda r:-r['value'])
