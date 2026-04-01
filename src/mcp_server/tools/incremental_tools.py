"""MCP tools for incremental updates - parse_diff, apply_diff."""

from mcp.server.fastmcp import Context

from src.incremental.symbol_delta import SymbolDelta
from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer
from src.parsers.symbol import Symbol


@mcp.tool()
async def parse_diff(
    diff_text: str,
    ctx: Context = None,  # type: ignore
) -> dict:
    """
    Parse a raw git diff and return a summary of which files changed and how.

    Args:
        diff_text: Raw git diff output.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: total_files_changed, total_lines_added,
        total_lines_deleted, files (list of {file_path, status, added_lines, deleted_lines}).
    """
    services: ServiceContainer = ctx.request_context.lifespan_context
    summary = services.diff_parser.parse_diff(diff_text)

    return {
        "total_files_changed": summary.total_files_changed,
        "total_lines_added": summary.total_lines_added,
        "total_lines_deleted": summary.total_lines_deleted,
        "files": [
            {
                "file_path": f.file_path,
                "status": f.status,
                "added_lines": f.added_lines,
                "deleted_lines": f.deleted_lines,
            }
            for f in summary.files
        ],
    }


@mcp.tool()
async def apply_diff(
    file: str,
    added_symbols: list = None,  # type: ignore
    deleted_symbol_names: list = None,  # type: ignore
    modified_symbols: list = None,  # type: ignore
    ctx: Context = None,  # type: ignore
) -> dict:
    """
    Apply a symbol delta to the in-memory index and Neo4j graph.
    Used after parsing changed files to keep the graph in sync.

    Each symbol dict in added_symbols/modified_symbols must have:
    name, type, file, line, column, and optionally parent.

    Args:
        file: File path that changed.
        added_symbols: List of symbol dicts representing new symbols.
        deleted_symbol_names: List of symbol names that were deleted.
        modified_symbols: List of symbol dicts with modified definitions.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: success, file, duration_ms, added, deleted, modified.

    Raises:
        ValueError: On conflict or invalid input.
        RuntimeError: On partial failure with rollback.
    """
    services: ServiceContainer = ctx.request_context.lifespan_context

    # Guard: apply_diff requires Neo4j
    if services.neo4j_client is None:
        raise RuntimeError(
            "apply_diff requires a live Neo4j connection. "
            "Start Neo4j and restart the MCP server."
        )

    # Safe defaults
    added_symbols = added_symbols or []
    deleted_symbol_names = deleted_symbol_names or []
    modified_symbols = modified_symbols or []

    # Construct Symbol objects - filter to known keys
    valid_keys = {"name", "type", "file", "line", "column", "parent", "docstring"}
    try:
        added = [
            Symbol(**{k: v for k, v in s.items() if k in valid_keys})
            for s in added_symbols
        ]
        modified = [
            Symbol(**{k: v for k, v in s.items() if k in valid_keys})
            for s in modified_symbols
        ]
    except (TypeError, KeyError) as e:
        raise ValueError(f"Invalid symbol dict: {e}")

    delta = SymbolDelta(
        file=file,
        added=added,
        deleted=deleted_symbol_names,
        modified=modified,
    )

    result = services.updater.apply_delta(delta)

    if not result.success:
        raise RuntimeError(f"Failed to apply delta: {result.error}")

    return {
        "success": True,
        "file": file,
        "duration_ms": result.duration_ms,
        "added": len(added),
        "deleted": len(deleted_symbol_names),
        "modified": len(modified),
    }
