# MCP Server - Cheatsheet

**Quick reference for using SYT's 10 MCP tools.**

---

## Setup (One-Time)

### Install
```bash
git clone https://github.com/budagov-lab/save-my-tokens.git
cd save-my-tokens
python -m venv venv && source venv/bin/activate
pip install -e .
```

### Start Server
```bash
python run_mcp.py
```

### Claude Desktop Config
Edit `~/Library/Application\ Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "syt-graph": {
      "command": "python",
      "args": ["/absolute/path/to/save-my-tokens/run_mcp.py"]
    }
  }
}
```

Restart Claude Desktop. Done! 🎉

---

## The 10 Tools

### 1. `get_context` — Understand a symbol
```python
get_context(
    symbol_name: str,          # "validate_token"
    depth: int = 1,            # 1=direct, 2=transitive, 3=full
    include_callers: bool = False  # Show who calls this?
)
```
**Returns:** Symbol info + what it calls + who calls it + token estimate

**Example:**
```
Agent: "What does authenticate_user do?"
→ Returns: signature, docstring, 12 dependencies, 8 callers, 287 tokens
```

---

### 2. `get_subgraph` — Full dependency graph
```python
get_subgraph(
    symbol_name: str,
    depth: int = 2
)
```
**Returns:** All nodes/edges reachable from this symbol (DAG)

**Example:**
```
Agent: "Show me everything that process_data depends on"
→ Returns: 45 functions, 78 edges, transitive dependencies
```

---

### 3. `semantic_search` — Find by meaning
```python
semantic_search(
    query: str,                # "password validation"
    top_k: int = 5
)
```
**Returns:** Ranked list of matching symbols (by similarity score)

**Example:**
```
Agent: "Find password strength checking code"
→ Returns: [validate_password_strength (0.92), check_entropy (0.85), ...]
```

---

### 4. `validate_conflicts` — Check parallelization
```python
validate_conflicts(
    tasks: list[{
        "id": str,
        "target_symbols": list[str],      # What I modify
        "dependency_symbols": list[str]   # What I read
    }]
)
```
**Returns:** Conflicts detected + whether tasks can run in parallel

**Example:**
```
Agent: "Can I modify A and B at the same time?"
→ Returns: conflicts=[], parallel_feasible=true
```

---

### 5. `extract_contract` — Parse function signature
```python
extract_contract(
    symbol_name: str,
    file_path: str,
    source_code: str,
    class_name: str | None = None  # If method in class
)
```
**Returns:** Function contract (params, return type, exceptions, docstring)

**Example:**
```
Agent: "What's the contract for send_email?"
→ Returns: params=[recipient, subject, body], return_type=bool, raises=[SMTPError]
```

---

### 6. `compare_contracts` — Detect breaking changes
```python
compare_contracts(
    symbol_name: str,
    old_source: str,    # Original code
    new_source: str,    # Modified code
    class_name: str | None = None
)
```
**Returns:** Breaking changes + compatibility score (0-1)

**Example:**
```
Agent: "Is this new version compatible?"
→ Returns: is_compatible=false, breaking_changes=[
    {type: "RETURN_TYPE_CHANGED", severity: "HIGH", impact: "..."}
]
```

---

### 7. `parse_diff` — Analyze git changes
```python
parse_diff(
    diff_text: str  # Output of `git diff`
)
```
**Returns:** Changed files + line counts

**Example:**
```
Agent: "What files changed in this commit?"
→ Returns: [
    {file: "src/auth.py", status: "modified", added: 42, deleted: 8},
    {file: "tests/test_auth.py", status: "modified", added: 15}
]
```

---

### 8. `apply_diff` — Update graph from changes
```python
apply_diff(
    diff_text: str,
    repo_path: str  # Path to repository
)
```
**Returns:** Delta applied + updated symbols

**Example:**
```
Agent: "Update graph after renaming function X to Y"
→ Returns: {added: [Y], deleted: [X], modified: [], duration_ms: 42}
```

---

### 9. `schedule_tasks` — Build execution plan
```python
schedule_tasks(
    tasks: list[{
        "id": str,
        "target_symbols": list[str],
        "dependency_symbols": list[str]
    }]
)
```
**Returns:** Phases (sequential stages) with tasks per phase

**Example:**
```
Agent: "Schedule these 10 tasks optimally"
→ Returns: phases=[
    ["t1", "t2"],      # Phase 1: parallel
    ["t3", "t4", "t5"], # Phase 2: parallel
    ["t6"]             # Phase 3: sequential
]
```

---

### 10. `execute_tasks` — Run with parallelization
```python
execute_tasks(
    tasks: list[...],
    max_retries: int = 3,
    timeout_per_task: int = 30  # seconds
)
```
**Returns:** Per-task results + success rate

**Example:**
```
Agent: "Execute the plan"
→ Returns: {
    succeeded: 10,
    failed: 0,
    success_rate: 1.0,
    total_time_ms: 2400
}
```

---

## Common Workflows

### Workflow 1: Understand & Modify
```
1. get_context("function_name")     # Understand what it does
2. get_context("function_name", include_callers=true)  # Who depends on it?
3. compare_contracts(old, new)      # Will my change break anything?
4. [Modify code]
```

### Workflow 2: Parallelize Tasks
```
1. validate_conflicts(tasks)        # Can I do these in parallel?
2. schedule_tasks(tasks)            # Build optimal schedule
3. execute_tasks(schedule)          # Run with conflict detection
```

### Workflow 3: Code Search
```
1. semantic_search("password validation")  # Find by meaning
2. get_context(result[0]["symbol"])        # Get details
3. [Modify code]
```

### Workflow 4: Handle Git Changes
```
1. [User makes changes]
2. parse_diff(git_diff)             # What changed?
3. apply_diff(git_diff)             # Update graph
4. get_context("modified_function") # See impact
```

---

## Performance Tips

| Operation | Fast | Slow | Why |
|-----------|------|------|-----|
| `get_context` | depth=1 | depth=3 | Larger subgraph = more time |
| `semantic_search` | 5 results | 100 results | Ranking is expensive |
| `validate_conflicts` | 10 tasks | 1000 tasks | Graph traversal scales |
| `schedule_tasks` | 50 tasks | 10000 tasks | Topological sort is O(n) |
| `execute_tasks` | Few tasks | Many tasks | Execution is parallelized |

**Rule of thumb:**
- depth=1 for quick lookups
- depth=2 for understanding impact
- depth=3 for full analysis

---

## Error Handling

### "Symbol not found"
```python
result = get_context("nonexistent_function")
# Returns: {error: "Symbol 'nonexistent_function' not found", symbol: null}
```

### "Neo4j unavailable"
The server runs in "offline mode":
- In-memory graph (lost on restart)
- All tools still work (except full subgraph queries)
- To fix: Start Neo4j with `docker-compose up -d`

### "Timeout on large query"
```python
# Use smaller depth
get_context("large_codebase_function", depth=1)  # Instead of depth=3
```

---

## Token Budget Guide

**Estimate before passing to Claude:**

```python
context = get_context("validate_token")
estimate = context["token_estimate"]

if estimate < 1000:    # ✅ Safe
    pass_to_claude(context)
elif estimate < 4000:  # ⚠️ Caution
    # Use depth=1 instead
    context = get_context("validate_token", depth=1)
else:                  # ❌ Too large
    # Reduce scope or ask user
    pass
```

---

## Quick Examples

### Example: "Show me who calls process_data"
```python
result = get_context("process_data", include_callers=True)
print(f"Callers: {result['callers']}")
```

### Example: "Find all password-related code"
```python
results = semantic_search("password validation", top_k=10)
for r in results:
    print(f"{r['symbol']}: {r['similarity']:.2f}")
```

### Example: "Can I refactor these functions in parallel?"
```python
conflicts = validate_conflicts([
    {"id": "t1", "target_symbols": ["func_a"]},
    {"id": "t2", "target_symbols": ["func_b"]}
])
print(f"Parallel safe: {conflicts['parallel_feasible']}")
```

### Example: "What breaking changes would this cause?"
```python
comparison = compare_contracts("send_email", old_code, new_code)
if not comparison["is_compatible"]:
    for change in comparison["breaking_changes"]:
        print(f"⚠️  {change['impact']}")
```

---

## One-Liner Help

```
Need to...                              Use tool...
─────────────────────────────────────────────────────────────
Understand a function                   get_context()
See full dependencies                   get_subgraph()
Find code by meaning                    semantic_search()
Check if parallel-safe                  validate_conflicts()
See function contract                   extract_contract()
Detect breaking changes                 compare_contracts()
Analyze git commit                      parse_diff()
Update graph from changes               apply_diff()
Optimize task order                     schedule_tasks()
Execute tasks safely                    execute_tasks()
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Server not connecting" | Verify: `python run_mcp.py` starts without errors |
| "Tool not found" | Restart Claude Desktop after config edit |
| "Queries timing out" | Use `depth=1` instead of `depth=3` |
| "Neo4j errors" | Run `docker-compose up -d` to start Neo4j |
| "Memory growing" | Restart server: `python run_mcp.py` |

---

## Full Documentation

- **[Quick Start](MCP_QUICK_START.md)** — 10-minute setup
- **[Examples](MCP_EXAMPLES.md)** — 6 real-world scenarios
- **[Architecture](FEATURE4_SCHEDULING_GUIDE.md)** — Deep technical dive

---

**Ready to use?** Start with `python run_mcp.py` and ask Claude a question! 🚀
