"""Evidence indexing and a local intake folder. Intake prepares a review, never invents payments."""
import base64
import hashlib
import json
import mimetypes
import threading
import time
from pathlib import Path
from . import store

ALLOWED={'.pdf','.png','.jpg','.jpeg','.webp','.csv','.txt','.xlsx','.xls','.html','.xhtml','.xml','.docx','.zip'}
INBOX=store.ROOT/'import-inbox'
MAX_FILE=40*1024*1024
_started=False
_scan_lock=threading.Lock()

def extract_text(name,raw):
    suffix=Path(name).suffix.lower()
    if suffix in ('.txt','.csv','.html','.xhtml','.xml'):
        from ai import decode_text
        text=decode_text(raw)
        if suffix in ('.html','.xhtml','.xml'):
            from html.parser import HTMLParser
            class Text(HTMLParser):
                def __init__(self):super().__init__();self.bits=[]
                def handle_data(self,s):self.bits.append(s)
            parser=Text();parser.feed(text);text=' '.join(parser.bits)
        return text[:100000],'Text extracted locally'
    if suffix=='.pdf':
        try:
            import io
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:return '', 'Encrypted PDF; upload an unlocked copy.'
            text='\n'.join((p.extract_text() or '') for p in reader.pages[:100])[:100000]
            return text,'Text extracted locally' if text.strip() else 'Scanned document; image/OCR extraction is needed.'
        except ImportError:return '', 'Install the optional PDF reader for local text search.'
        except Exception:return '', 'PDF text could not be read locally; original evidence is retained.'
    if suffix=='.docx':
        import io,zipfile,xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info=z.getinfo('word/document.xml')
            if info.file_size>8*1024*1024:raise ValueError('Document text is too large.')
            root=ET.fromstring(z.read(info));return ' '.join(root.itertext())[:100000],'Text extracted locally'
    return '', 'Image or spreadsheet; use the existing importer for extraction.'

def index_sources():
    import receipts
    count=0
    for src in receipts.read()['sources']:
        ident=src['id']
        old=store.record('document',ident)
        if old:continue
        try:
            path,item=receipts.source(ident)
            if path.stat().st_size>MAX_FILE:continue
            text,status=extract_text(item['name'],path.read_bytes())
            store.put('document',{'name':item['name'],'source_id':ident,'text':text[:80000],'status':status,'kind':item.get('kind','document'),'media_type':item.get('media_type'),'indexed_at':store.now()},ident)
            count+=1
        except Exception:continue
    return count

def scan():
    if not _scan_lock.acquire(False):return {'busy':True}
    try:
        INBOX.mkdir(exist_ok=True)
        found=0;errors=[]
        for path in sorted(INBOX.iterdir(),key=lambda p:p.name.lower())[:400]:
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in ALLOWED:continue
            stat=path.stat()
            if stat.st_size>MAX_FILE or time.time()-stat.st_mtime<5:continue
            raw=path.read_bytes();ident=hashlib.sha256(raw).hexdigest()
            if store.rows('SELECT id FROM files WHERE id=?',(ident,)):continue
            try:
                text,status=extract_text(path.name,raw)
                import spending,app
                bank=None;tr=None;trade=None
                if path.suffix.lower() in ('.csv','.txt','.xlsx','.xls'):
                    try:
                        from ai import decode_text
                        tr=app.tr_rows(decode_text(raw)) if path.suffix.lower() in ('.csv','.txt') else None
                        from .performance import parse_csv
                        trade=parse_csv(raw) if not tr else None
                        bank=spending.parse_known(path.name,raw) if not tr and not trade else None
                    except Exception:pass
                kind='Broker ledger' if trade else 'Trade Republic export' if tr else 'Bank export' if bank else 'Document'
                payload={'kind':kind,'rows':len(tr or trade or bank or []),'text':text,'extraction':status,'detected_from':min((r.get('date') or r.get('datetime','')[:10] for r in bank or tr or trade or []),default=''),'detected_to':max((r.get('date') or r.get('datetime','')[:10] for r in bank or tr or trade or []),default='')}
                # Keep immutable bytes in the existing evidence store, avoiding renamed/moved-file races.
                import receipts
                source=receipts.store_source({'name':path.name,'data':base64.b64encode(raw).decode()},kind='intake')
                payload['source_id']=source['id']
                store.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(ident,path.name,path.name,stat.st_size,stat.st_mtime,'ready',json.dumps(payload)))
                store.event('intake','Ready to review: '+path.name,{'id':ident,'name':path.name})
                found+=1
            except Exception as e:errors.append({'name':path.name,'error':str(e)[:300]})
        index_sources()
        return {'added':found,'errors':errors,'folder':'import-inbox','scope':'Files are indexed and prepared for review; importing remains explicit and uses the existing Undo workflow.'}
    finally:_scan_lock.release()

def intake():
    return [{**r,**json.loads(r['payload'])} for r in store.rows('SELECT id,name,size,status,payload FROM files ORDER BY modified DESC')]

def import_item(ident,provider=None,mode='auto'):
    rows=store.rows('SELECT * FROM files WHERE id=?',(ident,))
    if not rows:raise ValueError('Intake item not found.')
    item=rows[0]
    if item['status']=='imported':raise ValueError('This intake file was already imported.')
    payload=json.loads(item['payload']);import receipts,app
    path,source=receipts.source(payload['source_id']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ident:raise ValueError('Evidence hash changed; import stopped.')
    if payload['kind']=='Broker ledger':
        from . import performance
        bid=app.backup_now()
        result=performance.ingest(performance.parse_csv(raw),payload['source_id'])
        result['undo']=bid
        result['summary']=str(result['added'])+' ledger events retained. Current holdings and balances were not replaced.'
    else:result=app.import_files([{'name':item['name'],'media_type':source['media_type'],'data':base64.b64encode(raw).decode()}],'Imported from the local intake folder.',provider=provider,mode=mode)
    store.execute("UPDATE files SET status='imported' WHERE id=?",(ident,))
    index_sources();return result

def comparison(first,second):
    import difflib
    a=store.record('document',first);b=store.record('document',second)
    if not a or not b:raise ValueError('Choose two indexed documents.')
    if not a.get('text') or not b.get('text'):raise ValueError('Both documents need locally extracted text.')
    diff=list(difflib.unified_diff(a['text'].splitlines(),b['text'].splitlines(),fromfile=a['name'],tofile=b['name'],lineterm=''))
    return {'first':a['name'],'second':b['name'],'changes':diff[:2000],'truncated':len(diff)>2000,'scope':'Text differences only; changes require interpretation and are not automatically material.'}

def layout_instructions(files):
    import base64
    rules=store.records('rule');matches=[]
    for f in files:
        name=f.get('name','');raw=base64.b64decode(f.get('data',''))
        text,status=extract_text(name,raw)
        for r in rules:
            if r['pattern'].lower() in (name+' '+text).lower():
                matches.append(name+': '+r.get('supplier','')+' — '+r.get('note','')+' (saved preference; actual document evidence takes precedence)')
    return '\n'.join(matches)[:12000]

def start():
    global _started
    if _started:return
    _started=True
    def run():
        time.sleep(8)
        while True:
            try:scan()
            except Exception as e:store.event('intake-error','Document intake needs attention',{'error':str(e)[:200]})
            time.sleep(45)
    threading.Thread(target=run,name='document-intake',daemon=True).start()
