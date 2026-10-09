"""Local-only scheduled upkeep, independent of the browser and AI providers."""
import threading
import time
from datetime import datetime,timezone
from . import store
_started=False
_lock=threading.Lock()

def due(stamp,seconds):
    try:return (datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()>=seconds
    except (TypeError,ValueError):return True

def tick():
    from . import service,backups,cashflow,feeds
    prefs=store.record('prefs','maintenance',{})
    # A failed job is retried later; last-success dates only advance on success.
    if due(prefs.get('backup_at'),7*86400):
        try:
            result=backups.create();prefs['backup_at']=store.now();prefs.pop('backup_error',None)
        except Exception as e:prefs['backup_error']=str(e)[:200]
    if due(prefs.get('digest_at'),7*86400):
        digest=service.digest();stamp=store.now();store.put('briefing',digest,stamp[:10]);prefs['digest_at']=stamp
        store.event('briefing','Your weekly local briefing is ready',{'date':stamp[:10]})
    if due(prefs.get('signals_at'),3600):
        from .assets import record_rates
        record_rates()
        for r in cashflow.recurring(service.spending_data()):
            if r['active'] and abs(r['change_eur'])>=.01:
                store.event('payment-change',r['name']+' recurring amount changed',{'pattern':r['id'],'change_eur':r['change_eur'],'date':r['last_date'],'evidence_ids':r['evidence_ids']})
        for r in service.review()['tasks']:
            if r['kind'] in ('claim','policy','decision') and r['priority']==1:store.event('due',r['title']+' is due for review',{'kind':r['kind'],'target':r['target'],'detail':r['detail']})
        prefs['signals_at']=store.now()
    if due(prefs.get('feeds_at'),6*3600):
        try:feeds.refresh();prefs['feeds_at']=store.now();prefs.pop('feeds_error',None)
        except Exception as e:prefs['feeds_error']=str(e)[:200]
    store.put('prefs',prefs,'maintenance',audit=False)
    return prefs

def start():
    global _started
    with _lock:
        if _started:return
        _started=True
    def run():
        time.sleep(20)
        while True:
            try:tick()
            except Exception:pass
            time.sleep(900)
    threading.Thread(target=run,name='local-workflow-upkeep',daemon=True).start()
