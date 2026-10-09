"""Encrypted full backups and a verified restore into a separate directory."""
import hashlib
import io
import json
import os
import secrets
import sqlite3
import tempfile
import threading
import zipfile
from pathlib import Path,PurePosixPath
from . import store

PRIVATE=('portfolio.json','spending.json','receipts.json','notes.md','history.csv','history_accounts.csv','imports.json','inbox.json','ui.json','chats.json','settings.json')
_lock=threading.Lock()
MAGIC=b'WEALTHBACKUP2\n'

def owner_key():
    path=store.ROOT/'cache'/'backup-key.dpapi'
    path.parent.mkdir(exist_ok=True)
    from chatgpt_auth import _protect
    if not path.exists():
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(_protect(secrets.token_bytes(32)))
    return _protect(path.read_bytes(),decrypt=True)

def derive(password,salt):
    import hashlib
    if not isinstance(password,str) or len(password)<10:raise ValueError('Portable backup passwords need at least 10 characters.')
    return hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)

def folder():
    path=store.ROOT/'backups'/'complete';path.mkdir(parents=True,exist_ok=True);return path

def create(password=None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not _lock.acquire(False):raise ValueError('A complete backup is already running.')
    try:
        stream=io.BytesIO();manifest=[];total=0
        import app,spending,receipts
        # App mutations follow portfolio -> spending -> receipt lock order.
        with app.cfg_lock,spending.lock,receipts.lock, tempfile.TemporaryDirectory() as temporary:
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                paths=[store.ROOT/n for n in PRIVATE if (store.ROOT/n).is_file()]
                attachments=store.ROOT/'attachments'
                if attachments.exists():paths += [p for p in attachments.rglob('*') if p.is_file() and not p.is_symlink()]
                # Credential refresh tokens are deliberately outside a financial backup.
                databases=[store.ROOT/'cache'/'intelligence.sqlite3',store.DB]
                for original in databases:
                    if not original.exists():continue
                    dest=Path(temporary)/original.name
                    source=sqlite3.connect(str(original));target=sqlite3.connect(str(dest))
                    try:source.backup(target)
                    finally:target.close();source.close()
                    paths.append(dest)
                for p in paths:
                    if p.is_symlink():continue
                    name='cache/'+p.name if p.parent==Path(temporary) else p.relative_to(store.ROOT).as_posix()
                    raw=p.read_bytes();total+=len(raw)
                    if total>512*1024*1024:raise ValueError('Backup exceeds 512 MB. Archive old attachments separately before retrying.')
                    manifest.append({'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()});z.writestr(name,raw)
                z.writestr('manifest.json',json.dumps({'version':2,'created':store.now(),'files':manifest},indent=2))
        salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12);portable=bool(password)
        header=json.dumps({'version':2,'mode':'password' if portable else 'windows-owner' if os.name=='nt' else 'local-owner','salt':salt.hex(),'nonce':nonce.hex(),'created':store.now(),'files':len(manifest),'bytes':total},sort_keys=True).encode()
        key=derive(password,salt) if portable else owner_key()
        encrypted=AESGCM(key).encrypt(nonce,stream.getvalue(),header)
        name=store.now().replace(':','').replace('+','_')+'-'+secrets.token_hex(3)+'.wealthbackup'
        target=folder()/name;target.write_bytes(MAGIC+str(len(header)).encode()+b'\n'+header+encrypted)
        store.event('backup','Complete encrypted backup created',{'name':name,'files':len(manifest),'mode':json.loads(header)['mode']})
        return {'name':name,'files':len(manifest),'bytes':total,'mode':json.loads(header)['mode'],'scope':'Financial files, evidence attachments and SQLite databases. Settings are encrypted inside the archive. OAuth session tokens are excluded. Local-owner backups require the saved owner key; use a password for portable backups.'}
    finally:_lock.release()

def read_header(path):
    with path.open('rb') as f:
        if f.read(len(MAGIC))!=MAGIC:raise ValueError('Unsupported backup format.')
        length=f.readline(12)
        try:n=int(length)
        except ValueError:raise ValueError('Invalid backup header.')
        if not 0<n<8192:raise ValueError('Invalid backup header size.')
        header=f.read(n)
    return json.loads(header)

def listing():
    result=[]
    for p in sorted(folder().glob('*.wealthbackup'),reverse=True):
        try:result.append({'name':p.name,'size':p.stat().st_size,**read_header(p)})
        except Exception:result.append({'name':p.name,'error':'Backup header cannot be read.'})
    return result

def restore_preview(name,password=None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if Path(name).name!=name or not name.endswith('.wealthbackup'):raise ValueError('Choose a listed complete backup.')
    path=folder()/name
    with path.open('rb') as f:
        if f.read(len(MAGIC))!=MAGIC:raise ValueError('Unsupported backup format.')
        n=int(f.readline(12))
        if not 0<n<8192:raise ValueError('Invalid header.')
        header=f.read(n);cipher=f.read(512*1024*1024+1)
    meta=json.loads(header);key=derive(password,bytes.fromhex(meta['salt'])) if meta['mode']=='password' else owner_key()
    try:raw=AESGCM(key).decrypt(bytes.fromhex(meta['nonce']),cipher,header)
    except Exception:raise ValueError('Backup authentication failed. Check the password or the Windows account/owner key.')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest=json.loads(z.read('manifest.json'));members=z.infolist()
        if len(members)>20000 or sum(m.file_size for m in members)>512*1024*1024:raise ValueError('Backup contents exceed supported limits.')
        expected={r['name']:r for r in manifest['files']}
        if len(expected)!=len(manifest['files']) or set(z.namelist())!=set(expected)|{'manifest.json'}:raise ValueError('Backup manifest does not match its contents.')
        verified=[]
        for info in members:
            p=PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename or ':' in info.filename:raise ValueError('Unsafe path in backup.')
            if info.filename=='manifest.json':continue
            if not (info.filename in PRIVATE or info.filename.startswith('attachments/') or info.filename in ('cache/intelligence.sqlite3','cache/workspace.sqlite3')):raise ValueError('Unexpected file in financial backup.')
            data=z.read(info);item=expected[info.filename]
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Backup evidence failed integrity checks.')
            verified.append((info.filename,data))
        portfolio=next((json.loads(data) for n,data in verified if n=='portfolio.json'),None)
        if not portfolio or not all(k in portfolio for k in ('accounts','managed','savings','debts')):raise ValueError('Backup has no valid portfolio.')
        dest=store.ROOT/'backups'/('restore-preview-'+secrets.token_hex(6));dest.mkdir()
        for n,data in verified:
            target=dest.joinpath(*PurePosixPath(n).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        for db in (dest/'cache').glob('*.sqlite3') if (dest/'cache').exists() else []:
            c=sqlite3.connect(str(db))
            try:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored database failed integrity checks.')
            finally:c.close()
    store.event('restore','Backup verified in a separate restore folder',{'backup':name,'folder':dest.name,'files':len(verified)})
    return {'verified':True,'folder':'backups/'+dest.name,'files':len(verified),'manifest':manifest['files'],'scope':'Verified separate copy only. Current financial data has not been replaced.'}
