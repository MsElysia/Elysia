# project_guardian/tests/test_external_data_mirror.py
from __future__ import annotations

import asyncio
import json

import pytest

import project_guardian.external_storage as external_storage
import project_guardian.orchestration.telemetry.sqlite_store as sqlite_store_mod
from project_guardian.orchestration.telemetry.events import LLMCallEvent
from project_guardian.orchestration.telemetry.sqlite_store import TelemetrySqliteStore


def test_get_configured_external_data_dir_disabled_by_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELYSIA_DISABLE_EXTERNAL_DATA_MIRROR", "1")
    cfg = tmp_path / "external_storage.json"
    cfg.write_text(
        json.dumps({"use_external_storage": True, "data_dir": str(tmp_path / "should_not_create")}),
        encoding="utf-8",
    )
    monkeypatch.setattr(external_storage, "EXTERNAL_STORAGE_CONFIG_PATH", cfg)
    external_storage._mirror_data_dir_cache = None
    assert external_storage.get_configured_external_data_dir() is None


def test_get_configured_external_data_dir_creates_and_returns_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELYSIA_DISABLE_EXTERNAL_DATA_MIRROR", raising=False)
    ext = tmp_path / "usb_data"
    cfg = tmp_path / "external_storage.json"
    cfg.write_text(json.dumps({"use_external_storage": True, "data_dir": str(ext)}), encoding="utf-8")
    monkeypatch.setattr(external_storage, "EXTERNAL_STORAGE_CONFIG_PATH", cfg)
    external_storage._mirror_data_dir_cache = None
    got = external_storage.get_configured_external_data_dir()
    assert got == ext
    assert ext.is_dir()


def test_capability_usage_log_mirrored_to_external_data_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELYSIA_DISABLE_EXTERNAL_DATA_MIRROR", raising=False)
    import project_guardian.capability_registry as cr

    local = tmp_path / "localdata"
    local.mkdir(parents=True, exist_ok=True)
    ext = tmp_path / "usb_data"
    cfg = tmp_path / "external_storage.json"
    cfg.write_text(json.dumps({"use_external_storage": True, "data_dir": str(ext)}), encoding="utf-8")

    monkeypatch.setattr(cr, "DATA_DIR", local)
    monkeypatch.setattr(cr, "USAGE_LOG_PATH", local / "capability_usage_log.jsonl")
    monkeypatch.setattr(cr, "USAGE_STATS_PATH", local / "capability_usage_stats.json")
    monkeypatch.setattr(external_storage, "EXTERNAL_STORAGE_CONFIG_PATH", cfg)
    external_storage._mirror_data_dir_cache = None

    reg = cr.CapabilityRegistry()
    reg.log_capability_usage(
        task="mirror_test",
        capability_id="test_cap",
        capability_type="autonomy_action",
        success=True,
        quality=0.7,
        latency_ms=12.3,
    )

    mirror_log = ext / "capability_usage_log.jsonl"
    assert mirror_log.exists()
    text = mirror_log.read_text(encoding="utf-8")
    assert "mirror_test" in text
    assert "test_cap" in text


def test_orchestration_telemetry_db_mirrored_after_log_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELYSIA_DISABLE_EXTERNAL_DATA_MIRROR", raising=False)
    ext = tmp_path / "usb_data"
    ext.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sqlite_store_mod, "get_configured_external_data_dir", lambda: ext)

    src = tmp_path / "orch.db"
    store = TelemetrySqliteStore(src, telemetry_mirror_interval_sec=0.01)
    ev = LLMCallEvent(
        task_id="t1",
        pipeline_id="p1",
        node_id="plan",
        provider="ollama",
        model="m1",
        prompt_hash="abc",
        latency_ms=1.0,
        input_tokens_est=1,
        output_tokens_est=1,
        cost_estimate_usd=0.0,
        outcome_score=None,
        review_verdict=None,
        success=True,
        task_type="reasoning",
    )
    asyncio.run(store.log_call(ev))

    mirror_db = ext / "orchestration_telemetry.db"
    assert mirror_db.exists()
    import sqlite3

    with sqlite3.connect(str(mirror_db)) as conn:
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    assert int(n) >= 1
