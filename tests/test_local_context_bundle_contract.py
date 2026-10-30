"""Fail closed on corrupt worker context, before local inference or calculator use.

Synthetic data only; no local or remote network and no personal memory.
"""
import copy
import hashlib
import json

import pytest

from elysia_local_memory_chat import (
    ChatBoundaryError, LocalOllama, ManualAuthorization,
    canonical, converse_bundle, validate_context_bundle,
)

QUESTION = "Calculate fictional labor cost."
RATE = "Fictional labor rate is USD 35 per hour."


def sign(payload):
    unsigned = copy.deepcopy(payload)
    unsigned.pop("bundle_sha256", None)
    unsigned["bundle_sha256"] = hashlib.sha256(canonical(unsigned).encode()).hexdigest()
    return unsigned


def empty():
    return sign({
        "schema": "elysia.local-context.v1", "query": QUESTION,
        "evidence_trust": "untrusted_data", "selection": "current_revision_only",
        "evidence": [], "no_memory_support": True,
    })


def with_rate():
    value = empty()
    value["evidence"] = [{
        "source_id": "fictional-source", "chunk_id": "fictional-chunk",
        "revision": 2, "source_sha256": hashlib.sha256(RATE.encode()).hexdigest(),
        "highlights": [{"highlight_id": "fictional-highlight", "text": RATE}],
    }]
    value["no_memory_support"] = False
    return sign(value)


def auth(*scopes):
    return ManualAuthorization("bounded-synthetic-request", True, True,
                               frozenset(("local.chat", "memory.read", *scopes)))


def test_signed_empty_context_and_rate_context_accept():
    assert validate_context_bundle(empty(), QUESTION)["no_memory_support"] is True
    assert validate_context_bundle(with_rate(), QUESTION)["evidence"][0]["revision"] == 2


def test_valid_empty_context_does_not_claim_memory_support(monkeypatch):
    model = LocalOllama("synthetic:local")
    monkeypatch.setattr(model, "generate", lambda *a, **k: '{"answer":"Not established by memory."}')
    result = converse_bundle(empty(), QUESTION, auth(), model)
    assert result["answer"] == "Not established by memory."
    assert result["memory_written"] is False and result["tools_executed"] == []


@pytest.mark.parametrize("change", [
    lambda b: b.update(query="another request"),
    lambda b: b.update(schema="untrusted.schema"),
    lambda b: b.update(no_memory_support=False),
    lambda b: b.update(evidence_trust="instructions"),
    lambda b: b.update(selection="all_revisions"),
    lambda b: b.update(evidence="forged"),
    lambda b: b.update(unrecognized="unexpected"),
    lambda b: b.pop("bundle_sha256"),
    lambda b: b.update(bundle_sha256="0" * 64),
    lambda b: b.update(bundle_sha256=123),
])
def test_invalid_envelope_never_reaches_model(change, monkeypatch):
    data = empty()
    change(data)
    model = LocalOllama("synthetic:local")
    monkeypatch.setattr(model, "generate", lambda *a, **k: pytest.fail("model called for invalid context"))
    with pytest.raises(ChatBoundaryError):
        converse_bundle(data, QUESTION, auth("calculator.execute"), model)


@pytest.mark.parametrize("change", [
    lambda b: b["evidence"][0].update(revision=True),
    lambda b: b["evidence"][0].update(revision=0),
    lambda b: b["evidence"][0].update(source_sha256="not-a-hash"),
    lambda b: b["evidence"][0].update(chunk_id=None),
    lambda b: b["evidence"][0].update(highlights=[{"text": RATE}]),
    lambda b: b["evidence"][0].update(highlights=[{"highlight_id": "a", "text": "x" * 3001}]),
    lambda b: b["evidence"].append(copy.deepcopy(b["evidence"][0])),
    lambda b: b["evidence"].extend(copy.deepcopy(b["evidence"][0]) for _ in range(5)),
])
def test_rehashed_malformed_evidence_rejected_before_inference(change, monkeypatch):
    data = with_rate()
    change(data)
    data = sign(data)
    model = LocalOllama("synthetic:local")
    monkeypatch.setattr(model, "generate", lambda *a, **k: pytest.fail("model invoked with malformed evidence"))
    with pytest.raises(ChatBoundaryError):
        converse_bundle(data, QUESTION, auth("calculator.execute"), model)


def test_payload_tamper_detected_even_when_schema_looks_valid():
    value = with_rate()
    value["evidence"][0]["highlights"][0]["text"] = "Fictional labor rate is USD 99 per hour."
    with pytest.raises(ChatBoundaryError, match="digest mismatch"):
        validate_context_bundle(value, QUESTION)
