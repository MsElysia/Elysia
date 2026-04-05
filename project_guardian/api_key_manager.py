#!/usr/bin/env python3
"""
API Key Manager for WebScout
Centralized API key loading and validation for WebScout agent.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class APIKeys:
    """Container for API keys"""
    openai: Optional[str] = None
    openrouter: Optional[str] = None
    anthropic: Optional[str] = None
    huggingface: Optional[str] = None
    cohere: Optional[str] = None
    brave_search: Optional[str] = None
    tavily: Optional[str] = None
    
    def has_llm_key(self) -> bool:
        """Check if any LLM API key is available"""
        return bool(self.openai or self.openrouter or self.anthropic or self.huggingface or self.cohere)
    
    def has_web_key(self) -> bool:
        """Check if web search API key is available"""
        return bool(self.brave_search or self.tavily)


class APIKeyManager:
    """
    Manages API keys for WebScout agent.
    Loads from environment variables, config files, or API keys folder.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize API key manager.
        
        Args:
            config_path: Optional path to config/api_keys.json
        """
        self.config_path = config_path or (_PROJECT_ROOT / "config" / "api_keys.json")
        self.api_keys_dir = _PROJECT_ROOT / "API keys"
        self.keys = APIKeys()
        self.load_keys()
    
    def load_keys(self) -> bool:
        """
        Load API keys from multiple sources.
        
        Returns:
            True if at least one key was loaded
        """
        loaded = False
        
        # Try loading from config file first
        if self.config_path.exists():
            loaded = self._load_from_config() or loaded
        
        # Try loading from environment variables
        loaded = self._load_from_env() or loaded
        
        # Try loading from API keys folder
        loaded = self._load_from_folder() or loaded
        
        if not loaded:
            logger.warning("No API keys loaded. WebScout will run in simulated mode.")
        else:
            logger.info(f"API keys loaded. LLM available: {self.keys.has_llm_key()}")
        
        return loaded
    
    def _load_from_config(self) -> bool:
        """Load keys from config/api_keys.json"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Try different key formats
            openai_key = (
                config.get('openai', {}).get('api_key') if isinstance(config.get('openai'), dict)
                else config.get('openai') or config.get('openai_api_key')
            )
            
            openrouter_key = (
                config.get('openrouter', {}).get('api_key') if isinstance(config.get('openrouter'), dict)
                else config.get('openrouter') or config.get('openrouter_api_key')
            )
            
            anthropic_key = (
                config.get('anthropic', {}).get('api_key') if isinstance(config.get('anthropic'), dict)
                else config.get('anthropic') or config.get('anthropic_api_key')
            )
            
            huggingface_key = (
                config.get('huggingface', {}).get('api_key') if isinstance(config.get('huggingface'), dict)
                else config.get('huggingface') or config.get('huggingface_api_key')
            )
            
            brave_search_key = (
                config.get('brave_search', {}).get('api_key') if isinstance(config.get('brave_search'), dict)
                else config.get('brave_search') or config.get('brave_search_api_key') or config.get('BRAVE_SEARCH_API_KEY')
            )
            
            tavily_key = (
                config.get('tavily', {}).get('api_key') if isinstance(config.get('tavily'), dict)
                else config.get('tavily') or config.get('tavily_api_key') or config.get('TAVILY_API_KEY')
            )
            
            if openai_key:
                self.keys.openai = openai_key
            if openrouter_key:
                self.keys.openrouter = openrouter_key
            if anthropic_key:
                self.keys.anthropic = anthropic_key
            if huggingface_key:
                self.keys.huggingface = huggingface_key
            cohere_key = (
                config.get("cohere", {}).get("api_key") if isinstance(config.get("cohere"), dict)
                else config.get("cohere") or config.get("cohere_api_key")
            )
            if cohere_key:
                self.keys.cohere = cohere_key
            if brave_search_key:
                self.keys.brave_search = brave_search_key
            if tavily_key:
                self.keys.tavily = tavily_key
            
            return bool(
                openai_key or openrouter_key or anthropic_key or huggingface_key
                or cohere_key or brave_search_key or tavily_key
            )
        except Exception as e:
            logger.warning(f"Could not load keys from config: {e}")
            return False
    
    def _load_from_env(self) -> bool:
        """Load keys from environment variables"""
        loaded = False
        
        if os.getenv("OPENAI_API_KEY"):
            self.keys.openai = os.getenv("OPENAI_API_KEY")
            loaded = True
        
        if os.getenv("OPENROUTER_API_KEY"):
            self.keys.openrouter = os.getenv("OPENROUTER_API_KEY")
            loaded = True
        
        if os.getenv("ANTHROPIC_API_KEY"):
            self.keys.anthropic = os.getenv("ANTHROPIC_API_KEY")
            loaded = True
        
        if os.getenv("HUGGINGFACE_API_KEY"):
            self.keys.huggingface = os.getenv("HUGGINGFACE_API_KEY")
            loaded = True

        if os.getenv("COHERE_API_KEY"):
            self.keys.cohere = os.getenv("COHERE_API_KEY")
            loaded = True
        
        if os.getenv("BRAVE_SEARCH_API_KEY"):
            self.keys.brave_search = os.getenv("BRAVE_SEARCH_API_KEY")
            loaded = True
        
        if os.getenv("TAVILY_API_KEY"):
            self.keys.tavily = os.getenv("TAVILY_API_KEY")
            loaded = True
        
        return loaded
    
    def _load_from_folder(self) -> bool:
        """Load keys from API keys folder"""
        if not self.api_keys_dir.exists():
            return False
        
        loaded = False
        key_mapping = {
            "chat gpt api key for elysia.txt": ("openai", "openai"),
            "open router API key.txt": ("openrouter", "openrouter"),
            "Cohere API key.txt": ("cohere", "cohere"),
            "Hugging face API key.txt": ("huggingface", "huggingface"),
            "brave search api key.txt": ("brave_search", "brave_search"),
            "Brave Search API key.txt": ("brave_search", "brave_search"),
            "tavily api key.txt": ("tavily", "tavily"),
            "Tavily API key.txt": ("tavily", "tavily"),
        }
        
        for filename, (key_name, attr_name) in key_mapping.items():
            filepath = self.api_keys_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        key = f.read().strip()
                        if key and attr_name:
                            setattr(self.keys, attr_name, key)
                            loaded = True
                            logger.debug(f"Loaded {key_name} from {filename}")
                except Exception as e:
                    logger.warning(f"Could not load {filename}: {e}")
        
        return loaded
    
    def get_openai_client(self):
        """Get OpenAI client if key is available"""
        if not self.keys.openai:
            return None
        
        try:
            from openai import OpenAI
            return OpenAI(api_key=self.keys.openai)
        except ImportError:
            logger.warning("OpenAI package not installed. Install with: pip install openai")
            return None
        except Exception as e:
            logger.error(f"Error creating OpenAI client: {e}")
            return None
    
    def get_llm_client(self, preferred: str = "openai"):
        """
        Get LLM client (OpenAI, OpenRouter, or Anthropic).
        
        Args:
            preferred: Preferred provider ("openai", "openrouter", "anthropic")
        
        Returns:
            Client instance or None
        """
        # Try preferred first
        if preferred == "openai" and self.keys.openai:
            return self.get_openai_client()
        elif preferred == "openrouter" and self.keys.openrouter:
            # OpenRouter uses OpenAI-compatible API
            try:
                from openai import OpenAI
                return OpenAI(
                    api_key=self.keys.openrouter,
                    base_url="https://openrouter.ai/api/v1"
                )
            except ImportError:
                logger.warning("OpenAI package not installed")
                return None
        elif preferred == "anthropic" and self.keys.anthropic:
            try:
                from anthropic import Anthropic
                return Anthropic(api_key=self.keys.anthropic)
            except ImportError:
                logger.warning("Anthropic package not installed")
                return None
        
        # Fallback to any available
        if self.keys.openai:
            return self.get_openai_client()
        elif self.keys.openrouter:
            try:
                from openai import OpenAI
                return OpenAI(
                    api_key=self.keys.openrouter,
                    base_url="https://openrouter.ai/api/v1"
                )
            except ImportError:
                pass
        
        return None
    
    def has_llm_access(self) -> bool:
        """Check if LLM API access is available"""
        return self.keys.has_llm_key()
    
    def require_llm_access(self) -> bool:
        """
        Require LLM access. Raises error if not available.
        
        Returns:
            True if available
        
        Raises:
            RuntimeError: If no LLM keys are available
        """
        if not self.has_llm_access():
            raise RuntimeError(
                "No LLM API keys available. WebScout requires at least one of: "
                "OPENAI_API_KEY, OPENROUTER_API_KEY, or ANTHROPIC_API_KEY. "
                "Set environment variables or configure config/api_keys.json"
            )
        return True


# Global instance
_global_manager: Optional[APIKeyManager] = None


def get_api_key_manager() -> APIKeyManager:
    """Get or create global API key manager instance"""
    global _global_manager
    if _global_manager is None:
        _global_manager = APIKeyManager()
    return _global_manager

