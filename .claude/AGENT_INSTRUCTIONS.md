# SMT-First Agent Instruction Pattern

This document defines how agents should interact with this codebase when spawned via tools or subagent contexts.

**IMPORTANT:** SMT commands are invoked via Bash. Examples:
```bash
smt status                          # Check if graph is ready
smt context QueryEngine             # Get context for a symbol
smt search "agent loop"             # Semantic search
smt impact Neo4jClient --depth 3    # Impact analysis
```

## Tool Hierarchy (in order of preference)

### Tier 1: Semantic Tools (Use FIRST)
**Implementation:** Run via `Bash("smt context ...")` or similar
**Why:** 50-300x token efficient, understand code meaning, return structured relationships

- `bash: smt context <symbol>` — Get function + immediate dependencies + callers
  - Example: `Bash("smt context QueryEngine")`
  - Use for: "What does X do?", "What does X depend on?", "Who calls X?"
  - Cost: 1-2 requests, 50-200 tokens (much cheaper than reading full files)
  - Best for: Architecture understanding, dependency analysis

- `bash: smt search "<query>"` — Find related code by semantic meaning
  - Example: `Bash("smt search 'agent loop'")`
  - Use for: "Where is auth configured?", "Find similar patterns"
  - Cost: 1 request, 100-300 tokens
  - Best for: Exploratory queries, cross-cutting concerns

- `bash: smt impact <symbol>` — Analyze breaking changes
  - Example: `Bash("smt impact Neo4jClient --depth 3")`
  - Use for: "What breaks if I change X?"
  - Cost: 1 request, 200-400 tokens
  - Best for: Impact analysis, refactoring safety

### Tier 2: Pattern Matching Tools (Use when SMT needs validation)
**Why:** Fast verification, exact matching, pattern discovery

- `Grep(pattern)` — Find exact text matches
  - Use for: Verify SMT results, count occurrences, find exact identifiers
  - Cost: 1-3 requests, 50-150 tokens
  - When: After SMT gives you a suspected location

- `Glob(pattern)` — List files matching pattern
  - Use for: Find files by name pattern
  - Cost: 1 request, 50 tokens
  - When: You need file inventory

### Tier 3: File Operations (Use when location is known)
**Why:** Necessary for detailed inspection

- `Read(file)` — Read complete file
  - Use for: Examine full implementation, see exact code
  - Cost: ~100 tokens per 2k lines
  - When: File path is known from SMT/grep results
  - **AVOID:** Reading large files blindly; use smt context first

- `Edit(file)` — Modify file
  - Use for: Make code changes
  - Cost: 50-200 tokens per edit
  - When: Implementation is ready

### Tier 4: Shell Operations (Avoid)
**Why:** Least efficient, hard to parse, side-effect heavy

- `Bash(command)` — Run shell commands
  - Use for: Only when NO other tool applies
  - Cost: 100-500+ tokens (unpredictable output)
  - When: Building, testing, version checks
  - **AVOID:** Using find, grep, cat, head, tail — use dedicated tools instead

## Decision Rules by Query Type

| You want to... | Use this | Why |
|---|---|---|
| Understand what a function does | `smt context X` | Built-in caller/callee graph |
| Find all uses of a function | `smt impact X` | Reverse traversal built-in |
| Find similar patterns/concepts | `smt search "query"` | Semantic matching beats grep |
| Find exact function calls | `Grep("foo(")` | Pattern matching after SMT |
| Know how to call a function | `smt context X` then `Read(file)` | SMT finds location, Read shows signature |
| Understand architecture | `smt search` + `smt context` chain | Multi-step semantic understanding |
| Verify exact code location | `Grep(identifier)` | Fast confirmation after SMT |
| See full file contents | `Read(file)` | Only when file path known |

## Anti-Patterns (DO NOT DO THIS)

❌ **Do NOT use Bash find/grep/locate when tools exist**
```
# WRONG:
bash: find src -name "*.ts" -exec grep "pattern" {}

# RIGHT:
smt search "pattern"
then Glob("**/*.ts") if you need file list
```

❌ **Do NOT read entire files for exploratory queries**
```
# WRONG:
read(src/index.ts)  # 2000 lines, 200+ tokens
# Then manually search for the function

# RIGHT:
smt context FunctionName  # Gives exact location + dependencies
read(src/index.ts) if needed for full body
```

❌ **Do NOT use Grep for architecture questions**
```
# WRONG:
grep -r "import.*auth" .  # 50+ matches, need manual filtering

# RIGHT:
smt search "authentication middleware"  # Semantic understanding
```

❌ **Do NOT iterate files manually**
```
# WRONG:
for each file in src/:
  read(file)
  grep(pattern)

# RIGHT:
smt search "pattern" once  # Indexes entire codebase
```

## Agent Behavior Template

When spawned, agents should:

1. **Start with project context**
   ```
   smt status  # Verify graph is ready
   ```

2. **Explore semantically**
   ```
   smt search "<what I'm looking for>"
   smt context <symbol from search>
   ```

3. **Verify with patterns** (if needed)
   ```
   Grep(identifier) to double-check locations
   ```

4. **Read specific files** (only when necessary)
   ```
   Read(path from SMT) for implementation details
   ```

5. **Make changes** (with full context)
   ```
   Edit(file) with complete understanding
   ```

## Cost Estimates

| Tool | Cost | Result Quality |
|---|---|---|
| smt context | 1-2 req, 50-200 tokens | Structured, precise |
| smt search | 1 req, 100-300 tokens | Semantic, ranked |
| Grep | 1-3 req, 50-150 tokens | Exact, fragmented |
| Read | 1 req, 100-300 tokens per file | Complete, verbose |
| Bash | 1 req, 100-500+ tokens | Unpredictable |

**Efficiency ranking:** SMT context < SMT search < Grep < Read < Bash

## Token Budget Optimization

- **Wrong path:** Read(large file) → Grep(pattern) → Read(other files) = 500+ tokens
- **Right path:** SMT search → SMT context → Read(specific location) = 200 tokens
- **Savings:** 60% token reduction by using SMT first

## Implementation Notes

- Graph is at: `/tmp/512k-lines` (or project root)
- SMT commands: `smt --help` for full reference
- Graph status: `smt status` shows node count + readiness
- Stale graph: `smt build` to rebuild if needed

---

**This pattern is MANDATORY for all spawned agents in this codebase.**
