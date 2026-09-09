import importlib.util
import json
import threading
import time
from http.server import HTTPServer
from pathlib import Path

from project_guardian.openclaw_adapter import OpenClawAdapter, score_openclaw_result


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ELYSIA_PY = _PROJECT_ROOT / "elysia.py"
_SPEC = importlib.util.spec_from_file_location("elysia_main_module", _ELYSIA_PY)
_ELY_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_ELY_MOD)
UnifiedElysiaSystem = _ELY_MOD.UnifiedElysiaSystem


class _MemoryStub:
    def __init__(self):
        self.rows = []

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.rows.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


class _AdapterStub:
    def __init__(self, response):
        self.response = dict(response)
        self.calls = []

    def run_skill(self, skill_name, args=None):
        self.calls.append({"skill_name": skill_name, "args": dict(args or {})})
        out = dict(self.response)
        out.setdefault("skill", skill_name)
        out.setdefault("timestamp", "2026-01-01T00:00:00+00:00")
        out.setdefault("task_id", "task-1")
        out.setdefault("result", {"summary": "ok"})
        out.setdefault("error", None)
        return out


def test_openclaw_config_loads(tmp_path):
    cfg = {
        "enabled": True,
        "base_url": "http://127.0.0.1:9999",
        "timeout_seconds": 5,
        "default_skills": ["browser_research"],
    }
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    ad = OpenClawAdapter(config_path=str(cfg_path))
    assert ad.enabled is True
    assert ad.base_url == "http://127.0.0.1:9999"
    assert ad.timeout_seconds == 5
    assert ad.default_skills == ["browser_research"]


def test_openclaw_env_overrides_base_url(tmp_path, monkeypatch):
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "http://127.0.0.1:9999",
                "timeout_seconds": 5,
                "default_skills": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ELYSIA_OPENCLAW_BASE_URL", "http://127.0.0.1:18789")
    ad = OpenClawAdapter(config_path=str(cfg_path))
    assert ad.base_url == "http://127.0.0.1:18789"


def test_openclaw_unavailable_degrades_safely(tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "http://127.0.0.1:1",
                "timeout_seconds": 0.1,
                "default_skills": ["browser_research"],
            }
        ),
        encoding="utf-8",
    )
    ad = OpenClawAdapter(config_path=str(cfg_path))
    assert ad.is_available() is False
    out = ad.run_skill("browser_research", {"goal": "x"})
    assert out["ok"] is False
    assert out["skill"] == "browser_research"
    assert out["timestamp"]
    assert isinstance(ad.list_skills(), list)


def test_run_skill_returns_structured_json_when_disabled(tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps({"enabled": False, "base_url": "http://127.0.0.1:8765"}),
        encoding="utf-8",
    )
    ad = OpenClawAdapter(config_path=str(cfg_path))
    out = ad.run_skill("github_scan", {"query": "guardian"})
    assert set(out.keys()) >= {"ok", "task_id", "skill", "result", "error", "timestamp"}
    assert out["ok"] is False
    assert out["skill"] == "github_scan"


def test_delegate_to_openclaw_logs_and_writes_memory(monkeypatch):
    captured = {"calls": []}

    def _fake_append_openclaw_task_log(**kwargs):
        captured["calls"].append(kwargs)

    monkeypatch.setattr(_ELY_MOD, "append_openclaw_task_log", _fake_append_openclaw_task_log)

    system = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    system.openclaw = _AdapterStub(
        {
            "ok": True,
            "task_id": "oc-123",
            "result": {"summary": "Found useful repos."},
            "error": None,
        }
    )
    system.guardian = type("G", (), {"memory": _MemoryStub()})()
    system.last_openclaw_task = None
    system.last_openclaw_error = None

    out = system.delegate_to_openclaw(
        goal="Scan GitHub projects for integration",
        skill_name="github_scan",
        args={"query": "autonomy tools"},
    )
    assert out["ok"] is True
    assert out["task_id"] == "oc-123"
    assert "score" in out
    assert captured["calls"], "expected JSONL logger call"
    assert system.guardian.memory.rows, "expected memory feedback row"


def test_score_openclaw_result_handles_success_empty_error():
    ok_score = score_openclaw_result(
        "github research",
        {"ok": True, "result": {"repos": [{"name": "x"}], "summary": "useful"}, "error": None},
    )
    empty_score = score_openclaw_result("file scan", {"ok": True, "result": {}, "error": None})
    err_score = score_openclaw_result("browser research", {"ok": False, "result": {}, "error": "timeout"})

    assert ok_score["success_score"] > empty_score["success_score"]
    assert ok_score["usefulness_score"] > empty_score["usefulness_score"]
    assert err_score["error_score"] >= empty_score["error_score"]
    assert isinstance(ok_score["recommended_next_action"], str)


def test_autostart_skipped_when_env_disables(monkeypatch, tmp_path):
    monkeypatch.setenv("ELYSIA_OPENCLAW_AUTOSTART", "0")

    def _no_popen(*_a, **_k):
        raise AssertionError("subprocess.Popen should not be called when autostart disabled via env")

    monkeypatch.setattr("project_guardian.openclaw_adapter.subprocess.Popen", _no_popen)
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "http://127.0.0.1:1",
                "timeout_seconds": 0.2,
                "autostart": {"enabled": True, "command": ["should-not-run"], "max_wait_seconds": 5},
            }
        ),
        encoding="utf-8",
    )
    OpenClawAdapter(config_path=str(cfg_path))


def test_autostart_skips_when_command_empty(monkeypatch, tmp_path):
    def _no_popen(*_a, **_k):
        raise AssertionError("subprocess.Popen should not run when autostart.command is empty")

    monkeypatch.setattr("project_guardian.openclaw_adapter.subprocess.Popen", _no_popen)
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "http://127.0.0.1:1",
                "timeout_seconds": 0.2,
                "autostart": {"enabled": True, "command": [], "max_wait_seconds": 5},
            }
        ),
        encoding="utf-8",
    )
    OpenClawAdapter(config_path=str(cfg_path))


def test_shutdown_autostart_terminates_owned_process(monkeypatch, tmp_path):
    class _FakeProc:
        def __init__(self):
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    fake = _FakeProc()
    monkeypatch.setattr(
        "project_guardian.openclaw_adapter.OpenClawAdapter._maybe_autostart_worker",
        lambda self: None,
    )
    ad = OpenClawAdapter(config_path=str(tmp_path / "missing.json"))
    ad._autostart_proc = fake
    ad._autostart_owned = True
    ad.shutdown_autostart()
    assert fake.terminated is True
    assert ad._autostart_proc is None


def test_openclaw_stub_worker_script_is_reachable(tmp_path, monkeypatch):
    """scripts/openclaw_stub_worker.py speaks the same HTTP dialect as OpenClawAdapter."""
    stub_path = _PROJECT_ROOT / "scripts" / "openclaw_stub_worker.py"
    spec = importlib.util.spec_from_file_location("openclaw_stub_script", stub_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    skills = ["browser_research"]
    srv = HTTPServer(("127.0.0.1", 0), mod.make_handler(skills))
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    time.sleep(0.05)
    try:
        monkeypatch.setattr(
            "project_guardian.openclaw_adapter.OpenClawAdapter._maybe_autostart_worker",
            lambda self: None,
        )
        cfg_path = tmp_path / "openclaw.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "base_url": f"http://127.0.0.1:{port}",
                    "timeout_seconds": 5,
                    "default_skills": skills,
                    "autostart": {"enabled": False},
                }
            ),
            encoding="utf-8",
        )
        ad = OpenClawAdapter(config_path=str(cfg_path))
        assert ad.is_available() is True
        listed = ad.list_skills()
        assert isinstance(listed, list) and listed
        out = ad.run_skill("browser_research", {"goal": "probe"})
        assert out["ok"] is True
        assert "result" in out
    finally:
        srv.shutdown()
        th.join(timeout=3.0)

