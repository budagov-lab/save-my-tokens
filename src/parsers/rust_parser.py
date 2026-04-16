"""Rust symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    from tree_sitter import Language, Parser
    from tree_sitter_rust import language as rust_language
    RUST_LANGUAGE = Language(rust_language())
except ImportError:
    raise ImportError("tree-sitter-rust not installed. Run: pip install tree-sitter-rust")


class RustParser(BaseParser):
    """Extract symbols from Rust source code using Tree-sitter."""

    LANGUAGE = "rust"
    EXTENSIONS = [".rs"]

    def __init__(self, base_path: Optional[str] = None):
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = RUST_LANGUAGE

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse Rust file and extract symbols."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = self.parser.parse(source_code)
        symbols: List[Symbol] = []
        self._extract_from_node(tree.root_node, source_code, file_path, symbols)
        self._log_parsing(file_path, len(symbols))
        return symbols

    def _extract_symbols(self, source_code: str, file_path: str) -> List[Symbol]:
        """Unused — parse_file calls _extract_from_node directly."""
        return []

    def _extract_from_node(
        self,
        node,
        source_code: bytes,
        file_path: str,
        symbols: List[Symbol],
        parent: Optional[str] = None,
    ) -> None:
        """Walk top-level declarations and extract symbols."""
        last_doc: Optional[str] = None

        for child in node.children:
            if child.type == "line_comment":
                text = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                stripped = text.lstrip("/").strip()
                if text.lstrip().startswith("///"):
                    # Accumulate doc comment lines
                    last_doc = (last_doc + " " + stripped) if last_doc else stripped
                else:
                    last_doc = None

            elif child.type == "function_item":
                sym = self._make_symbol(child, "function", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "struct_item":
                sym = self._make_symbol(child, "class", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "enum_item":
                sym = self._make_symbol(child, "class", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "trait_item":
                sym = self._make_symbol(child, "interface", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "type_item":
                sym = self._make_symbol(child, "type", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "impl_item":
                # Extract the impl's type name for use as parent
                impl_type = self._get_impl_type(child, source_code)
                # Recurse into impl body to find method functions
                body = child.child_by_field_name("body")
                if body:
                    self._extract_from_node(body, source_code, file_path, symbols, parent=impl_type)
                last_doc = None

            elif child.type == "use_declaration":
                symbols.extend(self._extract_use(child, source_code, file_path))
                last_doc = None

            elif child.type == "mod_item":
                # Inline modules — recurse if they have a body
                body = child.child_by_field_name("body")
                if body:
                    mod_name_node = child.child_by_field_name("name")
                    mod_name = (
                        source_code[mod_name_node.start_byte:mod_name_node.end_byte]
                        .decode("utf-8", errors="replace")
                        if mod_name_node else None
                    )
                    self._extract_from_node(body, source_code, file_path, symbols, parent=mod_name)
                last_doc = None

            elif child.is_named:
                last_doc = None

    def _get_impl_type(self, impl_node, source_code: bytes) -> Optional[str]:
        """Extract the type name from an impl block (e.g. `impl MyStruct`)."""
        type_node = impl_node.child_by_field_name("type")
        if type_node:
            return source_code[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace")
        return None

    def _extract_use(self, node, source_code: bytes, file_path: str) -> List[Symbol]:
        """Extract import paths from use_declaration."""
        imports: List[Symbol] = []
        # The argument is the use tree (scoped_identifier, identifier, use_list, etc.)
        argument = node.child_by_field_name("argument")
        if argument:
            self._collect_use_paths(argument, source_code, file_path, node.start_point[0] + 1, imports)
        return imports

    def _collect_use_paths(self, node, source_code: bytes, file_path: str, line: int, imports: List[Symbol]) -> None:
        """Recursively collect leaf names from a use tree."""
        if node.type in ("identifier", "type_identifier"):
            name = source_code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            imports.append(Symbol(
                name=name,
                type="import",
                file=file_path,
                line=line,
                column=node.start_point[1],
            ))
        elif node.type == "scoped_identifier":
            # Take the name (last segment)
            name_node = node.child_by_field_name("name")
            if name_node:
                name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                imports.append(Symbol(
                    name=name,
                    type="import",
                    file=file_path,
                    line=line,
                    column=name_node.start_point[1],
                ))
        elif node.type == "use_list":
            for child in node.children:
                if child.is_named:
                    self._collect_use_paths(child, source_code, file_path, line, imports)
        elif node.type == "use_as_clause":
            # `use foo as bar` — take the alias
            alias = node.child_by_field_name("alias")
            if alias:
                name = source_code[alias.start_byte:alias.end_byte].decode("utf-8", errors="replace")
                imports.append(Symbol(
                    name=name,
                    type="import",
                    file=file_path,
                    line=line,
                    column=alias.start_point[1],
                ))
        elif node.type == "scoped_use_list":
            use_list = node.child_by_field_name("list")
            if use_list:
                self._collect_use_paths(use_list, source_code, file_path, line, imports)
        else:
            for child in node.children:
                if child.is_named:
                    self._collect_use_paths(child, source_code, file_path, line, imports)

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Rust doc comments are preceding siblings — handled in _extract_from_node."""
        return None
