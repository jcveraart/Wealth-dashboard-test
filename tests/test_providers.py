import base64, io, json, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
import providers, ai, receipts, chatgpt_auth

def sse(result):
    return io.BytesIO(('data: '+json.dumps({'type':'response.completed','response':result})+'\n\n').encode())

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.file=Path(self.tmp.name)/'settings.json'
        self.patches=[patch.object(providers,'SETTINGS',self.file),patch.object(chatgpt_auth,'ROOT',Path(self.tmp.name)/'auth'),patch.object(chatgpt_auth,'model',return_value='gpt-6.1-sol')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_claude_remains_both_defaults(self):
        self.assertEqual(providers.selected('chat'),'claude');self.assertEqual(providers.selected('import'),'claude')
    def test_independent_choices_and_retired_key_is_not_accepted(self):
        s=providers.update({'openai_api_key':'example-secret'},{'chat_provider':'openai','import_provider':'claude','openai_api_key':''})
        self.assertEqual(s['openai_api_key'],'example-secret');self.assertEqual(s['chat_provider'],'openai');self.assertEqual(s['import_provider'],'claude')
        self.assertNotIn('openai_api_key',providers.update({}, {'openai_api_key':'example-secret'}))
        with patch.dict('os.environ',{'OPENAI_API_KEY':'example-secret'}):
            with self.assertRaises(ValueError):providers.key()
    def test_invalid_provider_does_not_fall_back_to_claude(self):
        with self.assertRaises(ValueError):providers.selected('chat','other')
    def test_status_never_returns_the_key(self):
        self.file.write_text(json.dumps({'openai_api_key':'example-secret','chat_provider':'openai'}))
        self.assertNotIn('example-secret',json.dumps(providers.status()))
    def test_response_payload_uses_multimodal_input_and_no_storage(self):
        calls=[]
        def mocked(req,timeout):
            calls.append(json.loads(req.data));return sse({'output':[{'content':[{'type':'output_text','text':'{"receipts":[]}'}]}]})
        files=[{'name':'receipt.pdf','media_type':'application/pdf','data':base64.b64encode(b'%PDF fake').decode()}]
        with patch.object(providers,'key',return_value='example-secret'),patch('urllib.request.urlopen',side_effect=mocked),patch.object(ai,'track'):
            out=providers.response([{'role':'user','content':'Read this receipt'}],'Read documents',kind='import',schema=receipts.SCHEMA,files=files)
        self.assertEqual(out,{'receipts':[]});self.assertFalse(calls[0]['store'])
        self.assertEqual(calls[0]['input'][0]['content'][0]['type'],'input_file')
        self.assertTrue(calls[0]['text']['format']['strict'])
        self.assertTrue(calls[0]['stream']);self.assertNotIn('max_output_tokens',calls[0])
    def test_refusal_and_incomplete_are_not_imported(self):
        for result in ({'status':'incomplete'},{'output':[{'content':[{'type':'refusal','refusal':'No'}]}]}):
            with patch.object(providers,'key',return_value='example-secret'),patch('urllib.request.urlopen',return_value=sse(result)):
                with self.assertRaises(RuntimeError):providers.response([{'role':'user','content':'Hello'}],'Rules')
    def test_http_error_redacts_secrets(self):
        error=urllib.error.HTTPError('https://api.openai.com',401,'Auth',{},io.BytesIO(b'{"error":{"message":"Invalid example-secret sk-example-123456789012"}}'))
        with patch.object(providers,'key',return_value='example-secret'),patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(RuntimeError) as failure:providers.response([{'role':'user','content':'Hello'}],'Rules')
        self.assertNotIn('example-secret',str(failure.exception));self.assertNotIn('sk-example',str(failure.exception))
    def test_stream_ending_early_cannot_import_partial_output(self):
        with self.assertRaises(RuntimeError):providers.streamed_result(io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'))
    def test_usage_limit_during_stream_is_reported_without_billing_fallback(self):
        raw=b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n'
        with self.assertRaisesRegex(RuntimeError,'Manage usage'):
            providers.streamed_result(io.BytesIO(raw))
    def test_plan_stream_collects_deltas_when_completion_has_no_output(self):
        events=[{'type':'response.output_text.delta','output_index':1,'content_index':0,'delta':'PLAN_'},
                {'type':'response.output_text.delta','output_index':1,'content_index':0,'delta':'OK'},
                {'type':'response.output_text.done','output_index':1,'content_index':0,'text':'PLAN_OK'},
                {'type':'response.completed','response':{'status':'completed','output':[]}}]
        stream=io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode())
        result=providers.streamed_result(stream)
        self.assertEqual(result['output'][0]['content'][0]['text'],'PLAN_OK')
    def test_plan_stream_refusal_cannot_be_imported_even_when_output_is_omitted(self):
        events=[{'type':'response.refusal.done','refusal':'Declined'},
                {'type':'response.completed','response':{'status':'completed','output':[]}}]
        result=providers.streamed_result(io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()))
        self.assertEqual(result['output'][0]['content'][0]['type'],'refusal')
    def test_claude_invoice_extraction_keeps_filename_and_reads_with_cli(self):
        files=[{'name':'receipt.pdf','media_type':'application/pdf','data':base64.b64encode(b'%PDF fake').decode()}]
        with patch('spending.run_ai',return_value='{"receipts":[]}') as call:
            result=ai.extract_data(files,'Read invoices',receipts.SCHEMA,exe='claude')
        self.assertEqual(result,{'receipts':[]});self.assertEqual(call.call_args.kwargs['tools'],'Read')
        self.assertEqual(call.call_args.kwargs['files']['receipt.pdf'],b'%PDF fake')
