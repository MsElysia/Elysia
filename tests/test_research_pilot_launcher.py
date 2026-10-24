"""Real Windows launcher acceptance; disposable synthetic storage only."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import shutil

ROOT = Path(__file__).resolve().parents[1]

class ResearchLauncherTests(unittest.TestCase):
    def setUp(self):
        self.created_stores = []

    def tearDown(self):
        for store in self.created_stores:
            self.assertEqual(store.parent, ROOT/'.synthetic-pilot-stores')
            self.assertFalse(store.is_symlink())
            if store.exists():
                shutil.rmtree(store)

    def test_two_real_launcher_processes_preserve_evidence(self):
        with tempfile.TemporaryDirectory(prefix='research-acceptance-') as temporary:
            env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT'}}
            env.update(TEMP=temporary, TMP=temporary, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
            env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH','')
            token = uuid.uuid4().hex
            name = 'rtest-' + token
            store = ROOT / '.synthetic-pilot-stores' / name
            self.created_stores.append(store)
            transcript = []
            def launch(turns, number):
                out, err = Path(temporary)/f'out{number}', Path(temporary)/f'err{number}'
                command = [env.get('COMSPEC','cmd.exe'), '/d','/c','Start Project Guardian.bat','--interactive','--synthetic-store',name]
                transcript.append('ARGV: '+json.dumps(command))
                with out.open('w',encoding='utf-8') as stdout, err.open('w',encoding='utf-8') as stderr:
                    p = subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,encoding='utf-8')
                    try:
                        deadline=time.monotonic()+30
                        while 'Ask Elysia:' not in out.read_text(encoding='utf-8'):
                            self.assertIsNone(p.poll(),err.read_text(encoding='utf-8'))
                            self.assertLess(time.monotonic(),deadline)
                            time.sleep(.02)
                        transcript.append('INPUT:\n'+'\n'.join(turns))
                        p.communicate('\n'.join(turns)+'\n',timeout=30)
                        self.assertEqual(p.returncode,0,err.read_text(encoding='utf-8')+out.read_text(encoding='utf-8'))
                    finally:
                        if p.poll() is None:
                            p.kill(); p.communicate()
                text=out.read_text(encoding='utf-8')
                transcript.append('STDOUT:\n'+text)
                for line in text.splitlines():
                    if line.startswith('Security evidence: '):
                        security=json.loads(line.split(': ',1)[1])
                        self.assertEqual(security['denied_effects'],[])
                        self.assertEqual(security['threads'],['MainThread'])
                        self.assertFalse(security['legacy_core_loaded'])
                        self.assertFalse(security['running_after_shutdown'])
                        self.assertTrue(security['restart_equal'])
                        self.assertFalse(security['recall_wrote_files'])
                return text
            first=launch(['/research Unknown Topic', '/teach lantern | Fictional orbit lantern color is violet.',
                          'orbit lantern color', '/research Skylark Composite',
                          'Skylark Composite protective treatment','/exit'],1)
            self.assertIn('3 new sources preserved',first)
            self.assertIn('Only the fictional Skylark Composite fixture is approved', first)
            self.assertIn('Fictional orbit lantern color is violet.', first)
            self.assertIn('garden: irrelevant', first)
            self.assertIn('duplicate: duplicate', first)
            before={str(p.relative_to(store)):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.rglob('*') if p.is_file()}
            self.assertEqual(len(list(store.rglob('*.bin'))),7)
            second=launch(['/research Skylark Composite',
                           'What did you learn about protecting Skylark Composite?',
                           'Skylark Composite price',
                           'When should I apply Skylark Composite protective treatment?',
                           'Where should I apply Skylark Composite protective treatment?',
                           'orbit lantern color', '/restart', '/exit'],2)
            self.assertIn('0 new sources preserved; 1 unresolved potential conflicts', second)
            self.assertIn('Information unavailable.', second)
            self.assertEqual(second.count('Information unavailable.'), 3)
            self.assertIn('Fictional orbit lantern color is violet.', second)
            after={str(p.relative_to(store)):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            for text in (first,second):
                self.assertIn('Unresolved potential conflict: protective treatment',text)
                self.assertIn('apply synthetic wax',text); self.assertIn('avoid synthetic wax',text)
                self.assertIn('https://synthetic.invalid/skylark/lab',text)
                self.assertIn('https://synthetic.invalid/skylark/vendor',text)
            transcript.append('VERIFIED: all persisted artifact hashes identical across fresh launcher processes.\n'+json.dumps(before,sort_keys=True,indent=2))
            from offline_research_pilot import FIXTURES
            records = [json.loads(p.read_text(encoding='utf-8')) for p in (store/'research'/'memory_intelligence'/'records').glob('*.json')]
            for record in records:
                url = json.loads(record['source_identity'])['url']
                raw = (store/'research'/record['raw_source_path']).read_bytes()
                self.assertEqual(raw, FIXTURES[url])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record['source_sha256'])
                self.assertIn(record['source_sha256'], first + second)
            missions = list((store/'research').glob('mission-*.json'))
            self.assertEqual(len(missions), 1)
            mission = json.loads(missions[0].read_text(encoding='utf-8'))
            self.assertEqual(mission['subject'], 'Skylark Composite')
            self.assertTrue(mission['derived_claims'])
            self.assertEqual(mission['rejected'][1]['reason'], 'duplicate')
            self.assertTrue(mission['rejected'][1]['duplicate_source_ids'])
            # Delete only the unique synthetic test store within this checkout.
            self.assertEqual(store.parent, ROOT/'.synthetic-pilot-stores')
            self.assertFalse(store.is_symlink())
            shutil.rmtree(store)
        self.assertFalse(store.exists())
        transcript.append('VERIFIED: disposable memory storage removed by acceptance owner.')
        receipt = os.environ.get('ELYSIA_RESEARCH_RECEIPT')
        if receipt:
            Path(receipt).write_text('\n\n'.join(transcript),encoding='utf-8')

    def test_arbitrary_destination_and_invalid_token_refused(self):
        from elysia_synthetic_learning import store_path
        for token in ('../private','Z:/personal','a'*31):
            if token == 'a'*31:
                token = 'a'*41
            with self.assertRaises(ValueError): store_path(token)

    def test_actual_launcher_corrupt_research_source_fails_closed(self):
        name = 'rtest-' + uuid.uuid4().hex
        store = ROOT / '.synthetic-pilot-stores' / name
        self.created_stores.append(store)
        with tempfile.TemporaryDirectory() as directory:
            env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT'}}
            env.update(TEMP=directory, TMP=directory, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
            env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH','')
            command = [env.get('COMSPEC','cmd.exe'), '/d','/c','Start Project Guardian.bat','--interactive','--synthetic-store',name]
            first = subprocess.run(command, input='/research Skylark Composite\n/exit\n',
                cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
            raw = next((store/'research'/'memory_intelligence'/'raw_sources').glob('*.bin'))
            raw.write_bytes(b'corrupted synthetic evidence')
            before = {str(p.relative_to(store)):p.read_bytes() for p in store.rglob('*') if p.is_file()}
            second = subprocess.run(command, input='Skylark Composite protection\n/exit\n',
                cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(second.returncode, 2, second.stdout+second.stderr)
            self.assertIn('provenance mismatch', second.stderr)
            self.assertNotIn('Elysia: Synthetic source claims', second.stdout)
            self.assertEqual(before, {str(p.relative_to(store)):p.read_bytes() for p in store.rglob('*') if p.is_file()})

if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    unittest.main(verbosity=2)
