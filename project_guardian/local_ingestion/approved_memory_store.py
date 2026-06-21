"""Write operator-approved export records into a local JSONL memory store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .approved_memory_export import (
    APPROVED_MEMORY_EXPORT_FILENAME,
    default_export_path,
)
from .memory_candidates import MEMORY_CANDIDATES_SUBDIR, text_preview

MEMORY_STORE_SUBDIR = "memory_store"
APPROVED_MEMORY_STORE_FILENAME = "approved_memory_store.jsonl"
STORE_SAFETY_NOTES = "local_store_only_not_runtime_memory"
CREATED_BY = "local_approved_memory_store_writer"


class ApprovedMemoryStoreError(Exception):
    """Raised when approved local memory store writing cannot proceed safely."""


@dataclass
class StoreWriteReport:
    dest_dir: str
    approved_export_path: str
    memory_store_path: str
    apply: bool
    stored_count: int = 0
    skipped_invalid: int = 0
    records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dest_dir": self.dest_dir,
            "approved_export_path": self.approved_export_path,
            "memory_store_path": self.memory_store_path,
            "apply": self.apply,
            "stored_count": self.stored_count,
            "skipped_invalid": self.skipped_invalid,
            "records": self.records,
        }


def default_memory_store_path(dest_dir: Path) -> Path:
    return dest_dir / MEMORY_STORE_SUBDIR / APPROVED_MEMORY_STORE_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_memory_id(candidate_id: str) -> str:
    return hashlib.sha256(f"memory:{candidate_id}".encode("utf-8")).hexdigest()[:24]


def _read_jsonl(path: Path, *, label: str) -> List[Dict[str, Any]]:
    if not path.is_file():
        raise ApprovedMemoryStoreError(f"Approved export not found: {path}")
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ApprovedMemoryStoreError(
                        f"Malformed JSON in {label} at line {line_no}: {exc}"
                    ) from exc
                if not isinstance(item, dict):
                    raise ApprovedMemoryStoreError(
                        f"Expected JSON object in {label} at line {line_no}."
                    )
                records.append(item)
    except OSError as exc:
        raise ApprovedMemoryStoreError(f"Unable to read {label}: {exc}") from exc
    return records


def _is_eligible_export_record(record: Dict[str, Any]) -> bool:
    if record.get("operator_approved") is not True:
        return False
    if str(record.get("review_status") or "") != "approved":
        return False
    if record.get("live_memory_written") is not False:
        return False
    approved_text = str(record.get("approved_text") or "").strip()
    if not approved_text:
        return False
    if not str(record.get("candidate_id") or "").strip():
        return False
    return True


def _build_store_record(export_record: Dict[str, Any], *, stored_at: str) -> Dict[str, Any]:
    candidate_id = str(export_record["candidate_id"])
    text = str(export_record["approved_text"]).strip()
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "memory_id": _make_memory_id(candidate_id),
        "source": "approved_memory_export",
        "source_type": export_record.get("source_type"),
        "candidate_id": candidate_id,
        "text": text,
        "text_sha256": text_sha256,
        "original_filename": export_record.get("original_filename"),
        "imported_at": export_record.get("imported_at"),
        "approved_at": export_record.get("approved_at"),
        "exported_at": export_record.get("exported_at"),
        "stored_at": stored_at,
        "suggested_memory_type": export_record.get("suggested_memory_type"),
        "memory_status": "active",
        "operator_approved": True,
        "live_vector_written": False,
        "live_runtime_memory_written": False,
        "reversible": True,
        "safety_notes": STORE_SAFETY_NOTES,
        "text_preview": text_preview(text),
        "text_length": len(text),
        "tags": [],
        "importance": None,
        "created_by": CREATED_BY,
    }


def write_approved_memory_store(
    *,
    dest_dir: Optional[Path] = None,
    approved_export_path: Optional[Path] = None,
    memory_store_path: Optional[Path] = None,
    apply: bool = False,
) -> StoreWriteReport:
    if dest_dir is None and approved_export_path is None:
        raise ApprovedMemoryStoreError(
            "Provide --dest-dir or --approved-export to locate approved export records."
        )

    if approved_export_path is not None:
        export_path = approved_export_path.expanduser().resolve()
        resolved_dest = (
            dest_dir.expanduser().resolve()
            if dest_dir is not None
            else export_path.parent.parent
        )
    else:
        resolved_dest = dest_dir.expanduser().resolve()  # type: ignore[union-attr]
        export_path = default_export_path(resolved_dest)

    store_path = (
        memory_store_path.expanduser().resolve()
        if memory_store_path is not None
        else default_memory_store_path(resolved_dest)
    )

    export_records = _read_jsonl(export_path, label=str(export_path))
    stored_at = _utc_now_iso()
    store_records: List[Dict[str, Any]] = []
    skipped_invalid = 0

    for export_record in sorted(
        export_records,
        key=lambda item: str(item.get("candidate_id") or ""),
    ):
        if not _is_eligible_export_record(export_record):
            skipped_invalid += 1
            continue
        store_records.append(_build_store_record(export_record, stored_at=stored_at))

    report = StoreWriteReport(
        dest_dir=str(resolved_dest),
        approved_export_path=str(export_path),
        memory_store_path=str(store_path),
        apply=apply,
        stored_count=len(store_records),
        skipped_invalid=skipped_invalid,
        records=store_records,
    )

    if apply:
        lines = [json.dumps(record, ensure_ascii=False) for record in store_records]
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(
            ("\n".join(lines) + "\n") if lines else "",
            encoding="utf-8",
            newline="\n",
        )

    return report
