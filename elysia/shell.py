"""Interactive shell for Elysia runtime."""

from __future__ import annotations

import json
import sys
import urllib.error
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
            payload = json.dumps({"approver": "shell_user"}).encode("utf-8")
            url = f"http://{host}:{port}/api/proposals/{proposal_id}/approve"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    reply = json.loads(resp.read().decode("utf-8"))
                    print(json.dumps(reply, indent=2))
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)
            continue
        if line.startswith("reject "):
            parts = line[7:].strip().split(" ", 1)
            proposal_id = parts[0]
            reason = parts[1] if len(parts) > 1 else "No reason provided"
            payload = json.dumps({"rejector": "shell_user", "reason": reason}).encode("utf-8")
            url = f"http://{host}:{port}/api/proposals/{proposal_id}/reject"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    reply = json.loads(resp.read().decode("utf-8"))
                    print(json.dumps(reply, indent=2))
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)
            continue

        print("Unknown command. Type 'help' for available commands.")


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

