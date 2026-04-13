#!/usr/bin/env python3
"""
Elysia - Main Program
Unified Elysia system. Orchestrates all elysia_sub_* subroutines.
Run: python elysia.py  (or python -m elysia when packaged)
"""
import atexit
import json
import os
import sys
import logging
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from elysia_config import (
    STATUS_HOST,
    STATUS_PORT,
    API_TOKEN,
    USB_MEMORY_POLICY_HELP,
    get_elysia_config,
    get_status_url,
    launch_attach_interface_standalone,
    probe_backend_alive,
    release_backend_lock,
    try_acquire_backend_lock,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)

# Add paths before any local imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "core_modules" / "elysia_core_comprehensive"))
sys.path.insert(0, str(PROJECT_ROOT / "project_guardian"))

# Configure logging with rotation
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("elysia")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("faiss.loader").setLevel(logging.WARNING)
logging.getLogger("comtypes.client._code_cache").setLevel(logging.WARNING)


def _parse_positive_int_env(name: str, default: int) -> int:
    """Parse a positive integer env var with fallback."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except (TypeError, ValueError):
        return default

# Strip ANSI escape codes from file log (Werkzeug emits colored output)
class _AnsiStripFilter(logging.Filter):
    _re = __import__("re").compile(r"\x1b\[[0-9;]*m")
    def filter(self, record):
        record.msg = self._re.sub("", str(record.msg))
        return True
for h in logging.root.handlers:
    if isinstance(h, logging.handlers.RotatingFileHandler):
        h.addFilter(_AnsiStripFilter())
        break

# Import subroutines
from elysia_sub_apikeys import load_api_keys
from elysia_sub_architect import init_architect_core
from elysia_sub_guardian import init_guardian_core
from elysia_sub_runtime_loop import init_runtime_loop
from elysia_sub_modules import init_integrated_modules
from elysia_sub_income import init_income_modules
from elysia_sub_registration import register_all_modules

# Reference for status server (set when system starts)
_status_system: Optional["UnifiedElysiaSystem"] = None


def _make_status_handler():
    """Build request handler that uses _status_system."""

    class StatusHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.debug(f"[Status] {self.address_string()} - {format % args}")

        def do_GET(self):
            if self.path == "/":
                # Browser-friendly root: show link to control panel
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                dashboard_url = "http://127.0.0.1:5000"
                if _status_system and _status_system.guardian and getattr(_status_system.guardian, "ui_panel", None):
                    dashboard_url = f"http://127.0.0.1:{getattr(_status_system.guardian.ui_panel, 'port', 5000)}"
                html = (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Elysia</title></head><body style='font-family:sans-serif;padding:2rem;'>"
                    "<h1>Elysia is running</h1>"
                    "<p><a href='" + dashboard_url + "' style='font-size:1.2rem;'>Open Control Panel</a> (" + dashboard_url + ")</p>"
                    "<p><a href='/status'>JSON status</a> | <a href='/health'>Health</a></p>"
                    "</body></html>"
                )
                self.wfile.write(html.encode("utf-8"))
            elif self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = {"status": "ok", "system": "elysia", "checks": {}}
                if _status_system:
                    body["running"] = _status_system.running
                    g = _status_system.guardian
                    if g:
                        body["checks"]["guardian"] = True
                        body["checks"]["memory"] = hasattr(g, "memory") and g.memory is not None
                        body["checks"]["ui_panel"] = getattr(g, "ui_panel", None) is not None
                        if body["checks"]["ui_panel"]:
                            body["dashboard_url"] = f"http://127.0.0.1:{getattr(g.ui_panel, 'port', 5000)}"
                    else:
                        body["checks"]["guardian"] = False
                self.wfile.write(json.dumps(body).encode())
            elif self.path == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if _status_system:
                    try:
                        body = _status_system.get_status()
                    except Exception as e:
                        body = {"error": str(e), "status": "degraded"}
                else:
                    body = {"error": "System not initialized"}
                self.wfile.write(json.dumps(body, default=str).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def _check_auth(self):
            """If API_TOKEN is set, require Authorization: Bearer <token>. Return (True, None) or (False, body)."""
            if not API_TOKEN:
                return True, None
            auth = self.headers.get("Authorization") or ""
            if auth.startswith("Bearer ") and auth[7:].strip() == API_TOKEN:
                return True, None
            return False, json.dumps({"error": "Unauthorized", "message": "Missing or invalid Authorization header"})

        def do_POST(self):
            if self.path == "/chat":
                self._handle_chat()
            elif self.path == "/v1/chat/completions":
                self._handle_openai_chat()
            else:
                self.send_response(404)
                self.end_headers()

        def _handle_openai_chat(self):
            """OpenAI-compatible POST /v1/chat/completions for OpenClaw/custom LLM clients."""
            ok, err_body = self._check_auth()
            if not ok:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body.encode())
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                data = json.loads(body) if body else {}
                messages = data.get("messages") or []
                # Use last user message (or concatenate user content)
                user_parts = [m.get("content") or "" for m in messages if (m.get("role") or "").lower() == "user"]
                message = " ".join(user_parts).strip() if user_parts else ""
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": str(e)}}).encode())
                return
            reply = ""
            err = ""
            if _status_system and message:
                try:
                    reply, err = _status_system.chat_with_llm(message)
                except Exception as e:
                    err = str(e)
            elif not _status_system:
                err = "System not initialized"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            content = reply if reply else (err or "No response")
            out = {
                "id": "elysia-%s" % datetime.now().strftime("%Y%m%d%H%M%S"),
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            self.wfile.write(json.dumps(out).encode())

        def _handle_chat(self):
            """Handle POST /chat: body = {"message": "user text"}."""
            ok, err_body = self._check_auth()
            if not ok:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body.encode())
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                data = json.loads(body) if body else {}
                message = (data.get("message") or "").strip()
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return
            reply = ""
            err = ""
            if _status_system:
                try:
                    reply, err = _status_system.chat_with_llm(message)
                except Exception as e:
                    err = str(e)
            else:
                err = "System not initialized"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            out = {"reply": reply} if reply else {}
            if err:
                out["error"] = err
            self.wfile.write(json.dumps(out).encode())

    return StatusHandler


def _run_status_server(system: "UnifiedElysiaSystem"):
    global _status_system
    _status_system = system
    try:
        handler = _make_status_handler()
        server = HTTPServer((STATUS_HOST, STATUS_PORT), handler)
        logger.info(f"Status endpoint: http://{STATUS_HOST}:{STATUS_PORT}/status")
        server.serve_forever()
    except OSError as e:
        if "WinError 10048" in str(e) or "Address already in use" in str(e):
            msg = (
                f"[Elysia Status] Port {STATUS_HOST}:{STATUS_PORT} already in use — "
                "this process will NOT bind the real Elysia /status API here.\n"
                "Another app (or old Elysia) may own the port. Check: netstat -ano | findstr :8888\n"
                "Unified UI 'attach' may talk to that other service; logs may stay quiet in elysia_unified.log."
            )
            print(msg, flush=True)
            logger.warning("Status port %s in use, skipping status server: %s", STATUS_PORT, e)
        else:
            print(f"[Elysia Status] Could not start status server: {e}", flush=True)
            logger.warning(f"Could not start status server: {e}")
    finally:
        _status_system = None


class UnifiedElysiaSystem:
    """
    Unified Elysia System. Main program delegates to elysia_sub_* subroutines.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.start_time = datetime.now()
        self.running = False

        logger.info("=" * 70)
        logger.info("Initializing Unified Elysia System (elysia.py)")
        logger.info("=" * 70)

        # [0/5] API Keys
        load_api_keys()
        
        # Startup health: single authoritative pass per boot (normalize + validate).
        # Do NOT rerun normalize/validate in start() — consume this stored result.
        try:
            from project_guardian.startup_health import run_startup_health_check
            timeout_s = _parse_positive_int_env("ELYSIA_STARTUP_HEALTH_TIMEOUT_SEC", 30)
            logger.info("[Startup] Running startup health check (timeout=%ss)", timeout_s)
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=1) as health_pool:
                future = health_pool.submit(run_startup_health_check, PROJECT_ROOT)
                try:
                    passed, issues, details = future.result(timeout=timeout_s)
                except FuturesTimeoutError:
                    elapsed = time.perf_counter() - t0
                    logger.warning(
                        "[Startup] Startup health check timed out after %.1fs; continuing with degraded preflight signal",
                        elapsed,
                    )
                    passed, issues, details = True, [f"Startup health check timed out after {elapsed:.1f}s"], {
                        "passed": True,
                        "issues": [],
                        "critical": False,
                        "timed_out": True,
                        "timeout_seconds": timeout_s,
                    }
            elapsed = time.perf_counter() - t0
            logger.info("[Startup] Startup health check completed in %.1fs", elapsed)
            self.startup_health_passed = passed
            self.startup_health_issues = issues
            self.startup_health_details = details
            if not passed:
                logger.error("Startup health check failed - check logs above")
                sys.exit(1)
        except Exception as e:
            logger.warning("Startup health check error (continuing): %s", e)
            self.startup_health_passed = True
            self.startup_health_issues = [f"Startup health check exception: {e}"]
            self.startup_health_details = {"passed": True, "issues": [], "critical": False}
        
        logger.info("Unified Elysia System initialized successfully")

        # [1/5] Guardian Core first (Architect's WebScout needs web_reader from Guardian)
        self.guardian = init_guardian_core(config=self.config)

        # [2/5] Architect-Core
        self.architect = init_architect_core()

        # [3/5] Runtime Loop
        self.runtime_loop = init_runtime_loop()

        # [4/5] Integrated Modules
        self.modules = init_integrated_modules(
            architect=self.architect,
            guardian=self.guardian,
            runtime_loop=self.runtime_loop,
            config=self.config,
        )
        init_income_modules(self.modules, PROJECT_ROOT)
        if self.guardian and hasattr(self.guardian, "wire_modules"):
            self.guardian.wire_modules(self.modules)

        # [5/5] Register with Architect
        register_all_modules(self.architect)
        # So the control panel (guardian.ui_panel) can call Elysia's chat, income, harvest, etc.
        if self.guardian is not None:
            self.guardian._unified_system = self
            # Propagate startup health to GuardianCore so startup verification can see it
            try:
                self.guardian._startup_health = {
                    "passed": getattr(self, "startup_health_passed", True),
                    "issues": getattr(self, "startup_health_issues", []),
                    "details": getattr(self, "startup_health_details", {}),
                }
            except Exception:
                pass

    def get_income_generator(self):
        return self.modules.get("income_generator")

    def get_financial_manager(self):
        return self.modules.get("financial_manager")

    def get_revenue_creator(self):
        return self.modules.get("revenue_creator")

    def get_wallet(self):
        return self.modules.get("wallet")

    def _compute_startup_phase_label(self, status: Dict[str, Any]) -> str:
        """Short human-readable boot phase for /status (launcher polling, attach UX)."""
        op = status.get("operational_state") or {}
        if op.get("deferred_init_running"):
            return "loading_memory_and_vectors"
        if op.get("deferred_init_failed"):
            return "deferred_init_failed"
        dis = str(op.get("deferred_init_state", "") or "").lower()
        if dis in ("running", "in_progress", "pending"):
            return "loading_memory_and_vectors"
        comps = status.get("components") or {}
        if not comps.get("guardian_core"):
            return "initializing_guardian"
        if not comps.get("runtime_loop"):
            return "starting_runtime_loop"
        im = comps.get("integrated_modules")
        if isinstance(im, int) and im == 0:
            return "registering_modules"
        if op.get("vector_rebuild_pending") or op.get("vector_degraded"):
            return "loading_vectors"
        if self.running:
            return "running"
        return "starting"

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status. operational_state is canonical; top-level copies for backward compat."""
        status = {
            "system": "Unified Elysia System",
            "uptime": str(datetime.now() - self.start_time),
            "running": self.running,
            "start_time": str(self.start_time),
            "components": {
                "architect_core": self.architect is not None,
                "guardian_core": self.guardian is not None,
                "runtime_loop": self.runtime_loop is not None,
                "integrated_modules": len(self.modules),
            },
        }
        if self.architect:
            try:
                status["architect_status"] = self.architect.get_status_report()
            except Exception:
                pass
        if self.guardian:
            # Canonical operational state: single source for deferred/vector/dashboard
            op: Dict[str, Any] = {}
            try:
                op = self.guardian.get_startup_operational_state() if hasattr(self.guardian, "get_startup_operational_state") else {}
            except Exception:
                pass
            status["operational_state"] = op
            try:
                gs = self.guardian.get_system_status()
                status["guardian_status"] = gs
                if hasattr(self.guardian, "get_resource_stats"):
                    stats = self.guardian.get_resource_stats()
                    if stats:
                        status["resource_stats"] = stats
            except Exception:
                pass
        income_status = {}
        if "income_generator" in self.modules:
            try:
                income_status["income_generator"] = {
                    "available": True,
                    "total_earned": self.modules["income_generator"].income_data.get("total_earned", 0),
                    "active_projects": len(self.modules["income_generator"].income_data.get("active_projects", [])),
                }
            except Exception:
                income_status["income_generator"] = {"available": True, "status": "unknown"}
        if "financial_manager" in self.modules:
            try:
                income_status["financial_manager"] = {
                    "available": True,
                    "cash_balance": self.modules["financial_manager"].cash_balance,
                    "monthly_income": self.modules["financial_manager"].monthly_income,
                }
            except Exception:
                income_status["financial_manager"] = {"available": True, "status": "unknown"}
        if "wallet" in self.modules:
            try:
                income_status["wallet"] = {
                    "available": True,
                    "balance": getattr(self.modules["wallet"], "balance", 0),
                }
            except Exception:
                income_status["wallet"] = {"available": True, "status": "unknown"}
        if "harvest_engine" in self.modules:
            try:
                he = self.modules["harvest_engine"]
                if hasattr(he, "get_account_status"):
                    income_status["harvest_engine"] = {"available": True, **he.get_account_status()}
                elif hasattr(he, "generate_income_report"):
                    report = he.generate_income_report()
                    income_status["harvest_engine"] = {"available": True, "report": report if isinstance(report, dict) else str(report)[:200]}
                else:
                    income_status["harvest_engine"] = {"available": True, "status": "unknown"}
            except Exception as e:
                income_status["harvest_engine"] = {"available": True, "status": "error", "error": str(e)[:100]}
        if income_status:
            status["income_modules"] = income_status
        # Dashboard URL so scripts and users can open the control panel
        try:
            if self.guardian and getattr(self.guardian, "ui_panel", None) and self.guardian.ui_panel:
                port = getattr(self.guardian.ui_panel, "port", 5000)
                status["dashboard_url"] = f"http://127.0.0.1:{port}"
        except Exception:
            pass
        # All operational fields below: copy from canonical operational_state only (backward compat)
        op = status.get("operational_state") or {}
        status["dashboard_ready"] = bool(op.get("dashboard_ready", False))
        status["deferred_init_running"] = op.get("deferred_init_running", False)
        status["deferred_init_failed"] = op.get("deferred_init_failed", False)
        status["deferred_init_error"] = op.get("deferred_init_error")
        status["deferred_init_state"] = op.get("deferred_init_state", "not_started")
        status["vector_rebuild_pending"] = op.get("vector_rebuild_pending", False)
        status["vector_degraded"] = op.get("vector_degraded", False)
        status["last_vector_rebuild_attempt_at"] = op.get("last_vector_rebuild_attempt_at")
        status["last_vector_rebuild_result"] = op.get("last_vector_rebuild_result")
        status["last_vector_rebuild_reason"] = op.get("last_vector_rebuild_reason")
        status["last_vector_rebuild_error"] = op.get("last_vector_rebuild_error")
        status["resolved_memory_filepath"] = op.get("resolved_memory_filepath")
        # Warnings from canonical operational_state only
        defer_state = op.get("deferred_init_state", "not_started")
        if defer_state == "inconsistent":
            status.setdefault("warnings", []).append("Deferred initialization state inconsistent")
        elif op.get("deferred_init_failed"):
            err = op.get("deferred_init_error")
            status.setdefault("warnings", []).append(f"Deferred initialization failed: {err}" if err else "Deferred initialization failed")
        elif op.get("deferred_init_running"):
            status.setdefault("warnings", []).append("Deferred initialization still in progress")
        if op.get("vector_rebuild_pending"):
            status.setdefault("warnings", []).append("Vector rebuild pending")
        result = op.get("last_vector_rebuild_result")
        if result == "skipped":
            reason = op.get("last_vector_rebuild_reason") or "unknown"
            status.setdefault("warnings", []).append(f"Last vector rebuild skipped: {reason}")
        elif result == "failed":
            err = op.get("last_vector_rebuild_error") or op.get("last_vector_rebuild_reason") or "unknown"
            status.setdefault("warnings", []).append(f"Last vector rebuild failed: {err}")
        status["startup_phase"] = self._compute_startup_phase_label(status)
        return status

    def _unified_chat_llm_router_enabled(self) -> bool:
        try:
            p = PROJECT_ROOT / "config" / "mistral_decider.json"
            if not p.exists():
                return True
            with open(p, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("unified_chat_llm_router", True))
        except Exception:
            return True

    def _mistral_model_for_chat(self) -> str:
        try:
            p = PROJECT_ROOT / "config" / "mistral_decider.json"
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    m = (json.load(f).get("mistral_decider_model") or "mistral").strip()
                    return m or "mistral"
        except Exception:
            pass
        return "mistral"

    def _llm_completion_cloud_openai(self, messages: List[Dict[str, Any]], max_tokens: int) -> Tuple[str, str]:
        reply, err = "", ""
        ig = self.get_income_generator()
        if ig and getattr(ig, "api_manager", None):
            api = ig.api_manager
            client = api.get_openai_client() if hasattr(api, "get_openai_client") else None
            if client:
                try:
                    r = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        max_tokens=max_tokens,
                    )
                    if r.choices:
                        reply = (r.choices[0].message.content or "").strip()
                except Exception as e:
                    err = str(e)
                    try:
                        from project_guardian.openai_degraded import note_openai_transport_failure

                        note_openai_transport_failure(e, context="elysia_cloud_openai")
                    except Exception:
                        pass
            else:
                err = "No OpenAI client"
        else:
            err = "Income generator or API manager not available."
        return reply, err

    def _llm_completion_cloud_openrouter(self, messages: List[Dict[str, Any]], max_tokens: int) -> Tuple[str, str]:
        reply, err = "", ""
        ig = self.get_income_generator()
        if ig and getattr(ig, "api_manager", None):
            api = ig.api_manager
            if hasattr(api, "openrouter_key") and api.openrouter_key:
                try:
                    out = api.openrouter_chat(
                        "openai/gpt-3.5-turbo",
                        messages,
                        max_tokens=max_tokens,
                    )
                    if "error" in out:
                        err = out["error"]
                    elif out.get("choices"):
                        reply = (out["choices"][0].get("message", {}).get("content") or "").strip()
                except Exception as e:
                    err = str(e)
            else:
                err = "No OpenRouter key"
        else:
            err = "Income generator or API manager not available."
        return reply, err

    def _llm_completion_cloud_preferred(self, messages: List[Dict[str, Any]], max_tokens: int) -> Tuple[str, str]:
        reply, err = self._llm_completion_cloud_openai(messages, max_tokens)
        if reply or not err:
            return reply, err
        return self._llm_completion_cloud_openrouter(messages, max_tokens)

    def _chat_with_llm_cloud_only(self, message: str) -> Tuple[str, str]:
        """Cloud APIs only when unified routing is off; uses Guardian prompt stack (see elysia_llm_fallback)."""
        from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion

        return elysia_cloud_fallback_completion(
            [{"role": "user", "content": message}],
            500,
            cloud_preferred=self._llm_completion_cloud_preferred,
            caller="UnifiedElysiaSystem._chat_with_llm_cloud_only",
        )

    def chat_with_llm(self, message: str):
        """
        Send a chat message via unified router (capability preamble + Ollama vs cloud), or legacy cloud-only.
        Returns (reply_text, error_string). One will be empty.
        """
        if not self._unified_chat_llm_router_enabled():
            return self._chat_with_llm_cloud_only(message)
        try:
            from project_guardian.unified_llm_route import unified_chat_completion

            msgs = [{"role": "user", "content": message}]
            reply, err, _meta = unified_chat_completion(
                messages=msgs,
                max_tokens=500,
                guardian=self.guardian,
                cloud_openai_call=lambda m, mt: self._llm_completion_cloud_openai(m, mt),
                cloud_openrouter_call=lambda m, mt: self._llm_completion_cloud_openrouter(m, mt),
                mistral_model=self._mistral_model_for_chat(),
                module_name="planner",
                agent_name="orchestrator",
            )
            return reply, err
        except Exception as e:
            logger.warning("Unified chat router failed (%s); falling back to cloud-only", e)
            from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion

            return elysia_cloud_fallback_completion(
                [{"role": "user", "content": message}],
                500,
                cloud_preferred=self._llm_completion_cloud_preferred,
                caller="UnifiedElysiaSystem.chat_with_llm.fallback",
            )

    def _llm_completion(
        self,
        messages,
        max_tokens: int = 2000,
        *,
        module_name: str = "planner",
        agent_name: Optional[str] = "orchestrator",
        prompt_extra: Optional[Dict[str, Any]] = None,
        skip_capability_preamble: bool = False,
    ):
        """Call LLM with custom max_tokens. Returns (reply_text, error_string)."""
        if not isinstance(messages, list):
            messages = [{"role": "user", "content": str(messages)}]
        if not self._unified_chat_llm_router_enabled():
            from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion

            return elysia_cloud_fallback_completion(
                messages,
                max_tokens,
                cloud_preferred=self._llm_completion_cloud_preferred,
                caller="UnifiedElysiaSystem._llm_completion",
                module_name=module_name,
                agent_name=agent_name,
                prompt_extra=prompt_extra,
            )
        try:
            from project_guardian.unified_llm_route import unified_chat_completion

            reply, err, _ = unified_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                guardian=self.guardian,
                cloud_openai_call=lambda m, mt: self._llm_completion_cloud_openai(m, mt),
                cloud_openrouter_call=lambda m, mt: self._llm_completion_cloud_openrouter(m, mt),
                mistral_model=self._mistral_model_for_chat(),
                skip_capability_preamble=skip_capability_preamble,
                module_name=module_name,
                agent_name=agent_name,
                prompt_extra=prompt_extra,
            )
            return reply, err
        except Exception as e:
            logger.warning("Unified LLM completion failed (%s); cloud fallback", e)
            from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion

            return elysia_cloud_fallback_completion(
                messages,
                max_tokens,
                cloud_preferred=self._llm_completion_cloud_preferred,
                caller="UnifiedElysiaSystem._llm_completion.fallback",
                module_name=module_name,
                agent_name=agent_name,
                prompt_extra=prompt_extra,
            )

    def condense_memory_with_ai(self, memory_threshold: int = 4000, chunk_size: int = 80, max_to_condense: int = 2000, max_workers: int = 4) -> bool:
        """
        When memory is full, upload oldest memories to the LLM in parallel chunks to condense
        and eliminate redundancies, then replace the original segment with condensed entries.
        Called automatically before standard consolidate when condense_callback is set.
        Returns True if condensation ran and reduced count; False otherwise.
        """
        if not self.guardian or not hasattr(self.guardian, "memory"):
            return False
        memory_obj = self.guardian.memory
        if hasattr(memory_obj, "json_memory"):
            memory_obj = memory_obj.json_memory
        if not hasattr(memory_obj, "memory_log"):
            return False
        log = memory_obj.memory_log
        total = len(log)
        if total <= memory_threshold:
            return False
        # How many oldest entries to condense (cap to avoid huge prompts)
        to_condense = min(total - memory_threshold, max_to_condense)
        if to_condense <= 0:
            return False
        # Chunks for parallel processing
        chunks = []
        for start in range(0, to_condense, chunk_size):
            end = min(start + chunk_size, to_condense)
            chunks.append((start, end, log[start:end]))
        if not chunks:
            return False

        from project_guardian.memory_condense_helpers import (
            build_memory_condense_prompt_extra,
            parse_condensed_memory_json,
        )

        def process_chunk(args):
            start, end, mems = args
            lines = []
            for m in mems:
                t = m.get("thought", "")
                cat = m.get("category", "general")
                pri = m.get("priority", 0.5)
                ts = m.get("time", "")[:19] if m.get("time") else ""
                lines.append(f"[{ts}] {cat} {pri} | {t[:500]}")
            chunk_text = "\n".join(lines)
            prompt_extra = build_memory_condense_prompt_extra(chunk_text)
            user_msg = [{"role": "user", "content": "Memory condensation task (structured JSON per OUTPUT CONTRACT)."}]

            def _one_call():
                return self._llm_completion(
                    user_msg,
                    max_tokens=1500,
                    module_name="memory_condense",
                    agent_name=None,
                    prompt_extra=prompt_extra,
                    skip_capability_preamble=True,
                )

            reply, err = _one_call()
            if err or not reply:
                return start, end, None, err
            arr, perr = parse_condensed_memory_json(reply)
            if perr == "JSON parse failed":
                reply2, err2 = _one_call()
                if not err2 and reply2:
                    arr, perr = parse_condensed_memory_json(reply2)
            if perr:
                return start, end, None, perr
            out = []
            now = datetime.now().isoformat()
            for i, item in enumerate(arr):
                if not isinstance(item, dict):
                    continue
                thought = item.get("thought") or item.get("content") or str(item)
                category = item.get("category", "consensus")
                priority = float(item.get("priority", 0.5))
                priority = max(0.0, min(1.0, priority))
                out.append({
                    "time": now,
                    "thought": thought[:2000] if isinstance(thought, str) else str(thought),
                    "category": category,
                    "priority": priority,
                    "metadata": {"condensed": True, "chunk": f"{start}-{end}"},
                })
            return start, end, out, None

        condensed_all = []  # list of (start, end, entries)
        errors = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_chunk, c): c for c in chunks}
            for future in as_completed(futures):
                start, end, entries, err = future.result()
                if err:
                    errors.append(err)
                if entries:
                    condensed_all.append((start, end, entries))
        if not condensed_all:
            if errors:
                logger.warning(f"[Condense] AI condensation failed: {errors[0]}")
            return False
        # Build new log: keep leading uncondensed, then condensed segments, fill gaps with original, then tail
        condensed_all.sort(key=lambda x: x[0])
        new_log = []
        # Leading segment before first condensed chunk
        if condensed_all[0][0] > 0:
            new_log.extend(log[0 : condensed_all[0][0]])
        for i, (start, end, entries) in enumerate(condensed_all):
            new_log.extend(entries)
            # Gap until next chunk: keep original
            if i + 1 < len(condensed_all):
                next_start = condensed_all[i + 1][0]
                if end < next_start:
                    new_log.extend(log[end:next_start])
        new_log.extend(log[to_condense:])
        # Replace and save
        memory_obj.memory_log = new_log
        if hasattr(memory_obj, "_save"):
            try:
                memory_obj._save()
            except Exception as e:
                logger.warning(f"[Condense] Save after condensation failed: {e}")
        logger.info(f"[Condense] AI condensation: {total} -> {len(new_log)} memories (condensed {to_condense} entries)")
        return True

    def start(self):
        """Start the unified system."""
        logger.info("=" * 70)
        logger.info("Starting Unified Elysia System")
        logger.info("=" * 70)

        # Runtime config normalize/validate: already run once in __init__ via run_startup_health_check.
        # Consume stored startup_health_details; do NOT rerun.

        self.running = True

        # Embeddings: immediate only when not deferring heavy startup (else Phase B in guardian)
        if self.guardian and not getattr(self.guardian, "_defer_heavy_startup", False):
            mem = self.guardian.memory
            root = mem.json_memory if hasattr(mem, "json_memory") else mem
            if hasattr(root, "enable_embeddings"):
                root.enable_embeddings()
            elif hasattr(mem, "enable_embeddings"):
                mem.enable_embeddings()

        # Phase B after dashboard ready (does not block this path)
        if self.guardian and getattr(self.guardian, "_defer_heavy_startup", False):
            def _defer_after_dashboard():
                import time as _time
                panel = getattr(self.guardian, "ui_panel", None)
                ready_fn = getattr(panel, "is_ready", None) if panel else None
                if callable(ready_fn):
                    for _ in range(600):
                        try:
                            if ready_fn():
                                logger.info("[Startup] Dashboard ready — spawning deferred initialization")
                                break
                        except Exception:
                            pass
                        _time.sleep(0.2)
                    else:
                        logger.warning(
                            "[Startup] Dashboard not ready within timeout; running deferred initialization anyway"
                        )
                else:
                    logger.info("[Startup] No dashboard is_ready(); running deferred initialization")
                threading.Thread(
                    target=self.guardian.start_deferred_initialization,
                    daemon=True,
                ).start()

            threading.Thread(target=_defer_after_dashboard, daemon=True).start()

        # When memory is full, run AI condensation before standard cleanup (parallel + series processing)
        if self.guardian and hasattr(self.guardian, "monitor") and self.guardian.monitor is not None:
            self.guardian.monitor.condense_callback = lambda thresh: self.condense_memory_with_ai(memory_threshold=thresh)

        if self.runtime_loop and hasattr(self.runtime_loop, "start"):
            try:
                threading.Thread(target=self.runtime_loop.start, daemon=True).start()
                logger.info("Runtime loop started")
            except Exception as e:
                logger.warning(f"Could not start runtime loop: {e}")

        # Auto-learning: gather AI, income, etc. from Reddit/RSS, store on thumb drive
        auto_cfg = self.config.get("auto_learning", {})
        if auto_cfg.get("enabled", True):
            try:
                from project_guardian.auto_learning import AutoLearningScheduler, get_learned_storage_path, get_chatlogs_path
                self.auto_learning = AutoLearningScheduler(
                    system_ref=self,
                    interval_hours=auto_cfg.get("interval_hours", 6),
                    storage_path=Path(get_learned_storage_path()),
                    chatlogs_path=Path(get_chatlogs_path()),
                    max_chatlogs=auto_cfg.get("max_chatlogs", 20),
                )
                defer_al = self.guardian and getattr(self.guardian, "_defer_heavy_startup", False)
                if defer_al:
                    # First _run_once() is heavy (HTTP + parsing); wait until Phase B finishes or fails
                    def _auto_learning_after_deferred():
                        g = self.guardian
                        max_wait = 1200
                        for _ in range(max_wait):
                            if not self.running:
                                return
                            if getattr(g, "deferred_init_complete", False) or getattr(g, "deferred_init_failed", False):
                                break
                            time.sleep(1)
                        else:
                            logger.warning(
                                "[Startup] Auto-learning: deferred init wait exceeded %ds; starting scheduler anyway",
                                max_wait,
                            )
                        if self.running and getattr(self, "auto_learning", None):
                            self.auto_learning.start()
                            logger.info("Auto-learning started after Phase B (AI, income, etc. -> thumb drive)")

                    threading.Thread(
                        target=_auto_learning_after_deferred,
                        daemon=True,
                        name="AutoLearningAfterDeferred",
                    ).start()
                else:
                    self.auto_learning.start()
                    logger.info("Auto-learning started (AI, income, etc. -> thumb drive)")
            except Exception as e:
                logger.warning(f"Auto-learning not started: {e}")
                self.auto_learning = None
        else:
            self.auto_learning = None

        # Start status/health HTTP endpoint
        try:
            t = threading.Thread(target=_run_status_server, args=(self,), daemon=True)
            t.start()
        except Exception as e:
            logger.debug(f"Status server not started: {e}")

        logger.info("Unified Elysia System is running")
        logger.info("=" * 70)

    def shutdown(self):
        """Shutdown the system gracefully."""
        logger.info("Shutting down Unified Elysia System...")
        self.running = False
        if getattr(self, "auto_learning", None):
            try:
                self.auto_learning.stop()
            except Exception:
                pass
        if self.guardian and hasattr(self.guardian, "shutdown"):
            try:
                self.guardian.shutdown()
            except Exception:
                pass
        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    # Dedicated backend starter (Start_Elysia_Backend.cmd) must always run full boot;
    # a loose /status probe can otherwise match unrelated services and exit with no server.
    _force_full = os.environ.get("ELYSIA_FORCE_FULL_BACKEND", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if _force_full:
        print(
            "[Elysia] ELYSIA_FORCE_FULL_BACKEND is set — full backend boot "
            "(attach-only /status probe skipped).",
            flush=True,
        )
        logger.info("[Launcher] ELYSIA_FORCE_FULL_BACKEND active — forcing full backend boot")
    # 1) Live /status → attach UI only (never a second heavy backend boot)
    if not _force_full and probe_backend_alive():
        su = get_status_url()
        logger.info("[Launcher] Existing backend detected; skipping backend start")
        print("\n" + "=" * 70, flush=True)
        print("ATTACH-ONLY MODE (/status already returned usable JSON)", flush=True)
        print("=" * 70, flush=True)
        print(
            "Something on this machine already answered GET /status like Elysia. "
            "Skipping GuardianCore / full backend boot.",
            flush=True,
        )
        print(f"Status URL: {su}/status", flush=True)
        print(
            "If that is NOT Elysia, free the port or set ELYSIA_STATUS_PORT. "
            "To force full boot anyway: set ELYSIA_FORCE_FULL_BACKEND=1 (see Start_Elysia_Backend.cmd).",
            flush=True,
        )
        print("=" * 70 + "\n", flush=True)
        launch_attach_interface_standalone()
        sys.exit(0)

    # 2) Exclusive PID lock before heavy init (another process booting or running)
    ok_lock, lock_detail = try_acquire_backend_lock()
    if not ok_lock:
        logger.warning("[BackendLock] Refusing duplicate backend start: %s", lock_detail)
        print("\n" + "=" * 70)
        print("ELYSIA - Duplicate backend start refused")
        print("=" * 70)
        print(lock_detail)
        print("Another elysia.py backend is already running or still starting.")
        print("When /status is ready, re-run the launcher or: python elysia_interface.py --attach-only")
        print("=" * 70 + "\n")
        sys.exit(2)

    atexit.register(release_backend_lock)

    print("\n" + "=" * 70)
    print("ELYSIA - Unified Program")
    print("Main: elysia.py  |  Subroutines: elysia_sub_*.py")
    print("=" * 70 + "\n")

    config = get_elysia_config()
    sp = config.get("storage_path")
    td = config.get("thumb_drive_available", False)
    if sp:
        print(f"Memory Storage: {sp}")
        print(f"Thumb Drive Available: {td}")
    else:
        print("Memory Storage: (using defaults)")
    if config.get("usb_memory_policy"):
        pol = config.get("usb_memory_policy")
        pdrv = config.get("usb_primary_drive", "")
        sdrv = config.get("usb_secondary_drive") or "(none)"
        pa = config.get("usb_primary_available")
        sa = config.get("usb_secondary_available")
        targets = config.get("usb_active_write_targets") or [sp]
        logger.info(
            "[USBMemory] policy=%s primary=%s available=%s secondary=%s available=%s active_write_targets=%s",
            pol,
            pdrv,
            pa,
            sdrv,
            sa,
            targets,
        )
        if config.get("usb_archive_root"):
            logger.info("[USBMemory] archive_root=%s", config.get("usb_archive_root"))
        if config.get("usb_storage_degraded"):
            for note in config.get("usb_degraded_notes") or []:
                logger.warning("[USBMemory] degraded: %s", note)
        if pol == "mirror":
            logger.info(
                "[USBMemory] scope: mirror only replicates guardian_memory.json to the secondary USB "
                "after MemoryCore JSON saves; trust, tasks, and vectors are not mirrored."
            )
        elif pol == "split":
            logger.info(
                "[USBMemory] scope: split uses the secondary USB for archive/backup paths when available; "
                "active memory, trust, and tasks JSON files stay on the active storage root only."
            )
        if pol in ("mirror", "split"):
            logger.info("[USBMemory] policy guidance: %s", USB_MEMORY_POLICY_HELP)
    system = UnifiedElysiaSystem(config=config)
    system.start()

    # Canonical sources: status (operational_state from GuardianCore), startup_summary (verification)
    status = system.get_status()
    startup_summary = {}
    startup_status = "unknown"
    startup_warnings = 0
    startup_duration = None
    if getattr(system, "guardian", None) is not None and hasattr(system.guardian, "get_startup_verification"):
        try:
            startup_summary = system.guardian.get_startup_verification()
            startup_status = startup_summary.get("status", "unknown")
            startup_warnings = startup_summary.get("warnings", 0)
            startup_duration = startup_summary.get("duration_seconds", None)
        except Exception:
            startup_status = "unknown"
            startup_warnings = 0
            startup_duration = None
    print("\n" + "=" * 70)
    print("SYSTEM STATUS")
    print("=" * 70)
    print(f"Uptime: {status['uptime']}")
    print("Components:")
    for comp, available in status["components"].items():
        icon = "[OK]" if available else "[FAIL]"
        print(f"  {icon} {comp}: {'Available' if available else 'Unavailable'}")
    print(f"Integrated Modules: {status['components']['integrated_modules']}")

    # Startup summary
    print("\nStartup:")
    status_label = startup_status.upper()
    print(f"  Status: {status_label}")
    print(f"  Warnings: {startup_warnings}")
    if startup_duration is not None:
        print(f"  Duration: {startup_duration:.2f}s")
    else:
        print("  Duration: (unavailable)")

    if "hestia_bridge" in system.modules:
        hs = system.modules["hestia_bridge"].get_status()
        print(f"\nHestia Status:")
        print(f"  Connected: {'[OK]' if hs['connected'] else '[FAIL]'}")
        print(f"  Data Available: {'[OK]' if hs['data_available'] else '[FAIL]'}")
        print(f"  Path: {hs['hestia_path']}")

    print(f"\nStatus API: http://{STATUS_HOST}:{STATUS_PORT}/status")
    dashboard = status.get("dashboard_url")
    # dashboard_ready: from status, which copies from canonical operational_state
    dashboard_ready = status.get("dashboard_ready", bool(dashboard))
    if dashboard:
        print(f"Control Panel: {dashboard}")
    # Compact warning lines when success_with_warnings (up to 3, no duplicates)
    if startup_status == "success_with_warnings":
        warn_lines: List[str] = []
        seen: set = set()
        def _add(s: str, norm: bool = False):
            key = s[:60] if len(s) > 60 else s
            if key not in seen and len(warn_lines) < 3:
                seen.add(key)
                warn_lines.append(s)

        for issue in getattr(system, "startup_health_issues", []) or []:
            if issue and "[Startup] Normalized" in str(issue):
                _add(str(issue), norm=True)
            elif issue and "Config" not in str(issue)[:20]:
                _add(str(issue)[:120])
        for c in startup_summary.get("checks", []):
            if c.get("status") == "warning" and c.get("message"):
                name = str(c.get("name", ""))
                msg = c.get("message", "")
                if name in ("deferred_init_pending", "memory_not_loaded", "vector_not_loaded",
                            "vector_degraded", "vector_rebuild_pending", "dashboard_not_ready"):
                    _add(msg)
        for line in warn_lines:
            print(f"  [!] {line}")

    print("=" * 70)
    # Final call-to-action based on startup status and dashboard readiness
    if startup_status == "clean_success" and dashboard_ready:
        print(f">>> Ready - Open {dashboard} in your browser <<<")
    elif startup_status == "success_with_warnings" and dashboard_ready:
        print(f">>> Ready with warnings - Open {dashboard} in your browser <<<")
    elif startup_status == "failed":
        print(">>> Startup failed - Review logs before using the dashboard <<<")

    # Do not call system.shutdown() inside the SIGINT handler: on Windows that can deadlock
    # (handler runs in a restricted context while other threads hold locks). Request stop here,
    # run shutdown on the main thread after the wait loop exits.
    _shutdown_requested = threading.Event()

    def _request_shutdown(sig, frame):
        if not _shutdown_requested.is_set():
            print("\n\nShutdown signal received...", flush=True)
        _shutdown_requested.set()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    try:
        while not _shutdown_requested.is_set():
            _shutdown_requested.wait(timeout=1.0)
    except KeyboardInterrupt:
        if not _shutdown_requested.is_set():
            print("\n\nShutdown signal received...", flush=True)
        _shutdown_requested.set()

    print("\nShutting down...", flush=True)
    try:
        system.shutdown()
    except Exception as e:
        logger.debug("Shutdown: %s", e)
    try:
        release_backend_lock()
    except Exception:
        pass
    print("Goodbye!", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
