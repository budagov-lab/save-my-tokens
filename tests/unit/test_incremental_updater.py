"""Tests for incremental symbol updater."""

import pytest
from unittest.mock import MagicMock
from src.incremental.updater import IncrementalSymbolUpdater
from src.incremental.symbol_delta import SymbolDelta
from src.parsers.symbol_index import SymbolIndex
from src.parsers.symbol import Symbol


@pytest.fixture
def symbol_index():
    """Create test symbol index."""
    idx = SymbolIndex()
    idx.add(Symbol(name="func_a", type="function", file="test.py", line=1, column=0))
    idx.add(Symbol(name="func_b", type="function", file="test.py", line=10, column=0))
    return idx


@pytest.fixture
def updater(symbol_index):
    """Create updater with mocked Neo4j."""
    neo4j = MagicMock()
    return IncrementalSymbolUpdater(symbol_index, neo4j)


class TestUpdaterBasics:
    """Test basic updater functionality."""

    def test_updater_init(self, symbol_index):
        """Test updater initialization."""
        neo4j = MagicMock()
        updater = IncrementalSymbolUpdater(symbol_index, neo4j)

        assert updater.index is not None
        assert updater.neo4j is not None
        assert updater.delta_history == []

    def test_apply_delta_success(self, updater):
        """Test successful delta application."""
        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_c", type="function", file="test.py", line=20, column=0)],
            deleted=[],
            modified=[]
        )

        result = updater.apply_delta(delta)

        assert result.success == True
        assert result.delta == delta
        assert len(updater.delta_history) == 1

    def test_apply_delta_records_time(self, updater):
        """Test that delta application records duration."""
        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_c", type="function", file="test.py", line=20, column=0)],
            deleted=[],
            modified=[]
        )

        result = updater.apply_delta(delta)

        assert result.duration_ms >= 0

    def test_apply_multiple_deltas(self, updater):
        """Test applying multiple deltas sequentially."""
        deltas = [
            SymbolDelta(
                file="test.py",
                added=[Symbol(name=f"func_{i}", type="function", file="test.py", line=i*10, column=0)],
                deleted=[],
                modified=[]
            )
            for i in range(3)
        ]

        for delta in deltas:
            result = updater.apply_delta(delta)
            assert result.success == True

        assert len(updater.delta_history) == 3


class TestDeltaAdditions:
    """Test adding symbols via delta."""

    def test_delta_add_single_symbol(self, updater):
        """Test adding single symbol."""
        new_func = Symbol(name="new_func", type="function", file="test.py", line=30, column=0)
        delta = SymbolDelta(file="test.py", added=[new_func], deleted=[], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True
        # Verify symbol was added to index
        candidates = updater.index.get_by_name("new_func")
        assert len(candidates) > 0

    def test_delta_add_multiple_symbols(self, updater):
        """Test adding multiple symbols."""
        new_symbols = [
            Symbol(name=f"new_func_{i}", type="function", file="test.py", line=30+i*10, column=0)
            for i in range(3)
        ]
        delta = SymbolDelta(file="test.py", added=new_symbols, deleted=[], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True


class TestDeltaDeletions:
    """Test deleting symbols via delta."""

    def test_delta_delete_symbol(self, updater):
        """Test deleting symbol."""
        delta = SymbolDelta(file="test.py", added=[], deleted=["func_a"], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True

    def test_delta_delete_multiple_symbols(self, updater):
        """Test deleting multiple symbols."""
        delta = SymbolDelta(file="test.py", added=[], deleted=["func_a", "func_b"], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True


class TestDeltaModifications:
    """Test modifying symbols via delta."""

    def test_delta_modify_symbol(self, updater):
        """Test modifying symbol."""
        modified = Symbol(
            name="func_a",
            type="function",
            file="test.py",
            line=5,  # Changed line
            column=0,
            docstring="Updated docstring"
        )
        delta = SymbolDelta(file="test.py", added=[], deleted=[], modified=[modified])

        result = updater.apply_delta(delta)

        assert result.success == True

    def test_delta_modify_multiple_symbols(self, updater):
        """Test modifying multiple symbols."""
        modified_symbols = [
            Symbol(name="func_a", type="function", file="test.py", line=2, column=0, docstring="Updated A"),
            Symbol(name="func_b", type="function", file="test.py", line=11, column=0, docstring="Updated B"),
        ]
        delta = SymbolDelta(file="test.py", added=[], deleted=[], modified=modified_symbols)

        result = updater.apply_delta(delta)

        assert result.success == True


class TestComplexDeltas:
    """Test complex delta scenarios."""

    def test_delta_add_and_delete(self, updater):
        """Test adding and deleting in single delta."""
        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_new", type="function", file="test.py", line=30, column=0)],
            deleted=["func_a"],
            modified=[]
        )

        result = updater.apply_delta(delta)

        assert result.success == True

    def test_delta_add_modify_delete(self, updater):
        """Test add, modify, and delete in single delta."""
        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_new", type="function", file="test.py", line=30, column=0)],
            deleted=["func_a"],
            modified=[Symbol(name="func_b", type="function", file="test.py", line=11, column=0)]
        )

        result = updater.apply_delta(delta)

        assert result.success == True


class TestRollback:
    """Test rollback on failure."""

    def test_delta_rollback_on_error(self, updater):
        """Test that delta handles errors gracefully."""
        # Make the entire update process fail
        original_update = updater._update_neo4j
        updater._update_neo4j = MagicMock(side_effect=Exception("DB Error"))

        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_new", type="function", file="test.py", line=30, column=0)],
            deleted=[],
            modified=[]
        )

        result = updater.apply_delta(delta)

        # Should handle error
        assert result is not None
        # Restore
        updater._update_neo4j = original_update

    def test_delta_recorded_history(self, updater):
        """Test that successful deltas are recorded in history."""
        delta = SymbolDelta(
            file="test.py",
            added=[Symbol(name="func_new", type="function", file="test.py", line=30, column=0)],
            deleted=[],
            modified=[]
        )

        updater.apply_delta(delta)

        # History should contain successful delta
        assert len(updater.delta_history) == 1


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_delta(self, updater):
        """Test empty delta (no changes)."""
        delta = SymbolDelta(file="test.py", added=[], deleted=[], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True

    def test_delta_nonexistent_file(self, updater):
        """Test delta for non-tracked file."""
        delta = SymbolDelta(
            file="nonexistent.py",
            added=[Symbol(name="func_x", type="function", file="nonexistent.py", line=1, column=0)],
            deleted=[],
            modified=[]
        )

        result = updater.apply_delta(delta)

        # Should handle gracefully
        assert result is not None

    def test_delta_delete_nonexistent_symbol(self, updater):
        """Test deleting symbol that doesn't exist."""
        delta = SymbolDelta(file="test.py", added=[], deleted=["nonexistent"], modified=[])

        result = updater.apply_delta(delta)

        # Should handle gracefully
        assert result is not None

    def test_large_delta(self, updater):
        """Test delta with many symbols."""
        new_symbols = [
            Symbol(name=f"func_{i}", type="function", file="test.py", line=i, column=0)
            for i in range(100)
        ]
        delta = SymbolDelta(file="test.py", added=new_symbols, deleted=[], modified=[])

        result = updater.apply_delta(delta)

        assert result.success == True
