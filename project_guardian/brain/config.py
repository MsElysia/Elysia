# project_guardian/brain/config.py
"""Load ``config/brain_pipeline.json`` with safe defaults (never raises on startup)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "brain_pipeline.json"


def _default_entrypoints() -> Dict[str, bool]:
    return {
        "operator_chat": False,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }


def _default_prompt_contract_validation() -> Dict[str, Any]:
    return {
        "enabled": False,
        "mode": "warn",
        "modules": [
            "planner",
            "tool_router",
            "llm_router",
            "risk_checker",
            "think_decide_act_thinker",
            "think_decide_act_proposer",
        ],
        "operator_chat": False,
    }


@dataclass(frozen=True)
class BrainPipelineConfig:
    """Resolved brain pipeline settings (safe defaults if file missing or invalid)."""

    enabled: bool = False
    use_think_decide_act: bool = True
    dry_run: bool = True
    persist_trace: bool = True
    trace_path: Path = field(default_factory=lambda: _REPO_ROOT / "data" / "runtime" / "brain_last_pipeline.json")
    entrypoints: Dict[str, bool] = field(default_factory=_default_entrypoints)
    prompt_contract_validation: Dict[str, Any] = field(default_factory=_default_prompt_contract_validation)

    def entrypoint_enabled(self, name: str) -> bool:
        return bool(self.entrypoints.get(name, False))


def _parse_bool(val: Any, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return default


def _load_raw(path: Path) -> Tuple[Dict[str, Any], str]:
    """Returns (inner brain_pipeline dict or {}, reason)."""
    if not path.is_file():
        return {}, "missing_file"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("brain_pipeline config invalid JSON %s: %s", path, exc)
        return {}, "invalid_json"
    if not isinstance(raw, dict):
        logger.warning("brain_pipeline config root must be an object: %s", path)
        return {}, "bad_root"
    inner = raw.get("brain_pipeline")
    if inner is None:
        logger.warning("brain_pipeline config missing 'brain_pipeline' key: %s", path)
        return {}, "missing_brain_pipeline_key"
    if not isinstance(inner, dict):
        logger.warning("brain_pipeline.brain_pipeline must be an object: %s", path)
        return {}, "bad_brain_pipeline_type"
    return inner, "ok"


def _merge(inner: Dict[str, Any], reason: str) -> BrainPipelineConfig:
    ep = _default_entrypoints()
    raw_ep = inner.get("entrypoints")
    if isinstance(raw_ep, dict):
        for k in list(ep.keys()):
            if k in raw_ep:
                ep[k] = _parse_bool(raw_ep.get(k), ep[k])
        # Forward-compatible: allow new entrypoint flags from JSON not yet in defaults.
        for k, v in raw_ep.items():
            if k not in ep and isinstance(k, str):
                ep[k] = _parse_bool(v, False)

    trace_rel = inner.get("trace_path", "data/runtime/brain_last_pipeline.json")
    try:
        trace_path = (_REPO_ROOT / str(trace_rel).replace("\\", "/")).resolve()
    except Exception:
        trace_path = (_REPO_ROOT / "data" / "runtime" / "brain_last_pipeline.json").resolve()

    pcv = _default_prompt_contract_validation()
    raw_pcv = inner.get("prompt_contract_validation")
    if isinstance(raw_pcv, dict):
        pcv = dict(pcv)
        pcv["enabled"] = _parse_bool(raw_pcv.get("enabled"), pcv["enabled"])
        mode = str(raw_pcv.get("mode") or pcv["mode"]).strip().lower()
        pcv["mode"] = mode if mode in {"warn", "strict", "off"} else "warn"
        pcv["operator_chat"] = _parse_bool(raw_pcv.get("operator_chat"), pcv["operator_chat"])
        if isinstance(raw_pcv.get("modules"), list) and raw_pcv["modules"]:
            pcv["modules"] = [str(m) for m in raw_pcv["modules"] if str(m).strip()]

    cfg = BrainPipelineConfig(
        enabled=_parse_bool(inner.get("enabled"), False),
        use_think_decide_act=_parse_bool(inner.get("use_think_decide_act"), True),
        dry_run=_parse_bool(inner.get("dry_run"), True),
        persist_trace=_parse_bool(inner.get("persist_trace"), True),
        trace_path=trace_path,
        entrypoints=ep,
        prompt_contract_validation=pcv,
    )
    if reason != "ok":
        logger.warning("brain_pipeline config using defaults (%s)", reason)
    return cfg


@lru_cache(maxsize=8)
def get_brain_pipeline_config(*, _path_str: str = "") -> BrainPipelineConfig:
    """Load brain pipeline config. Cached by path string; pass _path_str for tests only."""
    path = Path(_path_str) if _path_str else _DEFAULT_CONFIG_PATH
    inner, reason = _load_raw(path)
    return _merge(inner, reason)


def clear_brain_pipeline_config_cache() -> None:
    get_brain_pipeline_config.cache_clear()
