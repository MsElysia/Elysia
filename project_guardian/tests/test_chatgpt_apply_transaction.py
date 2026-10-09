"""Crash and collision regressions at the real local ChatGPT apply boundary."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from project_guardian.local_ingestion import apply_transaction as transaction
from project_guardian.local_ingestion.chatgpt_export_ingest import (
    ChatGPTExportIngestError, apply_chatgpt_export, preview_chatgpt_export,
)
from project_guardian.local_ingestion.memory_intelligence import (
    load_memory_intelligence_records, query_memory_intelligence, expand_persisted_highlight,
)
from project_guardian.local_ingestion.memory_candidates import review_queue_path, read_known_candidate_ids
from project_guardian.local_ingestion.memory_candidate_review import load_queue_candidates

pytestmark = pytest.mark.skipif(os.name not in ("posix", "nt"), reason="supported OS locking required")
ROOT = Path(__file__).resolve().parents[2]


def fixture(tmp_path, *, existing=False):
    export = tmp_path / "export.json"
    dest = tmp_path / "dest"
    data = [{"id": "c1", "title": "Roof", "mapping": {"n": {"message": {
        "author": {"role": "user"}, "content": {"parts": ["Roof estimate 500 dollars."]},
    }}}}]
    export.write_text(json.dumps(data))
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    if existing:
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
        # Same rendered source, different original bytes: overwrite an existing
        # intelligence record and reports as well as publishing a new origin.
        data[0]["extra_metadata"] = "new origin"
        export.write_text(json.dumps(data))
        preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    return dest, Path(preview.json_path)


def bytes_at(dest):
    return {p.relative_to(dest).as_posix(): p.read_bytes()
            for p in dest.rglob("*") if p.is_file()}


def assert_complete(dest, count=1):
    rows = load_queue_candidates(review_queue_path(dest))
    assert len(rows) == count
    assert len(review_queue_path(dest).read_text().splitlines()) == count
    for row in rows:
        assert Path(row["source_text_path"]).is_file()
        assert Path(row["source_metadata_path"]).is_file()
        assert row["live_memory_written"] is False
    found = query_memory_intelligence(dest, "Roof")
    assert found
    for item in found:
        for highlight in item["highlights"]:
            expanded = expand_persisted_highlight(dest, highlight["highlight_id"])
            assert "extra_metadata" in expanded["original_raw_source"] or "Roof" in expanded["original_raw_source"]
    assert not (dest / transaction.TRANSACTION_DIR).exists()


def wait_ready(process, ready):
    deadline = time.monotonic() + 15
    while not ready.exists():
        if process.poll() is not None:
            out, err = process.communicate()
            pytest.fail(f"worker exited before injection: {out}\n{err}")
        if time.monotonic() >= deadline:
            process.kill()
            process.communicate()
            pytest.fail("worker did not reach deterministic pause")
        time.sleep(.01)


RUN_APPLY = '''
import json, sys
from pathlib import Path
from project_guardian.local_ingestion.chatgpt_export_ingest import apply_chatgpt_export, ChatGPTExportIngestError
try:
    report = apply_chatgpt_export(preview_json=Path(sys.argv[1]), apply=True)
    print('RESULT=' + json.dumps(report.report), flush=True)
except ChatGPTExportIngestError as exc:
    print('REFUSED=' + str(exc), flush=True)
    sys.exit(9)
'''


@pytest.mark.parametrize("existing", [False, True])
def test_two_real_processes_collide_then_retry_without_duplicate_candidates(tmp_path, existing):
    dest, preview = fixture(tmp_path, existing=existing)
    ready = tmp_path / "ready"
    paused_code = '''
import sys
from pathlib import Path
from project_guardian.local_ingestion import chatgpt_export_ingest as ingest
original = ingest.read_known_candidate_ids
def paused(path):
    result = original(path)
    Path(sys.argv[2]).write_text('ready')
    assert sys.stdin.readline().strip() == 'continue'
    return result
ingest.read_known_candidate_ids = paused
''' + RUN_APPLY
    first = subprocess.Popen([sys.executable, "-c", paused_code, str(preview), str(ready)],
                             cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_ready(first, ready)
        before = bytes_at(dest)
        second = subprocess.run([sys.executable, "-c", RUN_APPLY, str(preview)],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        assert second.returncode == 9 and "REFUSED=" in second.stdout
        assert bytes_at(dest) == before
        out, err = first.communicate("continue\n", timeout=15)
        assert first.returncode == 0, (out, err)
        third = subprocess.run([sys.executable, "-c", RUN_APPLY, str(preview)],
                               cwd=ROOT, capture_output=True, text=True, timeout=15)
        assert third.returncode == 0, third.stderr
        result = json.loads(third.stdout.split("RESULT=")[1])
        assert result["staged_count"] == 0 and result["duplicate_count"] == 1
        assert_complete(dest)
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate()


@pytest.mark.parametrize("phase", ["stage", "raw", "origin", "record", "queue", "report", "manifest", "publish"])
@pytest.mark.parametrize("existing", [False, True])
def test_injected_failure_rolls_back_every_artifact_and_retry_recovers(tmp_path, monkeypatch, phase, existing):
    dest, preview = fixture(tmp_path, existing=existing)
    if existing and phase == "queue":
        export = tmp_path / "export.json"
        export.write_text(export.read_text().replace("500 dollars", "600 dollars"))
        preview = Path(preview_chatgpt_export(export_json=export, dest_dir=dest).json_path)
    before = bytes_at(dest)
    original_write = transaction._durable_write
    original_replace = transaction.os.replace
    original_stage = transaction.ApplyTransaction.write
    count = 0
    raw_writes = 0

    def partial_write(path, data):
        if (phase == "stage" and path.name == "stage-0") or (phase == "manifest" and path.name == "manifest.tmp"):
            path.write_bytes(data[:max(1, len(data)//2)])
            raise OSError("injected partial write")
        return original_write(path, data)

    def fail_target(self, path, data):
        nonlocal raw_writes
        if path.parent.name == "raw_sources":
            raw_writes += 1
        if ((phase == "raw" and path.parent.name == "raw_sources")
                or (phase == "origin" and path.parent.name == "raw_sources" and raw_writes == (1 if existing else 2))
                or (phase == "record" and path.parent.name == "records")
                or (phase == "queue" and path.name == "review_queue.jsonl")
                or (phase == "report" and path.name == "chatgpt_export_apply_report.json")):
            original_stage(self, path, data[:1])
            raise OSError("injected target failure")
        return original_stage(self, path, data)

    def fail_replace(source, target):
        nonlocal count
        if Path(source).name.startswith("stage-"):
            count += 1
            if phase == "publish" and count == 4:
                raise OSError("injected publication failure")
        return original_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(transaction, "_durable_write", partial_write)
        patch.setattr(transaction.ApplyTransaction, "write", fail_target)
        patch.setattr(transaction.os, "replace", fail_replace)
        with pytest.raises(OSError, match="injected"):
            apply_chatgpt_export(preview_json=preview, apply=True)
    assert bytes_at(dest) == before
    report = apply_chatgpt_export(preview_json=preview, apply=True).report
    assert report["model_called"] is report["embeddings_used"] is report["live_memory_written"] is False
    assert_complete(dest, count=2 if existing and phase == "queue" else 1)


@pytest.mark.parametrize("kill_phase", ["staging", "publish", "rollback", "commit_marker", "cleanup"])
@pytest.mark.parametrize("existing", [False, True])
def test_process_death_recovery_never_serves_partial_publication(tmp_path, kill_phase, existing):
    dest, preview = fixture(tmp_path, existing=existing)
    before = bytes_at(dest)
    ready = tmp_path / "ready"
    code = '''
import os, sys
from pathlib import Path
from project_guardian.local_ingestion import apply_transaction as tx
phase = sys.argv[3]
original_replace = os.replace
original_write = tx._durable_write
original_recovery = tx._replace_bytes
original_unlink = Path.unlink
count = 0
def pause():
    Path(sys.argv[2]).write_text('ready')
    sys.stdin.readline()
def write(path, data):
    if phase == 'staging' and path.name == 'stage-0':
        path.write_bytes(data[:1])
        pause()
    return original_write(path, data)
def replace(source, target):
    global count
    result = original_replace(source, target)
    if Path(source).name.startswith('stage-'):
        count += 1
        if phase == 'rollback' and count == 4:
            raise OSError('enter rollback')
        if phase == 'publish' and count == 4:
            pause()
    if phase == 'commit_marker' and Path(target).name == 'committed':
        pause()
    if phase == 'cleanup' and Path(target).name == tx.TRANSACTION_DIR + '_cleanup':
        pause()
    return result
def restore(path, data):
    result = original_recovery(path, data)
    if phase == 'rollback':
        pause()
    return result
def unlink(path, *args, **kwargs):
    result = original_unlink(path, *args, **kwargs)
    if phase == 'rollback':
        pause()
    return result
os.replace = replace
tx._durable_write = write
tx._replace_bytes = restore
Path.unlink = unlink
''' + RUN_APPLY
    process = subprocess.Popen([sys.executable, "-c", code, str(preview), str(ready), kill_phase],
                               cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_ready(process, ready)
        # No cooperating reader can return a view during publication.
        with pytest.raises(transaction.ApplyTransactionError, match="lock"):
            query_memory_intelligence(dest, "Roof")
        process.kill()
        process.communicate(timeout=15)
        # Read entry point, not an explicit test-only recovery call.
        records = load_memory_intelligence_records(dest)
        if kill_phase in ("staging", "publish", "rollback"):
            assert bytes_at(dest) == before
            assert len(records) == int(existing)
        else:
            assert_complete(dest)  # Entire commit survives post-commit death.
        apply_chatgpt_export(preview_json=preview, apply=True)
        assert_complete(dest)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_corrupt_recovery_journal_blocks_reader_and_writer(tmp_path):
    dest, preview = fixture(tmp_path)
    root = dest / transaction.TRANSACTION_DIR
    root.mkdir()
    (root / "manifest.json").write_text('{"version":1,"entries":[{"target":"../escape","existed":false}]}')
    before = bytes_at(dest)
    with pytest.raises(transaction.ApplyTransactionError, match="recovery"):
        query_memory_intelligence(dest, "Roof")
    with pytest.raises(ChatGPTExportIngestError, match="recovery"):
        apply_chatgpt_export(preview_json=preview, apply=True)
    assert bytes_at(dest) == before


def test_queue_reader_recovers_interrupted_empty_stage(tmp_path):
    dest, _ = fixture(tmp_path, existing=True)
    before = bytes_at(dest)
    (dest / transaction.TRANSACTION_DIR).mkdir()
    (dest / transaction.TRANSACTION_DIR / "stage-0").write_bytes(b"partial")
    assert len(read_known_candidate_ids(review_queue_path(dest))) == 1
    assert bytes_at(dest) == before


@pytest.mark.parametrize("content", ['{"candidate_id":', '{}', '[]', '{"candidate_id":"same"}\n{"candidate_id":"same"}'])
def test_invalid_existing_queue_refuses_apply_without_mutation(tmp_path, content):
    dest, preview = fixture(tmp_path)
    queue = review_queue_path(dest)
    queue.parent.mkdir()
    queue.write_text(content)
    before = bytes_at(dest)
    with pytest.raises(ChatGPTExportIngestError, match="queue"):
        apply_chatgpt_export(preview_json=preview, apply=True)
    assert bytes_at(dest) == before


def test_recovery_failure_keeps_journal_and_refuses_reads_until_repaired(tmp_path, monkeypatch):
    dest, preview = fixture(tmp_path, existing=True)
    before = bytes_at(dest)
    original_replace = transaction.os.replace
    original_recover = transaction._replace_bytes
    count = 0
    def fail_publication(source, target):
        nonlocal count
        if Path(source).name.startswith('stage-'):
            count += 1
            if count == 4:
                raise OSError('publication interrupted')
        return original_replace(source, target)
    def refuse_recovery(*args):
        raise OSError('recovery storage unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(transaction.os, 'replace', fail_publication)
        patch.setattr(transaction, '_replace_bytes', refuse_recovery)
        with pytest.raises(ChatGPTExportIngestError, match='recovery'):
            apply_chatgpt_export(preview_json=preview, apply=True)
        with pytest.raises(transaction.ApplyTransactionError, match='recovery'):
            query_memory_intelligence(dest, 'Roof')
        assert (dest / transaction.TRANSACTION_DIR / 'manifest.json').is_file()
    assert load_memory_intelligence_records(dest)
    assert bytes_at(dest) == before
    assert original_recover is transaction._replace_bytes
    apply_chatgpt_export(preview_json=preview, apply=True)
    assert_complete(dest)


def test_external_session_output_is_refused_before_publication(tmp_path):
    dest, preview = fixture(tmp_path)
    external = tmp_path / 'external-session'
    external.mkdir()
    outside = external / preview.name
    outside.write_bytes(preview.read_bytes())
    before = bytes_at(dest)
    with pytest.raises(ChatGPTExportIngestError, match='inside destination'):
        apply_chatgpt_export(preview_json=outside, apply=True)
    assert bytes_at(dest) == before
    assert list(external.iterdir()) == [outside]


def integrity_journal(dest, *, version=2, committed=False, existing=True):
    root = dest / transaction.TRANSACTION_DIR
    root.mkdir()
    entries = []
    for i, name in enumerate(("a", "b", "new")):
        path = dest / name
        existed = existing and name != "new"
        original = ("original-" + name).encode()
        path.write_bytes(("published-" + name).encode())
        entry = {"target": name, "existed": existed}
        if existed:
            (root / f"backup-{i}").write_bytes(original)
        if version == 2:
            entry.update(backup_size=len(original) if existed else None,
                         backup_sha256=hashlib.sha256(original).hexdigest() if existed else None)
        entries.append(entry)
    (root / "manifest.json").write_text(json.dumps({"version": version, "entries": entries}))
    if committed:
        (root / "committed").write_bytes(b"committed\n")
    return root


@pytest.mark.parametrize("damage", ["corrupt", "truncate", "swap", "missing", "directory"])
@pytest.mark.parametrize("committed", [False, True])
def test_bad_backup_blocks_all_mutations_and_keeps_evidence(tmp_path, damage, committed):
    dest, preview = fixture(tmp_path)
    root = integrity_journal(dest, committed=committed)
    backup = root / "backup-0"  # Last restored: catches partial rollback without preflight.
    if damage == "corrupt":
        backup.write_bytes(b"X" * len(backup.read_bytes()))
    elif damage == "truncate":
        backup.write_bytes(backup.read_bytes()[:-1])
    elif damage == "swap":
        other = root / "backup-1"
        first, second = backup.read_bytes(), other.read_bytes()
        backup.write_bytes(second)
        other.write_bytes(first)
    elif damage == "missing":
        backup.unlink()
    else:
        backup.unlink()
        backup.mkdir()
    before = bytes_at(dest)
    for reader in (lambda: read_known_candidate_ids(review_queue_path(dest)),
                   lambda: query_memory_intelligence(dest, "Roof")):
        with pytest.raises(transaction.ApplyTransactionError, match="recovery"):
            reader()
        assert bytes_at(dest) == before
    with pytest.raises(ChatGPTExportIngestError, match="recovery"):
        apply_chatgpt_export(preview_json=preview, apply=True)
    assert bytes_at(dest) == before
    assert root.is_dir()


@pytest.mark.parametrize("field,value", [
    ("backup_size", -1), ("backup_size", True), ("backup_size", "10"),
    ("backup_size", None), ("backup_sha256", None), ("backup_sha256", "g" * 64),
    ("backup_sha256", "a" * 63), ("backup_sha256", 12),
    ("backup_sha256", "A" * 64), ("existed", 1), ("target", "../escape"),
])
def test_malformed_integrity_metadata_preserves_destinations(tmp_path, field, value):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest)
    manifest = root / "manifest.json"
    state = json.loads(manifest.read_text())
    state["entries"][0][field] = value
    manifest.write_text(json.dumps(state))
    before = bytes_at(dest)
    with pytest.raises(transaction.ApplyTransactionError, match="recovery"):
        read_known_candidate_ids(review_queue_path(dest))
    assert bytes_at(dest) == before


@pytest.mark.parametrize("mutation", ["missing_field", "extra_field", "new_metadata", "version"])
def test_malformed_manifest_schema_blocks_recovery(tmp_path, mutation):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest)
    manifest = root / "manifest.json"
    state = json.loads(manifest.read_text())
    if mutation == "missing_field":
        del state["entries"][0]["backup_sha256"]
    elif mutation == "extra_field":
        state["entries"][0]["extra"] = True
    elif mutation == "new_metadata":
        state["entries"][2]["backup_size"] = 0
    else:
        state["version"] = True
    manifest.write_text(json.dumps(state))
    before = bytes_at(dest)
    with pytest.raises(transaction.ApplyTransactionError):
        with transaction.destination_lock(dest):
            pass
    assert bytes_at(dest) == before


def test_verified_multi_file_rollback_retries_after_interruption(tmp_path, monkeypatch):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest)
    evidence = bytes_at(root)
    restore = transaction._replace_bytes
    calls = []
    def interrupted(path, data):
        calls.append(path.name)
        if len(calls) == 2:
            raise OSError("interrupted recovery")
        restore(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(transaction, "_replace_bytes", interrupted)
        with pytest.raises(transaction.ApplyTransactionError):
            with transaction.destination_lock(dest):
                pass
    assert bytes_at(root) == evidence
    with transaction.destination_lock(dest):
        assert (dest / "a").read_bytes() == b"original-a"
        assert (dest / "b").read_bytes() == b"original-b"
        assert not (dest / "new").exists()
    assert not root.exists()


@pytest.mark.parametrize("committed,existing,allowed", [(False, True, False),
                                                       (True, True, True),
                                                       (False, False, True)])
def test_legacy_journal_only_recovers_when_no_backup_restore_needed(tmp_path, committed, existing, allowed):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest, version=1, committed=committed, existing=existing)
    before = bytes_at(dest)
    if not allowed:
        with pytest.raises(transaction.ApplyTransactionError):
            read_known_candidate_ids(review_queue_path(dest))
        assert bytes_at(dest) == before
    else:
        with transaction.destination_lock(dest):
            pass
        assert not root.exists()
        for name in ("a", "b", "new"):
            if committed:
                assert (dest / name).read_bytes() == ("published-" + name).encode()
            else:
                assert not (dest / name).exists()


def test_backup_write_corruption_refuses_before_publication(tmp_path, monkeypatch):
    dest, preview = fixture(tmp_path, existing=True)
    before = {k: v for k, v in bytes_at(dest).items()}
    write = transaction._durable_write
    def corrupt(path, data):
        write(path, b"X" * len(data) if path.name.startswith("backup-") else data)
    monkeypatch.setattr(transaction, "_durable_write", corrupt)
    with pytest.raises(ChatGPTExportIngestError, match="recovery"):
        apply_chatgpt_export(preview_json=preview, apply=True)
    public = {k: v for k, v in bytes_at(dest).items() if not k.startswith(transaction.TRANSACTION_DIR + "/")}
    assert public == before
    assert (dest / transaction.TRANSACTION_DIR / "manifest.json").exists()


def test_recovery_uses_verified_snapshot_without_reopening_backups(tmp_path, monkeypatch):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest)
    restore = transaction._replace_bytes
    def mutate_after_validation(path, data):
        (root / "backup-0").write_bytes(b"corrupted after verification")
        restore(path, data)
    monkeypatch.setattr(transaction, "_replace_bytes", mutate_after_validation)
    with transaction.destination_lock(dest):
        pass
    assert (dest / "a").read_bytes() == b"original-a"
    assert (dest / "b").read_bytes() == b"original-b"


def test_issue111_exact_legacy_reproduction_now_blocks_queue_reader(tmp_path):
    dest, _ = fixture(tmp_path)
    queue = review_queue_path(dest)
    queue.parent.mkdir()
    queue.write_bytes(b'{"candidate_id":"old"}\n')
    root = dest / transaction.TRANSACTION_DIR
    root.mkdir()
    (root / "backup-0").write_bytes(b"BROKEN\n")
    (root / "manifest.json").write_text(json.dumps({"version": 1, "entries": [
        {"target": "memory_candidates/review_queue.jsonl", "existed": True}]}))
    before = bytes_at(dest)
    with pytest.raises(transaction.ApplyTransactionError):
        read_known_candidate_ids(queue)
    assert bytes_at(dest) == before


def test_duplicate_manifest_keys_fail_closed(tmp_path):
    dest, _ = fixture(tmp_path)
    root = integrity_journal(dest)
    manifest = root / "manifest.json"
    manifest.write_text(manifest.read_text().replace('"version": 2', '"version": 1, "version": 2'))
    before = bytes_at(dest)
    with pytest.raises(transaction.ApplyTransactionError):
        read_known_candidate_ids(review_queue_path(dest))
    assert bytes_at(dest) == before


def test_empty_original_backup_is_verified_and_restored(tmp_path, monkeypatch):
    dest, _ = fixture(tmp_path)
    path = dest / "empty"
    path.write_bytes(b"")
    replace = transaction.os.replace
    def interrupt(source, target):
        result = replace(source, target)
        if Path(source).name.startswith("stage-"):
            raise OSError("interrupted publication")
        return result
    with transaction.destination_lock(dest, write=True):
        tx = transaction.ApplyTransaction(dest)
        tx.write(path, b"new")
        monkeypatch.setattr(transaction.os, "replace", interrupt)
        with pytest.raises(OSError, match="interrupted"):
            tx.commit()
    assert path.read_bytes() == b""
    assert not tx.root.exists()
