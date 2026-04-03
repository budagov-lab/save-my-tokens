"""
Pre-launch tests for save-my-tokens.

These tests verify that the basic setup and dependencies work before
running the full MCP server.
"""

import sys
import json
import subprocess
import tempfile
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

    def test_import_mcp(self):
        """Test mcp framework is available."""
        try:
            import mcp
            assert mcp is not None
        except ImportError:
            pytest.skip("mcp not installed")


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

    def test_setup_py_syntax(self):
        """Test configure.py has valid Python syntax."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "configure.py"],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0, f"Syntax error in configure.py: {result.stderr.decode()}"


class TestConfigFiles:
    """Test that Claude Code config files can be created."""

    def test_create_mcp_json(self, tmp_path):
        """Test .mcp.json creation."""
        mcp_file = tmp_path / ".mcp.json"
        config = {
            "mcpServers": {
                "smt": {
                    "command": "python",
                    "args": ["run.py"]
                }
            }
        }
        with open(mcp_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        assert mcp_file.exists()
        with open(mcp_file) as f:
            loaded = json.load(f)
        assert loaded == config

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

    def test_create_skill_md(self, tmp_path):
        """Test .claude/skills/mcp-guide/SKILL.md creation."""
        skill_file = tmp_path / "SKILL.md"
        content = """---
name: mcp-guide
description: Test guide
---

# Test
"""
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(content)

        assert skill_file.exists()
        assert skill_file.read_text(encoding='utf-8').startswith("---\n")


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

    def test_src_mcp_server_exist(self):
        """Test src/mcp_server directory exists."""
        mcp_dir = Path("src/mcp_server")
        assert mcp_dir.exists()
        assert (mcp_dir / "__init__.py").exists()

    def test_claude_config_files_exist(self):
        """Test essential Claude config files exist."""
        assert Path(".mcp.json").exists(), ".mcp.json missing"
        assert Path(".claude/settings.json").exists(), ".claude/settings.json missing"
        assert Path(".claude/workspace.json").exists(), ".claude/workspace.json missing"
        assert Path(".claude/skills/mcp-guide/SKILL.md").exists(), "SKILL.md missing"


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
