# Git Integration — End-to-End Test Plan

**Status**: Ready to Execute  
**Goal**: Verify complete git-aware incremental graph sync workflow

## Test Environment

- **Test Repo**: `/test_repos/vue/` (Vue.js project with git)
- **SMT Dir**: `/save-my-tokens/`
- **Neo4j**: Running in Docker

## Test Sequence

### Phase 1: Setup & Hook Installation

**Goal**: Verify that `smt setup` creates hook and is ready for auto-sync

```bash
# 1.1 Initialize SMT in test repo
cd /path/to/test_repos/vue
smt setup --dir .

# Expected Output:
# ✓ .claude/.smt_config created
# ✓ .claude/settings.json created
# ✓ .claude/TOOLS.md created
# ✓ .git/hooks/post-commit installed
```

**Verification**:
- [ ] `.claude/.smt_config` exists with project_dir and project_name
- [ ] `.claude/settings.json` exists with SMT permissions
- [ ] `.git/hooks/post-commit` exists and is executable
- [ ] Hook file contains "# SMT: Auto-sync graph on commit" marker
- [ ] Hook command is: `smt diff HEAD~1..HEAD >/dev/null 2>&1 &`

### Phase 2: Build Initial Graph

**Goal**: Create baseline graph before testing incremental sync

```bash
# 2.1 Build full graph
smt build

# Expected: Graph indexed from src/
```

**Verification**:
- [ ] `smt status` shows node/edge counts > 0
- [ ] `smt status --check` shows "Graph health: HEALTHY"
- [ ] No errors in build output

### Phase 3: Commit-Based Incremental Update (Auto)

**Goal**: Verify that post-commit hook auto-triggers graph sync

```bash
# 3.1 Make a code change
cd /path/to/test_repos/vue/src
echo "// Test change" >> App.vue
# OR modify an existing Vue component slightly

# 3.2 Commit the change
git add .
git commit -m "test: Add test comment to verify hook"

# Expected: Hook fires automatically
# - Background process: smt diff HEAD~1..HEAD
# - Graph updates incrementally
# - Commit node created with MODIFIED_BY edges

# 3.3 Wait for hook to complete (2-3 seconds)
sleep 3

# 3.4 Query Neo4j to verify update
smt status --check
```

**Verification**:
- [ ] No error messages printed by hook
- [ ] `smt status` edge count increased
- [ ] Neo4j contains Commit node with recent timestamp
- [ ] Query: `MATCH (c:Commit) WHERE c.short_hash LIKE "XXXXX" RETURN c.message` returns commit message
- [ ] `MODIFIED_BY` edges exist for changed symbols

### Phase 4: Manual Sync Command

**Goal**: Verify `smt sync` works as manual fallback

```bash
# 4.1 Make another change (not committed yet)
echo "// Another test" >> src/another_file.vue
git add .
git commit -m "test: Second commit to test manual sync"

# 4.2 Run manual sync
smt sync

# OR with range
smt sync HEAD~2..HEAD

# Expected:
# ✓ Graph synced successfully
```

**Verification**:
- [ ] Manual sync completes without errors
- [ ] New Commit node appears in Neo4j
- [ ] MODIFIED_BY edges created for changed symbols

### Phase 5: Verify Graph Consistency

**Goal**: Ensure Neo4j graph is clean and consistent

```bash
# 5.1 Run consistency check
python3 -c "
from src.graph.neo4j_client import Neo4jClient
from src.config import settings

client = Neo4jClient()
stats = client.get_stats()
print(f'Nodes: {stats[\"node_count\"]}')
print(f'Edges: {stats[\"edge_count\"]}')
client.close()
"

# Expected:
# Nodes: > 0
# Edges: > 0
```

**Verification**:
- [ ] Node count reasonable (100+)
- [ ] Edge count > node count (most symbols have deps)

### Phase 6: Query Changed Symbols

**Goal**: Verify MODIFIED_BY edges link correctly

```bash
# 6.1 Query for symbols modified in recent commits
python3 <<'PYEOF'
from src.graph.neo4j_client import Neo4jClient
from src.config import settings

client = Neo4jClient()
# Query modified symbols
result = client.neo4j.run("""
    MATCH (s)-[:MODIFIED_BY]->(c:Commit)
    RETURN s.name, s.type, c.short_hash, c.message
    LIMIT 10
""")

for record in result:
    print(f"  {record[1]}: {record[0]} | {record[2]} | {record[3]}")

client.close()
PYEOF

# Expected:
# Output shows symbols linked to recent commits
```

**Verification**:
- [ ] MODIFIED_BY edges exist
- [ ] Symbols in MODIFIED_BY edges match files changed in commits
- [ ] Commit hashes are recent

### Phase 7: Embeddings Update

**Goal**: Verify embeddings regenerated for changed symbols

```bash
# 7.1 Check embedding cache
ls -la .claude/.embeddings/

# Expected:
# embeddings_cache.json updated recently
# faiss_index updated recently
```

**Verification**:
- [ ] `.claude/.embeddings/embeddings_cache.json` exists
- [ ] Recent modification time (after last sync)
- [ ] Semantic search works: `smt search "api endpoint"`

### Phase 8: Hook Uninstall

**Goal**: Verify hook removal works cleanly

```bash
# 8.1 Uninstall hook
smt hooks uninstall

# Expected:
# ✓ Removed SMT hook from .git/hooks/post-commit
```

**Verification**:
- [ ] Hook file deleted or cleaned
- [ ] SMT marker removed
- [ ] No SMT hook in `.git/hooks/post-commit`

```bash
# 8.2 Verify hook is gone
cat .git/hooks/post-commit | grep "SMT"

# Expected: (no output)
```

### Phase 9: Reinstall Hook

**Goal**: Verify hook can be reinstalled

```bash
# 9.1 Reinstall hook
smt hooks install

# Expected:
# ✓ .git/hooks/post-commit [OK] — Graph will sync after each commit
```

**Verification**:
- [ ] Hook reinstalled successfully
- [ ] SMT marker present
- [ ] Hook executable

## Expected Workflow Output

```
$ smt setup --dir .
Configuring SMT for: /path/to/vue
  .claude/.smt_config    [OK]
  .claude/settings.json  [OK]
  .claude/TOOLS.md       [OK]
  .git/hooks/post-commit [OK] — Graph will sync after each commit

Next steps:
  smt docker up          # start Neo4j (first time only)
  smt build              # index your codebase
  smt status             # verify graph is ready

$ git commit -m "test: change"
[main abc1234] test: change
# post-commit hook fires silently in background

$ smt sync HEAD~1..HEAD
Git Sync ████████░ 95% | Rebuilt FAISS index for 3 symbols
✓ Graph synced successfully

$ smt status --check
Graph Status:
  Database: neo4j (default)
  Nodes: 542, Edges: 1,248
  Commits: 5
  Health: HEALTHY ✓
```

## Success Criteria

- [ ] All 9 phases complete without errors
- [ ] Graph maintains consistency through multiple commits
- [ ] Hook auto-triggers without user intervention
- [ ] Manual sync works as fallback
- [ ] Embeddings updated for changed symbols
- [ ] No orphaned nodes or edges
- [ ] All commands return 0 on success, non-zero on error

## Cleanup (After Testing)

```bash
# Return to SMT directory
cd /path/to/save-my-tokens

# Clear test graph
smt docker down
docker volume rm save-my-tokens_neo4j_data  # Remove volume if needed
smt docker up                               # Fresh start

# Remove test repo changes (optional)
cd /path/to/test_repos/vue
git reset --hard HEAD  # Discard test commits
```

---

**Ready to execute**: All code complete, ready for user to run tests.
