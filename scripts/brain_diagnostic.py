#!/usr/bin/env python3
"""Print brain wiring, last pipeline trace, static LLM config, and brain_pipeline flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _print_brain_pipeline_flags() -> None:
    cfg_json = ROOT / "config" / "brain_pipeline.json"
    print("Brain pipeline config (file + resolved defaults):")
    print("  config file:", cfg_json, "exists:", cfg_json.is_file())
    if cfg_json.is_file():
        try:
            raw = json.loads(cfg_json.read_text(encoding="utf-8"))
            inner = raw.get("brain_pipeline")
            if isinstance(inner, dict):
                print("  file brain_pipeline.enabled:", inner.get("enabled"))
                print("  file use_think_decide_act:", inner.get("use_think_decide_act"))
                print("  file dry_run:", inner.get("dry_run"))
                ep = inner.get("entrypoints")
                if isinstance(ep, dict):
                    print("  file entrypoints:")
                    for k in sorted(ep.keys()):
                        print(f"    {k}: {ep.get(k)}")
                print("  file trace_path:", inner.get("trace_path"))
                print("  file persist_trace:", inner.get("persist_trace"))
            else:
                print("  (file missing top-level 'brain_pipeline' object)")
        except Exception as e:
            print("  (could not parse config file:", e, ")")

    try:
        from project_guardian.brain.config import clear_brain_pipeline_config_cache, get_brain_pipeline_config

        clear_brain_pipeline_config_cache()
        cfg = get_brain_pipeline_config()
        print("  resolved enabled:", cfg.enabled)
        print("  resolved use_think_decide_act:", cfg.use_think_decide_act)
        print("  resolved dry_run:", cfg.dry_run)
        print("  resolved persist_trace:", cfg.persist_trace)
        print("  resolved trace_path:", cfg.trace_path)
        print("  resolved entrypoints:")
        for k in sorted(cfg.entrypoints.keys()):
            print(f"    {k}: {cfg.entrypoints[k]}")
        live = [k for k, v in cfg.entrypoints.items() if v]
        print("  live entrypoints (true):", ", ".join(live) if live else "(none)")
    except Exception as e:
        print("  (could not resolve brain_pipeline config:", e, ")")

    try:
        from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event  # noqa: F401

        print("  production wrapper (run_brain_pipeline_for_operator_event): import ok")
    except Exception as e:
        print("  production wrapper: import failed:", e)

    print("  operator_chat API hook: elysia/api/server.py RuntimeAPIServer._maybe_run_brain_operator_chat_trace")
    try:
        import inspect

        from elysia.api.server import RuntimeAPIServer

        src = inspect.getsource(RuntimeAPIServer._maybe_run_brain_operator_chat_trace)
        print("  RuntimeAPIServer._maybe_run_brain_operator_chat_trace present:", "run_brain_pipeline_for_operator_event" in src)
    except Exception as e:
        print("  RuntimeAPIServer hook inspect failed:", e)

    print(
        "  note: POST /api/chat runs a trace when brain_pipeline.enabled and entrypoints.operator_chat are true "
        "(the HTTP operator chat hook is dry-run only). "
        "scripts/brain_diagnostic.py --invoke-pipeline uses entrypoints.diagnostic only."
    )
    print()


def _print_sanitized_trace_summary() -> None:
    print("Sanitized latest trace (GET /api/brain/trace/latest):")
    try:
        from project_guardian.brain.config import clear_brain_pipeline_config_cache
        from project_guardian.brain.trace_visibility import load_latest_brain_trace_summary

        clear_brain_pipeline_config_cache()
        summary = load_latest_brain_trace_summary()
        text = json.dumps(summary, indent=2, default=str)
        print(text[:8000] + ("..." if len(text) > 8000 else ""))
    except Exception as e:
        print("  (could not build summary:", e, ")")
    print()


def _maybe_invoke_pipeline(message: str) -> int:
    from project_guardian.brain.config import clear_brain_pipeline_config_cache, get_brain_pipeline_config
    from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event

    clear_brain_pipeline_config_cache()
    cfg = get_brain_pipeline_config()
    if not cfg.enabled:
        print("Invoke skipped: brain_pipeline.enabled is false (set true in config/brain_pipeline.json).")
        return 0
    if not cfg.entrypoint_enabled("diagnostic"):
        print(
            "Invoke skipped: entrypoints.diagnostic is false "
            "(set true to allow this diagnostic-only hook)."
        )
        return 0
    print("Running BrainPipeline via run_brain_pipeline_for_operator_event (diagnostic entrypoint)...")
    res = run_brain_pipeline_for_operator_event(message, source_entrypoint="diagnostic", config=cfg)
    if isinstance(res, dict) and res.get("bypass"):
        print("  unexpected bypass:", res)
        return 1
    trace, dash = res
    print("  brain_pipeline_id:", getattr(trace, "brain_pipeline_id", None))
    print("  transitions (last few):", (trace.transitions or [])[-8:])
    print("  dashboard keys:", list((dash or {}).keys())[:12])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elysia brain diagnostic (read-only except --invoke-pipeline).")
    parser.add_argument(
        "--invoke-pipeline",
        action="store_true",
        help="Run BrainPipeline once via the diagnostic entrypoint (requires enabled + entrypoints.diagnostic).",
    )
    parser.add_argument(
        "--message",
        default="diagnostic ping",
        help="Observation text for --invoke-pipeline.",
    )
    args = parser.parse_args(argv)

    root_str = str(ROOT.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    print("=== Elysia brain diagnostic ===\n")

    brain_dir = ROOT / "project_guardian" / "brain"
    print("Available brain modules (package files):")
    if brain_dir.is_dir():
        for p in sorted(brain_dir.glob("*.py")):
            if p.name != "__init__.py":
                print(f"  - project_guardian.brain.{p.stem}")
    else:
        print("  (brain directory not found)")
    print()

    tda_path = ROOT / "project_guardian" / "orchestration" / "think_decide_act.py"
    adapter_path = ROOT / "project_guardian" / "brain" / "think_decide_act_adapter.py"
    print("Think-Decide-Act + brain adapter:")
    print("  think_decide_act.py:", "yes" if tda_path.is_file() else "no", f"({tda_path})")
    print("  think_decide_act_adapter.py:", "yes" if adapter_path.is_file() else "no", f"({adapter_path})")
    print()

    _print_brain_pipeline_flags()
    _print_sanitized_trace_summary()

    trace_path = ROOT / "data" / "runtime" / "brain_last_pipeline.json"
    print("Current routing path: see sanitized latest trace summary above.")
    if False and trace_path.exists():
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        for t in data.get("transitions") or []:
            print(f"  {t}")
        print("  (full trace file:", str(trace_path), ")")
        print("  last run Think-Decide-Act via brain:")
        print("    use_think_decide_act:", data.get("use_think_decide_act"))
        print("    dry_run:", data.get("dry_run"))
        print("    think_decide_act_trace_present:", data.get("think_decide_act_trace_present"))
        ue = data.get("unified_export") or {}
        print("    brain_pipeline_id:", ue.get("brain_pipeline_id") or data.get("brain_pipeline_id"))
        print("  (Think-Decide-Act full trace is embedded in unified_export when used; no separate TDA file.)")
    elif trace_path.exists():
        print("  raw transition list suppressed to avoid exposing trace contents")
        print("  expected path:", trace_path)
    else:
        print("  (no trace yet — run BrainPipeline once)")
        print("  raw transition list suppressed to avoid exposing trace contents")
        print("  expected path:", trace_path)
    print()

    llm_yaml = ROOT / "config" / "llm_router.yaml"
    print("Configured LLM router YAML (route keys / defaults):")
    if llm_yaml.exists():
        try:
            import yaml  # type: ignore

            cfg = yaml.safe_load(llm_yaml.read_text(encoding="utf-8")) or {}
            print("  defaults:", json.dumps(cfg.get("defaults"), indent=2)[:800])
            routes = cfg.get("routes") or {}
            print("  route kinds:", ", ".join(sorted(routes.keys())))
        except Exception as e:
            print("  (could not parse yaml:", e, ")")
    else:
        print("  (missing", llm_yaml, ")")
    print()

    print("Configured LLM / routing (static config files, no live provider probe):")
    decider = ROOT / "config" / "mistral_decider.json"
    if decider.exists():
        try:
            d = json.loads(decider.read_text(encoding="utf-8"))
            keys = sorted(k for k in d.keys() if not k.startswith("_"))[:40]
            print("  mistral_decider keys:", ", ".join(keys))
        except Exception as e:
            print("  (could not read mistral_decider:", e, ")")
    else:
        print("  (missing", decider, ")")
    print("  (for live backend resolution use BrainPipeline or unified_llm_route in-process)")
    print()

    print("Memory status: see sanitized latest trace summary above; no MemoryCore load.")
    if False and trace_path.exists():
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        snips = data.get("memory_snippets") or []
        print(f"  last_trace_memory_snippet_count={len(snips)}")
        for s in snips[:3]:
            print("   -", str(s)[:120])
        if not snips:
            print("  (none in last trace)")
    else:
        print("  raw memory snippets suppressed to avoid exposing trace contents")
    print()

    print("Last action result: see sanitized latest trace summary above.")
    if False and trace_path.exists():
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        print("  execution_ok:", data.get("execution_ok"))
        print("  execution_error:", data.get("execution_error"))
        print("  risk:", data.get("risk"), data.get("risk_reason"))
        print("  tool_selected:", data.get("tool_selected"), "fallback:", data.get("tool_fallback"))
    else:
        print("  raw action detail suppressed to avoid exposing trace contents")
    print()

    if args.invoke_pipeline:
        return _maybe_invoke_pipeline(args.message.strip() or "diagnostic ping")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
