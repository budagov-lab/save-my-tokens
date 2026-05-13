# SMT A2A Onboarding — New Agent Quick Start

You are connected to **save-my-tokens (SMT)**, a semantic code graph agent.
Invoke it via Bash. Full capability reference: `.well-known/agent.json`.
Skills harness: `.claude/skills/smt-analysis/SKILL.md`

---

## Step 1: Verify connection (always first)

```bash
smt status
```

Expected: `X nodes, Y edges, [✓] fresh` — graph is ready.

| Problem | Fix |
|---|---|
| Neo4j unreachable | `smt start` |
| 0 nodes | `smt build` |
| Graph stale | `smt sync` |

---

## Step 2: Explore an unknown codebase

```bash
smt status                                # Verify graph is ready
smt search "entry point"                  # Find where code starts
smt definition <found_symbol>             # What is it?
smt context <found_symbol> --depth 2      # Deps + callers
smt impact <found_symbol> --depth 3       # Who depends on it?
```

---

## Step 3: Deep analysis

For impact prediction, refactor safety, or parallel work planning — invoke the analyst:

```
/smt-analysis
```

Single-agent pipeline: pre-flight → query → reason → report. See `SKILL.md`.

---

## Core rules

- Always run `smt status` before querying — stale graph = wrong answers
- Prefer `smt context` over reading raw files
- Use `--compress` to trim bridge functions from large outputs
- Use `--depth 1` for fast overview, `--depth 3` for full dependency picture

---

## Command reference

```bash
# Symbol queries
smt definition <symbol>               # What is this? (1-hop, fastest)
smt context <symbol> --depth N        # Deps + callers (bidirectional)
smt context <symbol> --callers        # Callers only
smt context <symbol> --depth 2 --compress  # Compressed working context
smt impact <symbol> --depth N         # What breaks if I change this?
smt path <A> <B>                      # Shortest dependency path

# Search & discovery
smt search "<query>"                  # Find by meaning (3–10 words)
smt list --module <path>              # Enumerate symbols in a module
smt scope <file>                      # File's exports, imports, internals

# Architecture
smt cycles                            # Circular dependencies
smt hot --top N                       # Most-called symbols
smt complexity --top N                # Hardest to refactor (fan-in × fan-out)
smt bottleneck --top N                # Cross-file bridge symbols
smt modules                           # Files ranked by coupling
smt unused                            # Dead code candidates
smt layer                             # Layer violation detection

# Git integration
smt changes [RANGE]                   # Symbols in changed files + caller impact
smt sync [RANGE]                      # Sync graph after commits (default: HEAD~1..HEAD)

# Graph management
smt build                             # Build graph from source
smt build --clear                     # Wipe and rebuild
smt build --check                     # Show graph statistics
smt status                            # Graph health check
smt start | stop                      # Start / stop Neo4j container
smt config                            # Show/change settings (memory, password)
```
