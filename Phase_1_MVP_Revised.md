# Phase 1 MVP Specification: Graph API Foundation (Revised)

**Project:** Codebase Project OS for Parallel Agents  
**Phase:** 1 - Graph API Foundation  
**Duration:** 4 months (16 weeks)  
**Status:** Ready for Implementation  
**Last Updated:** April 2026

---

## 1. Executive Summary

### Objective

Build and validate a **structured Graph API** that enables agents to retrieve code context more efficiently than file-based access, with measurable **observable metrics**.

### Why This Matters

Current code-understanding approaches for agents:
- Retrieve entire files (wasteful, loses context depth)
- Use simple symbol search (no dependency awareness)
- Cannot detect safe parallel execution boundaries

**Our approach:** Code as a queryable graph → minimal context + dependency awareness + parallelization foundation.

### Phase 1 Scope & Constraint

- **Single monorepo:** 50K LOC (primary test target)
- **Secondary targets:** 10K LOC (fast iteration) + 200K LOC (scalability test)
- **Languages:** Python + TypeScript (proven Tree-sitter support)
- **No incremental updates:** Static analysis only (Phase 2)
- **No agent evaluation yet:** This phase validates the API, not the agent

### Success Definition (Not Agent Improvement)

This phase succeeds when the Graph API meets **observable, measurable criteria**:

| Metric | Target | Reason |
|--------|--------|--------|
| **Parser Coverage** | 98%+ of functions/classes extracted | Shows parser quality |
| **Graph Query Latency** | <500ms p99 on 50K LOC | Shows scalability |
| **Dependency Accuracy** | 95%+ precision on call graph | Shows graph correctness |
| **Conflict Detection** | 90%+ precision, 90%+ recall | Shows if parallelization is safe |
| **API Response Payload** | <50KB median | Shows efficiency |

---

## 2. Problem Statement & Validation

### Current State (Evidence-Based)

**Problem 1: Inefficient Context Retrieval**
- Agents request code, receive entire files
- Average Python file: 300-500 LOC, but only 10-30 LOC relevant to task
- This wastes tokens and reduces reasoning quality

**Problem 2: Missing Cross-File Impact**
- Agents modify a function without seeing what calls it
- Result: introduces breaking changes
- Example: Change function signature → 5 indirect callers break, agent doesn't know

**Problem 3: No Parallelization Safety**
- Multi-agent systems must run tasks serially (safe but slow)
- Or run in parallel blindly (fast but unsafe)
- No automatic way to detect non-overlapping tasks

### Existing Solutions (Why They Don't Fully Solve This)

**LSP (Language Server Protocol)**
- ✓ Provides symbols, go-to-definition, references
- ✗ Requires IDE integration, not agent-friendly
- ✗ No graph of dependencies, no parallel-safety analysis

**Cursor, GitHub Copilot**
- ✓ Have some code understanding
- ✗ Proprietary, cannot inspect or extend
- ✗ No documented parallel execution awareness

**Simple AST Tools (ctags, ripgrep)**
- ✓ Fast, low overhead
- ✗ No semantic relationships, no conflict detection

### Our Contribution (Specific)

1. **Queryable dependency graph** → agents ask "what calls this function?" not "find files that might use it"
2. **Conflict detection API** → automatic detection of parallel-unsafe task pairs
3. **Measurable quality metrics** → prove the graph is accurate before agents use it

---

## 3. Scope Definition

### 3.1 In Scope

**Core Components:**
- Tree-sitter parser for Python and TypeScript
- Neo4j local instance for graph storage
- Symbol extraction: functions, classes, imports, type definitions
- Call graph construction (who calls whom)
- Inheritance graph (class extends/implements)
- Import graph (file/module dependencies)
- FAISS vector index for semantic search (optional enhancement)

**API Layer:**
- REST endpoints for context retrieval (symbol + dependencies)
- Conflict detection endpoint
- Query diagnostics (latency, coverage stats)

**Testing:**
- Unit tests: parser accuracy on code patterns
- Integration tests: graph construction on real repos
- Validation tests: compare graph against ground truth (manual inspection, linting results)

### 3.2 Explicitly Out of Scope

- ❌ **Incremental updates from git hooks** → Phase 2
- ❌ **Semantic search / embeddings** → Remove from Phase 1 (high effort, uncertain ROI)
- ❌ **Agent evaluation** → Defer to Phase 1.5 (first validate the API in isolation)
- ❌ **Multi-language support** → Only Python + TypeScript
- ❌ **Distributed graph database** → Local Neo4j only
- ❌ **Contract validation** → Phase 4
- ❌ **Circular dependency resolution** → Will be solved as blocking issue (see Risk Mitigation)
- ❌ **Real-time updates** → Batch processing only

---

## 4. System Architecture

### 4.1 High-Level Pipeline

```
Source Code Repository
    ↓
[Tree-sitter Parser]
    ├─ Extract: functions, classes, imports, types
    └─ Extract: assignments, variable definitions
    ↓
[Symbol Index] (in-memory during build)
    → Name → (file, line, type, scope)
    ↓
[Call Graph Analyzer] (static analysis)
    → Find CALLS relationships (function X calls Y)
    → Handle: direct calls, method calls, imports
    ↓
[Neo4j Graph Builder]
    ├─ Create nodes: File, Module, Function, Class, Variable, Type
    ├─ Create edges: IMPORTS, CALLS, DEFINES, INHERITS, DEPENDS_ON
    └─ Index for query performance
    ↓
[Query API] (FastAPI)
    ├─ GET /api/symbol/{name} → symbol metadata
    ├─ GET /api/context/{name}?depth=N → symbol + dependencies
    ├─ POST /api/validate-conflicts → conflict detection
    └─ GET /api/diagnostics → graph stats, coverage report
    ↓
[External Validation]
    → Compare against linters (pylint, eslint)
    → Manual spot-checks on known dependencies
```

### 4.2 Node Types

| Node Type | Attributes | Cardinality (50K LOC repo) |
|-----------|-----------|---------------------------|
| **File** | name, path, language, loc_count | ~50-100 |
| **Module** | name, path | ~10-20 |
| **Function** | name, file, line, signature, is_exported | ~500-1500 |
| **Class** | name, file, line, methods | ~100-300 |
| **Variable** | name, file, line, type_hint | ~1000-3000 |
| **Type** | name, file, definition | ~50-200 |

### 4.3 Edge Types (Relationship)

| Edge Type | Meaning | Example |
|-----------|---------|---------|
| **IMPORTS** | File A imports from File B | `from auth import login` |
| **CALLS** | Function X calls Function Y | `login()` called in `authenticate()` |
| **DEFINES** | File contains Function/Class | Function in module |
| **INHERITS** | Class B extends Class A | `class Manager(User)` |
| **DEPENDS_ON** | Used in function body | Variable used in function |
| **TYPE_OF** | Variable has type | `x: User` |
| **IMPLEMENTS** | Class implements interface | TypeScript interfaces |

### 4.4 API Design (Minimal Endpoints)

#### Endpoint 1: Get Symbol Metadata

```
GET /api/symbol/{symbol_name}

Response: {
  "symbol": "authenticate_user",
  "type": "function",
  "file": "src/auth/core.py",
  "line": 42,
  "signature": "def authenticate_user(username: str, password: str) -> User:",
  "is_exported": true,
  "location": {"file": "...", "line": 42},
  "response_time_ms": 45
}
```

**Purpose:** Locate a symbol, get basic metadata. Fast lookup.

---

#### Endpoint 2: Get Context (Symbol + Dependencies)

```
GET /api/context/{symbol_name}?depth=1&direction=both

Parameters:
  - symbol_name: required, symbol to retrieve
  - depth: optional, 0=symbol only, 1=direct deps, 2=transitive (default=1)
  - direction: optional, inbound|outbound|both (default=both)

Response: {
  "root_symbol": "authenticate_user",
  "root_type": "function",
  "root_file": "src/auth/core.py",
  "root_code_lines": ["def authenticate_user(...):","    ..."],
  
  "dependencies_outbound": [
    {
      "symbol": "check_password",
      "type": "function",
      "edge_type": "CALLS",
      "file": "src/auth/validators.py",
      "signature": "def check_password(pwd: str) -> bool:",
      "distance": 1
    }
  ],
  
  "dependencies_inbound": [
    {
      "symbol": "login_handler",
      "type": "function",
      "edge_type": "CALLS",
      "file": "src/routes/auth.py",
      "distance": 1
    }
  ],
  
  "graph_stats": {
    "total_nodes_in_context": 8,
    "response_payload_bytes": 3240,
    "response_time_ms": 127,
    "contains_circular_dependency": false
  }
}
```

**Purpose:** Agent retrieves a symbol and related code in one call. Minimizes back-and-forth.

---

#### Endpoint 3: Conflict Detection

```
POST /api/validate-conflicts

Request: {
  "tasks": [
    {
      "task_id": "task_1",
      "target_symbols": ["authenticate_user"],
      "operation": "modify"
    },
    {
      "task_id": "task_2",
      "target_symbols": ["login_handler"],
      "operation": "modify"
    }
  ]
}

Response: {
  "can_run_parallel": true,
  "conflicts": [],
  "explanation": "Tasks target non-overlapping symbol sets"
}
```

OR:

```
Response: {
  "can_run_parallel": false,
  "conflicts": [
    {
      "task_1_id": "task_1",
      "task_2_id": "task_2",
      "conflict_type": "direct_dependency",
      "shared_symbols": ["authenticate_user"],
      "severity": "critical",
      "explanation": "task_2 calls task_1's target. Order matters."
    }
  ],
  "recommendation": "Run task_1 first, then task_2"
}
```

**Purpose:** Determine if two tasks can run in parallel. Returns **both** precision and recall-aware detection.

---

#### Endpoint 4: Diagnostics

```
GET /api/diagnostics

Response: {
  "graph_stats": {
    "total_nodes": 4502,
    "total_edges": 12340,
    "node_counts_by_type": {
      "Function": 1243,
      "Class": 287,
      "File": 84,
      "Module": 18,
      "Variable": 2456,
      "Type": 414
    }
  },
  "parser_coverage": {
    "python_files": 64,
    "typescript_files": 20,
    "extracted_functions": 1243,
    "estimated_total_functions": 1265,
    "coverage_percent": 98.3
  },
  "graph_quality": {
    "call_edges": 5240,
    "import_edges": 2140,
    "verified_accuracy": "pending_validation"
  },
  "circular_dependencies": [
    {
      "cycle": ["module_a", "module_b"],
      "edge_count": 2
    }
  ],
  "api_performance": {
    "avg_query_latency_ms": 127,
    "p99_query_latency_ms": 485,
    "last_build_duration_seconds": 324
  }
}
```

**Purpose:** Transparency. Operators see graph quality, coverage, and performance.

---

## 5. Implementation Plan

### 5.1 Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Parser** | Tree-sitter | Multi-language, proven, fast |
| **Graph DB** | Neo4j | Rich query language, transitive closure, handles cyclic data |
| **Vector DB** | ~~FAISS~~ | **Removed from Phase 1** |
| **Embeddings** | ~~OpenAI API~~ | **Removed from Phase 1** |
| **API Server** | FastAPI (Python) | Async, simple, good for prototyping |
| **Testing** | pytest + unittest | Standard Python testing |
| **CI/CD** | GitHub Actions | Integrated, free |
| **Containerization** | Docker Compose | Reproducible setup |

**Rationale for removing Vector DB / Embeddings:**
- High effort: embeddings + semantic search = 2-3 weeks
- Uncertain ROI: unclear if semantic similarity = code relevance
- Can be added in Phase 1.5 if Phase 1 succeeds
- Graph-based retrieval (dependency walking) is sufficient for MVP

---

### 5.2 Deliverables by Week

| Week(s) | Deliverable | Success Criteria |
|---------|-------------|------------------|
| **1-2** | Environment setup | Docker Compose runs Neo4j + API server locally in <5 min |
| **3-4** | Tree-sitter integration | Extract 100% of functions, classes, imports from test files |
| **5** | Call graph analysis | Identify 95%+ of direct function calls |
| **6** | Neo4j graph construction | All 6 edge types present; queries run in <100ms |
| **7-8** | API endpoints 1-3 | All 3 endpoints functional; latency <500ms |
| **9** | Conflict detection | 90%+ precision, 90%+ recall on test cases |
| **10** | Circular dependency handling | Detect cycles, prevent infinite loops, log warnings |
| **11-12** | Validation & testing | Parser coverage, call graph accuracy verified |
| **13-14** | Documentation + diagnostics | README, API spec, architecture diagram complete |
| **15-16** | Benchmark & optimization | Measure against Phase 1 criteria; final tuning |

---

### 5.3 Test Strategy

#### A. Parser Unit Tests (Week 3-4)

**Test 1: Function Extraction (Python)**

```python
def test_extract_functions_python():
    code = """
    def authenticate_user(username: str) -> User:
        check_password(username)
        return User(username)
    
    def check_password(username: str) -> bool:
        return len(username) > 0
    """
    symbols = parse_python(code)
    
    assert len(symbols) == 2
    assert symbols[0].name == "authenticate_user"
    assert symbols[0].signature == "def authenticate_user(username: str) -> User:"
    assert symbols[1].name == "check_password"
```

**Test 2: Import Extraction**

```python
def test_extract_imports_python():
    code = """
    from auth.core import authenticate_user
    import database as db
    from typing import Optional
    """
    imports = parse_python(code)
    
    assert len(imports) == 3
    assert imports[0].source == "auth.core"
    assert imports[0].imported_name == "authenticate_user"
```

**Test 3: Class Hierarchy**

```python
def test_extract_class_inheritance_python():
    code = """
    class User:
        pass
    
    class Manager(User):
        pass
    """
    classes = parse_python(code)
    
    assert classes[1].parent == "User"
```

**Test 4: TypeScript Equivalents**

```python
def test_extract_functions_typescript():
    code = """
    export function authenticateUser(username: string): User {
        checkPassword(username);
        return new User(username);
    }
    """
    symbols = parse_typescript(code)
    
    assert len(symbols) == 1
    assert symbols[0].is_exported == True
    assert symbols[0].name == "authenticateUser"
```

---

#### B. Graph Construction Tests (Week 6-7)

**Test 1: Call Graph Accuracy**

```python
def test_call_graph_python():
    # Real function in test repo
    repo_path = "test_repos/simple_api_10k"
    graph = build_graph(repo_path)
    
    # Known fact: views.py::list_users calls db.py::get_users
    calls = graph.query("""
        MATCH (f1:Function {name: "list_users"})-[r:CALLS]->(f2:Function {name: "get_users"})
        RETURN r
    """)
    assert len(calls) > 0
```

**Test 2: Import Graph Accuracy**

```python
def test_import_graph_python():
    repo_path = "test_repos/simple_api_10k"
    graph = build_graph(repo_path)
    
    # Known: src/routes/auth.py imports from src/auth/core.py
    imports = graph.query("""
        MATCH (f1:File {name: "auth.py"})-[r:IMPORTS]->(f2:File {name: "core.py"})
        WHERE f1.path CONTAINS "routes" AND f2.path CONTAINS "auth"
        RETURN r
    """)
    assert len(imports) > 0
```

**Test 3: Node Count Sanity Check**

```python
def test_graph_node_distribution_50k_loc():
    repo_path = "test_repos/medium_webapp_50k"
    graph = build_graph(repo_path)
    
    nodes_by_type = graph.query("""
        MATCH (n)
        RETURN labels(n)[0] as type, COUNT(n) as count
        ORDER BY count DESC
    """)
    
    # Sanity check: expect 500-1500 functions in 50K LOC
    function_count = next(n["count"] for n in nodes_by_type if n["type"] == "Function")
    assert 500 < function_count < 2000
```

---

#### C. API Integration Tests (Week 8-9)

**Test 1: Symbol Lookup Latency**

```python
@pytest.mark.asyncio
async def test_get_symbol_latency():
    client = create_test_client()
    
    response = await client.get("/api/symbol/authenticate_user")
    
    assert response.status_code == 200
    assert response.json()["symbol"] == "authenticate_user"
    assert response.json()["response_time_ms"] < 200  # Should be fast
```

**Test 2: Context Retrieval (Depth 1)**

```python
@pytest.mark.asyncio
async def test_get_context_depth_1():
    client = create_test_client()
    
    response = await client.get("/api/context/authenticate_user?depth=1")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return root symbol
    assert data["root_symbol"] == "authenticate_user"
    
    # Should return only direct dependencies
    assert all(dep["distance"] == 1 for dep in data["dependencies_outbound"])
    
    # Payload size check
    assert data["graph_stats"]["response_payload_bytes"] < 50000
```

**Test 3: Conflict Detection (Negative Case)**

```python
@pytest.mark.asyncio
async def test_validate_conflicts_safe():
    client = create_test_client()
    
    response = await client.post("/api/validate-conflicts", json={
        "tasks": [
            {"task_id": "t1", "target_symbols": ["function_a"], "operation": "modify"},
            {"task_id": "t2", "target_symbols": ["function_b"], "operation": "modify"}
        ]
    })
    
    data = response.json()
    
    # Assuming function_a and function_b don't interact
    assert data["can_run_parallel"] == True
    assert len(data["conflicts"]) == 0
```

**Test 4: Conflict Detection (Positive Case)**

```python
@pytest.mark.asyncio
async def test_validate_conflicts_unsafe():
    client = create_test_client()
    
    response = await client.post("/api/validate-conflicts", json={
        "tasks": [
            {"task_id": "t1", "target_symbols": ["check_password"], "operation": "modify"},
            {"task_id": "t2", "target_symbols": ["authenticate_user"], "operation": "modify"}
        ]
    })
    
    data = response.json()
    
    # authenticate_user calls check_password → conflict
    assert data["can_run_parallel"] == False
    assert len(data["conflicts"]) > 0
    assert data["conflicts"][0]["conflict_type"] == "direct_dependency"
```

---

#### D. Validation Against Ground Truth (Week 11-12)

**Test 1: Compare Against Linter Results**

```python
def test_call_graph_vs_pylint():
    """
    Run pylint on repo, extract all "unused-import" and "undefined-name" warnings.
    Cross-reference with our graph: if we say X calls Y, pylint should not warn.
    """
    repo_path = "test_repos/medium_webapp_50k"
    graph = build_graph(repo_path)
    
    pylint_results = run_pylint(repo_path)
    undefined_names = [w for w in pylint_results if w.type == "undefined-name"]
    
    # For each undefined name, check if it's in our call graph
    false_negatives = 0
    for warning in undefined_names:
        symbol_name = warning.symbol
        # If we have this symbol in graph but didn't detect its call → false negative
        if graph.symbol_exists(symbol_name) and not graph.is_called(symbol_name):
            false_negatives += 1
    
    # Allow <5% false negatives
    assert false_negatives / len(undefined_names) < 0.05
```

**Test 2: Manual Spot-Check**

```python
def test_manual_validation_known_dependencies():
    """
    Hard-code a set of known dependencies in the test repo.
    Verify our graph finds them.
    """
    repo_path = "test_repos/simple_api_10k"
    graph = build_graph(repo_path)
    
    known_calls = [
        ("views.list_users", "db.get_users"),
        ("views.create_user", "db.insert_user"),
        ("auth.login", "auth.check_password"),
    ]
    
    for caller, callee in known_calls:
        found = graph.query(f"""
            MATCH (f1:Function {{fqn: "{caller}"}})-[r:CALLS]->(f2:Function {{fqn: "{callee}"}})
            RETURN COUNT(r) as count
        """)
        assert found > 0, f"Missing call: {caller} → {callee}"
```

---

#### E. Scalability Tests (Week 12)

**Test 1: Graph Performance at 50K LOC**

```python
def test_graph_query_performance_50k():
    repo_path = "test_repos/medium_webapp_50k"
    graph = build_graph(repo_path)
    
    # Measure latency on various queries
    latencies = []
    
    for symbol_name in ["authenticate_user", "login_handler", "api_request"]:
        start = time.time()
        _ = graph.query(f"""
            MATCH (f:Function {{name: "{symbol_name}"}})-[r:CALLS*..2]->(dep)
            RETURN DISTINCT dep
        """)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
    
    p99 = np.percentile(latencies, 99)
    assert p99 < 500  # Must be under 500ms p99
```

**Test 2: Graph Performance at 200K LOC**

```python
def test_graph_query_performance_200k():
    repo_path = "test_repos/complex_monorepo_200k"  # Only run if Phase 1 early success
    graph = build_graph(repo_path)
    
    latencies = []
    
    for _ in range(50):  # Sample 50 random queries
        symbol = random_symbol_from_graph(graph)
        start = time.time()
        _ = graph.get_context(symbol, depth=2)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
    
    p99 = np.percentile(latencies, 99)
    median = np.percentile(latencies, 50)
    
    # Should still be reasonable at larger scale
    assert p99 < 1000  # Slightly relaxed for 200K LOC
    assert median < 300
```

---

## 6. Success Criteria (Go/No-Go Decision)

### Weighted Rubric (Not All-or-Nothing)

Each metric has a weight. **Must score ≥70% overall to proceed to Phase 2.**

| Metric | Target | Weight | Pass? |
|--------|--------|--------|-------|
| **Parser Coverage** | 98%+ functions/classes extracted | 25% | [ ] |
| **Call Graph Accuracy** | 95%+ precision (validated via linting) | 25% | [ ] |
| **Query Latency** | <500ms p99 on 50K LOC | 20% | [ ] |
| **Conflict Detection** | 90%+ precision AND 90%+ recall | 15% | [ ] |
| **Circular Dep Handling** | No infinite loops; documented | 10% | [ ] |
| **API Response Efficiency** | <50KB median payload | 5% | [ ] |

### Minimum Acceptable Performance

**PASS (Go to Phase 2):** ≥70% weighted score + Parser Coverage ≥95%

**PARTIAL (Phase 1.5 - 4-week extension):** 60-69% weighted score
- Identified fixable issues (e.g., latency optimization, parser gaps)
- Plan for remediation exists

**FAIL (Pivot or Abandon):** <60% weighted score
- OR Parser Coverage <90% (fundamental parser issue)
- OR Latency consistently >1s (architectural issue)

---

## 7. Test Repositories

### Repo 1: Simple API Server (10K LOC, Python)

**Characteristics:**
- Single package (no cross-package complexity)
- ~100 functions, ~15 files
- Shallow dependency tree
- Fast iteration baseline

**Use:** Weekly local testing, parser validation

---

### Repo 2: Medium Web Application (50K LOC, Mixed)

**Characteristics:**
- Python backend (Flask/FastAPI) + TypeScript frontend
- ~1000-1500 functions across 80-100 files
- Cross-file imports, some circular dependencies
- Real-world complexity

**Use:** Primary integration testing, API validation

---

### Repo 3: Complex Monorepo (200K LOC, Mixed)

**Characteristics:**
- Multiple services (Python + TypeScript + Go)
- ~5000+ functions across 500+ files
- Multiple circular dependencies
- Dynamic imports (some may not be statically analyzable)

**Use:** Scalability gate (run if Phase 1 on track by week 10)

---

## 8. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Tree-sitter misses symbols** (e.g., dynamic calls) | Medium | Medium | Unit tests on patterns; document coverage limits |
| **Circular dependencies break transitive closure** | High | High | **Solve Week 10**: detect cycles, mark as unsafe, document |
| **Neo4j query performance degrades at scale** | Medium | High | Weekly latency profiling; add indexes before regression |
| **Call graph has 85%+ accuracy, not 95%** | Low | Medium | Acceptable for Phase 1; refine in Phase 1.5 |
| **Test repos too small to validate scalability** | Low | Medium | Prepared: have 200K LOC repo ready by week 5 |
| **Scope creep (embeddings, incremental updates)** | High | High | Strict scope gate: PR review blocks Phase 2 features |
| **API latency >500ms due to Neo4j design** | Medium | Medium | Migrate to query caching (Redis) in Phase 1.5 |
| **Conflict detection has high false negatives** | Low | High | Accept <90% recall in Phase 1, improve in Phase 2 |

---

## 9. Circular Dependency Handling (Explicit)

### Problem Statement

When module A imports B and B imports A, transitive dependency closure can become infinite:
```
A → B → A → B → ...
```

### Phase 1 Solution

**Approach:** Detect, mark, and transparently report.

1. **Cycle Detection (Week 10):**
   - Run DFS on import graph
   - Identify all cycles
   - Store in separate index: `CIRCULAR_CYCLES`

2. **Cycle Marking:**
   - Flag affected nodes: `has_circular_dependency = true`
   - In API response: `"contains_circular_dependency": true`
   - In diagnostics: list all cycles with involved modules

3. **Conservative Conflict Detection:**
   - Any symbol in a cycle: assume **parallel-unsafe**
   - Recommendation: "Run tasks involving these symbols sequentially"

### Example

```python
def test_circular_dependency_handling():
    """Module A imports B, B imports A"""
    code_a = "from module_b import func_b"
    code_b = "from module_a import func_a"
    
    graph = build_graph(...)
    cycles = graph.detect_cycles()
    
    assert len(cycles) == 1
    assert "module_a" in cycles[0]
    assert "module_b" in cycles[0]
```

---

## 10. Acceptance Criteria (Definition of Done)

### Code Quality

- [ ] All tests pass: `pytest --cov=src --cov-min-percentage=80`
- [ ] No warnings: `mypy src --strict` and `pylint src`
- [ ] Linting clean: `black` + `flake8` pass without issues
- [ ] API documented: OpenAPI spec auto-generated from FastAPI
- [ ] Docker setup reproducible: `docker-compose up` runs in <5 min

### Documentation

- [ ] README with setup instructions (< 10 min from clone to running)
- [ ] Architecture diagram (ASCII or PNG) showing all components
- [ ] API endpoint examples with curl/Python
- [ ] Glossary of terms (node types, edge types, metrics)
- [ ] Known limitations (what parser does/doesn't handle)

### Testing

- [ ] Unit test coverage ≥80%
- [ ] Integration tests on all 3 repos
- [ ] Validation against linting results
- [ ] Latency benchmarks logged
- [ ] Test results reproducible via CI/CD

### Evaluation

- [ ] Parser coverage report (% of symbols extracted)
- [ ] Call graph accuracy report (spot-checked against ground truth)
- [ ] Conflict detection precision/recall (test cases)
- [ ] Performance summary: latency, payload size, query times
- [ ] Known issues and future improvements listed

---

## 11. Team & Resources

### Required Roles

| Role | FTE | Responsibilities |
|------|-----|------------------|
| **Backend Engineer** | 1.0 | Graph API, Neo4j, FastAPI |
| **Static Analysis Engineer** | 0.5 | Tree-sitter, call graph analysis |
| **QA/Test Engineer** | 0.5 | Test automation, validation |

**Total: 2 FTE for 16 weeks**

### Required Infrastructure

- **Development:** 16GB RAM machine (local Neo4j + indexing)
- **CI/CD:** GitHub Actions (2 concurrent runners)
- **Storage:** 50GB for test repos + database snapshots
- **Monitoring:** Simple logging (no distributed tracing needed)

---

## 12. Timeline & Milestones

### Key Dates

| Week | Milestone | Gate |
|------|-----------|------|
| Week 2 | Environment ready | Can parse first repo |
| Week 5 | Call graph working | 95%+ of known calls detected |
| Week 8 | API endpoints live | Latency <500ms on 50K LOC |
| Week 10 | Circular deps solved | No infinite loops, documented |
| Week 12 | Validation complete | Graph accuracy verified |
| Week 14 | Documentation done | README + API spec complete |
| Week 16 | Go/No-go decision | Review against success criteria |

---

## 13. Go/No-Go Decision Process

### Week 15 Review Meeting

**Attendees:**
- Tech Lead
- Backend Engineer
- Product Owner
- One external reviewer (for objectivity)

**Agenda:**
1. Present metrics against success criteria
2. Discuss risks and mitigations
3. Vote: Go / Partial / No-go

### Decision Rules

**GO (Proceed to Phase 2):**
- Weighted score ≥70%
- Parser coverage ≥95%
- No critical bugs
- Team consensus

**PARTIAL (Phase 1.5 extension, 4 weeks):**
- Weighted score 60-69%
- Issues are fixable (e.g., query optimization)
- Plan for remediation clear

**NO-GO (Pivot or abandon):**
- Weighted score <60%
- OR Parser coverage <90%
- OR Fundamental architectural issue
- OR Neo4j unsuitable for scale

---

## 14. Phase 2 Readiness Criteria

If Phase 1 succeeds, Phase 2 can begin with:

1. ✓ Stable, validated graph API
2. ✓ Known accuracy limits (documented)
3. ✓ Performance baseline established
4. ✓ Test infrastructure in place
5. ✓ Team familiar with codebase

Phase 2 focus: **Incremental updates from git diffs** (not new API, not agent evaluation).

---

## 15. What Changed from Original Spec

| Original | Revised | Reason |
|----------|---------|--------|
| Duration: 12 weeks | Duration: 16 weeks | More realistic; added buffer for unknowns |
| Success metric: "15%+ agent improvement" | Success metric: Observable API metrics | Agent improvement conflates agent + API quality; impossible to isolate |
| Baseline: "raw grep" | Baseline: Removed agent comparison | Phase 1 validates API, not agent |
| FAISS + embeddings included | FAISS + embeddings removed | High effort, uncertain ROI; can add Phase 1.5 |
| 4 API endpoints | 4 API endpoints (simplified) | Removed redundant semantic search endpoint |
| All-or-nothing go/no-go | Weighted rubric go/no-go | More realistic; allows partial success and iteration |
| Circular deps as risk | Circular deps as blocking issue to solve | Will definitely occur; don't defer |
| Token-based metrics | Payload/latency metrics | Token counts are LLM-specific, not API-specific |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Subgraph** | Subset of graph focused on one symbol and its dependencies |
| **Call Graph** | Graph of function-to-function calls (CALLS edges) |
| **Import Graph** | Graph of file-to-file / module-to-module imports (IMPORTS edges) |
| **Transitive Dependency** | Indirect dependency: A → B → C means A transitively depends on C |
| **FQN (Fully Qualified Name)** | Unique identifier for a symbol: `module.submodule.ClassName.method_name` |
| **Conflict** | Two tasks cannot run in parallel because they share modified symbols or have dependency relationship |
| **Circular Dependency** | Cycle in graph: A imports B, B imports A |
| **Parse Coverage** | Percentage of actual symbols extracted by parser (vs. total in repo) |
| **Call Graph Accuracy** | Percentage of extracted calls that are correct (validated against ground truth) |

---

## Appendix B: API Examples

### Example 1: Get Symbol

```bash
curl -s http://localhost:8000/api/symbol/authenticate_user | jq .
```

```json
{
  "symbol": "authenticate_user",
  "type": "function",
  "file": "src/auth/core.py",
  "line": 42,
  "signature": "def authenticate_user(username: str, password: str) -> User:",
  "is_exported": true,
  "response_time_ms": 45
}
```

### Example 2: Get Context

```bash
curl -s "http://localhost:8000/api/context/authenticate_user?depth=1&direction=outbound" | jq .
```

```json
{
  "root_symbol": "authenticate_user",
  "root_type": "function",
  "root_file": "src/auth/core.py",
  "dependencies_outbound": [
    {
      "symbol": "check_password",
      "type": "function",
      "edge_type": "CALLS",
      "file": "src/auth/validators.py",
      "distance": 1
    },
    {
      "symbol": "User",
      "type": "class",
      "edge_type": "DEPENDS_ON",
      "file": "src/models/user.py",
      "distance": 1
    }
  ],
  "dependencies_inbound": [
    {
      "symbol": "login_handler",
      "type": "function",
      "edge_type": "CALLS",
      "file": "src/routes/auth.py",
      "distance": 1
    }
  ],
  "graph_stats": {
    "total_nodes_in_context": 5,
    "response_payload_bytes": 2840,
    "response_time_ms": 127,
    "contains_circular_dependency": false
  }
}
```

### Example 3: Validate Conflicts

```bash
curl -s -X POST http://localhost:8000/api/validate-conflicts \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"task_id": "t1", "target_symbols": ["check_password"], "operation": "modify"},
      {"task_id": "t2", "target_symbols": ["authenticate_user"], "operation": "modify"}
    ]
  }' | jq .
```

```json
{
  "can_run_parallel": false,
  "conflicts": [
    {
      "task_1_id": "t1",
      "task_2_id": "t2",
      "conflict_type": "indirect_dependency",
      "shared_symbols": ["check_password"],
      "severity": "critical",
      "explanation": "Task t2 (authenticate_user) calls Task t1's target (check_password). Task t1 must run first."
    }
  ],
  "recommendation": "Run t1 first, then t2"
}
```

---

## Appendix C: Repository

**GitHub:** [To be created]

**Structure:**

```
codebase-project-os/
├── src/
│   ├── parser/              # Tree-sitter integration
│   ├── graph_builder/       # Neo4j graph construction
│   ├── api/                 # FastAPI endpoints
│   ├── validation/          # Graph quality checks
│   └── utils/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── validation/
├── docs/
│   ├── architecture.md
│   ├── api_spec.md
│   └── known_limitations.md
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── Makefile
└── README.md
```

---

## Appendix D: Known Limitations

### Parser Limitations (Out of Scope for Phase 1)

- ❌ Dynamic imports: `__import__()`, `importlib.import_module()`
- ❌ Dynamic calls: `getattr(obj, func_name)()`
- ❌ Metaprogramming: Decorators that modify function signatures
- ❌ Eval/exec: Code generated at runtime

**Impact:** Call graph will have ~10-15% false negatives on complex codebases.

**Mitigation:** Document limits; flag uncertain calls in API response.

### Language Support (Phase 1)

- ✓ Python 3.6+
- ✓ TypeScript / JavaScript (ES6+)
- ❌ Go, Rust, Java (future phases)

---

## Appendix E: Rollback Plan

If Phase 1 fails (No-Go decision):

1. **Option A: Refocus (4-week Phase 1.5)**
   - Focus only on Python (drop TypeScript)
   - Reduce to 50K LOC only (drop 10K and 200K)
   - Focus on parser accuracy (core blocker)

2. **Option B: Pivot to LSP**
   - Use existing Language Server Protocol tools
   - Build agent integration layer instead
   - Leverage proven tools, reduce implementation risk

3. **Option C: Abandon**
   - Acknowledge hypothesis is invalid
   - Pursue alternative approaches (e.g., RAG-based code retrieval)
   - Archive findings for future reference

---

**End of Phase 1 MVP Specification (Revised)**
