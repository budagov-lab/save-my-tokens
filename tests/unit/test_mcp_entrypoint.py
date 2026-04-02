"""Tests for MCP server entrypoint."""

from unittest.mock import MagicMock, patch


def test_entrypoint_main_structure():
    """Test that entrypoint module has main() function with expected structure."""
    # Import the entrypoint module
    from src.mcp_server import entrypoint

    # Verify main function exists
    assert hasattr(entrypoint, "main")
    assert callable(entrypoint.main)

    # Verify it's a regular function (not async)
    import inspect

    assert not inspect.iscoroutinefunction(entrypoint.main)


def test_entrypoint_main_calls_mcp_run():
    """Test that main() calls mcp.run() with stdio transport."""
    # Patch the mcp instance before importing entrypoint
    with patch("src.mcp_server._app.mcp") as mock_mcp:
        # Remove any cached import
        import sys

        if "src.mcp_server.entrypoint" in sys.modules:
            del sys.modules["src.mcp_server.entrypoint"]

        # Now import and call
        from src.mcp_server.entrypoint import main

        main()

        # Verify mcp.run was called with stdio transport
        mock_mcp.run.assert_called_once_with(transport="stdio")
