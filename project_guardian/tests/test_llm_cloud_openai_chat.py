"""Unit tests for llm.cloud_openai_chat wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

from project_guardian.llm.cloud_openai_chat import openai_chat_completion


def test_openai_chat_completion_strips_and_returns_empty_err():
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = "  hello  \n"
    text, err = openai_chat_completion(
        client,
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=100,
        temperature=0.2,
    )
    assert err == ""
    assert text == "hello"
    client.chat.completions.create.assert_called_once()


def test_openai_chat_completion_returns_error_string_on_failure():
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("network")
    text, err = openai_chat_completion(
        client,
        model="m",
        messages=[],
        max_tokens=1,
    )
    assert text == ""
    assert "network" in err
