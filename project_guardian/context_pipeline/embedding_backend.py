# project_guardian/context_pipeline/embedding_backend.py
"""Local semantic similarity: Ollama /api/embeddings (preferred), optional sentence-transformers, TF-IDF fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_EMBED_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_ST_MODEL = None  # lazy sentence-transformers
_ST_PATH_DISABLED: bool = False
_ST_FAILURE_LOGGED: bool = False


def _cache_key(model: str, text: str) -> str:
    h = hashlib.sha256(f"{model}|{text[:8000]}".encode("utf-8", errors="replace")).hexdigest()
    return h


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _ollama_base() -> str:
    raw = (os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip()
    if "/api/" in raw:
        raw = raw.split("/api/")[0].rstrip("/")
    return raw.rstrip("/") or "http://127.0.0.1:11434"


def _coerce_ollama_embedding_rows(data: Dict[str, Any], expected: int) -> Optional[List[List[float]]]:
    """Normalize Ollama embed/embeddings responses into one vector per input."""
    try:
        embs = data.get("embeddings")
        if isinstance(embs, list) and embs:
            if expected == 1 and all(isinstance(x, (int, float)) for x in embs):
                return [[float(x) for x in embs]]
            if len(embs) == expected and all(isinstance(row, list) and row for row in embs):
                return [[float(x) for x in row] for row in embs]
        emb = data.get("embedding")
        if expected == 1 and isinstance(emb, list) and emb:
            return [[float(x) for x in emb]]
    except (TypeError, ValueError):
        return None
    return None


def _embed_ollama_multi_input(texts: List[str], model: str, timeout: float) -> List[Optional[List[float]]]:
    """Ollama embeddings, returning a list parallel to texts."""
    try:
        import requests
    except ImportError:
        return [None] * len(texts)
    if not texts:
        return []
    base = _ollama_base()
    inputs = [t[:12000] for t in texts]
    try:
        r = requests.post(f"{base}/api/embed", json={"model": model, "input": inputs}, timeout=timeout)
        r.raise_for_status()
        rows = _coerce_ollama_embedding_rows(r.json(), len(inputs))
        if rows:
            return rows
    except Exception as e:
        logger.debug("[RelevanceMap] ollama_embed_batch_fail n=%s err=%s", len(texts), e)

    out: List[Optional[List[float]]] = []
    for text in inputs:
        try:
            r = requests.post(f"{base}/api/embeddings", json={"model": model, "prompt": text}, timeout=timeout)
            r.raise_for_status()
            rows = _coerce_ollama_embedding_rows(r.json(), 1)
            out.append(rows[0] if rows else None)
        except Exception as e:
            logger.debug("[RelevanceMap] ollama_embed_legacy_fail err=%s", e)
            out.append(None)
    return out


def _embed_ollama_one(text: str, model: str, timeout: float) -> Optional[List[float]]:
    res = _embed_ollama_multi_input([text], model, timeout=timeout)
    return res[0] if res else None


def _st_embeddings_enabled() -> bool:
    v = (os.environ.get("ELYSIA_ENABLE_ST_EMBED_FALLBACK") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _embed_st_model(texts: List[str], model_name: str) -> List[Optional[List[float]]]:
    global _ST_MODEL, _ST_PATH_DISABLED, _ST_FAILURE_LOGGED
    if _ST_PATH_DISABLED or not _st_embeddings_enabled():
        return [None] * len(texts)
    try:
        from sentence_transformers import SentenceTransformer
    except BaseException as e:
        _ST_PATH_DISABLED = True
        if not _ST_FAILURE_LOGGED:
            _ST_FAILURE_LOGGED = True
            logger.warning(
                "[RelevanceMap] sentence_transformers import disabled for this process (%s); "
                "using Ollama/TF-IDF only (set ELYSIA_ENABLE_ST_EMBED_FALLBACK=0 to skip ST silently)",
                type(e).__name__,
            )
        return [None] * len(texts)
    try:
        if _ST_MODEL is None or getattr(_ST_MODEL, "_name", "") != model_name:
            _ST_MODEL = SentenceTransformer(model_name)
            setattr(_ST_MODEL, "_name", model_name)
        vecs = _ST_MODEL.encode([t[:8000] for t in texts], convert_to_numpy=True, show_progress_bar=False)
        return [list(map(float, row)) for row in vecs]
    except BaseException as e:
        _ST_PATH_DISABLED = True
        if not _ST_FAILURE_LOGGED:
            _ST_FAILURE_LOGGED = True
            logger.warning(
                "[RelevanceMap] sentence_transformers encode/load failed; ST path disabled for this process: %s",
                str(e)[:220],
            )
        _ST_MODEL = None
        return [None] * len(texts)


def embed_texts(
    texts: List[str],
    *,
    cfg: Dict[str, Any],
) -> Tuple[str, List[Optional[List[float]]]]:
    """
    Returns (backend_used, embeddings_per_text) same length as texts.
    backend_used: embeddings_ollama | embeddings_st | none
    """
    texts = [(t or "")[:12000] for t in texts]
    if not texts:
        return "none", []

    backend = str(cfg.get("semantic_backend") or "tfidf").lower().strip()
    if backend != "embeddings":
        return "none", [None] * len(texts)

    model = str(cfg.get("embedding_model") or "nomic-embed-text").strip()
    use_cache = bool(cfg.get("embedding_cache_enabled", True))
    batch = max(1, int(cfg.get("embedding_batch_size") or 8))
    timeout = float(cfg.get("embedding_http_timeout_sec") or 30.0)

    provider = str(cfg.get("embedding_provider") or "ollama").lower().strip()

    if provider == "sentence_transformers":
        res = _embed_st_model(texts, model)
        if any(v is not None for v in res):
            return "embeddings_st", res

    max_sz = int(cfg.get("embedding_cache_max_entries") or 4096)
    out_vecs: List[Optional[List[float]]] = [None] * len(texts)
    i = 0
    while i < len(texts):
        tx0 = texts[i]
        ck0 = _cache_key(model, tx0)
        if use_cache and ck0 in _EMBED_CACHE:
            out_vecs[i] = _EMBED_CACHE[ck0]
            _EMBED_CACHE.move_to_end(ck0)
            i += 1
            continue
        run: List[str] = []
        idxs: List[int] = []
        while i < len(texts) and len(run) < batch:
            tx = texts[i]
            ck = _cache_key(model, tx)
            if use_cache and ck in _EMBED_CACHE:
                break
            run.append(tx)
            idxs.append(i)
            i += 1
        if not run:
            continue
        multi = _embed_ollama_multi_input(run, model, timeout=timeout)
        if len(multi) != len(run) or all(v is None for v in multi):
            for j, tx in zip(idxs, run):
                v = _embed_ollama_one(tx, model, timeout=timeout)
                out_vecs[j] = v
                if v and use_cache:
                    _EMBED_CACHE[_cache_key(model, tx)] = v
                    while len(_EMBED_CACHE) > max_sz:
                        _EMBED_CACHE.popitem(last=False)
        else:
            for j, v in zip(idxs, multi):
                out_vecs[j] = v
                if v and use_cache:
                    tx = texts[j]
                    _EMBED_CACHE[_cache_key(model, tx)] = v
                    while len(_EMBED_CACHE) > max_sz:
                        _EMBED_CACHE.popitem(last=False)
    if any(v is not None for v in out_vecs):
        return "embeddings_ollama", out_vecs
    return "none", [None] * len(texts)


def max_cosine_to_queries(
    record_embedding: Optional[List[float]],
    query_embeddings: List[Optional[List[float]]],
    threshold: float,
) -> float:
    if not record_embedding:
        return 0.0
    best = 0.0
    for q in query_embeddings:
        if not q:
            continue
        best = max(best, _cosine(record_embedding, q))
    return best if best >= threshold else best * 0.85  # soft below threshold
