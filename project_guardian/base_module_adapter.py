# project_guardian/base_module_adapter.py
# BaseModuleAdapter: Standardized Interface for Module Integration
# Based on ElysiaLoop-Core Event Loop Design

import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, Awaitable
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ModuleStatus(Enum):
    """Module status states."""
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class BaseModuleAdapter(ABC):
    """
    Base adapter class for integrating modules with ElysiaLoop-Core.
    Provides standardized interface for module lifecycle, task handling, and events.
    """
    
    def __init__(
        self,
        module_name: str,
        module_instance: Any,
        priority: int = 5,
        dependencies: Optional[List[str]] = None
    ):
        """
        Initialize module adapter.
        
        Args:
            module_name: Unique name for this module
            module_instance: The actual module instance
            priority: Default priority for tasks (1-10, higher = more urgent)
            dependencies: List of module names this module depends on
        """
        self.module_name = module_name
        self.module_instance = module_instance
        self.priority = priority
        self.dependencies = dependencies or []
        
        # Status tracking
        self.status = ModuleStatus.INACTIVE
        self.last_activity = None
        self.error_count = 0
        self.error_history: List[Dict[str, Any]] = []
        
        # Metrics
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.total_processing_time = 0.0
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Configuration
        self.config: Dict[str, Any] = {}
    
    async def initialize(self) -> bool:
        """
        Initialize the module.
        Called during system startup.
        
        Returns:
            True if initialization successful
        """
        try:
            self.status = ModuleStatus.INITIALIZING
            logger.info(f"[{self.module_name}] Initializing...")
            
            # Call module-specific initialization
            result = await self._initialize_module()
            
            if result:
                self.status = ModuleStatus.ACTIVE
                self.last_activity = datetime.now()
                logger.info(f"[{self.module_name}] Initialized successfully")
                await self._emit_event("module_initialized", {"module": self.module_name})
            else:
                self.status = ModuleStatus.ERROR
                logger.error(f"[{self.module_name}] Initialization failed")
            
            return result
            
        except Exception as e:
            self.status = ModuleStatus.ERROR
            self._record_error("initialization", str(e))
            logger.error(f"[{self.module_name}] Initialization error: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """
        Shutdown the module gracefully.
        Called during system shutdown.
        
        Returns:
            True if shutdown successful
        """
        try:
            logger.info(f"[{self.module_name}] Shutting down...")
            self.status = ModuleStatus.SHUTDOWN
            
            # Call module-specific shutdown
            result = await self._shutdown_module()
            
            await self._emit_event("module_shutdown", {"module": self.module_name})
            logger.info(f"[{self.module_name}] Shutdown complete")
            
            return result
            
        except Exception as e:
            self._record_error("shutdown", str(e))
            logger.error(f"[{self.module_name}] Shutdown error: {e}")
            return False
    
    async def pause(self) -> bool:
        """Pause module operations."""
        if self.status == ModuleStatus.ACTIVE:
            self.status = ModuleStatus.PAUSED
            await self._emit_event("module_paused", {"module": self.module_name})
            logger.info(f"[{self.module_name}] Paused")
            return True
        return False
    
    async def resume(self) -> bool:
        """Resume module operations."""
        if self.status == ModuleStatus.PAUSED:
            self.status = ModuleStatus.ACTIVE
            await self._emit_event("module_resumed", {"module": self.module_name})
            logger.info(f"[{self.module_name}] Resumed")
            return True
        return False
    
    async def process_task(
        self,
        task_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a task assigned to this module.
        
        Args:
            task_data: Task data dictionary
            context: Optional execution context
            
        Returns:
            Task result dictionary
        """
        if self.status != ModuleStatus.ACTIVE:
            return {
                "success": False,
                "error": f"Module {self.module_name} is not active (status: {self.status.value})"
            }
        
        try:
            start_time = datetime.now()
            self.last_activity = start_time
            
            # Call module-specific task processing
            result = await self._process_task(task_data, context or {})
            
            # Update metrics
            elapsed = (datetime.now() - start_time).total_seconds()
            self.tasks_processed += 1
            self.total_processing_time += elapsed
            
            await self._emit_event("task_completed", {
                "module": self.module_name,
                "task": task_data.get("task_id"),
                "success": result.get("success", False),
                "duration": elapsed
            })
            
            return result
            
        except Exception as e:
            self.tasks_failed += 1
            self._record_error("task_processing", str(e))
            logger.error(f"[{self.module_name}] Task processing error: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "module": self.module_name
            }
    
    async def can_handle_task(self, task_data: Dict[str, Any]) -> bool:
        """
        Check if this module can handle a given task.
        
        Args:
            task_data: Task data dictionary
            
        Returns:
            True if module can handle the task
        """
        return await self._can_handle_task(task_data)
    
    def get_capabilities(self) -> List[str]:
        """
        Get list of capabilities this module provides.
        
        Returns:
            List of capability strings
        """
        return self._get_capabilities()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get module status and metrics.
        
        Returns:
            Status dictionary
        """
        avg_time = (
            self.total_processing_time / self.tasks_processed
            if self.tasks_processed > 0 else 0.0
        )
        
        return {
            "module_name": self.module_name,
            "status": self.status.value,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "error_count": self.error_count,
            "avg_processing_time": avg_time,
            "capabilities": self.get_capabilities(),
            "config": self.config
        }
    
    def configure(self, config: Dict[str, Any]):
        """
        Update module configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config.update(config)
        logger.debug(f"[{self.module_name}] Configuration updated")
    
    def on_event(self, event_type: str, handler: Callable):
        """
        Register an event handler.
        
        Args:
            event_type: Event type to listen for
            handler: Handler function (async or sync)
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def _record_error(self, context: str, error: str):
        """Record an error in history."""
        self.error_count += 1
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "error": error
        }
        self.error_history.append(error_entry)
        
        # Keep only last 50 errors
        if len(self.error_history) > 50:
            self.error_history = self.error_history[-50:]
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit an event to registered handlers."""
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[{self.module_name}] Event handler error: {e}")
    
    # Abstract methods to be implemented by subclasses
    
    @abstractmethod
    async def _initialize_module(self) -> bool:
        """
        Module-specific initialization.
        To be implemented by subclasses.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def _shutdown_module(self) -> bool:
        """
        Module-specific shutdown.
        To be implemented by subclasses.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def _process_task(self, task_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a task.
        To be implemented by subclasses.
        
        Args:
            task_data: Task data
            context: Execution context
            
        Returns:
            Task result
        """
        pass
    
    @abstractmethod
    async def _can_handle_task(self, task_data: Dict[str, Any]) -> bool:
        """
        Check if module can handle a task.
        To be implemented by subclasses.
        
        Args:
            task_data: Task data
            
        Returns:
            True if can handle
        """
        pass
    
    @abstractmethod
    def _get_capabilities(self) -> List[str]:
        """
        Get module capabilities.
        To be implemented by subclasses.
        
        Returns:
            List of capability strings
        """
        pass


# Example concrete implementation
class SimpleModuleAdapter(BaseModuleAdapter):
    """
    Simple adapter for modules with basic async methods.
    """
    
    def __init__(
        self,
        module_name: str,
        module_instance: Any,
        priority: int = 5,
        dependencies: Optional[List[str]] = None,
        process_method: Optional[str] = None,
        can_handle_method: Optional[str] = None
    ):
        """
        Initialize simple adapter.
        
        Args:
            module_name: Module name
            module_instance: Module instance
            priority: Priority
            dependencies: Dependencies
            process_method: Method name for task processing (default: 'process' or 'handle_task')
            can_handle_method: Method name for can_handle check (default: 'can_handle')
        """
        super().__init__(module_name, module_instance, priority, dependencies)
        
        # Auto-detect methods
        self.process_method = process_method
        self.can_handle_method = can_handle_method
        
        if not self.process_method:
            if hasattr(module_instance, 'process'):
                self.process_method = 'process'
            elif hasattr(module_instance, 'handle_task'):
                self.process_method = 'handle_task'
            else:
                self.process_method = None
        
        if not self.can_handle_method:
            if hasattr(module_instance, 'can_handle'):
                self.can_handle_method = 'can_handle'
            else:
                self.can_handle_method = None
    
    async def _initialize_module(self) -> bool:
        """Initialize module."""
        if hasattr(self.module_instance, 'initialize'):
            if asyncio.iscoroutinefunction(self.module_instance.initialize):
                return await self.module_instance.initialize()
            else:
                return self.module_instance.initialize()
        return True  # No initialization needed
    
    async def _shutdown_module(self) -> bool:
        """Shutdown module."""
        if hasattr(self.module_instance, 'shutdown'):
            if asyncio.iscoroutinefunction(self.module_instance.shutdown):
                return await self.module_instance.shutdown()
            else:
                return self.module_instance.shutdown()
        return True  # No shutdown needed
    
    async def _process_task(self, task_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Process task using detected method."""
        if not self.process_method:
            return {
                "success": False,
                "error": "No process method found"
            }
        
        method = getattr(self.module_instance, self.process_method)
        
        if asyncio.iscoroutinefunction(method):
            result = await method(task_data, **context)
        else:
            result = method(task_data, **context)
        
        # Normalize result
        if isinstance(result, dict):
            return result
        else:
            return {"success": True, "result": result}
    
    async def _can_handle_task(self, task_data: Dict[str, Any]) -> bool:
        """Check if can handle task."""
        if not self.can_handle_method:
            # Default: can handle if process method exists
            return self.process_method is not None
        
        method = getattr(self.module_instance, self.can_handle_method)
        
        if asyncio.iscoroutinefunction(method):
            return await method(task_data)
        else:
            return method(task_data)
    
    def _get_capabilities(self) -> List[str]:
        """Get capabilities from module if available."""
        if hasattr(self.module_instance, 'get_capabilities'):
            caps = self.module_instance.get_capabilities()
            if isinstance(caps, list):
                return caps
        
        # Default capability based on module name
        return [self.module_name]


# Example usage
if __name__ == "__main__":
    async def test_adapter():
        """Test the BaseModuleAdapter."""
        
        # Create a simple test module
        class TestModule:
            async def process(self, task_data, **kwargs):
                return {"success": True, "result": f"Processed: {task_data.get('task_id')}"}
            
            def can_handle(self, task_data):
                return task_data.get("type") == "test"
        
        # Create adapter
        test_module = TestModule()
        adapter = SimpleModuleAdapter(
            module_name="test_module",
            module_instance=test_module,
            priority=5
        )
        
        # Initialize
        await adapter.initialize()
        print(f"Status: {adapter.get_status()}")
        
        # Process task
        result = await adapter.process_task({
            "task_id": "task_1",
            "type": "test"
        })
        print(f"Task result: {result}")
        
        # Shutdown
        await adapter.shutdown()
    
    asyncio.run(test_adapter())

