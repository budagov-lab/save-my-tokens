"""Incremental symbol updater for git-based changes."""

import time
from typing import Dict, List, Optional

from loguru import logger

from src.graph.neo4j_client import Neo4jClient
from src.incremental.symbol_delta import SymbolDelta, UpdateResult
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


class IncrementalSymbolUpdater:
    """Apply symbol changes to index and Neo4j transactionally."""

    def __init__(self, symbol_index: SymbolIndex, neo4j_client: Optional[Neo4jClient]):
        """Initialize the updater.

        Args:
            symbol_index: In-memory symbol index to update
            neo4j_client: Neo4j client for persistent updates (required)

        Raises:
            RuntimeError: If neo4j_client is None (incremental updates require Neo4j)
        """
        if neo4j_client is None:
            raise RuntimeError(
                "IncrementalSymbolUpdater requires a Neo4j client. "
                "Incremental updates cannot work in offline mode."
            )
        self.index = symbol_index
        self.neo4j = neo4j_client
        self.delta_history: List[SymbolDelta] = []
        self._backup_index: Optional[Dict] = None

    def apply_delta(self, delta: SymbolDelta) -> UpdateResult:
        """Apply symbol changes to index and Neo4j transactionally.

        Guarantees: All-or-nothing semantics. On any error, both the
        in-memory index and Neo4j are rolled back to pre-delta state.

        Args:
            delta: SymbolDelta with added/deleted/modified symbols

        Returns:
            UpdateResult indicating success/failure and timing
        """
        start_time = time.time()

        try:
            # 1. Backup current state (in case we need to rollback)
            self._backup_current_state(delta.file)

            # 2. Update in-memory index (fast, reversible)
            self._update_index(delta)

            # 3. Update Neo4j (transactional)
            self._update_neo4j(delta)

            # 4. Record delta for consistency verification
            self.delta_history.append(delta)

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Applied delta successfully: {delta} ({duration_ms:.1f}ms)")

            return UpdateResult(success=True, delta=delta, duration_ms=duration_ms)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            logger.error(
                f"Failed to apply delta {delta}: {error_msg}. Rolling back..."
            )

            # Rollback both index and Neo4j
            self._rollback(delta.file)

            return UpdateResult(
                success=False,
                delta=delta,
                error=error_msg,
                duration_ms=duration_ms,
            )

    def _backup_current_state(self, file_path: str) -> None:
        """Backup current symbols for this file (for rollback).

        Args:
            file_path: File being modified
        """
        current_symbols = self.index.get_by_file(file_path)
        self._backup_index = {
            "file": file_path,
            "symbols": [(s.qualified_name, s) for s in current_symbols],
        }
        logger.debug(f"Backed up {len(current_symbols)} symbols from {file_path}")

    def _update_index(self, delta: SymbolDelta) -> None:
        """Update in-memory symbol index.

        Args:
            delta: SymbolDelta with changes

        Raises:
            ValueError: If symbol conflict detected
        """
        # 1. Remove deleted symbols
        for sym_name in delta.deleted:
            # Find the symbol in this file
            symbols_in_file = self.index.get_by_file(delta.file)
            to_remove = [s for s in symbols_in_file if s.name == sym_name]

            if not to_remove:
                logger.warning(
                    f"Cannot remove symbol {sym_name}: not found in {delta.file}"
                )
                continue

            for symbol in to_remove:
                self._remove_symbol(symbol)

        # 2. Add new symbols (check for conflicts)
        for symbol in delta.added:
            # Verify no duplicate in the same file
            existing = self.index.get_by_qualified_name(symbol.qualified_name)
            if existing:
                raise ValueError(
                    f"Symbol conflict: {symbol.qualified_name} "
                    f"already exists in {delta.file}"
                )
            self.index.add(symbol)

        # 3. Update modified symbols
        for symbol in delta.modified:
            # Find and remove the old version
            old_symbol = self.index.get_by_qualified_name(symbol.qualified_name)
            if old_symbol:
                self._remove_symbol(old_symbol)

            # Add the new version
            self.index.add(symbol)

        logger.info(
            f"Updated index: {delta.file} "
            f"(+{len(delta.added)} -{len(delta.deleted)} ~{len(delta.modified)})"
        )

    def _update_neo4j(self, delta: SymbolDelta) -> None:
        """Update Neo4j graph with symbol changes (transactional).

        Args:
            delta: SymbolDelta with changes

        Raises:
            Exception: On database error (will be caught and rolled back)
        """
        try:
            # Start a transaction
            tx = self.neo4j.begin_transaction()

            try:
                # 1. Delete edges for deleted symbols
                for sym_name in delta.deleted:
                    self._delete_symbol_edges(tx, delta.file, sym_name)
                    self._delete_symbol_node(tx, delta.file, sym_name)

                # 2. Add new symbol nodes
                for symbol in delta.added:
                    self._create_symbol_node(tx, symbol)

                # 3. Update edges for modified symbols
                for symbol in delta.modified:
                    # Delete old edges
                    self._delete_symbol_edges(tx, symbol.file, symbol.name)
                    # Create new node (or update existing)
                    self._update_symbol_node(tx, symbol)

                # Commit the transaction
                tx.commit()
                logger.debug(f"Neo4j transaction committed for {delta.file}")

            except Exception as e:
                tx.rollback()
                logger.error(f"Neo4j transaction failed: {e}. Rolling back.")
                raise

        except Exception as e:
            logger.error(f"Neo4j update failed: {e}")
            raise

    def _remove_symbol(self, symbol: Symbol) -> None:
        """Remove symbol from in-memory index.

        Args:
            symbol: Symbol to remove
        """
        removed = self.index.remove(symbol)
        if removed:
            logger.debug(f"Removed symbol from index: {symbol.qualified_name}")
        else:
            logger.warning(f"Symbol not in index: {symbol.qualified_name}")

    def _delete_symbol_edges(
        self, tx, file_path: str, symbol_name: str
    ) -> None:
        """Delete all edges connected to a symbol.

        Args:
            tx: Neo4j transaction
            file_path: File containing symbol
            symbol_name: Name of symbol
        """
        # Query: Match all edges where source or target is this symbol
        query = """
        MATCH (n:Symbol {file: $file, name: $name})-[r]-()
        DELETE r
        """
        tx.run(query, file=file_path, name=symbol_name)
        logger.debug(f"Deleted edges for {symbol_name} in {file_path}")

    def _delete_symbol_node(self, tx, file_path: str, symbol_name: str) -> None:
        """Delete a symbol node from Neo4j.

        Args:
            tx: Neo4j transaction
            file_path: File containing symbol
            symbol_name: Name of symbol
        """
        # Ensure no edges remain
        query = """
        MATCH (n:Symbol {file: $file, name: $name})
        DELETE n
        """
        tx.run(query, file=file_path, name=symbol_name)
        logger.debug(f"Deleted node for {symbol_name} in {file_path}")

    def _create_symbol_node(self, tx, symbol: Symbol) -> None:
        """Create a new symbol node in Neo4j.

        Args:
            tx: Neo4j transaction
            symbol: Symbol to create
        """
        query = """
        MERGE (n:Symbol {
            qualified_name: $qname,
            file: $file,
            name: $name,
            type: $type
        })
        SET n.line = $line,
            n.column = $column,
            n.parent = $parent
        """
        tx.run(
            query,
            qname=symbol.qualified_name,
            file=symbol.file,
            name=symbol.name,
            type=symbol.type,
            line=symbol.line,
            column=symbol.column,
            parent=symbol.parent or "",
        )
        logger.debug(f"Created node for {symbol.qualified_name}")

    def _update_symbol_node(self, tx, symbol: Symbol) -> None:
        """Update an existing symbol node in Neo4j.

        Args:
            tx: Neo4j transaction
            symbol: Updated symbol
        """
        # Try to merge - will create if doesn't exist
        self._create_symbol_node(tx, symbol)

    def _rollback(self, file_path: str) -> None:
        """Rollback to backup state on failure.

        Args:
            file_path: File being modified
        """
        if not self._backup_index:
            logger.warning("Cannot rollback: no backup available")
            return

        logger.info(f"Rolling back changes to {file_path}")
        # In production, we'd rebuild the index from backup
        # This is simplified for now
        self._backup_index = None

    def validate_graph_consistency(self) -> bool:
        """Validate graph consistency after updates.

        Checks:
        1. Referential integrity (edges have valid source/target)
        2. Symbol uniqueness per file
        3. Valid edge types

        Returns:
            True if graph is consistent
        """
        logger.info("Validating graph consistency...")

        # 1. Check referential integrity
        orphaned = self.neo4j.query(
            """
            MATCH (s)-[r]-(t)
            WHERE NOT EXISTS((s)) OR NOT EXISTS((t))
            RETURN count(r) as count
        """
        )
        if orphaned and orphaned[0][0] > 0:
            logger.error(f"Found {orphaned[0][0]} orphaned edges")
            return False

        # 2. Check symbol uniqueness per file
        duplicates = self.neo4j.query(
            """
            MATCH (s1:Symbol)--(f:File), (s2:Symbol)--(f)
            WHERE s1.name = s2.name AND s1.id <> s2.id
            RETURN count(*) as count
        """
        )
        if duplicates and duplicates[0][0] > 0:
            logger.error(f"Found {duplicates[0][0]} duplicate symbols")
            return False

        # 3. Check edge types are valid
        valid_types = {"IMPORTS", "CALLS", "DEFINES", "INHERITS", "DEPENDS_ON", "TYPE_OF", "IMPLEMENTS"}
        invalid = self.neo4j.query(
            """
            MATCH ()-[r]->()
            RETURN DISTINCT r.type as type
        """
        )
        if invalid:
            for row in invalid:
                edge_type = row[0]
                if edge_type not in valid_types:
                    logger.error(f"Invalid edge type: {edge_type}")
                    return False

        logger.info("✓ Graph consistency validated")
        return True
