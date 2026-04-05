# Project Guardian

An autonomous AI safety and management system that integrates advanced components from Elysia Core for enhanced capabilities.

## Overview

Project Guardian is a comprehensive AI safety system that provides:

- **Memory Management**: Persistent, categorized memory with priority levels
- **Safe Code Mutation**: AI-reviewed code changes with automatic backups
- **Safety Validation**: Built-in skepticism and critical thinking
- **Trust Management**: Dynamic trust scoring with decay mechanisms
- **Rollback Recovery**: Safe restoration and backup management
- **Task Management**: Comprehensive task tracking and completion
- **Consensus Decision Making**: Multi-agent voting and consensus building
- **Plugin System**: Dynamic plugin loading and management

## Core Components

### Memory Core (`memory.py`)
- Persistent JSON-based memory storage
- Categorized memories with priority levels
- Search and recall capabilities
- Memory statistics and reporting

### Mutation Engine (`mutation.py`)
- Safe code modification with automatic backups
- GPT-4 powered safety review
- Dangerous pattern detection
- Mutation history and statistics

### Safety Engine (`safety.py`)
- Critical thinking and validation
- Code mutation safety review
- Action validation
- System health monitoring

### Trust Matrix (`trust.py`)
- Dynamic trust scoring (0.0 to 1.0)
- Trust decay mechanisms
- Action-based trust validation
- Trust statistics and reporting

### Rollback Engine (`rollback.py`)
- Automatic backup creation
- Safe file restoration
- Backup integrity validation
- Cleanup and management

### Task Engine (`tasks.py`)
- Task creation and management
- Priority-based task handling
- Task logging and completion tracking
- Task statistics and cleanup

### Consensus Engine (`consensus.py`)
- Multi-agent voting system
- Weighted consensus calculation
- Agent registration and management
- Decision history tracking

### Guardian Core (`core.py`)
- Main system integration
- Component coordination
- System status monitoring
- Safety checks and validation

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd project_guardian

# Install dependencies
pip install openai flask

# Set up environment variables
export OPENAI_API_KEY="your-openai-api-key"
```

## Quick Start

```python
from project_guardian import GuardianCore

# Initialize the system
guardian = GuardianCore()

# Create a task
task = guardian.create_task(
    "example_task",
    "Demonstrate task creation",
    priority=0.7,
    category="demo"
)

# Store a memory
guardian.memory.remember(
    "Important system event",
    category="system",
    priority=0.8
)

# Propose a safe mutation
result = guardian.propose_mutation(
    "example.py",
    "# Safe code change\nprint('Hello, Guardian!')"
)

# Get system status
status = guardian.get_system_status()
print(guardian.get_system_summary())

# Shutdown safely
guardian.shutdown()
```

## Key Features

### Safety First
- All mutations require safety review
- Built-in skepticism and validation
- Trust-based action authorization
- Automatic backup and rollback

### Autonomous Management
- Self-monitoring and health checks
- Consensus-based decision making
- Dynamic trust management
- Task prioritization and completion

### Extensible Architecture
- Plugin system for extensions
- Modular component design
- Comprehensive logging
- API-ready integration

## Integration with Elysia Core

Project Guardian integrates the best components from Elysia Core:

1. **Memory System**: Enhanced with categories and priority levels
2. **Mutation Engine**: Improved with GPT-4 review and safety checks
3. **Safety Validation**: Expanded critical thinking capabilities
4. **Trust Management**: Dynamic scoring with decay mechanisms
5. **Rollback System**: Comprehensive backup and recovery
6. **Task Management**: Advanced task tracking and completion
7. **Consensus Engine**: Multi-agent decision making
8. **Plugin System**: Dynamic extension capabilities

## Configuration

```python
config = {
    "memory_file": "guardian_memory.json",
    "backup_folder": "guardian_backups",
    "plugin_directory": "guardian_plugins",
    "consensus_threshold": 0.6,
    "trust_decay_rate": 0.01,
    "safety_level": "high"
}

guardian = GuardianCore(config)
```

## API Usage

### Memory Management
```python
# Store memories
guardian.memory.remember("Event", category="system", priority=0.8)

# Recall memories
recent = guardian.memory.recall_last(5, category="system")

# Search memories
results = guardian.memory.search_memories("keyword")
```

### Task Management
```python
# Create tasks
task = guardian.tasks.create_task("name", "description", priority=0.7)

# Update status
guardian.tasks.update_task_status(task["id"], "in_progress")

# Complete tasks
guardian.tasks.complete_task(task["id"])
```

### Trust Management
```python
# Update trust
guardian.trust.update_trust("component", 0.1, "successful operation")

# Check trust
trust_level = guardian.trust.get_trust("component")

# Validate actions
can_mutate = guardian.trust.validate_trust_for_action("component", "mutation")
```

### Consensus Decision Making
```python
# Register agents
guardian.consensus.register_agent("agent_name", "type", weight=1.0)

# Cast votes
guardian.consensus.cast_vote("agent", "action", confidence=0.8)

# Make decisions
decision = guardian.consensus.decide("action")
```

## Safety Features

### Mutation Safety
- Automatic backup creation
- GPT-4 safety review
- Dangerous pattern detection
- Trust-based authorization

### System Health
- Memory usage monitoring
- Task completion tracking
- Error rate monitoring
- Consensus health checks

### Trust Validation
- Component trust scoring
- Action-based trust requirements
- Trust decay mechanisms
- Low-trust component warnings

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all safety checks pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Elysia Core for the foundational components
- OpenAI for GPT-4 integration
- The AI safety community for inspiration and guidance 