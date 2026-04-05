"""Command-line interface for the unified Elysia runtime."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from .config import RuntimeConfig, load_runtime_config
from .runtime import ElysiaRuntime


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="elysia", description="Unified Elysia runtime controller"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Start the runtime")
    run_p.add_argument("--mode", default="all", choices=["all", "core", "agents"])
    run_p.add_argument("--env", default="dev", choices=["dev", "prod"])
    run_p.add_argument("--no-api", action="store_true", help="Disable REST API server")
    run_p.add_argument(
        "--no-webscout", action="store_true", help="Skip WebScout initialization"
    )
    run_p.add_argument(
        "--require-api-keys",
        action="store_true",
        help="Fail if API keys are missing (WebScout)",
    )
    run_p.add_argument(
        "--log-level", default=None, help="Override log level (INFO, DEBUG, ...)"
    )
    run_p.add_argument(
        "--api-port", type=int, default=None, help="Override API port (default 8123)"
    )

    status_p = sub.add_parser("status", help="Fetch status from the running runtime")
    status_p.add_argument("--host", default="127.0.0.1")
    status_p.add_argument("--port", type=int, default=8123)

    shell_p = sub.add_parser("shell", help="Interactive shell over the REST API")
    shell_p.add_argument("--host", default="127.0.0.1")
    shell_p.add_argument("--port", type=int, default=8123)

    tail_p = sub.add_parser("tail-events", help="Stream recent events once")
    tail_p.add_argument("--host", default="127.0.0.1")
    tail_p.add_argument("--port", type=int, default=8123)
    tail_p.add_argument("--limit", type=int, default=25)

    args = parser.parse_args(argv)

    if args.command == "run":
        overrides = {
            "enable_api": not args.no_api,
            "enable_webscout": not args.no_webscout,
            "require_api_keys": args.require_api_keys,
        }
        if args.log_level:
            overrides["log_level"] = args.log_level
        if args.api_port:
            overrides["api_port"] = args.api_port

        cfg = load_runtime_config(mode=args.mode, env=args.env, overrides=overrides)
        runtime = ElysiaRuntime(cfg)
        runtime.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            runtime.stop()
        return

    if args.command == "status":
        from .status import print_status
        print_status(args.host, args.port)
        return

    if args.command == "tail-events":
        params = f"?limit={args.limit}"
        data = _fetch_json(args.host, args.port, f"/api/events{params}")
        if data is None:
            print("Event endpoint not reachable.", file=sys.stderr)
            sys.exit(1)
        events = data.get("events", [])
        for evt in events:
            print(f"{evt['ts']} [{evt['source']}] {evt['type']} {evt['payload']}")
        return

    if args.command == "shell":
        from .shell import interactive_shell
        interactive_shell(args.host, args.port)
        return


def _fetch_json(host: str, port: int, path: str) -> dict | None:
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"[error] {exc}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover
        print(f"[error] {exc}", file=sys.stderr)
    return None



