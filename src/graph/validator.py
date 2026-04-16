"""Graph validation — check freshness and consistency against git."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

from src.graph.neo4j_client import Neo4jClient


@dataclass
class ValidationResult:
    """Result of graph validation against git state."""

    is_fresh: bool  # Graph HEAD matches git HEAD
    git_head: str  # Current git commit hash (short, e.g., "a1b2c3d")
    graph_head: Optional[str]  # Last commit indexed into graph (or None if no commits yet)
    commits_behind: int  # Number of commits since last index (0 if fresh)
    stale_files: List[str] = field(default_factory=list)  # Files changed since last index


def validate_graph(neo4j_client: Neo4jClient, repo_path: Path) -> ValidationResult:
    """
    Validate graph freshness by comparing git HEAD with last indexed commit.

    Args:
        neo4j_client: Connected Neo4j client
        repo_path: Path to git repository

    Returns:
        ValidationResult with freshness status and details
    """
    # Get current git HEAD
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        git_head = result.stdout.strip()
        if not git_head:
            logger.warning("Could not determine git HEAD")
            return ValidationResult(
                is_fresh=False,
                git_head="unknown",
                graph_head=None,
                commits_behind=-1,
            )
    except Exception as e:
        logger.warning(f"Failed to get git HEAD: {e}")
        return ValidationResult(
            is_fresh=False,
            git_head="error",
            graph_head=None,
            commits_behind=-1,
        )

    # Get last indexed commit from Neo4j, scoped to current project when possible.
    # Instead of filtering by project_id on the Commit node (commits don't carry project_id),
    # we follow MODIFIED_BY edges from project-scoped symbol nodes to their commits.
    try:
        with neo4j_client.driver.session() as session:
            if neo4j_client.project_id:
                result = session.run(
                    "MATCH (n {project_id: $pid})-[:MODIFIED_BY]->(c:Commit) "
                    "RETURN c.short_hash AS short_hash "
                    "ORDER BY c.timestamp DESC LIMIT 1",
                    pid=neo4j_client.project_id,
                )
            else:
                result = session.run(
                    "MATCH (c:Commit) RETURN c.short_hash AS short_hash "
                    "ORDER BY c.timestamp DESC LIMIT 1"
                )
            record = result.single()
            graph_head = record["short_hash"] if record else None
    except Exception as e:
        logger.warning(f"Failed to query graph commits: {e}")
        graph_head = None

    # If no graph commits yet, it's not fresh
    if not graph_head:
        logger.debug("No commits found in graph")
        return ValidationResult(
            is_fresh=False,
            git_head=git_head,
            graph_head=None,
            commits_behind=-1,
        )

    # Check if fresh (heads match)
    is_fresh = git_head == graph_head

    if is_fresh:
        return ValidationResult(
            is_fresh=True,
            git_head=git_head,
            graph_head=graph_head,
            commits_behind=0,
        )

    # Not fresh — count commits and files
    commits_behind = 0
    stale_files: List[str] = []

    try:
        # Count commits between graph_head and git_head
        result = subprocess.run(
            ["git", "log", f"{graph_head}..HEAD", "--oneline"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            commits_behind = len([l for l in result.stdout.strip().split("\n") if l])

        # Get list of changed files
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{graph_head}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            stale_files = [f for f in result.stdout.strip().split("\n") if f]
    except Exception as e:
        logger.warning(f"Failed to count commits/files: {e}")
        commits_behind = -1

    return ValidationResult(
        is_fresh=False,
        git_head=git_head,
        graph_head=graph_head,
        commits_behind=commits_behind,
        stale_files=stale_files,
    )


def format_validation_line(validation: ValidationResult) -> str:
    """Format a single-line validation status for CLI output.

    Returns:
        String like "✓ fresh" or "! 3 commits behind"
    """
    if validation.is_fresh:
        return f"HEAD {validation.git_head}  [✓] fresh"

    if validation.commits_behind < 0:
        return f"HEAD {validation.git_head}  [?] unknown (run: smt sync)"

    if validation.commits_behind == 0:
        return f"HEAD {validation.git_head}  [!] out-of-sync"

    return f"HEAD {validation.git_head}  [!] {validation.commits_behind} commits behind"


def format_stale_files_line(validation: ValidationResult) -> Optional[str]:
    """Format stale files as a multi-line block if any exist.

    Returns:
        String like "  changed:  src/file1.py, src/file2.py" or None
    """
    if not validation.stale_files:
        return None

    # Truncate if too many files
    files_to_show = validation.stale_files[:5]
    suffix = (
        f", +{len(validation.stale_files) - 5} more"
        if len(validation.stale_files) > 5
        else ""
    )
    files_str = ", ".join(files_to_show) + suffix

    return f"  changed:  {files_str}"
