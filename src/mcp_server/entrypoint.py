"""MCP server entrypoint - imports FastMCP and all tools."""


def main() -> None:
    """Entry point for the MCP server."""
    # Import tools to register them on the mcp instance
    # Deferred import to avoid shadowing the mcp package
    from src.mcp_server.tools import (  # noqa: F401
        contract_tools,
        graph_tools,
        incremental_tools,
        scheduling_tools,
    )
    from src.mcp_server._app import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
