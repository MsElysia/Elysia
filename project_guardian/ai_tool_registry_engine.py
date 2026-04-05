# project_guardian/ai_tool_registry_engine.py
# ToolRegistry: Auto-discovery and Management of External AI Tools
# Based on Conversation 3 (elysia 4 sub a) design specifications
#
# SECURITY: This module handles AI tool registration and should be used with caution.
# API keys are stored in metadata and should be encrypted in production.
# All network operations route through WebReader gateway.

import logging
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
import importlib
import inspect

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for an AI tool."""
    name: str
    description: str
    provider: str  # e.g., "openai", "anthropic", "huggingface"
    api_endpoint: str
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None  # Environment variable name
    capabilities: List[str] = field(default_factory=list)
    rate_limit: Optional[Dict[str, Any]] = None
    cost_per_request: Optional[float] = None
    adapter_class: Optional[str] = None  # Generated adapter class name
    adapter_path: Optional[str] = None  # Path to adapter module
    registered_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "api_endpoint": self.api_endpoint,
            "api_key": self.api_key,  # In production, encrypt this
            "api_key_env": self.api_key_env,
            "capabilities": self.capabilities,
            "rate_limit": self.rate_limit,
            "cost_per_request": self.cost_per_request,
            "adapter_class": self.adapter_class,
            "adapter_path": self.adapter_path,
            "registered_at": self.registered_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetadata":
        """Create ToolMetadata from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            provider=data["provider"],
            api_endpoint=data["api_endpoint"],
            api_key=data.get("api_key"),
            api_key_env=data.get("api_key_env"),
            capabilities=data.get("capabilities", []),
            rate_limit=data.get("rate_limit"),
            cost_per_request=data.get("cost_per_request"),
            adapter_class=data.get("adapter_class"),
            adapter_path=data.get("adapter_path"),
            registered_at=datetime.fromisoformat(data.get("registered_at", datetime.now().isoformat())),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            metadata=data.get("metadata", {})
        )


class ToolAdapter:
    """
    Base adapter for AI tools.
    Provides standardized interface for different AI providers.
    """
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
        self.api_key = self._get_api_key()
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from metadata or environment."""
        if self.metadata.api_key:
            return self.metadata.api_key
        
        if self.metadata.api_key_env:
            import os
            return os.getenv(self.metadata.api_key_env)
        
        return None
    
    def call(self, method: str, **kwargs) -> Dict[str, Any]:
        """
        Call a method on the tool.
        
        Args:
            method: Method name
            **kwargs: Method arguments
            
        Returns:
            Response dictionary with 'success' and 'data'/'error' keys
        """
        try:
            # This is a base implementation
            # Subclasses should override with provider-specific logic
            logger.warning(f"Base ToolAdapter.call() called - should be overridden")
            return {
                "success": False,
                "error": "Base adapter - implement provider-specific logic"
            }
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def test_connection(self, web_reader) -> bool:
        """Test if the tool is accessible."""
        try:
            response = web_reader.request_json(
                method="GET",
                url=self.metadata.api_endpoint,
                timeout_s=5,
                caller_identity="ToolAdapter",
                task_id=None
            )
            return response.get("status_code", 0) < 400
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


class ToolRegistry:
    """
    Auto-discovers, registers, and manages external AI tools and APIs.
    Supports auto-generation of adapters for new APIs.
    """
    
    def __init__(self, storage_path: str = "data/tool_registry.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.tools: Dict[str, ToolMetadata] = {}  # name -> ToolMetadata
        self.adapters: Dict[str, ToolAdapter] = {}  # name -> ToolAdapter
        self.load()
    
    def ensure_minimal_builtin_tools(self) -> None:
        """
        Ensure catalog lists llm / web / exec surfaces so orchestration can treat the registry as usable.
        Stubs use local adapters only (no network).
        """
        builtins = [
            (
                "elysia_builtin_llm",
                "Builtin LLM/chat surface (routes via unified LLM stack)",
                "builtin",
                "local://llm",
                ["llm", "chat", "completion"],
            ),
            (
                "elysia_builtin_web",
                "Builtin web/read surface (routes via WebReader when used)",
                "builtin",
                "local://web",
                ["web", "http", "fetch"],
            ),
            (
                "elysia_builtin_exec",
                "Builtin safe local execution stub (no shell by default)",
                "builtin",
                "local://exec",
                ["exec", "run", "script"],
            ),
            (
                "revenue_executor",
                "Local revenue / execution-plan bridge (uses income_generator + artifacts)",
                "builtin",
                "local://revenue_executor",
                ["revenue", "execution_plan", "finance"],
            ),
            (
                "artifact_synthesizer",
                "Merge latest JSON operator artifacts from disk",
                "builtin",
                "local://artifact_synthesizer",
                ["artifacts", "reports", "synthesis"],
            ),
            (
                "opportunity_ranker",
                "Rank opportunities from latest revenue brief files",
                "builtin",
                "local://opportunity_ranker",
                ["ranking", "opportunities", "revenue"],
            ),
        ]
        for name, desc, prov, ep, caps in builtins:
            if name in self.tools:
                continue
            try:
                self.register_tool(
                    name,
                    desc,
                    prov,
                    ep,
                    capabilities=list(caps),
                    metadata={"builtin_stub": True},
                )
            except Exception as e:
                logger.debug("ensure_minimal_builtin_tools %s: %s", name, e)

    def register_tool(
        self,
        name: str,
        description: str,
        provider: str,
        api_endpoint: str,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        rate_limit: Optional[Dict[str, Any]] = None,
        cost_per_request: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register a new AI tool.
        
        Args:
            name: Tool name (unique identifier)
            description: Tool description
            provider: Provider name (e.g., "openai", "anthropic")
            api_endpoint: API endpoint URL
            api_key: API key (or use api_key_env)
            api_key_env: Environment variable name for API key
            capabilities: List of capabilities this tool provides
            rate_limit: Rate limit configuration
            cost_per_request: Cost per API call
            metadata: Additional metadata
            
        Returns:
            Tool name (for confirmation)
        """
        if name in self.tools:
            logger.warning(f"Tool {name} already registered, updating...")
        
        tool = ToolMetadata(
            name=name,
            description=description,
            provider=provider,
            api_endpoint=api_endpoint,
            api_key=api_key,
            api_key_env=api_key_env,
            capabilities=capabilities or [],
            rate_limit=rate_limit,
            cost_per_request=cost_per_request,
            metadata=metadata or {}
        )
        
        self.tools[name] = tool
        
        # Create adapter
        adapter = self._create_adapter(tool)
        if adapter:
            self.adapters[name] = adapter
        
        self.save()
        logger.info(f"Registered tool: {name} ({provider})")
        
        return name
    
    def _create_adapter(self, tool: ToolMetadata) -> Optional[ToolAdapter]:
        """Create an adapter for a tool."""
        # For now, use base adapter
        # In production, this would generate provider-specific adapters
        try:
            adapter = ToolAdapter(tool)
            return adapter
        except Exception as e:
            logger.error(f"Failed to create adapter for {tool.name}: {e}")
            return None
    
    def get_tool(self, name: str) -> Optional[ToolAdapter]:
        """Get a tool adapter by name."""
        return self.adapters.get(name)
    
    def get_tool_metadata(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name."""
        return self.tools.get(name)
    
    def list_tools(self, provider: Optional[str] = None) -> List[str]:
        """List registered tool names, optionally filtered by provider."""
        if provider:
            return [
                name for name, tool in self.tools.items()
                if tool.provider == provider
            ]
        return list(self.tools.keys())
    
    def discover_tools(
        self,
        sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Discover tools from external sources.
        
        Args:
            sources: List of sources to search ("huggingface", "openrouter", "rapidapi", "edenai")
            
        Returns:
            List of discovered tool metadata
        """
        sources = sources or ["huggingface"]
        discovered = []
        
        # Simplified discovery - in production would query APIs
        logger.info(f"Discovering tools from sources: {sources}")
        
        # Example: Hugging Face discovery
        if "huggingface" in sources:
            try:
                # In production, query Hugging Face API
                # For now, return placeholder
                discovered.append({
                    "name": "huggingface_placeholder",
                    "provider": "huggingface",
                    "description": "Hugging Face models",
                    "api_endpoint": "https://api-inference.huggingface.co",
                    "requires_registration": True
                })
            except Exception as e:
                logger.error(f"Hugging Face discovery failed: {e}")
        
        return discovered
    
    def call_tool(
        self,
        tool_name: str,
        method: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call a registered tool.
        
        Args:
            tool_name: Tool name
            method: Method to call
            **kwargs: Method arguments
            
        Returns:
            Response dictionary
        """
        adapter = self.get_tool(tool_name)
        if not adapter:
            return {
                "success": False,
                "error": f"Tool {tool_name} not found"
            }
        
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool metadata for {tool_name} not found"
            }
        
        # Update usage stats
        tool.usage_count += 1
        tool.last_used = datetime.now()
        
        # Call adapter
        result = adapter.call(method, **kwargs)
        
        # Update success/failure stats
        if result.get("success"):
            tool.success_count += 1
        else:
            tool.failure_count += 1
        
        self.save()
        return result
    
    def revoke_tool(self, name: str) -> bool:
        """Revoke/remove a tool from registry."""
        if name not in self.tools:
            return False
        
        del self.tools[name]
        if name in self.adapters:
            del self.adapters[name]
        
        self.save()
        logger.info(f"Revoked tool: {name}")
        return True
    
    def export_config(self, filepath: Optional[str] = None) -> str:
        """
        Export tool configurations to JSON file.
        
        Args:
            filepath: Optional custom file path
            
        Returns:
            Path to exported file
        """
        path = Path(filepath) if filepath else self.storage_path.parent / "tool_registry_export.json"
        
        data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "exported_at": datetime.now().isoformat()
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(self.tools)} tools to {path}")
        return str(path)
    
    def save(self):
        """Save tool registry to disk."""
        data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load tool registry from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for tool_data in data.get("tools", []):
                tool = ToolMetadata.from_dict(tool_data)
                self.tools[tool.name] = tool
                
                # Recreate adapter
                adapter = self._create_adapter(tool)
                if adapter:
                    self.adapters[tool.name] = adapter
            
            logger.info(f"Loaded {len(self.tools)} tools from registry")
        except Exception as e:
            logger.error(f"Error loading tool registry: {e}")


# Example usage
if __name__ == "__main__":
    registry = ToolRegistry()
    
    # Register a tool
    registry.register_tool(
        name="openai_gpt4",
        description="OpenAI GPT-4 API",
        provider="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        capabilities=["text_generation", "chat", "embeddings"],
        rate_limit={"max_requests": 100, "window_seconds": 60},
        cost_per_request=0.03
    )
    
    # List tools
    tools = registry.list_tools()
    print(f"Registered tools: {tools}")
    
    # Export config
    export_path = registry.export_config()
    print(f"Exported to: {export_path}")

