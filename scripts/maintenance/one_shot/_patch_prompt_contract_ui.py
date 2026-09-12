#!/usr/bin/env python3
"""ONE-SHOT UI REPAIR SCRIPT - NOT RUNTIME TOOLING.

This historical maintenance helper edits CONTROL_PANEL_TEMPLATE anchors.
Do not import, schedule, call from CI, or use as an application runtime path.
Prefer direct reviewed patches for future UI marker changes.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
p = _REPO_ROOT / "project_guardian" / "ui_control_panel.py"
text = p.read_text(encoding="utf-8")

if "Refresh prompt contracts" not in text:
    text = text.replace(
        'onclick="refreshMemoryRankingSummary()">Refresh memory ranking</button>',
        'onclick="refreshMemoryRankingSummary()">Refresh memory ranking</button>\n'
        '                        <button type="button" onclick="refreshPromptContractStatus()">Refresh prompt contracts</button>',
        1,
    )

html_block = """
                        <!-- prompt-contract-visibility-start -->
                        <div id="prompt-contract-panel" style="margin-top: 14px; padding: 12px; background: var(--bg-dark); border-radius: 8px; border: 1px solid var(--border);">
                            <h3 style="margin: 0 0 8px 0;">Prompt Contracts</h3>
                            <p style="font-size: 11px; color: var(--warning); margin: 0 0 8px 0; line-height: 1.45;">
                                Validation visibility only. Defaults remain off unless enabled in config/brain_pipeline.json.
                            </p>
                            <button type="button" onclick="refreshPromptContractStatus()">Refresh prompt contracts</button>
                            <motion.div id="prompt-contract-status" style="margin-top: 10px; font-size: 12px; color: var(--text-secondary); min-height: 72px; line-height: 1.5;">
                                <em>Click Refresh prompt contracts to load status.</em>
                            </div>
                        </div>
                        <!-- prompt-contract-visibility-end -->
""".replace('id="prompt-contract-status"', 'id="prompt-contract-status"').replace(
    "<motion.div id", "<motion.div id"
).replace("<motion.div id", "<div id", 1).replace(
    "            </div>\n        </div>", "            </div>\n        </div>", 1
)

# fix botched - rewrite html_block cleanly
html_block = """
                        <!-- prompt-contract-visibility-start -->
                        <div id="prompt-contract-panel" style="margin-top: 14px; padding: 12px; background: var(--bg-dark); border-radius: 8px; border: 1px solid var(--border);">
                            <h3 style="margin: 0 0 8px 0;">Prompt Contracts</h3>
                            <p style="font-size: 11px; color: var(--warning); margin: 0 0 8px 0; line-height: 1.45;">
                                Validation visibility only. Defaults remain off unless enabled in config/brain_pipeline.json.
                            </p>
                            <button type="button" onclick="refreshPromptContractStatus()">Refresh prompt contracts</button>
                            <div id="prompt-contract-status" style="margin-top: 10px; font-size: 12px; color: var(--text-secondary); min-height: 72px; line-height: 1.5;">
                                <em>Click Refresh prompt contracts to load status.</em>
                            </div>
                        </div>
                        <!-- prompt-contract-visibility-end -->
"""

if "prompt-contract-visibility-start" not in text:
    marker = "<!-- memory-ranking-visibility-end -->"
    if marker in text:
        text = text.replace(marker, marker + "\n" + html_block)

js = r'''
        window._renderPromptContractStatus = function(data) {
            const el = document.getElementById('prompt-contract-status');
            if (!el) return;
            if (!data || data.available === false) {
                el.innerHTML = '<span style="color: var(--danger);">' +
                    window._escapeHtml((data && data.error) || 'Prompt contract status unavailable') + '</span>';
                return;
            }
            let html = '<motion.div><strong>Config:</strong> enabled=' + window._escapeHtml(String(data.enabled)) +
                ', mode=' + window._escapeHtml(String(data.mode)) +
                ', operator_chat=' + window._escapeHtml(String(data.operator_chat)) +
                ', contracts=' + window._escapeHtml(String(data.contract_count || 0)) + '</div>';
            const lv = data.latest_validation || {};
            html += '<div style="margin-top:6px;"><strong>Latest validation:</strong> exists=' +
                window._escapeHtml(String(lv.exists)) + ', valid=' + window._escapeHtml(String(lv.valid_count || 0)) +
                ', invalid=' + window._escapeHtml(String(lv.invalid_count || 0)) +
                ', blocked=' + window._escapeHtml(String(lv.blocked_count || 0)) + '</div>';
            const contracts = Array.isArray(data.contracts) ? data.contracts : [];
            if (contracts.length) {
                html += '<div style="margin-top:8px;"><strong>Contracts</strong><ul style="margin:4px 0 0 16px;padding:0;">';
                contracts.slice(0, 12).forEach(function(c) {
                    html += '<li style="margin-bottom:3px;">' + window._escapeHtml(c.module_name || '') +
                        ' / ' + window._escapeHtml(c.contract_id || '') +
                        ' v' + window._escapeHtml(c.version || '') + '</li>';
                });
                html += '</ul></div>';
            }
            const results = Array.isArray(lv.results) ? lv.results : [];
            if (results.length) {
                html += '<div style="margin-top:8px;"><strong>Validation results</strong><ul style="margin:4px 0 0 16px;padding:0;">';
                results.slice(0, 8).forEach(function(r) {
                    html += '<li style="margin-bottom:4px;"><code>' + window._escapeHtml(r.module_name || '') +
                        '</code> valid=' + window._escapeHtml(String(r.valid)) +
                        ' blocked=' + window._escapeHtml(String(r.blocked));
                    if (r.errors && r.errors.length) {
                        html += ' — ' + window._escapeHtml(r.errors.join('; '));
                    }
                    html += '</li>';
                });
                html += '</ul></div>';
            }
            if (Array.isArray(data.warnings) && data.warnings.length) {
                html += '<div style="margin-top:8px;color:var(--warning);">' +
                    window._escapeHtml(data.warnings.join('; ')) + '</motion.div>';
            }
            el.innerHTML = html;
        };

        window.refreshPromptContractStatus = function() {
            const el = document.getElementById('prompt-contract-status');
            if (!el) return;
            el.innerHTML = '<em style="color: var(--text-secondary);">Loading prompt contract status...</em>';
            fetch('/api/prompt-contracts/status')
                .then(function(r) { return r.json(); })
                .then(function(data) { window._renderPromptContractStatus(data); })
                .catch(function(err) {
                    el.innerHTML = '<span style="color: var(--danger);">' + window._escapeHtml(String(err)) + '</span>';
                });
        };

'''.replace("<motion.div", "<div").replace("</motion.div>", "</div>")

if "window.refreshPromptContractStatus" not in text:
    text = text.replace(
        "        window.refreshMemoryRankingSummary = function() {",
        js + "        window.refreshMemoryRankingSummary = function() {",
        1,
    )

api = '''        @self.app.route("/api/prompt-contracts/status", methods=["GET"])
        def api_prompt_contracts_status():
            try:
                from project_guardian.prompt_contracts.controls import build_prompt_contract_status

                return jsonify(build_prompt_contract_status())
            except Exception as exc:
                logger.warning("prompt-contracts status failed: %s", exc)
                return jsonify({"available": False, "error": str(exc)[:400]}), 500

'''

if "/api/prompt-contracts/status" not in text:
    text = text.replace(
        '        @self.app.route("/api/memory/ranking/summary", methods=["GET"])',
        api + '        @self.app.route("/api/memory/ranking/summary", methods=["GET"])',
        1,
    )

p.write_text(text, encoding="utf-8")
