"""MissionDirector.log_progress used by autonomy continue_mission."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from project_guardian.memory import MemoryCore
from project_guardian.missions import MissionDirector


def test_autonomy_json_defines_continue_mission_throttle() -> None:
    root = Path(__file__).resolve().parents[2]
    raw = (root / "config" / "autonomy.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "continue_mission_min_interval_sec" in data
    assert float(data["continue_mission_min_interval_sec"]) >= 0.0


def test_log_progress_appends_and_returns_true_for_active_mission() -> None:
    with tempfile.TemporaryDirectory() as td:
        mem = MemoryCore(filepath=str(Path(td) / "m.json"))
        md = MissionDirector(mem)
        md.create_mission("Alpha", "goal", priority="medium")
        assert md.log_progress("Alpha", "[Autonomy] tick", progress=None) is True
        m = md.get_mission_by_name("Alpha")
        assert m is not None
        assert len(m.get("log", [])) >= 1
