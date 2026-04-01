"""Performance optimization utilities."""

import time
from typing import Callable, Dict, Optional

from loguru import logger


class PerformanceProfiler:
    """Profile and optimize performance of critical paths."""

    def __init__(self):
        """Initialize profiler."""
        self.measurements: Dict[str, list] = {}

    def measure(self, name: str) -> Callable:
        """Decorator to measure function execution time.

        Args:
            name: Name of the operation being measured

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end = time.perf_counter()
                    elapsed_ms = (end - start) * 1000

                    if name not in self.measurements:
                        self.measurements[name] = []

                    self.measurements[name].append(elapsed_ms)
                    logger.debug(f"{name} took {elapsed_ms:.2f}ms")

            return wrapper

        return decorator

    def get_stats(self, name: str) -> Optional[Dict]:
        """Get performance statistics for an operation.

        Args:
            name: Operation name

        Returns:
            Statistics dictionary or None if not found
        """
        if name not in self.measurements:
            return None

        times = self.measurements[name]
        times_sorted = sorted(times)

        return {
            "count": len(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "avg_ms": sum(times) / len(times),
            "p50_ms": times_sorted[len(times) // 2],
            "p99_ms": times_sorted[int(len(times) * 0.99)] if len(times) > 1 else times[0],
        }

    def print_report(self) -> None:
        """Print performance report."""
        print("\n" + "=" * 80)
        print("PERFORMANCE REPORT")
        print("=" * 80)

        for name in sorted(self.measurements.keys()):
            stats = self.get_stats(name)
            if stats:
                print(f"\n{name}:")
                print(
                    f"  Samples: {stats['count']} | "
                    f"Avg: {stats['avg_ms']:.2f}ms | "
                    f"p99: {stats['p99_ms']:.2f}ms"
                )
                print(
                    f"  Min: {stats['min_ms']:.2f}ms | "
                    f"Max: {stats['max_ms']:.2f}ms | "
                    f"p50: {stats['p50_ms']:.2f}ms"
                )

        print("\n" + "=" * 80)


class CacheOptimizer:
    """Optimization strategies for caching."""

    @staticmethod
    def estimate_cache_size(item_count: int, item_size_bytes: int) -> float:
        """Estimate cache size in MB.

        Args:
            item_count: Number of items in cache
            item_size_bytes: Average size per item

        Returns:
            Cache size in MB
        """
        return (item_count * item_size_bytes) / (1024 * 1024)

    @staticmethod
    def suggest_cache_size(item_count: int, target_mb: float = 100) -> int:
        """Suggest cache size that fits in target memory.

        Args:
            item_count: Number of items
            target_mb: Target cache size in MB

        Returns:
            Maximum item size in bytes
        """
        target_bytes = target_mb * 1024 * 1024
        return int(target_bytes / item_count) if item_count > 0 else 0


class QueryOptimizer:
    """Optimization strategies for database queries."""

    @staticmethod
    def estimate_index_benefit(full_scan_time_ms: float, indexed_time_ms: float) -> float:
        """Estimate speedup from adding an index.

        Args:
            full_scan_time_ms: Time for full scan
            indexed_time_ms: Time with index

        Returns:
            Speedup factor (e.g., 10.0 = 10x faster)
        """
        if indexed_time_ms == 0:
            return float("inf")
        return full_scan_time_ms / indexed_time_ms

    @staticmethod
    def recommend_indexes(query_count: int, avg_latency_ms: float) -> list:
        """Recommend indexes based on query patterns.

        Args:
            query_count: Number of queries
            avg_latency_ms: Average query latency

        Returns:
            List of index recommendations
        """
        recommendations = []

        if query_count > 100 and avg_latency_ms > 50:
            recommendations.append(
                {
                    "index": "node_id",
                    "reason": "High query volume with high latency",
                    "expected_speedup": 5,
                }
            )

        if avg_latency_ms > 100:
            recommendations.append(
                {
                    "index": "node_name",
                    "reason": "Slow symbol lookups",
                    "expected_speedup": 3,
                }
            )

        if query_count > 1000:
            recommendations.append(
                {
                    "index": "node_file",
                    "reason": "Very high query volume",
                    "expected_speedup": 2,
                }
            )

        return recommendations


class MemoryOptimizer:
    """Memory optimization strategies."""

    @staticmethod
    def estimate_symbol_index_memory(symbol_count: int) -> float:
        """Estimate memory usage of symbol index.

        Args:
            symbol_count: Number of symbols

        Returns:
            Estimated memory in MB
        """
        # Rough estimate: 500 bytes per symbol in index
        bytes_per_symbol = 500
        total_bytes = symbol_count * bytes_per_symbol
        return total_bytes / (1024 * 1024)

    @staticmethod
    def estimate_embedding_memory(embedding_count: int, dim: int = 1536) -> float:
        """Estimate memory usage of embeddings.

        Args:
            embedding_count: Number of embeddings
            dim: Embedding dimension

        Returns:
            Estimated memory in MB
        """
        # 4 bytes per float32 * dim + overhead
        bytes_per_embedding = 4 * dim + 50
        total_bytes = embedding_count * bytes_per_embedding
        return total_bytes / (1024 * 1024)

    @staticmethod
    def estimate_graph_memory(node_count: int, edge_count: int) -> float:
        """Estimate Neo4j memory usage.

        Args:
            node_count: Number of nodes
            edge_count: Number of edges

        Returns:
            Estimated memory in MB
        """
        # Very rough: 1KB per node + 200 bytes per edge
        total_bytes = (node_count * 1024) + (edge_count * 200)
        return total_bytes / (1024 * 1024)
