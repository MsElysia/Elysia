"""Review-queue memory candidates for operator-approved staging (no live memory writes)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

MEMORY_CANDIDATES_SUBDIR = "memory_candidates"
REVIEW_QUEUE_FILENAME = "review_queue.jsonl"
TEXT_PREVIEW_MAX = 280
SOURCE_TYPE_PHONE_TRANSCRIPTION = "phone_transcription"
DEFAULT_SUGGESTED_MEMORY_TYPE = "personal_note"
DEFAULT_SAFETY_NOTES = "operator_review_required"


def review_queue_path(dest_dir: Path) -> Path:
    return dest_dir / MEMORY_CANDIDATES_SUBDIR / REVIEW_QUEUE_FILENAME


def make_candidate_id(source_sha256: str, original_filename: str) -> str:
    key = f"{source_sha256}:{original_filename}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def text_preview(text: str, *, max_len: int = TEXT_PREVIEW_MAX) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def read_known_candidate_ids(queue_path: Path) -> Set[str]:
    if not queue_path.is_file():
        return set()
    ids: Set[str] = set()
    try:
        with queue_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                candidate_id = str(record.get("candidate_id") or "").strip()
                if candidate_id:
                    ids.add(candidate_id)
    except OSError:
        pass
    return ids


def build_memory_candidate(
    *,
    candidate_id: str,
    source_text_path: str,
    source_metadata_path: str,
    source_sha256: str,
    original_filename: str,
    imported_at: str,
    staged_at: str,
    normalized_text: str,
) -> Dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "source_type": SOURCE_TYPE_PHONE_TRANSCRIPTION,
        "source_text_path": source_text_path,
        "source_metadata_path": source_metadata_path,
        "source_sha256": source_sha256,
        "original_filename": original_filename,
        "imported_at": imported_at,
        "staged_at": staged_at,
        "review_status": "pending",
        "suggested_memory_type": DEFAULT_SUGGESTED_MEMORY_TYPE,
        "text_preview": text_preview(normalized_text),
        "text_length": len(normalized_text),
        "safety_notes": DEFAULT_SAFETY_NOTES,
        "live_memory_written": False,
    }


def stage_memory_candidate(
    dest_dir: Path,
    *,
    source_text_path: Path,
    source_metadata_path: Path,
    source_sha256: str,
    original_filename: str,
    imported_at: str,
    staged_at: str,
    normalized_text: str,
    known_candidate_ids: Optional[Set[str]] = None,
) -> Tuple[str, bool]:
    """
    Append one memory candidate to the review queue.

    Returns (status, wrote) where status is ``staged`` or ``duplicate_candidate``.
    """
    queue_path = review_queue_path(dest_dir)
    known = known_candidate_ids if known_candidate_ids is not None else read_known_candidate_ids(queue_path)
    candidate_id = make_candidate_id(source_sha256, original_filename)
    if candidate_id in known:
        return "duplicate_candidate", False

    record = build_memory_candidate(
        candidate_id=candidate_id,
        source_text_path=str(source_text_path),
        source_metadata_path=str(source_metadata_path),
        source_sha256=source_sha256,
        original_filename=original_filename,
        imported_at=imported_at,
        staged_at=staged_at,
        normalized_text=normalized_text,
    )
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    known.add(candidate_id)
    return "staged", True
