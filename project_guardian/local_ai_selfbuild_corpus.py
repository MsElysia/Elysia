# project_guardian/local_ai_selfbuild_corpus.py
"""
Capture high-signal learning rows into a durable corpus under the learned storage path.

Purpose: give Elysia a structured, append-only dataset she can later use for RAG, eval notes,
local stack documentation, or fine-tuning prep — all oriented toward *her own* on-machine AI
(Ollama, quantisation, RAG, agents) rather than generic web noise.
"""

from __future__ import annotations

import array
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

CORPUS_DIRNAME = "local_ai_selfbuild"
CORPUS_FILE_PREFIX = "corpus_"
MANIFEST_NAME = "manifest.json"
RAG_CHUNKS_FILENAME = "rag_chunks_latest.jsonl"
# Legacy: full vectors inline (large). Preferred: f32_index (binary vectors + JSONL index).
CHUNK_EMBEDDINGS_FILENAME = "chunk_embeddings.jsonl"
CHUNK_EMBEDDINGS_INDEX = "chunk_embeddings_index.jsonl"
CHUNK_EMBEDDINGS_F32 = "chunk_embeddings.f32.bin"
_DEFAULT_KEYWORD_FRAGMENTS: Tuple[str, ...] = (
    "ollama",
    "gguf",
    "quantize",
    "quantisation",
    "quantization",
    "lora",
    "fine-tun",
    "finetun",
    "local llm",
    "on-device",
    "on device",
    "edge inference",
    "rag",
    "retrieval augmented",
    "vector db",
    "vector database",
    "embedding",
    "llama.cpp",
    "vllm",
    "mlx",
    "model card",
    "eval harness",
    "benchmark",
    "inference server",
    "self-hosted",
    "self hosted",
    "small language model",
    "slm",
    "agent architecture",
    "tool calling",
    "function calling",
    "guardrails",
    "alignment",
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_keywords(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("local_ai_selfbuild_keywords")
    if isinstance(raw, list) and any(str(x).strip() for x in raw):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    return list(_DEFAULT_KEYWORD_FRAGMENTS)


def _normalize_selfbuild_topics(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("local_ai_selfbuild_topics")
    if isinstance(raw, list) and raw:
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    return [
        "local llm",
        "ollama",
        "rag",
        "model quantization",
        "ai agent",
        "on-device inference",
    ]


def _topic_hits(blob: str, topic_phrases: Sequence[str]) -> List[str]:
    b = blob.lower()
    hits: List[str] = []
    for ph in topic_phrases:
        p = ph.strip().lower()
        if len(p) < 3:
            continue
        if p in b:
            hits.append(ph)
    return hits


def _keyword_hits(blob: str, keywords: Sequence[str]) -> List[str]:
    b = blob.lower()
    out: List[str] = []
    for kw in keywords:
        k = kw.strip().lower()
        if len(k) < 3:
            continue
        if k in b:
            out.append(kw)
    return out


def _row_fingerprint(title: str, compressed: str, url: str) -> str:
    base = f"{title}|{compressed[:400]}|{url}"
    return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _load_recent_fingerprints(path: Path, max_lines: int = 400) -> set:
    fps: set = set()
    if not path.is_file():
        return fps
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-max_lines:]:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            fp = obj.get("fingerprint")
            if isinstance(fp, str) and fp:
                fps.add(fp)
    except OSError as e:
        logger.debug("[local_ai_selfbuild] fingerprint scan: %s", e)
    return fps


def _update_manifest(root: Path, *, added: int, last_signals: List[str]) -> None:
    man_path = root / MANIFEST_NAME
    prev: Dict[str, Any] = {}
    if man_path.is_file():
        try:
            prev = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
    prev["updated_at"] = _utc_iso()
    prev["total_rows"] = int(prev.get("total_rows") or 0) + added
    if last_signals:
        sig_hist = prev.get("signal_histogram")
        if not isinstance(sig_hist, dict):
            sig_hist = {}
        for s in last_signals:
            sig_hist[s] = int(sig_hist.get(s) or 0) + 1
        prev["signal_histogram"] = sig_hist
    try:
        root.mkdir(parents=True, exist_ok=True)
        man_path.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.debug("[local_ai_selfbuild] manifest write: %s", e)


def maybe_append_local_ai_selfbuild_row(
    *,
    storage_path: Path,
    item: Dict[str, Any],
    score_info: Dict[str, Any],
    session_topics: List[str],
    cfg: Dict[str, Any],
    recent_fingerprints: Optional[set] = None,
) -> bool:
    """
    If this admitted row looks useful for Elysia's future *local* AI stack, append one JSONL record.

    Returns True when a row was written.
    """
    if not bool(cfg.get("local_ai_selfbuild_enabled", True)):
        return False
    try:
        min_rel = int(cfg.get("local_ai_selfbuild_min_relevance", 2))
    except (TypeError, ValueError):
        min_rel = 2
    min_rel = max(1, min(10, min_rel))
    relevance = int(score_info.get("relevance") or 0)
    if relevance < min_rel:
        return False

    keywords = _normalize_keywords(cfg)
    self_topics = _normalize_selfbuild_topics(cfg)
    title = str(item.get("title") or "")[:400]
    raw_text = str(item.get("text") or "")[:8000]
    compressed = str(item.get("compressed") or "")[:2000]
    url = str(item.get("url") or "")[:800]
    src = str(item.get("source") or "unknown").lower()
    blob = " ".join(
        x
        for x in (
            title,
            raw_text[:4000],
            compressed,
            " ".join(str(t) for t in (session_topics or [])[:24]),
        )
        if x
    )
    kw_hits = _keyword_hits(blob, keywords)
    topic_hits = _topic_hits(blob, self_topics)
    if not kw_hits and not topic_hits:
        return False

    root = storage_path / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_file = root / f"{CORPUS_FILE_PREFIX}{day}.jsonl"
    fp = _row_fingerprint(title, compressed, url)
    if recent_fingerprints is not None:
        if fp in recent_fingerprints:
            return False
        recent_fingerprints.add(fp)
    elif fp in _load_recent_fingerprints(out_file):
        return False

    record = {
        "captured_at": _utc_iso(),
        "fingerprint": fp,
        "source": src,
        "title": title,
        "url": url or None,
        "text_excerpt": raw_text[:2400],
        "compressed": compressed[:1600],
        "relevance": relevance,
        "session_topics_sample": [str(t) for t in (session_topics or [])[:12]],
        "signals": sorted(set(kw_hits + topic_hits))[:40],
        "purpose_tags": [
            "local_ai_selfbuild",
            "training_corpus_candidate",
        ],
    }
    try:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("[local_ai_selfbuild] append failed: %s", e)
        return False

    signals = record["signals"] if isinstance(record["signals"], list) else []
    _update_manifest(root, added=1, last_signals=signals[:12])
    logger.info(
        "[local_ai_selfbuild] captured row fp=%s source=%s signals=%s",
        fp,
        src,
        ",".join(signals[:6]) or "-",
    )
    return True


def _squash_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _chunk_text(text: str, *, size: int, overlap: int, min_chars: int) -> List[str]:
    """Fixed windows with overlap; drops tiny fragments."""
    t = _squash_ws(text)
    if len(t) < min_chars:
        return []
    if len(t) <= size:
        return [t]
    out: List[str] = []
    start = 0
    n = len(t)
    while start < n:
        end = min(n, start + size)
        piece = t[start:end].strip()
        if len(piece) >= min_chars:
            out.append(piece)
        if end >= n:
            break
        start = max(0, end - overlap)
    return out


def estimate_selfbuild_corpus_mission_alignment(
    storage_path: Path,
    cfg: Dict[str, Any],
    *,
    max_rows: int = 8000,
) -> Dict[str, Any]:
    """
    Compare existing corpus rows against **current** self-build keywords/topics in ``cfg``.

    Rows collected under an older config may no longer match; this estimates how many would be
    dropped if you pruned non-aligning rows (see operator Insights ``mission_clarity`` bundle).
    """
    root = storage_path / CORPUS_DIRNAME
    out: Dict[str, Any] = {
        "corpus_dir_exists": root.is_dir(),
        "rows_scanned": 0,
        "aligned_rows": 0,
        "misaligned_rows": 0,
        "alignment_ratio": 0.0,
        "keywords_used_count": 0,
        "topics_used_count": 0,
    }
    if not root.is_dir():
        out["note"] = "No local_ai_selfbuild corpus directory yet."
        return out

    keywords = _normalize_keywords(cfg)
    topics = _normalize_selfbuild_topics(cfg)
    out["keywords_used_count"] = len(keywords)
    out["topics_used_count"] = len(topics)

    max_rows = max(50, min(50_000, int(max_rows)))
    scanned = 0
    aligned = 0
    files = sorted(root.glob(f"{CORPUS_FILE_PREFIX}*.jsonl"), key=lambda p: p.name, reverse=True)
    for fp in files:
        if scanned >= max_rows:
            break
        try:
            raw = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for line in reversed(lines):
            if scanned >= max_rows:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or not obj.get("fingerprint"):
                continue
            scanned += 1
            title = str(obj.get("title") or "")
            compressed = str(obj.get("compressed") or "")
            excerpt = str(obj.get("text_excerpt") or "")
            blob = " ".join(x for x in (title, excerpt[:4000], compressed) if x)
            kw_h = _keyword_hits(blob, keywords)
            tp_h = _topic_hits(blob, topics)
            if kw_h or tp_h:
                aligned += 1
            else:
                pass
    misaligned = scanned - aligned
    out["rows_scanned"] = scanned
    out["aligned_rows"] = aligned
    out["misaligned_rows"] = misaligned
    out["alignment_ratio"] = round((aligned / scanned), 4) if scanned else 0.0
    if misaligned and scanned:
        out["prune_hint"] = (
            f"{misaligned} row(s) do not match current keywords/topics — likely from an older config; "
            "optional prune would remove them before the next RAG rebuild."
        )
    return out


def _load_recent_corpus_records(root: Path, max_records: int) -> List[Dict[str, Any]]:
    """Newest corpus JSONL files first; newest lines within each file last (stable read order)."""
    max_records = max(1, min(5000, int(max_records)))
    rows: List[Dict[str, Any]] = []
    files = sorted(root.glob(f"{CORPUS_FILE_PREFIX}*.jsonl"), key=lambda p: p.name, reverse=True)
    for fp in files:
        if len(rows) >= max_records:
            break
        try:
            raw = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            logger.debug("[local_ai_selfbuild] read corpus %s: %s", fp.name, e)
            continue
        file_lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for line in reversed(file_lines):
            if len(rows) >= max_records:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("fingerprint"):
                rows.append(obj)
    return rows


def _merge_manifest_rag_stats(root: Path, stats: Dict[str, Any]) -> None:
    man_path = root / MANIFEST_NAME
    prev: Dict[str, Any] = {}
    if man_path.is_file():
        try:
            prev = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
    prev["rag_export"] = {
        "updated_at": _utc_iso(),
        **stats,
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        man_path.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.debug("[local_ai_selfbuild] manifest rag merge: %s", e)


def rebuild_local_ai_selfbuild_rag_chunks(storage_path: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rebuild ``rag_chunks_latest.jsonl`` from the most recent corpus rows (RAG / embedding prep).

    Writes one JSON object per line: chunk_id, source_fingerprint, text, title, signals, url.
    """
    if not bool(cfg.get("local_ai_selfbuild_rag_export_enabled", True)):
        return {"skipped": True, "reason": "disabled"}
    root = storage_path / CORPUS_DIRNAME
    if not root.is_dir():
        return {"skipped": True, "reason": "no_corpus_dir"}
    try:
        max_rows = int(cfg.get("local_ai_selfbuild_rag_max_corpus_rows", 400))
    except (TypeError, ValueError):
        max_rows = 400
    max_rows = max(20, min(4000, max_rows))
    try:
        chunk_chars = int(cfg.get("local_ai_selfbuild_rag_chunk_chars", 480))
    except (TypeError, ValueError):
        chunk_chars = 480
    chunk_chars = max(180, min(2000, chunk_chars))
    try:
        overlap = int(cfg.get("local_ai_selfbuild_rag_chunk_overlap", 72))
    except (TypeError, ValueError):
        overlap = 72
    overlap = max(0, min(chunk_chars // 2, overlap))
    try:
        min_chunk = int(cfg.get("local_ai_selfbuild_rag_min_chunk_chars", 48))
    except (TypeError, ValueError):
        min_chunk = 48
    min_chunk = max(24, min(200, min_chunk))

    records = _load_recent_corpus_records(root, max_rows)
    if not records:
        return {"skipped": True, "reason": "no_corpus_rows"}

    seen_chunk_ids: set = set()
    lines_out: List[str] = []
    for rec in records:
        title = str(rec.get("title") or "")[:400]
        body = " ".join(
            str(x)
            for x in (
                title,
                rec.get("compressed"),
                rec.get("text_excerpt"),
            )
            if x
        )
        body = _squash_ws(body)
        if len(body) < min_chunk:
            continue
        src_fp = str(rec.get("fingerprint") or "")[:32]
        signals = rec.get("signals") if isinstance(rec.get("signals"), list) else []
        url = rec.get("url")
        for chunk in _chunk_text(body, size=chunk_chars, overlap=overlap, min_chars=min_chunk):
            cid = hashlib.sha256(chunk.encode("utf-8", errors="ignore")).hexdigest()[:32]
            if cid in seen_chunk_ids:
                continue
            seen_chunk_ids.add(cid)
            row = {
                "chunk_id": cid,
                "source_fingerprint": src_fp,
                "title": title[:240],
                "text": chunk,
                "signals": signals[:24],
                "url": url,
                "captured_at": rec.get("captured_at") or _utc_iso(),
            }
            lines_out.append(json.dumps(row, ensure_ascii=False))

    if not lines_out:
        return {"skipped": True, "reason": "no_chunks_generated", "corpus_rows_scanned": len(records)}

    out_path = root / RAG_CHUNKS_FILENAME
    tmp = out_path.with_suffix(".jsonl.tmp")
    payload = "\n".join(lines_out) + "\n"
    last_error: Optional[OSError] = None
    for attempt in range(1, 4):
        try:
            root.mkdir(parents=True, exist_ok=True)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(out_path)
            last_error = None
            break
        except OSError as e:
            last_error = e
            logger.warning(
                "[local_ai_selfbuild] rag chunk export attempt=%d failed: %s",
                attempt,
                e,
            )
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if attempt < 3:
                time.sleep(0.25 * attempt)
    if last_error is not None:
        return {"ok": False, "error": str(last_error)}

    stats = {
        "corpus_rows_scanned": len(records),
        "chunks_written": len(lines_out),
        "chunk_chars": chunk_chars,
        "overlap": overlap,
        "output": str(out_path),
    }
    _merge_manifest_rag_stats(root, stats)
    logger.info(
        "[local_ai_selfbuild] RAG export: corpus_rows=%d chunks=%d -> %s",
        len(records),
        len(lines_out),
        out_path.name,
    )
    return {"ok": True, **stats}


def should_run_selfbuild_rag_export(
    cfg: Dict[str, Any],
    storage_path: Path,
    *,
    corpus_rows_appended_session: int,
) -> bool:
    if not bool(cfg.get("local_ai_selfbuild_rag_export_enabled", True)):
        return False
    root = storage_path / CORPUS_DIRNAME
    if not any(root.glob(f"{CORPUS_FILE_PREFIX}*.jsonl")):
        return False
    if corpus_rows_appended_session > 0:
        return True
    if bool(cfg.get("local_ai_selfbuild_rag_export_each_run", False)):
        return True
    rag_path = root / RAG_CHUNKS_FILENAME
    return not rag_path.exists()


def _selfbuild_embed_model(cfg: Dict[str, Any]) -> str:
    return (
        str(cfg.get("local_ai_selfbuild_embed_model") or "").strip()
        or (os.environ.get("ELYSIA_SELFBUILD_EMBED_MODEL") or "").strip()
    )


def _selfbuild_embeddings_enabled(cfg: Dict[str, Any]) -> bool:
    if (os.environ.get("ELYSIA_SELFBUILD_EMBED_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(cfg.get("local_ai_selfbuild_embed_enabled", False))


def _embed_storage_format(cfg: Dict[str, Any]) -> str:
    raw = str(cfg.get("local_ai_selfbuild_embed_storage") or "f32_index").strip().lower()
    if raw in ("jsonl", "inline", "legacy"):
        return "jsonl"
    if raw in ("f32_index", "f32", "binary", "mmap"):
        return "f32_index"
    return "f32_index"


def _load_embedded_chunk_ids_from_path(embed_path: Path, *, max_scan_lines: int = 12000) -> set:
    ids: set = set()
    if not embed_path.is_file():
        return ids
    try:
        raw = embed_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ids
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    for line in lines[-max_scan_lines:]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        cid = obj.get("chunk_id")
        if isinstance(cid, str) and cid:
            ids.add(cid)
    return ids


def _load_embedded_chunk_ids_unified(root: Path) -> set:
    """Union of chunk_ids from binary index and legacy inline-jsonl (migration / dedupe)."""
    ids = set()
    ids |= _load_embedded_chunk_ids_from_path(root / CHUNK_EMBEDDINGS_INDEX)
    ids |= _load_embedded_chunk_ids_from_path(root / CHUNK_EMBEDDINGS_FILENAME)
    return ids


def _append_f32_embedding_batch(
    root: Path,
    model: str,
    items: List[Tuple[Dict[str, Any], List[float]]],
) -> int:
    """Append float32 vectors (little-endian) and one JSON index line per vector. Returns rows written."""
    if not items:
        return 0
    bin_path = root / CHUNK_EMBEDDINGS_F32
    idx_path = root / CHUNK_EMBEDDINGS_INDEX
    root.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(bin_path, "ab") as bf, open(idx_path, "a", encoding="utf-8") as ix:
        for r, vec in items:
            if not vec:
                continue
            dims = len(vec)
            offset = bf.tell()
            try:
                buf = array.array("f", [float(x) for x in vec]).tobytes()
            except (TypeError, ValueError) as e:
                logger.debug("[local_ai_selfbuild] skip bad vector: %s", e)
                continue
            if len(buf) != dims * 4:
                continue
            bf.write(buf)
            rec = {
                "chunk_id": str(r.get("chunk_id") or ""),
                "model": model,
                "dims": dims,
                "offset": offset,
                "length_bytes": len(buf),
                "title": (r.get("title") or "")[:240],
                "signals": r.get("signals") if isinstance(r.get("signals"), list) else [],
                "exported_at": _utc_iso(),
            }
            ix.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return written


def read_embedding_f32(bin_path: Path, offset: int, dims: int) -> Optional[List[float]]:
    """Random read of one float32 vector (dims floats) at byte offset."""
    if dims <= 0 or offset < 0:
        return None
    need = dims * 4
    try:
        with open(bin_path, "rb") as f:
            f.seek(offset)
            raw = f.read(need)
    except OSError:
        return None
    if len(raw) != need:
        return None
    arr = array.array("f")
    arr.frombytes(raw)
    return list(arr)


def read_embedding_from_index_row(root: Path, record: Dict[str, Any]) -> Optional[List[float]]:
    """Load the vector described by one ``chunk_embeddings_index.jsonl`` object."""
    off = record.get("offset")
    dims = record.get("dims")
    if not isinstance(off, int) or not isinstance(dims, int):
        return None
    return read_embedding_f32(root / CHUNK_EMBEDDINGS_F32, off, dims)


def iter_f32_embedding_index(root: Path):
    """Yield index records (dict) from ``chunk_embeddings_index.jsonl`` for streaming consumers."""
    p = root / CHUNK_EMBEDDINGS_INDEX
    if not p.is_file():
        return
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("chunk_id"):
                    yield obj
    except OSError as e:
        logger.debug("[local_ai_selfbuild] iter index: %s", e)


def _merge_manifest_embed_stats(root: Path, stats: Dict[str, Any]) -> None:
    man_path = root / MANIFEST_NAME
    prev: Dict[str, Any] = {}
    if man_path.is_file():
        try:
            prev = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
    prev["chunk_embeddings"] = {"updated_at": _utc_iso(), **stats}
    try:
        root.mkdir(parents=True, exist_ok=True)
        man_path.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.debug("[local_ai_selfbuild] manifest embed merge: %s", e)


def system_ram_used_fraction() -> Optional[float]:
    """Host RAM usage fraction in ``[0, 1]`` for lightweight pressure gating; ``None`` if unknown."""
    try:
        import psutil

        return float(psutil.virtual_memory().percent) / 100.0
    except Exception:
        return None


def _adjust_selfbuild_embed_for_ram_pressure(
    max_new: int,
    batch: int,
    timeout: float,
) -> Tuple[int, int, float, Dict[str, Any]]:
    """
    When system RAM is at/above the configured trigger, shrink embedding batch work so Ollama
    embed calls do not amplify memory / CPU spikes during autonomy.
    """
    meta: Dict[str, Any] = {}
    frac = system_ram_used_fraction()
    if frac is None:
        return max_new, batch, timeout, meta
    try:
        from .monitoring import _load_memory_pressure_config

        mpc = _load_memory_pressure_config()
    except Exception:
        mpc = {}
    try:
        trigger = float(
            mpc.get(
                "selfbuild_embed_ram_trigger_fraction",
                mpc.get("memory_pressure_trigger_fraction", 0.88),
            )
        )
    except (TypeError, ValueError):
        trigger = 0.88
    trigger = max(0.5, min(0.99, trigger))
    if frac < trigger:
        return max_new, batch, timeout, meta
    try:
        cap_chunks = int(mpc.get("selfbuild_embed_max_chunks_when_ram_high", 8))
    except (TypeError, ValueError):
        cap_chunks = 8
    try:
        cap_batch = int(mpc.get("selfbuild_embed_batch_when_ram_high", 2))
    except (TypeError, ValueError):
        cap_batch = 2
    cap_chunks = max(1, min(256, cap_chunks))
    cap_batch = max(1, min(32, cap_batch))
    eff_max = min(max_new, cap_chunks)
    eff_batch = min(batch, cap_batch)
    meta = {
        "ram_pressure_embed_cap": True,
        "ram_used_fraction": round(float(frac), 4),
        "ram_trigger_fraction": round(trigger, 4),
        "embed_max_chunks_requested": max_new,
        "embed_max_chunks_effective": eff_max,
        "embed_batch_requested": batch,
        "embed_batch_effective": eff_batch,
    }
    if eff_max < max_new or eff_batch < batch:
        logger.info(
            "[local_ai_selfbuild] RAM pressure embed cap: used=%.1f%% ≥ trigger=%.1f%% → chunks %d→%d batch %d→%d",
            frac * 100.0,
            trigger * 100.0,
            max_new,
            eff_max,
            batch,
            eff_batch,
        )
    return eff_max, eff_batch, timeout, meta


def should_run_selfbuild_embed_export(
    cfg: Dict[str, Any],
    storage_path: Path,
    *,
    rag_rebuilt_ok: bool,
    corpus_rows_appended_session: int,
) -> bool:
    if not _selfbuild_embeddings_enabled(cfg):
        return False
    if not _selfbuild_embed_model(cfg):
        return False
    root = storage_path / CORPUS_DIRNAME
    rag = root / RAG_CHUNKS_FILENAME
    if not rag.is_file() or rag.stat().st_size == 0:
        return False
    if corpus_rows_appended_session > 0 or rag_rebuilt_ok:
        return True
    if bool(cfg.get("local_ai_selfbuild_embed_each_run", False)):
        return True
    return False


def export_selfbuild_chunk_embeddings(storage_path: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append Ollama /api/embeddings for RAG chunks not yet indexed.

    **Storage formats** (``local_ai_selfbuild_embed_storage``):

    - ``f32_index`` (default): append float32 vectors to ``chunk_embeddings.f32.bin`` and append
      lightweight rows to ``chunk_embeddings_index.jsonl`` (offset, dims, metadata). Scalable and
      stream-friendly.
    - ``jsonl``: legacy ``chunk_embeddings.jsonl`` with full ``embedding`` arrays per line.

    Reuses :func:`project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input`.
    """
    if not _selfbuild_embeddings_enabled(cfg):
        return {"skipped": True, "reason": "embed_disabled"}
    model = _selfbuild_embed_model(cfg)
    if not model:
        return {"skipped": True, "reason": "no_embed_model"}

    root = storage_path / CORPUS_DIRNAME
    rag_path = root / RAG_CHUNKS_FILENAME
    if not rag_path.is_file():
        return {"skipped": True, "reason": "no_rag_chunks_file"}

    fmt = _embed_storage_format(cfg)

    try:
        max_new = int(cfg.get("local_ai_selfbuild_embed_max_chunks_per_run", 24))
    except (TypeError, ValueError):
        max_new = 24
    max_new = max(1, min(256, max_new))
    try:
        batch = int(cfg.get("local_ai_selfbuild_embed_batch_size", 8))
    except (TypeError, ValueError):
        batch = 8
    batch = max(1, min(32, batch))
    try:
        timeout = float(cfg.get("local_ai_selfbuild_embed_timeout_sec", 120))
    except (TypeError, ValueError):
        timeout = 120.0
    timeout = max(15.0, min(600.0, timeout))

    max_new, batch, timeout, ram_embed_meta = _adjust_selfbuild_embed_for_ram_pressure(max_new, batch, timeout)

    already = _load_embedded_chunk_ids_unified(root)

    try:
        from .context_pipeline.embedding_backend import _embed_ollama_multi_input
    except ImportError as e:
        return {"skipped": True, "reason": f"import_error:{e}"}

    pending: List[Dict[str, Any]] = []
    try:
        for line in rag_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            cid = row.get("chunk_id")
            txt = str(row.get("text") or "").strip()
            if not isinstance(cid, str) or not cid or len(txt) < 8:
                continue
            if cid in already:
                continue
            pending.append(row)
    except OSError as e:
        return {"skipped": True, "reason": f"read_rag:{e}"}

    if not pending:
        skip_out: Dict[str, Any] = {"skipped": True, "reason": "nothing_new_to_embed"}
        skip_out.update(ram_embed_meta)
        return skip_out

    appended = 0
    errors = 0
    root.mkdir(parents=True, exist_ok=True)
    embed_path = root / CHUNK_EMBEDDINGS_FILENAME
    for i in range(0, min(len(pending), max_new), batch):
        chunk = pending[i : i + batch]
        texts = [str(r.get("text") or "")[:12000] for r in chunk]
        vecs = _embed_ollama_multi_input(texts, model, timeout=timeout)
        if len(vecs) != len(chunk):
            logger.debug(
                "[local_ai_selfbuild] embedding count mismatch: requested=%d returned=%d",
                len(chunk),
                len(vecs),
            )
            vecs = list(vecs[: len(chunk)]) + [None] * max(0, len(chunk) - len(vecs))
        if fmt == "f32_index":
            batch_pairs: List[Tuple[Dict[str, Any], List[float]]] = []
            for r, vec in zip(chunk, vecs):
                if not vec:
                    errors += 1
                    continue
                cid = str(r.get("chunk_id") or "")
                if cid in already:
                    continue
                batch_pairs.append((r, vec))
                if len(batch_pairs) + appended >= max_new:
                    batch_pairs = batch_pairs[: max_new - appended]
                    break
            if batch_pairs:
                try:
                    n_written = _append_f32_embedding_batch(root, model, batch_pairs)
                    for r, _ in batch_pairs[:n_written]:
                        already.add(str(r.get("chunk_id") or ""))
                    appended += n_written
                except OSError as e:
                    logger.warning("[local_ai_selfbuild] f32 embedding append failed: %s", e)
                    return {"ok": False, "error": str(e), "rows_appended": appended}
        else:
            lines_to_write: List[str] = []
            staged: List[Dict[str, Any]] = []
            for r, vec in zip(chunk, vecs):
                if not vec:
                    errors += 1
                    continue
                cid = str(r.get("chunk_id") or "")
                if cid in already:
                    continue
                rec = {
                    "chunk_id": cid,
                    "model": model,
                    "dims": len(vec),
                    "embedding": vec,
                    "title": (r.get("title") or "")[:240],
                    "signals": r.get("signals") if isinstance(r.get("signals"), list) else [],
                    "exported_at": _utc_iso(),
                }
                lines_to_write.append(json.dumps(rec, ensure_ascii=False))
                staged.append(r)
                if len(lines_to_write) + appended >= max_new:
                    cap = max(0, max_new - appended)
                    lines_to_write = lines_to_write[:cap]
                    staged = staged[:cap]
                    break
            if lines_to_write:
                try:
                    with open(embed_path, "a", encoding="utf-8") as ef:
                        for ln in lines_to_write:
                            ef.write(ln + "\n")
                    for r in staged:
                        already.add(str(r.get("chunk_id") or ""))
                    appended += len(lines_to_write)
                except OSError as e:
                    logger.warning("[local_ai_selfbuild] embedding append failed: %s", e)
                    return {"ok": False, "error": str(e), "rows_appended": appended}
        if appended >= max_new:
            break

    stats = {
        "model": model,
        "storage": fmt,
        "rows_appended": appended,
        "errors": errors,
        "pending_seen": len(pending),
    }
    stats.update(ram_embed_meta)
    if fmt == "f32_index":
        stats["output_vectors"] = str(root / CHUNK_EMBEDDINGS_F32)
        stats["output_index"] = str(root / CHUNK_EMBEDDINGS_INDEX)
    else:
        stats["output"] = str(embed_path)
    if appended <= 0 and errors > 0:
        stats["ok"] = False
        stats["reason"] = "no_embeddings_returned"
        _merge_manifest_embed_stats(root, stats)
        logger.warning(
            "[local_ai_selfbuild] embedding export failed: no vectors returned model=%s errors=%d pending=%d",
            model,
            errors,
            len(pending),
        )
        return dict(stats)
    stats["ok"] = True
    _merge_manifest_embed_stats(root, stats)
    if appended:
        logger.info(
            "[local_ai_selfbuild] embeddings appended=%d model=%s storage=%s",
            appended,
            model,
            fmt,
        )
    return dict(stats)
