# project_guardian/config_validator.py
# Configuration Validator: Validates system configuration and environment setup

import logging
import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class ConfigIssueSeverity(Enum):
    """Configuration issue severity levels."""
    ERROR = "error"  # Blocks startup
    WARNING = "warning"  # May cause issues
    INFO = "info"  # Optional optimization


class ConfigIssue:
    """Represents a configuration issue."""
    def __init__(
        self,
        severity: ConfigIssueSeverity,
        component: str,
        message: str,
        suggestion: Optional[str] = None
    ):
        self.severity = severity
        self.component = component
        self.message = message
        self.suggestion = suggestion
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "component": self.component,
            "message": self.message,
            "suggestion": self.suggestion
        }


class ConfigValidator:
    """
    Validates system configuration and environment.
    Checks for required settings, API keys, dependencies, and permissions.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize ConfigValidator.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = Path(config_path) if config_path else None
        self.config: Dict[str, Any] = {}
        
        if self.config_path and self.config_path.exists():
            self.load_config()
    
    def load_config(self) -> bool:
        """Load configuration from file."""
        if not self.config_path or not self.config_path.exists():
            return False
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return False
    
    def validate_all(self) -> Dict[str, Any]:
        """
        Run all validation checks.
        
        Returns:
            Dictionary with validation results
        """
        issues: List[ConfigIssue] = []
        
        # Check required directories
        issues.extend(self._check_directories())
        
        # Check API keys
        issues.extend(self._check_api_keys())
        
        # Check dependencies
        issues.extend(self._check_dependencies())
        
        # Check permissions
        issues.extend(self._check_permissions())
        
        # Check database setup
        issues.extend(self._check_database())
        
        # Categorize issues
        errors = [i for i in issues if i.severity == ConfigIssueSeverity.ERROR]
        warnings = [i for i in issues if i.severity == ConfigIssueSeverity.WARNING]
        info = [i for i in issues if i.severity == ConfigIssueSeverity.INFO]
        
        return {
            "valid": len(errors) == 0,
            "errors": [i.to_dict() for i in errors],
            "warnings": [i.to_dict() for i in warnings],
            "info": [i.to_dict() for i in info],
            "total_issues": len(issues)
        }
    
    def _check_directories(self) -> List[ConfigIssue]:
        """Check required directories exist."""
        issues = []
        required_dirs = [
            ("data", "Data storage directory"),
            ("data/backups", "Backup directory"),
            ("data/vault", "Recovery vault directory"),
        ]
        
        for dir_name, description in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    issues.append(ConfigIssue(
                        ConfigIssueSeverity.INFO,
                        "directories",
                        f"Created {description}: {dir_name}"
                    ))
                except Exception as e:
                    issues.append(ConfigIssue(
                        ConfigIssueSeverity.ERROR,
                        "directories",
                        f"Cannot create {description}: {e}",
                        f"Create directory manually: {dir_name}"
                    ))
        
        return issues
    
    def _check_api_keys(self) -> List[ConfigIssue]:
        """Check API keys for AI services."""
        issues = []
        
        # Check OpenAI
        openai_key = os.getenv("OPENAI_API_KEY") or self.config.get("openai_api_key")
        if not openai_key:
            issues.append(ConfigIssue(
                ConfigIssueSeverity.WARNING,
                "api_keys",
                "OpenAI API key not found",
                "Set OPENAI_API_KEY environment variable or add to config.json"
            ))
        
        # Check Claude
        claude_key = os.getenv("ANTHROPIC_API_KEY") or self.config.get("claude_api_key")
        if not claude_key:
            issues.append(ConfigIssue(
                ConfigIssueSeverity.INFO,
                "api_keys",
                "Claude API key not found (optional)",
                "Set ANTHROPIC_API_KEY for Claude support"
            ))
        
        # Check other optional keys
        optional_keys = {
            "GROK_API_KEY": "Grok",
            "HUGGINGFACE_API_KEY": "HuggingFace",
            "REPLICATE_API_KEY": "Replicate"
        }
        
        for env_key, service_name in optional_keys.items():
            key_value = os.getenv(env_key) or self.config.get(env_key.lower())
            if not key_value:
                issues.append(ConfigIssue(
                    ConfigIssueSeverity.INFO,
                    "api_keys",
                    f"{service_name} API key not found (optional)",
                    f"Set {env_key} environment variable if needed"
                ))
        
        return issues
    
    def _check_dependencies(self) -> List[ConfigIssue]:
        """Check Python dependencies."""
        issues = []
        
        required_packages = {
            "flask": "Flask (web UI)",
            "flask_socketio": "Flask-SocketIO (real-time UI)",
            "sqlite3": "SQLite (database)",
        }
        
        optional_packages = {
            "psutil": "psutil (system monitoring)",
            "openai": "OpenAI library",
            "anthropic": "Anthropic library (Claude)",
            "faiss": "FAISS (vector search)",
            "sentence_transformers": "Sentence Transformers (embeddings)"
        }
        
        for package, description in required_packages.items():
            try:
                __import__(package)
            except ImportError:
                issues.append(ConfigIssue(
                    ConfigIssueSeverity.ERROR,
                    "dependencies",
                    f"Missing required package: {package}",
                    f"Install with: pip install {package}"
                ))
        
        for package, description in optional_packages.items():
            try:
                __import__(package)
            except ImportError:
                issues.append(ConfigIssue(
                    ConfigIssueSeverity.INFO,
                    "dependencies",
                    f"Optional package not installed: {package}",
                    f"Install with: pip install {package} for {description}"
                ))
        
        return issues
    
    def _check_permissions(self) -> List[ConfigIssue]:
        """Check file system permissions."""
        issues = []
        
        # Check write permissions for data directory
        data_dir = Path("data")
        if data_dir.exists():
            test_file = data_dir / ".permission_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                issues.append(ConfigIssue(
                    ConfigIssueSeverity.ERROR,
                    "permissions",
                    f"Cannot write to data directory: {e}",
                    "Check directory permissions"
                ))
        else:
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                issues.append(ConfigIssue(
                    ConfigIssueSeverity.ERROR,
                    "permissions",
                    f"Cannot create data directory: {e}",
                    "Check parent directory permissions"
                ))
        
        return issues
    
    def _check_database(self) -> List[ConfigIssue]:
        """Check database setup."""
        issues = []
        
        # Check SQLite availability
        try:
            import sqlite3
            test_db = Path("data/test.db")
            conn = sqlite3.connect(str(test_db))
            conn.close()
            test_db.unlink()
        except Exception as e:
            issues.append(ConfigIssue(
                ConfigIssueSeverity.ERROR,
                "database",
                f"SQLite not available: {e}",
                "SQLite should be included with Python"
            ))
        
        return issues
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get summary of current configuration."""
        return {
            "config_file": str(self.config_path) if self.config_path else None,
            "config_loaded": len(self.config) > 0,
            "openai_configured": bool(os.getenv("OPENAI_API_KEY") or self.config.get("openai_api_key")),
            "claude_configured": bool(os.getenv("ANTHROPIC_API_KEY") or self.config.get("claude_api_key")),
            "data_directory_exists": Path("data").exists(),
            "vault_directory_exists": Path("data/vault").exists()
        }


def validate_configuration(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to validate configuration.
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        Validation results dictionary
    """
    validator = ConfigValidator(config_path)
    return validator.validate_all()


def validate_runtime_configs(
    project_root: Optional[Path] = None,
    skip_files: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Validate autonomy, introspection, and auto_learning configs (post-normalization state).
    Call after normalize_runtime_configs for autonomy.json / introspection.json so recoverable
    values are not double-reported.

    skip_files: basenames (e.g. autonomy.json) to skip — use when normalization already
    recorded unrecoverable errors for that file (malformed JSON).
    """
    import json
    root = project_root or Path(__file__).parent.parent
    config_dir = root / "config"
    issues: List[Dict[str, Any]] = []
    skip = set(skip_files or [])

    def _load(name: str) -> Optional[Dict[str, Any]]:
        if name in skip:
            return None
        p = config_dir / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append({"severity": "error", "component": name, "message": f"Invalid JSON: {e}", "suggestion": "Fix syntax"})
            return None

    # autonomy.json
    ac = _load("autonomy.json")
    if ac is not None:
        if "enabled" in ac and not isinstance(ac["enabled"], bool):
            issues.append({"severity": "warning", "component": "autonomy", "message": "enabled should be boolean", "suggestion": "Use true or false"})
        iv = ac.get("interval_seconds")
        if iv is not None and (not isinstance(iv, (int, float)) or iv < 30 or iv > 3600):
            issues.append({"severity": "warning", "component": "autonomy", "message": f"interval_seconds={iv} invalid (use 30-3600)", "suggestion": "Use 60-600"})
        al = ac.get("allowed_actions")
        if al is not None and not isinstance(al, list):
            issues.append({"severity": "warning", "component": "autonomy", "message": "allowed_actions should be list", "suggestion": 'e.g. ["consider_learning", "consider_dream_cycle"]'})
        mh = ac.get("max_actions_per_hour")
        if mh is not None and (not isinstance(mh, int) or mh < 1 or mh > 60):
            issues.append({"severity": "warning", "component": "autonomy", "message": f"max_actions_per_hour={mh} invalid (use 1-60)", "suggestion": "Use 4-12"})

    # introspection.json
    ic = _load("introspection.json")
    if ic is not None:
        if "enabled" in ic and not isinstance(ic["enabled"], bool):
            issues.append({"severity": "warning", "component": "introspection", "message": "enabled should be boolean", "suggestion": "Use true or false"})
        hb = ic.get("heartbeat_interval_beats")
        if hb is not None and (not isinstance(hb, int) or hb < 1 or hb > 60):
            issues.append({"severity": "warning", "component": "introspection", "message": f"heartbeat_interval_beats={hb} invalid (use 1-60)", "suggestion": "Use 5-15"})
        tm = ic.get("throttle_minutes")
        if tm is not None and (not isinstance(tm, (int, float)) or tm < 1 or tm > 120):
            issues.append({"severity": "warning", "component": "introspection", "message": f"throttle_minutes={tm} invalid (use 1-120)", "suggestion": "Use 15-60"})

    # auto_learning.json
    alc = _load("auto_learning.json")
    if alc is not None:
        ih = alc.get("interval_hours")
        if ih is not None and (not isinstance(ih, (int, float)) or ih < 0.5 or ih > 24):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"interval_hours={ih} invalid (use 0.5-24)", "suggestion": "Use 4-12"})
        mc = alc.get("max_chatlogs")
        if mc is not None and (not isinstance(mc, int) or mc < 0 or mc > 500):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"max_chatlogs={mc} invalid (use 0-500)", "suggestion": "Use 10-50"})
        for key in ("reddit_subs", "rss_feeds", "topics"):
            val = alc.get(key)
            if val is not None and not isinstance(val, list):
                issues.append({"severity": "warning", "component": "auto_learning", "message": f"{key} should be list", "suggestion": f'e.g. ["item1", "item2"]'})
        # Quality gates and caps (post-normalization sanity check)
        mrs = alc.get("min_relevance_score")
        if mrs is not None and (not isinstance(mrs, int) or mrs < 0 or mrs > 10):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"min_relevance_score={mrs} invalid (use 0-10)", "suggestion": "Use 1"})
        arm = alc.get("allow_reddit_into_memory")
        if arm is not None and not isinstance(arm, bool):
            issues.append({"severity": "warning", "component": "auto_learning", "message": "allow_reddit_into_memory should be boolean", "suggestion": "Use true or false"})
        mas = alc.get("max_archived_per_session")
        if mas is not None and (not isinstance(mas, int) or mas < 10 or mas > 500):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"max_archived_per_session={mas} invalid (use 10-500)", "suggestion": "Use 100"})
        mms = alc.get("max_memory_per_session")
        if mms is not None and (not isinstance(mms, int) or mms < 1 or mms > 100):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"max_memory_per_session={mms} invalid (use 1-100)", "suggestion": "Use 20"})
        mpsm = alc.get("max_per_source_memory")
        if mpsm is not None and (not isinstance(mpsm, int) or mpsm < 1 or mpsm > 50):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"max_per_source_memory={mpsm} invalid (use 1-50)", "suggestion": "Use 5"})
        dwd = alc.get("dedup_window_days")
        if dwd is not None and (not isinstance(dwd, int) or dwd < 1 or dwd > 365):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"dedup_window_days={dwd} invalid (use 1-365)", "suggestion": "Use 30"})
        mps = alc.get("max_per_source")
        if mps is not None and (not isinstance(mps, int) or mps < 1 or mps > 50):
            issues.append({"severity": "warning", "component": "auto_learning", "message": f"max_per_source={mps} invalid (use 1-50)", "suggestion": "Use 3"})

    for i in issues:
        msg = f"[Config] {i['component']}: {i['message']}"
        if i.get("suggestion"):
            msg += f" (→ {i['suggestion']})"
        if i.get("severity") == "error":
            logger.error(msg)
        else:
            logger.warning(msg)

    return issues


def normalize_runtime_configs(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Normalize autonomy and introspection runtime configs to safe values.
    Writes corrected JSON back to disk only when values change.
    
    Returns a structured result:
    {
        "changed": [...],
        "warnings": [...],
        "errors": [...],
        "files_checked": [...],
    }
    """
    import json
    root = project_root or Path(__file__).parent.parent
    config_dir = root / "config"
    result: Dict[str, Any] = {
        "changed": [],
        "warnings": [],
        "errors": [],
        "files_checked": [],
        "failed_files": [],  # basename e.g. autonomy.json — skip post-normalize validate for these
    }

    def _load_json(path: Path, name: str) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON in {name}: {e}"
            logger.error(f"[Startup] {msg}")
            result["errors"].append(msg)
            result["failed_files"].append(name)
            return None

    # autonomy.json normalization
    auto_path = config_dir / "autonomy.json"
    if auto_path.exists():
        result["files_checked"].append(str(auto_path))
        cfg = _load_json(auto_path, "autonomy.json")
        if cfg is not None:
            changed = False
            old = cfg.get("max_actions_per_hour")
            # Normalize to safe default if invalid/missing
            if old is None or not isinstance(old, int) or old < 1 or old > 60:
                new_val = 6
                cfg["max_actions_per_hour"] = new_val
                result["changed"].append({
                    "file": "autonomy.json",
                    "field": "max_actions_per_hour",
                    "old_value": old,
                    "new_value": new_val,
                })
                changed = True
            if changed:
                try:
                    auto_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                except Exception as e:
                    msg = f"Failed to write normalized autonomy.json: {e}"
                    logger.error(f"[Startup] {msg}")
                    result["errors"].append(msg)
                    result["failed_files"].append("autonomy.json")

    # introspection.json normalization
    intro_path = config_dir / "introspection.json"
    if intro_path.exists():
        result["files_checked"].append(str(intro_path))
        cfg = _load_json(intro_path, "introspection.json")
        if cfg is not None:
            changed = False
            old = cfg.get("throttle_minutes")
            # Normalize to safe default if invalid/missing
            if old is None or not isinstance(old, (int, float)) or old < 1 or old > 120:
                new_val = 30
                cfg["throttle_minutes"] = new_val
                result["changed"].append({
                    "file": "introspection.json",
                    "field": "throttle_minutes",
                    "old_value": old,
                    "new_value": new_val,
                })
                changed = True
            if changed:
                try:
                    intro_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                except Exception as e:
                    msg = f"Failed to write normalized introspection.json: {e}"
                    logger.error(f"[Startup] {msg}")
                    result["errors"].append(msg)
                    result["failed_files"].append("introspection.json")

    # auto_learning.json normalization (quality gates, caps, dedup)
    al_path = config_dir / "auto_learning.json"
    if al_path.exists():
        result["files_checked"].append(str(al_path))
        cfg = _load_json(al_path, "auto_learning.json")
        if cfg is not None:
            changed = False
            _int_specs = [
                ("min_relevance_score", 1, 0, 10),
                ("max_archived_per_session", 100, 10, 500),
                ("max_memory_per_session", 20, 1, 100),
                ("max_per_source_memory", 5, 1, 50),
                ("dedup_window_days", 30, 1, 365),
                ("max_chatlogs", 20, 0, 500),
                ("max_per_source", 3, 1, 50),
            ]
            _float_specs = [("interval_hours", 6.0, 0.5, 24)]
            for field, default, min_val, max_val in _int_specs:
                old = cfg.get(field)
                try:
                    v = int(old) if old is not None else None
                except (TypeError, ValueError):
                    v = None
                if v is None:
                    new_val = default
                    cfg[field] = new_val
                    result["changed"].append({"file": "auto_learning.json", "field": field, "old_value": old, "new_value": new_val})
                    changed = True
                elif v < min_val or v > max_val:
                    new_val = max(min_val, min(max_val, v))
                    cfg[field] = new_val
                    result["changed"].append({"file": "auto_learning.json", "field": field, "old_value": old, "new_value": new_val})
                    changed = True
            for field, default, min_val, max_val in _float_specs:
                old = cfg.get(field)
                try:
                    v = float(old) if old is not None else None
                except (TypeError, ValueError):
                    v = None
                if v is None:
                    new_val = default
                    cfg[field] = new_val
                    result["changed"].append({"file": "auto_learning.json", "field": field, "old_value": old, "new_value": new_val})
                    changed = True
                elif v < min_val or v > max_val:
                    new_val = max(min_val, min(max_val, v))
                    cfg[field] = new_val
                    result["changed"].append({"file": "auto_learning.json", "field": field, "old_value": old, "new_value": new_val})
                    changed = True
            old_allow = cfg.get("allow_reddit_into_memory")
            if old_allow is None or not isinstance(old_allow, bool):
                new_val = False
                if cfg.get("allow_reddit_into_memory") != new_val:
                    cfg["allow_reddit_into_memory"] = new_val
                    result["changed"].append({"file": "auto_learning.json", "field": "allow_reddit_into_memory", "old_value": old_allow, "new_value": new_val})
                    changed = True
            if changed:
                try:
                    al_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                except Exception as e:
                    msg = f"Failed to write normalized auto_learning.json: {e}"
                    logger.error(f"[Startup] {msg}")
                    result["errors"].append(msg)
                    result["failed_files"].append("auto_learning.json")

    return result


if __name__ == "__main__":
    # Example usage
    import sys
    
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    validator = ConfigValidator(config_path)
    
    results = validator.validate_all()
    
    print("=" * 60)
    print("Configuration Validation Results")
    print("=" * 60)
    
    if results["valid"]:
        print("[OK] Configuration is valid!")
    else:
        print("[FAIL] Configuration has errors:")
        for error in results["errors"]:
            print(f"  ERROR: {error['component']} - {error['message']}")
            if error.get("suggestion"):
                print(f"    → {error['suggestion']}")
    
    if results["warnings"]:
        print("\n[WARN] Warnings:")
        for warning in results["warnings"]:
            print(f"  WARNING: {warning['component']} - {warning['message']}")
            if warning.get("suggestion"):
                print(f"    → {warning['suggestion']}")
    
    if results["info"]:
        print("\n[INFO] Info:")
        for info in results["info"][:5]:  # Show first 5
            print(f"  INFO: {info['component']} - {info['message']}")
    
    print("\n" + "=" * 60)

