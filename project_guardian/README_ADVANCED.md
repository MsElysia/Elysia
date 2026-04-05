# Project Guardian - Advanced AI Safety System

## 🛡️ Overview

Project Guardian is a comprehensive AI safety and autonomous management system that integrates multiple advanced capabilities for intelligent, safe, and self-aware AI operations. Built on the foundation of Elysia Core components, it provides unprecedented levels of safety, creativity, and autonomous decision-making.

## 🚀 Key Features

### Core Safety & Management
- **Memory Core**: Persistent, categorized memory system
- **Mutation Engine**: Safe code evolution with safety checks
- **Devil's Advocate**: Critical safety validation
- **Trust Matrix**: Dynamic trust management
- **Rollback Engine**: Automatic recovery and backup
- **Task Engine**: Intelligent task management
- **Consensus Engine**: Multi-agent decision making
- **Plugin Loader**: Extensible plugin system

### Advanced Monitoring & Introspection
- **API Interface**: REST API for external control
- **Introspection Lens**: Self-analysis capabilities
- **Self Reflector**: Deep self-awareness
- **System Monitor**: Health monitoring
- **Heartbeat**: System vitality tracking
- **Error Trap**: Comprehensive error handling

### 🎨 Creativity & Context
- **Dream Engine**: Creative thinking and inspiration
- **Context Builder**: Intelligent context retrieval
- **Memory Search**: Advanced memory querying
- **Pattern Recognition**: Automated pattern analysis

### 🌐 External Interactions
- **Web Reader**: Web content fetching and analysis
- **Voice Thread**: Text-to-speech with personality modes
- **AI Interaction**: ChatGPT integration and AI assistance

### 🎯 Mission Management
- **Mission Director**: Goal-oriented task management
- **Progress Tracking**: Detailed progress monitoring
- **Deadline Management**: Automated deadline checking
- **Subtask Management**: Hierarchical task organization

## 📦 Installation

```bash
pip install -r requirements.txt
```

## 🏗️ Architecture

```
Project Guardian
├── Core System
│   ├── GuardianCore (Main orchestrator)
│   ├── MemoryCore (Persistent memory)
│   └── ConsensusEngine (Multi-agent decisions)
├── Safety Layer
│   ├── DevilsAdvocate (Critical validation)
│   ├── TrustMatrix (Trust management)
│   └── RollbackEngine (Recovery system)
├── Creativity Layer
│   ├── DreamEngine (Creative thinking)
│   ├── ContextBuilder (Context retrieval)
│   └── MemorySearch (Advanced search)
├── External Layer
│   ├── WebReader (Web content)
│   ├── VoiceThread (Speech synthesis)
│   └── AIInteraction (AI assistance)
├── Mission Layer
│   └── MissionDirector (Goal management)
└── Monitoring Layer
    ├── SystemMonitor (Health tracking)
    ├── IntrospectionLens (Self-analysis)
    └── SelfReflector (Deep awareness)
```

## 🎮 Usage Examples

### Basic Initialization

```python
from project_guardian import GuardianCore

# Initialize the system
guardian = GuardianCore()

# Get system status
status = guardian.get_system_status()
print(guardian.get_system_summary())
```

### Creative Dream Cycles

```python
# Begin creative thinking
dreams = guardian.begin_dream_cycle(3)
for dream in dreams:
    print(f"Dream: {dream}")

# Get dream statistics
stats = guardian.dreams.get_dream_stats()
print(f"Total dreams: {stats['total_dreams']}")
```

### External Interactions

```python
# Fetch web content
content = guardian.fetch_web_content("https://example.com")

# Speak with personality
guardian.speak_message("System is ready", "guardian")
guardian.voice.set_mode("warm_guide")
guardian.speak_message("I'm here to help", "warm_guide")

# Ask AI for assistance
response = guardian.ask_ai("What are the best practices for AI safety?")
```

### Mission Management

```python
# Create a mission
mission = guardian.create_mission(
    "Security Audit",
    "Perform comprehensive security analysis",
    priority="high"
)

# Add subtasks
guardian.missions.add_subtask("Security Audit", "Check trust matrix")
guardian.missions.add_subtask("Security Audit", "Validate safety protocols")

# Log progress
guardian.missions.log_progress("Security Audit", "Trust analysis complete", 0.5)

# Complete subtask
guardian.missions.complete_subtask("Security Audit", "Check trust matrix")

# Complete mission
guardian.missions.complete_mission("Security Audit", "Audit completed successfully")
```

### Context Building

```python
# Get context by keyword
context = guardian.get_context(keyword="safety")

# Get context by tag
context = guardian.get_context(tag="error")

# Get recent context
recent = guardian.get_context(minutes=60)
```

### Advanced Analytics

```python
# Find patterns in memory
patterns = guardian.memory_search.find_patterns("safety", hours=24)
print(f"Safety patterns: {patterns['total_matches']}")

# Get web reader statistics
web_stats = guardian.web_reader.get_web_stats()
print(f"Success rate: {web_stats['fetch_success_rate']:.1%}")

# Get voice statistics
voice_stats = guardian.voice.get_voice_stats()
print(f"Speech count: {voice_stats['speech_count']}")
```

### Safety Validation

```python
# Run comprehensive safety check
safety_results = guardian.run_safety_check()
for check in safety_results['checks']:
    print(f"{check['type']}: {check['message']} ({check['severity']})")

# Propose safe mutation
result = guardian.propose_mutation("test.py", "print('Hello World')")
print(result)
```

## 🔧 Configuration

### Environment Variables

```bash
# OpenAI API Key (for AI interactions)
export OPENAI_API_KEY="your-api-key-here"

# Guardian Configuration
export GUARDIAN_LOG_LEVEL="INFO"
export GUARDIAN_MEMORY_PATH="./memory_log.json"
```

### Configuration Dictionary

```python
config = {
    "memory_path": "./memory_log.json",
    "log_level": "INFO",
    "safety_threshold": 0.8,
    "trust_decay_rate": 0.05,
    "dream_cycles": 3,
    "voice_mode": "guardian",
    "web_timeout": 10,
    "ai_model": "gpt-3.5-turbo"
}

guardian = GuardianCore(config)
```

## 🛡️ Safety Features

### Multi-Layer Safety
1. **Devil's Advocate**: Critical validation of all decisions
2. **Trust Matrix**: Dynamic trust management
3. **Consensus Engine**: Multi-agent approval system
4. **Rollback Engine**: Automatic recovery capabilities
5. **Error Trap**: Comprehensive error handling

### Safety Validation Process
```python
# 1. Safety Review
safety_result = guardian.safety.review_mutation([code])

# 2. Trust Validation
trust_valid = guardian.trust.validate_trust_for_action("mutation_engine", "mutation")

# 3. Consensus Voting
guardian.consensus.cast_vote("mutation_engine", "approve_mutation", 0.8)
decision = guardian.consensus.decide("approve_mutation")

# 4. Apply if approved
if decision == "approve_mutation":
    result = guardian.mutation.propose_mutation(filename, code)
```

## 🎨 Creativity System

### Dream Engine
The Dream Engine provides creative thinking and inspiration:

```python
# Generate creative thoughts
dreams = guardian.dreams.begin_dream_cycle(3)

# Get creative statistics
stats = guardian.dreams.get_dream_stats()
print(f"Dream density: {stats['dream_density']:.2f}")

# Get creative summary
summary = guardian.dreams.get_creative_summary()
```

### Context Building
Intelligent context retrieval and analysis:

```python
# Build context from memories
context = guardian.context.build_context_by_keyword("safety")
context = guardian.context.build_recent_context(minutes=120)
context = guardian.context.build_context_by_tag("error")
```

## 🌐 External Interactions

### Web Reader
Fetch and analyze web content:

```python
# Fetch content from URL
content = guardian.web_reader.fetch("https://example.com", max_length=1000)

# Get web statistics
stats = guardian.web_reader.get_web_stats()
print(f"Total fetches: {stats['total_fetches']}")
```

### Voice Thread
Text-to-speech with personality modes:

```python
# Available modes: warm_guide, sharp_analyst, poetic_oracle, guardian
guardian.voice.set_mode("guardian")
guardian.voice.speak("System is ready to protect")

# Get voice statistics
stats = guardian.voice.get_voice_stats()
print(f"Current mode: {stats['current_mode']}")
```

### AI Interaction
ChatGPT integration for AI assistance:

```python
# Ask AI a question
response = guardian.ai_interaction.ask_chatgpt("What is AI safety?")

# Get AI advice with context
advice = guardian.ai_interaction.get_ai_advice(
    context="System has low trust levels",
    question="How to improve trust?"
)

# Get AI statistics
stats = guardian.ai_interaction.get_ai_stats()
print(f"Interactions: {stats['interaction_count']}")
```

## 🎯 Mission Management

### Mission Director
Goal-oriented task management:

```python
# Create mission with deadline
from datetime import datetime, timedelta
deadline = datetime.now() + timedelta(hours=24)

mission = guardian.missions.create_mission(
    "Security Audit",
    "Comprehensive security analysis",
    priority="high",
    deadline=deadline
)

# Add subtasks
guardian.missions.add_subtask("Security Audit", "Check trust matrix", "high")
guardian.missions.add_subtask("Security Audit", "Validate protocols", "medium")

# Log progress
guardian.missions.log_progress("Security Audit", "Trust analysis complete", 0.5)

# Complete subtask
guardian.missions.complete_subtask("Security Audit", "Check trust matrix")

# Complete mission
guardian.missions.complete_mission("Security Audit", "Audit successful")

# Check deadlines
issues = guardian.missions.check_deadlines()
for issue in issues:
    print(f"⚠️  {issue['mission']}: {issue['issue']}")
```

### Mission Statistics
```python
stats = guardian.missions.get_mission_stats()
print(f"Active missions: {stats['active_missions']}")
print(f"Completion rate: {stats['completion_rate']:.1%}")

summary = guardian.missions.get_mission_summary()
print(summary)
```

## 📊 Monitoring & Analytics

### System Health
```python
# Get comprehensive status
status = guardian.get_system_status()

# Run safety check
safety = guardian.run_safety_check()

# Get system summary
summary = guardian.get_system_summary()
```

### Pattern Analysis
```python
# Find patterns in memory
patterns = guardian.memory_search.find_patterns("safety", hours=24)
print(f"Patterns found: {patterns['total_matches']}")
print(f"Average priority: {patterns['average_priority']:.2f}")
```

### Memory Analytics
```python
# Get memory statistics
stats = guardian.memory.get_memory_stats()
print(f"Total memories: {stats['total_memories']}")

# Search memories
results = guardian.memory_search.search(
    keyword="safety",
    since_minutes=60,
    limit=10
)
```

## 🔌 Plugin System

### Plugin Development
```python
from project_guardian import PluginLoader

# Create custom plugin
class CustomPlugin:
    def __init__(self, guardian):
        self.guardian = guardian
    
    def execute(self, data):
        # Plugin logic here
        return "Plugin executed"

# Load plugin
loader = PluginLoader(guardian)
loader.load_plugin("custom_plugin", CustomPlugin)
```

## 🚨 Error Handling

### Comprehensive Error Management
```python
# Error trap catches all exceptions
try:
    guardian.propose_mutation("test.py", "invalid code")
except Exception as e:
    # Error automatically logged to memory
    print("Error handled by Guardian system")

# Check for recent errors
errors = guardian.memory.get_memories_by_category("error")
for error in errors:
    print(f"Error: {error['thought']}")
```

## 📈 Performance Optimization

### Memory Management
```python
# Get memory statistics
stats = guardian.memory.get_memory_stats()
print(f"Memory usage: {stats['memory_usage']:.2f}")

# Clean old memories
guardian.memory.cleanup_old_memories(days=7)
```

### Task Optimization
```python
# Get task statistics
stats = guardian.tasks.get_task_stats()
print(f"Active tasks: {stats['active_tasks']}")

# Complete low-priority tasks
tasks = guardian.tasks.get_active_tasks()
for task in tasks:
    if task['priority'] < 0.3:
        guardian.tasks.complete_task(task['id'])
```

## 🔒 Security Considerations

### Trust Management
```python
# Update trust levels
guardian.trust.update_trust("mutation_engine", 0.1, "Successful operation")
guardian.trust.update_trust("safety_engine", -0.1, "Failed validation")

# Get trust report
report = guardian.trust.get_trust_report()
print(f"Average trust: {report['average_trust']:.2f}")

# Get low trust components
low_trust = guardian.trust.get_low_trust_components()
print(f"Low trust: {low_trust}")
```

### Consensus Validation
```python
# Cast votes
guardian.consensus.cast_vote("safety_engine", "approve_action", 0.9, "Safety validated")
guardian.consensus.cast_vote("trust_matrix", "approve_action", 0.7, "Trust sufficient")

# Get decision
decision = guardian.consensus.decide("approve_action")
print(f"Decision: {decision}")
```

## 🎯 Best Practices

### 1. Safety First
- Always run safety checks before mutations
- Monitor trust levels regularly
- Use consensus for critical decisions

### 2. Memory Management
- Clean up old memories periodically
- Use appropriate categories for memories
- Monitor memory usage

### 3. Mission Planning
- Set realistic deadlines
- Break complex missions into subtasks
- Monitor progress regularly

### 4. External Interactions
- Validate web content before processing
- Use appropriate voice modes for context
- Handle AI responses carefully

### 5. Monitoring
- Run regular health checks
- Monitor pattern recognition
- Track system performance

## 🚀 Advanced Features

### Creative AI Integration
```python
# Combine dreams with AI assistance
dreams = guardian.begin_dream_cycle(2)
for dream in dreams:
    response = guardian.ask_ai(f"Analyze this dream: {dream}")
    print(f"AI Analysis: {response}")
```

### Web-Enhanced Context
```python
# Fetch web content and build context
content = guardian.fetch_web_content("https://ai-safety.org")
guardian.memory.remember(f"Web content: {content[:200]}...", category="external")

# Use web content in context
context = guardian.get_context(keyword="AI safety")
```

### Voice-Enhanced Monitoring
```python
# Speak system status
status = guardian.get_system_status()
guardian.speak_message(f"System status: {status['active_components']} components active")

# Voice alerts for issues
issues = guardian.missions.check_deadlines()
if issues:
    guardian.speak_message(f"Warning: {len(issues)} deadline issues detected", "sharp_analyst")
```

## 📚 API Reference

### GuardianCore Methods
- `begin_dream_cycle(cycles)`: Start creative thinking
- `fetch_web_content(url)`: Fetch web content
- `speak_message(message, mode)`: Speak with personality
- `ask_ai(question)`: Ask AI for assistance
- `create_mission(name, goal, priority)`: Create mission
- `get_context(keyword, tag, minutes)`: Get context
- `propose_mutation(filename, code)`: Safe code mutation
- `run_safety_check()`: Comprehensive safety check
- `get_system_status()`: System status
- `shutdown()`: Safe shutdown

### Component Access
- `guardian.memory`: Memory management
- `guardian.mutation`: Code evolution
- `guardian.safety`: Safety validation
- `guardian.trust`: Trust management
- `guardian.tasks`: Task management
- `guardian.consensus`: Decision making
- `guardian.dreams`: Creative thinking
- `guardian.web_reader`: Web content
- `guardian.voice`: Voice synthesis
- `guardian.ai_interaction`: AI assistance
- `guardian.missions`: Mission management
- `guardian.context`: Context building
- `guardian.memory_search`: Memory search

## 🤝 Contributing

Project Guardian is designed for extensibility. Key areas for contribution:

1. **Safety Protocols**: Enhanced safety validation
2. **Creative Algorithms**: Improved dream generation
3. **External Integrations**: Additional web/API connectors
4. **Voice Modes**: New personality types
5. **Mission Templates**: Predefined mission types
6. **Plugin Ecosystem**: Community plugins

## 📄 License

Project Guardian is released under the MIT License. See LICENSE file for details.

## 🆘 Support

For support, issues, or feature requests:
- Create an issue on the repository
- Check the documentation
- Review the example scripts

---

**🛡️ Project Guardian: Protecting AI, Empowering Humanity** 