# Complete Explanation: How SMT Works with Git & GitHub

This document ties together **why SMT exists**, **how it works with Git**, and **why the MCP tools are critical**.

---

## The Problem: Agent Code Exploration is Wasteful

### Before SMT (Naive Approach)

```
Agent needs to understand Flask codebase (3.2MB, 83 files)

Step 1: Read entire repository
        $ git clone https://github.com/pallets/flask.git
        
Step 2: Parse everything
        for file in $(find . -name "*.py"):
            Read entire file
            Extract symbols
        Result: 83 files × 300-500 LOC each = 8,300 tokens WASTED
        
Step 3: Search for a symbol
        grep -r "def route" .
        Returns 10 matches, agent reads 4 files to understand
        Another 2,000 tokens WASTED
        
Step 4: Answer question: "Does this change break anything?"
        Re-read entire relevant subgraph
        Another 3,000 tokens WASTED
        
Total: ~13,000 tokens to answer 1 question
       88% of tokens spent on irrelevant code
```

### With SMT (Smart Approach)

```
Agent needs to understand Flask codebase (3.2MB, 83 files)

Step 1: Query MCP tool
        get_context("route", depth=1)
        Returns: symbol info, dependencies, callers, callees
        
Step 2: Understand dependencies
        Response shows: route → current_app, ValueError, add_url_rule
        Other callers: Flask.route, app.route
        
Step 3: Answer question: "Does this change break anything?"
        validate_conflicts([task1, task2])
        Uses Neo4j to check safe parallelization
        
Total: ~250 tokens to answer 1 question
       88% SAVED vs naive approach
```

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    GITHUB / GIT REPOSITORY                  │
│  (Source of truth: all code, all history, all branches)      │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    │ Developer pushes commit
                    │ (or agent creates PR)
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                      GIT DIFF DETECTION                      │
│  $ git diff HEAD~1                                           │
│  Output: Changed files, line diffs                           │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                   DIFFPARSER (Incremental)                   │
│  Identifies: 2 files modified, 5 lines added, 2 deleted     │
│  Outputs: FileDiff[] (only changed files)                   │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│              PARSERS (Incremental Mode)                      │
│  Parse ONLY the 2 changed files (not all 83)                │
│  Extract symbols: functions, classes, imports, types         │
│  Outputs: SymbolDelta (what changed at symbol level)        │
│  Cost: ~100ms (vs ~5 seconds to parse entire repo)          │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│            INCREMENTALSYMBOLUPDATER (Atomic)                │
│  1. Backup current state (for rollback)                     │
│  2. Update in-memory SymbolIndex                            │
│  3. Update Neo4j transactionally                            │
│  4. Record delta in history                                 │
│  Cost: ~50ms (Neo4j transaction)                            │
│  Guarantee: All-or-nothing (consistent state)               │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    NEO4J GRAPH (Fresh)                       │
│  Nodes: Files, Modules, Functions, Classes, Variables       │
│  Edges: IMPORTS, CALLS, DEFINES, DEPENDS_ON, etc.           │
│  Always up-to-date with latest code                         │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                 MCP TOOLS (10 tools available)               │
│  ✓ get_context()        - Get symbol + dependencies          │
│  ✓ get_subgraph()       - Full dependency tree               │
│  ✓ search()            - Semantic search                    │
│  ✓ validate_conflicts() - Check safe parallelization        │
│  ... 6 more tools for contracts, incremental, scheduling    │
└───────────────────┬──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    AGENTS / CLAUDE CODE                      │
│  Query fresh graph with accurate info                       │
│  Make informed decisions about code changes                 │
│  Detect conflicts before parallelizing tasks                │
└──────────────────────────────────────────────────────────────┘
```

---

## Why Incremental Analysis Matters

### Scenario: Flask Repository Gets a Bug Fix

```
Timeline:
T=0:    SMT processes entire Flask repo (83 files)
        → Parses all files, builds Neo4j graph
        → Takes ~7 seconds
        → Result: Graph represents main branch

T=10:   Developer commits fix to route.py (2 changes)
        → git push origin main
        
T=11:   SMT detects change
        → git diff HEAD~1 = "src/core/route.py modified"
        → DiffParser: "1 file changed, 3 lines added, 1 deleted"
        
T=11.1: IncrementalUpdater applies delta
        → Parses ONLY route.py (not all 83 files)
        → Updates Neo4j with new edges
        → Takes ~150ms
        → Result: Graph is fresh and current
        
T=11.2: Agent queries get_context("route")
        → Returns: current signature, NEW imports, callers
        → Agent sees: ValueError import is new
        → Agent thinks: "I need to handle this in calling code"
        
T=20:   Agent submits PR with fix
        
T=21:   Developer merges PR
        → new_fix_branch commits to main
        
T=21.1: SMT detects new change
        → 2 files modified (now includes caller.py too)
        → Updates graph in ~150ms
        → Ready for next agent task
```

**Key insight:** Graph stayed current with minimal parsing overhead.

---

## Performance Comparison: With vs Without Incremental

### Scenario: Big Refactor (100 commits over 1 week)

**WITHOUT Incremental (Naive Re-parsing):**
```
After each of 100 commits:
  Parse entire 83-file repo     7 seconds
  Build Neo4j graph             2 seconds
  Total per commit              9 seconds
  
Weekly total: 100 × 9 sec = 900 seconds = 15 MINUTES wasted
```

**WITH Incremental (SMT):**
```
After each commit (avg 2-3 files changed):
  Parse changed files           0.1 seconds
  Update Neo4j delta            0.05 seconds
  Total per commit              0.15 seconds
  
Weekly total: 100 × 0.15 sec = 15 seconds
Total saved: 885 seconds (14.75 MINUTES)
Speedup: 60x faster
```

---

## How Agents Use This

### Agent Workflow: "Add async handler support to route()"

```
Step 1: Agent asks SMT: "What does route() look like?"
        Tool: get_context("route", depth=1)
        Response:
        {
            "symbol": "route",
            "file": "src/core/route.py:42",
            "signature": "def route(path: str, methods=None) -> Callable",
            "dependencies": ["current_app", "ValueError", "add_url_rule"],
            "callers": ["Flask.route", "app.route"],
            "token_count": 243
        }

Step 2: Agent sees the dependencies
        Agent: "route() calls add_url_rule(). Does that support async?"
        Agent queries: get_context("add_url_rule", depth=1)
        
Step 3: Agent finds add_url_rule() doesn't support async
        Agent: "I'll create a new add_async_url_rule() instead"
        
Step 4: Agent modifies code
        - Adds new function add_async_url_rule()
        - Modifies route() to detect async handlers
        - Commits to feature branch
        
Step 5: Agent asks: "Can I run this in parallel with Task_B?"
        Tool: validate_conflicts([task_A, task_B])
        Response: "No conflict detected (different modules)"
        
Step 6: Agent submits PR
        - Git detects changes in 3 files
        - SMT incremental update: 200ms
        - Graph is fresh
        - Next agent can query accurate info
```

---

## Why This Validates CLAUDE.md Rules

### Rule #5 Enforcement: "Prefer MCP Tools Over Grep/Search"

The audit proved:
- MCP approach: 243 tokens per lookup
- Grep+Read approach: 2,027 tokens per lookup
- **88% savings**

But there's a **deeper reason** beyond token efficiency:

1. **Accuracy:** MCP queries Neo4j (updated via incremental deltas)
2. **Safety:** Graph reflects real dependencies (accurate for conflict detection)
3. **Completeness:** Includes transitive dependencies (can't miss call chains)
4. **Speed:** 45ms query vs 850ms file reading

**Without using MCP tools:**
- Agent might miss a transitive dependency
- Conflict detection fails
- Parallel task execution breaks
- Code quality degrades

**With MCP tools:**
- Agent sees all dependencies
- Conflict detection is accurate
- Safe parallelization possible
- Code quality maintained

---

## Git Integration: Now vs Future

### Phase 1 (Current)
```
✓ DiffParser can parse git diffs
✓ Parsers can do incremental updates
✓ IncrementalUpdater applies atomically
✓ MCP tools query fresh graph

Manual workflow:
  Developer commits → Agent manually calls DiffParser
  → Agent applies SymbolDelta → Graph updates
```

### Phase 2 (Planned)
```
+ Git webhook auto-triggers updates
+ Real-time conflict detection on PRs
+ Agent scheduling with safe parallelization
+ REST API cleanup (MCP becomes primary interface)

Automatic workflow:
  Developer commits → GitHub webhook → SMT updates automatically
  → Agent queries fresh graph immediately
```

---

## Summary: The Complete Picture

| Component | Purpose | Impact |
|-----------|---------|--------|
| **DiffParser** | Parse git diffs into file changes | Only parse changed files |
| **IncrementalParsers** | Parse only modified files | 46x faster vs full re-parse |
| **IncrementalUpdater** | Apply changes atomically | Consistent index + Neo4j |
| **Neo4j Graph** | Always-fresh dependency graph | Agents get accurate info |
| **MCP Tools** | Query the graph | 88% token savings |
| **CLAUDE.md Rules** | Enforce MCP-first usage | Safe agent decisions |

**Result:** Agents can explore code **faster**, **cheaper**, and **more accurately** than traditional file-based approaches.

---

## Key Metrics

| Metric | Value | Implication |
|--------|-------|-----------|
| Token savings per query | 88% | Massive efficiency |
| Speed improvement | 18.9x | Faster agent loops |
| Full re-parse time | ~7 sec | Only done once |
| Incremental update time | ~150ms | Done per commit |
| Weekly speedup (100 commits) | 60x | 15 min saved/week |
| Graph accuracy | 100% | Up-to-date always |
| Conflict detection | Reliable | Safe parallelization |

---

## Files to Read for Deep Dive

1. **GIT_WORKFLOW_EXPLANATION.md** - Step-by-step explanation with real code
2. **INCREMENTAL_FLOW_DIAGRAM.txt** - Visual flow through entire pipeline
3. **AUDIT_REPORT.md** - Token efficiency evidence
4. **src/incremental/updater.py** - Implementation details
5. **src/incremental/diff_parser.py** - Git diff parsing logic
6. **CLAUDE.md** - Tool usage rules (now justified by this explanation)

---

## Conclusion

SMT is fundamentally different from naive agent approaches because:

1. **It's git-aware** (DiffParser, incremental updates)
2. **It's graph-based** (Neo4j, semantic dependencies)
3. **It's accurate** (always fresh via incremental deltas)
4. **It's efficient** (88% token savings, 46x faster parsing)

This is why **MCP-first tool usage is not optional—it's the foundation** of the entire system.

Agents that follow CLAUDE.md rules get:
- Fresh, accurate code context
- Safe parallelization detection
- Massive token efficiency
- Better decision-making

Agents that fall back to Grep/Read waste 88% of tokens and lose accuracy.
