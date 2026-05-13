"""Tests for C# parser."""

import tempfile
from pathlib import Path

import pytest

try:
    from src.parsers.csharp_parser import CSharpParser
    from src.parsers.symbol import Symbol

    HAS_CSHARP_PARSER = True
except ImportError:
    HAS_CSHARP_PARSER = False
    pytestmark = pytest.mark.skip(reason="tree-sitter-c-sharp not installed")


@pytest.fixture
def temp_cs_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", delete=False, encoding="utf-8") as f:
        f.write(
            """\
using System;
using System.Collections.Generic;

namespace MyApp.Services
{
    /// <summary>Manages users.</summary>
    public class UserService
    {
        public UserService(string name) {}

        /// <summary>Fetch a user.</summary>
        public string GetUser(int id)
        {
            return id.ToString();
        }

        private void Helper() {}
    }

    public interface IRepository
    {
        void Save();
    }

    public enum Status { Active, Inactive }

    public record Person(string Name, int Age);

    public struct Point { public int X; }
}
"""
        )
        f.flush()
        yield f.name
    Path(f.name).unlink()


@pytest.fixture
def parser():
    return CSharpParser()


class TestCSharpParserBasics:
    def test_language_and_extensions(self):
        p = CSharpParser()
        assert p.LANGUAGE == "csharp"
        assert ".cs" in p.EXTENSIONS

    def test_supports_cs_files(self):
        p = CSharpParser()
        assert p.supports_file("foo.cs")
        assert not p.supports_file("foo.py")
        assert not p.supports_file("foo.java")

    def test_missing_file_raises(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.cs")


class TestCSharpParserSymbols:
    def test_extracts_class(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        classes = [s for s in symbols if s.type == "class"]
        names = [s.name for s in classes]
        assert "UserService" in names

    def test_extracts_interface(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        ifaces = [s for s in symbols if s.type == "interface"]
        assert any(s.name == "IRepository" for s in ifaces)

    def test_extracts_methods(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "GetUser" in names
        assert "Helper" in names

    def test_extracts_constructor(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        funcs = [s for s in symbols if s.type == "function"]
        assert any(s.name == "UserService" for s in funcs)

    def test_extracts_enum_as_class(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        classes = [s for s in symbols if s.type == "class"]
        assert any(s.name == "Status" for s in classes)

    def test_extracts_record_as_class(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        classes = [s for s in symbols if s.type == "class"]
        assert any(s.name == "Person" for s in classes)

    def test_extracts_struct_as_class(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        classes = [s for s in symbols if s.type == "class"]
        assert any(s.name == "Point" for s in classes)

    def test_extracts_imports(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        imports = [s for s in symbols if s.type == "import"]
        names = [s.name for s in imports]
        assert "System" in names
        assert "Generic" in names

    def test_parent_set_for_methods(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        get_user = next(s for s in symbols if s.name == "GetUser")
        assert get_user.parent == "UserService"

    def test_xml_docstring_extracted(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        service = next(s for s in symbols if s.name == "UserService")
        assert service.docstring == "Manages users."

    def test_method_docstring_extracted(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        get_user = next(s for s in symbols if s.name == "GetUser")
        assert get_user.docstring == "Fetch a user."

    def test_line_numbers_are_positive(self, parser, temp_cs_file):
        symbols = parser.parse_file(temp_cs_file)
        for s in symbols:
            assert s.line >= 1


class TestCSharpParserFileScopedNamespace:
    def test_file_scoped_namespace(self, parser):
        code = "namespace App;\npublic class Foo {\n    public void Bar() {}\n}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", delete=False, encoding="utf-8") as f:
            f.write(code)
            fname = f.name
        try:
            symbols = parser.parse_file(fname)
            names = [s.name for s in symbols]
            assert "Foo" in names
            assert "Bar" in names
        finally:
            Path(fname).unlink()


class TestCSharpParserNestedTypes:
    def test_nested_class(self, parser):
        code = "class Outer {\n    public class Inner {\n        public void M() {}\n    }\n}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", delete=False, encoding="utf-8") as f:
            f.write(code)
            fname = f.name
        try:
            symbols = parser.parse_file(fname)
            inner = next((s for s in symbols if s.name == "Inner"), None)
            assert inner is not None
            assert inner.parent == "Outer"
            m = next((s for s in symbols if s.name == "M"), None)
            assert m is not None
            assert m.parent == "Inner"
        finally:
            Path(fname).unlink()
