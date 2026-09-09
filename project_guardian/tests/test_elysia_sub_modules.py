"""Tests for Elysia integrated module boot wiring."""

import sys
from pathlib import Path
from types import ModuleType

from elysia_sub_modules import init_integrated_modules


class _FakeWebScout:
    def __init__(self, web_reader=None, proposals_root=None, require_api_keys=False):
        self.web_reader = web_reader
        self.proposals_root = Path(proposals_root) if proposals_root is not None else None
        self.require_api_keys = require_api_keys
        self.research_calls = []

    def conduct_web_research(self, query: str, max_sources: int = 5):
        self.research_calls.append({"query": query, "max_sources": max_sources})
        return [], f"summary:{max_sources}"

    def list_proposals(self, status_filter=None):
        return []

    def get_brave_search_usage(self):
        return {"requests_used": 0}

    def get_tavily_usage(self):
        return {"requests_used": 0}


def _install_fake_webscout_module(monkeypatch):
    fake_module = ModuleType("project_guardian.webscout_agent")
    fake_module.ElysiaWebScout = _FakeWebScout
    monkeypatch.setitem(sys.modules, "project_guardian.webscout_agent", fake_module)


def test_integrated_modules_webscout_is_opt_in(monkeypatch, tmp_path):
    _install_fake_webscout_module(monkeypatch)

    modules = init_integrated_modules(
        architect=None,
        guardian=None,
        runtime_loop=None,
        config={"webscout_proposals_root": str(tmp_path / "proposals")},
    )

    assert "webscout_agent" not in modules


def test_integrated_modules_webscout_caps_research_sources(monkeypatch, tmp_path):
    _install_fake_webscout_module(monkeypatch)

    modules = init_integrated_modules(
        architect=None,
        guardian=None,
        runtime_loop=None,
        config={
            "enable_webscout_agent": True,
            "webscout_proposals_root": str(tmp_path / "proposals"),
            "webscout_max_sources": 2,
            "webscout_hard_cap": 4,
        },
    )

    assert "webscout_agent" in modules
    webscout = modules["webscout_agent"]
    _sources, summary = webscout.conduct_web_research("mutation safety patterns", max_sources=10)

    assert summary == "summary:2"
    assert webscout.webscout.research_calls[-1]["max_sources"] == 2
    status = webscout.get_status()
    assert status["max_sources_per_query"] == 2
