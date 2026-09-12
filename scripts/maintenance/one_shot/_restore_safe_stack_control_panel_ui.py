#!/usr/bin/env python3
"""ONE-SHOT UI REPAIR SCRIPT - NOT RUNTIME TOOLING.

This historical maintenance helper edits CONTROL_PANEL_TEMPLATE anchors.
Do not import, schedule, call from CI, or use as an application runtime path.
Prefer direct reviewed patches for future UI marker changes.
"""

"""Restore safe-stack dashboard UI markers in CONTROL_PANEL_TEMPLATE (idempotent)."""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PANEL = _REPO_ROOT / "project_guardian" / "ui_control_panel.py"
text = PANEL.read_text(encoding="utf-8")

if "refreshBrainTrace" in text and 'id="brain-visibility-panel"' in text:
    print("safe-stack UI markers already present")
    raise SystemExit(0)

ANCHOR = (
    "                </div>\n"
    "            </div>\n"
    "        </motion>\n\n"
    "        <!-- Learning Tab -->\n"
    "        <div id=\"learning\" class=\"tab-content\">"
)
if ANCHOR not in text:
    ANCHOR = (
        "                </div>\n"
        "            </div>\n"
        "        </div>\n\n"
        "        <!-- Learning Tab -->\n"
        "        <div id=\"learning\" class=\"tab-content\">"
    )
if ANCHOR not in text:
    raise SystemExit("HTML anchor not found")

HTML_BLOCK = """
                <div id="brain-visibility-panel" class="card" style="grid-column: 1 / -1;">
                    <!-- brain-visibility-review-only-start -->
                    <h2>Brain Trace &amp; Self-Improvement</h2>
                    <p style="font-size: 11px; color: var(--warning); margin: 0 0 8px 0; line-height: 1.45;">
                        Review-only summary. This does not apply code. Dry-run trace only unless explicitly enabled elsewhere.
                    </p>
                    <!-- brain-visibility-review-only-end -->
                    <h3 style="margin-top: 12px;">Brain Trace</h3>
                    <div id="brain-trace-summary" style="font-size: 12px; color: var(--text-secondary); min-height: 48px;">Loading…</div>
                    <button type="button" style="margin-top: 8px;" onclick="refreshBrainTrace()">Refresh trace</button>

                    <h3 style="margin-top: 16px;">Self-Improvement Proposals</h3>
                    <div id="self-improvement-proposals-list" style="font-size: 12px; min-height: 40px;">Loading…</div>
                    <button type="button" style="margin-top: 8px;" onclick="refreshSelfImprovementProposals()">Refresh proposals</button>
                    <div id="self-improvement-proposal-detail" style="margin-top: 12px; display: none;">
                        <div id="self-improvement-proposal-detail-body"></div>
                        <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
                            <button type="button" onclick="updateSelfImprovementProposalStatus('reviewing')">Reviewing</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('accepted')">Accepted</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('rejected')">Rejected</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('deferred')">Deferred</button>
                            <button type="button" onclick="updateSelfImprovementProposalStatus('implemented')">Implemented</button>
                        </div>
                        <!-- self-improvement-prompt-export-start -->
                        <p style="font-size: 11px; color: var(--warning); margin: 10px 0 6px 0;">
                            Export only. This does not apply code or run commands.
                        </p>
                        <div id="self-improvement-proposal-prompt-export" class="self-improvement-prompt-export">
                            <button type="button" onclick="exportSelfImprovementProposalPrompt('cursor')">Export Cursor Prompt</button>
                            <button type="button" onclick="exportSelfImprovementProposalPrompt('codex')">Export Codex Prompt</button>
                            <button type="button" onclick="copySelfImprovementExportedPrompt()">Copy exported prompt</button>
                            <pre id="self-improvement-prompt-export-text" style="margin-top: 8px; max-height: 160px; overflow: auto; font-size: 11px;"></pre>
                        </div>
                        <!-- self-improvement-prompt-export-end -->
                    </div>

                    <div id="memory-ranking-panel" style="margin-top: 18px;">
                        <h3>Memory Ranking</h3>
                        <p style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Read-only advisory ranking. No memory changes are applied from this panel.
                        </p>
                        <div id="memory-ranking-summary" style="font-size: 12px; min-height: 40px;">Loading…</div>
                        <button type="button" style="margin-top: 8px;" onclick="refreshMemoryRankingSummary()">Refresh ranking</button>
                    </div>

                    <div id="prompt-contract-panel" style="margin-top: 18px;">
                        <!-- prompt-contract-visibility-start -->
                        <h3>Prompt Contracts</h3>
                        <p style="font-size: 11px; color: var(--text-secondary); line-height: 1.45;">
                            Validation visibility only. Defaults remain off; this panel does not enable live execution.
                        </p>
                        <div id="prompt-contract-status" style="font-size: 12px; min-height: 40px;">Loading…</div>
                        <button type="button" style="margin-top: 8px;" onclick="refreshPromptContractStatus()">Refresh contract status</button>
                        <!-- prompt-contract-visibility-end -->
                    </div>
                </div>
"""
HTML_BLOCK = (
    HTML_BLOCK.replace("</motion>", "</div>")
    .replace('<motion id="self-improvement-proposal-prompt-export"', '<div id="self-improvement-proposal-prompt-export"')
)

text = text.replace(ANCHOR, HTML_BLOCK + ANCHOR, 1)

JS_ANCHOR = "        window.refreshApiChatHistory = function() {"
if JS_ANCHOR not in text:
    raise SystemExit("JS anchor not found")

JS_BLOCK = """
        window._selectedSelfImprovementProposalId = '';

        window.refreshBrainTrace = function() {
            var el = document.getElementById('brain-trace-summary');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/brain/trace/latest')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data || data.trace_exists === false) {
                        el.textContent = data && data.message ? data.message : 'No brain trace available.';
                        return;
                    }
                    var t = data.trace || data;
                    el.textContent = [
                        'ID: ' + (t.brain_pipeline_id || data.brain_pipeline_id || '—'),
                        'Risk: ' + (t.risk_level || data.risk_level || '—'),
                        'Dry run: ' + String(t.dry_run != null ? t.dry_run : data.brain_dry_run),
                        'Transitions: ' + (t.transition_count || data.brain_transition_count || 0)
                    ].join('\\n');
                })
                .catch(function(err) { el.textContent = 'Could not load trace: ' + err; });
        };
        window.refreshBrainTraceVisibility = window.refreshBrainTrace;

        window.renderSelfImprovementProposals = function(rows) {
            var el = document.getElementById('self-improvement-proposals-list');
            if (!el) return;
            rows = Array.isArray(rows) ? rows : [];
            if (!rows.length) { el.innerHTML = '<em>No proposals yet.</em>'; return; }
            el.innerHTML = rows.map(function(p) {
                var pid = String(p.proposal_id || '').replace(/'/g, '');
                return '<div style="padding:6px 0;border-bottom:1px solid var(--border);">' +
                    '<button type="button" style="font-size:11px;" onclick="window._selectSelfImprovementProposal(\\'' + pid + '\\')">' +
                    window._escapeHtml(p.title || p.proposal_id || 'proposal') + '</button>' +
                    ' <span style="color:var(--text-secondary);font-size:10px;">' + window._escapeHtml(p.status || '') + '</span></div>';
            }).join('');
        };

        window._selectSelfImprovementProposal = function(pid) {
            window._selectedSelfImprovementProposalId = pid || '';
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var panel = document.getElementById('self-improvement-proposal-detail');
                    var body = document.getElementById('self-improvement-proposal-detail-body');
                    if (!panel || !body) return;
                    var p = data.proposal || {};
                    body.textContent = (p.title || '') + '\\n' + (p.problem_summary || '');
                    panel.style.display = 'block';
                })
                .catch(function(err) { if (window.addLog) addLog('Proposal detail error: ' + err, 'warning'); });
        };

        window.refreshSelfImprovementProposals = function() {
            fetch('/api/self-improvement/proposals?limit=50')
                .then(function(r) { return r.json(); })
                .then(function(data) { if (data.success) window.renderSelfImprovementProposals(data.proposals || []); })
                .catch(function(err) { if (window.addLog) addLog('Proposals load error: ' + err, 'warning'); });
        };

        window.updateSelfImprovementProposalStatus = function(status) {
            var pid = window._selectedSelfImprovementProposalId;
            if (!pid) return;
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid) + '/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status })
            })
                .then(function(r) { return r.json(); })
                .then(function() { window.refreshSelfImprovementProposals(); })
                .catch(function(err) { if (window.addLog) addLog('Proposal status error: ' + err, 'warning'); });
        };

        window.exportSelfImprovementProposalPrompt = function(target) {
            var pid = window._selectedSelfImprovementProposalId;
            if (!pid) return;
            fetch('/api/self-improvement/proposals/' + encodeURIComponent(pid) + '/export_prompt?target=' + encodeURIComponent(target || 'cursor'))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var pre = document.getElementById('self-improvement-prompt-export-text');
                    if (pre) pre.textContent = data.prompt || data.export || '';
                })
                .catch(function(err) { if (window.addLog) addLog('Export prompt error: ' + err, 'warning'); });
        };

        window.copySelfImprovementExportedPrompt = function() {
            var pre = document.getElementById('self-improvement-prompt-export-text');
            if (!pre || !pre.textContent) return;
            try {
                navigator.clipboard.writeText(pre.textContent);
                if (window.addLog) addLog('Copied export prompt', 'info');
            } catch (e) { if (window.addLog) addLog('Copy failed: ' + e, 'warning'); }
        };

        window.refreshMemoryRankingSummary = function() {
            var el = document.getElementById('memory-ranking-summary');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/memory/ranking/summary?limit=10')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.available) { el.textContent = data.message || 'Ranking unavailable.'; return; }
                    el.textContent = 'Memories ranked: ' + (data.memory_count || 0) + ' · source: ' + (data.sample_source || '—');
                })
                .catch(function(err) { el.textContent = 'Could not load ranking: ' + err; });
        };

        window.refreshPromptContractStatus = function() {
            var el = document.getElementById('prompt-contract-status');
            if (!el) return;
            el.textContent = 'Loading…';
            fetch('/api/prompt-contracts/status')
                .then(function(r) { return r.json(); })
                .then(function(data) { el.textContent = JSON.stringify(data, null, 2).slice(0, 1200); })
                .catch(function(err) { el.textContent = 'Could not load contracts: ' + err; });
        };

"""
text = text.replace(JS_ANCHOR, JS_BLOCK + JS_ANCHOR, 1)

POLL_ANCHOR = "if (typeof window.refreshApiChatHistory === 'function') window.refreshApiChatHistory();"
POLL_EXTRA = """
                        if (typeof window.refreshBrainTrace === 'function') window.refreshBrainTrace();
                        if (typeof window.refreshSelfImprovementProposals === 'function') window.refreshSelfImprovementProposals();
                        if (typeof window.refreshMemoryRankingSummary === 'function') window.refreshMemoryRankingSummary();
                        if (typeof window.refreshPromptContractStatus === 'function') window.refreshPromptContractStatus();"""
idx = text.find(POLL_ANCHOR)
if idx >= 0 and "refreshBrainTrace()" not in text[idx : idx + 500]:
    text = text.replace(POLL_ANCHOR, POLL_ANCHOR + POLL_EXTRA, 1)

PANEL.write_text(text, encoding="utf-8")
verify = PANEL.read_text(encoding="utf-8")
print("written", len(verify), "refreshBrainTrace", "refreshBrainTrace" in verify)
