"""Load the UI control panel module without initializing GuardianCore.

The repository's package __init__ eagerly imports the entire runtime. Its main
branch lacks module_activity.py (present in newer draft branches). This helper
permits bounded UI/dashboard unit tests without misrepresenting whole-runtime
readiness. Do not use it as a production startup path.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import test module: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ui_panel_module = _load(
    "_elysia_ui_panel_test", _REPO_ROOT / "project_guardian" / "ui_control_panel.py"
)

UIControlPanel = ui_panel_module.UIControlPanel
reset_dashboard_guard = ui_panel_module.reset_dashboard_guard
