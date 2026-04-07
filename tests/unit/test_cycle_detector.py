"""Tests for cycle detection (SCC) in graph context retrieval."""

import pytest

from src.graph.cycle_detector import CycleGroup, detect_cycles


class TestCycleDetection:
    """Test strongly connected components detection."""

    def test_empty_graph(self) -> None:
        """Empty graph has no acyclic nodes or cycles."""
        acyclic, cycles = detect_cycles([], [])
        assert acyclic == []
        assert cycles == []

    def test_single_node_no_edges(self) -> None:
        """Single node with no edges is acyclic."""
        acyclic, cycles = detect_cycles(["A"], [])
        assert acyclic == ["A"]
        assert cycles == []

    def test_linear_chain_no_cycles(self) -> None:
        """A -> B -> C has no cycles."""
        acyclic, cycles = detect_cycles(
            ["A", "B", "C"], [("A", "B"), ("B", "C")]
        )
        assert set(acyclic) == {"A", "B", "C"}
        assert cycles == []

    def test_simple_cycle(self) -> None:
        """A -> B -> A is a cycle of size 2."""
        acyclic, cycles = detect_cycles(
            ["A", "B"], [("A", "B"), ("B", "A")]
        )
        assert acyclic == []
        assert len(cycles) == 1
        assert set(cycles[0].members) == {"A", "B"}
        assert cycles[0].representative == "A"  # alphabetically first

    def test_three_node_cycle(self) -> None:
        """A -> B -> C -> A is a cycle of size 3."""
        acyclic, cycles = detect_cycles(
            ["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]
        )
        assert acyclic == []
        assert len(cycles) == 1
        assert set(cycles[0].members) == {"A", "B", "C"}
        assert cycles[0].representative == "A"

    def test_separate_components(self) -> None:
        """A -> B (cycle) and C -> D (no cycle)."""
        acyclic, cycles = detect_cycles(
            ["A", "B", "C", "D"],
            [("A", "B"), ("B", "A"), ("C", "D")]
        )
        assert set(acyclic) == {"C", "D"}
        assert len(cycles) == 1
        assert set(cycles[0].members) == {"A", "B"}

    def test_multiple_cycles(self) -> None:
        """Two independent cycles: A <-> B and C <-> D."""
        acyclic, cycles = detect_cycles(
            ["A", "B", "C", "D"],
            [("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")]
        )
        assert acyclic == []
        assert len(cycles) == 2
        cycle_members = [set(c.members) for c in cycles]
        assert {"A", "B"} in cycle_members
        assert {"C", "D"} in cycle_members

    def test_self_loop(self) -> None:
        """A -> A is a cycle of size 1 (but should be filtered as acyclic since size 1)."""
        acyclic, cycles = detect_cycles(
            ["A"], [("A", "A")]
        )
        # Self-loops are SCC of size 1, treated as acyclic
        assert acyclic == ["A"]
        assert cycles == []

    def test_complex_graph(self) -> None:
        """
        Graph with multiple components:
        - Cycle: A -> B -> C -> A
        - Acyclic: D -> E -> F
        - Separate: G (no edges)
        """
        acyclic, cycles = detect_cycles(
            ["A", "B", "C", "D", "E", "F", "G"],
            [
                ("A", "B"), ("B", "C"), ("C", "A"),  # Cycle
                ("D", "E"), ("E", "F"),               # Linear
                # G is isolated
            ]
        )
        assert set(acyclic) == {"D", "E", "F", "G"}
        assert len(cycles) == 1
        assert set(cycles[0].members) == {"A", "B", "C"}

    def test_cycle_group_alphabetical_representative(self) -> None:
        """Cycle members should be sorted alphabetically, with first as representative."""
        acyclic, cycles = detect_cycles(
            ["Z", "A", "M"], [("Z", "A"), ("A", "M"), ("M", "Z")]
        )
        assert len(cycles) == 1
        assert cycles[0].representative == "A"  # alphabetically first
        assert cycles[0].members == ["A", "M", "Z"]  # sorted

    def test_unconnected_nodes(self) -> None:
        """Nodes without edges should be acyclic."""
        acyclic, cycles = detect_cycles(
            ["A", "B", "C"], []
        )
        assert set(acyclic) == {"A", "B", "C"}
        assert cycles == []

    def test_missing_edge_target(self) -> None:
        """Edges referencing non-existent nodes are ignored (filtered)."""
        # Edge X->Y but Y doesn't exist in nodes list
        acyclic, cycles = detect_cycles(
            ["A", "B"], [("A", "B"), ("A", "X"), ("Y", "B")]
        )
        # Only valid edges are considered
        assert set(acyclic) == {"A", "B"}
        assert cycles == []


class TestCycleGroupValidation:
    """Test CycleGroup dataclass validation."""

    def test_cycle_group_creation(self) -> None:
        """CycleGroup with valid members and representative."""
        cg = CycleGroup(members=["A", "B"], representative="A")
        assert cg.members == ["A", "B"]
        assert cg.representative == "A"

    def test_cycle_group_requires_members(self) -> None:
        """CycleGroup cannot have empty members."""
        with pytest.raises(ValueError, match="must have at least one member"):
            CycleGroup(members=[], representative="A")

    def test_cycle_group_representative_must_be_member(self) -> None:
        """CycleGroup representative must be one of the members."""
        with pytest.raises(ValueError, match="representative must be a member"):
            CycleGroup(members=["A", "B"], representative="C")
