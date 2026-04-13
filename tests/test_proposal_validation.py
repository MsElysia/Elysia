"""
Tests for ProposalValidator
"""

import pytest
from project_guardian.proposal_system import ProposalValidator


class TestProposalCreationAndValidation:
    """Test proposal creation and validation"""
    
    def test_create_minimal_draft_proposal_is_valid(self, validator, base_metadata):
        """Test that a minimal valid draft proposal passes validation"""
        metadata = base_metadata.copy()
        metadata["status"] = "research"
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is True, f"Validation failed: {result.get('errors')}"
        assert len(result["errors"]) == 0
    
    def test_missing_required_field_fails_validation(self, validator, base_metadata):
        """Test that missing required fields cause validation failure"""
        metadata = base_metadata.copy()
        del metadata["title"]  # Remove required field
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is False
        assert any("title" in error.lower() for error in result["errors"])
    
    def test_missing_schema_version_fails(self, validator, base_metadata):
        """Test that missing schema_version causes validation failure"""
        metadata = base_metadata.copy()
        del metadata["schema_version"]
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is False
        assert any("schema_version" in error.lower() for error in result["errors"])
    
    def test_invalid_status_fails_validation(self, validator, base_metadata):
        """Test that invalid status values are rejected"""
        metadata = base_metadata.copy()
        metadata["status"] = "invalid_status"
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is False
        assert any("invalid status" in error.lower() for error in result["errors"])


class TestScoringValidation:
    """Test scoring field validation"""
    
    def test_impact_effort_scores_are_in_range(self, validator, base_metadata):
        """Test that impact and effort scores must be 1-5"""
        # Test valid scores
        metadata = base_metadata.copy()
        metadata["impact_score"] = 3
        metadata["effort_score"] = 2
        
        result = validator.validate_metadata(metadata)
        assert result["valid"] is True
        
        # Test invalid impact_score (too low)
        metadata["impact_score"] = 0
        result = validator.validate_metadata(metadata)
        assert result["valid"] is False
        assert any("impact_score" in error.lower() for error in result["errors"])
        
        # Test invalid impact_score (too high)
        metadata["impact_score"] = 6
        result = validator.validate_metadata(metadata)
        assert result["valid"] is False
        
        # Test invalid effort_score
        metadata["impact_score"] = 3
        metadata["effort_score"] = 10
        result = validator.validate_metadata(metadata)
        assert result["valid"] is False
        assert any("effort_score" in error.lower() for error in result["errors"])
    
    def test_missing_scores_trigger_warning(self, validator, base_metadata):
        """Test that missing scores trigger warnings but don't fail validation"""
        metadata = base_metadata.copy()
        del metadata["impact_score"]
        del metadata["effort_score"]
        
        result = validator.validate_metadata(metadata)
        
        # Should still be valid (warnings, not errors)
        assert result["valid"] is True
        assert any("impact_score" in warning.lower() for warning in result.get("warnings", []))
        assert any("effort_score" in warning.lower() for warning in result.get("warnings", []))
    
    def test_risk_level_and_priority_values_are_valid(self, validator, base_metadata):
        """Test that risk_level and priority must be from allowed set"""
        # Valid values
        metadata = base_metadata.copy()
        metadata["risk_level"] = "low"
        metadata["priority"] = "high"
        
        result = validator.validate_metadata(metadata)
        assert result["valid"] is True
        
        # Invalid risk_level
        metadata["risk_level"] = "invalid_risk"
        result = validator.validate_metadata(metadata)
        assert result["valid"] is False
        assert any("risk_level" in error.lower() for error in result["errors"])
        
        # Invalid priority
        metadata["risk_level"] = "medium"
        metadata["priority"] = "invalid_priority"
        result = validator.validate_metadata(metadata)
        assert result["valid"] is False
        assert any("priority" in error.lower() for error in result["errors"])


class TestSchemaVersionAndUnknownFields:
    """Test schema version handling and unknown fields"""
    
    def test_unknown_field_triggers_warning_not_failure(self, validator, base_metadata):
        """Test that unknown fields trigger warnings but don't fail validation"""
        metadata = base_metadata.copy()
        metadata["weird_field"] = "something"
        metadata["another_unknown"] = 123
        
        result = validator.validate_metadata(metadata)
        
        # Should still be valid
        assert result["valid"] is True
        # Should have warnings about unknown fields
        warnings = result.get("warnings", [])
        assert any("unknown" in warning.lower() or "weird_field" in warning.lower() 
                  for warning in warnings)
    
    def test_schema_version_must_be_supported(self, validator, base_metadata):
        """Test that unsupported schema versions trigger warnings"""
        metadata = base_metadata.copy()
        metadata["schema_version"] = 999
        
        result = validator.validate_metadata(metadata)
        
        # Should still validate but warn
        assert result["valid"] is True
        warnings = result.get("warnings", [])
        assert any("schema version" in warning.lower() or "999" in warning 
                  for warning in warnings)
    
    def test_schema_version_1_is_valid(self, validator, base_metadata):
        """Test that schema version 1 is accepted"""
        metadata = base_metadata.copy()
        metadata["schema_version"] = 1
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is True
        assert len([w for w in result.get("warnings", []) 
                    if "schema version" in w.lower()]) == 0


class TestStatusSpecificValidation:
    """Test validation rules specific to proposal status"""
    
    def test_proposal_status_requires_design_impact(self, validator, base_metadata):
        """Test that proposal status should have design_impact"""
        metadata = base_metadata.copy()
        metadata["status"] = "proposal"
        if "design_impact" in metadata:
            del metadata["design_impact"]
        
        result = validator.validate_metadata(metadata)
        
        # Should warn about missing design_impact
        warnings = result.get("warnings", [])
        assert any("design_impact" in warning.lower() for warning in warnings)
    
    def test_approved_status_requires_approved_by(self, validator, base_metadata):
        """Test that approved status requires approved_by and approved_at"""
        metadata = base_metadata.copy()
        metadata["status"] = "approved"
        if "approved_by" in metadata:
            del metadata["approved_by"]
        if "approved_at" in metadata:
            del metadata["approved_at"]
        
        result = validator.validate_metadata(metadata)
        
        assert result["valid"] is False
        assert any("approved_by" in error.lower() for error in result["errors"])
        assert any("approved_at" in error.lower() for error in result["errors"])

