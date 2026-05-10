# project_guardian/ui/app.py
# FastAPI Control Panel for Project Guardian
# Local-only web UI for status, review queue, and task control

import subprocess
import json
import re
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from fastapi import FastAPI, Request, Form, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates
    FASTAPI_AVAILABLE = True
    FASTAPI_IMPORT_ERROR = None
except ImportError:
    FASTAPI_AVAILABLE = False
    FASTAPI_IMPORT_ERROR = "FastAPI dependencies are not installed"
    # Dummy classes if FastAPI not available
    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass
        def middleware(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    class Request:
        pass
    class Form:
        @staticmethod
        def __call__(*args, **kwargs):
            return ""
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code
            self.detail = detail
    class HTMLResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code
    class JSONResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code
    class PlainTextResponse:
        def __init__(self, content, status_code=200, media_type="text/plain"):
            self.content = content
            self.status_code = status_code
            self.media_type = media_type
    class RedirectResponse:
        def __init__(self, url: str, status_code: int = 302):
            self.url = url
            self.status_code = status_code
    class Jinja2Templates:
        def __init__(self, directory):
            pass
        def TemplateResponse(self, *args, **kwargs):
            return HTMLResponse("<h1>FastAPI not available. Install: pip install fastapi uvicorn jinja2</h1>")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from project_guardian.review_queue import ReviewQueue, ReviewRequest
from project_guardian.approval_store import ApprovalStore
from project_guardian.eai_safety import EAISafetyFramework, load_eai_safety_config

# Initialize FastAPI app
try:
    app = FastAPI(title="Project Guardian Control Panel")
except Exception as exc:
    FASTAPI_AVAILABLE = False
    FASTAPI_IMPORT_ERROR = str(exc)

    class _FallbackFastAPI:
        def __init__(self, *args, **kwargs):
            self.routes = []

        def middleware(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    app = _FallbackFastAPI(title="Project Guardian Control Panel")

# Templates directory
templates_dir = Path(__file__).parent / "templates"
if FASTAPI_AVAILABLE:
    templates = Jinja2Templates(directory=str(templates_dir))

# Project root
project_root = Path(__file__).parent.parent.parent

# Initialize review queue and approval store
# Note: ReviewQueue doesn't need memory for basic operations, but can accept it for logging
review_queue = ReviewQueue()
approval_store = ApprovalStore()

# Retention policy constants
MAX_RUN_ONCE_HISTORY = 200
MAX_ACCEPTANCE_HISTORY = 200
MAX_HISTORY_DAYS = 30  # Optional age-based retention
MAX_LOG_BYTES = 1_000_000  # 1MB limit for log copies


def is_loopback(host: str) -> bool:
    """
    Check if host is a loopback address.
    
    Allowed:
    - 127.0.0.1 (IPv4 loopback)
    - ::1 (IPv6 loopback)
    
    Args:
        host: Client host string (IP address)
    
    Returns:
        True if host is loopback, False otherwise
    """
    if not host:
        return False
    # Normalize host (remove port if present)
    host = host.split(':')[0].strip()
    return host in ('127.0.0.1', '::1', 'localhost')


# Local-only enforcement middleware
@app.middleware("http")
async def local_only_middleware(request: Request, call_next):
    """
    Enforce local-only access by rejecting non-loopback client hosts.
    
    Security:
    - Uses request.client.host only (does NOT trust X-Forwarded-For)
    - Rejects all non-loopback addresses with HTTP 403
    """
    client_host = request.client.host if request.client else None
    
    if not is_loopback(client_host):
        # Reject non-loopback access
        if FASTAPI_AVAILABLE:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error_title": "Local-only UI: remote access denied",
                "error_message": "This control panel is only accessible from localhost (127.0.0.1). Remote access is blocked for security.",
                "status_code": 403
            }, status_code=403)
        else:
            return HTMLResponse(
                "<h1>403 Forbidden</h1><p>Local-only UI: remote access denied.</p>",
                status_code=403
            )
    
    response = await call_next(request)
    return response


def _ensure_dir(path: Path) -> None:
    """Ensure directory exists, creating if needed"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except (IOError, OSError):
        # Best-effort: if creation fails, continue
        pass


def _prune_history_dir(
    history_dir: Path,
    max_files: int,
    max_days: Optional[int] = None,
    allowed_suffixes: tuple = ('.json',)
) -> None:
    """
    Prune history directory to keep only newest files.
    
    Args:
        history_dir: Directory to prune
        max_files: Maximum number of files to keep
        max_days: Optional maximum age in days (if provided, also prune older files)
        allowed_suffixes: Tuple of allowed file suffixes (e.g., ('.json', '.log'))
    
    Safety:
        - Only deletes files matching allowed_suffixes
        - Never deletes directories
        - Best-effort: failures are logged but don't crash
    """
    if not history_dir.exists():
        return
    
    try:
        # Get all files matching allowed suffixes
        all_files = []
        for suffix in allowed_suffixes:
            all_files.extend(history_dir.glob(f"*{suffix}"))
        
        if len(all_files) <= max_files:
            return  # No pruning needed
        
        # Sort by modified time (newest first)
        all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Determine which files to keep
        if max_days:
            from datetime import datetime, timedelta
            cutoff_time = (datetime.now() - timedelta(days=max_days)).timestamp()
            # Filter by age first
            files_to_keep_by_age = [f for f in all_files if f.stat().st_mtime >= cutoff_time]
            # Then apply count limit (use stricter of age or count)
            if len(files_to_keep_by_age) <= max_files:
                files_to_keep = files_to_keep_by_age
            else:
                # More files than max_files, keep newest max_files
                files_to_keep = files_to_keep_by_age[:max_files]
        else:
            # Count-based pruning only: keep newest max_files
            files_to_keep = all_files[:max_files]
        
        # Delete files NOT in the keep list
        files_to_keep_set = set(files_to_keep)
        files_to_delete = [f for f in all_files if f not in files_to_keep_set]
        
        for file_to_delete in files_to_delete:
            try:
                # Double-check: only delete files with allowed suffixes
                if any(file_to_delete.name.endswith(suffix) for suffix in allowed_suffixes):
                    # Double-check: only delete in history directory (safety check)
                    if file_to_delete.parent.resolve() == history_dir.resolve():
                        file_to_delete.unlink()
            except (IOError, OSError):
                # Best-effort: if deletion fails, continue
                pass
    except (IOError, OSError) as e:
        # Best-effort: if pruning fails, log but don't crash
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"History pruning failed for {history_dir}: {e}")


def _redact_sensitive_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive fields from context for UI display"""
    sensitive_keys = ["sensitive", "content", "body", "password", "token", "key", "secret"]
    redacted = {}
    for k, v in context.items():
        if any(sensitive in k.lower() for sensitive in sensitive_keys):
            redacted[k] = "[REDACTED]"
        else:
            redacted[k] = v
    return redacted


def _read_control_md() -> Dict[str, Any]:
    """Read CONTROL.md and extract current task"""
    control_file = project_root / "CONTROL.md"
    if not control_file.exists():
        return {"current_task": "NONE", "content": ""}
    
    try:
        content = control_file.read_text(encoding='utf-8')
    except IOError:
        return {"current_task": "NONE", "content": ""}
    current_task = "NONE"
    
    for line in content.split('\n'):
        if line.startswith("CURRENT_TASK:"):
            current_task = line.split(":", 1)[1].strip()
            break
    
    return {"current_task": current_task, "content": content}


def _write_control_md(current_task: str) -> bool:
    """Write CURRENT_TASK to CONTROL.md"""
    control_file = project_root / "CONTROL.md"
    if not control_file.exists():
        return False
    
    try:
        content = control_file.read_text(encoding='utf-8')
    except IOError:
        return False
    lines = content.split('\n')
    
    # Update CURRENT_TASK line
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("CURRENT_TASK:"):
            lines[i] = f"CURRENT_TASK: {current_task}"
            updated = True
            break
    
    if updated:
        try:
            # Atomic write: write to .tmp, then replace
            import os
            tmp_file = control_file.with_suffix('.tmp')
            tmp_file.write_text('\n'.join(lines), encoding='utf-8')
            os.replace(tmp_file, control_file)
            return True
        except IOError:
            return False
    
    return False


def _read_eai_safety_status() -> Dict[str, Any]:
    """Read EAI safety config and local lineage registry for the dashboard."""

    config_path = project_root / "config" / "eai_safety.json"
    status: Dict[str, Any] = {
        "enabled": False,
        "lineage_records": 0,
        "recent_lineage": [],
        "updated_at": None,
        "config_path": str(config_path),
        "lineage_registry_path": str(project_root / "data" / "eai_lineage_registry.json"),
        "audit_log_path": str(project_root / "data" / "eai_assessments.jsonl"),
        "alert_state_path": str(project_root / "data" / "eai_alert_state.json"),
        "audit_events": 0,
    }

    try:
        config = load_eai_safety_config(config_path=str(config_path))
        lineage_path = Path(config.get("lineage_registry_path") or "data/eai_lineage_registry.json")
        if not lineage_path.is_absolute():
            lineage_path = project_root / lineage_path
        audit_path = Path(config.get("audit_log_path") or "data/eai_assessments.jsonl")
        if not audit_path.is_absolute():
            audit_path = project_root / audit_path
        alert_state_path = Path(
            config.get("alert_state_path") or "data/eai_alert_state.json"
        )
        if not alert_state_path.is_absolute():
            alert_state_path = project_root / alert_state_path

        status.update(
            {
                "enabled": bool(config.get("enabled", True)),
                "autonomous_deployment_policy": config.get(
                    "autonomous_deployment_policy",
                    "deny",
                ),
                "review_threshold": config.get("review_threshold"),
                "deny_threshold": config.get("deny_threshold"),
                "lineage_registry_path": str(lineage_path),
                "audit_log_path": str(audit_path),
                "alert_state_path": str(alert_state_path),
                "registry_exists": lineage_path.exists(),
                "audit_log_exists": audit_path.exists(),
                "alert_state_exists": alert_state_path.exists(),
            }
        )

        if audit_path.exists():
            try:
                status["audit_events"] = sum(
                    1
                    for line in audit_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            except (IOError, OSError):
                status["audit_events"] = 0

        if not lineage_path.exists():
            return status

        data = json.loads(lineage_path.read_text(encoding="utf-8"))
        records = data.get("records", {})
        if not isinstance(records, dict):
            records = {}

        recent = sorted(
            records.values(),
            key=lambda item: str(item.get("created_at", "")) if isinstance(item, dict) else "",
            reverse=True,
        )
        max_items = int(config.get("max_lineage_status_items") or 5)
        status.update(
            {
                "lineage_records": len(records),
                "recent_lineage": [
                    {
                        "artifact_id": str(item.get("artifact_id", "")),
                        "artifact_type": str(item.get("artifact_type", "unknown")),
                        "created_by": str(item.get("created_by", "unknown")),
                        "created_at": item.get("created_at"),
                    }
                    for item in recent[:max(0, max_items)]
                    if isinstance(item, dict)
                ],
                "updated_at": data.get("updated_at"),
            }
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status


def _read_eai_audit(limit: int = 5, **filters: Any) -> Dict[str, Any]:
    """Read recent EAI safety audit events for dashboard display."""

    try:
        framework = _local_eai_safety_framework()
        events = framework.list_audit(limit=limit, **filters)
        return {
            "events": events,
            "limit": limit,
            "audit_log_path": str(framework.audit_path) if framework.audit_path else None,
        }
    except Exception as exc:
        return {"events": [], "limit": limit, "error": str(exc)}


def _read_eai_alerts(limit: int = 5, **filters: Any) -> Dict[str, Any]:
    """Read computed EAI safety alerts for dashboard display."""

    try:
        framework = _local_eai_safety_framework()
        alerts = framework.list_alerts(limit=limit, **filters)
        return {
            "alerts": alerts,
            "limit": limit,
            "audit_log_path": str(framework.audit_path) if framework.audit_path else None,
        }
    except Exception as exc:
        return {"alerts": [], "limit": limit, "error": str(exc)}


def _read_eai_summary(days: int = 1) -> Dict[str, Any]:
    """Read a compact EAI safety summary for dashboard display."""

    try:
        framework = _local_eai_safety_framework()
        return framework.get_daily_summary(days=days)
    except Exception as exc:
        return {"error": str(exc)}


def _local_eai_safety_framework() -> EAISafetyFramework:
    """Create a local read-only EAI gate instance for dashboard dry-runs."""

    config_path = project_root / "config" / "eai_safety.json"
    config = load_eai_safety_config(config_path=str(config_path))
    lineage_path = Path(config.get("lineage_registry_path") or "data/eai_lineage_registry.json")
    if not lineage_path.is_absolute():
        lineage_path = project_root / lineage_path
    audit_path = Path(config.get("audit_log_path") or "data/eai_assessments.jsonl")
    if not audit_path.is_absolute():
        audit_path = project_root / audit_path
    alert_state_path = Path(config.get("alert_state_path") or "data/eai_alert_state.json")
    if not alert_state_path.is_absolute():
        alert_state_path = project_root / alert_state_path

    return EAISafetyFramework(
        storage_path=str(lineage_path),
        audit_path=str(audit_path),
        alert_state_path=str(alert_state_path),
        approval_store=approval_store,
        review_queue=review_queue,
        autonomous_deployment_policy=str(config.get("autonomous_deployment_policy", "deny")),
        review_threshold=float(config.get("review_threshold", 0.45)),
        deny_threshold=float(config.get("deny_threshold", 0.85)),
        max_recent_assessments=int(config.get("max_recent_assessments", 25)),
        max_lineage_status_items=int(config.get("max_lineage_status_items", 5)),
    )


def _resolve_report_output_dir(requested: Optional[Any] = None) -> str:
    """Resolve report output under the project root for the local dashboard."""

    requested_text = str(requested or "REPORTS").strip() or "REPORTS"
    requested_path = Path(requested_text)
    target = (
        requested_path.resolve()
        if requested_path.is_absolute()
        else (project_root / requested_path).resolve()
    )
    try:
        target.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError("output_dir must stay within project root") from exc
    return str(target)


def _assess_eai_dry_run(
    data: Dict[str, Any],
    framework: Optional[EAISafetyFramework] = None,
) -> Dict[str, Any]:
    """Run an action through the local EAI gate without registering lineage."""

    if not isinstance(data, dict):
        raise ValueError("JSON object body required")

    action_type = str(data.get("action_type") or "").strip()
    if not action_type:
        raise ValueError("action_type required")

    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    framework = framework or _local_eai_safety_framework()
    assessment = framework.assess_action(
        action_type=action_type[:120],
        actor=str(data.get("actor") or "operator")[:160],
        target=str(data.get("target") or "")[:500],
        metadata=metadata,
        lineage_parent_ids=data.get("lineage_parent_ids", data.get("parent_ids")),
        artifact_content=data.get("artifact_content"),
        dry_run=True,
    )
    payload = assessment.to_dict()
    return {
        "dry_run": True,
        "lineage_mutated": False,
        "decision": payload["decision"],
        "risk_score": payload["risk_score"],
        "flags": payload["flags"],
        "selection_pressures": payload["selection_pressures"],
        "required_controls": payload["required_controls"],
        "assessment": payload,
    }


def _content_preview(value: Any, max_chars: int = 2000) -> Dict[str, Any]:
    if value is None:
        return {"present": False}
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, default=str)
    return {
        "present": True,
        "chars": len(text),
        "truncated": len(text) > max_chars,
        "preview": text[:max_chars],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _eai_review_context(data: Dict[str, Any], assessment_result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "target": str(data.get("target") or ""),
        "caller_identity": str(data.get("actor") or "operator"),
        "task_id": str(data.get("task_id") or "eai-dry-run"),
        "action_type": str(data.get("action_type") or ""),
        "metadata": metadata,
        "artifact_content": _content_preview(data.get("artifact_content")),
        "lineage_parent_ids": data.get("lineage_parent_ids", data.get("parent_ids")),
        "eai_safety": assessment_result.get("assessment", assessment_result),
        "eai_decision": assessment_result.get("decision"),
        "eai_risk_score": assessment_result.get("risk_score"),
        "eai_flags": assessment_result.get("flags", []),
        "eai_required_controls": assessment_result.get("required_controls", []),
        "lineage_mutated": False,
        "source": "eai_dry_run",
    }


def _create_eai_review_request(data: Dict[str, Any]) -> Dict[str, Any]:
    framework = _local_eai_safety_framework()
    assessment_result = _assess_eai_dry_run(data, framework=framework)
    decision = str(assessment_result.get("decision") or "").lower()
    if decision == "allow" and not data.get("force_review"):
        return {
            "created": False,
            "reason": "assessment_allowed",
            "assessment": assessment_result,
        }

    context = _eai_review_context(data, assessment_result)
    request_id = review_queue.enqueue(
        component="eai_safety",
        action=str(data.get("action_type") or "unknown"),
        context=context,
    )
    audit_event = framework.record_audit_event(
        "review_request",
        assessment_result.get("assessment", assessment_result),
        review_request_id=request_id,
        details={
            "source": "dashboard",
            "lineage_mutated": False,
        },
    )
    return {
        "created": True,
        "request_id": request_id,
        "review_url": f"/reviews/{request_id}",
        "audit_id": audit_event.get("audit_id"),
        "assessment": assessment_result,
    }


@app.get("/", response_class=HTMLResponse)
async def status_dashboard(request: Request):
    """Status dashboard - shows current task, last acceptance run, pending reviews"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available. Install: pip install fastapi uvicorn jinja2</h1>")
    
    # Get current task
    control_info = _read_control_md()
    current_task = control_info["current_task"]
    
    # Get pending review count
    pending_reviews = review_queue.list_pending()
    pending_count = len(pending_reviews)
    
    # Get last acceptance run from artifact
    acceptance_json = project_root / "REPORTS" / "acceptance_last.json"
    last_acceptance = None
    acceptance_status = None
    acceptance_exit_code = None
    
    if acceptance_json.exists():
        try:
            with open(acceptance_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                last_acceptance = data.get('timestamp')
                acceptance_status = data.get('status', 'unknown')
                acceptance_exit_code = data.get('exit_code')
        except (json.JSONDecodeError, IOError):
            # Fallback to file timestamp if JSON invalid
            stat = acceptance_json.stat()
            last_acceptance = datetime.fromtimestamp(stat.st_mtime).isoformat()
            acceptance_status = 'unknown'
    
    # Get last run_once result from artifact
    run_once_json = project_root / "REPORTS" / "run_once_last.json"
    last_run_once = None
    run_once_status = None
    run_once_result = None
    
    if run_once_json.exists():
        try:
            with open(run_once_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                last_run_once = data.get('timestamp')
                run_once_status = data.get('result', {}).get('status', 'unknown')
                run_once_result = data.get('result')
        except (json.JSONDecodeError, IOError):
            # Fallback to file timestamp if JSON invalid
            stat = run_once_json.stat()
            last_run_once = datetime.fromtimestamp(stat.st_mtime).isoformat()
            run_once_status = 'unknown'
    
    # Check if bind host is set and not loopback
    bind_host = os.environ.get("UI_BIND_HOST", "127.0.0.1")
    bind_host_warning = not is_loopback(bind_host) if bind_host else False
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_task": current_task,
        "pending_count": pending_count,
        "last_acceptance": last_acceptance,
        "acceptance_status": acceptance_status,
        "acceptance_exit_code": acceptance_exit_code,
        "last_run_once": last_run_once,
        "run_once_status": run_once_status,
        "run_once_result": run_once_result,
        "eai_safety": _read_eai_safety_status(),
        "eai_summary": _read_eai_summary(days=1),
        "eai_alerts": _read_eai_alerts(limit=5),
        "eai_audit": _read_eai_audit(limit=5),
        "bind_host_warning": bind_host_warning,
        "bind_host": bind_host
    })


@app.get("/reviews", response_class=HTMLResponse)
async def list_reviews(request: Request, status: str = "pending"):
    """List review requests with optional status filter"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Parse review queue to get all requests (latest per request_id)
    all_requests = {}
    queue_file = project_root / "REPORTS" / "review_queue.jsonl"
    
    if queue_file.exists():
        try:
            with open(queue_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req_data = json.loads(line)
                        request_id = req_data.get("request_id")
                        if request_id:
                            # Keep latest record per request_id
                            all_requests[request_id] = req_data
                    except json.JSONDecodeError:
                        continue
        except IOError:
            pass
    
    # Filter by status
    if status == "all":
        filtered = list(all_requests.values())
    else:
        filtered = [req for req in all_requests.values() if req.get("status", "pending") == status]
    
    # Convert to ReviewRequest objects for display
    reviews_display = []
    for req_data in filtered:
        # Check approval status
        approval = None
        try:
            approval = approval_store.get_approval(req_data.get("request_id"))
        except Exception:
            pass
        
        # Determine final status
        final_status = req_data.get("status", "pending")
        if approval:
            final_status = approval.status
        
        # Redact context
        redacted_context = _redact_sensitive_context(req_data.get("context", {}).copy())
        
        reviews_display.append({
            "request_id": req_data.get("request_id"),
            "component": req_data.get("component", "unknown"),
            "action": req_data.get("action", "unknown"),
            "target": req_data.get("context", {}).get("target", "unknown"),
            "created_at": req_data.get("created_at", "unknown"),
            "status": final_status,
            "context": redacted_context
        })
    
    # Count by status
    counts = {"pending": 0, "approved": 0, "denied": 0, "all": len(all_requests)}
    for req_data in all_requests.values():
        approval = None
        try:
            approval = approval_store.get_approval(req_data.get("request_id"))
        except Exception:
            pass
        
        if approval:
            counts[approval.status] = counts.get(approval.status, 0) + 1
        else:
            counts["pending"] = counts.get("pending", 0) + 1
    
    return templates.TemplateResponse("reviews.html", {
        "request": request,
        "reviews": reviews_display,
        "current_status": status,
        "counts": counts
    })


@app.get("/reviews/{request_id}", response_class=HTMLResponse)
async def review_detail(request: Request, request_id: str):
    """View detail of a specific review request"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    req = review_queue.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Review request not found")
    
    # Redact sensitive context - operate on COPY to avoid mutating original
    # This ensures the original request context remains unchanged
    redacted_context = _redact_sensitive_context(req.context.copy())
    
    # Check if already approved/denied
    approval = None
    try:
        approval = approval_store.get_approval(request_id)
    except Exception:
        # Approval store read failed - continue without approval info
        pass
    
    # Ensure context is JSON-serializable and safe for template
    context_json = json.dumps(redacted_context, indent=2)
    
    return templates.TemplateResponse("review_detail.html", {
        "request": request,
        "review": req,  # Original request (context not mutated)
        "approval": approval,
        "context_json": context_json  # Pre-escaped JSON string from redacted copy
    })


@app.post("/reviews/{request_id}/approve")
async def approve_review(request_id: str, notes: str = Form(""), approver: str = Form("human")):
    """Approve a review request"""
    # Sanitize inputs
    approver = approver[:100] if approver else "human"  # Limit length
    notes = notes[:1000] if notes else ""  # Limit length
    
    req = review_queue.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Review request not found")
    
    try:
        # Approve with original context
        approved = approval_store.approve(
            request_id=request_id,
            context=req.context,
            approver=approver,
            notes=notes
        )
        
        if not approved:
            raise HTTPException(status_code=400, detail="Request already approved/denied")
        
        # Update queue status
        review_queue.update_status(request_id, "approved", approver=approver, notes=notes)
        
        return JSONResponse({
            "status": "approved",
            "request_id": request_id,
            "message": f"Request {request_id} approved by {approver}"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving request: {str(e)}")


@app.post("/reviews/{request_id}/deny")
async def deny_review(request_id: str, notes: str = Form(""), approver: str = Form("human")):
    """Deny a review request"""
    # Sanitize inputs
    approver = approver[:100] if approver else "human"  # Limit length
    notes = notes[:1000] if notes else ""  # Limit length
    
    req = review_queue.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Review request not found")
    
    try:
        # Deny
        denied = approval_store.deny(
            request_id=request_id,
            approver=approver,
            notes=notes
        )
        
        if not denied:
            raise HTTPException(status_code=400, detail="Request already approved/denied")
        
        # Update queue status
        review_queue.update_status(request_id, "denied", approver=approver, notes=notes)
        
        return JSONResponse({
            "status": "denied",
            "request_id": request_id,
            "message": f"Request {request_id} denied by {approver}"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error denying request: {str(e)}")


@app.post("/control/task")
async def set_current_task(task: str = Form(...)):
    """Set CURRENT_TASK in CONTROL.md"""
    # Validate and sanitize task name
    if not task:
        raise HTTPException(status_code=400, detail="Task name cannot be empty")
    
    # Limit length and remove dangerous characters
    task = task.strip()[:100]  # Max 100 chars
    if not task:
        raise HTTPException(status_code=400, detail="Invalid task name")
    
    # Basic validation: allow alphanumeric, dash, underscore, dots
    import re
    if not re.match(r'^[A-Za-z0-9_\-\.]+$', task):
        raise HTTPException(status_code=400, detail="Task name contains invalid characters")
    
    try:
        success = _write_control_md(task)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update CONTROL.md")
        
        return JSONResponse({
            "status": "updated",
            "current_task": task,
            "message": f"CURRENT_TASK set to {task}"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating task: {str(e)}")


@app.post("/control/run-once")
async def run_once():
    """Run GuardianCore.run_once() and save result artifact"""
    if not FASTAPI_AVAILABLE:
        raise HTTPException(status_code=503, detail="FastAPI not available")
    
    try:
        # Import GuardianCore
        from project_guardian.core import GuardianCore
        
        # Initialize Core with minimal config
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config)
        
        # Call run_once()
        result = core.run_once()
        
        # Write artifact atomically
        reports_dir = project_root / "REPORTS"
        reports_dir.mkdir(exist_ok=True)
        artifact_file = reports_dir / "run_once_last.json"
        artifact_data = {
            "timestamp": datetime.now().isoformat(),
            "result": result
        }
        
        # Atomic write
        import os
        tmp_file = artifact_file.with_suffix('.tmp')
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(artifact_data, f, indent=2)
        os.replace(tmp_file, artifact_file)
        
        # Write to history directory
        history_dir = reports_dir / "run_once_history"
        _ensure_dir(history_dir)
        
        # Generate history filename: YYYYMMDD_HHMMSS_<status>_<task-or-none>.json
        now = datetime.now()
        status = result.get("status", "unknown")
        task_id = result.get("current_task", "none")
        if task_id is None:
            task_id = "none"
        task_id_safe = task_id.replace("/", "_").replace("\\", "_")[:20]  # Sanitize for filename
        
        history_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{status}_{task_id_safe}.json"
        history_file = history_dir / history_filename
        
        # Atomic write to history
        tmp_history = history_file.with_suffix('.tmp')
        with open(tmp_history, 'w', encoding='utf-8') as f:
            json.dump(artifact_data, f, indent=2)
        os.replace(tmp_history, history_file)
        
        # Prune history directory (keep newest MAX_RUN_ONCE_HISTORY)
        _prune_history_dir(history_dir, MAX_RUN_ONCE_HISTORY, max_days=MAX_HISTORY_DAYS, allowed_suffixes=('.json',))
        
        # Redirect back to dashboard
        return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running once: {str(e)}")


@app.post("/control/run-acceptance")
async def run_acceptance():
    """Run acceptance script and return output"""
    acceptance_script = project_root / "scripts" / "acceptance.ps1"
    
    if not acceptance_script.exists():
        raise HTTPException(status_code=404, detail="acceptance.ps1 not found")
    
    # Safety: only allow running the exact acceptance script
    script_path = str(acceptance_script.resolve())
    if not script_path.endswith("acceptance.ps1"):
        raise HTTPException(status_code=403, detail="Invalid script path")
    
    try:
        # Run acceptance script (only this specific script)
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=str(project_root),
            encoding='utf-8',
            errors='replace'  # Handle encoding errors gracefully
        )
        
        # Redact sensitive patterns from output
        def redact_sensitive(text: str) -> str:
            import re
            patterns = [
                (r'(?i)(api[_-]?key\s*[:=]\s*)([^\s"''\n]+)', r'\1[REDACTED]'),
                (r'(?i)(password\s*[:=]\s*)([^\s"''\n]+)', r'\1[REDACTED]'),
                (r'(?i)(token\s*[:=]\s*)([^\s"''\n]+)', r'\1[REDACTED]'),
                (r'(?i)(secret\s*[:=]\s*)([^\s"''\n]+)', r'\1[REDACTED]'),
            ]
            redacted = text
            for pattern, replacement in patterns:
                redacted = re.sub(pattern, replacement, redacted)
            return redacted
        
        stdout_redacted = redact_sensitive(result.stdout)
        stderr_redacted = redact_sensitive(result.stderr)
        
        # Copy acceptance artifacts to history (if they exist)
        acceptance_json = project_root / "REPORTS" / "acceptance_last.json"
        if acceptance_json.exists():
            try:
                # Read acceptance artifact
                with open(acceptance_json, 'r', encoding='utf-8') as f:
                    acceptance_data = json.load(f)
                
                # Write to history directory
                history_dir = project_root / "REPORTS" / "acceptance_history"
                _ensure_dir(history_dir)
                
                # Generate history filename: YYYYMMDD_HHMMSS_<status>_<exit_code>.json
                now = datetime.now()
                status = acceptance_data.get("status", "unknown")
                exit_code = acceptance_data.get("exit_code", 0)
                
                history_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{status}_{exit_code}.json"
                history_file = history_dir / history_filename
                
                # Optionally copy log file (if exists and not too large)
                acceptance_log = project_root / "REPORTS" / "acceptance_last.log"
                log_copied = False
                log_too_large = False
                
                if acceptance_log.exists():
                    try:
                        log_size = acceptance_log.stat().st_size
                        # Cap at MAX_LOG_BYTES (1MB)
                        if log_size <= MAX_LOG_BYTES:
                            log_history_filename = history_filename.replace('.json', '.log')
                            log_history_file = history_dir / log_history_filename
                            
                            # Read and write log (atomic)
                            log_content = acceptance_log.read_text(encoding='utf-8', errors='replace')
                            tmp_log = log_history_file.with_suffix('.tmp')
                            tmp_log.write_text(log_content, encoding='utf-8')
                            os.replace(tmp_log, log_history_file)
                            log_copied = True
                        else:
                            # Log too large - mark in JSON
                            log_too_large = True
                    except (IOError, OSError):
                        # Log copy failed - continue without it
                        pass
                
                # Add log copy status to JSON
                if log_too_large:
                    acceptance_data["log_copied"] = False
                    acceptance_data["log_too_large"] = True
                    acceptance_data["log_size_bytes"] = log_size
                elif log_copied:
                    acceptance_data["log_copied"] = True
                
                # Atomic write to history
                import os
                tmp_history = history_file.with_suffix('.tmp')
                with open(tmp_history, 'w', encoding='utf-8') as f:
                    json.dump(acceptance_data, f, indent=2)
                os.replace(tmp_history, history_file)
                
                # Prune history directory (keep newest MAX_ACCEPTANCE_HISTORY)
                _prune_history_dir(history_dir, MAX_ACCEPTANCE_HISTORY, max_days=MAX_HISTORY_DAYS, allowed_suffixes=('.json', '.log'))
            except (json.JSONDecodeError, IOError, OSError):
                # History copy failed - continue without it
                pass
        
        return JSONResponse({
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": stdout_redacted,
            "stderr": stderr_redacted,
            "success": result.returncode == 0
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "status": "timeout",
            "message": "Acceptance script timed out after 5 minutes"
        }, status_code=500)
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.get("/api/status")
async def api_status():
    """API endpoint for status (JSON)"""
    control_info = _read_control_md()
    pending_reviews = review_queue.list_pending()
    
    # Read acceptance artifact
    acceptance_json = project_root / "REPORTS" / "acceptance_last.json"
    last_acceptance = None
    acceptance_status = None
    acceptance_exit_code = None
    
    if acceptance_json.exists():
        try:
            with open(acceptance_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                last_acceptance = data.get('timestamp')
                acceptance_status = data.get('status', 'unknown')
                acceptance_exit_code = data.get('exit_code')
        except (json.JSONDecodeError, IOError):
            pass
    
    # Check if bind host is set and not loopback
    bind_host = os.environ.get("UI_BIND_HOST", "127.0.0.1")
    bind_host_warning = not is_loopback(bind_host) if bind_host else False
    
    return JSONResponse({
        "current_task": control_info["current_task"],
        "pending_reviews": len(pending_reviews),
        "last_acceptance": last_acceptance,
        "acceptance_status": acceptance_status,
        "acceptance_exit_code": acceptance_exit_code,
        "eai_safety": _read_eai_safety_status(),
        "eai_summary": _read_eai_summary(days=1),
        "eai_alerts": _read_eai_alerts(limit=10),
        "eai_audit": _read_eai_audit(limit=10),
        "local_only_enforced": True,
        "bind_host_warning": bind_host_warning
    })


@app.post("/api/eai/assess")
async def api_eai_assess(request: Request):
    """Dry-run an Evolvable-AI-sensitive action through the local safety gate."""
    try:
        data = await request.json()
        return JSONResponse(_assess_eai_dry_run(data))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/eai/audit")
async def api_eai_audit(
    limit: int = 50,
    decision: Optional[str] = None,
    flag: Optional[str] = None,
    actor: Optional[str] = None,
    target: Optional[str] = None,
    event_type: Optional[str] = None,
):
    """List recent EAI safety audit events."""
    try:
        bounded_limit = max(1, min(500, int(limit)))
        framework = _local_eai_safety_framework()
        return JSONResponse(
            {
                "events": framework.list_audit(
                    limit=bounded_limit,
                    decision=decision,
                    flag=flag,
                    actor=actor,
                    target=target,
                    event_type=event_type,
                ),
                "limit": bounded_limit,
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/eai/audit/{identifier}")
async def api_eai_audit_event(identifier: str):
    """Get an EAI audit event by audit, assessment, or review request id."""
    try:
        framework = _local_eai_safety_framework()
        event = framework.get_audit_event(identifier)
        if event is None:
            return JSONResponse({"error": "EAI audit event not found"}, status_code=404)
        return JSONResponse(event)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/eai/alerts")
async def api_eai_alerts(
    limit: int = 25,
    audit_limit: int = 500,
    severity: Optional[str] = None,
    rule: Optional[str] = None,
    include_acknowledged: bool = True,
    include_resolved: bool = False,
):
    """List computed EAI safety alerts from recent audit events."""
    try:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_audit_limit = max(1, min(5000, int(audit_limit)))
        framework = _local_eai_safety_framework()
        return JSONResponse(
            {
                "alerts": framework.list_alerts(
                    limit=bounded_limit,
                    audit_limit=bounded_audit_limit,
                    severity=severity,
                    rule=rule,
                    include_acknowledged=include_acknowledged,
                    include_resolved=include_resolved,
                ),
                "limit": bounded_limit,
                "audit_limit": bounded_audit_limit,
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/eai/summary")
async def api_eai_summary(
    days: int = 1,
    audit_limit: int = 5000,
    include_resolved: bool = True,
):
    """Get a compact EAI safety daily summary."""
    try:
        bounded_days = max(1, min(365, int(days)))
        bounded_audit_limit = max(1, min(20000, int(audit_limit)))
        framework = _local_eai_safety_framework()
        return JSONResponse(
            framework.get_daily_summary(
                days=bounded_days,
                audit_limit=bounded_audit_limit,
                include_resolved=include_resolved,
            )
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/eai/summary.md")
async def api_eai_summary_markdown(
    days: int = 1,
    audit_limit: int = 5000,
    include_resolved: bool = True,
):
    """Get a Markdown EAI safety daily summary report."""
    try:
        bounded_days = max(1, min(365, int(days)))
        bounded_audit_limit = max(1, min(20000, int(audit_limit)))
        framework = _local_eai_safety_framework()
        markdown = framework.render_daily_summary_markdown(
            days=bounded_days,
            audit_limit=bounded_audit_limit,
            include_resolved=include_resolved,
        )
        return PlainTextResponse(markdown, media_type="text/markdown")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/eai/summary/export")
async def api_eai_summary_export(request: Request):
    """Write a Markdown EAI safety summary report to disk."""
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}

        bounded_days = max(1, min(365, int(data.get("days") or 1)))
        bounded_audit_limit = max(1, min(20000, int(data.get("audit_limit") or 5000)))
        framework = _local_eai_safety_framework()
        result = framework.write_daily_summary_report(
            output_dir=_resolve_report_output_dir(data.get("output_dir")),
            days=bounded_days,
            audit_limit=bounded_audit_limit,
            include_resolved=bool(data.get("include_resolved", True)),
            filename=(
                str(data.get("filename"))
                if data.get("filename") is not None
                else None
            ),
        )
        return JSONResponse(result, status_code=201)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/eai/alerts/{alert_id}/ack")
async def api_eai_alert_ack(alert_id: str, request: Request):
    """Acknowledge a computed EAI alert."""
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        framework = _local_eai_safety_framework()
        state = framework.acknowledge_alert(
            alert_id,
            actor=str(data.get("actor") or "operator")[:160],
            notes=str(data.get("notes") or "")[:1000],
        )
        return JSONResponse({"updated": True, "state": state})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/eai/alerts/{alert_id}/resolve")
async def api_eai_alert_resolve(alert_id: str, request: Request):
    """Resolve a computed EAI alert."""
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        framework = _local_eai_safety_framework()
        state = framework.resolve_alert(
            alert_id,
            actor=str(data.get("actor") or "operator")[:160],
            notes=str(data.get("notes") or "")[:1000],
        )
        return JSONResponse({"updated": True, "state": state})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/eai/review-request")
async def api_eai_review_request(request: Request):
    """Create a human review request from an EAI dry-run assessment."""
    try:
        data = await request.json()
        result = _create_eai_review_request(data)
        status_code = 201 if result.get("created") else 200
        return JSONResponse(result, status_code=status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/insights/overview")
async def api_insights_overview_fastapi():
    """Same data as Flask Control Panel /api/insights/overview (self-build, MCP, traces, RAG log)."""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<p>FastAPI unavailable</p>", status_code=503)
    try:
        from project_guardian.operator_insights import build_insights_overview

        return JSONResponse(build_insights_overview(trace_lines=40, rag_lines=30))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/acceptance-log")
async def api_acceptance_log():
    """API endpoint to view last acceptance log"""
    log_file = project_root / "REPORTS" / "acceptance_last.log"
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Acceptance log not found")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        return JSONResponse({
            "log": log_content,
            "timestamp": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
        })
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")


@app.get("/acceptance-log", response_class=HTMLResponse)
async def view_acceptance_log(request: Request):
    """View last acceptance log in browser"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    log_file = project_root / "REPORTS" / "acceptance_last.log"
    
    if not log_file.exists():
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Acceptance log not found"
        })
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        return templates.TemplateResponse("log_viewer.html", {
            "request": request,
            "log_content": log_content,
            "title": "Last Acceptance Run Log"
        })
    except IOError as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": f"Error reading log: {str(e)}"
        })


@app.get("/api/reviews")
async def api_reviews():
    """API endpoint for reviews list (JSON)"""
    pending = review_queue.list_pending()
    
    # Redact sensitive context
    reviews_data = []
    for req in pending:
        reviews_data.append({
            "request_id": req.request_id,
            "component": req.component,
            "action": req.action,
            "target": req.context.get("target", "unknown"),
            "created_at": req.created_at,
            "context": _redact_sensitive_context(req.context)
        })
    
    return JSONResponse({"reviews": reviews_data})


@app.get("/tasks/new", response_class=HTMLResponse)
async def task_builder(request: Request):
    """Task builder form"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    return templates.TemplateResponse("task_builder.html", {
        "request": request
    })


@app.post("/tasks/create")
async def create_task(
    task_id: str = Form(...),
    task_type: str = Form(...),
    mutation_file: str = Form(""),
    allow_governance_mutation: str = Form("false"),
    request_id: str = Form(""),
    activate_now: str = Form("false")
):
    """Create a new task file"""
    # Validate task_id
    if not re.match(r'^TASK-[A-Za-z0-9_-]{1,32}$', task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format. Must match: TASK-[A-Za-z0-9_-]{1,32}")
    
    # Validate task_type
    if task_type not in ["RUN_ACCEPTANCE", "CLEAR_CURRENT_TASK", "APPLY_MUTATION"]:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {task_type}")
    
    # Build task content
    lines = [f"TASK_TYPE: {task_type}"]
    
    if task_type == "APPLY_MUTATION":
        if not mutation_file:
            raise HTTPException(status_code=400, detail="MUTATION_FILE required for APPLY_MUTATION")
        if not mutation_file.startswith("MUTATIONS/") or not mutation_file.endswith(".json"):
            raise HTTPException(status_code=400, detail="MUTATION_FILE must be MUTATIONS/*.json")
        lines.append(f"MUTATION_FILE: {mutation_file}")
        lines.append(f"ALLOW_GOVERNANCE_MUTATION: {allow_governance_mutation}")
        if request_id:
            lines.append(f"REQUEST_ID: {request_id}")
    
    task_content = "\n".join(lines) + "\n"
    
    # Write task file atomically
    tasks_dir = project_root / "TASKS"
    tasks_dir.mkdir(exist_ok=True)
    task_file = tasks_dir / f"{task_id}.md"
    
    import os
    tmp_file = task_file.with_suffix('.tmp')
    try:
        tmp_file.write_text(task_content, encoding='utf-8')
        os.replace(tmp_file, task_file)
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Error writing task file: {str(e)}")
    
    # Optionally activate task
    if activate_now.lower() == "true":
        _write_control_md(task_id)
    
    return JSONResponse({
        "status": "created",
        "task_id": task_id,
        "message": f"Task {task_id} created successfully"
    })


@app.get("/mutations/new", response_class=HTMLResponse)
async def mutation_builder(request: Request):
    """Mutation payload builder form"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    return templates.TemplateResponse("mutation_builder.html", {
        "request": request
    })


@app.post("/mutations/create")
async def create_mutation(
    payload_name: str = Form(...),
    summary: str = Form(...),
    file_paths: list = Form(...),
    file_contents: list = Form(...)
):
    """Create a mutation payload JSON file"""
    # Validate payload_name
    if not re.match(r'^[A-Za-z0-9_-]{1,64}\.json$', payload_name):
        raise HTTPException(status_code=400, detail="Invalid payload_name. Must be alphanumeric with .json extension")
    
    if not payload_name.startswith("MUTATIONS/"):
        payload_name = f"MUTATIONS/{payload_name}"
    
    # Validate file_paths and file_contents match
    if len(file_paths) != len(file_contents):
        raise HTTPException(status_code=400, detail="Number of file paths must match number of file contents")
    
    if len(file_paths) == 0:
        raise HTTPException(status_code=400, detail="At least one file change required")
    
    # Validate paths
    touched_paths = []
    changes = []
    
    for path, content in zip(file_paths, file_contents):
        path = path.strip()
        if not path:
            continue
        
        # Path safety validation
        if '..' in path or Path(path).is_absolute():
            raise HTTPException(status_code=400, detail=f"Invalid path (no .. or absolute paths): {path}")
        
        # Check if path would be outside repo root
        resolved_path = (project_root / path).resolve()
        if not str(resolved_path).startswith(str(project_root.resolve())):
            raise HTTPException(status_code=400, detail=f"Path would be outside repo root: {path}")
        
        touched_paths.append(path)
        changes.append({
            "path": path,
            "content": content
        })
    
    # Validate touched_paths matches changes[].path set
    change_paths_set = set(ch["path"] for ch in changes)
    touched_paths_set = set(touched_paths)
    
    if change_paths_set != touched_paths_set:
        raise HTTPException(status_code=400, detail="touched_paths must match changes[].path set")
    
    # Compute base hashes for each touched path
    base_info = {}
    captured_at = datetime.now().isoformat()
    
    for path in touched_paths:
        file_path = project_root / path
        if file_path.exists() and file_path.is_file():
            try:
                # Read file content as bytes for hash computation
                with open(file_path, 'rb') as f:
                    file_bytes = f.read()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                file_size = len(file_bytes)
                base_info[path] = {
                    "sha256": file_hash,
                    "bytes": file_size,
                    "captured_at": captured_at
                }
            except (IOError, OSError):
                # File exists but can't read it - mark as missing
                base_info[path] = {
                    "sha256": "MISSING",
                    "bytes": 0,
                    "captured_at": captured_at
                }
        else:
            # File doesn't exist
            base_info[path] = {
                "sha256": "MISSING",
                "bytes": 0,
                "captured_at": captured_at
            }
    
    # Build payload
    payload = {
        "touched_paths": sorted(touched_paths),  # Sorted for deterministic hashing
        "changes": changes,
        "summary": summary[:500],  # Limit summary length
        "base": base_info
    }
    
    # Write mutation file atomically
    mutations_dir = project_root / "MUTATIONS"
    mutations_dir.mkdir(exist_ok=True)
    
    # Extract filename from payload_name (remove MUTATIONS/ prefix if present)
    if payload_name.startswith("MUTATIONS/"):
        filename = payload_name[10:]  # Remove "MUTATIONS/" prefix
    else:
        filename = payload_name
    
    mutation_file = mutations_dir / filename
    
    import os
    tmp_file = mutation_file.with_suffix('.tmp')
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_file, mutation_file)
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Error writing mutation file: {str(e)}")
    
    return JSONResponse({
        "status": "created",
        "payload_name": payload_name,
        "message": f"Mutation payload {payload_name} created successfully"
    })


@app.get("/history", response_class=HTMLResponse)
async def history_list(request: Request):
    """List execution history (run_once and acceptance)"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Get run_once history
    run_once_history_dir = project_root / "REPORTS" / "run_once_history"
    run_once_files = []
    if run_once_history_dir.exists():
        for f in sorted(run_once_history_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    run_once_files.append({
                        "filename": f.name,
                        "timestamp": data.get("timestamp", "unknown"),
                        "status": data.get("result", {}).get("status", "unknown"),
                        "task": data.get("result", {}).get("current_task", "none")
                    })
            except (json.JSONDecodeError, IOError):
                continue
    
    # Get acceptance history
    acceptance_history_dir = project_root / "REPORTS" / "acceptance_history"
    acceptance_files = []
    if acceptance_history_dir.exists():
        for f in sorted(acceptance_history_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    acceptance_files.append({
                        "filename": f.name,
                        "timestamp": data.get("timestamp", "unknown"),
                        "status": data.get("status", "unknown"),
                        "exit_code": data.get("exit_code")
                    })
            except (json.JSONDecodeError, IOError):
                continue
    
    return templates.TemplateResponse("history.html", {
        "request": request,
        "run_once_files": run_once_files,
        "acceptance_files": acceptance_files,
        "max_run_once": MAX_RUN_ONCE_HISTORY,
        "max_acceptance": MAX_ACCEPTANCE_HISTORY,
        "max_days": MAX_HISTORY_DAYS
    })


@app.get("/history/run-once/{filename}", response_class=HTMLResponse)
async def history_run_once_detail(request: Request, filename: str):
    """View run_once history detail"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Validate filename (no .., ends with .json)
    if '..' in filename or not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    history_file = project_root / "REPORTS" / "run_once_history" / filename
    if not history_file.exists():
        raise HTTPException(status_code=404, detail="History file not found")
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading history file: {str(e)}")
    
    # Escape JSON for safe display
    import html
    json_str = json.dumps(data, indent=2)
    json_escaped = html.escape(json_str)
    
    return templates.TemplateResponse("history_detail.html", {
        "request": request,
        "filename": filename,
        "data": data,
        "json_escaped": json_escaped,
        "history_type": "run-once"
    })


@app.get("/history/acceptance/{filename}", response_class=HTMLResponse)
async def history_acceptance_detail(request: Request, filename: str):
    """View acceptance history detail"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Validate filename (no .., ends with .json)
    if '..' in filename or not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    history_file = project_root / "REPORTS" / "acceptance_history" / filename
    if not history_file.exists():
        raise HTTPException(status_code=404, detail="History file not found")
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading history file: {str(e)}")
    
    # Check for corresponding log file
    log_filename = filename.replace('.json', '.log')
    log_file = project_root / "REPORTS" / "acceptance_history" / log_filename
    has_log = log_file.exists()
    
    # Escape JSON for safe display
    import html
    json_str = json.dumps(data, indent=2)
    json_escaped = html.escape(json_str)
    
    return templates.TemplateResponse("history_detail.html", {
        "request": request,
        "filename": filename,
        "data": data,
        "json_escaped": json_escaped,
        "history_type": "acceptance",
        "has_log": has_log,
        "log_filename": log_filename
    })


@app.get("/mutations", response_class=HTMLResponse)
async def list_mutations(request: Request):
    """List mutation payloads"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    mutations_dir = project_root / "MUTATIONS"
    mutations = []
    
    if mutations_dir.exists():
        for f in sorted(mutations_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    mutations.append({
                        "filename": f.name,
                        "summary": data.get("summary", "No summary"),
                        "touched_paths_count": len(data.get("touched_paths", [])),
                        "touched_paths": data.get("touched_paths", []),
                        "modified_time": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    })
            except (json.JSONDecodeError, IOError):
                continue
    
    return templates.TemplateResponse("mutations.html", {
        "request": request,
        "mutations": mutations
    })


@app.get("/mutations/{filename}", response_class=HTMLResponse)
async def mutation_detail(request: Request, filename: str):
    """View mutation payload detail"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Validate filename (no .., ends with .json)
    if '..' in filename or not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    mutation_file = project_root / "MUTATIONS" / filename
    if not mutation_file.exists():
        raise HTTPException(status_code=404, detail="Mutation file not found")
    
    try:
        with open(mutation_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading mutation file: {str(e)}")
    
    # Compute current hashes and compare with base
    touched_paths = data.get("touched_paths", [])
    base_info = data.get("base", {})
    file_statuses = []
    
    for path in touched_paths:
        # Get base info
        base_file_info = base_info.get(path) if base_info else None
        base_hash = base_file_info.get("sha256") if base_file_info else None
        base_bytes = base_file_info.get("bytes", 0) if base_file_info else None
        captured_at = base_file_info.get("captured_at") if base_file_info else None
        
        # Compute current hash
        current_file = project_root / path
        current_hash = "MISSING"
        current_bytes = 0
        status = "MISSING"
        
        if current_file.exists() and current_file.is_file():
            try:
                with open(current_file, 'rb') as f:
                    current_file_bytes = f.read()
                current_hash = hashlib.sha256(current_file_bytes).hexdigest()
                current_bytes = len(current_file_bytes)
            except IOError:
                current_hash = "ERROR"
                status = "ERROR"
        
        # Determine status
        if base_hash:
            if base_hash == "MISSING":
                if current_hash == "MISSING":
                    status = "MISSING"
                else:
                    status = "NEW_FILE"  # File was missing at creation, now exists
            elif current_hash == "MISSING":
                status = "DELETED"  # File existed at creation, now missing
            elif current_hash == base_hash:
                status = "MATCH"
            else:
                status = "MISMATCH"
        else:
            # Legacy payload without base
            status = "LEGACY"
        
        file_statuses.append({
            "path": path,
            "base_hash": base_hash or "legacy/no base",
            "current_hash": current_hash,
            "base_bytes": base_bytes,
            "current_bytes": current_bytes,
            "captured_at": captured_at,
            "status": status
        })
    
    return templates.TemplateResponse("mutation_detail.html", {
        "request": request,
        "filename": filename,
        "summary": data.get("summary", "No summary"),
        "touched_paths": touched_paths,
        "changes": data.get("changes", []),
        "file_statuses": file_statuses
    })


@app.get("/diff", response_class=HTMLResponse)
async def diff_viewer(request: Request, mutation: str, path: str):
    """View diff between mutation payload and current file"""
    if not FASTAPI_AVAILABLE:
        return HTMLResponse("<h1>FastAPI not available</h1>")
    
    # Validate mutation filename
    if '..' in mutation or not mutation.endswith('.json'):
        # Allow with or without MUTATIONS/ prefix
        if not mutation.startswith('MUTATIONS/'):
            mutation = f"MUTATIONS/{mutation}"
        if '..' in mutation or not mutation.endswith('.json'):
            raise HTTPException(status_code=400, detail="Invalid mutation filename")
    
    # Remove MUTATIONS/ prefix if present
    if mutation.startswith("MUTATIONS/"):
        mutation = mutation[10:]
    
    mutation_file = project_root / "MUTATIONS" / mutation
    if not mutation_file.exists():
        raise HTTPException(status_code=404, detail="Mutation file not found")
    
    # Load mutation payload
    try:
        with open(mutation_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading mutation file: {str(e)}")
    
    # Validate path is in touched_paths
    touched_paths = payload.get("touched_paths", [])
    if path not in touched_paths:
        raise HTTPException(status_code=400, detail="Path not in mutation touched_paths")
    
    # Find matching change
    changes = payload.get("changes", [])
    proposed_content = None
    for change in changes:
        if change.get("path") == path:
            proposed_content = change.get("content", "")
            break
    
    if proposed_content is None:
        raise HTTPException(status_code=404, detail="Change not found in mutation")
    
    # Get current file content and compute hash
    current_file = project_root / path
    current_content = None
    current_hash = "MISSING"
    current_bytes = 0
    
    if current_file.exists() and current_file.is_file():
        try:
            # Read as bytes for hash computation
            with open(current_file, 'rb') as f:
                current_file_bytes = f.read()
            current_hash = hashlib.sha256(current_file_bytes).hexdigest()
            current_bytes = len(current_file_bytes)
            # Read as text for diff
            current_content = current_file.read_text(encoding='utf-8')
        except IOError:
            current_content = "[Error reading file]"
            current_hash = "ERROR"
    else:
        current_content = "[File does not exist]"
    
    # Check base hash and compute mismatch status
    base_info = payload.get("base", {})
    base_file_info = base_info.get(path) if base_info else None
    base_hash = None
    base_bytes = None
    captured_at = None
    mismatch_warning = None
    legacy_payload = False
    
    if base_file_info:
        base_hash = base_file_info.get("sha256")
        base_bytes = base_file_info.get("bytes", 0)
        captured_at = base_file_info.get("captured_at")
        
        if base_hash and base_hash != "MISSING":
            if current_hash != base_hash:
                mismatch_warning = {
                    "message": "Base mismatch: file changed since payload creation",
                    "base_sha256": base_hash,
                    "current_sha256": current_hash,
                    "captured_at": captured_at
                }
    else:
        # Legacy payload without base info
        legacy_payload = True
    
    # Generate unified diff
    import difflib
    from io import StringIO
    
    diff_lines = list(difflib.unified_diff(
        current_content.splitlines(keepends=True),
        proposed_content.splitlines(keepends=True),
        fromfile=f"current/{path}",
        tofile=f"proposed/{path}",
        lineterm=''
    ))
    
    # Limit diff size (max 2000 lines)
    MAX_DIFF_LINES = 2000
    truncated = False
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        truncated = True
    
    diff_text = ''.join(diff_lines)
    
    # Escape for HTML display
    import html
    diff_escaped = html.escape(diff_text)
    
    return templates.TemplateResponse("diff_viewer.html", {
        "request": request,
        "mutation": mutation,
        "path": path,
        "diff_text": diff_escaped,
        "truncated": truncated,
        "total_lines": len(diff_lines) if not truncated else MAX_DIFF_LINES,
        "mismatch_warning": mismatch_warning,
        "legacy_payload": legacy_payload,
        "base_hash": base_hash,
        "current_hash": current_hash
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
