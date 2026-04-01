"""Base agent for code modification tasks using Graph API."""

import json
from typing import Dict, List, Optional

from loguru import logger

from src.api.query_service import QueryService
from src.parsers.symbol_index import SymbolIndex


class BaseAgent:
    """Simple baseline agent that uses the Graph API for code modifications."""

    def __init__(self, query_service: QueryService, symbol_index: SymbolIndex, token_budget: int = 4000):
        """Initialize agent.

        Args:
            query_service: Query service for graph operations
            symbol_index: Symbol index for lookups
            token_budget: Maximum tokens available for context
        """
        self.query_service = query_service
        self.symbol_index = symbol_index
        self.token_budget = token_budget
        self.tokens_used = 0
        self.task_results: List[Dict] = []

    def execute_task(self, task: Dict) -> Dict:
        """Execute a code modification task.

        Args:
            task: Task dict with 'id', 'description', 'target_symbols'

        Returns:
            Result dict with 'id', 'status', 'success', 'tokens_used', 'details'
        """
        task_id = task.get("id", "unknown")
        description = task.get("description", "")
        target_symbols = task.get("target_symbols", [])

        logger.info(f"[Agent] Starting task {task_id}: {description}")

        result = {
            "task_id": task_id,
            "description": description,
            "status": "in_progress",
            "success": False,
            "tokens_used": 0,
            "details": {},
        }

        try:
            # Step 1: Get context for each target symbol
            context_data = self._gather_context(target_symbols)
            result["tokens_used"] += context_data["tokens_used"]

            if result["tokens_used"] > self.token_budget:
                logger.warning(f"[Agent] Task {task_id} exceeds token budget")
                result["status"] = "token_limit_exceeded"
                return result

            # Step 2: Analyze dependencies
            dependencies = self._analyze_dependencies(target_symbols)

            # Step 3: Plan modifications
            modification_plan = self._plan_modifications(target_symbols, dependencies)

            # Step 4: Simulate execution
            success = self._execute_plan(modification_plan)

            result["success"] = success
            result["status"] = "completed"
            result["details"] = {
                "context_symbols": len(context_data["symbols"]),
                "dependencies": len(dependencies),
                "modifications": len(modification_plan),
            }

            logger.info(f"[Agent] Task {task_id} completed: success={success}")
            return result

        except Exception as e:
            logger.error(f"[Agent] Task {task_id} failed: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result

    def _gather_context(self, target_symbols: List[str]) -> Dict:
        """Gather context for target symbols.

        Args:
            target_symbols: List of symbols to get context for

        Returns:
            Context data with tokens used
        """
        symbols = []
        tokens_used = 0

        for symbol_name in target_symbols:
            try:
                context = self.query_service.get_context(symbol_name, depth=1, include_callers=True)

                if "symbol" in context:
                    symbols.append(context["symbol"])
                    tokens_used += context.get("token_estimate", 0)
            except Exception as e:
                logger.warning(f"Failed to get context for {symbol_name}: {e}")

        return {
            "symbols": symbols,
            "tokens_used": tokens_used,
        }

    def _analyze_dependencies(self, target_symbols: List[str]) -> List[Dict]:
        """Analyze dependencies between target symbols.

        Args:
            target_symbols: List of symbols

        Returns:
            List of dependency relationships
        """
        dependencies = []

        for symbol in target_symbols:
            candidates = self.symbol_index.get_by_name(symbol)
            if candidates:
                sym = candidates[0]
                # Get symbols in same file (potential dependencies)
                file_symbols = self.symbol_index.get_by_file(sym.file)
                for file_sym in file_symbols:
                    if file_sym.name != symbol:
                        dependencies.append(
                            {
                                "source": symbol,
                                "target": file_sym.name,
                                "type": "same_file",
                            }
                        )

        return dependencies

    def _plan_modifications(self, target_symbols: List[str], dependencies: List[Dict]) -> List[Dict]:
        """Plan modifications for target symbols.

        Args:
            target_symbols: Symbols to modify
            dependencies: Dependency relationships

        Returns:
            List of planned modifications
        """
        plan = []

        for symbol in target_symbols:
            plan.append(
                {
                    "symbol": symbol,
                    "action": "update",
                    "priority": 1,
                    "depends_on": [d["target"] for d in dependencies if d["source"] == symbol],
                }
            )

        return plan

    def _execute_plan(self, plan: List[Dict]) -> bool:
        """Simulate execution of modification plan.

        Args:
            plan: Modification plan

        Returns:
            True if successful, False otherwise
        """
        # Simple success criterion: all modifications have targets
        return all("symbol" in mod for mod in plan)

    def get_statistics(self) -> Dict:
        """Get agent execution statistics.

        Returns:
            Statistics dictionary
        """
        successful_tasks = sum(1 for r in self.task_results if r.get("success"))
        total_tasks = len(self.task_results)
        avg_tokens = sum(r.get("tokens_used", 0) for r in self.task_results) / max(total_tasks, 1)

        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": successful_tasks / max(total_tasks, 1),
            "avg_tokens_used": avg_tokens,
            "total_tokens_used": sum(r.get("tokens_used", 0) for r in self.task_results),
        }
