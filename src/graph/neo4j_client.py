"""Neo4j database client and query interface."""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from neo4j import GraphDatabase, Session

from src.config import settings
from src.graph.node_types import CommitNode, Edge, Node, NodeType


class Neo4jClient:
    """Neo4j database client for graph operations."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        """Initialize Neo4j client.

        Args:
            uri: Neo4j connection URI (defaults to config)
            user: Neo4j user (defaults to config)
            password: Neo4j password (defaults to config)
            database: Neo4j database name (defaults to config, enables project isolation)
        """
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        logger.info(f"Connected to Neo4j at {self.uri} (database: {self.database})")

        # Ensure database exists (create if it doesn't)
        self._ensure_database_exists()

    def _ensure_database_exists(self) -> None:
        """Ensure database connection works (uses default database with project labels)."""
        try:
            # Test connection
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
        """Delete all nodes and edges from database."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared Neo4j database")

    def create_indexes(self) -> None:
        """Create indexes for performance optimization."""
        queries = [
            "CREATE INDEX node_id_idx IF NOT EXISTS FOR (n:Node) ON (n.node_id)",
            "CREATE INDEX node_name_idx IF NOT EXISTS FOR (n:Node) ON (n.name)",
            "CREATE INDEX node_file_idx IF NOT EXISTS FOR (n:Node) ON (n.file)",
            "CREATE INDEX node_type_idx IF NOT EXISTS FOR (n:Node) ON (n.type)",
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
        CREATE (n:{node.type.value} $props)
        RETURN n
        """
        with self.driver.session() as session:
            result = session.run(cypher, props=node.to_cypher_props())
            result.consume()
        logger.debug(f"Created node: {node.node_id}")

    def create_nodes_batch(self, nodes: List[Node]) -> None:
        """Create multiple nodes efficiently.

        Args:
            nodes: List of nodes to create
        """
        if not nodes:
            return

        with self.driver.session() as session:
            for node in nodes:
                cypher = f"""
                MERGE (n:{node.type.value} {{node_id: $node_id}})
                SET n += $props
                """
                session.run(cypher, node_id=node.node_id, props=node.to_cypher_props())
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
        MERGE (source)-[r:{edge.type.value} $props]->(target)
        RETURN r
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
        """Create multiple edges efficiently.

        Args:
            edges: List of (edge, source_type, target_type) tuples
        """
        if not edges:
            return

        with self.driver.session() as session:
            for edge, source_type, target_type in edges:
                cypher = f"""
                MATCH (source:{source_type} {{node_id: $source_id}})
                MATCH (target:{target_type} {{node_id: $target_id}})
                MERGE (source)-[r:{edge.type.value}]->(target)
                SET r += $props
                """
                session.run(
                    cypher,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    props=edge.to_cypher_props(),
                )
        logger.info(f"Created {len(edges)} edges")

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID.

        Args:
            node_id: Node ID to fetch

        Returns:
            Node properties dict or None if not found
        """
        cypher = "MATCH (n {node_id: $node_id}) RETURN n"
        with self.driver.session() as session:
            result = session.run(cypher, node_id=node_id)
            record = result.single()
            return dict(record["n"]) if record else None

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[Dict]:
        """Get nodes reachable from a node within depth.

        Args:
            node_id: Starting node ID
            depth: Maximum relationship depth

        Returns:
            List of neighbor node properties dicts
        """
        cypher = f"""
        MATCH (n {{node_id: $node_id}})
        MATCH (n)-[*1..{depth}]-(neighbor)
        RETURN DISTINCT neighbor
        """
        with self.driver.session() as session:
            result = session.run(cypher, node_id=node_id)
            return [dict(record["neighbor"]) for record in result]

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics.

        Returns:
            Dict with node_count and edge_count
        """
        with self.driver.session() as session:
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
        with self.driver.session() as session:
            # Query 1: Find root node and all reachable nodes via directed CALLS edges
            query1 = f"""
            MATCH (start {{name: $name}})
            OPTIONAL MATCH path = (start)-[:CALLS*1..{max_depth}]->(reached)
            WITH start, collect(DISTINCT reached) AS reachable
            WITH [start] + reachable AS all_nodes
            UNWIND all_nodes AS n
            RETURN DISTINCT n.node_id AS node_id, n.name AS name,
                   n.file AS file, n.line AS line, labels(n) AS labels
            ORDER BY n.name
            """
            result1 = session.run(query1, name=name)
            rows1 = list(result1)

            if not rows1:
                logger.debug(f"Symbol '{name}' not found in graph")
                return {}

            # Extract root node (first row matches root by definition)
            root_dict = dict(rows1[0])
            root_dict["labels"] = root_dict.get("labels", [])

            # Collect all node_ids for edge filtering
            node_ids = {row["node_id"] for row in rows1}
            nodes = [dict(row) for row in rows1]

            # Query 2: Get CALLS edges only between nodes in this subgraph
            query2 = """
            MATCH (a)-[:CALLS]->(b)
            WHERE a.node_id IN $node_ids AND b.node_id IN $node_ids
            RETURN a.name AS src, b.name AS dst
            ORDER BY src, dst
            """
            result2 = session.run(query2, node_ids=list(node_ids))
            edges = [dict(row) for row in result2]

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

    def begin_transaction(self):
        """Open a session and begin an explicit transaction.

        Caller is responsible for calling tx.commit() or tx.rollback().

        Returns:
            neo4j Transaction object
        """
        self._active_session = self.driver.session()
        return self._active_session.begin_transaction()

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
        """Link symbols to a commit via MODIFIED_BY edges.

        Args:
            symbol_node_ids: List of symbol node_ids that changed
            commit_hash: Commit hash to link to
        """
        cypher = """
        MATCH (s {node_id: $symbol_id})
        MATCH (c:Commit {commit_hash: $commit_hash})
        MERGE (s)-[:MODIFIED_BY]->(c)
        """
        with self.driver.session() as session:
            for symbol_id in symbol_node_ids:
                session.run(cypher, symbol_id=symbol_id, commit_hash=commit_hash)
        logger.debug(f"Created {len(symbol_node_ids)} MODIFIED_BY edges to commit {commit_hash}")
