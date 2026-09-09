# project_guardian/local_ai_selfbuild_retrieve.py
"""
Retrieve top similar chunks from Elysia's self-build corpus (f32 embeddings + index + rag text)
for injection into unified LLM calls (autonomy-safe and planner-style tasks).
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)
_SELFBUILD_ARTIFACT_REBUILD_COOLDOWN_SEC = 600.0
_last_selfbuild_artifact_rebuild_attempt_ts = 0.0


def _selfbuild_embed_model_from_cfg(cfg: Dict[str, Any]) -> str:
    return (
        str(cfg.get("local_ai_selfbuild_embed_model") or "").strip()
        or (os.environ.get("ELYSIA_SELFBUILD_EMBED_MODEL") or "").strip()
    )


def _selfbuild_embed_failure_cooldown_sec(cfg: Dict[str, Any]) -> float:
    try:
        raw = float(cfg.get("local_ai_selfbuild_embed_failure_cooldown_sec", 600.0))
    except (TypeError, ValueError):
        raw = 600.0
    return max(0.0, min(86400.0, raw))


def _parse_selfbuild_utc_iso_epoch(value: Any) -> float:
    if not isinstance(value, str) or not value.strip():
        return 0.0
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    except ValueError:
        return 0.0


def _recent_selfbuild_embed_failure(root: Path, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cooldown = _selfbuild_embed_failure_cooldown_sec(cfg)
    if cooldown <= 0:
        return None
    man_path = root / "manifest.json"
    if not man_path.is_file():
        return None
    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    emb = manifest.get("chunk_embeddings")
    if not isinstance(emb, dict) or emb.get("ok") is not False:
        return None
    try:
        rows_appended = int(emb.get("rows_appended") or 0)
        errors = int(emb.get("errors") or 0)
    except (TypeError, ValueError):
        return None
    if rows_appended > 0 or errors <= 0:
        return None
    current_model = _selfbuild_embed_model_from_cfg(cfg)
    failed_model = str(emb.get("model") or "").strip()
    if current_model and failed_model and failed_model != current_model:
        return None
    updated_epoch = _parse_selfbuild_utc_iso_epoch(emb.get("updated_at"))
    if updated_epoch <= 0:
        return None
    age = max(0.0, time.time() - updated_epoch)
    remaining = cooldown - age
    if remaining <= 0:
        return None
    return {
        "attempted": False,
        "reason": "recent_embed_failure",
        "cooldown_remaining_sec": round(remaining, 1),
        "embed_result": {
            "ok": False,
            "reason": str(emb.get("reason") or "previous_embed_failure"),
            "model": failed_model,
            "rows_appended": rows_appended,
            "errors": errors,
            "pending_seen": emb.get("pending_seen"),
            "updated_at": emb.get("updated_at"),
        },
    }


def _maybe_rebuild_selfbuild_artifacts(
    *,
    storage_path: Path,
    cfg: Dict[str, Any],
    idx_path: Path,
    bin_path: Path,
    rag_path: Path,
) -> Dict[str, Any]:
    """Best-effort on-demand rebuild when retrieval artifacts are missing."""
    global _last_selfbuild_artifact_rebuild_attempt_ts
    now = time.time()
    if (now - _last_selfbuild_artifact_rebuild_attempt_ts) < _SELFBUILD_ARTIFACT_REBUILD_COOLDOWN_SEC:
        return {"attempted": False, "reason": "cooldown"}
    _last_selfbuild_artifact_rebuild_attempt_ts = now
    corpus_dir = storage_path / "local_ai_selfbuild"
    if not corpus_dir.is_dir():
        return {
            "attempted": False,
            "reason": "no_corpus_dir",
            "has_index": idx_path.is_file(),
            "has_bin": bin_path.is_file(),
            "has_rag": rag_path.is_file(),
        }
    if rag_path.is_file() and (not idx_path.is_file() or not bin_path.is_file()):
        recent_failure = _recent_selfbuild_embed_failure(corpus_dir, cfg)
        if recent_failure:
            recent_failure.update(
                {
                    "has_index": idx_path.is_file(),
                    "has_bin": bin_path.is_file(),
                    "has_rag": rag_path.is_file(),
                }
            )
            return recent_failure
    try:
        from .local_ai_selfbuild_corpus import (
            export_selfbuild_chunk_embeddings,
            rebuild_local_ai_selfbuild_rag_chunks,
        )

        rag_result = rebuild_local_ai_selfbuild_rag_chunks(storage_path, cfg)
        emb_result = export_selfbuild_chunk_embeddings(storage_path, cfg)
        return {
            "attempted": True,
            "rag_result": rag_result,
            "embed_result": emb_result,
            "has_index": idx_path.is_file(),
            "has_bin": bin_path.is_file(),
            "has_rag": rag_path.is_file(),
        }
    except Exception as e:
        return {"attempted": True, "reason": f"exception:{str(e)[:180]}"}


def effective_selfbuild_rag_inject_params(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clamp ``local_ai_selfbuild_rag_inject_*`` keys the same way as retrieval.

    Use for ``selfbuild_rag`` meta, traces, and operator UI so tuning is visible even when retrieval skips.
    """
    try:
        top_k = int(cfg.get("local_ai_selfbuild_rag_inject_top_k", 5))
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(12, top_k))
    try:
        max_rows = int(cfg.get("local_ai_selfbuild_rag_inject_max_index_rows", 800))
    except (TypeError, ValueError):
        max_rows = 800
    max_rows = max(50, min(5000, max_rows))
    try:
        max_chars = int(cfg.get("local_ai_selfbuild_rag_inject_max_chars", 3200))
    except (TypeError, ValueError):
        max_chars = 3200
    max_chars = max(400, min(12000, max_chars))
    try:
        min_score = float(cfg.get("local_ai_selfbuild_rag_inject_min_score", 0.12))
    except (TypeError, ValueError):
        min_score = 0.12
    min_score = max(0.0, min(0.95, min_score))
    try:
        timeout = float(cfg.get("local_ai_selfbuild_rag_inject_embed_timeout_sec", 45))
    except (TypeError, ValueError):
        timeout = 45.0
    timeout = max(8.0, min(180.0, timeout))
    return {
        "top_k": top_k,
        "max_chars": max_chars,
        "max_index_rows": max_rows,
        "min_score": round(min_score, 6),
        "embed_timeout_sec": round(timeout, 3),
    }


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _load_rag_chunk_table(rag_path: Path, *, max_lines: int = 8000) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not rag_path.is_file():
        return out
    try:
        raw = rag_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    lines = [ln for ln in raw.splitlines() if ln.strip()][-max_lines:]
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        cid = row.get("chunk_id")
        if isinstance(cid, str) and cid:
            out[cid] = row
    return out


def _should_inject_selfbuild_rag(
    *,
    cfg: Dict[str, Any],
    require_autonomy_safe_reasoning: bool,
    route_task_type: str,
    skip_capability_preamble: bool,
    prompt_extra: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Return (allow, skip_reason). skip_reason is empty when allow is True; otherwise a short stable token
    for logs and meta (e.g. ``disabled``, ``task_type_excluded``).
    """
    if not bool(cfg.get("local_ai_selfbuild_rag_inject_enabled", False)):
        return False, "disabled"
    tt = str(prompt_extra.get("task_type") or "").strip().lower()
    if tt in ("compress_with_llm", "context_compression", "context_structuring", "prompt_packet"):
        return False, "task_type_excluded"
    if require_autonomy_safe_reasoning:
        return True, ""
    if skip_capability_preamble:
        return False, "structured_skip_preamble"
    if route_task_type in {"planning", "reasoning", "longform"}:
        return True, ""
    return False, "route_task_ineligible"


def build_selfbuild_rag_context_block(
    query: str,
    *,
    storage_path: Path,
    cfg: Dict[str, Any],
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Return a markdown-ish block of top matching snippets, or empty string.
    Uses ``chunk_embeddings_index.jsonl`` + ``chunk_embeddings.f32.bin`` + ``rag_chunks_latest.jsonl``.

    If ``stats`` is a dict, it is cleared and filled with retrieval diagnostics (timings, skip reason, scores).
    """
    import time as _time

    from .local_ai_selfbuild_corpus import (
        CHUNK_EMBEDDINGS_F32,
        CHUNK_EMBEDDINGS_INDEX,
        RAG_CHUNKS_FILENAME,
        read_embedding_from_index_row,
    )
    from .context_pipeline.embedding_backend import _embed_ollama_multi_input

    eff = effective_selfbuild_rag_inject_params(cfg)
    top_k = int(eff["top_k"])
    max_rows = int(eff["max_index_rows"])
    max_chars = int(eff["max_chars"])
    min_score = float(eff["min_score"])
    timeout = float(eff["embed_timeout_sec"])

    def _stat(**kwargs: Any) -> None:
        if stats is not None:
            stats.clear()
            stats.update(eff)
            stats.update(kwargs)

    t_all = _time.perf_counter()
    q = (query or "").strip()
    if len(q) < 12:
        _stat(ok=False, skip="query_too_short", query_chars=len(q))
        return ""

    model = (
        str(cfg.get("local_ai_selfbuild_embed_model") or "").strip()
        or (os.environ.get("ELYSIA_SELFBUILD_EMBED_MODEL") or "").strip()
    )
    if not model:
        _stat(ok=False, skip="no_embed_model")
        return ""

    root = storage_path / "local_ai_selfbuild"
    idx_path = root / CHUNK_EMBEDDINGS_INDEX
    bin_path = root / CHUNK_EMBEDDINGS_F32
    rag_path = root / RAG_CHUNKS_FILENAME
    if not idx_path.is_file() or not bin_path.is_file() or not rag_path.is_file():
        rebuild_meta = _maybe_rebuild_selfbuild_artifacts(
            storage_path=storage_path,
            cfg=cfg,
            idx_path=idx_path,
            bin_path=bin_path,
            rag_path=rag_path,
        )
        if idx_path.is_file() and bin_path.is_file() and rag_path.is_file():
            logger.info(
                "[SelfbuildRAG] recovered missing artifacts via on-demand rebuild (attempted=%s)",
                rebuild_meta.get("attempted"),
            )
        else:
            logger.info(
                "[SelfbuildRAG] artifacts missing has_index=%s has_bin=%s has_rag=%s rebuild=%s",
                idx_path.is_file(),
                bin_path.is_file(),
                rag_path.is_file(),
                rebuild_meta,
            )
            _stat(
                ok=False,
                skip="missing_artifacts",
                has_index=idx_path.is_file(),
                has_bin=bin_path.is_file(),
                has_rag=rag_path.is_file(),
                rebuild=rebuild_meta,
            )
            return ""

    t_embed = _time.perf_counter()
    q_emb = _embed_ollama_multi_input([q[:12000]], model, timeout=timeout)
    embed_ms = round((_time.perf_counter() - t_embed) * 1000.0, 2)
    qv = q_emb[0] if q_emb else None
    if not qv:
        _stat(ok=False, skip="query_embed_empty", embed_model=model, embed_ms=embed_ms)
        return ""

    id_to_row = _load_rag_chunk_table(rag_path)
    try:
        idx_lines = idx_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        _stat(ok=False, skip="index_read_error", embed_ms=embed_ms, embed_model=model)
        return ""
    idx_lines = [ln for ln in idx_lines if ln.strip()][-max_rows:]

    t_scan = _time.perf_counter()
    scored: List[Tuple[float, Dict[str, Any], List[float]]] = []
    for line in idx_lines:
        try:
            meta = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(meta, dict):
            continue
        cid = meta.get("chunk_id")
        if not isinstance(cid, str) or not cid:
            continue
        vec = read_embedding_from_index_row(root, meta)
        if not vec:
            continue
        sc = _cosine(qv, vec)
        if sc < min_score:
            continue
        scored.append((sc, meta, vec))

    scored.sort(key=lambda x: -x[0])
    picked = scored[:top_k]
    scan_ms = round((_time.perf_counter() - t_scan) * 1000.0, 2)

    parts: List[str] = []
    used = 0
    sims_used: List[float] = []
    for sc, meta, _ in picked:
        cid = str(meta.get("chunk_id") or "")
        row = id_to_row.get(cid) or {}
        title = str(meta.get("title") or row.get("title") or "")[:200]
        body = str(row.get("text") or "")[:1800]
        if not body.strip():
            continue
        line = f"- (sim={sc:.3f}) **{title}** — {body.strip()}"
        if used + len(line) + 2 > max_chars:
            break
        parts.append(line)
        sims_used.append(float(sc))
        used += len(line) + 1

    total_ms = round((_time.perf_counter() - t_all) * 1000.0, 2)

    if not parts:
        max_sim = float(picked[0][0]) if picked else 0.0
        _stat(
            ok=False,
            skip="no_chunk_text_or_budget" if picked else "no_scores_above_min",
            embed_ms=embed_ms,
            scan_ms=scan_ms,
            total_ms=total_ms,
            index_lines=len(idx_lines),
            candidates_after_min=len(scored),
            max_sim_any=max_sim,
            embed_model=model,
        )
        return ""

    _stat(
        ok=True,
        skip="",
        chunks=len(parts),
        max_sim=float(sims_used[0]) if sims_used else 0.0,
        sims_rounded=[round(s, 4) for s in sims_used[:8]],
        index_lines=len(idx_lines),
        embed_ms=embed_ms,
        scan_ms=scan_ms,
        total_ms=total_ms,
        chars=used,
        embed_model=model,
    )

    return (
        "[Elysia local self-build RAG — snippets from her collected corpus; verify facts; do not cite as law]\n"
        + "\n".join(parts)
    )


def maybe_prepend_selfbuild_rag_system_message(
    messages: List[Dict[str, str]],
    *,
    user_text: str,
    guardian: Any,
    require_autonomy_safe_reasoning: bool,
    route_task_type: str,
    skip_capability_preamble: bool,
    prompt_extra: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """
    Prepend one system message with retrieval context when policy allows.

    Returns ``(messages_out, meta)``. ``meta`` always includes ``applied`` (bool) and ``skip`` (reason token
    or empty string). When retrieval runs, merge fields from ``build_selfbuild_rag_context_block`` stats.
    """
    base_meta: Dict[str, Any] = {"applied": False, "skip": ""}
    try:
        from .auto_learning import get_learned_storage_path, load_learning_config

        cfg = load_learning_config()
        pe = prompt_extra or {}
        allow, skip = _should_inject_selfbuild_rag(
            cfg=cfg,
            require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
            route_task_type=route_task_type,
            skip_capability_preamble=skip_capability_preamble,
            prompt_extra=pe,
        )
        base_meta.update(effective_selfbuild_rag_inject_params(cfg))
        if not allow:
            base_meta["skip"] = skip or "policy_denied"
            return messages, base_meta

        storage = get_learned_storage_path()
        rstats: Dict[str, Any] = {}
        block = build_selfbuild_rag_context_block(
            user_text, storage_path=storage, cfg=cfg, stats=rstats
        )
        base_meta.update(rstats)
        base_meta["route_task_type"] = route_task_type
        if not block.strip():
            base_meta["skip"] = str(rstats.get("skip") or "empty_block")
            return messages, base_meta
        base_meta["applied"] = True
        base_meta["skip"] = ""
        return [{"role": "system", "content": block}] + list(messages), base_meta
    except Exception as e:
        logger.debug("[SelfbuildRAG] prepend skipped: %s", e)
        base_meta["skip"] = "exception"
        base_meta["error"] = str(e)[:300]
        return messages, base_meta
