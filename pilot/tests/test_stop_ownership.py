"""
Deterministic stop-ownership regressions (mocked termination).

Negative cases must never call real taskkill against live unrelated processes.
"""
from __future__ import annotations

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
    OwnershipVerdict,
    verify_live_ownership,
)
from pilot_paths import (  # noqa: E402
    APPLICATION_BASE_SHA,
    PILOT_MARKER,
    PILOT_DATA_ROOT,
    PILOT_PYTHON,
)


def _load_stop_module():
    spec = importlib.util.spec_from_file_location(
        "pilot_stop_under_test", PILOT_DIR / "stop_verified_pilot.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _complete_runtime(pid: int = 424242, **overrides):
    entry = str(Path(r"C:\Users\Owner\Elysia-Verified-Pilot\scripts\start_contained_browser_memory.py"))
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
        "delivery_commit": "fbcb78580ec2d7faaaf34988624731d753ecf068",
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
        command_line=f'"{PILOT_PYTHON}" "{entry}" --disposable-root {data} --enable-ui --keep-alive',
        create_filetime="133000000000000000",
    )
    if overrides:
        d = snap.__dict__.copy()
        d.update(overrides)
        snap = ProcessSnapshot(**d)
    return snap


class TestVerifyLiveOwnership(unittest.TestCase):
    def test_pid_and_marker_alone_insufficient(self):
        runtime = _complete_runtime()
        # Unrelated python at same PID/create-time mismatch path: wrong cmdline
        snap = ProcessSnapshot(
            pid=424242,
            name="python.exe",
            executable=r"C:\unrelated\python.exe",
            command_line=r"C:\unrelated\python.exe unrelated.py",
            create_filetime="133000000000000000",
        )
        verdict = verify_live_ownership(424242, runtime, snapshot=snap)
        self.assertFalse(verdict.owned)
        self.assertTrue(
            ("command line" in verdict.reason.lower())
            or ("executable" in verdict.reason.lower()),
            verdict.reason,
        )

    def test_creation_time_mismatch_refuses_reuse(self):
        runtime = _complete_runtime()
        snap = _owned_snapshot(create_filetime="999999999999999999")
        verdict = verify_live_ownership(424242, runtime, snapshot=snap)
        self.assertFalse(verdict.owned)
        self.assertIn("creation time", verdict.reason.lower())

    def test_missing_identity_fields_refuses(self):
        runtime = {"marker": PILOT_MARKER, "pid": 424242}
        verdict = verify_live_ownership(424242, runtime, snapshot=_owned_snapshot())
        self.assertFalse(verdict.owned)
        self.assertIn("missing", verdict.reason.lower())

    def test_matching_identity_accepts(self):
        runtime = _complete_runtime()
        verdict = verify_live_ownership(424242, runtime, snapshot=_owned_snapshot())
        self.assertTrue(verdict.owned)


class TestStopMainMocked(unittest.TestCase):
    def setUp(self):
        self.mod = _load_stop_module()

    def _patch_files(self, pid_text, runtime_obj):
        fake_pid = MagicMock()
        fake_pid.exists.return_value = True
        fake_pid.read_text.return_value = pid_text
        fake_pid.unlink = MagicMock()
        fake_rt = MagicMock()
        if runtime_obj is None:
            fake_rt.is_file.return_value = False
            fake_rt.exists.return_value = False
        else:
            fake_rt.is_file.return_value = True
            fake_rt.exists.return_value = True
            if isinstance(runtime_obj, Exception):
                fake_rt.read_text.side_effect = runtime_obj
            elif runtime_obj == "MALFORMED":
                fake_rt.read_text.return_value = "{not-json"
            else:
                fake_rt.read_text.return_value = json.dumps(runtime_obj)
            fake_rt.write_text = MagicMock()
        return fake_pid, fake_rt

    def test_stale_record_unrelated_python_refuses_kill(self):
        """Reproduction of independent-acceptance probe: must NOT taskkill."""
        runtime = _complete_runtime(pid=424242)
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        unrelated = ProcessSnapshot(
            pid=424242,
            name="python.exe",
            executable=r"C:\unrelated\python.exe",
            command_line=r"C:\unrelated\python.exe unrelated.py",
            create_filetime="133000000000000000",
        )
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", return_value=unrelated
        ), patch.object(
            self.mod, "taskkill_pid_only"
        ) as kill, patch.object(
            self.mod, "send_ctrl_c"
        ) as ctrl, patch.object(
            self.mod, "write_shutdown_request"
        ), patch.object(
            self.mod, "clear_shutdown_request"
        ):
            code = self.mod.main()
        self.assertEqual(code, 3)
        kill.assert_not_called()
        ctrl.assert_not_called()

    def test_reused_pid_different_create_time_refuses(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        snap = _owned_snapshot(create_filetime="111")
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", return_value=snap
        ), patch.object(self.mod, "taskkill_pid_only") as kill, patch.object(
            self.mod, "send_ctrl_c"
        ) as ctrl, patch.object(self.mod, "write_shutdown_request"), patch.object(
            self.mod, "clear_shutdown_request"
        ):
            code = self.mod.main()
        self.assertEqual(code, 3)
        kill.assert_not_called()
        ctrl.assert_not_called()

    def test_malformed_runtime_with_live_process_refuses(self):
        fake_pid, fake_rt = self._patch_files("424242", "MALFORMED")
        snap = _owned_snapshot()
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", return_value=snap
        ), patch.object(self.mod, "taskkill_pid_only") as kill, patch.object(
            self.mod, "send_ctrl_c"
        ) as ctrl, patch.object(self.mod, "clear_shutdown_request"):
            code = self.mod.main()
        self.assertEqual(code, 3)
        kill.assert_not_called()
        ctrl.assert_not_called()

    def test_stale_pid_not_running_cleans_without_kill(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", return_value=None
        ), patch.object(self.mod, "taskkill_pid_only") as kill, patch.object(
            self.mod, "send_ctrl_c"
        ) as ctrl, patch.object(self.mod, "clear_shutdown_request"):
            code = self.mod.main()
        self.assertEqual(code, 0)
        kill.assert_not_called()
        ctrl.assert_not_called()
        fake_pid.unlink.assert_called()

    def test_normal_pilot_shutdown_cooperative_no_hardkill(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        owned = _owned_snapshot()
        # First query: alive owned; after ctrl_c: gone
        queries = [owned, None]

        def _q(_pid):
            return queries.pop(0) if queries else None

        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", side_effect=_q
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(True, "ctrl_c_sent")
        ) as ctrl, patch.object(
            self.mod, "taskkill_pid_only"
        ) as kill, patch.object(
            self.mod, "write_shutdown_request"
        ) as req, patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(
            self.mod, "_port_in_use", return_value=False
        ), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 0)
        ctrl.assert_called_once()
        req.assert_called_once()
        kill.assert_not_called()

    def test_hardkill_fallback_is_pid_only_not_tree(self):
        runtime = _complete_runtime()
        fake_pid, fake_rt = self._patch_files("424242", runtime)
        owned = _owned_snapshot()
        state = {"killed": False}

        def _q(_pid):
            if state["killed"]:
                return None
            return owned

        def _kill(pid):
            state["killed"] = True
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(self.mod, "PID_FILE", fake_pid), patch.object(
            self.mod, "RUNTIME_JSON", fake_rt
        ), patch.object(
            self.mod, "query_process_snapshot", side_effect=_q
        ), patch.object(
            self.mod, "send_ctrl_c", return_value=(False, "attach_failed")
        ), patch.object(
            self.mod, "taskkill_pid_only", side_effect=_kill
        ) as kill, patch.object(
            self.mod, "write_shutdown_request"
        ), patch.object(
            self.mod, "clear_shutdown_request"
        ), patch.object(
            self.mod, "_port_in_use", return_value=False
        ), patch.object(
            self.mod.time, "sleep"
        ):
            code = self.mod.main()
        self.assertEqual(code, 0)
        kill.assert_called_once()
        self.assertEqual(kill.call_args[0][0], 424242)


class TestTaskkillHelper(unittest.TestCase):
    def test_taskkill_helper_never_passes_tree_flag(self):
        from pilot_identity import taskkill_pid_only

        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        taskkill_pid_only(99, runner=runner)
        self.assertEqual(calls[0][:4], ["taskkill", "/PID", "99", "/F"])
        self.assertNotIn("/T", calls[0])


if __name__ == "__main__":
    unittest.main()
