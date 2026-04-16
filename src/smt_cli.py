#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smt — CLI for save-my-tokens.

Usage:
    smt build                      # Build graph from src/
    smt build --check              # Show graph stats
    smt build --clear              # Wipe and rebuild

    smt definition <symbol>        # What is this symbol? (1-hop, fast)
    smt context <symbol>           # What do I need to work on this? (bounded, bidirectional)
    smt context <symbol> --callers # Who calls this symbol
    smt impact <symbol>            # What breaks if I change this? (reverse traversal)
    smt search <query>             # Semantic search
    smt sync [range]               # Sync graph after commits (default: HEAD~1..HEAD)

    smt docker up                  # Start Neo4j container
    smt docker down                # Stop Neo4j container
    smt docker status              # Check Neo4j container

    smt status                     # Graph health check
    smt setup [--dir <path>]       # Configure a project (.claude/settings.json)
"""

import sys
import json
import hashlib
import argparse
import subprocess
import stat
from pathlib import Path
from typing import Optional, Any

from loguru import logger

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SMT_DIR = Path(__file__).parent.parent.resolve()

# Ensure repo root is on sys.path so bare-module imports (cli_utils, src.*) work
# regardless of how this file is invoked (installed entry point vs. python smt.py).
if str(SMT_DIR) not in sys.path:
    sys.path.insert(0, str(SMT_DIR))

# Global Neo4j client for connection pooling across CLI commands
_neo4j_client: Optional[Any] = None
_validation_cache: Optional[Any] = None


# ---------------------------------------------------------------------------
# Color output (from shared cli_utils)
# ---------------------------------------------------------------------------

from cli_utils import Colors

# Compatibility aliases for existing code
_C = Colors

def _ok(msg: str) -> None:
    """Print OK status."""
    print(f"{Colors.GREEN}[OK]{Colors.RESET}   {msg}")

def _fail(msg: str) -> None:
    """Print FAIL status."""
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {msg}")

def _warn(msg: str) -> None:
    """Print WARN status."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


def _get_project_id(project_root: Path) -> str:
    """Derive a stable 12-char project ID from the project root path."""
    return hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:12]


def _get_neo4j_client(project_id: str = ""):
    """Get or create singleton Neo4j client (connection pooling).

    Re-creates the client if project_id has changed so queries never run
    against the wrong project's data.
    """
    global _neo4j_client
    if _neo4j_client is None or _neo4j_client.project_id != project_id:
        _close_neo4j_client()
        from src.config import settings
        from src.graph.neo4j_client import Neo4jClient
        _neo4j_client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
    return _neo4j_client


def _close_neo4j_client():
    """Close the global client on exit."""
    global _neo4j_client
    if _neo4j_client:
        _neo4j_client.driver.close()
        _neo4j_client = None


def _get_engine(project_path: Optional[Path] = None):
    """Return an SMTQueryEngine scoped to the current project."""
    from src.agents.query_engine import SMTQueryEngine
    from src.config import settings
    path = (project_path or _resolve_project_path()).resolve()
    project_id = _get_project_id(path)
    cache_dir = path / '.smt' / 'embeddings'
    return SMTQueryEngine(
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password=settings.NEO4J_PASSWORD,
        embeddings_cache_dir=cache_dir,
        project_id=project_id,
    )


def _get_validation(repo_path: Path):
    """Get or create cached validation result."""
    global _validation_cache
    if _validation_cache is None:
        from src.graph.validator import validate_graph
        client = _get_neo4j_client()
        _validation_cache = validate_graph(client, repo_path)
    return _validation_cache


def _get_services():
    """Lazy-import heavy services so CLI starts fast for docker/status commands."""
    sys.path.insert(0, str(SMT_DIR))
    from src.config import settings
    from src.graph.neo4j_client import Neo4jClient
    from src.graph.graph_builder import GraphBuilder
    from src.parsers.symbol_index import SymbolIndex
    from src.embeddings.embedding_service import EmbeddingService
    from src.incremental.updater import IncrementalSymbolUpdater
    return settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------

def _docker_compose_cmd() -> list:
    """Return the docker compose command — v2 ('docker compose') preferred, v1 fallback."""
    result = subprocess.run(['docker', 'compose', 'version'], capture_output=True)
    if result.returncode == 0:
        return ['docker', 'compose']
    return ['docker-compose']


def _neo4j_bolt_ready(timeout: float = 2.0) -> bool:
    """Check if Neo4j bolt port (7687) accepts connections — the actual database port."""
    import socket
    try:
        with socket.create_connection(('localhost', 7687), timeout=timeout):
            return True
    except OSError:
        return False


def cmd_docker(action: str) -> int:
    import time

    compose_file = SMT_DIR / 'docker-compose.yml'
    if not compose_file.exists():
        print("ERROR: docker-compose.yml not found")
        return 1

    dc = _docker_compose_cmd()

    if action == 'up':
        result = subprocess.run(
            dc + ['-f', str(compose_file), 'up', '-d', 'neo4j'],
            cwd=SMT_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr or ""
            if "pipe/dockerDesktopLinuxEngine" in stderr or "pipe/docker_engine" in stderr or "connect: no such file" in stderr:
                print("ERROR: Docker Desktop is not running.")
                print("  Fix: start Docker Desktop, then re-run: smt docker up")
            else:
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="")
            return result.returncode
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")

        # Wait for Neo4j bolt port to accept connections (up to 120s)
        print("Waiting for Neo4j to be ready...", flush=True)
        max_wait = 120
        elapsed = 0.0
        attempt = 0
        while elapsed < max_wait:
            if _neo4j_bolt_ready():
                print(f"Neo4j ready (bolt://localhost:7687) — run: smt build")
                return 0
            attempt += 1
            wait = min(0.5 * (2 ** (attempt - 1)), 8)
            elapsed += wait
            print(f"  still starting... ({int(elapsed)}s)", flush=True)
            time.sleep(wait)

        print(f"ERROR: Neo4j did not become ready in {max_wait}s")
        print("  Check container logs: docker logs save-my-tokens-neo4j")
        return 1

    elif action == 'down':
        result = subprocess.run(dc + ['-f', str(compose_file), 'down'], cwd=SMT_DIR)
    elif action == 'status':
        result = subprocess.run(dc + ['-f', str(compose_file), 'ps'], cwd=SMT_DIR)
    else:
        print(f"Unknown docker action: {action}. Use: up, down, status")
        return 1

    return result.returncode


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:7474', timeout=2)
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    print(f"Neo4j:  {'OK  (http://localhost:7474)' if neo4j_ok else 'NOT RUNNING'}")

    if not neo4j_ok:
        print("\nStart Neo4j with:  smt docker up")
        return 1

    try:
        settings, Neo4jClient, *_ = _get_services()
        project_path = _resolve_project_path()
        project_id = _get_project_id(project_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
        with client.driver.session() as session:
            if project_id:
                counts = session.run(
                    "MATCH (n {project_id: $pid}) RETURN labels(n)[0] AS label, count(n) AS cnt",
                    pid=project_id
                ).data()
                edge_count = session.run(
                    "MATCH (a {project_id: $pid})-[r]->(b {project_id: $pid}) RETURN count(r) AS cnt",
                    pid=project_id
                ).single()['cnt']
            else:
                counts = session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
                ).data()
                edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()['cnt']
        total = sum(r['cnt'] for r in counts)
        print(f"Graph:  {total} nodes, {edge_count} edges  (project: {project_path.name} [{project_id}])")
        for row in sorted(counts, key=lambda r: -r['cnt']):
            print(f"        {row['label']}: {row['cnt']}")

        if total == 0:
            print("\nGraph is empty. Build it with:  smt build")
            client.driver.close()
            return 1

        # Freshness check
        try:
            from src.graph.validator import validate_graph, format_validation_line, format_stale_files_line
            validation = validate_graph(client, project_path)
            print(f"Head:   {format_validation_line(validation)}")
            stale = format_stale_files_line(validation)
            if stale:
                print(stale)
        except Exception:
            pass
        client.driver.close()
    except Exception as e:
        print(f"Graph:  ERROR — {e}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(check: bool = False, clear: bool = False, target_dir: str | None = None) -> int:
    settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, _ = _get_services()

    if check:
        return cmd_status()

    # Determine target directory
    if target_dir:
        target_path = Path(target_dir).resolve()
    else:
        # Priority:
        # 1. Check for .smt_config in .claude/ (from smt setup)
        # 2. Use current directory if it has src/
        # 3. Fail with helpful message
        cwd = Path.cwd()
        smt_config_file = cwd / '.claude' / '.smt_config'

        if smt_config_file.exists():
            try:
                with open(smt_config_file, 'r', encoding='utf-8') as f:
                    smt_config = json.load(f)
                    target_path = Path(smt_config['project_dir']).resolve()
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                target_path = cwd
        else:
            target_path = cwd

    # Require git
    if not _require_git(target_path):
        return 1

    # Find source directory — try common names, fall back to project root
    _CANDIDATE_SRC_DIRS = ['src', 'app', 'lib', 'pkg', 'core', 'source']
    src_dir = None
    for dirname in _CANDIDATE_SRC_DIRS:
        candidate = target_path / dirname
        if candidate.exists() and candidate.is_dir():
            src_dir = candidate
            break
    if src_dir is None:
        src_dir = target_path  # scan from project root (GraphBuilder._SKIP_DIRS handles noise)

    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        from loguru import logger
        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        # Clear if requested — scoped to this project only
        if clear:
            print(f"{Colors.YELLOW}[WARN]{Colors.RESET} Clearing graph data for project: {target_path.name} [{project_id}]")
            client.clear_database()
            # Also wipe the project's embeddings cache
            import shutil
            embeddings_dir = target_path / '.smt' / 'embeddings'
            if embeddings_dir.exists():
                shutil.rmtree(embeddings_dir)
                logger.info(f"Cleared embeddings cache: {embeddings_dir}")

        builder = GraphBuilder(str(src_dir), neo4j_client=client, project_id=project_id)
        builder.build()
        client.driver.close()
        print(f"Done. (project: {target_path.name} [{project_id}])")
        return cmd_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def _resolve_project_path() -> Path:
    """Resolve project path from .smt_config or cwd."""
    cwd = Path.cwd()
    smt_config_file = cwd / '.claude' / '.smt_config'
    if smt_config_file.exists():
        try:
            with open(smt_config_file, 'r', encoding='utf-8') as f:
                smt_config = json.load(f)
                return Path(smt_config['project_dir']).resolve()
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            pass
    return cwd


def cmd_context(symbol: str, depth: int = 1, callers: bool = False,
                file_filter: str | None = None, compress: bool = False) -> int:
    from src.graph.cycle_detector import detect_cycles
    from src.graph.compressor import compress_subgraph, format_compression_stats

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        # Get bounded subgraph using depth parameter (clamped — 0 breaks Cypher, >10 kills DB)
        max_depth = max(1, min(depth, 10))
        subgraph = client.get_bounded_subgraph(symbol, max_depth=max_depth)

        if not subgraph:
            print(f"Symbol '{symbol}' not found in graph.")
            client.driver.close()
            return 1

        root = subgraph["root"]
        nodes = subgraph["nodes"]
        edges = subgraph["edges"]

        # Print header (definition)
        labels = root.get("labels", [])
        print(f"\n{root.get('name')}  [{', '.join(labels)}]")
        print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")
        if root.get("signature"):
            print(f"  sig:  {root.get('signature')}")
        if root.get("docstring"):
            print(f"  doc:  {root.get('docstring')[:120]}")

        # Detect cycles in the subgraph
        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        # Track original sizes for compression stats
        original_node_count = len(nodes)
        original_edge_count = len(edges)

        # Apply compression if requested
        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            # Replace nodes and edges with compressed versions
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            # Re-detect cycles on compressed graph
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e[0], e[1]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        # Build sets for quick lookup
        acyclic_set = set(acyclic_nodes)
        cyclic_nodes_set = {n for cg in cycle_groups for n in cg.members}

        # Print calls (outbound edges, excluding those in cycles)
        outbound_calls = [e for e in edges if e["src"] == symbol]
        if outbound_calls:
            print(f"\n  calls ({len(outbound_calls)}):")
            for edge in outbound_calls:
                target = edge["dst"]
                # Find target node for file info
                target_node = next((n for n in nodes if n["name"] == target), None)
                file_str = target_node.get("file", "?") if target_node else "?"
                file_base = Path(file_str).name if file_str != "?" else "?"
                print(f"    {target}  ({file_base})")

        # Print cycles
        if cycle_groups:
            for cg in cycle_groups:
                # Find a representative edge to show the cycle direction
                cycle_str = " → ".join(cg.members[:3])  # Show first 3 for readability
                if len(cg.members) > 3:
                    cycle_str += f" → ... ({len(cg.members)} total)"
                print(f"\n  [Cycle: {cycle_str}]")
                print(f"    {len(cg.members)} functions collapsed")

        # Callers (inbound edges, 1 hop only)
        if callers or depth > 1:
            with client.driver.session() as session:
                callers_data = session.run(
                    "MATCH (caller)-[:CALLS]->(n {name: $name}) RETURN caller.name AS name, caller.file AS file",
                    name=symbol
                ).data()
                if callers_data:
                    print(f"\n  callers ({len(callers_data)}):")
                    for c in callers_data:
                        file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                        print(f"    {c['name']}  ({file_base})")

        # Print metadata footer
        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        if compression_result and compression_result.bridges:
            # Show compression stats
            compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                       compression_result)
            print(f"\n  context: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
            print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
        else:
            print(f"\n  context: nodes={len(nodes)} edges={len(edges)} depth={max_depth} "
                  f"cycles={len(cycle_groups)} ~tokens={token_estimate}")

        # Print validation status
        try:
            validation = _get_validation(_resolve_project_path())
            from src.graph.validator import format_validation_line, format_stale_files_line
            print(f"  {format_validation_line(validation)}")
            stale = format_stale_files_line(validation)
            if stale:
                print(stale)
        except Exception as e:
            logger.debug(f"Validation check failed: {e}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        logger.error(f"cmd_context error: {traceback.format_exc()}")
        return 1


# ---------------------------------------------------------------------------
# callers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# definition
# ---------------------------------------------------------------------------

def cmd_definition(symbol: str, file_filter: str | None = None) -> int:
    """Fast definition lookup — just the signature and 1-hop callees."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        with client.driver.session() as session:
            # Check for multiple matches (warn before silently picking one)
            if not file_filter:
                matches = session.run(
                    f"MATCH (n {{name: $name}}) WHERE 1=1 {pid_clause} "
                    "RETURN n.file AS file, labels(n)[0] AS type, n.line AS line ORDER BY n.file",
                    name=symbol, pid=project_id
                ).data()
                if len(matches) > 1:
                    print(f"Multiple symbols named '{symbol}' found — use --file to disambiguate:\n")
                    for m in matches:
                        try:
                            display = str(Path(m['file']).relative_to(project_path))
                        except (ValueError, TypeError):
                            display = m['file'] or '?'
                        print(f"  [{m['type']}]  {display}:{m['line']}")
                    print(f"\n  e.g.  smt definition {symbol} --file {Path(matches[0]['file']).name}")
                    return 1

            # Find the symbol
            if file_filter:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE n.file CONTAINS $file {pid_clause}
                    RETURN n
                    LIMIT 1
                """
                node = session.run(query, name=symbol, file=file_filter, pid=project_id).single()
            else:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE 1=1 {pid_clause}
                    RETURN n,
                           CASE WHEN n:Function THEN 0
                                WHEN n:Class THEN 1
                                ELSE 2 END as priority
                    ORDER BY priority
                    LIMIT 1
                """
                node = session.run(query, name=symbol, pid=project_id).single()

            if not node:
                print(f"Symbol '{symbol}' not found in graph.")
                client.driver.close()
                return 1

            n = node['n']
            print(f"\n{n.get('name')}  [{', '.join(n.labels)}]")
            print(f"  file: {n.get('file', '?')}:{n.get('line', '?')}")
            if n.get('signature'):
                print(f"  sig:  {n.get('signature')}")
            if n.get('docstring'):
                # Print full docstring for definition (not truncated)
                print(f"  doc:  {n.get('docstring')}")

            # Direct callees only (1 hop, no recursion) — filter both ends by project
            callee_pid = "{project_id: $pid}" if project_id else ""
            callees = session.run(
                f"MATCH (n {{name: $name}})-[:CALLS]->(callee {callee_pid}) "
                f"WHERE 1=1 {pid_clause} "
                "RETURN callee.name AS name, callee.file AS file",
                name=symbol, pid=project_id
            ).data()
            if callees:
                print(f"\n  calls ({len(callees)}):")
                for c in callees:
                    file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                    print(f"    {c['name']}  ({file_base})")

            # Print validation status
            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_validation_line, format_stale_files_line
                print(f"\n  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            except Exception as e:
                logger.debug(f"Validation check failed: {e}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        logger.error(f"cmd_definition error: {traceback.format_exc()}")
        return 1


# ---------------------------------------------------------------------------
# impact
# ---------------------------------------------------------------------------

def _compute_depths(
    root: str, edges: list[tuple[str, str]]
) -> dict[str, int]:
    """
    Compute depth of each node from root via reverse BFS over edges.

    Used for impact analysis (reverse CALLS direction).
    Args:
        root: Root symbol name
        edges: List of (src, dst) tuples representing CALLS edges

    Returns:
        Dict mapping node name to depth (root=0, direct callers=1, etc.)
    """
    # Reverse the edges for backward traversal
    reverse_edges: dict[str, list[str]] = {}
    for src, dst in edges:
        if dst not in reverse_edges:
            reverse_edges[dst] = []
        reverse_edges[dst].append(src)

    # BFS from root in reverse direction
    depths = {root: 0}
    queue = [(root, 0)]
    visited = {root}

    while queue:
        node, depth = queue.pop(0)
        # Find all nodes that call this node (reverse direction)
        for caller in reverse_edges.get(node, []):
            if caller not in visited:
                visited.add(caller)
                depths[caller] = depth + 1
                queue.append((caller, depth + 1))

    return depths


def cmd_impact(symbol: str, max_depth: int = 3, compress: bool = False) -> int:
    """Impact analysis — what breaks if I change this symbol?"""
    from src.graph.cycle_detector import detect_cycles
    from src.graph.compressor import compress_subgraph, format_compression_stats

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        # Get impact graph (reverse traversal)
        impact_set = client.get_impact_graph(symbol, max_depth=max_depth)

        if not impact_set:
            print(f"Symbol '{symbol}' not found in graph.")
            client.driver.close()
            return 1

        root = impact_set["root"]
        nodes = impact_set["nodes"]
        edges = impact_set["edges"]

        # Print header
        labels = root.get("labels", [])
        total_callers = len([n for n in nodes if n["name"] != symbol])
        print(f"\nImpact: {root.get('name')}  [{', '.join(labels)}]  ({total_callers} caller{'s' if total_callers != 1 else ''})")
        print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")

        # Compute depths for impact grouping
        depths = _compute_depths(root.get('name', symbol), edges)

        # Group callers by depth
        callers_by_depth: dict[int, list[str]] = {}
        for n in nodes:
            node_name = n["name"]
            if node_name != symbol:  # Skip root
                d = depths.get(node_name, max_depth + 1)
                if d not in callers_by_depth:
                    callers_by_depth[d] = []
                callers_by_depth[d].append(node_name)

        # Print grouped callers
        for depth_level in sorted(callers_by_depth.keys()):
            callers = callers_by_depth[depth_level]
            if depth_level == 1:
                label = "direct callers"
            else:
                label = f"indirect callers — depth {depth_level}"
            print(f"\n  {label} ({len(callers)}):")
            for caller in sorted(callers):
                caller_node = next((n for n in nodes if n["name"] == caller), None)
                file_base = Path(caller_node.get("file", "?")).name if caller_node else "?"
                print(f"    {caller}  ({file_base})")

        # Track original sizes for compression stats
        original_node_count = len(nodes)
        original_edge_count = len(edges)

        # Detect cycles in the impact set
        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        # Apply compression if requested
        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            # Replace nodes and edges with compressed versions
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            # Recompute callers_by_depth on compressed graph
            depths = _compute_depths(root.get('name', symbol), edges)
            callers_by_depth = {}
            for n in nodes:
                node_name = n["name"]
                if node_name != symbol:
                    d = depths.get(node_name, max_depth + 1)
                    if d not in callers_by_depth:
                        callers_by_depth[d] = []
                    callers_by_depth[d].append(node_name)
            # Re-detect cycles
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e[0], e[1]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        if cycle_groups:
            for cg in cycle_groups:
                cycle_str = " → ".join(cg.members[:3])
                if len(cg.members) > 3:
                    cycle_str += f" → ... ({len(cg.members)} total)"
                print(f"\n  [Cycle: {cycle_str}]")
                print(f"    {len(cg.members)} functions in cycle — changing {symbol} affects the entire cycle")

        # Print metadata footer
        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        if compression_result and compression_result.bridges:
            # Show compression stats
            compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                       compression_result)
            print(f"\n  impact: {compression_line} depth={len(callers_by_depth)} cycles={len(cycle_groups)} ~tokens={token_estimate}")
            print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
        else:
            print(f"\n  impact: nodes={len(nodes)} depth={len(callers_by_depth)} "
                  f"cycles={len(cycle_groups)} ~tokens={token_estimate}")

        # Print validation status
        try:
            validation = _get_validation(_resolve_project_path())
            from src.graph.validator import format_validation_line, format_stale_files_line
            print(f"  {format_validation_line(validation)}")
            stale = format_stale_files_line(validation)
            if stale:
                print(stale)
        except Exception as e:
            logger.debug(f"Validation check failed: {e}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        logger.error(f"cmd_impact error: {traceback.format_exc()}")
        return 1


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def cmd_search(query: str, top_k: int = 5, follow: Optional[str] = None) -> int:
    settings, _, _, SymbolIndex, EmbeddingService, _ = _get_services()

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        cache_dir = project_path / '.smt' / 'embeddings'
        symbol_index = SymbolIndex()
        svc = EmbeddingService(symbol_index, cache_dir=cache_dir)

        # Fast path: load pre-built FAISS index saved by smt build
        if not svc.load_index():
            # Slow path: fetch all symbols from Neo4j and rebuild index
            from src.graph.neo4j_client import Neo4jClient
            from src.parsers.symbol import Symbol
            client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
            with client.driver.session() as session:
                rows = session.run(
                    "MATCH (n {project_id: $pid}) RETURN n, labels(n) as labels", pid=project_id
                ).data()
            client.driver.close()
            for row in rows:
                n = row['n']
                labels = row['labels']
                if not n.get('name'):
                    continue
                symbol_index.add(Symbol(
                    name=n.get('name', ''),
                    type=labels[0] if labels else 'Unknown',
                    file=n.get('file', ''),
                    line=n.get('line', 0),
                    column=n.get('column', 0),
                    docstring=n.get('docstring'),
                ))
            svc.build_index()
            svc.save_index()

        results = svc.search(query, top_k=top_k)

        if not results:
            # Check if embeddings are available (index exists means embeddings worked)
            if not svc.index:
                print(f"No results for '{query}' (embeddings unavailable — see warning above)")
            else:
                print(f"No results for '{query}'")
            return 0

        print(f"\nSearch: {query!r}  (top {len(results)})\n")
        for sym, score in results:
            print(f"  {sym.name}  [{sym.type}]  score={score:.3f}")
            print(f"    {sym.file}:{sym.line}")
            if sym.docstring:
                print(f"    {sym.docstring[:80]}")

        if follow and results:
            top_name = results[0][0].name
            print(f"\n--- {follow}: {top_name} ---")
            if follow == 'context':
                return cmd_context(top_name, depth=2)
            elif follow == 'impact':
                return cmd_impact(top_name, max_depth=3)

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

def cmd_explain(symbol: str, depth: int = 2) -> int:
    """Print a Claude-ready explanation prompt for a symbol.

    Outputs the symbol's context graph formatted as a self-contained block that
    Claude Code can read and explain directly — no API key required.
    """
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        subgraph = client.get_bounded_subgraph(symbol, max_depth=max(1, min(depth, 5)))
    except Exception as e:
        print(f"ERROR: Could not query graph — {e}")
        return 1

    if not subgraph:
        print(f"Symbol '{symbol}' not found in graph. Run 'smt build' first.")
        return 1

    root = subgraph.get("root", {})
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])

    print(f"# Context: {symbol}")
    print(f"# (paste this to Claude and ask it to explain)")
    print()
    print(f"Symbol : {root.get('name')}  ({root.get('type')})")
    print(f"File   : {root.get('file')}:{root.get('line')}")
    if root.get('docstring'):
        print(f"Docstr : {root['docstring'][:400]}")
    print()
    print(f"Graph  : {len(nodes)} nodes, {len(edges)} edges (depth={depth})")
    for edge in edges:
        src = edge.get('source', {}).get('name', '?')
        tgt = edge.get('target', {}).get('name', '?')
        rel = edge.get('type', 'CALLS')
        src_file = edge.get('source', {}).get('file', '')
        tgt_file = edge.get('target', {}).get('file', '')
        src_label = f"{src} ({src_file.split('/')[-1]})" if src_file else src
        tgt_label = f"{tgt} ({tgt_file.split('/')[-1]})" if tgt_file else tgt
        print(f"  {src_label} --[{rel}]--> {tgt_label}")
    print()
    print(f"Prompt : Explain what '{symbol}' does, its role in the architecture,")
    print(f"         and what to be aware of before modifying it.")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def cmd_sync(commit_range: str = 'HEAD~1..HEAD', target_dir: Optional[str] = None) -> int:
    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    try:
        target_path = Path(target_dir).resolve() if target_dir else _resolve_project_path()

        # Check if it looks like a git repository
        if not (target_path / '.git').exists():
            print(f"ERROR: No .git directory found in {target_path}")
            return 1

        from loguru import logger

        # Create Neo4j client (scoped to this project)
        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        # Create symbol index
        index = SymbolIndex()

        # Create embedding service
        cache_dir = target_path / '.smt' / 'embeddings'
        embedding_svc = EmbeddingService(index, cache_dir=cache_dir)

        # Create updater
        updater = IncrementalSymbolUpdater(
            symbol_index=index,
            neo4j_client=client,
            embedding_service=embedding_svc,
            base_path=str(target_path),
        )

        # Run sync
        success = updater.update_from_git(commit_range, repo_path=str(target_path))
        client.driver.close()

        if success:
            print("✓ Graph synced successfully")
            result = cmd_status()
            return result
        else:
            print("✗ Graph sync failed — try: smt build --clear")
            return 1

    except Exception as e:
        logger.debug(f"cmd_sync error", exc_info=True)
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# watch
# ---------------------------------------------------------------------------

def cmd_watch(target_dir: Optional[str] = None, debounce: float = 2.0) -> int:
    """Watch source files and auto-sync the graph on changes.

    Monitors .py/.ts/.tsx/.js/.jsx files for changes. After a quiet period
    of `debounce` seconds, re-parses changed files and updates the graph.

    Note: CALLS edges are not rebuilt in watch mode — run `smt build` to
    refresh edge relationships after large refactors.
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("ERROR: watchdog is not installed. Run:  pip install watchdog")
        return 1

    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    target_path = Path(target_dir).resolve() if target_dir else _resolve_project_path()
    if not _require_git(target_path):
        return 1

    project_id = _get_project_id(target_path)
    client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
    index = SymbolIndex()
    cache_dir = target_path / '.smt' / 'embeddings'
    embedding_svc = EmbeddingService(index, cache_dir=cache_dir)
    updater = IncrementalSymbolUpdater(
        symbol_index=index,
        neo4j_client=client,
        embedding_service=embedding_svc,
        base_path=str(target_path),
    )

    import threading
    import time

    _SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
    _pending: set = set()
    _timer: Optional[threading.Timer] = None
    _lock = threading.Lock()

    def _flush() -> None:
        with _lock:
            files = list(_pending)
            _pending.clear()
        if not files:
            return
        print(f"\n[watch] {len(files)} file(s) changed — syncing graph...", flush=True)
        updated = 0
        for abs_path in files:
            p = Path(abs_path)
            try:
                before = updater._query_symbols_in_file(abs_path)
                if p.exists():
                    after = updater._parse_file(abs_path)
                else:
                    after = []
                delta = updater._compute_delta(abs_path, before, after)
                result = updater.apply_delta(delta)
                if result.success:
                    added = len(delta.added)
                    deleted = len(delta.deleted)
                    modified = len(delta.modified)
                    print(f"  {p.name}: +{added} -{deleted} ~{modified}", flush=True)
                    updated += 1
                else:
                    print(f"  {p.name}: FAILED — {result.error}", flush=True)
            except Exception as e:
                print(f"  {p.name}: ERROR — {e}", flush=True)
        if updated:
            print(f"[watch] Done. ({updated}/{len(files)} files updated)", flush=True)

    def _schedule_flush() -> None:
        nonlocal _timer
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(debounce, _flush)
        _timer.daemon = True
        _timer.start()

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            src = getattr(event, 'src_path', None)
            if not src or Path(src).suffix not in _SOURCE_EXTS:
                return
            with _lock:
                _pending.add(src)
            _schedule_flush()

    observer = Observer()
    observer.schedule(_Handler(), str(target_path), recursive=True)
    observer.start()
    print(f"[watch] Watching {target_path}  (debounce={debounce}s)  Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        client.driver.close()

    return 0


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def _require_git(path: Path) -> bool:
    """Check that path is a git repository. Prints error if not."""
    if not (path / '.git').exists():
        print(f"ERROR: {path} is not a git repository.")
        print(f"  Run: smt setup --dir {path}")
        return False
    return True


def _git_initial_commit(target_dir: Path) -> None:
    """Anchor current project state in git history."""
    # Only set identity if not already configured (local or global) — don't clobber user's settings
    def _git_config_missing(key: str) -> bool:
        result = subprocess.run(
            ['git', 'config', key], cwd=target_dir, capture_output=True
        )
        return result.returncode != 0 or not result.stdout.strip()

    if _git_config_missing('user.name'):
        subprocess.run(['git', 'config', 'user.name', 'SMT'], cwd=target_dir, capture_output=True)
    if _git_config_missing('user.email'):
        subprocess.run(['git', 'config', 'user.email', 'smt@local'], cwd=target_dir, capture_output=True)
    # Do NOT touch commit.gpgsign — respect the user's signing policy

    result = subprocess.run(
        ['git', 'log', '--oneline', '-1'],
        cwd=target_dir, capture_output=True
    )
    has_commits = result.returncode == 0 and result.stdout.strip()

    if has_commits:
        subprocess.run(['git', 'add', '.claude/'], cwd=target_dir, capture_output=True)
        staged = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=target_dir, capture_output=True
        )
        if staged.stdout.strip():
            subprocess.run(
                ['git', 'commit', '-m', 'chore: Initialize SMT graph index'],
                cwd=target_dir, capture_output=True
            )
    else:
        subprocess.run(['git', 'add', '.'], cwd=target_dir, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Initial: Build graph index'],
            cwd=target_dir, capture_output=True
        )

    print("  git commit             [OK] — Graph state anchored in git history")


# A2A agent card written to .claude/a2a/smt.json in target projects
_A2A_AGENT_CARD = {
    "name": "save-my-tokens",
    "description": (
        "Semantic code graph for efficient codebase exploration. "
        "Provides symbol lookup, dependency analysis, impact assessment, "
        "and semantic search via the smt CLI."
    ),
    "url": "local://smt-cli",
    "version": "1.0.0",
    "onboard": "cat .claude/a2a/smt-onboard.md",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "skills": [
        {
            "id": "smt-definition",
            "name": "Symbol Definition",
            "description": "What is this symbol? Signature, docstring, immediate callees.",
            "invoke": "smt definition <symbol>",
        },
        {
            "id": "smt-context",
            "name": "Symbol Context",
            "description": "What do I need to work on this? Symbol + N-hop callees + callers.",
            "invoke": "smt context <symbol> [--depth N] [--compress]",
        },
        {
            "id": "smt-impact",
            "name": "Change Impact Analysis",
            "description": "What breaks if I change this? All callers grouped by distance.",
            "invoke": "smt impact <symbol> [--depth N]",
        },
        {
            "id": "smt-search",
            "name": "Semantic Code Search",
            "description": "Find symbols by meaning using local embeddings. No API calls.",
            "invoke": 'smt search "<query>"',
        },
        {
            "id": "smt-status",
            "name": "Graph Health Check",
            "description": "Graph freshness, node/edge counts, git alignment. Run at session start.",
            "invoke": "smt status",
        },
        {
            "id": "smt-analysis",
            "name": "Multi-Agent Analysis Harness",
            "description": "Scout + Fabler + PathFinder for deep impact/isolation analysis.",
            "invoke": "/smt-analysis",
        },
        {
            "id": "smt-list",
            "name": "Symbol Listing",
            "description": "Enumerate all symbols in the graph, optionally filtered by module/file path.",
            "invoke": "smt list [--module <path-substring>]",
        },
        {
            "id": "smt-unused",
            "name": "Dead Code Detection",
            "description": "Find symbols with no callers — candidates for dead code removal.",
            "invoke": "smt unused",
        },
        {
            "id": "smt-cycles",
            "name": "Circular Dependency Detection",
            "description": "Find all circular dependencies in the call graph using Tarjan's SCC.",
            "invoke": "smt cycles",
        },
        {
            "id": "smt-hot",
            "name": "Coupling Hotspots",
            "description": "Most-called symbols ranked by unique caller count — find high-coupling hotspots.",
            "invoke": "smt hot [--top N]",
        },
        {
            "id": "smt-path",
            "name": "Dependency Path",
            "description": "Shortest dependency path between two symbols via CALLS edges.",
            "invoke": "smt path <A> <B>",
        },
        {
            "id": "smt-modules",
            "name": "Module Coupling Report",
            "description": "Files ranked by symbol count and cross-file coupling edges.",
            "invoke": "smt modules",
        },
        {
            "id": "smt-changes",
            "name": "Git Change Impact",
            "description": "Symbols in git-changed files with caller counts. Pinpoints which symbols changed by line range. Essential for PR review.",
            "invoke": "smt changes [RANGE]",
        },
        {
            "id": "smt-complexity",
            "name": "God Function Detector",
            "description": "Ranks symbols by fan-in × fan-out. High score = hard to refactor AND large blast radius.",
            "invoke": "smt complexity [--top N]",
        },
        {
            "id": "smt-scope",
            "name": "File Surface Analysis",
            "description": "Shows a file's public exports, imports from other files, and internal symbols. File-level architectural view.",
            "invoke": "smt scope <file-substring>",
        },
        {
            "id": "smt-bottleneck",
            "name": "Architectural Bottleneck",
            "description": "Symbols that bridge distinct file clusters. Bridge score = caller files × callee files (cross-file only). High score = structural chokepoint.",
            "invoke": "smt bottleneck [--top N]",
        },
        {
            "id": "smt-layer",
            "name": "Architecture Layer Guard",
            "description": "Detects forbidden dependency directions (e.g. parsers calling CLI). Configured via .smt_layers.json. Returns non-zero exit if violations found (CI-safe).",
            "invoke": "smt layer [--config PATH]",
        },
    ],
    "authentication": {"schemes": []},
}

# ---------------------------------------------------------------------------
# onboard
# ---------------------------------------------------------------------------

def cmd_onboard(action: str, target_dir: Optional[Path] = None) -> int:
    """Guided onboarding: setup, orientation, or health check."""

    if action == 'project':
        # Guided project onboarding: docker up → wait → build → status
        target = (target_dir or Path.cwd()).resolve()
        print(f"\n{_C.BOLD}SMT Project Onboarding: {target.name}{_C.RESET}\n")

        # Step 1: Docker up (cmd_docker now waits for Neo4j to be ready)
        print("Step 1/3  Starting Neo4j...")
        rc = cmd_docker('up')
        if rc != 0:
            _fail("docker up failed — is Docker Desktop running?")
            print("  Fix: start Docker Desktop, then re-run: smt onboard project")
            return 1
        _ok("Neo4j is ready")

        # Step 3: Build graph
        print("\nStep 2/3  Building graph from source...")
        result = cmd_build(check=False, clear=False, target_dir=str(target))
        if result != 0:
            _fail("Graph build failed — check error above")
            return 1

        # Step 4: Status
        print("\nStep 3/3  Verifying graph health...")
        result = cmd_status()
        if result != 0:
            _fail("Status check failed")
            return 1

        print(f"\n{_C.GREEN}{_C.BOLD}Onboarding complete!{_C.RESET}")
        print("\nNext steps:")
        print("  smt context <SymbolName>   — explore a symbol's dependencies")
        print("  smt search \"your query\"    — semantic search by meaning")
        print("  smt impact <SymbolName>    — see what breaks if you change this")
        print("  smt status                 — check graph health")
        return 0

    elif action == 'agent':
        # Print agent orientation (no external deps needed)
        orientation = f"""\

{_C.BOLD}SMT AGENT ORIENTATION{_C.RESET}
save-my-tokens (SMT) exposes a semantic Neo4j graph of this codebase.
Use it instead of reading raw files.

{_C.BOLD}QUERY DECISION TABLE{_C.RESET}
Goal                          | Command
------------------------------|------------------------------------------
Understand what a symbol does | smt context <symbol>
See dependencies (2+ hops)    | smt context <symbol> --depth 2
See who calls a function      | smt context <symbol> --callers
Find code by topic/meaning    | smt search "description"
What breaks if I change this  | smt impact <symbol>
Check graph health            | smt status
Build graph from source       | smt build
Sync after recent commits     | smt sync HEAD~1..HEAD
Start Neo4j                   | smt docker up

{_C.BOLD}TOOL HIERARCHY (use in order){_C.RESET}
  Tier 1 (first)   — smt context / smt search / smt impact
  Tier 2 (verify)  — Grep, Glob
  Tier 3 (inspect) — Read (only after SMT locates the file)
  Tier 4 (avoid)   — Bash find/grep for exploration

{_C.BOLD}SESSION START CHECKLIST{_C.RESET}
  smt status   → node count > 0? Graph is ready.
  smt build    → if empty, build from src/
  smt sync     → if stale, sync after recent commits

{_C.BOLD}SKILLS FILES (in .claude/skills/){_C.RESET}
  agent-query-guide.md    — full decision tree
  graph-maintenance.md    — how to keep graph fresh
  project-onboarding.md   — setup guide for first-time users
"""
        print(orientation)
        return 0

    elif action == 'check':
        # Health check: works even before graph is built
        print(f"\n{_C.BOLD}SMT Health Check{_C.RESET}\n")
        exit_code = 0

        # Check 1: Neo4j reachable
        import urllib.request
        try:
            urllib.request.urlopen('http://localhost:7474', timeout=3)
            _ok("Neo4j reachable (http://localhost:7474)")
            neo4j_up = True
        except Exception:
            _fail("Neo4j not reachable — run: smt docker up")
            neo4j_up = False
            exit_code = 1

        # Check 2: Graph non-empty (only if Neo4j is up)
        if neo4j_up:
            try:
                client = _get_neo4j_client()
                with client.driver.session() as session:
                    result = session.run("MATCH (n) RETURN count(n) AS cnt")
                    total = result.single()['cnt']
                if total > 0:
                    _ok(f"Graph has {total} nodes")
                else:
                    _warn("Graph is empty — run: smt build")
                    exit_code = 1
            except Exception as e:
                _warn(f"Graph query failed: {str(e)[:80]}")
                exit_code = 1
        else:
            _warn("Graph check skipped (Neo4j not running)")

        # Check 3: Graph freshness (only if Neo4j is up)
        if neo4j_up:
            try:
                from src.graph.validator import validate_graph
                client = _get_neo4j_client()
                repo_path = (target_dir or Path.cwd()).resolve()
                v = validate_graph(client, repo_path)
                if v.is_fresh:
                    _ok(f"Graph is fresh (HEAD: {v.git_head})")
                else:
                    _warn(f"Graph is {v.commits_behind} commit(s) behind — run: smt sync")
            except Exception as e:
                _warn(f"Staleness check skipped: {str(e)[:80]}")

        # Check 4: Embeddings model loadable
        try:
            result = subprocess.run(
                [sys.executable, '-c', 'from sentence_transformers import SentenceTransformer'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                _ok("sentence_transformers importable")
            else:
                _warn("sentence_transformers not importable — semantic search disabled")
        except Exception:
            _warn("sentence_transformers check timed out")

        # Check 5: Skills directory
        skills_dir = Path('.claude/skills')
        if skills_dir.exists() and any(skills_dir.glob('*.md')):
            skill_count = len(list(skills_dir.glob('*.md')))
            _ok(f".claude/skills/ has {skill_count} skill file(s)")
        else:
            _warn(".claude/skills/ missing or empty — run: smt setup --dir .")

        print()
        return exit_code

    else:
        print(f"Unknown onboard action: {action}")
        print("Usage: smt onboard project|agent|check [--dir PATH]")
        return 1


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup(target_dir: Path) -> int:
    target_dir = target_dir.resolve()
    claude_dir = target_dir / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    print(f"Configuring SMT for: {target_dir}")

    # ------------------------------------------------------------------
    # 0. .claude/.smt_config — store project metadata for CLI
    # ------------------------------------------------------------------
    smt_config_file = claude_dir / '.smt_config'
    smt_config = {
        'project_dir': str(target_dir),
        'project_name': target_dir.name,
        'project_id': _get_project_id(target_dir),
    }
    with open(smt_config_file, 'w', encoding='utf-8') as f:
        json.dump(smt_config, f, indent=2)
    print("  .claude/.smt_config    [OK]")

    # ------------------------------------------------------------------
    # 0b. .gitignore — ensure .smt/ (embeddings cache) is ignored
    # ------------------------------------------------------------------
    gitignore_file = target_dir / '.gitignore'
    smt_ignore_entry = '.smt/'
    if gitignore_file.exists():
        content = gitignore_file.read_text(encoding='utf-8')
        if smt_ignore_entry not in content:
            with open(gitignore_file, 'a', encoding='utf-8') as f:
                f.write(f'\n# SMT embeddings cache\n{smt_ignore_entry}\n')
            print("  .gitignore             [OK] — added .smt/")
        else:
            print("  .gitignore             [OK] — .smt/ already ignored")
    else:
        gitignore_file.write_text(f'# SMT embeddings cache\n{smt_ignore_entry}\n', encoding='utf-8')
        print("  .gitignore             [OK] — created with .smt/")

    # ------------------------------------------------------------------
    # 1. .claude/settings.json
    # ------------------------------------------------------------------
    settings_file = claude_dir / 'settings.json'
    existing = {}
    if settings_file.exists():
        with open(settings_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'
    existing.setdefault('permissions', {})
    existing['permissions']['defaultMode'] = 'auto'
    # Merge allow list — preserve any existing entries the user added
    smt_allow = ['Read', 'Edit(**)', 'Write(**)', 'Bash']
    current_allow = existing['permissions'].get('allow', [])
    existing['permissions']['allow'] = list(dict.fromkeys(current_allow + smt_allow))
    # Merge deny list — add SMT safety rules without dropping user's existing denies
    smt_deny = [
        'Bash(rm -rf:*)',
        'Bash(git reset --hard:*)',
        'Bash(git push --force:*)',
    ]
    current_deny = existing['permissions'].get('deny', [])
    existing['permissions']['deny'] = list(dict.fromkeys(current_deny + [
        r for r in smt_deny if r not in current_deny
    ]))
    existing.setdefault('env', {})
    existing['env']['SMT_DIR'] = str(SMT_DIR)
    existing['env']['SMT_PROJECT'] = target_dir.name
    existing['respectGitignore'] = True

    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2)
    print("  .claude/settings.json  [OK]")

    # ------------------------------------------------------------------
    # 2. .claude/skills/smt-analysis/ — copy the full harness from SMT repo
    # ------------------------------------------------------------------
    skills_dir = claude_dir / 'skills'
    smt_skill_src = SMT_DIR / '.claude' / 'skills' / 'smt-analysis'
    smt_skill_dst = skills_dir / 'smt-analysis'
    if smt_skill_src.exists():
        smt_skill_dst.mkdir(parents=True, exist_ok=True)
        copied = []
        for src_file in smt_skill_src.iterdir():
            if src_file.is_file():
                (smt_skill_dst / src_file.name).write_bytes(src_file.read_bytes())
                copied.append(src_file.name)
        print(f"  .claude/skills/smt-analysis/ [OK] — {len(copied)} files")
    else:
        print(f"  .claude/skills/smt-analysis/ [SKIP] — source not found at {smt_skill_src}")

    # ------------------------------------------------------------------
    # 2.5. .claude/a2a/smt.json — A2A agent card
    # ------------------------------------------------------------------
    a2a_dir = claude_dir / 'a2a'
    a2a_dir.mkdir(parents=True, exist_ok=True)
    with open(a2a_dir / 'smt.json', 'w', encoding='utf-8') as f:
        json.dump(_A2A_AGENT_CARD, f, indent=2)
    print("  .claude/a2a/smt.json   [OK]")

    # ------------------------------------------------------------------
    # 3. CLAUDE.md — tells Claude how to work in this project
    # ------------------------------------------------------------------
    claude_md = target_dir / 'CLAUDE.md'
    if not claude_md.exists():
        project_name = target_dir.name
        claude_md_content = f"""\
# CLAUDE.md

## Code Context — use SMT, not file reads

This project is indexed by **save-my-tokens (SMT)**. Query the graph instead of reading files.

### Before you read any file, try this first:

```bash
smt context <SymbolName>        # definition + deps + callers
smt context <SymbolName> --callers  # who calls this
smt search "what you're looking for"  # semantic search
smt status                      # check graph health
```

### Session start

```bash
smt docker up   # if Neo4j isn't running
smt status      # is the graph ready? (node count > 0)
smt build       # build if empty
smt sync        # sync if stale after recent commits
```

### Tool order

`smt context` / `smt search` → Grep → Read. Only open a file when SMT doesn't give enough detail.

### New agent? Start here:

```bash
cat .claude/skills/smt-analysis/a2a-onboard.md
```

### Project: {project_name}

SMT is installed at: `{SMT_DIR}`
Neo4j browser: http://localhost:7474
"""
        with open(claude_md, 'w', encoding='utf-8') as f:
            f.write(claude_md_content)
        print("  CLAUDE.md              [OK]")
    else:
        print("  CLAUDE.md              [skipped — already exists]")

    # ------------------------------------------------------------------
    # 4. Git — initialize and anchor graph state
    # ------------------------------------------------------------------
    print("")
    if not (target_dir / '.git').exists():
        try:
            subprocess.run(['git', 'init', str(target_dir)], check=True, capture_output=True)
            print("  .git/                  [INIT] — Initialized new git repository")
        except subprocess.CalledProcessError as e:
            print(f"  .git/                  [WARN] — git init failed: {e}")
    else:
        print("  .git/                  [OK] — Using existing git repository")

    # ------------------------------------------------------------------
    # 5. Ensure Neo4j is running, then build initial graph
    # ------------------------------------------------------------------
    if not _neo4j_bolt_ready():
        print("\nStarting Neo4j...")
        rc = cmd_docker('up')
        if rc != 0:
            print("\nERROR: Cannot start Neo4j — setup cannot continue.")
            print("  1. Start Docker Desktop")
            print("  2. Re-run: smt setup")
            return 1

    src_dir = target_dir / 'src'
    if src_dir.exists():
        print("\nBuilding initial graph (this may take a few minutes)...")
        build_result = cmd_build(target_dir=str(target_dir))
        if build_result != 0:
            print("WARNING: Graph build failed — run 'smt build' after fixing the error above")
    else:
        print(f"\n  src/                   [SKIP] — No src/ directory found; run 'smt build --dir {target_dir}' when ready")

    # ------------------------------------------------------------------
    # 6. Anchor with initial git commit
    # ------------------------------------------------------------------
    try:
        _git_initial_commit(target_dir)
    except Exception as e:
        print(f"  git commit             [WARN] — {e}")

    # ------------------------------------------------------------------
    # 7. Install post-commit hook
    # ------------------------------------------------------------------
    try:
        cmd_setup_hooks(target_dir)
    except Exception as e:
        print(f"Warning: Failed to setup git hook: {e}")

    print(f"\nSetup complete! Graph is synced with git.")
    print(f"  Every git commit will now auto-update the graph via post-commit hook.")
    print(f"  Manual sync: smt sync")
    print(f"  Graph status: smt status")

    return 0


# ---------------------------------------------------------------------------
# hooks
# ---------------------------------------------------------------------------

def cmd_setup_hooks(target_dir: Path) -> bool:
    """Install post-commit hook for automatic graph sync.

    Args:
        target_dir: Target project directory

    Returns:
        True if hook was installed, False otherwise
    """
    git_dir = target_dir / '.git'
    if not git_dir.exists():
        logger.warning(f".git not found in {target_dir}, skipping hook setup")
        return False

    hooks_dir = git_dir / 'hooks'
    if not hooks_dir.exists():
        logger.debug(f"Creating .git/hooks directory")
        hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_file = hooks_dir / 'post-commit'
    smt_marker = "# SMT: Auto-sync graph on commit"

    # Read existing hook if present
    existing_content = ""
    if hook_file.exists():
        with open(hook_file, 'r', encoding='utf-8') as f:
            existing_content = f.read()

        # Check if SMT hook already installed (idempotent)
        if smt_marker in existing_content:
            logger.debug(f"SMT hook already installed in {hook_file}")
            return True

    # Append SMT hook to existing content
    smt_hook = f"""{smt_marker}
smt sync HEAD~1..HEAD >/dev/null 2>&1 &
exit 0
"""

    new_content = existing_content
    if existing_content and not existing_content.endswith('\n'):
        new_content += '\n'
    new_content += smt_hook

    # Write hook file
    with open(hook_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    # Make executable
    st = hook_file.stat()
    hook_file.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    logger.info(f"Installed post-commit hook at {hook_file}")
    print(f"  .git/hooks/post-commit [OK] — Graph will sync after each commit")
    return True


def cmd_remove_hooks(target_dir: Path) -> bool:
    """Remove SMT post-commit hook.

    Args:
        target_dir: Target project directory

    Returns:
        True if hook was removed, False if not found
    """
    git_dir = target_dir / '.git'
    hook_file = git_dir / 'hooks' / 'post-commit'

    if not hook_file.exists():
        logger.warning(f"Hook file not found: {hook_file}")
        return False

    # Read and remove SMT hook lines
    with open(hook_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Remove SMT hook block
    new_lines = []
    skip_block = False
    for line in lines:
        if "# SMT: Auto-sync graph on commit" in line:
            skip_block = True
            continue
        if skip_block and line.strip() == "exit 0":
            skip_block = False
            continue
        if not skip_block:
            new_lines.append(line)

    # Write back or delete if empty
    if new_lines and any(line.strip() for line in new_lines):
        with open(hook_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        logger.info(f"Removed SMT hook from {hook_file}")
    else:
        hook_file.unlink()
        logger.info(f"Deleted empty hook file {hook_file}")

    return True


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list(module: str | None = None, type_filter: str | None = None, limit: int = 0) -> int:
    """Enumerate all symbols in the graph, optionally filtered by file/module path and type."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    # Normalise type filter to title-case label (e.g. "function" → "Function")
    label_filter = type_filter.capitalize() if type_filter else None

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            conditions = ["NOT n:Commit", "n.file IS NOT NULL"]
            params: dict = {"pid": pid}
            if module:
                conditions.append("n.file CONTAINS $module")
                params["module"] = module
            if label_filter:
                conditions.append(f"n:{label_filter}")

            where_clause = " AND ".join(conditions)
            query = f"""
                MATCH (n {{project_id: $pid}})
                WHERE {where_clause}
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type
                ORDER BY n.file, n.line
            """
            rows = session.run(query, **params).data()

        if not rows:
            filters = []
            if module:
                filters.append(f"module={module!r}")
            if label_filter:
                filters.append(f"type={label_filter}")
            suffix = f" ({', '.join(filters)})" if filters else ""
            print(f"No symbols found{suffix}.")
            return 0

        # Apply limit after retrieval so header count is accurate
        total = len(rows)
        if limit and limit < total:
            rows = rows[:limit]

        from collections import defaultdict
        by_file: dict = defaultdict(list)
        for row in rows:
            by_file[row['file'] or '(unknown)'].append(row)

        filter_parts = []
        if module:
            filter_parts.append(f"module: {module!r}")
        if label_filter:
            filter_parts.append(f"type: {label_filter}")
        filter_note = f"  ({', '.join(filter_parts)})" if filter_parts else ""
        shown = f", showing first {limit}" if limit and limit < total else ""
        print(f"\n{total} symbols across {len(by_file)} files{filter_note}{shown}\n")

        for file_path in sorted(by_file):
            symbols = by_file[file_path]
            try:
                display = str(Path(file_path).relative_to(project_path))
            except ValueError:
                display = file_path
            print(f"  {display}  ({len(symbols)} symbols)")
            for sym in symbols:
                line_str = f":{sym['line']}" if sym['line'] else ""
                print(f"    {sym['name']:<40} [{sym['type']}]{line_str}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# unused
# ---------------------------------------------------------------------------

def cmd_unused(include_dunders: bool = False) -> int:
    """Find symbols with no callers — dead code candidates.

    Dunder methods (__init__, __str__, etc.) are excluded by default because
    they are called implicitly by Python and will never appear as CALLS edges.
    Use --include-dunders to see them anyway.
    """
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                  AND NOT ()-[:CALLS]->(n)
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type
                ORDER BY n.file, n.line
                """,
                pid=pid
            ).data()

        if not include_dunders:
            rows = [r for r in rows if not (r['name'] or '').startswith('__')]

        if not rows:
            print("No unused symbols found — everything is reachable.")
            return 0

        print(f"\n{len(rows)} symbols with no callers (potential dead code):\n")
        for row in rows:
            try:
                display = str(Path(row['file']).relative_to(project_path))
            except (ValueError, TypeError):
                display = Path(row['file'] or '?').name
            line_str = f":{row['line']}" if row['line'] else ""
            print(f"  {row['name']:<45} [{row['type']}]  {display}{line_str}")

        hint = ""
        if not include_dunders:
            hint = "  (dunder methods hidden — use --include-dunders to show them)\n"
        print(f"\n{hint}Note: entry points, public APIs, and test helpers are expected to have no in-graph callers.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------

def cmd_cycles() -> int:
    """Detect and display all circular dependencies in the graph."""
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            node_rows = session.run(
                "MATCH (n {project_id: $pid}) WHERE NOT n:Commit RETURN n.name AS name",
                pid=pid
            ).data()
            edge_rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                RETURN a.name AS src, b.name AS dst
                """,
                pid=pid
            ).data()

        # Build name→file lookup for context display
        name_to_file: dict = {}
        with client.driver.session() as session2:
            file_rows = session2.run(
                "MATCH (n {project_id: $pid}) WHERE n.file IS NOT NULL RETURN n.name AS name, n.file AS file",
                pid=pid,
            ).data()
        for r in file_rows:
            if r['name']:
                name_to_file[r['name']] = r['file']

        node_names = [r['name'] for r in node_rows if r['name']]
        edge_tuples = [(r['src'], r['dst']) for r in edge_rows if r['src'] and r['dst']]

        _, cycle_groups = detect_cycles(node_names, edge_tuples)

        if not cycle_groups:
            print("No circular dependencies found.")
            return 0

        # Sort largest cycles first — they are the most problematic
        cycle_groups_sorted = sorted(cycle_groups, key=lambda cg: len(cg.members), reverse=True)

        print(f"\n{len(cycle_groups_sorted)} circular dependency group(s) (largest first):\n")
        for i, cg in enumerate(cycle_groups_sorted, 1):
            cycle_str = " -> ".join(cg.members) + f" -> {cg.members[0]}"
            print(f"  [{i}] {len(cg.members)} symbols in cycle:")
            print(f"       {cycle_str}")
            for sym in cg.members:
                f_path = name_to_file.get(sym, "")
                if f_path:
                    try:
                        f_display = str(Path(f_path).relative_to(project_path))
                    except ValueError:
                        f_display = f_path
                    print(f"         {sym:<40}  {f_display}")
            print()

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# hot
# ---------------------------------------------------------------------------

def cmd_hot(limit: int = 20) -> int:
    """Most-called symbols — coupling hotspots."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (caller {project_id: $pid})-[:CALLS]->(n {project_id: $pid})
                WHERE NOT n:Commit
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       count(DISTINCT caller) AS caller_count
                ORDER BY caller_count DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No call edges found — build the graph first: smt build")
            return 0

        print(f"\nTop {len(rows)} most-called symbols (coupling hotspots):\n")
        for i, row in enumerate(rows, 1):
            file_base = Path(row['file'] or '?').name
            print(f"  {i:2}. {row['name']:<45} [{row['type']}]  callers={row['caller_count']}  ({file_base})")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

def cmd_path(symbol_a: str, symbol_b: str) -> int:
    """Shortest dependency path between two symbols."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            result = session.run(
                """
                MATCH (a {name: $a, project_id: $pid}), (b {name: $b, project_id: $pid})
                MATCH path = shortestPath((a)-[:CALLS*]->(b))
                RETURN [node IN nodes(path) | node.name] AS path_names,
                       [node IN nodes(path) | node.file] AS path_files,
                       length(path) AS hops
                LIMIT 1
                """,
                a=symbol_a, b=symbol_b, pid=pid
            ).single()

        if not result:
            with client.driver.session() as session:
                a_cnt = session.run(
                    "MATCH (n {name: $name, project_id: $pid}) RETURN count(n) AS cnt",
                    name=symbol_a, pid=pid
                ).single()['cnt']
                b_cnt = session.run(
                    "MATCH (n {name: $name, project_id: $pid}) RETURN count(n) AS cnt",
                    name=symbol_b, pid=pid
                ).single()['cnt']
            if not a_cnt:
                print(f"Symbol '{symbol_a}' not found in graph.")
            elif not b_cnt:
                print(f"Symbol '{symbol_b}' not found in graph.")
            else:
                print(f"No path found from '{symbol_a}' to '{symbol_b}'.")
                print(f"  Hint: smt impact {symbol_b} shows who calls it; smt impact {symbol_a} shows who calls the source.")
            return 1

        path_names = result['path_names']
        path_files = result['path_files']
        hops = result['hops']

        print(f"\nPath: {symbol_a} -> {symbol_b}  ({hops} hop{'s' if hops != 1 else ''})\n")
        for i, (name, file_path) in enumerate(zip(path_names, path_files)):
            file_base = Path(file_path or '?').name
            prefix = "  " if i == 0 else "  -> "
            print(f"{prefix}{name}  ({file_base})")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------

def cmd_modules() -> int:
    """Files ranked by symbol count and cross-file coupling."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            sym_rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND n.file IS NOT NULL
                RETURN n.file AS file, count(n) AS symbol_count
                ORDER BY symbol_count DESC
                """,
                pid=pid
            ).data()

            # Cross-file coupling: each file appears once per cross-file edge it participates in
            coupling_rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                WHERE a.file <> b.file AND a.file IS NOT NULL AND b.file IS NOT NULL
                UNWIND [a.file, b.file] AS file
                RETURN file, count(*) AS coupling
                """,
                pid=pid
            ).data()

        if not sym_rows:
            print("No symbols found — build the graph first: smt build")
            return 0

        coupling_map = {r['file']: r['coupling'] for r in coupling_rows}

        sorted_rows = sorted(
            sym_rows,
            key=lambda r: (-(coupling_map.get(r['file'], 0)), -r['symbol_count'])
        )

        print(f"\n{len(sorted_rows)} modules ranked by coupling:\n")
        col = 52
        print(f"  {'Module':<{col}} {'Symbols':>7}  {'Coupling':>8}")
        print(f"  {'-'*col} {'-'*7}  {'-'*8}")

        for row in sorted_rows:
            file_path = row['file'] or '(unknown)'
            try:
                display = str(Path(file_path).relative_to(project_path))
            except ValueError:
                display = Path(file_path).name
            coupling = coupling_map.get(row['file'], 0)
            # Truncate long paths
            if len(display) > col:
                display = "..." + display[-(col - 3):]
            print(f"  {display:<{col}} {row['symbol_count']:>7}  {coupling:>8}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------

def cmd_changes(commit_range: str = 'HEAD~1..HEAD') -> int:
    """Show symbols in git-changed files with caller impact, pinpointing changed lines."""
    import re

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        # 1. Get changed files with status (A=added, M=modified, D=deleted, R=renamed)
        status_result = subprocess.run(
            ['git', 'diff', '--name-status', commit_range],
            cwd=project_path, capture_output=True, text=True
        )
        if status_result.returncode != 0:
            print(f"ERROR: git diff failed: {status_result.stderr.strip()}")
            print(f"  Make sure {commit_range!r} is a valid git range.")
            return 1

        file_statuses: dict[str, str] = {}
        for line in status_result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split('\t')
            status = parts[0][0]
            fname = parts[-1]
            file_statuses[str(project_path / fname)] = status

        if not file_statuses:
            print(f"No file changes found in range: {commit_range}")
            return 0

        # 2. Get changed line ranges for modified files (to pinpoint which symbols changed)
        modified_abs = [p for p, s in file_statuses.items() if s == 'M']
        file_ranges: dict[str, list] = {}
        if modified_abs:
            rel_files = [str(Path(f).relative_to(project_path)) for f in modified_abs]
            hunk_result = subprocess.run(
                ['git', 'diff', '--unified=0', commit_range, '--'] + rel_files,
                cwd=project_path, capture_output=True, text=True
            )
            current = None
            for line in hunk_result.stdout.splitlines():
                if line.startswith('+++ b/'):
                    current = str(project_path / line[6:].strip())
                elif line.startswith('@@') and current:
                    m = re.search(r'\+(\d+)(?:,(\d+))?', line)
                    if m:
                        start = int(m.group(1))
                        count = int(m.group(2)) if m.group(2) is not None else 1
                        if count > 0:
                            file_ranges.setdefault(current, []).append((start, start + count - 1))

        # 3. Query graph for symbols in changed files
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file IN $files AND NOT n:Commit
                WITH n,
                     size([(caller {project_id: $pid})-[:CALLS]->(n) | caller]) AS caller_count
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type, caller_count
                ORDER BY n.file, n.line
                """,
                pid=pid, files=list(file_statuses.keys())
            ).data()

        if not rows:
            print(f"No indexed symbols found in changed files for range: {commit_range}")
            print(f"  {len(file_statuses)} file(s) changed — run 'smt build' if the graph is empty.")
            return 0

        # 4. Group by file and display
        from collections import defaultdict
        by_file: dict = defaultdict(list)
        for row in rows:
            by_file[row['file']].append(row)

        STATUS_LABEL = {'A': 'added', 'D': 'deleted', 'M': 'modified', 'R': 'renamed'}

        def sym_in_range(sym_line, ranges) -> bool:
            if not ranges or not sym_line:
                return False
            return any(s <= sym_line <= e for s, e in ranges)

        print(f"\nChanges: {commit_range}\n")

        total_changed_syms = 0
        for abs_path in sorted(by_file):
            syms = by_file[abs_path]
            status = file_statuses.get(abs_path, 'M')
            label = STATUS_LABEL.get(status, 'changed')
            try:
                display = str(Path(abs_path).relative_to(project_path))
            except ValueError:
                display = abs_path

            ranges = file_ranges.get(abs_path, [])

            if status in ('A', 'D'):
                # All symbols in added/deleted files are affected
                direct = syms
                indirect: list = []
            else:
                direct = [s for s in syms if sym_in_range(s.get('line'), ranges)]
                indirect = [s for s in syms if not sym_in_range(s.get('line'), ranges)]

            total_changed_syms += len(direct)
            print(f"  {display}  [{label}]")

            if direct:
                direct.sort(key=lambda s: s['caller_count'], reverse=True)
                print(f"    changed ({len(direct)}):")
                for sym in direct:
                    callers = sym['caller_count']
                    impact = f"  <- {callers} caller{'s' if callers != 1 else ''}" if callers else ""
                    print(f"      {sym['name']:<42} [{sym['type']}]{impact}")

            if indirect and status == 'M':
                shown = indirect[:4]
                print(f"    unchanged in file ({len(indirect)}):")
                for sym in shown:
                    callers = sym['caller_count']
                    impact = f"  <- {callers}" if callers else ""
                    print(f"      {sym['name']:<42} [{sym['type']}]{impact}")
                if len(indirect) > 4:
                    print(f"      ... and {len(indirect) - 4} more")
            print()

        total_affected_callers = sum(
            s['caller_count'] for syms in by_file.values() for s in syms if s['caller_count']
        )
        print(f"  {total_changed_syms} directly-changed symbols across {len(by_file)} files"
              f"  ({total_affected_callers} total caller edges affected)")
        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        logger.debug("cmd_changes error", exc_info=True)
        return 1


# ---------------------------------------------------------------------------
# complexity
# ---------------------------------------------------------------------------

def cmd_complexity(limit: int = 20) -> int:
    """Rank symbols by fan-in × fan-out — identifies 'god functions' that are
    both hard to change (many callees) and high blast-radius (many callers)."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                WITH n,
                     size([(caller {project_id: $pid})-[:CALLS]->(n) | caller]) AS fan_in,
                     size([(n)-[:CALLS]->(callee {project_id: $pid}) | callee]) AS fan_out
                WHERE fan_in > 0 OR fan_out > 0
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       fan_in, fan_out, (fan_in * fan_out) AS score
                ORDER BY score DESC, fan_in DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No symbols with call edges found — build the graph first: smt build")
            return 0

        print(f"\nTop {len(rows)} by complexity (fan-in × fan-out):\n")
        print(f"  {'Symbol':<45} {'Type':<10} {'In':>4}  {'Out':>4}  {'Score':>6}  File")
        print(f"  {'-'*45} {'-'*10} {'-'*4}  {'-'*4}  {'-'*6}  ----")

        for row in rows:
            try:
                file_display = str(Path(row['file']).relative_to(project_path))
            except (ValueError, TypeError):
                file_display = Path(row['file'] or '?').name
            print(
                f"  {row['name']:<45} {row['type']:<10} "
                f"{row['fan_in']:>4}  {row['fan_out']:>4}  {row['score']:>6}  {file_display}"
            )

        print(f"\nScore = callers × callees.  High score = hard to refactor + large blast radius.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------

def cmd_scope(file_filter: str) -> int:
    """File-level surface analysis: what a file exports, what it imports, internal symbols."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        # Resolve which file the filter points to
        with client.driver.session() as session:
            file_rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file IS NOT NULL AND n.file CONTAINS $filter AND NOT n:Commit
                RETURN DISTINCT n.file AS file ORDER BY n.file
                """,
                pid=pid, filter=file_filter
            ).data()

        if not file_rows:
            print(f"No symbols found for file filter: {file_filter!r}")
            return 1

        if len(file_rows) > 1:
            print(f"Multiple files match {file_filter!r} — be more specific:\n")
            for r in file_rows[:10]:
                try:
                    print(f"  {Path(r['file']).relative_to(project_path)}")
                except ValueError:
                    print(f"  {r['file']}")
            return 1

        file_abs = file_rows[0]['file']
        try:
            display = str(Path(file_abs).relative_to(project_path))
        except ValueError:
            display = file_abs

        with client.driver.session() as session:
            all_syms = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file = $file AND NOT n:Commit
                RETURN n.name AS name, n.line AS line, labels(n)[0] AS type
                ORDER BY n.line
                """,
                pid=pid, file=file_abs
            ).data()

            # Exports: called by symbols in OTHER files
            exports = session.run(
                """
                MATCH (caller {project_id: $pid})-[:CALLS]->(n {project_id: $pid})
                WHERE n.file = $file AND caller.file <> $file
                RETURN n.name AS name, n.line AS line, labels(n)[0] AS type,
                       n.docstring AS docstring,
                       count(DISTINCT caller) AS external_callers,
                       collect(DISTINCT caller.file)[..3] AS sample_files
                ORDER BY external_callers DESC
                """,
                pid=pid, file=file_abs
            ).data()

            # Imports: symbols from OTHER files called by this file's symbols
            imports = session.run(
                """
                MATCH (n {project_id: $pid})-[:CALLS]->(dep {project_id: $pid})
                WHERE n.file = $file AND dep.file <> $file
                RETURN dep.name AS name, dep.file AS dep_file,
                       labels(dep)[0] AS type,
                       count(DISTINCT n) AS usage_count
                ORDER BY dep.file, dep.name
                """,
                pid=pid, file=file_abs
            ).data()

        exported_names = {r['name'] for r in exports}
        imported_names = {r['name'] for r in imports}
        internal_syms = [
            s for s in all_syms
            if s['name'] not in exported_names and s['name'] not in imported_names
        ]

        print(f"\nScope: {display}\n")
        print(f"  {len(all_syms)} symbols total  |  "
              f"{len(exports)} exported  |  "
              f"{len(imports)} imported  |  "
              f"{len(internal_syms)} internal\n")

        if exports:
            print(f"  exports — called by other files ({len(exports)}):")
            for r in exports:
                caller_files = [Path(f).name for f in (r.get('sample_files') or [])]
                suffix = (f"  <- {r['external_callers']} caller{'s' if r['external_callers'] != 1 else ''}"
                          f" ({', '.join(caller_files[:2])}{'...' if len(caller_files) > 2 else ''})")
                doc = r.get('docstring') or ''
                doc_line = doc.splitlines()[0].strip()[:60] if doc else ''
                doc_suffix = f"  # {doc_line}" if doc_line else ""
                print(f"    {r['name']:<45} [{r['type']}]{suffix}{doc_suffix}")

        if imports:
            from collections import defaultdict
            by_src: dict = defaultdict(list)
            for r in imports:
                by_src[r['dep_file']].append(r)
            print(f"\n  imports — calls into other files ({len(imports)} symbols from {len(by_src)} files):")
            for dep_file in sorted(by_src):
                deps = by_src[dep_file]
                try:
                    dep_display = str(Path(dep_file).relative_to(project_path))
                except ValueError:
                    dep_display = Path(dep_file).name
                print(f"    from {dep_display}:")
                for dep in deps:
                    print(f"      {dep['name']}  [{dep['type']}]")

        if internal_syms:
            print(f"\n  internal — not directly coupled across files ({len(internal_syms)}):")
            for sym in internal_syms:
                line_str = f":{sym['line']}" if sym['line'] else ""
                print(f"    {sym['name']:<45} [{sym['type']}]{line_str}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# bottleneck
# ---------------------------------------------------------------------------

def cmd_bottleneck(limit: int = 10) -> int:
    """Find architectural bottleneck nodes — symbols that bridge distinct file clusters.

    Bridge score = (distinct caller files) × (distinct callee files), counting only
    cross-file edges. High score = structural connector between subsystems.
    """
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                OPTIONAL MATCH (caller {project_id: $pid})-[:CALLS]->(n)
                  WHERE caller.file <> n.file
                WITH n, collect(DISTINCT caller.file) AS caller_files
                OPTIONAL MATCH (n)-[:CALLS]->(callee {project_id: $pid})
                  WHERE callee.file <> n.file
                WITH n, caller_files, collect(DISTINCT callee.file) AS callee_files
                WHERE size(caller_files) > 0 AND size(callee_files) > 0
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       size(caller_files) AS caller_file_count,
                       size(callee_files) AS callee_file_count,
                       size(caller_files) * size(callee_files) AS bridge_score,
                       caller_files, callee_files
                ORDER BY bridge_score DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No cross-file call edges found — the graph may be empty or all code is in one file.")
            return 0

        print(f"\nTop {limit} architectural bottlenecks (cross-file bridge score):\n")
        print(f"  {'Symbol':<45} {'Type':<10} {'Caller files':>12}  {'Callee files':>12}  {'Score':>6}")
        print(f"  {'-'*45} {'-'*10} {'-'*12}  {'-'*12}  {'-'*6}")

        for row in rows:
            file_base = Path(row['file'] or '?').name
            print(
                f"  {row['name']:<45} {row['type']:<10} "
                f"{row['caller_file_count']:>12}  {row['callee_file_count']:>12}  "
                f"{row['bridge_score']:>6}  ({file_base})"
            )
            # Show which files connect through this bottleneck
            caller_files = [Path(f).name for f in (row.get('caller_files') or [])[:3]]
            callee_files = [Path(f).name for f in (row.get('callee_files') or [])[:3]]
            if caller_files and callee_files:
                print(f"    {', '.join(caller_files)} --> [this] --> {', '.join(callee_files)}")

        print(f"\nScore = (distinct caller files) × (distinct callee files) via cross-file edges.")
        print(f"High score = structural bridge. Refactoring these requires coordinating across files.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# layer
# ---------------------------------------------------------------------------

_DEFAULT_LAYERS_CONFIG = {
    "_comment": (
        "Layers are ordered from highest (index 0) to lowest (last index). "
        "A layer may only call downward (higher index). "
        "Edit 'paths' to match your project layout — use file path substrings. "
        "Add 'allowlist' entries for intentional cross-layer dependencies."
    ),
    "layers": [
        {"name": "cli",      "paths": ["cli/", "cmd/", "main.py", "_cli.py"]},
        {"name": "api",      "paths": ["api/", "routes/", "views/", "handlers/"]},
        {"name": "services", "paths": ["services/", "usecases/", "application/"]},
        {"name": "domain",   "paths": ["domain/", "models/", "entities/"]},
        {"name": "infra",    "paths": ["db/", "repo", "storage/", "clients/"]},
        {"name": "config",   "paths": ["config.py", "settings.py", "config/"]},
    ],
    "allowlist": [
        # {"from": "infra", "to": "domain", "reason": "Repository returns domain entities"}
    ],
}


def cmd_layer(config_path: str | None = None) -> int:
    """Detect architecture layer violations: calls from lower layers into higher ones."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    # Load or create config
    cfg_file = Path(config_path) if config_path else project_path / '.smt_layers.json'
    if cfg_file.exists():
        with open(cfg_file, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        print(f"Layer config: {cfg_file}")
    else:
        cfg = _DEFAULT_LAYERS_CONFIG
        # Write default so user can customize it
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Created default layer config: {cfg_file}")
        print(f"Edit it to match your project layout, then re-run.\n")

    layers = cfg.get('layers', [])
    if not layers:
        print("ERROR: No layers defined in config.")
        return 1

    # Build allowlist as set of (from_layer_name, to_layer_name)
    raw_allowlist = cfg.get('allowlist', [])
    allowlist: set = {(e['from'], e['to']) for e in raw_allowlist if 'from' in e and 'to' in e}

    def _file_layer(file_path: str) -> int | None:
        """Return the layer index for a file path, or None if unclassified."""
        for i, layer in enumerate(layers):
            for pattern in layer.get('paths', []):
                if pattern in file_path:
                    return i
        return None

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        # Get all cross-file CALLS edges
        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                WHERE a.file <> b.file
                  AND a.file IS NOT NULL AND b.file IS NOT NULL
                RETURN a.name AS src_name, a.file AS src_file,
                       b.name AS dst_name, b.file AS dst_file
                """,
                pid=pid
            ).data()

        if not rows:
            print("No cross-file call edges found in graph.")
            return 0

        # Classify each edge
        violations = []
        allowed_violations = []
        unclassified_files: set = set()

        for row in rows:
            src_layer = _file_layer(row['src_file'])
            dst_layer = _file_layer(row['dst_file'])

            if src_layer is None:
                unclassified_files.add(row['src_file'])
            if dst_layer is None:
                unclassified_files.add(row['dst_file'])

            if src_layer is None or dst_layer is None:
                continue

            # Violation: a deeper module (higher index) calls upward into a shallower one
            if src_layer > dst_layer:
                src_name = layers[src_layer]['name']
                dst_name = layers[dst_layer]['name']
                entry = {
                    'src_name': row['src_name'],
                    'src_file': row['src_file'],
                    'src_layer': src_name,
                    'dst_name': row['dst_name'],
                    'dst_file': row['dst_file'],
                    'dst_layer': dst_name,
                }
                if (src_name, dst_name) in allowlist:
                    allowed_violations.append(entry)
                else:
                    violations.append(entry)

        # Print layer definition
        print(f"\nLayer stack (index 0 = top, can call downward only):\n")
        for i, layer in enumerate(layers):
            print(f"  [{i}] {layer['name']:<12} — {', '.join(layer['paths'])}")

        print()

        if not violations:
            allowed_note = f"  ({len(allowed_violations)} allowlisted)" if allowed_violations else ""
            print(f"No layer violations found. ({len(rows)} cross-file edges checked){allowed_note}")
            return 0

        # Deduplicate by (src_layer, dst_layer, src_file, dst_file)
        seen: set = set()
        deduped = []
        for v in violations:
            key = (v['src_layer'], v['dst_layer'], v['src_file'], v['dst_file'])
            if key not in seen:
                seen.add(key)
                deduped.append(v)

        allowed_note = f"  ({len(allowed_violations)} allowlisted)" if allowed_violations else ""
        print(f"{len(deduped)} layer violation(s) found ({len(violations)} edges total){allowed_note}:\n")
        for v in deduped:
            try:
                src_display = str(Path(v['src_file']).relative_to(project_path))
            except ValueError:
                src_display = v['src_file']
            try:
                dst_display = str(Path(v['dst_file']).relative_to(project_path))
            except ValueError:
                dst_display = v['dst_file']
            print(f"  [!] {v['src_layer']} -> {v['dst_layer']}  (forbidden: lower layer calls upper)")
            print(f"      {src_display}")
            print(f"      calls {dst_display}")
            print()

        if allowlist:
            print(f"  Allowlisted pairs (intentional): {', '.join(f'{a}->{b}' for a, b in sorted(allowlist))}")
            print(f"  Add to 'allowlist' in {cfg_file} to suppress a violation.")
        if unclassified_files:
            print(f"  {len(unclassified_files)} file(s) not matched by any layer (ignored).")
            print(f"  Add path patterns to {cfg_file} to classify them.")

        return 1  # Non-zero = violations found (useful for CI)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog='smt',
        description='save-my-tokens — intelligent code context via CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  build                  Build graph from src/
  build --check          Show graph stats
  build --clear          Wipe and rebuild
  definition <symbol>    Symbol definition (fast, 1-hop)
  context <symbol>       Symbol context (bidirectional, bounded)
  context <symbol> --callers  Who calls this symbol
  impact <symbol>        Impact analysis (reverse traversal)
  search <query>         Semantic search
  sync [range]           Sync graph with git commits (default: HEAD~1..HEAD)
  watch [--debounce N]   Auto-sync graph when files change (live mode)
  explain <symbol>       Print symbol context formatted for Claude to explain
  hooks install|uninstall Auto-sync hooks for git commits
  docker up|down|status  Manage Neo4j container
  status                 Graph health check
  setup [--dir <path>]   Configure a project
  onboard project|agent|check Guided setup and orientation

graph analysis:
  list [--module X]      Enumerate all symbols (filter by file path)
  unused                 Symbols with no callers — dead code candidates
  cycles                 Circular dependencies in the call graph
  hot [--top N]          Most-called symbols — coupling hotspots
  path <A> <B>           Shortest dependency path between two symbols
  modules                Files ranked by symbol count and coupling

advanced analysis:
  changes [RANGE]        Symbols in git-changed files with caller impact
  complexity [--top N]   fan-in × fan-out — god function detection
  scope <file>           File surface: exports, imports, internal symbols
  bottleneck [--top N]   Cross-file bridge nodes — architectural chokepoints
  layer [--config PATH]  Architecture layer violation detection
        """
    )

    sub = parser.add_subparsers(dest='command')

    # build
    p_build = sub.add_parser('build', help='Build graph')
    p_build.add_argument('--dir', default=None, help='Target project directory (default: cwd)')
    p_build.add_argument('--check', action='store_true', help='Show stats only')
    p_build.add_argument('--clear', action='store_true', help='Wipe and rebuild')

    # context
    p_ctx = sub.add_parser('context', help='Symbol context (bidirectional, bounded)')
    p_ctx.add_argument('symbol')
    p_ctx.add_argument('--depth', type=int, default=1)
    p_ctx.add_argument('--callers', action='store_true')
    p_ctx.add_argument('--file', default=None, help='Filter by file path (substring match)')
    p_ctx.add_argument('--compress', action='store_true', help='Remove bridge functions to reduce tokens')
    p_ctx.add_argument('--json', action='store_true', help='Output as JSON')

    # definition
    p_def = sub.add_parser('definition', help='Symbol definition (fast, 1-hop)')
    p_def.add_argument('symbol')
    p_def.add_argument('--file', default=None, help='Filter by file path (substring match)')
    p_def.add_argument('--json', action='store_true', help='Output as JSON')

    # impact
    p_impact = sub.add_parser('impact', help='Impact analysis: what breaks if I change this?')
    p_impact.add_argument('symbol')
    p_impact.add_argument('--depth', type=int, default=3, help='Maximum depth for impact traversal')
    p_impact.add_argument('--compress', action='store_true', help='Remove bridge functions to reduce tokens')
    p_impact.add_argument('--json', action='store_true', help='Output as JSON')

    # search
    p_search = sub.add_parser('search', help='Semantic search')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)
    p_search.add_argument('--json', action='store_true', help='Output as JSON')
    follow_grp = p_search.add_mutually_exclusive_group()
    follow_grp.add_argument('--context', action='store_true', help='Show context for top result')
    follow_grp.add_argument('--impact', action='store_true', help='Show impact for top result')

    # sync (incremental graph update from git commits)
    p_sync = sub.add_parser('sync', help='Sync graph with git commits (incremental update)')
    p_sync.add_argument('range', nargs='?', default='HEAD~1..HEAD')
    p_sync.add_argument('--dir', default=None, help='Target project directory (default: cwd)')

    # watch (file-system watcher — auto-sync on save)
    p_watch = sub.add_parser('watch', help='Watch files and auto-sync graph on change')
    p_watch.add_argument('--dir', default=None, help='Target project directory (default: cwd)')
    p_watch.add_argument('--debounce', type=float, default=2.0,
                         help='Seconds to wait after last change before syncing (default: 2)')

    # explain (Claude-powered symbol explanation)
    p_explain = sub.add_parser('explain', help='Explain a symbol in plain English using Claude')
    p_explain.add_argument('symbol')
    p_explain.add_argument('--depth', type=int, default=2, help='Context graph depth (default: 2)')

    # docker
    p_docker = sub.add_parser('docker', help='Manage Neo4j container')
    p_docker.add_argument('action', choices=['up', 'down', 'status'])

    # status
    sub.add_parser('status', help='Graph health check')

    # setup
    p_setup = sub.add_parser('setup', help='Configure a project')
    p_setup.add_argument('--dir', default='.', help='Target project directory')

    # hooks
    p_hooks = sub.add_parser('hooks', help='Manage git hooks')
    p_hooks.add_argument('action', choices=['install', 'uninstall'], help='Hook action')
    p_hooks.add_argument('--dir', default=None, help='Target project directory (default: cwd)')

    # onboard
    p_onboard = sub.add_parser('onboard', help='Guided setup and orientation')
    p_onboard.add_argument('action', choices=['project', 'agent', 'check'],
                           help='project=guided setup, agent=orientation, check=health check')
    p_onboard.add_argument('--dir', default=None, help='Target project directory (default: cwd)')

    # list
    p_list = sub.add_parser('list', help='Enumerate all symbols (optionally filter by module/type)')
    p_list.add_argument('--module', default=None, help='Filter by file path substring (e.g. graph)')
    p_list.add_argument('--type', dest='type_filter', default=None,
                        help='Filter by symbol type: function, class, variable, module')
    p_list.add_argument('--limit', type=int, default=0,
                        help='Maximum number of symbols to show (default: all)')

    # unused
    p_unused = sub.add_parser('unused', help='Symbols with no callers — dead code candidates')
    p_unused.add_argument('--include-dunders', action='store_true',
                          help='Include dunder methods like __init__, __str__ (hidden by default)')

    # cycles
    sub.add_parser('cycles', help='Circular dependencies in the call graph')

    # hot
    p_hot = sub.add_parser('hot', help='Most-called symbols — coupling hotspots')
    p_hot.add_argument('--top', type=int, default=20, help='Number of results (default: 20)')

    # path
    p_path = sub.add_parser('path', help='Shortest dependency path between two symbols')
    p_path.add_argument('symbol_a', help='Source symbol name')
    p_path.add_argument('symbol_b', help='Target symbol name')

    # modules
    sub.add_parser('modules', help='Files ranked by symbol count and cross-file coupling')

    # changes
    p_changes = sub.add_parser('changes', help='Symbols in git-changed files with caller impact')
    p_changes.add_argument('range', nargs='?', default='HEAD~1..HEAD',
                           help='Git range (default: HEAD~1..HEAD)')

    # complexity
    p_complexity = sub.add_parser('complexity', help='fan-in × fan-out — god function detection')
    p_complexity.add_argument('--top', type=int, default=20, help='Number of results (default: 20)')

    # scope
    p_scope = sub.add_parser('scope', help='File surface: exports, imports, internal symbols')
    p_scope.add_argument('file', help='File path substring (e.g. graph_builder, parsers/python)')

    # bottleneck
    p_bottleneck = sub.add_parser('bottleneck', help='Cross-file bridge nodes — architectural chokepoints')
    p_bottleneck.add_argument('--top', type=int, default=10, help='Number of results (default: 10)')

    # layer
    p_layer = sub.add_parser('layer', help='Architecture layer violation detection')
    p_layer.add_argument('--config', default=None,
                         help='Path to .smt_layers.json (default: <project>/.smt_layers.json)')

    args = parser.parse_args()

    if args.command == 'build':
        return cmd_build(check=args.check, clear=args.clear, target_dir=args.dir)
    elif args.command == 'context':
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.context(args.symbol, depth=args.depth, compress=args.compress)
            print(json.dumps(result, indent=2))
            return 0 if result.get('found') else 1
        return cmd_context(args.symbol, depth=args.depth, callers=args.callers,
                          file_filter=args.file, compress=args.compress)
    elif args.command == 'definition':
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.definition(args.symbol)
            print(json.dumps(result, indent=2))
            return 0 if result.get('found') else 1
        return cmd_definition(args.symbol, file_filter=args.file)
    elif args.command == 'impact':
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.impact(args.symbol, depth=args.depth)
            print(json.dumps(result, indent=2))
            return 0 if result.get('found') else 1
        return cmd_impact(args.symbol, max_depth=args.depth, compress=args.compress)
    elif args.command == 'search':
        if getattr(args, 'json', False):
            engine = _get_engine()
            results = engine.search(args.query, top_k=args.top)
            print(json.dumps(results, indent=2))
            return 0
        follow = 'context' if getattr(args, 'context', False) else ('impact' if getattr(args, 'impact', False) else None)
        return cmd_search(args.query, top_k=args.top, follow=follow)
    elif args.command == 'sync':
        return cmd_sync(commit_range=args.range, target_dir=args.dir)
    elif args.command == 'watch':
        return cmd_watch(target_dir=args.dir, debounce=args.debounce)
    elif args.command == 'explain':
        return cmd_explain(args.symbol, depth=args.depth)
    elif args.command == 'docker':
        return cmd_docker(args.action)
    elif args.command == 'status':
        return cmd_status()
    elif args.command == 'setup':
        return cmd_setup(Path(args.dir))
    elif args.command == 'hooks':
        target_dir = Path(args.dir) if args.dir else Path.cwd()
        if args.action == 'install':
            try:
                success = cmd_setup_hooks(target_dir)
                return 0 if success else 1
            except Exception as e:
                print(f"ERROR: Failed to install hook: {e}")
                return 1
        elif args.action == 'uninstall':
            try:
                success = cmd_remove_hooks(target_dir)
                if success:
                    print(f"✓ Removed SMT hook from {target_dir}/.git/hooks/post-commit")
                else:
                    print(f"✗ Hook not found in {target_dir}/.git/hooks/post-commit")
                return 0 if success else 1
            except Exception as e:
                print(f"ERROR: Failed to remove hook: {e}")
                return 1
    elif args.command == 'onboard':
        target_dir = Path(args.dir) if args.dir else None
        return cmd_onboard(args.action, target_dir=target_dir)
    elif args.command == 'list':
        return cmd_list(module=args.module, type_filter=getattr(args, 'type_filter', None),
                        limit=getattr(args, 'limit', 0))
    elif args.command == 'unused':
        return cmd_unused(include_dunders=getattr(args, 'include_dunders', False))
    elif args.command == 'cycles':
        return cmd_cycles()
    elif args.command == 'hot':
        return cmd_hot(limit=args.top)
    elif args.command == 'path':
        return cmd_path(args.symbol_a, args.symbol_b)
    elif args.command == 'modules':
        return cmd_modules()
    elif args.command == 'changes':
        return cmd_changes(commit_range=args.range)
    elif args.command == 'complexity':
        return cmd_complexity(limit=args.top)
    elif args.command == 'scope':
        return cmd_scope(args.file)
    elif args.command == 'bottleneck':
        return cmd_bottleneck(limit=args.top)
    elif args.command == 'layer':
        return cmd_layer(config_path=args.config)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    finally:
        _close_neo4j_client()
