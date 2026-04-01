"""Unit tests for task execution engine."""

import time
from unittest.mock import Mock

import pytest

from src.agent.execution_engine import (
    ParallelExecutionEngine,
    TaskExecutor,
    create_default_execution_engine,
)
from src.agent.scheduler import SchedulingPlan, Task


class TestTaskExecutor:
    """Tests for individual task execution."""

    def test_execute_successful_task(self):
        """Test executing a successful task."""

        def dummy_executor(task):
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=dummy_executor)
        task = Task(id="t1", description="Test", target_symbols=[])

        result = executor.execute(task, timeout=5.0)

        assert result["task_id"] == "t1"
        assert result["success"] is True
        assert result["status"] == "completed"
        assert result["attempts"] == 1

    def test_execute_failing_task_retries(self):
        """Test that failed tasks are retried."""
        call_count = 0

        def failing_executor(task):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"success": False, "status": "failed", "error": "Transient error"}
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=failing_executor, max_retries=3)
        task = Task(id="t1", description="Test", target_symbols=[])

        result = executor.execute(task, timeout=5.0)

        assert result["success"] is True
        assert result["attempts"] == 3

    def test_execute_exhausts_retries(self):
        """Test task that exhausts all retries."""

        def failing_executor(task):
            return {"success": False, "status": "failed", "error": "Permanent error"}

        executor = TaskExecutor(task_executor=failing_executor, max_retries=2)
        task = Task(id="t1", description="Test", target_symbols=[])

        result = executor.execute(task, timeout=5.0)

        assert result["success"] is False
        assert result["attempts"] == 2
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_default_executor(self):
        """Test default dummy executor."""
        executor = TaskExecutor()
        task = Task(
            id="t1", description="Test task", target_symbols=["sym_a", "sym_b"]
        )

        result = executor.execute(task, timeout=5.0)

        assert result["success"] is True
        assert result["task_id"] == "t1"
        assert result["details"]["symbols_processed"] == 2

    def test_execute_tracks_timing(self):
        """Test that execution time is tracked."""

        def slow_executor(task):
            time.sleep(0.1)
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=slow_executor)
        task = Task(id="t1", description="Test", target_symbols=[])

        result = executor.execute(task, timeout=5.0)

        assert result["total_time"] >= 0.1


class TestParallelExecutionEngine:
    """Tests for parallel task execution."""

    def test_create_default_engine(self):
        """Test creating default execution engine."""
        engine = create_default_execution_engine(max_workers=4)

        assert engine.max_workers == 4
        assert engine.task_executor is not None

    def test_execute_single_phase(self):
        """Test execution of tasks in single phase."""

        def dummy_executor(task):
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=dummy_executor)
        engine = ParallelExecutionEngine(task_executor=executor, max_workers=2)

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(3)
        ]

        plan = SchedulingPlan(
            phases=[["t0", "t1", "t2"]],  # All in one phase
            total_tasks=3,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        assert result.completed_tasks == 3
        assert len(result.failed_tasks) == 0

    def test_execute_multiple_phases(self):
        """Test execution with sequential phases."""

        def dummy_executor(task):
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=dummy_executor)
        engine = ParallelExecutionEngine(task_executor=executor, max_workers=2)

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(4)
        ]

        plan = SchedulingPlan(
            phases=[["t0"], ["t1", "t2"], ["t3"]],
            total_tasks=4,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        assert result.completed_tasks == 4

    def test_execute_with_failures(self):
        """Test execution with some task failures."""

        def executor_with_failure(task):
            if task.id == "t1":
                return {"success": False, "status": "failed", "error": "Test error"}
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=executor_with_failure)
        engine = ParallelExecutionEngine(
            task_executor=executor,
            max_workers=2,
            fail_fast=False,
        )

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(3)
        ]

        plan = SchedulingPlan(
            phases=[["t0", "t1", "t2"]],
            total_tasks=3,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "PARTIAL"
        assert result.completed_tasks == 2
        assert len(result.failed_tasks) == 1

    def test_fail_fast_stops_on_failure(self):
        """Test that fail_fast stops execution on first failure."""

        def executor_with_failure(task):
            if task.id == "t0":
                return {"success": False, "status": "failed", "error": "Test error"}
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=executor_with_failure)
        engine = ParallelExecutionEngine(
            task_executor=executor,
            max_workers=2,
            fail_fast=True,
        )

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(4)
        ]

        # Two phases to test that execution stops after first phase failure
        plan = SchedulingPlan(
            phases=[["t0"], ["t1", "t2", "t3"]],
            total_tasks=4,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "FAILED"
        # Should have stopped execution after first phase
        assert result.completed_tasks == 0

    def test_set_custom_executor(self):
        """Test setting custom task executor."""
        engine = create_default_execution_engine()

        custom_executor_called = False

        def custom_executor(task):
            nonlocal custom_executor_called
            custom_executor_called = True
            return {"success": True, "status": "completed", "details": {}}

        engine.set_task_executor(custom_executor)

        tasks = [Task(id="t1", description="Test", target_symbols=[])]
        plan = SchedulingPlan(phases=[["t1"]], total_tasks=1)

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert custom_executor_called is True
        assert result.status == "SUCCESS"

    def test_execution_result_metrics(self):
        """Test ExecutionResult metrics."""

        def dummy_executor(task):
            if task.id in ["t0", "t2"]:
                return {"success": False, "status": "failed", "error": "Error"}
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=dummy_executor)
        engine = ParallelExecutionEngine(task_executor=executor, max_workers=2)

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(3)
        ]

        plan = SchedulingPlan(
            phases=[["t0", "t1", "t2"]],
            total_tasks=3,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.completed_tasks == 1
        assert len(result.failed_tasks) == 2
        assert result.success_rate() == pytest.approx(1.0 / 3.0)

    def test_empty_phase_list(self):
        """Test execution with empty phases."""
        engine = create_default_execution_engine()

        plan = SchedulingPlan(
            phases=[],
            total_tasks=0,
        )

        result = engine.execute_plan(plan, [], timeout=5.0)

        assert result.status == "SUCCESS"
        assert result.completed_tasks == 0

    def test_total_execution_time(self):
        """Test that total execution time is tracked."""

        def slow_executor(task):
            time.sleep(0.05)
            return {"success": True, "status": "completed", "details": {}}

        executor = TaskExecutor(task_executor=slow_executor)
        engine = ParallelExecutionEngine(task_executor=executor, max_workers=1)

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[])
            for i in range(2)
        ]

        plan = SchedulingPlan(
            phases=[["t0"], ["t1"]],
            total_tasks=2,
        )

        result = engine.execute_plan(plan, tasks, timeout=5.0)

        # Should be at least 0.1s (2 tasks * 0.05s)
        assert result.total_time_seconds >= 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
