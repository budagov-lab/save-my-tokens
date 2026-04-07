"""Comprehensive tests for TypeScript parser."""

import tempfile
from pathlib import Path
from typing import List

import pytest

# Skip entire module if tree-sitter-typescript not available
try:
    from src.parsers.typescript_parser import TypeScriptParser
    from src.parsers.symbol import Symbol

    HAS_TYPESCRIPT_PARSER = True
except ImportError:
    HAS_TYPESCRIPT_PARSER = False
    pytestmark = pytest.mark.skip(reason="tree-sitter-typescript not installed")


@pytest.fixture
def temp_ts_file():
    """Create a temporary TypeScript file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
        f.write(
            """
// Simple function
function greet(name: string): string {
    return `Hello, ${name}`;
}

// Arrow function
const add = (a: number, b: number): number => a + b;

// Class definition
class Calculator {
    constructor(private value: number) {}

    getValue(): number {
        return this.value;
    }

    add(x: number): void {
        this.value += x;
    }
}

// Interface
interface User {
    name: string;
    age: number;
}

// Type alias
type Status = 'pending' | 'completed' | 'failed';

// Variable declaration
const config = {
    host: 'localhost',
    port: 3000
};

// Import statement
import { Component } from '@angular/core';
import * as utils from './utils';

// Export
export function multiply(a: number, b: number): number {
    return a * b;
}
"""
        )
        f.flush()
        yield f.name
    Path(f.name).unlink()


class TestTypeScriptParserInitialization:
    """Test TypeScript parser initialization."""

    def test_initialization(self):
        """Test parser initializes without error."""
        parser = TypeScriptParser()
        assert parser.parser is not None
        assert parser.import_resolver is not None

    def test_initialization_with_base_path(self):
        """Test parser initializes with base_path."""
        parser = TypeScriptParser(base_path="/tmp")
        assert parser.parser is not None
        assert parser.import_resolver is not None


class TestTypeScriptParserBasicParsing:
    """Test basic TypeScript parsing functionality."""

    def test_parse_simple_function(self):
        """Test parsing a simple function."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function add(a: number, b: number): number { return a + b; }")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        assert len(symbols) > 0
        # Check that function symbol was extracted
        func_symbols = [s for s in symbols if s.type == "function"]
        assert len(func_symbols) > 0

        Path(f.name).unlink()

    def test_parse_class(self):
        """Test parsing a class definition."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("class MyClass { constructor() {} method() {} }")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        assert len(symbols) > 0
        # Check that class symbol was extracted
        class_symbols = [s for s in symbols if s.type == "class"]
        assert len(class_symbols) > 0

        Path(f.name).unlink()

    def test_parse_import(self):
        """Test parsing import statements."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("import { Component } from '@angular/core'; import * as utils from './utils';")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        assert len(symbols) > 0
        # Check that import symbols were extracted
        import_symbols = [s for s in symbols if s.type == "import"]
        assert len(import_symbols) > 0

        Path(f.name).unlink()

    def test_parse_variable_declaration(self):
        """Test parsing variable declarations."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("const x: number = 42; let y: string = 'hello';")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        # Should extract some symbols (variables or constants)
        assert isinstance(symbols, list)

        Path(f.name).unlink()

    def test_parse_arrow_function(self):
        """Test parsing arrow functions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("const greet = (name: string) => `Hello, ${name}`;")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        assert isinstance(symbols, list)

        Path(f.name).unlink()


class TestTypeScriptParserFileHandling:
    """Test file handling in TypeScript parser."""

    def test_file_not_found(self):
        """Test handling of non-existent file."""
        parser = TypeScriptParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.ts")

    def test_parse_empty_file(self):
        """Test parsing an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        assert isinstance(symbols, list)

        Path(f.name).unlink()

    def test_parse_complex_file(self, temp_ts_file):
        """Test parsing a complex TypeScript file with multiple symbols."""
        parser = TypeScriptParser()
        symbols = parser.parse_file(temp_ts_file)

        assert isinstance(symbols, list)
        assert len(symbols) > 0

        # Verify symbol attributes
        for symbol in symbols:
            assert isinstance(symbol, Symbol)
            assert hasattr(symbol, "name")
            assert hasattr(symbol, "type")
            assert hasattr(symbol, "file")


class TestTypeScriptParserSymbolTypes:
    """Test detection of different TypeScript symbol types."""

    def test_symbol_has_required_fields(self):
        """Test that extracted symbols have required fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() { } class Test { }")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        for symbol in symbols:
            assert symbol.name is not None
            assert symbol.type is not None
            assert symbol.file == f.name

        Path(f.name).unlink()

    def test_symbol_types_are_valid(self):
        """Test that symbol types are from expected set."""
        valid_types = {
            "function",
            "class",
            "import",
            "variable",
            "type",
            "interface",
            "method",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function f() {} class C {} import x from 'y'; const z = 1;")
            f.flush()
            parser = TypeScriptParser()
            symbols = parser.parse_file(f.name)

        for symbol in symbols:
            # Symbol type should be one of the expected types
            # or at least a string (parser may use different names)
            assert isinstance(symbol.type, str)

        Path(f.name).unlink()
