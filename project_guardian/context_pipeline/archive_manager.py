# project_guardian/context_pipeline/archive_manager.py
"""Topic archives with metadata, decay hints, and hygiene reports (no auto-delete)."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .memory_sidecar import ensure_pipeline_data_dir
from .relevance_engine import topic_bucket_for_record
from .schemas import TOPIC_BUCKETS, IngestedRecordDict

logger = logging.getLogger(__name__)


def archive_path() -> Path:
    return ensure_pipeline_data_dir() / "context_archive.jsonl"


def archive_state_path() -> Path:
    return ensure_pipeline_data_dir() / "archive_state.json"


def _load_archive_state() -> Dict[str, Any]:
    p = archive_state_path()
    if not p.is_file():
        return {"records": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"records": {}}


def _save_archive_state(state: Dict[str, Any]) -> None:
    p = archive_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, ensure_ascii=False)
    last_pe: PermissionError | None = None
    for attempt in range(8):
        tmp = p.parent / f".archive_state_{os.getpid()}_{attempt}_{random.randint(0, 999_999)}.tmp"
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(p)
            return
        except PermissionError as e:
            last_pe = e
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(0.02 * (2**attempt))
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise
    try:
        p.write_text(payload, encoding="utf-8")
    except Exception:
        if last_pe:
            raise last_pe
        raise


def get_record_archive_state(record_id: str) -> Dict[str, Any]:
    if not record_id:
        return {}
    st = _load_archive_state()
    row = (st.get("records") or {}).get(record_id)
    return dict(row) if isinstance(row, dict) else {}


def relevance_decay_multiplier(record_id: str, cfg: Dict[str, Any]) -> float:
    """Scale down archived-but-stale evidence unless retrieved/reinforced (no deletes)."""
    if not record_id or not bool(cfg.get("archive_decay_enabled", True)):
        return 1.0
    m = get_record_archive_state(record_id)
    stale = float(m.get("stale_score") or 0.0)
    tr = int(m.get("times_retrieved") or 0)
    reinforced = int(m.get("times_reinforced") or 0)
    k_stale = float(cfg.get("archive_decay_stale_weight") or 0.018)
    k_rec = float(cfg.get("archive_decay_retrieval_boost") or 0.012)
    k_reinf = float(cfg.get("archive_decay_reinforce_boost") or 0.02)
    factor = 1.0 - min(0.35, stale * k_stale) + min(0.12, tr * k_rec + reinforced * k_reinf)
    return max(0.35, min(1.05, factor))


def _touch_record_state(record_id: str, kind: str) -> None:
    """kind: archived | retrieved"""
    st = _load_archive_state()
    recs: Dict[str, Any] = st.setdefault("records", {})
    now = time.time()
    row = recs.get(record_id) or {
        "first_seen": now,
        "last_seen": now,
        "times_archived": 0,
        "times_retrieved": 0,
        "times_reinforced": 0,
        "contradiction_count": 0,
        "stale_score": 0.0,
    }
    prev_last = float(row.get("last_seen") or now)
    row["last_seen"] = now
    if kind == "archived":
        row["times_archived"] = int(row.get("times_archived") or 0) + 1
        row["times_reinforced"] = int(row.get("times_reinforced") or 0) + 1
    elif kind == "retrieved":
        row["times_retrieved"] = int(row.get("times_retrieved") or 0) + 1
    age = max(0.0, now - float(row.get("first_seen") or now))
    idle = max(0.0, now - prev_last)
    stale = (idle / 86400.0) * (1.0 / (1.0 + int(row.get("times_retrieved") or 0)))
    stale += 0.02 * max(0, int(row.get("times_archived") or 0) - int(row.get("times_retrieved") or 0))
    row["stale_score"] = round(min(99.0, stale), 4)
    recs[record_id] = row
    _save_archive_state(st)


def append_archived(
    records: Iterable[IngestedRecordDict],
    *,
    topic: str,
    relevance: float,
    session_id: str,
    cfg: Dict[str, Any],
) -> int:
    topic = topic if topic in TOPIC_BUCKETS else "architecture"
    p = archive_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    n = 0
    with open(p, "a", encoding="utf-8") as f:
        for r in records:
            rid = str((r or {}).get("id") or "")
            meta = {
                "first_seen": now,
                "last_seen": now,
                "times_retrieved": 0,
                "times_reinforced": 1,
                "contradiction_count": 0,
                "stale_score": 0.0,
            }
            rec = {
                "ts": now,
                "session_id": session_id,
                "topic": topic,
                "relevance": round(float(relevance), 4),
                "archive_meta": meta,
                "record": dict(r),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if rid:
                _touch_record_state(rid, "archived")
    if n:
        logger.info("[Archive] topic=%s rows=%s path=%s", topic, n, p)
    return n


def touch_retrieved_evidence(record_ids: List[str]) -> None:
    for rid in record_ids:
        if rid:
            _touch_record_state(rid, "retrieved")


def analyze_archive_hygiene(*, max_lines: int = 4000, stale_threshold: float = 2.5) -> Dict[str, Any]:
    """
    Scan archive tail; mark prune candidates (never deletes).
    """
    p = archive_path()
    if not p.is_file():
        return {
            "candidates_for_prune": [],
            "reinforced": 0,
            "stale": 0,
            "contradicted_hits": 0,
            "duplicate_clustered": 0,
        }
    lines: List[str] = []
    try:
        raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = raw[-max_lines:]
    except Exception:
        return {
            "candidates_for_prune": [],
            "reinforced": 0,
            "stale": 0,
            "contradicted_hits": 0,
            "duplicate_clustered": 0,
        }

    by_id: Dict[str, List[float]] = {}
    by_norm: Dict[str, List[str]] = {}
    contradicted = 0
    for ln in lines:
        try:
            o = json.loads(ln)
        except Exception:
            continue
        rec = o.get("record") or {}
        rid = str(rec.get("id") or "")
        if not rid:
            continue
        by_id.setdefault(rid, []).append(float(o.get("ts") or 0))
        body = str((rec.get("raw_text") or ""))[:500].lower().strip()
        nk = body[:100] if body else rid
        by_norm.setdefault(nk, []).append(rid[:48])
        cm = (o.get("archive_meta") or {}).get("contradiction_count") or 0
        if cm:
            contradicted += 1

    duplicate_clustered = sum(1 for _k, ids in by_norm.items() if len(set(ids)) >= 2)

    now = time.time()
    candidates: List[Dict[str, Any]] = []
    reinforced = 0
    stale = 0
    for rid, tss in by_id.items():
        tss.sort()
        first, last = tss[0], tss[-1]
        if len(tss) >= 2:
            reinforced += 1
        age_days = (now - last) / 86400.0
        if age_days > stale_threshold and len(tss) > 3:
            stale += 1
            candidates.append(
                {
                    "record_id": rid[:48],
                    "reason": "idle_long_frequent_archives",
                    "last_ts": last,
                    "archive_hits": len(tss),
                }
            )

    for nk, ids in by_norm.items():
        uids = list(dict.fromkeys(ids))
        if len(uids) >= 3:
            candidates.append(
                {
                    "record_id": (uids[0] if uids else "")[:48],
                    "reason": "duplicate_cluster",
                    "cluster_key_preview": nk[:80],
                    "distinct_ids": len(uids),
                }
            )

    logger.info(
        "[Archive] candidates_for_prune=%s reinforced=%s stale=%s contradicted_lines=%s duplicate_clustered=%s",
        len(candidates),
        reinforced,
        stale,
        contradicted,
        duplicate_clustered,
    )
    return {
        "candidates_for_prune": candidates[:200],
        "reinforced": reinforced,
        "stale": stale,
        "contradicted_hits": contradicted,
        "duplicate_clustered": duplicate_clustered,
    }


def archive_matched_buckets(
    records: List[IngestedRecordDict],
    rel_map: Dict[str, Dict[str, Any]],
    *,
    threshold: float,
    session_id: str,
    cfg: Dict[str, Any],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        rid = str(r.get("id") or "")
        sc = float((rel_map.get(rid) or {}).get("total_score") or (rel_map.get(rid) or {}).get("score") or 0.0)
        if sc < threshold:
            continue
        topic = topic_bucket_for_record(r)
        n = append_archived([r], topic=topic, relevance=sc, session_id=session_id, cfg=cfg)
        counts[topic] = counts.get(topic, 0) + n
    if counts:
        logger.info("[Archive] buckets=%s", counts)
    hy = analyze_archive_hygiene()
    logger.info(
        "[Archive] hygiene prune_candidates=%s",
        len(hy.get("candidates_for_prune") or []),
    )
    return counts
