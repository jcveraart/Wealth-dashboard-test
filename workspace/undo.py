"""Financial import snapshots extend the existing Undo; later planning edits stay intact."""
import json
import re
from . import store
KINDS=('fundholding','esef-facts')

def path(bid):
    if not re.fullmatch(r'\d{8}-\d{6}-\d{6}',str(bid)):raise ValueError('Invalid Undo reference.')
    return store.ROOT/'backups'/('workflow-import-'+bid+'.json')

def snapshot(bid):
    with store.connect() as c:
        data={'ledger':[dict(r) for r in c.execute('SELECT * FROM ledger')],
          'records':[dict(r) for r in c.execute("SELECT * FROM records WHERE kind IN ('fundholding','esef-facts')")]}
    file=path(bid);file.parent.mkdir(exist_ok=True);file.write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    for old in sorted(file.parent.glob('workflow-import-*.json'))[:-100]:old.unlink()

def restore(bid):
    restore_chat(bid)
    file=path(bid)
    if not file.exists():return
    data=json.loads(file.read_text(encoding='utf-8'))
    with store.connect() as c:
        c.execute('DELETE FROM ledger');c.execute("DELETE FROM records WHERE kind IN ('fundholding','esef-facts')")
        for r in data['ledger']:c.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ('id','account','date','type','instrument','currency','amount','units','source_id','payload')))
        for r in data['records']:c.execute('INSERT INTO records VALUES(?,?,?,?)',tuple(r[k] for k in ('kind','id','payload','updated')))
        c.execute('INSERT INTO audit(created,action,kind,record_id) VALUES(?,?,?,?)',(store.now(),'undo-import','financial-evidence',bid))

def chat_path(bid):return path(bid).with_name('workflow-chat-'+str(bid)+'.json')

def remember_chat(bid,kind,ident,before,after):
    file=chat_path(bid);rows=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
    key=kind+'|'+ident
    rows[key]={'kind':kind,'id':ident,'before':rows.get(key,{}).get('before',before),'after':after}
    file.write_text(json.dumps(rows,allow_nan=False),encoding='utf-8')

def restore_chat(bid,check_only=False):
    file=chat_path(bid)
    if not file.exists():return
    rows=json.loads(file.read_text(encoding='utf-8')).values()
    for r in rows:
        if store.record(r['kind'],r['id'])!=r['after']:raise ValueError('A workflow record changed again after this chat. Review it before undoing the earlier change.')
    if check_only:return
    for r in rows:
        if r['before'] is None:store.delete(r['kind'],r['id'])
        else:store.put(r['kind'],{k:v for k,v in r['before'].items() if k!='id'},r['id'])
