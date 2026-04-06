# Git Integration Status

**Last Updated**: 2026-04-06  
**Progress**: 50% Complete (Steps 1-3 of 7)

## Overview

Implementing git-aware incremental graph updates. After each commit, SMT will automatically:
1. Parse changed files
2. Detect symbol additions/deletions/modifications
3. Update Neo4j graph incrementally
4. Create Commit node with MODIFIED_BY edges
5. Update embeddings for changed symbols only

## Completed ✅

### Step 1: Schema Extensions
- Added `COMMIT` node type to `NodeType` enum
- Added `MODIFIED_BY` edge type to `EdgeType` enum
- Created `CommitNode` dataclass with metadata fields
- File: `src/graph/node_types.py`

### Step 2: Symbol Index Deletion
- Implemented `SymbolIndex.remove()` method
- Removes symbol from all 4 internal indices
- Fixed `_remove_symbol()` in updater to actually call remove
- File: `src/parsers/symbol_index.py`

### Step 3: Neo4j Commit Support
- Added `begin_transaction()` method
- Added `create_commit_node()` method
- Added `create_modified_by_edges()` method
- Added commit index to database
- File: `src/graph/neo4j_client.py`

## In Progress 🔄

### Step 4: Incremental Update Pipeline
- Implement `update_from_git(commit_range, repo_path)` method
- Add helper methods:
  - `_run_git()` — subprocess wrapper for git commands
  - `_get_commit_metadata()` — extract commit info
  - `_parse_file()` — re-parse changed files
  - `_compute_delta()` — compare before/after symbols
  - `_update_embeddings_for_changed()` — incremental embedding updates
- File: `src/incremental/updater.py`
- Est. Time: 20-30 minutes

## Pending ⏳

### Step 5: CLI Enhancements
- Fix `cmd_diff()` constructor
- Add `cmd_setup_hooks()` for post-commit hook
- Add CLI subcommands: `smt sync`, `smt hooks install/uninstall`
- File: `src/smt_cli.py`
- Est. Time: 15 minutes

### Step 6: Hook Installation
- Auto-install `.git/hooks/post-commit` during setup
- Idempotent (no duplicates if already present)
- Preserve existing hook content
- Est. Time: 10 minutes

### Step 7: End-to-End Testing
- Verify hook creation
- Test commit → graph sync
- Verify MODIFIED_BY edges
- Test manual `smt sync`
- Est. Time: 15 minutes

## User Workflow (When Complete)

```bash
# One-time setup
smt setup --dir /path/to/project
# → Builds initial graph + installs post-commit hook

# After each commit (automatic)
git commit -m "feat: add feature"
# → post-commit hook fires
# → SMT detects changes and updates graph incrementally
# → Commit node created with MODIFIED_BY edges

# Manual sync
smt sync [--range HEAD~5..HEAD]

# Query history
MATCH (f:Function)-[:MODIFIED_BY]->(c:Commit)
RETURN f.name, c.message, c.timestamp
ORDER BY c.timestamp DESC
```

## Technical Details

**Hook Command**: `smt diff HEAD~1..HEAD >/dev/null 2>&1 &`

**Key Files Modified**:
- `src/graph/node_types.py` — Schema
- `src/parsers/symbol_index.py` — Deletion support
- `src/graph/neo4j_client.py` — Commit operations
- `src/incremental/updater.py` — Main pipeline (IN PROGRESS)
- `src/smt_cli.py` — CLI integration (PENDING)

**Design Constraints**:
- Local git only (no GitHub API)
- Incremental embeddings (only changed symbols)
- Rich progress bars for UX
- All-or-nothing transaction semantics
