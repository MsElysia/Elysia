"""Regression: install manifest covers dependencies required by startup validation."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_startup_dependencies_are_installable():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    packages = {
        re.split(r"[<>=!~;\s]", line.strip(), maxsplit=1)[0].lower()
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {"flask", "flask-socketio"} <= packages
    assert "asyncio" not in packages
