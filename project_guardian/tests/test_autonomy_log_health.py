from __future__ import annotations

import json

from project_guardian.autonomy_log_health import (
    analyze_autonomy_log_text,
    format_autonomy_health_report,
    main,
)


def test_autonomy_log_health_flags_original_loop_patterns() -> None:
    text = "\n".join(
        [
            "[AutonomyDecisionTrace] cycle=7 winner=execute_self_task:generate_revenue_shortlist@6.420 runner=fractalmind_planning@1.200 candidates=4 source=self_tasking top=execute_self_task:generate_revenue_shortlist@6.420|fractalmind_planning@1.200",
            "[AutonomyDecisionTrace] cycle=8 winner=execute_self_task:generate_revenue_shortlist@6.410 runner=harvest_income_report@0.500 candidates=4 source=self_tasking top=execute_self_task:generate_revenue_shortlist@6.410|harvest_income_report@0.500",
            "project_guardian.self_task_queue - WARNING - [SelfTask] Archetype suppression 900s arch=summarize_monetizable_directions_from_learning useful_nonadv_streak=719",
            "[SelfTask] finished st_1 tier=strong success=True useful=True adv=False op_ready=False arch=generate_revenue_shortlist",
            "[SelfTask] finished st_2 tier=strong success=True useful=True adv=False op_ready=False arch=generate_revenue_shortlist",
            "[SelfTask] finished st_3 tier=strong success=True useful=True adv=False op_ready=False arch=generate_revenue_shortlist",
            "[Autonomy] use_capability tool/elysia_builtin_web: elysia_builtin_web requires an http(s) URL in url/query/task/prompt",
            "Income report generated: $0.00 from 0 sales",
            "[Autonomy] harvest_income_report: total=$0.0 sales=0",
            "[AutonomyNoop] Suppressing action=harvest_income_report for 900s after 1x no-op in window (zero_total_zero_sales)",
            "[Memory Alert] System memory at 81.9% - Automatic cleanup should trigger on next heartbeat",
        ]
    )
    report = analyze_autonomy_log_text(text)
    assert report["status"] == "attention"
    assert report["counts"]["url_less_web_error"] == 1
    assert report["counts"]["zero_harvest"] == 3
    assert report["counts"]["useful_nonadv_suppression"] == 1
    assert report["counts"]["memory_pressure"] == 1
    assert report["useful_nonadv_archetypes"][0]["name"] == "generate_revenue_shortlist"


def test_autonomy_log_health_healthy_trace_window() -> None:
    text = "\n".join(
        [
            "[AutonomyDecisionTrace] cycle=1 winner=execute_self_task:package_operator_offer_pack@4.200 runner=question_probe@3.000 candidates=5 source=self_tasking",
            "[AutonomyDecisionTrace] cycle=2 winner=question_probe@3.100 runner=tool_registry_pulse@2.000 candidates=5 source=system",
            "[AutonomyDecisionTrace] cycle=3 winner=tool_registry_pulse@2.300 runner=execute_self_task:package_operator_offer_pack@2.000 candidates=5 source=system",
            "[MissionDirector] selected action=execute_self_task campaign=cmp_execution because=Package operator offer page",
        ]
    )
    report = analyze_autonomy_log_text(text)
    assert report["status"] == "healthy"
    assert report["decision_traces"] == 3
    rendered = format_autonomy_health_report(report)
    assert "Autonomy loop health: healthy" in rendered
    assert "top_winners=" in rendered


def test_autonomy_log_health_cli_json_stdin(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin.read", lambda: "[AutonomyDecisionTrace] cycle=1 winner=question_probe@3.0\n")
    rc = main(["--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "healthy"
    assert payload["top_winners"][0]["name"] == "question_probe"


def test_autonomy_log_health_cli_tail_reads_last_lines(tmp_path, capsys) -> None:
    log = tmp_path / "guardian.log"
    log.write_text(
        "\n".join(
            [
                "elysia_builtin_web requires an http(s) URL in url/query/task/prompt",
                "[AutonomyDecisionTrace] cycle=1 winner=question_probe@3.0",
                "[AutonomyDecisionTrace] cycle=2 winner=tool_registry_pulse@2.0",
            ]
        ),
        encoding="utf-8",
    )
    rc = main([str(log), "--tail", "2", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"].get("url_less_web_error", 0) == 0
    assert payload["decision_traces"] == 2
