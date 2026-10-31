# Elysia / Project Guardian

**Experimental local-first AI architecture for durable memory, modular capabilities, and human-authorized tasks.**

**Development status (October 31, 2026): NOT RELEASE READY.** The repository includes legacy modules and newer, separately reviewed draft integrations. Hosted or synthetic test passes do not establish a complete owner-local Windows installation, production security approval, or end-to-end readiness. Autonomy and cloud-provider activation are not authorized by this documentation.

**Repository:** [github.com/MsElysia/Elysia](https://github.com/MsElysia/Elysia)

**Join responsibly:** [Invitation to AI agents, developers, and human operators](AGENT_COLLABORATION.md) · [Contribution and safety rules](CONTRIBUTING.md)

**Current work:** Consult exact-head open pull requests and their evidence. Older documents including `PROJECT_STATUS.md` (last updated in 2025) and `SECURITY_AUDIT_REPORT.md` are historical; they are **not** proof of current release or independent security certification.

---

## Legacy setup examples (not a verified release installation)

> **Warning:** The following commands are historical development examples, not an approved installation recipe. Do not configure paid providers, activate autonomy, import private data, or use this as a production setup. Newer restricted components may use different commands and verification requirements.

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

## Feature areas in the repository (not independently certified end-to-end)

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

**Security-related components documented in the repository (not a current external audit or certification)**:
- Encrypted API key storage
- Environment variable support
- Secure authentication
- Trust-based access control
- Audit logging

**Historical reference (November 2025, not a current security certification)**: [Security Audit Report](SECURITY_AUDIT_REPORT.md)  
**Checklist**: [Security Checklist](SECURITY_CHECKLIST.md)

---

## Legacy development instructions (not a production installation)

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

**Current status:** Development and integration are ongoing; no production-release acceptance is claimed here. Verify each capability against exact source SHAs, independent tests, and the specific machine/environment before relying on it.

**Historical snapshot only:** [Project Status (2025)](PROJECT_STATUS.md). For active work, review the repository's open pull requests.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the permitted scope, safe issue-reporting format, and authorization boundaries. See [AGENT_COLLABORATION.md](AGENT_COLLABORATION.md) for an invitation to human and AI-assisted reviewers. Nothing in these documents authorizes agents to act without their human operators' approval.

---

## License

**License not yet selected.** No `LICENSE` file is currently published. Public visibility does not grant permission to reuse or redistribute repository code. Formal contribution and reuse terms need a maintainer decision before broad code contributions are invited.

---

## Quick Links

- [User Guide](USER_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Project Status](PROJECT_STATUS.md)

---

**Status**: Active development; release readiness has not been established.
