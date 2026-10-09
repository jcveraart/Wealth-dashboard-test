"""Checks for the new demo packaging and complete sample dataset."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
import generate_demo

class DemoFixtures(unittest.TestCase):
    def test_versioned_chunks_contain_the_complete_dataset(self):
        import csv
        data = ROOT / 'demo_data'
        manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
        payments = [t for name in manifest['transaction_files']
                    for t in json.loads((data / name).read_text(encoding='utf-8'))]
        self.assertEqual(len(payments), manifest['transactions'])
        self.assertEqual(len({t['id'] for t in payments}), len(payments))
        invoice_payment=next(t for t in payments if t['id']=='demo-invoice-payment')
        self.assertEqual(invoice_payment['key'],'exampledemoshop')
        self.assertTrue(invoice_payment['description'].startswith('DEMO ONLY:'))
        for name, expected in (('history.csv', manifest['history_days']),
                               ('history_accounts.csv', manifest['history_days'] * 10)):
            rows = []
            for piece in manifest['history_files'][name]:
                with (data / piece).open(encoding='utf-8') as f:
                    rows.extend(csv.DictReader(f))
            self.assertEqual(len(rows), expected)
        self.assertTrue((data / 'receipts.json').exists())
        self.assertTrue((data / 'research.json').exists())

    def test_json_api_does_not_fall_through_to_a_second_response(self):
        import app, io
        from email.message import Message
        handler = app.Handler.__new__(app.Handler)
        handler.path = '/api/ui'
        handler.command = 'GET'
        handler.directory = str(ROOT / 'web')
        handler.request_version = 'HTTP/1.1'
        handler.requestline = 'GET /api/ui HTTP/1.1'
        handler.client_address = ('127.0.0.1', 0)
        handler.headers = Message()
        handler.headers['Host'] = '127.0.0.1:' + str(app.PORT)
        handler.wfile = io.BytesIO()
        handler.log_message = lambda *args: None
        handler.do_GET()
        raw = handler.wfile.getvalue()
        header, body = raw.split(b'\r\n\r\n', 1)
        self.assertEqual(raw.count(b'HTTP/1.0 '), 1)
        self.assertIn('prefs', json.loads(body))

    def test_generated_data_is_complete_and_repeatable(self):
        from datetime import date
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = generate_demo.generate(first, date(2026, 10, 7))
            b = generate_demo.generate(second, date(2026, 10, 7))
            self.assertEqual(a, b)
            self.assertGreater(len(a['spending']['transactions']), 650)
            self.assertGreater(len(a['history']), 1800)
            self.assertTrue(a['portfolio']['goals'])
            self.assertEqual(json.loads((Path(first) / 'settings.json').read_text()), {})
            self.assertTrue(all(t['description'].startswith('DEMO ONLY:') for t in a['spending']['transactions']))
            self.assertTrue(all(t['date'] <= '2026-10-07' for t in a['spending']['transactions']))
            self.assertTrue(any(t['category'] == 'from-people' and t['amount'] > 0 for t in a['spending']['transactions']))
            self.assertTrue(any(t.get('splits') for t in a['spending']['transactions']))
            self.assertGreater(len({t['country'] for t in a['spending']['transactions']}), 2)

    def test_launcher_preserves_edits_and_resets_only_its_runtime(self):
        import demo
        with tempfile.TemporaryDirectory() as folder:
            isolated = Path(folder) / '.demo-runtime'
            with patch.object(demo, 'ROOT', Path(folder)), patch.object(demo, 'RUNTIME', isolated), patch('profiles.copy_code'):
                demo.prepare()
                settings = isolated / 'settings.json'
                settings.write_text('{"demo_test": true}', encoding='utf-8')
                demo.prepare()
                self.assertTrue(json.loads(settings.read_text())['demo_test'])
                self.assertEqual(json.loads((isolated / 'manifest.json').read_text())['synthetic'], True)
                self.assertNotEqual(isolated, ROOT)

    def test_fresh_download_starts_without_optional_requirements(self):
        import demo, shutil
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            from profiles import source_files
            for name in source_files(ROOT):
                target=project/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT / name, target)
            shutil.copytree(ROOT / 'web', project / 'web', dirs_exist_ok=True)
            runtime = project / '.demo-runtime'
            with patch.object(demo, 'ROOT', project), patch.object(demo, 'RUNTIME', runtime):
                demo.prepare()
            self.assertTrue(json.loads((runtime / 'manifest.json').read_text())['synthetic'])
            self.assertTrue((runtime / 'spending.json').is_file())

    def test_interrupted_setup_is_preserved_and_recovers(self):
        import demo
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            runtime = project / '.demo-runtime'
            runtime.mkdir()
            (runtime / 'keep.txt').write_text('Preserve this incomplete setup')
            with patch.object(demo, 'ROOT', project), patch.object(demo, 'RUNTIME', runtime), patch('profiles.copy_code'):
                demo.prepare()
            self.assertTrue((runtime / 'manifest.json').exists())
            recovered = list((project / 'backups').glob('demo-preserved-*/keep.txt'))
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].read_text(), 'Preserve this incomplete setup')

    def test_public_fixtures_do_not_contain_credentials(self):
        data = ROOT / 'demo_data'
        self.assertEqual(json.loads((data / 'settings.json').read_text()), {})
        for name in ('portfolio.json', 'spending.json', 'chats.json', 'ui.json'):
            text = (data / name).read_text(encoding='utf-8')
            self.assertNotIn('sb_secret_', text)
            self.assertNotIn('sk-ant-', text)
        self.assertTrue((data / 'workflows.json').is_file())
