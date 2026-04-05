# project_guardian/module_registry.py
# ModuleRegistry: Module Discovery and Registration System
# Based on ElysiaLoop-Core Event Loop Design

import logging
import asyncio
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from threading import Lock

try:
    from .base_module_adapter import BaseModuleAdapter, ModuleStatus, SimpleModuleAdapter
except ImportError:
    from base_module_adapter import BaseModuleAdapter, ModuleStatus, SimpleModuleAdapter

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Central registry for module discovery, registration, and management.
    Provides dependency resolution and module lifecycle management.
    """
    
    def __init__(self):
        """Initialize module registry."""
        self._lock = Lock()
        self._modules: Dict[str, BaseModuleAdapter] = {}
        self._module_order: List[str] = []  # Initialization order
        self._initialized: Set[str] = set()
        self._shutdown: bool = False
        self._auto_creator = None  # Will be set if AutoModuleCreator is available
    
    def register(
        self,
        module_name: str,
        adapter: BaseModuleAdapter,
        auto_initialize: bool = False
    ) -> bool:
        """
        Register a module adapter.
        
        Args:
            module_name: Unique module name
            adapter: Module adapter instance
            auto_initialize: If True, initialize immediately
            
        Returns:
            True if registration successful
        """
        with self._lock:
            if module_name in self._modules:
                logger.warning(f"Module {module_name} already registered, overwriting")
            
            self._modules[module_name] = adapter
            if module_name not in self._module_order:
                self._module_order.append(module_name)
            
            logger.info(f"Registered module: {module_name}")
            
            # Auto-initialize if requested
            if auto_initialize:
                asyncio.create_task(self.initialize_module(module_name))
            
            return True
    
    def register_simple(
        self,
        module_name: str,
        module_instance: Any,
        priority: int = 5,
        dependencies: Optional[List[str]] = None,
        auto_initialize: bool = False
    ) -> bool:
        """
        Register a module using SimpleModuleAdapter (auto-detection).
        
        Args:
            module_name: Unique module name
            module_instance: Module instance
            priority: Task priority
            dependencies: Module dependencies
            auto_initialize: If True, initialize immediately
            
        Returns:
            True if registration successful
        """
        adapter = SimpleModuleAdapter(
            module_name=module_name,
            module_instance=module_instance,
            priority=priority,
            dependencies=dependencies
        )
        
        return self.register(module_name, adapter, auto_initialize)
    
    def unregister(self, module_name: str) -> bool:
        """
        Unregister a module.
        
        Args:
            module_name: Module name
            
        Returns:
            True if unregistration successful
        """
        with self._lock:
            if module_name not in self._modules:
                logger.warning(f"Module {module_name} not registered")
                return False
            
            # Shutdown before unregistering
            if module_name in self._initialized:
                asyncio.create_task(self.shutdown_module(module_name))
            
            del self._modules[module_name]
            if module_name in self._module_order:
                self._module_order.remove(module_name)
            
            logger.info(f"Unregistered module: {module_name}")
            return True
    
    def get_module(self, module_name: str) -> Optional[BaseModuleAdapter]:
        """
        Get a module adapter by name.
        
        Args:
            module_name: Module name
            
        Returns:
            Module adapter or None
        """
        with self._lock:
            return self._modules.get(module_name)
    
    def list_modules(self, status: Optional[ModuleStatus] = None) -> List[str]:
        """
        List all registered modules, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            List of module names
        """
        with self._lock:
            if status is None:
                return list(self._modules.keys())
            
            return [
                name for name, adapter in self._modules.items()
                if adapter.status == status
            ]
    
    def find_modules_by_capability(self, capability: str) -> List[str]:
        """
        Find modules that provide a specific capability.
        
        Args:
            capability: Capability name
            
        Returns:
            List of module names with the capability
        """
        with self._lock:
            matching = []
            for name, adapter in self._modules.items():
                capabilities = adapter.get_capabilities()
                if capability in capabilities:
                    matching.append(name)
            return matching
    
    def resolve_dependencies(self, module_name: str) -> List[str]:
        """
        Resolve module dependencies (topological sort).
        
        Args:
            module_name: Starting module name
            
        Returns:
            Ordered list of module names (dependencies first)
        """
        resolved: List[str] = []
        visited: Set[str] = set()
        
        def visit(name: str):
            if name in visited:
                return
            
            if name not in self._modules:
                logger.warning(f"Module {name} not found for dependency resolution")
                return
            
            visited.add(name)
            adapter = self._modules[name]
            
            # Visit dependencies first
            for dep in adapter.dependencies:
                visit(dep)
            
            resolved.append(name)
        
        visit(module_name)
        return resolved
    
    async def initialize_all(self, ignore_errors: bool = False) -> Dict[str, bool]:
        """
        Initialize all registered modules in dependency order.
        
        Args:
            ignore_errors: If True, continue initialization on errors
            
        Returns:
            Dictionary mapping module names to initialization success
        """
        results = {}
        
        # Build dependency-ordered list
        ordered_modules = []
        visited = set()
        
        def add_with_deps(name: str):
            if name in visited:
                return
            visited.add(name)
            
            if name in self._modules:
                adapter = self._modules[name]
                for dep in adapter.dependencies:
                    add_with_deps(dep)
                ordered_modules.append(name)
        
        # Process all modules
        for module_name in self._module_order:
            add_with_deps(module_name)
        
        # Initialize in order
        for module_name in ordered_modules:
            if module_name in self._initialized:
                results[module_name] = True
                continue
            
            try:
                success = await self.initialize_module(module_name)
                results[module_name] = success
                
                if not success and not ignore_errors:
                    logger.error(f"Failed to initialize {module_name}, stopping")
                    break
                    
            except Exception as e:
                logger.error(f"Error initializing {module_name}: {e}")
                results[module_name] = False
                if not ignore_errors:
                    raise
        
        return results
    
    async def initialize_module(self, module_name: str) -> bool:
        """
        Initialize a specific module.
        
        Args:
            module_name: Module name
            
        Returns:
            True if initialization successful
        """
        adapter = self.get_module(module_name)
        if not adapter:
            logger.error(f"Module {module_name} not found")
            return False
        
        if module_name in self._initialized:
            logger.debug(f"Module {module_name} already initialized")
            return True
        
        # Check dependencies
        for dep in adapter.dependencies:
            if dep not in self._initialized:
                logger.info(f"Initializing dependency {dep} for {module_name}")
                await self.initialize_module(dep)
        
        # Initialize module
        success = await adapter.initialize()
        
        if success:
            self._initialized.add(module_name)
            logger.info(f"Module {module_name} initialized")
        else:
            logger.error(f"Module {module_name} initialization failed")
        
        return success
    
    async def shutdown_all(self) -> Dict[str, bool]:
        """
        Shutdown all registered modules in reverse dependency order.
        
        Returns:
            Dictionary mapping module names to shutdown success
        """
        self._shutdown = True
        results = {}
        
        # Reverse order for shutdown
        ordered_modules = list(reversed(self._module_order))
        
        for module_name in ordered_modules:
            if module_name not in self._initialized:
                results[module_name] = True
                continue
            
            try:
                success = await self.shutdown_module(module_name)
                results[module_name] = success
            except Exception as e:
                logger.error(f"Error shutting down {module_name}: {e}")
                results[module_name] = False
        
        return results
    
    async def shutdown_module(self, module_name: str) -> bool:
        """
        Shutdown a specific module.
        
        Args:
            module_name: Module name
            
        Returns:
            True if shutdown successful
        """
        adapter = self.get_module(module_name)
        if not adapter:
            logger.error(f"Module {module_name} not found")
            return False
        
        if module_name not in self._initialized:
            logger.debug(f"Module {module_name} not initialized")
            return True
        
        success = await adapter.shutdown()
        
        if success:
            self._initialized.discard(module_name)
            logger.info(f"Module {module_name} shut down")
        else:
            logger.error(f"Module {module_name} shutdown failed")
        
        return success
    
    async def route_task(
        self,
        task_data: Dict[str, Any],
        preferred_module: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Route a task to an appropriate module.
        
        Args:
            task_data: Task data
            preferred_module: Preferred module name (optional)
            
        Returns:
            Task result
        """
        # Try preferred module first
        if preferred_module:
            adapter = self.get_module(preferred_module)
            if adapter and adapter.status == ModuleStatus.ACTIVE:
                if await adapter.can_handle_task(task_data):
                    return await adapter.process_task(task_data)
        
        # Find module that can handle task
        with self._lock:
            for module_name, adapter in self._modules.items():
                if adapter.status == ModuleStatus.ACTIVE:
                    if await adapter.can_handle_task(task_data):
                        logger.debug(f"Routing task to {module_name}")
                        return await adapter.process_task(task_data)
        
        # No module found - check if we should auto-create
        error_msg = f"No active module can handle task: {task_data.get('type', 'unknown')}"
        
        # Try to detect capability gap and auto-create module
        if hasattr(self, '_auto_creator') and self._auto_creator:
            required_capability = task_data.get('type') or task_data.get('capability') or 'unknown'
            gap_id = self._auto_creator.detect_capability_gap(
                required_capability=required_capability,
                task_description=str(task_data),
                error_context={"task": task_data}
            )
            
            if gap_id and self._auto_creator.auto_create_enabled:
                logger.info(f"Auto-creating module for capability: {required_capability} (gap_id: {gap_id})")
                # Trigger async module creation in background
                import asyncio
                try:
                    # Create task to run module creation asynchronously
                    loop = asyncio.get_event_loop()
                    asyncio.create_task(
                        self._auto_creator.create_module_for_gap(gap_id)
                    )
                    logger.info(f"Background module creation task started for gap: {gap_id}")
                except RuntimeError:
                    # No event loop running, schedule for later
                    logger.warning(f"Could not start async module creation (no event loop). Gap {gap_id} will be created on next system cycle.")
        
        return {
            "success": False,
            "error": error_msg,
            "suggested_action": "Module may be auto-created if capability gap detected",
            "gap_id": gap_id if (hasattr(self, '_auto_creator') and self._auto_creator) else None
        }
    
    def get_registry_status(self) -> Dict[str, Any]:
        """
        Get registry status and statistics.
        
        Returns:
            Status dictionary
        """
        with self._lock:
            modules_by_status = {}
            for status in ModuleStatus:
                modules_by_status[status.value] = len([
                    m for m in self._modules.values()
                    if m.status == status
                ])
            
            return {
                "total_modules": len(self._modules),
                "initialized_modules": len(self._initialized),
                "modules_by_status": modules_by_status,
                "module_names": list(self._modules.keys())
            }
    
    def get_module_status(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific module.
        
        Args:
            module_name: Module name
            
        Returns:
            Status dictionary or None
        """
        adapter = self.get_module(module_name)
        if adapter:
            return adapter.get_status()
        return None
    
    def set_auto_creator(self, auto_creator):
        """
        Set the AutoModuleCreator instance for automatic module creation.
        
        Args:
            auto_creator: AutoModuleCreator instance
        """
        self._auto_creator = auto_creator
        if auto_creator:
            auto_creator.registry = self


# Example usage
if __name__ == "__main__":
    async def test_registry():
        """Test the ModuleRegistry."""
        registry = ModuleRegistry()
        
        # Create test modules
        class TestModule1:
            async def process(self, task_data, **kwargs):
                return {"success": True, "module": "test1"}
            
            async def can_handle(self, task_data):
                return task_data.get("type") == "test1"
        
        class TestModule2:
            async def process(self, task_data, **kwargs):
                return {"success": True, "module": "test2"}
            
            async def can_handle(self, task_data):
                return task_data.get("type") == "test2"
        
        # Register modules
        registry.register_simple("test1", TestModule1(), priority=5)
        registry.register_simple("test2", TestModule2(), priority=6, dependencies=["test1"])
        
        # Initialize all
        results = await registry.initialize_all()
        print(f"Initialization results: {results}")
        
        # Get status
        status = registry.get_registry_status()
        print(f"Registry status: {status}")
        
        # Route task
        result = await registry.route_task({"type": "test1", "task_id": "task_1"})
        print(f"Task result: {result}")
        
        # Shutdown all
        await registry.shutdown_all()
    
    asyncio.run(test_registry())

