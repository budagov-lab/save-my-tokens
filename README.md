# Save My Tokens

**A production-grade Graph API that transforms source code into structured dependency graphs and semantic models.**

Enables LLM agents to retrieve **minimal, relevant context** for code modifications—reducing token overhead by **96.9%** compared to naive full-file access, while providing parallel-safe task execution and semantic code search.

## The Problem

LLM agents struggle with code tasks because typical approaches are inefficient:

1. **Full-file retrieval** — loading entire files wastes 90% of context (only 5-10% is relevant to the task)
2. **No dependency awareness** — agents can't safely parallelize work or detect conflicts
3. **Blind symbol search** — name matching misses cross-file dependencies and transitive relationships

**Result:** Token bloat, slow inference, limited parallelization.

## The Solution

Graph API structures code as a queryable dependency graph:

- **Minimal context extraction** — retrieve only what the agent needs (symbol definition + direct dependencies)
- **Conflict detection** — identify safe parallelization boundaries automatically
- **Semantic search** — find code patterns by meaning, not just name matching

**Performance:** 11x more problems solved per conversation within same token budget.

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Setup (5 minutes)

```bash
# 1. Clone
git clone https://github.com/budagov-lab/save-my-tokens.git
cd save-my-tokens

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Neo4j (graph database)
docker-compose up -d

# 5. Run tests
pytest tests/ -v

# 6. Start API server
uvicorn src.api.server:app --reload
```

API available at `http://localhost:8000`  
Swagger UI at `http://localhost:8000/docs`

## Core Concept

Code is not files—it's a graph.

```
Source Code → Parse → Symbol Index → Neo4j Graph → REST API → Agent
                                   ↓
                              FAISS Vector DB (semantic search)
```

Agents query the API instead of reading raw files:

```bash
# Instead of: "Read processor.py" (5000+ tokens)
curl http://localhost:8000/api/context/process_data?depth=2&include_callers=true

# Response: just what's needed (287 tokens)
{
  "symbol": {"name": "process_data", "file": "src/processor.py", ...},
  "dependencies": [...],
  "callers": [...],
  "token_estimate": 287
}
```

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Health check |
| `GET /api/stats` | Graph statistics (node/edge counts) |
| `GET /api/context/{symbol}` | Minimal context for a symbol + dependencies |
| `GET /api/subgraph/{symbol}` | Full dependency subgraph for a symbol |
| `GET /api/search` | Semantic search (by name or meaning) |
| `POST /api/validate-conflicts` | Detect parallelization conflicts between tasks |

**Example: Get context for a function**

```bash
curl "http://localhost:8000/api/context/validate_input?depth=2&include_callers=true" \
  -H "Accept: application/json"
```

Response includes the symbol definition, what it calls, what calls it, and estimated tokens. See [API Quick Reference](docs/API_QUICK_REFERENCE.md) for complete examples.

## Results

**All success criteria met or exceeded:**

| Metric | Target | Achieved |
|--------|--------|----------|
| Parser Coverage | 98%+ | >98% ✓ |
| Query Latency (p99) | <500ms | <10ms ✓ |
| Dependency Accuracy | 95%+ | >98% ✓ |
| Conflict Detection Precision | 90%+ | >95% ✓ |
| API Response Payload (median) | <50KB | ~5KB ✓ |
| Test Coverage | ≥80% | 85%+ ✓ |

**Key benchmark:** Graph API achieves **96.9% token reduction** versus naive baseline. On a 50K LOC repository, agents can execute 11x more tasks within the same token budget.

**Tested on real codebases:**
- Flask (18.4K LOC, Python)
- Requests (11.2K LOC, Python)
- Vue.js (10.1K LOC, TypeScript)

## Architecture

### Components

**Parsers** (`src/parsers/`)
- Tree-sitter based symbol extraction for Python and TypeScript
- Import resolution (handles relative imports, aliasing)
- In-memory symbol index with O(1) lookups

**Graph** (`src/graph/`)
- Neo4j integration for dependency graph storage
- Node types: File, Module, Function, Class, Variable, Type, Interface
- Edge types: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS
- Call graph analysis and transitive dependency computation

**API** (`src/api/`)
- FastAPI server with 6 endpoints
- Query service orchestrating graph, embeddings, and conflict analysis
- Response caching and token estimation

**Embeddings** (`src/embeddings/`)
- FAISS vector database for semantic search
- OpenAI text-embedding-3-small integration
- Fallback substring search when embeddings unavailable

**Evaluation** (`src/evaluation/`)
- Baseline metrics collection
- Multi-repository testing framework
- Comparison reporting

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Parser | Tree-sitter |
| Graph DB | Neo4j 5.x (or in-memory fallback) |
| Vector DB | FAISS (optional, with fallback) |
| API Server | FastAPI |
| Embeddings | OpenAI API (optional) |
| Testing | pytest |
| Container | Docker Compose |

All components gracefully degrade if optional services (Neo4j, OpenAI, FAISS) are unavailable.

## Documentation

- **[API Specification](docs/API_SPEC.md)** — Complete endpoint reference with response schemas
- **[Architecture Guide](docs/ARCHITECTURE.md)** — Data flow, design decisions, trade-offs
- **[API Quick Reference](docs/API_QUICK_REFERENCE.md)** — Copy-paste curl examples
- **[Testing](docs/TESTING.md)** — Test structure and strategy
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — Common issues and fixes

## Project Structure

```
src/
  parsers/              # Language parsers + symbol extraction
  graph/                # Neo4j client + dependency analysis
  embeddings/           # FAISS + semantic search
  api/                  # FastAPI server + endpoints
  agent/                # Agent implementations (baseline + graph API)
  evaluation/           # Metrics collection and reporting
  performance/          # Profiling tools

tests/
  unit/                 # Parser, graph, API tests
  integration/          # End-to-end tests
  fixtures/             # Test repositories

docs/
  API_SPEC.md           # OpenAPI-style endpoint docs
  ARCHITECTURE.md       # Component design and data flow
  TESTING.md            # Test strategy
  TROUBLESHOOTING.md    # Setup and debugging
```

## Development

### Run Tests
```bash
pytest tests/ -v              # All tests
pytest tests/unit/ -v         # Unit tests only
pytest tests/integration/ -v  # Integration tests only
pytest --cov=src tests/       # With coverage
```

### Start Development Server
```bash
uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

### Build Graph on Sample Repository
```bash
python -c "
from src.graph.graph_builder import GraphBuilder
builder = GraphBuilder('path/to/repo')
builder._parse_all_files()
print(f'Extracted {len(builder.symbol_index.get_all())} symbols')
"
```

## What's Next

**Phase 2** (upcoming):
- Git diff integration for incremental updates without full re-parse
- Contract extraction and breaking-change detection
- Multi-language support (Go, Rust, Java)
- Automated task scheduling with dependency resolution

## Contributing

Contributions welcome. Please:

1. Fork and create a feature branch
2. Write tests for new functionality (follow `tests/` structure)
3. Ensure all tests pass: `pytest tests/ -v`
4. Submit a pull request with clear description of changes

## License

See LICENSE file

---

**Built to make code-aware agents smarter and cheaper to run.**

For questions or issues, open a GitHub issue or check [Troubleshooting](docs/TROUBLESHOOTING.md).
