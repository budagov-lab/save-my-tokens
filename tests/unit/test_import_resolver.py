"""Unit tests for import resolver."""

import pytest

from src.parsers.import_resolver import ImportResolver


@pytest.fixture
def resolver():
    """Create resolver instance."""
    return ImportResolver()


class TestExtractImportNames:
    """Test extracting imported names from statements."""

    def test_simple_import(self):
        """Test simple import statement."""
        statement = "import os"
        names = ImportResolver.extract_import_names(statement)
        assert names == ["os"]

    def test_multiple_imports(self):
        """Test importing multiple modules."""
        statement = "import os, sys, json"
        names = ImportResolver.extract_import_names(statement)
        assert "os" in names
        assert "sys" in names
        assert "json" in names

    def test_from_import(self):
        """Test from X import Y format."""
        statement = "from typing import Dict, List"
        names = ImportResolver.extract_import_names(statement)
        assert "Dict" in names
        assert "List" in names

    def test_star_import(self):
        """Test star imports."""
        statement = "from module import *"
        names = ImportResolver.extract_import_names(statement)
        assert names == ["*"]

    def test_aliased_import(self):
        """Test as alias imports."""
        statement = "import numpy as np"
        names = ImportResolver.extract_import_names(statement)
        assert "np" in names

    def test_from_import_with_alias(self):
        """Test from import with alias."""
        statement = "from typing import Dict as D, List as L"
        names = ImportResolver.extract_import_names(statement)
        assert "D" in names
        assert "L" in names

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        statement = "  from   typing   import   Dict  ,  List  "
        names = ImportResolver.extract_import_names(statement)
        assert "Dict" in names
        assert "List" in names


class TestRelativeImports:
    """Test resolving relative imports."""

    def test_simple_relative_import(self, resolver):
        """Test simple relative import."""
        resolved = resolver.resolve_python_import("config", "src/utils/helpers.py")
        assert resolved == "config"

    def test_parent_relative_import(self, resolver):
        """Test parent directory relative import."""
        resolved = resolver.resolve_python_import(".config", "src/utils/helpers.py")
        # One dot means current package
        assert "config" in resolved

    def test_grandparent_relative_import(self, resolver):
        """Test grandparent directory relative import."""
        resolved = resolver.resolve_python_import("..config", "src/utils/helpers.py")
        # Two dots means parent package
        assert "config" in resolved

    def test_typescript_relative_import(self, resolver):
        """Test TypeScript relative import."""
        resolved = resolver.resolve_typescript_import("./utils", "src/helpers/index.ts")
        assert "utils" in resolved

    def test_typescript_parent_import(self, resolver):
        """Test TypeScript parent import."""
        resolved = resolver.resolve_typescript_import("../config", "src/utils/index.ts")
        assert "config" in resolved


class TestStdlibDetection:
    """Test standard library detection."""

    def test_stdlib_modules(self):
        """Test detection of stdlib modules."""
        assert ImportResolver.is_stdlib_import("os")
        assert ImportResolver.is_stdlib_import("sys")
        assert ImportResolver.is_stdlib_import("json")
        assert ImportResolver.is_stdlib_import("typing")

    def test_nested_stdlib(self):
        """Test nested stdlib imports."""
        assert ImportResolver.is_stdlib_import("typing.Dict")
        assert ImportResolver.is_stdlib_import("os.path")

    def test_third_party_modules(self):
        """Test non-stdlib modules."""
        assert not ImportResolver.is_stdlib_import("requests")
        assert not ImportResolver.is_stdlib_import("numpy")
        assert not ImportResolver.is_stdlib_import("django")

    def test_local_imports(self):
        """Test local module detection."""
        assert not ImportResolver.is_stdlib_import("config")
        assert not ImportResolver.is_stdlib_import("utils.helpers")
