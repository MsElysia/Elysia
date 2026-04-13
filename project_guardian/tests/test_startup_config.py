# project_guardian/tests/test_startup_config.py
# Regression tests for runtime config normalization ordering

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.startup_health import run_startup_health_check
from project_guardian.config_validator import normalize_runtime_configs, validate_runtime_configs


@pytest.fixture
def project_root(tmp_path):
    """Minimal project root with config dir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return tmp_path


@pytest.fixture
def mock_learned_storage(monkeypatch, tmp_path):
    """Make learned storage use tmp_path to avoid real disk."""
    learned = tmp_path / "learned"
    learned.mkdir(parents=True, exist_ok=True)

    def _fake():
        return learned

    monkeypatch.setattr(
        "project_guardian.auto_learning.get_learned_storage_path",
        _fake,
    )
    return learned


class TestConfigNormalizationOrdering:
    """Normalize before validate; no duplicate reporting."""

    def test_normalize_runs_before_validate(self, project_root, mock_learned_storage):
        """normalize_runtime_configs runs before validate in startup health."""
        # autonomy.json with invalid max_actions_per_hour
        autonomy = project_root / "config" / "autonomy.json"
        autonomy.write_text(json.dumps({"enabled": True, "max_actions_per_hour": 999}), encoding="utf-8")
        # introspection.json with invalid throttle_minutes
        intro = project_root / "config" / "introspection.json"
        intro.write_text(json.dumps({"enabled": True, "throttle_minutes": 999}), encoding="utf-8")

        passed, issues, details = run_startup_health_check(project_root)

        # Normalization should have run first and corrected values
        norm_changed = details.get("norm_changed", [])
        assert len(norm_changed) >= 2
        fields_changed = {c["field"] for c in norm_changed}
        assert "max_actions_per_hour" in fields_changed
        assert "throttle_minutes" in fields_changed

        # Validation runs on normalized state - should NOT report errors for normalized fields
        validation_errors = details.get("validation_errors", [])
        # No validation errors for max_actions_per_hour or throttle_minutes (already corrected)
        for err in validation_errors:
            assert "max_actions_per_hour" not in (err.get("message") or "")
            assert "throttle_minutes" not in (err.get("message") or "")

    def test_first_bad_boot_reports_normalization_not_duplicate_validation(self, project_root, mock_learned_storage):
        """First boot with bad values: normalization messages in issues, not duplicate validation for same fields."""
        autonomy = project_root / "config" / "autonomy.json"
        autonomy.write_text(json.dumps({"max_actions_per_hour": "not_an_int"}), encoding="utf-8")

        passed, issues, details = run_startup_health_check(project_root)

        norm_changed = details.get("norm_changed", [])
        assert any("max_actions_per_hour" in str(c) for c in norm_changed)
        # Issues should contain normalization message
        norm_msgs = [m for m in issues if "Normalized" in m and "max_actions_per_hour" in m]
        assert len(norm_msgs) >= 1

    def test_second_clean_boot_no_warnings_for_normalized_fields(self, project_root, mock_learned_storage):
        """Second boot after normalization: no new norm_changed, no validation warnings for corrected fields."""
        autonomy = project_root / "config" / "autonomy.json"
        autonomy.write_text(json.dumps({"max_actions_per_hour": 999}), encoding="utf-8")
        intro = project_root / "config" / "introspection.json"
        intro.write_text(json.dumps({"throttle_minutes": 200}), encoding="utf-8")

        # First boot - normalizes
        run_startup_health_check(project_root)

        # Second boot - values already on disk are valid
        passed, issues, details = run_startup_health_check(project_root)
        norm_changed = details.get("norm_changed", [])
        # No new changes (values already corrected)
        assert len(norm_changed) == 0

        # Validation should pass for those files (no warnings for normalized fields)
        validation_errors = details.get("validation_errors", [])
        for err in validation_errors:
            assert "max_actions_per_hour" not in (err.get("message") or "")
            assert "throttle_minutes" not in (err.get("message") or "")

    def test_malformed_json_remains_critical(self, project_root, mock_learned_storage):
        """Malformed JSON in config is a critical error."""
        autonomy = project_root / "config" / "autonomy.json"
        autonomy.write_text("{ invalid json ]", encoding="utf-8")

        passed, issues, details = run_startup_health_check(project_root)

        assert passed is False
        assert details.get("critical") is True
        norm_errors = details.get("norm_errors", [])
        assert any("Invalid JSON" in str(e) for e in norm_errors)
        assert "autonomy.json" in details.get("failed_files", [])

    def test_normalize_allow_reddit_invalid_to_false(self, project_root, mock_learned_storage):
        """Invalid allow_reddit_into_memory normalizes to False, not True."""
        al = project_root / "config" / "auto_learning.json"
        al.write_text(json.dumps({"allow_reddit_into_memory": "yes"}), encoding="utf-8")

        norm = normalize_runtime_configs(project_root)
        changed = norm.get("changed", [])
        arm_changes = [c for c in changed if c.get("field") == "allow_reddit_into_memory"]
        assert len(arm_changes) == 1
        assert arm_changes[0]["new_value"] is False
        assert arm_changes[0]["old_value"] == "yes"
