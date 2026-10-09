import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cash_notes,extras

class CashNotes(unittest.TestCase):
    def state(self):return {'savings':[{'name':'Flexible','value':3000,'rate_pct':3.0},{'name':'Fixed','value':10000,'rate_pct':4,'maturity':'2029-01-01'},{'name':'Marked investment but flexible','value':1000,'invest':True,'rate_pct':2.5}], 'accounts':[{'name':'Broker','cash':250,'value':25000},{'name':'Flexible','cash':3000}], 'debts':[{'name':'DUO loan','balance':10000,'rate_pct':2,'monthly_payment_eur':None},{'name':'Grant','balance':1000,'rate_pct':0,'expected_gift':True}], 'profile':{'buffer_months':4},'spend_month':1000}
    def test_excludes_locked_deposits_includes_only_broker_cash_and_deduplicates(self):
        rows=cash_notes.liquid_rows(self.state());self.assertEqual([r['name'] for r in rows],['Flexible','Marked investment but flexible','Broker']);self.assertEqual(sum(r['value'] for r in rows),4250)
        self.assertIsNone(rows[-1]['rate_pct'])
    def test_comparison_uses_marginal_saved_rates_and_reports_duo_gaps(self):
        facts=cash_notes.facts(self.state());text=json.dumps(facts)
        self.assertIn('10.00 EUR',text);self.assertNotIn('Fixed',text);self.assertNotIn('Grant',text);self.assertIn('not recorded',text);self.assertIn('4.0 months',text);self.assertIn('not an equivalent cash return',text)
    def test_missing_rate_is_not_zero_and_gift_does_not_trigger_advice(self):
        state=self.state();state['debts'][0]['rate_pct']=None
        facts=cash_notes.facts(state);self.assertFalse(any(f['kind']=='comparison' for f in facts));self.assertIn('interest rate is missing',json.dumps(facts))
    def test_offline_briefing_is_cached_and_contains_context(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch('spending.run_ai') as model:
            one=cash_notes.briefing(self.state());two=cash_notes.briefing(self.state());self.assertEqual(one,two);self.assertFalse(model.called);self.assertIn('duo',[f['kind'] for f in one['items']])
    def test_changed_rate_changes_cache_and_ai_cannot_add_claims(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)):
            state=self.state();before=cash_notes.briefing(state);state['debts'][0]['rate_pct']=4;after=cash_notes.briefing(state);self.assertNotEqual(before['items'],after['items'])
            path=Path(folder)/'test.json';facts=cash_notes.facts(state)
            with patch('spending.run_ai',return_value='[1,1,99,"buy bonds"]'):
                cash_notes._choose('test',path,{},facts,'claude',None)
            output=json.loads(path.read_text());self.assertEqual(output['items'],[facts[1]]);self.assertFalse(output['updating'])
    def test_ai_failure_retains_recorded_observations(self):
        with tempfile.TemporaryDirectory() as folder,patch('spending.run_ai',side_effect=RuntimeError('offline')):
            path=Path(folder)/'test.json';out={'items':[{'text':'recorded'}],'updating':True}
            cash_notes._choose('test',path,out,[],'claude',None);got=json.loads(path.read_text());self.assertEqual(got['items'],out['items']);self.assertFalse(got['updating'])

if __name__=='__main__':unittest.main()
