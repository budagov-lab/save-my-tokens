"""Incremental symbol updater for git-based changes."""

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from src.graph.neo4j_client import Neo4jClient
from src.graph.node_types import CommitNode
from src.incremental.diff_parser import DiffParser
from src.incremental.symbol_delta import SymbolDelta, UpdateResult
from src.parsers.python_parser import PythonParser
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex

try:
    from src.parsers.typescript_parser import TypeScriptParser
except ImportError:
    TypeScriptParser = None  # type: ignore[name-defined]

try:
    from src.parsers.go_parser import GoParser
except ImportError:
    GoParser = None  # type: ignore[name-defined]

try:
    from src.parsers.rust_parser import RustParser
except ImportError:
    RustParser = None  # type: ignore[name-defined]

try:
    from src.parsers.java_parser import JavaParser
except ImportError:
    JavaParser = None  # type: ignore[name-defined]


class IncrementalSymbolUpdater:
    """Apply symbol changes to index and Neo4j transactionally."""

    def __init__(
        self,
        symbol_index: SymbolIndex,
        neo4j_client: Optional[Neo4jClient],
        embedding_service=None,
        base_path: Optional[str] = None,
    ):
        """Initialize the updater.

        Args:
            symbol_index: In-memory symbol index to update
            neo4j_client: Neo4j client for persistent updates (required)
            embedding_service: Optional embedding service for incremental updates
            base_path: Base path for code parsing (required for update_from_git)

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
        self.embedding_service = embedding_service
        self.base_path = Path(base_path) if base_path else None
        self.delta_history: List[SymbolDelta] = []
        self._backup_index: Optional[Dict] = None

        # Initialize parsers
        self.python_parser = PythonParser(str(base_path)) if base_path else None
        self.typescript_parser = TypeScriptParser(str(base_path)) if base_path and TypeScriptParser else None  # type: ignore[operator]
        self.go_parser = GoParser(str(base_path)) if base_path and GoParser else None  # type: ignore[operator]
        self.rust_parser = RustParser(str(base_path)) if base_path and RustParser else None  # type: ignore[operator]
        self.java_parser = JavaParser(str(base_path)) if base_path and JavaParser else None  # type: ignore[operator]

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
            Exception: On database error (will be caught by apply_delta for rollback)
        """
        with self.neo4j.transaction() as tx:
            # 1. Delete nodes (+ edges via DETACH) for deleted symbols
            for sym_name in delta.deleted:
                self._delete_symbol_node(tx, delta.file, sym_name)

            # 2. Add new symbol nodes
            for symbol in delta.added:
                self._create_symbol_node(tx, symbol)

            # 3. Replace modified symbol nodes (delete old, create new)
            for symbol in delta.modified:
                self._delete_symbol_node(tx, symbol.file, symbol.name)
                self._create_symbol_node(tx, symbol)

        logger.debug(f"Neo4j transaction committed for {delta.file}")

    # Maps NodeType.value → Symbol.type (inverse of GraphBuilder._map_symbol_type_to_node_type)
    _LABEL_TO_SYM_TYPE: Dict[str, str] = {
        "Function": "function",
        "Class": "class",
        "Variable": "variable",
        "Module": "import",
        "Type": "type",
        "Interface": "interface",
    }

    @staticmethod
    def _symbol_type_to_label(sym_type: str) -> str:
        """Map Symbol.type string ('function', 'class', …) to Neo4j label."""
        mapping = {
            "function": "Function",
            "class": "Class",
            "variable": "Variable",
            "import": "Module",
            "type": "Type",
            "interface": "Interface",
        }
        return mapping.get(sym_type, "Variable")

    def _query_symbols_in_file(self, file_path: str) -> List[Symbol]:
        """Query Neo4j for all symbol nodes in a file (the 'before' state for delta computation)."""
        pid = self.neo4j.project_id or ""
        pid_filter = "AND n.project_id = $pid" if pid else ""
        query = f"""
        MATCH (n)
        WHERE n.file = $file AND n.name IS NOT NULL
              AND NOT n:File AND NOT n:Commit
              {pid_filter}
        RETURN n.name AS name, n.type AS ntype, n.file AS file,
               n.line AS line, n.column AS col, n.parent AS parent
        """
        params: Dict[str, Any] = {"file": file_path}
        if pid:
            params["pid"] = pid
        symbols: List[Symbol] = []
        with self.neo4j.driver.session() as session:
            for row in session.run(query, **params):
                # ntype is the NodeType.value stored in the node (e.g. "Function")
                sym_type = self._LABEL_TO_SYM_TYPE.get(row["ntype"] or "", "variable")
                symbols.append(Symbol(
                    name=row["name"],
                    type=sym_type,
                    file=row["file"],
                    line=row["line"] or 1,
                    column=row["col"] or 0,
                    parent=row["parent"],
                ))
        return symbols

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

    def _delete_symbol_node(self, tx, file_path: str, symbol_name: str) -> None:
        """Delete a symbol node and all its edges from Neo4j (DETACH DELETE)."""
        pid = self.neo4j.project_id or ""
        pid_clause = "AND n.project_id = $pid" if pid else ""
        query = f"MATCH (n {{file: $file, name: $name}}) WHERE 1=1 {pid_clause} DETACH DELETE n"
        params: Dict[str, Any] = {"file": file_path, "name": symbol_name}
        if pid:
            params["pid"] = pid
        tx.run(query, **params)
        logger.debug(f"Deleted node for {symbol_name} in {file_path}")

    def _create_symbol_node(self, tx, symbol: Symbol) -> None:
        """Create or update a symbol node in Neo4j using the correct label."""
        label = self._symbol_type_to_label(symbol.type)
        pid = self.neo4j.project_id or ""
        node_id = symbol.node_id or f"{symbol.type}:{symbol.file}:{symbol.line}:{symbol.name}"
        query = f"""
        MERGE (n:{label} {{node_id: $node_id}})
        SET n.name = $name,
            n.type = $label,
            n.file = $file,
            n.line = $line,
            n.column = $column,
            n.parent = $parent,
            n.project_id = $pid
        """
        tx.run(
            query,
            node_id=node_id,
            name=symbol.name,
            label=label,
            file=symbol.file,
            line=symbol.line,
            column=symbol.column,
            parent=symbol.parent or "",
            pid=pid,
        )
        logger.debug(f"Created/updated node for {symbol.qualified_name}")

    # _update_symbol_node removed — _update_neo4j now does delete + create for modified symbols

    def _rollback(self, file_path: str) -> None:
        """Rollback in-memory index to pre-delta state for the given file.

        Neo4j is rolled back automatically via the transaction context manager in
        _update_neo4j. This method restores the in-memory SymbolIndex to match.

        Args:
            file_path: File being modified
        """
        if not self._backup_index:
            logger.warning("Cannot rollback: no backup available")
            return

        logger.info(f"Rolling back in-memory index changes to {file_path}")

        # Remove all current symbols for this file (the partial-update state)
        for symbol in list(self.index.get_by_file(file_path)):
            self.index.remove(symbol)

        # Restore the backed-up symbols
        for _, symbol in self._backup_index["symbols"]:
            self.index.add(symbol)

        restored = len(self._backup_index["symbols"])
        self._backup_index = None
        logger.info(f"Rolled back {restored} symbols for {file_path}")

    def _run_git(self, args: List[str], cwd: Optional[str] = None) -> str:
        """Run a git command and return output.

        Args:
            args: Git command arguments (e.g., ["diff", "HEAD~1..HEAD"])
            cwd: Working directory for git command

        Returns:
            Command output (stdout)

        Raises:
            RuntimeError: If git command fails
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd or str(self.base_path),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e
        except FileNotFoundError as e:
            raise RuntimeError("Git not found in PATH") from e

    def _get_commit_metadata(self, ref: str, repo_path: str) -> CommitNode:
        """Extract commit metadata from git log.

        Args:
            ref: Commit reference (e.g., "HEAD", "HEAD~1")
            repo_path: Repository path

        Returns:
            CommitNode with metadata

        Raises:
            RuntimeError: If git log fails
        """
        # Format: "commit_hash|short_hash|message|author|timestamp|branch|files_changed"
        output = self._run_git(
            [
                "log",
                "-1",
                "--format=%H|%h|%s|%an|%aI",
                ref,
            ],
            cwd=repo_path,
        ).strip()

        if not output:
            raise RuntimeError(f"Failed to get commit metadata for {ref}")

        parts = output.split("|")
        if len(parts) < 5:
            raise RuntimeError(f"Invalid git log format: {output}")

        commit_hash, short_hash, message, author, timestamp = parts[:5]

        # Get branch name
        branch_output = self._run_git(["rev-parse", "--abbrev-ref", ref], cwd=repo_path).strip()
        branch = branch_output if branch_output else "unknown"

        # Get files changed count
        files_output = self._run_git(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", ref],
            cwd=repo_path,
        ).strip()
        files_changed = len(files_output.split("\n")) if files_output else 0

        return CommitNode(
            commit_hash=commit_hash,
            short_hash=short_hash,
            message=message,
            author=author,
            timestamp=timestamp,
            branch=branch,
            files_changed=files_changed,
        )

    def _parse_file(self, abs_path: str) -> List[Symbol]:
        """Parse a file and extract symbols.

        Args:
            abs_path: Absolute file path

        Returns:
            List of symbols extracted from file

        Raises:
            RuntimeError: If file parsing fails
        """
        ext = Path(abs_path).suffix.lower()

        if ext == ".py":
            if not self.python_parser:
                raise RuntimeError("Python parser not initialized")
            return self.python_parser.parse_file(abs_path)
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            if not self.typescript_parser:
                raise RuntimeError("TypeScript parser not available")
            return self.typescript_parser.parse_file(abs_path)
        elif ext == ".go":
            if not self.go_parser:
                raise RuntimeError("Go parser not available (pip install tree-sitter-go)")
            return self.go_parser.parse_file(abs_path)
        elif ext == ".rs":
            if not self.rust_parser:
                raise RuntimeError("Rust parser not available (pip install tree-sitter-rust)")
            return self.rust_parser.parse_file(abs_path)
        elif ext == ".java":
            if not self.java_parser:
                raise RuntimeError("Java parser not available (pip install tree-sitter-java)")
            return self.java_parser.parse_file(abs_path)
        else:
            raise RuntimeError(f"Unsupported file type: {ext}")

    def _compute_delta(self, file_path: str, before_symbols: List[Symbol], after_symbols: List[Symbol]) -> SymbolDelta:
        """Compute symbol changes between two versions.

        Args:
            file_path: Path to the file
            before_symbols: Symbols before change
            after_symbols: Symbols after change

        Returns:
            SymbolDelta describing additions, deletions, modifications
        """
        # Index by qualified name for comparison
        before_map = {s.qualified_name: s for s in before_symbols}
        after_map = {s.qualified_name: s for s in after_symbols}

        added = []
        deleted = []
        modified = []

        # Find added and modified symbols
        for qname, after_sym in after_map.items():
            if qname not in before_map:
                added.append(after_sym)
            else:
                before_sym = before_map[qname]
                # Modified = line number changed (symbol moved) or type changed
                if before_sym.line != after_sym.line or before_sym.type != after_sym.type:
                    modified.append(after_sym)

        # Find deleted symbols
        for qname, before_sym in before_map.items():
            if qname not in after_map:
                deleted.append(before_sym.name)

        return SymbolDelta(
            file=file_path,
            added=added,
            deleted=deleted,
            modified=modified,
        )

    def _update_embeddings_for_changed(self, symbol_node_ids: List[str]) -> None:
        """Update embeddings for changed symbols.

        Args:
            symbol_node_ids: List of symbol node_ids that changed
        """
        if not self.embedding_service or not symbol_node_ids:
            return

        try:
            logger.debug(f"Updating embeddings for {len(symbol_node_ids)} symbols")
            # Only embed symbols that changed
            symbols = [self.index.get_by_qualified_name(sid) for sid in symbol_node_ids]
            symbols = [s for s in symbols if s]  # Filter out None values

            if symbols:
                # Rebuild FAISS index with incremental updates
                self.embedding_service.build_index()
                logger.debug(f"Rebuilt FAISS index for {len(symbols)} symbols")
        except Exception as e:
            logger.warning(f"Failed to update embeddings: {e}. Semantic search will regenerate on first use.")

    def update_from_git(self, commit_range: str = "HEAD~1..HEAD", repo_path: Optional[str] = None) -> bool:
        """Apply symbol changes from git commits to index and Neo4j.

        Args:
            commit_range: Git commit range (e.g., "HEAD~1..HEAD")
            repo_path: Repository path (defaults to base_path)

        Returns:
            True if successful, False otherwise
        """
        if not self.base_path and not repo_path:
            logger.error("No repository path provided")
            return False

        repo_path = repo_path or str(self.base_path)
        start_time = time.time()
        all_changed_ids: Set[str] = set()

        try:
            logger.info(f"Syncing graph from git: {commit_range}")

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]Git Sync"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("[cyan]{task.description}"),
            ) as progress:
                task = progress.add_task("", total=100)

                # Step 1: Get diff
                progress.update(task, description="Getting git diff", advance=5)
                diff_output = self._run_git(["diff", "--name-status", commit_range], cwd=repo_path)
                diff_lines = [line for line in diff_output.strip().split("\n") if line]

                if not diff_lines:
                    logger.info("No changes in commit range")
                    return True

                progress.update(task, description=f"{len(diff_lines)} files changed", advance=5)

                # Step 2: Parse diff to identify changed files
                diff_parser = DiffParser()
                file_changes = {}  # file_path -> (status, before_text, after_text)

                for diff_line in diff_lines:
                    parts = diff_line.split("\t", 1)
                    if len(parts) != 2:
                        continue

                    status, file_path = parts[0], parts[1]
                    file_changes[file_path] = status

                # Step 3: Process each changed file
                files_processed = 0
                for file_path, status in file_changes.items():
                    try:
                        abs_path = str(Path(repo_path) / file_path)

                        # Handle deleted files
                        if status == "D":
                            # Query Neo4j for current symbols (the "before" state)
                            before_symbols = self._query_symbols_in_file(abs_path)
                            delta = SymbolDelta(
                                file=abs_path,
                                added=[],
                                deleted=[s.name for s in before_symbols],
                                modified=[],
                            )
                            result = self.apply_delta(delta)
                            if result.success:
                                all_changed_ids.update([s.node_id for s in before_symbols if s.node_id])
                        # Handle added/modified files
                        elif status in ("A", "M"):
                            try:
                                after_symbols = self._parse_file(abs_path)
                                # Query Neo4j for "before" state (not the empty in-memory index)
                                before_symbols = self._query_symbols_in_file(abs_path) if status == "M" else []

                                delta = self._compute_delta(abs_path, before_symbols, after_symbols)
                                result = self.apply_delta(delta)

                                if result.success:
                                    # Track changed symbol node_ids
                                    all_changed_ids.update([s.node_id for s in delta.added])
                                    all_changed_ids.update([s.node_id for s in delta.modified])
                            except Exception as e:
                                logger.warning(f"Failed to process {file_path}: {e}")

                        files_processed += 1
                        progress.update(task, description=f"Processed {files_processed}/{len(file_changes)} files", advance=(90 // len(file_changes)))

                    except Exception as e:
                        logger.warning(f"Failed to handle {file_path}: {e}")

                # Step 4: Create commit node
                progress.update(task, description="Creating commit node", advance=5)
                try:
                    # Get the commit at the end of the range
                    commit_ref = commit_range.split("..")[-1] or "HEAD"
                    commit_meta = self._get_commit_metadata(commit_ref, repo_path)
                    self.neo4j.create_commit_node(commit_meta)
                    logger.debug(f"Created commit node: {commit_meta.short_hash}")
                except Exception as e:
                    logger.warning(f"Failed to create commit node: {e}")

                # Step 5: Create MODIFIED_BY edges
                if all_changed_ids:
                    progress.update(task, description="Linking symbols to commit", advance=0)
                    try:
                        self.neo4j.create_modified_by_edges(
                            list(all_changed_ids),
                            commit_meta.commit_hash,
                        )
                        logger.debug(f"Created {len(all_changed_ids)} MODIFIED_BY edges")
                    except Exception as e:
                        logger.warning(f"Failed to create MODIFIED_BY edges: {e}")

                # Step 6: Update embeddings
                progress.update(task, description="Updating embeddings", advance=0)
                self._update_embeddings_for_changed(list(all_changed_ids))

                progress.update(task, description="Complete", advance=5)

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Git sync complete: {len(file_changes)} files, {len(all_changed_ids)} symbols ({duration_ms:.1f}ms)")
            return True

        except Exception as e:
            logger.error(f"Git sync failed: {e}")
            return False

    def validate_graph_consistency(self) -> bool:
        """Validate graph consistency after updates.

        Checks:
        1. No symbol nodes missing required fields (name or file)
        2. No duplicate (name, file) pairs within the project

        Returns:
            True if graph is consistent
        """
        logger.info("Validating graph consistency...")

        pid = self.neo4j.project_id or ""
        pid_filter = " AND n.project_id = $pid" if pid else ""
        params: Dict[str, Any] = {}
        if pid:
            params["pid"] = pid

        with self.neo4j.driver.session() as session:
            # 1. Nodes with missing name or file
            result = session.run(
                f"MATCH (n) WHERE (n.name IS NULL OR n.file IS NULL)"
                f"{pid_filter} AND NOT n:File AND NOT n:Commit "
                "RETURN count(n) AS cnt",
                **params,
            )
            missing = result.single()["cnt"]
            if missing > 0:
                logger.error(f"Found {missing} nodes with missing name or file")
                return False

            # 2. Duplicate (name, file) pairs — same symbol indexed twice
            result = session.run(
                f"MATCH (n) WHERE NOT n:File AND NOT n:Commit{pid_filter} "
                "WITH n.file AS file, n.name AS name, count(*) AS cnt "
                "WHERE cnt > 1 RETURN count(*) AS duplicates",
                **params,
            )
            duplicates = result.single()["duplicates"]
            if duplicates > 0:
                logger.error(f"Found {duplicates} duplicate (file, name) pairs")
                return False

        logger.info("Graph consistency validated")
        return True
