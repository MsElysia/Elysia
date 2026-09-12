#!/usr/bin/env python3
"""Quick prompt-contract registry + integration sanity check (no LLM calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "project_guardian").is_dir():
            return parent
    return here.parents[1]


_REPO_ROOT = _repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    try:
        from project_guardian.prompt_contracts import integration, list_prompt_contracts
        from project_guardian.prompt_contracts import validate_module_llm_response
    except ImportError as exc:
        print("prompt_contracts import failed:", exc)
        return 1

    contracts = list_prompt_contracts()
    print(f"contracts_loaded={len(contracts)}")
    print(f"integration_module={integration.__file__}")

    sample = json.dumps(
        {
            "goal": "demo",
            "steps": [{"description": "step"}],
            "constraints": [],
            "risk_level": "low",
            "reason_summary": "demo",
            "confidence": 0.5,
        }
    )
    ok, errs = validate_module_llm_response("planner", sample)
    print(f"sample_planner_validate_ok={ok} errors={errs}")

    res = integration.validate_module_output_for_trace(
        "planner",
        json.loads(sample),
        {"validate_prompt_contracts": True, "prompt_contract_mode": "warn", "dry_run": True},
    )
    print("sample_validate_module_output_for_trace=", json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
