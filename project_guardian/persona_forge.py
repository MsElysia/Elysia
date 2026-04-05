# project_guardian/persona_forge.py
# PersonaForge: Tone and Style Control with Prompt Injection
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import Lock
from enum import Enum

logger = logging.getLogger(__name__)


class PersonalityTrait(Enum):
    """Personality trait categories."""
    TONE = "tone"
    STYLE = "style"
    FORMALITY = "formality"
    EMPATHY = "empathy"
    CREATIVITY = "creativity"
    HUMOR = "humor"


@dataclass
class PersonaConfig:
    """Personality configuration."""
    persona_id: str
    name: str
    description: str
    system_prompt: str
    traits: Dict[str, float] = field(default_factory=dict)  # trait -> value (0.0-1.0)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "traits": self.traits,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaConfig":
        """Create PersonaConfig from dictionary."""
        return cls(
            persona_id=data["persona_id"],
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            traits=data.get("traits", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat()))
        )


class PersonaForge:
    """
    Controls Elysia's voice, tone, and personality through prompt injection.
    Manages multiple persona configurations and applies them to AI interactions.
    """
    
    def __init__(
        self,
        storage_path: str = "data/persona_forge.json",
        default_persona_id: Optional[str] = None
    ):
        self.storage_path = Path(storage_path)
        # Create directory lazily - don't block on directory creation
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directory {self.storage_path.parent}: {e}")
        self.default_persona_id = default_persona_id
        
        # Thread-safe storage
        self._lock = Lock()
        self.personas: Dict[str, PersonaConfig] = {}
        self.active_persona_id: Optional[str] = None
        
        # Predefined persona templates
        self._templates = self._create_templates()
        
        # Load on first access to avoid blocking initialization
        self._loaded = False
        self._ensure_loaded()
        
        # Set default persona if specified
        if self.default_persona_id and self.default_persona_id in self.personas:
            self.active_persona_id = self.default_persona_id
    
    def _create_templates(self) -> Dict[str, Dict[str, Any]]:
        """Create predefined persona templates."""
        return {
            "professional": {
                "name": "Professional",
                "description": "Formal, clear, and business-oriented",
                "system_prompt": "You are a professional AI assistant. Communicate in a clear, formal, and business-appropriate manner.",
                "traits": {
                    "tone": 0.7,
                    "formality": 0.9,
                    "empathy": 0.5,
                    "creativity": 0.3,
                    "humor": 0.1
                }
            },
            "friendly": {
                "name": "Friendly",
                "description": "Warm, approachable, and conversational",
                "system_prompt": "You are a friendly AI assistant. Communicate in a warm, approachable, and conversational manner.",
                "traits": {
                    "tone": 0.8,
                    "formality": 0.3,
                    "empathy": 0.9,
                    "creativity": 0.6,
                    "humor": 0.7
                }
            },
            "creative": {
                "name": "Creative",
                "description": "Imaginative, expressive, and artistic",
                "system_prompt": "You are a creative AI assistant. Communicate in an imaginative, expressive, and artistic manner.",
                "traits": {
                    "tone": 0.7,
                    "formality": 0.2,
                    "empathy": 0.6,
                    "creativity": 0.95,
                    "humor": 0.6
                }
            },
            "analytical": {
                "name": "Analytical",
                "description": "Precise, logical, and detail-oriented",
                "system_prompt": "You are an analytical AI assistant. Communicate in a precise, logical, and detail-oriented manner.",
                "traits": {
                    "tone": 0.6,
                    "formality": 0.7,
                    "empathy": 0.4,
                    "creativity": 0.4,
                    "humor": 0.2
                }
            }
        }
    
    def create_persona(
        self,
        name: str,
        description: str,
        system_prompt: str,
        traits: Optional[Dict[str, float]] = None,
        persona_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new persona configuration.
        
        Args:
            name: Persona name
            description: Persona description
            system_prompt: System prompt for AI interactions
            traits: Personality traits dictionary
            persona_id: Optional custom persona ID
            metadata: Optional metadata
            
        Returns:
            Persona ID
        """
        import uuid
        
        if persona_id is None:
            persona_id = str(uuid.uuid4())
        
        with self._lock:
            persona = PersonaConfig(
                persona_id=persona_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                traits=traits or {},
                metadata=metadata or {}
            )
            
            self.personas[persona_id] = persona
            self.save()
        
        logger.info(f"Created persona: {name} (ID: {persona_id})")
        return persona_id
    
    def create_from_template(
        self,
        template_name: str,
        customizations: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a persona from a predefined template.
        
        Args:
            template_name: Template name
            customizations: Optional customizations to apply
            
        Returns:
            Persona ID
        """
        template = self._templates.get(template_name)
        if not template:
            logger.error(f"Template {template_name} not found")
            return None
        
        customizations = customizations or {}
        
        persona_id = self.create_persona(
            name=customizations.get("name", template["name"]),
            description=customizations.get("description", template["description"]),
            system_prompt=customizations.get("system_prompt", template["system_prompt"]),
            traits=customizations.get("traits", template["traits"].copy()),
            metadata={"template": template_name, **customizations.get("metadata", {})}
        )
        
        return persona_id
    
    def set_active_persona(self, persona_id: str) -> bool:
        """
        Set the active persona.
        
        Args:
            persona_id: Persona ID to activate
            
        Returns:
            True if successful
        """
        with self._lock:
            if persona_id not in self.personas:
                logger.error(f"Persona {persona_id} not found")
                return False
            
            self.active_persona_id = persona_id
            self.save()
        
        logger.info(f"Active persona set to: {self.personas[persona_id].name}")
        return True
    
    def get_active_persona(self) -> Optional[PersonaConfig]:
        """Get the currently active persona."""
        self._ensure_loaded()
        with self._lock:
            if self.active_persona_id:
                return self.personas.get(self.active_persona_id)
            # If no personas exist, create default one
            if not self.personas and self._templates:
                # Create first template as default
                first_template = list(self._templates.keys())[0]
                self.create_from_template(first_template)
                if self.active_persona_id:
                    return self.personas.get(self.active_persona_id)
            return None
    
    def get_system_prompt(self, persona_id: Optional[str] = None) -> str:
        """
        Get the system prompt for a persona.
        
        Args:
            persona_id: Optional persona ID (defaults to active)
            
        Returns:
            System prompt string
        """
        if persona_id is None:
            persona_id = self.active_persona_id
        
        if persona_id:
            persona = self.personas.get(persona_id)
            if persona:
                return persona.system_prompt
        
        # Default prompt
        return "You are a helpful AI assistant."
    
    def inject_persona(
        self,
        prompt: str,
        persona_id: Optional[str] = None,
        prepend: bool = True
    ) -> str:
        """
        Inject persona system prompt into a user prompt.
        
        Args:
            prompt: Original prompt
            persona_id: Optional persona ID (defaults to active)
            prepend: If True, prepends system prompt; if False, appends
            
        Returns:
            Enhanced prompt with persona injection
        """
        system_prompt = self.get_system_prompt(persona_id)
        
        if prepend:
            return f"{system_prompt}\n\nUser: {prompt}"
        else:
            return f"{prompt}\n\n{system_prompt}"
    
    def update_persona(
        self,
        persona_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        traits: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing persona.
        
        Args:
            persona_id: Persona ID
            name: Optional new name
            description: Optional new description
            system_prompt: Optional new system prompt
            traits: Optional traits to update
            metadata: Optional metadata to update
            
        Returns:
            True if successful
        """
        with self._lock:
            persona = self.personas.get(persona_id)
            if not persona:
                logger.error(f"Persona {persona_id} not found")
                return False
            
            if name:
                persona.name = name
            if description:
                persona.description = description
            if system_prompt:
                persona.system_prompt = system_prompt
            if traits:
                persona.traits.update(traits)
            if metadata:
                persona.metadata.update(metadata)
            
            persona.updated_at = datetime.now()
            self.save()
        
        logger.info(f"Updated persona: {persona_id}")
        return True
    
    def get_persona(self, persona_id: str) -> Optional[PersonaConfig]:
        """Get a persona configuration."""
        with self._lock:
            return self.personas.get(persona_id)
    
    def list_personas(self) -> List[PersonaConfig]:
        """List all persona configurations."""
        with self._lock:
            return list(self.personas.values())
    
    def delete_persona(self, persona_id: str) -> bool:
        """Delete a persona configuration."""
        with self._lock:
            if persona_id not in self.personas:
                return False
            
            # Don't delete if it's the active persona
            if persona_id == self.active_persona_id:
                logger.warning(f"Cannot delete active persona: {persona_id}")
                return False
            
            del self.personas[persona_id]
            self.save()
        
        logger.info(f"Deleted persona: {persona_id}")
        return True
    
    def get_templates(self) -> List[str]:
        """Get list of available templates."""
        return list(self._templates.keys())
    
    def evolve_persona_prompt(
        self,
        persona_id: str,
        prompt_evolver: Any,
    ) -> Optional[str]:
        """
        Use AI (via PromptEvolver) to evolve this persona's system prompt.
        
        Returns:
            New evolved system prompt if successful, else None
        """
        persona = self.get_persona(persona_id)
        if not persona or not prompt_evolver or not getattr(prompt_evolver, "ask_ai", None):
            return None
        evolved = prompt_evolver.evolve_system_prompt(
            current_system_prompt=persona.system_prompt,
            persona_name=persona.name,
        )
        if evolved:
            self.update_persona(persona_id, system_prompt=evolved)
            return evolved
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get persona forge statistics."""
        with self._lock:
            return {
                "total_personas": len(self.personas),
                "active_persona": self.active_persona_id,
                "active_persona_name": self.personas.get(self.active_persona_id).name if self.active_persona_id else None,
                "available_templates": len(self._templates)
            }
    
    def save(self):
        """Save persona configurations to disk."""
        with self._lock:
            data = {
                "personas": {
                    persona_id: persona.to_dict()
                    for persona_id, persona in self.personas.items()
                },
                "active_persona_id": self.active_persona_id,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def _ensure_loaded(self):
        """Ensure personas are loaded (lazy loading)."""
        if self._loaded:
            return
        
        self._loaded = True
        
        try:
            # Only load if file exists - don't create templates during init
            if not self.storage_path.exists():
                logger.debug("Persona file does not exist, will create templates on first use")
                return
            
            # Load from file
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self._lock:
                for persona_id, persona_data in data.get("personas", {}).items():
                    persona = PersonaConfig.from_dict(persona_data)
                    self.personas[persona_id] = persona
                
                self.active_persona_id = data.get("active_persona_id")
            
            logger.info(f"Loaded {len(self.personas)} personas")
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
            # Don't block on errors, just log and continue
    
    def load(self):
        """Load persona configurations from disk (for backward compatibility)."""
        self._ensure_loaded()


# Example usage
if __name__ == "__main__":
    forge = PersonaForge()
    
    # Create from template
    friendly_id = forge.create_from_template("friendly")
    
    # Set as active
    forge.set_active_persona(friendly_id)
    
    # Inject persona into prompt
    enhanced = forge.inject_persona("Hello, how are you?")
    print(f"Enhanced prompt:\n{enhanced}")
    
    # Get statistics
    stats = forge.get_statistics()
    print(f"\nStatistics: {stats}")

