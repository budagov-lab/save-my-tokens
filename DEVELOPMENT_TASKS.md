# Development Tasks - Graph API Foundation (Phase 1)

**Project:** Codebase Project OS for Parallel Agents  
**Phase:** 1 - Graph API Foundation (MVP)  
**Duration:** 16 weeks  
**Start Date:** 2026-04-01  
**Status:** Planning → Implementation

---

## Week 1-2: Environment Setup & Infrastructure

### Task 1.1: Initialize Project Repository
- [ ] Create directory structure (src/, tests/, docs/, fixtures/)
- [ ] Initialize git repo
- [ ] Create .gitignore (Python, Node, IDE files)
- [ ] Set up pyproject.toml with dependencies (Tree-sitter, Neo4j, FastAPI, pytest, FAISS)
- [ ] Create Docker Compose file for Neo4j + Dev environment
- **Success:** `git status` shows clean setup, `docker-compose up` starts Neo4j

### Task 1.2: Set Up Development Environment
- [ ] Install Python 3.11+ and venv
- [ ] Install Tree-sitter and language bindings (Python + TypeScript)
- [ ] Install Neo4j Python driver
- [ ] Install FastAPI, uvicorn, pytest, FAISS
- [ ] Verify all imports work: `python -c "import tree_sitter; import neo4j; import fastapi"`
- **Success:** All imports succeed, no version conflicts

### Task 1.3: Set Up Neo4j Local Instance
- [ ] Run Neo4j via Docker Compose
- [ ] Create initial database schema (node labels, edge types)
- [ ] Write setup script to initialize empty graph
- [ ] Test connection with Python driver
- **Success:** Neo4j accessible on localhost:7687, can create/query nodes

### Task 1.4: Download & Organize Test Repositories
- [ ] Clone/obtain 10K LOC test repo (small, fast iteration)
- [ ] Clone/obtain 50K LOC test repo (primary evaluation)
- [ ] Clone/obtain 200K LOC test repo (scalability test)
- [ ] Place in fixtures/test_repos/ with standardized structure
- **Success:** All three repos present, sizes verified

### Task 1.5: Create Project Documentation Structure
- [ ] Create ARCHITECTURE.md (data flow diagram, component interactions)
- [ ] Create API_SPEC.md (OpenAPI-style endpoint definitions)
- [ ] Create TESTING.md (unit, integration, evaluation test strategy)
- [ ] Create TROUBLESHOOTING.md (common setup issues)
- **Success:** All .md files created with section headers, ready to fill in

---

## Week 3-4: Parser Implementation

### Task 2.1: Implement Python Symbol Extractor
- [ ] Use Tree-sitter to parse Python files
- [ ] Extract: functions, classes, imports, type hints
- [ ] Create Symbol data class (name, type, location, docstring)
- [ ] Handle nested definitions (methods in classes)
- **Success:** Parse 10K LOC repo, extract ≥98% of functions/classes

### Task 2.2: Implement TypeScript Symbol Extractor
- [ ] Use Tree-sitter to parse TypeScript files
- [ ] Extract: functions, classes, imports, type annotations
- [ ] Create unified Symbol interface (compatible with Python extractor)
- [ ] Handle JSX/TSX syntax
- **Success:** Parse TypeScript test files, extract ≥98% of functions/classes

### Task 2.3: Create Symbol Index
- [ ] Build in-memory index: name → {file, line, type, symbol_obj}
- [ ] Handle duplicate names (qualified paths: module.ClassName.method_name)
- [ ] Write unit tests for index lookups
- **Success:** Symbol index built from 10K LOC repo, fast lookups work

### Task 2.4: Implement Import Detection
- [ ] Detect all imports (from X import Y, import Z, require())
- [ ] Resolve relative imports to absolute paths
- [ ] Handle star imports (from X import *)
- [ ] Track both explicit and implicit dependencies
- **Success:** ≥95% of imports correctly identified on test repos

### Task 2.5: Write Parser Tests
- [ ] Unit tests: symbol extraction accuracy on Python + TypeScript snippets
- [ ] Integration tests: parse 10K LOC repo, validate symbol count
- [ ] Edge cases: decorators, comprehensions, dynamic imports
- **Success:** Parser tests pass with ≥90% code coverage

---

## Week 5-6: Graph Construction

### Task 3.1: Build Graph Node Layer
- [ ] Create Node types: File, Module, Function, Class, Variable, Type
- [ ] Implement Neo4j node creation for each type
- [ ] Write functions: create_file_node(), create_function_node(), etc.
- [ ] Add metadata: name, file path, line number, docstring
- **Success:** Nodes created in Neo4j, properties stored correctly

### Task 3.2: Build Graph Edge Layer
- [ ] Implement edge types: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON, TYPE_OF, IMPLEMENTS
- [ ] Create relationships in Neo4j
- [ ] Add edge metadata: line numbers, types, strengths
- **Success:** Edges created, relationships queryable in Neo4j

### Task 3.3: Parse Call Graph
- [ ] Static analysis to detect function calls within function bodies
- [ ] Create CALLS edges in graph
- [ ] Handle method calls, constructor calls, dynamic calls (best-effort)
- **Success:** Call graph edges created, >90% accuracy on test scenarios

### Task 3.4: Parse Inheritance & Type Information
- [ ] Detect class inheritance relationships (INHERITS edges)
- [ ] Detect interface implementations (IMPLEMENTS edges)
- [ ] Detect variable types (TYPE_OF edges)
- **Success:** Type graph complete, inheritance chains queryable

### Task 3.5: Integrate Parser → Graph
- [ ] Create GraphBuilder class that orchestrates: Parse → Index → Create Nodes → Create Edges
- [ ] Implement graph construction on 10K LOC repo
- [ ] Measure Neo4j query latency: target <100ms for simple queries
- **Success:** Full graph built from 10K LOC repo, queries <100ms

### Task 3.6: Write Graph Construction Tests
- [ ] Unit tests: node/edge creation correctness
- [ ] Integration tests: build graph from 10K/50K LOC repos
- [ ] Performance tests: query latency benchmarks
- **Success:** Graph tests pass, latencies documented

---

## Week 7: API Endpoints 1-3

### Task 4.1: Implement GET /api/context/{symbol_name}
- [ ] Query symbol in graph
- [ ] Return symbol info (name, file, line, type)
- [ ] Include direct dependencies (callees)
- [ ] Include reverse dependencies (callers) if include_callers=true
- [ ] Calculate token count estimate
- **Success:** Endpoint returns <50KB response, <500ms latency

### Task 4.2: Implement GET /api/subgraph/{symbol_name}
- [ ] Accept depth parameter (1, 2, 3...)
- [ ] Query graph with BFS to depth N
- [ ] Return nodes and edges in subgraph
- [ ] Include token count estimate
- **Success:** Subgraph queries return all reachable nodes at depth

### Task 4.3: Implement Health Check & Basic Endpoints
- [ ] GET /health → {status: "ok"}
- [ ] GET /api/stats → {nodes: count, edges: count, graph_size_mb: float}
- [ ] Add request/response logging
- **Success:** Health endpoint responds in <50ms

### Task 4.4: Write API Tests
- [ ] Unit tests: response format validation
- [ ] Integration tests: query correctness on test graph
- [ ] Latency tests: verify <500ms p99 on 50K LOC repo
- **Success:** API tests pass, latencies documented

---

## Week 8: Vector Embeddings & Semantic Search

### Task 5.1: Set Up Vector Database (FAISS)
- [ ] Initialize FAISS index (vector storage)
- [ ] Design vector storage: symbol_name → embedding_vector
- [ ] Write functions to index and search vectors
- **Success:** FAISS index created and searchable

### Task 5.2: Implement Embedding Generation
- [ ] Use OpenAI text-embedding-3-small API to embed symbol names
- [ ] Embed symbol docstrings for additional context
- [ ] Cache embeddings locally to reduce API calls
- **Success:** Symbols embedded, embeddings cached

### Task 5.3: Implement GET /api/search
- [ ] Accept query string (natural language or code snippet)
- [ ] Generate embedding for query
- [ ] Search FAISS index, return top-k ranked results
- [ ] Return symbols with similarity scores
- **Success:** Semantic search returns relevant results, top-5 precision >80%

### Task 5.4: Write Semantic Search Tests
- [ ] Unit tests: embedding consistency
- [ ] Integration tests: search relevance on test repos
- [ ] Precision/recall metrics on known query-result pairs
- **Success:** Search tests pass, precision documented

---

## Week 9: Conflict Detection

### Task 6.1: Design Conflict Detection Logic
- [ ] Define conflict: two tasks modify overlapping dependency sets
- [ ] Create algorithm to detect shared dependencies between symbols
- [ ] Create algorithm to determine safe parallelization boundaries
- **Success:** Conflict logic documented, pseudo-code clear

### Task 6.2: Implement POST /api/validate-conflicts
- [ ] Accept request: list of tasks, each with target symbols
- [ ] For each pair of tasks: query shared dependencies
- [ ] Determine if parallel execution is safe
- [ ] Return conflict report with reasons
- **Success:** Endpoint returns conflict analysis

### Task 6.3: Write Conflict Detection Tests
- [ ] Unit tests: conflict detection on simple graphs
- [ ] Integration tests: detect conflicts on test repos
- [ ] Precision/recall tests: >90% on test scenarios
- **Success:** Conflict tests pass, metrics documented

---

## Week 10: Integration Tests & Evaluation Setup

### Task 7.1: Build End-to-End Integration Tests
- [ ] Test full pipeline: Parse → Build Graph → Query API
- [ ] Test on 10K LOC repo (fast), 50K LOC repo (primary), 200K LOC repo (scalability)
- [ ] Verify all endpoints work together
- **Success:** E2E tests pass on all three repos

### Task 7.2: Implement Evaluation Harness
- [ ] Create evaluation runner that tests all success criteria
- [ ] Measure parser coverage (functions/classes extracted)
- [ ] Measure query latency (p99 on 50K LOC)
- [ ] Measure dependency accuracy (sample validation)
- [ ] Measure conflict detection (precision/recall)
- [ ] Measure API response payload size
- [ ] Measure test coverage (pytest --cov)
- **Success:** Evaluation harness runs, all metrics collected

### Task 7.3: Collect Baseline Metrics
- [ ] Run evaluation on all three test repos
- [ ] Document results in METRICS.md
- [ ] Compare against success criteria
- **Success:** Baseline metrics collected, go/no-go decision data ready

### Task 7.4: Go/No-Go Decision
- [ ] Review 6 success metrics
- [ ] GO if all 6/6 met → proceed to Week 11
- [ ] NO-GO if <6/6 met → Phase 1.5 extension or pivot
- **Success:** Decision documented, next steps clear

---

## Week 11-12: Optimization & Documentation

### Task 8.1: Performance Optimization
- [ ] Profile Neo4j queries (identify slow queries)
- [ ] Add Neo4j indexes if needed
- [ ] Optimize graph traversal algorithms
- [ ] Reduce API response payload sizes
- **Success:** Latencies remain <500ms, payload sizes <50KB

### Task 8.2: Write API Documentation
- [ ] Generate OpenAPI spec (auto from FastAPI)
- [ ] Create query examples for each endpoint
- [ ] Document rate limits, error codes, response formats
- **Success:** API_SPEC.md complete and clear

### Task 8.3: Write Architecture Documentation
- [ ] Create ARCHITECTURE.md with data flow diagram
- [ ] Document component interactions (parser, graph, API, embeddings)
- [ ] Explain design decisions
- **Success:** Architecture doc clear and complete

### Task 8.4: Write Setup & Troubleshooting Guide
- [ ] Create 10-minute setup instructions
- [ ] Document common issues and fixes
- [ ] Provide Docker Compose quick start
- **Success:** README and TROUBLESHOOTING.md complete

### Task 8.5: Code Cleanup & Linting
- [ ] Run pylint, mypy (strict mode) on all code
- [ ] Fix linting warnings
- [ ] Ensure ≥80% test coverage
- **Success:** No linting warnings, coverage target met

---

## Week 13-16: Agent Evaluation & Phase 2 Prep

### Task 9.1: Set Up Agent Baseline
- [ ] Create simple agent that uses Graph API
- [ ] Agent retrieves context for code modification tasks
- [ ] Measure baseline performance (token usage, accuracy)
- **Success:** Baseline agent works, metrics collected

### Task 9.2: Compare Graph API vs. File Access
- [ ] Run same tasks with raw file access (no Graph API)
- [ ] Compare token efficiency (tokens used per task)
- [ ] Compare correctness (task success rate)
- **Success:** Comparison documented, Graph API benefit quantified

### Task 9.3: Phase 2 Recommendations
- [ ] Document findings from Phase 1 evaluation
- [ ] Identify incremental features for Phase 2 (git diffs, incremental updates)
- [ ] Propose next steps and resource needs
- **Success:** Phase 2 spec drafted

### Task 9.4: Final Documentation & Release
- [ ] Ensure all documentation up to date
- [ ] Create CHANGELOG.md
- [ ] Tag release (v1.0.0)
- **Success:** Phase 1 complete and documented

---

## Success Criteria Checklist

| Task Group | Success Criteria | Status |
|-----------|-----------------|--------|
| **Week 1-2** | Environment setup complete, Docker/Neo4j working | ⬜ |
| **Week 3-4** | Parser extraction ≥98%, test coverage ≥80% | ⬜ |
| **Week 5-6** | Graph queries <100ms, accuracy >90% | ⬜ |
| **Week 7** | All 3 API endpoints working, latency <500ms | ⬜ |
| **Week 8** | Semantic search top-5 precision >80% | ⬜ |
| **Week 9** | Conflict detection precision/recall >90% | ⬜ |
| **Week 10** | 6/6 metrics met → GO decision | ⬜ |
| **Week 11-12** | Documentation complete, code clean | ⬜ |
| **Week 13-16** | Phase 2 recommendations documented | ⬜ |

---

## Notes

- Tasks are **sequential** by default (each week builds on previous)
- Some tasks within a week can run **in parallel** (e.g., Task 2.1 and 2.2 can start simultaneously)
- **Week 10 is a hard checkpoint:** Go/No-Go decision before proceeding
- If any task blocks, escalate immediately—don't proceed with assumptions
- Update this file weekly with progress and blockers
