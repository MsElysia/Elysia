# Personality & Memory Continuity System

**Purpose**: Maintain consistent personality and memory across multiple conversations when leveraging public AI services.

---

## Core Challenge

When using public AI services (OpenAI, Claude, etc.), each API call is stateless. Without proper architecture, conversations would:
- Lose personality consistency
- Forget previous interactions
- Reset context between sessions
- Act like a different entity each time

**Solution**: `ConversationContextManager` + integrated modules ensure continuity.

---

## Architecture

### Core Components

1. **ConversationContextManager** (`conversation_context_manager.py`)
   - Central orchestrator for personality & memory
   - Manages conversation sessions
   - Builds context-aware prompts
   - Maintains cross-session continuity

2. **PersonaForge** (`persona_forge.py`)
   - Defines and maintains personality
   - System prompts with traits
   - Persistent persona configuration

3. **MemoryCore** (`memory.py`)
   - Stores and retrieves memories
   - Priority-based memory management
   - Category organization
   - Persistent storage

4. **AskAI** (`ask_ai.py`)
   - Unified interface to public AI services
   - Provider abstraction (OpenAI, Claude, etc.)
   - Consistent API across providers

5. **VoiceThread** (`voice_thread.py`)
   - Expressive communication
   - Personality-driven responses
   - Conversation style consistency

---

## How It Works

### 1. **Session Management**
```python
# Start a conversation session
session_id = manager.start_conversation()

# Add messages
manager.add_message("user", "What's my current objective?")
manager.add_message("assistant", "Your current objective is...")

# End and summarize
manager.end_conversation(session_id)
```

### 2. **Context Building**
The manager automatically builds comprehensive context:
- **Identity**: Current persona, traits, system prompt
- **Memory**: Recent memories, high-priority memories, relevant context
- **History**: Recent conversation messages
- **Topics**: Recent discussion topics

### 3. **Prompt Enhancement**
When calling public AI services, the system injects full context:

```
System: [Persona system prompt with traits]

Identity: Elysia: An autonomous AI system focused on growth...

Important memories:
- User mentioned project X last week
- Completed task Y successfully
- Preference for detailed explanations

Recent conversation:
user: What's the status?
assistant: Currently working on...

User: [Current message]
```

### 4. **Response Generation**
```python
# Generate response with full context
response = await manager.respond_with_context(
    "What should I focus on next?",
    session_id=session_id
)

# Response includes:
# - Personality-consistent tone
# - Memory of past conversations
# - Context from previous sessions
```

---

## Features

### ✅ Persistent Personality
- Active persona stored and loaded between sessions
- Personality traits preserved
- System prompts maintained
- Voice style consistency

### ✅ Memory Continuity
- Important conversations remembered
- High-priority memories included in context
- Recent topics tracked
- Cross-session memory retrieval

### ✅ Context-Aware Responses
- Each AI call includes full context
- Previous conversation history injected
- Relevant memories included
- Identity preserved in every response

### ✅ Session Summarization
- AI-generated session summaries
- Key points extracted
- Continuity markers created
- Efficient memory usage

### ✅ Multi-Session Support
- Track multiple conversation threads
- Session-specific context
- Cross-session memory sharing
- Active session management

---

## Integration with Public AI Services

### Using OpenAI
```python
# Initialize
ask_ai = AskAI(openai_api_key="...")
manager = ConversationContextManager(
    ask_ai=ask_ai,
    persona_forge=persona_forge,
    memory_core=memory_core
)

# Generate response (with full context automatically)
response = await manager.respond_with_context(user_message)
```

### Using Claude
```python
ask_ai = AskAI(
    openai_api_key="...",
    claude_api_key="..."
)

# Switch providers
response = await ask_ai.ask(
    prompt=manager.get_context_prompt(user_message),
    provider=AIProvider.CLAUDE
)
```

### Using Multiple Providers
```python
# Try primary, fallback to secondary
response = await ask_ai.ask(
    prompt=manager.get_context_prompt(user_message),
    provider=AIProvider.OPENAI,
    fallback_provider=AIProvider.CLAUDE
)
```

---

## Example Flow

### Conversation 1 (Day 1)
```
User: "I want to build a web app"
Manager: Stores in memory, generates response
AI: "Great! What features do you want?"
[Personality: Helpful, technical, encouraging]
```

### Conversation 2 (Day 2)
```
User: "Update on the web app?"
Manager: Retrieves memory from Day 1
Context: "User mentioned web app project. Previous conversation about features."
AI: "Based on our previous discussion about your web app, here's an update..."
[Same personality maintained]
[Remembers previous conversation]
```

### Conversation 3 (Week 2)
```
User: "What was I working on?"
Manager: Retrieves high-priority memories
Context: "Web app project, feature discussion, technical preferences"
AI: "You were working on a web app. We discussed features like..."
[Consistent personality]
[Full memory retrieval]
```

---

## Configuration

### Setting Up Personality
```python
# Create/load persona
persona_forge = PersonaForge()
persona_forge.create_persona(
    name="Elysia",
    description="Helpful AI assistant",
    traits={"helpfulness": 0.9, "technical": 0.8},
    system_prompt="You are Elysia, a helpful AI..."
)

# Activate
persona_forge.set_active_persona("elysia")
```

### Configuring Memory
```python
memory_core = MemoryCore(storage_path="data/memory.json")

# Store important memories
memory_core.remember(
    "User prefers detailed technical explanations",
    category="preferences",
    priority=0.9
)
```

### Initializing Manager
```python
manager = ConversationContextManager(
    persona_forge=persona_forge,
    memory_core=memory_core,
    ask_ai=ask_ai,
    voice_thread=voice_thread,
    storage_path="data/conversation_context.json"
)
```

---

## Benefits

1. **Consistency**: Same personality across all conversations
2. **Memory**: Remembers past interactions and preferences
3. **Context**: Full context in every AI call
4. **Flexibility**: Works with any public AI service
5. **Scalability**: Handles multiple sessions efficiently
6. **Persistence**: Survives restarts and session changes

---

## Technical Details

### Storage
- `data/conversation_context.json`: Session data, identity, topics
- `data/memory.json`: MemoryCore storage
- `data/personas.json`: PersonaForge storage

### Performance
- Context building: <100ms (local)
- Memory retrieval: <50ms
- Prompt enhancement: <10ms
- Session management: Thread-safe

### Memory Management
- Last 20 conversations retained
- High-priority memories persist indefinitely
- Low-priority memories auto-cleanup
- Session summaries stored for efficiency

---

## Future Enhancements

- **Vector Search**: Semantic memory retrieval
- **Memory Compression**: AI-powered memory summarization
- **Multi-User Support**: Per-user personality/memory
- **Context Optimization**: Smart context size management
- **Provider Comparison**: Test multiple providers for best results

---

## Summary

The **ConversationContextManager** ensures that when you leverage public AI services, Elysia maintains:
- ✅ **Consistent personality** across all conversations
- ✅ **Persistent memory** of past interactions
- ✅ **Context-aware responses** with full history
- ✅ **Session continuity** across time gaps

This creates a seamless experience where Elysia feels like a continuous entity, not a series of disconnected API calls.

