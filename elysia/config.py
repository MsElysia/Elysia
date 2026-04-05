"""Runtime configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class RuntimeConfig:
    mode: str = "all"
    env: str = "dev"
    proposals_root: Path = Path("proposals")
    log_level: str = "INFO"
    enable_api: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8123
    enable_webscout: bool = True
    require_api_keys: bool = False


def load_runtime_config(
    mode: Optional[str] = None,
    env: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> RuntimeConfig:
    """
    Load runtime config from environment defaults plus user overrides.
    """

    cfg = RuntimeConfig(
        mode=mode or os.getenv("ELYSIA_MODE", "all"),
        env=env or os.getenv("ELYSIA_ENV", "dev"),
        proposals_root=Path(
            os.getenv("ELYSIA_PROPOSALS_ROOT", "proposals")
        ).resolve(),
        log_level=os.getenv("ELYSIA_LOG_LEVEL", "INFO"),
        enable_api=os.getenv("ELYSIA_ENABLE_API", "1") not in ("0", "false", "False"),
        api_host=os.getenv("ELYSIA_API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("ELYSIA_API_PORT", "8123")),
        enable_webscout=os.getenv("ELYSIA_ENABLE_WEBSCOUT", "1")
        not in ("0", "false", "False"),
        require_api_keys=os.getenv("ELYSIA_REQUIRE_KEYS", "0")
        in ("1", "true", "True"),
    )

    if cfg.mode == "core":
        cfg.enable_webscout = False

    if overrides:
        for key, value in overrides.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    return cfg

