"""Python symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from tree_sitter import Parser

from src.parsers.base_parser import BaseParser
from src.parsers.import_resolver import ImportResolver
from src.parsers.symbol import Symbol

# Load Tree-sitter Python grammar
try:
    from tree_sitter import Language
    from tree_sitter_python import language
    PYTHON_LANGUAGE = Language(language())
except ImportError:
    raise ImportError("tree-sitter-python not installed. Run: pip install tree-sitter-python")


class PythonParser(BaseParser):
    """Extract symbols from Python source code using Tree-sitter."""

    LANGUAGE = "python"
    EXTENSIONS = [".py"]

    def __init__(self, base_path: Optional[str] = None):
        """Initialize parser.

        Args:
            base_path: Root directory for resolving relative imports
        """
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = PYTHON_LANGUAGE
        self.import_resolver = ImportResolver(base_path)

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse Python file and extract symbols."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = self.parser.parse(source_code)
        symbols = []

        # Extract top-level symbols
        self._extract_from_node(
            tree.root_node, source_code, file_path, symbols, parent=None
        )

        return symbols

    def _extract_symbols(
        self, source_code: str, file_path: str
    ) -> List[Symbol]:
        """Extract symbols from source code (unused, provided for BaseParser compatibility).

        The PythonParser uses parse_file() which directly calls _extract_from_node()
        instead of this method. This is kept for abstract method implementation.
        """
        return []

    def _extract_from_node(
        self,
        node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        parent: Optional[str] = None,
    ):
        """Recursively extract symbols from AST node."""
        if node.type == "function_definition":
            sym = self._extract_function(node, source_code, file_path, parent)
            if sym is not None:
                symbols.append(sym)
            # Extract nested functions/classes
            self._extract_nested(node, source_code, file_path, symbols, parent)

        elif node.type == "class_definition":
            class_symbol = self._extract_class(node, source_code, file_path, parent)
            if class_symbol is not None:
                symbols.append(class_symbol)
                # Extract class methods
                self._extract_class_members(
                    node, source_code, file_path, symbols, class_symbol.name
                )

        elif node.type == "import_statement":
            symbols.extend(self._extract_imports(node, source_code, file_path))

        elif node.type == "import_from_statement":
            symbols.extend(self._extract_from_imports(node, source_code, file_path))

        # Recursively process all children
        for child in node.children:
            self._extract_from_node(
                child, source_code, file_path, symbols, parent=parent
            )

    def _extract_function(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract function definition."""
        return self._make_symbol(node, "function", source_code, file_path, parent)

    def _extract_class(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract class definition."""
        return self._make_symbol(node, "class", source_code, file_path, parent)

    def _extract_class_members(
        self,
        class_node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        class_name: str,
    ):
        """Extract methods from class body."""
        # Find class body block
        for child in class_node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        method = self._extract_function(
                            stmt, source_code, file_path, class_name
                        )
                        if method is not None:
                            symbols.append(method)

    def _extract_nested(
        self,
        node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        parent: Optional[str] = None,
    ):
        """Extract nested functions/classes inside function body."""
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        nested = self._extract_function(
                            stmt, source_code, file_path, parent
                        )
                        symbols.append(nested)
                    elif stmt.type == "class_definition":
                        nested_class = self._extract_class(
                            stmt, source_code, file_path, parent
                        )
                        symbols.append(nested_class)

    def _extract_imports(
        self, node, source_code: bytes, file_path: str
    ) -> List[Symbol]:
        """Extract symbols from 'import X' statement."""
        imports = []
        statement_text = source_code[node.start_byte : node.end_byte].decode("utf-8")
        imported_names = ImportResolver.extract_import_names(statement_text)

        for name in imported_names:
            # Resolve relative imports
            resolved_name = self.import_resolver.resolve_python_import(name, file_path)
            imports.append(
                Symbol(
                    name=resolved_name,
                    type="import",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                )
            )
        return imports

    def _extract_from_imports(
        self, node, source_code: bytes, file_path: str
    ) -> List[Symbol]:
        """Extract symbols from 'from X import Y' statement."""
        imports = []
        statement_text = source_code[node.start_byte : node.end_byte].decode("utf-8")

        # Parse the from statement to extract module and imported names
        # Format: from module import name1, name2, ...
        if " import " not in statement_text:
            return imports

        from_part, import_part = statement_text.split(" import ", 1)
        module_name = from_part.replace("from", "").strip()

        # Resolve relative imports in module name
        resolved_module = self.import_resolver.resolve_python_import(module_name, file_path)

        # Extract individual imports
        imported_names = ImportResolver.extract_import_names(import_part)

        for name in imported_names:
            if name == "*":
                # Star import
                imports.append(
                    Symbol(
                        name=f"{resolved_module}.*",
                        type="import",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )
            else:
                # Named import
                imports.append(
                    Symbol(
                        name=f"{resolved_module}.{name}",
                        type="import",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        return imports

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Extract docstring from function/class.

        Overrides BaseParser._get_docstring() with Python-specific implementation.
        Docstring is first string literal in the body.
        """
        # Docstring is first string literal in the body
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        if stmt.child_count > 0:
                            first_child = stmt.children[0]
                            if first_child.type == "string":
                                docstring = source_code[
                                    first_child.start_byte : first_child.end_byte
                                ].decode("utf-8")
                                # Remove quotes
                                return docstring.strip('\'"')
        return None
