#!/usr/bin/env python3
"""
Simple one-command graph builder for save-my-tokens.
Rebuilds the entire Neo4j graph from source and git history.

Usage:
    python build_graph.py              # Rebuild from source
    python build_graph.py --clear      # Clear and rebuild
    python build_graph.py --check      # Check graph status
"""

import sys
import argparse
from pathlib import Path

from loguru import logger

from src.graph.graph_builder import GraphBuilder
from src.graph.neo4j_client import Neo4jClient


def build_fresh(clear: bool = False) -> bool:
    """Build fresh graph from source code and git history."""
    try:
        client = Neo4jClient()

        if clear:
            logger.info("Clearing existing graph...")
            client.clear_database()

        logger.info("Building graph from source code...")
        builder = GraphBuilder(base_path="src")
        builder.build()

        # Add commit nodes from git history
        logger.info("Adding git commit history...")
        _add_commits_to_graph(client)

        # Check results
        stats = client.get_stats()
        logger.info(f"Graph built successfully: {stats['node_count']} nodes, {stats['edge_count']} edges")

        client.close()
        return True

    except Exception as e:
        logger.error(f"Failed to build graph: {e}")
        return False


def _add_commits_to_graph(client: Neo4jClient) -> None:
    """Add commit nodes to Neo4j from git history."""
    import subprocess

    result = subprocess.run(
        ['git', 'log', '--format=%H|%an|%ai|%s'],
        capture_output=True, text=True
    )

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|')
        if len(parts) >= 4:
            commits.append({
                'hash': parts[0],
                'author': parts[1],
                'date': parts[2],
                'message': parts[3]
            })

    # Add to Neo4j
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

    logger.info(f"Added {len(commits)} commits to graph")


def check_status() -> bool:
    """Check graph status."""
    try:
        client = Neo4jClient()
        stats = client.get_stats()

        print("\n" + "=" * 60)
        print("SAVE-MY-TOKENS GRAPH STATUS")
        print("=" * 60)
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

        # Commit count
        with client.driver.session() as session:
            result = session.run("MATCH (c:Commit) RETURN COUNT(c) as count")
            commit_count = result.single()['count']

        print(f"\nCommits Tracked: {commit_count}")

        if stats['node_count'] > 0:
            print("\nStatus: READY")
        else:
            print("\nStatus: EMPTY - Run 'python build_graph.py' to build")

        print("=" * 60 + "\n")

        client.close()
        return stats['node_count'] > 0

    except Exception as e:
        logger.error(f"Failed to check status: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build or manage save-my-tokens graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_graph.py              # Build graph from source
  python build_graph.py --clear      # Clear and rebuild
  python build_graph.py --check      # Check graph status
        """
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear existing graph before building'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check graph status without building'
    )

    args = parser.parse_args()

    if args.check:
        success = check_status()
        sys.exit(0 if success else 1)
    else:
        success = build_fresh(clear=args.clear)

        if success:
            print("\n[OK] Graph ready for use")
            sys.exit(0)
        else:
            print("\n[ERROR] Graph build failed")
            sys.exit(1)


if __name__ == '__main__':
    main()
