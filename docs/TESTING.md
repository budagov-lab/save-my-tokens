# Testing Strategy - Save My Tokens

## Test Pyramid

```
         ▲
        / \
       / E2E \          Integration tests
      /___────\           (full pipeline)
     /         \
    / Unit      \        Unit tests
   /_____________\     (individual modules)
```

## Unit Tests

**Location**: `tests/unit/`

### Parser Tests (`test_parsers_*.py`)
- Symbol extraction accuracy (functions, classes, imports)
- Docstring parsing
- Type annotation handling
- Edge cases: decorators, nested functions, async/await

**Target Coverage**: 95% of parser code

### Graph Tests (`test_graph.py`)
- Node creation (File, Function, Class, etc.)
- Edge creation (CALLS, IMPORTS, DEFINES, etc.)
- Query correctness
- Neo4j connection

**Target Coverage**: 90%

### API Tests (`test_api_*.py`)
- Response format validation
- Status codes
- Request parameter validation
- Error handling

**Target Coverage**: 85%

### Embeddings Tests (`test_embeddings.py`)
- FAISS index operations
- Embedding generation
- Similarity search accuracy

**Target Coverage**: 80%

## Integration Tests

**Location**: `tests/integration/`

### End-to-End Tests
1. **Parse → Graph → Query** (full pipeline on test repos)
   - Parse 10K LOC repo
   - Build complete graph
   - Query for context, subgraph, search
   - Verify correctness

2. **Query Latency Tests**
   - Measure p99 latency on 50K LOC repo
   - Verify <500ms target met
   - Profile hot paths

3. **Dependency Accuracy Tests**
   - Manual validation of call graphs
   - Compare against known callsites
   - Target: >95% precision

4. **Conflict Detection Tests**
   - Create synthetic conflict scenarios
   - Verify detection correctness
   - Target: 90% precision, 90% recall

## Test Repositories

Three repos of increasing size:

| Repo | Size | Purpose |
|------|------|---------|
| requests | 8.7M (12K LOC) | Quick iteration, parser validation |
| flask | 3.2M (25K LOC) | Primary evaluation, accuracy metrics |
| vue | 9.5M (100K+ LOC) | Scalability testing, performance |

## Running Tests

```bash
# All tests
pytest

# Unit only
pytest tests/unit/

# Integration only
pytest tests/integration/

# Specific test
pytest tests/unit/test_parsers_python.py::test_extract_functions

# With coverage
pytest --cov=src --cov-report=html

# Verbose output
pytest -vv
```

## Continuous Integration (Future)

For Phase 2, add:
- Pre-commit hooks (run fast unit tests)
- GitHub Actions (full test suite on PR)
- Performance regression detection

## Success Criteria

| Metric | Target |
|--------|--------|
| Parser Coverage | 98%+ of functions/classes extracted |
| Query Latency p99 | <500ms on 50K LOC |
| Dependency Accuracy | 95%+ precision |
| Conflict Detection | 90%+ precision, 90%+ recall |
| API Response Payload | <50KB median |
| Code Coverage | ≥80% |
