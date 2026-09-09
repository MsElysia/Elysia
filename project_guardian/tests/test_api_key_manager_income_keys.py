# project_guardian/tests/test_api_key_manager_income_keys.py
from __future__ import annotations

import pytest


@pytest.fixture
def skip_api_keys_folder(monkeypatch):
    """Avoid merging developer machine's API keys folder into isolated tests."""
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm.APIKeyManager, "_load_from_folder", lambda self: False)


def test_resolve_gumroad_from_api_keys_json(monkeypatch, tmp_path, skip_api_keys_folder):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)
    cfg = tmp_path / "api_keys.json"
    cfg.write_text('{"gumroad": {"api_key": "tok-json"}}', encoding="utf-8")
    mgr = akm.APIKeyManager(config_path=cfg)
    monkeypatch.setattr(akm, "_global_manager", mgr)
    assert akm.resolve_gumroad_access_token() == "tok-json"


def test_resolve_gumroad_from_env(monkeypatch, tmp_path, skip_api_keys_folder):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "tok-env")
    missing = tmp_path / "none.json"
    mgr = akm.APIKeyManager(config_path=missing)
    monkeypatch.setattr(akm, "_global_manager", mgr)
    assert akm.resolve_gumroad_access_token() == "tok-env"


def test_resolve_stripe_from_env(monkeypatch, tmp_path, skip_api_keys_folder):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_env")
    mgr = akm.APIKeyManager(config_path=tmp_path / "none.json")
    monkeypatch.setattr(akm, "_global_manager", mgr)
    assert akm.resolve_stripe_secret_key() == "sk_test_env"


def test_env_overwrites_config_for_gumroad(monkeypatch, tmp_path, skip_api_keys_folder):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "env-wins")
    cfg = tmp_path / "api_keys.json"
    cfg.write_text('{"gumroad": {"api_key": "from-json"}}', encoding="utf-8")
    mgr = akm.APIKeyManager(config_path=cfg)
    monkeypatch.setattr(akm, "_global_manager", mgr)
    assert akm.resolve_gumroad_access_token() == "env-wins"


def test_persist_income_keys_merges_into_config(tmp_path, monkeypatch, skip_api_keys_folder):
    import json
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(akm, "_global_manager", None)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "api_keys.json"
    cfg_path.write_text('{"openai": "keep-me"}', encoding="utf-8")
    akm.persist_income_keys_to_config_file(gumroad_access_token="g1", stripe_secret_key="sk_x")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data.get("openai") == "keep-me"
    assert data["gumroad"]["api_key"] == "g1"
    assert data["stripe"]["api_key"] == "sk_x"


def test_persist_clear_gumroad(tmp_path, monkeypatch, skip_api_keys_folder):
    import json
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(akm, "_global_manager", None)
    cfg_path = tmp_path / "config" / "api_keys.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text('{"gumroad": {"api_key": "old"}}', encoding="utf-8")
    akm.persist_income_keys_to_config_file(clear_gumroad=True)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "gumroad" not in data


def test_income_keys_status_reports_api_keys_folder_source(tmp_path, monkeypatch):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)
    folder = tmp_path / "API keys"
    folder.mkdir()
    (folder / "gumroad access token.txt").write_text("folder-gumroad", encoding="utf-8")

    status = akm.income_keys_ui_status()

    assert status["gumroad_configured"] is True
    assert status["gumroad_in_api_keys_folder"] is True
    assert status["gumroad_effective_source"] == "api_keys_folder"


def test_income_keys_status_reports_env_over_config_source(tmp_path, monkeypatch, skip_api_keys_folder):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(akm, "_global_manager", None)
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "env-gumroad")
    cfg_path = tmp_path / "config" / "api_keys.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text('{"gumroad": {"api_key": "config-gumroad"}}', encoding="utf-8")

    status = akm.income_keys_ui_status()

    assert status["gumroad_configured"] is True
    assert status["gumroad_from_env"] is True
    assert status["gumroad_in_config_file"] is True
    assert status["gumroad_effective_source"] == "env"
