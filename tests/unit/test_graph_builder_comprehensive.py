"""Comprehensive tests for graph builder."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.graph.graph_builder import GraphBuilder
from src.graph.neo4j_client import Neo4jClient
from src.graph.node_types import EdgeType, Node, NodeType
from src.parsers.python_parser import PythonParser
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def temp_dir():
    """Create temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func_a", type="function", file="module_a.py", line=1, column=0))
    index.add(Symbol(name="func_b", type="function", file="module_b.py", line=10, column=0))
    index.add(Symbol(name="ClassA", type="class", file="module_a.py", line=20, column=0))
    index.add(Symbol(name="os", type="import", file="module_a.py", line=1, column=0))
    return index


@pytest.fixture
def graph_builder(temp_dir):
    """Create graph builder."""
    mock_neo4j = MagicMock()
    return GraphBuilder(str(temp_dir), neo4j_client=mock_neo4j)


class TestGraphBuilderInit:
    """Test GraphBuilder initialization."""

    def test_init_creates_parsers(self, temp_dir):
        """Test initialization creates required parsers."""
        builder = GraphBuilder(str(temp_dir))

        assert builder.base_path == temp_dir
        assert builder.python_parser is not None
        assert builder.import_resolver is not None
        assert builder.symbol_index is not None
        assert builder.call_analyzer is not None

    def test_init_with_neo4j_client(self, temp_dir):
        """Test initialization with provided Neo4j client."""
        mock_neo4j = MagicMock()
        builder = GraphBuilder(str(temp_dir), neo4j_client=mock_neo4j)

        assert builder.neo4j_client is mock_neo4j

    def test_init_creates_neo4j_if_not_provided(self, temp_dir):
        """Test initialization creates Neo4j client if not provided."""
        with patch('src.graph.graph_builder.Neo4jClient'):
            builder = GraphBuilder(str(temp_dir))

            assert builder.neo4j_client is not None

    def test_init_typescript_parser_optional(self, temp_dir):
        """Test TypeScript parser is optional."""
        with patch('src.graph.graph_builder.TypeScriptParser', None):
            builder = GraphBuilder(str(temp_dir))

            assert builder.typescript_parser is None


class TestBuild:
    """Test full graph construction pipeline."""

    def test_build_executes_pipeline(self, graph_builder):
        """Test build executes all pipeline steps."""
        with patch.object(graph_builder, '_parse_all_files'):
            with patch.object(graph_builder, '_create_nodes'):
                with patch.object(graph_builder, '_create_edges'):
                    with patch.object(graph_builder, '_persist_to_neo4j'):
                        graph_builder.build()

    def test_build_parses_files_first(self, graph_builder):
        """Test build starts with parsing."""
        with patch.object(graph_builder, '_parse_all_files') as mock_parse:
            with patch.object(graph_builder, '_create_nodes'):
                with patch.object(graph_builder, '_create_edges'):
                    with patch.object(graph_builder, '_persist_to_neo4j'):
                        graph_builder.build()

                        mock_parse.assert_called_once()

    def test_build_creates_nodes(self, graph_builder):
        """Test build creates nodes."""
        with patch.object(graph_builder, '_parse_all_files'):
            with patch.object(graph_builder, '_create_nodes') as mock_nodes:
                with patch.object(graph_builder, '_create_edges'):
                    with patch.object(graph_builder, '_persist_to_neo4j'):
                        graph_builder.build()

                        mock_nodes.assert_called_once()

    def test_build_creates_edges(self, graph_builder):
        """Test build creates edges."""
        with patch.object(graph_builder, '_parse_all_files'):
            with patch.object(graph_builder, '_create_nodes'):
                with patch.object(graph_builder, '_create_edges') as mock_edges:
                    with patch.object(graph_builder, '_persist_to_neo4j'):
                        graph_builder.build()

                        mock_edges.assert_called_once()

    def test_build_persists_to_neo4j(self, graph_builder):
        """Test build persists to Neo4j."""
        with patch.object(graph_builder, '_parse_all_files'):
            with patch.object(graph_builder, '_create_nodes'):
                with patch.object(graph_builder, '_create_edges'):
                    with patch.object(graph_builder, '_persist_to_neo4j') as mock_persist:
                        graph_builder.build()

                        mock_persist.assert_called_once()


class TestParseAllFiles:
    """Test file parsing."""

    def test_parse_all_files_empty_directory(self, temp_dir, graph_builder):
        """Test parsing empty directory."""
        graph_builder._parse_all_files()

        assert len(graph_builder.symbol_index.get_all()) == 0

    def test_parse_all_files_python(self, temp_dir, graph_builder):
        """Test parsing Python files."""
        # Create a Python file
        py_file = temp_dir / "test.py"
        py_file.write_text("def test(): pass")

        mock_symbols = [
            Symbol(name="test", type="function", file=str(py_file), line=1, column=0)
        ]

        with patch.object(graph_builder.python_parser, 'parse_file', return_value=mock_symbols):
            graph_builder._parse_all_files()

            symbols = graph_builder.symbol_index.get_all()
            assert len(symbols) > 0

    def test_parse_all_files_excludes_venv(self, temp_dir, graph_builder):
        """Test parsing excludes venv directories."""
        # Create file in venv
        venv_dir = temp_dir / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        venv_file = venv_dir / "test.py"
        venv_file.write_text("def test(): pass")

        with patch.object(graph_builder.python_parser, 'parse_file') as mock_parse:
            graph_builder._parse_all_files()

            # Should not parse venv files
            assert not any(".venv" in str(call) for call in mock_parse.call_args_list)

    def test_parse_all_files_excludes_pycache(self, temp_dir, graph_builder):
        """Test parsing excludes pycache directories."""
        cache_dir = temp_dir / "__pycache__"
        cache_dir.mkdir()
        cache_file = cache_dir / "test.py"
        cache_file.write_text("def test(): pass")

        with patch.object(graph_builder.python_parser, 'parse_file') as mock_parse:
            graph_builder._parse_all_files()

            assert not any("__pycache__" in str(call) for call in mock_parse.call_args_list)

    def test_parse_all_files_handles_exception(self, temp_dir, graph_builder):
        """Test parsing handles exceptions gracefully."""
        py_file = temp_dir / "test.py"
        py_file.write_text("invalid")

        with patch.object(graph_builder.python_parser, 'parse_file', side_effect=Exception("Parse error")):
            # Should not raise
            graph_builder._parse_all_files()

    def test_parse_typescript_files_if_available(self, temp_dir):
        """Test TypeScript files parsed if parser available."""
        mock_neo4j = MagicMock()
        builder = GraphBuilder(str(temp_dir), neo4j_client=mock_neo4j)
        builder.typescript_parser = MagicMock()

        ts_file = temp_dir / "test.ts"
        ts_file.write_text("function test() {}")

        with patch.object(builder.typescript_parser, 'parse_file', return_value=[]):
            builder._parse_all_files()

    def test_parse_typescript_excludes_node_modules(self, temp_dir):
        """Test TypeScript parsing excludes node_modules."""
        mock_neo4j = MagicMock()
        builder = GraphBuilder(str(temp_dir), neo4j_client=mock_neo4j)
        builder.typescript_parser = MagicMock()

        nm_dir = temp_dir / "node_modules"
        nm_dir.mkdir()
        ts_file = nm_dir / "test.ts"
        ts_file.write_text("function test() {}")

        with patch.object(builder.typescript_parser, 'parse_file') as mock_parse:
            builder._parse_all_files()

            assert not any("node_modules" in str(call) for call in mock_parse.call_args_list)


class TestCreateNodes:
    """Test node creation."""

    def test_create_nodes_from_symbols(self, graph_builder, symbol_index):
        """Test nodes created from symbols."""
        graph_builder.symbol_index = symbol_index

        graph_builder._create_nodes()

        assert len(graph_builder.nodes) == len(symbol_index.get_all())

    def test_create_nodes_maps_symbol_to_node(self, graph_builder, symbol_index):
        """Test symbol properties mapped to node."""
        graph_builder.symbol_index = symbol_index

        graph_builder._create_nodes()

        nodes = graph_builder.nodes
        assert any(node.name == "func_a" for node in nodes)
        assert any(node.name == "ClassA" for node in nodes)

    def test_create_nodes_preserves_metadata(self, graph_builder, symbol_index):
        """Test node metadata preserved."""
        graph_builder.symbol_index = symbol_index

        graph_builder._create_nodes()

        func_node = [n for n in graph_builder.nodes if n.name == "func_a"][0]
        assert func_node.file == "module_a.py"
        assert func_node.line == 1

    def test_create_nodes_empty_index(self, graph_builder):
        """Test creating nodes with empty index."""
        graph_builder._create_nodes()

        assert len(graph_builder.nodes) == 0


class TestCreateEdges:
    """Test edge creation."""

    def test_create_edges_defines(self, graph_builder, symbol_index):
        """Test DEFINES edges created."""
        graph_builder.symbol_index = symbol_index

        graph_builder._create_edges()

        # Should have DEFINES edges for each symbol
        assert any(edge[0].type == EdgeType.DEFINES for edge in graph_builder.edges)

    def test_create_edges_imports(self, graph_builder, symbol_index):
        """Test IMPORTS edges created for imports."""
        graph_builder.symbol_index = symbol_index

        graph_builder._create_edges()

        # os import should create an edge if matching symbol found
        import_edges = [e for e in graph_builder.edges if e[0].type == EdgeType.IMPORTS]

    def test_create_edges_inherits(self, graph_builder):
        """Test INHERITS edges created for classes."""
        index = SymbolIndex()
        parent = Symbol(name="Parent", type="class", file="test.py", line=1, column=0)
        child = Symbol(name="Child", type="class", file="test.py", line=10, column=0, parent="Parent")
        index.add(parent)
        index.add(child)

        graph_builder.symbol_index = index

        graph_builder._create_edges()

        inherits_edges = [e for e in graph_builder.edges if e[0].type == EdgeType.INHERITS]
        assert len(inherits_edges) > 0

    def test_create_edges_empty_index(self, graph_builder):
        """Test edge creation with empty index."""
        graph_builder._create_edges()

        assert len(graph_builder.edges) == 0


class TestPersistToNeo4j:
    """Test persistence to Neo4j."""

    def test_persist_creates_indexes(self, graph_builder):
        """Test persistence creates indexes."""
        graph_builder._persist_to_neo4j()

        graph_builder.neo4j_client.create_indexes.assert_called_once()

    def test_persist_creates_nodes(self, graph_builder, symbol_index):
        """Test persistence creates nodes."""
        graph_builder.symbol_index = symbol_index
        graph_builder._create_nodes()

        graph_builder._persist_to_neo4j()

        graph_builder.neo4j_client.create_nodes_batch.assert_called_once()

    def test_persist_creates_edges(self, graph_builder, symbol_index):
        """Test persistence creates edges."""
        graph_builder.symbol_index = symbol_index
        graph_builder._create_edges()

        graph_builder._persist_to_neo4j()

        if graph_builder.edges:
            graph_builder.neo4j_client.create_edges_batch.assert_called_once()

    def test_persist_skips_empty_nodes(self, graph_builder):
        """Test persistence skips if no nodes."""
        graph_builder._persist_to_neo4j()

        graph_builder.neo4j_client.create_nodes_batch.assert_not_called()

    def test_persist_skips_empty_edges(self, graph_builder):
        """Test persistence skips if no edges."""
        graph_builder._persist_to_neo4j()

        graph_builder.neo4j_client.create_edges_batch.assert_not_called()


class TestMapSymbolTypeToNodeType:
    """Test symbol to node type mapping."""

    def test_map_function(self):
        """Test function mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("function")
        assert node_type == NodeType.FUNCTION

    def test_map_class(self):
        """Test class mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("class")
        assert node_type == NodeType.CLASS

    def test_map_variable(self):
        """Test variable mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("variable")
        assert node_type == NodeType.VARIABLE

    def test_map_import(self):
        """Test import mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("import")
        assert node_type == NodeType.MODULE

    def test_map_type(self):
        """Test type mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("type")
        assert node_type == NodeType.TYPE

    def test_map_interface(self):
        """Test interface mapping."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("interface")
        assert node_type == NodeType.INTERFACE

    def test_map_unknown(self):
        """Test unknown type defaults to variable."""
        node_type = GraphBuilder._map_symbol_type_to_node_type("unknown")
        assert node_type == NodeType.VARIABLE


class TestGetStats:
    """Test statistics retrieval."""

    def test_get_stats(self, graph_builder, symbol_index):
        """Test getting statistics."""
        graph_builder.symbol_index = symbol_index
        graph_builder.neo4j_client.get_stats.return_value = {
            "node_count": 5,
            "edge_count": 10,
        }

        stats = graph_builder.get_stats()

        assert "symbol_count" in stats
        assert stats["symbol_count"] == len(symbol_index.get_all())
        assert "node_count" in stats
        assert "edge_count" in stats
