#!/usr/bin/env python3
"""
save-my-tokens (SMT) - Main entry point.

Usage:
    python run.py                    # Start MCP server
    python run.py smt                # Alias for MCP server
    python run.py graph              # Build/check graph
    python run.py graph --clear      # Clear and rebuild graph
    python run.py graph --check      # Check graph status
"""

import sys
import json
import argparse
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
    """Start MCP server."""
    try:
        from src.mcp_server.entrypoint import main as mcp_main
        project_root = Path(__file__).parent

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
        with open(mcp_file, 'w') as f:
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
        with open(workspace_file, 'w') as f:
            json.dump(workspace_config, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="save-my-tokens (SMT) - Semantic code graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Start:
  python run.py                  # Start MCP server (auto-builds graph & config)
  python run.py smt              # Same as above
  python run.py graph            # Build/check graph
  python run.py graph --check    # Check status
  python run.py graph --clear    # Clear and rebuild

For Claude Desktop integration:
  1. Ensure Docker Neo4j is running: docker-compose up -d neo4j
  2. Start SMT: python run.py
  3. In Claude Desktop, configure .mcp.json to use stdio transport
  4. SMT MCP tools are now available
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # graph subcommand
    graph_parser = subparsers.add_parser('graph', help='Manage graph')
    graph_parser.add_argument('--check', action='store_true', help='Check status')
    graph_parser.add_argument('--clear', action='store_true', help='Clear and rebuild')

    args = parser.parse_args()

    # Handle commands
    if args.command == 'graph':
        if args.check:
            success = check_graph()
        else:
            success = init_graph(clear=args.clear)
    elif args.command == 'smt' or not args.command:
        # Default: start MCP
        success = start_mcp()
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
