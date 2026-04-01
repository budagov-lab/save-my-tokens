"""MCP application factory - FastMCP instance with lifespan management."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from src.mcp_server.services import ServiceContainer, build_services, teardown_services


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[ServiceContainer]:
    """
    Lifespan context manager for MCP server.

    Builds all singletons at startup and tears them down at shutdown.
    The yielded ServiceContainer is made available to all tools via
    ctx.request_context.lifespan_context.

    Args:
        app: FastMCP instance (passed by framework).

    Yields:
        ServiceContainer with all initialized services.
    """
    container = build_services()
    try:
        yield container
    finally:
        await teardown_services(container)


# FastMCP instance - tools will be registered on this instance
mcp = FastMCP(name="syt-graph", lifespan=lifespan)
