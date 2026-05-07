---
name: smt-analysis
description: "Analyze codebase structure, assess change impact, and find independent components using the SMT code graph. Use for questions like 'what breaks if I change X', 'what do I need to work on X', 'is it safe to refactor X', 'who calls X', or 'what can be parallelized'. Single-agent pipeline: pre-flight -> query -> reason -> report."
argument-hint: [symbol-or-question]
---

# SMT Analyst

**Task:** $ARGUMENTS — facts and analysis only. No file edits.

## Pre-flight

!`smt status`

| Result | Action |
|---|---|
| `[✓] fresh` | Proceed |
| `[!] N behind` | `smt sync` then proceed |
| 0 nodes | Stop — tell user: `smt build` |
| unreachable | Stop — tell user: `smt start` |

## Orient first

Unknown symbol name? Run `smt scope <file.py>` — lists every symbol in the file. Batch independent lookups with `&&`.

## Query

| Question | Command |
|---|---|
| What is X? | `smt definition X --compact --brief` |
| Work on X? | `smt context X --depth 2 --compact` |
| Who calls X? | `smt context X --callers` |
| What breaks? | `smt impact X --depth 3` |
| Signature changed? | `smt breaking-changes X` |
| Show code | `smt view X` (symbol name, not file path) |
| File contents? | `smt scope <basename.py>` |
| Find by name/doc | `smt grep <pattern>` (bare name — no `def`/`class` prefix) |
| A→B path? | `smt path A B` |
| Changed symbols? | `smt changes [RANGE]` |
| Dead code / cycles / hotspots | `smt unused` · `smt cycles` · `smt hot` |
| God functions / chokepoints / layers | `smt complexity` · `smt bottleneck` · `smt layer` |

**`--compact --brief`** = minimum tokens. Valid only on `definition`, `context`, `impact` — never on `scope`, `list`, `grep`.  
**Depth:** 1 = immediate · 2 = working context · 3 = full tree  
**Output too large?** Add `--compress` to `context` or `impact`.  
**Same symbol in multiple files?** Add `--file <fragment>` to any command.

## Symbol not found

```
smt lookup X          # exact → dot-notation → partial (try first)
smt grep X            # substring on names + docstrings
smt scope <file.py>   # pick exact name from file listing
```

## Reason — Impact

Classify each caller from `smt impact`:  
**Breaking** (won't compile/run) · **Degraded** (runs with reduced functionality) · **Unaffected**

Safe change order: leaves first → mid-level callers → roots/public API.

Hidden risks to flag: `getattr`/`importlib` dynamic calls (invisible to graph) · module-level state · multiple inheritance · test files in caller list.

## Report

Lead with the freshness line from `smt status`. Include `file:line` for every symbol.

Impact report must cover: direct callers + transitive callers + test files at risk + hidden risks + safe change order + atomicity (one commit or sequenced?).

## Stop and ask when

- Symbol still missing after lookup + grep + scope
- Graph >5 commits stale and `smt sync` fails → tell user: `smt build --clear`
- Target has 100+ symbols → "Which file or class specifically?"
- 50+ callers → confirm before running full analysis
