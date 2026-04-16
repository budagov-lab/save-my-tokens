"""SMTQueryEngine: Structured query API for agents (no stdout, returns typed models)."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from src.config import settings
from src.embeddings.embedding_service import EmbeddingService
from src.graph.cycle_detector import detect_cycles
from src.graph.compressor import compress_subgraph
from src.graph.neo4j_client import Neo4jClient
from src.graph.validator import validate_graph
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex
from src.agents.models import (
    DefinitionResult,
    ContextResult,
    ImpactResult,
    SearchResult,
    StatusResult,
)


class SMTQueryEngine:
    """Structured query interface for agent consumption (no stdout side effects).

    Wraps Neo4jClient, EmbeddingService, and graph utilities with a clean API
    that returns typed Pydantic models.

    Performance features:
    - In-memory LRU-style result cache (TTL-based, version-keyed via graph head)
    - Parallel batch queries via ThreadPoolExecutor (Neo4j pool: 100 connections)
    - Merged Cypher queries (1 round trip for definition, context, impact)
    - Batch deduplication (identical queries share one result)
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        embeddings_cache_dir: Optional[Path] = None,
        project_id: Optional[str] = None,
        cache_ttl: int = 60,
    ):
        """Initialize the query engine.

        Args:
            neo4j_uri: Neo4j connection URI (defaults to config)
            neo4j_user: Neo4j user (defaults to config)
            neo4j_password: Neo4j password (defaults to config)
            embeddings_cache_dir: Directory for cached embeddings (defaults to .smt/embeddings)
            project_id: Project isolation ID (12-char SHA256 prefix).
            cache_ttl: Seconds before cached results expire (default: 60).
                       Set to 0 to disable caching. status() uses ttl=10 regardless.
        """
        self.client = Neo4jClient(neo4j_uri, neo4j_user, neo4j_password, project_id=project_id or "")
        self.embeddings_cache_dir = embeddings_cache_dir or (
            Path.cwd() / ".smt" / "embeddings"
        )
        self._embedding_service: Optional[EmbeddingService] = None

        # Result cache: key → (result, timestamp)
        self._cache: Dict[tuple, Any] = {}
        self._cache_ts: Dict[tuple, float] = {}
        self._cache_ttl = cache_ttl

        logger.debug(f"SMTQueryEngine initialized (cache_ttl={cache_ttl}s)")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _ck(self, method: str, *args: Any, **kwargs: Any) -> tuple:
        """Build a hashable cache key from method name + args."""
        return (method,) + args + tuple(sorted(kwargs.items()))

    def _cache_get(self, key: tuple, ttl: Optional[int] = None) -> Optional[Any]:
        """Return a cached result if still valid, else None."""
        if self._cache_ttl == 0 or key not in self._cache:
            return None
        effective_ttl = ttl if ttl is not None else self._cache_ttl
        if time.monotonic() - self._cache_ts[key] > effective_ttl:
            del self._cache[key]
            del self._cache_ts[key]
            return None
        return self._cache[key]

    def _cache_set(self, key: tuple, value: Any) -> None:
        """Store result in cache."""
        if self._cache_ttl == 0:
            return
        self._cache[key] = value
        self._cache_ts[key] = time.monotonic()

    def cache_clear(self) -> None:
        """Invalidate all cached results.

        Call this after smt sync / smt build to ensure the next queries
        reflect the updated graph.
        """
        n = len(self._cache)
        self._cache.clear()
        self._cache_ts.clear()
        logger.debug(f"SMTQueryEngine cache cleared ({n} entries)")

    # ------------------------------------------------------------------
    # Embedding service
    # ------------------------------------------------------------------

    def _get_embedding_service(self, symbol_index: Optional[SymbolIndex] = None) -> EmbeddingService:
        """Lazy-load embedding service (cached across queries)."""
        if self._embedding_service is not None:
            return self._embedding_service
        logger.debug("Initializing EmbeddingService...")
        if symbol_index is None:
            symbol_index = SymbolIndex()
        self._embedding_service = EmbeddingService(symbol_index, self.embeddings_cache_dir)
        return self._embedding_service

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def definition(self, symbol: str) -> DefinitionResult:
        """Get definition of a symbol (1-hop, fast).

        Single Cypher round trip: finds the symbol and its callees together.
        Results are cached for cache_ttl seconds.

        Args:
            symbol: Symbol name to look up

        Returns:
            DefinitionResult with name, labels, file, line, signature, docstring, callees.
            result.found is False if symbol not found.
        """
        key = self._ck("definition", symbol)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug(f"definition('{symbol}'): cache hit")
            return cached

        try:
            pid = self.client.project_id
            params: Dict[str, Any] = {"name": symbol}

            if pid:
                params["pid"] = pid
                query = """
                MATCH (n {name: $name})
                WHERE n.project_id = $pid
                WITH n, CASE WHEN n:Function THEN 0
                             WHEN n:Class    THEN 1
                             ELSE 2 END AS priority
                ORDER BY priority LIMIT 1
                OPTIONAL MATCH (n)-[:CALLS]->(callee {project_id: $pid})
                RETURN n, collect({name: callee.name, file: callee.file}) AS callees
                """
            else:
                query = """
                MATCH (n {name: $name})
                WITH n, CASE WHEN n:Function THEN 0
                             WHEN n:Class    THEN 1
                             ELSE 2 END AS priority
                ORDER BY priority LIMIT 1
                OPTIONAL MATCH (n)-[:CALLS]->(callee)
                RETURN n, collect({name: callee.name, file: callee.file}) AS callees
                """

            with self.client.driver.session() as session:
                row = session.run(query, **params).single()

            if not row:
                logger.debug(f"Symbol '{symbol}' not found")
                result = DefinitionResult(found=False, symbol=symbol)
                self._cache_set(key, result)
                return result

            n = row["n"]
            callees = [dict(c) for c in row["callees"] if c.get("name")]
            raw: Dict[str, Any] = {
                "found": True,
                "name": n.get("name"),
                "labels": list(n.labels),
                "file": n.get("file"),
                "line": n.get("line"),
                "signature": n.get("signature"),
                "docstring": n.get("docstring"),
                "callees": callees,
            }
            logger.debug(f"definition('{symbol}'): found, {len(callees)} callees")
            result = DefinitionResult.model_validate(raw)
            self._cache_set(key, result)
            return result

        except Exception as e:
            logger.error(f"definition() error: {e}")
            return DefinitionResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def context(
        self, symbol: str, depth: int = 2, compress: bool = False
    ) -> ContextResult:
        """Get working context for a symbol (bounded bidirectional).

        Results are cached for cache_ttl seconds.

        Args:
            symbol: Symbol name to analyze
            depth: Max hop distance (1-10 recommended)
            compress: Remove bridge functions to save tokens

        Returns:
            ContextResult with root, nodes, edges, cycles, and compression stats.
            result.found is False if symbol not found.
        """
        key = self._ck("context", symbol, depth=depth, compress=compress)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug(f"context('{symbol}'): cache hit")
            return cached

        try:
            subgraph = self.client.get_bounded_subgraph(symbol, max_depth=depth)
            if not subgraph:
                logger.debug(f"Symbol '{symbol}' not found in graph")
                result = ContextResult(found=False, symbol=symbol)
                self._cache_set(key, result)
                return result

            root = subgraph["root"]
            nodes = subgraph["nodes"]
            edges = subgraph["edges"]
            original_node_count = len(nodes)

            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

            result_dict = {
                "found": True,
                "symbol": symbol,
                "root": root,
                "nodes": nodes,
                "edges": edges,
                "cycles": [
                    {"members": cg.members, "representative": cg.representative}
                    for cg in cycle_groups
                ],
                "compressed": False,
                "bridges_removed": 0,
                "original_node_count": original_node_count,
                "final_node_count": len(nodes),
                "depth_reached": subgraph.get("depth_reached", depth),
            }

            if compress and node_names:
                cycle_members = {m for cg in cycle_groups for m in cg.members}
                compression_result = compress_subgraph(
                    symbol, node_names, edge_tuples, cycle_members
                )
                nodes = [n for n in nodes if n["name"] in compression_result.nodes]
                edges = [
                    e for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges
                ]
                node_names = [n["name"] for n in nodes]
                edge_tuples = [(e["src"], e["dst"]) for e in edges]
                acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

                result_dict["nodes"] = nodes
                result_dict["edges"] = edges
                result_dict["cycles"] = [
                    {"members": cg.members, "representative": cg.representative}
                    for cg in cycle_groups
                ]
                result_dict["compressed"] = True
                result_dict["bridges_removed"] = len(compression_result.bridges)
                result_dict["final_node_count"] = len(nodes)

            result_dict["token_estimate"] = sum(
                len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes
            ) // 4

            logger.debug(
                f"context('{symbol}'): {result_dict['final_node_count']} nodes, "
                f"{len(result_dict['cycles'])} cycles, depth={depth}"
            )
            result = ContextResult.model_validate(result_dict)
            self._cache_set(key, result)
            return result

        except Exception as e:
            logger.error(f"context() error: {e}")
            return ContextResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def impact(self, symbol: str, depth: int = 3) -> ImpactResult:
        """Analyze impact of changing a symbol (reverse traversal).

        Results are cached for cache_ttl seconds.

        Args:
            symbol: Symbol name to analyze
            depth: Max hop distance in reverse direction

        Returns:
            ImpactResult with callers_by_depth, total_callers, cycles, token_estimate.
            result.found is False if symbol not found.
        """
        key = self._ck("impact", symbol, depth=depth)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug(f"impact('{symbol}'): cache hit")
            return cached

        try:
            impact_graph = self.client.get_impact_graph(symbol, max_depth=depth)
            if not impact_graph:
                logger.debug(f"Symbol '{symbol}' not found in graph")
                result = ImpactResult(found=False, symbol=symbol)
                self._cache_set(key, result)
                return result

            root = impact_graph["root"]
            nodes = impact_graph["nodes"]
            edges = impact_graph["edges"]

            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

            callers_by_depth: Dict[int, List[Dict[str, Any]]] = {}
            visited = {symbol}
            current_frontier = [symbol]
            current_depth = 1

            while current_frontier and current_depth <= depth:
                next_frontier = []
                callers_at_depth = []

                for caller in current_frontier:
                    for edge in edges:
                        if edge["dst"] == caller and edge["src"] not in visited:
                            visited.add(edge["src"])
                            next_frontier.append(edge["src"])
                            node_details = next(
                                (n for n in nodes if n["name"] == edge["src"]),
                                None,
                            )
                            if node_details:
                                callers_at_depth.append({
                                    "name": node_details["name"],
                                    "file": node_details["file"],
                                    "line": node_details["line"],
                                })

                if callers_at_depth:
                    callers_by_depth[current_depth] = callers_at_depth

                current_frontier = next_frontier
                current_depth += 1

            result_dict = {
                "found": True,
                "symbol": symbol,
                "root": root,
                "callers_by_depth": callers_by_depth,
                "total_callers": len(visited) - 1,
                "cycles": [
                    {"members": cg.members, "representative": cg.representative}
                    for cg in cycle_groups
                ],
                "token_estimate": sum(
                    len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes
                ) // 4,
                "depth_reached": depth,
            }

            logger.debug(
                f"impact('{symbol}'): {result_dict['total_callers']} callers, "
                f"{len(result_dict['cycles'])} cycles"
            )
            result = ImpactResult.model_validate(result_dict)
            self._cache_set(key, result)
            return result

        except Exception as e:
            logger.error(f"impact() error: {e}")
            return ImpactResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def search(self, query: str, top_k: int = 5) -> SearchResult:
        """Semantic search for symbols.

        Results are cached for cache_ttl seconds.

        Args:
            query: Natural language query or keywords
            top_k: Number of results to return

        Returns:
            SearchResult with hits list. Each hit has name, type, file, line, score.
        """
        key = self._ck("search", query, top_k=top_k)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug(f"search('{query}'): cache hit")
            return cached

        try:
            svc = self._get_embedding_service()
            results = svc.search(query, top_k=top_k)

            output = []
            for symbol, score in results:
                output.append({
                    "name": symbol.name,
                    "type": symbol.type,
                    "file": symbol.file,
                    "line": symbol.line,
                    "docstring": symbol.docstring,
                    "score": float(score),
                })

            logger.debug(f"search('{query}'): {len(output)} results")
            result = SearchResult.from_list(output, query=query)
            self._cache_set(key, result)
            return result

        except Exception as e:
            logger.error(f"search() error: {e}")
            return SearchResult(error_reason="parse_error", error_message=str(e))

    def status(self, repo_path: Optional[Path] = None) -> StatusResult:
        """Check graph freshness and statistics.

        Cached for 10 seconds (shorter than other methods — graph head can
        change if the user runs smt sync in another terminal).

        Args:
            repo_path: Path to git repository (defaults to cwd)

        Returns:
            StatusResult with is_fresh, git_head, graph_head, commits_behind,
            node_count, edge_count, freshness_status.
        """
        resolved = str(repo_path or Path.cwd())
        key = self._ck("status", resolved)
        cached = self._cache_get(key, ttl=10)
        if cached is not None:
            logger.debug("status(): cache hit")
            return cached

        try:
            repo_path = Path(resolved)
            validation = validate_graph(self.client, repo_path)
            stats = self.client.get_stats()

            if validation.is_fresh:
                freshness_status = "fresh"
            elif validation.commits_behind < 0:
                freshness_status = "unknown"
            else:
                freshness_status = "stale"

            result_dict = {
                "is_fresh": validation.is_fresh,
                "git_head": validation.git_head,
                "graph_head": validation.graph_head,
                "commits_behind": validation.commits_behind,
                "node_count": stats["node_count"],
                "edge_count": stats["edge_count"],
                "freshness_status": freshness_status,
            }

            logger.debug(f"status(): {freshness_status}, {stats['node_count']} nodes")
            result = StatusResult.model_validate(result_dict)
            self._cache_set(key, result)
            return result

        except Exception as e:
            logger.error(f"status() error: {e}")
            return StatusResult.model_validate({
                "is_fresh": False,
                "git_head": "unknown",
                "commits_behind": -1,
                "node_count": 0,
                "edge_count": 0,
                "freshness_status": "unknown",
                "error": str(e),
            })

    def batch(
        self,
        queries: List[Tuple[str, tuple, dict]],
        max_workers: int = 8,
    ) -> List[Any]:
        """Run multiple queries concurrently using a thread pool.

        Deduplicates identical queries (same method + args) so each unique
        query runs exactly once even if repeated in the input list.
        Results from the cache are returned without spawning threads.

        Each thread opens its own Neo4j session from the shared driver pool
        (default pool size: 100), so queries execute in parallel without
        connection contention.

        Args:
            queries: List of (method_name, args, kwargs) tuples.
                     method_name must be one of: definition, context, impact,
                     search, status.
                     Example:
                         [
                             ("impact",     ("build",),          {"depth": 3}),
                             ("impact",     ("validate_graph",), {"depth": 3}),
                             ("context",    ("GraphBuilder",),   {"depth": 2}),
                             ("definition", ("add",),            {}),
                         ]
            max_workers: Max parallel threads (default: 8).
                         Safe up to Neo4j pool size (100).

        Returns:
            List of results in the same order as input queries.
            Each result is the typed model returned by the called method.
            If a query raises unexpectedly, the result at that index is the
            Exception object.
        """
        _methods = {
            "definition": self.definition,
            "context":    self.context,
            "impact":     self.impact,
            "search":     self.search,
            "status":     self.status,
        }

        for i, (method_name, args, kwargs) in enumerate(queries):
            if method_name not in _methods:
                raise ValueError(
                    f"queries[{i}]: unknown method '{method_name}'. "
                    f"Valid: {', '.join(_methods)}"
                )

        # Deduplicate: build a map from cache-key → first index in input
        key_to_first_idx: Dict[tuple, int] = {}
        query_keys: List[tuple] = []
        unique_to_run: List[Tuple[int, str, tuple, dict]] = []  # (first_idx, method, args, kwargs)

        for idx, (method_name, args, kwargs) in enumerate(queries):
            key = self._ck(method_name, *args, **kwargs)
            query_keys.append(key)
            if key not in key_to_first_idx:
                key_to_first_idx[key] = idx
                unique_to_run.append((idx, method_name, args, kwargs))

        unique_results: Dict[tuple, Any] = {}

        # Separate cache hits from actual work
        work = []
        for first_idx, method_name, args, kwargs in unique_to_run:
            key = query_keys[first_idx]
            cached = self._cache_get(key)
            if cached is not None:
                unique_results[key] = cached
            else:
                work.append((key, method_name, args, kwargs))

        n_cached = len(unique_to_run) - len(work)
        n_dupes = len(queries) - len(unique_to_run)

        if work:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(work))) as pool:
                futures = {
                    pool.submit(_methods[method_name], *args, **kwargs): key
                    for key, method_name, args, kwargs in work
                }
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        unique_results[key] = future.result()
                    except Exception as exc:
                        logger.error(f"batch query raised unexpectedly: {exc}")
                        unique_results[key] = exc

        logger.debug(
            f"batch: {len(queries)} queries → "
            f"{len(work)} executed, {n_cached} cache hits, {n_dupes} deduped"
        )
        return [unique_results[key] for key in query_keys]

    def close(self) -> None:
        """Close database connection and clear cache."""
        self.cache_clear()
        self.client.close()
        logger.debug("SMTQueryEngine closed")
