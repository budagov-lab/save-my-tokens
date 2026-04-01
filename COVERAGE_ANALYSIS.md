# Test Coverage Analysis & Improvement Plan

**Current State:** April 1, 2026  
**Tests:** 299 passing (100% pass rate)  
**Coverage:** 64.49% (1104 statements untested)

---

## Coverage By Component

### ✅ Excellent Coverage (>85%)
- `config.py` — 100%
- `symbol.py` — 96.15%
- `symbol_index.py` — 96.83%
- `incremental/symbol_delta.py` — 94.74%
- `contract_models.py` — 95.89%
- `node_types.py` — 76%

**Status:** These are well-tested, low-risk components.

---

### ⚠️ Partial Coverage (50-85%)
- `api/query_service.py` — 71.25% (20 statements untested)
- `contracts/extractor.py` — 67.67% (43 untested)
- `parsers/python_parser.py` — 54.37% (47 untested)
- `parsers/symbol_index.py` — 55.56% (28 untested)
- `parsers/base_parser.py` — 56.67% (13 untested)
- `performance/optimizer.py` — 84.42% (12 untested)
- `graph/node_types.py` — 76% (12 untested)
- `neo4j_client.py` — 33.80% (47 untested)

**Issues Found:**
1. **Query Service** — Error paths not tested (line 80, 100-133, etc.)
2. **Contract Extractor** — Edge cases with type hints, complex functions
3. **Python Parser** — File I/O, nested structures, decorators
4. **Neo4j Client** — Database connection, graph operations

---

### ❌ Critical Gaps (0-50%)

#### MCP Server Layer (0-44% coverage)
- `mcp_server/entrypoint.py` — 0% (main entry point!)
- `mcp_server/_app.py` — 63.64% (lifespan not tested)
- `mcp_server/services.py` — 96.61% ✅ (Good!)
- `mcp_server/tools/scheduling_tools.py` — 29.63%
- `mcp_server/tools/incremental_tools.py` — 31.03%
- `mcp_server/tools/contract_tools.py` — 44.83%
- `mcp_server/tools/graph_tools.py` — 44%

**Why:** MCP tools use async/decorators, hard to test directly. Need integration tests.

#### Evaluation & Testing (0%)
- `evaluation/evaluation_runner.py` — 0% (benchmarking)
- `evaluation/metrics_collector.py` — 0% (metrics collection)
- `testing/test_executor.py` — 0% (test runner infrastructure)
- `api/server.py` — 0% (minimal health/stats endpoint)
- `agent/evaluator.py` — 0% (agent evaluation)

**Why:** These are Phase 3 features (not core to MVP). Safe to defer.

#### Language Parsers (8-23%)
- `parsers/typescript_parser.py` — 8.49% (complex tree-sitter binding)
- `parsers/unified_parser.py` — 66.67% (router for multiple parsers)
- `parsers/go_parser.py` — 22.83% (incomplete implementation)
- `parsers/rust_parser.py` — 22.31% (incomplete implementation)
- `parsers/java_parser.py` — 23.93% (incomplete implementation)
- `parsers/import_resolver.py` — 20.31% (relative import logic)

**Why:** Alternative language support is Phase 2/3. Python is primary (54%).

#### Agent Infrastructure (15-37%)
- `agent/baseline_agent.py` — 15.58%
- `agent/base_agent.py` — 16.67%
- `agent/evaluator.py` — 0%
- `agent/execution_engine.py` — 22.94%
- `agent/scheduler.py` — 37.50%

**Why:** Agent evaluation is Phase 3. Core scheduler is 37%, acceptable for Phase 1.

#### Incremental Updates (20-32%)
- `incremental/updater.py` — 20.69% (delta application logic)
- `incremental/diff_parser.py` — 32% (git diff parsing)
- `mcp_server/tools/incremental_tools.py` — 31.03%

**Why:** Implemented in Phase 2, but edge cases untested.

#### Conflict Analysis (27%)
- `graph/conflict_analyzer.py` — 27.68%

**Why:** Recently fixed for false positives, but edge cases remain.

---

## Root Cause Analysis: Why Low Coverage?

### 1. **Async Functions Hard to Test**
   - MCP tools use `async def` with FastMCP context injection
   - Pytest needs `@pytest.mark.asyncio` but tools are registered via decorators
   - **Fix:** Create async test fixtures or integration tests

### 2. **Database Operations (Neo4j)**
   - `neo4j_client.py` — 33.8% coverage
   - Real Neo4j connection needed for full coverage
   - **Fix:** Mock Neo4j or use in-memory fallback for tests

### 3. **Language Parser Complexity**
   - Tree-sitter bindings are opaque
   - Go/Rust/Java parsers are incomplete reference implementations
   - **Fix:** Focus on Python (54% → 80%+), defer other languages to Phase 3

### 4. **Phase 2/3 Features**
   - Evaluation, benchmarking, agent execution not yet integrated
   - These are future enhancements, not MVP-critical
   - **Fix:** Document as Phase 3, don't force coverage now

### 5. **Error Paths**
   - Most untested lines are `except`, `try`, error handling
   - Hard to trigger in happy-path tests
   - **Fix:** Add negative test cases

---

## Improvement Roadmap

### Immediate (Phase 1 Completion)
- [ ] Increase MCP coverage to 50%+ (currently 29-44%)
- [ ] Test error paths in QueryService
- [ ] Python parser coverage to 75%+
- [ ] Target: **70% overall coverage**

### Short-term (Phase 2 Polish)
- [ ] Add async test fixtures for MCP tools
- [ ] Mock Neo4j for `neo4j_client.py`
- [ ] Complete Go/Rust/Java parser coverage
- [ ] Add contract extractor edge cases
- [ ] Target: **75% overall coverage**

### Long-term (Phase 3)
- [ ] Evaluation & benchmarking tests
- [ ] Agent execution tests
- [ ] Performance profiling tests
- [ ] Target: **80%+ coverage**

---

## By-Priority Improvements

### P0: Critical Interface
1. **MCP Entrypoint** (currently 0%)
   - File: `mcp_server/entrypoint.py`
   - Fix: Add simple startup test
   - Impact: Ensures server can start

2. **MCP Tools** (currently 29-44%)
   - Files: `mcp_server/tools/*.py`
   - Fix: Add async integration tests
   - Impact: Validates primary agent interface

### P1: Core Query Engine
1. **QueryService Error Paths** (20 untested lines)
   - File: `api/query_service.py`
   - Lines: 80, 100-133, 149-164
   - Fix: Add negative test cases
   - Impact: Better error handling validation

2. **Conflict Analyzer** (27%)
   - File: `graph/conflict_analyzer.py`
   - Fix: Edge cases with nested dependencies
   - Impact: Safe parallelization detection

### P2: Parsers
1. **Python Parser** (54% → 80%)
   - File: `parsers/python_parser.py`
   - Gap: File I/O, nested structures
   - Fix: Add integration tests with real Python files

2. **Neo4j Client** (33%)
   - File: `graph/neo4j_client.py`
   - Gap: Database operations
   - Fix: Mock or use in-memory for tests

### P3: Future (Phase 2/3)
- Agent evaluation (0%)
- Alternative language parsers
- Incremental updates edge cases

---

## Code Quality Issues Found During Testing

### 1. **Incomplete Language Parsers**
   - Go, Rust, Java parsers have 20-23% coverage
   - Many lines marked as untested: `14, 39-44, 55-70, 90-145, ...`
   - **Status:** These are placeholder implementations
   - **Fix:** Complete in Phase 2 or remove if not needed

### 2. **MCP Tools Use Decorators**
   - Functions registered via `@mcp.tool()` decorator
   - Hard to call directly in tests (need FastMCP context)
   - **Status:** Known limitation of FastMCP
   - **Fix:** Test through QueryService instead (already done ✅)

### 3. **Database-Dependent Code**
   - Neo4j client has many untested paths
   - Cannot fully test without database connection
   - **Status:** By design (graceful fallback)
   - **Fix:** Add mock tests for common paths

### 4. **Async Function Testing**
   - Evaluation runner uses async but has 0% coverage
   - **Status:** Phase 3 feature
   - **Fix:** Defer or add async fixtures

---

## Test Results Summary

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| **Tests** | 210 | 299 | 350+ |
| **Pass Rate** | 100% | 100% | 100% |
| **Coverage** | 60.34% | 64.49% | 70% |
| **MCP Tools** | 0% | 29-96% | 60%+ |
| **Parsers** | 8-54% | 8-54% | 80%+ |

---

## Conclusion

**Status:** Good progress toward production-readiness.

**Remaining Work:**
1. MCP tools need better async test integration
2. Error paths need negative test cases  
3. Python parser needs edge case coverage
4. Phase 2/3 features can be addressed later

**Recommendation:** Current 64.49% coverage is acceptable for Phase 1 MVP completion. Focus Phase 2 on:
- Increasing to 70%+ (MCP integration tests)
- Completing alternative parser implementations
- Adding comprehensive evaluation tests

