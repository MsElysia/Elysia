#!/usr/bin/env python3
"""
Operator helpers for local_ai_selfbuild (status, backup, recent RAG log lines).

Usage (from repo root):
  python scripts/elysia_selfbuild_operator.py status
  python scripts/elysia_selfbuild_operator.py backup
  python scripts/elysia_selfbuild_operator.py backup --dest D:\\backups\\elysia_selfbuild.zip
  python scripts/elysia_selfbuild_operator.py last-rag
  python scripts/elysia_selfbuild_operator.py config-snapshot
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KiB"
    return f"{n / 1024**2:.1f} MiB"


def _mtime_iso(p: Path) -> str:
    try:
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    except OSError:
        return "—"


def _candidate_unified_logs() -> List[Path]:
    out: List[Path] = []
    root = PROJECT_ROOT
    out.append(root / "elysia_unified.log")
    for i in range(1, 6):
        out.append(root / f"elysia_unified.log.{i}")
    try:
        from project_guardian.external_storage import get_configured_external_data_dir

        ext = get_configured_external_data_dir()
        if ext:
            out.append(ext / "logs" / "elysia_unified.log")
            for i in range(1, 4):
                out.append(ext / "logs" / f"elysia_unified.log.{i}")
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
    uniq: List[Path] = []
    for p in out:
        k = str(p.resolve()) if p.exists() else str(p)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def cmd_status() -> int:
    from project_guardian.auto_learning import get_learned_storage_path, load_learning_config

    learned = get_learned_storage_path()
    sb = learned / "local_ai_selfbuild"
    cfg = load_learning_config()

    print("=== Elysia self-build operator: status ===\n")
    print(f"learned storage: {learned}")
    print(f"self-build dir:  {sb}  (exists={sb.is_dir()})\n")

    keys = [
        "enabled",
        "interval_hours",
        "local_ai_selfbuild_enabled",
        "local_ai_selfbuild_rag_export_enabled",
        "local_ai_selfbuild_rag_export_each_run",
        "local_ai_selfbuild_embed_enabled",
        "local_ai_selfbuild_embed_each_run",
        "local_ai_selfbuild_rag_inject_enabled",
        "local_ai_selfbuild_rag_inject_min_score",
        "local_ai_selfbuild_rag_inject_top_k",
        "local_ai_selfbuild_embed_model",
    ]
    print("auto_learning.json (subset):")
    for k in keys:
        if k in cfg:
            print(f"  {k}: {cfg.get(k)}")
    print()

    files = [
        ("rag_chunks_latest.jsonl", sb / "rag_chunks_latest.jsonl"),
        ("chunk_embeddings_index.jsonl", sb / "chunk_embeddings_index.jsonl"),
        ("chunk_embeddings.f32.bin", sb / "chunk_embeddings.f32.bin"),
    ]
    for label, p in files:
        if p.is_file():
            print(f"{label}: {_fmt_size(p.stat().st_size)}  mtime={_mtime_iso(p)}")
        else:
            print(f"{label}: MISSING ({p})")

    print("\nLog files to grep for [UnifiedLLM] selfbuild_rag:")
    for p in _candidate_unified_logs():
        mark = "yes" if p.is_file() else "no"
        print(f"  [{mark}] {p}")
    return 0


def cmd_config_snapshot() -> int:
    from project_guardian.auto_learning import load_learning_config

    cfg = load_learning_config()
    snap = {k: cfg.get(k) for k in sorted(cfg) if "local_ai_selfbuild" in k or k in ("enabled", "interval_hours")}
    print(json.dumps(snap, indent=2, default=str))
    return 0


def cmd_backup(dest: Optional[Path]) -> int:
    from project_guardian.auto_learning import get_learned_storage_path

    learned = get_learned_storage_path()
    sb = learned / "local_ai_selfbuild"
    if not sb.is_dir():
        print(f"No directory to backup: {sb}", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if dest is None:
        base = Path(os.environ.get("LOCALAPPDATA", str(PROJECT_ROOT))) / "ProjectGuardian" / "selfbuild_operator_backups"
        base.mkdir(parents=True, exist_ok=True)
        dest = base / f"local_ai_selfbuild_{stamp}.zip"
    else:
        dest = dest.expanduser()
        if dest.suffix.lower() != ".zip":
            dest = dest / f"local_ai_selfbuild_{stamp}.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(sb.rglob("*")):
            if fp.is_file():
                arc = fp.relative_to(sb)
                zf.write(fp, arcname=str(arc))
    print(f"Wrote {dest} ({_fmt_size(dest.stat().st_size)})")
    return 0


def _tail_matching_lines(path: Path, needle: str, max_bytes: int = 400_000, max_hits: int = 12) -> List[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="ignore")
    hits = [ln for ln in text.splitlines() if needle in ln]
    return hits[-max_hits:]


def cmd_last_rag() -> int:
    needle = "selfbuild_rag"
    found_any = False
    for p in _candidate_unified_logs():
        if not p.is_file():
            continue
        lines = _tail_matching_lines(p, needle)
        if not lines:
            continue
        found_any = True
        print(f"=== {p} (last {len(lines)} matching lines) ===\n")
        for ln in lines:
            print(ln)
        print()
    if not found_any:
        print("No log file contained recent lines matching 'selfbuild_rag'.")
        print("Start Elysia with file logging, or check path in elysia_config.LOG_FILE / external mirror.")
        return 1
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Elysia local_ai_selfbuild operator helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show learned path, artifact mtimes, key auto_learning flags, log paths")
    sub.add_parser("config-snapshot", help="Print JSON snapshot of self-build-related auto_learning keys")
    p_bak = sub.add_parser("backup", help="Zip local_ai_selfbuild under learned storage")
    p_bak.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Output .zip path or parent directory (default: %%LOCALAPPDATA%%\\ProjectGuardian\\selfbuild_operator_backups\\)",
    )
    sub.add_parser("last-rag", help="Print last UnifiedLLM selfbuild_rag lines from elysia_unified.log (tail scan)")

    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "config-snapshot":
        return cmd_config_snapshot()
    if args.cmd == "backup":
        return cmd_backup(args.dest)
    if args.cmd == "last-rag":
        return cmd_last_rag()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
