# Save My Tokens (SMT)

Give Claude smart code context instead of entire files.

## Setup (5 minutes)

```bash
# 1. Start database (one time)
docker-compose up -d neo4j

# 2. Install & configure (one time)
python setup.py

# 3. Run server (every session)
python run.py
```

Done. `python run.py` is all you need. Claude automatically uses SMT tools.

## How It Works

When you ask Claude about your code:

**Without SMT:**
- Claude reads entire file
- Doesn't know who calls this function
- Can't tell if changes break something

**With SMT (automatic):**
- Claude calls `get_context(symbol)`
- Gets: definition + callers + dependencies
- Minimal context needed
- Understands the code instantly

## The Problem

Claude reads entire files to find one function. It doesn't know who calls it or what breaks if you change it.

## The Solution

SMT gives exact context: function + callers + dependencies + breaking changes. Minimal token usage.

## Tools (10 total)

| Tool | Purpose |
|------|---------|
| `get_context` | Function + callers + dependencies |
| `get_subgraph` | Full dependency tree |
| `semantic_search` | Find code by meaning |
| `validate_conflicts` | Check if changes conflict |
| `extract_contract` | Parse signatures & types |
| `compare_contracts` | Detect breaking changes |
| `parse_diff` | Analyze git changes |
| `apply_diff` | Update graph from commits |
| `schedule_tasks` | Auto-parallelize work |
| `execute_tasks` | Run with dependency resolution |

## How It Works

```
Your Code → Parse (Tree-sitter) → Index (Neo4j) → Query (MCP) → Claude Code
```

Supports: Python, TypeScript, Go, Rust, Java

## Why Use This

✨ **Minimal context** — Only what's needed  
✨ **Safe refactoring** — Breaking change detection  
✨ **Parallelization** — Conflict detection  
✨ **Semantic search** — Find code by meaning  
✨ **Git-aware** — Incremental updates  

## Requirements

- Python 3.10+
- Docker (for Neo4j)
- Claude Code or Claude Desktop

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

**Setup:** `python setup.py` installs, builds, and configures everything.

**Run:** `python run.py` starts the MCP server.

**Use:** Just ask Claude about your code naturally.
