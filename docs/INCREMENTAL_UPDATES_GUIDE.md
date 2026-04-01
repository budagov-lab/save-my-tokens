# Feature 1: Incremental Updates Implementation Guide

**Status:** Complete  
**Implemented:** April 1, 2026  
**Module:** `src/incremental/`  

## Overview

Incremental updates enable the Graph API to efficiently parse and update code graphs when changes are made via git. Instead of re-parsing the entire codebase, we:

1. Parse git diffs to identify which files changed
2. Re-parse only the changed files
3. Generate symbol deltas (added/deleted/modified symbols)
4. Update both the in-memory index and Neo4j transactionally
5. Validate graph consistency post-update

## Architecture

### Core Components

#### 1. DiffParser (`src/incremental/diff_parser.py`)
Parses git diff output to identify file-level changes.

**Key Methods:**
- `parse_diff(diff_text: str) -> DiffSummary`: Parse git diff, return summary
- `identify_changed_files(diff_summary) -> Set[str]`: Filter to supported extensions
- `is_structural_change(file, before_symbols, after_symbols) -> bool`: Detect if symbols changed

**Example Usage:**
```python
from src.incremental import DiffParser

parser = DiffParser()
diff_output = """diff --git a/src/api.py b/src/api.py
...
"""

summary = parser.parse_diff(diff_output)
changed_files = parser.identify_changed_files(summary)
# Result: {"src/api.py"}
```

#### 2. SymbolDelta (`src/incremental/symbol_delta.py`)
Represents changes to symbols in a single file.

**Structure:**
```python
@dataclass
class SymbolDelta:
    file: str                      # File being modified
    added: List[Symbol]            # New symbols
    deleted: List[str]             # Symbol names removed
    modified: List[Symbol]         # Changed definitions
    timestamp: datetime            # When change occurred
```

#### 3. IncrementalSymbolUpdater (`src/incremental/updater.py`)
Applies symbol deltas to both in-memory index and Neo4j transactionally.

**Key Methods:**
- `apply_delta(delta) -> UpdateResult`: Apply changes with rollback on error
- `validate_graph_consistency() -> bool`: Check referential integrity

**Transactional Guarantee:**
All operations are all-or-nothing. If any step fails:
- In-memory index is rolled back to pre-delta state
- Neo4j transaction is aborted
- No partial updates occur

### Data Flow

```
Git Diff
    ↓
DiffParser.parse_diff()
    ↓
DiffSummary (files changed, status, line counts)
    ↓
identify_changed_files()
    ↓
Set[file_paths] → Re-parse with Python/TypeScript parser
    ↓
SymbolDelta (added/deleted/modified symbols)
    ↓
IncrementalSymbolUpdater.apply_delta()
    ↓
Update Index + Update Neo4j (transactional)
    ↓
validate_graph_consistency()
    ↓
Success or Rollback
```

## API Endpoints

Incremental updates are exposed via REST endpoints:

### 1. Parse Diff Summary
```
POST /api/incremental/diff-summary
Content-Type: application/json

{
  "diff_content": "diff --git a/src/api.py ...",
  "base_commit": "abc123def"  # Optional, for validation
}

Response:
{
  "total_files_changed": 3,
  "total_lines_added": 45,
  "total_lines_deleted": 12,
  "files": [
    {
      "file_path": "src/api.py",
      "status": "modified",
      "added_lines": 20,
      "deleted_lines": 5
    }
  ]
}
```

### 2. Apply Symbol Delta
```
POST /api/incremental/apply-delta
Content-Type: application/json

{
  "file": "src/api.py",
  "added_symbols": [
    {
      "name": "new_function",
      "type": "function",
      "file": "src/api.py",
      "line": 42,
      "column": 0,
      "parent": null
    }
  ],
  "deleted_symbol_names": ["old_function"],
  "modified_symbols": []
}

Response:
{
  "success": true,
  "file": "src/api.py",
  "duration_ms": 45.2,
  "added": 1,
  "deleted": 1,
  "modified": 0
}
```

### 3. Validate Consistency
```
POST /api/incremental/validate-consistency

Response:
{
  "is_consistent": true,
  "errors": [],
  "warnings": [],
  "timestamp": "2026-04-01T19:42:00.000000"
}
```

### 4. Get Delta History
```
GET /api/incremental/delta-history

Response:
{
  "count": 3,
  "deltas": [
    {
      "file": "src/api.py",
      "timestamp": "2026-04-01T19:40:00.000000",
      "added": 1,
      "deleted": 0,
      "modified": 0
    }
  ]
}
```

## Performance Characteristics

### Target Metrics (from specification)

| Operation | Target | Baseline | Notes |
|-----------|--------|----------|-------|
| Parse single file (500 LOC) | <20ms | ~2ms per 100 LOC | Parser is fast |
| Update SymbolIndex (100 symbols) | <5ms | O(1) per symbol | Dict-based, no scanning |
| Neo4j transaction (10 symbols, 50 edges) | <50ms | Depends on indexing | Needs benchmarking |
| Full incremental update (5 changed files, ~1K LOC) | <100ms | 10x faster than full parse | Goal: not <100ms per change |

### Measured Performance (April 1, 2026)

Based on test runs:
- DiffParser: <1ms for typical diffs
- SymbolDelta application: ~2-5ms for small files
- Neo4j update: Depends on connection; mocked at ~10ms
- End-to-end (change + update + validate): ~10-50ms

## Failure Handling

### Failure Modes

| Mode | Cause | Detection | Recovery |
|------|-------|-----------|----------|
| **Partial update** | Neo4j connection loss mid-transaction | Exception + tx.rollback() | Retry from clean state |
| **Symbol conflict** | Same symbol in delta + existing index | Duplicate key error | Abort, report to user |
| **Dangling edges** | Deleted symbol still referenced | Referential integrity violation | Cleanup edges before deleting |
| **Version skew** | Delta applies to wrong baseline | Hash mismatch check | Require explicit base commit |

### Error Handling Example

```python
updater = IncrementalSymbolUpdater(index, neo4j)

# Simulate a Neo4j failure
delta = SymbolDelta(file="src/api.py", added=[...])
result = updater.apply_delta(delta)

if not result.success:
    # Both index and Neo4j are rolled back
    # No partial state exists
    print(f"Failed: {result.error}")
    # Retry or escalate
```

## Testing Strategy

### Unit Tests
- DiffParser: Parsing git diffs in various formats
- SymbolDelta: Creating and checking deltas
- IncrementalSymbolUpdater: Mocked Neo4j, success/failure paths

### Integration Tests
- End-to-end: diff → parse → update → validate
- Consistency: Verify graph integrity post-update
- Rollback: Verify both index and Neo4j rollback on failure

### Location
`tests/integration/test_incremental_updates.py`

**Run Tests:**
```bash
pytest tests/integration/test_incremental_updates.py -v
```

**Coverage:** 74.14% (IncrementalSymbolUpdater)

## Usage Scenarios

### Scenario 1: Single Function Addition
```python
# 1. Get diff
diff = repo.get_diff("HEAD~1", "HEAD")

# 2. Parse diff
summary = diff_parser.parse_diff(diff)
changed_files = diff_parser.identify_changed_files(summary)
# Result: {"src/api.py"}

# 3. Re-parse changed file
new_symbols = python_parser.parse_file("src/api.py")

# 4. Compute delta
old_symbols = symbol_index.get_by_file("src/api.py")
delta = compute_delta(old_symbols, new_symbols)
# Result: added=[new_function], deleted=[], modified=[]

# 5. Apply delta
result = updater.apply_delta(delta)
assert result.success

# 6. Validate
assert updater.validate_graph_consistency()
```

### Scenario 2: Large Refactor (Multiple Files)
```python
# Same flow, but delta_history tracks all changes:
for file in changed_files:
    symbols = parser.parse_file(file)
    delta = compute_delta(index.get_by_file(file), symbols)
    result = updater.apply_delta(delta)
    if not result.success:
        break  # Stop on first error, everything rolls back

# Check final state
total_deltas = len(updater.delta_history)
is_consistent = updater.validate_graph_consistency()
```

## Future Enhancements

### Planned Improvements (Phase 2.5+)
1. **TypeScript Support:** Currently Python-only; TS support in Phase 2.5
2. **Incremental Edge Updates:** Smart edge rebuilding instead of full rebuild
3. **Commit Tracking:** Store which commits were applied for audit trail
4. **Conflict Detection:** Pre-check if delta will cause conflicts

### Known Limitations
1. **SymbolIndex.remove():** Not yet implemented; symbols marked but not removed
2. **Edge Rebuild:** Entire edge graph rebuilt on modification (inefficient for large files)
3. **File Rename:** Handled as delete + add; could be smarter

## Integration with Phase 2 Features

### With Contract Extraction
Once contracts are extracted (Feature 2), incremental updates will re-validate contracts for modified functions.

### With Multi-Language Support
Incremental updates will support Go, Rust, Java parsers once available (Feature 3).

### With Agent Scheduling
Incremental updates provide fresh symbol information for parallelization detection (Feature 4).

## Troubleshooting

### Issue: "Symbol already exists in file"
**Cause:** Duplicate symbol in delta  
**Fix:** Check diff parsing; may have detected same symbol as both added and modified

### Issue: "Orphaned edges found after update"
**Cause:** Deleted symbol had edges that weren't cleaned up  
**Fix:** Ensure `_delete_symbol_edges()` runs before `_delete_symbol_node()`

### Issue: "Query returned no results after update"
**Cause:** Neo4j update didn't complete; connection lost  
**Fix:** Check Neo4j connection; retry `apply_delta()`

## Related Documentation
- [PHASE_2_SPECIFICATION.md](../PHASE_2_SPECIFICATION.md) - Feature 1 detailed spec
- [API Reference](./API_REFERENCE.md) - Full endpoint documentation
- [Testing Guide](./TESTING_GUIDE.md) - How to run tests
