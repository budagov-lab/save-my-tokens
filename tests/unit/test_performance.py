"""Unit tests for performance optimization."""

import pytest

from src.performance.optimizer import CacheOptimizer, MemoryOptimizer, PerformanceProfiler, QueryOptimizer


class TestPerformanceProfiler:
    """Test PerformanceProfiler."""

    def test_measurement(self) -> None:
        """Test basic measurement."""
        profiler = PerformanceProfiler()

        @profiler.measure("test_op")
        def slow_operation() -> int:
            import time

            time.sleep(0.01)
            return 42

        result = slow_operation()
        assert result == 42
        assert "test_op" in profiler.measurements
        assert len(profiler.measurements["test_op"]) == 1

    def test_get_stats(self) -> None:
        """Test statistics generation."""
        profiler = PerformanceProfiler()
        profiler.measurements["test"] = [10.0, 20.0, 30.0, 40.0, 50.0]

        stats = profiler.get_stats("test")
        assert stats is not None
        assert stats["count"] == 5
        assert stats["min_ms"] == 10.0
        assert stats["max_ms"] == 50.0
        assert stats["avg_ms"] == 30.0

    def test_get_stats_not_found(self) -> None:
        """Test getting stats for non-existent operation."""
        profiler = PerformanceProfiler()
        stats = profiler.get_stats("nonexistent")
        assert stats is None


class TestCacheOptimizer:
    """Test CacheOptimizer."""

    def test_estimate_cache_size(self) -> None:
        """Test cache size estimation."""
        # 1000 items, 1KB each = 1MB
        size_mb = CacheOptimizer.estimate_cache_size(1000, 1024)
        assert 0.9 < size_mb < 1.1

    def test_suggest_cache_size(self) -> None:
        """Test cache size suggestion."""
        # 1000 items, fit in 100MB = 104857 bytes per item (100MB / 1000)
        max_item_size = CacheOptimizer.suggest_cache_size(1000, target_mb=100)
        assert max_item_size > 0
        assert max_item_size <= 104858  # 100MB / 1000 items


class TestQueryOptimizer:
    """Test QueryOptimizer."""

    def test_estimate_index_benefit(self) -> None:
        """Test index benefit estimation."""
        # 100ms without index, 10ms with index = 10x speedup
        speedup = QueryOptimizer.estimate_index_benefit(100.0, 10.0)
        assert speedup == 10.0

    def test_estimate_index_benefit_zero(self) -> None:
        """Test index benefit with zero indexed time."""
        speedup = QueryOptimizer.estimate_index_benefit(100.0, 0.0)
        assert speedup == float("inf")

    def test_recommend_indexes(self) -> None:
        """Test index recommendations."""
        # High query count + high latency
        recommendations = QueryOptimizer.recommend_indexes(150, 75.0)
        assert len(recommendations) > 0

    def test_recommend_indexes_low_volume(self) -> None:
        """Test with low query volume."""
        recommendations = QueryOptimizer.recommend_indexes(10, 5.0)
        assert len(recommendations) == 0


class TestMemoryOptimizer:
    """Test MemoryOptimizer."""

    def test_estimate_symbol_index_memory(self) -> None:
        """Test symbol index memory estimation."""
        # 1000 symbols at ~500 bytes each = ~500KB
        memory_mb = MemoryOptimizer.estimate_symbol_index_memory(1000)
        assert 0.4 < memory_mb < 0.6

    def test_estimate_embedding_memory(self) -> None:
        """Test embedding memory estimation."""
        # 100 embeddings, 1536-dim
        memory_mb = MemoryOptimizer.estimate_embedding_memory(100, dim=1536)
        assert memory_mb > 0

    def test_estimate_graph_memory(self) -> None:
        """Test graph memory estimation."""
        # 1000 nodes + 2000 edges
        memory_mb = MemoryOptimizer.estimate_graph_memory(1000, 2000)
        assert memory_mb > 1  # Should be at least 1MB
