"""Startup log hints for removable USB volumes (external_storage.log_startup_external_volume_hints)."""
from __future__ import annotations

import logging


def test_log_hints_respects_skip_env(monkeypatch, caplog):
    import project_guardian.external_storage as es

    monkeypatch.setenv("ELYSIA_SKIP_EXTERNAL_VOLUME_HINTS", "1")
    monkeypatch.setattr(es, "detect_removable_drives", lambda: [{"is_removable": True}])
    with caplog.at_level(logging.INFO):
        es.log_startup_external_volume_hints()
    assert "ExternalVolumes" not in caplog.text


def test_log_hints_when_mirror_active(tmp_path, monkeypatch, caplog):
    import project_guardian.external_storage as es

    monkeypatch.delenv("ELYSIA_SKIP_EXTERNAL_VOLUME_HINTS", raising=False)
    monkeypatch.setattr(es, "get_configured_external_data_dir", lambda: tmp_path)
    with caplog.at_level(logging.INFO):
        snap = es.log_startup_external_volume_hints()
    assert snap.get("hint_level") == "mirror_active"
    assert "External data mirror active" in caplog.text
    assert any(str(tmp_path) in rec.message for rec in caplog.records)


def test_log_hints_lists_removable_when_no_mirror(monkeypatch, caplog):
    import project_guardian.external_storage as es

    monkeypatch.delenv("ELYSIA_SKIP_EXTERNAL_VOLUME_HINTS", raising=False)
    monkeypatch.setattr(es, "get_configured_external_data_dir", lambda: None)
    monkeypatch.setattr(
        es,
        "detect_removable_drives",
        lambda: [{"mountpoint": "E:\\", "free_gb": 12.0, "is_removable": True}],
    )
    with caplog.at_level(logging.INFO):
        snap = es.log_startup_external_volume_hints()
    assert snap.get("hint_level") == "removable_present"
    assert snap.get("removable_count") == 1
    assert "Removable volumes" in caplog.text
    assert "E:" in caplog.text


def test_build_snapshot_mirror_active(monkeypatch, tmp_path):
    import project_guardian.external_storage as es

    monkeypatch.setattr(es, "get_configured_external_data_dir", lambda: tmp_path)
    snap = es.build_external_volume_snapshot()
    assert snap["hint_level"] == "mirror_active"
    assert snap["external_data_mirror_active"] is True
