# SMT Improvements Roadmap

## Alpha Release Complete ✅

Current status: **v0.1.0-alpha** - Core functionality working
- Graph builds successfully
- All 10 MCP tools functional
- Multi-project support ready
- GitHub integration working
- Team workflows documented

## Now: Improvements Phase

Based on alpha feedback and current limitations, here are improvements to work on:

## Priority 1: Core Functionality (High Impact)

### 1.1 Better Edge Types

**Current:** Only DEFINES and IMPORTS (776 edges)
**Goal:** Add semantic relationship types

```
CALLS - function calls another
TYPE_OF - variable has type
INHERITS - class inheritance
DEPENDS_ON - semantic dependency
USES - function uses symbol
RETURNS - function returns type
```

**Impact:** Better context queries, safer parallelization
**Effort:** Medium (1-2 weeks)
**Owner:** To be assigned

### 1.2 Call Graph Analysis

**Current:** Don't track function calls within code
**Goal:** Extract and analyze call chains

```
QueryService.get_context()
  ├── calls: query_service.py:50
  ├── calls: symbol_index.py:20
  └── calls: neo4j_client.py:100
```

**Impact:** Know what functions call what
**Effort:** Medium (1-2 weeks)
**Owner:** To be assigned

### 1.3 Conflict Detection Improvement

**Current:** Basic validation
**Goal:** Advanced conflict analysis

```
PR #42 changes: auth.py:50-80
PR #43 changes: auth.py:70-90
Conflict detected: Both modify same lines
```

**Impact:** Team safety, parallel task detection
**Effort:** High (2-3 weeks)
**Owner:** To be assigned

## Priority 2: Performance (Medium Impact)

### 2.1 Query Caching

**Current:** Every query hits Neo4j
**Goal:** Cache frequent queries (LRU)

```
First query: get_context('Neo4jClient') → 100ms
Cached: get_context('Neo4jClient') → 5ms
```

**Impact:** 10-20x faster repeated queries
**Effort:** Low (3-5 days)
**Owner:** To be assigned

### 2.2 Incremental Graph Updates

**Current:** Rebuild entire graph when code changes
**Goal:** Patch only changed symbols

```
Before: 15 seconds rebuild
After: 500ms delta update
```

**Impact:** Faster workflow, real-time updates
**Effort:** High (2-3 weeks)
**Owner:** To be assigned

### 2.3 Index Optimization

**Current:** Basic indexes on node_id
**Goal:** Advanced indexing strategy

```
- Hash indexes for fast lookups
- Range indexes for range queries
- Full-text indexes for semantic search
```

**Impact:** 2-3x query speed improvement
**Effort:** Medium (1-2 weeks)
**Owner:** To be assigned

## Priority 3: Features (Nice to Have)

### 3.1 Semantic Search Improvements

**Current:** Uses OpenAI embeddings (if configured)
**Goal:** Local embeddings + better ranking

```
Search: "password validation"
Results:
  1. validate_password() - 0.95 (perfect)
  2. check_auth() - 0.82 (related)
  3. encrypt_password() - 0.78 (related)
```

**Impact:** Better code discovery
**Effort:** Medium (1-2 weeks)
**Owner:** To be assigned

### 3.2 Web Dashboard (Bonus)

**Current:** CLI only
**Goal:** Visual graph browser

```
- Graph visualization (D3.js / Cytoscape)
- Search UI
- Dependency explorer
- PR status viewer
```

**Impact:** Better UX for exploration
**Effort:** High (3-4 weeks)
**Owner:** To be assigned

### 3.3 VS Code Extension

**Current:** Integrates via Claude Desktop
**Goal:** Direct VS Code support

```
Right-click on symbol → "Show context"
Sidebar: Current file dependencies
Hover: Show symbol info
```

**Impact:** Seamless IDE integration
**Effort:** High (2-3 weeks)
**Owner:** To be assigned

## Priority 4: Quality (Important)

### 4.1 Test Coverage

**Current:** 37 tests (80% coverage)
**Goal:** 95%+ coverage with edge cases

```
- Integration tests for all MCP tools
- Performance regression tests
- Team collaboration scenarios
- Error handling edge cases
```

**Effort:** Medium (1-2 weeks)
**Owner:** To be assigned

### 4.2 Documentation

**Current:** 8 guides
**Goal:** Comprehensive docs

```
- API reference (auto-generated)
- Architecture deep-dive
- Developer guide
- Deployment guide
- Troubleshooting wiki
```

**Effort:** Low (1 week)
**Owner:** To be assigned

### 4.3 Error Handling

**Current:** Basic error messages
**Goal:** User-friendly errors with fixes

```
Error: "Database does not exist"
Fix: "Run: python run.py to initialize"

Error: "GitHub token invalid"
Fix: "Check token at: https://github.com/settings/tokens"
```

**Effort:** Low (3-5 days)
**Owner:** To be assigned

## Work Schedule

### Week 1-2 (Immediate)

- [ ] Add CALLS edge type
- [ ] Improve error messages
- [ ] Query caching (LRU)
- [ ] More tests

### Week 3-4

- [ ] Better conflict detection
- [ ] Call graph analysis
- [ ] Performance benchmarks

### Week 5-6

- [ ] Incremental updates
- [ ] Semantic search improvements
- [ ] Documentation expansion

### Week 7-8

- [ ] Web dashboard (optional)
- [ ] VS Code extension (optional)
- [ ] Beta release readiness

## How to Contribute

### Pick an Issue

```bash
# See improvements above
# Comment: "I'll work on X"
# Create branch: git checkout -b improve/X
```

### Make Changes

```bash
# Make improvements
# Add tests
# Update docs
git add .
git commit -m "improve: X"
git push origin improve/X
```

### Submit PR

```bash
# Create PR on GitHub
# Link issue: "Fixes #X"
# Describe changes
# Request review
```

## Metrics to Track

After each improvement:

```
- Query latency (target: <50ms)
- Test coverage (target: 95%+)
- Build time (target: <5s)
- Graph size (monitor growth)
- User feedback (issues/discussions)
```

## Open Questions

1. Should we support more languages (Java, Go, Rust)?
2. Should we add real-time collaboration?
3. Should we create SaaS vs self-hosted?
4. What's the priority: performance or features?

## Current Blockers

None! All core functionality working.

## Success Criteria for Beta

- [ ] 95%+ test coverage
- [ ] <100ms p99 query latency
- [ ] Call graph analysis working
- [ ] Better conflict detection
- [ ] Comprehensive documentation
- [ ] Community feedback incorporated

Then → Beta v0.2.0

## Next Release Candidate

**v0.2.0-beta** target: 6-8 weeks
- Performance optimizations complete
- Feature improvements done
- Test coverage solid
- Documentation comprehensive
- Ready for wider adoption

---

**Let's improve SMT together!**

Pick an improvement above and start working.
