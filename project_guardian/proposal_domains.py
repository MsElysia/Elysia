#!/usr/bin/env python3
"""
Canonical Proposal Domains
Defines the allowed domains for proposals in the Elysia system.
"""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Set, List, Optional

logger = logging.getLogger(__name__)


class ProposalDomain(str, Enum):
    """
    Canonical proposal domains for Elysia system.
    
    Each proposal must be tagged with exactly one primary domain.
    """
    ELYSIA_CORE = "elysia_core"
    HESTIA_SCRAPING = "hestia_scraping"
    LEGAL_PIPELINE = "legal_pipeline"
    INFRA_OBSERVABILITY = "infra_observability"
    PERSONA_MUTATION = "persona_mutation"
    
    def __str__(self):
        return self.value
    
    @classmethod
    def values(cls) -> List[str]:
        """Get list of all domain values"""
        return [domain.value for domain in cls]
    
    @classmethod
    def is_valid(cls, domain: str) -> bool:
        """Check if a domain string is valid"""
        try:
            cls(domain)
            return True
        except ValueError:
            return False
    
    @classmethod
    def from_string(cls, domain: str) -> Optional['ProposalDomain']:
        """Convert string to ProposalDomain, returns None if invalid"""
        try:
            return cls(domain)
        except ValueError:
            return None


class ProposalDomainConfig:
    """
    Manages proposal domain configuration.
    Loads canonical domains from enum and optionally extends from config file.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize domain config.
        
        Args:
            config_path: Optional path to config/proposal_domains.json
        """
        self.config_path = config_path or Path("config/proposal_domains.json")
        self.canonical_domains = set(ProposalDomain.values())
        self.extended_domains = set()
        self.domain_descriptions = {}
        self.load_config()
    
    def load_config(self):
        """Load extended domains from config file if it exists"""
        if not self.config_path.exists():
            logger.debug(f"Domain config file not found: {self.config_path}. Using canonical domains only.")
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load extended domains
            extended = config.get("extended_domains", [])
            for domain in extended:
                if isinstance(domain, str):
                    self.extended_domains.add(domain)
                elif isinstance(domain, dict):
                    domain_name = domain.get("name")
                    if domain_name:
                        self.extended_domains.add(domain_name)
                        if "description" in domain:
                            self.domain_descriptions[domain_name] = domain["description"]
            
            # Load descriptions for canonical domains
            descriptions = config.get("domain_descriptions", {})
            for domain, desc in descriptions.items():
                if domain in self.canonical_domains:
                    self.domain_descriptions[domain] = desc
            
            logger.info(f"Loaded {len(self.extended_domains)} extended domains from config")
        except Exception as e:
            logger.warning(f"Could not load domain config: {e}. Using canonical domains only.")
    
    def get_all_domains(self) -> Set[str]:
        """Get all valid domains (canonical + extended)"""
        return self.canonical_domains | self.extended_domains
    
    def is_valid(self, domain: str) -> bool:
        """Check if domain is valid (canonical or extended)"""
        return domain in self.canonical_domains or domain in self.extended_domains
    
    def get_description(self, domain: str) -> Optional[str]:
        """Get description for a domain"""
        return self.domain_descriptions.get(domain)
    
    def validate_domain(self, domain: str) -> tuple[bool, Optional[str]]:
        """
        Validate domain and return (is_valid, error_message).
        
        Returns:
            (True, None) if valid
            (False, error_message) if invalid
        """
        if not domain:
            return (False, "Domain is required")
        
        if not self.is_valid(domain):
            valid_domains = sorted(self.canonical_domains | self.extended_domains)
            return (False, f"Invalid domain: '{domain}'. Must be one of: {', '.join(valid_domains)}")
        
        return (True, None)


# Global instance
_global_config: Optional[ProposalDomainConfig] = None


def get_domain_config() -> ProposalDomainConfig:
    """Get or create global domain config instance"""
    global _global_config
    if _global_config is None:
        _global_config = ProposalDomainConfig()
    return _global_config


def validate_domain(domain: str) -> tuple[bool, Optional[str]]:
    """Convenience function to validate a domain"""
    config = get_domain_config()
    return config.validate_domain(domain)

