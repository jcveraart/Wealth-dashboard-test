import json,time
from datetime import date
from unittest.mock import patch
from test_workspace import Isolated
from workspace import changes,plans,store,service,undo,performance
from intelligence import tools
import app,ai,providers

class ChatChanges(Isolated):
    def setup_backup(self):
        self.patches.append(patch.object(app,'BACKUPS',self.root/'backups'));self.patches[-1].start()
        self.patches.append(patch.object(app,'BACKED_UP',[(app.CONFIG,'portfolio','.json')]));self.patches[-1].start()
    def session(self,scope='investments'):
        self.setup_backup();ident,binding=changes.begin(scope,True);self.addCleanup(changes.finish,ident,binding);return ident
    def commit(self,session,section,action,index,fields):
        with patch.object(app,'cloud_sync_soon'):
            ref=changes.reference(service.cfg().get(section,[])[index]) if action!='add' else None
            return changes.commit({'session':session,'operation':'edit_dashboard_record','arguments':{'section':section,'action':action,'index':index,'reference':ref,'fields_json':json.dumps(fields)}})
    def test_twice_monthly_is_not_biweekly(self):
        self.assertEqual(plans.monthly({'amount_eur':10,'frequency':'twice_monthly'}),20)
        self.assertAlmostEqual(plans.monthly({'amount_eur':10,'frequency':'biweekly'}),21.6666667)
    def test_start_date_and_unknown_second_date_not_invented(self):
        p={'active':True,'starts_on':'2026-10-16','frequency':'twice_monthly','amount_eur':10,'day':16,'second_day':None}
        self.assertEqual(plans.next_date(p,date(2026,10,8)),'2026-10-16');self.assertIsNone(plans.next_date(p,date(2026,10,17)))
    def test_weekly_first_execution_anchored_to_start(self):
        p={'active':True,'starts_on':'2026-10-16','frequency':'weekly'}
        self.assertEqual(plans.next_date(p,date(2026,10,17)),'2026-10-23')
    def test_plan_edit_changes_real_dashboard_and_undo(self):
        ident=self.session();r=self.commit(ident,'savings_plans','add',None,{'account':'Demo Broker','instrument':'EQT private markets','amount_eur':10,'frequency':'twice_monthly','active':True,'starts_on':'2026-10-16','asset_class':'Private markets'})
        self.assertTrue(r['saved']);saved=service.cfg()['savings_plans'][0];self.assertNotIn('isin',saved);self.assertIsNone(saved['day']);self.assertEqual(app.monthly_amount(saved),20)
        self.assertEqual(service.get('plans',{})['items'][0]['next'],'2026-10-16')
        app.undo(r['undo']);self.assertEqual(service.cfg().get('savings_plans',[]),[])
    def test_foreign_or_expired_capability_cannot_edit(self):
        ident=self.session();r=store.record('chat-write-session',ident);r['expires']=time.time()-1;store.put('chat-write-session',r,ident,audit=False)
        with self.assertRaises(ValueError):self.commit(ident,'savings_plans','add',None,{})
        self.assertNotIn('savings_plans',service.cfg())
    def test_context_cannot_edit_other_accounts(self):
        ident=self.session()
        with self.assertRaises(ValueError):self.commit(ident,'savings','add',None,{'name':'Injected'})
    def test_invalid_plan_does_not_create_backup_or_write(self):
        ident=self.session()
        with self.assertRaises(ValueError):self.commit(ident,'savings_plans','add',None,{'account':'Unknown','instrument':'A','amount_eur':-10,'frequency':'weekly'})
        self.assertIsNone(store.record('chat-write-session',ident)['undo'])
    def test_workflow_edit_partial_fields_and_undo_preserve_other_changes(self):
        ident=self.session('planning');original=service.save_record('goal',{'name':'A','target_eur':1000,'saved_eur':10,'due':'2027-01-01'})
        with patch.object(app,'cloud_sync_soon'):
            r=changes.commit({'session':ident,'operation':'save_workflow_record','arguments':{'kind':'goal','id':original['id'],'fields_json':'{"saved_eur":20}','delete':False}})
        store.put('note',{'name':'Later note'},'later');app.undo(r['undo']);self.assertEqual(store.record('goal',original['id'])['saved_eur'],10);self.assertEqual(store.record('note','later')['name'],'Later note')
    def test_undo_conflict_checks_before_portfolio_restoration(self):
        self.setup_backup();bid=app.backup_now();store.put('goal',{'name':'After'},'g');undo.remember_chat(bid,'goal','g',None,store.record('goal','g'));store.put('goal',{'name':'Later'},'g')
        c=service.cfg();c['profile']['buffer_months']=9;app.save(app.CONFIG,c)
        with self.assertRaises(ValueError):app.undo(bid)
        self.assertEqual(service.cfg()['profile']['buffer_months'],9)
    def test_mutating_tools_only_advertised_for_requested_edit(self):
        self.assertNotIn('edit_dashboard_record',{d['name'] for d in tools.definitions('investments')})
        ident=self.session();self.assertIn('edit_dashboard_record',{d['name'] for d in tools.definitions('investments')})
        changes.SESSION.set('');self.assertTrue(tools.safe_call('edit_dashboard_record',{},'investments')['unavailable'])
    def test_provider_reply_carries_undo_metadata(self):
        def fake(*a,**k):
            ident=changes.token();r=store.record('chat-write-session',ident);r.update(undo='20261008-100000-123456',changes=[{'saved':True}]);store.put('chat-write-session',r,ident,audit=False);return 'Saved'
        with patch.object(ai,'_chat',fake):reply=ai.chat([{'role':'user','content':'Save this plan'}],'Context',provider='openai')
        self.assertEqual(reply,'Saved');self.assertEqual(reply.undo,'20261008-100000-123456');self.assertFalse(changes.token())
    def test_readonly_question_has_no_write_capability(self):
        with patch.object(ai,'_chat',lambda *a,**k:'Writable' if changes.token() else 'Readonly'):
            self.assertEqual(ai.chat([{'role':'user','content':'What are my plans?'}],'Context'),'Readonly')
            self.assertEqual(ai.chat([{'role':'user','content':'Should I cancel my savings plan?'}],'Context'),'Readonly')
    def test_stale_record_reference_rejected(self):
        ident=self.session();self.commit(ident,'savings_plans','add',None,{'account':'Demo Broker','instrument':'A','amount_eur':10,'frequency':'monthly','active':True})
        with self.assertRaises(ValueError):
            changes.commit({'session':ident,'operation':'edit_dashboard_record','arguments':{'section':'savings_plans','action':'update','index':0,'reference':'outdated','fields_json':'{"active":false}'}})
        self.assertTrue(service.cfg()['savings_plans'][0]['active'])
    def test_openai_change_protocol_saves_and_returns_tool_evidence(self):
        ident=self.session();args={'section':'savings_plans','action':'add','index':None,'reference':None,'fields_json':json.dumps({'account':'Demo Broker','instrument':'OpenAI fictional plan','amount_eur':10,'frequency':'monthly','active':True})}
        payload={'input':[]};responses=[{'output':[{'type':'function_call','call_id':'save1','name':'edit_dashboard_record','arguments':json.dumps(args)}]},{'output':[{'type':'message','content':[{'type':'output_text','text':'Saved'}]}]}]
        def local_call(name,a,scope):
            with patch.object(app,'cloud_sync_soon'):return changes.commit({'session':ident,'operation':name,'arguments':a})
        with patch.object(providers,'request_response',side_effect=responses),patch.object(tools,'safe_call',side_effect=local_call):result=providers.run_responses(payload,'fictional',True,scope='investments')
        self.assertEqual(result,responses[1]);self.assertTrue(json.loads(payload['input'][-1]['output'])['saved']);self.assertEqual(service.cfg()['savings_plans'][0]['instrument'],'OpenAI fictional plan')
        self.assertIn('edit_dashboard_record',{t['name'] for t in tools.openai_definitions('investments')})

class PeriodChecks(Isolated):
    def test_cloud_comparison_reports_conflicts_without_mutation(self):
        from workspace import sync_review
        a={'accounts':[{'name':'A'}],'savings_plans':[]};b={'accounts':[{'name':'A'}],'savings_plans':[{'amount_eur':10}]}
        self.assertEqual(sync_review.compare(a,b),[{'section':'savings_plans','local_records':0,'cloud_records':1,'status':'Different'}]);self.assertEqual(a['savings_plans'],[])
    def test_cloud_preview_needs_existing_connection(self):
        from workspace import sync_review
        with patch.object(app,'cloud_config',return_value=None):self.assertFalse(sync_review.cloud_preview()['configured'])
    def test_selected_period_uses_only_actual_valuations(self):
        c=service.cfg();c['account_history']=[{'account':'Demo Broker','date':f'2026-{m:02d}-01','value_eur':100*m} for m in range(1,4)]
        st=app.compute_state(c,record=False,include_intelligence=False)
        with patch.object(app,'account_history',return_value=[]):r=performance.account_report(c,st,'Demo Broker','2026-02-01','2026-03-01')
        self.assertEqual([v['date'] for v in r['valuations']],['2026-02-01','2026-03-01']);self.assertIsNone(r['performance']['twr_pct'])
    def test_inverted_period_rejected(self):
        c=service.cfg();st=app.compute_state(c,record=False,include_intelligence=False)
        with self.assertRaises(ValueError):performance.account_report(c,st,'Demo Broker','2026-03-01','2026-02-01')
