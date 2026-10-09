import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'cache' / 'workspace.sqlite3'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(kind,id));
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL,modified REAL NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,account TEXT NOT NULL,date TEXT NOT NULL,type TEXT NOT NULL,instrument TEXT,currency TEXT NOT NULL,amount REAL,units REAL,source_id TEXT,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ledger_account_date ON ledger(account,date);
CREATE TABLE IF NOT EXISTS public_cache(id TEXT PRIMARY KEY,source TEXT NOT NULL,retrieved TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,type TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL,seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,created TEXT NOT NULL,action TEXT NOT NULL,kind TEXT NOT NULL,record_id TEXT NOT NULL,before_json TEXT,after_json TEXT);
'''

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=30000')
    if c.execute('PRAGMA user_version').fetchone()[0] < 1:
        c.executescript(SCHEMA)
        c.execute('PRAGMA user_version=1')
        c.commit()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally: c.close()

def rows(sql, args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql, args)]

def execute(sql, args=()):
    with connect() as c: c.execute(sql, args)

def records(kind):
    return [{**json.loads(r['payload']), 'id':r['id'], 'updated':r['updated']} for r in rows('SELECT * FROM records WHERE kind=? ORDER BY updated DESC,id',(kind,))]

def record(kind, ident, default=None):
    found = rows('SELECT payload FROM records WHERE kind=? AND id=?',(kind,ident))
    return json.loads(found[0]['payload']) if found else default

def put(kind, data, ident=None, audit=True):
    ident = ident or str(data.get('id') or uuid.uuid4().hex[:20])
    if len(ident)>200: raise ValueError('Record identifier is too long.')
    payload = {k:v for k,v in data.items() if k not in ('id','updated')}
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(raw)>100000: raise ValueError('Record is too large.')
    with connect() as c:
        old = c.execute('SELECT payload FROM records WHERE kind=? AND id=?',(kind,ident)).fetchone()
        c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)',(kind,ident,raw,now()))
        if audit:c.execute('INSERT INTO audit(created,action,kind,record_id,before_json,after_json) VALUES(?,?,?,?,?,?)',(now(),'save',kind,ident,old['payload'] if old else None,raw))
    return {**payload,'id':ident}

def delete(kind,ident,audit=True):
    with connect() as c:
        old=c.execute('SELECT payload FROM records WHERE kind=? AND id=?',(kind,ident)).fetchone()
        if old:
            c.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,ident))
            if audit:c.execute('INSERT INTO audit(created,action,kind,record_id,before_json) VALUES(?,?,?,?,?)',(now(),'delete',kind,ident,old['payload']))

def finite(value, minimum=None, maximum=None, nullable=False):
    if nullable and (value is None or value==''): return None
    if isinstance(value,bool): raise ValueError('Enter a number.')
    try: value=float(value)
    except (TypeError,ValueError): raise ValueError('Enter a number.')
    if not math.isfinite(value) or minimum is not None and value<minimum or maximum is not None and value>maximum:
        raise ValueError('Number is outside the supported range.')
    return value

def iso(value,nullable=False):
    if nullable and not value:return ''
    return date.fromisoformat(str(value)).isoformat()

def event(kind,title,evidence):
    import hashlib
    raw=json.dumps(evidence,sort_keys=True,allow_nan=False)
    ident=hashlib.sha256((kind+raw).encode()).hexdigest()[:24]
    execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,0)',(ident,kind,title,now(),raw))
    return ident
