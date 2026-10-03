"""Deterministic source-linked memory primitives for Issue #95.

Pure/local only: no providers, network, autonomy, or live-memory writes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

_TAG_SEPARATORS = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


class MemoryIntelligenceError(ValueError):
    """Fail-closed provenance or offset validation error."""


@dataclass(frozen=True, slots=True)
class RawSource:
    source_id: str
    sha256: str
    raw_bytes: bytes


@dataclass(frozen=True, slots=True)
class SourceChunk:
    chunk_id: str
    source_id: str
    source_sha256: str
    start_byte: int
    end_byte: int
    text: str


@dataclass(frozen=True, slots=True)
class TagDecision:
    normalized_tag: str
    state: str
    source_chunk_id: str
    method: str
    rule_version: str
    confidence: float


def preserve_raw_source(raw_bytes: bytes, *, source_identity: str) -> RawSource:
    if type(raw_bytes) is not bytes:
        raise MemoryIntelligenceError("raw source must be exact bytes")
    if type(source_identity) is not str or not source_identity.strip():
        raise MemoryIntelligenceError("source identity must be non-empty")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    source_id = hashlib.sha256(
        b"source-v1\0" + source_identity.encode("utf-8") + b"\0" + digest.encode("ascii")
    ).hexdigest()
    return RawSource(source_id=source_id, sha256=digest, raw_bytes=raw_bytes)


def chunk_utf8_source(source: RawSource, *, max_bytes: int = 4096) -> tuple[SourceChunk, ...]:
    if type(source) is not RawSource or type(max_bytes) is not int or max_bytes <= 0:
        raise MemoryIntelligenceError("invalid source or chunk size")
    if hashlib.sha256(source.raw_bytes).hexdigest() != source.sha256:
        raise MemoryIntelligenceError("raw source hash mismatch")
    try:
        text = source.raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MemoryIntelligenceError("raw source is not valid UTF-8") from exc
    if not text:
        return ()

    chunks: list[SourceChunk] = []
    start = 0
    current = bytearray()
    for char in text:
        encoded = char.encode("utf-8")
        if current and len(current) + len(encoded) > max_bytes:
            end = start + len(current)
            chunk_text = bytes(current).decode("utf-8")
            chunk_id = _chunk_id(source, start, end)
            chunks.append(SourceChunk(chunk_id, source.source_id, source.sha256, start, end, chunk_text))
            start = end
            current = bytearray()
        current.extend(encoded)
    if current:
        end = start + len(current)
        chunk_text = bytes(current).decode("utf-8")
        chunks.append(SourceChunk(_chunk_id(source, start, end), source.source_id, source.sha256, start, end, chunk_text))
    return tuple(chunks)


def _chunk_id(source: RawSource, start: int, end: int) -> str:
    payload = f"chunk-v1\0{source.source_id}\0{source.sha256}\0{start}\0{end}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expand_chunk(source: RawSource, chunk: SourceChunk, *, context_bytes: int = 0) -> bytes:
    if type(source) is not RawSource or type(chunk) is not SourceChunk:
        raise MemoryIntelligenceError("typed source and chunk required")
    if type(context_bytes) is not int or context_bytes < 0:
        raise MemoryIntelligenceError("invalid context size")
    if hashlib.sha256(source.raw_bytes).hexdigest() != source.sha256:
        raise MemoryIntelligenceError("raw source hash mismatch")
    if chunk.source_id != source.source_id or chunk.source_sha256 != source.sha256:
        raise MemoryIntelligenceError("chunk source linkage mismatch")
    if (
        type(chunk.start_byte) is not int
        or type(chunk.end_byte) is not int
        or chunk.start_byte < 0
        or chunk.end_byte <= chunk.start_byte
        or chunk.end_byte > len(source.raw_bytes)
    ):
        raise MemoryIntelligenceError("malformed chunk offsets")
    if chunk.chunk_id != _chunk_id(source, chunk.start_byte, chunk.end_byte):
        raise MemoryIntelligenceError("chunk identity mismatch")
    exact = source.raw_bytes[chunk.start_byte:chunk.end_byte]
    try:
        exact_text = exact.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MemoryIntelligenceError("chunk offsets split UTF-8") from exc
    if exact_text != chunk.text:
        raise MemoryIntelligenceError("chunk text mismatch")
    start = max(0, chunk.start_byte - context_bytes)
    end = min(len(source.raw_bytes), chunk.end_byte + context_bytes)
    return source.raw_bytes[start:end]


def normalize_tag(tag: str) -> str:
    if type(tag) is not str:
        raise MemoryIntelligenceError("tag must be exact string")
    normalized = _TAG_SEPARATORS.sub(" ", tag.casefold()).strip()
    return _WS.sub(" ", normalized)


def classify_tag(
    tag: str,
    *,
    canonical_tags: Iterable[str],
    source_chunk_id: str,
    method: str = "deterministic-normalization",
    rule_version: str = "tag-v1",
    confidence: float = 1.0,
) -> TagDecision:
    normalized = normalize_tag(tag)
    if not normalized:
        raise MemoryIntelligenceError("empty normalized tag")
    if type(source_chunk_id) is not str or not source_chunk_id:
        raise MemoryIntelligenceError("source chunk id required")
    canonical: dict[str, str] = {}
    for existing in canonical_tags:
        key = normalize_tag(existing)
        if key:
            canonical.setdefault(key, key)
    state = "selected_existing" if normalized in canonical else "candidate_proposed"
    return TagDecision(normalized, state, source_chunk_id, method, rule_version, float(confidence))


MEMORY_INTELLIGENCE_SUBDIR = "memory_intelligence"
RAW_SOURCES_SUBDIR = "raw_sources"
RECORDS_SUBDIR = "records"
SCHEMA_VERSION = "memory-intelligence-v1"
CREATED_BY = "deterministic-local-memory-intelligence"
_DEFAULT_CONTEXT_BYTES = 192
_HIGHLIGHT_SEGMENT = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")


@dataclass(frozen=True, slots=True)
class SourceHighlight:
    highlight_id: str
    chunk_id: str
    source_id: str
    start_byte: int
    end_byte: int
    text: str


@dataclass(frozen=True, slots=True)
class MemoryIntelligenceWriteReport:
    status: str
    record_path: str
    raw_source_path: str
    source_id: str
    chunk_count: int
    highlight_count: int
    selected_tag_count: int
    candidate_tag_count: int
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _highlight_id(source: RawSource, chunk: SourceChunk, start: int, end: int) -> str:
    payload = (
        f"highlight-v1\0{source.source_id}\0{chunk.chunk_id}\0{start}\0{end}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def extract_highlights(
    source: RawSource,
    chunk: SourceChunk,
    *,
    max_highlights: int = 4,
    min_chars: int = 12,
) -> tuple[SourceHighlight, ...]:
    """Extract deterministic sentence/line highlights with exact source byte offsets."""
    expand_chunk(source, chunk, context_bytes=0)
    if type(max_highlights) is not int or max_highlights <= 0:
        raise MemoryIntelligenceError("invalid highlight limit")
    if type(min_chars) is not int or min_chars < 1:
        raise MemoryIntelligenceError("invalid highlight minimum")

    found: list[SourceHighlight] = []
    for match in _HIGHLIGHT_SEGMENT.finditer(chunk.text):
        raw_segment = match.group(0)
        left = len(raw_segment) - len(raw_segment.lstrip())
        right = len(raw_segment.rstrip())
        char_start = match.start() + left
        char_end = match.start() + right
        if char_end <= char_start:
            continue
        highlight_text = chunk.text[char_start:char_end]
        if len(highlight_text) < min_chars:
            continue
        local_start = len(chunk.text[:char_start].encode("utf-8"))
        local_end = len(chunk.text[:char_end].encode("utf-8"))
        start = chunk.start_byte + local_start
        end = chunk.start_byte + local_end
        found.append(
            SourceHighlight(
                highlight_id=_highlight_id(source, chunk, start, end),
                chunk_id=chunk.chunk_id,
                source_id=source.source_id,
                start_byte=start,
                end_byte=end,
                text=highlight_text,
            )
        )
        if len(found) >= max_highlights:
            break

    if not found and chunk.text.strip():
        stripped = chunk.text.strip()
        char_start = chunk.text.index(stripped)
        char_end = char_start + len(stripped)
        start = chunk.start_byte + len(chunk.text[:char_start].encode("utf-8"))
        end = chunk.start_byte + len(chunk.text[:char_end].encode("utf-8"))
        found.append(
            SourceHighlight(
                highlight_id=_highlight_id(source, chunk, start, end),
                chunk_id=chunk.chunk_id,
                source_id=source.source_id,
                start_byte=start,
                end_byte=end,
                text=stripped,
            )
        )
    return tuple(found)


def summarize_chunk(chunk: SourceChunk, *, max_chars: int = 220) -> str:
    if type(chunk) is not SourceChunk or type(max_chars) is not int or max_chars < 16:
        raise MemoryIntelligenceError("invalid chunk summary request")
    compact = _WS.sub(" ", chunk.text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def expand_highlight(
    source: RawSource,
    chunk: SourceChunk,
    highlight: SourceHighlight,
    *,
    context_bytes: int = _DEFAULT_CONTEXT_BYTES,
) -> dict[str, bytes]:
    """Validate highlight provenance and return highlight, surrounding context and raw source."""
    expand_chunk(source, chunk, context_bytes=0)
    if type(highlight) is not SourceHighlight:
        raise MemoryIntelligenceError("typed highlight required")
    if highlight.source_id != source.source_id or highlight.chunk_id != chunk.chunk_id:
        raise MemoryIntelligenceError("highlight linkage mismatch")
    if (
        type(highlight.start_byte) is not int
        or type(highlight.end_byte) is not int
        or highlight.start_byte < chunk.start_byte
        or highlight.end_byte > chunk.end_byte
        or highlight.end_byte <= highlight.start_byte
    ):
        raise MemoryIntelligenceError("malformed highlight offsets")
    expected_id = _highlight_id(source, chunk, highlight.start_byte, highlight.end_byte)
    if expected_id != highlight.highlight_id:
        raise MemoryIntelligenceError("highlight identity mismatch")
    exact = source.raw_bytes[highlight.start_byte:highlight.end_byte]
    try:
        exact_text = exact.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MemoryIntelligenceError("highlight offsets split UTF-8") from exc
    if exact_text != highlight.text:
        raise MemoryIntelligenceError("highlight text mismatch")
    if type(context_bytes) is not int or context_bytes < 0:
        raise MemoryIntelligenceError("invalid context size")
    context = expand_chunk(source, chunk, context_bytes=context_bytes)
    return {
        "highlight": exact,
        "context": context,
        "raw_source": source.raw_bytes,
    }


def _relative_artifact_path(dest_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(dest_dir.resolve()).as_posix()
    except ValueError as exc:
        raise MemoryIntelligenceError("memory intelligence artifact escaped destination") from exc


def _paths(dest_dir: Path, source_id: str) -> tuple[Path, Path]:
    root = Path(dest_dir) / MEMORY_INTELLIGENCE_SUBDIR
    raw_path = root / RAW_SOURCES_SUBDIR / f"{source_id}.bin"
    record_path = root / RECORDS_SUBDIR / f"{source_id}.json"
    return raw_path, record_path


def _tag_decisions_for_chunk(
    chunk: SourceChunk,
    *,
    canonical_tags: Sequence[str],
    tag_hints: Sequence[str],
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for hint in tag_hints:
        decision = classify_tag(
            hint,
            canonical_tags=canonical_tags,
            source_chunk_id=chunk.chunk_id,
        )
        key = (decision.normalized_tag, decision.state)
        if key in seen:
            continue
        seen.add(key)
        decisions.append(asdict(decision))
    return decisions


def persist_source_intelligence(
    *,
    dest_dir: Path,
    raw_bytes: bytes,
    source_identity: str,
    canonical_tags: Sequence[str] = (),
    tag_hints: Sequence[str] = (),
    max_chunk_bytes: int = 4096,
) -> MemoryIntelligenceWriteReport:
    """Persist deterministic source-linked artifacts under an existing ingestion destination."""
    dest = Path(dest_dir).expanduser().resolve()
    source = preserve_raw_source(raw_bytes, source_identity=source_identity)
    chunks = chunk_utf8_source(source, max_bytes=max_chunk_bytes)
    raw_path, record_path = _paths(dest, source.source_id)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        if raw_path.read_bytes() != source.raw_bytes:
            raise MemoryIntelligenceError("existing raw source bytes do not match source identity")
    else:
        raw_path.write_bytes(source.raw_bytes)

    canonical_normalized = sorted(
        {normalize_tag(tag) for tag in canonical_tags if normalize_tag(tag)}
    )
    chunk_payloads: list[dict[str, Any]] = []
    selected: set[str] = set()
    candidates: set[str] = set()
    highlight_count = 0

    for chunk in chunks:
        highlights = extract_highlights(source, chunk)
        highlight_count += len(highlights)
        decisions = _tag_decisions_for_chunk(
            chunk,
            canonical_tags=canonical_tags,
            tag_hints=tag_hints,
        )
        for decision in decisions:
            normalized = str(decision["normalized_tag"])
            if decision["state"] == "selected_existing":
                selected.add(normalized)
            else:
                candidates.add(normalized)
        chunk_payloads.append(
            {
                **asdict(chunk),
                "summary": summarize_chunk(chunk),
                "highlights": [asdict(item) for item in highlights],
                "tag_decisions": decisions,
            }
        )

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_by": CREATED_BY,
        "source_identity": source_identity,
        "source_id": source.source_id,
        "source_sha256": source.sha256,
        "raw_size_bytes": len(source.raw_bytes),
        "raw_source_path": _relative_artifact_path(dest, raw_path),
        "canonical_tags": canonical_normalized,
        "selected_tags": sorted(selected),
        "candidate_tags": sorted(candidates - selected),
        "chunks": chunk_payloads,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
    }
    encoded = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    status = "created"
    if record_path.exists():
        existing = record_path.read_text(encoding="utf-8")
        if existing == encoded:
            status = "unchanged"
        else:
            record_path.write_text(encoded, encoding="utf-8", newline="\n")
            status = "updated"
    else:
        record_path.write_text(encoded, encoding="utf-8", newline="\n")

    return MemoryIntelligenceWriteReport(
        status=status,
        record_path=str(record_path),
        raw_source_path=str(raw_path),
        source_id=source.source_id,
        chunk_count=len(chunks),
        highlight_count=highlight_count,
        selected_tag_count=len(selected),
        candidate_tag_count=len(candidates - selected),
    )


def _raw_source_from_record(dest: Path, record: dict[str, Any]) -> RawSource:
    raw_rel = str(record.get("raw_source_path") or "")
    raw_path = (dest / raw_rel).resolve()
    root = dest.resolve()
    try:
        raw_path.relative_to(root)
    except ValueError as exc:
        raise MemoryIntelligenceError("raw source path escaped destination") from exc
    if not raw_path.is_file():
        raise MemoryIntelligenceError("raw source artifact missing")
    source = preserve_raw_source(
        raw_path.read_bytes(),
        source_identity=str(record.get("source_identity") or ""),
    )
    if source.source_id != record.get("source_id") or source.sha256 != record.get("source_sha256"):
        raise MemoryIntelligenceError("persisted source provenance mismatch")
    return source


def _chunk_from_payload(payload: dict[str, Any]) -> SourceChunk:
    try:
        return SourceChunk(
            chunk_id=str(payload["chunk_id"]),
            source_id=str(payload["source_id"]),
            source_sha256=str(payload["source_sha256"]),
            start_byte=payload["start_byte"],
            end_byte=payload["end_byte"],
            text=str(payload["text"]),
        )
    except (KeyError, TypeError) as exc:
        raise MemoryIntelligenceError("malformed persisted chunk") from exc


def _highlight_from_payload(payload: dict[str, Any]) -> SourceHighlight:
    try:
        return SourceHighlight(
            highlight_id=str(payload["highlight_id"]),
            chunk_id=str(payload["chunk_id"]),
            source_id=str(payload["source_id"]),
            start_byte=payload["start_byte"],
            end_byte=payload["end_byte"],
            text=str(payload["text"]),
        )
    except (KeyError, TypeError) as exc:
        raise MemoryIntelligenceError("malformed persisted highlight") from exc


def load_memory_intelligence_records(dest_dir: Path) -> list[dict[str, Any]]:
    dest = Path(dest_dir).expanduser().resolve()
    records_dir = dest / MEMORY_INTELLIGENCE_SUBDIR / RECORDS_SUBDIR
    if not records_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryIntelligenceError(f"invalid intelligence record: {path.name}") from exc
        if not isinstance(payload, dict):
            raise MemoryIntelligenceError(f"invalid intelligence record: {path.name}")
        records.append(payload)
    return records


def _query_terms(query: str) -> list[str]:
    return [term for term in _TAG_SEPARATORS.split(query.casefold()) if term]



_TAG_DECISION_FIELDS = frozenset(
    {
        "normalized_tag",
        "state",
        "source_chunk_id",
        "method",
        "rule_version",
        "confidence",
    }
)
_TAG_DECISION_STATES = frozenset({"selected_existing", "candidate_proposed"})


def _validated_tag_decision(payload: Any, chunk: SourceChunk) -> str:
    """Validate persisted tag provenance before it can affect recall."""
    if type(payload) is not dict or set(payload) != _TAG_DECISION_FIELDS:
        raise MemoryIntelligenceError("malformed persisted tag decision")
    for field in (
        "normalized_tag",
        "state",
        "source_chunk_id",
        "method",
        "rule_version",
    ):
        if type(payload[field]) is not str:
            raise MemoryIntelligenceError("malformed persisted tag decision")
    normalized_tag = payload["normalized_tag"]
    if not normalized_tag or normalize_tag(normalized_tag) != normalized_tag:
        raise MemoryIntelligenceError("inconsistent persisted normalized tag")
    if payload["state"] not in _TAG_DECISION_STATES:
        raise MemoryIntelligenceError("unrecognized persisted tag state")
    if payload["source_chunk_id"] != chunk.chunk_id:
        raise MemoryIntelligenceError("persisted tag source linkage mismatch")
    if not payload["method"].strip() or not payload["rule_version"].strip():
        raise MemoryIntelligenceError("persisted tag provenance fields are required")
    confidence = payload["confidence"]
    if (
        type(confidence) is not float
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        raise MemoryIntelligenceError("invalid persisted tag confidence")
    return normalized_tag

def query_memory_intelligence(
    dest_dir: Path,
    query: str,
    *,
    limit: int = 5,
    context_bytes: int = _DEFAULT_CONTEXT_BYTES,
    validate_summaries: bool = False,
) -> list[dict[str, Any]]:
    """Read-only deterministic query with machine-readable recall reasons."""
    if type(query) is not str or not query.strip():
        raise MemoryIntelligenceError("query is required")
    if type(limit) is not int or limit < 0:
        raise MemoryIntelligenceError("invalid query limit")
    if type(validate_summaries) is not bool:
        raise MemoryIntelligenceError("invalid summary validation mode")
    terms = _query_terms(query)
    dest = Path(dest_dir).expanduser().resolve()
    results: list[dict[str, Any]] = []

    for record in load_memory_intelligence_records(dest):
        source = _raw_source_from_record(dest, record)
        for chunk_payload in record.get("chunks") or []:
            if not isinstance(chunk_payload, dict):
                raise MemoryIntelligenceError("malformed persisted chunk")
            chunk = _chunk_from_payload(chunk_payload)
            expand_chunk(source, chunk, context_bytes=0)
            if validate_summaries and chunk_payload.get("summary") != summarize_chunk(chunk):
                raise MemoryIntelligenceError("persisted summary does not match validated source chunk")
            text_blob = f"{chunk.text} {chunk_payload.get('summary') or ''}".casefold()
            text_matches = sorted({term for term in terms if term in text_blob})
            decisions = chunk_payload.get("tag_decisions")
            if type(decisions) is not list:
                raise MemoryIntelligenceError("malformed persisted tag decisions")
            tags = [_validated_tag_decision(item, chunk) for item in decisions]
            tag_matches = sorted(
                {tag for tag in tags if tag and any(term in tag for term in terms)}
            )
            if not text_matches and not tag_matches:
                continue
            reasons: list[dict[str, Any]] = []
            if text_matches:
                reasons.append({"type": "text_relevance", "matched_terms": text_matches})
            if tag_matches:
                reasons.append({"type": "tag_match", "matched_tags": tag_matches})
            reasons.append(
                {
                    "type": "source_relation",
                    "source_id": source.source_id,
                    "chunk_id": chunk.chunk_id,
                }
            )
            highlights_payload = chunk_payload.get("highlights") or []
            expansions: list[dict[str, Any]] = []
            for item in highlights_payload:
                if not isinstance(item, dict):
                    raise MemoryIntelligenceError("malformed persisted highlight")
                highlight = _highlight_from_payload(item)
                expanded = expand_highlight(
                    source,
                    chunk,
                    highlight,
                    context_bytes=context_bytes,
                )
                expansions.append(
                    {
                        **asdict(highlight),
                        "surrounding_context": expanded["context"].decode("utf-8", errors="replace"),
                    }
                )
            results.append(
                {
                    "source_id": source.source_id,
                    "chunk_id": chunk.chunk_id,
                    "summary": str(chunk_payload.get("summary") or ""),
                    "score": (len(tag_matches) * 3) + (len(text_matches) * 2),
                    "recall_reasons": reasons,
                    "selected_tags": list(record.get("selected_tags") or []),
                    "candidate_tags": list(record.get("candidate_tags") or []),
                    "highlights": expansions,
                    "raw_source_path": str(record.get("raw_source_path") or ""),
                }
            )

    results.sort(key=lambda item: (-int(item["score"]), item["source_id"], item["chunk_id"]))
    return results[:limit]


def expand_persisted_highlight(
    dest_dir: Path,
    highlight_id: str,
    *,
    context_bytes: int = _DEFAULT_CONTEXT_BYTES,
) -> dict[str, str]:
    """Expand persisted highlight -> surrounding context -> full raw source with provenance checks."""
    if type(highlight_id) is not str or not highlight_id:
        raise MemoryIntelligenceError("highlight id required")
    dest = Path(dest_dir).expanduser().resolve()
    for record in load_memory_intelligence_records(dest):
        source = _raw_source_from_record(dest, record)
        for chunk_payload in record.get("chunks") or []:
            if not isinstance(chunk_payload, dict):
                raise MemoryIntelligenceError("malformed persisted chunk")
            chunk = _chunk_from_payload(chunk_payload)
            for item in chunk_payload.get("highlights") or []:
                if not isinstance(item, dict):
                    raise MemoryIntelligenceError("malformed persisted highlight")
                highlight = _highlight_from_payload(item)
                if highlight.highlight_id != highlight_id:
                    continue
                expanded = expand_highlight(
                    source,
                    chunk,
                    highlight,
                    context_bytes=context_bytes,
                )
                return {
                    "highlight_id": highlight.highlight_id,
                    "chunk_id": chunk.chunk_id,
                    "source_id": source.source_id,
                    "highlight": expanded["highlight"].decode("utf-8"),
                    "surrounding_context": expanded["context"].decode("utf-8", errors="replace"),
                    "raw_source": expanded["raw_source"].decode("utf-8"),
                }
    raise MemoryIntelligenceError("highlight not found")
