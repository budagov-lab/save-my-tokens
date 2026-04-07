# Query Optimization Report

## Benchmark Results (SMT graph: 6,194 nodes, 11,780 edges)

| Mode | Avg Time | Min | Max | Variance |
|---|---|---|---|---|
| definition | 37.7ms | 11.2ms | 296.1ms | 26x |
| impact | 42.6ms | 18.1ms | 244.6ms | 13x |
| context | 115.6ms | 17.3ms | 930.8ms | 54x |

## Findings

### 1. **Context Mode Bottleneck**
- **Issue:** 54x variance indicates connection overhead dominates first query
- **Cause:** New session per query instead of connection pooling
- **Impact:** 115ms avg is acceptable but variance is problematic

### 2. **High Variance Pattern**
```
First run:   ~300ms (connection setup)
Warm runs:   ~20ms  (cached connection)
Outliers:    ~900ms (bidirectional traversal on large subgraphs)
```

### 3. **Query Structure Inefficiencies**
- **get_bounded_subgraph** (Query 1): Uses OPTIONAL MATCH + collect inefficiently
- **get_impact_graph** (similar issue)
- **Problem:** COLLECT(DISTINCT node) doesn't return COUNT, forces full node list

## Optimization Opportunities

### Priority 1: Connection Pool Reuse
**Current:** Each CLI call creates new Neo4jClient + session
**Optimization:** Session pooling or keep-alive connections

**Expected gain:** Reduce variance from 54x to ~3x
**Code location:** `src/smt_cli.py` — reuse client across commands

### Priority 2: Cypher Query Optimization  
**Current:** `OPTIONAL MATCH path = (n)-[:CALLS*1..3]->(reached) WITH ... COLLECT(DISTINCT reached)`
**Issue:** Returns full node objects when we only need count/filtering

**Optimized:** Use path aggregation or apoc functions (if available)
**Expected gain:** 20-30% reduction on large traversals
**Code location:** `src/graph/neo4j_client.py` — rewrite Cypher

### Priority 3: Early Termination
**Current:** Traverses ALL paths within depth limit
**Optimization:** Stop after reaching threshold (e.g., first N callers)

**Expected gain:** 40-50% on deep impacts
**Code location:** `src/smt_cli.py` — add `--limit N` option

## Recommended Fixes

### Fix 1 (Immediate): Connection Pooling
- Create singleton Neo4jClient in CLI
- Reuse across all commands
- Reduces first-query penalty

### Fix 2 (Quick): Cypher Optimization
- Replace COLLECT + UNWIND with simpler path counting
- Use APOC if available (Neo4j 5.14 has it)
- Reduce node materialization

### Fix 3 (Polish): Limit Queries
- Add `--limit 50` to impact/context
- Useful for large codebases
- Prevent runaway traversals

## Token Cost Analysis

For agent use, measure context size (token count):

| Mode | Avg Nodes | Avg Edges | Est. Tokens |
|---|---|---|---|
| definition | 5-10 | 3-5 | 50-100 |
| impact | 20-30 | 15-25 | 200-300 |
| context | 15-25 | 20-30 | 200-300 |

**Token reduction vs reading files:**
- Raw file read: 500-1000 tokens per function
- SMT context: 50-300 tokens per query
- **Savings: 60-90%**

## Next Steps

1. Implement connection pooling (Fix 1)
2. Optimize Cypher queries (Fix 2)
3. Add depth limiting (Fix 3)
4. Remeasure performance
