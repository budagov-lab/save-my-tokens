"""Graph builder orchestrates parsing, indexing, and graph construction."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.graph.call_analyzer import CallAnalyzer
from src.graph.neo4j_client import Neo4jClient
from src.graph.node_types import Edge, EdgeType, Node, NodeType
from src.parsers.import_resolver import ImportResolver
from src.parsers.python_parser import PythonParser
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex

try:
    from src.parsers.typescript_parser import TypeScriptParser
except ImportError:
    TypeScriptParser = None  # type: ignore[name-defined]


class GraphBuilder:
    """Orchestrates the full pipeline: Parse -> Index -> Create Graph Nodes -> Create Graph Edges."""

    def __init__(self, base_path: str, neo4j_client: Optional[Neo4jClient] = None):
        """Initialize graph builder.

        Args:
            base_path: Root directory of code to analyze
            neo4j_client: Neo4j client (created if not provided)
        """
        self.base_path = Path(base_path)
        self.neo4j_client = neo4j_client or Neo4jClient()
        self.import_resolver = ImportResolver(str(self.base_path))
        self.python_parser = PythonParser(str(self.base_path))
        self.typescript_parser = TypeScriptParser(str(self.base_path)) if TypeScriptParser else None  # type: ignore[operator]
        self.symbol_index: SymbolIndex = SymbolIndex()
        self.call_analyzer = CallAnalyzer(self.symbol_index)
        self.nodes: List[Node] = []
        self.edges: List[Tuple[Edge, str, str]] = []
        logger.info(f"Initialized GraphBuilder for {base_path}")

    def build(self) -> None:
        """Execute the full graph construction pipeline."""
        logger.info("Starting graph construction pipeline...")

        # Step 1: Parse all files and build symbol index
        self._parse_all_files()
        logger.info(f"Parsed files: {len(self.symbol_index.get_all())} symbols extracted")

        # Step 2: Create graph nodes
        self._create_nodes()
        logger.info(f"Created {len(self.nodes)} nodes")

        # Step 3: Create graph edges
        self._create_edges()
        logger.info(f"Created {len(self.edges)} edges")

        # Step 4: Flush to Neo4j
        self._persist_to_neo4j()
        logger.info("Graph construction complete")

    def _parse_all_files(self) -> None:
        """Parse all Python and TypeScript files in base_path."""
        # Find Python files
        python_files = self.base_path.rglob("*.py")
        for file_path in python_files:
            if ".venv" in str(file_path) or "__pycache__" in str(file_path):
                continue
            try:
                symbols = self.python_parser.parse_file(str(file_path))
                self.symbol_index.add_all(symbols)
                logger.debug(f"Parsed {file_path}: {len(symbols)} symbols")
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")

        # Find TypeScript/JavaScript files (only if TypeScript parser is available)
        if self.typescript_parser:
            ts_files = list(self.base_path.rglob("*.ts")) + list(self.base_path.rglob("*.tsx"))
            js_files = list(self.base_path.rglob("*.js")) + list(self.base_path.rglob("*.jsx"))
            for file_path in ts_files + js_files:
                if "node_modules" in str(file_path) or ".next" in str(file_path):
                    continue
                try:
                    symbols = self.typescript_parser.parse_file(str(file_path))
                    self.symbol_index.add_all(symbols)
                    logger.debug(f"Parsed {file_path}: {len(symbols)} symbols")
                except Exception as e:
                    logger.warning(f"Failed to parse {file_path}: {e}")

    def _create_nodes(self) -> None:
        """Create nodes from symbols in the index."""
        for symbol in self.symbol_index.get_all():
            # Convert Symbol to Node
            node_type = self._map_symbol_type_to_node_type(symbol.type)
            node = Node(
                node_id=symbol.node_id,
                type=node_type,
                name=symbol.name,
                file=symbol.file,
                line=symbol.line,
                column=symbol.column,
                docstring=symbol.docstring,
                parent=symbol.parent,
            )
            self.nodes.append(node)

    def _create_edges(self) -> None:
        """Create edges from symbol relationships."""
        for symbol in self.symbol_index.get_all():
            # DEFINES edge: parent file contains this symbol
            if symbol.file:
                file_node_id = f"File:{symbol.file}:1:{symbol.file}"
                edge = Edge(
                    source_id=file_node_id,
                    target_id=symbol.node_id,
                    type=EdgeType.DEFINES,
                )
                file_node_type = NodeType.FILE.value
                self.edges.append((edge, file_node_type, self._map_symbol_type_to_node_type(symbol.type).value))

            # INHERITS edge: for class inheritance (parent field)
            if symbol.parent and symbol.type == "class":
                parent_candidates = self.symbol_index.get_by_name(symbol.parent)
                if parent_candidates:
                    parent_symbol = parent_candidates[0]
                    edge = Edge(
                        source_id=symbol.node_id,
                        target_id=parent_symbol.node_id,
                        type=EdgeType.INHERITS,
                    )
                    self.edges.append(
                        (edge, NodeType.CLASS.value, self._map_symbol_type_to_node_type(parent_symbol.type).value)
                    )

            # IMPORTS edge: for imports
            if symbol.type == "import":
                # symbol.name is the resolved import path
                # Find matching module/file
                module_name = symbol.name
                # Try to find matching file or module symbol
                matching_symbols = self.symbol_index.get_by_name(module_name)
                if matching_symbols:
                    target_symbol = matching_symbols[0]
                    edge = Edge(
                        source_id=symbol.node_id,
                        target_id=target_symbol.node_id,
                        type=EdgeType.IMPORTS,
                    )
                    self.edges.append(
                        (
                            edge,
                            NodeType.FUNCTION.value,  # Import statement belongs to file/function
                            self._map_symbol_type_to_node_type(target_symbol.type).value,
                        )
                    )

    def _persist_to_neo4j(self) -> None:
        """Write nodes and edges to Neo4j."""
        # Create indexes
        self.neo4j_client.create_indexes()

        # Create all nodes
        if self.nodes:
            self.neo4j_client.create_nodes_batch(self.nodes)

        # Create all edges
        if self.edges:
            self.neo4j_client.create_edges_batch(self.edges)

    @staticmethod
    def _map_symbol_type_to_node_type(symbol_type: str) -> NodeType:
        """Map Symbol type string to NodeType enum.

        Args:
            symbol_type: Symbol type from parser

        Returns:
            Corresponding NodeType
        """
        type_mapping = {
            "function": NodeType.FUNCTION,
            "class": NodeType.CLASS,
            "variable": NodeType.VARIABLE,
            "import": NodeType.MODULE,
            "type": NodeType.TYPE,
            "interface": NodeType.INTERFACE,
        }
        return type_mapping.get(symbol_type, NodeType.VARIABLE)

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics.

        Returns:
            Dictionary with symbol_count, node_count, edge_count
        """
        stats = self.neo4j_client.get_stats()
        stats["symbol_count"] = len(self.symbol_index.get_all())
        return stats
