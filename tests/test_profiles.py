import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import profiles,build_supabase_seed

class ProfileIsolation(unittest.TestCase):
    def test_personal_starts_empty_and_survives_source_updates(self):
        with tempfile.TemporaryDirectory() as folder,patch('profiles.copy_code'):
            project=Path(folder);personal=profiles.prepare('personal',project=project)
            cfg=json.loads((personal/'portfolio.json').read_text())
            for name in ('accounts','savings','debts','goals','savings_plans'):self.assertEqual(cfg[name],[])
            self.assertEqual(cfg['managed']['value_eur'],0)
            self.assertFalse(json.loads((personal/'settings.json').read_text())['ai_enabled'])
            (personal/'notes.md').write_text('my private notes')
            profiles.prepare('personal',project=project)
            self.assertEqual((personal/'notes.md').read_text(),'my private notes')
            with self.assertRaises(ValueError):profiles.prepare('personal',reset=True,project=project)
    def test_unmarked_personal_and_outside_paths_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder);personal=project/'.personal-runtime';personal.mkdir();(personal/'keep.txt').write_text('keep')
            with self.assertRaises(RuntimeError):profiles.prepare('personal',project=project)
            self.assertEqual((personal/'keep.txt').read_text(),'keep')
            with self.assertRaises(RuntimeError):profiles.prepare('demo',project=project,runtime=project.parent/'outside')
    def test_demo_reset_preserves_old_demo_and_does_not_touch_personal(self):
        with tempfile.TemporaryDirectory() as folder,patch('profiles.copy_code'):
            project=Path(folder);personal=profiles.prepare('personal',project=project);(personal/'notes.md').write_text('personal')
            demo=profiles.prepare('demo',project=project);(demo/'notes.md').write_text('old demo')
            profiles.prepare('demo',reset=True,project=project)
            self.assertEqual((personal/'notes.md').read_text(),'personal')
            self.assertEqual(len(list((project/'backups').glob('demo-preserved-*/notes.md'))),1)
            self.assertTrue((demo/'cache/intelligence.sqlite3').exists())
    def test_seed_is_local_additive_and_from_marked_fixtures(self):
        sql=build_supabase_seed.build()
        self.assertIn('FICTIONAL DATA ONLY',sql);self.assertIn('ON CONFLICT DO NOTHING',sql)
        self.assertNotIn('DELETE FROM',sql);self.assertNotIn('DROP TABLE',sql)
        self.assertGreater(sql.count('INSERT INTO spending_transactions'),650)
