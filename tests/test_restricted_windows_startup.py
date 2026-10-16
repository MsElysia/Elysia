"""Main-based restricted startup checks, curated from f36259e.

The 19 restricted entry/guard assertions are unchanged. Three historical
Guardian construction/live-gate tests belong to modules not ported here.
Their original assertions remain protected in the reference checkout.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import time

ROOT = Path(__file__).resolve().parents[1]


class OfflineStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="offline-tests-", dir=ROOT / "tests")
        cls.env = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
        cls.env.update(TEMP=cls.temp.name, TMP=cls.temp.name, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        cls.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + cls.env.get("PATH", "")
        cls.before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in ROOT.rglob("*.py")}

    @classmethod
    def tearDownClass(cls):
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob("*.py")}
        assert cls.before == after, "source changed during execution"
        assert not list(Path(cls.temp.name).iterdir()), "synthetic directories leaked"
        cls.temp.cleanup()

    def run_command(self, command, *, expected=0, stdin_text=None, env=None):
        result = subprocess.run(command, cwd=ROOT, env=env or self.env, input=stdin_text,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def run_child(self, *args, expected=0, stdin_text=None):
        return self.run_command([sys.executable, "-B", *args], expected=expected, stdin_text=stdin_text)

    def windows_command(self, launcher, *args):
        return [self.env.get("COMSPEC", "C:/Windows/System32/cmd.exe"), "/d", "/c", launcher, *args]

    def test_script_entry_repeated_boot_shutdown(self):
        for _ in range(2):
            payload = json.loads(self.run_child("elysia.py", "--offline", "--query", "flashing").stdout)
            self.assertTrue(payload["recall"]["hits"])
            self.assertEqual(payload["denied_effects"], [])
            self.assertEqual(payload["threads"], ["MainThread"])
            self.assertFalse(payload["legacy_core_loaded"])
            self.assertTrue(payload["restart_equal"])
            self.assertFalse(payload["running_after_shutdown"])
            self.assertFalse(payload["recall_wrote_files"])

    def test_package_entry(self):
        payload = json.loads(self.run_child("-m", "elysia", "--offline", "--query", "flashing").stdout)
        self.assertTrue(payload["recall"]["hits"])

    def test_default_entry_is_restricted(self):
        for args in [("elysia.py",), ("-m", "elysia")]:
            payload = json.loads(self.run_child(*args).stdout)
            self.assertTrue(payload["synthetic_only"])
            self.assertEqual(payload["denied_effects"], [])

    def test_legacy_live_entry_refused(self):
        self.run_child("-m", "elysia", "run", expected=2)
        self.run_child("elysia.py", "--takeover", expected=2)

    def test_unmatched_input_has_no_fabricated_recall(self):
        payload = json.loads(self.run_child("elysia.py", "--offline", "--query", "zzzzunmatched").stdout)
        self.assertEqual(payload["recall"]["hits"], [])

    def test_user_storage_option_refused(self):
        self.run_child("elysia.py", "--offline", "--dest-dir", "Z:/private", expected=2)

    def test_negative_process_guard(self):
        payload = json.loads(self.run_child("tests/offline_startup_child.py", "guard").stdout)
        self.assertEqual(payload["guard_probes_denied"], 8)




    def test_real_windows_startup_input_answer_shutdown(self):
        # Send input only after the actual Windows launcher reports ready.
        # No startup/memory/component mocks are used in this process.
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            output = Path(directory) / "transcript.txt"
            errors = Path(directory) / "stderr.txt"
            with output.open("w", encoding="utf-8") as stdout, errors.open("w", encoding="utf-8") as stderr:
                process = subprocess.Popen(self.windows_command("Start Project Guardian.bat", "--offline", "--demo", "--stdin"),
                                           cwd=ROOT, env=self.env, stdin=subprocess.PIPE,
                                           stdout=stdout, stderr=stderr, text=True, encoding="utf-8")
                try:
                    deadline = time.monotonic() + 15
                    while "Enter one synthetic question:" not in output.read_text(encoding="utf-8"):
                        self.assertIsNone(process.poll(), errors.read_text(encoding="utf-8"))
                        self.assertLess(time.monotonic(), deadline, "Windows startup did not reach input")
                        time.sleep(0.01)
                    question = "What should I do before replacing the damaged flashing?"
                    process.communicate(question + "\n", timeout=15)
                    self.assertEqual(process.returncode, 0, errors.read_text(encoding="utf-8"))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
            transcript = output.read_text(encoding="utf-8")
            stages = ["Elysia offline startup complete.", "Enter one synthetic question:",
                      "Synthetic input: " + question, "Memory retrieval: 1 source-validated hit(s).",
                      "Elysia: From synthetic memory: Synthetic roofing plan: inspect the damaged flashing before replacing it.",
                      "Shutdown complete. Temporary synthetic data removed."]
            positions = [transcript.index(stage) for stage in stages]
            self.assertEqual(positions, sorted(positions))

    def test_windows_launcher_aliases_and_ambient_activation_flags(self):
        env = dict(self.env, ELYSIA_FORCE_FULL_BACKEND="1", ELYSIA_UNIFIED_ATTACH_IF_BACKEND_UP="1")
        for launcher in ("Start Project Guardian.bat", "Start_Elysia_Backend.cmd", "START_ELYSIA_UNIFIED.bat", "START_ELYSIA_FULL.bat"):
            payload = json.loads(self.run_command(self.windows_command(launcher, "--stdin"),
                                                 env=env, stdin_text="flashing\n").stdout)
            self.assertIn("inspect the damaged flashing before replacing it", payload["answer"])
            self.assertTrue(payload["temporary_data_removed"])
            self.assertEqual(payload["denied_effects"], [])
            self.assertEqual(payload["threads"], ["MainThread"])
            self.assertFalse(payload["legacy_core_loaded"])

    def test_python_launcher_aliases(self):
        for launcher in ("run_elysia.py", "run_elysia_unified.py"):
            payload = json.loads(self.run_child(launcher, "--stdin", stdin_text="flashing\n").stdout)
            self.assertTrue(payload["temporary_data_removed"])
            self.assertFalse(payload["legacy_core_loaded"])

    def test_windows_launcher_propagates_failure_and_no_match(self):
        for text in ("", "\n", "x" * 801 + "\n"):
            result = self.run_command(self.windows_command("Start_Elysia_Backend.cmd", "--demo", "--stdin"),
                                      expected=2, stdin_text=text)
            self.assertNotIn("Shutdown complete", result.stdout)
        payload = json.loads(self.run_command(self.windows_command("START_ELYSIA_FULL.bat", "--stdin"),
                                             stdin_text="zzzzunmatched\n").stdout)
        self.assertEqual(payload["answer"], "No matching synthetic memory was found.")
        self.assertEqual(payload["recall"]["hits"], [])

    def test_conflicting_input_options_refused(self):
        self.run_child("elysia.py", "--stdin", "--query", "flashing", expected=2)

    def test_interactive_real_launcher_multiple_memories_restart_exit(self):
        # No launcher flags: this is the double-click/default Windows path.
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            output, errors = Path(directory) / "session.txt", Path(directory) / "stderr.txt"
            with output.open("w", encoding="utf-8") as stdout, errors.open("w", encoding="utf-8") as stderr:
                process = subprocess.Popen(self.windows_command("Start Project Guardian.bat", "--interactive"), cwd=ROOT,
                                           env=self.env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                           text=True, encoding="utf-8")
                def wait_for(text, count=1):
                    deadline = time.monotonic() + 15
                    while output.read_text(encoding="utf-8").count(text) < count:
                        self.assertIsNone(process.poll(), errors.read_text(encoding="utf-8"))
                        self.assertLess(time.monotonic(), deadline, f"pilot did not reach {text}")
                        time.sleep(0.01)
                try:
                    wait_for("Ask Elysia:")
                    turns = [("What should I do before replacing damaged flashing?", "inspect the damaged flashing before replacing it."),
                             ("When should I water the seedlings?", "water the seedlings on Tuesday morning."),
                             ("Where are the reserved library books?", "collect reserved books from shelf B near the front desk."),
                             ("What is the flashing repair cost?", "Information unavailable."),
                             ("What is the telescope launch date?", "Information unavailable."),
                             ("/restart", "Restart complete. Synthetic memories retained."),
                             ("When should I water the seedlings?", "water the seedlings on Tuesday morning.")]
                    occurrences = {}
                    for query, expected in turns:
                        process.stdin.write(query + "\n")
                        process.stdin.flush()
                        occurrences[expected] = occurrences.get(expected, 0) + 1
                        wait_for(expected, occurrences[expected])
                    process.communicate("/exit\n", timeout=15)
                    self.assertEqual(process.returncode, 0, errors.read_text(encoding="utf-8"))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
            transcript = output.read_text(encoding="utf-8")
            self.assertIn("Session ended: 6 questions; 2 unavailable; 1 restarts.", transcript)
            self.assertTrue(transcript.rstrip().endswith("Shutdown complete. Temporary synthetic data removed."))

    def test_interactive_eof_empty_exit_and_process_restart(self):
        for _ in range(2):
            result = self.run_command(self.windows_command("Start_Elysia_Backend.cmd"), stdin_text="water seedlings\n")
            self.assertIn("water the seedlings on Tuesday morning.", result.stdout)
            self.assertIn("Input closed. Exiting.", result.stdout)
            self.assertIn("Shutdown complete. Temporary synthetic data removed.", result.stdout)
        result = self.run_command(self.windows_command("START_ELYSIA_FULL.bat"), stdin_text="/exit\n")
        self.assertIn("Session ended: 0 questions", result.stdout)

    def test_interactive_invalid_input_recovers_and_tail_is_not_executed(self):
        text = "\n" + "x" * 2000 + "/exit\n/unknown\nwater seedlings\n/exit\n"
        result = self.run_command(self.windows_command("START_ELYSIA_UNIFIED.bat"), stdin_text=text)
        self.assertIn("Enter a synthetic question or /exit.", result.stdout)
        self.assertIn("Please use a question of 1 to 800 characters.", result.stdout)
        self.assertIn("Unknown command.", result.stdout)
        self.assertIn("water the seedlings on Tuesday morning.", result.stdout)
        self.assertIn("Session ended: 1 questions", result.stdout)

    def test_interactive_help_memories_and_explicit_python_entry(self):
        result = self.run_child("-m", "elysia", "--interactive",
                                stdin_text="/help\n/memories\n/restart\nreserved library books\nquit\n")
        self.assertIn("Ask with words from the samples.", result.stdout)
        self.assertIn("Synthetic garden schedule:", result.stdout)
        self.assertIn("Synthetic library pickup:", result.stdout)
        self.assertIn("Restart complete.", result.stdout)
        self.assertIn("collect reserved books from shelf B", result.stdout)

    def test_conservative_recall_rejects_generic_and_missing_facts(self):
        for query in ("what is it", "What is the telescope launch date?", "What is the flashing repair cost?",
                      "When should I inspect flashing?", "Where are the seedlings?", "Who damaged the flashing?", "How much water?"):
            payload = json.loads(self.run_child("elysia.py", "--query", query).stdout)
            self.assertEqual(payload["answer"], "No matching synthetic memory was found.")
            self.assertEqual(payload["recall"]["hits"], [])

    def test_recorded_time_and_location_details(self):
        for query, answer in [("What day should I water seedlings?", "Tuesday morning"),
                              ("Where are reserved library books?", "shelf B near the front desk")]:
            payload = json.loads(self.run_child("elysia.py", "--query", query).stdout)
            self.assertIn(answer, payload["answer"])

    def test_interactive_conflicting_modes_refused(self):
        self.run_child("elysia.py", "--interactive", "--stdin", expected=2)
        self.run_child("elysia.py", "--interactive", "--query", "flashing", expected=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
