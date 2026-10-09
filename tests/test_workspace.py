import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch

import app,spending,receipts,extras
from workspace import store,cashflow,performance,documents,backups,service,feeds,resources,exports

class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.patches=[]
        for module,key,value in [(store,'ROOT',self.root),(store,'DB',self.root/'cache/workspace.sqlite3'),(documents,'INBOX',self.root/'import-inbox'),
          (app,'CONFIG',self.root/'portfolio.json'),(app,'SETTINGS',self.root/'settings.json'),(app,'ACCOUNT_HISTORY',self.root/'history_accounts.csv'),(app,'OFFLINE',True),
          (spending,'FILE',self.root/'spending.json'),(receipts,'FILE',self.root/'receipts.json'),(receipts,'ATTACHMENTS',self.root/'attachments/receipts')]:
            p=patch.object(module,key,value);p.start();self.patches.append(p)
        (self.root/'portfolio.json').write_text(json.dumps(exports.synthetic()),encoding='utf-8')
        (self.root/'settings.json').write_text('{}',encoding='utf-8');self.data=spending.empty()
        self.data['accounts']={'bank':{'name':'Bank','role':'payment'}}
        spending.save(self.data)
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def tx(self,ident,d,amount,merchant='Shop',category='groceries',splits=None):
        r={'id':ident,'account':'bank','date':d,'amount':amount,'merchant':merchant,'merchant_key':merchant.lower(),'description':merchant,'category':category,'category_source':'user','checked':True}
        if splits:r['splits']=splits
        self.data['transactions'].append(r);spending.save(self.data);return r

class CashflowTests(Isolated):
    def test_recurring_uses_evidence_and_direction(self):
        for i in range(1,5):self.tx(str(i),f'2026-{i:02d}-05',-10,'Video','subscriptions')
        self.tx('income','2026-04-05',10,'Video','salary')
        found=cashflow.recurring(self.data,date(2026,4,10));self.assertEqual(len(found),1);self.assertEqual(found[0]['frequency'],'monthly');self.assertEqual(found[0]['next_date'],'2026-05-05');self.assertEqual(found[0]['evidence_ids'],['1','2','3','4'])
    def test_variable_shopping_not_subscription(self):
        for i,v in enumerate([10,150,40,280],1):self.tx(str(i),f'2026-{i:02d}-05',-v)
        self.assertEqual(cashflow.recurring(self.data,date(2026,4,10)),[])
    def test_transfers_excluded(self):
        for i in range(1,5):self.tx(str(i),f'2026-{i:02d}-05',-50,'Savings','transfer')
        # Add a valid transfer category if legacy fixture doesn't define this exact id.
        self.data['categories'].append({'id':'transfer','name':'Transfer','kind':'transfer','group':'Transfer'})
        self.assertEqual(cashflow.recurring(self.data,date(2026,4,10)),[])
    def test_forecast_needs_real_opening_balance(self):
        result=cashflow.forecast(self.data,[],today=date(2026,4,1))
        self.assertIsNone(result['opening_eur']);self.assertTrue(all(r['balance_eur'] is None for r in result['curve']))
    def test_manual_commitment_replaces_matching_pattern(self):
        rec=[{'id':'r','name':'Rent','amount_eur':-100,'next_date':'2026-04-02','frequency':'monthly','account':'bank','active':True,'evidence_ids':['x']}]
        bills=[{'name':'Confirmed rent','amount_eur':-110,'due':'2026-04-02','frequency':'monthly','recurrence_id':'r'}]
        r=cashflow.forecast(self.data,[],bills,days=30,today=date(2026,4,1),recurrences=rec,starting=1000)
        self.assertEqual(len(r['events']),1);self.assertEqual(r['checkpoints']['30'],890)
    def test_split_and_refund_count_once(self):
        self.tx('a','2026-04-01',-40,splits=[{'category':'groceries','amount':-25},{'category':'subscriptions','amount':-15}])
        self.tx('b','2026-04-02',10,category='groceries')
        r=cashflow.spending_analysis(self.data,'2026-04');c={x['category']:x['current_eur'] for x in r['categories']}
        self.assertEqual(c['groceries'],15);self.assertEqual(c['subscriptions'],15);self.assertEqual(r['trend'][0]['expenses_eur'],30)
    def test_budget_carryover(self):
        self.tx('a','2026-03-01',-60);self.tx('b','2026-04-01',-50)
        b={'name':'Food','category':'groceries','limit_eur':100,'period':'monthly','carryover':True,'since':'2026-03-01'}
        r=cashflow.spending_analysis(self.data,'2026-04',[b])['budgets'][0]
        self.assertEqual(r['carryover_eur'],40);self.assertEqual(r['available_eur'],90)
    def test_goal_no_assumed_growth(self):
        r=cashflow.goal_projection({'name':'Goal','target_eur':1200,'saved_eur':600,'due':'2026-10-01'},date(2026,4,1));self.assertEqual(r['monthly_required_eur'],100)

class PerformanceTests(Isolated):
    def test_xirr_known_one_year_cashflow(self):
        r=performance.xirr([('2025-01-01',-1000),('2026-01-01',1100)]);self.assertAlmostEqual(r['value_pct'],10,delta=.02)
    def test_xirr_multiple_roots_are_withheld(self):
        r=performance.xirr([('2024-01-01',-100),('2025-01-01',230),('2026-01-01',-132)]);self.assertIsNone(r['value_pct']);self.assertIn('Multiple',r['reason'])
    def test_cashflow_adjustment_not_price_reconstruction(self):
        r=performance.calculate([{'date':'2026-01-01','value':1000},{'date':'2026-02-01','value':1600},{'date':'2026-03-01','value':1760}],[{'date':'2026-02-01','amount_eur':500}],True)
        self.assertAlmostEqual(r['twr_pct'],21);self.assertEqual(r['profit_eur'],260)
    def test_unconfirmed_coverage_withholds_returns(self):
        r=performance.calculate([{'date':'2026-01-01','value':1000},{'date':'2026-03-01','value':1760}],[],False)
        self.assertIsNone(r['twr_pct']);self.assertIsNone(r['profit_eur'])
    def test_missing_flow_valuation_withholds_twr(self):
        r=performance.calculate([{'date':'2026-01-01','value':1000},{'date':'2026-03-01','value':1760}],[{'date':'2026-02-01','amount_eur':500}],True)
        self.assertIsNone(r['twr_pct']);self.assertIsNotNone(r['modified_dietz_pct'])
    def test_ledger_dedup_preserves_identical_same_day_trades(self):
        r={'account':'Broker','date':'2026-01-01','type':'buy','currency':'EUR','amount':-100,'units':10,'instrument':'ABC'}
        first=performance.ingest([r,r]);second=performance.ingest([r,r]);self.assertEqual(first['added'],2);self.assertEqual(second['added'],0);self.assertEqual(len(performance.ledger()),2)
    def test_entire_import_validated_before_any_write(self):
        good={'account':'Broker','date':'2026-01-01','type':'buy','currency':'EUR','amount':-100,'units':10}
        with self.assertRaises(ValueError):performance.ingest([good,{**good,'amount':float('nan')}])
        self.assertEqual(performance.ledger(),[])
    def test_fifo_realized_and_remaining_lots(self):
        rows=[{'date':'2025-01-01','type':'buy','units':10,'amount_eur':-100},{'date':'2025-02-01','type':'buy','units':10,'amount_eur':-200},{'date':'2025-03-01','type':'sell','units':15,'amount_eur':450}]
        r=performance.fifo(rows,5);self.assertTrue(r['complete']);self.assertEqual(r['realized_eur'],250);self.assertEqual(r['remaining_cost_eur'],100)
    def test_fifo_missing_opening_lots_withheld(self):
        r=performance.fifo([{'date':'2025-01-01','type':'sell','units':10,'amount_eur':150}],0);self.assertFalse(r['complete']);self.assertIsNone(r['realized_eur'])
    def test_unconverted_non_eur_trade_not_assumed_eur(self):
        r=performance.normalize({'account':'Broker','date':'2025-01-01','type':'buy','currency':'USD','amount':-100,'units':10});self.assertIsNone(r['amount_eur'])
    def test_bond_known_par_coupon(self):
        r=performance.bond_metrics(1000,1000,5,'2027-01-01',1,date(2026,1,1));self.assertAlmostEqual(r['yield_to_maturity_pct'],5,delta=.02);self.assertEqual(r['cashflows'][-1]['amount_eur'],1050)

class EvidenceTests(Isolated):
    def test_intake_retains_immutable_original(self):
        documents.INBOX.mkdir();p=documents.INBOX/'invoice.txt';p.write_text('Example invoice 123',encoding='utf-8');os.utime(p,(1,1))
        with patch.object(documents,'index_sources',return_value=0):self.assertEqual(documents.scan()['added'],1);self.assertEqual(documents.scan()['added'],0)
        item=documents.intake()[0];p.unlink();original,_=receipts.source(item['source_id']);self.assertEqual(original.read_text(),'Example invoice 123')
    def test_intake_symlinks_not_followed(self):
        documents.INBOX.mkdir()
        # Junction/symlink creation is privilege-dependent on Windows; scanner's explicit gate is verified.
        with patch.object(Path,'is_symlink',return_value=True):
            p=documents.INBOX/'file.txt';p.write_text('ignored');os.utime(p,(1,1));self.assertEqual(documents.scan()['added'],0)
    def test_search_numeric_and_missing_invoice_filter(self):
        self.tx('small','2026-04-01',-20,'Amazon');self.tx('large','2026-04-01',-40,'Amazon')
        r=service.search('Amazon purchases above 30 without invoice');self.assertEqual([x['id'] for x in r['items']],['large'])
    def test_refund_cannot_exceed_real_bank_credit(self):
        self.tx('refund','2026-04-01',10,'Amazon','salary')
        receipts.save({'documents':[{'id':'invoice','items':[{'id':'product'}]}],'sources':[]})
        d={'name':'Return','document_id':'invoice','item_id':'product','transaction_id':'refund','amount_eur':8,'note':''}
        service.save_record('refund',d)
        with self.assertRaises(ValueError):service.save_record('refund',d)
    def test_record_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):service.validate('goal',{'name':'Goal','target_eur':100,'saved_eur':10,'due':'2027-01-01','secret':'x'})
    def test_fund_weights_over_100_rejected(self):
        r={'fund_isin':'FUND','instrument':'ABC','name':'A','weight_pct':70,'as_of':'2026-01-01','source_id':'x'}
        service.save_record('fundholding',r)
        with self.assertRaises(ValueError):service.save_record('fundholding',{**r,'instrument':'DEF','weight_pct':40})
    def test_audit_before_after_values(self):
        r=store.put('note',{'name':'A'},'x');store.put('note',{'name':'B'},'x');store.delete('note','x')
        audit=store.rows('SELECT * FROM audit ORDER BY id');self.assertEqual(len(audit),3);self.assertEqual(json.loads(audit[1]['before_json'])['name'],'A')
    def test_document_comparison(self):
        store.put('document',{'name':'Before','text':'Revenue 10\nRisk stable'},'a');store.put('document',{'name':'After','text':'Revenue 12\nRisk changed'},'b')
        r=documents.comparison('a','b');self.assertTrue(any('+Revenue 12' in line for line in r['changes']))

class BackupTests(Isolated):
    def test_encrypted_complete_backup_restores_separate_copy(self):
        r=backups.create('long-demo-password');path=backups.folder()/r['name'];self.assertNotIn(b'Demo Broker',path.read_bytes());before=(self.root/'portfolio.json').read_bytes()
        restored=backups.restore_preview(r['name'],'long-demo-password');self.assertTrue(restored['verified']);self.assertEqual((self.root/'portfolio.json').read_bytes(),before)
        self.assertEqual((self.root/restored['folder']/'portfolio.json').read_bytes(),before)
    def test_wrong_password_and_modified_ciphertext_rejected(self):
        r=backups.create('long-demo-password')
        with self.assertRaises(ValueError):backups.restore_preview(r['name'],'wrong-long-password')
        p=backups.folder()/r['name'];raw=bytearray(p.read_bytes());raw[-1]^=1;p.write_bytes(raw)
        with self.assertRaises(ValueError):backups.restore_preview(r['name'],'long-demo-password')
    def test_backup_path_traversal_rejected(self):
        with self.assertRaises(ValueError):backups.restore_preview('../outside.wealthbackup')
    def test_backup_includes_consistent_databases_and_sources(self):
        store.put('note',{'name':'Evidence'},'n');receipts.store_source({'name':'proof.txt','data':base64.b64encode(b'proof').decode()})
        r=backups.create('long-demo-password');v=backups.restore_preview(r['name'],'long-demo-password');names={x['name'] for x in v['manifest']}
        self.assertIn('cache/workspace.sqlite3',names);self.assertTrue(any(n.startswith('attachments/') for n in names))

class PublicAndExportTests(Isolated):
    def test_public_source_no_private_identifiers(self):
        for value in ('person@example.com','NL12ABNA0123456789','http://localhost'):
            with self.assertRaises(ValueError):resources.public_term(value)
    def test_public_source_requires_online_or_cached_evidence(self):
        with self.assertRaises(ValueError):resources.query('worldbank','NL')
    def test_source_failure_retains_cached_result(self):
        key=hashlib.sha256(b'worldbank|NL').hexdigest();store.execute('INSERT INTO public_cache VALUES(?,?,?,?)',(key,'worldbank','2020-01-01T00:00:00+00:00',json.dumps({'source':'worldbank','rows':[{'value':2}]})))
        with patch.object(app,'OFFLINE',False),patch.object(resources,'request',side_effect=ValueError('unavailable')):
            r=resources.query('worldbank','NL',True);self.assertTrue(r['stale']);self.assertEqual(r['rows'][0]['value'],2)
    def test_feed_parser_rejects_entities(self):
        with self.assertRaises(ValueError):feeds.parse(b'<!DOCTYPE x [<!ENTITY a "bad">]><rss/>')
    def test_feed_parser_returns_safe_public_link(self):
        r=feeds.parse(b'<rss><channel><item><title>News</title><link>javascript:alert(1)</link></item></channel></rss>');self.assertEqual(r[0]['url'],'')
    def test_private_feed_network_rejected_before_connect(self):
        with patch.object(feeds.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):feeds.fetch('https://example.com/feed')
    def test_csv_formula_injection_escaped_but_numbers_preserved(self):
        self.assertEqual(exports.cell('=SUM(A1)'),"'=SUM(A1)");self.assertEqual(exports.cell(-10),-10)
    def test_worldbank_preserves_nulls_as_missing(self):
        r=resources.rows_worldbank([{},[{'date':'2025','value':None},{'date':'2024','value':2,'country':{'value':'NL'},'indicator':{'value':'Inflation','id':'CPI'}}]])
        self.assertEqual(len(r),1);self.assertEqual(r[0]['value'],2)

if __name__=='__main__':unittest.main()
