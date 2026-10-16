from __future__ import annotations

import json

from project_guardian.guardian_layer import GuardianLayer


def _raise_if_called(*args, **kwargs):
    raise AssertionError("host fingerprint provider touched before activation")


def test_construct_is_read_only_and_does_not_probe_host(tmp_path, monkeypatch):
    import project_guardian.guardian_layer as guardian_layer_module

    for name in ("platform", "machine", "processor", "node"):
        monkeypatch.setattr(guardian_layer_module.platform, name, _raise_if_called)

    config_path = tmp_path / "state" / "guardian.json"
    rebuild_path = tmp_path / "state" / "guardian_rebuild.log"

    layer = GuardianLayer(
        config_path=str(config_path),
        rebuild_log_path=str(rebuild_path),
    )

    assert layer._activated is False
    assert layer.fingerprint is None
    assert not config_path.exists()
    assert not rebuild_path.exists()
    assert not config_path.parent.exists()

    status = layer.get_status()
    assert status["activated"] is False
    assert status["identity_verified"] is None
    assert not config_path.parent.exists()


def test_activate_performs_deferred_first_run_persistence_once(tmp_path, monkeypatch):
    config_path = tmp_path / "state" / "guardian.json"
    rebuild_path = tmp_path / "state" / "guardian_rebuild.log"

    layer = GuardianLayer(
        config_path=str(config_path),
        rebuild_log_path=str(rebuild_path),
    )
    monkeypatch.setattr(
        layer,
        "_generate_system_fingerprint",
        lambda: "a" * 64,
    )

    assert layer.activate() is True
    assert layer._activated is True
    assert layer.fingerprint == "a" * 64
    assert config_path.exists()
    assert not rebuild_path.exists()

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["fingerprint"] == "a" * 64

    before = config_path.read_text(encoding="utf-8")
    assert layer.activate() is True
    assert config_path.read_text(encoding="utf-8") == before


def test_mismatch_alert_and_rebuild_log_wait_for_activation(tmp_path, monkeypatch):
    config_path = tmp_path / "state" / "guardian.json"
    rebuild_path = tmp_path / "state" / "guardian_rebuild.log"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "fingerprint": "old-" + ("b" * 60),
                "contact_email": "operator@example.invalid",
                "smtp_config": {"server": "smtp.invalid"},
            }
        ),
        encoding="utf-8",
    )

    layer = GuardianLayer(
        config_path=str(config_path),
        rebuild_log_path=str(rebuild_path),
    )
    alerts = []
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "c" * 64)
    monkeypatch.setattr(
        layer,
        "send_alert_email",
        lambda **kwargs: alerts.append(kwargs) or True,
    )

    assert alerts == []
    assert not rebuild_path.exists()

    assert layer.activate() is True

    assert len(alerts) == 1
    assert rebuild_path.exists()
    rows = [
        json.loads(line)
        for line in rebuild_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[-1]["old_fingerprint"].startswith("old-")
    assert rows[-1]["new_fingerprint"] == "c" * 64


def test_simultaneous_activation_is_single_flight(tmp_path, monkeypatch):
    """Second explicit caller must not repeat any activation side effect."""
    from threading import Event, Thread, get_ident

    layer = GuardianLayer(
        config_path=str(tmp_path / "state" / "guardian.json"),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "d" * 64)
    original_update = layer._update_fingerprint
    entered, release, second_started = Event(), Event(), Event()
    update_threads, results, errors = [], [], []

    def blocking_update():
        update_threads.append(get_ident())
        entered.set()
        if not release.wait(timeout=5):
            raise AssertionError("activation test timed out")
        original_update()

    monkeypatch.setattr(layer, "_update_fingerprint", blocking_update)

    def worker(second=False):
        try:
            if second:
                second_started.set()
            results.append(layer.activate())
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=worker)
    second = Thread(target=worker, kwargs={"second": True})
    first.start()
    try:
        assert entered.wait(timeout=5), "first activation never entered update"
        second.start()
        assert second_started.wait(timeout=5)
        # Keep the first caller inside the update while the second competes.
        second.join(timeout=0.1)
        assert second.is_alive(), "second activation returned before first completed"
    finally:
        release.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert sorted(results) == [True, True]
    assert len(update_threads) == 1
    assert layer._activated is True
    assert json.loads(layer.config_path.read_text(encoding="utf-8"))["fingerprint"] == "d" * 64


def test_activation_failure_releases_lock_and_allows_explicit_retry(tmp_path, monkeypatch):
    layer = GuardianLayer(
        config_path=str(tmp_path / "state" / "guardian.json"),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "e" * 64)
    original_update = layer._update_fingerprint
    calls = []

    def fail_once():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("synthetic first activation failure")
        return original_update()

    monkeypatch.setattr(layer, "_update_fingerprint", fail_once)
    assert layer.activate() is False
    assert layer._activated is False
    assert not layer.config_path.exists()
    assert layer.activate() is True
    assert len(calls) == 2
    assert layer._activated is True
