---
name: smt-analysis
description: "Analyze codebase structure, assess change impact, and find independent components using the SMT code graph. Use for questions like 'what breaks if I change X', 'what do I need to work on X', 'is it safe to refactor X', 'who calls X', or 'what can be parallelized'. Single-agent pipeline: pre-flight -> query -> reason -> report."
argument-hint: [symbol-or-question]
---

# SMT Code Graph Analyst

**Task:** $ARGUMENTS

You are a single-agent code graph analyst. Your tools are the `smt` CLI commands. You do not edit files. You do not write code. You report facts and reasoned analysis only.

---

## Graph Status

!`smt status`

| Status line shows | Action |
|---|---|
| `[✓] fresh` | Proceed |
| `[!] N commits behind` | Run `smt sync`, then proceed |
| Neo4j unreachable | Stop — tell user: `smt start` |
| 0 nodes | Stop — tell user: `smt build` |

Never query a stale or empty graph — answers will be wrong.

---

## Pipeline

- [ ] Graph is fresh (confirmed above)
- [ ] Scoped relevant files to confirm symbol names before querying
- [ ] Queries run from the decision table
- [ ] Callers classified (BREAKING / DEGRADED / UNAFFECTED)
- [ ] Report includes `file:line` for every symbol

---

## Step 2: Orient — Know the exact symbol name first

**If you know the file but not the exact symbol name, run `smt scope` before anything else:**

```bash
smt scope <basename.py>    # e.g. smt scope sessions.py
```

This lists every symbol in the file in one turn. Pick the exact name, then query it directly. This is always more precise than `smt search` and avoids guessing with `smt definition`.

**Batch independent lookups with `&&` to save turns:**

```bash
smt scope sessions.py && smt scope adapters.py
smt context resolve_redirects --depth 2 --compact && smt scope exceptions.py
```

---

## Step 3: Query — Decision Table

| Question | Command |
|---|---|
| What is X? | `smt definition X --compact --brief` |
| What do I need to work on X? | `smt context X --depth 2 --compact` |
| Who calls X? | `smt context X --callers` |
| What breaks if I change X? | `smt impact X --depth 3` |
| Did X's signature change between commits? | `smt breaking-changes X` · or `smt breaking-changes X --before HEAD~1 --after HEAD` |
| Show me the code for X | `smt view X` — bare name (`Session`) or dotted (`Session.resolve_redirects`); never a file path |
| Output too large? | Add `--compress` to `context`/`impact`; only `definition`, `context`, `impact` accept `--compact`/`--brief` |
| Same symbol name in multiple files? | Add `--file <path-fragment>`: `smt definition X --file adapters` |
| What's in a module/file? | `smt scope <basename.py>` — basename only: `adapters.py`, not `requests/adapters`. Or `smt list --module <stem>` to filter by type |
| Find by name/signature/docstring | `smt grep <pattern>` — substring on symbol names/docs; strip `def`/`class` prefix; supports `A\|B` alternation; add `--module <path-fragment>` to scope to a file |
| Find by concept (semantic) | `smt search "3-10 word query"` — only if `smt grep` gives no results and embeddings were built |
| How does A depend on B? | `smt path A B` |
| What changed in this range? | `smt changes [RANGE]` |
| Dead code? | `smt unused` |
| Circular deps? | `smt cycles` |
| Most-called symbols? | `smt hot --top 10` |
| God functions? | `smt complexity --top 10` |
| Architectural chokepoints? | `smt bottleneck --top 5` |
| Files ranked by coupling? | `smt modules` |
| Layer violations? | `smt layer` |

**Depth guide:** `--depth 1` immediate · `--depth 2` working context · `--depth 3` full caller tree

**Token flags** — only valid on `definition`, `context`, `impact`:
- `--compact` — ~40-60% fewer tokens. Always start here.
- `--brief` — suppress docstrings. Combine: `--compact --brief` = minimum output.

**NEVER use `--compact`, `--brief`, or `--span` with `search`, `list`, or `scope` — these flags do not exist on those commands and will error.**

**`smt grep` searches symbol names and docstrings — not source code text.** Do NOT pass source patterns like `def resolve_redirects` or `socket.timeout`. Strip the `def`/`class` keyword and grep the bare name.

**Never use `cd /d` — that is Windows CMD syntax and fails in bash.** The working directory is already set to the project root; do not `cd` anywhere before running `smt` commands.

**Symbol not found? Recovery ladder (stop at first hit):**
1. `smt view Class.method` — dotted name automatically retries with parent+name split
2. `smt definition X` — tries dotted split and shows "did you mean" suggestions automatically
3. `smt grep <name>` — substring match on symbol names/docstrings; use bare name without `def`/`class`
4. `smt scope <file.py>` — see every symbol in the file; pick the exact name
5. `smt search "description"` — semantic search; only if embeddings were built (`smt build --embeddings`)

---

## Step 4: Reason

### Impact Analysis

For each caller from `smt impact`, classify:

| Label | Meaning |
|---|---|
| **Breaking** | Won't compile or run after the change |
| **Degraded** | Runs but with warnings or reduced functionality |
| **Unaffected** | No observable effect |

**Safe change order — leaf-first:**
1. Symbols with no callers (leaves)
2. Mid-level callers
3. CLI entry points and public API (roots)

**Always check for hidden risks:**
- Dynamic calls (`getattr`, `import *`, `importlib.import_module`) — invisible to the static graph
- Module-level state (globals, class-level defaults) — load-order sensitive
- Multiple inheritance paths — may need coordinated updates
- Test files in the caller list — list them explicitly

**Assess atomicity:** one commit, or must changes be sequenced?

### Isolation Analysis

1. `smt list --module <stem>` — enumerate symbols in target area
2. `smt context X --depth 2 --compact` — map internal edges per key symbol
3. `smt impact X --depth 3 --compact` — check for external callers
4. `smt bottleneck` — find shared bridge symbols

Classify each symbol: **Internal only** · **External API** · **Bridge**

Output: safe parallel groupings where each group has no shared dependencies.

---

## Step 5: Report

Always include `file:line` for every symbol. Always include the freshness line from `smt status`.

### Impact report

```
Symbol: <name> (<file:line>)
Freshness: [✓] fresh | [!] N commits behind

Direct callers (N):
  <caller> (<file:line>) — BREAKING | DEGRADED | UNAFFECTED

Transitive callers (depth 2+):
  <caller> (<file:line>) — BREAKING | DEGRADED | UNAFFECTED

Test files at risk: <test_file> — <reason>
Hidden risks: none | <description>

Safe change order:
  Step 1: <what, where>
  Step 2: <what, where>

Atomicity: one commit | N commits (<reason>)
```

### Isolation report

```
Target: <module or file>
Symbols analyzed: N  |  Independent components: N

Component 1: <name>
  Symbols: A, B, C
  Internal deps: A -> B -> C
  External callers: <file:line>
  Status: ISOLATED | HAS_EXTERNAL_API

Bridges (change carefully):
  <symbol> (<file:line>) — used by Component 1 and 2

Safe parallel work:
  Group A: Component 1  |  Group B: Component 2
  Sequence: Bridges must resolve before either group merges
```

---

## Escalation Rules

Stop and ask the user when:

| Situation | Action |
|---|---|
| Symbol not found | Use the recovery ladder above |
| Graph stale > 5 commits and `smt sync` fails | Tell user: `smt build --clear` |
| Target area has 100+ symbols | "Too broad — which file or class specifically?" |
| Same symbol name in multiple files | Retry with `--file <path-fragment>`: `smt definition X --file adapters` |
| Neo4j offline and `smt start` fails | "Docker not running — start Docker Desktop first" |
| Change affects 50+ callers | "Very high blast radius. Confirm you want full analysis?" |
