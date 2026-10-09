import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import company_notes,extras

class CompanyNotes(unittest.TestCase):
    def research(self):return {'symbol':'DEMO','name':'Example','status':'current','overview':'Example provides payment services.','website':'https://example.com','metadata':{'retrieved_at':'2026-10-08'},'fundamentals':{'price':10},'portfolio_fit':{'hhi_before':.2,'hhi_after':.18,'allocation_pct':5},'news':[{'title':'Recorded headline','url':'https://example.com/news','date':'2026-10-01'}],'filings':[]}
    def test_dossier_has_dated_headline_and_backend_fit(self):
        payload,items,sources=company_notes.dossier(self.research());self.assertIn('reduces',items[-1]['text']);self.assertIn('2026-10-01',items[1]['text']);self.assertEqual(sources[1]['url'],'https://example.com/news');self.assertNotIn('payments',payload)
    def test_rejects_unprovided_sources_numbers_and_urls(self):
        sources=[{'id':0,'url':'https://example.com'}]
        good={'topic':'News','text':'Recorded demand improved; verify the reporting period.','sources':[0]}
        self.assertEqual(company_notes.validated_items([good],sources),[good])
        for invalid in ({**good,'text':'Buy at 100 EUR'},{**good,'sources':[9]},{**good,'sources':[]},{**good,'text':'https://bad.example'}, {'topic':'Unknown','text':'fake','sources':[]}):self.assertFalse(company_notes.validated_items([invalid],sources))
        self.assertIsNone(company_notes.safe_url('javascript:alert(1)'))
    def test_offline_briefing_is_fast_cached_and_no_model_call(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch('company_notes.service.research',return_value=self.research()),patch('spending.run_ai') as model:
            one=company_notes.briefing('DEMO');two=company_notes.briefing('DEMO');self.assertEqual(one,two);self.assertFalse(model.called)
    def test_price_cache_is_quote_currency_not_adjusted_returns(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch('company_notes.store.rows',return_value=[{'date':'2026-10-01','close':9,'currency':'EUR','adjusted':1}]):
            first=company_notes.price_history('DEMO',offline=True);self.assertTrue(first['adjusted']);self.assertFalse(first['updating'])
            path=Path(folder)/'company-prices'/(__import__('hashlib').sha256(b'DEMO').hexdigest()[:24]+'.json');extras.write(path,{'symbol':'DEMO','rows':[{'date':'2026-10-01','close':10}],'currency':'EUR','adjusted':False,'at':time.time()})
            second=company_notes.price_history('DEMO',offline=True);self.assertFalse(second['adjusted']);self.assertEqual(second['rows'][0]['close'],10)
    def test_stale_price_cache_retains_actual_rows(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)):
            path=Path(folder)/'company-prices'/(__import__('hashlib').sha256(b'DEMO').hexdigest()[:24]+'.json');extras.write(path,{'symbol':'DEMO','rows':[{'date':'2025-10-01','close':8}],'currency':'EUR','adjusted':False,'at':1})
            result=company_notes.price_history('DEMO',offline=True);self.assertTrue(result['stale']);self.assertFalse(result['adjusted']);self.assertEqual(result['rows'][0]['close'],8)
    def test_model_failure_keeps_factual_briefing(self):
        with tempfile.TemporaryDirectory() as folder,patch('spending.run_ai',side_effect=RuntimeError('offline')):
            path=Path(folder)/'notes.json';out={'items':[{'text':'Recorded'}],'sources':[]}
            company_notes._phrase('test',path,out,{},'claude',None);self.assertEqual(json.loads(path.read_text())['items'],out['items'])

if __name__=='__main__':unittest.main()
