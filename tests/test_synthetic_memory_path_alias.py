"""Memory-store path identity must survive Windows short names and aliases.

No user data, providers or non-loopback network. All stores are disposable.
"""
import os
from pathlib import Path

import pytest

from elysia_synthetic_learning import SyntheticLearningStore
from project_guardian.local_ingestion.apply_transaction import (
    ApplyTransaction, ApplyTransactionError, destination_lock,
)


def test_noncanonical_directory_spelling_cannot_break_memory_writes(tmp_path):
    # This spelling differs lexically from the transaction's resolved root on
    # both Linux and Windows. Windows 8.3 TEMP aliases cause the same mismatch.
    holding = tmp_path / "holding"
    holding.mkdir()
    canonical = tmp_path / "store"
    canonical.mkdir()
    alias = holding / ".." / "store"
    assert alias.resolve() == canonical.resolve()
    assert alias != canonical

    # Reproduce the original problem at the unchanged transaction boundary.
    with destination_lock(alias, write=True):
        tx = ApplyTransaction(alias)
        try:
            with pytest.raises(ApplyTransactionError, match="inside destination"):
                tx.write(alias / "synthetic-learning.json", b"fictional")
        finally:
            tx.abort()

    store = SyntheticLearningStore(alias, ())
    assert store.path == canonical.resolve()
    assert store.index == store.path / "synthetic-learning.json"
    assert store.learn("bell", "Fictional brass bell rings twice.") == "Fictional fact learned."
    assert store.learn("bell", "Fictional brass bell rings once.", correction=True).startswith("Fictional fact corrected")
    assert len(store.history("bell")) == 2
    before = {p.relative_to(store.path).as_posix(): p.read_bytes()
              for p in store.path.rglob("*") if p.is_file()}
    reopened = SyntheticLearningStore(canonical, ())
    assert len(reopened.history("bell")) == 2
    assert reopened.history("bell")[-1].endswith("Fictional brass bell rings once.")
    after = {p.relative_to(store.path).as_posix(): p.read_bytes()
             for p in store.path.rglob("*") if p.is_file()}
    assert before == after
    assert not (store.path / ".chatgpt_apply_transaction").exists()


@pytest.mark.parametrize("nested", [False, True])
def test_symlinked_store_or_parent_is_refused_without_writes(tmp_path, nested):
    root = tmp_path / "real"
    root.mkdir()
    real_store = root / "store"
    real_store.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(real_store if not nested else root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    attempted = link / "store" if nested else link
    with pytest.raises(ValueError, match="symlinks or junctions"):
        SyntheticLearningStore(attempted, ())
    assert list(real_store.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="native Windows short-path identity")
def test_windows_short_path_if_available(tmp_path):
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    original = str(tmp_path)
    returned = ctypes.windll.kernel32.GetShortPathNameW(original, buffer, len(buffer))
    if returned == 0 or returned >= len(buffer) or buffer.value.casefold() == original.casefold():
        pytest.skip("filesystem did not provide an 8.3 alias")
    short = Path(buffer.value)
    assert short.resolve() == tmp_path.resolve()
    store = short / "fictional"
    store.mkdir()
    system = SyntheticLearningStore(store, ())
    assert system.path == (tmp_path / "fictional").resolve()
    assert system.learn("north", "Fictional map points north.") == "Fictional fact learned."
    assert "north" in system.history("north")[-1]
