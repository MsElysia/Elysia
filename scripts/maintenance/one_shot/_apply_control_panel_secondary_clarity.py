#!/usr/bin/env python3
"""ONE-SHOT UI REPAIR SCRIPT - NOT RUNTIME TOOLING.

This historical maintenance helper edits CONTROL_PANEL_TEMPLATE anchors.
Do not import, schedule, call from CI, or use as an application runtime path.
Prefer direct reviewed patches for future UI marker changes.
"""

"""Add plain-language helpers to non-dashboard control panel tabs (idempotent)."""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PANEL = _REPO_ROOT / "project_guardian" / "ui_control_panel.py"
text = PANEL.read_text(encoding="utf-8")
marker = "ui-clarity-secondary-tabs"
if marker in text:
    print("secondary tab clarity already applied")
    raise SystemExit(0)

replacements: list[tuple[str, str]] = [
    (
        """                    <h2>📚 Learning Capabilities</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 20px;">
                        Monitor and control Elysia's learning systems. Test learning from various sources including Reddit, web articles, and RSS feeds.
                    </p>""",
        """                    <h2>📚 Learning</h2>
                    <p class="ui-clarity-helper" style="color: var(--text-secondary); margin-bottom: 12px; line-height: 1.45;">
                        Learning pulls information from external sources (Reddit, web pages, RSS). Test buttons preview a small sample; starting learning may use the network.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 16px 0;">Review before using. This may fetch external content.</p>""",
    ),
    (
        """                <h2>Task Queue</h2>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    Guardian <strong>TaskEngine</strong> items, Elysia loop <strong>GlobalTaskQueue</strong> jobs, and optional <strong>TASKS/*.md</strong> drop files.
                </p>""",
        """                <h2>Task Queue</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.45;">
                    Lists work waiting for Elysia or Guardian. Refresh to see status; items here may run when autonomy or the event loop is active.
                </p>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    Guardian <strong>TaskEngine</strong> items, Elysia loop <strong>GlobalTaskQueue</strong> jobs, and optional <strong>TASKS/*.md</strong> drop files.
                </p>
                <p style="font-size: 10px; color: var(--warning); margin: 0 0 10px 0;">Review before acting on queued tasks.</p>""",
    ),
    (
        """                    <h2>Operator Workbench</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 20px;">
                        See what Elysia has actually produced: opportunities, active self-tasks, learning digests, and recent artifacts.
                    </p>""",
        """                    <h2>Operator Workbench</h2>
                    <p class="ui-clarity-helper" style="color: var(--text-secondary); margin-bottom: 12px; line-height: 1.45;">
                        See what Elysia has actually produced: opportunities, active self-tasks, learning digests, and recent artifacts. Read-only overview for operators.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 16px 0;">Review-only: does not start new autonomous work from this tab.</p>""",
    ),
    (
        """                <h2>Security Events</h2>
                <div id="security-events"></div>""",
        """                <h2>Security Events</h2>
                <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.45;">
                    Recent security-related events and alerts. Read-only log for investigation; does not change security policy.
                </p>
                <div id="security-events"></motion>""".replace(
            '<div id="security-events"></motion>', '<div id="security-events"></div>'
        ),
    ),
    (
        """                    <h2>Introspection & Self-Analysis</h2>
                    <button onclick="refreshIntrospection()">Refresh All</button>""",
        """                    <h2>Introspection & Self-Analysis</h2>
                    <p class="ui-clarity-helper" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.45;">
                        Read-only analysis of memory health, focus, and behavior patterns. Buttons refresh reports; they do not rewrite memory.
                    </p>
                    <p style="font-size: 10px; color: var(--warning); margin: 0 0 10px 0;">Read-only: no memory changes are applied from this tab.</p>
                    <button onclick="refreshIntrospection()">Refresh All</button>""",
    ),
    (
        """                <h2>📡 What Elysia is doing</h2>
                <p style="color: var(--text-secondary); font-size: 13px; max-width: 900px;">
                    Self-build RAG paths, optional LLM JSONL traces (<code>ELYSIA_LLM_TRACE_JSONL</code>),
                    recent <code>selfbuild_rag</code> log lines, and MCP readiness — same data as scripts, in one place.
                </p>""",
        """                <h2>📡 What Elysia is doing</h2>
                <p class="ui-clarity-helper" style="color: var(--text-secondary); font-size: 13px; max-width: 900px; line-height: 1.45;">
                    Observability only: RAG paths, optional LLM trace files, recent log lines, and MCP readiness. Refresh buttons reload data; they do not run new jobs.
                </p>
                <p style="color: var(--text-secondary); font-size: 12px; max-width: 900px; margin-top: 8px;">
                    Self-build RAG paths, optional LLM JSONL traces (<code>ELYSIA_LLM_TRACE_JSONL</code>),
                    recent <code>selfbuild_rag</code> log lines, and MCP readiness — same data as scripts, in one place.
                </p>""",
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"patch anchor missing:\n{old[:120]}...")
    text = text.replace(old, new, 1)

text = text.replace("</body>", f"        <!-- {marker} -->\n</body>", 1)
PANEL.write_text(text, encoding="utf-8")
print("applied secondary tab clarity")
