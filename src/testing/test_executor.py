"""Test executor for Phase 1 comprehensive testing."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.agent.base_agent import BaseAgent
from src.agent.baseline_agent import BaselineAgent
from src.api.query_service import QueryService
from src.graph.graph_builder import GraphBuilder
from src.parsers.symbol_index import SymbolIndex


class TestExecutor:
    """Execute comprehensive testing on multiple repositories."""

    def __init__(self, test_repos_dir: Path):
        """Initialize test executor.

        Args:
            test_repos_dir: Directory containing test repositories
        """
        self.test_repos_dir = test_repos_dir
        self.results = {}

    def load_test_tasks(self) -> List[Dict]:
        """Load test tasks from TESTING_PLAN.md format.

        Returns:
            List of task dictionaries
        """
        tasks = [
            # Task Set A: Simple Modifications
            {
                "id": "A1",
                "set": "A",
                "description": "Modify the main entry point to add new parameter",
                "target_symbols": ["main", "parse_arguments"],
                "difficulty": "easy",
            },
            {
                "id": "A2",
                "set": "A",
                "description": "Add new field to primary data model",
                "target_symbols": ["DataModel", "serialize"],
                "difficulty": "easy",
            },
            {
                "id": "A3",
                "set": "A",
                "description": "Add logging to critical path",
                "target_symbols": ["process", "execute"],
                "difficulty": "easy",
            },
            # Task Set B: Dependency-Heavy
            {
                "id": "B1",
                "set": "B",
                "description": "Modify endpoint to use new service",
                "target_symbols": ["get_user_endpoint", "UserService"],
                "difficulty": "medium",
            },
            {
                "id": "B2",
                "set": "B",
                "description": "Refactor utility function that's used widely",
                "target_symbols": ["validate_input"],
                "difficulty": "medium",
            },
            {
                "id": "B3",
                "set": "B",
                "description": "Optimize sorting algorithm in data processor",
                "target_symbols": ["sort_data", "DataProcessor"],
                "difficulty": "medium",
            },
            # Task Set C: Parallel/Conflict Testing
            {
                "id": "C1",
                "set": "C",
                "description": "Modify UserService",
                "target_symbols": ["UserService"],
                "parallel_with": "C2",
                "difficulty": "medium",
            },
            {
                "id": "C2",
                "set": "C",
                "description": "Modify PaymentService",
                "target_symbols": ["PaymentService"],
                "parallel_with": "C1",
                "difficulty": "medium",
            },
            {
                "id": "C3",
                "set": "C",
                "description": "Modify shared configuration",
                "target_symbols": ["config"],
                "expected_conflict": True,
                "difficulty": "hard",
            },
            # Task Set D: Search & Discovery
            {
                "id": "D1",
                "set": "D",
                "search_query": "error handling exception",
                "description": "Find error handling patterns",
                "difficulty": "medium",
            },
            {
                "id": "D2",
                "set": "D",
                "search_query": "authentication login",
                "description": "Find authentication-related code",
                "difficulty": "medium",
            },
            {
                "id": "D3",
                "set": "D",
                "search_query": "database connection",
                "description": "Find all code that touches database",
                "difficulty": "hard",
            },
        ]
        return tasks

    def run_test(self, repo_path: Path, repo_name: str) -> Dict:
        """Run complete test on a single repository.

        Args:
            repo_path: Path to repository
            repo_name: Name of repository

        Returns:
            Test results
        """
        logger.info(f"Starting test on {repo_name}")

        result = {
            "repo_name": repo_name,
            "repo_path": str(repo_path),
            "status": "in_progress",
            "graph_api": {},
            "baseline": {},
            "comparison": {},
        }

        try:
            # Build graph
            logger.info(f"Building graph for {repo_name}...")
            builder = GraphBuilder(str(repo_path))
            start_parse = time.time()
            builder._parse_all_files()
            parse_time = time.time() - start_parse

            symbol_index = builder.symbol_index
            result["parse_time"] = parse_time
            result["symbol_count"] = len(symbol_index.get_all())

            # Test Graph API Agent
            logger.info("Testing Graph API Agent...")
            mock_neo4j = None  # In real scenario, would use actual Neo4j
            query_service = QueryService(symbol_index, mock_neo4j, None)
            graph_api_agent = BaseAgent(query_service, symbol_index)

            graph_api_result = self._test_agent(graph_api_agent, "Graph API")
            result["graph_api"] = graph_api_result

            # Test Baseline Agent
            logger.info("Testing Baseline Agent...")
            baseline_agent = BaselineAgent(str(repo_path), symbol_index)
            baseline_result = self._test_agent(baseline_agent, "Baseline")
            result["baseline"] = baseline_result

            # Compare
            result["comparison"] = self._compare_results(graph_api_result, baseline_result)
            result["status"] = "completed"

            logger.info(f"Test on {repo_name} completed")
            return result

        except Exception as e:
            logger.error(f"Test on {repo_name} failed: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result

    def _test_agent(self, agent, agent_type: str) -> Dict:
        """Test an agent on all tasks.

        Args:
            agent: Agent to test
            agent_type: Type of agent (for logging)

        Returns:
            Agent test results
        """
        tasks = self.load_test_tasks()
        results = []
        tokens_list = []
        start_time = time.time()

        for task in tasks:
            try:
                task_result = agent.execute_task(task)
                results.append(task_result)
                tokens_list.append(task_result.get("tokens_used", 0))
            except Exception as e:
                logger.warning(f"Task {task['id']} failed: {e}")
                results.append({"task_id": task["id"], "status": "failed", "error": str(e)})

        elapsed_time = time.time() - start_time

        successful = sum(1 for r in results if r.get("success", False))
        total = len(results)

        return {
            "agent_type": agent_type,
            "total_tasks": total,
            "successful_tasks": successful,
            "success_rate": successful / max(total, 1),
            "avg_tokens_used": sum(tokens_list) / max(len(tokens_list), 1),
            "total_tokens_used": sum(tokens_list),
            "execution_time": elapsed_time,
            "tasks": results,
        }

    def _compare_results(self, graph_api_result: Dict, baseline_result: Dict) -> Dict:
        """Compare results between agents.

        Args:
            graph_api_result: Graph API agent results
            baseline_result: Baseline agent results

        Returns:
            Comparison dictionary
        """
        graph_api_tokens = graph_api_result["avg_tokens_used"]
        baseline_tokens = baseline_result["avg_tokens_used"]

        token_efficiency = (1 - graph_api_tokens / max(baseline_tokens, 1)) * 100

        return {
            "graph_api_avg_tokens": graph_api_tokens,
            "baseline_avg_tokens": baseline_tokens,
            "token_efficiency_improvement_pct": token_efficiency,
            "success_rate_graph_api": graph_api_result["success_rate"],
            "success_rate_baseline": baseline_result["success_rate"],
            "execution_time_graph_api": graph_api_result["execution_time"],
            "execution_time_baseline": baseline_result["execution_time"],
            "graph_api_faster": graph_api_result["execution_time"] < baseline_result["execution_time"],
        }

    def run_all_tests(self, repo_names: List[str]) -> Dict:
        """Run tests on all specified repositories.

        Args:
            repo_names: List of repository names

        Returns:
            Aggregated results
        """
        logger.info(f"Starting comprehensive test suite on {len(repo_names)} repositories")

        all_results = {
            "repositories": {},
            "summary": {},
            "decision": {},
        }

        for repo_name in repo_names:
            repo_path = self.test_repos_dir / repo_name
            if not repo_path.exists():
                logger.warning(f"Repository not found: {repo_path}")
                continue

            result = self.run_test(repo_path, repo_name)
            all_results["repositories"][repo_name] = result

        # Generate summary
        all_results["summary"] = self._generate_summary(all_results["repositories"])

        # Make decision
        all_results["decision"] = self._make_go_no_go_decision(all_results["summary"])

        return all_results

    def _generate_summary(self, repo_results: Dict) -> Dict:
        """Generate summary statistics.

        Args:
            repo_results: Results from all repositories

        Returns:
            Summary dictionary
        """
        repos_count = len(repo_results)
        successful_repos = sum(1 for r in repo_results.values() if r.get("status") == "completed")

        # Aggregate metrics
        graph_api_tokens = []
        baseline_tokens = []
        success_rates = []

        for repo_result in repo_results.values():
            if repo_result.get("status") == "completed":
                graph_api_tokens.append(repo_result["graph_api"]["avg_tokens_used"])
                baseline_tokens.append(repo_result["baseline"]["avg_tokens_used"])
                success_rates.append(repo_result["comparison"]["success_rate_graph_api"])

        return {
            "total_repositories": repos_count,
            "successful_repositories": successful_repos,
            "repo_success_rate": successful_repos / max(repos_count, 1),
            "avg_graph_api_tokens": sum(graph_api_tokens) / max(len(graph_api_tokens), 1),
            "avg_baseline_tokens": sum(baseline_tokens) / max(len(baseline_tokens), 1),
            "avg_token_efficiency_improvement": (
                (1 - (sum(graph_api_tokens) / max(sum(baseline_tokens), 1)))
                if baseline_tokens
                else 0
            ) * 100,
            "avg_task_success_rate": sum(success_rates) / max(len(success_rates), 1),
        }

    def _make_go_no_go_decision(self, summary: Dict) -> Dict:
        """Make Go/No-Go decision based on summary.

        Args:
            summary: Summary statistics

        Returns:
            Decision dictionary
        """
        criteria = {
            "repo_success_rate": (summary["repo_success_rate"] >= 0.8, "≥80% repos successful"),
            "token_efficiency": (
                summary["avg_token_efficiency_improvement"] >= 15,
                "≥15% token efficiency improvement",
            ),
            "task_success_rate": (summary["avg_task_success_rate"] >= 0.85, "≥85% task success rate"),
        }

        passed = sum(1 for passed, _ in criteria.values() if passed)
        total = len(criteria)

        decision = "GO" if passed >= 2 else "NO-GO"

        return {
            "decision": decision,
            "criteria": {name: passed for name, (passed, _) in criteria.items()},
            "criteria_descriptions": {name: desc for _, (_, desc) in criteria.items()},
            "passed": passed,
            "total": total,
        }

    def print_report(self, results: Dict) -> None:
        """Print test report.

        Args:
            results: Test results
        """
        print("\n" + "=" * 80)
        print("PHASE 1 MVP - COMPREHENSIVE TEST REPORT")
        print("=" * 80)

        # Repository results
        for repo_name, repo_result in results["repositories"].items():
            print(f"\n{repo_name.upper()}")
            print("-" * 80)

            if repo_result["status"] == "completed":
                print(f"Parse Time: {repo_result['parse_time']:.2f}s")
                print(f"Symbols: {repo_result['symbol_count']}")

                ga = repo_result["graph_api"]
                bl = repo_result["baseline"]
                print(f"\nGraph API: {ga['successful_tasks']}/{ga['total_tasks']} tasks, "
                      f"{ga['avg_tokens_used']:.0f} avg tokens")
                print(f"Baseline: {bl['successful_tasks']}/{bl['total_tasks']} tasks, "
                      f"{bl['avg_tokens_used']:.0f} avg tokens")

                comp = repo_result["comparison"]
                print(f"\nToken Efficiency Improvement: {comp['token_efficiency_improvement_pct']:+.1f}%")
            else:
                print(f"Status: {repo_result['status']}")
                if "error" in repo_result:
                    print(f"Error: {repo_result['error']}")

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        summary = results["summary"]
        print(f"Repositories Tested: {summary['successful_repositories']}/{summary['total_repositories']}")
        print(f"Avg Token Efficiency: {summary['avg_token_efficiency_improvement']:.1f}%")
        print(f"Avg Task Success Rate: {summary['avg_task_success_rate']:.1%}")

        # Decision
        print("\n" + "=" * 80)
        print("GO/NO-GO DECISION")
        print("=" * 80)
        decision = results["decision"]
        print(f"Decision: {decision['decision']}")
        print(f"Criteria Passed: {decision['passed']}/{decision['total']}")
        for criterion, passed in decision["criteria"].items():
            status = "✅" if passed else "❌"
            print(f"  {status} {criterion}")

        print("\n" + "=" * 80)
