"""Stop-ownership regressions: exact argv, handle-bound terminate, mocked kills."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PILOT_DIR = Path(__file__).resolve().parents[1]
if str(PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(PILOT_DIR))

from pilot_identity import (  # noqa: E402
    ProcessSnapshot,
    argv_matches_expected,
    verify_live_ownership,
)
from pilot_paths import (  # noqa: E402
    APPLICATION_BASE_SHA,
    PILOT_DATA_ROOT,
    PILOT_MARKER,
    PILOT_PYTHON,
)
from pilot_winprocess import BoundProcess  # noqa: E402


def _load_stop_module():
    spec = importlib.util.spec_from_file_location(
        "pilot_stop_under_test", PILOT_DIR / "stop_verified_pilot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _complete_runtime(pid: int = 424242, **overrides):
    entry = str(
        Path(r"C:\Users\Owner\Elysia-Verified-Pilot\scripts\start_contained_browser_memory.py")
    )
    base = {
        "marker": PILOT_MARKER,
        "pid": pid,
        "python": str(PILOT_PYTHON),
        "entry_point": entry,
        "data_root": str(PILOT_DATA_ROOT),
        "process_create_filetime": "133000000000000000",
        "process_executable": str(PILOT_PYTHON),
        "shutdown_token": "abc123token",
        "application_base_sha": APPLICATION_BASE_SHA,
        "delivery_commit": "e3aa17aac8404d79276e41583bf5028baeaf6de0",
        "ui_host": "127.0.0.1",
        "ui_port": 5065,
    }
    base.update(overrides)
    return base


def _owned_snapshot(pid: int = 424242, **overrides):
    entry = r"C:\Users\Owner\Elysia-Verified-Pilot\scripts\start_contained_browser_memory.py"
    data = str(PILOT_DATA_ROOT)
    snap = ProcessSnapshot(
        pid=pid,
        name="python.exe",
        executable=str(PILOT_PYTHON),
        command_line=f'"{PILOT_PYTHON}" "{entry}" --disposable-root "{data}" --enable-ui --keep-alive',
        create_filetime="133000000000000000",
    )
    if overrides:
        snap = dataclasses.replace(snap, **overrides)
    return snap


def _fake_bound(pid: int = 424242, ft: str = "133000000000000000", image: str = ""):
    b = MagicMock(spec=BoundProcess)
    b.handle = 1
    b.pid = pid
    b.create_filetime = ft
    b.image_path = image or str(PILOT_PYTHON)
    b.refresh_times_match.return_value = True
    b.is_still_running.side_effect = [True, True, False]
    b.wait.return_value = True
    b.terminate.return_value = (True, "terminated_via_handle")
    b.close = MagicMock()
    return b


class TestArgvExact(unittest.TestCase):
    def test_wrong_entry_same_basename_refused(self):
        rt = _complete_runtime()
        ok, reason = argv_matches_expected(
            f'"{rt["python"]}" C:\\unrelated\\start_contained_browser_memory.py '
            f'--disposable-root "{rt["data_root"]}"',
            expected_python=Path(rt["python"]),
            expected_entry=Path(rt["entry_point"]),
            expected_data_root=Path(rt["data_root"]),
        )
        self.assertFalse(ok)
        self.assertIn("entry", reason)

    def test_decoy_data_root_argument_refused(self):
        rt = _complete_runtime()
        ok, reason = argv_matches_expected(
            f'"{rt["python"]}" "{rt["entry_point"]}" --disposable-root C:\\unrelated '
            f'--note "{rt["data_root"]}"',
            expected_python=Path(rt["python"]),
            expected_entry=Path(rt["entry_point"]),
            expected_data_root=Path(rt["data_root"]),
        )
        self.assertFalse(ok)

    def test_exact_argv_accepted(self):
        rt = _complete_runtime()
        snap = _owned_snapshot()
        ok, _ = argv_matches_expected(
            snap.command_line,
            expected_python=Path(rt["python"]),
            expected_entry=Path(rt["entry_point"]),
            expected_data_root=Path(rt["data_root"]),
        )
        self.assertTrue(ok)


class TestVerifyLiveOwnership(unittest.TestCase):
    def test_wrong_executable_not_accepted_via_cmdline(self):
        rt = _complete_runtime()
        snap = _owned_snapshot(executable=r"C:\unrelated\python.exe")
        v = verify_live_ownership(424242, rt, snapshot=snap)
        self.assertFalse(v.owned)

    def test_empty_executable_refused(self):
        rt = _complete_runtime()
        snap = _owned_snapshot(executable="")
        v = verify_live_ownership(424242, rt, snapshot=snap)
        self.assertFalse(v.owned)

    def test_snapshot_wrong_pid_refused(self):
        rt = _complete_runtime()
        snap = _owned_snapshot(pid=999999)
        v = verify_live_ownership(424242, rt, snapshot=snap)
        self.assertFalse(v.owned)

    def test_creation_mismatch_refused(self):
        rt = _complete_runtime()
        snap = _owned_snapshot(create_filetime="999")
        v = verify_live_ownership(424242, rt, snapshot=snap)
        self.assertFalse(v.owned)

    def test_matching_identity_accepts(self):
        rt = _complete_runtime()
        v = verify_live_ownership(424242, rt, snapshot=_owned_snapshot())
        self.assertTrue(v.owned)


class TestStopMainMocked(unittest.TestCase):
    def setUp(self):
        self.mod = _load_stop_module()

    def _patch_files(self, pid_text, runtime_obj):
        fake_pid = MagicMock()
        fake_pid.exists.return_value = True
        fake_pid.read_text.return_value = pid_text
        fake_pid.unlink = MagicMock()
        fake_rt = MagicMock()
        fake_rt.is_file.return_value = True
        fake_rt.exists.return_value = True
        if runtime_obj == "MALFORMED":
            fake_rt.read_text.return_value = "{not-json"
        else:
            fake_rt.read_text.return_value = json.dumps(runtime_obj)
        fake_rt.write_text = MagicMock()
        return fake_pid, fake_rt

    def test_stale_unrelated_python_refuses_without_terminate(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        bound = _fake_bound()
        unrelated = _owned_snapshot(
            executable=r"C:\unrelated\python.exe",
            command_line=r"C:\unrelated\python.exe unrelated.py",
        )
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(
            self.mod, "verify_live_ownership", return_value=MagicMock(owned=False, reason="unrelated", bound=None)
        ), patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(self.mod, "send_ctrl_c") as ctrl:
            # Force verify path using snapshot mismatch
            with patch.object(
                self.mod,
                "verify_live_ownership",
                return_value=MagicMock(owned=False, reason="unrelated", bound=None),
            ):
                code = self.mod.main()
        self.assertEqual(code, 3)
        bound.terminate.assert_not_called()
        ctrl.assert_not_called()

    def test_uncertain_open_refuses_not_treated_as_absent(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(None, "access_denied")
        ), patch.object(self.mod, "clear_shutdown_request"):
            code = self.mod.main()
        self.assertEqual(code, 3)
        fake_pid.unlink.assert_not_called()

    def test_not_found_cleans_pid(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(None, "not_found")
        ), patch.object(self.mod, "clear_shutdown_request"):
            code = self.mod.main()
        self.assertEqual(code, 0)
        fake_pid.unlink.assert_called()

    def test_malformed_runtime_with_live_process_refuses(self):
        fake_pid, fake_rt = self._patch_files("424242", "MALFORMED")
        bound = _fake_bound()
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(self.mod, "clear_shutdown_request"):
            code = self.mod.main()
        self.assertEqual(code, 3)
        bound.terminate.assert_not_called()

    def test_cooperative_success_via_handle_wait(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        bound = _fake_bound()
        bound.wait.return_value = True
        bound.is_still_running.return_value = False
        verdict = MagicMock(owned=True, reason="ok", bound=bound)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(
            self.mod, "verify_live_ownership", return_value=verdict
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(True, "ctrl_c_sent")
        ), patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(self.mod, "_port_in_use", return_value=False), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 0)
        bound.terminate.assert_not_called()

    def test_hard_terminate_uses_handle_not_taskkill_pid(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        bound = _fake_bound()
        # Cooperative wait fails; still running; then terminate + wait ok
        bound.wait.side_effect = [False, True]
        bound.is_still_running.side_effect = [True, False]
        bound.terminate.return_value = (True, "terminated_via_handle")
        verdict = MagicMock(owned=True, reason="ok", bound=bound)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(
            self.mod, "verify_live_ownership", return_value=verdict
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(False, "attach_failed")
        ), patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(self.mod, "_port_in_use", return_value=False), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 0)
        bound.terminate.assert_called_once()

    def test_port_still_listening_is_failure(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        bound = _fake_bound()
        bound.wait.return_value = True
        bound.is_still_running.return_value = False
        verdict = MagicMock(owned=True, reason="ok", bound=bound)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(
            self.mod, "verify_live_ownership", return_value=verdict
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(True, "ok")
        ), patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(self.mod, "_port_in_use", return_value=True), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 1)
        # Must not claim stop_ok via write with success when port held — write_text may still run? we return before write
        # In our stop code we return 1 before write_text when port not released

    def test_pid_reuse_gap_terminate_only_via_bound_handle(self):
        """After validation, terminate must use the bound handle object, not a PID retarget."""
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        bound = _fake_bound()
        bound.wait.side_effect = [False, True]
        bound.is_still_running.side_effect = [True, False]
        calls = []

        def term():
            calls.append(("terminate_handle", bound.handle, bound.pid))
            return True, "terminated_via_handle"

        bound.terminate.side_effect = term
        verdict = MagicMock(owned=True, reason="ok", bound=bound)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod.BoundProcess, "open", return_value=(bound, "")
        ), patch.object(
            self.mod, "verify_live_ownership", return_value=verdict
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(False, "intercepted")
        ), patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(self.mod, "_port_in_use", return_value=False), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("terminate_handle", 1, 424242)])


if __name__ == "__main__":
    unittest.main()
