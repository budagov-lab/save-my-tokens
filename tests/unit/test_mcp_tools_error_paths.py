"""Comprehensive tests for MCP tools error paths."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.mcp_server.tools import graph_tools, contract_tools, scheduling_tools, incremental_tools


@pytest.fixture
def mock_context():
    """Create mock MCP context."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = MagicMock()
    return ctx


class TestGraphToolsErrorPaths:
    """Test graph tools error handling."""

    @pytest.mark.asyncio
    async def test_get_context_error_response(self, mock_context):
        """Test get_context with error from service."""
        mock_context.request_context.lifespan_context.query_service.get_context.return_value = {
            "error": "Symbol not found"
        }

        with pytest.raises(ValueError, match="Symbol not found"):
            await graph_tools.get_context("unknown", ctx=mock_context)

    @pytest.mark.asyncio
    async def test_get_context_success(self, mock_context):
        """Test get_context successful response."""
        mock_context.request_context.lifespan_context.query_service.get_context.return_value = {
            "symbol": "func_a",
            "dependencies": [],
            "callers": [],
            "token_estimate": 100,
        }

        result = await graph_tools.get_context("func_a", ctx=mock_context)

        assert result["symbol"] == "func_a"
        assert "token_estimate" in result

    @pytest.mark.asyncio
    async def test_get_context_with_depth(self, mock_context):
        """Test get_context with custom depth."""
        mock_context.request_context.lifespan_context.query_service.get_context.return_value = {
            "symbol": "func_a",
            "dependencies": [],
        }

        await graph_tools.get_context("func_a", depth=3, ctx=mock_context)

        mock_context.request_context.lifespan_context.query_service.get_context.assert_called_once_with(
            "func_a", depth=3, include_callers=False
        )

    @pytest.mark.asyncio
    async def test_get_context_with_callers(self, mock_context):
        """Test get_context with include_callers."""
        mock_context.request_context.lifespan_context.query_service.get_context.return_value = {
            "symbol": "func_a",
            "callers": ["func_b"],
        }

        await graph_tools.get_context("func_a", include_callers=True, ctx=mock_context)

        mock_context.request_context.lifespan_context.query_service.get_context.assert_called_once_with(
            "func_a", depth=1, include_callers=True
        )

    @pytest.mark.asyncio
    async def test_get_subgraph_error(self, mock_context):
        """Test get_subgraph with error."""
        mock_context.request_context.lifespan_context.query_service.get_subgraph.return_value = {
            "error": "Symbol not found"
        }

        with pytest.raises(ValueError, match="Symbol not found"):
            await graph_tools.get_subgraph("unknown", ctx=mock_context)

    @pytest.mark.asyncio
    async def test_get_subgraph_success(self, mock_context):
        """Test get_subgraph successful response."""
        mock_context.request_context.lifespan_context.query_service.get_subgraph.return_value = {
            "root_symbol": "func_a",
            "nodes": [],
            "edges": [],
            "depth": 2,
        }

        result = await graph_tools.get_subgraph("func_a", ctx=mock_context)

        assert result["root_symbol"] == "func_a"
        assert result["depth"] == 2

    @pytest.mark.asyncio
    async def test_get_subgraph_with_depth(self, mock_context):
        """Test get_subgraph with custom depth."""
        mock_context.request_context.lifespan_context.query_service.get_subgraph.return_value = {
            "root_symbol": "func_a",
            "nodes": [],
            "edges": [],
        }

        await graph_tools.get_subgraph("func_a", depth=4, ctx=mock_context)

        mock_context.request_context.lifespan_context.query_service.get_subgraph.assert_called_once_with(
            "func_a", depth=4
        )

    @pytest.mark.asyncio
    async def test_semantic_search_success(self, mock_context):
        """Test semantic_search successful response."""
        mock_context.request_context.lifespan_context.query_service.semantic_search.return_value = {
            "query": "validation",
            "results": [
                {"symbol_name": "validate", "similarity_score": 0.95}
            ],
            "top_k": 5,
        }

        result = await graph_tools.semantic_search("validation", ctx=mock_context)

        assert result["query"] == "validation"
        assert len(result["results"]) > 0

    @pytest.mark.asyncio
    async def test_semantic_search_with_top_k(self, mock_context):
        """Test semantic_search with custom top_k."""
        mock_context.request_context.lifespan_context.query_service.semantic_search.return_value = {
            "query": "test",
            "results": [],
            "top_k": 10,
        }

        await graph_tools.semantic_search("test", top_k=10, ctx=mock_context)

        mock_context.request_context.lifespan_context.query_service.semantic_search.assert_called_once_with(
            "test", top_k=10
        )

    @pytest.mark.asyncio
    async def test_validate_conflicts_success(self, mock_context):
        """Test validate_conflicts successful response."""
        mock_context.request_context.lifespan_context.query_service.validate_conflicts.return_value = {
            "parallel_feasible": True,
            "direct_conflicts": [],
            "recommendation": "Can execute in parallel",
        }

        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_b"]},
        ]

        result = await graph_tools.validate_conflicts(tasks, ctx=mock_context)

        assert result["parallel_feasible"] is True
        assert "recommendation" in result

    @pytest.mark.asyncio
    async def test_validate_conflicts_with_conflicts(self, mock_context):
        """Test validate_conflicts with conflicts detected."""
        mock_context.request_context.lifespan_context.query_service.validate_conflicts.return_value = {
            "parallel_feasible": False,
            "direct_conflicts": [{"task_a": "t1", "task_b": "t2", "symbol": "func_a"}],
            "recommendation": "Run sequentially",
        }

        tasks = [
            {"id": "t1", "target_symbols": ["func_a"]},
            {"id": "t2", "target_symbols": ["func_a"]},
        ]

        result = await graph_tools.validate_conflicts(tasks, ctx=mock_context)

        assert result["parallel_feasible"] is False
        assert len(result["direct_conflicts"]) > 0


class TestContractToolsErrorPaths:
    """Test contract tools error handling."""

    @pytest.mark.asyncio
    async def test_extract_contract_success(self, mock_context):
        """Test extract_contract successful response."""
        source = "def func_a(): pass"

        with patch('src.mcp_server.tools.contract_tools.ContractExtractor') as mock_extractor:
            mock_contract = MagicMock()
            mock_contract.symbol.name = "func_a"
            mock_extractor.return_value.extract_function_contract.return_value = mock_contract

            result = await contract_tools.extract_contract("func_a", "test.py", source, ctx=mock_context)

            assert result["symbol_name"] == "func_a"

    @pytest.mark.asyncio
    async def test_extract_contract_not_found(self, mock_context):
        """Test extract_contract when symbol not found."""
        source = "def other_func(): pass"

        with patch('src.mcp_server.tools.contract_tools.ContractExtractor') as mock_extractor:
            mock_extractor.return_value.extract_function_contract.return_value = None

            with pytest.raises(ValueError, match="not found"):
                await contract_tools.extract_contract("func_a", "test.py", source, ctx=mock_context)

    @pytest.mark.asyncio
    async def test_compare_contracts_success(self, mock_context):
        """Test compare_contracts successful response."""
        old_source = "def func_a(): pass"
        new_source = "def func_a(): pass"

        with patch('src.mcp_server.tools.contract_tools.ContractExtractor') as mock_extractor:
            with patch('src.mcp_server.tools.contract_tools.BreakingChangeDetector') as mock_detector:
                mock_contract = MagicMock()
                mock_contract.symbol.name = "func_a"
                mock_extractor.return_value.extract_function_contract.return_value = mock_contract

                mock_comparison = MagicMock()
                mock_comparison.old_contract = mock_contract
                mock_comparison.is_compatible = True
                mock_comparison.compatibility_score = 1.0
                mock_comparison.breaking_changes = []
                mock_comparison.non_breaking_changes = []
                mock_detector.return_value.detect_breaking_changes.return_value = mock_comparison

                result = await contract_tools.compare_contracts("func_a", old_source, new_source, ctx=mock_context)

                assert result["is_compatible"] is True

    @pytest.mark.asyncio
    async def test_compare_contracts_with_changes(self, mock_context):
        """Test compare_contracts with breaking changes."""
        old_source = "def func_a(x): pass"
        new_source = "def func_a(): pass"

        with patch('src.mcp_server.tools.contract_tools.ContractExtractor') as mock_extractor:
            with patch('src.mcp_server.tools.contract_tools.BreakingChangeDetector') as mock_detector:
                mock_contract = MagicMock()
                mock_contract.symbol.name = "func_a"
                mock_extractor.return_value.extract_function_contract.return_value = mock_contract

                mock_change = MagicMock()
                mock_change.type = "parameter_removed"
                mock_change.severity = "high"
                mock_change.impact = "Breaking change"
                mock_change.affected_elements = {"x"}
                mock_change.old_value = "x"
                mock_change.new_value = None

                mock_comparison = MagicMock()
                mock_comparison.old_contract = mock_contract
                mock_comparison.is_compatible = False
                mock_comparison.compatibility_score = 0.5
                mock_comparison.breaking_changes = [mock_change]
                mock_comparison.non_breaking_changes = []
                mock_detector.return_value.detect_breaking_changes.return_value = mock_comparison

                result = await contract_tools.compare_contracts("func_a", old_source, new_source, ctx=mock_context)

                assert result["is_compatible"] is False
                assert len(result["breaking_changes"]) > 0


class TestSchedulingToolsErrorPaths:
    """Test scheduling tools error handling."""

    @pytest.mark.asyncio
    async def test_schedule_tasks_success(self, mock_context):
        """Test schedule_tasks successful response."""
        mock_plan = MagicMock()
        mock_plan.total_tasks = 3
        mock_plan.num_phases.return_value = 2
        mock_plan.phases = [["task_1"], ["task_2", "task_3"]]
        mock_plan.parallelizable_pairs = []

        mock_context.request_context.lifespan_context.scheduler.schedule.return_value = mock_plan

        tasks = [
            {"id": "task_1", "description": "Task 1", "target_symbols": [], "dependency_symbols": []},
            {"id": "task_2", "description": "Task 2", "target_symbols": [], "dependency_symbols": ["task_1"]},
            {"id": "task_3", "description": "Task 3", "target_symbols": [], "dependency_symbols": ["task_1"]},
        ]

        result = await scheduling_tools.schedule_tasks(tasks, ctx=mock_context)

        assert result["total_tasks"] == 3
        assert result["num_phases"] == 2

    @pytest.mark.asyncio
    async def test_schedule_tasks_invalid_dict(self, mock_context):
        """Test schedule_tasks with invalid task dict."""
        tasks = [
            {"invalid_key": "value"},  # Missing required fields
        ]

        with pytest.raises(ValueError, match="Invalid task dict"):
            await scheduling_tools.schedule_tasks(tasks, ctx=mock_context)

    @pytest.mark.asyncio
    async def test_execute_tasks_success(self, mock_context):
        """Test execute_tasks successful response."""
        mock_plan = MagicMock()
        mock_plan.total_tasks = 1
        mock_plan.num_phases.return_value = 1
        mock_plan.phases = [["task_1"]]
        mock_plan.parallelizable_pairs = []

        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.completed_tasks = 1
        mock_result.failed_tasks = []
        mock_result.total_time_seconds = 0.1
        mock_result.results = [{"task_id": "task_1", "status": "success"}]

        mock_context.request_context.lifespan_context.scheduler.schedule.return_value = mock_plan
        mock_context.request_context.lifespan_context.execution_engine.execute_plan.return_value = mock_result

        tasks = [
            {"id": "task_1", "description": "Task 1", "target_symbols": [], "dependency_symbols": []},
        ]

        result = await scheduling_tools.execute_tasks(tasks, ctx=mock_context)

        assert result["status"] == "SUCCESS"
        assert result["completed_tasks"] == 1


class TestIncrementalToolsErrorPaths:
    """Test incremental tools error handling."""

    @pytest.mark.asyncio
    async def test_parse_diff_success(self, mock_context):
        """Test parse_diff successful response."""
        mock_summary = MagicMock()
        mock_summary.total_files_changed = 1
        mock_summary.total_lines_added = 5
        mock_summary.total_lines_deleted = 2
        mock_file = MagicMock()
        mock_file.file_path = "test.py"
        mock_file.status = "M"
        mock_file.added_lines = 5
        mock_file.deleted_lines = 2
        mock_summary.files = [mock_file]

        mock_context.request_context.lifespan_context.diff_parser.parse_diff.return_value = mock_summary

        result = await incremental_tools.parse_diff(
            "--- a/test.py\n+++ b/test.py",
            ctx=mock_context
        )

        assert result["total_files_changed"] == 1

    @pytest.mark.asyncio
    async def test_apply_diff_success(self, mock_context):
        """Test apply_diff successful response."""
        mock_context.request_context.lifespan_context.neo4j_client = MagicMock()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.duration_ms = 10
        mock_context.request_context.lifespan_context.updater.apply_delta.return_value = mock_result

        result = await incremental_tools.apply_diff(
            "test.py",
            added_symbols=[{"name": "func_a", "type": "function", "file": "test.py", "line": 1, "column": 0}],
            ctx=mock_context
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_apply_diff_no_neo4j(self, mock_context):
        """Test apply_diff without Neo4j connection."""
        mock_context.request_context.lifespan_context.neo4j_client = None

        with pytest.raises(RuntimeError, match="requires a live Neo4j"):
            await incremental_tools.apply_diff("test.py", ctx=mock_context)

    @pytest.mark.asyncio
    async def test_apply_diff_invalid_symbol(self, mock_context):
        """Test apply_diff with invalid symbol dict."""
        mock_context.request_context.lifespan_context.neo4j_client = MagicMock()

        with pytest.raises(ValueError, match="Invalid symbol dict"):
            await incremental_tools.apply_diff(
                "test.py",
                added_symbols=[{"invalid_key": "value"}],
                ctx=mock_context
            )


class TestToolErrorHandling:
    """Test common error handling patterns."""

    @pytest.mark.asyncio
    async def test_missing_context_injection(self):
        """Test tools require context injection."""
        with pytest.raises((AttributeError, TypeError)):
            # Call without context should fail
            await graph_tools.get_context("func_a", ctx=None)

    @pytest.mark.asyncio
    async def test_context_with_empty_string(self, mock_context):
        """Test tools handle empty string inputs."""
        mock_context.request_context.lifespan_context.query_service.semantic_search.return_value = {
            "query": "",
            "results": [],
        }

        result = await graph_tools.semantic_search("", ctx=mock_context)

        assert result["query"] == ""

    @pytest.mark.asyncio
    async def test_context_with_special_characters(self, mock_context):
        """Test tools handle special characters."""
        mock_context.request_context.lifespan_context.query_service.get_context.return_value = {
            "symbol": "_private_func",
            "dependencies": [],
        }

        result = await graph_tools.get_context("_private_func", ctx=mock_context)

        assert result["symbol"] == "_private_func"
