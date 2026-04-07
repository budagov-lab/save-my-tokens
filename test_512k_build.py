#!/usr/bin/env python3
"""Test script to build 512k-lines graph with Unicode handling."""

import sys
import os
import time
from pathlib import Path

# Set encoding for Windows console
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Suppress Rich progress bar output
os.environ['TERM'] = 'dumb'

from src.graph.graph_builder import GraphBuilder
from src.graph.neo4j_client import Neo4jClient
from loguru import logger

def build_512k_graph():
    """Build graph for 512k-lines codebase."""
    # Try both Windows and MSYS2 paths
    import subprocess
    result = subprocess.run(['bash', '-c', 'ls -d /tmp/512k-lines 2>/dev/null'],
                           capture_output=True, text=True)
    if result.returncode == 0:
        repo_path = Path(result.stdout.strip())
    else:
        repo_path = Path('C:/tmp/512k-lines')

    if not repo_path.exists():
        print(f"Error: 512k-lines repo not found at {repo_path}")
        return False

    src_path = repo_path / 'src'
    print(f"Building graph for {repo_path}...")
    print(f"Files in src/: {len(list(src_path.rglob('*.ts*')))}")

    start = time.time()
    try:
        gb = GraphBuilder(str(src_path))
        print("GraphBuilder created, starting parse...")

        # Parse files
        gb._parse_all_files()
        symbols = len(gb.symbol_index.get_all())
        parse_time = time.time() - start
        print(f"Parsed symbols: {symbols} in {parse_time:.2f}s")

        # Create nodes
        node_start = time.time()
        gb._create_nodes()
        node_time = time.time() - node_start
        print(f"Created nodes: {len(gb.nodes)} in {node_time:.2f}s")

        # Create edges
        edge_start = time.time()
        gb._create_edges()
        edge_time = time.time() - edge_start
        print(f"Created edges: {len(gb.edges)} in {edge_time:.2f}s")

        # Persist to Neo4j
        persist_start = time.time()
        gb._persist_to_neo4j()
        persist_time = time.time() - persist_start
        print(f"Persisted to Neo4j in {persist_time:.2f}s")

        total = time.time() - start
        print(f"\nTotal build time: {total:.2f}s")
        print(f"  Parsing: {parse_time:.2f}s")
        print(f"  Nodes: {node_time:.2f}s")
        print(f"  Edges: {edge_time:.2f}s")
        print(f"  Persist: {persist_time:.2f}s")

        # Check Neo4j status
        client = Neo4jClient()
        with client.driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            node_count = result.single()['count']
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            edge_count = result.single()['count']

        print(f"\nNeo4j Graph Stats:")
        print(f"  Total nodes: {node_count}")
        print(f"  Total edges: {edge_count}")

        return True

    except Exception as e:
        print(f"Error during build: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = build_512k_graph()
    sys.exit(0 if success else 1)
