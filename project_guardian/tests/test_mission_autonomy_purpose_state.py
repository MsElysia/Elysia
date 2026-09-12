from __future__ import annotations

import json


def test_mission_purpose_state_snapshot_updates(tmp_path, monkeypatch):
    import project_guardian.mission_autonomy as ma

    cfg = tmp_path / "mission_autonomy.json"
    state = tmp_path / "mission_autonomy_state.json"
    cfg.write_text(
        json.dumps(
            {
                "enabled": True,
                "core_mission": "Advance useful autonomy with measurable outcomes.",
                "campaigns": [
                    {
                        "id": "cmp_execution",
                        "title": "Execution and artifacts",
                        "status": "active",
                        "current_priority": 1.0,
                        "next_recommended_actions": ["execute_self_task", "work_on_objective"],
                    }
                ],
                "standing_priorities": [{"title": "Safety & trust maintenance"}],
                "action_campaign_map": {"execute_self_task": ["cmp_execution"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ma, "CONFIG_PATH", cfg)
    monkeypatch.setattr(ma, "STATE_PATH", state)

    store = ma.MissionAutonomyStore()
    out = store.apply_governance(
        [{"action": "execute_self_task", "reason": "build operator artifact", "priority_score": 1.0}],
        recent_actions=["process_queue", "execute_task"],
    )
    assert out
    snap = ma.mission_purpose_state_snapshot()
    assert isinstance(snap, dict) and snap
    assert snap.get("horizon") == "session"
    assert float(snap.get("confidence", 0)) > 0
    sig = snap.get("signals") or {}
    assert sig.get("primary_campaign_id") == "cmp_execution"
    assert "execute_self_task" in list(sig.get("recommended_actions") or [])
