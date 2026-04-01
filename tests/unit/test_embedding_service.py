"""Unit tests for embedding service."""

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.embeddings.embedding_service import EmbeddingService
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create symbol index with test symbols."""
    index = SymbolIndex()
    index.add(
        Symbol(
            name="authenticate_user",
            type="function",
            file="src/auth.py",
            line=1,
            column=0,
            docstring="Authenticate user with credentials",
        )
    )
    index.add(
        Symbol(
            name="validate_password",
            type="function",
            file="src/auth.py",
            line=20,
            column=0,
            docstring="Validate password strength",
        )
    )
    index.add(
        Symbol(
            name="process_data",
            type="function",
            file="src/processor.py",
            line=1,
            column=0,
            docstring="Process incoming data stream",
        )
    )
    return index


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create temporary cache directory."""
    return tmp_path / "cache"


class TestEmbeddingService:
    """Test EmbeddingService class."""

    def test_initialization(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test service initialization."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        assert service.symbol_index is not None
        assert service.cache_dir == temp_cache_dir
        assert service.EMBEDDING_MODEL == "text-embedding-3-small"
        assert service.EMBEDDING_DIM == 1536

    def test_prepare_text_for_embedding(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test text preparation for embedding."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_all()[0]

        text = service._prepare_text_for_embedding(symbol)
        assert symbol.name in text
        assert symbol.type in text
        if symbol.docstring:
            assert symbol.docstring in text

    def test_fallback_search_exact_match(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test fallback search with exact match."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        results = service._fallback_search("authenticate_user", top_k=5)

        assert len(results) > 0
        assert results[0][0].name == "authenticate_user"
        # Exact match should have score 1.0
        assert results[0][1] == 1.0

    def test_fallback_search_substring_match(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test fallback search with substring match."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        results = service._fallback_search("password", top_k=5)

        assert len(results) > 0
        # Should find validate_password
        assert any(r[0].name == "validate_password" for r in results)

    def test_fallback_search_top_k(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test fallback search respects top_k parameter."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        results = service._fallback_search("", top_k=2)

        # With empty query, should return empty
        assert len(results) == 0

        results = service._fallback_search("a", top_k=2)
        # Should not exceed top_k
        assert len(results) <= 2

    def test_fallback_search_docstring(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test fallback search matches in docstring."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        results = service._fallback_search("authenticate", top_k=5)

        # Should find authenticate_user by docstring
        assert len(results) > 0

    def test_embedding_cache(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test embedding cache."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_all()[0]

        # Manual cache entry
        cache_key = symbol.node_id
        test_embedding = [0.1] * 1536
        service.embedding_cache[cache_key] = test_embedding

        # Should return cached embedding without calling OpenAI
        result = service.embed_symbol(symbol)
        assert result == test_embedding

    def test_get_stats(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test service statistics."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        stats = service.get_stats()
        assert "cached_embeddings" in stats
        assert "indexed_symbols" in stats
        assert "embedding_model" in stats
        assert "embedding_dim" in stats
        assert stats["embedding_model"] == "text-embedding-3-small"
        assert stats["embedding_dim"] == 1536


class TestEmbeddingIntegration:
    """Integration tests for embedding service."""

    @pytest.mark.skip(reason="Requires OpenAI API key")
    def test_embed_symbol_with_api(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test embedding with OpenAI API (requires API key)."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_all()[0]

        embedding = service.embed_symbol(symbol)
        assert embedding is not None
        assert len(embedding) == 1536

    @pytest.mark.skip(reason="Requires OpenAI API key")
    def test_build_index_with_api(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test building FAISS index with OpenAI embeddings."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.build_index()

        assert service.index is not None
        assert len(service.id_to_symbol) > 0

    @pytest.mark.skip(reason="Requires FAISS")
    def test_search_with_index(self, symbol_index: SymbolIndex, temp_cache_dir: Path) -> None:
        """Test semantic search with FAISS index."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        # Would need embeddings to be built first
        # results = service.search("authentication", top_k=3)
        # assert len(results) > 0
        pass
