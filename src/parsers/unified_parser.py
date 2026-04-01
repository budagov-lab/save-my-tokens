"""Unified parser that auto-detects language and dispatches to appropriate parser."""

from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.python_parser import PythonParser
from src.parsers.symbol import Symbol

# Import other parsers with graceful fallback
try:
    from src.parsers.typescript_parser import TypeScriptParser
except ImportError:
    TypeScriptParser = None

try:
    from src.parsers.go_parser import GoParser
except ImportError:
    GoParser = None

try:
    from src.parsers.rust_parser import RustParser
except ImportError:
    RustParser = None

try:
    from src.parsers.java_parser import JavaParser
except ImportError:
    JavaParser = None


class UnifiedParser:
    """Auto-detect language and dispatch to appropriate parser."""

    def __init__(self, base_path: str = ""):
        """Initialize unified parser with all available language parsers.

        Args:
            base_path: Root directory for resolving imports/modules
        """
        self.base_path = Path(base_path)
        self.parsers: Dict[str, BaseParser] = {}

        # Initialize available parsers
        self.parsers["py"] = PythonParser(str(base_path))

        if TypeScriptParser:
            self.parsers["ts"] = TypeScriptParser(str(base_path))
            self.parsers["tsx"] = TypeScriptParser(str(base_path))
            self.parsers["js"] = TypeScriptParser(str(base_path))
            self.parsers["jsx"] = TypeScriptParser(str(base_path))
        else:
            logger.warning("TypeScript parser not available")

        if GoParser:
            self.parsers["go"] = GoParser(str(base_path))
        else:
            logger.warning("Go parser not available")

        if RustParser:
            self.parsers["rs"] = RustParser(str(base_path))
        else:
            logger.warning("Rust parser not available")

        if JavaParser:
            self.parsers["java"] = JavaParser(str(base_path))
        else:
            logger.warning("Java parser not available")

        logger.info(
            f"Unified parser initialized with {len(self.parsers)} language(s): "
            f"{', '.join(sorted(self.parsers.keys()))}"
        )

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Auto-detect language and parse file.

        Args:
            file_path: Path to file to parse

        Returns:
            List of symbols found in file
        """
        # Get file extension
        ext = Path(file_path).suffix.lstrip(".")

        # Check if we have a parser for this extension
        if ext not in self.parsers:
            logger.warning(f"No parser available for .{ext} files ({file_path})")
            return []

        parser = self.parsers[ext]
        return parser.parse_file(file_path)

    def parse_directory(self, directory: str) -> Dict[str, List[Symbol]]:
        """Parse all source files in directory.

        Args:
            directory: Directory to scan

        Returns:
            Dict mapping file paths to their symbols
        """
        results = {}
        dir_path = Path(directory)

        if not dir_path.is_dir():
            logger.warning(f"Directory not found: {directory}")
            return results

        # Supported extensions
        supported_exts = set(self.parsers.keys())
        extensions = [f".{ext}" for ext in supported_exts]

        # Find all source files
        for file_path in dir_path.rglob("*"):
            # Skip hidden files and common non-source directories
            if file_path.is_file() and file_path.suffix in extensions:
                # Skip .git, node_modules, __pycache__, etc.
                parts = file_path.parts
                if any(part.startswith(".") for part in parts):
                    continue
                if "node_modules" in parts or "__pycache__" in parts:
                    continue

                # Parse file
                symbols = self.parse_file(str(file_path))
                if symbols:
                    results[str(file_path)] = symbols

        logger.info(
            f"Parsed {len(results)} files from {directory} "
            f"({sum(len(s) for s in results.values())} total symbols)"
        )
        return results

    def get_language_for_file(self, file_path: str) -> Optional[str]:
        """Get the language name for a file.

        Args:
            file_path: Path to file

        Returns:
            Language name (e.g., "python", "go", "rust"), or None if unsupported
        """
        ext = Path(file_path).suffix.lstrip(".")

        if ext not in self.parsers:
            return None

        parser = self.parsers[ext]

        # Map extension to language name
        language_map = {
            "py": "python",
            "ts": "typescript",
            "tsx": "typescript",
            "js": "typescript",
            "jsx": "typescript",
            "go": "go",
            "rs": "rust",
            "java": "java",
        }

        return language_map.get(ext)

    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions.

        Returns:
            List of extensions (e.g., [".py", ".go", ".rs"])
        """
        return [f".{ext}" for ext in sorted(self.parsers.keys())]

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages.

        Returns:
            List of language names
        """
        language_map = {
            "py": "python",
            "ts": "typescript",
            "tsx": "typescript",
            "js": "typescript",
            "jsx": "typescript",
            "go": "go",
            "rs": "rust",
            "java": "java",
        }

        languages = []
        for ext in self.parsers.keys():
            lang = language_map.get(ext)
            if lang and lang not in languages:
                languages.append(lang)

        return sorted(languages)
