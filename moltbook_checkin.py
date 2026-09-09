#!/usr/bin/env python3
"""Run Elysia's authenticated Moltbook heartbeat check-in."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_guardian.moltbook_client import MoltbookAPIError, MoltbookClient, next_actions_text

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Moltbook /home and update heartbeat state.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--no-state", action="store_true", help="Do not update memory/heartbeat-state.json.")
    parser.add_argument("--credentials", type=Path, help="Path to Moltbook credentials JSON.")
    parser.add_argument("--state", type=Path, help="Path to heartbeat state JSON.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = MoltbookClient(
            credentials_path=args.credentials,
            state_path=args.state,
            timeout=args.timeout,
        )
        result = client.check_home(update_state=not args.no_state)
    except MoltbookAPIError as exc:
        payload = {
            "success": False,
            "status_code": exc.status_code,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            print(f"Moltbook check-in failed: {exc}")
            if exc.status_code:
                print(f"HTTP status: {exc.status_code}")
        return 1

    summary = result["summary"]
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    print("Moltbook check-in complete")
    print(f"Agent: {summary.get('agent_name') or '(unknown)'}")
    print(f"Karma: {summary.get('karma', 0)}")
    print(f"Unread notifications: {summary.get('unread_notifications', 0)}")
    print(f"DMs: {summary.get('dm_unread_messages', 0)} unread, {summary.get('dm_pending_requests', 0)} pending request(s)")
    print(f"Following feed posts shown: {summary.get('followed_posts_count', 0)}")
    announcement = summary.get("latest_announcement_title")
    if announcement:
        print(f"Latest announcement: {announcement}")
    actions = next_actions_text(summary.get("what_to_do_next") or [])
    if actions:
        print("\nWhat to do next:")
        print(actions)
    if result.get("state_updated"):
        print(f"\nHeartbeat state updated: {result.get('state_path')}")
        print(f"lastMoltbookCheck: {result.get('lastMoltbookCheck')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
