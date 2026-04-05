"""WebScout agent wrapper for Elysia-WebScout integration."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.proposal_system import ProposalSystem
from ..events import EventBus

logger = logging.getLogger(__name__)


class WebScoutAgent:
    """Wrapper for Elysia-WebScout agent that creates proposals."""

    def __init__(
        self,
        proposals_root: Path,
        proposal_system: ProposalSystem,
        event_bus: Optional[EventBus] = None,
        require_api_keys: bool = False,
    ):
        self.proposals_root = Path(proposals_root)
        self.proposal_system = proposal_system
        self.event_bus = event_bus
        self.require_api_keys = require_api_keys

        self._running = False
        self._background_thread: Optional[threading.Thread] = None
        self._webscout_instance: Optional[Any] = None

        # Try to import the actual WebScout implementation
        self._init_webscout()

    def _init_webscout(self):
        """Initialize the WebScout agent instance."""
        try:
            # Try importing from project_guardian
            from project_guardian.webscout_agent import ElysiaWebScout

            self._webscout_instance = ElysiaWebScout(
                proposals_root=self.proposals_root,
                require_api_keys=self.require_api_keys,
            )
            logger.info("WebScout agent initialized")
            if self.event_bus:
                self.event_bus.emit("webscout", "initialized", {})
        except ImportError:
            logger.warning("ElysiaWebScout not available - WebScout functionality disabled")
            self._webscout_instance = None
        except Exception as e:
            logger.error(f"Failed to initialize WebScout: {e}")
            self._webscout_instance = None

    def start_background_loop(self):
        """Start WebScout background processing loop."""
        if self._running:
            logger.warning("WebScout already running")
            return

        if not self._webscout_instance:
            logger.warning("WebScout not available, cannot start background loop")
            return

        self._running = True

        def _background_loop():
            """Background loop for WebScout processing."""
            logger.info("WebScout background loop started")
            while self._running:
                try:
                    # Check for new research tasks or proposals to process
                    # This is a placeholder - actual implementation would
                    # integrate with WebScout's task queue
                    time.sleep(30)  # Check every 30 seconds

                    if self.event_bus:
                        self.event_bus.emit("webscout", "heartbeat", {"status": "running"})
                except Exception as e:
                    logger.exception(f"Error in WebScout background loop: {e}")
                    time.sleep(5)

        self._background_thread = threading.Thread(target=_background_loop, daemon=True)
        self._background_thread.start()

        if self.event_bus:
            self.event_bus.emit("webscout", "started", {})

    def stop(self):
        """Stop WebScout agent."""
        if not self._running:
            return

        logger.info("Stopping WebScout agent...")
        self._running = False

        if self._background_thread:
            self._background_thread.join(timeout=2)

        if self.event_bus:
            self.event_bus.emit("webscout", "stopped", {})

    def create_proposal(
        self, title: str, description: str, domain: str = "elysia_core", **kwargs
    ) -> Optional[str]:
        """
        Create a new proposal via WebScout.

        Returns proposal_id if successful, None otherwise.
        """
        if not self._webscout_instance:
            logger.error("WebScout not available")
            return None

        try:
            # This would call the actual WebScout implementation
            # For now, we'll emit an event and return None
            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "proposal_created",
                    {"title": title, "domain": domain},
                )
            logger.info(f"WebScout proposal creation requested: {title}")
            return None
        except Exception as e:
            logger.error(f"Failed to create proposal via WebScout: {e}")
            return None

    def research_topic(self, topic: str, domain: str = "elysia_core") -> Dict[str, Any]:
        """
        Request WebScout to research a topic and create a proposal.

        Returns a dict with status and proposal_id if created.
        """
        if not self._webscout_instance:
            return {"status": "error", "message": "WebScout not available"}

        try:
            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "research_started",
                    {"topic": topic, "domain": domain},
                )

            # This would trigger actual research
            # For now, return a placeholder response
            return {
                "status": "accepted",
                "topic": topic,
                "domain": domain,
                "message": "Research task queued",
            }
        except Exception as e:
            logger.error(f"Failed to start research: {e}")
            if self.event_bus:
                self.event_bus.emit(
                    "webscout",
                    "research_failed",
                    {"topic": topic, "error": str(e)},
                )
            return {"status": "error", "message": str(e)}

