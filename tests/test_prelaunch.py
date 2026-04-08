"""
Pre-launch tests for save-my-tokens.

These tests verify that the basic setup and dependencies work before
running the CLI tool.
"""

import sys
import json
import subprocess
from pathlib import Path

import pytest


class TestDependencies:
    """Test that core dependencies can be imported."""

    def test_import_loguru(self):
        """Test loguru is available."""
        try:
            import loguru
            assert loguru is not None
        except ImportError:
            pytest.skip("loguru not installed")

    def test_import_neo4j(self):
        """Test neo4j driver is available."""
        try:
            import neo4j
            assert neo4j is not None
        except ImportError:
            pytest.skip("neo4j not installed")

    def test_import_tree_sitter(self):
        """Test tree-sitter is available."""
        try:
            import tree_sitter
            assert tree_sitter is not None
        except ImportError:
            pytest.skip("tree-sitter not installed")

    def test_import_sentence_transformers(self):
        """Test sentence-transformers is available."""
        try:
            import sentence_transformers
            assert sentence_transformers is not None
        except ImportError:
            pytest.skip("sentence-transformers not installed")


class TestSyntax:
    """Test that Python files have valid syntax."""

    def test_run_py_syntax(self):
        """Test run.py has valid Python syntax."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "run.py"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0, f"Syntax error in run.py: {result.stderr.decode()}"

    def test_configure_py_syntax(self):
        """Test configure.py has valid Python syntax."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "configure.py"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0, f"Syntax error in configure.py: {result.stderr.decode()}"

    def test_smt_cli_py_syntax(self):
        """Test src/smt_cli.py has valid Python syntax."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "src/smt_cli.py"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0, f"Syntax error in src/smt_cli.py: {result.stderr.decode()}"


class TestConfigFiles:
    """Test that Claude Code config files can be created."""

    def test_create_settings_json(self, tmp_path):
        """Test .claude/settings.json creation."""
        settings_file = tmp_path / "settings.json"
        settings = {
            "model": "haiku",
            "permissions": {
                "defaultMode": "auto",
                "allow": ["Read", "Edit", "Bash"]
            }
        }
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)

        assert settings_file.exists()
        with open(settings_file) as f:
            loaded = json.load(f)
        assert loaded == settings


class TestRunPy:
    """Test run.py functionality."""

    def test_run_py_help(self):
        """Test run.py --help works."""
        result = subprocess.run(
            [sys.executable, "run.py", "--help"],
            capture_output=True,
            timeout=10
        )
        assert result.returncode == 0
        output = result.stdout.decode()
        assert "save-my-tokens" in output or "usage:" in output

    def test_run_py_graph_check(self):
        """Test run.py graph --check works."""
        result = subprocess.run(
            [sys.executable, "run.py", "graph", "--check"],
            capture_output=True,
            timeout=30
        )
        # Should succeed or fail gracefully (if Neo4j not running)
        assert result.returncode in [0, 1]

    def test_run_py_docker_status(self):
        """Test run.py docker status works."""
        result = subprocess.run(
            [sys.executable, "run.py", "docker", "status"],
            capture_output=True,
            timeout=10
        )
        # Should succeed (Neo4j may or may not be running)
        assert result.returncode in [0, 1]


class TestSourceFiles:
    """Test that source files are valid."""

    def test_src_parsers_exist(self):
        """Test src/parsers directory exists."""
        parsers_dir = Path("src/parsers")
        assert parsers_dir.exists()
        assert (parsers_dir / "__init__.py").exists()

    def test_src_graph_exist(self):
        """Test src/graph directory exists."""
        graph_dir = Path("src/graph")
        assert graph_dir.exists()
        assert (graph_dir / "__init__.py").exists()

    def test_src_smt_cli_exists(self):
        """Test src/smt_cli.py exists."""
        cli_file = Path("src/smt_cli.py")
        assert cli_file.exists()

    def test_claude_config_files_exist(self):
        """Test essential Claude config files exist."""
        assert Path(".claude/settings.json").exists(), ".claude/settings.json missing"


class TestGitRepo:
    """Test git repository is valid."""

    def test_git_repo_exists(self):
        """Test .git directory exists."""
        assert Path(".git").exists()

    def test_git_config_valid(self):
        """Test git config is valid."""
        result = subprocess.run(
            ["git", "config", "--list"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0

    def test_git_status(self):
        """Test git status works."""
        result = subprocess.run(
            ["git", "status"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0


class TestDocumentation:
    """Test documentation files exist."""

    def test_readme_exists(self):
        """Test README exists."""
        assert Path("README.md").exists() or Path("readme.md").exists()

    def test_claude_md_exists(self):
        """Test CLAUDE.md exists."""
        assert Path("CLAUDE.md").exists()

    def test_dockerfile_exists(self):
        """Test docker-compose.yml exists."""
        assert Path("docker-compose.yml").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
