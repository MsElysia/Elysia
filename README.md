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

# Run system
python -m project_guardian
```

**Access Web UI**: http://localhost:5000  
**API Server**: http://localhost:8080

### Optional: Poetry

The repo includes `pyproject.toml` and `poetry.lock` for a package-based install. With [Poetry](https://python-poetry.org/) installed: `poetry install`

---

## Documentation

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
# Start system
python -m project_guardian

# Start web UI
python start_ui_panel.py

# Access API
curl http://localhost:8080/api/health
```

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
