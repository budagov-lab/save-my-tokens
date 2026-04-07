# Save My Tokens (SMT)

**Intelligent code context for Claude — without reading entire files.**

Instead of asking Claude to read 500-line files, SMT queries a **semantic dependency graph** of your codebase and returns only the **smallest relevant subgraph**. Result: **60-90% fewer tokens**, **sub-20ms queries**, and **cycle-safe bounds**.

---

## The Problem

Claude reads **entire files** to understand one function:
- "What does `GraphBuilder` do?" → reads 200 lines, uses 500+ tokens
- "Who calls `parse_diff`?" → reads all 40 functions in the file
- "What breaks if I change `Neo4jClient`?" → reads deeply into the dependency tree

**This is wasteful.** Most of those lines don't matter for the question.

---

## The Solution

SMT builds a **graph of function-level dependencies** from your code, then answers specific questions with **minimal context**:

```bash
# What is this? (definition + signature)
smt definition GraphBuilder           # ~13ms, ~100 tokens

# What do I need to work on this? (working context)
smt context GraphBuilder --depth 2    # ~19ms, ~200 tokens

# What breaks if I change this? (impact analysis)
smt impact Neo4jClient --depth 3      # ~23ms, ~250 tokens
```

---

## Key Features

✅ **Three Query Modes** — Each answers one agent question (definition / context / impact)

✅ **Cycle-Safe** — Detects circular dependencies (Tarjan's SCC algorithm), never spirals into 10k nodes

✅ **Fast** — Sub-20ms queries with automatic connection pooling

✅ **Validated** — Shows git freshness status ("fresh" or "N commits behind")

✅ **Compressed** — Removes trivial bridge functions, optional `--compress` flag saves 40-50% tokens

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
smt build        # Parses src/, builds Neo4j graph (~30s for large projects)
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
**Latency:** ~13ms | **Tokens:** ~100 | **Depth:** 1 hop

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

  context: nodes=7 edges=5 depth=2 cycles=1 ~tokens=210
  HEAD 1d27a7a  [✓] fresh
```

**Use when:** Agent refactoring, understanding dependencies, writing code
**Latency:** ~19ms | **Tokens:** ~200-300 | **Depth:** 2-3 hops (bounded)

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

  impact: nodes=12 depth=2 cycles=1 ~tokens=280
  HEAD 1d27a7a  [✓] fresh
```

**Use when:** Planning refactors, understanding breaking changes, impact analysis
**Latency:** ~23ms | **Tokens:** ~250-350 | **Depth:** 3-4 hops (reverse)

---

## Advanced Usage

### Compression (reduce tokens 40-50%)

```bash
# Remove "bridge" functions (trivial forwarders with no logic)
smt context GraphBuilder --depth 2 --compress

context: nodes=7→4 edges=5→3 depth=2 cycles=1 ~tokens=130
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

## Performance

### Latency

| Query | Latency | 99th Percentile |
|---|---|---|
| definition | 13ms | 15ms |
| context --depth 2 | 19ms | 26ms |
| impact --depth 3 | 23ms | 31ms |

(Tested on 6,194-node graph with connection pooling)

### Token Savings

| Scenario | Raw File | SMT | Savings |
|---|---|---|---|
| Single function definition | 500-600 | 50-100 | **85-90%** |
| Function + 2-hop context | 800-1200 | 200-300 | **70-75%** |
| Impact analysis (10+ callers) | 1500+ | 250-350 | **75-80%** |

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

### Example 1: Understanding a Function

```python
# Agent prompt: "Explain what validate_graph does"
# Instead of reading 50-line file:

result = subprocess.run(["smt", "definition", "validate_graph"])
# Returns: signature, docstring, 1-hop callees (~50 tokens)
# Agent explains clearly from minimal context
```

### Example 2: Refactoring Safely

```python
# Agent prompt: "I want to rename GraphBuilder.__init__. What breaks?"

result = subprocess.run(["smt", "impact", "GraphBuilder.__init__", "--depth", "3"])
# Returns: all callers grouped by distance (~250 tokens)
# Agent identifies all breaking changes before making edits
```

### Example 3: Code Review

```python
# Agent: "Review this commit for impact"

result = subprocess.run(["smt", "diff", "HEAD~1..HEAD"])
# Shows: which symbols changed, who depends on them
# Agent reviews in context of actual impact, not entire files
```

---

## FAQ

**Q: Do I need Neo4j?**
A: Yes. You can run it locally (`smt docker up`) or point to an existing instance. Community Edition is free.

**Q: What languages are supported?**
A: Python and TypeScript (via Tree-sitter). More languages can be added.

**Q: How often should I rebuild?**
A: `smt diff` syncs incrementally after commits. Full `smt build` takes ~30s for large projects. Use git hooks for auto-sync.

**Q: Can I use it with Claude?**
A: Yes! Agents can invoke `smt` via Bash:
```bash
$ smt context GraphBuilder --depth 2
```

**Q: What about private codebases?**
A: Everything runs locally. Neo4j stays on your machine.

**Q: Performance on very large codebases (100k+ LOC)?**
A: Tested on 512k-lines (40k+ nodes). Queries still sub-30ms. Neo4j Community can handle millions of nodes.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and testing.

---

## License

MIT

---

## Links

- **GitHub:** https://github.com/budagov-lab/save-my-tokens
- **Issues:** https://github.com/budagov-lab/save-my-tokens/issues
- **Docs:** [FINAL_SUMMARY.md](FINAL_SUMMARY.md) for architecture + design decisions

---

## Made with ❤️ for Claude

Built to help Claude (and other agents) understand code faster with less context.
