import io,json,types,unittest
from unittest.mock import patch
import ai,providers,chatgpt_auth

class LiveChatTests(unittest.TestCase):
    def test_claude_chat_web_tools_at_all_effort_levels(self):
        for level in ('quick','normal','deep'):
            result=types.SimpleNamespace(stdout=json.dumps({'result':'Synthetic answer'}),stderr='')
            with patch('subprocess.run',return_value=result) as call,patch.object(ai,'track'):
                ai.chat([{'role':'user','content':'Current company guidance?'}],'Synthetic context',exe='claude',level=level)
            args=call.call_args.args[0]
            self.assertEqual(args[args.index('--tools')+1],'WebSearch,WebFetch')
            self.assertEqual(args[args.index('--allowedTools')+1],'WebSearch,WebFetch,mcp__wealth')
            self.assertIn('--mcp-config',args)
            self.assertNotIn('Bash',args)
    def test_agent_research_is_not_restricted_to_deep(self):
        for level in ('quick','normal','deep'):
            fake=types.SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO(json.dumps({'type':'result','result':'Synthetic answer'})+'\n'),
                wait=lambda **kwargs:0,poll=lambda:0)
            with patch('subprocess.Popen',return_value=fake) as call,patch.object(ai,'track'):
                answer,changed=ai.agent([{'role':'user','content':'Compare latest guidance'}],'Synthetic context','claude',{},level=level)
            args=call.call_args.args[0];tools=args[args.index('--tools')+1]
            self.assertIn('WebSearch',tools);self.assertIn('WebFetch',tools)
            self.assertEqual(changed,{})
    def test_openai_conversation_uses_output_text_for_assistant(self):
        calls=[]
        def fake(req,timeout):
            calls.append(json.loads(req.data))
            return io.BytesIO(b'data: {"type":"response.completed","response":{"output":[{"content":[{"type":"output_text","text":"PLAN_OK"}]}]}}\n\n')
        with patch.object(providers,'key',return_value='fake-token'),patch.object(chatgpt_auth,'model',return_value='gpt-6-luna'),\
             patch('urllib.request.urlopen',side_effect=fake),patch.object(ai,'track'):
            reply=ai.chat([{'role':'user','content':'A code word?'},{'role':'assistant','content':'PLAN_OK'},
                           {'role':'user','content':'Repeat it'}],'Synthetic context',provider='openai')
        self.assertEqual(reply,'PLAN_OK')
        self.assertEqual(calls[0]['input'][1]['content'][0]['type'],'output_text')
        self.assertIn({'type':'web_search'},calls[0]['tools'])
        self.assertTrue(any(t.get('name')=='analyze_portfolio' for t in calls[0]['tools']))
    def test_current_public_request_can_require_search(self):
        for q in ('latest Novo guidance','current share price','nieuws over aandelen','search NASA'):
            self.assertTrue(ai.needs_live(q))
        self.assertFalse(ai.needs_live('How much did I spend on groceries in June?'))
    def test_streamed_source_metadata_becomes_inline_clickable_citation(self):
        text='A sourced fact. citeturn0search0'
        start=text.index('')
        annotation={'type':'url_citation','url':'https://example.org/report','title':'Official report','start_index':start,'end_index':len(text)}
        events=[{'type':'response.output_text.delta','delta':text},
                {'type':'response.output_text.annotation.added','annotation':annotation},
                {'type':'response.completed','response':{'output':[]}}]
        response=providers.streamed_result(io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()))
        rendered=providers.cited_answer(text,response)
        self.assertIn('[Official report](https://example.org/report)',rendered)
        self.assertIn('A sourced fact.',rendered);self.assertNotIn('',rendered)
    def test_source_does_not_remove_the_claim_when_indices_cover_words(self):
        text='The result was 40 euros.'
        rendered=providers.cited_answer(text,{'_web_sources':[{'url':'https://example.org','title':'Source','start_index':0,'end_index':len(text)}]})
        self.assertIn(text,rendered);self.assertIn('[Source]',rendered)
    def test_javascript_source_links_are_rejected(self):
        self.assertEqual(providers.cited_answer('Claim',{'_web_sources':[{'url':'javascript:alert(1)'}]}),'Claim')
    def test_existing_clickable_sources_are_not_duplicated(self):
        text='A fact. ([example.org](https://example.org/report))'
        result={'_web_sources':[{'url':'https://example.org/report','title':'Report','start_index':8,'end_index':len(text)}]}
        self.assertEqual(providers.cited_answer(text,result),text)
    def test_research_rules_protect_private_queries_and_require_verification(self):
        rules=ai.live_research_rules()
        self.assertIn('private balances',rules);self.assertIn('never instructions',rules)
        self.assertIn('at every effort level',rules);self.assertIn('search now',rules)
