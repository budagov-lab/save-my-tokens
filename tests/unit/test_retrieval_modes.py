"""Tests for the three retrieval modes (definition, context, impact)."""

from src.smt_cli import _compute_depths


class TestComputeDepths:
    """Test depth computation for impact analysis (BFS over reverse edges)."""

    def test_empty_graph(self) -> None:
        """Empty graph with single root."""
        depths = _compute_depths("A", [])
        assert depths == {"A": 0}

    def test_single_caller(self) -> None:
        """Single caller: B calls A."""
        # Edge (B, A) means B calls A (or in reverse, A is called by B)
        depths = _compute_depths("A", [("B", "A")])
        assert depths == {"A": 0, "B": 1}

    def test_chain_of_callers(self) -> None:
        """C -> B -> A (C calls B, B calls A). If A is root, C is depth 2."""
        edges = [("B", "A"), ("C", "B")]
        depths = _compute_depths("A", edges)
        assert depths["A"] == 0
        assert depths["B"] == 1
        assert depths["C"] == 2

    def test_multiple_direct_callers(self) -> None:
        """B and C both call A."""
        edges = [("B", "A"), ("C", "A")]
        depths = _compute_depths("A", edges)
        assert depths == {"A": 0, "B": 1, "C": 1}

    def test_multiple_levels(self) -> None:
        """Diamond: D calls B and C, B and C both call A."""
        edges = [
            ("B", "A"),  # B calls A
            ("C", "A"),  # C calls A
            ("D", "B"),  # D calls B
            ("D", "C"),  # D calls C
        ]
        depths = _compute_depths("A", edges)
        assert depths["A"] == 0
        assert depths["B"] == 1
        assert depths["C"] == 1
        assert depths["D"] == 2

    def test_unrelated_edges(self) -> None:
        """Edges unrelated to root are ignored in BFS."""
        edges = [
            ("B", "A"),   # B calls A
            ("X", "Y"),   # X calls Y (unrelated)
        ]
        depths = _compute_depths("A", edges)
        assert depths == {"A": 0, "B": 1}
        assert "X" not in depths
        assert "Y" not in depths

    def test_complex_graph(self) -> None:
        """Complex call graph with multiple paths to root."""
        edges = [
            ("B", "A"),   # depth 1
            ("C", "A"),   # depth 1
            ("D", "B"),   # depth 2
            ("D", "C"),   # depth 2
            ("E", "D"),   # depth 3
            ("F", "B"),   # depth 2
        ]
        depths = _compute_depths("A", edges)
        assert depths["A"] == 0
        assert depths["B"] == 1
        assert depths["C"] == 1
        assert depths["D"] == 2
        assert depths["F"] == 2
        assert depths["E"] == 3
