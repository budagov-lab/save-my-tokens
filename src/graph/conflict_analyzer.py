"""Advanced conflict detection for parallel task execution."""

from typing import Dict, List, Set, Tuple

from loguru import logger

from src.graph.neo4j_client import Neo4jClient
from src.parsers.symbol_index import SymbolIndex


class ConflictAnalyzer:
    """Analyze conflicts and determine safe parallelization boundaries."""

    def __init__(self, symbol_index: SymbolIndex, neo4j_client: Neo4jClient):
        """Initialize conflict analyzer.

        Args:
            symbol_index: Symbol index for dependency lookup
            neo4j_client: Neo4j client for graph queries
        """
        self.symbol_index = symbol_index
        self.neo4j_client = neo4j_client
        self._dependency_cache: Dict[str, Set[str]] = {}

    def get_all_dependencies(self, symbol_name: str) -> Set[str]:
        """Get all symbols that a given symbol depends on (transitive closure).

        Args:
            symbol_name: Symbol to get dependencies for

        Returns:
            Set of all symbol names this symbol depends on
        """
        if symbol_name in self._dependency_cache:
            return self._dependency_cache[symbol_name]

        dependencies: Set[str] = set()
        visited: Set[str] = set()
        to_visit: List[str] = [symbol_name]

        while to_visit:
            current = to_visit.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Find direct dependencies (imports, calls, etc.)
            symbol = self.symbol_index.get_by_qualified_name(current)
            if not symbol:
                # Try by name
                candidates = self.symbol_index.get_by_name(current)
                if not candidates:
                    continue
                symbol = candidates[0]

            # Get imports - only add direct imports (not all symbols in same file)
            imports = self.symbol_index.get_imports()
            for imp in imports:
                if imp.file == symbol.file:
                    dependencies.add(imp.name)
                    to_visit.append(imp.name)

        self._dependency_cache[symbol_name] = dependencies
        return dependencies

    def get_dependents(self, symbol_name: str) -> Set[str]:
        """Get all symbols that depend on a given symbol (reverse transitive).

        Args:
            symbol_name: Symbol to get dependents for

        Returns:
            Set of all symbol names that depend on this symbol
        """
        dependents: Set[str] = set()

        for symbol in self.symbol_index.get_all():
            deps = self.get_all_dependencies(symbol.name)
            if symbol_name in deps:
                dependents.add(symbol.name)

        return dependents

    def detect_direct_conflicts(self, tasks: List[Dict]) -> List[Dict]:
        """Detect direct conflicts (overlapping symbol sets).

        Args:
            tasks: List of task dicts with 'id' and 'target_symbols'

        Returns:
            List of conflict dicts
        """
        conflicts = []

        for i, task_a in enumerate(tasks):
            symbols_a = set(task_a.get("target_symbols", []))
            for j, task_b in enumerate(tasks[i + 1 :], start=i + 1):
                symbols_b = set(task_b.get("target_symbols", []))

                # Direct overlap
                overlap = symbols_a & symbols_b
                if overlap:
                    conflicts.append(
                        {
                            "type": "direct_overlap",
                            "task_a": task_a.get("id"),
                            "task_b": task_b.get("id"),
                            "conflicting_symbols": list(overlap),
                        }
                    )

        return conflicts

    def detect_dependency_conflicts(self, tasks: List[Dict]) -> List[Dict]:
        """Detect dependency-based conflicts.

        Task A conflicts with Task B if:
        - Task A modifies a symbol that Task B depends on
        - Task B modifies a symbol that Task A depends on

        Args:
            tasks: List of task dicts with 'id' and 'target_symbols'

        Returns:
            List of conflict dicts
        """
        conflicts = []

        for i, task_a in enumerate(tasks):
            symbols_a = set(task_a.get("target_symbols", []))
            deps_a = set()
            for sym in symbols_a:
                deps_a.update(self.get_all_dependencies(sym))

            for j, task_b in enumerate(tasks[i + 1 :], start=i + 1):
                symbols_b = set(task_b.get("target_symbols", []))
                deps_b = set()
                for sym in symbols_b:
                    deps_b.update(self.get_all_dependencies(sym))

                # Check: A modifies something B depends on
                if symbols_a & deps_b:
                    conflicts.append(
                        {
                            "type": "dependency_violation",
                            "task_a": task_a.get("id"),
                            "task_b": task_b.get("id"),
                            "reason": f"{task_a.get('id')} modifies symbols {task_a.get('id')} depends on",
                            "conflicting_symbols": list(symbols_a & deps_b),
                        }
                    )

                # Check: B modifies something A depends on
                if symbols_b & deps_a:
                    conflicts.append(
                        {
                            "type": "dependency_violation",
                            "task_a": task_a.get("id"),
                            "task_b": task_b.get("id"),
                            "reason": f"{task_b.get('id')} modifies symbols {task_a.get('id')} depends on",
                            "conflicting_symbols": list(symbols_b & deps_a),
                        }
                    )

        return conflicts

    def detect_circular_dependencies(self, tasks: List[Dict]) -> List[Dict]:
        """Detect circular dependencies between tasks.

        Args:
            tasks: List of task dicts with 'id' and 'target_symbols'

        Returns:
            List of circular dependency alerts
        """
        alerts = []

        for task in tasks:
            symbols = set(task.get("target_symbols", []))
            dependents = set()

            for sym in symbols:
                dependents.update(self.get_dependents(sym))

            # If any dependent is in target symbols, there's a cycle
            cycle = dependents & symbols
            if cycle:
                alerts.append(
                    {
                        "type": "circular_dependency",
                        "task": task.get("id"),
                        "cyclic_symbols": list(cycle),
                        "severity": "high",
                    }
                )

        return alerts

    def analyze_conflicts(self, tasks: List[Dict]) -> Dict:
        """Comprehensive conflict analysis.

        Args:
            tasks: List of task dicts with 'id' and 'target_symbols'

        Returns:
            Complete conflict report
        """
        if not tasks:
            return {
                "task_count": 0,
                "direct_conflicts": [],
                "dependency_conflicts": [],
                "circular_dependencies": [],
                "parallel_feasible": True,
                "recommendation": "No tasks to analyze",
            }

        direct = self.detect_direct_conflicts(tasks)
        dependencies = self.detect_dependency_conflicts(tasks)
        circular = self.detect_circular_dependencies(tasks)

        all_conflicts = direct + dependencies + circular
        parallel_feasible = len(all_conflicts) == 0

        recommendation = self._get_recommendation(tasks, all_conflicts)

        logger.info(
            f"Conflict analysis: {len(direct)} direct, {len(dependencies)} dep, "
            f"{len(circular)} circular. Parallel feasible: {parallel_feasible}"
        )

        return {
            "task_count": len(tasks),
            "tasks": [t.get("id") for t in tasks],
            "direct_conflicts": direct,
            "dependency_conflicts": dependencies,
            "circular_dependencies": circular,
            "total_conflicts": len(all_conflicts),
            "parallel_feasible": parallel_feasible,
            "recommendation": recommendation,
        }

    def _get_recommendation(self, tasks: List[Dict], conflicts: List[Dict]) -> str:
        """Generate recommendation based on conflict analysis.

        Args:
            tasks: Task list
            conflicts: Detected conflicts

        Returns:
            Recommendation string
        """
        if not conflicts:
            return "All tasks can execute in parallel"

        if len(conflicts) <= 2:
            return "Limited parallelization possible. Consider sequential execution."

        # Try to find independent subsets
        task_ids = {t.get("id") for t in tasks}
        conflicted_pairs = set()
        for conflict in conflicts:
            if "task_a" in conflict and "task_b" in conflict:
                pair = tuple(sorted([conflict["task_a"], conflict["task_b"]]))
                conflicted_pairs.add(pair)

        independent = []
        for tid in task_ids:
            is_independent = True
            for a, b in conflicted_pairs:
                if tid in (a, b):
                    is_independent = False
                    break
            if is_independent:
                independent.append(tid)

        if independent:
            return f"Tasks {independent} are independent. Consider executing them in parallel."

        return "All tasks have conflicts. Sequential execution recommended."
