"""Evaluator for comparing Graph API agent vs baseline agent."""

import time
from typing import Dict, List

from loguru import logger

from src.agent.base_agent import BaseAgent
from src.agent.baseline_agent import BaselineAgent
from src.api.query_service import QueryService
from src.parsers.symbol_index import SymbolIndex


class AgentEvaluator:
    """Evaluate and compare agent implementations."""

    def __init__(
        self,
        repo_path: str,
        symbol_index: SymbolIndex,
        query_service: QueryService,
        token_budget: int = 4000,
    ):
        """Initialize evaluator.

        Args:
            repo_path: Path to repository
            symbol_index: Symbol index
            query_service: Query service for Graph API agent
            token_budget: Token budget per task
        """
        self.repo_path = repo_path
        self.symbol_index = symbol_index
        self.query_service = query_service
        self.token_budget = token_budget

        # Initialize agents
        self.graph_api_agent = BaseAgent(query_service, symbol_index, token_budget)
        self.baseline_agent = BaselineAgent(repo_path, symbol_index, token_budget)

    def run_benchmark(self, tasks: List[Dict]) -> Dict:
        """Run benchmark on both agents.

        Args:
            tasks: List of tasks to execute

        Returns:
            Benchmark results
        """
        logger.info(f"Running benchmark with {len(tasks)} tasks")

        # Execute tasks with Graph API agent
        graph_api_results = self._run_agent_tasks(self.graph_api_agent, tasks)

        # Execute tasks with baseline agent
        baseline_results = self._run_agent_tasks(self.baseline_agent, tasks)

        # Compare results
        comparison = self._compare_results(graph_api_results, baseline_results)

        return {
            "task_count": len(tasks),
            "graph_api": graph_api_results,
            "baseline": baseline_results,
            "comparison": comparison,
        }

    def _run_agent_tasks(self, agent, tasks: List[Dict]) -> Dict:
        """Run tasks with an agent.

        Args:
            agent: Agent to run tasks with
            tasks: List of tasks

        Returns:
            Execution results
        """
        results = []
        start_time = time.time()

        for task in tasks:
            result = agent.execute_task(task)
            results.append(result)
            agent.task_results.append(result)

        elapsed_time = time.time() - start_time
        stats = agent.get_statistics()

        return {
            "results": results,
            "statistics": stats,
            "execution_time_seconds": elapsed_time,
            "agent_type": agent.__class__.__name__,
        }

    def _compare_results(self, graph_api_results: Dict, baseline_results: Dict) -> Dict:
        """Compare results between agents.

        Args:
            graph_api_results: Graph API agent results
            baseline_results: Baseline agent results

        Returns:
            Comparison metrics
        """
        graph_api_stats = graph_api_results["statistics"]
        baseline_stats = baseline_results["statistics"]

        # Calculate improvements
        success_rate_improvement = (
            graph_api_stats["success_rate"] - baseline_stats["success_rate"]
        ) * 100

        token_reduction = (
            1 - graph_api_stats["avg_tokens_used"] / max(baseline_stats["avg_tokens_used"], 1)
        ) * 100

        time_reduction = (
            1
            - graph_api_results["execution_time_seconds"]
            / max(baseline_results["execution_time_seconds"], 1)
        ) * 100

        return {
            "success_rate_improvement_pct": success_rate_improvement,
            "token_efficiency_improvement_pct": token_reduction,
            "execution_time_improvement_pct": time_reduction,
            "graph_api_avg_tokens": graph_api_stats["avg_tokens_used"],
            "baseline_avg_tokens": baseline_stats["avg_tokens_used"],
            "winner": self._determine_winner(graph_api_stats, baseline_stats),
        }

    def _determine_winner(self, graph_api_stats: Dict, baseline_stats: Dict) -> str:
        """Determine which agent performed better.

        Args:
            graph_api_stats: Graph API agent statistics
            baseline_stats: Baseline agent statistics

        Returns:
            "graph_api" if Graph API better, "baseline" if baseline better, "tie" if equal
        """
        graph_api_score = (
            graph_api_stats["success_rate"] * 0.6
            + (1 - graph_api_stats["avg_tokens_used"] / 10000) * 0.4
        )

        baseline_score = (
            baseline_stats["success_rate"] * 0.6 + (1 - baseline_stats["avg_tokens_used"] / 10000) * 0.4
        )

        if abs(graph_api_score - baseline_score) < 0.01:
            return "tie"
        return "graph_api" if graph_api_score > baseline_score else "baseline"

    def print_report(self, benchmark_results: Dict) -> None:
        """Print benchmark report.

        Args:
            benchmark_results: Benchmark results from run_benchmark
        """
        print("\n" + "=" * 80)
        print("AGENT EVALUATION BENCHMARK REPORT")
        print("=" * 80)

        print(f"\nTotal Tasks: {benchmark_results['task_count']}")

        # Graph API results
        print("\n" + "-" * 80)
        print("GRAPH API AGENT")
        print("-" * 80)
        graph_api = benchmark_results["graph_api"]
        ga_stats = graph_api["statistics"]
        print(f"Success Rate: {ga_stats['success_rate']:.1%}")
        print(f"Avg Tokens: {ga_stats['avg_tokens_used']:.0f}")
        print(f"Execution Time: {graph_api['execution_time_seconds']:.2f}s")

        # Baseline results
        print("\n" + "-" * 80)
        print("BASELINE AGENT (File Access)")
        print("-" * 80)
        baseline = benchmark_results["baseline"]
        b_stats = baseline["statistics"]
        print(f"Success Rate: {b_stats['success_rate']:.1%}")
        print(f"Avg Tokens: {b_stats['avg_tokens_used']:.0f}")
        print(f"Execution Time: {baseline['execution_time_seconds']:.2f}s")

        # Comparison
        print("\n" + "-" * 80)
        print("COMPARISON")
        print("-" * 80)
        comp = benchmark_results["comparison"]
        print(f"Success Rate Improvement: {comp['success_rate_improvement_pct']:+.1f}%")
        print(f"Token Efficiency Improvement: {comp['token_efficiency_improvement_pct']:+.1f}%")
        print(f"Execution Time Improvement: {comp['execution_time_improvement_pct']:+.1f}%")
        print(f"\nWinner: {comp['winner'].upper()}")

        if comp["token_efficiency_improvement_pct"] > 15:
            print("✓ Graph API achieves >15% token efficiency improvement")
        else:
            print("✗ Token efficiency improvement <15%")

        print("\n" + "=" * 80)
