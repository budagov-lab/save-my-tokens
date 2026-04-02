#!/usr/bin/env python3
"""
Minimal initialization for save-my-tokens.
Call this once to ensure graph is ready.

Usage:
    from init_smt import ensure_graph_ready
    ensure_graph_ready()  # Builds graph if needed
"""

import sys
from pathlib import Path
from loguru import logger

from src.graph.neo4j_client import Neo4jClient
from src.graph.graph_builder import GraphBuilder


def ensure_graph_ready(verbose: bool = False) -> bool:
    """
    Ensure graph is built and ready.

    Returns True if graph is ready, False if build failed.
    """
    try:
        client = Neo4jClient()
        stats = client.get_stats()
        client.close()

        # If graph has nodes, it's ready
        if stats['node_count'] > 100:  # Sanity check
            if verbose:
                print(f"[OK] Graph ready: {stats['node_count']} nodes")
            return True

        # Otherwise rebuild
        if verbose:
            print("[INFO] Graph empty, rebuilding...")

        client = Neo4jClient()
        client.clear_database()
        client.close()

        builder = GraphBuilder(base_path="src")
        builder.build()

        if verbose:
            client = Neo4jClient()
            stats = client.get_stats()
            print(f"[OK] Graph built: {stats['node_count']} nodes, {stats['edge_count']} edges")
            client.close()

        return True

    except Exception as e:
        logger.error(f"Failed to ensure graph ready: {e}")
        return False


if __name__ == '__main__':
    success = ensure_graph_ready(verbose=True)
    sys.exit(0 if success else 1)
