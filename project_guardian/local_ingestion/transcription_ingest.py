"""Import phone voice-to-text / transcription files into normalized local storage."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".vtt", ".srt"})
MANIFEST_FILENAME = "ingest_manifest.jsonl"
DEFAULT_MAX_FILE_MB = 5.0
_TEXT_SUBDIR = "text"
_META_SUBDIR = "metadata"

_VTT_TIMING_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}",
)
_SRT_TIMING_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}",
)


def default_dest_dir(repo_root: Optional[Path] = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "data" / "phone_transcriptions"


@dataclass
class FileIngestResult:
    original_filename: str
    original_path: str
    imported_at: str
    source_size_bytes: int
    detected_extension: str
    sha256: str
    output_text_path: Optional[str] = None
    output_metadata_path: Optional[str] = None
    status: str = "pending"

    def to_manifest_record(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IngestReport:
    source_dir: str
    dest_dir: str
    apply: bool
    recursive: bool
    max_file_mb: float
    scanned: int = 0
    ingested: int = 0
    duplicates: int = 0
    skipped: int = 0
    results: List[FileIngestResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_dir": self.source_dir,
            "dest_dir": self.dest_dir,
            "apply": self.apply,
            "recursive": self.recursive,
            "max_file_mb": self.max_file_mb,
            "scanned": self.scanned,
            "ingested": self.ingested,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "results": [r.to_manifest_record() for r in self.results],
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned or "transcription"


def _output_basename(sha256: str, original_name: str) -> str:
    return f"{sha256[:12]}_{_safe_stem(original_name)}"


def _read_known_hashes(manifest_path: Path) -> Set[str]:
    if not manifest_path.is_file():
        return set()
    hashes: Set[str] = set()
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                digest = str(record.get("sha256") or "").strip()
                if digest and record.get("status") == "ingested":
                    hashes.add(digest)
    except OSError:
        pass
    return hashes


def _looks_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(1 for b in sample if b < 9 or (13 < b < 32 and b != 27))
    return (non_text / len(sample)) > 0.30


def _decode_text(raw: bytes) -> Optional[str]:
    if _looks_binary(raw):
        return None
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_vtt(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("WEBVTT"):
            continue
        if upper.startswith("NOTE"):
            continue
        if _VTT_TIMING_RE.match(stripped):
            continue
        if stripped.isdigit():
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def normalize_srt(text: str) -> str:
    blocks = re.split(r"\n\s*\n", text.strip())
    lines: List[str] = []
    for block in blocks:
        block_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not block_lines:
            continue
        payload = block_lines
        if payload[0].isdigit():
            payload = payload[1:]
        if payload and _SRT_TIMING_RE.match(payload[0]):
            payload = payload[1:]
        lines.extend(payload)
    return "\n".join(lines).strip()


def normalize_transcription_text(text: str, extension: str) -> str:
    ext = extension.lower()
    if ext == ".vtt":
        return normalize_vtt(text)
    if ext == ".srt":
        return normalize_srt(text)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _iter_candidate_files(source_dir: Path, *, recursive: bool) -> Iterable[Path]:
    if recursive:
        for root, dirnames, filenames in os.walk(source_dir, followlinks=False):
            root_path = Path(root)
            dirnames[:] = [
                d
                for d in dirnames
                if not (root_path / d).is_symlink()
            ]
            for name in sorted(filenames):
                yield root_path / name
    else:
        for entry in sorted(source_dir.iterdir()):
            if entry.is_file():
                yield entry


def _skip_result(
    path: Path,
    *,
    status: str,
    extension: str = "",
    size_bytes: int = 0,
    sha256: str = "",
) -> FileIngestResult:
    return FileIngestResult(
        original_filename=path.name,
        original_path=str(path.resolve()),
        imported_at=_utc_now_iso(),
        source_size_bytes=size_bytes,
        detected_extension=extension,
        sha256=sha256,
        status=status,
    )


def ingest_transcriptions(
    source_dir: Path,
    dest_dir: Path,
    *,
    apply: bool = False,
    recursive: bool = False,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
) -> IngestReport:
    source = source_dir.expanduser().resolve()
    dest = dest_dir.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")

    max_bytes = int(max_file_mb * 1024 * 1024)
    manifest_path = dest / MANIFEST_FILENAME
    known_hashes = _read_known_hashes(manifest_path)

    report = IngestReport(
        source_dir=str(source),
        dest_dir=str(dest),
        apply=apply,
        recursive=recursive,
        max_file_mb=max_file_mb,
    )

    text_dir = dest / _TEXT_SUBDIR
    meta_dir = dest / _META_SUBDIR

    for path in _iter_candidate_files(source, recursive=recursive):
        report.scanned += 1
        ext = path.suffix.lower()

        if path.is_symlink():
            report.skipped += 1
            report.results.append(_skip_result(path, status="skipped_symlink"))
            continue

        if ext not in ALLOWED_EXTENSIONS:
            report.skipped += 1
            report.results.append(
                _skip_result(path, status="skipped_unsupported", extension=ext)
            )
            continue

        try:
            size_bytes = path.stat().st_size
        except OSError:
            report.skipped += 1
            report.results.append(_skip_result(path, status="skipped_unreadable", extension=ext))
            continue

        if size_bytes > max_bytes:
            report.skipped += 1
            report.results.append(
                _skip_result(
                    path,
                    status="skipped_oversized",
                    extension=ext,
                    size_bytes=size_bytes,
                )
            )
            continue

        try:
            raw = path.read_bytes()
        except OSError:
            report.skipped += 1
            report.results.append(
                _skip_result(
                    path,
                    status="skipped_unreadable",
                    extension=ext,
                    size_bytes=size_bytes,
                )
            )
            continue

        decoded = _decode_text(raw)
        if decoded is None:
            report.skipped += 1
            report.results.append(
                _skip_result(
                    path,
                    status="skipped_binary",
                    extension=ext,
                    size_bytes=size_bytes,
                )
            )
            continue

        normalized = normalize_transcription_text(decoded, ext)
        if not normalized:
            report.skipped += 1
            report.results.append(
                _skip_result(
                    path,
                    status="skipped_empty",
                    extension=ext,
                    size_bytes=size_bytes,
                )
            )
            continue

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        imported_at = _utc_now_iso()
        base = _output_basename(digest, path.name)
        text_out = text_dir / f"{base}.txt"
        meta_out = meta_dir / f"{base}.meta.json"

        if digest in known_hashes:
            report.duplicates += 1
            report.results.append(
                FileIngestResult(
                    original_filename=path.name,
                    original_path=str(path.resolve()),
                    imported_at=imported_at,
                    source_size_bytes=size_bytes,
                    detected_extension=ext,
                    sha256=digest,
                    output_text_path=str(text_out),
                    output_metadata_path=str(meta_out),
                    status="duplicate",
                )
            )
            continue

        if text_out.exists() or meta_out.exists():
            report.duplicates += 1
            report.results.append(
                FileIngestResult(
                    original_filename=path.name,
                    original_path=str(path.resolve()),
                    imported_at=imported_at,
                    source_size_bytes=size_bytes,
                    detected_extension=ext,
                    sha256=digest,
                    output_text_path=str(text_out),
                    output_metadata_path=str(meta_out),
                    status="duplicate",
                )
            )
            known_hashes.add(digest)
            continue

        result = FileIngestResult(
            original_filename=path.name,
            original_path=str(path.resolve()),
            imported_at=imported_at,
            source_size_bytes=size_bytes,
            detected_extension=ext,
            sha256=digest,
            output_text_path=str(text_out),
            output_metadata_path=str(meta_out),
            status="dry_run" if not apply else "ingested",
        )

        if apply:
            text_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            text_out.write_text(normalized + "\n", encoding="utf-8", newline="\n")
            metadata = result.to_manifest_record()
            meta_out.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            dest.mkdir(parents=True, exist_ok=True)
            with manifest_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            known_hashes.add(digest)
            report.ingested += 1
        else:
            report.ingested += 1

        report.results.append(result)

    return report
