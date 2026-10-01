"""Deterministic source-linked memory primitives for Issue #95.

Pure/local only: no providers, network, autonomy, or live-memory writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable

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
