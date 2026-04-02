"""MCP tools for graph queries - get_context, get_subgraph, semantic_search, validate_conflicts."""

from mcp.server.fastmcp import Context

from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer


@mcp.tool()
async def get_context(
    symbol: str,
    depth: int = 1,
    include_callers: bool = False,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Get minimal context for a symbol: its definition, direct dependencies,
    and optionally its callers. Returns only what the agent needs, minimizing
    token usage.

    Args:
        symbol: Symbol name to get context for.
        depth: How many levels of dependencies to include.
        include_callers: Whether to include functions that call this symbol.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: symbol, dependencies, callers (or null), token_estimate.

    Raises:
        ValueError: If symbol not found.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context
    result = services.query_service.get_context(
        symbol, depth=depth, include_callers=include_callers
    )
    if "error" in result:
        raise ValueError(result["error"])
    return result


@mcp.tool()
async def get_subgraph(
    symbol: str,
    depth: int = 2,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Get the full dependency subgraph rooted at a symbol, up to `depth` hops.
    Returns nodes (symbols) and edges (dependency relationships).

    Args:
        symbol: Root symbol name.
        depth: Maximum depth for the subgraph.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: root_symbol, nodes, edges, depth, token_estimate.

    Raises:
        ValueError: If symbol not found.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context
    result = services.query_service.get_subgraph(symbol, depth=depth)
    if "error" in result:
        raise ValueError(result["error"])
    return result


@mcp.tool()
async def semantic_search(
    query: str,
    top_k: int = 5,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Search the symbol index for symbols semantically matching the query.
    Uses embedding similarity when available; falls back to substring matching.

    Args:
        query: Natural language or code-based search query.
        top_k: Number of top results to return.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: query, results (list), top_k.
        Results contain: symbol_name, symbol_type, file, line, node_id, similarity_score.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context
    return services.query_service.semantic_search(query, top_k=top_k)


@mcp.tool()
async def validate_conflicts(
    tasks: list,  # type: ignore[type-arg]
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Detect conflicts between a set of parallel tasks before execution.
    Each task dict must have keys: "id" (str) and "target_symbols" (list[str]).

    Args:
        tasks: List of task dicts with at least {id, target_symbols}.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: tasks, direct_conflicts, dependency_conflicts,
        circular_dependencies, parallel_feasible, recommendation.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context
    return services.query_service.validate_conflicts(tasks)
