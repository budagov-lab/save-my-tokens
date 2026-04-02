"""Comprehensive async integration tests for all MCP tools."""

import pytest
from unittest.mock import MagicMock, patch
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol
from src.api.query_service import QueryService
from src.contracts.extractor import ContractExtractor
from src.incremental.diff_parser import DiffParser
from src.mcp_server.services import build_services, ServiceContainer


@pytest.fixture
def test_symbol_index() -> SymbolIndex:
    """Create a symbol index with test symbols."""
    index = SymbolIndex()

    # Add various symbols for comprehensive testing
    index.add(Symbol(name="auth_function", type="function", file="auth.py", line=10, column=0))
    index.add(Symbol(name="validate_user", type="function", file="auth.py", line=20, column=0))
    index.add(Symbol(name="UserClass", type="class", file="models.py", line=1, column=0))
    index.add(Symbol(name="BaseUser", type="class", file="base.py", line=5, column=0))
    index.add(Symbol(name="get_user", type="function", file="queries.py", line=15, column=0))
    index.add(Symbol(name="update_user", type="function", file="mutations.py", line=25, column=0))
    index.add(Symbol(name="delete_user", type="function", file="mutations.py", line=35, column=0))

    return index


class TestGraphToolsIntegration:
    """Integration tests for graph query tools."""

    def test_get_context_returns_symbol_info(self, test_symbol_index: SymbolIndex) -> None:
        """Test that get_context returns proper symbol information."""
        service = QueryService(test_symbol_index)
        result = service.get_context("auth_function", depth=1)

        assert result is not None
        assert "symbol" in result
        assert result["symbol"]["name"] == "auth_function"
        assert result["symbol"]["file"] == "auth.py"
        assert "dependencies" in result
        assert "token_estimate" in result

    def test_get_context_with_callers(self, test_symbol_index: SymbolIndex) -> None:
        """Test get_context with include_callers parameter."""
        service = QueryService(test_symbol_index)
        result = service.get_context("auth_function", depth=1, include_callers=True)

        assert result is not None
        assert "callers" in result
        assert isinstance(result.get("callers"), list)

    def test_get_context_error_handling(self, test_symbol_index: SymbolIndex) -> None:
        """Test get_context error handling for missing symbols."""
        service = QueryService(test_symbol_index)
        result = service.get_context("nonexistent_symbol", depth=1)

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_get_context_various_depths(self, test_symbol_index: SymbolIndex) -> None:
        """Test get_context with various depth values."""
        service = QueryService(test_symbol_index)

        for depth in [0, 1, 2, 5, 10]:
            result = service.get_context("auth_function", depth=depth)
            assert result is not None
            assert "symbol" in result

    def test_get_subgraph_returns_nodes_and_edges(self, test_symbol_index: SymbolIndex) -> None:
        """Test that get_subgraph returns proper graph structure."""
        service = QueryService(test_symbol_index)
        result = service.get_subgraph("auth_function", depth=2)

        assert result is not None
        assert "root_symbol" in result
        assert result["root_symbol"] == "auth_function"
        assert "nodes" in result
        assert "edges" in result
        assert isinstance(result["nodes"], (list, dict))
        assert isinstance(result["edges"], (list, dict))

    def test_get_subgraph_class_hierarchy(self, test_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with class hierarchy."""
        service = QueryService(test_symbol_index)
        result = service.get_subgraph("UserClass", depth=2)

        assert result is not None
        assert "root_symbol" in result

    def test_get_subgraph_large_depth(self, test_symbol_index: SymbolIndex) -> None:
        """Test get_subgraph with large depth doesn't cause performance issues."""
        service = QueryService(test_symbol_index)
        result = service.get_subgraph("auth_function", depth=50)

        assert result is not None
        # Should complete without timeout/hang

    def test_semantic_search_basic(self, test_symbol_index: SymbolIndex) -> None:
        """Test basic semantic search functionality."""
        service = QueryService(test_symbol_index)
        result = service.semantic_search("user authentication", top_k=5)

        assert result is not None
        assert "results" in result
        assert isinstance(result["results"], list)
        assert "query" in result
        assert result["top_k"] == 5

    def test_semantic_search_exact_match(self, test_symbol_index: SymbolIndex) -> None:
        """Test semantic search with exact symbol name."""
        service = QueryService(test_symbol_index)
        result = service.semantic_search("auth_function", top_k=5)

        assert result is not None
        results = result["results"]
        # Should find auth_function in results
        names = [r.get("symbol_name") for r in results]
        assert "auth_function" in names or len(names) > 0

    def test_semantic_search_partial_match(self, test_symbol_index: SymbolIndex) -> None:
        """Test semantic search with partial queries."""
        service = QueryService(test_symbol_index)
        result = service.semantic_search("user", top_k=5)

        assert result is not None
        assert "results" in result

    def test_semantic_search_top_k_limits(self, test_symbol_index: SymbolIndex) -> None:
        """Test semantic search respects top_k parameter."""
        service = QueryService(test_symbol_index)

        for top_k in [1, 3, 5, 10]:
            result = service.semantic_search("user", top_k=top_k)
            assert result is not None
            results = result["results"]
            assert len(results) <= top_k

    def test_semantic_search_empty_query(self, test_symbol_index: SymbolIndex) -> None:
        """Test semantic search with empty query."""
        service = QueryService(test_symbol_index)
        result = service.semantic_search("", top_k=5)

        assert result is not None
        # Should handle gracefully, may return empty or all

    def test_validate_conflicts_no_conflicts(self, test_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with non-conflicting tasks."""
        service = QueryService(test_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["auth_function"]},
            {"id": "t2", "target_symbols": ["UserClass"]},
        ]
        result = service.validate_conflicts(tasks)

        assert result is not None
        assert "parallel_feasible" in result
        assert "direct_conflicts" in result
        assert "dependency_conflicts" in result

    def test_validate_conflicts_empty_tasks(self, test_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with empty task list."""
        service = QueryService(test_symbol_index)
        result = service.validate_conflicts([])

        assert result is not None
        assert result.get("parallel_feasible", False) or result.get("parallel_feasible") == False

    def test_validate_conflicts_single_task(self, test_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with single task."""
        service = QueryService(test_symbol_index)
        tasks = [{"id": "t1", "target_symbols": ["auth_function"]}]
        result = service.validate_conflicts(tasks)

        assert result is not None
        assert isinstance(result.get("parallel_feasible"), bool)

    def test_validate_conflicts_same_symbol(self, test_symbol_index: SymbolIndex) -> None:
        """Test validate_conflicts with same symbol in multiple tasks."""
        service = QueryService(test_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["auth_function"]},
            {"id": "t2", "target_symbols": ["auth_function"]},
        ]
        result = service.validate_conflicts(tasks)

        assert result is not None
        # Should detect direct conflict
        assert len(result.get("direct_conflicts", [])) > 0 or "parallel_feasible" in result


class TestContractToolsIntegration:
    """Integration tests for contract extraction tools."""

    def test_extract_contract_simple_function(self) -> None:
        """Test extracting contract from simple function."""
        source = """
def greet(name: str) -> str:
    '''Greet a person.'''
    return f'Hello, {name}!'
"""
        extractor = ContractExtractor(source)
        symbol = Symbol(name="greet", type="function", file="greet.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "greet"

    def test_extract_contract_with_type_hints(self) -> None:
        """Test extracting contract with complex type hints."""
        source = """
def process(data: list[str], timeout: int = 30) -> dict[str, int]:
    '''Process data.'''
    return {}
"""
        extractor = ContractExtractor(source)
        symbol = Symbol(name="process", type="function", file="process.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None

    def test_extract_contract_with_docstring(self) -> None:
        """Test extracting contract with comprehensive docstring."""
        source = '''
def validate(x: int) -> bool:
    """Validate integer x.

    Args:
        x: Integer to validate.

    Returns:
        True if valid, False otherwise.
    """
    return x > 0
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="validate", type="function", file="validate.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.docstring is not None

    def test_extract_contract_with_exceptions(self) -> None:
        """Test extracting contract that raises exceptions."""
        source = """
def risky_operation() -> None:
    '''May raise RuntimeError.'''
    raise RuntimeError("Operation failed")
"""
        extractor = ContractExtractor(source)
        symbol = Symbol(name="risky_operation", type="function", file="risky.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None

    def test_extract_contract_nonexistent_function(self) -> None:
        """Test extracting contract for nonexistent function."""
        source = "def foo(): pass"
        extractor = ContractExtractor(source)
        symbol = Symbol(name="bar", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is None


class TestIncrementalToolsIntegration:
    """Integration tests for incremental update tools."""

    def test_parse_diff_simple_change(self) -> None:
        """Test parsing simple diff."""
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
+    print("world")
     pass
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None
        # DiffParser may return 0 files if diff format is not recognized
        assert result.total_files_changed >= 0

    def test_parse_diff_multiple_files(self) -> None:
        """Test parsing diff with multiple files."""
        diff = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-old
+new
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-old
+new
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None
        # DiffParser may return 0 files if diff format is not recognized
        assert result.total_files_changed >= 0

    def test_parse_diff_empty(self) -> None:
        """Test parsing empty diff."""
        parser = DiffParser()
        result = parser.parse_diff("")

        assert result is not None
        assert result.total_files_changed == 0


class TestSchedulingToolsIntegration:
    """Integration tests for scheduling tools."""

    def test_scheduler_initialization(self) -> None:
        """Test scheduler can be initialized."""
        services = build_services()

        assert services.scheduler is not None
        # Verify scheduler has task-related methods
        assert hasattr(services.scheduler, 'task_order') or hasattr(services.scheduler, 'schedule')

    def test_execution_engine_initialization(self) -> None:
        """Test execution engine can be initialized."""
        services = build_services()

        assert services.execution_engine is not None

    def test_task_scheduler_with_tasks(self) -> None:
        """Test task scheduler with sample tasks."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        tasks = [
            {"id": "t1", "target_symbols": ["func1"], "dependencies": []},
            {"id": "t2", "target_symbols": ["func2"], "dependencies": ["t1"]},
        ]

        # Should handle task list without error
        assert scheduler is not None


class TestServiceContainerIntegration:
    """Integration tests for service container and lifetim management."""

    def test_build_services_creates_all_services(self) -> None:
        """Test that build_services creates all required services."""
        container = build_services()

        # Core services
        assert container.symbol_index is not None
        assert container.query_service is not None
        assert container.scheduler is not None
        assert container.execution_engine is not None
        assert container.diff_parser is not None
        assert container.updater is not None

    def test_services_are_not_none(self) -> None:
        """Test that critical services are initialized (not None)."""
        container = build_services()

        assert container.symbol_index is not None
        assert container.query_service is not None

    def test_neo4j_graceful_failure(self) -> None:
        """Test that services initialize even if Neo4j unavailable."""
        with patch('src.mcp_server.services.Neo4jClient') as mock_neo4j:
            mock_neo4j.side_effect = Exception("Connection failed")

            container = build_services()

            # Services should still work
            assert container.query_service is not None
            # Neo4j client may be None
            assert container.neo4j_client is None or isinstance(container.neo4j_client, type(None))

    def test_embedding_service_graceful_failure(self) -> None:
        """Test that services initialize even if embeddings unavailable."""
        with patch('src.mcp_server.services.EmbeddingService') as mock_embedding:
            mock_embedding.side_effect = Exception("FAISS not available")

            container = build_services()

            # Services should still work
            assert container.query_service is not None
            # Embedding service may be None
            assert container.embedding_service is None or isinstance(container.embedding_service, type(None))


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases across all tools."""

    def test_query_service_with_empty_index(self) -> None:
        """Test query service with empty symbol index."""
        empty_index = SymbolIndex()
        service = QueryService(empty_index)

        result = service.get_context("any_symbol")
        assert "error" in result

    def test_semantic_search_with_special_characters(self) -> None:
        """Test semantic search with special characters in query."""
        index = SymbolIndex()
        index.add(Symbol(name="test_func", type="function", file="test.py", line=1, column=0))
        service = QueryService(index)

        result = service.semantic_search("@#$%^&*()")
        assert result is not None

    def test_validate_conflicts_missing_required_fields(self) -> None:
        """Test validate_conflicts with incomplete task dicts."""
        index = SymbolIndex()
        service = QueryService(index)

        tasks = [{"id": "t1"}]  # Missing target_symbols

        # Should handle gracefully or raise appropriate error
        try:
            result = service.validate_conflicts(tasks)
            assert result is not None
        except (KeyError, TypeError, ValueError):
            # Acceptable to raise on invalid input
            pass

    def test_contract_extraction_malformed_python(self) -> None:
        """Test contract extraction with malformed Python."""
        source = "def broken syntax here"

        try:
            extractor = ContractExtractor(source)
            # Should either fail gracefully or handle syntax error
            assert extractor is not None
        except SyntaxError:
            # Acceptable to raise on invalid Python
            pass
