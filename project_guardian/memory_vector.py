# project_guardian/memory_vector.py
# Vector Memory System with FAISS Integration
# Enhances MemoryCore with semantic search capabilities

import os
import json
import hashlib
import logging
import threading
import tempfile
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("FAISS not available. Install with: pip install faiss-cpu")

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

logger = logging.getLogger(__name__)

VECTOR_REBUILD_SAFE_MAX = 250


class VectorMemory:
    """
    Vector-based memory storage using FAISS for semantic search.
    Stores embeddings alongside metadata for enhanced recall.
    """
    
    def __init__(
        self,
        vector_dim: int = 1536,  # OpenAI ada-002 dimension
        index_path: str = "memory/vectors/index.faiss",
        metadata_path: str = "memory/vectors/metadata.json",
        embedding_model: str = "text-embedding-ada-002",
        lazy: bool = False,
    ):
        self.vector_dim = vector_dim
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.generation_path = metadata_path + ".generation.json"
        self.embedding_model = embedding_model
        self.embedding_status = {"available": False, "provider": None, "reason": "not_attempted"}
        self._sentence_transformer_model = None  # Lazy-loaded for sentence-transformers
        # After load/encode failure, do not retry ST for every embed in this process
        self._st_local_model_broken: bool = False
        self._st_load_failure_logged: bool = False
        # Degraded / rebuild state for cleanup
        self.degraded: bool = False
        self.rebuild_pending: bool = False
        # Observability: last rebuild attempt outcome (in-memory, lightweight)
        self.last_rebuild_attempt_at: Optional[str] = None
        self.last_rebuild_result: Optional[str] = None  # "success" | "failed" | "skipped"
        self.last_rebuild_reason: Optional[str] = None
        self.last_rebuild_error: Optional[str] = None
        self._lazy = lazy
        self.loaded: bool = False
        self._vector_load_lock = threading.Lock()
        self._metadata_io_lock = threading.Lock()
        
        # Existing bytes with no trusted local-model provenance must remain untouched.
        os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
        self.vector_pair_verified = self._verify_disk_pair()
        if not self.vector_pair_verified:
            self._quarantine_pair("unverified_legacy_or_incomplete_vector_pair")

        if FAISS_AVAILABLE:
            if lazy:
                self.index = None
                self.metadata = []
                self.loaded = False
                logger.info("[Startup] VectorMemory FAISS/metadata load deferred (lazy=True)")
            else:
                self.index = self._init_index() if self.vector_pair_verified else faiss.IndexFlatL2(self.vector_dim)
                self.metadata = []
                if self.vector_pair_verified:
                    self._load_metadata()
                    self._verify_loaded_pair()
                self.loaded = True
        else:
            self.index = None
            self.metadata = []
            self.loaded = True
            logger.warning("Vector memory initialized without FAISS - semantic search disabled")

    _PROVIDER = "sentence_transformers"
    _MODEL = "all-MiniLM-L6-v2"
    _SCHEMA = "elysia.offline_vector_pair.v1"

    @staticmethod
    def _file_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verify_disk_pair(self) -> bool:
        """Legacy or interrupted generations have NO trusted semantic provenance."""
        paths = (self.index_path, self.metadata_path, self.generation_path)
        if any(os.path.islink(p) for p in paths):
            return False
        present = tuple(os.path.isfile(p) for p in paths)
        if not any(present):
            return True  # Empty new store, not historical semantic evidence.
        if not all(present):
            return False
        try:
            with open(self.generation_path, "r", encoding="utf-8") as source:
                receipt = json.load(source)
            return (
                isinstance(receipt, dict)
                and receipt.get("schema") == self._SCHEMA
                and receipt.get("provider") == self._PROVIDER
                and receipt.get("model") == self._MODEL
                and receipt.get("vector_dim") == self.vector_dim
                and receipt.get("index_sha256") == self._file_sha256(self.index_path)
                and receipt.get("metadata_sha256") == self._file_sha256(self.metadata_path)
            )
        except (OSError, ValueError, TypeError):
            return False

    def _quarantine_pair(self, reason: str) -> None:
        self.vector_pair_verified = False
        self.degraded = True
        self.rebuild_pending = True
        self._embedding_unavailable(reason)
        self._set_rebuild_status("failed", reason)

    def _verify_loaded_pair(self) -> None:
        if not self._verify_disk_pair():
            self._quarantine_pair("vector_generation_hash_mismatch")
        elif self.index is not None and (
            int(self.index.ntotal) != len(self.metadata)
            or (hasattr(self.index, "d") and int(self.index.d) != self.vector_dim)
        ):
            self._quarantine_pair("vector_generation_row_or_dimension_mismatch")

    def _persist_verified_pair(self, new_index, new_metadata) -> None:
        """Stage both files first; manifest seals the published pair LAST.

        Two filesystem renames are not a transaction. An interrupted publication
        is rejected on the next read/restart by exact hashes in the old manifest.
        """
        if not self.vector_pair_verified or not self._verify_disk_pair():
            self._quarantine_pair("vector_pair_unverified_before_write")
            raise RuntimeError("unverified vector source; preserving original files")
        if new_metadata and (
            self.embedding_status.get("provider") != self._PROVIDER
            or self.embedding_status.get("available") is not True
        ):
            raise RuntimeError("cannot certify vectors without trusted local embedding")
        if int(new_index.ntotal) != len(new_metadata):
            raise ValueError("candidate vector count disagrees with metadata")
        if hasattr(new_index, "d") and int(new_index.d) != self.vector_dim:
            raise ValueError("candidate vector dimension mismatch")
        staged = []
        publishing = False
        try:
            for directory, prefix in (
                (os.path.dirname(self.metadata_path) or ".", "vector-meta-"),
                (os.path.dirname(self.index_path) or ".", "vector-index-"),
                (os.path.dirname(self.generation_path) or ".", "vector-proof-"),
            ):
                fd, name = tempfile.mkstemp(prefix=prefix, suffix=".pending", dir=directory)
                os.close(fd)
                staged.append(name)
            meta_stage, index_stage, proof_stage = staged
            self._atomic_write_json(meta_stage, new_metadata)
            self._atomic_write_faiss(index_stage, new_index)
            manifest = {
                "schema": self._SCHEMA, "provider": self._PROVIDER,
                "model": self._MODEL, "vector_dim": self.vector_dim,
                "index_sha256": self._file_sha256(index_stage),
                "metadata_sha256": self._file_sha256(meta_stage),
            }
            self._atomic_write_json(proof_stage, manifest)
            # Any failure from this point may leave a partially published pair.
            publishing = True
            self.vector_pair_verified = False
            os.replace(meta_stage, self.metadata_path)
            os.replace(index_stage, self.index_path)
            os.replace(proof_stage, self.generation_path)
            if not self._verify_disk_pair():
                raise RuntimeError("published vector pair failed integrity readback")
            self.vector_pair_verified = True
        except Exception:
            if publishing:
                self._quarantine_pair("vector_pair_partial_publication")
            else:
                self._quarantine_pair("vector_pair_staging_failed")
            raise
        finally:
            for name in staged:
                try:
                    if os.path.exists(name):
                        os.remove(name)  # Only our own uncommitted scratch files.
                except OSError:
                    pass

    def _set_rebuild_status(
        self,
        result: str,
        reason: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record rebuild outcome for observability. Keeps messages concise."""
        self.last_rebuild_attempt_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.last_rebuild_result = result
        self.last_rebuild_reason = (reason or "")[:120]
        self.last_rebuild_error = (error or "")[:200] if error else None

    def record_rebuild_outcome(
        self,
        result: str,
        reason: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record rebuild outcome when invoked from outside (e.g. GuardianCore skip)."""
        self._set_rebuild_status(result, reason, error)

    def load_if_needed(self) -> None:
        """Load FAISS index and metadata once (idempotent). Thread-safe."""
        if self.loaded or not FAISS_AVAILABLE:
            return
        with self._vector_load_lock:
            if self.loaded:
                return
            logger.info("[Startup] VectorMemory: loading FAISS index and metadata (deferred)")
            self.index = self._init_index() if self.vector_pair_verified else faiss.IndexFlatL2(self.vector_dim)
            self.metadata = []
            if self.vector_pair_verified:
                self._load_metadata()
                self._verify_loaded_pair()
            self.loaded = True

    def _reconcile_with_memories(
        self,
        kept_memories: List[Dict[str, Any]],
        safe_max: int,
    ) -> Dict[str, Any]:
        """
        Reconcile vector metadata and index with the kept JSON memories.
        Uses safe_max to avoid heavy rebuilds under pressure.
        """
        self.load_if_needed()
        metadata_before = len(self.metadata or [])
        if not self.vector_pair_verified or not self._verify_disk_pair():
            self._quarantine_pair("vector_rebuild_from_unverified_pair")
            return {
                "metadata_before": metadata_before, "metadata_after": metadata_before,
                "vector_rebuild_status": "failed", "vector_rebuild_success": False,
                "error": "Existing vector generation unverified; no automatic conversion",
            }
        faiss_before = 0
        if self.index is not None and hasattr(self.index, "ntotal"):
            try:
                faiss_before = int(self.index.ntotal)
            except Exception:
                faiss_before = 0

        # If no index or metadata, nothing to do
        if not FAISS_AVAILABLE or self.index is None:
            self._set_rebuild_status("skipped", "FAISS unavailable or no index", None)
            return {
                "metadata_before": metadata_before,
                "metadata_after": metadata_before,
                "faiss_before": faiss_before,
                "faiss_after": faiss_before,
                "vector_rebuild_status": "not_applicable",
                "vector_rebuild_success": True,
                "error": None,
            }

        kept_count = len(kept_memories)
        if kept_count > safe_max:
            # Defer rebuild: leave index/metadata unchanged
            reason = f"kept set exceeded safe threshold ({kept_count}>{safe_max})"
            self._set_rebuild_status("skipped", reason, None)
            return {
                "metadata_before": metadata_before,
                "metadata_after": metadata_before,
                "faiss_before": faiss_before,
                "faiss_after": faiss_before,
                "vector_rebuild_status": "deferred",
                "vector_rebuild_success": False,
                "error": (
                    f"kept set exceeded safe rebuild threshold "
                    f"({kept_count}>{safe_max}); rebuild deferred"
                ),
            }

        # Safe to rebuild: use fresh metadata + index in temporary structures
        new_metadata: List[Dict[str, Any]] = []
        new_index = faiss.IndexFlatL2(self.vector_dim)

        for i, mem in enumerate(kept_memories):
            text = mem.get("thought", "")
            if not text:
                continue
            try:
                from .memory_noise import is_embedding_entirely_skipped, is_low_value_memory_text
                if is_embedding_entirely_skipped(text) or is_low_value_memory_text(
                    text, min_chars_for_substantive=20
                ):
                    continue
                emb = self.generate_embedding(text)
                if emb is None or emb.shape != (self.vector_dim,) or not np.isfinite(emb).all():
                    raise ValueError("required cached local embedding unavailable")
                new_index.add(emb.reshape(1, -1))
                new_metadata.append({
                    "id": i,
                    "text": text,
                    "category": mem.get("category", "general"),
                    "priority": mem.get("priority", 0.5),
                    "timestamp": mem.get("time"),
                    "metadata": mem.get("metadata", {}),
                })
            except Exception:
                # Preserve the old index and metadata if any required row is unavailable.
                self.degraded = True
                self.rebuild_pending = True
                self._set_rebuild_status("failed", "embedding_unavailable")
                return {
                    "metadata_before": metadata_before, "metadata_after": metadata_before,
                    "faiss_before": faiss_before, "faiss_after": faiss_before,
                    "vector_rebuild_status": "failed", "vector_rebuild_success": False,
                    "error": "Required cached local embedding unavailable or invalid",
                }

        try:
            # Only the sealed verified generation can be served after restart.
            self._persist_verified_pair(new_index, new_metadata)
            self.index = new_index
            self.metadata = new_metadata
            self.degraded = False
            self.rebuild_pending = False

            faiss_after = 0
            try:
                faiss_after = int(self.index.ntotal)
            except Exception:
                faiss_after = 0

            self._set_rebuild_status("success", f"rebuilt from {len(self.metadata)} memories", None)
            return {
                "metadata_before": metadata_before,
                "metadata_after": len(self.metadata),
                "faiss_before": faiss_before,
                "faiss_after": faiss_after,
                "vector_rebuild_status": "rebuilt",
                "vector_rebuild_success": True,
                "error": None,
            }
        except Exception as e:
            self.degraded = True
            self.rebuild_pending = True

            err_msg = str(e)[:200] if str(e) else "unknown"
            self._set_rebuild_status("failed", "persist failed", err_msg)
            return {
                "metadata_before": metadata_before,
                "metadata_after": metadata_before,
                "faiss_before": faiss_before,
                "faiss_after": faiss_before,
                "vector_rebuild_status": "failed",
                "vector_rebuild_success": False,
                "error": str(e),
            }

    def rebuild_from_memories(
        self,
        kept_memories: List[Dict[str, Any]],
        safe_max: int = VECTOR_REBUILD_SAFE_MAX,
    ) -> Dict[str, Any]:
        """
        Reconcile vector index and metadata with kept JSON memories.
        Reuses existing _reconcile_with_memories logic. Call when rebuild_pending or degraded.
        """
        self.load_if_needed()
        return self._reconcile_with_memories(kept_memories, safe_max)

    def _init_index(self):
        """Initialize or load FAISS index."""
        if FAISS_AVAILABLE and os.path.exists(self.index_path):
            try:
                index = faiss.read_index(self.index_path)
                logger.info(f"Loaded existing FAISS index from {self.index_path}")
                return index
            except Exception as e:
                try:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    corrupt_copy = f"{self.index_path}.corrupt.{stamp}"
                    os.replace(self.index_path, corrupt_copy)
                    logger.warning(
                        "Failed to load FAISS index: %s; moved corrupt index to %s. Creating new index.",
                        e,
                        corrupt_copy,
                    )
                except Exception:
                    logger.warning(f"Failed to load FAISS index: {e}. Creating new index.")
                self.degraded = True
                self.rebuild_pending = True
                self._set_rebuild_status("failed", "faiss_index_corrupt_or_unreadable", str(e))
                
        # Create new index
        if FAISS_AVAILABLE:
            # L2 distance index (flat, exact search)
            index = faiss.IndexFlatL2(self.vector_dim)
            logger.info(f"Created new FAISS index with dimension {self.vector_dim}")
            return index
        return None
        
    def _load_metadata(self):
        """Load metadata from JSON file."""
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                if not isinstance(self.metadata, list):
                    raise ValueError(f"metadata payload must be a list, got {type(self.metadata).__name__}")
                logger.info(f"Loaded {len(self.metadata)} metadata entries")
            except Exception as e:
                # Preserve the corrupt file for forensics, then continue with clean metadata.
                try:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    corrupt_copy = f"{self.metadata_path}.corrupt.{stamp}"
                    os.replace(self.metadata_path, corrupt_copy)
                    logger.warning(
                        "Failed to load metadata: %s; moved corrupt file to %s",
                        e,
                        corrupt_copy,
                    )
                except Exception:
                    logger.warning(f"Failed to load metadata: {e}")
                self.metadata = []
                self.degraded = True
                self.rebuild_pending = True
                self._set_rebuild_status("failed", "metadata_corrupt_or_unreadable", str(e))
                # Persist an empty metadata list so next startup can proceed cleanly.
                self._save_metadata()
        else:
            self.metadata = []

    def _atomic_write_json(self, path: str, payload: Any) -> None:
        """Atomically write JSON with flush+fsync to reduce corruption risk."""
        parent = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix="vec-meta-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    def _atomic_write_faiss(self, path: str, index_obj) -> None:
        """Atomically write FAISS index with post-write fsync."""
        parent = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix="vec-index-", suffix=".tmp", dir=parent)
        os.close(fd)
        try:
            faiss.write_index(index_obj, tmp_path)
            # Windows can reject fsync on read-only descriptors; use rb+.
            with open(tmp_path, "rb+") as verify_f:
                verify_f.flush()
                os.fsync(verify_f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    def _save_metadata(self):
        """Save metadata to JSON file (locked + retried)."""
        import time as _time

        lock_path = self.metadata_path + ".lock"
        with self._metadata_io_lock:
            for attempt in range(3):
                try:
                    try:
                        with open(lock_path, "a", encoding="utf-8") as _lf:
                            _lf.write("")
                    except Exception:
                        pass
                    self._atomic_write_json(self.metadata_path, self.metadata)
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except Exception:
                        pass
                    return
                except Exception as e:
                    logger.error("Failed to save metadata (attempt %s): %s", attempt + 1, e)
                    _time.sleep(0.05 * (attempt + 1))

    def _save_index(self):
        """Save FAISS index to disk."""
        if FAISS_AVAILABLE and self.index is not None:
            try:
                self._atomic_write_faiss(self.index_path, self.index)
                logger.debug(f"Saved FAISS index to {self.index_path}")
            except Exception as e:
                logger.error(f"Failed to save FAISS index: {e}")

    def _persist_vector_state(self) -> None:
        """Back-compatible entrypoint, now delegates to verified pair publication."""
        if not FAISS_AVAILABLE or self.index is None:
            raise RuntimeError("No FAISS index available")
        self._persist_verified_pair(self.index, self.metadata)
                
    def _embedding_unavailable(self, reason: str) -> None:
        """Record a truthful absence, never invent a semantic match."""
        self.embedding_status = {"available": False, "provider": None, "reason": reason}
        return None

    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Use only already-cached local embeddings. Environment keys grant no cloud authority."""
        try:
            from .memory_noise import is_embedding_entirely_skipped, is_low_value_memory_text
            from .startup_runtime_guard import defer_sentence_transformers_for_embed
            if is_embedding_entirely_skipped(text) or is_low_value_memory_text(
                text, min_chars_for_substantive=20
            ):
                return self._embedding_unavailable("non_vectorizable_text")
            if defer_sentence_transformers_for_embed():
                return self._embedding_unavailable("local_model_deferred")
        except Exception:
            return self._embedding_unavailable("local_policy_unavailable")

        if not HAS_SENTENCE_TRANSFORMERS:
            return self._embedding_unavailable("local_dependency_unavailable")
        if self._st_local_model_broken:
            return self._embedding_unavailable("local_model_unavailable")

        try:
            if self._sentence_transformer_model is None:
                # Never download a missing model or execute remote model code.
                # Older loaders without these safeguards fail closed.
                self._sentence_transformer_model = SentenceTransformer(
                    "all-MiniLM-L6-v2", local_files_only=True, trust_remote_code=False
                )
            result = np.asarray(self._sentence_transformer_model.encode(text), dtype=np.float32)
            if result.ndim != 1 or result.size == 0 or not np.isfinite(result).all():
                raise ValueError("invalid cached local embedding")
            # Preserve legacy FAISS index dimensions without an implicit rebuild.
            if result.size > self.vector_dim:
                result = result[:self.vector_dim]
            elif result.size < self.vector_dim:
                result = np.pad(result, (0, self.vector_dim - result.size))
            self.embedding_status = {
                "available": True, "provider": "sentence_transformers",
                "reason": "local_model_ready",
            }
            return result.astype(np.float32, copy=False)
        except Exception:
            self._st_local_model_broken = True
            logger.warning("Cached local embedding unavailable; no network/hash fallback")
            return self._embedding_unavailable("local_model_unavailable")

    def _generate_hash_embedding(self, text: str) -> np.ndarray:
        """
        Generate a simple hash-based embedding as last resort.
        
        This provides degraded quality but ensures embeddings are always available.
        
        Args:
            text: Text to embed
            
        Returns:
            Hash-based embedding vector
        """
        import hashlib
        
        # Create hash-based embedding
        hash_obj = hashlib.sha256(text.encode('utf-8'))
        hex_str = hash_obj.hexdigest()
        
        # Convert hex to float values
        embedding = []
        for i in range(0, len(hex_str), 2):
            if len(embedding) >= self.vector_dim:
                break
            val = int(hex_str[i:i+2], 16) / 255.0
            embedding.append(val)
        
        # Pad if needed
        while len(embedding) < self.vector_dim:
            embedding.append(0.0)
        
        # Normalize
        embedding = np.array(embedding[:self.vector_dim], dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
            
    def add_memory(
        self,
        text: str,
        category: str = "general",
        priority: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[np.ndarray] = None
    ) -> Optional[int]:
        """
        Add a memory with vector embedding.
        
        Args:
            text: Memory text
            category: Memory category
            priority: Priority level
            metadata: Additional metadata
            embedding: Optional pre-computed embedding
            
        Returns:
            Memory ID or None if failed
        """
        try:
            from .memory_noise import is_embedding_entirely_skipped
            from .startup_runtime_guard import should_defer_vector_add_during_startup

            if is_embedding_entirely_skipped(text):
                logger.debug("Vector add skipped (non-vectorizable fragment)")
                return None
            if should_defer_vector_add_during_startup(category, float(priority or 0), text or ""):
                logger.debug("Vector add deferred (startup / pre-operational)")
                return None
        except Exception:
            pass

        self.load_if_needed()
        if self.index is None or not self.vector_pair_verified or not self._verify_disk_pair():
            self._quarantine_pair("vector_add_to_unverified_pair")
            return None
        # Caller-provided vectors lack model/provider provenance. Do not certify
        # or mix them into a locally attested SentenceTransformer generation.
        if embedding is not None:
            self._embedding_unavailable("external_embedding_provenance_unverified")
            return None

        embedding = self.generate_embedding(text)
        if embedding is None or embedding.shape != (self.vector_dim,) or not np.isfinite(embedding).all():
            return None

        try:
            # Work on a copy. The old in-memory index and disk pair survive
            # failures while candidate files are staged or published.
            working_index = faiss.clone_index(self.index)
            working_index.add(embedding.reshape(1, -1))
            memory_id = len(self.metadata)
            entry = {
                "id": memory_id,
                "text": text,
                "category": category,
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {},
            }
            working_metadata = self.metadata + [entry]
            self._persist_verified_pair(working_index, working_metadata)
            self.index = working_index
            self.metadata = working_metadata
            logger.debug("Added verified local memory vector %s", memory_id)
            return memory_id
        except Exception:
            self.degraded = True
            self.rebuild_pending = True
            self._set_rebuild_status("failed", "vector_add_persistence_failed")
            logger.warning("Vector add unavailable; original data preserved or quarantined")
            return None

    def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            threshold: Similarity threshold (lower = more strict)
            category: Optional category filter
            
        Returns:
            List of matching memories with similarity scores
        """
        try:
            from .memory_noise import is_embedding_entirely_skipped

            if is_embedding_entirely_skipped(query):
                return []
        except Exception:
            pass

        self.load_if_needed()
        if (not self.vector_pair_verified or not self._verify_disk_pair()
                or (self.metadata and not os.path.isfile(self.generation_path))):
            self._quarantine_pair("vector_search_unverified_generation")
            return []
        if self.index is None or len(self.metadata) == 0:
            return []
        try:
            if int(self.index.ntotal) != len(self.metadata):
                self._quarantine_pair("vector_search_row_mismatch")
                return []
        except (AttributeError, ValueError, TypeError):
            self._quarantine_pair("vector_search_index_unreadable")
            return []

        # Generate query embedding
        query_embedding = self.generate_embedding(query)
        if query_embedding is None:
            logger.warning("Failed to generate query embedding")
            return []
            
        # Reshape for FAISS
        query_embedding = query_embedding.reshape(1, -1)
        
        # Search
        try:
            k = min(limit * 2, len(self.metadata))  # Get more results for filtering
            distances, indices = self.index.search(query_embedding, k)
            
            results = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < 0 or idx >= len(self.metadata):
                    continue
                    
                memory = self.metadata[idx]
                
                # Filter by category if specified
                if category and memory.get("category") != category:
                    continue
                    
                # Convert distance to similarity (L2 distance, lower is better)
                # Normalize to 0-1 similarity score
                similarity = 1.0 / (1.0 + distance)
                
                if similarity >= threshold:
                    result = memory.copy()
                    result["similarity"] = float(similarity)
                    result["distance"] = float(distance)
                    results.append(result)
                    
                if len(results) >= limit:
                    break
                    
            # Sort by similarity (highest first)
            results.sort(key=lambda x: x["similarity"], reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
            
    def get_by_id(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get memory by ID."""
        self.load_if_needed()
        if not self.vector_pair_verified or not self._verify_disk_pair():
            self._quarantine_pair("vector_get_by_id_unverified")
            return None
        if 0 <= memory_id < len(self.metadata):
            return self.metadata[memory_id].copy()
        return None
        
    def get_stats(self) -> Dict[str, Any]:
        """Get vector memory statistics."""
        if not self.loaded and FAISS_AVAILABLE and self._lazy:
            return {
                "embedding_status": dict(self.embedding_status),
                "vector_memory_enabled": True,
                "vector_loaded": False,
                "total_memories": 0,
                "index_size": 0,
            }
        if self.index is None:
            return {
                "embedding_status": dict(self.embedding_status),
                "vector_memory_enabled": False,
                "vector_loaded": True,
                "total_memories": 0,
                "index_size": 0
            }
            
        categories = {}
        for memory in self.metadata:
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            
        return {
            "embedding_status": dict(self.embedding_status),
            "vector_pair_verified": self.vector_pair_verified,
            "vector_memory_enabled": True,
            "vector_loaded": True,
            "total_memories": len(self.metadata),
            "index_size": self.index.ntotal,
            "vector_dimension": self.vector_dim,
            "categories": categories,
            "embedding_model": self.embedding_model
        }
        
    def clear(self):
        """Clear all vector memories."""
        self.load_if_needed()
        if FAISS_AVAILABLE and self.index is not None:
            # Create new empty index
            self.index = faiss.IndexFlatL2(self.vector_dim)
        # Preserve pair-level integrity even for explicit vector clearing.
        # Never clobber an unverified legacy collection.
        self._persist_verified_pair(self.index, [])
        self.metadata = []
        logger.info("Vector memory cleared")


class EnhancedMemoryCore:
    """
    Enhanced MemoryCore that combines JSON storage with vector search.
    Provides both exact keyword matching and semantic similarity search.
    """
    
    def __init__(
        self,
        json_filepath: str = "guardian_memory.json",
        enable_vector: bool = True,
        vector_config: Optional[Dict[str, Any]] = None,
        timeline_memory=None,
        lazy_json: bool = False,
        lazy_vector: bool = False,
    ):
        from .memory import MemoryCore
        
        # Keep existing JSON-based memory
        self.json_memory = MemoryCore(
            json_filepath,
            timeline_memory=timeline_memory,
            lazy_load=lazy_json,
        )
        
        # Add vector memory if enabled and available
        self.vector_memory: Optional[VectorMemory] = None
        if enable_vector and FAISS_AVAILABLE:
            config = vector_config or {}
            self.vector_memory = VectorMemory(
                vector_dim=config.get("vector_dim", 1536),
                index_path=config.get("index_path", "memory/vectors/index.faiss"),
                metadata_path=config.get("metadata_path", "memory/vectors/metadata.json"),
                embedding_model=config.get("embedding_model", "text-embedding-ada-002"),
                lazy=lazy_vector,
            )
            logger.info("Enhanced memory with vector search enabled")
        else:
            if not FAISS_AVAILABLE:
                logger.warning("Vector memory disabled: FAISS not available")
            else:
                logger.info("Vector memory disabled by configuration")

    def load_if_needed(self) -> None:
        """Load JSON history and FAISS/metadata once (idempotent)."""
        self.json_memory.load_if_needed()
        if self.vector_memory:
            self.vector_memory.load_if_needed()

    def is_loaded(self) -> bool:
        """True when JSON history has been loaded (vector may still be lazy)."""
        return self.json_memory.is_loaded()

    def get_memory_count(self, load_if_needed: bool = False) -> Optional[int]:
        """Authoritative JSON memory count; None if unloaded and not forcing load."""
        return self.json_memory.get_memory_count(load_if_needed)

    def get_memory_state(self, load_if_needed: bool = False) -> Dict[str, Any]:
        """Combined JSON + vector load state for status APIs."""
        st = dict(self.json_memory.get_memory_state(load_if_needed))
        if self.vector_memory:
            if load_if_needed:
                self.vector_memory.load_if_needed()
            st["embedding_status"] = dict(self.vector_memory.embedding_status)
            st["vector_loaded"] = bool(self.vector_memory.loaded)
            if self.vector_memory.loaded and self.vector_memory.index is not None:
                try:
                    st["vector_memory_count"] = int(self.vector_memory.index.ntotal)
                except Exception:
                    st["vector_memory_count"] = len(self.vector_memory.metadata or [])
                st["vector_count_authoritative"] = True
            else:
                st["vector_memory_count"] = None
                st["vector_count_authoritative"] = False
        else:
            st["vector_loaded"] = True
            st["vector_memory_count"] = None
            st["vector_count_authoritative"] = True
        return st

    def consolidate(
        self,
        max_memories: int = 4000,
        keep_recent_days: int = 30
    ) -> Dict[str, Any]:
        """
        Consolidate both JSON and vector memory using the authoritative cleanup path.
        """
        self.load_if_needed()
        from .memory_cleanup import MemoryCleanup
        cleanup = MemoryCleanup(self)
        return cleanup.consolidate_memories(max_memories=max_memories, keep_recent_days=keep_recent_days)
                
    def remember(
        self,
        thought: str,
        category: str = "general",
        priority: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store a memory in both JSON and vector storage.
        
        Args:
            thought: Memory text
            category: Memory category
            priority: Priority level
            metadata: Additional metadata
        """
        try:
            from .startup_runtime_guard import should_skip_nonessential_remember

            if should_skip_nonessential_remember(category, float(priority or 0), thought or ""):
                logger.debug("EnhancedMemoryCore.remember skipped (startup memory-thin mode)")
                return
        except Exception:
            pass
        # Store in JSON (existing functionality)
        self.json_memory.remember(thought, category, priority)
        
        # Store in vector memory if available
        if self.vector_memory:
            self.vector_memory.add_memory(
                text=thought,
                category=category,
                priority=priority,
                metadata=metadata
            )
            
    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic similarity search using vector embeddings.
        
        Args:
            query: Search query
            limit: Maximum results
            threshold: Similarity threshold
            category: Optional category filter
            
        Returns:
            List of similar memories
        """
        self.load_if_needed()
        if self.vector_memory:
            results = self.vector_memory.search(query, limit, threshold, category)
            if results:
                return results
            if self.vector_memory.embedding_status.get("available", False):
                return []
        # The authoritative JSON remains useful when embedding is unavailable.
        # Keyword results are not labeled as vector/semantic matches.
        return [
            row for row in self.json_memory.search_memories(query, limit)
            if category is None or row.get("category") == category
        ][:limit]
            
    def search_memories(
        self,
        query: str,
        limit: int = 10,
        use_semantic: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search memories (semantic or keyword).
        
        Args:
            query: Search query
            limit: Maximum results
            use_semantic: If True, use semantic search (if available)
            
        Returns:
            List of matching memories
        """
        self.load_if_needed()
        if use_semantic and self.vector_memory:
            return self.semantic_search(query, limit)
        else:
            return self.json_memory.search_memories(query, limit)
            
    def recall_last(self, count: int = 1, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve most recent memories."""
        self.json_memory.load_if_needed()
        return self.json_memory.recall_last(count, category)
        
    def get_memories_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all memories in a category."""
        self.json_memory.load_if_needed()
        return self.json_memory.get_memories_by_category(category)

    def get_recent_memories(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        load_if_needed: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get most recent memories. Safe for UI/routes."""
        return self.json_memory.get_recent_memories(limit, category, load_if_needed)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get combined memory statistics."""
        json_stats = self.json_memory.get_memory_stats()
        
        if self.vector_memory:
            vector_stats = self.vector_memory.get_stats()
            json_stats.update(vector_stats)
        else:
            json_stats["vector_memory_enabled"] = False
        json_stats.update(self.get_memory_state(load_if_needed=False))
        return json_stats
        
    def dump_all(self) -> List[Dict[str, Any]]:
        """Get all memories."""
        self.json_memory.load_if_needed()
        return self.json_memory.dump_all()
        
    def forget(self) -> None:
        """Clear all memories."""
        self.json_memory.forget()
        if self.vector_memory:
            self.vector_memory.clear()
    
    @property
    def memory_log(self) -> List[Dict[str, Any]]:
        """Access to underlying memory_log for compatibility."""
        return self.json_memory.memory_log
    
    def cleanup_old_memories(self, days: int = 90, min_priority_to_keep: float = 0.7) -> Dict[str, Any]:
        """
        Cleanup old memories by delegating to json_memory.
        
        Args:
            days: Memories older than this will be removed
            min_priority_to_keep: Minimum priority for old memories to be retained
            
        Returns:
            Dictionary with cleanup statistics
        """
        return self.json_memory.cleanup_old_memories(days=days, min_priority_to_keep=min_priority_to_keep)

