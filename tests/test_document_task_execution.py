"""Document-search bound task execution, verification, and completion auth."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    StaleTaskEditError,
    resolve_conversation_root,
)
from project_guardian.local_documents_search import folder_fingerprint


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


@pytest.fixture()
def estimates(tmp_path: Path) -> Path:
    folder = tmp_path / "construction-estimates"
    folder.mkdir()
    (folder / "paint-estimate-duration.md").write_text(
        "# Painting estimate\n\n"
        "Brand: Duration exterior paint\n"
        "Material cost: USD 482.50\n",
        encoding="utf-8",
    )
    (folder / "notes.txt").write_text("Primer notes only.\n", encoding="utf-8")
    return folder


def _seed_docs_bound(store: ConversationStore, estimates: Path) -> tuple[str, str, int]:
    conv = store.create(
        objective="Prepare a painting estimate",
        constraints=["Stay fictional"],
    )
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=[
            "Find material costs from previous estimates",
            "Calculate labor requirements",
            "Draft estimate summary",
        ],
        next_safe_action="Find material costs from previous estimates",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    bound = store.bind_operator_step(
        cid,
        step_id=step_id,
        expected_revision=1,
        capability="local.documents.search",
        arguments={
            "query": "Duration exterior paint",
            "min_matches": 1,
            "required_substring": "482.50",
            "expected_relative_path": "paint-estimate-duration.md",
            "folder_label": estimates.name,
            "folder_fingerprint": folder_fingerprint(str(estimates)),
        },
    )
    return cid, step_id, int(bound["conversation"]["checkpoint_revision"])


def test_bind_rejects_stored_folder_path(store: ConversationStore):
    conv = store.create(objective="x")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Find costs"],
        next_safe_action="Find costs",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    with pytest.raises(ContinuityError, match="cannot be stored"):
        store.bind_operator_step(
            cid,
            step_id=step_id,
            expected_revision=1,
            capability="local.documents.search",
            arguments={"query": "Duration", "folder": "C:/somewhere"},
        )


def test_unauthorized_docs_execute_rejected(store: ConversationStore, estimates: Path):
    cid, step_id, rev = _seed_docs_bound(store, estimates)
    with pytest.raises(ContinuityError, match="document search not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=False,
            authorize_record_completion=True,
            documents_folder=str(estimates),
        )
    with pytest.raises(ContinuityError, match="recording completion not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=False,
            documents_folder=str(estimates),
        )
    assert store.get(cid)["task_steps"][0]["status"] == "pending"


def test_authorized_docs_execute_verifies_and_advances(
    store: ConversationStore, estimates: Path, tmp_path: Path
):
    cid, step_id, rev = _seed_docs_bound(store, estimates)
    result = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(estimates),
        execution_id="exec_" + "a" * 16,
    )
    assert result["saved"] and result["verified"] and result["advanced"]
    assert result["receipt"]["capability"] == "local.documents.search"
    assert result["receipt"]["match_count"] >= 1
    assert str(estimates) not in json.dumps(result["receipt"])
    assert "482.50" not in json.dumps(result["receipt"])
    assert result["conversation"]["next_safe_action"] == "Calculate labor requirements"
    step = next(s for s in result["conversation"]["task_steps"] if s["step_id"] == step_id)
    assert step["status"] == "completed"
    assert step["result_reference"]["top_relative_path"] == "paint-estimate-duration.md"

    again = ConversationStore(resolve_conversation_root(tmp_path))
    loaded = again.get(cid)
    assert loaded["next_safe_action"] == "Calculate labor requirements"
    assert loaded["task_steps"][0]["status"] == "completed"


def test_zero_match_does_not_complete(store: ConversationStore, estimates: Path):
    conv = store.create(objective="Prepare a painting estimate")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Find material costs from previous estimates", "Next"],
        next_safe_action="Find material costs from previous estimates",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    bound = store.bind_operator_step(
        cid,
        step_id=step_id,
        expected_revision=1,
        capability="local.documents.search",
        arguments={"query": "nonexistent-widget-xyz", "min_matches": 1},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="evidence criteria unmet"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(estimates),
        )
    assert store.get(cid)["task_steps"][0]["status"] == "pending"
    assert store.get(cid)["next_safe_action"] == "Find material costs from previous estimates"


def test_source_change_invalidates_verification(
    store: ConversationStore, estimates: Path, monkeypatch
):
    cid, step_id, rev = _seed_docs_bound(store, estimates)

    from project_guardian import local_documents_search as docs

    real_search = docs.search_local_documents

    def search_then_mutate(folder, query, **kwargs):
        result = real_search(folder, query, **kwargs)
        target = Path(folder) / "paint-estimate-duration.md"
        target.write_text("CHANGED CONTENTS NO COST\n", encoding="utf-8")
        return result

    monkeypatch.setattr(docs, "search_local_documents", search_then_mutate)
    with pytest.raises(ContinuityError, match="source changed|verification failed"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(estimates),
        )
    assert store.get(cid)["task_steps"][0]["status"] == "pending"


def test_docs_duplicate_and_stale(store: ConversationStore, estimates: Path):
    cid, step_id, rev = _seed_docs_bound(store, estimates)
    eid = "exec_" + "b" * 16
    a = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(estimates),
        execution_id=eid,
    )
    b = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(estimates),
        execution_id=eid,
    )
    assert a["checkpoint"]["revision"] == rev + 1
    assert b["idempotent"] is True
    with pytest.raises(StaleTaskEditError):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(estimates),
            execution_id="exec_" + "c" * 16,
        )


def test_docs_interrupted_persist(store: ConversationStore, estimates: Path, monkeypatch):
    cid, step_id, rev = _seed_docs_bound(store, estimates)
    good = store.get_checkpoint(cid)
    import project_guardian.conversation_continuity as mod

    real = mod._atomic_write_json

    def boom(path, payload):
        if str(path).endswith(".pending.json"):
            return real(path, payload)
        raise OSError("simulated interrupt")

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError, match="not durably recorded"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(estimates),
            execution_id="exec_" + "d" * 16,
        )
    loaded = json.loads(store._checkpoint_path(cid).read_text(encoding="utf-8"))
    assert loaded["content_sha256"] == good["content_sha256"]
    assert store.get(cid)["task_steps"][0]["status"] == "pending"
