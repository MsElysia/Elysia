#!/usr/bin/env python3
"""
Pilot .txt/.md inbox → MemoryCore import (startup / manual scan only).

Not a folder watcher and not a browser upload/DnD feature.

Reuses local-ingestion safety patterns (extension gate, binary reject, SHA-256
dedupe, source files never modified). Does not enable providers/autonomy.

Writes:
  - MemoryCore entries in the pilot data-root memory file (category inbox_import)
  - Append-only import_manifest.jsonl under inbox_state (provenance / dedupe)

Deduplication: normalized-text SHA-256 via manifest and in-memory source_sha256 /
identical thought+source check. Rescan of the same file is a no-op duplicate.

Concurrent MemoryCore access: MemoryCore locks are in-process only. This scanner
refuses apply while a verified live pilot instance is running (except the launch
path, which scans before spawning the UI). Operators should run SCAN_INBOX.bat
only when the pilot is stopped, or rely on startup scan.

Recovery: re-running the scan after interrupt is safe — duplicates are skipped;
source files are never moved or deleted.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_identity import read_delivery_identity
from pilot_paths import (
    APPLICATION_BASE_SHA,
    INBOX_DIR,
    INBOX_MANIFEST,
    INBOX_STATE_DIR,
    INBOX_SUPPORTED_EXTENSIONS,
    PID_FILE,
    PILOT_DATA_ROOT,
    PILOT_SOURCE_ROOT,
    RUNTIME_JSON,
)

DEFAULT_MAX_FILE_MB = 5.0


def _looks_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    non_text = sum(1 for b in sample if b < 9 or (13 < b < 32 and b != 27))
    return (non_text / len(sample)) > 0.30


def _decode_text(raw: bytes) -> Optional[str]:
    if _looks_binary(raw):
        return None
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_known_hashes(manifest_path: Path) -> Set[str]:
    hashes: Set[str] = set()
    if not manifest_path.is_file():
        return hashes
    try:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            digest = str(record.get("sha256") or "").strip()
            if digest and record.get("status") == "imported":
                hashes.add(digest)
    except OSError:
        pass
    return hashes


def _append_manifest(manifest_path: Path, record: Dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def ensure_inbox_dirs() -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_STATE_DIR.mkdir(parents=True, exist_ok=True)
    readme = INBOX_DIR / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Elysia Verified Pilot inbox\n"
            "Drop .txt or .md files here, then run SCAN_INBOX.bat or start the pilot.\n"
            "This is startup/manual scanning only (not a watcher).\n"
            "Unsupported types are rejected with a clear error. Source files are not moved.\n"
            "Prefer scanning while the pilot UI is stopped to avoid concurrent memory writes.\n",
            encoding="utf-8",
        )
    return INBOX_DIR


def _verified_pilot_running() -> bool:
    """True only when PID+runtime identify a live owned pilot (same bar as launch)."""
    if not PID_FILE.is_file() or not RUNTIME_JSON.is_file():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        runtime = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        return False
    if not isinstance(runtime, dict):
        return False
    from pilot_identity import verify_live_ownership

    return bool(verify_live_ownership(pid, runtime).owned)


def scan_inbox_to_memory(
    *,
    apply: bool = True,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
    allow_while_pilot_running: bool = False,
) -> Dict[str, Any]:
    """
    Scan top-level inbox files into the pilot MemoryCore store.

    apply=False: dry-run report only (no memory/manifest writes).
    allow_while_pilot_running: launch path may set True only before UI spawn;
      manual SCAN should leave False (default) to avoid cross-process MemoryCore races.
    """
    ensure_inbox_dirs()
    delivery = read_delivery_identity()
    max_bytes = int(max_file_mb * 1024 * 1024)
    known = _read_known_hashes(INBOX_MANIFEST) if apply else set()

    report: Dict[str, Any] = {
        "ok": True,
        "application_base_sha": APPLICATION_BASE_SHA,
        "delivery_commit": delivery.get("delivery_commit"),
        "delivery_status": delivery.get("delivery_status"),
        "exact_verified_delivery": bool(delivery.get("exact_verified_delivery")),
        "inbox_dir": str(INBOX_DIR),
        "memory_filepath": str(PILOT_DATA_ROOT / "memory" / "guardian_memory.json"),
        "supported_extensions": sorted(INBOX_SUPPORTED_EXTENSIONS),
        "scan_mode": "startup_or_manual",
        "apply": apply,
        "scanned": 0,
        "imported": 0,
        "duplicates": 0,
        "rejected": 0,
        "errors": [],
        "results": [],
    }

    if apply and not allow_while_pilot_running and _verified_pilot_running():
        report["ok"] = False
        report["errors"].append(
            "REFUSING inbox apply while a verified pilot instance is running "
            "(MemoryCore has no cross-process file lock). Stop the pilot or rely on "
            "startup scan before UI spawn."
        )
        return report

    memory = None
    if apply:
        if str(PILOT_SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(PILOT_SOURCE_ROOT))
        from project_guardian.memory import MemoryCore

        mem_path = PILOT_DATA_ROOT / "memory" / "guardian_memory.json"
        mem_path.parent.mkdir(parents=True, exist_ok=True)
        if not mem_path.exists():
            mem_path.write_text("[]", encoding="utf-8")
        memory = MemoryCore(
            filepath=str(mem_path),
            timeline_memory=None,
            enable_timeline_logging=False,
            enable_vector_search=False,
        )

    for entry in sorted(INBOX_DIR.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith(".") or entry.name.upper() == "README.TXT":
            continue
        report["scanned"] += 1
        ext = entry.suffix.lower()
        result: Dict[str, Any] = {
            "filename": entry.name,
            "path": str(entry.resolve()),
            "extension": ext,
        }

        if ext not in INBOX_SUPPORTED_EXTENSIONS:
            result["status"] = "unsupported"
            result["error"] = (
                f"Unsupported file type {ext or '(none)'}. "
                f"Supported: {', '.join(sorted(INBOX_SUPPORTED_EXTENSIONS))}"
            )
            report["rejected"] += 1
            report["errors"].append(result["error"] + f" ({entry.name})")
            report["results"].append(result)
            continue

        try:
            size = entry.stat().st_size
        except OSError as exc:
            result["status"] = "error"
            result["error"] = f"stat failed: {exc}"
            report["rejected"] += 1
            report["errors"].append(result["error"])
            report["results"].append(result)
            continue

        if size > max_bytes:
            result["status"] = "unsupported"
            result["error"] = f"File exceeds {max_file_mb} MB limit ({size} bytes)"
            report["rejected"] += 1
            report["errors"].append(result["error"] + f" ({entry.name})")
            report["results"].append(result)
            continue

        try:
            raw = entry.read_bytes()
        except OSError as exc:
            result["status"] = "error"
            result["error"] = f"read failed: {exc}"
            report["rejected"] += 1
            report["errors"].append(result["error"])
            report["results"].append(result)
            continue

        text = _decode_text(raw)
        if text is None:
            result["status"] = "unsupported"
            result["error"] = "File looks binary; only UTF text .txt/.md are accepted"
            report["rejected"] += 1
            report["errors"].append(result["error"] + f" ({entry.name})")
            report["results"].append(result)
            continue

        normalized = _normalize_text(text)
        if len(normalized) < 12:
            result["status"] = "unsupported"
            result["error"] = "Content too short after normalize (min 12 characters)"
            report["rejected"] += 1
            report["errors"].append(result["error"] + f" ({entry.name})")
            report["results"].append(result)
            continue

        digest = _sha256_text(normalized)
        result["sha256"] = digest

        if digest in known:
            result["status"] = "duplicate"
            report["duplicates"] += 1
            report["results"].append(result)
            continue

        if memory is not None:
            memory.load_if_needed()
            already = False
            for mem in memory.memory_log:
                meta = mem.get("metadata") or {}
                if meta.get("source_sha256") == digest:
                    already = True
                    break
                if (mem.get("thought") or "") == normalized and meta.get("source") == "pilot_inbox":
                    already = True
                    break
            if already:
                result["status"] = "duplicate"
                report["duplicates"] += 1
                report["results"].append(result)
                if apply:
                    _append_manifest(
                        INBOX_MANIFEST,
                        {
                            "status": "imported",
                            "sha256": digest,
                            "filename": entry.name,
                            "note": "already_in_memory",
                            "imported_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    known.add(digest)
                continue

        if not apply:
            result["status"] = "would_import"
            report["imported"] += 1
            report["results"].append(result)
            continue

        assert memory is not None
        metadata = {
            "source": "pilot_inbox",
            "source_path": str(entry.resolve()),
            "source_filename": entry.name,
            "source_sha256": digest,
            "source_extension": ext,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "application_base_sha": APPLICATION_BASE_SHA,
            "delivery_commit": delivery.get("delivery_commit"),
            "scan_mode": "startup_or_manual",
        }
        memory.remember(
            thought=normalized,
            category="inbox_import",
            priority=0.75,
            metadata=metadata,
        )
        _append_manifest(
            INBOX_MANIFEST,
            {
                "status": "imported",
                "sha256": digest,
                "filename": entry.name,
                "source_path": str(entry.resolve()),
                "imported_at": metadata["imported_at"],
                "application_base_sha": APPLICATION_BASE_SHA,
                "delivery_commit": delivery.get("delivery_commit"),
            },
        )
        known.add(digest)
        result["status"] = "imported"
        report["imported"] += 1
        report["results"].append(result)

    report["ok"] = report["ok"] and not (
        report["rejected"] > 0 and report["imported"] == 0 and report["duplicates"] == 0
        and any("REFUSING" in e for e in report["errors"])
    )
    # ok stays True for partial rejects of unsupported files alongside successful work
    if any(e.startswith("REFUSING") for e in report["errors"]):
        report["ok"] = False
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Startup/manual scan of pilot inbox (.txt/.md) into MemoryCore"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    report = scan_inbox_to_memory(apply=not args.dry_run, allow_while_pilot_running=False)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Inbox: {report['inbox_dir']}")
        print(f"Supported: {', '.join(report['supported_extensions'])}")
        print(f"scan_mode={report['scan_mode']}")
        print(
            f"scanned={report['scanned']} imported={report['imported']} "
            f"duplicates={report['duplicates']} rejected={report['rejected']}"
        )
        for item in report["results"]:
            line = f"  [{item.get('status')}] {item.get('filename')}"
            if item.get("error"):
                line += f" — {item['error']}"
            print(line)
        if report["errors"]:
            print("Errors:")
            for err in report["errors"]:
                print(f"  ! {err}")

    if any(str(e).startswith("REFUSING") for e in report.get("errors") or []):
        return 3
    if report["rejected"] > 0 and report["imported"] == 0 and report["duplicates"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
