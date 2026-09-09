# project_guardian/context_pipeline/memory_sidecar.py
"""Data directory for pipeline artifacts (separate from social_intelligence)."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_pipeline_data_dir() -> Path:
    d = project_root() / "data" / "context_pipeline"
    d.mkdir(parents=True, exist_ok=True)
    return d
