"""Bounded local imports into the runtime's existing MemoryCore, never personal facts.

Source receipts and chunks share the canonical store. Only a completed receipt makes
chunks searchable; interrupted writes can be retried without duplicate chunk IDs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone

# The extractor also runs directly as a file in a bounded subprocess.
# Preserve both package imports and the standalone worker entrypoint.
if __package__:
    from .retrieval_vocabulary import normalize_retrieval_term
else:
    from retrieval_vocabulary import normalize_retrieval_term

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 500_000
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


def extract(path, extension):
    """Runs in a deadline-limited worker; output and decompression are bounded."""
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ImportFailure('File exceeds 8 MiB')
    if extension in {'.txt', '.md', '.csv'}:
        if b'\x00' in raw or raw.startswith((b'%PDF-', b'PK\x03\x04')):
            raise ImportFailure('File contents do not match readable UTF-8 text')
        pages = [raw.decode('utf-8-sig')]
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
            text = page.extract_text() or ''
            total += len(text)
            if total > MAX_TEXT:
                raise ImportFailure('Extracted text exceeds 500,000 characters')
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
        pages = ['\n'.join([p.text for p in document.paragraphs] + [
            ' | '.join(c.text for c in row.cells) for table in document.tables for row in table.rows
        ])]
    pages = [p.replace('\r\n', '\n').replace('\r', '\n').strip() for p in pages]
    if sum(map(len, pages)) > MAX_TEXT:
        raise ImportFailure('Extracted text exceeds 500,000 characters')
    if not any(pages):
        raise ImportFailure('No readable text extracted. Scanned documents require local OCR, which is unavailable in this importer')
    return pages


def chunks(pages, source):
    result = []
    for page, text in enumerate(pages, 1):
        for start in range(0, len(text), 1000):
            piece = text[start:start + 1200]
            if not piece.strip():
                continue
            n = len(result)
            result.append((piece, {
                'source_id': source, 'chunk_id': f'{source}:{VERSION}:{n}',
                'chunk_number': n, 'page': page, 'start': start, 'end': start + len(piece),
                'processing_version': VERSION, 'content_sha256': digest(piece.encode()),
                'trust': 'untrusted_document',
            }))
    return result


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
            raise ImportFailure('File must contain 1 byte to 8 MiB')
        source = 'doc_' + digest(raw)
        previous = next((r for r in self.receipts() if r['source_id'] == source and r['status'] == 'completed'), None)
        # Stage bytes to a disposable temp under the library root for the worker.
        physical(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = physical(self.root / ('_preview_' + source + extension))
        try:
            with staging.open('wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            output = staging.with_suffix('.extracted.json')
            physical(output)
            subprocess.run(
                [sys.executable, '-B', str(Path(__file__).resolve()), str(staging), extension, str(output)],
                timeout=30, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            payload = json.loads(output.read_text(encoding='utf-8'))
            if payload.get('error'):
                raise ImportFailure(payload['error'])
            pages = payload['pages']
            rows = chunks(pages, source)
            preview = '\n\n'.join(p for p in pages if p)[:4000]
            return {
                'filename': filename,
                'source_id': source,
                'sha256': digest(raw),
                'file_type': extension,
                'page_count': len(pages),
                'chunk_count': len(rows),
                'chunk_settings': {
                    'target_chars': 1000,
                    'overlap_chars': 200,
                    'processing_version': VERSION,
                },
                'preview_text': preview,
                'already_imported': bool(previous),
                'ocr_available': False,
                'ocr_note': (
                    'Local OCR is not available in this importer. '
                    'Scanned PDFs without extractable text will fail clearly instead of saving empty text.'
                ),
            }
        finally:
            for leftover in (staging, staging.with_suffix('.extracted.json')):
                try:
                    if leftover.exists():
                        leftover.unlink()
                except OSError:
                    pass

    def import_bytes(self, filename, raw):
        if not filename or len(filename) > 180 or '/' in filename or '\\' in filename or ':' in filename or filename in {'.', '..'}:
            raise ImportFailure('Unsafe filename')
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED:
            raise ImportFailure('Unsupported format; choose TXT, Markdown, PDF, DOCX or CSV')
        if not raw or len(raw) > MAX_BYTES:
            raise ImportFailure('File must contain 1 byte to 8 MiB')
        source = 'doc_' + digest(raw)
        with _LOCK:
            previous = next((r for r in self.receipts() if r['source_id'] == source), None)
            if previous and previous['status'] == 'completed':
                return dict(previous, duplicate=True)
            if previous and previous.get('attempt', 0) >= 3:
                raise ImportFailure('Import retry limit reached (3 attempts)')
            physical(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            original = physical(self.root / (source + extension))
            if original.exists():
                if digest(original.read_bytes()) != digest(raw):
                    raise ImportFailure('Preserved source hash mismatch')
            else:
                with original.open('xb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            receipt = dict(source_id=source, filename=filename, sha256=digest(raw),
                           imported_at=now(), managed_copy=original.name, file_type=extension,
                           status='processing', attempt=(previous or {}).get('attempt', 0) + 1,
                           processing_version=VERSION)
            self._save('document_source', 'Document import started', receipt.copy())
            _ACTIVE_SOURCES.add(source)
            try:
                output = original.with_suffix('.extracted.json')
                physical(output)
                subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                                str(original), extension, str(output)],
                               timeout=30, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if output.stat().st_size > 4 * MAX_TEXT:
                    raise ImportFailure('Extraction output too large')
                payload = json.loads(output.read_text(encoding='utf-8'))
                if payload.get('error'):
                    raise ImportFailure(payload['error'])
                rows = chunks(payload['pages'], source)
                existing = {e.get('metadata', {}).get('chunk_id') for e in self.memory.memory_log if e.get('category') == 'document_chunk'}
                for text, meta in rows:
                    if meta['chunk_id'] not in existing:
                        self._save('document_chunk', text, dict(meta, filename=filename))
                # Check durable bytes, not merely the in-process list.
                saved = json.loads(Path(self.memory.filepath).read_text(encoding='utf-8'))
                ids = {e.get('metadata', {}).get('chunk_id') for e in saved if e.get('category') == 'document_chunk'}
                if not rows or not all(meta['chunk_id'] in ids for _, meta in rows):
                    raise ImportFailure('Durable chunk verification failed')
                receipt.update(status='completed', chunk_count=len(rows), page_count=len(payload['pages']), completed_at=now())
                self._save('document_source', 'Document chunks persisted and verified', receipt.copy())
                return dict(receipt, duplicate=False)
            except Exception as exc:
                detail = str(exc) if isinstance(exc, ImportFailure) else 'Extraction or indexing failed; retry is safe'
                receipt.update(status='failed', error=detail, failed_at=now())
                self._save('document_source', 'Document import failed', receipt.copy())
                raise ImportFailure(detail) from exc
            finally:
                _ACTIVE_SOURCES.discard(source)

    def search(self, query, limit=6):
        tokens = {normalize_retrieval_term(w) for w in re.findall(r'\w{3,}', query.casefold())} - {'the', 'what', 'which', 'does', 'and', 'from', 'with'}
        if not tokens:
            return []
        completed = {r['source_id'] for r in self.receipts() if r['status'] == 'completed'}
        found = []
        for entry in self.memory.memory_log:
            meta = entry.get('metadata', {})
            if entry.get('category') != 'document_chunk' or meta.get('source_id') not in completed:
                continue
            text = entry['thought']
            overlap = tokens & {normalize_retrieval_term(w) for w in re.findall(r'\w{3,}', text.casefold())}
            if overlap:
                found.append(dict(meta, text=text, score=len(overlap) / len(tokens)))
        matches = sorted(found, key=lambda x: (-x['score'], x['chunk_id']))[:limit]
        if matches:
            from project_guardian.runtime_activity import record
            record('Document evidence retrieved')
        return matches


if __name__ == '__main__':
    try:
        worker_memory_limit()
        value = {'pages': extract(Path(sys.argv[1]), sys.argv[2])}
    except Exception as exc:
        value = {'error': str(exc)[:250] if isinstance(exc, (ImportFailure, UnicodeDecodeError)) else 'Malformed or unreadable document'}
    # Parent sets deadline; never put source contents on stdout or activity logs.
    Path(sys.argv[3]).write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
