"""Go symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    from tree_sitter import Language, Parser
    from tree_sitter_go import language as go_language
    GO_LANGUAGE = Language(go_language())
except ImportError:
    raise ImportError("tree-sitter-go not installed. Run: pip install tree-sitter-go")


class GoParser(BaseParser):
    """Extract symbols from Go source code using Tree-sitter."""

    LANGUAGE = "go"
    EXTENSIONS = [".go"]

    def __init__(self, base_path: Optional[str] = None):
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = GO_LANGUAGE

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse Go file and extract symbols."""
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
            if child.type == "comment":
                text = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                last_doc = text.lstrip("/ ").strip()

            elif child.type == "function_declaration":
                sym = self._make_symbol(child, "function", source_code, file_path, parent)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "method_declaration":
                receiver_type = self._get_receiver_type(child, source_code)
                sym = self._make_symbol(child, "function", source_code, file_path, receiver_type)
                if sym is not None:
                    if last_doc:
                        sym.docstring = last_doc
                    symbols.append(sym)
                last_doc = None

            elif child.type == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        type_node = spec.child_by_field_name("type")
                        name_node = spec.child_by_field_name("name")
                        if not name_node:
                            continue
                        name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                        if type_node:
                            if type_node.type == "struct_type":
                                sym_type = "class"
                            elif type_node.type == "interface_type":
                                sym_type = "interface"
                            else:
                                sym_type = "type"
                        else:
                            sym_type = "type"
                        sym = Symbol(
                            name=name,
                            type=sym_type,
                            file=file_path,
                            line=spec.start_point[0] + 1,
                            column=spec.start_point[1],
                            docstring=last_doc,
                        )
                        symbols.append(sym)
                last_doc = None

            elif child.type == "import_declaration":
                symbols.extend(self._extract_imports(child, source_code, file_path))
                last_doc = None

            elif child.is_named:
                last_doc = None

    def _get_receiver_type(self, method_node, source_code: bytes) -> Optional[str]:
        """Extract the receiver struct type from a method declaration."""
        receiver = method_node.child_by_field_name("receiver")  # parameter_list
        if not receiver:
            return None
        for child in receiver.children:
            if child.type == "parameter_declaration":
                for tc in child.children:
                    if tc.type == "type_identifier":
                        return source_code[tc.start_byte:tc.end_byte].decode("utf-8", errors="replace")
                    if tc.type == "pointer_type":
                        for ptc in tc.children:
                            if ptc.type == "type_identifier":
                                return source_code[ptc.start_byte:ptc.end_byte].decode("utf-8", errors="replace")
        return None

    def _extract_imports(self, node, source_code: bytes, file_path: str) -> List[Symbol]:
        """Extract import paths from import_declaration."""
        imports: List[Symbol] = []

        def _add_spec(spec_node) -> None:
            # import_spec has an interpreted_string_literal or raw_string_literal child
            for child in spec_node.children:
                if child.type in ("interpreted_string_literal", "raw_string_literal"):
                    path = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip('"` ')
                    # Use the last path segment as the symbol name (e.g. "fmt" from "fmt")
                    name = path.rstrip("/").rsplit("/", 1)[-1]
                    imports.append(Symbol(
                        name=name,
                        type="import",
                        file=file_path,
                        line=spec_node.start_point[0] + 1,
                        column=spec_node.start_point[1],
                    ))

        for child in node.children:
            if child.type == "import_spec":
                _add_spec(child)
            elif child.type == "import_spec_list":
                for sub in child.children:
                    if sub.type == "import_spec":
                        _add_spec(sub)

        return imports

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Go doc comments are preceding siblings — handled in _extract_from_node."""
        return None
