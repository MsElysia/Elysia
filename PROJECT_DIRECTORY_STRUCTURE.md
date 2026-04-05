# Project Guardian - Full Directory Structure

## Main Entry Points

```
C:\Users\mrnat\Project guardian\
│
├── elysia\                          # Main Elysia package
│   ├── __init__.py
│   ├── __main__.py                  # ← PRIMARY ENTRY POINT (python -m elysia)
│   ├── cli.py                       # Command-line interface
│   ├── runtime.py                   # ElysiaRuntime orchestrator
│   ├── config.py                    # Runtime configuration
│   ├── events.py                    # EventBus system
│   ├── logging_config.py
│   ├── shell.py                     # Interactive shell
│   ├── status.py                    # Status checking
│   │
│   ├── agents\                      # Agent implementations
│   │   ├── __init__.py
│   │   ├── implementer.py          # Elysia-Implementer agent
│   │   └── webscout.py             # Elysia-WebScout agent
│   │
│   ├── api\                         # REST API server
│   │   ├── __init__.py
│   │   └── server.py               # RuntimeAPIServer (port 8123)
│   │
│   └── core\                        # Core systems
│       ├── __init__.py
│       └── proposal_system.py       # Proposal system (validation, lifecycle)
│
├── run_elysia.py                    # Alternative entry point (GuardianCore)
├── run_elysia_interactive.py        # Interactive runner
├── run_elysia_unified.py            # Unified system runner
├── elysia_proposals_cli.py          # Proposal management CLI
│
├── START_ELYSIA.bat                 # Batch file launcher
├── START_ELYSIA_UNIFIED.bat
├── START_ELYSIA_INTERFACE.bat
│
├── proposals\                       # Proposal storage
│   └── [proposal-id]\
│       ├── metadata.json
│       ├── README.md
│       ├── design\
│       │   ├── architecture.md
│       │   ├── integration.md
│       │   └── implementation_plan.md
│       ├── research\
│       │   ├── summary.md
│       │   ├── sources.md
│       │   └── patterns.md
│       └── implementation\
│           ├── diff.patch
│           ├── task_results.json
│           └── todos.md
│
├── tests\                           # Test suite
│   ├── conftest.py
│   ├── test_proposal_validation.py
│   ├── test_lifecycle_transitions.py
│   ├── test_duplicate_detection.py
│   ├── test_history_tracking.py
│   ├── test_proposal_domains.py
│   └── test_implementer_agent.py
│
├── config\                          # Configuration files
│   ├── proposal_domains.json
│   └── [other config files]
│
├── project_guardian\                # Legacy Project Guardian modules
│   └── [various modules]
│
├── core_modules\                    # Core module implementations
│   └── elysia_core_comprehensive\
│
├── scripts\                         # Utility scripts
│
├── logs\                            # Log files
│
├── memory\                          # Memory storage
│
├── data\                            # Data files
│
└── [various .py, .md, .bat files]  # Root level scripts and docs
```

## Key Files by Purpose

### Entry Points
- **`elysia/__main__.py`** → `elysia/cli.py` → `elysia/runtime.py` (PRIMARY)
- `run_elysia.py` (Legacy GuardianCore)
- `run_elysia_interactive.py` (Interactive)
- `run_elysia_unified.py` (Unified)

### Core Runtime
- `elysia/runtime.py` - ElysiaRuntime orchestrator
- `elysia/config.py` - Configuration management
- `elysia/events.py` - EventBus system

### Agents
- `elysia/agents/implementer.py` - Elysia-Implementer (executes proposals)
- `elysia/agents/webscout.py` - Elysia-WebScout (research & proposals)

### Proposal System
- `elysia/core/proposal_system.py` - Proposal validation, lifecycle, watcher
- `elysia_proposals_cli.py` - CLI for proposal management

### API
- `elysia/api/server.py` - REST API server (port 8123)

### Tests
- `tests/test_implementer_agent.py` - ImplementerAgent tests
- `tests/test_proposal_*.py` - Proposal system tests

## How to Start

**Primary method:**
```bash
python -m elysia run
```

**Alternative methods:**
```bash
# Batch file
START_ELYSIA.bat

# Direct Python
python run_elysia_interactive.py
python run_elysia_unified.py
```

## API Endpoints (when running)

- `http://localhost:8123/api/status` - System status
- `http://localhost:8123/api/events` - Recent events
- `http://localhost:8123/api/proposals` - List proposals
- `http://localhost:8123/api/proposals/<id>/implement` - Implement proposal
- `http://localhost:8123/api/proposals/<id>/implementation` - Implementation status

