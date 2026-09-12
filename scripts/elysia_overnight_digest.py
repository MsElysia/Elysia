#!/usr/bin/env python3
"""
Scan Elysia log files for errors/warnings/tracebacks and write a digest file.

Run after an overnight session (or any time):
  python scripts/elysia_overnight_digest.py
  python scripts/elysia_overnight_digest.py --hours 8
  python scripts/elysia_overnight_digest.py --log path/to/custom.log

Output: data/runtime/elysia_digest_<timestamp>.txt

This does not watch the process live; it summarizes what already landed in logs.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
DEFAULT_LOGS = [
    PROJECT_ROOT / "elysia_unified.log",
    PROJECT_ROOT / "organized_project" / "data" / "logs" / "unified_autonomous_system.log",
]

# Rough timestamp prefix like "2025-04-28 01:23:45" or ISO
_TS_PREFIX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}|"
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
)


def _parse_line_ts(line: str) -> datetime | None:
    m = _TS_PREFIX.match(line.strip())
    if not m:
        return None
    raw = m.group(1).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _interest(line: str) -> str | None:
    lo = line.lower()
    if "traceback" in lo:
        return "traceback"
    if "error" in lo or "exception" in lo or "critical" in lo:
        if any(x in lo for x in ("error", "exception", "critical")):
            return "error"
    if "warning" in lo or "warn " in lo:
        return "warning"
    return None


def _normalize_snippet(line: str, max_len: int = 200) -> str:
    s = line.strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def digest_file(
    path: Path,
    since: datetime | None,
    *,
    max_traceback_lines: int = 40,
) -> tuple[list[str], Counter[str]]:
    """Returns (interesting_raw_lines_for_context, kind_counts)."""
    if not path.is_file():
        return [], Counter()

    kinds: Counter[str] = Counter()
    bucket: list[str] = []
    in_tb = False
    tb_buf: list[str] = []

    def flush_tb() -> None:
        nonlocal tb_buf, in_tb
        if tb_buf:
            bucket.append("\n".join(tb_buf))
            kinds["traceback"] += 1
        tb_buf = []
        in_tb = False

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], Counter()

    for line in text.splitlines():
        if since:
            ts = _parse_line_ts(line)
            if ts and ts < since:
                if in_tb:
                    flush_tb()
                continue

        lo = line.lower()
        if "traceback (most recent call last)" in lo or (in_tb and line.startswith(" ")):
            in_tb = True
            tb_buf.append(line.rstrip())
            if len(tb_buf) >= max_traceback_lines:
                flush_tb()
            continue
        if in_tb and lo.strip() and not line.startswith(" "):
            flush_tb()

        kind = _interest(line)
        if kind:
            kinds[kind] += 1
            bucket.append(line.rstrip())

    if in_tb:
        flush_tb()

    return bucket, kinds


def main() -> int:
    ap = argparse.ArgumentParser(description="Digest Elysia logs into data/runtime/*.txt")
    ap.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Only include lines whose timestamp is within this many hours from now (UTC). "
        "If no timestamp on a line, the line is kept when --hours is not set; when set, "
        "unparseable lines are skipped.",
    )
    ap.add_argument("--log", action="append", default=[], help="Extra log file (repeatable)")
    args = ap.parse_args()

    since: datetime | None = None
    if args.hours is not None:
        since = datetime.now(timezone.utc) - timedelta(hours=float(args.hours))

    paths = [p for p in DEFAULT_LOGS + [Path(x) for x in args.log] if p]

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RUNTIME_DIR / f"elysia_digest_{stamp}.txt"

    lines_out: list[str] = [
        "Elysia overnight / session log digest",
        f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Window: {'last ' + str(args.hours) + ' hours' if args.hours else 'entire files (no time filter)'}",
        "",
    ]

    total_kinds: Counter[str] = Counter()
    snippets_for_dedupe: Counter[str] = Counter()

    for path in paths:
        if not path.is_file():
            lines_out.append(f"--- skip (missing): {path}")
            lines_out.append("")
            continue
        raw, kinds = digest_file(path, since)
        total_kinds.update(kinds)
        lines_out.append(f"=== {path} ===")
        lines_out.append(f"Counts: {dict(kinds)}")
        if not raw:
            lines_out.append("(no matching lines)")
            lines_out.append("")
            continue
        for block in raw:
            key = _normalize_snippet(block.split("\n")[0], 160)
            snippets_for_dedupe[key] += 1
            lines_out.append(block)
            lines_out.append("-" * 40)

    lines_out.insert(4, f"Aggregate counts: {dict(total_kinds)}")
    lines_out.insert(5, "")
    if snippets_for_dedupe:
        lines_out.append("")
        lines_out.append("=== Top repeated first-lines (hint: fix noisy repeats) ===")
        for line, n in snippets_for_dedupe.most_common(25):
            lines_out.append(f"  [{n}x] {line}")

    out_path.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
