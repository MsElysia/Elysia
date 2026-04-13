"""One-off: distribution of infer_canonical_routing_task_type on a sample corpus (not live traffic)."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core_modules" / "elysia_core_comprehensive"))

from ai_tool_registry import TaskRouter, ToolRegistry  # noqa: E402
from project_guardian.routing_task_type import infer_canonical_routing_task_type  # noqa: E402

CORPUS = [
    "idle exploration validate tools apis low risk",
    "orchestration_routing_probe",
    "autonomy_capability_run",
    "Improve system understanding",
    "Review underused modules",
    "do something useful",
    "",
    "Summarize the quarterly report for the board",
    "Explain the error in the stack trace",
    "Write a short status update",
    "Chat with the operator about priorities",
    "Fetch https://example.com/docs",
    "Open the URL for the API spec",
    "Web search for competitors",
    "curl https://api.example.com/v1",
    "scrape the pricing page",
    "Run this command: bash ./deploy.sh",
    "Execute the script in tools/setup.py",
    "npm run build",
    "shell into the container",
    "powershell Get-ChildItem",
    "mixed: summarize https://blog.example.com/post",
    "mixed: run bash then summarize output",
]


def main() -> None:
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for g in CORPUS:
        tt, rsn = infer_canonical_routing_task_type(g)
        counts[tt] += 1
        reasons[rsn] += 1

    n = len(CORPUS)
    print("=== infer_canonical_routing_task_type (sample corpus n=%d) ===" % n)
    for k in ("fetch", "script", "completion", "self_task"):
        c = counts.get(k, 0)
        print("  %s: %d (%.0f%%)" % (k, c, 100 * c / n if n else 0))
    print("reasons:", dict(reasons))

    reg = ToolRegistry()
    reg.ensure_minimal_builtin_tools()
    tr = TaskRouter(reg)
    print()
    print("=== TaskRouter per canonical task_type (strict_capability_tag_matches = available_tools field) ===")
    for tt in ("fetch", "script", "completion", "self_task"):
        out = tr.route_task(tt, {})
        print(
            "%s -> routed_to=%s strict_capability_tag_matches=%s score=%s"
            % (tt, out.get("routed_to"), out.get("available_tools"), out.get("score"))
        )


if __name__ == "__main__":
    main()
