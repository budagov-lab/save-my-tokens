"""Integration tests for incremental update system."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.graph.neo4j_client import Neo4jClient
from src.incremental.diff_parser import DiffParser, FileDiff
from src.incremental.symbol_delta import SymbolDelta, UpdateResult
from src.incremental.updater import IncrementalSymbolUpdater
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


class TestDiffParser:
    """Test suite for DiffParser."""

    def test_parse_simple_diff(self):
        """Test parsing a simple git diff."""
        diff_text = """diff --git a/src/api.py b/src/api.py
index 1234567..abcdefg 100644
--- a/src/api.py
+++ b/src/api.py
@@ -10,6 +10,10 @@ def existing_function():
     pass

+def new_function():
+    return 42
+
 def another_function():
     pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].file_path == "src/api.py"
        assert summary.files[0].status == "modified"
        assert summary.files[0].added_lines == 3  # new function definition, return statement, and blank line

    def test_parse_added_file(self):
        """Test parsing a diff for a newly added file."""
        diff_text = """diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,5 @@
+def new_function():
+    pass
+
+class NewClass:
+    pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].status == "added"
        assert summary.files[0].file_path == "src/new_module.py"

    def test_parse_deleted_file(self):
        """Test parsing a diff for a deleted file."""
        diff_text = """diff --git a/src/old_module.py b/src/old_module.py
deleted file mode 100644
index 1234567..0000000
--- a/src/old_module.py
+++ /dev/null
@@ -1,5 +0,0 @@
-def old_function():
-    pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)

        assert summary.total_files_changed == 1
        assert summary.files[0].status == "deleted"

    def test_identify_changed_files(self):
        """Test identifying only supported file extensions."""
        diff_text = """diff --git a/src/api.py b/src/api.py
index 1234567..abcdefg 100644
--- a/src/api.py
+++ b/src/api.py
@@ -1 +1,2 @@
 pass"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)
        changed_files = parser.identify_changed_files(summary)

        assert "src/api.py" in changed_files
        assert len(changed_files) == 1

    def test_identify_changed_files_excludes_unsupported(self):
        """Test that unsupported file types are excluded."""
        diff_text = """diff --git a/README.md b/README.md
index 1234567..abcdefg 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Project"""

        parser = DiffParser()
        summary = parser.parse_diff(diff_text)
        changed_files = parser.identify_changed_files(summary)

        assert "README.md" not in changed_files
        assert len(changed_files) == 0

    def test_is_structural_change_detects_added_symbols(self):
        """Test detection of added symbols."""
        parser = DiffParser()
        before = ["existing_func"]
        after = ["existing_func", "new_func"]

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is True

    def test_is_structural_change_detects_removed_symbols(self):
        """Test detection of removed symbols."""
        parser = DiffParser()
        before = ["func1", "func2"]
        after = ["func1"]

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is True

    def test_is_structural_change_ignores_content_changes(self):
        """Test that content-only changes are not detected as structural."""
        parser = DiffParser()
        before = ["func1", "func2"]
        after = ["func1", "func2"]  # Same symbols

        is_change = parser.is_structural_change(
            "src/api.py", before_symbols=before, after_symbols=after
        )

        assert is_change is False


class TestSymbolDelta:
    """Test suite for SymbolDelta."""

    def test_create_symbol_delta(self):
        """Test creating a symbol delta."""
        sym_added = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )

        delta = SymbolDelta(
            file="src/api.py",
            added=[sym_added],
            deleted=["old_func"],
            modified=[],
        )

        assert delta.file == "src/api.py"
        assert len(delta.added) == 1
        assert len(delta.deleted) == 1
        assert delta.is_empty() is False

    def test_empty_delta(self):
        """Test empty delta detection."""
        delta = SymbolDelta(file="src/api.py")

        assert delta.is_empty() is True


class TestIncrementalSymbolUpdater:
    """Test suite for IncrementalSymbolUpdater."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        index = SymbolIndex()
        neo4j = MagicMock(spec=Neo4jClient)
        return index, neo4j

    def test_apply_delta_success(self, mock_dependencies):
        """Test successful delta application."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        # Add initial symbols
        initial_sym = Symbol(
            name="existing_func",
            type="function",
            file="src/api.py",
            line=1,
            column=0,
        )
        index.add(initial_sym)

        # Create updater
        updater = IncrementalSymbolUpdater(index, neo4j)

        # Create delta: add one symbol
        new_sym = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )
        delta = SymbolDelta(file="src/api.py", added=[new_sym])

        # Mock Neo4j transaction
        mock_tx = MagicMock()
        neo4j.begin_transaction.return_value = mock_tx

        # Apply delta
        result = updater.apply_delta(delta)

        assert result.success is True
        assert result.delta == delta
        assert result.duration_ms >= 0

    def test_apply_delta_failure_rollback(self, mock_dependencies):
        """Test failure handling and rollback."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        # Add initial symbols
        initial_sym = Symbol(
            name="existing_func",
            type="function",
            file="src/api.py",
            line=1,
            column=0,
        )
        index.add(initial_sym)

        # Create updater
        updater = IncrementalSymbolUpdater(index, neo4j)

        # Create delta
        new_sym = Symbol(
            name="new_func",
            type="function",
            file="src/api.py",
            line=10,
            column=0,
        )
        delta = SymbolDelta(file="src/api.py", added=[new_sym])

        # Mock Neo4j to raise an exception
        mock_tx = MagicMock()
        mock_tx.commit.side_effect = Exception("Connection lost")
        neo4j.begin_transaction.return_value = mock_tx

        # Apply delta (should fail gracefully)
        result = updater.apply_delta(delta)

        assert result.success is False
        assert result.error != ""
        assert result.duration_ms >= 0

    def test_delta_history_tracking(self, mock_dependencies):
        """Test that deltas are tracked in history."""
        index, neo4j = mock_dependencies
        neo4j.begin_transaction = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j
        mock_tx = MagicMock()
        neo4j.begin_transaction.return_value = mock_tx

        # Apply two deltas
        delta1 = SymbolDelta(
            file="src/api.py",
            added=[Symbol(name="func1", type="function", file="src/api.py", line=1, column=0)],
        )
        delta2 = SymbolDelta(
            file="src/model.py",
            added=[Symbol(name="func2", type="function", file="src/model.py", line=1, column=0)],
        )

        updater.apply_delta(delta1)
        updater.apply_delta(delta2)

        assert len(updater.delta_history) == 2
        assert updater.delta_history[0] == delta1
        assert updater.delta_history[1] == delta2

    def test_validate_graph_consistency_success(self, mock_dependencies):
        """Test successful consistency validation."""
        index, neo4j = mock_dependencies
        neo4j.query = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j queries for consistency checks
        neo4j.query.side_effect = [
            [],  # No orphaned edges
            [],  # No duplicate symbols
            [("CALLS",), ("IMPORTS",)],  # Valid edge types
        ]

        result = updater.validate_graph_consistency()

        assert result is True
        assert neo4j.query.call_count == 3

    def test_validate_graph_consistency_failure(self, mock_dependencies):
        """Test consistency validation failure."""
        index, neo4j = mock_dependencies
        neo4j.query = MagicMock()

        updater = IncrementalSymbolUpdater(index, neo4j)

        # Mock Neo4j to return orphaned edges
        neo4j.query.return_value = [(5,)]  # 5 orphaned edges

        result = updater.validate_graph_consistency()

        assert result is False
