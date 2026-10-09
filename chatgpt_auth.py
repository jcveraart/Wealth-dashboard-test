"""Official ChatGPT plan OAuth for this local app; no API-key fallback.

Credentials are DPAPI protected on Windows, local-only, and excluded from Git.
The callback listens on loopback and validates state, PKCE and signed identity.
"""
import base64
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / '.chatgpt'
ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPE = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPE = 'chatgpt.tokens.use.direct'
USAGE_URL = 'https://chatgpt.com/settings/usage'
_lock = threading.RLock()
_attempt = None
_discovery = None
_jwks = None
_model_cache = {}

def _protect(raw, decrypt=False):
    if os.name != 'nt':
        return raw
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError('Could not unlock ChatGPT credentials for this Windows account.')
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.pbData)

@contextmanager
def _storage():
    # Cross-process lock prevents racing rotating refresh tokens.
    with _lock:
        ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(ROOT / 'session.lock'), os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'r+b') as lockfile:
            if not lockfile.read(1): lockfile.write(b'0'); lockfile.flush()
            lockfile.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lockfile.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                lockfile.seek(0)
                if os.name == 'nt': msvcrt.locking(lockfile.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)

def _read():
    path = ROOT / 'credentials.bin'
    if not path.exists(): return {'profiles': [], 'active': None}
    try:
        return json.loads(_protect(path.read_bytes(), decrypt=True))
    except (ValueError, OSError):
        raise RuntimeError('ChatGPT connection could not be read. Reconnect from Settings.') from None

def _write(data):
    raw = _protect(json.dumps(data).encode())
    tmp = ROOT / 'credentials.tmp'
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f: f.write(raw)
    os.replace(tmp, ROOT / 'credentials.bin')

def _active(data):
    return next((p for p in data['profiles'] if p['id'] == data.get('active')), None)

def _has_plan(profile):
    return bool(profile and profile.get('access_token') and PLAN_SCOPE in profile.get('scope', '').split())

def status():
    try:
        return _status()
    except (RuntimeError, OSError, ValueError):
        return {'connected': False, 'active': None, 'email': '', 'profiles': [], 'phase': 'failed',
                'message': 'ChatGPT connection could not be read for this computer account.',
                'welcome': False, 'usage_url': USAGE_URL}

def _status():
    with _storage():
        data = _read(); p = _active(data)
        attempt = _attempt
        phase = attempt['phase'] if attempt else 'idle'
        if attempt and phase == 'pending' and time.time() > attempt['deadline']: phase = 'expired'
        return {'connected': _has_plan(p), 'active': data.get('active'),
                'email': p.get('email', '') if p else '',
                'profiles': [{'id': q['id'], 'label': q.get('label', 'ChatGPT account'),
                              'email': q.get('email', ''), 'connected': _has_plan(q)} for q in data['profiles']],
                'phase': phase, 'message': attempt.get('message', '') if attempt else '',
                'welcome': bool(p and _has_plan(p) and not p.get('welcomed')),
                'usage_url': USAGE_URL}

def _request(url, form=None, token=None):
    headers = {'Accept': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    raw = None
    if form is not None:
        raw = urllib.parse.urlencode(form).encode(); headers['Content-Type'] = 'application/x-www-form-urlencoded'
    request = urllib.request.Request(url, data=raw, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        # Do not relay token endpoint bodies or credential-bearing request URLs.
        if e.code in (400, 401, 403):
            raise RuntimeError('ChatGPT authorization expired or was declined. Continue with ChatGPT again.') from None
        raise RuntimeError('ChatGPT connection failed. Try again shortly.') from None
    except urllib.error.URLError:
        raise RuntimeError('Could not reach ChatGPT. Check your connection and try again.') from None

def discovery():
    global _discovery
    if _discovery is None:
        d = _request(ISSUER + '/.well-known/openid-configuration')
        if d.get('issuer') != ISSUER: raise RuntimeError('Unexpected ChatGPT identity issuer.')
        for name in ('token_endpoint', 'authorization_endpoint', 'revocation_endpoint', 'jwks_uri'):
            u = urllib.parse.urlparse(d.get(name, ''))
            if u.scheme != 'https' or u.netloc != 'auth.openai.com':
                raise RuntimeError('Unexpected ChatGPT authorization endpoint.')
        _discovery = d
    return _discovery

def _identity(encoded, client_id, nonce=None):
    global _jwks
    import jwt
    try:
        if _jwks is None:
            _jwks = jwt.PyJWKClient(discovery()['jwks_uri'])
        signing_key = _jwks.get_signing_key_from_jwt(encoded)
        claims = jwt.decode(encoded, signing_key.key, algorithms=['RS256'], audience=client_id,
                            issuer=ISSUER, leeway=5, options={'require': ['sub', 'exp', 'iat']})
        if not isinstance(claims.get('sub'), str) or not claims['sub']:
            raise ValueError('Missing subject')
        if nonce is not None and not hmac.compare_digest(str(claims.get('nonce', '')), nonce):
            raise ValueError('Invalid nonce')
        return claims
    except Exception:
        raise RuntimeError('ChatGPT identity could not be verified. Start a new sign-in.') from None

def begin(profile_id=None):
    global _attempt
    with _storage():
        data = _read()
        data.setdefault('host_id', 'urn:uuid:' + str(uuid.uuid4()))
        profile = next((p for p in data['profiles'] if p['id'] == profile_id), None)
        if profile_id and not profile: raise ValueError('Choose a saved ChatGPT account.')
        _write(data)
        if _attempt and _attempt['phase'] == 'pending':
            _attempt['phase'] = 'cancelled'
        verifier = secrets.token_urlsafe(48)
        attempt = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
                   'verifier': verifier, 'profile_id': profile_id,
                   'client_id': profile['client_id'] if profile else None,
                   'deadline': time.time() + 600, 'phase': 'pending', 'message': ''}
        server = ThreadingHTTPServer(('127.0.0.1', 0), Callback)
        server.attempt = attempt
        attempt['redirect_uri'] = f'http://127.0.0.1:{server.server_port}/auth/callback'
        params = {'client_id': attempt['client_id'] or 'dynamic_agent_client',
                  'ext_agent_host_id': data['host_id'], 'response_type': 'code',
                  'redirect_uri': attempt['redirect_uri'], 'scope': SCOPE, 'resource': RESOURCE,
                  'state': attempt['state'], 'nonce': attempt['nonce'], 'code_challenge_method': 'S256',
                  'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if profile:
            if profile.get('email'): params['login_hint'] = profile['email']
        else: params['agent_name_hint'] = 'Wealth Dashboard'
        _attempt = attempt
        def serve():
            server.timeout = 1
            try:
                while attempt['phase'] == 'pending' and time.time() < attempt['deadline']:
                    server.handle_request()
                if attempt['phase'] == 'pending': attempt['phase'] = 'expired'
            finally: server.server_close()
        threading.Thread(target=serve, daemon=True).start()
        # No token hints are put into browser-accessible URLs.
        return {'url': ISSUER + '/api/accounts/authorize?' + urllib.parse.urlencode(params)}

def complete(attempt, query):
    with _storage():
        if attempt is not _attempt or attempt['phase'] != 'pending' or time.time() > attempt['deadline']:
            raise ValueError('This sign-in attempt expired. Start again in Wealth Dashboard.')
        if not hmac.compare_digest(str(query.get('state', '')), attempt['state']):
            raise ValueError('This sign-in callback does not match your request.')
        attempt['phase'] = 'exchanging'  # Single use, including failed exchanges.
        try:
            if query.get('error'): raise ValueError('ChatGPT sign-in was cancelled or declined.')
            client_id = query.get('client_id') or attempt['client_id']
            if not client_id or client_id == 'dynamic_agent_client':
                raise ValueError('ChatGPT did not finish registering this app. Start again.')
            if attempt['client_id'] and client_id != attempt['client_id']:
                raise ValueError('ChatGPT returned a different app registration.')
            if not query.get('code'): raise ValueError('ChatGPT did not return a sign-in code.')
            tokens = _request(discovery()['token_endpoint'], {'grant_type': 'authorization_code',
                    'client_id': client_id, 'code': query['code'], 'code_verifier': attempt['verifier'],
                    'redirect_uri': attempt['redirect_uri'], 'resource': RESOURCE})
            identity = _identity(tokens.get('id_token', ''), client_id, attempt['nonce'])
            data = _read()
            old = next((p for p in data['profiles'] if p['id'] == attempt['profile_id']), None)
            if old and identity['sub'] != old['sub']: raise ValueError('A different ChatGPT account was selected.')
            p = old or next((p for p in data['profiles'] if p['client_id'] == client_id and p['sub'] == identity['sub']), None)
            if p is None:
                p = {'id': secrets.token_hex(12), 'client_id': client_id, 'sub': identity['sub'],
                     'label': 'ChatGPT account ' + str(len(data['profiles']) + 1)}
                data['profiles'].append(p)
            p.update({'email': identity.get('email', ''), 'name': identity.get('name', ''),
                      'id_token': tokens['id_token'], 'access_token': tokens.get('access_token'),
                      'refresh_token': tokens.get('refresh_token'), 'scope': tokens.get('scope', ''),
                      'expires_at': time.time() + float(tokens.get('expires_in', 3600)),
                      'earliest_refresh_at': tokens.get('earliest_refresh_at', 0)})
            data['active'] = p['id']; _write(data)
            attempt['phase'] = 'done'
            attempt['message'] = 'Using your ChatGPT plan.' if _has_plan(p) else 'Signed in, but plan usage was not allowed. Reconnect and allow ChatGPT plan usage.'
            return attempt['message']
        except Exception as e:
            attempt['phase'] = 'failed'
            attempt['message'] = str(e) if isinstance(e, (RuntimeError, ValueError)) else 'ChatGPT sign-in could not finish. Try again.'
            raise RuntimeError(attempt['message']) from None
        finally:
            attempt.pop('verifier', None); attempt.pop('nonce', None)

class Callback(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Callback URLs contain authorization codes.
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != '/auth/callback': self.send_error(404); return
        if self.client_address[0] != '127.0.0.1' or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            self.send_error(403); return
        query = urllib.parse.parse_qs(u.query)
        try:
            if any(len(v) != 1 for v in query.values()): raise ValueError('Invalid sign-in callback.')
            message = complete(self.server.attempt, {k: v[0] for k, v in query.items()})
            code = 200
        except (ValueError, RuntimeError) as e:
            message = str(e); code = 400
        import html
        body = ('<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
                '<title>Wealth Dashboard · ChatGPT</title><style>body{font:16px system-ui;max-width:520px;'
                'margin:15vh auto;padding:24px;background:#191a18;color:#eee}h1{font-size:24px}</style>'
                '<h1>Wealth Dashboard</h1><p>' + html.escape(message) + '</p><p>You can close this tab and return to your dashboard.</p>').encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store'); self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

def access_token():
    with _storage():
        data = _read(); p = _active(data)
        if not _has_plan(p): raise ValueError('Continue with ChatGPT to connect your plan. OpenAI API billing is disabled.')
        if p.get('expires_at', 0) > time.time() + 60: return p['access_token']
        if not p.get('refresh_token'): raise ValueError('Reconnect your ChatGPT account in Settings.')
        try:
            tokens = _request(discovery()['token_endpoint'], {'grant_type': 'refresh_token',
                     'client_id': p['client_id'], 'refresh_token': p['refresh_token'], 'resource': RESOURCE})
            if not tokens.get('access_token'): raise ValueError('ChatGPT session could not be renewed. Reconnect.')
            if tokens.get('id_token'):
                identity = _identity(tokens['id_token'], p['client_id'])
                if identity['sub'] != p['sub']: raise ValueError('ChatGPT session identity changed. Reconnect.')
                p['id_token'] = tokens['id_token']
            p.update({'access_token': tokens['access_token'], 'refresh_token': tokens.get('refresh_token') or p['refresh_token'],
                      'scope': tokens.get('scope', p['scope']), 'expires_at': time.time() + float(tokens.get('expires_in', 3600)),
                      'earliest_refresh_at': tokens.get('earliest_refresh_at', 0)})
            _write(data)
        except (RuntimeError, ValueError):
            # Never substitute an API key when a session cannot be renewed.
            raise ValueError('ChatGPT session could not be renewed. Continue with ChatGPT again.') from None
        if not _has_plan(p): raise ValueError('ChatGPT plan permission is missing. Reconnect and allow plan usage.')
        return p['access_token']

def choose(profile_id):
    with _storage():
        data = _read()
        if not any(p['id'] == profile_id for p in data['profiles']): raise ValueError('Choose a saved ChatGPT account.')
        data['active'] = profile_id; _write(data)
    return status()

def welcome_done():
    with _storage():
        data = _read(); p = _active(data)
        if p: p['welcomed'] = True; _write(data)
    return {'ok': True}

def sign_out():
    with _storage():
        data = _read(); p = _active(data); revoked = True
        if p:
            if p.get('refresh_token'):
                try:
                    _request(discovery()['revocation_endpoint'], {'token': p['refresh_token'],
                             'token_type_hint': 'refresh_token', 'client_id': p['client_id']})
                except RuntimeError: revoked = False
            for name in ('access_token', 'refresh_token', 'id_token', 'expires_at'): p.pop(name, None)
            _write(data)
        return {'ok': True, 'revoked': revoked,
                'message': 'Signed out.' if revoked else 'Signed out locally. Disconnect Wealth Dashboard in ChatGPT settings to finish revoking access.'}

def models():
    token = access_token()
    cache_id = hashlib.sha256(token.encode()).hexdigest()
    cached = _model_cache.get(cache_id)
    if cached and cached[0] > time.time(): return cached[1]
    result = _request(RESOURCE + '/models', token=token)
    items = [{'id': m['slug'], 'name': m.get('display_name') or m['slug']} for m in result.get('models', [])
             if m.get('visibility') == 'list' and m.get('slug')]
    if not items: raise ValueError('No models are available to this ChatGPT account. Check your plan or workspace.')
    _model_cache[cache_id] = (time.time() + 300, items)
    return items

def model(preferred=None):
    choices = models()
    return preferred if preferred in {m['id'] for m in choices} else choices[0]['id']
