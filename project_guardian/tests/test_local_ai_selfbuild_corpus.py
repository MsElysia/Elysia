"""local_ai_selfbuild_corpus: admitted learning rows -> on-disk self-build corpus."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from project_guardian.local_ai_selfbuild_corpus import (
    CHUNK_EMBEDDINGS_FILENAME,
    CHUNK_EMBEDDINGS_F32,
    CHUNK_EMBEDDINGS_INDEX,
    CORPUS_DIRNAME,
    MANIFEST_NAME,
    RAG_CHUNKS_FILENAME,
    estimate_selfbuild_corpus_mission_alignment,
    export_selfbuild_chunk_embeddings,
    maybe_append_local_ai_selfbuild_row,
    read_embedding_from_index_row,
    rebuild_local_ai_selfbuild_rag_chunks,
    should_run_selfbuild_embed_export,
    should_run_selfbuild_rag_export,
)


def test_append_when_ollama_signal_and_relevance(tmp_path: Path):
    storage = tmp_path / "learned"
    storage.mkdir(parents=True, exist_ok=True)
    cfg = {
        "local_ai_selfbuild_enabled": True,
        "local_ai_selfbuild_min_relevance": 2,
        "local_ai_selfbuild_topics": ["ollama"],
        "local_ai_selfbuild_keywords": None,
    }
    item = {
        "source": "reddit",
        "title": "Running mistral on Ollama with GPU offload",
        "text": "Discussion of modelfile and context length.",
        "compressed": "Tips for Ollama performance tuning on Windows.",
        "url": "https://reddit.com/r/LocalLLaMA/x",
    }
    score_info = {"relevance": 3, "trust_tier": "low", "category": "operational"}
    ok = maybe_append_local_ai_selfbuild_row(
        storage_path=storage,
        item=item,
        score_info=score_info,
        session_topics=["local LLM"],
        cfg=cfg,
        recent_fingerprints=set(),
    )
    assert ok is True
    root = storage / CORPUS_DIRNAME
    assert root.is_dir()
    jsonl = next(root.glob("corpus_*.jsonl"))
    line = jsonl.read_text(encoding="utf-8").strip().splitlines()[0]
    row = json.loads(line)
    assert row["source"] == "reddit"
    assert "ollama" in row["signals"]


def test_skip_when_no_signal(tmp_path: Path):
    storage = tmp_path / "learned2"
    storage.mkdir(parents=True, exist_ok=True)
    cfg = {"local_ai_selfbuild_enabled": True, "local_ai_selfbuild_min_relevance": 2}
    item = {
        "source": "rss",
        "title": "Generic celebrity news",
        "text": "No technical content here.",
        "compressed": "Summary about entertainment.",
    }
    score_info = {"relevance": 4, "trust_tier": "medium", "category": "strategic"}
    ok = maybe_append_local_ai_selfbuild_row(
        storage_path=storage,
        item=item,
        score_info=score_info,
        session_topics=["shopping"],
        cfg=cfg,
        recent_fingerprints=set(),
    )
    assert ok is False


def test_rebuild_rag_chunks_from_corpus(tmp_path: Path):
    storage = tmp_path / "learned4"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    corp = root / "corpus_2099-01-01.jsonl"
    rec = {
        "captured_at": "2099-01-01T00:00:00Z",
        "fingerprint": "abc123",
        "source": "reddit",
        "title": "Ollama",
        "url": None,
        "text_excerpt": "word " * 120,
        "compressed": "more " * 80,
        "relevance": 3,
        "signals": ["ollama"],
        "purpose_tags": [],
    }
    corp.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_rag_export_enabled": True,
        "local_ai_selfbuild_rag_max_corpus_rows": 50,
        "local_ai_selfbuild_rag_chunk_chars": 200,
        "local_ai_selfbuild_rag_chunk_overlap": 40,
        "local_ai_selfbuild_rag_min_chunk_chars": 40,
    }
    out = rebuild_local_ai_selfbuild_rag_chunks(storage, cfg)
    assert out.get("ok") is True
    assert int(out.get("chunks_written") or 0) >= 1
    rag = root / RAG_CHUNKS_FILENAME
    assert rag.is_file()


def test_rebuild_rag_chunks_skips_when_no_chunks_generated(tmp_path: Path):
    storage = tmp_path / "learned4_empty"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    corp = root / "corpus_2099-01-02.jsonl"
    rec = {
        "captured_at": "2099-01-02T00:00:00Z",
        "fingerprint": "abc456",
        "source": "reddit",
        "title": "Tiny",
        "url": None,
        "text_excerpt": "x",
        "compressed": "",
        "relevance": 3,
        "signals": ["ollama"],
        "purpose_tags": [],
    }
    corp.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_rag_export_enabled": True,
        "local_ai_selfbuild_rag_chunk_chars": 200,
        "local_ai_selfbuild_rag_chunk_overlap": 40,
        "local_ai_selfbuild_rag_min_chunk_chars": 40,
    }
    out = rebuild_local_ai_selfbuild_rag_chunks(storage, cfg)
    assert out.get("skipped") is True
    assert out.get("reason") == "no_chunks_generated"


def test_export_embeddings_ram_pressure_caps_chunks(tmp_path: Path):
    storage = tmp_path / "learned_ramcap"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True)
    rag = root / RAG_CHUNKS_FILENAME
    lines = [
        json.dumps(
            {
                "chunk_id": f"c{i}",
                "text": "ollama inference tuning quantisation " * 5,
                "title": "t",
                "signals": [],
            }
        )
        for i in range(12)
    ]
    rag.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_embed_enabled": True,
        "local_ai_selfbuild_embed_storage": "f32_index",
        "local_ai_selfbuild_embed_model": "m",
        "local_ai_selfbuild_embed_max_chunks_per_run": 24,
        "local_ai_selfbuild_embed_batch_size": 8,
        "local_ai_selfbuild_embed_timeout_sec": 30,
    }
    fake_vec = [0.1, 0.2, 0.3]
    mpc = {
        "memory_pressure_trigger_fraction": 0.88,
        "selfbuild_embed_ram_trigger_fraction": 0.88,
        "selfbuild_embed_max_chunks_when_ram_high": 8,
        "selfbuild_embed_batch_when_ram_high": 2,
    }
    with patch("project_guardian.local_ai_selfbuild_corpus.system_ram_used_fraction", return_value=0.95):
        with patch("project_guardian.monitoring._load_memory_pressure_config", return_value=mpc):
            with patch(
                "project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input",
                side_effect=lambda texts, model, timeout: [[float(x) for x in fake_vec] for _ in texts],
            ):
                out = export_selfbuild_chunk_embeddings(storage, cfg)
    assert out.get("ok") is True
    assert out.get("ram_pressure_embed_cap") is True
    assert int(out.get("rows_appended") or 0) == 8
    assert int(out.get("embed_max_chunks_effective") or 0) == 8


def test_export_embeddings_f32_index_roundtrip(tmp_path: Path):
    storage = tmp_path / "learned6"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    rag = root / RAG_CHUNKS_FILENAME
    rag.write_text(
        json.dumps({"chunk_id": "c1", "text": "ollama run mistral for local inference " * 4, "title": "t", "signals": []})
        + "\n",
        encoding="utf-8",
    )
    cfg = {
        "local_ai_selfbuild_embed_enabled": True,
        "local_ai_selfbuild_embed_storage": "f32_index",
        "local_ai_selfbuild_embed_model": "nomic-embed-text",
        "local_ai_selfbuild_embed_max_chunks_per_run": 4,
        "local_ai_selfbuild_embed_batch_size": 2,
        "local_ai_selfbuild_embed_timeout_sec": 30,
    }
    fake_vec = [0.1, 0.2, 0.3]
    with patch(
        "project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input",
        side_effect=lambda texts, model, timeout: [[float(x) for x in fake_vec] for _ in texts],
    ):
        out = export_selfbuild_chunk_embeddings(storage, cfg)
    assert out.get("ok") is True
    assert int(out.get("rows_appended") or 0) >= 1
    assert (root / CHUNK_EMBEDDINGS_F32).is_file()
    assert (root / CHUNK_EMBEDDINGS_INDEX).is_file()
    idx_line = (root / CHUNK_EMBEDDINGS_INDEX).read_text(encoding="utf-8").strip().splitlines()[0]
    meta = json.loads(idx_line)
    assert meta["chunk_id"] == "c1"
    assert meta["dims"] == 3
    vec = read_embedding_from_index_row(root, meta)
    assert vec is not None
    assert len(vec) == 3
    assert abs(vec[0] - 0.1) < 1e-5


def test_export_embeddings_jsonl_inline(tmp_path: Path):
    storage = tmp_path / "learned6b"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    rag = root / RAG_CHUNKS_FILENAME
    rag.write_text(
        json.dumps({"chunk_id": "c2", "text": "ollama local llm " * 8, "title": "t2", "signals": []}) + "\n",
        encoding="utf-8",
    )
    cfg = {
        "local_ai_selfbuild_embed_enabled": True,
        "local_ai_selfbuild_embed_storage": "jsonl",
        "local_ai_selfbuild_embed_model": "m",
        "local_ai_selfbuild_embed_max_chunks_per_run": 4,
        "local_ai_selfbuild_embed_batch_size": 2,
    }
    fake_vec = [0.5, 0.25]
    with patch(
        "project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input",
        side_effect=lambda texts, model, timeout: [[float(x) for x in fake_vec] for _ in texts],
    ):
        out = export_selfbuild_chunk_embeddings(storage, cfg)
    assert out.get("ok") is True
    emb = root / CHUNK_EMBEDDINGS_FILENAME
    assert emb.is_file()
    row = json.loads(emb.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["chunk_id"] == "c2"
    assert row["dims"] == 2


def test_export_embeddings_reports_zero_vector_failure(tmp_path: Path):
    storage = tmp_path / "learned6c"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    rag = root / RAG_CHUNKS_FILENAME
    rows = [
        {"chunk_id": "c3", "text": "ollama embedding model unavailable " * 4, "title": "t3", "signals": []},
        {"chunk_id": "c4", "text": "local rag vectors missing " * 5, "title": "t4", "signals": []},
    ]
    rag.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_embed_enabled": True,
        "local_ai_selfbuild_embed_storage": "f32_index",
        "local_ai_selfbuild_embed_model": "missing-model",
        "local_ai_selfbuild_embed_max_chunks_per_run": 4,
        "local_ai_selfbuild_embed_batch_size": 2,
    }
    with patch(
        "project_guardian.context_pipeline.embedding_backend._embed_ollama_multi_input",
        side_effect=lambda texts, model, timeout: [None for _ in texts],
    ):
        out = export_selfbuild_chunk_embeddings(storage, cfg)
    assert out.get("ok") is False
    assert out.get("reason") == "no_embeddings_returned"
    assert int(out.get("rows_appended") or 0) == 0
    assert int(out.get("errors") or 0) == 2
    assert not (root / CHUNK_EMBEDDINGS_F32).exists()
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["chunk_embeddings"]["ok"] is False


def test_should_run_embed_policy(tmp_path: Path):
    storage = tmp_path / "learned7"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True)
    (root / RAG_CHUNKS_FILENAME).write_text('{"chunk_id":"x","text":"hello world here"}\n', encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_embed_enabled": True,
        "local_ai_selfbuild_embed_model": "m",
    }
    assert should_run_selfbuild_embed_export(cfg, storage, rag_rebuilt_ok=True, corpus_rows_appended_session=0) is True
    assert should_run_selfbuild_embed_export(cfg, storage, rag_rebuilt_ok=False, corpus_rows_appended_session=0) is False


def test_should_run_rag_policy(tmp_path: Path):
    storage = tmp_path / "learned5"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True)
    (root / "corpus_2099-02-01.jsonl").write_text(
        json.dumps(
            {
                "fingerprint": "fp1",
                "title": "t",
                "compressed": "c" * 200,
                "text_excerpt": "",
                "signals": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cfg = {"local_ai_selfbuild_rag_export_enabled": True, "local_ai_selfbuild_rag_export_each_run": False}
    assert should_run_selfbuild_rag_export(cfg, storage, corpus_rows_appended_session=0) is True
    (root / RAG_CHUNKS_FILENAME).write_text("x\n", encoding="utf-8")
    assert should_run_selfbuild_rag_export(cfg, storage, corpus_rows_appended_session=0) is False
    assert should_run_selfbuild_rag_export(cfg, storage, corpus_rows_appended_session=1) is True


def test_respects_disabled(tmp_path: Path):
    storage = tmp_path / "learned3"
    storage.mkdir(parents=True, exist_ok=True)
    cfg = {"local_ai_selfbuild_enabled": False, "local_ai_selfbuild_min_relevance": 1}
    item = {"source": "web", "title": "Ollama guide", "text": "ollama run mistral", "compressed": "ollama"}
    score_info = {"relevance": 5, "trust_tier": "medium", "category": "operational"}
    ok = maybe_append_local_ai_selfbuild_row(
        storage_path=storage,
        item=item,
        score_info=score_info,
        session_topics=[],
        cfg=cfg,
        recent_fingerprints=set(),
    )
    assert ok is False


def test_estimate_selfbuild_corpus_mission_alignment_counts(tmp_path: Path):
    storage = tmp_path / "learned_e"
    root = storage / CORPUS_DIRNAME
    root.mkdir(parents=True)
    row_ok = json.dumps(
        {
            "fingerprint": "aa",
            "title": "Ollama quantize",
            "compressed": "gguf model",
            "text_excerpt": "rag and embedding",
        }
    )
    row_bad = json.dumps(
        {
            "fingerprint": "bb",
            "title": "unrelated",
            "compressed": "zzz",
            "text_excerpt": "nothing",
        }
    )
    (root / "corpus_2099-01-01.jsonl").write_text(row_ok + "\n" + row_bad + "\n", encoding="utf-8")
    cfg = {
        "local_ai_selfbuild_topics": ["ollama", "rag"],
        "local_ai_selfbuild_keywords": ["gguf"],
    }
    est = estimate_selfbuild_corpus_mission_alignment(storage, cfg, max_rows=100)
    assert est["rows_scanned"] == 2
    assert est["aligned_rows"] == 1
    assert est["misaligned_rows"] == 1
