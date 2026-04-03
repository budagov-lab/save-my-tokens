#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smt — CLI for save-my-tokens.

Usage:
    smt build                      # Build graph from src/
    smt build --check              # Show graph stats
    smt build --clear              # Wipe and rebuild

    smt context <symbol>           # Symbol definition + deps + callers
    smt search <query>             # Semantic search
    smt callers <symbol>           # Who calls this symbol
    smt diff [range]               # Sync graph after commits (default: HEAD~1..HEAD)

    smt docker up                  # Start Neo4j container
    smt docker down                # Stop Neo4j container
    smt docker status              # Check Neo4j container

    smt status                     # Graph health check
    smt setup [--dir <path>]       # Configure a project (.claude/settings.json)
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SMT_DIR = Path(__file__).parent.resolve()


def _get_services():
    """Lazy-import heavy services so CLI starts fast for docker/status commands."""
    sys.path.insert(0, str(SMT_DIR))
    from src.config import settings
    from src.graph.neo4j_client import Neo4jClient
    from src.graph.graph_builder import GraphBuilder
    from src.parsers.symbol_index import SymbolIndex
    from src.embeddings.embedding_service import EmbeddingService
    from src.incremental.updater import GraphUpdater
    return settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, GraphUpdater


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------

def cmd_docker(action: str) -> int:
    compose_file = SMT_DIR / 'docker-compose.yml'
    if not compose_file.exists():
        print("ERROR: docker-compose.yml not found")
        return 1

    if action == 'up':
        result = subprocess.run(
            ['docker-compose', '-f', str(compose_file), 'up', '-d', 'neo4j'],
            cwd=SMT_DIR
        )
    elif action == 'down':
        result = subprocess.run(
            ['docker-compose', '-f', str(compose_file), 'down'],
            cwd=SMT_DIR
        )
    elif action == 'status':
        result = subprocess.run(
            ['docker-compose', '-f', str(compose_file), 'ps'],
            cwd=SMT_DIR
        )
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
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        with client.session() as session:
            counts = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            ).data()
            edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()['cnt']
        client.close()

        total = sum(r['cnt'] for r in counts)
        print(f"Graph:  {total} nodes, {edge_count} edges")
        for row in sorted(counts, key=lambda r: -r['cnt']):
            print(f"        {row['label']}: {row['cnt']}")

        if total == 0:
            print("\nGraph is empty. Build it with:  smt build")
            return 1
    except Exception as e:
        print(f"Graph:  ERROR — {e}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(check: bool = False, clear: bool = False) -> int:
    settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, _ = _get_services()

    if check:
        return cmd_status()

    src_dir = SMT_DIR / 'src'
    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        builder = GraphBuilder(
            neo4j_uri=settings.NEO4J_URI,
            neo4j_user=settings.NEO4J_USER,
            neo4j_password=settings.NEO4J_PASSWORD,
        )
        builder.build(str(src_dir), clear_first=clear)
        print("Done.")
        return cmd_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def cmd_context(symbol: str, depth: int = 1, callers: bool = False) -> int:
    settings, Neo4jClient, *_ = _get_services()

    try:
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        with client.session() as session:
            # Find the symbol
            node = session.run(
                "MATCH (n {name: $name}) RETURN n LIMIT 1", name=symbol
            ).single()

            if not node:
                print(f"Symbol '{symbol}' not found in graph.")
                client.close()
                return 1

            n = node['n']
            print(f"\n{n.get('name')}  [{', '.join(n.labels)}]")
            print(f"  file: {n.get('file', '?')}:{n.get('line', '?')}")
            if n.get('signature'):
                print(f"  sig:  {n.get('signature')}")
            if n.get('docstring'):
                print(f"  doc:  {n.get('docstring')[:120]}")

            # Dependencies (what this calls)
            deps = session.run(
                "MATCH (n {name: $name})-[:CALLS]->(dep) RETURN dep.name AS name, dep.file AS file",
                name=symbol
            ).data()
            if deps:
                print(f"\n  calls ({len(deps)}):")
                for d in deps:
                    print(f"    {d['name']}  ({d.get('file', '?')})")

            # Callers
            if callers or depth > 1:
                callers_data = session.run(
                    "MATCH (caller)-[:CALLS]->(n {name: $name}) RETURN caller.name AS name, caller.file AS file",
                    name=symbol
                ).data()
                if callers_data:
                    print(f"\n  callers ({len(callers_data)}):")
                    for c in callers_data:
                        print(f"    {c['name']}  ({c.get('file', '?')})")

        client.close()
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# callers
# ---------------------------------------------------------------------------

def cmd_callers(symbol: str) -> int:
    return cmd_context(symbol, callers=True)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def cmd_search(query: str, top_k: int = 5) -> int:
    settings, _, _, SymbolIndex, EmbeddingService, _ = _get_services()

    try:
        symbol_index = SymbolIndex()
        # Load symbols from Neo4j into the index
        from src.graph.neo4j_client import Neo4jClient
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        with client.session() as session:
            rows = session.run(
                "MATCH (n) WHERE n.name IS NOT NULL RETURN n"
            ).data()
        client.close()

        from src.parsers.symbol import Symbol
        for row in rows:
            n = row['n']
            sym = Symbol(
                name=n.get('name', ''),
                type=next(iter(n.labels), 'Unknown'),
                file=n.get('file', ''),
                line=n.get('line', 0),
                signature=n.get('signature', ''),
                docstring=n.get('docstring', ''),
            )
            symbol_index.add(sym)

        svc = EmbeddingService(symbol_index, cache_dir=SMT_DIR / '.smt' / 'embeddings')
        results = svc.search(query, top_k=top_k)

        if not results:
            print(f"No results for '{query}'")
            return 0

        print(f"\nSearch: {query!r}  (top {len(results)})\n")
        for sym, score in results:
            print(f"  {sym.name}  [{sym.type}]  score={score:.3f}")
            print(f"    {sym.file}:{sym.line}")
            if sym.docstring:
                print(f"    {sym.docstring[:80]}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def cmd_diff(commit_range: str = 'HEAD~1..HEAD') -> int:
    settings, _, _, _, _, GraphUpdater = _get_services()

    try:
        updater = GraphUpdater(
            neo4j_uri=settings.NEO4J_URI,
            neo4j_user=settings.NEO4J_USER,
            neo4j_password=settings.NEO4J_PASSWORD,
        )
        result = updater.update_from_git(commit_range, repo_path=str(SMT_DIR))
        print(f"Synced: {result}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup(target_dir: Path) -> int:
    target_dir = target_dir.resolve()
    claude_dir = target_dir / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    print(f"Configuring SMT for: {target_dir}")

    # .claude/settings.json — permissions + env, no MCP hooks
    settings_file = claude_dir / 'settings.json'
    existing = {}
    if settings_file.exists():
        with open(settings_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing.setdefault('permissions', {
        'defaultMode': 'auto',
        'allow': ['Read', 'Edit(**)', 'Write(**)', 'Bash'],
        'deny': ['Bash(rm -rf:*)', 'Bash(git reset --hard:*)', 'Bash(git push --force:*)'],
    })
    existing.setdefault('env', {})
    existing['env']['SMT_DIR'] = str(SMT_DIR)
    existing['env']['SMT_PROJECT'] = target_dir.name
    existing['respectGitignore'] = True

    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2)
    print("  .claude/settings.json  [OK]")

    # Copy TOOLS.md
    src_tools = SMT_DIR / '.claude' / 'TOOLS.md'
    if src_tools.exists():
        import shutil
        shutil.copy2(src_tools, claude_dir / 'TOOLS.md')
        print("  .claude/TOOLS.md       [OK]")

    print(f"\nDone. Use 'smt' commands from any terminal in {target_dir}")
    print("  smt status             # check graph health")
    print("  smt build              # build graph from src/")
    print("  smt search <query>     # semantic search")
    return 0


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
  context <symbol>       Symbol definition, deps, callers
  search <query>         Semantic search
  callers <symbol>       Who calls this symbol
  diff [range]           Sync graph after commits
  docker up|down|status  Manage Neo4j container
  status                 Graph health check
  setup [--dir <path>]   Configure a project
        """
    )

    sub = parser.add_subparsers(dest='command')

    # build
    p_build = sub.add_parser('build', help='Build graph')
    p_build.add_argument('--check', action='store_true', help='Show stats only')
    p_build.add_argument('--clear', action='store_true', help='Wipe and rebuild')

    # context
    p_ctx = sub.add_parser('context', help='Symbol context')
    p_ctx.add_argument('symbol')
    p_ctx.add_argument('--depth', type=int, default=1)
    p_ctx.add_argument('--callers', action='store_true')

    # search
    p_search = sub.add_parser('search', help='Semantic search')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)

    # callers
    p_callers = sub.add_parser('callers', help='Who calls a symbol')
    p_callers.add_argument('symbol')

    # diff
    p_diff = sub.add_parser('diff', help='Sync graph after commits')
    p_diff.add_argument('range', nargs='?', default='HEAD~1..HEAD')

    # docker
    p_docker = sub.add_parser('docker', help='Manage Neo4j container')
    p_docker.add_argument('action', choices=['up', 'down', 'status'])

    # status
    sub.add_parser('status', help='Graph health check')

    # setup
    p_setup = sub.add_parser('setup', help='Configure a project')
    p_setup.add_argument('--dir', default='.', help='Target project directory')

    args = parser.parse_args()

    if args.command == 'build':
        return cmd_build(check=args.check, clear=args.clear)
    elif args.command == 'context':
        return cmd_context(args.symbol, depth=args.depth, callers=args.callers)
    elif args.command == 'search':
        return cmd_search(args.query, top_k=args.top)
    elif args.command == 'callers':
        return cmd_callers(args.symbol)
    elif args.command == 'diff':
        return cmd_diff(args.range)
    elif args.command == 'docker':
        return cmd_docker(args.action)
    elif args.command == 'status':
        return cmd_status()
    elif args.command == 'setup':
        return cmd_setup(Path(args.dir))
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
