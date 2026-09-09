#!/usr/bin/env python3
"""
Print the deliberate-practice replay pack (prompts + checklist).

Does not call the LLM; use each line in your normal Elysia chat, then note meta[\"selfbuild_rag\"]
or run: python scripts/elysia_selfbuild_operator.py last-rag

Usage:
  python scripts/run_replay_prompts.py
  python scripts/run_replay_prompts.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK = PROJECT_ROOT / "proposals" / "elysia-acceleration" / "replay_prompts.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="Emit raw JSONL to stdout")
    args = ap.parse_args()
    if not PACK.is_file():
        print(f"Missing replay pack: {PACK}", file=sys.stderr)
        return 1
    raw = PACK.read_text(encoding="utf-8")
    if args.json:
        sys.stdout.write(raw)
        if not raw.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    print("=== Elysia replay pack (run weekly; log selfbuild_rag meta per turn) ===\n")
    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(f"{i}. [parse error] {line[:80]}")
            continue
        cid = row.get("id", i)
        cat = row.get("category", "")
        text = (row.get("text") or "").strip()
        print(f"--- {cid} [{cat}] ---\n{text}\n")
    print("After each run, append one line to proposals/elysia-acceleration/replay_runs.md (optional).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
