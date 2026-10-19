from __future__ import annotations

import json
from contextlib import contextmanager
from threading import Event, Thread

import pytest

from project_guardian.guardian_layer import GuardianLayer


@pytest.mark.parametrize("setter", ["contact", "smtp"])
def test_stale_setter_discards_attempt_revokes_activation_and_requires_reload(
    tmp_path, monkeypatch, setter
):
    config = tmp_path / "guardian.json"
    config.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "original@example.invalid",
        "smtp_config": {"server": "original.invalid"},
    }), encoding="utf-8")
    stale = GuardianLayer(str(config), str(tmp_path / "rebuild.log"))
    writer = GuardianLayer(str(config), str(tmp_path / "writer.log"))
    monkeypatch.setattr(stale, "_generate_system_fingerprint", lambda: "a" * 64)
    assert stale.activate() is True
    prior_contact, prior_smtp = stale.contact_email, stale.smtp_config.copy()
    writer.set_contact_email("newer@example.invalid")
    writer.configure_smtp("newer.invalid", smtp_port=2525)
    durable = config.read_bytes()

    def attempt():
        if setter == "contact":
            stale.set_contact_email("uncommitted@example.invalid")
        else:
            stale.configure_smtp("uncommitted.invalid")

    with pytest.raises(RuntimeError, match="changed since load"):
        attempt()
    assert config.read_bytes() == durable
    assert stale.contact_email == prior_contact
    assert stale.smtp_config == prior_smtp
    assert stale.get_status()["activated"] is False
    assert stale._state_load_error is True
    assert stale.activate() is False
    for update in (lambda: stale.set_contact_email("blocked@example.invalid"),
                   lambda: stale.configure_smtp("blocked.invalid"), stale.save):
        with pytest.raises(RuntimeError):
            update()
        assert config.read_bytes() == durable

    stale.load()
    assert stale.contact_email == "newer@example.invalid"
    assert stale.smtp_config["server"] == "newer.invalid"
    assert stale.get_status()["activated"] is False
    assert stale.activate() is True
    attempt()
    reopened = GuardianLayer(str(config), str(tmp_path / "reopened.log"))
    assert reopened.contact_email == stale.contact_email
    assert reopened.smtp_config == stale.smtp_config


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


def _competing_activation(layer, entered, release, *, allow_committed_early_return=False):
    """Start caller two while caller one is blocked inside a guarded effect."""
    from threading import Event, Thread

    results, errors = [], []
    second_started = Event()

    def call(index):
        if index == 2:
            second_started.set()
        try:
            results.append((index, layer.activate()))
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=call, args=(1,))
    second = Thread(target=call, args=(2,))
    first.start()
    try:
        assert entered.wait(timeout=5), "first activation did not reach injected boundary"
        second.start()
        assert second_started.wait(timeout=5)
        second.join(timeout=0.1)
        if allow_committed_early_return:
            # Once the complete durable state has committed, returning during
            # notification is safe and is required to avoid callback re-entry
            # deadlocks. No caller may return early with uncommitted state.
            if not second.is_alive():
                assert layer._activated is True
                persisted = json.loads(layer.config_path.read_text(encoding="utf-8"))
                assert persisted["fingerprint"] == layer.fingerprint
        else:
            assert second.is_alive(), "second caller passed before durable commit"
    finally:
        release.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    return dict(results)


def test_failed_persistence_during_overlapping_activation(tmp_path, monkeypatch):
    """Vega failure #1: rejected save must not create a phantom fingerprint."""
    from threading import Event

    layer = GuardianLayer(
        config_path=str(tmp_path / "state" / "guardian.json"),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "f" * 64)
    actual_save = layer.save
    entered, release = Event(), Event()
    calls = []

    def fail_once_after_assignment():
        calls.append(layer.fingerprint)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=5)
            raise OSError("synthetic persistence denied")
        return actual_save()

    monkeypatch.setattr(layer, "save", fail_once_after_assignment)
    results = _competing_activation(layer, entered, release)
    assert results == {1: False, 2: True}
    assert calls == ["f" * 64, "f" * 64]
    assert layer._activated is True
    assert layer.fingerprint == "f" * 64
    assert json.loads(layer.config_path.read_text(encoding="utf-8"))["fingerprint"] == "f" * 64
    assert not layer.rebuild_log_path.exists()


def test_atomic_persistence_failure_keeps_prior_file_and_single_notification(tmp_path, monkeypatch):
    """Failed atomic replace preserves the old bytes; only a successful retry alerts."""
    import project_guardian.guardian_layer as guardian_module
    from threading import Event

    path = tmp_path / "state" / "guardian.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"fingerprint": "a" * 64,
                    "contact_email": "operator@example.invalid",
                    "smtp_config": {"server": "smtp.invalid"}}),
        encoding="utf-8",
    )
    before = path.read_bytes()
    layer = GuardianLayer(
        config_path=str(path),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "b" * 64)
    notifications = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kwargs: notifications.append(kwargs) or True)

    original_replace = guardian_module.os.replace
    entered, release = Event(), Event()
    calls = []

    def fail_replace_once(src, dst):
        calls.append((src, dst))
        if len(calls) == 1:
            # Atomic publication has not occurred; original config is intact.
            assert path.read_bytes() == before
            entered.set()
            assert release.wait(timeout=5)
            raise OSError("synthetic replace denied")
        return original_replace(src, dst)

    monkeypatch.setattr(guardian_module.os, "replace", fail_replace_once)
    results = _competing_activation(layer, entered, release)
    assert results == {1: False, 2: True}
    assert len(calls) == 2
    assert len(notifications) == 1
    assert layer.fingerprint == "b" * 64
    assert json.loads(path.read_text(encoding="utf-8"))["fingerprint"] == "b" * 64
    events = [json.loads(line) for line in layer.rebuild_log_path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["old_fingerprint"] == "a" * 64
    assert events[0]["new_fingerprint"] == "b" * 64
    assert not list(path.parent.glob(".guardian-*.tmp"))


def test_post_alert_failure_does_not_retry_completed_side_effects(tmp_path, monkeypatch):
    """Vega failure #2: an alert that lands must not be emitted twice on retry."""
    from threading import Event

    path = tmp_path / "state" / "guardian.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "operator@example.invalid",
        "smtp_config": {"server": "smtp.invalid"}
    }), encoding="utf-8")
    layer = GuardianLayer(
        config_path=str(path),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "z" * 64)
    entered, release = Event(), Event()
    notifications = []

    def send_and_pause(**kwargs):
        notifications.append(kwargs)
        entered.set()
        assert release.wait(timeout=5)
        return True

    monkeypatch.setattr(layer, "send_alert_email", send_and_pause)
    original_check = layer._check_and_alert

    def raise_after_alert(*args, **kwargs):
        original_check(*args, **kwargs)
        raise OSError("synthetic error after alert already sent")

    monkeypatch.setattr(layer, "_check_and_alert", raise_after_alert)
    results = _competing_activation(
        layer, entered, release, allow_committed_early_return=True
    )
    assert results == {1: True, 2: True}
    assert len(notifications) == 1
    assert layer._activated is True
    assert json.loads(path.read_text(encoding="utf-8"))["fingerprint"] == "z" * 64
    events = [json.loads(line) for line in layer.rebuild_log_path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["old_fingerprint"] == "a" * 64
    assert events[0]["new_fingerprint"] == "z" * 64


def test_post_rebuild_write_exception_cannot_double_record(tmp_path, monkeypatch):
    path = tmp_path / "state" / "guardian.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "operator@example.invalid",
        "smtp_config": {"server": "smtp.invalid"}
    }), encoding="utf-8")
    layer = GuardianLayer(
        config_path=str(path),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "c" * 64)
    recorded = layer._log_rebuild_event
    notifications = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kw: notifications.append(kw) or True)

    def fail_after_record(*args, **kwargs):
        recorded(*args, **kwargs)
        raise OSError("synthetic interruption after rebuild append")

    monkeypatch.setattr(layer, "_log_rebuild_event", fail_after_record)
    assert layer.activate() is True
    assert layer.activate() is True
    assert layer._activated is True
    assert len(notifications) == 1
    assert len(layer.rebuild_log_path.read_text().splitlines()) == 1


def test_noop_save_is_not_mistaken_for_successful_activation(tmp_path, monkeypatch):
    layer = GuardianLayer(
        config_path=str(tmp_path / "state" / "guardian.json"),
        rebuild_log_path=str(tmp_path / "state" / "guardian_rebuild.log"),
    )
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "n" * 64)
    monkeypatch.setattr(layer, "save", lambda: None)
    assert layer.activate() is False
    assert layer._activated is False
    assert layer.fingerprint is None
    assert not layer.config_path.exists()


def test_post_commit_cleanup_failure_cannot_rollback_persisted_identity(
    tmp_path, monkeypatch
):
    """Adversarial: replacement is durable, but temp cleanup raises afterward."""
    from pathlib import Path

    path = tmp_path / "guardian.json"
    old = "a" * 64
    new = "b" * 64
    path.write_text(json.dumps({
        "fingerprint": old,
        "contact_email": None,
        "smtp_config": {},
    }), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: new)
    original_unlink = Path.unlink
    injected = []

    def cleanup_error(target, *, missing_ok=False):
        if target.name.startswith(".guardian-") and not injected:
            # save() has already called os.replace successfully at this point.
            assert json.loads(path.read_text(encoding="utf-8"))["fingerprint"] == new
            injected.append(target.name)
            raise OSError("synthetic post-commit cleanup failure")
        return original_unlink(target, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", cleanup_error)
    result = layer.activate()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert injected, "the post-commit fault was not exercised"
    # Success and failure must not produce contradictory state: after a durable
    # commit the object must not roll back to a fingerprint no longer on disk.
    assert layer.fingerprint == persisted["fingerprint"]
    assert result is True


def test_alert_callback_can_wait_for_other_guardian_state_update(
    tmp_path, monkeypatch
):
    """Adversarial lock-order probe; bounded waits prevent stuck hosted CI."""
    from threading import Event, Thread

    path = tmp_path / "guardian.json"
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "operator@example.invalid",
        "smtp_config": {"server": "smtp.invalid"},
    }), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "b" * 64)
    worker_started, worker_finished = Event(), Event()
    finished_while_in_callback, workers = [], []

    def callback(**kwargs):
        def update_guardian():
            worker_started.set()
            layer.set_contact_email("updated@example.invalid")
            worker_finished.set()

        worker = Thread(target=update_guardian, daemon=True)
        workers.append(worker)
        worker.start()
        assert worker_started.wait(timeout=2)
        finished_while_in_callback.append(worker_finished.wait(timeout=0.4))
        return True

    monkeypatch.setattr(layer, "send_alert_email", callback)
    assert layer.activate() is True
    for worker in workers:
        worker.join(timeout=2)
    assert worker_finished.is_set(), "test worker failed to finish after callback"
    assert finished_while_in_callback == [True], (
        "alert callback held Guardian lock while awaiting a different thread "
        "which needs that same lock; a synchronous wait could deadlock"
    )


def test_cross_thread_activate_from_alert_callback_uses_durable_commit(
    tmp_path, monkeypatch
):
    """Vega #134: alert may synchronously await another thread's activate()."""
    from threading import Thread

    path = tmp_path / "guardian.json"
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "owner@example.invalid",
        "smtp_config": {"server": "smtp.invalid"},
    }), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "b" * 64)
    alerts, callbacks = [], []

    def callback(**kwargs):
        alerts.append(kwargs)
        observed = []
        worker = Thread(target=lambda: observed.append(layer.activate()), daemon=True)
        worker.start()
        worker.join(timeout=1)
        callbacks.append((worker.is_alive(), observed))
        assert not worker.is_alive(), "activate worker blocked behind alert callback"
        return True

    monkeypatch.setattr(layer, "send_alert_email", callback)
    assert layer.activate() is True
    assert callbacks == [(False, [True])]
    assert len(alerts) == 1
    assert len(layer.rebuild_log_path.read_text().splitlines()) == 1
    assert json.loads(path.read_text())["fingerprint"] == "b" * 64


def test_corrupt_existing_config_refuses_activation_and_preserves_bytes(
    tmp_path, monkeypatch
):
    """Vega #134: truncated existing JSON must not be treated as first-run."""
    path = tmp_path / "guardian.json"
    path.write_bytes(b'{"fingerprint": "truncated"')
    previous = path.read_bytes()
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    touched = []
    monkeypatch.setattr(
        layer, "_generate_system_fingerprint",
        lambda: touched.append("host fingerprint") or "c" * 64
    )
    assert layer.activate() is False
    assert layer._activated is False
    assert not touched
    assert path.read_bytes() == previous
    assert not layer.rebuild_log_path.exists()
    assert layer.verify_identity()["identity_verified"] is None
    assert layer.activate() is False
    assert path.read_bytes() == previous


def test_partial_saved_payload_with_matching_fingerprint_fails_closed(
    tmp_path, monkeypatch
):
    """Vega #134: matching fingerprint cannot hide lost SMTP/contact fields."""
    path = tmp_path / "guardian.json"
    original = {
        "fingerprint": "a" * 64,
        "contact_email": "owner@example.invalid",
        "smtp_config": {"server": "smtp.invalid", "username": "fake-user"},
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "b" * 64)
    alerts = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kw: alerts.append(kw) or True)

    def partial_write():
        path.write_text(json.dumps({"fingerprint": "b" * 64, "updated_at": "test"}),
                        encoding="utf-8")

    monkeypatch.setattr(layer, "save", partial_write)
    assert layer.activate() is False
    assert layer._activated is False
    assert layer._state_load_error is True
    assert alerts == []
    assert not layer.rebuild_log_path.exists()
    before_retry = path.read_bytes()
    assert layer.activate() is False
    assert path.read_bytes() == before_retry


def test_one_shot_post_replace_read_fault_reconciles_full_payload(
    tmp_path, monkeypatch
):
    """Vega #134: retry a read fault after durable os.replace, never roll back."""
    from pathlib import Path
    import project_guardian.guardian_layer as module

    path = tmp_path / "guardian.json"
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "owner@example.invalid",
        "smtp_config": {"server": "smtp.invalid", "port": 2525},
    }), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "b" * 64)
    alerts = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kw: alerts.append(kw) or True)
    actual_replace, actual_open = module.os.replace, Path.open
    committed, injected = [], []

    def track_replace(src, dst):
        out = actual_replace(src, dst)
        if Path(dst) == path:
            committed.append(True)
        return out

    def read_fault_once(file, *args, **kwargs):
        if Path(file) == path and committed and not injected:
            injected.append(True)
            raise OSError("synthetic read-after-commit interruption")
        return actual_open(file, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", track_replace)
    monkeypatch.setattr(Path, "open", read_fault_once)
    assert layer.activate() is True
    assert injected == [True]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert layer.fingerprint == payload["fingerprint"] == "b" * 64
    assert payload["contact_email"] == "owner@example.invalid"
    assert payload["smtp_config"] == {"server": "smtp.invalid", "port": 2525}
    assert len(alerts) == 1
    assert len(layer.rebuild_log_path.read_text().splitlines()) == 1


def test_replace_commits_then_raises_reconciles_without_duplicate_alert(
    tmp_path, monkeypatch
):
    """Even a reported write error can follow a successful atomic replacement."""
    import project_guardian.guardian_layer as module

    path = tmp_path / "guardian.json"
    path.write_text(json.dumps({
        "fingerprint": "a" * 64,
        "contact_email": "owner@example.invalid",
        "smtp_config": {"server": "smtp.invalid"},
    }), encoding="utf-8")
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: "z" * 64)
    delivered = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kw: delivered.append(kw) or True)
    real_replace = module.os.replace
    def committed_but_raised(src, dst):
        real_replace(src, dst)
        raise OSError("injected exception after replacement")

    monkeypatch.setattr(module.os, "replace", committed_but_raised)
    assert layer.activate() is True
    assert layer.activate() is True
    assert layer.fingerprint == json.loads(path.read_text())["fingerprint"] == "z" * 64
    assert len(delivered) == 1
    assert len(layer.rebuild_log_path.read_text().splitlines()) == 1


def test_corrupt_state_blocks_configuration_setters_and_direct_save(
    tmp_path
):
    """No alternate setter may overwrite a malformed durable state artifact."""
    import pytest

    path = tmp_path / "guardian.json"
    path.write_bytes(b'{"fingerprint": "truncated"')
    raw = path.read_bytes()
    layer = GuardianLayer(config_path=str(path),
                          rebuild_log_path=str(tmp_path / "events.jsonl"))
    assert layer._state_load_error is True
    with pytest.raises(RuntimeError, match="configuration invalid"):
        layer.set_contact_email("new@example.invalid")
    with pytest.raises(RuntimeError, match="configuration invalid"):
        layer.configure_smtp("smtp.invalid", smtp_port=2525)
    with pytest.raises(RuntimeError, match="configuration invalid"):
        layer.save()
    assert path.read_bytes() == raw
    assert layer.contact_email is None
    assert layer.smtp_config == {}
    assert layer._activated is False


# Stale-revision adversarial cases, registered in the mandatory Guardian suite.
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


def test_windows_setter_sequence_digests_exact_written_bytes(tmp_path, monkeypatch):
    """Vega: a successful Windows save must not poison its next stale check."""
    import hashlib

    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    layer.set_contact_email("first@example.invalid")
    first_bytes = path.read_bytes()
    assert layer._loaded_config_digest == hashlib.sha256(first_bytes).hexdigest()
    assert first_bytes.count(b"\r\n") == 0, "canonical bytes must not depend on OS"

    layer.configure_smtp("next.smtp.invalid", smtp_port=2526)
    second_bytes = path.read_bytes()
    assert layer._loaded_config_digest == hashlib.sha256(second_bytes).hexdigest()
    assert layer._state_load_error is False
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: OLD)
    assert layer.activate() is True
    assert layer.fingerprint == OLD
    assert _layer(tmp_path).contact_email == "first@example.invalid"
    assert _layer(tmp_path).smtp_config["server"] == "next.smtp.invalid"


def test_cooperative_edit_during_unchanged_fingerprint_probe_refuses_stale_success(
    tmp_path, monkeypatch
):
    """Vega: an unchanged host fingerprint is not an unchanged config revision."""
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    cooperating_writer = _layer(tmp_path)
    def probe_with_racing_writer():
        cooperating_writer.set_contact_email("external@example.invalid")
        return OLD

    monkeypatch.setattr(layer, "_generate_system_fingerprint", probe_with_racing_writer)
    assert layer.activate() is False
    assert layer._activated is False
    assert layer._state_load_error is True
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable["fingerprint"] == OLD
    assert durable["contact_email"] == "external@example.invalid"
    assert not layer.rebuild_log_path.exists()


def test_corruption_during_unchanged_fingerprint_probe_refuses_activation(
    tmp_path, monkeypatch
):
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    corrupted = b'{"partial":'
    def probe_with_corrupting_writer():
        path.write_bytes(corrupted)
        return OLD

    monkeypatch.setattr(layer, "_generate_system_fingerprint",
                        probe_with_corrupting_writer)
    assert layer.activate() is False
    assert layer._activated is False
    assert layer._state_load_error is True
    assert path.read_bytes() == corrupted
    assert not layer.rebuild_log_path.exists()


def test_invalid_commit_timestamp_is_not_accepted_as_durable_state(
    tmp_path, monkeypatch
):
    path = tmp_path / "guardian.json"
    state = _seed(path)
    state["updated_at"] = "not-a-timestamp"
    path.write_text(json.dumps(state), encoding="utf-8")
    old_bytes = path.read_bytes()
    layer = _layer(tmp_path)
    touched = []
    monkeypatch.setattr(layer, "_generate_system_fingerprint",
                        lambda: touched.append("probed") or OLD)
    assert layer._state_load_error is True
    assert layer.activate() is False
    assert touched == []
    assert path.read_bytes() == old_bytes


@pytest.mark.parametrize("setter", ["email", "smtp"])
def test_repeated_activation_rejects_cooperating_configuration_commit(
    tmp_path, monkeypatch, setter
):
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: OLD)
    assert layer.activate() is True
    writer = _layer(tmp_path)
    if setter == "email":
        writer.set_contact_email("external@example.invalid")
    else:
        writer.configure_smtp("external.smtp.invalid", smtp_port=2526)
    committed = path.read_bytes()
    assert layer.activate() is False
    assert layer._activated is False
    assert layer._state_load_error is True
    assert layer.contact_email == "owner@example.invalid"
    assert layer.smtp_config["server"] == "smtp.invalid"
    assert path.read_bytes() == committed
    layer.load()  # Recovery is explicit; stale activation did not adopt writer.
    assert layer.activate() is True
    assert layer.contact_email == writer.contact_email
    assert layer.smtp_config == writer.smtp_config
    assert path.read_bytes() == committed


@pytest.mark.parametrize("setter", ["email", "smtp"])
def test_setter_replace_then_raise_reconciles_exact_revision(
    tmp_path, monkeypatch, setter
):
    import hashlib
    import project_guardian.guardian_layer as module

    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    real_replace = module.os.replace
    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("synthetic exception immediately after replacement")

    with monkeypatch.context() as fault:
        fault.setattr(module.os, "replace", replace_then_raise)
        # A verified commit can complete despite the transport exception.
        if setter == "email":
            layer.set_contact_email("committed@example.invalid")
        else:
            layer.configure_smtp("committed.smtp.invalid", smtp_port=2526)
    raw = path.read_bytes()
    durable = json.loads(raw)
    assert layer.contact_email == durable["contact_email"]
    assert layer.smtp_config == durable["smtp_config"]
    assert layer._loaded_config_digest == hashlib.sha256(raw).hexdigest()
    assert layer._state_load_error is False
    # Next write, activation and restart all use the reconciled revision.
    layer.set_contact_email("next@example.invalid")
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: OLD)
    assert layer.activate() is True
    reopened = _layer(tmp_path)
    assert reopened.contact_email == layer.contact_email
    assert reopened.smtp_config == layer.smtp_config
    assert not layer.rebuild_log_path.exists()


@pytest.mark.parametrize("operation", ["activation", "email", "smtp"])
def test_persistent_post_commit_read_failure_requires_explicit_revalidation(
    tmp_path, monkeypatch, operation
):
    import hashlib
    from pathlib import Path
    import project_guardian.guardian_layer as module

    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: NEW)
    alerts = []
    monkeypatch.setattr(layer, "send_alert_email",
                        lambda **kw: alerts.append(kw) or True)
    real_replace, real_read = module.os.replace, Path.read_bytes
    committed = []
    def replace(src, dst):
        real_replace(src, dst)
        committed.append(real_read(path))
        if operation != "activation":
            raise OSError("replacement committed but reported failure")

    def unavailable(target):
        if target == path and committed:
            raise OSError("persistent read-back failure")
        return real_read(target)

    with monkeypatch.context() as fault:
        fault.setattr(module.os, "replace", replace)
        fault.setattr(Path, "read_bytes", unavailable)
        if operation == "activation":
            assert layer.activate() is False
        else:
            with pytest.raises(OSError):
                if operation == "email":
                    layer.set_contact_email("committed@example.invalid")
                else:
                    layer.configure_smtp("committed.smtp.invalid")
        assert layer._durable_state_unknown is True
        assert layer._state_load_error is True
        assert layer._activated is False
        assert layer.fingerprint is None
        assert layer._loaded_config_digest is None
        assert layer.get_status()["identity_verified"] is None
        assert layer.get_status()["durable_state_unknown"] is True
        assert layer.activate() is False
        with pytest.raises(RuntimeError):
            layer.set_contact_email("blocked@example.invalid")
        with pytest.raises(RuntimeError):
            layer.configure_smtp("blocked.smtp.invalid")
        with pytest.raises(RuntimeError):
            layer.save()
        assert len(committed) == 1
    # Removing the fault alone must not reopen the fence or retry a write.
    assert layer.activate() is False
    assert path.read_bytes() == committed[0]
    layer.load()
    durable = json.loads(committed[0])
    assert layer._durable_state_unknown is False
    assert layer.fingerprint == durable["fingerprint"]
    assert layer.contact_email == durable["contact_email"]
    assert layer.smtp_config == durable["smtp_config"]
    assert layer._loaded_config_digest == hashlib.sha256(committed[0]).hexdigest()
    reopened = _layer(tmp_path)
    assert reopened.fingerprint == layer.fingerprint
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: layer.fingerprint)
    assert layer.activate() is True
    assert path.read_bytes() == committed[0]
    assert not alerts
    assert not layer.rebuild_log_path.exists()


@pytest.mark.parametrize("setter", ["email", "smtp"])
def test_precommit_setter_failure_restores_verified_previous_state(
    tmp_path, monkeypatch, setter
):
    import project_guardian.guardian_layer as module
    path = tmp_path / "guardian.json"
    prior = _seed(path)
    layer = _layer(tmp_path)
    raw, digest = path.read_bytes(), layer._loaded_config_digest
    def denied(*args):
        raise OSError("replacement denied before commit")
    with monkeypatch.context() as fault:
        fault.setattr(module.os, "replace", denied)
        with pytest.raises(OSError):
            if setter == "email":
                layer.set_contact_email("uncommitted@example.invalid")
            else:
                layer.configure_smtp("uncommitted.smtp.invalid")
    assert path.read_bytes() == raw
    assert layer.contact_email == prior["contact_email"]
    assert layer.smtp_config == prior["smtp_config"]
    assert layer._loaded_config_digest == digest
    assert layer._state_load_error is False
    layer.set_contact_email("retry@example.invalid")


def test_ambiguous_setter_rejects_third_revision_even_with_intended_fields(
    tmp_path, monkeypatch
):
    import project_guardian.guardian_layer as module
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    real_replace = module.os.replace
    evidence = []
    def third_revision(src, dst):
        real_replace(src, dst)
        data = json.loads(path.read_bytes())
        # Same protected values do not identify our precise attempted commit.
        data["updated_at"] = "2000-01-01T00:00:00"
        path.write_bytes(json.dumps(data).encode("utf-8"))
        evidence.append(path.read_bytes())
        raise OSError("unrecognized revision after replacement")
    with monkeypatch.context() as fault:
        fault.setattr(module.os, "replace", third_revision)
        with pytest.raises(OSError):
            layer.set_contact_email("intended@example.invalid")
    assert layer._durable_state_unknown is True
    assert layer.fingerprint is None
    assert layer._loaded_config_digest is None
    assert layer.activate() is False
    assert path.read_bytes() == evidence[0]
    layer.load()
    assert layer._durable_state_unknown is False
    assert layer.contact_email == "intended@example.invalid"


def test_setter_interrupt_after_verified_replace_does_not_restore_stale_memory(
    tmp_path, monkeypatch
):
    import hashlib
    import project_guardian.guardian_layer as module
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    real_replace = module.os.replace
    def interrupted(src, dst):
        real_replace(src, dst)
        raise KeyboardInterrupt("synthetic interruption after commit")
    monkeypatch.setattr(module.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        layer.set_contact_email("committed@example.invalid")
    assert layer.contact_email == json.loads(path.read_bytes())["contact_email"]
    assert layer._loaded_config_digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert layer._state_load_error is False


@pytest.mark.parametrize("inspection", ["verify_identity", "get_status"])
def test_identity_inspection_cannot_bypass_durable_activation_revalidation(
    tmp_path, monkeypatch, inspection
):
    path = tmp_path / "guardian.json"
    _seed(path)
    layer = _layer(tmp_path)
    monkeypatch.setattr(layer, "_generate_system_fingerprint", lambda: OLD)
    assert layer.activate() is True
    writer = _layer(tmp_path)
    writer.set_contact_email("external@example.invalid")
    raw = path.read_bytes()
    result = getattr(layer, inspection)()
    assert result["identity_verified"] is None
    assert result["activated"] is False
    assert layer._state_load_error is True
    assert layer.contact_email == "owner@example.invalid"
    assert path.read_bytes() == raw
