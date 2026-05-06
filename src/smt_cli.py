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
    _fail,
    _get_default_depth,
    _get_default_compact,
    _get_default_brief,
    _get_engine,
    _get_embedding_service,
    _get_neo4j_client,
    _get_project_id,
    _get_services,
    _get_validation,
    _git_initial_commit,
    _ok,
    _require_git,
    _resolve_project_path,
    _warn,
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

from src.cli.docker import cmd_docker
from src.cli.config import cmd_config
from src.cli.status import cmd_status

from src.cli.build import cmd_build

from src.cli.query import cmd_context, cmd_definition, cmd_view, cmd_impact, cmd_grep

from src.cli.search import cmd_search, cmd_explain, cmd_lookup
from src.cli.sync import cmd_sync
from src.cli.onboard import cmd_onboard


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
  lookup <query>         Unified resolver: exact → dot-notation → partial-name (use when unsure of name)
  definition <symbol>    Symbol definition (fast, 1-hop)
  view <symbol>          Show symbol source lines (graph lookup + targeted file read)
  context <symbol>       Symbol context (bidirectional, bounded)
  context <symbol> --callers  Who calls this symbol
  impact <symbol>        Impact analysis (reverse traversal)
  search <query>         Semantic search (requires smt build --embeddings)
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
    p_build.add_argument('--embeddings', action='store_true', help='Also build semantic search index (slow, opt-in)')

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
    p_view.add_argument('--compact', action='store_true', help=argparse.SUPPRESS)
    p_view.add_argument('--brief', action='store_true', help=argparse.SUPPRESS)

    # impact
    p_impact = sub.add_parser('impact', help='Impact analysis: what breaks if I change this?')
    p_impact.add_argument('symbol')
    p_impact.add_argument('--depth', type=int, default=None)
    p_impact.add_argument('--compress', action='store_true')
    p_impact.add_argument('--compact', action='store_true')
    p_impact.add_argument('--brief', action='store_true')
    p_impact.add_argument('--json', action='store_true')

    # search (semantic, opt-in via smt build --embeddings)
    p_search = sub.add_parser('search', help='Semantic search (requires smt build --embeddings)')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)
    p_search.add_argument('--json', action='store_true')
    follow_grp = p_search.add_mutually_exclusive_group()
    follow_grp.add_argument('--context', action='store_true')
    follow_grp.add_argument('--impact', action='store_true')

    # lookup (unified resolver: exact → dot-notation → partial-name)
    p_lookup = sub.add_parser('lookup', help='Unified resolver: exact → dot-notation → partial-name match')
    p_lookup.add_argument('query', help='Symbol name, Class.method, or partial name fragment')
    p_lookup.add_argument('--compact', action='store_true')
    p_lookup.add_argument('--brief', action='store_true')

    # grep (fast text search on AST index — no embeddings needed)
    p_grep = sub.add_parser('grep', help='Text search across symbol names, signatures, and docstrings')
    p_grep.add_argument('pattern', help='Substring to search for (case-insensitive)')
    p_grep.add_argument('--field', choices=['name', 'doc'], default=None,
                        help='Restrict to a specific field (default: name + doc)')
    p_grep.add_argument('--type', dest='type_filter', default=None,
                        help='Filter by node type: Function, Class, etc.')
    p_grep.add_argument('--top', type=int, default=20)
    p_grep.add_argument('--module', default=None,
                        help='Filter by file path fragment (e.g. --module adapters)')

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
    p_scope.add_argument('--dir', default=None, dest='dir_filter',
                         help='Path fragment to disambiguate when multiple files match (e.g. requests/)')

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

    # Apply global preferences for compact/brief (CLI flag wins — only set if not already true).
    if not os.environ.get("SMT_AGENT"):
        if hasattr(args, 'compact') and not args.compact:
            args.compact = _get_default_compact()
        if hasattr(args, 'brief') and not args.brief:
            args.brief = _get_default_brief()

    # In agent mode: force compact + brief unconditionally (saves 40-60% tokens).
    if os.environ.get("SMT_AGENT"):
        for _flag in ("compact", "brief"):
            if hasattr(args, _flag) and not getattr(args, _flag):
                setattr(args, _flag, True)

    if args.command == 'build':
        return cmd_build(check=args.check, clear=args.clear, target_dir=args.dir,
                         embeddings=getattr(args, 'embeddings', False))
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
                        context_lines=getattr(args, 'context_lines', 0),
                        compact=getattr(args, 'compact', False),
                        brief=getattr(args, 'brief', False))
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
    elif args.command == 'lookup':
        return cmd_lookup(args.query,
                          compact=getattr(args, 'compact', False),
                          brief=getattr(args, 'brief', False))
    elif args.command == 'grep':
        return cmd_grep(args.pattern, field=args.field,
                        type_filter=args.type_filter, top=args.top,
                        module=getattr(args, 'module', None))
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
        return cmd_scope(args.file, dir_filter=getattr(args, 'dir_filter', None))
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
