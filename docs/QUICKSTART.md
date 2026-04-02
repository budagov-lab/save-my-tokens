# Save-My-Tokens (SMT) - Quick Start

## What is SMT?

A **semantic graph database** of your codebase that enables:
- Fast code context retrieval (800 tokens vs 5000+ with traditional file reading)
- Dependency analysis and impact detection
- Git history tracking
- 88% token savings compared to Grep+Read

## Getting Started

### 1. Ensure Neo4j is Running

```bash
# Using Docker
docker-compose up -d neo4j

# Or via Docker Desktop: Start the Neo4j container
```

### 2. Build the Graph (One-Time)

```bash
python build_graph.py
```

This creates:
- 653 nodes (code symbols)
- 776 edges (dependencies)
- 72 commits (git history)

Check status anytime:
```bash
python build_graph.py --check
```

### 3. Use the Graph in Code

**Option A: In Python scripts**
```python
from init_smt import ensure_graph_ready
from src.mcp_server.services import build_services

ensure_graph_ready()  # Build if needed
services = build_services()

# Query the graph
context = services.query_service.get_context('Neo4jClient', depth=1)
print(f"Found: {context['symbol']['name']}")
```

**Option B: Via CLI**
```bash
# Check what changed in last commit
python build_graph.py --check

# Rebuild after code changes
python build_graph.py
```

## Common Tasks

### Find all functions in a file
```python
from src.graph.neo4j_client import Neo4jClient

client = Neo4jClient()
with client.driver.session() as session:
    result = session.run("""
        MATCH (f:File {name: 'src/api/server.py'})-[d:DEFINES]->(m:Function)
        RETURN m.name
    """)
    functions = [record['m.name'] for record in result]
```

### Find what methods a class has
```python
with client.driver.session() as session:
    result = session.run("""
        MATCH (c:Class {name: 'QueryService'})-[d:DEFINES]->(m:Function)
        RETURN m.name
    """)
```

### Find recent commits
```python
with client.driver.session() as session:
    result = session.run("""
        MATCH (c:Commit)
        RETURN c.hash, c.message, c.author
        ORDER BY c.index DESC
        LIMIT 10
    """)
```

## Graph Statistics

- **Symbols**: 745 (functions, classes, modules)
- **Files**: 44 Python source files
- **Classes**: 53
- **Functions**: 244
- **Modules/Imports**: 240
- **Commits**: 72
- **Edges**: 776 (DEFINES, IMPORTS)

## Next Steps

1. **Rebuild after changes**: Run `python build_graph.py` after making code changes
2. **Query semantically**: Use `get_context()` to find what you need quickly
3. **Track changes**: Graph includes full git history automatically

## Troubleshooting

**Graph shows 0 nodes?**
```bash
python build_graph.py  # Rebuild
```

**Neo4j connection error?**
- Ensure Docker is running: `docker-compose up -d neo4j`
- Check Neo4j is accessible on localhost:7687

**Need to reset everything?**
```bash
python build_graph.py --clear  # Clear and rebuild
```

## Architecture

```
Code → Tree-sitter Parser → Symbol Index → Neo4j Graph
                                              ↓
                                        MCP Tools
                                              ↓
                                    Claude/Agents
```

The graph stores:
- **Nodes**: Files, Functions, Classes, Modules, Commits
- **Edges**: DEFINES (file→symbol), IMPORTS (file→import), etc.
- **Metadata**: Line numbers, docstrings, git info

See `README.md` for full project details.
