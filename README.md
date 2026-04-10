# Save My Tokens (SMT)

**Intelligent code context for Claude — without reading entire files.**

SMT builds a **function-level dependency graph** of your codebase and answers specific questions with the smallest possible subgraph. Instead of reading 500-line files, Claude gets the 10 lines that matter.

---

## The Problem

When Claude needs to understand one function, it reads the whole file:

- "What does `GraphBuilder.build` do?" → reads 370 lines
- "Who calls `parse_diff`?" → reads every function in the module
- "What breaks if I rename `Neo4jClient`?" → unrolls the entire dependency tree

Most of those tokens don't matter for the question.

---

## The Solution

Three commands, each answering one question:

```bash
smt definition GraphBuilder        # What is this?
smt context GraphBuilder --depth 2 # What do I need to work on it?
smt impact Neo4jClient --depth 3   # What breaks if I change it?
```

Each returns only the relevant subgraph — bounded by depth, with circular dependencies collapsed.

---

## Quick Start

```bash
git clone https://github.com/budagov-lab/save-my-tokens
cd save-my-tokens
python install.py
```

`install.py` creates a venv, bootstraps pip, installs all dependencies, creates `.env`, and starts Neo4j via Docker. First run takes 5–10 minutes (PyTorch is ~2 GB).

Requires Python 3.11+ from python.org (not Microsoft Store — missing `ensurepip`) and Docker.

```bash
# Point SMT at your codebase and build the graph
smt build --dir /path/to/your/project

# Verify it worked
smt status
```

---

## Query Modes

### `definition` — What is this?

Single-hop lookup: signature, docstring, immediate callees.

```
$ smt definition GraphBuilder

GraphBuilder  [Class]
  file: src/graph/graph_builder.py:23
  sig:  class GraphBuilder:
  doc:  Orchestrates the full pipeline: Parse → Index → Graph Nodes → Graph Edges.

  calls (3):
    _parse_all_files     graph_builder.py
    _create_nodes        graph_builder.py
    _create_edges        graph_builder.py

  HEAD 1d27a7a  [✓] fresh
```

### `context` — What do I need to work on this?

Bounded bidirectional traversal: callees + callers up to `--depth` hops, with cycles collapsed.

```
$ smt context GraphBuilder --depth 2

GraphBuilder  [Class]
  ...

  calls (3): _parse_all_files, _create_nodes, _create_edges

  [Cycle: CallAnalyzer._infer_edge_type → _resolve_target → _infer_edge_type]
    2 functions collapsed

  callers (1):
    cmd_build  smt_cli.py

  context: nodes=7 edges=5 depth=2 cycles=1
```

Add `--compress` to strip trivial pass-through functions and cut output further:

```
$ smt context GraphBuilder --depth 2 --compress
  context: nodes=7→4 edges=5→3  (3 bridge functions removed)
```

### `impact` — What breaks if I change this?

Reverse traversal: all callers grouped by distance from the root symbol.

```
$ smt impact Neo4jClient --depth 3

Impact: Neo4jClient  [Class]
  file: src/graph/neo4j_client.py:40

  depth 1 — direct callers (5):
    GraphBuilder          graph_builder.py
    IncrementalUpdater    incremental/updater.py
    SMTQueryEngine        agents/query_engine.py
    ...

  depth 2 — indirect callers (3):
    cmd_build, cmd_diff, cmd_status

  impact: total=8 depth=2 cycles=0
```

---

## Other Commands

```bash
# Semantic search (local embeddings, no API calls)
smt search "cycle detection"

# Sync graph after commits (incremental, ~10x faster than full rebuild)
smt diff HEAD~1..HEAD

# Full rebuild
smt build --clear

# Graph health: node/edge counts, git freshness
smt status

# Manage Neo4j
smt docker up | down | status

# Configure a project (writes .claude/settings.json with hooks)
smt setup [--dir PATH]
```

---

## CLI Reference

```
smt build [--dir PATH]         Build or sync graph
smt build --check              Show graph statistics
smt build --clear              Wipe and rebuild

smt definition SYMBOL          1-hop lookup
smt context SYMBOL [--depth N] [--compress]   Bidirectional context
smt impact SYMBOL [--depth N]  Reverse traversal
smt callers SYMBOL             Shorthand for context (callers only)
smt search QUERY               Semantic search by meaning

smt diff [RANGE]               Incremental sync (default: HEAD~1..HEAD)
smt status                     Graph health check

smt docker up|down|status      Manage Neo4j container
smt setup [--dir PATH]         Configure project hooks
```

---

## Agent Integration

### CLI (subprocess)

Works from any language or agent framework:

```bash
smt definition validate_graph
smt impact GraphBuilder.__init__ --depth 3
smt context Neo4jClient --depth 2 --compress
```

### Python API (`SMTQueryEngine`)

For structured agent workflows without subprocess overhead:

```python
from src.agents.query_engine import SMTQueryEngine

engine = SMTQueryEngine()

result = engine.definition("GraphBuilder")
# → {"found": True, "name": "GraphBuilder", "file": "...", "line": 23, "callees": [...]}

result = engine.context("GraphBuilder", depth=2, compress=True)
# → {"found": True, "nodes": [...], "edges": [...], "cycles": [...], "bridges_removed": 3}

result = engine.impact("Neo4jClient", depth=3)
# → {"found": True, "callers_by_depth": {1: [...], 2: [...]}, "total_callers": 8}

results = engine.search("cycle detection", top_k=5)
# → [{"name": "...", "file": "...", "score": 0.95}, ...]

engine.close()
```

All methods return JSON-serializable dicts with no stdout side effects.

### Agent Harness (Scout / Fabler / PathFinder)

SMT ships a team of specialized subagents for multi-step analysis in Claude Code:

| Agent | Question it answers |
|---|---|
| **Scout** | "What is X? Who calls it? Is the graph fresh?" |
| **Fabler** | "What breaks if I change X? In what order do I make the changes?" |
| **PathFinder** | "Which parts of this module can I refactor independently?" |

Invoke via Claude Code:

```
/smt-analysis
```

Or ask naturally — "what breaks if I change X?" triggers Scout → Fabler automatically.

---

## Architecture

```
Source Code (Python / TypeScript)
        ↓  Tree-sitter parsing
   SymbolIndex  (functions, classes, imports)
        ↓  CallAnalyzer
   Neo4j Graph  (nodes + CALLS / DEFINES / IMPORTS / INHERITS edges)
        ↓
  ┌─────────────────────────────────┐
  │  definition  context  impact    │  ← three query modes
  │  CycleDetector (Tarjan's SCC)   │  ← prevents unbounded expansion
  │  Compressor (bridge removal)    │  ← reduces output size
  │  Validator (git freshness)      │  ← warns when graph is stale
  └─────────────────────────────────┘
        ↓
   CLI / SMTQueryEngine / Agents
```

**Embeddings**: Local `all-MiniLM-L6-v2` (384-dim, via SentenceTransformers) stored in `.smt/embeddings/`. No API calls, fully offline.

**Project isolation**: All graph nodes carry a `project_id` (SHA256 of project root path) so multiple projects share one Neo4j instance without colliding.

---

## Requirements

- Python 3.11+ (from python.org, not Microsoft Store)
- Docker (for Neo4j, or point to an existing instance)
- Git

---

## License

MIT
