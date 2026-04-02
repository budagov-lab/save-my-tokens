# Neo4j Management via MCP - Phase 1 Design

## Overview

Currently, Neo4j management (init, rebuild, clear, stats) is not exposed via MCP tools. This document specifies the first scope of Neo4j management operations accessible to Claude and agents.

**Goal:** Enable Claude to manage graph lifecycle (build, rebuild, validate, inspect) without manual CLI commands.

---

## Phase 1 Scope

### Tools to Implement (4 tools)

| Tool | Purpose | Input | Output | Use Case |
|------|---------|-------|--------|----------|
| **graph_init** | Create/initialize empty graph, set up indexes | `project_dir` | `{status, node_count, edge_count, indexes_created}` | Fresh setup, after docker-compose up |
| **graph_rebuild** | Full parse + index build from source | `project_dir`, `clear_first=true` | `{status, nodes_parsed, edges_created, time_ms, token_estimate}` | After code changes, full refresh |
| **graph_stats** | Get current graph stats (nodes, edges, size) | - | `{node_count, edge_count, node_types, edge_types, memory_mb}` | Inspect current state, debugging |
| **graph_validate** | Check graph consistency (orphaned nodes, missing edges) | - | `{is_valid, orphaned_nodes, inconsistencies, warnings}` | Quality assurance before agent use |

### Tools NOT in Phase 1 (Phase 2+)

- `graph_clear_symbol(symbol)` — Remove single symbol + edges
- `graph_diff_rebuild(commit_range)` — Incremental from git history (use existing `apply_diff`)
- `graph_backup/restore` — Database snapshots
- `graph_export` — Dump to JSON/GraphML
- `graph_reindex` — Reindex specific node types

---

## Detailed Design

### 1. `graph_init`

**Purpose:** Initialize graph after docker-compose up (idempotent)

**Input:**
```python
{
    "project_dir": "./src"  # Optional, defaults to config
}
```

**Output:**
```python
{
    "status": "success",
    "message": "Graph initialized",
    "node_count": 0,
    "edge_count": 0,
    "indexes_created": [
        "node_id_idx",
        "node_name_idx",
        "node_file_idx",
        "node_type_idx"
    ]
}
```

**Backend Implementation:**
- Call `Neo4jClient.create_indexes()`
- No parsing (empty graph after init)
- Test Neo4j connectivity
- Return stats before parsing

**Use Case:** After `docker-compose up -d neo4j` or fresh setup
```
Claude: "Initialize the graph after starting Neo4j"
→ Calls: graph_init()
← Returns: "Graph initialized, ready for rebuild"
```

---

### 2. `graph_rebuild`

**Purpose:** Parse all source code + build graph from scratch

**Input:**
```python
{
    "project_dir": "./src",      # What to parse
    "clear_first": true,          # Clear existing graph before rebuild
    "languages": ["python", "typescript"],  # Optional filter
    "include_embeddings": true    # Build embeddings after parsing
}
```

**Output:**
```python
{
    "status": "success",
    "message": "Graph rebuilt",
    
    # Parsing results
    "files_parsed": 42,
    "symbols_extracted": 1250,
    "parse_errors": 2,
    
    # Graph construction
    "nodes_created": 1248,
    "edges_created": 3847,
    
    # Performance
    "elapsed_ms": 5230,
    "symbols_per_sec": 238,
    
    # Estimate token usage for context queries
    "token_estimate_total": 156000,
    "token_estimate_avg_per_symbol": 125
}
```

**Backend Implementation:**
- Uses existing `GraphBuilder` class
- Optional: clear graph first (via `neo4j_client.clear_database()`)
- Call `GraphBuilder(project_dir).build()`
- Optionally: build embeddings via `embedding_service.build_index()`
- Return detailed stats

**Use Case:** Full graph reconstruction
```
Claude: "Rebuild the graph after major code changes"
→ Calls: graph_rebuild(clear_first=true)
← Returns: "Rebuilt: 1248 nodes, 3847 edges in 5.2s"
```

---

### 3. `graph_stats`

**Purpose:** Inspect current graph state

**Input:** (none)

**Output:**
```python
{
    "status": "success",
    "message": "Graph statistics",
    
    # Counts
    "node_count": 1248,
    "edge_count": 3847,
    
    # Breakdown
    "node_types": {
        "File": 42,
        "Function": 856,
        "Class": 245,
        "Type": 105
    },
    "edge_types": {
        "IMPORTS": 423,
        "CALLS": 2156,
        "DEFINES": 1102,
        "DEPENDS_ON": 166
    },
    
    # Size estimates
    "estimated_memory_mb": 45,
    "database_size_mb": 12,
    
    # Health check
    "is_connected": true,
    "last_update": "2026-04-03T00:38:00Z"
}
```

**Backend Implementation:**
- Query Neo4j for node/edge counts
- Breakdown by type using `MATCH (n:Type) RETURN count(*)`
- Estimate memory from node count + embedding cache
- Return last update timestamp

**Use Case:** Inspect state before work
```
Claude: "Check the current graph status"
→ Calls: graph_stats()
← Returns: "1248 nodes, 3847 edges, 45MB memory"
```

---

### 4. `graph_validate`

**Purpose:** Check graph integrity before using for queries

**Input:**
```python
{
    "check_orphaned": true,     # Find nodes with no edges
    "check_cycles": false,      # Detect circular dependencies (slow)
    "check_references": true    # Verify node references are valid
}
```

**Output:**
```python
{
    "status": "valid",  # or "invalid", "warning"
    "message": "Graph is consistent",
    
    # Issues found
    "orphaned_nodes": 0,
    "broken_references": 0,
    "circular_dependencies": 0,
    "inconsistencies": [],
    
    # Warnings
    "warnings": [
        "5 symbols not indexed (parse errors)"
    ],
    
    # Recommendations
    "recommended_actions": [
        "Run graph_rebuild to fix parse errors"
    ],
    
    # Safe to use?
    "safe_for_queries": true,
    "token_estimate_accuracy": "95%"
}
```

**Backend Implementation:**
- Query for nodes with degree = 0
- Check for broken IMPORTS (file doesn't exist)
- Optional cycle detection via recursive CTE (expensive for large graphs)
- Return detailed consistency report

**Use Case:** QA before agent work
```
Claude: "Validate the graph before running semantic search"
→ Calls: graph_validate()
← Returns: "Graph is valid, 1248 nodes consistent"
```

---

## Implementation Order

### Step 1: Create `database_tools.py`
New file: `src/mcp_server/tools/database_tools.py`
- Implement 4 tools above
- Register in `src/mcp_server/entrypoint.py`

### Step 2: Add helper methods to `Neo4jClient`
- `get_node_type_breakdown()` — Count nodes by type
- `get_edge_type_breakdown()` — Count edges by type
- `validate_orphaned_nodes()` — Find nodes with no edges
- `validate_references()` — Check broken links

### Step 3: Extend `GraphBuilder` 
- Expose `build()` with optional clear
- Return detailed stats (not just logging)

### Step 4: Tests
- Unit tests for each tool
- Integration tests (Neo4j running)
- Error cases (Neo4j down, invalid project_dir, etc.)

---

## Integration with Claude Workflow

### Typical Session

```
1. Claude starts: "Help me refactor this code"
   → Claude calls: graph_stats()
   ← "Graph has 1248 nodes, last updated 2h ago"

2. If stale: "The graph is outdated, rebuild it"
   → Claude calls: graph_rebuild()
   ← "Rebuilt: 1248 nodes, 3847 edges in 5.2s"

3. Validate: "Check if the graph is ready"
   → Claude calls: graph_validate()
   ← "Graph is valid, safe for queries"

4. Query: "Find password validation code"
   → Claude calls: semantic_search("password validation")
   ← Returns matched symbols with full context
```

### Manual Debugging

```
User: "Why is semantic search slow?"
→ Claude calls: graph_stats()
← "Graph: 1248 nodes, 45MB memory"
→ Claude calls: graph_validate()
← "Graph: valid, but 12 orphaned nodes"
→ Claude recommends: "Run graph_rebuild() to clean up"
```

---

## Error Handling

### Neo4j Down
```python
{
    "status": "error",
    "error": "Neo4j connection failed",
    "message": "Unable to connect to bolt://localhost:7687",
    "suggestion": "Start Neo4j: docker-compose up -d neo4j"
}
```

### Invalid Project Dir
```python
{
    "status": "error",
    "error": "Project directory not found",
    "project_dir": "/invalid/path",
    "suggestion": "Use an existing project directory"
}
```

### Graph Already Rebuilding
```python
{
    "status": "error",
    "error": "Graph rebuild in progress",
    "eta_seconds": 45,
    "suggestion": "Wait 45s or stop the current build"
}
```

---

## Success Criteria (Phase 1)

- [ ] All 4 tools implemented + tested
- [ ] All tools tested with Neo4j running and offline
- [ ] Claude can rebuild graph without CLI
- [ ] Graph validation helps identify issues
- [ ] Token estimates accurate within 10%
- [ ] Tools integrated into MCP entrypoint
- [ ] Documentation in tool docstrings

---

## Future Enhancements (Phase 2+)

- Incremental rebuild from git diff (use `apply_diff`)
- Selective symbol deletion
- Database snapshots/restore
- Export to GraphML/JSON for visualization
- Performance profiling (slowest queries, largest symbols)
- Compression strategies (deduplicate embeddings)
- Multi-database support (one per project)

---

## References

- `Neo4jClient` — `src/graph/neo4j_client.py`
- `GraphBuilder` — `src/graph/graph_builder.py`
- Existing tools — `src/mcp_server/tools/graph_tools.py`
- Services — `src/mcp_server/services.py`
