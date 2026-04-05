# Elysia: Module Integration & Internet Learning Guide

## 🔌 How Modules Are Called Up

Elysia uses a **sophisticated modular architecture** with two approaches:

### 1. **Architect-Core Module Orchestration** (From ChatGPT Conversations)

According to the ChatGPT conversations, Elysia uses **Architect-Core** which orchestrates modules through a **contract-based system**:

```python
# Modules are registered with contracts
type ModuleSpec = {
    id: NodeId
    name: string
    version: string
    contract: Contract  # Defines inputs, outputs, invariants
    deps: NodeId[]
}

# Modules expose interfaces
exposed_interfaces:
  - authenticate_user
  - get_persona_profile
  - evaluate_output_risk
  - generate_dream
  - speak
  # etc.

# Architect-Core routes intents to modules
type Intent = {
    id: string
    kind: string
    payload: any
    priority: number
    actor: string
}

# Routing logic:
# - Loads config from elysia.config.yaml
# - Dynamically imports module entrypoints
# - Composes dependency graph
# - Routes intents based on priority, TrustEngine score, and backpressure
# - Enforces contract invariants pre/post execution
```

**Architect-Core Implementation** (from codebase):
```python
from core.architect_core import ArchitectCore

architect = ArchitectCore()

# Route commands to modules
result = architect.route_command(
    target="modules",  # or "mutations", "policies", "persona"
    command="register_module",
    data={"module_name": "MyModule", "module_type": "Custom"}
)

# Get status of all architects
status = architect.get_status_report()
```

**Module Registry System**:
- Modules are registered via `ModuleArchitect`
- Each module has a registry entry with dependencies and exposed interfaces
- Architect-Core maintains a registry mapping module names to handlers
- Commands are routed through `route_command()` method

### 2. **Current Codebase Approach** (Adapter Pattern)

The current codebase uses adapters with **ElysiaLoop-Core** for task scheduling:

```python
# Example: Using Enhanced Elysia Core Adapter
from src.core.adapters.enhanced_elysia_core_adapter import EnhancedElysiaCoreAdapter

adapter = EnhancedElysiaCoreAdapter()

# Call a module method
result = adapter.execute("read_web", {"url": "https://example.com"})
result = adapter.execute("get_memory", {"query": "AI"})
result = adapter.execute("dream", {"cycles": 5})
result = adapter.execute("speak", {"message": "Hello"})
```

**ElysiaLoop-Core Task Execution** (from ChatGPT conversations):

ElysiaLoop-Core uses a **priority-based task queue** with async execution:

```python
# Task structure
class Task:
    def __init__(self, source: str, task_type: str, priority_score: float,
                 scheduled_time: datetime.datetime, dependencies: List[str], payload: dict):
        self.id = str(uuid.uuid4())
        self.source = source  # Module name (e.g., "DreamCore", "UIControlPanel")
        self.task_type = task_type  # Method to call
        self.priority_score = priority_score  # Higher = more urgent
        self.scheduled_time = scheduled_time
        self.dependencies = dependencies  # Other task IDs that must complete first
        self.status = TaskStatus.PENDING
        self.payload = payload  # Arguments for the module method

# Module adapters are registered in ModuleRegistry
ModuleRegistry.register("DreamCore", DreamCoreAdapter())
ModuleRegistry.register("TrustEngine", TrustEngineAdapter())
ModuleRegistry.register("UIControlPanel", UIControlPanelAdapter())

# Tasks are executed through the event loop
# The loop routes tasks to the correct adapter based on task.source
# Each adapter implements execute(method: str, payload: dict) -> dict
```

**How Module Routing Works**:
1. Task is created with `source` field specifying the module name
2. ElysiaLoop-Core's event loop pulls tasks from priority queue
3. Loop resolves the adapter from `ModuleRegistry` using `task.source`
4. Calls `adapter.execute(task.task_type, task.payload)`
5. Result is logged and task status updated

### 3. **Core Modules** (From ChatGPT Conversations)

According to the conversations, Elysia has **9 core modules**:

1. **Architect-Core** - System architect and orchestrator
2. **ElysiaLoop-Core** - Work-Dream scheduler
3. **IdentityAnchor** - Immutable identity root and signing
4. **TrustEngine** - Risk scoring and guardrails
5. **ReputationEngine** - Actor reputation tracking
6. **MutationFlow** - Persona and code mutation management
7. **VoicePersona** - Controlled output style and tone
8. **UIControlPanel** - Operator console for human oversight
9. **ThreadWeaver** - Conversation and task threading

Each module has:
- **Dependencies**: Other modules it depends on
- **Exposed Interfaces**: Methods it exposes to other modules
- **Contracts**: Input/output specifications and invariants

### 4. **Available Module Methods** (Current Implementation)

Elysia provides these module methods:

#### **Core Operations:**
- `get_status` - Get system status
- `start_runtime` - Start runtime loop
- `speak` - Generate speech/output
- `dream` - Run dream cycle
- `mutate` - System mutation
- `reflect` - Reflection process
- `evolve` - Evolution process

#### **Memory Operations:**
- `get_memory` - Retrieve memory
- `search_memory` - Search memories
- `build_context` - Build context from memories

#### **Web & External:**
- `read_web` - Read web pages
- `ask_external` - Query external APIs
- `integrate_module` - Integrate new modules

#### **System Operations:**
- `get_trust` - Get trust evaluation
- `get_mission` - Get mission status
- `get_ranking` - Get rankings
- `get_introspection` - Get introspection data
- `get_consensus` - Get consensus
- `get_heartbeat` - Get heartbeat
- `get_sync` - Get sync status
- `get_feedback` - Get feedback
- `get_registry` - Get module registry
- `get_plugins` - Get plugins

### 5. **Module Integration System**

Modules can be integrated dynamically:

```python
# Integrate a new module
result = adapter.execute("integrate_module", {
    "module_name": "MyModule",
    "module_type": "Custom",
    "methods": ["method1", "method2"]
})
```

### 6. **Module Registry**

Elysia maintains a registry of available modules:

```python
# Get all registered modules
modules = adapter.execute("get_registry", {})

# Get available plugins
plugins = adapter.execute("get_plugins", {})
```

### 7. **Module Configuration** (From Conversations)

Modules are configured in `elysia.config.yaml`:

```yaml
modules:
  - name: ArchitectCore
    entrypoint: "modules/ArchitectCore/main.py"
  - name: ElysiaLoopCore
    entrypoint: "modules/ElysiaLoopCore/loop.py"
  - name: IdentityAnchor
    entrypoint: "modules/IdentityAnchor/main.py"
  # ... etc
```

**Module Adapter Pattern** (from ElysiaLoop-Core conversations):

All modules implement `BaseModuleAdapter`:

```python
class BaseModuleAdapter:
    def __init__(self, module_name: str):
        self.module_name = module_name
    
    def execute(self, method: str, payload: dict) -> dict:
        """Must be implemented by each module"""
        raise NotImplementedError

# Example: DreamCore adapter
class DreamCoreAdapter(BaseModuleAdapter):
    def execute(self, method: str, payload: dict) -> dict:
        if method == "generate_dream":
            # Call DreamCore's generate_dream method
            return {"dream": "...", "error": None}
        return {"error": f"Unknown method '{method}'"}

# Example: TrustEngine adapter
class TrustEngineAdapter(BaseModuleAdapter):
    def execute(self, method: str, payload: dict) -> dict:
        if method == "evaluateContent":
            # Evaluate content for trust/risk
            return {"score": 0.95, "flags": [], "error": None}
        return {"error": f"Unknown method '{method}'"}
```

**Task Execution Flow**:
1. **Task Creation**: Task created with `source="DreamCore"`, `task_type="generate_dream"`, `payload={...}`
2. **Queue**: Task added to `GlobalTaskQueue` (priority heap)
3. **Scheduling**: ElysiaLoop-Core event loop pulls ready tasks (dependencies met, scheduled time reached)
4. **Routing**: Loop looks up `ModuleRegistry.get(task.source)` to get adapter
5. **Execution**: Calls `adapter.execute(task.task_type, task.payload)` asynchronously with timeout
6. **Completion**: Result logged, task status updated, dependent tasks may be unblocked

### 8. **Using Modules from Chat Interface**

You can call modules from the chat interface by extending `chat_with_elysia.py`:

```python
# In chat_with_elysia.py, add module calls:
if message_lower.startswith('read web '):
    url = message[9:].strip()
    result = adapter.execute("read_web", {"url": url})
    return f"Elysia: {result.get('data', 'Read web page')}"
```

---

---

## 🌐 How Elysia Learns from the Internet

**Note**: According to the ChatGPT conversations, there's a TODO item: **"Add rate-limited external connectors under TrustEngine supervision"** - This suggests internet learning should be integrated with the TrustEngine for safety.

**Integration with ElysiaLoop-Core** (from conversations):

Internet learning can be scheduled as tasks:

```python
# Create a learning task
learning_task = Task(
    source="OnlineLearningSystem",
    task_type="learn_from_web",
    priority_score=0.5,  # Medium priority
    scheduled_time=datetime.now(),
    dependencies=[],
    payload={
        "sources": ["https://news.ycombinator.com/"],
        "max_articles": 10
    }
)

# Add to ElysiaLoop-Core queue
elysia_loop.queue.enqueue_task(learning_task)

# TrustEngine can evaluate learning tasks before execution
trust_result = trust_engine.evaluate_action({
    "action": "learn_from_web",
    "sources": learning_task.payload["sources"]
})
if trust_result["score"] > 0.65:  # Deny threshold
    # Task requires human review
    pass
```

Elysia has **comprehensive internet learning capabilities** built-in!

### 1. **Online Learning System**

The main system is `OnlineLearningSystem`:

```python
from src.learning.web.online_learning_system import OnlineLearningSystem

# Initialize with memory system
learning_system = OnlineLearningSystem(memory_system=your_memory_system)

# Learn from web sources
result = await learning_system.learn_from_web(
    sources=["https://news.ycombinator.com/"],
    max_articles=10
)
```

### 2. **Pre-configured Learning Sources**

Elysia comes with pre-configured sources:

#### **News Sites:**
- Hacker News
- The Verge
- TechCrunch
- Ars Technica

#### **AI News:**
- OpenAI Blog
- Google AI Blog
- LessWrong
- Scott Aaronson's Blog

#### **Finance Sites:**
- Seeking Alpha
- CoinDesk
- Bloomberg
- Reuters

#### **Science Sites:**
- arXiv (AI papers)
- Aeon
- Nature
- Science

#### **RSS Feeds:**
- TechCrunch RSS
- CNN RSS
- BBC News RSS
- Reddit RSS feeds

### 3. **Learning Methods**

#### **Web Learning:**
```python
# Learn from web pages
result = await learning_system.learn_from_web(
    sources=["https://example.com"],
    max_articles=10
)
```

#### **RSS Feed Learning:**
```python
# Learn from RSS feeds
result = await learning_system.learn_from_rss_feeds(
    feed_urls=["https://feeds.feedburner.com/TechCrunch/"]
)
```

#### **Social Media Learning:**
```python
# Learn from Reddit (no API key needed)
from src.learning.web.social_media_integration import SocialMediaIntegration

social = SocialMediaIntegration()
result = social.learn_from_reddit("MachineLearning", max_posts=10)

# Learn from Hacker News
result = social.learn_from_hackernews(max_posts=10)
```

### 4. **How Learning Works**

1. **Fetch**: Elysia fetches content from sources
2. **Parse**: Extracts text and metadata using BeautifulSoup
3. **Filter**: Filters out ads, spam, and low-quality content
4. **Process**: Analyzes and categorizes content
5. **Store**: Saves to memory system with tags and associations
6. **Learn**: Builds knowledge patterns and connections

### 5. **Running Internet Learning**

#### **Quick Start:**
```bash
python run_internet_learning.py
```

#### **From Code:**
```python
import asyncio
from src.learning.web.online_learning_system import OnlineLearningSystem

async def learn():
    learning_system = OnlineLearningSystem()
    
    # Learn from multiple sources
    await learning_system.learn_from_web(
        sources=learning_system.learning_sources["news_sites"],
        max_articles=5
    )
    
    # Get statistics
    stats = learning_system.get_learning_statistics()
    print(f"Articles processed: {stats['articles_processed']}")

asyncio.run(learn())
```

### 6. **Learning Statistics**

Track what Elysia has learned:

```python
stats = learning_system.get_learning_statistics()
# Returns:
# - total_sources_processed
# - total_articles_fetched
# - total_knowledge_stored
# - learning_sessions
# - last_learning_session
```

### 7. **Content Filtering**

Configure what Elysia learns:

```python
filters = {
    "min_content_length": 100,
    "max_content_length": 10000,
    "required_keywords": ["AI", "technology"],
    "excluded_keywords": ["spam", "advertisement"]
}

learning_system.configure_content_filters(filters)
```

### 8. **Integration with Chat Interface**

You can add internet learning to the chat:

```python
# In chat_with_elysia.py
if message_lower.startswith('learn from '):
    source = message[11:].strip()
    result = await learning_system.learn_from_web([source])
    return f"Elysia: Learned from {source}! Processed {result['data']['articles_processed']} articles."
```

---

## 🎯 Practical Examples

### Example 1: Call a Module from Chat

```python
# Add to chat_with_elysia.py
from src.core.adapters.enhanced_elysia_core_adapter import EnhancedElysiaCoreAdapter

class ElysiaChat:
    def __init__(self):
        # ... existing code ...
        self.adapter = EnhancedElysiaCoreAdapter()
    
    def process_message(self, message):
        # ... existing code ...
        
        if message_lower.startswith('read '):
            url = message[5:].strip()
            result = self.adapter.execute("read_web", {"url": url})
            return f"Elysia: {result.get('data', 'Read the web page')}"
```

### Example 2: Enable Internet Learning

```python
# Add to chat_with_elysia.py
import asyncio
from src.learning.web.online_learning_system import OnlineLearningSystem

class ElysiaChat:
    def __init__(self):
        # ... existing code ...
        self.learning_system = OnlineLearningSystem(memory_system=self.core.memory)
    
    async def learn_from_internet(self):
        """Background task to learn from internet"""
        while True:
            await self.learning_system.learn_from_web(max_articles=5)
            await asyncio.sleep(3600)  # Learn every hour
```

### Example 3: Get Module Status

```python
# Check what modules are available
adapter = EnhancedElysiaCoreAdapter()
status = adapter.execute("get_status", {})
print(status["data"]["core_systems"])
print(status["data"]["subsystems"])
print(status["data"]["advanced_systems"])
```

---

## 📚 Key Files

- **Module Adapters**: `src/core/adapters/enhanced_elysia_core_adapter.py`
- **Online Learning**: `src/learning/web/online_learning_system.py`
- **Social Media**: `src/learning/web/social_media_integration.py`
- **Web Reader**: `elysia_core/web_reader.py`
- **Run Learning**: `run_internet_learning.py`

---

## 🚀 Quick Commands

**Start Internet Learning:**
```bash
python run_internet_learning.py
```

**Check Module Status:**
```python
python -c "from src.core.adapters.enhanced_elysia_core_adapter import EnhancedElysiaCoreAdapter; a = EnhancedElysiaCoreAdapter(); print(a.execute('get_status', {}))"
```

**Learn from Specific Source:**
```python
from src.learning.web.online_learning_system import OnlineLearningSystem
import asyncio

ls = OnlineLearningSystem()
asyncio.run(ls.learn_from_web(["https://news.ycombinator.com/"]))
```

---

## 💡 Tips

1. **Modules are lazy-loaded**: They initialize when first called
2. **Internet learning is async**: Use `await` or `asyncio.run()`
3. **Memory integration**: Connect learning system to memory for storage
4. **Rate limiting**: Be respectful of web sources
5. **Content filtering**: Configure filters to avoid spam/ads
6. **Statistics**: Track learning progress with statistics

---

**Status**: ✅ Modules can be called via adapters  
**Status**: ✅ Internet learning is fully functional  
**Status**: ✅ Pre-configured sources available  
**Status**: ✅ Memory integration ready

