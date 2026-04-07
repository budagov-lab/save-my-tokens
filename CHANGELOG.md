# Changelog

All notable changes to Save My Tokens are documented here.

## [0.1.0] - 2026-04-07

### ✨ Features

#### Tier 1: Safety
- **SCC Cycle Detection** — Tarjan's algorithm prevents unbounded context expansion
  - Detects cycles in call graphs
  - Collapses circular dependencies into single nodes
  - Preserves cycle info in output
  - 15 unit tests, 100% coverage

#### Tier 2: Clarity
- **Three Retrieval Modes** — Each answers a specific agent question
  - `definition` — Fast 1-hop lookup (13ms, ~100 tokens)
  - `context` — Bidirectional bounded traversal (19ms, ~200-300 tokens)
  - `impact` — Reverse traversal for breaking changes (23ms, ~250-350 tokens)
- **Connection Pooling** — 6x speedup via session reuse
  - Sub-20ms queries even on large graphs
  - Consistent latency across repeated queries
- **Bounded Traversal** — `--depth N` prevents spiral into entire codebase

#### Tier 3: Trust
- **Validation Reports** — Git freshness checks
  - Shows if graph matches git HEAD
  - Lists commits behind and changed files
  - Appears in footer of all query modes
- **Smart Compression** — Bridge function removal
  - `--compress` flag removes trivial forwarders
  - Detects 1-in, 1-out nodes (not in cycles)
  - Saves 40-50% tokens on dense codebases
  - Iteratively collapses bridge chains

### 🎯 Performance

- Query latency: 13-23ms (99th percentile)
- Token reduction: 60-90% vs reading full files
- Large graphs: tested up to 40k+ nodes
- Graph build: ~30s for typical projects

### 📦 Installation

```bash
pip install -e .
```

Supports Python 3.11+, requires Docker for Neo4j or existing Neo4j instance.

### 🔧 CLI Commands

```
smt build                Build graph from src/
smt definition SYMBOL    What is this? (fast lookup)
smt context SYMBOL       What do I need? (working context)
smt impact SYMBOL        What breaks? (impact analysis)
smt search QUERY         Semantic search
smt diff RANGE           Sync after commits
smt status               Graph health
smt docker up/down       Neo4j management
```

All commands support `--help` for options.

### 📝 Documentation

- **README.md** — Complete guide with examples
- **QUICKSTART.md** — 5-minute setup
- **FINAL_SUMMARY.md** — Architecture & design decisions
- **CONTRIBUTING.md** — Development guide

### ✅ Testing

- 15 SCC cycle detection tests (100% coverage)
- 5 BFS depth computation tests
- 28 conflict analyzer tests
- 0 regressions in existing functionality

### 🏗️ Architecture

- **Parsers** — Tree-sitter for Python + TypeScript
- **Graph** — Neo4j with 5 edge types (CALLS, DEFINES, IMPORTS, INHERITS, MODIFIED_BY)
- **Algorithms** — Tarjan's SCC, BFS, bridge detection
- **CLI** — Click-based with git integration

### 🔐 Safety

- Cycle-safe traversal (never unlimited expansion)
- Type-safe code (mypy strict mode)
- No destructive operations (read-only graph queries)
- Local execution (no external API calls)

### 🚀 Ready for Production

- Fully tested on SMT itself (6,194 nodes)
- Validated on 512k-lines TypeScript codebase (40k+ nodes)
- Connection pooling for predictable latency
- Git freshness validation

### 📋 Known Limitations

- Neo4j Community Edition only (no multi-database support)
- Tree-sitter parsing limitations (no dynamic imports, no type validation)
- Windows Unicode progress bar rendering (doesn't affect functionality)

### 🙏 Thanks

Built with ❤️ for Claude and other code-understanding agents.

---

## Future Roadmap

### v0.2.0 (Planned)
- [ ] MCP wrapper for Claude Desktop
- [ ] More language support (Go, Rust, Java)
- [ ] APOC plugin support for advanced graph queries
- [ ] VS Code extension

### v0.3.0 (Future)
- [ ] Database optimization for 100k+ node graphs
- [ ] Incremental graph updates from git hooks
- [ ] Advanced compression strategies
- [ ] IDE plugins (IntelliJ, Cursor)

---

## Migration Guide

If upgrading from older versions, the CLI interface is backwards compatible. All three query modes now support `--compress` flag for token reduction.

---

## Support

- **Docs:** See README.md and FINAL_SUMMARY.md
- **Issues:** GitHub Issues
- **Contributing:** See CONTRIBUTING.md
