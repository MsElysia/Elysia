"""Minimal REST API surface for the Elysia runtime."""

from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

try:  # pragma: no cover - optional dependency
    from flask_cors import CORS
except ImportError:  # pragma: no cover
    CORS = None  # type: ignore

from ..events import EventBus

from project_guardian.safe_stack import responses as _safe_stack_responses
from project_guardian.safe_stack.operator_chat import (
    OperatorChatRequest,
    OperatorChatResponderResult,
    run_operator_chat_turn,
)
from project_guardian.conversation_store import (
    CHAT_LIST_MESSAGES_DEFAULT,
    get_default_conversation_store,
    sanitize_conversation_id,
)

logger = logging.getLogger(__name__)


class RuntimeAPIServer:
    """Wrap a Flask server that exposes runtime status and events."""

    def __init__(
        self,
        status_provider: Callable[[], Dict[str, Any]],
        event_bus: EventBus,
        host: str = "127.0.0.1",
        port: int = 8123,
        proposal_system: Optional[Any] = None,
        webscout: Optional[Any] = None,
        architect: Optional[Any] = None,
        implementer: Optional[Any] = None,
        guardian: Optional[Any] = None,
        conversation_store: Optional[Any] = None,
        self_improvement_queue: Optional[Any] = None,
    ):
        self._status_provider = status_provider
        self._event_bus = event_bus
        self._proposal_system = proposal_system
        self._webscout = webscout
        self._architect = architect
        self._implementer = implementer
        self._guardian = guardian
        self._conversation_store = conversation_store
        self._self_improvement_queue = self_improvement_queue
        self.host = host
        self.port = port
        self._app = Flask(__name__)
        if CORS:
            CORS(self._app)

        self._thread: Optional[threading.Thread] = None
        self._server: Optional[Any] = None
        self._running = False
        self._setup_routes()

    def _self_improvement_queue_impl(self) -> Any:
        if self._self_improvement_queue is not None:
            return self._self_improvement_queue
        from project_guardian.self_improvement.proposal_queue import get_default_proposal_queue

        return get_default_proposal_queue()

    def _architect_chat(self, message: str, context: str) -> Optional[Dict[str, Any]]:
        """Delegate general chat to Architect-Core when it exposes a chat surface."""
        if not self._architect:
            return None

        chat = getattr(self._architect, "chat", None)
        if callable(chat):
            result = chat(message, context=context)
            if isinstance(result, dict):
                return result
            return {"response": str(result), "context": context, "source": "architect_core"}

        return {
            "response": "Architect-Core is connected, but no chat handler is configured.",
            "context": context,
            "status": "deferred",
            "source": "architect_core",
        }

    def _maybe_run_brain_operator_chat_trace(self, message: str, http_context: str) -> Dict[str, Any]:
        """Config-gated BrainPipeline trace for /api/chat (dry-run for operator_chat unless live flag set)."""
        try:
            from project_guardian.brain.config import get_brain_pipeline_config
            from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event

            cfg = get_brain_pipeline_config()
            if not cfg.enabled or not cfg.entrypoint_enabled("operator_chat"):
                return {}

            res = run_brain_pipeline_for_operator_event(
                {
                    "message": message,
                    "source": "operator",
                    "metadata": {"http_context": str(http_context)[:240]},
                },
                guardian=self._guardian,
                source_entrypoint="operator_chat",
                config=cfg,
            )
            if isinstance(res, dict) and res.get("bypass"):
                return {}

            trace, _dash = res
            rc = trace.run_context or {}
            transitions = getattr(trace, "transitions", None)
            transition_count = len(transitions) if isinstance(transitions, list) else 0
            last_transition = str(transitions[-1])[:120] if transition_count else ""
            risk = getattr(trace, "risk", None)
            execution = getattr(trace, "execution", None)
            return {
                "brain_trace_enabled": True,
                "brain_trace_id": trace.brain_pipeline_id or "",
                "brain_trace_path": str(cfg.trace_path),
                "brain_dry_run": bool(rc.get("dry_run")),
                "brain_risk_level": getattr(getattr(risk, "level", None), "value", getattr(risk, "level", None))
                if risk
                else None,
                "brain_tda_used": trace.think_decide_act_trace is not None,
                "brain_execution_success": bool(getattr(execution, "success", False)) if execution else False,
                "brain_transition_count": transition_count,
                "brain_last_transition": last_transition,
            }
        except Exception as exc:
            logger.warning("BrainPipeline operator chat trace failed (chat continues): %s", exc)
            return {"brain_trace_error": str(exc)[:400]}

    def _runtime_conversation_store(self) -> Any:
        if self._conversation_store is not None:
            return self._conversation_store
        try:
            return get_default_conversation_store()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("conversation store unavailable: %s", exc)
            return None

    @staticmethod
    def _brain_meta_for_storage(meta: Dict[str, Any]) -> Dict[str, Any]:
        allow = {
            "brain_trace_enabled",
            "brain_trace_id",
            "brain_dry_run",
            "brain_tda_used",
            "brain_risk_level",
            "brain_execution_success",
            "brain_transition_count",
            "brain_last_transition",
            "brain_trace_error",
        }
        out: Dict[str, Any] = {}
        for k, v in (meta or {}).items():
            if k not in allow:
                continue
            if isinstance(v, (dict, list)):
                continue
            out[k] = v
        return out

    def _resolve_runtime_chat_conversation_id(self, data: Dict[str, Any]) -> str:
        conversation_id = data.get("conversation_id") or request.cookies.get("elysia_conversation_id")
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        return sanitize_conversation_id(str(conversation_id))

    def _make_runtime_operator_chat_responder(self, http_context: str):
        def responder(req: OperatorChatRequest) -> OperatorChatResponderResult:
            architect_reply = self._architect_chat(req.composed_prompt, http_context)
            if architect_reply is not None:
                return OperatorChatResponderResult(
                    reply_text=str(architect_reply.get("response", "")),
                    extra_fields={
                        k: v for k, v in architect_reply.items() if k != "response"
                    },
                )
            logger.info("Chat message received: %s", req.message)
            return OperatorChatResponderResult(
                reply_text=f"Echo: {req.message}",
                extra_fields={"status": "accepted", "fallback_echo": True},
            )

        return responder

    def _runtime_operator_chat_after_persist(
        self, message: str, http_context: str
    ) -> Callable[[str, str, str, Dict[str, Any], Dict[str, Any]], None]:
        def _after(
            _cid: str,
            _user: str,
            reply: str,
            brain_meta: Dict[str, Any],
            extra: Dict[str, Any],
        ) -> None:
            if extra.get("fallback_echo"):
                self._event_bus.emit(
                    "api",
                    "chat",
                    {"message": message, "context": http_context, **brain_meta},
                )
                return
            emit_payload: Dict[str, Any] = {
                "message": message,
                "context": http_context,
                "response": reply,
            }
            emit_payload.update(brain_meta)
            self._event_bus.emit("api", "chat", emit_payload)

        return _after

    def _jsonify_runtime_operator_chat_result(self, result: Any) -> Any:
        if not result.ok:
            return jsonify({"error": result.error or "chat failed"}), 500

        body: Dict[str, Any] = dict(result.extra or {})
        body.update(result.brain_metadata or {})
        body["conversation_id"] = result.conversation_id
        body["reply"] = result.reply
        body.setdefault("response", result.reply)

        resp = jsonify(body)
        resp.set_cookie(
            "elysia_conversation_id",
            result.conversation_id,
            max_age=365 * 24 * 3600,
            samesite="Lax",
            path="/",
        )
        return resp

    def _handle_runtime_general_chat_no_store(
        self,
        message: str,
        http_context: str,
        conversation_id: str,
    ) -> Any:
        """General chat when ConversationStore is unavailable (no persistence)."""
        brain_meta = self._maybe_run_brain_operator_chat_trace(message, http_context)

        architect_reply = self._architect_chat(message, http_context)
        if architect_reply is not None:
            try:
                if brain_meta:
                    architect_reply = dict(architect_reply)
                    architect_reply.update(brain_meta)
                response = architect_reply.get("response", "")
                architect_reply["conversation_id"] = conversation_id
                architect_reply["reply"] = response
                emit_payload: Dict[str, Any] = {
                    "message": message,
                    "context": http_context,
                    "response": response,
                }
                emit_payload.update(brain_meta)
                self._event_bus.emit("api", "chat", emit_payload)
                resp = jsonify(architect_reply)
                resp.set_cookie(
                    "elysia_conversation_id",
                    conversation_id,
                    max_age=365 * 24 * 3600,
                    samesite="Lax",
                    path="/",
                )
                return resp
            except Exception as e:
                logger.exception("Chat error")
                return jsonify({"error": str(e)}), 500

        logger.info("Chat message received: %s", message)
        self._event_bus.emit(
            "api",
            "chat",
            {"message": message, "context": http_context, **brain_meta},
        )
        response_payload: Dict[str, Any] = {
            "response": f"Echo: {message}",
            "status": "accepted",
            "conversation_id": conversation_id,
            "reply": f"Echo: {message}",
        }
        response_payload.update(brain_meta)
        resp = jsonify(response_payload)
        resp.set_cookie(
            "elysia_conversation_id",
            conversation_id,
            max_age=365 * 24 * 3600,
            samesite="Lax",
            path="/",
        )
        return resp

    def _handle_runtime_general_chat(
        self,
        message: str,
        http_context: str,
        conversation_id: str,
    ) -> Any:
        store = self._runtime_conversation_store()
        if store is None:
            return self._handle_runtime_general_chat_no_store(
                message, http_context, conversation_id
            )

        result = run_operator_chat_turn(
            message,
            conversation_id=conversation_id,
            conversation_store=store,
            responder=self._make_runtime_operator_chat_responder(http_context),
            brain_trace_callback=self._maybe_run_brain_operator_chat_trace,
            after_persist_callback=self._runtime_operator_chat_after_persist(
                message, http_context
            ),
            history_limit=20,
            history_char_limit=8000,
            http_context=http_context,
            source_entrypoint="operator_chat",
        )
        return self._jsonify_runtime_operator_chat_result(result)

    def _setup_routes(self) -> None:
        @self._app.route("/api/status", methods=["GET"])
        def api_status():
            """Status endpoint - optimized for fast response."""
            try:
                status = self._status_provider()
                
                # Ensure response is always valid JSON
                if not isinstance(status, dict):
                    status = {"error": "Invalid status format"}
                
                return jsonify(status)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Status endpoint failure")
                # Return minimal status even on error
                return jsonify({
                    "error": str(exc),
                    "components": {"api_server": True},
                    "running": True,
                }), 500

        @self._app.route("/api/events", methods=["GET"])
        def api_events():
            limit = min(int(request.args.get("limit", 50)), 200)
            events = self._event_bus.get_recent_events(limit=limit)
            return jsonify({"events": events})

        @self._app.route("/api/chat", methods=["POST"])
        def api_chat():
            data = request.get_json(force=True, silent=True) or {}
            message = data.get("message", "").strip()
            context = data.get("context", "general")
            if not message:
                return jsonify({"error": "message is required"}), 400

            # Route to appropriate handler based on context
            if context.startswith("proposal:"):
                proposal_id = context.split(":", 1)[1]
                # Handle proposal-specific chat
                if self._proposal_system:
                    proposal = self._proposal_system.get_proposal(proposal_id)
                    if proposal:
                        response = f"Proposal '{proposal.get('title', proposal_id)}' status: {proposal.get('status', 'unknown')}"
                        self._event_bus.emit("api", "chat", {"message": message, "context": context, "response": response})
                        return jsonify({"response": response, "context": context})
                    return jsonify({"error": "Proposal not found"}), 404
                return jsonify({"error": "Proposal system not available"}), 503

            conversation_id = self._resolve_runtime_chat_conversation_id(data)
            return self._handle_runtime_general_chat(message, context, conversation_id)

        @self._app.route("/api/chat/history", methods=["GET"])
        def api_chat_history():
            """Bounded chat history for the operator UI (same store as POST /api/chat)."""
            store = self._runtime_conversation_store()
            conversation_id = (
                request.args.get("conversation_id")
                or request.args.get("session_id")
                or request.cookies.get("elysia_conversation_id")
                or "control_panel"
            )
            body, code = _safe_stack_responses.build_chat_history_response(
                store, str(conversation_id)
            )
            return jsonify(body), code

        @self._app.route("/api/chat/history", methods=["DELETE"])
        def api_chat_history_clear():
            store = self._runtime_conversation_store()
            data = request.get_json(force=True, silent=True) or {}
            conversation_id = (
                data.get("conversation_id")
                or data.get("session_id")
                or request.args.get("conversation_id")
                or request.cookies.get("elysia_conversation_id")
                or "control_panel"
            )
            body, code = _safe_stack_responses.build_chat_history_clear_response(
                store, str(conversation_id)
            )
            return jsonify(body), code

        @self._app.route("/api/conversations", methods=["GET"])
        def api_conversations_list():
            body, code = _safe_stack_responses.build_conversations_list_response(
                self._runtime_conversation_store()
            )
            return jsonify(body), code

        @self._app.route("/api/conversations", methods=["POST"])
        def api_conversations_create():
            body, code = _safe_stack_responses.build_conversation_create_response(
                self._runtime_conversation_store()
            )
            return jsonify(body), code

        @self._app.route("/api/conversations/<conversation_id>", methods=["GET"])
        def api_conversations_get(conversation_id: str):
            body, code = _safe_stack_responses.build_conversation_detail_response(
                self._runtime_conversation_store(), conversation_id
            )
            return jsonify(body), code

        @self._app.route("/api/conversations/<conversation_id>/messages", methods=["POST"])
        def api_conversations_append(conversation_id: str):
            store = self._runtime_conversation_store()
            if store is None:
                return jsonify({"success": False, "error": "conversation store unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            role = str(body.get("role") or "user").strip().lower()
            content = str(body.get("content") or "").strip()
            if not content:
                return jsonify({"success": False, "error": "content is required"}), 400
            cid = sanitize_conversation_id(conversation_id)
            msg = store.append_message(cid, role=role, content=content)
            return jsonify({"success": True, "message": msg})

        @self._app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
        def api_conversations_delete(conversation_id: str):
            body, code = _safe_stack_responses.build_conversation_delete_response(
                self._runtime_conversation_store(), conversation_id
            )
            return jsonify(body), code

        @self._app.route("/api/ping", methods=["GET"])
        def api_ping():
            return jsonify({"status": "ok"})

        @self._app.route("/api/brain/trace/latest", methods=["GET"])
        def api_brain_trace_latest():
            """Sanitized summary of the latest persisted BrainPipeline trace (read-only, no LLM)."""
            body, code = _safe_stack_responses.build_brain_trace_latest_response()
            return jsonify(body), code

        @self._app.route("/api/self-improvement/proposals", methods=["GET"])
        def api_self_improvement_proposals_list():
            """List self-improvement proposals (review-only; no code execution)."""
            limit = min(max(int(request.args.get("limit", 50)), 1), 200)
            body, code = _safe_stack_responses.build_self_improvement_proposals_list_response(
                self._self_improvement_queue_impl(), limit=limit
            )
            return jsonify(body), code

        @self._app.route("/api/self-improvement/proposals/<proposal_id>", methods=["GET"])
        def api_self_improvement_proposal_get(proposal_id: str):
            body, code = _safe_stack_responses.build_self_improvement_proposal_detail_response(
                self._self_improvement_queue_impl(), proposal_id
            )
            return jsonify(body), code

        @self._app.route("/api/self-improvement/proposals/<proposal_id>/status", methods=["POST"])
        def api_self_improvement_proposal_status(proposal_id: str):
            body_json = request.get_json(force=True, silent=True) or {}
            status = str(body_json.get("status") or "").strip().lower()
            note = body_json.get("note")
            body, code = _safe_stack_responses.build_self_improvement_proposal_status_update_response(
                self._self_improvement_queue_impl(),
                proposal_id,
                status,
                note=str(note) if note is not None else None,
            )
            return jsonify(body), code

        @self._app.route(
            "/api/self-improvement/proposals/<proposal_id>/export_prompt",
            methods=["GET"],
        )
        def api_self_improvement_proposal_export_prompt(proposal_id: str):
            """Export a copyable Cursor/Codex prompt (text only; no execution)."""
            body, code = _safe_stack_responses.build_self_improvement_prompt_export_response(
                self._self_improvement_queue_impl(),
                proposal_id,
                target=request.args.get("target", "cursor"),
            )
            return jsonify(body), code

        @self._app.route("/api/prompt-contracts/status", methods=["GET"])
        def api_prompt_contracts_status():
            """Read-only prompt-contract config and latest validation summary."""
            body, code = _safe_stack_responses.build_prompt_contracts_status_response()
            return jsonify(body), code

        @self._app.route("/api/governance/operator-confirmations", methods=["GET"])
        def api_governance_operator_confirmations_list():
            """Read-only operator confirmation records and live-exec governance flags."""
            try:
                limit = min(max(int(request.args.get("limit", 25)), 1), 50)
            except (TypeError, ValueError):
                limit = 25
            body, code = _safe_stack_responses.build_operator_confirmations_list_response(
                limit=limit,
                conversation_id=request.args.get("conversation_id"),
                status_filter=request.args.get("status"),
            )
            return jsonify(body), code

        @self._app.route(
            "/api/governance/operator-confirmations/<operator_confirmation_id>",
            methods=["GET"],
        )
        def api_governance_operator_confirmation_detail(operator_confirmation_id: str):
            """Read-only detail for one operator confirmation record."""
            body, code = _safe_stack_responses.build_operator_confirmation_detail_response(
                operator_confirmation_id
            )
            return jsonify(body), code

        @self._app.route("/api/memory/ranking/summary", methods=["GET"])
        def api_memory_ranking_summary():
            """Read-only advisory memory ranking summary (no mutation)."""
            try:
                limit = min(max(int(request.args.get("limit", 10)), 1), 50)
            except (TypeError, ValueError):
                limit = 10
            body, code = _safe_stack_responses.build_memory_ranking_summary_response(
                conversation_store=self._runtime_conversation_store(),
                limit=limit,
            )
            return jsonify(body), code

        # Proposal endpoints
        @self._app.route("/api/proposals", methods=["GET"])
        def api_list_proposals():
            """List all proposals, optionally filtered by status."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            status_filter = request.args.get("status")
            proposals = self._proposal_system.list_proposals(status_filter=status_filter)
            return jsonify({"proposals": proposals, "count": len(proposals)})

        @self._app.route("/api/proposals/<proposal_id>", methods=["GET"])
        def api_get_proposal(proposal_id: str):
            """Get a specific proposal by ID."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            proposal = self._proposal_system.get_proposal(proposal_id)
            if not proposal:
                return jsonify({"error": "Proposal not found"}), 404

            return jsonify(proposal)

        @self._app.route("/api/proposals/<proposal_id>/approve", methods=["POST"])
        def api_approve_proposal(proposal_id: str):
            """Approve a proposal."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            data = request.get_json(force=True, silent=True) or {}
            approver = data.get("approver", "api_user")

            success, error = self._proposal_system.approve_proposal(proposal_id, approver)
            if success:
                return jsonify({"status": "approved", "proposal_id": proposal_id})
            return jsonify({"error": error or "Failed to approve"}), 400

        @self._app.route("/api/proposals/<proposal_id>/reject", methods=["POST"])
        def api_reject_proposal(proposal_id: str):
            """Reject a proposal."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            data = request.get_json(force=True, silent=True) or {}
            reason = data.get("reason", "No reason provided")
            rejector = data.get("rejector", "api_user")

            success, error = self._proposal_system.reject_proposal(proposal_id, reason, rejector)
            if success:
                return jsonify({"status": "rejected", "proposal_id": proposal_id, "reason": reason})
            return jsonify({"error": error or "Failed to reject"}), 400

        @self._app.route("/api/proposals/<proposal_id>/status", methods=["POST"])
        def api_transition_status(proposal_id: str):
            """Transition a proposal to a new status."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            data = request.get_json(force=True, silent=True) or {}
            new_status = data.get("status")
            actor = data.get("actor", "api_user")

            if not new_status:
                return jsonify({"error": "status is required"}), 400

            success, error = self._proposal_system.transition_status(proposal_id, new_status, actor)
            if success:
                return jsonify({"status": "updated", "proposal_id": proposal_id, "new_status": new_status})
            return jsonify({"error": error or "Failed to transition status"}), 400

        # WebScout endpoints
        @self._app.route("/api/webscout/research", methods=["POST"])
        def api_webscout_research():
            """Request WebScout to research a topic."""
            if not self._webscout:
                return jsonify({"error": "WebScout not available"}), 503

            data = request.get_json(force=True, silent=True) or {}
            topic = data.get("topic", "").strip()
            domain = data.get("domain", "elysia_core")
            result = self._webscout.research_topic(topic, domain)
            return jsonify(result)

        # Implementer endpoints
        @self._app.route("/api/proposals/<proposal_id>/implement", methods=["POST"])
        def api_implement_proposal(proposal_id: str):
            """Trigger implementation for a specific proposal."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            data = request.get_json(force=True, silent=True) or {}
            dry_run = data.get("dry_run", False)

            try:
                from ..agents.implementer import ImplementerAgent
                from pathlib import Path

                implementer = ImplementerAgent(
                    repo_root=Path("."),
                    proposal_system=self._proposal_system,
                    event_bus=self._event_bus,
                    dry_run=dry_run,
                )

                result = implementer.run_for_proposal(proposal_id)
                return jsonify(result)
            except ImportError:
                return jsonify({"error": "Implementer agent not available"}), 503
            except Exception as e:
                logger.exception("Implementation error")
                return jsonify({"error": str(e)}), 500


        @self._app.route("/api/proposals/<proposal_id>/implementation", methods=["GET"])
        def api_get_implementation_status(proposal_id: str):
            """Get implementation status for a proposal."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            proposal = self._proposal_system.get_proposal(proposal_id)
            if not proposal:
                return jsonify({"error": "Proposal not found"}), 404

            # Extract implementation-related fields
            impl_info = {
                "implementation_status": proposal.get("implementation_status", "not_started"),
                "last_implemented_at": proposal.get("last_implemented_at"),
                "last_implementation_result": proposal.get("last_implementation_result"),
            }

            # Get recent implementer history entries
            history = proposal.get("history", [])
            implementer_entries = [
                h for h in history if h.get("actor") == "Elysia-Implementer"
            ]
            impl_info["recent_history"] = sorted(
                implementer_entries, key=lambda x: x.get("timestamp", ""), reverse=True
            )[:10]

            return jsonify(impl_info)

    def start(self) -> None:
        if self._running:
            logger.warning("API server already running")
            return

        def _run_server():
            logger.info("API server listening on http://%s:%s", self.host, self.port)
            try:
                # Use Werkzeug's make_server for proper shutdown support
                self._server = make_server(
                    self.host, self.port, self._app, threaded=True
                )
                self._server.serve_forever()
            except Exception as e:
                logger.exception("Server error: %s", e)
                self._running = False

        self._thread = threading.Thread(target=_run_server, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        
        logger.info("Stopping API server...")
        self._running = False
        
        if self._server:
            try:
                self._server.shutdown()
                logger.info("API server stopped successfully")
            except Exception as e:
                logger.warning("Error stopping server: %s", e)
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                logger.warning("Server thread did not stop within timeout")

    @property
    def running(self) -> bool:
        return self._running

