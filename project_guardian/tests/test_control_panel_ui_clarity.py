# project_guardian/tests/test_control_panel_ui_clarity.py
"""Operator-friendly control panel copy (plain language, safe-stack panels)."""

from __future__ import annotations

import re

import pytest


def _html() -> str:
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    return CONTROL_PANEL_TEMPLATE


def test_system_safety_status_card_exists():
    html = _html()
    assert 'id="system-safety-status-card"' in html
    assert "System Safety Status" in html
    assert "Autonomy:" in html and "Off unless explicitly enabled" in html
    assert "Live execution:" in html and "Off for safe-stack panels" in html
    assert "ConversationStore" in html


def test_helper_text_conversation_chat():
    html = _html()
    assert "Conversation Chat" in html
    assert "This is your conversation with Elysia." in html
    assert "refreshes do not erase the thread" in html


def test_helper_text_control():
    html = _html()
    assert "Manual operator controls." in html
    assert "Use carefully." in html


def test_helper_text_task_next_action():
    html = _html()
    assert "Task / Next Action" in html
    assert "Shows what Elysia thinks the next useful task or action is." in html


def test_helper_text_memory():
    html = _html()
    assert "Saved information Elysia can use later." in html


def test_helper_text_brain_trace():
    html = _html()
    assert "Shows what Elysia considered during the latest dry-run reasoning trace." in html
    assert "This does not mean Elysia executed anything." in html


def test_helper_text_self_improvement_proposals():
    html = _html()
    assert "Ideas Elysia found for improving itself." in html
    assert "Nothing here changes code by itself." in html


def test_helper_text_proposal_export():
    html = _html()
    assert "Proposal Export" in html
    assert "Creates a copyable prompt for Cursor or Codex." in html


def test_helper_text_memory_ranking():
    html = _html()
    assert "advisory only and does not edit memory" in html


def test_helper_text_prompt_contracts():
    html = _html()
    assert "Checks whether module outputs follow the expected JSON format." in html


def test_empty_state_messages_exist():
    html = _html()
    assert "No brain trace has been recorded yet." in html
    assert "No self-improvement proposals yet." in html
    assert "No recent memories found to rank." in html
    assert "No validation results recorded yet." in html
    assert "Start a conversation with Elysia." in html


def test_clear_button_labels_exist():
    html = _html()
    assert "Refresh brain trace" in html
    assert "Refresh memory ranking" in html
    assert "Refresh prompt contract status" in html
    assert "Start new conversation" in html
    assert "Send message to Elysia" in html
    assert "Export Cursor prompt" in html or "Export Cursor Prompt" in html
    assert "Export Codex prompt" in html or "Export Codex Prompt" in html


def test_conversation_memory_markers_remain():
    html = _html()
    assert "elysia_control_panel_conversation_id" in html
    assert "getApiChatConversationId" in html
    assert "localStorage" in html
    assert "/api/conversations" in html
    assert "/api/chat/history" in html
    assert "refreshApiChatHistory" in html
    assert "renderApiChatHistory" in html


def test_safe_stack_panel_markers_remain():
    html = _html()
    assert "brain-visibility-panel" in html
    assert "Brain Trace" in html
    assert "Self-Improvement Proposals" in html
    assert "memory-ranking-panel" in html
    assert "prompt-contract-panel" in html
    assert "refreshBrainTrace" in html
    assert "refreshSelfImprovementProposals" in html
    assert "refreshMemoryRankingSummary" in html
    assert "refreshPromptContractStatus" in html
    assert "exportSelfImprovementProposalPrompt" in html
    assert "updateSelfImprovementProposalStatus" in html
    assert "/api/brain/trace/latest" in html
    assert "/api/self-improvement/proposals" in html
    assert "/api/memory/ranking/summary" in html
    assert "/api/prompt-contracts/status" in html


def test_secondary_tab_helper_text():
    html = _html()
    assert "Learning pulls information from external sources" in html
    assert "Lists work waiting for Elysia or Guardian" in html
    assert "Read-only overview for operators" in html
    assert "Recent security-related events and alerts" in html
    assert "Read-only analysis of memory health" in html
    assert "Observability only: RAG paths" in html


def test_no_unsafe_controls_in_safe_stack_panels():
    html = _html()
    start = html.find('id="brain-visibility-panel"')
    assert start >= 0
    end = html.find("<!-- Learning Tab -->", start)
    assert end > start
    block = html[start:end].lower()
    for forbidden in (
        "apply_patch",
        "run_command",
        "execute proposal",
        "trigger autonomy",
        "compress memory",
        "delete memory",
        "enable live execution",
    ):
        assert forbidden not in block
    onclick_bad = re.findall(
        r"onclick=[\"'][^\"']*(?:apply_patch|run_command|subprocess)[^\"']*[\"']",
        html[start:end],
        re.I,
    )
    assert not onclick_bad
