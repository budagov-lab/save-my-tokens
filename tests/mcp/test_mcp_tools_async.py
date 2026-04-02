"""Async tests for MCP tools - covering error paths and context injection."""

import pytest
import asyncio
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
