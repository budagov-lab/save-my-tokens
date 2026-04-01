"""Agent module for code modification tasks."""

from src.agent.base_agent import BaseAgent
from src.agent.baseline_agent import BaselineAgent
from src.agent.scheduler import (
    Task,
    TaskDAG,
    TaskDAGBuilder,
    TaskDependency,
    TaskDependencyType,
    TaskScheduler,
    SchedulingPlan,
)
from src.agent.execution_engine import (
    ParallelExecutionEngine,
    TaskExecutor,
    create_default_execution_engine,
)

__all__ = [
    "BaseAgent",
    "BaselineAgent",
    "Task",
    "TaskDAG",
    "TaskDAGBuilder",
    "TaskDependency",
    "TaskDependencyType",
    "TaskScheduler",
    "SchedulingPlan",
    "ParallelExecutionEngine",
    "TaskExecutor",
    "create_default_execution_engine",
]
