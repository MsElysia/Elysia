"""GuardianLayer must not deadlock when save() is called under the fingerprint lock."""

import tempfile
from pathlib import Path

from project_guardian.guardian_layer import GuardianLayer


def test_fingerprint_update_save_under_lock_does_not_deadlock():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "guardian.json"
        log = Path(tmp) / "rebuild.log"
        layer = GuardianLayer(config_path=str(cfg), rebuild_log_path=str(log))
        assert layer.fingerprint
        assert cfg.exists()

        # Force a change so _update_fingerprint holds the lock and calls save().
        layer.fingerprint = "stale-fingerprint"
        layer.contact_email = None
        layer._update_fingerprint()
        assert layer.fingerprint != "stale-fingerprint"
        assert cfg.exists()
