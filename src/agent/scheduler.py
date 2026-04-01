"""Task scheduling and dependency graph management for automated agent execution."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
from datetime import datetime

from loguru import logger


class TaskDependencyType(Enum):
    """Types of dependencies between tasks."""

    DEPENDS_ON = "DEPENDS_ON"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SAFE_PARALLEL = "SAFE_PARALLEL"


@dataclass
class Task:
    """Represents a code modification task."""

    id: str
    description: str
    target_symbols: List[str]  # Symbols this task modifies
    dependency_symbols: List[str] = field(default_factory=list)  # Symbols this task reads
    metadata: Dict = field(default_factory=dict)  # Additional task info
    created_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Task):
            return self.id == other.id
        return False


@dataclass
class TaskDependency:
    """Edge in the task dependency graph."""

    task_a_id: str
    task_b_id: str
    type: TaskDependencyType
    reason: str = ""


@dataclass
class TaskDAG:
    """Directed acyclic graph of task dependencies."""

    tasks: List[Task]
    edges: List[TaskDependency]

    def __post_init__(self):
        self._adjacency_list: Optional[Dict[str, List[str]]] = None
        self._reverse_adjacency_list: Optional[Dict[str, List[str]]] = None

    def _build_adjacency_list(self):
        """Build adjacency lists for efficient graph traversal.

        Edge (task_a -> task_b) with type DEPENDS_ON means:
        task_b depends on task_a (task_a must run before task_b).

        So task_a's dependents include task_b.
        And task_b's dependencies include task_a.
        """
        if self._adjacency_list is not None:
            return

        self._adjacency_list = {task.id: [] for task in self.tasks}
        self._reverse_adjacency_list = {task.id: [] for task in self.tasks}

        for edge in self.edges:
            if edge.type == TaskDependencyType.DEPENDS_ON:
                # task_b depends on task_a
                self._adjacency_list[edge.task_b_id].append(edge.task_a_id)
                self._reverse_adjacency_list[edge.task_a_id].append(edge.task_b_id)

    def get_dependencies(self, task_id: str) -> List[str]:
        """Get tasks that this task depends on."""
        self._build_adjacency_list()
        return self._adjacency_list.get(task_id, [])

    def get_dependents(self, task_id: str) -> List[str]:
        """Get tasks that depend on this task."""
        self._build_adjacency_list()
        return self._reverse_adjacency_list.get(task_id, [])

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS.

        Returns:
            List of cycles (each cycle is a list of task IDs)
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.get_dependencies(node):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            path.pop()
            rec_stack.remove(node)

        for task in self.tasks:
            if task.id not in visited:
                dfs(task.id, [])

        return cycles


class TaskDAGBuilder:
    """Build task dependency graphs with conflict detection."""

    def __init__(self, conflict_detector=None):
        """Initialize DAG builder.

        Args:
            conflict_detector: Optional conflict detector (e.g., BreakingChangeDetector)
        """
        self.conflict_detector = conflict_detector

    def build_dag(self, tasks: List[Task]) -> TaskDAG:
        """Build dependency graph from task list.

        Uses conflict detection to identify which tasks must be serialized.

        Args:
            tasks: List of tasks to schedule

        Returns:
            TaskDAG with dependency edges
        """
        edges = []
        task_dict = {task.id: task for task in tasks}

        # First, identify data dependencies between tasks
        for task_b in tasks:
            # Find tasks that provide symbols that task_b depends on
            for task_a in tasks:
                if task_a.id == task_b.id:
                    continue

                # Check if task_a produces symbols that task_b needs
                if set(task_a.target_symbols) & set(task_b.dependency_symbols):
                    # task_a must run before task_b (data dependency)
                    edges.append(
                        TaskDependency(
                            task_a_id=task_a.id,
                            task_b_id=task_b.id,
                            type=TaskDependencyType.DEPENDS_ON,
                            reason=f"Data dependency: task_b needs symbols from task_a",
                        )
                    )

        # Now check for conflicts between tasks
        for i, task_a in enumerate(tasks):
            for task_b in tasks[i + 1 :]:
                conflict = self._check_conflict(task_a, task_b)

                if conflict:
                    # Check if dependency edge already exists
                    has_dependency = any(
                        (e.task_a_id == task_a.id and e.task_b_id == task_b.id)
                        or (e.task_a_id == task_b.id and e.task_b_id == task_a.id)
                        for e in edges
                        if e.type == TaskDependencyType.DEPENDS_ON
                    )

                    if not has_dependency:
                        # Tasks conflict - must serialize (task_a before task_b)
                        edges.append(
                            TaskDependency(
                                task_a_id=task_a.id,
                                task_b_id=task_b.id,
                                type=TaskDependencyType.DEPENDS_ON,
                                reason=f"Conflict detected: {conflict}",
                            )
                        )
                else:
                    # No conflict - record as safe to parallel
                    edges.append(
                        TaskDependency(
                            task_a_id=task_a.id,
                            task_b_id=task_b.id,
                            type=TaskDependencyType.SAFE_PARALLEL,
                            reason="No conflicts detected",
                        )
                    )

        return TaskDAG(tasks=tasks, edges=edges)

    def _check_conflict(self, task_a: Task, task_b: Task) -> Optional[str]:
        """Check if two tasks conflict.

        Conflict occurs when:
        - Both tasks modify the same symbol, OR
        - Task A modifies a symbol that Task B depends on (and vice versa)

        Args:
            task_a: First task
            task_b: Second task

        Returns:
            Conflict description if exists, None otherwise
        """
        # Check for symbol overlap in modifications
        target_overlap = set(task_a.target_symbols) & set(task_b.target_symbols)
        if target_overlap:
            return f"Both tasks modify: {target_overlap}"

        # Check for read-write conflicts
        # (Task A modifies what Task B reads, or vice versa)
        task_a_writes = set(task_a.target_symbols)
        task_b_writes = set(task_b.target_symbols)
        task_a_reads = set(task_a.dependency_symbols)
        task_b_reads = set(task_b.dependency_symbols)

        # Task A writes what Task B reads
        if task_a_writes & task_b_reads:
            return f"Task A writes symbols Task B depends on"

        # Task B writes what Task A reads
        if task_b_writes & task_a_reads:
            return f"Task B writes symbols Task A depends on"

        return None


@dataclass
class SchedulingPlan:
    """Execution plan for a set of tasks."""

    phases: List[List[str]]  # Each phase is a list of task IDs that can run in parallel
    total_tasks: int
    parallelizable_pairs: int = 0
    estimated_time_seconds: float = 0.0

    def num_phases(self) -> int:
        """Get number of sequential phases."""
        return len(self.phases)

    def parallelization_ratio(self) -> float:
        """Calculate parallelization efficiency.

        Ratio of sequential phases needed vs. all tasks in parallel.
        Higher is better (closer to 1.0 means more parallelization possible).
        """
        if self.total_tasks == 0:
            return 0.0
        return self.total_tasks / (self.num_phases() * self.total_tasks) if self.num_phases() > 0 else 0.0


@dataclass
class ExecutionResult:
    """Result of task execution."""

    status: str  # 'SUCCESS', 'FAILED', 'PARTIAL'
    completed_tasks: int
    failed_tasks: List[Dict] = field(default_factory=list)
    results: List[Dict] = field(default_factory=list)
    total_time_seconds: float = 0.0

    def success_rate(self) -> float:
        """Calculate task success rate."""
        total = self.completed_tasks + len(self.failed_tasks)
        if total == 0:
            return 0.0
        return self.completed_tasks / total


class TaskScheduler:
    """Schedule and execute tasks with parallelization support."""

    def __init__(
        self,
        conflict_detector=None,
        max_parallel: int = 4,
        task_timeout: float = 30.0,
        fail_fast: bool = False,
    ):
        """Initialize scheduler.

        Args:
            conflict_detector: Conflict detection logic
            max_parallel: Max tasks to run in parallel
            task_timeout: Timeout per task in seconds
            fail_fast: Stop on first task failure if True
        """
        self.dag_builder = TaskDAGBuilder(conflict_detector)
        self.max_parallel = max_parallel
        self.task_timeout = task_timeout
        self.fail_fast = fail_fast

    def schedule(self, tasks: List[Task]) -> SchedulingPlan:
        """Generate execution plan from task list.

        Args:
            tasks: Tasks to schedule

        Returns:
            SchedulingPlan with execution phases

        Raises:
            ValueError: If circular dependency detected
        """
        if not tasks:
            return SchedulingPlan(phases=[], total_tasks=0)

        # Build dependency graph
        dag = self.dag_builder.build_dag(tasks)

        # Detect cycles (fatal)
        cycles = dag.detect_cycles()
        if cycles:
            logger.error(f"Circular task dependencies detected: {cycles}")
            raise ValueError(f"Circular task dependencies: {cycles}")

        # Compute execution phases
        phases = self._compute_execution_phases(dag)

        # Count parallelizable pairs
        parallelizable = sum(
            1
            for edge in dag.edges
            if edge.type == TaskDependencyType.SAFE_PARALLEL
        )

        plan = SchedulingPlan(
            phases=phases,
            total_tasks=len(tasks),
            parallelizable_pairs=parallelizable,
        )

        logger.info(
            f"Scheduled {len(tasks)} tasks in {plan.num_phases()} phases "
            f"({parallelizable} parallelizable pairs)"
        )

        return plan

    def _compute_execution_phases(self, dag: TaskDAG) -> List[List[str]]:
        """Partition tasks into sequential phases.

        Each phase contains tasks that can run in parallel.
        Phases must execute sequentially to respect dependencies.

        Args:
            dag: Task dependency graph

        Returns:
            List of phases (each phase is a list of task IDs)

        Raises:
            RuntimeError: If deadlock detected (shouldn't happen with cycle detection)
        """
        phases = []
        visited = set()
        task_ids = {task.id for task in dag.tasks}

        while len(visited) < len(dag.tasks):
            # Find all tasks with all dependencies satisfied
            phase = []

            for task in dag.tasks:
                if task.id in visited:
                    continue

                # Check if all dependencies are satisfied
                dependencies = dag.get_dependencies(task.id)
                dependencies_met = all(dep_id in visited for dep_id in dependencies)

                if dependencies_met:
                    phase.append(task.id)

            if not phase:
                # Deadlock - no progress made (shouldn't happen if cycle detection works)
                unvisited = task_ids - visited
                logger.error(f"Deadlock detected. Unvisited tasks: {unvisited}")
                raise RuntimeError(
                    f"Deadlock in task scheduling. Unvisited: {unvisited}"
                )

            phases.append(phase)
            visited.update(phase)

        return phases
