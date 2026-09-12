#!/usr/bin/env python3
"""One safe ChatGPT/Cursor/Guardian cycle for Project Guardian.

This is a bounded automation harness:

1. Turn an operator prompt into a strict TASKS/*.md contract.
2. Point CONTROL.md at that task.
3. Optionally run a Cursor agent command and wait for it to exit.
4. Run GuardianCore.run_once() as the verification entrypoint.
5. Write durable JSON and Markdown cycle reports.

It deliberately does not enable autonomy, live execution, or mutation by default.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONTROL_PATH = ROOT / "CONTROL.md"
TASKS_DIR = ROOT / "TASKS"
REPORTS_DIR = ROOT / "REPORTS"
MUTATIONS_DIR = ROOT / "MUTATIONS"
AUTONOMY_CONFIG = ROOT / "config" / "autonomy.json"
CYCLE_LOG = REPORTS_DIR / "guardian_cursor_cycle_log.md"

DEFAULT_PROMPT = (
    "Run a safe plumbing smoke cycle for the ChatGPT to Cursor to Guardian "
    "handoff. Do not modify application code."
)


class CycleError(RuntimeError):
    """Raised for a controlled cycle failure."""


def utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def ensure_autonomy_disabled() -> Dict[str, Any]:
    if not AUTONOMY_CONFIG.exists():
        raise CycleError(f"missing autonomy config: {AUTONOMY_CONFIG}")
    try:
        cfg = json.loads(AUTONOMY_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CycleError(f"cannot parse {AUTONOMY_CONFIG}: {exc}") from exc
    if bool(cfg.get("enabled")):
        raise CycleError(
            "config/autonomy.json has enabled=true; refusing to run this automation harness"
        )
    return cfg


def next_task_id() -> str:
    highest = 0
    for path in TASKS_DIR.glob("TASK-*.md"):
        match = re.match(r"TASK-(\d{4,})", path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"TASK-{highest + 1:04d}"


def sanitize_prompt(prompt: str) -> str:
    prompt = (prompt or DEFAULT_PROMPT).replace("\x00", "")
    prompt = re.sub(r"\r\n?", "\n", prompt).strip()
    return prompt or DEFAULT_PROMPT


def build_task_contract(
    *,
    task_id: str,
    prompt: str,
    output_report: str,
    cursor_prompt_report: str,
) -> str:
    return f"""# {task_id} - Guardian Cursor Cycle Smoke

TASK_TYPE: READ_ONLY_ANALYSIS
ANALYSIS_KIND: FILE_SET
INPUTS:
  - type: file
    value: CONTROL.md
  - type: file
    value: TASKS/{task_id}.md
  - type: file
    value: {cursor_prompt_report}
OUTPUT_REPORT: {output_report}

## Goal

{prompt}

## Scope

- CONTROL.md
- TASKS/{task_id}.md
- {cursor_prompt_report}
- {output_report}
- REPORTS/guardian_cursor_cycle_*.json
- REPORTS/guardian_cursor_cycle_log.md

## Non-goals

- Do not enable autonomy.
- Do not enable live execution.
- Do not modify application code during this smoke cycle.
- Do not run mutation tasks.

## Acceptance

- Cursor execution is skipped or exits within the configured timeout.
- GuardianCore.run_once() returns a structured result.
- The read-only analysis report is written under REPORTS/.
- CONTROL.md is restored unless the runner is invoked with --leave-control.
"""


def build_cursor_prompt(*, task_id: str, prompt: str) -> str:
    return f"""You are the Cursor executor for Project Guardian.

Read CONTROL.md, then read TASKS/{task_id}.md.

Operator prompt:

{prompt}

Rules:
- Follow the task contract exactly.
- Do not enable autonomy.
- Do not enable live execution.
- Do not modify files outside the task scope.
- For this smoke cycle, prefer reporting over code changes.
- Write your execution notes to REPORTS/AGENT_REPORT.md if you make changes.
"""


def set_current_task(task_id: str) -> None:
    before = read_text_if_exists(CONTROL_PATH)
    lines = before.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("CURRENT_TASK:"):
            lines[i] = f"CURRENT_TASK: {task_id}"
            replaced = True
            break
    if not replaced:
        lines.insert(0, f"CURRENT_TASK: {task_id}")
    atomic_write_text(CONTROL_PATH, "\n".join(lines).rstrip() + "\n")


def cursor_status() -> Dict[str, Any]:
    cursor = shutil.which("cursor")
    if not cursor:
        return {"available": False, "path": None, "version": None}
    try:
        proc = subprocess.run(
            [cursor, "--version"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=10,
        )
        version = (proc.stdout or proc.stderr or "").strip().splitlines()
    except Exception as exc:
        version = [f"version probe failed: {exc}"]
    return {"available": True, "path": cursor, "version": version}


def split_command(command: str) -> List[str]:
    # Simple Windows-friendly split for the expected use case. Users who need
    # complex quoting can place a wrapper script in PATH and pass that command.
    return [part for part in re.split(r"\s+", command.strip()) if part]


def run_cursor_agent(
    *,
    command: Optional[str],
    prompt_text: str,
    timeout_sec: int,
    enabled: bool,
) -> Dict[str, Any]:
    if not enabled:
        return {"status": "skipped", "reason": "run_cursor_false"}
    if not command:
        return {
            "status": "skipped",
            "reason": "no_cursor_command",
            "hint": "Pass --cursor-command after confirming a non-interactive Cursor agent command.",
        }

    cmd = split_command(command)
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "command": cmd,
            "started_at": started,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "command": cmd,
            "started_at": started,
            "timeout_sec": timeout_sec,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }


def run_guardian_once() -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    import project_guardian.guardian_singleton as guardian_singleton
    from project_guardian.core import GuardianCore

    guardian_singleton.reset_singleton()
    core = None
    original_monitor = guardian_singleton.ensure_monitoring_started
    original_verify = GuardianCore._verify_startup
    original_runtime_health = GuardianCore._init_runtime_health_monitoring
    original_resource_after_deferred = GuardianCore._ensure_resource_monitor_started_after_deferred

    def _skip_monitoring(_guardian_core: Any) -> bool:
        return False

    try:
        guardian_singleton.ensure_monitoring_started = _skip_monitoring
        GuardianCore._verify_startup = lambda self: None  # type: ignore[method-assign]
        GuardianCore._init_runtime_health_monitoring = lambda self: None  # type: ignore[method-assign]
        GuardianCore._ensure_resource_monitor_started_after_deferred = lambda self: None  # type: ignore[method-assign]
        core = GuardianCore(
            config={
                "enable_vector_memory": False,
                "enable_resource_monitoring": False,
                "enable_runtime_health_monitoring": False,
                "_test_skip_external_storage": True,
            },
            control_path=CONTROL_PATH,
            tasks_dir=TASKS_DIR,
            mutations_dir=MUTATIONS_DIR,
            allow_multiple=True,
        )
        result = core.run_once()
        return result if isinstance(result, dict) else {"status": "error", "detail": repr(result)}
    finally:
        guardian_singleton.ensure_monitoring_started = original_monitor
        GuardianCore._verify_startup = original_verify  # type: ignore[method-assign]
        GuardianCore._init_runtime_health_monitoring = original_runtime_health  # type: ignore[method-assign]
        GuardianCore._ensure_resource_monitor_started_after_deferred = original_resource_after_deferred  # type: ignore[method-assign]
        if core is not None:
            try:
                core.shutdown()
            except Exception:
                pass
        guardian_singleton.reset_singleton()


def append_markdown_log(path: Path, payload: Dict[str, Any]) -> None:
    task_id = payload.get("task_id", "unknown")
    guardian = payload.get("guardian", {})
    cursor = payload.get("cursor", {})
    lines = [
        f"## {payload.get('cycle_id', utc_stamp())} - {task_id}",
        "",
        f"- Prompt: {payload.get('prompt', '')}",
        f"- Cursor: {cursor.get('status', 'unknown')}",
        f"- Guardian: {guardian.get('status', 'unknown')} / {guardian.get('outcome', guardian.get('code', ''))}",
        f"- Task file: {payload.get('task_file', '')}",
        f"- Cycle report: {payload.get('cycle_report', '')}",
        f"- Analysis report: {payload.get('analysis_report', '')}",
        "",
    ]
    old = read_text_if_exists(path)
    atomic_write_text(path, old.rstrip() + ("\n\n" if old.strip() else "") + "\n".join(lines))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=None, help="Operator prompt to feed into the cycle.")
    parser.add_argument("--prompt-file", default=None, help="Read the operator prompt from this file.")
    parser.add_argument("--task-id", default=None, help="Use an explicit TASK id, such as TASK-0051.")
    parser.add_argument(
        "--run-cursor",
        action="store_true",
        help="Run the configured Cursor command. Default is report-only/skipped.",
    )
    parser.add_argument(
        "--cursor-command",
        default=None,
        help="Non-interactive Cursor command to run. Example: cursor-agent --print",
    )
    parser.add_argument("--cursor-timeout-sec", type=int, default=900)
    parser.add_argument(
        "--leave-control",
        action="store_true",
        help="Leave CONTROL.md pointing at the generated task after the run.",
    )
    parser.add_argument(
        "--allow-autonomy-enabled",
        action="store_true",
        help="Override the safety refusal when config/autonomy.json has enabled=true.",
    )
    return parser.parse_args(argv)


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return sanitize_prompt(Path(args.prompt_file).read_text(encoding="utf-8"))
    return sanitize_prompt(args.prompt or DEFAULT_PROMPT)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    cycle_id = utc_stamp()
    prompt = load_prompt(args)
    task_id = args.task_id or next_task_id()

    if not re.fullmatch(r"TASK-[A-Za-z0-9_-]+", task_id):
        raise CycleError(f"invalid task id: {task_id}")

    TASKS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
    MUTATIONS_DIR.mkdir(exist_ok=True)

    autonomy = None
    if args.allow_autonomy_enabled:
        autonomy = json.loads(AUTONOMY_CONFIG.read_text(encoding="utf-8"))
    else:
        autonomy = ensure_autonomy_disabled()

    task_file = TASKS_DIR / f"{task_id}.md"
    analysis_report_rel = f"REPORTS/guardian_cursor_cycle_{task_id}_analysis.json"
    cursor_prompt_rel = f"REPORTS/guardian_cursor_cycle_{task_id}_cursor_prompt.md"
    cycle_report = REPORTS_DIR / f"guardian_cursor_cycle_{task_id}_{cycle_id}.json"
    cursor_prompt_path = ROOT / cursor_prompt_rel
    original_control = read_text_if_exists(CONTROL_PATH)

    task_contract = build_task_contract(
        task_id=task_id,
        prompt=prompt,
        output_report=analysis_report_rel,
        cursor_prompt_report=cursor_prompt_rel,
    )
    cursor_prompt = build_cursor_prompt(task_id=task_id, prompt=prompt)

    atomic_write_text(task_file, task_contract)
    atomic_write_text(cursor_prompt_path, cursor_prompt)
    set_current_task(task_id)

    cursor_result: Dict[str, Any] = {}
    guardian_result: Dict[str, Any] = {}
    control_restored = False
    try:
        cursor_result = run_cursor_agent(
            command=args.cursor_command,
            prompt_text=cursor_prompt,
            timeout_sec=max(1, int(args.cursor_timeout_sec)),
            enabled=bool(args.run_cursor),
        )
        guardian_result = run_guardian_once()
    finally:
        if not args.leave_control:
            atomic_write_text(CONTROL_PATH, original_control or "CURRENT_TASK: NONE\n")
            control_restored = True

    payload: Dict[str, Any] = {
        "cycle_id": cycle_id,
        "task_id": task_id,
        "prompt": prompt,
        "task_file": str(task_file.relative_to(ROOT)),
        "cursor_prompt": cursor_prompt_rel,
        "analysis_report": analysis_report_rel,
        "cycle_report": str(cycle_report.relative_to(ROOT)),
        "autonomy_enabled": bool(autonomy.get("enabled")),
        "control_restored": control_restored,
        "cursor_probe": cursor_status(),
        "cursor": cursor_result,
        "guardian": guardian_result,
    }
    atomic_write_json(cycle_report, payload)
    append_markdown_log(CYCLE_LOG, payload)

    print(json.dumps(payload, indent=2, sort_keys=True))
    if guardian_result.get("status") != "ok":
        return 3
    if cursor_result.get("status") in {"failed", "timeout"}:
        return 4
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CycleError as exc:
        print(f"guardian_cursor_cycle: {exc}", file=sys.stderr)
        raise SystemExit(2)
