# SMT A2A Onboarding — New Agent Quick Start

You are connected to **save-my-tokens (SMT)**, a semantic code graph agent.
Invoke it via Bash. Full capability reference: `.claude/a2a/smt.json`.
Skills harness: `.claude/skills/smt-analysis/`

---

## Step 1: Verify connection (always first)

```bash
smt status
```

Expected: `X nodes, Y edges, [✓] fresh` — graph is ready.
If Neo4j is down: run `smt docker up` first.
If empty: run `smt build`. If stale: run `smt diff`.

---

## Step 2: Example — explore an unknown codebase

```bash
smt status                              # Verify graph is ready
smt search "entry point"               # Find where code starts
smt context <found_symbol>             # Understand it
smt context <found_symbol> --depth 2   # Deeper context (deps + callers)
smt impact <found_symbol> --depth 3    # Who depends on it?
```

---

## Step 3: Multi-agent analysis (optional)

For deep analysis — impact prediction, refactor safety, parallel work planning:

```
/smt-analysis
```

This launches Scout → Fabler/PathFinder → synthesis. See `SKILL.md` in the skills directory.

---

## Rules

- Run `smt status` before any query — stale graph = wrong answers
- Prefer `smt context` over reading files
- Use `--compress` flag to remove bridge functions (reduces output size)
- Use `--depth 1` for fast overview, `--depth 3` for full dependency picture

---

## All commands

```bash
smt definition <symbol>          # What is this? (fastest)
smt context <symbol> --depth N   # What do I need to work on this?
smt impact <symbol> --depth N    # What breaks if I change this?
smt search "<query>"             # Find by meaning
smt callers <symbol>             # Who calls this?
smt status                       # Graph health
smt build                        # Build graph from source
smt diff HEAD~1..HEAD            # Sync after commits
smt docker up / down / status    # Neo4j management
```
