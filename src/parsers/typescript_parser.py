"""TypeScript symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from tree_sitter import Language, Parser

from src.parsers.base_parser import BaseParser
from src.parsers.import_resolver import ImportResolver
from src.parsers.symbol import Symbol

# Load Tree-sitter TypeScript grammar
try:
    from tree_sitter_typescript import language_tsx, language_typescript
    TYPESCRIPT_LANGUAGE = Language(language_typescript())
    TSX_LANGUAGE = Language(language_tsx())
except ImportError:
    raise ImportError(
        "tree-sitter-typescript not installed. Run: pip install tree-sitter-typescript"
    )


class TypeScriptParser(BaseParser):
    """Extract symbols from TypeScript source code using Tree-sitter."""

    LANGUAGE = "typescript"
    EXTENSIONS = [".ts", ".tsx"]

    def __init__(self, base_path: Optional[str] = None):
        """Initialize parser.

        Args:
            base_path: Root directory for resolving relative imports
        """
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = TYPESCRIPT_LANGUAGE
        self.import_resolver = ImportResolver(base_path)

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse TypeScript file and extract symbols."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Set language based on file extension
        if file_path.endswith('.tsx'):
            self.parser.language = TSX_LANGUAGE
        else:
            self.parser.language = TYPESCRIPT_LANGUAGE

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

        The TypeScriptParser uses parse_file() which directly calls _extract_from_node()
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
        if node.type == "function_declaration":
            sym = self._extract_function(node, source_code, file_path, parent)
            if sym is not None:
                symbols.append(sym)
            # Extract nested functions
            self._extract_nested(node, source_code, file_path, symbols, parent)

        elif node.type == "class_declaration":
            class_symbol = self._extract_class(node, source_code, file_path, parent)
            if class_symbol is not None:
                symbols.append(class_symbol)
                # Extract class methods
                self._extract_class_members(
                    node, source_code, file_path, symbols, class_symbol.name
                )

        elif node.type == "method_definition":
            # Standalone method (shouldn't happen at top level)
            pass

        elif node.type == "import_statement":
            symbols.extend(self._extract_imports(node, source_code, file_path))

        elif node.type == "interface_declaration":
            sym = self._extract_interface(node, source_code, file_path, parent)
            if sym is not None:
                symbols.append(sym)

        elif node.type == "type_alias_declaration":
            sym = self._extract_type_alias(node, source_code, file_path, parent)
            if sym is not None:
                symbols.append(sym)

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
        """Extract function declaration."""
        return self._make_symbol(node, "function", source_code, file_path, parent)

    def _extract_class(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract class declaration."""
        return self._make_symbol(node, "class", source_code, file_path, parent)

    def _extract_interface(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract interface declaration."""
        return self._make_symbol(node, "interface", source_code, file_path, parent)

    def _extract_type_alias(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract type alias declaration."""
        return self._make_symbol(node, "type", source_code, file_path, parent)

    def _extract_class_members(
        self,
        class_node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        class_name: str,
    ):
        """Extract methods from class body."""
        # Find class body
        for child in class_node.children:
            if child.type == "class_body":
                for stmt in child.children:
                    if stmt.type == "method_definition":
                        method = self._extract_method(
                            stmt, source_code, file_path, class_name
                        )
                        if method is not None:
                            symbols.append(method)

    def _extract_method(
        self,
        node,
        source_code: bytes,
        file_path: str,
        class_name: str,
    ) -> Symbol:
        """Extract method definition."""
        return self._make_symbol(node, "function", source_code, file_path, class_name)

    def _extract_nested(
        self,
        node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        parent: Optional[str] = None,
    ):
        """Extract nested functions inside function body."""
        for child in node.children:
            if child.type == "statement_block":
                for stmt in child.children:
                    if stmt.type == "function_declaration":
                        nested = self._extract_function(
                            stmt, source_code, file_path, parent
                        )
                        symbols.append(nested)

    def _extract_imports(
        self, node, source_code: bytes, file_path: str
    ) -> List[Symbol]:
        """Extract symbols from import statement."""
        imports = []
        source_text = source_code[node.start_byte : node.end_byte].decode("utf-8")

        # Extract from path (what's being imported from)
        from_path = None
        for child in node.children:
            if child.type == "string":
                from_path = source_code[
                    child.start_byte : child.end_byte
                ].decode("utf-8").strip('\'"')
                break

        if not from_path:
            return imports

        # Resolve relative imports
        resolved_path = self.import_resolver.resolve_typescript_import(from_path, file_path)

        # Extract imported names
        imported_names = ImportResolver.extract_import_names(source_text)

        # If no specific names found, use the path itself
        if not imported_names:
            imports.append(
                Symbol(
                    name=resolved_path,
                    type="import",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                )
            )
        else:
            for name in imported_names:
                if name == "*":
                    imports.append(
                        Symbol(
                            name=f"{resolved_path}.*",
                            type="import",
                            file=file_path,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                        )
                    )
                else:
                    imports.append(
                        Symbol(
                            name=f"{resolved_path}.{name}",
                            type="import",
                            file=file_path,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                        )
                    )

        return imports

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Extract JSDoc comment before node.

        Overrides BaseParser._get_docstring() with TypeScript-specific implementation.
        Looks for JSDoc/comment nodes before the symbol.
        """
        # Look for comment nodes before this node
        if node.prev_sibling and node.prev_sibling.type in (
            "comment",
            "line_comment",
        ):
            comment = source_code[
                node.prev_sibling.start_byte : node.prev_sibling.end_byte
            ].decode("utf-8")
            # Remove comment markers
            return comment.replace("//", "").replace("/*", "").replace("*/", "").strip()
        return None
