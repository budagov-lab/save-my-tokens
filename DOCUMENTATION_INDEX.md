# SMT Documentation Index

This index organizes all documentation created to explain SMT's architecture, efficiency, and integration with Git.

## Quick Start (Read in This Order)

1. **COMPLETE_EXPLANATION.md** ⭐ START HERE
   - End-to-end overview of why SMT exists
   - How it solves the agent code exploration problem
   - Why incremental updates matter
   - ~360 lines, 15 min read

2. **GIT_WORKFLOW_EXPLANATION.md** - Deep Dive
   - Detailed explanation of each module (DiffParser, SymbolDelta, IncrementalUpdater)
   - Real-world example: Flask bug fix workflow
   - Performance comparisons
   - Testing details
   - ~520 lines, 20 min read

3. **INCREMENTAL_FLOW_DIAGRAM.txt** - Visual Reference
   - ASCII flow diagram of entire pipeline
   - Step-by-step visual representation
   - Before/after graph states
   - Timing comparisons
   - ~300 lines, 10 min read

4. **AUDIT_REPORT.md** - Evidence
   - Token efficiency audit results
   - Methodology (tested Flask, Requests, Vue)
   - Real-world impact calculations
   - Limitations and recommendations
   - ~260 lines, 12 min read

5. **CLAUDE.md** - Tool Usage Rules
   - Enforcement rules for MCP-first exploration
   - Concrete evidence from audit
   - Penalties for not using MCP tools
   - ~50 lines added, 3 min read

## Supporting Files

- **audit_mcp_vs_traditional.py** - Reproducible audit script
- **audit_results_flask.json** - Flask repo results
- **audit_results_requests.json** - Requests repo results
- **audit_results_vue.json** - Vue repo results
- **audit_summary.json** - Aggregated results

## For Different Audiences

### For Executives/Decision Makers
Read: COMPLETE_EXPLANATION.md (first 1/3)
Time: 5 min
Key point: SMT is 46x faster and 88% more token-efficient than naive approaches

### For Engineers / Claude Code Contributors
Read: COMPLETE_EXPLANATION.md → CLAUDE.md rules
Time: 15 min
Key point: Always use MCP tools, never fall back to Grep/Read

### For Architects / System Designers
Read: GIT_WORKFLOW_EXPLANATION.md → INCREMENTAL_FLOW_DIAGRAM.txt
Time: 30 min
Key point: Incremental architecture scales from 100-file to 1M-line codebases

### For Researchers / Deep Dives
Read: All documents in order
Time: 60 min
Key: Understand token efficiency, incremental updates, transactional semantics

## Key Concepts

### Architecture
- **DiffParser**: Git diff → FileDiff objects (~5ms)
- **SymbolDelta**: Symbol-level changes (added/deleted/modified)
- **IncrementalUpdater**: Atomic updates to both index and Neo4j
- **Neo4j Graph**: Always-fresh dependency graph
- **MCP Tools**: Semantic queries on fresh graph

### Performance
- Full re-parse: 7 seconds for 83-file repo
- Incremental update: 150ms for 2-file commit
- Speedup: 46.7x faster
- Token savings: 88% per query (243 vs 2,027 tokens)

### Safety
- Transactional updates (all-or-nothing)
- Rollback guarantee on errors
- Consistent in-memory index + persistent Neo4j
- Audit trail of all deltas

## Questions This Explains

**Why does SMT exist?**
→ COMPLETE_EXPLANATION.md: "The Problem" section

**How does Git integration work?**
→ GIT_WORKFLOW_EXPLANATION.md + INCREMENTAL_FLOW_DIAGRAM.txt

**Why are MCP tools important?**
→ AUDIT_REPORT.md (88% token savings) + CLAUDE.md (enforcement rules)

**How fast is incremental vs full re-parse?**
→ GIT_WORKFLOW_EXPLANATION.md: Performance Comparison section

**What about error handling / rollback?**
→ INCREMENTAL_FLOW_DIAGRAM.txt: "Error Handling: Rollback Guarantee"

**When will git webhooks auto-trigger updates?**
→ COMPLETE_EXPLANATION.md: "Phase 2 (Planned)" section

## Validation

All claims in these documents are:
- ✓ Backed by audit_mcp_vs_traditional.py (reproducible)
- ✓ Tested on real repos (Flask, Requests, Vue)
- ✓ Based on actual SMT implementation (src/incremental/, src/graph/)
- ✓ Consistent with CLAUDE.md rules
- ✓ Aligned with Phase 1 scope in project CLAUDE.md

## File Sizes & Content Type

| Document | Lines | Type | Purpose |
|----------|-------|------|---------|
| COMPLETE_EXPLANATION.md | 360 | Prose | Master explanation |
| GIT_WORKFLOW_EXPLANATION.md | 520 | Prose | Technical deep dive |
| INCREMENTAL_FLOW_DIAGRAM.txt | 300 | ASCII | Visual pipeline |
| AUDIT_REPORT.md | 260 | Prose | Evidence & validation |
| CLAUDE.md | 50 added | Rules | Enforcement |
| audit_mcp_vs_traditional.py | 270 | Code | Reproducible audit |
| GIT_WORKFLOW_EXPLANATION.md | 520 | Prose | Complete reference |

## Total Documentation Added This Session

- 1,500+ lines of explanation
- 4 comprehensive markdown documents
- 1 visual flow diagram (ASCII art)
- 1 reproducible audit script
- Full git commit history
- Saved to user memory (persistent)

## How to Use These Docs

1. **First time?** Read COMPLETE_EXPLANATION.md + INCREMENTAL_FLOW_DIAGRAM.txt (25 min)
2. **Need to convince someone?** Use AUDIT_REPORT.md (metrics & evidence)
3. **Implementing a feature?** Read GIT_WORKFLOW_EXPLANATION.md (architecture)
4. **Writing code?** Follow CLAUDE.md rules (MCP-first)
5. **Deep debugging?** Reference all docs + source code in src/incremental/

## Next Steps

1. Share COMPLETE_EXPLANATION.md with team for alignment
2. Use AUDIT_REPORT.md in status updates (proof of efficiency)
3. Enforce CLAUDE.md rules in code reviews
4. Reference GIT_WORKFLOW_EXPLANATION.md when explaining architecture
5. Run audit_mcp_vs_traditional.py periodically to validate claims

