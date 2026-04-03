# Working with save-my-tokens

## What This Project Is

**save-my-tokens (SMT)** is an MCP server that builds a semantic graph of your codebase using Neo4j + Tree-sitter.

**Status:** All 20 MCP tools are fully implemented and ready to use. Start with `python run.py`.

## Tools You Have Right Now

✅ **Standard Claude Code Tools:**
- `Read`, `Write`, `Edit` — work with files  
- `Glob`, `Grep` — search codebase  
- `Bash` — run shell commands (docker, git, python)  
- `Agent` (Explore) — comprehensive codebase analysis  
- `TaskCreate/TaskUpdate` — track your work  

✅ **MCP Tools (when server is running):**
- All 20 tools are fully implemented in src/mcp_server/tools/
- Start server: `python run.py`
- Then use them in Claude Code (when integrated)

## Quick Start

```bash
# ONE-TIME: Initialize project
python setup.py

# Start MCP server (auto-starts Docker, builds graph)
python run.py

# In a separate terminal, check status
python run.py graph --check
```

When running, the MCP server exposes 20 tools for code understanding, graph management, contracts, git integration, and task scheduling.

## The 20 MCP Tools (All Ready)

### Code Understanding (4 tools)
- `get_context(symbol, depth=1, include_callers=False)` — function + callers + dependencies
- `get_subgraph(symbol, depth=2)` — full dependency tree
- `semantic_search(query, top_k=5)` — find code by meaning (embedding-based)
- `validate_conflicts(tasks)` — detect conflicts between parallel changes

### Graph Management (8 tools)
- `graph_init()` — create indexes, prepare for building
- `graph_stats()` — node/edge counts, status, integrity
- `graph_rebuild(project_dir="./src", clear_first=True)` — full reconstruction from source
- `graph_diff_rebuild(commit_range)` — incremental update from git commits
- `graph_validate()` — check integrity and repair
- `graph_clear_symbol(symbol_name)` — remove single symbol + edges
- `graph_backup(output_file)` — export to JSON
- `graph_restore(input_file)` — import from JSON
- `graph_export(format="graphml")` — export as JSON or GraphML
- `graph_reindex()` — rebuild indexes for performance

### Breaking Changes (2 tools)
- `extract_contract(symbol_name, file_path, source_code)` — parse function signature + contract
- `compare_contracts(old_contract, new_contract)` — detect breaking changes before refactoring

### Git Integration (2 tools)
- `parse_diff(diff_text)` — analyze git diff output
- `apply_diff(file, added_symbols, deleted_symbol_names, modified_symbols)` — sync graph with commits

### Task Scheduling (2 tools)
- `schedule_tasks(tasks)` — build execution plan with parallelization
- `execute_tasks(tasks, timeout_seconds=30)` — run with dependency resolution

## Key Directories

- **`src/parsers/`** — Tree-sitter parsers (extract symbols)
- **`src/graph/`** — Graph building pipeline (parse → index → Neo4j)
- **`src/mcp_server/`** — MCP server + all 20 tools
  - `tools/graph_tools.py` → get_context, get_subgraph, semantic_search, validate_conflicts
  - `tools/database_tools.py` → graph_* tools
  - `tools/contract_tools.py` → extract_contract, compare_contracts
  - `tools/incremental_tools.py` → parse_diff, apply_diff
  - `tools/scheduling_tools.py` → schedule_tasks, execute_tasks
- **`src/contracts/`** — Breaking change detection
- **`src/incremental/`** — Git-aware graph updates
- **`tests/`** — Test fixtures
- **`run.py`** — Start MCP server, manage Docker/graph
- **`setup.py`** — One-time project initialization

## Commands Reference

```bash
# ONE-TIME: Initialize
python setup.py

# Start MCP server
python run.py

# Check graph
python run.py graph --check

# Docker management
python run.py docker status
python run.py docker up
python run.py docker down

# Run tests
pytest tests/ -v
```

## How to Use the Tools

The MCP server runs as a subprocess when you execute `python run.py`. It:
1. Starts Neo4j (or connects to existing instance)
2. Builds/updates the code graph from src/
3. Exposes the 20 tools via MCP protocol

To call a tool:
```python
# Example: get_context tool
result = get_context("my_function_name", depth=2, include_callers=True)
```

Or via Claude Code when MCP is configured:
```
Use get_context to understand the function "validate_email"
```

## Next Steps

1. Run `python setup.py` — creates config files
2. Run `python run.py` — starts MCP server + Neo4j
3. Check `python run.py graph --check` — see if graph built
4. Open folder in Claude Code — tools become available when .mcp.json is recognized
