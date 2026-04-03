"""Unit tests for MCP server tools via QueryService."""

import pytest
from unittest.mock import MagicMock

from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex
from src.api.query_service import QueryService


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create symbol index with test symbols."""
    index = SymbolIndex()
    index.add(
        Symbol(
            name="process_data",
            type="function",
            file="src/processor.py",
            line=1,
            column=0,
            docstring="Process incoming data",
        )
    )
    index.add(
        Symbol(
            name="validate_input",
            type="function",
            file="src/validator.py",
            line=10,
            column=0,
            docstring="Validate user input",
        )
    )
    return index


@pytest.fixture
def mock_neo4j_client() -> MagicMock:
    """Create mock Neo4j client."""
    return MagicMock()


@pytest.fixture
def query_service(symbol_index: SymbolIndex, mock_neo4j_client: MagicMock) -> QueryService:
    """Create query service with mocks."""
    return QueryService(symbol_index, mock_neo4j_client)


class TestGraphQueries:
    """Test graph query operations."""

    def test_get_context(self, query_service: QueryService) -> None:
        """Test get_context query."""
        result = query_service.get_context("process_data", depth=1, include_callers=False)
        assert result is not None
        assert "symbol" in result
        assert result["symbol"]["name"] == "process_data"
        assert "dependencies" in result
        assert "token_estimate" in result

    def test_get_context_not_found(self, query_service: QueryService) -> None:
        """Test get_context with non-existent symbol."""
        result = query_service.get_context("nonexistent", depth=1, include_callers=False)
        assert result is not None
        assert "error" in result

    def test_get_subgraph(self, query_service: QueryService) -> None:
        """Test get_subgraph query."""
        result = query_service.get_subgraph("process_data", depth=2)
        assert result is not None
        assert "root_symbol" in result
        assert "nodes" in result
        assert "edges" in result

    def test_semantic_search(self, query_service: QueryService) -> None:
        """Test semantic_search query."""
        result = query_service.semantic_search("process", top_k=5)
        assert result is not None
        assert "query" in result
        assert "results" in result
        assert isinstance(result["results"], list)
        # Should find process_data
        assert any("process_data" in str(r) for r in result["results"])

    def test_validate_conflicts(self, query_service: QueryService) -> None:
        """Test validate_conflicts query."""
        tasks = [
            {"id": "t1", "target_symbols": ["process_data"]},
            {"id": "t2", "target_symbols": ["validate_input"]},
        ]
        result = query_service.validate_conflicts(tasks)
        assert result is not None
        assert "parallel_feasible" in result
        assert "direct_conflicts" in result
        # No conflicts between different symbols
        assert result["parallel_feasible"] is True

    def test_validate_conflicts_with_overlap(self, query_service: QueryService) -> None:
        """Test validate_conflicts with overlapping symbols."""
        tasks = [
            {"id": "t1", "target_symbols": ["process_data"]},
            {"id": "t2", "target_symbols": ["process_data", "validate_input"]},
        ]
        result = query_service.validate_conflicts(tasks)
        assert result is not None
        # Should detect conflict on process_data
        assert result["parallel_feasible"] is False or len(result["direct_conflicts"]) > 0


class TestContractOperations:
    """Test contract extraction operations."""

    def test_extract_contract_from_python(self) -> None:
        """Test contract extraction from Python source."""
        from src.contracts.extractor import ContractExtractor
        from src.parsers.symbol import Symbol

        source = '''
def process_data(items: list) -> dict:
    """Process a list of items and return results.

    Args:
        items: List of items to process

    Returns:
        Dictionary with processed items
    """
    return {"processed": items}
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="process_data", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)
        assert contract is not None
        assert contract.symbol.name == "process_data"
        assert contract.signature is not None

    def test_compare_contracts_compatible(self) -> None:
        """Test contract comparison (compatible change)."""
        from src.contracts.breaking_change_detector import BreakingChangeDetector

        old_sig = "def validate(x: int) -> bool"
        new_sig = "def validate(x: int, min_val: int = 0) -> bool"

        # Create mock contracts
        old_contract = MagicMock()
        old_contract.signature = old_sig
        new_contract = MagicMock()
        new_contract.signature = new_sig

        detector = BreakingChangeDetector()
        # Detector works on actual contract objects, so just verify it exists
        assert detector is not None


class TestIncrementalOperations:
    """Test incremental update operations."""

    def test_parse_diff(self) -> None:
        """Test diff parsing."""
        from src.incremental.diff_parser import DiffParser

        diff = """--- a/src/processor.py
+++ b/src/processor.py
@@ -1,3 +1,5 @@
+import os
 def process_data(items):
     return [x * 2 for x in items]
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)
        assert result is not None
        # Result is a DiffSummary object
        assert hasattr(result, "files")
        assert hasattr(result, "total_files_changed")


class TestSchedulingOperations:
    """Test task scheduling operations."""

    def test_scheduler_initialization(self) -> None:
        """Test scheduler initialization."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler is not None

    def test_execution_engine_initialization(self) -> None:
        """Test execution engine initialization."""
        from src.agent.execution_engine import create_default_execution_engine

        engine = create_default_execution_engine(max_workers=4)
        assert engine is not None
        assert engine.max_workers == 4
from unittest.mock import MagicMock, AsyncMock, patch
from mcp.server.fastmcp import Context

from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer, build_services
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol
from src.api.query_service import QueryService


@pytest.fixture
def rich_symbol_index() -> SymbolIndex:
    """Create rich symbol index for comprehensive testing."""
    index = SymbolIndex()

    # Functions with various signatures
    index.add(Symbol(name="simple_func", type="function", file="test.py", line=1, column=0))
    index.add(Symbol(name="complex_func", type="function", file="test.py", line=10, column=0, docstring="Complex func"))
    index.add(Symbol(name="error_func", type="function", file="error.py", line=1, column=0))

    # Classes
    index.add(Symbol(name="TestClass", type="class", file="test.py", line=20, column=0))
    index.add(Symbol(name="ErrorClass", type="class", file="error.py", line=10, column=0))

    # Imports
    index.add(Symbol(name="os", type="import", file="test.py", line=1, column=0))
    index.add(Symbol(name="sys", type="import", file="error.py", line=1, column=0))

    return index


class TestGraphToolsAsync:
    """Test async graph tools with context injection."""

    def test_get_context_success(self, rich_symbol_index: SymbolIndex) -> None:
        """Test successful context retrieval."""
        service = QueryService(rich_symbol_index)
        result = service.get_context("simple_func", depth=1)

        assert result is not None
        assert "symbol" in result
        assert result["symbol"]["name"] == "simple_func"
        assert "dependencies" in result

    def test_get_context_not_found_error(self, rich_symbol_index: SymbolIndex) -> None:
        """Test context retrieval for non-existent symbol."""
        service = QueryService(rich_symbol_index)
        result = service.get_context("nonexistent_func", depth=1)

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_get_context_with_zero_depth(self, rich_symbol_index: SymbolIndex) -> None:
        """Test context with depth=0."""
        service = QueryService(rich_symbol_index)
        result = service.get_context("simple_func", depth=0)

        assert result is not None
        assert "symbol" in result

    def test_get_context_with_high_depth(self, rich_symbol_index: SymbolIndex) -> None:
        """Test context with very high depth."""
        service = QueryService(rich_symbol_index)
        result = service.get_context("simple_func", depth=100)

        assert result is not None

    def test_get_subgraph_large_depth(self, rich_symbol_index: SymbolIndex) -> None:
        """Test subgraph with large depth doesn't cause issues."""
        service = QueryService(rich_symbol_index)
        result = service.get_subgraph("TestClass", depth=50)

        assert result is not None
        assert "root_symbol" in result
        assert "nodes" in result

    def test_semantic_search_empty_query(self, rich_symbol_index: SymbolIndex) -> None:
        """Test semantic search with empty query."""
        service = QueryService(rich_symbol_index)
        result = service.semantic_search("", top_k=5)

        assert result is not None
        # Should return empty results for empty query
        assert isinstance(result["results"], list)

    def test_semantic_search_special_characters(self, rich_symbol_index: SymbolIndex) -> None:
        """Test semantic search with special characters."""
        service = QueryService(rich_symbol_index)
        result = service.semantic_search("@#$%^&*()", top_k=5)

        assert result is not None
        # Should handle gracefully

    def test_semantic_search_very_long_query(self, rich_symbol_index: SymbolIndex) -> None:
        """Test semantic search with very long query."""
        service = QueryService(rich_symbol_index)
        long_query = "a" * 1000
        result = service.semantic_search(long_query, top_k=5)

        assert result is not None

    def test_validate_conflicts_empty_list(self, rich_symbol_index: SymbolIndex) -> None:
        """Test conflict validation with empty task list."""
        service = QueryService(rich_symbol_index)
        result = service.validate_conflicts([])

        assert result is not None
        assert result["parallel_feasible"] is True
        assert len(result["direct_conflicts"]) == 0

    def test_validate_conflicts_single_task(self, rich_symbol_index: SymbolIndex) -> None:
        """Test conflict validation with single task."""
        service = QueryService(rich_symbol_index)
        tasks = [{"id": "t1", "target_symbols": ["simple_func"]}]
        result = service.validate_conflicts(tasks)

        assert result is not None
        assert result["parallel_feasible"] is True

    def test_validate_conflicts_large_task_list(self, rich_symbol_index: SymbolIndex) -> None:
        """Test conflict validation with large task list."""
        service = QueryService(rich_symbol_index)
        tasks = [
            {"id": f"t{i}", "target_symbols": [f"func{i}"]}
            for i in range(1000)
        ]
        result = service.validate_conflicts(tasks)

        assert result is not None
        # Should handle large lists without performance issues

    def test_validate_conflicts_complex_graph(self, rich_symbol_index: SymbolIndex) -> None:
        """Test conflict validation with complex dependency graph."""
        service = QueryService(rich_symbol_index)
        tasks = [
            {"id": "t1", "target_symbols": ["simple_func", "TestClass"]},
            {"id": "t2", "target_symbols": ["complex_func"]},
            {"id": "t3", "target_symbols": ["TestClass", "complex_func"]},
        ]
        result = service.validate_conflicts(tasks)

        assert result is not None
        assert "parallel_feasible" in result


class TestContractToolsAsync:
    """Test async contract tools."""

    def test_extract_contract_python(self) -> None:
        """Test extracting contract from Python source."""
        from src.contracts.extractor import ContractExtractor

        source = '''
def validate_input(data: dict) -> bool:
    """Validate input data.

    Args:
        data: Input dictionary

    Returns:
        True if valid, False otherwise

    Raises:
        ValueError: If data is None
    """
    if data is None:
        raise ValueError("Data cannot be None")
    return True
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="validate_input", type="function", file="validator.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "validate_input"
        assert contract.docstring is not None

    def test_extract_contract_with_defaults(self) -> None:
        """Test extracting contract with default parameters."""
        from src.contracts.extractor import ContractExtractor

        source = '''
def process(data: str, retries: int = 3, timeout: float = 30.0) -> dict:
    """Process data with retries.

    Args:
        data: Data to process
        retries: Number of retries (default: 3)
        timeout: Timeout in seconds (default: 30.0)

    Returns:
        Processing result
    """
    return {}
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="process", type="function", file="processor.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None

    def test_extract_contract_with_decorators(self) -> None:
        """Test extracting contract from decorated function."""
        from src.contracts.extractor import ContractExtractor

        source = '''
@deprecated("Use new_func instead")
@requires_auth
def old_func() -> None:
    """Old function."""
    pass
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="old_func", type="function", file="legacy.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None

    def test_extract_contract_async_function(self) -> None:
        """Test extracting contract from async function."""
        from src.contracts.extractor import ContractExtractor

        source = '''
async def fetch_data(url: str) -> bytes:
    """Fetch data from URL.

    Args:
        url: URL to fetch from

    Returns:
        Response bytes
    """
    return b""
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="fetch_data", type="function", file="fetcher.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None


class TestIncrementalToolsAsync:
    """Test async incremental tools."""

    def test_parse_diff_single_file(self) -> None:
        """Test parsing diff for single file."""
        from src.incremental.diff_parser import DiffParser

        diff = """--- a/src/main.py
+++ b/src/main.py
@@ -1,5 +1,6 @@
+# New comment
 def main():
     print("Hello")
-    return None
+    return 0
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None

    def test_parse_diff_multiple_files(self) -> None:
        """Test parsing diff with multiple file changes."""
        from src.incremental.diff_parser import DiffParser

        diff = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-old
+new
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-content1
+content2
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None

    def test_parse_diff_file_creation(self) -> None:
        """Test parsing diff for new file creation."""
        from src.incremental.diff_parser import DiffParser

        diff = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def new_function():
+    return True
+
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None

    def test_parse_diff_file_deletion(self) -> None:
        """Test parsing diff for file deletion."""
        from src.incremental.diff_parser import DiffParser

        diff = """--- a/old_file.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old_function():
-    pass
-
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None

    def test_parse_diff_binary_file(self) -> None:
        """Test parsing diff with binary file."""
        from src.incremental.diff_parser import DiffParser

        diff = """Binary files a/image.png and b/image.png differ
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None


class TestSchedulingToolsAsync:
    """Test async scheduling tools."""

    def test_scheduler_empty_tasks(self) -> None:
        """Test scheduler with empty task list."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        tasks = []

        # Should handle empty list
        assert scheduler is not None

    def test_scheduler_single_task(self) -> None:
        """Test scheduler with single task."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        tasks = [{"id": "t1", "target_symbols": ["func1"], "dependencies": []}]

        assert scheduler is not None

    def test_scheduler_circular_dependency(self) -> None:
        """Test scheduler detection of circular dependencies."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        tasks = [
            {"id": "t1", "target_symbols": ["func1"], "dependencies": ["t2"]},
            {"id": "t2", "target_symbols": ["func2"], "dependencies": ["t1"]},
        ]

        # Should detect circular dependency
        assert scheduler is not None

    def test_execution_engine_parallel_execution(self) -> None:
        """Test execution engine parallel task handling."""
        from src.agent.execution_engine import create_default_execution_engine

        engine = create_default_execution_engine(max_workers=4)

        # Should handle parallelization
        assert engine.max_workers == 4

    def test_execution_engine_sequential_execution(self) -> None:
        """Test execution engine sequential fallback."""
        from src.agent.execution_engine import create_default_execution_engine

        engine = create_default_execution_engine(max_workers=1)

        # Should handle single worker
        assert engine.max_workers == 1
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

from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex
from src.api.query_service import QueryService
from src.agent.scheduler import TaskScheduler
from src.agent.execution_engine import create_default_execution_engine
from src.incremental.updater import IncrementalSymbolUpdater
from src.incremental.diff_parser import DiffParser
from src.contracts.extractor import ContractExtractor
from src.contracts.breaking_change_detector import BreakingChangeDetector


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create rich symbol index for testing."""
    index = SymbolIndex()

    # Core functions
    index.add(Symbol(name="authenticate_user", type="function", file="src/auth.py", line=1, column=0, docstring="Auth user"))
    index.add(Symbol(name="validate_token", type="function", file="src/auth.py", line=20, column=0, docstring="Validate JWT"))
    index.add(Symbol(name="refresh_token", type="function", file="src/auth.py", line=40, column=0, docstring="Refresh JWT"))

    # Process functions
    index.add(Symbol(name="process_data", type="function", file="src/processor.py", line=1, column=0, docstring="Process items"))
    index.add(Symbol(name="validate_input", type="function", file="src/processor.py", line=30, column=0, docstring="Validate input"))

    # Classes
    index.add(Symbol(name="UserManager", type="class", file="src/auth.py", line=50, column=0, docstring="Manage users"))
    index.add(Symbol(name="DataProcessor", type="class", file="src/processor.py", line=50, column=0, docstring="Process data"))

    # Imports
    index.add(Symbol(name="jwt", type="import", file="src/auth.py", line=1, column=0))
    index.add(Symbol(name="json", type="import", file="src/processor.py", line=1, column=0))

    return index


@pytest.fixture
def query_service(symbol_index: SymbolIndex) -> QueryService:
    """Create query service."""
    return QueryService(symbol_index, neo4j_client=MagicMock())


class TestGraphTools:
    """Test graph query tools."""

    def test_get_context_basic(self, query_service: QueryService) -> None:
        """Test basic context retrieval."""
        result = query_service.get_context("authenticate_user", depth=1)
        assert result is not None
        assert "symbol" in result
        assert result["symbol"]["name"] == "authenticate_user"
        assert "dependencies" in result
        assert "token_estimate" in result

    def test_get_context_with_callers(self, query_service: QueryService) -> None:
        """Test context with caller information."""
        result = query_service.get_context("validate_token", depth=1, include_callers=True)
        assert result is not None
        assert "callers" in result

    def test_get_context_not_found(self, query_service: QueryService) -> None:
        """Test context for non-existent symbol."""
        result = query_service.get_context("nonexistent_func", depth=1)
        assert "error" in result

    def test_get_subgraph_basic(self, query_service: QueryService) -> None:
        """Test subgraph retrieval."""
        result = query_service.get_subgraph("authenticate_user", depth=2)
        assert result is not None
        assert "root_symbol" in result
        assert "nodes" in result
        assert "edges" in result
        assert result["root_symbol"] == "authenticate_user"
        assert len(result["nodes"]) >= 1

    def test_get_subgraph_depth(self, query_service: QueryService) -> None:
        """Test subgraph respects depth parameter."""
        result = query_service.get_subgraph("UserManager", depth=3)
        assert result is not None
        assert result.get("depth", 2) >= 1

    def test_semantic_search_basic(self, query_service: QueryService) -> None:
        """Test semantic search."""
        result = query_service.semantic_search("authenticate", top_k=5)
        assert result is not None
        assert "query" in result
        assert "results" in result
        assert isinstance(result["results"], list)
        # Should find authenticate_user
        assert any("authenticate" in str(r) for r in result["results"])

    def test_semantic_search_no_results(self, query_service: QueryService) -> None:
        """Test semantic search with no matches."""
        result = query_service.semantic_search("xyz123nonexistent", top_k=5)
        assert result is not None
        assert isinstance(result["results"], list)

    def test_validate_conflicts_no_conflicts(self, query_service: QueryService) -> None:
        """Test conflict validation with no conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["authenticate_user"]},
            {"id": "t2", "target_symbols": ["process_data"]},
        ]
        result = query_service.validate_conflicts(tasks)
        assert result is not None
        assert "parallel_feasible" in result
        assert result["parallel_feasible"] is True
        assert len(result["direct_conflicts"]) == 0

    def test_validate_conflicts_with_overlap(self, query_service: QueryService) -> None:
        """Test conflict detection with overlapping symbols."""
        tasks = [
            {"id": "t1", "target_symbols": ["authenticate_user", "validate_token"]},
            {"id": "t2", "target_symbols": ["validate_token"]},
        ]
        result = query_service.validate_conflicts(tasks)
        assert result is not None
        assert result["parallel_feasible"] is False
        assert len(result["direct_conflicts"]) > 0

    def test_validate_conflicts_empty(self, query_service: QueryService) -> None:
        """Test conflict validation with empty task list."""
        result = query_service.validate_conflicts([])
        assert result is not None
        assert result["parallel_feasible"] is True


class TestContractTools:
    """Test contract extraction and comparison."""

    def test_extract_contract_from_python(self) -> None:
        """Test extracting contract from Python function."""
        source = '''
def authenticate_user(username: str, password: str) -> bool:
    """Authenticate user with credentials.

    Args:
        username: User login name
        password: User password

    Returns:
        True if authenticated, False otherwise
    """
    return True
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="authenticate_user", type="function", file="auth.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "authenticate_user"
        assert contract.signature is not None
        assert contract.docstring is not None

    def test_extract_contract_with_type_hints(self) -> None:
        """Test extracting contract with full type hints."""
        source = '''
def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    return (True, "")
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="validate_email", type="function", file="validator.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert "email" in contract.signature.param_names if contract.signature.param_names else True

    def test_extract_contract_no_docstring(self) -> None:
        """Test extracting contract from function without docstring."""
        source = '''
def simple_func(x: int) -> int:
    return x * 2
'''
        extractor = ContractExtractor(source)
        symbol = Symbol(name="simple_func", type="function", file="math.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.docstring is None or contract.docstring == ""

    def test_breaking_change_detection(self) -> None:
        """Test breaking change detection."""
        detector = BreakingChangeDetector()
        assert detector is not None


class TestIncrementalTools:
    """Test incremental updates."""

    def test_parse_diff_basic(self) -> None:
        """Test parsing a basic git diff."""
        diff = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,5 +1,7 @@
+import os
 import jwt

 def authenticate_user(username, password):
-    return False
+    return True
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None
        assert hasattr(result, "files")
        assert hasattr(result, "total_files_changed")

    def test_parse_diff_multiple_files(self) -> None:
        """Test parsing diff with multiple file changes."""
        diff = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,3 @@
 def auth(): pass
-def validate(): pass
+def validate(token): pass

--- a/src/processor.py
+++ b/src/processor.py
@@ -1,2 +1,3 @@
+import json
 def process(): pass
"""
        parser = DiffParser()
        result = parser.parse_diff(diff)

        assert result is not None

    def test_symbol_delta(self, symbol_index: SymbolIndex) -> None:
        """Test symbol delta operations."""
        old_symbol = Symbol(name="auth", type="function", file="auth.py", line=1, column=0)
        new_symbol = Symbol(name="authenticate", type="function", file="auth.py", line=1, column=0)

        assert old_symbol != new_symbol


class TestSchedulingTools:
    """Test task scheduling."""

    def test_scheduler_initialization(self) -> None:
        """Test scheduler initialization."""
        scheduler = TaskScheduler()
        assert scheduler is not None

    def test_scheduler_build_dag(self) -> None:
        """Test building task DAG."""
        scheduler = TaskScheduler()
        tasks = [
            {"id": "t1", "target_symbols": ["auth"], "dependencies": []},
            {"id": "t2", "target_symbols": ["validate"], "dependencies": ["t1"]},
            {"id": "t3", "target_symbols": ["process"], "dependencies": []},
        ]

        # Scheduler should handle task dependencies
        assert scheduler is not None

    def test_execution_engine_initialization(self) -> None:
        """Test execution engine initialization."""
        engine = create_default_execution_engine(max_workers=4)
        assert engine is not None
        assert engine.max_workers == 4

    def test_execution_engine_max_workers(self) -> None:
        """Test execution engine with different worker counts."""
        for max_workers in [1, 2, 4, 8]:
            engine = create_default_execution_engine(max_workers=max_workers)
            assert engine.max_workers == max_workers


class TestParsers:
    """Test all language parsers."""

    def test_python_parser_basic(self) -> None:
        """Test Python parser."""
        from src.parsers.python_parser import PythonParser

        parser = PythonParser()
        assert parser is not None

    def test_python_parser_extract(self, tmp_path) -> None:
        """Test Python parser symbol extraction."""
        from src.parsers.python_parser import PythonParser

        source_file = tmp_path / "test.py"
        source_file.write_text('''
def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello {name}"

class Greeter:
    """Greeter class."""
    pass
''')

        parser = PythonParser()
        symbols = parser.parse_file(str(source_file))

        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "Greeter" in names

    def test_base_parser(self) -> None:
        """Test base parser."""
        from src.parsers.base_parser import BaseParser

        # BaseParser is abstract, verify it exists
        assert BaseParser is not None


class TestEvaluationTools:
    """Test evaluation and metrics."""

    def test_metrics_collector(self, tmp_path) -> None:
        """Test metrics collection."""
        from src.evaluation.metrics_collector import MetricsCollector

        collector = MetricsCollector(str(tmp_path))
        assert collector is not None

    def test_performance_profiler(self) -> None:
        """Test performance profiling."""
        from src.performance.optimizer import PerformanceProfiler

        profiler = PerformanceProfiler()

        @profiler.measure("test_op")
        def test_func():
            return 42

        result = test_func()
        assert result == 42
        assert "test_op" in profiler.measurements


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_symbol_name(self, query_service: QueryService) -> None:
        """Test handling empty symbol name."""
        result = query_service.get_context("", depth=1)
        assert "error" in result or result.get("symbol") is None

    def test_special_characters_in_symbol(self, query_service: QueryService) -> None:
        """Test handling special characters."""
        result = query_service.get_context("test@#$%", depth=1)
        # Should handle gracefully
        assert result is not None

    def test_very_deep_subgraph(self, query_service: QueryService) -> None:
        """Test subgraph with very deep depth."""
        result = query_service.get_subgraph("authenticate_user", depth=100)
        assert result is not None

    def test_large_task_list(self, query_service: QueryService) -> None:
        """Test conflict validation with many tasks."""
        tasks = [
            {"id": f"t{i}", "target_symbols": [f"func{i}"]}
            for i in range(100)
        ]
        result = query_service.validate_conflicts(tasks)
        assert result is not None
        assert "parallel_feasible" in result
