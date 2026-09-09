# project_guardian/tests/test_parse_action_intent.py
from __future__ import annotations

from project_guardian.orchestration.tools.schemas import parse_action_intent


def test_parse_action_intent_plain_object() -> None:
    raw = (
        '{"action_type":"invoke","target_kind":"module","target_name":"foo",'
        '"confidence":0.9,"rationale":"because"}'
    )
    ai = parse_action_intent(raw)
    assert ai is not None
    assert ai.action_type == "invoke"
    assert ai.target_kind == "module"
    assert ai.target_name == "foo"
    assert ai.confidence == 0.9


def test_parse_action_intent_with_preamble() -> None:
    raw = (
        "Here is the intent:\n"
        '{"action_type":"model_only","target_kind":"none","confidence":0.4,"rationale":"unsafe"}'
        "\nHope this helps."
    )
    ai = parse_action_intent(raw)
    assert ai is not None
    assert ai.target_kind == "none"
    assert ai.action_type == "model_only"


def test_parse_action_intent_json_array_single_object() -> None:
    raw = (
        '[{"action_type":"invoke","target_kind":"tool","target_name":"bar",'
        '"confidence":0.8,"rationale":"ok"}]'
    )
    ai = parse_action_intent(raw)
    assert ai is not None
    assert ai.target_kind == "tool"
    assert ai.target_name == "bar"


def test_parse_action_intent_fenced_block() -> None:
    raw = """```json
{"action_type":"x","target_kind":"none","confidence":0.5,"rationale":"r"}
```"""
    ai = parse_action_intent(raw)
    assert ai is not None
    assert ai.action_type == "x"


def test_parse_action_intent_invalid_returns_none() -> None:
    assert parse_action_intent("") is None
    assert parse_action_intent("not json") is None
    assert parse_action_intent("{broken") is None
