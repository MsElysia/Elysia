"""Serve the existing dashboard with fictional state and read-only HTTP access.

Run with: python scripts/verify_dashboard_windows.py
Stop with Ctrl+C; the process owns the server and releases its port on exit.
"""

import argparse
import os
from pathlib import Path
import socket
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    for name in list(os.environ):
        if any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            os.environ.pop(name, None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_only(address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1" or address[1] != panel.port:
            raise OSError("Verification blocks outbound connections")

    def connect(connection, address):
        local_only(address)
        return original_connect(connection, address)

    def connect_ex(connection, address):
        local_only(address)
        return original_connect_ex(connection, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    from flask import jsonify, request
    from dashboard_verification_loader import load_dashboard
    ui = load_dashboard()

    with tempfile.TemporaryDirectory(prefix="elysia-fictional-ui-") as directory:
        root = Path(directory)
        for name in (
            "BROWSER_AGENT_STATE_PATH", "OPENCLAW_ACTIVITY_PATH",
            "CURRENT_BACKEND_LOG_PATH", "SECONDARY_RUNTIME_LOG_PATH",
            "LEGACY_AUTONOMOUS_LOG_PATH", "CONTROL_PANEL_CHAT_HISTORY_PATH",
        ):
            setattr(ui, name, root / name)
        ui._is_tcp_endpoint_reachable = lambda *args, **kwargs: False
        panel = ui.UIControlPanel(None, host="127.0.0.1", port=args.port)
        if hasattr(ui, "ConversationStore"):
            panel._conversation_store = ui.ConversationStore(root / "conversations")
        allowed = {"/", "/api/ping", "/api/status", "/favicon.ico"}

        @panel.app.before_request
        def read_only_verification():
            if request.method != "GET" or request.path not in allowed:
                return jsonify(success=False, error="Disabled in fictional verification"), 403

        @panel.app.after_request
        def block_external_browser_requests(response):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
            )
            return response

        try:
            panel.start(source="fictional-windows-verification")
            deadline = time.monotonic() + 10
            while not panel.is_ready() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not panel.is_ready():
                raise RuntimeError("Dashboard never returned its own HTTP ping")
            print(f"FICTIONAL_READ_ONLY_READY http://127.0.0.1:{panel.port}", flush=True)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            panel.stop()


if __name__ == "__main__":
    main()
