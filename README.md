# Save My Tokens (SMT)

Intelligent code context for Claude via CLI — instead of reading entire files.

## The Problem

Claude reads entire files to understand one function. It doesn't know who calls it or what breaks if you change it.

## The Solution

SMT builds a semantic graph of your codebase and exposes it through a `smt` CLI. Claude queries the graph via Bash instead of reading files.

```bash
smt context GraphBuilder          # definition + deps + callers
smt search "embedding logic"      # semantic search
smt callers build_graph           # who calls this
smt diff HEAD~1..HEAD             # sync after commit
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/your-org/save-my-tokens
cd save-my-tokens
pip install -e .
```

### 2. Start Neo4j

```bash
smt docker up
```

### 3. Build the graph

```bash
smt build
```

### 4. Query

```bash
smt status
smt search "your query"
smt context MyFunction
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `smt build` | Build graph from `src/` |
| `smt build --check` | Show graph stats |
| `smt build --clear` | Wipe and rebuild |
| `smt context <symbol>` | Symbol definition + deps + callers |
| `smt context <symbol> --depth 2` | Deeper dependency tree |
| `smt callers <symbol>` | Who calls this symbol |
| `smt search <query>` | Semantic search |
| `smt diff [range]` | Sync graph after commits (default: `HEAD~1..HEAD`) |
| `smt docker up/down/status` | Manage Neo4j container |
| `smt status` | Graph health check |
| `smt setup [--dir <path>]` | Configure a project |

---

## Architecture

```
Source Code → Parse (Tree-sitter) → Graph (Neo4j) → CLI → Claude (Bash)
                                         ↕
                               Embeddings (FAISS + SentenceTransformers)
```

**Supported languages:** Python, TypeScript

---

## Requirements

- Python 3.10+
- Docker (for Neo4j)

---

## Testing

```bash
pytest tests/ -v
```

## License

MIT
