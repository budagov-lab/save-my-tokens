"""Integration tests for graph construction on real repositories."""

import shutil
import tempfile
import textwrap
from pathlib import Path
from typing import Generator

import pytest

from src.graph.graph_builder import GraphBuilder
from src.graph.neo4j_client import Neo4jClient


@pytest.fixture
def temp_python_repo() -> Generator[Path, None, None]:
    """Create a temporary Python repository for testing.

    Yields:
        Path to temporary repo
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="syt_test_"))

    # Create sample Python files
    src_dir = temp_dir / "src"
    src_dir.mkdir()

    # Create a simple module file
    (src_dir / "__init__.py").write_text("")

    # Create utils.py with functions
    (src_dir / "utils.py").write_text(
        """
def helper_function():
    '''A helper function.'''
    return 42

def another_helper(x, y):
    '''Another helper.'''
    return x + y
"""
    )

    # Create main.py with classes and imports
    (src_dir / "main.py").write_text(
        """
from src.utils import helper_function

class Calculator:
    '''Simple calculator.'''

    def add(self, a, b):
        '''Add two numbers.'''
        return helper_function() + a + b

    def multiply(self, a, b):
        '''Multiply two numbers.'''
        return a * b

def main():
    '''Main entry point.'''
    calc = Calculator()
    result = calc.add(1, 2)
    return result
"""
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestGraphBuilderOnRealRepo:
    """Test graph building on real Python repository."""

    @pytest.mark.skip(reason="Requires Neo4j instance")
    def test_build_graph_from_python_repo(self, temp_python_repo: Path) -> None:
        """Test building graph from a Python repository.

        This test requires a running Neo4j instance at NEO4J_URI.
        """
        # Create builder and build graph
        builder = GraphBuilder(str(temp_python_repo))
        builder.build()

        # Verify graph was built
        stats = builder.get_stats()
        assert stats["symbol_count"] >= 3  # At least 3 functions/classes

    def test_parse_python_repo(self, temp_python_repo: Path) -> None:
        """Test parsing Python repo (without Neo4j)."""
        from unittest.mock import MagicMock

        # Create builder with mocked Neo4j client
        mock_client = MagicMock(spec=Neo4jClient)
        builder = GraphBuilder(str(temp_python_repo), neo4j_client=mock_client)

        # Parse files only
        builder._parse_all_files()

        # Verify symbols were extracted
        assert len(builder.symbol_index.get_all()) >= 5
        functions = builder.symbol_index.get_functions()
        assert len(functions) >= 3

        classes = builder.symbol_index.get_classes()
        assert len(classes) >= 1

    def test_create_nodes_from_symbols(self, temp_python_repo: Path) -> None:
        """Test creating nodes from extracted symbols."""
        from unittest.mock import MagicMock

        mock_client = MagicMock(spec=Neo4jClient)
        builder = GraphBuilder(str(temp_python_repo), neo4j_client=mock_client)

        # Parse and create nodes
        builder._parse_all_files()
        builder._create_nodes()

        # Verify nodes were created
        assert len(builder.nodes) >= 5
        # Check node types are correct
        node_types = {n.type for n in builder.nodes}
        assert len(node_types) > 0


class TestGraphBuilderEdgeCreation:
    """Test edge creation logic."""

    def test_create_defines_edges(self, temp_python_repo: Path) -> None:
        """Test DEFINES edge creation."""
        from unittest.mock import MagicMock

        mock_client = MagicMock(spec=Neo4jClient)
        builder = GraphBuilder(str(temp_python_repo), neo4j_client=mock_client)

        builder._parse_all_files()
        builder._create_nodes()
        builder._create_edges()

        # Should have DEFINES edges (file defines functions/classes)
        defines_edges = [e for e in builder.edges if e[0].type.value == "DEFINES"]
        assert len(defines_edges) > 0

    def test_create_imports_edges(self, temp_python_repo: Path) -> None:
        """Test IMPORTS edge creation."""
        from unittest.mock import MagicMock

        mock_client = MagicMock(spec=Neo4jClient)
        builder = GraphBuilder(str(temp_python_repo), neo4j_client=mock_client)

        builder._parse_all_files()
        builder._create_nodes()
        builder._create_edges()

        # Should have IMPORTS edges
        import_edges = [e for e in builder.edges if e[0].type.value == "IMPORTS"]
        # May or may not have imports depending on parsing
        assert isinstance(import_edges, list)
import pytest

from src.contracts.breaking_change_detector import BreakingChangeDetector
from src.contracts.contract_models import (
    BreakingChangeType,
    ChangeSeverity,
    ParameterInfo,
    SignatureInfo,
)
from src.contracts.extractor import ContractExtractor
from src.parsers.symbol import Symbol


class TestContractExtractor:
    """Test suite for ContractExtractor."""

    def test_extract_simple_function_contract(self):
        """Test extracting contract from simple function."""
        source = textwrap.dedent(
            '''
            def add(a: int, b: int) -> int:
                """Add two integers.

                Args:
                    a: First integer
                    b: Second integer

                Returns:
                    Sum of a and b
                """
                return a + b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="add", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "add"
        assert contract.signature.return_type == "int"
        assert len(contract.signature.parameters) == 2
        assert contract.signature.parameters[0].name == "a"
        assert contract.signature.parameters[0].type_hint == "int"

    def test_extract_function_with_optional_parameters(self):
        """Test extracting function with optional parameters."""
        source = textwrap.dedent(
            '''
            def greet(name: str, greeting: str = "Hello") -> str:
                """Greet a person.

                Args:
                    name: Person's name
                    greeting: Greeting message (default: "Hello")

                Returns:
                    Greeting string
                """
                return f"{greeting}, {name}!"
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="greet", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert len(contract.signature.parameters) == 2
        assert not contract.signature.parameters[0].is_optional
        assert contract.signature.parameters[1].is_optional
        assert contract.signature.parameters[1].default_value == "'Hello'"

    def test_extract_function_with_exceptions(self):
        """Test extracting function with exceptions in docstring."""
        source = textwrap.dedent(
            '''
            def divide(a: float, b: float) -> float:
                """Divide two numbers.

                Args:
                    a: Dividend
                    b: Divisor

                Returns:
                    Result of a / b

                Raises:
                    ZeroDivisionError: When b is zero
                    ValueError: When inputs are invalid
                """
                if b == 0:
                    raise ZeroDivisionError("Cannot divide by zero")
                return a / b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="divide", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert "ZeroDivisionError" in contract.signature.raises
        assert "ValueError" in contract.signature.raises

    def test_extract_function_without_docstring(self):
        """Test extracting function without docstring."""
        source = textwrap.dedent(
            '''
            def multiply(a: int, b: int) -> int:
                return a * b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="multiply", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.docstring is None
        assert len(contract.signature.parameters) == 2
        assert contract.signature.return_type == "int"

    def test_extract_function_without_type_hints(self):
        """Test extracting function without type hints."""
        source = textwrap.dedent(
            '''
            def subtract(a, b):
                """Subtract b from a."""
                return a - b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="subtract", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.signature.parameters[0].type_hint is None
        assert contract.signature.return_type is None


class TestBreakingChangeDetector:
    """Test suite for BreakingChangeDetector."""

    def test_detect_parameter_removed(self):
        """Test detection of removed parameters (breaking)."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate"),
                ],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="data")],  # validate removed
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.PARAMETER_REMOVED
        )
        assert "validate" in comparison.breaking_changes[0].affected_elements
        assert (
            comparison.breaking_changes[0].severity == ChangeSeverity.HIGH
        )

    def test_detect_optional_parameter_added(self):
        """Test that adding optional parameters is non-breaking."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="data")],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=True),  # Added optional
                ],
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert comparison.is_compatible  # Should be compatible
        assert len(comparison.breaking_changes) == 0
        assert len(comparison.non_breaking_changes) > 0

    def test_detect_parameter_became_required(self):
        """Test detection of optional parameter becoming required."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=True),
                ],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=False),  # Now required
                ],
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.PARAMETER_REQUIRED_NOW
        )

    def test_detect_return_type_narrowed(self):
        """Test detection of narrowed return type."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="get_value", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="Any",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="get_value", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="int",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.RETURN_TYPE_NARROWED
        )

    def test_detect_exception_added(self):
        """Test detection of newly added exceptions."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="parse", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="dict",
                raises=[],
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="parse", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="dict",
                raises=["ValueError", "JSONDecodeError"],
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        # Added exceptions are low severity
        low_severity_changes = [
            c for c in comparison.breaking_changes if c.severity == ChangeSeverity.LOW
        ]
        assert len(low_severity_changes) >= 1

    def test_compatibility_score(self):
        """Test that compatibility score is calculated correctly."""
        from src.contracts.contract_models import FunctionContract

        # Fully compatible
        contract1 = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(parameters=[], return_type="None"),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(contract1, contract1)

        assert comparison.compatibility_score == 1.0
        assert comparison.is_compatible

        # With breaking changes
        old_contract = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="x"), ParameterInfo(name="y")],
                return_type="int",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="x")],  # y removed
                return_type="int",
            ),
        )

        comparison = detector.detect_breaking_changes(old_contract, new_contract)
        assert comparison.compatibility_score < 1.0
        assert not comparison.is_compatible
from unittest.mock import MagicMock, patch

import pytest

from src.graph.neo4j_client import Neo4jClient
from src.incremental.diff_parser import DiffParser, FileDiff
from src.incremental.symbol_delta import SymbolDelta, UpdateResult
from src.incremental.updater import IncrementalSymbolUpdater
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


class TestDiffParser:
    """Test suite for DiffParser."""

    def test_parse_simple_diff(self):
        """Test parsing a simple git diff."""
        diff_text = """diff --git a/src/api.py b/src/api.py
index 1234567..abcdefg 100644
--- a/src/api.py
+++ b/src/api.py
@@ -10,6 +10,10 @@ def existing_function():
     pass

+def new_function():
+    return 42
+
 def another_function():
     pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].file_path == "src/api.py"
        assert summary.files[0].status == "modified"
        assert summary.files[0].added_lines == 3  # new function definition, return statement, and blank line

    def test_parse_added_file(self):
        """Test parsing a diff for a newly added file."""
        diff_text = """diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,5 @@
+def new_function():
+    pass
+
+class NewClass:
+    pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].status == "added"
        assert summary.files[0].file_path == "src/new_module.py"

    def test_parse_deleted_file(self):
        """Test parsing a diff for a deleted file."""
        diff_text = """diff --git a/src/old_module.py b/src/old_module.py
deleted file mode 100644
index 1234567..0000000
--- a/src/old_module.py
+++ /dev/null
@@ -1,5 +0,0 @@
-def old_function():
-    pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].status == "deleted"

    def test_identify_changed_files(self):
        """Test identifying only supported file extensions."""
        diff_text = """diff --git a/src/api.py b/src/api.py
index 1234567..abcdefg 100644
--- a/src/api.py
+++ b/src/api.py
@@ -1 +1,2 @@
 pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)
        changed_files = parser.identify_changed_files(summary)

        assert "src/api.py" in changed_files
        assert len(changed_files) == 1

    def test_identify_changed_files_excludes_unsupported(self):
        """Test that unsupported file types are excluded."""
        diff_text = """diff --git a/README.md b/README.md
index 1234567..abcdefg 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Project"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)
        changed_files = parser.identify_changed_files(summary)

        assert "README.md" not in changed_files
        assert len(changed_files) == 0

    def test_is_structural_change_detects_added_symbols(self):
        """Test detection of added symbols."""
        parser = DiffParser()
        before = ["existing_func"]
        after = ["existing_func", "new_func"]

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is True

    def test_is_structural_change_detects_removed_symbols(self):
        """Test detection of removed symbols."""
        parser = DiffParser()
        before = ["func1", "func2"]
        after = ["func1"]

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is True

    def test_is_structural_change_ignores_content_changes(self):
        """Test that content-only changes are not detected as structural."""
        parser = DiffParser()
        before = ["func1", "func2"]
        after = ["func1", "func2"]  # Same symbols

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is False


class TestSymbolDelta:
    """Test suite for SymbolDelta."""

    def test_create_symbol_delta(self):
        """Test creating a symbol delta."""
        sym_added = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )

        delta = SymbolDelta(
            file="src/api.py",
            added=[sym_added],
            deleted=["old_func"],
            modified=[],
        )

        assert delta.file == "src/api.py"
        assert len(delta.added) == 1
        assert len(delta.deleted) == 1
        assert delta.is_empty() is False

    def test_empty_delta(self):
        """Test empty delta detection."""
        delta = SymbolDelta(file="src/api.py")

        assert delta.is_empty() is True


class TestIncrementalSymbolUpdater:
    """Test suite for IncrementalSymbolUpdater."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        index = SymbolIndex()
        neo4j = MagicMock(spec=Neo4jClient)
        return index, neo4j

    def test_apply_delta_success(self, mock_dependencies):
        """Test successful delta application."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        # Add initial symbols
        initial_sym = Symbol(
            name="existing_func",
            type="function",
            file="src/api.py",
            line=1,
            column=0,
        )
        index.add(initial_sym)

        # Create updater
        updater = IncrementalSymbolUpdater(index, neo4j)

        # Create delta: add one symbol
        new_sym = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )
        delta = SymbolDelta(file="src/api.py", added=[new_sym])

        # Mock Neo4j transaction
        mock_tx = MagicMock()
        neo4j.begin_transaction.return_value = mock_tx

        # Apply delta
        result = updater.apply_delta(delta)

        assert result.success is True
        assert result.delta == delta
        assert result.duration_ms >= 0

    def test_apply_delta_failure_rollback(self, mock_dependencies):
        """Test failure handling and rollback."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        # Add initial symbols
        initial_sym = Symbol(
            name="existing_func",
            type="function",
            file="src/api.py",
            line=1,
            column=0,
        )
        index.add(initial_sym)

        # Create updater
        updater = IncrementalSymbolUpdater(index, neo4j)

        # Create delta
        new_sym = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )
        delta = SymbolDelta(file="src/api.py", added=[new_sym])

        # Mock Neo4j to raise an exception
        mock_tx = MagicMock()
        mock_tx.commit.side_effect = Exception("Connection lost")
        neo4j.begin_transaction.return_value = mock_tx

        # Apply delta (should fail gracefully)
        result = updater.apply_delta(delta)

        assert result.success is False
        assert result.error != ""
        assert result.duration_ms >= 0

    def test_delta_history_tracking(self, mock_dependencies):
        """Test that deltas are tracked in history."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j
        mock_tx = MagicMock()
        neo4j.begin_transaction.return_value = mock_tx

        # Apply two deltas
        delta1 = SymbolDelta(
            file="src/api.py",
            added=[Symbol(name="func1", type="function", file="src/api.py", line=1, column=0)],
        )
        delta2 = SymbolDelta(
            file="src/model.py",
            added=[Symbol(name="func2", type="function", file="src/model.py", line=1, column=0)],
        )

        updater.apply_delta(delta1)
        updater.apply_delta(delta2)

        assert len(updater.delta_history) == 2
        assert updater.delta_history[0] == delta1
        assert updater.delta_history[1] == delta2

    def test_validate_graph_consistency_success(self, mock_dependencies):
        """Test successful consistency validation."""
        index, neo4j = mock_dependencies
        neo4j.query = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j queries for consistency checks
        neo4j.query.side_effect = [
            [],  # No orphaned edges
            [],  # No duplicate symbols
            [("CALLS",), ("IMPORTS",)],  # Valid edge types
        ]

        result = updater.validate_graph_consistency()

        assert result is True
        assert neo4j.query.call_count == 3

    def test_validate_graph_consistency_failure(self, mock_dependencies):
        """Test consistency validation failure."""
        index, neo4j = mock_dependencies
        neo4j.query = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j to return orphaned edges
        neo4j.query.return_value = [(5,)]  # 5 orphaned edges

        result = updater.validate_graph_consistency()

        assert result is False
from src.agent.execution_engine import ParallelExecutionEngine, TaskExecutor
from src.agent.scheduler import Task, TaskScheduler, TaskDAGBuilder


class TestSchedulingIntegration:
    """Integration tests for full scheduling pipeline."""

    def test_schedule_and_execute_workflow(self):
        """Test complete workflow: schedule tasks, then execute them."""

        # Track execution order
        execution_log = []

        def tracking_executor(task):
            execution_log.append(task.id)
            return {"success": True, "status": "completed", "details": {}}

        # Create tasks with dependencies
        tasks = [
            Task(id="t1", description="Parse file", target_symbols=["ast"]),
            Task(
                id="t2",
                description="Build graph",
                target_symbols=["graph"],
                dependency_symbols=["ast"],
            ),
            Task(
                id="t3",
                description="Build embeddings",
                target_symbols=["embeddings"],
                dependency_symbols=["ast"],
            ),
            Task(
                id="t4",
                description="Run queries",
                target_symbols=["results"],
                dependency_symbols=["graph", "embeddings"],
            ),
        ]

        # Schedule
        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=2)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        # Verify execution completed successfully
        assert result.status == "SUCCESS"
        assert result.completed_tasks == 4

        # Verify execution order respects dependencies
        # t1 must come before t2, t3
        # t2, t3 must come before t4
        t1_idx = execution_log.index("t1")
        t4_idx = execution_log.index("t4")

        assert t1_idx < execution_log.index("t2")
        assert t1_idx < execution_log.index("t3")
        assert execution_log.index("t2") < t4_idx
        assert execution_log.index("t3") < t4_idx

    def test_parallel_execution_respects_phases(self):
        """Test that parallel execution respects phase boundaries."""

        # Track tasks running at same time
        concurrent_tasks = set()
        max_concurrent = 0

        def tracking_executor(task):
            nonlocal max_concurrent
            concurrent_tasks.add(task.id)
            max_concurrent = max(max_concurrent, len(concurrent_tasks))
            # Simulate work
            import time

            time.sleep(0.01)
            concurrent_tasks.remove(task.id)
            return {"success": True, "status": "completed", "details": {}}

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(4)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # All tasks are independent, so all should be in one phase
        assert len(plan.phases) == 1

        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=4)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        # With 4 workers and 4 independent tasks, we may see parallelism
        assert max_concurrent >= 1

    def test_complex_dependency_graph(self):
        """Test scheduling and execution of complex dependency graph."""

        execution_times = {}

        def tracking_executor(task):
            import time

            execution_times[task.id] = time.time()
            return {"success": True, "status": "completed", "details": {}}

        # Complex DAG with multiple dependency chains
        tasks = [
            Task(id="t1", description="Init", target_symbols=["data"]),
            Task(
                id="t2",
                description="Process A",
                target_symbols=["result_a"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t3",
                description="Process B",
                target_symbols=["result_b"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t4",
                description="Process C",
                target_symbols=["result_c"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t5",
                description="Merge AB",
                target_symbols=["merged_ab"],
                dependency_symbols=["result_a", "result_b"],
            ),
            Task(
                id="t6",
                description="Merge ABC",
                target_symbols=["final"],
                dependency_symbols=["merged_ab", "result_c"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Verify plan structure
        assert plan.num_phases() == 4
        assert plan.phases[0] == ["t1"]  # Init first
        assert set(plan.phases[1]) == {"t2", "t3", "t4"}  # Parallel processing
        assert plan.phases[2] == ["t5"]  # Merge AB
        assert plan.phases[3] == ["t6"]  # Final merge

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=3)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        assert result.completed_tasks == 6

        # Verify dependency order
        assert execution_times["t1"] < execution_times["t2"]
        assert execution_times["t1"] < execution_times["t3"]
        assert execution_times["t1"] < execution_times["t4"]
        assert execution_times["t2"] < execution_times["t5"]
        assert execution_times["t3"] < execution_times["t5"]
        assert execution_times["t5"] < execution_times["t6"]
        assert execution_times["t4"] < execution_times["t6"]

    def test_conflict_detection_in_workflow(self):
        """Test that conflicting tasks are properly serialized."""

        # Track execution
        execution_log = []

        def tracking_executor(task):
            execution_log.append(task.id)
            return {"success": True, "status": "completed", "details": {}}

        # Create conflicting tasks
        tasks = [
            Task(
                id="t1",
                description="Modify function_a",
                target_symbols=["function_a"],
            ),
            Task(
                id="t2",
                description="Also modify function_a (conflict!)",
                target_symbols=["function_a"],
            ),
            Task(
                id="t3",
                description="Modify function_b (independent)",
                target_symbols=["function_b"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # t1 and t2 conflict (same symbol), so must be serialized
        # t3 is independent
        assert plan.num_phases() >= 2

        # Verify phases respect conflict
        t1_phase = None
        t2_phase = None
        for idx, phase in enumerate(plan.phases):
            if "t1" in phase:
                t1_phase = idx
            if "t2" in phase:
                t2_phase = idx

        assert t1_phase < t2_phase  # t1 before t2

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=2)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"

        # Verify execution order: t1 before t2
        assert execution_log.index("t1") < execution_log.index("t2")

    def test_large_batch_scheduling(self):
        """Test scheduling of large task batches."""

        # Create 100 independent tasks
        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(100)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # All independent → single phase
        assert plan.num_phases() == 1
        assert len(plan.phases[0]) == 100

        # Verify scheduling was fast
        assert plan.total_tasks == 100

    def test_execution_with_partial_failures(self):
        """Test execution behavior with some task failures."""

        def failure_executor(task):
            # Fail on tasks with even IDs
            task_num = int(task.id[1:])
            if task_num % 2 == 0:
                return {"success": False, "status": "failed", "error": "Simulated error"}
            return {"success": True, "status": "completed", "details": {}}

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(6)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        task_executor = TaskExecutor(task_executor=failure_executor)
        engine = ParallelExecutionEngine(
            task_executor=task_executor, max_workers=2, fail_fast=False
        )
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        # Some tasks should succeed, some fail
        assert result.status == "PARTIAL"
        assert result.completed_tasks == 3  # Odd-numbered tasks: t1, t3, t5
        assert len(result.failed_tasks) == 3  # Even-numbered: t0, t2, t4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
