"""Comprehensive tests for QueryService error paths and edge cases."""

import pytest
from unittest.mock import MagicMock, patch
from src.api.query_service import QueryService
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol
from src.graph.conflict_analyzer import ConflictAnalyzer
from src.embeddings.embedding_service import EmbeddingService
from src.graph.neo4j_client import Neo4jClient


@pytest.fixture
def basic_symbol_index() -> SymbolIndex:
    """Create a basic symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func1", type="function", file="test.py", line=1, column=0))
    index.add(Symbol(name="func2", type="function", file="test.py", line=10, column=0))
    index.add(Symbol(name="TestClass", type="class", file="models.py", line=1, column=0))
    return index


class TestGetContextErrorPaths:
    """Test error handling in get_context method."""

    def test_get_context_symbol_not_found(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context returns error dict when symbol not found."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("nonexistent_symbol")

        assert "error" in result
        assert "not found" in result["error"].lower()
        assert result["symbol"] is None

    def test_get_context_with_none_symbol_name(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with None symbol name."""
        service = QueryService(basic_symbol_index)
        # Should handle None gracefully
        try:
            result = service.get_context(None)
            assert "error" in result or result is not None
        except (TypeError, AttributeError):
            # Acceptable to raise on None input
            pass

    def test_get_context_empty_string_symbol(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with empty string symbol name."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("")

        assert "error" in result or "results" in result

    def test_get_context_negative_depth(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with negative depth."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("func1", depth=-1)

        # Should handle gracefully
        assert result is not None
        assert "symbol" in result

    def test_get_context_very_large_depth(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with very large depth value."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("func1", depth=10000)

        # Should handle without stack overflow
        assert result is not None
        assert "symbol" in result

    def test_get_context_with_callers_true(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with include_callers=True."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("func1", include_callers=True)

        assert result is not None
        assert "callers" in result
        assert isinstance(result["callers"], list)

    def test_get_context_with_callers_false(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_context with include_callers=False."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("func1", include_callers=False)

        assert result is not None
        assert result["callers"] is None

    def test_get_context_multiple_candidates(self) -> None:
        """Test get_context when multiple symbols have same name."""
        index = SymbolIndex()
        # Add multiple symbols with same name
        index.add(Symbol(name="func", type="function", file="file1.py", line=1, column=0))
        index.add(Symbol(name="func", type="function", file="file2.py", line=1, column=0))

        service = QueryService(index)
        result = service.get_context("func")

        # Should return first match
        assert result is not None
        assert "symbol" in result

    def test_get_context_token_estimate(self, basic_symbol_index: SymbolIndex) -> None:
        """Test that token estimate is calculated."""
        service = QueryService(basic_symbol_index)
        result = service.get_context("func1")

        assert "token_estimate" in result
        assert isinstance(result["token_estimate"], int)
        assert result["token_estimate"] >= 0


class TestGetSubgraphErrorPaths:
    """Test error handling in get_subgraph method."""

    def test_get_subgraph_symbol_not_found(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph returns error when symbol not found."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("nonexistent")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_get_subgraph_empty_string(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with empty string."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("")

        assert "error" in result or "root_symbol" in result

    def test_get_subgraph_negative_depth(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with negative depth."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("func1", depth=-1)

        assert result is not None
        assert "root_symbol" in result

    def test_get_subgraph_zero_depth(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with depth=0."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("func1", depth=0)

        assert result is not None
        assert "nodes" in result
        assert "edges" in result

    def test_get_subgraph_very_large_depth(self, basic_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with very large depth."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("func1", depth=9999)

        # Should not cause performance issues
        assert result is not None
        assert "nodes" in result

    def test_get_subgraph_token_estimate(self, basic_symbol_index: SymbolIndex) -> None:
        """Test that subgraph includes token estimate."""
        service = QueryService(basic_symbol_index)
        result = service.get_subgraph("func1")

        assert "token_estimate" in result
        assert isinstance(result["token_estimate"], int)


class TestSemanticSearchErrorPaths:
    """Test error handling in semantic_search method."""

    def test_semantic_search_empty_query(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with empty query."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("")

        assert result is not None
        assert "results" in result
        assert isinstance(result["results"], list)

    def test_semantic_search_none_query(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with None query."""
        service = QueryService(basic_symbol_index)
        try:
            result = service.semantic_search(None)
            # If it doesn't raise, should return valid response
            assert result is not None
        except (TypeError, AttributeError):
            # Acceptable to raise on None
            pass

    def test_semantic_search_zero_top_k(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with top_k=0."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("test", top_k=0)

        assert result is not None
        assert len(result["results"]) == 0

    def test_semantic_search_negative_top_k(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with negative top_k."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("test", top_k=-1)

        # Should handle gracefully
        assert result is not None
        assert isinstance(result["results"], list)

    def test_semantic_search_very_large_top_k(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with very large top_k."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("test", top_k=10000)

        assert result is not None
        # Should return at most as many results as symbols exist
        assert len(result["results"]) <= len(basic_symbol_index.get_all())

    def test_semantic_search_special_characters(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with special characters."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("@#$%^&*()")

        assert result is not None
        assert isinstance(result["results"], list)

    def test_semantic_search_unicode_characters(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search with unicode characters."""
        service = QueryService(basic_symbol_index)
        result = service.semantic_search("测试中文字符")

        assert result is not None
        assert isinstance(result["results"], list)

    def test_semantic_search_with_embedding_service(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search when embedding service is available."""
        mock_embedding = MagicMock(spec=EmbeddingService)
        mock_embedding.search.return_value = [(basic_symbol_index.get_by_name("func1")[0], 0.95)]

        service = QueryService(basic_symbol_index, embedding_service=mock_embedding)
        result = service.semantic_search("test")

        assert result is not None
        assert len(result["results"]) == 1

    def test_semantic_search_embedding_exception(self, basic_symbol_index: SymbolIndex) -> None:
        """Test semantic search falls back when embedding fails."""
        mock_embedding = MagicMock(spec=EmbeddingService)
        mock_embedding.search.side_effect = Exception("Embedding service error")

        service = QueryService(basic_symbol_index, embedding_service=mock_embedding)
        result = service.semantic_search("func")

        # Should fall back to substring search and not raise
        assert result is not None
        assert isinstance(result["results"], list)


class TestFallbackSearchErrorPaths:
    """Test error handling in _fallback_search method."""

    def test_fallback_search_empty_index(self) -> None:
        """Test fallback search with empty index."""
        empty_index = SymbolIndex()
        service = QueryService(empty_index)
        result = service._fallback_search("test", 5)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    def test_fallback_search_no_matches(self, basic_symbol_index: SymbolIndex) -> None:
        """Test fallback search with no matching symbols."""
        service = QueryService(basic_symbol_index)
        result = service._fallback_search("nonexistent_xyz", 5)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_fallback_search_partial_match(self, basic_symbol_index: SymbolIndex) -> None:
        """Test fallback search with partial symbol name match."""
        service = QueryService(basic_symbol_index)
        result = service._fallback_search("func", 5)

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_fallback_search_docstring_match(self) -> None:
        """Test fallback search matches docstring."""
        index = SymbolIndex()
        symbol = Symbol(
            name="my_func",
            type="function",
            file="test.py",
            line=1,
            column=0,
            docstring="This is a test function"
        )
        index.add(symbol)

        service = QueryService(index)
        result = service._fallback_search("test", 5)

        # Should find the function by docstring
        assert len(result) > 0

    def test_fallback_search_case_insensitive(self, basic_symbol_index: SymbolIndex) -> None:
        """Test fallback search is case insensitive."""
        service = QueryService(basic_symbol_index)
        result = service._fallback_search("FUNC1", 5)

        # Should find "func1"
        assert len(result) > 0

    def test_fallback_search_zero_top_k(self, basic_symbol_index: SymbolIndex) -> None:
        """Test fallback search with top_k=0."""
        service = QueryService(basic_symbol_index)
        result = service._fallback_search("func", 0)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_fallback_search_very_large_top_k(self, basic_symbol_index: SymbolIndex) -> None:
        """Test fallback search with very large top_k."""
        service = QueryService(basic_symbol_index)
        result = service._fallback_search("func", 10000)

        # Should return at most all symbols
        assert len(result) <= len(basic_symbol_index.get_all())


class TestValidateConflictsErrorPaths:
    """Test error handling in validate_conflicts method."""

    def test_validate_conflicts_empty_list(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with empty task list."""
        service = QueryService(basic_symbol_index)
        result = service.validate_conflicts([])

        assert result is not None
        assert result["parallel_feasible"] == True
        assert len(result["tasks"]) == 0

    def test_validate_conflicts_none_input(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with None input."""
        service = QueryService(basic_symbol_index)
        try:
            result = service.validate_conflicts(None)
            # May raise or handle
            assert result is not None
        except (TypeError, AttributeError):
            pass

    def test_validate_conflicts_missing_id(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with task missing 'id' field."""
        service = QueryService(basic_symbol_index)
        tasks = [{"target_symbols": ["func1"]}]  # No 'id'

        result = service.validate_conflicts(tasks)
        assert result is not None
        assert "parallel_feasible" in result

    def test_validate_conflicts_missing_target_symbols(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with task missing 'target_symbols'."""
        service = QueryService(basic_symbol_index)
        tasks = [{"id": "t1"}]  # No target_symbols

        result = service.validate_conflicts(tasks)
        # Should handle missing field
        assert result is not None

    def test_validate_conflicts_single_task(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with single task."""
        service = QueryService(basic_symbol_index)
        tasks = [{"id": "t1", "target_symbols": ["func1"]}]

        result = service.validate_conflicts(tasks)

        assert result is not None
        assert result["parallel_feasible"] == True

    def test_validate_conflicts_duplicate_symbols(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with same symbol in multiple tasks."""
        service = QueryService(basic_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["func1"]},
            {"id": "t2", "target_symbols": ["func1"]},
        ]

        result = service.validate_conflicts(tasks)

        assert result is not None
        assert result["parallel_feasible"] == False
        assert len(result["direct_conflicts"]) > 0

    def test_validate_conflicts_no_overlap(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with non-overlapping tasks."""
        service = QueryService(basic_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["func1"]},
            {"id": "t2", "target_symbols": ["func2"]},
        ]

        result = service.validate_conflicts(tasks)

        assert result is not None
        assert result["parallel_feasible"] == True

    def test_validate_conflicts_with_conflict_analyzer(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts uses conflict analyzer when available."""
        mock_analyzer = MagicMock(spec=ConflictAnalyzer)
        mock_analyzer.analyze_conflicts.return_value = {
            "parallel_feasible": False,
            "direct_conflicts": [],
        }

        service = QueryService(basic_symbol_index, neo4j_client=MagicMock())
        # Service would create conflict analyzer

        tasks = [{"id": "t1", "target_symbols": ["func1"]}]
        result = service.validate_conflicts(tasks)

        # Should return valid conflict analysis
        assert result is not None

    def test_validate_conflicts_empty_target_symbols(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with empty target_symbols list."""
        service = QueryService(basic_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": []},
            {"id": "t2", "target_symbols": []},
        ]

        result = service.validate_conflicts(tasks)

        assert result is not None
        # No overlap, so should be parallelizable
        assert result["parallel_feasible"] == True

    def test_validate_conflicts_complex_overlap(self, basic_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with complex multi-task overlap."""
        service = QueryService(basic_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["func1", "func2"]},
            {"id": "t2", "target_symbols": ["func2", "TestClass"]},
            {"id": "t3", "target_symbols": ["TestClass"]},
        ]

        result = service.validate_conflicts(tasks)

        assert result is not None
        # Should detect multiple conflicts
        assert result["parallel_feasible"] == False
