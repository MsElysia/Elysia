# project_guardian/system_orchestrator.py
# SystemOrchestrator: Unified System Control and Coordination
# Brings together all Elysia components into a cohesive operational system

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from threading import Lock

try:
    from .module_registry import ModuleRegistry
    from .runtime_loop_core import RuntimeLoop
    from .elysia_loop_core import ElysiaLoopCore
    from .timeline_memory import TimelineMemory
    from .global_task_queue import GlobalTaskQueue
    from .conversation_context_manager import ConversationContextManager
    from .memory import MemoryCore
    from .persona_forge import PersonaForge
    from .ask_ai import AskAI
    from .voice_thread import VoiceThread
    from .heartbeat import Heartbeat
    from .runtime_bootstrap import RuntimeBootstrap
    from .global_priority_registry import GlobalPriorityRegistry
    from .auto_module_creator import AutoModuleCreator
    try:
        from .ui_control_panel import UIControlPanel
        UI_AVAILABLE = True
    except ImportError:
        UI_AVAILABLE = False
        UIControlPanel = None
except ImportError:
    from module_registry import ModuleRegistry
    from runtime_loop_core import RuntimeLoop
    from elysia_loop_core import ElysiaLoopCore
    from timeline_memory import TimelineMemory
    from global_task_queue import GlobalTaskQueue
    from conversation_context_manager import ConversationContextManager
    from memory import MemoryCore
    from persona_forge import PersonaForge
    from ask_ai import AskAI
    from voice_thread import VoiceThread
    from heartbeat import Heartbeat
    from runtime_bootstrap import RuntimeBootstrap
    from global_priority_registry import GlobalPriorityRegistry
    try:
        from auto_module_creator import AutoModuleCreator
    except ImportError:
        AutoModuleCreator = None
    try:
        from ui_control_panel import UIControlPanel
        UI_AVAILABLE = True
    except ImportError:
        UI_AVAILABLE = False
        UIControlPanel = None

logger = logging.getLogger(__name__)


class SystemOrchestrator:
    """
    Central orchestrator that unifies all Elysia system components.
    Provides unified interface for system initialization, operation, and coordination.
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize SystemOrchestrator.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._lock = Lock()
        self._running = False
        self._initialized = False
        
        # Core components
        self.module_registry: Optional[ModuleRegistry] = None
        self.elysia_loop: Optional[ElysiaLoopCore] = None
        self.runtime_loop: Optional[RuntimeLoop] = None
        self.timeline_memory: Optional[TimelineMemory] = None
        self.task_queue: Optional[GlobalTaskQueue] = None
        self.conversation_manager: Optional[ConversationContextManager] = None
        self.memory: Optional[MemoryCore] = None
        self.persona: Optional[PersonaForge] = None
        self.ask_ai: Optional[AskAI] = None
        self.voice: Optional[VoiceThread] = None
        self.heartbeat: Optional[Heartbeat] = None
        self.bootstrap: Optional[RuntimeBootstrap] = None
        self.priority_registry: Optional[GlobalPriorityRegistry] = None
        self.auto_module_creator: Optional[AutoModuleCreator] = None
        self.ui_control_panel: Optional[UIControlPanel] = None
        self._guardian_owns_panel: bool = False  # Defer to GuardianCore when present
        
        # System state
        self.start_time: Optional[datetime] = None
        self.operational_stats: Dict[str, Any] = {
            "total_tasks_processed": 0,
            "total_conversations": 0,
            "uptime_seconds": 0
        }
    
    async def initialize(
        self,
        initialize_components: bool = True,
        auto_register_modules: bool = True
    ) -> bool:
        """
        Initialize the entire Elysia system.
        
        Args:
            initialize_components: If True, initialize all core components
            auto_register_modules: If True, auto-register discovered modules
            
        Returns:
            True if initialization successful
        """
        if self._initialized:
            logger.warning("System already initialized")
            return True
        
        try:
            logger.info("=" * 60)
            logger.info("Initializing Elysia System")
            logger.info("=" * 60)
            
            # Initialize core infrastructure
            await self._initialize_core_components()
            
            # Initialize operational components
            if initialize_components:
                await self._initialize_operational_components()
            
            # Auto-register modules if requested
            if auto_register_modules:
                await self._auto_register_modules()
            
            # Initialize all registered modules
            if self.module_registry:
                init_results = await self.module_registry.initialize_all(ignore_errors=True)
                successful = sum(1 for v in init_results.values() if v)
                logger.info(f"Initialized {successful}/{len(init_results)} modules")
            
            # Start operational systems
            await self._start_operational_systems()
            
            self._initialized = True
            self.start_time = datetime.now()
            
            logger.info("=" * 60)
            logger.info("Elysia System Initialized Successfully")
            logger.info("=" * 60)
            
            # Generate boot message (non-blocking, skip if no AI available)
            if self.voice and self.ask_ai:
                try:
                    boot_msg = await asyncio.wait_for(
                        self.voice.generate_boot_message(),
                        timeout=5.0
                    )
                    logger.info(f"Boot Message: {boot_msg}")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Could not generate boot message: {e}")
                    logger.info("Elysia is online and ready. Systems initialized.")
            else:
                logger.info("Elysia is online and ready. Systems initialized.")
            
            return True
            
        except Exception as e:
            logger.error(f"System initialization failed: {e}", exc_info=True)
            return False
    
    async def _initialize_core_components(self):
        """Initialize core infrastructure components."""
        logger.info("Initializing core infrastructure...")
        
        # Priority Registry (foundational)
        logger.info("  -> Creating GlobalPriorityRegistry...")
        self.priority_registry = GlobalPriorityRegistry()
        logger.info("[OK] GlobalPriorityRegistry initialized")
        
        # Timeline Memory (foundational - for event logging)
        logger.info("  -> Creating TimelineMemory...")
        timeline_db_path = self.config.get("timeline_db_path", "data/timeline_memory.db")
        self.timeline_memory = TimelineMemory(db_path=timeline_db_path)
        logger.info("[OK] TimelineMemory initialized")
        
        # Task Queue
        logger.info("  -> Creating GlobalTaskQueue...")
        self.task_queue = GlobalTaskQueue()
        logger.info("[OK] GlobalTaskQueue initialized")
        
        # Module Registry
        logger.info("  -> Creating ModuleRegistry...")
        self.module_registry = ModuleRegistry()
        logger.info("[OK] ModuleRegistry initialized")
        
        # ElysiaLoopCore (MAIN EVENT LOOP COORDINATOR - Foundation)
        logger.info("  -> Creating ElysiaLoopCore (main event loop coordinator)...")
        self.elysia_loop = ElysiaLoopCore(
            timeline_memory=self.timeline_memory,
            module_registry=self.module_registry
        )
        # Link task queue to ElysiaLoopCore
        if self.elysia_loop.task_queue != self.task_queue:
            self.elysia_loop.task_queue = self.task_queue
        logger.info("[OK] ElysiaLoopCore initialized")
        
        # Runtime Loop (uses ElysiaLoopCore)
        logger.info("  -> Creating RuntimeLoop (with ElysiaLoopCore integration)...")
        self.runtime_loop = RuntimeLoop(elysia_loop=self.elysia_loop)
        # Link task queue if available
        if hasattr(self.runtime_loop, 'task_queue') and self.task_queue:
            self.runtime_loop.task_queue = self.task_queue
        logger.info("[OK] RuntimeLoop initialized")
        
        # Bootstrap tracker
        logger.info("  -> Creating RuntimeBootstrap...")
        self.bootstrap = RuntimeBootstrap()
        # Bootstrap will track initialization automatically
        logger.info("[OK] RuntimeBootstrap initialized")
        
        # AutoModuleCreator (for self-extending capability)
        if AutoModuleCreator and self.ask_ai:
            logger.info("  -> Creating AutoModuleCreator...")
            try:
                from .mutation_engine import MutationEngine
                from .trust_eval_action import TrustEvalAction
            except ImportError:
                from mutation_engine import MutationEngine
                from trust_eval_action import TrustEvalAction
            
            mutation_engine = MutationEngine(ask_ai=self.ask_ai) if self.ask_ai else None
            trust_eval = TrustEvalAction() if hasattr(self, 'trust_eval') else None
            
            self.auto_module_creator = AutoModuleCreator(
                module_registry=self.module_registry,
                mutation_engine=mutation_engine,
                ask_ai=self.ask_ai,
                trust_eval=trust_eval,
                project_root=".",
                modules_dir="project_guardian"
            )
            
            # Link to module registry
            if self.module_registry:
                self.module_registry.set_auto_creator(self.auto_module_creator)
            
            logger.info("[OK] AutoModuleCreator initialized")
        else:
            logger.info("[SKIP] AutoModuleCreator not available (requires AskAI)")
        
        # UI Control Panel (optional) — defer to GuardianCore when it already owns the panel
        guardian = self.config.get("guardian_core")
        if guardian is not None and getattr(guardian, "ui_panel", None) is not None:
            self._guardian_owns_panel = True
            logger.info("[DASHBOARD] SystemOrchestrator deferring to existing GuardianCore-owned panel")
        else:
            ui_enabled = self.config.get("ui_enabled", False)
            if ui_enabled and UI_AVAILABLE and UIControlPanel:
                logger.info("  -> Creating UIControlPanel...")
                try:
                    ui_host = self.config.get("ui_host", "127.0.0.1")
                    ui_port = self.config.get("ui_port", 5000)
                    self.ui_control_panel = UIControlPanel(
                        orchestrator=self,
                        host=ui_host,
                        port=ui_port
                    )
                    logger.info("[OK] UIControlPanel initialized")
                except Exception as e:
                    logger.warning(f"[WARN] UIControlPanel initialization failed: {e}")
                    self.ui_control_panel = None
            elif ui_enabled and not UI_AVAILABLE:
                logger.info("[SKIP] UIControlPanel not available (install flask flask-socketio)")
    
    async def _initialize_operational_components(self):
        """Initialize operational components."""
        logger.info("Initializing operational components...")
        
        # Memory (use canonical memory_filepath via resolver)
        from .memory_paths import get_memory_file_path
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        memory_filepath = get_memory_file_path(self.config, project_root)
        logger.info("  -> Creating MemoryCore...")
        self.memory = MemoryCore(filepath=memory_filepath)
        logger.info("[OK] MemoryCore initialized")
        
        # Persona (may do file I/O in __init__)
        logger.info("  -> Creating PersonaForge (may load from disk)...")
        self.persona = PersonaForge(
            storage_path=self.config.get("persona_path", "data/personas.json")
        )
        logger.info("[OK] PersonaForge initialized")
        
        # AskAI (if API keys provided)
        logger.info("  -> Creating AskAI...")
        openai_key = self.config.get("openai_api_key")
        claude_key = self.config.get("claude_api_key")
        
        if openai_key or claude_key:
            self.ask_ai = AskAI(
                openai_api_key=openai_key,
                claude_api_key=claude_key
            )
            logger.info("[OK] AskAI initialized")
        else:
            logger.warning("[WARN] AskAI not configured (no API keys provided)")
            self.ask_ai = None
        
        # Voice Thread
        logger.info("  -> Creating VoiceThread...")
        self.voice = VoiceThread(
            persona_forge=self.persona,
            ask_ai=self.ask_ai
        )
        logger.info("[OK] VoiceThread initialized")
        
        # Conversation Context Manager (may do file I/O in __init__)
        logger.info("  -> Creating ConversationContextManager (may load from disk)...")
        self.conversation_manager = ConversationContextManager(
            persona_forge=self.persona,
            memory_core=self.memory,
            ask_ai=self.ask_ai,
            voice_thread=self.voice,
            storage_path=self.config.get("conversation_path", "data/conversation_context.json")
        )
        logger.info("[OK] ConversationContextManager initialized")
        
        # Heartbeat (may do file I/O in __init__)
        logger.info("  -> Creating Heartbeat (may load from disk)...")
        self.heartbeat = Heartbeat(
            storage_path=self.config.get("heartbeat_path", "data/heartbeat.json")
        )
        logger.info("[OK] Heartbeat initialized")
    
    async def _auto_register_modules(self):
        """Auto-register available modules."""
        if not self.module_registry:
            return
        
        logger.info("Auto-registering modules...")
        
        # Register core modules with the registry
        # This enables them to be managed through the module system
        
        # Example: Register runtime loop
        # if self.runtime_loop:
        #     self.module_registry.register_simple(
        #         "runtime_loop",
        #         self.runtime_loop,
        #         priority=10,
        #         auto_initialize=False
        #     )
        
        # Modules will be registered as they're created/imported
        # This is a placeholder for future auto-discovery
    
    async def _start_operational_systems(self):
        """Start operational background systems."""
        logger.info("Starting operational systems...")
        
        # Start runtime loop if available
        if self.runtime_loop:
            # Runtime loop starts its own background task
            logger.info("[OK] RuntimeLoop operational")
        
        # Start heartbeat monitoring
        if self.heartbeat:
            self.heartbeat.start()  # Note: start() is not async
            logger.info("[OK] Heartbeat monitoring started")
        
        # Bootstrap tracking is automatic - no need to call anything
        if self.bootstrap:
            logger.info("[OK] Bootstrap tracking active")
    
    async def shutdown(self, graceful: bool = True) -> bool:
        """
        Shutdown the entire system gracefully.
        
        Args:
            graceful: If True, wait for tasks to complete
            
        Returns:
            True if shutdown successful
        """
        logger.info("=" * 60)
        logger.info("Shutting down Elysia System")
        logger.info("=" * 60)
        
        try:
            self._running = False
            
            # Shutdown all modules
            if self.module_registry:
                shutdown_results = await self.module_registry.shutdown_all()
                successful = sum(1 for v in shutdown_results.values() if v)
                logger.info(f"Shut down {successful}/{len(shutdown_results)} modules")
            
            # Stop heartbeat
            if self.heartbeat:
                await self.heartbeat.stop_monitoring()
            
            # Stop runtime loop
            if self.runtime_loop:
                await self.runtime_loop.stop()
            
            # Stop ElysiaLoopCore (main event loop coordinator)
            if self.elysia_loop:
                self.elysia_loop.stop()
                logger.info("[OK] ElysiaLoopCore stopped")
            
            logger.info("=" * 60)
            logger.info("Elysia System Shutdown Complete")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)
            return False
    
    async def start(self) -> bool:
        """
        Start the system (after initialization).
        
        Returns:
            True if started successfully
        """
        if not self._initialized:
            logger.error("System not initialized. Call initialize() first.")
            return False
        
        if self._running:
            logger.warning("System already running")
            return True
        
        self._running = True
        
        # Start ElysiaLoopCore (main event loop coordinator)
        if self.elysia_loop:
            self.elysia_loop.start()
            logger.info("[OK] ElysiaLoopCore started")
        
        # Start main operational loop (RuntimeLoop will use ElysiaLoopCore)
        if self.runtime_loop:
            self.runtime_loop.start()  # Note: start() is not async
            logger.info("[OK] RuntimeLoop started")
        
        # Start UI Control Panel if enabled (skip when GuardianCore owns the panel)
        if self._guardian_owns_panel:
            logger.info("[DASHBOARD] SystemOrchestrator deferring to existing GuardianCore-owned panel")
        elif self.ui_control_panel:
            self.ui_control_panel.start(source="SystemOrchestrator.start")
            logger.info(f"[OK] UI Control Panel started at http://{self.ui_control_panel.host}:{self.ui_control_panel.port}")
        
        logger.info("Elysia System is now running")
        return True
    
    async def process_conversation(
        self,
        user_message: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Process a conversation message with full system context.
        
        Args:
            user_message: User's message
            session_id: Optional session ID
            
        Returns:
            System response
        """
        if not self.conversation_manager:
            return "System not fully initialized"
        
        # Use conversation manager to generate response with full context
        response = await self.conversation_manager.respond_with_context(
            user_message,
            session_id
        )
        
        # Update stats
        self.operational_stats["total_conversations"] += 1
        
        return response
    
    async def submit_task(
        self,
        task_type: str,
        task_data: Dict[str, Any],
        priority: int = 5
    ) -> str:
        """
        Submit a task to the system.
        
        Args:
            task_type: Task type identifier
            task_data: Task data dictionary
            priority: Task priority (1-10)
            
        Returns:
            Task ID
        """
        if not self.task_queue:
            raise RuntimeError("Task queue not initialized")
        
        task_id = await self.task_queue.enqueue(
            task_type=task_type,
            data=task_data,
            priority=priority
        )
        
        logger.info(f"Task submitted: {task_id} (type: {task_type}, priority: {priority})")
        return task_id
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status.
        
        Returns:
            System status dictionary
        """
        uptime = (
            (datetime.now() - self.start_time).total_seconds()
            if self.start_time else 0
        )
        
        status = {
            "system": {
                "initialized": self._initialized,
                "running": self._running,
                "uptime_seconds": uptime,
                "start_time": self.start_time.isoformat() if self.start_time else None
            },
            "components": {
                "module_registry": self.module_registry is not None,
                "runtime_loop": self.runtime_loop is not None,
                "task_queue": self.task_queue is not None,
                "conversation_manager": self.conversation_manager is not None,
                "memory": self.memory is not None,
                "persona": self.persona is not None,
                "ask_ai": self.ask_ai is not None,
                "voice": self.voice is not None,
                "heartbeat": self.heartbeat is not None
            },
            "statistics": self.operational_stats.copy()
        }
        
        # Add module registry status
        if self.module_registry:
            status["modules"] = self.module_registry.get_registry_status()
        
        # Add task queue status
        if self.task_queue:
            status["task_queue"] = {
                "pending": self.task_queue.get_queue_size(),
                "processing": self.task_queue.get_processing_count()
            }
        
        # Add heartbeat status
        if self.heartbeat:
            status["heartbeat"] = self.heartbeat.get_status()
        
        return status
    
    def get_component(self, component_name: str) -> Any:
        """
        Get a system component by name.
        
        Args:
            component_name: Component name
            
        Returns:
            Component instance or None
        """
        components = {
            "module_registry": self.module_registry,
            "runtime_loop": self.runtime_loop,
            "task_queue": self.task_queue,
            "conversation_manager": self.conversation_manager,
            "memory": self.memory,
            "persona": self.persona,
            "ask_ai": self.ask_ai,
            "voice": self.voice,
            "heartbeat": self.heartbeat,
            "bootstrap": self.bootstrap,
            "priority_registry": self.priority_registry
        }
        
        return components.get(component_name)
    
    async def update_config(self, updates: Dict[str, Any]):
        """
        Update system configuration.
        
        Args:
            updates: Configuration updates
        """
        self.config.update(updates)
        
        # Apply configuration updates to components
        if "priority" in updates and self.priority_registry:
            await self.priority_registry.set_priority(
                "system",
                updates["priority"]
            )


# Example usage
if __name__ == "__main__":
    async def test_system():
        """Test the SystemOrchestrator."""
        orchestrator = SystemOrchestrator(
            config={
                "memory_path": "data/memory.json",
                "persona_path": "data/personas.json"
            }
        )
        
        # Initialize system
        success = await orchestrator.initialize()
        print(f"Initialization: {success}")
        
        # Get status
        status = orchestrator.get_system_status()
        print(f"System status: {status['system']}")
        
        # Process conversation
        response = await orchestrator.process_conversation(
            "Hello, what's my current status?"
        )
        print(f"Response: {response}")
        
        # Shutdown
        await orchestrator.shutdown()
    
    asyncio.run(test_system())

