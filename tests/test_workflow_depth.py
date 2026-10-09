import io,json,zipfile
from datetime import date
from unittest.mock import patch
from test_workspace import Isolated
from workspace import assets,context,chat_tools,performance,service,store,research,maintenance,exports,undo,cashflow
from intelligence import tools
import app,receipts

class AssetDepth(Isolated):
    def test_fda_no_matches_is_valid_empty_response(self):
        import io,urllib.error
        from workspace import resources
        error=urllib.error.HTTPError('https://api.fda.gov/drug/drugsfda.json',404,'No matches',{},io.BytesIO(b'{"error":{"code":"NOT_FOUND","message":"No matches found!"}}'))
        opener=__import__('unittest').mock.MagicMock();opener.open.side_effect=error
        with patch('urllib.request.build_opener',return_value=opener):self.assertEqual(resources.request('https://api.fda.gov/drug/drugsfda.json',empty_not_found=True),{'results':[]})
    def test_calendar_schedule_keeps_month_end_anchor(self):
        r=cashflow.forecast(self.data,[],[{'name':'Rent','amount_eur':-10,'due':'2026-01-31','frequency':'monthly'}],days=90,today=date(2026,1,1),starting=100)
        self.assertEqual([e['date'] for e in r['events']],['2026-01-31','2026-02-28','2026-03-31'])
    def test_payment_balance_is_used_without_guessing(self):
        r=cashflow.forecast(self.data,[{'name':'Bank','value':200,'kind':'payment'}],today=date(2026,1,1));self.assertEqual(r['opening_eur'],200)
    def test_loan_with_zero_rate_and_lump_sum(self):
        r=assets.loan_schedule(1000,0,100,200);self.assertEqual(r['months'],8);self.assertEqual(r['interest_eur'],0);self.assertEqual(r['curve'][-1]['balance_eur'],0)
    def test_loan_payment_must_cover_interest(self):self.assertIsNone(assets.loan_schedule(1000,12,5)['months'])
    def test_fund_weights_validate_before_any_write(self):
        rows=[{'fund_isin':'F','instrument':'A','name':'A','weight_pct':60,'as_of':'2026-01-01'},{'fund_isin':'F','instrument':'B','name':'B','weight_pct':60,'as_of':'2026-01-01'}]
        with self.assertRaises(ValueError):assets.ingest_funds(rows,'source')
        self.assertEqual(store.records('fundholding'),[])
    def test_fund_versions_retained_and_partial_absence_unknown(self):
        assets.ingest_funds([{'fund_isin':'IE00B4L5Y983','instrument':'A','name':'A','weight_pct':5,'as_of':'2026-01-01'}],'first')
        assets.ingest_funds([{'fund_isin':'IE00B4L5Y983','instrument':'B','name':'B','weight_pct':8,'as_of':'2026-02-01'}],'second')
        r=assets.fund_overlap();self.assertEqual(r['coverage'][0]['covered_pct'],8);self.assertEqual(len(r['changes']),2);self.assertTrue(all(c['change_pp'] is None for c in r['changes']))
    def test_unknown_order_of_same_day_trades_withholds_fifo(self):
        r=performance.fifo([{'date':'2026-01-01','type':'buy','units':10,'amount_eur':-100},{'date':'2026-01-01','type':'sell','units':5,'amount_eur':60}],5)
        self.assertFalse(r['complete']);self.assertIsNone(r['realized_eur'])
    def test_execution_time_allows_fifo(self):
        r=performance.fifo([{'date':'2026-01-01','executed_at':'2026-01-01T10:00:00','type':'buy','units':10,'amount_eur':-100},{'date':'2026-01-01','executed_at':'2026-01-01T11:00:00','type':'sell','units':5,'amount_eur':60}],5)
        self.assertTrue(r['complete']);self.assertEqual(r['realized_eur'],10)
    def test_transfer_requires_verified_opening_lots(self):
        r=performance.fifo([{'date':'2026-01-01','type':'transfer-in','units':10}],10);self.assertFalse(r['complete'])
    def test_undo_restores_imported_financial_rows_only(self):
        bid='20261008-120000-123456';undo.snapshot(bid)
        performance.ingest([{'account':'A','date':'2026-01-01','type':'deposit','currency':'EUR','amount':100}])
        store.put('goal',{'name':'Keep my later goal'},'g');undo.restore(bid)
        self.assertEqual(performance.ledger(),[]);self.assertEqual(store.record('goal','g')['name'],'Keep my later goal')
    def test_undo_rejects_path_traversal(self):
        with self.assertRaises(ValueError):undo.path('../portfolio.json')
    def test_search_account_date_and_kind(self):
        self.tx('a','2026-01-01',-50,'Shop');self.tx('b','2026-02-01',-60,'Shop')
        r=service.search('shop after:2026-02-01 account:bank type:payment');self.assertEqual([x['id'] for x in r['items']],['b'])
    def test_full_document_search_matches_distant_terms(self):
        store.put('document',{'name':'Test','text':'alpha '+'filler '*100+'omega','source_id':'s'},'d')
        r=service.search('alpha omega');self.assertTrue(any(x['kind']=='document' for x in r['items']))
    def test_scope_never_advertises_other_local_context(self):
        names={d['name'] for d in tools.definitions('documents')};self.assertIn('get_purchase_evidence',names);self.assertNotIn('get_portfolio',names);self.assertNotIn('get_cashflow_outlook',names)
        self.assertTrue(tools.safe_call('get_portfolio',{},'documents')['unavailable'])
    def test_selected_system_excludes_personal_notes_and_other_balances(self):
        with patch.object(app,'read_notes',return_value='SECRET NOTE NEVER SHARE'):
            prompt=context.system('documents');self.assertNotIn('SECRET NOTE',prompt);self.assertNotIn('Demo Loan',prompt);self.assertNotIn('Demo Broker',prompt)
    def test_invalid_context_cannot_expand_access(self):
        with self.assertRaises(ValueError):tools.definitions('../../all')
    def test_weekly_maintenance_does_not_repeat_backups_or_briefings(self):
        with patch('workspace.backups.create',return_value={'name':'test'} ) as backup,patch('workspace.feeds.refresh',return_value={'feeds':[]}):
            maintenance.tick();maintenance.tick();self.assertEqual(backup.call_count,1);self.assertEqual(len(store.records('briefing')),1)
    def test_rate_history_retains_distinct_effective_rates(self):
        assets.record_rates();assets.record_rates();self.assertEqual(len(store.records('ratepoint')),2)
        cfg=service.cfg();cfg['savings'][1]['rate_pct']=3;cfg['savings'][1]['snapshot_date']='2026-10-09';app.save(app.CONFIG,cfg);assets.record_rates();self.assertEqual(len(store.records('ratepoint')),3)
    def test_fictional_demo_has_no_owner_files_or_credentials(self):
        original_root=exports.store.ROOT
        # Demo source is the staged app, with synthetic configuration created independently.
        with patch.object(exports.store,'ROOT',app.HERE):raw=exports.demo_bundle()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist();self.assertFalse(any(n.startswith(('.git/','cache/','attachments/','backups/')) for n in names))
            text='\n'.join(z.read(n).decode() for n in names if not n.endswith(('.png','.jpg','.jpeg'))).lower();self.assertNotIn('jan example-owner',text);self.assertNotIn('jcveraart/'+'wealth-dashboard.git',text)
            self.assertEqual(json.loads(z.read('settings.json')),{});self.assertEqual(json.loads(z.read('portfolio.json'))['accounts'][0]['name'],'Demo Broker')
    def test_esef_reports_units_context_scale_and_unsupported_format(self):
        raw=b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:x="http://www.xbrl.org/2003/instance"><x:context id="c"><x:period><x:instant>2025-12-31</x:instant></x:period></x:context><x:unit id="eur"><x:measure>iso4217:EUR</x:measure></x:unit><ix:nonFraction name="ifrs:Revenue" contextRef="c" unitRef="eur" format="ixt:num-comma-decimal" scale="3">1.234,5</ix:nonFraction><ix:nonFraction name="ifrs:Other" contextRef="c" unitRef="eur" format="ixt:unsupported">one</ix:nonFraction></html>'
        r=research.parse_esef(raw);self.assertEqual(r['facts'][0]['value'],1234500);self.assertEqual(r['facts'][0]['context']['instant'],'2025-12-31');self.assertEqual(r['facts'][0]['unit'],'iso4217:EUR');self.assertIsNone(r['facts'][1]['value'])
    def test_esef_entities_are_rejected(self):
        with self.assertRaises(ValueError):research.parse_esef(b'<!DOCTYPE x [<!ENTITY e "boom">]><x/>')
    def test_calendar_export_escapes_newlines(self):
        store.put('goal',{'name':'Goal\nBEGIN:EVIL','due':'2027-01-01'},'g');text,name,mime=exports.export('calendar',{});self.assertIn('Goal\\nBEGIN:EVIL',text);self.assertNotIn('\r\nBEGIN:EVIL',text)
