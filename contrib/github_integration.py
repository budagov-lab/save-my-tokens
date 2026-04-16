"""GitHub integration for collaborative graph updates."""

import os
from typing import Optional, List
from dataclasses import dataclass
from loguru import logger


@dataclass
class GitHubPullRequest:
    """GitHub Pull Request metadata."""

    number: int
    title: str
    author: str
    branch: str
    state: str  # "open" or "closed"
    description: str


class GitHubClient:
    """GitHub API client for collaborative graph updates."""

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token (from env: GITHUB_TOKEN)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.repo = None

        if self.token:
            try:
                import subprocess

                result = subprocess.run(
                    ["git", "config", "--get", "remote.origin.url"],
                    capture_output=True,
                    text=True,
                )
                remote_url = result.stdout.strip()

                # Extract repo from URL: https://github.com/owner/repo.git
                if "github.com" in remote_url:
                    parts = remote_url.split("/")
                    self.repo = f"{parts[-2]}/{parts[-1].replace('.git', '')}"
                    logger.info(f"Connected to GitHub repo: {self.repo}")
            except Exception as e:
                logger.debug(f"Could not detect GitHub repo: {e}")

    def get_pull_requests(self) -> List[GitHubPullRequest]:
        """Get open pull requests from GitHub.

        Requires: GITHUB_TOKEN environment variable

        Returns:
            List of pull requests
        """
        if not self.token or not self.repo:
            logger.debug("GitHub integration not configured (set GITHUB_TOKEN)")
            return []

        try:
            import subprocess

            # Use gh CLI if available
            result = subprocess.run(
                ["gh", "pr", "list", "--repo", self.repo, "--state", "open", "--json",
                 "number,title,author,headRefName,state"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.debug(f"Failed to fetch PRs: {result.stderr}")
                return []

            import json

            prs = []
            for item in json.loads(result.stdout):
                pr = GitHubPullRequest(
                    number=item["number"],
                    title=item["title"],
                    author=item["author"]["login"],
                    branch=item["headRefName"],
                    state=item["state"],
                    description="",
                )
                prs.append(pr)

            logger.info(f"Found {len(prs)} open pull requests")
            return prs

        except Exception as e:
            logger.debug(f"Error fetching pull requests: {e}")
            return []

    def get_current_branch(self) -> str:
        """Get current git branch name.

        Returns:
            Current branch name
        """
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get current branch: {e}")
            return "main"

    def is_pr_branch(self) -> bool:
        """Check if current branch is a pull request branch.

        Returns:
            True if on a PR branch (not main/master)
        """
        branch = self.get_current_branch()
        return branch not in ["main", "master", "develop"]

    def get_pr_for_branch(self, branch: str) -> Optional[GitHubPullRequest]:
        """Get PR for specific branch.

        Args:
            branch: Branch name

        Returns:
            PR if exists, None otherwise
        """
        prs = self.get_pull_requests()
        for pr in prs:
            if pr.branch == branch:
                return pr
        return None


class GraphCollaborationManager:
    """Manage collaborative graph updates for teams."""

    def __init__(self, github_client: Optional[GitHubClient] = None):
        """Initialize collaboration manager.

        Args:
            github_client: GitHub client (auto-created if not provided)
        """
        self.github = github_client or GitHubClient()

    def should_update_graph_on_pull_request(self) -> bool:
        """Check if graph should be updated on PR branch.

        Returns:
            True if on PR branch with changes
        """
        if not self.github.is_pr_branch():
            return False

        # Check if there are uncommitted changes or new commits
        import subprocess

        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
        )

        return bool(result.stdout.strip())

    def get_collaboration_info(self) -> dict:
        """Get info about current collaboration context.

        Returns:
            Dict with branch, PR info, team context
        """
        branch = self.github.get_current_branch()
        pr = self.github.get_pr_for_branch(branch) if self.github.is_pr_branch() else None

        return {
            "current_branch": branch,
            "is_pr_branch": self.github.is_pr_branch(),
            "pull_request": {
                "number": pr.number if pr else None,
                "title": pr.title if pr else None,
                "author": pr.author if pr else None,
            } if pr else None,
            "open_prs": len(self.github.get_pull_requests()),
        }
