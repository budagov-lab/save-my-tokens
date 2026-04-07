"""Strongly connected components detection for cycle-safe context retrieval."""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


@dataclass
class CycleGroup:
    """Represents a cycle (strongly connected component with >1 member)."""

    members: List[str]  # function names in the cycle
    representative: str  # canonical name (alphabetically first) for display

    def __post_init__(self) -> None:
        """Ensure representative is one of the members."""
        if not self.members:
            raise ValueError("CycleGroup must have at least one member")
        if self.representative not in self.members:
            raise ValueError("representative must be a member of the cycle")


def detect_cycles(
    nodes: List[str], edges: List[Tuple[str, str]]
) -> Tuple[List[str], List[CycleGroup]]:
    """
    Detect strongly connected components using Tarjan's algorithm.

    Args:
        nodes: List of node names
        edges: List of (source, target) tuples representing directed edges

    Returns:
        acyclic_nodes: Nodes not part of any cycle
        cycle_groups: List of CycleGroup objects (each has >=2 members)
    """
    if not nodes:
        return [], []

    # Build adjacency list
    adjacency: Dict[str, List[str]] = {node: [] for node in nodes}
    for src, dst in edges:
        if src in adjacency and dst in adjacency:
            adjacency[src].append(dst)

    # Tarjan's SCC algorithm (recursive but safe for typical graph sizes)
    index_counter = [0]
    index_map: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    sccs: List[List[str]] = []

    def strongconnect(node: str) -> None:
        """Recursive Tarjan's SCC finding."""
        index_map[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        # Process successors
        for successor in adjacency[node]:
            if successor not in index_map:
                # Successor not yet visited; recurse
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif successor in on_stack:
                # Successor is in the current SCC path
                lowlink[node] = min(lowlink[node], index_map[successor])

        # If node is a root node of an SCC, pop it
        if lowlink[node] == index_map[node]:
            scc: List[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == node:
                    break
            sccs.append(scc)

    # Find all SCCs
    for node in nodes:
        if node not in index_map:
            strongconnect(node)

    # Separate acyclic nodes and cycle groups
    acyclic_nodes: List[str] = []
    cycle_groups: List[CycleGroup] = []

    for scc in sccs:
        if len(scc) == 1:
            acyclic_nodes.append(scc[0])
        else:
            # Sort members alphabetically, use first as representative
            sorted_members = sorted(scc)
            cycle_groups.append(CycleGroup(members=sorted_members, representative=sorted_members[0]))

    return acyclic_nodes, cycle_groups
