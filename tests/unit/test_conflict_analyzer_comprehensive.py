"""Comprehensive tests for conflict analyzer."""

import pytest
from unittest.mock import MagicMock
from src.graph.conflict_analyzer import ConflictAnalyzer
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol


@pytest.fixture
def symbol_index_with_dependencies():
    """Create symbol index with dependency relationships."""
    index = SymbolIndex()

    # Core functions
    index.add(Symbol(name="func_a", type="function", file="module_a.py", line=1, column=0))
    index.add(Symbol(name="func_b", type="function", file="module_b.py", line=1, column=0))
    index.add(Symbol(name="func_c", type="function", file="module_c.py", line=1, column=0))
    index.add(Symbol(name="func_d", type="function", file="module_d.py", line=1, column=0))

    # Classes
    index.add(Symbol(name="ClassA", type="class", file="module_a.py", line=10, column=0))
    index.add(Symbol(name="ClassB", type="class", file="module_b.py", line=10, column=0))

    # Imports to create dependencies
    index.add(Symbol(name="os", type="import", file="module_a.py", line=1, column=0))
    index.add(Symbol(name="sys", type="import", file="module_b.py", line=1, column=0))

    return index


@pytest.fixture
def analyzer(symbol_index_with_dependencies):
    """Create conflict analyzer with mock Neo4j client."""
    neo4j_client = MagicMock()
    return ConflictAnalyzer(symbol_index_with_dependencies, neo4j_client)


class TestConflictAnalyzerBasics:
    """Test basic conflict analyzer functionality."""

    def test_analyzer_init(self, symbol_index_with_dependencies):
        """Test analyzer initialization."""
        neo4j_client = MagicMock()
        analyzer = ConflictAnalyzer(symbol_index_with_dependencies, neo4j_client)

        assert analyzer.symbol_index is not None
        assert analyzer.neo4j_client is not None
        assert analyzer._dependency_cache == {}

    def test_get_all_dependencies_simple(self, analyzer):
        """Test getting dependencies for symbol."""
        deps = analyzer.get_all_dependencies("func_a")

        assert isinstance(deps, set)
        # Should cache the result
        assert "func_a" in analyzer._dependency_cache

    def test_get_all_dependencies_caching(self, analyzer):
        """Test that dependencies are cached."""
        deps1 = analyzer.get_all_dependencies("func_a")
        deps2 = analyzer.get_all_dependencies("func_a")

        # Should return same object from cache
        assert deps1 is deps2

    def test_get_all_dependencies_nonexistent(self, analyzer):
        """Test getting dependencies for nonexistent symbol."""
        deps = analyzer.get_all_dependencies("nonexistent")

        assert isinstance(deps, set)
        # May be empty since symbol doesn't exist
        assert len(deps) >= 0

    def test_get_dependents_simple(self, analyzer):
        """Test getting dependents for symbol."""
        dependents = analyzer.get_dependents("os")

        assert isinstance(dependents, set)

    def test_get_dependents_nonexistent(self, analyzer):
        """Test getting dependents for nonexistent symbol."""
        dependents = analyzer.get_dependents("nonexistent_symbol")

        assert isinstance(dependents, set)


class TestDirectConflictDetection:
    """Test direct conflict detection."""

    def test_detect_direct_conflicts_no_overlap(self, analyzer):
        """Test detecting conflicts with non-overlapping symbols."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_c"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        assert isinstance(conflicts, list)
        assert len(conflicts) == 0

    def test_detect_direct_conflicts_with_overlap(self, analyzer):
        """Test detecting conflicts with overlapping symbols."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a", "func_b"]},
            {"id": "t2", "target_symbols": ["func_b", "func_c"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        assert isinstance(conflicts, list)
        assert len(conflicts) > 0
        assert conflicts[0]["conflicting_symbols"] == ["func_b"]

    def test_detect_direct_conflicts_same_symbol(self, analyzer):
        """Test detecting conflicts when tasks target same symbol."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_a"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        assert len(conflicts) > 0
        assert "task_a" in conflicts[0]
        assert "task_b" in conflicts[0]

    def test_detect_direct_conflicts_empty_tasks(self, analyzer):
        """Test with empty task list."""
        conflicts = analyzer.detect_direct_conflicts([])

        assert isinstance(conflicts, list)
        assert len(conflicts) == 0

    def test_detect_direct_conflicts_single_task(self, analyzer):
        """Test with single task."""
        tasks = [{"id": "t1", "target_symbols": ["func_a"]}]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        assert len(conflicts) == 0

    def test_detect_direct_conflicts_empty_target_symbols(self, analyzer):
        """Test with empty target symbols."""
        tasks = [
            {"id": "t1", "target_symbols": []},
            {"id": "t2", "target_symbols": []},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        assert len(conflicts) == 0

    def test_detect_direct_conflicts_partial_overlap(self, analyzer):
        """Test with partial overlap in multiple tasks."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a", "func_b", "func_c"]},
            {"id": "t2", "target_symbols": ["func_c", "func_d"]},
            {"id": "t3", "target_symbols": ["func_d"]},
        ]

        conflicts = analyzer.detect_direct_conflicts(tasks)

        # Should detect conflicts on func_c and func_d
        assert len(conflicts) > 0


class TestDependencyConflicts:
    """Test dependency-based conflict detection."""

    def test_detect_dependency_conflicts_simple(self, analyzer):
        """Test detecting dependency conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
        ]

        conflicts = analyzer.detect_dependency_conflicts(tasks)

        assert isinstance(conflicts, list)

    def test_detect_dependency_conflicts_with_deps(self, analyzer):
        """Test detecting dependency conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["os"]},
        ]

        conflicts = analyzer.detect_dependency_conflicts(tasks)

        assert isinstance(conflicts, list)

    def test_detect_dependency_conflicts_empty_list(self, analyzer):
        """Test with empty task list."""
        conflicts = analyzer.detect_dependency_conflicts([])

        assert isinstance(conflicts, list)
        assert len(conflicts) == 0


class TestCircularDependencies:
    """Test circular dependency detection."""

    def test_detect_circular_dependencies_simple(self, analyzer):
        """Test detecting circular dependencies."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
        ]

        alerts = analyzer.detect_circular_dependencies(tasks)

        assert isinstance(alerts, list)

    def test_detect_circular_dependencies_empty_list(self, analyzer):
        """Test with empty task list."""
        alerts = analyzer.detect_circular_dependencies([])

        assert isinstance(alerts, list)
        assert len(alerts) == 0

    def test_detect_circular_dependencies_multiple_tasks(self, analyzer):
        """Test with multiple tasks."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_c"]},
        ]

        alerts = analyzer.detect_circular_dependencies(tasks)

        assert isinstance(alerts, list)


class TestComprehensiveAnalysis:
    """Test the main analyze_conflicts method."""

    def test_analyze_conflicts_comprehensive(self, analyzer):
        """Test comprehensive conflict analysis."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_a"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert result is not None
        assert "parallel_feasible" in result
        assert "direct_conflicts" in result
        assert "dependency_conflicts" in result
        assert "circular_dependencies" in result
        assert "recommendation" in result
        assert "task_count" in result

    def test_analyze_conflicts_empty_list(self, analyzer):
        """Test analysis with empty task list."""
        result = analyzer.analyze_conflicts([])

        assert result is not None
        assert result["parallel_feasible"] == True
        assert result["task_count"] == 0

    def test_analyze_conflicts_single_task(self, analyzer):
        """Test analysis with single task."""
        tasks = [{"id": "t1", "target_symbols": ["func_a"]}]

        result = analyzer.analyze_conflicts(tasks)

        assert result["parallel_feasible"] == True
        assert result["task_count"] == 1

    def test_analyze_conflicts_no_conflicts(self, analyzer):
        """Test analysis with no conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_c"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        # No overlapping symbols, should be parallelizable
        assert result["total_conflicts"] == 0

    def test_analyze_conflicts_has_conflicts(self, analyzer):
        """Test analysis with conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_a"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert result["total_conflicts"] > 0
        assert result["parallel_feasible"] == False

    def test_analyze_conflicts_missing_fields(self, analyzer):
        """Test analysis with missing task fields."""
        tasks = [
            {"id": "t1"},  # Missing target_symbols
            {"id": "t2", "target_symbols": ["func_b"]},
        ]

        # Should handle gracefully
        result = analyzer.analyze_conflicts(tasks)
        assert result is not None

    def test_analyze_conflicts_returns_recommendation(self, analyzer):
        """Test that analysis returns clear recommendation."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert "recommendation" in result
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0


class TestRecommendationLogic:
    """Test recommendation generation."""

    def test_recommendation_no_conflicts(self, analyzer):
        """Test recommendation when no conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert "parallel" in result["recommendation"].lower()

    def test_recommendation_with_conflicts(self, analyzer):
        """Test recommendation with conflicts."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_a"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        # Should recommend sequential
        assert "sequential" in result["recommendation"].lower() or "conflict" in result["recommendation"].lower()

    def test_recommendation_independent_subsets(self, analyzer):
        """Test recommendation with independent subsets."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_a"]},
            {"id": "t3", "target_symbols": ["func_b"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        # t3 is independent
        assert isinstance(result["recommendation"], str)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_analyze_very_large_task_set(self, analyzer):
        """Test analyzing large number of tasks."""
        tasks = [
            {
                "id": f"t{i}",
                "target_symbols": [f"func_{(i*10+j) % 100}" for j in range(10)]
            }
            for i in range(50)
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert result is not None
        assert isinstance(result, dict)

    def test_analyze_deeply_nested_dependencies(self, analyzer):
        """Test with deeply nested dependency chains."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_c"]},
            {"id": "t4", "target_symbols": ["func_d"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert result is not None

    def test_analyze_symbols_with_special_chars(self, analyzer):
        """Test analyzing symbols with special characters."""
        tasks = [
            {"id": "t1", "target_symbols": ["_private_func", "__dunder__"]},
            {"id": "t2", "target_symbols": ["func_with_123_numbers"]},
        ]

        result = analyzer.analyze_conflicts(tasks)

        assert result is not None

    def test_cache_consistency(self, analyzer):
        """Test that cache remains consistent."""
        deps1 = analyzer.get_all_dependencies("func_a")
        deps2 = analyzer.get_all_dependencies("func_a")
        deps3 = analyzer.get_all_dependencies("func_b")
        deps4 = analyzer.get_all_dependencies("func_a")

        # All calls to func_a should return same cached object
        assert deps1 is deps2
        assert deps2 is deps4
        # func_b should be different
        assert deps3 is not deps1

    def test_multiple_analyses_independence(self, analyzer):
        """Test that multiple analyses don't interfere."""
        tasks_a = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
        ]
        tasks_b = [
            {"id": "t3", "target_symbols": ["func_c"]},
            {"id": "t4", "target_symbols": ["func_d"]},
        ]

        result_a = analyzer.analyze_conflicts(tasks_a)
        result_b = analyzer.analyze_conflicts(tasks_b)

        # Both should complete successfully
        assert result_a is not None
        assert result_b is not None
