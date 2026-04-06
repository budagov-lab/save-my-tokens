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
import stat
from pathlib import Path

from loguru import logger

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SMT_DIR = Path(__file__).parent.parent.resolve()


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
        with client.driver.session() as session:
            counts = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            ).data()
            edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()['cnt']
        client.driver.close()

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

    # Find src directory
    src_dir = target_path / 'src'
    if not src_dir.exists():
        print(f"ERROR: No 'src/' directory found in {target_path}")
        print(f"\nOptions:")
        print(f"  1. Run from a project with src/:  cd /path/to/project && smt build")
        print(f"  2. Specify the directory:         smt build --dir /path/to/project")
        print(f"  3. Set up the project:            smt setup --dir /path/to/project")
        return 1

    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        from loguru import logger
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

        # Clear if requested
        if clear:
            logger.info(f"Clearing graph database...")
            with client.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            logger.info("Database cleared.")

        builder = GraphBuilder(str(src_dir), neo4j_client=client)
        builder.build()
        client.driver.close()
        print("Done.")
        return cmd_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def cmd_context(symbol: str, depth: int = 1, callers: bool = False, file_filter: str | None = None) -> int:
    settings, Neo4jClient, *_ = _get_services()

    try:
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        with client.driver.session() as session:
            # Find the symbol, prioritizing by type (Function > Class > other)
            # and optionally filtering by file
            if file_filter:
                query = """
                    MATCH (n {name: $name})
                    WHERE n.file CONTAINS $file
                    RETURN n
                    LIMIT 1
                """
                node = session.run(query, name=symbol, file=file_filter).single()
            else:
                query = """
                    MATCH (n {name: $name})
                    RETURN n,
                           CASE WHEN n:Function THEN 0
                                WHEN n:Class THEN 1
                                ELSE 2 END as priority
                    ORDER BY priority
                    LIMIT 1
                """
                node = session.run(query, name=symbol).single()

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

        client.driver.close()
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
        with client.driver.session() as session:
            rows = session.run(
                "MATCH (n) RETURN n, labels(n) as labels"
            ).data()
        client.driver.close()

        from src.parsers.symbol import Symbol
        for row in rows:
            n = row['n']
            labels = row['labels']
            if not n.get('name'):
                continue
            sym = Symbol(
                name=n.get('name', ''),
                type=labels[0] if labels else 'Unknown',
                file=n.get('file', ''),
                line=n.get('line', 0),
                column=n.get('column', 0),
                docstring=n.get('docstring'),
            )
            symbol_index.add(sym)

        svc = EmbeddingService(symbol_index, cache_dir=SMT_DIR / '.smt' / 'embeddings')
        svc.build_index()  # Build FAISS index from symbols
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
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def cmd_diff(commit_range: str = 'HEAD~1..HEAD', target_dir: Optional[str] = None) -> int:
    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    try:
        # Determine target directory (same logic as cmd_build)
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

        # Check if it looks like a git repository
        if not (target_path / '.git').exists():
            print(f"ERROR: No .git directory found in {target_path}")
            return 1

        from loguru import logger

        # Create Neo4j client
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

        # Create symbol index
        index = SymbolIndex()

        # Create embedding service
        cache_dir = target_path / '.claude' / '.embeddings'
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
            return 0
        else:
            print("✗ Graph sync failed")
            return 1

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
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
    }
    with open(smt_config_file, 'w', encoding='utf-8') as f:
        json.dump(smt_config, f, indent=2)
    print("  .claude/.smt_config    [OK]")

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
    existing['permissions']['allow'] = ['Read', 'Edit(**)', 'Write(**)', 'Bash']
    existing['permissions'].setdefault('deny', [
        'Bash(rm -rf:*)',
        'Bash(git reset --hard:*)',
        'Bash(git push --force:*)',
    ])
    existing.setdefault('env', {})
    existing['env']['SMT_DIR'] = str(SMT_DIR)
    existing['env']['SMT_PROJECT'] = target_dir.name
    existing['respectGitignore'] = True

    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2)
    print("  .claude/settings.json  [OK]")

    # ------------------------------------------------------------------
    # 2. .claude/TOOLS.md  — smt quick reference for Claude
    # ------------------------------------------------------------------
    tools_md = claude_dir / 'TOOLS.md'
    tools_content = """\
# SMT CLI — Quick Reference

Use `smt` commands via Bash instead of reading/grepping source files.

---

## Decision Table

| You want to...                          | Run this                              |
|-----------------------------------------|---------------------------------------|
| Understand what a function does         | `smt context <symbol>`                |
| See what a function depends on          | `smt context <symbol> --depth 2`      |
| See who calls a function                | `smt callers <symbol>`                |
| Find code by meaning / topic            | `smt search "description"`            |
| Check graph health                      | `smt status`                          |
| Build graph from source                 | `smt build`                           |
| Wipe and rebuild                        | `smt build --clear`                   |
| Sync graph after a commit               | `smt diff HEAD~1..HEAD`               |
| Start Neo4j                             | `smt docker up`                       |

---

## Session Start Checklist

```bash
smt status          # node count > 100? Graph is ready.
smt build           # if empty — build from src/
smt diff            # if stale — sync with recent commits
```

## Hard Restart (graph broken / corrupted)

```bash
smt build --clear   # wipes all nodes/edges and rebuilds from source
smt status          # confirm node count > 100
```
"""
    with open(tools_md, 'w', encoding='utf-8') as f:
        f.write(tools_content)
    print("  .claude/TOOLS.md       [OK]")

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
smt search "what you're looking for"  # semantic search
smt callers <SymbolName>        # who calls this
smt status                      # check graph health
```

### Session start

```bash
smt status      # is the graph ready? (node count > 0)
smt build       # build if empty
smt diff        # sync if stale after recent commits
```

### When to read files directly

Only read a file when:
- `smt context` doesn't return enough detail (e.g. need to see the full function body)
- You are writing new code and need the exact surrounding lines

### Project: {project_name}

SMT is installed at: `{SMT_DIR}`
Neo4j browser: http://localhost:7474
"""
        with open(claude_md, 'w', encoding='utf-8') as f:
            f.write(claude_md_content)
        print("  CLAUDE.md              [OK]")
    else:
        print("  CLAUDE.md              [skipped — already exists]")

    print(f"\nDone! To build your graph:")
    print(f"  smt docker up          # start Neo4j (first time only)")
    print(f"  smt build              # index your codebase from {target_dir}/src/")
    print(f"  smt status             # verify graph is ready")
    print(f"\nNote: You can run 'smt build' from any directory—it will use the")
    print(f"      project directory you configured here ({target_dir})")

    # ------------------------------------------------------------------
    # Install post-commit hook (for automatic graph sync)
    # ------------------------------------------------------------------
    try:
        cmd_setup_hooks(target_dir)
    except Exception as e:
        print(f"Warning: Failed to setup git hook: {e}")

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
smt diff HEAD~1..HEAD >/dev/null 2>&1 &
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
  diff [range]           Sync graph with git commits
  sync [range]           Alias for diff (incremental update)
  hooks install|uninstall Auto-sync hooks for git commits
  docker up|down|status  Manage Neo4j container
  status                 Graph health check
  setup [--dir <path>]   Configure a project
        """
    )

    sub = parser.add_subparsers(dest='command')

    # build
    p_build = sub.add_parser('build', help='Build graph')
    p_build.add_argument('--dir', default=None, help='Target project directory (default: cwd)')
    p_build.add_argument('--check', action='store_true', help='Show stats only')
    p_build.add_argument('--clear', action='store_true', help='Wipe and rebuild')

    # context
    p_ctx = sub.add_parser('context', help='Symbol context')
    p_ctx.add_argument('symbol')
    p_ctx.add_argument('--depth', type=int, default=1)
    p_ctx.add_argument('--callers', action='store_true')
    p_ctx.add_argument('--file', default=None, help='Filter by file path (substring match)')

    # search
    p_search = sub.add_parser('search', help='Semantic search')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)

    # callers
    p_callers = sub.add_parser('callers', help='Who calls a symbol')
    p_callers.add_argument('symbol')

    # diff / sync
    p_diff = sub.add_parser('diff', help='Sync graph after commits')
    p_diff.add_argument('range', nargs='?', default='HEAD~1..HEAD')
    p_diff.add_argument('--dir', default=None, help='Target project directory (default: cwd)')

    # sync (alias for diff)
    p_sync = sub.add_parser('sync', help='Sync graph with git commits (alias for diff)')
    p_sync.add_argument('range', nargs='?', default='HEAD~1..HEAD')
    p_sync.add_argument('--dir', default=None, help='Target project directory (default: cwd)')

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

    args = parser.parse_args()

    if args.command == 'build':
        return cmd_build(check=args.check, clear=args.clear, target_dir=args.dir)
    elif args.command == 'context':
        return cmd_context(args.symbol, depth=args.depth, callers=args.callers, file_filter=args.file)
    elif args.command == 'search':
        return cmd_search(args.query, top_k=args.top)
    elif args.command == 'callers':
        return cmd_callers(args.symbol)
    elif args.command in ('diff', 'sync'):
        return cmd_diff(commit_range=args.range, target_dir=args.dir)
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
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
