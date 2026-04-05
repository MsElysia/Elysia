# project_guardian/startup_health.py
# Startup health checks - validate key paths and config before main system runs
#
# AUTHORITATIVE OWNER: run_startup_health_check() is the single entry point for
# startup health per unified boot. It runs normalize + validate once. Callers
# (elysia.py __init__) must consume the stored result; do NOT rerun normalize/validate
# in start() or elsewhere.

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


def run_startup_health_check(project_root: Path) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Run quick health checks before main system initialization.
    Single authoritative pass per boot: normalize runtime configs first, then validate.
    
    Returns:
        (passed, list of warning/error messages, structured_details)
        passed=True means startup can proceed; False means critical failure
        structured_details: passed, issues, norm_changed, norm_errors, failed_files, validation_errors
    """
    project_root = Path(project_root)
    config_dir = project_root / "config"
    issues: List[str] = []
    critical = False
    norm_result: Dict[str, Any] = {}
    runtime_issues: List[Dict[str, Any]] = []

    # 1. Config directory exists
    if not config_dir.exists():
        issues.append(f"[Startup] config/ directory not found at {config_dir}")
        critical = True
    else:
        # 2. Runtime configs: normalize recoverable fields first, then validate remainder
        try:
            from .config_validator import validate_runtime_configs, normalize_runtime_configs
            norm_result = normalize_runtime_configs(project_root)
            for change in norm_result.get("changed", []):
                issues.append(
                    f"[Startup] Normalized {change['file']}.{change['field']}: "
                    f"{change['old_value']} -> {change['new_value']}"
                )
            for err in norm_result.get("errors", []):
                critical = True
                issues.append(f"[Startup] Config normalization error: {err}")
            skip_validate = norm_result.get("failed_files") or []
            runtime_issues = validate_runtime_configs(project_root, skip_files=skip_validate)
            for i in runtime_issues:
                if i.get("severity") == "error":
                    critical = True
                    issues.append(f"Config {i.get('component', '?')}: {i.get('message', '')}")
        except Exception as e:
            issues.append(f"Config validation/normalization failed: {e}")
            critical = True
    
    # 3. External storage (if configured) - check writable
    ext_cfg = config_dir / "external_storage.json"
    if ext_cfg.exists():
        try:
            from .external_storage import normalize_storage_root
            cfg = json.loads(ext_cfg.read_text(encoding="utf-8"))
            base = normalize_storage_root((cfg.get("external_drive") or "").strip())
            if base:
                test_path = Path(base) / "ProjectGuardian" / ".health_check"
                try:
                    test_path.parent.mkdir(parents=True, exist_ok=True)
                    test_path.write_text("ok", encoding="utf-8")
                    test_path.unlink()
                except OSError as e:
                    issues.append(f"[Startup] External storage not writable: {base} - {e}")
                    critical = True
        except Exception as e:
            issues.append(f"[Startup] External storage config error: {e}")
    
    # 4. Learned storage path - ensure we can create it
    try:
        from .auto_learning import get_learned_storage_path
        path = get_learned_storage_path()
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".startup_ok"
        probe.write_text("1", encoding="utf-8")
        probe.unlink()
    except Exception as e:
        issues.append(f"[Startup] Learned storage path not writable: {e}")
        critical = True
    
    # 5. Critical imports for control panel
    try:
        import flask
    except ImportError:
        issues.append("[Startup] Flask not installed - control panel will not be available")
    try:
        import httpx
    except ImportError:
        issues.append("[Startup] httpx not installed - learning (RSS/Reddit) may fail")
    
    passed = not critical
    if issues:
        for msg in issues:
            if critical and msg.startswith("[Startup]"):
                logger.error(msg)
            else:
                logger.warning(msg)

    structured_details: Dict[str, Any] = {
        "passed": passed,
        "issues": issues,
        "critical": critical,
        "norm_changed": norm_result.get("changed", []),
        "norm_errors": norm_result.get("errors", []),
        "failed_files": norm_result.get("failed_files", []),
        "validation_errors": [i for i in runtime_issues if i.get("severity") == "error"],
    }

    return passed, issues, structured_details
