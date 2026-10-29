"""Real Windows launcher persistence regression; no startup or memory mocks."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


class LearningLauncherTests(unittest.TestCase):
    def setUp(self):
        self.name = "test-" + uuid.uuid4().hex
        self.store = ROOT / ".synthetic-pilot-stores" / self.name
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.env = {k: v for k, v in os.environ.items()
                    if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
        self.env.update(TEMP=self.temp.name, TMP=self.temp.name, PYTHONUTF8="1",
                        PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        self.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + self.env.get("PATH", "")
        self.runs = []

    def tearDown(self):
        assert self.store.parent == ROOT / ".synthetic-pilot-stores"
        assert self.store.name == self.name and not self.store.is_symlink()
        if self.store.exists():
            shutil.rmtree(self.store)
        self.temp.cleanup()

    def launch(self, text, expected=0):
        command = [self.env.get("COMSPEC", "C:/Windows/System32/cmd.exe"), "/d", "/c",
                   "Start Project Guardian.bat", "--interactive", "--synthetic-store", self.name]
        result = subprocess.run(command, input=text, capture_output=True, text=True,
                                encoding="utf-8", env=self.env, cwd=ROOT, timeout=30)
        self.runs.append({"argv": command, "stdin": text, "stdout": result.stdout,
                          "stderr": result.stderr, "exit_code": result.returncode})
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def test_teach_exit_relaunch_correct_history_duplicates_and_unavailable(self):
        original = "Fictional moonberry lantern color is violet."
        revised = "Fictional moonberry lantern color is amber."
        output = self.launch(f"/teach lantern | {original}\nWhat color is the moonberry lantern?\n/exit\n")
        self.assertIn("Fictional fact learned.", output)
        self.assertIn("Elysia: From synthetic memory: " + original, output)
        self.assertIn("Shutdown complete. Named fictional store retained.", output)
        files = {str(p.relative_to(self.store)): p.read_bytes() for p in self.store.rglob("*") if p.is_file()}
        output = self.launch("Tell me the moonberry lantern color.\n/restart\n/exit\n")
        self.assertIn(original, output)
        self.assertIn("Restart complete.", output)
        self.assertEqual(files, {str(p.relative_to(self.store)): p.read_bytes() for p in self.store.rglob("*") if p.is_file()})
        output = self.launch(f"/teach lantern | {original}\n/correct lantern | {revised}\n/history lantern\nmoonberry lantern color\n/exit\n")
        self.assertIn("Duplicate fact; no record written.", output)
        self.assertIn("source history preserved", output)
        self.assertIn("Revision 1:", output)
        self.assertIn("Revision 2:", output)
        self.assertIn(original, output)
        self.assertIn("Elysia: From synthetic memory: " + revised, output)
        for name, data in files.items():
            if name != "synthetic-learning.json":
                self.assertEqual((self.store / name).read_bytes(), data)
        output = self.launch(f"/teach alias | {revised}\nmoonberry lantern color\nmoonberry lantern violet\nmoonberry lantern price\nseedlings color\nwater seedlings\nreserved library books\n/exit\n")
        self.assertIn("Learning unavailable: Duplicate conflicts", output)
        self.assertIn("Elysia: From synthetic memory: " + revised, output)
        self.assertEqual(output.count("Information unavailable."), 3)
        self.assertIn("Tuesday morning", output)
        self.assertIn("shelf B", output)
        self.assertEqual(len(list((self.store / "memory_intelligence" / "records").glob("*.json"))), 5)
        # Save only synthetic transcripts outside the store for reproducibility.
        receipt = os.environ.get("ELYSIA_TEST_RECEIPT")
        if receipt:
            Path(receipt).write_text(json.dumps(self.runs, indent=2), encoding="utf-8")

    def test_invalid_commands_and_tampered_source_fail_closed(self):
        output = self.launch("/teach broken\n/teach lantern | Real data\n/correct absent | Fictional lantern is red.\n/teach lantern | Fictional lantern color is red.\n/exit\n")
        self.assertEqual(output.count("Learning unavailable:"), 3)
        raw = next((self.store / "memory_intelligence" / "raw_sources").glob("*.bin"))
        raw.write_bytes(b"tampered")
        self.launch("lantern color\n/exit\n", expected=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
