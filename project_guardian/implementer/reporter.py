"""
Reporter - Updates proposal metadata and history for implementation
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .data_models import ImplementationResult, ImplementationStatus

logger = logging.getLogger(__name__)


class Reporter:
    """
    Single place that mutates proposal metadata and history for implementation.
    Ensures transparency in the audit trail.
    """
    
    def __init__(self, proposals_root: Path):
        """
        Initialize reporter.
        
        Args:
            proposals_root: Root directory for proposals
        """
        self.proposals_root = Path(proposals_root)
    
    def mark_status(self, proposal: Dict[str, Any], status: str, actor: str, change_summary: str):
        """
        Mark proposal status and add history entry.
        
        Args:
            proposal: Proposal metadata dict
            status: New status
            actor: Who made the change
            change_summary: Summary of change
        """
        proposal_id = proposal.get("proposal_id")
        if not proposal_id:
            raise ValueError("Proposal missing proposal_id")
        
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            raise ValueError(f"Proposal metadata not found: {metadata_path}")
        
        # Load metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Update status
        old_status = metadata.get("status")
        metadata["status"] = status
        metadata["updated_at"] = datetime.now().isoformat()
        metadata["last_updated_by"] = actor
        
        # Add history entry
        if "history" not in metadata:
            metadata["history"] = []
        
        metadata["history"].append({
            "timestamp": datetime.now().isoformat(),
            "actor": actor,
            "change_summary": change_summary,
            "details": f"Status changed from {old_status} to {status}"
        })
        
        # Save metadata
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Updated proposal {proposal_id} status to {status}")
    
    def record_implementation_result(self, 
                                    proposal: Dict[str, Any],
                                    result: ImplementationResult,
                                    actor: str):
        """
        Record implementation result in proposal metadata.
        
        Args:
            proposal: Proposal metadata dict
            result: ImplementationResult
            actor: Who executed the implementation
        """
        proposal_id = proposal.get("proposal_id")
        if not proposal_id:
            raise ValueError("Proposal missing proposal_id")
        
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            raise ValueError(f"Proposal metadata not found: {metadata_path}")
        
        # Load metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Update status
        metadata["status"] = result.status.value
        metadata["updated_at"] = datetime.now().isoformat()
        metadata["last_updated_by"] = actor
        
        # Store implementation artifacts
        if "implementation_artifacts" not in metadata:
            metadata["implementation_artifacts"] = {}
        
        metadata["implementation_artifacts"].update({
            "branch_name": result.branch_name,
            "tasks_completed": result.tasks_completed,
            "tasks_failed": result.tasks_failed,
            "tasks_total": result.tasks_total,
            "test_results": result.test_results,
            "completed_at": datetime.now().isoformat()
        })
        
        # Store implementation summary
        if "implementation_summary" not in metadata:
            metadata["implementation_summary"] = ""
        
        summary = f"""Implementation completed:
- Status: {result.status.value}
- Tasks: {result.tasks_completed}/{result.tasks_total} passed
- Branch: {result.branch_name}
"""
        if result.error:
            summary += f"- Error: {result.error}\n"
        
        metadata["implementation_summary"] = summary
        
        # Add history entry
        if "history" not in metadata:
            metadata["history"] = []
        
        metadata["history"].append({
            "timestamp": datetime.now().isoformat(),
            "actor": actor,
            "change_summary": f"Implementation completed: {result.status.value}",
            "details": {
                "tasks_completed": result.tasks_completed,
                "tasks_failed": result.tasks_failed,
                "branch": result.branch_name
            }
        })
        
        # Save diff summary if available
        if result.diff_summary:
            diff_path = proposal_path / "implementation" / "diff.patch"
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            with open(diff_path, 'w', encoding='utf-8') as f:
                f.write(result.diff_summary)
        
        # Save task results
        if result.task_results:
            results_path = proposal_path / "implementation" / "task_results.json"
            results_path.parent.mkdir(parents=True, exist_ok=True)
            with open(results_path, 'w', encoding='utf-8') as f:
                json.dump([
                    {
                        "task_id": r.task_id,
                        "status": r.status.value,
                        "error": r.error,
                        "files_changed": r.files_changed
                    }
                    for r in result.task_results
                ], f, indent=2)
        
        # Save metadata
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Recorded implementation result for {proposal_id}: {result.status.value}")

