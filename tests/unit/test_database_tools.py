"""Unit tests for Neo4j database management tools (Phase 1 & 2)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.mcp_server.tools import database_tools


class TestGraphInit:
    """Test graph_init tool."""

    @pytest.mark.asyncio
    async def test_graph_init_success(self):
        """Test successful graph initialization."""
        # Mock context and services
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.get_stats.return_value = {"node_count": 0, "edge_count": 0}
        mock_neo4j.create_indexes.return_value = None

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Call tool
        result = await database_tools.graph_init(ctx=mock_ctx)

        # Verify
        assert result["status"] == "success"
        assert "Graph initialized" in result["message"]
        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        assert "node_id_idx" in result["indexes_created"]
        mock_neo4j.create_indexes.assert_called_once()

    @pytest.mark.asyncio
    async def test_graph_init_connection_error(self):
        """Test graph_init when Neo4j is unavailable."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.create_indexes.side_effect = ConnectionError("Connection refused")

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        result = await database_tools.graph_init(ctx=mock_ctx)

        assert result["status"] == "error"
        assert "initialization failed" in result["error"]


class TestGraphRebuild:
    """Test graph_rebuild tool."""

    @pytest.mark.asyncio
    async def test_graph_rebuild_success(self):
        """Test successful graph rebuild."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.clear_database.return_value = None
        mock_neo4j.get_stats.return_value = {"node_count": 100, "edge_count": 250}

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Mock GraphBuilder
        with patch("src.mcp_server.tools.database_tools.GraphBuilder") as mock_builder_class:
            mock_builder = Mock()
            mock_builder.build.return_value = None
            mock_builder.symbol_index.get_all.return_value = [
                Mock() for _ in range(100)
            ]  # 100 symbols
            mock_builder_class.return_value = mock_builder

            # Mock Path to allow temp directory
            with patch("src.mcp_server.tools.database_tools.Path") as mock_path:
                mock_path_obj = Mock()
                mock_path_obj.exists.return_value = True
                mock_path_obj.absolute.return_value = "/src"
                mock_path.return_value = mock_path_obj

                result = await database_tools.graph_rebuild(project_dir="./src", ctx=mock_ctx)

        assert result["status"] == "success"
        assert "Graph rebuilt" in result["message"]
        assert result["nodes_created"] == 100
        assert result["edges_created"] == 250
        assert result["symbols_extracted"] == 100
        assert result["token_estimate_total"] == 100 * 125

    @pytest.mark.asyncio
    async def test_graph_rebuild_invalid_directory(self):
        """Test graph_rebuild with non-existent directory."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        with patch("src.mcp_server.tools.database_tools.Path") as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path_obj.absolute.return_value = "/invalid/path"
            mock_path.return_value = mock_path_obj

            result = await database_tools.graph_rebuild(project_dir="/invalid/path", ctx=mock_ctx)

        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestGraphStats:
    """Test graph_stats tool."""

    @pytest.mark.asyncio
    async def test_graph_stats_success(self):
        """Test successful stats retrieval."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.get_stats.return_value = {"node_count": 1248, "edge_count": 3847}
        mock_neo4j.driver.session.return_value.__enter__ = Mock()
        mock_neo4j.driver.session.return_value.__exit__ = Mock()

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        with patch(
            "src.mcp_server.tools.database_tools._get_node_type_breakdown"
        ) as mock_node_breakdown:
            mock_node_breakdown.return_value = {"File": 42, "Function": 856}

            with patch(
                "src.mcp_server.tools.database_tools._get_edge_type_breakdown"
            ) as mock_edge_breakdown:
                mock_edge_breakdown.return_value = {"IMPORTS": 423, "CALLS": 2156}

                result = await database_tools.graph_stats(ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["node_count"] == 1248
        assert result["edge_count"] == 3847
        assert result["is_connected"] is True
        assert result["node_types"]["File"] == 42


class TestGraphValidate:
    """Test graph_validate tool."""

    @pytest.mark.asyncio
    async def test_graph_validate_success(self):
        """Test successful graph validation."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.get_stats.return_value = {"node_count": 1248, "edge_count": 3847}

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        with patch(
            "src.mcp_server.tools.database_tools._count_orphaned_nodes"
        ) as mock_orphaned:
            mock_orphaned.return_value = 0

            with patch(
                "src.mcp_server.tools.database_tools._count_broken_references"
            ) as mock_broken:
                mock_broken.return_value = 0

                result = await database_tools.graph_validate(ctx=mock_ctx)

        assert result["status"] == "valid"
        assert "consistent" in result["message"]
        assert result["orphaned_nodes"] == 0
        assert result["safe_for_queries"] is True

    @pytest.mark.asyncio
    async def test_graph_validate_with_orphaned_nodes(self):
        """Test graph validation with orphaned nodes."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_neo4j.get_stats.return_value = {"node_count": 1248, "edge_count": 3847}

        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        with patch(
            "src.mcp_server.tools.database_tools._count_orphaned_nodes"
        ) as mock_orphaned:
            mock_orphaned.return_value = 5

            with patch(
                "src.mcp_server.tools.database_tools._count_broken_references"
            ) as mock_broken:
                mock_broken.return_value = 0

                result = await database_tools.graph_validate(ctx=mock_ctx)

        assert result["status"] == "warning"
        assert result["orphaned_nodes"] == 5
        assert any("orphaned" in w.lower() for w in result["warnings"])
        assert result["safe_for_queries"] is True


# ==================== PHASE 2 TESTS ====================


class TestGraphDiffRebuild:
    """Test graph_diff_rebuild tool."""

    @pytest.mark.asyncio
    async def test_graph_diff_rebuild_success(self):
        """Test successful incremental rebuild."""
        mock_ctx = Mock()
        mock_services = Mock()
        mock_ctx.request_context.lifespan_context = mock_services

        # Mock git diff
        with patch("src.mcp_server.tools.database_tools.subprocess.check_output") as mock_git:
            mock_git.return_value = "diff --git a/src/test.py b/src/test.py\n..."

            # Mock diff parser
            mock_diff_summary = Mock()
            mock_file = Mock()
            mock_file.file_path = "src/test.py"
            mock_diff_summary.files = [mock_file]
            mock_services.diff_parser.parse_diff.return_value = mock_diff_summary

            # Mock parsers
            mock_services.python_parser.parse_file.return_value = [Mock() for _ in range(5)]
            mock_services.typescript_parser = None

            result = await database_tools.graph_diff_rebuild(commit_range="HEAD~1..HEAD", ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["files_changed"] == 1
        assert result["symbols_added"] == 5

    @pytest.mark.asyncio
    async def test_graph_diff_rebuild_no_changes(self):
        """Test diff_rebuild with no changes."""
        mock_ctx = Mock()
        mock_services = Mock()
        mock_ctx.request_context.lifespan_context = mock_services

        with patch("src.mcp_server.tools.database_tools.subprocess.check_output") as mock_git:
            mock_git.return_value = ""

            result = await database_tools.graph_diff_rebuild(ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["files_changed"] == 0
        assert result["graph_updated"] is False


class TestGraphClearSymbol:
    """Test graph_clear_symbol tool."""

    @pytest.mark.asyncio
    async def test_graph_clear_symbol_success(self):
        """Test successful symbol deletion."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Mock Neo4j responses with proper context manager
        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__.return_value = mock_session
        mock_ctx_mgr.__exit__.return_value = None
        mock_neo4j.driver.session.return_value = mock_ctx_mgr

        # Mock single() calls
        mock_find_record = {"node_id": 42}
        mock_count_record = {"edge_count": 3, "affected_types": ["Function"]}
        mock_delete_record = {"deleted_count": 1}

        mock_session.run.return_value.single.side_effect = [
            mock_find_record,
            mock_count_record,
            mock_delete_record,
        ]

        result = await database_tools.graph_clear_symbol(symbol_name="test_func", ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["symbol_deleted"] == "test_func"

    @pytest.mark.asyncio
    async def test_graph_clear_symbol_not_found(self):
        """Test clearing non-existent symbol."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Mock Neo4j: symbol not found
        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__.return_value = mock_session
        mock_ctx_mgr.__exit__.return_value = None
        mock_neo4j.driver.session.return_value = mock_ctx_mgr

        mock_session.run.return_value.single.return_value = None

        result = await database_tools.graph_clear_symbol(symbol_name="nonexistent", ctx=mock_ctx)

        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestGraphBackup:
    """Test graph_backup tool."""

    @pytest.mark.asyncio
    async def test_graph_backup_success(self):
        """Test successful graph backup."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Mock Neo4j responses with proper context manager
        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__.return_value = mock_session
        mock_ctx_mgr.__exit__.return_value = None
        mock_neo4j.driver.session.return_value = mock_ctx_mgr

        # Mock nodes and edges queries
        mock_session.run.side_effect = [
            [{"node": {"id": 1, "name": "func1", "type": "Function"}}],
            [{"edge": {"source_id": 1, "target_id": 2, "type": "CALLS"}}],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = str(Path(tmpdir) / "test_backup.json")

            result = await database_tools.graph_backup(backup_path=backup_path, ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["nodes_exported"] == 1
        assert result["edges_exported"] == 1


class TestGraphRestore:
    """Test graph_restore tool."""

    @pytest.mark.asyncio
    async def test_graph_restore_success(self):
        """Test successful graph restore."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        # Create test backup file
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = str(Path(tmpdir) / "backup.json")
            backup_data = {
                "timestamp": "2026-04-03T00:00:00",
                "node_count": 1,
                "edge_count": 1,
                "nodes": [{"id": 1, "name": "func1", "type": "Function", "properties": {}}],
                "edges": [
                    {
                        "source_id": 1,
                        "target_id": 2,
                        "type": "CALLS",
                        "properties": {},
                    }
                ],
            }
            with open(backup_path, "w") as f:
                json.dump(backup_data, f)

            # Mock Neo4j with proper context manager
            mock_session = MagicMock()
            mock_ctx_mgr = MagicMock()
            mock_ctx_mgr.__enter__.return_value = mock_session
            mock_ctx_mgr.__exit__.return_value = None
            mock_neo4j.driver.session.return_value = mock_ctx_mgr
            mock_neo4j.clear_database.return_value = None

            result = await database_tools.graph_restore(backup_path=backup_path, ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["nodes_restored"] == 1
        assert result["edges_restored"] == 1


class TestGraphExport:
    """Test graph_export tool."""

    @pytest.mark.asyncio
    async def test_graph_export_json(self):
        """Test exporting graph as JSON."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__.return_value = mock_session
        mock_ctx_mgr.__exit__.return_value = None
        mock_neo4j.driver.session.return_value = mock_ctx_mgr

        mock_session.run.side_effect = [
            [{"node": {"id": 1, "name": "func1", "type": "Function", "file": "test.py", "line": 10}}],
            [{"edge": {"source_id": 1, "target_id": 2, "type": "CALLS"}}],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = str(Path(tmpdir) / "export.json")

            result = await database_tools.graph_export(export_path=export_path, format="json", ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["format"] == "json"
        assert result["nodes_exported"] == 1

    @pytest.mark.asyncio
    async def test_graph_export_graphml(self):
        """Test exporting graph as GraphML."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__.return_value = mock_session
        mock_ctx_mgr.__exit__.return_value = None
        mock_neo4j.driver.session.return_value = mock_ctx_mgr

        mock_session.run.side_effect = [
            [{"node": {"id": 1, "name": "func1", "type": "Function", "file": "test.py", "line": 10}}],
            [{"edge": {"source_id": 1, "target_id": 2, "type": "CALLS"}}],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = str(Path(tmpdir) / "export.graphml")

            result = await database_tools.graph_export(export_path=export_path, format="graphml", ctx=mock_ctx)

        assert result["status"] == "success"
        assert result["format"] == "graphml"


class TestGraphReindex:
    """Test graph_reindex tool."""

    @pytest.mark.asyncio
    async def test_graph_reindex_all(self):
        """Test reindexing all node types."""
        mock_ctx = Mock()
        mock_neo4j = Mock()
        mock_services = Mock()
        mock_services.neo4j_client = mock_neo4j
        mock_ctx.request_context.lifespan_context = mock_services

        mock_neo4j.create_indexes.return_value = None

        result = await database_tools.graph_reindex(node_type="all", ctx=mock_ctx)

        assert result["status"] == "success"
        assert "node_id_idx" in result["indexes_recreated"]
        mock_neo4j.create_indexes.assert_called_once()
