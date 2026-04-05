# project_guardian/self_task_artifacts.py
# Persist strong self-task outputs for operator visibility.

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONTRACT_TO_SUBDIR = {
    "revenue_shortlist": ("data", "revenue_briefs"),
    "research_brief": ("data", "research_briefs"),
    "system_improvement_proposal": ("data", "generated_reports"),
    "learned_digest": ("data", "generated_reports"),
    "capability_gap_report": ("data", "generated_reports"),
}


def _safe_name(s: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", (s or "task")[:80])[:80]


def save_self_task_artifact(
    *,
    task_id: str,
    archetype: str,
    contract_id: str,
    payload: Any,
    execution_tier: str,
) -> Optional[Path]:
    """Write JSON artifact for operator review. Returns path or None."""
    if execution_tier != "strong":
        return None
    sub = CONTRACT_TO_SUBDIR.get(contract_id)
    if not sub:
        return None
    dir_path = PROJECT_ROOT.joinpath(*sub)
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        fn = f"{_safe_name(task_id)}_{_safe_name(archetype)}.json"
        path = dir_path / fn
        blob = {
            "task_id": task_id,
            "archetype": archetype,
            "contract_id": contract_id,
            "execution_tier": execution_tier,
            "payload": payload,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(blob, f, indent=2, ensure_ascii=False)
        logger.info("[SelfTask] artifact saved %s", path)
        return path
    except Exception as e:
        logger.debug("artifact save failed: %s", e)
        return None
