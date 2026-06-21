"""Export operator-approved memory candidates to a local package (no live memory writes)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_candidate_review import (
    MemoryCandidateReviewError,
    find_latest_edited_text_path,
    load_all_decisions,
    load_latest_decisions,
    load_queue_candidates,
    resolve_review_paths,
)
from .memory_candidates import MEMORY_CANDIDATES_SUBDIR

APPROVED_MEMORY_EXPORT_FILENAME = "approved_memory_export.jsonl"
EXPORT_SAFETY_NOTES = "approved_export_only_not_live_memory"


class ApprovedMemoryExportError(MemoryCandidateReviewError):
    """Raised when approved-memory export cannot proceed safely."""


@dataclass
class ExportReport:
    dest_dir: str
    queue_path: str
    decisions_path: str
    export_path: str
    exported_count: int = 0
    skipped_pending: int = 0
    skipped_rejected: int = 0
    skipped_other: int = 0
    records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dest_dir": self.dest_dir,
            "queue_path": self.queue_path,
            "decisions_path": self.decisions_path,
            "export_path": self.export_path,
            "exported_count": self.exported_count,
            "skipped_pending": self.skipped_pending,
            "skipped_rejected": self.skipped_rejected,
            "skipped_other": self.skipped_other,
            "records": self.records,
        }


def default_export_path(dest_dir: Path) -> Path:
    return dest_dir / MEMORY_CANDIDATES_SUBDIR / APPROVED_MEMORY_EXPORT_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_export_id(candidate_id: str) -> str:
    return hashlib.sha256(f"export:{candidate_id}".encode("utf-8")).hexdigest()[:24]


def _read_approved_text(
    candidate: Dict[str, Any],
    decision: Dict[str, Any],
    all_decisions: List[Dict[str, Any]],
) -> str:
    candidate_id = str(candidate.get("candidate_id") or "")
    edited_path = str(decision.get("edited_text_path") or "").strip()
    if not edited_path:
        edited_path = find_latest_edited_text_path(candidate_id, all_decisions) or ""
    if edited_path:
        path = Path(edited_path)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()

    source_path = str(candidate.get("source_text_path") or "").strip()
    if not source_path:
        raise ApprovedMemoryExportError(
            f"Candidate {candidate_id} is approved but has no readable source text path."
        )
    path = Path(source_path)
    if not path.is_file():
        raise ApprovedMemoryExportError(
            f"Candidate {candidate_id} source text not found: {source_path}"
        )
    return path.read_text(encoding="utf-8").strip()


def _build_export_record(
    candidate: Dict[str, Any],
    decision: Dict[str, Any],
    approved_text: str,
    *,
    exported_at: str,
) -> Dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    approved_text_sha256 = hashlib.sha256(approved_text.encode("utf-8")).hexdigest()
    return {
        "export_id": _make_export_id(candidate_id),
        "candidate_id": candidate_id,
        "source_type": candidate.get("source_type"),
        "approved_text": approved_text,
        "approved_text_sha256": approved_text_sha256,
        "source_text_path": candidate.get("source_text_path"),
        "source_metadata_path": candidate.get("source_metadata_path"),
        "source_sha256": candidate.get("source_sha256"),
        "original_filename": candidate.get("original_filename"),
        "imported_at": candidate.get("imported_at"),
        "approved_at": decision.get("decided_at"),
        "exported_at": exported_at,
        "suggested_memory_type": candidate.get("suggested_memory_type"),
        "review_status": "approved",
        "live_memory_written": False,
        "operator_approved": True,
        "safety_notes": EXPORT_SAFETY_NOTES,
    }


def export_approved_memory_candidates(
    *,
    dest_dir: Optional[Path] = None,
    queue_path: Optional[Path] = None,
    decisions_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> ExportReport:
    paths = resolve_review_paths(dest_dir=dest_dir, queue_path=queue_path)
    resolved_decisions = (
        decisions_path.expanduser().resolve()
        if decisions_path is not None
        else paths.decisions_path
    )
    export_path = (
        output_path.expanduser().resolve()
        if output_path is not None
        else default_export_path(paths.dest_dir)
    )

    try:
        candidates = load_queue_candidates(paths.queue_path)
        all_decisions = load_all_decisions(resolved_decisions)
        latest = load_latest_decisions(resolved_decisions)
    except MemoryCandidateReviewError as exc:
        raise ApprovedMemoryExportError(str(exc)) from exc
    exported_at = _utc_now_iso()

    report = ExportReport(
        dest_dir=str(paths.dest_dir),
        queue_path=str(paths.queue_path),
        decisions_path=str(resolved_decisions),
        export_path=str(export_path),
    )

    export_records: List[Dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: str(item.get("candidate_id") or "")):
        candidate_id = str(candidate.get("candidate_id") or "")
        decision = latest.get(candidate_id)
        if not decision:
            report.skipped_pending += 1
            continue
        status = str(decision.get("new_status") or "pending")
        if status == "pending":
            report.skipped_pending += 1
            continue
        if status == "rejected":
            report.skipped_rejected += 1
            continue
        if status != "approved":
            report.skipped_other += 1
            continue

        approved_text = _read_approved_text(candidate, decision, all_decisions)
        record = _build_export_record(
            candidate,
            decision,
            approved_text,
            exported_at=exported_at,
        )
        export_records.append(record)

    lines = [json.dumps(record, ensure_ascii=False) for record in export_records]
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        ("\n".join(lines) + "\n") if lines else "",
        encoding="utf-8",
        newline="\n",
    )

    report.exported_count = len(export_records)
    report.records = export_records
    return report
