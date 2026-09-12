# Project Guardian / Elysia

**An Autonomous AI System with Self-Modification, Trust Management, and Financial Operations**

**GitHub:** [github.com/MsElysia/Elysia](https://github.com/MsElysia/Elysia)

[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Security](https://img.shields.io/badge/security-audited-green)]()
[![Documentation](https://img.shields.io/badge/docs-complete-blue)]()

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Optional: Better embeddings and semantic search (recommended)
pip install -r requirements-optional.txt

# Configure system
python setup_guardian.py

# Set API keys (secure method)
export OPENAI_API_KEY=sk-...
export CLAUDE_API_KEY=sk-ant-...

# Primary live boot (Windows desktop / operator)
START_ELYSIA_UNIFIED.bat
# or: Start_Elysia_Backend.cmd   → python elysia.py
```

**Status API**: http://127.0.0.1:8888/status  
**Control panel**: http://127.0.0.1:5000  

**Boot contract (canonical):** [`docs/CANONICAL_BOOT_CONTRACT.md`](docs/CANONICAL_BOOT_CONTRACT.md)  
Secondary / parallel entries (`python -m project_guardian`, `python -m elysia run`) are documented there — they are **not** the desktop primary path.

### Optional: Poetry

The repo includes `pyproject.toml` and `poetry.lock` for a package-based install. With [Poetry](https://python-poetry.org/) installed: `poetry install`

### Safe-stack smoke tests (CI slice)

Verifies conversation memory, brain trace visibility, TDA naming, self-improvement proposals/export, prompt contracts, and memory ranking — **without** starting servers, enabling autonomy, or calling external APIs:

```bash
python scripts/run_safe_stack_smoke_tests.py
# or: make safe-smoke
```

GitHub Actions: workflow **Safe stack smoke** (`.github/workflows/safe-stack-smoke.yml`). See `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` for scope and limits.

---

## Documentation

- **[Canonical Boot Contract](docs/CANONICAL_BOOT_CONTRACT.md)** - What is actually live
- **[Canonical Runtime Map](REPORTS/canonical_runtime_map.md)** - Subsystem classification
- **[User Guide](USER_GUIDE.md)** - Complete usage instructions
- **[API Reference](API_REFERENCE.md)** - REST API documentation
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Production deployment
- **[Security Checklist](SECURITY_CHECKLIST.md)** - Pre-deployment security
- **[Troubleshooting](TROUBLESHOOTING.md)** - Problem solving
- **[Quick Reference](QUICK_REFERENCE.md)** - One-page cheat sheet

---

## Features

### Core Systems
- **Event Loop**: Non-blocking async task execution
- **Memory System**: Persistent memory with timeline logging
- **Trust System**: Comprehensive trust scoring and evaluation
- **Mutation System**: Safe self-modification with AI validation

### Financial Operations
- **Core Credits**: Virtual currency system
- **Revenue Sharing**: Master-slave revenue distribution
- **Franchise Model**: Business structure for slave operations
- **Asset Management**: Financial tracking and management

### Security & Safety
- **Encrypted Secrets**: Secure API key management
- **Mutation Safety**: Multi-layer validation and rollback
- **Recovery Vault**: System snapshots and recovery
- **Trust-Based Access**: Policy-driven access control

### External Access
- **REST API**: Complete API for system interaction
- **Web UI**: Control panel for monitoring and control
- **Health Monitoring**: System health and metrics

---

## Architecture

```
Project Guardian
├── Foundation Layer
│   ├── ElysiaLoopCore (event loop)
│   ├── RuntimeLoop (task scheduling)
│   └── SystemOrchestrator (coordination)
├── Memory & State
│   ├── MemoryCore (with TimelineMemory)
│   └── MemoryVectorSearch (semantic search)
├── Trust & Safety
│   ├── TrustRegistry
│   ├── TrustPolicyManager
│   └── TrustAuditLog
├── Mutation System
│   ├── MutationEngine
│   ├── AIMutationValidator
│   ├── MutationSandbox
│   └── RecoveryVault
├── Financial System
│   ├── CoreCredits
│   ├── RevenueSharing
│   └── FranchiseManager
└── External Access
    ├── APIServer (REST API)
    └── UI Control Panel
```

---

## Security

**Security Features**:
- Encrypted API key storage
- Environment variable support
- Secure authentication
- Trust-based access control
- Audit logging

**See**: [Security Audit Report](SECURITY_AUDIT_REPORT.md)  
**Checklist**: [Security Checklist](SECURITY_CHECKLIST.md)

---

## Getting Started

### Installation

1. **Clone/Navigate to project**
   ```bash
   git clone https://github.com/MsElysia/Elysia.git
   cd Elysia
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run setup wizard**
   ```bash
   python setup_guardian.py
   ```

### Configuration

**Secure API Keys** (Recommended):
```bash
export OPENAI_API_KEY=sk-...
export CLAUDE_API_KEY=sk-ant-...
```

**Or use SecretsManager**:
```python
from project_guardian.secrets_manager import SecretsManager
manager = SecretsManager()
manager.set_secret("openai_api_key", "sk-...")
```

### Running

```bash
# Primary (unified backend + attach UI)
START_ELYSIA_UNIFIED.bat

# Backend only
python elysia.py

# Secondary package entry (SystemOrchestrator — not desktop-primary)
python -m project_guardian

# Probe status
curl http://127.0.0.1:8888/status
```

See [`docs/CANONICAL_BOOT_CONTRACT.md`](docs/CANONICAL_BOOT_CONTRACT.md).

---

## Development

### Project Structure

```
project_guardian/
├── core/              # Core systems
├── memory/            # Memory modules
├── trust/             # Trust & safety
├── mutation/          # Mutation system
├── financial/         # Financial modules
├── master_slave/      # Master-slave architecture
└── api/               # API server
```

### Testing

```bash
# Run verification
python verify_system.py

# Run safe-stack smoke tests (pytest slice; no services, autonomy, or live execution)
python scripts/run_safe_stack_smoke_tests.py

# Optional Makefile shortcut
make safe-smoke

# Manual testing
python test_mutation_manual.py
```

---

## Status

**System Status**: Production Ready  
**Modules Implemented**: 44+  
**Documentation**: Complete  
**Security**: Audited

**See**: [Project Status](PROJECT_STATUS.md)

---

## Contributing

1. Review security checklist before committing
2. Never commit API keys or secrets
3. Follow code style guidelines
4. Update documentation for new features

---

## License

[Your License Here]

---

## Quick Links

- [User Guide](USER_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Project Status](PROJECT_STATUS.md)

---

**Status**: System is operational and production-ready.
