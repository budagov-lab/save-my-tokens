"""Baseline agent using raw file access (without Graph API)."""

import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.parsers.symbol_index import SymbolIndex


class BaselineAgent:
    """Baseline agent that retrieves entire files without Graph API."""

    def __init__(self, repo_path: str, symbol_index: SymbolIndex, token_budget: int = 4000):
        """Initialize baseline agent.

        Args:
            repo_path: Root path of repository
            symbol_index: Symbol index for lookups
            token_budget: Maximum tokens available
        """
        self.repo_path = Path(repo_path)
        self.symbol_index = symbol_index
        self.token_budget = token_budget
        self.tokens_used = 0
        self.task_results: List[Dict] = []

    def execute_task(self, task: Dict) -> Dict:
        """Execute task using raw file access.

        Args:
            task: Task dict with 'id', 'description', 'target_symbols'

        Returns:
            Result dict
        """
        task_id = task.get("id", "unknown")
        description = task.get("description", "")
        target_symbols = task.get("target_symbols", [])

        logger.info(f"[BaselineAgent] Starting task {task_id}: {description}")

        result = {
            "task_id": task_id,
            "description": description,
            "status": "in_progress",
            "success": False,
            "tokens_used": 0,
            "details": {},
        }

        try:
            # Step 1: Retrieve entire files containing target symbols
            files_data = self._retrieve_files(target_symbols)
            result["tokens_used"] += files_data["tokens_used"]

            if result["tokens_used"] > self.token_budget:
                logger.warning(f"[BaselineAgent] Task {task_id} exceeds token budget")
                result["status"] = "token_limit_exceeded"
                return result

            # Step 2: Search for dependencies in files
            dependencies = self._find_dependencies_in_files(files_data["files"])

            # Step 3: Plan modifications
            modification_plan = self._plan_modifications(target_symbols, dependencies)

            # Step 4: Simulate execution
            success = self._execute_plan(modification_plan)

            result["success"] = success
            result["status"] = "completed"
            result["details"] = {
                "files_retrieved": len(files_data["files"]),
                "bytes_retrieved": files_data["total_bytes"],
                "dependencies": len(dependencies),
                "modifications": len(modification_plan),
            }

            logger.info(f"[BaselineAgent] Task {task_id} completed: success={success}")
            return result

        except Exception as e:
            logger.error(f"[BaselineAgent] Task {task_id} failed: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result

    def _retrieve_files(self, target_symbols: List[str]) -> Dict:
        """Retrieve entire files for target symbols.

        Args:
            target_symbols: Symbols to find files for

        Returns:
            Dict with files and tokens used
        """
        files = {}
        total_bytes = 0

        # Find files for each symbol
        file_paths = set()
        for symbol_name in target_symbols:
            candidates = self.symbol_index.get_by_name(symbol_name)
            if candidates:
                file_paths.add(candidates[0].file)

        # Read entire files
        for file_path in file_paths:
            full_path = self.repo_path / file_path
            if full_path.exists():
                try:
                    with open(full_path, "r") as f:
                        content = f.read()
                        files[file_path] = content
                        total_bytes += len(content)
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")

        # Estimate tokens: ~4 chars per token
        tokens_used = total_bytes // 4

        return {
            "files": files,
            "total_bytes": total_bytes,
            "tokens_used": tokens_used,
        }

    def _find_dependencies_in_files(self, files: Dict[str, str]) -> List[Dict]:
        """Find dependencies by text search in files.

        Args:
            files: Dict of file paths to contents

        Returns:
            List of dependency findings
        """
        dependencies = []

        # Simple heuristic: look for imports and function calls in text
        all_symbols = {s.name for s in self.symbol_index.get_all()}

        for file_path, content in files.items():
            for symbol_name in all_symbols:
                if symbol_name in content:
                    dependencies.append(
                        {
                            "file": file_path,
                            "symbol": symbol_name,
                            "type": "text_match",
                        }
                    )

        return dependencies

    def _plan_modifications(self, target_symbols: List[str], dependencies: List[Dict]) -> List[Dict]:
        """Plan modifications.

        Args:
            target_symbols: Symbols to modify
            dependencies: Found dependencies

        Returns:
            Modification plan
        """
        plan = []

        for symbol in target_symbols:
            plan.append(
                {
                    "symbol": symbol,
                    "action": "update",
                    "priority": 1,
                }
            )

        return plan

    def _execute_plan(self, plan: List[Dict]) -> bool:
        """Simulate plan execution.

        Args:
            plan: Modification plan

        Returns:
            Success status
        """
        return all("symbol" in mod for mod in plan)

    def get_statistics(self) -> Dict:
        """Get execution statistics.

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
