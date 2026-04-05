"""Structured logging helpers for the unified runtime."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_CONFIGURED = False


def setup_logging(level: str = "INFO", log_path: Optional[Path] = None) -> None:
    """
    Configure logging once with console + rotating file output.

    Subsequent calls only adjust the root level so that downstream modules
    (e.g., Architect-Core) can reuse the same handlers.
    """
    global _CONFIGURED

    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if _CONFIGURED:
        root_logger.setLevel(numeric_level)
        return

    log_path = log_path or Path("logs/elysia_runtime.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stderr)  # Use stderr to avoid contaminating interactive prompts
    console_handler.setFormatter(formatter)

    root_logger.setLevel(numeric_level)
    root_logger.handlers = [console_handler, file_handler]

    _CONFIGURED = True

