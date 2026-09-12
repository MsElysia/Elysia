"""local_ai_selfbuild_retrieve: cosine RAG context for unified LLM injection."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.local_ai_selfbuild_retrieve import (
    _cosine,
    build_selfbuild_rag_context_block,
    effective_selfbuild_rag_inject_params,
    maybe_prepend_selfbuild_rag_system_message,
)


def test_effective_selfbuild_rag_inject_params_clamps():
    e = effective_selfbuild_rag_inject_params(
        {
            "local_ai_selfbuild_rag_inject_top_k": 99,
            "local_ai_selfbuild_rag_inject_max_chars": 50,
            "local_ai_selfbuild_rag_inject_max_index_rows": 10,
            "local_ai_selfbuild_rag_inject_min_score": 2.0,
        }
    )
    assert e["top_k"] == 12
    assert e["max_chars"] == 400
    assert e["max_index_rows"] == 50
    assert e["min_score"] == 0.95


def test_cosine_basic():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert abs(_cosine(a, b) - 1.0) < 1e-6


def test_build_selfbuild_rag_context_block(tmp_path: Path):
    root = tmp_path / "learned" / "local_ai_selfbuild"
    root.mkdir(parents=True)
    rag = root / "rag_chunks_latest.jsonl"
    cid = "abc123"
    rag.write_text(
        json.dumps({"chunk_id": cid, "text": "ollama local inference tuning " * 6, "title": "Ollama tips"})
        + "\n",
        encoding="utf-8",
    )
    idx = root / "chunk_embeddings_index.jsonl"
    idx.write_text(
        json.dumps(
            {
                "chunk_id": cid,
                "model": "m",
                "dims": 3,
                "offset": 0,
                "length_bytes": 12,
                "title": "Ollama tips",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    import array as arrlib

    vec = [0.0, 1.0, 0.0]
    bin_path = root / "chunk_embeddings.f32.bin"
    bin_path.write_bytes(arrlib.array("f", vec).tobytes())

    cfg = {
        "local_ai_selfbuild_embed_model": "m",
        "local_ai_selfbuild_rag_inject_top_k": 3,
        "local_ai_selfbuild_rag_inject_max_index_rows": 100,
        "local_ai_selfbuild_rag_inject_max_chars": 4000,
        "local_ai_selfbuild_rag_inject_min_score": 0.01,
        "local_ai_selfbuild_rag_inject_embed_timeout_sec": 10,
    }

    stats: dict = {}
    with patch(
        "project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input",
        return_value=[vec],
    ):
        block = build_selfbuild_rag_context_block(
            "ollama inference tuning help",
            storage_path=tmp_path / "learned",
            cfg=cfg,
            stats=stats,
        )

    assert "Elysia local self-build RAG" in block
    assert "Ollama" in block
    assert stats.get("ok") is True
    assert int(stats.get("chunks") or 0) >= 1
    assert stats.get("top_k") == 3
    assert stats.get("max_chars") == 4000
    assert stats.get("min_score") == 0.01


def test_maybe_prepend_disabled_returns_same_messages():
    msgs = [{"role": "user", "content": "hello"}]
    g = object()
    with patch(
        "project_guardian.auto_learning.load_learning_config",
        return_value={"local_ai_selfbuild_rag_inject_enabled": False},
    ):
        out, meta = maybe_prepend_selfbuild_rag_system_message(
            msgs,
            user_text="hello",
            guardian=g,
            require_autonomy_safe_reasoning=True,
            route_task_type="reasoning",
            skip_capability_preamble=False,
            prompt_extra={},
        )
    assert out == msgs
    assert meta.get("applied") is False
    assert meta.get("skip") == "disabled"
    assert meta.get("top_k") == 5


def test_build_selfbuild_rag_missing_artifacts_attempts_rebuild(tmp_path: Path):
    cfg = {
        "local_ai_selfbuild_embed_model": "nomic-embed-text",
        "local_ai_selfbuild_rag_export_enabled": True,
        "local_ai_selfbuild_embed_enabled": True,
    }
    stats: dict = {}
    with patch(
        "project_guardian.local_ai_selfbuild_retrieve._maybe_rebuild_selfbuild_artifacts",
        return_value={"attempted": True},
    ) as rebuild_mock:
        block = build_selfbuild_rag_context_block(
            "local ollama rag tuning details for embeddings",
            storage_path=tmp_path / "learned",
            cfg=cfg,
            stats=stats,
        )
    assert block == ""
    assert rebuild_mock.called
    assert stats.get("skip") == "missing_artifacts"


def test_selfbuild_rebuild_skips_when_corpus_dir_missing(tmp_path: Path, monkeypatch):
    import project_guardian.local_ai_selfbuild_retrieve as retrieve

    monkeypatch.setattr(retrieve, "_last_selfbuild_artifact_rebuild_attempt_ts", 0.0)
    storage = tmp_path / "learned"
    root = storage / "local_ai_selfbuild"

    out = retrieve._maybe_rebuild_selfbuild_artifacts(
        storage_path=storage,
        cfg={
            "local_ai_selfbuild_rag_export_enabled": True,
            "local_ai_selfbuild_embed_enabled": True,
        },
        idx_path=root / "chunk_embeddings_index.jsonl",
        bin_path=root / "chunk_embeddings.f32.bin",
        rag_path=root / "rag_chunks_latest.jsonl",
    )

    assert out["attempted"] is False
    assert out["reason"] == "no_corpus_dir"


def test_selfbuild_rebuild_skips_recent_embed_failure_manifest(tmp_path: Path, monkeypatch):
    import project_guardian.local_ai_selfbuild_retrieve as retrieve

    monkeypatch.setattr(retrieve, "_last_selfbuild_artifact_rebuild_attempt_ts", 0.0)
    storage = tmp_path / "learned"
    root = storage / "local_ai_selfbuild"
    root.mkdir(parents=True)
    (root / "rag_chunks_latest.jsonl").write_text(
        json.dumps({"chunk_id": "c1", "text": "local rag embedding test " * 4}) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "chunk_embeddings": {
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ok": False,
                    "reason": "no_embeddings_returned",
                    "model": "nomic-embed-text",
                    "rows_appended": 0,
                    "errors": 2,
                    "pending_seen": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    with patch("project_guardian.local_ai_selfbuild_corpus.rebuild_local_ai_selfbuild_rag_chunks") as rag_mock:
        out = retrieve._maybe_rebuild_selfbuild_artifacts(
            storage_path=storage,
            cfg={
                "local_ai_selfbuild_embed_model": "nomic-embed-text",
                "local_ai_selfbuild_embed_failure_cooldown_sec": 3600,
            },
            idx_path=root / "chunk_embeddings_index.jsonl",
            bin_path=root / "chunk_embeddings.f32.bin",
            rag_path=root / "rag_chunks_latest.jsonl",
        )

    assert out["attempted"] is False
    assert out["reason"] == "recent_embed_failure"
    assert out["has_rag"] is True
    assert out["embed_result"]["reason"] == "no_embeddings_returned"
    rag_mock.assert_not_called()
