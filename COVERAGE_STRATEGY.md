# Coverage Strategy for Save My Tokens

## Problem: 20% overall coverage is misleading

- Many modules are **supporting utilities** (imports, helpers) that don't need 70% coverage
- Focus should be on **user-facing functionality** that affects SMT behavior

## Critical Modules (Target 80%+ Coverage)

### Tier 1: Core Graph Operations
- `src/graph/neo4j_client.py` — Database interface (queries, stats, health)
- `src/graph/graph_builder.py` — Symbol parsing and graph construction
- `src/graph/call_analyzer.py` — Function call edge detection

### Tier 2: MCP Tools (User Entrypoints)
- `src/mcp_server/tools/graph_tools.py` — get_context, get_subgraph
- `src/mcp_server/tools/database_tools.py` — graph_init, graph_rebuild, graph_stats
- `src/mcp_server/tools/contract_tools.py` — extract_contract, compare_contracts
- `src/mcp_server/tools/incremental_tools.py` — parse_diff, apply_diff

### Tier 3: Parser Quality
- `src/parsers/python_parser.py` — Python symbol extraction
- `src/parsers/symbol_index.py` — Symbol storage and lookup

## Lower Priority (10-20% coverage OK)

- Support utilities: `import_resolver.py`, `projects.py`
- Config: `config.py`
- Services: `services.py` (integration, tested via tools)
- Performance helpers: `optimizer.py`

## Why This Works

1. **Focused effort** — High coverage where it matters, not everywhere
2. **Practical** — Users interact with MCP tools, parsers, and graph queries
3. **Scalable** — New code defaults to testing critical paths first
4. **Honest metrics** — Report coverage of "critical" vs "total" separately

## Target Metrics

- **Critical modules:** 75-85% coverage
- **Overall coverage:** 30-40% (natural given supporting code)
- **Test quality:** 100% of edge cases in user-facing code

## Next Steps

1. Add tests for critical modules in order:
   - neo4j_client (database reliability)
   - database_tools (user-facing graph commands)
   - graph_builder (core functionality)
   - contract_tools (breaking change detection)
   
2. Run: `pytest tests/ --cov=src/graph --cov=src/mcp_server/tools --cov-report=term`
