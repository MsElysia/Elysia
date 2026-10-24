"""First-time fingerprint updates must return while the guardian lock is held.

``_update_fingerprint`` calls ``save()`` on the first fingerprint, and ``save()``
acquires the same lock. That path deadlocks if the lock is not reentrant.
No network.
"""

import json
import sys
import threading
import types
from pathlib import Path
from unittest.mock import patch

# Import GuardianLayer without executing project_guardian/__init__.py when that
# package init cannot load (it pulls GuardianCore and provider clients).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _ensure_guardian_layer():
    if "project_guardian.guardian_layer" in sys.modules:
        return
    try:
        import project_guardian.guardian_layer  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package


_ensure_guardian_layer()

from project_guardian.guardian_layer import GuardianLayer


_RETURN_TIMEOUT_SECONDS = 2


def test_first_time_fingerprint_update_returns(tmp_path):
    """Call ``_update_fingerprint`` with no stored fingerprint and require it to return."""
    config_path = tmp_path / "guardian.json"
    rebuild_log_path = tmp_path / "guardian_rebuild.log"

    # Build a real GuardianLayer (so it owns the production lock) without
    # running the fingerprint update during construction. No config file means
    # load() leaves fingerprint unset: the next update is the first-time path.
    with patch.object(GuardianLayer, "_update_fingerprint", lambda self: None):
        layer = GuardianLayer(
            config_path=str(config_path),
            rebuild_log_path=str(rebuild_log_path),
        )

    assert layer.fingerprint is None
    assert not config_path.exists()

    result = {}
    error = {}

    def run_first_time_update():
        try:
            layer._update_fingerprint()
            result["fingerprint"] = layer.fingerprint
        except Exception as exc:
            error["exc"] = exc

    worker = threading.Thread(
        target=run_first_time_update,
        name="first-time-fingerprint",
        daemon=True,
    )
    worker.start()
    worker.join(timeout=_RETURN_TIMEOUT_SECONDS)

    assert not worker.is_alive(), (
        "_update_fingerprint did not return within "
        f"{_RETURN_TIMEOUT_SECONDS} seconds while saving a first-time fingerprint"
    )
    assert "exc" not in error, error.get("exc")

    fingerprint = result["fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["fingerprint"] == fingerprint
