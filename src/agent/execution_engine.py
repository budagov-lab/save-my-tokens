"""Task execution engine with parallel execution and failure handling."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from loguru import logger

from src.agent.scheduler import ExecutionResult, SchedulingPlan, Task


class TaskExecutor:
    """Execute individual tasks with timeout and retry support."""

    def __init__(self, task_executor: Optional[Callable] = None, max_retries: int = 3):
        """Initialize executor.

        Args:
            task_executor: Callable that executes a task. If None, uses dummy executor.
            max_retries: Max retries on task failure
        """
        self.task_executor = task_executor or self._default_executor
        self.max_retries = max_retries

    def execute(self, task: Task, timeout: float = 30.0) -> Dict:
        """Execute a single task with retry logic.

        Args:
            task: Task to execute
            timeout: Task timeout in seconds

        Returns:
            Execution result with status, timing, and metadata
        """
        result = {
            "task_id": task.id,
            "status": "pending",
            "success": False,
            "attempts": 0,
            "total_time": 0.0,
            "error": None,
        }

        start_time = time.time()
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            result["attempts"] = attempt

            try:
                logger.info(f"[Executor] Running task {task.id} (attempt {attempt}/{self.max_retries})")

                # Execute task with timeout
                task_result = self._execute_with_timeout(task, timeout)

                result["success"] = task_result.get("success", False)
                result["status"] = task_result.get("status", "completed")
                result["details"] = task_result.get("details", {})

                if result["success"]:
                    logger.info(f"[Executor] Task {task.id} completed successfully")
                    break
                else:
                    last_error = task_result.get("error", "Task execution failed")
                    logger.warning(
                        f"[Executor] Task {task.id} attempt {attempt} failed: {last_error}"
                    )

            except TimeoutError:
                last_error = f"Task timeout after {timeout}s"
                logger.error(f"[Executor] {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Executor] Task {task.id} exception: {last_error}")

            if attempt < self.max_retries:
                logger.info(f"[Executor] Retrying task {task.id}")

        result["total_time"] = time.time() - start_time

        if not result["success"]:
            result["status"] = "failed"
            result["error"] = last_error

        return result

    def _execute_with_timeout(self, task: Task, timeout: float) -> Dict:
        """Execute task with timeout enforcement.

        Args:
            task: Task to execute
            timeout: Timeout in seconds

        Returns:
            Task execution result

        Raises:
            TimeoutError: If task exceeds timeout
        """
        start_time = time.time()

        try:
            # Execute task
            result = self.task_executor(task)

            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Task execution exceeded {timeout}s timeout")

            return result

        except TimeoutError:
            raise

    def _default_executor(self, task: Task) -> Dict:
        """Default task executor (dummy implementation).

        Can be overridden with custom executor.

        Args:
            task: Task to execute

        Returns:
            Execution result
        """
        logger.info(f"[Default Executor] Executing task: {task.id}")

        return {
            "success": True,
            "status": "completed",
            "details": {
                "task_id": task.id,
                "description": task.description,
                "symbols_processed": len(task.target_symbols),
            },
        }


class ParallelExecutionEngine:
    """Execute tasks in parallel with dependency tracking."""

    def __init__(
        self,
        task_executor: Optional[TaskExecutor] = None,
        max_workers: int = 4,
        fail_fast: bool = False,
    ):
        """Initialize execution engine.

        Args:
            task_executor: TaskExecutor instance (uses default if None)
            max_workers: Max concurrent workers
            fail_fast: Stop on first failure if True
        """
        self.task_executor = task_executor or TaskExecutor()
        self.max_workers = max_workers
        self.fail_fast = fail_fast
        self.task_map: Dict[str, Task] = {}

    def set_task_executor(self, executor: Callable):
        """Set custom task executor function.

        Args:
            executor: Callable that takes a Task and returns a result dict
        """
        self.task_executor.task_executor = executor

    def execute_plan(
        self, plan: SchedulingPlan, tasks: List[Task], timeout: float = 30.0
    ) -> ExecutionResult:
        """Execute tasks according to scheduling plan.

        Args:
            plan: SchedulingPlan with execution phases
            tasks: List of all tasks
            timeout: Timeout per task in seconds

        Returns:
            ExecutionResult with summary and per-task results
        """
        # Build task map for lookup
        self.task_map = {task.id: task for task in tasks}

        all_results = []
        failed_tasks = []
        start_time = time.time()

        logger.info(f"Starting execution: {len(tasks)} tasks in {plan.num_phases()} phases")

        try:
            for phase_idx, phase_task_ids in enumerate(plan.phases):
                logger.info(
                    f"Executing phase {phase_idx + 1}/{plan.num_phases()}: {len(phase_task_ids)} tasks"
                )

                # Execute tasks in this phase in parallel
                phase_results = self._execute_phase(phase_task_ids, timeout)
                all_results.extend(phase_results)

                # Check for failures
                phase_failed = [r for r in phase_results if not r["success"]]
                if phase_failed:
                    logger.warning(f"Phase {phase_idx + 1}: {len(phase_failed)} failures")
                    failed_tasks.extend(phase_failed)

                    if self.fail_fast:
                        logger.error("Stopping execution due to fail_fast setting")
                        break

            # Determine overall status
            total_successful = len([r for r in all_results if r["success"]])
            status = "SUCCESS" if not failed_tasks else ("PARTIAL" if total_successful > 0 else "FAILED")

            elapsed = time.time() - start_time

            return ExecutionResult(
                status=status,
                completed_tasks=total_successful,
                failed_tasks=failed_tasks,
                results=all_results,
                total_time_seconds=elapsed,
            )

        except Exception as e:
            logger.error(f"Execution engine error: {e}")
            return ExecutionResult(
                status="FAILED",
                completed_tasks=len([r for r in all_results if r["success"]]),
                failed_tasks=failed_tasks,
                results=all_results,
                total_time_seconds=time.time() - start_time,
            )

    def _execute_phase(self, task_ids: List[str], timeout: float) -> List[Dict]:
        """Execute all tasks in a phase in parallel.

        Args:
            task_ids: List of task IDs to execute
            timeout: Timeout per task

        Returns:
            List of execution results
        """
        results = []

        if not task_ids:
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            futures = {}

            for task_id in task_ids:
                task = self.task_map.get(task_id)
                if task:
                    future = executor.submit(self.task_executor.execute, task, timeout)
                    futures[future] = task_id

            # Collect results as they complete
            for future in as_completed(futures):
                task_id = futures[future]

                try:
                    result = future.result(timeout=timeout + 5)  # Allow extra time for result retrieval
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error executing task {task_id}: {e}")
                    results.append(
                        {
                            "task_id": task_id,
                            "status": "failed",
                            "success": False,
                            "error": str(e),
                        }
                    )

        return results


def create_default_execution_engine(max_workers: int = 4) -> ParallelExecutionEngine:
    """Create a default execution engine with dummy task executor.

    Args:
        max_workers: Max concurrent workers

    Returns:
        Configured ParallelExecutionEngine
    """
    task_executor = TaskExecutor(max_retries=3)
    return ParallelExecutionEngine(
        task_executor=task_executor,
        max_workers=max_workers,
        fail_fast=False,
    )
