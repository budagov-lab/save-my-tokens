"""SMTQueryEngine: Structured query API for agents (no stdout, returns typed models)."""

from pathlib import Path
from typing import Any, Dict, List, Optional

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
    that returns JSON-serializable dicts suitable for agent parsing.

    All methods return structured data, not stdout. No side effects beyond logging.
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        embeddings_cache_dir: Optional[Path] = None,
        project_id: Optional[str] = None,
    ):
        """Initialize the query engine.

        Args:
            neo4j_uri: Neo4j connection URI (defaults to config)
            neo4j_user: Neo4j user (defaults to config)
            neo4j_password: Neo4j password (defaults to config)
            embeddings_cache_dir: Directory for cached embeddings (defaults to .smt/embeddings)
            project_id: Project isolation ID (12-char SHA256 prefix). Required for multi-project setups.
        """
        self.client = Neo4jClient(neo4j_uri, neo4j_user, neo4j_password, project_id=project_id or "")
        self.embeddings_cache_dir = embeddings_cache_dir or (
            Path.cwd() / ".smt" / "embeddings"
        )
        self._embedding_service: Optional[EmbeddingService] = None
        logger.debug("SMTQueryEngine initialized")

    def _get_embedding_service(self, symbol_index: Optional[SymbolIndex] = None) -> EmbeddingService:
        """Lazy-load embedding service (caches across queries for efficiency).

        Args:
            symbol_index: Optional SymbolIndex (if not provided, will be built from Neo4j)

        Returns:
            EmbeddingService instance
        """
        if self._embedding_service is not None:
            return self._embedding_service

        logger.debug("Initializing EmbeddingService...")
        if symbol_index is None:
            # Build SymbolIndex from Neo4j graph
            # This is a fallback — in production agents would pass pre-built index
            symbol_index = SymbolIndex()

        self._embedding_service = EmbeddingService(symbol_index, self.embeddings_cache_dir)
        return self._embedding_service

    def definition(self, symbol: str) -> DefinitionResult:
        """Get definition of a symbol (1-hop, fast).

        Args:
            symbol: Symbol name to look up

        Returns:
            DefinitionResult with name, labels, file, line, signature, docstring, callees.
            result.found is False if symbol not found.
        """
        try:
            pid = self.client.project_id
            pid_filter = "AND n.project_id = $pid" if pid else ""
            with self.client.driver.session() as session:
                # Find the symbol
                query = f"""
                MATCH (n {{name: $name}})
                WHERE 1=1 {pid_filter}
                RETURN n,
                       CASE WHEN n:Function THEN 0
                            WHEN n:Class THEN 1
                            ELSE 2 END as priority
                ORDER BY priority
                LIMIT 1
                """
                params: Dict[str, Any] = {"name": symbol}
                if pid:
                    params["pid"] = pid
                node = session.run(query, **params).single()

                if not node:
                    logger.debug(f"Symbol '{symbol}' not found")
                    return DefinitionResult(found=False, symbol=symbol)

                n = node["n"]
                raw: Dict[str, Any] = {
                    "found": True,
                    "name": n.get("name"),
                    "labels": list(n.labels),
                    "file": n.get("file"),
                    "line": n.get("line"),
                    "signature": n.get("signature"),
                    "docstring": n.get("docstring"),
                }

                # Get callees (1 hop only)
                callee_pid_filter = "AND callee.project_id = $pid" if pid else ""
                callees = session.run(
                    f"MATCH (n {{name: $name}})-[:CALLS]->(callee) "
                    f"WHERE 1=1 {pid_filter} {callee_pid_filter} "
                    "RETURN callee.name AS name, callee.file AS file",
                    **params,
                ).data()
                raw["callees"] = callees

                logger.debug(f"Definition for '{symbol}': found, {len(callees)} callees")
                return DefinitionResult.model_validate(raw)

        except Exception as e:
            logger.error(f"definition() error: {e}")
            return DefinitionResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def context(
        self, symbol: str, depth: int = 2, compress: bool = False
    ) -> ContextResult:
        """Get working context for a symbol (bounded bidirectional).

        Args:
            symbol: Symbol name to analyze
            depth: Max hop distance (1-10 recommended)
            compress: Remove bridge functions to save tokens

        Returns:
            ContextResult with root, nodes, edges, cycles, and compression stats.
            result.found is False if symbol not found.
        """
        try:
            # Get bounded subgraph (callees)
            subgraph = self.client.get_bounded_subgraph(symbol, max_depth=depth)
            if not subgraph:
                logger.debug(f"Symbol '{symbol}' not found in graph")
                return ContextResult(found=False, symbol=symbol)

            root = subgraph["root"]
            nodes = subgraph["nodes"]
            edges = subgraph["edges"]
            original_node_count = len(nodes)

            # Detect cycles
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

            result = {
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

            # Apply compression if requested
            if compress and node_names:
                cycle_members = {m for cg in cycle_groups for m in cg.members}
                compression_result = compress_subgraph(
                    symbol, node_names, edge_tuples, cycle_members
                )
                # Replace nodes and edges with compressed versions
                nodes = [n for n in nodes if n["name"] in compression_result.nodes]
                edges = [
                    e for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges
                ]
                # Re-detect cycles on compressed graph
                node_names = [n["name"] for n in nodes]
                edge_tuples = [(e["src"], e["dst"]) for e in edges]
                acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

                result["nodes"] = nodes
                result["edges"] = edges
                result["cycles"] = [
                    {"members": cg.members, "representative": cg.representative}
                    for cg in cycle_groups
                ]
                result["compressed"] = True
                result["bridges_removed"] = len(compression_result.bridges)
                result["final_node_count"] = len(nodes)

            # Estimate tokens
            result["token_estimate"] = sum(
                len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes
            ) // 4

            logger.debug(
                f"Context for '{symbol}': {result['final_node_count']} nodes, "
                f"{len(result['cycles'])} cycles, depth={depth}"
            )
            return ContextResult.model_validate(result)

        except Exception as e:
            logger.error(f"context() error: {e}")
            return ContextResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def impact(self, symbol: str, depth: int = 3) -> ImpactResult:
        """Analyze impact of changing a symbol (reverse traversal).

        Args:
            symbol: Symbol name to analyze
            depth: Max hop distance in reverse direction

        Returns:
            ImpactResult with callers_by_depth, total_callers, cycles, token_estimate.
            result.found is False if symbol not found.
        """
        try:
            # Get impact graph (reverse CALLS)
            impact_graph = self.client.get_impact_graph(symbol, max_depth=depth)
            if not impact_graph:
                logger.debug(f"Symbol '{symbol}' not found in graph")
                return ImpactResult(found=False, symbol=symbol)

            root = impact_graph["root"]
            nodes = impact_graph["nodes"]
            edges = impact_graph["edges"]

            # Detect cycles
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e["src"], e["dst"]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

            # Group callers by distance from root
            # Use reverse BFS to compute depth from root
            callers_by_depth: Dict[int, List[Dict[str, Any]]] = {}
            visited = {symbol}
            current_frontier = [symbol]
            current_depth = 1

            while current_frontier and current_depth <= depth:
                next_frontier = []
                callers_at_depth = []

                for caller in current_frontier:
                    # Find all nodes that call this node
                    for edge in edges:
                        if edge["dst"] == caller and edge["src"] not in visited:
                            visited.add(edge["src"])
                            next_frontier.append(edge["src"])
                            # Find node details
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

            result = {
                "found": True,
                "symbol": symbol,
                "root": root,
                "callers_by_depth": callers_by_depth,
                "total_callers": len(visited) - 1,  # exclude root
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
                f"Impact for '{symbol}': {result['total_callers']} callers, "
                f"{len(result['cycles'])} cycles"
            )
            return ImpactResult.model_validate(result)

        except Exception as e:
            logger.error(f"impact() error: {e}")
            return ImpactResult.model_validate({"found": False, "symbol": symbol, "error": str(e)})

    def search(self, query: str, top_k: int = 5) -> SearchResult:
        """Semantic search for symbols.

        Args:
            query: Natural language query or keywords
            top_k: Number of results to return

        Returns:
            SearchResult with hits list. Each hit has name, type, file, line, score.
            Returns SearchResult with empty hits list on error.

        Old return type was List[Dict]; use result.model_dump()["hits"] for compat.

        Returns:
            [
                {
                    "name": str,
                    "type": str,
                    "file": str,
                    "line": int,
                    "docstring": Optional[str],
                    "score": float,
                }, ...
            ]

        Returns empty list if no results or if embeddings are unavailable.
        """
        try:
            svc = self._get_embedding_service()
            results = svc.search(query, top_k=top_k)

            # Convert (Symbol, float) tuples to dicts
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

            logger.debug(f"Search for '{query}': {len(output)} results")
            return SearchResult.from_list(output, query=query)

        except Exception as e:
            logger.error(f"search() error: {e}")
            return SearchResult(error_reason="parse_error", error_message=str(e))

    def status(self, repo_path: Optional[Path] = None) -> StatusResult:
        """Check graph freshness and statistics.

        Args:
            repo_path: Path to git repository (defaults to cwd)

        Returns:
            StatusResult with is_fresh, git_head, graph_head, commits_behind,
            node_count, edge_count, freshness_status.
        """
        try:
            repo_path = repo_path or Path.cwd()

            # Get validation
            validation = validate_graph(self.client, repo_path)

            # Get stats
            stats = self.client.get_stats()

            # Format freshness status
            if validation.is_fresh:
                freshness_status = "fresh"
            elif validation.commits_behind < 0:
                freshness_status = "unknown"
            else:
                freshness_status = "stale"

            result = {
                "is_fresh": validation.is_fresh,
                "git_head": validation.git_head,
                "graph_head": validation.graph_head,
                "commits_behind": validation.commits_behind,
                "node_count": stats["node_count"],
                "edge_count": stats["edge_count"],
                "freshness_status": freshness_status,
            }

            logger.debug(f"Status: {freshness_status}, {stats['node_count']} nodes")
            return StatusResult.model_validate(result)

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

    def close(self) -> None:
        """Close database connection."""
        self.client.close()
        logger.debug("SMTQueryEngine closed")
