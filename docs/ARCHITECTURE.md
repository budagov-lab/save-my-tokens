# Architecture - Save My Tokens

## System Overview

```
Source Code (Python + TypeScript)
    ↓
Tree-sitter Parser
    ↓
Symbol Index (in-memory)
    ↓
Neo4j Graph DB (nodes + edges)
    ↓
FAISS Vector DB (embeddings)
    ↓
FastAPI REST API
    ↓
Agent Client
```

## Components

### 1. Parser (`src/parsers/`)
- **Purpose**: Extract symbols (functions, classes, imports) from source code
- **Technologies**: Tree-sitter
- **Inputs**: Python, TypeScript files
- **Outputs**: Symbol objects with metadata (name, type, location, docstring)

### 2. Symbol Index (`src/parsers/`)
- **Purpose**: Fast lookup of symbols by name
- **Data Structure**: In-memory dictionary: `name → Symbol`
- **Handles**: Qualified names for disambiguation (e.g., `module.ClassName.method`)

### 3. Graph (`src/graph/`)
- **Purpose**: Build and query dependency graph
- **Database**: Neo4j
- **Node Types**: File, Module, Function, Class, Variable, Type
- **Edge Types**: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS

### 4. Embeddings (`src/embeddings/`)
- **Purpose**: Semantic search on code
- **Vector DB**: FAISS (in-memory, persistent)
- **Embedding Model**: OpenAI text-embedding-3-small
- **Indexing**: Symbol names + docstrings

### 5. API (`src/api/`)
- **Framework**: FastAPI
- **Port**: 8000 (default)
- **Endpoints**: See API_SPEC.md

## Data Flow

### Initialization (Week 1-6)
1. Parse source code → extract symbols
2. Build symbol index
3. Create graph nodes for each symbol
4. Create graph edges from call/import/inheritance analysis
5. Generate embeddings for semantic search

### Query Time (Week 7+)
1. Client requests symbol context via REST API
2. API queries Neo4j for direct dependencies
3. Optionally: query FAISS for semantic neighbors
4. Return minimal payload with token estimate

## Design Decisions

### Why Neo4j?
- Native graph queries (BFS, shortest path)
- Pattern matching for dependency analysis
- Indexed queries <100ms on 50K LOC

### Why FAISS?
- Fast similarity search (<500ms for top-k)
- No external dependencies (runs locally)
- Supports incremental indexing

### Why Tree-sitter?
- Incremental parsing (future: git diff support)
- Language-agnostic (Phase 2: expand to more languages)
- Accurate symbol extraction (98%+ precision)

## Deployment

### Local Development
```bash
docker-compose up -d  # Start Neo4j
python -m pip install -e .
python scripts/setup_neo4j.py
uvicorn src.api.server:app --reload
```

### Production (Future)
- Containerized: Docker image with Neo4j + API
- Load balancing: Multiple API instances
- Caching: Redis for query results
