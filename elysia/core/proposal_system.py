"""Proposal system wrapper integrating ProposalValidator, LifecycleManager, and Watcher."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..events import EventBus

logger = logging.getLogger(__name__)


class ProposalValidator:
    """Validates proposal structure and metadata schema."""

    def __init__(self, proposals_root: Path):
        self.proposals_root = proposals_root

    def validate_structure(self, proposal_path: Path) -> tuple[bool, Optional[str]]:
        """Validate folder structure of a proposal."""
        if not proposal_path.exists():
            return False, "Proposal directory does not exist"

        metadata_file = proposal_path / "metadata.json"
        if not metadata_file.exists():
            return False, "metadata.json missing"

        return True, None

    def validate_metadata(self, metadata: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate metadata.json schema."""
        required_fields = ["proposal_id", "title", "status", "created_by", "created_at"]
        for field in required_fields:
            if field not in metadata:
                return False, f"Missing required field: {field}"

        valid_statuses = [
            "research",
            "design",
            "proposal",
            "approved",
            "rejected",
            "implemented",
            "in_implementation",
            "implementation_failed",
        ]
        if metadata.get("status") not in valid_statuses:
            return False, f"Invalid status: {metadata.get('status')}"

        # Validate implementation_status if present
        implementation_status = metadata.get("implementation_status")
        if implementation_status is not None:
            valid_impl_statuses = ["pending", "in_progress", "completed", "failed", "not_started"]
            if implementation_status not in valid_impl_statuses:
                return False, f"Invalid implementation_status: {implementation_status}"

        return True, None

    def validate_proposal(self, proposal_path: Path) -> tuple[bool, Optional[str]]:
        """Full validation of a proposal."""
        valid, error = self.validate_structure(proposal_path)
        if not valid:
            return valid, error

        try:
            metadata_file = proposal_path / "metadata.json"
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"Failed to read metadata: {e}"

        return self.validate_metadata(metadata)


class ProposalLifecycleManager:
    """Manages proposal lifecycle transitions."""

    def __init__(self, proposals_root: Path, event_bus: Optional[EventBus] = None):
        self.proposals_root = proposals_root
        self.event_bus = event_bus

    def _load_metadata(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Load metadata for a proposal."""
        proposal_path = self.proposals_root / proposal_id
        metadata_file = proposal_path / "metadata.json"
        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_metadata(self, proposal_id: str, metadata: Dict[str, Any]) -> bool:
        """Save metadata for a proposal."""
        proposal_path = self.proposals_root / proposal_id
        proposal_path.mkdir(parents=True, exist_ok=True)
        metadata_file = proposal_path / "metadata.json"

        try:
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save metadata for {proposal_id}: {e}")
            return False

    def _add_history_entry(
        self, metadata: Dict[str, Any], actor: str, change_summary: str, details: Optional[Any] = None
    ):
        """Add a history entry to metadata."""
        if "history" not in metadata:
            metadata["history"] = []

        metadata["history"].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "change_summary": change_summary,
                "details": details,
            }
        )

    def transition_status(
        self, proposal_id: str, new_status: str, actor: str = "system"
    ) -> tuple[bool, Optional[str]]:
        """Transition a proposal to a new status."""
        metadata = self._load_metadata(proposal_id)
        if not metadata:
            return False, "Proposal not found"

        old_status = metadata.get("status")
        if old_status == new_status:
            return True, "Status unchanged"

        valid_transitions = {
            "research": ["design"],
            "design": ["proposal"],
            "proposal": ["approved", "rejected"],
            "approved": ["in_implementation", "rejected"],
            "in_implementation": ["implemented", "implementation_failed", "approved"],
            "implementation_failed": ["approved", "rejected"],
            "rejected": [],
            "implemented": [],
        }

        allowed = valid_transitions.get(old_status, [])
        if new_status not in allowed:
            return False, f"Invalid transition from {old_status} to {new_status}"

        metadata["status"] = new_status
        metadata["last_updated_by"] = actor
        self._add_history_entry(
            metadata, actor, f"Status changed from {old_status} to {new_status}"
        )

        if self._save_metadata(proposal_id, metadata):
            if self.event_bus:
                self.event_bus.emit(
                    "proposal_system",
                    "status_changed",
                    {"proposal_id": proposal_id, "from": old_status, "to": new_status, "actor": actor},
                )
            return True, None

        return False, "Failed to save metadata"

    def approve_proposal(self, proposal_id: str, approver: str) -> tuple[bool, Optional[str]]:
        """Approve a proposal."""
        metadata = self._load_metadata(proposal_id)
        if not metadata:
            return False, "Proposal not found"

        metadata["approval_status"] = "approved"
        metadata["approved_by"] = approver
        metadata["approved_at"] = datetime.now(timezone.utc).isoformat()
        metadata["last_updated_by"] = approver
        self._add_history_entry(metadata, approver, "Proposal approved")

        success, error = self.transition_status(proposal_id, "approved", actor=approver)
        if success:
            return True, None
        return False, error or "Failed to transition status"

    def reject_proposal(self, proposal_id: str, reason: str, rejector: str) -> tuple[bool, Optional[str]]:
        """Reject a proposal."""
        metadata = self._load_metadata(proposal_id)
        if not metadata:
            return False, "Proposal not found"

        metadata["approval_status"] = "rejected"
        metadata["rejection_reason"] = reason
        metadata["last_updated_by"] = rejector
        self._add_history_entry(metadata, rejector, f"Proposal rejected: {reason}")

        success, error = self.transition_status(proposal_id, "rejected", actor=rejector)
        if success:
            return True, None
        return False, error or "Failed to transition status"


class ProposalWatcher:
    """Monitors proposals/ folder for new/updated proposals."""

    def __init__(
        self,
        proposals_root: Path,
        validator: ProposalValidator,
        lifecycle_manager: ProposalLifecycleManager,
        event_bus: Optional[EventBus] = None,
        check_interval: float = 5.0,
    ):
        self.proposals_root = proposals_root
        self.validator = validator
        self.lifecycle_manager = lifecycle_manager
        self.event_bus = event_bus
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_proposals: set[str] = set()

    def _scan_proposals(self):
        """Scan for new or updated proposals."""
        if not self.proposals_root.exists():
            return

        current_proposals = {
            p.name for p in self.proposals_root.iterdir() if p.is_dir() and (p / "metadata.json").exists()
        }

        # Detect new proposals
        new_proposals = current_proposals - self._known_proposals
        for proposal_id in new_proposals:
            valid, error = self.validator.validate_proposal(self.proposals_root / proposal_id)
            if valid:
                if self.event_bus:
                    self.event_bus.emit(
                        "proposal_system",
                        "proposal_created",
                        {"proposal_id": proposal_id},
                    )
                logger.info(f"Detected new proposal: {proposal_id}")
            else:
                logger.warning(f"Invalid proposal {proposal_id}: {error}")

        self._known_proposals = current_proposals

    def start(self):
        """Start watching for proposals."""
        if self._running:
            return

        self._running = True
        self._known_proposals = set()

        def _watch_loop():
            while self._running:
                try:
                    self._scan_proposals()
                except Exception as e:
                    logger.exception(f"Error scanning proposals: {e}")
                time.sleep(self.check_interval)

        self._thread = threading.Thread(target=_watch_loop, daemon=True)
        self._thread.start()
        logger.info("ProposalWatcher started")

    def stop(self):
        """Stop watching for proposals."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


class ProposalSystem:
    """Unified proposal system integrating validator, lifecycle manager, and watcher."""

    def __init__(
        self,
        proposals_root: Path,
        event_bus: Optional[EventBus] = None,
        enable_watcher: bool = True,
    ):
        self.proposals_root = Path(proposals_root).resolve()
        self.proposals_root.mkdir(parents=True, exist_ok=True)
        self.event_bus = event_bus

        self.validator = ProposalValidator(self.proposals_root)
        self.lifecycle_manager = ProposalLifecycleManager(self.proposals_root, event_bus)
        self.watcher = ProposalWatcher(
            self.proposals_root, self.validator, self.lifecycle_manager, event_bus
        ) if enable_watcher else None

        if self.watcher:
            self.watcher.start()

        if self.event_bus:
            self.event_bus.emit(
                "proposal_system",
                "initialized",
                {"root": str(self.proposals_root), "watcher_enabled": enable_watcher},
            )

    def list_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all proposals, optionally filtered by status."""
        proposals = []
        if not self.proposals_root.exists():
            return proposals

        for proposal_dir in self.proposals_root.iterdir():
            if not proposal_dir.is_dir():
                continue

            metadata_file = proposal_dir / "metadata.json"
            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)

                if status_filter and metadata.get("status") != status_filter:
                    continue

                proposals.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to load proposal {proposal_dir.name}: {e}")

        return sorted(proposals, key=lambda p: p.get("created_at", ""), reverse=True)

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific proposal by ID."""
        proposal_path = self.proposals_root / proposal_id
        metadata_file = proposal_path / "metadata.json"

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def approve_proposal(self, proposal_id: str, approver: str) -> tuple[bool, Optional[str]]:
        """Approve a proposal."""
        return self.lifecycle_manager.approve_proposal(proposal_id, approver)

    def reject_proposal(self, proposal_id: str, reason: str, rejector: str) -> tuple[bool, Optional[str]]:
        """Reject a proposal."""
        return self.lifecycle_manager.reject_proposal(proposal_id, reason, rejector)

    def transition_status(
        self, proposal_id: str, new_status: str, actor: str = "system"
    ) -> tuple[bool, Optional[str]]:
        """Transition a proposal to a new status."""
        return self.lifecycle_manager.transition_status(proposal_id, new_status, actor)

    def shutdown(self):
        """Shutdown the proposal system."""
        if self.watcher:
            self.watcher.stop()

