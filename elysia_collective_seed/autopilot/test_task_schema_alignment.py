import json
from pathlib import Path


SCHEMA = Path(__file__).with_name("task_packet_schema.json")


def test_task_schema_declares_dispatcher_capability_field():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert "required_capabilities" in schema["properties"]
    prop = schema["properties"]["required_capabilities"]
    assert prop["type"] == "array"
    assert prop["uniqueItems"] is True


def test_dispatcher_fields_are_schema_declared():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    declared = set(schema["properties"])
    dispatcher_fields = {
        "task_id",
        "status",
        "risk_class",
        "required_capabilities",
        "task_class",
        "allowed_workers",
        "dependencies",
        "human_approval_required",
        "attempt",
        "max_attempts",
        "preferred_worker",
        "acceptance_criteria",
        "source_refs",
        "title",
    }
    assert dispatcher_fields <= declared
