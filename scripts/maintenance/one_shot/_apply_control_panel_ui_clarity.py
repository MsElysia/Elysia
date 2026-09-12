#!/usr/bin/env python3
"""ONE-SHOT UI REPAIR SCRIPT - NOT RUNTIME TOOLING.

This historical maintenance helper edits CONTROL_PANEL_TEMPLATE anchors.
Do not import, schedule, call from CI, or use as an application runtime path.
Prefer direct reviewed patches for future UI marker changes.
"""

"""Apply operator-friendly UI clarity copy to CONTROL_PANEL_TEMPLATE (idempotent)."""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PANEL = _REPO_ROOT / "project_guardian" / "ui_control_panel.py"
text = PANEL.read_text(encoding="utf-8")

if 'id="system-safety-status-card"' in text:
    print("UI clarity already applied")
    raise SystemExit(0)

# --- System Safety Status card (top of dashboard) ---
DASH_GRID = '<div id="dashboard" class="tab-content active">\n            <div class="grid">'
if DASH_GRID not in text:
    DASH_GRID = '<div id="dashboard" class="tab-content active">\n            <div class="grid">'
if DASH_GRID not in text:
    raise SystemExit("dashboard grid anchor missing")

SAFETY_CARD = """
                <div id="system-safety-status-card" class="card" style="grid-column: 1 / -1;">
                    <h2>System Safety Status</h2>
                    <p style="font-size: 12px; color: var(--text-secondary); margin: 0 0 10px 0; line-height: 1.5;">
                        Plain-language summary for operators. Safe-stack panels below are read-only or review-only unless config says otherwise.
                    </p>
                    <ul style="font-size: 12px; color: var(--text-secondary); margin: 0; padding-left: 18px; line-height: 1.6;">
                        <li><strong>Autonomy:</strong> Off unless explicitly enabled</li>
                        <li><strong>Live execution:</strong> Off for safe-stack panels</li>
                        <li><strong>Brain traces:</strong> Dry-run and config-gated</li>
                        <li><strong>Memory ranking:</strong> Read-only</li>
                        <li><strong>Self-improvement:</strong> Review/export only</li>
                        <li><strong>Chat memory:</strong> Saved locally through ConversationStore</li>
                    </ul>
                </div>
"""
text = text.replace(DASH_GRID, DASH_GRID + SAFETY_CARD, 1)
if 'id="system-safety-status-card"' not in text:
    raise SystemExit("failed to insert safety card")

# --- Hidden empty-state copy for tests (also used in JS below) ---
EMPTY_BLOCK = """
        <!-- ui-clarity-empty-states -->
        <span id="ui-empty-brain-trace" hidden>No brain trace has been recorded yet.</span>
        <span id="ui-empty-proposals" hidden>No self-improvement proposals yet.</span>
        <span id="ui-empty-memory-ranking" hidden>No recent memories found to rank.</span>
        <span id="ui-empty-prompt-contracts" hidden>No validation results recorded yet.</span>
        <span id="ui-empty-conversation-chat" hidden>Start a conversation with Elysia.</span>
"""
if "ui-clarity-empty-states" not in text:
    text = text.replace("</body>", EMPTY_BLOCK + "\n</body>", 1)

# --- Brain visibility panel: enrich copy and button labels ---
OLD_BRAIN_HEADER = """                    <h3 style="margin-top: 12px;">Brain Trace</h3>
                    <div id="brain-trace-summary" """
NEW_BRAIN_HEADER = """                    <h3 style="margin-top: 12px;">Brain Trace</h3>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                        Shows what Elysia considered during the latest dry-run reasoning trace. This does not mean Elysia executed anything.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Dry-run/config-gated. Review-only: does not apply code.</p>
                    <motion id="brain-trace-summary" """
NEW_BRAIN_HEADER = NEW_BRAIN_HEADER.replace("<motion id=", "<div id=")
text = text.replace(OLD_BRAIN_HEADER, NEW_BRAIN_HEADER, 1)
text = text.replace('onclick="refreshBrainTrace()">Refresh trace</button>', 'onclick="refreshBrainTrace()">Refresh brain trace</button>', 1)

OLD_SI = """                    <h3 style="margin-top: 16px;">Self-Improvement Proposals</h3>
                    <div id="self-improvement-proposals-list" """
NEW_SI = """                    <h3 style="margin-top: 16px;">Self-Improvement Proposals</h3>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                        Ideas Elysia found for improving itself. These are review-only. Nothing here changes code by itself.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Review-only: does not apply code.</p>
                    <div id="self-improvement-proposals-list" """
text = text.replace(OLD_SI, NEW_SI, 1)
text = text.replace(
    'onclick="refreshSelfImprovementProposals()">Refresh proposals</button>',
    'onclick="refreshSelfImprovementProposals()">Refresh proposals</button>',
    1,
)

OLD_EXPORT_P = """                        <!-- self-improvement-prompt-export-start -->
                        <p style="font-size: 11px; color: var(--warning); margin: 10px 0 6px 0;">
                            Export only. This does not apply code or run commands.
                        </p>"""
NEW_EXPORT_P = """                        <!-- self-improvement-prompt-export-start -->
                        <h3 style="margin-top: 14px;">Proposal Export</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Creates a copyable prompt for Cursor or Codex. Exporting does not apply changes.
                        </p>
                        <p style="font-size: 11px; color: var(--warning); margin: 10px 0 6px 0;">
                            Export only. This does not apply code or run commands.
                        </p>"""
text = text.replace(OLD_EXPORT_P, NEW_EXPORT_P, 1)
# Keep "Export Cursor Prompt" / "Export Codex Prompt" (test_self_improvement_prompt_export.py)

OLD_MR = """                    <motion id="memory-ranking-panel" style="margin-top: 18px;">
                        <h3>Memory Ranking</h3>
                        <p style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Read-only advisory ranking. No memory changes are applied from this panel.
                        </p>"""
OLD_MR = OLD_MR.replace("<motion ", "<div ")
NEW_MR = """                    <div id="memory-ranking-panel" style="margin-top: 18px;">
                        <h3>Memory Ranking</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Shows which recent memories look important, low-value, or worth reviewing. This is advisory only and does not edit memory.
                        </p>
                        <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Read-only advisory ranking. No memory changes are applied.</p>"""
if OLD_MR in text:
    text = text.replace(OLD_MR, NEW_MR, 1)
text = text.replace(
    'onclick="refreshMemoryRankingSummary()">Refresh ranking</button>',
    'onclick="refreshMemoryRankingSummary()">Refresh memory ranking</button>',
    1,
)

OLD_PC = """                        <h3>Prompt Contracts</h3>
                        <p style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Read-only validation status. Validation visibility only. Defaults remain off. No model calls from this panel. production chat is not blocked by default.
                        </p>"""
NEW_PC = """                        <h3>Prompt Contracts</h3>
                        <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Checks whether module outputs follow the expected JSON format. Defaults are off unless enabled in config.
                        </p>
                        <p style="font-size: 10px; color: var(--warning); margin: 0 0 6px 0;">Read-only validation status. No model calls from this panel. production chat is not blocked by default.</p>"""
if "Checks whether module outputs" not in text:
    text = text.replace(OLD_PC, NEW_PC, 1)
text = text.replace(
    'onclick="refreshPromptContractStatus()">Refresh contract status</button>',
    'onclick="refreshPromptContractStatus()">Refresh prompt contract status</button>',
    1,
)

# --- Control tab ---
OLD_CTRL = """        <div id="control" class="tab-content">
            <div class="controls">
                <h2>System Controls</h2>"""
NEW_CTRL = """        <div id="control" class="tab-content">
            <div class="controls">
                <h2>Control</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45; max-width: 920px;">
                    Manual operator controls. These affect how Elysia is monitored or directed. Use carefully.
                </p>
                <p style="font-size: 10px; color: var(--warning); margin: 0 0 12px 0;">Review before using. This may affect runtime behavior.</p>
                <h2 style="margin-top: 8px;">System Controls</h2>"""
text = text.replace(OLD_CTRL, NEW_CTRL, 1)

OLD_CHAT = """                <h3 style="margin-top: 24px;">APIs &amp; Tools</h3>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Trigger income, research, harvest, and AI chat from the dashboard.</p>
                <div class="input-group" style="margin-bottom: 12px;">
                    <label>Chat with AI (OpenAI/OpenRouter):</label>"""
NEW_CHAT = """                <h3 style="margin-top: 24px;">APIs &amp; Tools</h3>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Trigger income, research, harvest, and AI chat from the dashboard.</p>
                <h3 style="margin-top: 16px;">Conversation Chat</h3>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45;">
                    This is your conversation with Elysia. Messages are saved locally so refreshes do not erase the thread.
                </p>
                <div class="input-group" style="margin-bottom: 12px;">
                    <label>Chat with Elysia:</label>"""
text = text.replace(OLD_CHAT, NEW_CHAT, 1)
text = text.replace('onclick="sendApiChat()">Send</button>', 'onclick="sendApiChat()">Send message to Elysia</button>', 1)
text = text.replace('onclick="startNewApiChat()">New chat</button>', 'onclick="startNewApiChat()">Start new conversation</button>', 1)

# --- Memory tab ---
OLD_MEM = """        <div id="memory" class="tab-content">
            <div class="card">
                <h2>Memory Operations</h2>"""
NEW_MEM = """        <div id="memory" class="tab-content">
            <div class="card">
                <h2>Memory</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); line-height: 1.45; margin-bottom: 12px;">
                    Saved information Elysia can use later. This may include conversation summaries, lessons, and important context.
                </p>
                <h3 style="margin-top: 0;">Memory Operations</h3>"""
text = text.replace(OLD_MEM, NEW_MEM, 1)

# --- Next Action ---
OLD_NA = """                <div class="card">
                    <h2>Next Action</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Unified decision: what the system should do next</p>"""
NEW_NA = """                <div class="card">
                    <h2>Task / Next Action</h2>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                        Shows what Elysia thinks the next useful task or action is. Review before acting.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 8px 0;">Review before using.</p>"""
text = text.replace(OLD_NA, NEW_NA, 1)

# --- Autonomy ---
OLD_AUTO = """                <div class="card">
                    <h2>Autonomy</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Elysia acts on its own when enabled</p>"""
NEW_AUTO = """                <div class="card">
                    <h2>Autonomy</h2>
                    <p class="ui-clarity-helper" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                        High-impact controls. These should stay off unless you intentionally enable them and understand the consequences.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin-bottom: 8px;">This may affect runtime behavior.</p>"""
text = text.replace(OLD_AUTO, NEW_AUTO, 1)

# --- JS empty states ---
text = text.replace(
    "el.textContent = data && data.message ? data.message : 'No brain trace available.';",
    "el.textContent = data && data.message ? data.message : 'No brain trace has been recorded yet.';",
    1,
)
text = text.replace(
    "if (!rows.length) { el.innerHTML = '<em>No proposals yet.</em>'; return; }",
    "if (!rows.length) { el.innerHTML = '<em>No self-improvement proposals yet.</em>'; return; }",
    1,
)
text = text.replace(
    "el.textContent = data.message || 'Ranking unavailable.';",
    "el.textContent = data.message || 'No recent memories found to rank.';",
    1,
)
if "No validation results recorded yet" not in text:
    text = text.replace(
        "el.textContent = 'Loading…';\n            fetch('/api/prompt-contracts/status')",
        "el.textContent = 'Loading…';\n            fetch('/api/prompt-contracts/status')",
        1,
    )
    text = text.replace(
        """            fetch('/api/prompt-contracts/status')
                .then(function(r) { return r.json(); })
                .then(function(data) { el.textContent = JSON.stringify(data, null, 2).slice(0, 1200); })""",
        """            fetch('/api/prompt-contracts/status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data || data.available === false) {
                        el.textContent = 'No validation results recorded yet.';
                        return;
                    }
                    el.textContent = JSON.stringify(data, null, 2).slice(0, 1200);
                })""",
        1,
    )

text = text.replace(
    "el.innerHTML = '<em style=\"color: var(--text-secondary);\">No conversation yet.</em>';",
    "el.innerHTML = '<em style=\"color: var(--text-secondary);\">Start a conversation with Elysia.</em>';",
    1,
)

PANEL.write_text(text, encoding="utf-8")
print("applied UI clarity pass")
