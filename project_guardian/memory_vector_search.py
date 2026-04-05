# project_guardian/memory_vector_search.py
# Memory Vector Search: Semantic Memory Retrieval
# Adds vector search capabilities to MemoryCore for better context retrieval

import logging
import json
import threading
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

_ST_SHARED = None
_ST_SHARED_NAME: Optional[str] = None
_ST_LOCK = threading.Lock()

# Try to import vector search libraries (optional dependencies)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("NumPy not available, vector search features will be limited")

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    SentenceTransformer = None  # type: ignore
    logger.warning(
        "sentence-transformers not available, using fallback embedding. "
        "For better embeddings: pip install -r requirements-optional.txt"
    )


def _shared_sentence_transformer(model_name: str):
    global _ST_SHARED, _ST_SHARED_NAME
    if not HAS_SENTENCE_TRANSFORMERS or SentenceTransformer is None:
        raise RuntimeError("sentence_transformers unavailable")
    with _ST_LOCK:
        if _ST_SHARED is not None and _ST_SHARED_NAME == model_name:
            return _ST_SHARED
        inst = SentenceTransformer(model_name)
        _ST_SHARED = inst
        _ST_SHARED_NAME = model_name
        logger.info("Loaded shared SentenceTransformer: %s", model_name)
        return _ST_SHARED

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("FAISS not available, using in-memory vector storage")

# Fallback embedding model (simple TF-IDF-like approach)
class SimpleEmbedder:
    """Simple fallback embedder when sentence-transformers unavailable."""
    
    def __init__(self):
        self.vocab = {}
        self.idf = {}
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        return text.lower().split()
    
    def _build_vocab(self, texts: List[str]):
        """Build vocabulary from texts."""
        from collections import Counter
        
        doc_counts = {}
        for text in texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                doc_counts[token] = doc_counts.get(token, 0) + 1
        
        # Calculate IDF
        total_docs = len(texts)
        for token, count in doc_counts.items():
            self.idf[token] = np.log(total_docs / (count + 1))
    
    def embed(self, text: str, dimension: int = 384) -> np.ndarray:
        """Simple embedding using word frequencies."""
        if not HAS_NUMPY:
            # Fallback to hash-based embedding
            return self._hash_embed(text, dimension)
        
        tokens = self._tokenize(text)
        embedding = np.zeros(dimension)
        
        for i, token in enumerate(tokens[:dimension]):
            # Simple hash-based position embedding
            hash_val = int(hashlib.md5(token.encode()).hexdigest(), 16)
            embedding[i % dimension] += hash_val % 1000 / 1000.0
        
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
    
    def _hash_embed(self, text: str, dimension: int) -> List[float]:
        """Hash-based embedding fallback."""
        hash_obj = hashlib.sha256(text.encode())
        hex_str = hash_obj.hexdigest()
        
        embedding = []
        for i in range(0, len(hex_str), 2):
            if len(embedding) >= dimension:
                break
            val = int(hex_str[i:i+2], 16) / 255.0
            embedding.append(val)
        
        # Pad if needed
        while len(embedding) < dimension:
            embedding.append(0.0)
        
        return embedding[:dimension]


class MemoryVectorSearch:
    """
    Vector search layer for MemoryCore.
    Provides semantic similarity search for memories.
    """
    
    def __init__(
        self,
        embedding_dimension: int = 384,
        use_faiss: bool = None,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize vector search.
        
        Args:
            embedding_dimension: Dimension of embeddings
            use_faiss: Use FAISS if available (auto-detect if None)
            model_name: Sentence transformer model name
        """
        self.embedding_dimension = embedding_dimension
        
        # Initialize embedder
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.embedder = _shared_sentence_transformer(model_name)
                self.embedding_dimension = self.embedder.get_sentence_embedding_dimension()
                logger.info(f"Using SentenceTransformer model: {model_name} (shared instance)")
            except Exception as e:
                logger.warning(f"Failed to load SentenceTransformer: {e}, using fallback")
                self.embedder = SimpleEmbedder()
        else:
            self.embedder = SimpleEmbedder()
        
        # Vector storage
        self.use_faiss = use_faiss if use_faiss is not None else HAS_FAISS
        
        if self.use_faiss and HAS_FAISS and HAS_NUMPY:
            # Initialize FAISS index
            self.index = faiss.IndexFlatL2(self.embedding_dimension)
            self.memory_id_to_index = {}  # Maps memory IDs to FAISS indices
            self.index_to_memory_id = {}  # Reverse mapping
            self._next_index = 0
            logger.info("Using FAISS for vector search")
        else:
            # In-memory storage
            self.vectors = {}  # memory_id -> embedding vector
            self.memory_texts = {}  # memory_id -> original text
            logger.info("Using in-memory vector storage")
        
        # Cache for embeddings
        self.embedding_cache = {}
    
    def add_memory(
        self,
        memory_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Add a memory to the vector index.
        
        Args:
            memory_id: Unique memory identifier
            text: Memory text to embed
            metadata: Optional metadata
        """
        try:
            from .memory_noise import is_low_value_memory_text

            if is_low_value_memory_text(text, min_chars_for_substantive=22):
                logger.debug("add_memory skipped (low-value / noise text)")
                return
        except Exception:
            pass
        # Generate embedding
        embedding = self._get_embedding(text)
        
        if self.use_faiss and HAS_FAISS and HAS_NUMPY:
            # Add to FAISS index
            embedding_array = np.array([embedding], dtype=np.float32)
            index_pos = self.index.ntotal
            self.index.add(embedding_array)
            self.memory_id_to_index[memory_id] = index_pos
            self.index_to_memory_id[index_pos] = memory_id
        else:
            # Store in memory
            self.vectors[memory_id] = embedding
            self.memory_texts[memory_id] = text
        
        # Cache embedding
        text_hash = hashlib.md5(text.encode()).hexdigest()
        self.embedding_cache[text_hash] = embedding
    
    def remove_memory(self, memory_id: str):
        """Remove a memory from the vector index."""
        if self.use_faiss and HAS_FAISS:
            # FAISS doesn't support removal, mark as invalid
            if memory_id in self.memory_id_to_index:
                index_pos = self.memory_id_to_index[memory_id]
                del self.memory_id_to_index[memory_id]
                del self.index_to_memory_id[index_pos]
        else:
            # Remove from in-memory storage
            if memory_id in self.vectors:
                del self.vectors[memory_id]
            if memory_id in self.memory_texts:
                del self.memory_texts[memory_id]
    
    def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.0
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Search for similar memories.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            threshold: Minimum similarity score
            
        Returns:
            List of (memory_id, similarity_score, metadata) tuples
        """
        # Get query embedding
        query_embedding = self._get_embedding(query)
        
        if self.use_faiss and HAS_FAISS and HAS_NUMPY:
            # Search using FAISS
            query_array = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.index.search(query_array, min(limit * 2, self.index.ntotal))
            
            results = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx == -1:  # Invalid index
                    continue
                
                memory_id = self.index_to_memory_id.get(idx)
                if not memory_id:
                    continue
                
                # Convert distance to similarity (1 / (1 + distance))
                similarity = 1.0 / (1.0 + float(distance))
                
                if similarity >= threshold:
                    results.append((
                        memory_id,
                        similarity,
                        {"distance": float(distance)}
                    ))
            
            return results[:limit]
        else:
            # Search in-memory vectors using cosine similarity
            if not HAS_NUMPY:
                # Fallback: simple text matching
                query_lower = query.lower()
                results = []
                for memory_id, text in self.memory_texts.items():
                    text_lower = text.lower()
                    # Simple overlap score
                    query_words = set(query_lower.split())
                    text_words = set(text_lower.split())
                    if query_words:
                        overlap = len(query_words & text_words) / len(query_words)
                        if overlap >= threshold:
                            results.append((memory_id, overlap, {}))
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]
            
            # Cosine similarity search
            query_vec = np.array(query_embedding)
            results = []
            
            for memory_id, vec in self.vectors.items():
                vec_array = np.array(vec)
                # Cosine similarity
                dot_product = np.dot(query_vec, vec_array)
                norm_query = np.linalg.norm(query_vec)
                norm_vec = np.linalg.norm(vec_array)
                
                if norm_query > 0 and norm_vec > 0:
                    similarity = dot_product / (norm_query * norm_vec)
                else:
                    similarity = 0.0
                
                if similarity >= threshold:
                    results.append((memory_id, float(similarity), {}))
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text (with caching).
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        # Check cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self.embedding_cache:
            return self.embedding_cache[text_hash]

        try:
            from .memory_noise import is_low_value_memory_text

            if is_low_value_memory_text(text, min_chars_for_substantive=22):
                embedding = SimpleEmbedder().embed(text, self.embedding_dimension)
                if HAS_NUMPY and hasattr(embedding, "tolist"):
                    embedding = embedding.tolist()
                elif HAS_NUMPY:
                    embedding = list(embedding)
                self.embedding_cache[text_hash] = embedding
                return embedding
        except Exception:
            pass

        # Generate embedding
        if HAS_SENTENCE_TRANSFORMERS and not isinstance(self.embedder, SimpleEmbedder):
            embedding = self.embedder.encode(text).tolist()
        else:
            if HAS_NUMPY:
                embedding = self.embedder.embed(text, self.embedding_dimension).tolist()
            else:
                embedding = self.embedder.embed(text, self.embedding_dimension)
        
        # Cache
        self.embedding_cache[text_hash] = embedding
        
        # Limit cache size
        if len(self.embedding_cache) > 1000:
            # Remove oldest entries (simple FIFO)
            keys = list(self.embedding_cache.keys())
            for key in keys[:100]:
                del self.embedding_cache[key]
        
        return embedding
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get vector search statistics."""
        if self.use_faiss and HAS_FAISS:
            index_size = self.index.ntotal
        else:
            index_size = len(self.vectors)
        
        return {
            "index_size": index_size,
            "embedding_dimension": self.embedding_dimension,
            "cache_size": len(self.embedding_cache),
            "using_faiss": self.use_faiss and HAS_FAISS,
            "using_sentence_transformers": HAS_SENTENCE_TRANSFORMERS,
            "has_numpy": HAS_NUMPY
        }


# Integration function for MemoryCore
def add_vector_search_to_memory_core(memory_core) -> MemoryVectorSearch:
    """
    Add vector search capabilities to an existing MemoryCore instance.
    
    Args:
        memory_core: MemoryCore instance
        
    Returns:
        MemoryVectorSearch instance
    """
    vector_search = MemoryVectorSearch()
    
    # BOOTSTRAP: full dump to index existing memories (one-time, intentional)
    all_memories = memory_core.dump_all()
    for i, memory in enumerate(all_memories):
        memory_id = f"memory_{i}_{memory.get('time', '')}"
        text = memory.get('thought', '')
        if text:
            vector_search.add_memory(memory_id, text, memory)
    
    logger.info(f"Indexed {len(all_memories)} memories for vector search")
    return vector_search

