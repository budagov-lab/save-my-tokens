"""Query service for graph API endpoints."""

from typing import Dict, List, Optional

from loguru import logger

from src.embeddings import EmbeddingService
from src.graph.neo4j_client import Neo4jClient
from src.parsers.symbol_index import SymbolIndex


class QueryService:
    """Service for querying the dependency graph."""

    def __init__(
        self,
        symbol_index: SymbolIndex,
        neo4j_client: Optional[Neo4jClient] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """Initialize query service.

        Args:
            symbol_index: Symbol index for symbol lookup
            neo4j_client: Neo4j client for graph queries
            embedding_service: Embedding service for semantic search
        """
        self.symbol_index = symbol_index
        self.neo4j_client = neo4j_client
        self.embedding_service = embedding_service

    def get_context(
        self, symbol_name: str, depth: int = 1, include_callers: bool = False
    ) -> Dict:
        """Get minimal context for a symbol.

        Args:
            symbol_name: Name of symbol to get context for
            depth: Maximum depth of dependencies to include
            include_callers: Whether to include reverse dependencies (callers)

        Returns:
            Dictionary with symbol info and dependencies
        """
        # Find the symbol
        candidates = self.symbol_index.get_by_name(symbol_name)
        if not candidates:
            logger.warning(f"Symbol not found: {symbol_name}")
            return {"error": f"Symbol '{symbol_name}' not found", "symbol": None}

        symbol = candidates[0]
        response = {
            "symbol": {
                "name": symbol.name,
                "type": symbol.type,
                "file": symbol.file,
                "line": symbol.line,
                "column": symbol.column,
                "node_id": symbol.node_id,
                "docstring": symbol.docstring,
            },
            "dependencies": [],
            "callers": [] if include_callers else None,
            "token_estimate": 0,
        }

        # Get direct dependencies (callees)
        if symbol.type in ("function", "class"):
            # For now, return empty (would query Neo4j in production)
            # This would look for CALLS and DEPENDS_ON edges
            response["dependencies"] = []

        # Get callers if requested
        if include_callers:
            # Would query for reverse CALLS relationships
            response["callers"] = []

        # Estimate token count (rough heuristic: 4 chars ≈ 1 token)
        estimated_chars = len(str(response))
        response["token_estimate"] = estimated_chars // 4

        logger.info(f"Got context for {symbol_name}: {response['token_estimate']} tokens")
        return response

    def get_subgraph(self, symbol_name: str, depth: int = 2) -> Dict:
        """Get dependency subgraph for a symbol.

        Args:
            symbol_name: Name of symbol to get subgraph for
            depth: Maximum depth of traversal

        Returns:
            Dictionary with nodes and edges in the subgraph
        """
        # Find the symbol
        candidates = self.symbol_index.get_by_name(symbol_name)
        if not candidates:
            logger.warning(f"Symbol not found: {symbol_name}")
            return {"error": f"Symbol '{symbol_name}' not found"}

        symbol = candidates[0]

        # In production, would query Neo4j with:
        # MATCH (source {node_id: $start})
        # MATCH (source)-[*1..depth]-(reachable)
        # RETURN DISTINCT reachable

        response = {
            "root_symbol": symbol.name,
            "nodes": [
                {
                    "node_id": symbol.node_id,
                    "name": symbol.name,
                    "type": symbol.type,
                    "file": symbol.file,
                    "line": symbol.line,
                }
            ],
            "edges": [],
            "depth": depth,
            "token_estimate": 0,
        }

        # Estimate token count
        estimated_chars = len(str(response))
        response["token_estimate"] = estimated_chars // 4

        logger.info(f"Got subgraph for {symbol_name}: {len(response['nodes'])} nodes")
        return response

    def semantic_search(self, query: str, top_k: int = 5) -> Dict:
        """Search for symbols matching query.

        Args:
            query: Natural language or code snippet query
            top_k: Number of top results to return

        Returns:
            List of matching symbols with similarity scores
        """
        results = []

        # Use embedding service if available
        if self.embedding_service:
            try:
                search_results = self.embedding_service.search(query, top_k=top_k)
                for symbol, similarity_score in search_results:
                    results.append(
                        {
                            "symbol_name": symbol.name,
                            "symbol_type": symbol.type,
                            "file": symbol.file,
                            "line": symbol.line,
                            "node_id": symbol.node_id,
                            "similarity_score": similarity_score,
                        }
                    )
            except Exception as e:
                logger.warning(f"Embedding search failed: {e}. Falling back to substring search.")
                results = self._fallback_search(query, top_k)
        else:
            # Fallback to simple substring search
            results = self._fallback_search(query, top_k)

        logger.info(f"Semantic search for '{query}': {len(results)} results")
        return {
            "query": query,
            "results": results,
            "top_k": top_k,
        }

    def _fallback_search(self, query: str, top_k: int) -> List[Dict]:
        """Fallback substring search.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of result dictionaries
        """
        results = []
        all_symbols = self.symbol_index.get_all()

        # Simple matching: if query is substring of symbol name or docstring
        for symbol in all_symbols:
            match_score = 0.0
            if query.lower() in symbol.name.lower():
                match_score = 0.8
            elif symbol.docstring and query.lower() in symbol.docstring.lower():
                match_score = 0.5

            if match_score > 0:
                results.append(
                    {
                        "symbol_name": symbol.name,
                        "symbol_type": symbol.type,
                        "file": symbol.file,
                        "line": symbol.line,
                        "node_id": symbol.node_id,
                        "similarity_score": match_score,
                    }
                )

        # Sort by score and return top_k
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]

    def validate_conflicts(self, tasks: List[Dict]) -> Dict:
        """Validate conflicts between parallel tasks.

        Args:
            tasks: List of task dicts with 'id' and 'target_symbols' fields

        Returns:
            Conflict report with detected conflicts and parallel feasibility
        """
        if not tasks:
            return {"tasks": [], "conflicts": [], "parallel_feasible": True}

        # Simple conflict detection: if two tasks modify overlapping symbols
        conflicts = []

        for i, task_a in enumerate(tasks):
            for task_b in tasks[i + 1 :]:
                symbols_a = set(task_a.get("target_symbols", []))
                symbols_b = set(task_b.get("target_symbols", []))

                overlap = symbols_a & symbols_b
                if overlap:
                    conflicts.append(
                        {
                            "task_a": task_a.get("id", f"task_{i}"),
                            "task_b": task_b.get("id", f"task_{i+1}"),
                            "shared_symbols": list(overlap),
                        }
                    )

        # Tasks are parallelizable if no conflicts
        parallel_feasible = len(conflicts) == 0

        logger.info(f"Conflict validation: {len(conflicts)} conflicts, parallel_feasible={parallel_feasible}")
        return {
            "tasks": [t.get("id", f"task_{i}") for i, t in enumerate(tasks)],
            "conflicts": conflicts,
            "parallel_feasible": parallel_feasible,
        }
