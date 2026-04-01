"""Unit tests for agents."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agent.base_agent import BaseAgent
from src.agent.baseline_agent import BaselineAgent
from src.agent.evaluator import AgentEvaluator
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create symbol index with test data."""
    index = SymbolIndex()
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
    return index


@pytest.fixture
def mock_query_service() -> MagicMock:
    """Create mock query service."""
    mock = MagicMock()
    mock.get_context.return_value = {
        "symbol": {"name": "test", "type": "function"},
        "token_estimate": 100,
    }
    return mock


class TestBaseAgent:
    """Test BaseAgent."""

    def test_initialization(self, mock_query_service: MagicMock, symbol_index: SymbolIndex) -> None:
        """Test agent initialization."""
        agent = BaseAgent(mock_query_service, symbol_index, token_budget=4000)
        assert agent.token_budget == 4000
        assert agent.tokens_used == 0

    def test_execute_task(self, mock_query_service: MagicMock, symbol_index: SymbolIndex) -> None:
        """Test task execution."""
        agent = BaseAgent(mock_query_service, symbol_index, token_budget=4000)

        task = {
            "id": "task_1",
            "description": "Modify function",
            "target_symbols": ["process_data"],
        }

        result = agent.execute_task(task)
        assert result["task_id"] == "task_1"
        assert result["status"] == "completed"
        assert "tokens_used" in result

    def test_gather_context(self, mock_query_service: MagicMock, symbol_index: SymbolIndex) -> None:
        """Test context gathering."""
        agent = BaseAgent(mock_query_service, symbol_index)
        context = agent._gather_context(["process_data"])

        assert "symbols" in context
        assert "tokens_used" in context

    def test_statistics(self, mock_query_service: MagicMock, symbol_index: SymbolIndex) -> None:
        """Test statistics collection."""
        agent = BaseAgent(mock_query_service, symbol_index)
        agent.task_results = [
            {"success": True, "tokens_used": 100},
            {"success": True, "tokens_used": 150},
        ]

        stats = agent.get_statistics()
        assert stats["total_tasks"] == 2
        assert stats["successful_tasks"] == 2
        assert stats["success_rate"] == 1.0


class TestBaselineAgent:
    """Test BaselineAgent."""

    def test_initialization(self, tmp_path: Path, symbol_index: SymbolIndex) -> None:
        """Test baseline agent initialization."""
        agent = BaselineAgent(str(tmp_path), symbol_index, token_budget=4000)
        assert agent.token_budget == 4000

    def test_execute_task(self, tmp_path: Path, symbol_index: SymbolIndex) -> None:
        """Test task execution."""
        agent = BaselineAgent(str(tmp_path), symbol_index, token_budget=4000)

        task = {
            "id": "task_1",
            "description": "Modify function",
            "target_symbols": ["process_data"],
        }

        result = agent.execute_task(task)
        assert result["task_id"] == "task_1"
        assert "tokens_used" in result

    def test_retrieve_files(self, tmp_path: Path, symbol_index: SymbolIndex) -> None:
        """Test file retrieval."""
        agent = BaselineAgent(str(tmp_path), symbol_index)
        files_data = agent._retrieve_files(["process_data"])

        assert "files" in files_data
        assert "tokens_used" in files_data


class TestAgentEvaluator:
    """Test AgentEvaluator."""

    def test_initialization(
        self, tmp_path: Path, mock_query_service: MagicMock, symbol_index: SymbolIndex
    ) -> None:
        """Test evaluator initialization."""
        evaluator = AgentEvaluator(str(tmp_path), symbol_index, mock_query_service)
        assert evaluator.graph_api_agent is not None
        assert evaluator.baseline_agent is not None

    def test_run_benchmark(
        self, tmp_path: Path, mock_query_service: MagicMock, symbol_index: SymbolIndex
    ) -> None:
        """Test benchmark execution."""
        evaluator = AgentEvaluator(str(tmp_path), symbol_index, mock_query_service)

        tasks = [
            {
                "id": "task_1",
                "description": "Test task",
                "target_symbols": ["process_data"],
            }
        ]

        results = evaluator.run_benchmark(tasks)
        assert results["task_count"] == 1
        assert "graph_api" in results
        assert "baseline" in results
        assert "comparison" in results

    def test_comparison(self, tmp_path: Path, mock_query_service: MagicMock, symbol_index: SymbolIndex) -> None:
        """Test result comparison."""
        evaluator = AgentEvaluator(str(tmp_path), symbol_index, mock_query_service)

        graph_api_results = {
            "statistics": {
                "success_rate": 1.0,
                "avg_tokens_used": 500,
            }
        }

        baseline_results = {
            "statistics": {
                "success_rate": 1.0,
                "avg_tokens_used": 2000,
            }
        }

        comparison = evaluator._compare_results(graph_api_results, baseline_results)
        assert comparison["token_efficiency_improvement_pct"] > 0
