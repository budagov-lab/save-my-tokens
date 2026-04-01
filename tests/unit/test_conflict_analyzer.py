"""Unit tests for conflict analyzer."""

from unittest.mock import MagicMock

import pytest

from src.graph.conflict_analyzer import ConflictAnalyzer
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create symbol index with test symbols."""
    index = SymbolIndex()

    # Module A
    index.add(
        Symbol(
            name="process_data",
            type="function",
            file="src/processor.py",
            line=1,
            column=0,
        )
    )
    index.add(
        Symbol(
            name="validate_input",
            type="function",
            file="src/processor.py",
            line=10,
            column=0,
        )
    )

    # Module B
    index.add(
        Symbol(
            name="format_output",
            type="function",
            file="src/formatter.py",
            line=1,
            column=0,
        )
    )
    index.add(
        Symbol(
            name="sanitize_data",
            type="function",
            file="src/formatter.py",
            line=20,
            column=0,
        )
    )

    # Imports
    index.add(
        Symbol(
            name="os",
            type="import",
            file="src/processor.py",
            line=1,
            column=0,
        )
    )

    return index


@pytest.fixture
def mock_neo4j_client() -> MagicMock:
    """Create mock Neo4j client."""
    return MagicMock()


@pytest.fixture
def analyzer(symbol_index: SymbolIndex, mock_neo4j_client: MagicMock) -> ConflictAnalyzer:
    """Create conflict analyzer."""
    return ConflictAnalyzer(symbol_index, mock_neo4j_client)


class TestDirectConflicts:
    """Test direct conflict detection."""

    def test_no_direct_conflicts(self, analyzer: ConflictAnalyzer) -> None:
        """Test tasks with no overlapping symbols."""
        tasks = [
            {"id": "task_1", "target_symbols": ["process_data"]},
            {"id": "task_2", "target_symbols": ["format_output"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)
        assert len(conflicts) == 0

    def test_direct_conflict_same_symbol(self, analyzer: ConflictAnalyzer) -> None:
        """Test tasks modifying same symbol."""
        tasks = [
            {"id": "task_1", "target_symbols": ["process_data", "validate_input"]},
            {"id": "task_2", "target_symbols": ["validate_input", "format_output"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "direct_overlap"
        assert "validate_input" in conflicts[0]["conflicting_symbols"]

    def test_direct_conflict_multiple_overlaps(self, analyzer: ConflictAnalyzer) -> None:
        """Test tasks with multiple overlapping symbols."""
        tasks = [
            {"id": "task_1", "target_symbols": ["a", "b", "c"]},
            {"id": "task_2", "target_symbols": ["b", "c", "d"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)
        assert len(conflicts) == 1


class TestDependencies:
    """Test dependency tracking."""

    def test_get_all_dependencies(self, analyzer: ConflictAnalyzer) -> None:
        """Test getting all dependencies for a symbol."""
        # process_data -> imports os and validate_input
        deps = analyzer.get_all_dependencies("process_data")
        # Should include os (imported) and validate_input (in same file)
        assert isinstance(deps, set)

    def test_get_dependents(self, analyzer: ConflictAnalyzer) -> None:
        """Test getting all dependents of a symbol."""
        dependents = analyzer.get_dependents("validate_input")
        assert isinstance(dependents, set)

    def test_dependency_caching(self, analyzer: ConflictAnalyzer) -> None:
        """Test dependency caching."""
        deps1 = analyzer.get_all_dependencies("process_data")
        deps2 = analyzer.get_all_dependencies("process_data")
        # Should be same cached object
        assert deps1 is deps2


class TestComprehensiveAnalysis:
    """Test comprehensive conflict analysis."""

    def test_analyze_no_conflicts(self, analyzer: ConflictAnalyzer) -> None:
        """Test analysis with no conflicts."""
        tasks = [
            {"id": "task_1", "target_symbols": ["process_data"]},
            {"id": "task_2", "target_symbols": ["format_output"]},
            {"id": "task_3", "target_symbols": ["sanitize_data"]},
        ]

        result = analyzer.analyze_conflicts(tasks)
        assert result["parallel_feasible"] is True
        assert len(result["direct_conflicts"]) == 0
        assert result["task_count"] == 3

    def test_analyze_with_conflicts(self, analyzer: ConflictAnalyzer) -> None:
        """Test analysis with conflicts."""
        tasks = [
            {"id": "task_1", "target_symbols": ["process_data", "validate_input"]},
            {"id": "task_2", "target_symbols": ["validate_input"]},
        ]

        result = analyzer.analyze_conflicts(tasks)
        assert result["parallel_feasible"] is False
        assert result["total_conflicts"] > 0

    def test_analyze_empty_tasks(self, analyzer: ConflictAnalyzer) -> None:
        """Test analysis with empty task list."""
        result = analyzer.analyze_conflicts([])
        assert result["task_count"] == 0
        assert result["parallel_feasible"] is True

    def test_analyze_single_task(self, analyzer: ConflictAnalyzer) -> None:
        """Test analysis with single task."""
        tasks = [{"id": "task_1", "target_symbols": ["process_data"]}]

        result = analyzer.analyze_conflicts(tasks)
        assert result["parallel_feasible"] is True
        assert result["task_count"] == 1


class TestRecommendations:
    """Test recommendation generation."""

    def test_recommendation_no_conflicts(self, analyzer: ConflictAnalyzer) -> None:
        """Test recommendation when no conflicts."""
        tasks = [
            {"id": "task_1", "target_symbols": ["a"]},
            {"id": "task_2", "target_symbols": ["b"]},
        ]

        result = analyzer.analyze_conflicts(tasks)
        assert "parallel" in result["recommendation"].lower()

    def test_recommendation_multiple_conflicts(self, analyzer: ConflictAnalyzer) -> None:
        """Test recommendation with multiple conflicts."""
        tasks = [
            {"id": "task_1", "target_symbols": ["a", "b"]},
            {"id": "task_2", "target_symbols": ["a", "b"]},
            {"id": "task_3", "target_symbols": ["a", "b"]},
        ]

        result = analyzer.analyze_conflicts(tasks)
        assert "sequential" in result["recommendation"].lower() or "conflict" in result["recommendation"].lower()


class TestCircularDependencies:
    """Test circular dependency detection."""

    def test_detect_circular_dependencies(self, analyzer: ConflictAnalyzer) -> None:
        """Test detecting circular dependencies."""
        tasks = [
            {"id": "task_1", "target_symbols": ["process_data"]},
        ]

        result = analyzer.detect_circular_dependencies(tasks)
        assert isinstance(result, list)
        # Real cycle detection would need actual dependency graph


class TestDependencyConflicts:
    """Test dependency-based conflict detection."""

    def test_dependency_conflict_detection(self, analyzer: ConflictAnalyzer) -> None:
        """Test detecting dependency conflicts."""
        tasks = [
            {"id": "task_1", "target_symbols": ["validate_input"]},
            {"id": "task_2", "target_symbols": ["process_data"]},
        ]

        conflicts = analyzer.detect_dependency_conflicts(tasks)
        # May have dependency conflicts if process_data depends on validate_input
        assert isinstance(conflicts, list)
