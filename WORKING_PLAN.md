# Codebase Project OS for Parallel Agents – Working Plan

**Last Updated:** April 2026  
**Phase:** 1 (MVP)  
**Duration:** 3 months

---

## Project Goal

Build a system that transforms source code into a **dependency graph + semantic model**, enabling agents to:
- Retrieve minimal context for tasks
- Detect safe parallelization boundaries
- Modify code via API instead of raw file access
- Perform impact analysis

**Core principle:** Code is not files—it's a graph. Agents interact only through the Query API.

---

## Phase 1: MVP Scope (3 months)

**Objective:** Prove that Graph API improves agent task completion by 15%+ vs. baseline.

**Success metric:** Agent using Graph API achieves 15%+ higher completion rate on code modification tasks.

### What We Build

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Parser | Tree-sitter | Extract functions, classes, imports |
| Graph DB | Neo4j | Store nodes (files, functions, classes) and edges (imports, calls, dependencies) |
| Vector DB | FAISS + OpenAI embeddings | Semantic search |
| API Server | FastAPI (Python) | Query endpoints for agents |
| Tests | pytest | Unit, integration, agent evaluation |

### What We Skip (Phase 2+)

- Incremental updates from git diffs
- Contract validation
- Automated agent scheduling
- Multi-language support

---

## System Architecture (Phase 1)

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
- File, Module, Function, Class, Variable, Type

### Edge Types
- IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS

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

## Implementation Timeline (12 weeks)

| Week | Deliverable | Success Check |
|------|-------------|----------------|
| 1-2 | Setup (Tree-sitter, Neo4j, Docker) | Repo parses without errors |
| 3-4 | Symbol extraction (1 language) | Extract 100% of functions/classes |
| 5 | Build graph: nodes + edges | Neo4j queries <100ms |
| 6 | Implement API endpoints 1-3 | Response time <500ms |
| 7 | Add vector embeddings | Semantic search top-5 > 70% relevant |
| 8 | Implement conflict detection | >95% recall on test scenarios |
| 9 | Integration tests + baseline setup | Ready for agent evaluation |
| 10-12 | Agent evaluation | Measure 15%+ completion improvement |

---

## Testing Strategy

### Unit Tests
- Parser correctness (extract all symbols, imports)
- Graph construction (nodes created, edges typed correctly)
- API response format and latency

### Integration Tests
- Graph on 50K-100K LOC repo
- Query latency on real workload
- Conflict detection on real dependency chains

### Agent Evaluation
- 20-30 code modification tasks
- Measure: completion rate, tokens used, time
- Compare Graph API vs. baseline (raw files)

---

## Success Criteria (Go/No-Go at Week 10)

| Metric | Target | Status |
|--------|--------|--------|
| Parser accuracy | 100% extraction | [ ] |
| Query latency p99 | <500ms | [ ] |
| Graph size | >1000 nodes on 50K LOC | [ ] |
| Semantic search precision | >80% top-5 | [ ] |
| Conflict detection recall | >95% | [ ] |
| **Agent completion rate improvement** | **≥15%** | [ ] |
| Token efficiency improvement | ≥20% | [ ] |
| Test coverage | ≥80% | [ ] |

**Decision:** GO if 7/8 metrics met. Otherwise: extend Phase 1.5 or pivot.

---

## Test Repositories

| Repo | Size | Language | Purpose |
|------|------|----------|---------|
| Simple API | 10K LOC | Python | Unit test baseline |
| Medium Web App | 50K LOC | TypeScript | Integration tests + baseline |
| Complex Monorepo | 200K LOC | Mixed (optional) | Scalability test |

---

## Team & Resources

**Required Roles:**
- 1 Backend Engineer (Graph API, Neo4j)
- 1 ML/NLP Engineer (embeddings, evaluation)
- 1 DevOps (Docker, CI/CD)
- 0.5 QA (test automation)

**Infrastructure:**
- Dev machine: 16GB RAM
- CI/CD: GitHub Actions
- External: OpenAI API ($200 budget)

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Parser misses symbols | Medium | High | Unit tests on standard patterns |
| Neo4j query performance | Medium | High | Weekly profiling + indexes |
| Circular dependencies confuse conflict detection | Medium | Medium | Conservative marking as "unsafe" |
| Vector embeddings low quality | Low | Medium | Benchmark vs. baselines |
| Scope creep into Phase 2 | High | High | Strict PR review, block incremental features |

---

## Definition of Done

**Code:**
- [ ] All tests pass (>80% coverage)
- [ ] No warnings (pylint, mypy strict)
- [ ] API response times documented
- [ ] Docker Compose for reproducibility
- [ ] README with 10-min setup

**Documentation:**
- [ ] OpenAPI spec
- [ ] Architecture diagram
- [ ] Query examples per endpoint
- [ ] Troubleshooting guide

**Evaluation:**
- [ ] Baseline vs. Graph API results
- [ ] Statistical significance (t-test)
- [ ] Failure analysis
- [ ] Phase 2 recommendations

---

## Go/No-Go Decision (Week 10)

**Date:** End of Week 10  
**Decision Makers:** Tech Lead + Product Owner + External Reviewer  
**Process:**
1. Collect all 8 metrics
2. Compare vs. targets
3. Document findings
4. Decide: Phase 2, Phase 1.5 extend, or pivot

---

## Quick Reference: Node Types & Edges

**Nodes:** File | Module | Function | Class | Variable | Type

**Edges:**
- `IMPORTS` – file imports from another file
- `CALLS` – function calls another function
- `DEFINES` – file contains function/class
- `INHERITS` – class extends parent
- `DEPENDS_ON` – semantic dependency (used in body)
- `TYPE_OF` – variable has type
- `IMPLEMENTS` – class implements interface

---

## Next Steps

1. **Week 1:** Environment setup, test repo clones, first parser test
2. **Weekly:** Standup on metric progress, blockers, scope adjustments
3. **Week 10:** Final decision meeting

---

## Links

- Tree-sitter: https://tree-sitter.github.io/tree-sitter/
- Neo4j: https://neo4j.com/docs/python-manual/
- FAISS: https://github.com/facebookresearch/faiss
- FastAPI: https://fastapi.tiangolo.com/
