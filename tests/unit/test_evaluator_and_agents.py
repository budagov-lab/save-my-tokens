"""Tests for agent evaluator and baseline agent."""

import pytest
from unittest.mock import MagicMock, patch
from src.agent.evaluator import AgentEvaluator
from src.agent.baseline_agent import BaselineAgent
from src.agent.base_agent import BaseAgent
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol
from src.api.query_service import QueryService


@pytest.fixture
def test_symbol_index():
    """Create test symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func1", type="function", file="test.py", line=1, column=0))
    index.add(Symbol(name="func2", type="function", file="test.py", line=10, column=0))
    index.add(Symbol(name="TestClass", type="class", file="test.py", line=20, column=0))
    return index


@pytest.fixture
def query_service(test_symbol_index):
    """Create query service."""
    return QueryService(test_symbol_index)


class TestAgentEvaluator:
    """Test agent evaluator."""

    def test_evaluator_init(self, test_symbol_index, query_service):
        """Test evaluator initialization."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service,
            token_budget=4000
        )

        assert evaluator.repo_path == "/test/repo"
        assert evaluator.symbol_index is not None
        assert evaluator.query_service is not None
        assert evaluator.token_budget == 4000
        assert evaluator.graph_api_agent is not None
        assert evaluator.baseline_agent is not None

    def test_evaluator_init_custom_token_budget(self, test_symbol_index, query_service):
        """Test evaluator with custom token budget."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service,
            token_budget=8000
        )

        assert evaluator.token_budget == 8000

    def test_run_benchmark_empty_tasks(self, test_symbol_index, query_service):
        """Test benchmark with empty task list."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        result = evaluator.run_benchmark([])

        assert result is not None
        assert result["task_count"] == 0
        assert "graph_api" in result
        assert "baseline" in result
        assert "comparison" in result

    def test_run_benchmark_single_task(self, test_symbol_index, query_service):
        """Test benchmark with single task."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        task = {"id": "t1", "target_symbols": ["func1"], "description": "Test task"}
        result = evaluator.run_benchmark([task])

        assert result["task_count"] == 1
        assert "results" in result["graph_api"]
        assert "results" in result["baseline"]

    def test_run_benchmark_multiple_tasks(self, test_symbol_index, query_service):
        """Test benchmark with multiple tasks."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        tasks = [
            {"id": "t1", "target_symbols": ["func1"]},
            {"id": "t2", "target_symbols": ["func2"]},
            {"id": "t3", "target_symbols": ["TestClass"]},
        ]
        result = evaluator.run_benchmark(tasks)

        assert result["task_count"] == 3
        assert len(result["graph_api"]["results"]) == 3
        assert len(result["baseline"]["results"]) == 3

    def test_run_agent_tasks_returns_stats(self, test_symbol_index, query_service):
        """Test that _run_agent_tasks returns statistics."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        task = {"id": "t1", "target_symbols": ["func1"]}
        agent_results = evaluator._run_agent_tasks(evaluator.graph_api_agent, [task])

        assert "results" in agent_results
        assert "statistics" in agent_results
        assert "execution_time_seconds" in agent_results
        assert "agent_type" in agent_results

    def test_run_agent_tasks_timing(self, test_symbol_index, query_service):
        """Test that execution time is recorded."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        task = {"id": "t1", "target_symbols": ["func1"]}
        agent_results = evaluator._run_agent_tasks(evaluator.graph_api_agent, [task])

        assert agent_results["execution_time_seconds"] >= 0

    def test_compare_results(self, test_symbol_index, query_service):
        """Test result comparison."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        # Create results with proper statistics structure
        graph_api_stats = {
            "success_rate": 0.95,
            "avg_tokens_used": 800,
            "tasks_completed": 1
        }
        baseline_stats = {
            "success_rate": 0.90,
            "avg_tokens_used": 1500,
            "tasks_completed": 1
        }

        graph_api_results = {
            "results": [{"status": "success"}],
            "statistics": graph_api_stats,
            "execution_time_seconds": 0.5,
            "agent_type": "BaseAgent"
        }
        baseline_results = {
            "results": [{"status": "success"}],
            "statistics": baseline_stats,
            "execution_time_seconds": 1.0,
            "agent_type": "BaselineAgent"
        }

        comparison = evaluator._compare_results(graph_api_results, baseline_results)

        # Comparison should have improvement metrics
        assert comparison is not None
        assert isinstance(comparison, dict)
        assert "success_rate_improvement_pct" in comparison
        assert "token_efficiency_improvement_pct" in comparison
        assert "winner" in comparison

    def test_benchmark_agents_execute_independently(self, test_symbol_index, query_service):
        """Test that agents execute independently without interference."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        task = {"id": "t1", "target_symbols": ["func1"]}

        # Run both agents
        graph_api_results = evaluator._run_agent_tasks(evaluator.graph_api_agent, [task])
        baseline_results = evaluator._run_agent_tasks(evaluator.baseline_agent, [task])

        # Both should complete without interference
        assert graph_api_results["agent_type"] == "BaseAgent"
        assert baseline_results["agent_type"] == "BaselineAgent"


class TestBaselineAgent:
    """Test baseline agent."""

    def test_baseline_agent_init(self, test_symbol_index):
        """Test baseline agent initialization."""
        agent = BaselineAgent(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            token_budget=4000
        )

        assert str(agent.repo_path) == str("/test/repo") or "repo" in str(agent.repo_path)
        assert agent.symbol_index is not None
        assert agent.token_budget == 4000

    def test_baseline_agent_execute_task(self, test_symbol_index):
        """Test baseline agent task execution."""
        agent = BaselineAgent(
            repo_path="/test/repo",
            symbol_index=test_symbol_index
        )

        task = {"id": "t1", "target_symbols": ["func1"]}
        result = agent.execute_task(task)

        assert result is not None
        assert isinstance(result, dict)

    def test_baseline_agent_get_statistics(self, test_symbol_index):
        """Test getting agent statistics."""
        agent = BaselineAgent(
            repo_path="/test/repo",
            symbol_index=test_symbol_index
        )

        stats = agent.get_statistics()

        assert stats is not None
        assert isinstance(stats, dict)

    def test_baseline_agent_task_results_tracking(self, test_symbol_index):
        """Test task results are tracked."""
        agent = BaselineAgent(
            repo_path="/test/repo",
            symbol_index=test_symbol_index
        )

        task = {"id": "t1", "target_symbols": ["func1"]}
        result = agent.execute_task(task)
        agent.task_results.append(result)

        assert len(agent.task_results) >= 1


class TestBaseAgent:
    """Test base agent."""

    def test_base_agent_init(self, test_symbol_index, query_service):
        """Test base agent initialization."""
        agent = BaseAgent(
            query_service=query_service,
            symbol_index=test_symbol_index,
            token_budget=4000
        )

        assert agent.query_service is not None
        assert agent.symbol_index is not None
        assert agent.token_budget == 4000

    def test_base_agent_execute_task(self, test_symbol_index, query_service):
        """Test base agent task execution."""
        agent = BaseAgent(
            query_service=query_service,
            symbol_index=test_symbol_index
        )

        task = {"id": "t1", "target_symbols": ["func1"]}
        result = agent.execute_task(task)

        assert result is not None
        assert isinstance(result, dict)

    def test_base_agent_get_statistics(self, test_symbol_index, query_service):
        """Test base agent statistics."""
        agent = BaseAgent(
            query_service=query_service,
            symbol_index=test_symbol_index
        )

        stats = agent.get_statistics()

        assert stats is not None
        assert isinstance(stats, dict)

    def test_base_agent_handles_missing_symbols(self, test_symbol_index, query_service):
        """Test base agent gracefully handles missing symbols."""
        agent = BaseAgent(
            query_service=query_service,
            symbol_index=test_symbol_index
        )

        task = {"id": "t1", "target_symbols": ["nonexistent_func"]}
        result = agent.execute_task(task)

        # Should not raise, should handle gracefully
        assert result is not None

    def test_base_agent_multiple_target_symbols(self, test_symbol_index, query_service):
        """Test base agent with multiple target symbols."""
        agent = BaseAgent(
            query_service=query_service,
            symbol_index=test_symbol_index
        )

        task = {
            "id": "t1",
            "target_symbols": ["func1", "func2", "TestClass"]
        }
        result = agent.execute_task(task)

        assert result is not None


class TestAgentComparison:
    """Test agent comparison utilities."""

    def test_agents_produce_consistent_results(self, test_symbol_index, query_service):
        """Test that agents produce results for same task."""
        graph_agent = BaseAgent(query_service, test_symbol_index)
        baseline_agent = BaselineAgent("/test/repo", test_symbol_index)

        task = {"id": "t1", "target_symbols": ["func1"]}

        graph_result = graph_agent.execute_task(task)
        baseline_result = baseline_agent.execute_task(task)

        # Both should return results
        assert graph_result is not None
        assert baseline_result is not None

    def test_evaluator_comparison_format(self, test_symbol_index, query_service):
        """Test evaluator produces properly formatted comparison."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=test_symbol_index,
            query_service=query_service
        )

        tasks = [
            {"id": "t1", "target_symbols": ["func1"]},
            {"id": "t2", "target_symbols": ["func2"]},
        ]

        result = evaluator.run_benchmark(tasks)

        # Check structure
        assert "task_count" in result
        assert "graph_api" in result
        assert "baseline" in result
        assert "comparison" in result

        # Check nested structure
        assert "results" in result["graph_api"]
        assert "statistics" in result["graph_api"]
        assert "execution_time_seconds" in result["graph_api"]
