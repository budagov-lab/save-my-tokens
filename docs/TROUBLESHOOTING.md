# Troubleshooting Guide - Save My Tokens

## Setup Issues

### Python/venv

**Issue**: `ModuleNotFoundError: No module named 'tree_sitter'`

**Fix**:
```bash
# Reinstall dependencies
python -m pip install -e ".[dev]"

# Or specific packages
python -m pip install tree-sitter neo4j fastapi pytest
```

**Issue**: `venv/Scripts/python: No such file or directory`

**Fix**: Recreate the venv
```bash
rm -rf venv
python -m venv venv
python -m pip install --upgrade pip
```

---

### Docker / Neo4j

**Issue**: `unable to get image 'neo4j:5.14-community': ... The system cannot find the file specified`

**Fix**: Docker daemon not running
```bash
# Windows: Open Docker Desktop app and wait for initialization
# Linux/Mac: systemctl start docker

# Then retry
docker-compose up -d
```

**Issue**: `Connection refused` when connecting to Neo4j

**Fix**: Neo4j container not running
```bash
# Check container status
docker-compose ps

# Check logs
docker-compose logs neo4j

# Restart if stuck
docker-compose restart neo4j

# Wait 10 seconds for startup
sleep 10
```

**Issue**: `neo4j.exceptions.AuthError: Invalid username or password`

**Fix**: Verify credentials in `.env`
```bash
# Should match docker-compose.yml
NEO4J_USER=neo4j
NEO4J_PASSWORD=password  # Change in both files
```

---

## Parser Issues

**Issue**: `IndexError: strings index out of range` when parsing TypeScript

**Fix**: TypeScript parser not installed
```bash
python -m pip install tree-sitter-typescript
```

**Issue**: Symbol extraction only finds 50% of functions

**Fix**: Check file extensions are recognized
```bash
# Python files must be .py
# TypeScript files must be .ts or .tsx
```

---

## Graph Issues

**Issue**: Queries running >500ms

**Fix**: Add Neo4j indexes
```cypher
CREATE INDEX idx_func_name FOR (f:Function) ON (f.name);
CREATE INDEX idx_file_path FOR (f:File) ON (f.path);
```

**Issue**: `Transaction times out` on large repos

**Fix**: Increase Neo4j timeout
```bash
# In docker-compose.yml, add:
environment:
  NEO4J_dbms_transaction_timeout=30s
```

---

## API Issues

**Issue**: `127.0.0.1:8000: Connection refused`

**Fix**: API server not running
```bash
# Start in debug mode
uvicorn src.api.server:app --reload --port 8000

# Or check if port is in use
lsof -i :8000  # (Linux/Mac)
netstat -ano | findstr :8000  # (Windows)
```

**Issue**: `Empty context returned` for valid symbol

**Fix**: Graph not built yet
```bash
# Initialize Neo4j
python scripts/setup_neo4j.py

# Or rebuild graph
python -m src.graph.build_graph --repo tests/fixtures/test_repos/requests
```

---

## Test Issues

**Issue**: `pytest: command not found`

**Fix**: pytest not installed
```bash
python -m pip install pytest pytest-cov
```

**Issue**: Tests pass locally but fail in CI

**Fix**: Commit `.env.example`, not `.env`
```bash
# .env should be in .gitignore
git rm --cached .env
echo ".env" >> .gitignore
```

---

## Performance Issues

**Issue**: Query takes >1 second

**Diagnosis**:
```bash
# Profile query
python -c "
from src.api.server import app
from fastapi.testclient import TestClient
import time

client = TestClient(app)
start = time.time()
response = client.get('/api/context/validate_conflicts?depth=1')
elapsed = time.time() - start
print(f'Latency: {elapsed*1000:.0f}ms')
print(f'Payload: {len(response.text)} bytes')
"
```

**Fix**:
- Check Neo4j indexes exist
- Reduce query depth
- Enable query logging in Neo4j

---

## Development Tips

### Debugging

```python
# Add to any module
import logging
logging.basicConfig(level=logging.DEBUG)

# Or use breakpoints
import pdb; pdb.set_trace()
```

### Inspecting Neo4j

```bash
# Connect to Neo4j browser
# Navigate to http://localhost:7474

# Or use cypher-shell
docker exec -it save-my-tokens-neo4j cypher-shell
> MATCH (n) RETURN count(n);
> MATCH (n:Function) RETURN n.name LIMIT 10;
```

### Testing a Single Repo

```python
from src.graph import GraphBuilder

# Parse requests repo
builder = GraphBuilder("bolt://localhost:7687")
builder.build("tests/fixtures/test_repos/requests")
```

---

## Getting Help

1. Check logs: `docker-compose logs -f neo4j`
2. Run tests: `pytest -vv tests/unit/`
3. Verify setup: `python -c "import tree_sitter; import neo4j; print('OK')"`
4. GitHub issues: Report with full error traceback
