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

    smt start                      # Start Neo4j container
    smt stop                       # Stop Neo4j container

    smt status                     # Graph health check (includes container state)
    smt setup [--dir <path>]       # Configure a project (.claude/settings.json)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# When running inside an agent harness (SMT_AGENT=1 set via .claude/settings.json):
#   - suppress all non-error logs (no noise in tool output)
#   - strip ANSI color codes from stdout (escape sequences waste tokens)
if os.environ.get("SMT_AGENT"):
    logger.remove()
    logger.add(sys.stderr, level="ERROR")

    import re as _re

    class _StripAnsi:
        _pat = _re.compile(r"\x1b\[[0-9;]*[mGKHF]")

        def __init__(self, stream):
            self._s = stream

        def write(self, text):
            self._s.write(self._pat.sub("", text))

        def flush(self):
            self._s.flush()

        def __getattr__(self, name):
            return getattr(self._s, name)

    sys.stdout = _StripAnsi(sys.stdout)

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SMT_DIR = Path(__file__).parent.parent.resolve()

# Ensure repo root is on sys.path so bare-module imports (cli_utils, src.*) work
if str(SMT_DIR) not in sys.path:
    sys.path.insert(0, str(SMT_DIR))

# ---------------------------------------------------------------------------
# Shared helpers and sub-module commands (extracted from this file)
# ---------------------------------------------------------------------------

from src.cli._helpers import (
    Colors,
    _C,
    _close_neo4j_client,
    _ensure_smtignore,
    _get_default_depth,
    _get_engine,
    _get_neo4j_client,
    _get_project_id,
    _get_services,
    _get_validation,
    _git_initial_commit,
    _require_git,
    _resolve_project_path,
)
from src.cli.analysis import (
    cmd_bottleneck,
    cmd_breaking_changes,
    cmd_changes,
    cmd_complexity,
    cmd_cycles,
    cmd_hot,
    cmd_layer,
    cmd_list,
    cmd_modules,
    cmd_path,
    cmd_scope,
    cmd_unused,
)
from src.cli.setup import (
    _A2A_AGENT_CARD,
    cmd_remove_hooks,
    cmd_setup,
    cmd_setup_hooks,
)
from src.cli.watch import cmd_watch


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------

def _docker_compose_cmd() -> list:
    """Return the docker compose command — v2 ('docker compose') preferred, v1 fallback."""
    result = subprocess.run(['docker', 'compose', 'version'], capture_output=True)
    if result.returncode == 0:
        return ['docker', 'compose']
    return ['docker-compose']


_CONFIG_KEYS = {
    'SMT_NEO4J_HEAP_INIT': ('512m', 'Neo4j JVM heap initial size  (e.g. 256m, 512m, 1g)'),
    'SMT_NEO4J_HEAP_MAX':  ('1g',   'Neo4j JVM heap max size       (e.g. 512m, 1g, 2g)'),
    'SMT_NEO4J_PAGECACHE': ('512m', 'Neo4j page-cache size         (e.g. 256m, 512m, 1g)'),
    'NEO4J_PASSWORD':      ('password', 'Neo4j auth password'),
    'NEO4J_URI':           ('bolt://localhost:7687', 'Neo4j bolt URI'),
}


def _read_env() -> dict:
    env_file = SMT_DIR / '.env'
    result: dict = {}
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    env_file = SMT_DIR / '.env'
    lines = env_file.read_text(encoding='utf-8').splitlines() if env_file.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f'{key}=') or stripped == key:
            new_lines.append(f'{key}={value}')
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f'{key}={value}')
    env_file.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


def cmd_config(action: Optional[str], key: Optional[str], value: Optional[str]) -> int:
    env = _read_env()

    if action is None:
        print(f"\n{'KEY':<30} {'CURRENT':<20} {'DEFAULT':<20} DESCRIPTION")
        print('-' * 95)
        for k, (default, desc) in _CONFIG_KEYS.items():
            current = env.get(k, '')
            display = current if current else f'(default: {default})'
            print(f"  {k:<28} {display:<20} {default:<20} {desc}")
        print()
        print("To change a setting:")
        print("  smt config set SMT_NEO4J_HEAP_MAX 1g")
        print("  smt config set SMT_NEO4J_PAGECACHE 512m")
        print()
        print("After changing Neo4j memory, restart the container:")
        print("  smt stop && smt start")
        return 0

    if action == 'set':
        if not key or value is None:
            print("Usage: smt config set <KEY> <VALUE>")
            print("Example: smt config set SMT_NEO4J_HEAP_MAX 1g")
            return 1
        key = key.upper()
        if key not in _CONFIG_KEYS:
            known = ', '.join(_CONFIG_KEYS)
            print(f"Unknown key '{key}'. Configurable keys: {known}")
            return 1
        _write_env_key(key, value)
        _, desc = _CONFIG_KEYS[key]
        print(f"Set {key}={value}  ({desc})")
        if key.startswith('SMT_NEO4J_'):
            print("Restart Neo4j for the change to take effect:  smt stop && smt start")
        return 0

    if action == 'reset':
        for k, (default, _) in _CONFIG_KEYS.items():
            if k in _read_env():
                _write_env_key(k, default)
        print("Reset all SMT config keys to defaults.")
        print("Restart Neo4j:  smt stop && smt start")
        return 0

    print(f"Unknown config action '{action}'. Use: smt config | smt config set KEY VALUE | smt config reset")
    return 1


def _neo4j_bolt_ready(timeout: float = 2.0) -> bool:
    """Check if Neo4j is ready: bolt port (7687) accepts TCP AND HTTP API (7474) responds.

    The bolt port opens before Neo4j finishes initializing its database engine.
    Waiting for the HTTP endpoint ensures the server is actually ready for queries.
    """
    import socket
    import urllib.request
    try:
        with socket.create_connection(('localhost', 7687), timeout=timeout):
            pass
    except OSError:
        return False
    try:
        urllib.request.urlopen('http://localhost:7474', timeout=timeout)
        return True
    except Exception:
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
                print("  Fix: start Docker Desktop, then re-run: smt start")
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

        print("Waiting for Neo4j to be ready...", flush=True)
        max_wait = 120
        elapsed = 0.0
        attempt = 0
        while elapsed < max_wait:
            check = subprocess.run(
                dc + ['-f', str(compose_file), 'ps', '--status', 'running', '-q', 'neo4j'],
                cwd=SMT_DIR, capture_output=True, text=True,
            )
            if check.returncode != 0 or not check.stdout.strip():
                print("ERROR: Neo4j container stopped unexpectedly.")
                print("  Check logs: docker logs save-my-tokens-neo4j")
                return 1
            if _neo4j_bolt_ready():
                print("Neo4j ready (bolt://localhost:7687) — run: smt build")
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
    compose_file = SMT_DIR / 'docker-compose.yml'
    dc = _docker_compose_cmd()
    try:
        ps = subprocess.run(
            dc + ['-f', str(compose_file), 'ps', '--status', 'running', '-q', 'neo4j'],
            cwd=SMT_DIR, capture_output=True, text=True,
        )
        container_running = bool(ps.stdout.strip())
    except Exception:
        container_running = False
    print(f"Container:  {'running' if container_running else 'stopped'}")

    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:7474', timeout=2)
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    print(f"Neo4j:  {'OK  (http://localhost:7474)' if neo4j_ok else 'NOT RUNNING'}")

    if not neo4j_ok:
        print("\nStart Neo4j with:  smt start")
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

        try:
            from src.graph.validator import (
                format_stale_files_line,
                format_validation_line,
                validate_graph,
            )
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

def cmd_build(check: bool = False, clear: bool = False, target_dir: Optional[str] = None) -> int:
    settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, _ = _get_services()

    if check:
        return cmd_status()

    if target_dir:
        target_path = Path(target_dir).resolve()
    else:
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

    if not _require_git(target_path):
        return 1

    _ensure_smtignore(target_path)

    _CANDIDATE_SRC_DIRS = ['src', 'app', 'lib', 'pkg', 'core', 'source']
    src_dir = None
    for dirname in _CANDIDATE_SRC_DIRS:
        candidate = target_path / dirname
        if candidate.exists() and candidate.is_dir():
            src_dir = candidate
            break
    if src_dir is None:
        src_dir = target_path

    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        from loguru import logger
        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        if clear:
            print(f"{Colors.YELLOW}[WARN]{Colors.RESET} Clearing graph data for project: {target_path.name} [{project_id}]")
            client.clear_database()
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

def cmd_context(symbol: str, depth: int = 1, callers: bool = False,
                file_filter: Optional[str] = None, compress: bool = False,
                compact: bool = False, brief: bool = False) -> int:
    from src.graph.compressor import compress_subgraph, format_compression_stats
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        max_depth = max(1, min(depth, 10))
        subgraph = client.get_bounded_subgraph(symbol, max_depth=max_depth, file_filter=file_filter)

        if not subgraph:
            print(f"Symbol '{symbol}' not found in graph.")
            client.driver.close()
            return 1

        root = subgraph["root"]
        nodes = subgraph["nodes"]
        edges = subgraph["edges"]

        labels = root.get("labels", [])
        if compact:
            print(f"{root.get('name')} [{', '.join(labels)}] {root.get('file', '?')}:{root.get('line', '?')}")
            if root.get("signature"):
                print(f"sig: {root.get('signature')}")
            if root.get("docstring") and not brief:
                print(f"doc: {root.get('docstring')[:120]}")
        else:
            print(f"\n{root.get('name')}  [{', '.join(labels)}]")
            print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")
            if root.get("signature"):
                print(f"  sig:  {root.get('signature')}")
            if root.get("docstring") and not brief:
                print(f"  doc:  {root.get('docstring')[:120]}")

        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        original_node_count = len(nodes)
        original_edge_count = len(edges)

        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e[0], e[1]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        acyclic_set = set(acyclic_nodes)
        cyclic_nodes_set = {n for cg in cycle_groups for n in cg.members}

        outbound_calls = [e for e in edge_tuples if e[0] == symbol]
        if outbound_calls:
            if compact:
                call_names = ", ".join(e[1] for e in outbound_calls)
                print(f"calls({len(outbound_calls)}): {call_names}")
            else:
                print(f"\n  calls ({len(outbound_calls)}):")
                for edge in outbound_calls:
                    target = edge[1]
                    target_node = next((n for n in nodes if n["name"] == target), None)
                    file_str = target_node.get("file", "?") if target_node else "?"
                    file_base = Path(file_str).name if file_str != "?" else "?"
                    print(f"    {target}  ({file_base})")

        if cycle_groups:
            for cg in cycle_groups:
                cycle_str = " → ".join(cg.members[:3])
                if len(cg.members) > 3:
                    cycle_str += f" → ... ({len(cg.members)} total)"
                print(f"\n  [Cycle: {cycle_str}]")
                print(f"    {len(cg.members)} functions collapsed")

        if callers or depth > 1:
            with client.driver.session() as session:
                callers_data = session.run(
                    "MATCH (caller)-[:CALLS]->(n {name: $name}) RETURN caller.name AS name, caller.file AS file",
                    name=symbol
                ).data()
                if callers_data:
                    if compact:
                        caller_names = ", ".join(c['name'] for c in callers_data)
                        print(f"callers({len(callers_data)}): {caller_names}")
                    else:
                        print(f"\n  callers ({len(callers_data)}):")
                        for c in callers_data:
                            file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                            print(f"    {c['name']}  ({file_base})")

        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        if compact:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                stats_line = f"context: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            else:
                stats_line = f"nodes={len(nodes)} edges={len(edges)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
                print(f"{stats_line}  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            except Exception as e:
                logger.debug(f"Validation check failed: {e}")
                print(stats_line)
        else:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                print(f"\n  context: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
                print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
            else:
                print(f"\n  context: nodes={len(nodes)} edges={len(edges)} depth={max_depth} "
                      f"cycles={len(cycle_groups)} ~tokens={token_estimate}")
            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
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
# definition
# ---------------------------------------------------------------------------

def cmd_definition(symbol: str, file_filter: Optional[str] = None,
                   compact: bool = False, brief: bool = False) -> int:
    """Fast definition lookup — just the signature and 1-hop callees."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        with client.driver.session() as session:
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
            if compact:
                print(f"{n.get('name')} [{', '.join(n.labels)}] {n.get('file', '?')}:{n.get('line', '?')}")
                if n.get('signature'):
                    print(f"sig: {n.get('signature')}")
                if n.get('docstring') and not brief:
                    print(f"doc: {n.get('docstring')[:120]}")
            else:
                print(f"\n{n.get('name')}  [{', '.join(n.labels)}]")
                print(f"  file: {n.get('file', '?')}:{n.get('line', '?')}")
                if n.get('signature'):
                    print(f"  sig:  {n.get('signature')}")
                if n.get('docstring') and not brief:
                    print(f"  doc:  {n.get('docstring')}")

            callee_pid = "{project_id: $pid}" if project_id else ""
            callees = session.run(
                f"MATCH (n {{name: $name}})-[:CALLS]->(callee {callee_pid}) "
                f"WHERE 1=1 {pid_clause} "
                "RETURN callee.name AS name, callee.file AS file",
                name=symbol, pid=project_id
            ).data()
            if callees:
                if compact:
                    callee_names = ", ".join(c['name'] for c in callees)
                    print(f"calls({len(callees)}): {callee_names}")
                else:
                    print(f"\n  calls ({len(callees)}):")
                    for c in callees:
                        file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                        print(f"    {c['name']}  ({file_base})")

            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
                if compact:
                    print(f"{format_validation_line(validation)}")
                else:
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
# view
# ---------------------------------------------------------------------------

def cmd_view(symbol: str, file_filter: Optional[str] = None, context_lines: int = 0) -> int:
    """Show only the source lines for a symbol — graph lookup then targeted file read."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        with client.driver.session() as session:
            if file_filter:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE n.file CONTAINS $file {pid_clause}
                    RETURN n LIMIT 1
                """
                row = session.run(query, name=symbol, file=file_filter, pid=project_id).single()
            else:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE 1=1 {pid_clause}
                    RETURN n,
                           CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END AS priority
                    ORDER BY priority LIMIT 1
                """
                row = session.run(query, name=symbol, pid=project_id).single()

        client.driver.close()

        if not row:
            print(f"Symbol '{symbol}' not found in graph.")
            return 1

        n = row["n"]
        file_path = n.get("file")
        line_start = n.get("line")
        line_end = n.get("end_line")

        if not file_path or not line_start:
            print(f"Symbol '{symbol}' has no file/line info in graph.")
            return 1

        if not Path(file_path).exists():
            print(f"File not found: {file_path}")
            return 1

        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        # line numbers are 1-indexed; fall back to 30-line window if end_line missing
        start = max(0, line_start - 1 - context_lines)
        end = min(total, (line_end if line_end else line_start + 29) + context_lines)

        label = f"{symbol}  [{', '.join(n.labels)}]"
        range_str = f"lines {start + 1}–{end}" + (f"  (end_line not in graph — showing window)" if not line_end else "")
        print(f"\n{label}")
        print(f"  {file_path}:{line_start}  {range_str}\n")

        width = len(str(end))
        for i, text in enumerate(lines[start:end], start=start + 1):
            marker = ">" if i == line_start else " "
            print(f"  {marker} {str(i).rjust(width)}  {text}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        logger.error(f"cmd_view error: {traceback.format_exc()}")
        return 1


# ---------------------------------------------------------------------------
# impact
# ---------------------------------------------------------------------------

def _compute_depths(
    root: str, edges: list[tuple[str, str]]
) -> dict[str, int]:
    """Compute depth of each node from root via reverse BFS over edges."""
    reverse_edges: dict[str, list[str]] = {}
    for src, dst in edges:
        if dst not in reverse_edges:
            reverse_edges[dst] = []
        reverse_edges[dst].append(src)

    depths = {root: 0}
    queue = [(root, 0)]
    visited = {root}

    while queue:
        node, depth = queue.pop(0)
        for caller in reverse_edges.get(node, []):
            if caller not in visited:
                visited.add(caller)
                depths[caller] = depth + 1
                queue.append((caller, depth + 1))

    return depths


def cmd_impact(symbol: str, max_depth: int = 3, compress: bool = False,
               compact: bool = False, brief: bool = False) -> int:
    """Impact analysis — what breaks if I change this symbol?"""
    from src.graph.compressor import compress_subgraph, format_compression_stats
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        impact_set = client.get_impact_graph(symbol, max_depth=max_depth)

        if not impact_set:
            print(f"Symbol '{symbol}' not found in graph.")
            client.driver.close()
            return 1

        root = impact_set["root"]
        nodes = impact_set["nodes"]
        edges = impact_set["edges"]

        labels = root.get("labels", [])
        total_callers = len([n for n in nodes if n["name"] != symbol])
        if compact:
            print(f"Impact: {root.get('name')} [{', '.join(labels)}] {total_callers} caller{'s' if total_callers != 1 else ''} | {root.get('file', '?')}:{root.get('line', '?')}")
        else:
            print(f"\nImpact: {root.get('name')}  [{', '.join(labels)}]  ({total_callers} caller{'s' if total_callers != 1 else ''})")
            print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")

        depths = _compute_depths(root.get('name', symbol), edges)

        callers_by_depth: dict[int, list[str]] = {}
        for n in nodes:
            node_name = n["name"]
            if node_name != symbol:
                d = depths.get(node_name, max_depth + 1)
                if d not in callers_by_depth:
                    callers_by_depth[d] = []
                callers_by_depth[d].append(node_name)

        for depth_level in sorted(callers_by_depth.keys()):
            callers_list = callers_by_depth[depth_level]
            if compact:
                print(f"depth{depth_level}({len(callers_list)}): {', '.join(sorted(callers_list))}")
            else:
                if depth_level == 1:
                    label = "direct callers"
                else:
                    label = f"indirect callers — depth {depth_level}"
                print(f"\n  {label} ({len(callers_list)}):")
                for caller in sorted(callers_list):
                    caller_node = next((n for n in nodes if n["name"] == caller), None)
                    file_base = Path(caller_node.get("file", "?")).name if caller_node else "?"
                    print(f"    {caller}  ({file_base})")

        original_node_count = len(nodes)
        original_edge_count = len(edges)

        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            depths = _compute_depths(root.get('name', symbol), edges)
            callers_by_depth = {}
            for n in nodes:
                node_name = n["name"]
                if node_name != symbol:
                    d = depths.get(node_name, max_depth + 1)
                    if d not in callers_by_depth:
                        callers_by_depth[d] = []
                    callers_by_depth[d].append(node_name)
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

        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        if compact:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                stats_line = f"impact: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            else:
                stats_line = f"nodes={len(nodes)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
                print(f"{stats_line}  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            except Exception as e:
                logger.debug(f"Validation check failed: {e}")
                print(stats_line)
        else:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                print(f"\n  impact: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
                print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
            else:
                print(f"\n  impact: nodes={len(nodes)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
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

        if not svc.load_index():
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
    """Print a Claude-ready explanation prompt for a symbol."""
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
    print("# (paste this to Claude and ask it to explain)")
    print()
    print(f"Symbol : {root.get('name')}  ({root.get('type')})")
    print(f"File   : {root.get('file')}:{root.get('line')}")
    if root.get('docstring'):
        print(f"Docstr : {root['docstring'][:400]}")
    print()
    print(f"Graph  : {len(nodes)} nodes, {len(edges)} edges (depth={depth})")
    for edge in edges:
        src = edge.get('src', '?')
        tgt = edge.get('dst', '?')
        print(f"  {src} --[CALLS]--> {tgt}")
    print()
    print(f"Prompt : Explain what '{symbol}' does, its role in the architecture,")
    print("         and what to be aware of before modifying it.")
    return 0


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def cmd_sync(commit_range: str = 'HEAD~1..HEAD', target_dir: Optional[str] = None) -> int:
    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    try:
        target_path = Path(target_dir).resolve() if target_dir else _resolve_project_path()

        if not (target_path / '.git').exists():
            print(f"ERROR: No .git directory found in {target_path}")
            return 1

        from loguru import logger

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

        # Guard: single-commit repo — nothing to diff, but record HEAD so validator shows fresh.
        if commit_range == 'HEAD~1..HEAD':
            count_result = subprocess.run(
                ['git', 'rev-list', '--count', 'HEAD'],
                cwd=str(target_path), capture_output=True, text=True,
            )
            if count_result.returncode == 0 and count_result.stdout.strip() == '1':
                try:
                    commit_meta = updater._get_commit_metadata('HEAD', str(target_path))
                    client.create_commit_node(commit_meta)
                    print("✓ Graph marked fresh (single-commit repository)")
                except Exception as e:
                    logger.warning(f"Could not record HEAD commit: {e}")
                    print("Nothing to sync — repository has only one commit.")
                client.driver.close()
                return cmd_status()

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
        logger.debug("cmd_sync error", exc_info=True)
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# onboard
# ---------------------------------------------------------------------------

def cmd_onboard(action: str, target_dir: Optional[Path] = None) -> int:
    """Guided onboarding: setup, orientation, or health check."""

    if action == 'project':
        target = (target_dir or Path.cwd()).resolve()
        print(f"\n{_C.BOLD}SMT Project Onboarding: {target.name}{_C.RESET}\n")

        print("Step 1/3  Starting Neo4j...")
        rc = cmd_docker('up')
        if rc != 0:
            _fail("docker up failed — is Docker Desktop running?")
            print("  Fix: start Docker Desktop, then re-run: smt onboard project")
            return 1
        _ok("Neo4j is ready")

        print("\nStep 2/3  Building graph from source...")
        result = cmd_build(check=False, clear=False, target_dir=str(target))
        if result != 0:
            _fail("Graph build failed — check error above")
            return 1

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
Start Neo4j                   | smt start

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
        print(f"\n{_C.BOLD}SMT Health Check{_C.RESET}\n")
        exit_code = 0

        import urllib.request
        try:
            urllib.request.urlopen('http://localhost:7474', timeout=3)
            _ok("Neo4j reachable (http://localhost:7474)")
            neo4j_up = True
        except Exception:
            _fail("Neo4j not reachable — run: smt start")
            neo4j_up = False
            exit_code = 1

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
  view <symbol>          Show symbol source lines (graph lookup + targeted file read)
  context <symbol>       Symbol context (bidirectional, bounded)
  context <symbol> --callers  Who calls this symbol
  impact <symbol>        Impact analysis (reverse traversal)
  search <query>         Semantic search
  sync [range]           Sync graph with git commits (default: HEAD~1..HEAD)
  watch [--debounce N]   Auto-sync graph when files change (live mode)
  explain <symbol>       Print symbol context formatted for Claude to explain
  hooks install|uninstall Auto-sync hooks for git commits
  config                 Show or change SMT settings (memory, passwords)
  start                  Start Neo4j container
  stop                   Stop Neo4j container
  status                 Graph health check (includes container state)
  setup [--dir <path>]   Configure a project
  onboard project|agent|check Guided setup and orientation

graph analysis:
  list [--module X]      Enumerate all symbols (filter by file path)
  unused                 Symbols with no callers — dead code candidates
  cycles                 Circular dependencies in the call graph
  hot [--top N]          Most-called symbols (coupling hotspots)
  path <A> <B>           Shortest dependency path between two symbols
  modules                Files ranked by symbol count + coupling
  changes [RANGE]        Symbols in git-changed files with caller impact
  complexity [--top N]   fan-in × fan-out — god function detection
  scope <file>           File surface: exports, imports, internal symbols
  bottleneck [--top N]   Cross-file bridge nodes — architectural chokepoints
  layer [--config PATH]  Architecture layer violation detection
  breaking-changes <sym> Detect breaking contract changes between two git refs
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
    p_ctx.add_argument('--depth', type=int, default=None)
    p_ctx.add_argument('--callers', action='store_true')
    p_ctx.add_argument('--file', default=None)
    p_ctx.add_argument('--compress', action='store_true')
    p_ctx.add_argument('--compact', action='store_true')
    p_ctx.add_argument('--brief', action='store_true')
    p_ctx.add_argument('--json', action='store_true')

    # definition
    p_def = sub.add_parser('definition', help='Symbol definition (fast, 1-hop)')
    p_def.add_argument('symbol')
    p_def.add_argument('--file', default=None)
    p_def.add_argument('--compact', action='store_true')
    p_def.add_argument('--brief', action='store_true')
    p_def.add_argument('--json', action='store_true')

    # view
    p_view = sub.add_parser('view', help='Show symbol source lines (graph lookup + targeted file read)')
    p_view.add_argument('symbol')
    p_view.add_argument('--file', default=None)
    p_view.add_argument('--context', type=int, default=0, dest='context_lines',
                        help='Extra lines before/after the symbol body (default: 0)')

    # impact
    p_impact = sub.add_parser('impact', help='Impact analysis: what breaks if I change this?')
    p_impact.add_argument('symbol')
    p_impact.add_argument('--depth', type=int, default=None)
    p_impact.add_argument('--compress', action='store_true')
    p_impact.add_argument('--compact', action='store_true')
    p_impact.add_argument('--brief', action='store_true')
    p_impact.add_argument('--json', action='store_true')

    # search
    p_search = sub.add_parser('search', help='Semantic search')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)
    p_search.add_argument('--json', action='store_true')
    follow_grp = p_search.add_mutually_exclusive_group()
    follow_grp.add_argument('--context', action='store_true')
    follow_grp.add_argument('--impact', action='store_true')

    # sync
    p_sync = sub.add_parser('sync', help='Sync graph with git commits (incremental update)')
    p_sync.add_argument('range', nargs='?', default='HEAD~1..HEAD')
    p_sync.add_argument('--dir', default=None)

    # watch
    p_watch = sub.add_parser('watch', help='Watch files and auto-sync graph on change')
    p_watch.add_argument('--dir', default=None)
    p_watch.add_argument('--debounce', type=float, default=2.0)

    # explain
    p_explain = sub.add_parser('explain', help='Explain a symbol in plain English using Claude')
    p_explain.add_argument('symbol')
    p_explain.add_argument('--depth', type=int, default=2)

    # config
    p_config = sub.add_parser('config', help='Show or change SMT settings (memory, passwords)')
    p_config.add_argument('action', nargs='?', choices=['set', 'reset'], default=None)
    p_config.add_argument('key', nargs='?', default=None)
    p_config.add_argument('value', nargs='?', default=None)

    # start / stop
    sub.add_parser('start', help='Start Neo4j container')
    sub.add_parser('stop', help='Stop Neo4j container')

    # status
    sub.add_parser('status', help='Graph health check (includes container state)')

    # setup
    p_setup = sub.add_parser('setup', help='Configure a project')
    p_setup.add_argument('--dir', default='.', help='Target project directory')

    # hooks
    p_hooks = sub.add_parser('hooks', help='Manage git hooks')
    p_hooks.add_argument('action', choices=['install', 'uninstall'])
    p_hooks.add_argument('--dir', default=None)

    # onboard
    p_onboard = sub.add_parser('onboard', help='Guided setup and orientation')
    p_onboard.add_argument('action', choices=['project', 'agent', 'check'])
    p_onboard.add_argument('--dir', default=None)

    # list
    p_list = sub.add_parser('list', help='Enumerate all symbols (optionally filter by module/type)')
    p_list.add_argument('--module', default=None)
    p_list.add_argument('--type', dest='type_filter', default=None)
    p_list.add_argument('--limit', type=int, default=0)

    # unused
    p_unused = sub.add_parser('unused', help='Symbols with no callers — dead code candidates')
    p_unused.add_argument('--include-dunders', action='store_true')

    # cycles
    sub.add_parser('cycles', help='Circular dependencies in the call graph')

    # hot
    p_hot = sub.add_parser('hot', help='Most-called symbols — coupling hotspots')
    p_hot.add_argument('--top', type=int, default=20)

    # path
    p_path = sub.add_parser('path', help='Shortest dependency path between two symbols')
    p_path.add_argument('symbol_a')
    p_path.add_argument('symbol_b')

    # modules
    sub.add_parser('modules', help='Files ranked by symbol count and cross-file coupling')

    # changes
    p_changes = sub.add_parser('changes', help='Symbols in git-changed files with caller impact')
    p_changes.add_argument('range', nargs='?', default='HEAD~1..HEAD')

    # complexity
    p_complexity = sub.add_parser('complexity', help='fan-in × fan-out — god function detection')
    p_complexity.add_argument('--top', type=int, default=20)

    # scope
    p_scope = sub.add_parser('scope', help='File surface: exports, imports, internal symbols')
    p_scope.add_argument('file')

    # bottleneck
    p_bottleneck = sub.add_parser('bottleneck', help='Cross-file bridge nodes — architectural chokepoints')
    p_bottleneck.add_argument('--top', type=int, default=10)

    # layer
    p_layer = sub.add_parser('layer', help='Architecture layer violation detection')
    p_layer.add_argument('--config', default=None)

    # breaking-changes
    p_bc = sub.add_parser('breaking-changes', help='Detect breaking contract changes for a function between two git refs')
    p_bc.add_argument('symbol')
    p_bc.add_argument('--before', default='HEAD~1', dest='before_ref')
    p_bc.add_argument('--after', default='HEAD', dest='after_ref')

    args = parser.parse_args()

    # In agent mode: default compact + brief on every query (saves 40-60% tokens).
    # Explicit --no-compact / --no-brief flags are not wired, so this is unconditional.
    if os.environ.get("SMT_AGENT"):
        for _flag in ("compact", "brief"):
            if hasattr(args, _flag) and not getattr(args, _flag):
                setattr(args, _flag, True)

    if args.command == 'build':
        return cmd_build(check=args.check, clear=args.clear, target_dir=args.dir)
    elif args.command == 'context':
        depth = args.depth if args.depth is not None else _get_default_depth(2)
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.context(args.symbol, depth=depth, compress=args.compress)
            print(json.dumps(result.model_dump(), indent=2))
            return 0 if result.found else 1
        return cmd_context(args.symbol, depth=depth, callers=args.callers,
                          file_filter=args.file, compress=args.compress,
                          compact=getattr(args, 'compact', False), brief=getattr(args, 'brief', False))
    elif args.command == 'definition':
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.definition(args.symbol)
            print(json.dumps(result.model_dump(), indent=2))
            return 0 if result.found else 1
        return cmd_definition(args.symbol, file_filter=args.file,
                              compact=getattr(args, 'compact', False), brief=getattr(args, 'brief', False))
    elif args.command == 'view':
        return cmd_view(args.symbol, file_filter=args.file,
                        context_lines=getattr(args, 'context_lines', 0))
    elif args.command == 'impact':
        depth = args.depth if args.depth is not None else _get_default_depth(3)
        if getattr(args, 'json', False):
            engine = _get_engine()
            result = engine.impact(args.symbol, depth=depth)
            print(json.dumps(result.model_dump(), indent=2))
            return 0 if result.found else 1
        return cmd_impact(args.symbol, max_depth=depth, compress=args.compress,
                         compact=getattr(args, 'compact', False), brief=getattr(args, 'brief', False))
    elif args.command == 'search':
        if getattr(args, 'json', False):
            engine = _get_engine()
            results = engine.search(args.query, top_k=args.top)
            print(json.dumps(results.model_dump(), indent=2))
            return 0
        follow = 'context' if getattr(args, 'context', False) else ('impact' if getattr(args, 'impact', False) else None)
        return cmd_search(args.query, top_k=args.top, follow=follow)
    elif args.command == 'sync':
        return cmd_sync(commit_range=args.range, target_dir=args.dir)
    elif args.command == 'watch':
        return cmd_watch(target_dir=args.dir, debounce=args.debounce)
    elif args.command == 'explain':
        return cmd_explain(args.symbol, depth=args.depth)
    elif args.command == 'config':
        return cmd_config(args.action, getattr(args, 'key', None), getattr(args, 'value', None))
    elif args.command == 'start':
        return cmd_docker('up')
    elif args.command == 'stop':
        return cmd_docker('down')
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
    elif args.command == 'breaking-changes':
        return cmd_breaking_changes(
            symbol=args.symbol,
            before_ref=args.before_ref,
            after_ref=args.after_ref,
        )
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
