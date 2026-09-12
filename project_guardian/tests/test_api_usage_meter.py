# project_guardian/tests/test_api_usage_meter.py

from project_guardian.api_usage_meter import (
    format_gas_meter_text,
    record_router_choice,
    record_transport,
    reset_session,
    snapshot,
)


def test_meter_transport_and_router_roundtrip():
    reset_session()
    record_transport("openai_chat", True, usage={"prompt_tokens": 100, "completion_tokens": 50})
    record_transport("openai_chat", False, detail="timeout")
    record_router_choice("local_mistral", task_type="reasoning")
    s = snapshot()
    assert s["transport_totals"]["calls_ok"] >= 1
    assert s["transport_totals"]["calls_fail"] >= 1
    assert "openai_chat" in s["transport"]
    txt = format_gas_meter_text(s)
    assert "openai_chat" in txt
    assert "router:" in txt or "local_mistral" in txt
