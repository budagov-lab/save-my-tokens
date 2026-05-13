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
| `[!] N behind` N > 100 | CALL edges may be incomplete — `smt grep` and `smt view` are still fully reliable; treat any empty context/impact result as "not found" and use `smt grep` to locate usages instead |
| 0 nodes | Stop — tell user: `smt build` |
| unreachable | Stop — tell user: `smt start` |

## ⚡ Run smt directly — no cd required

`smt grep X`, `smt view X`, `smt context X` work from the current directory.  
**Do NOT `cd` anywhere before running smt — especially not `cd .claude/skills/smt-analysis`.**  
The working directory is already the project root.

## Turn 1 — check orient output first, then query

**Orient already ran above.** If it injected `smt context` output for your key symbols, you have callers + callees pre-loaded — proceed directly to reasoning. Only run additional commands if:
- The symbol was not found by orient (not in graph → use `smt grep`)
- You need deeper callers (`smt impact X --depth 3`)
- A second symbol wasn't covered

**If orient did NOT find the symbol** → run:
```bash
smt context X --depth 5 --compact --compress
```
This gives you: location, what it calls, and who calls it — in one command. Do NOT substitute grep + view + scope loops for this.

**If the task is "what breaks / what changes / what is affected by changing X"** → use:
```bash
smt impact X --depth 3
```
If X is a concept (not a symbol), use `smt grep <concept>` to identify the key symbols, then immediately run `smt impact sym1 --depth 3 && smt impact sym2 --depth 3`. Do NOT substitute grep/Read/scope loops for impact traversal.

| Situation | Run |
|---|---|
| orient injected context for your symbol | Skip — go straight to reasoning |
| symbol not found by orient | `smt context X --depth 5 --compact --compress` |
| "what breaks / what changes if I change X" | `smt impact X --depth 3` |
| "who calls X" | `smt context X --callers` |
| concept only, no symbol | `smt grep <concept>` → get symbols → then `smt context` or `smt impact` |
| file name mentioned | `smt scope requests/file.py` (full relative path, not basename) |

Batch independent queries with `&&` — never waste a turn on a single lookup.

## Stop when you have these four things

1. File path + line number for the symbol  
2. What it calls — from `smt context`  
3. Who calls it — from `smt context --callers` or `smt impact`  
4. The actual source — from `smt view`  

**That is enough. Write the report immediately. Do not read more files.**

## Symbol not found

If `smt definition X` or `smt view X` returns "not found":

```bash
smt grep X            # searches names + docstrings — use this first
smt scope <file.py>   # list what symbols actually exist in the file
```

Do NOT try `smt lookup X` — it also fails for symbols not in the graph.  
If `smt grep X` returns nothing: the symbol may not exist in this checkout. Use `smt scope <likely_file.py>` to see what IS there.

## When more depth is needed

| Need | Command |
|---|---|
| Full caller tree | `smt impact X --depth 3` |
| Symbol in multiple files | Add `--file <fragment>` to any command |
| Is file path ambiguous? | `smt scope requests/exceptions.py` (full path, not basename) |
| Contract change check | `smt breaking-changes X` |
| Shortest dependency path | `smt path A B` |
| Dead code / hotspots | `smt unused` · `smt hot` · `smt complexity` |

**`--compact --brief`** = minimum tokens. Valid on `definition`, `context`, `impact` only.  
**`--compress`** = removes bridge forwarders from context/impact output.  
**Output too large?** Add `--compress` then `--depth 1`.

## Hard stops — do NOT do these

- `cd` anywhere, especially `cd .claude/skills/smt-analysis` — run `smt` from the current directory  
- `findstr`, `Get-Content`, `Select-String` — bash only; use `smt grep`  
- `Read <file>` without offset — run `smt scope <file>` or `smt view <symbol>` first, then `Read` with offset+limit  
- `smt view <file.py>` or `smt view <file.py> --lines N-M` — `smt view` takes a **symbol name**, not a file path; use `smt scope <file>` to list symbols  
- `smt grep ... --output_mode content` or `smt grep ... -C N` — Grep tool flags; `smt grep` outputs content by default  
- Re-running the same query to verify — trust the first result  
- `smt view X --depth N` — `--depth` is not a view flag; use `smt context X --depth N`

## Report format

Lead with graph freshness from pre-flight. Include `file:line` for every symbol mentioned.  
Impact analysis: direct callers → transitive callers → test files → hidden risks (`getattr`, dynamic imports) → safe change order.
