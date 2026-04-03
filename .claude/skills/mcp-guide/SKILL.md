---
name: mcp-guide
description: Learn how to use 20 MCP tools efficiently instead of reading/grepping large files
---

# MCP Tools Guide

You have access to 20 MCP tools organized by category:

## Code Understanding (4 tools)
- `get_context(symbol)` - Understand a function/class + callers + dependencies
- `get_subgraph(symbol)` - Full dependency tree up to N hops
- `semantic_search(query)` - Find code by meaning (not just names)
- `validate_conflicts(tasks)` - Check if changes can run in parallel

## Graph Management (8+ tools)
- `graph_stats()` - Is graph fresh? Get node/edge counts
- `graph_rebuild()` - Full reconstruction from source
- `graph_diff_rebuild()` - Fast incremental update from git
- `graph_validate()` - Check graph integrity and consistency

## Contracts & Breaking Changes (2 tools)
- `extract_contract(code)` - Parse function signatures and types
- `compare_contracts(old, new)` - Detect breaking changes before refactoring

## Git & Updates (2 tools)
- `parse_diff()` - Analyze git diff output
- `apply_diff()` - Sync graph with git commits

## Task Scheduling (2 tools)
- `schedule_tasks(tasks)` - Build execution plan with parallelization
- `execute_tasks(plan)` - Run tasks respecting dependencies

## Usage Principle

Don't read large files - use tools instead:
- "What does function X do?" -> Use get_context('X')
- "Find code that does X" -> Use semantic_search('X')
- "Is my change safe?" -> Use compare_contracts(old, new) + validate_conflicts(tasks)
- "Update after git commit" -> Use graph_diff_rebuild()

Always use these tools instead of Read() or Grep() for code understanding.
