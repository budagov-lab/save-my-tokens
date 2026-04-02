"""Tests for performance optimizer."""

import pytest

from src.performance.optimizer import PerformanceProfiler, CacheOptimizer


class TestPerformanceProfiler:
    """Test performance profiler."""

    def test_profiler_init(self):
        """Test profiler initialization."""
        profiler = PerformanceProfiler()

        assert profiler.measurements == {}

    def test_measure_decorator(self):
        """Test measure decorator."""
        profiler = PerformanceProfiler()

        @profiler.measure("test_operation")
        def test_func():
            return 42

        result = test_func()

        assert result == 42
        assert "test_operation" in profiler.measurements
        assert len(profiler.measurements["test_operation"]) == 1

    def test_measure_multiple_calls(self):
        """Test measuring multiple calls."""
        profiler = PerformanceProfiler()

        @profiler.measure("test_op")
        def test_func():
            return 1

        test_func()
        test_func()
        test_func()

        assert len(profiler.measurements["test_op"]) == 3

    def test_measure_with_args(self):
        """Test measuring function with arguments."""
        profiler = PerformanceProfiler()

        @profiler.measure("test_op")
        def test_func(a, b):
            return a + b

        result = test_func(1, 2)

        assert result == 3
        assert "test_op" in profiler.measurements

    def test_measure_with_exception(self):
        """Test measuring function that raises exception."""
        profiler = PerformanceProfiler()

        @profiler.measure("failing_op")
        def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            test_func()

        # Measurement should still be recorded
        assert "failing_op" in profiler.measurements

    def test_get_stats_not_found(self):
        """Test getting stats for non-existent operation."""
        profiler = PerformanceProfiler()

        stats = profiler.get_stats("nonexistent")

        assert stats is None

    def test_get_stats_single_measurement(self):
        """Test stats with single measurement."""
        profiler = PerformanceProfiler()

        @profiler.measure("op1")
        def test_func():
            pass

        test_func()

        stats = profiler.get_stats("op1")

        assert stats is not None
        assert stats["count"] == 1
        assert stats["min_ms"] == stats["max_ms"]
        assert stats["avg_ms"] == stats["min_ms"]

    def test_get_stats_multiple_measurements(self):
        """Test stats with multiple measurements."""
        profiler = PerformanceProfiler()

        profiler.measurements["op1"] = [10.0, 20.0, 30.0, 40.0, 50.0]

        stats = profiler.get_stats("op1")

        assert stats["count"] == 5
        assert stats["min_ms"] == 10.0
        assert stats["max_ms"] == 50.0
        assert stats["avg_ms"] == 30.0
        assert stats["p50_ms"] == 30.0
        assert stats["p99_ms"] == 50.0

    def test_get_stats_p99_calculation(self):
        """Test p99 calculation."""
        profiler = PerformanceProfiler()

        # Create 100 measurements
        profiler.measurements["op1"] = list(range(1, 101))

        stats = profiler.get_stats("op1")

        assert stats["p99_ms"] == 100

    def test_print_report_empty(self, capsys):
        """Test printing empty report."""
        profiler = PerformanceProfiler()

        profiler.print_report()

        captured = capsys.readouterr()
        assert "PERFORMANCE REPORT" in captured.out

    def test_print_report_with_data(self, capsys):
        """Test printing report with data."""
        profiler = PerformanceProfiler()

        @profiler.measure("operation1")
        def test_func1():
            pass

        @profiler.measure("operation2")
        def test_func2():
            pass

        test_func1()
        test_func2()
        test_func2()

        profiler.print_report()

        captured = capsys.readouterr()
        assert "PERFORMANCE REPORT" in captured.out
        assert "operation1" in captured.out
        assert "operation2" in captured.out
        assert "Samples:" in captured.out
        assert "Avg:" in captured.out
        assert "p99:" in captured.out
        assert "Min:" in captured.out
        assert "Max:" in captured.out
        assert "p50:" in captured.out


class TestCacheOptimizer:
    """Test cache optimizer."""

    def test_estimate_cache_size_zero(self):
        """Test cache size estimation with zero items."""
        size_mb = CacheOptimizer.estimate_cache_size(0, 1000)

        assert size_mb == 0.0

    def test_estimate_cache_size_single_item(self):
        """Test cache size estimation with single item."""
        # 1 item of 1000 bytes = 1000 bytes = ~0.001 MB
        size_mb = CacheOptimizer.estimate_cache_size(1, 1000)

        assert size_mb > 0

    def test_estimate_cache_size_multiple_items(self):
        """Test cache size estimation with multiple items."""
        # 1000 items of 1000 bytes = 1MB
        size_mb = CacheOptimizer.estimate_cache_size(1000, 1000)

        assert 0.9 < size_mb < 1.1  # Should be ~1 MB

    def test_estimate_cache_size_large(self):
        """Test cache size estimation with large values."""
        # 1,000,000 items of 1000 bytes = ~1000 MB
        size_mb = CacheOptimizer.estimate_cache_size(1000000, 1000)

        assert size_mb > 900  # Should be ~1000 MB

    def test_estimate_cache_size_exact(self):
        """Test cache size calculation is correct."""
        # 1 MB = 1,000,000 bytes
        # So 1,000 items of 1,000 bytes = 0.001 MB
        size_mb = CacheOptimizer.estimate_cache_size(1000, 1000)

        expected_mb = (1000 * 1000) / (1024 * 1024)
        assert abs(size_mb - expected_mb) < 0.01
