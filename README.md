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

`install.py` creates a venv, installs all dependencies, and starts Neo4j via Docker. First run takes 5–10 minutes (PyTorch is ~2 GB).

Requires Python 3.11+ from [python.org](https://python.org) (not Microsoft Store — missing `ensurepip`) and Docker.

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
    ...

  depth 2 — indirect callers (3):
    cmd_build, cmd_sync, cmd_status

  impact: total=8 depth=2 cycles=0
```

### `view` — Show the source

Jump directly to a symbol's source lines without reading the whole file:

```bash
smt view GraphBuilder            # symbol source lines only
smt view GraphBuilder --context 5  # with 5 lines of surrounding context
```

---

## More Commands

```bash
# Semantic search (local embeddings, no API calls)
smt search "cycle detection algorithm"

# Sync graph after commits (incremental, ~10x faster than full rebuild)
smt sync                         # default: HEAD~1..HEAD
smt sync main..feature-branch    # custom range

# Enumerate symbols
smt list --module src/parsers    # all symbols in a path
smt scope graph_builder          # file exports, imports, internal symbols
smt unused                       # dead code candidates

# Architecture analysis
smt cycles                       # circular dependencies
smt hot --top 10                 # most-called symbols (coupling hotspots)
smt complexity --top 10          # fan-in × fan-out god functions
smt bottleneck --top 5           # cross-file bridge symbols
smt modules                      # files ranked by coupling
smt path A B                     # shortest call path between two symbols

# Breaking change detection
smt breaking-changes MyFunction  # compare HEAD~1..HEAD
smt breaking-changes MyFunction --before v1.0 --after v1.1

# PR review
smt changes main..feature-branch # symbols in changed files + caller counts

# Graph management
smt build --check                # show graph stats
smt build --clear                # wipe and rebuild from scratch
smt status                       # node/edge counts, git freshness
smt start                        # start Neo4j container
smt stop                         # stop Neo4j container
smt setup [--dir PATH]           # configure project (.claude/settings.json + hooks)
```

---

## CLI Reference

```
smt build [--dir PATH] [--check] [--clear]
smt sync [RANGE]

smt definition SYMBOL [--file SUBSTR] [--compact] [--brief]
smt context   SYMBOL [--depth N] [--compress] [--callers] [--compact] [--brief]
smt impact    SYMBOL [--depth N] [--compress] [--compact] [--brief]
smt view      SYMBOL [--file SUBSTR] [--context N]
smt search    QUERY  [--top N]

smt list      [--module PATH]
smt scope     FILE
smt unused
smt cycles
smt hot       [--top N]
smt complexity [--top N]
smt bottleneck [--top N]
smt modules
smt path      A B
smt changes   [RANGE]
smt breaking-changes SYMBOL [--before REF] [--after REF]

smt status
smt start
smt stop
smt setup     [--dir PATH]
```

**Output flags** (apply to `definition`, `context`, `impact`):
- `--compact` — single-line format, 40–60% fewer tokens
- `--brief` — suppress docstrings
- `--compress` — remove trivial pass-through functions from context

---

## Agent Integration

SMT works as a subprocess from any agent framework:

```bash
smt definition validate_graph
smt context GraphBuilder --depth 2 --compress
smt impact Neo4jClient --depth 3
```

### Claude Code

Run `smt setup` once in your project to install hooks. This writes `.claude/settings.json` with:
- **PreToolUse hooks** — blocks raw file reads and greps, routes them through SMT first
- **`SMT_AGENT=1`** env var — automatically suppresses log noise and applies compact output in agent sessions

Then use the built-in skill:

```
/smt-analysis
```

Or ask naturally — "what breaks if I change X?" / "architecture health check" / "what parts can be worked on independently?"

---

## Architecture

```
Source Code (Python / TypeScript / Go / Rust / Java)
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
   CLI (smt) / Claude Code skill
```

**Embeddings**: Local `all-MiniLM-L6-v2` (384-dim, SentenceTransformers) stored in `.smt/`. No API calls, fully offline.

**Project isolation**: All graph nodes carry a `project_id` (SHA256 of project root path) so multiple projects share one Neo4j instance without colliding.

---

## Requirements

- Python 3.11+ (from python.org, not Microsoft Store)
- Docker (for Neo4j)
- Git

---

## License

MIT
