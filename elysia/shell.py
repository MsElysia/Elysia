"""Interactive shell for Elysia runtime."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


def interactive_shell(host: str = "127.0.0.1", port: int = 8123) -> None:
    """Run an interactive shell that connects to the Elysia runtime API."""
    print("Elysia shell – type 'help' for commands, 'exit' to quit.")
    while True:
        try:
            line = input("elysia> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in {"exit", "quit"}:
            break
        if line == "help":
            print("commands: status, events, proposals, chat <message>, approve <id>, reject <id> <reason>, exit")
            continue
        if line == "status":
            data = _fetch_json(host, port, "/api/status")
            print(json.dumps(data or {}, indent=2))
            continue
        if line == "events":
            data = _fetch_json(host, port, "/api/events?limit=10")
            events = (data or {}).get("events", [])
            for evt in events:
                print(f"{evt['ts']} [{evt['source']}] {evt['type']} {evt['payload']}")
            continue
        if line == "proposals":
            data = _fetch_json(host, port, "/api/proposals")
            proposals = (data or {}).get("proposals", [])
            for prop in proposals[:10]:  # Show first 10
                print(f"{prop.get('proposal_id', 'unknown')}: {prop.get('title', 'No title')} [{prop.get('status', 'unknown')}]")
            continue
        if line.startswith("chat "):
            message = line[5:].strip()
            payload = json.dumps({"message": message}).encode("utf-8")
            url = f"http://{host}:{port}/api/chat"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    reply = json.loads(resp.read().decode("utf-8"))
                    print(reply.get("response", json.dumps(reply, indent=2)))
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)
            continue
        if line.startswith("approve "):
            proposal_id = line[8:].strip()
            if not proposal_id:
                print("[error] proposal id is required", file=sys.stderr)
                continue
            post_json(
                host,
                port,
                f"/api/proposals/{urllib.parse.quote(proposal_id, safe='')}/approve",
                {"approver": "shell_user"},
            )
            continue
        if line.startswith("reject "):
            parts = line[7:].strip().split(" ", 1)
            proposal_id = parts[0] if parts and parts[0] else ""
            if not proposal_id:
                print("[error] proposal id is required", file=sys.stderr)
                continue
            reason = parts[1] if len(parts) > 1 else "No reason provided"
            post_json(
                host,
                port,
                f"/api/proposals/{urllib.parse.quote(proposal_id, safe='')}/reject",
                {"rejector": "shell_user", "reason": reason},
            )
            continue

        print("Unknown command. Type 'help' for available commands.")


def post_json(host: str, port: int, path: str, payload: dict) -> int:
    """POST JSON and print the stored result, or the API error text."""
    data = json.dumps(payload).encode("utf-8")
    url = f"http://{host}:{port}{path}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 0

    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[error] HTTP {status}: {raw}", file=sys.stderr)
        return status

    if not isinstance(body, dict):
        print(f"[error] HTTP {status}: {raw}", file=sys.stderr)
        return status

    if status != 200:
        print(f"[error] HTTP {status}: {body.get('error') or raw}", file=sys.stderr)
        return status

    warning = body.get("warning")
    if isinstance(warning, str) and warning:
        print(f"[warning] {warning}", file=sys.stderr)
    print(json.dumps(body, indent=2))
    return status


def _fetch_json(host: str, port: int, path: str) -> Optional[dict]:
    """Fetch JSON from the API."""
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"[error] {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
    return None

