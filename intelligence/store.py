import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'cache' / 'intelligence.sqlite3'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, entity TEXT NOT NULL, source TEXT NOT NULL, retrieved_at TEXT NOT NULL, period TEXT, currency TEXT, filing_date TEXT, url TEXT, digest TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(kind,entity,source,digest));
CREATE INDEX IF NOT EXISTS observation_lookup ON observations(kind,entity,id DESC);
CREATE TABLE IF NOT EXISTS prices(symbol TEXT, date TEXT, source TEXT, close REAL NOT NULL, currency TEXT, adjusted INTEGER, retrieved_at TEXT, PRIMARY KEY(symbol,date,source));
CREATE TABLE IF NOT EXISTS filings(accession TEXT PRIMARY KEY,cik TEXT,form TEXT,period TEXT,filed TEXT,url TEXT,payload TEXT);
CREATE TABLE IF NOT EXISTS holdings(accession TEXT,security TEXT,name TEXT,cusip TEXT,shares REAL,value REAL,share_type TEXT,option_type TEXT,PRIMARY KEY(accession,security));
CREATE TABLE IF NOT EXISTS insider_trades(id TEXT PRIMARY KEY,accession TEXT,symbol TEXT,payload TEXT);
CREATE TABLE IF NOT EXISTS managers(cik TEXT PRIMARY KEY,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS watchlist(symbol TEXT PRIMARY KEY,name TEXT,note TEXT,thesis TEXT,added TEXT);
CREATE TABLE IF NOT EXISTS alert_rules(id TEXT PRIMARY KEY,type TEXT,symbol TEXT,threshold REAL,enabled INTEGER NOT NULL,payload TEXT);
CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,type TEXT,symbol TEXT,title TEXT,detail TEXT,created_at TEXT,seen INTEGER NOT NULL DEFAULT 0,payload TEXT);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,signal_id TEXT,channel TEXT,status TEXT,created_at TEXT,UNIQUE(signal_id,channel));
CREATE TABLE IF NOT EXISTS jobs(name TEXT PRIMARY KEY,started_at TEXT,finished_at TEXT,status TEXT,error TEXT,cursor TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,payload TEXT NOT NULL);
'''

@contextmanager
def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c = sqlite3.connect(str(DB),timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA busy_timeout=30000')
    # Run schema setup once per database, rather than writing on every read.
    if c.execute('PRAGMA user_version').fetchone()[0] < 1:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO migrations VALUES(1,?)',(now(),))
        c.execute('PRAGMA user_version=1')
        c.commit()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args)]

def execute(sql,args=()):
    with connect() as c: c.execute(sql,args)

def setting(key,default=None):
    r=rows('SELECT payload FROM settings WHERE key=?',(key,))
    return json.loads(r[0]['payload']) if r else default

def set_setting(key,value):
    execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

def observe(kind,entity,payload,source,url=None,period=None,currency=None,filing_date=None):
    raw=json.dumps(payload,sort_keys=True,default=str,allow_nan=False)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO observations(kind,entity,source,retrieved_at,period,currency,filing_date,url,digest,payload) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (kind,entity,source,now(),period,currency,filing_date,url,digest,raw))
        # Identical data still has a new successful retrieval time.
        c.execute('UPDATE observations SET retrieved_at=? WHERE kind=? AND entity=? AND source=? AND digest=?',(now(),kind,entity,source,digest))

def latest(kind,entity,days=2):
    r=rows('SELECT * FROM observations WHERE kind=? AND entity=? ORDER BY retrieved_at DESC,id DESC LIMIT 1',(kind,entity))
    if not r: return None
    x=r[0]; x['data']=json.loads(x.pop('payload'));x.pop('digest')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(x['retrieved_at'])).total_seconds()/86400
    x['freshness']='stale' if age>days else 'current';x['age_days']=round(age,2)
    return x

def history(kind,entity,limit=100):
    return [{**r,'data':json.loads(r['payload'])} for r in rows('SELECT * FROM observations WHERE kind=? AND entity=? ORDER BY retrieved_at DESC,id DESC LIMIT ?',(kind,entity,limit))]

def signal(type,symbol,title,detail,evidence):
    raw=json.dumps(evidence,sort_keys=True,default=str)
    ident=hashlib.sha256((type+symbol+raw).encode()).hexdigest()[:24]
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?,?,0,?)',(ident,type,symbol,title,detail,now(),raw))
        # An outbox is ready for future notification adapters; no emails are sent.
        c.execute("INSERT OR IGNORE INTO deliveries(signal_id,channel,status,created_at) VALUES(?,'in-app','ready',?)",(ident,now()))
    return ident
