# Quick Start (5 minutes)

Get SMT running and make your first query.

## 1. Install (1 minute)

```bash
git clone https://github.com/budagov-lab/save-my-tokens
cd save-my-tokens
pip install -e .
```

## 2. Start Neo4j (2 minutes)

```bash
smt docker up
# Wait for startup... (should take ~10 seconds)
```

To verify Neo4j is running:
```bash
curl http://localhost:7474
# Should return: Neo4j browser HTML
```

## 3. Build the graph (1-2 minutes)

```bash
smt build
# Shows progress: Parsing files -> Creating nodes -> Creating edges -> Persisting
# Should complete in 20-60 seconds depending on codebase size
```

Check it worked:
```bash
smt status
# Should show: Graph: X nodes, Y edges
```

## 4. Make your first query (30 seconds)

Pick a symbol from your codebase. For SMT itself:

```bash
# Mode 1: What is this?
smt definition GraphBuilder

# Mode 2: What do I need to work on this?
smt context GraphBuilder --depth 2

# Mode 3: What breaks if I change this?
smt impact Neo4jClient --depth 3
```

---

## Troubleshooting

### Neo4j won't start

```bash
# Check Docker is running
docker ps

# View Neo4j logs
docker-compose logs neo4j

# Or start manually with more detail
docker-compose up neo4j  # (don't use -d)
```

### Graph build fails

```bash
# Clear and rebuild
smt build --clear

# Check for parse errors
smt build 2>&1 | grep -i error
```

### Symbol not found

Make sure:
- You built the graph (`smt build`)
- The symbol actually exists in `src/`
- No typos in the symbol name (case-sensitive)

---

## Next Steps

- Read [README.md](README.md) for full documentation
- Try `smt search` for semantic search
- Use `smt diff` to sync after code changes
- Check [FINAL_SUMMARY.md](FINAL_SUMMARY.md) for architecture details

---

## Common Commands

```bash
# Query modes
smt definition SYMBOL           # Fast lookup
smt context SYMBOL --depth 2    # Working context
smt impact SYMBOL --depth 3     # Impact analysis
smt context SYMBOL --compress   # Reduce tokens

# Management
smt build                       # Rebuild graph
smt diff HEAD~1..HEAD          # Sync after commits
smt status                      # Check health

# Docker
smt docker up                   # Start Neo4j
smt docker down                 # Stop Neo4j
smt docker status               # Check status
```

Done! 🎉
