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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _probe_drive_project_guardian_writable(base: str, project_name: str = "ProjectGuardian") -> bool:
    """Return True when a drive root supports a ProjectGuardian health-check write."""
    from .external_storage import normalize_storage_root

    root = normalize_storage_root((base or "").strip())
    if not root:
        return False
    drive = Path(root)
    if not drive.exists():
        return False
    test_path = drive / project_name / ".health_check"
    try:
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text("ok", encoding="utf-8")
        test_path.unlink()
        return True
    except OSError:
        return False


def _assess_external_storage_startup(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Check external storage writability with the same fallback order as runtime storage.

    Returns:
        (critical, issue_messages) — critical=True only when no writable path exists.
    """
    from .external_storage import get_default_fallback_path, normalize_storage_root

    use_external = bool(cfg.get("use_external_storage"))
    external_drive = (cfg.get("external_drive") or "").strip()
    if not use_external and not external_drive:
        return False, []

    fallback_drives = cfg.get("fallback_drives") or []
    candidates: List[str] = []
    if external_drive:
        candidates.append(external_drive)
    for drive in fallback_drives:
        ds = str(drive).strip()
        if ds and ds not in candidates:
            candidates.append(ds)

    primary_norm = normalize_storage_root(external_drive) if external_drive else ""
    chosen_drive: Optional[str] = None
    for candidate in candidates:
        if _probe_drive_project_guardian_writable(candidate):
            chosen_drive = normalize_storage_root(candidate)
            break

    issues: List[str] = []
    if chosen_drive:
        if primary_norm and chosen_drive != primary_norm:
            issues.append(
                f"[Startup] External storage primary {primary_norm} unavailable; "
                f"using fallback drive {chosen_drive}"
            )
        return False, issues

    local_base = get_default_fallback_path()
    try:
        local_base.mkdir(parents=True, exist_ok=True)
        probe = local_base / ".health_check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        tried = ", ".join(normalize_storage_root(c) for c in candidates) if candidates else "(none)"
        issues.append(
            f"[Startup] External storage not writable (tried {tried}) "
            f"and local fallback failed: {local_base} - {e}"
        )
        return True, issues

    tried = ", ".join(normalize_storage_root(c) for c in candidates) if candidates else "(none)"
    issues.append(
        f"[Startup] External storage unavailable (tried {tried}); "
        f"using local fallback: {local_base}"
    )
    return False, issues


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
    
    # 3. External storage (if configured) - primary, fallback drives, then local path
    ext_cfg = config_dir / "external_storage.json"
    if ext_cfg.exists():
        try:
            cfg = json.loads(ext_cfg.read_text(encoding="utf-8"))
            ext_critical, ext_issues = _assess_external_storage_startup(cfg)
            issues.extend(ext_issues)
            if ext_critical:
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
