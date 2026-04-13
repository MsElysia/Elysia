# Capability wiring for bounded browser (no Playwright in most tests).

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from project_guardian.bounded_browser.capability import (
    build_compact_browser_result,
    run_bounded_browser_for_capability,
)
from project_guardian.bounded_browser.schema import BrowseTaskResult, PageStepResult
from project_guardian.capability_execution import execute_capability_kind


def test_unsafe_start_url_refused() -> None:
    out = run_bounded_browser_for_capability(
        None,
        {"goal": "explore docs", "start_url": "javascript:alert(1)"},
    )
    assert out["success"] is False
    assert out["error"] == "unsafe_url_scheme"


def test_unsafe_scheme_in_goal_refused() -> None:
    out = run_bounded_browser_for_capability(
        None,
        {"goal": "open javascript:evil"},
    )
    assert out["success"] is False
    assert "unsafe" in out["error"]


def test_max_pages_clamped_in_browse_call() -> None:
    captured: dict = {}

    def _fake_browse(goal, start_url=None, max_pages=3, max_scrolls_per_page=2, max_depth=1, **_kwargs):
        captured.update(
            {
                "goal": goal,
                "start_url": start_url,
                "max_pages": max_pages,
                "max_scrolls_per_page": max_scrolls_per_page,
                "max_depth": max_depth,
            }
        )
        return BrowseTaskResult(
            goal=goal,
            start_url=start_url or "https://a.test/",
            stop_reason="ok",
        )

    with patch("project_guardian.bounded_browser.agent.browse_task", side_effect=_fake_browse):
        out = run_bounded_browser_for_capability(
            None,
            {
                "goal": "https://a.test/",
                "max_pages": 99,
                "max_scrolls_per_page": 99,
                "max_depth": 99,
            },
        )
    assert out["success"] is True
    assert captured["max_pages"] == 8
    assert captured["max_scrolls_per_page"] == 6
    assert captured["max_depth"] == 3


def test_compact_result_shape() -> None:
    r = BrowseTaskResult(goal="g", start_url="https://x.test/", stop_reason="done")
    r.visited_urls = ["https://x.test/"]
    r.steps.append(
        PageStepResult(
            url="https://x.test/",
            title="T",
            page_type="misc",
            key_findings="alpha beta",
            discovered_links=[{"href": "https://x.test/next", "text": "n"}],
            relevance_score=0.5,
            continue_recommendation="stop",
            scroll_index=2,
        )
    )
    c = build_compact_browser_result(r, scrolls_used=2)
    assert set(c.keys()) >= {
        "summary",
        "visited_urls",
        "top_findings",
        "next_links_considered",
        "stop_reason",
        "pages_visited",
        "scrolls_used",
    }
    assert c["pages_visited"] == 1
    assert c["scrolls_used"] == 2
    assert c["visited_urls"] == ["https://x.test/"]


def test_execute_capability_module_bounded_browser() -> None:
    g = MagicMock()
    with patch(
        "project_guardian.bounded_browser.capability.run_bounded_browser_for_capability",
        return_value={"success": True, "result": {"summary": "x"}},
    ) as m:
        out = execute_capability_kind(g, "module", "bounded_browser", {"goal": "explore site"})
    m.assert_called_once()
    assert out["success"] is True


def test_builtin_operator_elysia_bounded_browser() -> None:
    from project_guardian.capability_execution import _builtin_operator_tool_result

    g = MagicMock()
    with patch(
        "project_guardian.bounded_browser.capability.run_bounded_browser_for_capability",
        return_value={"success": True, "result": {"summary": "y"}},
    ) as m:
        out = _builtin_operator_tool_result(g, "elysia_bounded_browser", {"goal": "g"})
    m.assert_called_once()
    assert out["success"] is True


def test_builtin_operator_elysia_moltbook_browser() -> None:
    from project_guardian.capability_execution import _builtin_operator_tool_result

    g = MagicMock()
    with patch(
        "project_guardian.bounded_browser.moltbook.run_moltbook_browser_for_capability",
        return_value={"success": True, "result": {"summary": "m"}},
    ) as m:
        out = _builtin_operator_tool_result(g, "elysia_moltbook_browser", {"goal": "read feed"})
    m.assert_called_once()
    assert out["success"] is True


def test_allowed_hosts_in_payload_passed_to_browse() -> None:
    captured: dict = {}

    def _fake_browse(goal, start_url=None, **kwargs):
        captured["allowed_hosts"] = kwargs.get("allowed_hosts")
        return BrowseTaskResult(goal=goal, start_url=start_url or "https://a/", stop_reason="ok")

    with patch("project_guardian.bounded_browser.agent.browse_task", side_effect=_fake_browse):
        out = run_bounded_browser_for_capability(
            None,
            {"goal": "https://example.com/", "allowed_hosts": ["example.com", "www.example.com"]},
        )
    assert out["success"] is True
    assert captured.get("allowed_hosts") == frozenset({"example.com"})


def test_allow_any_domain_skips_allowlist() -> None:
    captured: dict = {}

    def _fake_browse(goal, start_url=None, **kwargs):
        captured["allowed_hosts"] = kwargs.get("allowed_hosts")
        return BrowseTaskResult(goal=goal, start_url=start_url or "https://a/", stop_reason="ok")

    with patch("project_guardian.bounded_browser.agent.browse_task", side_effect=_fake_browse):
        run_bounded_browser_for_capability(
            None,
            {
                "goal": "https://example.com/",
                "allowed_hosts": ["example.com"],
                "allow_any_domain": True,
            },
        )
    assert captured.get("allowed_hosts") is None
