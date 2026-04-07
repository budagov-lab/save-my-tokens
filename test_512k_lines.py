#!/usr/bin/env python3
"""Test SMT on the 512k-lines TypeScript codebase."""

import subprocess
import time
from pathlib import Path

def run_test():
    """Run SMT queries on 512k-lines."""
    print("\n" + "="*80)
    print("SMT Performance Test: 512k-lines TypeScript Codebase")
    print("="*80 + "\n")

    # First, check graph stats
    print("Graph Statistics:")
    print("-" * 40)
    result = subprocess.run(
        ["python", "-c", """
from src.config import settings
from src.graph.neo4j_client import Neo4jClient
client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
stats = client.get_stats()
print(f"  Nodes: {stats['node_count']}")
print(f"  Edges: {stats['edge_count']}")
client.driver.close()
"""],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"  Error: {result.stderr}")
        return

    # Test three modes on a real symbol
    test_symbols = [
        ("commands", "definition"),
        ("CommandExecutor", "context"),
        ("parseCommand", "impact"),
    ]

    for symbol, mode in test_symbols:
        print(f"\nTesting: {mode} mode on '{symbol}'")
        print("-" * 40)

        start = time.time()
        if mode == "definition":
            result = subprocess.run(
                ["python", "-c", f"""
import sys
from src.smt_cli import cmd_definition
sys.exit(cmd_definition('{symbol}'))
"""],
                capture_output=True,
                text=True,
            )
        elif mode == "context":
            result = subprocess.run(
                ["python", "-c", f"""
import sys
from src.smt_cli import cmd_context
sys.exit(cmd_context('{symbol}', depth=2))
"""],
                capture_output=True,
                text=True,
            )
        else:  # impact
            result = subprocess.run(
                ["python", "-c", f"""
import sys
from src.smt_cli import cmd_impact
sys.exit(cmd_impact('{symbol}', max_depth=3))
"""],
                capture_output=True,
                text=True,
            )

        elapsed = time.time() - start
        print(f"  Status: {'OK' if result.returncode == 0 else 'FAILED'}")
        print(f"  Time: {elapsed*1000:.1f}ms")

        # Extract metadata from output
        lines = result.stdout.split("\n")
        for line in lines:
            if "nodes=" in line or "context:" in line or "impact:" in line:
                print(f"  {line.strip()}")

    print("\n" + "="*80)
    print("Test Complete")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_test()
