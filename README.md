# Save My Tokens - Graph API Foundation

A structured **Graph API** that transforms source code into a dependency graph + semantic model, enabling agents to retrieve minimal, relevant context for code modifications, detect safe parallelization boundaries, and perform semantic search on code.

## Project Overview

**Status:** Phase 1 - Graph API Foundation (MVP)  
**Duration:** 16 weeks  
**Start Date:** April 1, 2026  

### Core Principle

Code is not files—it's a graph. Agents interact through the Query API, not raw file access.

## Quick Start

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

## Project Structure

```
src/
  parsers/          # Language-specific parsing (Python, TypeScript)
  graph/            # Graph construction and queries
  embeddings/       # Vector DB and semantic search
  api/              # FastAPI endpoints
  evaluation/       # Baseline metrics collection

tests/
  unit/             # Parser, graph, API tests
  integration/      # End-to-end tests
  fixtures/         # Test repositories

docs/
  ARCHITECTURE.md   # Data flow, components
  API_SPEC.md       # Endpoint definitions
  TESTING.md        # Test strategy
```

## API Endpoints (Phase 1)

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Health check |
| `GET /api/stats` | Graph statistics |
| `GET /api/context/{symbol}` | Minimal context for symbol |
| `GET /api/subgraph/{symbol}` | Dependency subgraph |
| `GET /api/search` | Semantic search |
| `POST /api/validate-conflicts` | Detect parallelization conflicts |

## Success Criteria (Week 10)

Must meet 6/6 metrics:

| Metric | Target |
|--------|--------|
| Parser Coverage | 98%+ |
| Query Latency (p99) | <500ms on 50K LOC |
| Dependency Accuracy | 95%+ precision |
| Conflict Detection | 90%+ precision & recall |
| API Response Payload | <50KB median |
| Test Coverage | ≥80% |

## Development Tasks

See **[DEVELOPMENT_TASKS.md](DEVELOPMENT_TASKS.md)** for detailed week-by-week breakdown.

## Documentation

- [CLAUDE.md](CLAUDE.md) — Project overview and development approach
- [DEVELOPMENT_TASKS.md](DEVELOPMENT_TASKS.md) — Detailed task breakdown
- [WORKING_PLAN.md](WORKING_PLAN.md) — Initial planning notes
- [Phase_1_MVP_Revised.md](Phase_1_MVP_Revised.md) — Full MVP specification

## Test Repositories

This project is validated against three real-world codebases:

1. **[requests](https://github.com/psf/requests)** — ~12K LOC (Python) — Quick iteration
2. **[Flask](https://github.com/pallets/flask)** — ~25K LOC (Python) — Primary evaluation
3. **[Vue.js](https://github.com/vuejs/core)** — ~100K+ LOC (TypeScript) — Scalability test

## Architecture

```
Source Code
    ↓
Tree-sitter Parser
    ↓
Symbol Index
    ↓
Neo4j Graph (nodes + edges)
    ↓
FAISS Vector DB
    ↓
Query API (REST)
    ↓
Agent Client
```

## Next Steps

1. **Week 1-2:** Environment setup, test repo download
2. **Week 3-4:** Parser implementation (Python + TypeScript)
3. **Week 5-6:** Graph construction (nodes, edges, queries)
4. **Week 7:** REST API endpoints
5. **Week 8:** Vector embeddings & semantic search
6. **Week 9:** Conflict detection
7. **Week 10:** Integration tests & go/no-go decision

## Contributing

This is an experimental phase of development. Follow the guidelines in [CLAUDE.md](CLAUDE.md) for development approach.

## License

See LICENSE file (TBD)

---

**Built with Claude Code** — Interactive agent for software engineering
