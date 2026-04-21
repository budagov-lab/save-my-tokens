"""Base parser class for language-agnostic parsing."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from loguru import logger

from src.parsers.symbol import Symbol


class BaseParser(ABC):
    """Abstract base class for language-specific parsers."""

    LANGUAGE: str = ""  # Set in subclass (e.g., "python", "typescript")
    EXTENSIONS: List[str] = []  # Supported file extensions (e.g., [".py"])

    def __init__(self, base_path: str = ""):
        """Initialize parser.

        Args:
            base_path: Root directory for resolving imports/modules
        """
        self.base_path = Path(base_path)

    @abstractmethod
    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse a file and extract symbols.

        Args:
            file_path: Path to file to parse

        Returns:
            List of symbols found in file
        """
        pass

    @abstractmethod
    def _extract_symbols(
        self, source_code: str, file_path: str
    ) -> List[Symbol]:
        """Extract symbols from source code.

        Subclasses override this with language-specific logic.

        Args:
            source_code: Source code text
            file_path: Path to file (for debugging)

        Returns:
            List of symbols
        """
        pass

    @abstractmethod
    def _get_docstring(self, node, source_code: bytes) -> Optional[str]:
        """Extract docstring/JSDoc for a node.

        Language-specific implementation: Python uses triple-quotes,
        TypeScript uses JSDoc comments, etc.

        Args:
            node: Tree-sitter node
            source_code: Source code bytes

        Returns:
            Docstring text, or None if not found
        """
        pass

    def _get_child_text(
        self, node, field_name: str, source_code: bytes
    ) -> Optional[str]:
        """Get text of child node by field name.

        Args:
            node: Tree-sitter node
            field_name: Field name (e.g., "name")
            source_code: Source code bytes

        Returns:
            Child node text, or None if not found
        """
        child = node.child_by_field_name(field_name)
        if child:
            return source_code[child.start_byte : child.end_byte].decode("utf-8")
        return None

    def _make_symbol(
        self,
        node,
        symbol_type: str,
        source_code: bytes,
        file_path: str,
        parent: Optional[str] = None,
    ) -> Optional[Symbol]:
        """Create a Symbol from a tree-sitter node.

        Args:
            node: Tree-sitter node
            symbol_type: Symbol type (e.g., "function", "class")
            source_code: Source code bytes
            file_path: File path
            parent: Parent symbol name (e.g., class name for methods)

        Returns:
            Symbol object, or None if the node has no name field.
        """
        name = self._get_child_text(node, "name", source_code)
        if name is None:
            logger.warning(
                f"No 'name' field on {node.type} node at {file_path}:{node.start_point[0] + 1} — skipping"
            )
            return None
        docstring = self._get_docstring(node, source_code)

        return Symbol(
            name=name,
            type=symbol_type,
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            parent=parent,
        )

    def supports_file(self, file_path: str) -> bool:
        """Check if this parser supports the file.

        Args:
            file_path: Path to check

        Returns:
            True if parser can handle this file
        """
        for ext in self.EXTENSIONS:
            if file_path.endswith(ext):
                return True
        return False

    def _read_file(self, file_path: str) -> Optional[str]:
        """Read file contents.

        Args:
            file_path: Path to file

        Returns:
            File contents, or None if read fails
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return None

    def _log_parsing(self, file_path: str, symbol_count: int) -> None:
        """Log parsing result.

        Args:
            file_path: File that was parsed
            symbol_count: Number of symbols extracted
        """
        logger.debug(f"Parsed {file_path}: {symbol_count} symbols ({self.LANGUAGE})")
