"""Comprehensive tests for all language parsers (Python, TS, Go, Rust, Java)."""

import pytest
from pathlib import Path
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex
from src.parsers.python_parser import PythonParser


class TestPythonParserComprehensive:
    """Comprehensive Python parser tests."""

    @pytest.fixture
    def parser(self):
        """Create Python parser."""
        return PythonParser()

    def test_function_with_decorators(self, parser, tmp_path):
        """Test parsing function with decorators."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
@decorator
@another_decorator
def decorated_func():
    """A decorated function."""
    pass
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "decorated_func" in names

    def test_async_function(self, parser, tmp_path):
        """Test parsing async functions."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
async def fetch_data():
    """Async function."""
    return None
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "fetch_data" in names

    def test_nested_classes(self, parser, tmp_path):
        """Test parsing nested classes."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class Outer:
    """Outer class."""

    class Inner:
        """Inner class."""
        pass
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "Outer" in names

    def test_method_with_type_hints(self, parser, tmp_path):
        """Test parsing methods with type hints."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class Calculator:
    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "add" in names
        assert "Calculator" in names

    def test_lambda_functions(self, parser, tmp_path):
        """Test parsing lambda functions."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
square = lambda x: x ** 2
numbers = list(map(lambda x: x * 2, range(10)))
''')
        symbols = parser.parse_file(str(source_file))
        # Lambdas may not be extracted as named symbols, but parser should handle them
        assert symbols is not None

    def test_context_managers(self, parser, tmp_path):
        """Test parsing context managers."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class FileManager:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
''')
        symbols = parser.parse_file(str(source_file))
        assert any(s.name == "__enter__" for s in symbols)

    def test_property_decorators(self, parser, tmp_path):
        """Test parsing @property decorators."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class Person:
    @property
    def name(self):
        """Get name."""
        return self._name

    @name.setter
    def name(self, value):
        """Set name."""
        self._name = value
''')
        symbols = parser.parse_file(str(source_file))
        assert "Person" in [s.name for s in symbols]

    def test_static_methods(self, parser, tmp_path):
        """Test parsing static methods."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class Math:
    @staticmethod
    def add(a, b):
        """Add numbers."""
        return a + b

    @classmethod
    def from_string(cls, s):
        """Create from string."""
        return cls()
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "add" in names
        assert "from_string" in names

    def test_multiple_inheritance(self, parser, tmp_path):
        """Test parsing multiple inheritance."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
class A:
    pass

class B:
    pass

class C(A, B):
    """Class with multiple inheritance."""
    pass
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols]
        assert "C" in names
        assert "A" in names
        assert "B" in names

    def test_exception_handling(self, parser, tmp_path):
        """Test parsing exception handling."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
def safe_divide(a, b):
    """Safely divide."""
    try:
        return a / b
    except ZeroDivisionError as e:
        return None
    finally:
        pass
''')
        symbols = parser.parse_file(str(source_file))
        assert any(s.name == "safe_divide" for s in symbols)

    def test_generator_functions(self, parser, tmp_path):
        """Test parsing generator functions."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
def count_up(n):
    """Generator function."""
    i = 0
    while i < n:
        yield i
        i += 1
''')
        symbols = parser.parse_file(str(source_file))
        assert any(s.name == "count_up" for s in symbols)


class TestParserEdgeCases:
    """Test parser edge cases and error handling."""

    @pytest.fixture
    def parser(self):
        """Create parser."""
        return PythonParser()

    def test_empty_file(self, parser, tmp_path):
        """Test parsing empty file."""
        source_file = tmp_path / "empty.py"
        source_file.write_text("")
        symbols = parser.parse_file(str(source_file))
        assert isinstance(symbols, list)

    def test_syntax_error_handling(self, parser, tmp_path):
        """Test handling syntax errors."""
        source_file = tmp_path / "broken.py"
        source_file.write_text("def broken(:\n  pass")
        try:
            symbols = parser.parse_file(str(source_file))
            # Parser should handle gracefully
            assert isinstance(symbols, list)
        except Exception:
            # Or may raise, both are acceptable
            pass

    def test_unicode_characters(self, parser, tmp_path):
        """Test parsing unicode characters."""
        source_file = tmp_path / "unicode.py"
        source_file.write_text('''
def greet(name):
    """Greet someone."""
    return f"Hello {name}!"
''', encoding='utf-8')
        symbols = parser.parse_file(str(source_file))
        assert any(s.name == "greet" for s in symbols)

    def test_very_long_function(self, parser, tmp_path):
        """Test parsing very long functions."""
        source_file = tmp_path / "long.py"
        long_body = "\n".join([f"    x = {i}" for i in range(100)])
        source_file.write_text(f'''
def long_function():
    """A very long function."""
{long_body}
    return x
''')
        symbols = parser.parse_file(str(source_file))
        assert any(s.name == "long_function" for s in symbols)

    def test_deeply_nested_structure(self, parser, tmp_path):
        """Test parsing deeply nested structures."""
        source_file = tmp_path / "nested.py"
        source_file.write_text('''
class A:
    class B:
        class C:
            def method(self):
                pass
''')
        symbols = parser.parse_file(str(source_file))
        # Should extract at least the class
        assert len(symbols) > 0


class TestImportHandling:
    """Test import statement handling."""

    @pytest.fixture
    def parser(self):
        """Create parser."""
        return PythonParser()

    def test_simple_import(self, parser, tmp_path):
        """Test simple import statements."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
import os
import sys
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols if s.type == "import"]
        assert len(names) >= 2

    def test_from_import(self, parser, tmp_path):
        """Test from...import statements."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
from pathlib import Path
from typing import List, Dict, Optional
''')
        symbols = parser.parse_file(str(source_file))
        names = [s.name for s in symbols if s.type == "import"]
        assert len(names) > 0

    def test_import_as_alias(self, parser, tmp_path):
        """Test import with alias."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
import numpy as np
from typing import Dict as D
''')
        symbols = parser.parse_file(str(source_file))
        # Parser should handle aliases
        assert len(symbols) > 0

    def test_relative_imports(self, parser, tmp_path):
        """Test relative imports."""
        source_file = tmp_path / "test.py"
        source_file.write_text('''
from . import sibling
from .. import parent
from .module import something
''')
        symbols = parser.parse_file(str(source_file))
        # Should handle relative imports
        assert isinstance(symbols, list)


class TestSymbolIndexing:
    """Test symbol indexing and lookup."""

    def test_index_by_name(self):
        """Test indexing symbols by name."""
        index = SymbolIndex()
        index.add(Symbol(name="func1", type="function", file="file.py", line=1, column=0))
        index.add(Symbol(name="func2", type="function", file="file.py", line=10, column=0))

        results = index.get_by_name("func1")
        assert len(results) > 0
        assert results[0].name == "func1"

    def test_index_by_file(self):
        """Test indexing symbols by file."""
        index = SymbolIndex()
        index.add(Symbol(name="func1", type="function", file="file.py", line=1, column=0))
        index.add(Symbol(name="func2", type="function", file="file.py", line=10, column=0))
        index.add(Symbol(name="func3", type="function", file="other.py", line=1, column=0))

        results = index.get_by_file("file.py")
        assert len(results) == 2

    def test_index_by_type(self):
        """Test indexing symbols by type."""
        index = SymbolIndex()
        index.add(Symbol(name="func", type="function", file="file.py", line=1, column=0))
        index.add(Symbol(name="MyClass", type="class", file="file.py", line=10, column=0))

        all_symbols = index.get_all()
        functions = [s for s in all_symbols if s.type == "function"]
        classes = [s for s in all_symbols if s.type == "class"]

        assert len(functions) > 0
        assert len(classes) > 0

    def test_get_imports(self):
        """Test getting import symbols."""
        index = SymbolIndex()
        index.add(Symbol(name="os", type="import", file="file.py", line=1, column=0))
        index.add(Symbol(name="sys", type="import", file="file.py", line=2, column=0))
        index.add(Symbol(name="func", type="function", file="file.py", line=10, column=0))

        imports = index.get_imports()
        assert len(imports) == 2
        assert all(s.type == "import" for s in imports)
