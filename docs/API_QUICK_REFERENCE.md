# Graph API - Quick Reference

**Base URL:** `http://localhost:8000`

---

## Health & Stats

### GET /health
Health check endpoint.

```bash
curl http://localhost:8000/health
```

**Response (200):**
```json
{
  "status": "ok",
  "app": "Graph API",
  "version": "0.1.0"
}
```

### GET /api/stats
Graph statistics.

```bash
curl http://localhost:8000/api/stats
```

**Response (200):**
```json
{
  "node_count": 1542,
  "edge_count": 3205
}
```

---

## Query Endpoints

### GET /api/context/{symbol_name}
Get minimal context for a symbol.

**Parameters:**
- `symbol_name` (path): Symbol name to retrieve context for
- `depth` (query, default=1): Maximum dependency depth
- `include_callers` (query, default=false): Include reverse dependencies

**Example:**
```bash
curl "http://localhost:8000/api/context/process_data?depth=2&include_callers=true"
```

**Response (200):**
```json
{
  "symbol": {
    "name": "process_data",
    "type": "function",
    "file": "src/processor.py",
    "line": 42,
    "column": 0,
    "node_id": "Function:src/processor.py:42:process_data",
    "docstring": "Process incoming data"
  },
  "dependencies": [
    {
      "name": "validate_input",
      "type": "function",
      "node_id": "Function:src/validator.py:10:validate_input"
    }
  ],
  "callers": [
    {
      "name": "main",
      "type": "function",
      "node_id": "Function:src/main.py:1:main"
    }
  ],
  "token_estimate": 287
}
```

**Response (404):**
```json
{
  "detail": "Symbol 'unknown_func' not found"
}
```

---

### GET /api/subgraph/{symbol_name}
Get dependency subgraph for a symbol.

**Parameters:**
- `symbol_name` (path): Symbol to get subgraph for
- `depth` (query, default=2): Maximum traversal depth

**Example:**
```bash
curl "http://localhost:8000/api/subgraph/Calculator?depth=3"
```

**Response (200):**
```json
{
  "root_symbol": "Calculator",
  "nodes": [
    {
      "node_id": "Class:src/calc.py:20:Calculator",
      "name": "Calculator",
      "type": "class",
      "file": "src/calc.py",
      "line": 20
    },
    {
      "node_id": "Function:src/calc.py:25:add",
      "name": "add",
      "type": "function",
      "file": "src/calc.py",
      "line": 25
    }
  ],
  "edges": [
    {
      "source": "Class:src/calc.py:20:Calculator",
      "target": "Function:src/calc.py:25:add",
      "type": "DEFINES"
    }
  ],
  "depth": 3,
  "token_estimate": 512
}
```

---

### GET /api/search
Search for symbols.

**Parameters:**
- `query` (query): Search query (name or natural language)
- `top_k` (query, default=5): Number of results to return

**Examples:**
```bash
# Search by name
curl "http://localhost:8000/api/search?query=password&top_k=5"

# Search by code snippet (future with embeddings)
curl "http://localhost:8000/api/search?query=validate+user+input&top_k=3"
```

**Response (200):**
```json
{
  "query": "password",
  "results": [
    {
      "symbol_name": "validate_password",
      "symbol_type": "function",
      "file": "src/security.py",
      "line": 15,
      "node_id": "Function:src/security.py:15:validate_password",
      "similarity_score": 0.95
    },
    {
      "symbol_name": "hash_password",
      "symbol_type": "function",
      "file": "src/security.py",
      "line": 25,
      "node_id": "Function:src/security.py:25:hash_password",
      "similarity_score": 0.85
    }
  ],
  "top_k": 5
}
```

---

### POST /api/validate-conflicts
Validate conflicts between parallel tasks.

**Request Body:**
```json
{
  "tasks": [
    {
      "id": "task_1",
      "target_symbols": ["process_data", "validate_input"]
    },
    {
      "id": "task_2",
      "target_symbols": ["validate_input", "format_output"]
    }
  ]
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/validate-conflicts \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"id": "task_1", "target_symbols": ["func_a", "func_b"]},
      {"id": "task_2", "target_symbols": ["func_c"]}
    ]
  }'
```

**Response (200) - No Conflicts:**
```json
{
  "tasks": ["task_1", "task_2"],
  "conflicts": [],
  "parallel_feasible": true
}
```

**Response (200) - With Conflicts:**
```json
{
  "tasks": ["task_1", "task_2"],
  "conflicts": [
    {
      "task_a": "task_1",
      "task_b": "task_2",
      "shared_symbols": ["validate_input"]
    }
  ],
  "parallel_feasible": false
}
```

---

## API Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 404 | Symbol not found |
| 422 | Validation error (invalid request) |
| 500 | Server error |

---

## Token Estimation

All responses include `token_estimate` field (approximate count of tokens needed to represent the response). This helps agents decide if the context fits in their token budget.

**Formula:** estimated_chars / 4 ≈ tokens (rough approximation)

---

## Running the Server

```bash
# Start development server
python -m src.api.server

# With custom settings
API_HOST=0.0.0.0 API_PORT=8000 python -m src.api.server

# With Docker
docker-compose up api
```

API will be available at `http://localhost:8000`  
Swagger docs at `http://localhost:8000/docs`  
OpenAPI spec at `http://localhost:8000/openapi.json`

---

## Error Handling

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Example: Symbol not found (404)
```json
{
  "detail": "Symbol 'unknown_func' not found"
}
```

---

## Performance Targets

| Endpoint | Target Latency | Target Payload |
|----------|-----------------|-----------------|
| /health | <50ms | <1KB |
| /api/stats | <100ms | <5KB |
| /api/context | <500ms | <50KB |
| /api/subgraph | <500ms | <50KB |
| /api/search | <500ms | <50KB |
| /api/validate-conflicts | <500ms | <50KB |

---

## Next Steps (Phase 2)

- **Incremental Updates:** Git diff integration for partial re-parsing
- **Contract Validation:** Detect breaking changes and API violations
- **Multi-Language Support:** Go, Rust, Java parsers
- **Agent Scheduling:** Automated task dependency resolution and execution

