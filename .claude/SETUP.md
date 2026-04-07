# SMT Setup Instructions

This repository has **save-my-tokens (SMT)** installed for intelligent code context retrieval.

## Quick Start

```bash
# 1. Verify setup
smt status

# 2. Query code structure
smt definition <symbol>      # What is this?
smt context <symbol>         # What do I need to understand this?
smt impact <symbol>          # What breaks if I change this?
smt search "<query>"         # Semantic search
```

## What It Does

- **Fast queries** — Sub-20ms response time even on large codebases
- **Token efficient** — 60-90% reduction vs reading raw files
- **Understands structure** — Calls, definitions, dependencies, relationships

## Examples

```bash
# Find a function definition
smt definition main

# Get context for working on a module
smt context GraphBuilder --depth 2

# Analyze impact of changes
smt impact Neo4jClient --depth 3

# Search semantically
smt search "cycle detection"
```

## Documentation

- Run `smt --help` for all commands
- Run `smt <command> --help` for command-specific options
