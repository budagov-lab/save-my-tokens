"""Comprehensive tests for evaluation runner."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.evaluation_runner import EvaluationRunner
from src.evaluation.metrics_collector import MetricsCollector


@pytest.fixture
def temp_dir():
    """Create temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def eval_runner(temp_dir):
    """Create evaluation runner."""
    return EvaluationRunner(temp_dir)


class TestEvaluationRunnerInit:
    """Test EvaluationRunner initialization."""

    def test_init(self, temp_dir):
        """Test runner initialization."""
        runner = EvaluationRunner(temp_dir)

        assert runner.test_repos_dir == temp_dir
        assert runner.results == {}

    def test_success_criteria_defined(self, eval_runner):
        """Test success criteria are defined."""
        assert "parser_coverage" in eval_runner.SUCCESS_CRITERIA
        assert "query_latency_p99" in eval_runner.SUCCESS_CRITERIA
        assert "graph_size" in eval_runner.SUCCESS_CRITERIA
        assert "semantic_search_precision" in eval_runner.SUCCESS_CRITERIA
        assert "conflict_detection_recall" in eval_runner.SUCCESS_CRITERIA
        assert "api_response_payload" in eval_runner.SUCCESS_CRITERIA
        assert "test_coverage" in eval_runner.SUCCESS_CRITERIA


class TestRunEvaluation:
    """Test evaluation execution."""

    def test_run_evaluation_empty_list(self, eval_runner):
        """Test running evaluation with empty repo list."""
        result = eval_runner.run_evaluation([])

        assert "results" in result
        assert "summary" in result
        assert "go_no_go" in result
        assert result["results"] == {}

    def test_run_evaluation_repo_not_found(self, temp_dir):
        """Test evaluation with non-existent repository."""
        runner = EvaluationRunner(temp_dir)

        with patch('src.evaluation.evaluation_runner.logger') as mock_logger:
            result = runner.run_evaluation(["nonexistent_repo"])

            mock_logger.warning.assert_called()
            assert result["results"] == {}

    def test_run_evaluation_success(self, temp_dir):
        """Test successful evaluation."""
        runner = EvaluationRunner(temp_dir)
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        mock_metrics = {
            "parser": {"total_symbols": 100},
            "latency": {"p99_ms": 250},
            "graph": {"nodes": 500},
        }

        with patch.object(MetricsCollector, 'collect_all', return_value=mock_metrics):
            with patch.object(MetricsCollector, 'get_summary', return_value={"status": "ok"}):
                result = runner.run_evaluation(["test_repo"])

                assert "test_repo" in result["results"]
                assert result["results"]["test_repo"]["status"] == "success"

    def test_run_evaluation_multiple_repos(self, temp_dir):
        """Test evaluation with multiple repositories."""
        runner = EvaluationRunner(temp_dir)

        for i in range(3):
            (temp_dir / f"repo_{i}").mkdir()

        mock_metrics = {"parser": {"total_symbols": 100}}

        with patch.object(MetricsCollector, 'collect_all', return_value=mock_metrics):
            with patch.object(MetricsCollector, 'get_summary', return_value={}):
                result = runner.run_evaluation(["repo_0", "repo_1", "repo_2"])

                assert len(result["results"]) == 3

    def test_run_evaluation_summary_generation(self, temp_dir):
        """Test summary is generated."""
        runner = EvaluationRunner(temp_dir)
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        with patch.object(MetricsCollector, 'collect_all', return_value={}):
            with patch.object(MetricsCollector, 'get_summary', return_value={}):
                result = runner.run_evaluation(["test_repo"])

                assert "summary" in result
                assert "total_repos" in result["summary"]
                assert "passed_repos" in result["summary"]


class TestEvaluateRepo:
    """Test single repository evaluation."""

    def test_evaluate_repo_success(self, eval_runner, temp_dir):
        """Test successful repository evaluation."""
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        mock_metrics = {"parser": {"total_symbols": 50}}
        mock_summary = {"status": "complete"}

        with patch.object(MetricsCollector, '__init__', return_value=None):
            with patch.object(MetricsCollector, 'collect_all', return_value=mock_metrics):
                with patch.object(MetricsCollector, 'get_summary', return_value=mock_summary):
                    result = eval_runner._evaluate_repo(repo_path)

                    assert result["status"] == "success"
                    assert result["metrics"] == mock_metrics
                    assert result["summary"] == mock_summary

    def test_evaluate_repo_exception(self, eval_runner, temp_dir):
        """Test repository evaluation with exception."""
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        with patch.object(MetricsCollector, '__init__', side_effect=Exception("Collection failed")):
            result = eval_runner._evaluate_repo(repo_path)

            assert result["status"] == "failed"
            assert "error" in result


class TestGenerateSummary:
    """Test summary generation."""

    def test_generate_summary_empty(self, eval_runner):
        """Test summary with no results."""
        summary = eval_runner._generate_summary()

        assert summary["total_repos"] == 0
        assert summary["passed_repos"] == 0
        assert summary["failed_repos"] == 0
        assert summary["repo_pass_rate"] == 0

    def test_generate_summary_all_passed(self, eval_runner):
        """Test summary with all repos passed."""
        eval_runner.results = {
            "repo1": {"status": "success"},
            "repo2": {"status": "success"},
            "repo3": {"status": "success"},
        }

        summary = eval_runner._generate_summary()

        assert summary["total_repos"] == 3
        assert summary["passed_repos"] == 3
        assert summary["failed_repos"] == 0
        assert summary["repo_pass_rate"] == 1.0

    def test_generate_summary_partial_pass(self, eval_runner):
        """Test summary with partial pass."""
        eval_runner.results = {
            "repo1": {"status": "success"},
            "repo2": {"status": "success"},
            "repo3": {"status": "failed", "error": "Error"},
        }

        summary = eval_runner._generate_summary()

        assert summary["total_repos"] == 3
        assert summary["passed_repos"] == 2
        assert summary["failed_repos"] == 1
        assert summary["repo_pass_rate"] == 2 / 3

    def test_generate_summary_all_failed(self, eval_runner):
        """Test summary with all repos failed."""
        eval_runner.results = {
            "repo1": {"status": "failed", "error": "Error 1"},
            "repo2": {"status": "failed", "error": "Error 2"},
        }

        summary = eval_runner._generate_summary()

        assert summary["total_repos"] == 2
        assert summary["passed_repos"] == 0
        assert summary["failed_repos"] == 2
        assert summary["repo_pass_rate"] == 0


class TestMakeDecision:
    """Test Go/No-Go decision logic."""

    def test_decision_go_high_pass_rate(self, eval_runner):
        """Test GO decision with high pass rate."""
        summary = {
            "total_repos": 5,
            "passed_repos": 4,
            "failed_repos": 1,
            "repo_pass_rate": 0.8,
        }

        decision = eval_runner._make_decision(summary)

        assert decision["decision"] == "GO"
        assert "Phase 2 Planning" in decision["next_phase"]
        assert len(decision["reasoning"]) == 2

    def test_decision_go_perfect_rate(self, eval_runner):
        """Test GO decision with perfect pass rate."""
        summary = {
            "total_repos": 3,
            "passed_repos": 3,
            "failed_repos": 0,
            "repo_pass_rate": 1.0,
        }

        decision = eval_runner._make_decision(summary)

        assert decision["decision"] == "GO"

    def test_decision_nogo_low_pass_rate(self, eval_runner):
        """Test NO-GO decision with low pass rate."""
        summary = {
            "total_repos": 5,
            "passed_repos": 3,
            "failed_repos": 2,
            "repo_pass_rate": 0.6,
        }

        decision = eval_runner._make_decision(summary)

        assert decision["decision"] == "NO-GO"
        assert "Phase 1.5 Extension" in decision["next_phase"]

    def test_decision_nogo_insufficient_passed(self, eval_runner):
        """Test NO-GO decision with insufficient passed repos."""
        summary = {
            "total_repos": 5,
            "passed_repos": 1,
            "failed_repos": 4,
            "repo_pass_rate": 0.2,
        }

        decision = eval_runner._make_decision(summary)

        assert decision["decision"] == "NO-GO"

    def test_decision_boundary_case(self, eval_runner):
        """Test decision at exactly 80% pass rate."""
        summary = {
            "total_repos": 5,
            "passed_repos": 4,
            "failed_repos": 1,
            "repo_pass_rate": 0.8,
        }

        decision = eval_runner._make_decision(summary)

        assert decision["decision"] == "GO"


class TestSaveResults:
    """Test results persistence."""

    def test_save_results_success(self, eval_runner, temp_dir):
        """Test successful results saving."""
        output_file = temp_dir / "results.json"
        eval_runner.results = {
            "repo1": {"status": "success", "metrics": {"symbols": 100}},
        }

        eval_runner.save_results(output_file)

        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)
            assert "results" in data
            assert "summary" in data
            assert "decision" in data

    def test_save_results_error(self, eval_runner):
        """Test save results with error."""
        eval_runner.results = {"repo1": {"status": "success"}}

        with patch('builtins.open', side_effect=IOError("Write failed")):
            with patch('src.evaluation.evaluation_runner.logger') as mock_logger:
                eval_runner.save_results(Path("/invalid/path/results.json"))

                mock_logger.error.assert_called()


class TestPrintReport:
    """Test console report printing."""

    def test_print_report_success(self, eval_runner, capsys):
        """Test report printing with successful evaluation."""
        eval_runner.results = {
            "test_repo": {
                "status": "success",
                "metrics": {
                    "parser": {"total_symbols": 100},
                    "latency": {"p99_ms": 250},
                    "graph": {"nodes": 500},
                },
            },
        }

        eval_runner.print_report()

        captured = capsys.readouterr()
        assert "PHASE 1 EVALUATION REPORT" in captured.out
        assert "test_repo" in captured.out
        assert "Success" in captured.out

    def test_print_report_failure(self, eval_runner, capsys):
        """Test report printing with failed evaluation."""
        eval_runner.results = {
            "test_repo": {
                "status": "failed",
                "error": "Collection failed",
            },
        }

        eval_runner.print_report()

        captured = capsys.readouterr()
        assert "PHASE 1 EVALUATION REPORT" in captured.out
        assert "Failed" in captured.out
        assert "Collection failed" in captured.out

    def test_print_report_mixed(self, eval_runner, capsys):
        """Test report printing with mixed results."""
        eval_runner.results = {
            "repo1": {
                "status": "success",
                "metrics": {
                    "parser": {"total_symbols": 100},
                    "latency": {"p99_ms": 250},
                    "graph": {"nodes": 500},
                },
            },
            "repo2": {
                "status": "failed",
                "error": "Collection failed",
            },
        }

        eval_runner.print_report()

        captured = capsys.readouterr()
        assert "repo1" in captured.out
        assert "repo2" in captured.out
        assert "Summary:" in captured.out

    def test_print_report_decision(self, eval_runner, capsys):
        """Test report includes decision."""
        eval_runner.results = {
            "repo1": {
                "status": "success",
                "metrics": {"parser": {"total_symbols": 100}, "latency": {"p99_ms": 250}, "graph": {"nodes": 500}},
                "summary": {},
            },
            "repo2": {
                "status": "success",
                "metrics": {"parser": {"total_symbols": 100}, "latency": {"p99_ms": 250}, "graph": {"nodes": 500}},
                "summary": {},
            },
        }

        eval_runner.print_report()

        captured = capsys.readouterr()
        assert "Decision:" in captured.out
