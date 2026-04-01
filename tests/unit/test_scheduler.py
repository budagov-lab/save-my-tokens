"""Unit tests for task scheduling and DAG management."""

import pytest

from src.agent.scheduler import (
    Task,
    TaskDAG,
    TaskDAGBuilder,
    TaskDependency,
    TaskDependencyType,
    TaskScheduler,
    SchedulingPlan,
)


class TestTask:
    """Tests for Task data class."""

    def test_task_creation(self):
        """Test basic task creation."""
        task = Task(
            id="task_1",
            description="Test task",
            target_symbols=["func_a", "func_b"],
            dependency_symbols=["func_c"],
        )

        assert task.id == "task_1"
        assert task.description == "Test task"
        assert task.target_symbols == ["func_a", "func_b"]
        assert task.dependency_symbols == ["func_c"]

    def test_task_equality(self):
        """Test task equality by ID."""
        task1 = Task(id="task_1", description="Task", target_symbols=[])
        task2 = Task(id="task_1", description="Different", target_symbols=[])
        task3 = Task(id="task_2", description="Task", target_symbols=[])

        assert task1 == task2  # Same ID
        assert task1 != task3  # Different ID

    def test_task_hashable(self):
        """Test that tasks can be hashed."""
        task1 = Task(id="task_1", description="Task", target_symbols=[])
        task2 = Task(id="task_2", description="Task", target_symbols=[])

        task_set = {task1, task2}
        assert len(task_set) == 2

        task_set.add(task1)
        assert len(task_set) == 2  # No duplicate


class TestTaskDAG:
    """Tests for task dependency graph."""

    def test_dag_creation(self):
        """Test DAG creation with tasks and edges."""
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym1"]),
            Task(id="t2", description="Task 2", target_symbols=["sym2"]),
            Task(id="t3", description="Task 3", target_symbols=["sym3"]),
        ]

        edges = [
            TaskDependency(
                task_a_id="t1",
                task_b_id="t2",
                type=TaskDependencyType.DEPENDS_ON,
                reason="Test dependency",
            ),
        ]

        dag = TaskDAG(tasks=tasks, edges=edges)

        assert len(dag.tasks) == 3
        assert len(dag.edges) == 1

    def test_get_dependencies(self):
        """Test retrieving task dependencies.

        Edge (task_a -> task_b) with DEPENDS_ON means: task_b depends on task_a.
        """
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym1"]),
            Task(id="t2", description="Task 2", target_symbols=["sym2"]),
            Task(id="t3", description="Task 3", target_symbols=["sym3"]),
        ]

        edges = [
            # t1 must run before t2 (t2 depends on t1)
            TaskDependency("t1", "t2", TaskDependencyType.DEPENDS_ON),
            # t1 must run before t3 (t3 depends on t1)
            TaskDependency("t1", "t3", TaskDependencyType.DEPENDS_ON),
        ]

        dag = TaskDAG(tasks=tasks, edges=edges)

        # t2 depends on t1
        assert dag.get_dependencies("t2") == ["t1"]
        # t3 depends on t1
        assert dag.get_dependencies("t3") == ["t1"]
        # t1 has no dependencies
        assert dag.get_dependencies("t1") == []

    def test_get_dependents(self):
        """Test retrieving tasks that depend on a given task.

        Edge (task_a -> task_b) with DEPENDS_ON means: task_b depends on task_a.
        So task_a's dependents are those tasks that depend on it.
        """
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym1"]),
            Task(id="t2", description="Task 2", target_symbols=["sym2"]),
            Task(id="t3", description="Task 3", target_symbols=["sym3"]),
        ]

        edges = [
            # t1 must run before t2 (t2 depends on t1)
            TaskDependency("t1", "t2", TaskDependencyType.DEPENDS_ON),
            # t1 must run before t3 (t3 depends on t1)
            TaskDependency("t1", "t3", TaskDependencyType.DEPENDS_ON),
        ]

        dag = TaskDAG(tasks=tasks, edges=edges)

        # t1 is depended on by t2 and t3
        dependents = dag.get_dependents("t1")
        assert set(dependents) == {"t2", "t3"}

    def test_detect_no_cycles(self):
        """Test cycle detection when no cycles exist."""
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym1"]),
            Task(id="t2", description="Task 2", target_symbols=["sym2"]),
            Task(id="t3", description="Task 3", target_symbols=["sym3"]),
        ]

        edges = [
            TaskDependency("t2", "t1", TaskDependencyType.DEPENDS_ON),
            TaskDependency("t3", "t2", TaskDependencyType.DEPENDS_ON),
        ]

        dag = TaskDAG(tasks=tasks, edges=edges)
        cycles = dag.detect_cycles()

        assert len(cycles) == 0

    def test_detect_simple_cycle(self):
        """Test detection of simple circular dependency."""
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym1"]),
            Task(id="t2", description="Task 2", target_symbols=["sym2"]),
        ]

        # Create a cycle: t1 -> t2 -> t1
        edges = [
            TaskDependency("t2", "t1", TaskDependencyType.DEPENDS_ON),
            TaskDependency("t1", "t2", TaskDependencyType.DEPENDS_ON),
        ]

        dag = TaskDAG(tasks=tasks, edges=edges)
        cycles = dag.detect_cycles()

        assert len(cycles) > 0


class TestTaskDAGBuilder:
    """Tests for DAG builder with conflict detection."""

    def test_builder_no_conflicts(self):
        """Test building DAG when no conflicts exist."""
        tasks = [
            Task(
                id="t1",
                description="Modify sym_a",
                target_symbols=["sym_a"],
                dependency_symbols=[],
            ),
            Task(
                id="t2",
                description="Modify sym_b",
                target_symbols=["sym_b"],
                dependency_symbols=[],
            ),
        ]

        builder = TaskDAGBuilder()
        dag = builder.build_dag(tasks)

        assert len(dag.tasks) == 2
        assert len(dag.edges) == 1

        # Should have SAFE_PARALLEL edge
        parallel_edges = [e for e in dag.edges if e.type == TaskDependencyType.SAFE_PARALLEL]
        assert len(parallel_edges) == 1

    def test_builder_conflicting_symbols(self):
        """Test that tasks modifying same symbol are serialized."""
        tasks = [
            Task(
                id="t1",
                description="Modify sym_a",
                target_symbols=["sym_a"],
            ),
            Task(
                id="t2",
                description="Also modify sym_a",
                target_symbols=["sym_a"],
            ),
        ]

        builder = TaskDAGBuilder()
        dag = builder.build_dag(tasks)

        # Should have DEPENDS_ON edge (conflict detected)
        depend_edges = [e for e in dag.edges if e.type == TaskDependencyType.DEPENDS_ON]
        assert len(depend_edges) == 1

    def test_builder_read_write_conflict(self):
        """Test detection of read-write conflicts."""
        tasks = [
            Task(
                id="t1",
                description="Modify sym_a",
                target_symbols=["sym_a"],
                dependency_symbols=[],
            ),
            Task(
                id="t2",
                description="Read sym_a",
                target_symbols=["sym_b"],
                dependency_symbols=["sym_a"],
            ),
        ]

        builder = TaskDAGBuilder()
        dag = builder.build_dag(tasks)

        # t1 writes what t2 reads → conflict
        depend_edges = [e for e in dag.edges if e.type == TaskDependencyType.DEPENDS_ON]
        assert len(depend_edges) == 1


class TestTaskScheduler:
    """Tests for task scheduling."""

    def test_schedule_independent_tasks(self):
        """Test scheduling of independent tasks."""
        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(5)
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # All independent tasks should be in same phase (parallel)
        assert plan.num_phases() == 1
        assert len(plan.phases[0]) == 5

    def test_schedule_dependent_tasks(self):
        """Test scheduling of dependent tasks."""
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym_1"]),
            Task(
                id="t2",
                description="Task 2",
                target_symbols=["sym_2"],
                dependency_symbols=["sym_1"],
            ),
            Task(
                id="t3",
                description="Task 3",
                target_symbols=["sym_3"],
                dependency_symbols=["sym_2"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Should have 3 phases (linear chain)
        assert plan.num_phases() == 3

        # Verify the order respects dependencies
        # Find positions of each task
        t1_phase = next(i for i, phase in enumerate(plan.phases) if "t1" in phase)
        t2_phase = next(i for i, phase in enumerate(plan.phases) if "t2" in phase)
        t3_phase = next(i for i, phase in enumerate(plan.phases) if "t3" in phase)

        assert t1_phase < t2_phase
        assert t2_phase < t3_phase

    def test_schedule_mixed_dependencies(self):
        """Test scheduling with mixed parallel and serial dependencies."""
        # t1 -> t2 -> t4
        #    -> t3 ->
        tasks = [
            Task(id="t1", description="Task 1", target_symbols=["sym_1"]),
            Task(
                id="t2",
                description="Task 2",
                target_symbols=["sym_2"],
                dependency_symbols=["sym_1"],
            ),
            Task(
                id="t3",
                description="Task 3",
                target_symbols=["sym_3"],
                dependency_symbols=["sym_1"],
            ),
            Task(
                id="t4",
                description="Task 4",
                target_symbols=["sym_4"],
                dependency_symbols=["sym_2", "sym_3"],
            ),
        ]

        scheduler = TaskScheduler()
        plan = scheduler.schedule(tasks)

        # Phase 1: t1
        # Phase 2: t2, t3 (parallel)
        # Phase 3: t4
        assert plan.num_phases() == 3

        # Find phases for each task
        t1_phase = next(i for i, phase in enumerate(plan.phases) if "t1" in phase)
        t2_phase = next(i for i, phase in enumerate(plan.phases) if "t2" in phase)
        t3_phase = next(i for i, phase in enumerate(plan.phases) if "t3" in phase)
        t4_phase = next(i for i, phase in enumerate(plan.phases) if "t4" in phase)

        # Verify order
        assert t1_phase < t2_phase  # t1 before t2
        assert t1_phase < t3_phase  # t1 before t3
        assert t2_phase == t3_phase  # t2 and t3 can be parallel
        assert t2_phase < t4_phase  # t2, t3 before t4
        assert t3_phase < t4_phase

    def test_schedule_detects_cycles(self):
        """Test that scheduling detects circular dependencies."""
        tasks = [
            Task(
                id="t1",
                description="Task 1",
                target_symbols=["sym_1"],
                dependency_symbols=["sym_2"],
            ),
            Task(
                id="t2",
                description="Task 2",
                target_symbols=["sym_2"],
                dependency_symbols=["sym_1"],
            ),
        ]

        scheduler = TaskScheduler()

        # Should raise ValueError for circular dependency
        with pytest.raises(ValueError, match="Circular task dependencies"):
            scheduler.schedule(tasks)

    def test_scheduling_plan_metrics(self):
        """Test SchedulingPlan metrics."""
        tasks = [
            Task(id=f"t{i}", description=f"Task {i}", target_symbols=[f"sym_{i}"])
            for i in range(4)
        ]

        plan = SchedulingPlan(
            phases=[["t0"], ["t1", "t2"], ["t3"]],
            total_tasks=4,
            parallelizable_pairs=2,
        )

        assert plan.num_phases() == 3
        assert plan.total_tasks == 4

    def test_empty_task_list(self):
        """Test scheduling with empty task list."""
        scheduler = TaskScheduler()
        plan = scheduler.schedule([])

        assert plan.num_phases() == 0
        assert plan.total_tasks == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
