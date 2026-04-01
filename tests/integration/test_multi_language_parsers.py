"""Integration tests for multi-language parsing."""

import pytest

from src.parsers.base_parser import BaseParser
from src.parsers.unified_parser import UnifiedParser
from src.parsers.symbol import Symbol


class TestBaseParser:
    """Test suite for BaseParser abstraction."""

    def test_supports_file(self):
        """Test file extension checking."""

        class MockParser(BaseParser):
            LANGUAGE = "mock"
            EXTENSIONS = [".mock"]

            def parse_file(self, file_path: str):
                return []

            def _extract_symbols(self, source_code: str, file_path: str):
                return []

        parser = MockParser()
        assert parser.supports_file("file.mock")
        assert not parser.supports_file("file.py")
        assert not parser.supports_file("file.go")

    def test_multiple_extensions(self):
        """Test parser supporting multiple extensions."""

        class MockParser(BaseParser):
            LANGUAGE = "mock"
            EXTENSIONS = [".a", ".b", ".c"]

            def parse_file(self, file_path: str):
                return []

            def _extract_symbols(self, source_code: str, file_path: str):
                return []

        parser = MockParser()
        assert parser.supports_file("file.a")
        assert parser.supports_file("file.b")
        assert parser.supports_file("file.c")
        assert not parser.supports_file("file.d")


class TestUnifiedParser:
    """Test suite for UnifiedParser."""

    def test_initialization(self):
        """Test unified parser initializes with available parsers."""
        parser = UnifiedParser()

        # Should have at least Python parser
        assert "py" in parser.parsers
        assert parser.parsers["py"] is not None

    def test_get_supported_extensions(self):
        """Test getting list of supported extensions."""
        parser = UnifiedParser()
        exts = parser.get_supported_extensions()

        # Should have Python at minimum
        assert ".py" in exts
        assert isinstance(exts, list)
        assert all(isinstance(e, str) for e in exts)

    def test_get_supported_languages(self):
        """Test getting list of supported languages."""
        parser = UnifiedParser()
        langs = parser.get_supported_languages()

        # Should have Python at minimum
        assert "python" in langs
        assert isinstance(langs, list)
        assert all(isinstance(l, str) for l in langs)

    def test_get_language_for_file(self):
        """Test language detection by file extension."""
        parser = UnifiedParser()

        assert parser.get_language_for_file("test.py") == "python"
        assert parser.get_language_for_file("unknown.xyz") is None

    def test_unsupported_file_type(self):
        """Test that unsupported files return empty symbols."""
        parser = UnifiedParser()
        symbols = parser.parse_file("test.unsupported")

        assert symbols == []

    def test_python_parser_fallback(self):
        """Test that Python parser is always available."""
        parser = UnifiedParser()

        assert "py" in parser.parsers
        python_parser = parser.parsers["py"]
        assert python_parser is not None
        # Python parser should support .py files
        assert parser.get_language_for_file("test.py") == "python"


class TestParserIntegration:
    """Integration tests for multi-language parsing workflow."""

    def test_multiple_languages_in_dict(self):
        """Test that multiple parser instances can coexist."""
        parser = UnifiedParser()

        # Verify we have multiple parser instances if available
        parsers_count = len(parser.parsers)
        assert parsers_count >= 1  # At least Python

    def test_file_extension_to_parser_mapping(self):
        """Test correct parser selection by extension."""
        parser = UnifiedParser()

        # Test Python
        py_parser = parser.parsers.get("py")
        assert py_parser is not None
        assert parser.get_language_for_file("test.py") == "python"

        # Test TypeScript if available
        ts_parser = parser.parsers.get("ts")
        if ts_parser:
            assert parser.get_language_for_file("test.ts") == "typescript"

        # Test Go if available
        go_parser = parser.parsers.get("go")
        if go_parser:
            assert parser.get_language_for_file("test.go") == "go"

        # Test Rust if available
        rs_parser = parser.parsers.get("rs")
        if rs_parser:
            assert parser.get_language_for_file("test.rs") == "rust"

        # Test Java if available
        java_parser = parser.parsers.get("java")
        if java_parser:
            assert parser.get_language_for_file("test.java") == "java"

    def test_parse_directory_returns_dict(self):
        """Test that parse_directory returns proper structure."""
        parser = UnifiedParser()

        # Parse a non-existent directory should return empty dict
        results = parser.parse_directory("/nonexistent/path")
        assert isinstance(results, dict)
        assert len(results) == 0

    def test_parse_file_error_handling(self):
        """Test error handling for parse_file."""
        parser = UnifiedParser()

        # Unsupported file extension should return empty list
        symbols = parser.parse_file("file.unsupported")
        assert isinstance(symbols, list)
        assert len(symbols) == 0


class TestParserAvailability:
    """Test availability of language parsers."""

    def test_python_always_available(self):
        """Test that Python parser is always available."""
        from src.parsers.unified_parser import UnifiedParser

        parser = UnifiedParser()
        assert "py" in parser.parsers
        assert parser.parsers["py"] is not None

    def test_graceful_fallback_for_unavailable_languages(self):
        """Test that missing language parsers don't crash initialization."""
        # Unified parser should initialize even if some parsers are unavailable
        parser = UnifiedParser()
        assert parser is not None
        assert len(parser.parsers) >= 1  # At least Python

    def test_go_parser_optional(self):
        """Test Go parser is optional."""
        from src.parsers.unified_parser import GoParser

        # This might be None if tree-sitter-go is not installed
        assert GoParser is None or callable(GoParser)

    def test_rust_parser_optional(self):
        """Test Rust parser is optional."""
        from src.parsers.unified_parser import RustParser

        # This might be None if tree-sitter-rust is not installed
        assert RustParser is None or callable(RustParser)

    def test_java_parser_optional(self):
        """Test Java parser is optional."""
        from src.parsers.unified_parser import JavaParser

        # This might be None if tree-sitter-java is not installed
        assert JavaParser is None or callable(JavaParser)
