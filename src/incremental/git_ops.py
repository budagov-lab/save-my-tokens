"""Git subprocess helpers for incremental graph updates."""

import subprocess
from typing import List, Optional

from loguru import logger

from src.graph.node_types import CommitNode


def run_git(args: List[str], cwd: str) -> str:
    """Run a git command and return stdout.

    Raises:
        RuntimeError: If git command fails or git not found.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e
    except FileNotFoundError as e:
        raise RuntimeError("Git not found in PATH") from e


def get_commit_metadata(ref: str, repo_path: str) -> CommitNode:
    """Extract commit metadata from git log.

    Args:
        ref: Commit reference (e.g. "HEAD", "HEAD~1")
        repo_path: Repository path

    Raises:
        RuntimeError: If git log fails or output is malformed.
    """
    output = run_git(
        ["log", "-1", "--format=%H|%h|%s|%an|%aI", ref],
        cwd=repo_path,
    ).strip()

    if not output:
        raise RuntimeError(f"Failed to get commit metadata for {ref}")

    parts = output.split("|")
    if len(parts) < 5:
        raise RuntimeError(f"Invalid git log format: {output}")

    commit_hash, short_hash, message, author, timestamp = parts[:5]

    branch = run_git(["rev-parse", "--abbrev-ref", ref], cwd=repo_path).strip() or "unknown"

    files_output = run_git(
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
