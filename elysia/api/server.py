"""Minimal REST API surface for the Elysia runtime."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

try:  # pragma: no cover - optional dependency
    from flask_cors import CORS
except ImportError:  # pragma: no cover
    CORS = None  # type: ignore

from ..events import EventBus

logger = logging.getLogger(__name__)


def _safe_proposal_id(proposal_id: str) -> bool:
    """Accept one path segment. Reject blanks and parent-directory ids."""
    if not isinstance(proposal_id, str) or proposal_id in {"", ".", ".."}:
        return False
    if "/" in proposal_id or "\\" in proposal_id or "\x00" in proposal_id:
        return False
    return Path(proposal_id).name == proposal_id


def _invalid_proposal_id_response(proposal_id: str):
    return jsonify({"error": "invalid proposal id", "proposal_id": proposal_id}), 400


def _unreadable_proposal_response(proposal_id: str):
    return (
        jsonify(
            {"error": "Proposal metadata is unreadable", "proposal_id": proposal_id}
        ),
        500,
    )


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
    ):
        self._status_provider = status_provider
        self._event_bus = event_bus
        self._proposal_system = proposal_system
        self._webscout = webscout
        self._architect = architect
        self._implementer = implementer
        self.host = host
        self.port = port
        self._app = Flask(__name__)
        if CORS:
            CORS(self._app)

        self._thread: Optional[threading.Thread] = None
        self._server: Optional[Any] = None
        self._running = False
        self._setup_routes()

    def _proposal_root(self) -> Optional[Path]:
        root = getattr(self._proposal_system, "proposals_root", None)
        if root is None:
            return None
        return Path(root)

    def _metadata_exists(self, proposal_id: str) -> bool:
        root = self._proposal_root()
        if root is None:
            return False
        try:
            return (root / proposal_id / "metadata.json").exists()
        except OSError:
            return True

    def _read_proposal(self, proposal_id: str):
        """Return ``(metadata, error_response)``.

        ``metadata`` is a dict when the file is a JSON object. ``error_response``
        is set for an unsafe id or for metadata that exists but is not a JSON
        object. Both values are ``None`` when the proposal is absent.
        """
        if not _safe_proposal_id(proposal_id):
            return None, _invalid_proposal_id_response(proposal_id)
        if not self._proposal_system:
            return None, (jsonify({"error": "Proposal system not available"}), 503)
        try:
            loaded = self._proposal_system.get_proposal(proposal_id)
        except Exception:
            logger.exception("Proposal read failed for %s", proposal_id)
            return None, _unreadable_proposal_response(proposal_id)
        if isinstance(loaded, dict):
            return loaded, None
        if self._metadata_exists(proposal_id):
            return None, _unreadable_proposal_response(proposal_id)
        return None, None

    def _list_proposals_by_directory(self, status_filter: Optional[str]) -> List[Dict[str, Any]]:
        """Read each direct child when ``list_proposals`` cannot return a page."""
        root = self._proposal_root()
        if root is None or not root.is_dir():
            return []
        found: List[Dict[str, Any]] = []
        for child in root.iterdir():
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            if not is_dir or not _safe_proposal_id(child.name):
                continue
            loaded, error = self._read_proposal(child.name)
            if error is not None or not isinstance(loaded, dict):
                continue
            if status_filter and loaded.get("status") != status_filter:
                continue
            found.append(loaded)
        return sorted(
            found,
            key=lambda proposal: proposal.get("created_at")
            if isinstance(proposal.get("created_at"), str)
            else "",
            reverse=True,
        )

    def _unreadable_proposal_ids(self) -> List[str]:
        root = self._proposal_root()
        if root is None or not root.is_dir():
            return []
        found: List[str] = []
        for child in root.iterdir():
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            if not is_dir:
                continue
            name = child.name
            if not _safe_proposal_id(name):
                found.append(name)
                continue
            _loaded, error = self._read_proposal(name)
            if error is not None and error[1] == 500:
                found.append(name)
        return sorted(found)

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
                    proposal, error_response = self._read_proposal(proposal_id)
                    if error_response is not None:
                        return error_response
                    if proposal:
                        response = f"Proposal '{proposal.get('title', proposal_id)}' status: {proposal.get('status', 'unknown')}"
                        self._event_bus.emit("api", "chat", {"message": message, "context": context, "response": response})
                        return jsonify({"response": response, "context": context})
                    return jsonify({"error": "Proposal not found"}), 404
                return jsonify({"error": "Proposal system not available"}), 503

            # General chat - try Architect-Core if available
            if self._architect:
                try:
                    # This would call Architect-Core's chat interface
                    # For now, return a placeholder
                    response = f"Echo: {message}"
                    self._event_bus.emit("api", "chat", {"message": message, "context": context, "response": response})
                    return jsonify({"response": response, "context": context})
                except Exception as e:
                    logger.exception("Chat error")
                    return jsonify({"error": str(e)}), 500

            # Fallback echo
            logger.info("Chat message received: %s", message)
            self._event_bus.emit("api", "chat", {"message": message, "context": context})
            return jsonify({"response": f"Echo: {message}", "status": "accepted"})

        @self._app.route("/api/ping", methods=["GET"])
        def api_ping():
            return jsonify({"status": "ok"})

        # Proposal endpoints
        @self._app.route("/api/proposals", methods=["GET"])
        def api_list_proposals():
            """List all proposals, optionally filtered by status."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            status_filter = request.args.get("status")
            try:
                proposals = self._proposal_system.list_proposals(status_filter=status_filter)
            except Exception as exc:
                logger.warning(
                    "Proposal list failed (%s); reading each proposal directory",
                    exc,
                )
                try:
                    proposals = self._list_proposals_by_directory(status_filter)
                except Exception:
                    logger.exception("Proposal directory read failed")
                    return (
                        jsonify(
                            {
                                "error": "Proposal list failed",
                                "proposals": [],
                                "count": 0,
                                "unreadable": [],
                            }
                        ),
                        500,
                    )
            if not isinstance(proposals, list):
                return (
                    jsonify(
                        {
                            "error": "Proposal list failed",
                            "proposals": [],
                            "count": 0,
                            "unreadable": [],
                        }
                    ),
                    500,
                )
            try:
                unreadable = self._unreadable_proposal_ids()
            except Exception:
                logger.exception("Unreadable proposal scan failed")
                return (
                    jsonify(
                        {
                            "error": "Proposal list failed",
                            "proposals": [],
                            "count": 0,
                            "unreadable": [],
                        }
                    ),
                    500,
                )
            readable = [item for item in proposals if isinstance(item, dict)]
            return jsonify(
                {"proposals": readable, "count": len(readable), "unreadable": unreadable}
            )

        @self._app.route("/api/proposals/<proposal_id>", methods=["GET"])
        def api_get_proposal(proposal_id: str):
            """Get a specific proposal by ID."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            proposal, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response
            if not proposal:
                return jsonify({"error": "Proposal not found"}), 404

            return jsonify(proposal)

        @self._app.route("/api/proposals/<proposal_id>/approve", methods=["POST"])
        def api_approve_proposal(proposal_id: str):
            """Approve a proposal."""
            if not self._proposal_system:
                return jsonify({"error": "Proposal system not available"}), 503

            _loaded, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response

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

            _loaded, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response

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

            _loaded, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response

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

            if not topic:
                return jsonify({"error": "topic is required"}), 400

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

            _loaded, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response

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

            proposal, error_response = self._read_proposal(proposal_id)
            if error_response is not None:
                return error_response
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

