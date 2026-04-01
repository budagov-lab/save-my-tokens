"""Evaluation runner for Phase 1 success metrics."""

import json
from pathlib import Path
from typing import Dict, List

from loguru import logger

from src.evaluation.metrics_collector import MetricsCollector


class EvaluationRunner:
    """Run Phase 1 evaluation across test repositories."""

    # Success criteria (from DEVELOPMENT_TASKS.md)
    SUCCESS_CRITERIA = {
        "parser_coverage": {"target": 98, "unit": "%", "description": "Functions/classes extraction"},
        "query_latency_p99": {"target": 500, "unit": "ms", "description": "Neo4j query latency"},
        "graph_size": {
            "target": 1000,
            "unit": "nodes",
            "description": "Graph nodes on 50K LOC",
        },
        "semantic_search_precision": {"target": 80, "unit": "%", "description": "Top-5 precision"},
        "conflict_detection_recall": {"target": 90, "unit": "%", "description": "Recall on scenarios"},
        "api_response_payload": {"target": 50, "unit": "KB", "description": "Median response size"},
        "test_coverage": {"target": 80, "unit": "%", "description": "Code coverage"},
    }

    def __init__(self, test_repos_dir: Path):
        """Initialize evaluation runner.

        Args:
            test_repos_dir: Directory containing test repositories
        """
        self.test_repos_dir = test_repos_dir
        self.results: Dict = {}

    def run_evaluation(self, repo_names: List[str]) -> Dict:
        """Run evaluation on specified test repositories.

        Args:
            repo_names: List of repository names to evaluate on

        Returns:
            Evaluation results for all repositories
        """
        logger.info(f"Starting Phase 1 evaluation on {len(repo_names)} repositories")

        for repo_name in repo_names:
            repo_path = self.test_repos_dir / repo_name
            if not repo_path.exists():
                logger.warning(f"Repository not found: {repo_path}")
                continue

            logger.info(f"Evaluating {repo_name}...")
            self.results[repo_name] = self._evaluate_repo(repo_path)

        # Generate summary
        summary = self._generate_summary()

        logger.info("Phase 1 evaluation complete")
        return {
            "results": self.results,
            "summary": summary,
            "go_no_go": self._make_decision(summary),
        }

    def _evaluate_repo(self, repo_path: Path) -> Dict:
        """Evaluate a single repository.

        Args:
            repo_path: Path to repository

        Returns:
            Metrics for this repository
        """
        try:
            collector = MetricsCollector(repo_path)
            metrics = collector.collect_all()
            summary = collector.get_summary()

            return {
                "status": "success",
                "metrics": metrics,
                "summary": summary,
            }
        except Exception as e:
            logger.error(f"Failed to evaluate {repo_path}: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }

    def _generate_summary(self) -> Dict:
        """Generate overall summary from all repositories.

        Returns:
            Summary statistics
        """
        passed_repos = [r for r, result in self.results.items() if result.get("status") == "success"]
        failed_repos = [r for r, result in self.results.items() if result.get("status") == "failed"]

        return {
            "total_repos": len(self.results),
            "passed_repos": len(passed_repos),
            "failed_repos": len(failed_repos),
            "repo_pass_rate": len(passed_repos) / len(self.results) if self.results else 0,
        }

    def _make_decision(self, summary: Dict) -> Dict:
        """Make Go/No-Go decision based on evaluation results.

        Args:
            summary: Evaluation summary

        Returns:
            Go/No-Go decision with reasoning
        """
        decision = "GO" if summary["repo_pass_rate"] >= 0.8 else "NO-GO"

        reasoning = []
        if summary["passed_repos"] >= 2:
            reasoning.append("✓ Passed on at least 2 test repositories")
        else:
            reasoning.append("✗ Did not pass on 2+ test repositories")

        if summary["repo_pass_rate"] >= 0.8:
            reasoning.append("✓ Pass rate ≥80%")
        else:
            reasoning.append("✗ Pass rate <80%")

        return {
            "decision": decision,
            "reasoning": reasoning,
            "next_phase": "Phase 2 Planning" if decision == "GO" else "Phase 1.5 Extension",
        }

    def save_results(self, output_file: Path) -> None:
        """Save evaluation results to JSON file.

        Args:
            output_file: Path to output JSON file
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "results": self.results,
                        "summary": self._generate_summary(),
                        "decision": self._make_decision(self._generate_summary()),
                    },
                    f,
                    indent=2,
                    default=str,
                )
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def print_report(self) -> None:
        """Print evaluation report to console."""
        print("\n" + "=" * 80)
        print("PHASE 1 EVALUATION REPORT")
        print("=" * 80)

        for repo_name, result in self.results.items():
            print(f"\n{repo_name}:")
            if result["status"] == "success":
                print(f"  Status: ✓ Success")
                metrics = result.get("metrics", {})
                print(f"  Symbols: {metrics.get('parser', {}).get('total_symbols', 'N/A')}")
                print(f"  Latency p99: {metrics.get('latency', {}).get('p99_ms', 'N/A'):.2f}ms")
                print(f"  Graph size: {metrics.get('graph', {}).get('nodes', 'N/A')} nodes")
            else:
                print(f"  Status: ✗ Failed")
                print(f"  Error: {result.get('error', 'Unknown')}")

        summary = self._generate_summary()
        print("\n" + "-" * 80)
        print(f"Summary: {summary['passed_repos']}/{summary['total_repos']} repositories passed")

        decision = self._make_decision(summary)
        print(f"\nDecision: {decision['decision']}")
        for reason in decision["reasoning"]:
            print(f"  {reason}")

        print("\n" + "=" * 80)
