"""
Tests for canonical proposal domains
"""

import pytest
from project_guardian.proposal_domains import (
    ProposalDomain,
    ProposalDomainConfig,
    validate_domain,
    get_domain_config
)


class TestProposalDomain:
    """Test ProposalDomain enum"""
    
    def test_all_canonical_domains_exist(self):
        """Test that all expected canonical domains exist"""
        expected_domains = {
            "elysia_core",
            "hestia_scraping",
            "legal_pipeline",
            "infra_observability",
            "persona_mutation"
        }
        actual_domains = {d.value for d in ProposalDomain}
        assert actual_domains == expected_domains
    
    def test_domain_values(self):
        """Test that domain values() returns all domains"""
        values = ProposalDomain.values()
        assert len(values) == 5
        assert "elysia_core" in values
        assert "hestia_scraping" in values
    
    def test_is_valid(self):
        """Test is_valid method"""
        assert ProposalDomain.is_valid("elysia_core") is True
        assert ProposalDomain.is_valid("invalid") is False
        assert ProposalDomain.is_valid("") is False
    
    def test_from_string(self):
        """Test from_string method"""
        assert ProposalDomain.from_string("elysia_core") == ProposalDomain.ELYSIA_CORE
        assert ProposalDomain.from_string("invalid") is None
        assert ProposalDomain.from_string("") is None


class TestDomainValidation:
    """Test domain validation"""
    
    def test_validate_canonical_domains(self):
        """Test that all canonical domains validate"""
        for domain in ProposalDomain:
            is_valid, error = validate_domain(domain.value)
            assert is_valid is True, f"Domain {domain.value} should be valid: {error}"
    
    def test_validate_invalid_domain(self):
        """Test that invalid domains are rejected"""
        is_valid, error = validate_domain("invalid_domain")
        assert is_valid is False
        assert "Invalid domain" in error
    
    def test_validate_empty_domain(self):
        """Test that empty domain is rejected"""
        is_valid, error = validate_domain("")
        assert is_valid is False
        assert "required" in error.lower()
    
    def test_validate_none_domain(self):
        """Test that None domain is rejected"""
        is_valid, error = validate_domain(None)
        assert is_valid is False


class TestDomainConfig:
    """Test ProposalDomainConfig"""
    
    def test_config_loads_canonical_domains(self):
        """Test that config includes all canonical domains"""
        config = get_domain_config()
        all_domains = config.get_all_domains()
        
        for domain in ProposalDomain:
            assert domain.value in all_domains
    
    def test_config_validates_domains(self):
        """Test that config validates domains correctly"""
        config = get_domain_config()
        
        assert config.is_valid("elysia_core") is True
        assert config.is_valid("invalid") is False
    
    def test_config_get_description(self):
        """Test getting domain descriptions"""
        config = get_domain_config()
        
        desc = config.get_description("elysia_core")
        assert desc is not None
        assert len(desc) > 0

