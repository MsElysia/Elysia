"""
Run the real Elysia dashboard (project_guardian/ui_control_panel.py) against a
fictional, in-memory orchestrator for browser acceptance testing.

- Loads the dashboard module by file path, so GuardianCore / the project_guardian
  package __init__ is never imported or started.
- Binds to 127.0.0.1 only. No providers, credentials, memory files or autonomy.
- Chat goes to the Ollama HTTP API at OLLAMA_BASE_URL (default
  http://127.0.0.1:11434) using the configured model; nothing else.
- ``--stub-ollama PORT`` additionally starts a fake Ollama-API server (labelled
  "STUB" in every reply) for machines without a local model.

Usage:
    python scripts/dashboard_fictional_harness.py --mode fictional --port 5055
    python scripts/dashboard_fictional_harness.py --mode none --port 5055
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PANEL_PATH = ROOT / "project_guardian" / "ui_control_panel.py"


def load_panel_module():
    spec = importlib.util.spec_from_file_location("elysia_ui_control_panel_standalone", PANEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ollama_chat(message: str, timeout: float = 120.0):
    import requests

    base = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = (os.environ.get("ELYSIA_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "").strip()
    if not model:
        return None, "No model configured (set ELYSIA_OLLAMA_MODEL)"
    try:
        r = requests.post(
            f"{base}/api/chat",
            json={"model": model, "stream": False, "messages": [{"role": "user", "content": message}]},
            timeout=timeout,
        )
    except Exception as e:
        return None, f"Local model unreachable at {base}: {e}"
    if r.status_code != 200:
        return None, f"Ollama HTTP {r.status_code} for model {model!r}: {r.text[:200]}"
    content = ((r.json() or {}).get("message") or {}).get("content") or ""
    return content, None


class FictionalUnifiedSystem:
    def chat_with_llm(self, message: str):
        reply, err = _ollama_chat(message)
        if err:
            return None, err
        return reply, None


class FictionalLoop:
    def __init__(self, running: bool):
        self.running = running
        self.paused = False
        self.task_queue = SimpleNamespace(get_queue_size=lambda: 0)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def build_orchestrator(mode: str):
    if mode == "none":
        return None
    loop_running = mode == "fictional"
    orch = SimpleNamespace()
    orch._initialized = True
    orch._running = loop_running
    orch.elysia_loop = FictionalLoop(running=loop_running)
    orch.memory = None
    orch.start_time = None
    orch._unified_system = FictionalUnifiedSystem()
    return orch


def start_stub_ollama(port: int, models):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/tags":
                self._send(200, {"models": [{"name": m} for m in models]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path != "/api/chat":
                return self._send(404, {"error": "not found"})
            model = req.get("model")
            if model not in models:
                return self._send(404, {"error": f"model '{model}' not found"})
            text = (req.get("messages") or [{}])[-1].get("content", "")
            self._send(200, {"model": model, "message": {"role": "assistant",
                             "content": f"[STUB {model}] received: {text}"}, "done": True})

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["none", "fictional", "stopped"], default="fictional")
    ap.add_argument("--port", type=int, default=5055)
    ap.add_argument("--stub-ollama", type=int, default=0)
    ap.add_argument("--stub-models", default="llama3.2:3b")
    args = ap.parse_args()

    if args.stub_ollama:
        start_stub_ollama(args.stub_ollama, [m for m in args.stub_models.split(",") if m])
        os.environ["OLLAMA_BASE_URL"] = f"http://127.0.0.1:{args.stub_ollama}"
        print(f"[harness] STUB Ollama API on 127.0.0.1:{args.stub_ollama} models={args.stub_models}")

    mod = load_panel_module()
    panel = mod.UIControlPanel(orchestrator=build_orchestrator(args.mode), host="127.0.0.1", port=args.port)
    panel.start(source="fictional_harness")
    print(f"[harness] dashboard mode={args.mode} on http://127.0.0.1:{panel.port}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
