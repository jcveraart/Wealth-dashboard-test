import hashlib,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import cash_notes,company_notes,portfolio_notes,page_notes,extras

class ReadyBriefings(unittest.TestCase):
    def state(self):return {'savings':[{'name':'Cash','value':1000,'rate_pct':3}], 'accounts':[], 'debts':[{'name':'Loan','balance':500,'rate_pct':2}], 'positions':[{'name':'Stock','value':100,'category':'Stock','region':'Europe'}], 'advice':[{'id':'one','title':'Check loan','detail':'Use the recorded rate.'},{'id':'done','title':'Already done'}], 'advice_done':[{'id':'done'}], 'todos':[{'text':'Check statement','done':False}], 'intelligence':{}}
    def test_readiness_never_writes_or_calls_a_model(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch('extras.write') as write,patch('spending.run_ai') as model:
            state=self.state();self.assertTrue(cash_notes.peek(state)['items']);self.assertTrue(portfolio_notes.peek(state)['items']);self.assertTrue(page_notes.peek('advice',state)['items']);self.assertTrue(page_notes.peek('opportunities',state)['items'])
            r={'symbol':'DEMO','overview':'Example business','metadata':{},'news':[],'portfolio_fit':{}};self.assertTrue(company_notes.peek(r)['items']);self.assertFalse(write.called);self.assertFalse(model.called)
    def test_ready_cash_returns_saved_ai_for_same_recorded_facts(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)):
            state=self.state();items=cash_notes.facts(state);ident=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()[:24]
            extras.write(Path(folder)/'cash-notes'/f'{ident}.json',{'at':time.time(),'by':'claude','items':[items[0]]})
            self.assertEqual(cash_notes.peek(state)['by'],'claude');state['debts'][0]['rate_pct']=4;self.assertEqual(cash_notes.peek(state)['by'],'facts')
    def test_advice_is_scoped_and_dismissed_or_completed_items_stay_out(self):
        items=page_notes.facts('advice',self.state());self.assertIn('Check loan',json.dumps(items));self.assertNotIn('Already done',json.dumps(items));self.assertNotIn('Stock',json.dumps(items))
    def test_model_can_only_select_recorded_page_observations(self):
        with tempfile.TemporaryDirectory() as folder,patch('spending.run_ai',return_value='[0, 99, "invented claim", 0]'):
            items=page_notes.facts('advice',self.state());path=Path(folder)/'notes.json';page_notes._choose('test',path,{},items,'claude',None)
            result=json.loads(path.read_text());self.assertEqual(result['items'],[items[0]]);self.assertEqual(result['by'],'claude')
    def test_unknown_page_is_rejected(self):
        with self.assertRaises(ValueError):page_notes.peek('settings',self.state())
    def test_saved_opportunity_keeps_risk_and_evidence_date(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)):
            extras.write(Path(folder)/'ideas.json',{'date':'2026-10-08','ideas':[{'title':'Example idea','why':'Recorded rationale','fits':'Recorded fit','risk':'Liquidity risk'}]})
            item=page_notes.facts('opportunities',self.state())[0];self.assertEqual(item['risk'],'Liquidity risk');self.assertEqual(item['source_date'],'2026-10-08')

if __name__=='__main__':unittest.main()
