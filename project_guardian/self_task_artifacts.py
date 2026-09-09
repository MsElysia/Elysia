# project_guardian/self_task_artifacts.py
# Persist strong self-task outputs for operator visibility.

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONTRACT_TO_SUBDIR = {
    "revenue_shortlist": ("data", "revenue_briefs"),
    "research_brief": ("data", "research_briefs"),
    "system_improvement_proposal": ("data", "generated_reports"),
    "learned_digest": ("data", "generated_reports"),
    "capability_gap_report": ("data", "generated_reports"),
    "offer_pack": ("data", "generated_reports"),
}

# Cap JSON files under data/generated_reports (strong self-task artifacts) to avoid unbounded growth.
_GENERATED_REPORTS_MAX_FILES = 120


def _prune_generated_reports_dir(root: Path, *, max_files: int) -> None:
    """Keep the newest max_files JSON artifacts; delete older files in generated_reports only."""
    if max_files < 4:
        max_files = 4
    d = root.joinpath("data", "generated_reports")
    if not d.is_dir():
        return
    try:
        files = [p for p in d.glob("*.json") if p.is_file()]
    except OSError:
        return
    if len(files) <= max_files:
        return
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[max_files:]:
        try:
            stale.unlink()
            logger.info("[SelfTask] pruned old generated_report %s", stale.name)
        except OSError as e:
            logger.debug("[SelfTask] prune skip %s: %s", stale, e)


def _safe_name(s: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", (s or "task")[:80])[:80]


def _artifact_target_paths(contract_id: str, task_id: str, archetype: str) -> List[Path]:
    sub = CONTRACT_TO_SUBDIR.get(contract_id)
    if not sub:
        return []

    filename = f"{_safe_name(task_id)}_{_safe_name(archetype)}.json"
    targets: List[Path] = [PROJECT_ROOT.joinpath(*sub) / filename]
    cfg_path = PROJECT_ROOT / "config" / "external_storage.json"
    try:
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if cfg.get("use_external_storage") and isinstance(cfg.get("data_dir"), str) and cfg.get("data_dir").strip():
                external_root = Path(str(cfg["data_dir"]).strip())
                relative_parts = sub[1:] if sub and sub[0] == "data" else sub
                mirrored = external_root.joinpath(*relative_parts) / filename
                if mirrored not in targets:
                    targets.append(mirrored)
    except Exception as e:
        logger.debug("external artifact path resolution failed: %s", e)
    return targets


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
    target_paths = _artifact_target_paths(contract_id, task_id, archetype)
    if not target_paths:
        return None
    try:
        blob = {
            "task_id": task_id,
            "archetype": archetype,
            "contract_id": contract_id,
            "execution_tier": execution_tier,
            "payload": payload,
        }
        primary_path: Optional[Path] = None
        for path in target_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(blob, f, indent=2, ensure_ascii=False)
            if primary_path is None:
                primary_path = path
                logger.info("[SelfTask] artifact saved %s", path)
            else:
                logger.info("[SelfTask] artifact mirrored %s", path)
        if contract_id in (
            "system_improvement_proposal",
            "learned_digest",
            "capability_gap_report",
            "offer_pack",
        ):
            _prune_generated_reports_dir(PROJECT_ROOT, max_files=_GENERATED_REPORTS_MAX_FILES)
        return primary_path
    except Exception as e:
        logger.debug("artifact save failed: %s", e)
        return None
