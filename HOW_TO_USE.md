# HOW_TO_USE.md
# How to Use the Elysia System

## Quick Start

```python
from project_guardian.core import GuardianCore

# Initialize the system
core = GuardianCore({
    "enable_resource_monitoring": False,
    "enable_runtime_health_monitoring": False,
})
```

## 1. Memory Operations

Store and retrieve memories:

```python
# Store a memory
core.memory.remember("I learned about Python today", category="learning")

# Recall recent memories
memories = core.memory.recall_last(count=5)
for mem in memories:
    print(f"{mem.get('category')}: {mem.get('thought')}")
```

## 2. System Status

Check system status:

```python
status = core.get_system_status()
print(f"Total memories: {status['memory']['total_memories']}")
print(f"Uptime: {status['uptime']}")
```

## 3. Startup Verification

Verify all components initialized:

```python
verification = core.get_startup_verification()
checks = verification.get("checks", [])
successes = sum(1 for c in checks if c.get("status") == "success")
print(f"{successes}/{len(checks)} checks passed")
```

## 4. Mutation Engine

Propose code changes:

```python
mutation_id = core.mutation.propose_mutation(
    target_module="example.py",
    mutation_type="code_modification",
    description="Add error handling",
    proposed_code="def func():\n    try:\n        pass\n    except:\n        pass",
    original_code="def func():\n    pass"
)

# Check mutation status
mutation = core.mutation.get_mutation(mutation_id)
print(f"Status: {mutation.status.value}")
```

## 5. Task Management

Create and manage tasks:

```python
# Create a task
task_id = core.tasks.create_task(
    description="Review system performance",
    priority="high",
    category="monitoring"
)

# Get task
task = core.tasks.get_task(task_id)
print(f"Task: {task.description}, Status: {task.status.value}")
```

## 6. Trust Management

Work with trust scores:

```python
# Get trust matrix
trust_info = core.trust.get_trust_matrix()
print(f"Trust nodes: {len(trust_info.get('nodes', {}))}")
```

## 7. Consensus Engine

Check consensus status:

```python
consensus_info = core.consensus.get_consensus_status()
agents = consensus_info.get('agents', {})
print(f"Active agents: {len(agents)}")
```

## Complete Example

```python
from project_guardian.core import GuardianCore

# Initialize
core = GuardianCore()

# Store memories
core.memory.remember("User asked how to use the system", category="interaction")
core.memory.remember("System is operational", category="status")

# Check status
status = core.get_system_status()
print(f"System has {status['memory']['total_memories']} memories")

# Recall recent
memories = core.memory.recall_last(count=3)
print(f"Retrieved {len(memories)} recent memories")

# Shutdown when done
core.shutdown()
```

## Available Components

- `core.memory` - Memory storage and retrieval
- `core.mutation` - Code mutation proposals
- `core.tasks` - Task management
- `core.trust` - Trust tracking
- `core.consensus` - Multi-agent consensus
- `core.get_system_status()` - System status
- `core.get_startup_verification()` - Startup checks
- `core.shutdown()` - Graceful shutdown

## Running Examples

Run the example script:
```bash
python usage_examples.py
```

Check system status:
```bash
python check_status.py
```

Run interactively:
```bash
python run_elysia_interactive.py
```

