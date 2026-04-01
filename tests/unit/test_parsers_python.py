"""Unit tests for Python parser."""

import pytest

from src.parsers.python_parser import PythonParser
from src.parsers.symbol import Symbol


@pytest.fixture
def parser():
    """Create parser instance."""
    return PythonParser()


@pytest.fixture
def sample_file(tmp_path):
    """Create sample Python file."""
    code = '''"""Module docstring."""

def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!"

class Calculator:
    """Simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

def helper():
    """Helper function."""
    pass

import os
from typing import Dict, List
from module import func
'''
    file_path = tmp_path / "test.py"
    file_path.write_text(code)
    return str(file_path)


def test_extract_function(parser, sample_file):
    """Test function extraction."""
    symbols = parser.parse_file(sample_file)
    functions = [s for s in symbols if s.type == "function"]

    assert len(functions) >= 4
    assert any(s.name == "greet" for s in functions)
    assert any(s.name == "helper" for s in functions)
    assert any(s.name == "add" for s in functions)
    assert any(s.name == "multiply" for s in functions)


def test_extract_class(parser, sample_file):
    """Test class extraction."""
    symbols = parser.parse_file(sample_file)
    classes = [s for s in symbols if s.type == "class"]

    assert len(classes) >= 1
    assert any(s.name == "Calculator" for s in classes)


def test_extract_imports(parser, sample_file):
    """Test import extraction."""
    symbols = parser.parse_file(sample_file)
    imports = [s for s in symbols if s.type == "import"]

    assert len(imports) >= 3
    # Should find os, Dict, List, func imports
    import_names = [s.name for s in imports]
    assert any("os" in name for name in import_names)
    assert any("Dict" in name or "List" in name for name in import_names)


def test_method_parent(parser, sample_file):
    """Test that methods have parent class set."""
    symbols = parser.parse_file(sample_file)
    methods = [s for s in symbols if s.type == "function" and s.parent == "Calculator"]

    assert len(methods) == 2
    assert any(s.name == "add" for s in methods)
    assert any(s.name == "multiply" for s in methods)


def test_docstring_extraction(parser, sample_file):
    """Test docstring extraction."""
    symbols = parser.parse_file(sample_file)
    greet = next((s for s in symbols if s.name == "greet"), None)

    assert greet is not None
    assert greet.docstring == "Greet a person."


def test_symbol_qualified_name(parser, sample_file):
    """Test qualified name generation."""
    symbols = parser.parse_file(sample_file)
    add_method = next((s for s in symbols if s.name == "add"), None)

    assert add_method is not None
    assert add_method.qualified_name == "Calculator.add"


def test_symbol_hash_and_equality():
    """Test Symbol hash and equality."""
    sym1 = Symbol(
        name="test", type="function", file="test.py", line=1, column=0
    )
    sym2 = Symbol(
        name="test", type="function", file="test.py", line=1, column=0
    )

    assert sym1 == sym2
    assert hash(sym1) == hash(sym2)


def test_parse_empty_file(parser, tmp_path):
    """Test parsing empty file."""
    file_path = tmp_path / "empty.py"
    file_path.write_text("")

    symbols = parser.parse_file(str(file_path))
    assert symbols == []


def test_parse_nonexistent_file(parser):
    """Test parsing nonexistent file."""
    with pytest.raises(FileNotFoundError):
        parser.parse_file("/nonexistent/file.py")
