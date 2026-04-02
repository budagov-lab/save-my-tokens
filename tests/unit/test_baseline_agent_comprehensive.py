"""Comprehensive tests for baseline agent."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.baseline_agent import BaselineAgent
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func_a", type="function", file="module.py", line=1, column=0))
    index.add(Symbol(name="func_b", type="function", file="module.py", line=10, column=0))
    return index


@pytest.fixture
def temp_repo():
    """Create temporary repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        # Create a test module file
        module = repo / "module.py"
        module.write_text("def func_a(): pass\ndef func_b(): pass\n")
        yield repo


@pytest.fixture
def agent(temp_repo, symbol_index):
    """Create baseline agent."""
    return BaselineAgent(str(temp_repo), symbol_index, token_budget=10000)


class TestBaselineAgentInit:
    """Test agent initialization."""

    def test_init(self, temp_repo, symbol_index):
        """Test initialization."""
        agent = BaselineAgent(str(temp_repo), symbol_index, token_budget=5000)

        assert agent.repo_path == temp_repo
        assert agent.symbol_index is symbol_index
        assert agent.token_budget == 5000
        assert agent.tokens_used == 0
        assert agent.task_results == []


class TestExecuteTask:
    """Test task execution."""

    def test_execute_task_success(self, agent):
        """Test successful task execution."""
        task = {
            "id": "t1",
            "description": "Test task",
            "target_symbols": ["func_a"],
        }

        result = agent.execute_task(task)

        assert result["task_id"] == "t1"
        assert result["status"] in ["completed", "token_limit_exceeded"]
        assert "tokens_used" in result

    def test_execute_task_empty_symbols(self, agent):
        """Test task with empty target symbols."""
        task = {
            "id": "t1",
            "description": "Empty task",
            "target_symbols": [],
        }

        result = agent.execute_task(task)

        assert result["task_id"] == "t1"

    def test_execute_task_nonexistent_symbol(self, agent):
        """Test task with nonexistent symbol."""
        task = {
            "id": "t1",
            "description": "Task",
            "target_symbols": ["nonexistent"],
        }

        result = agent.execute_task(task)

        assert result["task_id"] == "t1"

    def test_execute_task_token_budget_exceeded(self, agent):
        """Test task exceeding token budget."""
        # Create agent with very low budget
        agent.token_budget = 1
        task = {
            "id": "t1",
            "description": "Task",
            "target_symbols": ["func_a"],
        }

        result = agent.execute_task(task)

        assert result["task_id"] == "t1"

    def test_execute_task_with_exception(self, agent):
        """Test task execution with exception."""
        task = {
            "id": "t1",
            "description": "Task",
            "target_symbols": ["func_a"],
        }

        with patch.object(agent, '_retrieve_files', side_effect=Exception("File error")):
            result = agent.execute_task(task)

            assert result["status"] == "failed"
            assert "error" in result


class TestRetrieveFiles:
    """Test file retrieval."""

    def test_retrieve_files(self, agent):
        """Test file retrieval."""
        result = agent._retrieve_files(["func_a"])

        assert "files" in result
        assert "total_bytes" in result
        assert "tokens_used" in result
        assert result["tokens_used"] > 0

    def test_retrieve_files_empty_symbols(self, agent):
        """Test file retrieval with empty symbols."""
        result = agent._retrieve_files([])

        assert result["files"] == {}
        assert result["total_bytes"] == 0
        assert result["tokens_used"] == 0

    def test_retrieve_files_nonexistent(self, agent):
        """Test file retrieval for nonexistent symbols."""
        result = agent._retrieve_files(["nonexistent"])

        assert result["files"] == {}

    def test_retrieve_files_reads_content(self, agent, temp_repo):
        """Test files are actually read."""
        result = agent._retrieve_files(["func_a"])

        assert "module.py" in result["files"]
        assert "func_a" in result["files"]["module.py"]


class TestFindDependencies:
    """Test dependency finding."""

    def test_find_dependencies(self, agent):
        """Test dependency finding."""
        files = {"module.py": "func_a()\nfunc_b()"}

        dependencies = agent._find_dependencies_in_files(files)

        assert isinstance(dependencies, list)

    def test_find_dependencies_empty_files(self, agent):
        """Test dependency finding with empty files."""
        files = {}

        dependencies = agent._find_dependencies_in_files(files)

        assert dependencies == []

    def test_find_dependencies_no_matches(self, agent):
        """Test dependency finding with no matches."""
        files = {"other.py": "unrelated code"}

        dependencies = agent._find_dependencies_in_files(files)

        assert dependencies == []

    def test_find_dependencies_matches(self, agent):
        """Test dependency finding with matches."""
        files = {"module.py": "def foo():\n    func_a()\n    func_b()"}

        dependencies = agent._find_dependencies_in_files(files)

        assert len(dependencies) > 0


class TestPlanModifications:
    """Test modification planning."""

    def test_plan_modifications_single_symbol(self, agent):
        """Test planning modifications for single symbol."""
        dependencies = []

        plan = agent._plan_modifications(["func_a"], dependencies)

        assert len(plan) == 1
        assert plan[0]["symbol"] == "func_a"
        assert plan[0]["action"] == "update"

    def test_plan_modifications_multiple_symbols(self, agent):
        """Test planning modifications for multiple symbols."""
        dependencies = []

        plan = agent._plan_modifications(["func_a", "func_b"], dependencies)

        assert len(plan) == 2

    def test_plan_modifications_empty(self, agent):
        """Test planning with empty symbols."""
        plan = agent._plan_modifications([], [])

        assert plan == []

    def test_plan_modifications_with_dependencies(self, agent):
        """Test planning considers dependencies."""
        dependencies = [
            {"file": "module.py", "symbol": "func_a", "type": "text_match"}
        ]

        plan = agent._plan_modifications(["func_b"], dependencies)

        assert len(plan) == 1


class TestExecutePlan:
    """Test plan execution."""

    def test_execute_plan_success(self, agent):
        """Test successful plan execution."""
        plan = [
            {"symbol": "func_a", "action": "update"},
            {"symbol": "func_b", "action": "update"},
        ]

        success = agent._execute_plan(plan)

        assert success is True

    def test_execute_plan_empty(self, agent):
        """Test execution of empty plan."""
        success = agent._execute_plan([])

        assert success is True

    def test_execute_plan_invalid(self, agent):
        """Test execution of invalid plan."""
        plan = [
            {"action": "update"},  # Missing symbol
        ]

        success = agent._execute_plan(plan)

        assert success is False


class TestGetStatistics:
    """Test statistics calculation."""

    def test_get_statistics_empty(self, agent):
        """Test statistics with no tasks."""
        stats = agent.get_statistics()

        assert stats["total_tasks"] == 0
        assert stats["successful_tasks"] == 0
        assert stats["success_rate"] == 0
        assert stats["avg_tokens_used"] == 0

    def test_get_statistics_with_results(self, agent):
        """Test statistics with task results."""
        agent.task_results = [
            {"success": True, "tokens_used": 100},
            {"success": False, "tokens_used": 200},
            {"success": True, "tokens_used": 150},
        ]

        stats = agent.get_statistics()

        assert stats["total_tasks"] == 3
        assert stats["successful_tasks"] == 2
        assert stats["success_rate"] == 2/3
        assert stats["avg_tokens_used"] == 150
        assert stats["total_tokens_used"] == 450

    def test_get_statistics_all_successful(self, agent):
        """Test statistics with all successful tasks."""
        agent.task_results = [
            {"success": True, "tokens_used": 100},
            {"success": True, "tokens_used": 200},
        ]

        stats = agent.get_statistics()

        assert stats["success_rate"] == 1.0
        assert stats["total_tasks"] == 2
        assert stats["successful_tasks"] == 2

    def test_get_statistics_all_failed(self, agent):
        """Test statistics with all failed tasks."""
        agent.task_results = [
            {"success": False, "tokens_used": 100},
            {"success": False, "tokens_used": 200},
        ]

        stats = agent.get_statistics()

        assert stats["success_rate"] == 0.0
        assert stats["total_tasks"] == 2
        assert stats["successful_tasks"] == 0
