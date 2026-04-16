"""Neo4j database client and query interface."""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from neo4j import GraphDatabase, Session

from src.config import settings
from src.graph.node_types import CommitNode, Edge, Node, NodeType


class _ManagedTransaction:
    """Context manager that wraps a Neo4j session + transaction.

    Commits on clean exit, rolls back and closes session on any exception.
    Prevents the session-leak pattern of bare begin_transaction() calls.
    """

    def __init__(self, driver):
        self._driver = driver
        self._session = None
        self._tx = None

    def __enter__(self):
        self._session = self._driver.session()
        self._tx = self._session.begin_transaction()
        return self._tx

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._tx.commit()
            else:
                self._tx.rollback()
        finally:
            self._session.close()
        return False  # never suppress exceptions


class Neo4jClient:
    """Neo4j database client for graph operations."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        project_id: str = "",
    ):
        """Initialize Neo4j client.

        Args:
            uri: Neo4j connection URI (defaults to config)
            user: Neo4j user (defaults to config)
            password: Neo4j password (defaults to config)
            database: Neo4j database name (defaults to config)
            project_id: Project namespace — all reads/writes are scoped to this ID
        """
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE
        self.project_id = project_id
        if self.password == "password":
            logger.warning(
                "Neo4j is using the default password 'password'. "
                "Set NEO4J_PASSWORD in your .env file before exposing this service."
            )
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        logger.info(f"Connected to Neo4j at {self.uri} (database: {self.database}, project: {self.project_id or 'ALL'})")

        # Ensure database exists (create if it doesn't)
        self._ensure_database_exists()

    def _ensure_database_exists(self) -> None:
        """Verify the Neo4j connection is usable."""
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def close(self) -> None:
        """Close database connection."""
        self.driver.close()
        logger.info("Closed Neo4j connection")

    def clear_database(self) -> None:
        """Delete all nodes (and their edges) for the current project.

        Raises:
            RuntimeError: If project_id is not set — refuses to wipe the entire database.
        """
        if not self.project_id:
            raise RuntimeError(
                "clear_database() refused: project_id is not set. "
                "Instantiate Neo4jClient with a project_id to scope the clear operation."
            )
        with self.driver.session() as session:
            session.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=self.project_id)
            logger.info(f"Cleared Neo4j nodes for project: {self.project_id}")

    def create_indexes(self) -> None:
        """Create indexes for performance optimization."""
        queries = [
            "CREATE INDEX node_id_idx IF NOT EXISTS FOR (n:Node) ON (n.node_id)",
            "CREATE INDEX node_name_idx IF NOT EXISTS FOR (n:Node) ON (n.name)",
            "CREATE INDEX node_file_idx IF NOT EXISTS FOR (n:Node) ON (n.file)",
            "CREATE INDEX node_type_idx IF NOT EXISTS FOR (n:Node) ON (n.type)",
            "CREATE INDEX node_project_idx IF NOT EXISTS FOR (n:Node) ON (n.project_id)",
            "CREATE INDEX commit_hash_idx IF NOT EXISTS FOR (c:Commit) ON (c.commit_hash)",
        ]
        with self.driver.session() as session:
            for query in queries:
                try:
                    session.run(query)
                except Exception as e:
                    logger.debug(f"Index creation skipped: {e}")
        logger.info("Indexes ready")

    def create_node(self, node: Node) -> None:
        """Create a node in the graph.

        Args:
            node: Node to create
        """
        cypher = f"""
        MERGE (n:{node.type.value} {{node_id: $node_id}})
        SET n += $props
        """
        props = node.to_cypher_props()
        with self.driver.session() as session:
            result = session.run(cypher, node_id=node.node_id, props=props)
            result.consume()
        logger.debug(f"Created node: {node.node_id}")

    def create_nodes_batch(self, nodes: List[Node]) -> None:
        """Create multiple nodes in a single transaction (atomic — all or nothing).

        Args:
            nodes: List of nodes to create
        """
        if not nodes:
            return

        # Group nodes by type so we can use UNWIND per label (labels can't be parameterised)
        by_type: Dict[str, List[Dict]] = {}
        for node in nodes:
            by_type.setdefault(node.type.value, []).append(node.to_cypher_props())

        # All label groups in ONE transaction — if any label fails the whole batch rolls back.
        with self.transaction() as tx:
            for label, batch in by_type.items():
                tx.run(
                    f"UNWIND $batch AS props MERGE (n:{label} {{node_id: props.node_id}}) SET n += props",
                    batch=batch,
                )
        logger.info(f"Created {len(nodes)} nodes")

    def create_edge(self, edge: Edge, source_type: str, target_type: str) -> None:
        """Create an edge between two nodes.

        Args:
            edge: Edge to create
            source_type: Neo4j label of source node
            target_type: Neo4j label of target node
        """
        cypher = f"""
        MATCH (source:{source_type} {{node_id: $source_id}})
        MATCH (target:{target_type} {{node_id: $target_id}})
        MERGE (source)-[r:{edge.type.value}]->(target)
        SET r += $props
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                source_id=edge.source_id,
                target_id=edge.target_id,
                props=edge.to_cypher_props(),
            )
            result.consume()
        logger.debug(f"Created edge: {edge.source_id} -[{edge.type.value}]-> {edge.target_id}")

    def create_edges_batch(self, edges: List[Tuple[Edge, str, str]]) -> None:
        """Create multiple edges in a single transaction per edge-type combination (atomic).

        Args:
            edges: List of (edge, source_type, target_type) tuples
        """
        if not edges:
            return

        # Group by (edge_type, source_label, target_label) — labels can't be parameterised
        by_signature: Dict[Tuple[str, str, str], List[Dict]] = {}
        for edge, source_type, target_type in edges:
            key = (edge.type.value, source_type, target_type)
            by_signature.setdefault(key, []).append({
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "props": edge.to_cypher_props(),
            })

        # All edge-type groups in ONE transaction — if any group fails the whole batch rolls back.
        with self.transaction() as tx:
            for (edge_type, src_label, tgt_label), batch in by_signature.items():
                tx.run(
                    f"""
                    UNWIND $batch AS row
                    MATCH (source:{src_label} {{node_id: row.source_id}})
                    MATCH (target:{tgt_label} {{node_id: row.target_id}})
                    MERGE (source)-[r:{edge_type}]->(target)
                    SET r += row.props
                    """,
                    batch=batch,
                )
        logger.info(f"Created {len(edges)} edges")

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID (scoped to current project).

        Args:
            node_id: Node ID to fetch

        Returns:
            Node properties dict or None if not found
        """
        if self.project_id:
            cypher = "MATCH (n {node_id: $node_id, project_id: $pid}) RETURN n"
            with self.driver.session() as session:
                result = session.run(cypher, node_id=node_id, pid=self.project_id)
                record = result.single()
                return dict(record["n"]) if record else None
        cypher = "MATCH (n {node_id: $node_id}) RETURN n"
        with self.driver.session() as session:
            result = session.run(cypher, node_id=node_id)
            record = result.single()
            return dict(record["n"]) if record else None

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[Dict]:
        """Get nodes reachable from a node within depth (scoped to current project).

        Args:
            node_id: Starting node ID
            depth: Maximum relationship depth (clamped to 1-10)

        Returns:
            List of neighbor node properties dicts
        """
        depth = max(1, min(depth, 10))
        pid_filter = " {project_id: $pid}" if self.project_id else ""
        cypher = f"""
        MATCH (n{pid_filter} {{node_id: $node_id}})
        MATCH (n)-[:CALLS*1..{depth}]->(neighbor{pid_filter})
        RETURN DISTINCT neighbor
        LIMIT 500
        """
        params: Dict[str, Any] = {"node_id": node_id}
        if self.project_id:
            params["pid"] = self.project_id
        with self.driver.session() as session:
            result = session.run(cypher, **params)
            return [dict(record["neighbor"]) for record in result]

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics (scoped to current project if project_id is set).

        Returns:
            Dict with node_count and edge_count
        """
        with self.driver.session() as session:
            if self.project_id:
                node_result = session.run(
                    "MATCH (n {project_id: $pid}) RETURN COUNT(n) as count", pid=self.project_id
                )
                node_count = node_result.single()["count"]
                # Edges: count only edges between nodes in this project
                edge_result = session.run(
                    "MATCH (a {project_id: $pid})-[r]->(b {project_id: $pid}) RETURN COUNT(r) as count",
                    pid=self.project_id,
                )
            else:
                node_result = session.run("MATCH (n) RETURN COUNT(n) as count")
                node_count = node_result.single()["count"]
                edge_result = session.run("MATCH ()-[r]->() RETURN COUNT(r) as count")
            edge_count = edge_result.single()["count"]

        return {"node_count": node_count, "edge_count": edge_count}

    def get_bounded_subgraph(self, name: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get all nodes and directed CALLS edges reachable from a symbol within max_depth.

        Args:
            name: Symbol name to start from
            max_depth: Maximum hop distance (1-10 recommended)

        Returns:
            {
                "root": {node properties dict},
                "nodes": [{node_id, name, file, line, labels}, ...],
                "edges": [{src: name, dst: name}, ...],
                "depth_reached": actual max depth traversed
            }

        Returns empty dict if symbol not found.
        """
        max_depth = max(1, min(max_depth, 10))
        params: Dict[str, Any] = {"name": name}
        if self.project_id:
            params["pid"] = self.project_id

        # Single merged query: traverse nodes + collect edges in one round trip.
        # node_rows is built as a list comprehension (scalar) before UNWIND so it
        # survives the per-row explosion. OPTIONAL MATCH after UNWIND finds intra-
        # subgraph edges; NULLs (unmatched OPTIONALs) are stripped in RETURN.
        if self.project_id:
            query = f"""
            MATCH (start {{name: $name}})
            WHERE start.project_id = $pid
            OPTIONAL MATCH (start)-[:CALLS*1..{max_depth}]->(reached)
            WHERE reached.project_id = $pid
            WITH start, collect(DISTINCT reached) AS reachable
            WITH start, [start] + reachable AS all_nodes
            WITH start,
                 [n IN all_nodes | {{
                     node_id: n.node_id, name: n.name, file: n.file, line: n.line,
                     labels: labels(n), is_root: (n.node_id = start.node_id)
                 }}] AS node_rows,
                 all_nodes
            UNWIND all_nodes AS a
            OPTIONAL MATCH (a)-[:CALLS]->(b)
            WHERE b IN all_nodes AND a.project_id = $pid AND b.project_id = $pid
            WITH node_rows,
                 collect(DISTINCT CASE WHEN b IS NOT NULL
                     THEN {{src: a.name, dst: b.name}} ELSE null END) AS raw_edges
            RETURN node_rows AS nodes,
                   [e IN raw_edges WHERE e IS NOT NULL] AS edges
            """
        else:
            query = f"""
            MATCH (start {{name: $name}})
            OPTIONAL MATCH (start)-[:CALLS*1..{max_depth}]->(reached)
            WITH start, collect(DISTINCT reached) AS reachable
            WITH start, [start] + reachable AS all_nodes
            WITH start,
                 [n IN all_nodes | {{
                     node_id: n.node_id, name: n.name, file: n.file, line: n.line,
                     labels: labels(n), is_root: (n.node_id = start.node_id)
                 }}] AS node_rows,
                 all_nodes
            UNWIND all_nodes AS a
            OPTIONAL MATCH (a)-[:CALLS]->(b)
            WHERE b IN all_nodes
            WITH node_rows,
                 collect(DISTINCT CASE WHEN b IS NOT NULL
                     THEN {{src: a.name, dst: b.name}} ELSE null END) AS raw_edges
            RETURN node_rows AS nodes,
                   [e IN raw_edges WHERE e IS NOT NULL] AS edges
            """

        with self.driver.session() as session:
            result = session.run(query, **params)
            row = result.single()

        if not row:
            logger.debug(f"Symbol '{name}' not found in graph")
            return {}

        nodes: List[Dict[str, Any]] = [dict(n) for n in row["nodes"]]
        edges: List[Dict[str, Any]] = [dict(e) for e in row["edges"]]

        root_dict = next((n for n in nodes if n.get("is_root")), nodes[0] if nodes else {})

        logger.debug(
            f"Bounded subgraph for '{name}': {len(nodes)} nodes, "
            f"{len(edges)} edges, depth={max_depth}"
        )

        return {
            "root": root_dict,
            "nodes": nodes,
            "edges": edges,
            "depth_reached": max_depth,
        }

    def get_impact_graph(self, name: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get all nodes that call this symbol, directly or indirectly (reverse CALLS traversal).

        Used for impact analysis: "what breaks if I change this?"

        Args:
            name: Symbol name to start from
            max_depth: Maximum hop distance in reverse direction (1-10 recommended)

        Returns:
            {
                "root": {node properties dict},
                "nodes": [{node_id, name, file, line, labels}, ...],
                "edges": [{src: name, dst: name}, ...],
                "depth_reached": actual max depth traversed
            }

        Returns empty dict if symbol not found.
        """
        max_depth = max(1, min(max_depth, 10))
        params: Dict[str, Any] = {"name": name}
        if self.project_id:
            params["pid"] = self.project_id

        # Single merged query: reverse traversal (callers) + intra-set edges in one trip.
        # Same pattern as get_bounded_subgraph but traversal direction is reversed.
        if self.project_id:
            query = f"""
            MATCH (start {{name: $name}})
            WHERE start.project_id = $pid
            OPTIONAL MATCH (caller)-[:CALLS*1..{max_depth}]->(start)
            WHERE caller.project_id = $pid
            WITH start, collect(DISTINCT caller) AS callers
            WITH start, [start] + callers AS all_nodes
            WITH start,
                 [n IN all_nodes | {{
                     node_id: n.node_id, name: n.name, file: n.file, line: n.line,
                     labels: labels(n), is_root: (n.node_id = start.node_id)
                 }}] AS node_rows,
                 all_nodes
            UNWIND all_nodes AS a
            OPTIONAL MATCH (a)-[:CALLS]->(b)
            WHERE b IN all_nodes AND a.project_id = $pid AND b.project_id = $pid
            WITH node_rows,
                 collect(DISTINCT CASE WHEN b IS NOT NULL
                     THEN {{src: a.name, dst: b.name}} ELSE null END) AS raw_edges
            RETURN node_rows AS nodes,
                   [e IN raw_edges WHERE e IS NOT NULL] AS edges
            """
        else:
            query = f"""
            MATCH (start {{name: $name}})
            OPTIONAL MATCH (caller)-[:CALLS*1..{max_depth}]->(start)
            WITH start, collect(DISTINCT caller) AS callers
            WITH start, [start] + callers AS all_nodes
            WITH start,
                 [n IN all_nodes | {{
                     node_id: n.node_id, name: n.name, file: n.file, line: n.line,
                     labels: labels(n), is_root: (n.node_id = start.node_id)
                 }}] AS node_rows,
                 all_nodes
            UNWIND all_nodes AS a
            OPTIONAL MATCH (a)-[:CALLS]->(b)
            WHERE b IN all_nodes
            WITH node_rows,
                 collect(DISTINCT CASE WHEN b IS NOT NULL
                     THEN {{src: a.name, dst: b.name}} ELSE null END) AS raw_edges
            RETURN node_rows AS nodes,
                   [e IN raw_edges WHERE e IS NOT NULL] AS edges
            """

        with self.driver.session() as session:
            result = session.run(query, **params)
            row = result.single()

        if not row:
            logger.debug(f"Symbol '{name}' not found in graph")
            return {}

        nodes: List[Dict[str, Any]] = [dict(n) for n in row["nodes"]]
        edges: List[Dict[str, Any]] = [dict(e) for e in row["edges"]]

        root_dict = next((n for n in nodes if n.get("is_root")), nodes[0] if nodes else {})

        logger.debug(
            f"Impact graph for '{name}': {len(nodes)} nodes, "
            f"{len(edges)} edges, depth={max_depth}"
        )

        return {
            "root": root_dict,
            "nodes": nodes,
            "edges": edges,
            "depth_reached": max_depth,
        }

    def transaction(self):
        """Context manager for explicit transactions. Use with `with client.transaction() as tx:`.

        Commits on clean exit, rolls back on exception, always closes the session.

        Example:
            with client.transaction() as tx:
                tx.run("MERGE (n:Node {id: $id})", id="foo")
                # auto-committed here
        """
        return _ManagedTransaction(self.driver)

    def create_commit_node(self, commit: CommitNode) -> None:
        """Create a commit node in the graph.

        Args:
            commit: CommitNode to create
        """
        cypher = """
        MERGE (c:Commit {commit_hash: $hash})
        SET c += $props
        """
        with self.driver.session() as session:
            session.run(cypher, hash=commit.commit_hash, props=commit.to_cypher_props())
        logger.debug(f"Created commit node: {commit.short_hash}")

    def create_modified_by_edges(self, symbol_node_ids: List[str], commit_hash: str) -> None:
        """Link symbols to a commit via MODIFIED_BY edges (single batched query).

        Args:
            symbol_node_ids: List of symbol node_ids that changed
            commit_hash: Commit hash to link to
        """
        if not symbol_node_ids:
            return
        pid_filter = " AND s.project_id = $pid" if self.project_id else ""
        cypher = f"""
        MATCH (c:Commit {{commit_hash: $commit_hash}})
        UNWIND $symbol_ids AS symbol_id
        MATCH (s {{node_id: symbol_id}})
        WHERE 1=1{pid_filter}
        MERGE (s)-[:MODIFIED_BY]->(c)
        """
        params: Dict[str, Any] = {"commit_hash": commit_hash, "symbol_ids": symbol_node_ids}
        if self.project_id:
            params["pid"] = self.project_id
        with self.driver.session() as session:
            session.run(cypher, **params)
        logger.debug(f"Created {len(symbol_node_ids)} MODIFIED_BY edges to commit {commit_hash}")
