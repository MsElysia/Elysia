"""
Pytest fixtures for proposal system tests
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


@pytest.fixture
def base_metadata() -> Dict[str, Any]:
    """Base metadata fixture for valid proposal"""
    return {
        "schema_version": 1,
        "proposal_id": "prop-0001",
        "title": "Hestia: Improve Zillow scraping robustness",
        "description": "Enhance error handling, anti-bot strategies, and data normalization for the Zillow scraper.",
        "status": "research",
        "domain": "hestia_scraping",
        "priority": "medium",
        "impact_score": 4,
        "effort_score": 3,
        "risk_level": "medium",
        "tags": ["hestia", "scraping", "zillow"],
        "research_sources": [],
        "created_by": "Elysia-WebScout",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "last_updated_by": "Elysia-WebScout",
        "approval_status": "pending",
        "implementation_status": "not_started",
        "implementation_notes": [],
        "history": []
    }


@pytest.fixture
def temp_proposals_dir():
    """Create temporary directory for proposals"""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_proposal_path(temp_proposals_dir, base_metadata):
    """Create a sample proposal directory with metadata"""
    proposal_id = base_metadata["proposal_id"]
    proposal_path = temp_proposals_dir / proposal_id
    proposal_path.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    (proposal_path / "research").mkdir(exist_ok=True)
    (proposal_path / "design").mkdir(exist_ok=True)
    (proposal_path / "implementation").mkdir(exist_ok=True)
    
    # Write metadata
    metadata_path = proposal_path / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(base_metadata, f, indent=2)
    
    # Write README
    readme_path = proposal_path / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(f"# {base_metadata['title']}\n\n")
        f.write(f"**Proposal ID**: {proposal_id}\n")
    
    return proposal_path


@pytest.fixture
def validator():
    """ProposalValidator instance"""
    from project_guardian.proposal_system import ProposalValidator
    return ProposalValidator()


@pytest.fixture
def lifecycle_manager(temp_proposals_dir):
    """ProposalLifecycleManager instance"""
    from project_guardian.proposal_system import ProposalLifecycleManager
    return ProposalLifecycleManager(temp_proposals_dir)

