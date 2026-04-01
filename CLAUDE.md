# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**Project:** Codebase Project OS for Parallel Agents  
**Phase:** 1 - Graph API Foundation (MVP)  
**Duration:** 4 months (16 weeks)  
**Status:** Planning complete, ready for implementation  

### What We're Building

A structured **Graph API** that transforms source code into a dependency graph + semantic model, enabling agents to:
- Retrieve minimal, relevant context for code modifications
- Detect safe parallelization boundaries between tasks
- Understand cross-file dependencies and impact
- Perform semantic search on code

**Core principle:** Code is not files—it's a graph. Agents interact through the Query API, not raw file access.

### Why This Matters

Current agent approaches to code:
- Retrieve entire files (wasteful—only 5-10% of content is relevant)
- Use simple symbol search (miss cross-file dependencies)
- Cannot detect safe parallel execution boundaries

This project builds infrastructure to solve these problems measurably.

---

## Phase 1 Scope

### In Scope
- **Parser:** Tree-sitter for Python + TypeScript symbol extraction (functions, classes, imports, types)
- **Graph DB:** Neo4j local instance storing nodes (files, functions, classes) and edges (imports, calls, dependencies)
- **Vector DB:** FAISS + OpenAI embeddings for semantic search
- **API Server:** FastAPI (Python) with REST endpoints for graph queries
- **Testing:** pytest for unit, integration, and evaluation tests
- **Test repos:** 10K LOC (fast iteration), 50K LOC (primary), 200K LOC (scalability)

### Out of Scope (Phase 2+)
- Incremental updates from git diffs
- Contract validation
- Automated agent scheduling
- Multi-language support
- Agent evaluation (Phase 1 validates the API, not agents)

---

## System Architecture

```
Source Code
    ↓
Tree-sitter Parser
    ↓
Symbol Index (name → location)
    ↓
Neo4j Graph (nodes + edges)
    ↓
FAISS Vector DB (embeddings)
    ↓
Query API (REST endpoints)
    ↓
Agent Client
```

### Node Types
- **File, Module, Function, Class, Variable, Type**

### Edge Types
- `IMPORTS` – file imports from another file
- `CALLS` – function calls another function
- `DEFINES` – file contains function/class
- `INHERITS` – class extends parent
- `DEPENDS_ON` – semantic dependency (used in body)
- `TYPE_OF` – variable has type
- `IMPLEMENTS` – class implements interface

---

## API Endpoints (Phase 1)

### 1. Get Minimal Context
```
GET /api/context/{symbol_name}?depth=1&include_callers=true

Returns: symbol info + direct dependencies + reverse dependencies + token count
```

### 2. Get Dependency Subgraph
```
GET /api/subgraph/{symbol_name}?depth=2

Returns: nodes, edges, context size in tokens
```

### 3. Semantic Search
```
GET /api/search?query=password+validation&top_k=5

Returns: ranked list of matching symbols with similarity scores
```

### 4. Detect Conflicts
```
POST /api/validate-conflicts

Request: list of tasks with target symbols
Response: detected conflicts + parallel feasibility
```

---

## Success Criteria (Phase 1 Completion)

Go/No-Go decision at end of Week 10. Must meet these observable metrics:

| Metric | Target | Purpose |
|--------|--------|---------|
| Parser Coverage | 98%+ of functions/classes extracted | Shows parser quality |
| Query Latency | <500ms p99 on 50K LOC | Shows scalability |
| Dependency Accuracy | 95%+ precision on call graph | Shows graph correctness |
| Conflict Detection | 90%+ precision, 90%+ recall | Shows parallelization safety |
| API Response Payload | <50KB median | Shows efficiency |
| Test Coverage | ≥80% | Shows code quality |

**Decision:** GO if 6/6 metrics met. Otherwise: Phase 1.5 extension or pivot.

---

## Development Timeline (16 weeks)

| Week | Deliverable | Success Check |
|------|-------------|----------------|
| 1-2 | Setup (Tree-sitter, Neo4j, Docker) | Repo parses without errors |
| 3-4 | Symbol extraction (Python + TS) | Extract 100% of functions/classes |
| 5-6 | Build graph: nodes + edges | Neo4j queries <100ms |
| 7 | Implement API endpoints 1-3 | Response time <500ms |
| 8 | Add vector embeddings + semantic search | Top-5 precision >80% |
| 9 | Implement conflict detection | >95% recall on test scenarios |
| 10 | Integration tests + evaluation setup | Ready for metrics review |
| 11-12 | Optimization + documentation | API spec, architecture guide, troubleshooting |
| 13-16 | Agent evaluation & Phase 2 prep | Baseline vs. Graph API results |

---

## Key Planning Documents

- **WORKING_PLAN.md** – Detailed MVP plan with timeline, risks, and definitions of done
- **Phase_1_MVP_Revised.md** – Full specification with problem analysis, scope, and acceptance criteria
- **TOKEN_SAVING.md** – Development best practices for token efficiency

---

## Testing Strategy

### Unit Tests (pytest)
- Parser correctness (symbol extraction, import detection)
- Graph construction (nodes created, edges typed correctly)
- API response format and latency
- Conflict detection logic

### Integration Tests
- Graph construction on 10K/50K/200K LOC repos
- Query latency under real workload
- Dependency chain validation
- Conflict detection on complex scenarios

### Evaluation Tests
- Baseline metrics establishment
- API consistency across test repos
- Performance profiling (latency, memory, graph size)

---

## Dependencies & Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Parser | Tree-sitter | Latest |
| Graph DB | Neo4j | 5.x |
| Vector DB | FAISS | Latest |
| API Server | FastAPI | 0.100+ |
| Embeddings | OpenAI API | text-embedding-3-small |
| Testing | pytest | 7.x+ |
| Container | Docker Compose | 2.x |
| Language | Python | 3.11+ |

---

## Tool Usage & Efficiency Best Practices

### Claude Code Tool Search Patterns
When Claude Code is working on this codebase, apply these patterns to minimize tokens:

**1. Search Before Reading**
```bash
# ❌ BAD: Read entire file without knowing what's in it
Read(src/api/endpoints.py)

# ✅ GOOD: Grep first to find relevant sections
Grep(pattern: "def validate_conflicts", path: "src/", type: "py")
Read(src/api/endpoints.py, offset: 42, limit: 50)  # Read only the relevant function
```

**2. Limit Grep Results**
```bash
# ❌ BAD: Unbounded search across entire codebase
Grep(pattern: ".*", type: "py")  # Returns 1000+ results

# ✅ GOOD: Use head_limit to cap expensive searches
Grep(pattern: "IMPORTS|CALLS|DEPENDS_ON", type: "py", head_limit: 10)
```

**3. Batch Independent Operations**
```bash
# ❌ BAD: Three separate Bash calls
Bash(command: "npm install")
Bash(command: "python -m pytest")
Bash(command: "python -m mypy src/")

# ✅ GOOD: Chain with && when order matters
Bash(command: "python -m pytest tests/unit/ && python -m mypy src/")
```

**4. Use Glob Before Read (for file discovery)**
```bash
# ❌ BAD: Glob returns huge list, then read them all
Glob(pattern: "src/**/*.py")
# → Reads every file (1000+ tokens)

# ✅ GOOD: Glob with pattern, then Read specific matches
Glob(pattern: "src/parsers/**/*.py")  # Narrow pattern first
Read(src/parsers/python_parser.py)
```

### Programmatic Tool Calling (Agent Phase)
When agents use the Graph API (Phase 2 evaluation), they'll call endpoints like:

```python
# Agent requests minimal context before modifying code
GET /api/context/{symbol_name}?depth=1&include_callers=true

# Response includes:
{
  "symbol": "validate_conflicts()",
  "file": "src/api/endpoints.py",
  "dependencies": [...],  # Direct callers + callees
  "token_count": 800,     # Tells agent if context fits in token budget
  "callers": [...]        # Reverse dependencies (safe parallelization check)
}
```

**Why this pattern matters:** Instead of agents retrieving entire files (5000+ tokens), they query only what's needed (~800 tokens), reducing waste by 80%+.

**For Phase 1 development:** Claude Code uses file-based access normally. But the **tests** should verify that the Graph API returns minimal payloads (<50KB median, as per success criteria).

---

## Development Approach & Decisions

### Code Organization
Organize by concern, not by layer:
```
src/
  parsers/          # Language-specific parsing logic
  graph/            # Graph construction and query logic
  embeddings/       # Vector DB and semantic search
  api/              # FastAPI endpoints
  evaluation/       # Baseline setup and metrics collection
tests/
  unit/
  integration/
  fixtures/         # Test repos, sample code
```

### Git Workflow
- Feature branches: `feat/description`
- Bug fixes: `fix/description`
- Each PR must include tests covering the changes
- Baseline metrics are immutable—changes require decision maker approval

### Critical Decisions at Checkpoints
- **Week 2:** If parser can't extract >95% of symbols, consider alternative parser or scope to 1 language
- **Week 5:** If Neo4j queries >200ms, add indexes or profile before proceeding
- **Week 10:** Go/No-Go on success metrics (see above)—do NOT proceed with agent evaluation if metrics not met

### Scope Protection
- **No incremental features** until Phase 2 is approved
- **No multi-language support** until Python + TS are solid
- **No git diff integration** until evaluation shows value
- PR reviewers should block Phase 2 features aggressively

---

## Definition of Done (Phase 1 Completion)

### Code
- [ ] All tests pass (≥80% coverage)
- [ ] No linting warnings (pylint, mypy strict)
- [ ] API response times documented per endpoint
- [ ] Docker Compose setup for reproducibility
- [ ] README with 10-minute setup instructions

### Documentation
- [ ] OpenAPI spec (auto-generated from FastAPI)
- [ ] Architecture diagram (data flow + component interactions)
- [ ] Query examples for each API endpoint
- [ ] Troubleshooting guide

### Evaluation
- [ ] Baseline metrics collected on all test repos
- [ ] Success criteria evaluated (6/6 checklist above)
- [ ] Failure analysis documented (if any metrics missed)
- [ ] Phase 2 recommendations written

---

## Quick Reference: Metric Formulas

**Parser Coverage:** (Functions + Classes extracted) / (Functions + Classes in codebase) × 100%

**Query Latency p99:** Sort 99% of query responses by time; report the slowest

**Dependency Accuracy:** (Correct edges + Correct non-edges) / (Total edge decisions) × 100%

**Conflict Detection Precision:** (True conflicts found) / (Predicted conflicts) × 100%

**Conflict Detection Recall:** (True conflicts found) / (Actual conflicts) × 100%

---

## Resources & Links

- **Tree-sitter:** https://tree-sitter.github.io/tree-sitter/
- **Neo4j Python Driver:** https://neo4j.com/docs/python-manual/
- **FAISS:** https://github.com/facebookresearch/faiss
- **FastAPI:** https://fastapi.tiangolo.com/
- **OpenAI Embeddings API:** https://platform.openai.com/docs/guides/embeddings

---

## Next Steps

1. **Environment setup:** Clone test repos, install Tree-sitter, Docker, Neo4j
2. **First parser test:** Parse 10K LOC repo, validate symbol extraction
3. **Weekly standups:** Review metric progress, identify blockers, adjust scope
4. **Week 10 decision:** Go/No-Go on Phase 1 completion
