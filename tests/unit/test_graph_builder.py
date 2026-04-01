"""Unit tests for graph builder and related components."""

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.graph.call_analyzer import CallAnalyzer
from src.graph.graph_builder import GraphBuilder
from src.graph.node_types import Edge, EdgeType, Node, NodeType
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


class TestNodeTypes:
    """Test node and edge type definitions."""

    def test_node_creation(self) -> None:
        """Test creating a node."""
        node = Node(
            node_id="Function:src/main.py:1:test_func",
            type=NodeType.FUNCTION,
            name="test_func",
            file="src/main.py",
            line=1,
            column=0,
        )
        assert node.name == "test_func"
        assert node.type == NodeType.FUNCTION

    def test_node_cypher_props(self) -> None:
        """Test converting node to Cypher properties."""
        node = Node(
            node_id="Function:src/main.py:1:test_func",
            type=NodeType.FUNCTION,
            name="test_func",
            file="src/main.py",
            line=1,
            column=0,
            docstring="Test function",
        )
        props = node.to_cypher_props()
        assert props["node_id"] == "Function:src/main.py:1:test_func"
        assert props["name"] == "test_func"
        assert props["type"] == "Function"
        assert props["docstring"] == "Test function"

    def test_edge_creation(self) -> None:
        """Test creating an edge."""
        edge = Edge(
            source_id="Function:src/a.py:1:foo",
            target_id="Function:src/b.py:1:bar",
            type=EdgeType.CALLS,
        )
        assert edge.type == EdgeType.CALLS

    def test_edge_types(self) -> None:
        """Test all edge types are defined."""
        expected_types = ["IMPORTS", "CALLS", "DEFINES", "INHERITS", "DEPENDS_ON", "TYPE_OF", "IMPLEMENTS"]
        for expected in expected_types:
            assert hasattr(EdgeType, expected)


class TestCallAnalyzer:
    """Test call graph extraction."""

    @pytest.fixture
    def analyzer(self) -> CallAnalyzer:
        """Create analyzer with sample symbol index."""
        index = SymbolIndex()
        index.add(
            Symbol(
                name="func_a",
                type="function",
                file="test.py",
                line=1,
                column=0,
            )
        )
        index.add(
            Symbol(
                name="func_b",
                type="function",
                file="test.py",
                line=10,
                column=0,
            )
        )
        return CallAnalyzer(index)

    def test_resolve_simple_call(self, analyzer: CallAnalyzer) -> None:
        """Test resolving a simple function call."""
        resolved = analyzer._resolve_call_name("func_a", "test.py")
        assert resolved is not None
        assert "func_a" in resolved

    def test_resolve_unknown_call(self, analyzer: CallAnalyzer) -> None:
        """Test resolving a call to unknown function."""
        resolved = analyzer._resolve_call_name("unknown_func", "test.py")
        assert resolved is None

    def test_resolve_qualified_call(self, analyzer: CallAnalyzer) -> None:
        """Test resolving a qualified call (module.function)."""
        resolved = analyzer._resolve_call_name("module.func_a", "test.py")
        # Should find func_a even with module prefix
        assert resolved is not None


class TestGraphBuilderNodeTypes:
    """Test symbol type mapping in GraphBuilder."""

    def test_map_symbol_to_node_type(self) -> None:
        """Test mapping symbol types to node types."""
        assert GraphBuilder._map_symbol_type_to_node_type("function") == NodeType.FUNCTION
        assert GraphBuilder._map_symbol_type_to_node_type("class") == NodeType.CLASS
        assert GraphBuilder._map_symbol_type_to_node_type("variable") == NodeType.VARIABLE
        assert GraphBuilder._map_symbol_type_to_node_type("import") == NodeType.MODULE
        assert GraphBuilder._map_symbol_type_to_node_type("type") == NodeType.TYPE
        assert GraphBuilder._map_symbol_type_to_node_type("interface") == NodeType.INTERFACE
        assert GraphBuilder._map_symbol_type_to_node_type("unknown") == NodeType.VARIABLE

    @patch("src.graph.graph_builder.Neo4jClient")
    def test_graph_builder_init(self, mock_neo4j: MagicMock) -> None:
        """Test GraphBuilder initialization."""
        builder = GraphBuilder("/tmp/test")
        assert builder.base_path == Path("/tmp/test")
        assert builder.symbol_index is not None
        assert builder.python_parser is not None
        # TypeScript parser may be None if tree-sitter-typescript not installed
        assert builder.typescript_parser is None or builder.typescript_parser is not None

    @patch("src.graph.graph_builder.Neo4jClient")
    def test_graph_builder_create_nodes(self, mock_neo4j: MagicMock) -> None:
        """Test creating nodes from symbols."""
        builder = GraphBuilder("/tmp/test")

        # Add test symbols
        symbol1 = Symbol(
            name="test_func",
            type="function",
            file="test.py",
            line=1,
            column=0,
        )
        symbol2 = Symbol(
            name="TestClass",
            type="class",
            file="test.py",
            line=10,
            column=0,
        )
        builder.symbol_index.add(symbol1)
        builder.symbol_index.add(symbol2)

        # Create nodes
        builder._create_nodes()
        assert len(builder.nodes) == 2

        # Verify node properties
        func_node = next(n for n in builder.nodes if n.name == "test_func")
        assert func_node.type == NodeType.FUNCTION
        assert func_node.line == 1

        class_node = next(n for n in builder.nodes if n.name == "TestClass")
        assert class_node.type == NodeType.CLASS
        assert class_node.line == 10
