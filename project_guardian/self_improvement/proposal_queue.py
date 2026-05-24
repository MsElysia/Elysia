# project_guardian/self_improvement/proposal_queue.py
"""Append-only JSONL queue of self-improvement proposals (review-only; no patch execution)."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from project_guardian.brain.trace_visibility import redact_sensitive

logger = logging.getLogger(__name__)

DEFAULT_PROPOSALS_PATH = Path(__file__).resolve().parents[2] / "data" / "runtime" / "self_improvement_proposals.jsonl"
LEGACY_BRAIN_QUEUE_PATH = Path(__file__).resolve().parents[2] / "data" / "runtime" / "brain_self_improvement_queue.jsonl"

LEGACY_QUEUE_WRITE_ENV = "ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE"
_LEGACY_QUEUE_WRITE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def legacy_queue_write_enabled() -> bool:
    """True when ``ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE`` is set to a truthy value."""
    v = os.environ.get(LEGACY_QUEUE_WRITE_ENV, "").strip().lower()
    return v in _LEGACY_QUEUE_WRITE_TRUTHY


def count_jsonl_rows(path: Path) -> int:
    """Read-only line count for diagnostics (non-empty lines)."""
    p = Path(path)
    if not p.exists():
        return 0
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())

_ALLOWED_CATEGORIES = frozenset(
    {
        "bug",
        "test_gap",
        "architecture",
        "prompt",
        "memory",
        "dashboard",
        "safety",
        "performance",
        "docs",
        "unknown",
    }
)
_ALLOWED_RISK = frozenset({"low", "medium", "high", "blocked", "unknown"})
_ALLOWED_STATUS = frozenset(
    {"proposed", "reviewing", "accepted", "rejected", "deferred", "implemented"}
)
_STATUS_UPDATE_ALLOWED = frozenset({"accepted", "rejected", "deferred", "reviewing", "implemented"})

_METADATA_BLOCK = frozenset(
    {
        "think_decide_act_trace",
        "raw_trace",
        "trace",
        "transitions",
        "execution",
        "run_context",
        "unified_export",
    }
)

_default_queue: Optional["ProposalQueue"] = None
_default_lock = threading.Lock()


def reset_default_proposal_queue_for_tests() -> None:
    global _default_queue
    with _default_lock:
        _default_queue = None


def get_default_proposal_queue(path: Optional[Path] = None) -> "ProposalQueue":
    global _default_queue
    with _default_lock:
        if _default_queue is None:
            _default_queue = ProposalQueue(path or DEFAULT_PROPOSALS_PATH)
        return _default_queue


@dataclass
class SelfImprovementProposal:
    proposal_id: str
    created_at: str
    source: str
    source_trace_id: str
    category: str
    title: str
    problem_summary: str
    evidence: Dict[str, Any]
    proposed_change: str
    affected_files: List[str]
    expected_benefit: str
    risk_level: str
    priority_score: float
    confidence: float
    status: str
    requires_human_review: bool
    blocked_reason: str
    tags: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def proposal_to_dict(p: SelfImprovementProposal) -> Dict[str, Any]:
    return asdict(p)


def proposal_from_dict(d: Dict[str, Any]) -> SelfImprovementProposal:
    kwargs: Dict[str, Any] = {}
    names = {f.name for f in fields(SelfImprovementProposal)}
    for k in names:
        if k not in d:
            continue
        kwargs[k] = d[k]
    return SelfImprovementProposal(**kwargs)


def sanitize_proposal(p: SelfImprovementProposal, *, for_api: bool = True) -> Dict[str, Any]:
    """Redact secrets, strip unsafe metadata; safe for HTTP."""
    d = proposal_to_dict(p)
    for key in (
        "title",
        "problem_summary",
        "proposed_change",
        "expected_benefit",
        "blocked_reason",
    ):
        if isinstance(d.get(key), str):
            d[key] = str(redact_sensitive(d[key]))[:4000]
    ev = d.get("evidence")
    if isinstance(ev, dict):
        clean_ev: Dict[str, Any] = {}
        for k, v in ev.items():
            if str(k).lower() in _METADATA_BLOCK:
                continue
            if isinstance(v, str):
                clean_ev[str(k)[:120]] = str(redact_sensitive(v))[:2000]
            elif isinstance(v, (int, float, bool)) or v is None:
                clean_ev[str(k)[:120]] = v
            elif isinstance(v, list) and all(isinstance(x, str) for x in v[:50]):
                clean_ev[str(k)[:120]] = [str(redact_sensitive(x))[:500] for x in v[:50]]
        d["evidence"] = clean_ev
    d["affected_files"] = [str(redact_sensitive(x))[:500] for x in (d.get("affected_files") or [])[:80]]
    d["tags"] = [str(x)[:80] for x in (d.get("tags") or [])[:40]]
    if for_api:
        meta2 = dict(p.metadata or {})
        note = meta2.get("status_note")
        d.pop("metadata", None)
        if note:
            d["review_note"] = str(redact_sensitive(str(note)))[:2000]
    else:
        d["metadata"] = _safe_metadata(dict(p.metadata or {}), for_api=False)
    return d


def _safe_metadata(meta: Dict[str, Any], *, for_api: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        sk = str(k)[:64]
        if sk in _METADATA_BLOCK:
            continue
        if isinstance(v, (dict, list)):
            continue
        if isinstance(v, str):
            out[sk] = str(redact_sensitive(v))[:1200]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[sk] = v
    if for_api and "status_note" in (meta or {}):
        out["status_note"] = str(redact_sensitive(str(meta.get("status_note"))))[:2000]
    return out


def create_proposal(
    *,
    source: str,
    source_trace_id: str,
    title: str,
    problem_summary: str,
    category: str = "unknown",
    evidence: Optional[Dict[str, Any]] = None,
    proposed_change: str = "",
    affected_files: Optional[List[str]] = None,
    expected_benefit: str = "",
    risk_level: str = "unknown",
    priority_score: float = 0.5,
    confidence: float = 0.5,
    status: str = "proposed",
    requires_human_review: bool = True,
    blocked_reason: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    proposal_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> SelfImprovementProposal:
    cat = str(category or "unknown").strip().lower()
    if cat not in _ALLOWED_CATEGORIES:
        cat = "unknown"
    rl = str(risk_level or "unknown").strip().lower()
    if rl not in _ALLOWED_RISK:
        rl = "unknown"
    st = str(status or "proposed").strip().lower()
    if st not in _ALLOWED_STATUS:
        st = "proposed"
    ps = max(0.0, min(1.0, float(priority_score)))
    cf = max(0.0, min(1.0, float(confidence)))
    pid = proposal_id or f"prop_{uuid.uuid4().hex[:20]}"
    return SelfImprovementProposal(
        proposal_id=pid,
        created_at=created_at or _utc_iso(),
        source=str(source or "unknown")[:120],
        source_trace_id=str(source_trace_id or "")[:128],
        category=cat,
        title=str(title or "")[:500],
        problem_summary=str(problem_summary or "")[:8000],
        evidence=dict(evidence or {}),
        proposed_change=str(proposed_change or "")[:8000],
        affected_files=list(affected_files or [])[:200],
        expected_benefit=str(expected_benefit or "")[:4000],
        risk_level=rl,
        priority_score=ps,
        confidence=cf,
        status=st,
        requires_human_review=bool(requires_human_review),
        blocked_reason=str(blocked_reason or "")[:2000],
        tags=[str(t)[:80] for t in (tags or [])[:50]],
        metadata=_strip_trace_metadata(dict(metadata or {})),
    )


def _strip_trace_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if str(k) in _METADATA_BLOCK:
            continue
        if isinstance(v, (dict, list)):
            continue
        if isinstance(v, str):
            out[str(k)[:64]] = v[:2000]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[str(k)[:64]] = v
    return out


def create_proposal_from_brain_learning(
    outcome: Any,
    trace: Any,
    *,
    source: str = "brain_pipeline",
) -> SelfImprovementProposal:
    """Build a proposal from BrainPipeline learning outcome + trace (no raw TDA payload)."""
    worked = bool(getattr(outcome, "worked", False))
    lesson = str(getattr(outcome, "lesson", "") or "")
    hints = list(getattr(outcome, "improvement_hints", None) or [])
    tid = str(getattr(trace, "brain_pipeline_id", "") or "")
    trans = getattr(trace, "transitions", None) or []
    tail = [str(t) for t in trans[-12:]] if isinstance(trans, list) else []
    evidence = {
        "worked": worked,
        "hint_count": len(hints),
        "hints": hints[:20],
        "transition_tail": tail,
    }
    risk = "low" if worked else "medium"
    priority = 0.45 if worked else 0.72
    return create_proposal(
        source=source,
        source_trace_id=tid,
        title=lesson[:120] or "Brain pipeline learning note",
        problem_summary=lesson[:4000],
        category="unknown",
        evidence=evidence,
        proposed_change="; ".join(str(h) for h in hints)[:4000] if hints else "Review pipeline lesson",
        expected_benefit="Stability or capability improvement after human review",
        risk_level=risk,
        priority_score=priority,
        confidence=0.55,
        status="proposed",
        requires_human_review=True,
        metadata={"enqueue": "brain_pipeline"},
    )


def append_proposal(p: SelfImprovementProposal, path: Optional[Path] = None) -> None:
    q = ProposalQueue(path or DEFAULT_PROPOSALS_PATH)
    q.append(sanitize_for_persist(p))


def sanitize_for_persist(p: SelfImprovementProposal) -> SelfImprovementProposal:
    """Normalize strings with redaction before writing JSONL."""
    d = sanitize_proposal(p, for_api=False)
    d["metadata"] = _strip_trace_metadata(dict(p.metadata or {}))
    for k in ("title", "problem_summary", "proposed_change", "expected_benefit", "blocked_reason"):
        if k in d and isinstance(d[k], str):
            d[k] = str(redact_sensitive(d[k]))
    return proposal_from_dict(d)


class ProposalQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, p: SelfImprovementProposal) -> None:
        line = json.dumps(proposal_to_dict(sanitize_for_persist(p)), ensure_ascii=False) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def read_all(self) -> List[SelfImprovementProposal]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                text = self.path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("proposal queue read failed: %s", exc)
                return []
        out: List[SelfImprovementProposal] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            try:
                out.append(proposal_from_dict(obj))
            except TypeError:
                continue
        return out

    def list_latest(self, *, limit: int = 100) -> List[SelfImprovementProposal]:
        rows = self.read_all()
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[: max(1, min(limit, 500))]

    def get(self, proposal_id: str) -> Optional[SelfImprovementProposal]:
        pid = str(proposal_id or "").strip()
        last: Optional[SelfImprovementProposal] = None
        for p in self.read_all():
            if p.proposal_id == pid:
                last = p
        return last

    def update_status(
        self,
        proposal_id: str,
        status: str,
        *,
        note: Optional[str] = None,
    ) -> Tuple[bool, str]:
        st = str(status or "").strip().lower()
        if st not in _STATUS_UPDATE_ALLOWED:
            return False, f"invalid_status:{st}"
        pid = str(proposal_id or "").strip()
        with self._lock:
            rows = ProposalQueue(self.path).read_all()
            found = False
            new_rows: List[SelfImprovementProposal] = []
            for p in rows:
                if p.proposal_id != pid:
                    new_rows.append(p)
                    continue
                found = True
                meta = dict(p.metadata or {})
                if note is not None and str(note).strip():
                    meta["status_note"] = str(note)[:4000]
                new_rows.append(
                    SelfImprovementProposal(
                        **{
                            **proposal_to_dict(p),
                            "status": st,
                            "metadata": meta,
                        }
                    )
                )
            if not found:
                return False, "not_found"
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                with tmp.open("w", encoding="utf-8") as fh:
                    for p in new_rows:
                        fh.write(json.dumps(proposal_to_dict(p), ensure_ascii=False) + "\n")
                tmp.replace(self.path)
            except OSError as exc:
                logger.warning("proposal queue rewrite failed: %s", exc)
                try:
                    tmp.unlink(missing_ok=True)  # type: ignore[arg-type]
                except OSError:
                    pass
                return False, f"write_error:{exc}"
        return True, "ok"


def list_proposals(*, limit: int = 100, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    q = ProposalQueue(path or DEFAULT_PROPOSALS_PATH)
    return [proposal_to_dict(p) for p in q.list_latest(limit=limit)]


def get_proposal(proposal_id: str, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    q = ProposalQueue(path or DEFAULT_PROPOSALS_PATH)
    p = q.get(proposal_id)
    return proposal_to_dict(p) if p else None


def update_proposal_status(
    proposal_id: str,
    status: str,
    *,
    note: Optional[str] = None,
    path: Optional[Path] = None,
) -> Tuple[bool, str]:
    return ProposalQueue(path or DEFAULT_PROPOSALS_PATH).update_status(proposal_id, status, note=note)


def rank_proposals(proposals: Iterable[SelfImprovementProposal]) -> List[SelfImprovementProposal]:
    rows = list(proposals)
    rows.sort(key=lambda p: (float(p.priority_score or 0), p.created_at), reverse=True)
    return rows


def load_latest_proposals(*, limit: int = 20, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    q = ProposalQueue(path or DEFAULT_PROPOSALS_PATH)
    ranked = rank_proposals(q.list_latest(limit=max(limit, 50)))
    return [proposal_to_dict(p) for p in ranked[:limit]]


def count_proposals_for_trace(source_trace_id: str, path: Optional[Path] = None) -> int:
    tid = str(source_trace_id or "").strip()
    if not tid:
        return 0
    n = 0
    for p in ProposalQueue(path or DEFAULT_PROPOSALS_PATH).read_all():
        if p.source_trace_id == tid:
            n += 1
    return n


def append_legacy_brain_row(row: Dict[str, Any], legacy_path: Optional[Path] = None) -> None:
    """Optional compatibility write to ``brain_self_improvement_queue.jsonl``."""
    pth = legacy_path or LEGACY_BRAIN_QUEUE_PATH
    pth.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    try:
        with pth.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        logger.warning("legacy self-improvement queue write failed: %s", exc)
