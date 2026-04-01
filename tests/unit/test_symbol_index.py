"""Unit tests for symbol index."""

import pytest

from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def index():
    """Create an empty symbol index."""
    return SymbolIndex()


@pytest.fixture
def sample_symbols():
    """Create sample symbols."""
    return [
        Symbol("greet", "function", "test.py", 1, 0, docstring="Greet"),
        Symbol("add", "function", "test.py", 5, 4, parent="Calculator"),
        Symbol("multiply", "function", "test.py", 8, 4, parent="Calculator"),
        Symbol("Calculator", "class", "test.py", 4, 0),
        Symbol("validate", "function", "utils.py", 1, 0),
        Symbol("os", "import", "test.py", 10, 0),
    ]


def test_add_single_symbol(index):
    """Test adding a single symbol."""
    sym = Symbol("test", "function", "test.py", 1, 0)
    index.add(sym)

    assert len(index) == 1
    assert index.get_by_name("test") == [sym]


def test_add_multiple_symbols(index, sample_symbols):
    """Test adding multiple symbols."""
    index.add_all(sample_symbols)

    assert len(index) == len(sample_symbols)


def test_get_by_name(index, sample_symbols):
    """Test getting symbols by name."""
    index.add_all(sample_symbols)

    greets = index.get_by_name("greet")
    assert len(greets) == 1
    assert greets[0].type == "function"

    # Multiple symbols with same name
    adds = index.get_by_name("add")
    assert len(adds) == 1


def test_get_by_qualified_name(index, sample_symbols):
    """Test getting symbol by qualified name."""
    index.add_all(sample_symbols)

    calc_add = index.get_by_qualified_name("Calculator.add")
    assert calc_add is not None
    assert calc_add.name == "add"
    assert calc_add.parent == "Calculator"


def test_get_by_file(index, sample_symbols):
    """Test getting symbols by file."""
    index.add_all(sample_symbols)

    test_py_symbols = index.get_by_file("test.py")
    assert len(test_py_symbols) == 5

    utils_py_symbols = index.get_by_file("utils.py")
    assert len(utils_py_symbols) == 1


def test_find_symbol(index, sample_symbols):
    """Test finding a symbol."""
    index.add_all(sample_symbols)

    # Find by name only
    sym = index.find("greet")
    assert sym is not None
    assert sym.name == "greet"

    # Find by name and file
    sym = index.find("validate", "utils.py")
    assert sym is not None
    assert sym.file == "utils.py"


def test_find_symbol_not_found(index):
    """Test finding non-existent symbol."""
    sym = index.find("nonexistent")
    assert sym is None


def test_get_functions(index, sample_symbols):
    """Test getting all functions."""
    index.add_all(sample_symbols)

    functions = index.get_functions()
    assert len(functions) == 4
    assert all(s.type == "function" for s in functions)


def test_get_classes(index, sample_symbols):
    """Test getting all classes."""
    index.add_all(sample_symbols)

    classes = index.get_classes()
    assert len(classes) == 1
    assert classes[0].name == "Calculator"


def test_get_imports(index, sample_symbols):
    """Test getting all imports."""
    index.add_all(sample_symbols)

    imports = index.get_imports()
    assert len(imports) == 1
    assert imports[0].name == "os"


def test_search_by_prefix(index, sample_symbols):
    """Test prefix search."""
    index.add_all(sample_symbols)

    # Names starting with 'a'
    results = index.search_by_prefix("a")
    assert len(results) == 1
    assert results[0].name == "add"

    # Names starting with 'v'
    results = index.search_by_prefix("v")
    assert len(results) == 1
    assert results[0].name == "validate"


def test_get_methods_of_class(index, sample_symbols):
    """Test getting methods of a class."""
    index.add_all(sample_symbols)

    methods = index.get_methods_of_class("Calculator")
    assert len(methods) == 2
    names = {m.name for m in methods}
    assert names == {"add", "multiply"}


def test_get_duplicates(index):
    """Test getting duplicate names."""
    # Add symbols with same name
    sym1 = Symbol("test", "function", "file1.py", 1, 0)
    sym2 = Symbol("test", "function", "file2.py", 1, 0)
    sym3 = Symbol("unique", "function", "file1.py", 5, 0)

    index.add_all([sym1, sym2, sym3])

    duplicates = index.get_duplicates()
    assert "test" in duplicates
    assert len(duplicates["test"]) == 2
    assert "unique" not in duplicates


def test_get_all(index, sample_symbols):
    """Test getting all symbols."""
    index.add_all(sample_symbols)

    all_symbols = index.get_all()
    assert len(all_symbols) == len(sample_symbols)


def test_repr(index, sample_symbols):
    """Test string representation."""
    index.add_all(sample_symbols)

    repr_str = repr(index)
    assert "6 symbols" in repr_str
    assert "2 files" in repr_str
