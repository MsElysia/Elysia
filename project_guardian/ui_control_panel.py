# project_guardian/ui_control_panel.py
# UI Control Panel - Web-based Operator Interface
# Provides monitoring, control, and visibility into Elysia system

try:
    from flask import Flask, render_template_string, jsonify, request
    from flask_socketio import SocketIO, emit
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    # Dummy classes for when Flask not available
    class Flask:
        pass
    class SocketIO:
        pass
    def emit(*args, **kwargs):
        pass

import threading
import json
import logging
import socket
import time
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from project_guardian.safe_stack import responses as _safe_stack_responses
from project_guardian.safe_stack.operator_chat import (
    OperatorChatRequest,
    OperatorChatResponderError,
    OperatorChatResponderResult,
    run_operator_chat_turn,
)
from .conversation_store import (
    DEFAULT_CONVERSATIONS_DIR,
    ConversationStore,
    build_recent_transcript,
    redact_chat_text,
    sanitize_conversation_id,
)

logger = logging.getLogger(__name__)

# Module-level guard for dashboard start (idempotent across all instances)
_dashboard_started = False
_dashboard_start_lock = threading.Lock()
_dashboard_start_attempts = 0

# Bounded limits for UI/runtime memory access (avoid full-dump latency spikes)
UI_MEMORY_RECENT_LIMIT = 200
PROJECT_ROOT_PATH = Path(__file__).resolve().parent.parent
BROWSER_AGENT_STATE_PATH = PROJECT_ROOT_PATH / "browser_agent_state.json"
OPENCLAW_ACTIVITY_PATH = PROJECT_ROOT_PATH / "data" / "runtime" / "openclaw_activity.json"
CURRENT_BACKEND_LOG_PATH = PROJECT_ROOT_PATH / "elysia_unified.log"
SECONDARY_RUNTIME_LOG_PATH = PROJECT_ROOT_PATH / "logs" / "elysia_runtime.log"
LEGACY_AUTONOMOUS_LOG_PATH = (
    PROJECT_ROOT_PATH / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
)
EXTERNAL_ACTIVITY_RECENT_WINDOW_SEC = 15 * 60
LIVE_LOG_STALE_AFTER_SEC = 6 * 60 * 60
LEGACY_LOG_STALE_AFTER_SEC = 24 * 60 * 60
# Legacy import-only path (not written at runtime; see ConversationStore.import_legacy_control_panel_json).
CONTROL_PANEL_CHAT_HISTORY_PATH = PROJECT_ROOT_PATH / "data" / "runtime" / "control_panel_chat_history.json"
CONTROL_PANEL_CHAT_MAX_MESSAGES = 60
CONTROL_PANEL_CHAT_PROMPT_MESSAGES = 10
CONTROL_PANEL_CHAT_PROMPT_CHAR_LIMIT = 6000
CONTROL_PANEL_CHAT_RESPONSE_MESSAGES = 20

_redact_control_panel_chat_text = redact_chat_text
_control_panel_chat_session_id = sanitize_conversation_id

try:
    OPENCLAW_GATEWAY_PORT = int((os.environ.get("OPENCLAW_GATEWAY_PORT") or "18789").strip())
except ValueError:
    OPENCLAW_GATEWAY_PORT = 18789
OPENCLAW_GATEWAY_HOST = (os.environ.get("OPENCLAW_GATEWAY_HOST") or "127.0.0.1").strip() or "127.0.0.1"

_JSON_FILE_CACHE_LOCK = threading.Lock()
_JSON_FILE_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_cached_json(path: Path) -> Optional[Any]:
    """Read a JSON file with a tiny mtime/size cache to keep /api/status cheap."""
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        with _JSON_FILE_CACHE_LOCK:
            _JSON_FILE_CACHE.pop(key, None)
        return None
    sig = (stat.st_mtime_ns, stat.st_size)
    with _JSON_FILE_CACHE_LOCK:
        cached = _JSON_FILE_CACHE.get(key)
        if cached and cached.get("sig") == sig:
            return cached.get("data")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("External activity JSON load failed for %s: %s", path, e)
        return None
    with _JSON_FILE_CACHE_LOCK:
        _JSON_FILE_CACHE[key] = {"sig": sig, "data": payload}
    return payload


def _tail_text_file(path: Path, *, max_lines: int = 120, max_bytes: int = 512_000) -> List[str]:
    """Read the tail of a text file without loading huge legacy logs into memory."""
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
    lines = raw.decode("utf-8", errors="replace").splitlines()
    limit = max(1, min(500, int(max_lines)))
    return lines[-limit:]


def _file_status(path: Path, *, label: str, role: str, stale_after_sec: int) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "label": label,
        "role": role,
        "path": str(path),
        "exists": False,
        "size_bytes": 0,
        "mtime": None,
        "age_seconds": None,
        "stale": True,
    }
    try:
        stat = path.stat()
    except OSError:
        return info
    age = max(0.0, time.time() - stat.st_mtime)
    try:
        mtime = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
    except Exception:
        mtime = None
    info.update(
        {
            "exists": True,
            "size_bytes": stat.st_size,
            "mtime": mtime,
            "age_seconds": round(age, 1),
            "stale": age > stale_after_sec,
        }
    )
    return info


def _build_recent_log_payload(max_lines: int = 120) -> Dict[str, Any]:
    """
    Control-panel log view.

    Prefer the current rotating backend log. The old autonomous-system log is a
    historical trial-run file and is included only as metadata/fallback so stale
    STATUS UPDATE blocks are not mistaken for live server output.
    """
    limit = max(10, min(500, int(max_lines)))
    sources = [
        (
            CURRENT_BACKEND_LOG_PATH,
            "Current backend log",
            "live_backend",
            LIVE_LOG_STALE_AFTER_SEC,
        ),
        (
            SECONDARY_RUNTIME_LOG_PATH,
            "Runtime package log",
            "runtime_package",
            LIVE_LOG_STALE_AFTER_SEC,
        ),
    ]
    source_statuses = [
        _file_status(path, label=label, role=role, stale_after_sec=stale_after)
        for path, label, role, stale_after in sources
    ]
    legacy_status = _file_status(
        LEGACY_AUTONOMOUS_LOG_PATH,
        label="Legacy trial/autonomous log",
        role="legacy_trial_history",
        stale_after_sec=LEGACY_LOG_STALE_AFTER_SEC,
    )

    selected_status = next((status for status in source_statuses if status["exists"]), None)
    if selected_status is None and legacy_status["exists"]:
        selected_status = legacy_status

    if selected_status is None:
        return {
            "success": False,
            "message": "No Elysia log files were found.",
            "source": None,
            "sources": source_statuses,
            "legacy_source": legacy_status,
            "lines": [],
        }

    lines = _tail_text_file(Path(str(selected_status["path"])), max_lines=limit)
    message = ""
    if selected_status.get("role") == "legacy_trial_history":
        message = "Showing legacy trial history only because no current backend log exists."
    elif selected_status.get("stale"):
        message = "Current backend log exists but has not been updated recently; backend may be stopped."

    return {
        "success": True,
        "message": message,
        "source": selected_status,
        "sources": source_statuses,
        "legacy_source": legacy_status,
        "lines": lines,
    }


def _stripe_secret_key_mode() -> str:
    """Classify Stripe secret from env prefix only (never return key material)."""
    k = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not k:
        return "unset"
    if k.startswith("sk_live"):
        return "live"
    if k.startswith("sk_test"):
        return "test"
    return "custom"


def _stripe_publishable_key_mode() -> str:
    k = (os.environ.get("STRIPE_PUBLISHABLE_KEY") or "").strip()
    if not k:
        return "unset"
    if k.startswith("pk_live"):
        return "live"
    if k.startswith("pk_test"):
        return "test"
    return "custom"


def _build_payment_provider_status(unified: Any) -> Dict[str, Any]:
    """
    Gumroad + Stripe operator snapshot: env presence, key mode (test/live), HarvestEngine binding.
    Does not call external APIs and does not expose secrets.
    """
    gum_token = bool((os.environ.get("GUMROAD_ACCESS_TOKEN") or "").strip())
    stripe_secret = bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip())
    stripe_pub = bool((os.environ.get("STRIPE_PUBLISHABLE_KEY") or "").strip())
    harvest_gum = False
    harvest_stripe = False
    if unified is not None:
        modules = getattr(unified, "modules", None) or {}
        he = modules.get("harvest_engine")
        if he is not None:
            harvest_gum = getattr(he, "gumroad_client", None) is not None
            harvest_stripe = getattr(he, "stripe_client", None) is not None

    def _row(env_ok: bool, harvest_ok: bool) -> str:
        if env_ok and harvest_ok:
            return "ok"
        if env_ok and not harvest_ok:
            return "env_only_restart_may_be_needed"
        return "not_configured"

    return {
        "gumroad": {
            "access_token_env": gum_token,
            "harvest_client_bound": harvest_gum,
            "summary": _row(gum_token, harvest_gum),
        },
        "stripe": {
            "secret_key_env": stripe_secret,
            "publishable_key_env": stripe_pub,
            "secret_key_mode": _stripe_secret_key_mode(),
            "publishable_key_mode": _stripe_publishable_key_mode(),
            "harvest_client_bound": harvest_stripe,
            "summary": _row(stripe_secret, harvest_stripe),
        },
    }


def _normalize_preview_text(value: Any, limit: int = 320) -> Optional[str]:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_from_epoch(value: Any) -> Optional[str]:
    ts = _coerce_float(value)
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except Exception:
        return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _seconds_since(ts: Optional[datetime]) -> Optional[float]:
    if ts is None:
        return None
    now = datetime.now().astimezone()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=now.tzinfo)
    try:
        return max(0.0, (now - ts).total_seconds())
    except Exception:
        return None


def _is_tcp_endpoint_reachable(host: str, port: int, timeout: float = 0.15) -> bool:
    if not host or not isinstance(port, int) or port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _build_moltbook_activity_snapshot() -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "available": False,
        "status": "never",
        "last_seen_at": None,
        "goal": None,
        "summary": None,
        "summary_source": None,
        "readout_quality": "none",
        "stop_reason": None,
        "pages_visited": 0,
        "step_count": 0,
        "latest_url": None,
        "latest_snippet": None,
    }
    payload = _load_cached_json(BROWSER_AGENT_STATE_PATH)
    if not isinstance(payload, dict):
        return snapshot

    sessions = payload.get("sessions") or []
    findings = payload.get("findings_log") or []
    latest_session = sessions[-1] if sessions and isinstance(sessions[-1], dict) else {}
    latest_finding = findings[-1] if findings and isinstance(findings[-1], dict) else {}
    steps = latest_session.get("steps") or []
    urls = [
        str(step.get("url") or "").strip()
        for step in steps
        if isinstance(step, dict) and str(step.get("url") or "").strip()
    ]

    last_seen_at = _iso_from_epoch(latest_session.get("ts")) or _iso_from_epoch(latest_finding.get("ts"))
    session_summary = _normalize_preview_text(latest_session.get("summary"), 420)
    finding_summary = _normalize_preview_text(latest_finding.get("snippet"), 320)
    summary_text = session_summary or finding_summary
    summary_source = (
        "session_summary"
        if session_summary
        else "latest_finding"
        if finding_summary
        else None
    )
    summary_word_count = len(str(summary_text or "").split())
    readout_quality = "none"
    if summary_text:
        if len(set(urls)) >= 3 and summary_word_count >= 20:
            readout_quality = "detailed"
        elif summary_word_count >= 8:
            readout_quality = "clear"
        else:
            readout_quality = "thin"

    snapshot.update(
        {
            "available": bool(latest_session or latest_finding),
            "last_seen_at": last_seen_at,
            "goal": _normalize_preview_text(latest_session.get("goal"), 220),
            "summary": summary_text,
            "summary_source": summary_source,
            "readout_quality": readout_quality,
            "stop_reason": _normalize_preview_text(latest_session.get("stop_reason"), 80),
            "pages_visited": len(set(urls)),
            "step_count": len(steps) if isinstance(steps, list) else 0,
            "latest_url": urls[-1] if urls else None,
            "latest_snippet": _normalize_preview_text(latest_finding.get("snippet"), 240),
        }
    )

    age_seconds = _seconds_since(_parse_iso_datetime(last_seen_at))
    if snapshot["available"] and age_seconds is not None and age_seconds <= EXTERNAL_ACTIVITY_RECENT_WINDOW_SEC:
        snapshot["status"] = "active_recently"
    elif snapshot["available"]:
        snapshot["status"] = "idle"
    return snapshot


def _build_openclaw_activity_snapshot() -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "available": False,
        "status": "unseen",
        "gateway_host": OPENCLAW_GATEWAY_HOST,
        "gateway_port": OPENCLAW_GATEWAY_PORT,
        "gateway_reachable": _is_tcp_endpoint_reachable(OPENCLAW_GATEWAY_HOST, OPENCLAW_GATEWAY_PORT),
        "updated_at": None,
        "request_count": 0,
        "last_model": None,
        "last_status": None,
        "last_request_preview": None,
        "last_reply_preview": None,
        "last_error": None,
        "recent_requests": [],
    }
    payload = _load_cached_json(OPENCLAW_ACTIVITY_PATH)
    if isinstance(payload, dict):
        recent_requests: List[Dict[str, Any]] = []
        for item in list(payload.get("recent_requests") or [])[:3]:
            if not isinstance(item, dict):
                continue
            recent_requests.append(
                {
                    "ts": item.get("ts"),
                    "status": _normalize_preview_text(item.get("status"), 40),
                    "model": _normalize_preview_text(item.get("model"), 80),
                    "message_preview": _normalize_preview_text(item.get("message_preview"), 200),
                    "reply_preview": _normalize_preview_text(item.get("reply_preview"), 220),
                    "error": _normalize_preview_text(item.get("error"), 180),
                }
            )
        snapshot.update(
            {
                "available": True,
                "updated_at": payload.get("updated_at") or payload.get("last_request_at"),
                "request_count": int(payload.get("request_count") or 0),
                "last_model": _normalize_preview_text(payload.get("last_model"), 80),
                "last_status": _normalize_preview_text(payload.get("last_status"), 40),
                "last_request_preview": _normalize_preview_text(
                    payload.get("last_request_preview") or payload.get("last_request_message"),
                    220,
                ),
                "last_reply_preview": _normalize_preview_text(payload.get("last_reply_preview"), 240),
                "last_error": _normalize_preview_text(payload.get("last_error"), 180),
                "recent_requests": recent_requests,
            }
        )

    age_seconds = _seconds_since(_parse_iso_datetime(snapshot.get("updated_at")))
    if snapshot["available"] and age_seconds is not None and age_seconds <= EXTERNAL_ACTIVITY_RECENT_WINDOW_SEC:
        snapshot["status"] = "active_recently"
    elif snapshot["gateway_reachable"]:
        snapshot["status"] = "gateway_ready"
    elif snapshot["available"]:
        snapshot["status"] = "idle"
    return snapshot


def _build_external_activity_snapshot(orchestrator: Any = None) -> Dict[str, Any]:
    """MoltBook + OpenClaw file snapshots; optional USB/external data snapshot from UnifiedElysiaSystem."""
    storage_snapshot: Dict[str, Any] = {}
    if orchestrator is not None:
        try:
            unified = getattr(orchestrator, "_unified_system", None)
            ev = getattr(unified, "_external_volume_snapshot", None) if unified is not None else None
            if isinstance(ev, dict):
                storage_snapshot = dict(ev)
        except Exception as e:
            logger.debug("external storage snapshot for UI: %s", e)
    return {
        "moltbook": _build_moltbook_activity_snapshot(),
        "openclaw": _build_openclaw_activity_snapshot(),
        "storage": storage_snapshot,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


# HTML Template for Control Panel - Enhanced Version
CONTROL_PANEL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Elysia Control Panel</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" crossorigin="anonymous"></script>
    <style>
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --bg-hover: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --border: #334155;
            --shadow: rgba(0, 0, 0, 0.3);
        }
        
        [data-theme="light"] {
            --bg-dark: #f8fafc;
            --bg-card: #ffffff;
            --bg-hover: #f1f5f9;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border: #e2e8f0;
            --shadow: rgba(0, 0, 0, 0.1);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, var(--bg-dark) 0%, #1e293b 100%);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
            transition: background 0.3s ease;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            padding: 24px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px var(--shadow);
            animation: slideDown 0.5s ease;
        }
        
        @keyframes slideDown {
            from { transform: translateY(-20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        h1 {
            color: white;
            font-size: 28px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .header-controls {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .theme-toggle {
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.05);
        }
        
        .status-indicator {
            display: inline-block;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .status-running { background: var(--success); box-shadow: 0 0 10px var(--success); }
        .status-paused { background: var(--warning); box-shadow: 0 0 10px var(--warning); }
        .status-stopped { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
        .status-connected { background: var(--primary); box-shadow: 0 0 10px var(--primary); }
        .status-initialized { background: var(--secondary); box-shadow: 0 0 10px var(--secondary); }
        
        .status-text {
            color: white;
            font-weight: 600;
            font-size: 16px;
        }
        
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            background: var(--bg-card);
            padding: 8px;
            border-radius: 12px;
            box-shadow: 0 4px 12px var(--shadow);
        }
        
        .tab {
            padding: 12px 24px;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            position: relative;
            pointer-events: auto;
            user-select: none;
            -webkit-user-select: none;
            z-index: 10;
        }
        
        .tab:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }
        
        .tab.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .tab-content.active {
            display: block;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }
        
        .card {
            background: var(--bg-card);
            padding: 24px;
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px var(--shadow);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
        }
        
        .card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px var(--shadow);
        }
        
        .card h2 {
            color: var(--text-primary);
            margin-bottom: 20px;
            font-size: 20px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 12px 0;
            padding: 12px;
            background: var(--bg-dark);
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        
        .metric:hover {
            background: var(--bg-hover);
            transform: translateX(4px);
        }
        
        .metric-label {
            font-weight: 500;
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .metric-value {
            color: var(--success);
            font-weight: 700;
            font-size: 16px;
        }
        
        .metric-value.warning { color: var(--warning); }
        .metric-value.danger { color: var(--danger); }
        
        button {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            margin: 6px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            pointer-events: auto;
            user-select: none;
            -webkit-user-select: none;
            position: relative;
            z-index: 1;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button.danger {
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        
        button.secondary {
            background: var(--bg-hover);
            box-shadow: none;
        }
        
        button.secondary:hover {
            background: var(--border);
        }
        
        .controls {
            background: var(--bg-card);
            padding: 24px;
            border-radius: 16px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px var(--shadow);
        }
        
        .console {
            background: #000;
            color: #0f0;
            padding: 20px;
            border-radius: 12px;
            font-family: 'Courier New', 'Fira Code', monospace;
            font-size: 13px;
            height: 450px;
            overflow-y: auto;
            margin-top: 20px;
            border: 1px solid var(--border);
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        
        .log-entry {
            margin: 6px 0;
            padding: 8px;
            border-left: 3px solid #0f0;
            padding-left: 12px;
            line-height: 1.6;
        }
        
        .log-error { border-left-color: var(--danger); color: #ff6b6b; }
        .log-warning { border-left-color: var(--warning); color: #ffd93d; }
        .log-info { border-left-color: #3b82f6; color: #60a5fa; }
        
        .input-group {
            margin: 16px 0;
        }
        
        .input-group label {
            display: block;
            margin-bottom: 8px;
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 14px;
        }
        
        input, textarea, select {
            width: 100%;
            padding: 12px;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            color: var(--text-primary);
            border-radius: 8px;
            margin-top: 6px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        textarea {
            min-height: 120px;
            font-family: 'Courier New', monospace;
            resize: vertical;
        }
        
        .section {
            margin-bottom: 32px;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            background: var(--bg-hover);
            color: var(--text-primary);
        }
        
        .badge.success { background: var(--success); color: white; }
        .badge.warning { background: var(--warning); color: white; }
        .badge.danger { background: var(--danger); color: white; }
        
        .api-meter-stat-card h3 { margin-bottom: 8px; }
        .api-meter-g-track {
            height: 14px;
            border-radius: 8px;
            background: var(--bg-dark);
            overflow: hidden;
            margin-top: 10px;
            border: 1px solid var(--border);
        }
        .api-meter-g-fill {
            height: 100%;
            border-radius: 8px;
            transition: width 0.4s ease;
        }
        .api-meter-g-label {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .api-meter-g-msg {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 10px;
            line-height: 1.45;
            word-break: break-word;
        }
        .api-meter-chart-note {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 10px;
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            
            header {
                flex-direction: column;
                gap: 16px;
                text-align: center;
            }
            
            .tabs {
                overflow-x: auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Elysia Control Panel</h1>
            <div class="header-controls">
                <button class="theme-toggle" onclick="toggleTheme()">🌓 Toggle Theme</button>
                <div>
                    <span class="status-indicator" id="status-indicator"></span>
                    <span class="status-text" id="status-text">Initializing...</span>
                    <span id="loading-spinner" style="margin-left: 10px; display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 1s linear infinite;"></span>
                </div>
            </div>
        </header>

        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard', this)">📊 Dashboard</button>
            <button class="tab" onclick="showTab('learning', this)">📚 Learning</button>
            <button class="tab" onclick="showTab('tasks', this)">📋 Tasks</button>
            <button class="tab" onclick="showTab('workbench', this)">Workbench</button>
            <button class="tab" onclick="showTab('security', this)">🔒 Security</button>
            <button class="tab" onclick="showTab('memory', this)">🧠 Memory</button>
            <button class="tab" onclick="showTab('introspection', this)">🔍 Introspection</button>
            <button class="tab" onclick="showTab('control', this)">🎮 Control</button>
            <button class="tab" onclick="showTab('insights', this)">📡 Insights</button>
            <button class="tab" onclick="showTab('api-meter', this)">⛽ API meter</button>
            <button class="tab" onclick="showTab('logs', this)">📝 Logs</button>
        </div>

        <!-- Dashboard Tab -->
        <div id="dashboard" class="tab-content active">
            <div class="grid">
                <div id="system-safety-status-card" class="card" style="grid-column: 1 / -1;">
                    <h2>System Safety Status</h2>
                    <p style="font-size: 12px; color: var(--text-secondary); margin: 0 0 10px 0; line-height: 1.5;">
                        Plain-language summary for operators. Safe-stack panels below are read-only or review-only unless config says otherwise.
                    </p>
                    <ul style="font-size: 12px; color: var(--text-secondary); margin: 0; padding-left: 18px; line-height: 1.6;">
                        <li><strong>Autonomy:</strong> Off unless explicitly enabled</li>
                        <li><strong>Live execution:</strong> Off for safe-stack panels</li>
                        <li><strong>Brain traces:</strong> Dry-run and config-gated</li>
                        <li><strong>Memory ranking:</strong> Read-only</li>
                        <li><strong>Self-improvement:</strong> Review/export only</li>
                        <li><strong>Chat memory:</strong> Saved locally through ConversationStore</li>
                    </ul>
                </div>

                <div class="card" style="grid-column: 1 / -1;">
                    <h2>Start Here</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 16px; max-width: 920px; line-height: 1.6;">
                        Use Elysia like a result engine: ask a question, pull in fresh source material, or jump straight to the latest opportunities and artifacts.
                    </p>
                    <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px;">
                        <button onclick="quickFindOpportunities()">Find Opportunities</button>
                        <button onclick="quickLearnFrom('twitter')">Learn From X</button>
                        <button onclick="quickLearnFrom('chatgpt')">Learn From ChatGPT</button>
                        <button onclick="quickLearnFrom('web')">Learn From Web</button>
                        <button onclick="quickShowChanges()">Show What Changed</button>
                    </div>
                    <div class="input-group" style="margin-bottom: 10px;">
                        <label>Ask Elysia:</label>
                        <input type="text" id="dashboard-quick-ask" placeholder="e.g., What should I work on next to make this useful for real users?" onkeydown="if(event.key === 'Enter'){ quickAskElysia(); }">
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
                        <button onclick="quickAskElysia()">Get Answer</button>
                        <button onclick="quickAskElysia('What are the top operator-facing opportunities right now?')">Ask For Opportunities</button>
                        <button onclick="quickAskElysia('Summarize the most useful change since the last run.')">Ask What Changed</button>
                    </div>
                    <div id="dashboard-quick-answer" style="padding: 14px; background: var(--bg-dark); border-radius: 10px; min-height: 66px; white-space: pre-wrap; font-size: 13px;">
                        <em style="color: var(--text-secondary);">Ask a direct question and Elysia will answer here.</em>
                    </div>
                </div>

                <div class="card">
                    <h2>System Status</h2>
                    <div class="metric">
                        <span class="metric-label">Uptime:</span>
                        <span class="metric-value" id="uptime">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Event Loop:</span>
                        <span class="metric-value" id="loop-status">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Queue Size:</span>
                        <span class="metric-value" id="queue-size">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Active Tasks:</span>
                        <span class="metric-value" id="active-tasks">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>API gas meter</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin: 0 0 8px 0;">
                        Session usage (this process); resets on restart. Refreshes when you open Dashboard or click below.
                    </p>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;">
                        <button type="button" onclick="refreshDashboardApiMeter()">Refresh meter</button>
                    </div>
                    <div id="dashboard-api-meter-summary" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; font-size: 11px; font-family: monospace; color: var(--text-secondary); min-height: 120px; white-space: pre-wrap;">
                        <em style="color: var(--text-muted);">Loading…</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Autonomy</h2>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                        High-impact controls. These should stay off unless you intentionally enable them and understand the consequences.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin-bottom: 8px;">This may affect runtime behavior.</p>
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                            <input type="checkbox" id="autonomy-enabled" onchange="toggleAutonomy(this.checked)">
                            <span>Enabled</span>
                        </label>
                        <span id="autonomy-status" style="font-size: 12px; color: var(--text-secondary);">-</span>
                    </div>
                    <div id="autonomy-last" style="font-size: 11px; color: var(--text-secondary);">Last: -</div>
                </div>

                <div class="card">
                    <h2>Task / Next Action</h2>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                        Shows what Elysia thinks the next useful task or action is. Review before acting.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 8px 0;">Review before using.</p>
                    <div id="next-action-display" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 80px; font-size: 13px;">
                        <em>Click "Suggest Next Action" to load...</em>
                    </div>
                    <button onclick="suggestNextAction()" style="margin-top: 8px;">Suggest Next Action</button>
                    <button onclick="executeNextAction()" id="execute-next-btn" style="margin-top: 8px; display: none;" class="danger">Execute</button>
                </div>

                <div class="card">
                    <h2>Top Opportunity</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Latest operator-facing opportunity from Elysia's self-task output</p>
                    <div id="dashboard-opportunity" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 96px; font-size: 13px;">
                        <em>Loading workbench...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Recent Artifact</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Most recent useful output ready for operator review</p>
                    <div id="dashboard-artifact" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 96px; font-size: 13px;">
                        <em>Loading workbench...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Sales Launch</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Current offer, launch path, and the next transaction setup step</p>
                    <div id="dashboard-sales-launch" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 120px; font-size: 13px;">
                        <em>Loading workbench...</em>
                    </div>
                </div>

                <div class="card" style="grid-column: 1 / -1;">
                    <h2>External Activity</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 12px;">See what Elysia most recently observed on MoltBook (goal, readout, coverage), what OpenClaw is sending through the local chat bridge, and USB / external data mirror status from startup.</p>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px;">
                        <div style="padding: 14px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px;">
                                <strong>MoltBook</strong>
                                <span id="external-moltbook-badge" class="badge">Waiting</span>
                            </div>
                            <div id="external-moltbook-details" style="font-size: 13px; line-height: 1.55;">
                                <em style="color: var(--text-secondary);">Waiting for MoltBook activity...</em>
                            </div>
                        </div>
                        <div style="padding: 14px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px;">
                                <strong>OpenClaw</strong>
                                <span id="external-openclaw-badge" class="badge">Waiting</span>
                            </div>
                            <div id="external-openclaw-details" style="font-size: 13px; line-height: 1.55;">
                                <em style="color: var(--text-secondary);">Waiting for OpenClaw activity...</em>
                            </div>
                        </div>
                        <div style="padding: 14px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px;">
                                <strong>Storage &amp; USB</strong>
                                <span id="external-storage-badge" class="badge">Waiting</span>
                            </div>
                            <div id="external-storage-details" style="font-size: 13px; line-height: 1.55;">
                                <em style="color: var(--text-secondary);">Waiting for status...</em>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2>Memory System</h2>
                    <div class="metric">
                        <span class="metric-label">Total Memories:</span>
                        <span class="metric-value" id="total-memories">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Vector Enabled:</span>
                        <span class="metric-value" id="vector-enabled">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Snapshot:</span>
                        <span class="metric-value" id="last-snapshot">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Cleanup:</span>
                        <span class="metric-value" id="last-cleanup-outcome">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Cleanup Reason:</span>
                        <span class="metric-value" id="last-cleanup-reason">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Cleanup Target:</span>
                        <span class="metric-value" id="last-cleanup-target">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Security Status</h2>
                    <div class="metric">
                        <span class="metric-label">Recent Violations:</span>
                        <span class="metric-value" id="violations">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Pending Reviews:</span>
                        <span class="metric-value" id="pending-reviews">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Policy Loaded:</span>
                        <span class="metric-value" id="policy-loaded">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Trust System</h2>
                    <div class="metric">
                        <span class="metric-label">Average Trust:</span>
                        <span class="metric-value" id="avg-trust">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Components:</span>
                        <span class="metric-value" id="trust-components">-</span>
                    </div>
                </div>

                <div id="brain-visibility-panel" class="card" style="grid-column: 1 / -1;">
                    <!-- brain-visibility-review-only-start -->
                    <h2>Brain Trace &amp; Self-Improvement</h2>
                    <p style="font-size: 11px; color: var(--warning); margin: 0 0 8px 0; line-height: 1.45;">
                        Review-only summary. This does not apply code. Dry-run trace only; non-dry-run paths stay off.
                    </p>
                    <!-- brain-visibility-review-only-end -->
                    <h3 style="margin-top: 12px;">Brain Trace</h3>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                        Shows what Elysia considered during the latest dry-run reasoning trace. This does not mean Elysia executed anything.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Dry-run/config-gated. Review-only: does not apply code.</p>
                    <div id="brain-trace-summary" style="font-size: 12px; color: var(--text-secondary); min-height: 48px;">Loading…</div>
                    <button type="button" style="margin-top: 8px;" onclick="refreshBrainTrace()">Refresh brain trace</button>

                    <h3 style="margin-top: 16px;">Self-Improvement Proposals</h3>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                        Ideas Elysia found for improving itself. These are review-only. Nothing here changes code by itself.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Review-only: does not apply code.</p>
                    <div id="self-improvement-proposals-list" style="font-size: 12px; min-height: 40px;">Loading…</div>
                    <button type="button" style="margin-top: 8px;" onclick="refreshSelfImprovementProposals()">Refresh proposals</button>
                    <div id="self-improvement-proposal-detail" style="margin-top: 12px; display: none;">
                        <div id="self-improvement-proposal-detail-body"></div>
                        <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
                            <button type="button" onclick="updateSelfImprovementProposalStatus('reviewing')">Reviewing</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('accepted')">Accepted</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('rejected')">Rejected</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('deferred')">Deferred</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('implemented')">Implemented</button>
                        </div>
                        <!-- self-improvement-prompt-export-start -->
                        <h3 style="margin-top: 14px;">Proposal Export</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Creates a copyable prompt for Cursor or Codex. Exporting does not apply changes.
                        </p>
                        <p style="font-size: 11px; color: var(--warning); margin: 10px 0 6px 0;">
                            Export only. This does not apply code or run commands.
                        </p>
                        <div id="self-improvement-proposal-prompt-export" class="self-improvement-prompt-export">
                            <button type="button" onclick="exportSelfImprovementProposalPrompt('cursor')">Export Cursor Prompt</button>
                            <button type="button" onclick="exportSelfImprovementProposalPrompt('codex')">Export Codex Prompt</button>
                            <button type="button" onclick="copySelfImprovementExportedPrompt()">Copy exported prompt</button>
                            <pre id="self-improvement-prompt-export-text" style="margin-top: 8px; max-height: 160px; overflow: auto; font-size: 11px;"></pre>
                        </div>
                        <!-- self-improvement-prompt-export-end -->
                    </div>

                    <div id="memory-ranking-panel" style="margin-top: 18px;">
                        <h3>Memory Ranking</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Shows which recent memories look important, low-value, or worth reviewing. This is advisory only and does not edit memory.
                        </p>
                        <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Read-only advisory ranking. No memory changes are applied.</p>
                        <div id="memory-ranking-summary" style="font-size: 12px; min-height: 40px;">Loading…</div>
                        <button type="button" style="margin-top: 8px;" onclick="refreshMemoryRankingSummary()">Refresh memory ranking</button>
                    </div>

                    <div id="prompt-contract-panel" style="margin-top: 18px;">
                        <!-- prompt-contract-visibility-start -->
                        <h3>Prompt Contracts</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Checks whether module outputs follow the expected JSON format. Defaults are off unless enabled in config.
                        </p>
                        <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Read-only validation status. No model calls from this panel. production chat is not blocked by default.</p>
                        <div id="prompt-contract-status" style="font-size: 12px; min-height: 40px;">Loading…</div>
                        <button type="button" style="margin-top: 8px;" onclick="refreshPromptContractStatus()">Refresh prompt contract status</button>
                        <!-- prompt-contract-visibility-end -->
                    </div>
                </div>
            </div>
        </div>

        <!-- Learning Tab -->
        <div id="learning" class="tab-content">
            <div class="section">
                <div class="controls">
                    <h2>📚 Learning</h2>
                    <p class="ui-clarity-helper" style="color: var(--text-secondary); margin-bottom: 12px; line-height: 1.45;">
                        Learning pulls information from external sources (Reddit, web pages, RSS). Test buttons preview a small sample; starting learning may use the network.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 16px 0;">Review before using. This may fetch external content.</p>
                    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                        <button onclick="testRedditLearning()">Test Reddit Learning</button>
                        <button onclick="getLearningSummary()">Learning Summary</button>
                        <button onclick="refreshLearningStats()">Refresh Stats</button>
                    </div>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>Learning Statistics</h2>
                    <div class="metric">
                        <span class="metric-label">Total Articles:</span>
                        <span class="metric-value" id="learning-articles">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Reddit Posts:</span>
                        <span class="metric-value" id="learning-reddit">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">RSS Entries:</span>
                        <span class="metric-value" id="learning-rss">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Learning:</span>
                        <span class="metric-value" id="learning-last">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Quick Learning Test</h2>
                    <div class="input-group">
                        <label>Platform:</label>
                        <select id="learning-platform">
                            <option value="reddit">Reddit</option>
                            <option value="rss">RSS Feeds</option>
                            <option value="facebook">Facebook Page(s)</option>
                            <option value="twitter">X (Twitter) Search</option>
                            <option value="chatgpt">ChatGPT Conversations</option>
                            <option value="web">Web URL(s)</option>
                            <option value="all">All Sources</option>
                            <option value="mistral_chain">Mistral chain (X + Reddit + Wikipedia + ChatGPT context)</option>
                        </select>
                    </div>
                    <div class="input-group">
                        <label>Query/Topic/URL:</label>
                        <input type="text" id="learning-query" placeholder="e.g., AI, MachineLearning, Meta (FB page), or https://example.com/article">
                    </div>
                    <div class="input-group">
                        <label>Max Items:</label>
                        <input type="number" id="learning-max" value="5" min="1" max="20">
                    </div>
                    <div class="input-group" style="align-items: center;">
                        <label style="margin-right: 8px;">Use headless browser for web URLs:</label>
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                            <input type="checkbox" id="learning-headless" onchange="saveLearningHeadless(this.checked)">
                            <span>Yes (Playwright – for JS-heavy or bot-blocking sites)</span>
                        </label>
                    </div>
                    <button onclick="startLearning()">Start Learning</button>
                    <div id="learning-results" style="margin-top: 16px; padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 60px;">
                        <em style="color: var(--text-secondary);">Click "Start Learning" to begin...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Link your account</h2>
                    <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Connect accounts so Elysia can learn from your linked sources.</p>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>Facebook:</label>
                        <span id="link-fb-status" style="font-size: 13px; color: var(--text-secondary);">Checking...</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <input type="password" id="link-fb-token" placeholder="Paste your Facebook access token" style="flex: 1; min-width: 200px;" autocomplete="off">
                        <button onclick="saveLinkFacebook()">Save / Link</button>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Get a token: <a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noopener">Graph API Explorer</a> or Facebook for Developers → Tools → Access Token Tool.</p>
                    <hr style="margin: 16px 0; border-color: var(--border);">
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>X (Twitter):</label>
                        <span id="link-twitter-status" style="font-size: 13px; color: var(--text-secondary);">Checking...</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <input type="password" id="link-twitter-token" placeholder="Paste your X Bearer Token" style="flex: 1; min-width: 200px;" autocomplete="off">
                        <button onclick="saveLinkTwitter()">Save / Link</button>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Get a token: <a href="https://developer.x.com/en/portal/dashboard" target="_blank" rel="noopener">X Developer Portal</a> → your App → Keys and tokens → Bearer Token. Used for recent search (public tweets).</p>
                </div>

                <div class="card">
                    <h2>Income APIs (Gumroad &amp; Stripe)</h2>
                    <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">
                        Saves to <code style="font-size: 11px;">config/api_keys.json</code> (same as other API keys). Environment variables still override the file.
                        <strong>Harvest Engine reloads in this process</strong> when you save or clear keys here. Use a full Elysia restart only if another subsystem still shows stale state.
                    </p>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>Gumroad:</label>
                        <span id="income-gumroad-status" style="font-size: 13px; color: var(--text-secondary);">…</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                        <input type="password" id="income-gumroad-token" placeholder="Paste Gumroad access token" style="flex: 1; min-width: 200px;" autocomplete="off">
                        <button type="button" onclick="saveIncomeKeys()">Save keys</button>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>Stripe:</label>
                        <span id="income-stripe-status" style="font-size: 13px; color: var(--text-secondary);">…</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <input type="password" id="income-stripe-token" placeholder="Paste Stripe secret key (sk_…)" style="flex: 1; min-width: 200px;" autocomplete="off">
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
                        <button type="button" class="secondary" onclick="clearIncomeKey('gumroad')">Remove Gumroad from config file</button>
                        <button type="button" class="secondary" onclick="clearIncomeKey('stripe')">Remove Stripe from config file</button>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 10px;">Removing only deletes keys from the JSON file; unset env vars in your shell or system if those are set.</p>
                </div>

                <div class="card">
                    <h2>Learning Sources</h2>
                    <div style="margin-top: 16px;">
                        <div class="badge success" style="margin: 6px;">Reddit API</div>
                        <div class="badge success" style="margin: 6px;">RSS Feeds</div>
                        <div class="badge success" style="margin: 6px;">Facebook Pages</div>
                        <div class="badge success" style="margin: 6px;">X (Twitter) Search</div>
                        <div class="badge success" style="margin: 6px;">ChatGPT Conversations</div>
                        <div class="badge success" style="margin: 6px;">Web URLs</div>
                        <div class="badge" style="margin: 6px;">Financial Data</div>
                        <div class="badge" style="margin: 6px;">Social Media</div>
                    </div>
                    <div style="margin-top: 20px; padding: 12px; background: var(--bg-dark); border-radius: 8px;">
                        <strong style="color: var(--text-primary);">Status:</strong>
                        <div id="learning-status" style="margin-top: 8px; color: var(--success);">Learning system ready</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tasks Tab -->
        <div id="tasks" class="tab-content">
            <div class="card">
                <h2>Task Queue</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                    Lists work waiting for Elysia or Guardian. Refresh to see status; items here may run when autonomy or the event loop is active.
                </p>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    Guardian <strong>TaskEngine</strong> items, Elysia loop <strong>GlobalTaskQueue</strong> jobs, and optional <strong>TASKS/*.md</strong> drop files.
                </p>
                <p style="font-size: 10px; color: var(--warning); margin: 0 0 10px 0;">Review before acting on queued tasks.</p>
                <button type="button" onclick="refreshTaskQueue()">Refresh</button>
                <div id="task-list" style="margin-top: 16px;"></div>
            </div>
        </div>

        <!-- Workbench Tab -->
        <div id="workbench" class="tab-content">
            <div class="section">
                <div class="controls">
                    <h2>Operator Workbench</h2>
                    <p class="ui-clarity-helper" style="color: var(--text-secondary); margin-bottom: 12px; line-height: 1.45;">
                        See what Elysia has actually produced: opportunities, active self-tasks, learning digests, and recent artifacts. Read-only overview for operators.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 16px 0;">Review-only: does not start new autonomous work from this tab.</p>
                    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                        <button onclick="refreshWorkbench()">Refresh Workbench</button>
                    </div>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>Workbench Snapshot</h2>
                    <div id="workbench-metrics" style="font-size: 13px; line-height: 1.7;">
                        <em>Loading snapshot...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Top Opportunities</h2>
                    <div id="workbench-opportunities" style="font-size: 12px;">
                        <em>Loading opportunities...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Active Self-Tasks</h2>
                    <div id="workbench-active-tasks" style="font-size: 12px;">
                        <em>Loading active tasks...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Recent Useful Tasks</h2>
                    <div id="workbench-successes" style="font-size: 12px;">
                        <em>Loading recent task results...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Sales Launch</h2>
                    <div id="workbench-sales-launch" style="font-size: 12px;">
                        <em>Loading sales launch plan...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Learning Digests</h2>
                    <div id="workbench-digests" style="font-size: 12px;">
                        <em>Loading digests...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Improvement Briefs</h2>
                    <div id="workbench-improvements" style="font-size: 12px;">
                        <em>Loading improvement briefs...</em>
                    </div>
                </div>
            </div>

            <div class="card" style="margin-top: 20px;">
                <h2>Recent Artifacts</h2>
                <div id="workbench-artifacts" style="font-size: 12px;">
                    <em>Loading artifacts...</em>
                </div>
            </div>
        </div>

        <!-- Security Tab -->
        <div id="security" class="tab-content">
            <div class="card">
                <h2>Security Events</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.45;">
                    Recent security-related events and alerts. Read-only log for investigation; does not change security policy.
                </p>
                <div id="security-events"></div>
            </div>
        </div>

        <!-- Memory Tab -->
        <div id="memory" class="tab-content">
            <div class="card">
                <h2>Memory</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45; margin-bottom: 12px;">
                    Saved information Elysia can use later. This may include conversation summaries, lessons, and important context.
                </p>
                <h3 style="margin-top: 0;">Memory Operations</h3>
                <div class="input-group">
                    <label>Search Memories:</label>
                    <input type="text" id="memory-search" placeholder="Enter search query">
                    <button onclick="searchMemories()">Search</button>
                </div>
                <div id="memory-results"></div>
            </div>
        </div>

        <!-- Introspection Tab -->
        <div id="introspection" class="tab-content">
            <div class="section">
                <div class="controls">
                    <h2>Introspection & Self-Analysis</h2>
                    <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.45;">
                        Read-only analysis of memory health, focus, and behavior patterns. Buttons refresh reports; they do not rewrite memory.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 10px 0;">Read-only: no memory changes are applied from this tab.</p>
                    <button onclick="refreshIntrospection()">Refresh All</button>
                    <button onclick="getComprehensiveReport()">Full Report</button>
                    <button onclick="checkMemoryHealth()">Memory Health</button>
                    <button onclick="analyzeFocus()">Focus Analysis</button>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>System Identity</h2>
                    <div id="identity-summary" style="white-space: pre-wrap; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                        <em>Click "Full Report" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Memory Health</h2>
                    <div class="metric">
                        <span class="metric-label">Status:</span>
                        <span class="metric-value" id="health-status">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Health Score:</span>
                        <span class="metric-value" id="health-score">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Memories:</span>
                        <span class="metric-value" id="health-total">-</span>
                    </div>
                    <div id="health-warnings" style="margin-top: 10px; font-size: 12px; color: #f39c12;">
                        <em>Click "Memory Health" to analyze...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Focus Analysis (24h)</h2>
                    <div class="metric">
                        <span class="metric-label">Primary Focus:</span>
                        <span class="metric-value" id="focus-primary">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Activity Count:</span>
                        <span class="metric-value" id="focus-activity">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Priority Trend:</span>
                        <span class="metric-value" id="focus-trend">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Most Active Period:</span>
                        <span class="metric-value" id="focus-period">-</span>
                    </div>
                    <div id="focus-distribution" style="margin-top: 10px; font-size: 11px; font-family: monospace;">
                        <em>Click "Focus Analysis" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Behavior Patterns</h2>
                    <div id="behavior-report" style="white-space: pre-wrap; font-family: monospace; font-size: 11px; max-height: 300px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                        <em>Click "Full Report" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Introspection Decisions</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Last decision from heartbeat-driven introspection</p>
                    <div id="introspection-debug" style="font-family: monospace; font-size: 11px; padding: 10px; background: #0f3460; border-radius: 4px; min-height: 80px;">
                        <em>Loading...</em>
                    </div>
                    <button onclick="refreshIntrospectionDebug()" style="margin-top: 8px;">Refresh</button>
                </div>
            </div>

            <div class="card" style="margin-top: 20px;">
                <h2>Memory Correlations</h2>
                <div class="input-group">
                    <label>Search for correlated memories:</label>
                    <input type="text" id="correlation-keyword" placeholder="Enter keyword">
                    <button onclick="findCorrelations()">Find Correlations</button>
                </div>
                <div id="correlation-results" style="margin-top: 15px; font-size: 11px; font-family: monospace; max-height: 400px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                    <em>Enter a keyword and click "Find Correlations" to analyze related memories...</em>
                </div>
            </div>
        </div>

        <!-- Control Tab -->
        <div id="control" class="tab-content">
            <div class="controls">
                <h2>Control</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45; max-width: 920px;">
                    Manual operator controls. These affect how Elysia is monitored or directed. Use carefully.
                </p>
                <p style="font-size: 10px; color: var(--warning); margin: 0 0 12px 0;">Review before using. This may affect runtime behavior.</p>
                <h2 style="margin-top: 8px;">System Controls</h2>
                <button onclick="pauseLoop()">Pause Event Loop</button>
                <button onclick="resumeLoop()">Resume Event Loop</button>
                <button onclick="createSnapshot()">Create Memory Snapshot</button>
                <button onclick="triggerDreamCycle()" class="danger">Trigger Dream Cycle</button>
                
                <div class="input-group" style="margin-top: 16px;">
                    <label>Speak (TTS):</label>
                    <input type="text" id="speak-text" placeholder="e.g., System is operational" style="flex: 1;">
                    <select id="speak-mode">
                        <option value="guardian">Guardian</option>
                        <option value="warm_guide">Warm Guide</option>
                        <option value="sharp_analyst">Sharp Analyst</option>
                        <option value="poetic_oracle">Poetic Oracle</option>
                    </select>
                    <button onclick="speakMessage()">Speak</button>
                </div>
                
                <div class="input-group">
                    <label>Submit Task:</label>
                    <textarea id="task-code" placeholder="async def task():&#10;    # Your task code here&#10;    return 'result'"></textarea>
                    <input type="number" id="task-priority" placeholder="Priority (1-10)" value="5" min="1" max="10">
                    <button onclick="submitTask()">Submit Task</button>
                </div>

                <h3 style="margin-top: 24px;">APIs &amp; Tools</h3>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Trigger income, research, harvest, and AI chat from the dashboard.</p>
                <h3 style="margin-top: 16px;">Conversation Chat</h3>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45;">
                    This is your conversation with Elysia. Messages are saved locally so refreshes do not erase the thread.
                </p>
                <div class="input-group" style="margin-bottom: 12px;">
                    <label>Chat with Elysia:</label>
                    <div style="font-size: 11px; color: var(--text-secondary); margin: 4px 0;">
                        Conversation: <span id="api-chat-conv-label">control_panel</span>
                        · Stored under <code>data/runtime/conversations/</code>
                    </div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <input type="text" id="api-chat-message" placeholder="Ask anything..." style="flex: 1; min-width: 200px;">
                        <button type="button" onclick="sendApiChat()">Send message to Elysia</button>
                        <button type="button" onclick="startNewApiChat()">Start new conversation</button>
                    </div>
                    <div id="api-chat-result" style="margin-top: 8px; padding: 10px; background: var(--bg-dark); border-radius: 8px; font-size: 13px; min-height: 40px; white-space: pre-wrap;"></div>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
                    <button onclick="refreshIncomeStatus()">Income / API Status</button>
                    <button onclick="runHarvestReport()">Harvest Report</button>
                    <button onclick="runResearchProposal()">Research Proposal (WebScout)</button>
                    <button onclick="runPromptEvolution()">Run Prompt Evolution</button>
                </div>
                <p style="color: var(--text-secondary); font-size: 11px; margin: 0 0 10px 0;">
                    Gumroad / Stripe: environment and HarvestEngine wiring only (no secrets). Refresh with <strong>Income / API Status</strong>.
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-bottom: 14px;">
                    <div style="padding: 12px; background: var(--bg-dark); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
                        <div style="font-weight: 600; margin-bottom: 6px;">Gumroad</div>
                        <div id="payment-status-gumroad" style="font-size: 12px; color: var(--text-secondary); white-space: pre-wrap;">—</div>
                    </div>
                    <div style="padding: 12px; background: var(--bg-dark); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
                        <div style="font-weight: 600; margin-bottom: 6px;">Stripe</div>
                        <div id="payment-status-stripe" style="font-size: 12px; color: var(--text-secondary); white-space: pre-wrap;">—</div>
                    </div>
                </div>
                <h4 style="margin: 16px 0 8px 0;">Wallet accounts</h4>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 8px;">
                    Add virtual sub-accounts (ledger in <code>organized_project/data/</code>). Optional: copy <code>wallet_accounts.example.json</code> to <code>wallet_accounts.json</code> for bulk setup on startup.
                </p>
                <div class="input-group" style="margin-bottom: 8px; flex-wrap: wrap;">
                    <input type="text" id="wallet-new-name" placeholder="Display name (e.g. Tax reserve)" style="min-width: 160px; flex: 1;">
                    <input type="text" id="wallet-new-id" placeholder="Optional id (slug)" style="width: 140px;">
                    <button onclick="refreshWalletAccounts()">List accounts</button>
                    <button onclick="addWalletAccount()">Add account</button>
                </div>
                <div id="api-tools-result" style="padding: 10px; background: var(--bg-dark); border-radius: 8px; font-size: 12px; min-height: 40px; white-space: pre-wrap;"></div>
            </div>
        </div>

        <!-- Insights: RAG / traces / MCP (operator observability) -->
        <div id="insights" class="tab-content">
            <div class="card">
                <h2>📡 What Elysia is doing</h2>
                <p class="ui-clarity-helper" style="color: var(--text-secondary); font-size: 13px; max-width: 900px; line-height: 1.45;">
                    Observability only: RAG paths, optional LLM trace files, recent log lines, and MCP readiness. Refresh buttons reload data; they do not run new jobs.
                </p>
                <p style="color: var(--text-secondary); font-size: 12px; max-width: 900px; margin-top: 8px;">
                    Self-build RAG paths, optional LLM JSONL traces (<code>ELYSIA_LLM_TRACE_JSONL</code>),
                    recent <code>selfbuild_rag</code> log lines, and MCP readiness — same data as scripts, in one place.
                </p>
                <div style="display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0;">
                    <button onclick="refreshInsightsOverview()">Refresh overview</button>
                    <button onclick="refreshInsightsTraces()">Reload trace tail</button>
                    <button onclick="refreshInsightsRagLog()">Reload RAG log tail</button>
                </div>
            </div>
            <div class="grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px;">
                <div class="card">
                    <h3>USB / paths</h3>
                    <div id="insights-storage-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 88px;">—</div>
                </div>
                <div class="card">
                    <h3>Local Ollama</h3>
                    <div id="insights-ollama-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 88px; white-space: pre-wrap;">—</div>
                </div>
                <div class="card">
                    <h3>API gas meter</h3>
                    <p style="font-size: 11px; color: var(--text-secondary); margin: 0 0 8px 0;">
                        This process only — resets on restart. Paid chat vs local vs structured OpenAI paths.
                    </p>
                    <div id="insights-api-meter-summary" style="font-size: 11px; font-family: monospace; color: var(--text-secondary); min-height: 120px; white-space: pre-wrap;">—</div>
                </div>
                <div class="card">
                    <h3>Self-build</h3>
                    <div id="insights-selfbuild-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 72px;">—</div>
                </div>
                <div class="card">
                    <h3>MCP</h3>
                    <div id="insights-mcp-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 72px;">—</div>
                </div>
                <div class="card">
                    <h3>LLM trace file</h3>
                    <div id="insights-trace-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 72px;">—</div>
                </div>
                <div class="card">
                    <h3>RAG log</h3>
                    <div id="insights-rag-summary" style="font-size: 12px; font-family: monospace; color: var(--text-secondary); min-height: 72px;">—</div>
                </div>
                <div class="card">
                    <h3>Brains / routing</h3>
                    <div id="insights-brains-summary" style="font-size: 11px; font-family: monospace; color: var(--text-secondary); min-height: 120px; white-space: pre-wrap;">—</div>
                </div>
                <div class="card">
                    <h3>Mission / topics</h3>
                    <div id="insights-mission-summary" style="font-size: 11px; font-family: monospace; color: var(--text-secondary); min-height: 120px; white-space: pre-wrap;">—</div>
                </div>
            </div>
            <div class="card" style="margin-top: 14px;">
                <h3>Full JSON</h3>
                <pre id="insights-json-overview" style="max-height: 420px; overflow: auto; font-size: 11px; background: #0f3460; padding: 12px; border-radius: 6px; margin: 0;">Click &quot;Refresh overview&quot;…</pre>
            </div>
            <div class="card" style="margin-top: 14px;">
                <h3>Trace tail (raw lines)</h3>
                <pre id="insights-trace-lines" style="max-height: 220px; overflow: auto; font-size: 11px; background: #16213e; padding: 10px; border-radius: 6px;">—</pre>
            </div>
            <div class="card" style="margin-top: 14px;">
                <h3>Unified LLM log — selfbuild_rag lines</h3>
                <pre id="insights-rag-lines" style="max-height: 220px; overflow: auto; font-size: 11px; background: #16213e; padding: 10px; border-radius: 6px;">—</pre>
            </div>
        </div>

        <!-- API Meter Tab (graphical) -->
        <div id="api-meter" class="tab-content">
            <div class="card" style="margin-bottom: 16px;">
                <h2>⛽ API gas meter</h2>
                <p style="color: var(--text-secondary); font-size: 14px; max-width: 920px; line-height: 1.55;">
                    Session-scoped usage for this process (resets on restart). Charts mirror <code>/api/insights/api-meter</code>.
                    Green/red stacks are successful vs failed calls per channel; doughnut is router decision counts; bars are reported tokens.
                </p>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px;">
                    <button type="button" onclick="refreshApiMeterTab()">Refresh charts</button>
                </div>
            </div>
            <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                <div class="card api-meter-stat-card">
                    <h3>Session uptime</h3>
                    <div id="api-meter-stat-uptime" style="font-size: 26px; font-weight: 700;">—</div>
                </div>
                <div class="card api-meter-stat-card">
                    <h3>Calls OK</h3>
                    <div id="api-meter-stat-ok" style="font-size: 26px; font-weight: 700; color: var(--success);">—</div>
                </div>
                <div class="card api-meter-stat-card">
                    <h3>Calls fail</h3>
                    <div id="api-meter-stat-fail" style="font-size: 26px; font-weight: 700; color: var(--danger);">—</div>
                </div>
                <div class="card api-meter-stat-card">
                    <h3>Tokens reported</h3>
                    <div id="api-meter-stat-tokens" style="font-size: 26px; font-weight: 700; color: var(--primary);">—</div>
                </div>
            </div>
            <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 20px; margin-top: 8px;">
                <div class="card">
                    <h3>Calls by channel</h3>
                    <p class="api-meter-chart-note">Stacked: OK vs failed completions per transport channel.</p>
                    <div id="api-meter-fallback-transport" style="display:none;font-size:12px;color:var(--text-secondary);"></div>
                    <div class="chart-container" style="height: 300px; position: relative;">
                        <canvas id="api-meter-canvas-transport"></canvas>
                    </div>
                </div>
                <div class="card">
                    <h3>Router choices</h3>
                    <p class="api-meter-chart-note">Counts from <code>select_best_api</code> (probes excluded).</p>
                    <div id="api-meter-fallback-router" style="display:none;font-size:12px;color:var(--text-secondary);"></div>
                    <div class="chart-container" style="height: 300px; position: relative;">
                        <canvas id="api-meter-canvas-router"></canvas>
                    </div>
                </div>
            </div>
            <div class="card" style="margin-top: 8px;">
                <h3>Tokens by channel</h3>
                <p class="api-meter-chart-note">Sum of provider-reported tokens (mostly OpenAI structured paths).</p>
                <div id="api-meter-fallback-tokens" style="display:none;font-size:12px;color:var(--text-secondary);"></div>
                <div class="chart-container" style="height: 280px; position: relative;">
                    <canvas id="api-meter-canvas-tokens"></canvas>
                </div>
            </div>
            <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 8px;">
                <div class="card">
                    <h3>OpenAI routing</h3>
                    <div id="api-meter-gauge-openai"></div>
                </div>
                <div class="card">
                    <h3>OpenRouter</h3>
                    <div id="api-meter-gauge-openrouter"></div>
                </div>
                <div class="card">
                    <h3>Anthropic (trust)</h3>
                    <div id="api-meter-gauge-anthropic"></div>
                </div>
            </div>
            <div class="card" style="margin-top: 8px;">
                <h3>Session meter &amp; unified budget</h3>
                <pre id="api-meter-detail-text" style="max-height: 220px; overflow: auto; font-size: 11px; background: var(--bg-dark); padding: 12px; border-radius: 8px; white-space: pre-wrap; margin: 0;">—</pre>
            </div>
            <div class="card" style="margin-top: 8px;">
                <h3>All configured APIs &amp; usage hints</h3>
                <p style="color: var(--text-secondary); font-size: 12px; margin: 0 0 10px 0; max-width: 920px;">
                    Key present (file/env), routing where applicable, local Brave/Tavily month counters (~plan limits),
                    Alpha Vantage / Replicate env-only visibility. Nothing secret is echoed.
                </p>
                <pre id="api-meter-availability-block" style="max-height: 300px; overflow: auto; font-size: 11px; background: var(--bg-dark); padding: 12px; border-radius: 8px; white-space: pre-wrap; margin: 0;">—</pre>
            </div>
        </div>

        <!-- Logs Tab -->
        <div id="logs" class="tab-content">
            <div class="card" style="margin-bottom: 12px;">
                <h2>Backend Log Tail</h2>
                <p style="font-size: 12px; color: var(--text-secondary); margin: 0 0 10px 0; line-height: 1.45;">
                    Reads the current rotating backend log first: <code>elysia_unified.log</code>. The old
                    <code>unified_autonomous_system.log</code> is treated as legacy trial history.
                </p>
                <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px;">
                    <button type="button" onclick="refreshBackendLogs()">Refresh backend logs</button>
                    <span id="backend-log-source" style="font-size: 12px; color: var(--text-secondary);">Not loaded yet.</span>
                </div>
                <div id="legacy-log-warning" style="font-size: 12px; color: var(--warning); margin-bottom: 8px;"></div>
                <pre id="backend-log-lines" style="max-height: 460px; overflow: auto; font-size: 11px; background: var(--bg-dark); padding: 12px; border-radius: 8px; white-space: pre-wrap; margin: 0;">Click "Refresh backend logs" to load the live log tail.</pre>
            </div>
            <div class="card">
                <h2>Control Panel Events</h2>
                <div class="console" id="console-logs">
                    <div class="log-entry">[System] Control Panel initialized</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Define addLog function FIRST so it's available immediately
        function addLog(message, level) {
            if (level === undefined) level = 'info';
            try {
                const console = document.getElementById('console-logs');
                if (console) {
                    const entry = document.createElement('div');
                    entry.className = 'log-entry log-' + level;
                    entry.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
                    console.appendChild(entry);
                    console.scrollTop = console.scrollHeight;
                } else {
                    // Fallback to browser console if element not found
                    console.log('[' + level.toUpperCase() + '] ' + message);
                }
            } catch (e) {
                console.log('[' + level.toUpperCase() + '] ' + message);
            }
        }
        
        // Make addLog globally available
        window.addLog = addLog;

        function formatLogAge(seconds) {
            if (seconds === null || seconds === undefined) return 'unknown age';
            var n = Number(seconds);
            if (!isFinite(n)) return 'unknown age';
            if (n < 60) return Math.round(n) + 's ago';
            if (n < 3600) return Math.round(n / 60) + 'm ago';
            if (n < 86400) return Math.round(n / 3600) + 'h ago';
            return Math.round(n / 86400) + 'd ago';
        }

        window.refreshBackendLogs = function() {
            const linesEl = document.getElementById('backend-log-lines');
            const sourceEl = document.getElementById('backend-log-source');
            const legacyEl = document.getElementById('legacy-log-warning');
            if (linesEl) linesEl.textContent = 'Loading backend log tail...';
            if (sourceEl) sourceEl.textContent = 'Loading...';
            if (legacyEl) legacyEl.textContent = '';

            fetch('/api/logs/recent?lines=160', {headers: {'Accept': 'application/json'}})
                .then(function(r) {
                    if (!r.ok) throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                    return r.json();
                })
                .then(function(data) {
                    const source = data.source || {};
                    if (sourceEl) {
                        if (source.exists) {
                            sourceEl.textContent = source.label + ' - updated ' + formatLogAge(source.age_seconds) + ' - ' + source.path;
                        } else {
                            sourceEl.textContent = data.message || 'No backend log found.';
                        }
                    }
                    if (linesEl) {
                        const lines = Array.isArray(data.lines) ? data.lines : [];
                        linesEl.textContent = lines.length ? lines.join('\n') : (data.message || 'No log lines found.');
                    }
                    const legacy = data.legacy_source || {};
                    if (legacyEl && legacy.exists) {
                        var warning = 'Legacy trial log: ' + legacy.path + ' - updated ' + formatLogAge(legacy.age_seconds) + '.';
                        if (legacy.stale) warning += ' This is historical, not the live backend log.';
                        if (source.role === 'legacy_trial_history') warning += ' Current backend log was not found, so this fallback is being shown.';
                        legacyEl.textContent = warning;
                    }
                    if (data.message && window.addLog) addLog(data.message, source.stale ? 'warning' : 'info');
                })
                .catch(function(err) {
                    if (linesEl) linesEl.textContent = 'Could not load backend logs: ' + err;
                    if (sourceEl) sourceEl.textContent = 'Backend log fetch failed.';
                    if (window.addLog) addLog('Backend log fetch failed: ' + err, 'error');
                });
        };
        
        // Define toggleTheme and showTab early so buttons work even before full script loads
        window.toggleTheme = function() {
            var body = document.body;
            var currentTheme = body.getAttribute('data-theme');
            var newTheme = currentTheme === 'light' ? 'dark' : 'light';
            body.setAttribute('data-theme', newTheme);
            try { localStorage.setItem('theme', newTheme); } catch (e) {}
            if (window.addLog) addLog('Theme: ' + newTheme, 'info');
        };
        
        // Define showTab early so tab buttons work even before DOMContentLoaded completes
        window.showTab = function(tabName, buttonElement) {
            document.querySelectorAll('.tab-content').forEach(function(tab) { tab.classList.remove('active'); });
            document.querySelectorAll('.tab').forEach(function(tab) { tab.classList.remove('active'); });
            const tabContent = document.getElementById(tabName);
            if (tabContent) tabContent.classList.add('active');
            if (buttonElement) buttonElement.classList.add('active');
            else {
                document.querySelectorAll('.tab').forEach(function(tab) {
                    if (tab.textContent.indexOf(tabName.charAt(0).toUpperCase() + tabName.slice(1)) >= 0)
                        tab.classList.add('active');
                });
            }
            if (tabName === 'introspection' && typeof window.refreshIntrospectionDebug === 'function')
                window.refreshIntrospectionDebug();
            if (tabName === 'learning') {
                if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                if (typeof window.refreshLearningSettings === 'function') window.refreshLearningSettings();
                if (typeof window.refreshIncomeKeysStatus === 'function') window.refreshIncomeKeysStatus();
            }
            if (tabName === 'dashboard') {
                if (typeof window.suggestNextAction === 'function') window.suggestNextAction();
                if (typeof window.refreshAutonomyStatus === 'function') window.refreshAutonomyStatus();
                if (typeof window.refreshDashboardApiMeter === 'function') window.refreshDashboardApiMeter();
            }
            if (tabName === 'tasks' && typeof window.refreshTaskQueue === 'function')
                window.refreshTaskQueue();
            if (tabName === 'workbench' && typeof window.refreshWorkbench === 'function')
                window.refreshWorkbench();
            if (tabName === 'insights' && typeof window.refreshInsightsOverview === 'function')
                window.refreshInsightsOverview();
            if (tabName === 'api-meter' && typeof window.refreshApiMeterTab === 'function')
                window.refreshApiMeterTab();
            if (tabName === 'logs' && typeof window.refreshBackendLogs === 'function')
                window.refreshBackendLogs();
        };
        
        const socket = (typeof io !== 'undefined') ? io() : null;
        let updateInterval;
        let initialized = false;

        // Initialize on page load - show UI immediately
        document.addEventListener('DOMContentLoaded', function() {
            try {
                addLog('Control Panel loaded at ' + window.location.href, 'info');
                const spinner = document.getElementById('loading-spinner');
                if (spinner) spinner.style.display = 'none';
                const statusTextEl = document.getElementById('status-text');
                if (statusTextEl) statusTextEl.textContent = 'Connecting...';
                const indicator = document.getElementById('status-indicator');
                if (indicator) indicator.className = 'status-indicator status-connected';
                if (!socket) {
                    addLog('Socket.IO CDN not loaded - using HTTP polling only', 'warning');
                }
                setTimeout(function() {
                    try { startUpdates(); } catch (e) {
                        addLog('startUpdates error: ' + e.message, 'error');
                        console.error(e);
                    }
                }, 100);
                setTimeout(function() {
                    try {
                        if (typeof window.refreshDashboardApiMeter === 'function') window.refreshDashboardApiMeter();
                    } catch (e) { console.error(e); }
                }, 350);
                setTimeout(function() {
                    try {
                        if (typeof window.refreshWorkbench === 'function') window.refreshWorkbench();
                    } catch (e) {
                        addLog('refreshWorkbench error: ' + e.message, 'error');
                        console.error(e);
                    }
                }, 600);
                setTimeout(function() {
                    try {
                        if (typeof window.refreshApiChatHistory === 'function') window.refreshApiChatHistory();
                        if (typeof window.refreshBrainTrace === 'function') window.refreshBrainTrace();
                        if (typeof window.refreshSelfImprovementProposals === 'function') window.refreshSelfImprovementProposals();
                        if (typeof window.refreshMemoryRankingSummary === 'function') window.refreshMemoryRankingSummary();
                        if (typeof window.refreshPromptContractStatus === 'function') window.refreshPromptContractStatus();
                    } catch (e) {
                        addLog('refreshApiChatHistory error: ' + e.message, 'warning');
                        console.error(e);
                    }
                }, 750);
            } catch (e) {
                console.error('DOMContentLoaded error:', e);
                if (window.addLog) addLog('Init error: ' + e.message, 'error');
            }
        });

        if (socket) socket.on('connect', function() {
            addLog('Connected to Elysia system', 'info');
            if (!updateInterval) {
                startUpdates();
            }
        });

        if (socket) socket.on('disconnect', function() {
            addLog('Disconnected from Elysia system', 'warning');
        });

        if (socket) socket.on('connect_error', function(error) {
            addLog('Socket.IO connection error (continuing with HTTP polling): ' + error, 'warning');
            // Still start updates even if socket fails - use HTTP polling instead
            if (!updateInterval && !initialized) {
                startUpdates();
            }
        });
        
        // Fallback: if socket doesn't connect within 2 seconds, start HTTP polling
        setTimeout(function() {
            if (!initialized && (!socket || !socket.connected)) {
                addLog('Socket.IO not connected, using HTTP polling mode', 'info');
                startUpdates();
            }
        }, 2000);

        if (socket) socket.on('status_update', function(data) {
            updateDashboard(data);
        });

        if (socket) socket.on('log_entry', function(data) {
            addLog(data.message, data.level || 'info');
        });

        // Safety: force UI usable if stuck - run at 2s and 4s
        setTimeout(function() {
            const statusTextEl = document.getElementById('status-text');
            const spinner = document.getElementById('loading-spinner');
            if (statusTextEl && (statusTextEl.textContent === 'Initializing...' || statusTextEl.textContent === 'Connecting...')) {
                statusTextEl.textContent = 'Connected (Limited)';
                if (spinner) spinner.style.display = 'none';
                const ind = document.getElementById('status-indicator');
                if (ind) ind.className = 'status-indicator status-running';
                addLog('Status: using limited mode - buttons should work', 'info');
            }
        }, 2000);
        setTimeout(function() {
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl && statusTextEl.textContent === 'Connecting...') {
                statusTextEl.textContent = 'Connected (Limited)';
            }
        }, 4000);

        function startUpdates() {
            // Prevent multiple initializations
            if (initialized) {
                return;
            }
            initialized = true;
            
            // Mark as initialized immediately to show UI
            const spinner = document.getElementById('loading-spinner');
            if (spinner) {
                spinner.style.display = 'none';
            }
            
            // Show "Connecting" status immediately
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl) {
                statusTextEl.textContent = 'Connecting...';
            }
            const indicator = document.getElementById('status-indicator');
            if (indicator) {
                indicator.className = 'status-indicator status-running';
            }
            
            // Set a timeout to show "Connected" status if API doesn't respond quickly
            let timeoutId = setTimeout(function() {
                if (statusTextEl && (statusTextEl.textContent === 'Initializing...' || statusTextEl.textContent === 'Connecting...')) {
                    statusTextEl.textContent = 'Connected';
                    if (indicator) {
                        indicator.className = 'status-indicator status-running';
                    }
                    addLog('Connected to server (waiting for status)', 'info');
                }
            }, 2000); // 2 second timeout (reduced from 3)
            
            // Do an immediate update with timeout protection
            const controller = new AbortController();
            const timeoutId2 = setTimeout(function() { controller.abort(); }, 5000); // 5 second fetch timeout
            
            fetch('/api/status', { 
                method: 'GET',
                headers: {'Accept': 'application/json'},
                signal: controller.signal
            })
                .then(function(r) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    if (!r.ok) {
                        throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                    }
                    return r.json();
                })
                .then(function(data) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    updateDashboard(data);
                    addLog('Status update received', 'info');
                })
                .catch(function(err) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    const msg = err.name === 'AbortError' ? 'Status timed out (5s)' : (err.message || String(err));
                    addLog('Status fetch failed: ' + msg + ' - using fallback', 'warning');
                    // Use fallback status to show UI is working
                    // Check if we have any indicators that system is running
                    updateDashboard({
                        system: { running: true, initialized: true, uptime: 0 },
                        loop: { running: true, paused: false, queue_size: 0 },
                        memory: { total_entries: 0, total_memories: 0 },
                        security: { policy_loaded: false, recent_violations: 0, pending_reviews: 0 },
                        trust: { components: 0, average_trust: 0 }
                    });
                    
                    // Ensure UI is visible even on error
                    const statusTextEl = document.getElementById('status-text');
                    if (statusTextEl && statusTextEl.textContent === 'Initializing...') {
                        statusTextEl.textContent = 'Connected (Limited)';
                    }
                });
            
            // Then set up interval
            if (updateInterval) {
                clearInterval(updateInterval);
            }
            updateInterval = setInterval(function() {
                const controller = new AbortController();
                const timeoutId = setTimeout(function() { controller.abort(); }, 5000); // 5 second timeout
                
                fetch('/api/status', {
                    method: 'GET',
                    headers: {'Accept': 'application/json'},
                    signal: controller.signal
                })
                    .then(function(r) {
                        clearTimeout(timeoutId);
                        if (!r.ok) {
                            throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                        }
                        return r.json();
                    })
                    .then(function(data) {
                        clearTimeout(timeoutId);
                        updateDashboard(data);
                    })
                    .catch(function(err) {
                        clearTimeout(timeoutId);
                        if (err.name !== 'AbortError') {
                            console.log('Status fetch error:', err);
                        }
                        // Don't update status on error - keep showing last known status
                    });
            }, 2000);

            setInterval(function() {
                try {
                    if (typeof window.refreshDashboardApiMeter === 'function')
                        window.refreshDashboardApiMeter();
                    var am = document.getElementById('api-meter');
                    if (am && am.classList.contains('active') && typeof window.refreshApiMeterTab === 'function')
                        window.refreshApiMeterTab();
                } catch (e) { /* ignore */ }
            }, 30000);
        }

        function updateDashboard(data) {
            if (!data || typeof data !== 'object') return;
            const spinner = document.getElementById('loading-spinner');
            if (spinner) spinner.style.display = 'none';
            
            // Update status indicator and text first
            // Priority: system initialized/running > loop status > memory loaded > connected
            // If we got any response, never stay stuck on "Initializing"
            let status = 'connected';
            let statusText = 'Connected';
            
            // Check for errors first
            if (data.system && data.system.error) {
                status = 'stopped';
                statusText = 'Error: ' + (data.system.error.substring(0, 30) || 'Unknown error');
            } else if (data.system && data.system.timeout) {
                status = 'stopped';
                statusText = 'Timeout - Slow Response';
            } else if (data.system) {
                // Check multiple indicators to determine status
                const systemInitialized = data.system.initialized || false;
                const systemRunning = data.system.running || false;
                const loopRunning = data.loop && data.loop.running !== undefined ? data.loop.running : false;
                const memoryLoaded = data.memory && data.memory.total_entries > 0;
                const hasUptime = data.system.uptime && data.system.uptime > 0;
                
                // System is considered running if any of these are true:
                const isActuallyRunning = systemRunning || loopRunning || memoryLoaded || hasUptime;
                const isActuallyInitialized = systemInitialized || memoryLoaded || loopRunning || hasUptime;
                
                if (isActuallyInitialized || isActuallyRunning) {
                    // System is initialized/running, check loop status for more detail
                    if (data.loop && data.loop.running !== undefined) {
                        status = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'initialized';
                        statusText = status.charAt(0).toUpperCase() + status.slice(1);
                    } else if (memoryLoaded) {
                        // Memory is loaded, system is running
                        status = 'running';
                        statusText = 'Running';
                    } else {
                        // System is initialized but not fully running yet
                        status = isActuallyRunning ? 'running' : 'initialized';
                        statusText = status.charAt(0).toUpperCase() + status.slice(1);
                    }
                } else {
                    // Got system data but not fully initialized - still show connected so UI is usable
                    status = 'connected';
                    statusText = 'Connected (Limited)';
                }
            } else if (data.loop && data.loop.running !== undefined) {
                // Only loop data available
                status = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'stopped';
                statusText = status.charAt(0).toUpperCase() + status.slice(1);
            } else if (data.memory && data.memory.total_entries > 0) {
                // Memory is loaded, system is likely running
                status = 'running';
                statusText = 'Running';
            } else {
                // No system data but we got a response - assume connected but initializing
                status = 'connected';
                statusText = 'Connected';
            }
            
            const indicator = document.getElementById('status-indicator');
            if (indicator) {
                indicator.className = 'status-indicator status-' + status;
            }
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl) {
                statusTextEl.textContent = statusText;
            }
            
            // Update system metrics
            if (data.system) {
                const uptimeEl = document.getElementById('uptime');
                if (uptimeEl) {
                    const uptime = data.system.uptime || 0;
                    uptimeEl.textContent = Math.floor(uptime) + 's';
                }
                const activeTasksEl = document.getElementById('active-tasks');
                if (activeTasksEl) {
                    const tasks = (data.system.tasks && data.system.tasks.active_tasks) || (data.system.operational_stats && data.system.operational_stats.total_tasks_processed) || 0;
                    activeTasksEl.textContent = tasks;
                }
            }
            
            if (data.loop) {
                const loopStatusEl = document.getElementById('loop-status');
                if (loopStatusEl) {
                    const loopStatus = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'stopped';
                    loopStatusEl.textContent = loopStatus;
                }
                const queueSizeEl = document.getElementById('queue-size');
                if (queueSizeEl) {
                    queueSizeEl.textContent = data.loop.queue_size || 0;
                }
            }
            
            if (data.memory) {
                const totalMemoriesEl = document.getElementById('total-memories');
                if (totalMemoriesEl) {
                    totalMemoriesEl.textContent = data.memory.total_entries || data.memory.total_memories || 0;
                }
                const vectorEnabledEl = document.getElementById('vector-enabled');
                if (vectorEnabledEl) {
                    vectorEnabledEl.textContent = (data.memory.vector_memory_enabled || data.memory.vector_enabled) ? 'Yes' : 'No';
                }
                const cleanup = data.memory.last_cleanup || {};
                const cleanupOutcomeEl = document.getElementById('last-cleanup-outcome');
                if (cleanupOutcomeEl) {
                    cleanupOutcomeEl.textContent = cleanup.outcome || 'none';
                }
                const cleanupReasonEl = document.getElementById('last-cleanup-reason');
                if (cleanupReasonEl) {
                    cleanupReasonEl.textContent = cleanup.reason || '-';
                }
                const cleanupTargetEl = document.getElementById('last-cleanup-target');
                if (cleanupTargetEl) {
                    const target = cleanup.trim_target;
                    const floor = cleanup.effective_emergency_floor;
                    if (target !== undefined && target !== null) {
                        cleanupTargetEl.textContent = floor !== undefined && floor !== null
                            ? (String(target) + ' (floor ' + String(floor) + ')')
                            : String(target);
                    } else {
                        cleanupTargetEl.textContent = '-';
                    }
                }
            }
            
            if (data.security) {
                const violationsEl = document.getElementById('violations');
                if (violationsEl) {
                    violationsEl.textContent = data.security.recent_violations || 0;
                }
                const pendingReviewsEl = document.getElementById('pending-reviews');
                if (pendingReviewsEl) {
                    pendingReviewsEl.textContent = data.security.pending_reviews || 0;
                }
                const policyLoadedEl = document.getElementById('policy-loaded');
                if (policyLoadedEl) {
                    policyLoadedEl.textContent = data.security.policy_loaded ? 'Yes' : 'No';
                }
            }

            if (data.external) {
                renderExternalActivity(data.external);
            }
        }

        function externalEscape(value) {
            if (value === undefined || value === null) return '';
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function externalFormatTime(value) {
            if (!value) return 'Never';
            const dt = new Date(value);
            if (Number.isNaN(dt.getTime())) return externalEscape(value);
            return externalEscape(dt.toLocaleString());
        }

        function externalBadgeState(status) {
            switch (status) {
                case 'active_recently':
                    return {label: 'Active recently', className: 'badge success'};
                case 'gateway_ready':
                    return {label: 'Gateway ready', className: 'badge warning'};
                case 'idle':
                    return {label: 'Idle', className: 'badge'};
                case 'never':
                    return {label: 'No sessions', className: 'badge'};
                default:
                    return {label: 'Waiting', className: 'badge'};
            }
        }

        function externalStorageBadgeState(hintLevel) {
            const hl = String(hintLevel || '').trim();
            if (hl === 'mirror_active') return {label: 'Data mirror on', className: 'badge success'};
            if (hl === 'removable_present') return {label: 'USB / removable', className: 'badge warning'};
            return {label: 'Local only', className: 'badge'};
        }

        function externalMoltbookSummarySourceLabel(source) {
            switch (source) {
                case 'session_summary':
                    return 'Session readout';
                case 'latest_finding':
                    return 'Latest captured text';
                default:
                    return 'Readout';
            }
        }

        function externalHumanizeStopReason(reason) {
            const raw = String(reason || '').trim();
            if (!raw) return '';
            if (raw === 'completed') return 'Completed planned scan';
            if (raw === 'page_budget') return 'Stopped at page budget';
            if (raw === 'step_budget') return 'Stopped at step budget';
            if (raw.startsWith('navigation_error:')) {
                return 'Navigation error: ' + raw.split(':').slice(1).join(':');
            }
            return raw.replace(/_/g, ' ');
        }

        function renderExternalActivity(external) {
            const moltbook = external.moltbook || {};
            const openclaw = external.openclaw || {};
            const storage = external.storage || {};

            const moltbookBadge = externalBadgeState(moltbook.status);
            const moltbookBadgeEl = document.getElementById('external-moltbook-badge');
            if (moltbookBadgeEl) {
                moltbookBadgeEl.className = moltbookBadge.className;
                moltbookBadgeEl.textContent = moltbookBadge.label;
            }

            const openclawBadge = externalBadgeState(openclaw.status);
            const openclawBadgeEl = document.getElementById('external-openclaw-badge');
            if (openclawBadgeEl) {
                openclawBadgeEl.className = openclawBadge.className;
                openclawBadgeEl.textContent = openclawBadge.label;
            }

            const moltbookLines = [];
            if (moltbook.last_seen_at) {
                moltbookLines.push('<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">Last seen: ' + externalFormatTime(moltbook.last_seen_at) + '</div>');
            }
            if (moltbook.goal) {
                moltbookLines.push('<div><strong>Goal:</strong> ' + externalEscape(moltbook.goal) + '</div>');
            }
            if (moltbook.summary) {
                const summaryLabel = externalMoltbookSummarySourceLabel(moltbook.summary_source);
                moltbookLines.push('<div style="margin-top: 8px;"><strong>' + externalEscape(summaryLabel) + ':</strong> ' + externalEscape(moltbook.summary) + '</div>');
            }
            if (moltbook.latest_snippet && (!moltbook.summary || moltbook.latest_snippet !== moltbook.summary)) {
                moltbookLines.push('<div style="margin-top: 8px; font-size: 12px; color: var(--text-secondary);"><strong>Observed excerpt:</strong> ' + externalEscape(moltbook.latest_snippet) + '</div>');
            }
            const moltbookMeta = [];
            if (moltbook.readout_quality && moltbook.readout_quality !== 'none') {
                moltbookMeta.push('Readout: ' + externalEscape(moltbook.readout_quality));
            }
            const stopLabel = externalHumanizeStopReason(moltbook.stop_reason);
            if (stopLabel) moltbookMeta.push('Ended: ' + externalEscape(stopLabel));
            if (moltbook.pages_visited || moltbook.step_count) {
                moltbookMeta.push(
                    'Coverage: ' +
                    externalEscape(moltbook.pages_visited || 0) +
                    ' page(s), ' +
                    externalEscape(moltbook.step_count || 0) +
                    ' step(s)'
                );
            }
            if (moltbook.latest_url) moltbookMeta.push('Last URL: ' + externalEscape(moltbook.latest_url));
            if (moltbookMeta.length) {
                moltbookLines.push('<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">' + moltbookMeta.join(' | ') + '</div>');
            }
            if (!moltbookLines.length) {
                moltbookLines.push('<em style="color: var(--text-secondary);">No MoltBook sessions recorded yet. Start a bounded MoltBook browse and this panel will show goal, readout, and captured text.</em>');
            }
            const moltbookDetailsEl = document.getElementById('external-moltbook-details');
            if (moltbookDetailsEl) {
                moltbookDetailsEl.innerHTML = moltbookLines.join('');
            }

            const openclawLines = [];
            const gatewayLabel = (openclaw.gateway_host || '127.0.0.1') + ':' + (openclaw.gateway_port || 18789);
            openclawLines.push(
                '<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">Gateway ' +
                externalEscape(gatewayLabel) +
                ' is ' +
                (openclaw.gateway_reachable ? '<span style="color: var(--success);">reachable</span>' : '<span style="color: var(--text-secondary);">not reachable</span>') +
                '</div>'
            );
            if (openclaw.updated_at) {
                openclawLines.push('<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">Last activity: ' + externalFormatTime(openclaw.updated_at) + '</div>');
            }
            const openclawMeta = [];
            if (openclaw.request_count !== undefined && openclaw.request_count !== null) openclawMeta.push('Requests: ' + externalEscape(openclaw.request_count));
            if (openclaw.last_model) openclawMeta.push('Model: ' + externalEscape(openclaw.last_model));
            if (openclaw.last_status) openclawMeta.push('Status: ' + externalEscape(openclaw.last_status));
            if (openclawMeta.length) {
                openclawLines.push('<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">' + openclawMeta.join(' | ') + '</div>');
            }
            if (openclaw.last_request_preview) {
                openclawLines.push('<div><strong>Latest user message:</strong> ' + externalEscape(openclaw.last_request_preview) + '</div>');
            }
            if (openclaw.last_reply_preview) {
                openclawLines.push('<div style="margin-top: 8px;"><strong>Latest reply:</strong> ' + externalEscape(openclaw.last_reply_preview) + '</div>');
            }
            if (openclaw.last_error) {
                openclawLines.push('<div style="margin-top: 8px; color: var(--warning);"><strong>Last error:</strong> ' + externalEscape(openclaw.last_error) + '</div>');
            }
            if (openclaw.recent_requests && openclaw.recent_requests.length) {
                const recentHtml = openclaw.recent_requests.map(function(item) {
                    const bits = [];
                    if (item.ts) bits.push(externalFormatTime(item.ts));
                    if (item.status) bits.push(externalEscape(item.status));
                    if (item.model) bits.push(externalEscape(item.model));
                    let html = '<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border);">';
                    if (bits.length) {
                        html += '<div style="font-size: 11px; color: var(--text-secondary);">' + bits.join(' | ') + '</div>';
                    }
                    if (item.message_preview) {
                        html += '<div style="margin-top: 4px;"><strong>In:</strong> ' + externalEscape(item.message_preview) + '</div>';
                    }
                    if (item.reply_preview) {
                        html += '<div style="margin-top: 4px;"><strong>Out:</strong> ' + externalEscape(item.reply_preview) + '</div>';
                    }
                    return html + '</div>';
                }).join('');
                openclawLines.push('<div style="margin-top: 10px;"><div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary); margin-bottom: 4px;">Recent bridge traffic</div>' + recentHtml + '</div>');
            } else if (!openclaw.last_request_preview) {
                openclawLines.push('<em style="color: var(--text-secondary);">No OpenClaw requests recorded yet. After restart, this panel will fill as traffic hits /v1/chat/completions.</em>');
            }
            const openclawDetailsEl = document.getElementById('external-openclaw-details');
            if (openclawDetailsEl) {
                openclawDetailsEl.innerHTML = openclawLines.join('');
            }

            const storageBadge = externalStorageBadgeState(storage.hint_level);
            const storageBadgeEl = document.getElementById('external-storage-badge');
            if (storageBadgeEl) {
                storageBadgeEl.className = storageBadge.className;
                storageBadgeEl.textContent = storageBadge.label;
            }
            const storageLines = [];
            if (storage.external_data_mirror_active && storage.external_data_mirror_path) {
                storageLines.push('<div><strong>External data dir:</strong> ' + externalEscape(String(storage.external_data_mirror_path)) + '</div>');
            }
            const vols = storage.removable_volumes || [];
            if (vols.length) {
                storageLines.push('<div style="margin-top: 8px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-secondary);">Detected volumes</div>');
                vols.forEach(function(v) {
                    const mp = externalEscape(String(v.mountpoint || ''));
                    const fg = v.free_gb != null ? externalEscape(String(v.free_gb)) : '?';
                    const tg = v.total_gb != null ? externalEscape(String(v.total_gb)) : '?';
                    storageLines.push('<div style="margin-top: 6px;">' + mp + ' · ~' + fg + ' GB free · ' + tg + ' GB total</div>');
                });
                storageLines.push('<div style="margin-top: 10px; font-size: 11px; color: var(--text-secondary);">To use for Project Guardian data: configure <code style="font-size: 11px;">config/external_storage.json</code> or set <code style="font-size: 11px;">ELYSIA_THUMB_DRIVE</code> / ELYSIA_MEMORY marker.</div>');
            } else if (!storage.external_data_mirror_active) {
                storageLines.push('<em style="color: var(--text-secondary);">No removable volumes matched at startup (or none reported). Plug in a USB stick and restart to refresh; mirror path requires config.</em>');
            }
            const storageDetailsEl = document.getElementById('external-storage-details');
            if (storageDetailsEl) {
                storageDetailsEl.innerHTML = storageLines.length ? storageLines.join('') : '<em style="color: var(--text-secondary);">Unified system did not expose storage snapshot yet.</em>';
            }
        }

        // addLog function moved to top of script for early availability

        // Make all control functions globally accessible
        window.pauseLoop = function() {
            addLog('Pause requested...', 'info');
            fetch('/api/control/pause', { method: 'POST' })
                .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
                .then(function(o) { addLog(o.ok ? 'Loop paused' : ('Pause: ' + (o.data.message || o.data.error || 'failed')), o.ok ? 'info' : 'warning'); })
                .catch(function(err) { addLog('Pause error: ' + err, 'error'); });
        };

        window.resumeLoop = function() {
            addLog('Resume requested...', 'info');
            fetch('/api/control/resume', { method: 'POST' })
                .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
                .then(function(o) { addLog(o.ok ? 'Loop resumed' : ('Resume: ' + (o.data.message || o.data.error || 'failed')), o.ok ? 'info' : 'warning'); })
                .catch(function(err) { addLog('Resume error: ' + err, 'error'); });
        };

        window.createSnapshot = function() {
            fetch('/api/memory/snapshot', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) { addLog('Snapshot created: ' + (data.path || 'success'), 'info'); })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.refreshAutonomyStatus = function() {
            fetch('/api/autonomy')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const cb = document.getElementById('autonomy-enabled');
                    const statusEl = document.getElementById('autonomy-status');
                    const lastEl = document.getElementById('autonomy-last');
                    if (cb) cb.checked = data.enabled;
                    if (statusEl) statusEl.textContent = data.enabled ? 'Active' : 'Disabled';
                    if (lastEl) {
                        const last = data.last;
                        if (last && last.executed) {
                            lastEl.textContent = 'Last: ' + (last.action || '') + ' - ' + (last.reason || '').substring(0, 40);
                        } else {
                            lastEl.textContent = 'Last: -';
                        }
                    }
                })
                .catch(function() {});
        };
        window.toggleAutonomy = function(enabled) {
            fetch('/api/autonomy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog('Autonomy ' + (data.enabled ? 'enabled' : 'disabled'), 'info');
                    window.refreshAutonomyStatus();
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.suggestNextAction = function() {
            fetch('/api/next-action')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const div = document.getElementById('next-action-display');
                    const execBtn = document.getElementById('execute-next-btn');
                    if (!div) return;
                    if (data.error) {
                        div.innerHTML = '<span style="color: var(--danger);">' + data.error + '</span>';
                        if (execBtn) execBtn.style.display = 'none';
                        return;
                    }
                    let html = '<strong>Action:</strong> ' + (data.action || 'none') + '<br>';
                    html += '<strong>Source:</strong> ' + (data.source || '-') + '<br>';
                    html += '<strong>Reason:</strong> ' + (data.reason || '-') + '<br>';
                    if (data.ask_user_question) {
                        html += '<strong style="color: var(--accent);">Ask operator:</strong> ' + (data.ask_user_question || '') + ' ';
                        html += '<button type="button" onclick="ackOperatorQuestion()" style="margin-left:4px; font-size:10px;">Ack</button><br>';
                    }
                    if (data.override_reason) {
                        html += '<span style="color: var(--text-secondary); font-size: 11px;">Governor override: ' + (data.override_reason || '') + '</span><br>';
                    }
                    if (data.candidates_count > 1) {
                        html += '<span style="color: var(--text-secondary); font-size: 11px;">' + data.candidates_count + ' candidates</span>';
                    }
                    div.innerHTML = html;
                    if (execBtn) {
                        execBtn.style.display = (data.can_auto_execute && data.action) ? 'inline-block' : 'none';
                        execBtn.onclick = function() {
                            if (data.action === 'consider_learning') {
                                fetch('/api/learning/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: 'reddit', query: 'MachineLearning', max_items: 2 }) })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) { addLog(d.success ? 'Learning started' : (d.error || 'Failed'), d.success ? 'info' : 'error'); });
                            } else if (data.action === 'consider_dream_cycle') {
                                fetch('/api/control/dream-cycle', { method: 'POST' })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) { addLog('Dream cycle: ' + (d.dream_thoughts ? d.dream_thoughts.join('; ') : 'triggered'), 'info'); });
                            } else {
                                fetch('/api/autonomy/execute-cycle', { method: 'POST' })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) {
                                        addLog(d.executed ? 'Executed: ' + (d.action || '') : (d.reason || d.error || 'Not executed'), d.executed ? 'info' : 'warning');
                                        if (d.ask_user_question) addLog('Ask operator: ' + d.ask_user_question, 'info');
                                    });
                            }
                            suggestNextAction();
                        };
                    }
                    addLog('Next action: ' + (data.action || 'none'), 'info');
                })
                .catch(function(err) {
                    const div = document.getElementById('next-action-display');
                    if (div) div.innerHTML = '<span style="color: var(--danger);">Error: ' + err + '</span>';
                });
        };
        window.executeNextAction = function() { /* Set by suggestNextAction */ };

        window.ackOperatorQuestion = function() {
            fetch('/api/operator/ack-question', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    addLog(d.success ? 'Operator question acknowledged' : (d.error || 'Failed'), d.success ? 'info' : 'error');
                    suggestNextAction();
                })
                .catch(function(err) { addLog('Ack error: ' + err, 'error'); });
        };

        window.speakMessage = function() {
            const el = document.getElementById('speak-text');
            const text = (el && el.value) ? String(el.value).trim() : '';
            const mode = document.getElementById('speak-mode').value;
            if (!text) {
                addLog('Enter text to speak', 'warning');
                return;
            }
            fetch('/api/speak', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, mode: mode })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog(data.success ? 'Speaking: ' + text.substring(0, 40) + '...' : (data.error || 'Speak failed'), data.success ? 'info' : 'error');
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.triggerDreamCycle = function() {
            fetch('/api/control/dream-cycle', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog(data.success ? 'Dream cycle completed' : (data.message || 'Dream cycle triggered'), data.success ? 'info' : 'warning');
                    if (data.dream_thoughts && data.dream_thoughts.length) {
                        data.dream_thoughts.forEach(function(t) { addLog('[Dream] ' + t, 'info'); });
                    }
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.submitTask = function() {
            const code = document.getElementById('task-code').value;
            const priority = parseInt(document.getElementById('task-priority').value);
            
            fetch('/api/tasks/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, priority: priority })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) { 
                addLog('Task submitted: ' + (data.task_id || 'success'), 'info');
                if (typeof window.refreshTaskQueue === 'function') window.refreshTaskQueue();
            })
            .catch(function(err) { 
                addLog('Error: ' + err, 'error'); 
            });
        };

        window._escapeHtml = function(s) {
            if (s === undefined || s === null) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        };

        window.openTabAndFocus = function(tabName, elementId) {
            if (typeof window.showTab === 'function') window.showTab(tabName);
            setTimeout(function() {
                const el = document.getElementById(elementId);
                if (el) {
                    try { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
                    if (typeof el.focus === 'function') {
                        try { el.focus(); } catch (_) {}
                    }
                }
            }, 120);
        };

        window.quickFindOpportunities = function() {
            if (typeof window.showTab === 'function') window.showTab('workbench');
            if (typeof window.refreshWorkbench === 'function') window.refreshWorkbench();
            setTimeout(function() {
                const el = document.getElementById('workbench-opportunities');
                if (el) {
                    try { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
                }
            }, 160);
        };

        window.quickShowChanges = function() {
            if (typeof window.showTab === 'function') window.showTab('workbench');
            if (typeof window.refreshWorkbench === 'function') window.refreshWorkbench();
            setTimeout(function() {
                const el = document.getElementById('workbench-artifacts');
                if (el) {
                    try { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
                }
            }, 160);
        };

        window.quickLearnFrom = function(platform) {
            if (typeof window.showTab === 'function') window.showTab('learning');
            const select = document.getElementById('learning-platform');
            const query = document.getElementById('learning-query');
            const result = document.getElementById('learning-results');
            const defaults = {
                twitter: {
                    query: 'AI agents, automation pain point',
                    message: 'Ready to learn from X. Adjust the query if needed, then click "Start Learning".'
                },
                chatgpt: {
                    query: 'operator-ready offers, next steps',
                    message: 'Ready to mine ChatGPT conversations for useful goals and offers.'
                },
                web: {
                    query: 'https://example.com/article',
                    message: 'Paste one or more URLs, then click "Start Learning".'
                }
            };
            const preset = defaults[platform] || { query: '', message: 'Learning ready.' };
            if (select) select.value = platform;
            if (query) query.value = preset.query;
            if (result) {
                result.innerHTML = '<div style="color: var(--text-secondary);">' + window._escapeHtml(preset.message) + '</div>';
            }
            setTimeout(function() {
                if (query) {
                    try { query.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) {}
                    try { query.focus(); query.select(); } catch (_) {}
                }
            }, 140);
            if (platform === 'twitter' && typeof window.refreshLinkedAccounts === 'function') {
                window.refreshLinkedAccounts();
            }
        };

        window.quickAskElysia = function(prefill) {
            const input = document.getElementById('dashboard-quick-ask');
            const result = document.getElementById('dashboard-quick-answer');
            const message = String(prefill || (input && input.value) || '').trim();
            if (!message) {
                if (result) result.innerHTML = '<span style="color: var(--warning);">Enter a question first.</span>';
                if (input) input.focus();
                return;
            }
            if (input) input.value = message;
            if (result) result.innerHTML = '<span style="color: var(--warning);">Thinking...</span>';
            const controlInput = document.getElementById('api-chat-message');
            if (controlInput) controlInput.value = message;
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, conversation_id: window.getApiChatConversationId() })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const reply = data.reply || data.response || '(no reply)';
                        if (data.conversation_id) window.setApiChatConversationId(data.conversation_id);
                        const lab = document.getElementById('api-chat-conv-label');
                        if (lab && data.conversation_id) lab.textContent = data.conversation_id;
                        if (result) result.textContent = reply;
                        if (window.addLog) addLog('Quick ask answered', 'info');
                        const controlResult = document.getElementById('api-chat-result');
                        if (controlResult && typeof window.renderApiChatHistory === 'function') {
                            window.renderApiChatHistory(data.history || [
                                { role: 'user', content: message },
                                { role: 'assistant', content: reply }
                            ]);
                        } else if (controlResult) {
                            controlResult.textContent = reply;
                        }
                    } else {
                        const err = data.error || 'No reply available';
                        if (result) result.innerHTML = '<span style="color: var(--danger);">' + window._escapeHtml(err) + '</span>';
                        if (window.addLog) addLog('Quick ask failed: ' + err, 'error');
                    }
                })
                .catch(function(err) {
                    if (result) result.innerHTML = '<span style="color: var(--danger);">' + window._escapeHtml(String(err)) + '</span>';
                    if (window.addLog) addLog('Quick ask error: ' + err, 'error');
                });
        };

        window.ELYSIA_CP_CONV_LS = 'elysia_control_panel_conversation_id';
        window.getApiChatConversationId = function() {
            try {
                var id = localStorage.getItem(window.ELYSIA_CP_CONV_LS);
                if (id && String(id).trim()) return String(id).trim();
            } catch (_) {}
            return 'control_panel';
        };
        window.setApiChatConversationId = function(id) {
            try {
                if (id) localStorage.setItem(window.ELYSIA_CP_CONV_LS, String(id));
            } catch (_) {}
        };

        window.renderApiChatHistory = function(history) {
            const el = document.getElementById('api-chat-result');
            if (!el) return;
            const rows = Array.isArray(history) ? history : [];
            if (!rows.length) {
                el.innerHTML = '<em style="color: var(--text-secondary);">Start a conversation with Elysia.</em>';
                return;
            }
            el.innerHTML = rows.map(function(row) {
                const role = String(row.role || '').toLowerCase() === 'user' ? 'You' : 'Elysia';
                const color = role === 'You' ? 'var(--accent)' : 'var(--secondary)';
                return '<div style="margin-bottom: 8px;"><strong style="color:' + color + ';">' +
                    role + ':</strong> ' + window._escapeHtml(row.content || '') + '</div>';
            }).join('');
        };


        window._selectedSelfImprovementProposalId = '';

        window.refreshBrainTrace = function() {
            var el = document.getElementById('brain-trace-summary');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/brain/trace/latest')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data || data.trace_exists === false) {
                        el.textContent = data && data.message ? data.message : 'No brain trace has been recorded yet.';
                        return;
                    }
                    var t = data.trace || data;
                    el.textContent = [
                        'ID: ' + (t.brain_pipeline_id || data.brain_pipeline_id || '—'),
                        'Risk: ' + (t.risk_level || data.risk_level || '—'),
                        'Dry run: ' + String(t.dry_run != null ? t.dry_run : data.brain_dry_run),
                        'Transitions: ' + (t.transition_count || data.brain_transition_count || 0)
                    ].join('\n');
                })
                .catch(function(err) { el.textContent = 'Could not load trace: ' + err; });
        };
        window.refreshBrainTraceVisibility = window.refreshBrainTrace;

        window.renderSelfImprovementProposals = function(rows) {
            var el = document.getElementById('self-improvement-proposals-list');
            if (!el) return;
            rows = Array.isArray(rows) ? rows : [];
            if (!rows.length) { el.innerHTML = '<em>No self-improvement proposals yet.</em>'; return; }
            el.innerHTML = rows.map(function(p) {
                var pid = String(p.proposal_id || '').replace(/'/g, '');
                return '<div style="padding:6px 0;border-bottom:1px solid var(--border);">' +
                    '<button type="button" style="font-size:11px;" onclick="window._selectSelfImprovementProposal(\'' + pid + '\')">' +
                    window._escapeHtml(p.title || p.proposal_id || 'proposal') + '</button>' +
                    ' <span style="color:var(--text-secondary);font-size:10px;">' + window._escapeHtml(p.status || '') + '</span></div>';
            }).join('');
        };

        window._selectSelfImprovementProposal = function(pid) {
            window._selectedSelfImprovementProposalId = pid || '';
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var panel = document.getElementById('self-improvement-proposal-detail');
                    var body = document.getElementById('self-improvement-proposal-detail-body');
                    if (!panel || !body) return;
                    var p = data.proposal || {};
                    body.textContent = (p.title || '') + '\n' + (p.problem_summary || '');
                    panel.style.display = 'block';
                })
                .catch(function(err) { if (window.addLog) addLog('Proposal detail error: ' + err, 'warning'); });
        };

        window.refreshSelfImprovementProposals = function() {
            fetch('/api/self-improvement/proposals?limit=50')
                .then(function(r) { return r.json(); })
                .then(function(data) { if (data.success) window.renderSelfImprovementProposals(data.proposals || []); })
                .catch(function(err) { if (window.addLog) addLog('Proposals load error: ' + err, 'warning'); });
        };

        window.updateSelfImprovementProposalStatus = function(status) {
            var pid = window._selectedSelfImprovementProposalId;
            if (!pid) return;
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid) + '/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status })
            })
                .then(function(r) { return r.json(); })
                .then(function() { window.refreshSelfImprovementProposals(); })
                .catch(function(err) { if (window.addLog) addLog('Proposal status error: ' + err, 'warning'); });
        };

        window.exportSelfImprovementProposalPrompt = function(target) {
            var pid = window._selectedSelfImprovementProposalId;
            if (!pid) return;
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid) + '/export_prompt?target=' + encodeURIComponent(target || 'cursor'))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var pre = document.getElementById('self-improvement-prompt-export-text');
                    if (pre) pre.textContent = data.prompt || data.export || '';
                })
                .catch(function(err) { if (window.addLog) addLog('Export prompt error: ' + err, 'warning'); });
        };

        window.copySelfImprovementExportedPrompt = function() {
            var pre = document.getElementById('self-improvement-prompt-export-text');
            if (!pre || !pre.textContent) return;
            try {
                navigator.clipboard.writeText(pre.textContent);
                if (window.addLog) addLog('Copied export prompt', 'info');
            } catch (e) { if (window.addLog) addLog('Copy failed: ' + e, 'warning'); }
        };

        window.refreshMemoryRankingSummary = function() {
            var el = document.getElementById('memory-ranking-summary');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/memory/ranking/summary?limit=10')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.available) { el.textContent = data.message || 'No recent memories found to rank.'; return; }
                    el.textContent = 'Memories ranked: ' + (data.memory_count || 0) + ' · source: ' + (data.sample_source || '—');
                })
                .catch(function(err) { el.textContent = 'Could not load ranking: ' + err; });
        };

        window.refreshPromptContractStatus = function() {
            var el = document.getElementById('prompt-contract-status');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/prompt-contracts/status')
                .then(function(r) { return r.json(); })
                .then(function(data) { el.textContent = JSON.stringify(data, null, 2).slice(0, 1200); })
                .catch(function(err) { el.textContent = 'Could not load contracts: ' + err; });
        };

        window.refreshApiChatHistory = function() {
            var cid = encodeURIComponent(window.getApiChatConversationId());
            fetch('/api/chat/history?conversation_id=' + cid)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.conversation_id) {
                        window.setApiChatConversationId(data.conversation_id);
                        var lab = document.getElementById('api-chat-conv-label');
                        if (lab) lab.textContent = data.conversation_id;
                    }
                    if (data.success && typeof window.renderApiChatHistory === 'function') {
                        window.renderApiChatHistory(data.history || []);
                    }
                })
                .catch(function(err) {
                    if (window.addLog) addLog('Chat history load error: ' + err, 'warning');
                });
        };

        window.startNewApiChat = function() {
            fetch('/api/conversations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success && data.conversation_id) {
                        window.setApiChatConversationId(data.conversation_id);
                        var lab = document.getElementById('api-chat-conv-label');
                        if (lab) lab.textContent = data.conversation_id;
                        if (typeof window.renderApiChatHistory === 'function') window.renderApiChatHistory([]);
                        if (window.addLog) addLog('Started new conversation', 'info');
                    } else if (window.addLog) {
                        addLog('Could not start new conversation', 'warning');
                    }
                })
                .catch(function(err) {
                    if (window.addLog) addLog('New chat error: ' + err, 'error');
                });
        };

        window.refreshTaskQueue = function() {
            const el = document.getElementById('task-list');
            if (!el) return;
            el.innerHTML = '<em style="color: var(--text-secondary);">Loading…</em>';
            fetch('/api/tasks/list')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.success) {
                        el.textContent = data.error || 'Could not load tasks';
                        return;
                    }
                    const tasks = data.tasks || [];
                    if (tasks.length === 0) {
                        el.innerHTML = '<p style="color: var(--text-secondary);">No tasks to show. Loop queue depth: <strong>' +
                            (data.queue_size != null ? data.queue_size : 0) + '</strong>. Create tasks from the Control tab or add files under <code>TASKS/</code>.</p>';
                        return;
                    }
                    let html = '<ul style="list-style: none; padding: 0; margin: 0;">';
                    tasks.forEach(function(t) {
                        const title = t.name || t.task_id || t.file || 'Task';
                        const src = t.source ? (' <span style="color:var(--text-secondary);font-size:11px;">(' + window._escapeHtml(t.source) + ')</span>') : '';
                        html += '<li style="padding: 10px; margin: 8px 0; background: var(--bg-card); border-radius: 8px; border: 1px solid var(--border);">';
                        html += '<div><strong>' + window._escapeHtml(String(title)) + '</strong>' + src + '</div>';
                        if (t.status) html += '<div style="font-size: 12px; margin-top: 4px;">Status: ' + window._escapeHtml(String(t.status)) + '</div>';
                        if (t.category) html += '<div style="font-size: 11px; color: var(--text-secondary);">Category: ' + window._escapeHtml(String(t.category)) + '</div>';
                        if (t.priority !== undefined && t.priority !== null)
                            html += '<div style="font-size: 11px; color: var(--text-secondary);">Priority: ' + window._escapeHtml(String(t.priority)) + '</div>';
                        if (t.description)
                            html += '<div style="font-size: 12px; margin-top: 6px; white-space: pre-wrap;">' + window._escapeHtml(String(t.description)) + '</div>';
                        if (t.module) html += '<div style="font-size: 11px; margin-top: 4px;">Module: ' + window._escapeHtml(String(t.module)) + '</div>';
                        if (t.func) html += '<div style="font-size: 11px; color: var(--text-secondary);">Job: ' + window._escapeHtml(String(t.func)) + '</div>';
                        if (t.metadata && Object.keys(t.metadata).length)
                            html += '<div style="font-size: 10px; margin-top: 4px; font-family: monospace; color: var(--text-secondary);">' +
                                window._escapeHtml(JSON.stringify(t.metadata)) + '</div>';
                        html += '</li>';
                    });
                    html += '</ul>';
                    html += '<p style="margin-top: 14px; font-size: 12px; color: var(--text-secondary);">Loop queue depth: <strong>' +
                        (data.queue_size != null ? data.queue_size : 0) + '</strong> · Total rows: <strong>' + tasks.length + '</strong></p>';
                    el.innerHTML = html;
                })
                .catch(function(err) {
                    el.textContent = 'Error: ' + err;
                });
        };

        window.refreshWorkbench = function() {
            function setHtml(id, html) {
                const el = document.getElementById(id);
                if (el) el.innerHTML = html;
            }

            function fmt(text) {
                if (text === undefined || text === null) return '';
                return window._escapeHtml(text);
            }

            function emptyState(message) {
                return '<p style="color: var(--text-secondary); margin: 0;">' + fmt(message) + '</p>';
            }

            function metricCard(label, value) {
                return '<div style="padding: 12px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border); min-width: 140px;">' +
                    '<div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary);">' + fmt(label) + '</div>' +
                    '<div style="font-size: 22px; font-weight: 700; margin-top: 8px;">' + fmt(value) + '</div>' +
                    '</div>';
            }

            function listHtml(items, renderer, emptyMessage) {
                if (!items || items.length === 0) return emptyState(emptyMessage);
                return items.map(renderer).join('');
            }

            function salesLaunchHtml(item, compact) {
                if (!item || (!item.offer_name && (!item.docs || !item.docs.length))) {
                    return emptyState('No sales launch plan yet. Generate an offer pack to seed this panel.');
                }

                let html = '';
                if (item.recommended_path) {
                    html += '<div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary);">Recommended path</div>';
                    html += '<div style="font-weight: 700; margin-top: 4px;">' + fmt(item.recommended_path) + '</div>';
                }
                if (item.offer_name) {
                    html += '<div style="margin-top: 10px;"><strong>' + fmt(item.offer_name) + '</strong></div>';
                }
                if (item.offer_summary) {
                    html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.offer_summary) + '</div>';
                }
                if (item.price_points && item.price_points.length) {
                    html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">Pricing: ' + fmt(item.price_points.join(' | ')) + '</div>';
                }
                if (item.next_step) {
                    html += '<div style="margin-top: 8px; font-size: 12px;"><strong>Next:</strong> ' + fmt(item.next_step) + '</div>';
                }
                if (!compact && item.validation_prompt) {
                    html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);"><strong>Validation prompt:</strong> ' + fmt(item.validation_prompt) + '</div>';
                }
                if (item.docs && item.docs.length) {
                    html += '<div style="margin-top: 10px;">';
                    html += '<div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary); margin-bottom: 6px;">Launch docs</div>';
                    item.docs.forEach(function(doc) {
                        html += '<div style="padding: 10px; margin-bottom: 8px; border-radius: 8px; background: var(--bg-card); border: 1px solid var(--border);">';
                        html += '<div style="font-weight: 700;">' + fmt(doc.title || doc.file_name || 'Launch doc') + '</div>';
                        if (doc.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(doc.summary) + '</div>';
                        if (doc.path) html += '<div style="margin-top: 6px; font-size: 11px; color: var(--text-secondary);">' + fmt(doc.path) + '</div>';
                        html += '</div>';
                    });
                    html += '</div>';
                }
                return html || emptyState('No sales launch plan yet.');
            }

            function artifactMeta(item) {
                const bits = [];
                if (item.artifact_type) bits.push(fmt(item.artifact_type));
                if (item.created_at) bits.push(fmt(item.created_at));
                return bits.length ? '<div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">' + bits.join(' | ') + '</div>' : '';
            }

            setHtml('workbench-metrics', '<em style="color: var(--text-secondary);">Loading...</em>');
            setHtml('workbench-opportunities', emptyState('Loading opportunities...'));
            setHtml('workbench-active-tasks', emptyState('Loading active self-tasks...'));
            setHtml('workbench-successes', emptyState('Loading recent wins...'));
            setHtml('workbench-sales-launch', emptyState('Loading sales launch plan...'));
            setHtml('workbench-digests', emptyState('Loading learning digests...'));
            setHtml('workbench-improvements', emptyState('Loading improvement briefs...'));
            setHtml('workbench-artifacts', emptyState('Loading artifacts...'));
            setHtml('dashboard-sales-launch', emptyState('Loading sales launch plan...'));

            fetch('/api/workbench/summary')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.success) throw new Error(data.error || 'Could not load workbench');

                    const wb = data.workbench || {};
                    const counts = wb.counts || {};
                    const opportunities = wb.top_opportunities || [];
                    const activeTasks = wb.active_self_tasks || [];
                    const recentSuccesses = wb.recent_successes || [];
                    const salesLaunch = wb.sales_launch || {};
                    const digests = wb.learning_digests || [];
                    const improvements = wb.improvement_briefs || [];
                    const artifacts = wb.recent_artifacts || [];

                    setHtml(
                        'workbench-metrics',
                        '<div style="display:flex; flex-wrap:wrap; gap:12px;">' +
                            metricCard('Opportunities', counts.opportunities_total || 0) +
                            metricCard('Active Self-Tasks', counts.active_self_tasks || 0) +
                            metricCard('Useful Outputs', counts.useful_outputs || 0) +
                            metricCard('Artifacts', counts.artifacts_total || 0) +
                            '</div>'
                    );

                    setHtml(
                        'workbench-opportunities',
                        listHtml(opportunities, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.title || 'Opportunity') + '</div>';
                            if (item.rationale) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.rationale) + '</div>';
                            const meta = [];
                            if (item.required_capability) meta.push('Capability: ' + fmt(item.required_capability));
                            if (item.difficulty) meta.push('Difficulty: ' + fmt(item.difficulty));
                            if (item.expected_value) meta.push('Value: ' + fmt(item.expected_value));
                            if (meta.length) html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">' + meta.join(' | ') + '</div>';
                            html += '</div>';
                            return html;
                        }, 'No opportunities yet. Generate a revenue shortlist or learning digest to seed this panel.')
                    );

                    setHtml(
                        'workbench-active-tasks',
                        listHtml(activeTasks, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.title || item.task_id || 'Self-task') + '</div>';
                            if (item.goal) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.goal) + '</div>';
                            const meta = [];
                            if (item.status) meta.push('Status: ' + fmt(item.status));
                            if (item.category) meta.push('Category: ' + fmt(item.category));
                            if (item.priority !== undefined && item.priority !== null) meta.push('Priority: ' + fmt(item.priority));
                            if (meta.length) html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">' + meta.join(' | ') + '</div>';
                            html += '</div>';
                            return html;
                        }, 'No active self-tasks right now.')
                    );

                    setHtml(
                        'workbench-successes',
                        listHtml(recentSuccesses, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.title || item.task_id || 'Useful output') + '</div>';
                            if (item.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.summary) + '</div>';
                            html += artifactMeta(item);
                            html += '</div>';
                            return html;
                        }, 'No successful artifacts yet.')
                    );

                    setHtml(
                        'workbench-sales-launch',
                        salesLaunchHtml(salesLaunch, false)
                    );

                    setHtml(
                        'workbench-digests',
                        listHtml(digests, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.headline || 'Learning digest') + '</div>';
                            if (item.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.summary) + '</div>';
                            if (item.top_insights && item.top_insights.length) {
                                html += '<div style="margin-top: 8px; font-size: 12px;"><strong>Top insights:</strong> ' + fmt(item.top_insights.join(' | ')) + '</div>';
                            }
                            if (item.recommended_followup_tasks && item.recommended_followup_tasks.length) {
                                html += '<div style="margin-top: 6px; font-size: 11px; color: var(--text-secondary);">Next: ' + fmt(item.recommended_followup_tasks.join(', ')) + '</div>';
                            }
                            html += artifactMeta(item);
                            html += '</div>';
                            return html;
                        }, 'No learning digests yet.')
                    );

                    setHtml(
                        'workbench-improvements',
                        listHtml(improvements, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.headline || 'Improvement brief') + '</div>';
                            if (item.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.summary) + '</div>';
                            if (item.key_points && item.key_points.length) {
                                html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">' + fmt(item.key_points.join(' | ')) + '</div>';
                            }
                            html += artifactMeta(item);
                            html += '</div>';
                            return html;
                        }, 'No improvement briefs yet.')
                    );

                    setHtml(
                        'workbench-artifacts',
                        listHtml(artifacts, function(item) {
                            let html = '<div style="padding: 12px; margin-bottom: 10px; border-radius: 10px; background: var(--bg-dark); border: 1px solid var(--border);">';
                            html += '<div style="font-weight: 700;">' + fmt(item.headline || item.file_name || 'Artifact') + '</div>';
                            if (item.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.summary) + '</div>';
                            html += artifactMeta(item);
                            html += '</div>';
                            return html;
                        }, 'No artifacts yet.')
                    );

                    if (opportunities.length) {
                        const item = opportunities[0];
                        let html = '<div><strong>' + fmt(item.title || 'Opportunity') + '</strong></div>';
                        if (item.rationale) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.rationale) + '</div>';
                        const meta = [];
                        if (item.required_capability) meta.push(fmt(item.required_capability));
                        if (item.expected_value) meta.push('Value: ' + fmt(item.expected_value));
                        if (meta.length) html += '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);">' + meta.join(' | ') + '</div>';
                        setHtml('dashboard-opportunity', html);
                    } else {
                        setHtml('dashboard-opportunity', emptyState('No opportunity shortlist yet.'));
                    }

                    if (artifacts.length) {
                        const item = artifacts[0];
                        let html = '<div><strong>' + fmt(item.headline || item.file_name || 'Artifact') + '</strong></div>';
                        if (item.summary) html += '<div style="margin-top: 6px; line-height: 1.5;">' + fmt(item.summary) + '</div>';
                        html += artifactMeta(item);
                        setHtml('dashboard-artifact', html);
                    } else {
                        setHtml('dashboard-artifact', emptyState('No recent artifacts yet.'));
                    }

                    setHtml('dashboard-sales-launch', salesLaunchHtml(salesLaunch, true));
                })
                .catch(function(err) {
                    const message = 'Workbench error: ' + err;
                    setHtml('workbench-metrics', '<span style="color: var(--danger);">' + fmt(message) + '</span>');
                    setHtml('workbench-opportunities', emptyState(message));
                    setHtml('workbench-active-tasks', emptyState(message));
                    setHtml('workbench-successes', emptyState(message));
                    setHtml('workbench-sales-launch', emptyState(message));
                    setHtml('workbench-digests', emptyState(message));
                    setHtml('workbench-improvements', emptyState(message));
                    setHtml('workbench-artifacts', emptyState(message));
                    setHtml('dashboard-opportunity', emptyState(message));
                    setHtml('dashboard-artifact', emptyState(message));
                    setHtml('dashboard-sales-launch', emptyState(message));
                    if (window.addLog) addLog(message, 'error');
                });
        };

        window.sendApiChat = function() {
            const msg = (document.getElementById('api-chat-message') || {}).value;
            const el = document.getElementById('api-chat-result');
            if (!msg) { if (el) el.textContent = 'Enter a message first.'; return; }
            if (el) el.textContent = 'Sending...';
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg, conversation_id: window.getApiChatConversationId() })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.conversation_id) {
                        window.setApiChatConversationId(data.conversation_id);
                        var lab = document.getElementById('api-chat-conv-label');
                        if (lab) lab.textContent = data.conversation_id;
                    }
                    if (data.success && typeof window.renderApiChatHistory === 'function') {
                        window.renderApiChatHistory(data.history || []);
                    } else if (el) {
                        el.textContent = data.reply || data.response || data.error || JSON.stringify(data);
                    }
                    addLog('Chat: ' + (data.success ? 'OK' : (data.error || '')), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Chat error: ' + err, 'error'); });
        };

        window.refreshWalletAccounts = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Loading wallet...';
            fetch('/api/wallet/accounts')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = JSON.stringify(data.balance || data.accounts || data, null, 2);
                    addLog(data.success ? 'Wallet accounts loaded' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Wallet list error: ' + err, 'error'); });
        };

        window.addWalletAccount = function() {
            const nameEl = document.getElementById('wallet-new-name');
            const idEl = document.getElementById('wallet-new-id');
            const el = document.getElementById('api-tools-result');
            const name = (nameEl && nameEl.value || '').trim();
            if (!name) { if (el) el.textContent = 'Enter a display name.'; return; }
            const idRaw = (idEl && idEl.value || '').trim();
            const body = { name: name, type: 'virtual', currency: 'USD', balance: 0 };
            if (idRaw) body.id = idRaw;
            if (el) el.textContent = 'Adding account...';
            fetch('/api/wallet/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = JSON.stringify(data, null, 2);
                    addLog(data.success ? ('Added account: ' + (data.account_id || '')) : (data.error || ''), data.success ? 'info' : 'error');
                    if (data.success && nameEl) nameEl.value = '';
                    if (data.success && idEl) idEl.value = '';
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Wallet add error: ' + err, 'error'); });
        };

        function renderPaymentProviders(pp) {
            var gEl = document.getElementById('payment-status-gumroad');
            var sEl = document.getElementById('payment-status-stripe');
            if (!gEl || !sEl) return;
            if (!pp) {
                gEl.textContent = '—';
                sEl.textContent = '—';
                return;
            }
            var g = pp.gumroad || {};
            var s = pp.stripe || {};
            var nl = String.fromCharCode(10);
            var gl = [];
            gl.push('Token in env: ' + (g.access_token_env ? 'yes' : 'no'));
            gl.push('Harvest client: ' + (g.harvest_client_bound ? 'bound' : 'not bound'));
            gl.push('Overall: ' + (g.summary || '—'));
            gEl.textContent = gl.join(nl);
            var sl = [];
            sl.push('Secret in env: ' + (s.secret_key_env ? 'yes' : 'no'));
            sl.push('Publishable in env: ' + (s.publishable_key_env ? 'yes' : 'no'));
            sl.push('Secret mode: ' + (s.secret_key_mode || '—'));
            sl.push('Publishable mode: ' + (s.publishable_key_mode || '—'));
            sl.push('Harvest client: ' + (s.harvest_client_bound ? 'bound' : 'not bound'));
            sl.push('Overall: ' + (s.summary || '—'));
            sEl.textContent = sl.join(nl);
        }

        window.refreshIncomeStatus = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Loading...';
            fetch('/api/income-status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    renderPaymentProviders(data.payment_providers);
                    if (el) el.textContent = JSON.stringify(data, null, 2);
                    addLog('Income status refreshed', 'info');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Income status error: ' + err, 'error'); });
        };

        window.runHarvestReport = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Running harvest report...';
            fetch('/api/harvest-report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.report !== undefined ? JSON.stringify(data.report, null, 2) : (data.error || JSON.stringify(data));
                    addLog(data.success ? 'Harvest report done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Harvest error: ' + err, 'error'); });
        };

        window.runResearchProposal = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Creating research proposal...';
            const topic = prompt('Research topic (or leave default):', 'AI safety') || 'AI safety';
            fetch('/api/research-proposal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: topic }) })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.result !== undefined ? JSON.stringify(data.result, null, 2) : (data.error || JSON.stringify(data));
                    addLog(data.success ? 'Research proposal done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Research error: ' + err, 'error'); });
        };

        window.runPromptEvolution = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Running prompt evolution...';
            fetch('/api/prompts/evolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.error || ('Evolved: ' + (data.evolved_count || 0) + ', stats: ' + JSON.stringify(data.stats || {}));
                    addLog(data.success ? 'Prompt evolution done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Prompt evolution error: ' + err, 'error'); });
        };

        window.searchMemories = function() {
            const query = document.getElementById('memory-search').value;
            fetch('/api/memory/search?q=' + encodeURIComponent(query))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const results = document.getElementById('memory-results');
                    results.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        // Introspection Functions - make globally accessible
        window.refreshIntrospection = function() {
            addLog('Refreshing introspection data...', 'info');
            window.getComprehensiveReport();
            window.checkMemoryHealth();
            window.analyzeFocus();
            window.refreshIntrospectionDebug();
        };

        window.refreshIntrospectionDebug = function() {
            fetch('/api/introspection/debug')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const div = document.getElementById('introspection-debug');
                    if (!div) return;
                    if (!data.success || !data.debug) {
                        div.innerHTML = '<em>No data</em>';
                        return;
                    }
                    const d = data.debug;
                    if (d.note) {
                        div.innerHTML = '<em>' + d.note + '</em>';
                        return;
                    }
                    let html = '<strong>Suggested:</strong> ' + (d.suggested_action || 'none') + '<br>';
                    html += '<strong>Triggered:</strong> ' + (d.triggered ? 'yes' : 'no') + '<br>';
                    if (d.context && Object.keys(d.context).length) {
                        html += '<strong>Context:</strong><br>' + JSON.stringify(d.context, null, 2).split(String.fromCharCode(10)).join('<br>');
                    }
                    div.innerHTML = html;
                })
                .catch(function() {
                    const div = document.getElementById('introspection-debug');
                    if (div) div.innerHTML = '<em>Failed to load</em>';
                });
        };

        function _setText(id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        }

        /** Shared formatter for Insights + Dashboard API meter cards */
        window.renderApiGasMeterText = function(gm) {
            var brs = String.fromCharCode(10);
            if (!gm || gm.error)
                return (gm && gm.error) ? ('error: ' + gm.error) : '—';
            var parts = [gm.summary_text || '—'];
            var av = String(gm.availability_text || '').trim();
            if (av)
                parts.push(av);
            return parts.join(brs + brs);
        };

        window.refreshDashboardApiMeter = function() {
            fetch('/api/insights/api-meter')
                .then(function(r) { return r.json(); })
                .then(function(gm) {
                    _setText('dashboard-api-meter-summary', window.renderApiGasMeterText(gm));
                })
                .catch(function(err) {
                    _setText('dashboard-api-meter-summary', 'Could not load API meter: ' + (err && err.message ? err.message : String(err)));
                });
        };

        window._apiMeterChartHandles = {};
        window._destroyApiMeterCharts = function() {
            var H = window._apiMeterChartHandles || {};
            ['transport', 'router', 'tokens'].forEach(function(k) {
                try {
                    if (H[k] && typeof H[k].destroy === 'function') H[k].destroy();
                } catch (e) { /* ignore */ }
                H[k] = null;
            });
            window._apiMeterChartHandles = {};
        };

        window._fmtUptime = function(sec) {
            var s = parseFloat(sec) || 0;
            if (s < 60) return Math.round(s) + 's';
            if (s < 3600) return (Math.round(s / 60 * 10) / 10) + ' min';
            var h = Math.floor(s / 3600);
            var m = Math.floor((s % 3600) / 60);
            return h + 'h ' + m + 'm';
        };

        window._paletteRouter = ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#84cc16'];

        window._renderApiMeterGauges = function(gm) {
            var openaiEl = document.getElementById('api-meter-gauge-openai');
            var orEl = document.getElementById('api-meter-gauge-openrouter');
            var anEl = document.getElementById('api-meter-gauge-anthropic');
            if (!openaiEl || !orEl || !anEl) return;
            var ut = (gm.usable_cloud_routing || {}).openai || {};
            var oaOk = ut.usable_for_routing === true;
            openaiEl.innerHTML = '';
            var l1 = document.createElement('div');
            l1.className = 'api-meter-g-label';
            l1.style.color = oaOk ? 'var(--success)' : 'var(--danger)';
            l1.textContent = oaOk ? 'Routable' : 'Not routable';
            openaiEl.appendChild(l1);
            var tr = document.createElement('div');
            tr.className = 'api-meter-g-track';
            var fi = document.createElement('div');
            fi.className = 'api-meter-g-fill';
            fi.style.width = oaOk ? '100%' : '0%';
            fi.style.background = oaOk ? 'var(--success)' : 'var(--danger)';
            tr.appendChild(fi);
            openaiEl.appendChild(tr);
            var m1 = document.createElement('div');
            m1.className = 'api-meter-g-msg';
            m1.textContent = ut.routing_block_message || (oaOk ? 'Keys + guards allow OpenAI for routing.' : '');
            openaiEl.appendChild(m1);

            var pt = gm.provider_truth || {};
            var orU = (pt.openrouter || {}).usable === true;
            orEl.innerHTML = '';
            var l2 = document.createElement('div');
            l2.className = 'api-meter-g-label';
            l2.style.color = orU ? 'var(--success)' : 'var(--warning)';
            l2.textContent = orU ? 'Usable (reasoning)' : 'Not usable';
            orEl.appendChild(l2);
            var tr2 = document.createElement('div');
            tr2.className = 'api-meter-g-track';
            var fi2 = document.createElement('div');
            fi2.className = 'api-meter-g-fill';
            fi2.style.width = orU ? '100%' : '0%';
            fi2.style.background = orU ? 'var(--success)' : 'var(--warning)';
            tr2.appendChild(fi2);
            orEl.appendChild(tr2);
            var m2 = document.createElement('div');
            m2.className = 'api-meter-g-msg';
            m2.textContent = (pt.openrouter || {}).blocked_reason
                ? String((pt.openrouter || {}).blocked_reason)
                : (orU ? 'Key + policy allow OpenRouter for reasoning.' : 'Missing key, policy off, or not trusted.');
            orEl.appendChild(m2);

            var anU = (pt.anthropic || {}).usable === true;
            anEl.innerHTML = '';
            var l3 = document.createElement('div');
            l3.className = 'api-meter-g-label';
            l3.style.color = anU ? 'var(--success)' : 'var(--text-secondary)';
            l3.textContent = anU ? 'Trusted for reasoning' : 'Not trusted';
            anEl.appendChild(l3);
            var tr3 = document.createElement('div');
            tr3.className = 'api-meter-g-track';
            var fi3 = document.createElement('div');
            fi3.className = 'api-meter-g-fill';
            fi3.style.width = anU ? '100%' : '0%';
            fi3.style.background = anU ? 'var(--success)' : 'var(--bg-hover)';
            tr3.appendChild(fi3);
            anEl.appendChild(tr3);
            var m3 = document.createElement('div');
            m3.className = 'api-meter-g-msg';
            m3.textContent = (pt.anthropic || {}).blocked_reason
                ? String((pt.anthropic || {}).blocked_reason)
                : (anU ? 'ELYSIA_ANTHROPIC_REASONING_TRUST enabled.' : 'Requires key + ELYSIA_ANTHROPIC_REASONING_TRUST.');
            anEl.appendChild(m3);
        };

        window.refreshApiMeterTab = function() {
            fetch('/api/insights/api-meter')
                .then(function(r) { return r.json(); })
                .then(function(gm) {
                    var detail = document.getElementById('api-meter-detail-text');
                    if (gm.error) {
                        _setText('api-meter-stat-uptime', '—');
                        _setText('api-meter-stat-ok', '—');
                        _setText('api-meter-stat-fail', '—');
                        _setText('api-meter-stat-tokens', '—');
                        if (detail) detail.textContent = 'error: ' + gm.error;
                        _setText('api-meter-availability-block', '—');
                        window._destroyApiMeterCharts();
                        return;
                    }
                    var m = gm.meter || {};
                    var tt = m.transport_totals || {};
                    _setText('api-meter-stat-uptime', window._fmtUptime(m.uptime_sec));
                    _setText('api-meter-stat-ok', String(tt.calls_ok != null ? tt.calls_ok : 0));
                    _setText('api-meter-stat-fail', String(tt.calls_fail != null ? tt.calls_fail : 0));
                    _setText('api-meter-stat-tokens', String(tt.total_tokens_reported != null ? tt.total_tokens_reported : 0));
                    if (detail) detail.textContent = gm.summary_text || '—';
                    var avBlk = ((gm.availability_text || '').trim()) || '—';
                    _setText('api-meter-availability-block', avBlk);
                    window._renderApiMeterGauges(gm);

                    var fbT = document.getElementById('api-meter-fallback-transport');
                    var fbR = document.getElementById('api-meter-fallback-router');
                    var fbK = document.getElementById('api-meter-fallback-tokens');
                    if (fbT) { fbT.style.display = 'none'; fbT.textContent = ''; }
                    if (fbR) { fbR.style.display = 'none'; fbR.textContent = ''; }
                    if (fbK) { fbK.style.display = 'none'; fbK.textContent = ''; }

                    window._destroyApiMeterCharts();

                    if (typeof Chart === 'undefined') {
                        if (fbT) { fbT.style.display = 'block'; fbT.textContent = 'Chart.js not loaded — open browser network tab or allow cdn.jsdelivr.net.'; }
                        return;
                    }

                    try {
                        Chart.defaults.color = '#94a3b8';
                        Chart.defaults.borderColor = 'rgba(148, 163, 184, 0.25)';
                    } catch (e1) { /* ignore */ }

                    var transport = m.transport || {};
                    var labels = Object.keys(transport).sort();
                    if (labels.length === 0) labels = ['(no calls yet)'];
                    var okArr = labels.map(function(l) {
                        if (l === '(no calls yet)') return 0;
                        return parseInt((transport[l] || {}).calls_ok, 10) || 0;
                    });
                    var failArr = labels.map(function(l) {
                        if (l === '(no calls yet)') return 0;
                        return parseInt((transport[l] || {}).calls_fail, 10) || 0;
                    });
                    var tokArr = labels.map(function(l) {
                        if (l === '(no calls yet)') return 0;
                        return parseInt((transport[l] || {}).total_tokens, 10) || 0;
                    });

                    var ctxT = document.getElementById('api-meter-canvas-transport');
                    if (ctxT) {
                        window._apiMeterChartHandles.transport = new Chart(ctxT, {
                            type: 'bar',
                            data: {
                                labels: labels,
                                datasets: [
                                    { label: 'OK', data: okArr, backgroundColor: '#10b981', stack: 's' },
                                    { label: 'Fail', data: failArr, backgroundColor: '#ef4444', stack: 's' }
                                ]
                            },
                            options: {
                                indexAxis: 'y',
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    legend: { position: 'bottom', labels: { boxWidth: 12 } },
                                    title: { display: false }
                                },
                                scales: {
                                    x: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
                                    y: { stacked: true, ticks: { autoSkip: false } }
                                }
                            }
                        });
                    }

                    var rc = m.router_choices || {};
                    var rLabels = Object.keys(rc).sort(function(a, b) { return (rc[b] || 0) - (rc[a] || 0); });
                    var rData = rLabels.map(function(k) { return parseInt(rc[k], 10) || 0; });
                    var rSum = rData.reduce(function(a, b) { return a + b; }, 0);
                    var rCol = rLabels.map(function(_, i) {
                        return window._paletteRouter[i % window._paletteRouter.length];
                    });
                    if (rSum === 0) {
                        rLabels = ['No router picks yet'];
                        rData = [1];
                        rCol = ['#64748b'];
                    }
                    var ctxR = document.getElementById('api-meter-canvas-router');
                    if (ctxR) {
                        window._apiMeterChartHandles.router = new Chart(ctxR, {
                            type: 'doughnut',
                            data: {
                                labels: rLabels,
                                datasets: [{ data: rData, backgroundColor: rCol, borderWidth: 1 }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    legend: { position: 'right', labels: { boxWidth: 11, font: { size: 11 } } }
                                }
                            }
                        });
                    }

                    var ctxK = document.getElementById('api-meter-canvas-tokens');
                    if (ctxK) {
                        window._apiMeterChartHandles.tokens = new Chart(ctxK, {
                            type: 'bar',
                            data: {
                                labels: labels,
                                datasets: [{ label: 'Tokens', data: tokArr, backgroundColor: '#6366f1' }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: { legend: { display: false } },
                                scales: {
                                    y: { beginAtZero: true, ticks: { precision: 0 } },
                                    x: { ticks: { autoSkip: false, maxRotation: 45, minRotation: 0 } }
                                }
                            }
                        });
                    }
                })
                .catch(function(err) {
                    var detail = document.getElementById('api-meter-detail-text');
                    if (detail) detail.textContent = 'fetch error: ' + (err && err.message ? err.message : String(err));
                    _setText('api-meter-availability-block', '—');
                    window._destroyApiMeterCharts();
                });
        };

        window.refreshInsightsOverview = function() {
            fetch('/api/insights/overview?trace_lines=45&rag_lines=35')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    const pre = document.getElementById('insights-json-overview');
                    if (pre) pre.textContent = JSON.stringify(d, null, 2);
                    const sa = d.storage_alignment || {};
                    var brs = String.fromCharCode(10);
                    var stTxt = '';
                    if (sa.warnings && sa.warnings.length) {
                        stTxt = '⚠ ' + sa.warnings.join(brs + '⚠ ');
                    } else {
                        stTxt = 'Paths aligned (no warnings).';
                    }
                    stTxt += brs + 'learned: ' + (sa.learned_root || '—');
                    var extReach = 'n/a';
                    if (sa.configured_external_drive)
                        extReach = sa.configured_drive_root_exists ? 'yes' : 'no';
                    stTxt += brs + 'external_drive reachable: ' + extReach;
                    _setText('insights-storage-summary', stTxt);
                    const om = d.ollama_runtime || {};
                    var omTxt = '';
                    if (om.startup_error) {
                        omTxt = 'error: ' + om.startup_error;
                    } else {
                        omTxt = 'readiness: ' + (om.readiness_label || '—') + brs;
                        omTxt += 'effective: ' + (om.effective_model || '—');
                        if (om.env_model_override)
                            omTxt += brs + 'env: ' + om.env_model_override;
                        const st = om.startup || {};
                        omTxt += brs + 'reachable: ' + (st.ollama_reachable ? 'yes' : 'no') +
                            '  installed: ' + (st.model_installed ? 'yes' : 'no') +
                            '  health: ' + (st.startup_health_ok ? 'ok' : 'no');
                        if (st.startup_detail)
                            omTxt += brs + 'detail: ' + String(st.startup_detail).slice(0, 200);
                        if (om.config_file_primary)
                            omTxt += brs + 'config primary: ' + om.config_file_primary;
                        if (om.resolution_note)
                            omTxt += brs + om.resolution_note;
                        const th = st.installed_model_tags_head;
                        if (th && th.length)
                            omTxt += brs + 'tags: ' + th.join(', ');
                    }
                    _setText('insights-ollama-summary', omTxt || '—');
                    _setText('insights-api-meter-summary', window.renderApiGasMeterText(d.api_gas_meter || {}));
                    _setText('dashboard-api-meter-summary', window.renderApiGasMeterText(d.api_gas_meter || {}));
                    const sb = d.selfbuild || {};
                    if (!sb.error) {
                        const arts = sb.artifacts || {};
                        const ri = sb.rag_inject_effective || {};
                        const miss = Object.keys(arts).filter(function(k) { return !arts[k].exists; });
                        var br = String.fromCharCode(10);
                        var ragLine = (ri.top_k !== undefined)
                            ? br + 'RAG inject: top_k=' + ri.top_k + ' min_score=' + ri.min_score +
                              ' max_chars=' + ri.max_chars + ' index_rows≤' + ri.max_index_rows
                            : '';
                        var er = sb.embed_ram_pressure || {};
                        var ramHint = '';
                        if (er.host_ram_used_fraction != null && er.host_ram_used_fraction !== undefined && !er.error) {
                            ramHint = br + 'host RAM ~' + (Math.round(er.host_ram_used_fraction * 1000) / 10) + '%';
                            if (er.embed_cap_would_apply)
                                ramHint += ' (embed export chunks/batch capped per memory_pressure.json)';
                        }
                        _setText('insights-selfbuild-summary',
                            (sb.selfbuild_dir_exists ? 'dir: ok' : 'dir: missing') + br + 'learned: ' + (sb.learned_root || '') +
                            (miss.length ? br + 'missing: ' + miss.join(', ') : br + 'artifacts: ok') + ragLine + ramHint);
                    } else {
                        _setText('insights-selfbuild-summary', sb.error || 'error');
                    }
                    const m = d.mcp || {};
                    var br2 = String.fromCharCode(10);
                    _setText('insights-mcp-summary',
                        'sdk: ' + (m.mcp_sdk_installed ? 'yes' : 'no') + br2 +
                        'chat MCP: ' + (m.chat_mcp_capability_active ? 'on' : 'off') + br2 +
                        'allowlist: ' + (m.allowlist_exists ? (m.allowlist_enabled ? 'enabled' : 'present') : 'missing'));
                    const tr = d.llm_traces || {};
                    var br3 = String.fromCharCode(10);
                    _setText('insights-trace-summary',
                        tr.enabled ? ((tr.exists ? 'file ok' + br3 : 'file missing' + br3) + (tr.path || '')) : (tr.note || 'traces off'));
                    const rg = d.rag_unified_log || {};
                    var br4 = String.fromCharCode(10);
                    _setText('insights-rag-summary',
                        (rg.source_log ? ('from ' + rg.source_log + br4) : '') +
                        ((rg.lines && rg.lines.length) ? (rg.lines.length + ' lines') : (rg.note || 'no lines')));
                    const tl = document.getElementById('insights-trace-lines');
                    if (tl) tl.textContent = (tr.lines && tr.lines.length) ? tr.lines.join(String.fromCharCode(10)) : '—';
                    const rl = document.getElementById('insights-rag-lines');
                    if (rl) rl.textContent = (rg.lines && rg.lines.length) ? rg.lines.join(String.fromCharCode(10)) : '—';
                    const pb = d.parallel_brains || {};
                    var brz = String.fromCharCode(10);
                    var brainsTxt = 'unified router (mistral_decider): ' + (pb.unified_chat_llm_router_enabled ? 'on' : 'off');
                    if (pb.cloud_only_when_router_disabled)
                        brainsTxt += brz + '⚠ When off, operator chat uses cloud-only fallback (no local ordering).';
                    const uxs = pb.unified_route_scenarios || [];
                    brainsTxt += brz + brz + 'Unified try-order (sample scenarios):';
                    for (var i = 0; i < uxs.length && i < 6; i++) {
                        var row = uxs[i];
                        if (row.error) {
                            brainsTxt += brz + 'error: ' + row.error;
                            break;
                        }
                        brainsTxt += brz + row.id + ' [' + (row.route_task_type || '?') + ']: ' +
                            (row.try_order || []).join(' → ');
                    }
                    var mar = pb.multi_api_router || {};
                    if (mar.error)
                        brainsTxt += brz + brz + 'multi_api_router: ' + mar.error;
                    else if (mar.reasoning && mar.reasoning.chosen) {
                        brainsTxt += brz + brz + 'multi_api_router picks: reasoning→' + mar.reasoning.chosen +
                            ', autonomy_safe→' + ((mar.reasoning_autonomy_safe && mar.reasoning_autonomy_safe.chosen) || '—') +
                            ', embedding→' + ((mar.embedding && mar.embedding.chosen) || '—');
                    }
                    if (pb.orchestration_parallel_pipeline && pb.orchestration_parallel_pipeline.pipeline_id)
                        brainsTxt += brz + brz + 'parallel pipeline: ' + pb.orchestration_parallel_pipeline.pipeline_id;
                    _setText('insights-brains-summary', brainsTxt);
                    const mc = d.mission_clarity || {};
                    var mTxt = '';
                    if (mc.core_mission_excerpt)
                        mTxt = mc.core_mission_excerpt.slice(0, 280) + (mc.core_mission_excerpt.length > 280 ? '…' : '');
                    const fms = mc.focus_missions || [];
                    if (fms.length) {
                        mTxt += (mTxt ? brz + brz : '') + 'Focus (max 5):';
                        for (var j = 0; j < fms.length; j++) {
                            var fm = fms[j];
                            mTxt += brz + '• ' + (fm.title || fm.id || '') +
                                (fm.purpose ? ' — ' + String(fm.purpose).slice(0, 120) : '');
                        }
                    }
                    var samp = mc.merged_guidance_keywords_sample || [];
                    if (samp.length)
                        mTxt += brz + brz + 'Keywords (sample): ' + samp.slice(0, 18).join(', ');
                    var ca = mc.corpus_keyword_alignment || {};
                    if (ca.rows_scanned !== undefined)
                        mTxt += brz + brz + 'Corpus vs keywords: scanned=' + ca.rows_scanned +
                            ' aligned=' + ca.aligned_rows + ' misaligned=' + ca.misaligned_rows +
                            (ca.alignment_ratio !== undefined ? ' ratio=' + ca.alignment_ratio : '');
                    _setText('insights-mission-summary', mTxt || '—');
                    addLog('Insights overview refreshed', 'info');
                })
                .catch(function(err) {
                    addLog('Insights error: ' + err, 'error');
                    _setText('insights-json-overview', 'Error: ' + err);
                });
        };

        window.refreshInsightsTraces = function() {
            fetch('/api/insights/traces?lines=60')
                .then(function(r) { return r.json(); })
                .then(function(tr) {
                    const tl = document.getElementById('insights-trace-lines');
                    if (tl) tl.textContent = (tr.lines && tr.lines.length) ? tr.lines.join(String.fromCharCode(10)) : '—';
                    var br5 = String.fromCharCode(10);
                    _setText('insights-trace-summary',
                        tr.enabled ? ((tr.exists ? 'file ok' + br5 : 'file missing' + br5) + (tr.path || '')) : (tr.note || 'off'));
                    addLog('Trace tail reloaded', 'info');
                })
                .catch(function(err) { addLog('Trace tail error: ' + err, 'error'); });
        };

        window.refreshInsightsRagLog = function() {
            fetch('/api/insights/rag-log?lines=40')
                .then(function(r) { return r.json(); })
                .then(function(rg) {
                    const rl = document.getElementById('insights-rag-lines');
                    if (rl) rl.textContent = (rg.lines && rg.lines.length) ? rg.lines.join(String.fromCharCode(10)) : '—';
                    var br6 = String.fromCharCode(10);
                    _setText('insights-rag-summary',
                        (rg.source_log ? ('from ' + rg.source_log + br6) : '') +
                        ((rg.lines && rg.lines.length) ? (rg.lines.length + ' lines') : (rg.note || '—')));
                    addLog('RAG log tail reloaded', 'info');
                })
                .catch(function(err) { addLog('RAG log error: ' + err, 'error'); });
        };

        window.getComprehensiveReport = function() {
            fetch('/api/introspection/comprehensive')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success && data.report) {
                        const report = data.report;
                        const reportStr = typeof report === 'string' ? report : JSON.stringify(report, null, 2);
                        const lines = reportStr.split(String.fromCharCode(10));
                        
                        // Find identity section
                        let identityStart = -1;
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].indexOf('[Guardian Identity]') !== -1) {
                                identityStart = i;
                                break;
                            }
                        }
                        let identityEnd = lines.length;
                        for (let i = (identityStart >= 0 ? identityStart + 1 : 0); i < lines.length; i++) {
                            if (lines[i].charAt(0) === '[' && lines[i].indexOf('Guardian Identity') === -1) {
                                identityEnd = i;
                                break;
                            }
                        }
                        const identityText = identityStart >= 0 ? lines.slice(identityStart, identityEnd).join(String.fromCharCode(10)) : reportStr.substring(0, 1000);
                        const elId = document.getElementById('identity-summary');
                        if (elId) elId.textContent = identityText || reportStr.substring(0, 1000);
                        
                        // Find behavior section
                        let behaviorStart = -1;
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].indexOf('[Guardian Behavior]') !== -1) {
                                behaviorStart = i;
                                break;
                            }
                        }
                        let behaviorEnd = lines.length;
                        for (let i = (behaviorStart >= 0 ? behaviorStart + 1 : 0); i < lines.length; i++) {
                            if (lines[i].charAt(0) === '[' && lines[i].indexOf('Guardian Behavior') === -1) {
                                behaviorEnd = i;
                                break;
                            }
                        }
                        const behaviorText = behaviorStart >= 0 ? lines.slice(behaviorStart, behaviorEnd).join(String.fromCharCode(10)) : 'No behavior data available';
                        const elBeh = document.getElementById('behavior-report');
                        if (elBeh) elBeh.textContent = behaviorText;
                        
                        addLog('Comprehensive report loaded', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error loading comprehensive report: ' + err, 'error');
                    console.error(err);
                });
        };

        window.checkMemoryHealth = function() {
            fetch('/api/introspection/health')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const health = data.health || {};
                        const statusEl = document.getElementById('health-status');
                        const scoreEl = document.getElementById('health-score');
                        const totalEl = document.getElementById('health-total');
                        if (statusEl) statusEl.textContent = (health.status || 'unknown').toUpperCase();
                        if (scoreEl) scoreEl.textContent = ((health.health_score || 0) * 100).toFixed(1) + '%';
                        if (totalEl) totalEl.textContent = (health.total_memories !== undefined && health.total_memories !== null) ? health.total_memories : '-';
                        
                        const warningsDiv = document.getElementById('health-warnings');
                        if (warningsDiv) {
                            if (health.warnings && health.warnings.length > 0) {
                                warningsDiv.innerHTML = '<strong>Warnings:</strong><br>' + 
                                    health.warnings.map(function(w) { return 'Warning: ' + w; }).join('<br>');
                            } else {
                                warningsDiv.innerHTML = '<span style="color: #2ecc71;">No issues detected</span>';
                            }
                        }
                        
                        addLog('Memory health check completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error checking memory health: ' + err, 'error');
                    console.error(err);
                });
        };

        window.analyzeFocus = function() {
            fetch('/api/introspection/focus?hours=24')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const focus = data.focus || {};
                        const fp = document.getElementById('focus-primary');
                        const fa = document.getElementById('focus-activity');
                        const ft = document.getElementById('focus-trend');
                        const fm = document.getElementById('focus-period');
                        if (fp) fp.textContent = focus.primary_focus || '-';
                        if (fa) fa.textContent = (focus.activity_count !== undefined && focus.activity_count !== null) ? focus.activity_count : '-';
                        if (ft) ft.textContent = focus.priority_trend || '-';
                        if (fm) fm.textContent = focus.most_active_period || '-';
                        
                        const distDiv = document.getElementById('focus-distribution');
                        if (distDiv) {
                            if (focus.focus_distribution && Object.keys(focus.focus_distribution).length > 0) {
                                const distText = Object.entries(focus.focus_distribution)
                                    .map(function(entry) { return entry[0] + ': ' + entry[1]; })
                                    .join(String.fromCharCode(10));
                                distDiv.innerHTML = '<strong>Category Distribution:</strong><br><pre>' + distText + '</pre>';
                            } else {
                                distDiv.innerHTML = '<em>No focus distribution data</em>';
                            }
                        }
                        
                        addLog('Focus analysis completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error analyzing focus: ' + err, 'error');
                    console.error(err);
                });
        };

        window.findCorrelations = function() {
            const keyword = document.getElementById('correlation-keyword').value;
            if (!keyword) {
                addLog('Please enter a keyword', 'warning');
                return;
            }
            
            addLog('Finding correlations for: ' + keyword, 'info');
            fetch('/api/introspection/correlations?keyword=' + encodeURIComponent(keyword) + '&threshold=0.3')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const resultsDiv = document.getElementById('correlation-results');
                        if (data.correlations && data.correlations.length > 0) {
                            const html = data.correlations.map(function(corr) {
                                const score = (corr.correlation_score * 100).toFixed(1);
                                const timeDiff = corr.time_diff_hours.toFixed(1);
                                const keywords = corr.shared_keywords ? corr.shared_keywords.join(', ') : '';
                                return '<div style="margin: 10px 0; padding: 10px; background: var(--bg-card); border-radius: 8px; border-left: 3px solid var(--primary);">' +
                                    '<strong>Correlation Score:</strong> ' + score + '%<br>' +
                                    '<strong>Time Difference:</strong> ' + timeDiff + ' hours<br>' +
                                    '<strong>Memory 1:</strong> ' + (corr.memory1 || '').substring(0, 100) + '<br>' +
                                    '<strong>Memory 2:</strong> ' + (corr.memory2 || '').substring(0, 100) + '<br>' +
                                    '<strong>Shared Keywords:</strong> ' + keywords +
                                    '</div>';
                            }).join('');
                            resultsDiv.innerHTML = '<div><strong>Found ' + data.correlations.length + ' correlations:</strong></div>' + html;
                        } else {
                            resultsDiv.innerHTML = '<em>No correlations found for this keyword</em>';
                        }
                        addLog('Correlation analysis completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error finding correlations: ' + err, 'error');
                    console.error(err);
                });
        };

        // Initialize theme from localStorage (toggleTheme defined at top of script)
        (function() {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            document.body.setAttribute('data-theme', savedTheme);
        })();

        // Learning Functions - make globally accessible
        window.testRedditLearning = function() {
            addLog('Testing Reddit learning...', 'info');
            document.getElementById('learning-status').textContent = 'Testing Reddit API...';
            document.getElementById('learning-status').style.color = 'var(--warning)';
            
            fetch('/api/learning/test-reddit', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        document.getElementById('learning-status').textContent = 'Reddit learning test successful';
                        document.getElementById('learning-status').style.color = 'var(--success)';
                        addLog('Reddit learning test: ' + data.message, 'info');
                        window.refreshLearningStats();
                    } else {
                        document.getElementById('learning-status').textContent = 'Test failed: ' + (data.error || 'Unknown error');
                        document.getElementById('learning-status').style.color = 'var(--danger)';
                        addLog('Reddit learning test failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    document.getElementById('learning-status').textContent = 'Error: ' + err;
                    document.getElementById('learning-status').style.color = 'var(--danger)';
                        addLog('Error testing Reddit learning: ' + err, 'error');
                });
        };

        window.getLearningSummary = function() {
            addLog('Fetching learning summary...', 'info');
            fetch('/api/learning/summary')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const summary = data.summary;
                        document.getElementById('learning-articles').textContent = summary.total_articles || 0;
                        document.getElementById('learning-reddit').textContent = summary.reddit_posts || 0;
                        document.getElementById('learning-rss').textContent = summary.rss_entries || 0;
                        document.getElementById('learning-last').textContent = summary.last_learning || 'Never';
                        addLog('Learning summary loaded', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error fetching learning summary: ' + err, 'error');
                });
        };

        window.refreshLearningStats = function() {
            window.getLearningSummary();
        };

        window.refreshLearningSettings = function() {
            var cb = document.getElementById('learning-headless');
            if (!cb) return;
            fetch('/api/learning/settings')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    cb.checked = !!data.use_headless_browser;
                })
                .catch(function() { cb.checked = false; });
        };

        window.saveLearningHeadless = function(checked) {
            fetch('/api/learning/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ use_headless_browser: !!checked })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) addLog('Headless browser for web: ' + (data.use_headless_browser ? 'on' : 'off'), 'info');
                })
                .catch(function(err) { addLog('Failed to save setting: ' + err, 'error'); });
        };

        window.refreshLinkedAccounts = function() {
            fetch('/api/learning/linked-accounts')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var fb = document.getElementById('link-fb-status');
                    if (fb) { fb.textContent = (data.facebook ? 'Linked' : 'Not linked'); fb.style.color = data.facebook ? 'var(--success)' : 'var(--text-secondary)'; }
                    var tw = document.getElementById('link-twitter-status');
                    if (tw) { tw.textContent = (data.twitter ? 'Linked' : 'Not linked'); tw.style.color = data.twitter ? 'var(--success)' : 'var(--text-secondary)'; }
                })
                .catch(function() {
                    var fb = document.getElementById('link-fb-status'); if (fb) { fb.textContent = 'Not linked'; fb.style.color = 'var(--text-secondary)'; }
                    var tw = document.getElementById('link-twitter-status'); if (tw) { tw.textContent = 'Not linked'; tw.style.color = 'var(--text-secondary)'; }
                });
        };

        window.saveLinkFacebook = function() {
            var input = document.getElementById('link-fb-token');
            var token = input ? input.value : '';
            var statusEl = document.getElementById('link-fb-status');
            fetch('/api/learning/link-facebook', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (input) input.value = '';
                        addLog(data.message || (data.linked ? 'Facebook linked' : 'Token cleared'), 'info');
                        if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                    } else {
                        addLog('Link failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Link failed: ' + err, 'error');
                });
        };

        window.saveLinkTwitter = function() {
            var input = document.getElementById('link-twitter-token');
            var token = input ? input.value : '';
            fetch('/api/learning/link-twitter', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (input) input.value = '';
                        addLog(data.message || (data.linked ? 'X (Twitter) linked' : 'Token cleared'), 'info');
                        if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                    } else {
                        addLog('Link failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) { addLog('Link failed: ' + err, 'error'); });
        };

        window.refreshIncomeKeysStatus = function() {
            fetch('/api/settings/income-keys')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.success) return;
                    function fmt(eff, source, env, file, folder) {
                        var parts = [];
                        parts.push(eff ? 'active' : 'not set');
                        if (eff && source === 'api_keys_folder') parts.push('API keys folder');
                        else if (eff && source === 'env') parts.push('env');
                        else if (eff && source === 'config_file') parts.push('config file');
                        if (eff && folder && (env || file)) parts.push('folder overrides');
                        else if (eff && env && file) parts.push('env overrides file');
                        return parts.join(' · ');
                    }
                    var g = document.getElementById('income-gumroad-status');
                    var s = document.getElementById('income-stripe-status');
                    if (g) {
                        g.textContent = fmt(
                            data.gumroad_configured,
                            data.gumroad_effective_source,
                            data.gumroad_from_env,
                            data.gumroad_in_config_file,
                            data.gumroad_in_api_keys_folder
                        );
                        g.style.color = data.gumroad_configured ? 'var(--success)' : 'var(--text-secondary)';
                    }
                    if (s) {
                        s.textContent = fmt(
                            data.stripe_configured,
                            data.stripe_effective_source,
                            data.stripe_from_env,
                            data.stripe_in_config_file,
                            data.stripe_in_api_keys_folder
                        );
                        s.style.color = data.stripe_configured ? 'var(--success)' : 'var(--text-secondary)';
                    }
                })
                .catch(function() {
                    var g = document.getElementById('income-gumroad-status');
                    var s = document.getElementById('income-stripe-status');
                    if (g) { g.textContent = 'Could not load status'; g.style.color = 'var(--danger)'; }
                    if (s) { s.textContent = 'Could not load status'; s.style.color = 'var(--danger)'; }
                });
        };

        window.saveIncomeKeys = function() {
            var gt = document.getElementById('income-gumroad-token');
            var st = document.getElementById('income-stripe-token');
            var body = {};
            if (gt && gt.value.trim()) body.gumroad_access_token = gt.value.trim();
            if (st && st.value.trim()) body.stripe_secret_key = st.value.trim();
            if (Object.keys(body).length === 0) {
                addLog('Paste at least one new key before saving', 'warning');
                return;
            }
            fetch('/api/settings/income-keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (gt) gt.value = '';
                        if (st) st.value = '';
                        addLog(data.message || 'Income API keys saved to config file', 'info');
                        if (typeof window.refreshIncomeKeysStatus === 'function') window.refreshIncomeKeysStatus();
                    } else {
                        addLog('Save failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) { addLog('Save failed: ' + err, 'error'); });
        };

        window.clearIncomeKey = function(which) {
            var body = which === 'gumroad' ? { clear_gumroad: true } : { clear_stripe: true };
            fetch('/api/settings/income-keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        addLog(data.message || 'Removed from config file', 'info');
                        if (typeof window.refreshIncomeKeysStatus === 'function') window.refreshIncomeKeysStatus();
                    } else {
                        addLog('Clear failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) { addLog('Clear failed: ' + err, 'error'); });
        };

        window.startLearning = function() {
            const platform = document.getElementById('learning-platform').value;
            const query = document.getElementById('learning-query').value;
            const maxItems = parseInt(document.getElementById('learning-max').value);
            
            if (!query && platform === 'reddit') {
                addLog('Please enter a subreddit or topic for Reddit', 'warning');
                return;
            }
            if (platform === 'web') {
                const urls = query.split(',').map(function(u) { return u.trim(); }).filter(function(u) { return u && (u.startsWith('http://') || u.startsWith('https://')); });
                if (urls.length === 0) {
                    addLog('Please enter one or more URLs (comma-separated)', 'warning');
                    return;
                }
            }
            if (platform === 'facebook' && !query) {
                addLog('Facebook: using pages from config. To use specific pages, enter Page ID(s) in the query box (e.g. Meta, TechCrunch). Set facebook_access_token in config/auto_learning.json or FACEBOOK_ACCESS_TOKEN env.', 'info');
            }
            if (platform === 'twitter' && !query) {
                addLog('Twitter: using search queries from config. Enter search term(s) in the query box (e.g. AI agents, machine learning) or set twitter_search_queries in config. Link X with Bearer Token above.', 'info');
            }
            
            addLog('Starting ' + platform + ' learning: "' + (query || 'config/default') + '" (max: ' + maxItems + ')', 'info');
            const resultsDiv = document.getElementById('learning-results');
            resultsDiv.innerHTML = '<div style="color: var(--warning);">Learning in progress...</div>';
            
            fetch('/api/learning/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ platform: platform, query: query, max_items: maxItems })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const result = data.result;
                        const status = result.status || 'success';
                        const message = result.message || 'Learning completed';
                        const itemsProcessed = (result.data && result.data.posts_processed) || (result.data && result.data.entries_processed) || (result.data && result.data.articles_processed) || 0;
                        resultsDiv.innerHTML = 
                            '<div style="color: var(--success); margin-bottom: 12px;">' +
                            '<strong>Learning Complete!</strong>' +
                            '</div>' +
                            '<div style="color: var(--text-primary);">' +
                            '<strong>Status:</strong> ' + status + '<br>' +
                            '<strong>Message:</strong> ' + message + '<br>' +
                            '<strong>Items Processed:</strong> ' + itemsProcessed +
                            '</div>';
                        addLog('Learning completed: ' + (result.message || 'Success'), 'info');
                        window.refreshLearningStats();
                    } else {
                        resultsDiv.innerHTML = '<div style="color: var(--danger);">Error: ' + (data.error || 'Unknown error') + '</div>';
                        addLog('Learning failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    resultsDiv.innerHTML = '<div style="color: var(--danger);">Error: ' + err + '</div>';
                    addLog('Error starting learning: ' + err, 'error');
                });
        };
    </script>

        <!-- ui-clarity-empty-states -->
        <span id="ui-empty-brain-trace" hidden>No brain trace has been recorded yet.</span>
        <span id="ui-empty-proposals" hidden>No self-improvement proposals yet.</span>
        <span id="ui-empty-memory-ranking" hidden>No recent memories found to rank.</span>
        <span id="ui-empty-prompt-contracts" hidden>No validation results recorded yet.</span>
        <span id="ui-empty-conversation-chat" hidden>Start a conversation with Elysia.</span>
        <span id="ui-helper-learning" hidden>Learning pulls information from external sources</span>
        <span id="ui-helper-tasks" hidden>Lists work waiting for Elysia or Guardian</span>
        <span id="ui-helper-workbench" hidden>Read-only overview for operators</span>
        <span id="ui-helper-security" hidden>Recent security-related events and alerts</span>
        <span id="ui-helper-memory" hidden>Read-only analysis of memory health</span>
        <span id="ui-helper-insights" hidden>Observability only: RAG paths</span>

        <!-- ui-clarity-secondary-tabs -->
</body>
</html>
"""


class UIControlPanel:
    """
    Web-based control panel for Elysia system.
    Provides real-time monitoring and manual control.
    """
    
    def __init__(self, orchestrator, host: str = "127.0.0.1", port: int = 5000):
        """
        Initialize UI Control Panel.
        
        Args:
            orchestrator: SystemOrchestrator instance (or any object with compatible interface)
            host: Host to bind to
            port: Port to listen on
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask and Flask-SocketIO are required for UI Control Panel. Install with: pip install flask flask-socketio")
        
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        raw_legacy = getattr(orchestrator, "control_panel_chat_history_path", None)
        if not isinstance(raw_legacy, (str, os.PathLike)):
            raw_legacy = CONTROL_PANEL_CHAT_HISTORY_PATH
        self._legacy_chat_history_path = Path(raw_legacy)
        raw_conv_dir = getattr(orchestrator, "conversation_store_dir", None)
        if not isinstance(raw_conv_dir, (str, os.PathLike)):
            raw_conv_dir = DEFAULT_CONVERSATIONS_DIR
        self._conversation_store = ConversationStore(Path(raw_conv_dir))
        self._setup_routes()
        self._setup_socketio()
        self.running = False
        self._server_ready = threading.Event()
        self._server_listening = False
        self._server_error = None
        self._actual_port = None

    def is_ready(self) -> bool:
        """
        Return True only when the dashboard server is actually ready/listening.
        Uses the running flag and a positive socket readiness probe.
        """
        if not bool(getattr(self, "running", False)) or getattr(self, "_server_error", None):
            self._server_listening = False
            return False
        if bool(getattr(self, "_server_listening", False)):
            return True
        self._server_listening = self._probe_server_listening(timeout=0.05)
        return self._server_listening

    def get_readiness_state(self) -> Dict[str, Any]:
        """Return diagnostic dashboard readiness state for startup/status surfaces."""
        ready = self.is_ready()
        return {
            "running": bool(getattr(self, "running", False)),
            "ready": ready,
            "listening": bool(getattr(self, "_server_listening", False)),
            "startup_checked": self._server_ready.is_set(),
            "host": getattr(self, "host", None),
            "port": getattr(self, "_actual_port", None) or getattr(self, "port", None),
            "error": getattr(self, "_server_error", None),
        }

    def _ensure_legacy_control_panel_import(self) -> None:
        """Import legacy control_panel_chat_history.json once (marker-gated; no legacy reads after)."""
        from project_guardian.conversation_store import legacy_import_marker_path

        if legacy_import_marker_path(self._conversation_store.base_dir).exists():
            return
        try:
            self._conversation_store.import_legacy_control_panel_json(self._legacy_chat_history_path)
        except Exception as exc:
            logger.debug("legacy control panel chat import skipped: %s", exc)

    def _chat_history_for_response(self, session_id: str) -> List[Dict[str, Any]]:
        self._ensure_legacy_control_panel_import()
        cid = _control_panel_chat_session_id(session_id)
        rows = self._conversation_store.list_messages(cid, limit=CONTROL_PANEL_CHAT_RESPONSE_MESSAGES)
        return [
            {
                "role": r.get("role"),
                "content": r.get("content"),
                "created_at": r.get("created_at"),
                "message_id": r.get("message_id"),
            }
            for r in rows
        ]

    def _append_chat_history(self, session_id: str, role: str, content: str) -> None:
        cid = _control_panel_chat_session_id(session_id)
        self._conversation_store.append_message(cid, role=role, content=content)

    def _clear_chat_history(self, session_id: str) -> None:
        cid = _control_panel_chat_session_id(session_id)
        self._conversation_store.delete_conversation(cid)

    def _build_chat_prompt_with_history(self, session_id: str, message: str) -> str:
        cid = _control_panel_chat_session_id(session_id)
        msgs = self._conversation_store.get_messages(cid, limit=CONTROL_PANEL_CHAT_PROMPT_MESSAGES)
        block = build_recent_transcript(
            msgs,
            max_messages=CONTROL_PANEL_CHAT_PROMPT_MESSAGES,
            max_chars=CONTROL_PANEL_CHAT_PROMPT_CHAR_LIMIT,
        )
        if not block.strip():
            return message
        return block + "\n\nCurrent user message:\n" + message

    def _remember_chat_exchange(self, session_id: str, user_message: str, reply: str) -> None:
        memory = getattr(self.orchestrator, "memory", None)
        if memory is None or not hasattr(memory, "remember"):
            return
        try:
            memory.remember(
                (
                    "Control panel conversation: "
                    f"user={_redact_control_panel_chat_text(user_message)[:300]!r}; "
                    f"elysia={_redact_control_panel_chat_text(reply)[:300]!r}"
                ),
                category="conversation",
                priority=0.62,
                metadata={"source": "control_panel", "conversation_id": _control_panel_chat_session_id(session_id)},
            )
        except Exception as exc:
            logger.debug("Control panel chat memory write skipped: %s", exc)

    def _maybe_run_brain_operator_chat_trace(self, message: str, http_context: str) -> Dict[str, Any]:
        """Config-gated BrainPipeline trace for panel /api/chat (dry-run unless live flag set)."""
        try:
            from project_guardian.brain.config import get_brain_pipeline_config
            from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event

            cfg = get_brain_pipeline_config()
            if not cfg.enabled or not cfg.entrypoint_enabled("operator_chat"):
                return {}

            guardian = getattr(self.orchestrator, "guardian", None) or getattr(
                self.orchestrator, "_guardian", None
            )
            res = run_brain_pipeline_for_operator_event(
                {
                    "message": message,
                    "source": "operator",
                    "metadata": {"http_context": str(http_context)[:240]},
                },
                guardian=guardian,
                source_entrypoint="operator_chat",
                config=cfg,
            )
            if isinstance(res, dict) and res.get("bypass"):
                return {}

            trace, _dash = res
            rc = trace.run_context or {}
            transitions = getattr(trace, "transitions", None)
            transition_count = len(transitions) if isinstance(transitions, list) else 0
            last_transition = str(transitions[-1])[:120] if transition_count else ""
            risk = getattr(trace, "risk", None)
            execution = getattr(trace, "execution", None)
            return {
                "brain_trace_enabled": True,
                "brain_trace_id": trace.brain_pipeline_id or "",
                "brain_trace_path": str(cfg.trace_path),
                "brain_dry_run": bool(rc.get("dry_run")),
                "brain_risk_level": getattr(getattr(risk, "level", None), "value", getattr(risk, "level", None))
                if risk
                else None,
                "brain_tda_used": trace.think_decide_act_trace is not None,
                "brain_execution_success": bool(getattr(execution, "success", False)) if execution else False,
                "brain_transition_count": transition_count,
                "brain_last_transition": last_transition,
            }
        except Exception as exc:
            logger.warning("BrainPipeline operator chat trace failed (chat continues): %s", exc)
            return {"brain_trace_error": str(exc)[:400]}

    def _make_panel_operator_chat_responder(self, get_unified_system: Callable[[], Any]):
        def responder(req: OperatorChatRequest) -> OperatorChatResponderResult:
            us = get_unified_system()
            if us and hasattr(us, "chat_with_llm"):
                reply, err = us.chat_with_llm(req.composed_prompt)
                if err:
                    raise OperatorChatResponderError(str(err))
                return OperatorChatResponderResult(
                    reply_text=reply or "",
                    extra_fields={"backend": "chat_with_llm"},
                )
            if hasattr(self.orchestrator, "ask_ai"):
                reply = self.orchestrator.ask_ai(req.composed_prompt) or "(no reply)"
                return OperatorChatResponderResult(
                    reply_text=reply,
                    extra_fields={"backend": "ask_ai"},
                )
            raise OperatorChatResponderError(
                "No chat backend available (unified system or ask_ai)"
            )

        return responder

    def _jsonify_panel_operator_chat_result(self, result: Any) -> Any:
        history = self._chat_history_for_response(result.conversation_id)
        body: Dict[str, Any] = {
            "conversation_id": result.conversation_id,
            "history": history,
        }
        if result.brain_metadata:
            body.update(result.brain_metadata)

        if not result.ok:
            err = str(result.error or "chat failed")
            if err.startswith("user_persist_failed") or err.startswith("assistant_persist_failed"):
                return jsonify({"error": err}), 500
            body.update(
                {
                    "success": False,
                    "error": err,
                    "reply": None,
                }
            )
            return jsonify(body), 200

        body.update(
            {
                "success": True,
                "reply": result.reply,
                "error": None,
            }
        )
        return jsonify(body), 200

    def _handle_control_panel_operator_chat(
        self,
        message: str,
        conversation_id: str,
        get_unified_system: Callable[[], Any],
    ) -> Any:
        self._ensure_legacy_control_panel_import()
        us = get_unified_system()
        has_unified = bool(us and hasattr(us, "chat_with_llm"))
        has_ask_ai = hasattr(self.orchestrator, "ask_ai")
        if not has_unified and not has_ask_ai:
            return jsonify({"error": "No chat backend available (unified system or ask_ai)"}), 400

        result = run_operator_chat_turn(
            message,
            conversation_id=conversation_id,
            conversation_store=self._conversation_store,
            responder=self._make_panel_operator_chat_responder(get_unified_system),
            brain_trace_callback=self._maybe_run_brain_operator_chat_trace,
            after_persist_callback=lambda cid, user, reply, _brain, _extra: self._remember_chat_exchange(
                cid, user, reply
            ),
            history_limit=CONTROL_PANEL_CHAT_PROMPT_MESSAGES,
            history_char_limit=CONTROL_PANEL_CHAT_PROMPT_CHAR_LIMIT,
            http_context="control_panel",
            source_entrypoint="control_panel_operator_chat",
            default_conversation_id="control_panel",
            persist_user_before_responder=False,
        )
        return self._jsonify_panel_operator_chat_result(result)

    def _setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            return render_template_string(CONTROL_PANEL_TEMPLATE)
        
        @self.app.route('/favicon.ico')
        def favicon():
            return '', 204
        
        @self.app.route('/.well-known/appspecific/com.chrome.devtools.json')
        def chrome_devtools():
            return '', 204
        
        @self.app.route('/api/autonomy', methods=['GET'])
        def get_autonomy_status():
            """Get autonomy config and last execution status."""
            try:
                cfg = {"enabled": False, "allowed_actions": [], "max_actions_per_hour": 6}
                if hasattr(self.orchestrator, "_load_autonomy_config"):
                    cfg = self.orchestrator._load_autonomy_config()
                last = getattr(self.orchestrator, "_last_autonomy_result", None)
                return jsonify({
                    "success": True,
                    "enabled": cfg.get("enabled", False),
                    "allowed_actions": cfg.get("allowed_actions", []),
                    "max_actions_per_hour": cfg.get("max_actions_per_hour", 6),
                    "last": last,
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/autonomy', methods=['POST'])
        def set_autonomy():
            """Toggle autonomy on/off via config file."""
            try:
                data = request.get_json() or {}
                enabled = data.get("enabled")
                if enabled is None:
                    return jsonify({"error": "enabled required"}), 400
                import json
                from pathlib import Path
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "autonomy.json"
                cfg = {"enabled": False, "interval_seconds": 120, "allowed_actions": ["consider_learning", "consider_dream_cycle"], "max_actions_per_hour": 6}
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                cfg["enabled"] = bool(enabled)
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                return jsonify({"success": True, "enabled": cfg["enabled"]})
            except Exception as e:
                logger.error(f"Set autonomy error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/next-action')
        def get_next_action():
            """Get unified next action from tasks, missions, introspection, etc."""
            try:
                if hasattr(self.orchestrator, "get_next_action"):
                    result = self.orchestrator.get_next_action()
                    return jsonify(result)
                return jsonify({"success": False, "error": "Next action not available"}), 503
            except Exception as e:
                logger.error(f"Next action error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/autonomy/execute-cycle', methods=['POST'])
        def execute_autonomy_cycle():
            """Run one autonomy cycle (get next action and execute if allowed). Supports exploratory actions."""
            try:
                if hasattr(self.orchestrator, "run_autonomous_cycle"):
                    result = self.orchestrator.run_autonomous_cycle()
                    return jsonify({
                        "success": True,
                        "dry_run": bool(result.get("dry_run", True)),
                        "executed": result.get("executed", False),
                        "action": result.get("action"),
                        "reason": result.get("reason"),
                        "trace_id": result.get("trace_id"),
                        "guard_reasons": result.get("guard_reasons"),
                        "ask_user_question": result.get("ask_user_question"),
                    })
                return jsonify({"success": False, "error": "Autonomy not available"}), 503
            except Exception as e:
                logger.error("Execute cycle error: %s", e, exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/operator/ack-question', methods=['POST'])
        def ack_operator_question():
            """Clear pending operator question after acknowledgment. Resumes normal auto-execute."""
            try:
                if hasattr(self.orchestrator, "_pending_operator_question"):
                    self.orchestrator._pending_operator_question = None
                    return jsonify({"success": True, "message": "Question acknowledged"})
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Ack question error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/ping')
        def ping():
            """Quick connectivity check - returns immediately."""
            return jsonify({
                "ok": True,
                "service": "elysia-control-panel",
                "port": getattr(self, 'port', None),
                "orchestrator": self.orchestrator is not None if hasattr(self, 'orchestrator') else False,
            }), 200

        @self.app.route('/api/debug')
        def debug_info():
            """Diagnostic endpoint for control panel troubleshooting."""
            try:
                info = {
                    "flask_available": FLASK_AVAILABLE,
                    "orchestrator": self.orchestrator is not None if hasattr(self, 'orchestrator') else False,
                    "port": getattr(self, 'port', None),
                    "running": getattr(self, 'running', False),
                    "readiness": self.get_readiness_state(),
                }
                if self.orchestrator:
                    info["has_memory"] = hasattr(self.orchestrator, 'memory') and self.orchestrator.memory is not None
                    info["has_elysia_loop"] = hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop is not None
                    info["has_module_registry"] = hasattr(self.orchestrator, 'module_registry') and self.orchestrator.module_registry is not None
                return jsonify(info), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/logs/recent")
        def api_logs_recent():
            """Tail the current backend log; legacy trial logs are clearly labeled as historical."""
            try:
                n = request.args.get("lines", "120")
                try:
                    nl = max(10, min(500, int(n)))
                except (TypeError, ValueError):
                    nl = 120
                return jsonify(_build_recent_log_payload(max_lines=nl)), 200
            except Exception as e:
                logger.error("logs recent: %s", e, exc_info=True)
                return jsonify({"error": str(e), "success": False}), 500

        @self.app.route("/api/insights/overview")
        def api_insights_overview():
            """Operator observability: self-build, MCP, LLM trace tail, RAG log tail."""
            try:
                from .operator_insights import build_insights_overview

                tl = request.args.get("trace_lines", "40")
                rl = request.args.get("rag_lines", "30")
                try:
                    tln = max(5, min(120, int(tl)))
                except (TypeError, ValueError):
                    tln = 40
                try:
                    rln = max(5, min(120, int(rl)))
                except (TypeError, ValueError):
                    rln = 30
                return jsonify(build_insights_overview(trace_lines=tln, rag_lines=rln)), 200
            except Exception as e:
                logger.error("insights overview: %s", e, exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/insights/api-meter")
        def api_insights_api_meter():
            """Lightweight session API usage + availability for Dashboard meter card."""
            try:
                from .operator_insights import build_api_gas_meter_bundle

                return jsonify(build_api_gas_meter_bundle()), 200
            except Exception as e:
                logger.error("insights api-meter: %s", e, exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/insights/selfbuild")
        def api_insights_selfbuild():
            try:
                from .operator_insights import build_selfbuild_bundle

                return jsonify(build_selfbuild_bundle()), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/insights/mcp")
        def api_insights_mcp():
            try:
                from .operator_insights import build_mcp_bundle

                return jsonify(build_mcp_bundle()), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/insights/traces")
        def api_insights_traces():
            try:
                from .operator_insights import build_llm_trace_bundle

                n = request.args.get("lines", "50")
                try:
                    nl = max(5, min(200, int(n)))
                except (TypeError, ValueError):
                    nl = 50
                return jsonify(build_llm_trace_bundle(max_lines=nl)), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/insights/rag-log")
        def api_insights_rag_log():
            try:
                from .operator_insights import build_rag_log_bundle

                n = request.args.get("lines", "35")
                try:
                    nl = max(5, min(150, int(n)))
                except (TypeError, ValueError):
                    nl = 35
                return jsonify(build_rag_log_bundle(max_lines=nl)), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500
            
        @self.app.route('/api/status')
        def get_status():
            """Get comprehensive system status - optimized for fast response."""
            try:
                external_activity = _build_external_activity_snapshot(getattr(self, "orchestrator", None))
                # Quick check - return fast if orchestrator is None
                if not hasattr(self, 'orchestrator') or self.orchestrator is None:
                    return jsonify({
                        "system": {"running": False, "initialized": False, "uptime": 0, "error": "Orchestrator not available"},
                        "loop": {"running": False, "paused": False, "queue_size": 0},
                        "memory": {"total_entries": 0, "total_memories": 0},
                        "security": {"policy_loaded": False, "recent_violations": 0, "pending_reviews": 0},
                        "trust": {"components": 0, "average_trust": 0},
                        "external": external_activity,
                        "timestamp": datetime.now().isoformat()
                    }), 200
                
                # Helper function to convert Path objects to strings
                def convert_paths(obj):
                    """Recursively convert Path objects to strings."""
                    if isinstance(obj, dict):
                        return {k: convert_paths(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_paths(item) for item in obj]
                    elif hasattr(obj, '__str__') and hasattr(obj, 'parts'):  # Path object
                        return str(obj)
                    else:
                        return obj
                
                # Get system status - use direct attribute access (fast)
                # Check multiple indicators to determine if system is actually initialized
                _initialized_attr = getattr(self.orchestrator, '_initialized', False)
                _running_attr = getattr(self.orchestrator, '_running', False)
                
                # Additional indicators: use loaded-aware APIs (do not read memory_log directly)
                memory_loaded = False
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        if hasattr(self.orchestrator.memory, 'get_memory_state'):
                            st = self.orchestrator.memory.get_memory_state(load_if_needed=False)
                            memory_loaded = bool(st.get("memory_loaded")) and ((st.get("memory_count") or 0) > 0)
                        elif hasattr(self.orchestrator.memory, 'get_memory_count'):
                            cnt = self.orchestrator.memory.get_memory_count(load_if_needed=False)
                            memory_loaded = cnt is not None and cnt > 0
                    except Exception:
                        pass
                
                loop_running = False
                if hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop:
                    try:
                        loop_running = getattr(self.orchestrator.elysia_loop, 'running', False)
                    except:
                        pass
                
                # System is considered initialized if:
                # - _initialized attribute is True, OR
                # - Memory is loaded (system has been running), OR
                # - Loop is running, OR
                # - Orchestrator has core components (so UI never sticks on "Initializing")
                has_core = (
                    (hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop is not None)
                    or (hasattr(self.orchestrator, 'memory') and self.orchestrator.memory is not None)
                )
                is_initialized = _initialized_attr or memory_loaded or loop_running or has_core
                is_running = _running_attr or loop_running or memory_loaded or has_core
                
                system_status = {
                    "running": is_running,
                    "initialized": is_initialized,
                    "start_time": None,
                    "operational_stats": {}
                }
                try:
                    from .mission_autonomy import mission_purpose_state_snapshot

                    system_status["mission_purpose_state"] = mission_purpose_state_snapshot() or {}
                except Exception:
                    system_status["mission_purpose_state"] = {}
                try:
                    unified = getattr(self.orchestrator, "_unified_system", None)
                    if unified is not None and hasattr(unified, "get_status"):
                        ustat = unified.get_status() or {}
                        system_status["openclaw_enabled"] = bool(ustat.get("openclaw_enabled", False))
                        system_status["openclaw_available"] = bool(ustat.get("openclaw_available", False))
                        system_status["openclaw_skills_count"] = int(ustat.get("openclaw_skills_count", 0) or 0)
                        system_status["last_openclaw_task"] = ustat.get("last_openclaw_task")
                        system_status["last_openclaw_error"] = ustat.get("last_openclaw_error")
                except Exception as e:
                    logger.debug(f"Error getting unified openclaw status: {e}")
                try:
                    if hasattr(self.orchestrator, "get_context_pipeline_runtime_status"):
                        system_status["context_pipeline_runtime_status"] = (
                            self.orchestrator.get_context_pipeline_runtime_status() or {}
                        )
                except Exception as e:
                    logger.debug(f"Error getting context pipeline runtime status: {e}")
                
                # Safely get start_time
                if hasattr(self.orchestrator, 'start_time') and self.orchestrator.start_time:
                    try:
                        if hasattr(self.orchestrator.start_time, 'isoformat'):
                            system_status["start_time"] = self.orchestrator.start_time.isoformat()
                        else:
                            system_status["start_time"] = str(self.orchestrator.start_time)
                    except:
                        system_status["start_time"] = None
                
                # Calculate uptime if start_time exists
                if system_status["start_time"]:
                    try:
                        from datetime import datetime
                        start = datetime.fromisoformat(system_status["start_time"])
                        uptime = (datetime.now() - start).total_seconds()
                        system_status["uptime"] = max(0, uptime)
                    except:
                        system_status["uptime"] = 0
                else:
                    system_status["uptime"] = 0
                
                # Get operational stats if available (non-blocking)
                try:
                    operational_stats = getattr(self.orchestrator, 'operational_stats', {})
                    system_status["operational_stats"] = convert_paths(operational_stats)
                except:
                    pass
                # Canonical operational state (deferred/vector/dashboard) - single source for UI
                try:
                    if hasattr(self.orchestrator, 'get_startup_operational_state'):
                        op = self.orchestrator.get_startup_operational_state()
                        system_status["operational_state"] = convert_paths(op)
                except Exception:
                    system_status["operational_state"] = {}
                
                # Get ElysiaLoopCore status - direct attribute access only (fast)
                loop_status = {}
                if hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop:
                    try:
                        loop_status["running"] = getattr(self.orchestrator.elysia_loop, 'running', False)
                        loop_status["paused"] = getattr(self.orchestrator.elysia_loop, 'paused', False)
                        # Get queue_size - ElysiaLoopCore uses task_queue.get_queue_size()
                        try:
                            tq = getattr(self.orchestrator.elysia_loop, 'task_queue', None)
                            if tq and hasattr(tq, 'get_queue_size'):
                                loop_status["queue_size"] = tq.get_queue_size()
                            else:
                                queue_size = getattr(self.orchestrator.elysia_loop, 'queue_size', 0)
                                loop_status["queue_size"] = 0 if callable(queue_size) else queue_size
                        except Exception:
                            loop_status["queue_size"] = 0
                    except Exception as e:
                        logger.debug(f"Error getting loop status: {e}")
                        loop_status = {"running": False, "paused": False, "queue_size": 0}
                else:
                    # If no elysia_loop, check if system is at least initialized
                    loop_status = {"running": system_status.get("initialized", False), "paused": False, "queue_size": 0}
                
                # Get RuntimeLoop status (quick check only)
                runtime_status = {}
                if hasattr(self.orchestrator, 'runtime_loop') and self.orchestrator.runtime_loop:
                    try:
                        runtime_status["running"] = getattr(self.orchestrator.runtime_loop, 'running', False)
                    except:
                        runtime_status["running"] = False
                
                # Get ModuleRegistry status (quick check only)
                module_status = {}
                if hasattr(self.orchestrator, 'module_registry') and self.orchestrator.module_registry:
                    module_status["available"] = True
                
                # Get memory stats via loaded-aware APIs (non-forcing for status)
                memory_stats = {}
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_memory_state'):
                            st = mem.get_memory_state(load_if_needed=False)
                            count = st.get("memory_count")
                            memory_stats = {
                                "total_entries": count if count is not None else 0,
                                "total_memories": count if count is not None else 0,
                                "memory_loaded": st.get("memory_loaded", False),
                            }
                        elif hasattr(mem, 'get_memory_count'):
                            count = mem.get_memory_count(load_if_needed=False)
                            memory_stats = {"total_entries": count or 0, "total_memories": count or 0}
                        if getattr(mem, 'vector_memory', None):
                            memory_stats["vector_memory_enabled"] = True
                    except Exception as e:
                        logger.debug(f"Error getting memory stats: {e}")
                        memory_stats = {"total_entries": 0, "total_memories": 0}
                else:
                    memory_stats = {"total_entries": 0, "total_memories": 0}

                # Add latest cleanup policy/result details when available.
                monitor_obj = None
                monitor_sources = [
                    self.orchestrator,
                    getattr(self.orchestrator, "guardian_core", None),
                    getattr(self.orchestrator, "core", None),
                ]
                for src in monitor_sources:
                    if src is None:
                        continue
                    maybe_monitor = getattr(src, "monitor", None)
                    if maybe_monitor is not None:
                        monitor_obj = maybe_monitor
                        break
                if monitor_obj and hasattr(monitor_obj, "get_last_cleanup_result"):
                    try:
                        memory_stats["last_cleanup"] = monitor_obj.get_last_cleanup_result()
                    except Exception as e:
                        logger.debug(f"Error getting cleanup status: {e}")
                
                # Get security status (quick check)
                security_status = {}
                if hasattr(self.orchestrator, 'safety') and self.orchestrator.safety:
                    security_status["policy_loaded"] = True
                    security_status["recent_violations"] = 0
                    security_status["pending_reviews"] = 0
                
                # Get trust status (quick check)
                trust_status = {}
                if hasattr(self.orchestrator, 'trust') and self.orchestrator.trust:
                    trust_status["components"] = 1
                    trust_status["average_trust"] = 0.8
                
                # Convert all data to ensure no Path objects remain
                response_data = {
                    "system": convert_paths(system_status),
                    "loop": convert_paths(loop_status),
                    "runtime": convert_paths(runtime_status),
                    "modules": convert_paths(module_status),
                    "memory": convert_paths(memory_stats),
                    "security": convert_paths(security_status),
                    "trust": convert_paths(trust_status),
                    "external": convert_paths(external_activity),
                    "timestamp": datetime.now().isoformat()
                }
                
                return jsonify(response_data)
                
            except Exception as e:
                logger.error(f"Status endpoint error: {e}", exc_info=True)
                error_msg = str(e)[:200]
                # Return minimal valid status even on error
                return jsonify({
                    "system": {
                        "running": getattr(self.orchestrator, '_running', False),
                        "initialized": getattr(self.orchestrator, '_initialized', False),
                        "uptime": 0,
                        "error": error_msg
                    },
                    "loop": {
                        "running": getattr(self.orchestrator, '_running', False),
                        "paused": False,
                        "queue_size": 0
                    },
                    "memory": {"total_entries": 0, "total_memories": 0},
                    "security": {"policy_loaded": False, "recent_violations": 0, "pending_reviews": 0},
                    "trust": {"components": 0, "average_trust": 0},
                    "external": _build_external_activity_snapshot(getattr(self, "orchestrator", None)),
                    "timestamp": datetime.now().isoformat()
                }), 200
                
        @self.app.route('/api/control/pause', methods=['POST'])
        def pause_loop():
            """Pause the event loop."""
            try:
                if self.orchestrator.elysia_loop and hasattr(self.orchestrator.elysia_loop, 'pause'):
                    self.orchestrator.elysia_loop.pause()
                    return jsonify({"success": True, "message": "Loop paused"})
                return jsonify({"success": False, "message": "Pause not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/control/resume', methods=['POST'])
        def resume_loop():
            """Resume the event loop."""
            try:
                if self.orchestrator.elysia_loop and hasattr(self.orchestrator.elysia_loop, 'resume'):
                    self.orchestrator.elysia_loop.resume()
                    return jsonify({"success": True, "message": "Loop resumed"})
                return jsonify({"success": False, "message": "Resume not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/memory/snapshot', methods=['POST'])
        def create_snapshot():
            """Create memory snapshot."""
            try:
                # Use MemoryCore if available
                if self.orchestrator.memory and hasattr(self.orchestrator.memory, 'save'):
                    # Save current memory state
                    self.orchestrator.memory.save()
                    return jsonify({"success": True, "message": "Memory saved"})
                return jsonify({"success": False, "message": "Memory snapshot not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/memory/cleanup', methods=['POST'])
        def cleanup_memory():
            """Cleanup and consolidate memories to reduce memory usage."""
            try:
                if not hasattr(self.orchestrator, 'memory') or not self.orchestrator.memory:
                    return jsonify({"error": "Memory system not available"}), 400
                
                # Get parameters from request
                data = request.get_json() or {}
                max_memories = data.get("max_memories", 5000)
                keep_recent_days = data.get("keep_recent_days", 30)
                
                # Perform consolidation
                if hasattr(self.orchestrator.memory, 'consolidate'):
                    result = self.orchestrator.memory.consolidate(
                        max_memories=max_memories,
                        keep_recent_days=keep_recent_days
                    )
                    return jsonify({"success": True, "result": result})
                else:
                    return jsonify({"error": "Consolidate method not available"}), 400
            except Exception as e:
                logger.error(f"Memory cleanup error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/memory/rebuild-vector', methods=['POST'])
        def rebuild_vector():
            """Manually trigger vector index rebuild when degraded or rebuild pending."""
            try:
                if not hasattr(self.orchestrator, 'rebuild_vector_memory_if_pending'):
                    return jsonify({"error": "Vector rebuild not available"}), 400
                result = self.orchestrator.rebuild_vector_memory_if_pending()
                return jsonify({"success": True, "result": result})
            except Exception as e:
                logger.error(f"Vector rebuild error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/memory/stats', methods=['GET'])
        def get_memory_stats():
            """Get memory usage statistics."""
            try:
                if not hasattr(self.orchestrator, 'memory') or not self.orchestrator.memory:
                    return jsonify({"error": "Memory system not available"}), 400
                
                from project_guardian.memory_cleanup import MemoryCleanup
                cleanup = MemoryCleanup(self.orchestrator.memory)
                stats = cleanup.get_memory_size_estimate()
                
                om = self.orchestrator.memory
                if hasattr(om, "get_memory_state"):
                    _pst = om.get_memory_state(load_if_needed=False)
                    stats.update(_pst)
                    stats["current_count"] = _pst.get("memory_count")
                elif hasattr(om, "get_memory_count"):
                    stats["current_count"] = om.get_memory_count(load_if_needed=False)
                
                return jsonify({"success": True, "stats": stats})
            except Exception as e:
                logger.error(f"Memory stats error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/prompts/evolve', methods=['POST'])
        def run_prompt_evolution():
            """Run AI-powered prompt evolution on low-scoring prompts."""
            try:
                if not hasattr(self.orchestrator, 'prompt_evolver') or not self.orchestrator.prompt_evolver:
                    return jsonify({"error": "Prompt evolution not available"}), 400
                data = request.get_json() or {}
                min_records = data.get("min_records", 5)
                evolved = self.orchestrator.run_prompt_evolution(min_records=min_records)
                stats = self.orchestrator.prompt_evolver.get_stats()
                return jsonify({
                    "success": True,
                    "evolved_count": evolved,
                    "stats": stats
                })
            except Exception as e:
                logger.error(f"Prompt evolution error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/prompts/stats', methods=['GET'])
        def get_prompt_evolution_stats():
            """Get prompt evolution statistics."""
            try:
                if not hasattr(self.orchestrator, 'prompt_evolver') or not self.orchestrator.prompt_evolver:
                    return jsonify({"error": "Prompt evolution not available"}), 400
                return jsonify({"success": True, "stats": self.orchestrator.prompt_evolver.get_stats()})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        def _get_unified_system():
            """Unified Elysia system when guardian is run under Elysia (for chat, income, harvest, etc.)."""
            return getattr(self.orchestrator, '_unified_system', None)

        def _ui_data_roots() -> List[Path]:
            override = getattr(self.orchestrator, "ui_data_roots", None)
            if override:
                raw_roots = override if isinstance(override, (list, tuple, set)) else [override]
            else:
                raw_roots = [Path(__file__).resolve().parent.parent / "data"]
                storage_path = getattr(self.orchestrator, "storage_path", None)
                if storage_path:
                    storage_root = Path(storage_path)
                    raw_roots.append(storage_root if storage_root.name == "data" else storage_root / "data")

            roots: List[Path] = []
            seen = set()
            for raw_root in raw_roots:
                try:
                    root = Path(raw_root).expanduser()
                except TypeError:
                    continue
                key = str(root.resolve()) if root.exists() else str(root)
                if key in seen:
                    continue
                seen.add(key)
                roots.append(root)
            return roots

        def _load_json_file(path: Path) -> Any:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug("Workbench JSON load failed for %s: %s", path, exc)
                return None

        def _project_root() -> Path:
            return Path(__file__).resolve().parent.parent

        def _ui_doc_roots() -> List[Path]:
            raw_roots: List[Path] = []
            configured = getattr(self.orchestrator, "ui_doc_roots", None)
            if isinstance(configured, (list, tuple, set)):
                raw_roots.extend(Path(item) for item in configured if item)
            raw_roots.append(_project_root() / "docs")

            roots: List[Path] = []
            seen = set()
            for raw_root in raw_roots:
                try:
                    root = Path(raw_root).expanduser()
                except Exception:
                    continue
                key = str(root.resolve()) if root.exists() else str(root)
                if key in seen:
                    continue
                seen.add(key)
                roots.append(root)
            return roots

        def _doc_excerpt(text: str) -> str:
            if not isinstance(text, str):
                return ""
            lines: List[str] = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith("```"):
                    continue
                lines.append(line)
                if len(" ".join(lines)) >= 220:
                    break
            excerpt = " ".join(lines).strip()
            return excerpt[:280]

        def _coerce_timestamp(value: Any, fallback: float = 0.0) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return fallback
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                try:
                    return datetime.fromisoformat(text).timestamp()
                except ValueError:
                    pass
                try:
                    return float(text)
                except ValueError:
                    return fallback
            return fallback

        def _artifact_contract_label(contract_id: Optional[str]) -> str:
            labels = {
                "revenue_shortlist": "Revenue shortlist",
                "learned_digest": "Learning digest",
                "system_improvement_proposal": "System improvement",
                "capability_gap_report": "Capability gap report",
                "research_brief": "Research brief",
                "offer_pack": "Offer pack",
            }
            if not contract_id:
                return "Artifact"
            return labels.get(contract_id, contract_id.replace("_", " ").strip().title())

        def _artifact_headline(blob: Dict[str, Any], payload: Any, fallback_name: str) -> str:
            if isinstance(payload, dict):
                for key in ("title", "product_name", "summary", "one_liner", "why_they_matter"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                insights = payload.get("top_insights")
                if isinstance(insights, list):
                    for item in insights:
                        if isinstance(item, str) and item.strip():
                            return item.strip()
                opportunities = payload.get("opportunities")
                if isinstance(opportunities, list):
                    for item in opportunities:
                        if isinstance(item, dict):
                            title = item.get("title")
                            if isinstance(title, str) and title.strip():
                                return title.strip()
            for key in ("title", "archetype", "contract_id"):
                value = blob.get(key)
                if isinstance(value, str) and value.strip():
                    return value.replace("_", " ").strip().title()
            return fallback_name.replace("_", " ").replace("-", " ").strip().title()

        def _artifact_summary(blob: Dict[str, Any], payload: Any) -> str:
            if isinstance(payload, dict):
                for key in ("one_liner", "why_buy_now", "why_they_matter"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                why = payload.get("why_they_matter")
                if isinstance(why, str) and why.strip():
                    return why.strip()
                validation = payload.get("validation_prompt")
                if isinstance(validation, str) and validation.strip():
                    return validation.strip()
                recommendations = payload.get("recommended_followup_tasks")
                if isinstance(recommendations, list) and recommendations:
                    trimmed = [str(item).strip() for item in recommendations if str(item).strip()]
                    if trimmed:
                        return "Next: " + ", ".join(trimmed[:3])
                opportunities = payload.get("opportunities")
                if isinstance(opportunities, list) and opportunities:
                    titles = []
                    for item in opportunities:
                        if isinstance(item, dict):
                            title = item.get("title")
                            if isinstance(title, str) and title.strip():
                                titles.append(title.strip())
                        if len(titles) >= 2:
                            break
                    if titles:
                        return "Opportunities: " + "; ".join(titles)
                for key in ("summary", "notes"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            for key in ("reason", "goal"):
                value = blob.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""

        def _load_artifact_entries() -> List[Dict[str, Any]]:
            entries: List[Dict[str, Any]] = []
            contract_defaults = {
                "generated_reports": None,
                "revenue_briefs": "revenue_shortlist",
                "research_briefs": "research_brief",
            }
            for root in _ui_data_roots():
                for folder_name, default_contract in contract_defaults.items():
                    folder = root / folder_name
                    if not folder.exists():
                        continue
                    for path in folder.glob("*.json"):
                        blob = _load_json_file(path)
                        if not isinstance(blob, dict):
                            continue
                        payload = blob.get("payload")
                        contract_id = blob.get("contract_id") or default_contract
                        mtime = path.stat().st_mtime
                        created_ts = _coerce_timestamp(
                            blob.get("created_at") or blob.get("finished_at") or blob.get("updated_at"),
                            fallback=mtime,
                        )
                        created_at = (
                            blob.get("created_at")
                            or blob.get("finished_at")
                            or blob.get("updated_at")
                            or datetime.fromtimestamp(created_ts).isoformat()
                        )
                        entries.append(
                            {
                                "task_id": blob.get("task_id"),
                                "contract_id": contract_id,
                                "artifact_type": _artifact_contract_label(contract_id),
                                "headline": _artifact_headline(blob, payload, path.stem),
                                "summary": _artifact_summary(blob, payload),
                                "created_at": created_at,
                                "file_name": path.name,
                                "path": str(path),
                                "source_dir": folder_name,
                                "payload": payload,
                                "_sort_ts": created_ts,
                            }
                        )
            entries.sort(key=lambda item: item.get("_sort_ts", 0.0), reverse=True)
            return entries

        def _load_self_task_entries() -> List[Dict[str, Any]]:
            task_map: Dict[str, Dict[str, Any]] = {}
            for root in _ui_data_roots():
                path = root / "self_task_queue.json"
                if not path.exists():
                    continue
                blob = _load_json_file(path)
                task_rows: List[Any] = []
                if isinstance(blob, dict):
                    if isinstance(blob.get("tasks"), list):
                        task_rows.extend(blob["tasks"])
                    else:
                        for key in ("active", "queued", "completed", "failed"):
                            value = blob.get(key)
                            if isinstance(value, list):
                                task_rows.extend(value)
                elif isinstance(blob, list):
                    task_rows.extend(blob)
                for row in task_rows:
                    if not isinstance(row, dict):
                        continue
                    task_id = row.get("task_id") or row.get("id") or f"task-{len(task_map)}"
                    sort_ts = _coerce_timestamp(row.get("updated_at") or row.get("created_at"), 0.0)
                    merged = dict(row)
                    merged["_sort_ts"] = sort_ts
                    existing = task_map.get(task_id)
                    if existing is None or sort_ts >= existing.get("_sort_ts", 0.0):
                        task_map[task_id] = merged
            tasks = list(task_map.values())
            tasks.sort(key=lambda item: item.get("_sort_ts", 0.0), reverse=True)
            return tasks

        def _load_sales_launch_docs() -> List[Dict[str, Any]]:
            specs = [
                ("STRIPE_PAYMENT_LINK_SETUP.md", "Stripe Payment Link Setup"),
                ("TRANSACTION_SETUP_CHECKLIST.md", "Transaction Setup Checklist"),
                ("FIRST_OFFER_LAUNCH_BUNDLE.md", "First Offer Launch Bundle"),
                ("FIRST_BUYER_SIGNAL_LOG.md", "First Buyer Signal Log"),
            ]
            entries: List[Dict[str, Any]] = []
            candidate_roots: List[Path] = []
            candidate_roots.extend(_ui_doc_roots())
            for root in _ui_data_roots():
                candidate_roots.append(root / "generated_reports")

            for file_name, title in specs:
                chosen_path: Optional[Path] = None
                for root in candidate_roots:
                    path = root / file_name
                    if path.exists():
                        chosen_path = path
                        break
                if chosen_path is None:
                    continue
                try:
                    text = chosen_path.read_text(encoding="utf-8")
                except Exception as exc:
                    logger.debug("Launch doc load failed for %s: %s", chosen_path, exc)
                    continue
                entries.append(
                    {
                        "title": title,
                        "file_name": file_name,
                        "path": str(chosen_path),
                        "summary": _doc_excerpt(text),
                    }
                )
            return entries

        def _build_workbench_summary() -> Dict[str, Any]:
            artifacts = _load_artifact_entries()
            tasks = _load_self_task_entries()
            launch_docs = _load_sales_launch_docs()

            active_statuses = {"queued", "pending", "running", "in_progress", "ready", "submitted"}
            completed_statuses = {"completed", "complete", "success", "succeeded", "finished", "done"}

            active_self_tasks = []
            recent_successes = []
            for task in tasks:
                status = str(task.get("status") or "").strip().lower()
                summary = str(task.get("goal") or task.get("reason") or "").strip()
                task_row = {
                    "task_id": task.get("task_id"),
                    "title": task.get("title") or task.get("task_id") or "Self-task",
                    "goal": summary,
                    "status": task.get("status"),
                    "category": task.get("category"),
                    "priority": task.get("priority"),
                    "created_at": task.get("updated_at") or task.get("created_at"),
                    "artifact_type": _artifact_contract_label(task.get("output_contract_id")),
                }
                if status in active_statuses:
                    active_self_tasks.append(task_row)
                if status in completed_statuses:
                    recent_successes.append(
                        {
                            "task_id": task.get("task_id"),
                            "title": task_row["title"],
                            "summary": summary,
                            "created_at": task_row["created_at"],
                            "artifact_type": task_row["artifact_type"],
                        }
                    )

            top_opportunities = []
            seen_titles = set()
            for artifact in artifacts:
                if artifact.get("contract_id") != "revenue_shortlist":
                    continue
                payload = artifact.get("payload")
                if not isinstance(payload, dict):
                    continue
                opportunities = payload.get("opportunities")
                if not isinstance(opportunities, list):
                    continue
                for item in opportunities:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "").strip()
                    if not title:
                        continue
                    key = title.lower()
                    if key in seen_titles:
                        continue
                    seen_titles.add(key)
                    top_opportunities.append(
                        {
                            "title": title,
                            "rationale": item.get("rationale"),
                            "required_capability": item.get("required_capability"),
                            "difficulty": item.get("difficulty"),
                            "expected_value": item.get("expected_value"),
                            "created_at": artifact.get("created_at"),
                            "artifact_type": artifact.get("artifact_type"),
                        }
                    )
                    if len(top_opportunities) >= 6:
                        break
                if len(top_opportunities) >= 6:
                    break

            learning_digests = []
            improvement_briefs = []
            recent_artifacts = []
            improvement_contracts = {"system_improvement_proposal", "capability_gap_report", "research_brief"}

            for artifact in artifacts[:8]:
                recent_artifacts.append(
                    {
                        "task_id": artifact.get("task_id"),
                        "headline": artifact.get("headline"),
                        "summary": artifact.get("summary"),
                        "created_at": artifact.get("created_at"),
                        "artifact_type": artifact.get("artifact_type"),
                        "file_name": artifact.get("file_name"),
                        "path": artifact.get("path"),
                    }
                )

            for artifact in artifacts:
                payload = artifact.get("payload")
                if artifact.get("contract_id") == "learned_digest":
                    insights = payload.get("top_insights") if isinstance(payload, dict) else []
                    followups = payload.get("recommended_followup_tasks") if isinstance(payload, dict) else []
                    learning_digests.append(
                        {
                            "headline": artifact.get("headline"),
                            "summary": artifact.get("summary"),
                            "created_at": artifact.get("created_at"),
                            "artifact_type": artifact.get("artifact_type"),
                            "top_insights": [str(item) for item in insights[:3]] if isinstance(insights, list) else [],
                            "recommended_followup_tasks": [str(item) for item in followups[:3]] if isinstance(followups, list) else [],
                        }
                    )
                if artifact.get("contract_id") in improvement_contracts:
                    key_points: List[str] = []
                    if isinstance(payload, dict):
                        for key in ("recommendations", "gaps", "sources_or_origin", "recommended_followup_tasks"):
                            value = payload.get(key)
                            if isinstance(value, list):
                                key_points = [str(item) for item in value[:3]]
                                if key_points:
                                    break
                    improvement_briefs.append(
                        {
                            "headline": artifact.get("headline"),
                            "summary": artifact.get("summary"),
                            "created_at": artifact.get("created_at"),
                            "artifact_type": artifact.get("artifact_type"),
                            "key_points": key_points,
                        }
                    )

            if not recent_successes:
                recent_successes = [
                    {
                        "task_id": artifact.get("task_id"),
                        "title": artifact.get("headline"),
                        "summary": artifact.get("summary"),
                        "created_at": artifact.get("created_at"),
                        "artifact_type": artifact.get("artifact_type"),
                    }
                    for artifact in recent_artifacts[:5]
                ]

            latest_offer_pack: Optional[Dict[str, Any]] = None
            for artifact in artifacts:
                if artifact.get("contract_id") == "offer_pack":
                    latest_offer_pack = artifact
                    break

            sales_launch: Dict[str, Any] = {
                "recommended_path": "Stripe Payment Links",
                "next_step": "Create one live $79 Signal Test payment link, then send it to 3 real prospects.",
                "docs": launch_docs[:4],
            }
            if isinstance(latest_offer_pack, dict):
                payload = latest_offer_pack.get("payload") if isinstance(latest_offer_pack.get("payload"), dict) else {}
                pricing = payload.get("pricing_options") if isinstance(payload, dict) else []
                price_points: List[str] = []
                if isinstance(pricing, list):
                    for option in pricing[:4]:
                        if not isinstance(option, dict):
                            continue
                        name = str(option.get("name") or "").strip()
                        price = str(option.get("price") or "").strip()
                        if name and price:
                            price_points.append(f"{name}: {price}")
                        elif price:
                            price_points.append(price)
                sales_launch.update(
                    {
                        "offer_name": latest_offer_pack.get("headline"),
                        "offer_summary": latest_offer_pack.get("summary"),
                        "offer_path": latest_offer_pack.get("path"),
                        "created_at": latest_offer_pack.get("created_at"),
                        "validation_prompt": str(payload.get("validation_prompt") or "").strip() if isinstance(payload, dict) else "",
                        "next_step": str(payload.get("recommended_next_step") or sales_launch["next_step"]).strip(),
                        "price_points": price_points,
                    }
                )

            return {
                "counts": {
                    "opportunities_total": len(top_opportunities),
                    "active_self_tasks": len(active_self_tasks),
                    "useful_outputs": len(recent_successes),
                    "artifacts_total": len(artifacts),
                    "learning_digests": len(learning_digests),
                    "improvement_briefs": len(improvement_briefs),
                },
                "top_opportunities": top_opportunities,
                "active_self_tasks": active_self_tasks[:6],
                "recent_successes": recent_successes[:5],
                "sales_launch": sales_launch,
                "learning_digests": learning_digests[:4],
                "improvement_briefs": improvement_briefs[:4],
                "recent_artifacts": recent_artifacts[:6],
            }

        @self.app.route('/api/workbench/summary', methods=['GET'])
        def api_workbench_summary():
            """Aggregate useful artifacts, self-tasks, and opportunities for the operator workbench."""
            try:
                return jsonify({"success": True, "workbench": _build_workbench_summary()})
            except Exception as e:
                logger.error("Workbench summary error: %s", e, exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/chat', methods=['POST'])
        def api_chat():
            """Chat with AI (OpenAI/OpenRouter via unified system or guardian.ask_ai fallback)."""
            try:
                data = request.get_json() or {}
                message = (data.get("message") or "").strip()
                conversation_id = _control_panel_chat_session_id(
                    data.get("conversation_id") or data.get("session_id") or "control_panel"
                )
                if not message:
                    return jsonify({"error": "message is required"}), 400
                return self._handle_control_panel_operator_chat(
                    message, conversation_id, _get_unified_system
                )
            except Exception as e:
                logger.error("Chat error: %s", e, exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/conversations", methods=["GET"])
        def api_conversations_list():
            body, code = _safe_stack_responses.build_conversations_list_response(
                self._conversation_store
            )
            return jsonify(body), code

        @self.app.route("/api/conversations", methods=["POST"])
        def api_conversations_create():
            """Allocate a new conversation id (no messages yet)."""
            body, code = _safe_stack_responses.build_conversation_create_response(
                self._conversation_store
            )
            return jsonify(body), code

        @self.app.route("/api/conversations/<conversation_id>", methods=["GET"])
        def api_conversations_get(conversation_id: str):
            body, code = _safe_stack_responses.build_conversation_detail_response(
                self._conversation_store,
                conversation_id,
                message_limit=CONTROL_PANEL_CHAT_RESPONSE_MESSAGES,
            )
            return jsonify(body), code

        @self.app.route("/api/conversations/<conversation_id>/messages", methods=["POST"])
        def api_conversations_append(conversation_id: str):
            try:
                body = request.get_json(silent=True) or {}
                role = str(body.get("role") or "user").strip().lower()
                content = str(body.get("content") or "").strip()
                if not content:
                    return jsonify({"success": False, "error": "content is required"}), 400
                cid = _control_panel_chat_session_id(conversation_id)
                msg = self._conversation_store.append_message(cid, role=role, content=content)
                return jsonify({"success": True, "message": msg})
            except Exception as e:
                logger.error("conversations append: %s", e, exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
        def api_conversations_delete(conversation_id: str):
            body, code = _safe_stack_responses.build_conversation_delete_response(
                self._conversation_store, conversation_id
            )
            return jsonify(body), code

        @self.app.route('/api/chat/history', methods=['GET'])
        def api_chat_history():
            """Return bounded, redacted control-panel chat history."""
            self._ensure_legacy_control_panel_import()
            conversation_id = (
                request.args.get("conversation_id")
                or request.args.get("session_id")
                or "control_panel"
            )
            body, code = _safe_stack_responses.build_chat_history_response(
                self._conversation_store,
                conversation_id,
                limit=CONTROL_PANEL_CHAT_RESPONSE_MESSAGES,
            )
            return jsonify(body), code

        @self.app.route('/api/chat/history', methods=['DELETE'])
        def api_chat_history_clear():
            """Clear one control-panel chat history session."""
            data = request.get_json(silent=True) or {}
            conversation_id = (
                data.get("conversation_id")
                or data.get("session_id")
                or request.args.get("conversation_id")
                or "control_panel"
            )
            body, code = _safe_stack_responses.build_chat_history_clear_response(
                self._conversation_store, str(conversation_id)
            )
            return jsonify(body), code

        @self.app.route("/api/brain/trace/latest", methods=["GET"])
        def api_brain_trace_latest():
            """Sanitized BrainPipeline trace summary (read-only)."""
            body, code = _safe_stack_responses.build_brain_trace_latest_response()
            return jsonify(body), code

        @self.app.route("/api/prompt-contracts/status", methods=["GET"])
        def api_prompt_contracts_status():
            """Read-only prompt-contract config and latest validation summary."""
            body, code = _safe_stack_responses.build_prompt_contracts_status_response()
            return jsonify(body), code

        @self.app.route("/api/governance/operator-confirmations", methods=["GET"])
        def api_governance_operator_confirmations_list():
            """Read-only operator confirmation diagnostics (mirrors Runtime API)."""
            try:
                limit = min(max(int(request.args.get("limit", 25)), 1), 50)
            except (TypeError, ValueError):
                limit = 25
            body, code = _safe_stack_responses.build_operator_confirmations_list_response(
                limit=limit,
                conversation_id=request.args.get("conversation_id"),
                status_filter=request.args.get("status"),
            )
            return jsonify(body), code

        @self.app.route(
            "/api/governance/operator-confirmations/<operator_confirmation_id>",
            methods=["GET"],
        )
        def api_governance_operator_confirmation_detail(operator_confirmation_id: str):
            body, code = _safe_stack_responses.build_operator_confirmation_detail_response(
                operator_confirmation_id
            )
            return jsonify(body), code

        @self.app.route("/api/self-improvement/proposals", methods=["GET"])
        def api_self_improvement_proposals_list():
            from project_guardian.self_improvement.proposal_queue import get_default_proposal_queue

            limit = min(max(int(request.args.get("limit", 50)), 1), 200)
            body, code = _safe_stack_responses.build_self_improvement_proposals_list_response(
                get_default_proposal_queue(), limit=limit
            )
            return jsonify(body), code

        @self.app.route("/api/memory/ranking/summary", methods=["GET"])
        def api_memory_ranking_summary():
            try:
                limit = min(max(int(request.args.get("limit", 10)), 1), 50)
            except (TypeError, ValueError):
                limit = 10
            body, code = _safe_stack_responses.build_memory_ranking_summary_response(
                conversation_store=self._conversation_store,
                limit=limit,
            )
            return jsonify(body), code

        @self.app.route("/api/self-improvement/proposals/<proposal_id>", methods=["GET"])
        def api_self_improvement_proposal_get(proposal_id: str):
            from project_guardian.self_improvement.proposal_queue import get_default_proposal_queue

            body, code = _safe_stack_responses.build_self_improvement_proposal_detail_response(
                get_default_proposal_queue(), proposal_id
            )
            return jsonify(body), code

        @self.app.route("/api/self-improvement/proposals/<proposal_id>/export_prompt", methods=["GET"])
        def api_self_improvement_proposal_export_prompt(proposal_id: str):
            from project_guardian.self_improvement.proposal_queue import get_default_proposal_queue

            body, code = _safe_stack_responses.build_self_improvement_prompt_export_response(
                get_default_proposal_queue(),
                proposal_id,
                target=request.args.get("target", "cursor"),
            )
            return jsonify(body), code

        @self.app.route("/api/self-improvement/proposals/<proposal_id>/status", methods=["POST"])
        def api_self_improvement_proposal_status(proposal_id: str):
            from project_guardian.self_improvement.proposal_queue import get_default_proposal_queue

            body_json = request.get_json(force=True, silent=True) or {}
            status = str(body_json.get("status") or "").strip().lower()
            note = body_json.get("note")
            body, code = _safe_stack_responses.build_self_improvement_proposal_status_update_response(
                get_default_proposal_queue(),
                proposal_id,
                status,
                note=str(note) if note is not None else None,
            )
            return jsonify(body), code

        @self.app.route('/api/income-status', methods=['GET'])
        def api_income_status():
            """Income/API module status (income_generator, harvest_engine, etc.) from unified system."""
            try:
                us = _get_unified_system()
                payload: Dict[str, Any] = {
                    "success": True,
                    "payment_providers": _build_payment_provider_status(us),
                }
                if us and hasattr(us, 'get_status'):
                    status = us.get_status()
                    income = status.get('income_modules') or {}
                    payload["income_modules"] = income
                    return jsonify(payload)
                payload["income_modules"] = {}
                payload["message"] = "Unified system not available"
                return jsonify(payload)
            except Exception as e:
                logger.error(f"Income status error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/wallet/accounts', methods=['GET'])
        def api_wallet_accounts_get():
            """List wallet sub-accounts and totals (unified Elysia wallet module)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, "modules"):
                    return jsonify({"success": False, "error": "Unified system not available"}), 400
                wallet = us.modules.get("wallet")
                if not wallet or not hasattr(wallet, "get_balance"):
                    return jsonify({"success": False, "error": "Wallet not available"}), 400
                bal = wallet.get_balance()
                return jsonify({"success": True, "balance": bal})
            except Exception as e:
                logger.error(f"Wallet list error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/wallet/accounts', methods=['POST'])
        def api_wallet_accounts_post():
            """Add a wallet sub-account (display name + optional id slug)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, "modules"):
                    return jsonify({"success": False, "error": "Unified system not available"}), 400
                wallet = us.modules.get("wallet")
                if not wallet or not hasattr(wallet, "add_account"):
                    return jsonify({"success": False, "error": "Wallet not available"}), 400
                data = request.get_json() or {}
                name = (data.get("name") or "").strip()
                if not name:
                    return jsonify({"success": False, "error": "name is required"}), 400
                rid = (data.get("id") or data.get("account_id") or "").strip() or None
                out = wallet.add_account(
                    name,
                    account_id=rid,
                    account_type=str(data.get("type", "virtual")),
                    currency=str(data.get("currency", "USD")),
                    initial_balance=float(data.get("balance", data.get("initial_balance", 0)) or 0),
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
                )
                status = 200 if out.get("success") else 400
                return jsonify(out), status
            except Exception as e:
                logger.error(f"Wallet add error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/harvest-report', methods=['POST'])
        def api_harvest_report():
            """Request a harvest/income report from HarvestEngine (Alpha Vantage, etc.)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, 'modules'):
                    return jsonify({"error": "Unified system not available"}), 400
                he = us.modules.get('harvest_engine')
                if not he:
                    return jsonify({"error": "HarvestEngine not available"}), 400
                report = None
                if hasattr(he, 'generate_income_report'):
                    report = he.generate_income_report("all")
                elif hasattr(he, 'get_account_status'):
                    report = he.get_account_status()
                else:
                    return jsonify({"error": "HarvestEngine has no report method"}), 400
                return jsonify({"success": True, "report": report})
            except Exception as e:
                logger.error(f"Harvest report error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/research-proposal', methods=['POST'])
        def api_research_proposal():
            """Create a research proposal via Architect/WebScout (Brave Search)."""
            try:
                us = _get_unified_system()
                if not us or not getattr(us, 'architect', None):
                    return jsonify({"error": "Unified system or Architect not available"}), 400
                arch = us.architect
                data = request.get_json() or {}
                topic = (data.get('topic') or data.get('query') or 'AI safety').strip() or 'AI safety'
                task_description = (data.get('task_description') or f'Summarize key findings and sources for: {topic}').strip()
                if hasattr(arch, 'create_research_proposal'):
                    result = arch.create_research_proposal(task_description, topic)
                    return jsonify({"success": True, "topic": topic, "result": result})
                if hasattr(arch, 'webscout') and arch.webscout:
                    # Fallback: use webscout search
                    out = arch.webscout.search(topic, max_results=5) if hasattr(arch.webscout, 'search') else {"results": []}
                    return jsonify({"success": True, "topic": topic, "result": out})
                return jsonify({"error": "Architect has no research proposal or WebScout"}), 400
            except Exception as e:
                logger.error(f"Research proposal error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/control/dream-cycle', methods=['POST'])
        def trigger_dream_cycle():
            """Trigger a dream cycle for memory consolidation."""
            try:
                result = {
                    "success": True,
                    "message": "Dream cycle initiated",
                    "activities": []
                }
                
                # If memory system available, trigger consolidation
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        # Save memory state
                        if hasattr(self.orchestrator.memory, 'save'):
                            self.orchestrator.memory.save()
                            result["activities"].append("Memory saved")
                        
                        # Consolidate if available
                        if hasattr(self.orchestrator.memory, 'consolidate'):
                            self.orchestrator.memory.consolidate()
                            result["activities"].append("Memory consolidation")
                    except Exception as e:
                        logger.warning(f"Memory operations failed: {e}")
                
                # If orchestrator has dreams/creativity component
                if hasattr(self.orchestrator, 'dreams') and self.orchestrator.dreams:
                    try:
                        dreams = self.orchestrator.dreams
                        if hasattr(dreams, 'dream_cycle'):
                            dreams.dream_cycle()
                            result["activities"].append("Dream cycle processing")
                        elif hasattr(dreams, 'begin_dream_cycle'):
                            thoughts = dreams.begin_dream_cycle(cycles=1)
                            result["activities"].append(f"Dream cycle: {len(thoughts)} thought(s)")
                            if thoughts:
                                result["dream_thoughts"] = thoughts
                    except Exception as e:
                        logger.warning(f"Dream cycle processing failed: {e}")
                
                # Log the dream cycle event via timeline if available
                if hasattr(self.orchestrator, 'timeline') and self.orchestrator.timeline:
                    try:
                        if hasattr(self.orchestrator.timeline, 'add_event'):
                            self.orchestrator.timeline.add_event(
                                event_type="dream_cycle",
                                actor="system",
                                description="Dream cycle triggered",
                                metadata=result
                            )
                            result["activities"].append("Event logged")
                    except Exception as e:
                        logger.warning(f"Timeline logging failed: {e}")
                
                if not result["activities"]:
                    result["message"] = "Dream cycle triggered (no operations performed)"
                    result["success"] = False
                
                return jsonify(result)
            except Exception as e:
                logger.error(f"Dream cycle error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/speak', methods=['POST'])
        def speak_message():
            """Trigger TTS speech via VoiceThread."""
            try:
                data = request.get_json() or {}
                message = (data.get("message") or "").strip()
                mode = data.get("mode", "guardian")
                if not message:
                    return jsonify({"success": False, "error": "No message provided"}), 400
                if hasattr(self.orchestrator, "speak_message"):
                    self.orchestrator.speak_message(message, mode=mode)
                    return jsonify({"success": True, "message": "Speaking"})
                if hasattr(self.orchestrator, "voice") and self.orchestrator.voice:
                    if hasattr(self.orchestrator.voice, "set_mode"):
                        self.orchestrator.voice.set_mode(mode)
                    self.orchestrator.voice.speak(message)
                    return jsonify({"success": True, "message": "Speaking"})
                return jsonify({"success": False, "error": "Voice not available"}), 503
            except Exception as e:
                logger.error(f"Speak error: {e}", exc_info=True)
                return jsonify({"error": str(e), "success": False}), 500
                
        @self.app.route('/api/memory/search')
        def search_memory():
            """Search memories. Forces load (memory-detail route). Bounded by limit param (default 10)."""
            try:
                query = request.args.get('q', '')
                try:
                    limit = min(int(request.args.get('limit', 10)), 100)
                except (ValueError, TypeError):
                    limit = 10
                if not self.orchestrator.memory:
                    return jsonify({"success": False, "results": []})
                mem = self.orchestrator.memory
                if hasattr(mem, 'search_memories') and query:
                    results = mem.search_memories(query, limit=limit)
                    return jsonify({"success": True, "results": results[:limit]})
                # Fallback: bounded scan (no dump_all)
                if hasattr(mem, 'get_recent_memories'):
                    entries = mem.get_recent_memories(limit=min(UI_MEMORY_RECENT_LIMIT, limit * 10), load_if_needed=True)
                    q_lower = query.lower()
                    results = []
                    for m in entries:
                        text = m.get('thought', m.get('text', str(m)))
                        if q_lower in str(text).lower():
                            results.append({"thought": text, "category": m.get("category", "")})
                            if len(results) >= limit:
                                break
                    return jsonify({"success": True, "results": results[:limit]})
                return jsonify({"success": True, "results": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/tasks/submit', methods=['POST'])
        def submit_task():
            """Submit a task to the system."""
            try:
                data = request.get_json() or {}
                # Support both formats: {type, payload, priority} and {code, priority} from Control tab
                task_type = data.get('type') or ''
                payload = data.get('payload') or {}
                if data.get('code') is not None:
                    task_type = task_type or 'custom'
                    payload = dict(payload, code=data.get('code'))
                
                # Submit task through ModuleRegistry
                if self.orchestrator.module_registry:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        self.orchestrator.module_registry.route_task({
                            "type": task_type or "general",
                            "payload": payload
                        })
                    )
                    loop.close()
                    if isinstance(result, dict) and result.get("success") is False:
                        return jsonify({
                            "success": False,
                            "error": result.get("error", "Task routing failed"),
                            "task_id": result.get("task_id"),
                        }), 400
                    return jsonify({"success": True, "result": result})
                else:
                    return jsonify({"success": False, "error": "ModuleRegistry not available"}), 400
            except Exception as e:
                logger.error(f"Task submission error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/modules/list')
        def list_modules():
            """List all registered modules."""
            try:
                if self.orchestrator.module_registry:
                    try:
                        status = self.orchestrator.module_registry.get_registry_status()
                        modules = []
                        for module_name in status.get("module_names", []):
                            module_info = self.orchestrator.module_registry.get_module_status(module_name)
                            if module_info:
                                modules.append(module_info)
                        return jsonify({"success": True, "modules": modules})
                    except AttributeError:
                        # Fallback if get_registry_status doesn't exist
                        module_names = self.orchestrator.module_registry.list_modules() if hasattr(self.orchestrator.module_registry, 'list_modules') else []
                        modules = [{"name": name, "capabilities": []} for name in module_names]
                        return jsonify({"success": True, "modules": modules})
                return jsonify({"success": False, "modules": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/gaps/list')
        def list_gaps():
            """List capability gaps."""
            try:
                if self.orchestrator.auto_module_creator:
                    unresolved = self.orchestrator.auto_module_creator.list_unresolved_gaps()
                    gaps = []
                    for gap in unresolved:
                        gaps.append({
                            "gap_id": gap.gap_id,
                            "required_capability": gap.required_capability,
                            "task_description": gap.task_description,
                            "detected_at": gap.detected_at.isoformat()
                        })
                    return jsonify({"success": True, "gaps": gaps})
                return jsonify({"success": True, "gaps": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/gaps/create', methods=['POST'])
        def create_module_for_gap():
            """Manually trigger module creation for a gap."""
            try:
                data = request.get_json() or {}
                gap_id = data.get('gap_id')
                
                if not gap_id:
                    return jsonify({"success": False, "error": "gap_id required"}), 400
                
                if self.orchestrator.auto_module_creator:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        self.orchestrator.auto_module_creator.create_module_for_gap(gap_id)
                    )
                    loop.close()
                    return jsonify(result)
                return jsonify({"success": False, "error": "AutoModuleCreator not available"}), 400
            except Exception as e:
                logger.error(f"Module creation error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/tasks/list')
        def list_tasks():
            """Active TaskEngine tasks, GlobalTaskQueue jobs, and TASKS/*.md drop files."""
            try:
                orch = self.orchestrator
                if orch is None:
                    return jsonify({"success": False, "queue_size": 0, "tasks": [], "error": "Orchestrator not available"}), 503

                rows: List[Dict[str, Any]] = []
                queue_size = 0

                tq = getattr(getattr(orch, "elysia_loop", None), "task_queue", None) or getattr(orch, "task_queue", None)
                if tq and hasattr(tq, "get_queue_size"):
                    queue_size = int(tq.get_queue_size())

                # Guardian TaskEngine (in-memory operational tasks)
                task_engine = getattr(orch, "tasks", None)
                if task_engine and hasattr(task_engine, "get_active_tasks"):
                    for t in task_engine.get_active_tasks():
                        if not isinstance(t, dict):
                            continue
                        item = {"source": "task_engine"}
                        for k, v in t.items():
                            if k == "logs":
                                item[k] = v[-5:] if isinstance(v, list) else v
                            else:
                                item[k] = v
                        rows.append(item)

                # Elysia loop priority queue (serializable subset)
                if tq and hasattr(tq, "list_tasks"):
                    try:
                        for raw in tq.list_tasks(limit=80):
                            fn = getattr(raw.func, "__name__", None) or type(raw.func).__name__
                            st = raw.status.value if hasattr(raw.status, "value") else str(raw.status)
                            meta = raw.metadata or {}
                            safe_meta = {
                                k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v)[:400]
                                for k, v in meta.items()
                            }
                            rows.append({
                                "source": "loop_queue",
                                "task_id": raw.task_id,
                                "status": st,
                                "priority": raw.priority,
                                "module": raw.module,
                                "created_at": raw.created_at.isoformat() if hasattr(raw.created_at, "isoformat") else str(raw.created_at),
                                "func": fn,
                                "metadata": safe_meta,
                            })
                    except Exception as e:
                        logger.debug("list_tasks loop_queue slice failed: %s", e)

                # Disk drop files (TASKS/*.md)
                tasks_dir = getattr(orch, "tasks_dir", None)
                if tasks_dir:
                    td = Path(tasks_dir)
                    if td.is_dir():
                        for fp in sorted(td.glob("*.md"))[:40]:
                            rows.append({
                                "source": "disk",
                                "file": fp.name,
                                "path": str(fp.resolve()),
                                "status": "pending_file",
                            })

                return jsonify({"success": True, "queue_size": queue_size, "tasks": rows})
            except Exception as e:
                logger.error("list_tasks: %s", e, exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500
                
        # Introspection API Endpoints (behavior / correlations / patterns backed by core + memory)
        @self.app.route('/api/introspection/comprehensive')
        def get_comprehensive_report():
            """Get comprehensive introspection report."""
            try:
                # Build a text report for frontend parsing; fallback to reflector if available
                report_text = "[Guardian Identity]\nSystem: Elysia / Project Guardian\nStatus: Operational\n\n"
                report_text += "[Guardian Behavior]\nRuntime snapshot (autonomy / introspection / decider tail).\n"
                if hasattr(self.orchestrator, 'reflector') and self.orchestrator.reflector:
                    try:
                        r = self.orchestrator.reflector
                        if hasattr(r, 'get_comprehensive_report'):
                            report_text = r.get_comprehensive_report()
                        elif hasattr(r, 'get_identity_summary'):
                            ident = r.get_identity_summary()
                            if ident:
                                report_text = ident + "\n\n" + report_text.split("[Guardian Behavior]", 1)[-1]
                        elif hasattr(r, 'get_identity_report'):
                            ident = r.get_identity_report()
                            if ident:
                                report_text = "[Guardian Identity]\n" + str(ident) + "\n\n" + report_text.split("[Guardian Behavior]", 1)[-1]
                    except Exception:
                        pass
                try:
                    orch = self.orchestrator
                    snap: Dict[str, Any] = {}
                    for key, attr in (
                        ("last_autonomy", "_last_autonomy_result"),
                        ("last_introspection", "_last_introspection_result"),
                        ("last_autonomy_next", "_last_autonomy_next_result"),
                    ):
                        v = getattr(orch, attr, None)
                        if v is not None:
                            snap[key] = v if isinstance(v, (dict, list, str, int, float, bool)) else str(v)[:2000]
                    ra = getattr(orch, "_decider_recent_actions", None)
                    if isinstance(ra, list) and ra:
                        snap["decider_recent_actions_tail"] = [str(x) for x in ra[-20:]]
                    if snap:
                        report_text += "\n[Runtime behavior snapshot]\n"
                        report_text += json.dumps(snap, ensure_ascii=False, indent=0)[:8000] + "\n"
                except Exception:
                    pass
                return jsonify({"success": True, "report": report_text})
            except Exception as e:
                logger.error(f"Comprehensive report error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/debug')
        def get_introspection_debug():
            """Get last introspection decision (for debug view)."""
            try:
                result = getattr(self.orchestrator, "_last_introspection_result", None)
                if result is None:
                    return jsonify({"success": True, "debug": {"note": "No introspection run yet"}})
                return jsonify({"success": True, "debug": result})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/introspection/identity')
        def get_identity_summary():
            """Get identity summary from reflector or IdentityCore."""
            try:
                identity = {
                    "name": "Elysia",
                    "role": "Autonomous AI Safety System",
                    "system_name": "Project Guardian",
                    "oath": "I exist to learn, adapt, and protect the future."
                }
                if hasattr(self.orchestrator, 'reflector') and self.orchestrator.reflector:
                    try:
                        r = self.orchestrator.reflector
                        if hasattr(r, 'get_identity_summary'):
                            identity["summary_text"] = r.get_identity_summary()
                        if hasattr(r, 'summarize_self'):
                            s = r.summarize_self()
                            identity["uptime_seconds"] = s.get("uptime_seconds")
                            identity["active_tasks"] = s.get("active_tasks")
                            identity["memory_stats"] = s.get("memory_stats", {})
                            identity["system_health"] = s.get("system_health", {})
                    except Exception:
                        pass
                return jsonify({"success": True, "identity": identity})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/behavior')
        def get_behavior_report():
            """Get behavior report from last autonomy / introspection / decider tail."""
            try:
                orch = self.orchestrator
                behavior: Dict[str, Any] = {
                    "last_autonomy": getattr(orch, "_last_autonomy_result", None),
                    "last_introspection": getattr(orch, "_last_introspection_result", None),
                    "last_autonomy_next": getattr(orch, "_last_autonomy_next_result", None),
                    "decider_recent_actions_tail": list(getattr(orch, "_decider_recent_actions", []) or [])[-24:],
                }
                for k, v in list(behavior.items()):
                    if v is not None and not isinstance(v, (dict, list, str, int, float, bool)):
                        behavior[k] = str(v)[:4000]
                return jsonify({"success": True, "behavior": behavior})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/health')
        def get_memory_health():
            """Get memory health analysis. Non-forcing (uses loaded-aware state)."""
            try:
                health = {"status": "unknown", "health_score": 0, "total_memories": 0, "warnings": []}
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_memory_state'):
                            st = mem.get_memory_state(load_if_needed=False)
                            count = st.get("memory_count")
                            loaded = st.get("memory_loaded", False)
                        elif hasattr(mem, 'get_memory_count'):
                            count = mem.get_memory_count(load_if_needed=False)
                            loaded = count is not None
                        else:
                            count, loaded = 0, False
                        health["total_memories"] = count if count is not None else 0
                        health["memory_loaded"] = loaded
                        if not loaded:
                            health["status"] = "loading"
                            health["warnings"] = ["Memory not yet loaded (deferred)"]
                        elif (count or 0) > 0:
                            health["health_score"] = min(1.0, 0.5 + ((count or 0) / 10000) * 0.5)
                            health["status"] = "healthy"
                        else:
                            health["health_score"] = 0.5
                            health["status"] = "empty"
                    except Exception:
                        health["warnings"] = ["Could not read memory count"]
                return jsonify({"success": True, "health": health})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/focus')
        def get_focus_analysis():
            """Get focus analysis. Forces load (memory-detail route)."""
            try:
                try:
                    hours = int(request.args.get("hours", 24))
                except (TypeError, ValueError):
                    hours = 24
                hours = max(1, min(168, hours))
                focus = {
                    "time_window_hours": hours,
                    "primary_focus": "System monitoring",
                    "activity_count": 0,
                    "priority_trend": "stable",
                    "most_active_period": "N/A",
                    "focus_distribution": {},
                }
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_recent_memories'):
                            entries = mem.get_recent_memories(limit=UI_MEMORY_RECENT_LIMIT, load_if_needed=True)
                        else:
                            entries = []
                        focus["activity_count"] = len(entries)
                        if entries:
                            cats = {}
                            for m in entries:
                                c = (m.get("category") or "general") if isinstance(m, dict) else "general"
                                cats[c] = cats.get(c, 0) + 1
                            focus["focus_distribution"] = cats
                            if cats:
                                focus["primary_focus"] = max(cats, key=cats.get)
                    except Exception:
                        pass
                return jsonify({"success": True, "focus": focus})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/correlations')
        def get_memory_correlations():
            """Get memory correlations."""
            try:
                keyword = (request.args.get("keyword") or "").strip()
                if not keyword:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "keyword query parameter is required",
                            }
                        ),
                        400,
                    )
                try:
                    thr = float(request.args.get("threshold", 0.3) or 0.3)
                except (TypeError, ValueError):
                    thr = 0.3
                hits: List[Dict[str, Any]] = []
                mem = getattr(self.orchestrator, "memory", None)
                if mem is not None and hasattr(mem, "search_memories"):
                    try:
                        rows = mem.search_memories(keyword, limit=40) or []
                    except Exception:
                        rows = []
                    for r in rows:
                        if not isinstance(r, dict):
                            continue
                        thought = str(r.get("thought") or "")
                        hits.append(
                            {
                                "time": r.get("time"),
                                "category": r.get("category"),
                                "snippet": thought[:400],
                                "keyword_match": keyword.lower() in thought.lower(),
                            }
                        )
                return jsonify(
                    {
                        "success": True,
                        "correlations": {
                            "keyword": keyword,
                            "threshold": thr,
                            "hit_count": len(hits),
                            "hits": hits[:24],
                        },
                    }
                )
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/patterns')
        def get_memory_patterns():
            """Category distribution from recent memories (lightweight patterns)."""
            try:
                patterns: Dict[str, Any] = {
                    "categories": {},
                    "sample_count": 0,
                    "source": "recent_memory_categories",
                }
                mem = getattr(self.orchestrator, "memory", None)
                if mem is not None and hasattr(mem, "get_recent_memories"):
                    try:
                        entries = mem.get_recent_memories(
                            limit=min(UI_MEMORY_RECENT_LIMIT, 120),
                            load_if_needed=True,
                        )
                    except Exception:
                        entries = []
                    patterns["sample_count"] = len(entries)
                    cats: Dict[str, int] = {}
                    for m in entries or []:
                        if not isinstance(m, dict):
                            continue
                        c = str(m.get("category") or "general").strip() or "general"
                        cats[c] = cats.get(c, 0) + 1
                    patterns["categories"] = cats
                return jsonify({"success": True, "patterns": patterns})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        # Learning API Endpoints (use project_guardian.auto_learning)
        @self.app.route('/api/learning/test-reddit', methods=['POST'])
        def test_reddit_learning():
            """Test Reddit learning capability."""
            try:
                from project_guardian.auto_learning import fetch_reddit, compress_with_llm
                llm = None
                if hasattr(self.orchestrator, 'chat_with_llm'):
                    llm = lambda m: self.orchestrator.chat_with_llm(m)
                else:
                    try:
                        import sys
                        main_mod = sys.modules.get("__main__")
                        if main_mod:
                            status_sys = getattr(main_mod, "_status_system", None)
                            if status_sys and hasattr(status_sys, "chat_with_llm"):
                                llm = lambda m: status_sys.chat_with_llm(m)
                    except Exception:
                        pass
                items = fetch_reddit("MachineLearning", limit=3)
                for item in items:
                    item["compressed"] = compress_with_llm(item.get("text", ""), llm, module_name="summarizer")
                return jsonify({
                    "success": True,
                    "message": f"Fetched {len(items)} posts from r/MachineLearning",
                    "result": {"data": {"posts_processed": len(items)}, "status": "success", "message": f"Test OK: {len(items)} posts"}
                })
            except Exception as e:
                logger.error(f"Reddit learning test error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/learning/summary')
        def get_learning_summary():
            """Get learning summary from learned JSONL files on thumb drive."""
            try:
                from project_guardian.auto_learning import get_learned_storage_path
                storage = get_learned_storage_path()
                total = 0
                last_learning = "Never"
                last_mtime = 0
                for f in storage.glob("learned_*.jsonl"):
                    try:
                        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                            n = sum(1 for _ in fp)
                        total += n
                        if f.stat().st_mtime > last_mtime:
                            last_mtime = f.stat().st_mtime
                            last_learning = datetime.fromtimestamp(last_mtime).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                return jsonify({
                    "success": True,
                    "summary": {
                        "total_articles": total,
                        "reddit_posts": total,
                        "rss_entries": total,
                        "last_learning": last_learning
                    }
                })
            except Exception as e:
                logger.error(f"Learning summary error: {e}", exc_info=True)
                return jsonify({"success": True, "summary": {"total_articles": 0, "reddit_posts": 0, "rss_entries": 0, "last_learning": "Never"}})

        @self.app.route('/api/learning/settings', methods=['GET'])
        def get_learning_settings():
            """Return learning options (e.g. use_headless_browser)."""
            try:
                from project_guardian.auto_learning import load_learning_config
                cfg = load_learning_config()
                return jsonify({"success": True, "use_headless_browser": bool(cfg.get("use_headless_browser", False))})
            except Exception as e:
                logger.debug(f"Learning settings error: {e}")
                return jsonify({"success": True, "use_headless_browser": False})

        @self.app.route('/api/learning/settings', methods=['POST'])
        def set_learning_settings():
            """Update learning options (e.g. use_headless_browser)."""
            try:
                data = request.get_json() or {}
                use_headless = bool(data.get("use_headless_browser", False))
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config() or {}
                cfg["use_headless_browser"] = use_headless
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "use_headless_browser": use_headless})
            except Exception as e:
                logger.error(f"Learning settings error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/linked-accounts', methods=['GET'])
        def get_linked_accounts():
            """Return which accounts are linked (no secrets)."""
            try:
                from project_guardian.auto_learning import load_learning_config
                import os
                cfg = load_learning_config()
                fb = bool((cfg.get("facebook_access_token") or "").strip() or (os.environ.get("FACEBOOK_ACCESS_TOKEN") or "").strip())
                tw = bool((cfg.get("twitter_bearer_token") or "").strip() or (os.environ.get("TWITTER_BEARER_TOKEN") or "").strip())
                return jsonify({"success": True, "facebook": fb, "twitter": tw})
            except Exception as e:
                logger.debug(f"Linked accounts error: {e}")
                return jsonify({"success": True, "facebook": False, "twitter": False})

        @self.app.route('/api/learning/link-facebook', methods=['POST'])
        def link_facebook_account():
            """Save the user's Facebook access token to config so Elysia can use their account for learning."""
            try:
                data = request.get_json() or {}
                token = (data.get("token") or "").strip()
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config()
                if not cfg:
                    cfg = {}
                cfg["facebook_access_token"] = token
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "linked": bool(token), "message": "Facebook account linked" if token else "Facebook token cleared"})
            except Exception as e:
                logger.error(f"Link Facebook error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/link-twitter', methods=['POST'])
        def link_twitter_account():
            """Save the user's X (Twitter) Bearer Token to config so Elysia can learn from Twitter search."""
            try:
                data = request.get_json() or {}
                token = (data.get("token") or "").strip()
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config()
                if not cfg:
                    cfg = {}
                cfg["twitter_bearer_token"] = token
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "linked": bool(token), "message": "X (Twitter) account linked" if token else "Twitter token cleared"})
            except Exception as e:
                logger.error(f"Link Twitter error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/settings/income-keys', methods=['GET'])
        def get_income_keys_settings():
            """Income API keys status for Control Panel (no secrets)."""
            try:
                from project_guardian.api_key_manager import income_keys_ui_status

                return jsonify({"success": True, **income_keys_ui_status()})
            except Exception as e:
                logger.error(f"Income keys GET error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/settings/income-keys', methods=['POST'])
        def post_income_keys_settings():
            """Save Gumroad/Stripe to config/api_keys.json or clear file entries (does not change env)."""
            try:
                data = request.get_json() or {}
                clear_gumroad = bool(data.get("clear_gumroad"))
                clear_stripe = bool(data.get("clear_stripe"))
                raw_g = data.get("gumroad_access_token")
                raw_s = data.get("stripe_secret_key")
                g_arg = raw_g.strip() if isinstance(raw_g, str) and raw_g.strip() else None
                s_arg = raw_s.strip() if isinstance(raw_s, str) and raw_s.strip() else None
                if not clear_gumroad and not clear_stripe and not g_arg and not s_arg:
                    return jsonify({"success": False, "error": "Nothing to save or clear"}), 400
                from project_guardian.api_key_manager import persist_income_keys_to_config_file

                persist_income_keys_to_config_file(
                    gumroad_access_token=g_arg,
                    stripe_secret_key=s_arg,
                    clear_gumroad=clear_gumroad,
                    clear_stripe=clear_stripe,
                )
                harvest_refreshed = False
                harvest_refresh_detail: Optional[Dict[str, Any]] = None
                try:
                    orch = getattr(self, "orchestrator", None)
                    us = getattr(orch, "_unified_system", None) if orch is not None else None
                    mods = getattr(us, "modules", None) if us is not None else None
                    if isinstance(mods, dict):
                        from elysia_sub_modules import refresh_harvest_engine_in_modules

                        harvest_refresh_detail = refresh_harvest_engine_in_modules(mods)
                        harvest_refreshed = bool(harvest_refresh_detail.get("ok"))
                except Exception as ex:
                    logger.warning("Harvest Engine refresh after income keys save: %s", ex)
                msg_parts = []
                if clear_gumroad:
                    msg_parts.append("Gumroad removed from config file")
                if clear_stripe:
                    msg_parts.append("Stripe removed from config file")
                if g_arg:
                    msg_parts.append("Gumroad token saved")
                if s_arg:
                    msg_parts.append("Stripe key saved")
                if harvest_refreshed:
                    msg_parts.append("Harvest Engine reloaded in this process")
                elif harvest_refresh_detail and not harvest_refresh_detail.get("ok"):
                    msg_parts.append("Harvest reload skipped or failed (see logs)")
                return jsonify(
                    {
                        "success": True,
                        "message": "; ".join(msg_parts) or "Updated",
                        "harvest_engine_refreshed": harvest_refreshed,
                        "harvest_refresh": harvest_refresh_detail,
                    }
                )
            except Exception as e:
                logger.error(f"Income keys POST error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/start', methods=['POST'])
        def start_learning():
            """Start a learning session (Reddit, RSS, ChatGPT chatlogs) via auto_learning."""
            try:
                data = request.get_json() or {}
                platform = data.get('platform', 'reddit')
                query = data.get('query', '')
                max_items = max(2, min(20, int(data.get('max_items', 5))))
                
                from project_guardian.auto_learning import (
                    run_learning_session,
                    run_mistral_chained_learning_session,
                    get_learned_storage_path,
                    get_chatlogs_path,
                    load_learning_config,
                    DEFAULT_REDDIT_SUBS,
                    DEFAULT_RSS_FEEDS,
                    DEFAULT_FACEBOOK_PAGES,
                    DEFAULT_TWITTER_SEARCH_QUERIES,
                )
                import os
                cfg = load_learning_config()
                storage = get_learned_storage_path()
                chatlogs = get_chatlogs_path()
                facebook_token = cfg.get("facebook_access_token") or os.environ.get("FACEBOOK_ACCESS_TOKEN") or ""
                twitter_token = cfg.get("twitter_bearer_token") or os.environ.get("TWITTER_BEARER_TOKEN") or ""
                llm = None
                if hasattr(self.orchestrator, 'chat_with_llm'):
                    llm = lambda m: self.orchestrator.chat_with_llm(m)
                else:
                    try:
                        import sys
                        main_mod = sys.modules.get("__main__")
                        if main_mod:
                            status_sys = getattr(main_mod, "_status_system", None)
                            if status_sys and hasattr(status_sys, "chat_with_llm"):
                                llm = lambda m: status_sys.chat_with_llm(m)
                    except Exception:
                        pass
                reddit_subs = cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS
                rss_feeds = cfg.get("rss_feeds") or DEFAULT_RSS_FEEDS
                facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
                twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
                chatlogs_path = chatlogs
                web_urls = []
                if platform == 'reddit':
                    subs = [query.replace(" ", "") if query else "MachineLearning"]
                    reddit_subs = subs
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'rss':
                    reddit_subs = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'facebook':
                    reddit_subs = []
                    rss_feeds = []
                    twitter_search_queries = []
                    chatlogs_path = None
                    if query:
                        facebook_pages = [p.strip() for p in query.split(",") if p.strip()]
                    if not facebook_pages:
                        facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
                elif platform == 'twitter':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    chatlogs_path = None
                    if query:
                        twitter_search_queries = [q.strip() for q in query.split(",") if q.strip()]
                    if not twitter_search_queries:
                        twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
                elif platform == 'chatgpt' or platform == 'chatlogs':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = chatlogs
                elif platform == 'web':
                    web_urls = [u.strip() for u in query.split(",") if u.strip() and (u.startswith("http://") or u.startswith("https://"))]
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'all':
                    raw_w = cfg.get("web_urls") or []
                    web_urls = [
                        u.strip() for u in raw_w
                        if isinstance(u, str) and u.strip().startswith(("http://", "https://"))
                    ][:5]
                elif platform == 'mistral_chain':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    web_urls = []
                    chatlogs_path = chatlogs
                else:
                    pass
                if platform not in ('web', 'all', 'mistral_chain'):
                    web_urls = []
                
                memory = None
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    memory = self.orchestrator.memory
                if platform == 'mistral_chain':
                    topics_use = list(cfg.get("topics") or [])
                    if query:
                        extras = [t.strip() for t in query.split(",") if t.strip()]
                        topics_use = extras + [t for t in topics_use if t not in extras]
                    result = run_mistral_chained_learning_session(
                        storage_path=storage,
                        topics=topics_use,
                        memory=memory,
                        llm_callback=llm,
                        chatlogs_path=chatlogs_path,
                        twitter_bearer_token=twitter_token or None,
                        default_reddit_subs=cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS,
                        seed_twitter_queries=cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES,
                    )
                    if result.get("mistral_chained_error"):
                        return jsonify({
                            "success": False,
                            "error": f"Mistral chained learning failed (is Ollama running?): {result.get('mistral_chained_error')}",
                        }), 500
                else:
                    result = run_learning_session(
                        storage_path=storage,
                        topics=[],
                        reddit_subs=reddit_subs,
                        rss_feeds=rss_feeds,
                        chatlogs_path=chatlogs_path,
                        web_urls=web_urls if web_urls else None,
                        facebook_pages=facebook_pages if (platform == 'facebook' or platform == 'all') and facebook_token else None,
                        facebook_access_token=facebook_token or None,
                        twitter_search_queries=twitter_search_queries if (platform == 'twitter' or platform == 'all') and twitter_token else None,
                        twitter_bearer_token=twitter_token or None,
                        max_per_source=max_items,
                        max_chatlogs=max_items,
                        llm_callback=llm,
                        memory=memory,
                    )
                
                mc = result.get("memory_count", 0)
                msg = f"Saved {result.get('saved', 0)} items to {result.get('file', 'learned')}"
                if mc:
                    msg += f" ({mc} piped to memory)"
                return jsonify({
                    "success": True,
                    "result": {
                        "status": "success",
                        "message": msg,
                        "data": {
                            "posts_processed": result.get("saved", 0),
                            "entries_processed": result.get("saved", 0),
                            "articles_processed": result.get("saved", 0),
                            "memory_count": mc,
                        }
                    }
                })
            except Exception as e:
                logger.error(f"Learning start error: {e}", exc_info=True)
                return jsonify({"error": str(e), "success": False}), 500
                
    def _setup_socketio(self):
        """Setup SocketIO event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            logger.info("Client connected to control panel")
            emit('status_update', {"message": "Connected"})
    
    def _check_port_available(self, host: str, port: int) -> bool:
        """Check if a port is available for binding."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, int(port)))
                return True
        except (OSError, TypeError, ValueError):
            return False
    
    def _find_available_port(self, start_port: int, max_attempts: int = 10) -> int:
        """Find an available port starting from start_port."""
        for i in range(max_attempts):
            port = start_port + i
            if self._check_port_available(self.host, port):
                return port
        raise OSError(f"Could not find available port in range {start_port}-{start_port + max_attempts - 1}")

    def _probe_server_listening(self, timeout: float = 0.5) -> bool:
        """Probe the configured dashboard socket once."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((self.host, self._actual_port or self.port)) == 0
        except Exception:
            return False
    
    def _wait_for_server_ready(self, timeout: float = 10.0) -> bool:
        """Wait for server to be ready by checking if port is listening."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check for server errors first (fast failure)
            if self._server_error:
                logger.error(f"[DASHBOARD] Server error detected during readiness check: {self._server_error}")
                return False
            
            if self._probe_server_listening(timeout=0.5):
                self._server_listening = True
                return True
            time.sleep(0.1)
        self._server_listening = False
        return False
            
    def start(self, debug: bool = False, source: str = "unknown"):
        """
        Start the web server (idempotent - only starts once per process).
        
        Args:
            debug: Enable debug mode
            source: Call site identifier for instrumentation
        """
        global _dashboard_started, _dashboard_start_attempts
        
        # Module-level guard: prevent multiple dashboard starts
        with _dashboard_start_lock:
            _dashboard_start_attempts += 1
            attempt_num = _dashboard_start_attempts
            thread_name = threading.current_thread().name
            
            if _dashboard_started:
                logger.info(
                    "[DASHBOARD] start attempt %d source=%s thread=%s - Already started; skipping",
                    attempt_num, source, thread_name
                )
                return
            
            # Instance-level guard (defensive)
            if self.running:
                logger.warning(
                    "[DASHBOARD] start attempt %d source=%s thread=%s - Instance already running; skipping",
                    attempt_num, source, thread_name
                )
                return
            
            # Check port availability and find alternative if needed
            if not self._check_port_available(self.host, self.port):
                logger.warning(
                    f"[DASHBOARD] Port {self.port} is in use, attempting to find alternative..."
                )
                try:
                    self.port = self._find_available_port(self.port)
                    logger.info(f"[DASHBOARD] Using port {self.port} instead")
                except OSError as e:
                    logger.error(f"[DASHBOARD] Could not find available port: {e}")
                    raise
            
            # Reset readiness event
            self._server_ready.clear()
            self._server_listening = False
            self._server_error = None
            self._actual_port = self.port
            
            # Mark as started BEFORE actually starting (prevents race conditions)
            _dashboard_started = True
            self.running = True
            
            logger.info(
                "[DASHBOARD] start attempt %d source=%s thread=%s - Starting Elysia Control Panel on http://%s:%s",
                attempt_num, source, thread_name, self.host, self.port
            )
        
        # Start in background thread
        def run_server():
            global _dashboard_started
            try:
                logger.info(
                    f"[DASHBOARD] Server thread starting - binding to {self.host}:{self.port} (PID: {os.getpid()})"
                )
                self.socketio.run(
                    self.app,
                    host=self.host,
                    port=self.port,
                    debug=debug,
                    use_reloader=False,
                    allow_unsafe_werkzeug=True
                )
            except OSError as e:
                if "Address already in use" in str(e) or "address is already in use" in str(e).lower():
                    logger.error(f"[DASHBOARD] Port {self.port} is already in use: {e}")
                    self._server_error = f"Port {self.port} already in use"
                else:
                    logger.error(f"[DASHBOARD] Server OSError: {e}")
                    self._server_error = str(e)
                # Reset flag on error so it can be retried
                with _dashboard_start_lock:
                    _dashboard_started = False
                    self.running = False
                    self._server_listening = False
            except Exception as e:
                logger.error(f"[DASHBOARD] Server error: {e}", exc_info=True)
                self._server_error = str(e)
                # Reset flag on error so it can be retried
                with _dashboard_start_lock:
                    _dashboard_started = False
                    self.running = False
                    self._server_listening = False
            finally:
                if self._server_error:
                    self._server_ready.set()
            
        server_thread = threading.Thread(target=run_server, daemon=True, name="UIControlPanel-Server")
        server_thread.start()
        
        # Wait briefly so startup doesn't stall the main thread. Timeouts stay non-fatal,
        # but immediate server errors are surfaced to direct callers.
        time.sleep(0.3)
        if self._wait_for_server_ready(timeout=2.0):
            self._server_listening = True
            self._server_ready.set()
            logger.info(
                f"[DASHBOARD] Server is listening on http://{self.host}:{self.port} (PID: {os.getpid()})"
            )
        else:
            self._server_ready.set()
            if self._server_error:
                logger.warning(f"[DASHBOARD] Server failed readiness check: {self._server_error}")
                raise RuntimeError(f"Dashboard failed to start: {self._server_error}")
            else:
                logger.warning(
                    "[DASHBOARD] Server did not become ready in 2s (panel may load in a few seconds); continuing startup"
                )
        
    def stop(self):
        """Stop the web server."""
        global _dashboard_started
        with _dashboard_start_lock:
            _dashboard_started = False
            self.running = False
            self._server_listening = False
        logger.info("Control panel stopped")


def reset_dashboard_guard():
    """
    Reset the dashboard start guard (for testing only).
    """
    global _dashboard_started, _dashboard_start_attempts
    with _dashboard_start_lock:
        _dashboard_started = False
        _dashboard_start_attempts = 0
    logger.debug("[DASHBOARD] Guard reset (for testing)")


def create_control_panel(orchestrator, host: str = "127.0.0.1", port: int = 5000):
    """
    Create and return a UIControlPanel instance.
    
    Args:
        orchestrator: SystemOrchestrator instance
        host: Host to bind to
        port: Port to listen on
        
    Returns:
        UIControlPanel instance
    """
    return UIControlPanel(orchestrator, host, port)
