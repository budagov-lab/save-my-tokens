#!/usr/bin/env python3
"""
save-my-tokens Setup - ONE COMMAND

Official Claude Code configuration following scope hierarchy:
- .mcp.json (project-scoped MCP servers)
- .claude/settings.json (project-scoped settings)
- .claude/HARNESS.md (project documentation)
"""

import sys
import json
import subprocess
from pathlib import Path


def setup_mcp_json(project_root: Path) -> bool:
    """
    Create .mcp.json - Project-scoped MCP server configuration.

    This defines the save-my-tokens MCP server for Claude Code.
    Stored in root .mcp.json (not .claude/), per Claude Code spec.
    """
    print("  Creating .mcp.json...", end=" ", flush=True)
    try:
        mcp_file = project_root / '.mcp.json'
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
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def setup_claude_settings(project_root: Path) -> bool:
    """
    Create .claude/settings.json - Project-scoped Claude Code configuration.

    Per official docs (code.claude.com/docs/en/settings):
    - .claude/settings.json applies to all collaborators on this repo
    - Checked into git and shared with team
    - Permissions, environment variables, tools, hooks go here
    """
    print("  Creating .claude/settings.json...", end=" ", flush=True)
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

        settings = {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
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
                "NEO4J_LOG_LEVEL": "info"
            },
            "respectGitignore": True
        }

        settings_file = claude_dir / 'settings.json'
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def setup_harness_documentation(project_root: Path) -> bool:
    """
    Create .claude/HARNESS.md - Project documentation for Claude Code.

    Explains:
    - What tools are available (real vs. planned)
    - How to work with this project
    - Key commands and directories
    """
    print("  Creating .claude/HARNESS.md...", end=" ", flush=True)
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

        harness_content = """# Working with save-my-tokens

## Project Overview

**save-my-tokens (SMT)** = MCP server that builds a semantic code graph using Neo4j + Tree-sitter.

Exposes 20 tools for understanding code without reading entire files.

## Available Tools Now

✅ Real tools in Claude Code:
- `Read`, `Write`, `Edit` — file operations
- `Glob`, `Grep` — codebase search
- `Bash` — system commands (docker, git, python)
- `Agent (Explore)` — comprehensive codebase analysis
- Task tools — progress tracking

✅ MCP Tools (fully implemented, ready to use):
- `get_context()`, `semantic_search()`, `compare_contracts()`, `graph_stats()`, etc.
- Require: Running Neo4j + active MCP server
- All 20 tools in src/mcp_server/tools/ are ready

## How to Work

**For code analysis:** Use Explore agent (faster than manual Read/Grep).

**For quick searches:** Use Glob/Grep/Read directly.

**For MCP tool testing:**
```bash
python run.py                    # Start MCP server + auto-starts Docker
python run.py graph --check      # See graph status
```

## Project Structure

```
src/parsers/          Tree-sitter parsers (Python, TypeScript)
src/graph/            Graph building pipeline
src/mcp_server/       MCP tool implementations (20 tools)
src/contracts/        Breaking change detection
src/incremental/      Git-aware graph updates
src/projects.py       Multi-project database support
tests/                Test fixtures

run.py                MCP server + Docker management
setup.py              Project initialization (this file)
```

## Quick Commands

```bash
# ONE-TIME: Initialize project
python setup.py

# Start everything (auto-starts Docker + builds graph + starts MCP)
python run.py

# Check graph status
python run.py graph --check

# Docker operations
python run.py docker status
python run.py docker up
python run.py docker down

# Tests
pytest tests/ -v
```

## The 20 MCP Tools (Ready Now)

To use them: Start the MCP server (`python run.py`), then they're available.

**Code Understanding (4):**
- `get_context(symbol, depth=1, include_callers=False)` — function + callers + dependencies
- `get_subgraph(symbol, depth=2)` — dependency tree (N hops)
- `semantic_search(query, top_k=5)` — find code by meaning (embedding-based)
- `validate_conflicts(tasks)` — detect conflicts between parallel changes

**Graph Management (8):**
- `graph_init()` — create indexes, prepare for building
- `graph_stats()` — node/edge counts, status
- `graph_rebuild(project_dir="./src", clear_first=True)` — full reconstruction from source
- `graph_diff_rebuild(commit_range)` — incremental from git commits
- `graph_validate()` — integrity check and repair
- `graph_clear_symbol(symbol_name)` — remove single symbol + edges
- `graph_backup(output_file)` — export to JSON
- `graph_restore(input_file)` — import from JSON
- `graph_export(format="graphml")` — export as JSON or GraphML
- `graph_reindex()` — rebuild indexes for performance

**Breaking Changes (2):**
- `extract_contract(symbol_name, file_path, source_code)` — parse function signature + contract
- `compare_contracts(old_contract, new_contract)` — detect breaking changes before refactoring

**Git Integration (2):**
- `parse_diff(diff_text)` — analyze git diff output
- `apply_diff(file, added_symbols, deleted_symbol_names, modified_symbols)` — sync graph with commits

**Task Scheduling (2):**
- `schedule_tasks(tasks)` — build execution plan with parallelization
- `execute_tasks(tasks, timeout_seconds=30)` — run with dependency resolution

**How to use them:**
1. `python run.py` — Start MCP server (auto-starts Docker, builds graph)
2. Open folder in Claude Code
3. Use the tools (e.g., `get_context("my_function")`)
"""
        harness_file = claude_dir / 'HARNESS.md'
        with open(harness_file, 'w', encoding='utf-8') as f:
            f.write(harness_content)
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def install_packages(project_root: Path) -> bool:
    """Install required Python packages."""
    print("[Installing Packages]")
    print("-" * 70)

    packages = [
        'loguru',
        'neo4j',
        'tree-sitter',
        'mcp',
        'fastapi',
        'sentence-transformers',
        'pydantic',
        'gitpython',
    ]

    for package in packages:
        print(f"  {package}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package, '-q'],
            capture_output=True
        )
        print("[OK]" if result.returncode == 0 else "[WARN]")

    print()
    return True


def check_prerequisites(project_root: Path) -> bool:
    """Check that prerequisites are met."""
    print("[Checking Prerequisites]")
    print("-" * 70)

    # Check Python version
    print(f"  Python version...", end=" ", flush=True)
    if sys.version_info >= (3, 10):
        print(f"[OK] {sys.version_info.major}.{sys.version_info.minor}")
    else:
        print(f"[FAIL] Need 3.10+, have {sys.version_info.major}.{sys.version_info.minor}")
        return False

    # Check Docker (optional)
    print(f"  Docker...", end=" ", flush=True)
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, timeout=2)
        if result.returncode == 0:
            print("[OK]")
        else:
            print("[WARN - optional, needed for Neo4j]")
    except FileNotFoundError:
        print("[WARN - optional, needed for Neo4j]")

    print()
    return True


def run_setup():
    """Main setup orchestration."""
    project_root = Path.cwd()

    # Banner
    print("\n" + "=" * 70)
    print("  SAVE-MY-TOKENS SETUP")
    print("=" * 70)
    print("\n  Intelligent Code Context for Claude\n")
    print("  ✓ Semantic code graph with Neo4j")
    print("  ✓ 20 MCP tools for code understanding")
    print("  ✓ Auto-configured for Claude Code\n")
    print("=" * 70 + "\n")

    # Phase 1: Check prerequisites
    if not check_prerequisites(project_root):
        return False

    # Phase 2: Install packages
    if not install_packages(project_root):
        return False

    # Phase 3: Configure Claude Code (3 files per official spec)
    print("[Configuring Claude Code]")
    print("-" * 70)

    success = True
    success &= setup_mcp_json(project_root)
    success &= setup_claude_settings(project_root)
    success &= setup_harness_documentation(project_root)

    if not success:
        return False

    print()

    # Success
    print("=" * 70)
    print("[SUCCESS] SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("Configuration files created:")
    print("  ✓ .mcp.json                      (MCP server definition)")
    print("  ✓ .claude/settings.json          (Claude Code permissions/env)")
    print("  ✓ .claude/HARNESS.md             (Project documentation)")
    print()
    print("Next steps:")
    print("  1. Start MCP server:")
    print("     python run.py")
    print()
    print("  2. (Optional) Check graph status:")
    print("     python run.py graph --check")
    print()
    print("  3. Open this folder in Claude Code")
    print()

    return True


if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
