"""
Tests for proposal history/audit trail
"""

import pytest
import json
from pathlib import Path
from project_guardian.webscout_agent import ElysiaWebScout, ProposalMetadata


class TestHistoryTracking:
    """Test history/audit trail functionality"""
    
    def test_history_entry_created_on_metadata_update(self, temp_proposals_dir):
        """Test that history entries are created on metadata updates"""
        scout = ElysiaWebScout(proposals_root=temp_proposals_dir)
        
        # Create proposal
        result = scout.create_proposal(
            task_description="Test proposal",
            topic="test-topic",
            domain="elysia_core"
        )
        proposal_id = result["proposal_id"]
        
        # Load metadata
        metadata = scout.get_proposal(proposal_id)
        initial_history_length = len(metadata.get("history", []))
        
        # Update metadata
        scout._update_metadata(
            proposal_id,
            {"impact_score": 4},
            actor="test-user",
            change_summary="Updated impact_score from 3 to 4"
        )
        
        # Reload and check history
        updated_metadata = scout.get_proposal(proposal_id)
        history = updated_metadata.get("history", [])
        
        assert len(history) == initial_history_length + 1
        
        last_entry = history[-1]
        assert last_entry["actor"] == "test-user"
        assert "impact_score" in last_entry["change_summary"].lower()
        assert "timestamp" in last_entry
        assert last_entry["timestamp"] is not None
    
    def test_history_preserves_previous_entries(self, temp_proposals_dir):
        """Test that history preserves previous entries"""
        scout = ElysiaWebScout(proposals_root=temp_proposals_dir)
        
        # Create proposal
        result = scout.create_proposal(
            task_description="Test proposal",
            topic="test-topic",
            domain="elysia_core"
        )
        proposal_id = result["proposal_id"]
        
        # Make multiple updates
        scout._update_metadata(
            proposal_id,
            {"impact_score": 4},
            actor="user1",
            change_summary="First update"
        )
        
        scout._update_metadata(
            proposal_id,
            {"effort_score": 3},
            actor="user2",
            change_summary="Second update"
        )
        
        # Check all entries are preserved
        metadata = scout.get_proposal(proposal_id)
        history = metadata.get("history", [])
        
        assert len(history) >= 2  # At least 2 updates plus initial creation
        
        # Check first entry still exists
        assert any(entry["actor"] == "user1" for entry in history)
        assert any(entry["actor"] == "user2" for entry in history)
    
    def test_initial_proposal_has_history_entry(self, temp_proposals_dir):
        """Test that creating a proposal adds initial history entry"""
        scout = ElysiaWebScout(proposals_root=temp_proposals_dir)
        
        result = scout.create_proposal(
            task_description="Test proposal",
            topic="test-topic",
            domain="elysia_core"
        )
        proposal_id = result["proposal_id"]
        
        metadata = scout.get_proposal(proposal_id)
        history = metadata.get("history", [])
        
        # Should have at least one entry (creation)
        assert len(history) >= 1
        
        # First entry should be about creation
        creation_entry = history[0]
        assert "created" in creation_entry["change_summary"].lower() or \
               creation_entry["actor"] == "elysia-webscout"
    
    def test_history_tracks_last_updated_by(self, temp_proposals_dir):
        """Test that last_updated_by is tracked in history"""
        scout = ElysiaWebScout(proposals_root=temp_proposals_dir)
        
        result = scout.create_proposal(
            task_description="Test proposal",
            topic="test-topic",
            domain="elysia_core"
        )
        proposal_id = result["proposal_id"]
        
        # Update with different actor
        scout._update_metadata(
            proposal_id,
            {"priority": "high"},
            actor="human-admin",
            change_summary="Updated priority"
        )
        
        metadata = scout.get_proposal(proposal_id)
        
        assert metadata["last_updated_by"] == "human-admin"
        assert metadata["updated_at"] is not None

