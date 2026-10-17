"""Adversarial persistence tests stacked on Guardian PR #135.

Only tmp_path, fictional credentials, monkeypatch; never an SMTP/network provider.
"""
import json
from contextlib import contextmanager
from threading import Event, Thread

import pytest

from project_guardian.guardian_layer import GuardianLayer


OLD = "a" * 64
NEW = "b" * 64


def _seed(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "fingerprint": OLD,
        "contact_email": "owner@example.invalid",
        "smtp_config": {"server": "smtp.invalid", "port": 2525},
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    return state


def _layer(tmp_path):
    return GuardianLayer(
        config_path=str(tmp_path / "guardian.json"),
        rebuild_log_path=str(tmp_path / "events.jsonl"),
    )


def test_corruption_after_valid_load_refuses_activation_without_probe(tmp_path, monkeypatch):
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    path.write_bytes(b'{"broken":')
    original = path.read_bytes()
    seen = []
    monkeypatch.setattr(layer, "_generate_system_fingerprint",
                        lambda: seen.append("probe") or NEW)
    assert layer.activate() is False
    assert seen == []
    assert layer._state_load_error is True
    assert layer._activated is False
    assert path.read_bytes() == original
    assert not layer.rebuild_log_path.exists()


@pytest.mark.parametrize("new_fingerprint", [OLD, NEW])
def test_external_edit_after_load_refuses_noop_or_write(
    tmp_path, monkeypatch, new_fingerprint
):
    path = tmp_path / "guardian.json"
    original = _seed(path)
    layer = _layer(tmp_path)
    revised = dict(original, contact_email="new-owner@example.invalid")
    path.write_text(json.dumps(revised), encoding="utf-8")
    original_bytes = path.read_bytes()
    monkeypatch.setattr(layer, "_generate_system_fingerprint",
                        lambda: new_fingerprint)
    assert layer.activate() is False
    assert path.read_bytes() == original_bytes
    assert layer._state_load_error is True
    assert not layer.rebuild_log_path.exists()


def test_direct_save_and_setters_refuse_corruption_after_load(tmp_path):
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    path.write_bytes(b"not-json")
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match="changed since load"):
        layer.save()
    with pytest.raises(RuntimeError, match="configuration invalid"):
        layer.set_contact_email("attacker@example.invalid")
    with pytest.raises(RuntimeError, match="configuration invalid"):
        layer.configure_smtp("attacker.invalid")
    assert path.read_bytes() == original
    assert layer.contact_email == "owner@example.invalid"
    assert layer.smtp_config["server"] == "smtp.invalid"


def test_two_instances_do_not_publish_duplicate_rebuild_or_alert(
    tmp_path, monkeypatch
):
    path = tmp_path / "guardian.json"
    _seed(path)
    first, second = _layer(tmp_path), _layer(tmp_path)
    sent = []
    for i, layer in enumerate((first, second)):
        monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: NEW)
        monkeypatch.setattr(
            layer, "send_alert_email",
            lambda i=i, **kwargs: sent.append(i) or True,
        )
    assert first.activate() is True
    assert second.activate() is False
    assert sent == [0]
    assert second._state_load_error is True
    assert len(first.rebuild_log_path.read_text().splitlines()) == 1
    assert json.loads(path.read_text())["fingerprint"] == NEW


def test_concurrent_instance_commits_are_serialized(tmp_path, monkeypatch):
    path = tmp_path / "guardian.json"
    _seed(path)
    first, second = _layer(tmp_path), _layer(tmp_path)
    for layer in (first, second):
        monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: NEW)
    alerts = []
    monkeypatch.setattr(first, "send_alert_email",
                        lambda **kw: alerts.append("first") or True)
    monkeypatch.setattr(second, "send_alert_email",
                        lambda **kw: alerts.append("second") or True)
    real_lock = first._exclusive_persistence_lock
    entered, release = Event(), Event()

    @contextmanager
    def paused_lock():
        with real_lock():
            entered.set()
            assert release.wait(timeout=5), "first writer not released"
            yield

    monkeypatch.setattr(first, "_exclusive_persistence_lock", paused_lock)
    results = {}

    a = Thread(target=lambda: results.setdefault("first", first.activate()))
    b = Thread(target=lambda: results.setdefault("second", second.activate()))
    a.start()
    try:
        assert entered.wait(timeout=5), "first writer did not acquire lock"
        b.start()
        b.join(timeout=0.1)
        assert b.is_alive(), "second writer bypassed the shared persistence lock"
    finally:
        release.set()
        a.join(timeout=5)
        if b.ident is not None:
            b.join(timeout=5)
    assert not a.is_alive() and not b.is_alive()
    assert results == {"first": True, "second": False}
    assert alerts == ["first"]
    assert len(first.rebuild_log_path.read_text().splitlines()) == 1
    assert json.loads(path.read_text())["fingerprint"] == NEW


def test_explicit_valid_reload_can_resume_after_external_change(tmp_path, monkeypatch):
    path = tmp_path / "guardian.json"
    state = _seed(path)
    layer = _layer(tmp_path)
    state["contact_email"] = "new-owner@example.invalid"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert layer.activate() is False
    layer.load()  # Explicit operator-mediated revalidation, not automatic overwrite.
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: NEW)
    delivered = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kwargs: delivered.append(kwargs) or True)
    assert layer.activate() is True
    assert layer.contact_email == "new-owner@example.invalid"
    assert len(delivered) == 1
    assert json.loads(path.read_text())["contact_email"] == "new-owner@example.invalid"
