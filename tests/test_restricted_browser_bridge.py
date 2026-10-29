"""Real registered Flask routes and real guarded workers; no listener/providers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import elysia_restricted_browser as browser

def _deny_network(event, args):
    if event in {"socket.bind", "socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("no-network browser verification: " + event)
sys.addaudithook(_deny_network)

PASSWORD = "synthetic-browser-test-password"
PORT = 5077
ORIGIN = f"http://127.0.0.1:{PORT}"
ORIGINAL = "Fictional moonberry lantern color is violet."
CORRECTED = "Fictional moonberry lantern color is amber."
ENV = {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": f"127.0.0.1:{PORT}"}


@pytest.fixture
def closure(tmp_path, monkeypatch):
    app = tmp_path / "isolated-app"
    app.mkdir()
    files = runpy.run_path(str(ROOT / "tests/test_canonical_windows_app.py"))["FILES"]
    for name in (*files, "elysia_browser_worker.py"):
        dest = app / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    monkeypatch.setattr(browser, "CODE", app)
    return app


@pytest.fixture
def surface(closure):
    app = browser.create_app(password=PASSWORD, port=PORT)
    app.config["TESTING"] = True
    return app, app.test_client(), closure


def request(client, path, body=None, headers=None, env=None, method="POST"):
    return client.open(path, method=method, json=body,
        headers={"Origin": ORIGIN, **(headers or {})},
        environ_overrides={**ENV, **(env or {})})


def login(client):
    response = request(client, "/session", {"password": PASSWORD})
    assert response.status_code == 200
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    session = request(client, "/api/session", method="GET")
    assert session.status_code == 200
    assert session.json["synthetic_only"] is True
    assert session.json["providers"] is False and session.json["autonomy"] is False
    return {"X-Elysia-CSRF": session.json["csrf"]}


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_unauthenticated_page_has_no_credential_or_external_script(surface):
    app, client, root = surface
    before = snapshot(root)
    page = request(client, "/", method="GET")
    assert page.status_code == 200
    assert PASSWORD not in page.text and "RESTRICTED_TOKEN" not in page.text
    assert '<script src="/app.js"' in page.text
    assert '<script src="http' not in page.text
    assert "default-src 'none'" in page.headers["Content-Security-Policy"]
    assert page.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in page.headers
    assert request(client, "/api/session", method="GET").status_code == 401
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}).status_code == 401
    assert snapshot(root) == before
    routes = {r.rule for r in app.url_map.iter_rules()}
    assert not routes.intersection({"/api/autonomy", "/api/tasks/submit", "/socket.io", "/api/credentials"})


@pytest.mark.parametrize("headers,env", [
    ({"Origin": "http://untrusted.invalid"}, {}),
    ({"Origin": "null"}, {}),
    ({}, {"HTTP_HOST": "untrusted.invalid"}),
    ({}, {"HTTP_HOST": "localhost:5077"}),
    ({}, {"REMOTE_ADDR": "203.0.113.8"}),
])
def test_invalid_authority_denied_without_writes(surface, headers, env):
    _, client, root = surface
    csrf = login(client)
    before = snapshot(root)
    r = request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL},
                headers={**csrf, **headers}, env=env)
    assert r.status_code == 403
    assert snapshot(root) == before


def test_missing_origin_and_missing_csrf_denied(surface):
    _, client, root = surface
    csrf = login(client)
    before = snapshot(root)
    assert client.post("/api/teach", json={"key": "lantern", "text": ORIGINAL},
                       headers=csrf, environ_overrides=ENV).status_code == 403
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}).status_code == 403
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL},
                   headers={"X-Elysia-CSRF": "wrong"}).status_code == 403
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL},
                   headers={"X-Elysia-CSRF": "wrong-\u00e9"}).status_code == 403
    assert snapshot(root) == before


def test_wrong_password_rate_limit_and_no_persistence(surface):
    _, client, root = surface
    before = snapshot(root)
    for _ in range(5):
        assert request(client, "/session", {"password": "wrong"}).status_code == 401
    assert request(client, "/session", {"password": PASSWORD}).status_code == 429
    assert snapshot(root) == before


def test_login_requires_origin(surface):
    _, client, _ = surface
    assert client.post("/session", json={"password": PASSWORD}, environ_overrides=ENV).status_code == 403


def test_complete_workflow_reopen_and_duplicate_preservation(surface):
    _, client, root = surface
    csrf = login(client)
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf).json["ok"]
    first = request(client, "/api/recall", {"query": "What color is the moonberry lantern?"}, headers=csrf)
    assert first.status_code == 200 and ORIGINAL in first.json["answer"]
    assert first.json["evidence"]["hits"]
    assert request(client, "/api/correct", {"key": "lantern", "text": CORRECTED}, headers=csrf).json["ok"]
    history = request(client, "/api/history", {"key": "lantern"}, headers=csrf)
    assert len(history.json["revisions"]) == 2
    assert ORIGINAL in history.json["revisions"][0] and CORRECTED in history.json["revisions"][1]
    before = snapshot(root)
    duplicate = request(client, "/api/correct", {"key": "lantern", "text": CORRECTED}, headers=csrf)
    assert duplicate.json["ok"] and "Duplicate" in duplicate.json["message"]
    assert snapshot(root) == before
    # Every operation already used a fresh actual worker. Recreate the HTTP app too.
    replacement = browser.create_app(password=PASSWORD, port=PORT).test_client()
    old_cookie = client.get_cookie(browser.COOKIE, domain="127.0.0.1")
    replacement.set_cookie(browser.COOKIE, old_cookie.value, domain="127.0.0.1")
    assert request(replacement, "/api/session", method="GET").status_code == 401
    new_csrf = login(replacement)
    recalled = request(replacement, "/api/recall", {"query": "Tell me the moonberry lantern color."}, headers=new_csrf)
    assert CORRECTED in recalled.json["answer"] and ORIGINAL not in recalled.json["answer"]
    assert snapshot(root) == before
    unknown = request(replacement, "/api/recall", {"query": "moonberry lantern price"}, headers=new_csrf)
    assert not unknown.json["evidence"]["hits"]
    assert request(replacement, "/logout", {}, headers=new_csrf).status_code == 200
    assert request(replacement, "/api/session", method="GET").status_code == 401


def test_expired_session_denied(closure):
    tick = [0]
    app = browser.create_app(password=PASSWORD, port=PORT, clock=lambda: tick[0])
    client = app.test_client()
    csrf = login(client)
    before = snapshot(closure)
    tick[0] = 1801
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf).status_code == 401
    assert snapshot(closure) == before


@pytest.mark.parametrize("body", [{}, {"key": "lantern", "text": ORIGINAL, "path": "elsewhere"},
    {"key": "../escape", "text": ORIGINAL}, {"key": "lantern", "text": "Real data"},
    {"key": "lantern", "text": 23}, []])
def test_malformed_requests_do_not_write(surface, body):
    _, client, root = surface
    csrf = login(client)
    before = snapshot(root)
    assert request(client, "/api/teach", body, headers=csrf).status_code == 400
    assert snapshot(root) == before


def test_corruption_is_not_success_or_reset(surface):
    _, client, root = surface
    csrf = login(client)
    index = root / ".synthetic-pilot-stores/browser-pilot/synthetic-learning.json"
    index.write_text("[")
    before = snapshot(root)
    r = request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf)
    assert r.status_code == 409 and r.json["ok"] is False
    assert snapshot(root) == before
    with pytest.raises(RuntimeError, match="store unavailable"):
        browser.create_app(password=PASSWORD, port=PORT)
    assert snapshot(root) == before


@pytest.mark.parametrize("kind", ["timeout", "invalid-output"])
def test_worker_failure_never_becomes_success(closure, kind):
    real = browser.run_worker
    def runner(store, command):
        if command["operation"] == "inspect":
            return real(store, command)
        if kind == "timeout":
            raise subprocess.TimeoutExpired("synthetic worker", 15)
        raise ValueError("malformed worker response")
    client = browser.create_app(password=PASSWORD, port=PORT, runner=runner).test_client()
    csrf = login(client)
    before = snapshot(closure)
    r = request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf)
    assert r.status_code == 503 and r.json["ok"] is False and r.json["outcome_unknown"]
    assert snapshot(closure) == before


def test_failed_actual_commit_preserves_store(surface, monkeypatch):
    _, _, root = surface
    real = browser.run_worker
    def runner(store, command):
        if command["operation"] == "inspect":
            return real(store, command)
        # Execute the real worker after injecting a deterministic commit failure.
        code = "from project_guardian.local_ingestion.apply_transaction import ApplyTransaction\n" \
               "def fail(self): raise OSError('synthetic disk failure')\n" \
               "ApplyTransaction.commit=fail\nimport elysia_browser_worker as w\nraise SystemExit(w.main())"
        env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-S", "-B", "-c", code, store],
            cwd=root, env=env, input=json.dumps(command), text=True, capture_output=True, timeout=15)
        return json.loads(result.stdout)
    client = browser.create_app(password=PASSWORD, port=PORT, runner=runner).test_client()
    csrf = login(client)
    before = snapshot(root)
    r = request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf)
    assert r.status_code == 409 and r.json["ok"] is False
    assert snapshot(root) == before


def test_symlink_workspace_refused(closure, tmp_path):
    target = tmp_path / "unrelated"
    target.mkdir()
    (target / "sentinel").write_text("preserve")
    try:
        (closure / ".synthetic-pilot-stores").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable; native junction test remains mandatory")
    with pytest.raises(RuntimeError, match="store unavailable"):
        browser.create_app(password=PASSWORD, port=PORT)
    assert sorted(p.name for p in target.iterdir()) == ["sentinel"]


def test_busy_request_is_bounded_and_not_replayed(closure):
    entered, release = threading.Event(), threading.Event()
    real = browser.run_worker
    calls = []
    def runner(store, command):
        if command["operation"] != "inspect":
            calls.append(command)
            entered.set()
            assert release.wait(5)
        return real(store, command)
    app = browser.create_app(password=PASSWORD, port=PORT, runner=runner)
    a, b = app.test_client(), app.test_client()
    ca, cb = login(a), login(b)
    outcomes = []
    t = threading.Thread(target=lambda: outcomes.append(request(a, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=ca)))
    t.start()
    try:
        assert entered.wait(5)
        r = request(b, "/api/teach", {"key": "other", "text": CORRECTED}, headers=cb)
        assert r.status_code == 409 and len(calls) == 1
    finally:
        release.set()
        t.join(10)
    assert not t.is_alive() and outcomes[0].json["ok"]


@pytest.mark.parametrize("store", ["../real-data", "/tmp/other", "C:\\user-memory", "UPPER", "x" * 21])
def test_store_selector_cannot_be_a_path_or_unbounded_name(store):
    def forbidden(*args):
        pytest.fail("invalid store reached worker")
    with pytest.raises(ValueError):
        browser.create_app(password=PASSWORD, port=PORT, store=store, runner=forbidden)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory descriptor regression")
@pytest.mark.parametrize("operation", ["inside-cleanup", "outside-scan", "outside-remove", "outside-rename"])
def test_offline_guard_handles_descriptors_without_allowing_escape(closure, tmp_path, operation):
    inside, outside = tmp_path / "guard-data", tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (outside / "sentinel").write_text("preserve")
    script = '''import os,sys,shutil
from pathlib import Path
from elysia_offline import install_offline_guard,OfflineBoundaryError
inside,outside,op=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
fd=os.open(outside,os.O_RDONLY|os.O_DIRECTORY)
tree=inside/'tree';tree.mkdir();(tree/'child').write_text('synthetic')
install_offline_guard(inside)
if op=='inside-cleanup':
    shutil.rmtree(tree)
    assert not tree.exists()
else:
    try:
        if op=='outside-scan': list(os.scandir(fd))
        elif op=='outside-remove': os.remove('sentinel',dir_fd=fd)
        elif op=='outside-rename': os.rename('sentinel',str(inside/'stolen'),src_dir_fd=fd)
    except OfflineBoundaryError: print('DENIED')
    else: raise AssertionError('outside descriptor escaped')
os.close(fd)
'''
    r = subprocess.run([sys.executable, "-S", "-B", "-c", script, str(inside), str(outside), operation],
        cwd=closure, env={"PATH": os.environ["PATH"]}, text=True, capture_output=True, timeout=10)
    assert r.returncode == 0, r.stderr
    if operation != "inside-cleanup":
        assert "DENIED" in r.stdout
    assert (outside / "sentinel").read_text() == "preserve"
    assert not (inside / "stolen").exists()


def test_worker_inspection_does_not_load_legacy_core_or_credentials(closure):
    r = browser.run_worker("pilot", {"operation": "inspect"})
    assert r["ok"] and not r["legacy_core_loaded"] and not r["credential_manager_loaded"]


def test_offline_guard_refuses_hardlinked_write_target(closure, tmp_path):
    inside = tmp_path / "guard-data"
    inside.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve", encoding="utf-8")
    os.link(outside, inside / "linked.txt")
    code = '''from pathlib import Path
import sys
from elysia_offline import install_offline_guard, OfflineBoundaryError
inside = Path(sys.argv[1])
install_offline_guard(inside)
try:
    (inside / "linked.txt").write_text("changed")
except OfflineBoundaryError:
    print("DENIED")
else:
    raise AssertionError("hardlinked write escaped")
'''
    result = subprocess.run([sys.executable, "-S", "-B", "-c", code, str(inside)],
        cwd=closure, env={"PATH": os.environ["PATH"]}, capture_output=True,
        text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "DENIED" in result.stdout
    assert outside.read_text(encoding="utf-8") == "preserve"


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction acceptance still required")
def test_windows_junction_workspace_refused(closure, tmp_path):
    target = tmp_path / "external"
    target.mkdir()
    (target / "sentinel").write_text("preserve")
    link = closure / ".synthetic-pilot-stores"
    result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    with pytest.raises(RuntimeError, match="store unavailable"):
        browser.create_app(password=PASSWORD, port=PORT)
    assert sorted(p.name for p in target.iterdir()) == ["sentinel"]


def test_unmarked_existing_store_is_preserved_without_initialization(closure):
    store = closure / ".synthetic-pilot-stores/browser-pilot"
    store.mkdir(parents=True)
    (store / "sentinel").write_text("preserve")
    before = snapshot(closure)
    with pytest.raises(RuntimeError, match="store unavailable"):
        browser.create_app(password=PASSWORD, port=PORT)
    assert snapshot(closure) == before


def test_partial_commit_process_exit_recovers_then_retries_once(surface):
    _, client, root = surface
    csrf = login(client)
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf).json["ok"]
    before = snapshot(root)
    code = '''import os
from pathlib import Path
real=os.replace
def crash(src,dst):
    real(src,dst)
    if Path(src).name=='stage-0': os._exit(77)
os.replace=crash
import elysia_browser_worker as w
raise SystemExit(w.main())
'''
    env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}}
    interrupted = subprocess.run([sys.executable, "-S", "-B", "-c", code, "pilot"], cwd=root,
        env=env, input=json.dumps({"operation": "correct", "key": "lantern", "text": CORRECTED}),
        text=True, capture_output=True, timeout=15)
    assert interrupted.returncode == 77
    history = request(client, "/api/history", {"key": "lantern"}, headers=csrf)
    assert history.status_code == 200 and len(history.json["revisions"]) == 1
    assert ORIGINAL in history.json["revisions"][0]
    assert snapshot(root) == before
    corrected = request(client, "/api/correct", {"key": "lantern", "text": CORRECTED}, headers=csrf)
    assert corrected.json["ok"]
    after = snapshot(root)
    assert request(client, "/api/correct", {"key": "lantern", "text": CORRECTED}, headers=csrf).json["ok"]
    assert snapshot(root) == after
    assert len(request(client, "/api/history", {"key": "lantern"}, headers=csrf).json["revisions"]) == 2


@pytest.mark.parametrize("path", ["/api/autonomy", "/api/tasks/submit", "/api/credentials", "/api/inspect?path=elsewhere"])
def test_privileged_and_path_selection_requests_are_denied(surface, path):
    _, client, root = surface
    csrf = login(client)
    before = snapshot(root)
    r = request(client, path, {"enabled": True}, headers=csrf)
    assert r.status_code in (400, 404)
    assert snapshot(root) == before


def test_oversized_and_malformed_json_are_denied(surface):
    _, client, root = surface
    csrf = login(client)
    before = snapshot(root)
    for body, status in [("[", 400), ("x" * 5000, 413)]:
        r = client.post("/api/teach", data=body, content_type="application/json",
                        headers={"Origin": ORIGIN, **csrf}, environ_overrides=ENV)
        assert r.status_code == status
    assert snapshot(root) == before


@pytest.mark.parametrize("operation", ["teach", "correct"])
def test_silently_aborted_commit_cannot_acknowledge_a_write(surface, operation):
    _, normal, root = surface
    normal_csrf = login(normal)
    if operation == "correct":
        assert request(normal, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=normal_csrf).json["ok"]
    real = browser.run_worker
    def runner(store, command):
        if command["operation"] == "inspect":
            return real(store, command)
        code = "from project_guardian.local_ingestion.apply_transaction import ApplyTransaction\n" \
               "ApplyTransaction.commit=lambda self: self.abort()\n" \
               "import elysia_browser_worker as w\nraise SystemExit(w.main())"
        env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}}
        result = subprocess.run([sys.executable, "-S", "-B", "-c", code, store], cwd=root,
            env=env, input=json.dumps(command), text=True, capture_output=True, timeout=15)
        return json.loads(result.stdout)
    faulty = browser.create_app(password=PASSWORD, port=PORT, runner=runner).test_client()
    csrf = login(faulty)
    before = snapshot(root)
    text = CORRECTED if operation == "correct" else ORIGINAL
    r = request(faulty, "/api/" + operation, {"key": "lantern", "text": text}, headers=csrf)
    assert r.status_code == 409 and r.json["ok"] is False, r.json
    assert r.json["outcome_unknown"]
    assert snapshot(root) == before
    # Recovery is an explicit retry via the real unmodified transaction engine.
    success = request(normal, "/api/" + operation, {"key": "lantern", "text": text}, headers=normal_csrf)
    assert success.status_code == 200 and success.json["ok"]
    assert success.json["written"] is True
    after = snapshot(root)
    duplicate = request(normal, "/api/" + operation, {"key": "lantern", "text": text}, headers=normal_csrf)
    assert duplicate.json["ok"] and duplicate.json["written"] is False
    assert snapshot(root) == after


@pytest.mark.parametrize("scenario", ["new-key", "other-key", "old-revision"])
def test_duplicate_requires_requested_key_and_current_value(surface, scenario):
    _, client, root = surface
    csrf = login(client)
    assert request(client, "/api/teach", {"key": "lantern", "text": ORIGINAL}, headers=csrf).json["ok"]
    if scenario == "other-key":
        assert request(client, "/api/teach", {"key": "other", "text": CORRECTED}, headers=csrf).json["ok"]
    elif scenario == "old-revision":
        assert request(client, "/api/correct", {"key": "lantern", "text": CORRECTED}, headers=csrf).json["ok"]
    key = {"new-key": "missing", "other-key": "other", "old-revision": "lantern"}[scenario]
    operation = "teach" if scenario == "new-key" else "correct"
    before = snapshot(root)
    result = request(client, "/api/" + operation, {"key": key, "text": ORIGINAL}, headers=csrf)
    assert result.status_code == 409 and result.json["ok"] is False, result.json
    assert snapshot(root) == before
    history = request(client, "/api/history", {"key": key}, headers=csrf)
    if scenario == "new-key":
        assert history.status_code == 409
    else:
        assert CORRECTED in history.json["revisions"][-1]
    # An actual retry of the current value remains an idempotent success.
    value = ORIGINAL if scenario == "new-key" else CORRECTED
    current_key = "lantern" if scenario == "new-key" else key
    duplicate = request(client, "/api/correct", {"key": current_key, "text": value.upper().replace("FICTIONAL", "Fictional")}, headers=csrf)
    assert duplicate.status_code == 200 and duplicate.json["written"] is False
    assert snapshot(root) == before
