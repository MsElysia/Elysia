# tests/test_orchestration_validator.py
from project_guardian.orchestration.tools.candidates import CapabilityCandidate, build_capability_candidates
from project_guardian.orchestration.tools.schemas import ActionIntent
from project_guardian.orchestration.tools.validator import validate_action_intent


def test_build_candidates_caps_at_max():
    caps = ["module:a", "tool:b", "module:c", "module:d", "module:e", "module:f"]
    c = build_capability_candidates(allowed_capabilities=caps, archetype="t", max_candidates=3)
    assert len(c) == 3


def test_validator_rejects_unknown_target():
    candidates = [
        CapabilityCandidate(
            target_kind="module",
            target_name="tool_registry",
            label="tr",
            allowed_payload_keys=["task"],
            priority=1.0,
            reason="t",
        )
    ]
    intent = ActionIntent(
        action_type="bounded_capability",
        target_kind="module",
        target_name="evil",
        payload={},
        confidence=0.99,
        rationale="x",
    )
    v = validate_action_intent(intent, candidates, min_confidence=0.2)
    assert v.valid is False
    assert v.fallback_mode == "legacy_capability_loop"
    assert v.reason == "target_not_in_candidate_set"


def test_validator_filters_payload_keys():
    candidates = [
        CapabilityCandidate(
            target_kind="module",
            target_name="tool_registry",
            label="tr",
            allowed_payload_keys=["task", "query"],
            priority=1.0,
            reason="t",
        )
    ]
    intent = ActionIntent(
        action_type="bounded_capability",
        target_kind="module",
        target_name="tool_registry",
        payload={"task": "x", "evil": 1},
        confidence=0.9,
        rationale="ok",
    )
    v = validate_action_intent(intent, candidates, min_confidence=0.2)
    assert v.valid is True
    assert v.normalized_intent is not None
    assert "evil" not in v.normalized_intent.payload
