# project_guardian/api_server.py
# REST API Server: Expose System State and Controls via REST
# Provides external API access to Elysia system

import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple
from flask import Flask, request, jsonify, Response
from datetime import datetime
import threading

try:
    from flask_cors import CORS
except ImportError:
    CORS = None

try:
    from .system_orchestrator import SystemOrchestrator
    from .mutation_engine import MutationEngine
    from .trust_registry import TrustRegistry
    from .franchise_manager import FranchiseManager
    from .revenue_sharing import RevenueSharing
    from .master_slave_controller import MasterSlaveController
    from .health_monitor import HealthMonitor, get_health_monitor
    try:
        from .ui import app as ui_app_module
    except Exception:
        ui_app_module = None
except ImportError:
    from system_orchestrator import SystemOrchestrator
    from mutation_engine import MutationEngine
    from trust_registry import TrustRegistry
    from franchise_manager import FranchiseManager
    from revenue_sharing import RevenueSharing
    from master_slave_controller import MasterSlaveController
    try:
        from ui import app as ui_app_module
    except Exception:
        ui_app_module = None
    try:
        from health_monitor import HealthMonitor, get_health_monitor
    except ImportError:
        HealthMonitor = None
        get_health_monitor = None

logger = logging.getLogger(__name__)


class UiAppLauncher:
    """Read-only launcher/introspection surface for FastAPI control panel app."""

    def __init__(self, module: Any = None):
        self._module = module

    def get_status(self) -> Dict[str, Any]:
        module = self._module
        if module is None:
            return {"available": False, "reason": "ui module unavailable"}

        return {
            "available": True,
            "fastapi_available": bool(getattr(module, "FASTAPI_AVAILABLE", False)),
            "fastapi_error": getattr(module, "FASTAPI_IMPORT_ERROR", None),
            "has_app": getattr(module, "app", None) is not None,
        }

    def list_routes(self) -> List[str]:
        module = self._module
        if module is None:
            return []
        app = getattr(module, "app", None)
        routes = getattr(app, "routes", None)
        if not routes:
            return []

        route_paths: List[str] = []
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                route_paths.append(path)
        return sorted(set(route_paths))


class APIServer:
    """
    REST API Server for Elysia system.
    Provides external access to system state, controls, and operations.
    """
    
    def __init__(
        self,
        orchestrator: Optional[SystemOrchestrator] = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_cors: bool = True,
        enable_ui_launcher: bool = False,
    ):
        """
        Initialize API Server.
        
        Args:
            orchestrator: SystemOrchestrator instance
            host: Host to bind to
            port: Port to listen on
            enable_cors: Enable CORS for web access
            enable_ui_launcher: Expose ui/app launcher inspection surface
        """
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.ui_app_launcher = UiAppLauncher(ui_app_module) if enable_ui_launcher else None
        
        if enable_cors and CORS:
            CORS(self.app)  # Enable CORS for all routes
        elif enable_cors:
            logger.warning("flask_cors not available; continuing without CORS support")
        
        # Health monitor
        self.health_monitor = get_health_monitor() if get_health_monitor else None
        
        # Server thread
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Setup routes
        self._setup_routes()
        
        # Register API server component health
        if self.health_monitor and HealthMonitor:
            from .health_monitor import HealthStatus
            self.health_monitor.check_component_health(
                "api_server",
                HealthStatus.HEALTHY,
                "API server initialized"
            )
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "started_at": datetime.now()
        }

    def _task_resolution_roots(self) -> Dict[str, Any]:
        """Build the set of task-callable roots exposed through the API."""
        roots: Dict[str, Any] = {
            "api_server": self,
            "api": self,
        }
        if self.ui_app_launcher is not None:
            roots["ui_app_launcher"] = self.ui_app_launcher
        if not self.orchestrator:
            return roots

        roots.update(
            {
                "orchestrator": self.orchestrator,
                "system": self.orchestrator,
            }
        )

        for name in (
            "guardian_core",
            "mutation_engine",
            "trust_registry",
            "franchise_manager",
            "revenue_sharing",
            "master_slave_controller",
            "task_assignment_engine",
            "implementer_core",
            "mutation_review_manager",
            "mutation_router",
            "mutation_publisher",
            "mutation_sandbox",
            "tool_executor",
            "digital_safehouse",
            "dream_engine",
            "ai_mutation_validator",
            "income_executor",
            "intelligent_task_distribution",
            "proposal_api",
            "slave_deployment",
            "credit_spend_log",
            "error_handler",
            "chatgpt_export_import",
            "feedback_loop_core",
            "file_writer",
            "mutation_autonomy_sandbox",
            "eai_safety_framework",
            "eai_safety",
            "review_queue",
            "approval_store",
            "module_registry",
            "runtime_loop",
            "task_queue",
            "memory",
        ):
            component = getattr(self.orchestrator, name, None)
            if component is not None:
                roots[name] = component

        return roots

    def _resolve_task_callable(
        self,
        function_name: str,
        module_name: Optional[str] = None,
    ) -> Tuple[Callable[..., Any], str]:
        """
        Resolve an API task target to a real callable.

        Supports either ``module + function`` or dotted names like
        ``trust_registry.register_node``. Private attributes are never exposed.
        """
        function_name = str(function_name or "").strip()
        if not function_name:
            raise ValueError("function name required")

        parts = [part.strip() for part in function_name.split(".") if part.strip()]
        if not parts:
            raise ValueError("function name required")
        if any(part.startswith("_") for part in parts):
            raise ValueError("Private task targets are not allowed")

        roots = self._task_resolution_roots()
        module_key = str(module_name or "").strip()
        generic_modules = {"", "api", "default", "auto"}

        target: Any = None
        resolved_path = ""
        remaining_parts = list(parts)

        if remaining_parts[0] in roots:
            root_name = remaining_parts.pop(0)
            target = roots[root_name]
            resolved_path = root_name
        elif module_key and module_key not in generic_modules:
            if module_key not in roots:
                raise LookupError(f"Unknown task module: {module_key}")
            target = roots[module_key]
            resolved_path = module_key
        elif len(remaining_parts) > 1:
            raise LookupError(
                f"Unknown task root '{remaining_parts[0]}'. Use a known module or explicit module field."
            )
        else:
            attr_name = remaining_parts[0]
            candidates = []
            seen = set()
            for root_name, root in roots.items():
                if not hasattr(root, attr_name):
                    continue
                candidate = getattr(root, attr_name)
                if not callable(candidate):
                    continue
                dedupe_key = (id(root), attr_name)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                candidates.append((root_name, candidate))

            if not candidates:
                raise LookupError(f"Task function not found: {attr_name}")
            if len(candidates) > 1:
                raise LookupError(
                    f"Ambiguous task function '{attr_name}'. Specify the module explicitly."
                )

            root_name, candidate = candidates[0]
            return candidate, f"{root_name}.{attr_name}"

        current = target
        for attr_name in remaining_parts:
            if attr_name.startswith("_"):
                raise ValueError("Private task targets are not allowed")
            current = getattr(current, attr_name, None)
            if current is None:
                raise LookupError(f"Task function not found: {function_name}")
            resolved_path = f"{resolved_path}.{attr_name}" if resolved_path else attr_name

        if not callable(current):
            raise TypeError(f"Resolved task target is not callable: {resolved_path or function_name}")

        return current, (resolved_path or function_name)

    def _get_eai_safety_framework(self) -> Optional[Any]:
        """Resolve the shared Evolvable-AI safety framework if it is initialized."""

        roots = []
        if self.orchestrator is not None:
            roots.append(self.orchestrator)
            guardian_core = getattr(self.orchestrator, "guardian_core", None)
            if guardian_core is not None:
                roots.append(guardian_core)

        for root in roots:
            for name in ("eai_safety_framework", "eai_safety", "evolvable_ai_safety"):
                framework = getattr(root, name, None)
                if framework is not None:
                    return framework
        return None

    @staticmethod
    def _bounded_limit(value: Optional[int], default: int = 50, maximum: int = 500) -> int:
        if value is None:
            return default
        return max(1, min(maximum, int(value)))

    @staticmethod
    def _content_preview(value: Any, max_chars: int = 2000) -> Dict[str, Any]:
        if value is None:
            return {"present": False}
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
        elif isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, sort_keys=True, default=str)
        return {
            "present": True,
            "chars": len(text),
            "truncated": len(text) > max_chars,
            "preview": text[:max_chars],
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def _eai_review_context(
        self,
        data: Dict[str, Any],
        assessment_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        return {
            "target": str(data.get("target") or ""),
            "caller_identity": str(data.get("actor") or "operator"),
            "task_id": str(data.get("task_id") or "eai-dry-run"),
            "action_type": str(data.get("action_type") or ""),
            "metadata": metadata,
            "artifact_content": self._content_preview(data.get("artifact_content")),
            "lineage_parent_ids": data.get("lineage_parent_ids", data.get("parent_ids")),
            "eai_safety": assessment_result.get("assessment", assessment_result),
            "eai_decision": assessment_result.get("decision"),
            "eai_risk_score": assessment_result.get("risk_score"),
            "eai_flags": assessment_result.get("flags", []),
            "eai_required_controls": assessment_result.get("required_controls", []),
            "lineage_mutated": False,
            "source": "eai_dry_run",
        }

    def _get_review_queue(self) -> Any:
        """Resolve the review queue used for EAI human-review handoff."""

        framework = self._get_eai_safety_framework()
        queue = getattr(framework, "review_queue", None) if framework is not None else None
        if queue is not None:
            return queue

        queue = getattr(self.orchestrator, "review_queue", None) if self.orchestrator else None
        if queue is not None:
            return queue

        try:
            from .review_queue import ReviewQueue
        except ImportError:
            from review_queue import ReviewQueue

        return ReviewQueue()

    def _resolve_eai_report_output_dir(self, requested: Optional[Any] = None) -> str:
        """Resolve an EAI report output directory under configured storage."""

        config = getattr(self.orchestrator, "config", {}) if self.orchestrator else {}
        configured_root = config.get("storage_path") if isinstance(config, dict) else None
        base_root = Path(configured_root or ".").resolve()
        if base_root.suffix and not base_root.is_dir():
            base_root = base_root.parent

        requested_text = str(requested or "REPORTS").strip() or "REPORTS"
        requested_path = Path(requested_text)
        target = (
            requested_path.resolve()
            if requested_path.is_absolute()
            else (base_root / requested_path).resolve()
        )
        try:
            target.relative_to(base_root)
        except ValueError as exc:
            raise ValueError("output_dir must stay within configured storage") from exc
        return str(target)
    
    def _setup_routes(self):
        """Setup API routes."""
        
        # Health check
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint with detailed health status."""
            try:
                if get_health_monitor:
                    monitor = get_health_monitor()
                    health_response = monitor.get_health_endpoint_response()
                    status_code = health_response.pop("http_status", 200)
                    return jsonify(health_response), status_code
                else:
                    # Fallback simple health check
                    return jsonify({
                        "status": "healthy",
                        "timestamp": datetime.now().isoformat(),
                        "api_version": "1.0",
                        "components": {},
                        "resources": {}
                    })
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                return jsonify({
                    "status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                }), 503
        
        # Metrics endpoint
        @self.app.route('/api/metrics', methods=['GET'])
        def get_metrics():
            """Get system metrics for monitoring."""
            try:
                metrics = {}
                
                # Health monitor metrics
                if self.health_monitor:
                    metrics.update(self.health_monitor.get_metrics())
                
                # API server stats
                metrics["api_server"] = {
                    "total_requests": self.stats["total_requests"],
                    "successful_requests": self.stats["successful_requests"],
                    "failed_requests": self.stats["failed_requests"],
                    "uptime": (
                        (datetime.now() - self.stats["started_at"]).total_seconds()
                        if self.stats["started_at"] else None
                    )
                }
                
                self._record_request(success=True)
                return jsonify(metrics)
            except Exception as e:
                logger.error(f"Error getting metrics: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # System status
        @self.app.route('/api/system/status', methods=['GET'])
        def get_system_status():
            """Get system status."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                status = self.orchestrator.get_system_status()
                self._record_request(success=True)
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting system status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # System statistics
        @self.app.route('/api/system/stats', methods=['GET'])
        def get_system_stats():
            """Get system statistics."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                stats = {
                    "uptime": self.stats.get("started_at"),
                    "api_requests": {
                        "total": self.stats["total_requests"],
                        "successful": self.stats["successful_requests"],
                        "failed": self.stats["failed_requests"]
                    }
                }
                
                # Add orchestrator stats if available
                if self.orchestrator:
                    orchestrator_stats = self.orchestrator.get_system_status()
                    stats["system"] = orchestrator_stats
                
                self._record_request(success=True)
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Error getting system stats: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/ui/status', methods=['GET'])
        def get_ui_status():
            """Get UI launcher status."""
            try:
                if self.ui_app_launcher is None:
                    return jsonify({"available": False, "message": "UI launcher disabled"}), 404
                status = self.ui_app_launcher.get_status()
                status["routes"] = self.ui_app_launcher.list_routes()[:50]
                self._record_request(success=True)
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting UI status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/status', methods=['GET'])
        def get_eai_status():
            """Get Evolvable-AI safety gate status."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None:
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety framework not available"
                    }), 503

                status = framework.get_status()
                self._record_request(success=True)
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting EAI safety status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/assess', methods=['POST'])
        def assess_eai_action():
            """Dry-run an Evolvable-AI-sensitive action through the safety gate."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None:
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety framework not available"
                    }), 503

                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    self._record_request(success=False)
                    return jsonify({"error": "JSON object body required"}), 400

                action_type = str(data.get("action_type") or "").strip()
                if not action_type:
                    self._record_request(success=False)
                    return jsonify({"error": "action_type required"}), 400

                metadata = data.get("metadata") or {}
                if not isinstance(metadata, dict):
                    self._record_request(success=False)
                    return jsonify({"error": "metadata must be an object"}), 400

                parent_ids = data.get("lineage_parent_ids", data.get("parent_ids"))
                assessment = framework.assess_action(
                    action_type=action_type[:120],
                    actor=str(data.get("actor") or "operator")[:160],
                    target=str(data.get("target") or "")[:500],
                    metadata=metadata,
                    lineage_parent_ids=parent_ids,
                    artifact_content=data.get("artifact_content"),
                    dry_run=True,
                )
                payload = assessment.to_dict()
                self._record_request(success=True)
                return jsonify({
                    "dry_run": True,
                    "lineage_mutated": False,
                    "decision": payload["decision"],
                    "risk_score": payload["risk_score"],
                    "flags": payload["flags"],
                    "selection_pressures": payload["selection_pressures"],
                    "required_controls": payload["required_controls"],
                    "assessment": payload,
                })
            except Exception as e:
                logger.error(f"Error assessing EAI action: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/review-request', methods=['POST'])
        def create_eai_review_request():
            """Create a human review request from an EAI dry-run assessment."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None:
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety framework not available"
                    }), 503

                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    self._record_request(success=False)
                    return jsonify({"error": "JSON object body required"}), 400

                action_type = str(data.get("action_type") or "").strip()
                if not action_type:
                    self._record_request(success=False)
                    return jsonify({"error": "action_type required"}), 400

                metadata = data.get("metadata") or {}
                if not isinstance(metadata, dict):
                    self._record_request(success=False)
                    return jsonify({"error": "metadata must be an object"}), 400

                parent_ids = data.get("lineage_parent_ids", data.get("parent_ids"))
                assessment = framework.assess_action(
                    action_type=action_type[:120],
                    actor=str(data.get("actor") or "operator")[:160],
                    target=str(data.get("target") or "")[:500],
                    metadata=metadata,
                    lineage_parent_ids=parent_ids,
                    artifact_content=data.get("artifact_content"),
                    dry_run=True,
                )
                assessment_payload = assessment.to_dict()
                result = {
                    "dry_run": True,
                    "lineage_mutated": False,
                    "decision": assessment_payload["decision"],
                    "risk_score": assessment_payload["risk_score"],
                    "flags": assessment_payload["flags"],
                    "selection_pressures": assessment_payload["selection_pressures"],
                    "required_controls": assessment_payload["required_controls"],
                    "assessment": assessment_payload,
                }

                if result["decision"] == "allow" and not data.get("force_review"):
                    self._record_request(success=True)
                    return jsonify({
                        "created": False,
                        "reason": "assessment_allowed",
                        "assessment": result,
                    })

                queue = self._get_review_queue()
                request_id = queue.enqueue(
                    component="eai_safety",
                    action=action_type[:120],
                    context=self._eai_review_context(data, result),
                )
                audit_event = None
                if hasattr(framework, "record_audit_event"):
                    audit_event = framework.record_audit_event(
                        "review_request",
                        assessment,
                        review_request_id=request_id,
                        details={
                            "source": "api_server",
                            "lineage_mutated": False,
                        },
                    )
                self._record_request(success=True)
                return jsonify({
                    "created": True,
                    "request_id": request_id,
                    "review_url": f"/reviews/{request_id}",
                    "audit_id": (
                        audit_event.get("audit_id")
                        if isinstance(audit_event, dict)
                        else None
                    ),
                    "assessment": result,
                }), 201
            except Exception as e:
                logger.error(f"Error creating EAI review request: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/audit', methods=['GET'])
        def list_eai_audit():
            """List recent EAI safety audit events."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "list_audit"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety audit trail not available"
                    }), 503

                limit = self._bounded_limit(request.args.get('limit', type=int))
                events = framework.list_audit(
                    limit=limit,
                    decision=request.args.get('decision'),
                    flag=request.args.get('flag'),
                    actor=request.args.get('actor'),
                    target=request.args.get('target'),
                    event_type=request.args.get('event_type'),
                )
                self._record_request(success=True)
                return jsonify({
                    "events": events,
                    "limit": limit,
                })
            except Exception as e:
                logger.error(f"Error listing EAI audit trail: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/audit/<identifier>', methods=['GET'])
        def get_eai_audit_event(identifier):
            """Get an EAI audit event by audit, assessment, or review request id."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "get_audit_event"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety audit trail not available"
                    }), 503

                event = framework.get_audit_event(identifier)
                if event is None:
                    self._record_request(success=False)
                    return jsonify({"error": "EAI audit event not found"}), 404

                self._record_request(success=True)
                return jsonify(event)
            except Exception as e:
                logger.error(f"Error getting EAI audit event: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/alerts', methods=['GET'])
        def list_eai_alerts():
            """List computed EAI safety alerts from recent audit events."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "list_alerts"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety alerts not available"
                    }), 503

                limit = self._bounded_limit(request.args.get('limit', type=int), default=25)
                audit_limit = self._bounded_limit(
                    request.args.get('audit_limit', type=int),
                    default=500,
                    maximum=5000,
                )
                alerts = framework.list_alerts(
                    limit=limit,
                    audit_limit=audit_limit,
                    severity=request.args.get('severity'),
                    rule=request.args.get('rule'),
                    include_acknowledged=(
                        str(request.args.get('include_acknowledged', 'true')).lower()
                        not in {"0", "false", "no"}
                    ),
                    include_resolved=(
                        str(request.args.get('include_resolved', 'false')).lower()
                        in {"1", "true", "yes"}
                    ),
                )
                self._record_request(success=True)
                return jsonify({
                    "alerts": alerts,
                    "limit": limit,
                    "audit_limit": audit_limit,
                })
            except Exception as e:
                logger.error(f"Error listing EAI alerts: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/summary', methods=['GET'])
        def get_eai_summary():
            """Get a compact EAI safety daily summary."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "get_daily_summary"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety summary not available"
                    }), 503

                days = self._bounded_limit(
                    request.args.get('days', type=int),
                    default=1,
                    maximum=365,
                )
                audit_limit = self._bounded_limit(
                    request.args.get('audit_limit', type=int),
                    default=5000,
                    maximum=20000,
                )
                summary = framework.get_daily_summary(
                    days=days,
                    audit_limit=audit_limit,
                    include_resolved=(
                        str(request.args.get('include_resolved', 'true')).lower()
                        in {"1", "true", "yes"}
                    ),
                )
                self._record_request(success=True)
                return jsonify(summary)
            except Exception as e:
                logger.error(f"Error getting EAI summary: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/summary.md', methods=['GET'])
        def get_eai_summary_markdown():
            """Get a Markdown EAI safety daily summary report."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(
                    framework,
                    "render_daily_summary_markdown",
                ):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety summary report not available"
                    }), 503

                days = self._bounded_limit(
                    request.args.get('days', type=int),
                    default=1,
                    maximum=365,
                )
                audit_limit = self._bounded_limit(
                    request.args.get('audit_limit', type=int),
                    default=5000,
                    maximum=20000,
                )
                markdown = framework.render_daily_summary_markdown(
                    days=days,
                    audit_limit=audit_limit,
                    include_resolved=(
                        str(request.args.get('include_resolved', 'true')).lower()
                        in {"1", "true", "yes"}
                    ),
                )
                self._record_request(success=True)
                return Response(markdown, mimetype="text/markdown")
            except Exception as e:
                logger.error(f"Error getting EAI summary report: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/summary/export', methods=['POST'])
        def export_eai_summary_markdown():
            """Write a Markdown EAI safety summary report to disk."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(
                    framework,
                    "write_daily_summary_report",
                ):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety summary export not available"
                    }), 503

                data = request.get_json(silent=True) or {}
                if not isinstance(data, dict):
                    data = {}
                days = self._bounded_limit(data.get("days"), default=1, maximum=365)
                audit_limit = self._bounded_limit(
                    data.get("audit_limit"),
                    default=5000,
                    maximum=20000,
                )
                output_dir = self._resolve_eai_report_output_dir(data.get("output_dir"))
                result = framework.write_daily_summary_report(
                    output_dir=output_dir,
                    days=days,
                    audit_limit=audit_limit,
                    include_resolved=bool(data.get("include_resolved", True)),
                    filename=(
                        str(data.get("filename"))
                        if data.get("filename") is not None
                        else None
                    ),
                )
                self._record_request(success=True)
                return jsonify(result), 201
            except ValueError as e:
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                logger.error(f"Error exporting EAI summary report: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/alerts/<alert_id>/ack', methods=['POST'])
        def acknowledge_eai_alert(alert_id):
            """Acknowledge a computed EAI alert."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "acknowledge_alert"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety alert state not available"
                    }), 503

                data = request.get_json(silent=True) or {}
                if not isinstance(data, dict):
                    data = {}
                state = framework.acknowledge_alert(
                    alert_id,
                    actor=str(data.get("actor") or "operator")[:160],
                    notes=str(data.get("notes") or "")[:1000],
                )
                self._record_request(success=True)
                return jsonify({"updated": True, "state": state})
            except ValueError as e:
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                logger.error(f"Error acknowledging EAI alert: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/alerts/<alert_id>/resolve', methods=['POST'])
        def resolve_eai_alert(alert_id):
            """Resolve a computed EAI alert."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None or not hasattr(framework, "resolve_alert"):
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety alert state not available"
                    }), 503

                data = request.get_json(silent=True) or {}
                if not isinstance(data, dict):
                    data = {}
                state = framework.resolve_alert(
                    alert_id,
                    actor=str(data.get("actor") or "operator")[:160],
                    notes=str(data.get("notes") or "")[:1000],
                )
                self._record_request(success=True)
                return jsonify({"updated": True, "state": state})
            except ValueError as e:
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                logger.error(f"Error resolving EAI alert: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/lineage', methods=['GET'])
        def list_eai_lineage():
            """List EAI lineage records."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None:
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety framework not available"
                    }), 503

                limit = self._bounded_limit(request.args.get('limit', type=int))
                self._record_request(success=True)
                return jsonify({
                    "records": framework.list_lineage(limit=limit),
                    "limit": limit,
                })
            except Exception as e:
                logger.error(f"Error listing EAI lineage: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/eai/lineage/<artifact_id>', methods=['GET'])
        def get_eai_lineage_record(artifact_id):
            """Get a specific EAI lineage record."""
            try:
                framework = self._get_eai_safety_framework()
                if framework is None:
                    return jsonify({
                        "enabled": False,
                        "error": "EAI safety framework not available"
                    }), 503

                record = framework.get_lineage_record(artifact_id)
                if record is None:
                    self._record_request(success=False)
                    return jsonify({"error": "Lineage record not found"}), 404

                self._record_request(success=True)
                return jsonify(record.to_dict())
            except Exception as e:
                logger.error(f"Error getting EAI lineage record: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Mutation endpoints
        @self.app.route('/api/mutations', methods=['GET'])
        def list_mutations():
            """List all mutation proposals."""
            try:
                mutation_engine = getattr(self.orchestrator, "mutation_engine", None) if self.orchestrator else None
                if not mutation_engine:
                    return jsonify({"error": "MutationEngine not available"}), 503

                if hasattr(mutation_engine, "get_all_proposals"):
                    mutations = mutation_engine.get_all_proposals()
                else:
                    mutations = mutation_engine.list_mutations()
                mutations_data = [m.to_dict() for m in mutations]
                
                self._record_request(success=True)
                return jsonify({"mutations": mutations_data})
            except Exception as e:
                logger.error(f"Error listing mutations: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/mutations/<mutation_id>', methods=['GET'])
        def get_mutation(mutation_id):
            """Get specific mutation proposal."""
            try:
                mutation_engine = getattr(self.orchestrator, "mutation_engine", None) if self.orchestrator else None
                if not mutation_engine:
                    return jsonify({"error": "MutationEngine not available"}), 503

                if hasattr(mutation_engine, "get_proposal"):
                    proposal = mutation_engine.get_proposal(mutation_id)
                else:
                    proposal = mutation_engine.get_mutation(mutation_id)
                if not proposal:
                    return jsonify({"error": "Mutation not found"}), 404
                
                self._record_request(success=True)
                return jsonify(proposal.to_dict())
            except Exception as e:
                logger.error(f"Error getting mutation: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Trust Registry endpoints
        @self.app.route('/api/trust/nodes', methods=['GET'])
        def list_trust_nodes():
            """List all nodes in trust registry."""
            try:
                trust_registry = getattr(self.orchestrator, "trust_registry", None) if self.orchestrator else None
                if not trust_registry:
                    return jsonify({"error": "TrustRegistry not available"}), 503
                
                nodes = trust_registry.list_nodes()
                nodes_data = []
                for node in nodes:
                    if hasattr(node, "to_dict"):
                        nodes_data.append(node.to_dict())
                        continue

                    trust = None
                    if hasattr(trust_registry, "get_node_trust"):
                        trust = trust_registry.get_node_trust(node)
                    elif hasattr(trust_registry, "get_node"):
                        trust = trust_registry.get_node(node)
                    if trust:
                        nodes_data.append(trust.to_dict())
                
                self._record_request(success=True)
                return jsonify({"nodes": nodes_data})
            except Exception as e:
                logger.error(f"Error listing trust nodes: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/trust/nodes/<node_id>', methods=['GET'])
        def get_trust_node(node_id):
            """Get trust data for specific node."""
            try:
                trust_registry = getattr(self.orchestrator, "trust_registry", None) if self.orchestrator else None
                if not trust_registry:
                    return jsonify({"error": "TrustRegistry not available"}), 503

                if hasattr(trust_registry, "get_node_trust"):
                    trust = trust_registry.get_node_trust(node_id)
                else:
                    trust = trust_registry.get_node(node_id)
                if not trust:
                    return jsonify({"error": "Node not found"}), 404
                
                self._record_request(success=True)
                return jsonify(trust.to_dict())
            except Exception as e:
                logger.error(f"Error getting trust node: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Franchise endpoints
        @self.app.route('/api/franchises', methods=['GET'])
        def list_franchises():
            """List all franchises."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'franchise_manager'):
                    return jsonify({"error": "FranchiseManager not available"}), 503
                
                # Get franchises from orchestrator if available
                franchises = []
                if self.orchestrator.franchise_manager:
                    agreements = self.orchestrator.franchise_manager.agreements
                    franchises = [
                        {
                            "agreement_id": aid,
                            "franchise_id": agreement.franchise_id,
                            "status": agreement.status.value,
                            "created_at": agreement.created_at.isoformat()
                        }
                        for aid, agreement in agreements.items()
                    ]
                
                self._record_request(success=True)
                return jsonify({"franchises": franchises})
            except Exception as e:
                logger.error(f"Error listing franchises: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/franchises/<franchise_id>', methods=['GET'])
        def get_franchise(franchise_id):
            """Get franchise report."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'franchise_manager'):
                    return jsonify({"error": "FranchiseManager not available"}), 503
                
                if not self.orchestrator.franchise_manager:
                    return jsonify({"error": "FranchiseManager not initialized"}), 503
                
                report = self.orchestrator.franchise_manager.get_franchise_report(franchise_id)
                
                self._record_request(success=True)
                return jsonify(report)
            except Exception as e:
                logger.error(f"Error getting franchise: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Revenue endpoints
        @self.app.route('/api/revenue/summary', methods=['GET'])
        def get_revenue_summary():
            """Get master revenue summary."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'revenue_sharing'):
                    return jsonify({"error": "RevenueSharing not available"}), 503
                
                if not self.orchestrator.revenue_sharing:
                    return jsonify({"error": "RevenueSharing not initialized"}), 503
                
                days = request.args.get('days', 30, type=int)
                summary = self.orchestrator.revenue_sharing.get_master_revenue_summary(days=days)
                
                self._record_request(success=True)
                return jsonify(summary)
            except Exception as e:
                logger.error(f"Error getting revenue summary: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Task submission
        @self.app.route('/api/tasks', methods=['POST'])
        def submit_task():
            """Submit a task to the system."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400
                
                # Extract task parameters
                task_func_name = data.get("function")
                priority = data.get("priority", 5)
                module = data.get("module")
                args = data.get("args", [])
                kwargs = data.get("kwargs", {})
                
                if not task_func_name:
                    return jsonify({"error": "function name required"}), 400

                if not isinstance(args, (list, tuple)):
                    return jsonify({"error": "args must be a list"}), 400
                if not isinstance(kwargs, dict):
                    return jsonify({"error": "kwargs must be an object"}), 400

                task_function, resolved_function = self._resolve_task_callable(task_func_name, module)
                task_module = str(module or resolved_function.split(".", 1)[0] or "api")

                # Submit task
                task_id = self.orchestrator.submit_task(
                    task_function,
                    priority=priority,
                    module=task_module,
                    args=tuple(args),
                    kwargs=kwargs,
                    metadata={
                        "source": "api_server",
                        "requested_function": task_func_name,
                        "resolved_function": resolved_function,
                    },
                )
                
                self._record_request(success=True)
                return jsonify({
                    "success": True,
                    "task_id": task_id,
                    "resolved_function": resolved_function,
                    "message": "Task submitted successfully"
                }), 201
            except (LookupError, TypeError, ValueError) as e:
                logger.warning(f"Invalid task submission: {e}")
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                logger.error(f"Error submitting task: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Memory endpoints
        @self.app.route('/api/memory/search', methods=['POST'])
        def search_memory():
            """Search memories."""
            try:
                if not self.orchestrator or not self.orchestrator.memory:
                    return jsonify({"error": "MemoryCore not available"}), 503
                
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400
                
                keyword = data.get("keyword")
                limit = data.get("limit", 10)
                
                if not keyword:
                    return jsonify({"error": "keyword required"}), 400
                
                memories = self.orchestrator.memory.search_memories(keyword, limit=limit)
                
                self._record_request(success=True)
                return jsonify({"memories": memories})
            except Exception as e:
                logger.error(f"Error searching memory: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Security audit endpoints
        @self.app.route('/api/security/audit', methods=['GET'])
        def run_security_audit():
            """Run security audit."""
            try:
                # Try to get GuardianCore if available
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'run_security_audit'):
                    audit_results = guardian_core.run_security_audit()
                else:
                    # Fallback: create auditor directly
                    from .security_audit import SecurityAuditor
                    auditor = SecurityAuditor()
                    audit_results = auditor.run_audit()
                
                self._record_request(success=True)
                return jsonify(audit_results)
            except Exception as e:
                logger.error(f"Error running security audit: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Resource monitoring endpoints
        @self.app.route('/api/resources/status', methods=['GET'])
        def get_resource_status():
            """Get resource usage and limits status."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_status'):
                    resource_status = guardian_core.get_resource_status()
                else:
                    resource_status = {"error": "Resource monitoring not available"}
                
                self._record_request(success=True)
                return jsonify(resource_status)
            except Exception as e:
                logger.error(f"Error getting resource status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/resources/stats', methods=['GET'])
        def get_resource_stats():
            """Get current resource statistics."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_stats'):
                    resource_stats = guardian_core.get_resource_stats()
                else:
                    resource_stats = {}
                
                self._record_request(success=True)
                return jsonify(resource_stats)
            except Exception as e:
                logger.error(f"Error getting resource stats: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/resources/violations', methods=['GET'])
        def get_resource_violations():
            """Get resource limit violations."""
            try:
                limit = request.args.get('limit', type=int)
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_violations'):
                    violations = guardian_core.get_resource_violations(limit=limit)
                else:
                    violations = []
                
                self._record_request(success=True)
                return jsonify({"violations": violations})
            except Exception as e:
                logger.error(f"Error getting resource violations: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Configuration validation endpoint
        @self.app.route('/api/config/validation', methods=['GET'])
        def get_config_validation():
            """Get configuration validation status."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                if not guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                verification = guardian_core.get_startup_verification()
                self._record_request(success=True)
                return jsonify(verification)
            except Exception as e:
                logger.error(f"Error getting config validation: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/health/runtime', methods=['GET'])
        def get_runtime_health():
            """Get current runtime health status."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                if not guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                health = guardian_core.get_runtime_health()
                self._record_request(success=True)
                return jsonify(health)
            except Exception as e:
                logger.error(f"Error getting runtime health: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/health/history', methods=['GET'])
        def get_health_history():
            """Get runtime health check history."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                if not guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                limit = request.args.get('limit', type=int)
                history = guardian_core.get_runtime_health_history(limit=limit)
                self._record_request(success=True)
                return jsonify({"history": history})
            except Exception as e:
                logger.error(f"Error getting health history: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/startup/verification', methods=['GET'])
        def get_startup_verification():
            """Get startup verification results."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                if not guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                verification = guardian_core.get_startup_verification()
                self._record_request(success=True)
                return jsonify(verification)
            except Exception as e:
                logger.error(f"Error getting startup verification: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Error handlers
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({"error": "Endpoint not found"}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({"error": "Internal server error"}), 500
    
    def _record_request(self, success: bool = True):
        """Record API request statistics."""
        self.stats["total_requests"] += 1
        if success:
            self.stats["successful_requests"] += 1
        else:
            self.stats["failed_requests"] += 1
    
    def start(self, threaded: bool = True):
        """
        Start the API server.
        
        Args:
            threaded: If True, run in background thread
        """
        if self._running:
            logger.warning("API server already running")
            return
        
        self.stats["started_at"] = datetime.now().isoformat()
        
        if threaded:
            def run_server():
                self.app.run(host=self.host, port=self.port, debug=False)
            
            self._server_thread = threading.Thread(target=run_server, daemon=True)
            self._server_thread.start()
            self._running = True
            logger.info(f"API server started on http://{self.host}:{self.port}")
        else:
            logger.info(f"API server starting on http://{self.host}:{self.port}")
            logger.warning("Running in non-threaded mode - this will block")
            self._running = True
            self.app.run(host=self.host, port=self.port, debug=False)
    
    def stop(self):
        """Stop the API server."""
        if not self._running:
            return
        
        # Flask doesn't have a built-in stop method
        # In production, use a proper WSGI server like gunicorn
        logger.warning("Flask development server cannot be stopped gracefully")
        self._running = False
        logger.info("API server stopped")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get API server statistics."""
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "started_at": self.stats["started_at"],
            "total_requests": self.stats["total_requests"],
            "successful_requests": self.stats["successful_requests"],
            "failed_requests": self.stats["failed_requests"],
            "success_rate": (
                self.stats["successful_requests"] / max(1, self.stats["total_requests"])
            )
        }


# Example usage
if __name__ == "__main__":
    # Initialize system
    orchestrator = SystemOrchestrator()
    # await orchestrator.initialize()  # Would need async context
    
    # Create API server
    api_server = APIServer(
        orchestrator=orchestrator,
        host="0.0.0.0",
        port=8080
    )
    
    # Start server
    api_server.start(threaded=False)  # Run in main thread for testing

