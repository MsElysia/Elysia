"""Cross-process launch claim / lifetime-ready regressions (Codex simultaneous-launch gap)."""
from __future__ import annotations

import contextlib
import multiprocessing as mp
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PILOT_DIR = Path(__file__).resolve().parents[1]
SRC = PILOT_DIR.parent
sys.path[:0] = [str(PILOT_DIR), str(SRC)]

import launch_verified_pilot as launch  # noqa: E402
import pilot_exclusion as excl  # noqa: E402


def _second_claim_worker(root_str: str, result_q: mp.Queue) -> None:
    sys.path[:0] = [str(PILOT_DIR), str(SRC)]
    import pilot_exclusion as pe

    claim, reason = pe.try_acquire_launch_claim(data_root=Path(root_str), blocking=False)
    result_q.put((claim is not None, reason))
    if claim is not None:
        claim.release()


class TestLaunchExclusion(unittest.TestCase):
    def test_launch_claim_blocks_second_process(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "runtime").mkdir(parents=True)
            claim, reason = excl.try_acquire_launch_claim(data_root=root, blocking=False)
            self.assertIsNotNone(claim, reason)
            q: mp.Queue = mp.Queue()
            proc = mp.Process(target=_second_claim_worker, args=(str(root), q))
            proc.start()
            proc.join(10)
            self.assertEqual(proc.exitcode, 0)
            acquired, other_reason = q.get(timeout=2)
            self.assertFalse(acquired, other_reason)
            self.assertTrue(excl.launch_claim_is_held(data_root=root))
            claim.release()
            claim2, reason2 = excl.try_acquire_launch_claim(data_root=root, blocking=False)
            self.assertIsNotNone(claim2, reason2)
            claim2.release()

    def test_own_launch_claim_does_not_self_block_writer_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "runtime").mkdir(parents=True)
            claim, reason = excl.try_acquire_launch_claim(data_root=root, blocking=False)
            self.assertIsNotNone(claim, reason)
            entry = SRC / "scripts" / "start_contained_browser_memory.py"
            pid = root / "runtime" / "pilot.pid"
            rt = root / "runtime" / "pilot.runtime.json"
            blocked = excl.writer_exclusion_status(
                entry=entry, data_root=root, pid_file=pid, runtime_json=rt
            )
            self.assertFalse(blocked.get("safe_to_write"))
            self.assertEqual(blocked.get("reason"), "launch_claim_held_by_other")
            ok = excl.writer_exclusion_status(
                entry=entry,
                data_root=root,
                own_launch_claim=claim,
                pid_file=pid,
                runtime_json=rt,
            )
            self.assertTrue(ok.get("safe_to_write"), ok)
            hold = ok.get("hold")
            if hold is not None:
                hold.release()
            claim.release()

    def test_spawn_boundary_claim_held_blocks_exclusion_interloper(self):
        """Codex edge pattern: at Popen time another process must not take the store."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ("runtime", "inbox", "inbox_state", "logs", "memory", "temp"):
                (root / d).mkdir(parents=True)
            (root / "memory" / "guardian_memory.json").write_text("[]", encoding="utf-8")
            interloper_out: list[str] = []
            real_popen = subprocess.Popen
            entry_path = SRC / "scripts" / "start_contained_browser_memory.py"
            py = Path(sys.executable)
            # Cross-process interloper (Windows mutexes are re-entrant in-process).
            interloper_code = (
                "import sys; from pathlib import Path; "
                f"sys.path[:0]=[{str(PILOT_DIR)!r},{str(SRC)!r}]; "
                "from pilot_exclusion import try_acquire_exclusion, try_acquire_launch_claim; "
                f"root=Path({str(root)!r}); "
                "h,e=try_acquire_exclusion(data_root=root, timeout_ms=0); "
                "c,cr=try_acquire_launch_claim(data_root=root, blocking=False); "
                "print('mutex=' + str(bool(h)) + ' ' + str(e) + '; claim=' + str(bool(c)) + ' ' + str(cr)); "
                "h and h.release(); c and c.release()"
            )

            def intercept(cmd, *a, **kw):
                if isinstance(cmd, list) and any(
                    "start_contained_browser_memory.py" in str(x) for x in cmd
                ):
                    self.assertTrue(excl.launch_claim_is_held(data_root=root))
                    child = subprocess.run(
                        [str(py), "-B", "-c", interloper_code],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    interloper_out.append((child.stdout or "") + (child.stderr or ""))
                    raise RuntimeError("verification spawn intercepted after gap proof")
                return real_popen(cmd, *a, **kw)

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(launch, "PILOT_DATA_ROOT", root))
                stack.enter_context(patch.object(launch, "PID_FILE", root / "runtime" / "pilot.pid"))
                stack.enter_context(
                    patch.object(launch, "RUNTIME_JSON", root / "runtime" / "pilot.runtime.json")
                )
                stack.enter_context(patch.object(launch, "RUNTIME_DIR", root / "runtime"))
                stack.enter_context(patch.object(launch, "LAUNCH_LOG", root / "logs" / "launch.log"))
                stack.enter_context(patch.object(launch, "INBOX_DIR", root / "inbox"))
                stack.enter_context(patch.object(launch, "PILOT_PYTHON", py))
                stack.enter_context(patch.object(launch, "PILOT_SOURCE_ROOT", SRC))
                stack.enter_context(patch.object(excl, "PILOT_DATA_ROOT", root))
                stack.enter_context(patch.object(subprocess, "Popen", side_effect=intercept))
                stack.enter_context(patch.object(launch, "_already_running", return_value=False))
                stack.enter_context(patch.object(launch, "_choose_port", return_value=51299))
                stack.enter_context(
                    patch.object(launch, "expected_entry_path", return_value=entry_path)
                )
                stack.enter_context(
                    patch.object(
                        launch,
                        "read_delivery_identity",
                        return_value={
                            "delivery_commit": "0" * 40,
                            "delivery_status": "clean",
                            "exact_verified_delivery": True,
                        },
                    )
                )
                stack.enter_context(
                    patch(
                        "inbox_import.scan_inbox_to_memory",
                        return_value={
                            "ok": True,
                            "scanned": 0,
                            "imported": 0,
                            "duplicates": 0,
                            "rejected": 0,
                            "inbox_dir": str(root / "inbox"),
                            "errors": [],
                        },
                    )
                )
                with self.assertRaises(RuntimeError):
                    launch.main()
            self.assertEqual(len(interloper_out), 1, interloper_out)
            detail = interloper_out[0]
            self.assertIn("mutex=False", detail, detail)
            self.assertIn("claim=False", detail, detail)

    def test_lifetime_ready_required_before_claim_release_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "runtime").mkdir(parents=True)
            claim, _ = excl.try_acquire_launch_claim(data_root=root, blocking=False)
            self.assertIsNotNone(claim)
            self.assertFalse(excl.wait_for_lifetime_ready(data_root=root, timeout_sec=0.3))
            excl.write_lifetime_ready(data_root=root)
            self.assertTrue(excl.wait_for_lifetime_ready(data_root=root, timeout_sec=1.0))
            claim.release()
