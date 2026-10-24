"""ELY-153-SECURITY-REGRESSION-001 — unauthorized boundary regression tests.

Target product SHA: 821b9f4459eb888ad79d7845a8826a9f6cb94e3e
Mode: isolated, draft-only, regression tests only. No production repairs.

These tests assert secure denial behavior. A FAIL on a security assertion is
valid defect evidence at the exact SHA. Import/fixture failure is BLOCKED.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import re
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

from tests.security_isolation_helpers import (
    CREDENTIAL_ROUTES,
    SYNTHETIC_TOKEN,
    TARGET_SHA,
    UNTRUSTED_ORIGIN,
    IsolationGuard,
    RecordingFakeRegistry,
    assert_denied,
    build_isolated_panel,
    extract_remote_dynamic_imports,
    extract_script_sources,
    install_fake_auto_learning,
    is_remote_url,
)

# ---------------------------------------------------------------------------
# Fixture / SHA guards
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def product_sha() -> str:
    root = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    return sha


@pytest.fixture(scope="module")
def require_exact_sha(product_sha):
    if product_sha != TARGET_SHA:
        pytest.fail(
            f"BLOCKED: product SHA {product_sha} != required exact SHA {TARGET_SHA}. "
            "Do not transfer PASS/FAIL from another commit."
        )


@pytest.fixture
def isolated_panel(require_exact_sha):
    """Isolated dashboard panel; does not start a network listener."""
    try:
        return build_isolated_panel()
    except Exception as exc:  # noqa: BLE001 — classify as fixture block
        pytest.fail(f"BLOCKED: dashboard isolate load failed: {exc}")


# ---------------------------------------------------------------------------
# Independent verification (must exercise real routes / config / assets)
# ---------------------------------------------------------------------------


def test_independent_verification_registered_routes(isolated_panel, product_sha):
    """Confirm tests target actually registered Flask routes at the exact SHA."""
    rules = {str(rule) for rule in isolated_panel.app.url_map.iter_rules()}
    required = {
        "/api/autonomy",
        "/api/tasks/submit",
        "/api/learning/link-facebook",
        "/api/learning/link-twitter",
        "/",
    }
    missing = required - rules
    assert not missing, f"required routes missing from registered map: {missing}"
    assert product_sha == TARGET_SHA


def test_independent_verification_socketio_config_object(isolated_panel):
    """Confirm Socket.IO server object is the live panel configuration."""
    assert hasattr(isolated_panel, "socketio")
    server = getattr(isolated_panel.socketio, "server", None)
    assert server is not None, "Socket.IO server not initialized on panel"
    eio = getattr(server, "eio", None)
    assert eio is not None
    # Read actual runtime cors setting (not a mock of the auth decision).
    assert hasattr(eio, "cors_allowed_origins")


def test_independent_verification_rendered_assets_endpoint(isolated_panel):
    client = isolated_panel.app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Elysia Control Panel" in html
    assert "<script" in html.lower()


# ---------------------------------------------------------------------------
# A. Unauthorized autonomy configuration
# ---------------------------------------------------------------------------


def test_A_unauthorized_autonomy_configuration_denied(isolated_panel, product_sha):
    """Unauthenticated POST /api/autonomy must be 401/403 with zero persistence."""
    autonomy_path = Path(__file__).resolve().parents[1] / "config" / "autonomy.json"
    before = autonomy_path.read_bytes() if autonomy_path.exists() else b""
    before_hash = hashlib.sha256(before).hexdigest()

    worker_started = {"count": 0}

    class GuardedOrchestrator:
        def _load_autonomy_config(self):
            return {"enabled": False, "allowed_actions": [], "max_actions_per_hour": 0}

        def run_autonomous_cycle(self):
            worker_started["count"] += 1
            raise AssertionError("autonomy cycle must not start")

    # Rebuild panel with guarded orchestrator (still no auth).
    from tests.dashboard_panel_loader import UIControlPanel

    panel = UIControlPanel(orchestrator=GuardedOrchestrator(), host="127.0.0.1", port=5999)
    client = panel.app.test_client()

    with IsolationGuard() as recorder:
        response = client.post("/api/autonomy", json={"enabled": True})
        status = response.status_code
        body = response.get_data(as_text=True)

    after = autonomy_path.read_bytes() if autonomy_path.exists() else b""
    after_hash = hashlib.sha256(after).hexdigest()

    # Evidence fields (visible in assertion messages on failure).
    evidence = {
        "test": "test_A_unauthorized_autonomy_configuration_denied",
        "source_sha": product_sha,
        "route": "POST /api/autonomy",
        "expected": "HTTP 401|403; persistence_count==0; autonomy remains disabled; no worker",
        "actual_status": status,
        "intercepted_side_effect_count": recorder.persistence_count,
        "worker_starts": worker_started["count"],
        "config_hash_unchanged": before_hash == after_hash,
        "failure_class": "security-relevant",
    }

    try:
        assert_denied(status)
        assert recorder.persistence_count == 0, evidence
        assert before_hash == after_hash, f"autonomy.json mutated: {evidence}"
        assert worker_started["count"] == 0, evidence
        assert "enabled\": true" not in body.lower().replace(" ", "")
    except AssertionError as err:
        raise AssertionError(f"SECURITY DEFECT A: {err}; evidence={evidence}") from err


# ---------------------------------------------------------------------------
# B. Unauthorized task submission
# ---------------------------------------------------------------------------


def test_B_unauthorized_task_submission_denied(require_exact_sha, product_sha):
    """Unauthenticated POST /api/tasks/submit must not reach the registry."""
    registry = RecordingFakeRegistry()
    execution_hits = {"count": 0}
    registry.execution_callbacks.append(lambda task: execution_hits.__setitem__("count", execution_hits["count"] + 1))

    panel = build_isolated_panel(registry=registry)
    client = panel.app.test_client()

    with IsolationGuard() as recorder:
        response = client.post(
            "/api/tasks/submit",
            json={
                "type": "bounded_browse",
                "payload": {"goal": "fictional synthetic task — do not execute"},
                "priority": 1,
            },
        )
        status = response.status_code

    evidence = {
        "test": "test_B_unauthorized_task_submission_denied",
        "source_sha": product_sha,
        "route": "POST /api/tasks/submit",
        "expected": "HTTP 401|403; registry submissions==0; queue empty; no execution callback",
        "actual_status": status,
        "registry_submissions": registry.submission_count,
        "route_task_calls": registry.route_task_calls,
        "queue_len": len(registry.queue),
        "execution_callback_count": execution_hits["count"],
        "intercepted_side_effect_count": recorder.persistence_count,
        "failure_class": "security-relevant",
    }

    try:
        assert_denied(status)
        assert registry.submission_count == 0, evidence
        assert registry.route_task_calls == 0, evidence
        assert len(registry.queue) == 0, evidence
        assert execution_hits["count"] == 0, evidence
    except AssertionError as err:
        raise AssertionError(f"SECURITY DEFECT B: {err}; evidence={evidence}") from err


# ---------------------------------------------------------------------------
# C. Credential persistence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route,payload", CREDENTIAL_ROUTES, ids=[r[0] for r in CREDENTIAL_ROUTES])
def test_C_unauthorized_credential_persistence_denied(route, payload, require_exact_sha, product_sha, monkeypatch):
    """Unauthenticated credential POSTs must be denied; no file/env secret writes."""
    install_fake_auto_learning(monkeypatch)
    panel = build_isolated_panel()
    client = panel.app.test_client()

    env_before = dict(os.environ)

    with IsolationGuard() as recorder:
        response = client.post(route, json=payload)
        status = response.status_code
        body = response.get_data(as_text=True)

    env_after = dict(os.environ)

    evidence = {
        "test": "test_C_unauthorized_credential_persistence_denied",
        "source_sha": product_sha,
        "route": f"POST {route}",
        "expected": "HTTP 401|403; zero credential/config writes; token absent from body; env unchanged",
        "actual_status": status,
        "intercepted_side_effect_count": recorder.persistence_count,
        "env_mutations": recorder.env_mutations,
        "token_in_response": SYNTHETIC_TOKEN in body,
        "env_unchanged": env_before == env_after,
        "failure_class": "security-relevant",
    }

    try:
        assert_denied(status)
        assert recorder.persistence_count == 0, evidence
        assert recorder.env_mutations == [], evidence
        assert SYNTHETIC_TOKEN not in body, evidence
        assert env_before == env_after, evidence
    except AssertionError as err:
        raise AssertionError(f"SECURITY DEFECT C: {err}; evidence={evidence}") from err


# ---------------------------------------------------------------------------
# D. Socket.IO origin restrictions
# ---------------------------------------------------------------------------


def _cors_is_restricted(cors) -> bool:
    if cors is None or cors == "*":
        return False
    if isinstance(cors, str):
        return cors != "*" and bool(cors.strip())
    if isinstance(cors, (list, tuple, set)):
        return len(cors) > 0 and "*" not in cors
    return False


def test_D_socketio_rejects_untrusted_origin(isolated_panel, product_sha):
    """Untrusted Origin must not connect; wildcard CORS must not be accepted."""
    server = isolated_panel.socketio.server
    eio_cors = getattr(server.eio, "cors_allowed_origins", None)

    # Use in-process Socket.IO test client — no real network port.
    client = None
    connected = None
    connect_error = None
    privileged_events = []
    try:
        client = isolated_panel.socketio.test_client(
            isolated_panel.app,
            headers={"Origin": UNTRUSTED_ORIGIN, "Referer": UNTRUSTED_ORIGIN + "/"},
        )
        connected = client.is_connected()
        if connected:
            # Real connect handler emits status_update — privileged path executed.
            privileged_events = client.get_received()
    except Exception as exc:  # noqa: BLE001
        connect_error = str(exc)
        connected = False
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # Also inspect source construction for unrestricted origins.
    from tests import dashboard_panel_loader as loader

    source = Path(inspect.getfile(loader.UIControlPanel)).read_text(encoding="utf-8")
    wildcard_in_source = bool(
        re.search(r"cors_allowed_origins\s*=\s*[\"']\*[\"']", source)
        or re.search(r"cors_allowed_origins\s*=\s*\*", source)
    )

    evidence = {
        "test": "test_D_socketio_rejects_untrusted_origin",
        "source_sha": product_sha,
        "route": f"Socket.IO connect Origin={UNTRUSTED_ORIGIN}",
        "expected": "connection refused; no privileged handler; no wildcard CORS",
        "actual_connected": connected,
        "connect_error": connect_error,
        "eio_cors_allowed_origins": eio_cors,
        "wildcard_in_source": wildcard_in_source,
        "privileged_events": privileged_events,
        "intercepted_side_effect_count": 0,
        "failure_class": "security-relevant",
    }

    try:
        assert connected is False, evidence
        assert _cors_is_restricted(eio_cors), evidence
        assert wildcard_in_source is False, evidence
        assert privileged_events == [], evidence
    except AssertionError as err:
        raise AssertionError(f"SECURITY DEFECT D: {err}; evidence={evidence}") from err


# ---------------------------------------------------------------------------
# E. Offline JavaScript assets
# ---------------------------------------------------------------------------


def test_E_offline_javascript_assets_are_local(isolated_panel, product_sha):
    """Rendered dashboard must not depend on CDN/external script URLs."""
    client = isolated_panel.app.test_client()
    response = client.get("/")
    assert response.status_code == 200, (
        f"BLOCKED: dashboard did not render (status={response.status_code})"
    )
    html = response.get_data(as_text=True)

    script_srcs = extract_script_sources(html)
    remote_scripts = [src for src in script_srcs if is_remote_url(src)]
    remote_imports = extract_remote_dynamic_imports(html)

    # Local asset resolution: any non-remote src must be inline-path or app-local.
    local_srcs = [src for src in script_srcs if not is_remote_url(src)]
    for src in local_srcs:
        # Relative/local paths are acceptable; absolute file URLs are not remote CDN.
        assert not src.lower().startswith("file:"), f"unexpected file URL script: {src}"

    evidence = {
        "test": "test_E_offline_javascript_assets_are_local",
        "source_sha": product_sha,
        "route": "GET / (rendered HTML + script srcs)",
        "expected": "no external script URLs; no CDN; no remote dynamic imports; renderable offline",
        "actual_status": response.status_code,
        "script_srcs": script_srcs,
        "remote_scripts": remote_scripts,
        "remote_dynamic_imports": remote_imports,
        "intercepted_side_effect_count": 0,
        "failure_class": "security-relevant",
    }

    try:
        assert remote_scripts == [], evidence
        assert remote_imports == [], evidence
        # Dashboard remains renderable without external networking (already served via test client).
        assert "Elysia" in html or "Control Panel" in html, evidence
    except AssertionError as err:
        raise AssertionError(f"SECURITY DEFECT E: {err}; evidence={evidence}") from err
