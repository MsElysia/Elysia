"""
HTTP client for an OpenClaw-style gateway (see config/openclaw.json: base_url, default_skills).

Availability: GET /health, /status, /api/health, or / must return JSON.

Local dev: stub on 127.0.0.1:8765 (START_OPENCLAW_STUB.bat), or point base_url / ELYSIA_OPENCLAW_BASE_URL
at the real gateway (commonly 127.0.0.1:18789). autostart.command in openclaw.json can spawn the gateway;
ELYSIA_OPENCLAW_AUTOSTART=0 skips spawn.
"""
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def score_openclaw_result(goal: str, result: dict) -> dict:
    """
    Lightweight scoring for OpenClaw task outcomes.
    """
    goal_text = str(goal or "").strip().lower()
    ok = bool(result.get("ok"))
    error_text = str(result.get("error") or "").strip()
    payload = result.get("result")
    if not isinstance(payload, dict):
        payload = {}
    payload_blob = json.dumps(payload, ensure_ascii=False)[:3000].lower()

    success_score = 0.2
    usefulness_score = 0.2
    error_score = 0.0
    next_action = "refine_goal_and_retry"

    if ok:
        success_score = 0.85
        next_action = "apply_results_to_next_planning_step"
    if payload:
        usefulness_score += 0.25
    if any(k in payload for k in ("summary", "recommendation", "integration_notes")):
        usefulness_score += 0.2
    if any(k in payload for k in ("links", "repos", "files", "detected_issues")):
        usefulness_score += 0.2
    if any(token in payload_blob for token in ("http://", "https://", "github.com", "todo", "fix", "recommend")):
        usefulness_score += 0.15

    if error_text:
        error_score = min(1.0, 0.5 + (0.1 if "timeout" in error_text.lower() else 0.0))
        success_score = min(success_score, 0.25)
        usefulness_score = min(usefulness_score, 0.2)
        next_action = "retry_or_switch_skill"
    elif not payload:
        error_score = 0.4
        success_score = min(success_score, 0.4)
        usefulness_score = min(usefulness_score, 0.2)
        next_action = "request_more_specific_output"

    if "browser" in goal_text and "links" in payload:
        usefulness_score += 0.1
    if "github" in goal_text and any(k in payload for k in ("repos", "repo", "stars", "license")):
        usefulness_score += 0.1
    if "file" in goal_text and any(k in payload for k in ("files", "detected_issues")):
        usefulness_score += 0.1

    return {
        "success_score": max(0.0, min(1.0, float(success_score))),
        "usefulness_score": max(0.0, min(1.0, float(usefulness_score))),
        "error_score": max(0.0, min(1.0, float(error_score))),
        "recommended_next_action": str(next_action),
    }


def append_openclaw_task_log(
    *,
    goal: str,
    skill: str,
    args: Optional[Dict[str, Any]],
    response: Dict[str, Any],
    score: Optional[Dict[str, Any]] = None,
    log_path: str = "data/openclaw_tasks.jsonl",
) -> None:
    """
    Append one OpenClaw execution row to JSONL task log.
    """
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": _now_iso(),
            "goal": str(goal or "")[:800],
            "skill": str(skill or "")[:120],
            "args": dict(args or {}),
            "ok": bool(response.get("ok")),
            "result_summary": str(response.get("result") or "")[:1200],
            "error": str(response.get("error") or "")[:500] or None,
            "score": dict(score or {}),
            "task_id": response.get("task_id"),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("OpenClaw JSONL log append failed: %s", e)


class OpenClawAdapter:
    def __init__(self, config_path="config/openclaw.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.enabled = bool(self.config.get("enabled", False))
        self.base_url = str(self.config.get("base_url", "http://127.0.0.1:18789")).rstrip("/")
        self.timeout_seconds = float(self.config.get("timeout_seconds", 60))
        self.default_skills = list(self.config.get("default_skills") or [])
        self._last_task: Optional[Dict[str, Any]] = None
        self._last_error: Optional[str] = None
        self._autostart_proc: Optional[subprocess.Popen] = None
        self._autostart_owned = False
        self._maybe_autostart_worker()

    def _load_config(self) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg = raw
            except Exception as e:
                logger.warning("OpenClaw config load failed: %s", e)
        if not cfg:
            cfg = {
                "enabled": False,
                "base_url": "http://127.0.0.1:18789",
                "timeout_seconds": 60,
                "default_skills": [],
                "autostart": {"enabled": False},
            }
        else:
            cfg.setdefault("enabled", False)
            # Stubs used 8765; real OpenClaw gateway default is 18789 (see OPENCLAW_GATEWAY_PORT in UI).
            cfg.setdefault("base_url", "http://127.0.0.1:18789")
            cfg.setdefault("timeout_seconds", 60)
            cfg.setdefault("default_skills", [])
            if "autostart" not in cfg or not isinstance(cfg.get("autostart"), dict):
                cfg["autostart"] = {"enabled": False}
        env_base = (
            (os.environ.get("ELYSIA_OPENCLAW_BASE_URL") or os.environ.get("OPENCLAW_GATEWAY_URL") or "").strip()
        )
        if env_base:
            cfg["base_url"] = env_base.rstrip("/")
        return cfg

    def shutdown_autostart(self) -> None:
        """Terminate OpenClaw worker only if this adapter started it (autostart)."""
        if not self._autostart_owned or self._autostart_proc is None:
            return
        proc = self._autostart_proc
        self._autostart_proc = None
        self._autostart_owned = False
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception as e:
            logger.debug("OpenClaw autostart terminate: %s", e)
            try:
                proc.kill()
            except Exception:
                pass

    def _maybe_autostart_worker(self) -> None:
        """
        Optional local worker spawn (Ollama-style), gated by config + env.
        Set ``config/openclaw.json`` → ``autostart.enabled`` and ``autostart.command``.
        Disable with ``ELYSIA_OPENCLAW_AUTOSTART=0``.
        """
        if os.environ.get("ELYSIA_OPENCLAW_AUTOSTART", "").strip() == "0":
            logger.info("OpenClaw autostart skipped (ELYSIA_OPENCLAW_AUTOSTART=0)")
            return
        ac = self.config.get("autostart") or {}
        if not isinstance(ac, dict) or not ac.get("enabled"):
            return
        if not self.enabled:
            return
        try:
            if self.is_available():
                return
        except Exception:
            pass
        cmd = ac.get("command")
        if not isinstance(cmd, list) or not cmd:
            logger.warning("OpenClaw autostart is enabled but autostart.command is empty; not spawning")
            return
        cmd = [str(x) for x in cmd if str(x).strip()]
        if not cmd:
            return
        cwd_raw = ac.get("working_directory") or ac.get("cwd") or ""
        cwd = str(cwd_raw).strip() or None
        max_wait = int(ac.get("max_wait_seconds", 30) or 30)
        max_wait = max(5, min(120, max_wait))
        log_dir = Path(str(ac.get("log_directory") or "data/runtime")).resolve()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            log_dir = Path(".")
        out_log = log_dir / "openclaw_autostart.stdout.log"
        err_log = log_dir / "openclaw_autostart.stderr.log"
        out_f = open(out_log, "ab", buffering=0)
        err_f = open(err_log, "ab", buffering=0)
        popen_kw: Dict[str, Any] = {"cwd": cwd, "stdout": out_f, "stderr": err_f}
        if sys.platform == "win32":
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                popen_kw["creationflags"] = cf
        try:
            self._autostart_proc = subprocess.Popen(cmd, **popen_kw)
            self._autostart_owned = True
            logger.info("OpenClaw autostart: spawned pid=%s cmd=%s", self._autostart_proc.pid, cmd[0])
        except Exception as e:
            logger.warning("OpenClaw autostart spawn failed: %s", e)
            self._autostart_proc = None
            self._autostart_owned = False
            try:
                out_f.close()
            except Exception:
                pass
            try:
                err_f.close()
            except Exception:
                pass
            return
        for _ in range(max_wait):
            time.sleep(1.0)
            try:
                if self.is_available():
                    logger.info("OpenClaw autostart: worker reachable at %s", self.base_url)
                    return
            except Exception:
                pass
            if self._autostart_proc.poll() is not None:
                logger.warning(
                    "OpenClaw autostart: process exited early (code=%s); see %s / %s",
                    self._autostart_proc.returncode,
                    out_log,
                    err_log,
                )
                self._autostart_owned = False
                self._autostart_proc = None
                return
        logger.warning(
            "OpenClaw autostart: worker not reachable within %ss at %s (process may still be starting)",
            max_wait,
            self.base_url,
        )

    def _make_response(
        self,
        *,
        ok: bool,
        skill: str = "",
        task_id: str = "",
        result: Optional[Dict[str, Any]] = None,
        error_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "ok": bool(ok),
            "task_id": str(task_id or ""),
            "skill": str(skill or ""),
            "result": dict(result or {}),
            "error": str(error_text) if error_text else None,
            "timestamp": _now_iso(),
        }

    def _http_json(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(url=url, data=body, method=method.upper(), headers=headers)
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        # Any successful JSON (or empty) response counts as reachable — workers vary.
        for path in ("/health", "/status", "/api/health", "/"):
            try:
                self._http_json("GET", path)
                return True
            except Exception:
                continue
        return False

    def list_skills(self) -> List[Dict]:
        if not self.enabled:
            return [{"name": s, "source": "config_default"} for s in self.default_skills]
        try:
            out = self._http_json("GET", "/skills")
            skills = out.get("skills") if isinstance(out, dict) else []
            if isinstance(skills, list):
                return [x for x in skills if isinstance(x, dict)]
        except Exception as e:
            self._last_error = str(e)
        return [{"name": s, "source": "config_default"} for s in self.default_skills]

    def run_skill(self, skill_name: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        if not self.enabled:
            return self._make_response(
                ok=False,
                skill=skill_name,
                result={},
                error_text="openclaw_disabled",
            )
        endpoints = [
            ("POST", f"/skills/{skill_name}/run", {"args": args}),
            ("POST", "/run_skill", {"skill": skill_name, "args": args}),
            ("POST", "/tasks", {"skill": skill_name, "args": args}),
        ]
        last_error = None
        for method, path, payload in endpoints:
            try:
                raw = self._http_json(method, path, payload)
                if not isinstance(raw, dict):
                    raw = {"raw": raw}
                task_id = str(raw.get("task_id") or raw.get("id") or "")
                result_payload = raw.get("result") if isinstance(raw.get("result"), dict) else raw
                resp = self._make_response(
                    ok=bool(raw.get("ok", True)),
                    task_id=task_id,
                    skill=skill_name,
                    result=result_payload if isinstance(result_payload, dict) else {"data": result_payload},
                    error_text=str(raw.get("error") or "") or None,
                )
                self._last_task = resp
                self._last_error = resp.get("error")
                return resp
            except Exception as e:
                last_error = str(e)
                continue
        self._last_error = last_error or "openclaw_request_failed"
        return self._make_response(
            ok=False,
            skill=skill_name,
            result={},
            error_text=self._last_error,
        )

    def get_status(self) -> dict:
        if not self.enabled:
            return {
                "enabled": False,
                "available": False,
                "base_url": self.base_url,
                "skills_count": len(self.default_skills),
                "last_error": self._last_error,
            }
        for path in ("/status", "/health"):
            try:
                out = self._http_json("GET", path)
                if not isinstance(out, dict):
                    out = {}
                return {
                    "enabled": True,
                    "available": True,
                    "base_url": self.base_url,
                    "skills_count": len(self.list_skills()),
                    "remote_status": out,
                    "last_task": self._last_task,
                    "last_error": self._last_error,
                }
            except Exception as e:
                self._last_error = str(e)
        return {
            "enabled": True,
            "available": False,
            "base_url": self.base_url,
            "skills_count": len(self.default_skills),
            "last_task": self._last_task,
            "last_error": self._last_error,
        }

    def get_task_log(self, task_id: str) -> dict:
        if not self.enabled:
            return self._make_response(ok=False, task_id=task_id, error_text="openclaw_disabled")
        for path in (f"/tasks/{task_id}", f"/task/{task_id}", "/task_log"):
            try:
                if path == "/task_log":
                    out = self._http_json("GET", f"{path}?task_id={task_id}")
                else:
                    out = self._http_json("GET", path)
                return self._make_response(
                    ok=True,
                    task_id=task_id,
                    result=out if isinstance(out, dict) else {"data": out},
                )
            except Exception:
                continue
        return self._make_response(ok=False, task_id=task_id, error_text="task_log_unavailable")

    def stop_task(self, task_id: str) -> dict:
        if not self.enabled:
            return self._make_response(ok=False, task_id=task_id, error_text="openclaw_disabled")
        for method, path in (("POST", f"/tasks/{task_id}/stop"), ("POST", "/stop_task")):
            try:
                payload = {"task_id": task_id} if path == "/stop_task" else {}
                out = self._http_json(method, path, payload)
                return self._make_response(
                    ok=bool((out or {}).get("ok", True)),
                    task_id=task_id,
                    result=out if isinstance(out, dict) else {"data": out},
                    error_text=str((out or {}).get("error") or "") or None,
                )
            except Exception:
                continue
        return self._make_response(ok=False, task_id=task_id, error_text="stop_task_unavailable")

