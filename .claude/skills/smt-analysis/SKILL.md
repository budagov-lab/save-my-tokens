---
name: smt-analysis
description: "Analyze codebase structure, assess change impact, and find independent components using the SMT code graph. Use for questions like 'what breaks if I change X', 'what do I need to work on X', 'is it safe to refactor X', 'who calls X', or 'what can be parallelized'. Single-agent pipeline: pre-flight -> query -> reason -> report."
argument-hint: [symbol-or-question]
---

# SMT Analyst

**Task:** $ARGUMENTS — facts and analysis only. No file edits.

## Pre-flight

!`smt status 2>&1`

## Auto-context (callers + callees pre-loaded)

!`smt orient "$ARGUMENTS" --source 2>/dev/null`

| Status | Action |
|---|---|
| `[✓] fresh` | Proceed |
| `[!] N behind` N ≤ 10 | `smt sync` then proceed |
| `[!] N behind` N > 10 | Proceed — line numbers may drift, but edges are intact |
| `[!] N behind` N > 100 | CALL edges may be incomplete — treat empty context/impact as "not found" and re-locate via the Phase 1 ladder |
| 0 nodes | Stop — tell user: `smt build` |
| unreachable | Stop — tell user: `smt start` |

## ⚡ Run smt directly — no cd required

`smt view X`, `smt scope X`, `smt context X` work from the current directory.  
**Do NOT `cd` anywhere before running smt — especially not `cd .claude/skills/smt-analysis`.**  
The working directory is already the project root.

## Three phases: Locate → Read → Trace

Every analysis follows this pipeline. Never skip a phase.

### Phase 1 — Locate (where is the symbol?)

**Check the orient output above first.** Work down this ladder until you have `Symbol [Type] file:line`:

| You have | Do |
|---|---|
| Symbol in orient output — `Name [Type] file:line` | **Done** — symbol name is right there, go to Phase 2 |
| Exact or partial symbol name | `smt lookup <name>` — fuzzy + dot-notation resolver |
| A file path | `smt scope <file>` → pick the relevant symbol → go to Phase 2 |
| A concept only (no symbol name) | `smt grep <concept>` — searches names + docstrings (**last resort**) |

`smt grep` is only for the last row. If you have a symbol name or file path, skip it entirely.

### Phase 2 — Read (what is the symbol?)

```bash
smt view <symbol>        # source lines — primary read tool
smt definition <symbol>  # signature + docstring + immediate callees
```

Both need a **symbol name**, not a file path. Get the name from Phase 1 first.

### Phase 3 — Trace (how does it connect?)

```bash
smt context <symbol> --depth 2    # callers + callees together
smt context <symbol> --callers    # who calls it only
smt impact <symbol> --depth 3     # full reverse traversal — use for "what breaks if I change X"
```

**"What breaks / what changes if I change X"** → go straight to `smt impact X --depth 3`.  
For a concept (not yet a symbol), complete Phase 1 first, then run impact on each result.

Batch independent queries with `&&` — never waste a turn on a single lookup.

## Stop when you have these four things

1. File path + line number — from Phase 1  
2. Source — from `smt view`  
3. What it calls — from `smt context` or `smt definition`  
4. Who calls it — from `smt context --callers` or `smt impact`  

**That is enough. Write the report immediately. Do not read more files.**

## When more depth is needed

| Need | Command |
|---|---|
| Full caller tree | `smt impact X --depth 3` |
| Symbol in multiple files | Add `--file <fragment>` to any command |
| Is file path ambiguous? | `smt scope requests/exceptions.py` (full path, not basename) |
| Contract change check | `smt breaking-changes X` |
| Shortest dependency path | `smt path A B` |
| Dead code / hotspots | `smt unused` · `smt hot` · `smt complexity` |

| Flag | Works on | Effect |
|---|---|---|
| `--compact --brief` | `definition` · `context` · `impact` ONLY | minimum tokens |
| `--compress` | `context` · `impact` ONLY | removes bridge forwarders |
| `--depth N` | `context` · `impact` ONLY | traversal depth |

**Output too large?** `--compress` first, then `--depth 1`. Do NOT add these flags to `grep`, `scope`, `path`, `lookup`, `view`, or analysis commands — they will error.

## Hard stops — do NOT do these

- `cd` anywhere, especially `cd .claude/skills/smt-analysis` — run `smt` from the current directory  
- `findstr`, `Get-Content`, `Select-String` — not available; use `smt scope` or `smt view`  
- `Read <file>` without offset — run `smt scope <file>` or `smt view <symbol>` first, then `Read` with offset+limit  
- `smt grep <file.py>`, `smt context <file.py>`, `smt view <file.py>` — these take a **symbol name**, not a file path; use `smt scope <file>` for a file-based view  
- `smt grep` when you already have the symbol name — go straight to `smt view` or `smt definition`  
- `smt grep ... --output_mode content` or `smt grep ... -C N` — Grep tool flags; not valid for smt  
- Re-running the same query to verify — trust the first result  
- `smt view X --depth N` — `--depth` is not a view flag; use `smt context X --depth N`

## Report format

Lead with graph freshness from pre-flight. Include `file:line` for every symbol mentioned.  
Impact analysis: direct callers → transitive callers → test files → hidden risks (`getattr`, dynamic imports) → safe change order.
