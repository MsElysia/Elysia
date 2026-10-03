from __future__ import annotations

from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import (
    InMemoryBrainStore,
    MemoryIntelligenceBrainBridge,
)
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event
from project_guardian.local_ingestion.memory_intelligence import persist_source_intelligence


def _seed(root):
    persist_source_intelligence(
        dest_dir=root,
        raw_bytes=(
            b"Roof inspection notes. The north slope needs new flashing before winter. "
            b"Photographs and measurements are attached to the original report."
        ),
        source_identity="brain-bridge-source",
        canonical_tags=("roofing",),
        tag_hints=("roofing",),
    )


def test_brain_pipeline_consumes_source_linked_recall(tmp_path):
    _seed(tmp_path)
    memory = MemoryIntelligenceBrainBridge(InMemoryBrainStore(), tmp_path)
    pipe = BrainPipeline(memory=memory)

    trace, _ = pipe.run(
        Observation("user", "What did the roofing inspection say?"),
        context={"dry_run": True, "persist_trace": False},
    )

    evidence = trace.run_context["memory_intelligence_recall"]
    assert evidence
    assert any("source_relation" == reason["type"] for reason in evidence[0]["recall_reasons"])
    assert evidence[0]["source_id"]
    assert evidence[0]["chunk_id"]
    assert any("source_id=" in snippet and "roof" in snippet.casefold() for snippet in trace.memory_snippets)


def test_tda_trace_names_the_source_linked_context(tmp_path):
    _seed(tmp_path)
    memory = MemoryIntelligenceBrainBridge(InMemoryBrainStore(), tmp_path)
    trace, _ = BrainPipeline(memory=memory).run(
        Observation("user", "What did the roofing inspection say?"),
        context={"use_think_decide_act": True, "dry_run": True, "persist_trace": False},
    )

    ids = trace.think_decide_act_trace["observation"]["relevant_context_ids"]
    assert ids
    assert all(item.startswith("memory-intelligence:") for item in ids)


def test_operator_runtime_is_non_test_bridge_caller(tmp_path):
    _seed(tmp_path)
    result = run_brain_pipeline_for_operator_event(
        "What did the roofing inspection say?",
        context={"memory_intelligence_dir": tmp_path, "dry_run": True},
        config=BrainPipelineConfig(
            enabled=True,
            dry_run=True,
            persist_trace=False,
            entrypoints={"operator_chat": True},
        ),
    )

    trace, _ = result
    assert trace.run_context["memory_intelligence_recall"]
    assert any("source_id=" in item for item in trace.memory_snippets)


def test_bridge_expands_recalled_highlight_to_exact_raw_source_after_reopen(tmp_path):
    _seed(tmp_path)
    first = MemoryIntelligenceBrainBridge(InMemoryBrainStore(), tmp_path)
    first.retrieve("roofing")
    hit = first.recall_evidence()[0]
    highlight_id = hit["highlights"][0]["highlight_id"]

    reopened = MemoryIntelligenceBrainBridge(InMemoryBrainStore(), tmp_path)
    repeated = reopened.retrieve("roofing")
    expanded = reopened.expand_highlight(highlight_id)

    assert repeated == first.retrieve("roofing")
    assert expanded["source_id"] == hit["source_id"]
    assert expanded["chunk_id"] == hit["chunk_id"]
    assert expanded["highlight"] in expanded["surrounding_context"]
    assert expanded["surrounding_context"] in expanded["raw_source"]


def test_bridge_does_not_write_to_source_linked_store(tmp_path):
    _seed(tmp_path)
    records = list((tmp_path / "memory_intelligence" / "records").glob("*.json"))
    before = {path: path.read_bytes() for path in records}
    primary = InMemoryBrainStore()
    bridge = MemoryIntelligenceBrainBridge(primary, tmp_path)

    bridge.retrieve("roofing")
    bridge.remember("ordinary disposable lesson", category="brain_lesson")

    assert primary.entries
    assert {path: path.read_bytes() for path in records} == before
