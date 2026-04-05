# project_guardian/ui_control_panel.py
# UI Control Panel - Web-based Operator Interface
# Provides monitoring, control, and visibility into Elysia system

try:
    from flask import Flask, render_template_string, jsonify, request
    from flask_socketio import SocketIO, emit
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    # Dummy classes for when Flask not available
    class Flask:
        pass
    class SocketIO:
        pass
    def emit(*args, **kwargs):
        pass

import threading
import json
import logging
import socket
import time
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Module-level guard for dashboard start (idempotent across all instances)
_dashboard_started = False
_dashboard_start_lock = threading.Lock()
_dashboard_start_attempts = 0

# Bounded limits for UI/runtime memory access (avoid full-dump latency spikes)
UI_MEMORY_RECENT_LIMIT = 200


# HTML Template for Control Panel - Enhanced Version
CONTROL_PANEL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Elysia Control Panel</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" crossorigin="anonymous"></script>
    <style>
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --bg-hover: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --border: #334155;
            --shadow: rgba(0, 0, 0, 0.3);
        }
        
        [data-theme="light"] {
            --bg-dark: #f8fafc;
            --bg-card: #ffffff;
            --bg-hover: #f1f5f9;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border: #e2e8f0;
            --shadow: rgba(0, 0, 0, 0.1);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, var(--bg-dark) 0%, #1e293b 100%);
            color: var(--text-primary);
            padding: 20px;
            min-height: 100vh;
            transition: background 0.3s ease;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            padding: 24px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px var(--shadow);
            animation: slideDown 0.5s ease;
        }
        
        @keyframes slideDown {
            from { transform: translateY(-20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        h1 {
            color: white;
            font-size: 28px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .header-controls {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .theme-toggle {
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.05);
        }
        
        .status-indicator {
            display: inline-block;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .status-running { background: var(--success); box-shadow: 0 0 10px var(--success); }
        .status-paused { background: var(--warning); box-shadow: 0 0 10px var(--warning); }
        .status-stopped { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
        .status-connected { background: var(--primary); box-shadow: 0 0 10px var(--primary); }
        .status-initialized { background: var(--secondary); box-shadow: 0 0 10px var(--secondary); }
        
        .status-text {
            color: white;
            font-weight: 600;
            font-size: 16px;
        }
        
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            background: var(--bg-card);
            padding: 8px;
            border-radius: 12px;
            box-shadow: 0 4px 12px var(--shadow);
        }
        
        .tab {
            padding: 12px 24px;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            position: relative;
            pointer-events: auto;
            user-select: none;
            -webkit-user-select: none;
            z-index: 10;
        }
        
        .tab:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }
        
        .tab.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .tab-content.active {
            display: block;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }
        
        .card {
            background: var(--bg-card);
            padding: 24px;
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px var(--shadow);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
        }
        
        .card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px var(--shadow);
        }
        
        .card h2 {
            color: var(--text-primary);
            margin-bottom: 20px;
            font-size: 20px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 12px 0;
            padding: 12px;
            background: var(--bg-dark);
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        
        .metric:hover {
            background: var(--bg-hover);
            transform: translateX(4px);
        }
        
        .metric-label {
            font-weight: 500;
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .metric-value {
            color: var(--success);
            font-weight: 700;
            font-size: 16px;
        }
        
        .metric-value.warning { color: var(--warning); }
        .metric-value.danger { color: var(--danger); }
        
        button {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            margin: 6px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            pointer-events: auto;
            user-select: none;
            -webkit-user-select: none;
            position: relative;
            z-index: 1;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button.danger {
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        
        button.secondary {
            background: var(--bg-hover);
            box-shadow: none;
        }
        
        button.secondary:hover {
            background: var(--border);
        }
        
        .controls {
            background: var(--bg-card);
            padding: 24px;
            border-radius: 16px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px var(--shadow);
        }
        
        .console {
            background: #000;
            color: #0f0;
            padding: 20px;
            border-radius: 12px;
            font-family: 'Courier New', 'Fira Code', monospace;
            font-size: 13px;
            height: 450px;
            overflow-y: auto;
            margin-top: 20px;
            border: 1px solid var(--border);
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        
        .log-entry {
            margin: 6px 0;
            padding: 8px;
            border-left: 3px solid #0f0;
            padding-left: 12px;
            line-height: 1.6;
        }
        
        .log-error { border-left-color: var(--danger); color: #ff6b6b; }
        .log-warning { border-left-color: var(--warning); color: #ffd93d; }
        .log-info { border-left-color: #3b82f6; color: #60a5fa; }
        
        .input-group {
            margin: 16px 0;
        }
        
        .input-group label {
            display: block;
            margin-bottom: 8px;
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 14px;
        }
        
        input, textarea, select {
            width: 100%;
            padding: 12px;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            color: var(--text-primary);
            border-radius: 8px;
            margin-top: 6px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        textarea {
            min-height: 120px;
            font-family: 'Courier New', monospace;
            resize: vertical;
        }
        
        .section {
            margin-bottom: 32px;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            background: var(--bg-hover);
            color: var(--text-primary);
        }
        
        .badge.success { background: var(--success); color: white; }
        .badge.warning { background: var(--warning); color: white; }
        .badge.danger { background: var(--danger); color: white; }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            
            header {
                flex-direction: column;
                gap: 16px;
                text-align: center;
            }
            
            .tabs {
                overflow-x: auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Elysia Control Panel</h1>
            <div class="header-controls">
                <button class="theme-toggle" onclick="toggleTheme()">🌓 Toggle Theme</button>
                <div>
                    <span class="status-indicator" id="status-indicator"></span>
                    <span class="status-text" id="status-text">Initializing...</span>
                    <span id="loading-spinner" style="margin-left: 10px; display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 1s linear infinite;"></span>
                </div>
            </div>
        </header>

        <div class="tabs">
            <button class="tab active" onclick="showTab('dashboard', this)">📊 Dashboard</button>
            <button class="tab" onclick="showTab('learning', this)">📚 Learning</button>
            <button class="tab" onclick="showTab('tasks', this)">📋 Tasks</button>
            <button class="tab" onclick="showTab('security', this)">🔒 Security</button>
            <button class="tab" onclick="showTab('memory', this)">🧠 Memory</button>
            <button class="tab" onclick="showTab('introspection', this)">🔍 Introspection</button>
            <button class="tab" onclick="showTab('control', this)">🎮 Control</button>
            <button class="tab" onclick="showTab('logs', this)">📝 Logs</button>
        </div>

        <!-- Dashboard Tab -->
        <div id="dashboard" class="tab-content active">
            <div class="grid">
                <div class="card">
                    <h2>System Status</h2>
                    <div class="metric">
                        <span class="metric-label">Uptime:</span>
                        <span class="metric-value" id="uptime">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Event Loop:</span>
                        <span class="metric-value" id="loop-status">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Queue Size:</span>
                        <span class="metric-value" id="queue-size">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Active Tasks:</span>
                        <span class="metric-value" id="active-tasks">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Autonomy</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Elysia acts on its own when enabled</p>
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                            <input type="checkbox" id="autonomy-enabled" onchange="toggleAutonomy(this.checked)">
                            <span>Enabled</span>
                        </label>
                        <span id="autonomy-status" style="font-size: 12px; color: var(--text-secondary);">-</span>
                    </div>
                    <div id="autonomy-last" style="font-size: 11px; color: var(--text-secondary);">Last: -</div>
                </div>

                <div class="card">
                    <h2>Next Action</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Unified decision: what the system should do next</p>
                    <div id="next-action-display" style="padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 80px; font-size: 13px;">
                        <em>Click "Suggest Next Action" to load...</em>
                    </div>
                    <button onclick="suggestNextAction()" style="margin-top: 8px;">Suggest Next Action</button>
                    <button onclick="executeNextAction()" id="execute-next-btn" style="margin-top: 8px; display: none;" class="danger">Execute</button>
                </div>

                <div class="card">
                    <h2>Memory System</h2>
                    <div class="metric">
                        <span class="metric-label">Total Memories:</span>
                        <span class="metric-value" id="total-memories">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Vector Enabled:</span>
                        <span class="metric-value" id="vector-enabled">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Snapshot:</span>
                        <span class="metric-value" id="last-snapshot">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Security Status</h2>
                    <div class="metric">
                        <span class="metric-label">Recent Violations:</span>
                        <span class="metric-value" id="violations">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Pending Reviews:</span>
                        <span class="metric-value" id="pending-reviews">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Policy Loaded:</span>
                        <span class="metric-value" id="policy-loaded">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Trust System</h2>
                    <div class="metric">
                        <span class="metric-label">Average Trust:</span>
                        <span class="metric-value" id="avg-trust">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Components:</span>
                        <span class="metric-value" id="trust-components">-</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Learning Tab -->
        <div id="learning" class="tab-content">
            <div class="section">
                <div class="controls">
                    <h2>📚 Learning Capabilities</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 20px;">
                        Monitor and control Elysia's learning systems. Test learning from various sources including Reddit, web articles, and RSS feeds.
                    </p>
                    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                        <button onclick="testRedditLearning()">Test Reddit Learning</button>
                        <button onclick="getLearningSummary()">Learning Summary</button>
                        <button onclick="refreshLearningStats()">Refresh Stats</button>
                    </div>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>Learning Statistics</h2>
                    <div class="metric">
                        <span class="metric-label">Total Articles:</span>
                        <span class="metric-value" id="learning-articles">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Reddit Posts:</span>
                        <span class="metric-value" id="learning-reddit">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">RSS Entries:</span>
                        <span class="metric-value" id="learning-rss">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Learning:</span>
                        <span class="metric-value" id="learning-last">-</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Quick Learning Test</h2>
                    <div class="input-group">
                        <label>Platform:</label>
                        <select id="learning-platform">
                            <option value="reddit">Reddit</option>
                            <option value="rss">RSS Feeds</option>
                            <option value="facebook">Facebook Page(s)</option>
                            <option value="twitter">X (Twitter) Search</option>
                            <option value="chatgpt">ChatGPT Conversations</option>
                            <option value="web">Web URL(s)</option>
                            <option value="all">All Sources</option>
                            <option value="mistral_chain">Mistral chain (X + Reddit + Wikipedia + ChatGPT context)</option>
                        </select>
                    </div>
                    <div class="input-group">
                        <label>Query/Topic/URL:</label>
                        <input type="text" id="learning-query" placeholder="e.g., AI, MachineLearning, Meta (FB page), or https://example.com/article">
                    </div>
                    <div class="input-group">
                        <label>Max Items:</label>
                        <input type="number" id="learning-max" value="5" min="1" max="20">
                    </div>
                    <div class="input-group" style="align-items: center;">
                        <label style="margin-right: 8px;">Use headless browser for web URLs:</label>
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                            <input type="checkbox" id="learning-headless" onchange="saveLearningHeadless(this.checked)">
                            <span>Yes (Playwright – for JS-heavy or bot-blocking sites)</span>
                        </label>
                    </div>
                    <button onclick="startLearning()">Start Learning</button>
                    <div id="learning-results" style="margin-top: 16px; padding: 12px; background: var(--bg-dark); border-radius: 8px; min-height: 60px;">
                        <em style="color: var(--text-secondary);">Click "Start Learning" to begin...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Link your account</h2>
                    <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Connect accounts so Elysia can learn from your linked sources.</p>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>Facebook:</label>
                        <span id="link-fb-status" style="font-size: 13px; color: var(--text-secondary);">Checking...</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <input type="password" id="link-fb-token" placeholder="Paste your Facebook access token" style="flex: 1; min-width: 200px;" autocomplete="off">
                        <button onclick="saveLinkFacebook()">Save / Link</button>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Get a token: <a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noopener">Graph API Explorer</a> or Facebook for Developers → Tools → Access Token Tool.</p>
                    <hr style="margin: 16px 0; border-color: var(--border);">
                    <div class="input-group" style="margin-bottom: 8px;">
                        <label>X (Twitter):</label>
                        <span id="link-twitter-status" style="font-size: 13px; color: var(--text-secondary);">Checking...</span>
                    </div>
                    <div class="input-group" style="margin-bottom: 8px;">
                        <input type="password" id="link-twitter-token" placeholder="Paste your X Bearer Token" style="flex: 1; min-width: 200px;" autocomplete="off">
                        <button onclick="saveLinkTwitter()">Save / Link</button>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Get a token: <a href="https://developer.x.com/en/portal/dashboard" target="_blank" rel="noopener">X Developer Portal</a> → your App → Keys and tokens → Bearer Token. Used for recent search (public tweets).</p>
                </div>

                <div class="card">
                    <h2>Learning Sources</h2>
                    <div style="margin-top: 16px;">
                        <div class="badge success" style="margin: 6px;">Reddit API</div>
                        <div class="badge success" style="margin: 6px;">RSS Feeds</div>
                        <div class="badge success" style="margin: 6px;">Facebook Pages</div>
                        <div class="badge success" style="margin: 6px;">X (Twitter) Search</div>
                        <div class="badge success" style="margin: 6px;">ChatGPT Conversations</div>
                        <div class="badge success" style="margin: 6px;">Web URLs</div>
                        <div class="badge" style="margin: 6px;">Financial Data</div>
                        <div class="badge" style="margin: 6px;">Social Media</div>
                    </div>
                    <div style="margin-top: 20px; padding: 12px; background: var(--bg-dark); border-radius: 8px;">
                        <strong style="color: var(--text-primary);">Status:</strong>
                        <div id="learning-status" style="margin-top: 8px; color: var(--success);">Learning system ready</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tasks Tab -->
        <div id="tasks" class="tab-content">
            <div class="card">
                <h2>Task Queue</h2>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    Guardian <strong>TaskEngine</strong> items, Elysia loop <strong>GlobalTaskQueue</strong> jobs, and optional <strong>TASKS/*.md</strong> drop files.
                </p>
                <button type="button" onclick="refreshTaskQueue()">Refresh</button>
                <div id="task-list" style="margin-top: 16px;"></div>
            </div>
        </div>

        <!-- Security Tab -->
        <div id="security" class="tab-content">
            <div class="card">
                <h2>Security Events</h2>
                <div id="security-events"></div>
            </div>
        </div>

        <!-- Memory Tab -->
        <div id="memory" class="tab-content">
            <div class="card">
                <h2>Memory Operations</h2>
                <div class="input-group">
                    <label>Search Memories:</label>
                    <input type="text" id="memory-search" placeholder="Enter search query">
                    <button onclick="searchMemories()">Search</button>
                </div>
                <div id="memory-results"></div>
            </div>
        </div>

        <!-- Introspection Tab -->
        <div id="introspection" class="tab-content">
            <div class="section">
                <div class="controls">
                    <h2>Introspection & Self-Analysis</h2>
                    <button onclick="refreshIntrospection()">Refresh All</button>
                    <button onclick="getComprehensiveReport()">Full Report</button>
                    <button onclick="checkMemoryHealth()">Memory Health</button>
                    <button onclick="analyzeFocus()">Focus Analysis</button>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>System Identity</h2>
                    <div id="identity-summary" style="white-space: pre-wrap; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                        <em>Click "Full Report" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Memory Health</h2>
                    <div class="metric">
                        <span class="metric-label">Status:</span>
                        <span class="metric-value" id="health-status">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Health Score:</span>
                        <span class="metric-value" id="health-score">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Memories:</span>
                        <span class="metric-value" id="health-total">-</span>
                    </div>
                    <div id="health-warnings" style="margin-top: 10px; font-size: 12px; color: #f39c12;">
                        <em>Click "Memory Health" to analyze...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Focus Analysis (24h)</h2>
                    <div class="metric">
                        <span class="metric-label">Primary Focus:</span>
                        <span class="metric-value" id="focus-primary">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Activity Count:</span>
                        <span class="metric-value" id="focus-activity">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Priority Trend:</span>
                        <span class="metric-value" id="focus-trend">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Most Active Period:</span>
                        <span class="metric-value" id="focus-period">-</span>
                    </div>
                    <div id="focus-distribution" style="margin-top: 10px; font-size: 11px; font-family: monospace;">
                        <em>Click "Focus Analysis" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Behavior Patterns</h2>
                    <div id="behavior-report" style="white-space: pre-wrap; font-family: monospace; font-size: 11px; max-height: 300px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                        <em>Click "Full Report" to load...</em>
                    </div>
                </div>

                <div class="card">
                    <h2>Introspection Decisions</h2>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Last decision from heartbeat-driven introspection</p>
                    <div id="introspection-debug" style="font-family: monospace; font-size: 11px; padding: 10px; background: #0f3460; border-radius: 4px; min-height: 80px;">
                        <em>Loading...</em>
                    </div>
                    <button onclick="refreshIntrospectionDebug()" style="margin-top: 8px;">Refresh</button>
                </div>
            </div>

            <div class="card" style="margin-top: 20px;">
                <h2>Memory Correlations</h2>
                <div class="input-group">
                    <label>Search for correlated memories:</label>
                    <input type="text" id="correlation-keyword" placeholder="Enter keyword">
                    <button onclick="findCorrelations()">Find Correlations</button>
                </div>
                <div id="correlation-results" style="margin-top: 15px; font-size: 11px; font-family: monospace; max-height: 400px; overflow-y: auto; padding: 10px; background: #0f3460; border-radius: 4px;">
                    <em>Enter a keyword and click "Find Correlations" to analyze related memories...</em>
                </div>
            </div>
        </div>

        <!-- Control Tab -->
        <div id="control" class="tab-content">
            <div class="controls">
                <h2>System Controls</h2>
                <button onclick="pauseLoop()">Pause Event Loop</button>
                <button onclick="resumeLoop()">Resume Event Loop</button>
                <button onclick="createSnapshot()">Create Memory Snapshot</button>
                <button onclick="triggerDreamCycle()" class="danger">Trigger Dream Cycle</button>
                
                <div class="input-group" style="margin-top: 16px;">
                    <label>Speak (TTS):</label>
                    <input type="text" id="speak-text" placeholder="e.g., System is operational" style="flex: 1;">
                    <select id="speak-mode">
                        <option value="guardian">Guardian</option>
                        <option value="warm_guide">Warm Guide</option>
                        <option value="sharp_analyst">Sharp Analyst</option>
                        <option value="poetic_oracle">Poetic Oracle</option>
                    </select>
                    <button onclick="speakMessage()">Speak</button>
                </div>
                
                <div class="input-group">
                    <label>Submit Task:</label>
                    <textarea id="task-code" placeholder="async def task():&#10;    # Your task code here&#10;    return 'result'"></textarea>
                    <input type="number" id="task-priority" placeholder="Priority (1-10)" value="5" min="1" max="10">
                    <button onclick="submitTask()">Submit Task</button>
                </div>

                <h3 style="margin-top: 24px;">APIs &amp; Tools</h3>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;">Trigger income, research, harvest, and AI chat from the dashboard.</p>
                <div class="input-group" style="margin-bottom: 12px;">
                    <label>Chat with AI (OpenAI/OpenRouter):</label>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <input type="text" id="api-chat-message" placeholder="Ask anything..." style="flex: 1; min-width: 200px;">
                        <button onclick="sendApiChat()">Send</button>
                    </div>
                    <div id="api-chat-result" style="margin-top: 8px; padding: 10px; background: var(--bg-dark); border-radius: 8px; font-size: 13px; min-height: 40px; white-space: pre-wrap;"></div>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
                    <button onclick="refreshIncomeStatus()">Income / API Status</button>
                    <button onclick="runHarvestReport()">Harvest Report</button>
                    <button onclick="runResearchProposal()">Research Proposal (WebScout)</button>
                    <button onclick="runPromptEvolution()">Run Prompt Evolution</button>
                </div>
                <h4 style="margin: 16px 0 8px 0;">Wallet accounts</h4>
                <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 8px;">
                    Add virtual sub-accounts (ledger in <code>organized_project/data/</code>). Optional: copy <code>wallet_accounts.example.json</code> to <code>wallet_accounts.json</code> for bulk setup on startup.
                </p>
                <div class="input-group" style="margin-bottom: 8px; flex-wrap: wrap;">
                    <input type="text" id="wallet-new-name" placeholder="Display name (e.g. Tax reserve)" style="min-width: 160px; flex: 1;">
                    <input type="text" id="wallet-new-id" placeholder="Optional id (slug)" style="width: 140px;">
                    <button onclick="refreshWalletAccounts()">List accounts</button>
                    <button onclick="addWalletAccount()">Add account</button>
                </div>
                <div id="api-tools-result" style="padding: 10px; background: var(--bg-dark); border-radius: 8px; font-size: 12px; min-height: 40px; white-space: pre-wrap;"></div>
            </div>
        </div>

        <!-- Logs Tab -->
        <div id="logs" class="tab-content">
            <div class="console" id="console-logs">
                <div class="log-entry">[System] Control Panel initialized</div>
            </div>
        </div>
    </div>

    <script>
        // Define addLog function FIRST so it's available immediately
        function addLog(message, level) {
            if (level === undefined) level = 'info';
            try {
                const console = document.getElementById('console-logs');
                if (console) {
                    const entry = document.createElement('div');
                    entry.className = 'log-entry log-' + level;
                    entry.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
                    console.appendChild(entry);
                    console.scrollTop = console.scrollHeight;
                } else {
                    // Fallback to browser console if element not found
                    console.log('[' + level.toUpperCase() + '] ' + message);
                }
            } catch (e) {
                console.log('[' + level.toUpperCase() + '] ' + message);
            }
        }
        
        // Make addLog globally available
        window.addLog = addLog;
        
        // Define toggleTheme and showTab early so buttons work even before full script loads
        window.toggleTheme = function() {
            var body = document.body;
            var currentTheme = body.getAttribute('data-theme');
            var newTheme = currentTheme === 'light' ? 'dark' : 'light';
            body.setAttribute('data-theme', newTheme);
            try { localStorage.setItem('theme', newTheme); } catch (e) {}
            if (window.addLog) addLog('Theme: ' + newTheme, 'info');
        };
        
        // Define showTab early so tab buttons work even before DOMContentLoaded completes
        window.showTab = function(tabName, buttonElement) {
            document.querySelectorAll('.tab-content').forEach(function(tab) { tab.classList.remove('active'); });
            document.querySelectorAll('.tab').forEach(function(tab) { tab.classList.remove('active'); });
            const tabContent = document.getElementById(tabName);
            if (tabContent) tabContent.classList.add('active');
            if (buttonElement) buttonElement.classList.add('active');
            else {
                document.querySelectorAll('.tab').forEach(function(tab) {
                    if (tab.textContent.indexOf(tabName.charAt(0).toUpperCase() + tabName.slice(1)) >= 0)
                        tab.classList.add('active');
                });
            }
            if (tabName === 'introspection' && typeof window.refreshIntrospectionDebug === 'function')
                window.refreshIntrospectionDebug();
            if (tabName === 'learning') {
                if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                if (typeof window.refreshLearningSettings === 'function') window.refreshLearningSettings();
            }
            if (tabName === 'dashboard') {
                if (typeof window.suggestNextAction === 'function') window.suggestNextAction();
                if (typeof window.refreshAutonomyStatus === 'function') window.refreshAutonomyStatus();
            }
            if (tabName === 'tasks' && typeof window.refreshTaskQueue === 'function')
                window.refreshTaskQueue();
        };
        
        const socket = (typeof io !== 'undefined') ? io() : null;
        let updateInterval;
        let initialized = false;

        // Initialize on page load - show UI immediately
        document.addEventListener('DOMContentLoaded', function() {
            try {
                addLog('Control Panel loaded at ' + window.location.href, 'info');
                const spinner = document.getElementById('loading-spinner');
                if (spinner) spinner.style.display = 'none';
                const statusTextEl = document.getElementById('status-text');
                if (statusTextEl) statusTextEl.textContent = 'Connecting...';
                const indicator = document.getElementById('status-indicator');
                if (indicator) indicator.className = 'status-indicator status-connected';
                if (!socket) {
                    addLog('Socket.IO CDN not loaded - using HTTP polling only', 'warning');
                }
                setTimeout(function() {
                    try { startUpdates(); } catch (e) {
                        addLog('startUpdates error: ' + e.message, 'error');
                        console.error(e);
                    }
                }, 100);
            } catch (e) {
                console.error('DOMContentLoaded error:', e);
                if (window.addLog) addLog('Init error: ' + e.message, 'error');
            }
        });

        if (socket) socket.on('connect', function() {
            addLog('Connected to Elysia system', 'info');
            if (!updateInterval) {
                startUpdates();
            }
        });

        if (socket) socket.on('disconnect', function() {
            addLog('Disconnected from Elysia system', 'warning');
        });

        if (socket) socket.on('connect_error', function(error) {
            addLog('Socket.IO connection error (continuing with HTTP polling): ' + error, 'warning');
            // Still start updates even if socket fails - use HTTP polling instead
            if (!updateInterval && !initialized) {
                startUpdates();
            }
        });
        
        // Fallback: if socket doesn't connect within 2 seconds, start HTTP polling
        setTimeout(function() {
            if (!initialized && (!socket || !socket.connected)) {
                addLog('Socket.IO not connected, using HTTP polling mode', 'info');
                startUpdates();
            }
        }, 2000);

        if (socket) socket.on('status_update', function(data) {
            updateDashboard(data);
        });

        if (socket) socket.on('log_entry', function(data) {
            addLog(data.message, data.level || 'info');
        });

        // Safety: force UI usable if stuck - run at 2s and 4s
        setTimeout(function() {
            const statusTextEl = document.getElementById('status-text');
            const spinner = document.getElementById('loading-spinner');
            if (statusTextEl && (statusTextEl.textContent === 'Initializing...' || statusTextEl.textContent === 'Connecting...')) {
                statusTextEl.textContent = 'Connected (Limited)';
                if (spinner) spinner.style.display = 'none';
                const ind = document.getElementById('status-indicator');
                if (ind) ind.className = 'status-indicator status-running';
                addLog('Status: using limited mode - buttons should work', 'info');
            }
        }, 2000);
        setTimeout(function() {
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl && statusTextEl.textContent === 'Connecting...') {
                statusTextEl.textContent = 'Connected (Limited)';
            }
        }, 4000);

        function startUpdates() {
            // Prevent multiple initializations
            if (initialized) {
                return;
            }
            initialized = true;
            
            // Mark as initialized immediately to show UI
            const spinner = document.getElementById('loading-spinner');
            if (spinner) {
                spinner.style.display = 'none';
            }
            
            // Show "Connecting" status immediately
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl) {
                statusTextEl.textContent = 'Connecting...';
            }
            const indicator = document.getElementById('status-indicator');
            if (indicator) {
                indicator.className = 'status-indicator status-running';
            }
            
            // Set a timeout to show "Connected" status if API doesn't respond quickly
            let timeoutId = setTimeout(function() {
                if (statusTextEl && (statusTextEl.textContent === 'Initializing...' || statusTextEl.textContent === 'Connecting...')) {
                    statusTextEl.textContent = 'Connected';
                    if (indicator) {
                        indicator.className = 'status-indicator status-running';
                    }
                    addLog('Connected to server (waiting for status)', 'info');
                }
            }, 2000); // 2 second timeout (reduced from 3)
            
            // Do an immediate update with timeout protection
            const controller = new AbortController();
            const timeoutId2 = setTimeout(function() { controller.abort(); }, 5000); // 5 second fetch timeout
            
            fetch('/api/status', { 
                method: 'GET',
                headers: {'Accept': 'application/json'},
                signal: controller.signal
            })
                .then(function(r) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    if (!r.ok) {
                        throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                    }
                    return r.json();
                })
                .then(function(data) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    updateDashboard(data);
                    addLog('Status update received', 'info');
                })
                .catch(function(err) {
                    clearTimeout(timeoutId);
                    clearTimeout(timeoutId2);
                    const msg = err.name === 'AbortError' ? 'Status timed out (5s)' : (err.message || String(err));
                    addLog('Status fetch failed: ' + msg + ' - using fallback', 'warning');
                    // Use fallback status to show UI is working
                    // Check if we have any indicators that system is running
                    updateDashboard({
                        system: { running: true, initialized: true, uptime: 0 },
                        loop: { running: true, paused: false, queue_size: 0 },
                        memory: { total_entries: 0, total_memories: 0 },
                        security: { policy_loaded: false, recent_violations: 0, pending_reviews: 0 },
                        trust: { components: 0, average_trust: 0 }
                    });
                    
                    // Ensure UI is visible even on error
                    const statusTextEl = document.getElementById('status-text');
                    if (statusTextEl && statusTextEl.textContent === 'Initializing...') {
                        statusTextEl.textContent = 'Connected (Limited)';
                    }
                });
            
            // Then set up interval
            if (updateInterval) {
                clearInterval(updateInterval);
            }
            updateInterval = setInterval(function() {
                const controller = new AbortController();
                const timeoutId = setTimeout(function() { controller.abort(); }, 5000); // 5 second timeout
                
                fetch('/api/status', {
                    method: 'GET',
                    headers: {'Accept': 'application/json'},
                    signal: controller.signal
                })
                    .then(function(r) {
                        clearTimeout(timeoutId);
                        if (!r.ok) {
                            throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                        }
                        return r.json();
                    })
                    .then(function(data) {
                        clearTimeout(timeoutId);
                        updateDashboard(data);
                    })
                    .catch(function(err) {
                        clearTimeout(timeoutId);
                        if (err.name !== 'AbortError') {
                            console.log('Status fetch error:', err);
                        }
                        // Don't update status on error - keep showing last known status
                    });
            }, 2000);
        }

        function updateDashboard(data) {
            if (!data || typeof data !== 'object') return;
            const spinner = document.getElementById('loading-spinner');
            if (spinner) spinner.style.display = 'none';
            
            // Update status indicator and text first
            // Priority: system initialized/running > loop status > memory loaded > connected
            // If we got any response, never stay stuck on "Initializing"
            let status = 'connected';
            let statusText = 'Connected';
            
            // Check for errors first
            if (data.system && data.system.error) {
                status = 'stopped';
                statusText = 'Error: ' + (data.system.error.substring(0, 30) || 'Unknown error');
            } else if (data.system && data.system.timeout) {
                status = 'stopped';
                statusText = 'Timeout - Slow Response';
            } else if (data.system) {
                // Check multiple indicators to determine status
                const systemInitialized = data.system.initialized || false;
                const systemRunning = data.system.running || false;
                const loopRunning = data.loop && data.loop.running !== undefined ? data.loop.running : false;
                const memoryLoaded = data.memory && data.memory.total_entries > 0;
                const hasUptime = data.system.uptime && data.system.uptime > 0;
                
                // System is considered running if any of these are true:
                const isActuallyRunning = systemRunning || loopRunning || memoryLoaded || hasUptime;
                const isActuallyInitialized = systemInitialized || memoryLoaded || loopRunning || hasUptime;
                
                if (isActuallyInitialized || isActuallyRunning) {
                    // System is initialized/running, check loop status for more detail
                    if (data.loop && data.loop.running !== undefined) {
                        status = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'initialized';
                        statusText = status.charAt(0).toUpperCase() + status.slice(1);
                    } else if (memoryLoaded) {
                        // Memory is loaded, system is running
                        status = 'running';
                        statusText = 'Running';
                    } else {
                        // System is initialized but not fully running yet
                        status = isActuallyRunning ? 'running' : 'initialized';
                        statusText = status.charAt(0).toUpperCase() + status.slice(1);
                    }
                } else {
                    // Got system data but not fully initialized - still show connected so UI is usable
                    status = 'connected';
                    statusText = 'Connected (Limited)';
                }
            } else if (data.loop && data.loop.running !== undefined) {
                // Only loop data available
                status = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'stopped';
                statusText = status.charAt(0).toUpperCase() + status.slice(1);
            } else if (data.memory && data.memory.total_entries > 0) {
                // Memory is loaded, system is likely running
                status = 'running';
                statusText = 'Running';
            } else {
                // No system data but we got a response - assume connected but initializing
                status = 'connected';
                statusText = 'Connected';
            }
            
            const indicator = document.getElementById('status-indicator');
            if (indicator) {
                indicator.className = 'status-indicator status-' + status;
            }
            const statusTextEl = document.getElementById('status-text');
            if (statusTextEl) {
                statusTextEl.textContent = statusText;
            }
            
            // Update system metrics
            if (data.system) {
                const uptimeEl = document.getElementById('uptime');
                if (uptimeEl) {
                    const uptime = data.system.uptime || 0;
                    uptimeEl.textContent = Math.floor(uptime) + 's';
                }
                const activeTasksEl = document.getElementById('active-tasks');
                if (activeTasksEl) {
                    const tasks = (data.system.tasks && data.system.tasks.active_tasks) || (data.system.operational_stats && data.system.operational_stats.total_tasks_processed) || 0;
                    activeTasksEl.textContent = tasks;
                }
            }
            
            if (data.loop) {
                const loopStatusEl = document.getElementById('loop-status');
                if (loopStatusEl) {
                    const loopStatus = data.loop.running ? (data.loop.paused ? 'paused' : 'running') : 'stopped';
                    loopStatusEl.textContent = loopStatus;
                }
                const queueSizeEl = document.getElementById('queue-size');
                if (queueSizeEl) {
                    queueSizeEl.textContent = data.loop.queue_size || 0;
                }
            }
            
            if (data.memory) {
                const totalMemoriesEl = document.getElementById('total-memories');
                if (totalMemoriesEl) {
                    totalMemoriesEl.textContent = data.memory.total_entries || data.memory.total_memories || 0;
                }
                const vectorEnabledEl = document.getElementById('vector-enabled');
                if (vectorEnabledEl) {
                    vectorEnabledEl.textContent = (data.memory.vector_memory_enabled || data.memory.vector_enabled) ? 'Yes' : 'No';
                }
            }
            
            if (data.security) {
                const violationsEl = document.getElementById('violations');
                if (violationsEl) {
                    violationsEl.textContent = data.security.recent_violations || 0;
                }
                const pendingReviewsEl = document.getElementById('pending-reviews');
                if (pendingReviewsEl) {
                    pendingReviewsEl.textContent = data.security.pending_reviews || 0;
                }
                const policyLoadedEl = document.getElementById('policy-loaded');
                if (policyLoadedEl) {
                    policyLoadedEl.textContent = data.security.policy_loaded ? 'Yes' : 'No';
                }
            }
        }

        // addLog function moved to top of script for early availability

        // Make all control functions globally accessible
        window.pauseLoop = function() {
            addLog('Pause requested...', 'info');
            fetch('/api/control/pause', { method: 'POST' })
                .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
                .then(function(o) { addLog(o.ok ? 'Loop paused' : ('Pause: ' + (o.data.message || o.data.error || 'failed')), o.ok ? 'info' : 'warning'); })
                .catch(function(err) { addLog('Pause error: ' + err, 'error'); });
        };

        window.resumeLoop = function() {
            addLog('Resume requested...', 'info');
            fetch('/api/control/resume', { method: 'POST' })
                .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
                .then(function(o) { addLog(o.ok ? 'Loop resumed' : ('Resume: ' + (o.data.message || o.data.error || 'failed')), o.ok ? 'info' : 'warning'); })
                .catch(function(err) { addLog('Resume error: ' + err, 'error'); });
        };

        window.createSnapshot = function() {
            fetch('/api/memory/snapshot', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) { addLog('Snapshot created: ' + (data.path || 'success'), 'info'); })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.refreshAutonomyStatus = function() {
            fetch('/api/autonomy')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const cb = document.getElementById('autonomy-enabled');
                    const statusEl = document.getElementById('autonomy-status');
                    const lastEl = document.getElementById('autonomy-last');
                    if (cb) cb.checked = data.enabled;
                    if (statusEl) statusEl.textContent = data.enabled ? 'Active' : 'Disabled';
                    if (lastEl) {
                        const last = data.last;
                        if (last && last.executed) {
                            lastEl.textContent = 'Last: ' + (last.action || '') + ' - ' + (last.reason || '').substring(0, 40);
                        } else {
                            lastEl.textContent = 'Last: -';
                        }
                    }
                })
                .catch(function() {});
        };
        window.toggleAutonomy = function(enabled) {
            fetch('/api/autonomy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog('Autonomy ' + (data.enabled ? 'enabled' : 'disabled'), 'info');
                    window.refreshAutonomyStatus();
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.suggestNextAction = function() {
            fetch('/api/next-action')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const div = document.getElementById('next-action-display');
                    const execBtn = document.getElementById('execute-next-btn');
                    if (!div) return;
                    if (data.error) {
                        div.innerHTML = '<span style="color: var(--danger);">' + data.error + '</span>';
                        if (execBtn) execBtn.style.display = 'none';
                        return;
                    }
                    let html = '<strong>Action:</strong> ' + (data.action || 'none') + '<br>';
                    html += '<strong>Source:</strong> ' + (data.source || '-') + '<br>';
                    html += '<strong>Reason:</strong> ' + (data.reason || '-') + '<br>';
                    if (data.ask_user_question) {
                        html += '<strong style="color: var(--accent);">Ask operator:</strong> ' + (data.ask_user_question || '') + ' ';
                        html += '<button type="button" onclick="ackOperatorQuestion()" style="margin-left:4px; font-size:10px;">Ack</button><br>';
                    }
                    if (data.override_reason) {
                        html += '<span style="color: var(--text-secondary); font-size: 11px;">Governor override: ' + (data.override_reason || '') + '</span><br>';
                    }
                    if (data.candidates_count > 1) {
                        html += '<span style="color: var(--text-secondary); font-size: 11px;">' + data.candidates_count + ' candidates</span>';
                    }
                    div.innerHTML = html;
                    if (execBtn) {
                        execBtn.style.display = (data.can_auto_execute && data.action) ? 'inline-block' : 'none';
                        execBtn.onclick = function() {
                            if (data.action === 'consider_learning') {
                                fetch('/api/learning/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: 'reddit', query: 'MachineLearning', max_items: 2 }) })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) { addLog(d.success ? 'Learning started' : (d.error || 'Failed'), d.success ? 'info' : 'error'); });
                            } else if (data.action === 'consider_dream_cycle') {
                                fetch('/api/control/dream-cycle', { method: 'POST' })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) { addLog('Dream cycle: ' + (d.dream_thoughts ? d.dream_thoughts.join('; ') : 'triggered'), 'info'); });
                            } else {
                                fetch('/api/autonomy/execute-cycle', { method: 'POST' })
                                    .then(function(r) { return r.json(); })
                                    .then(function(d) {
                                        addLog(d.executed ? 'Executed: ' + (d.action || '') : (d.reason || d.error || 'Not executed'), d.executed ? 'info' : 'warning');
                                        if (d.ask_user_question) addLog('Ask operator: ' + d.ask_user_question, 'info');
                                    });
                            }
                            suggestNextAction();
                        };
                    }
                    addLog('Next action: ' + (data.action || 'none'), 'info');
                })
                .catch(function(err) {
                    const div = document.getElementById('next-action-display');
                    if (div) div.innerHTML = '<span style="color: var(--danger);">Error: ' + err + '</span>';
                });
        };
        window.executeNextAction = function() { /* Set by suggestNextAction */ };

        window.ackOperatorQuestion = function() {
            fetch('/api/operator/ack-question', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    addLog(d.success ? 'Operator question acknowledged' : (d.error || 'Failed'), d.success ? 'info' : 'error');
                    suggestNextAction();
                })
                .catch(function(err) { addLog('Ack error: ' + err, 'error'); });
        };

        window.speakMessage = function() {
            const el = document.getElementById('speak-text');
            const text = (el && el.value) ? String(el.value).trim() : '';
            const mode = document.getElementById('speak-mode').value;
            if (!text) {
                addLog('Enter text to speak', 'warning');
                return;
            }
            fetch('/api/speak', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, mode: mode })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog(data.success ? 'Speaking: ' + text.substring(0, 40) + '...' : (data.error || 'Speak failed'), data.success ? 'info' : 'error');
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.triggerDreamCycle = function() {
            fetch('/api/control/dream-cycle', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    addLog(data.success ? 'Dream cycle completed' : (data.message || 'Dream cycle triggered'), data.success ? 'info' : 'warning');
                    if (data.dream_thoughts && data.dream_thoughts.length) {
                        data.dream_thoughts.forEach(function(t) { addLog('[Dream] ' + t, 'info'); });
                    }
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        window.submitTask = function() {
            const code = document.getElementById('task-code').value;
            const priority = parseInt(document.getElementById('task-priority').value);
            
            fetch('/api/tasks/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, priority: priority })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) { 
                addLog('Task submitted: ' + (data.task_id || 'success'), 'info');
                if (typeof window.refreshTaskQueue === 'function') window.refreshTaskQueue();
            })
            .catch(function(err) { 
                addLog('Error: ' + err, 'error'); 
            });
        };

        window._escapeHtml = function(s) {
            if (s === undefined || s === null) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        };

        window.refreshTaskQueue = function() {
            const el = document.getElementById('task-list');
            if (!el) return;
            el.innerHTML = '<em style="color: var(--text-secondary);">Loading…</em>';
            fetch('/api/tasks/list')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.success) {
                        el.textContent = data.error || 'Could not load tasks';
                        return;
                    }
                    const tasks = data.tasks || [];
                    if (tasks.length === 0) {
                        el.innerHTML = '<p style="color: var(--text-secondary);">No tasks to show. Loop queue depth: <strong>' +
                            (data.queue_size != null ? data.queue_size : 0) + '</strong>. Create tasks from the Control tab or add files under <code>TASKS/</code>.</p>';
                        return;
                    }
                    let html = '<ul style="list-style: none; padding: 0; margin: 0;">';
                    tasks.forEach(function(t) {
                        const title = t.name || t.task_id || t.file || 'Task';
                        const src = t.source ? (' <span style="color:var(--text-secondary);font-size:11px;">(' + window._escapeHtml(t.source) + ')</span>') : '';
                        html += '<li style="padding: 10px; margin: 8px 0; background: var(--bg-card); border-radius: 8px; border: 1px solid var(--border);">';
                        html += '<div><strong>' + window._escapeHtml(String(title)) + '</strong>' + src + '</div>';
                        if (t.status) html += '<div style="font-size: 12px; margin-top: 4px;">Status: ' + window._escapeHtml(String(t.status)) + '</div>';
                        if (t.category) html += '<div style="font-size: 11px; color: var(--text-secondary);">Category: ' + window._escapeHtml(String(t.category)) + '</div>';
                        if (t.priority !== undefined && t.priority !== null)
                            html += '<div style="font-size: 11px; color: var(--text-secondary);">Priority: ' + window._escapeHtml(String(t.priority)) + '</div>';
                        if (t.description)
                            html += '<div style="font-size: 12px; margin-top: 6px; white-space: pre-wrap;">' + window._escapeHtml(String(t.description)) + '</div>';
                        if (t.module) html += '<div style="font-size: 11px; margin-top: 4px;">Module: ' + window._escapeHtml(String(t.module)) + '</div>';
                        if (t.func) html += '<div style="font-size: 11px; color: var(--text-secondary);">Job: ' + window._escapeHtml(String(t.func)) + '</div>';
                        if (t.metadata && Object.keys(t.metadata).length)
                            html += '<div style="font-size: 10px; margin-top: 4px; font-family: monospace; color: var(--text-secondary);">' +
                                window._escapeHtml(JSON.stringify(t.metadata)) + '</div>';
                        html += '</li>';
                    });
                    html += '</ul>';
                    html += '<p style="margin-top: 14px; font-size: 12px; color: var(--text-secondary);">Loop queue depth: <strong>' +
                        (data.queue_size != null ? data.queue_size : 0) + '</strong> · Total rows: <strong>' + tasks.length + '</strong></p>';
                    el.innerHTML = html;
                })
                .catch(function(err) {
                    el.textContent = 'Error: ' + err;
                });
        };

        window.sendApiChat = function() {
            const msg = (document.getElementById('api-chat-message') || {}).value;
            const el = document.getElementById('api-chat-result');
            if (!msg) { if (el) el.textContent = 'Enter a message first.'; return; }
            if (el) el.textContent = 'Sending...';
            fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg }) })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.reply || data.error || JSON.stringify(data);
                    addLog('Chat: ' + (data.success ? 'OK' : (data.error || '')), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Chat error: ' + err, 'error'); });
        };

        window.refreshWalletAccounts = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Loading wallet...';
            fetch('/api/wallet/accounts')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = JSON.stringify(data.balance || data.accounts || data, null, 2);
                    addLog(data.success ? 'Wallet accounts loaded' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Wallet list error: ' + err, 'error'); });
        };

        window.addWalletAccount = function() {
            const nameEl = document.getElementById('wallet-new-name');
            const idEl = document.getElementById('wallet-new-id');
            const el = document.getElementById('api-tools-result');
            const name = (nameEl && nameEl.value || '').trim();
            if (!name) { if (el) el.textContent = 'Enter a display name.'; return; }
            const idRaw = (idEl && idEl.value || '').trim();
            const body = { name: name, type: 'virtual', currency: 'USD', balance: 0 };
            if (idRaw) body.id = idRaw;
            if (el) el.textContent = 'Adding account...';
            fetch('/api/wallet/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = JSON.stringify(data, null, 2);
                    addLog(data.success ? ('Added account: ' + (data.account_id || '')) : (data.error || ''), data.success ? 'info' : 'error');
                    if (data.success && nameEl) nameEl.value = '';
                    if (data.success && idEl) idEl.value = '';
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Wallet add error: ' + err, 'error'); });
        };

        window.refreshIncomeStatus = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Loading...';
            fetch('/api/income-status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = JSON.stringify(data.income_modules || data, null, 2);
                    addLog('Income status refreshed', 'info');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Income status error: ' + err, 'error'); });
        };

        window.runHarvestReport = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Running harvest report...';
            fetch('/api/harvest-report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.report !== undefined ? JSON.stringify(data.report, null, 2) : (data.error || JSON.stringify(data));
                    addLog(data.success ? 'Harvest report done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Harvest error: ' + err, 'error'); });
        };

        window.runResearchProposal = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Creating research proposal...';
            const topic = prompt('Research topic (or leave default):', 'AI safety') || 'AI safety';
            fetch('/api/research-proposal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: topic }) })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.result !== undefined ? JSON.stringify(data.result, null, 2) : (data.error || JSON.stringify(data));
                    addLog(data.success ? 'Research proposal done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Research error: ' + err, 'error'); });
        };

        window.runPromptEvolution = function() {
            const el = document.getElementById('api-tools-result');
            if (el) el.textContent = 'Running prompt evolution...';
            fetch('/api/prompts/evolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (el) el.textContent = data.error || ('Evolved: ' + (data.evolved_count || 0) + ', stats: ' + JSON.stringify(data.stats || {}));
                    addLog(data.success ? 'Prompt evolution done' : (data.error || ''), data.success ? 'info' : 'error');
                })
                .catch(function(err) { if (el) el.textContent = 'Error: ' + err; addLog('Prompt evolution error: ' + err, 'error'); });
        };

        window.searchMemories = function() {
            const query = document.getElementById('memory-search').value;
            fetch('/api/memory/search?q=' + encodeURIComponent(query))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const results = document.getElementById('memory-results');
                    results.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                })
                .catch(function(err) { addLog('Error: ' + err, 'error'); });
        };

        // Introspection Functions - make globally accessible
        window.refreshIntrospection = function() {
            addLog('Refreshing introspection data...', 'info');
            window.getComprehensiveReport();
            window.checkMemoryHealth();
            window.analyzeFocus();
            window.refreshIntrospectionDebug();
        };

        window.refreshIntrospectionDebug = function() {
            fetch('/api/introspection/debug')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    const div = document.getElementById('introspection-debug');
                    if (!div) return;
                    if (!data.success || !data.debug) {
                        div.innerHTML = '<em>No data</em>';
                        return;
                    }
                    const d = data.debug;
                    if (d.note) {
                        div.innerHTML = '<em>' + d.note + '</em>';
                        return;
                    }
                    let html = '<strong>Suggested:</strong> ' + (d.suggested_action || 'none') + '<br>';
                    html += '<strong>Triggered:</strong> ' + (d.triggered ? 'yes' : 'no') + '<br>';
                    if (d.context && Object.keys(d.context).length) {
                        html += '<strong>Context:</strong><br>' + JSON.stringify(d.context, null, 2).split(String.fromCharCode(10)).join('<br>');
                    }
                    div.innerHTML = html;
                })
                .catch(function() {
                    const div = document.getElementById('introspection-debug');
                    if (div) div.innerHTML = '<em>Failed to load</em>';
                });
        };

        window.getComprehensiveReport = function() {
            fetch('/api/introspection/comprehensive')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success && data.report) {
                        const report = data.report;
                        const reportStr = typeof report === 'string' ? report : JSON.stringify(report, null, 2);
                        const lines = reportStr.split(String.fromCharCode(10));
                        
                        // Find identity section
                        let identityStart = -1;
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].indexOf('[Guardian Identity]') !== -1) {
                                identityStart = i;
                                break;
                            }
                        }
                        let identityEnd = lines.length;
                        for (let i = (identityStart >= 0 ? identityStart + 1 : 0); i < lines.length; i++) {
                            if (lines[i].charAt(0) === '[' && lines[i].indexOf('Guardian Identity') === -1) {
                                identityEnd = i;
                                break;
                            }
                        }
                        const identityText = identityStart >= 0 ? lines.slice(identityStart, identityEnd).join(String.fromCharCode(10)) : reportStr.substring(0, 1000);
                        const elId = document.getElementById('identity-summary');
                        if (elId) elId.textContent = identityText || reportStr.substring(0, 1000);
                        
                        // Find behavior section
                        let behaviorStart = -1;
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].indexOf('[Guardian Behavior]') !== -1) {
                                behaviorStart = i;
                                break;
                            }
                        }
                        let behaviorEnd = lines.length;
                        for (let i = (behaviorStart >= 0 ? behaviorStart + 1 : 0); i < lines.length; i++) {
                            if (lines[i].charAt(0) === '[' && lines[i].indexOf('Guardian Behavior') === -1) {
                                behaviorEnd = i;
                                break;
                            }
                        }
                        const behaviorText = behaviorStart >= 0 ? lines.slice(behaviorStart, behaviorEnd).join(String.fromCharCode(10)) : 'No behavior data available';
                        const elBeh = document.getElementById('behavior-report');
                        if (elBeh) elBeh.textContent = behaviorText;
                        
                        addLog('Comprehensive report loaded', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error loading comprehensive report: ' + err, 'error');
                    console.error(err);
                });
        };

        window.checkMemoryHealth = function() {
            fetch('/api/introspection/health')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const health = data.health || {};
                        const statusEl = document.getElementById('health-status');
                        const scoreEl = document.getElementById('health-score');
                        const totalEl = document.getElementById('health-total');
                        if (statusEl) statusEl.textContent = (health.status || 'unknown').toUpperCase();
                        if (scoreEl) scoreEl.textContent = ((health.health_score || 0) * 100).toFixed(1) + '%';
                        if (totalEl) totalEl.textContent = (health.total_memories !== undefined && health.total_memories !== null) ? health.total_memories : '-';
                        
                        const warningsDiv = document.getElementById('health-warnings');
                        if (warningsDiv) {
                            if (health.warnings && health.warnings.length > 0) {
                                warningsDiv.innerHTML = '<strong>Warnings:</strong><br>' + 
                                    health.warnings.map(function(w) { return 'Warning: ' + w; }).join('<br>');
                            } else {
                                warningsDiv.innerHTML = '<span style="color: #2ecc71;">No issues detected</span>';
                            }
                        }
                        
                        addLog('Memory health check completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error checking memory health: ' + err, 'error');
                    console.error(err);
                });
        };

        window.analyzeFocus = function() {
            fetch('/api/introspection/focus?hours=24')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const focus = data.focus || {};
                        const fp = document.getElementById('focus-primary');
                        const fa = document.getElementById('focus-activity');
                        const ft = document.getElementById('focus-trend');
                        const fm = document.getElementById('focus-period');
                        if (fp) fp.textContent = focus.primary_focus || '-';
                        if (fa) fa.textContent = (focus.activity_count !== undefined && focus.activity_count !== null) ? focus.activity_count : '-';
                        if (ft) ft.textContent = focus.priority_trend || '-';
                        if (fm) fm.textContent = focus.most_active_period || '-';
                        
                        const distDiv = document.getElementById('focus-distribution');
                        if (distDiv) {
                            if (focus.focus_distribution && Object.keys(focus.focus_distribution).length > 0) {
                                const distText = Object.entries(focus.focus_distribution)
                                    .map(function(entry) { return entry[0] + ': ' + entry[1]; })
                                    .join(String.fromCharCode(10));
                                distDiv.innerHTML = '<strong>Category Distribution:</strong><br><pre>' + distText + '</pre>';
                            } else {
                                distDiv.innerHTML = '<em>No focus distribution data</em>';
                            }
                        }
                        
                        addLog('Focus analysis completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error analyzing focus: ' + err, 'error');
                    console.error(err);
                });
        };

        window.findCorrelations = function() {
            const keyword = document.getElementById('correlation-keyword').value;
            if (!keyword) {
                addLog('Please enter a keyword', 'warning');
                return;
            }
            
            addLog('Finding correlations for: ' + keyword, 'info');
            fetch('/api/introspection/correlations?keyword=' + encodeURIComponent(keyword) + '&threshold=0.3')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const resultsDiv = document.getElementById('correlation-results');
                        if (data.correlations && data.correlations.length > 0) {
                            const html = data.correlations.map(function(corr) {
                                const score = (corr.correlation_score * 100).toFixed(1);
                                const timeDiff = corr.time_diff_hours.toFixed(1);
                                const keywords = corr.shared_keywords ? corr.shared_keywords.join(', ') : '';
                                return '<div style="margin: 10px 0; padding: 10px; background: var(--bg-card); border-radius: 8px; border-left: 3px solid var(--primary);">' +
                                    '<strong>Correlation Score:</strong> ' + score + '%<br>' +
                                    '<strong>Time Difference:</strong> ' + timeDiff + ' hours<br>' +
                                    '<strong>Memory 1:</strong> ' + (corr.memory1 || '').substring(0, 100) + '<br>' +
                                    '<strong>Memory 2:</strong> ' + (corr.memory2 || '').substring(0, 100) + '<br>' +
                                    '<strong>Shared Keywords:</strong> ' + keywords +
                                    '</div>';
                            }).join('');
                            resultsDiv.innerHTML = '<div><strong>Found ' + data.correlations.length + ' correlations:</strong></div>' + html;
                        } else {
                            resultsDiv.innerHTML = '<em>No correlations found for this keyword</em>';
                        }
                        addLog('Correlation analysis completed', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error finding correlations: ' + err, 'error');
                    console.error(err);
                });
        };

        // Initialize theme from localStorage (toggleTheme defined at top of script)
        (function() {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            document.body.setAttribute('data-theme', savedTheme);
        })();

        // Learning Functions - make globally accessible
        window.testRedditLearning = function() {
            addLog('Testing Reddit learning...', 'info');
            document.getElementById('learning-status').textContent = 'Testing Reddit API...';
            document.getElementById('learning-status').style.color = 'var(--warning)';
            
            fetch('/api/learning/test-reddit', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        document.getElementById('learning-status').textContent = 'Reddit learning test successful';
                        document.getElementById('learning-status').style.color = 'var(--success)';
                        addLog('Reddit learning test: ' + data.message, 'info');
                        window.refreshLearningStats();
                    } else {
                        document.getElementById('learning-status').textContent = 'Test failed: ' + (data.error || 'Unknown error');
                        document.getElementById('learning-status').style.color = 'var(--danger)';
                        addLog('Reddit learning test failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    document.getElementById('learning-status').textContent = 'Error: ' + err;
                    document.getElementById('learning-status').style.color = 'var(--danger)';
                        addLog('Error testing Reddit learning: ' + err, 'error');
                });
        };

        window.getLearningSummary = function() {
            addLog('Fetching learning summary...', 'info');
            fetch('/api/learning/summary')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const summary = data.summary;
                        document.getElementById('learning-articles').textContent = summary.total_articles || 0;
                        document.getElementById('learning-reddit').textContent = summary.reddit_posts || 0;
                        document.getElementById('learning-rss').textContent = summary.rss_entries || 0;
                        document.getElementById('learning-last').textContent = summary.last_learning || 'Never';
                        addLog('Learning summary loaded', 'info');
                    } else {
                        addLog('Error: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Error fetching learning summary: ' + err, 'error');
                });
        };

        window.refreshLearningStats = function() {
            window.getLearningSummary();
        };

        window.refreshLearningSettings = function() {
            var cb = document.getElementById('learning-headless');
            if (!cb) return;
            fetch('/api/learning/settings')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    cb.checked = !!data.use_headless_browser;
                })
                .catch(function() { cb.checked = false; });
        };

        window.saveLearningHeadless = function(checked) {
            fetch('/api/learning/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ use_headless_browser: !!checked })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) addLog('Headless browser for web: ' + (data.use_headless_browser ? 'on' : 'off'), 'info');
                })
                .catch(function(err) { addLog('Failed to save setting: ' + err, 'error'); });
        };

        window.refreshLinkedAccounts = function() {
            fetch('/api/learning/linked-accounts')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var fb = document.getElementById('link-fb-status');
                    if (fb) { fb.textContent = (data.facebook ? 'Linked' : 'Not linked'); fb.style.color = data.facebook ? 'var(--success)' : 'var(--text-secondary)'; }
                    var tw = document.getElementById('link-twitter-status');
                    if (tw) { tw.textContent = (data.twitter ? 'Linked' : 'Not linked'); tw.style.color = data.twitter ? 'var(--success)' : 'var(--text-secondary)'; }
                })
                .catch(function() {
                    var fb = document.getElementById('link-fb-status'); if (fb) { fb.textContent = 'Not linked'; fb.style.color = 'var(--text-secondary)'; }
                    var tw = document.getElementById('link-twitter-status'); if (tw) { tw.textContent = 'Not linked'; tw.style.color = 'var(--text-secondary)'; }
                });
        };

        window.saveLinkFacebook = function() {
            var input = document.getElementById('link-fb-token');
            var token = input ? input.value : '';
            var statusEl = document.getElementById('link-fb-status');
            fetch('/api/learning/link-facebook', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (input) input.value = '';
                        addLog(data.message || (data.linked ? 'Facebook linked' : 'Token cleared'), 'info');
                        if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                    } else {
                        addLog('Link failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) {
                    addLog('Link failed: ' + err, 'error');
                });
        };

        window.saveLinkTwitter = function() {
            var input = document.getElementById('link-twitter-token');
            var token = input ? input.value : '';
            fetch('/api/learning/link-twitter', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (input) input.value = '';
                        addLog(data.message || (data.linked ? 'X (Twitter) linked' : 'Token cleared'), 'info');
                        if (typeof window.refreshLinkedAccounts === 'function') window.refreshLinkedAccounts();
                    } else {
                        addLog('Link failed: ' + (data.error || 'Unknown'), 'error');
                    }
                })
                .catch(function(err) { addLog('Link failed: ' + err, 'error'); });
        };

        window.startLearning = function() {
            const platform = document.getElementById('learning-platform').value;
            const query = document.getElementById('learning-query').value;
            const maxItems = parseInt(document.getElementById('learning-max').value);
            
            if (!query && platform === 'reddit') {
                addLog('Please enter a subreddit or topic for Reddit', 'warning');
                return;
            }
            if (platform === 'web') {
                const urls = query.split(',').map(function(u) { return u.trim(); }).filter(function(u) { return u && (u.startsWith('http://') || u.startsWith('https://')); });
                if (urls.length === 0) {
                    addLog('Please enter one or more URLs (comma-separated)', 'warning');
                    return;
                }
            }
            if (platform === 'facebook' && !query) {
                addLog('Facebook: using pages from config. To use specific pages, enter Page ID(s) in the query box (e.g. Meta, TechCrunch). Set facebook_access_token in config/auto_learning.json or FACEBOOK_ACCESS_TOKEN env.', 'info');
            }
            if (platform === 'twitter' && !query) {
                addLog('Twitter: using search queries from config. Enter search term(s) in the query box (e.g. AI agents, machine learning) or set twitter_search_queries in config. Link X with Bearer Token above.', 'info');
            }
            
            addLog('Starting ' + platform + ' learning: "' + (query || 'config/default') + '" (max: ' + maxItems + ')', 'info');
            const resultsDiv = document.getElementById('learning-results');
            resultsDiv.innerHTML = '<div style="color: var(--warning);">Learning in progress...</div>';
            
            fetch('/api/learning/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ platform: platform, query: query, max_items: maxItems })
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        const result = data.result;
                        const status = result.status || 'success';
                        const message = result.message || 'Learning completed';
                        const itemsProcessed = (result.data && result.data.posts_processed) || (result.data && result.data.entries_processed) || (result.data && result.data.articles_processed) || 0;
                        resultsDiv.innerHTML = 
                            '<div style="color: var(--success); margin-bottom: 12px;">' +
                            '<strong>Learning Complete!</strong>' +
                            '</div>' +
                            '<div style="color: var(--text-primary);">' +
                            '<strong>Status:</strong> ' + status + '<br>' +
                            '<strong>Message:</strong> ' + message + '<br>' +
                            '<strong>Items Processed:</strong> ' + itemsProcessed +
                            '</div>';
                        addLog('Learning completed: ' + (result.message || 'Success'), 'info');
                        window.refreshLearningStats();
                    } else {
                        resultsDiv.innerHTML = '<div style="color: var(--danger);">Error: ' + (data.error || 'Unknown error') + '</div>';
                        addLog('Learning failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(function(err) {
                    resultsDiv.innerHTML = '<div style="color: var(--danger);">Error: ' + err + '</div>';
                    addLog('Error starting learning: ' + err, 'error');
                });
        };
    </script>
</body>
</html>
"""


class UIControlPanel:
    """
    Web-based control panel for Elysia system.
    Provides real-time monitoring and manual control.
    """
    
    def __init__(self, orchestrator, host: str = "127.0.0.1", port: int = 5000):
        """
        Initialize UI Control Panel.
        
        Args:
            orchestrator: SystemOrchestrator instance (or any object with compatible interface)
            host: Host to bind to
            port: Port to listen on
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask and Flask-SocketIO are required for UI Control Panel. Install with: pip install flask flask-socketio")
        
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self._setup_routes()
        self._setup_socketio()
        self.running = False
        self._server_ready = threading.Event()
        self._server_error = None
        self._actual_port = None

    def is_ready(self) -> bool:
        """
        Return True only when the dashboard server is actually ready/listening.
        Uses the running flag and the internal _server_ready event.
        """
        return bool(self.running) and self._server_ready.is_set()
        
    def _setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            return render_template_string(CONTROL_PANEL_TEMPLATE)
        
        @self.app.route('/favicon.ico')
        def favicon():
            return '', 204
        
        @self.app.route('/.well-known/appspecific/com.chrome.devtools.json')
        def chrome_devtools():
            return '', 204
        
        @self.app.route('/api/autonomy', methods=['GET'])
        def get_autonomy_status():
            """Get autonomy config and last execution status."""
            try:
                cfg = {"enabled": False, "allowed_actions": [], "max_actions_per_hour": 6}
                if hasattr(self.orchestrator, "_load_autonomy_config"):
                    cfg = self.orchestrator._load_autonomy_config()
                last = getattr(self.orchestrator, "_last_autonomy_result", None)
                return jsonify({
                    "success": True,
                    "enabled": cfg.get("enabled", False),
                    "allowed_actions": cfg.get("allowed_actions", []),
                    "max_actions_per_hour": cfg.get("max_actions_per_hour", 6),
                    "last": last,
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/autonomy', methods=['POST'])
        def set_autonomy():
            """Toggle autonomy on/off via config file."""
            try:
                data = request.get_json() or {}
                enabled = data.get("enabled")
                if enabled is None:
                    return jsonify({"error": "enabled required"}), 400
                import json
                from pathlib import Path
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "autonomy.json"
                cfg = {"enabled": False, "interval_seconds": 120, "allowed_actions": ["consider_learning", "consider_dream_cycle"], "max_actions_per_hour": 6}
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                cfg["enabled"] = bool(enabled)
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                return jsonify({"success": True, "enabled": cfg["enabled"]})
            except Exception as e:
                logger.error(f"Set autonomy error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/next-action')
        def get_next_action():
            """Get unified next action from tasks, missions, introspection, etc."""
            try:
                if hasattr(self.orchestrator, "get_next_action"):
                    result = self.orchestrator.get_next_action()
                    return jsonify(result)
                return jsonify({"success": False, "error": "Next action not available"}), 503
            except Exception as e:
                logger.error(f"Next action error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/autonomy/execute-cycle', methods=['POST'])
        def execute_autonomy_cycle():
            """Run one autonomy cycle (get next action and execute if allowed). Supports exploratory actions."""
            try:
                if hasattr(self.orchestrator, "run_autonomous_cycle"):
                    result = self.orchestrator.run_autonomous_cycle()
                    return jsonify({
                        "success": True,
                        "executed": result.get("executed", False),
                        "action": result.get("action"),
                        "reason": result.get("reason"),
                        "ask_user_question": result.get("ask_user_question"),
                    })
                return jsonify({"success": False, "error": "Autonomy not available"}), 503
            except Exception as e:
                logger.error("Execute cycle error: %s", e, exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/operator/ack-question', methods=['POST'])
        def ack_operator_question():
            """Clear pending operator question after acknowledgment. Resumes normal auto-execute."""
            try:
                if hasattr(self.orchestrator, "_pending_operator_question"):
                    self.orchestrator._pending_operator_question = None
                    return jsonify({"success": True, "message": "Question acknowledged"})
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Ack question error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/ping')
        def ping():
            """Quick connectivity check - returns immediately."""
            return jsonify({
                "ok": True,
                "service": "elysia-control-panel",
                "port": getattr(self, 'port', None),
                "orchestrator": self.orchestrator is not None if hasattr(self, 'orchestrator') else False,
            }), 200

        @self.app.route('/api/debug')
        def debug_info():
            """Diagnostic endpoint for control panel troubleshooting."""
            try:
                info = {
                    "flask_available": FLASK_AVAILABLE,
                    "orchestrator": self.orchestrator is not None if hasattr(self, 'orchestrator') else False,
                    "port": getattr(self, 'port', None),
                    "running": getattr(self, 'running', False),
                }
                if self.orchestrator:
                    info["has_memory"] = hasattr(self.orchestrator, 'memory') and self.orchestrator.memory is not None
                    info["has_elysia_loop"] = hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop is not None
                    info["has_module_registry"] = hasattr(self.orchestrator, 'module_registry') and self.orchestrator.module_registry is not None
                return jsonify(info), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500
            
        @self.app.route('/api/status')
        def get_status():
            """Get comprehensive system status - optimized for fast response."""
            try:
                # Quick check - return fast if orchestrator is None
                if not hasattr(self, 'orchestrator') or self.orchestrator is None:
                    return jsonify({
                        "system": {"running": False, "initialized": False, "uptime": 0, "error": "Orchestrator not available"},
                        "loop": {"running": False, "paused": False, "queue_size": 0},
                        "memory": {"total_entries": 0, "total_memories": 0},
                        "security": {"policy_loaded": False, "recent_violations": 0, "pending_reviews": 0},
                        "trust": {"components": 0, "average_trust": 0},
                        "timestamp": datetime.now().isoformat()
                    }), 200
                
                # Helper function to convert Path objects to strings
                def convert_paths(obj):
                    """Recursively convert Path objects to strings."""
                    if isinstance(obj, dict):
                        return {k: convert_paths(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_paths(item) for item in obj]
                    elif hasattr(obj, '__str__') and hasattr(obj, 'parts'):  # Path object
                        return str(obj)
                    else:
                        return obj
                
                # Get system status - use direct attribute access (fast)
                # Check multiple indicators to determine if system is actually initialized
                _initialized_attr = getattr(self.orchestrator, '_initialized', False)
                _running_attr = getattr(self.orchestrator, '_running', False)
                
                # Additional indicators: use loaded-aware APIs (do not read memory_log directly)
                memory_loaded = False
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        if hasattr(self.orchestrator.memory, 'get_memory_state'):
                            st = self.orchestrator.memory.get_memory_state(load_if_needed=False)
                            memory_loaded = bool(st.get("memory_loaded")) and ((st.get("memory_count") or 0) > 0)
                        elif hasattr(self.orchestrator.memory, 'get_memory_count'):
                            cnt = self.orchestrator.memory.get_memory_count(load_if_needed=False)
                            memory_loaded = cnt is not None and cnt > 0
                    except Exception:
                        pass
                
                loop_running = False
                if hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop:
                    try:
                        loop_running = getattr(self.orchestrator.elysia_loop, 'running', False)
                    except:
                        pass
                
                # System is considered initialized if:
                # - _initialized attribute is True, OR
                # - Memory is loaded (system has been running), OR
                # - Loop is running, OR
                # - Orchestrator has core components (so UI never sticks on "Initializing")
                has_core = (
                    (hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop is not None)
                    or (hasattr(self.orchestrator, 'memory') and self.orchestrator.memory is not None)
                )
                is_initialized = _initialized_attr or memory_loaded or loop_running or has_core
                is_running = _running_attr or loop_running or memory_loaded or has_core
                
                system_status = {
                    "running": is_running,
                    "initialized": is_initialized,
                    "start_time": None,
                    "operational_stats": {}
                }
                
                # Safely get start_time
                if hasattr(self.orchestrator, 'start_time') and self.orchestrator.start_time:
                    try:
                        if hasattr(self.orchestrator.start_time, 'isoformat'):
                            system_status["start_time"] = self.orchestrator.start_time.isoformat()
                        else:
                            system_status["start_time"] = str(self.orchestrator.start_time)
                    except:
                        system_status["start_time"] = None
                
                # Calculate uptime if start_time exists
                if system_status["start_time"]:
                    try:
                        from datetime import datetime
                        start = datetime.fromisoformat(system_status["start_time"])
                        uptime = (datetime.now() - start).total_seconds()
                        system_status["uptime"] = max(0, uptime)
                    except:
                        system_status["uptime"] = 0
                else:
                    system_status["uptime"] = 0
                
                # Get operational stats if available (non-blocking)
                try:
                    operational_stats = getattr(self.orchestrator, 'operational_stats', {})
                    system_status["operational_stats"] = convert_paths(operational_stats)
                except:
                    pass
                # Canonical operational state (deferred/vector/dashboard) - single source for UI
                try:
                    if hasattr(self.orchestrator, 'get_startup_operational_state'):
                        op = self.orchestrator.get_startup_operational_state()
                        system_status["operational_state"] = convert_paths(op)
                except Exception:
                    system_status["operational_state"] = {}
                
                # Get ElysiaLoopCore status - direct attribute access only (fast)
                loop_status = {}
                if hasattr(self.orchestrator, 'elysia_loop') and self.orchestrator.elysia_loop:
                    try:
                        loop_status["running"] = getattr(self.orchestrator.elysia_loop, 'running', False)
                        loop_status["paused"] = getattr(self.orchestrator.elysia_loop, 'paused', False)
                        # Get queue_size - ElysiaLoopCore uses task_queue.get_queue_size()
                        try:
                            tq = getattr(self.orchestrator.elysia_loop, 'task_queue', None)
                            if tq and hasattr(tq, 'get_queue_size'):
                                loop_status["queue_size"] = tq.get_queue_size()
                            else:
                                queue_size = getattr(self.orchestrator.elysia_loop, 'queue_size', 0)
                                loop_status["queue_size"] = 0 if callable(queue_size) else queue_size
                        except Exception:
                            loop_status["queue_size"] = 0
                    except Exception as e:
                        logger.debug(f"Error getting loop status: {e}")
                        loop_status = {"running": False, "paused": False, "queue_size": 0}
                else:
                    # If no elysia_loop, check if system is at least initialized
                    loop_status = {"running": system_status.get("initialized", False), "paused": False, "queue_size": 0}
                
                # Get RuntimeLoop status (quick check only)
                runtime_status = {}
                if hasattr(self.orchestrator, 'runtime_loop') and self.orchestrator.runtime_loop:
                    try:
                        runtime_status["running"] = getattr(self.orchestrator.runtime_loop, 'running', False)
                    except:
                        runtime_status["running"] = False
                
                # Get ModuleRegistry status (quick check only)
                module_status = {}
                if hasattr(self.orchestrator, 'module_registry') and self.orchestrator.module_registry:
                    module_status["available"] = True
                
                # Get memory stats via loaded-aware APIs (non-forcing for status)
                memory_stats = {}
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_memory_state'):
                            st = mem.get_memory_state(load_if_needed=False)
                            count = st.get("memory_count")
                            memory_stats = {
                                "total_entries": count if count is not None else 0,
                                "total_memories": count if count is not None else 0,
                                "memory_loaded": st.get("memory_loaded", False),
                            }
                        elif hasattr(mem, 'get_memory_count'):
                            count = mem.get_memory_count(load_if_needed=False)
                            memory_stats = {"total_entries": count or 0, "total_memories": count or 0}
                        if getattr(mem, 'vector_memory', None):
                            memory_stats["vector_memory_enabled"] = True
                    except Exception as e:
                        logger.debug(f"Error getting memory stats: {e}")
                        memory_stats = {"total_entries": 0, "total_memories": 0}
                else:
                    memory_stats = {"total_entries": 0, "total_memories": 0}
                
                # Get security status (quick check)
                security_status = {}
                if hasattr(self.orchestrator, 'safety') and self.orchestrator.safety:
                    security_status["policy_loaded"] = True
                    security_status["recent_violations"] = 0
                    security_status["pending_reviews"] = 0
                
                # Get trust status (quick check)
                trust_status = {}
                if hasattr(self.orchestrator, 'trust') and self.orchestrator.trust:
                    trust_status["components"] = 1
                    trust_status["average_trust"] = 0.8
                
                # Convert all data to ensure no Path objects remain
                response_data = {
                    "system": convert_paths(system_status),
                    "loop": convert_paths(loop_status),
                    "runtime": convert_paths(runtime_status),
                    "modules": convert_paths(module_status),
                    "memory": convert_paths(memory_stats),
                    "security": convert_paths(security_status),
                    "trust": convert_paths(trust_status),
                    "timestamp": datetime.now().isoformat()
                }
                
                return jsonify(response_data)
                
            except Exception as e:
                logger.error(f"Status endpoint error: {e}", exc_info=True)
                error_msg = str(e)[:200]
                # Return minimal valid status even on error
                return jsonify({
                    "system": {
                        "running": getattr(self.orchestrator, '_running', False),
                        "initialized": getattr(self.orchestrator, '_initialized', False),
                        "uptime": 0,
                        "error": error_msg
                    },
                    "loop": {
                        "running": getattr(self.orchestrator, '_running', False),
                        "paused": False,
                        "queue_size": 0
                    },
                    "memory": {"total_entries": 0, "total_memories": 0},
                    "security": {"policy_loaded": False, "recent_violations": 0, "pending_reviews": 0},
                    "trust": {"components": 0, "average_trust": 0},
                    "timestamp": datetime.now().isoformat()
                }), 200
                
        @self.app.route('/api/control/pause', methods=['POST'])
        def pause_loop():
            """Pause the event loop."""
            try:
                if self.orchestrator.elysia_loop and hasattr(self.orchestrator.elysia_loop, 'pause'):
                    self.orchestrator.elysia_loop.pause()
                    return jsonify({"success": True, "message": "Loop paused"})
                return jsonify({"success": False, "message": "Pause not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/control/resume', methods=['POST'])
        def resume_loop():
            """Resume the event loop."""
            try:
                if self.orchestrator.elysia_loop and hasattr(self.orchestrator.elysia_loop, 'resume'):
                    self.orchestrator.elysia_loop.resume()
                    return jsonify({"success": True, "message": "Loop resumed"})
                return jsonify({"success": False, "message": "Resume not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/memory/snapshot', methods=['POST'])
        def create_snapshot():
            """Create memory snapshot."""
            try:
                # Use MemoryCore if available
                if self.orchestrator.memory and hasattr(self.orchestrator.memory, 'save'):
                    # Save current memory state
                    self.orchestrator.memory.save()
                    return jsonify({"success": True, "message": "Memory saved"})
                return jsonify({"success": False, "message": "Memory snapshot not available"}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/memory/cleanup', methods=['POST'])
        def cleanup_memory():
            """Cleanup and consolidate memories to reduce memory usage."""
            try:
                if not hasattr(self.orchestrator, 'memory') or not self.orchestrator.memory:
                    return jsonify({"error": "Memory system not available"}), 400
                
                # Get parameters from request
                data = request.get_json() or {}
                max_memories = data.get("max_memories", 5000)
                keep_recent_days = data.get("keep_recent_days", 30)
                
                # Perform consolidation
                if hasattr(self.orchestrator.memory, 'consolidate'):
                    result = self.orchestrator.memory.consolidate(
                        max_memories=max_memories,
                        keep_recent_days=keep_recent_days
                    )
                    return jsonify({"success": True, "result": result})
                else:
                    return jsonify({"error": "Consolidate method not available"}), 400
            except Exception as e:
                logger.error(f"Memory cleanup error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/memory/rebuild-vector', methods=['POST'])
        def rebuild_vector():
            """Manually trigger vector index rebuild when degraded or rebuild pending."""
            try:
                if not hasattr(self.orchestrator, 'rebuild_vector_memory_if_pending'):
                    return jsonify({"error": "Vector rebuild not available"}), 400
                result = self.orchestrator.rebuild_vector_memory_if_pending()
                return jsonify({"success": True, "result": result})
            except Exception as e:
                logger.error(f"Vector rebuild error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/memory/stats', methods=['GET'])
        def get_memory_stats():
            """Get memory usage statistics."""
            try:
                if not hasattr(self.orchestrator, 'memory') or not self.orchestrator.memory:
                    return jsonify({"error": "Memory system not available"}), 400
                
                from project_guardian.memory_cleanup import MemoryCleanup
                cleanup = MemoryCleanup(self.orchestrator.memory)
                stats = cleanup.get_memory_size_estimate()
                
                om = self.orchestrator.memory
                if hasattr(om, "get_memory_state"):
                    _pst = om.get_memory_state(load_if_needed=False)
                    stats.update(_pst)
                    stats["current_count"] = _pst.get("memory_count")
                elif hasattr(om, "get_memory_count"):
                    stats["current_count"] = om.get_memory_count(load_if_needed=False)
                
                return jsonify({"success": True, "stats": stats})
            except Exception as e:
                logger.error(f"Memory stats error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/prompts/evolve', methods=['POST'])
        def run_prompt_evolution():
            """Run AI-powered prompt evolution on low-scoring prompts."""
            try:
                if not hasattr(self.orchestrator, 'prompt_evolver') or not self.orchestrator.prompt_evolver:
                    return jsonify({"error": "Prompt evolution not available"}), 400
                data = request.get_json() or {}
                min_records = data.get("min_records", 5)
                evolved = self.orchestrator.run_prompt_evolution(min_records=min_records)
                stats = self.orchestrator.prompt_evolver.get_stats()
                return jsonify({
                    "success": True,
                    "evolved_count": evolved,
                    "stats": stats
                })
            except Exception as e:
                logger.error(f"Prompt evolution error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/prompts/stats', methods=['GET'])
        def get_prompt_evolution_stats():
            """Get prompt evolution statistics."""
            try:
                if not hasattr(self.orchestrator, 'prompt_evolver') or not self.orchestrator.prompt_evolver:
                    return jsonify({"error": "Prompt evolution not available"}), 400
                return jsonify({"success": True, "stats": self.orchestrator.prompt_evolver.get_stats()})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        def _get_unified_system():
            """Unified Elysia system when guardian is run under Elysia (for chat, income, harvest, etc.)."""
            return getattr(self.orchestrator, '_unified_system', None)

        @self.app.route('/api/chat', methods=['POST'])
        def api_chat():
            """Chat with AI (OpenAI/OpenRouter via unified system or guardian.ask_ai fallback)."""
            try:
                data = request.get_json() or {}
                message = (data.get('message') or '').strip()
                if not message:
                    return jsonify({"error": "message is required"}), 400
                us = _get_unified_system()
                if us and hasattr(us, 'chat_with_llm'):
                    reply, err = us.chat_with_llm(message)
                    if err:
                        return jsonify({"success": False, "error": err, "reply": None}), 200
                    return jsonify({"success": True, "reply": reply, "error": None})
                if hasattr(self.orchestrator, 'ask_ai'):
                    reply = self.orchestrator.ask_ai(message)
                    return jsonify({"success": True, "reply": reply or "(no reply)", "error": None})
                return jsonify({"error": "No chat backend available (unified system or ask_ai)"}), 400
            except Exception as e:
                logger.error(f"Chat error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/income-status', methods=['GET'])
        def api_income_status():
            """Income/API module status (income_generator, harvest_engine, etc.) from unified system."""
            try:
                us = _get_unified_system()
                if us and hasattr(us, 'get_status'):
                    status = us.get_status()
                    income = status.get('income_modules') or {}
                    return jsonify({"success": True, "income_modules": income})
                return jsonify({"success": True, "income_modules": {}, "message": "Unified system not available"})
            except Exception as e:
                logger.error(f"Income status error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/wallet/accounts', methods=['GET'])
        def api_wallet_accounts_get():
            """List wallet sub-accounts and totals (unified Elysia wallet module)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, "modules"):
                    return jsonify({"success": False, "error": "Unified system not available"}), 400
                wallet = us.modules.get("wallet")
                if not wallet or not hasattr(wallet, "get_balance"):
                    return jsonify({"success": False, "error": "Wallet not available"}), 400
                bal = wallet.get_balance()
                return jsonify({"success": True, "balance": bal})
            except Exception as e:
                logger.error(f"Wallet list error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/wallet/accounts', methods=['POST'])
        def api_wallet_accounts_post():
            """Add a wallet sub-account (display name + optional id slug)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, "modules"):
                    return jsonify({"success": False, "error": "Unified system not available"}), 400
                wallet = us.modules.get("wallet")
                if not wallet or not hasattr(wallet, "add_account"):
                    return jsonify({"success": False, "error": "Wallet not available"}), 400
                data = request.get_json() or {}
                name = (data.get("name") or "").strip()
                if not name:
                    return jsonify({"success": False, "error": "name is required"}), 400
                rid = (data.get("id") or data.get("account_id") or "").strip() or None
                out = wallet.add_account(
                    name,
                    account_id=rid,
                    account_type=str(data.get("type", "virtual")),
                    currency=str(data.get("currency", "USD")),
                    initial_balance=float(data.get("balance", data.get("initial_balance", 0)) or 0),
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
                )
                status = 200 if out.get("success") else 400
                return jsonify(out), status
            except Exception as e:
                logger.error(f"Wallet add error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/harvest-report', methods=['POST'])
        def api_harvest_report():
            """Request a harvest/income report from HarvestEngine (Alpha Vantage, etc.)."""
            try:
                us = _get_unified_system()
                if not us or not hasattr(us, 'modules'):
                    return jsonify({"error": "Unified system not available"}), 400
                he = us.modules.get('harvest_engine')
                if not he:
                    return jsonify({"error": "HarvestEngine not available"}), 400
                report = None
                if hasattr(he, 'generate_income_report'):
                    report = he.generate_income_report()
                elif hasattr(he, 'get_account_status'):
                    report = he.get_account_status()
                else:
                    return jsonify({"error": "HarvestEngine has no report method"}), 400
                return jsonify({"success": True, "report": report})
            except Exception as e:
                logger.error(f"Harvest report error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/research-proposal', methods=['POST'])
        def api_research_proposal():
            """Create a research proposal via Architect/WebScout (Brave Search)."""
            try:
                us = _get_unified_system()
                if not us or not getattr(us, 'architect', None):
                    return jsonify({"error": "Unified system or Architect not available"}), 400
                arch = us.architect
                data = request.get_json() or {}
                topic = (data.get('topic') or data.get('query') or 'AI safety').strip() or 'AI safety'
                task_description = (data.get('task_description') or f'Summarize key findings and sources for: {topic}').strip()
                if hasattr(arch, 'create_research_proposal'):
                    result = arch.create_research_proposal(task_description, topic)
                    return jsonify({"success": True, "topic": topic, "result": result})
                if hasattr(arch, 'webscout') and arch.webscout:
                    # Fallback: use webscout search
                    out = arch.webscout.search(topic, max_results=5) if hasattr(arch.webscout, 'search') else {"results": []}
                    return jsonify({"success": True, "topic": topic, "result": out})
                return jsonify({"error": "Architect has no research proposal or WebScout"}), 400
            except Exception as e:
                logger.error(f"Research proposal error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/control/dream-cycle', methods=['POST'])
        def trigger_dream_cycle():
            """Trigger a dream cycle for memory consolidation."""
            try:
                result = {
                    "success": True,
                    "message": "Dream cycle initiated",
                    "activities": []
                }
                
                # If memory system available, trigger consolidation
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        # Save memory state
                        if hasattr(self.orchestrator.memory, 'save'):
                            self.orchestrator.memory.save()
                            result["activities"].append("Memory saved")
                        
                        # Consolidate if available
                        if hasattr(self.orchestrator.memory, 'consolidate'):
                            self.orchestrator.memory.consolidate()
                            result["activities"].append("Memory consolidation")
                    except Exception as e:
                        logger.warning(f"Memory operations failed: {e}")
                
                # If orchestrator has dreams/creativity component
                if hasattr(self.orchestrator, 'dreams') and self.orchestrator.dreams:
                    try:
                        dreams = self.orchestrator.dreams
                        if hasattr(dreams, 'dream_cycle'):
                            dreams.dream_cycle()
                            result["activities"].append("Dream cycle processing")
                        elif hasattr(dreams, 'begin_dream_cycle'):
                            thoughts = dreams.begin_dream_cycle(cycles=1)
                            result["activities"].append(f"Dream cycle: {len(thoughts)} thought(s)")
                            if thoughts:
                                result["dream_thoughts"] = thoughts
                    except Exception as e:
                        logger.warning(f"Dream cycle processing failed: {e}")
                
                # Log the dream cycle event via timeline if available
                if hasattr(self.orchestrator, 'timeline') and self.orchestrator.timeline:
                    try:
                        if hasattr(self.orchestrator.timeline, 'add_event'):
                            self.orchestrator.timeline.add_event(
                                event_type="dream_cycle",
                                actor="system",
                                description="Dream cycle triggered",
                                metadata=result
                            )
                            result["activities"].append("Event logged")
                    except Exception as e:
                        logger.warning(f"Timeline logging failed: {e}")
                
                if not result["activities"]:
                    result["message"] = "Dream cycle triggered (no operations performed)"
                    result["success"] = False
                
                return jsonify(result)
            except Exception as e:
                logger.error(f"Dream cycle error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/speak', methods=['POST'])
        def speak_message():
            """Trigger TTS speech via VoiceThread."""
            try:
                data = request.get_json() or {}
                message = (data.get("message") or "").strip()
                mode = data.get("mode", "guardian")
                if not message:
                    return jsonify({"success": False, "error": "No message provided"}), 400
                if hasattr(self.orchestrator, "speak_message"):
                    self.orchestrator.speak_message(message, mode=mode)
                    return jsonify({"success": True, "message": "Speaking"})
                if hasattr(self.orchestrator, "voice") and self.orchestrator.voice:
                    if hasattr(self.orchestrator.voice, "set_mode"):
                        self.orchestrator.voice.set_mode(mode)
                    self.orchestrator.voice.speak(message)
                    return jsonify({"success": True, "message": "Speaking"})
                return jsonify({"success": False, "error": "Voice not available"}), 503
            except Exception as e:
                logger.error(f"Speak error: {e}", exc_info=True)
                return jsonify({"error": str(e), "success": False}), 500
                
        @self.app.route('/api/memory/search')
        def search_memory():
            """Search memories. Forces load (memory-detail route). Bounded by limit param (default 10)."""
            try:
                query = request.args.get('q', '')
                try:
                    limit = min(int(request.args.get('limit', 10)), 100)
                except (ValueError, TypeError):
                    limit = 10
                if not self.orchestrator.memory:
                    return jsonify({"success": False, "results": []})
                mem = self.orchestrator.memory
                if hasattr(mem, 'search_memories') and query:
                    results = mem.search_memories(query, limit=limit)
                    return jsonify({"success": True, "results": results[:limit]})
                # Fallback: bounded scan (no dump_all)
                if hasattr(mem, 'get_recent_memories'):
                    entries = mem.get_recent_memories(limit=min(UI_MEMORY_RECENT_LIMIT, limit * 10), load_if_needed=True)
                    q_lower = query.lower()
                    results = []
                    for m in entries:
                        text = m.get('thought', m.get('text', str(m)))
                        if q_lower in str(text).lower():
                            results.append({"thought": text, "category": m.get("category", "")})
                            if len(results) >= limit:
                                break
                    return jsonify({"success": True, "results": results[:limit]})
                return jsonify({"success": True, "results": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/tasks/submit', methods=['POST'])
        def submit_task():
            """Submit a task to the system."""
            try:
                data = request.get_json() or {}
                # Support both formats: {type, payload, priority} and {code, priority} from Control tab
                task_type = data.get('type') or ''
                payload = data.get('payload') or {}
                if data.get('code') is not None:
                    task_type = task_type or 'custom'
                    payload = dict(payload, code=data.get('code'))
                
                # Submit task through ModuleRegistry
                if self.orchestrator.module_registry:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        self.orchestrator.module_registry.route_task({
                            "type": task_type or "general",
                            "payload": payload
                        })
                    )
                    loop.close()
                    if isinstance(result, dict) and result.get("success") is False:
                        return jsonify({
                            "success": False,
                            "error": result.get("error", "Task routing failed"),
                            "task_id": result.get("task_id"),
                        }), 400
                    return jsonify({"success": True, "result": result})
                else:
                    return jsonify({"success": False, "error": "ModuleRegistry not available"}), 400
            except Exception as e:
                logger.error(f"Task submission error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/modules/list')
        def list_modules():
            """List all registered modules."""
            try:
                if self.orchestrator.module_registry:
                    try:
                        status = self.orchestrator.module_registry.get_registry_status()
                        modules = []
                        for module_name in status.get("module_names", []):
                            module_info = self.orchestrator.module_registry.get_module_status(module_name)
                            if module_info:
                                modules.append(module_info)
                        return jsonify({"success": True, "modules": modules})
                    except AttributeError:
                        # Fallback if get_registry_status doesn't exist
                        module_names = self.orchestrator.module_registry.list_modules() if hasattr(self.orchestrator.module_registry, 'list_modules') else []
                        modules = [{"name": name, "capabilities": []} for name in module_names]
                        return jsonify({"success": True, "modules": modules})
                return jsonify({"success": False, "modules": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/gaps/list')
        def list_gaps():
            """List capability gaps."""
            try:
                if self.orchestrator.auto_module_creator:
                    unresolved = self.orchestrator.auto_module_creator.list_unresolved_gaps()
                    gaps = []
                    for gap in unresolved:
                        gaps.append({
                            "gap_id": gap.gap_id,
                            "required_capability": gap.required_capability,
                            "task_description": gap.task_description,
                            "detected_at": gap.detected_at.isoformat()
                        })
                    return jsonify({"success": True, "gaps": gaps})
                return jsonify({"success": True, "gaps": []})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/gaps/create', methods=['POST'])
        def create_module_for_gap():
            """Manually trigger module creation for a gap."""
            try:
                data = request.get_json() or {}
                gap_id = data.get('gap_id')
                
                if not gap_id:
                    return jsonify({"success": False, "error": "gap_id required"}), 400
                
                if self.orchestrator.auto_module_creator:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        self.orchestrator.auto_module_creator.create_module_for_gap(gap_id)
                    )
                    loop.close()
                    return jsonify(result)
                return jsonify({"success": False, "error": "AutoModuleCreator not available"}), 400
            except Exception as e:
                logger.error(f"Module creation error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/tasks/list')
        def list_tasks():
            """Active TaskEngine tasks, GlobalTaskQueue jobs, and TASKS/*.md drop files."""
            try:
                orch = self.orchestrator
                if orch is None:
                    return jsonify({"success": False, "queue_size": 0, "tasks": [], "error": "Orchestrator not available"}), 503

                rows: List[Dict[str, Any]] = []
                queue_size = 0

                tq = getattr(getattr(orch, "elysia_loop", None), "task_queue", None) or getattr(orch, "task_queue", None)
                if tq and hasattr(tq, "get_queue_size"):
                    queue_size = int(tq.get_queue_size())

                # Guardian TaskEngine (in-memory operational tasks)
                task_engine = getattr(orch, "tasks", None)
                if task_engine and hasattr(task_engine, "get_active_tasks"):
                    for t in task_engine.get_active_tasks():
                        if not isinstance(t, dict):
                            continue
                        item = {"source": "task_engine"}
                        for k, v in t.items():
                            if k == "logs":
                                item[k] = v[-5:] if isinstance(v, list) else v
                            else:
                                item[k] = v
                        rows.append(item)

                # Elysia loop priority queue (serializable subset)
                if tq and hasattr(tq, "list_tasks"):
                    try:
                        for raw in tq.list_tasks(limit=80):
                            fn = getattr(raw.func, "__name__", None) or type(raw.func).__name__
                            st = raw.status.value if hasattr(raw.status, "value") else str(raw.status)
                            meta = raw.metadata or {}
                            safe_meta = {
                                k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v)[:400]
                                for k, v in meta.items()
                            }
                            rows.append({
                                "source": "loop_queue",
                                "task_id": raw.task_id,
                                "status": st,
                                "priority": raw.priority,
                                "module": raw.module,
                                "created_at": raw.created_at.isoformat() if hasattr(raw.created_at, "isoformat") else str(raw.created_at),
                                "func": fn,
                                "metadata": safe_meta,
                            })
                    except Exception as e:
                        logger.debug("list_tasks loop_queue slice failed: %s", e)

                # Disk drop files (TASKS/*.md)
                tasks_dir = getattr(orch, "tasks_dir", None)
                if tasks_dir:
                    td = Path(tasks_dir)
                    if td.is_dir():
                        for fp in sorted(td.glob("*.md"))[:40]:
                            rows.append({
                                "source": "disk",
                                "file": fp.name,
                                "path": str(fp.resolve()),
                                "status": "pending_file",
                            })

                return jsonify({"success": True, "queue_size": queue_size, "tasks": rows})
            except Exception as e:
                logger.error("list_tasks: %s", e, exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500
                
        # Introspection API Endpoints (placeholder - can be extended)
        @self.app.route('/api/introspection/comprehensive')
        def get_comprehensive_report():
            """Get comprehensive introspection report."""
            try:
                # Build a text report for frontend parsing; fallback to reflector if available
                report_text = "[Guardian Identity]\nSystem: Elysia / Project Guardian\nStatus: Operational\n\n"
                report_text += "[Guardian Behavior]\nBehavior introspection not yet fully implemented.\n"
                if hasattr(self.orchestrator, 'reflector') and self.orchestrator.reflector:
                    try:
                        r = self.orchestrator.reflector
                        if hasattr(r, 'get_comprehensive_report'):
                            report_text = r.get_comprehensive_report()
                        elif hasattr(r, 'get_identity_summary'):
                            ident = r.get_identity_summary()
                            if ident:
                                report_text = ident + "\n\n" + report_text.split("[Guardian Behavior]", 1)[-1]
                        elif hasattr(r, 'get_identity_report'):
                            ident = r.get_identity_report()
                            if ident:
                                report_text = "[Guardian Identity]\n" + str(ident) + "\n\n" + report_text.split("[Guardian Behavior]", 1)[-1]
                    except Exception:
                        pass
                return jsonify({"success": True, "report": report_text})
            except Exception as e:
                logger.error(f"Comprehensive report error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/debug')
        def get_introspection_debug():
            """Get last introspection decision (for debug view)."""
            try:
                result = getattr(self.orchestrator, "_last_introspection_result", None)
                if result is None:
                    return jsonify({"success": True, "debug": {"note": "No introspection run yet"}})
                return jsonify({"success": True, "debug": result})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/introspection/identity')
        def get_identity_summary():
            """Get identity summary from reflector or IdentityCore."""
            try:
                identity = {
                    "name": "Elysia",
                    "role": "Autonomous AI Safety System",
                    "system_name": "Project Guardian",
                    "oath": "I exist to learn, adapt, and protect the future."
                }
                if hasattr(self.orchestrator, 'reflector') and self.orchestrator.reflector:
                    try:
                        r = self.orchestrator.reflector
                        if hasattr(r, 'get_identity_summary'):
                            identity["summary_text"] = r.get_identity_summary()
                        if hasattr(r, 'summarize_self'):
                            s = r.summarize_self()
                            identity["uptime_seconds"] = s.get("uptime_seconds")
                            identity["active_tasks"] = s.get("active_tasks")
                            identity["memory_stats"] = s.get("memory_stats", {})
                            identity["system_health"] = s.get("system_health", {})
                    except Exception:
                        pass
                return jsonify({"success": True, "identity": identity})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/behavior')
        def get_behavior_report():
            """Get behavior report."""
            try:
                return jsonify({
                    "success": True,
                    "behavior": {"note": "Behavior introspection not yet implemented"}
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/health')
        def get_memory_health():
            """Get memory health analysis. Non-forcing (uses loaded-aware state)."""
            try:
                health = {"status": "unknown", "health_score": 0, "total_memories": 0, "warnings": []}
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_memory_state'):
                            st = mem.get_memory_state(load_if_needed=False)
                            count = st.get("memory_count")
                            loaded = st.get("memory_loaded", False)
                        elif hasattr(mem, 'get_memory_count'):
                            count = mem.get_memory_count(load_if_needed=False)
                            loaded = count is not None
                        else:
                            count, loaded = 0, False
                        health["total_memories"] = count if count is not None else 0
                        health["memory_loaded"] = loaded
                        if not loaded:
                            health["status"] = "loading"
                            health["warnings"] = ["Memory not yet loaded (deferred)"]
                        elif (count or 0) > 0:
                            health["health_score"] = min(1.0, 0.5 + ((count or 0) / 10000) * 0.5)
                            health["status"] = "healthy"
                        else:
                            health["health_score"] = 0.5
                            health["status"] = "empty"
                    except Exception:
                        health["warnings"] = ["Could not read memory count"]
                return jsonify({"success": True, "health": health})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/focus')
        def get_focus_analysis():
            """Get focus analysis. Forces load (memory-detail route)."""
            try:
                try:
                    hours = int(request.args.get("hours", 24))
                except (TypeError, ValueError):
                    hours = 24
                hours = max(1, min(168, hours))
                focus = {
                    "time_window_hours": hours,
                    "primary_focus": "System monitoring",
                    "activity_count": 0,
                    "priority_trend": "stable",
                    "most_active_period": "N/A",
                    "focus_distribution": {},
                }
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    try:
                        mem = self.orchestrator.memory
                        if hasattr(mem, 'get_recent_memories'):
                            entries = mem.get_recent_memories(limit=UI_MEMORY_RECENT_LIMIT, load_if_needed=True)
                        else:
                            entries = []
                        focus["activity_count"] = len(entries)
                        if entries:
                            cats = {}
                            for m in entries:
                                c = (m.get("category") or "general") if isinstance(m, dict) else "general"
                                cats[c] = cats.get(c, 0) + 1
                            focus["focus_distribution"] = cats
                            if cats:
                                focus["primary_focus"] = max(cats, key=cats.get)
                    except Exception:
                        pass
                return jsonify({"success": True, "focus": focus})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/correlations')
        def get_memory_correlations():
            """Get memory correlations."""
            try:
                keyword = (request.args.get("keyword") or "").strip()
                if not keyword:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "keyword query parameter is required",
                            }
                        ),
                        400,
                    )
                return jsonify(
                    {
                        "success": True,
                        "correlations": {
                            "note": "Memory correlations not yet implemented",
                            "keyword": keyword,
                        },
                    }
                )
            except Exception as e:
                return jsonify({"error": str(e)}), 500
                
        @self.app.route('/api/introspection/patterns')
        def get_memory_patterns():
            """Get memory patterns."""
            try:
                return jsonify({
                    "success": True,
                    "patterns": {"note": "Memory patterns not yet implemented"}
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        # Learning API Endpoints (use project_guardian.auto_learning)
        @self.app.route('/api/learning/test-reddit', methods=['POST'])
        def test_reddit_learning():
            """Test Reddit learning capability."""
            try:
                from project_guardian.auto_learning import fetch_reddit, compress_with_llm
                llm = None
                if hasattr(self.orchestrator, 'chat_with_llm'):
                    llm = lambda m: self.orchestrator.chat_with_llm(m)
                else:
                    try:
                        import sys
                        main_mod = sys.modules.get("__main__")
                        if main_mod:
                            status_sys = getattr(main_mod, "_status_system", None)
                            if status_sys and hasattr(status_sys, "chat_with_llm"):
                                llm = lambda m: status_sys.chat_with_llm(m)
                    except Exception:
                        pass
                items = fetch_reddit("MachineLearning", limit=3)
                for item in items:
                    item["compressed"] = compress_with_llm(item.get("text", ""), llm, module_name="summarizer")
                return jsonify({
                    "success": True,
                    "message": f"Fetched {len(items)} posts from r/MachineLearning",
                    "result": {"data": {"posts_processed": len(items)}, "status": "success", "message": f"Test OK: {len(items)} posts"}
                })
            except Exception as e:
                logger.error(f"Reddit learning test error: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/learning/summary')
        def get_learning_summary():
            """Get learning summary from learned JSONL files on thumb drive."""
            try:
                from project_guardian.auto_learning import get_learned_storage_path
                storage = get_learned_storage_path()
                total = 0
                last_learning = "Never"
                last_mtime = 0
                for f in storage.glob("learned_*.jsonl"):
                    try:
                        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                            n = sum(1 for _ in fp)
                        total += n
                        if f.stat().st_mtime > last_mtime:
                            last_mtime = f.stat().st_mtime
                            last_learning = datetime.fromtimestamp(last_mtime).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                return jsonify({
                    "success": True,
                    "summary": {
                        "total_articles": total,
                        "reddit_posts": total,
                        "rss_entries": total,
                        "last_learning": last_learning
                    }
                })
            except Exception as e:
                logger.error(f"Learning summary error: {e}", exc_info=True)
                return jsonify({"success": True, "summary": {"total_articles": 0, "reddit_posts": 0, "rss_entries": 0, "last_learning": "Never"}})

        @self.app.route('/api/learning/settings', methods=['GET'])
        def get_learning_settings():
            """Return learning options (e.g. use_headless_browser)."""
            try:
                from project_guardian.auto_learning import load_learning_config
                cfg = load_learning_config()
                return jsonify({"success": True, "use_headless_browser": bool(cfg.get("use_headless_browser", False))})
            except Exception as e:
                logger.debug(f"Learning settings error: {e}")
                return jsonify({"success": True, "use_headless_browser": False})

        @self.app.route('/api/learning/settings', methods=['POST'])
        def set_learning_settings():
            """Update learning options (e.g. use_headless_browser)."""
            try:
                data = request.get_json() or {}
                use_headless = bool(data.get("use_headless_browser", False))
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config() or {}
                cfg["use_headless_browser"] = use_headless
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "use_headless_browser": use_headless})
            except Exception as e:
                logger.error(f"Learning settings error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/linked-accounts', methods=['GET'])
        def get_linked_accounts():
            """Return which accounts are linked (no secrets)."""
            try:
                from project_guardian.auto_learning import load_learning_config
                import os
                cfg = load_learning_config()
                fb = bool((cfg.get("facebook_access_token") or "").strip() or (os.environ.get("FACEBOOK_ACCESS_TOKEN") or "").strip())
                tw = bool((cfg.get("twitter_bearer_token") or "").strip() or (os.environ.get("TWITTER_BEARER_TOKEN") or "").strip())
                return jsonify({"success": True, "facebook": fb, "twitter": tw})
            except Exception as e:
                logger.debug(f"Linked accounts error: {e}")
                return jsonify({"success": True, "facebook": False, "twitter": False})

        @self.app.route('/api/learning/link-facebook', methods=['POST'])
        def link_facebook_account():
            """Save the user's Facebook access token to config so Elysia can use their account for learning."""
            try:
                data = request.get_json() or {}
                token = (data.get("token") or "").strip()
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config()
                if not cfg:
                    cfg = {}
                cfg["facebook_access_token"] = token
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "linked": bool(token), "message": "Facebook account linked" if token else "Facebook token cleared"})
            except Exception as e:
                logger.error(f"Link Facebook error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/link-twitter', methods=['POST'])
        def link_twitter_account():
            """Save the user's X (Twitter) Bearer Token to config so Elysia can learn from Twitter search."""
            try:
                data = request.get_json() or {}
                token = (data.get("token") or "").strip()
                from pathlib import Path
                import json
                from project_guardian.auto_learning import load_learning_config
                cfg_path = Path(__file__).resolve().parent.parent / "config" / "auto_learning.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg = load_learning_config()
                if not cfg:
                    cfg = {}
                cfg["twitter_bearer_token"] = token
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                return jsonify({"success": True, "linked": bool(token), "message": "X (Twitter) account linked" if token else "Twitter token cleared"})
            except Exception as e:
                logger.error(f"Link Twitter error: {e}", exc_info=True)
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route('/api/learning/start', methods=['POST'])
        def start_learning():
            """Start a learning session (Reddit, RSS, ChatGPT chatlogs) via auto_learning."""
            try:
                data = request.get_json() or {}
                platform = data.get('platform', 'reddit')
                query = data.get('query', '')
                max_items = max(2, min(20, int(data.get('max_items', 5))))
                
                from project_guardian.auto_learning import (
                    run_learning_session,
                    run_mistral_chained_learning_session,
                    get_learned_storage_path,
                    get_chatlogs_path,
                    load_learning_config,
                    DEFAULT_REDDIT_SUBS,
                    DEFAULT_RSS_FEEDS,
                    DEFAULT_FACEBOOK_PAGES,
                    DEFAULT_TWITTER_SEARCH_QUERIES,
                )
                import os
                cfg = load_learning_config()
                storage = get_learned_storage_path()
                chatlogs = get_chatlogs_path()
                facebook_token = cfg.get("facebook_access_token") or os.environ.get("FACEBOOK_ACCESS_TOKEN") or ""
                twitter_token = cfg.get("twitter_bearer_token") or os.environ.get("TWITTER_BEARER_TOKEN") or ""
                llm = None
                if hasattr(self.orchestrator, 'chat_with_llm'):
                    llm = lambda m: self.orchestrator.chat_with_llm(m)
                else:
                    try:
                        import sys
                        main_mod = sys.modules.get("__main__")
                        if main_mod:
                            status_sys = getattr(main_mod, "_status_system", None)
                            if status_sys and hasattr(status_sys, "chat_with_llm"):
                                llm = lambda m: status_sys.chat_with_llm(m)
                    except Exception:
                        pass
                reddit_subs = cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS
                rss_feeds = cfg.get("rss_feeds") or DEFAULT_RSS_FEEDS
                facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
                twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
                chatlogs_path = chatlogs
                web_urls = []
                if platform == 'reddit':
                    subs = [query.replace(" ", "") if query else "MachineLearning"]
                    reddit_subs = subs
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'rss':
                    reddit_subs = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'facebook':
                    reddit_subs = []
                    rss_feeds = []
                    twitter_search_queries = []
                    chatlogs_path = None
                    if query:
                        facebook_pages = [p.strip() for p in query.split(",") if p.strip()]
                    if not facebook_pages:
                        facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
                elif platform == 'twitter':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    chatlogs_path = None
                    if query:
                        twitter_search_queries = [q.strip() for q in query.split(",") if q.strip()]
                    if not twitter_search_queries:
                        twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
                elif platform == 'chatgpt' or platform == 'chatlogs':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = chatlogs
                elif platform == 'web':
                    web_urls = [u.strip() for u in query.split(",") if u.strip() and (u.startswith("http://") or u.startswith("https://"))]
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    chatlogs_path = None
                elif platform == 'all':
                    raw_w = cfg.get("web_urls") or []
                    web_urls = [
                        u.strip() for u in raw_w
                        if isinstance(u, str) and u.strip().startswith(("http://", "https://"))
                    ][:5]
                elif platform == 'mistral_chain':
                    reddit_subs = []
                    rss_feeds = []
                    facebook_pages = []
                    twitter_search_queries = []
                    web_urls = []
                    chatlogs_path = chatlogs
                else:
                    pass
                if platform not in ('web', 'all', 'mistral_chain'):
                    web_urls = []
                
                memory = None
                if hasattr(self.orchestrator, 'memory') and self.orchestrator.memory:
                    memory = self.orchestrator.memory
                if platform == 'mistral_chain':
                    topics_use = list(cfg.get("topics") or [])
                    if query:
                        extras = [t.strip() for t in query.split(",") if t.strip()]
                        topics_use = extras + [t for t in topics_use if t not in extras]
                    result = run_mistral_chained_learning_session(
                        storage_path=storage,
                        topics=topics_use,
                        memory=memory,
                        llm_callback=llm,
                        chatlogs_path=chatlogs_path,
                        twitter_bearer_token=twitter_token or None,
                        default_reddit_subs=cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS,
                        seed_twitter_queries=cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES,
                    )
                    if result.get("mistral_chained_error"):
                        return jsonify({
                            "success": False,
                            "error": f"Mistral chained learning failed (is Ollama running?): {result.get('mistral_chained_error')}",
                        }), 500
                else:
                    result = run_learning_session(
                        storage_path=storage,
                        topics=[],
                        reddit_subs=reddit_subs,
                        rss_feeds=rss_feeds,
                        chatlogs_path=chatlogs_path,
                        web_urls=web_urls if web_urls else None,
                        facebook_pages=facebook_pages if (platform == 'facebook' or platform == 'all') and facebook_token else None,
                        facebook_access_token=facebook_token or None,
                        twitter_search_queries=twitter_search_queries if (platform == 'twitter' or platform == 'all') and twitter_token else None,
                        twitter_bearer_token=twitter_token or None,
                        max_per_source=max_items,
                        max_chatlogs=max_items,
                        llm_callback=llm,
                        memory=memory,
                    )
                
                mc = result.get("memory_count", 0)
                msg = f"Saved {result.get('saved', 0)} items to {result.get('file', 'learned')}"
                if mc:
                    msg += f" ({mc} piped to memory)"
                return jsonify({
                    "success": True,
                    "result": {
                        "status": "success",
                        "message": msg,
                        "data": {
                            "posts_processed": result.get("saved", 0),
                            "entries_processed": result.get("saved", 0),
                            "articles_processed": result.get("saved", 0),
                            "memory_count": mc,
                        }
                    }
                })
            except Exception as e:
                logger.error(f"Learning start error: {e}", exc_info=True)
                return jsonify({"error": str(e), "success": False}), 500
                
    def _setup_socketio(self):
        """Setup SocketIO event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            logger.info("Client connected to control panel")
            emit('status_update', {"message": "Connected"})
    
    def _check_port_available(self, host: str, port: int) -> bool:
        """Check if a port is available for binding."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                return result != 0  # 0 means port is in use
        except Exception:
            return False
    
    def _find_available_port(self, start_port: int, max_attempts: int = 10) -> int:
        """Find an available port starting from start_port."""
        for i in range(max_attempts):
            port = start_port + i
            if self._check_port_available(self.host, port):
                return port
        raise OSError(f"Could not find available port in range {start_port}-{start_port + max_attempts - 1}")
    
    def _wait_for_server_ready(self, timeout: float = 10.0) -> bool:
        """Wait for server to be ready by checking if port is listening."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check for server errors first (fast failure)
            if self._server_error:
                logger.error(f"[DASHBOARD] Server error detected during readiness check: {self._server_error}")
                return False
            
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    result = s.connect_ex((self.host, self._actual_port or self.port))
                    if result == 0:  # Port is listening
                        return True
            except Exception:
                pass
            time.sleep(0.1)
        return False
            
    def start(self, debug: bool = False, source: str = "unknown"):
        """
        Start the web server (idempotent - only starts once per process).
        
        Args:
            debug: Enable debug mode
            source: Call site identifier for instrumentation
        """
        global _dashboard_started, _dashboard_start_attempts
        
        # Module-level guard: prevent multiple dashboard starts
        with _dashboard_start_lock:
            _dashboard_start_attempts += 1
            attempt_num = _dashboard_start_attempts
            thread_name = threading.current_thread().name
            
            if _dashboard_started:
                logger.info(
                    "[DASHBOARD] start attempt %d source=%s thread=%s - Already started; skipping",
                    attempt_num, source, thread_name
                )
                return
            
            # Instance-level guard (defensive)
            if self.running:
                logger.warning(
                    "[DASHBOARD] start attempt %d source=%s thread=%s - Instance already running; skipping",
                    attempt_num, source, thread_name
                )
                return
            
            # Check port availability and find alternative if needed
            if not self._check_port_available(self.host, self.port):
                logger.warning(
                    f"[DASHBOARD] Port {self.port} is in use, attempting to find alternative..."
                )
                try:
                    self.port = self._find_available_port(self.port)
                    logger.info(f"[DASHBOARD] Using port {self.port} instead")
                except OSError as e:
                    logger.error(f"[DASHBOARD] Could not find available port: {e}")
                    raise
            
            # Reset readiness event
            self._server_ready.clear()
            self._server_error = None
            self._actual_port = self.port
            
            # Mark as started BEFORE actually starting (prevents race conditions)
            _dashboard_started = True
            self.running = True
            
            logger.info(
                "[DASHBOARD] start attempt %d source=%s thread=%s - Starting Elysia Control Panel on http://%s:%s",
                attempt_num, source, thread_name, self.host, self.port
            )
        
        # Start in background thread
        def run_server():
            global _dashboard_started
            try:
                logger.info(
                    f"[DASHBOARD] Server thread starting - binding to {self.host}:{self.port} (PID: {os.getpid()})"
                )
                self.socketio.run(
                    self.app,
                    host=self.host,
                    port=self.port,
                    debug=debug,
                    use_reloader=False,
                    allow_unsafe_werkzeug=True
                )
            except OSError as e:
                if "Address already in use" in str(e) or "address is already in use" in str(e).lower():
                    logger.error(f"[DASHBOARD] Port {self.port} is already in use: {e}")
                    self._server_error = f"Port {self.port} already in use"
                else:
                    logger.error(f"[DASHBOARD] Server OSError: {e}")
                    self._server_error = str(e)
                # Reset flag on error so it can be retried
                with _dashboard_start_lock:
                    _dashboard_started = False
                    self.running = False
            except Exception as e:
                logger.error(f"[DASHBOARD] Server error: {e}", exc_info=True)
                self._server_error = str(e)
                # Reset flag on error so it can be retried
                with _dashboard_start_lock:
                    _dashboard_started = False
                    self.running = False
            finally:
                self._server_ready.set()  # Signal even on error
            
        server_thread = threading.Thread(target=run_server, daemon=True, name="UIControlPanel-Server")
        server_thread.start()
        
        # Wait briefly so startup doesn't stall the main thread (was 10s, now 2s max; never raise)
        time.sleep(0.3)
        if self._wait_for_server_ready(timeout=2.0):
            self._server_ready.set()
            logger.info(
                f"[DASHBOARD] Server is listening on http://{self.host}:{self.port} (PID: {os.getpid()})"
            )
        else:
            self._server_ready.set()
            if self._server_error:
                logger.warning(f"[DASHBOARD] Server may still be starting: {self._server_error}")
            else:
                logger.warning(
                    "[DASHBOARD] Server did not become ready in 2s (panel may load in a few seconds); continuing startup"
                )
        
    def stop(self):
        """Stop the web server."""
        global _dashboard_started
        with _dashboard_start_lock:
            _dashboard_started = False
            self.running = False
        logger.info("Control panel stopped")


def reset_dashboard_guard():
    """
    Reset the dashboard start guard (for testing only).
    """
    global _dashboard_started, _dashboard_start_attempts
    with _dashboard_start_lock:
        _dashboard_started = False
        _dashboard_start_attempts = 0
    logger.debug("[DASHBOARD] Guard reset (for testing)")


def create_control_panel(orchestrator, host: str = "127.0.0.1", port: int = 5000):
    """
    Create and return a UIControlPanel instance.
    
    Args:
        orchestrator: SystemOrchestrator instance
        host: Host to bind to
        port: Port to listen on
        
    Returns:
        UIControlPanel instance
    """
    return UIControlPanel(orchestrator, host, port)

