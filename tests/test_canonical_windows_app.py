"""No-argument real launcher: all capabilities in one isolated application."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Copy only the actual offline runtime closure; no configs, credentials or data.
FILES = ('Start Project Guardian.bat', 'Start_Elysia_Backend.cmd', 'elysia.py',
         'elysia_offline.py', 'elysia_synthetic_learning.py', 'offline_research_pilot.py',
         'project_guardian/__init__.py', 'project_guardian/auto_learning.py',
         'project_guardian/offline_research_recovery.py', 'project_guardian/brain/__init__.py',
         'project_guardian/brain/memory_intelligence_bridge.py',
         'project_guardian/local_ingestion/__init__.py',
         'project_guardian/local_ingestion/memory_intelligence.py',
         'project_guardian/local_ingestion/apply_transaction.py')


class CanonicalApplicationTests(unittest.TestCase):
    def test_complete_no_argument_launcher_session_and_fresh_restart(self):
        transcript = []
        with tempfile.TemporaryDirectory(prefix='ca-', dir=ROOT.parent) as directory:
            app = Path(directory) / 'app'
            app.mkdir()
            for name in FILES:
                target = app/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/name, target)
                self.assertEqual(target.read_bytes(), (ROOT/name).read_bytes())
            env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT'}}
            env.update(TEMP=directory, TMP=directory, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
            store = app/'.synthetic-pilot-stores'/'windows-pilot'
            def snapshot():
                return {str(p.relative_to(store)):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.rglob('*') if p.is_file()}
            def launch(turns, number):
                # No application arguments, exactly the double-click entry path.
                argv = [env.get('COMSPEC','cmd.exe'), '/d', '/c', str(app/'Start Project Guardian.bat')]
                out, err = Path(directory)/f'out{number}', Path(directory)/f'err{number}'
                with out.open('w', encoding='utf-8') as stdout, err.open('w', encoding='utf-8') as stderr:
                    process = subprocess.Popen(argv,cwd=app,env=env,stdin=subprocess.PIPE,
                        stdout=stdout,stderr=stderr,text=True,encoding='utf-8')
                    try:
                        deadline=time.monotonic()+20
                        while 'Ask Elysia:' not in out.read_text(encoding='utf-8'):
                            self.assertIsNone(process.poll(),err.read_text(encoding='utf-8'))
                            self.assertLess(time.monotonic(),deadline)
                            time.sleep(.02)
                        process.communicate('\n'.join(turns)+'\n',timeout=30)
                        self.assertEqual(process.returncode,0,err.read_text(encoding='utf-8')+out.read_text(encoding='utf-8'))
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate(timeout=5)
                text=out.read_text(encoding='utf-8')
                self.assertIn('Security evidence: ',text)
                security=json.loads(next(line.split(': ',1)[1] for line in text.splitlines() if line.startswith('Security evidence: ')))
                self.assertEqual(security['denied_effects'],[])
                self.assertEqual(security['threads'],['MainThread'])
                for field in ['legacy_core_loaded','running_after_shutdown','recall_wrote_files']:
                    self.assertFalse(security[field])
                self.assertTrue(security['restart_equal'])
                transcript.append({'argv':argv,'stdin':turns,'stdout':text,'stderr':err.read_text(encoding='utf-8'),'exit_code':0})
                return text
            first=launch(['water seedlings',
                '/teach lantern | Fictional moonberry lantern color is violet.',
                'What color is the moonberry lantern?',
                '/correct lantern | Fictional moonberry lantern color is amber.',
                'moonberry lantern color','/history lantern',
                '/teach lantern | Fictional moonberry lantern color is amber.',
                '/research Skylark Composite',
                'What did you learn about protecting Skylark Composite?',
                'Skylark Composite price','/exit'],1)
            for text in ['Tuesday morning','color is violet.','color is amber.','Revision 1:',
                         'Revision 2:','Duplicate fact; no record written.', '3 new sources preserved',
                         'garden: irrelevant','duplicate: duplicate','Unresolved potential conflict:',
                         'Information unavailable.','Named fictional store retained.']:
                self.assertIn(text,first)
            before=snapshot()
            self.assertEqual(len(list(store.rglob('*.bin'))),8) # 3 samples + 2 revisions + 3 research
            second=launch(['Tell me the moonberry lantern color.',
                'Skylark Composite protective treatment','/research Skylark Composite',
                '/history lantern','/exit'],2)
            self.assertIn('Elysia: From synthetic memory: Fictional moonberry lantern color is amber.',second)
            self.assertIn('0 new sources preserved; 1 unresolved potential conflicts',second)
            self.assertIn('Unresolved potential conflict: protective treatment',second)
            self.assertEqual(before,snapshot())
            from offline_research_pilot import FIXTURES
            for path in (store/'research'/'memory_intelligence'/'records').glob('*.json'):
                record=json.loads(path.read_text(encoding='utf-8'))
                meta=json.loads(record['source_identity'])
                raw=(store/'research'/record['raw_source_path']).read_bytes()
                self.assertEqual(raw,FIXTURES[meta['url']])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),record['source_sha256'])
                self.assertTrue(meta['retrieved_at'] and meta['session_id'])
            receipt={'runtime_files_sha256':{name:hashlib.sha256((app/name).read_bytes()).hexdigest() for name in FILES},
                     'processes':transcript,'retained_artifact_hashes':before,'restart_hashes_identical':True}
            if os.environ.get('ELYSIA_CANONICAL_RECEIPT'):
                Path(os.environ['ELYSIA_CANONICAL_RECEIPT']).write_text(json.dumps(receipt,indent=2),encoding='utf-8')


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    unittest.main(verbosity=2)
