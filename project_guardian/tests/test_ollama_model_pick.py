"""Tests for ollama_model_pool and pick_ollama_model_for_decider."""

from __future__ import annotations

import json

import pytest

from project_guardian import ollama_model_config as om


@pytest.fixture(autouse=True)
def _reset_ollama_cfg(monkeypatch):
    om.reset_log_flag_for_tests()
    for k in ("ELYSIA_OLLAMA_MODEL", "OLLAMA_MODEL"):
        monkeypatch.delenv(k, raising=False)
    yield
    om.reset_log_flag_for_tests()


def test_pick_round_robin(tmp_path, monkeypatch):
    p = tmp_path / "mistral_decider.json"
    p.write_text(
        json.dumps(
            {
                "ollama_model_pool": ["model-a", "model-b"],
                "ollama_model_pick_strategy": "round_robin",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(om, "_MISTRAL_DECIDER_PATH", p)
    assert om.pick_ollama_model_for_decider(decision_cycle=0) == "model-a"
    assert om.pick_ollama_model_for_decider(decision_cycle=1) == "model-b"
    assert om.pick_ollama_model_for_decider(decision_cycle=2) == "model-a"


def test_pick_alternate_stagnation(tmp_path, monkeypatch):
    p = tmp_path / "mistral_decider.json"
    p.write_text(
        json.dumps(
            {
                "ollama_model_pool": ["light", "heavy"],
                "ollama_model_pick_strategy": "alternate_stagnation",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(om, "_MISTRAL_DECIDER_PATH", p)
    assert om.pick_ollama_model_for_decider(decision_cycle=0) == "light"
    assert om.pick_ollama_model_for_decider(decision_cycle=4) == "heavy"
    assert om.pick_ollama_model_for_decider(decision_cycle=8) == "light"


def test_env_overrides_pool(tmp_path, monkeypatch):
    p = tmp_path / "mistral_decider.json"
    p.write_text(
        json.dumps({"ollama_model_pool": ["a", "b"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(om, "_MISTRAL_DECIDER_PATH", p)
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "from-env")
    assert om.pick_ollama_model_for_decider(decision_cycle=99) == "from-env"


def test_pick_process_monotonic_advances_without_cycle(tmp_path, monkeypatch):
    p = tmp_path / "mistral_decider.json"
    p.write_text(
        json.dumps(
            {
                "ollama_model_pool": ["model-a", "model-b"],
                "ollama_model_pick_strategy": "round_robin",
                "ollama_model_pick_index_mode": "process_monotonic",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(om, "_MISTRAL_DECIDER_PATH", p)
    assert om.pick_ollama_model_for_decider(decision_cycle=0) == "model-a"
    assert om.pick_ollama_model_for_decider(decision_cycle=0) == "model-b"
    assert om.pick_ollama_model_for_decider(decision_cycle=0) == "model-a"


def test_canonical_is_pool_primary(tmp_path, monkeypatch):
    p = tmp_path / "mistral_decider.json"
    p.write_text(
        json.dumps({"ollama_model_pool": ["first", "second"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(om, "_MISTRAL_DECIDER_PATH", p)
    assert om.get_canonical_ollama_model(log_once=False) == "first"
