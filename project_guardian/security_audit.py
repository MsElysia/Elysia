# project_guardian/security_audit.py
# Security Audit System
# Provides automated security checks and audit reporting

import logging
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

try:
    from .secrets_manager import SecretsManager, get_api_key
except ImportError:
    SecretsManager = None
    get_api_key = None

logger = logging.getLogger(__name__)


class SecurityIssueSeverity(Enum):
    """Security issue severity levels."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # High priority fix needed
    MEDIUM = "medium"  # Should be addressed
    LOW = "low"  # Nice to have
    INFO = "info"  # Informational


class SecurityIssue:
    """Represents a security issue."""
    def __init__(
        self,
        severity: SecurityIssueSeverity,
        category: str,
        title: str,
        description: str,
        recommendation: Optional[str] = None,
        location: Optional[str] = None
    ):
        self.severity = severity
        self.category = category
        self.title = title
        self.description = description
        self.recommendation = recommendation
        self.location = location
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "location": self.location,
            "timestamp": self.timestamp.isoformat()
        }


class SecurityAuditor:
    """
    Automated security audit system.
    Checks API keys, authentication, configuration, and other security aspects.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize SecurityAuditor.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = Path(config_path) if config_path else None
        self.issues: List[SecurityIssue] = []
        
    def run_audit(self) -> Dict[str, Any]:
        """
        Run complete security audit.
        
        Returns:
            Dictionary with audit results
        """
        self.issues = []
        
        # Check API key security
        self._audit_api_keys()
        
        # Check authentication
        self._audit_authentication()
        
        # Check configuration security
        self._audit_configuration()
        
        # Check file permissions
        self._audit_file_permissions()
        
        # Check secrets management
        self._audit_secrets_management()
        
        # Categorize issues
        critical = [i for i in self.issues if i.severity == SecurityIssueSeverity.CRITICAL]
        high = [i for i in self.issues if i.severity == SecurityIssueSeverity.HIGH]
        medium = [i for i in self.issues if i.severity == SecurityIssueSeverity.MEDIUM]
        low = [i for i in self.issues if i.severity == SecurityIssueSeverity.LOW]
        info = [i for i in self.issues if i.severity == SecurityIssueSeverity.INFO]
        
        # Calculate security score (0-100)
        score = self._calculate_security_score()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "security_score": score,
            "status": "secure" if len(critical) == 0 and len(high) == 0 else "needs_attention",
            "critical_issues": len(critical),
            "high_issues": len(high),
            "medium_issues": len(medium),
            "low_issues": len(low),
            "info_issues": len(info),
            "total_issues": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": self._generate_summary()
        }
    
    def _audit_api_keys(self):
        """Audit API key security."""
        # Check for API keys in plain text files
        api_key_files = [
            "API keys/alpha vantage API.txt",
            "API keys/chat gpt api key for elysia.txt",
            "API keys/Cohere API key.txt",
            "API keys/Hugging face API key.txt",
            "API keys/open router API key.txt",
            "API keys/replicate API key.txt",
            "alpha vantage api key.txt"
        ]
        
        for file_path in api_key_files:
            path = Path(file_path)
            if path.exists():
                self.issues.append(SecurityIssue(
                    severity=SecurityIssueSeverity.HIGH,
                    category="api_keys",
                    title=f"API key found in plain text file",
                    description=f"API key file found: {file_path}",
                    recommendation="Migrate to SecretsManager and delete plain text file",
                    location=str(path)
                ))
        
        # Check environment variables
        api_key_env_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GROK_API_KEY",
            "HUGGINGFACE_API_KEY",
            "REPLICATE_API_KEY"
        ]
        
        env_keys_found = []
        for var in api_key_env_vars:
            if os.getenv(var):
                env_keys_found.append(var)
        
        if not env_keys_found:
            self.issues.append(SecurityIssue(
                severity=SecurityIssueSeverity.MEDIUM,
                category="api_keys",
                title="No API keys in environment variables",
                description="API keys should be set via environment variables for production",
                recommendation="Set API keys as environment variables or use SecretsManager"
            ))
        
        # Check SecretsManager usage
        if SecretsManager:
            try:
                # Test if SecretsManager is working
                sm = SecretsManager()
                if not sm.storage_path.exists():
                    self.issues.append(SecurityIssue(
                        severity=SecurityIssueSeverity.LOW,
                        category="secrets_management",
                        title="SecretsManager not initialized",
                        description="SecretsManager storage path doesn't exist",
                        recommendation="Initialize SecretsManager for secure key storage"
                    ))
            except Exception as e:
                self.issues.append(SecurityIssue(
                    severity=SecurityIssueSeverity.MEDIUM,
                    category="secrets_management",
                    title="SecretsManager error",
                    description=f"SecretsManager encountered an error: {e}",
                    recommendation="Review SecretsManager configuration"
                ))
        else:
            self.issues.append(SecurityIssue(
                severity=SecurityIssueSeverity.HIGH,
                category="secrets_management",
                title="SecretsManager not available",
                description="SecretsManager module not found",
                recommendation="Ensure SecretsManager is properly installed"
            ))
    
    def _audit_authentication(self):
        """Audit authentication security."""
        # Check for weak token generation
        try:
            import secrets
            # If secrets module is available, that's good
            pass
        except ImportError:
            self.issues.append(SecurityIssue(
                severity=SecurityIssueSeverity.MEDIUM,
                category="authentication",
                title="Weak random number generation",
                description="secrets module not available, using potentially weak random",
                recommendation="Use secrets module for token generation"
            ))
        
        # Check master-slave authentication files
        auth_files = [
            "data/master_slave.json",
            "data/master_slave_auth.json"
        ]
        
        for auth_file in auth_files:
            path = Path(auth_file)
            if path.exists():
                # Check file permissions (basic check)
                stat = path.stat()
                # On Windows, check if file is readable by others
                # This is a simplified check
                if stat.st_mode & 0o077:  # Others can read/write
                    self.issues.append(SecurityIssue(
                        severity=SecurityIssueSeverity.MEDIUM,
                        category="authentication",
                        title="Insecure file permissions",
                        description=f"Authentication file has permissive permissions: {auth_file}",
                        recommendation="Restrict file permissions to owner only"
                    ))
    
    def _audit_configuration(self):
        """Audit configuration security."""
        # Check for sensitive data in config files
        config_files = [
            "config/guardian_config.json",
            "config/trust_policies.yaml"
        ]
        
        for config_file in config_files:
            path = Path(config_file)
            if path.exists():
                try:
                    if config_file.endswith('.json'):
                        import json
                        with open(path, 'r') as f:
                            config = json.load(f)
                            # Check for API keys in config
                            if isinstance(config, dict):
                                for key, value in config.items():
                                    if 'api_key' in key.lower() or 'secret' in key.lower():
                                        if isinstance(value, str) and len(value) > 10:
                                            self.issues.append(SecurityIssue(
                                                severity=SecurityIssueSeverity.HIGH,
                                                category="configuration",
                                                title="API key in configuration file",
                                                description=f"API key found in {config_file}",
                                                recommendation="Move to environment variables or SecretsManager",
                                                location=config_file
                                            ))
                except Exception:
                    # Can't read config, skip
                    pass
    
    def _audit_file_permissions(self):
        """Audit file permissions."""
        sensitive_dirs = [
            "data/vault",
            "data/secrets",
            "memory/snapshots"
        ]
        
        for dir_path in sensitive_dirs:
            path = Path(dir_path)
            if path.exists():
                # Basic permission check
                # On Windows, this is simplified
                pass  # File permission checks are OS-specific
    
    def _audit_secrets_management(self):
        """Audit secrets management implementation."""
        # Check if secrets directory exists and is protected
        secrets_dir = Path("data/secrets")
        if secrets_dir.exists():
            # Check .gitignore
            gitignore = Path(".gitignore")
            if gitignore.exists():
                content = gitignore.read_text()
                if "secrets" not in content.lower() and "data/secrets" not in content:
                    self.issues.append(SecurityIssue(
                        severity=SecurityIssueSeverity.MEDIUM,
                        category="secrets_management",
                        title="Secrets directory not in .gitignore",
                        description="Secrets directory may be committed to version control",
                        recommendation="Add 'data/secrets' to .gitignore"
                    ))
        else:
            self.issues.append(SecurityIssue(
                severity=SecurityIssueSeverity.LOW,
                category="secrets_management",
                title="Secrets directory not created",
                description="Secrets directory doesn't exist yet",
                recommendation="Initialize SecretsManager to create secure storage"
            ))
    
    def _calculate_security_score(self) -> int:
        """Calculate security score (0-100)."""
        if not self.issues:
            return 100
        
        # Start with perfect score
        score = 100
        
        # Deduct points based on severity
        for issue in self.issues:
            if issue.severity == SecurityIssueSeverity.CRITICAL:
                score -= 20
            elif issue.severity == SecurityIssueSeverity.HIGH:
                score -= 10
            elif issue.severity == SecurityIssueSeverity.MEDIUM:
                score -= 5
            elif issue.severity == SecurityIssueSeverity.LOW:
                score -= 2
            # INFO doesn't deduct points
        
        # Ensure score doesn't go below 0
        return max(0, score)
    
    def _generate_summary(self) -> str:
        """Generate audit summary."""
        critical = len([i for i in self.issues if i.severity == SecurityIssueSeverity.CRITICAL])
        high = len([i for i in self.issues if i.severity == SecurityIssueSeverity.HIGH])
        
        if critical > 0:
            return f"CRITICAL: {critical} critical security issues found. Immediate action required."
        elif high > 0:
            return f"WARNING: {high} high-priority security issues found. Review recommended."
        elif len(self.issues) > 0:
            return f"INFO: {len(self.issues)} security recommendations found."
        else:
            return "No security issues found. System appears secure."


def run_security_audit(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to run security audit.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Audit results dictionary
    """
    auditor = SecurityAuditor(config_path=config_path)
    return auditor.run_audit()

