"""Worker path identity regressions; no network or live memory."""
import os
from pathlib import Path

import pytest

import elysia_browser_worker as worker


def test_worker_store_survives_noncanonical_code_path(tmp_path, monkeypatch):
    code = tmp_path / "app"
    code.mkdir()
    holder = tmp_path / "holder"
    holder.mkdir()
    alias = holder / ".." / "app"
    assert alias != code and alias.resolve() == code.resolve()
    monkeypatch.setattr(worker, "CODE", alias)
    path = worker.workspace("alias")
    assert path == code.resolve() / ".synthetic-pilot-stores" / "browser-alias"
    assert path.is_dir() and list(path.iterdir()) == []


def test_linked_code_root_stays_refused(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    monkeypatch.setattr(worker, "CODE", link)
    with pytest.raises(ValueError, match="linked synthetic workspace refused"):
        worker.workspace("alias")
    assert list(real.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="native Windows 8.3 worker path")
def test_native_windows_short_code_path(tmp_path, monkeypatch):
    import ctypes
    code = tmp_path / "app"
    code.mkdir()
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(tmp_path), buffer, len(buffer))
    if not length or length >= len(buffer) or buffer.value.casefold() == str(tmp_path).casefold():
        pytest.skip("filesystem has no short alias for disposable parent")
    monkeypatch.setattr(worker, "CODE", Path(buffer.value) / "app")
    path = worker.workspace("alias")
    assert path == code.resolve() / ".synthetic-pilot-stores" / "browser-alias"
    assert path.is_dir()
