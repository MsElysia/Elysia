# project_guardian/tests/test_chatgpt_export_ingest.py

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.chatgpt_export_ingest import (
    APPLY_REPORT_JSON,
    PREVIEW_JSON,
    PREVIEW_MD,
    ChatGPTExportIngestError,
    apply_chatgpt_export,
    preview_chatgpt_export,
)
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME, review_queue_path


def _sample_export() -> list[dict]:
    return [
        {
            "title": "Drywall quote chat",
            "id": "conv-1",
            "create_time": 1700000000,
            "update_time": 1700000100,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Need a drywall quote for the kitchen."]},
                        "create_time": 1700000001,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Sure, what are the dimensions?"]},
                        "create_time": 1700000002,
                    },
                },
            },
        },
        {
            "title": "Empty chat",
            "id": "conv-empty",
            "mapping": {},
        },
    ]


def _write_export(path: Path) -> None:
    path.write_text(json.dumps(_sample_export()), encoding="utf-8")


def test_preview_requires_explicit_paths(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    report = preview_chatgpt_export(export_json=export, dest_dir=dest)
    assert report.preview["export_path"]


def test_preview_writes_json_and_markdown(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    report = preview_chatgpt_export(export_json=export, dest_dir=dest)

    assert Path(report.json_path).name == PREVIEW_JSON
    assert Path(report.markdown_path).name == PREVIEW_MD
    assert Path(report.json_path).is_file()
    assert Path(report.markdown_path).is_file()


def test_preview_counts_conversations_and_messages(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    report = preview_chatgpt_export(export_json=export, dest_dir=dest)

    assert report.preview["conversation_count"] == 2
    assert report.preview["message_count_estimate"] >= 2
    assert report.preview["candidate_count_estimate"] == 1
    assert report.preview["skipped_count"] == 1


def test_preview_writes_no_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    preview_chatgpt_export(export_json=export, dest_dir=dest)

    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert not queue.exists()


def test_apply_dry_run_writes_no_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=False)

    assert report.report["dry_run"] is True
    assert not (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).exists()


def test_apply_with_apply_stages_pending_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    assert report.report["staged_count"] == 1
    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert queue.is_file()
    record = json.loads(queue.read_text(encoding="utf-8").strip())
    assert record["review_status"] == "pending"


def test_apply_writes_extracted_text_and_metadata(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    session = Path(preview.session_dir)
    assert list((session / "extracted_text").glob("*.txt"))
    assert list((session / "metadata").glob("*.json"))


def test_candidate_source_type_chatgpt_export(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    record = json.loads(
        (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).read_text(encoding="utf-8").strip()
    )
    assert record["source_type"] == "chatgpt_export"
    assert record["suggested_memory_type"] == "conversation_history"


def test_candidate_live_memory_written_false(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    record = json.loads(
        (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).read_text(encoding="utf-8").strip()
    )
    assert record["live_memory_written"] is False


def test_repeat_apply_does_not_duplicate_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    first = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    second = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    assert first.report["staged_count"] == 1
    assert second.report["duplicate_count"] == 1
    lines = [
        ln
        for ln in (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert len(lines) == 1


def test_malformed_json_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ChatGPTExportIngestError, match="Malformed"):
        preview_chatgpt_export(export_json=bad, dest_dir=dest)


def test_missing_export_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    missing = tmp_path / "missing.json"
    with pytest.raises(ChatGPTExportIngestError, match="not found"):
        preview_chatgpt_export(export_json=missing, dest_dir=dest)


def test_export_size_changed_after_preview_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    export.write_text(json.dumps(_sample_export() + [{"title": "extra", "id": "x", "mapping": {}}]), encoding="utf-8")

    with pytest.raises(ChatGPTExportIngestError, match="size changed"):
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)


def test_no_network_model_vector_calls(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    with patch("project_guardian.memory_vector.VectorMemory") as vector:
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    vector.assert_not_called()
    bundle = json.loads(Path(preview.json_path).read_text(encoding="utf-8"))
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_apply_report_written(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=False)

    assert Path(report.json_path).name == APPLY_REPORT_JSON
    assert Path(report.markdown_path).is_file()


def test_preview_rejects_export_symlink_before_resolve_monkeypatch(tmp_path, monkeypatch):
    """Windows may lack admin symlink creation; stub is_symlink to assert pre-resolve guard."""
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    resolve_called: list[str] = []
    original_resolve = Path.resolve

    def tracking_resolve(self, *args, **kwargs):
        resolve_called.append(str(self))
        return original_resolve(self, *args, **kwargs)

    def fake_is_symlink(self):
        if self == export:
            return True
        return original_is_symlink(self)

    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", tracking_resolve)

    with pytest.raises(ChatGPTExportIngestError, match="Symlinks are not followed"):
        preview_chatgpt_export(export_json=export, dest_dir=dest)

    assert resolve_called == []


def test_apply_rejects_preview_symlink_before_resolve_monkeypatch(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    preview_path = Path(preview.json_path)
    resolve_called: list[str] = []
    original_resolve = Path.resolve
    original_is_symlink = Path.is_symlink

    def tracking_resolve(self, *args, **kwargs):
        resolve_called.append(str(self))
        return original_resolve(self, *args, **kwargs)

    def fake_is_symlink(self):
        if self == preview_path:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", tracking_resolve)

    with pytest.raises(ChatGPTExportIngestError, match="Symlinks are not followed"):
        apply_chatgpt_export(preview_json=preview_path, apply=False)

    assert resolve_called == []


def test_apply_rejects_stored_export_symlink_before_read_monkeypatch(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    preview_path = Path(preview.json_path)
    preview_data = json.loads(preview_path.read_text(encoding="utf-8"))
    stored_export = Path(preview_data["export_path"])
    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def tracking_resolve(self, *args, **kwargs):
        if self == stored_export:
            raise AssertionError("resolve must not run on symlink export path")
        return original_resolve(self, *args, **kwargs)

    def fake_is_symlink(self):
        if self == stored_export:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", tracking_resolve)

    with pytest.raises(ChatGPTExportIngestError, match="Symlinks are not followed"):
        apply_chatgpt_export(preview_json=preview_path, apply=False)


def _serialization_fixture(tmp_path):
    export = tmp_path / 'export.json'
    export.write_text(json.dumps(_sample_export()), encoding='utf-8')
    dest = tmp_path / 'dest'
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    return dest, Path(preview.json_path)


def _destination_bytes(dest):
    return {str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob('*') if p.is_file()}


def _paused_apply_process(preview, ready):
    """Pause a real second interpreter after reading candidate IDs inside apply."""
    import subprocess
    import sys
    import time

    code = '''
import json, sys
from pathlib import Path
from project_guardian.local_ingestion import chatgpt_export_ingest as ingest
original = ingest.read_known_candidate_ids
def paused(path):
    known = original(path)
    Path(sys.argv[2]).write_text('ready')
    if sys.stdin.readline().strip() != 'continue':
        raise RuntimeError('interrupted before staging')
    return known
ingest.read_known_candidate_ids = paused
result = ingest.apply_chatgpt_export(preview_json=Path(sys.argv[1]), apply=True)
print('RESULT=' + json.dumps(result.report))
'''
    process = subprocess.Popen(
        [sys.executable, '-c', code, str(preview), str(ready)],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 10
    while not ready.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f'paused apply exited early: {stdout}\n{stderr}')
        if time.monotonic() >= deadline:
            process.kill()
            process.communicate()
            pytest.fail('paused apply did not reach protected candidate read')
        time.sleep(0.01)
    return process


@pytest.mark.skipif(__import__('os').name not in ('posix', 'nt'), reason='supported OS locking required')
def test_two_process_overlap_refuses_without_writes_then_rechecks_candidate_ids(tmp_path):
    dest, preview = _serialization_fixture(tmp_path)
    process = _paused_apply_process(preview, tmp_path / 'ready')
    try:
        before = _destination_bytes(dest)
        with pytest.raises(ChatGPTExportIngestError, match='lock refused'):
            apply_chatgpt_export(preview_json=preview, apply=True)
        assert _destination_bytes(dest) == before
        stdout, stderr = process.communicate('continue\n', timeout=10)
        assert process.returncode == 0, (stdout, stderr)
        first = json.loads(next(line[7:] for line in stdout.splitlines() if line.startswith('RESULT=')))
        assert first['staged_count'] == 1
        intelligence_before = _destination_bytes(dest / 'memory_intelligence')
        retry = apply_chatgpt_export(preview_json=preview, apply=True)
        assert retry.report['staged_count'] == 0
        assert retry.report['duplicate_count'] == 1
        assert retry.report['memory_intelligence_unchanged'] == 1
        assert _destination_bytes(dest / 'memory_intelligence') == intelligence_before
        rows = [json.loads(line) for line in review_queue_path(dest).read_text().splitlines()]
        assert len(rows) == len({row['candidate_id'] for row in rows}) == 1
        assert retry.report['model_called'] is False
        assert retry.report['embeddings_used'] is False
        assert retry.report['live_memory_written'] is False
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.skipif(__import__('os').name not in ('posix', 'nt'), reason='supported OS locking required')
def test_killed_apply_process_releases_destination_lock(tmp_path):
    dest, preview = _serialization_fixture(tmp_path)
    before = _destination_bytes(dest)
    process = _paused_apply_process(preview, tmp_path / 'ready')
    process.kill()
    process.communicate(timeout=10)
    # An interrupted stage is private and recovered before destination reads.
    from project_guardian.local_ingestion.memory_intelligence import load_memory_intelligence_records
    assert load_memory_intelligence_records(dest) == []
    assert _destination_bytes(dest) == before
    assert apply_chatgpt_export(preview_json=preview, apply=True).report['staged_count'] == 1
    assert len(review_queue_path(dest).read_text().splitlines()) == 1


@pytest.mark.skipif(__import__('os').name not in ('posix', 'nt'), reason='supported OS locking required')
def test_apply_exception_releases_lock_for_recovery(tmp_path):
    from project_guardian.local_ingestion import chatgpt_export_ingest as ingest
    dest, preview = _serialization_fixture(tmp_path)
    with patch.object(ingest, 'stage_memory_candidate', side_effect=OSError('injected staging failure')):
        with pytest.raises(OSError, match='injected staging failure'):
            apply_chatgpt_export(preview_json=preview, apply=True)
    retry = apply_chatgpt_export(preview_json=preview, apply=True)
    assert retry.report['staged_count'] == 1
    assert len(review_queue_path(dest).read_text().splitlines()) == 1


@pytest.mark.skipif(__import__('os').name != 'posix', reason='POSIX backend failure injection')
@pytest.mark.parametrize('failure', ['open', 'flock', 'platform'])
def test_lock_failure_is_closed_and_destination_bytes_unchanged(tmp_path, failure):
    import builtins
    from project_guardian.local_ingestion import chatgpt_export_ingest as ingest
    dest, preview = _serialization_fixture(tmp_path)
    before = _destination_bytes(dest)
    if failure == 'open':
        context = patch.object(ingest.os, 'open', side_effect=PermissionError('refused'))
    elif failure == 'flock':
        fcntl = pytest.importorskip('fcntl')
        context = patch.object(fcntl, 'flock', side_effect=OSError('unsupported filesystem'))
    else:
        original = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == 'fcntl':
                raise ImportError('unsupported platform')
            return original(name, *args, **kwargs)
        context = patch.object(builtins, '__import__', side_effect=unavailable)
    with context:
        with pytest.raises(ChatGPTExportIngestError, match='lock'):
            apply_chatgpt_export(preview_json=preview, apply=True)
    assert _destination_bytes(dest) == before
    assert not (dest / 'memory_intelligence').exists()
    assert not review_queue_path(dest).exists()


@pytest.mark.skipif(__import__('os').name not in ('posix', 'nt'), reason='supported OS locking required')
def test_destination_lock_scope_and_default_dry_run(tmp_path):
    from project_guardian.local_ingestion.chatgpt_export_ingest import _destination_apply_lock
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    dest, preview = _serialization_fixture(first)
    other, other_preview = _serialization_fixture(second)
    with _destination_apply_lock(dest):
        dry = apply_chatgpt_export(preview_json=preview)
        assert dry.report['dry_run'] is True
        assert not (dest / 'memory_intelligence').exists()
        assert not review_queue_path(dest).exists()
        assert apply_chatgpt_export(preview_json=other_preview, apply=True).report['staged_count'] == 1
    assert apply_chatgpt_export(preview_json=preview, apply=True).report['staged_count'] == 1


@pytest.mark.parametrize('flag', [None, 0, 1, '', 'true', [], {}, object()])
def test_malformed_apply_flag_rejected_before_preview_access(tmp_path, monkeypatch, flag):
    from project_guardian.local_ingestion import chatgpt_export_ingest as ingest

    def forbidden(*args, **kwargs):
        raise AssertionError('malformed flag must be rejected before file access')

    monkeypatch.setattr(ingest, '_safe_resolve', forbidden)
    with pytest.raises(ChatGPTExportIngestError, match='apply must be a boolean'):
        apply_chatgpt_export(preview_json=tmp_path / 'missing.json', apply=flag)


@pytest.mark.skipif(__import__('os').name not in ('posix', 'nt'), reason='supported OS locking required')
def test_stateful_apply_flag_cannot_bypass_held_destination_lock(tmp_path):
    from project_guardian.local_ingestion.chatgpt_export_ingest import _destination_apply_lock

    class StatefulFlag:
        calls = 0

        def __bool__(self):
            self.calls += 1
            return self.calls > 1

    dest, preview = _serialization_fixture(tmp_path)
    before = _destination_bytes(dest)
    flag = StatefulFlag()
    with _destination_apply_lock(dest):
        with pytest.raises(ChatGPTExportIngestError, match='apply must be a boolean'):
            apply_chatgpt_export(preview_json=preview, apply=flag)
        assert flag.calls == 0
        assert _destination_bytes(dest) == before
        with pytest.raises(ChatGPTExportIngestError, match='lock refused'):
            apply_chatgpt_export(preview_json=preview, apply=True)
    assert apply_chatgpt_export(preview_json=preview, apply=True).report['staged_count'] == 1
