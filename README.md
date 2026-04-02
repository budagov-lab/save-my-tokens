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

## Core Concept

**Code is not files—it's a graph.**

```
Source Code → Parse → Symbol Index → Neo4j Graph ⟷ MCP Server ⟷ Claude Agent
                                   ↓
                              FAISS Vector DB (semantic search)
```

Agents interact with the MCP server via **native tools**:

```python
# Agent calls MCP tool (native interface)
result = graph_api.get_context("process_data", depth=2, include_callers=True)

# Response: just what's needed (287 tokens vs 5000+ for full file)
{
  "symbol": {"name": "process_data", "file": "src/processor.py", ...},
  "dependencies": [...],
  "callers": [...],
  "token_estimate": 287
}
```

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

### System Overview

```
┌─────────────────────────────────────────────────────────┐
│ Claude / Claude Desktop / Claude Code (Agent)           │
└────────────────┬────────────────────────────────────────┘
                 │ (MCP Protocol)
                 ↓
        ┌────────────────────┐
        │  MCP Server        │ (stdio transport)
        │  (src/mcp_server/) │
        └────────┬───────────┘
                 │
    ┌────────────┴─────────────┐
    ↓                          ↓
┌──────────────┐      ┌─────────────────┐
│ ServiceContainer  │      │ Query Service  │
│ (singletons)     │      │ (facades)      │
└──────┬───────┘      └────────┬────────┘
       │                       │
  ┌────┴────────┬──────┬─────────────┬────────┐
  ↓             ↓      ↓             ↓        ↓
SymbolIndex  Neo4j  FAISS      Incremental Scheduler
              Graph  Embeddings  Updates     Engine
```

### Components

**Parsers** (`src/parsers/`)
- Tree-sitter based symbol extraction: Python, TypeScript, Go, Rust, Java
- Import resolution (handles relative imports, aliasing)
- In-memory symbol index with O(1) lookups by name/file/type

**Graph** (`src/graph/`)
- Neo4j integration for persistent dependency graph storage
- Node types: File, Module, Function, Class, Variable, Type, Interface
- Edge types: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS
- Call graph analysis, transitive dependency computation
- Graceful fallback to in-memory graph if Neo4j unavailable

**MCP Server** (`src/mcp_server/`)
- **NEW:** Model Context Protocol server (replaces REST API)
- Stateful session management via lifespan context
- 10 MCP tools wrapping all Graph API + Phase 2 operations
- Async tools with streaming support
- Stdio transport for agent subprocess model

**Query Service** (`src/api/query_service.py`)
- Core query brain orchestrating graph, embeddings, conflict analysis
- 4 query operations (context, subgraph, search, validate-conflicts)
- Token estimation and response optimization

**Contracts** (`src/contracts/`)
- Contract extraction (Python function signatures, docstrings, types)
- Breaking change detection (7 change types)
- Compatibility scoring (0-1 scale)

**Incremental Updates** (`src/incremental/`)
- Git diff parsing (identify changed files/symbols)
- Transactional delta application to graph
- Graph consistency validation

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
