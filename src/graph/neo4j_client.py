"""Neo4j database client and query interface."""

from typing import Dict, List, Optional, Tuple

from loguru import logger
from neo4j import GraphDatabase, Session

from src.config import settings
from src.graph.node_types import Edge, Node, NodeType


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
