# Elysia Unified Runtime Implementation

## Overview

This document describes the unified runtime system ("god switch") for Elysia that provides a single entry point to start, monitor, and interact with all Elysia subsystems.

## Architecture

The unified runtime follows the pattern specified in the implementation plan:

```
elysia/
├── __init__.py
├── __main__.py          # Entry point: `python -m elysia`
├── cli.py               # CLI argument parsing and dispatch
├── runtime.py           # ElysiaRuntime: central orchestrator
├── events.py            # Event + EventBus for observability
├── config.py            # Configuration loading
├── logging_config.py    # Structured logging setup
├── shell.py             # Interactive shell
├── status.py            # Status command
├── core/
│   └── proposal_system.py  # ProposalSystem wrapper (Validator, LifecycleManager, Watcher)
├── agents/
│   └── webscout.py          # WebScoutAgent wrapper
└── api/
    └── server.py            # REST API server
```

## Key Components

### 1. ElysiaRuntime (`runtime.py`)

The central orchestrator that:
- Initializes all subsystems (Architect-Core, ProposalSystem, WebScout, API server)
- Manages lifecycle (start/stop)
- Publishes events via EventBus
- Provides status information

### 2. EventBus (`events.py`)

Lightweight publish/subscribe event system:
- Subscribers receive all events
- In-memory buffer of recent events (configurable size)
- Used for observability and logging

### 3. ProposalSystem (`core/proposal_system.py`)

Unified wrapper integrating:
- **ProposalValidator**: Validates proposal structure and metadata schema
- **ProposalLifecycleManager**: Manages status transitions (research → design → proposal → approved/rejected → implemented)
- **ProposalWatcher**: Monitors `proposals/` folder for new/updated proposals

### 4. WebScoutAgent (`agents/webscout.py`)

Wrapper for Elysia-WebScout integration:
- Creates proposals from research tasks
- Background processing loop
- Emits events for proposal creation and research activities

### 5. API Server (`api/server.py`)

REST API endpoints:
- `/api/status` - Runtime status
- `/api/events` - Recent events
- `/api/chat` - Chat interface (routes to Architect-Core or proposal context)
- `/api/proposals` - List proposals
- `/api/proposals/<id>` - Get proposal details
- `/api/proposals/<id>/approve` - Approve proposal
- `/api/proposals/<id>/reject` - Reject proposal
- `/api/proposals/<id>/status` - Transition proposal status
- `/api/webscout/research` - Request WebScout research

## Usage

### Start Everything

```bash
# Start all subsystems
python -m elysia run --mode=all

# Start just core + proposals (no WebScout)
python -m elysia run --mode=core

# Start with custom options
python -m elysia run --mode=all --env=prod --api-port=9000
```

### Check Status

```bash
# From CLI
python -m elysia status

# Or via API
curl http://localhost:8123/api/status
```

### Interactive Shell

```bash
python -m elysia shell
```

Available commands:
- `status` - Show runtime status
- `events` - Show recent events
- `proposals` - List proposals
- `chat <message>` - Send chat message
- `approve <proposal_id>` - Approve a proposal
- `reject <proposal_id> <reason>` - Reject a proposal
- `help` - Show available commands
- `exit` - Exit shell

### Tail Events

```bash
python -m elysia tail-events --limit=50
```

## Event Types

The system emits structured events:

- **Runtime events**: `runtime.initialized`, `runtime.started`, `runtime.stopped`, `runtime.heartbeat`
- **Proposal system events**: `proposal_system.initialized`, `proposal_system.proposal_created`, `proposal_system.status_changed`
- **WebScout events**: `webscout.initialized`, `webscout.started`, `webscout.stopped`, `webscout.proposal_created`, `webscout.research_started`, `webscout.research_failed`
- **API events**: `api.chat`

All events include:
- `ts`: Timestamp (ISO format)
- `source`: Subsystem name
- `type`: Event type
- `payload`: Event-specific data

## Configuration

Configuration is loaded from:
1. Environment variables (e.g., `ELYSIA_MODE`, `ELYSIA_ENV`, `ELYSIA_API_PORT`)
2. CLI arguments (override environment)
3. Defaults (defined in `config.py`)

Key configuration options:
- `mode`: `"all"`, `"core"`, or `"agents"`
- `env`: `"dev"` or `"prod"`
- `proposals_root`: Path to proposals directory (default: `proposals/`)
- `enable_api`: Enable REST API server (default: `True`)
- `enable_webscout`: Enable WebScout agent (default: `True`, disabled in `core` mode)
- `api_host`: API server host (default: `127.0.0.1`)
- `api_port`: API server port (default: `8123`)

## Integration Points

### Architect-Core

The runtime attempts to import and initialize `ArchitectCore` from `architect_core`. If unavailable, it logs a warning and continues without it.

### Proposal System

The proposal system is **required** and will raise an error if initialization fails. It:
- Watches the `proposals/` directory
- Validates proposal structure and metadata
- Manages lifecycle transitions
- Emits events for all proposal activities

### WebScout

WebScout is optional and will be disabled if:
- `mode=core` is specified
- `--no-webscout` flag is used
- Import fails (module not available)

### API Server

The API server runs in a background thread and exposes all runtime functionality via REST endpoints. It integrates with:
- Proposal system (for proposal management)
- WebScout (for research requests)
- Architect-Core (for chat functionality)

## Example Workflow

1. **Start the runtime**:
   ```bash
   python -m elysia run --mode=all
   ```

2. **Check status**:
   ```bash
   python -m elysia status
   ```

3. **Request WebScout research** (via API):
   ```bash
   curl -X POST http://localhost:8123/api/webscout/research \
     -H "Content-Type: application/json" \
     -d '{"topic": "multi-agent orchestration", "domain": "elysia_core"}'
   ```

4. **List proposals**:
   ```bash
   curl http://localhost:8123/api/proposals
   ```

5. **Approve a proposal**:
   ```bash
   curl -X POST http://localhost:8123/api/proposals/webscout-20251129-001/approve \
     -H "Content-Type: application/json" \
     -d '{"approver": "user"}'
   ```

6. **Chat with Elysia**:
   ```bash
   curl -X POST http://localhost:8123/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What proposals are pending?", "context": "general"}'
   ```

## Benefits

1. **Single Entry Point**: One command to start everything
2. **Observability**: All subsystems emit events that can be monitored
3. **Interactivity**: CLI shell and REST API for interaction
4. **Modularity**: Subsystems can be enabled/disabled via configuration
5. **Extensibility**: Easy to add new subsystems or agents

## Next Steps

Potential enhancements:
- Web dashboard for `/api/events/recent`
- More sophisticated chat routing (proposal-specific contexts)
- Background scheduler for periodic tasks
- Metrics collection and health checks
- Proposal templates and validation rules

