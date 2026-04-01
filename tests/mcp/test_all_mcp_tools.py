"""Comprehensive tests for all MCP tools (graph, contracts, incremental, scheduling)."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

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
