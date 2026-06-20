"""Operator-run local file ingestion (no autonomy, no background watchers)."""

from .memory_candidate_review import (
    APPROVED_CANDIDATES_FILENAME,
    REJECTED_CANDIDATES_FILENAME,
    REVIEW_DECISIONS_FILENAME,
    DecisionReport,
    ListReport,
    MemoryCandidateReviewError,
    ReviewPaths,
    approve_candidate,
    edit_candidate,
    list_candidates,
    reject_candidate,
    resolve_review_paths,
)
from .memory_candidates import (
    MEMORY_CANDIDATES_SUBDIR,
    REVIEW_QUEUE_FILENAME,
    review_queue_path,
    stage_memory_candidate,
)
from .transcription_ingest import (
    ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_MB,
    IngestReport,
    default_dest_dir,
    ingest_transcriptions,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "APPROVED_CANDIDATES_FILENAME",
    "DEFAULT_MAX_FILE_MB",
    "DecisionReport",
    "IngestReport",
    "ListReport",
    "MEMORY_CANDIDATES_SUBDIR",
    "MemoryCandidateReviewError",
    "REJECTED_CANDIDATES_FILENAME",
    "REVIEW_DECISIONS_FILENAME",
    "REVIEW_QUEUE_FILENAME",
    "ReviewPaths",
    "approve_candidate",
    "default_dest_dir",
    "edit_candidate",
    "ingest_transcriptions",
    "list_candidates",
    "reject_candidate",
    "resolve_review_paths",
    "review_queue_path",
    "stage_memory_candidate",
]
