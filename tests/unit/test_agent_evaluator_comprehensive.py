"""Comprehensive tests for agent evaluator."""

from unittest.mock import MagicMock, patch

import pytest

from src.agent.evaluator import AgentEvaluator
from src.parsers.symbol_index import SymbolIndex
from src.api.query_service import QueryService


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    return SymbolIndex()


@pytest.fixture
def query_service(symbol_index):
    """Create query service."""
    return QueryService(symbol_index)


@pytest.fixture
def evaluator(symbol_index, query_service):
    """Create evaluator."""
    return AgentEvaluator(
        repo_path="/test/repo",
        symbol_index=symbol_index,
        query_service=query_service,
        token_budget=4000,
    )


class TestAgentEvaluatorInit:
    """Test AgentEvaluator initialization."""

    def test_init(self, symbol_index, query_service):
        """Test initialization."""
        evaluator = AgentEvaluator(
            repo_path="/test/repo",
            symbol_index=symbol_index,
            query_service=query_service,
            token_budget=4000,
        )

        assert evaluator.repo_path == "/test/repo"
        assert evaluator.token_budget == 4000
        assert evaluator.graph_api_agent is not None
        assert evaluator.baseline_agent is not None


class TestRunBenchmark:
    """Test benchmark execution."""

    def test_run_benchmark_empty_tasks(self, evaluator):
        """Test benchmark with empty task list."""
        result = evaluator.run_benchmark([])

        assert result["task_count"] == 0
        assert "graph_api" in result
        assert "baseline" in result
        assert "comparison" in result

    def test_run_benchmark_single_task(self, evaluator):
        """Test benchmark with single task."""
        tasks = [{"id": "t1", "target_symbols": ["func_a"]}]

        with patch.object(evaluator.graph_api_agent, 'execute_task', return_value={"status": "success"}):
            with patch.object(evaluator.baseline_agent, 'execute_task', return_value={"status": "success"}):
                with patch.object(evaluator.graph_api_agent, 'get_statistics', return_value={
                    "success_rate": 1.0,
                    "avg_tokens_used": 800,
                    "tasks_completed": 1,
                }):
                    with patch.object(evaluator.baseline_agent, 'get_statistics', return_value={
                        "success_rate": 0.9,
                        "avg_tokens_used": 1500,
                        "tasks_completed": 1,
                    }):
                        result = evaluator.run_benchmark(tasks)

                        assert result["task_count"] == 1
                        assert "comparison" in result

    def test_run_benchmark_multiple_tasks(self, evaluator):
        """Test benchmark with multiple tasks."""
        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
            {"id": "t3", "target_symbols": ["func_c"]},
        ]

        with patch.object(evaluator.graph_api_agent, 'execute_task', return_value={"status": "success"}):
            with patch.object(evaluator.baseline_agent, 'execute_task', return_value={"status": "success"}):
                with patch.object(evaluator.graph_api_agent, 'get_statistics', return_value={
                    "success_rate": 1.0,
                    "avg_tokens_used": 800,
                    "tasks_completed": 3,
                }):
                    with patch.object(evaluator.baseline_agent, 'get_statistics', return_value={
                        "success_rate": 0.9,
                        "avg_tokens_used": 1500,
                        "tasks_completed": 3,
                    }):
                        result = evaluator.run_benchmark(tasks)

                        assert result["task_count"] == 3


class TestRunAgentTasks:
    """Test agent task execution."""

    def test_run_agent_tasks(self, evaluator):
        """Test running tasks with agent."""
        tasks = [{"id": "t1", "target_symbols": ["func_a"]}]

        with patch.object(evaluator.graph_api_agent, 'execute_task', return_value={"status": "success"}):
            with patch.object(evaluator.graph_api_agent, 'get_statistics', return_value={
                "success_rate": 1.0,
                "avg_tokens_used": 800,
            }):
                result = evaluator._run_agent_tasks(evaluator.graph_api_agent, tasks)

                assert "results" in result
                assert "statistics" in result
                assert "execution_time_seconds" in result
                assert result["agent_type"] == "BaseAgent"

    def test_run_agent_tasks_empty(self, evaluator):
        """Test running no tasks."""
        with patch.object(evaluator.graph_api_agent, 'get_statistics', return_value={
            "success_rate": 1.0,
            "avg_tokens_used": 0,
        }):
            result = evaluator._run_agent_tasks(evaluator.graph_api_agent, [])

            assert result["results"] == []
            assert result["execution_time_seconds"] >= 0


class TestCompareResults:
    """Test result comparison."""

    def test_compare_results(self, evaluator):
        """Test comparing results between agents."""
        graph_api_results = {
            "results": [{"status": "success"}],
            "statistics": {
                "success_rate": 0.95,
                "avg_tokens_used": 800,
                "tasks_completed": 1,
            },
            "execution_time_seconds": 0.5,
            "agent_type": "BaseAgent",
        }
        baseline_results = {
            "results": [{"status": "success"}],
            "statistics": {
                "success_rate": 0.90,
                "avg_tokens_used": 1500,
                "tasks_completed": 1,
            },
            "execution_time_seconds": 1.0,
            "agent_type": "BaselineAgent",
        }

        comparison = evaluator._compare_results(graph_api_results, baseline_results)

        assert "success_rate_improvement_pct" in comparison
        assert "token_efficiency_improvement_pct" in comparison
        assert "execution_time_improvement_pct" in comparison
        assert "winner" in comparison
        assert comparison["success_rate_improvement_pct"] > 0
        assert comparison["token_efficiency_improvement_pct"] > 0

    def test_compare_results_equal_performance(self, evaluator):
        """Test comparing equal performance results."""
        graph_api_results = {
            "statistics": {
                "success_rate": 0.9,
                "avg_tokens_used": 1000,
            },
            "execution_time_seconds": 1.0,
        }
        baseline_results = {
            "statistics": {
                "success_rate": 0.9,
                "avg_tokens_used": 1000,
            },
            "execution_time_seconds": 1.0,
        }

        comparison = evaluator._compare_results(graph_api_results, baseline_results)

        assert "winner" in comparison


class TestDetermineWinner:
    """Test winner determination."""

    def test_determine_winner_graph_api_wins(self, evaluator):
        """Test Graph API wins."""
        graph_api_stats = {
            "success_rate": 0.95,
            "avg_tokens_used": 800,
        }
        baseline_stats = {
            "success_rate": 0.90,
            "avg_tokens_used": 1500,
        }

        winner = evaluator._determine_winner(graph_api_stats, baseline_stats)

        assert winner == "graph_api"

    def test_determine_winner_baseline_wins(self, evaluator):
        """Test baseline wins."""
        graph_api_stats = {
            "success_rate": 0.80,
            "avg_tokens_used": 2000,
        }
        baseline_stats = {
            "success_rate": 0.95,
            "avg_tokens_used": 800,
        }

        winner = evaluator._determine_winner(graph_api_stats, baseline_stats)

        assert winner == "baseline"

    def test_determine_winner_tie(self, evaluator):
        """Test tie."""
        graph_api_stats = {
            "success_rate": 0.9,
            "avg_tokens_used": 1000,
        }
        baseline_stats = {
            "success_rate": 0.9,
            "avg_tokens_used": 1000,
        }

        winner = evaluator._determine_winner(graph_api_stats, baseline_stats)

        assert winner == "tie"


class TestPrintReport:
    """Test report printing."""

    def test_print_report_basic(self, evaluator, capsys):
        """Test printing basic report."""
        benchmark_results = {
            "task_count": 1,
            "graph_api": {
                "statistics": {
                    "success_rate": 0.95,
                    "avg_tokens_used": 800,
                },
                "execution_time_seconds": 0.5,
            },
            "baseline": {
                "statistics": {
                    "success_rate": 0.90,
                    "avg_tokens_used": 1500,
                },
                "execution_time_seconds": 1.0,
            },
            "comparison": {
                "success_rate_improvement_pct": 5.0,
                "token_efficiency_improvement_pct": 46.67,
                "execution_time_improvement_pct": 50.0,
                "winner": "graph_api",
            },
        }

        evaluator.print_report(benchmark_results)

        captured = capsys.readouterr()
        assert "AGENT EVALUATION BENCHMARK REPORT" in captured.out
        assert "GRAPH API AGENT" in captured.out
        assert "BASELINE AGENT" in captured.out
        assert "COMPARISON" in captured.out

    def test_print_report_high_token_improvement(self, evaluator, capsys):
        """Test report with high token improvement."""
        benchmark_results = {
            "task_count": 1,
            "graph_api": {
                "statistics": {
                    "success_rate": 0.95,
                    "avg_tokens_used": 500,
                },
                "execution_time_seconds": 0.5,
            },
            "baseline": {
                "statistics": {
                    "success_rate": 0.90,
                    "avg_tokens_used": 2000,
                },
                "execution_time_seconds": 1.0,
            },
            "comparison": {
                "success_rate_improvement_pct": 5.0,
                "token_efficiency_improvement_pct": 75.0,
                "execution_time_improvement_pct": 50.0,
                "winner": "graph_api",
            },
        }

        evaluator.print_report(benchmark_results)

        captured = capsys.readouterr()
        assert ">15% token efficiency" in captured.out

    def test_print_report_low_token_improvement(self, evaluator, capsys):
        """Test report with low token improvement."""
        benchmark_results = {
            "task_count": 1,
            "graph_api": {
                "statistics": {
                    "success_rate": 0.95,
                    "avg_tokens_used": 1900,
                },
                "execution_time_seconds": 0.5,
            },
            "baseline": {
                "statistics": {
                    "success_rate": 0.90,
                    "avg_tokens_used": 2000,
                },
                "execution_time_seconds": 1.0,
            },
            "comparison": {
                "success_rate_improvement_pct": 5.0,
                "token_efficiency_improvement_pct": 5.0,
                "execution_time_improvement_pct": 50.0,
                "winner": "baseline",
            },
        }

        evaluator.print_report(benchmark_results)

        captured = capsys.readouterr()
        assert "Token efficiency improvement <15%" in captured.out

    def test_print_report_multiple_tasks(self, evaluator, capsys):
        """Test report with multiple tasks."""
        benchmark_results = {
            "task_count": 5,
            "graph_api": {
                "statistics": {
                    "success_rate": 0.95,
                    "avg_tokens_used": 800,
                },
                "execution_time_seconds": 2.5,
            },
            "baseline": {
                "statistics": {
                    "success_rate": 0.90,
                    "avg_tokens_used": 1500,
                },
                "execution_time_seconds": 5.0,
            },
            "comparison": {
                "success_rate_improvement_pct": 5.0,
                "token_efficiency_improvement_pct": 46.67,
                "execution_time_improvement_pct": 50.0,
                "winner": "graph_api",
            },
        }

        evaluator.print_report(benchmark_results)

        captured = capsys.readouterr()
        assert "Total Tasks: 5" in captured.out
