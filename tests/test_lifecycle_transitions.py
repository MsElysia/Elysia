"""
Tests for ProposalLifecycleManager lifecycle transitions
"""

import pytest
import json
from pathlib import Path
from project_guardian.proposal_system import ProposalLifecycleManager


class TestLifecycleTransitions:
    """Test proposal lifecycle state transitions"""
    
    def test_transition_to_design_requires_research_summary(self, lifecycle_manager, 
                                                           sample_proposal_path, base_metadata):
        """Test that transition to design requires research summary"""
        proposal_id = base_metadata["proposal_id"]
        
        # Try to transition without research summary
        result = lifecycle_manager.transition_to_design(proposal_id)
        
        # Should fail because research summary doesn't exist
        assert result["status"] == "error"
        assert "research summary" in result["message"].lower()
        
        # Create research summary
        research_summary_path = sample_proposal_path / "research" / "summary.md"
        with open(research_summary_path, 'w') as f:
            f.write("# Research Summary\n\nFindings...")
        
        # Now transition should succeed
        result = lifecycle_manager.transition_to_design(proposal_id)
        assert result["status"] == "success"
        assert result["new_status"] == "design"
    
    def test_transition_to_proposal_requires_design(self, lifecycle_manager, 
                                                    sample_proposal_path, base_metadata):
        """Test that transition to proposal works with design documents"""
        proposal_id = base_metadata["proposal_id"]
        
        # First transition to design
        research_summary_path = sample_proposal_path / "research" / "summary.md"
        with open(research_summary_path, 'w') as f:
            f.write("# Research Summary\n\nFindings...")
        
        lifecycle_manager.transition_to_design(proposal_id)
        
        # Update metadata to design status
        metadata_path = sample_proposal_path / "metadata.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata["status"] = "design"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Create design documents
        arch_path = sample_proposal_path / "design" / "architecture.md"
        with open(arch_path, 'w') as f:
            f.write("# Architecture\n\nDesign...")
        
        int_path = sample_proposal_path / "design" / "integration.md"
        with open(int_path, 'w') as f:
            f.write("# Integration\n\nIntegration points...")
        
        # Update metadata with design_impact
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata["design_impact"] = {
            "modules_affected": ["test_module"],
            "complexity": "medium",
            "estimated_effort_hours": 10,
            "breaking_changes": False,
            "dependencies": []
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Transition should succeed with design documents
        result = lifecycle_manager.transition_to_proposal(proposal_id)
        assert result["status"] == "success"
        assert result["new_status"] == "proposal"
    
    def test_approve_proposal_requires_proposal_status(self, lifecycle_manager, 
                                                       sample_proposal_path, base_metadata):
        """Test that approval requires proposal status"""
        proposal_id = base_metadata["proposal_id"]
        
        # Update metadata to proposal status first
        metadata_path = sample_proposal_path / "metadata.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata["status"] = "proposal"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Now try to approve - should work
        result = lifecycle_manager.approve_proposal(proposal_id, "test_user")
        
        # Should succeed since status is now proposal
        assert result["status"] == "success"
    
    def test_reject_proposal_requires_proposal_status(self, lifecycle_manager, sample_proposal_path, 
                                                      base_metadata):
        """Test that rejection requires proposal status"""
        proposal_id = base_metadata["proposal_id"]
        
        # Try to reject from research status (should fail)
        result = lifecycle_manager.reject_proposal(proposal_id, "Not aligned with priorities")
        
        assert result["status"] == "error"
        assert "proposal" in result["message"].lower()


class TestApprovalWorkflow:
    """Test approval and rejection workflows"""
    
    def test_approve_proposal_sets_metadata(self, lifecycle_manager, sample_proposal_path, 
                                           base_metadata):
        """Test that approving a proposal sets all required metadata"""
        proposal_id = base_metadata["proposal_id"]
        
        # Set up proposal status
        metadata_path = sample_proposal_path / "metadata.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata["status"] = "proposal"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Approve
        approver = "test_user"
        result = lifecycle_manager.approve_proposal(proposal_id, approver)
        
        assert result["status"] == "success"
        
        # Check metadata was updated
        with open(metadata_path, 'r') as f:
            updated_metadata = json.load(f)
        
        assert updated_metadata["approval_status"] == "approved"
        assert updated_metadata["approved_by"] == approver
        assert updated_metadata["approved_at"] is not None
        assert updated_metadata["status"] == "approved"
    
    def test_reject_proposal_sets_reason(self, lifecycle_manager, sample_proposal_path, 
                                        base_metadata):
        """Test that rejecting a proposal sets rejection reason"""
        proposal_id = base_metadata["proposal_id"]
        
        # Set up proposal status
        metadata_path = sample_proposal_path / "metadata.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata["status"] = "proposal"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Reject
        reason = "Does not align with current priorities"
        result = lifecycle_manager.reject_proposal(proposal_id, reason)
        
        assert result["status"] == "success"
        
        # Check metadata was updated
        with open(metadata_path, 'r') as f:
            updated_metadata = json.load(f)
        
        assert updated_metadata["approval_status"] == "rejected"
        assert updated_metadata["rejection_reason"] == reason
        assert updated_metadata["status"] == "rejected"

