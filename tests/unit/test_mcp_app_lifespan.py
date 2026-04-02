"""Tests for MCP app lifespan management."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.mcp_server._app import lifespan


@pytest.mark.asyncio
async def test_lifespan_builds_services():
    """Test lifespan builds services on startup."""
    mock_app = MagicMock()
    mock_container = MagicMock()

    with patch('src.mcp_server._app.build_services', return_value=mock_container):
        with patch('src.mcp_server._app.teardown_services', new_callable=AsyncMock):
            async with lifespan(mock_app) as container:
                assert container is mock_container


@pytest.mark.asyncio
async def test_lifespan_teardown_on_success():
    """Test lifespan tears down services on normal exit."""
    mock_app = MagicMock()
    mock_container = MagicMock()
    mock_teardown = AsyncMock()

    with patch('src.mcp_server._app.build_services', return_value=mock_container):
        with patch('src.mcp_server._app.teardown_services', mock_teardown):
            async with lifespan(mock_app) as container:
                assert container is mock_container

            # Verify teardown was called
            mock_teardown.assert_called_once_with(mock_container)


@pytest.mark.asyncio
async def test_lifespan_teardown_on_exception():
    """Test lifespan tears down services even on exception."""
    mock_app = MagicMock()
    mock_container = MagicMock()
    mock_teardown = AsyncMock()

    with patch('src.mcp_server._app.build_services', return_value=mock_container):
        with patch('src.mcp_server._app.teardown_services', mock_teardown):
            try:
                async with lifespan(mock_app) as container:
                    assert container is mock_container
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Verify teardown was still called
            mock_teardown.assert_called_once_with(mock_container)


@pytest.mark.asyncio
async def test_lifespan_yields_container():
    """Test lifespan yields the container."""
    mock_app = MagicMock()
    mock_container = MagicMock()

    with patch('src.mcp_server._app.build_services', return_value=mock_container):
        with patch('src.mcp_server._app.teardown_services', new_callable=AsyncMock):
            async with lifespan(mock_app) as container:
                assert container is not None
                assert container is mock_container


class TestMCPInstance:
    """Test MCP instance creation."""

    def test_mcp_instance_exists(self):
        """Test MCP instance is created."""
        from src.mcp_server._app import mcp

        assert mcp is not None

    def test_mcp_has_name(self):
        """Test MCP instance has correct name."""
        from src.mcp_server._app import mcp

        assert mcp.name == "smt-graph"

    def test_mcp_is_fastmcp_instance(self):
        """Test MCP instance is FastMCP type."""
        from src.mcp_server._app import mcp
        from mcp.server.fastmcp import FastMCP

        assert isinstance(mcp, FastMCP)
