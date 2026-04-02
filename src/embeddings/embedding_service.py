"""Embedding service for semantic search using FAISS and SentenceTransformers."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from src.config import settings
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore[name-defined]

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[name-defined]


class EmbeddingService:
    """Service for generating and searching embeddings using SentenceTransformers."""

    # SentenceTransformers model - all-MiniLM-L6-v2 is small (22MB) and fast
    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 produces 384-dim vectors

    def __init__(self, symbol_index: SymbolIndex, cache_dir: Optional[Path] = None):
        """Initialize embedding service.

        Args:
            symbol_index: Symbol index for embeddings
            cache_dir: Directory for caching embeddings (defaults to data_dir)
        """
        self.symbol_index = symbol_index
        self.cache_dir = cache_dir or settings.DATA_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize SentenceTransformer model
        self.embedding_model = None
        if SentenceTransformer:
            try:
                self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info(f"Loaded embedding model: {settings.EMBEDDING_MODEL}")
            except Exception as e:
                logger.error(f"Failed to load embedding model {settings.EMBEDDING_MODEL}: {e}")
        else:
            logger.warning("SentenceTransformers not installed. Install with: pip install sentence-transformers")

        # Initialize FAISS index
        self.index: Optional[faiss.IndexFlatL2] = None
        self.id_to_symbol: Dict[int, Symbol] = {}
        self.embedding_cache: Dict[str, List[float]] = {}

        # Load cache if it exists
        self._load_embedding_cache()

    def embed_symbol(self, symbol: Symbol) -> Optional[List[float]]:
        """Generate embedding for a symbol.

        Args:
            symbol: Symbol to embed

        Returns:
            Embedding vector or None if generation fails
        """
        # Check cache first
        cache_key = f"{symbol.node_id}"
        if cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]

        # Generate embedding text
        text = self._prepare_text_for_embedding(symbol)

        if not self.embedding_model:
            logger.warning(f"Cannot embed {symbol.name}: embedding model not loaded")
            return None

        try:
            embeddings = self.embedding_model.encode([text], convert_to_numpy=True)
            embedding = embeddings[0].tolist()
            self.embedding_cache[cache_key] = embedding
            logger.debug(f"Embedded {symbol.name}: {len(embedding)} dims")
            return embedding
        except Exception as e:
            logger.error(f"Failed to embed {symbol.name}: {e}")
            return None

    def build_index(self, symbols: Optional[List[Symbol]] = None) -> None:
        """Build FAISS index from symbols.

        Args:
            symbols: Symbols to index (defaults to all in symbol_index)
        """
        if not faiss:
            logger.error("FAISS not installed. Install with: pip install faiss-cpu")
            return

        symbols = symbols or self.symbol_index.get_all()

        if not symbols:
            logger.warning("No symbols to index")
            return

        # Create index
        self.index = faiss.IndexFlatL2(self.EMBEDDING_DIM)
        self.id_to_symbol = {}

        embeddings_to_add = []
        symbol_ids = []

        for idx, symbol in enumerate(symbols):
            embedding = self.embed_symbol(symbol)
            if embedding:
                embeddings_to_add.append(embedding)
                self.id_to_symbol[idx] = symbol
                symbol_ids.append(idx)

        if not embeddings_to_add:
            logger.warning("No embeddings generated. Check OpenAI API key and network.")
            return

        # Add to FAISS index
        embeddings_array = np.array(embeddings_to_add, dtype=np.float32)
        self.index.add(embeddings_array)
        logger.info(f"Built FAISS index with {len(embeddings_to_add)} embeddings")

        # Save cache
        self._save_embedding_cache()

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Symbol, float]]:
        """Search for symbols using semantic similarity.

        Args:
            query: Query string
            top_k: Number of top results to return

        Returns:
            List of (symbol, similarity_score) tuples
        """
        if not self.index:
            logger.warning("FAISS index not built. Cannot search.")
            return []

        if not self.embedding_model:
            logger.warning("Embedding model not loaded. Using fallback search.")
            return self._fallback_search(query, top_k)

        # Embed query
        try:
            query_embeddings = self.embedding_model.encode([query], convert_to_numpy=True)
            query_embedding = query_embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return self._fallback_search(query, top_k)

        # Search FAISS index
        query_array = np.array([query_embedding], dtype=np.float32)
        distances, indices = self.index.search(query_array, top_k)

        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx in self.id_to_symbol:
                symbol = self.id_to_symbol[idx]
                # Convert L2 distance to similarity (inverse relationship)
                similarity = 1.0 / (1.0 + distance)
                results.append((symbol, float(similarity)))

        logger.info(f"Semantic search for '{query}': {len(results)} results")
        return results

    def _prepare_text_for_embedding(self, symbol: Symbol) -> str:
        """Prepare text for embedding.

        Args:
            symbol: Symbol to prepare text for

        Returns:
            Text to embed
        """
        parts = [symbol.name]

        if symbol.type:
            parts.append(f"type: {symbol.type}")

        if symbol.docstring:
            parts.append(symbol.docstring)

        if symbol.parent:
            parts.append(f"parent: {symbol.parent}")

        return " ".join(parts)

    def _fallback_search(self, query: str, top_k: int) -> List[Tuple[Symbol, float]]:
        """Fallback search using simple string matching.

        Args:
            query: Query string
            top_k: Number of results to return

        Returns:
            List of (symbol, similarity_score) tuples
        """
        results = []
        query_lower = query.lower()

        # Return empty results for empty query
        if not query_lower:
            return results

        for symbol in self.symbol_index.get_all():
            score = 0.0

            # Exact match in name
            if query_lower == symbol.name.lower():
                score = 1.0
            # Substring in name
            elif query_lower in symbol.name.lower():
                score = 0.8
            # Substring in docstring
            elif symbol.docstring and query_lower in symbol.docstring.lower():
                score = 0.5

            if score > 0:
                results.append((symbol, score))

        # Sort by score and return top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _load_embedding_cache(self) -> None:
        """Load embedding cache from disk."""
        cache_file = self.cache_dir / "embeddings_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    self.embedding_cache = json.load(f)
                logger.info(f"Loaded {len(self.embedding_cache)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")

    def _save_embedding_cache(self) -> None:
        """Save embedding cache to disk."""
        cache_file = self.cache_dir / "embeddings_cache.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self.embedding_cache, f)
            logger.info(f"Saved {len(self.embedding_cache)} embeddings to cache")
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding service statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "cached_embeddings": len(self.embedding_cache),
            "indexed_symbols": len(self.id_to_symbol),
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dim": self.EMBEDDING_DIM,
        }
