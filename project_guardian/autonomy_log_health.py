# project_guardian/autonomy_log_health.py
"""Compact health analysis for Project Guardian autonomy logs."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRACE_WINNER_RE = re.compile(r"\[AutonomyDecisionTrace\].*?\bwinner=([^\s]+)")
SELECTED_RE = re.compile(r"\[MissionDirector\]\s+selected action=([^\s]+)")
FINISHED_SELF_TASK_RE = re.compile(
    r"\[SelfTask\]\s+finished\s+\S+.*?\buseful=(True|False).*?\badv=(True|False).*?\barch=([^\s]+)"
)


def _winner_action(raw: str) -> str:
    label = (raw or "").strip()
    if not label:
        return ""
    head = label.split("@", 1)[0]
    if head.startswith("execute_self_task:"):
        return head
    if head.startswith("uc:"):
        return "use_capability/" + head[3:]
    return head


def _top(counter: Counter[str], n: int = 6) -> List[Dict[str, Any]]:
    return [{"name": k, "count": v} for k, v in counter.most_common(n)]


def analyze_autonomy_log_lines(lines: Iterable[str]) -> Dict[str, Any]:
    total = 0
    decision_traces = 0
    winners: Counter[str] = Counter()
    selected: Counter[str] = Counter()
    useful_nonadv_arches: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    for raw_line in lines:
        total += 1
        line = str(raw_line or "")
        if "elysia_builtin_web requires an http(s) URL" in line:
            counts["url_less_web_error"] += 1
        if "web_missing_url" in line or "guard=0.04" in line:
            counts["web_missing_url_guard"] += 1
        if (
            "zero_total_zero_sales" in line
            or "Income report generated: $0.00 from 0 sales" in line
            or "harvest_income_report: total=$0.0 sales=0" in line
            or "'total_earned': 0.0" in line
            and "'total_sales': 0" in line
        ):
            counts["zero_harvest"] += 1
        if "useful_nonadv_streak" in line:
            counts["useful_nonadv_suppression"] += 1
        if "memory_pressure_high" in line or "Resource limit exceeded: memory" in line or "[Memory Alert]" in line:
            counts["memory_pressure"] += 1
        if "[AutonomyPickOverride]" in line:
            counts["pick_override"] += 1
        if "post_override=" in line:
            counts["post_override_trace"] += 1
        if "skipped_top=" in line:
            counts["skipped_top_trace"] += 1

        m = TRACE_WINNER_RE.search(line)
        if m:
            decision_traces += 1
            action = _winner_action(m.group(1))
            if action:
                winners[action] += 1

        m = SELECTED_RE.search(line)
        if m:
            selected[m.group(1)] += 1

        m = FINISHED_SELF_TASK_RE.search(line)
        if m:
            useful = m.group(1) == "True"
            advanced = m.group(2) == "True"
            arch = m.group(3)
            if useful and not advanced:
                useful_nonadv_arches[arch] += 1

    action_counts = winners if winners else selected
    dominant_action = ""
    dominant_count = 0
    dominant_ratio = 0.0
    if action_counts:
        dominant_action, dominant_count = action_counts.most_common(1)[0]
        dominant_ratio = dominant_count / max(1, sum(action_counts.values()))

    issues: List[str] = []
    recommendations: List[str] = []
    status = "healthy"

    if counts["url_less_web_error"] > 0:
        status = "attention"
        issues.append(f"url_less_web_error={counts['url_less_web_error']}")
        recommendations.append("Direct web capability is still executing without an http(s) URL; inspect web_missing_url guards and executable filtering.")
    elif counts["web_missing_url_guard"] > 0:
        status = "warn"
        issues.append(f"web_missing_url_guard={counts['web_missing_url_guard']}")
        recommendations.append("URL-less web candidates are being caught before execution; confirm they do not become selected actions.")

    if counts["zero_harvest"] >= 3:
        status = "attention"
        issues.append(f"zero_harvest={counts['zero_harvest']}")
        recommendations.append("Harvest zero-yield work is still recurring; check equivalent suppression for harvest_engine capability actions.")
    elif counts["zero_harvest"] > 0 and status == "healthy":
        status = "warn"
        issues.append(f"zero_harvest={counts['zero_harvest']}")

    if counts["useful_nonadv_suppression"] > 0:
        if status == "healthy":
            status = "warn"
        issues.append(f"useful_nonadv_suppression={counts['useful_nonadv_suppression']}")
        recommendations.append("Self-task suppression is firing; inspect decision traces for whether suppressed archetypes still win.")

    if counts["memory_pressure"] > 0:
        if status == "healthy":
            status = "warn"
        issues.append(f"memory_pressure={counts['memory_pressure']}")
        recommendations.append("Memory pressure appeared in the window; keep an eye on PromptPacket skips and cleanup outcomes.")

    if dominant_ratio >= 0.75 and dominant_count >= 6:
        status = "attention" if status != "attention" else status
        issues.append(f"dominant_action={dominant_action}:{dominant_count}/{sum(action_counts.values())}")
        recommendations.append("One action dominates the window; check whether its score remains high after penalties and mission drift.")

    if total > 0 and decision_traces == 0:
        if status == "healthy":
            status = "warn"
        issues.append("decision_traces=0")
        recommendations.append("Restart with the decision-trace patch loaded or set ELYSIA_AUTONOMY_DECISION_TRACE=1.")

    return {
        "status": status,
        "total_lines": total,
        "decision_traces": decision_traces,
        "counts": dict(counts),
        "top_winners": _top(winners),
        "top_selected_actions": _top(selected),
        "useful_nonadv_archetypes": _top(useful_nonadv_arches),
        "dominant_action": {
            "name": dominant_action,
            "count": dominant_count,
            "ratio": round(dominant_ratio, 4),
        },
        "issues": issues,
        "recommendations": recommendations,
    }


def analyze_autonomy_log_text(text: str) -> Dict[str, Any]:
    return analyze_autonomy_log_lines(str(text or "").splitlines())


def format_autonomy_health_report(report: Dict[str, Any]) -> str:
    lines = [
        f"Autonomy loop health: {report.get('status', 'unknown')}",
        f"lines={report.get('total_lines', 0)} decision_traces={report.get('decision_traces', 0)}",
    ]
    dom = report.get("dominant_action") if isinstance(report.get("dominant_action"), dict) else {}
    if dom.get("name"):
        lines.append(f"dominant={dom.get('name')} count={dom.get('count')} ratio={dom.get('ratio')}")
    for label, key in (
        ("top_winners", "top_winners"),
        ("top_selected", "top_selected_actions"),
        ("useful_nonadv", "useful_nonadv_archetypes"),
    ):
        rows = report.get(key) or []
        if rows:
            lines.append(label + "=" + ", ".join(f"{r['name']}:{r['count']}" for r in rows[:6]))
    issues = report.get("issues") or []
    if issues:
        lines.append("issues=" + "; ".join(str(x) for x in issues))
    recs = report.get("recommendations") or []
    if recs:
        lines.append("recommendations:")
        lines.extend(f"- {r}" for r in recs[:6])
    return "\n".join(lines)


def _read_tail(path: Path, lines: int, *, chunk_size: int = 8192) -> str:
    if lines <= 0:
        return path.read_text(encoding="utf-8", errors="replace")
    with path.open("rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        chunks: List[bytes] = []
        newline_count = 0
        while pos > 0 and newline_count <= lines:
            take = min(chunk_size, pos)
            pos -= take
            f.seek(pos)
            data = f.read(take)
            chunks.append(data)
            newline_count += data.count(b"\n")
    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def _read_paths(paths: List[str], *, tail_lines: int = 0) -> str:
    chunks: List[str] = []
    for p in paths:
        path = Path(p)
        if tail_lines > 0:
            chunks.append(_read_tail(path, tail_lines))
        else:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize autonomy loop health from Guardian logs.")
    ap.add_argument("paths", nargs="*", help="Log file paths. Reads stdin when omitted.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    ap.add_argument("--tail", type=int, default=0, help="Read only the last N lines from each file path.")
    ns = ap.parse_args(argv)
    text = _read_paths(ns.paths, tail_lines=max(0, int(ns.tail or 0))) if ns.paths else sys.stdin.read()
    report = analyze_autonomy_log_text(text)
    if ns.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_autonomy_health_report(report))
    return 0 if report.get("status") in ("healthy", "warn") else 2


if __name__ == "__main__":
    raise SystemExit(main())
