from __future__ import annotations

import sys
from pathlib import Path


def test_launcher_package_path_appends_instead_of_prepending(tmp_path, monkeypatch):
    import elysia_sub_income as esi

    launcher = tmp_path / "organized_project" / "launcher"
    launcher.mkdir(parents=True)
    parent = str(launcher.parent)
    monkeypatch.setattr(sys, "path", ["stdlib", "project"])

    esi._ensure_launcher_package_path(Path(launcher))

    assert sys.path[:2] == ["stdlib", "project"]
    assert sys.path[-1] == parent


def test_launcher_package_path_is_idempotent(tmp_path, monkeypatch):
    import elysia_sub_income as esi

    launcher = tmp_path / "organized_project" / "launcher"
    launcher.mkdir(parents=True)
    parent = str(launcher.parent)
    monkeypatch.setattr(sys, "path", ["stdlib", parent])

    esi._ensure_launcher_package_path(Path(launcher))

    assert sys.path == ["stdlib", parent]
