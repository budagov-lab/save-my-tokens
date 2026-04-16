"""Java symbol extractor using Tree-sitter."""

from pathlib import Path
from typing import List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    from tree_sitter import Language, Parser
    from tree_sitter_java import language as java_language
    JAVA_LANGUAGE = Language(java_language())
except ImportError:
    raise ImportError("tree-sitter-java not installed. Run: pip install tree-sitter-java")


class JavaParser(BaseParser):
    """Extract symbols from Java source code using Tree-sitter."""

    LANGUAGE = "java"
    EXTENSIONS = [".java"]

    def __init__(self, base_path: Optional[str] = None):
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = JAVA_LANGUAGE

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse Java file and extract symbols."""
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
        """Walk declarations and extract symbols."""
        last_doc: Optional[str] = None

        for child in node.children:
            if child.type == "block_comment":
                text = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if text.startswith("/**"):
                    # Javadoc comment — strip delimiters and leading * per line
                    lines = text[3:-2].splitlines()
                    cleaned = " ".join(
                        line.strip().lstrip("* ") for line in lines if line.strip().lstrip("* ")
                    )
                    last_doc = cleaned or None
                else:
                    last_doc = None

            elif child.type == "line_comment":
                last_doc = None

            elif child.type == "class_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="class",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=last_doc,
                        parent=parent,
                    )
                    symbols.append(sym)
                    # Recurse into class body
                    body = child.child_by_field_name("body")
                    if body:
                        self._extract_from_node(body, source_code, file_path, symbols, parent=name)
                last_doc = None

            elif child.type == "interface_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="interface",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=last_doc,
                        parent=parent,
                    )
                    symbols.append(sym)
                    body = child.child_by_field_name("body")
                    if body:
                        self._extract_from_node(body, source_code, file_path, symbols, parent=name)
                last_doc = None

            elif child.type == "enum_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="class",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=last_doc,
                        parent=parent,
                    )
                    symbols.append(sym)
                    # Recurse into enum body to capture methods defined inside the enum
                    body = child.child_by_field_name("body")
                    if body:
                        self._extract_from_node(body, source_code, file_path, symbols, parent=name)
                last_doc = None

            elif child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="function",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=last_doc,
                        parent=parent,
                    )
                    symbols.append(sym)
                last_doc = None

            elif child.type == "constructor_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="function",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=last_doc,
                        parent=parent,
                    )
                    symbols.append(sym)
                last_doc = None

            elif child.type == "import_declaration":
                symbols.extend(self._extract_imports(child, source_code, file_path))
                last_doc = None

            elif child.is_named:
                last_doc = None

    def _extract_imports(self, node, source_code: bytes, file_path: str) -> List[Symbol]:
        """Extract import paths from import_declaration."""
        imports: List[Symbol] = []
        # Walk children to find scoped_identifier or identifier
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                full = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                # Use last segment as the symbol name (e.g. "ArrayList" from "java.util.ArrayList")
                name = full.rsplit(".", 1)[-1]
                imports.append(Symbol(
                    name=name,
                    type="import",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                ))
                break  # only one path per import declaration
        return imports

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Java Javadoc comments are preceding siblings — handled in _extract_from_node."""
        return None
