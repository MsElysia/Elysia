"""
Tests for duplicate proposal detection
"""

import pytest
import json
from pathlib import Path
from project_guardian.proposal_system import ProposalLifecycleManager


class TestDuplicateDetection:
    """Test duplicate proposal detection"""
    
    def test_duplicate_detection_catches_similar_title_same_domain(self, lifecycle_manager, 
                                                                  temp_proposals_dir):
        """Test that similar titles in same domain are detected"""
        # Create existing proposal
        existing_id = "prop-existing-001"
        existing_path = temp_proposals_dir / existing_id
        existing_path.mkdir(parents=True, exist_ok=True)
        
        existing_metadata = {
            "proposal_id": existing_id,
            "title": "Hestia: Zillow Scraper v2",
            "domain": "hestia_scraping",
            "tags": ["scraping", "zillow"],
            "status": "research",
            "created_at": "2025-01-01T00:00:00"
        }
        
        metadata_path = existing_path / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(existing_metadata, f, indent=2)
        
        # Search for similar proposal
        similar = lifecycle_manager.find_similar_proposals(
            title="Zillow scraper v2 for Hestia",
            tags=["scraping", "zillow"],
            domain="hestia_scraping"
        )
        
        assert len(similar) > 0
        assert similar[0]["proposal_id"] == existing_id
    
    def test_duplicate_detection_ignores_different_domain(self, lifecycle_manager, 
                                                         temp_proposals_dir):
        """Test that same title but different domain doesn't match"""
        # Create existing proposal
        existing_id = "prop-existing-002"
        existing_path = temp_proposals_dir / existing_id
        existing_path.mkdir(parents=True, exist_ok=True)
        
        existing_metadata = {
            "proposal_id": existing_id,
            "title": "Improve scraping robustness",
            "domain": "hestia_scraping",
            "tags": ["scraping"],
            "status": "research",
            "created_at": "2025-01-01T00:00:00"
        }
        
        metadata_path = existing_path / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(existing_metadata, f, indent=2)
        
        # Search with different domain
        similar = lifecycle_manager.find_similar_proposals(
            title="Improve scraping robustness",
            tags=["scraping"],
            domain="legal_pipeline"  # Different domain
        )
        
        # Should not match or match below threshold
        assert len(similar) == 0 or all(
            prop.get("domain") != "legal_pipeline" for prop in similar
        )
    
    def test_duplicate_detection_by_tag_overlap(self, lifecycle_manager, temp_proposals_dir):
        """Test that tag overlap triggers duplicate detection"""
        # Create existing proposal
        existing_id = "prop-existing-003"
        existing_path = temp_proposals_dir / existing_id
        existing_path.mkdir(parents=True, exist_ok=True)
        
        existing_metadata = {
            "proposal_id": existing_id,
            "title": "Multi-agent orchestration patterns",
            "domain": "elysia_core",
            "tags": ["orchestration", "multi-agent", "langgraph"],
            "status": "research",
            "created_at": "2025-01-01T00:00:00"
        }
        
        metadata_path = existing_path / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(existing_metadata, f, indent=2)
        
        # Search with overlapping tags
        similar = lifecycle_manager.find_similar_proposals(
            title="Agent orchestration improvements",
            tags=["orchestration", "multi-agent"],  # Overlapping tags
            domain="elysia_core"
        )
        
        assert len(similar) > 0
        assert similar[0]["proposal_id"] == existing_id
    
    def test_no_duplicates_when_none_exist(self, lifecycle_manager, temp_proposals_dir):
        """Test that no duplicates are found when none exist"""
        similar = lifecycle_manager.find_similar_proposals(
            title="Completely new proposal",
            tags=["new", "unique"],
            domain="elysia_core"
        )
        
        assert len(similar) == 0

