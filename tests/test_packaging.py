import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_submission import package


class PackagingTests(unittest.TestCase):
    def test_extracted_real_package_contains_ai_resources_and_runs_without_credentials(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'source.zip'
            package(root, destination)
            with zipfile.ZipFile(destination) as archive:
                names = set(archive.namelist())
                self.assertIn('retail-sql-reconciliation/src/source_preflight.py', names)
                self.assertNotIn('retail-sql-reconciliation/src/retail_check.py', names)
                self.assertNotIn('retail-sql-reconciliation/demo.py', names)
                self.assertFalse(any(name.startswith('retail-sql-reconciliation/configs/') for name in names))
                archive.extractall(Path(temporary) / 'extracted')
            extracted = Path(temporary) / 'extracted/retail-sql-reconciliation'
            env = os.environ.copy()
            for key in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'PYTHONPATH'):
                env.pop(key, None)
            code = (
                "from pathlib import Path; from src.reconcile import run_reconciliation; "
                "r=run_reconciliation(Path('samples/reconciliation/filter_mismatch/job-paid-query.json'), "
                "Path('outputs/package-smoke'), ai=True); "
                "assert r['status']=='MATCH', r; "
                "assert r['ai_analysis']['status']=='UNAVAILABLE', r['ai_analysis']")
            completed = subprocess.run([sys.executable, '-S', '-c', code], cwd=extracted, env=env,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_only_manifest_files_are_archived_and_source_hashes_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'README.md').write_text('Synthetic package sample.\n')
            (root / '.env').write_text('OFFLINE_TEST_PLACEHOLDER=not-a-real-credential\n')
            (root / 'docs').mkdir()
            (root / 'docs/data_reconciliation_quality_framework.md').write_text('Private working notes.\n')
            (root / 'outputs').mkdir()
            (root / 'outputs/local-run.json').write_text('{}')
            (root / 'submission_manifest.json').write_text(json.dumps({'schema_version': 1, 'files': ['README.md']}))
            destination = root / 'package.zip'
            audit = package(root, destination)
            self.assertTrue(audit['verified'])
            self.assertEqual(audit['files'], ['README.md'])
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {'retail-sql-reconciliation/README.md', 'retail-sql-reconciliation/CONTENTS.json'})
                self.assertEqual(archive.read('retail-sql-reconciliation/README.md'), (root / 'README.md').read_bytes())
                self.assertEqual(json.loads(archive.read('retail-sql-reconciliation/CONTENTS.json')), audit['file_sha256'])
            with self.assertRaises(FileExistsError):
                package(root, destination)

    def test_unsafe_or_unrelated_manifest_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'README.md').write_text('Sample.')
            bad_entries = ['../outside.txt', '/tmp/outside.txt', '.git/config', '.env',
                           'outputs/run.json', 'data/private/orders.csv', 'docs/data_reconciliation_quality_framework.md',
                           'src/../README.md', 'src\\outside.py']
            for name in bad_entries:
                with self.subTest(name=name):
                    (root / 'submission_manifest.json').write_text(json.dumps({'schema_version': 1, 'files': [name]}))
                    with self.assertRaises(ValueError):
                        package(root, root / 'rejected.zip')
                    self.assertFalse((root / 'rejected.zip').exists())


if __name__ == '__main__':
    unittest.main()
