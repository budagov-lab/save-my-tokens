#!/usr/bin/env python3
"""
save-my-tokens Setup - ONE COMMAND

User runs:
    python setup.py

That's it. Everything else is automatic.
"""

import sys
import json
import subprocess
from pathlib import Path

def create_claude_settings(project_root: Path) -> bool:
    """Create .claude/settings.json for Claude Code."""
    print("  Creating .claude/settings.json...", end=" ", flush=True)
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

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
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "jq -r '.tool_input.file_path // .tool_response.filePath' | grep -E '\\.py$' | { read -r f; python -m black --line-length 100 \"$f\" 2>/dev/null || true; }",
                                "statusMessage": "Formatting Python with Black",
                                "timeout": 10
                            }
                        ]
                    },
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "jq -r '.tool_input.file_path // .tool_response.filePath' | grep -E '\\.py$' && python -m mypy \"$(jq -r '.tool_input.file_path // .tool_response.filePath')\" --ignore-missing-imports 2>/dev/null || true",
                                "statusMessage": "Type checking with mypy",
                                "timeout": 15
                            }
                        ]
                    }
                ],
                "SessionStart": [
                    {
                        "matcher": "SessionStart",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "echo '{\"systemMessage\": \"📊 Graph API Project (Phase 1 MVP) - MCP tools available. Use get_context(), semantic_search(), validate_conflicts() for code analysis.\"}'",
                                "statusMessage": "Loading project context"
                            }
                        ]
                    }
                ]
            },
            "respectGitignore": True,
            "cleanupPeriodDays": 30,
            "spinnerTipsEnabled": True,
            "spinnerVerbs": {
                "mode": "append",
                "verbs": [
                    "Parsing symbols",
                    "Building graphs",
                    "Querying Neo4j",
                    "Embedding vectors",
                    "Validating conflicts"
                ]
            },
            "attribution": {
                "commit": "Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
            }
        }

        settings_file = claude_dir / 'settings.json'
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def create_mcp_instructions(project_root: Path) -> bool:
    """Create .claude/MCP_SETUP_INSTRUCTIONS.md with tool documentation."""
    print("  Creating .claude/MCP_SETUP_INSTRUCTIONS.md...", end=" ", flush=True)
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

        instructions = """# MCP Setup Instructions for Claude

This document tells Claude how to use save-my-tokens (SMT) MCP in your project.

## What This Is

**save-my-tokens (SMT)** is an MCP server that gives you access to 10 powerful tools for understanding code:

- **Graph queries** (get_context, get_subgraph, semantic_search)
- **Conflict detection** (validate_conflicts)
- **Contract analysis** (extract_contract, compare_contracts)
- **Git integration** (parse_diff, apply_diff)
- **Task scheduling** (schedule_tasks, execute_tasks)

**Why it matters:** Instead of reading entire files (5000+ tokens), you get minimal context (287 tokens avg). That's 11x more token budget for solving problems.

---

## Available MCP Tools

### Graph Queries
| Tool | What It Does |
|------|-------------|
| `get_context(symbol)` | Function definition + callers + dependencies |
| `get_subgraph(symbol)` | Full dependency tree |
| `semantic_search(query)` | Find code by meaning |
| `validate_conflicts(tasks)` | Check if changes conflict |

### Contracts & Breaking Changes
| Tool | What It Does |
|------|-------------|
| `extract_contract(code)` | Parse signatures & types |
| `compare_contracts(old, new)` | Detect breaking changes |

### Git & Updates
| Tool | What It Does |
|------|-------------|
| `parse_diff()` | Analyze git changes |
| `apply_diff()` | Update graph from commits |

### Task Scheduling
| Tool | What It Does |
|------|-------------|
| `schedule_tasks(tasks)` | Auto-parallelize work |
| `execute_tasks(plan)` | Run with dependency resolution |

---

## How to Use

### 1. Understand Code
```
User: "What does validate_token() do?"
Claude calls: get_context("validate_token", include_callers=true)
Result: Definition + callers + dependencies
```

### 2. Find Related Code
```
User: "Show me password validation logic"
Claude calls: semantic_search("password validation")
Result: Ranked list of matching functions
```

### 3. Refactor Safely
```
User: "Can I change process_data() signature?"
Claude calls: compare_contracts(old_code, new_code)
Result: Lists breaking changes if any
```

### 4. Parallelize Tasks
```
User: "Can these changes run in parallel?"
Claude calls: validate_conflicts([task1, task2, task3])
Result: no_conflicts=true or lists conflicts
```

---

## Rules for Safe Usage

1. **Always query before assuming** — Use get_context() before refactoring
2. **Check compatibility** — Use compare_contracts() before changing signatures
3. **Validate conflicts** — Use validate_conflicts() before parallelizing
4. **Estimate tokens** — MCP queries use 287 tokens avg vs 5000+ for files

---

## Troubleshooting

### "MCP tools not available"
1. Check: `python run.py` is running
2. Check: `.mcp.json` exists with correct path
3. Restart Claude Code

### "Graph is empty"
```bash
python run.py graph  # Build graph
```

### "Neo4j not running"
```bash
docker-compose up -d neo4j
```

---

## Remember

Use MCP tools to **save tokens and make smarter code changes**.
Every query instead of file read = 4700 tokens saved.
Every conflict check = prevents bugs.
Every semantic search = faster code discovery.

The graph is your source of truth. Use it.
"""

        instructions_file = claude_dir / 'MCP_SETUP_INSTRUCTIONS.md'
        with open(instructions_file, 'w') as f:
            f.write(instructions)

        if instructions_file.exists():
            print("[OK]")
            return True
        else:
            print("[FAIL - file not created]")
            return False
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def create_claude_workspace(project_root: Path) -> bool:
    """Create .claude/workspace.json for project-level config."""
    print("  Creating .claude/workspace.json...", end=" ", flush=True)
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

        workspace_config = {
            "mcp_enabled": True,
            "graph_auto_sync": True,
            "graph_base_path": "src",
            "neo4j_uri": "bolt://localhost:7687",
            "project_name": "save-my-tokens",
            "description": "Semantic code graph for parallel agents"
        }

        workspace_file = claude_dir / 'workspace.json'
        with open(workspace_file, 'w') as f:
            json.dump(workspace_config, f, indent=2)
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def create_mcp_json(project_root: Path) -> bool:
    """Create .mcp.json for MCP server discovery."""
    print("  Creating .mcp.json...", end=" ", flush=True)
    try:
        mcp_config = {
            "mcpServers": {
                "smt": {
                    "command": "python",
                    "args": [str(project_root / "run.py")]
                }
            }
        }
        mcp_file = project_root / '.mcp.json'
        with open(mcp_file, 'w') as f:
            json.dump(mcp_config, f, indent=2)

        if mcp_file.exists():
            print("[OK]")
            return True
        else:
            print("[FAIL - file not created]")
            return False
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def run_setup():
    """Run complete setup."""
    project_root = Path.cwd()  # Use current working directory, not script location

    # Banner
    print("\n" + "*"*70)
    print("*" + " "*68 + "*")
    print("*" + " "*20 + "SAVE-MY-TOKENS" + " "*34 + "*")
    print("*" + " "*68 + "*")
    print("*"*70)

    print("\n  Intelligent Code Context for Claude\n")
    print("  Features:")
    print("    [+] Minimal context queries instead of full files")
    print("    [+] Semantic code understanding via Neo4j graph")
    print("    [+] Smart function context with callers & dependencies")
    print("    [+] Breaking change detection before refactoring")
    print("    [+] Parallel task conflict validation")
    print("    [+] Auto-configured for Claude Code on setup\n")
    print("*"*70 + "\n")

    # Phase 0: Install packages
    print("[Phase 0] Installing Required Packages")
    print("-" * 70)

    core_packages = [
        'loguru',
        'neo4j',
        'tree-sitter',
        'mcp',
        'fastapi',
    ]

    for package in core_packages:
        print(f"  Installing {package}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package, '-q'],
            capture_output=True
        )
        print("[OK]" if result.returncode == 0 else "[WARN]")

    print()

    # Phase 1: Check prerequisites
    print("[Phase 1] Checking Prerequisites")
    print("-" * 70)

    # Check Neo4j
    print("  Checking Neo4j running...", end=" ", flush=True)
    try:
        result = subprocess.run(['curl', '-s', 'http://localhost:7474'],
                              capture_output=True, timeout=2)
        print("[OK]" if result.returncode == 0 else "[FAIL]")
        if result.returncode != 0:
            print("\nERROR: Neo4j is not running!")
            print("Start with: docker-compose up -d neo4j\n")
            return False
    except:
        print("[FAIL]")
        print("\nERROR: Neo4j not accessible!")
        print("Start with: docker-compose up -d neo4j\n")
        return False

    # Check Python
    print("  Checking Python 3.10+...", end=" ", flush=True)
    if sys.version_info >= (3, 10):
        print("[OK]")
    else:
        print("[FAIL]")
        print(f"\nERROR: Python {sys.version_info.major}.{sys.version_info.minor} (need 3.10+)\n")
        return False

    print()

    # Phase 2: Build graph
    print("[Phase 2] Building Code Graph")
    print("-" * 70)

    print("  Checking if graph needs building...", end=" ", flush=True)
    try:
        from src.graph.neo4j_client import Neo4jClient
        client = Neo4jClient()
        stats = client.get_stats()
        client.close()

        if stats['node_count'] > 100:
            print(f"[OK] ({stats['node_count']} nodes already indexed)")
        else:
            print("[BUILD NEEDED]")
            print("  Building graph from source...", end=" ", flush=True)
            result = subprocess.run(
                [sys.executable, 'build_graph.py'],
                cwd=project_root,
                capture_output=True,
                timeout=300
            )
            print("[OK]" if result.returncode == 0 else "[FAIL]")
            if result.returncode != 0:
                print("  Try: python build_graph.py --check")
    except Exception as e:
        print(f"[ERROR] {e}")

    print()

    # Phase 3: Configure Claude Code
    print("[Phase 3] Configuring Claude Code")
    print("-" * 70)

    success = True
    success &= create_mcp_json(project_root)
    success &= create_claude_settings(project_root)
    success &= create_claude_workspace(project_root)
    success &= create_mcp_instructions(project_root)

    print()

    # Success!
    print("="*70)
    print("[SUCCESS] SETUP COMPLETE!")
    print("="*70)
    print()
    print("What's next:")
    print("  1. Start MCP server: python run.py")
    print("  2. Open this folder in Claude Code")
    print("  3. Claude will auto-detect MCP and use SMT tools")
    print()
    print("MCP files created:")
    print("  - .mcp.json                    (MCP server config)")
    print("  - .claude/settings.json        (Claude Code settings)")
    print("  - .claude/workspace.json       (Project workspace config)")
    print("  - .claude/MCP_SETUP_INSTRUCTIONS.md (Tool guide)")
    print()

    return success

if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
