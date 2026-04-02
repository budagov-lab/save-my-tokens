# 🚀 MCP Setup Instructions for Claude

This document tells Claude how to set up and use save-my-tokens (SMT) MCP in your project.

## What This Is

**save-my-tokens (SMT)** is an MCP server that gives you access to 10 powerful tools for understanding code:

- **Graph queries** (get_context, get_subgraph, semantic_search)
- **Conflict detection** (validate_conflicts)
- **Contract analysis** (extract_contract, compare_contracts)
- **Git integration** (parse_diff, apply_diff)
- **Task scheduling** (schedule_tasks, execute_tasks)

**Why it matters:** Instead of reading entire files (5000+ tokens), you get minimal context (287 tokens avg). That's 11x more token budget for solving problems.

---

## When You See This for the First Time

Claude will detect you're in a save-my-tokens project and ask:

```
I detected that this project needs MCP configuration. Would you like me to:
- Add MCP server to Claude Code settings
- Index your code into Neo4j
- Enable 10 MCP tools

This takes 2-3 minutes. Should I proceed?
```

**You should say: "Yes"**

Claude will then:
1. Check prerequisites (Neo4j, Python, packages)
2. Update ~/.claude/settings.json with MCP config
3. Build the code graph (if needed)
4. Verify everything works
5. Show you available tools

---

## After Setup: Using MCP Tools

Once configured, Claude can use these tools natively:

### 1. Understand Code
```
User: "What does validate_token() do?"

Claude calls: get_context("validate_token", include_callers=true)
Result: 287 tokens with definition + 8 callers + dependencies
Claude: "It validates JWT tokens. Called from 8 places. Here's what depends on it..."
```

### 2. Find Related Code
```
User: "Show me all password validation logic"

Claude calls: semantic_search("password validation")
Result: Ranked list of matching functions
Claude: "Found 5 functions related to password validation..."
```

### 3. Refactor Safely
```
User: "Can I change the signature of process_data()?"

Claude calls: 
  - extract_contract(old_code)
  - compare_contracts(old, new)
Result: breaking_changes=[], is_compatible=true
Claude: "Yes, your changes are compatible with all callers."
```

### 4. Parallelize Tasks
```
User: "Can these changes run in parallel?"

Claude calls: validate_conflicts([task1, task2, task3])
Result: no_conflicts=true, safe_parallel=true
Claude: "All 3 can run simultaneously. No conflicts."
```

---

## Available MCP Tools

### Graph Queries
| Tool | What It Does | Example |
|------|-------------|---------|
| `get_context(symbol, depth=1, include_callers=true)` | Get a function definition + dependencies + who calls it | `get_context("login_user", include_callers=true)` |
| `get_subgraph(symbol, depth=2)` | Full dependency tree starting from a symbol | `get_subgraph("authenticate", depth=3)` |
| `semantic_search(query, top_k=5)` | Find code by meaning (not just name) | `semantic_search("user authentication flow")` |
| `validate_conflicts(tasks)` | Check if code changes conflict | `validate_conflicts([{"id":"task1","target_symbols":["auth.py"]}])` |

### Contracts & Breaking Changes
| Tool | What It Does | Example |
|------|-------------|---------|
| `extract_contract(code)` | Parse function signature, docstring, types | `extract_contract(validate_token_code)` |
| `compare_contracts(old_code, new_code)` | Detect breaking changes | `compare_contracts(old_validate, new_validate)` |

### Git & Incremental Updates
| Tool | What It Does | Example |
|------|-------------|---------|
| `parse_diff()` | Analyze git diff to find changed symbols | `parse_diff()` → returns changed files |
| `apply_diff()` | Update graph from git commits | `apply_diff()` → syncs Neo4j with repo |

### Task Scheduling
| Tool | What It Does | Example |
|------|-------------|---------|
| `schedule_tasks(tasks)` | Build execution plan with auto-parallelization | `schedule_tasks([task1, task2, task3])` |
| `execute_tasks(plan)` | Run tasks with dependency resolution & retries | `execute_tasks(execution_plan)` |

---

## Important Rules for Claude

**RULE 1: Always query before assuming**
```
❌ WRONG:
Claude: "I'll refactor validate_token() in auth.py"
(Doesn't check who calls it)

✅ RIGHT:
Claude calls: get_context("validate_token", include_callers=true)
Claude: "validate_token() is called from 8 places. Let me check compatibility..."
```

**RULE 2: Check compatibility before changing signatures**
```
❌ WRONG:
Claude: "I'll change the function signature"
(Changes it, breaks everything)

✅ RIGHT:
Claude calls: compare_contracts(old_code, new_code)
Result: breaking_changes = ["param_removed: api_key"]
Claude: "Your change removes api_key parameter. This breaks 3 callers. Let me fix those too..."
```

**RULE 3: Use validate_conflicts before parallelizing**
```
❌ WRONG:
Claude: "Let's refactor auth.py AND update docs in parallel"
(They might conflict)

✅ RIGHT:
Claude calls: validate_conflicts([auth_refactor, docs_update])
Result: no_conflicts=true
Claude: "These can run in parallel safely."
```

**RULE 4: Always estimate tokens**
```
❌ WRONG:
Claude: "I'll get the full subgraph"
(Uses 10,000+ tokens)

✅ RIGHT:
Claude calls: get_context(symbol, depth=1)
Result: token_estimate=287
Claude: "I have the context in 287 tokens. That leaves plenty budget."
```

---

## Graph Status

The code graph contains:

| Type | Count | What It Tracks |
|------|-------|----------------|
| Functions | 1000+ | All function definitions, signatures, calls |
| Classes | 200+ | Class definitions, inheritance, methods |
| Files | 50+ | File structure, imports, dependencies |
| Imports | 3000+ | What imports what, circular dependencies |
| Calls | 5000+ | Which function calls which function |

To check graph status:
```bash
python build_graph.py --check
```

---

## Troubleshooting

### "MCP tools not available"
1. Check: `python build_graph.py --check` (should show nodes > 100)
2. Check: Neo4j running on localhost:7474
3. Check: `~/.claude/settings.json` has mcpServers.smt config

### "Graph is empty"
```bash
python build_graph.py  # Build/rebuild
```

### "Neo4j not running"
```bash
docker-compose up -d neo4j
curl http://localhost:7474  # Should return JSON
```

### "Python packages missing"
```bash
pip install -e .
```

---

## When to Use Each Tool

### Use `get_context()` when:
- You need to understand what a function does
- You need to know who calls it
- You're about to modify it
- You need to estimate token budget

### Use `semantic_search()` when:
- You need to find "all auth-related code" (not a specific function name)
- You're searching by functionality, not name
- You want the most relevant matches ranked

### Use `validate_conflicts()` when:
- You have multiple changes to make
- You want to parallelize work
- You need to know if changes are safe together

### Use `extract_contract()` + `compare_contracts()` when:
- You're refactoring function signatures
- You're changing a public API
- You need to detect what will break

---

## Remember

This MCP system exists to **save tokens and make you smarter about code changes**.

Every time you:
- Query instead of read → Save 4700 tokens
- Check conflicts instead of guessing → Prevent bugs
- Use semantic search instead of grep → Find relevant code faster

You're getting more intelligence per token spent.

The graph is your source of truth. Use it.
