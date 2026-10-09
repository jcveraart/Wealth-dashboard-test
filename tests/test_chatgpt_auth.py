import base64, hashlib, json, tempfile, time, types, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import chatgpt_auth as auth

class ChatGPTAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(auth, 'ROOT', Path(self.temp.name)/'auth'),
                        patch.object(auth, '_attempt', None), patch.object(auth, '_model_cache', {}),
                        patch.object(auth, '_discovery', {'issuer':auth.ISSUER,'token_endpoint':auth.ISSUER+'/token',
                            'jwks_uri':auth.ISSUER+'/jwks','revocation_endpoint':auth.ISSUER+'/revoke'}),
                        patch.object(auth, '_jwks', types.SimpleNamespace(get_signing_key_from_jwt=lambda _:types.SimpleNamespace(key=self.public_key)))]
        for p in self.patches: p.start()
    def tearDown(self):
        if auth._attempt: auth._attempt['phase']='cancelled'
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()
    def begin(self, profile_id=None):
        server=types.SimpleNamespace(server_port=4567)
        with patch.object(auth,'ThreadingHTTPServer',return_value=server), patch('threading.Thread.start'):
            result=auth.begin(profile_id)
        return result, auth._attempt
    def identity_token(self, **changes):
        claims={'sub':'synthetic-user','email':'user@example.invalid','iss':auth.ISSUER,
                'aud':'oaiapp_synthetic','iat':time.time(),'exp':time.time()+3600,'nonce':auth._attempt['nonce']}
        claims.update(changes)
        return jwt.encode(claims,self.private_key,algorithm='RS256')
    def connect(self, scope=auth.SCOPE):
        self.begin()
        tokens={'access_token':'synthetic-access','refresh_token':'synthetic-refresh','id_token':self.identity_token(),
                'expires_in':3600,'scope':scope}
        with patch.object(auth,'_request',return_value=tokens):
            auth.complete(auth._attempt,{'state':auth._attempt['state'],'code':'synthetic-code','client_id':'oaiapp_synthetic'})
        return auth.status()
    def test_stable_host_and_fresh_pkce_state_nonce(self):
        a,attempt=self.begin();q=parse_qs(urlparse(a['url']).query)
        b,other=self.begin();r=parse_qs(urlparse(b['url']).query)
        self.assertEqual(q['ext_agent_host_id'],r['ext_agent_host_id'])
        self.assertNotEqual(q['state'],r['state']);self.assertNotEqual(q['nonce'],r['nonce'])
        challenge=base64.urlsafe_b64encode(hashlib.sha256(attempt['verifier'].encode()).digest()).decode().rstrip('=')
        self.assertEqual(q['code_challenge'],[challenge]);self.assertEqual(q['client_id'],['dynamic_agent_client'])
        self.assertEqual(q['redirect_uri'],['http://127.0.0.1:4567/auth/callback'])
        self.assertIn(auth.PLAN_SCOPE,q['scope'][0]);self.assertEqual(q['agent_name_hint'],['Wealth Dashboard'])
    def test_invalid_state_does_not_exchange_code_or_consume_real_attempt(self):
        self.begin()
        with patch.object(auth,'_request') as request:
            with self.assertRaises(ValueError):auth.complete(auth._attempt,{'state':'wrong','code':'code','client_id':'oaiapp_synthetic'})
            request.assert_not_called()
        self.assertEqual(auth._attempt['phase'],'pending')
    def test_denied_consent_never_exchanges_code(self):
        self.begin()
        with patch.object(auth,'_request') as request:
            with self.assertRaises(RuntimeError):auth.complete(auth._attempt,{'state':auth._attempt['state'],'error':'access_denied'})
            request.assert_not_called()
        self.assertEqual(auth._attempt['phase'],'failed')
    def test_missing_dynamic_client_id_is_rejected(self):
        self.begin()
        with self.assertRaises(RuntimeError):auth.complete(auth._attempt,{'state':auth._attempt['state'],'code':'code'})
    def test_success_stores_issued_client_and_hides_tokens_from_status(self):
        c=self.connect()
        self.assertTrue(c['connected']);self.assertTrue(c['welcome'])
        self.assertNotIn('synthetic-access',json.dumps(c));self.assertNotIn('synthetic-refresh',json.dumps(c))
        with auth._storage():p=auth._active(auth._read())
        self.assertEqual(p['client_id'],'oaiapp_synthetic');self.assertEqual(p['sub'],'synthetic-user')
        self.assertEqual(auth.access_token(),'synthetic-access')
        if __import__('os').name=='nt':self.assertNotIn(b'synthetic-access',(auth.ROOT/'credentials.bin').read_bytes())
    def test_identity_only_permission_cannot_use_plan(self):
        c=self.connect(scope='openid email profile')
        self.assertFalse(c['connected'])
        with self.assertRaises(ValueError):auth.access_token()
    def test_verified_nonce_audience_issuer_expiry_and_signature(self):
        self.begin()
        for change in ({'nonce':'wrong'},{'aud':'other'},{'iss':'https://example.invalid'},{'exp':time.time()-100}):
            with self.assertRaises(RuntimeError):auth._identity(self.identity_token(**change),'oaiapp_synthetic',auth._attempt['nonce'])
        fake_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        good=jwt.decode(self.identity_token(),options={'verify_signature':False})
        bad=jwt.encode(good,fake_key,algorithm='RS256')
        with self.assertRaises(RuntimeError):auth._identity(bad,'oaiapp_synthetic',auth._attempt['nonce'])
    def test_callback_replay_rejected(self):
        self.connect()
        with self.assertRaises(ValueError):auth.complete(auth._attempt,{'state':auth._attempt['state'],'code':'replay'})
    def test_refresh_rotates_token_and_reuses_issued_client(self):
        self.connect()
        with auth._storage():
            data=auth._read();p=auth._active(data);p['expires_at']=0;auth._write(data)
        with patch.object(auth,'_request',return_value={'access_token':'new-access','refresh_token':'replacement','expires_in':3600}) as call:
            self.assertEqual(auth.access_token(),'new-access')
        self.assertEqual(call.call_args.args[1]['client_id'],'oaiapp_synthetic')
        self.assertNotIn('scope',call.call_args.args[1])
        with auth._storage():self.assertEqual(auth._active(auth._read())['refresh_token'],'replacement')
    def test_failed_refresh_never_uses_api_credentials(self):
        self.connect()
        with auth._storage():
            data=auth._read();auth._active(data)['expires_at']=0;auth._write(data)
        with patch.object(auth,'_request',side_effect=RuntimeError('offline')):
            with self.assertRaises(ValueError):auth.access_token()
    def test_returning_registration_cannot_change_client_or_identity(self):
        c=self.connect();id=c['active'];self.begin(id)
        with self.assertRaises(RuntimeError):auth.complete(auth._attempt,{'state':auth._attempt['state'],'code':'code','client_id':'other-client'})
        self.assertTrue(auth.status()['connected'])
        self.begin(id)
        with patch.object(auth,'_request',return_value={'id_token':self.identity_token(sub='other-user'),'scope':auth.SCOPE}):
            with self.assertRaises(RuntimeError):auth.complete(auth._attempt,{'state':auth._attempt['state'],'code':'code'})
        self.assertEqual(auth.access_token(),'synthetic-access')
    def test_model_catalog_filters_hidden_and_rejects_stale_model(self):
        self.connect()
        catalog={'models':[{'slug':'eligible','display_name':'Eligible model','visibility':'list'},
                           {'slug':'hidden','visibility':'hidden'}]}
        with patch.object(auth,'_request',return_value=catalog):
            self.assertEqual(auth.models(),[{'id':'eligible','name':'Eligible model'}])
            self.assertEqual(auth.model('retired-api-model'),'eligible')
    def test_signout_revokes_and_clears_tokens_but_retains_registration(self):
        c=self.connect()
        with patch.object(auth,'_request',return_value={}) as call:out=auth.sign_out()
        self.assertTrue(out['revoked']);self.assertEqual(call.call_args.args[1]['token_type_hint'],'refresh_token')
        self.assertFalse(auth.status()['connected']);self.assertEqual(auth.status()['active'],c['active'])
        with auth._storage():self.assertNotIn('refresh_token',auth._active(auth._read()))
    def test_signout_network_failure_is_reported_and_still_clears_local_tokens(self):
        self.connect()
        with patch.object(auth,'_request',side_effect=RuntimeError('offline')):out=auth.sign_out()
        self.assertFalse(out['revoked']);self.assertFalse(auth.status()['connected'])
    def test_welcome_is_once_per_registration(self):
        self.connect();auth.welcome_done();self.assertFalse(auth.status()['welcome'])
