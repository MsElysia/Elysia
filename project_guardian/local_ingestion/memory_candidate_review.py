"""Operator review of staged memory candidates (audit trail only; no live memory writes)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory_candidates import MEMORY_CANDIDATES_SUBDIR, REVIEW_QUEUE_FILENAME

REVIEW_DECISIONS_FILENAME = "review_decisions.jsonl"
APPROVED_CANDIDATES_FILENAME = "approved_candidates.jsonl"
REJECTED_CANDIDATES_FILENAME = "rejected_candidates.jsonl"
EDITED_TEXT_SUBDIR = "edited"

FINAL_DECISION_STATUSES = frozenset({"approved", "rejected", "edited"})


class MemoryCandidateReviewError(Exception):
    """Raised when review operations cannot proceed safely."""


@dataclass
class ReviewPaths:
    dest_dir: Path
    queue_path: Path
    decisions_path: Path
    approved_path: Path
    rejected_path: Path
    edited_dir: Path


@dataclass
class ListReport:
    queue_path: str
    filter_status: str
    count: int
    candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue_path": self.queue_path,
            "filter_status": self.filter_status,
            "count": self.count,
            "candidates": self.candidates,
        }


@dataclass
class DecisionReport:
    decision: Dict[str, Any]
    snapshot_path: Optional[str] = None
    edited_text_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {"decision": self.decision}
        if self.snapshot_path:
            payload["snapshot_path"] = self.snapshot_path
        if self.edited_text_path:
            payload["edited_text_path"] = self.edited_text_path
        return payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _memory_candidates_dir(dest_dir: Path) -> Path:
    return dest_dir / MEMORY_CANDIDATES_SUBDIR


def resolve_review_paths(
    *,
    dest_dir: Optional[Path] = None,
    queue_path: Optional[Path] = None,
) -> ReviewPaths:
    if queue_path is None and dest_dir is None:
        raise MemoryCandidateReviewError(
            "Provide --dest-dir or --queue-path to locate the review queue."
        )

    if queue_path is not None:
        resolved_queue = queue_path.expanduser().resolve()
        if dest_dir is not None:
            resolved_dest = dest_dir.expanduser().resolve()
        else:
            if resolved_queue.parent.name != MEMORY_CANDIDATES_SUBDIR:
                raise MemoryCandidateReviewError(
                    f"Queue path must live under {MEMORY_CANDIDATES_SUBDIR}/ when --dest-dir is omitted: "
                    f"{resolved_queue}"
                )
            resolved_dest = resolved_queue.parent.parent
    else:
        resolved_dest = dest_dir.expanduser().resolve()  # type: ignore[union-attr]
        resolved_queue = _memory_candidates_dir(resolved_dest) / REVIEW_QUEUE_FILENAME

    base = _memory_candidates_dir(resolved_dest)
    return ReviewPaths(
        dest_dir=resolved_dest,
        queue_path=resolved_queue,
        decisions_path=base / REVIEW_DECISIONS_FILENAME,
        approved_path=base / APPROVED_CANDIDATES_FILENAME,
        rejected_path=base / REJECTED_CANDIDATES_FILENAME,
        edited_dir=base / EDITED_TEXT_SUBDIR,
    )


def _read_jsonl(path: Path, *, label: str) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
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
                    raise MemoryCandidateReviewError(
                        f"Malformed JSON in {label} at line {line_no}: {exc}"
                    ) from exc
                if not isinstance(item, dict):
                    raise MemoryCandidateReviewError(
                        f"Expected JSON object in {label} at line {line_no}."
                    )
                records.append(item)
    except OSError as exc:
        raise MemoryCandidateReviewError(f"Unable to read {label}: {exc}") from exc
    return records


def load_queue_candidates(queue_path: Path) -> List[Dict[str, Any]]:
    if not queue_path.is_file():
        raise MemoryCandidateReviewError(f"Review queue not found: {queue_path}")
    records = _read_jsonl(queue_path, label=str(queue_path))
    by_id: Dict[str, Dict[str, Any]] = {}
    for record in records:
        candidate_id = str(record.get("candidate_id") or "").strip()
        if not candidate_id:
            raise MemoryCandidateReviewError(
                f"Queue record missing candidate_id in {queue_path}"
            )
        by_id[candidate_id] = record
    return list(by_id.values())


def load_latest_decisions(decisions_path: Path) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for record in _read_jsonl(decisions_path, label=str(decisions_path)):
        candidate_id = str(record.get("candidate_id") or "").strip()
        if candidate_id:
            latest[candidate_id] = record
    return latest


def effective_status(
    candidate: Dict[str, Any],
    latest_decisions: Dict[str, Dict[str, Any]],
) -> str:
    candidate_id = str(candidate.get("candidate_id") or "")
    decision = latest_decisions.get(candidate_id)
    if decision:
        return str(decision.get("new_status") or candidate.get("review_status") or "pending")
    return str(candidate.get("review_status") or "pending")


def list_candidates(
    paths: ReviewPaths,
    *,
    include_all: bool = False,
) -> ListReport:
    candidates = load_queue_candidates(paths.queue_path)
    latest = load_latest_decisions(paths.decisions_path)
    visible: List[Dict[str, Any]] = []
    for candidate in candidates:
        status = effective_status(candidate, latest)
        item = dict(candidate)
        item["effective_review_status"] = status
        if include_all or status == "pending":
            visible.append(item)
    return ListReport(
        queue_path=str(paths.queue_path),
        filter_status="all" if include_all else "pending",
        count=len(visible),
        candidates=visible,
    )


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _make_decision_id(candidate_id: str, new_status: str, decided_at: str) -> str:
    digest = hashlib.sha256(f"{candidate_id}:{new_status}:{decided_at}".encode("utf-8")).hexdigest()
    return digest[:24]


def _require_candidate(
    candidate_id: str,
    candidates_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if candidate_id not in candidates_by_id:
        raise MemoryCandidateReviewError(f"Candidate not found: {candidate_id}")
    return candidates_by_id[candidate_id]


def _guard_final_decision(
    candidate_id: str,
    latest_decisions: Dict[str, Dict[str, Any]],
    *,
    force: bool,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    prior = latest_decisions.get(candidate_id)
    if prior and str(prior.get("new_status")) in FINAL_DECISION_STATUSES and not force:
        raise MemoryCandidateReviewError(
            f"Candidate {candidate_id} already has final decision "
            f"{prior.get('new_status')}. Use --force to override."
        )
    previous_status = "pending"
    if prior:
        previous_status = str(prior.get("new_status") or "pending")
    return previous_status, prior


def _build_decision(
    *,
    candidate_id: str,
    previous_status: str,
    new_status: str,
    source_queue_path: Path,
    notes: Optional[str] = None,
    edited_text_path: Optional[str] = None,
) -> Dict[str, Any]:
    decided_at = _utc_now_iso()
    decision: Dict[str, Any] = {
        "decision_id": _make_decision_id(candidate_id, new_status, decided_at),
        "candidate_id": candidate_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "decided_at": decided_at,
        "operator_required": True,
        "live_memory_written": False,
        "source_queue_path": str(source_queue_path),
    }
    if notes:
        decision["notes"] = notes
    if edited_text_path:
        decision["edited_text_path"] = edited_text_path
    return decision


def _snapshot_record(
    candidate: Dict[str, Any],
    decision: Dict[str, Any],
    *,
    edited_text_path: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot = dict(candidate)
    snapshot["effective_review_status"] = decision["new_status"]
    snapshot["latest_decision_id"] = decision["decision_id"]
    snapshot["decided_at"] = decision["decided_at"]
    snapshot["live_memory_written"] = False
    if decision.get("notes"):
        snapshot["review_notes"] = decision["notes"]
    if edited_text_path:
        snapshot["edited_text_path"] = edited_text_path
    return snapshot


def approve_candidate(
    paths: ReviewPaths,
    candidate_id: str,
    *,
    notes: Optional[str] = None,
    force: bool = False,
) -> DecisionReport:
    candidates = load_queue_candidates(paths.queue_path)
    candidates_by_id = {str(c["candidate_id"]): c for c in candidates}
    candidate = _require_candidate(candidate_id, candidates_by_id)
    latest = load_latest_decisions(paths.decisions_path)
    previous_status, _prior = _guard_final_decision(candidate_id, latest, force=force)

    decision = _build_decision(
        candidate_id=candidate_id,
        previous_status=previous_status,
        new_status="approved",
        source_queue_path=paths.queue_path,
        notes=notes,
    )
    snapshot = _snapshot_record(candidate, decision)
    _append_jsonl(paths.decisions_path, decision)
    _append_jsonl(paths.approved_path, snapshot)
    return DecisionReport(decision=decision, snapshot_path=str(paths.approved_path))


def reject_candidate(
    paths: ReviewPaths,
    candidate_id: str,
    *,
    notes: Optional[str] = None,
    force: bool = False,
) -> DecisionReport:
    candidates = load_queue_candidates(paths.queue_path)
    candidates_by_id = {str(c["candidate_id"]): c for c in candidates}
    candidate = _require_candidate(candidate_id, candidates_by_id)
    latest = load_latest_decisions(paths.decisions_path)
    previous_status, _prior = _guard_final_decision(candidate_id, latest, force=force)

    decision = _build_decision(
        candidate_id=candidate_id,
        previous_status=previous_status,
        new_status="rejected",
        source_queue_path=paths.queue_path,
        notes=notes,
    )
    snapshot = _snapshot_record(candidate, decision)
    _append_jsonl(paths.decisions_path, decision)
    _append_jsonl(paths.rejected_path, snapshot)
    return DecisionReport(decision=decision, snapshot_path=str(paths.rejected_path))


def edit_candidate(
    paths: ReviewPaths,
    candidate_id: str,
    replacement_text: str,
    *,
    notes: Optional[str] = None,
    force: bool = False,
) -> DecisionReport:
    if not replacement_text.strip():
        raise MemoryCandidateReviewError("Replacement text must not be empty.")

    candidates = load_queue_candidates(paths.queue_path)
    candidates_by_id = {str(c["candidate_id"]): c for c in candidates}
    candidate = _require_candidate(candidate_id, candidates_by_id)
    latest = load_latest_decisions(paths.decisions_path)
    previous_status, _prior = _guard_final_decision(candidate_id, latest, force=force)

    paths.edited_dir.mkdir(parents=True, exist_ok=True)
    edited_path = paths.edited_dir / f"{candidate_id}.txt"
    if edited_path.exists() and not force:
        raise MemoryCandidateReviewError(
            f"Edited artifact already exists for {candidate_id}. Use --force to overwrite."
        )
    edited_path.write_text(replacement_text.rstrip() + "\n", encoding="utf-8", newline="\n")

    decision = _build_decision(
        candidate_id=candidate_id,
        previous_status=previous_status,
        new_status="edited",
        source_queue_path=paths.queue_path,
        notes=notes,
        edited_text_path=str(edited_path),
    )
    snapshot = _snapshot_record(candidate, decision, edited_text_path=str(edited_path))
    _append_jsonl(paths.decisions_path, decision)
    _append_jsonl(paths.approved_path, snapshot)
    return DecisionReport(
        decision=decision,
        snapshot_path=str(paths.approved_path),
        edited_text_path=str(edited_path),
    )
