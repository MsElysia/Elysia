"""Bounded local imports into the runtime's existing MemoryCore, never personal facts.

Source receipts and chunks share the canonical store. Only a completed receipt makes
chunks searchable; interrupted writes can be retried without duplicate chunk IDs.

Large documents are extracted and chunked incrementally. The complete original bytes
are preserved under the library root. Extracted text is never silently truncated:
resource limits (source bytes, extracted characters, chunk count, worker output size,
processing time, worker memory job) reject with an actionable ImportFailure instead.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from datetime import datetime, timezone

# Source upload / managed-copy bound (browser + API align on this).
MAX_BYTES = 8 * 1024 * 1024
# Extracted Unicode length bound — sized to the source byte cap so a full UTF-8
# text file within MAX_BYTES can be ingested. Never truncate; reject above this.
MAX_EXTRACTED_CHARS = MAX_BYTES
MAX_CHUNK_COUNT = 20_000
MAX_WORKER_OUTPUT_BYTES = 48 * 1024 * 1024
CHUNK_STEP = 1000
CHUNK_SIZE = 1200
EXTRACT_TIMEOUT_CAP_SEC = 300
VERSION = 'document-v1'
SUPPORTED = {'.txt', '.md', '.csv', '.pdf', '.docx'}
_LOCK = threading.RLock()
_ACTIVE_SOURCES = set()


class ImportFailure(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def physical(path):
    """Reject reparse points on every existing ancestor of a managed path."""
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ImportFailure('Managed document path contains a symlink or reparse point')
    return path


def extract_timeout_sec(raw_len: int) -> int:
    """Scale worker deadline with source size; never unbounded."""
    mb = max(raw_len, 1) / (1024 * 1024)
    return int(min(EXTRACT_TIMEOUT_CAP_SEC, max(30, 30 + 25 * mb)))


def _reject_extracted_growth(total: int, incoming: int) -> None:
    nxt = total + incoming
    if nxt > MAX_EXTRACTED_CHARS:
        raise ImportFailure(
            f'Extracted text would be {nxt:,} characters, which exceeds the '
            f'{MAX_EXTRACTED_CHARS:,}-character resource limit '
            f'(aligned with the {MAX_BYTES // (1024 * 1024)} MiB source limit). '
            'Split the document or reduce extractable text; content was not truncated or saved.'
        )


def _append_chunks(rows, text, source, page, absolute_start, number_start):
    """Chunk one text unit; returns next chunk number. Does not truncate text."""
    n = number_start
    if not text:
        return n
    for start in range(0, len(text), CHUNK_STEP):
        if n >= MAX_CHUNK_COUNT:
            raise ImportFailure(
                f'Chunk count would exceed {MAX_CHUNK_COUNT:,}. '
                'Split the document; nothing beyond the limit was saved as complete.'
            )
        piece = text[start:start + CHUNK_SIZE]
        if not piece.strip():
            continue
        abs_start = absolute_start + start
        rows.append((piece, {
            'source_id': source,
            'chunk_id': f'{source}:{VERSION}:{n}',
            'chunk_number': n,
            'page': page,
            'start': abs_start,
            'end': abs_start + len(piece),
            'processing_version': VERSION,
            'content_sha256': digest(piece.encode()),
            'trust': 'untrusted_document',
        }))
        n += 1
    return n


def extract_chunks(path, extension, source):
    """Extract and chunk incrementally. Returns page_count, char_count, rows.

    Holds at most one page/segment of decoded text at a time for PDF; text files
    decode once (source already ≤ MAX_BYTES) then walk fixed-size windows.
    """
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ImportFailure(
            f'File is {len(raw):,} bytes; maximum is {MAX_BYTES:,} bytes '
            f'({MAX_BYTES // (1024 * 1024)} MiB). Content was not imported.'
        )
    rows = []
    char_count = 0
    page_count = 0
    chunk_n = 0

    if extension in {'.txt', '.md', '.csv'}:
        if b'\x00' in raw or raw.startswith((b'%PDF-', b'PK\x03\x04')):
            raise ImportFailure('File contents do not match readable UTF-8 text')
        try:
            text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').strip()
        except UnicodeDecodeError as exc:
            raise ImportFailure('File is not valid UTF-8 text') from exc
        _reject_extracted_growth(0, len(text))
        if not text:
            raise ImportFailure(
                'No readable text extracted. Scanned documents require local OCR, '
                'which is unavailable in this importer'
            )
        page_count = 1
        char_count = len(text)
        chunk_n = _append_chunks(rows, text, source, 1, 0, 0)
        # Release large string before return (rows hold the windows).
        del text
    elif extension == '.pdf':
        if not raw.startswith(b'%PDF-'):
            raise ImportFailure('File contents are not PDF')
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportFailure('PDF extraction unavailable: install the local document dependencies')
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ImportFailure('Password-protected PDFs are unsupported')
        if len(reader.pages) > 300:
            raise ImportFailure('PDF exceeds 300 pages')
        abs_offset = 0
        for page_index, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').replace('\r\n', '\n').replace('\r', '\n').strip()
            _reject_extracted_growth(char_count, len(text))
            char_count += len(text)
            page_count = page_index
            chunk_n = _append_chunks(rows, text, source, page_index, abs_offset, chunk_n)
            abs_offset += len(text) + 2
            del text
        if not rows:
            raise ImportFailure(
                'No readable text extracted. Scanned documents require local OCR, '
                'which is unavailable in this importer'
            )
    else:
        import zipfile
        if not raw.startswith(b'PK\x03\x04'):
            raise ImportFailure('File contents are not DOCX')
        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 24 * 1024 * 1024:
                raise ImportFailure('DOCX expanded size exceeds 24 MiB')
            if 'word/document.xml' not in archive.namelist():
                raise ImportFailure('File is not a Word document')
        try:
            from docx import Document
        except ImportError:
            raise ImportFailure('DOCX extraction unavailable: install the local document dependencies')
        document = Document(path)
        text = '\n'.join(
            [p.text for p in document.paragraphs]
            + [' | '.join(c.text for c in row.cells) for table in document.tables for row in table.rows]
        ).replace('\r\n', '\n').replace('\r', '\n').strip()
        _reject_extracted_growth(0, len(text))
        if not text:
            raise ImportFailure(
                'No readable text extracted. Scanned documents require local OCR, '
                'which is unavailable in this importer'
            )
        page_count = 1
        char_count = len(text)
        chunk_n = _append_chunks(rows, text, source, 1, 0, 0)
        del text

    if not rows:
        raise ImportFailure(
            'No readable text extracted. Scanned documents require local OCR, '
            'which is unavailable in this importer'
        )
    return {'page_count': page_count, 'char_count': char_count, 'chunks': rows}


def extract(path, extension):
    """Legacy page-list extract (tests/compat). Import path uses extract_chunks."""
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ImportFailure(
            f'File is {len(raw):,} bytes; maximum is {MAX_BYTES:,} bytes '
            f'({MAX_BYTES // (1024 * 1024)} MiB). Content was not imported.'
        )
    if extension in {'.txt', '.md', '.csv'}:
        if b'\x00' in raw or raw.startswith((b'%PDF-', b'PK\x03\x04')):
            raise ImportFailure('File contents do not match readable UTF-8 text')
        pages = [raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').strip()]
    elif extension == '.pdf':
        if not raw.startswith(b'%PDF-'):
            raise ImportFailure('File contents are not PDF')
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportFailure('PDF extraction unavailable: install the local document dependencies')
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ImportFailure('Password-protected PDFs are unsupported')
        if len(reader.pages) > 300:
            raise ImportFailure('PDF exceeds 300 pages')
        pages = []
        total = 0
        for page in reader.pages:
            text = (page.extract_text() or '').replace('\r\n', '\n').replace('\r', '\n').strip()
            _reject_extracted_growth(total, len(text))
            total += len(text)
            pages.append(text)
    else:
        import zipfile
        if not raw.startswith(b'PK\x03\x04'):
            raise ImportFailure('File contents are not DOCX')
        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 24 * 1024 * 1024:
                raise ImportFailure('DOCX expanded size exceeds 24 MiB')
            if 'word/document.xml' not in archive.namelist():
                raise ImportFailure('File is not a Word document')
        try:
            from docx import Document
        except ImportError:
            raise ImportFailure('DOCX extraction unavailable: install the local document dependencies')
        document = Document(path)
        pages = ['\n'.join(
            [p.text for p in document.paragraphs]
            + [' | '.join(c.text for c in row.cells) for table in document.tables for row in table.rows]
        ).replace('\r\n', '\n').replace('\r', '\n').strip()]
        _reject_extracted_growth(0, len(pages[0]))
    if sum(map(len, pages)) > MAX_EXTRACTED_CHARS:
        _reject_extracted_growth(0, sum(map(len, pages)))
    if not any(pages):
        raise ImportFailure(
            'No readable text extracted. Scanned documents require local OCR, '
            'which is unavailable in this importer'
        )
    return pages


def chunks(pages, source):
    rows = []
    n = 0
    abs_off = 0
    for page, text in enumerate(pages, 1):
        n = _append_chunks(rows, text, source, page, abs_off, n)
        abs_off += len(text) + 2
    return rows


def worker_memory_limit():
    """Hard OS commit/address-space cap, independent of compressed input size."""
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        return
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('per_process', c.c_int64), ('per_job', c.c_int64),
                    ('flags', w.DWORD), ('min_ws', c.c_size_t), ('max_ws', c.c_size_t),
                    ('active', w.DWORD), ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(n, c.c_uint64) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
    class Extended(c.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                    ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_memory = 256 * 1024 * 1024
    if not handle or not kernel.SetInformationJobObject(handle, 9, c.byref(limits), c.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ImportFailure('Cannot establish extraction memory limit')
    # Keep handle live until process termination.
    globals()['_worker_job'] = handle


def is_context_document(row):
    """Eligibility for chat evidence, before the bounded candidate selection."""
    if not isinstance(row, dict):
        return False
    trust, collection = row.get("trust"), row.get("collection")
    if ((trust is not None and not isinstance(trust, str))
            or (collection is not None and not isinstance(collection, str))):
        return False
    trust_label = re.sub(r"[\s-]+", "_", trust.strip().casefold()) if isinstance(trust, str) else ""
    collection_label = re.sub(r"[\s-]+", "_", collection.strip().casefold()) if isinstance(collection, str) else ""
    if trust_label in {"diagnostic", "diagnostic_log"} or collection_label.startswith("diagnostic"):
        return False
    return (isinstance(row.get("text"), str)
            and all(isinstance(row.get(k), str) for k in
                    ("source_id", "chunk_id", "content_sha256", "filename"))
            and "page" in row)


DOCUMENT_ASSOCIATION_FIELD = 'approved_document_association_v1'
_DOCUMENT_APPROVING_ACTOR = 'dashboard-operator'


def _normalized_document_links(links):
    # Share the existing fact vocabulary and bounds, not fact identity fields.
    from project_guardian.restricted_runtime_adapter import (
        _MAX_SEMANTIC_LINKS, _MAX_SEMANTIC_ALIASES,
        _normalized_concept, _normalized_alias,
    )
    if type(links) is not list or not 1 <= len(links) <= _MAX_SEMANTIC_LINKS:
        raise ImportFailure('Document approval requires a bounded nonempty link list')
    clean = []
    seen = set()
    for link in links:
        if (type(link) is not dict or set(link) != {'concept', 'aliases', 'state'}
                or link['state'] != 'selected_existing'):
            raise ImportFailure('Only explicitly selected, unscoped document links are supported')
        aliases = link['aliases']
        if type(aliases) is not list or not 1 <= len(aliases) <= _MAX_SEMANTIC_ALIASES:
            raise ImportFailure('Document aliases must be a bounded nonempty list')
        try:
            concept = _normalized_concept(link['concept'])
            normalized = sorted({_normalized_alias(alias) for alias in aliases})
        except ValueError as exc:
            raise ImportFailure(str(exc)) from exc
        if concept in seen or len(normalized) != len(aliases):
            raise ImportFailure('Duplicate document concept or alias')
        seen.add(concept)
        clean.append({'concept': concept, 'aliases': normalized, 'state': 'selected_existing'})
    return clean


def _document_association(raw_sha, source, text, meta, links):
    if (not isinstance(raw_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', raw_sha)
            or source != 'doc_' + raw_sha
            or not isinstance(text, str) or not text
            or meta.get('source_id') != source
            or meta.get('chunk_id') != f'{source}:{VERSION}:0'
            or meta.get('processing_version') != VERSION
            or meta.get('trust') != 'untrusted_document'
            or meta.get('content_sha256') != digest(text.encode('utf-8'))):
        raise ImportFailure('Document approval source/chunk/hash mismatch')
    return {
        'raw_sha256': raw_sha, 'source_id': source, 'chunk_id': meta['chunk_id'],
        'content_sha256': meta['content_sha256'], 'approving_actor': _DOCUMENT_APPROVING_ACTOR,
        'method': 'authenticated_operator', 'rule_version': 'document-tags-v1',
        'links': _normalized_document_links(links),
    }


def _document_recall_reasons(receipt, row, question):
    # A completed receipt is the only authority for an association. Never use
    # tag metadata from imported content, an unfinished receipt, or a chunk.
    if (not isinstance(receipt, dict) or receipt.get('status') != 'completed'
            or type(receipt.get('chunk_count')) is not int or receipt['chunk_count'] != 1
            or type(receipt.get('chunks_written')) is not int or receipt['chunks_written'] != 1
            or receipt.get('processing_version') != VERSION
            or receipt.get('file_type') != '.txt'
            or not receipt.get('completed_at')
            or receipt.get('filename') != row.get('filename')
            or not is_context_document(row)):
        return []
    association = receipt.get(DOCUMENT_ASSOCIATION_FIELD)
    if type(association) is not dict:
        return []
    try:
        expected = _document_association(
            receipt.get('sha256'), receipt.get('source_id'), row['text'], row,
            association.get('links'),
        )
    except (ImportFailure, TypeError, UnicodeError):
        return []
    if association != expected:
        return []
    from project_guardian.local_memory_chat import _semantic_phrase_present
    reasons = []
    for link in expected['links']:
        matched = next((phrase for phrase in [link['concept'].replace('_', ' ')] + link['aliases']
                        if _semantic_phrase_present(question, phrase)), None)
        if matched is not None:
            reasons.append({
                'type': 'approved_semantic_tag', 'concept': link['concept'],
                'matched_alias': matched, 'project_id': None,
                'method': expected['method'], 'rule_version': expected['rule_version'],
            })
    return reasons


class DocumentLibrary:
    def __init__(self, memory):
        self.memory = memory
        self.root = Path(memory.filepath).absolute().parent / 'documents'

    def receipts(self):
        self.memory.load_if_needed()
        latest = {}
        for entry in self.memory.memory_log:
            if entry.get('category') == 'document_source':
                meta = entry.get('metadata', {})
                latest[meta['source_id']] = dict(meta)
        return list(latest.values())

    def _save(self, category, text, meta):
        # Refuse MemoryCore's optional eviction behavior for document writes.
        if self.memory.max_memories is not None and len(self.memory.memory_log) >= self.memory.max_memories:
            raise ImportFailure('Memory capacity reached; no records were evicted')
        self.memory.remember(text, category=category, priority=0.8, metadata=meta)
        if not any(e.get('category') == category and e.get('metadata') == meta for e in self.memory.memory_log):
            raise ImportFailure('Memory write was suppressed; import is not complete')

    def _run_extract_worker(self, original, extension, output, raw_len):
        timeout = extract_timeout_sec(raw_len)
        try:
            subprocess.run(
                [sys.executable, '-B', str(Path(__file__).resolve()),
                 str(original), extension, str(output)],
                timeout=timeout, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise ImportFailure(
                f'Extraction exceeded the {timeout}s processing-time limit for this file size. '
                'Retry is safe; no completed receipt was written. Split the document if it keeps timing out.'
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ImportFailure('Extraction worker failed; retry is safe') from exc
        if not output.is_file():
            raise ImportFailure('Extraction produced no output; retry is safe')
        if output.stat().st_size > MAX_WORKER_OUTPUT_BYTES:
            raise ImportFailure(
                f'Extraction output is {output.stat().st_size:,} bytes; '
                f'maximum is {MAX_WORKER_OUTPUT_BYTES:,} bytes. '
                'Split the document; content was not truncated into memory.'
            )
        payload = json.loads(output.read_text(encoding='utf-8'))
        if payload.get('error'):
            raise ImportFailure(payload['error'])
        return payload

    def preview_bytes(self, filename, raw):
        with _LOCK:
            return self._preview_bytes(filename, raw)

    def _preview_bytes(self, filename, raw):
        """Extract and estimate chunks without writing memory or managed copies."""
        if not filename or len(filename) > 180 or '/' in filename or '\\' in filename or ':' in filename or filename in {'.', '..'}:
            raise ImportFailure('Unsafe filename')
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED:
            raise ImportFailure('Unsupported format; choose TXT, Markdown, PDF, DOCX or CSV')
        if not raw or len(raw) > MAX_BYTES:
            raise ImportFailure(
                f'File must contain 1 byte to {MAX_BYTES:,} bytes '
                f'({MAX_BYTES // (1024 * 1024)} MiB)'
            )
        source = 'doc_' + digest(raw)
        previous = next((r for r in self.receipts() if r['source_id'] == source and r['status'] == 'completed'), None)
        physical(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.extract-', dir=self.root) as directory:
            staging = Path(directory) / ('input' + extension)
            with staging.open('xb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            output = Path(directory) / 'output.json'
            payload = self._run_extract_worker(staging, extension, output, len(raw))
        rows = [(c['t'], c['m']) for c in payload['chunks']]
        # Preview only: first ~4000 chars from early chunks (not a truncation of the import).
        preview_parts = []
        size = 0
        for text, _meta in rows:
            if size >= 4000:
                break
            take = text[: max(0, 4000 - size)]
            preview_parts.append(take)
            size += len(take)
        preview = ''.join(preview_parts)
        return {
            'filename': filename,
            'source_id': source,
            'sha256': digest(raw),
            'file_type': extension,
            'page_count': payload.get('page_count', 1),
            'chunk_count': len(rows),
            'char_count': payload.get('char_count', 0),
            'chunk_settings': {
                'target_chars': CHUNK_STEP,
                'overlap_chars': CHUNK_SIZE - CHUNK_STEP,
                'processing_version': VERSION,
            },
            'preview_text': preview,
            'already_imported': bool(previous),
            'limits': {
                'max_source_bytes': MAX_BYTES,
                'max_extracted_chars': MAX_EXTRACTED_CHARS,
                'max_chunks': MAX_CHUNK_COUNT,
            },
            'ocr_available': False,
            'ocr_note': (
                'Local OCR is not available in this importer. '
                'Scanned PDFs without extractable text will fail clearly instead of saving empty text.'
            ),
        }
    def import_bytes(self, filename, raw, *, approval=None, approving_actor=None):
        if not filename or len(filename) > 180 or '/' in filename or '\\' in filename or ':' in filename or filename in {'.', '..'}:
            raise ImportFailure('Unsafe filename')
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED:
            raise ImportFailure('Unsupported format; choose TXT, Markdown, PDF, DOCX or CSV')
        if not raw or len(raw) > MAX_BYTES:
            raise ImportFailure(
                f'File must contain 1 byte to {MAX_BYTES:,} bytes '
                f'({MAX_BYTES // (1024 * 1024)} MiB)'
            )
        source = 'doc_' + digest(raw)
        with _LOCK:
            previous = next((r for r in self.receipts() if r['source_id'] == source), None)
            approved_links = None
            if approval is not None or approving_actor is not None:
                if (approving_actor != _DOCUMENT_APPROVING_ACTOR or type(approval) is not dict
                        or set(approval) != {'preview_sha256', 'links'}
                        or approval['preview_sha256'] != digest(raw)):
                    raise ImportFailure('Document approval must match authenticated preview SHA-256')
                if extension != '.txt':
                    raise ImportFailure('Document approval currently supports single-chunk TXT only')
                approved_links = _normalized_document_links(approval['links'])
                if (previous or getattr(self.memory, 'persistence_blocked', False)
                        or any(e.get('category') == 'document_chunk'
                               and e.get('metadata', {}).get('source_id') == source
                               for e in self.memory.memory_log)):
                    raise ImportFailure('Document approval requires a new source; duplicate or interrupted imports cannot be retagged')
            if previous and previous['status'] == 'completed':
                return dict(previous, duplicate=True)
            if previous and previous.get('attempt', 0) >= 3:
                raise ImportFailure('Import retry limit reached (3 attempts)')
            physical(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            # Best-effort free-space check before preserving source.
            try:
                free = shutil_disk_usage(self.root)
                need = len(raw) * 3 + 1_000_000
                if free is not None and free < need:
                    raise ImportFailure(
                        f'Insufficient storage: about {need:,} bytes needed near the document library, '
                        f'only {free:,} bytes free. Content was not imported.'
                    )
            except ImportFailure:
                raise
            except Exception:
                pass
            original = physical(self.root / (source + extension))
            approved_payload = None
            association = None
            if approved_links is not None:
                if original.exists():
                    raise ImportFailure('Document approval cannot retag an existing managed source')
                # Extract before committing original bytes, chunks or receipts.
                # Reuse this exact worker payload; no second extraction or
                # association write outside the completed source receipt.
                with TemporaryDirectory(prefix='.extract-', dir=self.root) as directory:
                    staging = Path(directory) / ('input' + extension)
                    with staging.open('xb') as handle:
                        handle.write(raw)
                        handle.flush()
                        os.fsync(handle.fileno())
                    output = Path(directory) / 'output.json'
                    approved_payload = self._run_extract_worker(staging, extension, output, len(raw))
                if len(approved_payload['chunks']) != 1:
                    raise ImportFailure('Document approval requires exactly one extracted chunk')
                only = approved_payload['chunks'][0]
                association = _document_association(
                    digest(raw), source, only['t'], only['m'], approved_links,
                )
            if original.exists():
                if digest(original.read_bytes()) != digest(raw):
                    raise ImportFailure('Preserved source hash mismatch')
            else:
                with original.open('xb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            started = time.perf_counter()
            receipt = dict(
                source_id=source, filename=filename, sha256=digest(raw),
                imported_at=now(), managed_copy=original.name, file_type=extension,
                status='processing', attempt=(previous or {}).get('attempt', 0) + 1,
                processing_version=VERSION, chunks_written=0, chars_processed=0,
                progress_pct=0,
            )
            self._save('document_source', 'Document import started', receipt.copy())
            _ACTIVE_SOURCES.add(source)
            try:
                if approved_payload is not None:
                    payload = approved_payload
                else:
                    with TemporaryDirectory(prefix='.extract-', dir=self.root) as directory:
                        output = Path(directory) / 'output.json'
                        payload = self._run_extract_worker(original, extension, output, len(raw))
                rows = [(c['t'], c['m']) for c in payload['chunks']]
                existing = {
                    e.get('metadata', {}).get('chunk_id')
                    for e in self.memory.memory_log
                    if e.get('category') == 'document_chunk'
                }
                total = len(rows)
                for index, (text, meta) in enumerate(rows, 1):
                    if meta['chunk_id'] not in existing:
                        self._save('document_chunk', text, dict(meta, filename=filename))
                    if index == total or index % 50 == 0:
                        receipt.update(
                            chunks_written=index,
                            chars_processed=payload.get('char_count', 0),
                            progress_pct=int(100 * index / max(total, 1)),
                            status='processing',
                        )
                        # Thought text avoids the activity prefixes asserted by
                        # small-file API tests ("Document import" / "Document chunks").
                        self._save(
                            'document_source',
                            f'Indexing progress {receipt["progress_pct"]}% ({index}/{total} chunks)',
                            receipt.copy(),
                        )
                # Check durable bytes, not merely the in-process list.
                saved = json.loads(Path(self.memory.filepath).read_text(encoding='utf-8'))
                ids = {e.get('metadata', {}).get('chunk_id') for e in saved if e.get('category') == 'document_chunk'}
                if not rows or not all(meta['chunk_id'] in ids for _, meta in rows):
                    raise ImportFailure('Durable chunk verification failed')
                receipt.update(
                    status='completed',
                    chunk_count=len(rows),
                    page_count=payload.get('page_count', 1),
                    char_count=payload.get('char_count', 0),
                    chunks_written=len(rows),
                    progress_pct=100,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    completed_at=now(),
                )
                if association is not None:
                    # For an approved link, require the exact durable chunk, not
                    # only an ID. Publish approval atomically with completion.
                    text, meta = rows[0]
                    matching = [entry for entry in saved
                                if entry.get('category') == 'document_chunk'
                                and entry.get('metadata', {}).get('chunk_id') == meta['chunk_id']]
                    if (len(matching) != 1 or matching[0].get('thought') != text
                            or matching[0].get('metadata') != dict(meta, filename=filename)):
                        raise ImportFailure('Durable approved chunk verification failed')
                    receipt[DOCUMENT_ASSOCIATION_FIELD] = association
                self._save('document_source', 'Document chunks persisted and verified', receipt.copy())
                return dict(receipt, duplicate=False)
            except Exception as exc:
                receipt.pop(DOCUMENT_ASSOCIATION_FIELD, None)
                detail = str(exc) if isinstance(exc, ImportFailure) else 'Extraction or indexing failed; retry is safe'
                receipt.update(
                    status='failed',
                    error=detail,
                    failed_at=now(),
                    progress_pct=receipt.get('progress_pct', 0),
                )
                self._save('document_source', 'Document import failed', receipt.copy())
                raise ImportFailure(detail) from exc
            finally:
                _ACTIVE_SOURCES.discard(source)

    def approved_recall_reasons(self, row, question):
        """Recheck source binding at the model context boundary, not row claims."""
        with _LOCK:
            receipt = next((r for r in self.receipts()
                            if r['source_id'] == row.get('source_id')), None)
            reasons = _document_recall_reasons(receipt, row, question)
            if not reasons:
                return []
            matching = [entry for entry in self.memory.memory_log
                        if entry.get('category') == 'document_chunk'
                        and entry.get('metadata', {}).get('chunk_id') == row['chunk_id']]
            if len(matching) != 1 or matching[0].get('thought') != row['text']:
                return []
            meta = matching[0].get('metadata', {})
            if any(meta.get(key) != row.get(key) for key in (
                    'source_id', 'chunk_id', 'content_sha256', 'processing_version',
                    'filename', 'trust', 'page')):
                return []
            return reasons

    def search(self, query, limit=6, *, context_distinct=False):
        """Default search stays lexical; chat can request approved association recall."""
        # Import holds the same lock through durable receipt publication.
        with _LOCK:
            return self._search(query, limit, context_distinct=context_distinct)

    def _search(self, query, limit, *, context_distinct):
        tokens = set(re.findall(r'\w{3,}', query.casefold())) - {'the', 'what', 'which', 'does', 'and', 'from', 'with'}
        if not tokens and not context_distinct:
            return []
        completed = {r['source_id']: r for r in self.receipts() if r['status'] == 'completed'}
        found = []
        for entry in self.memory.memory_log:
            if context_distinct and not isinstance(entry, dict):
                continue
            meta = entry.get('metadata', {})
            if context_distinct and (
                    not isinstance(meta, dict) or not isinstance(meta.get('source_id'), str)):
                continue
            if entry.get('category') != 'document_chunk' or meta.get('source_id') not in completed:
                continue
            text = entry.get('thought') if context_distinct else entry['thought']
            if context_distinct and not is_context_document(dict(meta, text=text)):
                continue
            overlap = tokens & set(re.findall(r'\w{3,}', text.casefold()))
            row = dict(meta, text=text)
            if context_distinct:
                row.pop('recall_reasons', None)
            reasons = (_document_recall_reasons(completed[meta['source_id']], row, query)
                       if context_distinct else [])
            if overlap or reasons:
                row['score'] = len(overlap) / max(len(tokens), 1)
                if reasons:
                    row['score'] = max(row['score'], 0.85)
                    row['recall_reasons'] = reasons
                found.append(row)
        if context_distinct:
            ranked = sorted(found, key=lambda x: (
                -x['score'], not bool(x.get('recall_reasons')), x['source_id'], x['chunk_id']))
            # Group only exact original text, not token sets, normalized
            # paraphrases, or untrusted source hash metadata.
            seen = set()
            distinct = []
            for row in ranked:
                if row['text'] not in seen:
                    seen.add(row['text'])
                    distinct.append(row)
            ranked = distinct
        else:
            ranked = sorted(found, key=lambda x: (-x['score'], x['chunk_id']))
        matches = ranked[:limit]
        if matches:
            from project_guardian.runtime_activity import record
            record('Document evidence retrieved')
        return matches


def shutil_disk_usage(path: Path):
    import shutil
    return shutil.disk_usage(path).free


if __name__ == '__main__':
    try:
        worker_memory_limit()
        src = Path(sys.argv[1])
        extension = sys.argv[2]
        source = 'doc_' + digest(src.read_bytes()[: min(src.stat().st_size, MAX_BYTES + 1)])
        # Stable source_id for worker output must match parent: parent names file doc_<sha>.ext
        # Recover sha from filename when staged as doc_<hex>...
        name = src.name
        if name.startswith('doc_') or name.startswith('_preview_doc_'):
            hexpart = name.split('doc_', 1)[1]
            hexpart = hexpart.split('.')[0]
            if len(hexpart) == 64 and all(c in '0123456789abcdef' for c in hexpart):
                source = 'doc_' + hexpart
        result = extract_chunks(src, extension, source)
        value = {
            'page_count': result['page_count'],
            'char_count': result['char_count'],
            'chunks': [{'t': text, 'm': meta} for text, meta in result['chunks']],
        }
    except Exception as exc:
        value = {
            'error': str(exc)[:400] if isinstance(exc, (ImportFailure, UnicodeDecodeError)) else 'Malformed or unreadable document'
        }
    # Parent sets deadline; never put source contents on stdout or activity logs.
    with Path(sys.argv[3]).open('x', encoding='utf-8') as output:
        output.write(json.dumps(value, ensure_ascii=True))
