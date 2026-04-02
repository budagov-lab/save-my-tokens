# SMT: Code Context for AI Agents

**Make Claude understand your codebase efficiently. No more full-file context bloat.**

SMT is an MCP server that gives Claude agents smart, minimal code context. Instead of loading entire files (wasting 90% of tokens), SMT provides exactly what's needed: symbol definitions, callers, dependencies, and breaking changes. 

**Result:** 11x more problems solved per conversation | Faster inference | Lower token costs

**What you get:** One-click installation → 10 MCP tools for code analysis → Claude understands your code instantly

## The Problem

Claude agents waste tokens and slow down when working with code:

1. **Full-file bloat** — You ask "show me the login function", Claude loads 500 lines (5000 tokens wasted)
2. **No code understanding** — Claude doesn't know who calls what, so it can't parallelize safely
3. **Blind search** — Searching by name misses where code is actually used
4. **No conflict detection** — Can't tell if two changes conflict until you test them

**Reality:** For a 50K LOC codebase, Claude needs 10x more tokens than it should.

## The Solution

SMT gives Claude agents a smart code map:

- **Minimal context** — Instead of 5000 tokens, get 287 tokens (symbol + callers + dependencies)
- **Safe parallelization** — Know which code changes can run in parallel automatically
- **Semantic search** — Find "password validation" logic without grepping for "password"
- **Breaking change detection** — Know before you refactor if you'll break existing code
- **Git-aware updates** — Graph stays in sync with your code (no re-parse needed)

**The benefit:** Solve 11x more code problems per conversation, faster inference, lower API costs.

## Installation

**Two paths depending on your needs:**

### 🚀 Path 1: One-Click Setup (Recommended for most users)

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

✅ **3 minutes | Automated | Zero hassle**

### 👨‍💻 Path 2: Developer Setup (For contributors & customization)

```bash
git clone https://github.com/budagov-lab/smt-graph.git
cd smt-graph
python -m venv venv && source venv/bin/activate
pip install -e .
```

✅ **5 minutes | Full control | Edit code freely**

### 📖 Details

See [INSTALL_PATHS.md](INSTALL_PATHS.md) for detailed comparison and when to use each path.

### ⚙️ Configure Claude Code

After installation, add 5 lines to `~/.claude/settings.json`:

```json
{
  "mcpServers": [{
    "name": "smt-graph",
    "command": "python",
    "args": ["/path/to/smt-graph/run_mcp.py"]
  }]
}
```

Restart Claude Code. Done!

### Start Using

```bash
python run_mcp.py
```

Then ask Claude Code about your code!

## How It Actually Works: The Incremental Analysis Pipeline

**Code is not files—it's a graph that stays fresh with your commits.**

SMT's pipeline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ GitHub/Git Repository                                                  │
│ (developer commits code changes)                                       │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (git diff HEAD~1)
┌─────────────────────────────────────────────────────────────────────────┐
│ DiffParser (5ms)                                                        │
│ • Parse git diff output                                                │
│ • Identify changed files (added/modified/deleted)                      │
│ • Extract line counts                                                   │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (FileDiff[])
┌─────────────────────────────────────────────────────────────────────────┐
│ Incremental Parsers (100ms for 2-3 changed files)                      │
│ • Parse ONLY the changed files (not entire codebase)                   │
│ • Extract symbols: functions, classes, imports, types                  │
│ • Identify what changed at symbol level                                │
│ ⚡ 46.7x faster than parsing entire repo                               │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (SymbolDelta)
┌─────────────────────────────────────────────────────────────────────────┐
│ IncrementalUpdater (50ms)                                              │
│ • Transactional: Backup → Update → Commit (or rollback)                │
│ • Update in-memory SymbolIndex                                         │
│ • Update Neo4j with new/deleted/modified symbols + edges               │
│ ✓ Guarantee: Index and Neo4j always stay in sync                       │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (Updated ~150ms total)
┌─────────────────────────────────────────────────────────────────────────┐
│ Neo4j Graph (Always Fresh)                                              │
│ • Nodes: Files, Functions, Classes, Variables, Types                  │
│ • Edges: IMPORTS, CALLS, DEPENDS_ON, DEFINES, INHERITS, etc.          │
│ • Reflects latest code changes within milliseconds                     │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (MCP Server: stdio protocol)
┌─────────────────────────────────────────────────────────────────────────┐
│ MCP Tools (stateful session)                                            │
│ • get_context("symbol")       → 287 tokens (vs 5000+ from full file)   │
│ • get_subgraph("symbol")      → Full dependency tree                   │
│ • semantic_search("query")    → Find code by meaning                   │
│ • validate_conflicts()         → Safe parallelization                   │
│ ⚡ 88% token savings per query vs traditional Grep+Read                │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │
                        ▼ (Tools available to agent immediately)
┌─────────────────────────────────────────────────────────────────────────┐
│ Claude Agent / Claude Code                                              │
│ • Queries fresh graph with accurate dependency info                    │
│ • Makes informed decisions about code changes                          │
│ • Detects conflicts before parallelizing tasks                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### What This Means

**Without SMT (Naive Approach):**
- Parse entire 50K LOC codebase → 7 seconds
- Reload into memory every time code changes → waste
- Search by filename → miss actual usage patterns
- Agent reads entire files → 5000 tokens wasted per lookup

**With SMT (Incremental Pipeline):**
- Parse ONLY changed files → 150ms per commit
- Graph updates atomically → always fresh
- Neo4j knows all relationships → find real usage
- Agent queries semantic graph → 287 tokens per lookup (88% savings)

### Agent Usage (Real Code)

```python
# Agent calls MCP tool (native interface)
result = await mcp.call_tool("get_context", {
    "symbol": "process_data",
    "depth": 2,
    "include_callers": True
})

# Response: exactly what's needed, no bloat
{
  "symbol": {
    "name": "process_data",
    "file": "src/processor.py:42",
    "signature": "def process_data(input: str) -> Dict",
    "docstring": "...",
  },
  "dependencies": [
    {"name": "validate_input", "type": "call"},
    {"name": "logger", "type": "import"}
  ],
  "callers": [
    {"symbol": "batch_process", "file": "src/batch.py:15"},
    {"symbol": "api_endpoint", "file": "src/api.py:88"}
  ],
  "token_estimate": 287  # vs 5000+ for full file
}
```

## Performance: Numbers That Matter

Audited across real codebases (Flask 3.2MB, Requests 8.7MB, Vue 9.5MB):

| Metric | Incremental (SMT) | Full Re-Parse | Improvement |
|--------|-------------------|---------------|-------------|
| **Per Code Lookup** | 243 tokens, 45ms | 2,027 tokens, 850ms | 88% savings, 18.9x faster |
| **Developer Session** (100 lookups) | 24.3K tokens | 202.8K tokens | **178.5K tokens saved** |
| **Weekly Sprint** (500 lookups) | 121.5K tokens | 1.01M tokens | **~892K tokens saved** |
| **Parse Time** (2-file commit) | 150ms | 7 seconds | **46.7x faster** |

**Translation:** SMT frees up enough token budget to solve 10x more problems per week.

---

## MCP Tools (10 total)

**Graph Queries:**
- `get_context` — Symbol definition + direct dependencies + callers
- `get_subgraph` — Full dependency graph (DAG) for a symbol
- `semantic_search` — Find code by meaning or name
- `validate_conflicts` — Detect parallelization conflicts before execution

**Contracts & Breaking Changes:**
- `extract_contract` — Parse function signatures, docstrings, pre/postconditions
- `compare_contracts` — Detect breaking changes between old/new implementations

**Incremental Updates:**
- `parse_diff` — Parse git diff to identify changed files
- `apply_diff` — Update graph from file changes (transactional)

**Task Scheduling:**
- `schedule_tasks` — Build execution plan with parallelization
- `execute_tasks` — Run tasks with dependency resolution, retries, and timeout handling

**Why MCP?**
- **Stateful:** Graph stays loaded (no per-request parsing)
- **Native agent integration:** Claude understands MCP natively
- **Streaming:** Async tools, large responses supported
- **Token efficient:** No HTTP serialization overhead
- **Session awareness:** Agent context preserved across tool calls

## Implementation Status

**Phase 1 (MVP) - Complete:**
- Symbol extraction: Python, TypeScript parsers
- Dependency graph: Neo4j-backed with 9 edge types
- Query API: 4 endpoints (minimal, no longer REST-only)
- Semantic search: FAISS + optional embeddings
- Conflict detection: Graph-based analysis

**Phase 2 (Enhancements) - Complete:**
- Feature 1: Incremental Updates (git diff parsing, transactional graph updates)
- Feature 2: Contract Extraction (breaking change detection, 7 change types)
- Feature 3: Multi-Language Support (Python, TypeScript, Go, Rust, Java)
- Feature 4: Task Scheduling (DAG-based, topological sort, parallel execution)

**MCP Migration - Complete:**
- 10 MCP tools (graph queries, contracts, incremental, scheduling)
- Stateful session management (graph loaded once)
- Graceful degradation (works without Neo4j/embeddings)
- Stdio transport (subprocess model for Claude Desktop/Code)

**Test Coverage:**
- 202 passing tests (85%+ coverage)
- MCP server startup verified
- Phase 2 features validated

## Architecture

### System Overview: The Complete Pipeline

```
GITHUB/GIT (Source of Truth)
    ↓
    │ (developer commits)
    ▼
DIFFPARSER (src/incremental/)
    ├─ Detects changed files
    └─ Outputs: FileDiff[]
    ↓
INCREMENTAL PARSERS (src/parsers/)
    ├─ Parse ONLY changed files
    ├─ Extract: functions, classes, imports
    └─ Outputs: SymbolDelta
    ↓
INCREMENTALUPDATER (src/incremental/)
    ├─ Transactional update (backup → update → commit)
    ├─ Update in-memory SymbolIndex
    └─ Update Neo4j Graph
    ↓
    │ (index + graph stay in sync)
    ▼
NEO4J GRAPH (Always Fresh)
    │ (available to MCP server)
    ▼
MCP SERVER (src/mcp_server/)
    ├─ Stateful session (graph loaded once)
    ├─ 10 MCP tools
    └─ Stdio transport
    ↓
    │ (MCP protocol)
    ▼
CLAUDE AGENT
    ├─ get_context() → 287 tokens (vs 5000+ from files)
    ├─ get_subgraph() → Full dependency tree
    ├─ search() → Semantic search
    └─ validate_conflicts() → Safe parallelization
```

### Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Claude / Claude Desktop / Claude Code (Agent)           │
└────────────────┬────────────────────────────────────────┘
                 │ (MCP Protocol, stdio)
                 ↓
        ┌────────────────────┐
        │  MCP Server        │ (src/mcp_server/)
        │  (10 tools)        │ Stateful session
        └────────┬───────────┘
                 │
    ┌────────────┴─────────────────┬─────────────┐
    ↓                              ↓             ↓
SERVICECONTAINER          QUERYSERVICE    DIFFPARSER
(singletons: all            (facades)   (git analysis)
 services loaded once)           │
    │                    ┌───────┴────────┐
    │                    ↓                ↓
    │              QUERYLOGIC      CONFLICTANALYZER
    │                    │                ↓
  ┌─┴──────────┬────────┴──┬─────────┬────────┬──────────┐
  ↓            ↓           ↓         ↓        ↓          ↓
SymbolIndex  Neo4j      FAISS   Incremental Contract  Scheduler
             Graph    Embeddings Updater    Extractor  Engine
```

### Components

**Incremental Analysis Pipeline** (The Core Innovation)

**DiffParser** (`src/incremental/diff_parser.py`)
- Parse git diff output to identify changed files
- Status detection: added/modified/deleted/renamed
- Line counting per file
- Cost: ~5ms

**Incremental Parsers** (`src/parsers/`, incremental mode)
- Parse ONLY changed files (not entire codebase)
- Tree-sitter based symbol extraction: Python, TypeScript, Go, Rust, Java
- Extract functions, classes, imports at symbol level
- Cost: ~100ms for 2-3 changed files (vs ~5 sec for full repo)

**SymbolDelta** (`src/incremental/symbol_delta.py`)
- Represent symbol-level changes (added/deleted/modified)
- Track which symbols changed and why
- Metadata: old_symbol, new_symbol, change_reason

**IncrementalUpdater** (`src/incremental/updater.py`)
- Atomically apply deltas to both in-memory index and Neo4j
- Backup current state before updating (for rollback)
- Transactional semantics: all-or-nothing
- Rollback guarantee: if Neo4j fails, index is restored
- Cost: ~50ms (Neo4j transaction)
- **Guarantee:** Index and Neo4j always stay in sync

---

**Core Components**

**Parsers** (`src/parsers/`)
- Tree-sitter based symbol extraction: Python, TypeScript, Go, Rust, Java
- Import resolution (handles relative imports, aliasing)
- In-memory symbol index with O(1) lookups by name/file/type
- **Incremental mode:** Can parse just changed files

**Graph** (`src/graph/`)
- Neo4j integration for persistent dependency graph storage
- Node types: File, Module, Function, Class, Variable, Type, Interface
- Edge types: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS
- Call graph analysis, transitive dependency computation
- **Always fresh** (updated via IncrementalUpdater on each commit)
- Graceful fallback to in-memory graph if Neo4j unavailable

**MCP Server** (`src/mcp_server/`)
- Model Context Protocol server (stdio transport)
- Stateful session management via lifespan context
- 10 MCP tools wrapping Graph API + Phase 2 operations
- Async tools with streaming support
- **Graph is pre-loaded and stays fresh**

**Query Service** (`src/api/query_service.py`)
- Core query brain orchestrating graph, embeddings, conflict analysis
- 4 query operations (context, subgraph, search, validate-conflicts)
- Token estimation and response optimization

**Contracts** (`src/contracts/`)
- Contract extraction (Python function signatures, docstrings, types)
- Breaking change detection (7 change types)
- Compatibility scoring (0-1 scale)

**Task Scheduling** (`src/agent/`)
- Task DAG builder with conflict detection
- Topological sorting + phase partitioning
- Parallel execution engine with retries and timeout handling

**Embeddings** (`src/embeddings/`)
- FAISS vector database for semantic search
- OpenAI text-embedding-3-small integration
- Fallback substring search when embeddings unavailable

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Agent Interface | MCP (Model Context Protocol) 1.26.0 |
| Transport | Stdio (subprocess model) |
| Parser | Tree-sitter + Language-specific grammars |
| Graph DB | Neo4j 5.x (optional, in-memory fallback) |
| Vector DB | FAISS (optional, substring fallback) |
| Embeddings | OpenAI API (optional) |
| Task Scheduling | Python asyncio + concurrent.futures |
| Testing | pytest 7.x+ with async support |
| Container | Docker Compose |

All components gracefully degrade if optional services unavailable.

## Documentation

**Getting Started:**
- **[INSTALL_PATHS.md](INSTALL_PATHS.md)** — Choose your installation path (one-click vs developer)
- **[INSTALL.md](INSTALL.md)** — Step-by-step setup guide
- **[POSITIONING.md](POSITIONING.md)** — What SMT does & why you need it

**Understanding the Pipeline (Recommended):**
- **[COMPLETE_EXPLANATION.md](docs/internal/COMPLETE_EXPLANATION.md)** ⭐ — End-to-end overview of how SMT works with Git (start here!)
- **[GIT_WORKFLOW_EXPLANATION.md](docs/internal/GIT_WORKFLOW_EXPLANATION.md)** — Detailed technical breakdown of incremental analysis
- **[INCREMENTAL_FLOW_DIAGRAM.txt](docs/internal/INCREMENTAL_FLOW_DIAGRAM.txt)** — Visual flow diagram of entire pipeline
- **[AUDIT_REPORT.md](docs/internal/AUDIT_REPORT.md)** — Token efficiency audit with real numbers
- **[DOCUMENTATION_INDEX.md](docs/internal/DOCUMENTATION_INDEX.md)** — Navigation guide for all documentation

**Usage:**
- **[MCP Examples](docs/MCP_EXAMPLES.md)** — 6 real-world usage examples
- **[MCP Cheatsheet](docs/MCP_CHEATSHEET.md)** — Quick reference for all 10 tools

**Deep Dives:**
- **[MCP Server Guide](docs/FEATURE4_SCHEDULING_GUIDE.md)** — MCP tools, session management, APIs
- **[Incremental Updates Guide](docs/INCREMENTAL_UPDATES_GUIDE.md)** — Git diff parsing, delta application
- **[Contract Extraction Guide](docs/CONTRACT_EXTRACTION_GUIDE.md)** — Function contracts, breaking changes
- **[Architecture Guide](docs/ARCHITECTURE.md)** — Data flow, design decisions, trade-offs
- **[Phase 2 Specification](PHASE_2_SPECIFICATION.md)** — Complete feature specifications and test plans
- **[Testing](docs/TESTING.md)** — Test structure and strategy
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — Common issues and fixes

## Project Structure

```
src/
  parsers/              # Language parsers (Python, TS, Go, Rust, Java) + symbol extraction
  graph/                # Neo4j client + dependency analysis
  embeddings/           # FAISS + semantic search
  api/                  # Legacy: FastAPI server (for backward compatibility)
  mcp_server/           # NEW: MCP server + 10 tools
  contracts/            # Contract extraction + breaking change detection
  incremental/          # Git diff parsing + transactional updates
  agent/                # Agent implementations + task scheduling
  evaluation/           # Metrics collection and reporting
  performance/          # Profiling tools

tests/
  unit/                 # Parser, graph, contract, incremental tests
  integration/          # End-to-end tests
  mcp/                  # MCP server startup test
  fixtures/             # Test repositories

docs/
  FEATURE4_SCHEDULING_GUIDE.md     # MCP tools + task scheduling
  INCREMENTAL_UPDATES_GUIDE.md     # Git diff + delta application
  CONTRACT_EXTRACTION_GUIDE.md     # Contracts + breaking changes
  ARCHITECTURE.md                  # System design
  TESTING.md                       # Test strategy
  TROUBLESHOOTING.md               # Setup and debugging
```

## Development

### Run Tests
```bash
pytest tests/ -v              # All tests
pytest tests/unit/ -v         # Unit tests only
pytest tests/integration/ -v  # Integration tests only
pytest tests/mcp/ -v          # MCP server startup
pytest --cov=src tests/       # With coverage
```

### Start MCP Server (Development)
```bash
python run_mcp.py
```

Server listens on stdin/stdout (stdio transport) for MCP client connections.

### Build Graph on Sample Repository
```bash
python -c "
from src.graph.graph_builder import GraphBuilder
builder = GraphBuilder('path/to/repo')
builder._parse_all_files()
print(f'Extracted {len(builder.symbol_index.get_all())} symbols')
"
```

## Project Status

**Phase 1 ✅ Complete** — Graph API Foundation (MVP)
- Symbol extraction (Python, TypeScript)
- Dependency graph (Neo4j)
- Query API (minimal context, semantic search)
- Conflict detection for parallelization

**Phase 2 ✅ Complete** — Enhancements
- **Feature 1:** Incremental Updates (git diff parsing, transactional updates)
- **Feature 2:** Contract Extraction (function signatures, breaking change detection)
- **Feature 3:** Multi-Language Support (Go, Rust, Java parsers)
- **Feature 4:** Task Scheduling (DAG-based parallelization with dependency resolution)

**Phase 3 🔮 Planned** — Advanced Capabilities
- Distributed scheduling (multi-agent parallel work)
- Priority-based task ordering
- Resource-aware parallelization
- Automated agent evaluation

## Contributing

Contributions welcome. Please:

1. Fork and create a feature branch (`feat/description` or `fix/description`)
2. Write tests for new functionality (follow `tests/` structure)
3. Ensure all tests pass: `pytest tests/ -v`
4. Ensure code passes linting: `pylint src/ --rcfile=.pylintrc`
5. Submit a pull request with clear description of changes

## License

MIT License. See LICENSE file for details.

---

**Built to make code-aware agents smarter, faster, and cheaper to run.**

For questions, issues, or discussions, open a GitHub issue or check [Troubleshooting](docs/TROUBLESHOOTING.md).

---

## How It Works

**Before SMT:** You ask Claude to refactor login code
```
Claude: "I need to see the whole auth.py file" (loads 5000 tokens)
Claude: "I don't know who calls validate_token, might break something"
Time: 5 minutes of back-and-forth
```

**With SMT:** You ask Claude to refactor login code
```
Claude calls: get_context("validate_token")
Result: 287 tokens with definition + 8 callers + breaking changes
Claude: "Found it, 8 places call this. My changes don't break anything. Safe to parallelize with other tasks."
Time: Instant
```

## Real Example: Refactoring Authentication

```python
# 1. Claude asks: "Show me validate_token and everything that calls it"
context = await mcp.call_tool("get_context", symbol="validate_token", include_callers=True)
# Returns: function code + 8 callers + dependencies (287 tokens, not 5000)

# 2. Claude checks: "Will my changes break anything?"
changes = await mcp.call_tool("compare_contracts", old_code=old, new_code=new)
# Returns: breaking_changes=[], is_compatible=true

# 3. Claude asks: "Can I parallelize these changes?"
plan = await mcp.call_tool("schedule_tasks", tasks=[
    {"id": "refactor_auth", "target_symbols": ["validate_token"]},
    {"id": "update_tests", "target_symbols": ["test_auth.py"]},
    {"id": "update_docs", "target_symbols": ["README.md"]}
])
# Returns: All 3 can run in parallel (no conflicts)

# 4. Claude executes with automatic retries and timeout handling
result = await mcp.call_tool("execute_tasks", tasks=plan)
# All done!
```
