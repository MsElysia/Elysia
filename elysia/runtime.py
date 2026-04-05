"""Unified runtime orchestrator."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from .api.server import RuntimeAPIServer
from .config import RuntimeConfig
from .events import EventBus
from .logging_config import setup_logging

if TYPE_CHECKING:
    from .core.proposal_system import ProposalSystem
    from .agents.webscout import WebScoutAgent

logger = logging.getLogger(__name__)


class ElysiaRuntime:
    """High-level orchestration layer for Architect-Core + agents + API."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.event_bus = EventBus()
        self._initialized = False
        self._running = False
        self._start_time: Optional[datetime] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

        self.architect = None
        self.proposal_system: Optional[ProposalSystem] = None
        self.webscout: Optional[WebScoutAgent] = None
        self.api_server: Optional[RuntimeAPIServer] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init(self) -> None:
        if self._initialized:
            return

        setup_logging(level=self.config.log_level)
        self._wire_event_logging()
        self._load_api_keys()

        self._init_architect()
        self._init_proposal_system()

        if self.config.enable_webscout:
            self._init_webscout()

        if self.config.enable_api:
            self._init_api_server()

        self._initialized = True
        self.event_bus.emit(
            "runtime", "initialized", {"mode": self.config.mode, "env": self.config.env}
        )

    def start(self) -> None:
        if not self._initialized:
            self.init()

        if self._running:
            logger.warning("Runtime already running")
            return

        self._start_time = datetime.now(timezone.utc)
        self._heartbeat_stop.clear()
        self._start_heartbeat()

        if self.api_server:
            self.api_server.start()

        if self.webscout:
            self.webscout.start_background_loop()

        self._running = True
        logger.info("ElysiaRuntime started (mode=%s)", self.config.mode)
        self.event_bus.emit("runtime", "started", {"mode": self.config.mode})

        # Keep the main thread alive when invoked via CLI.
        # Callers embedding the runtime can ignore this and manage their own loop.

    def stop(self) -> None:
        if not self._running:
            return

        logger.info("Stopping ElysiaRuntime...")
        self._running = False

        if self.webscout:
            self.webscout.stop()

        if self.api_server:
            self.api_server.stop()

        if self.proposal_system:
            try:
                self.proposal_system.shutdown()
            except Exception:  # pragma: no cover
                logger.exception("Failed to shutdown proposal system")

        self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)

        self.event_bus.emit("runtime", "stopped", {})

    # ------------------------------------------------------------------
    # Component initialization helpers
    # ------------------------------------------------------------------
    def _wire_event_logging(self) -> None:
        log = logging.getLogger("elysia.events")

        def _log_event(event):
            log.info("[%s] %s %s", event.source, event.type, json.dumps(event.payload))

        self.event_bus.subscribe(_log_event)

    def _load_api_keys(self) -> None:
        try:
            from load_api_keys import load_api_keys

            loaded = load_api_keys()
            if loaded:
                logger.info("Loaded %s API keys", len(loaded))
        except Exception as exc:
            logger.warning("API key loader unavailable: %s", exc)

    def _init_architect(self) -> None:
        try:
            from architect_core import ArchitectCore

            self.architect = ArchitectCore()
            self.event_bus.emit("architect", "initialized", {"status": "ok"})
        except Exception as exc:
            logger.warning("Architect-Core unavailable: %s", exc)
            self.architect = None

    def _init_proposal_system(self) -> None:
        try:
            from .core.proposal_system import ProposalSystem

            self.proposal_system = ProposalSystem(
                proposals_root=Path(self.config.proposals_root),
                event_bus=self.event_bus,
                enable_watcher=True,
            )
        except Exception as exc:
            logger.error("Failed to initialize proposal system: %s", exc)
            raise

    def _init_webscout(self) -> None:
        if not self.proposal_system:
            logger.warning("Proposal system not available, cannot initialize WebScout")
            self.webscout = None
            return

        try:
            from .agents.webscout import WebScoutAgent

            self.webscout = WebScoutAgent(
                proposals_root=Path(self.config.proposals_root),
                proposal_system=self.proposal_system,
                event_bus=self.event_bus,
                require_api_keys=self.config.require_api_keys,
            )
        except Exception as exc:
            logger.warning("WebScout unavailable: %s", exc)
            self.webscout = None

    def _init_api_server(self) -> None:
        self.api_server = RuntimeAPIServer(
            status_provider=self.get_status,
            event_bus=self.event_bus,
            host=self.config.api_host,
            port=self.config.api_port,
            proposal_system=self.proposal_system,
            webscout=self.webscout,
            architect=self.architect,
        )

    def _start_heartbeat(self) -> None:
        def _loop():
            while not self._heartbeat_stop.is_set():
                payload = {
                    "running": self._running,
                    "uptime": self.get_uptime_seconds(),
                    "proposals": len(
                        self.proposal_system.list_proposals()
                    )
                    if self.proposal_system
                    else 0,
                }
                self.event_bus.emit("runtime", "heartbeat", payload)
                self._heartbeat_stop.wait(timeout=60)

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self._heartbeat_thread.start()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def get_uptime_seconds(self) -> float:
        if not self._start_time:
            return 0.0
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()

    def get_status(self) -> Dict[str, Any]:
        """Get runtime status - optimized for fast response (no proposal loading)."""
        # Fast path: just count proposal directories, don't load metadata
        proposal_count = 0
        if self.proposal_system:
            try:
                proposals_root = self.proposal_system.proposals_root
                if proposals_root.exists():
                    # Ultra-fast: just count directories with metadata.json
                    proposal_count = sum(
                        1 for p in proposals_root.iterdir()
                        if p.is_dir() and (p / "metadata.json").exists()
                    )
            except Exception as e:
                logger.debug(f"Error counting proposals: {e}")
        
        return {
            "mode": self.config.mode,
            "env": self.config.env,
            "running": self._running,
            "uptime_seconds": self.get_uptime_seconds(),
            "components": {
                "architect": bool(self.architect),
                "proposal_system": bool(self.proposal_system),
                "webscout": bool(self.webscout),
                "api_server": self.api_server.running if self.api_server else False,
            },
            "proposal_count": proposal_count,
            # Don't load proposals here - UI should call /api/proposals separately
        }

