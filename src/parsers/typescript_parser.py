"""TypeScript symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from tree_sitter import Language, Parser

from src.parsers.symbol import Symbol

# Load Tree-sitter TypeScript grammar
try:
    from tree_sitter_typescript import language
    TYPESCRIPT_LANGUAGE = Language(language())
except ImportError:
    raise ImportError(
        "tree-sitter-typescript not installed. Run: pip install tree-sitter-typescript"
    )


class TypeScriptParser:
    """Extract symbols from TypeScript source code using Tree-sitter."""

    def __init__(self):
        """Initialize parser."""
        self.parser = Parser()
        self.parser.language = TYPESCRIPT_LANGUAGE

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse TypeScript file and extract symbols."""
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
            symbols.append(
                self._extract_function(node, source_code, file_path, parent)
            )
            # Extract nested functions
            self._extract_nested(node, source_code, file_path, symbols, parent)

        elif node.type == "class_declaration":
            class_symbol = self._extract_class(node, source_code, file_path, parent)
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
            symbols.append(
                self._extract_interface(node, source_code, file_path, parent)
            )

        elif node.type == "type_alias_declaration":
            symbols.append(self._extract_type_alias(node, source_code, file_path, parent))

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
        name = self._get_child_text(node, "name", source_code)
        docstring = self._extract_jsdoc(node, source_code)

        return Symbol(
            name=name,
            type="function",
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            docstring=docstring,
            parent=parent,
        )

    def _extract_class(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract class declaration."""
        name = self._get_child_text(node, "name", source_code)
        docstring = self._extract_jsdoc(node, source_code)

        return Symbol(
            name=name,
            type="class",
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            docstring=docstring,
            parent=parent,
        )

    def _extract_interface(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract interface declaration."""
        name = self._get_child_text(node, "name", source_code)
        docstring = self._extract_jsdoc(node, source_code)

        return Symbol(
            name=name,
            type="interface",
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            docstring=docstring,
            parent=parent,
        )

    def _extract_type_alias(
        self,
        node,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Symbol:
        """Extract type alias declaration."""
        name = self._get_child_text(node, "name", source_code)
        docstring = self._extract_jsdoc(node, source_code)

        return Symbol(
            name=name,
            type="type",
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            docstring=docstring,
            parent=parent,
        )

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
                        symbols.append(method)

    def _extract_method(
        self,
        node,
        source_code: bytes,
        file_path: str,
        class_name: str,
    ) -> Symbol:
        """Extract method definition."""
        name = self._get_child_text(node, "name", source_code)
        docstring = self._extract_jsdoc(node, source_code)

        return Symbol(
            name=name,
            type="function",
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            docstring=docstring,
            parent=class_name,
        )

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

        # Handle: import x from 'y'
        for child in node.children:
            if child.type == "import_clause":
                for clause_child in child.children:
                    if clause_child.type in (
                        "namespace_import",
                        "named_imports",
                        "identifier",
                    ):
                        name = source_code[
                            clause_child.start_byte : clause_child.end_byte
                        ].decode("utf-8")
                        imports.append(
                            Symbol(
                                name=name.strip(),
                                type="import",
                                file=file_path,
                                line=node.start_point[0] + 1,
                                column=node.start_point[1],
                            )
                        )

        if not imports:
            # Fallback: extract entire import
            imports.append(
                Symbol(
                    name=source_text.strip(),
                    type="import",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                )
            )

        return imports

    def _extract_jsdoc(self, node, source_code: bytes) -> Optional[str]:
        """Extract JSDoc comment before node."""
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

    def _get_child_text(
        self, node, field_name: str, source_code: bytes
    ) -> Optional[str]:
        """Get text of child node by field name."""
        child = node.child_by_field_name(field_name)
        if child:
            return source_code[child.start_byte : child.end_byte].decode("utf-8")
        return None
