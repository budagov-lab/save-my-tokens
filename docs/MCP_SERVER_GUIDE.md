# MCP Server Guide

**Model Context Protocol Server for SYT Graph API**

This document explains how the MCP server works, how to use it with Claude, and how to extend it.

---

## Overview

The MCP server replaces the REST API with a **stateful, agent-first interface**. Instead of agents making HTTP requests to stateless endpoints, they interact with the server via **native MCP tools**.

### Why MCP?

```
REST API (stateless):
Agent → POST /api/context/foo → Parse → Build graph → Return JSON → Discard graph
↑ Graph reloaded every request, HTTP overhead, inefficient

MCP Server (stateful):
Agent ⟷ MCP Server (persistent) → Graph loaded once → Stream responses
↑ Graph stays in memory, zero HTTP overhead, efficient
```

---

## Architecture

### Lifespan Management

```python
@asynccontextmanager
async def lifespan(app) -> ServiceContainer:
    # Startup: Build all singletons
    container = build_services()  # SymbolIndex, QueryService, Neo4j, etc.
    try:
        yield container  # Available to all tools
    finally:
        # Shutdown: Teardown resources
        await teardown_services(container)
```

**Key:** All services are built **once** at startup and shared across all tool calls.

### Service Injection

Each tool receives services via **context injection**:

```python
@mcp.tool()
async def get_context(symbol: str, depth: int = 1, ctx: Context = None) -> dict:
    """ctx parameter is stripped from MCP arguments and injected by framework."""
    services: ServiceContainer = ctx.request_context.lifespan_context
    return services.query_service.get_context(symbol, depth=depth)
```

**Why this pattern?**
- Services are singletons (built once, not per-tool)
- No circular imports (tools import from `_app.py`, not the other way)
- Clean separation of concerns (tools are thin wrappers)

### Transport

The server uses **stdio** (standard input/output) for communication:

```bash
$ python run_mcp.py
# Server listens on stdin, writes responses to stdout
# Perfect for subprocess model (Claude Desktop, Claude Code)
```

---

## The 10 MCP Tools

### Graph Queries

#### `get_context(symbol, depth=1, include_callers=False) -> dict`

Get minimal context for a symbol.

```python
result = tool.get_context("validate_token", depth=2, include_callers=True)
# {
#   "symbol": {"name": "validate_token", "file": "src/auth.py", ...},
#   "dependencies": [<symbols this calls>],
#   "callers": [<symbols that call this>],
#   "token_estimate": 287
# }
```

#### `get_subgraph(symbol, depth=2) -> dict`

Full dependency graph (DAG) for a symbol.

```python
result = tool.get_subgraph("process_data", depth=2)
# {
#   "root_symbol": "process_data",
#   "nodes": [...],  # All symbols in the subgraph
#   "edges": [...]   # Dependencies as edges
# }
```

#### `semantic_search(query, top_k=5) -> dict`

Find code by meaning or name.

```python
result = tool.semantic_search("password validation logic", top_k=5)
# {
#   "query": "password validation logic",
#   "results": [
#     {"symbol_name": "validate_password", "similarity_score": 0.92, ...},
#     {"symbol_name": "check_strength", "similarity_score": 0.88, ...},
#     ...
#   ]
# }
```

#### `validate_conflicts(tasks) -> dict`

Detect parallelization conflicts before execution.

```python
result = tool.validate_conflicts([
    {"id": "t1", "target_symbols": ["auth_service"]},
    {"id": "t2", "target_symbols": ["auth_service"]},  # CONFLICT!
])
# {
#   "parallel_feasible": False,
#   "conflicts": [{"tasks": ["t1", "t2"], "reason": "Both modify auth_service"}],
#   "recommendation": "Serialize t1 → t2"
# }
```

### Contract & Breaking Changes

#### `extract_contract(symbol_name, file_path, source_code, class_name=None) -> dict`

Parse function signature, docstring, type hints, pre/postconditions.

```python
result = tool.extract_contract(
    symbol_name="validate_token",
    file_path="src/auth.py",
    source_code=<full_source>,
)
# {
#   "symbol_name": "validate_token",
#   "signature": {
#     "parameters": [
#       {"name": "token", "type_hint": "str", "is_optional": False}
#     ],
#     "return_type": "bool",
#     "raises": ["ValueError"]
#   },
#   "docstring": "...",
#   "preconditions": ["token must be non-empty"],
#   "postconditions": ["returns True iff token is valid"]
# }
```

#### `compare_contracts(symbol_name, old_source, new_source, class_name=None) -> dict`

Detect breaking changes.

```python
result = tool.compare_contracts(
    symbol_name="validate_token",
    old_source=<old_code>,
    new_source=<new_code>,
)
# {
#   "symbol": "validate_token",
#   "is_compatible": False,
#   "compatibility_score": 0.5,
#   "breaking_changes": [
#     {
#       "type": "PARAMETER_REMOVED",
#       "severity": "HIGH",
#       "impact": "Parameters removed: allow_expired"
#     }
#   ]
# }
```

### Incremental Updates

#### `parse_diff(diff_text) -> dict`

Parse git diff to identify changed files.

```python
result = tool.parse_diff(<git_diff_output>)
# {
#   "total_files_changed": 3,
#   "total_lines_added": 42,
#   "total_lines_deleted": 15,
#   "files": [
#     {"file_path": "src/auth.py", "status": "M", "added_lines": 10, "deleted_lines": 5},
#     {"file_path": "src/routes.py", "status": "M", "added_lines": 32, "deleted_lines": 10},
#   ]
# }
```

#### `apply_diff(file, added_symbols=[], deleted_symbol_names=[], modified_symbols=[]) -> dict`

Update graph from symbol changes (requires Neo4j).

```python
result = tool.apply_diff(
    file="src/auth.py",
    added_symbols=[
        {"name": "new_validate", "type": "function", "file": "src/auth.py", "line": 50, "column": 0}
    ],
    deleted_symbol_names=["old_validate"],
    modified_symbols=[
        {"name": "validate_token", "type": "function", "file": "src/auth.py", "line": 20, "column": 0}
    ]
)
# {
#   "success": True,
#   "file": "src/auth.py",
#   "duration_ms": 15,
#   "added": 1,
#   "deleted": 1,
#   "modified": 1
# }
```

### Task Scheduling

#### `schedule_tasks(tasks) -> dict`

Build execution plan with parallelization.

```python
result = tool.schedule_tasks([
    {"id": "t1", "description": "auth update", "target_symbols": ["validate_token"], "dependency_symbols": []},
    {"id": "t2", "description": "route update", "target_symbols": ["login_route"], "dependency_symbols": ["validate_token"]},
    {"id": "t3", "description": "logging", "target_symbols": ["log_access"], "dependency_symbols": []},
])
# {
#   "total_tasks": 3,
#   "num_phases": 2,
#   "phases": [
#     {"phase_number": 0, "task_ids": ["t1", "t3"], "can_parallel": True},
#     {"phase_number": 1, "task_ids": ["t2"], "can_parallel": False},
#   ],
#   "parallelizable_pairs": 1
# }
```

#### `execute_tasks(tasks, timeout_seconds=30.0) -> dict`

Schedule and execute tasks with dependency resolution.

```python
result = tool.execute_tasks(
    tasks=[...],
    timeout_seconds=30.0
)
# {
#   "status": "SUCCESS",
#   "completed_tasks": 3,
#   "failed_tasks": 0,
#   "total_time_seconds": 2.45,
#   "task_results": [
#     {"task_id": "t1", "status": "completed", "success": True, "attempts": 1, "total_time": 0.50},
#     {"task_id": "t2", "status": "completed", "success": True, "attempts": 1, "total_time": 1.20},
#     {"task_id": "t3", "status": "completed", "success": True, "attempts": 1, "total_time": 0.75},
#   ]
# }
```

---

## Error Handling

Tools raise Python exceptions → MCP converts to `isError=True` responses.

```python
# Tool code:
@mcp.tool()
async def get_context(symbol: str, ctx: Context) -> dict:
    result = services.query_service.get_context(symbol)
    if "error" in result:
        raise ValueError(result["error"])  # ← Becomes isError response
    return result

# Agent sees:
# {
#   "isError": True,
#   "content": [{"type": "text", "text": "Symbol 'foo' not found"}]
# }
```

### Common Errors

| Tool | Error | When | Fix |
|------|-------|------|-----|
| `get_context` | `ValueError: Symbol not found` | Symbol doesn't exist in graph | Use `semantic_search` to find alternatives |
| `apply_diff` | `RuntimeError: Neo4j unavailable` | Neo4j offline | Start Neo4j or use offline mode |
| `schedule_tasks` | `ValueError: Circular task dependencies` | Tasks form a cycle | Check task `dependency_symbols` |
| `execute_tasks` | `RuntimeError: Task timeout` | Task exceeds 30s | Increase `timeout_seconds` or optimize task |

---

## Service Container

The `ServiceContainer` holds all singletons:

```python
@dataclass
class ServiceContainer:
    symbol_index: SymbolIndex              # In-memory symbol cache
    query_service: QueryService            # Graph queries
    updater: IncrementalSymbolUpdater      # Delta application
    diff_parser: DiffParser                # Git diff parsing
    scheduler: TaskScheduler               # DAG scheduling
    execution_engine: ParallelExecutionEngine  # Task execution
    neo4j_client: Optional[Neo4jClient]    # Live DB connection (or None)
    embedding_service: Optional[EmbeddingService]  # Embeddings (or None)
```

### Offline Mode

If Neo4j or embeddings are unavailable:

- `symbol_index` — always available (in-memory)
- `neo4j_client` — `None` (queries fall back to in-memory)
- `embedding_service` — `None` (search falls back to substring matching)
- `updater` — fails gracefully if Neo4j required

This allows the server to start and serve basic queries even without optional services.

---

## Extending the Server

### Add a New MCP Tool

1. **Create a new file** in `src/mcp_server/tools/`:

```python
# src/mcp_server/tools/my_tools.py
from mcp.server.fastmcp import Context
from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer

@mcp.tool()
async def my_new_tool(param: str, ctx: Context = None) -> dict:
    """Docstring becomes the MCP tool description."""
    services: ServiceContainer = ctx.request_context.lifespan_context
    # Use services to implement your logic
    return {"result": "..."}
```

2. **Import it in** `src/mcp_server/entrypoint.py`:

```python
from src.mcp_server.tools import my_tools  # noqa: F401
```

3. **Test it:**

```bash
python -m pytest tests/mcp/ -v
```

### Add a New Service

1. **Create service class** in `src/my_service/`:

```python
class MyService:
    def __init__(self, symbol_index):
        self.symbol_index = symbol_index
    
    def do_something(self, param):
        # Implement logic
        return result
```

2. **Register in ServiceContainer**:

```python
# src/mcp_server/services.py
@dataclass
class ServiceContainer:
    # ... existing fields ...
    my_service: MyService

def build_services() -> ServiceContainer:
    # ... existing services ...
    my_service = MyService(symbol_index)
    return ServiceContainer(
        # ... existing params ...
        my_service=my_service,
    )
```

3. **Use in tools:**

```python
@mcp.tool()
async def my_tool(ctx: Context = None) -> dict:
    services: ServiceContainer = ctx.request_context.lifespan_context
    result = services.my_service.do_something(param)
    return result
```

---

## Claude Desktop Integration

### Configuration

Create or edit `~/.config/Claude/claude_desktop_config.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "syt-graph": {
      "command": "python",
      "args": ["/path/to/save-my-tokens/run_mcp.py"]
    }
  }
}
```

### Verify It Works

1. Launch Claude Desktop
2. Open Developer Tools (⌘+Shift+I on Mac, Ctrl+Shift+I on Windows)
3. Look for "Tools available" section
4. Should list all 10 MCP tools from SYT

### Agent Example

```
You: Help me refactor the authentication system in my repo.

Claude: I'll help you refactor the authentication system. Let me start by 
exploring the current implementation...

[Claude calls: get_context("validate_token", depth=2, include_callers=true)]

I can see validate_token is used in 3 places: login_route, api_middleware, 
and refresh_token. Here's my refactoring plan:

1. Extract a validate_token_internal() helper (reusable logic)
2. Update login_route to use the new helper
3. Update refresh_token similarly
4. Keep api_middleware as-is (no breaking changes)

Let me check for breaking changes first...

[Claude calls: compare_contracts("validate_token", old_source=..., new_source=...)]

Good news! The new signature is backward compatible (added optional parameter).

Now let's plan the parallelization...

[Claude calls: schedule_tasks(tasks=[...t1, t2, t3...])]

Tasks can be parallelized in 2 phases:
- Phase 1: Extract helper, update middleware (can run in parallel)
- Phase 2: Update route handlers (depends on Phase 1)

Should I proceed with the refactoring?
```

---

## Monitoring & Debugging

### Logs

The server logs to `logs/syt.log` by default (configured in `src/config.py`).

```bash
tail -f logs/syt.log  # Watch for errors/warnings
```

### Offline Testing

Test MCP tools without connecting to Claude:

```bash
python run_mcp.py  # Starts server
# In another terminal:
curl -X POST http://localhost:8000/api/tools/get_context -d '{"symbol": "foo"}'
```

(This uses a test client—not a real integration, but useful for debugging)

---

## Performance Tuning

### Memory

The `SymbolIndex` holds all symbols in memory. On large repos (200K+ LOC):

- Memory: ~500MB for typical Python/JS codebase
- Load time: 2-5 seconds
- Query time: <1ms (O(1) lookups)

### Neo4j

If using Neo4j:
- Create indexes for fast lookups: `CREATE INDEX ON :Symbol(name)`
- Monitor slow queries: Check Neo4j logs for query >100ms
- Batch large updates: `apply_diff` groups changes transactionally

### Parallelization

Max parallelism controlled by `create_default_execution_engine(max_workers=4)`. Increase for CPU-bound work:

```python
engine = create_default_execution_engine(max_workers=8)  # Up to 8 parallel tasks
```

---

## FAQ

**Q: Why MCP instead of REST?**  
A: MCP provides stateful sessions (graph stays loaded), streaming responses, and native agent integration. REST is stateless and HTTP-heavy.

**Q: Can I use SYT without Neo4j?**  
A: Yes. Symbol queries use in-memory index. Graph queries fall back to in-memory. `apply_diff` requires Neo4j (or fails gracefully).

**Q: How do I add support for a new language?**  
A: Add a new parser in `src/parsers/{language}_parser.py`, register in `UnifiedParser`, and wire it up in `GraphBuilder`.

**Q: Can multiple agents use the same MCP server?**  
A: Yes, if connected via network (would need SSE/HTTP transport instead of stdio). Stdio is for single-agent per process.

**Q: How do I optimize query latency?**  
A: Profile with `src/performance/optimizer.py`. Common bottleneck: Neo4j queries >100ms. Add indexes.

---

## References

- [MCP Specification](https://modelcontextprotocol.io/)
- [ServiceContainer Design](../src/mcp_server/services.py)
- [MCP Tools Implementation](../src/mcp_server/tools/)
- [Task Scheduling](../docs/FEATURE4_SCHEDULING_GUIDE.md)
