# SMT-First Blind Test - CORRECTED

## Test Objective

Verify that agents instructed with SMT-First pattern:
1. **Use Bash `smt` commands** for primary exploration (Tier 1)
2. **Use Grep/Read sparingly** for validation (Tier 2-3)
3. **Deliver comprehensive architecture report** without misleading estimates

---

## Corrected Test Format

### Step 1: Verify Working Directory
Agent MUST start with:
```bash
Bash("pwd")                    # Confirm current directory
Bash("ls -la /tmp/512k-lines")  # Verify target repo exists
```

### Step 2: Verify Graph is Ready
```bash
Bash("cd /tmp/512k-lines && smt status")  # Show node/edge counts
```

### Step 3: Research Using SMT-First Pattern
Use semantic tools FIRST:
- `Bash("smt search '...'")` for exploratory queries
- `Bash("smt context Symbol")` for architecture/dependencies
- `Bash("smt impact Symbol")` for breaking changes

Use validation tools only after:
- `Grep(pattern)` to verify exact locations
- `Read(file)` when specific code is needed

### Step 4: Simple Telemetry (No Token Estimates)
Just count actual tool calls. NO estimation. Format:

```
[TOOL CALL #N]
Tool: Bash | Grep | Read
Command: <what was executed>
```

---

## Final Report Requirements

After research, provide:

```
## TELEMETRY SUMMARY

Total tool calls: X

**Tool Breakdown:**
- Bash (smt search): Y calls
- Bash (smt context): Z calls  
- Bash (smt impact): A calls
- Bash (other): B calls
- Grep: C calls
- Read: D calls

**Ratios:**
- SMT commands: (Y+Z+A)/(X total) = ??%
- Semantic-first: (Y+Z+A+B)/(X total) = ??%
- Raw file ops: (C+D)/(X total) = ??%

**Actual clock time:** X minutes
**Report comprehensiveness:** [brief assessment]
```

---

## Success Criteria

✅ **PASS**: 
- >50% of tool calls are SMT commands (smt search/context/impact)
- Report is comprehensive (covers architecture, modules, patterns)
- Telemetry is honest (no invented token estimates)

❌ **FAIL**:
- <30% SMT commands (indicates agent didn't follow pattern)
- Analyzed wrong codebase (agent confusion)
- Misleading token estimates (useless data)
- Report is shallow or incomplete

---

## Key Rules for This Test

1. **Agent must verify working directory FIRST** (pwd + ls)
2. **Agent must call `smt status` to confirm graph is ready** 
3. **Agent must use SMT for 50%+ of exploration**
4. **No token estimation** - just count actual tool calls
5. **Focus on honest telemetry**, not impressive numbers
