"""C# symbol extractor using Tree-sitter."""

import re
from pathlib import Path
from typing import List, Optional

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    from tree_sitter import Language, Parser
    from tree_sitter_c_sharp import language as csharp_language
    CSHARP_LANGUAGE = Language(csharp_language())
except ImportError:
    raise ImportError("tree-sitter-c-sharp not installed. Run: pip install tree-sitter-c-sharp")

_XML_TAG_RE = re.compile(r"<[^>]+>")


class CSharpParser(BaseParser):
    """Extract symbols from C# source code using Tree-sitter."""

    LANGUAGE = "csharp"
    EXTENSIONS = [".cs"]

    def __init__(self, base_path: Optional[str] = None):
        super().__init__(base_path or "")
        self.parser = Parser()
        self.parser.language = CSHARP_LANGUAGE

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse C# file and extract symbols."""
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
        doc_lines: List[str] = []

        for child in node.children:
            if child.type == "comment":
                text = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if text.startswith("///"):
                    stripped = text[3:].strip()
                    clean = _XML_TAG_RE.sub("", stripped).strip()
                    if clean:
                        doc_lines.append(clean)
                else:
                    doc_lines = []

            elif child.type in ("class_declaration", "struct_declaration", "record_declaration", "enum_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="class",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        docstring=" ".join(doc_lines) if doc_lines else None,
                        parent=parent,
                    )
                    symbols.append(sym)
                    body = child.child_by_field_name("body")
                    if body:
                        self._extract_from_node(body, source_code, file_path, symbols, parent=name)
                doc_lines = []

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
                        docstring=" ".join(doc_lines) if doc_lines else None,
                        parent=parent,
                    )
                    symbols.append(sym)
                    body = child.child_by_field_name("body")
                    if body:
                        self._extract_from_node(body, source_code, file_path, symbols, parent=name)
                doc_lines = []

            elif child.type in ("method_declaration", "constructor_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = source_code[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    sym = Symbol(
                        name=name,
                        type="function",
                        file=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1],
                        end_line=child.end_point[0] + 1,
                        docstring=" ".join(doc_lines) if doc_lines else None,
                        parent=parent,
                    )
                    symbols.append(sym)
                doc_lines = []

            elif child.type == "namespace_declaration":
                # Recurse into namespace body without emitting a symbol
                body = child.child_by_field_name("body")
                if body:
                    self._extract_from_node(body, source_code, file_path, symbols, parent=parent)
                doc_lines = []

            elif child.type == "using_directive":
                symbols.extend(self._extract_using(child, source_code, file_path))
                doc_lines = []

            elif child.is_named:
                doc_lines = []

    def _extract_using(self, node, source_code: bytes, file_path: str) -> List[Symbol]:
        """Extract imported names from using_directive."""
        imports: List[Symbol] = []
        for child in node.children:
            if child.type in ("identifier", "qualified_name"):
                full = source_code[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                name = full.rsplit(".", 1)[-1]
                imports.append(Symbol(
                    name=name,
                    type="import",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                ))
                break
        return imports

    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """C# XML doc comments are preceding siblings — handled in _extract_from_node."""
        return None
