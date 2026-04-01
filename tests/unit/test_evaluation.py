"""Unit tests for evaluation modules."""

from pathlib import Path

import pytest

from src.evaluation.evaluation_runner import EvaluationRunner
from src.evaluation.metrics_collector import MetricsCollector


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a sample Python repository for testing."""
    repo = tmp_path / "sample_repo"
    repo.mkdir()

    # Create some Python files
    (repo / "main.py").write_text(
        """
def hello():
    return "world"

class MyClass:
    def method(self):
        return hello()
"""
    )

    (repo / "utils.py").write_text(
        """
def helper():
    pass

def another():
    return helper()
"""
    )

    return repo


class TestMetricsCollector:
    """Test MetricsCollector."""

    def test_initialization(self, sample_repo: Path) -> None:
        """Test collector initialization."""
        collector = MetricsCollector(sample_repo)
        assert collector.repo_path == sample_repo
        assert collector.metrics == {}

    def test_collect_parser_coverage(self, sample_repo: Path) -> None:
        """Test parser coverage collection."""
        collector = MetricsCollector(sample_repo)
        collector._collect_parser_coverage()

        assert "parser" in collector.metrics
        assert "functions" in collector.metrics["parser"]
        assert "classes" in collector.metrics["parser"]

    def test_collect_graph_stats(self, sample_repo: Path) -> None:
        """Test graph statistics collection."""
        collector = MetricsCollector(sample_repo)
        collector._collect_graph_stats()

        assert "graph" in collector.metrics
        assert "nodes" in collector.metrics["graph"]
        assert "edges" in collector.metrics["graph"]

    def test_check_parser_coverage(self, sample_repo: Path) -> None:
        """Test parser coverage check."""
        collector = MetricsCollector(sample_repo)
        collector._collect_parser_coverage()

        result = collector._check_parser_coverage()
        assert "target" in result
        assert "actual" in result
        assert "passed" in result

    def test_check_query_latency(self, sample_repo: Path) -> None:
        """Test query latency check."""
        collector = MetricsCollector(sample_repo)
        collector._collect_query_latency()

        result = collector._check_query_latency()
        assert "target" in result
        assert "actual" in result
        assert "passed" in result

    def test_check_api_payload(self, sample_repo: Path) -> None:
        """Test API payload check."""
        collector = MetricsCollector(sample_repo)
        collector._collect_api_payload()

        result = collector._check_api_payload()
        assert "target" in result
        assert "actual" in result
        assert "passed" in result


class TestEvaluationRunner:
    """Test EvaluationRunner."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test runner initialization."""
        runner = EvaluationRunner(tmp_path)
        assert runner.test_repos_dir == tmp_path
        assert runner.results == {}

    def test_evaluate_single_repo(self, sample_repo: Path, tmp_path: Path) -> None:
        """Test evaluating single repository."""
        runner = EvaluationRunner(sample_repo.parent)
        result = runner._evaluate_repo(sample_repo)

        assert "status" in result
        assert result["status"] in ("success", "failed")

    def test_generate_summary(self, tmp_path: Path) -> None:
        """Test summary generation."""
        runner = EvaluationRunner(tmp_path)
        runner.results = {
            "repo1": {"status": "success"},
            "repo2": {"status": "success"},
            "repo3": {"status": "failed"},
        }

        summary = runner._generate_summary()
        assert summary["total_repos"] == 3
        assert summary["passed_repos"] == 2
        assert summary["failed_repos"] == 1

    def test_make_decision_go(self, tmp_path: Path) -> None:
        """Test Go decision."""
        runner = EvaluationRunner(tmp_path)
        summary = {
            "total_repos": 3,
            "passed_repos": 3,
            "failed_repos": 0,
            "repo_pass_rate": 1.0,
        }

        decision = runner._make_decision(summary)
        assert decision["decision"] == "GO"

    def test_make_decision_no_go(self, tmp_path: Path) -> None:
        """Test No-Go decision."""
        runner = EvaluationRunner(tmp_path)
        summary = {
            "total_repos": 3,
            "passed_repos": 1,
            "failed_repos": 2,
            "repo_pass_rate": 0.33,
        }

        decision = runner._make_decision(summary)
        assert decision["decision"] == "NO-GO"

    def test_save_results(self, sample_repo: Path, tmp_path: Path) -> None:
        """Test saving results to file."""
        runner = EvaluationRunner(sample_repo.parent)
        runner.results = {
            "repo": {"status": "success", "metrics": {}},
        }

        output_file = tmp_path / "results.json"
        runner.save_results(output_file)

        assert output_file.exists()
