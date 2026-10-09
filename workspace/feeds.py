"""Public RSS/Atom feeds with DNS-pinned requests and bounded XML parsing."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import urllib.parse
import xml.etree.ElementTree as ET
from . import store

def validate_url(url):
    u=urllib.parse.urlsplit(str(url))
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.port not in (None,80,443):raise ValueError('Use a public HTTP(S) feed URL without credentials or a custom port.')
    if u.hostname.lower() in ('localhost','wealth.localhost') or u.hostname.lower().endswith('.localhost'):raise ValueError('Feed addresses must be public.')
    return u

def fetch(url,limit=3*1024*1024,redirects=3):
    u=validate_url(url);port=u.port or (443 if u.scheme=='https' else 80)
    addresses=list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(u.hostname,port,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):raise ValueError('Feed resolves to a private or reserved network.')
    # Pin the checked address; TLS still verifies the original public hostname.
    sock=socket.create_connection((addresses[0],port),timeout=20)
    if u.scheme=='https':sock=ssl.create_default_context().wrap_socket(sock,server_hostname=u.hostname)
    conn=http.client.HTTPConnection(u.hostname,port,timeout=20);conn.sock=sock
    try:
        conn.request('GET',urllib.parse.urlunsplit(('','',u.path or '/',u.query,'')),headers={'User-Agent':'WealthDashboard public feed reader','Accept-Encoding':'identity'})
        response=conn.getresponse()
        if response.status in (301,302,303,307,308):
            if not redirects:raise ValueError('Too many feed redirects.')
            target=urllib.parse.urljoin(url,response.getheader('Location') or '')
            return fetch(target,limit,redirects-1)
        if response.status!=200:raise ValueError('Public feed returned HTTP '+str(response.status))
        raw=response.read(limit+1)
        if len(raw)>limit:raise ValueError('Feed exceeds supported size.')
        return raw
    finally:conn.close()

def parse(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Feed XML declarations are unsupported.')
    root=ET.fromstring(raw);out=[]
    local=lambda tag:tag.rsplit('}',1)[-1]
    for item in root.iter():
        if local(item.tag) not in ('item','entry'):continue
        values={};link=''
        for child in item:
            key=local(child.tag);values[key]=''.join(child.itertext()).strip()
            if key=='link':link=child.attrib.get('href') or values[key]
        if link:
            try:validate_url(link)
            except ValueError:link=''
        out.append({'title':values.get('title') or 'Untitled item','date':values.get('published') or values.get('updated') or values.get('pubDate'),'summary':(values.get('description') or values.get('summary') or '')[:3000],'url':link,'identity':values.get('guid') or values.get('id') or link or values.get('title')})
    return out[:100]

def refresh():
    import app
    if app.OFFLINE:raise ValueError('Feeds require online mode.')
    results=[]
    for f in store.records('feed'):
        if not f.get('enabled'):continue
        try:
            items=parse(fetch(f['url']));previous=store.record('feed-cache',f['id'],{'items':[]});seen={r['identity'] for r in previous['items']}
            for item in items:
                if item['identity'] not in seen:store.event('feed',item['title'],{'feed':f['name'],'symbol':f.get('symbol'),'url':item['url'],'identity':item['identity']})
            store.put('feed-cache',{'name':f['name'],'symbol':f.get('symbol'),'items':items,'retrieved_at':store.now(),'url':f['url']},f['id'])
            results.append({'name':f['name'],'items':len(items),'ok':True})
        except Exception as e:results.append({'name':f['name'],'ok':False,'error':str(e)[:250]})
    return {'feeds':results,'scope':'Original public feeds; retrieved HTML content is treated as text, never as instructions.'}
