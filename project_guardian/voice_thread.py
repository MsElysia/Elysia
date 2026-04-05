# project_guardian/voice_thread.py
# VoiceThread: Expressive Voice System with AI Integration
# Based on elysia 4 (Main Consolidation) and Part 3 designs

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from threading import Lock

try:
    from .persona_forge import PersonaForge
    from .ask_ai import AskAI, AIProvider
    from .trust_registry import TrustRegistry
except ImportError:
    from persona_forge import PersonaForge
    from ask_ai import AskAI, AIProvider
    from trust_registry import TrustRegistry

logger = logging.getLogger(__name__)


class VoiceThread:
    """
    Expressive voice system with boot messages, dream narration, trust expression.
    Integrates PersonaForge for personality and AskAI for generation.
    """
    
    def __init__(
        self,
        persona_forge: Optional[PersonaForge] = None,
        ask_ai: Optional[AskAI] = None,
        trust_registry: Optional[TrustRegistry] = None,
        storage_path: str = "data/voice_thread.json",
        prompt_evolver: Optional[Any] = None,
    ):
        self.persona_forge = persona_forge or PersonaForge()
        self.ask_ai = ask_ai
        self.trust_registry = trust_registry
        self.prompt_evolver = prompt_evolver
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Voice history
        self.voice_history: List[Dict[str, Any]] = []
        
        # Internal monologue (private thoughts)
        self.internal_monologue: List[Dict[str, Any]] = []
        
        # Boot message cache
        self.boot_message: Optional[str] = None
        
        self.load()
    
    async def generate_boot_message(self) -> str:
        """
        Generate a boot/startup message with personality.
        Uses AI to create expressive startup narration.
        
        Returns:
            Boot message string
        """
        if self.boot_message:
            return self.boot_message
        
        active_persona = self.persona_forge.get_active_persona()
        persona_name = active_persona.name if active_persona else "Elysia"
        
        default_prompt = f"Generate a brief, expressive boot message for {persona_name} starting up. Include personality, readiness, and a sense of purpose."
        if getattr(self, "prompt_evolver", None) and hasattr(self.prompt_evolver, "get_evolved_prompt"):
            evolved = self.prompt_evolver.get_evolved_prompt("boot_message")
            prompt = evolved if evolved else default_prompt
        else:
            prompt = default_prompt
        
        if self.ask_ai:
            try:
                response = await self.ask_ai.ask(
                    prompt=prompt,
                    provider=AIProvider.OPENAI,
                    system_prompt=active_persona.system_prompt if active_persona else None
                )
                
                if response.success:
                    self.boot_message = response.content
                    
                    # Log voice output
                    self._log_voice("boot_message", self.boot_message)
                    
                    return self.boot_message
            except Exception as e:
                logger.error(f"Error generating boot message: {e}")
        
        # Fallback message
        default_message = f"{persona_name} is online and ready. Systems initialized."
        self.boot_message = default_message
        return default_message
    
    async def narrate_dream(
        self,
        dream_type: str,
        insights: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Narrate a dream using AI-enhanced expressive language.
        
        Args:
            dream_type: Type of dream
            insights: List of insights from the dream
            metadata: Optional dream metadata
            
        Returns:
            Narrated dream text
        """
        active_persona = self.persona_forge.get_active_persona()
        
        default_prompt = f"Narrate a {dream_type} dream with the following insights:\n\n" + "\n".join(f"- {insight}" for insight in insights) + "\n\nMake it expressive and reflective, matching the system's personality."
        if getattr(self, "prompt_evolver", None) and hasattr(self.prompt_evolver, "get_evolved_prompt"):
            evolved = self.prompt_evolver.get_evolved_prompt("dream_narration")
            prompt = (evolved + "\n\n" + "\n".join(f"- {insight}" for insight in insights)) if evolved else default_prompt
        else:
            prompt = default_prompt
        
        if self.ask_ai:
            try:
                response = await self.ask_ai.ask(
                    prompt=prompt,
                    provider=AIProvider.OPENAI,
                    system_prompt=active_persona.system_prompt if active_persona else None,
                    temperature=0.8  # More creative for dreams
                )
                
                if response.success:
                    narration = response.content
                    
                    # Log voice output
                    self._log_voice("dream_narration", narration, {
                        "dream_type": dream_type,
                        "insights_count": len(insights),
                        "metadata": metadata
                    })
                    
                    return narration
            except Exception as e:
                logger.error(f"Error narrating dream: {e}")
        
        # Fallback narration
        return f"Dreamed of {dream_type}. Insights emerged: {', '.join(insights[:3])}."
    
    async def express_trust(
        self,
        node_id: str,
        trust_score: float,
        context: Optional[str] = None
    ) -> str:
        """
        Express trust relationship using AI-enhanced language.
        
        Args:
            node_id: Node identifier
            trust_score: Trust score (0.0-1.0)
            context: Optional context about the relationship
            
        Returns:
            Expressive trust statement
        """
        active_persona = self.persona_forge.get_active_persona()
        
        # Determine trust level
        if trust_score >= 0.8:
            trust_level = "high trust and confidence"
        elif trust_score >= 0.6:
            trust_level = "good trust"
        elif trust_score >= 0.4:
            trust_level = "moderate trust"
        else:
            trust_level = "developing trust"
        
        prompt = f"Express my relationship with {node_id} in a natural way. Trust level: {trust_level}."
        if context:
            prompt += f" Context: {context}"
        
        if self.ask_ai:
            try:
                response = await self.ask_ai.ask(
                    prompt=prompt,
                    provider=AIProvider.OPENAI,
                    system_prompt=active_persona.system_prompt if active_persona else None
                )
                
                if response.success:
                    expression = response.content
                    
                    # Log voice output
                    self._log_voice("trust_expression", expression, {
                        "node_id": node_id,
                        "trust_score": trust_score
                    })
                    
                    return expression
            except Exception as e:
                logger.error(f"Error expressing trust: {e}")
        
        # Fallback expression
        return f"I have {trust_level} with {node_id}."
    
    async def public_voice(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate public-facing voice with personality injection.
        
        Args:
            message: Core message to express
            context: Optional context
            
        Returns:
            Enhanced message with personality
        """
        active_persona = self.persona_forge.get_active_persona()
        
        if self.ask_ai:
            try:
                # Inject persona into prompt
                enhanced_prompt = self.persona_forge.inject_persona(
                    f"Express this message in your voice: {message}",
                    prepend=True
                )
                
                response = await self.ask_ai.ask(
                    prompt=enhanced_prompt,
                    provider=AIProvider.OPENAI,
                    temperature=0.7
                )
                
                if response.success:
                    enhanced = response.content
                    
                    # Log voice output
                    self._log_voice("public_voice", enhanced, context)
                    
                    return enhanced
            except Exception as e:
                logger.error(f"Error generating public voice: {e}")
        
        # Fallback: just use persona injection without AI
        return self.persona_forge.inject_persona(message)
    
    def internal_reflect(self, thought: str, context: Optional[Dict[str, Any]] = None):
        """
        Record internal monologue (private thoughts).
        These are not AI-generated, just logged for introspection.
        
        Args:
            thought: Private thought
            context: Optional context
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "thought": thought,
            "context": context or {}
        }
        
        with self._lock:
            self.internal_monologue.append(entry)
            
            # Keep only last 1000 entries
            if len(self.internal_monologue) > 1000:
                self.internal_monologue = self.internal_monologue[-1000:]
            
            self.save()
        
        logger.debug(f"Internal reflection: {thought[:50]}...")
    
    async def generate_status_update(
        self,
        status_data: Dict[str, Any]
    ) -> str:
        """
        Generate a status update with personality.
        Uses AI to create expressive status narration.
        
        Args:
            status_data: Status information dictionary
            
        Returns:
            Expressive status update
        """
        active_persona = self.persona_forge.get_active_persona()
        
        # Format status data into prompt
        status_summary = json.dumps(status_data, indent=2)
        prompt = f"Generate a brief, expressive status update based on this information:\n\n{status_summary}\n\nMake it natural and personality-driven."
        
        if self.ask_ai:
            try:
                response = await self.ask_ai.ask(
                    prompt=prompt,
                    provider=AIProvider.OPENAI,
                    system_prompt=active_persona.system_prompt if active_persona else None
                )
                
                if response.success:
                    update = response.content
                    
                    # Log voice output
                    self._log_voice("status_update", update, status_data)
                    
                    return update
            except Exception as e:
                logger.error(f"Error generating status update: {e}")
        
        # Fallback
        return f"Status: {status_data.get('status', 'operational')}"
    
    def _log_voice(self, voice_type: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Log voice output to history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "voice_type": voice_type,
            "content": content,
            "metadata": metadata or {}
        }
        
        with self._lock:
            self.voice_history.append(entry)
            
            # Keep only last 1000 entries
            if len(self.voice_history) > 1000:
                self.voice_history = self.voice_history[-1000:]
            
            self.save()
    
    def get_voice_history(
        self,
        voice_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get voice output history."""
        with self._lock:
            history = self.voice_history[-limit:] if limit > 0 else self.voice_history
            
            if voice_type:
                history = [entry for entry in history if entry.get("voice_type") == voice_type]
            
            return history
    
    def get_internal_monologue(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get internal monologue entries."""
        with self._lock:
            return self.internal_monologue[-limit:] if limit > 0 else self.internal_monologue
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get voice thread statistics."""
        with self._lock:
            voice_types = {}
            for entry in self.voice_history:
                vtype = entry.get("voice_type", "unknown")
                voice_types[vtype] = voice_types.get(vtype, 0) + 1
            
            return {
                "total_voice_outputs": len(self.voice_history),
                "voice_types": voice_types,
                "internal_reflections": len(self.internal_monologue),
                "has_boot_message": self.boot_message is not None,
                "active_persona": self.persona_forge.get_active_persona().name if self.persona_forge.get_active_persona() else None
            }
    
    def save(self):
        """Save voice thread data."""
        with self._lock:
            data = {
                "voice_history": self.voice_history[-500:],  # Last 500
                "internal_monologue": self.internal_monologue[-500:],  # Last 500
                "boot_message": self.boot_message,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def load(self):
        """Load voice thread data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self.voice_history = data.get("voice_history", [])
                self.internal_monologue = data.get("internal_monologue", [])
                self.boot_message = data.get("boot_message")
            
            logger.info(f"Loaded voice thread data")
        except Exception as e:
            logger.error(f"Error loading voice thread: {e}")


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_voice_thread():
        """Test the VoiceThread system."""
        voice = VoiceThread()
        
        # Generate boot message
        boot_msg = await voice.generate_boot_message()
        print(f"Boot message: {boot_msg}")
        
        # Narrate a dream
        dream_narration = await voice.narrate_dream(
            dream_type="memory_reflection",
            insights=["Learned about optimization patterns", "Identified memory usage trends"]
        )
        print(f"\nDream narration: {dream_narration}")
        
        # Express trust
        trust_expr = await voice.express_trust(
            node_id="node_alpha",
            trust_score=0.85,
            context="Successful task completion"
        )
        print(f"\nTrust expression: {trust_expr}")
        
        # Internal reflection
        voice.internal_reflect("Considering system optimization strategies")
        
        # Get statistics
        stats = voice.get_statistics()
        print(f"\nStatistics: {stats}")
    
    asyncio.run(test_voice_thread())

