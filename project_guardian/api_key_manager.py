#!/usr/bin/env python3
"""
API Key Manager for WebScout and shared secrets.
Centralized API key loading from env, config/api_keys.json, and the API keys folder.

Income APIs (Gumroad / Stripe) use the same loader; see resolve_gumroad_access_token /
resolve_stripe_secret_key (env GUMROAD_ACCESS_TOKEN / STRIPE_SECRET_KEY and matching config keys).
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LAST_KEY_AVAILABILITY_SIGNATURE: Optional[tuple[bool, bool]] = None


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
    gumroad: Optional[str] = None
    stripe: Optional[str] = None

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
        
        llm_available = self.keys.has_llm_key()
        web_available = self.keys.has_web_key()
        availability_sig = (llm_available, web_available)
        global _LAST_KEY_AVAILABILITY_SIGNATURE
        if not loaded:
            if _LAST_KEY_AVAILABILITY_SIGNATURE != availability_sig:
                logger.warning("No API keys loaded. WebScout will run in simulated mode.")
            else:
                logger.debug("No API keys loaded (unchanged availability state).")
        else:
            msg = f"API keys loaded. LLM available: {llm_available}"
            if _LAST_KEY_AVAILABILITY_SIGNATURE != availability_sig:
                logger.info(msg)
            else:
                logger.debug("%s (unchanged availability state)", msg)
        _LAST_KEY_AVAILABILITY_SIGNATURE = availability_sig
        
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

            gumroad_key = (
                config.get('gumroad', {}).get('api_key') if isinstance(config.get('gumroad'), dict)
                else config.get('gumroad') or config.get('gumroad_access_token') or config.get('GUMROAD_ACCESS_TOKEN')
            )

            stripe_key = (
                config.get('stripe', {}).get('api_key') if isinstance(config.get('stripe'), dict)
                else config.get('stripe') or config.get('stripe_secret_key') or config.get('STRIPE_SECRET_KEY')
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
            if gumroad_key:
                self.keys.gumroad = gumroad_key
            if stripe_key:
                self.keys.stripe = stripe_key

            return bool(
                openai_key or openrouter_key or anthropic_key or huggingface_key
                or cohere_key or brave_search_key or tavily_key or gumroad_key or stripe_key
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

        if os.getenv("GUMROAD_ACCESS_TOKEN"):
            self.keys.gumroad = os.getenv("GUMROAD_ACCESS_TOKEN")
            loaded = True

        if os.getenv("STRIPE_SECRET_KEY"):
            self.keys.stripe = os.getenv("STRIPE_SECRET_KEY")
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
            "gumroad access token.txt": ("gumroad", "gumroad"),
            "Gumroad access token.txt": ("gumroad", "gumroad"),
            "stripe secret key.txt": ("stripe", "stripe"),
            "Stripe secret key.txt": ("stripe", "stripe"),
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


def resolve_gumroad_access_token() -> Optional[str]:
    """
    Gumroad access token for Harvest Engine / income modules.
    Loaded via APIKeyManager (config/api_keys.json, env GUMROAD_ACCESS_TOKEN, API keys folder).
    Precedence matches other keys: config, then env, then folder files (last wins).
    """
    mgr = get_api_key_manager()
    v = (mgr.keys.gumroad or "").strip()
    return v or None


def resolve_stripe_secret_key() -> Optional[str]:
    """Stripe secret key; same sources as resolve_gumroad_access_token (STRIPE_SECRET_KEY, config, folder)."""
    mgr = get_api_key_manager()
    v = (mgr.keys.stripe or "").strip()
    return v or None


def reload_api_key_manager() -> None:
    """Drop singleton so the next resolve_* reloads from disk, env, and API keys folder."""
    global _global_manager
    _global_manager = None
    get_api_key_manager()


def _parse_gumroad_from_cfg_dict(cfg: Dict[str, Any]) -> Optional[str]:
    g = cfg.get("gumroad")
    if isinstance(g, dict):
        v = (g.get("api_key") or "").strip()
        return v or None
    if isinstance(g, str) and g.strip():
        return g.strip()
    v = (cfg.get("gumroad_access_token") or "").strip()
    return v or None


def _parse_stripe_from_cfg_dict(cfg: Dict[str, Any]) -> Optional[str]:
    s = cfg.get("stripe")
    if isinstance(s, dict):
        v = (s.get("api_key") or "").strip()
        return v or None
    if isinstance(s, str) and s.strip():
        return s.strip()
    v = (cfg.get("stripe_secret_key") or "").strip()
    return v or None


def _folder_key_present(filenames: List[str]) -> bool:
    api_keys_dir = _PROJECT_ROOT / "API keys"
    if not api_keys_dir.exists():
        return False
    for filename in filenames:
        path = api_keys_dir / filename
        if not path.exists():
            continue
        try:
            if path.read_text(encoding="utf-8").strip():
                return True
        except Exception:
            continue
    return False


def _effective_income_key_source(*, folder: bool, env: bool, config_file: bool, configured: bool) -> str:
    if not configured:
        return "none"
    # APIKeyManager load order is config, env, folder; folder wins when present.
    if folder:
        return "api_keys_folder"
    if env:
        return "env"
    if config_file:
        return "config_file"
    return "other"


def income_keys_ui_status() -> Dict[str, Any]:
    """Non-secret snapshot for Control Panel (effective token presence + source hints)."""
    import os

    path = _PROJECT_ROOT / "config" / "api_keys.json"
    file_g = False
    file_s = False
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                file_g = bool(_parse_gumroad_from_cfg_dict(data))
                file_s = bool(_parse_stripe_from_cfg_dict(data))
        except Exception:
            pass
    env_g = bool((os.environ.get("GUMROAD_ACCESS_TOKEN") or "").strip())
    env_s = bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip())
    folder_g = _folder_key_present(["gumroad access token.txt", "Gumroad access token.txt"])
    folder_s = _folder_key_present(["stripe secret key.txt", "Stripe secret key.txt"])
    eff_g = bool(resolve_gumroad_access_token())
    eff_s = bool(resolve_stripe_secret_key())
    return {
        "gumroad_configured": eff_g,
        "stripe_configured": eff_s,
        "gumroad_from_env": env_g,
        "stripe_from_env": env_s,
        "gumroad_in_config_file": file_g,
        "stripe_in_config_file": file_s,
        "gumroad_in_api_keys_folder": folder_g,
        "stripe_in_api_keys_folder": folder_s,
        "gumroad_effective_source": _effective_income_key_source(
            folder=folder_g,
            env=env_g,
            config_file=file_g,
            configured=eff_g,
        ),
        "stripe_effective_source": _effective_income_key_source(
            folder=folder_s,
            env=env_s,
            config_file=file_s,
            configured=eff_s,
        ),
    }


def persist_income_keys_to_config_file(
    *,
    gumroad_access_token: Optional[str] = None,
    stripe_secret_key: Optional[str] = None,
    clear_gumroad: bool = False,
    clear_stripe: bool = False,
) -> None:
    """
    Merge Gumroad / Stripe into config/api_keys.json (creates file if needed).
    Env vars are not modified; they still override file after reload. Folder-based keys are unchanged.
    """
    path = _PROJECT_ROOT / "config" / "api_keys.json"
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = dict(raw)
        except Exception:
            data = {}
    if clear_gumroad:
        data.pop("gumroad", None)
        data.pop("gumroad_access_token", None)
    if clear_stripe:
        data.pop("stripe", None)
        data.pop("stripe_secret_key", None)
    if gumroad_access_token is not None and gumroad_access_token.strip():
        data["gumroad"] = {"api_key": gumroad_access_token.strip()}
    if stripe_secret_key is not None and stripe_secret_key.strip():
        data["stripe"] = {"api_key": stripe_secret_key.strip()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    reload_api_key_manager()

