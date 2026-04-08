"""Unit tests for SMTQueryEngine."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.query_engine import SMTQueryEngine
from src.graph.cycle_detector import CycleGroup


class TestSMTQueryEngine(unittest.TestCase):
    """Test SMTQueryEngine structured query interface."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock Neo4jClient to avoid database dependency
        self.mock_client_patch = patch("src.agents.query_engine.Neo4jClient")
        self.mock_client_class = self.mock_client_patch.start()
        self.mock_client = MagicMock()
        self.mock_client_class.return_value = self.mock_client

        # Initialize engine with mocked client
        self.engine = SMTQueryEngine()
        self.engine.client = self.mock_client

    def tearDown(self):
        """Clean up patches."""
        self.mock_client_patch.stop()

    def test_definition_found(self):
        """Test definition() when symbol is found."""
        # Mock Neo4j session
        mock_session = MagicMock()
        self.mock_client.driver.session.return_value.__enter__.return_value = mock_session

        # Mock node
        mock_node = MagicMock()
        mock_node.labels = ["Function"]
        mock_node.get.side_effect = lambda key, default=None: {
            "name": "test_func",
            "file": "src/test.py",
            "line": 42,
            "signature": "def test_func():",
            "docstring": "Test function.",
        }.get(key, default)

        mock_session.run.side_effect = [
            MagicMock(single=MagicMock(return_value={"n": mock_node})),
            MagicMock(data=MagicMock(return_value=[
                {"name": "helper1", "file": "src/helper.py"},
                {"name": "helper2", "file": "src/helper.py"},
            ])),
        ]

        result = self.engine.definition("test_func")

        self.assertTrue(result["found"])
        self.assertEqual(result["name"], "test_func")
        self.assertEqual(result["line"], 42)
        self.assertEqual(len(result["callees"]), 2)

    def test_definition_not_found(self):
        """Test definition() when symbol is not found."""
        mock_session = MagicMock()
        self.mock_client.driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.single.return_value = None

        result = self.engine.definition("nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(result["symbol"], "nonexistent")

    def test_context_found(self):
        """Test context() when symbol is found."""
        mock_session = MagicMock()
        self.mock_client.driver.session.return_value.__enter__.return_value = mock_session

        # Mock bounded subgraph
        subgraph = {
            "root": {"name": "main", "file": "src/main.py", "line": 1, "labels": ["Function"]},
            "nodes": [
                {"name": "main", "file": "src/main.py", "line": 1, "labels": ["Function"]},
                {"name": "helper", "file": "src/helper.py", "line": 10, "labels": ["Function"]},
            ],
            "edges": [{"src": "main", "dst": "helper"}],
            "depth_reached": 2,
        }
        self.mock_client.get_bounded_subgraph.return_value = subgraph

        result = self.engine.context("main", depth=2)

        self.assertTrue(result["found"])
        self.assertEqual(result["symbol"], "main")
        self.assertEqual(result["final_node_count"], 2)
        self.assertEqual(len(result["edges"]), 1)
        self.assertGreater(result["token_estimate"], 0)

    def test_context_with_cycles(self):
        """Test context() detects cycles."""
        self.mock_client.get_bounded_subgraph.return_value = {
            "root": {"name": "a", "file": "test.py", "line": 1, "labels": ["Function"]},
            "nodes": [
                {"name": "a", "file": "test.py", "line": 1, "labels": ["Function"]},
                {"name": "b", "file": "test.py", "line": 10, "labels": ["Function"]},
            ],
            "edges": [
                {"src": "a", "dst": "b"},
                {"src": "b", "dst": "a"},  # Cycle!
            ],
            "depth_reached": 2,
        }

        result = self.engine.context("a")

        self.assertTrue(result["found"])
        self.assertGreater(len(result["cycles"]), 0)
        self.assertEqual(len(result["cycles"][0]["members"]), 2)

    def test_context_not_found(self):
        """Test context() when symbol not found."""
        self.mock_client.get_bounded_subgraph.return_value = {}

        result = self.engine.context("nonexistent")

        self.assertFalse(result["found"])

    def test_impact_found(self):
        """Test impact() when symbol is found."""
        self.mock_client.get_impact_graph.return_value = {
            "root": {"name": "core", "file": "src/core.py", "line": 5, "labels": ["Function"]},
            "nodes": [
                {"name": "core", "file": "src/core.py", "line": 5, "labels": ["Function"]},
                {"name": "wrapper", "file": "src/api.py", "line": 20, "labels": ["Function"]},
                {"name": "handler", "file": "src/api.py", "line": 30, "labels": ["Function"]},
            ],
            "edges": [
                {"src": "wrapper", "dst": "core"},
                {"src": "handler", "dst": "wrapper"},
            ],
            "depth_reached": 3,
        }

        result = self.engine.impact("core", depth=3)

        self.assertTrue(result["found"])
        self.assertEqual(result["symbol"], "core")
        self.assertGreater(result["total_callers"], 0)
        self.assertIn(1, result["callers_by_depth"])

    def test_impact_not_found(self):
        """Test impact() when symbol not found."""
        self.mock_client.get_impact_graph.return_value = {}

        result = self.engine.impact("nonexistent")

        self.assertFalse(result["found"])

    @patch("src.agents.query_engine.EmbeddingService")
    def test_search(self, mock_embedding_service_class):
        """Test search() returns formatted results."""
        from src.parsers.symbol import Symbol

        # Mock EmbeddingService
        mock_svc = MagicMock()
        mock_embedding_service_class.return_value = mock_svc

        # Create mock symbols with search results
        symbol1 = Symbol(
            name="detect_cycles",
            type="Function",
            file="src/graph/cycle_detector.py",
            line=22,
            column=0,
            docstring="Detect strongly connected components.",
            parent=None,
            node_id="Function:cycle_detector.py:22:detect_cycles",
        )
        symbol2 = Symbol(
            name="CycleGroup",
            type="Class",
            file="src/graph/cycle_detector.py",
            line=8,
            column=0,
            docstring="Represents a cycle.",
            parent=None,
            node_id="Class:cycle_detector.py:8:CycleGroup",
        )

        mock_svc.search.return_value = [
            (symbol1, 0.95),
            (symbol2, 0.87),
        ]

        results = self.engine.search("cycle detection", top_k=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "detect_cycles")
        self.assertEqual(results[0]["type"], "Function")
        self.assertAlmostEqual(results[0]["score"], 0.95)
        self.assertEqual(results[1]["name"], "CycleGroup")

    @patch("src.agents.query_engine.validate_graph")
    def test_status(self, mock_validate):
        """Test status() returns freshness and stats."""
        from src.graph.validator import ValidationResult

        # Mock validation result
        validation = ValidationResult(
            is_fresh=True,
            git_head="a1b2c3d",
            graph_head="a1b2c3d",
            commits_behind=0,
        )
        mock_validate.return_value = validation

        # Mock stats
        self.mock_client.get_stats.return_value = {
            "node_count": 150,
            "edge_count": 200,
        }

        result = self.engine.status()

        self.assertTrue(result["is_fresh"])
        self.assertEqual(result["freshness_status"], "fresh")
        self.assertEqual(result["node_count"], 150)
        self.assertEqual(result["edge_count"], 200)

    @patch("src.agents.query_engine.validate_graph")
    def test_status_stale(self, mock_validate):
        """Test status() when graph is stale."""
        from src.graph.validator import ValidationResult

        validation = ValidationResult(
            is_fresh=False,
            git_head="z9y8x7w",
            graph_head="a1b2c3d",
            commits_behind=3,
        )
        mock_validate.return_value = validation

        self.mock_client.get_stats.return_value = {
            "node_count": 100,
            "edge_count": 120,
        }

        result = self.engine.status()

        self.assertFalse(result["is_fresh"])
        self.assertEqual(result["freshness_status"], "stale")
        self.assertEqual(result["commits_behind"], 3)

    def test_context_compression(self):
        """Test context() with compression enabled."""
        self.mock_client.get_bounded_subgraph.return_value = {
            "root": {"name": "start", "file": "test.py", "line": 1, "labels": ["Function"]},
            "nodes": [
                {"name": "start", "file": "test.py", "line": 1, "labels": ["Function"]},
                {"name": "bridge", "file": "test.py", "line": 5, "labels": ["Function"]},
                {"name": "end", "file": "test.py", "line": 10, "labels": ["Function"]},
            ],
            "edges": [
                {"src": "start", "dst": "bridge"},
                {"src": "bridge", "dst": "end"},
            ],
            "depth_reached": 2,
        }

        with patch("src.agents.query_engine.compress_subgraph") as mock_compress:
            from src.graph.compressor import CompressionResult

            # Mock compression: remove bridge node
            mock_compress.return_value = CompressionResult(
                nodes=["start", "end"],
                edges=[("start", "end")],
                bridges=["bridge"],
                bridge_paths=["start → [bridge] → end"],
            )

            result = self.engine.context("start", compress=True)

            self.assertTrue(result["compressed"])
            self.assertEqual(result["bridges_removed"], 1)
            self.assertEqual(result["final_node_count"], 2)


if __name__ == "__main__":
    unittest.main()
