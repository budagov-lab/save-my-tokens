"""Graph builder orchestrates parsing, indexing, and graph construction."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

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

    def build(self, build_embeddings: bool = True) -> None:
        """Execute the full graph construction pipeline.

        Args:
            build_embeddings: Whether to generate embeddings and build FAISS index (default: True)
        """
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

        # Step 5: Build embeddings and FAISS index for semantic search
        if build_embeddings:
            self._build_embeddings_and_index()
            logger.info("Embeddings and FAISS index ready for semantic search")

    def _parse_all_files(self) -> None:
        """Parse all Python and TypeScript files in base_path."""
        # Collect all files first
        all_files = []
        python_files = list(self.base_path.rglob("*.py"))
        for file_path in python_files:
            if ".venv" not in str(file_path) and "__pycache__" not in str(file_path):
                all_files.append((file_path, "python"))

        if self.typescript_parser:
            ts_files = list(self.base_path.rglob("*.ts")) + list(self.base_path.rglob("*.tsx"))
            js_files = list(self.base_path.rglob("*.js")) + list(self.base_path.rglob("*.jsx"))
            for file_path in ts_files + js_files:
                if "node_modules" not in str(file_path) and ".next" not in str(file_path):
                    all_files.append((file_path, "typescript"))

        # Parse with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Parsing files"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.description}"),
        ) as progress:
            task = progress.add_task("", total=len(all_files))

            for file_path, file_type in all_files:
                try:
                    if file_type == "python":
                        symbols = self.python_parser.parse_file(str(file_path))
                    else:
                        symbols = self.typescript_parser.parse_file(str(file_path))

                    self.symbol_index.add_all(symbols)
                    logger.debug(f"Parsed {file_path}: {len(symbols)} symbols")
                except Exception as e:
                    logger.warning(f"Failed to parse {file_path}: {e}")

                progress.update(task, description=f"{len(self.symbol_index.get_all())} symbols", advance=1)

    def _create_nodes(self) -> None:
        """Create nodes from symbols in the index."""
        symbols = self.symbol_index.get_all()

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]Creating nodes"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.description}"),
        ) as progress:
            task = progress.add_task("", total=len(symbols) + 1)

            # First, create File nodes for each unique file
            files_seen = set()
            for symbol in symbols:
                if symbol.file and symbol.file not in files_seen:
                    files_seen.add(symbol.file)
                    file_node_id = f"File:{symbol.file}:1:{symbol.file}"
                    file_node = Node(
                        node_id=file_node_id,
                        type=NodeType.FILE,
                        name=symbol.file,
                        file=symbol.file,
                        line=1,
                        column=1,
                    )
                    self.nodes.append(file_node)

            progress.update(task, advance=1)

            # Then create nodes from symbols
            for symbol in symbols:
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
                progress.update(task, description=f"{len(self.nodes)} nodes", advance=1)

    def _create_edges(self) -> None:
        """Create edges from symbol relationships."""
        # File cache for CALLS edge generation: file_path -> (source_bytes, tree)
        file_cache: Dict[str, Tuple[bytes, any]] = {}  # type: ignore[type-arg]

        symbols = self.symbol_index.get_all()
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold yellow]Creating edges"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.description}"),
        ) as progress:
            task = progress.add_task("", total=len(symbols))

            for symbol in symbols:
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

                # IMPORTS edge: from file to imported module
                if symbol.type == "import":
                    # symbol.file is the file that imports
                    # symbol.name is the imported module name
                    if symbol.file:
                        source_file_id = f"File:{symbol.file}:1:{symbol.file}"
                        # Try to find matching module node for the imported name
                        matching_symbols = self.symbol_index.get_by_name(symbol.name)
                        if matching_symbols:
                            target_symbol = matching_symbols[0]
                            edge = Edge(
                                source_id=source_file_id,
                                target_id=target_symbol.node_id,
                                type=EdgeType.IMPORTS,
                            )
                            self.edges.append(
                                (
                                    edge,
                                    NodeType.FILE.value,  # Import is from the file
                                    self._map_symbol_type_to_node_type(target_symbol.type).value,
                                )
                            )

                # CALLS edges: extract function calls using CallAnalyzer
                if symbol.type == "function" and symbol.file:
                    file_path = symbol.file
                    ext = Path(file_path).suffix.lower()

                    # Determine which parser to use
                    parser_obj = None
                    if ext == ".py":
                        parser_obj = self.python_parser
                    elif ext in (".ts", ".tsx", ".js", ".jsx"):
                        parser_obj = self.typescript_parser
                    else:
                        continue

                    # Skip if parser not available
                    if parser_obj is None:
                        continue

                    try:
                        # Re-parse file (cached per file)
                        if file_path not in file_cache:
                            with open(file_path, "rb") as f:
                                source_bytes = f.read()
                            tree = parser_obj.parser.parse(source_bytes)
                            file_cache[file_path] = (source_bytes, tree)

                        source_bytes, tree = file_cache[file_path]

                        # Find the function node matching this symbol's line (convert 1-indexed to 0-indexed)
                        func_node = self._find_node_at_line(tree.root_node, symbol.line - 1, ext)
                        if func_node is None:
                            continue

                        # Extract calls
                        if ext == ".py":
                            callee_ids = self.call_analyzer.extract_calls_python(func_node, source_bytes, file_path)
                        else:
                            callee_ids = self.call_analyzer.extract_calls_typescript(func_node, source_bytes, file_path)

                        # Create CALLS edges
                        for callee_id in callee_ids:
                            edge = Edge(source_id=symbol.node_id, target_id=callee_id, type=EdgeType.CALLS)
                            self.edges.append((edge, NodeType.FUNCTION.value, NodeType.FUNCTION.value))

                    except (OSError, Exception) as e:  # noqa: BLE001
                        logger.debug(f"Failed to extract calls from {file_path}: {e}")

                progress.update(task, description=f"{len(self.edges)} edges", advance=1)

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

    def _build_embeddings_and_index(self) -> None:
        """Generate embeddings for all symbols and build FAISS index.

        This is done during graph build so semantic search is instant on first use.
        """
        try:
            from src.embeddings.embedding_service import EmbeddingService

            logger.info("Building embeddings and FAISS index for semantic search...")

            # Create embedding service
            cache_dir = Path(self.base_path).parent / '.claude' / '.embeddings'
            svc = EmbeddingService(self.symbol_index, cache_dir=cache_dir)

            # Build the FAISS index (generates embeddings for all symbols)
            svc.build_index()

            logger.info(f"Embeddings built for {len(self.symbol_index.get_all())} symbols")
        except Exception as e:
            logger.warning(f"Failed to build embeddings/index: {e}. Semantic search will generate them on first use.")

    def _find_node_at_line(self, node: any, target_line: int, file_ext: str) -> Optional[any]:  # type: ignore[name-defined]
        """Find a function/method definition node at a specific line (0-indexed).

        Args:
            node: Current tree-sitter node to search
            target_line: 0-indexed line number to find
            file_ext: File extension (.py, .ts, etc) to determine node types to search for

        Returns:
            Tree-sitter node for the function at that line, or None if not found
        """
        # Determine the node type names based on file extension
        if file_ext == ".py":
            func_types = ("function_definition",)
        else:  # TypeScript/JavaScript
            func_types = ("function_declaration", "arrow_function", "method_definition")

        # Check if current node is a function definition at the target line
        if node.type in func_types and node.start_point[0] == target_line:
            return node

        # Recursively search children
        for child in node.children:
            result = self._find_node_at_line(child, target_line, file_ext)
            if result:
                return result

        return None

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
