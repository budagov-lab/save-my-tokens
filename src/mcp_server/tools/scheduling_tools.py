"""MCP tools for task scheduling and execution."""

from mcp.server.fastmcp import Context

from src.agent.scheduler import Task
from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer


@mcp.tool()
async def schedule_tasks(
    tasks: list = None,  # type: ignore[type-arg]
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Build an optimal execution plan for a set of tasks, grouping
    non-conflicting tasks into parallel phases.

    Each task dict must have: id (str), description (str),
    target_symbols (list[str]), dependency_symbols (list[str]).

    Args:
        tasks: List of task dicts.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: total_tasks, num_phases, phases
        (list of {phase_number, task_ids, can_parallel}), parallelizable_pairs.

    Raises:
        ValueError: On circular dependencies.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context

    tasks = tasks or []

    # Filter task dicts to known keys
    valid_keys = {"id", "description", "target_symbols", "dependency_symbols"}
    try:
        task_objs = [Task(**{k: v for k, v in t.items() if k in valid_keys}) for t in tasks]
    except (TypeError, KeyError) as e:
        raise ValueError(f"Invalid task dict: {e}")

    plan = services.scheduler.schedule(task_objs)

    return {
        "total_tasks": plan.total_tasks,
        "num_phases": plan.num_phases(),
        "phases": [
            {
                "phase_number": i,
                "task_ids": phase,
                "can_parallel": len(phase) > 1,
            }
            for i, phase in enumerate(plan.phases)
        ],
        "parallelizable_pairs": plan.parallelizable_pairs,
    }


@mcp.tool()
async def execute_tasks(
    tasks: list = None,  # type: ignore[type-arg]
    timeout_seconds: float = 30.0,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Schedule and execute a set of tasks, respecting dependencies and
    running conflict-free tasks in parallel.

    Same task dict shape as schedule_tasks.

    Args:
        tasks: List of task dicts.
        timeout_seconds: Timeout per task.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: status ("SUCCESS"/"PARTIAL"/"FAILED"),
        completed_tasks, failed_tasks (count), total_time_seconds,
        task_results (list of {task_id, status, success, attempts, total_time, error}).
    """
    services: ServiceContainer = ctx.request_context.lifespan_context

    tasks = tasks or []

    # Filter task dicts to known keys
    valid_keys = {"id", "description", "target_symbols", "dependency_symbols"}
    try:
        task_objs = [Task(**{k: v for k, v in t.items() if k in valid_keys}) for t in tasks]
    except (TypeError, KeyError) as e:
        raise ValueError(f"Invalid task dict: {e}")

    # Schedule
    plan = services.scheduler.schedule(task_objs)

    # Execute
    result = services.execution_engine.execute_plan(plan, task_objs, timeout=timeout_seconds)

    return {
        "status": result.status,
        "completed_tasks": result.completed_tasks,
        "failed_tasks": len(result.failed_tasks),
        "total_time_seconds": result.total_time_seconds,
        "task_results": result.results,
    }
