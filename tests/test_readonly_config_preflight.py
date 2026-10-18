"""Read-only preflight must not create or alter storage files."""
import importlib.util
from pathlib import Path


def _validator_class():
    path = Path(__file__).resolve().parents[1] / "project_guardian" / "config_validator.py"
    spec = importlib.util.spec_from_file_location("isolated_config_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConfigValidator


def test_readonly_preflight_does_not_create_missing_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    validator = _validator_class()(read_only=True)
    issues = validator._check_directories() + validator._check_permissions() + validator._check_database()
    assert issues
    assert not (tmp_path / "data").exists()


def test_readonly_preflight_preserves_existing_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    for dirname in ("backups", "vault"):
        (data / dirname).mkdir(parents=True, exist_ok=True)
    sentinel = data / "test.db"
    sentinel.write_bytes(b"preserve-existing-database")
    before = sentinel.read_bytes()
    validator = _validator_class()(read_only=True)
    validator._check_directories()
    validator._check_permissions()
    validator._check_database()
    assert sentinel.read_bytes() == before
    assert not (data / ".permission_test").exists()
