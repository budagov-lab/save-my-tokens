# Save My Tokens (SMT)

**Intelligent code context for Claude — without reading entire files.**

Instead of asking Claude to read 500-line files, SMT queries a **semantic dependency graph** of your codebase and returns only the **smallest relevant subgraph**. Result: **faster context**, **smaller payloads**, and **cycle-safe bounds**.

---

## The Problem

Claude reads **entire files** to understand one function:
- "What does `GraphBuilder` do?" → reads 200 lines to answer
- "Who calls `parse_diff`?" → reads all 40 functions in the file
- "What breaks if I change `Neo4jClient`?" → reads deeply into the dependency tree

**This is wasteful.** Most of those lines don't matter for the question.

---

## The Solution

SMT builds a **graph of function-level dependencies** from your code, then answers specific questions with **minimal context**:

```bash
# What is this? (definition + signature)
smt definition GraphBuilder

# What do I need to work on this? (working context)
smt context GraphBuilder --depth 2

# What breaks if I change this? (impact analysis)
smt impact Neo4jClient --depth 3
```

---

## Key Features

✅ **Three Query Modes** — Each answers one agent question (definition / context / impact)

✅ **Cycle-Safe** — Detects circular dependencies (Tarjan's SCC algorithm), prevents unbounded context expansion

✅ **Validated** — Shows git freshness status ("fresh" or "N commits behind")

✅ **Compressed** — Removes trivial bridge functions with optional `--compress` flag

✅ **Multi-Language** — Python + TypeScript (via Tree-sitter), extensible to more languages

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/budagov-lab/save-my-tokens
cd save-my-tokens
pip install -e .
```

### 2. Start Neo4j

```bash
smt docker up    # or: docker-compose up -d neo4j
sleep 10         # wait for startup
```

### 3. Build the graph

```bash
smt build        # Parses src/, builds Neo4j graph
smt status       # Check: should show node/edge counts
```

### 4. Query

```bash
# Try all three modes on your codebase
smt definition MyClass
smt context MyClass --depth 2
smt impact MyFunction --depth 3 --compress
```

---

## Query Modes Explained

### Mode 1: **Definition** — "What is this?"

```bash
$ smt definition GraphBuilder

GraphBuilder  [Class]
  file: src/graph/graph_builder.py:23
  sig:  class GraphBuilder:
  doc:  Orchestrates the full pipeline: Parse -> Index -> Create Graph Nodes -> Create Graph Edges.

  calls (3):
    _parse_all_files     (graph_builder.py)
    _create_nodes        (graph_builder.py)
    _create_edges        (graph_builder.py)

  HEAD 1d27a7a  [✓] fresh
```

**Use when:** Agent needs to understand what a symbol is
**Scope:** 1 hop (immediate dependencies)

---

### Mode 2: **Context** — "What do I need to work on this?"

```bash
$ smt context GraphBuilder --depth 2

GraphBuilder  [Class]
  file: src/graph/graph_builder.py:23
  sig:  class GraphBuilder:
  doc:  Orchestrates...

  calls (3):
    _parse_all_files
    _create_nodes
    _create_edges

  [Cycle: CallAnalyzer._infer_edge_type → _resolve_target → _infer_edge_type]
    2 functions collapsed

  callers (1):
    cmd_build  (smt_cli.py)

  context: nodes=7 edges=5 depth=2 cycles=1
  HEAD 1d27a7a  [✓] fresh
```

**Use when:** Agent refactoring, understanding dependencies, writing code
**Scope:** 2-3 hops (bounded depth)

---

### Mode 3: **Impact** — "What breaks if I change this?"

```bash
$ smt impact Neo4jClient --depth 3

Impact: Neo4jClient  [Class]
  file: src/graph/neo4j_client.py:12

  direct callers (5):
    GraphBuilder      (graph_builder.py)
    IncrementalUpdater (incremental/updater.py)
    ... 

  indirect callers — depth 2 (3):
    cmd_build
    cmd_diff
    ...

  [Cycle: get_bounded_subgraph → create_edges → get_bounded_subgraph]
    2 functions in cycle

  impact: nodes=12 depth=2 cycles=1
  HEAD 1d27a7a  [✓] fresh
```

**Use when:** Planning refactors, understanding breaking changes, impact analysis
**Scope:** 3-4 hops (reverse traversal)

---

## Advanced Usage

### Compression (remove trivial functions)

```bash
# Remove "bridge" functions (trivial forwarders with no logic)
smt context GraphBuilder --depth 2 --compress

context: nodes=7→4 edges=5→3 depth=2 cycles=1
compressed: 3 bridge functions removed
```

### Semantic Search

```bash
# Find related symbols by meaning
smt search "cycle detection"
# → returns: detect_cycles, SCC, Tarjan's algorithm, etc.
```

### Sync After Commits

```bash
# Update graph after code changes
smt diff HEAD~1..HEAD   # or: smt diff
# Shows: "Graph synced: 3 commits, 12 symbols changed"
```

---

## Architecture

```
Your Codebase (Python / TypeScript)
          ↓
    Tree-sitter
    (parse symbols, calls, definitions)
          ↓
       Neo4j Graph
    (store dependencies)
          ↓
   Three Query Engines
   ├─ definition (1-hop)
   ├─ context (bidirectional, bounded)
   └─ impact (reverse traversal)
          ↓
    Cycle Detection (Tarjan's SCC)
   + Validation (git freshness)
   + Compression (bridge removal)
          ↓
     CLI Tool / Agent
```

---

## CLI Reference

```
smt build [--dir PATH]        Build graph from src/
smt build --check             Show graph statistics
smt build --clear             Wipe and rebuild

smt definition SYMBOL         Fast lookup: what is this?
smt context SYMBOL [--depth] Working context with cycles
smt impact SYMBOL [--depth]   Who calls this symbol (reverse)
smt context ... --compress    Remove bridge functions

smt search QUERY              Semantic search by meaning
smt callers SYMBOL            Quick alias for context --callers

smt diff [RANGE]              Sync graph after commits
smt status                     Graph health check

smt docker up|down|status     Manage Neo4j container
smt setup [--dir PATH]        Configure a project
smt hooks install|uninstall   Auto-sync hooks for git
```

---

## Requirements

- **Python 3.11+**
- **Docker** (for Neo4j, or use existing Neo4j instance)
- **Git** (for change tracking)

---

## How Agents Use SMT

### CLI Approach (subprocess)

Agents can invoke `smt` CLI commands directly via subprocess:

```python
# Example 1: Understanding a function
result = subprocess.run(["smt", "definition", "validate_graph"])
# Returns: signature, docstring, 1-hop callees

# Example 2: Impact analysis
result = subprocess.run(["smt", "impact", "GraphBuilder.__init__", "--depth", "3"])
# Returns: all callers grouped by distance

# Example 3: Commit analysis
result = subprocess.run(["smt", "diff", "HEAD~1..HEAD"])
# Shows: which symbols changed, who depends on them
```

**Pros**: Simple, works from any language, no imports needed.

**Cons**: 
- Subprocess overhead per call
- Parsing stdout is fragile
- No structured return types (string parsing)
- Sequencing multiple queries requires parsing between steps

---

### A2A Approach: Agent-to-Agent Orchestration (recommended)

For multi-step analysis workflows, use **A2A orchestration** — one orchestrator agent spawns and manages specialized subagents (Scout, Fabler, PathFinder) with deterministic, structured data flow.

**Problem A2A Solves**:
1. **Query sequencing**: Agent needs facts before it can reason (Scout → Fabler)
   - Without A2A: Agent does N subprocess calls, waits for each, parses output, then decides next step
   - With A2A: Orchestrator sends Scout once, gets structured JSON, routes directly to Fabler with those facts
2. **Determinism**: Agent chains hallucinate code paths
   - Without A2A: Fabler might reason about "a function that doesn't exist" based on bad Scout output parsing
   - With A2A: SMTQueryEngine guarantees Scout returns only symbols that exist in the graph
3. **Parallelism**: Some analyses can run at the same time
   - Without A2A: Sequential subprocess calls block each other
   - With A2A: Scout completes once, then Fabler and PathFinder run in parallel with identical facts

**Solution: SMTQueryEngine**

```python
from src.agents.query_engine import SMTQueryEngine

engine = SMTQueryEngine()

# Scout agent gathers facts (deterministic, structured)
definition = engine.definition("GraphBuilder")           # What is this?
context = engine.context("GraphBuilder", depth=2)       # Working context
impact = engine.impact("GraphBuilder", depth=3)         # Who calls this?
search = engine.search("cycle detection", top_k=5)      # Semantic search

# Results are JSON-serializable dicts, not stdout strings
# Fabler/PathFinder agents receive these as structured input
# No parsing, no hallucination risk

engine.close()
```

**Why A2A Over CLI**:
| Aspect | CLI (subprocess) | A2A (SMTQueryEngine) |
|---|---|---|
| **Return type** | stdout string (parse) | JSON dict (structured) |
| **Overhead** | Per-call subprocess | In-process queries |
| **Agent chains** | Sequential only | Sequential + parallel |
| **Hallucination risk** | High (parsing) | Low (verified symbols) |
| **Use case** | Simple one-off queries | Complex multi-agent workflows |

---

## FAQ

**Q: Do I need Neo4j?**
A: Yes. You can run it locally (`smt docker up`) or point to an existing instance. Community Edition is free.

**Q: What languages are supported?**
A: Python and TypeScript (via Tree-sitter). More languages can be added.

**Q: How often should I rebuild?**
A: `smt diff` syncs incrementally after commits. Use `smt build` for full rebuilds. Set up git hooks for auto-sync.

**Q: Can I use it with Claude?**
A: Yes! Agents can invoke `smt` via Bash:
```bash
$ smt context GraphBuilder --depth 2
```

**Q: What about private codebases?**
A: Everything runs locally. Neo4j stays on your machine.

**Q: Can it handle very large codebases (100k+ LOC)?**
A: SMT is designed for large graphs. Neo4j Community can handle millions of nodes. Queries scale with depth bounds, not codebase size.

---

## Agent Harness: Automated Code Analysis

SMT includes **Scout, Fabler, and PathFinder** — a team of specialized agents that automate multi-step code analysis workflows.

### Scout: Read-Only Graph Analyst

**Use when**: You need facts about code structure and dependencies

```bash
/smt-analysis
# Scout runs: smt status → smt definition → smt context → smt impact
# Returns: Exact file:line locations, caller counts, cycle detection
```

**Example**:
```
Question: "Who calls GraphBuilder.build?"
Scout queries: smt context GraphBuilder.build --depth 3
Returns: 7 direct callers, 12 indirect, no cycles, graph is fresh
```

### Fabler: What-If Impact Analyst

**Use when**: You want to predict consequences of a code change

```bash
# Ask naturally:
# "What would break if I renamed GraphBuilder.build to GraphBuilder.execute?"
# "Impact analysis: refactor Neo4jClient.__init__"
```

**What Fabler does**:
1. Receives Scout's verified facts
2. Classifies each caller: **Breaking** / **Degraded** / **Unaffected**
3. Proposes safe change order (leaf functions first)
4. Assesses if change can be atomic (one commit)

**Example output**:
```
Proposed change: Rename GraphBuilder.build() → GraphBuilder.execute()
Confidence: HIGH

Direct callers affected: 1
- cmd_build (src/smt_cli.py:168): BREAKING

Safe change order:
  Step 1: Rename in src/graph/graph_builder.py
  Step 2: Update caller in src/smt_cli.py
  Step 3: Update tests/

Atomicity: One commit ✓
```

### PathFinder: Code Isolation Analyst

**Use when**: You need to find independent code areas for parallel development

```bash
# Ask naturally:
# "What parts of src/parsers can we work on independently?"
# "Find isolated components in the graph module"
```

**What PathFinder does**:
1. Enumerates all symbols in target area
2. Checks for external dependencies per component
3. Identifies connected components (tightly coupled groups)
4. Outputs safe parallel work groupings

**Example output**:
```
Independent components found: 2

Component 1: PythonParser, _extract_function_node
  - External callers: GraphBuilder.build (read-only)
  - Status: Fully isolated

Component 2: TypeScriptParser, _extract_ts_function
  - External callers: GraphBuilder.build (read-only)
  - Status: Fully isolated

Safe to work on in parallel:
  Team A: Refactor PythonParser
  Team B: Refactor TypeScriptParser
  (No coordination needed)
```

### How to Use the Agent Harness

```bash
# In Claude Code, invoke directly:
/smt-analysis

# Or ask questions that trigger it:
"What breaks if I change Neo4jClient?"
"Can we work on src/parsers independently?"
"Show me the impact analysis for validate_graph"
```

### Under the Hood: A2A Orchestration

The Agent Harness implements **A2A (Agent-to-Agent) orchestration** internally:

```
User Question
     ↓
Orchestrator (Claude Code)
     ├→ Spawns Scout via SMTQueryEngine
     │   (reads graph, gathers verified facts)
     │
     ├→ Routes to Fabler and/or PathFinder (parallel)
     │   (each receives Scout's JSON output)
     │
     └→ Synthesizes final answer
        (file:line locations + action plan)
```

**Why this matters**:
- **Facts first**: Scout verifies symbols exist before Fabler reasons about them
- **Parallel**: Fabler and PathFinder analyze independently (no waiting)
- **No parsing**: All data is structured JSON (no stdout string parsing)
- **Deterministic**: No hallucination risk from string parsing or symbol inference

See [How Agents Use SMT: A2A Approach](#a2a-approach-agent-to-agent-orchestration-recommended) for implementation details and SMTQueryEngine API.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and testing.

---

## License

MIT

---

## Documentation

- **[CLAUDE.md](CLAUDE.md)** — Project guidance, architecture, development workflows

---

## Links

- **GitHub:** https://github.com/budagov-lab/save-my-tokens
- **Issues:** https://github.com/budagov-lab/save-my-tokens/issues

---

## Made with ❤️ for Claude

Built to help Claude (and other agents) understand code faster with less context.
