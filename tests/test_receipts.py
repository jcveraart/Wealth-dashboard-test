import base64, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import receipts, spending

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.patches=[patch.object(receipts,'FILE',self.root/'receipts.json'),patch.object(receipts,'ATTACHMENTS',self.root/'attachments'),patch.object(spending,'FILE',self.root/'spending.json')]
        for p in self.patches:p.start()
        d=spending.empty();d['accounts']={'checking':{'name':'Checking','role':'payment'}}
        d['transactions']=[{'id':'bank-40','date':'2026-10-02','amount':-40.0,'merchant':'Amazon','description':'AMZN Mktp order A1','key':'amazon','account':'checking','category':'online-shopping','category_source':'user','country':'NL','country_source':'user'}]
        spending.save(d)
        self.file={'name':'invoice.pdf','media_type':'application/pdf','data':base64.b64encode(b'%PDF-1.4 synthetic invoice').decode()}
        self.doc={'source_name':'invoice.pdf','supplier':'Amazon','invoice_number':'EXAMPLE-A1','order_number':'A1','date':'2026-10-01','currency':'EUR','total':40,
            'items':[{'description':'USB charger','quantity':1,'unit_price':25,'total':25,'category':'electronics','sku':None},
                     {'description':'Book','quantity':1,'unit_price':15,'total':15,'category':'education','sku':None}]}
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def add(self):
        receipts.add([self.doc],[self.file]);return next(d['id'] for d in receipts.read()['documents'] if d['invoice_number']==self.doc['invoice_number'])
    def link(self,id=None,amount=40):
        receipts.edit({'action':'link','id':id or self.add(),'transaction_id':'bank-40','amount_eur':amount})
    def test_invoice_is_evidence_not_another_expense(self):
        self.add();self.assertEqual(len(spending.load()['transactions']),1);self.assertEqual(spending.load()['transactions'][0]['amount'],-40)
        self.assertEqual(receipts.view()['documents'][0]['links'],[])
        self.assertEqual(receipts.view()['documents'][0]['candidates'][0]['transaction_id'],'bank-40')
    def test_reimport_and_different_scan_of_same_invoice_are_deduplicated(self):
        self.add();self.assertEqual(receipts.add([self.doc],[self.file])['duplicates'],1)
        second={**self.file,'data':base64.b64encode(b'%PDF-1.4 a second synthetic scan').decode()}
        receipts.add([self.doc],[second]);self.assertEqual(len(receipts.read()['documents']),1)
        self.assertEqual(len(receipts.read()['documents'][0]['attachments']),2)
    def test_match_requires_exact_amount_and_direction(self):
        doc=receipts.validate(self.doc);txs=spending.load()['transactions']
        self.assertEqual(len(receipts.candidates(doc,txs)),1)
        self.assertEqual(receipts.candidates(doc,[{**txs[0],'amount':-40.01}]),[])
        self.assertEqual(receipts.candidates(doc,[{**txs[0],'amount':40}]),[])
    def test_unknown_currency_does_not_get_a_euro_match(self):
        doc=receipts.validate({**self.doc,'currency':'USD'})
        self.assertEqual(receipts.candidates(doc,spending.load()['transactions']),[])
    def test_ambiguous_payments_remain_suggestions(self):
        d=spending.load();d['transactions'].append({**d['transactions'][0],'id':'bank-second'});spending.save(d)
        self.add();out=receipts.view()['documents'][0]
        self.assertEqual(len(out['candidates']),2);self.assertEqual(out['links'],[])
    def test_split_by_products_preserves_bank_amount(self):
        id=self.add();self.link(id)
        receipts.edit({'action':'split-payment','id':id,'transaction_id':'bank-40'})
        t=spending.load()['transactions'][0]
        self.assertEqual(t['amount'],-40);self.assertEqual(sum(p['amount'] for p in t['splits']),-40)
        self.assertEqual([p['category'] for p in t['splits']],['electronics','education'])
    def test_partial_line_totals_cannot_change_the_bank_payment(self):
        self.doc['items'][0]['total']=24.99
        id=self.add();self.link(id)
        with self.assertRaises(ValueError):receipts.edit({'action':'split-payment','id':id,'transaction_id':'bank-40'})
        self.assertNotIn('splits',spending.load()['transactions'][0])
    def test_allocations_cannot_overfill_a_payment(self):
        first=self.add();self.link(first,30)
        self.doc['invoice_number']='EXAMPLE-B2';self.doc['total']=20;self.doc['items']=[]
        second=self.add()
        with self.assertRaises(ValueError):self.link(second,20)
        self.assertEqual(receipts.read()['documents'][1]['links'],[])
    def test_two_invoices_can_explain_one_payment(self):
        self.doc['total']=25;self.doc['items']=self.doc['items'][:1]
        first=self.add();self.link(first,25)
        self.doc={**self.doc,'invoice_number':'EXAMPLE-B2','total':15,'items':[{'description':'Book','quantity':1,'unit_price':15,'total':15,'category':'education','sku':None}]}
        second=self.add();self.link(second,15)
        receipts.edit({'action':'split-payment','id':second,'transaction_id':'bank-40'})
        self.assertEqual(sum(p['amount'] for p in spending.load()['transactions'][0]['splits']),-40)
    def test_original_bytes_are_kept_not_the_ai_resize(self):
        self.file.update(original_data=base64.b64encode(b'original evidence').decode())
        self.add();d=receipts.read()['documents'][0];a=d['attachments'][0]
        file,_=receipts.attachment(d['id'],a['id']);self.assertEqual(file.read_bytes(),b'original evidence')
    def test_source_paths_are_not_exposed_and_unknown_sources_are_rejected(self):
        self.add();out=receipts.view()['documents'][0]
        self.assertNotIn('file',out['attachments'][0])
        with self.assertRaises(ValueError):receipts.source('../../settings.json')
    def test_bank_source_is_attached_when_a_csv_is_reimported(self):
        f={'name':'bank.csv','data':base64.b64encode(b'synthetic bank export').decode(),'media_type':'text/csv'}
        source=receipts.store_source(f)
        row={'date':'2026-10-03','amount':-12,'description':'EXAMPLE SHOP','account':'checking','counterparty':''}
        spending.import_transactions('bank.csv',[row]);before=len(spending.load()['transactions'])
        spending.import_transactions('bank.csv',[row],source_id=source['id'])
        self.assertEqual(len(spending.load()['transactions']),before)
        self.assertIn(source['id'],next(t for t in spending.load()['transactions'] if t['date']=='2026-10-03')['source_ids'])
    def test_invalid_numeric_invoice_is_not_saved(self):
        with self.assertRaises(ValueError):receipts.add([{**self.doc,'total':float('nan')}],[self.file])
        self.assertFalse(receipts.FILE.exists())
    def test_discount_reduces_expense_instead_of_creating_income(self):
        self.doc['items'][0]['total']=30
        self.doc['items'].append({'description':'Discount','quantity':1,'unit_price':-5,'total':-5,'category':'electronics','sku':None})
        id=self.add();self.link(id)
        receipts.edit({'action':'split-payment','id':id,'transaction_id':'bank-40'})
        pieces=spending.parts(spending.load()['transactions'][0])
        self.assertEqual(sum(p['amount'] for p in pieces),-40)
        self.assertTrue(next(p for p in pieces if p['amount']>0)['receipt_adjustment'])
