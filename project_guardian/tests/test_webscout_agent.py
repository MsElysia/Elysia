"""Tests for structured LLM-only WebScout research fallback."""

from types import SimpleNamespace

import pytest

from project_guardian.webscout_agent import ElysiaWebScout, _parse_research_json_payload_flex


def _fake_llm_client(content: str):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )
            )
        )
    )


class _FakeAPIManager:
    def __init__(self, content: str):
        self._client = _fake_llm_client(content)

    def get_llm_client(self):
        return self._client


def test_llm_only_research_parses_fenced_json_response(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    scout = ElysiaWebScout(proposals_root=tmp_path / "proposals")
    scout.api_manager = _FakeAPIManager(
        """```json
        {
          "summary": "Structured research summary.",
          "sources": [
            {
              "url": "https://example.com/a",
              "title": "Example Source",
              "relevance": "high",
              "extracted_patterns": ["Uses structured output"],
              "summary": "A useful source."
            }
          ]
        }
        ```"""
    )

    sources, summary = scout._llm_only_research("structured parsing", max_sources=3)

    assert summary == "Structured research summary."
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/a"
    assert sources[0].extracted_patterns == ["Uses structured output"]


def test_parse_research_json_payload_flex_trailing_commas():
    blob = """{
      "summary": "OK",
      "sources": [{"url": "https://example.com/", "title": "T", "relevance": "low",},],
    }"""
    data = _parse_research_json_payload_flex(blob, blob)
    assert data["summary"] == "OK"
    assert len(data["sources"]) == 1


def test_llm_only_research_accepts_trailing_comma_json(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    scout = ElysiaWebScout(proposals_root=tmp_path / "proposals")
    scout.api_manager = _FakeAPIManager(
        """```json
        {
          "summary": "Tolerant parse.",
          "sources": [
            {
              "url": "https://example.com/b",
              "title": "B",
              "relevance": "medium",
            },
          ],
        }
        ```"""
    )

    sources, summary = scout._llm_only_research("tolerant json", max_sources=3)

    assert summary == "Tolerant parse."
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/b"


def test_llm_only_research_rejects_unstructured_response(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")
    scout = ElysiaWebScout(proposals_root=tmp_path / "proposals")
    scout.api_manager = _FakeAPIManager("This is just prose with no JSON payload.")

    with pytest.raises(ValueError, match="structured JSON object"):
        scout._llm_only_research("structured parsing", max_sources=2)
