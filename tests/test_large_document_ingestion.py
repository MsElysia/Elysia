"""Large-document ingestion past the former 500k-character hard fail.

Uses disposable MemoryCore only. No model, network, or personal data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from project_guardian.document_ingestion import (
    MAX_EXTRACTED_CHARS,
    DocumentLibrary,
    ImportFailure,
)
from project_guardian.memory import MemoryCore


def _memory(path: Path) -> MemoryCore:
    return MemoryCore(
        filepath=str(path),
        enable_timeline_logging=False,
        enable_vector_search=False,
    )


def _text(n: int) -> str:
    begin, mid, end = "BEGIN_MARK_L\n", "\nMID_MARK_L\n", "\nEND_MARK_L\n"
    unit = "abcdefghijklmnopqrstuvwxyz012345\n"
    core = n - len(begin) - len(mid) - len(end)
    reps = max(0, core // len(unit))
    half = reps // 2
    text = begin + unit * half + mid + unit * (reps - half) + end
    if len(text) < n:
        text += "x" * (n - len(text))
    return text[:n]


@pytest.mark.parametrize("n", [499_999, 500_000, 500_001])
def test_boundary_around_former_500k_limit(tmp_path, n):
    library = DocumentLibrary(_memory(tmp_path / "m.json"))
    receipt = library.import_bytes(f"b{n}.txt", _text(n).encode())
    assert receipt["status"] == "completed"
    assert receipt["char_count"] == n
    assert receipt["chunk_count"] >= n // 1000


def test_multimillion_markers_dedupe_and_preserved_source(tmp_path):
    library = DocumentLibrary(_memory(tmp_path / "m.json"))
    raw = _text(1_200_000).encode()
    receipt = library.import_bytes("big.txt", raw)
    assert receipt["status"] == "completed"
    assert receipt["char_count"] == 1_200_000
    assert library.search("BEGIN_MARK_L")
    assert library.search("MID_MARK_L")
    assert library.search("END_MARK_L")
    assert (library.root / receipt["managed_copy"]).read_bytes() == raw
    assert library.import_bytes("renamed.txt", raw)["duplicate"] is True


def test_reject_over_extracted_char_limit_without_truncation(tmp_path, monkeypatch):
    import project_guardian.document_ingestion as di

    monkeypatch.setattr(di, "MAX_EXTRACTED_CHARS", 10_000)
    src = tmp_path / "too_big.txt"
    src.write_bytes(_text(12_000).encode())
    with pytest.raises(ImportFailure, match="resource limit|characters"):
        di.extract_chunks(src, ".txt", "doc_test")
    # Full import path still refuses completed receipts when worker surfaces the error.
    library = DocumentLibrary(_memory(tmp_path / "m.json"))

    def boom(original, extension, output, raw_len):
        raise ImportFailure(
            "Extracted text would be 12,000 characters, which exceeds the "
            "10,000-character resource limit"
        )

    monkeypatch.setattr(library, "_run_extract_worker", boom)
    with pytest.raises(ImportFailure, match="resource limit|characters"):
        library.import_bytes("too_big.txt", _text(12_000).encode())
    assert not any(r["status"] == "completed" for r in library.receipts())
    assert not library.search("BEGIN_MARK_L")
