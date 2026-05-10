# project_guardian/system_orchestrator.py
# SystemOrchestrator: Unified System Control and Coordination
# Brings together all Elysia components into a cohesive operational system

import logging
import asyncio
import inspect
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
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
    from .task_assignment_engine import configure_task_assignment_engine
    from .implementer.implementer_core import ImplementerCore
    from .income_executor import IncomeExecutor
    from .intelligent_task_distribution import IntelligentTaskDistribution
    from .proposal_api import ProposalAPI
    from .slave_deployment import SlaveDeployment
    from .chatgpt_export_import import import_chatgpt_export
    from .credit_spend_log import CreditSpendLog
    from .error_handler import ErrorHandler
    from .feedback_loop_core import FeedbackLoopCore
    from .file_writer import FileWriter
    from .mutation_autonomy_sandbox import SANDBOX_VERSION as MUTATION_SANDBOX_VERSION
    from .ai_mutation_validator import AIMutationValidator, configure_ai_validator_integration
    from .digital_safehouse import DigitalSafehouse
    from .dream_engine import DreamEngine
    from .mutation_sandbox import MutationSandbox
    from .mutation_publisher import configure_mutation_publisher
    from .mutation_review_manager import configure_mutation_review_manager
    from .mutation_router import configure_mutation_router
    from .eai_safety import configure_eai_safety_framework, load_eai_safety_config
    from .review_queue import ReviewQueue
    from .approval_store import ApprovalStore
    from . import tool_executor as tool_executor_module
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
    from task_assignment_engine import configure_task_assignment_engine
    from implementer.implementer_core import ImplementerCore
    from income_executor import IncomeExecutor
    from intelligent_task_distribution import IntelligentTaskDistribution
    from proposal_api import ProposalAPI
    from slave_deployment import SlaveDeployment
    from chatgpt_export_import import import_chatgpt_export
    from credit_spend_log import CreditSpendLog
    from error_handler import ErrorHandler
    from feedback_loop_core import FeedbackLoopCore
    from file_writer import FileWriter
    from mutation_autonomy_sandbox import SANDBOX_VERSION as MUTATION_SANDBOX_VERSION
    from ai_mutation_validator import AIMutationValidator, configure_ai_validator_integration
    from digital_safehouse import DigitalSafehouse
    from dream_engine import DreamEngine
    from mutation_sandbox import MutationSandbox
    from mutation_publisher import configure_mutation_publisher
    from mutation_review_manager import configure_mutation_review_manager
    from mutation_router import configure_mutation_router
    from eai_safety import configure_eai_safety_framework, load_eai_safety_config
    from review_queue import ReviewQueue
    from approval_store import ApprovalStore
    import tool_executor as tool_executor_module
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


class ToolExecutorSurface:
    """Bound execution surface for tool-executor API routing."""

    def __init__(self, guardian: Any, allowed_tools: List[str]):
        self.guardian = guardian
        self._allowed_tools = set(allowed_tools)

    def get_allowed_tools(self) -> List[str]:
        return sorted(self._allowed_tools)

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        return tool_executor_module.execute_action(
            action=action,
            allowed_tools=self._allowed_tools,
            guardian=self.guardian,
        )


class _ProposalApiAdapter:
    """Adapter providing architect-like methods for ProposalAPI."""

    def __init__(self, surface: "ProposalApiSurface"):
        self._surface = surface

    def get_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._surface.list_proposals(status_filter=status_filter)

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        return self._surface.get_proposal(proposal_id)

    def get_status_report(self) -> Dict[str, Any]:
        return self._surface.get_status_report()

    def get_webscout_status(self) -> Dict[str, Any]:
        return self._surface.get_webscout_status()

    def create_research_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "create_research_proposal disabled on compatibility surface"}

    def add_research_to_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "add_research_to_proposal disabled on compatibility surface"}

    def add_design_to_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "add_design_to_proposal disabled on compatibility surface"}

    def add_implementation_to_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "add_implementation_to_proposal disabled on compatibility surface"}

    def approve_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "approve_proposal disabled on compatibility surface"}

    def reject_proposal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "error", "message": "reject_proposal disabled on compatibility surface"}


class ProposalApiSurface:
    """Filesystem-backed proposal read surface with optional ProposalAPI app."""

    def __init__(
        self,
        proposals_root: Path,
        *,
        build_flask_app: bool = False,
        host: str = "127.0.0.1",
        port: int = 5000,
    ):
        self.proposals_root = Path(proposals_root)
        self.proposals_root.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.port = int(port)
        self._proposal_api_app = None
        if build_flask_app:
            try:
                adapter = _ProposalApiAdapter(self)
                self._proposal_api_app = ProposalAPI(adapter, host=self.host, port=self.port)
            except Exception as e:
                logger.warning("[WARN] ProposalAPI app initialization failed: %s", e)

    def _metadata_path(self, proposal_id: str) -> Path:
        return self.proposals_root / proposal_id / "metadata.json"

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        metadata_path = self._metadata_path(proposal_id)
        if not metadata_path.exists():
            return None
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read proposal metadata for %s: %s", proposal_id, e)
            return None

    def list_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []
        for proposal_dir in sorted(self.proposals_root.iterdir()):
            if not proposal_dir.is_dir():
                continue
            metadata = self.get_proposal(proposal_dir.name)
            if not metadata:
                continue
            if status_filter is not None and metadata.get("status") != status_filter:
                continue
            proposals.append(metadata)
        return sorted(proposals, key=lambda p: p.get("created_at", ""), reverse=True)

    def get_webscout_status(self) -> Dict[str, Any]:
        proposals = self.list_proposals()
        return {
            "status": "compatibility_mode",
            "agent_name": "proposal-api-surface",
            "role": "proposal_read_surface",
            "proposals_count": len(proposals),
            "proposals": proposals[:5],
        }

    def get_status_report(self) -> Dict[str, Any]:
        proposals = self.list_proposals()
        status_counts: Dict[str, int] = {}
        for proposal in proposals:
            key = str(proposal.get("status", "unknown"))
            status_counts[key] = status_counts.get(key, 0) + 1
        return {
            "ProposalSurface": {
                "status": "active",
                "proposals_root": str(self.proposals_root),
                "proposals_count": len(proposals),
                "proposals_by_status": status_counts,
                "proposal_api_flask_app": self._proposal_api_app is not None,
            }
        }


class _NoOpSubprocessRunner:
    """Minimal subprocess runner compatibility shim for disabled deployment execution."""

    def run_command(
        self,
        command: Any,
        caller_identity: str,
        task_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        _ = (command, caller_identity, task_id, timeout)
        return {"returncode": 0, "stdout": "", "stderr": ""}


class SlaveDeploymentSurface:
    """Read-oriented surface for slave deployment state and explicit deployment actions."""

    def __init__(self, deployment: SlaveDeployment, master_controller: Any):
        self.deployment = deployment
        self.master_controller = master_controller

    def get_statistics(self) -> Dict[str, Any]:
        if self.master_controller and hasattr(self.master_controller, "get_statistics"):
            return self.master_controller.get_statistics()
        return {"total_slaves": 0, "status": "master_controller_unavailable"}

    def list_slaves(self) -> List[Dict[str, Any]]:
        if not self.master_controller or not hasattr(self.master_controller, "list_slaves"):
            return []
        entries = []
        for slave in self.master_controller.list_slaves():
            if hasattr(slave, "to_dict"):
                entries.append(slave.to_dict())
            else:
                entries.append(dict(vars(slave)))
        return entries


class ChatGptExportImportSurface:
    """Controlled surface for ChatGPT export ingestion utilities."""

    def __init__(self, default_output_dir: Path):
        self.default_output_dir = Path(default_output_dir)
        self.default_output_dir.mkdir(parents=True, exist_ok=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "default_output_dir": str(self.default_output_dir),
            "default_output_exists": self.default_output_dir.exists(),
        }

    def import_export(
        self,
        src_path: str,
        out_dir: Optional[str] = None,
        *,
        limit: Optional[int] = None,
        dry_run: bool = True,
        skip_existing: bool = True,
        force: bool = False,
    ) -> Dict[str, Any]:
        output_dir = Path(out_dir) if out_dir else self.default_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        stats = import_chatgpt_export(
            Path(src_path),
            output_dir,
            limit=limit,
            dry_run=dry_run,
            skip_existing=skip_existing,
            force=force,
        )
        return {
            "written": stats.written,
            "skipped_existing": stats.skipped_existing,
            "skipped_empty": stats.skipped_empty,
            "errors": stats.errors,
            "error_messages": list(stats.error_messages),
            "dry_run": dry_run,
            "output_dir": str(output_dir),
        }


class _MemorySink:
    """No-op memory sink for utility surface wiring."""

    def remember(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class FileWriterSurface:
    """Conservative adapter around FileWriter with status and path validation."""

    def __init__(
        self,
        *,
        repo_root: Path,
        memory: Optional[Any] = None,
        trust_matrix: Optional[Any] = None,
        review_queue: Optional[Any] = None,
        approval_store: Optional[Any] = None,
    ):
        self._writer = FileWriter(
            memory=memory or _MemorySink(),
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=repo_root,
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "repo_root": str(self._writer.repo_root),
            "has_trust_matrix": self._writer.trust_matrix is not None,
            "has_review_queue": self._writer.review_queue is not None,
            "has_approval_store": self._writer.approval_store is not None,
        }

    def validate_path(self, file_path: str) -> Dict[str, Any]:
        try:
            resolved = self._writer._validate_path_safety(file_path)
            return {"valid": True, "resolved_path": str(resolved)}
        except Exception as e:
            return {"valid": False, "error": str(e)}


class MutationAutonomySandboxSurface:
    """Read-only surface for safe mutation sandbox metadata."""

    def __init__(self, sandbox_path: Path):
        self.sandbox_path = Path(sandbox_path)

    def get_status(self) -> Dict[str, Any]:
        return {
            "sandbox_version": MUTATION_SANDBOX_VERSION,
            "sandbox_path": str(self.sandbox_path),
            "exists": self.sandbox_path.exists(),
        }

    def read_sandbox(self, max_chars: int = 4000) -> Dict[str, Any]:
        if not self.sandbox_path.exists():
            return {"exists": False, "content": ""}
        content = self.sandbox_path.read_text(encoding="utf-8")
        truncated = len(content) > max_chars
        return {
            "exists": True,
            "truncated": truncated,
            "content": content[:max_chars],
        }


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
        
        # API / legacy compatibility components
        self.guardian_core: Optional[Any] = self.config.get("guardian_core")
        self.mutation_engine: Optional[Any] = None
        self.trust_registry: Optional[Any] = None
        self.master_slave_controller: Optional[Any] = None
        self.revenue_sharing: Optional[Any] = None
        self.franchise_manager: Optional[Any] = None
        self.task_assignment_engine: Optional[Any] = None
        self.implementer_core: Optional[Any] = None
        self.mutation_review_manager: Optional[Any] = None
        self.mutation_router: Optional[Any] = None
        self.mutation_publisher: Optional[Any] = None
        self.mutation_sandbox: Optional[Any] = None
        self.ai_mutation_validator: Optional[Any] = None
        self.digital_safehouse: Optional[Any] = None
        self.dream_engine: Optional[Any] = None
        self.income_executor: Optional[Any] = None
        self.intelligent_task_distribution: Optional[Any] = None
        self.proposal_api: Optional[Any] = None
        self.slave_deployment: Optional[Any] = None
        self.chatgpt_export_import: Optional[Any] = None
        self.credit_spend_log: Optional[Any] = None
        self.error_handler: Optional[Any] = None
        self.feedback_loop_core: Optional[Any] = None
        self.file_writer: Optional[Any] = None
        self.mutation_autonomy_sandbox: Optional[Any] = None
        self.tool_executor: Optional[Any] = None
        self.eai_safety_framework: Optional[Any] = None
        self.eai_safety: Optional[Any] = None
        self.review_queue: Optional[Any] = None
        self.approval_store: Optional[Any] = None

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

        # API compatibility surfaces used by api_server.py and older integrations.
        self._initialize_api_compatibility_components()
        
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

        if self.mutation_engine is not None:
            self.mutation_engine.ask_ai = self.ask_ai

        self._initialize_auto_module_creator()
        
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

    def _compat_storage_root(self) -> Path:
        """Resolve a writable directory for compatibility component storage."""
        configured = self.config.get("api_compat_storage_dir") or self.config.get("storage_path") or "data"
        root = Path(configured)
        if root.suffix and not root.is_dir():
            root = root.parent
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _initialize_review_approval_stores(self, storage_root: Path) -> None:
        """Initialize shared review queue and approval store for API-facing gates."""
        guardian_queue = getattr(self.guardian_core, "review_queue", None)
        guardian_store = getattr(self.guardian_core, "approval_store", None)

        if self.review_queue is None:
            self.review_queue = guardian_queue or ReviewQueue(
                queue_file=Path(
                    self.config.get(
                        "eai_review_queue_path",
                        self.config.get("review_queue_path", str(storage_root / "review_queue.jsonl")),
                    )
                )
            )
        if self.approval_store is None:
            self.approval_store = guardian_store or ApprovalStore(
                store_file=Path(
                    self.config.get(
                        "eai_approval_store_path",
                        self.config.get("approval_store_path", str(storage_root / "approval_store.json")),
                    )
                )
            )

        if self.guardian_core is not None:
            for name, value in (
                ("review_queue", self.review_queue),
                ("approval_store", self.approval_store),
            ):
                if getattr(self.guardian_core, name, None) is None:
                    try:
                        setattr(self.guardian_core, name, value)
                    except Exception:
                        logger.debug("Unable to attach %s to guardian core", name, exc_info=True)

    def _initialize_eai_safety_framework(self, storage_root: Path) -> None:
        """Initialize the shared Evolvable-AI safety gate for runtime surfaces."""
        config_path = str(self.config.get("eai_safety_config_path", "config/eai_safety.json"))
        eai_config = load_eai_safety_config(config_path=config_path, overrides=self.config)
        if not eai_config.get("enabled", True):
            logger.info("[SKIP] EAI safety framework disabled by config")
            return
        if self.eai_safety_framework is not None:
            return

        audit_log = (
            getattr(self.guardian_core, "trust_audit", None)
            or getattr(self.guardian_core, "trust_audit_log", None)
            or getattr(self.guardian_core, "audit_log", None)
        )
        storage_path = str(
            self.config.get("eai_lineage_registry_path")
            or self.config.get("lineage_registry_path")
            or str(storage_root / "eai_lineage_registry.json")
        )
        audit_path = str(
            self.config.get("eai_audit_log_path")
            or self.config.get("eai_safety_audit_log_path")
            or self.config.get("audit_log_path")
            or str(storage_root / "eai_assessments.jsonl")
        )
        alert_state_path = str(
            self.config.get("eai_alert_state_path")
            or self.config.get("eai_safety_alert_state_path")
            or self.config.get("alert_state_path")
            or str(storage_root / "eai_alert_state.json")
        )
        deployment_policy = self.config.get("eai_autonomous_deployment_policy")
        self.eai_safety_framework = configure_eai_safety_framework(
            guardian=self.guardian_core or self,
            audit_log=audit_log,
            approval_store=self.approval_store,
            review_queue=self.review_queue,
            storage_path=storage_path,
            audit_path=audit_path,
            alert_state_path=alert_state_path,
            autonomous_deployment_policy=(
                str(deployment_policy) if deployment_policy is not None else None
            ),
            config_path=config_path,
            config=self.config,
        )
        self.eai_safety = self.eai_safety_framework
        logger.info("[OK] EAI safety framework initialized")

    def _initialize_api_compatibility_components(self) -> None:
        """Initialize the API-facing legacy components expected by APIServer."""
        if not self.config.get("initialize_api_compat_components", True):
            logger.info("[SKIP] API compatibility components disabled by config")
            return

        logger.info("Initializing API compatibility components...")
        storage_root = self._compat_storage_root()
        self._initialize_review_approval_stores(storage_root)

        try:
            from .trust_registry import TrustRegistry
            from .master_slave_controller import MasterSlaveController
            from .revenue_sharing import RevenueSharing
            from .franchise_manager import FranchiseManager
            from .mutation_engine import MutationEngine
        except ImportError:
            from trust_registry import TrustRegistry
            from master_slave_controller import MasterSlaveController
            from revenue_sharing import RevenueSharing
            from franchise_manager import FranchiseManager
            from mutation_engine import MutationEngine

        self._initialize_eai_safety_framework(storage_root)

        if self.trust_registry is None:
            self.trust_registry = TrustRegistry(
                storage_path=str(storage_root / "trust_registry.json")
            )
            logger.info("[OK] TrustRegistry compatibility surface initialized")

        if self.master_slave_controller is None:
            self.master_slave_controller = MasterSlaveController(
                master_id=self.config.get("master_id", "elysia-master"),
                master_name=self.config.get("master_name", "Elysia-Master"),
                trust_registry=self.trust_registry,
                eai_safety=self.eai_safety_framework,
                storage_path=str(storage_root / "master_slaves.json"),
                auth_token_path=str(storage_root / "slave_tokens.json"),
            )
            logger.info("[OK] MasterSlaveController compatibility surface initialized")

        if self.revenue_sharing is None:
            self.revenue_sharing = RevenueSharing(
                master_slave=self.master_slave_controller,
                trust_registry=self.trust_registry,
                storage_path=str(storage_root / "revenue_sharing.json"),
            )
            logger.info("[OK] RevenueSharing compatibility surface initialized")

        if self.franchise_manager is None:
            self.franchise_manager = FranchiseManager(
                master_slave=self.master_slave_controller,
                revenue_sharing=self.revenue_sharing,
                trust_registry=self.trust_registry,
                storage_path=str(storage_root / "franchise_manager.json"),
            )
            logger.info("[OK] FranchiseManager compatibility surface initialized")

        if self.revenue_sharing and getattr(self.revenue_sharing, "franchise_manager", None) is None:
            self.revenue_sharing.franchise_manager = self.franchise_manager

        if self.mutation_engine is None:
            live_mutation_engine = getattr(self.guardian_core, "mutation", None) if self.guardian_core else None
            self.mutation_engine = MutationEngine(
                runtime_loop=self.runtime_loop,
                ask_ai=self.ask_ai,
                storage_path=str(storage_root / "mutations.json"),
                live_mutation_engine=live_mutation_engine,
                repo_root=str(Path(__file__).resolve().parent.parent),
            )
            logger.info("[OK] MutationEngine compatibility surface initialized")

        if self.task_assignment_engine is None and self.config.get("enable_task_assignment_engine", True):
            self.task_assignment_engine = configure_task_assignment_engine(
                runtime_loop=self.runtime_loop,
                trust_registry_path=str(storage_root / "assignment_trust_registry.json"),
                min_trust_for_assignment=float(self.config.get("task_assignment_min_trust", 0.3)),
                trial_task_probability=float(self.config.get("task_assignment_trial_probability", 0.1)),
            )
            logger.info("[OK] TaskAssignmentEngine compatibility surface initialized")

        if self.implementer_core is None and self.config.get("enable_implementer_core", True):
            proposals_root = Path(
                self.config.get(
                    "implementer_proposals_root",
                    str(storage_root / "proposals"),
                )
            )
            proposals_root.mkdir(parents=True, exist_ok=True)
            repo_root = Path(
                self.config.get(
                    "implementer_repo_root",
                    str(Path(__file__).resolve().parent.parent),
                )
            )
            self.implementer_core = ImplementerCore(
                proposals_root=proposals_root,
                repo_root=repo_root,
                api_manager=None,
            )
            logger.info("[OK] ImplementerCore compatibility surface initialized")

        mutation_workflow_enabled = bool(
            self.config.get("enable_mutation_workflow_components", False)
        )
        enable_review_manager = bool(
            self.config.get("enable_mutation_review_manager", mutation_workflow_enabled)
        )
        enable_router = bool(
            self.config.get("enable_mutation_router", mutation_workflow_enabled)
        )
        enable_publisher = bool(
            self.config.get("enable_mutation_publisher", mutation_workflow_enabled)
        )

        if enable_review_manager and self.mutation_review_manager is None:
            self.mutation_review_manager = configure_mutation_review_manager(
                trust_registry=self.trust_registry,
                mutation_engine=self.mutation_engine,
                eai_safety=self.eai_safety_framework,
                guardian=self.guardian_core,
                storage_path=str(storage_root / "mutation_reviews.json"),
                auto_approve_trust_threshold=float(
                    self.config.get("mutation_review_auto_approve_threshold", 0.9)
                ),
            )
            logger.info("[OK] MutationReviewManager compatibility surface initialized")

        if enable_router and self.mutation_router is None:
            if self.mutation_review_manager is None:
                logger.warning(
                    "[SKIP] MutationRouter requested but MutationReviewManager is disabled/unavailable"
                )
            else:
                self.mutation_router = configure_mutation_router(
                    review_manager=self.mutation_review_manager,
                    mutation_engine=self.mutation_engine,
                    guardian=self.guardian_core,
                )
                logger.info("[OK] MutationRouter compatibility surface initialized")

        if enable_publisher and self.mutation_publisher is None:
            self.mutation_publisher = configure_mutation_publisher(
                mutation_engine=self.mutation_engine,
                guardian=self.guardian_core,
                codebase_path=str(
                    self.config.get("mutation_publisher_codebase_path", "project_guardian")
                ),
            )
            logger.info("[OK] MutationPublisher compatibility surface initialized")

        enable_sandbox = bool(
            self.config.get("enable_mutation_sandbox", mutation_workflow_enabled)
        )
        if enable_sandbox and self.mutation_sandbox is None:
            mutation_project_root = str(
                self.config.get(
                    "mutation_sandbox_project_root",
                    str(Path(__file__).resolve().parent.parent),
                )
            )
            sandbox_timeout = int(self.config.get("mutation_sandbox_timeout_seconds", 60))
            sandbox_cleanup = bool(self.config.get("mutation_sandbox_cleanup", True))
            self.mutation_sandbox = MutationSandbox(
                project_root=mutation_project_root,
                test_command=self.config.get("mutation_sandbox_test_command"),
                timeout=sandbox_timeout,
                cleanup=sandbox_cleanup,
                metacoder=getattr(self.guardian_core, "metacoder", None),
            )
            logger.info("[OK] MutationSandbox compatibility surface initialized")

        if self.tool_executor is None and self.config.get("enable_tool_executor", False):
            raw_allowed_tools = self.config.get("tool_executor_allowed_tools")
            if isinstance(raw_allowed_tools, (list, tuple, set)):
                allowed_tools = [str(tool).strip() for tool in raw_allowed_tools if str(tool).strip()]
            else:
                allowed_tools = [
                    "run_diagnostic",
                    "create_task",
                    "search_memory",
                    "ask_user",
                    "execute_task",
                    "consider_learning",
                    "consider_adversarial_learning",
                    "rebuild_vector",
                    "continue_monitoring",
                ]
            self.tool_executor = ToolExecutorSurface(
                guardian=self.guardian_core or self,
                allowed_tools=allowed_tools,
            )
            logger.info("[OK] ToolExecutor compatibility surface initialized")

        if self.digital_safehouse is None and self.config.get("enable_digital_safehouse", False):
            self.digital_safehouse = DigitalSafehouse(
                safehouse_dir=str(
                    self.config.get(
                        "digital_safehouse_dir",
                        str(storage_root / "safehouse"),
                    )
                ),
                key_file=str(
                    self.config.get(
                        "digital_safehouse_key_file",
                        str(storage_root / "safehouse.key"),
                    )
                ),
            )
            logger.info("[OK] DigitalSafehouse compatibility surface initialized")

        if self.dream_engine is None and self.config.get("enable_dream_engine", False):
            self.dream_engine = DreamEngine(
                runtime_loop=self.runtime_loop,
                introspection=getattr(self.guardian_core, "introspection", None),
                ask_ai=self.ask_ai,
                storage_path=str(
                    self.config.get(
                        "dream_engine_storage_path",
                        str(storage_root / "dream_engine.json"),
                    )
                ),
                idle_threshold_seconds=float(
                    self.config.get("dream_engine_idle_threshold_seconds", 5.0)
                ),
            )
            logger.info("[OK] DreamEngine compatibility surface initialized")

        if self.ai_mutation_validator is None and self.config.get("enable_ai_mutation_validator", False):
            self.ai_mutation_validator = AIMutationValidator(
                ask_ai=self.ask_ai or getattr(self.guardian_core, "ask_ai", None),
                min_confidence_threshold=float(
                    self.config.get("ai_mutation_validator_min_confidence", 0.7)
                ),
                fail_on_critical=bool(
                    self.config.get("ai_mutation_validator_fail_on_critical", True)
                ),
            )
            logger.info("[OK] AIMutationValidator compatibility surface initialized")
            if self.mutation_review_manager is not None:
                try:
                    configure_ai_validator_integration(
                        review_manager=self.mutation_review_manager,
                        mutation_engine=self.mutation_engine,
                        guardian=self.guardian_core,
                        ai_validator=self.ai_mutation_validator,
                    )
                except Exception as e:
                    logger.warning(
                        "[WARN] AIMutationValidator integration with review manager failed: %s",
                        e,
                    )
            else:
                logger.info(
                    "[SKIP] AIMutationValidator integration skipped (mutation_review_manager unavailable)"
                )

        if self.income_executor is None and self.config.get("enable_income_executor", False):
            self.income_executor = IncomeExecutor(
                gumroad_client=getattr(self.guardian_core, "gumroad_client", None),
                asset_manager=getattr(self.guardian_core, "asset_manager", None),
                master_slave=self.master_slave_controller,
                trust_registry=self.trust_registry,
                longterm_planner=getattr(self.guardian_core, "longterm_planner", None),
                storage_path=str(
                    self.config.get(
                        "income_executor_storage_path",
                        str(storage_root / "income_executor.json"),
                    )
                ),
            )
            logger.info("[OK] IncomeExecutor compatibility surface initialized")

        if self.intelligent_task_distribution is None and self.config.get(
            "enable_intelligent_task_distribution",
            False,
        ):
            self.intelligent_task_distribution = IntelligentTaskDistribution(
                network_discovery=getattr(self.guardian_core, "network_discovery", None),
                trust_registry=self.trust_registry,
                task_assignment=self.task_assignment_engine,
                storage_path=str(
                    self.config.get(
                        "intelligent_task_distribution_storage_path",
                        str(storage_root / "task_distribution.json"),
                    )
                ),
                use_ml=bool(self.config.get("intelligent_task_distribution_use_ml", False)),
            )
            logger.info("[OK] IntelligentTaskDistribution compatibility surface initialized")

        if self.proposal_api is None and self.config.get("enable_proposal_api", False):
            proposals_root = Path(
                self.config.get(
                    "proposal_api_proposals_root",
                    str(storage_root / "proposals"),
                )
            )
            build_flask = bool(self.config.get("proposal_api_build_flask_app", False))
            self.proposal_api = ProposalApiSurface(
                proposals_root=proposals_root,
                build_flask_app=build_flask,
                host=str(self.config.get("proposal_api_host", "127.0.0.1")),
                port=int(self.config.get("proposal_api_port", 5000)),
            )
            logger.info("[OK] ProposalAPI compatibility surface initialized")

        if self.slave_deployment is None and self.config.get("enable_slave_deployment", False):
            subprocess_runner = (
                getattr(self.guardian_core, "subprocess_runner", None)
                or getattr(getattr(self.guardian_core, "metacoder", None), "subprocess_runner", None)
                or _NoOpSubprocessRunner()
            )
            deployment = SlaveDeployment(
                master_controller=self.master_slave_controller,
                subprocess_runner=subprocess_runner,
                slave_code_package=str(
                    self.config.get(
                        "slave_deployment_package_path",
                        str(storage_root / "slave_elysia_package.zip"),
                    )
                ),
                deployment_config=dict(self.config.get("slave_deployment_config", {})),
                eai_safety=self.eai_safety_framework,
            )
            self.slave_deployment = SlaveDeploymentSurface(
                deployment=deployment,
                master_controller=self.master_slave_controller,
            )
            logger.info("[OK] SlaveDeployment compatibility surface initialized")

        if self.credit_spend_log is None and self.config.get("enable_credit_spend_log", False):
            self.credit_spend_log = CreditSpendLog(
                storage_path=str(
                    self.config.get(
                        "credit_spend_log_storage_path",
                        str(storage_root / "credit_spend_log.json"),
                    )
                ),
                audit_log=(
                    getattr(self.guardian_core, "trust_audit", None)
                    or getattr(self.guardian_core, "trust_audit_log", None)
                ),
                retention_days=int(self.config.get("credit_spend_log_retention_days", 365)),
            )
            logger.info("[OK] CreditSpendLog compatibility surface initialized")

        if self.error_handler is None and self.config.get("enable_error_handler", False):
            self.error_handler = ErrorHandler(
                recovery_vault=getattr(self.guardian_core, "recovery_vault", None),
                memory_snapshot=getattr(self.guardian_core, "memory_snapshot", None),
                timeline_memory=self.timeline_memory,
            )
            logger.info("[OK] ErrorHandler compatibility surface initialized")

        if self.chatgpt_export_import is None and self.config.get("enable_chatgpt_export_import", False):
            self.chatgpt_export_import = ChatGptExportImportSurface(
                default_output_dir=Path(
                    self.config.get(
                        "chatgpt_export_import_output_dir",
                        str(storage_root / "chatlogs"),
                    )
                )
            )
            logger.info("[OK] ChatGPT export import compatibility surface initialized")

        if self.feedback_loop_core is None and self.config.get("enable_feedback_loop_core", False):
            self.feedback_loop_core = FeedbackLoopCore(
                storage_path=str(
                    self.config.get(
                        "feedback_loop_core_storage_path",
                        str(storage_root / "feedback_loop.json"),
                    )
                ),
                ask_ai=self.ask_ai or getattr(self.guardian_core, "ask_ai", None),
            )
            logger.info("[OK] FeedbackLoopCore compatibility surface initialized")

        if self.file_writer is None and self.config.get("enable_file_writer", False):
            repo_root = Path(self.config.get("file_writer_repo_root", ".")).resolve()
            self.file_writer = FileWriterSurface(
                repo_root=repo_root,
                memory=self.memory or getattr(self.guardian_core, "memory", None),
                trust_matrix=getattr(self.guardian_core, "trust_matrix", None),
                review_queue=getattr(self.guardian_core, "review_queue", None),
                approval_store=getattr(self.guardian_core, "approval_store", None),
            )
            logger.info("[OK] FileWriter compatibility surface initialized")

        if self.mutation_autonomy_sandbox is None and self.config.get(
            "enable_mutation_autonomy_sandbox",
            False,
        ):
            sandbox_path = Path(
                self.config.get(
                    "mutation_autonomy_sandbox_path",
                    str((Path(__file__).resolve().parent / "mutation_autonomy_sandbox.py")),
                )
            )
            self.mutation_autonomy_sandbox = MutationAutonomySandboxSurface(
                sandbox_path=sandbox_path
            )
            logger.info("[OK] Mutation autonomy sandbox compatibility surface initialized")

    def _initialize_auto_module_creator(self) -> None:
        """Initialize AutoModuleCreator after AskAI is available."""
        if not AutoModuleCreator:
            logger.info("[SKIP] AutoModuleCreator not available")
            return
        if not self.ask_ai:
            logger.info("[SKIP] AutoModuleCreator not available (requires AskAI)")
            return
        if self.auto_module_creator is not None:
            self.auto_module_creator.ask_ai = self.ask_ai
            if self.mutation_engine is not None:
                self.auto_module_creator.mutation_engine = self.mutation_engine
            if self.eai_safety_framework is not None:
                self.auto_module_creator.eai_safety = self.eai_safety_framework
            return

        logger.info("  -> Creating AutoModuleCreator...")
        try:
            from .trust_eval_action import TrustEvalAction
        except ImportError:
            from trust_eval_action import TrustEvalAction

        trust_eval = TrustEvalAction() if hasattr(self, 'trust_eval') else None
        self.auto_module_creator = AutoModuleCreator(
            module_registry=self.module_registry,
            mutation_engine=self.mutation_engine,
            ask_ai=self.ask_ai,
            trust_eval=trust_eval,
            eai_safety=self.eai_safety_framework,
            project_root=".",
            modules_dir="project_guardian"
        )

        if self.module_registry:
            self.module_registry.set_auto_creator(self.auto_module_creator)

        logger.info("[OK] AutoModuleCreator initialized")
    
    async def _auto_register_modules(self):
        """Auto-register available modules."""
        if not self.module_registry:
            return
        
        logger.info("Auto-registering modules...")

        registered: List[str] = []

        def _register_module(
            module_name: str,
            instance: Any,
            *,
            priority: int = 5,
            dependencies: Optional[List[str]] = None,
        ) -> None:
            if instance is None:
                return
            try:
                self.module_registry.register_simple(
                    module_name,
                    instance,
                    priority=priority,
                    dependencies=dependencies,
                    auto_initialize=False,
                )
                registered.append(module_name)
            except Exception as e:
                logger.warning("Failed to auto-register module %s: %s", module_name, e)

        _register_module("priority_registry", self.priority_registry, priority=10)
        _register_module("timeline_memory", self.timeline_memory, priority=10)
        _register_module("task_queue", self.task_queue, priority=10)
        _register_module(
            "elysia_loop",
            self.elysia_loop,
            priority=10,
            dependencies=["timeline_memory", "task_queue"],
        )
        _register_module(
            "runtime_loop",
            self.runtime_loop,
            priority=10,
            dependencies=["elysia_loop", "task_queue"],
        )
        _register_module("bootstrap", self.bootstrap, priority=8)

        _register_module("memory", self.memory, priority=8)
        _register_module("persona", self.persona, priority=8)
        _register_module("ask_ai", self.ask_ai, priority=8)
        _register_module(
            "voice",
            self.voice,
            priority=7,
            dependencies=[dep for dep in ("persona", "ask_ai") if self.module_registry.get_module(dep)],
        )
        _register_module(
            "conversation_manager",
            self.conversation_manager,
            priority=8,
            dependencies=[
                dep for dep in ("memory", "persona", "voice", "ask_ai")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module("heartbeat", self.heartbeat, priority=7)
        _register_module(
            "auto_module_creator",
            self.auto_module_creator,
            priority=6,
            dependencies=[
                dep for dep in ("ask_ai", "mutation_engine")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module("ui_control_panel", self.ui_control_panel, priority=4)

        _register_module("trust_registry", self.trust_registry, priority=7)
        _register_module(
            "mutation_engine",
            self.mutation_engine,
            priority=7,
            dependencies=[
                dep for dep in ("runtime_loop", "ask_ai")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "master_slave_controller",
            self.master_slave_controller,
            priority=6,
            dependencies=[dep for dep in ("trust_registry",) if self.module_registry.get_module(dep)],
        )
        _register_module(
            "revenue_sharing",
            self.revenue_sharing,
            priority=6,
            dependencies=[
                dep for dep in ("master_slave_controller", "trust_registry")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "franchise_manager",
            self.franchise_manager,
            priority=6,
            dependencies=[
                dep for dep in ("master_slave_controller", "revenue_sharing", "trust_registry")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "task_assignment_engine",
            self.task_assignment_engine,
            priority=6,
            dependencies=[
                dep for dep in ("runtime_loop",)
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "implementer_core",
            self.implementer_core,
            priority=5,
            dependencies=[
                dep for dep in ("mutation_engine", "ask_ai")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "mutation_review_manager",
            self.mutation_review_manager,
            priority=6,
            dependencies=[
                dep for dep in ("mutation_engine", "trust_registry")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "mutation_router",
            self.mutation_router,
            priority=6,
            dependencies=[
                dep for dep in ("mutation_review_manager", "mutation_engine")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "mutation_publisher",
            self.mutation_publisher,
            priority=6,
            dependencies=[
                dep for dep in ("mutation_engine",)
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "mutation_sandbox",
            self.mutation_sandbox,
            priority=5,
            dependencies=[
                dep for dep in ("mutation_engine",)
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module("tool_executor", self.tool_executor, priority=5)
        _register_module(
            "digital_safehouse",
            self.digital_safehouse,
            priority=5,
        )
        _register_module(
            "dream_engine",
            self.dream_engine,
            priority=5,
            dependencies=[
                dep for dep in ("runtime_loop", "ask_ai")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "ai_mutation_validator",
            self.ai_mutation_validator,
            priority=5,
            dependencies=[
                dep for dep in ("ask_ai", "mutation_engine")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "income_executor",
            self.income_executor,
            priority=5,
            dependencies=[
                dep for dep in ("master_slave_controller", "trust_registry")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module(
            "intelligent_task_distribution",
            self.intelligent_task_distribution,
            priority=5,
            dependencies=[
                dep for dep in ("task_assignment_engine", "trust_registry")
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module("proposal_api", self.proposal_api, priority=4)
        _register_module(
            "slave_deployment",
            self.slave_deployment,
            priority=5,
            dependencies=[
                dep for dep in ("master_slave_controller",)
                if self.module_registry.get_module(dep)
            ],
        )
        _register_module("credit_spend_log", self.credit_spend_log, priority=4)
        _register_module("error_handler", self.error_handler, priority=4)
        _register_module("chatgpt_export_import", self.chatgpt_export_import, priority=4)
        _register_module("feedback_loop_core", self.feedback_loop_core, priority=4)
        _register_module("file_writer", self.file_writer, priority=4)
        _register_module(
            "mutation_autonomy_sandbox",
            self.mutation_autonomy_sandbox,
            priority=3,
        )

        logger.info("Auto-registered %s modules", len(registered))
    
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
                if hasattr(self.heartbeat, "stop_monitoring"):
                    stop_result = self.heartbeat.stop_monitoring()
                else:
                    stop_result = self.heartbeat.stop()
                if inspect.isawaitable(stop_result):
                    await stop_result
            
            # Stop runtime loop
            if self.runtime_loop:
                stop_result = self.runtime_loop.stop()
                if inspect.isawaitable(stop_result):
                    await stop_result
            
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
            try:
                self.ui_control_panel.start(source="SystemOrchestrator.start")
                logger.info(f"[OK] UI Control Panel started at http://{self.ui_control_panel.host}:{self.ui_control_panel.port}")
            except RuntimeError as e:
                logger.warning("[WARN] UI Control Panel start failed; continuing without ready dashboard: %s", e)
        
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
    
    def submit_task(
        self,
        task: Any,
        task_data: Optional[Dict[str, Any]] = None,
        *,
        priority: int = 5,
        module: str = "system",
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Submit a task to the system.

        Supports both callable tasks and the older ``(task_type, task_data)`` form used by
        some legacy integrations.
        
        Args:
            task: Callable task or task type identifier
            task_data: Task data dictionary for legacy submissions
            priority: Task priority (1-10)
            module: Module name for queue bookkeeping

        Returns:
            Task ID
        """
        if not self.task_queue:
            raise RuntimeError("Task queue not initialized")

        submit_metadata = dict(metadata or {})
        submit_kwargs = dict(kwargs or {})

        if callable(task):
            func: Callable[..., Any] = task
            log_type = getattr(task, "__name__", "callable_task")
        else:
            task_type = str(task)
            payload = dict(task_data or {})
            submit_metadata.setdefault("task_type", task_type)
            submit_metadata.setdefault("task_data", payload)

            def func() -> Dict[str, Any]:
                return {"task_type": task_type, "task_data": payload}

            log_type = task_type

        task_id = self.task_queue.submit_task(
            func,
            args=args,
            kwargs=submit_kwargs,
            priority=priority,
            module=module,
            timeout=timeout,
            dependencies=dependencies,
            metadata=submit_metadata,
        )
        self.operational_stats["total_tasks_processed"] += 1
        logger.info(f"Task submitted: {task_id} (type: {log_type}, priority: {priority})")
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
                "heartbeat": self.heartbeat is not None,
                "guardian_core": self.guardian_core is not None,
                "mutation_engine": self.mutation_engine is not None,
                "trust_registry": self.trust_registry is not None,
                "master_slave_controller": self.master_slave_controller is not None,
                "revenue_sharing": self.revenue_sharing is not None,
                "franchise_manager": self.franchise_manager is not None,
                "task_assignment_engine": self.task_assignment_engine is not None,
                "implementer_core": self.implementer_core is not None,
                "mutation_review_manager": self.mutation_review_manager is not None,
                "mutation_router": self.mutation_router is not None,
                "mutation_publisher": self.mutation_publisher is not None,
                "mutation_sandbox": self.mutation_sandbox is not None,
                "tool_executor": self.tool_executor is not None,
                "digital_safehouse": self.digital_safehouse is not None,
                "dream_engine": self.dream_engine is not None,
                "ai_mutation_validator": self.ai_mutation_validator is not None,
                "income_executor": self.income_executor is not None,
                "intelligent_task_distribution": self.intelligent_task_distribution is not None,
                "proposal_api": self.proposal_api is not None,
                "slave_deployment": self.slave_deployment is not None,
                "credit_spend_log": self.credit_spend_log is not None,
                "error_handler": self.error_handler is not None,
                "chatgpt_export_import": self.chatgpt_export_import is not None,
                "feedback_loop_core": self.feedback_loop_core is not None,
                "file_writer": self.file_writer is not None,
                "mutation_autonomy_sandbox": self.mutation_autonomy_sandbox is not None,
                "auto_module_creator": self.auto_module_creator is not None,
                "eai_safety_framework": self.eai_safety_framework is not None,
            },
            "statistics": self.operational_stats.copy()
        }
        if self.eai_safety_framework is not None:
            try:
                status["eai_safety"] = self.eai_safety_framework.get_status()
            except Exception as e:
                status["eai_safety"] = {"error": str(e)}
        
        # Add module registry status
        if self.module_registry:
            status["modules"] = self.module_registry.get_registry_status()
        
        # Add task queue status
        if self.task_queue:
            task_queue_stats = (
                self.task_queue.get_statistics()
                if hasattr(self.task_queue, "get_statistics")
                else {}
            )
            status_counts = task_queue_stats.get("status_counts", {}) if isinstance(task_queue_stats, dict) else {}
            status["task_queue"] = {
                "pending": self.task_queue.get_queue_size(),
                "processing": int(status_counts.get("running", 0) or 0),
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
            "priority_registry": self.priority_registry,
            "guardian_core": self.guardian_core,
            "mutation_engine": self.mutation_engine,
            "trust_registry": self.trust_registry,
            "master_slave_controller": self.master_slave_controller,
            "revenue_sharing": self.revenue_sharing,
            "franchise_manager": self.franchise_manager,
            "task_assignment_engine": self.task_assignment_engine,
            "implementer_core": self.implementer_core,
            "mutation_review_manager": self.mutation_review_manager,
            "mutation_router": self.mutation_router,
            "mutation_publisher": self.mutation_publisher,
            "mutation_sandbox": self.mutation_sandbox,
            "tool_executor": self.tool_executor,
            "digital_safehouse": self.digital_safehouse,
            "dream_engine": self.dream_engine,
            "ai_mutation_validator": self.ai_mutation_validator,
            "income_executor": self.income_executor,
            "intelligent_task_distribution": self.intelligent_task_distribution,
            "proposal_api": self.proposal_api,
            "slave_deployment": self.slave_deployment,
            "credit_spend_log": self.credit_spend_log,
            "error_handler": self.error_handler,
            "chatgpt_export_import": self.chatgpt_export_import,
            "feedback_loop_core": self.feedback_loop_core,
            "file_writer": self.file_writer,
            "mutation_autonomy_sandbox": self.mutation_autonomy_sandbox,
            "auto_module_creator": self.auto_module_creator,
            "eai_safety_framework": self.eai_safety_framework,
            "eai_safety": self.eai_safety_framework,
            "review_queue": self.review_queue,
            "approval_store": self.approval_store,
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

