"""Unit tests for Neo4j client operations with mocking."""

import pytest
from unittest.mock import MagicMock, patch
from src.graph.neo4j_client import Neo4jClient
from src.graph.node_types import Node, NodeType, Edge, EdgeType


class TestNeo4jClientInitAndCleanup:
    """Test Neo4j client initialization and cleanup."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_init_creates_driver(self, mock_driver_factory):
        """Test that client initializes driver."""
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()

        assert client.driver is not None
        mock_driver_factory.assert_called_once()

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_init_with_custom_uri(self, mock_driver_factory):
        """Test initialization with custom URI."""
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient(uri="bolt://custom:7687")

        assert client.uri == "bolt://custom:7687"
        call_args = mock_driver_factory.call_args
        assert "bolt://custom:7687" in call_args[0]

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_close_closes_driver(self, mock_driver_factory):
        """Test close properly closes driver."""
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        client.close()

        mock_driver.close.assert_called_once()


class TestNeo4jClientDatabaseOps:
    """Test database operations."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_clear_database(self, mock_driver_factory):
        """Test clearing database runs DETACH DELETE."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        client.clear_database()

        mock_session.run.assert_called()
        assert "DETACH DELETE" in mock_session.run.call_args[0][0]

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_indexes(self, mock_driver_factory):
        """Test index creation."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        client.create_indexes()

        # Should create 4 indexes
        assert mock_session.run.call_count == 4
        # All should have IF NOT EXISTS
        for call in mock_session.run.call_args_list:
            assert "IF NOT EXISTS" in call[0][0]


class TestNeo4jClientNodeOps:
    """Test node operations."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_node(self, mock_driver_factory):
        """Test creating single node."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        node = Node(node_id="f1", name="func1", type=NodeType.FUNCTION, file="test.py", line=1, column=0)
        client.create_node(node)

        mock_session.run.assert_called_once()
        assert "CREATE" in mock_session.run.call_args[0][0]

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_nodes_batch(self, mock_driver_factory):
        """Test creating multiple nodes."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        nodes = [
            Node(node_id="f1", name="func1", type=NodeType.FUNCTION, file="test.py", line=1, column=0),
            Node(node_id="f2", name="func2", type=NodeType.FUNCTION, file="test.py", line=10, column=0),
        ]
        client.create_nodes_batch(nodes)

        # Should create 2 nodes
        assert mock_session.run.call_count == 2

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_nodes_batch_empty(self, mock_driver_factory):
        """Test batch with empty list does nothing."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        client.create_nodes_batch([])

        # Should not run queries
        mock_session.run.assert_not_called()

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_get_node(self, mock_driver_factory):
        """Test getting node by ID."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {"n": {"name": "func1", "node_id": "f1"}}
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        node = client.get_node("f1")

        assert node is not None
        mock_session.run.assert_called_once()

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_get_node_not_found(self, mock_driver_factory):
        """Test getting non-existent node."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        node = client.get_node("nonexistent")

        assert node is None


class TestNeo4jClientEdgeOps:
    """Test edge operations."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_edge(self, mock_driver_factory):
        """Test creating single edge."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        edge = Edge(source_id="f1", target_id="f2", type=EdgeType.CALLS)
        client.create_edge(edge, "Function", "Function")

        mock_session.run.assert_called_once()
        call_cypher = mock_session.run.call_args[0][0]
        assert "MERGE" in call_cypher
        assert "CALLS" in call_cypher

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_edges_batch(self, mock_driver_factory):
        """Test creating multiple edges."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        edges = [
            (Edge(source_id="f1", target_id="f2", type=EdgeType.CALLS), "Function", "Function"),
            (Edge(source_id="f2", target_id="f3", type=EdgeType.CALLS), "Function", "Function"),
        ]
        client.create_edges_batch(edges)

        # Should create 2 edges
        assert mock_session.run.call_count == 2

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_edges_batch_empty(self, mock_driver_factory):
        """Test batch with empty list does nothing."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        client.create_edges_batch([])

        # Should not run queries
        mock_session.run.assert_not_called()


class TestNeo4jClientQueries:
    """Test query operations."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_get_neighbors(self, mock_driver_factory):
        """Test getting node neighbors."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.data.return_value = [{"n": {"name": "func2"}}]
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        neighbors = client.get_neighbors("f1", depth=1)

        assert isinstance(neighbors, list)
        mock_session.run.assert_called_once()

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_get_stats(self, mock_driver_factory):
        """Test getting database stats."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_single_result = MagicMock()
        mock_single_result.__getitem__ = MagicMock(return_value=5)
        mock_result.single.return_value = mock_single_result
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        stats = client.get_stats()

        assert isinstance(stats, dict)
        # Should run 2 queries (node count and edge count)
        assert mock_session.run.call_count >= 2


class TestNeo4jClientErrorHandling:
    """Test error handling."""

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_create_node_db_error(self, mock_driver_factory):
        """Test handling database error in create_node."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("DB Error")
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
        mock_driver_factory.return_value = mock_driver

        client = Neo4jClient()
        node = Node(node_id="f1", name="func1", type=NodeType.FUNCTION, file="test.py", line=1, column=0)

        with pytest.raises(Exception):
            client.create_node(node)

    @patch('src.graph.neo4j_client.GraphDatabase.driver')
    def test_driver_init_failure(self, mock_driver_factory):
        """Test handling driver initialization failure."""
        mock_driver_factory.side_effect = Exception("Connection failed")

        with pytest.raises(Exception):
            Neo4jClient()
