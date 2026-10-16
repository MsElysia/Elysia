"""Additional real Windows failure/recovery gates, with synthetic data only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import unittest

import test_synthetic_learning_isolated as learning

ROOT = Path(__file__).resolve().parents[1]


class FinalApplicationTests(unittest.TestCase):
    setUp = learning.LearningLauncherTests.setUp
    tearDown = learning.LearningLauncherTests.tearDown

    def launch(self, text, expected=0):
        # Exercise the actual full checkout from an unrelated directory with spaces.
        cwd = Path(self.temp.name) / 'different working directory'
        cwd.mkdir(exist_ok=True)
        command = [self.env.get('COMSPEC', 'cmd.exe'), '/d', '/c',
                   str(ROOT / 'Start Project Guardian.bat'), '--interactive', '--synthetic-store', self.name]
        result = subprocess.run(command, input=text, cwd=cwd, env=self.env,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.runs.append({'argv': command, 'cwd': str(cwd), 'stdin': text,
                          'stdout': result.stdout, 'stderr': result.stderr, 'exit_code': result.returncode})
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def save_receipt(self):
        directory = os.environ.get('ELYSIA_FINAL_RECEIPTS')
        if directory:
            Path(directory, self._testMethodName + '.json').write_text(json.dumps(self.runs, indent=2), encoding='utf-8')

    def hashes(self):
        return {str(p.relative_to(self.store)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.store.rglob('*') if p.is_file()}

    def test_unicode_subjects_corrections_and_unsupported_queries(self):
        output = self.launch('water seedlings\nreserved library books\n'
                             '/teach lamp | Fictional 灯笼 color is 紫色.\n'
                             '/teach moon | Fictional 月亮 color is 红色.\n'
                             'What color is 灯笼?\n'
                             '/correct lamp | Fictional 灯笼 color is 琥珀色.\n'
                             'Tell me 灯笼 color.\n灯笼 紫色\n/history lamp\n'
                             '/research Skylark Composite\n'
                             'What did you learn about protecting Skylark Composite?\n'
                             'Skylark Composite 不存在\n/exit\n')
        answer = [line for line in output.splitlines() if line.startswith('Elysia: ')][2]
        self.assertIn('灯笼', answer)
        self.assertNotIn('月亮', answer)
        self.assertIn('Tuesday morning', output)
        self.assertIn('shelf B', output)
        self.assertIn('Elysia: From synthetic memory: Fictional 灯笼 color is 琥珀色.', output)
        self.assertEqual(output.count('Information unavailable.'), 2)
        self.assertIn('Revision 1:', output)
        self.assertIn('Revision 2:', output)
        self.assertIn('3 new sources preserved', output)
        self.assertIn('garden: irrelevant', output)
        self.assertIn('duplicate: duplicate', output)
        self.assertIn('Unresolved potential conflict:', output)
        before = self.hashes()
        output = self.launch('What color is 灯笼?\nSkylark Composite protective treatment\n'
                             '/research Skylark Composite\n/exit\n')
        self.assertIn('Elysia: From synthetic memory: Fictional 灯笼 color is 琥珀色.', output)
        self.assertIn('Unresolved potential conflict:', output)
        self.assertEqual(before, self.hashes())
        self.save_receipt()

    def test_acknowledged_save_survives_killed_application_process(self):
        import psutil  # Existing development dependency; observer runs outside pilot.
        cwd = Path(self.temp.name) / 'another cwd with spaces'
        cwd.mkdir()
        command = [self.env.get('COMSPEC', 'cmd.exe'), '/d', '/c',
                   str(ROOT / 'Start Project Guardian.bat'), '--interactive', '--synthetic-store', self.name]
        output = Path(self.temp.name) / 'crash-stdout.txt'
        errors = Path(self.temp.name) / 'crash-stderr.txt'
        with output.open('w', encoding='utf-8') as stdout, errors.open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen(command, cwd=cwd, env=self.env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, text=True, encoding='utf-8')
            try:
                deadline = time.monotonic() + 25
                def wait_for(text):
                    while text not in output.read_text(encoding='utf-8'):
                        self.assertIsNone(process.poll(), errors.read_text(encoding='utf-8'))
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.02)
                wait_for('Ask Elysia:')
                children = psutil.Process(process.pid).children(recursive=True)
                observed = [{'pid':p.pid, 'name':p.name(), 'connections':len(p.net_connections(kind='inet'))}
                            for p in children]
                self.assertTrue(observed)
                self.assertTrue(all(p['name'].lower() in {'python.exe','cmd.exe'} and p['connections']==0 for p in observed))
                process.stdin.write('/teach beacon | Fictional café beacon signal is éclair.\n')
                process.stdin.flush()
                wait_for('Fictional fact learned.')
                before = self.hashes()
                python = next(p for p in children if p.name().lower()=='python.exe')
                python.kill()  # Only our application's observed child, after durable acknowledgment.
                process.communicate(timeout=15)
                self.assertNotEqual(process.returncode, 0)
                self.assertNotIn('Shutdown complete.', output.read_text(encoding='utf-8'))
                self.runs.append({'argv':command,'cwd':str(cwd),'stdout':output.read_text(encoding='utf-8'),
                    'stderr':errors.read_text(encoding='utf-8'),'unexpected_termination_after_ack':True,
                    'observed_child_processes':observed,'killed_application_pid':python.pid})
            finally:
                if process.poll() is None:
                    for child in psutil.Process(process.pid).children(recursive=True):child.kill()
                    process.kill()
                    process.communicate(timeout=5)
        answer = self.launch('Tell me café beacon signal.\n/exit\n')
        self.assertIn('Fictional café beacon signal is éclair.', answer)
        self.assertEqual(before, self.hashes())
        self.assertFalse(any(self.store.glob('.chatgpt_apply_transaction*')))
        self.save_receipt()

    def test_origin_separation_and_corrupt_research_refusal(self):
        output = self.launch('/teach origin | Fictional Skylark Composite operatornote is café.\n'
                             '/research Skylark Composite\nSkylark Composite operatornote\n/exit\n')
        self.assertIn('Elysia: From synthetic memory: Fictional Skylark Composite operatornote is café.', output)
        parent = [json.loads(p.read_text(encoding='utf-8')) for p in (self.store/'memory_intelligence/records').glob('*.json')]
        self.assertEqual(sum(r['source_identity']=='elysia-fictional:origin' for r in parent),1)
        research = [json.loads(p.read_text(encoding='utf-8')) for p in (self.store/'research/memory_intelligence/records').glob('*.json')]
        for row in research:
            meta = json.loads(row['source_identity'])
            self.assertEqual(meta['kind'],'offline-research-evidence-v1')
            self.assertTrue(meta['url'].startswith('https://synthetic.invalid/'))
        raw = self.store/'research'/research[0]['raw_source_path']
        raw.write_bytes(b'altered synthetic source')
        before = self.hashes()
        self.launch('Skylark Composite protection\n/exit\n', expected=2)
        self.assertEqual(before, self.hashes())
        self.save_receipt()

    def test_failed_save_never_reports_success(self):
        self.launch('/exit\n')
        from project_guardian.local_ingestion.memory_intelligence import preserve_raw_source
        fact = b'Fictional failed beacon color is blue.'
        source = preserve_raw_source(fact, source_identity='elysia-fictional:failed')
        obstruction = self.store/'memory_intelligence/raw_sources'/(source.source_id+'.bin')
        obstruction.mkdir()  # Real local I/O failure, not a transaction mock.
        output = self.launch('/teach failed | '+fact.decode()+'\n/exit\n', expected=2)
        self.assertNotIn('Fictional fact learned.', output)
        index = json.loads((self.store/'synthetic-learning.json').read_text(encoding='utf-8'))
        self.assertEqual(index['facts'],{})
        self.assertEqual(len(list((self.store/'memory_intelligence/records').glob('*.json'))),3)
        self.save_receipt()


if __name__ == '__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    unittest.main(verbosity=2)
