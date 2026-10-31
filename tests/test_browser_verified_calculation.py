"""Single restricted browser: real guarded memory worker + PR175 calculator/journal."""
import json
from pathlib import Path
import re
import runpy
import shutil
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import elysia_restricted_browser as browser
from elysia_local_memory_chat import LocalOllama
from project_guardian import verified_local_calculation as lane

PASSWORD = "synthetic-browser-confirmation-password"
PORT = 5077
ENV = {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": f"127.0.0.1:{PORT}"}
ORIGIN = f"http://127.0.0.1:{PORT}"
INPUTS = {"rate": "35.50", "painters": 3, "days": 2, "hours_per_day": 8}


def post(client, path, body, csrf=None, **kwargs):
    return client.post(path, json=body, headers={"Origin": ORIGIN, **({"X-Elysia-CSRF": csrf} if csrf else {}),
                       **kwargs.pop("headers", {})}, environ_overrides={**ENV, **kwargs.pop("env", {})}, **kwargs)


def connect(app):
    client = app.test_client()
    assert post(client, "/session", {"password": PASSWORD}).status_code == 200
    csrf = client.get("/api/session", environ_overrides=ENV).json["csrf"]
    return client, csrf


def plan(client, csrf, inputs=None):
    response = post(client, "/api/calculation/prepare", INPUTS if inputs is None else inputs, csrf)
    assert response.status_code == 200, response.json
    return response.json["calculation"]


def confirm(client, csrf, prepared, **changes):
    fields = dict(request_id=prepared["request_id"], confirmation=prepared["confirmation_phrase"], password=PASSWORD)
    fields.update(changes)
    return post(client, "/api/calculation/confirm", fields, csrf)


@pytest.fixture
def surface(tmp_path, monkeypatch):
    code = tmp_path / "app"
    code.mkdir()
    files = runpy.run_path(str(ROOT / "tests/browser_test_support.py"))["FILES"]
    for name in (*files, "elysia_browser_worker.py"):
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    monkeypatch.setattr(browser, "CODE", code)
    now = [100.0]
    app = browser.create_app(password=PASSWORD, port=PORT, store="workflow", clock=lambda: now[0], local_model="synthetic:local")
    client, csrf = connect(app)
    yield app, client, csrf, code, now
    app.extensions["close_calculator"]()


def test_browser_prepare_confirm_persist_restart_and_memory_correction(surface, monkeypatch):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    assert prepared["inputs"] == INPUTS
    assert prepared["execution_attempted"] is False
    before = client.get("/api/calculations", environ_overrides=ENV).json
    assert before["outcomes"] == []
    result = confirm(client, csrf, prepared)
    assert result.status_code == 200, result.json
    out = result.json["outcome"]
    assert out["verification_status"] == "verified" and out["evidence"]["result"] == "1704"
    assert out["audit_persisted"] and not out["external_effect_verified"] and not out["durable_effect_verified"]
    assert result.json["task"]["status"] == result.json["objective"]["status"] == "completed"
    assert result.json["task"]["execution_evidence"] == out["evidence"]
    # Memory operates while the calculator byte lock remains live on Windows.
    for op, text in (("teach", "Fictional moonberry lantern color is violet."),
                     ("correct", "Fictional moonberry lantern color is amber.")):
        saved = post(client, "/api/" + op, {"key": "lantern", "text": text}, csrf)
        assert saved.status_code == 200, saved.json
    history = post(client, "/api/history", {"key": "lantern"}, csrf)
    assert len(history.json["revisions"]) == 2
    recall = post(client, "/api/recall", {"query": "moonberry lantern color"}, csrf)
    assert "amber" in recall.json["answer"]
    journal = code / ".synthetic-pilot-task-journals/browser-workflow/verified-calculations-v1/events.json"
    persisted = journal.read_bytes()
    app.extensions["close_calculator"]()
    restarted = browser.create_app(password=PASSWORD, port=PORT, store="workflow", clock=lambda: now[0])
    try:
        fresh, new_csrf = connect(restarted)
        monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("reload reran calculator"))
        status = fresh.get("/api/calculations", environ_overrides=ENV)
        assert status.status_code == 200 and status.json["outcomes"] == [out]
        assert status.json["execution_attempted"] is False
        assert journal.read_bytes() == persisted
        assert confirm(fresh, new_csrf, prepared).status_code == 409
        assert "amber" in post(fresh, "/api/recall", {"query": "moonberry lantern color"}, new_csrf).json["answer"]
    finally:
        restarted.extensions["close_calculator"]()


@pytest.mark.parametrize("path,fields", [("/api/calculation/prepare", INPUTS),
    ("/api/calculation/confirm", {"request_id": "x", "confirmation": "x", "password": PASSWORD})])
@pytest.mark.parametrize("bad", ["unauthenticated", "csrf", "origin", "host", "remote"])
def test_calculation_routes_preserve_existing_boundary(surface, path, fields, bad, monkeypatch):
    app, client, csrf, code, now = surface
    if bad == "unauthenticated": client = app.test_client()
    headers = {}
    env = {}
    if bad == "csrf": csrf = None
    if bad == "origin": headers["Origin"] = "http://untrusted.invalid"
    if bad == "host": env["HTTP_HOST"] = "localhost:5077"
    if bad == "remote": env["REMOTE_ADDR"] = "203.0.113.8"
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("denial executed calculator"))
    result = post(client, path, fields, csrf, headers=headers, env=env)
    assert result.status_code in {401, 403}
    assert not (code / ".synthetic-pilot-task-journals").exists()


@pytest.mark.parametrize("changes", [{"confirmation": "yes"}, {"password": "wrong"}, {"request_id": "forged"},
                                    {"rate": "99"}, {"grant": {"verified": True}}, {"authorized": True}])
def test_tampered_confirmation_cannot_authorize_or_change_inputs(surface, changes, monkeypatch):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("tampered confirmation executed"))
    result = confirm(client, csrf, prepared, **changes)
    assert result.status_code in {400, 401, 403, 409}
    assert client.get("/api/calculations", environ_overrides=ENV).json["outcomes"] == []


def test_replay_expiry_session_switch_logout_and_relogin(surface, monkeypatch):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    other, other_csrf = connect(app)
    assert confirm(other, other_csrf, prepared).status_code == 409
    assert confirm(client, csrf, prepared).json["outcome"]["verification_status"] == "verified"
    assert confirm(client, csrf, prepared).status_code == 409
    expired = plan(client, csrf)
    now[0] += 121
    assert confirm(client, csrf, expired).status_code == 409
    stale = plan(client, csrf)
    assert post(client, "/logout", {}, csrf).status_code == 200
    assert post(client, "/session", {"password": PASSWORD}).status_code == 200
    csrf = client.get("/api/session", environ_overrides=ENV).json["csrf"]
    assert confirm(client, csrf, stale).status_code == 409
    stale = plan(client, csrf)
    assert post(client, "/session", {"password": PASSWORD}).status_code == 200
    csrf = client.get("/api/session", environ_overrides=ENV).json["csrf"]
    assert confirm(client, csrf, stale).status_code == 409


def test_reauthentication_uses_original_login_failure_budget(surface):
    app, client, csrf, code, now = surface
    for _ in range(5):
        prepared = plan(client, csrf)
        assert confirm(client, csrf, prepared, password="wrong").status_code == 401
    prepared = plan(client, csrf)
    assert confirm(client, csrf, prepared).status_code == 429
    assert post(app.test_client(), "/session", {"password": PASSWORD}).status_code == 429


@pytest.mark.parametrize("mode", ["false_report", "interruption", "persistence", "terminal_persistence", "unrelated_writer"])
def test_false_or_failed_execution_never_becomes_verified(surface, monkeypatch, mode):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    if mode in {"persistence", "terminal_persistence"}:
        real_write = lane.MemoryCore._write_atomic
        writes = [0]
        def write(self, payload):
            writes[0] += 1
            if mode == "persistence" or writes[0] >= 2:
                raise OSError("full")
            return real_write(self, payload)
        monkeypatch.setattr(lane.MemoryCore, "_write_atomic", write)
        monkeypatch.setattr("time.sleep", lambda *a: None)
    else:
        def broken(expression):
            if mode == "interruption": raise KeyboardInterrupt()
            if mode == "unrelated_writer":
                writer = threading.Thread(target=lambda: (code / "unrelated-health.txt").write_text("healthy"))
                writer.start(); writer.join()
            return {"success": True, "verified": True, "result": "1704"}
        monkeypatch.setattr(lane, "calculate_local", broken)
    result = confirm(client, csrf, prepared)
    if mode in {"persistence", "terminal_persistence"}:
        assert result.status_code == 503 and result.json["outcome_unknown"] is True
    else:
        assert result.status_code == 200
        assert result.json["outcome"]["verification_status"] in {"partial", "failed"}
        assert result.json["objective"]["progress"] == 0
        assert not result.json["outcome"]["value_verified"]
    status = client.get("/api/calculations", environ_overrides=ENV)
    assert status.status_code == 200
    assert not any(row["verification_status"] == "verified" for row in status.json["outcomes"])
    assert confirm(client, csrf, prepared).status_code == 409


def test_concurrent_sessions_cannot_execute_during_another_dispatch(surface, monkeypatch):
    app, client, csrf, code, now = surface
    other, other_csrf = connect(app)
    first = plan(client, csrf)
    second = plan(other, other_csrf)
    entered, release = threading.Event(), threading.Event()
    real = lane.calculate_local
    def slow(expression):
        entered.set()
        assert release.wait(5)
        return real(expression)
    monkeypatch.setattr(lane, "calculate_local", slow)
    results = []
    thread = threading.Thread(target=lambda: results.append(confirm(client, csrf, first)))
    thread.start()
    try:
        assert entered.wait(5)
        assert confirm(other, other_csrf, second).status_code == 409
    finally:
        release.set(); thread.join(10)
    assert results[0].json["outcome"]["verification_status"] == "verified"
    assert confirm(other, other_csrf, second).json["outcome"]["verification_status"] == "verified"


def test_model_proposes_only_then_host_checks_current_rate_source(surface, monkeypatch):
    app, client, csrf, code, now = surface
    assert post(client, "/api/teach", {"key": "rate", "text": "Fictional labor rate is USD 35.50 per hour."}, csrf).status_code == 200
    def propose(self, messages, **kwargs):
        data = json.loads(messages[1]["content"])
        source = data["context_bundle"]["evidence"][0]["source_id"]
        return json.dumps({"tool": "calculator.labor", "arguments": {"rate_source_id": source, "painters": 3, "days": 2, "hours_per_day": 8}})
    monkeypatch.setattr(LocalOllama, "generate", propose)
    response = post(client, "/api/chat", {"query": "Use saved labor rate for three painters", "allow_calculator": True}, csrf)
    assert response.status_code == 200, response.json
    assert response.json["kind"] == "calculation_proposal"
    assert response.json["tools_executed"] == [] and not response.json["calculation_verified"]
    prepared = response.json["calculation"]
    assert prepared["inputs"]["rate"] == "35.50"
    assert client.get("/api/calculations", environ_overrides=ENV).json["outcomes"] == []
    assert confirm(client, csrf, prepared).json["outcome"]["evidence"]["result"] == "1704"
    proposed = post(client, "/api/chat", {"query": "Use saved labor rate", "allow_calculator": True}, csrf).json["calculation"]
    assert post(client, "/api/correct", {"key": "rate", "text": "Fictional labor rate is USD 40 per hour."}, csrf).status_code == 200
    assert confirm(client, csrf, proposed).status_code == 409
    proposed = post(client, "/api/chat", {"query": "Use saved labor rate", "allow_calculator": True}, csrf).json["calculation"]
    changed = browser.run_worker("workflow", {"operation": "correct", "key": "rate", "text": "Fictional labor rate is USD 45 per hour."})
    assert changed["ok"] is True
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("stale source executed"))
    assert confirm(client, csrf, proposed).status_code == 409


def test_checkbox_or_model_without_host_confirmation_never_executes(surface, monkeypatch):
    app, client, csrf, code, now = surface
    monkeypatch.setattr(LocalOllama, "generate", lambda *a, **k: json.dumps({"tool": "calculator.labor", "arguments": {"rate_source_id": "forged", "painters": 3, "days": 2, "hours_per_day": 8}}))
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("model response executed calculator"))
    response = post(client, "/api/chat", {"query": "calculate", "allow_calculator": True}, csrf)
    assert response.status_code == 503
    assert client.get("/api/calculations", environ_overrides=ENV).json["outcomes"] == []


def test_user_interface_has_explicit_review_and_no_password_or_html_injection(surface):
    app, client, csrf, code, now = surface
    page = client.get("/", environ_overrides=ENV).text
    script = client.get("/app.js", environ_overrides=ENV).text
    assert "Prepare for review" in page and "Re-enter existing session password" in page
    assert "Confirm and execute this calculation" in page
    assert "innerHTML" not in script and "textContent" in script
    assert PASSWORD not in page + script
    assert "allow_calculator" in script  # proposal-only backwards-compatible chat schema


def test_static_browser_javascript_parses():
    import subprocess
    checked = subprocess.run(["node", "--check", "--input-type=commonjs"], input=browser.JS,
                             text=True, capture_output=True)
    assert checked.returncode == 0, checked.stderr


def test_session_revocation_serializes_with_dispatch(surface, monkeypatch):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    peer = app.test_client()
    peer.set_cookie(browser.COOKIE, client.get_cookie(browser.COOKIE, domain="127.0.0.1").value, domain="127.0.0.1")
    entered, release = threading.Event(), threading.Event()
    real = lane.OperatorCalculationSession.authorize
    def paused(self, owned, **kwargs):
        entered.set()
        assert release.wait(5)
        return real(self, owned, **kwargs)
    monkeypatch.setattr(lane.OperatorCalculationSession, "authorize", paused)
    result = []
    thread = threading.Thread(target=lambda: result.append(confirm(client, csrf, prepared)))
    thread.start()
    try:
        assert entered.wait(5)
        assert post(peer, "/logout", {}, csrf).status_code == 409
        assert post(peer, "/session", {"password": PASSWORD}).status_code == 409
    finally:
        release.set(); thread.join(10)
    assert result[0].json["outcome"]["verification_status"] == "verified"
    assert post(peer, "/logout", {}, csrf).status_code == 200


@pytest.mark.parametrize("expiry", ["review", "session"])
def test_expiry_during_validation_cannot_mint_fresh_authority(surface, monkeypatch, expiry):
    app, client, csrf, code, now = surface
    if expiry == "session": now[0] += 1790
    prepared = plan(client, csrf)
    real = lane.OperatorCalculationSession.authorize
    def delayed(self, owned, **kwargs):
        now[0] += 121 if expiry == "review" else 20
        return real(self, owned, **kwargs)
    monkeypatch.setattr(lane.OperatorCalculationSession, "authorize", delayed)
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("expired approval executed"))
    result = confirm(client, csrf, prepared)
    assert result.status_code == 409



def test_lazy_package_retains_existing_public_exports_without_implicit_core_startup():
    import subprocess
    code = "import project_guardian as p,sys; assert 'project_guardian.core' not in sys.modules; from project_guardian import MemoryCore,GuardianCore; assert MemoryCore.__name__=='MemoryCore' and GuardianCore.__name__=='GuardianCore'"
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr



def test_grant_expiry_at_exact_dispatch_boundary_is_not_authorized(surface, monkeypatch):
    app, client, csrf, code, now = surface
    prepared = plan(client, csrf)
    deadline = now[0] + prepared["expires_in_seconds"]
    real = lane.OperatorCalculationSession.execute
    def boundary(self, owned, grant, **kwargs):
        now[0] = deadline
        return real(self, owned, grant, **kwargs)
    monkeypatch.setattr(lane.OperatorCalculationSession, "execute", boundary)
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("expired at dispatch"))
    result = confirm(client, csrf, prepared)
    assert result.status_code == 200
    assert result.json["outcome"]["verification_status"] == "blocked"
    assert not result.json["outcome"]["execution_attempted"]



def test_model_claimed_success_does_not_create_verified_task(surface, monkeypatch):
    app, client, csrf, code, now = surface
    monkeypatch.setattr(LocalOllama, "generate", lambda *a, **k: json.dumps({"answer": "I calculated it successfully."}))
    monkeypatch.setattr(lane, "calculate_local", lambda *a: pytest.fail("model assertion executed"))
    response = post(client, "/api/chat", {"query": "calculate", "allow_calculator": True}, csrf)
    assert response.status_code == 200
    assert response.json["tools_executed"] == [] and response.json["calculation_verified"] is False
    assert client.get("/api/calculations", environ_overrides=ENV).json["outcomes"] == []


def test_second_application_cannot_own_same_task_journal(surface):
    app, client, csrf, code, now = surface
    plan(client, csrf)
    other_app = browser.create_app(password=PASSWORD, port=PORT, store="workflow", clock=lambda: now[0])
    try:
        other, other_csrf = connect(other_app)
        busy = post(other, "/api/calculation/prepare", INPUTS, other_csrf)
        assert busy.status_code == 409
        app.extensions["close_calculator"]()
        assert post(other, "/api/calculation/prepare", INPUTS, other_csrf).status_code == 200
    finally:
        other_app.extensions["close_calculator"]()
