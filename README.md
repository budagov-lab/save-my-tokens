# Save My Tokens (SYT)

**A Graph API + MCP server that transforms source code into structured dependency graphs, enabling LLM agents to work efficiently on codebases.**

Agents retrieve **minimal, relevant context** for code modifications instead of loading entire files. Includes 10 MCP tools for dependency queries, breaking change detection, incremental updates, and parallel-safe task execution.

**Current Status:** Phase 2 implementation complete. MCP server production-ready. REST API deprecated.

**Architecture:** MCP (Model Context Protocol) for native agent integration with stateful session management.

## The Problem

LLM agents struggle with code tasks because typical approaches are inefficient:

1. **Full-file retrieval** — loading entire files wastes 90% of context (only 5-10% is relevant to the task)
2. **No dependency awareness** — agents can't safely parallelize work or detect conflicts
3. **Blind symbol search** — name matching misses cross-file dependencies and transitive relationships
4. **Repeated parsing** — REST API reloads the graph on every request

**Result:** Token bloat, slow inference, limited parallelization, wasted compute.

## The Solution

Graph API structures code as a queryable dependency graph **exposed via MCP**:

- **Minimal context extraction** — retrieve only what the agent needs (symbol + direct dependencies)
- **Conflict detection** — identify safe parallelization boundaries automatically
- **Semantic search** — find code patterns by meaning, not just name matching
- **Task scheduling** — automatic parallelization with dependency resolution
- **Incremental updates** — git-aware graph updates without full re-parse
- **Contract awareness** — breaking-change detection before modifications

**Design Goals:** Designed to support 11x more problems per conversation by reducing token overhead compared to naive full-file access.

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional, for Neo4j)
- Claude Desktop or Claude Code (to use MCP server)

### Setup (5 minutes)

```bash
# 1. Clone
git clone https://github.com/budagov-lab/save-my-tokens.git
cd save-my-tokens

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. (Optional) Start Neo4j for full functionality
docker-compose up -d

# 5. Run tests
pytest tests/ -v

# 6. Start MCP server (stdio transport)
python run_mcp.py
```

For Claude Desktop integration, configure in `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "syt-graph": {
      "command": "python",
      "args": ["/path/to/save-my-tokens/run_mcp.py"]
    }
  }
}
```

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
- **[MCP Quick Start](docs/MCP_QUICK_START.md)** — 10-minute setup guide (START HERE!)
- **[MCP Examples](docs/MCP_EXAMPLES.md)** — Real-world usage examples & patterns

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

## How Agents Use SYT

```python
# Example: Agent modifies authentication system
assistant = await load_claude_with_mcp_tools("syt-graph")

# 1. Discover what to modify
context = assistant.call_tool("get_context", symbol="validate_token", depth=2)
print(context)  # Returns: definition + what it calls + what calls it

# 2. Check for breaking changes before modifying
comparison = assistant.call_tool(
    "compare_contracts",
    symbol_name="validate_token",
    old_source=read_file("src/auth.py"),
    new_source="def validate_token(token, check_expiry=True): ..."  # new version
)
print(comparison.is_compatible)  # True/False + severity

# 3. Plan parallel modifications
plan = assistant.call_tool(
    "schedule_tasks",
    tasks=[
        {"id": "t1", "target_symbols": ["validate_token"], "dependency_symbols": []},
        {"id": "t2", "target_symbols": ["refresh_token"], "dependency_symbols": ["validate_token"]},
        {"id": "t3", "target_symbols": ["log_access"], "dependency_symbols": []},  # Can run in parallel
    ]
)
print(plan.phases)  # [[t1], [t2, t3]] → 2 sequential phases, t2 and t3 in parallel

# 4. Execute with conflict detection built in
result = assistant.call_tool("execute_tasks", tasks=plan.tasks)
print(result.success_rate)  # Automatic retries, timeout handling
```
