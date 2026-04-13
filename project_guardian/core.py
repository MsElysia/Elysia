# project_guardian/core.py
# Main Guardian Core System
# Enhanced with ElysiaLoop-Core integration

import datetime
import json
import os
import time
import asyncio
import logging
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from .memory import MemoryCore
from .mutation import MutationEngine
from .safety import DevilsAdvocate
from .trust import TrustMatrix
from .rollback import RollbackEngine
from .tasks import TaskEngine
from .consensus import ConsensusEngine
from .introspection import SelfReflector
from .monitoring import SystemMonitor
from .creativity import ContextBuilder, DreamEngine, MemorySearch
from .external import WebReader, VoiceThread, AIInteraction, TrustDeniedError, TrustReviewRequiredError
from .subprocess_runner import SubprocessRunner
from .analysis_engine import AnalysisEngine
from .missions import MissionDirector
from .elysia_loop_core import ElysiaLoopCore, TimelineMemory, ModuleRegistry
from .adapters import (
    MemoryAdapter, MutationAdapter, SafetyAdapter,
    TrustAdapter, TaskAdapter, ConsensusAdapter
)
from .trust_eval_action import TrustEvalAction, TrustEvalActionAdapter
from .trust_eval_content import TrustEvalContent, TrustEvalContentAdapter
from .feedback_loop import FeedbackLoopCore, FeedbackLoopAdapter
from .prompt_evolver import PromptEvolver, AutoPromptEvolutionScheduler
from .trust_policy_manager import TrustPolicyManager
from .trust_audit_log import TrustAuditLog
from .trust_escalation_handler import TrustEscalationHandler
from .memory_snapshot import MemorySnapshot
from .ui_control_panel import UIControlPanel
from .config_validator import ConfigValidator
from .security_audit import SecurityAuditor, run_security_audit
from .resource_limits import ResourceMonitor, ResourceType
from .startup_verification import StartupVerifier, verify_guardian_startup
from .runtime_health import RuntimeHealthMonitor, create_guardian_health_checks
from .adversarial_self_learning import (
    run_adversarial_cycle,
    get_adversarial_status,
    get_recent_findings,
    get_finding_priority_boost,
    get_execution_policy_effect,
    apply_execution_policy_to_candidates,
    trigger_adversarial_on_event,
    record_task_completed,
    TRIGGER_PERIODIC,
    TRIGGER_VECTOR_DEGRADED,
    TRIGGER_STARTUP_WARNINGS,
    TRIGGER_BAD_LEARNING_SESSION,
)

logger = logging.getLogger(__name__)

class GuardianCore:
    """
    Main Project Guardian core system.
    Integrates all components for autonomous AI safety and management.
    """
    
    # Class-level flag to track if any instance has been initialized
    _any_instance_initialized = False
    _initialization_lock = threading.Lock()
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, control_path: Optional[Path] = None, tasks_dir: Optional[Path] = None, mutations_dir: Optional[Path] = None, allow_multiple: bool = False):
        """
        Initialize Project Guardian core system.
        
        Args:
            config: Configuration dictionary
            control_path: Optional path to CONTROL.md (default: project_root/CONTROL.md)
            tasks_dir: Optional path to TASKS directory (default: project_root/TASKS)
            mutations_dir: Optional path to MUTATIONS directory (default: project_root/MUTATIONS)
            allow_multiple: If True, allow multiple instances (for testing only)
        
        Raises:
            RuntimeError: If another GuardianCore instance already exists and allow_multiple=False
        """
        # Prevent double initialization unless explicitly allowed
        if not allow_multiple:
            with GuardianCore._initialization_lock:
                if GuardianCore._any_instance_initialized:
                    raise RuntimeError(
                        "GuardianCore instance already exists. "
                        "Use project_guardian.guardian_singleton.get_guardian_core() "
                        "to get the existing instance, or set allow_multiple=True for testing."
                    )
                GuardianCore._any_instance_initialized = True
        
        self.config = config or {}
        self.start_time = datetime.datetime.now()
        self._initialized = False
        self._running = False
        
        # Set paths for CONTROL.md, TASKS directory, and MUTATIONS directory
        project_root = Path(__file__).parent.parent
        self.control_path = Path(control_path) if control_path else project_root / "CONTROL.md"
        self.tasks_dir = Path(tasks_dir) if tasks_dir else project_root / "TASKS"
        self.mutations_dir = Path(mutations_dir) if mutations_dir else project_root / "MUTATIONS"
        
        # Load API keys from project "API keys" folder so validation and LLM work (backend or interface)
        self._load_api_keys_from_folder(project_root)
        
        # Validate configuration early
        self._validate_configuration()

        # Shared timeline before memory (MemoryCore / ElysiaLoop use same instance)
        self.timeline = TimelineMemory()
        self._defer_heavy_startup = self.config.get("defer_heavy_startup", True)
        self.deferred_init_started = False
        self.deferred_init_running = False
        self.deferred_init_complete = False
        self.deferred_init_failed = False
        self.deferred_init_error: Optional[str] = None
        self._deferred_init_lock = threading.Lock()
        logger.info("[Startup] Phase A (minimal boot) started")
        
        # Check for external storage configuration file
        # Testability: _test_skip_external_storage=True skips external storage (use provided paths)
        config_dir = Path(__file__).parent.parent / "config"
        external_config_file = config_dir / "external_storage.json"
        
        if not config.get("_test_skip_external_storage", False) and external_config_file.exists():
            try:
                import json
                with open(external_config_file, 'r', encoding='utf-8') as f:
                    external_config = json.load(f)
                
                if external_config.get("use_external_storage", False):
                    logger.info(f"[External Storage] Config found: {external_config.get('external_drive')}")
                    
                    # Validate and resolve paths (with fallback if needed)
                    from .external_storage import validate_and_resolve_storage_paths
                    validated_config = validate_and_resolve_storage_paths(external_config)
                    
                    # Merge validated external storage paths into config
                    config = {**config, **validated_config}
                    
                    if validated_config.get("fallback_used", False):
                        logger.debug(
                            f"[External Storage] Fallback used: original path '{validated_config.get('original_drive')}' "
                            f"not available (already warned by external_storage)"
                        )
                    else:
                        logger.info("[External Storage] Using external storage for memory")
            except Exception as e:
                logger.warning(f"Error loading external storage config: {e}, using local storage")
        
        # Also check config parameter for external storage
        use_external = config.get("use_external_storage", False)
        if not config.get("_test_skip_external_storage", False) and use_external and not external_config_file.exists():
            try:
                from .external_storage import get_external_storage_config
                external_config = get_external_storage_config()
                if external_config:
                    logger.info(f"[INFO] Auto-detected external storage: {external_config.get('external_drive')}")
                    # Merge external storage paths into config
                    config = {**config, **external_config}
                    logger.info("[OK] Using external storage for memory")
                else:
                    logger.warning("External storage requested but no drive found, using local storage")
            except Exception as e:
                logger.warning(f"Error setting up external storage: {e}, using local storage")
        
        # Merge any external storage updates into self.config
        if config:
            self.config = {**self.config, **config}
        # Resolve memory path from canonical/legacy keys (single source of truth)
        from .memory_paths import resolve_memory_paths
        resolved_paths = resolve_memory_paths(self.config, project_root)
        self.config = {**self.config, **resolved_paths}
        
        # Initialize core components
        # Check if vector memory should be enabled
        enable_vector = self.config.get("enable_vector_memory", True)
        _defer = self._defer_heavy_startup
        memory_filepath = self.config["memory_filepath"]
        vector_config = self.config.get("vector_memory_config", {})
        if enable_vector:
            try:
                from .memory_vector import EnhancedMemoryCore
                self.memory = EnhancedMemoryCore(
                    json_filepath=memory_filepath,
                    enable_vector=True,
                    vector_config=vector_config,
                    timeline_memory=self.timeline,
                    lazy_json=_defer,
                    lazy_vector=_defer,
                )
                logger.info(
                    "Memory initialized with vector search support"
                    + (" (lazy JSON + vector for boot)" if _defer else "")
                )
            except Exception as e:
                logger.warning(f"Failed to initialize vector memory, using basic memory: {e}")
                self.memory = MemoryCore(
                    filepath=memory_filepath,
                    timeline_memory=self.timeline,
                    lazy_load=_defer,
                )
        else:
            self.memory = MemoryCore(
                filepath=memory_filepath,
                timeline_memory=self.timeline,
                lazy_load=_defer,
            )

        # Confirm shared TimelineMemory ownership between GuardianCore and MemoryCore/EnhancedMemoryCore
        shared_timeline = False
        if hasattr(self.memory, "json_memory"):
            json_mem = getattr(self.memory, "json_memory", None)
            if json_mem is not None and getattr(json_mem, "timeline", None) is self.timeline:
                shared_timeline = True
        else:
            if getattr(self.memory, "timeline", None) is self.timeline:
                shared_timeline = True
        if shared_timeline:
            logger.info("GuardianCore: Memory attached to GuardianCore TimelineMemory (shared instance)")

        try:
            from .startup_runtime_guard import bind_guardian_for_runtime_guard

            bind_guardian_for_runtime_guard(self)
        except Exception:
            pass
        
        # Initialize TrustMatrix FIRST (needed by other components)
        self.trust = TrustMatrix(self.memory)
        
        # Initialize ReviewQueue and ApprovalStore for mutation engine
        from .review_queue import ReviewQueue
        from .approval_store import ApprovalStore
        project_root = Path(__file__).parent.parent
        review_queue = ReviewQueue(queue_file=project_root / "REPORTS" / "review_queue.jsonl", memory=self.memory)
        approval_store = ApprovalStore(store_file=project_root / "REPORTS" / "approval_store.json")
        
        # Initialize MutationEngine with TrustMatrix, ReviewQueue, ApprovalStore
        self.mutation = MutationEngine(
            self.memory, 
            trust_matrix=self.trust,
            review_queue=review_queue,
            approval_store=approval_store
        )
        self.safety = DevilsAdvocate(self.memory)
        self.rollback = RollbackEngine(self.memory)
        self.tasks = TaskEngine(self.memory)

        def _on_adversarial_task_complete(task_id: int, task: Dict) -> None:
            if task.get("category") == "adversarial":
                try:
                    from .adversarial_self_learning import _ensure_registry
                    reg = _ensure_registry(self)
                    for fid, f in reg.get("findings_by_id", {}).items():
                        if task_id in f.get("created_task_ids", []):
                            record_task_completed(self, fid)
                            self.memory.remember(
                                f"[Adversarial] Finding {fid} -> task_completed_unverified (task {task_id} done; awaiting verification)",
                                category="adversarial_finding",
                                priority=0.6,
                            )
                            break
                except Exception as e:
                    logger.debug("Adversarial task completion: %s", e)

        self.tasks._on_task_complete = _on_adversarial_task_complete
        self.consensus = ConsensusEngine(self.memory)
        
        # Initialize advanced components
        self.reflector = SelfReflector(self.memory, self)
        self.monitor = SystemMonitor(self.memory, self)
        
        # Initialize production readiness components
        resource_config = config.get("resource_limits", {})
        self.resource_monitor = ResourceMonitor(
            memory_limit_percent=resource_config.get("memory_limit", 0.8),
            cpu_limit_percent=resource_config.get("cpu_limit", 0.9),
            disk_limit_percent=resource_config.get("disk_limit", 0.9),
            disk_path=resource_config.get("disk_path", config.get("storage_path", "."))
        )
        self._resource_monitor_startup_deferred = False
        try:
            self._resource_monitoring_interval = int(config.get("resource_monitoring_interval", 30))
        except (TypeError, ValueError):
            self._resource_monitoring_interval = 30
        
        # Initialize security auditor
        self.security_auditor = SecurityAuditor(
            config_path=config.get("config_path")
        )
        
        # Start resource monitoring if enabled (defer thread until Phase B when defer_heavy_startup)
        if config.get("enable_resource_monitoring", True):
            # When memory limit exceeded, trigger aggressive cleanup (throttled to avoid thrashing)
            self._last_resource_triggered_cleanup: Optional[float] = None
            _RESOURCE_CLEANUP_COOLDOWN = 180  # seconds; don't run again within 3 minutes
            from .resource_limits import ResourceType
            def _on_memory_limit_exceeded(violation):
                try:
                    from project_guardian.monitoring import CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE, _load_memory_pressure_config
                    now = datetime.datetime.now().timestamp()
                    last = getattr(self, "_last_resource_triggered_cleanup", None) or 0
                    if now - last < _RESOURCE_CLEANUP_COOLDOWN:
                        return
                    consolidation_threshold = self.config.get("memory_cleanup_threshold", 3500)
                    pressure_cfg = _load_memory_pressure_config()
                    # Under high memory pressure, trim to lower watermark (1600) to break pressure loop
                    target = pressure_cfg.get("pressure_trim_target", max(1000, int(consolidation_threshold * 0.5)))
                    target = max(1000, int(target))
                    usage = violation.get("usage_percent")
                    if hasattr(self, "monitor") and self.monitor and hasattr(self.monitor, "_perform_cleanup"):
                        self.monitor._perform_cleanup(
                            target,
                            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
                            system_memory_percent=usage,
                            consolidation_threshold=consolidation_threshold,
                        )
                        self._last_resource_triggered_cleanup = now
                except Exception as e:
                    logger.debug(f"Resource limit cleanup callback: {e}")
            self.resource_monitor.register_callback(ResourceType.MEMORY, _on_memory_limit_exceeded)
            if self._defer_heavy_startup:
                self._resource_monitor_startup_deferred = True
                logger.info(
                    "[Startup] Resource monitor thread deferred until Phase B (avoid overlap with JSON/FAISS/embed load)"
                )
            else:
                self.resource_monitor.start_monitoring(interval=self._resource_monitoring_interval)
        
        # Initialize creativity and context components
        self.context = ContextBuilder(self.memory)
        self.dreams = DreamEngine(self.memory, self.mutation, prompt_evolver=getattr(self, "prompt_evolver", None))
        self.memory_search = MemorySearch(self.memory)
        
        # Initialize external interaction components
        # WebReader needs ReviewQueue and ApprovalStore for review/replay support
        self.web_reader = WebReader(
            self.memory, 
            trust_matrix=self.trust,
            review_queue=review_queue,
            approval_store=approval_store
        )
        # SubprocessRunner is the single subprocess surface (including acceptance execution)
        self.subprocess_runner = SubprocessRunner(
            memory=self.memory,
            trust_matrix=self.trust,
            review_queue=review_queue,
            approval_store=approval_store
        )
        # AnalysisEngine for read-only analysis tasks
        # Use mutations_dir.parent as repo_root to respect test/project root settings
        analysis_repo_root = self.mutations_dir.parent if self.mutations_dir else project_root
        self.analysis_engine = AnalysisEngine(
            memory=self.memory,
            web_reader=self.web_reader,
            repo_root=analysis_repo_root
        )
        self.voice = VoiceThread(self.memory)
        self.ai_interaction = AIInteraction(self.memory)
        
        # Initialize mission management
        self.missions = MissionDirector(self.memory)
        self._modules = None  # Set by wire_modules() from Elysia after modules init
        self._last_introspection_result = None  # Updated by decide_from_introspection
        self._last_autonomy_result = None  # Updated by run_autonomous_cycle
        self._module_last_invoked: Dict[str, str] = {}  # module_name -> ISO timestamp
        # Mistral override memory, outcome reinforcement, adversarial gating (decider loop only)
        self._mistral_decision_cycle = 0
        self._mistral_penalty_entries: List[Dict[str, Any]] = []
        self._mistral_recent_overrides: List[Dict[str, Any]] = []
        self._mistral_outcome_boost: Dict[str, Dict[str, Any]] = {}
        self._mistral_consecutive_override_count = 0
        self._last_get_next_had_override = False
        self._adversarial_low_yield_streak = 0
        self._adversarial_last_fingerprint: Optional[str] = None
        self._adversarial_priority_penalty = 0.0
        self._get_next_action_lock = threading.Lock()  # UI + heartbeat may call concurrently
        from .capability_registry import CapabilityRegistry
        self._orchestration_registry = CapabilityRegistry()
        self._self_task_low_confidence_streak = 0
        self._nonadv_action_streak: Dict[str, int] = {}
        self._nonadv_penalty_until: Dict[str, float] = {}
        self._income_modules_prev_sig_for_nonadv: Optional[str] = None
        self._autonomy_last_advanced: bool = True
        self._planner_startup_snapshot: Dict[str, Any] = {}
        self._planner_startup_probe_pending: bool = False
        self._last_autonomy_next_result: Optional[Dict[str, Any]] = None

        # Initialize ElysiaLoop-Core system (timeline already created for MemoryCore)
        self.module_registry = ModuleRegistry()
        self.elysia_loop = ElysiaLoopCore(
            timeline_memory=self.timeline,
            module_registry=self.module_registry
        )
        
        # Initialize TrustEval system
        self.trust_policy = TrustPolicyManager()
        self.trust_audit = TrustAuditLog()
        self.trust_escalation = TrustEscalationHandler(self.trust_audit)
        self.trust_eval_action = TrustEvalAction(
            policy_manager=self.trust_policy,
            audit_logger=self.trust_audit,
            escalation_handler=self.trust_escalation
        )
        self.trust_eval_content = TrustEvalContent(
            policy_manager=self.trust_policy,
            audit_logger=self.trust_audit,
            escalation_handler=self.trust_escalation
        )
        
        # Initialize PromptEvolver first (evolve prompts using AI API)
        self._ask_ai_for_evolution = None
        try:
            if os.getenv("OPENAI_API_KEY"):
                from .ask_ai import AskAI
                self._ask_ai_for_evolution = AskAI()
        except Exception as e:
            logger.debug(f"AskAI not available for PromptEvolver: {e}")
        evolver_path = config.get("prompt_evolver_path", "data/prompt_evolver.json")
        self.prompt_evolver = PromptEvolver(
            storage_path=evolver_path,
            ask_ai=self._ask_ai_for_evolution,
        )
        self.prompt_evolution_scheduler = AutoPromptEvolutionScheduler(
            prompt_evolver=self.prompt_evolver,
        )
        if self.dreams:
            self.dreams.prompt_evolver = self.prompt_evolver
        
        # Initialize FeedbackLoop-Core (with prompt evolver for logging)
        self.feedback_loop = FeedbackLoopCore(prompt_evolver=self.prompt_evolver)
        
        # Initialize Memory Snapshot System
        snapshot_config = config.get("snapshot_config", {})
        self.memory_snapshot = MemorySnapshot(
            snapshot_dir=snapshot_config.get("snapshot_dir", "memory/snapshots"),
            backup_shards=snapshot_config.get("backup_shards", 3),
            retention_days=snapshot_config.get("retention_days", 30)
        )
        
        # Initialize UI Control Panel (optional) — use canonical wrapper for start
        self.ui_panel = None
        ui_config = config.get("ui_config", {})
        if ui_config.get("enabled", False):
            ui_host = ui_config.get("host", "127.0.0.1")
            ui_port = ui_config.get("port", 5000)
            self.ui_panel = UIControlPanel(
                orchestrator=self,
                host=ui_host,
                port=ui_port
            )
            if ui_config.get("auto_start", False):
                self.start_ui_panel(host=ui_host, port=ui_port, debug=ui_config.get("debug", False))
        
        # Register module adapters
        self._register_module_adapters()
        
        # Register core components as agents
        self._register_core_agents()
        
        # Initialize system
        self._initialize_system()
        
        # Note: enable_embeddings() is called by run_elysia_unified.py after unified startup completes
        # Do NOT call here during __init__ to ensure embeddings are truly deferred until startup completes
        
    def _register_module_adapters(self) -> None:
        """Register all modules with the ElysiaLoop-Core registry."""
        self.module_registry.register("memory", MemoryAdapter(self.memory))
        self.module_registry.register("mutation", MutationAdapter(self.mutation))
        self.module_registry.register("safety", SafetyAdapter(self.safety))
        self.module_registry.register("trust", TrustAdapter(self.trust))
        self.module_registry.register("tasks", TaskAdapter(self.tasks))
        self.module_registry.register("consensus", ConsensusAdapter(self.consensus))
        self.module_registry.register("trust_eval_action", TrustEvalActionAdapter(self.trust_eval_action))
        self.module_registry.register("trust_eval_content", TrustEvalContentAdapter(self.trust_eval_content))
        self.module_registry.register("feedback_loop", FeedbackLoopAdapter(self.feedback_loop))
        
    def _register_core_agents(self) -> None:
        """Register core components as consensus agents."""
        agents = [
            ("memory_core", "memory", 1.0, ["persistence", "recall"]),
            ("mutation_engine", "mutation", 0.8, ["code_evolution", "safety"]),
            ("safety_engine", "safety", 1.0, ["validation", "criticism"]),
            ("trust_matrix", "trust", 0.9, ["trust_management", "validation"]),
            ("rollback_engine", "recovery", 0.7, ["backup", "restoration"]),
            ("task_engine", "task", 0.6, ["task_management", "tracking"]),
            ("consensus_engine", "consensus", 1.0, ["decision_making", "voting"]),
            ("dream_engine", "creativity", 0.6, ["creative_thinking", "inspiration"]),
            ("web_reader", "external", 0.5, ["information_gathering", "web_access"]),
            ("mission_director", "mission", 0.7, ["goal_management", "progress_tracking"])
        ]
        
        for name, agent_type, weight, capabilities in agents:
            self.consensus.register_agent(name, agent_type, weight, capabilities)

    def _want_mistral_planner_startup_probe(self) -> bool:
        """True when config enables Mistral decider / autonomy engine (Ollama planner may run)."""
        try:
            root = Path(__file__).parent.parent
            auto_path = root / "config" / "autonomy.json"
            dec_path = root / "config" / "mistral_decider.json"
            if auto_path.exists():
                with open(auto_path, "r", encoding="utf-8") as f:
                    if bool(json.load(f).get("use_mistral_decision_engine", False)):
                        return True
            if dec_path.exists():
                with open(dec_path, "r", encoding="utf-8") as f:
                    return bool(json.load(f).get("mistral_primary_decider_enabled", False))
        except Exception:
            pass
        return False

    def _initialize_system(self) -> None:
        """Initialize the Guardian system."""
        self.memory.remember(
            "[Guardian Core] System initialized",
            category="system",
            priority=0.9
        )
        
        # Create initial system tasks
        self.tasks.create_task(
            "system_monitoring",
            "Monitor system health and performance",
            priority=0.8,
            category="system"
        )
        
        self.tasks.create_task(
            "safety_validation",
            "Validate system safety and trust levels",
            priority=0.9,
            category="safety"
        )
        
        # Set initial trust levels
        self.trust.update_trust("memory_core", 0.8, "Core component")
        self.trust.update_trust("safety_engine", 0.9, "Critical safety component")
        self.trust.update_trust("mutation_engine", 0.7, "Requires careful monitoring")
        
        # Start monitoring (with singleton guard to prevent duplicate starts)
        from .guardian_singleton import ensure_monitoring_started
        ensure_monitoring_started(self)

        # Planner readiness: sync Ollama tags + canonical model + health (when Mistral decider may run)
        try:
            want_probe = self._want_mistral_planner_startup_probe()
            self._planner_startup_probe_pending = False
            if want_probe:
                from .planner_readiness import compute_readiness_label, run_startup_planner_probe
                from .startup_runtime_guard import startup_memory_thin_mode_active

                defer_heavy = bool(getattr(self, "_defer_heavy_startup", False))
                probe_defer = False
                try:
                    probe_defer = defer_heavy and bool(startup_memory_thin_mode_active(self))
                except Exception:
                    probe_defer = False
                if probe_defer:
                    self._planner_startup_probe_pending = True
                    self._planner_startup_snapshot = {}
                    logger.info(
                        "[Startup] Planner startup probe deferred (memory-thin + defer_heavy_startup)"
                    )
                else:
                    self._planner_startup_snapshot = run_startup_planner_probe(log_tags_on_fail=True)
                    _lbl = compute_readiness_label()
                    logger.info(
                        "[Autonomy] planner_startup readiness=%s exact_tag_match=%s health_ok=%s",
                        _lbl,
                        self._planner_startup_snapshot.get("exact_tag_match"),
                        self._planner_startup_snapshot.get("startup_health_ok"),
                    )
        except Exception as e:
            logger.debug("Planner startup probe skip: %s", e)

        # Mark system as initialized
        self._initialized = True
        self._running = True
        
        # Start ElysiaLoop-Core event loop (delegated to singleton guard)
        # The ensure_monitoring_started() call above will handle elysia_loop.start()
        # if needed, so we don't start it here to avoid double initialization
        
        # Verify startup and component initialization
        self._verify_startup()
        
        # Initialize runtime health monitoring
        self._init_runtime_health_monitoring()
        
        if not getattr(self, "_defer_heavy_startup", False):
            self._check_and_cleanup_memory()
            self.deferred_init_started = True
            self.deferred_init_running = False
            self.deferred_init_complete = True
            self.deferred_init_failed = False
            self.deferred_init_error = None
            logger.info("[Startup] Phase A end — full memory loaded at boot (defer_heavy_startup=False)")
        else:
            logger.info(
                "[Startup] Phase A end — dashboard path ready; "
                "JSON/FAISS load and startup cleanup deferred"
            )
        
    def _ensure_resource_monitor_started_after_deferred(self) -> None:
        """Start psutil resource thread after Phase B if it was deferred (idempotent)."""
        if not getattr(self, "_resource_monitor_startup_deferred", False):
            return
        rm = getattr(self, "resource_monitor", None)
        if rm is None:
            self._resource_monitor_startup_deferred = False
            return
        try:
            if not rm.monitoring_active:
                rm.start_monitoring(interval=getattr(self, "_resource_monitoring_interval", 30))
                logger.info("[Startup] Resource monitor thread started (post Phase B)")
        except Exception as e:
            logger.warning("[Startup] Deferred resource monitor start failed: %s", e)
        finally:
            self._resource_monitor_startup_deferred = False

    def start_deferred_initialization(self) -> None:
        """
        Phase B: load full JSON history, FAISS/metadata, embeddings, startup cleanup.
        Idempotent; safe from a background thread. Call after dashboard is ready.
        Always resolves to a terminal state: complete or failed.
        """
        import time as _time
        if not getattr(self, "_defer_heavy_startup", False):
            with self._deferred_init_lock:
                self.deferred_init_started = True
                self.deferred_init_running = False
                self.deferred_init_complete = True
                self.deferred_init_failed = False
                self.deferred_init_error = None
            return
        with self._deferred_init_lock:
            if self.deferred_init_running:
                logger.debug("[Startup] Deferred initialization already running; skipping")
                return
            if self.deferred_init_complete:
                logger.debug("[Startup] Deferred initialization already complete; skipping")
                return
            if self.deferred_init_failed:
                logger.debug("[Startup] Deferred initialization already failed; skipping")
                return
            logger.info("[Startup] Beginning deferred initialization...")
            self.deferred_init_started = True
            self.deferred_init_running = True
            self.deferred_init_complete = False
            self.deferred_init_failed = False
            self.deferred_init_error = None
            t0 = _time.time()
        try:
            mem = self.memory
            if hasattr(mem, "load_if_needed"):
                mem.load_if_needed()
            if hasattr(mem, "json_memory") and hasattr(mem.json_memory, "load_if_needed"):
                mem.json_memory.load_if_needed()
            if getattr(mem, "vector_memory", None) and hasattr(mem.vector_memory, "load_if_needed"):
                mem.vector_memory.load_if_needed()
            self._check_and_cleanup_memory()
            root = mem.json_memory if hasattr(mem, "json_memory") else mem
            if hasattr(root, "enable_embeddings"):
                root.enable_embeddings()
            elif hasattr(mem, "enable_embeddings"):
                mem.enable_embeddings()
            with self._deferred_init_lock:
                self.deferred_init_running = False
                self.deferred_init_complete = True
                self.deferred_init_failed = False
                self.deferred_init_error = None
            logger.info(
                "[Startup] Deferred initialization complete (%.1fs)",
                _time.time() - t0,
            )
            if getattr(self, "_planner_startup_probe_pending", False):
                self._planner_startup_probe_pending = False
                try:
                    if self._want_mistral_planner_startup_probe():
                        from .planner_readiness import compute_readiness_label, run_startup_planner_probe

                        self._planner_startup_snapshot = run_startup_planner_probe(log_tags_on_fail=True)
                        _lbl = compute_readiness_label()
                        logger.info(
                            "[Autonomy] deferred planner_startup readiness=%s exact_tag_match=%s health_ok=%s",
                            _lbl,
                            self._planner_startup_snapshot.get("exact_tag_match"),
                            self._planner_startup_snapshot.get("startup_health_ok"),
                        )
                except Exception as probe_e:
                    logger.debug("Deferred planner startup probe: %s", probe_e)
            # One automatic vector rebuild recovery attempt if pending
            try:
                rec = self.rebuild_vector_memory_if_pending()
                if rec.get("attempted"):
                    logger.info("[Startup] Attempting deferred vector rebuild recovery...")
                    if rec.get("success"):
                        logger.info("[Startup] Deferred vector rebuild recovery complete")
                    else:
                        logger.warning(
                            "[Startup] Deferred vector rebuild recovery failed: %s",
                            rec.get("error", "unknown"),
                        )
                elif rec.get("skipped"):
                    logger.info(
                        "[Startup] Deferred vector rebuild recovery skipped: %s",
                        rec.get("reason", ""),
                    )
            except Exception as rec_err:
                logger.warning("[Startup] Vector rebuild recovery attempt error: %s", rec_err)
        except Exception as e:
            err_msg = str(e).strip()[:500]
            with self._deferred_init_lock:
                self.deferred_init_running = False
                self.deferred_init_complete = False
                self.deferred_init_failed = True
                self.deferred_init_error = err_msg
            logger.error("[Startup] Deferred initialization failed: %s", err_msg)
            logger.exception("[Startup] Deferred initialization traceback")
        finally:
            if getattr(self, "deferred_init_running", False):
                with self._deferred_init_lock:
                    if self.deferred_init_running:
                        self.deferred_init_running = False
                        self.deferred_init_complete = False
                        self.deferred_init_failed = True
                        self.deferred_init_error = (getattr(self, "deferred_init_error", None) or "Unexpected exit")
                        logger.warning("[Startup] Deferred initialization did not complete normally; marked failed")
            try:
                self._ensure_resource_monitor_started_after_deferred()
            except Exception as e:
                logger.debug("[Startup] resource monitor post-deferred hook: %s", e)
        
    def propose_mutation(
        self, 
        filename: str, 
        new_code: str, 
        require_consensus: bool = True,
        allow_governance_mutation: bool = False,
        request_id: Optional[str] = None,
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        """
        Propose a code mutation with safety checks and consensus.
        
        Args:
            filename: Target file
            new_code: Proposed code
            require_consensus: Whether to require consensus approval
            allow_governance_mutation: If True, allows mutation of governance files
            request_id: Optional approved request_id for replay
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            
        Returns:
            Status message (string for backward compatibility)
        """
        from .mutation import MutationDeniedError, MutationReviewRequiredError, MutationApplyError
        from .trust import GOVERNANCE_MUTATION
        
        # Safety review
        safety_result = self.safety.review_mutation([new_code])
        if "suspicious" in safety_result.lower():
            return f"[Guardian Core] Mutation blocked by safety: {safety_result}"
            
        # Trust validation - use TrustDecision semantics (not truthiness)
        # For non-governance mutations, use legacy "mutation" action (documented in LEGACY_ACTIONS)
        # For governance mutations, use GOVERNANCE_MUTATION constant
        action = GOVERNANCE_MUTATION if allow_governance_mutation else "mutation"
        decision = self.trust.validate_trust_for_action("mutation_engine", action, context={
            "filename": filename,
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        })
        
        # Branch on decision.decision (not truthiness)
        if decision.decision == "deny":
            return f"[Guardian Core] Mutation blocked: {decision.message}"
        elif decision.decision == "review":
            # Review required - mutation engine will handle enqueueing
            # We still need to check consensus if required
            pass  # Will be handled by mutation engine
        # elif decision.decision == "allow": proceed
            
        # Consensus voting if required
        if require_consensus:
            self.consensus.cast_vote("mutation_engine", "approve_mutation", 0.8,
                                   f"Proposed mutation for {filename}")
            self.consensus.cast_vote("safety_engine", "approve_mutation", 0.7,
                                   "Safety review passed")
            # Additional agents vote based on their state
            trust_level = self.trust.get_trust("mutation_engine")
            if trust_level is not None:
                self.consensus.cast_vote("trust_matrix", "approve_mutation",
                                       max(0.0, min(1.0, trust_level)),
                                       f"Trust level {trust_level:.2f}")
            active = self.tasks.get_active_tasks()
            high_priority = sum(1 for t in active if (t.get("priority") or 0) >= 0.9)
            task_vote = 0.8 if high_priority == 0 else 0.5  # Slight caution when busy
            self.consensus.cast_vote("task_engine", "approve_mutation", task_vote,
                                   f"Active high-priority tasks: {high_priority}")
            self.consensus.cast_vote("dream_engine", "approve_mutation", 0.6,
                                   "Creative approval")
            self.consensus.cast_vote("mission_director", "approve_mutation", 0.6,
                                   "Mission context")

            decision_consensus = self.consensus.decide("approve_mutation")
            if decision_consensus != "approve_mutation":
                return "[Guardian Core] Mutation blocked: no consensus"

        # Identity mutation verifier (Elysia module) if available
        identity_verifier = (self._modules or {}).get("identity_verifier")
        if identity_verifier:
            try:
                if hasattr(identity_verifier, "verify_mutation"):
                    ok = identity_verifier.verify_mutation(filename, new_code)
                    if ok is False:
                        return "[Guardian Core] Mutation blocked: identity verifier rejected"
                elif hasattr(identity_verifier, "check_mutation_integrity"):
                    result = identity_verifier.check_mutation_integrity(filename, new_code)
                    if isinstance(result, dict) and result.get("valid") is False:
                        return "[Guardian Core] Mutation blocked: integrity check failed"
            except Exception as e:
                logger.debug(f"Identity verifier check: {e}")

        # Apply mutation (may raise exceptions)
        try:
            result = self.mutation.propose_mutation(
                filename, 
                new_code,
                require_review=False,  # review_with_gpt is disabled
                allow_governance_mutation=allow_governance_mutation,
                request_id=request_id,
                caller_identity=caller_identity,
                task_id=task_id
            )
            
            self._module_last_invoked["mutation"] = datetime.datetime.now().isoformat()
            # Update trust based on result
            if result.ok:
                self.trust.update_trust("mutation_engine", 0.1, "Successful mutation")
                return result.summary
            else:
                self.trust.update_trust("mutation_engine", -0.1, "Failed mutation")
                return result.summary
                
        except MutationDeniedError as e:
            self.trust.update_trust("mutation_engine", -0.1, "Mutation denied")
            return f"[Guardian Core] Mutation denied: {e.reason}"
        except MutationReviewRequiredError as e:
            # Review required - return message with request_id
            return f"[Guardian Core] Mutation requires review: {e.summary} (Request ID: {e.request_id})"
        except MutationApplyError as e:
            self.trust.update_trust("mutation_engine", -0.1, "Mutation apply failed")
            return f"[Guardian Core] Mutation apply failed: {e.error}"
        
    def create_task(self, name: str, description: str, priority: float = 0.5,
                   category: str = "general") -> Dict[str, Any]:
        """
        Create a new task with consensus validation.
        
        Args:
            name: Task name
            description: Task description
            priority: Task priority
            category: Task category
            
        Returns:
            Created task
        """
        # Validate task creation
        if priority > 0.9:
            self.safety.challenge(f"High priority task: {name}", "task_creation")
            
        task = self.tasks.create_task(name, description, priority, category)
        
        # Log task creation
        self.memory.remember(
            f"[Guardian Core] Created task: {name}",
            category="task",
            priority=priority
        )
        self._module_last_invoked["tasks"] = datetime.datetime.now().isoformat()
        return task
        
    def get_startup_operational_state(self) -> Dict[str, Any]:
        """
        Canonical operational state: deferred init, memory, vector, dashboard.
        Single source of truth for status APIs, CLI, and UI. Do not compute these elsewhere.
        """
        started = getattr(self, "deferred_init_started", False)
        running = getattr(self, "deferred_init_running", False)
        complete = getattr(self, "deferred_init_complete", True)
        failed = getattr(self, "deferred_init_failed", False)
        if started and not running and not complete and not failed:
            state = "inconsistent"
        elif running:
            state = "running"
        elif complete:
            state = "complete"
        elif failed:
            state = "failed"
        else:
            state = "not_started"
        out: Dict[str, Any] = {
            "deferred_init_started": started,
            "deferred_init_running": running,
            "deferred_init_complete": complete,
            "deferred_init_failed": failed,
            "deferred_init_error": getattr(self, "deferred_init_error", None),
            "deferred_init_state": state,
            "memory_loaded": False,
            "memory_count_authoritative": False,
            "vector_loaded": True,
            "vector_degraded": False,
            "vector_rebuild_pending": False,
            "last_vector_rebuild_attempt_at": None,
            "last_vector_rebuild_result": None,
            "last_vector_rebuild_reason": None,
            "last_vector_rebuild_error": None,
            "dashboard_ready": False,
            "resolved_memory_filepath": None,
        }
        mem = getattr(self, "memory", None)
        if mem is not None and hasattr(mem, "get_memory_state"):
            st = mem.get_memory_state(load_if_needed=False)
            out["memory_loaded"] = bool(st.get("memory_loaded", st.get("json_loaded", False)))
            out["memory_count_authoritative"] = bool(st.get("memory_count_authoritative", False))
            out["vector_loaded"] = bool(st.get("vector_loaded", True))
        vm = getattr(mem, "vector_memory", None) if mem else None
        if vm is not None:
            out["vector_degraded"] = bool(getattr(vm, "degraded", False))
            out["vector_rebuild_pending"] = bool(getattr(vm, "rebuild_pending", False))
            out["last_vector_rebuild_attempt_at"] = getattr(vm, "last_rebuild_attempt_at", None)
            out["last_vector_rebuild_result"] = getattr(vm, "last_rebuild_result", None)
            out["last_vector_rebuild_reason"] = getattr(vm, "last_rebuild_reason", None)
            out["last_vector_rebuild_error"] = getattr(vm, "last_rebuild_error", None)
        panel = getattr(self, "ui_panel", None)
        if panel is not None and hasattr(panel, "is_ready"):
            out["dashboard_ready"] = bool(panel.is_ready())
        out["resolved_memory_filepath"] = self.config.get("memory_filepath")
        try:
            from .planner_readiness import compact_runtime_status

            out["planner_runtime_status"] = compact_runtime_status()
        except Exception:
            out["planner_runtime_status"] = {}
        try:
            from .startup_runtime_guard import (
                early_runtime_budget_active,
                observe_memory_thin_transition,
                startup_age_sec,
                startup_memory_thin_mode_active,
            )

            out["startup_thin_mode"] = bool(startup_memory_thin_mode_active(self))
            out["early_runtime_budget"] = bool(early_runtime_budget_active(self))
            _sag = startup_age_sec(self)
            out["startup_age_sec"] = round(float(_sag), 1) if _sag is not None else None
            observe_memory_thin_transition(self)
        except Exception:
            out["startup_thin_mode"] = False
            out["early_runtime_budget"] = False
            out["startup_age_sec"] = None
        out["embedding_fallback_loaded"] = bool(
            getattr(vm, "_sentence_transformer_model", None) is not None
        )
        return out

    def get_planner_runtime_status(self) -> Dict[str, Any]:
        """Compact planner / Ollama / cloud routing view for live diagnostics."""
        try:
            from .planner_readiness import compact_runtime_status

            return compact_runtime_status()
        except Exception:
            return {}

    def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status including capabilities.
        
        Returns:
            System status dictionary
        """
        memory_stats = self.memory.get_memory_stats()
        if hasattr(self.memory, "get_memory_state"):
            memory_stats = {**memory_stats, **self.memory.get_memory_state(load_if_needed=False)}
        task_stats = self.tasks.get_task_stats()
        trust_report = self.trust.get_trust_report()
        consensus_stats = self.consensus.get_agent_stats()
        
        # Get capability report
        try:
            from .capabilities import get_capabilities
            capabilities = get_capabilities()
        except Exception as e:
            logger.debug(f"Could not get capabilities: {e}")
            capabilities = {}
        
        # operational_state is canonical; deferred_init_* copied from it for backward compat
        op = self.get_startup_operational_state()
        return {
            "uptime": (datetime.datetime.now() - self.start_time).total_seconds(),
            "memory": memory_stats,
            "tasks": task_stats,
            "trust": trust_report,
            "consensus": consensus_stats,
            "safety_level": self.safety.get_safety_report()["safety_level"],
            "active_components": len(self.consensus.agents),
            "monitoring": self.monitor.get_system_health(),
            "introspection": self.reflector.summarize_self(),
            "capabilities": capabilities,
            "module_last_invoked": getattr(self, "_module_last_invoked", {}),
            "deferred_init_started": op.get("deferred_init_started", False),
            "deferred_init_running": op.get("deferred_init_running", False),
            "deferred_init_complete": op.get("deferred_init_complete", True),
            "deferred_init_failed": op.get("deferred_init_failed", False),
            "deferred_init_error": op.get("deferred_init_error"),
            "defer_heavy_startup": getattr(self, "_defer_heavy_startup", False),
            "operational_state": op,
            "adversarial_self_learning": get_adversarial_status(self),
            "planner_runtime_status": op.get("planner_runtime_status", {}),
        }
        
    def run_safety_check(self) -> Dict[str, Any]:
        """
        Run a comprehensive safety check.
        
        Returns:
            Safety check results
        """
        results = {
            "timestamp": datetime.datetime.now().isoformat(),
            "checks": []
        }
        
        # Check trust levels
        low_trust = self.trust.get_low_trust_components()
        if low_trust:
            results["checks"].append({
                "type": "trust_warning",
                "message": f"Low trust components: {low_trust}",
                "severity": "medium"
            })
            
        # Check system health
        task_stats = self.tasks.get_task_stats()
        if hasattr(self.memory, "get_memory_state"):
            mem_state = self.memory.get_memory_state(load_if_needed=False)
        elif hasattr(self.memory, "get_memory_count"):
            c = self.memory.get_memory_count(load_if_needed=False)
            mem_state = {"memory_count": c, "memory_count_authoritative": c is not None}
        else:
            mem_state = {"memory_count": None, "memory_count_authoritative": False}
        mc = mem_state.get("memory_count")
        health_metrics = {
            "memory_usage": (mc / 1000.0) if mem_state.get("memory_count_authoritative") and mc is not None else None,
            "memory_count_authoritative": mem_state.get("memory_count_authoritative", True),
            "task_count": task_stats["active_tasks"],
            "consensus_pending": len(self.consensus.votes)
        }
        
        health_check = self.safety.check_system_health(health_metrics)
        if "concerns" in health_check:
            results["checks"].append({
                "type": "health_warning",
                "message": health_check,
                "severity": "high"
            })
            
        # Check for recent errors
        recent_errors = self.memory.get_memories_by_category("error")
        if recent_errors:
            results["checks"].append({
                "type": "error_warning",
                "message": f"Recent errors: {len(recent_errors)}",
                "severity": "high"
            })
            
        return results
        
    def begin_dream_cycle(self, cycles: int = 1) -> List[str]:
        """
        Begin a creative dream cycle.
        
        Args:
            cycles: Number of dream cycles
            
        Returns:
            List of dream thoughts
        """
        return self.dreams.begin_dream_cycle(cycles)
        
    def fetch_web_content(self, url: str) -> Optional[str]:
        """
        Fetch content from a URL.
        
        Args:
            url: URL to fetch
            
        Returns:
            Extracted content or None
        """
        try:
            return self.web_reader.fetch(url, caller_identity="GuardianCore", task_id="unknown")
        except TrustDeniedError:
            # Re-raise TrustDeniedError - it's explicit and should propagate
            raise
        except Exception as e:
            # For other exceptions (network errors, etc.), return None
            self.memory.remember(
                f"[Guardian Core] WebReader.fetch() failed: {str(e)}",
                category="error",
                priority=0.7
            )
            return None
        
    def speak_message(self, message: str, mode: str = "guardian") -> None:
        """
        Speak a message using voice synthesis.
        
        Args:
            message: Message to speak
            mode: Voice mode
        """
        self.voice.set_mode(mode)
        self.voice.speak(message)
        
    def ask_ai(self, question: str) -> str:
        """
        Ask an AI model a question.
        
        Args:
            question: Question to ask
            
        Returns:
            AI response
        """
        response = self.ai_interaction.ask_chatgpt(question)
        # Log for prompt evolution (score unknown; evolver uses this for learning)
        if self.prompt_evolver and not response.startswith("Error:"):
            self.prompt_evolver.log_interaction(
                task_type="conversation",
                prompt=question,
                response=response,
                score=0.5,
            )
        return response
        
    def create_mission(self, name: str, goal: str, priority: str = "medium") -> Dict[str, Any]:
        """
        Create a new mission.
        
        Args:
            name: Mission name
            goal: Mission goal
            priority: Mission priority
            
        Returns:
            Created mission
        """
        return self.missions.create_mission(name, goal, priority)
        
    def get_context(self, keyword: Optional[str] = None, tag: Optional[str] = None, minutes: int = 60) -> str:
        """
        Get context from memory.
        
        Args:
            keyword: Keyword to search for
            tag: Tag to search for
            minutes: Minutes to look back
            
        Returns:
            Context string
        """
        if keyword:
            return self.context.build_context_by_keyword(keyword)
        elif tag:
            return self.context.build_context_by_tag(tag)
        else:
            return self.context.build_recent_context(minutes)
        
    def get_system_summary(self) -> str:
        """
        Get a human-readable system summary.
        
        Returns:
            System summary string
        """
        status = self.get_system_status()
        safety = self.run_safety_check()
        
        summary = f"[Guardian Core] System Summary:\n"
        summary += f"  Uptime: {status['uptime']:.0f}s\n"
        summary += f"  Memory: {status['memory']['total_memories']} entries\n"
        summary += f"  Tasks: {status['tasks']['active_tasks']} active\n"
        summary += f"  Trust: {status['trust']['average_trust']:.2f} avg\n"
        summary += f"  Consensus: {status['consensus']['total_agents']} agents\n"
        summary += f"  Safety: {status['safety_level']}\n"
        summary += f"  Health Checks: {len(safety['checks'])} warnings"
        
        # Add new component summaries
        mission_stats = self.missions.get_mission_stats()
        summary += f"\n  Missions: {mission_stats['active_missions']} active"
        
        dream_stats = self.dreams.get_dream_stats()
        summary += f"\n  Dreams: {dream_stats['total_dreams']} generated"
        
        return summary

    def decide_from_introspection(self) -> Dict[str, Any]:
        """
        Use reflector output to inform decisions. Runs periodically from heartbeat.
        Feeds introspection (identity, behavior, focus) into the system and can
        trigger learning or dream cycles when suggested.
        """
        result = {"suggested_action": None, "context": {}, "triggered": False}
        cfg = self._load_introspection_config()
        if not cfg.get("enabled", True):
            return result
        if not hasattr(self, "reflector") or not self.reflector:
            return result
        now = datetime.datetime.now()
        last = getattr(self, "_last_introspection_trigger", {})
        throttle_min = cfg.get("throttle_minutes", 30)
        try:
            summary = self.reflector.summarize_self()
            behavior = self.reflector.reflect_on_behavior()
            result["context"] = {
                "focus": behavior.get("dominant_category", "general"),
                "pattern": behavior.get("behavior_pattern", "unknown"),
                "activity": behavior.get("recent_activity_count", 0),
                "active_tasks": summary.get("active_tasks", "0"),
            }
            focus = result["context"].get("focus", "general")
            activity = result["context"].get("activity", 0)
            if focus == "learning" and activity < 5:
                result["suggested_action"] = "consider_learning"
            elif focus == "creativity" or (activity < 3 and self.dreams.get_dream_stats().get("total_dreams", 0) < 10):
                result["suggested_action"] = "consider_dream_cycle"
            elif "mission" in str(summary.get("active_tasks", "")) or focus == "mission":
                result["suggested_action"] = "continue_mission"
            elif focus == "general" and getattr(self, "prompt_evolver", None) and self.prompt_evolver.ask_ai:
                try:
                    with self.prompt_evolver._lock:
                        low = [r for r in self.prompt_evolver.records if r.score < 0.5]
                    if len(low) >= 3:
                        result["suggested_action"] = "consider_prompt_evolution"
                except Exception:
                    pass
            if result["suggested_action"]:
                thought = f"[Introspection Decision] Focus={focus} pattern={result['context'].get('pattern')} -> suggest: {result['suggested_action']}"
                self.memory.remember(thought, category="introspection", priority=0.6, metadata=result["context"])
                # Throttle check
                last_ts = last.get(result["suggested_action"])
                can_trigger = last_ts is None or (now - last_ts).total_seconds() > throttle_min * 60
                if can_trigger and result["suggested_action"] in ("consider_learning", "consider_dream_cycle", "continue_mission", "consider_prompt_evolution"):
                    if result["suggested_action"] == "consider_dream_cycle" and cfg.get("trigger_dreams", True):
                        try:
                            self.dreams.begin_dream_cycle(1)
                            self._module_last_invoked["dreams"] = now.isoformat()
                            result["triggered"] = True
                            self._last_introspection_trigger = {**last, "consider_dream_cycle": now}
                        except Exception as e:
                            logger.debug(f"Introspection dream trigger: {e}")
                    elif result["suggested_action"] == "consider_learning" and cfg.get("trigger_learning", True):
                        try:
                            self._trigger_introspection_learning()
                            result["triggered"] = True
                            self._last_introspection_trigger = {**last, "consider_learning": now}
                        except Exception as e:
                            logger.debug(f"Introspection learning trigger: {e}")
                    elif result["suggested_action"] == "continue_mission" and cfg.get("suggest_objectives", True):
                        try:
                            self._suggest_objective_from_introspection(result["context"])
                            result["triggered"] = True
                            self._last_introspection_trigger = {**last, "continue_mission": now}
                        except Exception as e:
                            logger.debug(f"Introspection objective suggest: {e}")
                    elif result["suggested_action"] == "consider_prompt_evolution" and getattr(self, "run_prompt_evolution", None):
                        try:
                            self.run_prompt_evolution(min_records=3)
                            result["triggered"] = True
                            self._last_introspection_trigger = {**last, "consider_prompt_evolution": now}
                        except Exception as e:
                            logger.debug(f"Introspection prompt evolution: {e}")
        except Exception as e:
            logger.debug(f"decide_from_introspection: {e}")
        self._last_introspection_result = result
        return result

    def _trigger_introspection_learning(self) -> None:
        """Run a small learning session (background) when introspection suggests it."""
        guardian = self
        def _run():
            try:
                from .auto_learning import run_learning_session, get_learned_storage_path, get_chatlogs_path, load_learning_config, DEFAULT_REDDIT_SUBS
                cfg = load_learning_config()
                storage = get_learned_storage_path()
                chatlogs = get_chatlogs_path()
                reddit_subs = cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS[:1]
                llm = None
                try:
                    import sys
                    main_mod = sys.modules.get("__main__")
                    if main_mod:
                        status_sys = getattr(main_mod, "_status_system", None)
                        if status_sys and hasattr(status_sys, "chat_with_llm"):
                            llm = lambda m: status_sys.chat_with_llm(m)
                except Exception:
                    pass
                result = run_learning_session(
                    storage_path=storage,
                    topics=[],
                    reddit_subs=reddit_subs,
                    rss_feeds=[],
                    chatlogs_path=None,
                    max_per_source=2,
                    max_chatlogs=0,
                    llm_callback=llm,
                    memory=guardian.memory,
                )
                guardian.memory.remember("[Introspection] Auto-learning triggered (2 Reddit items)", category="learning", priority=0.55)
                # Event-driven adversarial: bad learning session
                try:
                    trigger_adversarial_on_event(guardian, TRIGGER_BAD_LEARNING_SESSION, result)
                except Exception as ae:
                    logger.debug("Adversarial learning trigger: %s", ae)
            except Exception as e:
                logger.debug(f"Introspection learning: {e}")
        threading.Thread(target=_run, daemon=True, name="IntrospectionLearning").start()

    def _suggest_objective_from_introspection(self, context: Dict[str, Any]) -> None:
        """Suggest an objective to LongTermPlanner based on introspection focus/pattern."""
        planner = None
        if self._modules:
            planner = self._modules.get("longterm_planner")
        if not planner or not hasattr(planner, "suggest_from_introspection"):
            return
        try:
            planner.suggest_from_introspection(context, memory=self.memory)
        except Exception as e:
            logger.debug(f"suggest_from_introspection: {e}")
        
    def wire_modules(self, modules: Dict[str, Any]) -> None:
        """Receive reference to Elysia modules (LongTermPlanner, etc.) after init."""
        self._modules = modules
        tr = (modules or {}).get("tool_registry")
        if tr is not None and hasattr(tr, "ensure_minimal_builtin_tools"):
            try:
                pre = len(getattr(tr, "tools", {}) or {}) if isinstance(getattr(tr, "tools", None), dict) else -1
                tr.ensure_minimal_builtin_tools()
                post = len(getattr(tr, "tools", {}) or {}) if isinstance(getattr(tr, "tools", None), dict) else -1
                lt_n = len(tr.list_tools() or []) if hasattr(tr, "list_tools") else -1
                tm_n = len(tr.tools_map()) if hasattr(tr, "tools_map") else -1
                logger.info(
                    "[Guardian] tool_registry live wire id=%s cls=%s storage_pre=%s storage_post=%s list_tools=%s tools_map=%s",
                    id(tr),
                    type(tr).__name__,
                    pre,
                    post,
                    lt_n,
                    tm_n,
                )
            except Exception as e:
                logger.debug("tool_registry ensure on wire_modules: %s", e)
        try:
            self._orchestration_registry.refresh(self)
        except Exception as e:
            logger.debug("Orchestration capability refresh after wire_modules: %s", e)

    def _build_capability_task_context(self) -> str:
        """Objective + recent memory lines for capability matching (pre-decision)."""
        parts: List[str] = []
        try:
            am = self.missions.get_active_missions()
            if am:
                parts.append(str(am[0].get("name", "")))
        except Exception:
            pass
        if not parts and (self._modules or {}).get("longterm_planner"):
            try:
                planner = self._modules["longterm_planner"]
                raw = getattr(planner, "objectives", {})
                seq = list(raw.values()) if isinstance(raw, dict) else (list(raw) if isinstance(raw, list) else [])
                for o in seq:
                    st = str((o or {}).get("status", "")).lower() if isinstance(o, dict) else ""
                    if "active" in st:
                        parts.append(str((o or {}).get("name", "")))
                        break
            except Exception:
                pass
        try:
            if getattr(self, "memory", None) and hasattr(self.memory, "recall_last"):
                for m in (self.memory.recall_last(5) or [])[:5]:
                    if isinstance(m, dict):
                        parts.append(str(m.get("thought", ""))[:160])
                    else:
                        parts.append(str(m)[:160])
        except Exception:
            pass
        return " | ".join(parts)[:900]

    def _memory_capability_hints(self, task_ctx: str) -> List[str]:
        """Keyword memory hits to bias capability scores (lightweight)."""
        out: List[str] = []
        if not task_ctx or not getattr(self, "memory", None):
            return out
        try:
            words = [w for w in task_ctx.replace("|", " ").split() if len(w) > 3][:5]
            seen = set()
            for w in words:
                if w.lower() in seen:
                    continue
                seen.add(w.lower())
                if hasattr(self.memory, "search_memories"):
                    for row in (self.memory.search_memories(w, limit=2) or []):
                        t = (row or {}).get("thought", "") if isinstance(row, dict) else str(row)
                        if t:
                            out.append(t[:180])
        except Exception as e:
            logger.debug("memory capability hints: %s", e)
        return out[:8]

    def _tool_registry_list_names(self, tr: Any) -> List[str]:
        if tr is None or not hasattr(tr, "list_tools"):
            return []
        try:
            raw = tr.list_tools()
        except Exception:
            return []
        if isinstance(raw, dict):
            return [str(k) for k in raw.keys()]
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return [str(raw)] if raw else []

    def _tool_registry_pulse_metrics(self, tr: Any) -> Tuple[int, List[str], Dict[str, Any]]:
        """
        Same tool surface as capability_registry.refresh: coerce list_tools() (list or dict) to names,
        plus storage/diagnostic counts. Use this everywhere we log 'N tools' for tool_registry_pulse.
        """
        from .capability_registry import collect_tool_registry_surface_diag, coerce_tool_registry_name_list

        diag: Dict[str, Any] = {
            "registry_id": id(tr) if tr is not None else None,
            "registry_class": type(tr).__name__ if tr is not None else None,
        }
        if tr is None:
            diag["reason"] = "no_tool_registry"
            return 0, [], diag
        storage_n = 0
        try:
            td = getattr(tr, "tools", None)
            if isinstance(td, dict):
                storage_n = len(td)
        except Exception:
            pass
        diag["raw_tools_map_count"] = storage_n
        names, coerce_exc = coerce_tool_registry_name_list(tr, 96)
        diag["coerce_suffix"] = coerce_exc or ""
        n = len(names)
        diag["list_tools_usable_count"] = n
        diag["first_names"] = names[:8]
        try:
            raw = tr.list_tools()
            diag["list_tools_return_type"] = type(raw).__name__
            if isinstance(raw, dict):
                diag["raw_list_tools_len"] = len(raw)
                diag["raw_first_names"] = [str(k) for k in list(raw.keys())[:8]]
            elif isinstance(raw, (list, tuple)):
                diag["raw_list_tools_len"] = len(raw)
                diag["raw_first_names"] = [str(x) for x in raw[:8]]
            else:
                diag["raw_list_tools_len"] = 0
                diag["raw_first_names"] = []
        except Exception as ex:
            diag["list_tools_exc"] = str(ex)
        try:
            d2 = collect_tool_registry_surface_diag(
                tr,
                listed_count=n,
                storage_before_ensure=storage_n,
                storage_after_ensure=storage_n,
            )
            diag["surface"] = d2
            if d2.get("filter_reason") and d2.get("filter_reason") != "ok":
                diag["exclusion_hint"] = d2.get("filter_reason")
        except Exception:
            pass
        return n, names, diag

    def _tool_registry_minimal_capabilities_ok(self, tr: Any) -> bool:
        """True when registry exposes llm + web + exec class tools (or builtin trio)."""
        names = [n.lower() for n in self._tool_registry_list_names(tr)]
        if not names:
            return False
        required = {"elysia_builtin_llm", "elysia_builtin_web", "elysia_builtin_exec"}
        if required <= set(names):
            return True
        blob = " ".join(names)
        has_llm = any(
            x in blob
            for x in ("llm", "gpt", "chat", "openai", "mistral", "claude", "completion", "builtin_llm")
        )
        has_web = any(
            x in blob for x in ("web", "http", "url", "fetch", "browser", "scrape", "builtin_web")
        )
        has_exec = any(
            x in blob for x in ("exec", "shell", "bash", "python", "code", "run", "script", "builtin_exec")
        )
        return bool(has_llm and has_web and has_exec)

    def _structured_router_probe_task(self) -> Dict[str, Any]:
        """Structured payload for task_router (never raw system logs)."""
        pdc = getattr(self, "_pre_decision_context", None) or {}
        ctx = (pdc.get("task_context") or "").strip()
        if len(ctx) < 4 or "idle exploration" in ctx.lower():
            ctx = ""
        if len(ctx) < 4:
            try:
                am = self.missions.get_active_missions()
                if am:
                    ctx = str(am[0].get("name", ""))[:400]
            except Exception:
                pass
        if len(ctx) < 4:
            ctx = "orchestration_routing_probe"
        return {
            "task_type": "routing_probe",
            "objective": ctx[:500],
            "payload": {
                "source": "guardian",
                "format_version": 1,
                "probe_role": "registry_router_health",
                "does_not_execute_registered_tools": True,
            },
            # TaskRouter only: adds tie diagnostics; does not change winner vs omitting this flag.
            "_guardian_router_health_probe": True,
        }

    def _invoke_task_router_probe(self, router: Any) -> Any:
        task = self._structured_router_probe_task()
        try:
            return router.route_task(task["task_type"], task)
        except Exception as e:
            logger.debug("task_router probe: %s", e)
            return None

    def _run_tool_registry_pulse_quick(self) -> bool:
        """Low-risk registry + router probe (idle / exploration)."""
        tr = (self._modules or {}).get("tool_registry")
        if not tr:
            return False
        if hasattr(tr, "ensure_minimal_builtin_tools"):
            try:
                tr.ensure_minimal_builtin_tools()
            except Exception:
                pass
        if not self._tool_registry_minimal_capabilities_ok(tr):
            logger.info("[Idle] tool_registry probe skipped (missing llm/web/exec tools)")
            return False
        n, _pulse_names, pulse_diag = self._tool_registry_pulse_metrics(tr)
        logger.debug(
            "[Idle] tool_registry metrics id=%s cls=%s usable=%s map=%s first=%s",
            pulse_diag.get("registry_id"),
            pulse_diag.get("registry_class"),
            n,
            pulse_diag.get("raw_tools_map_count"),
            pulse_diag.get("first_names"),
        )
        route_hint = ""
        route_to = None
        router = (self._modules or {}).get("task_router")
        if router and hasattr(router, "route_task"):
            try:
                r = self._invoke_task_router_probe(router)
                if isinstance(r, dict):
                    route_to = r.get("routed_to")
                    route_hint = f" route_registry_health->{route_to}"
            except Exception:
                pass
        self._tool_registry_last_sig = f"{n}:{route_to}"
        self._tool_registry_last_pulse_ts = time.time()
        logger.info(
            "[Idle] registry_router_health_probe: %d tools visible (no tool execution)%s",
            n,
            route_hint,
        )
        self._module_last_invoked["tool_registry"] = datetime.datetime.now().isoformat()
        return True

    def _idle_capability_probe_if_needed(self, autonomy_cfg: Dict[str, Any]) -> None:
        if not autonomy_cfg.get("idle_capability_probe", True):
            return
        interval = float(autonomy_cfg.get("idle_capability_probe_interval_sec", 1800))
        now = time.time()
        if now - getattr(self, "_last_idle_capability_probe_ts", 0.0) < interval:
            return
        self._last_idle_capability_probe_ts = now
        try:
            cap_snap = self._orchestration_registry.refresh_if_due(self, min_interval_sec=60.0)
            ranked = self._orchestration_registry.get_relevant_capabilities(
                "idle exploration validate tools apis low risk", self, snapshot=cap_snap, top_k=10
            )
            logger.info("[Idle] Capability probe — candidates: %s", [r.get("name") for r in ranked[:6]])
            try:
                from .capability_execution import capability_action_is_safe_idle, execute_capability_kind

                for r in ranked[:6]:
                    rk = str(r.get("type") or "")
                    rn = str(r.get("name") or "")
                    if not capability_action_is_safe_idle(rk, rn):
                        continue
                    ex = execute_capability_kind(self, rk, rn, {})
                    logger.info(
                        "[Idle] capability execute kind=%s name=%s success=%s",
                        rk,
                        rn,
                        bool(ex.get("success")),
                    )
                    try:
                        self._orchestration_registry.log_capability_usage(
                            task="idle_probe",
                            capability_id=f"idle:{rk}:{rn}",
                            capability_type="idle_probe",
                            success=bool(ex.get("success")),
                            quality=0.72 if ex.get("success") else 0.22,
                            latency_ms=0.0,
                            extra={"snippet": str(ex.get("result", ex.get("error")))[:320]},
                        )
                    except Exception:
                        pass
                    break
            except Exception as ie:
                logger.debug("Idle capability execute: %s", ie)
        except Exception as e:
            logger.debug("Idle capability probe: %s", e)
        try:
            if (self._modules or {}).get("tool_registry"):
                self._run_tool_registry_pulse_quick()
        except Exception as e:
            logger.debug("Idle tool_registry pulse: %s", e)

    def get_next_action(self) -> Dict[str, Any]:
        """
        Unified Next Action: aggregate pending items from all sources and pick top priority.
        Returns: { action, source, reason, priority_score, candidates, can_auto_execute }
        """
        with self._get_next_action_lock:
            return self._get_next_action_impl()

    def _get_next_action_impl(self) -> Dict[str, Any]:
        """Body of get_next_action (must hold _get_next_action_lock via get_next_action)."""
        candidates = []
        # 1. Mission deadlines (highest urgency)
        try:
            issues = self.missions.check_deadlines()
            if issues:
                m = issues[0]
                candidates.append({
                    "action": "mission_deadline",
                    "source": "missions",
                    "reason": f"Mission '{m['mission']}' is {m.get('issue', 'overdue')}",
                    "priority_score": 10,
                    "can_auto_execute": False,
                    "metadata": m,
                })
        except Exception:
            pass
        # 2. High-priority tasks (safety, system)
        try:
            active = self.tasks.get_active_tasks()
            for t in active:
                if t.get("category") in ("safety", "system", "adversarial") or (t.get("priority", 0) or 0) >= 0.9:
                    candidates.append({
                        "action": "execute_task",
                        "source": "tasks",
                        "reason": t.get("name", "High-priority task"),
                        "priority_score": 9,
                        "can_auto_execute": False,
                        "metadata": {"task_id": t.get("id"), "name": t.get("name")},
                    })
                    break
        except Exception:
            pass
        # 3. Active missions (no deadline issue)
        if not any(c["action"] == "mission_deadline" for c in candidates):
            try:
                am = self.missions.get_active_missions()
                if am:
                    m = am[0]
                    candidates.append({
                        "action": "continue_mission",
                        "source": "missions",
                        "reason": f"Advance mission: {m.get('name', 'Unknown')} ({m.get('progress', 0) * 100:.0f}% done)",
                        "priority_score": 7,
                        "can_auto_execute": True,
                        "metadata": {"mission": m.get("name")},
                    })
            except Exception:
                pass
        # 4. Task queue (pending execution)
        try:
            tq = getattr(self.elysia_loop, "task_queue", None)
            if tq and hasattr(tq, "get_queue_size") and tq.get_queue_size() > 0:
                candidates.append({
                    "action": "process_queue",
                    "source": "elysia_loop",
                    "reason": f"{tq.get_queue_size()} task(s) in queue",
                    "priority_score": 6,
                    "can_auto_execute": True,
                    "metadata": {"queue_size": tq.get_queue_size()},
                })
        except Exception:
            pass
        # 5. Introspection suggestion
        try:
            last = getattr(self, "_last_introspection_result", None)
            if last and last.get("suggested_action"):
                action = last["suggested_action"]
                reason = f"Introspection suggests: {action}"
                can_auto = action in ("consider_learning", "consider_dream_cycle", "consider_prompt_evolution") and not last.get("triggered")
                candidates.append({
                    "action": action,
                    "source": "introspection",
                    "reason": reason,
                    "priority_score": 5,
                    "can_auto_execute": can_auto,
                    "metadata": last.get("context", {}),
                })
        except Exception:
            pass
        # 5b. Prompt evolution (enough low-scoring records)
        try:
            if getattr(self, "prompt_evolver", None) and self.prompt_evolver.ask_ai:
                with self.prompt_evolver._lock:
                    low = [r for r in self.prompt_evolver.records if r.score < 0.5]
                if len(low) >= 3:
                    candidates.append({
                        "action": "consider_prompt_evolution",
                        "source": "prompt_evolver",
                        "reason": f"{len(low)} low-scoring prompts to evolve",
                        "priority_score": 4,
                        "can_auto_execute": True,
                        "metadata": {"low_scoring_count": len(low)},
                    })
        except Exception:
            pass
        # 5b1. Vector rebuild (when degraded or rebuild pending)
        try:
            op = self.get_startup_operational_state()
            if op.get("vector_degraded") or op.get("vector_rebuild_pending"):
                candidates.append({
                    "action": "rebuild_vector",
                    "source": "operational_state",
                    "reason": "Vector memory degraded or rebuild pending",
                    "priority_score": 8,
                    "can_auto_execute": True,
                    "metadata": {},
                })
        except Exception:
            pass
        # 5b2. Adversarial self-learning (throttled to every 30 min)
        try:
            last = getattr(self, "_adversarial_last_run", None)
            throttle_min = 30
            should_run = True
            if last and last.get("last_run"):
                try:
                    then = datetime.datetime.fromisoformat(last["last_run"])
                    if (datetime.datetime.now() - then).total_seconds() < throttle_min * 60:
                        should_run = False
                except Exception:
                    pass
            if should_run:
                # Novelty gating: if adversarial learning repeatedly yields the same finding
                # without creating actionable tasks, back off aggressively.
                cool_until = getattr(self, "_adversarial_low_yield_cooldown_until", None)
                if cool_until and isinstance(cool_until, (int, float)) and time.time() < float(cool_until):
                    should_run = False
                    logger.info("[Adversarial] Suppressing consider_adversarial_learning (low-yield cooldown active)")

                candidates.append({
                    "action": "consider_adversarial_learning",
                    "source": "adversarial_self_learning",
                    "reason": "Adversarial self-learning cycle (weakness discovery, refinement)",
                    "priority_score": 5,
                    "can_auto_execute": True,
                    "metadata": {},
                })
        except Exception:
            pass
        # 5c. FractalMind planning (when available and no higher priority)
        try:
            fm = (self._modules or {}).get("fractalmind")
            if fm and hasattr(fm, "process_task"):
                cool_until = getattr(self, "_fractalmind_low_yield_cooldown_until", None)
                rep_until = getattr(self, "_fractalmind_repetition_suppress_until", None)
                if cool_until and isinstance(cool_until, (int, float)) and time.time() < float(cool_until):
                    logger.info("[FractalMind] Suppressing fractalmind_planning (low-yield cooldown active)")
                elif rep_until and isinstance(rep_until, (int, float)) and time.time() < float(rep_until):
                    logger.info("[FractalMind] Suppressing fractalmind_planning (repeated-artifact cooldown active)")
                else:
                    candidates.append({
                        "action": "fractalmind_planning",
                        "source": "fractalmind",
                        "reason": "FractalMind available for task breakdown",
                        "priority_score": 3,
                        "can_auto_execute": True,
                        "metadata": {},
                    })
        except Exception:
            pass
        # 5d. Harvest Engine — Gumroad/local income snapshot
        try:
            he = (self._modules or {}).get("harvest_engine")
            if he and hasattr(he, "generate_income_report"):
                candidates.append({
                    "action": "harvest_income_report",
                    "source": "harvest_engine",
                    "reason": "Refresh Harvest income report (Gumroad aggregate / local)",
                    "priority_score": 4,
                    "can_auto_execute": True,
                    "metadata": {},
                })
        except Exception:
            pass
        # 5e. Income modules (launcher: generator, wallet, financial manager)
        try:
            m = self._modules or {}
            if m.get("income_generator") or m.get("wallet") or m.get("financial_manager"):
                # Event-driven suppression:
                # If last pulse showed all-zero state and nothing changed, don't keep offering this action.
                now_ts = time.time()
                refresh_sec = 1800  # 30m: slow refresh while state appears stagnant
                last_sig = getattr(self, "_income_modules_last_sig", None)
                last_ts = getattr(self, "_income_modules_last_pulse_ts", 0.0) or 0.0
                all_zero = False
                sig = None
                try:
                    ig = m.get("income_generator")
                    wallet = m.get("wallet")
                    fm = m.get("financial_manager")
                    earned = 0.0
                    active = 0
                    wallet_total = 0.0
                    elysia_acct = 0.0
                    cash = 0.0

                    if ig and hasattr(ig, "get_income_summary"):
                        s = ig.get_income_summary()
                        if isinstance(s, dict):
                            earned = float(s.get("total_earned", 0) or 0)
                            active = int(s.get("active_projects", 0) or 0)
                    if wallet and hasattr(wallet, "get_balance"):
                        b = wallet.get_balance()
                        if isinstance(b, dict):
                            wallet_total = float(b.get("total_balance", b.get("available_balance", 0) or 0) or 0)
                            accs = (b.get("accounts") if isinstance(b.get("accounts"), dict) else None)
                            # Some wallet impls expose accounts under wallet.wallet.accounts
                            if hasattr(getattr(wallet, "wallet", None), "get") and isinstance(getattr(wallet, "wallet", None), dict):
                                # fallback; handled below by direct access in action executor
                                pass
                            if hasattr(wallet, "wallet") and isinstance(getattr(wallet, "wallet", None), dict):
                                try:
                                    accs = wallet.wallet.get("accounts") or accs or {}
                                    ely = accs.get("elysia_autonomy") if isinstance(accs, dict) else {}
                                    if isinstance(ely, dict):
                                        elysia_acct = float(ely.get("balance", 0) or 0)
                                except Exception:
                                    pass
                    if fm and hasattr(fm, "get_financial_status"):
                        st = fm.get_financial_status()
                        if isinstance(st, dict):
                            cash = float(st.get("cash_balance", st.get("balance", 0) or 0) or 0)

                    all_zero = (earned == 0.0 and wallet_total == 0.0 and elysia_acct == 0.0 and cash == 0.0)
                    sig = f"{earned:.2f}:{active}:{wallet_total:.2f}:{elysia_acct:.2f}:{cash:.2f}"
                except Exception:
                    # If snapshot fails, don't suppress (prefer progress over stalling)
                    sig = None
                    all_zero = False

                if sig is not None and last_sig is not None and sig == last_sig and all_zero and (now_ts - last_ts) < refresh_sec:
                    logger.debug("[Adversarial] Suppressing income_modules_pulse (unchanged all-zero state; %.0fs remaining)",
                                 refresh_sec - (now_ts - last_ts))
                else:
                    candidates.append({
                        "action": "income_modules_pulse",
                        "source": "income_modules",
                        "reason": "Pulse income generator / wallet / financial status (read-only summary)",
                        "priority_score": 3,
                        "can_auto_execute": True,
                        "metadata": {},
                    })
        except Exception:
            pass
        # 5f. AI tool registry — tool count and routing sanity check (only if llm/web/exec present)
        try:
            tr = (self._modules or {}).get("tool_registry")
            if tr:
                if hasattr(tr, "ensure_minimal_builtin_tools"):
                    try:
                        tr.ensure_minimal_builtin_tools()
                    except Exception:
                        pass
                if self._tool_registry_minimal_capabilities_ok(tr):
                    now_ts = time.time()
                    refresh_sec = 1800  # 30m: slow refresh while registry seems stagnant/empty
                    last_sig = getattr(self, "_tool_registry_last_sig", None)
                    last_ts = getattr(self, "_tool_registry_last_pulse_ts", 0.0) or 0.0
                    cd_until = float(getattr(self, "_tool_registry_pulse_cooldown_until", 0.0) or 0.0)
                    if cd_until > now_ts:
                        logger.debug(
                            "[Adversarial] Skipping tool_registry_pulse candidate (cooldown %.0fs remaining)",
                            cd_until - now_ts,
                        )
                    else:
                        sig = None
                        try:
                            router = (self._modules or {}).get("task_router")
                            tools_n, _, _ = self._tool_registry_pulse_metrics(tr)
                            route_to = None
                            if tools_n > 0 and router and hasattr(router, "route_task"):
                                r = self._invoke_task_router_probe(router)
                                if isinstance(r, dict):
                                    route_to = r.get("routed_to")
                            sig = f"{tools_n}:{route_to}"
                        except Exception:
                            sig = None

                        if sig is not None and last_sig is not None and sig == last_sig and (now_ts - last_ts) < refresh_sec:
                            logger.debug("[Adversarial] Suppressing tool_registry_pulse (unchanged; %.0fs remaining)",
                                         refresh_sec - (now_ts - last_ts))
                        else:
                            candidates.append({
                                "action": "tool_registry_pulse",
                                "source": "tool_registry",
                                "reason": "Snapshot registered tools and routing probe",
                                "priority_score": 3,
                                "can_auto_execute": True,
                                "metadata": {},
                            })
        except Exception:
            pass
        # 6. LongTermPlanner objectives (objectives may be list or dict)
        try:
            planner = (self._modules or {}).get("longterm_planner")
            if planner and hasattr(planner, "objectives"):
                _objs = planner.objectives
                _seq = list(_objs.values()) if isinstance(_objs, dict) else (list(_objs) if isinstance(_objs, list) else [])
                active_obj = []
                for o in _seq:
                    st = o.get("status", "") if isinstance(o, dict) else getattr(o, "status", "")
                    if "active" in str(st).lower():
                        active_obj.append(o)
                if active_obj:
                    o = active_obj[0]
                    candidates.append({
                        "action": "work_on_objective",
                        "source": "longterm_planner",
                        "reason": f"Objective: {getattr(o, 'name', 'Unknown')}",
                        "priority_score": 5,
                        "can_auto_execute": True,
                        "metadata": {"objective_id": getattr(o, "objective_id", "")},
                    })
        except Exception:
            pass
        # 7. Exploratory / diversity candidates (expand pool to 5–7 options)
        decider_cfg = self._load_mistral_decider_config()
        min_cands = decider_cfg.get("mistral_min_candidates", 5)
        exploratory_actions = decider_cfg.get("mistral_exploratory_actions", [
            "fractalmind_planning", "question_probe", "code_analysis", "consider_prompt_evolution", "work_on_objective", "consider_mutation",
            "harvest_income_report", "income_modules_pulse", "tool_registry_pulse",
        ])
        existing_actions = {c.get("action") for c in candidates}
        for action in exploratory_actions:
            if action not in existing_actions and len(candidates) < min_cands + 2:
                if action == "question_probe":
                    candidates.append({
                        "action": "question_probe",
                        "source": "exploration",
                        "reason": "Probe operator with exploratory question",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "code_analysis" and hasattr(self, "analysis_engine") and self.analysis_engine:
                    candidates.append({
                        "action": "code_analysis",
                        "source": "exploration",
                        "reason": "Run code/context analysis (exploratory)",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "consider_mutation" and hasattr(self, "mutation") and self.mutation:
                    candidates.append({
                        "action": "consider_mutation",
                        "source": "exploration",
                        "reason": "Explore mutation/code evolution (exploratory)",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "fractalmind_planning" and (self._modules or {}).get("fractalmind"):
                    if "fractalmind_planning" not in existing_actions:
                        cool_until = getattr(self, "_fractalmind_low_yield_cooldown_until", None)
                        rep_until = getattr(self, "_fractalmind_repetition_suppress_until", None)
                        low_cool = cool_until and isinstance(cool_until, (int, float)) and time.time() < float(cool_until)
                        rep_cool = rep_until and isinstance(rep_until, (int, float)) and time.time() < float(rep_until)
                        if not low_cool and not rep_cool:
                            candidates.append({
                                "action": "fractalmind_planning",
                                "source": "exploration",
                                "reason": "FractalMind task breakdown (exploratory)",
                                "priority_score": 3,
                                "can_auto_execute": True,
                                "metadata": {"exploratory": True},
                            })
                            existing_actions.add(action)
                elif action == "consider_learning" and getattr(self, "elysia_loop", None):
                    candidates.append({
                        "action": "consider_learning",
                        "source": "exploration",
                        "reason": "Explore auto-learning module",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "consider_dream_cycle" and getattr(self, "dreams", None):
                    candidates.append({
                        "action": "consider_dream_cycle",
                        "source": "exploration",
                        "reason": "Explore dream engine",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "consider_prompt_evolution" and getattr(self, "prompt_evolver", None) and getattr(self.prompt_evolver, "ask_ai", None):
                    candidates.append({
                        "action": "consider_prompt_evolution",
                        "source": "exploration",
                        "reason": "Explore prompt evolution module",
                        "priority_score": 2,
                        "can_auto_execute": True,
                        "metadata": {"exploratory": True},
                    })
                    existing_actions.add(action)
                elif action == "consider_adversarial_learning":
                    # Only add as exploratory fallback when not already in pool (throttle may block 5b2)
                    if "consider_adversarial_learning" not in existing_actions:
                        cool_until = getattr(self, "_adversarial_low_yield_cooldown_until", None)
                        if not (cool_until and isinstance(cool_until, (int, float)) and time.time() < float(cool_until)):
                            candidates.append({
                                "action": "consider_adversarial_learning",
                                "source": "exploration",
                                "reason": "Explore adversarial self-learning",
                                "priority_score": 2,
                                "can_auto_execute": True,
                                "metadata": {"exploratory": True},
                            })
                            existing_actions.add(action)
                elif action == "work_on_objective" and (self._modules or {}).get("longterm_planner"):
                    if "work_on_objective" not in existing_actions:
                        candidates.append({
                            "action": "work_on_objective",
                            "source": "exploration",
                            "reason": "Explore long-term objectives",
                            "priority_score": 2,
                            "can_auto_execute": True,
                            "metadata": {"exploratory": True},
                        })
                        existing_actions.add(action)
                elif action == "harvest_income_report" and (self._modules or {}).get("harvest_engine"):
                    if "harvest_income_report" not in existing_actions:
                        candidates.append({
                            "action": "harvest_income_report",
                            "source": "exploration",
                            "reason": "Harvest income snapshot (exploratory)",
                            "priority_score": 2,
                            "can_auto_execute": True,
                            "metadata": {"exploratory": True},
                        })
                        existing_actions.add(action)
                elif action == "income_modules_pulse":
                    m = self._modules or {}
                    if m.get("income_generator") or m.get("wallet") or m.get("financial_manager"):
                        if "income_modules_pulse" not in existing_actions:
                            now_ts = time.time()
                            refresh_sec = 1800
                            last_sig = getattr(self, "_income_modules_last_sig", None)
                            last_ts = getattr(self, "_income_modules_last_pulse_ts", 0.0) or 0.0
                            all_zero = False
                            sig = None
                            try:
                                ig = m.get("income_generator")
                                wallet = m.get("wallet")
                                fm = m.get("financial_manager")
                                earned = 0.0
                                active = 0
                                wallet_total = 0.0
                                elysia_acct = 0.0
                                cash = 0.0
                                if ig and hasattr(ig, "get_income_summary"):
                                    s = ig.get_income_summary()
                                    if isinstance(s, dict):
                                        earned = float(s.get("total_earned", 0) or 0)
                                        active = int(s.get("active_projects", 0) or 0)
                                if wallet and hasattr(wallet, "get_balance"):
                                    b = wallet.get_balance()
                                    if isinstance(b, dict):
                                        wallet_total = float(b.get("total_balance", b.get("available_balance", 0) or 0) or 0)
                                        if hasattr(wallet, "wallet") and isinstance(getattr(wallet, "wallet", None), dict):
                                            try:
                                                accs = wallet.wallet.get("accounts") or {}
                                                ely = accs.get("elysia_autonomy") if isinstance(accs, dict) else {}
                                                if isinstance(ely, dict):
                                                    elysia_acct = float(ely.get("balance", 0) or 0)
                                            except Exception:
                                                pass
                                if fm and hasattr(fm, "get_financial_status"):
                                    st = fm.get_financial_status()
                                    if isinstance(st, dict):
                                        cash = float(st.get("cash_balance", st.get("balance", 0) or 0) or 0)
                                all_zero = (earned == 0.0 and wallet_total == 0.0 and elysia_acct == 0.0 and cash == 0.0)
                                sig = f"{earned:.2f}:{active}:{wallet_total:.2f}:{elysia_acct:.2f}:{cash:.2f}"
                            except Exception:
                                sig = None
                                all_zero = False

                            if sig is not None and last_sig is not None and sig == last_sig and all_zero and (now_ts - last_ts) < refresh_sec:
                                logger.debug("[Adversarial] Suppressing income_modules_pulse expansion (unchanged all-zero; %.0fs remaining)",
                                             refresh_sec - (now_ts - last_ts))
                            else:
                                candidates.append({
                                    "action": "income_modules_pulse",
                                    "source": "exploration",
                                    "reason": "Income modules status (exploratory)",
                                    "priority_score": 2,
                                    "can_auto_execute": True,
                                    "metadata": {"exploratory": True},
                                })
                                existing_actions.add(action)
                elif action == "tool_registry_pulse" and (self._modules or {}).get("tool_registry"):
                    tr_e = (self._modules or {}).get("tool_registry")
                    if tr_e and hasattr(tr_e, "ensure_minimal_builtin_tools"):
                        try:
                            tr_e.ensure_minimal_builtin_tools()
                        except Exception:
                            pass
                    if (
                        "tool_registry_pulse" not in existing_actions
                        and tr_e
                        and self._tool_registry_minimal_capabilities_ok(tr_e)
                    ):
                        now_ts = time.time()
                        refresh_sec = 1800
                        last_sig = getattr(self, "_tool_registry_last_sig", None)
                        last_ts = getattr(self, "_tool_registry_last_pulse_ts", 0.0) or 0.0
                        cd_until = float(getattr(self, "_tool_registry_pulse_cooldown_until", 0.0) or 0.0)
                        if cd_until > now_ts:
                            logger.debug(
                                "[Exploration] Skipping tool_registry_pulse expansion (cooldown %.0fs remaining)",
                                cd_until - now_ts,
                            )
                        else:
                            sig = None
                            try:
                                router = (self._modules or {}).get("task_router")
                                tools_n, _, _ = self._tool_registry_pulse_metrics(tr_e)
                                route_to = None
                                if tools_n > 0 and router and hasattr(router, "route_task"):
                                    r = self._invoke_task_router_probe(router)
                                    if isinstance(r, dict):
                                        route_to = r.get("routed_to")
                                sig = f"{tools_n}:{route_to}"
                            except Exception:
                                sig = None

                            if sig is not None and last_sig is not None and sig == last_sig and (now_ts - last_ts) < refresh_sec:
                                logger.debug("[Adversarial] Suppressing tool_registry_pulse expansion (unchanged; %.0fs remaining)",
                                             refresh_sec - (now_ts - last_ts))
                            else:
                                candidates.append({
                                    "action": "tool_registry_pulse",
                                    "source": "exploration",
                                    "reason": "Tool registry snapshot (exploratory)",
                                    "priority_score": 2,
                                    "can_auto_execute": True,
                                    "metadata": {"exploratory": True},
                                })
                                existing_actions.add(action)
        if len(candidates) < min_cands:
            logger.info("[Exploration] Candidate expansion: %d -> target %d", len(candidates), min_cands)
        # execute_task cooldown: exclude from candidate pool while timer active (any last action)
        try:
            cooldown_min = decider_cfg.get("mistral_execute_task_cooldown_minutes", 0)
            if cooldown_min > 0:
                last_sel = getattr(self, "_last_execute_task_selected_at", None)
                rem = 0.0
                if last_sel:
                    try:
                        elapsed = (datetime.datetime.now() - last_sel).total_seconds()
                        lim = cooldown_min * 60
                        if elapsed < lim:
                            rem = lim - elapsed
                    except Exception:
                        pass
                if rem > 0:
                    _kept: List[Dict[str, Any]] = []
                    for c in candidates:
                        if c.get("action") != "execute_task":
                            _kept.append(c)
                            continue
                        if float(c.get("priority_score", 0) or 0) >= 9.0:
                            _kept.append(c)
                            continue
                        logger.info(
                            "[AutonomyNoop] Pre-selection excluded execute_task (cooldown %.0fs remaining; score<9)",
                            rem,
                        )
                    if _kept:
                        candidates = _kept
        except Exception:
            pass

        # Apply adversarial finding influence: boost/reduce priorities
        try:
            findings = get_recent_findings(self, unresolved_only=True)
            for c in candidates:
                boost = get_finding_priority_boost(c.get("action", ""), findings)
                c["priority_score"] = c.get("priority_score", 0) + boost
                c["_adversarial_boost"] = boost
        except Exception as e:
            logger.debug("Adversarial priority influence: %s", e)

        # Apply stronger execution policy: suppress, gate (enforced), bias
        try:
            policy = get_execution_policy_effect(self)
            candidates, gated_out = apply_execution_policy_to_candidates(
                candidates, policy, log_fn=lambda msg: logger.info("[Adversarial] %s", msg)
            )
            bias_toward = policy.get("bias_toward", [])
            for c in candidates:
                if c.get("action") in bias_toward:
                    c["priority_score"] = c.get("priority_score", 0) + 3.0
                    c["_policy_bias"] = True
        except Exception as e:
            logger.debug("Adversarial execution policy: %s", e)

        try:
            from .planner_readiness import (
                autonomy_noop_suppression_factor,
                boost_alternatives_when_autonomy_noop_suppressed,
                boot_low_value_action_factor,
                harvest_zero_yield_priority_factor,
            )

            for c in candidates:
                fac = autonomy_noop_suppression_factor(str(c.get("action") or ""))
                if fac < 1.0:
                    c["priority_score"] = float(c.get("priority_score", 0) or 0) * fac
                    c["_autonomy_noop_penalty"] = True
            for c in candidates:
                hz = harvest_zero_yield_priority_factor(str(c.get("action") or ""))
                if hz < 1.0:
                    c["priority_score"] = float(c.get("priority_score", 0) or 0) * hz
                    c["_harvest_zero_yield_penalty"] = True
            for c in candidates:
                bf = boot_low_value_action_factor(str(c.get("action") or ""))
                if bf < 1.0:
                    c["priority_score"] = float(c.get("priority_score", 0) or 0) * bf
                    c["_boot_low_value_penalty"] = True
            boost_alternatives_when_autonomy_noop_suppressed(
                candidates,
                list(decider_cfg.get("mistral_exploratory_actions", []) or []),
            )
        except Exception as e:
            logger.debug("autonomy noop suppression: %s", e)

        # Stagnation / memory-block: after 2+ consecutive memory-centric actions, block for 2 cycles
        try:
            from .monitoring import _load_memory_pressure_config
            cfg = _load_memory_pressure_config()
            block_cycles = cfg.get("memory_search_no_novelty_block_cycles", 2)
            force_after = cfg.get("stagnation_force_non_memory_after_cycles", 3)
            memory_actions = {"consider_learning", "consider_dream_cycle"}
            last = getattr(self, "_last_returned_action", None)
            consec = getattr(self, "_consecutive_memory_actions", 0)
            block_remaining = getattr(self, "_memory_block_cycles_remaining", 0)
            stagnation = getattr(self, "_stagnation_cycles", 0)

            if last in memory_actions:
                consec += 1
            else:
                consec = 0
            self._consecutive_memory_actions = consec

            if block_remaining > 0:
                self._memory_block_cycles_remaining = block_remaining - 1
                candidates = [c for c in candidates if c.get("action") not in memory_actions]
                if not any(c.get("action") in ("consider_prompt_evolution", "process_queue", "work_on_objective", "continue_mission") for c in candidates):
                    stagnation += 1
                else:
                    stagnation = 0
            elif consec >= 2:
                self._memory_block_cycles_remaining = block_cycles
                candidates = [c for c in candidates if c.get("action") not in memory_actions]
                logger.info("[Stagnation] Blocking memory actions for %d cycles (consecutive=%d)", block_cycles, consec)
            elif stagnation >= force_after:
                non_memory = [c for c in candidates if c.get("action") not in memory_actions]
                if non_memory:
                    candidates = non_memory
                    for c in candidates:
                        c["priority_score"] = c.get("priority_score", 0) + 2.0
                stagnation = 0
                self._stagnation_cycles = 0
            else:
                stagnation = min(stagnation + 1, force_after + 1) if not candidates else 0
            self._stagnation_cycles = stagnation
        except Exception as e:
            logger.debug("Stagnation logic: %s", e)

        # Novelty pressure: if last 3 actions same or low-value, boost underused and penalize repeated
        try:
            recent = getattr(self, "_decider_recent_actions", [])[-5:]
            last_act = getattr(self, "_last_returned_action", None)
            if last_act:
                recent = (recent + [last_act])[-5:]
            same_threshold = decider_cfg.get("mistral_novelty_same_action_threshold", 3)
            if len(recent) >= same_threshold:
                from collections import Counter
                counts = Counter(recent)
                most_common = counts.most_common(1)[0] if counts else (None, 0)
                if most_common[1] >= same_threshold:
                    repeated_action = most_common[0]
                    used = getattr(self, "_module_last_invoked", {}) or {}
                    action_to_mod = {"consider_learning": "learning", "consider_dream_cycle": "dreams", "execute_task": "tasks",
                                     "consider_adversarial_learning": "adversarial_self_learning", "consider_prompt_evolution": "prompt_evolver"}
                    for c in candidates:
                        act = c.get("action")
                        mod = action_to_mod.get(act, act)
                        if act == repeated_action:
                            c["priority_score"] = c.get("priority_score", 0) - 4.0
                        elif not used.get(mod):
                            c["priority_score"] = c.get("priority_score", 0) + 3.0
                            c["_novelty_boost"] = True
                    logger.info(
                        "[Novelty] Priority decay/boost: penalized %s by -4.0; boosted underused modules (same action %d of last %d)",
                        repeated_action, most_common[1], len(recent),
                    )
        except Exception as e:
            logger.debug("Novelty pressure: %s", e)

        # Stagnation/exploration enforcement: restrict to exploratory modules when repetition detected
        try:
            exploratory_set = set(decider_cfg.get("mistral_exploratory_actions", []))
            max_repeated = decider_cfg.get("mistral_max_repeated_action_count", 2)
            stagnation_threshold = decider_cfg.get("mistral_force_exploration_stagnation_cycles", 2)
            rep_count = getattr(self, "_mistral_repeated_action_count", 0)
            last_act = getattr(self, "_last_returned_action", None)
            force_exploratory = (
                (rep_count >= max_repeated or getattr(self, "_stagnation_cycles", 0) >= stagnation_threshold)
                and exploratory_set
            )
            if force_exploratory:
                explor_candidates = [c for c in candidates if c.get("action") in exploratory_set]
                if explor_candidates:
                    candidates = explor_candidates
                    for c in candidates:
                        c["priority_score"] = c.get("priority_score", 0) + 5.0
                    logger.info("[Exploration] Forced exploratory only: %d candidates (rep=%d stagnation=%d) actions=%s",
                                len(candidates), rep_count, getattr(self, "_stagnation_cycles", 0),
                                [c.get("action") for c in candidates])
                else:
                    logger.warning("[Exploration] Forced exploratory but no exploratory candidates in pool (rep=%d)",
                                   rep_count)
        except Exception as e:
            logger.debug("Exploration enforcement: %s", e)

        # Mission Director: campaign-aware scoring + anti-drift (novelty/exploration already applied above)
        try:
            recent_ma = list(getattr(self, "_decider_recent_actions", []) or [])
            last_ma = getattr(self, "_last_returned_action", None)
            if last_ma:
                recent_ma = (recent_ma + [str(last_ma)])[-12:]
            candidates = self.missions.apply_mission_governance(candidates, recent_ma)
        except Exception as e:
            logger.debug("Mission governance: %s", e)

        # Pre-decision: refresh API budget cycle, rank capabilities vs task, boost matching candidates
        self._pre_decision_context = {}
        try:
            max_api = int(decider_cfg.get("max_api_calls_per_decision_cycle", 2))
            self._orchestration_registry.begin_decision_cycle(max_api_calls=max_api)
            cap_snap = self._orchestration_registry.refresh_if_due(
                self, min_interval_sec=float(decider_cfg.get("orchestration_refresh_min_sec", 45))
            )
            task_ctx = self._build_capability_task_context()
            mem_hints = self._memory_capability_hints(task_ctx)
            task_for_rank = task_ctx
            if mem_hints:
                task_for_rank = (task_ctx + " | " + " ".join(mem_hints[:6]))[:1200]
            ranked = self._orchestration_registry.get_relevant_capabilities(
                task_for_rank, self, snapshot=cap_snap, top_k=14
            )
            self._orchestration_registry.boost_candidates_for_relevance(
                candidates, ranked, guardian=self
            )
            self._orchestration_registry.append_dynamic_capability_candidates(
                candidates,
                ranked,
                self,
                decider_cfg,
                max_n=int(decider_cfg.get("orchestration_dynamic_capability_max", 6)),
            )
            slim = []
            for r in ranked[:12]:
                slim.append(
                    {
                        "name": r.get("name"),
                        "type": r.get("type"),
                        "description": (r.get("description") or "")[:200],
                        "health": r.get("health"),
                        "suggested_action": r.get("suggested_action"),
                        "match_score": r.get("match_score"),
                        "success_rate": r.get("success_rate"),
                    }
                )
            self._pre_decision_context = {
                "task_context": task_ctx,
                "relevant_capabilities": slim,
                "memory_recall_lines": mem_hints,
            }
            logger.info(
                "[Orchestration] Pre-decision caps (top 5): %s",
                [f"{x.get('name')}:{x.get('match_score')}" for x in slim[:5]],
            )
        except Exception as e:
            logger.debug("Pre-decision capability pass: %s", e)

        # Only offer actions that can actually run (wired plugins + core dependencies)
        try:
            if decider_cfg.get("orchestration_require_executable_candidates", True):
                reg = self._orchestration_registry
                executable_only = [
                    c for c in candidates
                    if reg.action_is_executable(c.get("action") or "", self)
                ]
                if len(executable_only) >= 1:
                    candidates = executable_only
        except Exception as e:
            logger.debug("executable candidate filter: %s", e)

        # Pick next action: Mistral primary decider (when enabled) or deterministic highest-priority
        # Mistral-owned: routing choice. Python governor overrides when hard rules violated.
        cfg = self._load_autonomy_config()
        decider_cfg = self._load_mistral_decider_config()
        use_mistral = decider_cfg.get("mistral_primary_decider_enabled", False) or cfg.get("use_mistral_decision_engine", False)
        best = None
        override_reason = None
        mistral_ask_user = None
        mistral_decision: Optional[Dict[str, Any]] = None

        planner_runtime_out: Dict[str, Any] = {}
        if use_mistral and candidates:
            try:
                self._mistral_decision_cycle += 1
                self._mistral_decay_outcome_boosts(decider_cfg)
                candidates_backup = [dict(c) for c in candidates]
                candidates = self._mistral_strip_dream_if_pressure(candidates, decider_cfg)
                self._mistral_apply_adversarial_priority_penalty(candidates)
                self._mistral_apply_outcome_boosts(candidates, decider_cfg)
                candidates, removed_penalty = self._mistral_apply_penalty_filters(candidates, decider_cfg)
                if removed_penalty:
                    logger.info("[Mistral] Penalty filter removed: %s", ", ".join(removed_penalty))
                if not candidates:
                    logger.warning("[Mistral] Penalty filters emptied pool; using pre-filter candidate backup")
                    candidates = candidates_backup
                if candidates:
                    snapshot = self._build_decider_state_snapshot(candidates)
                    from .planner_readiness import pick_degraded_autonomy_candidate, planner_context_for_snapshot

                    planner_runtime_out = planner_context_for_snapshot(self._mistral_decision_cycle)
                    snapshot["planner_runtime"] = planner_runtime_out
                    self._last_decider_snapshot = snapshot
                    self._decider_recent_actions = snapshot.get("recent_actions", [])
                    allow_pl = bool(planner_runtime_out.get("planner_gate_allow_mistral"))
                    skip_reason = str(planner_runtime_out.get("planner_gate_reason") or "")
                    autonomy_mode = str(planner_runtime_out.get("autonomy_planner_mode") or "")
                    if not allow_pl:
                        logger.info(
                            "[Autonomy] Planner gated (%s) mode=%s readiness=%s — bounded autonomy path",
                            skip_reason or "n/a",
                            autonomy_mode,
                            planner_runtime_out.get("planner_readiness"),
                        )
                        degraded_pick = pick_degraded_autonomy_candidate(candidates)
                        if degraded_pick is not None:
                            best = dict(degraded_pick)
                            best["_mistral_source"] = "degraded_autonomy"
                            best["_mistral_reason"] = skip_reason or autonomy_mode
                        else:
                            best = max(candidates, key=lambda c: c.get("priority_score", 0))
                            best = dict(best)
                            best["_mistral_source"] = "degraded_autonomy"
                            best["_mistral_reason"] = skip_reason or "planner_gated_deterministic"
                        mistral_decision = None
                    else:
                        logger.info("[Mistral] Decision requested (candidates=%d)", len(candidates))
                        from .mistral_engine import MistralEngine
                        from .ollama_model_config import get_canonical_ollama_model

                        model = get_canonical_ollama_model(log_once=True)
                        if not hasattr(self, "_mistral_engine") or getattr(self, "_mistral_engine_model", None) != model:
                            self._mistral_engine = MistralEngine(model=model)
                            self._mistral_engine_model = model
                        gov_hints: List[str] = []
                        if getattr(self, "_mistral_consecutive_override_count", 0) >= 2:
                            gov_hints.append("low_confidence_local")
                        _stag_thr = int(decider_cfg.get("mistral_force_exploration_stagnation_cycles", 2))
                        if int(snapshot.get("stagnation_count", 0) or 0) >= _stag_thr:
                            gov_hints.append("repeated_low_value_local")
                        mistral_decision = self._mistral_engine.decide_next_action(
                            snapshot,
                            governance_hints=gov_hints,
                            module_name="planner",
                            agent_name="orchestrator",
                        )
                        try:
                            _el = float(decider_cfg.get("mistral_extreme_low_confidence_threshold", 0.2))
                            if float(mistral_decision.get("confidence", 1.0) or 0.0) < _el:
                                self._enqueue_extreme_low_confidence_fallback_tasks()
                        except Exception as _e_el:
                            logger.debug("extreme low confidence enqueue: %s", _e_el)
                        mistral_ask_user = mistral_decision.get("ask_user_question", "").strip() or None
                        _pr = (mistral_decision.get("pre_recon_summary") or "").strip()
                        _cr = (mistral_decision.get("capability_route") or "").strip()
                        logger.info(
                            "[Mistral] Decision received: action=%s confidence=%.2f needs_memory=%s route=%s recon=%s",
                            mistral_decision.get("chosen_action"),
                            mistral_decision.get("confidence", 0),
                            mistral_decision.get("needs_memory", False),
                            _cr or "-",
                            (_pr[:160] + "…") if len(_pr) > 160 else (_pr or "-"),
                        )
                        best, override_reason = self._apply_governor_to_mistral(mistral_decision, candidates, decider_cfg)
                        intended = mistral_decision.get("chosen_action", "")
                        _final = (best or {}).get("action", "")
                        logger.info(
                            "[Mistral] Route: cycle=%d intended=%s final=%s override=%s candidates=%d",
                            self._mistral_decision_cycle,
                            intended or "-",
                            _final or "-",
                            override_reason or "none",
                            len(candidates),
                        )
                        if override_reason:
                            logger.info("[Mistral] Decision overridden: %s", override_reason)
                            if override_reason != "low_confidence_force_capability":
                                self._mistral_record_override(intended, override_reason, decider_cfg)
                                self._mistral_consecutive_override_count += 1
                                self._last_get_next_had_override = True
                            else:
                                self._mistral_consecutive_override_count = 0
                                self._last_get_next_had_override = False
                            best = best or max(candidates, key=lambda c: c.get("priority_score", 0))
                            if best:
                                best = dict(best)
                        else:
                            self._mistral_consecutive_override_count = 0
                            self._last_get_next_had_override = False
                            if best:
                                best = dict(best)
                                best["_mistral_source"] = "mistral"
                                best["_mistral_reason"] = mistral_decision.get("reasoning", best.get("reason", ""))
            except Exception as e:
                logger.debug("[Mistral] Fallback to deterministic: %s", e)

        if best is None and candidates:
            best = max(candidates, key=lambda c: c.get("priority_score", 0))
            if use_mistral and mistral_decision is not None:
                logger.info("[Mistral] Deterministic fallback used")

        try:
            candidates, best = self._self_tasking_augment_decision(
                candidates,
                best,
                mistral_decision,
                override_reason,
                decider_cfg,
                use_mistral,
            )
        except Exception as e:
            logger.debug("self_tasking augment: %s", e)

        if best is None and candidates:
            best = max(candidates, key=lambda c: c.get("priority_score", 0))

        if best:
            self._last_returned_action = best["action"]
            if best["action"] == "execute_task":
                self._last_execute_task_selected_at = datetime.datetime.now()
            try:
                from .mission_autonomy import log_selected_action

                _mg = best.get("_mission_governance") if isinstance(best.get("_mission_governance"), dict) else None
                log_selected_action(
                    best["action"],
                    str(best.get("_mistral_reason") or best.get("reason") or ""),
                    mission_meta=(
                        {
                            "score_delta": _mg.get("score_delta"),
                            "drift_delta": _mg.get("drift_delta"),
                        }
                        if _mg
                        else None
                    ),
                )
            except Exception as _e_ms:
                logger.debug("MissionDirector log_selected: %s", _e_ms)
            out = {
                "success": True,
                "action": best["action"],
                "source": best.get("_mistral_source", best["source"]),
                "reason": best.get("_mistral_reason", best["reason"]),
                "priority_score": best.get("priority_score", 0),
                "can_auto_execute": best.get("can_auto_execute", False),
                "candidates": candidates,
                "candidates_count": len(candidates),
            }
            if mistral_ask_user:
                out["ask_user_question"] = mistral_ask_user
            if override_reason:
                out["override_reason"] = override_reason
            if mistral_decision and (
                mistral_decision.get("pre_recon_summary") or mistral_decision.get("capability_route")
            ):
                out["mistral_orchestration"] = {
                    "pre_recon_summary": (mistral_decision.get("pre_recon_summary") or "")[:400],
                    "capability_route": (mistral_decision.get("capability_route") or "")[:80],
                }
            if best.get("metadata") is not None:
                out["metadata"] = best.get("metadata")
            if planner_runtime_out:
                out["planner_runtime"] = planner_runtime_out
            return out
        self._last_returned_action = "continue_monitoring"
        return {
            "success": True,
            "action": "continue_monitoring",
            "source": "system",
            "reason": "No pending high-priority actions",
            "priority_score": 1,
            "can_auto_execute": False,
            "candidates": [],
            "candidates_count": 0,
        }

    def _load_autonomy_config(self) -> Dict[str, Any]:
        """Load config/autonomy.json."""
        cfg_path = Path(__file__).parent.parent / "config" / "autonomy.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    cfg = json.load(f)
                    # Second-line guard: enforce sane values in-memory
                    mh = cfg.get("max_actions_per_hour")
                    if mh is None or not isinstance(mh, int) or mh < 1 or mh > 60:
                        cfg["max_actions_per_hour"] = 6
                    return cfg
            except Exception:
                pass
        return {
            "enabled": True,
            "interval_seconds": 120,
            "use_mistral_decision_engine": False,
            "allowed_actions": ["consider_learning", "consider_dream_cycle", "consider_prompt_evolution", "consider_adversarial_learning", "rebuild_vector"],
            "max_actions_per_hour": 0,
        }

    def _load_mistral_decider_config(self) -> Dict[str, Any]:
        """Load config/mistral_decider.json. Governor uses these for override rules."""
        cfg_path = Path(__file__).parent.parent / "config" / "mistral_decider.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "mistral_primary_decider_enabled": False,
            "mistral_decider_model": "mistral:7b",
            "mistral_decision_confidence_threshold": 0.5,
            "mistral_override_on_memory_pressure": True,
            "mistral_override_on_needs_memory_false": True,
            "mistral_force_exploration_after_stagnation": True,
            "mistral_max_repeated_action_count": 2,
            "mistral_skip_auto_execute_when_ask_user": True,
            "mistral_exploratory_actions": [
                "fractalmind_planning", "question_probe", "code_analysis", "consider_prompt_evolution", "work_on_objective", "consider_mutation",
                "harvest_income_report", "income_modules_pulse", "tool_registry_pulse",
            ],
            "mistral_min_candidates": 5,
            "mistral_novelty_same_action_threshold": 3,
            "mistral_execute_task_cooldown_minutes": 15,
            "mistral_force_exploration_stagnation_cycles": 2,
            "mistral_extreme_low_confidence_threshold": 0.2,
        }

    def _enqueue_extreme_low_confidence_fallback_tasks(self) -> None:
        """When Mistral confidence is extremely low, enqueue bounded operator tasks (not task_router)."""
        from .self_task_generator import enqueue_generated, new_task_dict
        from .self_task_queue import SelfTaskQueue

        st_cfg = self._load_self_tasking_config()
        if not st_cfg.get("enabled", True):
            return
        slot_mark = str(int(time.time() // 3600))
        if getattr(self, "_extreme_low_fallback_hour", None) == slot_mark:
            return
        self._extreme_low_fallback_hour = slot_mark
        q = SelfTaskQueue(max_size=int(st_cfg.get("max_queue_size", 24)))
        cooldown = float(st_cfg.get("dedupe_cooldown_sec", 900))
        tasks = [
            new_task_dict(
                archetype="synthesize_latest_artifacts",
                title="Synthesize latest operator artifacts",
                goal="Merge recent JSON briefs from data/generated_reports and data/revenue_briefs into one summary dict.",
                category="maintenance",
                reason="Extreme low Mistral confidence; deterministic artifact progress.",
                priority=0.78,
                recommended_capabilities=["tool:artifact_synthesizer"],
                success_criteria="Structured synthesis dict.",
                dedupe_key=f"synthesize_latest_artifacts_{slot_mark}",
            ),
            new_task_dict(
                archetype="refine_revenue_shortlist",
                title="Refine revenue shortlist from local data",
                goal="Refresh ranked opportunities from income summary and prior briefs.",
                category="finance",
                reason="Extreme low confidence; refine monetary picture.",
                priority=0.76,
                recommended_capabilities=["tool:revenue_executor"],
                success_criteria="revenue_shortlist-shaped dict.",
                dedupe_key=f"refine_revenue_shortlist_{slot_mark}",
            ),
            new_task_dict(
                archetype="rank_top_opportunities",
                title="Rank top opportunities",
                goal="Read latest revenue brief JSON if present; rank opportunities by expected value.",
                category="finance",
                reason="Order work by payoff.",
                priority=0.75,
                recommended_capabilities=["tool:opportunity_ranker"],
                success_criteria="Ranked list dict.",
                dedupe_key=f"rank_top_opportunities_{slot_mark}",
            ),
            new_task_dict(
                archetype="execute_best_opportunity",
                title="Plan execution for best opportunity",
                goal="Pick best ranked item and emit local execution plan (no outbound transactions).",
                category="finance",
                reason="Turn ideas into next actions.",
                priority=0.74,
                recommended_capabilities=["tool:revenue_executor"],
                success_criteria="Plan dict with steps.",
                dedupe_key=f"execute_best_opportunity_{slot_mark}",
            ),
        ]
        enqueue_generated(q, tasks, cooldown_sec=cooldown, guardian=self)

    def _mistral_get_memory_pressure_high(self) -> bool:
        """True when guardian memory count is at/above scaled trim target (default: full target)."""
        try:
            from .monitoring import _load_memory_pressure_config
            pressure_cfg = _load_memory_pressure_config()
        except Exception:
            pressure_cfg = {}
        trim_target = int(pressure_cfg.get("pressure_trim_target", 1600))
        frac = float(pressure_cfg.get("memory_pressure_trigger_fraction", 1.0))
        frac = max(0.5, min(1.0, frac))
        trigger = max(1, int(trim_target * frac))
        memory_count = None
        if hasattr(self, "memory") and self.memory:
            mc = self.memory.get_memory_count(load_if_needed=False)
            if mc is not None:
                memory_count = mc
        return memory_count is not None and memory_count >= trigger

    def _mistral_prune_penalty_entries(self, decider_cfg: Dict[str, Any]) -> None:
        """Drop expired override-penalty entries."""
        cycle = self._mistral_decision_cycle
        now = time.time()
        pressure_high = self._mistral_get_memory_pressure_high()
        kept: List[Dict[str, Any]] = []
        for e in self._mistral_penalty_entries:
            if e.get("until_cycle") is not None and cycle > int(e["until_cycle"]):
                continue
            if e.get("until_pressure_low") and not pressure_high:
                continue
            if e.get("until_ts") is not None and now > float(e["until_ts"]):
                continue
            kept.append(e)
        self._mistral_penalty_entries = kept

    def _mistral_record_override(
        self, intended_action: str, reason: str, decider_cfg: Dict[str, Any]
    ) -> None:
        """Record governor override for penalty memory and recent history."""
        if not intended_action or not reason:
            return
        cy = self._mistral_decision_cycle
        c_need = int(decider_cfg.get("mistral_override_penalty_cycles_needs_memory_false", 4))
        c_rep = int(decider_cfg.get("mistral_override_penalty_cycles_repeated_action", 2))
        soft = float(decider_cfg.get("mistral_override_soft_penalty_score", 6.0))
        cooldown_min = int(decider_cfg.get("mistral_module_cooldown_minutes", 5))
        entry: Optional[Dict[str, Any]] = None
        if reason == "needs_memory_false":
            entry = {
                "action": intended_action,
                "reason": reason,
                "until_cycle": cy + c_need,
                "soft": True,
                "soft_penalty": soft,
            }
        elif reason == "memory_pressure":
            entry = {
                "action": intended_action,
                "reason": reason,
                "until_pressure_low": True,
                "hard": True,
            }
        elif reason == "repeated_action":
            entry = {
                "action": intended_action,
                "reason": reason,
                "until_cycle": cy + c_rep,
                "hard": True,
            }
        elif reason == "module_cooldown":
            entry = {
                "action": intended_action,
                "reason": reason,
                "until_ts": time.time() + cooldown_min * 60,
                "hard": True,
            }
        if entry:
            self._mistral_penalty_entries.append(entry)
        self._mistral_recent_overrides.append({"action": intended_action, "reason": reason, "cycle": cy})
        if len(self._mistral_recent_overrides) > 14:
            self._mistral_recent_overrides = self._mistral_recent_overrides[-14:]

    def _mistral_apply_penalty_filters(
        self, candidates: List[Dict[str, Any]], decider_cfg: Dict[str, Any]
    ) -> tuple:
        """Remove hard-blocked candidates; apply soft penalties. Returns (filtered, removed_actions)."""
        self._mistral_prune_penalty_entries(decider_cfg)
        pressure_high = self._mistral_get_memory_pressure_high()
        now = time.time()
        cy = self._mistral_decision_cycle
        out: List[Dict[str, Any]] = []
        removed: List[str] = []
        for c in candidates:
            act = c.get("action")
            if not act:
                continue
            hard_block = False
            soft_pen = 0.0
            for e in self._mistral_penalty_entries:
                if e.get("action") != act:
                    continue
                if e.get("hard"):
                    if e.get("until_pressure_low"):
                        if pressure_high:
                            hard_block = True
                    elif e.get("until_ts") is not None:
                        if now < float(e["until_ts"]):
                            hard_block = True
                    elif e.get("until_cycle") is not None:
                        if cy <= int(e["until_cycle"]):
                            hard_block = True
                elif e.get("soft") and e.get("until_cycle") is not None:
                    if cy <= int(e["until_cycle"]):
                        soft_pen += float(e.get("soft_penalty", 0))
            if hard_block:
                removed.append(f"{act}(hard)")
                logger.info(
                    "[Mistral] Candidate suppressed (prior override history): action=%s",
                    act,
                )
                continue
            nc = dict(c)
            if soft_pen > 0:
                nc["priority_score"] = nc.get("priority_score", 0) - soft_pen
                nc["_override_soft_penalty"] = soft_pen
                logger.info(
                    "[Mistral] Soft penalty from prior override: action=%s penalty=%.1f",
                    act,
                    soft_pen,
                )
            out.append(nc)
        return out, removed

    def _mistral_decay_outcome_boosts(self, decider_cfg: Dict[str, Any]) -> None:
        """Decay outcome reinforcement boosts each decision cycle."""
        for act in list(self._mistral_outcome_boost.keys()):
            rec = self._mistral_outcome_boost.get(act) or {}
            left = int(rec.get("cycles", 0)) - 1
            if left <= 0:
                del self._mistral_outcome_boost[act]
            else:
                rec["cycles"] = left
                self._mistral_outcome_boost[act] = rec

    def _mistral_apply_outcome_boosts(self, candidates: List[Dict[str, Any]], decider_cfg: Dict[str, Any]) -> None:
        """Increase priority for actions that recently succeeded after blocked routes."""
        for c in candidates:
            act = c.get("action")
            if not act:
                continue
            rec = self._mistral_outcome_boost.get(act)
            if not rec:
                continue
            bonus = float(rec.get("value", 0))
            if bonus > 0:
                c["priority_score"] = c.get("priority_score", 0) + bonus
                c["_outcome_boost"] = bonus

    def _mistral_reward_successful_action(self, action: str, decider_cfg: Dict[str, Any]) -> None:
        """Outcome-based reinforcement after a successful execute following overrides."""
        if not getattr(self, "_last_get_next_had_override", False):
            return
        if self._mistral_consecutive_override_count <= 0:
            return
        cycles = int(decider_cfg.get("mistral_success_outcome_boost_cycles", 4))
        val = float(decider_cfg.get("mistral_success_outcome_boost_value", 4.0))
        self._mistral_outcome_boost[action] = {"cycles": cycles, "value": val}
        self._last_get_next_had_override = False
        logger.info(
            "[Mistral] Outcome boost applied: action=%s +%.1f for %d cycles (after prior overrides)",
            action,
            val,
            cycles,
        )

    def _mistral_update_adversarial_gating(self, adv_result: Dict[str, Any], decider_cfg: Dict[str, Any]) -> None:
        """Penalize repeated low-yield adversarial runs (same finding, no new tasks)."""
        top = adv_result.get("top_weakness")
        top_type = adv_result.get("top_type")
        tasks_created = int(adv_result.get("tasks_created", 0) or 0)
        fc = int(adv_result.get("findings_count", 0) or 0)
        if fc == 0 and tasks_created == 0:
            return
        fp = f"{top_type}:{str(top)[:80]}" if top else ""
        if fp and fp == self._adversarial_last_fingerprint and tasks_created == 0:
            self._adversarial_low_yield_streak += 1
            per = float(decider_cfg.get("mistral_adversarial_low_yield_penalty_per_streak", 1.5))
            hard_block_streak = int(decider_cfg.get("mistral_adversarial_low_yield_hard_block_streak", 4))
            cooldown_min = float(decider_cfg.get("mistral_adversarial_low_yield_cooldown_minutes", 90))
            self._adversarial_priority_penalty = min(
                float(decider_cfg.get("mistral_adversarial_low_yield_penalty_cap", 6.0)),
                self._adversarial_priority_penalty + per,
            )

            # Strong cooldown + candidate suppression when novelty/actionability collapses.
            if self._adversarial_low_yield_streak >= hard_block_streak:
                self._adversarial_low_yield_cooldown_until = time.time() + int(cooldown_min * 60)
                logger.warning(
                    "[Mistral] Adversarial low-yield hard block: streak=%d cooldown=%.1fm finding=%s",
                    self._adversarial_low_yield_streak,
                    cooldown_min,
                    (str(top)[:60] + "...") if top and len(str(top)) > 60 else top,
                )
            logger.info(
                "[Mistral] Adversarial low-yield repeat: streak=%d priority_penalty=%.1f finding=%s",
                self._adversarial_low_yield_streak,
                self._adversarial_priority_penalty,
                (str(top)[:60] + "...") if top and len(str(top)) > 60 else top,
            )
        else:
            if tasks_created > 0 or (fp and fp != self._adversarial_last_fingerprint):
                self._adversarial_low_yield_streak = 0
                self._adversarial_priority_penalty = max(
                    0.0,
                    self._adversarial_priority_penalty - float(decider_cfg.get("mistral_adversarial_penalty_decay", 2.0)),
                )
                # Reset cooldown once we get novelty or actionable output.
                self._adversarial_low_yield_cooldown_until = None
        self._adversarial_last_fingerprint = fp or self._adversarial_last_fingerprint

    def _mistral_apply_adversarial_priority_penalty(self, candidates: List[Dict[str, Any]]) -> None:
        """Reduce priority of consider_adversarial_learning when low-yield streak is high."""
        pen = getattr(self, "_adversarial_priority_penalty", 0.0)
        if pen <= 0:
            return
        for c in candidates:
            if c.get("action") == "consider_adversarial_learning":
                c["priority_score"] = c.get("priority_score", 0) - pen
                c["_adversarial_low_yield_penalty"] = pen

    def _nonadv_penalty_module_for_action(self, action: Optional[str]) -> Optional[str]:
        if not action:
            return None
        return {
            "work_on_objective": "longterm_planner",
            "income_modules_pulse": "income_modules",
            "tool_registry_pulse": "tool_registry",
        }.get(action)

    def _apply_nonadv_penalties_to_cooldowns(self, module_cooldowns: Dict[str, Any]) -> None:
        """Inject virtual cooldown minutes for modules stuck in non-advancing success loops."""
        now_ts = time.time()
        penal = getattr(self, "_nonadv_penalty_until", None)
        if penal is None:
            self._nonadv_penalty_until = {}
            penal = self._nonadv_penalty_until
        expired_mods = []
        for mod, until in list(penal.items()):
            if now_ts < float(until):
                cur = float(module_cooldowns.get(mod, 0) or 0)
                module_cooldowns[mod] = max(cur, 48.0)
            else:
                expired_mods.append(mod)
        for m in expired_mods:
            penal.pop(m, None)

    def _finish_nonadv_tracking(self, action: Optional[str], meaningful_ok: bool, advanced: bool) -> None:
        if not meaningful_ok or not action:
            return
        mod = self._nonadv_penalty_module_for_action(action)
        if not mod:
            return
        if advanced:
            self._nonadv_action_streak[action] = 0
            self._nonadv_penalty_until.pop(mod, None)
            return
        st = int(self._nonadv_action_streak.get(action, 0) or 0) + 1
        self._nonadv_action_streak[action] = st
        if st >= 3:
            until = time.time() + 900.0
            self._nonadv_penalty_until[mod] = until
            logger.warning(
                "[NonAdv] Suppressing module=%s after %d non-advancing successes for action=%s (cooldown 900s)",
                mod,
                st,
                action,
            )

    def _mistral_strip_dream_if_pressure(self, candidates: List[Dict[str, Any]], decider_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Do not offer consider_dream_cycle when memory pressure makes it likely to be blocked."""
        if not decider_cfg.get("mistral_suppress_dream_when_memory_pressure", True):
            return candidates
        if not self._mistral_get_memory_pressure_high():
            return candidates
        out = [c for c in candidates if c.get("action") != "consider_dream_cycle"]
        if len(out) < len(candidates):
            logger.info(
                "[Mistral] Removed consider_dream_cycle from candidates (memory pressure; avoids futile selection)",
            )
        return out

    def _build_decider_state_snapshot(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build structured state for Mistral decide_next_action. Python-owned: data only."""
        decider_cfg = self._load_mistral_decider_config()
        refresh_sec = float(decider_cfg.get("orchestration_refresh_min_sec", 45))
        cap_snap: Dict[str, Any] = {}
        try:
            cap_snap = self._orchestration_registry.refresh_if_due(self, min_interval_sec=refresh_sec)
        except Exception as e:
            logger.debug("Orchestration snapshot refresh: %s", e)

        try:
            from .monitoring import _load_memory_pressure_config
            pressure_cfg = _load_memory_pressure_config()
        except Exception:
            pressure_cfg = {}
        trim_target = int(pressure_cfg.get("pressure_trim_target", 1600))
        frac = float(pressure_cfg.get("memory_pressure_trigger_fraction", 1.0))
        frac = max(0.5, min(1.0, frac))
        trigger = max(1, int(trim_target * frac))
        memory_count = None
        if hasattr(self, "memory") and self.memory:
            mem_cnt = self.memory.get_memory_count(load_if_needed=False)
            if mem_cnt is not None:
                memory_count = mem_cnt
        memory_pressure_high = memory_count is not None and memory_count >= trigger

        # Active goal from missions or LongTermPlanner
        active_goal = None
        try:
            am = self.missions.get_active_missions()
            if am:
                active_goal = am[0].get("name", "")
        except Exception:
            pass
        if not active_goal and self._modules:
            try:
                planner = self._modules.get("longterm_planner")
                if planner and hasattr(planner, "objectives"):
                    _raw = planner.objectives
                    _seq = list(_raw.values()) if isinstance(_raw, dict) else (list(_raw) if isinstance(_raw, list) else [])
                    for o in _seq:
                        st = (o or {}).get("status", "") if isinstance(o, dict) else getattr(o, "status", "")
                        if "active" in str(st).lower():
                            active_goal = (o or {}).get("name", "") if isinstance(o, dict) else getattr(o, "name", "")
                            break
            except Exception:
                pass

        # Recent actions (last 5)
        recent = getattr(self, "_decider_recent_actions", [])
        last_act = getattr(self, "_last_returned_action", None)
        if last_act:
            recent = (recent + [last_act])[-5:]

        # Recent outcomes and action feedback (for Mistral to adapt)
        outcomes = []
        last_outcome = getattr(self, "_last_action_outcome", None)
        if getattr(self, "_last_autonomy_result", None):
            r = self._last_autonomy_result
            outcomes.append(f"executed={r.get('executed')} action={r.get('action')}")
        if getattr(self, "_last_introspection_result", None):
            r = self._last_introspection_result
            outcomes.append(f"introspection suggested={r.get('suggested_action')}")

        # Module cooldowns (time since last invoke)
        module_cooldowns: Dict[str, Any] = {}
        for name, ts in (getattr(self, "_module_last_invoked", None) or {}).items():
            try:
                dt = datetime.datetime.fromisoformat(ts)
                mins = (datetime.datetime.now() - dt).total_seconds() / 60
                module_cooldowns[name] = round(mins, 1)
            except Exception:
                module_cooldowns[name] = 0

        try:
            self._apply_nonadv_penalties_to_cooldowns(module_cooldowns)
        except Exception as e:
            logger.debug("nonadv cooldown injection: %s", e)

        score_rows: List[Dict[str, Any]] = []
        try:
            _, score_rows = self._orchestration_registry.score_candidates(
                candidates, cap_snap, module_cooldowns
            )
        except Exception as e:
            logger.debug("Orchestration scoring: %s", e)

        try:
            from .capability_registry import describe_available_capabilities
            cap_digest = describe_available_capabilities(
                cap_snap,
                max_chars=int(decider_cfg.get("orchestration_digest_max_chars", 4000)),
            )
        except Exception:
            cap_digest = ""

        cap_snap_export = dict(cap_snap) if cap_snap else {}
        cap_snap_export["scored_candidates"] = score_rows

        pdc = getattr(self, "_pre_decision_context", None) or {}
        api_eval: Dict[str, Any] = {}
        try:
            from .multi_api_router import evaluate_api_vs_local

            api_eval = evaluate_api_vs_local(
                (pdc.get("task_context") or "") or (active_goal or ""),
                registry=self._orchestration_registry,
            )
        except Exception as e:
            logger.debug("api_vs_local eval: %s", e)

        orchestration_recon = {
            "A_objective": active_goal or cap_snap.get("recon_objective"),
            "B_memory_hint": (cap_snap.get("memory_recon_hint") or "")[:400],
            "C_capability_digest": cap_digest,
            "D_tools_modules": f"adapters={cap_snap.get('module_registry_count', 0)} plugins={len(cap_snap.get('plugin_module_names') or [])} tools={cap_snap.get('tool_registry_count', 0)}",
            "E_scored_actions": score_rows[:15],
            "F_relevant_capabilities": pdc.get("relevant_capabilities") or [],
            "G_memory_capability_recall": pdc.get("memory_recall_lines") or [],
            "H_api_vs_local": api_eval,
            "I_api_routing_hints": cap_snap.get("api_routing_hints") or {},
            "understanding_ready": self._orchestration_registry.understanding_ready(),
        }

        recent_overrides = list(getattr(self, "_mistral_recent_overrides", [])[-8:])
        penalty_summary = [
            {"action": e.get("action"), "reason": e.get("reason")}
            for e in getattr(self, "_mistral_penalty_entries", [])
        ]

        uncertainty_level = "low" if active_goal else "medium"
        if len(recent_overrides) >= 3:
            uncertainty_level = "high"

        return {
            "active_goal": active_goal,
            "recent_actions": recent,
            "recent_outcomes": outcomes[-3:],
            "last_action_outcome": last_outcome,
            "pending_operator_question": getattr(self, "_pending_operator_question", None),
            "memory_pressure_high": memory_pressure_high,
            "memory_count": memory_count,
            "stagnation_count": getattr(self, "_stagnation_cycles", 0),
            "memory_block_cycles_remaining": getattr(self, "_memory_block_cycles_remaining", 0),
            "consecutive_memory_actions": getattr(self, "_consecutive_memory_actions", 0),
            "candidates": candidates,
            "module_cooldowns": module_cooldowns,
            "uncertainty_level": uncertainty_level,
            "recent_governor_overrides": recent_overrides,
            "active_override_penalties": penalty_summary,
            "adversarial_priority_penalty": getattr(self, "_adversarial_priority_penalty", 0.0),
            "decision_cycle": getattr(self, "_mistral_decision_cycle", 0),
            "capability_snapshot": cap_snap_export,
            "capability_digest": cap_digest,
            "orchestration_recon": orchestration_recon,
            "pre_decision_task_context": (pdc.get("task_context") or "")[:800],
            "relevant_capabilities": pdc.get("relevant_capabilities") or [],
        }

    def _apply_governor_to_mistral(
        self,
        mistral_decision: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        decider_cfg: Dict[str, Any],
    ) -> tuple:
        """
        Governor (Python): override Mistral when hard rules are violated.
        Returns (best_candidate, override_reason). override_reason is None if Mistral choice accepted.
        """
        chosen = mistral_decision.get("chosen_action", "")
        confidence = mistral_decision.get("confidence", 0)
        needs_memory = mistral_decision.get("needs_memory", False)
        threshold = decider_cfg.get("mistral_decision_confidence_threshold", 0.5)
        extreme_low = float(decider_cfg.get("mistral_extreme_low_confidence_threshold", 0.2))
        memory_actions = {"consider_learning", "consider_dream_cycle"}
        action_to_module = {
            "consider_learning": "learning",
            "consider_dream_cycle": "dreams",
            "consider_prompt_evolution": "prompt_evolver",
            "rebuild_vector": "memory",
            "consider_adversarial_learning": "adversarial_self_learning",
            "execute_task": "tasks",
            "fractalmind_planning": "fractalmind",
            "question_probe": "exploration",
            "code_analysis": "analysis_engine",
            "consider_mutation": "mutation",
            "work_on_objective": "longterm_planner",
            "harvest_income_report": "harvest_engine",
            "income_modules_pulse": "income_modules",
            "tool_registry_pulse": "tool_registry",
            "execute_self_task": "self_tasking",
        }

        def _module_key_for_action(act: str) -> str:
            a = act or ""
            if a.startswith("use_capability/module/") and a.count("/") >= 2:
                return a.split("/", 2)[-1]
            if a.startswith("use_capability/tool/"):
                return "tool_registry"
            return action_to_module.get(a, "")

        warm = int(decider_cfg.get("orchestration_warmup_cycles", 0) or 0)
        if warm > 0:
            cy = int(getattr(self, "_mistral_decision_cycle", 0) or 0)
            if cy <= warm and chosen in ("execute_task", "work_on_objective", "consider_mutation"):
                alt = [
                    c for c in candidates
                    if c.get("action") in (
                        "code_analysis", "tool_registry_pulse", "consider_learning",
                        "fractalmind_planning", "income_modules_pulse",
                    )
                ]
                if alt:
                    return (max(alt, key=lambda x: x.get("priority_score", 0)), "orchestration_warmup")

        def _is_task_router_action(act: Optional[str]) -> bool:
            return bool(act) and "task_router" in str(act)

        # Low confidence → force a capability-style candidate (avoid idle/deterministic loops)
        if confidence < threshold:
            # Extreme low: never steer to task_router (empty tool surface loops); prefer self-tasks.
            if confidence < extreme_low:
                st_only = [c for c in candidates if c.get("action") == "execute_self_task"]
                if st_only:
                    return (
                        max(st_only, key=lambda x: x.get("priority_score", 0)),
                        "extreme_low_confidence_self_task",
                    )
            uc = [
                c
                for c in candidates
                if isinstance(c.get("action"), str) and c["action"].startswith("use_capability/")
            ]
            if confidence < extreme_low:
                uc = [c for c in uc if not _is_task_router_action(c.get("action"))]
            if uc:
                pick = max(uc, key=lambda x: x.get("priority_score", 0))
                return (dict(pick), "low_confidence_force_capability")
            cap_pool = [
                c
                for c in candidates
                if self._orchestration_registry.action_is_executable(c.get("action") or "", self)
                and str(c.get("action") or "")
                not in ("question_probe", "continue_monitoring")
            ]
            if confidence < extreme_low:
                cap_pool = [c for c in cap_pool if not _is_task_router_action(c.get("action"))]
            if cap_pool:
                pick = max(cap_pool, key=lambda x: x.get("priority_score", 0))
                return (dict(pick), "low_confidence_force_capability")
            return (None, "low_confidence")

        # Invalid or empty choice
        valid_actions = {c.get("action") for c in candidates if c.get("action")}
        if chosen not in valid_actions:
            return (None, "invalid_action")

        best = next((c for c in candidates if c.get("action") == chosen), None)
        if not best:
            return (None, "candidate_not_found")

        if decider_cfg.get("orchestration_require_executable_candidates", True):
            if not self._orchestration_registry.action_is_executable(chosen, self):
                alt = [
                    c for c in candidates
                    if self._orchestration_registry.action_is_executable(c.get("action") or "", self)
                ]
                if alt:
                    return (max(alt, key=lambda x: x.get("priority_score", 0)), "chosen_not_executable_runtime")
                return (None, "no_executable_actions")

        # Memory pressure override (block memory-heavy actions; optionally allow consider_learning)
        if decider_cfg.get("mistral_override_on_memory_pressure", True):
            snapshot = getattr(self, "_last_decider_snapshot", {}) or {}
            if snapshot.get("memory_pressure_high") and chosen in memory_actions:
                allow_learning = decider_cfg.get("mistral_allow_consider_learning_under_pressure", True)
                if chosen == "consider_learning" and allow_learning:
                    # consider_learning has strict admission; unlikely to add many memories
                    pass
                else:
                    non_mem = [c for c in candidates if c.get("action") not in memory_actions]
                    if non_mem:
                        fallback = max(non_mem, key=lambda x: x.get("priority_score", 0))
                        return (fallback, "memory_pressure")

        # needs_memory=false but Mistral chose memory -> override (avoid memory reflex).
        # Set mistral_override_on_needs_memory_false: false to give Mistral full control.
        if decider_cfg.get("mistral_override_on_needs_memory_false", True) and not needs_memory and chosen in memory_actions:
            non_mem = [c for c in candidates if c.get("action") not in memory_actions]
            if non_mem:
                fallback = max(non_mem, key=lambda x: x.get("priority_score", 0))
                return (fallback, "needs_memory_false")

        # Repeated action -> force exploration
        max_repeated = decider_cfg.get("mistral_max_repeated_action_count", 3)
        last_act = getattr(self, "_last_returned_action", None)
        rep_count = getattr(self, "_mistral_repeated_action_count", 0)
        if last_act == chosen:
            rep_count = rep_count + 1
        else:
            rep_count = 1
        self._mistral_repeated_action_count = rep_count
        if decider_cfg.get("mistral_force_exploration_after_stagnation", True) and rep_count >= max_repeated:
            others = [c for c in candidates if c.get("action") != chosen]
            if others:
                # Prefer underused modules; exploration_score from Mistral biases toward novelty
                used = getattr(self, "_module_last_invoked", {}) or {}
                expl_bias = decider_cfg.get("mistral_exploration_score_bias", 0.3)
                expl_score = mistral_decision.get("exploration_score", 0.5)

                def _fallback_score(c):
                    mod = _module_key_for_action(c.get("action") or "")
                    ts = used.get(mod, "")
                    base = c.get("priority_score", 0)
                    if not ts:  # underused
                        base += expl_score * expl_bias
                    return (-base, (ts or "")[:1])

                others.sort(key=_fallback_score)
                fallback = others[0]
                self._mistral_repeated_action_count = 0
                return (fallback, "repeated_action")

        # Module cooldown (configurable minutes between same module)
        cooldown_min = decider_cfg.get("mistral_module_cooldown_minutes", 5)
        mod = _module_key_for_action(chosen)
        invoked = (getattr(self, "_module_last_invoked", None) or {}).get(mod, "")
        if invoked:
            try:
                dt = datetime.datetime.fromisoformat(invoked)
                if (datetime.datetime.now() - dt).total_seconds() < cooldown_min * 60:
                    others = [c for c in candidates if _module_key_for_action(c.get("action") or "") != mod]
                    if others:
                        return (max(others, key=lambda x: x.get("priority_score", 0)), "module_cooldown")
            except Exception:
                pass

        return (best, None)

    def _orchestration_log_cycle(
        self,
        action: Optional[str],
        success: bool,
        latency_ms: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            self._orchestration_registry.log_outcome(
                action=action or "unknown",
                success=success,
                latency_ms=latency_ms,
                extra=extra,
            )
        except Exception:
            pass
        try:
            pdc = getattr(self, "_pre_decision_context", None) or {}
            q = 0.85 if success else 0.25
            if extra and extra.get("reason") == "no_handler_for_action":
                q = 0.35
            self._orchestration_registry.log_capability_usage(
                task=(pdc.get("task_context") or "")[:500],
                capability_id=action or "unknown",
                capability_type="autonomy_action",
                success=success,
                quality=q,
                latency_ms=latency_ms,
                extra=extra,
            )
        except Exception:
            pass

    def _load_self_tasking_config(self) -> Dict[str, Any]:
        p = Path(__file__).resolve().parent.parent / "config" / "self_tasking.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "enabled": True,
            "max_queue_size": 24,
            "stale_ttl_sec": 7200,
            "expire_max_priority": 0.35,
            "max_generate_per_cycle": 5,
            "dedupe_cooldown_sec": 900,
            "prefer_over_priority_below": 5.5,
            "underuse_module_hours": 2.0,
            "followup_max_retries_per_archetype": 2,
            "operator_value_priority_boost": 0.42,
            "blocking_maintenance_priority_boost": 0.55,
            "max_operator_value_tasks_per_cycle": 4,
        }

    @staticmethod
    def _self_task_payload_useful(res: Any) -> bool:
        if res is None:
            return False
        if isinstance(res, dict):
            if len(res) == 0:
                return False
            if set(res.keys()) <= {"routed_to"}:
                return False
            return True
        return len(str(res).strip()) > 24

    @staticmethod
    def _self_task_structured_output(res: Any) -> bool:
        if res is None:
            return False
        if isinstance(res, dict):
            if len(res) == 0:
                return False
            if set(res.keys()) <= {"routed_to"}:
                return False
            return True
        if isinstance(res, list):
            return len(res) > 0
        return len(str(res).strip()) > 24

    def _self_task_has_strong_signals(
        self,
        *,
        useful_payload: bool,
        memory_written: bool,
        last_result: Any,
        capability_ok: bool,
    ) -> bool:
        if useful_payload:
            return True
        if memory_written:
            return True
        if self._self_task_structured_output(last_result):
            return True
        if capability_ok and self._self_task_payload_useful(last_result):
            return True
        return False

    def _run_self_generated_task(
        self,
        task_id: str,
        t0: float,
        cycle_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, bool, str]:
        from .self_task_queue import SelfTaskQueue
        from .capability_execution import execute_capability_kind
        from .self_task_objectives import ObjectiveStore
        from .self_task_followups import maybe_enqueue_followups, maybe_enqueue_execution_outcome_followups
        from .self_task_output_contracts import (
            contract_id_for_archetype,
            normalize_payload,
            validate_contract,
        )
        from .self_task_artifacts import save_self_task_artifact
        from .self_task_advancement import evaluate_task_advancement, merge_best_artifact
        from .self_task_execution_outcome import (
            evaluate_execution_outcome,
            is_execution_stage_archetype,
        )
        from .self_task_value_verification import evaluate_execution_value
        from .self_task_cycle_priority import evaluate_cycle_priority_choice

        st_cfg = self._load_self_tasking_config()
        q = SelfTaskQueue(max_size=int(st_cfg.get("max_queue_size", 24)))
        obj_store = ObjectiveStore()
        q.release_stale_in_progress(max_sec=1800)
        task = q.claim(task_id)
        if not task:
            return False, False, "claim_failed"
        useful_any = False
        ok_any = False
        memory_written = False
        last_result: Any = None
        capability_ok = False
        capability_attempted = False
        last_capability_ex: Optional[Dict[str, Any]] = None
        detail_parts: List[str] = []
        arch = str(task.get("archetype") or "")
        learning_digest_archs = (
            "learning_recent_digest",
            "summarize_recent_learning_operator",
            "learning_operator_digest",
        )

        try:
            if arch in learning_digest_archs and getattr(self, "memory", None):
                try:
                    lines: List[str] = []
                    if hasattr(self.memory, "recall_last"):
                        for row in (self.memory.recall_last(8) or [])[:8]:
                            if isinstance(row, dict):
                                lines.append(str(row.get("thought", ""))[:120])
                            else:
                                lines.append(str(row)[:120])
                    summary = "; ".join(x for x in lines if x).strip()
                    insights = [x.strip() for x in summary.split(";") if x.strip()][:8]
                    if len(insights) >= 1:
                        self.memory.remember(
                            f"[SelfTask] Learning digest: {summary[:400]}",
                            category="autonomy",
                            priority=0.45,
                        )
                        memory_written = True
                        last_result = {
                            "top_insights": insights[:5],
                            "why_they_matter": "Themes from recent autonomy memory consolidate into operator-actionable guidance.",
                            "recommended_followup_tasks": [
                                "generate_revenue_shortlist",
                                "identify_capability_gaps",
                            ],
                        }
                        useful_any = True
                        ok_any = True
                        detail_parts.append("memory_digest_structured")
                    elif len(summary) > 20:
                        self.memory.remember(
                            f"[SelfTask] Learning digest: {summary[:400]}",
                            category="autonomy",
                            priority=0.45,
                        )
                        memory_written = True
                        ok_any = True
                        detail_parts.append("memory_digest_partial")
                except Exception as e:
                    detail_parts.append(str(e)[:80])
            else:
                orchestration_ran = False
                from .orchestration.tools.candidates import BROKERED_BOUNDED_SELF_TASK_ARCHETYPES

                if arch in BROKERED_BOUNDED_SELF_TASK_ARCHETYPES and bool(
                    st_cfg.get("orchestration_bounded_capability_execution", True)
                ):
                    try:
                        from .orchestration import TaskRequest, get_orchestration_broker

                        caps = task.get("recommended_capabilities") or []
                        goal = str(task.get("goal") or "")[:500]
                        prompt = (
                            f"Self-task archetype: {arch}\nGoal: {goal}\n"
                            f"Recommended capabilities: {caps}\n"
                            "Plan one bounded module or tool execution aligned with the goal."
                        )
                        ctx = {
                            "allowed_capabilities": list(caps),
                            "archetype": arch,
                            "goal": goal,
                            "task_id": task_id,
                            "underused_modules": list(task.get("underused_modules") or []),
                            "bounded_settings": {
                                "min_action_confidence": float(
                                    st_cfg.get("bounded_action_min_confidence", 0.35)
                                ),
                                "max_action_candidates": int(
                                    st_cfg.get("bounded_action_max_candidates", 5)
                                ),
                                "invalid_intent_fallback": str(
                                    st_cfg.get(
                                        "bounded_action_invalid_fallback",
                                        "legacy_capability_loop",
                                    )
                                ),
                            },
                        }
                        meta_gov: Dict[str, Any] = {
                            "prefer_bounded_action": True,
                            "governance_hints": [],
                        }
                        if getattr(self, "_self_task_low_confidence_streak", 0) >= int(
                            st_cfg.get("low_confidence_streak_trigger", 2)
                        ):
                            meta_gov["governance_hints"].append("repeated_low_value_local")
                        req = TaskRequest(
                            task_id=str(task_id),
                            task_type="bounded_action",
                            prompt=prompt,
                            context=ctx,
                            metadata=meta_gov,
                        )
                        pr = get_orchestration_broker().run_task_sync(req, guardian=self)
                        if pr.success and isinstance(pr.final_output, dict):
                            bundle = pr.final_output
                            rfg = bundle.get("result_for_governance")
                            if rfg is not None:
                                orchestration_ran = True
                                last_result = rfg
                                capability_attempted = True
                                exb = bundle.get("execution") or {}
                                if isinstance(exb, dict) and exb.get("success") is not None:
                                    capability_ok = bool(exb.get("success"))
                                    ok_any = capability_ok
                                else:
                                    capability_ok = self._self_task_payload_useful(rfg)
                                    ok_any = capability_ok or bool(rfg)
                                useful_any = self._self_task_payload_useful(rfg)
                                if isinstance(exb, dict):
                                    pl_ex = exb.get("payload")
                                    if isinstance(pl_ex, dict) and isinstance(
                                        pl_ex.get("executor_response"), dict
                                    ):
                                        last_capability_ex = pl_ex.get("executor_response")
                                detail_parts.append("orchestration_bounded_action")
                    except Exception as _oe:
                        detail_parts.append(f"orchestration_bounded:{str(_oe)[:80]}")

                if not orchestration_ran:
                    caps = task.get("recommended_capabilities") or []
                    for cap in caps[:2]:
                        if ":" not in cap:
                            continue
                        kind, _, name = cap.partition(":")
                        kind = kind.strip().lower()
                        name = name.strip()
                        if kind not in ("module", "tool"):
                            continue
                        capability_attempted = True
                        goal = str(task.get("goal") or "")[:500]
                        inp: Dict[str, Any] = {
                            "task": goal,
                            "query": goal[:400],
                            "objective": goal,
                            "self_task_archetype": arch,
                            "underused_modules": list(task.get("underused_modules") or []),
                        }
                        if kind == "module" and name == "task_router":
                            from .routing_task_type import infer_canonical_routing_task_type

                            rt, rsn = infer_canonical_routing_task_type(goal, archetype=arch)
                            logger.info(
                                "[SelfTasking] routing_task_type inferred=%s reason=%s archetype=%s goal_sample=%s",
                                rt,
                                rsn,
                                (arch or "")[:120],
                                (goal or "")[:160],
                            )
                            inp["structured_task"] = {
                                "task_type": rt,
                                "objective": goal,
                                "payload": {
                                    "source": "self_tasking",
                                    "format_version": 1,
                                    "task_id": task_id,
                                    "routing_inference": rsn,
                                },
                            }
                        ex = execute_capability_kind(self, kind, name, inp)
                        last_capability_ex = ex if isinstance(ex, dict) else None
                        ok = bool(ex.get("success"))
                        res = ex.get("result")
                        last_result = res
                        if ok:
                            capability_ok = True
                            ok_any = True
                        if self._self_task_payload_useful(res):
                            useful_any = True
                        detail_parts.append(f"{kind}:{name}={'ok' if ok else 'fail'}")

            detail = " | ".join(detail_parts)[:400]
        except Exception as e:
            detail = str(e)[:400]
            ok_any = False
            useful_any = False

        base_strong = self._self_task_has_strong_signals(
            useful_payload=useful_any,
            memory_written=memory_written,
            last_result=last_result,
            capability_ok=capability_ok,
        )
        cid = (task.get("output_contract_id") or contract_id_for_archetype(arch) or "").strip() or None
        contract_ok = True
        if base_strong and cid and ok_any:
            payload = last_result if arch in learning_digest_archs else normalize_payload(last_result)
            contract_ok, _creason = validate_contract(cid, payload)
        strong = bool(base_strong and contract_ok)

        if not ok_any:
            tier = "failed"
        elif strong:
            tier = "strong"
        else:
            tier = "weak"

        oid = task.get("objective_id")
        adv_payload_for_eval = (
            last_result
            if arch in learning_digest_archs
            else normalize_payload(last_result)
        )
        adv_result = evaluate_task_advancement(
            archetype=arch,
            execution_tier=tier,
            contract_ok=contract_ok,
            contract_id=cid,
            payload=adv_payload_for_eval,
            objective_id=str(oid) if oid else None,
            store=obj_store,
            guardian=self,
        )
        if oid:
            merge_best_artifact(
                obj_store,
                str(oid),
                task_id=task_id,
                archetype=arch,
                payload=adv_payload_for_eval,
                advancement=adv_result,
            )

        objective_advanced = bool(adv_result.get("objective_advanced"))
        operator_ready = bool(adv_result.get("operator_ready"))
        execution_ready = bool(adv_result.get("execution_ready"))

        art_path = None
        if tier == "strong" and cid and contract_ok:
            art_payload_pre = (
                last_result
                if arch in learning_digest_archs
                else normalize_payload(last_result)
            )
            art_path = save_self_task_artifact(
                task_id=task_id,
                archetype=arch,
                contract_id=cid,
                payload=art_payload_pre,
                execution_tier=tier,
            )

        exec_result = evaluate_execution_outcome(
            archetype=arch,
            execution_ready=execution_ready,
            execution_tier=tier,
            capability_attempted=capability_attempted,
            capability_ok=capability_ok,
            last_result=last_result,
            artifact_path=art_path,
            memory_written=memory_written,
            last_capability_ex=last_capability_ex,
            detail=detail,
        )

        value_result = evaluate_execution_value(
            archetype=arch,
            adv_result=adv_result,
            exec_result=exec_result,
            artifact_path=art_path,
            execution_tier=tier,
            payload=adv_payload_for_eval,
        )

        _cm = cycle_metadata if isinstance(cycle_metadata, dict) else {}
        _snap = _cm.get("cycle_selection_snapshot")
        cycle_pri = evaluate_cycle_priority_choice(
            chosen_task_id=str(task_id),
            chosen_archetype=arch,
            chosen_task=task if isinstance(task, dict) else {},
            snapshot=_snap if isinstance(_snap, list) else None,
            value_verified=bool(value_result.get("value_verified")),
            objective_advanced=objective_advanced,
            execution_outcome=str(exec_result.get("execution_outcome") or "none"),
        )

        from .self_task_portfolio import PortfolioCycleTracker

        _port_tracker = PortfolioCycleTracker()
        port_res = _port_tracker.record_and_score_event(
            archetype=arch,
            task=task if isinstance(task, dict) else {},
            success=ok_any,
            tier=tier,
            value_verified=bool(value_result.get("value_verified")),
            value_score=float(value_result.get("value_score") or 0.0),
            cycle_best_choice_verified=bool(cycle_pri.get("cycle_best_choice_verified")),
            cycle_choice_score=float(cycle_pri.get("cycle_choice_score") or 0.0),
            blocker_removed=bool(value_result.get("blocker_removed")),
        )

        q.complete(
            task_id,
            success=ok_any,
            useful=useful_any,
            detail=detail,
            execution_tier=tier,
            objective_advanced=objective_advanced,
            advancement_score=float(adv_result.get("advancement_score") or 0.0),
            advancement_reason=str(adv_result.get("advancement_reason") or ""),
            operator_ready=operator_ready,
            execution_ready=execution_ready,
            execution_attempted=bool(exec_result.get("execution_attempted")),
            execution_outcome=str(exec_result.get("execution_outcome") or "none"),
            execution_reason=str(exec_result.get("execution_reason") or ""),
            execution_artifact=exec_result.get("execution_artifact"),
            execution_followup_needed=bool(exec_result.get("execution_followup_needed")),
            value_verified=bool(value_result.get("value_verified")),
            value_score=float(value_result.get("value_score") or 0.0),
            value_reason=str(value_result.get("value_reason") or ""),
            value_type=str(value_result.get("value_type") or "none"),
            cycle_best_choice_verified=bool(cycle_pri.get("cycle_best_choice_verified")),
            cycle_choice_score=float(cycle_pri.get("cycle_choice_score") or 0.0),
            cycle_choice_reason=str(cycle_pri.get("cycle_choice_reason") or ""),
            cycle_opportunity_cost=str(cycle_pri.get("cycle_opportunity_cost") or "low"),
            higher_priority_task_skipped=bool(cycle_pri.get("higher_priority_task_skipped")),
            portfolio_balance_score=float(port_res.get("portfolio_balance_score") or 0.0),
            portfolio_reason=str(port_res.get("portfolio_reason") or ""),
        )

        ex_out_l = str(exec_result.get("execution_outcome") or "").lower()
        if oid and is_execution_stage_archetype(arch):
            obj_store.apply_post_execution_objective(
                str(oid),
                archetype=arch,
                exec_result=exec_result,
                value_result=value_result,
            )
        elif oid and objective_advanced and tier in ("strong", "weak"):
            delta = 0.06 if tier == "strong" else 0.035
            obj_store.bump_progress(str(oid), delta, real_outcome=True)

        if art_path is not None and objective_advanced and oid:
            obj_store.record_strong_artifact(str(oid))

        cooldown = float(st_cfg.get("dedupe_cooldown_sec", 900))
        finished = q.get_by_id(task_id) or task
        try:
            maybe_enqueue_followups(
                self,
                finished,
                execution_tier=tier,
                useful=useful_any,
                objective_advanced=objective_advanced,
                operator_ready=operator_ready,
                execution_ready=execution_ready,
                queue=q,
                objective_store=obj_store,
                st_cfg=st_cfg,
                cooldown_sec=cooldown,
            )
            maybe_enqueue_execution_outcome_followups(
                self,
                finished,
                queue=q,
                objective_store=obj_store,
                st_cfg=st_cfg,
                cooldown_sec=cooldown,
            )
        except Exception as e:
            logger.debug("self_task followups: %s", e)

        try:
            self._orchestration_registry.log_capability_usage(
                task=str(task.get("title", ""))[:500],
                capability_id=f"self_task:{task_id}",
                capability_type="self_task",
                success=ok_any,
                quality=(
                    0.98
                    if (
                        str(exec_result.get("execution_outcome") or "").lower() == "succeeded"
                        and bool(value_result.get("value_verified"))
                        and bool(cycle_pri.get("cycle_best_choice_verified"))
                        and float(port_res.get("portfolio_balance_score") or 0.0) >= 0.78
                        and tier == "strong"
                    )
                    else (
                    0.97
                    if (
                        str(exec_result.get("execution_outcome") or "").lower() == "succeeded"
                        and bool(value_result.get("value_verified"))
                        and bool(cycle_pri.get("cycle_best_choice_verified"))
                        and tier == "strong"
                    )
                    else (
                        0.95
                        if (
                            str(exec_result.get("execution_outcome") or "").lower() == "succeeded"
                            and bool(value_result.get("value_verified"))
                            and tier == "strong"
                        )
                        else (
                            0.92
                            if (
                                str(exec_result.get("execution_outcome") or "").lower() == "succeeded"
                                and tier == "strong"
                            )
                            else (
                                0.88
                                if (tier == "strong" and useful_any and objective_advanced and operator_ready)
                                else (
                                    0.82
                                    if (tier == "strong" and useful_any and objective_advanced)
                                    else (
                                        0.68
                                        if (tier == "strong" and useful_any)
                                        else (0.55 if tier != "failed" else 0.2)
                                    )
                                )
                            )
                        )
                    )
                )
                ),
                latency_ms=(time.time() - t0) * 1000,
                extra={
                    "archetype": arch,
                    "useful": useful_any,
                    "detail": detail,
                    "execution_tier": tier,
                    "objective_advanced": objective_advanced,
                    "operator_ready": operator_ready,
                    "execution_ready": execution_ready,
                    "execution_attempted": exec_result.get("execution_attempted"),
                    "execution_outcome": exec_result.get("execution_outcome"),
                    "execution_reason": (exec_result.get("execution_reason") or "")[:160],
                    "value_verified": value_result.get("value_verified"),
                    "value_score": value_result.get("value_score"),
                    "value_reason": (value_result.get("value_reason") or "")[:160],
                    "value_type": value_result.get("value_type"),
                    "advancement_score": adv_result.get("advancement_score"),
                    "advancement_reason": (adv_result.get("advancement_reason") or "")[:200],
                    "readiness_reason": (adv_result.get("readiness_reason") or "")[:120],
                    "cycle_best_choice_verified": cycle_pri.get("cycle_best_choice_verified"),
                    "cycle_choice_score": cycle_pri.get("cycle_choice_score"),
                    "cycle_choice_reason": (cycle_pri.get("cycle_choice_reason") or "")[:160],
                    "cycle_opportunity_cost": cycle_pri.get("cycle_opportunity_cost"),
                    "higher_priority_task_skipped": cycle_pri.get("higher_priority_task_skipped"),
                    "portfolio_balance_score": port_res.get("portfolio_balance_score"),
                    "portfolio_reason": (port_res.get("portfolio_reason") or "")[:160],
                    "portfolio_category": port_res.get("portfolio_category"),
                },
            )
        except Exception:
            pass
        try:
            _cm = cycle_metadata if isinstance(cycle_metadata, dict) else {}
            if _cm.get("degraded_autonomy"):
                from .planner_readiness import note_degraded_execute_self_task_outcome

                note_degraded_execute_self_task_outcome(
                    tier=str(tier),
                    useful=useful_any,
                    objective_advanced=objective_advanced,
                    archetype=arch,
                )
        except Exception:
            pass
        return ok_any, useful_any, detail

    def _self_tasking_augment_decision(
        self,
        candidates: List[Dict[str, Any]],
        best: Optional[Dict[str, Any]],
        mistral_decision: Optional[Dict[str, Any]],
        override_reason: Optional[str],
        decider_cfg: Dict[str, Any],
        use_mistral: bool,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        st_cfg = self._load_self_tasking_config()
        if not st_cfg.get("enabled", True):
            return candidates, best
        if not self._load_autonomy_config().get("self_generated_tasks", True):
            return candidates, best

        from .self_task_generator import (
            SelfTaskGenerator,
            build_context_for_guardian,
            enqueue_generated,
        )
        from .self_task_objectives import ObjectiveStore
        from .self_task_queue import SelfTaskQueue

        obj_store = ObjectiveStore()

        if use_mistral and mistral_decision is not None:
            conf = float(mistral_decision.get("confidence", 1.0) or 1.0)
            thr = float(decider_cfg.get("mistral_decision_confidence_threshold", 0.5))
            if conf < thr:
                self._self_task_low_confidence_streak = int(
                    getattr(self, "_self_task_low_confidence_streak", 0) or 0
                ) + 1
            else:
                self._self_task_low_confidence_streak = 0

        queue = SelfTaskQueue(max_size=int(st_cfg.get("max_queue_size", 24)))
        queue.expire_stale(
            ttl_sec=float(st_cfg.get("stale_ttl_sec", 7200)),
            max_priority=float(st_cfg.get("expire_max_priority", 0.35)),
        )

        ctx = build_context_for_guardian(
            self,
            candidates_empty=len(candidates) == 0,
            mistral_decision=mistral_decision,
            override_reason=override_reason,
            decider_cfg=decider_cfg,
            self_task_cfg=st_cfg,
        )
        gen = SelfTaskGenerator(st_cfg)
        cooldown = float(st_cfg.get("dedupe_cooldown_sec", 900))
        if gen.should_generate(ctx, queue):
            new_tasks = gen.build(self, ctx)
            enqueue_generated(
                queue,
                new_tasks,
                cooldown_sec=cooldown,
                guardian=self,
                objective_store=obj_store,
            )

        from .self_task_portfolio import PortfolioCycleTracker

        _portfolio_tracker = PortfolioCycleTracker()
        pending = queue.list_pending_sorted(obj_store, _portfolio_tracker)
        if not pending:
            return list(candidates), best

        top = pending[0]
        from .self_task_cycle_priority import build_cycle_selection_snapshot

        _cycle_snap = build_cycle_selection_snapshot(
            pending, obj_store, chosen_task_id=str(top.get("task_id") or "")
        )
        thr_c = float(decider_cfg.get("mistral_decision_confidence_threshold", 0.5))
        conf = float((mistral_decision or {}).get("confidence", 1.0) or 1.0)
        weak = (
            len(candidates) == 0
            or best is None
            or (override_reason or "")
            in ("low_confidence", "invalid_action", "low_confidence_force_capability")
            or (use_mistral and mistral_decision is not None and conf < thr_c)
        )
        pri_boost = float(top.get("priority", 0.5) or 0.5)
        pri_self = float(st_cfg.get("prefer_over_priority_below", 5.5)) + pri_boost
        if str(top.get("value_tier") or "") == "high":
            pri_self += float(st_cfg.get("operator_value_priority_boost", 0.42))
        try:
            tr_mod = (getattr(self, "_modules", None) or {}).get("tool_registry")
            reg_weak = bool(tr_mod) and not self._tool_registry_minimal_capabilities_ok(tr_mod)
        except Exception:
            reg_weak = False
        ta = str(top.get("archetype") or "")
        if reg_weak and ta in ("validate_tool_registry_snapshot", "repair_tool_registry_coverage"):
            pri_self += float(st_cfg.get("blocking_maintenance_priority_boost", 0.55))
        cand = {
            "action": "execute_self_task",
            "source": "self_tasking",
            "reason": str(top.get("title") or "Bounded self-task")[:200],
            "priority_score": pri_self,
            "can_auto_execute": True,
            "metadata": {
                "self_task_id": top.get("task_id"),
                "cycle_selection_snapshot": _cycle_snap,
            },
        }
        out_c = list(candidates)
        if not any(c.get("action") == "execute_self_task" for c in out_c):
            out_c.append(cand)

        top_oid = top.get("objective_id")
        chain_active = bool(top_oid) and obj_store.is_active(str(top_oid))
        idle_or_weak = weak or best is None or len(candidates) == 0
        if chain_active and idle_or_weak:
            return out_c, dict(cand)

        cur_pri = (best or {}).get("priority_score", 0) or 0
        if weak or best is None or cur_pri < pri_self - 0.25:
            return out_c, dict(cand)
        return out_c, best

    def _autonomy_in_degraded_planner_mode(self, next_result: Optional[Dict[str, Any]] = None) -> bool:
        nr = next_result if next_result is not None else getattr(self, "_last_autonomy_next_result", None)
        if not nr:
            return False
        pr = nr.get("planner_runtime") or {}
        return str(pr.get("autonomy_planner_mode") or "") == "degraded_autonomy"

    def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Autonomous decision loop: get next action and execute if allowed.
        Called periodically from heartbeat. Returns { executed, action, reason }.
        """
        result = {"executed": False, "action": None, "reason": None}
        cfg = self._load_autonomy_config()
        if not cfg.get("enabled", False):
            return result
        allowed = set(cfg.get("allowed_actions", []))
        if not allowed:
            return result
        max_per_hour = cfg.get("max_actions_per_hour", 6)
        if max_per_hour > 0:
            now = datetime.datetime.now()
            action_times = getattr(self, "_autonomy_action_times", [])
            action_times = [t for t in action_times if (now - t).total_seconds() < 3600]
            if len(action_times) >= max_per_hour:
                return result
        try:
            t0 = time.time()
            self._autonomy_cycle_t0 = t0
            next_result = self.get_next_action()
            self._last_autonomy_next_result = next_result
            action = next_result.get("action")
            if not action or action == "continue_monitoring":
                return result
            if not next_result.get("can_auto_execute"):
                return result
            dynamic_uc = cfg.get("allow_dynamic_capability_actions", True) and isinstance(
                action, str
            ) and action.startswith("use_capability/")
            self_task_ok = cfg.get("self_generated_tasks", True) and action == "execute_self_task"
            if action not in allowed and not dynamic_uc and not self_task_ok:
                return result
            # Mistral asked operator: store question, skip auto-execute this cycle (gives Mistral control to pause)
            decider_cfg = self._load_mistral_decider_config()
            if decider_cfg.get("mistral_skip_auto_execute_when_ask_user", True) and next_result.get("ask_user_question"):
                self._pending_operator_question = next_result.get("ask_user_question")
                result["reason"] = "Mistral requested operator question; skipping auto-execute"
                result["ask_user_question"] = self._pending_operator_question
                return result
            self._pending_operator_question = None
            action_meaningful_success = True
            if action == "execute_self_task":
                tid = (next_result.get("metadata") or {}).get("self_task_id")
                if not tid:
                    action_meaningful_success = False
                    self.memory.remember(
                        "[Autonomy] execute_self_task missing self_task_id",
                        category="error",
                        priority=0.5,
                    )
                else:
                    _meta = dict(next_result.get("metadata") or {})
                    _meta["degraded_autonomy"] = self._autonomy_in_degraded_planner_mode(next_result)
                    ok_m, useful_m, det = self._run_self_generated_task(str(tid), t0, _meta)
                    action_meaningful_success = bool(useful_m or ok_m)
                    self.memory.remember(
                        f"[Autonomy] execute_self_task {tid}: ok={ok_m} useful={useful_m} {det[:160]}",
                        category="autonomy",
                        priority=0.55,
                    )
                self._module_last_invoked["self_tasking"] = datetime.datetime.now().isoformat()
            elif action == "consider_learning":
                try:
                    if getattr(self, "elysia_loop", None) and hasattr(self.elysia_loop, "submit_task"):
                        self.elysia_loop.submit_task(
                            lambda: self._trigger_introspection_learning(),
                            module="autonomy_learning",
                            priority=5,
                        )
                    else:
                        self._trigger_introspection_learning()
                except Exception as e:
                    logger.debug(f"ElysiaLoop learning submit: {e}")
                    self._trigger_introspection_learning()
                self._module_last_invoked["learning"] = datetime.datetime.now().isoformat()
                self.memory.remember("[Autonomy] Executed consider_learning", category="autonomy", priority=0.6)
            elif action == "consider_dream_cycle":
                def _do_dream_cycle() -> None:
                    try:
                        thoughts = self.dreams.begin_dream_cycle(1)
                        if thoughts:
                            joined = "; ".join(str(t) for t in thoughts)
                            logger.info(
                                "[Dream cycle] finished (%d thought(s); text in [Dream] lines above)",
                                len(thoughts),
                            )
                            self.memory.remember(
                                f"[Autonomy] consider_dream_cycle: {joined}",
                                category="autonomy",
                                priority=0.6,
                            )
                        else:
                            logger.info("[Dream cycle] finished (no thoughts composed)")
                            self.memory.remember(
                                "[Autonomy] consider_dream_cycle (no thoughts composed)",
                                category="autonomy",
                                priority=0.6,
                            )
                    except Exception as ex:
                        logger.warning("Dream cycle failed: %s", ex)

                try:
                    if getattr(self, "elysia_loop", None) and hasattr(self.elysia_loop, "submit_task"):
                        self.elysia_loop.submit_task(
                            _do_dream_cycle,
                            module="autonomy_dream",
                            priority=6,
                        )
                    else:
                        _do_dream_cycle()
                except Exception as e:
                    logger.debug(f"ElysiaLoop dream submit: {e}")
                    _do_dream_cycle()
                self._module_last_invoked["dreams"] = datetime.datetime.now().isoformat()
            elif action == "consider_prompt_evolution":
                evolved = self.run_prompt_evolution(min_records=3)
                self.memory.remember(
                    f"[Autonomy] Executed consider_prompt_evolution (evolved {evolved} prompts)",
                    category="autonomy", priority=0.6
                )
            elif action == "rebuild_vector":
                try:
                    rebuild_result = self.rebuild_vector_memory_if_pending()
                    self.memory.remember(
                        f"[Autonomy] Executed rebuild_vector: {rebuild_result.get('reason', 'done')}",
                        category="autonomy", priority=0.7
                    )
                except Exception as e:
                    logger.debug("Autonomy rebuild_vector: %s", e)
                    self.memory.remember(f"[Autonomy] rebuild_vector failed: {e}", category="error", priority=0.8)
            elif action == "consider_adversarial_learning":
                adv_result = run_adversarial_cycle(self, triggered_by=TRIGGER_PERIODIC)
                try:
                    self._mistral_update_adversarial_gating(adv_result, self._load_mistral_decider_config())
                except Exception as ae:
                    logger.debug("adversarial gating: %s", ae)
                self.memory.remember(
                    f"[Autonomy] Executed consider_adversarial_learning: findings={adv_result.get('findings_count', 0)} tasks={adv_result.get('tasks_created', 0)}",
                    category="autonomy", priority=0.7
                )
                self._module_last_invoked["adversarial_self_learning"] = datetime.datetime.now().isoformat()
            elif action == "process_queue":
                action_meaningful_success = False
                self._autonomy_last_advanced = False
                try:
                    loop = getattr(self, "elysia_loop", None)
                    tq = getattr(loop, "task_queue", None) if loop else None
                    if not tq:
                        try:
                            from .planner_readiness import record_autonomy_noop_outcome

                            record_autonomy_noop_outcome("process_queue", reason="no_task_queue")
                        except Exception:
                            pass
                    else:
                        before_sz = int(tq.get_queue_size())
                        before_tot = int(tq.get_task_count())
                        time.sleep(0.15)
                        after_sz = int(tq.get_queue_size())
                        after_tot = int(tq.get_task_count())
                        changed = before_sz != after_sz or before_tot != after_tot
                        logger.info(
                            "[Autonomy] process_queue snapshot before=(q=%s,tot=%s) after=(q=%s,tot=%s) changed=%s",
                            before_sz,
                            before_tot,
                            after_sz,
                            after_tot,
                            changed,
                        )
                        if changed:
                            try:
                                from .planner_readiness import clear_autonomy_noop_streak

                                clear_autonomy_noop_streak("process_queue")
                            except Exception:
                                pass
                        else:
                            try:
                                from .planner_readiness import record_autonomy_noop_outcome

                                record_autonomy_noop_outcome(
                                    "process_queue",
                                    reason="queue_totals_unchanged_after_probe",
                                )
                            except Exception:
                                pass
                        action_meaningful_success = bool(changed)
                        self._autonomy_last_advanced = bool(changed)
                    self._module_last_invoked["elysia_loop"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    logger.debug("Autonomy process_queue: %s", e)
                    self.memory.remember(f"[Autonomy] process_queue failed: {e}", category="error", priority=0.65)
            elif action == "question_probe":
                probe_msg = next_result.get("ask_user_question") or "System exploring alternatives — any priorities or guidance?"
                self._pending_operator_question = probe_msg
                self._module_last_invoked["exploration"] = datetime.datetime.now().isoformat()
                self.memory.remember(f"[Autonomy] Executed question_probe: {probe_msg[:80]}...", category="autonomy", priority=0.6)
                logger.info("[Exploration] question_probe: %s", probe_msg[:100])
            elif action == "code_analysis":
                try:
                    analysis_result = self.analysis_engine.run("REPO_SUMMARY", [], task_id=None)
                    ext_count = len(analysis_result.get("file_counts_by_extension", {}))
                    lines_est = analysis_result.get("total_lines_estimate", 0)
                    self.memory.remember(
                        f"[Autonomy] Executed code_analysis: {ext_count} extensions, ~{lines_est} lines (exploratory)",
                        category="autonomy", priority=0.6
                    )
                    self._module_last_invoked["analysis_engine"] = datetime.datetime.now().isoformat()
                    logger.info("[Exploration] code_analysis: repo summary completed")
                except Exception as e:
                    logger.debug("Autonomy code_analysis: %s", e)
                    self.memory.remember(f"[Autonomy] code_analysis failed: {e}", category="error", priority=0.7)
            elif action == "consider_mutation":
                try:
                    from .mutation import load_mutation_autonomy_config

                    mac = load_mutation_autonomy_config()
                    ran_openai = False
                    if (
                        mac.get("enabled")
                        and os.getenv("OPENAI_API_KEY")
                        and self.mutation
                    ):
                        raw_targets = mac.get("target_files") or []
                        targets: List[str] = []
                        for t in raw_targets:
                            if not t or not isinstance(t, str):
                                continue
                            norm = t.replace("\\", "/").strip()
                            if self.mutation._is_protected_path(norm):
                                logger.debug("consider_mutation: skip protected target %s", norm)
                                continue
                            targets.append(norm)
                        if targets:
                            idx = getattr(self, "_mutation_autonomy_index", 0) % len(targets)
                            self._mutation_autonomy_index = idx + 1
                            rel = targets[idx]
                            instr = (mac.get("instruction_template") or "").strip()
                            mistral_r = (next_result.get("reason") or "")[:500]
                            if mistral_r:
                                instr = f"{instr}\n\nMistral decision context: {mistral_r}"
                            new_code = self.mutation.generate_mutation_with_openai(
                                rel,
                                instr,
                                module_name="planner",
                                agent_name="executor",
                                model=str(mac.get("openai_model") or "gpt-4o-mini"),
                                max_output_tokens=int(mac.get("max_output_tokens") or 4096),
                                max_input_chars=int(mac.get("max_input_chars") or 60000),
                            )
                            if new_code:
                                try:
                                    res = self.mutation.propose_mutation(
                                        rel,
                                        new_code,
                                        require_review=False,
                                        caller_identity="mistral_consider_mutation_openai",
                                        danger_profile="llm_assisted",
                                    )
                                    ran_openai = True
                                    self.memory.remember(
                                        f"[Autonomy] consider_mutation OpenAI→mutation {rel}: {res.summary}",
                                        category="autonomy",
                                        priority=0.65,
                                    )
                                    logger.info("[Exploration] consider_mutation: OpenAI mutation applied %s", rel)
                                except Exception as me:
                                    ran_openai = True
                                    logger.warning("consider_mutation OpenAI apply failed: %s", me)
                                    self.memory.remember(
                                        f"[Autonomy] consider_mutation OpenAI apply failed {rel}: {me}",
                                        category="error",
                                        priority=0.7,
                                    )
                            else:
                                ran_openai = True
                                logger.info("[Exploration] consider_mutation: OpenAI returned no code for %s", rel)
                                self.memory.remember(
                                    f"[Autonomy] consider_mutation: OpenAI produced no code for {rel}",
                                    category="autonomy",
                                    priority=0.5,
                                )
                    if not ran_openai:
                        if hasattr(self.mutation, "mutation_log") and self.mutation.mutation_log:
                            pending = len([m for m in self.mutation.mutation_log if not m.get("applied")])
                            self.memory.remember(
                                f"[Autonomy] consider_mutation: {pending} pending in log (exploratory)",
                                category="autonomy",
                                priority=0.6,
                            )
                        else:
                            self.memory.remember(
                                "[Autonomy] consider_mutation: no OpenAI run or no pending mutations",
                                category="autonomy",
                                priority=0.5,
                            )
                        logger.info("[Exploration] consider_mutation: status check completed")
                    self._module_last_invoked["mutation"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    logger.debug("Autonomy consider_mutation: %s", e)
            elif action == "fractalmind_planning":
                try:
                    fm = (self._modules or {}).get("fractalmind")
                    if fm:
                        # FractalMind.process_task(prompt: str, depth=..., save_log=...) — not a dict
                        # Ask for a concrete planning artifact (we still parse from returned subtasks).
                        probe_prompt = (
                            "Elysia autonomy planning artifact: produce (1) ranked next action, "
                            "(2) hypothesis, (3) plan delta, (4) task recommendation."
                        )
                        if hasattr(fm, "process_task"):
                            try:
                                fractal_res = fm.process_task(
                                    probe_prompt,
                                    depth=3,
                                    save_log=True,
                                    source="guardian_autonomy_fractalmind_planning",
                                )
                            except TypeError:
                                try:
                                    fractal_res = fm.process_task(probe_prompt, depth=3, save_log=True)
                                except TypeError:
                                    fractal_res = fm.process_task(probe_prompt)
                        elif hasattr(fm, "plan"):
                            fm.plan()

                    # Parse and apply low-yield gating based on returned concreteness.
                    res = locals().get("fractal_res")
                    subtasks = res.get("subtasks") if isinstance(res, dict) else []
                    count = int(res.get("count", len(subtasks)) if isinstance(res, dict) else 0)
                    subtasks = subtasks or []

                    ranked_next_action = subtasks[0] if len(subtasks) > 0 else None
                    hypothesis = subtasks[1] if len(subtasks) > 1 else None
                    plan_delta = subtasks[2] if len(subtasks) > 2 else None
                    task_recommendation = (
                        subtasks[3] if len(subtasks) > 3 else "Submit tasks based on the ranked next action"
                    )

                    low_yield = count < 3 or not ranked_next_action
                    if low_yield:
                        self._fractalmind_low_yield_streak = getattr(self, "_fractalmind_low_yield_streak", 0) + 1
                        cooldown_min = 10 * self._fractalmind_low_yield_streak
                        self._fractalmind_low_yield_cooldown_until = time.time() + cooldown_min * 60
                    else:
                        self._fractalmind_low_yield_streak = 0
                        self._fractalmind_low_yield_cooldown_until = None

                    artifact = {
                        "ranked_next_action": ranked_next_action,
                        "hypothesis": hypothesis,
                        "plan_delta": plan_delta,
                        "task_recommendation": task_recommendation,
                        "count": count,
                        "low_yield": low_yield,
                    }
                    # Repeated identical high-level fingerprints → short suppression (no material change).
                    _payload = {
                        "c": count,
                        "r": (str(ranked_next_action)[:400] if ranked_next_action is not None else ""),
                        "h": (str(hypothesis)[:400] if hypothesis is not None else ""),
                        "p": (str(plan_delta)[:400] if plan_delta is not None else ""),
                        "t": (str(task_recommendation)[:400] if task_recommendation is not None else ""),
                    }
                    _fp = hashlib.sha256(
                        json.dumps(_payload, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    _prev_fp = getattr(self, "_fractalmind_last_artifact_fingerprint", None)
                    if _fp != _prev_fp:
                        self._fractalmind_repetition_suppress_until = None
                    if low_yield:
                        self._fractalmind_same_artifact_streak = 0
                    elif _fp == _prev_fp:
                        self._fractalmind_same_artifact_streak = (
                            getattr(self, "_fractalmind_same_artifact_streak", 0) + 1
                        )
                    else:
                        self._fractalmind_same_artifact_streak = 0
                    self._fractalmind_last_artifact_fingerprint = _fp
                    try:
                        _need = max(2, int(os.environ.get("ELYSIA_FRACTALMIND_REPEAT_STREAK_BEFORE_SUPPRESS", "3")))
                    except ValueError:
                        _need = 3
                    if self._fractalmind_same_artifact_streak >= _need:
                        try:
                            _cool = float(os.environ.get("ELYSIA_FRACTALMIND_REPEAT_COOLDOWN_SEC", "900"))
                        except ValueError:
                            _cool = 900.0
                        self._fractalmind_repetition_suppress_until = time.time() + _cool
                        logger.info(
                            "[FractalMind] Repeated identical planning artifact — suppression %.0fs",
                            _cool,
                        )
                        self._fractalmind_same_artifact_streak = 0

                    self._last_fractalmind_artifact = artifact
                    self._module_last_invoked["fractalmind"] = datetime.datetime.now().isoformat()
                    self.memory.remember(
                        f"[Autonomy] fractalmind_planning artifact: count={count} low_yield={low_yield}",
                        category="autonomy",
                        priority=0.6,
                        metadata=artifact,
                    )
                    logger.info("[Exploration] fractalmind_planning: artifact-ready=%s count=%d low_yield=%s", True, count, low_yield)
                except Exception as e:
                    logger.debug("Autonomy fractalmind_planning: %s", e)
                    self.memory.remember(f"[Autonomy] fractalmind_planning failed: {e}", category="error", priority=0.7)
            elif action == "harvest_income_report":
                try:
                    he = (self._modules or {}).get("harvest_engine")
                    if he and hasattr(he, "generate_income_report"):
                        report = he.generate_income_report("gumroad")
                        total = report.get("total_earned", 0) if isinstance(report, dict) else 0
                        sales = report.get("total_sales", 0) if isinstance(report, dict) else 0
                        self.memory.remember(
                            f"[Autonomy] harvest_income_report: total=${total} sales={sales}",
                            category="autonomy",
                            priority=0.55,
                        )
                        logger.info("[Exploration] harvest_income_report: total=%s sales=%s", total, sales)
                        try:
                            from .planner_readiness import (
                                clear_autonomy_noop_streak,
                                clear_degraded_low_value_streak,
                                record_autonomy_noop_outcome,
                                record_degraded_low_value_signal,
                                record_harvest_zero_yield_outcome,
                            )

                            nonzero = float(total or 0) > 0.0 or int(sales or 0) > 0
                            record_harvest_zero_yield_outcome(nonzero)
                            if nonzero:
                                clear_autonomy_noop_streak("harvest_income_report")
                                logger.debug(
                                    "[AutonomyNoop] harvest_income_report noop/suppression cleared (non-zero total=%s sales=%s)",
                                    total,
                                    sales,
                                )
                            else:
                                record_autonomy_noop_outcome(
                                    "harvest_income_report",
                                    reason="zero_total_zero_sales",
                                )
                            try:
                                from .mission_autonomy import mission_autonomy_feedback_harvest

                                mission_autonomy_feedback_harvest(nonzero=nonzero)
                            except Exception:
                                pass
                            if self._autonomy_in_degraded_planner_mode():
                                if nonzero:
                                    clear_degraded_low_value_streak("harvest_income_report")
                                else:
                                    record_degraded_low_value_signal(
                                        "harvest_income_report",
                                        reason="zero_total_sales_degraded",
                                    )
                        except Exception:
                            pass
                    self._module_last_invoked["harvest_engine"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    logger.debug("Autonomy harvest_income_report: %s", e)
                    self.memory.remember(f"[Autonomy] harvest_income_report failed: {e}", category="error", priority=0.65)
            elif action == "income_modules_pulse":
                prev_sig = self._income_modules_prev_sig_for_nonadv
                self._autonomy_last_advanced = True
                try:
                    m = self._modules or {}
                    snippets = []
                    earned = 0.0
                    active = 0
                    wallet_total = 0.0
                    elysia_acct = 0.0
                    cash = 0.0
                    ig = m.get("income_generator")
                    if ig and hasattr(ig, "get_income_summary"):
                        s = ig.get_income_summary()
                        if isinstance(s, dict):
                            earned = float(s.get("total_earned", 0) or 0)
                            active = int(s.get("active_projects", 0) or 0)
                            snippets.append(f"gen earned={earned:.2f} active={active}")
                    w = m.get("wallet")
                    if w and hasattr(w, "get_balance"):
                        b = w.get_balance()
                        if isinstance(b, dict):
                            wallet_total = float(b.get("total_balance", b.get("available_balance", 0) or 0) or 0)
                            snippets.append(f"wallet total={wallet_total}")
                        if hasattr(w, "wallet") and isinstance(getattr(w, "wallet", None), dict):
                            accs = w.wallet.get("accounts") or {}
                            ely = accs.get("elysia_autonomy")
                            if isinstance(ely, dict):
                                elysia_acct = float(ely.get("balance", 0) or 0)
                                snippets.append(f"elysia_acct={elysia_acct} {ely.get('currency', 'USD')}")
                    fm = m.get("financial_manager")
                    if fm and hasattr(fm, "get_financial_status"):
                        st = fm.get_financial_status()
                        if isinstance(st, dict):
                            cash = float(st.get("cash_balance", st.get("balance", 0) or 0) or 0)
                            snippets.append(f"fm cash={cash}")
                    _prev_income_sig = getattr(self, "_income_modules_last_sig", None)
                    sig = f"{earned:.2f}:{active}:{wallet_total:.2f}:{elysia_acct:.2f}:{cash:.2f}"
                    _all_zero_income = (
                        earned == 0.0 and wallet_total == 0.0 and elysia_acct == 0.0 and cash == 0.0
                    )
                    _same_income_sig = _prev_income_sig is not None and _prev_income_sig == sig
                    self._income_modules_last_sig = sig
                    self._income_modules_last_pulse_ts = time.time()
                    msg = "; ".join(snippets) if snippets else "no income module data"
                    if "no income module data" in msg:
                        self._autonomy_last_advanced = False
                    else:
                        self._autonomy_last_advanced = prev_sig is None or prev_sig != sig
                    self._income_modules_prev_sig_for_nonadv = sig
                    self.memory.remember(f"[Autonomy] income_modules_pulse: {msg[:200]}", category="autonomy", priority=0.55)
                    logger.info("[Exploration] income_modules_pulse: %s", msg[:120])
                    try:
                        from .mission_autonomy import mission_autonomy_feedback_income_pulse

                        mission_autonomy_feedback_income_pulse(
                            all_zero=_all_zero_income,
                            same_signature=_same_income_sig,
                        )
                    except Exception:
                        pass
                    if self._autonomy_in_degraded_planner_mode():
                        try:
                            from .planner_readiness import (
                                clear_degraded_low_value_streak,
                                record_degraded_low_value_signal,
                            )

                            if self._autonomy_last_advanced:
                                clear_degraded_low_value_streak("income_modules_pulse")
                            else:
                                record_degraded_low_value_signal(
                                    "income_modules_pulse",
                                    reason="no_meaningful_delta_degraded",
                                )
                        except Exception:
                            pass
                    self._module_last_invoked["income_modules"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    logger.debug("Autonomy income_modules_pulse: %s", e)
                    self._autonomy_last_advanced = False
                    self.memory.remember(f"[Autonomy] income_modules_pulse failed: {e}", category="error", priority=0.65)
            elif action == "tool_registry_pulse":
                action_meaningful_success = False
                self._autonomy_last_advanced = False
                _zero_pulse_limit = 3
                _pulse_cooldown_sec = 180.0
                try:
                    cd_until = float(getattr(self, "_tool_registry_pulse_cooldown_until", 0.0) or 0.0)
                    if time.time() < cd_until:
                        rem = int(cd_until - time.time())
                        logger.info(
                            "[Exploration] tool_registry_pulse suppressed (cooldown %ds; prefer other exploration)",
                            rem,
                        )
                        self.memory.remember(
                            f"[Autonomy] tool_registry_pulse skipped: cooldown {rem}s",
                            category="autonomy",
                            priority=0.45,
                        )
                    else:
                        tr = (self._modules or {}).get("tool_registry")
                        if tr and hasattr(tr, "ensure_minimal_builtin_tools"):
                            try:
                                tr.ensure_minimal_builtin_tools()
                            except Exception:
                                pass
                        if not tr or not self._tool_registry_minimal_capabilities_ok(tr):
                            self.memory.remember(
                                "[Autonomy] tool_registry_pulse skipped: registry lacks llm/web/exec tools",
                                category="autonomy",
                                priority=0.5,
                            )
                            logger.info("[Autonomy] tool_registry_pulse skipped (minimal tool set not met)")
                        else:
                            n, _names, diag = self._tool_registry_pulse_metrics(tr)
                            surf = diag.get("surface") if isinstance(diag.get("surface"), dict) else {}
                            excl = diag.get("exclusion_hint") or surf.get("filter_reason") or ""
                            if excl == "ok":
                                excl = ""
                            logger.info(
                                "[Exploration] tool_registry_pulse diag id=%s cls=%s raw_list_len=%s map=%s usable=%s "
                                "return_type=%s raw_first=%s coerced_first=%s filter=%s coerce=%s",
                                diag.get("registry_id"),
                                diag.get("registry_class"),
                                diag.get("raw_list_tools_len"),
                                diag.get("raw_tools_map_count"),
                                n,
                                diag.get("list_tools_return_type"),
                                diag.get("raw_first_names"),
                                diag.get("first_names"),
                                excl or "(none)",
                                (diag.get("coerce_suffix") or "")[:160],
                            )
                            if n == 0:
                                streak = int(getattr(self, "_tool_registry_zero_pulse_streak", 0) or 0) + 1
                            else:
                                streak = 0
                            self._tool_registry_zero_pulse_streak = streak
                            if streak >= _zero_pulse_limit:
                                self._tool_registry_pulse_cooldown_until = time.time() + _pulse_cooldown_sec
                                self._tool_registry_zero_pulse_streak = 0
                                logger.warning(
                                    "[Exploration] tool_registry_pulse: %d consecutive zero-usable pulses; "
                                    "cooldown %.0fs (other exploration actions preferred)",
                                    _zero_pulse_limit,
                                    _pulse_cooldown_sec,
                                )

                            router = (self._modules or {}).get("task_router")
                            route_hint = ""
                            route_to = None
                            r = None
                            if router and hasattr(router, "route_task"):
                                r = self._invoke_task_router_probe(router)
                                if isinstance(r, dict):
                                    route_to = r.get("routed_to")
                                    # Label: registry + router health only — not a multi-tool exercise.
                                    route_hint = f" route_registry_health->{route_to}"
                                    tied = r.get("diagnostic_tied_tools_at_winner_score")
                                    pick_rule = r.get("diagnostic_pick_rule") or ""
                                    logger.info(
                                        "[Exploration] registry_router_health_probe (task_type=routing_probe) "
                                        "reply routed_to=%s score=%s tied_at_winner_score=%s pick_rule=%s "
                                        "(health check only — no web/exec execution; tie-break policy, not tool visibility)",
                                        route_to,
                                        r.get("score"),
                                        tied,
                                        pick_rule,
                                    )
                            self._tool_registry_last_sig = f"{n}:{route_to}"
                            self._tool_registry_last_pulse_ts = time.time()
                            self.memory.remember(
                                f"[Autonomy] tool_registry_pulse: {n} tools{route_hint}",
                                category="autonomy",
                                priority=0.55,
                            )
                            logger.info("[Exploration] tool_registry_pulse: %d usable tools%s", n, route_hint)
                            self._module_last_invoked["tool_registry"] = datetime.datetime.now().isoformat()
                            meaningful = n >= 3
                            if isinstance(r, dict):
                                if r.get("data") or r.get("tasks") or r.get("result"):
                                    meaningful = True
                                elif route_to and not r.get("data") and not r.get("tasks"):
                                    meaningful = False
                            action_meaningful_success = bool(meaningful)
                            self._autonomy_last_advanced = bool(meaningful)
                except Exception as e:
                    logger.debug("Autonomy tool_registry_pulse: %s", e)
                    self.memory.remember(f"[Autonomy] tool_registry_pulse failed: {e}", category="error", priority=0.65)
            elif action == "work_on_objective":
                action_meaningful_success = False
                self._autonomy_last_advanced = False
                state_changed = False
                try:
                    planner = (self._modules or {}).get("longterm_planner")
                    tasks_created = 0
                    submitted = 0
                    objective_id = None
                    if planner:
                        # Pick first active objective and ensure it has pending tasks.
                        active = []
                        if hasattr(planner, "list_active_objectives"):
                            active = planner.list_active_objectives() or []
                        elif hasattr(planner, "objectives"):
                            try:
                                raw = planner.objectives
                                seq = list(raw.values()) if isinstance(raw, dict) else (list(raw) if isinstance(raw, list) else [])
                                active = [o for o in seq if getattr(o, "status", "").value == "active" or "active" in str(getattr(o, "status", "")).lower()]
                            except Exception:
                                active = []

                        if active:
                            obj = active[0]
                            objective_id = getattr(obj, "objective_id", None) or getattr(obj, "id", None) or ""
                            if not objective_id and isinstance(obj, dict):
                                objective_id = obj.get("objective_id") or obj.get("id") or ""

                            # Snapshot before for outcome scoring
                            before_pending = 0
                            try:
                                if hasattr(planner, "get_objective_progress") and objective_id:
                                    prog = planner.get_objective_progress(objective_id) or {}
                                    before_pending = int(prog.get("task_statuses", {}).get("pending", 0) or 0)
                            except Exception:
                                pass

                            # Breakdown only if no planned tasks exist yet.
                            task_ids = getattr(obj, "tasks", None) if obj is not None else None
                            if (not task_ids) and isinstance(obj, object) and hasattr(planner, "breakdown_objective"):
                                import asyncio
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    created_ids = loop.run_until_complete(planner.breakdown_objective(objective_id, strategy="hierarchical"))
                                    tasks_created = len(created_ids or [])
                                finally:
                                    loop.close()

                            # Submit planned tasks to runtime loop.
                            try:
                                if hasattr(planner, "submit_tasks_to_runtime") and objective_id:
                                    submitted_map = planner.submit_tasks_to_runtime(objective_id=objective_id)
                                    submitted = len(submitted_map or {})
                            except Exception:
                                submitted = 0

                            # Store an outcome score that influences module priority.
                            state_changed = (tasks_created > 0 or submitted > 0)
                            if submitted > 0:
                                score = 1.0
                            elif tasks_created > 0:
                                score = 0.6
                            elif before_pending > 0:
                                score = 0.3
                            else:
                                score = 0.1

                            self._mistral_outcome_boost["work_on_objective"] = {"cycles": 3, "value": 4.0 * score}
                            self._last_work_on_objective_score = score

                            logger.info(
                                "[Outcome] work_on_objective objective_id=%s tasks_created=%d submitted=%d score=%.2f changed=%s",
                                objective_id,
                                tasks_created,
                                submitted,
                                score,
                                state_changed,
                            )
                            action_meaningful_success = bool(state_changed)
                            self._autonomy_last_advanced = bool(state_changed)
                            if not state_changed:
                                logger.info(
                                    "[Outcome] work_on_objective no-op (tasks_created=0, changed=False) — treated as low-value for cooldowns"
                                )
                                try:
                                    from .planner_readiness import record_autonomy_noop_outcome

                                    record_autonomy_noop_outcome(
                                        "work_on_objective",
                                        reason="tasks_created=0_submitted=0_changed=False",
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    from .planner_readiness import clear_autonomy_noop_streak

                                    clear_autonomy_noop_streak("work_on_objective")
                                except Exception:
                                    pass
                            try:
                                from .mission_autonomy import mission_autonomy_feedback_work_objective

                                mission_autonomy_feedback_work_objective(
                                    state_changed=bool(state_changed),
                                    tasks_created=int(tasks_created),
                                    submitted=int(submitted),
                                )
                            except Exception:
                                pass
                            self.memory.remember(
                                f"[Autonomy] work_on_objective: objective={objective_id} tasks_created={tasks_created} submitted={submitted} score={score:.2f}",
                                category="autonomy",
                                priority=0.6,
                            )
                        else:
                            self.memory.remember("[Autonomy] work_on_objective: no active objectives found", category="autonomy", priority=0.5)
                            try:
                                from .planner_readiness import record_autonomy_noop_outcome

                                record_autonomy_noop_outcome("work_on_objective", reason="no_active_objectives")
                            except Exception:
                                pass
                    else:
                        self.memory.remember("[Autonomy] work_on_objective failed: longterm_planner not wired", category="error", priority=0.6)
                        try:
                            from .planner_readiness import record_autonomy_noop_outcome

                            record_autonomy_noop_outcome("work_on_objective", reason="planner_not_wired")
                        except Exception:
                            pass
                    self._module_last_invoked["longterm_planner"] = datetime.datetime.now().isoformat()
                except Exception as e:
                    logger.debug("Autonomy work_on_objective: %s", e)
                    self.memory.remember(f"[Autonomy] work_on_objective error: {e}", category="error", priority=0.7)
            elif isinstance(action, str) and action.startswith("use_capability/"):
                from .capability_execution import execute_capability_kind, resolve_exec_target

                resolved = resolve_exec_target(self, action, next_result.get("metadata"))
                ok_exec = False
                ex: Dict[str, Any] = {}
                if resolved:
                    rk, rn = resolved
                    pdc = self._pre_decision_context or {}
                    ctx = (pdc.get("task_context") or "").strip()
                    if len(ctx) < 4 or "idle exploration" in ctx.lower():
                        ctx = ""
                    if len(ctx) < 4:
                        try:
                            am = self.missions.get_active_missions()
                            if am:
                                ctx = str(am[0].get("name", ""))[:400]
                        except Exception:
                            pass
                    if len(ctx) < 4:
                        ctx = "autonomy_capability_run"
                    from .routing_task_type import infer_canonical_routing_task_type

                    rt_auto, rsn_auto = infer_canonical_routing_task_type(
                        ctx, extra_context="autonomy_use_capability"
                    )
                    logger.info(
                        "[Autonomy] routing_task_type inferred=%s reason=%s context_sample=%s",
                        rt_auto,
                        rsn_auto,
                        (ctx or "")[:200],
                    )
                    structured = {
                        "task_type": rt_auto,
                        "objective": ctx[:500],
                        "payload": {
                            "source": "run_autonomous_cycle",
                            "format_version": 1,
                            "routing_inference": rsn_auto,
                        },
                    }
                    inp_kw: Dict[str, Any] = {
                        "task": structured["objective"],
                        "query": structured["objective"],
                        "objective": structured["objective"],
                    }
                    if rk == "module" and rn == "task_router":
                        inp_kw["structured_task"] = structured
                    ex = execute_capability_kind(self, rk, rn, inp_kw)
                    ok_exec = bool(ex.get("success"))
                    if not ok_exec and rk == "module" and rn == "task_router":
                        try:
                            from .self_task_queue import SelfTaskQueue

                            st_cfg = self._load_self_tasking_config()
                            q2 = SelfTaskQueue(max_size=int(st_cfg.get("max_queue_size", 24)))
                            pend = q2.list_pending_sorted()
                            if pend:
                                tid_fb = pend[0].get("task_id")
                                if tid_fb:
                                    self._run_self_generated_task(str(tid_fb), t0, None)
                                    ok_exec = True
                                    logger.info(
                                        "[Autonomy] task_router empty; fell back to execute_self_task %s",
                                        tid_fb,
                                    )
                        except Exception as tr_fb:
                            logger.debug("task_router self_task fallback: %s", tr_fb)
                    logger.info(
                        "[Autonomy] use_capability kind=%s name=%s success=%s",
                        rk,
                        rn,
                        ok_exec,
                    )
                    self.memory.remember(
                        f"[Autonomy] use_capability {rk}/{rn}: {str(ex.get('result', ex.get('error')))[:240]}",
                        category="autonomy",
                        priority=0.55,
                    )
                    mk = "tool_registry" if rk == "tool" else (rn if rk == "module" else "")
                    if mk:
                        self._module_last_invoked[mk] = datetime.datetime.now().isoformat()
                try:
                    self._orchestration_registry.log_capability_usage(
                        task=(self._pre_decision_context or {}).get("task_context", "")[:500],
                        capability_id=action,
                        capability_type="use_capability",
                        success=ok_exec,
                        quality=0.82 if ok_exec else 0.28,
                        latency_ms=(time.time() - t0) * 1000,
                        extra={"resolved": resolved, "payload": str(ex)[:400]},
                    )
                except Exception:
                    pass
                if not ok_exec:
                    self._orchestration_log_cycle(
                        action,
                        False,
                        (time.time() - t0) * 1000,
                        {"reason": "use_capability_failed", "detail": str(ex.get("error"))[:200]},
                    )
                    return result
            else:
                self._orchestration_log_cycle(
                    action,
                    False,
                    (time.time() - t0) * 1000,
                    {"reason": "no_handler_for_action"},
                )
                return result
            try:
                if action_meaningful_success:
                    self._mistral_reward_successful_action(action, self._load_mistral_decider_config())
            except Exception as re:
                logger.debug("mistral outcome reward: %s", re)
            if action in ("work_on_objective", "income_modules_pulse", "tool_registry_pulse", "process_queue"):
                try:
                    self._finish_nonadv_tracking(
                        action,
                        action_meaningful_success,
                        getattr(self, "_autonomy_last_advanced", True),
                    )
                except Exception as ne:
                    logger.debug("nonadv tracking: %s", ne)
            self._autonomy_action_times = action_times + [now]
            result["executed"] = True
            result["action"] = action
            result["reason"] = next_result.get("reason", "")
            self._last_autonomy_result = result
            self._last_action_outcome = "success" if action_meaningful_success else "failure"
            try:
                self._orchestration_log_cycle(
                    action,
                    action_meaningful_success,
                    (time.time() - t0) * 1000,
                    {
                        "reason": (next_result.get("reason") or "")[:300],
                        "override_reason": next_result.get("override_reason"),
                        "orchestration": next_result.get("mistral_orchestration"),
                        "meaningful": action_meaningful_success,
                    },
                )
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Autonomous cycle: {e}")
            self._last_action_outcome = "failure"
            try:
                lat = (time.time() - getattr(self, "_autonomy_cycle_t0", time.time())) * 1000
                self._orchestration_log_cycle(
                    locals().get("action"),
                    False,
                    lat,
                    {"error": str(e)[:200]},
                )
            except Exception:
                pass
        if not result.get("executed") and cfg.get("idle_capability_probe", True):
            self._idle_capability_probe_if_needed(cfg)
        return result

    def _load_introspection_config(self) -> Dict[str, Any]:
        """Load config/introspection.json for throttle, interval, etc."""
        cfg_path = Path(__file__).parent.parent / "config" / "introspection.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    cfg = json.load(f)
                    tm = cfg.get("throttle_minutes")
                    if tm is None or not isinstance(tm, (int, float)) or tm < 1 or tm > 120:
                        cfg["throttle_minutes"] = 30
                    return cfg
            except Exception:
                pass
        return {"enabled": True, "heartbeat_interval_beats": 10, "throttle_minutes": 30, "trigger_learning": True, "trigger_dreams": True, "suggest_objectives": True}

    def submit_task_to_loop(
        self,
        func,
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 5,
        module: str = "unknown",
        timeout: Optional[float] = None,
        dependencies: List[str] = None
    ) -> str:
        """
        Submit a task to the ElysiaLoop-Core event loop.
        
        Args:
            func: Function or coroutine to execute
            args: Function arguments
            kwargs: Function keyword arguments
            priority: Task priority (higher = more important)
            module: Module name (for routing)
            timeout: Task timeout in seconds
            dependencies: List of task IDs this task depends on
            
        Returns:
            Task ID
        """
        return self.elysia_loop.submit_task(
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            module=module,
            timeout=timeout,
            dependencies=dependencies
        )
        
    def get_loop_status(self) -> Dict[str, Any]:
        """Get ElysiaLoop-Core status."""
        return self.elysia_loop.get_status()
        
    def authorize_action(
        self,
        action: Dict[str, Any],
        user_id: str = "system",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Authorize an action through TrustEval-Action.
        
        Args:
            action: Action dictionary (type, target, parameters)
            user_id: User/component identifier
            dry_run: If True, validate without executing
            
        Returns:
            Authorization result
        """
        context = {"user_id": user_id}
        return self.trust_eval_action.authorize_action(context, action, dry_run)
        
    def evaluate_content(
        self,
        content: str,
        user_id: str = "system",
        persona_mode: Optional[str] = None,
        child_safe_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate content for safety and compliance.
        
        Args:
            content: Content text to evaluate
            user_id: User/component identifier
            persona_mode: Active persona mode
            child_safe_mode: Stricter filtering if True
            
        Returns:
            Evaluation result with verdict and flags
        """
        return self.trust_eval_content.evaluate(content, user_id, persona_mode, child_safe_mode)
        
    def evaluate_output(
        self,
        output: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate output quality through FeedbackLoop-Core.
        
        Args:
            output: Output text to evaluate
            context: Optional context (user_id, task_type, etc.)
            
        Returns:
            Complete feedback report with scores and advice
        """
        return self.feedback_loop.evaluate_output(output, context)
        
    def log_user_preference(
        self,
        user_id: str,
        preference_type: str,
        value: Any
    ):
        """
        Log a user preference for FeedbackLoop matching.
        
        Args:
            user_id: User identifier
            preference_type: Type of preference (tone, length, style, etc.)
            value: Preference value
        """
        self.feedback_loop.log_user_preference(user_id, preference_type, value)

    def log_ai_interaction(
        self,
        task_type: str,
        prompt: str,
        response: str,
        score: float = 0.5,
        system_prompt: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> Optional[str]:
        """
        Log an AI prompt–response pair for prompt evolution.
        Call this when you have a score (e.g. from evaluation or user feedback).
        
        Returns:
            record_id if logged, else None
        """
        if not self.prompt_evolver:
            return None
        return self.prompt_evolver.log_interaction(
            task_type=task_type,
            prompt=prompt,
            response=response,
            score=score,
            system_prompt=system_prompt,
            feedback=feedback,
        )

    def run_prompt_evolution(self, min_records: int = 5) -> int:
        """
        Run evolution pass: use AI to improve low-scoring prompts.
        
        Returns:
            Number of prompts evolved
        """
        if not self.prompt_evolver or not self.prompt_evolver.ask_ai:
            return 0
        n = self.prompt_evolver.run_evolution_pass(min_records=min_records)
        self._module_last_invoked["prompt_evolver"] = datetime.datetime.now().isoformat()
        return n

    def evolve_system_prompt(
        self,
        current_system_prompt: str,
        persona_name: Optional[str] = None,
    ) -> Optional[str]:
        """Use AI to suggest an improved system prompt."""
        if not self.prompt_evolver or not self.prompt_evolver.ask_ai:
            return None
        return self.prompt_evolver.evolve_system_prompt(
            current_system_prompt=current_system_prompt,
            persona_name=persona_name,
        )
        
    def filter_content(
        self,
        content: str,
        user_id: str = "system",
        **kwargs
    ) -> str:
        """
        Filter content and return sanitized version.
        
        Args:
            content: Content to filter
            user_id: User identifier
            **kwargs: Additional filtering parameters
            
        Returns:
            Filtered/sanitized content
        """
        return self.trust_eval_content.filter_content(content, user_id, **kwargs)
        
    def create_memory_snapshot(self, daily: bool = False) -> str:
        """
        Create a snapshot of current memory state.
        
        Args:
            daily: If True, create/replace daily snapshot
            
        Returns:
            Snapshot file path
        """
        # ADMIN/EXPORT: full dump for snapshot backup (intentional full-memory operation)
        memory_data = self.memory.dump_all()
        # Get vector index path if available
        vector_index_path = None
        if hasattr(self.memory, "vector_memory") and self.memory.vector_memory:
            vector_index_path = self.memory.vector_memory.index_path
            
        if daily:
            return self.memory_snapshot.create_daily_snapshot(memory_data, vector_index_path)
        else:
            return self.memory_snapshot.create_snapshot(memory_data, vector_index_path)
            
    def restore_memory_from_snapshot(self, snapshot_path: str) -> bool:
        """
        Restore memory from a snapshot file.
        
        Args:
            snapshot_path: Path to snapshot file
            
        Returns:
            True if successful
        """
        return self.memory_snapshot.restore_from_snapshot(snapshot_path, self.memory)
        
    def get_security_status(self) -> Dict[str, Any]:
        """
        Get security system status.
        
        Returns:
            Security status including violations, escalations
        """
        violations = self.trust_audit.get_violations(limit=10)
        escalations = self.trust_audit.get_escalations(limit=10)
        pending_reviews = self.trust_escalation.get_pending_reviews()
        
        return {
            "recent_violations": len(violations),
            "recent_escalations": len(escalations),
            "pending_reviews": len(pending_reviews),
            "policy_loaded": bool(self.trust_policy.current_policy),
            "audit_log_size": len(self.trust_audit.logs)
        }
    
    def _load_api_keys_from_folder(self, project_root: Path) -> None:
        """Load API keys from project's 'API keys' folder into os.environ so validation and LLM see them."""
        api_keys_dir = project_root / "API keys"
        if not api_keys_dir.exists():
            return
        key_mapping = {
            "chat gpt api key for elysia.txt": "OPENAI_API_KEY",
            "open router API key.txt": "OPENROUTER_API_KEY",
            "Cohere API key.txt": "COHERE_API_KEY",
            "Hugging face API key.txt": "HUGGINGFACE_API_KEY",
            "replicate API key.txt": "REPLICATE_API_KEY",
            "alpha vantage API.txt": "ALPHA_VANTAGE_API_KEY",
            "brave search api key.txt": "BRAVE_SEARCH_API_KEY",
        }
        for filename, env_var in key_mapping.items():
            if os.environ.get(env_var):
                continue
            filepath = api_keys_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        key = f.read().strip()
                        if key:
                            os.environ[env_var] = key
                            logger.debug(f"Loaded {env_var} from API keys folder")
                except Exception as e:
                    logger.debug(f"Could not read {filename}: {e}")

    def _validate_configuration(self) -> None:
        """
        Validate system configuration on startup.
        Logs warnings for issues but doesn't block startup unless critical.
        """
        try:
            config_path = self.config.get("config_path")
            validator = ConfigValidator(config_path=config_path)
            results = validator.validate_all()
            
            # Store validation results
            self.config_validation_results = results
            
            # Log errors (critical issues)
            if results["errors"]:
                for error in results["errors"]:
                    logger.error(
                        f"Configuration error [{error['component']}]: {error['message']}"
                    )
                    if error.get("suggestion"):
                        logger.error(f"  -> Suggestion: {error['suggestion']}")
            
            # Log warnings (non-critical issues)
            if results["warnings"]:
                for warning in results["warnings"]:
                    logger.warning(
                        f"Configuration warning [{warning['component']}]: {warning['message']}"
                    )
                    if warning.get("suggestion"):
                        logger.warning(f"  -> Suggestion: {warning['suggestion']}")
            
            # Log info (informational messages)
            if results.get("info"):
                for info in results["info"]:
                    logger.info(f"Configuration: {info['message']}")
            
            # Summary
            if results["valid"]:
                logger.info("[OK] Configuration validation passed")
            else:
                logger.warning(
                    f"⚠ Configuration has {len(results['errors'])} error(s) and "
                    f"{len(results['warnings'])} warning(s)"
                )
                logger.warning(
                    "System will continue, but some features may not work correctly"
                )
                
        except Exception as e:
            # Don't block startup if validation fails
            logger.warning(f"Configuration validation failed: {e}")
            logger.warning("Continuing with startup...")
            self.config_validation_results = {
                "valid": False,
                "errors": [{"message": f"Validation error: {e}"}],
                "warnings": [],
                "info": []
            }
    
    def get_config_validation_status(self) -> Dict[str, Any]:
        """
        Get configuration validation status.
        
        Returns:
            Dictionary with validation results
        """
        return getattr(self, 'config_validation_results', {
            "valid": True,
            "errors": [],
            "warnings": [],
            "info": []
        })
    
    def run_security_audit(self) -> Dict[str, Any]:
        """
        Run security audit.
        
        Returns:
            Dictionary with security audit results
        """
        return self.security_auditor.run_audit()
    
    def get_resource_status(self) -> Dict[str, Any]:
        """
        Get resource usage and limits status.
        
        Returns:
            Dictionary with resource status
        """
        return self.resource_monitor.get_status()
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """
        Get current resource statistics.
        
        Returns:
            Dictionary with resource usage stats
        """
        return self.resource_monitor.get_resource_stats()
    
    def get_resource_violations(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get resource limit violations.
        
        Args:
            limit: Maximum number of violations to return
            
        Returns:
            List of violations
        """
        return self.resource_monitor.get_violations(limit=limit)
    
    def _verify_startup(self) -> None:
        """
        Verify system startup and component initialization.
        Logs verification results and warnings.
        """
        try:
            verification_results = verify_guardian_startup(self)
            
            # Store verification results
            self.startup_verification = verification_results
            
            # If critical failures, log but don't crash (graceful degradation)
            if not verification_results["startup_successful"]:
                logger.error("CRITICAL: Some critical components failed to initialize")
                logger.error("System may not function correctly")
            elif not verification_results["all_components_ok"]:
                logger.warning("Some non-critical components failed to initialize")
                logger.warning("System will continue but some features may be unavailable")
            else:
                logger.info("[OK] All components initialized successfully")
            # Event-driven adversarial trigger on startup with warnings
            if verification_results.get("status") == "success_with_warnings":
                try:
                    trigger_adversarial_on_event(self, TRIGGER_STARTUP_WARNINGS, {"summary": verification_results})
                except Exception as ae:
                    logger.debug("Adversarial startup trigger: %s", ae)
                
        except Exception as e:
            # Don't crash on verification failure
            logger.warning(f"Startup verification failed: {e}")
            self.startup_verification = {
                "startup_successful": True,  # Assume OK if verification fails
                "verification_error": str(e)
            }
    
    def get_startup_verification(self) -> Dict[str, Any]:
        """
        Get startup verification results.
        
        Returns:
            Dictionary with verification results
        """
        return getattr(self, 'startup_verification', {
            "startup_successful": True,
            "verification_not_run": True
        })
    
    def _init_runtime_health_monitoring(self) -> None:
        """
        Initialize runtime health monitoring.
        Registers health checks and starts monitoring if enabled.
        """
        try:
            check_interval = self.config.get("health_check_interval", 30.0)
            self.runtime_health = RuntimeHealthMonitor(check_interval=check_interval)
            
            # Register health checks
            health_checks = create_guardian_health_checks(self)
            for name, check_func in health_checks.items():
                self.runtime_health.register_check(name, check_func)
            
            # Start monitoring if enabled
            if self.config.get("enable_runtime_health_monitoring", True):
                self.runtime_health.start_monitoring()
                logger.info("Runtime health monitoring started")
            else:
                logger.info("Runtime health monitoring disabled in config")
                
        except Exception as e:
            logger.warning(f"Failed to initialize runtime health monitoring: {e}")
            self.runtime_health = None
    
    def get_runtime_health(self) -> Dict[str, Any]:
        """
        Get current runtime health status.
        
        Returns:
            Dictionary with current health information
        """
        if not hasattr(self, 'runtime_health') or self.runtime_health is None:
            return {
                "status": "unknown",
                "message": "Runtime health monitoring not available"
            }
        return self.runtime_health.get_health()
    
    def rebuild_vector_memory_if_pending(self) -> Dict[str, Any]:
        """
        Safe recovery for deferred vector rebuilds. Call when vector_degraded or vector_rebuild_pending.
        Returns structured result: attempted, skipped, success, reason, error, memory_count.
        """
        from .memory_vector import VectorMemory, VECTOR_REBUILD_SAFE_MAX
        result: Dict[str, Any] = {
            "attempted": False,
            "skipped": False,
            "success": False,
            "reason": None,
            "error": None,
            "memory_count": None,
        }
        mem = getattr(self, "memory", None)
        if mem is None:
            result["skipped"] = True
            result["reason"] = "memory not initialized"
            return result
        if not getattr(self, "deferred_init_complete", True):
            result["skipped"] = True
            result["reason"] = "deferred init not complete"
            return result
        if getattr(self, "deferred_init_failed", False):
            result["skipped"] = True
            result["reason"] = "deferred init failed"
            return result
        vm = getattr(mem, "vector_memory", None)
        if vm is None or not isinstance(vm, VectorMemory):
            result["skipped"] = True
            result["reason"] = "no vector memory"
            return result
        if not getattr(vm, "rebuild_pending", False) and not getattr(vm, "degraded", False):
            result["skipped"] = True
            result["reason"] = "no rebuild pending or degraded"
            if hasattr(vm, "record_rebuild_outcome"):
                vm.record_rebuild_outcome("skipped", result["reason"], None)
            return result
        json_mem = getattr(mem, "json_memory", mem) if hasattr(mem, "json_memory") else mem
        if hasattr(json_mem, "load_if_needed"):
            json_mem.load_if_needed()
        kept = getattr(json_mem, "memory_log", None) or []
        memory_count = len(kept)
        result["memory_count"] = memory_count
        if memory_count > VECTOR_REBUILD_SAFE_MAX:
            result["skipped"] = True
            result["reason"] = f"memory count ({memory_count}) exceeds safe threshold ({VECTOR_REBUILD_SAFE_MAX})"
            if hasattr(vm, "record_rebuild_outcome"):
                vm.record_rebuild_outcome("skipped", result["reason"], None)
            return result
        result["attempted"] = True
        try:
            metrics = vm.rebuild_from_memories(kept, VECTOR_REBUILD_SAFE_MAX)
            success = bool(metrics.get("vector_rebuild_success", False))
            result["success"] = success
            if success:
                result["error"] = None
                result["reason"] = "rebuilt"
            else:
                result["error"] = metrics.get("error") or "rebuild failed"
                result["reason"] = metrics.get("vector_rebuild_status", "failed")
        except Exception as e:
            result["success"] = False
            result["error"] = str(e).strip()[:300]
            result["reason"] = "exception"
            if hasattr(vm, "record_rebuild_outcome"):
                vm.record_rebuild_outcome("failed", "exception", str(e)[:200])
        return result

    def _check_and_cleanup_memory(self) -> None:
        """
        Check memory usage and cleanup if needed.
        Automatically consolidates memories if count exceeds threshold.
        Runs at startup and can be called periodically.
        """
        try:
            if hasattr(self.memory, "get_memory_count"):
                memory_count = self.memory.get_memory_count(load_if_needed=True)
            elif hasattr(self.memory, "get_memory_state"):
                st = self.memory.get_memory_state(load_if_needed=True)
                memory_count = st.get("memory_count")
            else:
                return
            if memory_count is None:
                return
            memory_threshold = self.config.get("memory_cleanup_threshold", 3500)
            
            if memory_count > memory_threshold:
                logger.warning(f"[Auto-Cleanup] Memory count ({memory_count}) exceeds threshold ({memory_threshold}), performing cleanup...")
                print(f"[Auto-Cleanup] Starting memory cleanup: {memory_count} memories -> target: {memory_threshold}")
                
                # Perform consolidation on the authoritative memory object
                memory_obj = self.memory
                if hasattr(memory_obj, 'consolidate'):
                    result = memory_obj.consolidate(
                        max_memories=memory_threshold,
                        keep_recent_days=self.config.get("memory_keep_recent_days", 30)
                    )
                    
                    if "error" not in result:
                        original = result.get('original_count', 0)
                        final = result.get('final_count', 0)
                        removed = result.get('removed', 0)
                        logger.info(f"[Auto-Cleanup] Startup cleanup completed: {original} -> {final} memories (removed {removed})")
                        print(f"[Auto-Cleanup] Memory cleanup completed: {original} -> {final} (removed {removed})")
                    else:
                        logger.error(f"[Auto-Cleanup] Error: {result.get('error')}")
                else:
                    logger.warning(f"[Auto-Cleanup] Memory object does not have consolidate method")
            else:
                logger.debug(f"Memory count ({memory_count}) is within threshold ({memory_threshold})")
        except Exception as e:
            logger.warning(f"Error checking/cleaning memory: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def get_runtime_health_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get runtime health check history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of historical health check results
        """
        if not hasattr(self, 'runtime_health') or self.runtime_health is None:
            return []
        return self.runtime_health.get_history(limit=limit)
        
    def start_ui_panel(self, host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
        """
        Canonical programmatic wrapper for starting the dashboard. GuardianCore-owned
        panel should only be started via this method or from __init__ (which calls this).
        """
        if self.ui_panel is None:
            self.ui_panel = UIControlPanel(
                orchestrator=self,
                host=host,
                port=port
            )
        panel = self.ui_panel
        if panel.running or (hasattr(panel, "is_ready") and panel.is_ready()):
            logger.info("[DASHBOARD] Start skipped: control panel already running")
            return
        logger.info("[DASHBOARD] GuardianCore starting control panel via canonical wrapper")
        panel.start(debug=debug, source="GuardianCore.start_ui_panel")
        actual_host = getattr(panel, "host", host)
        actual_port = getattr(panel, "port", port)
        logger.info(f"UI Control Panel started on http://{actual_host}:{actual_port}")
        
    def stop_ui_panel(self) -> None:
        """Stop the UI Control Panel."""
        if self.ui_panel and self.ui_panel.running:
            self.ui_panel.stop()
            logger.info("UI Control Panel stopped")
    
    def shutdown(self) -> None:
        """
        Safely shutdown the Guardian system.
        """
        self.memory.remember(
            "[Guardian Core] System shutdown initiated",
            category="system",
            priority=0.9
        )
        
        # Stop UI Control Panel
        self.stop_ui_panel()
        
        # Stop ElysiaLoop-Core
        if self.elysia_loop:
            self.elysia_loop.stop()
        
        # Complete pending tasks
        active_tasks = self.tasks.get_active_tasks()
        for task in active_tasks:
            if task["priority"] >= 0.8:
                self.tasks.complete_task(task["id"])
                
        # Clear consensus votes
        self.consensus.clear_votes()
        
        # Stop monitoring
        self.monitor.stop_monitoring()
        
        # Stop resource monitoring
        if hasattr(self, 'resource_monitor'):
            self.resource_monitor.stop_monitoring()
        
        # Stop runtime health monitoring
        if hasattr(self, 'runtime_health') and self.runtime_health:
            self.runtime_health.stop_monitoring()
        
        # Apply trust decay
        self.trust.decay_all(0.05)
        
        self.memory.remember(
            "[Guardian Core] System shutdown complete",
            category="system",
            priority=0.9
        )
        
        self._running = False
    
    def _read_control_task(self) -> Optional[str]:
        """
        Read CURRENT_TASK from CONTROL.md.
        
        Returns:
            Task ID (e.g., "TASK-0001") or None if NONE/missing
        """
        try:
            if not self.control_path.exists():
                return None
            
            with open(self.control_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse CURRENT_TASK: <value>
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('CURRENT_TASK:'):
                    # Extract value after colon
                    value = line.split(':', 1)[1].strip()
                    if value.upper() == 'NONE':
                        return None
                    return value
            
            # No CURRENT_TASK found
            return None
        except Exception as e:
            logger.warning(f"Error reading CONTROL.md: {e}")
            return None
    
    def load_task_contract(self, task_id: str) -> Dict[str, Any]:
        """
        Load task contract from TASKS/{task_id}.md.
        
        Args:
            task_id: Task ID (e.g., "TASK-0001")
            
        Returns:
            Dict with status, task_id, and either error details or contract info
        """
        task_file = self.tasks_dir / f"{task_id}.md"
        
        if not task_file.exists():
            return {
                "status": "error",
                "code": "TASK_NOT_FOUND",
                "task_id": task_id,
                "detail": f"Task file not found: {task_file}"
            }
        
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Compute hash
            contract_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            
            # Get preview (first ~20 lines)
            lines = content.split('\n')
            contract_preview = '\n'.join(lines[:20])
            
            # Extract directives (TASK_TYPE and others for APPLY_MUTATION)
            task_type = None
            task_type_count = 0
            directives = {}
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('TASK_TYPE:'):
                    task_type_count += 1
                    if task_type_count == 1:
                        # Extract value after colon
                        task_type = line.split(':', 1)[1].strip()
                elif line.startswith('MUTATION_FILE:'):
                    directives['MUTATION_FILE'] = line.split(':', 1)[1].strip()
                elif line.startswith('ALLOW_GOVERNANCE_MUTATION:'):
                    directives['ALLOW_GOVERNANCE_MUTATION'] = line.split(':', 1)[1].strip()
                elif line.startswith('REQUEST_ID:'):
                    directives['REQUEST_ID'] = line.split(':', 1)[1].strip()
                elif line.startswith('ANALYSIS_KIND:'):
                    directives['ANALYSIS_KIND'] = line.split(':', 1)[1].strip()
                elif line.startswith('OUTPUT_REPORT:'):
                    directives['OUTPUT_REPORT'] = line.split(':', 1)[1].strip()
                elif line.startswith('INPUTS:'):
                    # INPUTS is a YAML-like list - parse multi-line format
                    inputs_list = []
                    # Find the line index in the full content
                    all_lines = content.split('\n')
                    current_idx = None
                    for idx, l in enumerate(all_lines):
                        if l.strip() == line:
                            current_idx = idx
                            break
                    
                    if current_idx is not None:
                        # Parse subsequent lines until we hit another directive or end
                        i = current_idx + 1
                        while i < len(all_lines):
                            next_line_raw = all_lines[i]
                            next_line_stripped = next_line_raw.strip()
                            
                            # Stop if we hit another directive (uppercase word followed by colon at start of line)
                            if next_line_stripped and ':' in next_line_stripped:
                                potential_directive = next_line_stripped.split(':')[0].strip()
                                if potential_directive.isupper() and potential_directive in ['TASK_TYPE', 'ANALYSIS_KIND', 'OUTPUT_REPORT', 'MUTATION_FILE', 'ALLOW_GOVERNANCE_MUTATION', 'REQUEST_ID']:
                                    break
                            
                            # Collect list items (lines starting with '-' after stripping)
                            if next_line_stripped.startswith('-'):
                                # Parse YAML-like list item: "- type: repo" or "- type: file\n    value: path"
                                item_dict = {}
                                # Extract type from this line (remove leading '-')
                                type_line = next_line_stripped[1:].strip()  # Remove '-'
                                if 'type:' in type_line:
                                    item_dict['type'] = type_line.split('type:', 1)[1].strip()
                                
                                # Check next line for value (indented continuation - has leading spaces)
                                if i + 1 < len(all_lines):
                                    next_next_raw = all_lines[i + 1]
                                    next_next_stripped = next_next_raw.strip()
                                    # If next line is indented (starts with spaces) and contains 'value:', it's a continuation
                                    if next_next_raw and next_next_raw[0] in ' \t' and 'value:' in next_next_stripped:
                                        item_dict['value'] = next_next_stripped.split('value:', 1)[1].strip()
                                        i += 1  # Skip the value line
                                
                                # Also check if value is on same line (e.g., "- type: repo value: .")
                                if 'value:' in type_line and 'value' not in item_dict:
                                    item_dict['value'] = type_line.split('value:', 1)[1].strip()
                                
                                # If we have both type and value, add to list
                                if item_dict.get('type') and item_dict.get('value'):
                                    inputs_list.append(item_dict)
                            
                            i += 1
                    directives['INPUTS'] = inputs_list
            
            # Validate TASK_TYPE
            if task_type_count == 0:
                return {
                    "status": "error",
                    "code": "TASK_TYPE_INVALID",
                    "task_id": task_id,
                    "detail": "Missing TASK_TYPE directive"
                }
            elif task_type_count > 1:
                return {
                    "status": "error",
                    "code": "TASK_TYPE_INVALID",
                    "task_id": task_id,
                    "detail": "Multiple TASK_TYPE directives found (exactly one required)"
                }
            elif task_type not in ["RUN_ACCEPTANCE", "CLEAR_CURRENT_TASK", "APPLY_MUTATION", "READ_ONLY_ANALYSIS"]:
                return {
                    "status": "error",
                    "code": "TASK_TYPE_INVALID",
                    "task_id": task_id,
                    "detail": f"Unknown TASK_TYPE: {task_type}. Allowed: RUN_ACCEPTANCE, CLEAR_CURRENT_TASK, APPLY_MUTATION, READ_ONLY_ANALYSIS"
                }
            
            # For APPLY_MUTATION, validate additional directives
            if task_type == "APPLY_MUTATION":
                # Validate required directives
                if 'MUTATION_FILE' not in directives:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": "Missing MUTATION_FILE directive for APPLY_MUTATION"
                    }
                if 'ALLOW_GOVERNANCE_MUTATION' not in directives:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": "Missing ALLOW_GOVERNANCE_MUTATION directive for APPLY_MUTATION"
                    }
                
                # Validate MUTATION_FILE path
                mutation_file = directives['MUTATION_FILE']
                if not mutation_file.startswith('MUTATIONS/'):
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"MUTATION_FILE must start with MUTATIONS/, got: {mutation_file}"
                    }
                if not mutation_file.endswith('.json'):
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"MUTATION_FILE must end with .json, got: {mutation_file}"
                    }
                if '..' in mutation_file:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"MUTATION_FILE must not contain .. segments, got: {mutation_file}"
                    }
                
                # Validate ALLOW_GOVERNANCE_MUTATION value
                allow_gov = directives['ALLOW_GOVERNANCE_MUTATION'].lower()
                if allow_gov not in ['true', 'false']:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"ALLOW_GOVERNANCE_MUTATION must be 'true' or 'false', got: {allow_gov}"
                    }
            
            # For READ_ONLY_ANALYSIS, validate required directives
            if task_type == "READ_ONLY_ANALYSIS":
                # Validate required directives
                if 'ANALYSIS_KIND' not in directives:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": "Missing ANALYSIS_KIND directive for READ_ONLY_ANALYSIS"
                    }
                if 'OUTPUT_REPORT' not in directives:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": "Missing OUTPUT_REPORT directive for READ_ONLY_ANALYSIS"
                    }
                
                # Validate ANALYSIS_KIND
                analysis_kind = directives['ANALYSIS_KIND']
                if analysis_kind not in ['REPO_SUMMARY', 'FILE_SET', 'URL_RESEARCH']:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"ANALYSIS_KIND must be one of: REPO_SUMMARY, FILE_SET, URL_RESEARCH. Got: {analysis_kind}"
                    }
                
                # Validate OUTPUT_REPORT path
                output_report = directives['OUTPUT_REPORT']
                if not output_report.startswith('REPORTS/'):
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"OUTPUT_REPORT must start with REPORTS/, got: {output_report}"
                    }
                if not output_report.endswith('.json'):
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"OUTPUT_REPORT must end with .json, got: {output_report}"
                    }
                if '..' in output_report:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": f"OUTPUT_REPORT must not contain .. segments, got: {output_report}"
                    }
                
                # Validate INPUTS (must be non-empty)
                # INPUTS is parsed as a list in directives
                if 'INPUTS' not in directives or not directives['INPUTS']:
                    return {
                        "status": "error",
                        "code": "TASK_CONTRACT_INVALID",
                        "task_id": task_id,
                        "detail": "Missing or empty INPUTS directive for READ_ONLY_ANALYSIS"
                    }
            
            return {
                "status": "ready",
                "task_id": task_id,
                "contract_hash": contract_hash,
                "contract_preview": contract_preview,
                "task_type": task_type,
                "directives": directives if task_type in ["APPLY_MUTATION", "READ_ONLY_ANALYSIS"] else {}
            }
        except Exception as e:
            return {
                "status": "error",
                "code": "TASK_LOAD_ERROR",
                "task_id": task_id,
                "detail": str(e)
            }
    
    def run_once(self) -> Dict[str, Any]:
        """
        Execute a single deterministic iteration of the core loop.
        
        This method provides a testable entrypoint for one cycle of core operations
        without infinite loops. It performs:
        - CONTROL.md parsing and task routing
        - System health check
        - Task processing (if any pending)
        - Trust decay (minimal)
        - Status update
        
        Returns:
            Dict with iteration results (status, current_task, etc.)
            Status values: "idle", "ready", "error"
        """
        if not self._initialized:
            raise RuntimeError("Core not initialized. Call _initialize_system() first.")
        
        # Parse CONTROL.md to get current task
        current_task = self._read_control_task()
        
        # Initialize result structure
        iteration_result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "idle",
            "current_task": None,
            "tasks_processed": 0,
            "health_checks": []
        }
        
        # Handle CONTROL.md missing or unreadable
        if current_task is None:
            # Check if CONTROL.md exists
            if not self.control_path.exists():
                iteration_result.update({
                    "status": "error",
                    "code": "CONTROL_MISSING",
                    "detail": f"CONTROL.md not found at {self.control_path}"
                })
                return iteration_result
            
            # CURRENT_TASK is NONE (idle state)
            iteration_result["status"] = "idle"
            iteration_result["current_task"] = None
        else:
            # Load task contract
            contract_result = self.load_task_contract(current_task)
            
            if contract_result["status"] == "error":
                # Task file missing or error loading
                iteration_result.update({
                    "status": "error",
                    "code": contract_result["code"],
                    "detail": contract_result.get("detail", "Unknown error"),
                    "current_task": current_task
                })
                return iteration_result
            else:
                # Task loaded successfully - now execute it
                task_type = contract_result.get("task_type")
                directives = contract_result.get("directives", {})
                if task_type:
                    # Execute task based on type
                    execution_result = self._execute_task(current_task, task_type, directives)
                    execution_status = execution_result.get("status", "error")
                    # Outcome scoring for module priority feedback (simple + deterministic).
                    outcome_score = 0.0
                    state_changed = False
                    if execution_status == "ok":
                        outcome_score = 1.0
                        state_changed = True
                    elif execution_status in ("denied", "needs_review"):
                        outcome_score = 0.2
                        state_changed = False
                    else:
                        outcome_score = 0.0
                        state_changed = False
                    
                    if execution_status == "ok":
                        # Task executed successfully
                        iteration_result.update({
                            "status": "ok",
                            "current_task": current_task,
                            "task_type": task_type,
                            "outcome": execution_result.get("outcome"),
                            "exit_code": execution_result.get("exit_code")
                        })
                    elif execution_status in ("denied", "needs_review"):
                        # Preserve deny/review statuses (don't overwrite with "error")
                        iteration_result.update({
                            "status": execution_status,
                            "current_task": current_task,
                            "task_type": task_type,
                            "code": execution_result.get("code"),
                            "detail": execution_result.get("detail"),
                            "request_id": execution_result.get("request_id"),
                            "reason_code": execution_result.get("reason_code"),
                            "outcome": execution_result.get("outcome"),
                            "summary": execution_result.get("summary")
                        })
                    else:
                        # Task execution failed
                        iteration_result.update({
                            "status": "error",
                            "code": execution_result.get("code", "TASK_EXECUTION_ERROR"),
                            "detail": execution_result.get("detail", "Unknown error"),
                            "current_task": current_task,
                            "task_type": task_type
                        })
                else:
                    # Task loaded but no task_type (should not happen if validation worked)
                    iteration_result.update({
                        "status": "ready",
                        "current_task": current_task,
                        "contract_hash": contract_result["contract_hash"],
                        "contract_preview": contract_result["contract_preview"]
                    })

                # Feed outcome score into module priority reinforcement.
                # (Runs only when we attempted a task; safe to skip when task_type is missing.)
                try:
                    if task_type:
                        self._mistral_outcome_boost["execute_task"] = {"cycles": 3, "value": 4.0 * float(outcome_score)}
                        self._last_execute_task_score = outcome_score
                        logger.info(
                            "[Outcome] execute_task task_type=%s status=%s score=%.2f changed=%s",
                            task_type,
                            execution_status,
                            outcome_score,
                            state_changed,
                        )
                        self.memory.remember(
                            f"[Outcome] execute_task score={outcome_score:.2f} changed={state_changed} status={execution_status}",
                            category="autonomy",
                            priority=0.55,
                        )
                        try:
                            from .planner_readiness import clear_autonomy_noop_streak, record_autonomy_noop_outcome

                            if state_changed:
                                clear_autonomy_noop_streak("execute_task")
                            elif execution_status not in ("ok",):
                                record_autonomy_noop_outcome(
                                    "execute_task",
                                    reason=f"run_once_no_progress status={execution_status}",
                                )
                        except Exception:
                            pass
                except Exception:
                    pass
        
        # Run safety check (non-blocking, deterministic)
        try:
            safety_result = self.run_safety_check()
            iteration_result["health_checks"].append(safety_result)
        except Exception as e:
            logger.warning(f"Safety check failed in run_once: {e}")
            iteration_result["health_checks"].append({"error": str(e)})
        
        # Process one high-priority task if available (deterministic, no infinite loop)
        try:
            active_tasks = self.tasks.get_active_tasks()
            if active_tasks:
                # Sort by priority and process highest priority task
                sorted_tasks = sorted(active_tasks, key=lambda t: t.get("priority", 0.5), reverse=True)
                top_task = sorted_tasks[0]
                # Just mark as processed (don't actually execute task logic to keep it deterministic)
                iteration_result["tasks_processed"] = 1
                iteration_result["top_task"] = top_task.get("name", "unknown")
        except Exception as e:
            logger.warning(f"Task processing failed in run_once: {e}")
        
        # Minimal trust decay (deterministic, small amount)
        try:
            self.trust.decay_all(0.01)  # Small decay per iteration
        except Exception as e:
            logger.warning(f"Trust decay failed in run_once: {e}")
        
        # Update system status
        iteration_result["system_status"] = {
            "uptime": (datetime.datetime.now() - self.start_time).total_seconds(),
            "initialized": self._initialized,
            "running": self._running
        }
        
        return iteration_result
    
    def _execute_task(self, task_id: str, task_type: str, directives: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Execute a task based on its type.
        
        Args:
            task_id: Task ID (e.g., "TASK-0001")
            task_type: Task type (RUN_ACCEPTANCE, CLEAR_CURRENT_TASK, APPLY_MUTATION)
            directives: Optional task directives (required for APPLY_MUTATION)
            
        Returns:
            Dict with status, outcome, and optional exit_code
        """
        if task_type == "RUN_ACCEPTANCE":
            return self._execute_run_acceptance(task_id)
        elif task_type == "CLEAR_CURRENT_TASK":
            return self._execute_clear_current_task(task_id)
        elif task_type == "APPLY_MUTATION":
            if not directives:
                return {
                    "status": "error",
                    "code": "TASK_CONTRACT_INVALID",
                    "detail": "APPLY_MUTATION requires directives"
                }
            return self._execute_apply_mutation(task_id, directives)
        elif task_type == "READ_ONLY_ANALYSIS":
            if not directives:
                return {
                    "status": "error",
                    "code": "TASK_CONTRACT_INVALID",
                    "detail": "READ_ONLY_ANALYSIS requires directives"
                }
            return self._execute_read_only_analysis(task_id, directives)
        else:
            return {
                "status": "error",
                "code": "TASK_TYPE_INVALID",
                "detail": f"Unknown task type: {task_type}"
            }
    
    def _execute_run_acceptance(self, task_id: str) -> Dict[str, Any]:
        """
        Execute RUN_ACCEPTANCE task by running the acceptance script via SubprocessRunner.
        
        All subprocess execution must go through SubprocessRunner gateway to enforce
        "all external power goes through gateways" doctrine.
        
        Args:
            task_id: Task ID
            
        Returns:
            Dict with status, outcome, exit_code
        """
        from .external import TrustDeniedError, TrustReviewRequiredError
        
        try:
            # Get acceptance script path (relative to project root or mutations_dir parent)
            # Use mutations_dir.parent as project root (consistent with APPLY_MUTATION)
            project_root = self.mutations_dir.parent
            acceptance_script = project_root / "scripts" / "acceptance.ps1"
            
            if not acceptance_script.exists():
                return {
                    "status": "error",
                    "code": "ACCEPTANCE_SCRIPT_NOT_FOUND",
                    "detail": f"Acceptance script not found: {acceptance_script}"
                }
            
            # Build fixed command list (no user-controlled input)
            # PowerShell command: powershell -NoProfile -ExecutionPolicy Bypass -File <ABS_PATH>
            command = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(acceptance_script.resolve())  # Absolute path
            ]
            
            # Run acceptance script via SubprocessRunner (single subprocess surface)
            try:
                result = self.subprocess_runner.run_command(
                    command=command,
                    caller_identity="GuardianCore",
                    task_id=task_id,
                    request_id=None,  # No replay for acceptance (it's a known safe command)
                    timeout=300  # 5 minute timeout for acceptance script
                )
                
                # SubprocessRunner returns dict with stdout, stderr, returncode
                return {
                    "status": "ok",
                    "task_id": task_id,
                    "outcome": "acceptance_ran",
                    "exit_code": result.get("returncode", -1)
                }
            except TrustReviewRequiredError as e:
                # Review required - return needs_review status
                return {
                    "status": "needs_review",
                    "task_id": task_id,
                    "request_id": e.request_id,
                    "outcome": "acceptance_review_required",
                    "summary": e.summary
                }
            except TrustDeniedError as e:
                # Denied - return denied status
                return {
                    "status": "denied",
                    "task_id": task_id,
                    "code": "ACCEPTANCE_DENIED",
                    "detail": str(e),
                    "reason_code": e.reason
                }
        except Exception as e:
            return {
                "status": "error",
                "code": "ACCEPTANCE_EXECUTION_ERROR",
                "detail": str(e)
            }
    
    def _execute_clear_current_task(self, task_id: str) -> Dict[str, Any]:
        """
        Execute CLEAR_CURRENT_TASK by atomically setting CONTROL.md to NONE.
        
        Args:
            task_id: Task ID
            
        Returns:
            Dict with status, outcome
        """
        try:
            # Atomic write: write to temp file, then replace
            temp_file = self.control_path.with_suffix('.tmp')
            
            # Read existing content (if exists)
            existing_content = ""
            if self.control_path.exists():
                with open(self.control_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            
            # Replace CURRENT_TASK line
            lines = existing_content.split('\n')
            new_lines = []
            replaced = False
            for line in lines:
                if line.strip().startswith('CURRENT_TASK:'):
                    new_lines.append('CURRENT_TASK: NONE')
                    replaced = True
                else:
                    new_lines.append(line)
            
            # If no CURRENT_TASK found, add it at the beginning
            if not replaced:
                new_lines.insert(0, 'CURRENT_TASK: NONE')
            
            # Write to temp file
            with open(temp_file, 'w', encoding='utf-8') as f:
                content = '\n'.join(new_lines)
                f.write(content)
                if not content.endswith('\n'):
                    f.write('\n')
            
            # Atomic replace
            import os
            os.replace(temp_file, self.control_path)
            
            return {
                "status": "ok",
                "task_id": task_id,
                "outcome": "task_cleared"
            }
        except Exception as e:
            return {
                "status": "error",
                "code": "CLEAR_TASK_ERROR",
                "detail": str(e)
            }
    
    def _execute_apply_mutation(self, task_id: str, directives: Dict[str, str]) -> Dict[str, Any]:
        """
        Execute APPLY_MUTATION task by loading mutation payload and applying via MutationEngine.
        
        Implements preflight phase to prevent partial mutation applies.
        
        Args:
            task_id: Task ID
            directives: Task directives (MUTATION_FILE, ALLOW_GOVERNANCE_MUTATION, REQUEST_ID)
            
        Returns:
            Dict with status, outcome, and mutation results
        """
        from .mutation import MutationDeniedError, MutationReviewRequiredError, MutationApplyError, PROTECTED_GOVERNANCE_PATHS, PROTECTED_DIRECTORIES
        from .trust import GOVERNANCE_MUTATION
        
        try:
            # Load mutation file
            mutation_file_path = directives.get('MUTATION_FILE')
            if not mutation_file_path:
                return {
                    "status": "error",
                    "code": "TASK_CONTRACT_INVALID",
                    "task_id": task_id,
                    "detail": "Missing MUTATION_FILE directive"
                }
            
            # Resolve mutation file path (relative to mutations_dir)
            if mutation_file_path.startswith('MUTATIONS/'):
                mutation_file_path = mutation_file_path[10:]  # Remove 'MUTATIONS/' prefix
            
            mutation_file = self.mutations_dir / mutation_file_path
            
            if not mutation_file.exists():
                return {
                    "status": "error",
                    "code": "MUTATION_FILE_NOT_FOUND",
                    "task_id": task_id,
                    "detail": f"Mutation file not found: {mutation_file}"
                }
            
            # Parse JSON payload
            import json
            try:
                with open(mutation_file, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "code": "MUTATION_PAYLOAD_INVALID",
                    "task_id": task_id,
                    "detail": f"Invalid JSON in mutation file: {e}"
                }
            
            # Validate payload schema
            if not isinstance(payload, dict):
                return {
                    "status": "error",
                    "code": "MUTATION_PAYLOAD_INVALID",
                    "task_id": task_id,
                    "detail": "Payload must be a JSON object"
                }
            
            if 'touched_paths' not in payload or 'changes' not in payload:
                return {
                    "status": "error",
                    "code": "MUTATION_PAYLOAD_INVALID",
                    "task_id": task_id,
                    "detail": "Payload must contain 'touched_paths' and 'changes'"
                }
            
            touched_paths = payload.get('touched_paths', [])
            changes = payload.get('changes', [])
            
            # Validate touched_paths matches changes[].path
            change_paths = set(change.get('path') for change in changes if isinstance(change, dict) and 'path' in change)
            touched_paths_set = set(touched_paths)
            
            if change_paths != touched_paths_set:
                return {
                    "status": "error",
                    "code": "MUTATION_PAYLOAD_INVALID",
                    "task_id": task_id,
                    "detail": f"touched_paths {touched_paths_set} does not match changes paths {change_paths}"
                }
            
            # Validate path safety (no .., no absolute paths)
            # Use mutations_dir's parent as project root
            project_root = self.mutations_dir.parent
            
            for path in touched_paths:
                if '..' in path or Path(path).is_absolute():
                    return {
                        "status": "error",
                        "code": "MUTATION_PAYLOAD_INVALID",
                        "task_id": task_id,
                        "detail": f"Invalid path (no .. or absolute paths allowed): {path}"
                    }
                # Check if path would be outside repo root
                resolved_path = (project_root / path).resolve()
                if not str(resolved_path).startswith(str(project_root.resolve())):
                    return {
                        "status": "error",
                        "code": "MUTATION_PAYLOAD_INVALID",
                        "task_id": task_id,
                        "detail": f"Path would be outside repo root: {path}"
                    }
            
            # Get allow_governance_mutation from directive
            allow_gov_str = directives.get('ALLOW_GOVERNANCE_MUTATION', 'false').lower()
            allow_governance_mutation = allow_gov_str == 'true'
            
            # Get request_id for replay (optional)
            request_id = directives.get('REQUEST_ID')
            
            # PREFLIGHT PHASE: Check all paths before any writes
            # STEP 1: Validate path safety for ALL paths (using MutationEngine's validation)
            # This must happen BEFORE protected path checks or TrustMatrix gating
            invalid_paths = []
            validated_paths = {}  # Map original path -> (resolved_path, normalized_rel_path)
            
            for path in touched_paths:
                try:
                    # Use MutationEngine's path validation
                    resolved_path, normalized_rel_path = self.mutation._validate_and_resolve_path(path)
                    validated_paths[path] = (resolved_path, normalized_rel_path)
                except MutationDeniedError as e:
                    # Path validation failed - collect for error reporting
                    invalid_paths.append({
                        "path": path,
                        "reason": e.reason,
                        "context": e.context
                    })
            
            # If any path is invalid, deny entire batch before any writes
            if invalid_paths:
                return {
                    "status": "denied",
                    "task_id": task_id,
                    "code": "MUTATION_DENIED",
                    "detail": "path_validation_failed",
                    "reason_code": "PATH_TRAVERSAL_BLOCKED",
                    "invalid_paths": invalid_paths
                }
            
            # STEP 2: Use normalized relative paths for protected path checks
            # Compute sorted touched_paths using normalized paths for deterministic hashing
            normalized_touched_paths = [validated_paths[p][1] for p in touched_paths]
            sorted_touched_paths = sorted(normalized_touched_paths)
            
            # Check if any path is protected (using MutationEngine's protection logic)
            def _is_protected_path(filename: str) -> bool:
                """Check if a file path is protected (same logic as MutationEngine)"""
                normalized = filename.replace("\\", "/")
                
                # Check exact matches in protected paths
                for protected in PROTECTED_GOVERNANCE_PATHS:
                    if normalized.endswith(protected) or normalized == protected:
                        return True
                
                # Check if file is in protected directory
                for protected_dir in PROTECTED_DIRECTORIES:
                    if normalized.startswith(protected_dir):
                        return True
                
                return False
            
            # Check all paths for protection
            protected_paths = [path for path in sorted_touched_paths if _is_protected_path(path)]
            
            # PREFLIGHT: If ALLOW_GOVERNANCE_MUTATION=false and any path is protected, deny immediately
            if not allow_governance_mutation and protected_paths:
                return {
                    "status": "denied",
                    "task_id": task_id,
                    "code": "MUTATION_DENIED",
                    "detail": "protected_path_without_override",
                    "reason_code": "PROTECTED_PATH_WITHOUT_OVERRIDE",
                    "protected_paths": protected_paths
                }
            
            # PREFLIGHT: If ALLOW_GOVERNANCE_MUTATION=true, check TrustMatrix once for entire batch
            if allow_governance_mutation and protected_paths:
                # Build context for trust gate (same as MutationEngine)
                gate_context = {
                    "component": "MutationEngine",
                    "action": GOVERNANCE_MUTATION,
                    "touched_paths": sorted_touched_paths,
                    "override_flag": True,
                    "caller_identity": "GuardianCore",
                    "task_id": task_id
                }
                
                # Check for replay: if request_id provided and approved, bypass review
                approved_replay = False
                if request_id and self.mutation.approval_store:
                    if self.mutation.approval_store.is_approved(request_id, context=gate_context):
                        # Approved request with matching context - proceed (skip gate check)
                        approved_replay = True
                    else:
                        # Request ID provided but not approved or context mismatch
                        return {
                            "status": "denied",
                            "task_id": task_id,
                            "code": "MUTATION_DENIED",
                            "detail": "APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                            "reason_code": "APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH"
                        }
                
                # Normal gate check (only if no approved request_id)
                if not approved_replay:
                    if not self.mutation.trust_matrix:
                        return {
                            "status": "denied",
                            "task_id": task_id,
                            "code": "MUTATION_DENIED",
                            "detail": "TrustMatrix not available",
                            "reason_code": "TRUST_MATRIX_NOT_AVAILABLE"
                        }
                    
                    decision = self.mutation.trust_matrix.validate_trust_for_action(
                        "MutationEngine",
                        GOVERNANCE_MUTATION,
                        context=gate_context
                    )
                    
                    if decision.decision == "deny":
                        # TrustMatrix denied - return immediately (no writes)
                        return {
                            "status": "denied",
                            "task_id": task_id,
                            "code": "MUTATION_DENIED",
                            "detail": decision.message,
                            "reason_code": decision.reason_code
                        }
                    elif decision.decision == "review":
                        # Borderline trust - enqueue review request (no writes)
                        if self.mutation.review_queue:
                            review_request_id = self.mutation.review_queue.enqueue(
                                component="MutationEngine",
                                action=GOVERNANCE_MUTATION,
                                context=gate_context
                            )
                            
                            summary = f"Governance mutation to {', '.join(sorted_touched_paths)} requires review (trust: {decision.risk_score:.2f})"
                            
                            return {
                                "status": "needs_review",
                                "task_id": task_id,
                                "request_id": review_request_id,
                                "outcome": "mutation_review_required",
                                "summary": summary
                            }
                        else:
                            # No review queue - treat as deny
                            return {
                                "status": "denied",
                                "task_id": task_id,
                                "code": "MUTATION_DENIED",
                                "detail": decision.message,
                                "reason_code": decision.reason_code
                            }
                    # decision == "allow" - proceed to apply
            
            # PREFLIGHT PASSED: Apply entire batch (all files)
            # Use validated paths (already normalized and resolved)
            changed_files = []
            backup_paths = []
            summaries = []
            
            for change in changes:
                original_file_path = change.get('path')
                file_content = change.get('content', '')
                
                # Use validated path (already resolved and normalized)
                if original_file_path not in validated_paths:
                    # Should not happen after preflight, but defensive
                    return {
                        "status": "error",
                        "task_id": task_id,
                        "code": "MUTATION_APPLY_ERROR",
                        "detail": f"Path not validated in preflight: {original_file_path}"
                    }
                
                resolved_path, normalized_rel_path = validated_paths[original_file_path]
                
                # Use normalized relative path for MutationEngine.apply() (it will validate again internally)
                # MutationEngine.apply() expects relative path and will validate it again
                file_path = normalized_rel_path
                
                # Call MutationEngine.apply()
                # Note: For protected paths with allow_governance_mutation=True, we've already checked TrustMatrix
                # MutationEngine will still check, but it should pass (or we pass request_id for replay)
                try:
                    result = self.mutation.apply(
                        str(file_path),
                        file_content,
                        origin="GuardianCore",
                        allow_governance_mutation=allow_governance_mutation,
                        request_id=request_id,
                        caller_identity="GuardianCore",
                        task_id=task_id
                    )
                    
                    # Success - collect results
                    changed_files.extend(result.changed_files)
                    backup_paths.extend(result.backup_paths)
                    summaries.append(result.summary)
                    
                except MutationReviewRequiredError as e:
                    # This should not happen if preflight worked correctly, but handle it
                    return {
                        "status": "needs_review",
                        "task_id": task_id,
                        "request_id": e.request_id,
                        "outcome": "mutation_review_required",
                        "filename": e.filename,
                        "summary": e.summary
                    }
                except MutationDeniedError as e:
                    # This should not happen if preflight worked correctly, but handle it
                    return {
                        "status": "denied",
                        "task_id": task_id,
                        "code": "MUTATION_DENIED",
                        "detail": str(e),
                        "reason_code": e.reason,
                        "filename": e.filename
                    }
                except MutationApplyError as e:
                    # Apply failed - return immediately
                    return {
                        "status": "error",
                        "task_id": task_id,
                        "code": "MUTATION_APPLY_FAILED",
                        "detail": str(e),
                        "filename": e.filename
                    }
            
            # All mutations applied successfully
            combined_summary = payload.get('summary', '; '.join(summaries))
            
            return {
                "status": "ok",
                "task_id": task_id,
                "outcome": "mutation_applied",
                "changed_files": changed_files,
                "backup_paths": backup_paths,
                "summary": combined_summary
            }
            
        except Exception as e:
            return {
                "status": "error",
                "code": "MUTATION_EXECUTION_ERROR",
                "task_id": task_id,
                "detail": str(e)
            }
    
    def _execute_read_only_analysis(self, task_id: str, directives: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute READ_ONLY_ANALYSIS task by running analysis via AnalysisEngine.
        
        Args:
            task_id: Task ID
            directives: Task directives (ANALYSIS_KIND, OUTPUT_REPORT, INPUTS)
            
        Returns:
            Dict with status, outcome, and analysis results
        """
        import json
        import os
        from pathlib import Path
        
        # Extract directives
        analysis_kind = directives.get('ANALYSIS_KIND')
        output_report = directives.get('OUTPUT_REPORT')
        inputs_raw = directives.get('INPUTS', [])
        
        # Parse INPUTS (YAML-like list format)
        # INPUTS may be a list of strings like "- type: file\n  value: path" or parsed dicts
        inputs: List[Dict[str, str]] = []
        
        # If INPUTS is a list of strings, parse each one
        if isinstance(inputs_raw, list):
            for item in inputs_raw:
                if isinstance(item, dict):
                    # Already parsed
                    inputs.append(item)
                elif isinstance(item, str):
                    # Parse YAML-like format: "- type: file\n  value: path"
                    # Simple parser: look for "type:" and "value:" patterns
                    item_dict = {}
                    for line in item.split('\n'):
                        line = line.strip()
                        if line.startswith('-'):
                            line = line[1:].strip()
                        if 'type:' in line:
                            item_dict['type'] = line.split('type:', 1)[1].strip()
                        if 'value:' in line:
                            item_dict['value'] = line.split('value:', 1)[1].strip()
                    if item_dict.get('type') and item_dict.get('value'):
                        inputs.append(item_dict)
        
        if not inputs:
            return {
                "status": "error",
                "code": "TASK_CONTRACT_INVALID",
                "task_id": task_id,
                "detail": "INPUTS must contain at least one valid input"
            }
        
        # Resolve output report path (must be under REPORTS/)
        project_root = self.mutations_dir.parent
        report_path = project_root / output_report
        
        # Safety: ensure path is within REPORTS/
        try:
            report_path.relative_to(project_root / "REPORTS")
        except ValueError:
            return {
                "status": "error",
                "code": "TASK_CONTRACT_INVALID",
                "task_id": task_id,
                "detail": f"OUTPUT_REPORT must be under REPORTS/, got: {output_report}"
            }
        
        # Run analysis via AnalysisEngine
        # This may raise TrustDeniedError or TrustReviewRequiredError for URL_RESEARCH
        try:
            analysis_result = self.analysis_engine.run(
                kind=analysis_kind,
                inputs=inputs,
                task_id=task_id
            )
            
            # Build report with metadata
            report = {
                "metadata": {
                    "task_id": task_id,
                    "analysis_kind": analysis_kind,
                    "inputs": inputs,
                    "timestamp": datetime.datetime.now().isoformat() + "Z"
                },
                "results": analysis_result
            }
            
            # Write report atomically
            report_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = report_path.with_suffix(report_path.suffix + '.tmp')
            
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2)
                os.replace(temp_path, report_path)
            except Exception as e:
                # Clean up temp file on error
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise
            
            self.memory.remember(
                f"[GuardianCore] READ_ONLY_ANALYSIS completed: {analysis_kind} -> {output_report}",
                category="analysis",
                priority=0.7
            )
            
            return {
                "status": "ok",
                "task_id": task_id,
                "outcome": "analysis_completed",
                "analysis_kind": analysis_kind,
                "output_report": output_report,
                "summary": f"Analysis {analysis_kind} completed, report written to {output_report}"
            }
            
        except TrustDeniedError as e:
            # Network access denied - no report written
            try:
                reason_code = e.reason if hasattr(e, 'reason') else 'UNKNOWN'
            except Exception:
                reason_code = 'UNKNOWN'
            return {
                "status": "denied",
                "task_id": task_id,
                "code": "ANALYSIS_DENIED",
                "detail": str(e),
                "reason_code": reason_code
            }
        except TrustReviewRequiredError as e:
            # Network access requires review - no report written
            try:
                request_id = e.request_id if hasattr(e, 'request_id') else None
                summary = e.summary if hasattr(e, 'summary') else str(e)
            except Exception:
                request_id = None
                summary = str(e)
            return {
                "status": "needs_review",
                "task_id": task_id,
                "request_id": request_id,
                "outcome": "analysis_review_required",
                "summary": summary
            }
        except Exception as e:
            # Analysis failed - check if it's a trust-related exception by name
            exception_type_name = type(e).__name__
            error_detail = str(e)
            
            # Check if error message indicates trust denial/review
            if 'Trust denied' in error_detail or exception_type_name == 'TrustDeniedError':
                try:
                    reason_code = getattr(e, 'reason', 'UNKNOWN') if hasattr(e, 'reason') else 'UNKNOWN'
                except Exception:
                    reason_code = 'UNKNOWN'
                return {
                    "status": "denied",
                    "task_id": task_id,
                    "code": "ANALYSIS_DENIED",
                    "detail": error_detail,
                    "reason_code": reason_code
                }
            elif 'Review required' in error_detail or exception_type_name == 'TrustReviewRequiredError':
                try:
                    request_id = getattr(e, 'request_id', None) if hasattr(e, 'request_id') else None
                    summary = getattr(e, 'summary', error_detail) if hasattr(e, 'summary') else error_detail
                except Exception:
                    request_id = None
                    summary = error_detail
                return {
                    "status": "needs_review",
                    "task_id": task_id,
                    "request_id": request_id,
                    "outcome": "analysis_review_required",
                    "summary": summary
                }
            
            # Analysis failed for other reasons
            return {
                "status": "error",
                "code": "ANALYSIS_FAILED",
                "task_id": task_id,
                "detail": error_detail,
                "exception_type": exception_type_name
            }