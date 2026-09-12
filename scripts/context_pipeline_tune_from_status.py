#!/usr/bin/env python3
"""
Read context-pipeline telemetry from a running control panel (/api/status) and
suggest (or optionally apply) conservative config tweaks to config/context_pipeline.json.

Usage:
  python scripts/context_pipeline_tune_from_status.py
  python scripts/context_pipeline_tune_from_status.py --url http://127.0.0.1:8888/api/status
  python scripts/context_pipeline_tune_from_status.py --apply --dry-run
  python scripts/context_pipeline_tune_from_status.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Allow `python scripts/context_pipeline_tune_from_status.py` without PYTHONPATH
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from project_guardian.context_pipeline.telemetry_tuning import (  # noqa: E402
    recommend_context_pipeline_patch,
)


def _repo_root() -> Path:
    return _ROOT


def _default_config_path() -> Path:
    return _repo_root() / "config" / "context_pipeline.json"


def fetch_status(url: str, timeout_sec: float = 8.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def extract_pipeline_runtime(data: Dict[str, Any]) -> Dict[str, Any]:
    sys_block = data.get("system") if isinstance(data.get("system"), dict) else {}
    cp = sys_block.get("context_pipeline_runtime_status")
    return cp if isinstance(cp, dict) else {}


def apply_patch(config_path: Path, patch: Dict[str, Any], *, dry_run: bool) -> None:
    if not patch:
        print("Nothing to apply.")
        return
    if not config_path.is_file():
        raise SystemExit(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit("context_pipeline.json must be a JSON object")
    merged = {**data, **patch}
    if dry_run:
        print("--dry-run: would write:", json.dumps(patch, indent=2, ensure_ascii=False))
        return
    bak = config_path.with_suffix(
        config_path.suffix + ".bak." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    shutil.copy2(config_path, bak)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {config_path} (backup {bak})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tune context_pipeline.json from /api/status telemetry.")
    ap.add_argument(
        "--url",
        default="http://127.0.0.1:8888/api/status",
        help="Status JSON URL (default: local control panel)",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to context_pipeline.json (default: repo config/)",
    )
    ap.add_argument("--apply", action="store_true", help="Merge recommended patch into config file")
    ap.add_argument("--dry-run", action="store_true", help="With --apply, print patch only")
    ap.add_argument("--min-cycles", type=int, default=8, help="Minimum cycles before recommending changes")
    args = ap.parse_args()

    cfg_path = args.config or _default_config_path()
    try:
        status = fetch_status(args.url)
    except urllib.error.URLError as e:
        print(f"Could not fetch {args.url}: {e}", file=sys.stderr)
        print(
            "Start the backend (e.g. START_ELYSIA_UNIFIED.bat) and ensure the UI port matches --url.",
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from {args.url}: {e}", file=sys.stderr)
        return 2

    cp = extract_pipeline_runtime(status)
    if not cp:
        print("context_pipeline_runtime_status missing or empty in response.system.")
        print("Keys at top level:", list(status.keys()))
        return 1

    if not cfg_path.is_file():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        return 2
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        print("Config must be a JSON object", file=sys.stderr)
        return 2

    notes, patch = recommend_context_pipeline_patch(cp, cfg, min_cycles=args.min_cycles)
    for line in notes:
        print(line)
    if patch:
        print("\nProposed patch:")
        print(json.dumps(patch, indent=2, ensure_ascii=False))
    if args.apply or args.dry_run:
        apply_patch(cfg_path, patch, dry_run=args.dry_run or not args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
