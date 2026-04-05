#!/usr/bin/env python3
"""
Architect-Core Proposal System
Manages proposal lifecycle from research to implementation.
Integrates with Elysia-WebScout agent.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    from .proposal_domains import ProposalDomain, get_domain_config, validate_domain
except ImportError:
    from proposal_domains import ProposalDomain, get_domain_config, validate_domain

logger = logging.getLogger(__name__)


class ProposalValidator:
    """Validates proposal structure and content"""
    
    REQUIRED_FOLDERS = ["research", "design", "implementation"]
    REQUIRED_FILES = ["metadata.json", "README.md"]
    
    def validate_structure(self, proposal_path: Path) -> Dict[str, Any]:
        """
        Validate proposal folder structure.
        
        Returns:
            Dict with "valid" bool and "errors" list
        """
        errors = []
        
        if not proposal_path.exists():
            return {"valid": False, "errors": ["Proposal path does not exist"]}
        
        if not proposal_path.is_dir():
            return {"valid": False, "errors": ["Proposal path is not a directory"]}
        
        # Check required folders
        for folder in self.REQUIRED_FOLDERS:
            folder_path = proposal_path / folder
            if not folder_path.exists():
                errors.append(f"Missing required folder: {folder}")
            elif not folder_path.is_dir():
                errors.append(f"{folder} exists but is not a directory")
        
        # Check required files
        for file in self.REQUIRED_FILES:
            file_path = proposal_path / file
            if not file_path.exists():
                errors.append(f"Missing required file: {file}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def validate_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate metadata.json schema with strict rules.
        
        Returns:
            Dict with "valid" bool, "errors" list, and "warnings" list
        """
        errors = []
        warnings = []
        
        # Required fields for all proposals
        required_fields = [
            "proposal_id", "title", "description", "status",
            "created_by", "created_at", "updated_at", "schema_version"
        ]
        
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Missing required field: {field}")
        
        # Validate schema_version
        schema_version = metadata.get("schema_version", 0)
        if schema_version != 1:
            warnings.append(f"Schema version {schema_version} may not be supported. Expected: 1")
        
        # Validate status
        valid_statuses = [
            "research", "design", "proposal", "approved", "rejected", "implemented",
            "in_implementation", "implementation_failed", "implementation_partial",
            "rolled_back", "rework_required"
        ]
        status = metadata.get("status")
        if status not in valid_statuses:
            errors.append(f"Invalid status: {status}. Must be one of: {valid_statuses}")
        
        # Validate approval_status
        valid_approval_statuses = ["pending", "approved", "rejected"]
        approval_status = metadata.get("approval_status")
        if approval_status and approval_status not in valid_approval_statuses:
            errors.append(f"Invalid approval_status: {approval_status}")
        
        # Validate scoring fields
        impact_score = metadata.get("impact_score")
        if impact_score is not None:
            if not isinstance(impact_score, int) or impact_score < 1 or impact_score > 5:
                errors.append(f"impact_score must be an integer between 1-5, got: {impact_score}")
        else:
            warnings.append("impact_score not set. Required for priority calculation.")
        
        effort_score = metadata.get("effort_score")
        if effort_score is not None:
            if not isinstance(effort_score, int) or effort_score < 1 or effort_score > 5:
                errors.append(f"effort_score must be an integer between 1-5, got: {effort_score}")
        else:
            warnings.append("effort_score not set. Required for priority calculation.")
        
        # Validate risk_level
        valid_risk_levels = ["low", "medium", "high"]
        risk_level = metadata.get("risk_level")
        if risk_level and risk_level not in valid_risk_levels:
            errors.append(f"Invalid risk_level: {risk_level}. Must be one of: {valid_risk_levels}")
        
        # Validate priority
        valid_priorities = ["low", "medium", "high"]
        priority = metadata.get("priority")
        if priority and priority not in valid_priorities:
            errors.append(f"Invalid priority: {priority}. Must be one of: {valid_priorities}")
        
        # Validate domain (canonical domains)
        domain = metadata.get("domain")
        if not domain:
            errors.append("Domain is a required field. Must be one of the canonical domains.")
        else:
            is_valid, error_msg = validate_domain(domain)
            if not is_valid:
                errors.append(error_msg)
        
        # Status-specific required fields
        if status == "proposal":
            if not metadata.get("design_impact"):
                warnings.append("Proposal status requires design_impact field")
            if not metadata.get("research_sources"):
                warnings.append("Proposal status should have research_sources")
        
        if status == "approved":
            if not metadata.get("approved_by"):
                errors.append("Approved status requires approved_by field")
            if not metadata.get("approved_at"):
                errors.append("Approved status requires approved_at field")
        
        # Check for unknown fields (strict mode)
        known_fields = {
            "proposal_id", "title", "description", "status", "created_by", "created_at",
            "updated_at", "last_updated_by", "schema_version", "domain", "priority",
            "impact_score", "effort_score", "risk_level", "tags", "research_sources",
            "design_impact", "approval_status", "approved_by", "approved_at",
            "rejection_reason", "implementation_status", "implementation_notes", "history"
        }
        unknown_fields = set(metadata.keys()) - known_fields
        if unknown_fields:
            warnings.append(f"Unknown fields detected (may be ignored): {', '.join(unknown_fields)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_design(self, proposal_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate design against Elysia architecture.
        
        Returns:
            Dict with "valid" bool, "warnings" and "errors" lists
        """
        warnings = []
        errors = []
        
        design_path = proposal_path / "design"
        if not design_path.exists():
            errors.append("Design folder does not exist")
            return {"valid": False, "warnings": warnings, "errors": errors}
        
        # Check for required design files
        required_design_files = ["architecture.md", "integration.md"]
        for file in required_design_files:
            file_path = design_path / file
            if not file_path.exists():
                warnings.append(f"Design file missing: {file}")
        
        # Check design impact
        design_impact = metadata.get("design_impact", {})
        if not design_impact:
            warnings.append("No design_impact specified in metadata")
        
        modules_affected = design_impact.get("modules_affected", [])
        if not modules_affected:
            warnings.append("No modules_affected specified")
        
        return {
            "valid": len(errors) == 0,
            "warnings": warnings,
            "errors": errors
        }


class ProposalLifecycleManager:
    """Manages proposal lifecycle transitions"""
    
    def __init__(self, proposals_root: Path):
        self.proposals_root = proposals_root
        self.validator = ProposalValidator()
    
    def find_similar_proposals(self, title: str, tags: List[str] = None, domain: str = None) -> List[Dict[str, Any]]:
        """
        Find similar proposals to prevent duplicates.
        
        Args:
            title: Proposal title to search for
            tags: Optional tags to match
            domain: Optional domain to filter by
        
        Returns:
            List of similar proposal metadata
        """
        similar = []
        title_lower = title.lower()
        
        for proposal_dir in self.proposals_root.iterdir():
            if proposal_dir.is_dir():
                metadata_path = proposal_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        prop_metadata = json.load(f)
                    
                    # Check title similarity (simple word overlap)
                    prop_title_lower = prop_metadata.get("title", "").lower()
                    title_words = set(title_lower.split())
                    prop_title_words = set(prop_title_lower.split())
                    overlap = len(title_words & prop_title_words) / max(len(title_words), 1)
                    
                    # Check domain match
                    domain_match = domain and prop_metadata.get("domain") == domain
                    
                    # Check tag overlap
                    tag_match = False
                    if tags and prop_metadata.get("tags"):
                        tag_overlap = set(tags) & set(prop_metadata.get("tags", []))
                        tag_match = len(tag_overlap) > 0
                    
                    # Consider similar if >30% title overlap or domain/tag match
                    if overlap > 0.3 or domain_match or tag_match:
                        similar.append(prop_metadata)
        
        return similar
    
    def transition_to_design(self, proposal_id: str) -> Dict[str, Any]:
        """Move proposal from research to design phase"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return {"status": "error", "message": "Proposal not found"}
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        if metadata.get("status") != "research":
            return {"status": "error", "message": f"Proposal is in {metadata.get('status')} phase, not research"}
        
        # Validate research phase is complete
        research_path = proposal_path / "research"
        if not (research_path / "summary.md").exists():
            return {"status": "error", "message": "Research summary not found"}
        
        # Update status
        metadata["status"] = "design"
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Proposal {proposal_id} transitioned to design phase")
        return {"status": "success", "proposal_id": proposal_id, "new_status": "design"}
    
    def transition_to_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Move proposal from design to proposal phase"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return {"status": "error", "message": "Proposal not found"}
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        if metadata.get("status") != "design":
            return {"status": "error", "message": f"Proposal is in {metadata.get('status')} phase, not design"}
        
        # Validate design phase is complete
        validation = self.validator.validate_design(proposal_path, metadata)
        if not validation["valid"]:
            return {"status": "error", "message": "Design validation failed", "errors": validation["errors"]}
        
        # Update status
        metadata["status"] = "proposal"
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Proposal {proposal_id} transitioned to proposal phase")
        return {"status": "success", "proposal_id": proposal_id, "new_status": "proposal"}
    
    def approve_proposal(self, proposal_id: str, approver: str) -> Dict[str, Any]:
        """Approve a proposal"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return {"status": "error", "message": "Proposal not found"}
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        if metadata.get("status") != "proposal":
            return {"status": "error", "message": f"Proposal is in {metadata.get('status')} phase, not proposal"}
        
        # Update metadata
        metadata["approval_status"] = "approved"
        metadata["approved_by"] = approver
        metadata["approved_at"] = datetime.now().isoformat()
        metadata["status"] = "approved"
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Proposal {proposal_id} approved by {approver}")
        return {"status": "success", "proposal_id": proposal_id, "approved_by": approver}
    
    def reject_proposal(self, proposal_id: str, reason: str) -> Dict[str, Any]:
        """Reject a proposal"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return {"status": "error", "message": "Proposal not found"}
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        if metadata.get("status") != "proposal":
            return {"status": "error", "message": f"Proposal is in {metadata.get('status')} phase, not proposal"}
        
        # Update metadata
        metadata["approval_status"] = "rejected"
        metadata["rejection_reason"] = reason
        metadata["status"] = "rejected"
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Proposal {proposal_id} rejected: {reason}")
        return {"status": "success", "proposal_id": proposal_id, "rejection_reason": reason}


class ProposalWatcher(FileSystemEventHandler):
    """Watches proposals folder for new/updated proposals"""
    
    def __init__(self, lifecycle_manager: ProposalLifecycleManager):
        self.lifecycle_manager = lifecycle_manager
        self.validator = ProposalValidator()
    
    def on_created(self, event):
        """Handle new proposal creation"""
        if event.is_directory:
            proposal_path = Path(event.src_path)
            metadata_path = proposal_path / "metadata.json"
            
            if metadata_path.exists():
                logger.info(f"New proposal detected: {proposal_path.name}")
                self._validate_proposal(proposal_path)
    
    def on_modified(self, event):
        """Handle proposal updates"""
        if event.src_path.endswith("metadata.json"):
            proposal_path = Path(event.src_path).parent
            logger.debug(f"Proposal updated: {proposal_path.name}")
            self._validate_proposal(proposal_path)
    
    def _validate_proposal(self, proposal_path: Path):
        """Validate a proposal"""
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Validate structure
        structure_validation = self.validator.validate_structure(proposal_path)
        if not structure_validation["valid"]:
            logger.warning(f"Proposal {proposal_path.name} structure validation failed: {structure_validation['errors']}")
            return
        
        # Validate metadata
        metadata_validation = self.validator.validate_metadata(metadata)
        if not metadata_validation["valid"]:
            logger.warning(f"Proposal {proposal_path.name} metadata validation failed: {metadata_validation['errors']}")
            return
        
        logger.debug(f"Proposal {proposal_path.name} validated successfully")


class ProposalSystem:
    """Main proposal system integrating all components"""
    
    def __init__(self, proposals_root: Optional[Path] = None):
        self.proposals_root = proposals_root or Path("proposals")
        self.proposals_root.mkdir(exist_ok=True)
        
        self.validator = ProposalValidator()
        self.lifecycle_manager = ProposalLifecycleManager(self.proposals_root)
        self.watcher = ProposalWatcher(self.lifecycle_manager)
        
        # Start watching for proposals
        self.observer = Observer()
        self.observer.schedule(self.watcher, str(self.proposals_root), recursive=True)
        self.observer.start()
        
        logger.info("Proposal system initialized")
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get proposal data"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r') as f:
            return json.load(f)
    
    def list_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all proposals"""
        proposals = []
        for proposal_dir in self.proposals_root.iterdir():
            if proposal_dir.is_dir():
                metadata = self.get_proposal(proposal_dir.name)
                if metadata:
                    if status_filter is None or metadata.get("status") == status_filter:
                        proposals.append(metadata)
        
        return sorted(proposals, key=lambda x: x.get("created_at", ""), reverse=True)
    
    def shutdown(self):
        """Shutdown the proposal system"""
        self.observer.stop()
        self.observer.join()
        logger.info("Proposal system shut down")


# Example usage
if __name__ == "__main__":
    system = ProposalSystem()
    
    # List proposals
    proposals = system.list_proposals()
    print(f"Found {len(proposals)} proposals")
    
    # Keep running to watch for changes
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        system.shutdown()

