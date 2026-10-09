"""Small, locally cached AI briefings based only on the selected portfolio facts."""
import hashlib,json,re,threading,time
from datetime import datetime
import extras

_running=set()
_lock=threading.Lock()

def facts(state,account='',asset='all'):
    def asset_class(p):
        category=(p.get('category') or '').lower()
        if re.search('bond|obligat|treasur|money market|geldmarkt',category):return 'bonds'
        if re.search('crypto|bitcoin|ether',category):return 'crypto'
        if re.search('gold|silver|commod|real estate|reit|property',category):return 'other'
        return 'shares'
    rows=[p for p in state.get('positions',[]) if (not account or p.get('account')==account) and (asset=='all' or asset_class(p)==asset)]
    managed=state.get('managed') or {}
    if asset in ('all','shares') and managed.get('value') is not None and not any(p.get('managed') for p in state.get('positions',[])) and (not account or account==managed.get('name')):
        rows.append({'name':managed.get('name','Managed portfolio'),'value':managed['value'],'region':None,'category':'Managed portfolio'})
    total=sum(p.get('value') or 0 for p in rows)
    result=[]
    priced=[p for p in rows if p.get('live') and p.get('day_change') is not None]
    if priced:
        top=max(priced,key=lambda p:p['day_change']);bottom=min(priced,key=lambda p:p['day_change'])
        for row,label,sign in [(top,'Largest positive contribution today',1),(bottom,'Largest negative contribution today',-1)]:
            if row['day_change']*sign>0:
                result.append({'text':f"{label}: {row['name']} ({row['day_change']:+,.0f} EUR).",'id':row.get('isin') or 'n:'+row['name'].strip().lower()})
    if total>0 and rows:
        top=max(rows,key=lambda p:p.get('value') or 0)
        result.append({'text':f"{top['name']} is the largest holding in this selection, {(top.get('value',0)/total*100):.1f}% of its invested value.",'id':top.get('isin') or 'n:'+top['name'].strip().lower()})
    unknown=sum(1 for p in rows if not p.get('region') or p.get('region','').lower() in ('other','unknown','unclassified'))
    if unknown:result.append({'text':f"Regional exposure still needs classification for {unknown} holdings in this selection.",'id':None})
    return result[:4]

def peek(state,account='',asset='all'):
    ident=hashlib.sha256(json.dumps([account,asset],ensure_ascii=False).encode()).hexdigest()[:20]
    old=extras.read(extras.CACHE/'investment-notes'/f'{ident}.json',{})
    if old.get('items') and time.time()-old.get('at',0)<4*3600 and old.get('date')==datetime.now().date().isoformat():return {**old,'updating':ident in _running}
    return {'items':facts(state,account,asset)[:2],'by':'facts','account':account,'asset':asset,'updating':False}

def briefing(state,account='',asset='all',exe=None,key=None,force=False):
    items=facts(state,account,asset)
    ident=hashlib.sha256(json.dumps([account,asset],ensure_ascii=False).encode()).hexdigest()[:20]
    path=extras.CACHE/'investment-notes'/f'{ident}.json'
    old=extras.read(path,{})
    if not force and time.time()-old.get('at',0)<4*3600 and old.get('date')==datetime.now().date().isoformat():return {**old,'updating':ident in _running}
    out={'items':items[:2],'by':'facts','time':extras.now(),'at':time.time(),'date':datetime.now().date().isoformat(),'account':account,'asset':asset,'prices_at':state.get('status',{}).get('last_refresh'),'updating':False}
    path.parent.mkdir(parents=True,exist_ok=True)
    with _lock:
        if ident in _running:return {**old,'updating':True} if old else {**out,'updating':True}
        extras.write(path,out)
        if items and (exe or key):
            _running.add(ident);out['updating']=True
            threading.Thread(target=_phrase,args=(ident,path,out,items,exe,key),daemon=True).start()
    return out

def _phrase(ident,path,out,items,exe,key):
    import spending
    try:
        rules='Choose up to two useful portfolio observations. Return only a JSON array of fact indices (integers). Do not create any new figures, research, predictions or recommendations. Prefer one performance observation and one allocation observation when available.'
        answer=spending.json_from(spending.run_ai(json.dumps(items,ensure_ascii=False),rules,exe=exe,api_key=key,kind='briefing',level='quick'))
        chosen=list(dict.fromkeys(i for i in answer if type(i) is int and 0<=i<len(items)))[:2]
        if chosen:extras.write(path,{**out,'by':'claude','items':[items[i] for i in chosen],'updating':False})
    except Exception as error:extras.write(path,{**out,'error':str(error)[:160],'updating':False})
    finally:
        with _lock:_running.discard(ident)
