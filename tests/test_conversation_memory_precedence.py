"""Conversation checkpoints must not override newer durable memory corrections."""
from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.conversation_continuity import ConversationStore, resolve_conversation_root
from project_guardian.local_memory_chat import ManualAuthorization, build_context_from_adapter
from project_guardian.restricted_runtime_adapter import (
    OPERATOR_FACT_PERMISSIONS,
    LocalPrincipal,
    RestrictedRuntimeAdapter,
)


def test_corrected_memory_outranks_stale_checkpoint_text(tmp_path: Path):
    memory_path = tmp_path / "guardian_memory.json"
    memory_path.write_text("[]", encoding="utf-8")
    adapter = RestrictedRuntimeAdapter(
        principals=[
            LocalPrincipal("dashboard-operator", "token-secret", OPERATOR_FACT_PERMISSIONS)
        ],
        memory_filepath=str(memory_path),
    )
    headers = {
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": "token-secret",
    }
    create = adapter.handle(
        "POST",
        "/api/restricted/v1/facts",
        headers=headers,
        body={"statement": "Fictional harbor city of Veridia is Lumenport."},
    )
    assert create.status in (200, 201)
    fact_id = create.body["fact"]["fact_id"]
    correct = adapter.handle(
        "POST",
        f"/api/restricted/v1/facts/{fact_id}/corrections",
        headers=headers,
        body={"statement": "Fictional harbor city of Veridia is Glasshaven."},
    )
    assert correct.status in (200, 201)
    revision = correct.body["fact"]["revision"]

    store = ConversationStore(resolve_conversation_root(tmp_path))
    conv = store.create(objective="Discuss Veridia harbor")
    cid = conv["conversation_id"]
    store.update_task_fields(
        cid,
        {
            "confirmed_facts": ["Harbor city is Lumenport"],  # stale checkpoint claim
            "memory_refs": [{"fact_id": fact_id, "revision": 1}],
            "outstanding_steps": ["Confirm harbor name"],
            "next_safe_action": "Confirm harbor name",
        },
    )
    store.write_checkpoint(cid, reason="operator")
    assembled = store.assemble_model_context(cid, "What is the harbor city?")
    assert assembled["checkpoint"]["confirmed_facts"][0] == "Harbor city is Lumenport"

    bundle = build_context_from_adapter(adapter, "harbor city Veridia", headers)
    statements = []
    for row in bundle.get("evidence") or []:
        for h in row.get("highlights") or []:
            statements.append(h.get("text") or "")
    joined = " ".join(statements)
    assert "Glasshaven" in joined
    assert "Lumenport" not in joined
    # Host must treat memory evidence as authoritative over checkpoint text.
    assert assembled["continuity_note"]
    assert "overrides" in assembled["continuity_note"].casefold()
    assert any(
        isinstance(ref, dict) and ref.get("fact_id") == fact_id
        for ref in (assembled["checkpoint"].get("memory_refs") or [])
    )
    # Authorization still empty on checkpoint
    assert assembled["checkpoint"]["authorization_state"] == "none"
    _ = ManualAuthorization("r", True, True, frozenset({"local.chat", "memory.read"}))
    assert revision >= 2
