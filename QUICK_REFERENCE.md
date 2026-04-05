# Quick Reference Card - Project Guardian

**One-page cheat sheet for common tasks**

---

## 🚀 Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
python setup_guardian.py

# Run
python -m project_guardian

# UI
python start_ui_panel.py
```

---

## 🔐 API Keys (Secure)

```bash
# Set environment variables
export OPENAI_API_KEY=sk-...
export CLAUDE_API_KEY=sk-ant-...

# Or use SecretsManager
python -c "from project_guardian.secrets_manager import get_api_key; print(get_api_key('openai'))"
```

---

## 📝 Common Python Operations

### Memory
```python
from project_guardian.memory import MemoryCore
memory = MemoryCore()
memory.add_memory("content", category="note", importance=0.7)
memories = memory.get_memories(limit=10)
```

### Mutations
```python
from project_guardian.mutation_engine import MutationEngine
engine = MutationEngine()
mutation_id = engine.propose_mutation(...)
proposal = engine.get_proposal(mutation_id)
```

### Trust
```python
from project_guardian.trust_registry import TrustRegistry
registry = TrustRegistry()
registry.register_node("node-1", trust_scores={"mutation": 0.8})
node = registry.get_node("node-1")
```

### Credits
```python
from project_guardian.core_credits import CoreCredits
credits = CoreCredits()
credits.earn(100, "task")
credits.spend(50, "api_call")
balance = credits.get_balance()
```

---

## 🌐 API Endpoints

```
GET  /api/health              # Health check
GET  /api/status              # System status
GET  /api/metrics             # Metrics
GET  /api/mutations           # List mutations
POST /api/mutations/propose   # Propose mutation
GET  /api/trust/nodes         # List nodes
GET  /api/financial/credits   # Credit balance
POST /api/memory/search       # Search memories
```

---

## 🔧 Common Commands

```bash
# Check system status
curl http://localhost:8080/api/health

# View logs
tail -f logs/guardian.log

# Verify system
python verify_system.py

# Backup data
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

---

## 📁 Key Files

```
project_guardian/          # Main code
config/                    # Configuration
data/                      # Data storage
data/secrets/             # Encrypted secrets
logs/                      # Log files
```

---

## ⚠️ Troubleshooting

| Issue | Quick Fix |
|-------|-----------|
| Won't start | Check logs, verify deps |
| API keys fail | Check env vars, test key |
| Out of memory | Clean old memories |
| Tests hang | Use verify_system.py |

---

## 📚 Documentation

- `USER_GUIDE.md` - Complete guide
- `API_REFERENCE.md` - API docs
- `DEPLOYMENT_GUIDE.md` - Production setup
- `TROUBLESHOOTING.md` - Problem solving

---

**Print this page for quick reference!**




















