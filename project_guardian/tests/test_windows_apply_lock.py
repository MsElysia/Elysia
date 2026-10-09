"""Win32 failure contracts plus native Windows process/alias/abandonment proof.

Mocked API tests run everywhere; the native test MUST run on Windows CI.
The shared transaction suite also runs real process collisions and death there.
"""
import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from project_guardian.local_ingestion import apply_transaction as tx
from project_guardian.local_ingestion.memory_intelligence import load_memory_intelligence_records

ROOT = Path(__file__).resolve().parents[2]


class FakeAPI:
    def __init__(self, *, handle=123, status=0, release=True, close=True):
        self.handle, self.status = handle, status
        self.release, self.close = release, close
        self.calls = []

    def CreateMutexW(self, attributes, owner, name):
        self.calls.append(("create", attributes, owner, name))
        return self.handle

    def WaitForSingleObject(self, handle, timeout):
        self.calls.append(("wait", handle, timeout))
        return self.status

    def ReleaseMutex(self, handle):
        self.calls.append(("release", handle))
        return self.release

    def CloseHandle(self, handle):
        self.calls.append(("close", handle))
        return self.close


@pytest.mark.parametrize("status", [0, 0x80])
def test_windows_ownership_always_recovers_before_read_and_releases(tmp_path, monkeypatch, status):
    api = FakeAPI(status=status)
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    monkeypatch.setattr(tx, "_windows_api", lambda: api)
    monkeypatch.setattr(tx, "recover", lambda dest: api.calls.append(("recover", dest)))
    name = tx._windows_mutex_name(tmp_path)
    with tx.destination_lock(tmp_path):
        api.calls.append(("read",))
        with tx.destination_lock(tmp_path):
            pass  # Nested reads do not reacquire or repeat recovery.
        with pytest.raises(tx.ApplyTransactionError, match="nested apply"):
            with tx.destination_lock(tmp_path, write=True):
                pytest.fail("nested apply allowed")
    assert api.calls == [("create", None, False, name), ("wait", 123, 0),
                         ("recover", tmp_path), ("read",), ("release", 123), ("close", 123)]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status", [0x102, 0xFFFFFFFF, 17])
@pytest.mark.parametrize("write", [False, True])
def test_timeout_failed_or_unknown_wait_never_recovers_or_serves(tmp_path, monkeypatch, status, write):
    api = FakeAPI(status=status)
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    monkeypatch.setattr(tx, "_windows_api", lambda: api)
    def forbidden(*args):
        pytest.fail("recovery before lock acquisition")
    monkeypatch.setattr(tx, "recover", forbidden)
    with pytest.raises(tx.ApplyTransactionError, match="lock refused"):
        with tx.destination_lock(tmp_path, write=write):
            pytest.fail("served without ownership")
    assert api.calls[-1] == ("close", 123)
    assert not any(c[0] == "release" for c in api.calls)
    assert list(tmp_path.iterdir()) == []


def test_creation_denied_never_falls_back_or_mutates(tmp_path, monkeypatch):
    api = FakeAPI(handle=None)
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    monkeypatch.setattr(tx, "_windows_api", lambda: api)
    with pytest.raises(tx.ApplyTransactionError, match="lock refused"):
        with tx.destination_lock(tmp_path, write=True):
            pytest.fail("creation denial bypassed")
    assert len(api.calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("error", [ImportError, AttributeError, OSError])
def test_unavailable_windows_api_refuses_reader_with_journal_and_writer(tmp_path, monkeypatch, error):
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    def unavailable():
        raise error("injected")
    monkeypatch.setattr(tx, "_windows_api", unavailable)
    root = tmp_path / tx.TRANSACTION_DIR
    root.mkdir()
    (root / "stage-0").write_bytes(b"interrupted")
    for write in (False, True):
        with pytest.raises(tx.ApplyTransactionError, match="unavailable on Windows"):
            with tx.destination_lock(tmp_path, write=write):
                pytest.fail("API failure bypassed")
    assert (root / "stage-0").read_bytes() == b"interrupted"


@pytest.mark.parametrize("where", ["recover", "body"])
def test_windows_exception_releases_and_closes_owned_handle(tmp_path, monkeypatch, where):
    api = FakeAPI(status=0x80)
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    monkeypatch.setattr(tx, "_windows_api", lambda: api)
    def recovery(dest):
        if where == "recover":
            raise tx.ApplyTransactionError("injected recovery failure")
    monkeypatch.setattr(tx, "recover", recovery)
    with pytest.raises((tx.ApplyTransactionError, OSError), match="injected"):
        with tx.destination_lock(tmp_path):
            raise OSError("injected body failure")
    assert api.calls[-2:] == [("release", 123), ("close", 123)]
    assert getattr(tx._held, "destinations") == set()


@pytest.mark.parametrize("release,close", [(False, True), (True, False)])
def test_handle_cleanup_failure_is_reported_and_close_is_attempted(monkeypatch, release, close):
    api = FakeAPI(release=release, close=close)
    monkeypatch.setattr(tx, "_windows_api", lambda: api)
    with pytest.raises(tx.ApplyTransactionError, match="failed on Windows"):
        with tx._windows_mutex("test"):
            pass
    assert api.calls[-2:] == [("release", 123), ("close", 123)]


def test_mutex_identity_uses_directory_identity_not_spelling(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    assert tx._windows_mutex_name(tmp_path) != tx._windows_mutex_name(other)
    assert tx._windows_mutex_name(tmp_path).startswith("Global\\Elysia.ChatGPTApply.v1.")
    original = Path.stat
    def aliases(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == other:
            return original(tmp_path)
        return result
    monkeypatch.setattr(Path, "stat", aliases)
    assert tx._windows_mutex_name(tmp_path) == tx._windows_mutex_name(other)


def test_missing_or_zero_file_identity_refuses_windows_lock(tmp_path, monkeypatch):
    with pytest.raises(tx.ApplyTransactionError, match="identity unavailable"):
        tx._windows_mutex_name(tmp_path / "missing")
    original = Path.stat
    def zero_identity(path, *args, **kwargs):
        if path == tmp_path:
            return SimpleNamespace(st_dev=0, st_ino=0, st_mode=0o40755)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", zero_identity)
    with pytest.raises(tx.ApplyTransactionError, match="identity unavailable"):
        tx._windows_mutex_name(tmp_path)


@pytest.mark.parametrize("relative", [".", "a:stream", "C:relative", "NUL", "NUL/file", "COM1.txt",
    "trailing./file", "trailing /file", "bad?name", "bad\x01name", "../escape", "..\\escape",
    tx.TRANSACTION_DIR.upper() + "/manifest.json", tx.TRANSACTION_DIR.upper() + "_CLEANUP/file"])
def test_windows_journal_paths_cannot_alias_reserved_names(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(tx, "_PLATFORM", "nt")
    with pytest.raises(tx.ApplyTransactionError):
        tx._target(tmp_path, relative)


def test_other_thread_refuses_same_destination_while_owner_holds_it(tmp_path):
    results = []
    def contender():
        try:
            with tx.destination_lock(tmp_path, write=True):
                results.append("incorrectly acquired")
        except tx.ApplyTransactionError:
            results.append("refused")
    with tx.destination_lock(tmp_path, write=True):
        thread = threading.Thread(target=contender)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert results == ["refused"]
    with tx.destination_lock(tmp_path, write=True):
        pass


@pytest.mark.skipif(os.name != "nt", reason="native Windows kernel proof")
def test_native_exact_parent_refuses_then_current_apply_succeeds(tmp_path):
    from project_guardian.tests.test_chatgpt_apply_transaction import fixture, bytes_at, assert_complete
    from project_guardian.local_ingestion.chatgpt_export_ingest import apply_chatgpt_export
    parent = "931576224432b6db6f4290eee0ea4c0aa9bd9c73"
    result = subprocess.run(["git", "show", parent + ":project_guardian/local_ingestion/apply_transaction.py"],
                            cwd=ROOT, capture_output=True, check=True, timeout=15)
    source = tmp_path / "parent_transaction.py"
    source.write_bytes(result.stdout)
    spec = importlib.util.spec_from_file_location("parent_transaction", source)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    dest, preview = fixture(tmp_path)
    before = bytes_at(dest)
    with pytest.raises(old.ApplyTransactionError, match="unavailable on this platform"):
        with old.destination_lock(dest, write=True):
            pytest.fail("exact parent unexpectedly supports Windows")
    assert bytes_at(dest) == before
    report = apply_chatgpt_export(preview_json=preview, apply=True).report
    assert report["staged_count"] == 1
    assert report["model_called"] is report["embeddings_used"] is report["live_memory_written"] is False
    assert_complete(dest)


@pytest.mark.skipif(os.name != "nt", reason="native Windows kernel proof")
def test_native_case_alias_contention_abandonment_and_recovery(tmp_path, monkeypatch):
    from project_guardian.tests.test_chatgpt_apply_transaction import wait_ready
    dest = tmp_path / "MixedCaseDestination"
    dest.mkdir()
    alias = dest.with_name(dest.name.upper())
    assert tx._windows_mutex_name(dest) == tx._windows_mutex_name(alias)
    name = tx._windows_mutex_name(dest)
    api = tx._windows_api()
    # Retain an unowned handle so kernel abandonment survives process death.
    watcher = api.CreateMutexW(None, False, name)
    assert watcher
    ready = tmp_path / "ready"
    code = '''
import sys
from pathlib import Path
from project_guardian.local_ingestion import apply_transaction as tx
with tx.destination_lock(Path(sys.argv[1]), write=True):
    root = Path(sys.argv[1]) / tx.TRANSACTION_DIR
    root.mkdir()
    (root / 'stage-0').write_bytes(b'interrupted')
    Path(sys.argv[2]).write_text('ready')
    sys.stdin.readline()
'''
    process = subprocess.Popen([sys.executable, "-c", code, str(dest), str(ready)],
                               cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        wait_ready(process, ready)
        with pytest.raises(tx.ApplyTransactionError, match="lock refused"):
            load_memory_intelligence_records(alias)
        process.kill()
        process.communicate(timeout=15)
        waits = []
        def wait(handle, timeout):
            result = api.WaitForSingleObject(handle, timeout)
            waits.append(result)
            return result
        wrapper = SimpleNamespace(CreateMutexW=api.CreateMutexW, WaitForSingleObject=wait,
                                  ReleaseMutex=api.ReleaseMutex, CloseHandle=api.CloseHandle)
        monkeypatch.setattr(tx, "_windows_api", lambda: wrapper)
        assert load_memory_intelligence_records(alias) == []
        assert waits == [0x80]
        assert list(dest.iterdir()) == []
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        assert api.CloseHandle(watcher)
