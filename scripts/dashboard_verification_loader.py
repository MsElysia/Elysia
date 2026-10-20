"""Load the real dashboard without executing GuardianCore package startup."""

import importlib
from pathlib import Path
import sys
from types import ModuleType


def load_dashboard():
    root = Path(__file__).resolve().parents[1]
    if "project_guardian" not in sys.modules:
        package = ModuleType("project_guardian")
        package.__path__ = [str(root / "project_guardian")]
        sys.modules["project_guardian"] = package
    return importlib.import_module("project_guardian.ui_control_panel")
