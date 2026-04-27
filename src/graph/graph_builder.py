"""Graph builder orchestrates parsing, indexing, and graph construction."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from src.graph.call_analyzer import CallAnalyzer
from src.graph.neo4j_client import Neo4jClient
from src.graph.node_types import Edge, EdgeType, Node, NodeType
from src.parsers.import_resolver import ImportResolver
from src.parsers.python_parser import PythonParser
from src.parsers.symbol_index import SymbolIndex
from src.smtignore import SMTIgnore

try:
    from src.parsers.typescript_parser import TypeScriptParser
except ImportError:
    TypeScriptParser = None  # type: ignore[name-defined]

try:
    from src.parsers.go_parser import GoParser
except ImportError:
    GoParser = None  # type: ignore[name-defined]

try:
    from src.parsers.rust_parser import RustParser
except ImportError:
    RustParser = None  # type: ignore[name-defined]

try:
    from src.parsers.java_parser import JavaParser
except ImportError:
    JavaParser = None  # type: ignore[name-defined]


class GraphBuilder:
    """Orchestrates the full pipeline: Parse -> Index -> Create Graph Nodes -> Create Graph Edges."""

    def __init__(self, base_path: str, neo4j_client: Optional[Neo4jClient] = None, project_id: str = ""):
        """Initialize graph builder.

        Args:
            base_path: Root directory of code to analyze
            neo4j_client: Neo4j client (created if not provided)
            project_id: Project namespace for graph isolation
        """
        self.base_path = Path(base_path)
        self.project_id = project_id
        self.neo4j_client = neo4j_client or Neo4jClient(project_id=project_id)
        self.import_resolver = ImportResolver(str(self.base_path))
        self.python_parser = PythonParser(str(self.base_path))
        self.typescript_parser = TypeScriptParser(str(self.base_path)) if TypeScriptParser else None  # type: ignore[operator]
        self.go_parser = GoParser(str(self.base_path)) if GoParser else None  # type: ignore[operator]
        self.rust_parser = RustParser(str(self.base_path)) if RustParser else None  # type: ignore[operator]
        self.java_parser = JavaParser(str(self.base_path)) if JavaParser else None  # type: ignore[operator]
        self.symbol_index: SymbolIndex = SymbolIndex()
        self.call_analyzer = CallAnalyzer(self.symbol_index)
        self.nodes: List[Node] = []
        self.edges: List[Tuple[Edge, str, str]] = []
        self.smtignore = SMTIgnore(self.base_path)
        if self.smtignore:
            logger.info(f"Loaded .smtignore from {self.base_path}")
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

    # Directories to always skip when scanning source files
    _SKIP_DIRS = {
        "node_modules", ".next", ".venv", "venv", "__pycache__",
        "generated", "dist", "build", "target", ".git", ".tox", "coverage",
        "htmlcov", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    }

    @classmethod
    def _should_skip(cls, file_path: Path) -> bool:
        return any(part in cls._SKIP_DIRS for part in file_path.parts)

    def _is_ignored(self, file_path: Path) -> bool:
        """Check both _SKIP_DIRS and .smtignore rules."""
        return self._should_skip(file_path) or self.smtignore.is_ignored(file_path)

    def _parse_all_files(self) -> None:
        """Parse all supported source files (Python, TypeScript, Go, Rust, Java) in base_path."""
        # Collect all files first
        all_files = []
        python_files = list(self.base_path.rglob("*.py"))
        for file_path in python_files:
            if not self._is_ignored(file_path):
                all_files.append((file_path, "python"))

        if self.typescript_parser:
            ts_files = list(self.base_path.rglob("*.ts")) + list(self.base_path.rglob("*.tsx"))
            js_files = list(self.base_path.rglob("*.js")) + list(self.base_path.rglob("*.jsx"))
            for file_path in ts_files + js_files:
                if not self._is_ignored(file_path):
                    all_files.append((file_path, "typescript"))

        if self.go_parser:
            for file_path in self.base_path.rglob("*.go"):
                if not self._is_ignored(file_path):
                    all_files.append((file_path, "go"))

        if self.rust_parser:
            for file_path in self.base_path.rglob("*.rs"):
                if not self._is_ignored(file_path):
                    all_files.append((file_path, "rust"))

        if self.java_parser:
            for file_path in self.base_path.rglob("*.java"):
                if not self._is_ignored(file_path):
                    all_files.append((file_path, "java"))

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
                    elif file_type == "typescript":
                        symbols = self.typescript_parser.parse_file(str(file_path))
                    elif file_type == "go":
                        symbols = self.go_parser.parse_file(str(file_path))
                    elif file_type == "rust":
                        symbols = self.rust_parser.parse_file(str(file_path))
                    else:  # java
                        symbols = self.java_parser.parse_file(str(file_path))

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
                        project_id=self.project_id,
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
                    end_line=symbol.end_line,
                    docstring=symbol.docstring,
                    parent=symbol.parent,
                    project_id=self.project_id,
                )
                self.nodes.append(node)
                progress.update(task, description=f"{len(self.nodes)} nodes", advance=1)

    def _build_line_index(self, root_node: any, file_ext: str) -> Dict[int, any]:  # type: ignore[name-defined]
        """Build a {start_line: tree_node} index for function nodes in a file.

        Avoids re-traversing the full AST for every symbol by indexing once per file.
        """
        if file_ext == ".py":
            func_types = ("function_definition",)
        elif file_ext in (".ts", ".tsx", ".js", ".jsx"):
            func_types = ("function_declaration", "arrow_function", "method_definition")
        elif file_ext == ".go":
            func_types = ("function_declaration", "method_declaration")
        elif file_ext == ".rs":
            func_types = ("function_item",)
        elif file_ext == ".java":
            func_types = ("method_declaration", "constructor_declaration")
        else:
            func_types = ("function_declaration",)

        index: Dict[int, any] = {}  # type: ignore[type-arg]
        stack = [root_node]
        while stack:
            node = stack.pop()
            if node.type in func_types:
                index[node.start_point[0]] = node
            stack.extend(node.children)
        return index

    def _create_edges(self) -> None:
        """Create edges from symbol relationships."""
        # File cache for CALLS edge generation: file_path -> (source_bytes, tree, line_index)
        file_cache: Dict[str, Tuple[bytes, any, Dict[int, any]]] = {}  # type: ignore[type-arg]

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

                    # Determine which parser and call conventions to use
                    parser_obj = None
                    body_type = "block"
                    call_type = "call"
                    call_name_field = "function"
                    if ext == ".py":
                        parser_obj = self.python_parser
                        body_type = "block"
                        call_type = "call"
                    elif ext in (".ts", ".tsx", ".js", ".jsx"):
                        parser_obj = self.typescript_parser
                        body_type = "statement_block"
                        call_type = "call_expression"
                    elif ext == ".go":
                        parser_obj = self.go_parser
                        body_type = "block"
                        call_type = "call_expression"
                    elif ext == ".rs":
                        parser_obj = self.rust_parser
                        body_type = "block"
                        call_type = "call_expression"
                    elif ext == ".java":
                        parser_obj = self.java_parser
                        body_type = "block"
                        call_type = "method_invocation"
                        call_name_field = "name"
                    else:
                        continue

                    # Skip if parser not available
                    if parser_obj is None:
                        continue

                    try:
                        # Re-parse file (cached per file); build line index once per file
                        if file_path not in file_cache:
                            with open(file_path, "rb") as f:
                                source_bytes = f.read()
                            tree = parser_obj.parser.parse(source_bytes)
                            line_index = self._build_line_index(tree.root_node, ext)
                            file_cache[file_path] = (source_bytes, tree, line_index)

                        source_bytes, tree, line_index = file_cache[file_path]

                        # O(1) lookup via pre-built line index (convert 1-indexed to 0-indexed)
                        func_node = line_index.get(symbol.line - 1)
                        if func_node is None:
                            continue

                        # Extract calls
                        callee_ids = self.call_analyzer.extract_calls(
                            func_node, source_bytes, file_path, body_type, call_type,
                            call_name_field=call_name_field,
                        )

                        # Create CALLS edges
                        for callee_id in callee_ids:
                            edge = Edge(source_id=symbol.node_id, target_id=callee_id, type=EdgeType.CALLS)
                            self.edges.append((edge, NodeType.FUNCTION.value, NodeType.FUNCTION.value))

                    except (OSError, Exception) as e:  # noqa: BLE001
                        logger.debug(f"Failed to extract calls from {file_path}: {e}")

                progress.update(task, description=f"{len(self.edges)} edges", advance=1)

    def _persist_to_neo4j(self) -> None:
        """Write nodes and edges to Neo4j."""
        self.neo4j_client.create_indexes()
        self.neo4j_client.clear_database()

        if self.nodes:
            self.neo4j_client.create_nodes_batch(self.nodes)

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
            cache_dir = Path(self.base_path) / '.smt' / 'embeddings'
            svc = EmbeddingService(self.symbol_index, cache_dir=cache_dir)

            # Build the FAISS index (generates embeddings for all symbols)
            svc.build_index()
            svc.save_index()

            logger.info(f"Embeddings built for {len(self.symbol_index.get_all())} symbols")
        except Exception as e:
            logger.warning(f"Failed to build embeddings/index: {e}. Semantic search will generate them on first use.")

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
