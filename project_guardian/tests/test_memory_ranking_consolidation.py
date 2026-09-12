"""Ensure a single canonical memory_ranking implementation and no shadowing of memory.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import project_guardian.memory_ranking as canonical_mr
import project_guardian.brain.memory_ranking as shim_mr


def test_canonical_public_import_surface():
    from project_guardian.memory_ranking import (
        MemoryCompressionProposal,
        MemoryRankingConfig,
        MemoryRankingInput,
        MemoryRankingReport,
        MemoryScores,
        RankedMemory,
        clear_memory_ranking_config_cache,
        get_memory_ranking_config,
        optional_remember_extras_for_pipeline,
        propose_memory_compression,
        rank_memories,
        redact_memory_text,
        score_memory,
        should_retain_full_memory,
        summarize_memory_for_compression,
    )

    assert MemoryRankingConfig is not None
    assert callable(score_memory)
    assert callable(rank_memories)
    assert callable(propose_memory_compression)
    assert callable(summarize_memory_for_compression)
    assert callable(should_retain_full_memory)
    assert callable(optional_remember_extras_for_pipeline)
    assert callable(redact_memory_text)
    assert callable(get_memory_ranking_config)
    assert callable(clear_memory_ranking_config_cache)
    _ = (MemoryRankingInput, MemoryScores, RankedMemory, MemoryCompressionProposal, MemoryRankingReport)


def test_brain_shim_reexports_same_objects():
    from project_guardian.brain.memory_ranking import (
        MemoryRankingInput as ShimMRI,
        get_memory_ranking_config as ShimG,
        score_memory as ShimS,
    )

    assert ShimMRI is canonical_mr.MemoryRankingInput
    assert ShimG is canonical_mr.get_memory_ranking_config
    assert ShimS is canonical_mr.score_memory


def test_shim_module_identity_matches_canonical_for_core_types():
    assert shim_mr.MemoryRankingInput is canonical_mr.MemoryRankingInput
    assert shim_mr.MemoryScores is canonical_mr.MemoryScores
    assert shim_mr.RankedMemory is canonical_mr.RankedMemory
    assert shim_mr.MemoryCompressionProposal is canonical_mr.MemoryCompressionProposal
    assert shim_mr.MemoryRankingReport is canonical_mr.MemoryRankingReport
    assert shim_mr.MemoryRankingConfig is canonical_mr.MemoryRankingConfig


def test_project_guardian_memory_is_memorycore_module_not_package():
    import project_guardian.memory as mem

    assert hasattr(mem, "MemoryCore")
    path = Path(str(mem.__file__)).resolve()
    assert path.name == "memory.py", f"expected memory.py module, got {path}"


def test_no_memory_package_directory_shadowing_memorycore():
    root = Path(__file__).resolve().parents[1]
    memory_pkg_init = root / "memory" / "__init__.py"
    assert not memory_pkg_init.is_file(), (
        "project_guardian/memory/ package must not exist; it shadows memory.py / MemoryCore"
    )


def test_memory_ranking_config_safe_defaults():
    from project_guardian.memory_ranking import clear_memory_ranking_config_cache, get_memory_ranking_config

    clear_memory_ranking_config_cache()
    cfg = get_memory_ranking_config()
    assert cfg.enabled is False
    assert cfg.dry_run is True


def test_memory_ranking_diagnostic_script_runs():
    import os

    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "memory_ranking_diagnostic.py"
    env = {**os.environ, "PYTHONPATH": str(repo)}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_brain_pipeline_still_importable_after_consolidation():
    from project_guardian.brain.pipeline import BrainPipeline

    assert BrainPipeline is not None
