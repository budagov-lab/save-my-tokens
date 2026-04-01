"""Base parser class for language-agnostic parsing."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from loguru import logger

from src.parsers.symbol import Symbol


class BaseParser(ABC):
    """Abstract base class for language-specific parsers."""

    LANGUAGE: str = ""  # Set in subclass (e.g., "python", "go", "rust")
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
