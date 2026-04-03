# Save My Tokens (SMT)

Intelligent code context for Claude instead of entire files.

## Quick Start (3 steps)

### 1. Start Database (one time)
```bash
docker-compose up -d neo4j
```

### 2. Initialize Project (one time)
```bash
python setup.py
```

Creates:
- `.mcp.json` — MCP server config
- `.claude/settings.json` — Claude Code settings
- `.claude/workspace.json` — Project config  
- `.claude/MCP_SETUP_INSTRUCTIONS.md` — Tool guide

### 3. Start Server (every session)
```bash
python run.py
```

Then open project in Claude Code. MCP tools are available.

---

## The Problem

Claude reads entire files to understand one function. It doesn't know who calls it or what breaks if you change it.

## The Solution

SMT provides exact context: function + callers + dependencies + breaking changes.

Instead of reading files, Claude queries the code graph via MCP tools.

---

## MCP Tools (10 total)

### Graph Query Tools
| Tool | Purpose |
|------|---------|
| `get_context` | Function + callers + dependencies |
| `get_subgraph` | Full dependency tree |
| `semantic_search` | Find code by meaning |
| `validate_conflicts` | Check if changes conflict |

### Code Analysis Tools
| Tool | Purpose |
|------|---------|
| `extract_contract` | Parse function signatures & types |
| `compare_contracts` | Detect breaking changes |

### Graph Management Tools
| Tool | Purpose |
|------|---------|
| `graph_init` | Initialize empty graph |
| `graph_rebuild` | Full rebuild from source |
| `graph_stats` | Get graph status (nodes, edges) |
| `graph_validate` | Check graph integrity |
| `graph_diff_rebuild` | Incremental update from git commits |

### Task Orchestration Tools
| Tool | Purpose |
|------|---------|
| `parse_diff` | Analyze git changes |
| `apply_diff` | Update graph from commits |
| `schedule_tasks` | Auto-parallelize work |
| `execute_tasks` | Run with dependency resolution |

---

## Architecture

```
Source Code → Parse (Tree-sitter) → Index (Neo4j) → Query (MCP) → Claude
```

Supports: Python, TypeScript, Go, Rust, Java

---

## Why This Works

- **Minimal context** — Only what's needed, not entire files
- **Safe refactoring** — Breaking change detection before you refactor
- **Parallelization** — Conflict detection between tasks
- **Semantic search** — Find code by meaning, not just name
- **Git-aware** — Incremental updates from commits

---

## Requirements

- Python 3.10+
- Docker (for Neo4j)
- Claude Code or Claude Desktop

---

## Testing

```bash
pytest tests/ -v
```

## Contributing

```bash
git checkout -b feat/your-feature
# Make changes
pytest tests/ -v
git push
```

## License

MIT

---

**That's it.** Just ask Claude about your code naturally.
