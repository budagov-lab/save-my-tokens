"""REST API endpoints for task scheduling and execution."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agent.execution_engine import ParallelExecutionEngine, create_default_execution_engine
from src.agent.scheduler import Task, TaskScheduler
from loguru import logger

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])


class TaskRequest(BaseModel):
    """Request model for a single task."""

    id: str = Field(..., description="Unique task ID")
    description: str = Field(..., description="Task description")
    target_symbols: List[str] = Field(default_factory=list, description="Symbols modified by this task")
    dependency_symbols: List[str] = Field(default_factory=list, description="Symbols read by this task")


class SchedulingRequest(BaseModel):
    """Request model for scheduling a batch of tasks."""

    tasks: List[TaskRequest] = Field(..., description="List of tasks to schedule")


class PhaseInfo(BaseModel):
    """Information about an execution phase."""

    phase_number: int = Field(..., description="Phase index (0-based)")
    task_ids: List[str] = Field(..., description="Task IDs in this phase")
    can_parallel: bool = Field(default=True, description="Whether tasks can run in parallel")


class SchedulingPlanResponse(BaseModel):
    """Response model for scheduling plan."""

    status: str = Field(default="success", description="Status: 'success' or 'error'")
    total_tasks: int = Field(..., description="Total tasks in the plan")
    num_phases: int = Field(..., description="Number of sequential phases")
    phases: List[PhaseInfo] = Field(..., description="Detailed phase information")
    parallelizable_pairs: int = Field(..., description="Count of task pairs that can run in parallel")
    cycles_detected: List[List[str]] = Field(default_factory=list, description="Circular dependencies (if any)")


class TaskResult(BaseModel):
    """Result for a single executed task."""

    task_id: str
    status: str
    success: bool
    attempts: int = 1
    total_time: float = 0.0
    error: str = None


class ExecutionResponse(BaseModel):
    """Response model for execution result."""

    status: str = Field(..., description="'SUCCESS', 'PARTIAL', or 'FAILED'")
    completed_tasks: int
    failed_tasks: int = 0
    total_time_seconds: float
    task_results: List[TaskResult] = Field(default_factory=list, description="Per-task results")


# Global scheduler and execution engine
_scheduler = None
_execution_engine = None


def get_scheduler() -> TaskScheduler:
    """Get or create global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler


def get_execution_engine() -> ParallelExecutionEngine:
    """Get or create global execution engine."""
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = create_default_execution_engine(max_workers=4)
    return _execution_engine


@router.post("/schedule", response_model=SchedulingPlanResponse)
async def schedule_tasks(request: SchedulingRequest) -> SchedulingPlanResponse:
    """Schedule a batch of tasks with dependency resolution.

    Analyzes task dependencies and conflicts to produce an optimal execution plan
    with maximum parallelization where safe.

    Args:
        request: SchedulingRequest with task list

    Returns:
        SchedulingPlanResponse with execution phases and conflict information

    Raises:
        HTTPException: If circular dependencies detected
    """
    try:
        # Convert request to internal Task objects
        tasks = [
            Task(
                id=t.id,
                description=t.description,
                target_symbols=t.target_symbols,
                dependency_symbols=t.dependency_symbols,
            )
            for t in request.tasks
        ]

        if not tasks:
            return SchedulingPlanResponse(
                total_tasks=0,
                num_phases=0,
                phases=[],
                parallelizable_pairs=0,
            )

        logger.info(f"Scheduling {len(tasks)} tasks")

        # Schedule tasks
        scheduler = get_scheduler()
        plan = scheduler.schedule(tasks)

        # Build response
        phases = [
            PhaseInfo(
                phase_number=i,
                task_ids=phase,
                can_parallel=True if len(phase) > 1 else True,
            )
            for i, phase in enumerate(plan.phases)
        ]

        return SchedulingPlanResponse(
            status="success",
            total_tasks=plan.total_tasks,
            num_phases=plan.num_phases(),
            phases=phases,
            parallelizable_pairs=plan.parallelizable_pairs,
        )

    except ValueError as e:
        if "Circular" in str(e):
            logger.error(f"Circular dependencies detected: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Circular task dependencies: {str(e)}",
            )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Scheduling error: {e}")
        raise HTTPException(status_code=500, detail=f"Scheduling failed: {str(e)}")


@router.post("/execute", response_model=ExecutionResponse)
async def execute_tasks(request: SchedulingRequest) -> ExecutionResponse:
    """Schedule and execute tasks in parallel.

    Combines scheduling with execution, respecting dependencies and conflicts.
    Executes tasks concurrently where safe.

    Args:
        request: SchedulingRequest with task list

    Returns:
        ExecutionResponse with execution results

    Raises:
        HTTPException: On scheduling or execution errors
    """
    try:
        # Convert request to internal Task objects
        tasks = [
            Task(
                id=t.id,
                description=t.description,
                target_symbols=t.target_symbols,
                dependency_symbols=t.dependency_symbols,
            )
            for t in request.tasks
        ]

        if not tasks:
            return ExecutionResponse(
                status="SUCCESS",
                completed_tasks=0,
                total_time_seconds=0.0,
            )

        logger.info(f"Scheduling and executing {len(tasks)} tasks")

        # Schedule
        scheduler = get_scheduler()
        plan = scheduler.schedule(tasks)

        # Execute
        engine = get_execution_engine()
        result = engine.execute_plan(plan, tasks, timeout=30.0)

        # Build response
        task_results = [
            TaskResult(
                task_id=r["task_id"],
                status=r.get("status", "unknown"),
                success=r.get("success", False),
                attempts=r.get("attempts", 1),
                total_time=r.get("total_time", 0.0),
                error=r.get("error"),
            )
            for r in result.results
        ]

        return ExecutionResponse(
            status=result.status,
            completed_tasks=result.completed_tasks,
            failed_tasks=len(result.failed_tasks),
            total_time_seconds=result.total_time_seconds,
            task_results=task_results,
        )

    except ValueError as e:
        if "Circular" in str(e):
            logger.error(f"Circular dependencies: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Execution error: {e}")
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check for scheduling service."""
    return {
        "status": "healthy",
        "service": "scheduling",
        "version": "1.0",
    }
