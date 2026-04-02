"""Comprehensive tests for embedding service."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

from src.embeddings.embedding_service import EmbeddingService
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func_a", type="function", file="test.py", line=1, column=0, docstring="Function A docs"))
    index.add(Symbol(name="func_b", type="function", file="test.py", line=10, column=0, docstring="Function B docs"))
    index.add(Symbol(name="ClassA", type="class", file="test.py", line=20, column=0, parent=None))
    return index


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestEmbeddingServiceInit:
    """Test embedding service initialization."""

    def test_init_with_cache_dir(self, symbol_index, temp_cache_dir):
        """Test initialization with custom cache directory."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        assert service.symbol_index is symbol_index
        assert service.cache_dir == temp_cache_dir
        assert service.embedding_cache == {}
        assert service.id_to_symbol == {}

    def test_init_with_embedding_model(self, symbol_index, temp_cache_dir):
        """Test initialization with embedding model."""
        with patch('src.embeddings.embedding_service.SentenceTransformer') as mock_model:
            service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

            mock_model.assert_called_once_with('all-MiniLM-L6-v2')

    def test_init_without_embedding_model(self, symbol_index, temp_cache_dir):
        """Test initialization without embedding model."""
        with patch('src.embeddings.embedding_service.SentenceTransformer', None):
            service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

            assert service.embedding_model is None


class TestEmbedSymbol:
    """Test embedding symbol generation."""

    def test_embed_symbol_from_cache(self, symbol_index, temp_cache_dir):
        """Test embedding retrieval from cache."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_by_name("func_a")[0]

        cached_embedding = [0.1, 0.2, 0.3]
        service.embedding_cache[f"{symbol.node_id}"] = cached_embedding

        result = service.embed_symbol(symbol)

        assert result == cached_embedding

    def test_embed_symbol_success(self, symbol_index, temp_cache_dir):
        """Test successful symbol embedding."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_by_name("func_a")[0]

        mock_embedding = np.array([[0.1] * 384], dtype=np.float32)
        with patch.object(service, 'embedding_model') as mock_model:
            mock_model.encode.return_value = mock_embedding

            result = service.embed_symbol(symbol)

            assert result == mock_embedding[0].tolist()

    def test_embed_symbol_no_embedding_model(self, symbol_index, temp_cache_dir):
        """Test embedding fails without embedding model."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.embedding_model = None
        symbol = symbol_index.get_by_name("func_a")[0]

        result = service.embed_symbol(symbol)

        assert result is None

    def test_embed_symbol_model_error(self, symbol_index, temp_cache_dir):
        """Test embedding fails on model error."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = symbol_index.get_by_name("func_a")[0]

        with patch.object(service, 'embedding_model') as mock_model:
            mock_model.encode.side_effect = Exception("Model Error")

            result = service.embed_symbol(symbol)

            assert result is None


class TestBuildIndex:
    """Test FAISS index building."""

    def test_build_index_no_faiss(self, symbol_index, temp_cache_dir):
        """Test build index when FAISS not available."""
        with patch('src.embeddings.embedding_service.faiss', None):
            service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
            service.build_index()

    def test_build_index_no_symbols(self, temp_cache_dir):
        """Test build index with empty symbol list."""
        empty_index = SymbolIndex()
        service = EmbeddingService(empty_index, cache_dir=temp_cache_dir)

        with patch('src.embeddings.embedding_service.faiss') as mock_faiss:
            service.build_index()

    def test_build_index_success(self, symbol_index, temp_cache_dir):
        """Test successful index building."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        mock_embedding = np.array([0.1] * 384, dtype=np.float32)

        with patch.object(service, 'embed_symbol', return_value=mock_embedding.tolist()):
            with patch('src.embeddings.embedding_service.faiss') as mock_faiss:
                mock_index = MagicMock()
                mock_faiss.IndexFlatL2.return_value = mock_index

                service.build_index()

                mock_faiss.IndexFlatL2.assert_called_once_with(384)


class TestSearch:
    """Test semantic search."""

    def test_search_no_index(self, symbol_index, temp_cache_dir):
        """Test search fails without index."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.index = None

        result = service.search("test query")

        assert result == []

    def test_search_no_embedding_model_fallback(self, symbol_index, temp_cache_dir):
        """Test search falls back without embedding model."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.index = MagicMock()
        service.embedding_model = None

        with patch.object(service, '_fallback_search', return_value=[]) as mock_fallback:
            result = service.search("test query")

            mock_fallback.assert_called_once_with("test query", 5)

    def test_search_model_error_fallback(self, symbol_index, temp_cache_dir):
        """Test search falls back on model error."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.index = MagicMock()

        with patch.object(service, 'embedding_model') as mock_model:
            mock_model.encode.side_effect = Exception("Model Error")

            with patch.object(service, '_fallback_search', return_value=[]) as mock_fallback:
                result = service.search("test query")

                mock_fallback.assert_called()

    def test_search_success(self, symbol_index, temp_cache_dir):
        """Test successful semantic search."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        service.index = MagicMock()
        symbol = symbol_index.get_by_name("func_a")[0]
        service.id_to_symbol = {0: symbol}

        with patch.object(service, 'embedding_model') as mock_model:
            mock_model.encode.return_value = np.array(
                [[0.1] * 384], dtype=np.float32
            )

            service.index.search.return_value = (
                np.array([[0.5]]),
                np.array([[0]])
            )

            result = service.search("test query", top_k=5)

            assert len(result) == 1
            assert result[0][0] == symbol
            assert 0 < result[0][1] < 1


class TestFallbackSearch:
    """Test fallback search functionality."""

    def test_fallback_empty_query(self, symbol_index, temp_cache_dir):
        """Test fallback search with empty query."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        result = service._fallback_search("", top_k=5)

        assert result == []

    def test_fallback_exact_match(self, symbol_index, temp_cache_dir):
        """Test fallback search with exact name match."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        result = service._fallback_search("func_a", top_k=5)

        assert len(result) > 0
        assert result[0][1] == 1.0

    def test_fallback_substring_match(self, symbol_index, temp_cache_dir):
        """Test fallback search with substring match."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        result = service._fallback_search("func", top_k=5)

        assert len(result) > 0
        assert result[0][1] == 0.8

    def test_fallback_docstring_match(self, symbol_index, temp_cache_dir):
        """Test fallback search matches docstring."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        result = service._fallback_search("docs", top_k=5)

        assert any(score == 0.5 for _, score in result)

    def test_fallback_respects_top_k(self, symbol_index, temp_cache_dir):
        """Test fallback search respects top_k limit."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        for i in range(10):
            symbol_index.add(Symbol(name=f"func_{i}", type="function", file="test.py", line=i, column=0))

        result = service._fallback_search("func", top_k=3)

        assert len(result) <= 3


class TestCacheOperations:
    """Test cache loading and saving."""

    def test_load_cache_success(self, symbol_index, temp_cache_dir):
        """Test successful cache loading."""
        cache_data = {"symbol_1": [0.1, 0.2], "symbol_2": [0.3, 0.4]}
        cache_file = temp_cache_dir / "embeddings_cache.json"
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        assert service.embedding_cache == cache_data

    def test_load_cache_file_not_found(self, symbol_index, temp_cache_dir):
        """Test cache loading when file doesn't exist."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        assert service.embedding_cache == {}

    def test_load_cache_corruption(self, symbol_index, temp_cache_dir):
        """Test cache loading with corrupted file."""
        cache_file = temp_cache_dir / "embeddings_cache.json"
        with open(cache_file, "w") as f:
            f.write("invalid json {{{")

        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)

        assert service.embedding_cache == {}

    def test_save_cache_success(self, symbol_index, temp_cache_dir):
        """Test successful cache saving."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.embedding_cache = {"symbol_1": [0.1, 0.2]}

        service._save_embedding_cache()

        cache_file = temp_cache_dir / "embeddings_cache.json"
        assert cache_file.exists()

        with open(cache_file) as f:
            data = json.load(f)
            assert data == {"symbol_1": [0.1, 0.2]}


class TestPrepareTextForEmbedding:
    """Test text preparation for embedding."""

    def test_prepare_text_basic(self, symbol_index, temp_cache_dir):
        """Test basic text preparation."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = Symbol(name="test_func", type="function", file="test.py", line=1, column=0)

        text = service._prepare_text_for_embedding(symbol)

        assert "test_func" in text
        assert "type: function" in text

    def test_prepare_text_with_docstring(self, symbol_index, temp_cache_dir):
        """Test text preparation with docstring."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = Symbol(
            name="test_func",
            type="function",
            file="test.py",
            line=1,
            column=0,
            docstring="This is a test function"
        )

        text = service._prepare_text_for_embedding(symbol)

        assert "test_func" in text
        assert "This is a test function" in text

    def test_prepare_text_with_parent(self, symbol_index, temp_cache_dir):
        """Test text preparation with parent class."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        symbol = Symbol(
            name="test_method",
            type="function",
            file="test.py",
            line=1,
            column=0,
            parent="TestClass"
        )

        text = service._prepare_text_for_embedding(symbol)

        assert "test_method" in text
        assert "parent: TestClass" in text


class TestGetStats:
    """Test statistics retrieval."""

    def test_get_stats(self, symbol_index, temp_cache_dir):
        """Test getting service statistics."""
        service = EmbeddingService(symbol_index, cache_dir=temp_cache_dir)
        service.embedding_cache = {"sym_1": [0.1], "sym_2": [0.2]}
        service.id_to_symbol = {0: MagicMock(), 1: MagicMock(), 2: MagicMock()}

        stats = service.get_stats()

        assert stats["cached_embeddings"] == 2
        assert stats["indexed_symbols"] == 3
        assert stats["embedding_model"] == "all-MiniLM-L6-v2"
        assert stats["embedding_dim"] == 384
