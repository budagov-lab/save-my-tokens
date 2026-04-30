#!/usr/bin/env python3
"""Benchmark Neo4j queries for the three retrieval modes."""

import time
import sys
from pathlib import Path

# Suppress logs during benchmark
import logging
logging.getLogger("loguru").setLevel(logging.WARNING)

from src.config import settings
from src.graph.neo4j_client import Neo4jClient
from src.graph.cycle_detector import detect_cycles
from src.graph.neo4j_client import compute_depths as _compute_depths

def benchmark_definition(client: Neo4jClient, symbol: str, runs: int = 5) -> dict:
    """Benchmark definition mode."""
    times = []
    for _ in range(runs):
        start = time.time()
        with client.driver.session() as session:
            # Node lookup
            result = session.run(
                "MATCH (n {name: $name}) RETURN n LIMIT 1",
                name=symbol
            )
            node = result.single()

            if node:
                # Direct callees (1-hop)
                callees = session.run(
                    "MATCH (n {name: $name})-[:CALLS]->(callee) RETURN callee.name",
                    name=symbol
                ).data()

        times.append(time.time() - start)

    return {
        "mode": "definition",
        "symbol": symbol,
        "runs": runs,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
        "avg_ms": sum(times) / len(times) * 1000,
    }


def benchmark_context(client: Neo4jClient, symbol: str, depth: int = 2, runs: int = 5) -> dict:
    """Benchmark context mode."""
    times = []
    for _ in range(runs):
        start = time.time()

        # Get bounded subgraph
        subgraph = client.get_bounded_subgraph(symbol, max_depth=depth)

        if subgraph:
            # Detect cycles
            nodes = subgraph["nodes"]
            edges = subgraph["edges"]
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            detect_cycles(node_names, edge_tuples)

        times.append(time.time() - start)

    return {
        "mode": "context",
        "symbol": symbol,
        "depth": depth,
        "runs": runs,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
        "avg_ms": sum(times) / len(times) * 1000,
    }


def benchmark_impact(client: Neo4jClient, symbol: str, depth: int = 3, runs: int = 5) -> dict:
    """Benchmark impact mode."""
    times = []
    for _ in range(runs):
        start = time.time()

        # Get impact graph
        impact = client.get_impact_graph(symbol, max_depth=depth)

        if impact:
            # Detect cycles
            nodes = impact["nodes"]
            edges = impact["edges"]
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            detect_cycles(node_names, edge_tuples)

            # Compute depths
            _compute_depths(symbol, edge_tuples)

        times.append(time.time() - start)

    return {
        "mode": "impact",
        "symbol": symbol,
        "depth": depth,
        "runs": runs,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
        "avg_ms": sum(times) / len(times) * 1000,
    }


def main() -> None:
    """Run all benchmarks."""
    client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

    # Get some symbols to test
    symbols = ["GraphBuilder", "SymbolIndex", "Neo4jClient", "detect_cycles"]

    print("\n" + "="*80)
    print("SMT Query Performance Benchmark")
    print("="*80 + "\n")

    all_results = []

    for symbol in symbols:
        print(f"Benchmarking: {symbol}")
        print("-" * 40)

        try:
            result_def = benchmark_definition(client, symbol, runs=3)
            all_results.append(result_def)
            print(f"  definition:    {result_def['avg_ms']:.1f}ms (min={result_def['min_ms']:.1f}ms, max={result_def['max_ms']:.1f}ms)")
        except Exception as e:
            print(f"  definition:    ERROR - {e}")

        try:
            result_ctx = benchmark_context(client, symbol, depth=2, runs=3)
            all_results.append(result_ctx)
            print(f"  context:       {result_ctx['avg_ms']:.1f}ms (min={result_ctx['min_ms']:.1f}ms, max={result_ctx['max_ms']:.1f}ms)")
        except Exception as e:
            print(f"  context:       ERROR - {e}")

        try:
            result_imp = benchmark_impact(client, symbol, depth=3, runs=3)
            all_results.append(result_imp)
            print(f"  impact:        {result_imp['avg_ms']:.1f}ms (min={result_imp['min_ms']:.1f}ms, max={result_imp['max_ms']:.1f}ms)")
        except Exception as e:
            print(f"  impact:        ERROR - {e}")

        print()

    # Summary
    print("\n" + "="*80)
    print("Summary")
    print("="*80 + "\n")

    by_mode = {}
    for r in all_results:
        mode = r["mode"]
        if mode not in by_mode:
            by_mode[mode] = []
        by_mode[mode].append(r["avg_ms"])

    for mode, times in sorted(by_mode.items()):
        avg = sum(times) / len(times)
        print(f"  {mode:12s}:  avg={avg:.1f}ms  (n={len(times)})")

    # Test graph stats
    print("\n" + "="*80)
    print("Graph Statistics")
    print("="*80 + "\n")

    stats = client.get_stats()
    print(f"  Total nodes:    {stats['node_count']}")
    print(f"  Total edges:    {stats['edge_count']}")

    client.driver.close()


if __name__ == "__main__":
    main()
