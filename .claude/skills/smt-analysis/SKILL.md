---
name: smt-analysis
description: "Use when analyzing codebase structure, understanding symbol dependencies, assessing impact of code changes, or finding independent components that can be worked on in parallel. Dispatches specialized subagents: Scout (reads graph), Fabler (what-if analyst), PathFinder (isolation analyst)."
---

# SMT Analysis Harness

**Scout → Fabler/PathFinder → Synthesis**

This skill orchestrates a team of three specialized subagents to analyze code dependencies, predict change impact, and find independent components.

---

## Process

### Step 1: Always Dispatch Scout First

Scout is the read-only graph analyst. It runs `smt status`, `smt definition`, `smt context`, `smt impact`, and `smt search` to gather facts before any analysis.

**Decision**: Scout returns `DONE` + findings?
- **Yes** → proceed to Step 2
- **BLOCKED** (graph stale, Neo4j down, symbol not found) → escalate to user immediately
- **NEEDS_CONTEXT** → provide more info (e.g., "Which symbol did you mean?") and re-dispatch Scout

---

### Step 2: Route to Fabler and/or PathFinder

Based on the original user question:

| Question Type | Route |
|---|---|
| "What breaks if I change X?" | → Fabler only |
| "What parts can be worked on independently?" | → PathFinder only |
| "Give me the full impact analysis + isolation plan" | → Both (parallel) |

**Decision**: After both agents complete:
- Both return `DONE` → proceed to Step 3 (synthesis)
- Either returns `DONE_WITH_CONCERNS` → flag to user, still proceed
- Either returns `BLOCKED` → escalate immediately
- Either needs more context → provide and re-dispatch

---

### Step 3: Synthesize Results

Combine Scout, Fabler, and PathFinder reports into a cohesive answer:

1. **Scout insight**: "Here's what the code looks like"
2. **Fabler insight** (if present): "Here's what breaks"
3. **PathFinder insight** (if present): "Here's how to work in isolation"
4. **User action**: Give developer exact file:line locations + change order + impact summary

---

## Red Flags (Never Do)

- ❌ Dispatch Fabler before Scout returns DONE
- ❌ Skip `smt status` check (graph may be stale; agents may use outdated data)
- ❌ Use Scout output older than 5 minutes for Fabler/PathFinder input
- ❌ Dispatch both Fabler and PathFinder if Scout found the symbol doesn't exist
- ❌ Proceed with `BLOCKED` status; escalate immediately

---

## Model Selection

| Agent | Task Type | Recommended Model |
|---|---|---|
| Scout | Mechanical CLI execution | Fast (Haiku or Flash) |
| Fabler | Causal impact reasoning | Standard (Sonnet) |
| PathFinder | Graph traversal reasoning | Standard (Sonnet) |
| Orchestrator | Coordination + synthesis | Capable (Claude) |

---

## Status Codes

All subagents return one of these:

- **`DONE`** — Task completed successfully, report is final
- **`DONE_WITH_CONCERNS`** — Task completed but with caveats (e.g., "confidence is medium due to missing docstrings")
- **`BLOCKED`** — Cannot proceed, need human decision or external action (e.g., Neo4j down, stale graph that smt diff can't fix)
- **`NEEDS_CONTEXT`** — Missing information, please provide and re-dispatch

---

## When to Use Each Subagent

### Scout

**When**: You need to read or search the codebase graph
- "What is `GraphBuilder.build`?"
- "Show me who calls `validate_graph`"
- "Find functions related to cycle detection"
- "Is the graph fresh?"

**Scout runs**: `smt status`, `smt definition`, `smt context --depth 2`, `smt impact --depth 3`, `smt search`

**You don't call Scout for**: Causality ("why would this break?"), independence ("can we work separately?") — those are Fabler and PathFinder.

### Fabler

**When**: You need to predict consequences of a code change
- "What would break if I changed the signature of `CallAnalyzer._infer_edge_type`?"
- "Impact analysis: refactor `Neo4jClient` initialization"
- "What tests would fail if I remove this parameter?"

**Fabler receives**: Scout's full report + hypothetical change description
**Fabler returns**: Breaking callers + safe change order + atomicity assessment

**Fabler does NOT make changes**, just predicts.

### PathFinder

**When**: You need to find independent code areas
- "What parts of `src/parsers/` can be refactored independently?"
- "Which modules can we work on in parallel?"
- "Find isolated components in the graph module"

**PathFinder receives**: Scout's full report + target area (module, file, or symbol set)
**PathFinder returns**: Connected components + isolation boundaries + shared dependencies

---

## Example Flow

**User asks**: "What would break if I renamed `GraphBuilder.build` to `GraphBuilder.execute`?"

1. **Dispatch Scout** → runs `smt impact GraphBuilder.build --depth 3` + `smt status`
   - Returns: ✓ Graph fresh, 7 direct callers, 12 indirect callers, all in `src/smt_cli.py` and tests

2. Scout status: `DONE` + report ✓
   → **Dispatch Fabler** with Scout report + hypothetical change inlined

3. **Fabler analyzes** → reads Scout output, extends depth if needed, classifies each caller
   - Returns: 7 breaking calls (direct), 5 test references, 2 deprecation warnings needed, safe to do in one commit

4. Fabler status: `DONE` ✓
   → **Synthesize** → give user:
   - "7 places call this function (locations with file:line)"
   - "Change order: rename, update callers, update tests (3 commits safe)"
   - "Test coverage: 2 existing tests, 1 integration test"

---

## Integration with Claude Code

This skill is invoked via:
- `/smt-analysis` (explicit skill invocation)
- Or auto-detected when user asks questions like "What breaks if I change X?"

Subagents are spawned via the `Task` tool. Each subagent inherits full Claude Code capabilities (Read, Grep, Bash, etc.) but the prompt templates restrict them to SMT-specific queries.
