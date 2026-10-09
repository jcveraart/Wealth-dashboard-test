import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import extras,spending

class HomeBriefing(unittest.TestCase):
    def facts(self,state):
        with patch('spending.load',return_value=spending.empty()),patch('public.economy',return_value={}):return extras.briefing_facts(state)
    def test_a_quiet_or_new_workspace_has_a_useful_next_step(self):
        facts=self.facts({});self.assertTrue(facts);self.assertEqual(facts[0]['link']['page'],'import')
    def test_stored_payments_without_legacy_key_still_produce_a_briefing(self):
        data=spending.empty();data['transactions']=[{'id':'payment','date':extras.date.today().isoformat(),'amount':-50,'merchant':'Example Shop','merchant_key':'exampleshop','category':'groceries'}]
        with patch('spending.load',return_value=data),patch('public.economy',return_value={}):facts=extras.briefing_facts({})
        self.assertIn('€50',json.dumps(facts,ensure_ascii=False))
    def test_briefing_covers_investments_savings_goals_and_pending_advice(self):
        facts=self.facts({'totals':{'invested':1000,'savings':500,'debt':200},'savings_plans':[{'active':True,'per_month':20}],'goals':[{'name':'Travel'}],'advice':[{'id':'review','title':'Review portfolio concentration'},{'id':'done','title':'Completed action'}],'advice_done':[{'id':'done'}]})
        pages={f['link'].get('page') for f in facts};self.assertTrue({'holdings','cash','plan','advice'}<=pages)
        self.assertNotIn('Completed action',json.dumps(facts));self.assertIn('€20',json.dumps(facts,ensure_ascii=False))
    def test_candidates_keep_category_breadth_without_repeating_payment_alerts(self):
        rows=[{'text':'Big payment','link':{'kind':'tx'}},{'text':'Another payment','link':{'kind':'payments'}},{'text':'Investment','link':{'kind':'page','page':'holdings'}},{'text':'Goal','link':{'kind':'page','page':'plan'}}]
        self.assertEqual([f['text'] for f in extras.diverse_briefing_facts(rows)],['Big payment','Investment','Goal'])
    def test_old_daily_cache_is_replaced_by_the_broader_briefing(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'BRIEFING',Path(folder)/'brief.json'),patch('extras.briefing_facts',return_value=[{'text':'Current facts','impact':1,'link':{'kind':'page','page':'holdings'}}]):
            extras.write(extras.BRIEFING,{'date':extras.date.today().isoformat(),'items':[{'text':'Old summary'}]})
            result=extras.briefing({},{});self.assertEqual(result['version'],'overview-v2');self.assertEqual(result['items'][0]['text'],'Current facts')
    def test_an_empty_ai_answer_does_not_leave_a_permanent_thinking_indicator(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'BRIEFING',Path(folder)/'brief.json'),patch('spending.run_ai',return_value='[]'):
            extras.write(extras.BRIEFING,{'updating':True,'items':[]})
            extras._phrase([{'text':'A fact','link':{}}],'claude',None)
            self.assertNotIn('updating',extras.read(extras.BRIEFING,{}))

if __name__=='__main__':unittest.main()
