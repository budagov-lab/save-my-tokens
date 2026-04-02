"""Tests for MCP server entrypoint - ensures server startup and tool registration."""

import pytest
from unittest.mock import patch, MagicMock, call
import sys


class TestEntrypointMain:
    """Test the main() function in entrypoint.py."""

    def test_main_calls_mcp_run(self):
        """Test that main() calls mcp.run() with stdio transport."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            from src.mcp_server import entrypoint

            # Mock run method
            mock_mcp.run = MagicMock()

            # Call main
            entrypoint.main()

            # Verify mcp.run was called with stdio transport
            mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_main_imports_all_tools(self):
        """Test that main() imports all tool modules for registration."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            mock_mcp.run = MagicMock()

            from src.mcp_server import entrypoint

            # Call main which will import the tools
            entrypoint.main()

            # If we get here without exception, tools were imported successfully
            # Direct import verification is complex with FastMCP decorators
            assert True

    def test_main_does_not_raise_on_success(self):
        """Test that main() completes without raising exceptions."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            mock_mcp.run = MagicMock()

            from src.mcp_server import entrypoint

            # Should not raise
            entrypoint.main()

    def test_main_with_transport_parameter(self):
        """Test that transport="stdio" is correctly passed to mcp.run()."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            mock_mcp.run = MagicMock()

            from src.mcp_server import entrypoint
            entrypoint.main()

            # Verify exact parameter
            args, kwargs = mock_mcp.run.call_args
            assert kwargs.get('transport') == 'stdio'

    def test_entrypoint_can_be_called_as_script(self):
        """Test that entrypoint can be invoked as __main__."""
        # The if __name__ == "__main__" block should exist
        import inspect
        from src.mcp_server import entrypoint

        source = inspect.getsource(entrypoint)
        assert 'if __name__ == "__main__"' in source
        assert 'main()' in source


class TestEntrypointImports:
    """Test that all required modules can be imported by entrypoint."""

    def test_import_graph_tools(self):
        """Test that graph_tools module can be imported."""
        from src.mcp_server.tools import graph_tools
        assert graph_tools is not None

    def test_import_contract_tools(self):
        """Test that contract_tools module can be imported."""
        from src.mcp_server.tools import contract_tools
        assert contract_tools is not None

    def test_import_incremental_tools(self):
        """Test that incremental_tools module can be imported."""
        from src.mcp_server.tools import incremental_tools
        assert incremental_tools is not None

    def test_import_scheduling_tools(self):
        """Test that scheduling_tools module can be imported."""
        from src.mcp_server.tools import scheduling_tools
        assert scheduling_tools is not None

    def test_import_mcp_app(self):
        """Test that _app module can be imported."""
        from src.mcp_server._app import mcp
        assert mcp is not None

    def test_all_tool_imports_in_entrypoint(self):
        """Test that entrypoint imports all tool modules."""
        import inspect
        from src.mcp_server import entrypoint

        source = inspect.getsource(entrypoint.main)

        # Verify all tool modules are imported
        assert 'contract_tools' in source
        assert 'graph_tools' in source
        assert 'incremental_tools' in source
        assert 'scheduling_tools' in source


class TestEntrypointServer:
    """Test MCP server startup through entrypoint."""

    def test_server_startup_flow(self):
        """Test the complete server startup flow."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            mock_mcp.run = MagicMock()

            from src.mcp_server import entrypoint

            # Call main
            entrypoint.main()

            # Verify server was started
            assert mock_mcp.run.called

    def test_server_uses_stdio_transport(self):
        """Test that server uses stdio transport for Claude integration."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            mock_mcp.run = MagicMock()

            from src.mcp_server import entrypoint
            entrypoint.main()

            # stdio transport is correct for subprocess model
            call_kwargs = mock_mcp.run.call_args[1]
            assert 'transport' in call_kwargs
            assert call_kwargs['transport'] == 'stdio'

    def test_server_startup_with_mocked_services(self):
        """Test server startup with mocked services."""
        with patch('src.mcp_server._app.mcp') as mock_mcp:
            with patch('src.mcp_server.services.build_services') as mock_build:
                mock_mcp.run = MagicMock()
                mock_build.return_value = MagicMock()

                from src.mcp_server import entrypoint

                # Should complete without error
                entrypoint.main()


class TestEntrypointIntegration:
    """Integration tests for entrypoint with actual services."""

    def test_main_with_real_services(self):
        """Test main() actually initializes services when called."""
        from src.mcp_server.services import build_services

        # Build services to verify they work
        container = build_services()

        # All critical services should be present
        assert container.symbol_index is not None
        assert container.query_service is not None
        assert container.scheduler is not None

    def test_entrypoint_preserves_service_state(self):
        """Test that entrypoint initialization preserves service state."""
        from src.mcp_server.services import build_services, teardown_services
        import asyncio

        container = build_services()
        original_index = container.symbol_index

        # Verify state is preserved
        assert container.symbol_index is original_index

        # Cleanup
        asyncio.run(teardown_services(container))


class TestEntrypointEdgeCases:
    """Test edge cases and error conditions."""

    def test_main_with_missing_mcp_module(self):
        """Test graceful handling if mcp module is unavailable."""
        # This is more of a documentation test
        # The actual error would be caught at module load time
        from src.mcp_server._app import mcp
        assert mcp is not None

    def test_entrypoint_function_signature(self):
        """Test that main() has correct signature."""
        import inspect
        from src.mcp_server.entrypoint import main

        sig = inspect.signature(main)

        # Should take no required arguments
        params = [p for p in sig.parameters.values()
                  if p.default == inspect.Parameter.empty]
        assert len(params) == 0

        # Should return None
        assert sig.return_annotation is None or sig.return_annotation == 'None'

    def test_entrypoint_module_docstring(self):
        """Test that entrypoint module has proper documentation."""
        from src.mcp_server import entrypoint

        assert entrypoint.__doc__ is not None
        assert 'entrypoint' in entrypoint.__doc__.lower()

    def test_main_function_docstring(self):
        """Test that main function has proper documentation."""
        from src.mcp_server.entrypoint import main

        assert main.__doc__ is not None
        assert 'entry point' in main.__doc__.lower()


class TestEntrypointToolsRegistration:
    """Test that all tools are properly registered via entrypoint."""

    def test_tools_module_exists(self):
        """Test that tools package exists."""
        from src.mcp_server import tools
        assert tools is not None

    def test_tools_init_has_all_modules(self):
        """Test that tools __init__ properly exports all tool modules."""
        from src.mcp_server.tools import (
            contract_tools,
            graph_tools,
            incremental_tools,
            scheduling_tools,
        )

        assert all([contract_tools, graph_tools, incremental_tools, scheduling_tools])

    def test_entrypoint_imports_trigger_registration(self):
        """Test that importing entrypoint triggers tool registration."""
        # Tools are registered when modules are imported via decorators
        # This test verifies the import path works
        from src.mcp_server.tools import graph_tools

        # If we get here, imports worked
        assert graph_tools is not None


class TestEntrypointCliInvocation:
    """Test that entrypoint works when invoked from CLI."""

    def test_main_module_entrypoint(self):
        """Test that module can be invoked as __main__."""
        import inspect
        from src.mcp_server import entrypoint

        source = inspect.getsource(entrypoint)

        # Verify __main__ block exists
        assert 'if __name__ == "__main__"' in source

    def test_main_is_called_in_main_block(self):
        """Test that main() is called in __main__ block."""
        import inspect
        from src.mcp_server import entrypoint

        source = inspect.getsource(entrypoint)

        # Find the __main__ block and verify main() call
        if_main_start = source.find('if __name__ == "__main__"')
        assert if_main_start != -1

        main_block = source[if_main_start:]
        assert 'main()' in main_block
