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
from typing import Any, Dict, List, Optional, Set, Tuple  # Any used for exclusion_hold

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
    """Strict UTF-8 (BOM optional). Malformed sequences are rejected — no latin-1 fallback."""
    if _looks_binary(raw):
        return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


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


def ensure_inbox_dirs() -> Tuple[Path, str]:
    """
    Ensure inbox/state dirs. Refuses to create README through a reparse-point root.
    Returns (inbox_dir, inbox_final_path_or_error_prefix).
    """
    from pilot_fs import assert_physical_inbox_root

    INBOX_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not INBOX_DIR.exists():
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ok, detail = assert_physical_inbox_root(INBOX_DIR)
    if not ok:
        return INBOX_DIR, f"REFUSING:{detail}"
    readme = INBOX_DIR / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Elysia Verified Pilot inbox\n"
            "Drop .txt or .md files here, then run SCAN_INBOX.bat or start the pilot.\n"
            "This is startup/manual scanning only (not a watcher).\n"
            "Unsupported types are rejected with a clear error. Source files are not moved.\n"
            "UTF-8 text only. Prefer scanning while the pilot UI is stopped.\n",
            encoding="utf-8",
        )
    return INBOX_DIR, detail


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
    exclusion_hold: Any = None,
) -> Dict[str, Any]:
    """
    Scan top-level inbox files into the pilot MemoryCore store.

    apply=False: dry-run report only (no memory/manifest writes).
    exclusion_hold: optional already-acquired pilot exclusion mutex from launch.
    allow_while_pilot_running: legacy flag; ignored when exclusion_hold is provided.
      Manual SCAN must establish exclusion (fail closed if uncertain).
    """
    inbox_path, inbox_final = ensure_inbox_dirs()
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

    if isinstance(inbox_final, str) and inbox_final.startswith("REFUSING:"):
        report["ok"] = False
        report["errors"].append(
            f"REFUSING inbox apply: inbox root failed containment ({inbox_final[9:]})"
        )
        return report

    owned_exclusion = False
    if apply and exclusion_hold is None:
        from pilot_exclusion import writer_exclusion_status
        from pilot_identity import expected_entry_path

        excl = writer_exclusion_status(entry=expected_entry_path(), data_root=PILOT_DATA_ROOT)
        if not excl.get("safe_to_write"):
            report["ok"] = False
            report["errors"].append(
                "REFUSING inbox apply: cannot establish exclusive writer ownership "
                f"({excl.get('reason')})."
            )
            return report
        exclusion_hold = excl.get("hold")
        owned_exclusion = True

    from pilot_fs import ImportFileLock

    file_lock = ImportFileLock(INBOX_STATE_DIR / "import.lock")
    if apply:
        ok_lock, lock_reason = file_lock.acquire(blocking=True)
        if not ok_lock:
            report["ok"] = False
            report["errors"].append(f"REFUSING inbox apply: {lock_reason}")
            if owned_exclusion and exclusion_hold is not None:
                try:
                    exclusion_hold.release()
                except Exception:
                    pass
            return report

    try:
        return _scan_inbox_body(
            report=report,
            apply=apply,
            max_bytes=max_bytes,
            known=known,
            delivery=delivery,
            inbox_final=str(inbox_final),
        )
    finally:
        if apply:
            file_lock.release()
        if owned_exclusion and exclusion_hold is not None:
            try:
                exclusion_hold.release()
            except Exception:
                pass


def _scan_inbox_body(
    *,
    report: Dict[str, Any],
    apply: bool,
    max_bytes: int,
    known: Set[str],
    delivery: Dict[str, Any],
    inbox_final: str,
) -> Dict[str, Any]:
    from pilot_fs import assert_file_inside_inbox

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
            "path": str(entry),
            "extension": ext,
        }

        inside, final_or_err = assert_file_inside_inbox(entry, inbox_final)
        if not inside:
            result["status"] = "unsupported"
            result["error"] = f"Path containment failed: {final_or_err}"
            report["rejected"] += 1
            report["errors"].append(result["error"] + f" ({entry.name})")
            report["results"].append(result)
            continue
        result["path"] = final_or_err

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
            result["error"] = f"File exceeds size limit ({size} bytes > {max_bytes})"
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
            result["error"] = (
                "Invalid encoding or binary content; only strict UTF-8 .txt/.md are accepted"
            )
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
            "source_path": final_or_err,
            "source_filename": entry.name,
            "source_sha256": digest,
            "source_extension": ext,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "application_base_sha": APPLICATION_BASE_SHA,
            "delivery_commit": delivery.get("delivery_commit"),
            "scan_mode": "startup_or_manual",
        }
        try:
            memory.remember(
                thought=normalized,
                category="inbox_import",
                priority=0.75,
                metadata=metadata,
            )
        except Exception as exc:
            result["status"] = "error"
            result["error"] = f"memory_persist_failed:{exc}"
            report["rejected"] += 1
            report["errors"].append(result["error"])
            report["results"].append(result)
            report["ok"] = False
            continue

        # Durable integrity: reload from disk and confirm the SHA is present
        mem_path = Path(report["memory_filepath"])
        try:
            disk = json.loads(mem_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result["status"] = "error"
            result["error"] = f"post_write_integrity_failed:{exc}"
            report["rejected"] += 1
            report["errors"].append(result["error"])
            report["results"].append(result)
            report["ok"] = False
            continue
        persisted = any(
            (m.get("metadata") or {}).get("source_sha256") == digest
            or (
                (m.get("thought") or "") == normalized
                and (m.get("metadata") or {}).get("source") == "pilot_inbox"
            )
            for m in disk
        )
        if not persisted:
            result["status"] = "error"
            result["error"] = "post_write_integrity_failed:entry_missing_on_disk"
            report["rejected"] += 1
            report["errors"].append(result["error"])
            report["results"].append(result)
            report["ok"] = False
            continue

        _append_manifest(
            INBOX_MANIFEST,
            {
                "status": "imported",
                "sha256": digest,
                "filename": entry.name,
                "source_path": final_or_err,
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
