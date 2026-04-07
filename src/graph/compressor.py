"""Smart context compression — remove bridge functions to reduce token count."""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from loguru import logger


@dataclass
class CompressionResult:
    """Result of compressing a subgraph."""

    nodes: List[str]  # Surviving node names after compression
    edges: List[Tuple[str, str]]  # Surviving edges (src, dst)
    bridges: List[str]  # Names of removed bridge nodes
    bridge_paths: List[str] = field(default_factory=list)  # Descriptions like "A → [B] → C"


def compress_subgraph(
    root: str,
    nodes: List[str],
    edges: List[Tuple[str, str]],
    cycle_members: Set[str],
) -> CompressionResult:
    """
    Compress subgraph by removing bridge functions.

    A bridge function is one that:
    1. Is not the root symbol
    2. Is not in any cycle
    3. Has exactly 1 inbound edge in the subgraph
    4. Has exactly 1 outbound edge in the subgraph

    This removes trivial forwarding functions that don't add semantic value.

    Args:
        root: Root symbol name (never removed)
        nodes: List of node names in subgraph
        edges: List of (src, dst) edges
        cycle_members: Set of node names that are in cycles (preserved)

    Returns:
        CompressionResult with compressed nodes/edges and removed bridge info
    """
    if not edges:
        # No edges, nothing to compress
        return CompressionResult(
            nodes=nodes,
            edges=[],
            bridges=[],
        )

    # Build adjacency structures
    node_set = set(nodes)
    out_edges: Dict[str, List[str]] = {n: [] for n in nodes}
    in_edges: Dict[str, List[str]] = {n: [] for n in nodes}

    for src, dst in edges:
        if src in node_set and dst in node_set:
            out_edges[src].append(dst)
            in_edges[dst].append(src)

    # Find bridge nodes iteratively (bridges can chain)
    removed_bridges: Set[str] = set()
    bridge_paths: List[str] = []

    changed = True
    while changed:
        changed = False

        for node in nodes:
            if node in removed_bridges or node == root or node in cycle_members:
                continue

            # Check if bridge: exactly 1 in, 1 out
            actual_in = [s for s in in_edges[node] if s not in removed_bridges]
            actual_out = [d for d in out_edges[node] if d not in removed_bridges]

            if len(actual_in) == 1 and len(actual_out) == 1:
                # Bridge found: collapse edge
                src = actual_in[0]
                dst = actual_out[0]

                logger.debug(f"Removing bridge: {src} → [{node}] → {dst}")
                bridge_paths.append(f"{src} → [{node}] → {dst}")

                # Record as removed
                removed_bridges.add(node)
                changed = True

                # Update adjacency for next iteration
                # Add direct edge src → dst
                if dst not in out_edges[src]:
                    out_edges[src].append(dst)
                    in_edges[dst].append(src)

                # Remove bridge edges
                out_edges[src] = [d for d in out_edges[src] if d != node]
                in_edges[node] = []
                out_edges[node] = []

    # Build final nodes and edges
    final_nodes = [n for n in nodes if n not in removed_bridges]
    final_edges: List[Tuple[str, str]] = []

    for src, dests in out_edges.items():
        if src not in removed_bridges:
            for dst in dests:
                if dst not in removed_bridges and (src, dst) not in final_edges:
                    final_edges.append((src, dst))

    logger.debug(f"Compression: {len(nodes)} → {len(final_nodes)} nodes, "
                 f"removed {len(removed_bridges)} bridges")

    return CompressionResult(
        nodes=final_nodes,
        edges=final_edges,
        bridges=sorted(list(removed_bridges)),
        bridge_paths=bridge_paths,
    )


def format_compression_stats(before_nodes: int, before_edges: int,
                            compression: CompressionResult) -> str:
    """Format compression results for display.

    Returns:
        String like "nodes=7→4 edges=5→3" with percentages
    """
    after_nodes = len(compression.nodes)
    after_edges = len(compression.edges)
    node_reduction = ((before_nodes - after_nodes) / before_nodes * 100) if before_nodes > 0 else 0
    edge_reduction = ((before_edges - after_edges) / before_edges * 100) if before_edges > 0 else 0

    return (f"nodes={before_nodes}→{after_nodes} ({node_reduction:.0f}%) "
            f"edges={before_edges}→{after_edges} ({edge_reduction:.0f}%)")
