# project_guardian/memory_vector.py
# Vector Memory System with FAISS Integration
# Enhances MemoryCore with semantic search capabilities

import os
import json
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
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("OpenAI not available. Embeddings will not work without API key.")

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
        self.embedding_model = embedding_model
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
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        
        if FAISS_AVAILABLE:
            if lazy:
                self.index = None
                self.metadata = []
                self.loaded = False
                logger.info("[Startup] VectorMemory FAISS/metadata load deferred (lazy=True)")
            else:
                self.index = self._init_index()
                self.metadata = []
                self._load_metadata()
                self.loaded = True
        else:
            self.index = None
            self.metadata = []
            self.loaded = True
            logger.warning("Vector memory initialized without FAISS - semantic search disabled")

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
            self.index = self._init_index()
            self.metadata = []
            self._load_metadata()
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
                emb = self.generate_embedding(text)
                if emb is None:
                    continue
                if emb.shape[0] != self.vector_dim:
                    continue
                emb = emb.reshape(1, -1)
                new_index.add(emb)
                new_metadata.append({
                    "id": i,
                    "text": text,
                    "category": mem.get("category", "general"),
                    "priority": mem.get("priority", 0.5),
                    "timestamp": mem.get("time"),
                    "metadata": mem.get("metadata", {}),
                })
            except Exception:
                # Skip problematic entries; continue with others
                continue

        try:
            # Persist using fsync-backed atomic writes to reduce torn-file risk.
            self._atomic_write_json(self.metadata_path, new_metadata)
            if FAISS_AVAILABLE:
                self._atomic_write_faiss(self.index_path, new_index)
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
            self.rebuild_pending = False

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
        """Persist metadata + index atomically-per-file in stable order."""
        # Write metadata first, then index. If index write fails, metadata remains authoritative
        # and startup rebuild logic can recover from mismatch.
        self._atomic_write_json(self.metadata_path, self.metadata)
        if FAISS_AVAILABLE and self.index is not None:
            self._atomic_write_faiss(self.index_path, self.index)
                
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for text using multi-provider fallback chain.
        
        Fallback order:
        1. OpenAI API (if API key available)
        2. Sentence-transformers (local, no API needed)
        3. Hash-based fallback (last resort, degraded quality)
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if all providers fail
        """
        try:
            from .memory_noise import is_embedding_entirely_skipped, is_low_value_memory_text

            if is_embedding_entirely_skipped(text):
                logger.debug("Embedding: skipped (non-vectorizable bookkeeping fragment)")
                return None
            if is_low_value_memory_text(text, min_chars_for_substantive=20):
                logger.debug("Embedding: low-value text skipped OpenAI/ST; using hash vector")
                return self._generate_hash_embedding(text)
        except Exception:
            pass
        try:
            from .openai_degraded import note_openai_transport_failure, skip_openai_embeddings
        except Exception:
            def skip_openai_embeddings() -> bool:
                return False

            def note_openai_transport_failure(_e, _c=""):
                return

        # Try OpenAI API first (highest quality)
        if OPENAI_AVAILABLE:
            try:
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key and not skip_openai_embeddings():
                    client = openai.OpenAI(api_key=api_key)
                    response = client.embeddings.create(
                        model=self.embedding_model,
                        input=text
                    )
                    embedding = np.array(response.data[0].embedding, dtype=np.float32)
                    logger.debug(f"Generated embedding using OpenAI API")
                    try:
                        from .openai_degraded import note_openai_embedding_success_clear_streak

                        note_openai_embedding_success_clear_streak()
                    except Exception:
                        pass
                    return embedding
            except Exception as e:
                note_openai_transport_failure(e, "vector_openai_embed")
                logger.debug("OpenAI embedding failed (fallback=reason:openai_error): %s", e)
        
        # Fallback to sentence-transformers (local, no API needed)
        if HAS_SENTENCE_TRANSFORMERS and not self._st_local_model_broken:
            try:
                try:
                    from .startup_runtime_guard import defer_sentence_transformers_for_embed

                    if defer_sentence_transformers_for_embed():
                        return self._generate_hash_embedding(text)
                except Exception:
                    pass
                # Lazy-load model (only load once; deferred until after boot / first real need)
                if self._sentence_transformer_model is None:
                    # Use a lightweight model that doesn't require GPU
                    logger.info("Loading sentence-transformers model for embedding fallback...")
                    try:
                        self._sentence_transformer_model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dimensions
                    except Exception as load_e:
                        self._st_local_model_broken = True
                        if not self._st_load_failure_logged:
                            self._st_load_failure_logged = True
                            logger.warning(
                                "Sentence-transformers load failed; local ST disabled for this process: %s",
                                load_e,
                            )
                        return self._generate_hash_embedding(text)

                model = self._sentence_transformer_model
                try:
                    embedding = model.encode(text)
                except Exception as enc_e:
                    self._st_local_model_broken = True
                    if not self._st_load_failure_logged:
                        self._st_load_failure_logged = True
                        logger.warning(
                            "Sentence-transformers encode failed; local ST disabled for this process: %s",
                            enc_e,
                        )
                    else:
                        logger.debug("ST encode skipped (local model disabled): %s", enc_e)
                    return self._generate_hash_embedding(text)
                # Resize to match expected dimension if needed
                if len(embedding) != self.vector_dim:
                    # Simple truncation or padding (not ideal, but works)
                    if len(embedding) > self.vector_dim:
                        embedding = embedding[:self.vector_dim]
                    else:
                        padding = np.zeros(self.vector_dim - len(embedding))
                        embedding = np.concatenate([embedding, padding])
                embedding = np.array(embedding, dtype=np.float32)
                logger.info("Embedding fallback: method=sentence_transformers reason=openai_failed_or_unavailable")
                return embedding
            except Exception as e:
                self._st_local_model_broken = True
                if not self._st_load_failure_logged:
                    self._st_load_failure_logged = True
                    logger.warning(
                        "Sentence-transformers path failed; local ST disabled for this process: %s",
                        e,
                    )
                logger.debug("Sentence-transformers failed (fallback=reason:local_model_error): %s", e)
        
        # Last resort: hash-based fallback (degraded quality, but always works)
        try:
            embedding = self._generate_hash_embedding(text)
            try:
                from .memory_noise import is_low_value_memory_text

                _quiet = is_low_value_memory_text(text, min_chars_for_substantive=20)
            except Exception:
                _quiet = False
            _sample = (text[:50] + "...") if len(text) > 50 else text
            if _quiet or self._st_local_model_broken:
                logger.debug(
                    "Embedding fallback: method=hash_based reason=degraded_or_low_value text_sample=%s",
                    _sample,
                )
            else:
                logger.warning(
                    "Embedding fallback: method=hash_based reason=openai_unavailable_and_local_model_failed text_sample=%s",
                    _sample,
                )
            return embedding
        except Exception as e:
            logger.error(f"All embedding providers failed, including hash fallback: {e}")
            return None
    
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
        if self.index is None:
            logger.warning("FAISS index not available")
            return None
            
        # Generate embedding if not provided
        if embedding is None:
            embedding = self.generate_embedding(text)
            if embedding is None:
                try:
                    from .memory_noise import is_embedding_entirely_skipped

                    if is_embedding_entirely_skipped(text):
                        logger.debug("No vector row (embedding intentionally skipped for fragment)")
                        return None
                except Exception:
                    pass
                logger.warning("Failed to generate embedding, memory not stored")
                return None
                
        # Ensure embedding is correct dimension
        if embedding.shape[0] != self.vector_dim:
            logger.error(f"Embedding dimension mismatch: {embedding.shape[0]} != {self.vector_dim}")
            return None
            
        # Reshape for FAISS (needs to be 2D)
        embedding = embedding.reshape(1, -1)
        
        # Add to index
        try:
            self.index.add(embedding)
            memory_id = len(self.metadata)
            
            # Store metadata
            memory_entry = {
                "id": memory_id,
                "text": text,
                "category": category,
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            self.metadata.append(memory_entry)
            
            # Save (atomic writes to reduce startup corruption risk)
            self._persist_vector_state()
            
            logger.debug(f"Added memory {memory_id} to vector store")
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to add memory to index: {e}")
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
        if self.index is None or len(self.metadata) == 0:
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
        if 0 <= memory_id < len(self.metadata):
            return self.metadata[memory_id].copy()
        return None
        
    def get_stats(self) -> Dict[str, Any]:
        """Get vector memory statistics."""
        if not self.loaded and FAISS_AVAILABLE and self._lazy:
            return {
                "vector_memory_enabled": True,
                "vector_loaded": False,
                "total_memories": 0,
                "index_size": 0,
            }
        if self.index is None:
            return {
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
        self.metadata = []
        self._save_metadata()
        self._save_index()
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
            return self.vector_memory.search(query, limit, threshold, category)
        else:
            # Fallback to keyword search
            logger.warning("Vector memory not available, using keyword search")
            return self.json_memory.search_memories(query, limit)
            
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

