"""Load the dashboard module without importing GuardianCore.

``import project_guardian`` constructs the launcher stack and currently fails
on a missing optional dependency before the control panel can be tested.
"""

import importlib.util
import sys
from pathlib import Path

_PANEL_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "ui_control_panel.py"
_SPEC = importlib.util.spec_from_file_location("elysia_dashboard_panel_under_test", _PANEL_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load dashboard panel from {_PANEL_PATH}")

panel_module = sys.modules.get(_SPEC.name)
if panel_module is None:
    panel_module = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = panel_module
    _SPEC.loader.exec_module(panel_module)

UIControlPanel = panel_module.UIControlPanel
reset_dashboard_guard = panel_module.reset_dashboard_guard
