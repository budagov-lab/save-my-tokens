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
    """Deprecated - consolidated into mcp-guide.md skill."""
    # This function is no longer used - all content moved to mcp-guide.md skill
    return True
    try:
        claude_dir = project_root / '.claude'
        claude_dir.mkdir(exist_ok=True)

        instructions = """# MCP Setup Instructions for Claude & Agents

## QUICK START: Understanding This Project

You're working with **save-my-tokens** — a semantic code graph system that teaches Claude (and agents) how to understand code **efficiently** instead of reading entire files.

### The Problem We Solve
- Reading a 1000-line file = 5000 tokens wasted
- 90% of that file is irrelevant to your task
- You run out of token budget before solving the real problem

### The Solution: MCP Tools
Instead of reading files, ask smart questions:
- "What does function X do?" → Use `get_context()`
- "Find code that does X" → Use `semantic_search()`
- "Is my change safe?" → Use `validate_conflicts()`

---

## Available MCP Tools (13 Total)

### Graph Queries (Code Understanding)
| Tool | Use When | Cost | Saves |
|------|----------|------|-------|
| `get_context(symbol)` | Understanding a function | 287 tokens | 1000+ |
| `get_subgraph(symbol)` | Full dependency tree | 500 tokens | 3000+ |
| `semantic_search(query)` | Finding related code | 450 tokens | 2500+ |
| `validate_conflicts(tasks)` | Checking if changes conflict | 200 tokens | Prevents bugs |

### Database Management (Phase 2)
| Tool | Use When | Cost |
|------|----------|------|
| `graph_stats()` | Check if graph needs updating | 150 tokens |
| `graph_rebuild()` | Full graph reconstruction | 2000 tokens |
| `graph_diff_rebuild()` | Fast incremental update | 800 tokens |
| `graph_validate()` | Check graph integrity | 200 tokens |
| `graph_clear_symbol()` | Remove single symbol | 100 tokens |
| `graph_backup()` | Export to JSON | 300 tokens |
| `graph_export()` | Export as GraphML | 300 tokens |

### Contracts & Breaking Changes
| Tool | Use When | Cost |
|------|----------|------|
| `extract_contract(code)` | Parse function signatures | 200 tokens |
| `compare_contracts(old, new)` | Detect breaking changes | 300 tokens |

### Git & Updates
| Tool | Use When | Cost |
|------|----------|------|
| `parse_diff()` | Analyze git changes | 250 tokens |
| `apply_diff()` | Update graph from commits | 400 tokens |

### Task Scheduling
| Tool | Use When | Cost |
|------|----------|------|
| `schedule_tasks(tasks)` | Auto-parallelize work | 300 tokens |
| `execute_tasks(plan)` | Run with dependency resolution | 500 tokens |

---

## Decision Tree: When to Use What

```
User: "Show me src/api/server.py"
├─ File > 500 LOC?
│  ├─ YES → Use get_context() or semantic_search()
│  │         (Save 4000+ tokens)
│  └─ NO → Read file directly
│
User: "What does validate_email() do?"
├─ Need definition + callers?
│  └─ YES → Use get_context('validate_email', include_callers=true)
│           (Cost: 287 tokens vs 1000+ for reading related files)
│
User: "Find all password validation logic"
├─ Need multiple related functions?
│  └─ YES → Use semantic_search('password validation')
│           (Cost: 450 tokens vs 2500+ for grep + reading)
│
User: "Can I change this function signature?"
├─ Need to find all callers and check compatibility?
│  ├─ Step 1: get_context('function', include_callers=true)
│  ├─ Step 2: compare_contracts(old_sig, new_sig)
│  └─ Result: Know exactly what breaks before changing
│
User: "Update graph after code changes"
├─ Small changes? → graph_diff_rebuild() (fast, 800 tokens)
└─ Major changes? → graph_rebuild() (full, 2000 tokens)
```

---

## Agent Learning Path

New agents start with zero context. Here's how they learn:

### Level 1: Discovery (First Contact)
Agent reads this file and learns:
- 20 tools exist (4 query + 6 graph mgmt + 2 contracts + 2 git + 2 scheduling + 4 init/stats)
- Each tool solves a specific problem
- MCP tools save 80-90% of tokens vs file reads

### Level 2: Pattern Recognition
Agent learns when to use each tool:
```python
# DON'T: Read entire file
with open('src/api/server.py') as f:
    content = f.read()  # 5000 tokens, 90% waste

# DO: Use get_context()
result = get_context('validate_request', include_callers=true)
# 287 tokens, 100% relevant
```

### Level 3: Tool Chaining
Agent learns to combine tools:
```
Task: Refactor function X safely
├─ Step 1: semantic_search('function X context')  # Find related code
├─ Step 2: get_context('function X')               # Deep dive
├─ Step 3: compare_contracts(old_sig, new_sig)     # Check safety
└─ Step 4: validate_conflicts([change_task])       # Check parallelizable
```

### Level 4: Graph Maintenance
Agent learns when to rebuild graph:
```
At session start:
├─ Call graph_stats() → Check node_count, last_update
├─ If > 1 hour old → Call graph_diff_rebuild()
├─ If broken → Call graph_validate() → Fix with graph_rebuild()
```

---

## Token Budget Optimization

This is critical: **Tokens are your problem-solving budget.**

| Operation | Tokens | % of Budget | Better Way |
|-----------|--------|------------|-----------|
| Read 1000-line file | 5000 | 50% | get_context() = 287 tokens |
| Grep + read 5 files | 8000 | 80% | semantic_search() = 450 tokens |
| Read entire codebase | 15000+ | 150% | ❌ IMPOSSIBLE | Use MCP tools |
| graph_rebuild() | 2000 | 20% | ✓ Worth it for fresh start |
| get_context() | 287 | 3% | ✓ Use for every question |

**Rule:** "If you can solve it with MCP, do it. Save tokens for harder problems."

---

## Troubleshooting Guide

### "MCP tools not available"
```bash
# Step 1: Check if MCP server running
python run.py

# Step 2: Check .mcp.json exists
cat .mcp.json

# Step 3: Restart Claude Code
```

### "Graph is empty (0 nodes)"
```bash
# Build from source
python build_graph.py

# Or in Claude:
graph_rebuild(project_dir='./src', clear_first=true)
```

### "Graph is stale (1 hour old)"
```bash
# Fast incremental update
graph_diff_rebuild(commit_range='HEAD~10..HEAD')

# Or full rebuild
graph_rebuild(clear_first=true)
```

### "Neo4j connection failed"
```bash
# Start Neo4j
docker-compose up -d neo4j

# Wait 10s then verify
curl http://localhost:7474
```

### "Symbol not found in graph"
```python
# DON'T: Ask agent to Read() the file
# DO: Use semantic_search()
result = semantic_search('what you\\'re looking for')
# Will find similar functions even if exact name doesn't exist
```

---

## For New Agents: What NOT to Do

### ❌ DON'T
```python
# Read large files
file_content = Read("src/api/large_file.py")  # 5000 tokens wasted

# Grep entire codebase
results = Grep(".*pattern.*")  # Returns 1000+ matches, still need to read

# Assume code structure
# "This function probably calls X"  # Wrong without checking
```

### ✅ DO
```python
# Use MCP tools
context = get_context("function_name", include_callers=true)

# Chain tools
search_results = semantic_search("what you need")
for result in search_results[:3]:
    details = get_context(result['symbol'])

# Validate before assuming
conflicts = validate_conflicts([your_changes])
if not conflicts['no_conflicts']:
    # See exactly what conflicts exist
    print(conflicts['details'])
```

---

## Real Examples

### Example 1: "What does validate_email() do?"
```
❌ OLD (Bad): Read entire user validation module (3000 tokens)
✅ NEW (Good):
  get_context('validate_email', include_callers=true)
  Cost: 287 tokens
  Result: Definition + 15 callers + 3 dependencies
```

### Example 2: "Find all password handling code"
```
❌ OLD (Bad): grep -r "password" + read 12 files (8000 tokens)
✅ NEW (Good):
  semantic_search('password validation and hashing')
  Cost: 450 tokens
  Result: 8 ranked matching functions with context
```

### Example 3: "Can I change API response format?"
```
❌ OLD (Bad): Read API file (2000) + grep callers (3000) = 5000 tokens
✅ NEW (Good):
  get_context('api_response', include_callers=true)  # 287
  compare_contracts(old_format, new_format)          # 300
  validate_conflicts([change_task])                  # 200
  Total: 787 tokens
```

---

## Success Metrics

You're using MCP correctly when:
- [ ] First instinct is "use MCP" not "read file"
- [ ] Average tokens per session < 8000 (vs 12000+ without MCP)
- [ ] Can explain what code does without reading it
- [ ] Can find related code in 1-2 searches
- [ ] Know exactly what breaks before changing it
- [ ] Rebuild graph only when needed (not every session)

---

## References

- **Full Tool Docs**: See entrypoint.py (tool implementations)
- **Graph Schema**: src/graph/node_types.py
- **Token Measurements**: Phase 1 evaluation results
- **Neo4j Query Language**: https://neo4j.com/docs/cypher-manual/
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


def create_mcp_guide_skill(project_root: Path) -> bool:
    """Create .claude/skills/mcp-guide/SKILL.md - comprehensive MCP learning guide."""
    print("  Creating .claude/skills/mcp-guide/SKILL.md...", end=" ", flush=True)
    try:
        skill_dir = project_root / '.claude' / 'skills' / 'mcp-guide'
        skill_dir.mkdir(parents=True, exist_ok=True)

        guide = """---
name: mcp-guide
description: Learn how to use 20 MCP tools efficiently instead of reading/grepping large files. Decision tree, learning path, token savings breakdown, and agent checklist.
---

# MCP Learning Guide: Use Smart Tools Instead of Reading Files

## Purpose

This file teaches new Claude agents (and humans) how to work efficiently with this codebase by using **20 MCP tools** instead of reading/grepping files.

**Target audience:** Agents starting with zero context of the project.

**Available tools:** 20 specialized tools for code understanding, graph management, contracts, git integration, and task scheduling.

---

## Core Principle: Tool Choice

Every task has a tool. Choose wisely (20 tools total):

| You Want To... | Use This | NOT This | Savings |
|---|---|---|---|
| Understand what a function does | `get_context()` | `Read()` entire file | 76% |
| Find code by meaning | `semantic_search()` | `Grep()` + read files | 85% |
| Check if change is safe | `compare_contracts()` | Read all callers | 90% |
| Update after git commit | `graph_diff_rebuild()` | `graph_rebuild()` | 60% |
| Check graph health | `graph_stats()` + `graph_validate()` | Manual inspection | 100% |
| Parallelize tasks safely | `validate_conflicts()` | Manual analysis | 95% |
| Export/backup graph | `graph_backup()` or `graph_export()` | Manual export | 100% |

---

## Learning Path (4 Levels)

### Level 1: Know the Tools Exist

You have access to **20 MCP tools** organized by category:

**Code Understanding (4 tools):**
- `get_context(symbol)` - Understand a function/class + callers + dependencies
- `get_subgraph(symbol)` - Full dependency tree up to N hops
- `semantic_search(query)` - Find code by meaning (not just names)
- `validate_conflicts(tasks)` - Check if changes can run in parallel

**Graph Management (6 tools - Phase 2):**
- `graph_init()` - Initialize graph and create indexes
- `graph_stats()` - Is graph fresh? Get node/edge counts
- `graph_rebuild()` - Full reconstruction from source
- `graph_diff_rebuild()` - Fast incremental update from git
- `graph_validate()` - Check graph integrity and consistency
- `graph_clear_symbol()` - Remove single symbol + edges
- `graph_backup()` - Export graph to JSON
- `graph_restore()` - Import graph from JSON
- `graph_export()` - Export as JSON or GraphML
- `graph_reindex()` - Rebuild indexes for performance

**Contracts & Breaking Changes (2 tools):**
- `extract_contract(code)` - Parse function signatures and types
- `compare_contracts(old, new)` - Detect breaking changes before refactoring

**Git & Incremental Updates (2 tools):**
- `parse_diff()` - Analyze git diff output
- `apply_diff()` - Sync graph with git commits

**Task Scheduling & Execution (2 tools):**
- `schedule_tasks(tasks)` - Build execution plan with parallelization
- `execute_tasks(plan)` - Run tasks respecting dependencies

### Level 2: Learn When to Use Each

**Scenario: Understand a function**
```
Agent thinking:
  "User asked: 'What does validate_email() do?'"

  Option A (Bad): Read file containing validate_email
    - Cost: 1200 tokens
    - Time: Need to locate file, parse it
    - Irrelevant content: 90% of file

  Option B (Good): get_context('validate_email', include_callers=true)
    - Cost: 287 tokens
    - Time: Instant
    - Relevant content: 100%

  Decision: Use get_context()
```

**Scenario: Find code that does X**
```
Agent thinking:
  "User asked: 'Show me all password handling code'"

  Option A (Bad): grep -r "password" + read matching files
    - Cost: 3000+ tokens
    - Misses semantic variations (hashing, encryption, etc.)
    - Many false positives

  Option B (Good): semantic_search('password validation and hashing')
    - Cost: 450 tokens
    - Finds semantic matches (understands meaning)
    - Ranked by relevance

  Decision: Use semantic_search()
```

**Scenario: Before refactoring**
```
Agent thinking:
  "User asked: 'Can I change process_data() signature?'"

  Do not assume. Never assume. Check first.

  Step 1: get_context('process_data', include_callers=true)
    Cost: 287 tokens
    Result: Definition + all callers

  Step 2: compare_contracts(old_signature, new_signature)
    Cost: 300 tokens
    Result: Exact list of breaking changes

  Decision: Only refactor if no breaking changes (or user accepts them)
```

### Level 3: Chain Tools Together

Most problems need multiple tools:

**Pattern 1: Search → Deep Dive → Validate**
```
Task: Refactor password validation safely

Step 1: Find candidates
  semantic_search('password validation')
  Cost: 450 tokens
  Result: [validate_password, hash_password, compare_hash, ...]

Step 2: Understand each candidate
  For each result:
    get_context(result.symbol, include_callers=true)
    Cost: 287 × 3 = 861 tokens
    Result: Callers, dependencies, usage patterns

Step 3: Check safety
  compare_contracts(old_sig, new_sig)
  Cost: 300 tokens
  Result: Breaking changes (if any)

Step 4: Validate parallelization
  validate_conflicts([refactor_task])
  Cost: 200 tokens
  Result: Can this run in parallel with other work?

Total cost: 450 + 861 + 300 + 200 = 1811 tokens
Without MCP: Read 15 files + grep = 10000+ tokens
Savings: 82%
```

**Pattern 2: Maintain → Check → Update**
```
Task: Keep graph in sync with code

Step 1: Check freshness
  graph_stats()
  Cost: 150 tokens
  Result: node_count, edge_count, last_update

Step 2: If stale, decide update strategy
  IF 1 hour old:
    graph_diff_rebuild(commit_range='HEAD~10..HEAD')
    Cost: 800 tokens
    Result: Fast incremental update

  IF completely broken:
    graph_validate()
    Cost: 200 tokens
    Result: Orphaned nodes, broken refs

    graph_rebuild(clear_first=true)
    Cost: 2000 tokens
    Result: Fresh graph from source

Total for sync: 150 + 800 = 950 tokens (vs 6000 for rebuild)
Savings: 84%
```

### Level 4: Know When to Break Rules

These situations warrant file reads:
- File < 100 LOC and directly answers the question
- Need to see exact formatting/comments
- Graph doesn't have the symbol (rare)

Example:
```
User: "Show me the exact imports at top of main.py"
✓ OK to use: Read() or grep() - quick answer, small file
✗ Wrong choice: get_context() - gives dependencies, not raw code
```

---

## Decision Tree: Quick Reference

```
START: User asks about code

├─ "What does function X do?"
│  └─ get_context('X', include_callers=true)

├─ "Find code that does X"
│  └─ semantic_search('X')

├─ "Show me file X"
│  ├─ File > 500 LOC?
│  │  ├─ YES → Use get_context() or semantic_search()
│  │  └─ NO → Read() is OK
│
├─ "Can I change X?"
│  ├─ Step 1: get_context('X', include_callers=true)
│  └─ Step 2: compare_contracts(old, new)

├─ "Update graph after git change"
│  ├─ Small change? → graph_diff_rebuild()
│  └─ Large change? → graph_rebuild()

├─ "Graph broken or stale?"
│  ├─ Check: graph_stats()
│  ├─ Validate: graph_validate()
│  └─ Fix: graph_rebuild() or graph_diff_rebuild()

└─ "Can I parallelize these changes?"
   └─ validate_conflicts([task1, task2, ...])
```

---

## Token Budget Reality

You have ~100,000 tokens to solve problems. Spend wisely:

**Scenario A (Without MCP):**
```
Task: Refactor password validation system
├─ Read user auth file: 2000 tokens
├─ Read database file: 2000 tokens
├─ Read API file: 1500 tokens
├─ Grep for callers: 1000 tokens
├─ Read 5 caller files: 5000 tokens
└─ TOTAL: 11,500 tokens (12% of budget)
└─ Left for actual refactoring: 88,500 tokens

Problem: 90% of those reads were irrelevant. You wasted token budget.
```

**Scenario B (With MCP):**
```
Task: Refactor password validation system
├─ semantic_search('password'): 450 tokens
├─ get_context(3 candidates): 861 tokens
├─ compare_contracts: 300 tokens
└─ TOTAL: 1,611 tokens (1.6% of budget)
└─ Left for actual refactoring: 98,389 tokens

Advantage: Used minimal budget to understand problem, have plenty left
           to implement solution, test, and handle edge cases.
```

**Lesson:** "Use MCP to stay under 5000 tokens for understanding. Save 95000+ for actual work."

---

## Common Mistakes & How to Avoid Them

### Mistake 1: Reading Entire Files
```python
❌ BAD:
  content = Read('src/api/endpoints.py')  # 5000 tokens
  # Now read it character by character...

✅ GOOD:
  context = get_context('validate_request', include_callers=true)  # 287 tokens
  # Instant understanding, exact info needed
```

### Mistake 2: Assuming Without Checking
```python
❌ BAD:
  Agent: "This function is only called from one place"
  (Later) Refactor breaks 5 hidden callers

✅ GOOD:
  context = get_context('function_name', include_callers=true)
  # Sees all 5 callers before making assumptions
```

### Mistake 3: Using Grep on Large Codebase
```python
❌ BAD:
  results = Grep('.*password.*')  # Returns 2000 matches
  # Now read all 2000 files?

✅ GOOD:
  results = semantic_search('password validation')  # Returns 8 relevant matches
  # Ranked by relevance, exactly what you need
```

### Mistake 4: Not Checking Graph Freshness
```python
❌ BAD:
  Agent uses 2-hour-old graph
  Result: Missing recent changes, wrong answers

✅ GOOD:
  stats = graph_stats()  # 150 tokens
  If > 1 hour old:
    graph_diff_rebuild()  # 800 tokens (fast)
  Now graph is fresh and queries are accurate
```

### Mistake 5: Not Validating Conflicts
```python
❌ BAD:
  Agent: "I'll parallelize these 3 tasks"
  (Later) Tasks conflict, cause problems

✅ GOOD:
  conflicts = validate_conflicts([task1, task2, task3])  # 200 tokens
  If conflicts exist, see exactly what conflicts and fix them
```

---

## Agent Checklist: Am I Using MCP Right?

At end of each session, rate yourself on these 10 criteria:

- [ ] Did I use get_context() instead of reading files? (Target: 90%+)
- [ ] Did I use semantic_search() for code discovery? (Target: 95%+)
- [ ] Did I check graph freshness before querying? (Target: 100%)
- [ ] Did I use graph_stats() to monitor graph health? (Target: 100%)
- [ ] Did I sync graph after git changes with graph_diff_rebuild()? (Target: 100%)
- [ ] Did I use compare_contracts() before refactoring? (Target: 100%)
- [ ] Did I validate conflicts before parallelizing? (Target: 100%)
- [ ] Did I avoid reading files > 500 LOC? (Target: 95%+)
- [ ] Did I save tokens vs traditional approach? (Target: 70%+ savings)
- [ ] Did I use the right tool for each task? (Target: 100%)

If you answered YES to 8/10, you're using MCP correctly!

---

## Graph Syncing with Git/GitHub

**Important:** The code graph must stay in sync with your code changes.

### How It Works

```
You make changes → git add/commit → git push GitHub
                                         ↓
                            Agent checks graph freshness
                                         ↓
                    Agent sees graph is stale (1+ hour old)
                                         ↓
                    Agent calls: graph_diff_rebuild()
                                         ↓
                    Graph pulls changes from git history
                                         ↓
                    Next query uses fresh, accurate graph
```

### When to Sync Graph

**Automatic (recommended):**
```python
# At session start, agent does:
stats = graph_stats()
if stats['last_update'] < 1_hour_ago:
    graph_diff_rebuild(commit_range='HEAD~10..HEAD')
```

**Manual (when you know changes happened):**
```bash
# Option 1: Fast incremental (small changes)
graph_diff_rebuild(commit_range='HEAD~5..HEAD')

# Option 2: Full rebuild (major changes or broken graph)
graph_rebuild(clear_first=true)
```

### GitHub Workflow (Complete Cycle)

**Step 1: You make and push changes**
```bash
# Make changes locally
git add src/api/endpoints.py
git commit -m "refactor: Add rate limiting to API endpoints"
git push origin main
```

**Step 2: Changes are now on GitHub**
- Your code is on GitHub main branch
- Local graph still has old state (1-2 hours stale)

**Step 3: Agent detects stale graph**
```python
# Agent's automatic check at session start:
stats = graph_stats()  # 150 tokens
# Returns:
#   node_count: 1248
#   last_update: "2 hours ago"
#   is_connected: true
```

**Step 4: Agent syncs from GitHub**
```python
# Option A: Fast sync (for small changes)
graph_diff_rebuild(commit_range='HEAD~5..HEAD')
# Cost: 800 tokens
# Time: 30 seconds
# Updates: Only changed files

# Option B: Full sync (if unsure)
graph_diff_rebuild(commit_range='origin/main..HEAD')
# Cost: 1200 tokens
# Time: 1 minute
# Updates: All commits since last sync
```

**Step 5: Graph is now fresh from GitHub**
```python
# Agent can now query with confidence:
context = get_context('rate_limit_check')
# Returns: Latest function from GitHub + callers + dependencies
# All based on pushed code, not stale local state
```

**Step 6: Agent uses fresh context for next task**
```python
# Example: Refactor something related
search = semantic_search('rate limiting')
# Returns: All functions that handle rate limiting
# All from fresh GitHub state
```

### Token Cost Comparison

| Scenario | Method | Cost | Speed |
|----------|--------|------|-------|
| 1-5 files changed | `graph_diff_rebuild()` | 800 tokens | Fast (30s) |
| 10+ files changed | `graph_diff_rebuild()` | 1200 tokens | Fast (1m) |
| Major refactor | `graph_rebuild()` | 2000 tokens | Slow (5m) |
| Unsure/broken | `graph_rebuild()` | 2000 tokens | Slow (5m) |

**Best practice:** Always try `graph_diff_rebuild()` first (fast + cheap). Only use `graph_rebuild()` if diff fails or graph is broken.

### Why GitHub Sync Matters

**Without syncing:**
- ❌ Graph shows 2-hour-old code from GitHub
- ❌ Agent doesn't know about new functions pushed today
- ❌ Queries return outdated context
- ❌ Agent makes changes based on stale assumptions
- ❌ Can't see recent refactors or deletions

**With GitHub sync:**
- ✅ Graph always matches GitHub main branch
- ✅ Agent immediately sees pushed changes
- ✅ Queries return accurate, fresh context
- ✅ Agent knows about all recent modifications
- ✅ Safe to refactor and parallelize
- ✅ No surprises from changes you made elsewhere

### Quick Reference: Graph vs GitHub

```
GitHub main branch       Your local branch       Agent's graph
      ↓                        ↓                        ↓
  (Latest pushed)        (Your working code)    (Used for queries)

What agent sees:
├─ If synced: Graph = GitHub main (correct)
└─ If stale: Graph ≠ GitHub main (wrong!)
```

---

## Git Workflow for Agents

Agents need to know basic git commands to work effectively:

### Essential Git Commands

**Before working (check state):**
```bash
git status              # See what files changed locally
git log --oneline -5    # See last 5 commits
git branch -a           # See all branches
```

**When making changes:**
```bash
git add src/file.py     # Stage specific files
git add .               # Stage all changes
git commit -m "feat: Add new feature"  # Commit with message
git push origin main    # Push to GitHub
```

**Pulling latest changes:**
```bash
git pull origin main    # Fetch and merge from GitHub
# After pulling, agent should call:
graph_diff_rebuild()    # Keep graph in sync
```

**Before committing (verify changes):**
```bash
git diff                # See unstaged changes
git diff --staged       # See staged changes only
git status              # Full status overview
```

### Git Commands for Graph Syncing

**Get commit information (for graph_diff_rebuild):**
```bash
git log --oneline -10   # Last 10 commits
git rev-parse HEAD      # Current commit hash
git rev-parse origin/main  # GitHub main commit hash
```

**For graph_diff_rebuild() call:**
```python
# Agent needs to know the commit range:
graph_diff_rebuild(commit_range='HEAD~5..HEAD')
#                                   ↑ use git log to find
```

### Git Workflow: Agent Makes Changes

```
1. Agent checks state:
   git status
   → 5 files changed, not staged

2. Agent reviews changes:
   git diff
   → Sees exact changes in each file

3. Agent stages changes:
   git add src/api.py src/utils.py

4. Agent commits:
   git commit -m "refactor: Optimize API endpoints"

5. Agent pushes to GitHub:
   git push origin main

6. Agent syncs graph:
   graph_diff_rebuild(commit_range='HEAD~1..HEAD')
   → Graph now matches GitHub main

7. Agent verifies:
   git log --oneline -1
   → Confirms commit is on GitHub
```

### Common Git Scenarios

**Agent wants to undo changes:**
```bash
# Unstage file
git reset src/file.py

# Discard local changes (⚠️ destructive)
git checkout -- src/file.py

# Revert last commit (keeps history)
git revert HEAD
```

**Agent needs to check what changed:**
```bash
git diff HEAD~1..HEAD   # What changed in last commit
git show HEAD           # Full last commit info
git blame src/file.py   # Who changed each line
```

**Agent working on branch (before merging):**
```bash
git checkout -b feature/new-api
# ... make changes ...
git add .
git commit -m "feat: New API endpoints"
git push origin feature/new-api
# Create PR on GitHub, then:
git checkout main
git pull origin main
graph_diff_rebuild()    # Sync graph with merged main
```

### Git Best Practices for Agents

1. **Always check state first:**
   ```bash
   git status  # Before doing anything
   ```

2. **Review changes before committing:**
   ```bash
   git diff    # See what you're about to commit
   ```

3. **Write clear commit messages:**
   ```bash
   git commit -m "feat: Add rate limiting"  # Clear intent
   # NOT: git commit -m "fix stuff"         # vague
   ```

4. **Push frequently:**
   ```bash
   git push origin main  # After each logical change
   ```

5. **Sync graph after pushing:**
   ```bash
   git push origin main
   graph_diff_rebuild()  # Keep graph fresh
   ```

6. **Never force push (unless authorized):**
   ```bash
   # ❌ DON'T: git push --force
   # ✅ DO: Normal push workflow
   ```

### When Agent Should Use Git Commands

| Task | Git Command | Then Call |
|------|------------|-----------|
| See what changed | `git diff` | N/A (just view) |
| Check status | `git status` | N/A (just check) |
| Stage changes | `git add .` | `git commit -m "msg"` |
| Commit work | `git commit -m "msg"` | `git push origin main` |
| Push to GitHub | `git push origin main` | `graph_diff_rebuild()` |
| Pull from GitHub | `git pull origin main` | `graph_diff_rebuild()` |
| View history | `git log --oneline` | N/A (just view) |

---

How to keep synced:
├─ Option 1: Automatic every 1 hour
├─ Option 2: Manual after git push
├─ Option 3: CI/CD on every merge
└─ Option 4: Agent syncs on demand
```

### Integration with Your GitHub Workflow

**Option 1: Automatic (Recommended)**
Agent detects stale graph automatically:
```python
# At session start, agent does:
stats = graph_stats()
if stats['last_update'] > 1_hour_old:
    graph_diff_rebuild(commit_range='HEAD~10..HEAD')
    # Graph is now fresh from GitHub
```

**Option 2: Manual after git push**
```bash
# After you push to GitHub:
git push origin main

# Agent syncs next time it queries:
# (happens automatically, no manual step needed)
```

**Option 3: CI/CD Pipeline (GitHub Actions)**
```yaml
# .github/workflows/sync-graph.yml
name: Sync graph after merge
on:
  push:
    branches: [main]

jobs:
  sync-graph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Sync graph from git
        run: |
          python -c "from src.mcp_server.tools.database_tools import graph_diff_rebuild; graph_diff_rebuild(commit_range='HEAD~1..HEAD')"
```

**Option 4: Manual trigger anytime**
```bash
# If you know changes happened:
# Tell the agent to sync immediately:
# "Please sync the graph with latest GitHub changes"

# Agent will call:
graph_diff_rebuild(commit_range='origin/main..HEAD')
```

### GitHub + Graph Sync Best Practices

| Scenario | Action | Cost | Speed |
|----------|--------|------|-------|
| Just pushed to main | Wait for auto-check (1h max) | None | Auto |
| Made 1-5 file changes | `graph_diff_rebuild()` | 800 tokens | 30s |
| Made 10+ file changes | `graph_diff_rebuild()` | 1200 tokens | 60s |
| Major refactor | `graph_rebuild()` | 2000 tokens | 5m |
| Graph is broken | `graph_rebuild()` | 2000 tokens | 5m |
| Not sure if stale | `graph_stats()` then decide | 150 tokens | Instant |

---

## Automatic Graph Syncing with Git Hooks

Instead of manual commands or CI/CD, you can use git hooks for **automatic local syncing**:

### Setup (One-time)

```bash
# Install git hooks (auto-sync on commit/push)
bash install-git-hooks.sh
```

This creates two hooks:
- `.git/hooks/post-commit` - Syncs graph after each commit
- `.git/hooks/post-push` - Syncs graph after each push (manual trigger)

### How It Works

**Automatic on commit:**
```bash
git commit -m "refactor: Update API"
# → Hook runs automatically
# → graph_diff_rebuild() syncs last commit
# → Graph now has your changes
```

**Manual on push:**
```bash
git push origin main
bash .git/hooks/post-push
# → Graph syncs with pushed commits
# → Graph matches remote
```

### Three Ways to Sync Graph

| Method | Trigger | Cost | Speed | Setup |
|--------|---------|------|-------|-------|
| **Git Hooks** | Auto on commit | 800 tokens | 30s | `bash install-git-hooks.sh` |
| **GitHub Actions** | Auto on push | Free CI/CD | 60s | Already configured |
| **Manual** | On demand | 800 tokens | 30s | `graph_diff_rebuild()` |

### Requirements for Git Hooks

1. **Neo4j must be running:**
   ```bash
   docker-compose up -d neo4j
   ```

2. **MCP server must be running** (optional, for full features):
   ```bash
   python run.py
   ```

If Neo4j is down, hooks skip silently and log a warning.

### Uninstall Git Hooks

```bash
rm .git/hooks/post-commit .git/hooks/post-push
```

### Git Hooks vs GitHub Actions

**Use Git Hooks if:**
- Working locally without pushing
- Want instant feedback after commits
- Don't need CI/CD pipeline
- Prefer local-only syncing

**Use GitHub Actions if:**
- Team needs synced graph on main branch
- Want consistent state across deployments
- Need automated testing + syncing
- Prefer remote pipeline

**Use Both if:**
- Local development: git hooks
- Team collaboration: GitHub Actions
- Safety: Double sync (local + remote)

---

## Getting Help

If stuck, ask:
- "Is the graph working?" → `graph_stats()`
- "Is my change safe?" → `compare_contracts()`
- "What code does this?" → `get_context()`
- "Find code that does X" → `semantic_search()`
- "Update after git" → `graph_diff_rebuild()`

Never answer with assumptions. Always use tools.
"""

        guide_file = skill_dir / 'SKILL.md'
        with open(guide_file, 'w') as f:
            f.write(guide)

        if guide_file.exists():
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


def ask_sync_method() -> str:
    """Ask user which graph sync method they prefer."""
    print("\n" + "="*70)
    print("GRAPH SYNC METHOD")
    print("="*70)
    print("\nHow should the graph stay in sync with code changes?\n")

    print("1. GIT HOOKS (Local - Recommended for solo development)")
    print("   - Auto-syncs after each git commit")
    print("   - Instant feedback (30 seconds)")
    print("   - Works offline")
    print("   - Setup: bash install-git-hooks.sh\n")

    print("2. GITHUB ACTIONS (Remote - Recommended for teams)")
    print("   - Auto-syncs on every git push")
    print("   - Free CI/CD runners")
    print("   - Team has synced graph on main")
    print("   - Already configured (.github/workflows/sync-graph.yml)\n")

    print("3. MANUAL ONLY (No automation)")
    print("   - Use: graph_diff_rebuild()")
    print("   - Control when graph syncs")
    print("   - Minimal overhead\n")

    print("4. BOTH (Git hooks + GitHub Actions)")
    print("   - Local instant sync + team sync")
    print("   - Maximum coverage")
    print("   - Slight CI/CD overhead\n")

    while True:
        choice = input("Choose 1-4 (default: 1 - Git Hooks): ").strip()
        if not choice:
            return "git-hooks"
        if choice == "1":
            return "git-hooks"
        elif choice == "2":
            return "github-actions"
        elif choice == "3":
            return "manual"
        elif choice == "4":
            return "both"
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


def setup_sync_method(method: str, project_root: Path) -> bool:
    """Setup the selected sync method."""
    if method == "git-hooks":
        print("\n[Phase 2.5] Setting up Git Hooks")
        print("-" * 70)
        print("  Installing git hooks...", end=" ", flush=True)
        try:
            result = subprocess.run(['bash', 'install-git-hooks.sh'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("[OK]")
                print("  Git hooks installed for auto-sync on commit")
                return True
            else:
                print("[WARN]")
                print("  Manual setup: bash install-git-hooks.sh")
                return True
        except Exception as e:
            print(f"[WARN] {e}")
            return True

    elif method == "github-actions":
        print("\n[Phase 2.5] GitHub Actions Setup")
        print("-" * 70)
        print("  GitHub Actions workflow ready: .github/workflows/sync-graph.yml")
        print("  Graph will auto-sync on every git push to main/develop")
        return True

    elif method == "both":
        print("\n[Phase 2.5] Setting up Git Hooks + GitHub Actions")
        print("-" * 70)
        print("  Installing git hooks...", end=" ", flush=True)
        try:
            result = subprocess.run(['bash', 'install-git-hooks.sh'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("[OK]")
            else:
                print("[WARN]")
        except Exception as e:
            print(f"[WARN] {e}")

        print("  GitHub Actions workflow ready: .github/workflows/sync-graph.yml")
        print("  Dual sync: local (on commit) + remote (on push)")
        return True

    else:  # manual
        print("\n[Phase 2.5] Manual Sync Method")
        print("-" * 70)
        print("  No automation configured")
        print("  Sync manually with: graph_diff_rebuild()")
        return True


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

    # Phase 2.5: Ask about sync method
    sync_method = ask_sync_method()
    setup_sync_method(sync_method, project_root)

    print()

    # Phase 3: Configure Claude Code
    print("[Phase 3] Configuring Claude Code")
    print("-" * 70)

    success = True
    success &= create_mcp_json(project_root)
    success &= create_claude_settings(project_root)
    success &= create_claude_workspace(project_root)
    success &= create_mcp_guide_skill(project_root)

    print()

    # Success!
    print("="*70)
    print("[SUCCESS] SETUP COMPLETE!")
    print("="*70)
    print()
    print("What's next:")
    print("  1. Start everything: python run.py")
    print("     (automatically starts Neo4j + MCP server + builds graph)")
    print("  2. Open this folder in Claude Code")
    print("  3. Claude will auto-detect MCP and use SMT tools")
    print()
    print("Optional docker commands:")
    print("  python run.py docker status    # Check Neo4j status")
    print("  python run.py docker down      # Stop Neo4j")
    print()
    print("Configuration files created:")
    print("  - .mcp.json                         (MCP server discovery)")
    print("  - .claude/settings.json             (Claude Code configuration)")
    print("  - .claude/workspace.json            (Project workspace config)")
    print("  - .claude/skills/mcp-guide/SKILL.md (MCP learning guide)")
    print()
    print(f"Graph sync method: {sync_method.upper()}")
    if sync_method == "git-hooks":
        print("  - Auto-syncs on every git commit")
        print("  - Manual trigger: bash .git/hooks/post-push")
    elif sync_method == "github-actions":
        print("  - Auto-syncs on every git push")
        print("  - Make sure to push to GitHub")
    elif sync_method == "both":
        print("  - Local sync: on every git commit")
        print("  - Remote sync: on every git push")
    else:
        print("  - Manual sync: use graph_diff_rebuild()")
    print()

    return success

if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
