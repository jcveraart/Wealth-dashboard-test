import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import extras,portfolio_notes

class Classifications(unittest.TestCase):
    def test_placeholder_regions_are_missing_but_known_exposure_is_kept(self):
        for value in (None,'','Other','UNKNOWN','Unclassified'):self.assertTrue(extras.classification_missing(value))
        self.assertFalse(extras.classification_missing('Global'))

    def test_only_identified_and_valid_ai_fields_are_retained(self):
        cfg={'accounts':[{'positions':[{'name':'World fund','isin':'IE00EXAMPLE1','category':'Broad ETF','region':'Other'}]}],'managed':{}}
        answer={'IE00EXAMPLE1':{'region':'Global','sector':'Diversified','currency':'USD','confidence':'high','basis':'World equity mandate'},'foreign':{'region':'Europe','confidence':'high'}}
        with patch('spending.run_ai',return_value=json.dumps(answer)):
            got=extras.classify(cfg,lambda p:p['isin'],'claude',None)
        self.assertEqual(set(got),{'IE00EXAMPLE1'})
        self.assertEqual(got['IE00EXAMPLE1']['region'],'Global')
        self.assertTrue(got['IE00EXAMPLE1']['classification_note'].startswith('AI inferred'))
        answer['IE00EXAMPLE1'].update(region='Other',currency='EURO',confidence='low')
        with patch('spending.run_ai',return_value=json.dumps(answer)):
            self.assertEqual(extras.classify(cfg,lambda p:p['isin'],'claude',None),{})

    def test_classification_batches_avoid_unbounded_prompts_and_financial_data(self):
        positions=[{'name':f'Fund {i}','isin':str(i),'value_eur':9000,'units':100} for i in range(41)]
        with patch('spending.run_ai',return_value='{}') as model:
            extras.classify({'accounts':[{'positions':positions}],'managed':{}},lambda p:p['isin'],'claude',None)
        self.assertEqual(model.call_count,3)
        for call in model.call_args_list:
            payload=json.loads(call.args[0]);self.assertLessEqual(len(payload),20)
            self.assertNotIn('units',json.dumps(payload));self.assertNotIn('value_eur',json.dumps(payload))
            self.assertEqual(call.kwargs['kind'],'holding','Use the connected model for investment identity instead of repeated local-model retries')

class PortfolioNotes(unittest.TestCase):
    def test_price_history_accepts_the_same_proxy_shapes_as_portfolio_state(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'HIST_DIR',Path(folder)):
            for weights in ({'IWDA.AS':.8,'IEAC.AS':.2},[{'symbol':'IWDA.AS','weight':.8},{'symbol':'IEAC.AS','weight':.2}]):
                result=extras.price_history({'managed':{'proxy':weights}}, {},offline=True)
                self.assertEqual(set(result['proxy']),{'IWDA.AS','IEAC.AS'})
    def state(self):return {'positions':[{'name':'Company A','account':'Broker A','value':1000,'day_change':25,'live':True,'category':'Stock','region':'North America'},{'name':'Company B','account':'Broker B','value':500,'day_change':-40,'live':True,'category':'Stock','region':'Europe'},{'name':'Bond','account':'Broker A','value':200,'category':'Bond','region':'Europe'}],'status':{'last_refresh':'2026-10-08T10:00:00'}}
    def test_notes_use_only_selected_account_and_asset_class(self):
        text=json.dumps(portfolio_notes.facts(self.state(),'Broker A','shares'))
        self.assertIn('Company A',text);self.assertNotIn('Company B',text);self.assertNotIn('Bond',text);self.assertIn('100.0%',text)
    def test_offline_notes_are_cached_without_launching_ai(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch('spending.run_ai') as model:
            one=portfolio_notes.briefing(self.state(),'Broker A');two=portfolio_notes.briefing(self.state(),'Broker A')
            self.assertEqual(one,two);self.assertEqual(one['by'],'facts');self.assertFalse(model.called)
    def test_ai_can_select_facts_but_cannot_add_model_generated_figures(self):
        with tempfile.TemporaryDirectory() as folder,patch('spending.run_ai',return_value='[1, 1, 99, 0, "fake claim"]'):
            path=Path(folder)/'note.json';out={'date':'2026-10-08'};facts=portfolio_notes.facts(self.state())
            portfolio_notes._phrase('test',path,out,facts,'claude',None)
            result=json.loads(path.read_text());self.assertEqual(result['items'],[facts[1],facts[0]])

if __name__=='__main__':unittest.main()
