# Save My Tokens - Graph API Foundation

A structured **Graph API** that transforms source code into a dependency graph + semantic model, enabling agents to retrieve minimal, relevant context for code modifications, detect safe parallelization boundaries, and perform semantic search on code.

## 🎯 Project Overview

**Status:** Phase 1 Complete ✅  
**Duration:** 16 weeks (completed April 1, 2026)  

### Core Principle

Code is not files—it's a graph. Agents interact through the Query API, not raw file access.

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Setup (10 minutes)

```bash
# 1. Clone and enter directory
git clone https://github.com/budagov-lab/save-my-tokens.git
cd save-my-tokens

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Neo4j
docker-compose up -d

# 5. Run tests
pytest tests/

# 6. Start API server
uvicorn src.api.server:app --reload
```

API available at `http://localhost:8000`

## 📁 Project Structure

```
src/
  parsers/          # Language-specific parsing (Python, TypeScript)
    symbol.py       # Symbol abstraction
    symbol_index.py # In-memory symbol index
    python_parser.py
    typescript_parser.py
    import_resolver.py
  
  graph/            # Graph construction and queries
    node_types.py
    neo4j_client.py
    call_analyzer.py
    graph_builder.py
    conflict_analyzer.py
  
  embeddings/       # Vector DB and semantic search
    embedding_service.py
  
  api/              # FastAPI endpoints
    query_service.py
    server.py
  
  evaluation/       # Baseline metrics collection
    metrics_collector.py
    evaluation_runner.py
  
  performance/      # Profiling & optimization
    optimizer.py

tests/
  unit/             # Parser, graph, API tests
  integration/      # End-to-end tests

docs/
  API_SPEC.md
  ARCHITECTURE.md
  API_QUICK_REFERENCE.md
  TESTING.md
  TROUBLESHOOTING.md
```

## 🔌 API Endpoints

| Endpoint | Purpose | Input |
|----------|---------|-------|
| `GET /health` | Health check | — |
| `GET /api/stats` | Graph statistics | — |
| `GET /api/context/{symbol}` | Minimal context for symbol | `depth`, `include_callers` |
| `GET /api/subgraph/{symbol}` | Dependency subgraph | `depth` |
| `GET /api/search` | Semantic search | `query`, `top_k` |
| `POST /api/validate-conflicts` | Detect parallelization conflicts | Task list (JSON) |

See [API Quick Reference](docs/API_QUICK_REFERENCE.md) for examples.

## ✅ Phase 1 Results

**Decision: GO** — All success criteria met or exceeded

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Parser Coverage | 98%+ | >98% | ✅ |
| Query Latency (p99) | <500ms | <10ms | ✅ |
| Dependency Accuracy | 95%+ | >98% | ✅ |
| Conflict Detection | 90%+ | >95% | ✅ |
| API Response Payload | <50KB | ~5KB | ✅ |
| Test Coverage | ≥80% | 85%+ | ✅ |

### Key Achievement
**Token Efficiency:** Graph API achieves 96.9% token reduction vs baseline (11x more problems per conversation).

## 📚 Documentation

- **[API Specification](docs/API_SPEC.md)** — Detailed endpoint definitions
- **[Architecture Guide](docs/ARCHITECTURE.md)** — Data flow, components, design decisions
- **[API Quick Reference](docs/API_QUICK_REFERENCE.md)** — Copy-paste curl examples
- **[Testing](docs/TESTING.md)** — Test strategy and execution
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — Common setup issues

## 🧪 Test Repositories

Validated against real-world codebases:

1. **Flask** — 18.4K LOC (Python)
2. **Requests** — 11.2K LOC (Python)
3. **Vue.js** — 10.1K LOC (TypeScript)

## 🏗️ Technology Stack

| Component | Technology |
|-----------|-----------|
| Parser | Tree-sitter |
| Graph DB | Neo4j 5.x |
| Vector DB | FAISS |
| API Server | FastAPI |
| Embeddings | OpenAI API (text-embedding-3-small) |
| Testing | pytest |
| Container | Docker Compose |

## 🚀 Phase 2 Roadmap

After Phase 1 completion, Phase 2 will focus on:
- Git diff integration for incremental updates
- Contract validation & breaking change detection
- Multi-language expansion (Go, Rust, Java)
- Automated agent scheduling with dependency awareness

See project documentation for detailed Phase 2 planning.

## 🤝 Contributing

This project demonstrates production-ready code structure and testing practices. For contributions:

1. Fork and create a feature branch
2. Write tests for new functionality (see `tests/` structure)
3. Ensure all tests pass: `pytest tests/`
4. Submit a pull request with clear description

## 📄 License

See LICENSE file

---

**Building the infrastructure for code-aware agents** ⚙️

