# API Specification - Save My Tokens

## Base URL
```
http://localhost:8000/api
```

## Endpoints

### 1. Health Check
```
GET /health
```
**Response**: `{"status": "ok", "app": "save-my-tokens", "version": "0.1.0"}`

### 2. Graph Statistics
```
GET /api/stats
```
**Response**:
```json
{
  "nodes": 1500,
  "edges": 3200,
  "graph_size_mb": 12.4
}
```

### 3. Get Minimal Context
```
GET /api/context/{symbol_name}?depth=1&include_callers=true
```
**Query Parameters**:
- `depth` (int, default=1): How many levels of dependencies to include
- `include_callers` (bool, default=false): Include reverse dependencies (functions that call this symbol)

**Response**:
```json
{
  "symbol": "validate_conflicts",
  "type": "function",
  "file": "src/api/endpoints.py",
  "line": 42,
  "docstring": "Validate task conflicts...",
  "dependencies": [
    {
      "name": "get_call_graph",
      "type": "function",
      "relationship": "CALLS"
    }
  ],
  "callers": [
    {
      "name": "POST /api/validate-conflicts",
      "type": "endpoint",
      "relationship": "CALLED_BY"
    }
  ],
  "token_count": 800
}
```

### 4. Get Dependency Subgraph
```
GET /api/subgraph/{symbol_name}?depth=2
```
**Query Parameters**:
- `depth` (int, default=1): BFS depth for subgraph traversal

**Response**:
```json
{
  "nodes": [
    {
      "id": "func:validate_conflicts",
      "label": "Function",
      "name": "validate_conflicts",
      "file": "src/api/endpoints.py"
    }
  ],
  "edges": [
    {
      "source": "func:validate_conflicts",
      "target": "func:get_call_graph",
      "type": "CALLS"
    }
  ],
  "token_count": 2100
}
```

### 5. Semantic Search
```
GET /api/search?query=password+validation&top_k=5
```
**Query Parameters**:
- `query` (string, required): Search query (natural language or code snippet)
- `top_k` (int, default=5): Number of results to return

**Response**:
```json
{
  "results": [
    {
      "rank": 1,
      "name": "validate_password",
      "type": "function",
      "file": "src/utils/auth.py",
      "similarity_score": 0.92,
      "docstring": "Validate password meets security requirements..."
    }
  ]
}
```

### 6. Detect Conflicts
```
POST /api/validate-conflicts
```
**Request Body**:
```json
{
  "tasks": [
    {
      "id": "task-1",
      "symbols": ["validate_conflicts", "get_call_graph"]
    },
    {
      "id": "task-2",
      "symbols": ["update_graph", "create_index"]
    }
  ]
}
```

**Response**:
```json
{
  "conflicts": [
    {
      "task_a": "task-1",
      "task_b": "task-2",
      "shared_dependencies": ["create_index"],
      "can_parallelize": false,
      "reason": "task-2 modifies create_index, which task-1 depends on"
    }
  ],
  "safe_groups": [
    ["task-1"],
    ["task-2"]
  ]
}
```

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (missing params, invalid format) |
| 404 | Symbol not found |
| 500 | Server error |

## Performance Targets

| Endpoint | Latency (p99) | Payload Size |
|----------|---------------|--------------|
| /health | <50ms | <1KB |
| /api/context | <500ms | <50KB |
| /api/subgraph | <500ms | <100KB |
| /api/search | <500ms | <50KB |
| /api/validate-conflicts | <1s | <200KB |

## Rate Limiting

None for Phase 1. Future: 100 req/sec per IP.

## Authentication

None for Phase 1. Future: Bearer token or API key.
