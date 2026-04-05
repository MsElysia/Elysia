# Project Guardian - User Guide

**Version**: 1.0  
**Last Updated**: November 2, 2025

---

## 📖 Table of Contents

1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running the System](#running-the-system)
5. [Using Features](#using-features)
6. [API Usage](#api-usage)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Topics](#advanced-topics)

---

## 🚀 Quick Start

### First Time Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Setup Wizard**
   ```bash
   python setup_guardian.py
   ```

3. **Configure API Keys** (Secure Method)
   ```bash
   # Set environment variables (recommended)
   set OPENAI_API_KEY=your-key-here
   set CLAUDE_API_KEY=your-key-here
   
   # Or use SecretsManager
   python -m project_guardian.secrets_manager
   ```

4. **Start the System**
   ```bash
   python -m project_guardian
   ```

---

## 📦 Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- 500MB free disk space

### Step-by-Step Installation

```bash
# 1. Clone or navigate to project directory
cd "Project guardian"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create data directories
mkdir -p data logs

# 4. Run setup wizard
python setup_guardian.py
```

### Optional Dependencies

Some features require additional packages:

```bash
# For vector search (optional)
pip install sentence-transformers faiss-cpu

# For system monitoring (optional)
pip install psutil

# For encryption (required for secrets)
pip install cryptography
```

---

## ⚙️ Configuration

### Configuration Files

Configuration is stored in multiple locations:

- **Main Config**: `config/guardian_config.json`
- **API Keys**: Environment variables (preferred) or encrypted storage
- **Trust Policies**: `config/trust_policies.yaml`
- **Logging**: `config/logging_config.json`

### Configuration Options

```json
{
  "memory_path": "data/guardian_memory.json",
  "persona_path": "data/personas.json",
  "conversation_path": "data/conversation_context.json",
  "heartbeat_path": "data/heartbeat.json",
  "log_level": "INFO",
  "api_keys": {
    "openai_api_key": "set via env or secrets",
    "claude_api_key": "set via env or secrets"
  }
}
```

### Environment Variables

Set these for secure configuration:

```bash
# Windows
set OPENAI_API_KEY=sk-...
set CLAUDE_API_KEY=sk-ant-...
set GUARDIAN_LOG_LEVEL=INFO

# Linux/Mac
export OPENAI_API_KEY=sk-...
export CLAUDE_API_KEY=sk-ant-...
export GUARDIAN_LOG_LEVEL=INFO
```

---

## 🏃 Running the System

### Basic Usage

```bash
# Start the system
python -m project_guardian

# Or use the batch file (Windows)
Start Project Guardian.bat
```

### Running with Options

```python
# Custom config
python -m project_guardian --config custom_config.json

# Debug mode
python -m project_guardian --log-level DEBUG
```

### Web UI Control Panel

```bash
# Start UI on port 5000
python start_ui_panel.py

# Access at http://localhost:5000
```

### System Status

Check if system is running:
- Look for "Elysia is running" message
- Check heartbeat file: `data/heartbeat.json`
- Access health endpoint: `http://localhost:8080/api/health`

---

## 🎯 Using Features

### 1. Memory System

```python
from project_guardian.memory import MemoryCore

memory = MemoryCore(filepath="data/guardian_memory.json")

# Store memory
memory.add_memory(
    content="User prefers Python over JavaScript",
    category="preference",
    importance=0.8
)

# Retrieve memories
memories = memory.get_memories(category="preference", limit=10)
```

### 2. Mutation System

```python
from project_guardian.mutation_engine import MutationEngine

engine = MutationEngine(storage_path="data/mutations.json")

# Propose a mutation
mutation_id = engine.propose_mutation(
    target_module="project_guardian/test_module.py",
    mutation_type="code_modification",
    description="Add error handling",
    proposed_code="def new_function(): ...",
    original_code="def old_function(): ..."
)

# Review mutation
from project_guardian.mutation_review_manager import MutationReviewManager
review = manager.review_mutation(mutation_id, author="user")
```

### 3. Financial System

```python
from project_guardian.core_credits import CoreCredits

credits = CoreCredits(storage_path="data/credits.json")

# Earn credits
credits.earn(amount=100, source="task_completion")

# Spend credits
success = credits.spend(amount=50, category="api_call")
```

### 4. Master-Slave Control

```python
from project_guardian.master_slave_controller import MasterSlaveController

controller = MasterSlaveController()

# Register a slave
slave_id = controller.register_slave(
    slave_info={"name": "slave-1", "capabilities": ["mutation"]},
    initial_trust=0.5
)

# Send command to slave
controller.queue_command(slave_id, command="process_task", params={...})
```

---

## 🌐 API Usage

### REST API Endpoints

The system exposes a REST API on port 8080 (default):

#### Health Check
```bash
GET /api/health
# Returns: {"status": "healthy", "components": {...}}
```

#### System Status
```bash
GET /api/status
# Returns: {"initialized": true, "running": true, ...}
```

#### Mutations
```bash
GET /api/mutations
POST /api/mutations/propose
GET /api/mutations/{mutation_id}
```

#### Trust Registry
```bash
GET /api/trust/nodes
GET /api/trust/nodes/{node_id}
```

#### Financial
```bash
GET /api/financial/credits
GET /api/financial/assets
```

See `API_SERVER_DOCUMENTATION.md` for complete API reference.

---

## 🔧 Troubleshooting

### System Won't Start

**Issue**: System hangs during initialization

**Solutions**:
1. Check for blocking file I/O (should be fixed)
2. Verify all dependencies installed
3. Check logs: `logs/guardian.log`
4. Run with debug: `--log-level DEBUG`

### API Keys Not Working

**Issue**: AI features not working

**Solutions**:
1. Verify environment variables set correctly
2. Check encrypted storage: `data/secrets/`
3. Test key: `python -c "import os; print(os.getenv('OPENAI_API_KEY')[:10])"`
4. Use SecretsManager migration tool

### Memory Issues

**Issue**: System running out of memory

**Solutions**:
1. Reduce memory history size in config
2. Clean old memories: `memory.cleanup(oldest_days=30)`
3. Disable vector search if not needed
4. Increase system swap space

### Tests Hanging

**Issue**: Pytest tests hang during collection

**Solutions**:
1. Use manual verification scripts: `verify_system.py`
2. Test modules individually
3. Check for blocking imports
4. Use API-based testing instead

---

## 📚 Advanced Topics

### Custom Module Development

```python
from project_guardian.base_module_adapter import BaseModuleAdapter

class MyCustomModule(BaseModuleAdapter):
    async def initialize(self):
        # Your initialization code
        pass
    
    async def process_task(self, task):
        # Your task processing
        pass
    
    async def shutdown(self):
        # Cleanup code
        pass
```

### Extending Trust System

```python
from project_guardian.trust_registry import TrustRegistry

registry = TrustRegistry()

# Register custom trust evaluator
registry.register_evaluator("custom_domain", custom_evaluator_func)

# Evaluate trust
score = registry.evaluate_trust(node_id, context="custom_domain")
```

### Mutation Safety

The mutation system includes multiple safety layers:

1. **Syntax Validation**: Checks code is valid Python
2. **AI Review**: Uses AI to review code quality
3. **Sandbox Testing**: Tests in isolated environment
4. **Trust-Based Approval**: Requires sufficient trust score
5. **Recovery Vault**: Automatic snapshots before mutations
6. **Rollback**: Can revert if mutation causes issues

---

## 📞 Getting Help

### Documentation
- `PROJECT_STATUS.md` - System overview
- `API_SERVER_DOCUMENTATION.md` - API reference
- `ELYSIA_IMPLEMENTATION_ROADMAP.md` - Feature roadmap

### Logs
- Check `logs/guardian.log` for errors
- Enable debug logging: `"log_level": "DEBUG"`

### Common Issues
- See `TROUBLESHOOTING.md` (if exists)
- Check GitHub issues (if public repo)
- Review log files for error messages

---

## 🎓 Next Steps

1. **Explore Features**: Try different system capabilities
2. **Customize**: Adjust configuration for your needs
3. **Extend**: Add custom modules and features
4. **Deploy**: Set up for production use

---

**Happy Guardian-ing!** 🛡️




















