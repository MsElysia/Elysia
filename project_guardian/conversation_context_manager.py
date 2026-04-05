# project_guardian/conversation_context_manager.py
# ConversationContextManager: Maintain Consistent Personality & Memory Across Conversations
# Core requirement for leveraging public AI services with persistent identity

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from dataclasses import dataclass, field
import uuid

try:
    from .persona_forge import PersonaForge
    from .memory import MemoryCore
    from .ask_ai import AskAI, AIProvider
    from .voice_thread import VoiceThread
except ImportError:
    from persona_forge import PersonaForge
    from memory import MemoryCore
    from ask_ai import AskAI, AIProvider
    from voice_thread import VoiceThread

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """Represents a conversation session."""
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "messages": self.messages,
            "context_summary": self.context_summary,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSession":
        """Create ConversationSession from dictionary."""
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            messages=data.get("messages", []),
            context_summary=data.get("context_summary"),
            metadata=data.get("metadata", {})
        )


class ConversationContextManager:
    """
    Maintains consistent personality and memory across multiple conversations.
    Integrates PersonaForge (personality) and MemoryCore (memory) to provide
    persistent context when leveraging public AI services.
    """
    
    def __init__(
        self,
        persona_forge: Optional[PersonaForge] = None,
        memory_core: Optional[MemoryCore] = None,
        ask_ai: Optional[AskAI] = None,
        voice_thread: Optional[VoiceThread] = None,
        storage_path: str = "data/conversation_context.json"
    ):
        self.persona_forge = persona_forge or PersonaForge()
        self.memory_core = memory_core or MemoryCore()
        self.ask_ai = ask_ai
        self.voice_thread = voice_thread
        self.storage_path = Path(storage_path)
        # Create directory lazily - don't block on directory creation
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directory {self.storage_path.parent}: {e}")
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Conversation sessions
        self.sessions: Dict[str, ConversationSession] = {}
        self.active_session_id: Optional[str] = None
        
        # Persistent identity & context
        self.identity_summary: Optional[str] = None
        self.memory_context: List[str] = []  # Key memories for context
        self.personality_traits: Dict[str, float] = {}
        
        # Conversation continuity data
        self.conversation_history_summary: Optional[str] = None
        self.recent_topics: List[str] = []
        
        # Load on first access to avoid blocking initialization
        self._loaded = False
        # Skip loading during init - will load on first access
        # self._ensure_loaded()
        
        # Skip identity initialization during init - will do on first access
        # if not self.identity_summary:
        #     self._initialize_identity()
    
    def _initialize_identity(self):
        """Initialize persistent identity summary."""
        active_persona = self.persona_forge.get_active_persona()
        if active_persona:
            self.identity_summary = f"{active_persona.name}: {active_persona.description}"
            self.personality_traits = active_persona.traits.copy()
        else:
            self.identity_summary = "Elysia: An autonomous AI system focused on growth and self-improvement"
    
    def start_conversation(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a new conversation session.
        
        Args:
            session_id: Optional custom session ID
            metadata: Optional session metadata
            
        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        session = ConversationSession(
            session_id=session_id,
            started_at=datetime.now(),
            metadata=metadata or {}
        )
        
        with self._lock:
            self.sessions[session_id] = session
            self.active_session_id = session_id
            self.save()
        
        logger.info(f"Started conversation session: {session_id}")
        return session_id
    
    def end_conversation(self, session_id: Optional[str] = None):
        """End a conversation session and generate summary."""
        sid = session_id or self.active_session_id
        if not sid:
            return
        
        session = self.sessions.get(sid)
        if not session:
            return
        
        session.ended_at = datetime.now()
        
        # Generate context summary for continuity
        if self.ask_ai and session.messages:
            try:
                import asyncio
                summary = asyncio.run(self._generate_session_summary(session))
                session.context_summary = summary
                
                # Store key points in memory
                self.memory_core.remember(
                    f"Conversation session {sid}: {summary[:100]}",
                    category="conversation",
                    priority=0.6
                )
            except Exception as e:
                logger.warning(f"Failed to generate session summary: {e}")
        
        with self._lock:
            self.save()
        
        # Clear active session if it's the one ending
        if sid == self.active_session_id:
            self.active_session_id = None
    
    async def _generate_session_summary(self, session: ConversationSession) -> str:
        """Generate a summary of conversation session for continuity."""
        if not self.ask_ai:
            return "Conversation session completed"
        
        # Collect conversation highlights
        messages_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
            for msg in session.messages[-10:]  # Last 10 messages
        ])
        
        prompt = f"""Summarize this conversation session in 2-3 sentences, focusing on key topics, decisions, and important information that should be remembered:

{messages_text}

Provide a concise summary for maintaining conversation continuity."""

        try:
            response = await self.ask_ai.ask(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.5,
                max_tokens=200
            )
            
            if response.success:
                return response.content.strip()
        except Exception as e:
            logger.error(f"Error generating session summary: {e}")
        
        return "Conversation session completed"
    
    def add_message(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Add a message to the current conversation.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            session_id: Optional session ID (defaults to active)
            metadata: Optional message metadata
        """
        sid = session_id or self.active_session_id
        if not sid:
            # Auto-start session
            sid = self.start_conversation()
        
        session = self.sessions.get(sid)
        if not session:
            session = ConversationSession(session_id=sid, started_at=datetime.now())
            self.sessions[sid] = session
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        session.messages.append(message)
        
        # Store important messages in memory
        if role == "user" and len(content) > 20:
            self.memory_core.remember(
                f"User said: {content[:200]}",
                category="conversation",
                priority=0.7
            )
        
        self.save()
    
    def get_conversation_context(
        self,
        include_history: bool = True,
        include_identity: bool = True,
        include_memory: bool = True,
        max_history_messages: int = 20
    ) -> Dict[str, Any]:
        """
        Get full conversation context for maintaining continuity.
        
        Args:
            include_history: Include recent conversation history
            include_identity: Include personality/identity summary
            include_memory: Include relevant memories
            
        Returns:
            Context dictionary
        """
        context = {}
        
        # Identity & Personality
        if include_identity:
            active_persona = self.persona_forge.get_active_persona()
            context["identity"] = {
                "summary": self.identity_summary,
                "persona": active_persona.name if active_persona else None,
                "traits": self.personality_traits,
                "system_prompt": active_persona.system_prompt if active_persona else None
            }
        
        # Conversation History
        if include_history and self.active_session_id:
            session = self.sessions.get(self.active_session_id)
            if session:
                context["conversation_history"] = session.messages[-max_history_messages:]
                context["session_summary"] = session.context_summary
        
        # Relevant Memories
        if include_memory:
            # Get recent memories relevant to conversation
            recent_memories = self.memory_core.recall_last(count=10, category="conversation")
            context["relevant_memories"] = [
                {
                    "thought": mem.get("thought", ""),
                    "timestamp": mem.get("time", ""),
                    "priority": mem.get("priority", 0.5)
                }
                for mem in recent_memories
            ]
            
            # Get high-priority memories (bounded, no dump_all)
            recent = []
            if hasattr(self.memory_core, "get_recent_memories"):
                recent = self.memory_core.get_recent_memories(limit=100, load_if_needed=True)
            high_priority = [
                mem for mem in recent
                if mem.get("priority", 0) > 0.7
            ][-5:]
            context["important_memories"] = [
                {
                    "thought": mem.get("thought", ""),
                    "category": mem.get("category", ""),
                    "timestamp": mem.get("time", "")
                }
                for mem in high_priority
            ]
        
        # Recent topics
        if self.recent_topics:
            context["recent_topics"] = self.recent_topics[-5:]
        
        return context
    
    def get_context_prompt(
        self,
        user_message: str,
        include_system_context: bool = True
    ) -> str:
        """
        Build a comprehensive prompt with full context for AI services.
        This ensures personality and memory continuity across conversations.
        
        Args:
            user_message: Current user message
            include_system_context: Include system/identity context
            
        Returns:
            Enhanced prompt with full context
        """
        context = self.get_conversation_context()
        
        # Build context prompt
        context_parts = []
        
        # Identity & Personality
        if include_system_context and context.get("identity"):
            identity = context["identity"]
            if identity.get("system_prompt"):
                context_parts.append(f"System: {identity['system_prompt']}")
            elif identity.get("summary"):
                context_parts.append(f"Identity: {identity['summary']}")
        
        # Important memories
        if context.get("important_memories"):
            memories_text = "\n".join([
                f"- {mem['thought'][:150]}"
                for mem in context["important_memories"]
            ])
            context_parts.append(f"Important memories:\n{memories_text}")
        
        # Conversation history
        if context.get("conversation_history"):
            history_text = "\n".join([
                f"{msg['role']}: {msg['content'][:200]}"
                for msg in context["conversation_history"][-5:]  # Last 5 messages
            ])
            context_parts.append(f"Recent conversation:\n{history_text}")
        
        # Current message
        context_parts.append(f"User: {user_message}")
        
        return "\n\n".join(context_parts)
    
    async def respond_with_context(
        self,
        user_message: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Generate a response using AI with full context (personality + memory).
        
        Args:
            user_message: User's message
            session_id: Optional session ID
            
        Returns:
            AI-generated response with personality and memory context
        """
        if not self.ask_ai:
            return "AI service not available"
        
        # Add user message to conversation
        self.add_message("user", user_message, session_id)
        
        # Build context-aware prompt
        enhanced_prompt = self.get_context_prompt(user_message)
        
        # Get active persona for system prompt
        active_persona = self.persona_forge.get_active_persona()
        system_prompt = active_persona.system_prompt if active_persona else None
        
        # Generate response with AI
        try:
            response = await self.ask_ai.ask(
                prompt=enhanced_prompt,
                provider=AIProvider.OPENAI,
                system_prompt=system_prompt,
                temperature=0.7
            )
            
            if response.success:
                assistant_response = response.content
                
                # Add response to conversation
                self.add_message("assistant", assistant_response, session_id)
                
                # Remember the interaction
                self.memory_core.remember(
                    f"Conversation: User asked about {user_message[:50]}. I responded with {assistant_response[:100]}",
                    category="conversation",
                    priority=0.6
                )
                
                return assistant_response
            else:
                return f"Error: {response.error}"
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I encountered an error processing your message."
    
    def update_personality(self, persona_id: str) -> bool:
        """
        Update active personality while maintaining conversation continuity.
        
        Args:
            persona_id: Persona ID to activate
            
        Returns:
            True if successful
        """
        success = self.persona_forge.set_active_persona(persona_id)
        
        if success:
            active_persona = self.persona_forge.get_active_persona()
            if active_persona:
                # Update identity summary
                self.identity_summary = f"{active_persona.name}: {active_persona.description}"
                self.personality_traits = active_persona.traits.copy()
                self.save()
        
        return success
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a conversation session."""
        return self.sessions.get(session_id)
    
    def list_sessions(self, limit: int = 50) -> List[ConversationSession]:
        """List recent conversation sessions."""
        with self._lock:
            sessions = sorted(
                self.sessions.values(),
                key=lambda s: s.started_at,
                reverse=True
            )
            return sessions[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get conversation context statistics."""
        with self._lock:
            total_sessions = len(self.sessions)
            active_sessions = len([s for s in self.sessions.values() if not s.ended_at])
            total_messages = sum(len(s.messages) for s in self.sessions.values())
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "total_messages": total_messages,
                "identity_configured": bool(self.identity_summary),
                "active_persona": self.persona_forge.get_active_persona().name if self.persona_forge.get_active_persona() else None,
                "memory_count": (self.memory_core.get_memory_count(load_if_needed=False) or 0) if hasattr(self.memory_core, "get_memory_count") else 0
            }
    
    def save(self):
        """Save conversation context."""
        with self._lock:
            data = {
                "sessions": {
                    sid: session.to_dict()
                    for sid, session in self.sessions.items()
                },
                "active_session_id": self.active_session_id,
                "identity_summary": self.identity_summary,
                "personality_traits": self.personality_traits,
                "recent_topics": self.recent_topics[-20:],  # Last 20
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def _ensure_loaded(self):
        """Ensure conversation context is loaded (lazy loading)."""
        if self._loaded:
            return
        
        self._loaded = True
        
        try:
            if not self.storage_path.exists():
                logger.debug("Conversation context file does not exist")
                return
            
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self._lock:
                # Load sessions
                for sid, session_data in data.get("sessions", {}).items():
                    session = ConversationSession.from_dict(session_data)
                    self.sessions[sid] = session
                
                self.active_session_id = data.get("active_session_id")
                self.identity_summary = data.get("identity_summary")
                self.personality_traits = data.get("personality_traits", {})
                self.recent_topics = data.get("recent_topics", [])
            
            logger.info(f"Loaded {len(self.sessions)} conversation sessions")
        except Exception as e:
            logger.error(f"Error loading conversation context: {e}")
            # Don't block on errors
    
    def load(self):
        """Load conversation context from disk (for backward compatibility)."""
        self._ensure_loaded()


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_conversation_context():
        """Test the ConversationContextManager."""
        manager = ConversationContextManager()
        
        # Start conversation
        session_id = manager.start_conversation()
        
        # Add messages
        manager.add_message("user", "Hello, what's my current objective?")
        
        # Get context
        context = manager.get_conversation_context()
        print(f"Context: {context.keys()}")
        
        # Get statistics
        stats = manager.get_statistics()
        print(f"Statistics: {stats}")
        
        # End conversation
        manager.end_conversation(session_id)
    
    asyncio.run(test_conversation_context())

