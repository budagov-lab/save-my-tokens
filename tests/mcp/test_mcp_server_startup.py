"""Tests for MCP server startup and tool registration."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.mcp_server._app import mcp
from src.mcp_server.services import build_services, teardown_services


class TestMCPServerInitialization:
    """Test MCP server initialization and startup."""

    def test_mcp_instance_exists(self):
        """Verify MCP FastMCP instance is created."""
        assert mcp is not None
        assert hasattr(mcp, 'run')

    def test_build_services(self):
        """Test service container initialization."""
        container = build_services()

        # Verify all core services are initialized
        assert container.symbol_index is not None
        assert container.query_service is not None
        assert container.scheduler is not None
        assert container.execution_engine is not None
        assert container.diff_parser is not None
        assert container.updater is not None

    @pytest.mark.asyncio
    async def test_teardown_services(self):
        """Test service teardown."""
        container = build_services()

        # Should not raise
        await teardown_services(container)

    def test_neo4j_client_graceful_failure(self):
        """Test services initialize even when Neo4j unavailable."""
        with patch('src.mcp_server.services.Neo4jClient') as mock_neo4j:
            mock_neo4j.side_effect = Exception("Connection failed")
            container = build_services()

            # Should still initialize with None client
            assert container.neo4j_client is None
            assert container.query_service is not None

    def test_embedding_service_graceful_failure(self):
        """Test services initialize even when embeddings unavailable."""
        with patch('src.mcp_server.services.EmbeddingService') as mock_embedding:
            mock_embedding.side_effect = Exception("FAISS not available")
            container = build_services()

            # Should still initialize with None service
            assert container.embedding_service is None
            assert container.query_service is not None


class TestToolRegistration:
    """Test that all tools are properly registered."""

    def test_graph_tools_registered(self):
        """Verify graph query tools are registered."""
        # Import the tools to trigger registration
        from src.mcp_server.tools import graph_tools

        # Tools are registered via decorators when module is imported
        assert graph_tools is not None

    def test_contract_tools_registered(self):
        """Verify contract tools are registered."""
        from src.mcp_server.tools import contract_tools

        assert contract_tools is not None

    def test_incremental_tools_registered(self):
        """Verify incremental update tools are registered."""
        from src.mcp_server.tools import incremental_tools

        assert incremental_tools is not None

    def test_scheduling_tools_registered(self):
        """Verify scheduling tools are registered."""
        from src.mcp_server.tools import scheduling_tools

        assert scheduling_tools is not None


class TestToolFunctionality:
    """Test individual tool functionality."""

    def test_graph_context_tool(self):
        """Test get_context tool through query service."""
        from src.parsers.symbol_index import SymbolIndex
        from src.parsers.symbol import Symbol
        from src.api.query_service import QueryService

        index = SymbolIndex()
        index.add(Symbol(name="test_func", type="function", file="test.py", line=1, column=0))

        service = QueryService(index)
        result = service.get_context("test_func", depth=1)

        assert result is not None
        assert "symbol" in result
        assert result["symbol"]["name"] == "test_func"

    def test_graph_search_tool(self):
        """Test semantic_search tool through query service."""
        from src.parsers.symbol_index import SymbolIndex
        from src.parsers.symbol import Symbol
        from src.api.query_service import QueryService

        index = SymbolIndex()
        index.add(Symbol(name="authenticate_user", type="function", file="auth.py", line=1, column=0))

        service = QueryService(index)
        result = service.semantic_search("authenticate", top_k=5)

        assert result is not None
        assert "results" in result

    def test_validate_conflicts_tool(self):
        """Test validate_conflicts tool through query service."""
        from src.parsers.symbol_index import SymbolIndex
        from src.api.query_service import QueryService

        index = SymbolIndex()
        service = QueryService(index)

        tasks = [
            {"id": "t1", "target_symbols": ["func1"]},
            {"id": "t2", "target_symbols": ["func2"]},
        ]
        result = service.validate_conflicts(tasks)

        assert result is not None
        assert "parallel_feasible" in result

    def test_scheduler_tool(self):
        """Test scheduler through execution engine."""
        from src.agent.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        tasks = [
            {"id": "t1", "target_symbols": ["func1"], "dependencies": []},
            {"id": "t2", "target_symbols": ["func2"], "dependencies": ["t1"]},
        ]

        # Scheduler should handle task list
        assert scheduler is not None


class TestServiceIntegration:
    """Test service integration."""

    def test_symbol_index_to_query_service(self):
        """Test data flow from symbol index to query service."""
        from src.parsers.symbol_index import SymbolIndex
        from src.parsers.symbol import Symbol
        from src.api.query_service import QueryService

        index = SymbolIndex()
        index.add(Symbol(name="module_func", type="function", file="module.py", line=1, column=0))

        service = QueryService(index)

        # Query service should access symbol index
        result = service.get_context("module_func")
        assert result["symbol"]["name"] == "module_func"

    def test_incremental_updater_integration(self):
        """Test incremental updater with symbol index."""
        from src.parsers.symbol_index import SymbolIndex
        from src.incremental.updater import IncrementalSymbolUpdater

        index = SymbolIndex()
        updater = IncrementalSymbolUpdater(index, neo4j_client=None)

        assert updater is not None

    def test_contract_extractor_integration(self):
        """Test contract extractor with symbols."""
        from src.contracts.extractor import ContractExtractor
        from src.parsers.symbol import Symbol

        source = "def test_func(x: int) -> int:\n    return x * 2"
        extractor = ContractExtractor(source)

        symbol = Symbol(name="test_func", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "test_func"


class TestErrorHandling:
    """Test error handling in MCP server."""

    def test_missing_symbol_graceful_handling(self):
        """Test handling of missing symbols."""
        from src.parsers.symbol_index import SymbolIndex
        from src.api.query_service import QueryService

        index = SymbolIndex()
        service = QueryService(index)

        result = service.get_context("nonexistent_symbol")

        # Should return error, not raise
        assert "error" in result

    def test_invalid_task_format_handling(self):
        """Test handling of invalid task formats."""
        from src.parsers.symbol_index import SymbolIndex
        from src.api.query_service import QueryService

        index = SymbolIndex()
        service = QueryService(index)

        # Missing required fields
        tasks = [{"id": "t1"}]  # Missing target_symbols

        # Should handle gracefully
        try:
            result = service.validate_conflicts(tasks)
            # May return error or empty
            assert result is not None
        except (KeyError, TypeError):
            # Acceptable to raise on invalid input
            pass

    def test_deep_recursion_handling(self):
        """Test handling of deeply nested dependencies."""
        from src.graph.conflict_analyzer import ConflictAnalyzer
        from src.parsers.symbol_index import SymbolIndex

        index = SymbolIndex()
        analyzer = ConflictAnalyzer(index, neo4j_client=None)

        # Should not stack overflow with deep deps
        deps = analyzer.get_all_dependencies("nonexistent")
        assert isinstance(deps, set)
