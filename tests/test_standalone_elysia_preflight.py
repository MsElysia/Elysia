"""Standalone preflight regression: no runtime imports or disk mutation."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_help_runs_without_runtime_dependencies(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "elysia_preflight.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "Read-only" in result.stdout


def test_preflight_rejects_corrupt_config_without_creating_storage(tmp_path):
    config = tmp_path / "broken.json"
    config.write_text("{invalid", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "elysia_preflight.py"), "--config", str(config), "--json"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert any(item["component"] == "config" for item in payload["errors"])
    assert not (tmp_path / "data").exists()
    assert config.read_text(encoding="utf-8") == "{invalid"
