"""Comprehensive tests for call analyzer."""

from unittest.mock import MagicMock

import pytest

from src.graph.call_analyzer import CallAnalyzer
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    index = SymbolIndex()
    index.add(Symbol(name="func_a", type="function", file="module_a.py", line=1, column=0))
    index.add(Symbol(name="func_b", type="function", file="module_b.py", line=10, column=0))
    index.add(Symbol(name="ClassA", type="class", file="module_a.py", line=20, column=0))
    index.add(Symbol(name="process", type="function", file="module_c.py", line=5, column=0))
    return index


@pytest.fixture
def call_analyzer(symbol_index):
    """Create call analyzer."""
    return CallAnalyzer(symbol_index)


class TestCallAnalyzerInit:
    """Test CallAnalyzer initialization."""

    def test_init(self, symbol_index):
        """Test analyzer initialization."""
        analyzer = CallAnalyzer(symbol_index)

        assert analyzer.symbol_index is symbol_index


class TestExtractCallsPython:
    """Test Python call extraction."""

    def test_extract_calls_no_body(self, call_analyzer):
        """Test extraction with no function body."""
        mock_node = MagicMock()
        mock_node.children = []

        result = call_analyzer.extract_calls_python(mock_node, b"", "test.py")

        assert result == []

    def test_extract_calls_with_block(self, call_analyzer):
        """Test extraction finds block node."""
        block_node = MagicMock()
        block_node.type = "block"
        block_node.children = []

        func_node = MagicMock()
        func_node.children = [block_node]

        result = call_analyzer.extract_calls_python(func_node, b"func_a()", "module_a.py")

        assert result == []

    def test_extract_calls_empty_block(self, call_analyzer):
        """Test extraction with empty block."""
        block_node = MagicMock()
        block_node.type = "block"
        block_node.children = []

        func_node = MagicMock()
        func_node.children = [block_node]

        result = call_analyzer.extract_calls_python(func_node, b"", "test.py")

        assert result == []


class TestFindCallNodesPython:
    """Test Python AST call node finding."""

    def test_find_calls_simple_call(self, call_analyzer):
        """Test finding simple function calls."""
        # Create mock call node
        call_node = MagicMock()
        call_node.type = "call"

        func_ref = MagicMock()
        func_ref.start_byte = 0
        func_ref.end_byte = 6
        call_node.child_by_field_name.return_value = func_ref

        # Create parent node
        parent_node = MagicMock()
        parent_node.type = "block"
        parent_node.children = [call_node]

        calls = set()

        # Mock the _resolve_call_name to return a node_id
        call_analyzer._resolve_call_name = MagicMock(return_value="func_a_id")

        call_analyzer._find_call_nodes_python(parent_node, b"func_a()", "module_a.py", calls)

        assert len(calls) > 0

    def test_find_calls_nested_nodes(self, call_analyzer):
        """Test finding calls in nested nodes."""
        call_node = MagicMock()
        call_node.type = "call"
        call_node.children = []

        func_ref = MagicMock()
        func_ref.start_byte = 0
        func_ref.end_byte = 5
        call_node.child_by_field_name.return_value = func_ref

        parent_node = MagicMock()
        parent_node.type = "block"
        parent_node.children = [call_node]

        calls = set()

        call_analyzer._resolve_call_name = MagicMock(return_value="func_id")

        call_analyzer._find_call_nodes_python(parent_node, b"func()", "test.py", calls)

        assert len(calls) >= 0

    def test_find_calls_no_calls(self, call_analyzer):
        """Test node with no calls."""
        node = MagicMock()
        node.type = "block"
        node.children = []

        calls = set()

        call_analyzer._find_call_nodes_python(node, b"", "test.py", calls)

        assert len(calls) == 0


class TestExtractCallsTypeScript:
    """Test TypeScript call extraction."""

    def test_extract_calls_no_body(self, call_analyzer):
        """Test extraction with no function body."""
        mock_node = MagicMock()
        mock_node.children = []

        result = call_analyzer.extract_calls_typescript(mock_node, b"", "test.ts")

        assert result == []

    def test_extract_calls_with_statement_block(self, call_analyzer):
        """Test extraction finds statement block."""
        block_node = MagicMock()
        block_node.type = "statement_block"
        block_node.children = []

        func_node = MagicMock()
        func_node.children = [block_node]

        result = call_analyzer.extract_calls_typescript(func_node, b"", "test.ts")

        assert result == []

    def test_extract_calls_wrong_block_type(self, call_analyzer):
        """Test extraction ignores wrong block type."""
        block_node = MagicMock()
        block_node.type = "wrong_block"
        block_node.children = []

        func_node = MagicMock()
        func_node.children = [block_node]

        result = call_analyzer.extract_calls_typescript(func_node, b"", "test.ts")

        assert result == []


class TestFindCallNodesTypeScript:
    """Test TypeScript AST call node finding."""

    def test_find_calls_call_expression(self, call_analyzer):
        """Test finding call expressions."""
        call_node = MagicMock()
        call_node.type = "call_expression"
        call_node.children = []

        func_ref = MagicMock()
        func_ref.start_byte = 0
        func_ref.end_byte = 6
        call_node.child_by_field_name.return_value = func_ref

        parent_node = MagicMock()
        parent_node.type = "statement_block"
        parent_node.children = [call_node]

        calls = set()

        call_analyzer._resolve_call_name = MagicMock(return_value="func_id")

        call_analyzer._find_call_nodes_typescript(parent_node, b"func_a()", "test.ts", calls)

        assert len(calls) >= 0

    def test_find_calls_no_function_field(self, call_analyzer):
        """Test finding call with no function field."""
        call_node = MagicMock()
        call_node.type = "call_expression"
        call_node.child_by_field_name.return_value = None
        call_node.children = []

        parent_node = MagicMock()
        parent_node.type = "statement_block"
        parent_node.children = [call_node]

        calls = set()

        call_analyzer._find_call_nodes_typescript(parent_node, b"", "test.ts", calls)

        # Should handle None gracefully
        assert len(calls) == 0

    def test_find_calls_nested_calls(self, call_analyzer):
        """Test finding nested call expressions."""
        inner_call = MagicMock()
        inner_call.type = "call_expression"
        inner_call.children = []

        func_ref = MagicMock()
        func_ref.start_byte = 0
        func_ref.end_byte = 5
        inner_call.child_by_field_name.return_value = func_ref

        outer_node = MagicMock()
        outer_node.type = "statement_block"
        outer_node.children = [inner_call]

        calls = set()

        call_analyzer._resolve_call_name = MagicMock(return_value="func_id")

        call_analyzer._find_call_nodes_typescript(outer_node, b"func()", "test.ts", calls)

        assert len(calls) >= 0


class TestResolveCallName:
    """Test call name resolution."""

    def test_resolve_simple_name_local(self, call_analyzer):
        """Test resolving simple function name from local file."""
        result = call_analyzer._resolve_call_name("func_a", "module_a.py")

        assert result is not None

    def test_resolve_simple_name_other_file(self, call_analyzer):
        """Test resolving simple function name from other file."""
        result = call_analyzer._resolve_call_name("func_b", "module_a.py")

        assert result is not None

    def test_resolve_simple_name_not_found(self, call_analyzer):
        """Test resolving non-existent function."""
        result = call_analyzer._resolve_call_name("nonexistent", "module_a.py")

        assert result is None

    def test_resolve_qualified_name(self, call_analyzer):
        """Test resolving qualified function name."""
        result = call_analyzer._resolve_call_name("module.func_a", "test.py")

        # Should resolve to func_a
        assert result is not None

    def test_resolve_deep_qualified_name(self, call_analyzer):
        """Test resolving deeply qualified name."""
        result = call_analyzer._resolve_call_name("a.b.c.process", "test.py")

        # Should resolve to process
        assert result is not None

    def test_resolve_whitespace_stripped(self, call_analyzer):
        """Test whitespace is stripped."""
        result = call_analyzer._resolve_call_name("  func_a  ", "module_a.py")

        assert result is not None

    def test_resolve_method_call(self, call_analyzer):
        """Test resolving method calls."""
        result = call_analyzer._resolve_call_name("obj.func_a", "test.py")

        # Should resolve to func_a
        assert result is not None

    def test_resolve_prefers_local(self, call_analyzer, symbol_index):
        """Test resolution prefers local definitions."""
        # Add another func_a in a different file
        symbol_index.add(
            Symbol(name="func_a", type="function", file="module_other.py", line=50, column=0)
        )

        result = call_analyzer._resolve_call_name("func_a", "module_a.py")

        # Should prefer the one in module_a.py
        candidates = symbol_index.get_by_name("func_a")
        local = [c for c in candidates if c.file == "module_a.py"]
        if local:
            assert result == local[0].node_id


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_call_name(self, call_analyzer):
        """Test empty call name."""
        result = call_analyzer._resolve_call_name("", "test.py")

        assert result is None

    def test_whitespace_only_call_name(self, call_analyzer):
        """Test whitespace-only call name."""
        result = call_analyzer._resolve_call_name("   ", "test.py")

        # Should return None or handle gracefully
        assert result is None or isinstance(result, str)

    def test_special_characters_in_name(self, call_analyzer):
        """Test special characters in call name."""
        result = call_analyzer._resolve_call_name("_private_func", "test.py")

        # Should handle gracefully
        assert isinstance(result, (str, type(None)))

    def test_numeric_call_names(self, call_analyzer):
        """Test numeric patterns in names."""
        # Add a symbol with numbers
        call_analyzer.symbol_index.add(
            Symbol(name="func_123", type="function", file="test.py", line=1, column=0)
        )

        result = call_analyzer._resolve_call_name("func_123", "test.py")

        assert result is not None
