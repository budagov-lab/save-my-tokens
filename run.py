#!/usr/bin/env python3
"""
save-my-tokens (SMT) - Main entry point.

Usage:
    python run.py                    # Start MCP server (auto-starts docker + graph)
    python run.py smt                # Alias for MCP server
    python run.py graph              # Build/check graph
    python run.py graph --clear      # Clear and rebuild graph
    python run.py graph --check      # Check graph status
    python run.py docker             # Manage Docker (up/down/status)
    python run.py docker up          # Start Neo4j container
    python run.py docker down        # Stop Neo4j container
    python run.py docker status      # Check Neo4j status
"""

import sys
import json
import argparse
import subprocess
import time
import urllib.request
from pathlib import Path

from loguru import logger

from src.projects import set_project_database, get_database_name
from src.graph.neo4j_client import Neo4jClient
from src.graph.graph_builder import GraphBuilder
from src.github_integration import GraphCollaborationManager

# Set up project isolation at startup
set_project_database()

# Initialize collaboration manager
collab = GraphCollaborationManager()


def is_neo4j_running() -> bool:
    """Check if Neo4j is running and accessible."""
    try:
        urllib.request.urlopen('http://localhost:7474', timeout=2)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def is_docker_installed() -> bool:
    """Check if docker-compose is installed."""
    try:
        subprocess.run(['docker-compose', '--version'], capture_output=True, timeout=2)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_docker() -> bool:
    """Start Neo4j container with docker-compose."""
    logger.info("Starting Neo4j container...")

    if not is_docker_installed():
        logger.error("Docker not installed. Install from https://www.docker.com")
        return False

    try:
        result = subprocess.run(
            ['docker-compose', 'up', '-d', 'neo4j'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Docker-compose failed: {result.stderr}")
            return False

        # Wait for Neo4j to be ready with exponential backoff
        logger.info("Waiting for Neo4j to be ready...")
        backoff = 0.5
        for attempt in range(30):
            if is_neo4j_running():
                logger.info("Neo4j is ready!")
                return True
            time.sleep(min(backoff, 5))
            backoff *= 1.5

        logger.error("Neo4j failed to start in time")
        return False

    except Exception as e:
        logger.error(f"Failed to start docker: {e}")
        return False


def stop_docker() -> bool:
    """Stop Neo4j container with docker-compose."""
    logger.info("Stopping Neo4j container...")
    try:
        result = subprocess.run(
            ['docker-compose', 'down'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("Neo4j stopped")
            return True
        else:
            logger.error(f"Failed to stop docker: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Failed to stop docker: {e}")
        return False


def docker_status() -> bool:
    """Check Neo4j container status."""
    if is_neo4j_running():
        logger.info("Neo4j is running and accessible")
        return True
    else:
        logger.warning("Neo4j is not running")
        return False


def init_graph(clear: bool = False) -> bool:
    """Initialize the graph."""
    try:
        client = Neo4jClient()

        if clear:
            logger.info("Clearing existing graph...")
            client.clear_database()

        logger.info("Building graph from source code...")
        builder = GraphBuilder(base_path="src")
        builder.build()

        # Add git history
        logger.info("Adding git commit history...")
        _add_commits(client)

        stats = client.get_stats()
        logger.info(f"Graph ready: {stats['node_count']} nodes, {stats['edge_count']} edges")

        client.close()
        return True

    except Exception as e:
        logger.error(f"Graph initialization failed: {e}")
        return False


def check_graph() -> bool:
    """Check graph status."""
    try:
        client = Neo4jClient()
        stats = client.get_stats()
        db_name = get_database_name()

        # Get collaboration info
        collab_info = collab.get_collaboration_info()

        print("\n" + "=" * 60)
        print("SAVE-MY-TOKENS GRAPH STATUS")
        print("=" * 60)
        print(f"\nDatabase: {db_name}")
        print(f"Branch: {collab_info['current_branch']}")

        # Show PR info if on PR branch
        if collab_info['pull_request']:
            pr = collab_info['pull_request']
            print(f"Pull Request: #{pr['number']} - {pr['title']}")
            print(f"Author: {pr['author']}")
        else:
            print(f"Open PRs: {collab_info['open_prs']}")

        print(f"\nNodes: {stats['node_count']}")
        print(f"Edges: {stats['edge_count']}")

        # Node breakdown
        with client.driver.session() as session:
            result = session.run("""
                MATCH (n)
                RETURN DISTINCT labels(n)[0] as type, COUNT(n) as count
                ORDER BY count DESC
            """)
            print("\nNode Types:")
            for record in result:
                print(f"  {record['type']}: {record['count']}")

        # Commits
        with client.driver.session() as session:
            result = session.run("MATCH (c:Commit) RETURN COUNT(c) as count")
            commit_count = result.single()['count']

        print(f"\nCommits: {commit_count}")

        if stats['node_count'] > 100:
            print("\nStatus: READY FOR MCP")
        else:
            print("\nStatus: EMPTY - Run 'python run.py graph' to build")

        print("=" * 60 + "\n")

        client.close()
        return stats['node_count'] > 0

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return False


def start_mcp() -> bool:
    """Start MCP server (auto-starts docker if needed)."""
    try:
        from src.mcp_server.entrypoint import main as mcp_main
        project_root = Path(__file__).parent

        # Ensure Neo4j is running
        logger.info("Checking Neo4j status...")
        if not is_neo4j_running():
            logger.info("Neo4j not running, starting container...")
            if not start_docker():
                logger.error("Failed to start Neo4j container")
                return False

        logger.info("Setting up Claude Code configuration...")
        ensure_claude_config(project_root)

        logger.info("Initializing graph for MCP...")

        # Ensure graph is ready
        client = Neo4jClient()
        stats = client.get_stats()
        client.close()

        if stats['node_count'] < 100:
            logger.info("Graph empty, building...")
            if not init_graph():
                logger.error("Failed to initialize graph")
                return False

        logger.info("Starting MCP server...")
        mcp_main()
        return True

    except Exception as e:
        logger.error(f"MCP server failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _add_commits(client: Neo4jClient) -> None:
    """Add commits to graph."""
    import subprocess

    result = subprocess.run(
        ['git', 'log', '--format=%H|%an|%ai|%s'],
        capture_output=True, text=True
    )

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 3)
        if len(parts) >= 4:
            commits.append({
                'hash': parts[0],
                'author': parts[1],
                'date': parts[2],
                'message': parts[3]
            })

    # Check if commits already exist
    with client.driver.session() as session:
        result = session.run("MATCH (c:Commit) RETURN COUNT(c) as count")
        existing = result.single()['count']

    if existing > 0:
        logger.debug(f"Commits already in graph ({existing})")
        return

    # Add commits
    with client.driver.session() as session:
        for i, commit in enumerate(commits):
            cypher = """
            CREATE (c:Commit {
                node_id: $node_id,
                hash: $hash,
                author: $author,
                date: $date,
                message: $message,
                index: $index
            })
            """
            session.run(
                cypher,
                node_id=f"commit:{commit['hash']}",
                hash=commit['hash'],
                author=commit['author'],
                date=commit['date'],
                message=commit['message'],
                index=i
            )

    logger.info(f"Added {len(commits)} commits")


def ensure_claude_config(project_root: Path) -> None:
    """Ensure Claude Code configuration files exist."""
    claude_dir = project_root / '.claude'
    claude_dir.mkdir(exist_ok=True)

    # Create .mcp.json if missing
    mcp_file = project_root / '.mcp.json'
    if not mcp_file.exists():
        logger.info("Creating .mcp.json...")
        mcp_config = {
            "mcpServers": {
                "smt": {
                    "command": "python",
                    "args": [str(project_root / "run.py")]
                }
            }
        }
        with open(mcp_file, 'w', encoding='utf-8') as f:
            json.dump(mcp_config, f, indent=2)

    # Create .claude/workspace.json if missing
    workspace_file = claude_dir / 'workspace.json'
    if not workspace_file.exists():
        logger.info("Creating .claude/workspace.json...")
        workspace_config = {
            "mcp_enabled": True,
            "graph_auto_sync": True,
            "graph_base_path": "src",
            "neo4j_uri": "bolt://localhost:7687"
        }
        with open(workspace_file, 'w', encoding='utf-8') as f:
            json.dump(workspace_config, f, indent=2)

    # Create .claude/settings.json if missing
    settings_file = claude_dir / 'settings.json'
    if not settings_file.exists():
        logger.info("Creating .claude/settings.json...")
        settings = {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "model": "haiku",
            "alwaysThinkingEnabled": False,
            "permissions": {
                "defaultMode": "auto",
                "allow": [
                    "Read",
                    "Edit(src/**)",
                    "Edit(tests/**)",
                    "Edit(.claude/**)",
                    "Write(src/**)",
                    "Write(tests/**)",
                    "Bash"
                ],
                "deny": [
                    "Bash(rm -rf:*)",
                    "Bash(git reset --hard:*)",
                    "Bash(git push --force:*)"
                ],
                "ask": [
                    "Write(README.md)",
                    "Write(CLAUDE.md)"
                ]
            },
            "env": {
                "PYTHONPATH": "src",
                "NEO4J_LOG_LEVEL": "info",
                "PYTEST_ADDOPTS": "-v --tb=short"
            },
            "respectGitignore": True,
            "cleanupPeriodDays": 30,
            "spinnerTipsEnabled": True
        }
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)

    # Create .claude/skills/mcp-guide/SKILL.md if missing
    skill_dir = claude_dir / 'skills' / 'mcp-guide'
    skill_file = skill_dir / 'SKILL.md'
    if not skill_file.exists():
        logger.info("Creating .claude/skills/mcp-guide/SKILL.md...")
        skill_dir.mkdir(parents=True, exist_ok=True)
        guide_content = """---
name: mcp-guide
description: Learn how to use 20 MCP tools efficiently instead of reading/grepping large files
---

# MCP Tools Guide

You have access to 20 MCP tools organized by category:

## Code Understanding (4 tools)
- `get_context(symbol)` - Understand a function/class + callers + dependencies
- `get_subgraph(symbol)` - Full dependency tree up to N hops
- `semantic_search(query)` - Find code by meaning (not just names)
- `validate_conflicts(tasks)` - Check if changes can run in parallel

## Graph Management (8+ tools)
- `graph_stats()` - Is graph fresh? Get node/edge counts
- `graph_rebuild()` - Full reconstruction from source
- `graph_diff_rebuild()` - Fast incremental update from git
- `graph_validate()` - Check graph integrity and consistency

## Contracts & Breaking Changes (2 tools)
- `extract_contract(code)` - Parse function signatures and types
- `compare_contracts(old, new)` - Detect breaking changes before refactoring

## Git & Updates (2 tools)
- `parse_diff()` - Analyze git diff output
- `apply_diff()` - Sync graph with git commits

## Task Scheduling (2 tools)
- `schedule_tasks(tasks)` - Build execution plan with parallelization
- `execute_tasks(plan)` - Run tasks respecting dependencies

## Usage Principle

Don't read large files - use tools instead:
- "What does function X do?" -> Use get_context('X')
- "Find code that does X" -> Use semantic_search('X')
- "Is my change safe?" -> Use compare_contracts(old, new) + validate_conflicts(tasks)
- "Update after git commit" -> Use graph_diff_rebuild()

Always use these tools instead of Read() or Grep() for code understanding.
"""
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(guide_content)


def main():
    parser = argparse.ArgumentParser(
        description="save-my-tokens (SMT) - Semantic code graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Start:
  python run.py                  # Start MCP server (auto-starts docker + builds graph)
  python run.py smt              # Same as above
  python run.py graph            # Build/check graph
  python run.py graph --check    # Check status
  python run.py graph --clear    # Clear and rebuild
  python run.py docker           # Check Neo4j status
  python run.py docker up        # Start Neo4j container
  python run.py docker down      # Stop Neo4j container

For Claude Desktop integration:
  1. Run: python run.py
     (automatically starts Neo4j, builds graph, starts MCP server)
  2. In Claude Desktop, configure .mcp.json to use stdio transport
  3. SMT MCP tools are now available
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # graph subcommand
    graph_parser = subparsers.add_parser('graph', help='Manage graph')
    graph_parser.add_argument('--check', action='store_true', help='Check status')
    graph_parser.add_argument('--clear', action='store_true', help='Clear and rebuild')

    # docker subcommand
    docker_parser = subparsers.add_parser('docker', help='Manage Neo4j Docker container')
    docker_parser.add_argument('action', nargs='?', choices=['up', 'down', 'status'], default='status',
                              help='Docker action (default: status)')

    args = parser.parse_args()

    # Handle commands
    if args.command == 'graph':
        if args.check:
            success = check_graph()
        else:
            success = init_graph(clear=args.clear)
    elif args.command == 'docker':
        if args.action == 'up':
            success = start_docker()
        elif args.action == 'down':
            success = stop_docker()
        else:
            success = docker_status()
    elif args.command == 'smt' or not args.command:
        # Default: start MCP (auto-starts docker)
        success = start_mcp()
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
