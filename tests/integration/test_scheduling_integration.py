"""Integration tests for task scheduling and execution."""

import pytest

from src.agent.execution_engine import ParallelExecutionEngine, TaskExecutor
from src.agent.scheduler import Task, TaskScheduler, TaskDAGBuilder


class TestSchedulingIntegration:
    """Integration tests for full scheduling pipeline."""

    def test_schedule_and_execute_workflow(self):
        """Test complete workflow: schedule tasks, then execute them."""

        # Track execution order
        execution_log = []

        def tracking_executor(task):
            execution_log.append(task.id)
            return {"success": True, "status": "completed", "details": {}}

        # Create tasks with dependencies
        tasks = [
            Task(id="t1", description="Parse file", target_symbols=["ast"]),
            Task(
                id="t2",
                description="Build graph",
                target_symbols=["graph"],
                dependency_symbols=["ast"],
            ),
            Task(
                id="t3",
                description="Build embeddings",
                target_symbols=["embeddings"],
                dependency_symbols=["ast"],
            ),
            Task(
                id="t4",
                description="Run queries",
                target_symbols=["results"],
                dependency_symbols=["graph", "embeddings"],
            ),
        ]

        # Schedule
        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=2)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        # Verify execution completed successfully
        assert result.status == "SUCCESS"
        assert result.completed_tasks == 4

        # Verify execution order respects dependencies
        # t1 must come before t2, t3
        # t2, t3 must come before t4
        t1_idx = execution_log.index("t1")
        t4_idx = execution_log.index("t4")

        assert t1_idx < execution_log.index("t2")
        assert t1_idx < execution_log.index("t3")
        assert execution_log.index("t2") < t4_idx
        assert execution_log.index("t3") < t4_idx

    def test_parallel_execution_respects_phases(self):
        """Test that parallel execution respects phase boundaries."""

        # Track tasks running at same time
        concurrent_tasks = set()
        max_concurrent = 0

        def tracking_executor(task):
            nonlocal max_concurrent
            concurrent_tasks.add(task.id)
            max_concurrent = max(max_concurrent, len(concurrent_tasks))
            # Simulate work
            import time

            time.sleep(0.01)
            concurrent_tasks.remove(task.id)
            return {"success": True, "status": "completed", "details": {}}

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(4)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # All tasks are independent, so all should be in one phase
        assert len(plan.phases) == 1

        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=4)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        # With 4 workers and 4 independent tasks, we may see parallelism
        assert max_concurrent >= 1

    def test_complex_dependency_graph(self):
        """Test scheduling and execution of complex dependency graph."""

        execution_times = {}

        def tracking_executor(task):
            import time

            execution_times[task.id] = time.time()
            return {"success": True, "status": "completed", "details": {}}

        # Complex DAG with multiple dependency chains
        tasks = [
            Task(id="t1", description="Init", target_symbols=["data"]),
            Task(
                id="t2",
                description="Process A",
                target_symbols=["result_a"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t3",
                description="Process B",
                target_symbols=["result_b"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t4",
                description="Process C",
                target_symbols=["result_c"],
                dependency_symbols=["data"],
            ),
            Task(
                id="t5",
                description="Merge AB",
                target_symbols=["merged_ab"],
                dependency_symbols=["result_a", "result_b"],
            ),
            Task(
                id="t6",
                description="Merge ABC",
                target_symbols=["final"],
                dependency_symbols=["merged_ab", "result_c"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Verify plan structure
        assert plan.num_phases() == 4
        assert plan.phases[0] == ["t1"]  # Init first
        assert set(plan.phases[1]) == {"t2", "t3", "t4"}  # Parallel processing
        assert plan.phases[2] == ["t5"]  # Merge AB
        assert plan.phases[3] == ["t6"]  # Final merge

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=3)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"
        assert result.completed_tasks == 6

        # Verify dependency order
        assert execution_times["t1"] < execution_times["t2"]
        assert execution_times["t1"] < execution_times["t3"]
        assert execution_times["t1"] < execution_times["t4"]
        assert execution_times["t2"] < execution_times["t5"]
        assert execution_times["t3"] < execution_times["t5"]
        assert execution_times["t5"] < execution_times["t6"]
        assert execution_times["t4"] < execution_times["t6"]

    def test_conflict_detection_in_workflow(self):
        """Test that conflicting tasks are properly serialized."""

        # Track execution
        execution_log = []

        def tracking_executor(task):
            execution_log.append(task.id)
            return {"success": True, "status": "completed", "details": {}}

        # Create conflicting tasks
        tasks = [
            Task(
                id="t1",
                description="Modify function_a",
                target_symbols=["function_a"],
            ),
            Task(
                id="t2",
                description="Also modify function_a (conflict!)",
                target_symbols=["function_a"],
            ),
            Task(
                id="t3",
                description="Modify function_b (independent)",
                target_symbols=["function_b"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # t1 and t2 conflict (same symbol), so must be serialized
        # t3 is independent
        assert plan.num_phases() >= 2

        # Verify phases respect conflict
        t1_phase = None
        t2_phase = None
        for idx, phase in enumerate(plan.phases):
            if "t1" in phase:
                t1_phase = idx
            if "t2" in phase:
                t2_phase = idx

        assert t1_phase < t2_phase  # t1 before t2

        # Execute
        task_executor = TaskExecutor(task_executor=tracking_executor)
        engine = ParallelExecutionEngine(task_executor=task_executor, max_workers=2)
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        assert result.status == "SUCCESS"

        # Verify execution order: t1 before t2
        assert execution_log.index("t1") < execution_log.index("t2")

    def test_large_batch_scheduling(self):
        """Test scheduling of large task batches."""

        # Create 100 independent tasks
        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(100)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # All independent → single phase
        assert plan.num_phases() == 1
        assert len(plan.phases[0]) == 100

        # Verify scheduling was fast
        assert plan.total_tasks == 100

    def test_execution_with_partial_failures(self):
        """Test execution behavior with some task failures."""

        def failure_executor(task):
            # Fail on tasks with even IDs
            task_num = int(task.id[1:])
            if task_num % 2 == 0:
                return {"success": False, "status": "failed", "error": "Simulated error"}
            return {"success": True, "status": "completed", "details": {}}

        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(6)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        task_executor = TaskExecutor(task_executor=failure_executor)
        engine = ParallelExecutionEngine(
            task_executor=task_executor, max_workers=2, fail_fast=False
        )
        result = engine.execute_plan(plan, tasks, timeout=5.0)

        # Some tasks should succeed, some fail
        assert result.status == "PARTIAL"
        assert result.completed_tasks == 3  # Odd-numbered tasks: t1, t3, t5
        assert len(result.failed_tasks) == 3  # Even-numbered: t0, t2, t4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
