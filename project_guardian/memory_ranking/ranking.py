# project_guardian/memory_ranking/ranking.py
"""Deterministic memory ranking and compression proposals (advisory; no default mutation)."""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _REPO_ROOT / "config" / "memory_ranking.json"

_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",
)
_NAME_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")


@dataclass
class MemoryRankingConfig:
    enabled: bool = False
    dry_run: bool = True
    allow_delete_proposals: bool = False
    max_raw_memory_chars: int = 2000
    compression_threshold: float = 0.35
    archive_threshold: float = 0.20
    delete_threshold: float = 0.05
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "relevance": 0.25,
            "recency": 0.10,
            "frequency": 0.10,
            "confidence": 0.15,
            "user_importance": 0.15,
            "strategic_value": 0.15,
            "failure_prevention": 0.10,
        }
    )


@dataclass
class MemoryRankingInput:
    """One memory row for scoring (unknown fields use safe defaults)."""

    memory_id: str = ""
    text: str = ""
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    access_count: int = 0
    tags: Tuple[str, ...] = ()
    linked_goal: str = ""
    source: str = ""
    confidence: Optional[float] = None
    user_marked_important: bool = False
    failure_related: bool = False
    length_chars: int = 0
    is_active_commitment: bool = False
    category: str = ""


@dataclass
class MemoryScores:
    relevance_score: float = 0.0
    recency_score: float = 0.0
    frequency_score: float = 0.0
    confidence_score: float = 0.0
    user_importance_score: float = 0.0
    strategic_value_score: float = 0.0
    failure_prevention_score: float = 0.0
    compression_priority: float = 0.0
    retention_priority: float = 0.0


@dataclass
class RankedMemory:
    memory_id: str
    text: str
    scores: MemoryScores
    memory_value_score: float


@dataclass
class MemoryCompressionProposal:
    memory_id: str
    current_length: int
    proposed_summary: str
    reason: str
    original_value_score: float
    risk_of_loss: float
    action: str  # keep_full | compress | archive | review_manually
    dry_run: bool = True


@dataclass
class MemoryRankingReport:
    ranked: List[RankedMemory] = field(default_factory=list)
    proposals: List[MemoryCompressionProposal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _parse_bool(val: Any, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return default


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    t = ts.strip()
    if not t:
        return None
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def _days_since(ts: Optional[str], *, now: Optional[datetime] = None) -> Optional[float]:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    delta = ref - dt
    return max(0.0, delta.total_seconds() / 86400.0)


def _load_raw(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing_file"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("memory_ranking config invalid JSON %s: %s", path, exc)
        return {}, "invalid_json"
    if not isinstance(raw, dict):
        return {}, "bad_root"
    inner = raw.get("memory_ranking")
    if inner is None:
        return {}, "missing_memory_ranking_key"
    if not isinstance(inner, dict):
        return {}, "bad_memory_ranking_type"
    return inner, "ok"


def _merge(inner: Dict[str, Any], reason: str) -> MemoryRankingConfig:
    w = MemoryRankingConfig().weights.copy()
    raw_w = inner.get("weights")
    if isinstance(raw_w, dict):
        for k in list(w.keys()):
            if k in raw_w:
                try:
                    w[k] = float(raw_w[k])
                except (TypeError, ValueError):
                    pass
    try:
        mx = int(inner.get("max_raw_memory_chars", 2000))
    except (TypeError, ValueError):
        mx = 2000
    cfg = MemoryRankingConfig(
        enabled=_parse_bool(inner.get("enabled"), False),
        dry_run=_parse_bool(inner.get("dry_run"), True),
        allow_delete_proposals=_parse_bool(inner.get("allow_delete_proposals"), False),
        max_raw_memory_chars=max(200, mx),
        compression_threshold=_clamp01(float(inner.get("compression_threshold", 0.35))),
        archive_threshold=_clamp01(float(inner.get("archive_threshold", 0.20))),
        delete_threshold=_clamp01(float(inner.get("delete_threshold", 0.05))),
        weights=w,
    )
    if reason != "ok":
        logger.warning("memory_ranking config using defaults (%s)", reason)
    return cfg


@lru_cache(maxsize=8)
def get_memory_ranking_config(*, _path_str: str = "") -> MemoryRankingConfig:
    path = Path(_path_str) if _path_str else _DEFAULT_PATH
    inner, reason = _load_raw(path)
    return _merge(inner, reason)


def clear_memory_ranking_config_cache() -> None:
    get_memory_ranking_config.cache_clear()


def _failure_lexical_boost(text: str) -> float:
    low = (text or "").lower()
    hits = sum(1 for k in ("failure", "failed", "error", "root cause", "postmortem", "bug", "regression") if k in low)
    return _clamp01(0.12 * hits)


def _relevance_score(text: str, goal: str) -> float:
    if not goal.strip():
        return 0.45
    gw = {w for w in re.findall(r"[a-z0-9]{3,}", goal.lower())}
    tw = {w for w in re.findall(r"[a-z0-9]{3,}", text.lower())}
    if not gw:
        return 0.45
    overlap = len(gw & tw) / max(1, len(gw))
    return _clamp01(0.25 + 0.75 * overlap)


def _recency_score(inp: MemoryRankingInput, *, now: Optional[datetime] = None) -> float:
    d = _days_since(inp.last_used_at, now=now) or _days_since(inp.created_at, now=now)
    if d is None:
        return 0.50
    return _clamp01(math.exp(-d / 45.0))


def _frequency_score(access: int) -> float:
    return _clamp01(math.log1p(max(0, access)) / math.log1p(50))


def score_memory(
    inp: MemoryRankingInput,
    cfg: MemoryRankingConfig,
    *,
    current_goal_text: str = "",
    now: Optional[datetime] = None,
) -> Tuple[MemoryScores, float]:
    """Return sub-scores and a single ``memory_value_score`` in ``[0, 1]``."""
    try:
        text = inp.text or ""
        ln = inp.length_chars if inp.length_chars > 0 else len(text)
        rel = _relevance_score(text, current_goal_text)
        rec = _recency_score(inp, now=now)
        freq = _frequency_score(inp.access_count)
        conf = _clamp01(float(inp.confidence) if inp.confidence is not None else 0.55)
        uimp = 0.95 if inp.user_marked_important else 0.35
        strat = 0.85 if (inp.linked_goal or "").strip() else 0.42
        base_fail = 0.92 if inp.failure_related else 0.38
        failp = _clamp01(base_fail + _failure_lexical_boost(text))
        w = cfg.weights
        total_w = sum(max(0.0, w.get(k, 0.0)) for k in w)
        if total_w <= 0:
            total_w = 1.0
        value = (
            w.get("relevance", 0) * rel
            + w.get("recency", 0) * rec
            + w.get("frequency", 0) * freq
            + w.get("confidence", 0) * conf
            + w.get("user_importance", 0) * uimp
            + w.get("strategic_value", 0) * strat
            + w.get("failure_prevention", 0) * failp
        ) / total_w
        value = _clamp01(value)
        vmax = max(0.001, float(cfg.max_raw_memory_chars))
        comp_pri = _clamp01((1.0 - value) * min(1.0, ln / vmax))
        ret_pri = _clamp01(value * (0.55 + 0.45 * uimp))
        scores = MemoryScores(
            relevance_score=rel,
            recency_score=rec,
            frequency_score=freq,
            confidence_score=conf,
            user_importance_score=uimp,
            strategic_value_score=strat,
            failure_prevention_score=failp,
            compression_priority=comp_pri,
            retention_priority=ret_pri,
        )
        return scores, value
    except Exception as exc:
        logger.debug("score_memory fallback: %s", exc)
        neutral = MemoryScores(
            relevance_score=0.5,
            recency_score=0.5,
            frequency_score=0.5,
            confidence_score=0.5,
            user_importance_score=0.5,
            strategic_value_score=0.5,
            failure_prevention_score=0.5,
            compression_priority=0.5,
            retention_priority=0.5,
        )
        return neutral, 0.5


def rank_memories(
    items: List[MemoryRankingInput],
    cfg: MemoryRankingConfig,
    *,
    current_goal_text: str = "",
    now: Optional[datetime] = None,
) -> List[RankedMemory]:
    ranked: List[RankedMemory] = []
    for it in items:
        mid = (it.memory_id or "").strip() or uuid.uuid4().hex[:12]
        scores, val = score_memory(it, cfg, current_goal_text=current_goal_text, now=now)
        ranked.append(RankedMemory(memory_id=mid, text=it.text, scores=scores, memory_value_score=val))
    ranked.sort(key=lambda r: r.memory_value_score, reverse=True)
    return ranked


def _redact_quick(s: str) -> str:
    try:
        from project_guardian.brain.trace_visibility import redact_sensitive

        return str(redact_sensitive(s))
    except Exception:
        return s


def redact_memory_text(text: str) -> str:
    """Redact likely secrets before persistence or compression summaries."""
    return _redact_quick(text)


def summarize_memory_for_compression(
    text_or_memory: Any,
    *,
    max_len: int = 420,
    max_chars: Optional[int] = None,
) -> str:
    """Short deterministic summary; ``text_or_memory`` may be a str or dict with ``thought`` / ``text``."""
    lim = int(max_chars) if max_chars is not None else int(max_len)
    if isinstance(text_or_memory, dict):
        t = str(text_or_memory.get("thought") or text_or_memory.get("text") or "")
    else:
        t = str(text_or_memory or "")
    t = _redact_quick(t).strip()
    if not t:
        return "[compressed] (empty)"
    keep: List[str] = []
    for m in _DATE_RE.findall(t):
        if m not in keep:
            keep.append(m)
    for m in _NAME_RE.findall(t):
        if len(m) > 3 and m not in keep:
            keep.append(m)
    low = t.lower()
    for needle in (
        "user prefers",
        "preference",
        "decided",
        "decision",
        "failure cause",
        "root cause",
        "lesson learned",
        "commitment",
        "deadline",
        "active goal",
    ):
        idx = low.find(needle)
        if idx >= 0:
            frag = t[idx : idx + 180].strip()
            if frag and frag not in keep:
                keep.append(frag)
    head = " | ".join(keep) if keep else ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    buf: List[str] = []
    n = len(head) + 16 if head else 0
    for p in parts:
        if n + len(p) > lim - 12:
            break
        buf.append(p)
        n += len(p) + 1
    body = " ".join(buf).strip()
    if len(body) < min(40, len(t)):
        body = t[: lim - 12]
    out = ("[compressed] " + (head + " — " if head else "") + body).strip()
    if len(out) > lim:
        out = out[: lim - 3] + "..."
    return out


def should_retain_full_memory(ranked: RankedMemory, cfg: MemoryRankingConfig) -> bool:
    return ranked.memory_value_score >= cfg.compression_threshold or ranked.scores.user_importance_score >= 0.9


def propose_memory_compression(
    ranked: List[RankedMemory],
    cfg: MemoryRankingConfig,
) -> List[MemoryCompressionProposal]:
    props: List[MemoryCompressionProposal] = []
    for r in ranked:
        text = r.text or ""
        ln = len(text)
        risk = _clamp01(1.0 - r.memory_value_score + 0.15 * r.scores.compression_priority)
        low = text.lower()
        # Protected / commitments first: never auto-keep-full solely on score
        if (
            "commitment" in low
            or "deadline:" in low
            or "due:" in low
            or "todo:" in low
            or " i will " in low
            or " i'll " in low
            or "high risk" in low
            or "active task" in low
            or "user prefers" in low
            or "do not expose" in low
            or "credentials" in low
        ):
            props.append(
                MemoryCompressionProposal(
                    memory_id=r.memory_id,
                    current_length=ln,
                    proposed_summary=text[:800],
                    reason="possible_active_commitment_manual_review",
                    original_value_score=r.memory_value_score,
                    risk_of_loss=0.75,
                    action="review_manually",
                    dry_run=True,
                )
            )
            continue
        if r.scores.user_importance_score >= 0.9 or r.memory_value_score >= 0.92:
            props.append(
                MemoryCompressionProposal(
                    memory_id=r.memory_id,
                    current_length=ln,
                    proposed_summary=text[:800],
                    reason="high_value_or_user_marked_important",
                    original_value_score=r.memory_value_score,
                    risk_of_loss=risk,
                    action="keep_full",
                    dry_run=True,
                )
            )
            continue
        if r.memory_value_score < cfg.archive_threshold:
            props.append(
                MemoryCompressionProposal(
                    memory_id=r.memory_id,
                    current_length=ln,
                    proposed_summary=summarize_memory_for_compression(text),
                    reason="below_archive_threshold",
                    original_value_score=r.memory_value_score,
                    risk_of_loss=risk,
                    action="archive",
                    dry_run=bool(cfg.dry_run),
                )
            )
            continue
        if r.memory_value_score < cfg.compression_threshold and ln > 180:
            props.append(
                MemoryCompressionProposal(
                    memory_id=r.memory_id,
                    current_length=ln,
                    proposed_summary=summarize_memory_for_compression(text),
                    reason="below_compression_threshold_and_long",
                    original_value_score=r.memory_value_score,
                    risk_of_loss=risk,
                    action="compress",
                    dry_run=bool(cfg.dry_run),
                )
            )
            continue
        props.append(
            MemoryCompressionProposal(
                memory_id=r.memory_id,
                current_length=ln,
                proposed_summary=text[:800],
                reason="default_keep",
                original_value_score=r.memory_value_score,
                risk_of_loss=risk,
                action="keep_full",
                dry_run=True,
            )
        )
    return props


def review_memory_scores_with_llm(
    ranked: List[RankedMemory],
    *,
    reviewer: Optional[Callable[[List[RankedMemory]], List[RankedMemory]]] = None,
) -> List[RankedMemory]:
    """Optional LLM hook; default is identity. Caller must enforce safety after review."""
    if reviewer is None:
        return ranked
    try:
        return reviewer(ranked)
    except Exception as exc:
        logger.warning("memory_ranking llm reviewer failed: %s", exc)
        return ranked


def build_ranking_report(
    items: List[MemoryRankingInput],
    cfg: MemoryRankingConfig,
    *,
    current_goal_text: str = "",
    now: Optional[datetime] = None,
    reviewer: Optional[Callable[[List[RankedMemory]], List[RankedMemory]]] = None,
) -> MemoryRankingReport:
    warnings: List[str] = []
    ranked = rank_memories(items, cfg, current_goal_text=current_goal_text, now=now)
    ranked2 = review_memory_scores_with_llm(ranked, reviewer=reviewer)
    proposals = propose_memory_compression(ranked2, cfg)
    return MemoryRankingReport(ranked=ranked2, proposals=proposals, warnings=warnings)


def memory_dict_to_input(mem: Dict[str, Any], index: int = 0) -> MemoryRankingInput:
    """Best-effort mapping from loose dicts (e.g. MemoryCore rows) to MemoryRankingInput."""
    mid = str(mem.get("id") or mem.get("memory_id") or f"mem-{index}")
    thought = str(mem.get("thought") or mem.get("text") or "")
    created = mem.get("created_at") or mem.get("time") or mem.get("timestamp")
    lastu = mem.get("last_used_at") or mem.get("last_access")
    try:
        ac = int(mem.get("access_count") or mem.get("accesses") or 0)
    except (TypeError, ValueError):
        ac = 0
    conf = mem.get("confidence")
    if conf is not None:
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = None
    try:
        pri = float(mem.get("priority", 0.5))
    except (TypeError, ValueError):
        pri = 0.5
    tl = thought.lower()
    user_imp = bool(
        mem.get("user_important")
        or mem.get("user_marked_important")
        or pri >= 0.85
        or ("user prefers" in tl)
        or ("important decision" in tl)
    )
    cat = str(mem.get("category") or "")
    fail = "error" in cat.lower() or "fail" in cat.lower() or "postmortem" in thought.lower()
    return MemoryRankingInput(
        memory_id=mid,
        text=thought,
        created_at=str(created) if created is not None else None,
        last_used_at=str(lastu) if lastu is not None else None,
        access_count=ac,
        linked_goal=str(mem.get("linked_goal") or "")[:500],
        source=str(mem.get("source") or "")[:120],
        confidence=conf,
        user_marked_important=user_imp,
        failure_related=fail,
        category=cat[:120],
    )


def optional_remember_extras_for_pipeline(
    lesson: str,
    pipeline_ctx: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Small JSON-safe kwargs fragment for ``memory.remember``; never raises."""
    if not pipeline_ctx:
        return {}
    try:
        cfg = get_memory_ranking_config()
        if not (cfg.enabled or bool(pipeline_ctx.get("rank_memory"))):
            return {}
        goal = str(
            pipeline_ctx.get("compression_goal_context")
            or pipeline_ctx.get("plan_goal_hint")
            or (pipeline_ctx.get("plan_goal") if isinstance(pipeline_ctx.get("plan_goal"), str) else "")
            or ""
        )[:2000]
        now_ts = pipeline_ctx.get("now")
        now_dt = _parse_iso(str(now_ts)) if now_ts else None
        inp = MemoryRankingInput(
            memory_id=str(pipeline_ctx.get("memory_ranking_id") or "") or "pipeline",
            text=lesson or "",
            length_chars=len(lesson or ""),
            failure_related=bool(pipeline_ctx.get("failure_related")),
            user_marked_important=bool(pipeline_ctx.get("user_marked_important")),
            linked_goal=str(pipeline_ctx.get("linked_goal") or "")[:500],
            source=str(pipeline_ctx.get("source_entrypoint") or "brain_pipeline")[:120],
            category=str(pipeline_ctx.get("lesson_category") or "brain_lesson")[:120],
        )
        scores, val = score_memory(inp, cfg, current_goal_text=goal, now=now_dt)
        return {
            "memory_ranking": {
                "value_score": val,
                "scores": asdict(scores),
                "config_dry_run": cfg.dry_run,
                "config_enabled": cfg.enabled,
            }
        }
    except Exception as exc:
        logger.debug("optional_remember_extras_for_pipeline skipped: %s", exc)
        return {}
