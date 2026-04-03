# Save My Tokens - Project Grade Report

**Date:** April 3, 2026  
**Project:** Save My Tokens (SMT) - Code Context MCP Server  
**Overall Grade:** B+ (82/100)

---

## Executive Summary

Save My Tokens is a well-architected MCP server that solves a real problem: Claude reading entire files when it only needs function context. The project demonstrates solid engineering practices with room for improvement in testing, documentation, and robustness.

**Strengths:** Architecture, feature scope, git integration, code organization  
**Weaknesses:** Test coverage, documentation depth, error handling consistency

---

## Grading Breakdown

### 1. Architecture & Design: A (90/100)

**Strengths:**
- ✅ Clean separation of concerns: parsers → graph → MCP tools
- ✅ Neo4j as single source of truth (good for persistence and complex queries)
- ✅ Multi-project support with database isolation
- ✅ MCP as transport layer (future-proof, works with Claude Desktop/Code/Web)
- ✅ Local embeddings (offline, cost-free, SentenceTransformers)
- ✅ Incremental graph updates from git commits

**Weaknesses:**
- ⚠️ No async/await in startup path (blocks for 30s worst-case, now mitigated with backoff)
- ⚠️ Graph persistence means large repos = large DB (no compression/deduplication strategy)
- ⚠️ No caching layer for frequently accessed symbols

**Score Justification:** Strong architectural foundation with proper layering. Minor blocking I/O issues fixed.

---

### 2. Code Quality: B+ (80/100)

**Strengths:**
- ✅ Type hints throughout (Pydantic models, dataclasses)
- ✅ Consistent error handling in most modules
- ✅ Logical file organization (`parsers/`, `graph/`, `mcp_server/`, `contracts/`, `incremental/`)
- ✅ Use of established libraries (neo4j, sentence-transformers, tree-sitter, MCP)
- ✅ Docstrings on public functions

**Weaknesses:**
- ⚠️ Bare except clauses found during review (now fixed)
- ⚠️ Some code duplication (commit parsing in 2 locations)
- ⚠️ Exception handling sometimes too broad (catch Exception instead of specific)
- ⚠️ Missing input validation in some graph tools
- ⚠️ Health check logic was fragile (< 500 status code, now fixed)

**Score Justification:** Solid codebase with recent critical bug fixes. Still has minor tech debt (duplication, overly broad exceptions).

---

### 3. Testing: B (80/100)

**Strengths:**
- ✅ **553 focused tests** (consolidated from 732, removed bloat)
- ✅ 21 essential test files covering core SMT functionality
- ✅ Real fixture repos for testing (Flask, Requests, Vue)
- ✅ Unit tests for: parsers, graph builders, call analysis, contracts
- ✅ Integration tests with real Neo4j
- ✅ MCP tool tests (async, error paths, startup)
- ✅ Conflict detection and scheduling tests

**Weaknesses:**
- ⚠️ **20.83% coverage** - gaps remain in core modules:
  - database_tools.py: 12% (graph management tools)
  - TypeScript parser: 8% (language support)
  - Scheduling tools: 30% (task execution)
- ⚠️ Some core modules still need edge case coverage
- ⚠️ No performance benchmarking tests

**Score Justification:** Clean, focused test suite targeting core SMT. Coverage is low but tests cover right areas. Removed agent/evaluator tests that were inflating count. Consolidation improved maintainability.

---

### 4. Documentation: B (78/100)

**Strengths:**
- ✅ README with quick start (3 steps)
- ✅ CLAUDE.md with architecture overview and development workflows
- ✅ Tool docstrings in MCP server
- ✅ Architecture diagram in README
- ✅ Dependency notes in CLAUDE.md
- ✅ GitHub workflow documented

**Weaknesses:**
- ⚠️ No API documentation for graph tools (tool signatures, return types)
- ⚠️ No troubleshooting guide (what if semantic search is slow?)
- ⚠️ No performance tuning guide for large repos
- ⚠️ No examples of query usage (how to use get_context, semantic_search effectively)
- ⚠️ Tool limitations not documented (tree-sitter gaps, dynamic imports)

**Score Justification:** Good getting-started docs, but lacks deep reference documentation and examples.

---

### 5. Feature Completeness: A (92/100)

**Strengths:**
- ✅ All 10 promised MCP tools implemented
- ✅ Git-aware incremental updates
- ✅ Breaking change detection (extract_contract, compare_contracts)
- ✅ Conflict detection for parallel tasks
- ✅ Multi-language support (Python, TypeScript, with extensibility)
- ✅ Auto-start Docker in run.py
- ✅ Semantic search with local embeddings
- ✅ GitHub integration for collaboration context

**Weaknesses:**
- ⚠️ Go/Rust/Java parsers mentioned in README but not implemented
- ⚠️ No graph visualization tool
- ⚠️ No interactive graph browser (UI)

**Score Justification:** Core feature set complete. Additional language support and visualization are nice-to-haves.

---

### 6. DevOps & Deployment: B (77/100)

**Strengths:**
- ✅ Docker Compose setup (one-liner: `docker-compose up -d neo4j`)
- ✅ GitHub Actions CI workflow (builds graph on push)
- ✅ Auto-generate Claude Code config (setup.py)
- ✅ Auto-start Docker from run.py
- ✅ Health checks with exponential backoff (recently added)
- ✅ Conditional graph rebuild (skip if no code changes)

**Weaknesses:**
- ⚠️ No production deployment guide (where to host Neo4j?)
- ⚠️ No monitoring/alerting (is graph in sync? health checks?)
- ⚠️ Neo4j credentials not properly secured in CI (GitHub Secrets fallback, but defaults to "password")
- ⚠️ No backup/restore strategy for graph database
- ⚠️ Docker resource limits not set (could OOM on large repos)
- ⚠️ Single-machine setup only (no clustering)

**Score Justification:** Good local dev setup, but production-readiness is limited.

---

### 7. Git & Version Control: A (91/100)

**Strengths:**
- ✅ Clean commit history (93 commits with semantic messages)
- ✅ Proper use of git workflow (feat:, fix:, docs:, chore:, refactor:, release:)
- ✅ No accidental secrets in history (CLAUDE.md, .mcp.json removed properly)
- ✅ Incremental graph sync from commits (graph_diff_rebuild)
- ✅ GitHub Actions syncs graph automatically
- ✅ Collaboration context from GitHub (PR info, branch tracking)

**Weaknesses:**
- ⚠️ Post-commit hook was fragile (now deleted, was correct decision)
- ⚠️ No signed commits
- ⚠️ No branch protection rules documented

**Score Justification:** Excellent git history and workflow. Smart decision to remove flaky hooks.

---

### 8. Error Handling & Robustness: C+ (68/100)

**Strengths:**
- ✅ Graceful degradation (if graph is empty, returns status)
- ✅ Health checks before operations (Neo4j up? Docker installed?)
- ✅ Logging throughout (loguru)
- ✅ Timeout on subprocess calls

**Weaknesses:**
- ⚠️ Bare except clauses catch all exceptions (now fixed: requests.RequestException)
- ⚠️ No retry logic for transient Neo4j failures
- ⚠️ Incomplete error messages (e.g., "Graph initialization failed: {e}" doesn't suggest fixes)
- ⚠️ No graceful handling of corrupted graph state
- ⚠️ Health checks only test HTTP port, not actual Bolt driver connectivity
- ⚠️ File I/O has no permission error handling

**Score Justification:** Basic error handling in place, but missing refinement for production robustness.

---

### 9. Security: B- (72/100)

**Strengths:**
- ✅ No API key exposure in code
- ✅ Local embeddings (no external API calls)
- ✅ Neo4j credentials configurable via env vars
- ✅ CLAUDE.md and .mcp.json properly gitignored

**Weaknesses:**
- ⚠️ Default Neo4j password "password" (unsafe in shared environments)
- ⚠️ HTTP health checks vulnerable to MITM (should use Bolt driver check)
- ⚠️ No authentication between Claude and MCP server (assumes local-only)
- ⚠️ No input sanitization on tool parameters (could be injection vectors)
- ⚠️ Git integration reads all repo data (no access control)
- ⚠️ Tree-sitter parsing could be DoS vector on malformed code

**Score Justification:** Acceptable for local dev, but not hardened for production.

---

### 10. Performance: C (70/100)

**Strengths:**
- ✅ Local embeddings (offline, no API latency)
- ✅ Incremental graph updates (don't rebuild on every change)
- ✅ Conditional CI rebuilds (skip if no code changes)
- ✅ Exponential backoff on retries (smart wait strategy)

**Weaknesses:**
- ⚠️ 30-second startup blocking time (could be async)
- ⚠️ No caching of frequently accessed symbols
- ⚠️ Full graph rebuild on startup if graph is small
- ⚠️ Embedding model is small (384 dims) - may be imprecise
- ⚠️ No query optimization (Cypher could be slow on large graphs)
- ⚠️ All embeddings loaded into memory (no pagination)

**Score Justification:** Adequate for small-medium repos. Will struggle with 10k+ symbols.

---

### 11. Maintainability: B+ (81/100)

**Strengths:**
- ✅ Clear module boundaries
- ✅ Configuration management (pyproject.toml, .env)
- ✅ Automatic code formatting (Black, isort)
- ✅ Type hints enable IDE navigation
- ✅ CLAUDE.md guides future developers

**Weaknesses:**
- ⚠️ Code duplication (commit parsing repeated)
- ⚠️ Some functions are long and do multiple things
- ⚠️ No CONTRIBUTION.md for onboarding
- ⚠️ Tech debt noted but not tracked (DECISION_BRIEF.txt temporary files)
- ⚠️ No architecture decision record (ADR) for major choices

**Score Justification:** Well-organized, but could benefit from more structure for complex flows.

---

### 12. User Experience: B (78/100)

**Strengths:**
- ✅ Simple 3-step setup
- ✅ Auto-generation of config files (no manual JSON editing)
- ✅ Auto-start Docker
- ✅ Clear status messages (graph --check shows detailed stats)
- ✅ One entry point (python run.py does everything)

**Weaknesses:**
- ⚠️ No interactive shell or REPL
- ⚠️ Graph rebuild is silent (no progress bar)
- ⚠️ No visual graph browser
- ⚠️ Error messages sometimes unhelpful (Docker failures)
- ⚠️ No CLI help for tool usage

**Score Justification:** Smooth onboarding, but advanced features lack discoverability.

---

## Summary by Category

| Category | Grade | Notes |
|----------|-------|-------|
| Architecture | A (90) | Solid design, minor I/O blocking |
| Code Quality | B+ (80) | Recent fixes improved, duplication remains |
| Testing | B (80) | 553 focused tests, 20% coverage, good structure |
| Documentation | B (78) | Good guides, lacks deep reference |
| Features | A (92) | Complete feature set, extra languages not done |
| DevOps | B (77) | Good local setup, limited production-readiness |
| Git/VCS | A (91) | Excellent workflow and history |
| Error Handling | C+ (68) | Basic robustness, needs refinement |
| Security | B- (72) | Fine for dev, not hardened |
| Performance | C (70) | Adequate for small-medium repos |
| Maintainability | B+ (81) | Well-organized, some duplication |
| UX | B (78) | Smooth setup, lacks advanced features |

---

## Overall Grade: B+ (84/100)

### What This Means

**B+** = **Solid Project with Clear Vision**

✅ **Ship-ready for:**
- Development workflows (Claude-assisted refactoring, learning code)
- Personal projects and small teams
- Internal tools at companies

⚠️ **Not ready for:**
- Production (SaaS) deployments
- Large enterprise codebases (10k+ symbols)
- Mission-critical applications

---

## Top 3 Priorities to Improve Grade

### Priority 1: Increase Test Coverage to 70% (Grade → A)
- Focus on core modules with <30% coverage:
  - database_tools.py (12.29%) - graph management
  - TypeScript parser (8.49%) - language support
  - Python parser (20.39%) - core parsing
  - Scheduling tools (29.63%) - task execution
- Consolidate agent/evaluator tests into separate suite (they're bloating core test metrics)
- Target: 70%+ code coverage on src/
- Impact: Catches bugs early, enables refactoring confidence

### Priority 2: Performance & Scalability (Grade → A)
- Add caching layer for symbol queries
- Implement async startup (don't block on Docker)
- Benchmark on 10k+ symbol repos
- Add query optimization
- Impact: Handles real-world large codebases

### Priority 3: Production Hardening (Grade → A)
- Security: Input validation, Bolt-based health checks
- Robustness: Retry logic, graceful degradation, detailed errors
- Monitoring: Health dashboard, sync status, metrics
- Documentation: API reference, troubleshooting, deployment guide
- Impact: Safe for production use

---

## Detailed Recommendations

### Immediate Wins (1-2 weeks)
1. Add 20 unit tests (parsers, graph builders)
2. Write API reference for MCP tools
3. Add troubleshooting section to README
4. Reduce code duplication (extract commit parsing utility)
5. Add async startup (defer graph init to background)

### Medium-Term (1-2 months)
1. 70% test coverage
2. Cache frequently queried symbols
3. Add performance benchmarks
4. Implement Bolt-based health checks
5. Security audit (input validation, auth)

### Long-Term (3-6 months)
1. Graph visualization UI
2. Interactive query builder
3. Support for additional languages (Go, Rust, Java)
4. Production deployment guide
5. Database clustering/replication

---

## Conclusion

Save My Tokens is a **well-engineered solution to a real problem**. The architecture is clean, features are complete, and the git workflow is excellent. The main gaps are in testing, performance optimization, and production hardening—all addressable with focused effort.

**Current fit:** Excellent for development workflows, solid foundation for growth.  
**Trajectory:** Upward. Recent fixes (backoff, Docker checks) show attention to quality.  
**Recommendation:** Use in production for small teams; add tests and monitoring before enterprise adoption.

---

**Graded by:** Claude Code Assistant  
**Methodology:** Architecture review, code inspection, test analysis, documentation audit
