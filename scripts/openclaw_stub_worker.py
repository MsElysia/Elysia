#!/usr/bin/env python3
"""
Minimal HTTP worker compatible with project_guardian.openclaw_adapter.OpenClawAdapter.

- Listens on 127.0.0.1:8765 by default (override with --host / --port or OPENCLAW_STUB_HOST / OPENCLAW_STUB_PORT).
- Implements GET /health, /status, /api/health, / → JSON (so is_available() succeeds).
- GET /skills → {"skills": [...]} matching config/openclaw.json default_skills.
- POST /skills/<name>/run, /run_skill, /tasks → {"ok": true, "result": {...}}.

For production, replace this with a real OpenClaw gateway on the same base_url.

Run from project root:
  python scripts/openclaw_stub_worker.py
Or: START_OPENCLAW_STUB.bat
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Default skills align with config/openclaw.json
DEFAULT_SKILLS = ["browser_research", "github_scan", "file_scan", "daily_report"]


def _load_skills_from_project_config() -> list[str]:
    root = Path(__file__).resolve().parent.parent
    cfg = root / "config" / "openclaw.json"
    if not cfg.is_file():
        return list(DEFAULT_SKILLS)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        skills = data.get("default_skills")
        if isinstance(skills, list) and skills:
            return [str(s) for s in skills if str(s).strip()]
    except Exception:
        pass
    return list(DEFAULT_SKILLS)


def make_handler(skills: list[str]):
    skill_set = frozenset(skills)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send_json(self, code: int, obj: object) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/health", "/status", "/api/health", "/"):
                self._send_json(200, {"ok": True, "service": "openclaw_stub"})
                return
            if path == "/skills":
                self._send_json(
                    200,
                    {"skills": [{"name": n, "source": "stub"} for n in skills]},
                )
                return
            self._send_json(404, {"error": "not_found", "path": path})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            if path.startswith("/skills/") and path.endswith("/run"):
                name = path[len("/skills/") : -len("/run")]
                if name not in skill_set:
                    self._send_json(
                        400,
                        {"ok": False, "error": f"unknown_skill:{name}"},
                    )
                    return
                args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "task_id": "stub-1",
                        "result": {
                            "summary": f"stub execution for {name}",
                            "integration_notes": "Replace stub worker with a real OpenClaw gateway for live results.",
                            "args_echo": args,
                        },
                    },
                )
                return
            if path == "/run_skill":
                skill = str(payload.get("skill") or "browser_research")
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "task_id": "stub-2",
                        "result": {"summary": f"stub /run_skill {skill}"},
                    },
                )
                return
            if path == "/tasks":
                skill = str(payload.get("skill") or "browser_research")
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "task_id": "stub-3",
                        "result": {"summary": f"stub /tasks {skill}"},
                    },
                )
                return
            self._send_json(404, {"error": "not_found", "path": path})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="Dev stub for OpenClaw HTTP gateway.")
    ap.add_argument("--host", default=os.environ.get("OPENCLAW_STUB_HOST", "127.0.0.1"))
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OPENCLAW_STUB_PORT", "8765")),
    )
    args = ap.parse_args()
    skills = _load_skills_from_project_config()
    handler = make_handler(skills)
    server = HTTPServer((args.host, args.port), handler)
    print(
        f"[openclaw_stub] listening http://{args.host}:{args.port} skills={skills}",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[openclaw_stub] shutdown", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
