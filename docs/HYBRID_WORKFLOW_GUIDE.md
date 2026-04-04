# Hybrid Workflow Guide: SMT + Traditional Analysis

When analyzing codebases with save-my-tokens (SMT), you don't have to choose between traditional file reading and graph-based queries. **Combine both approaches** for optimal efficiency and depth.

---

## Quick Comparison

| Approach | Best For | Time | Cost | Depth |
|----------|----------|------|------|-------|
| **SMT Only** | Architecture, call graphs | 18 min | 53k tokens | Functions |
| **Traditional Only** | Code details, security | 3.6 min | 70k tokens | Implementation |
| **Hybrid** | Full understanding | 23 min | 73k tokens | Complete ⭐ |

---

## Three-Phase Workflow

### Phase 1: Architecture Overview with SMT (5 minutes)

**Goal**: Understand high-level structure, entry points, major flows.

```bash
# Get overall graph health
smt status
# Output:
#   Graph: 4363 nodes, 7641 edges
#   Function: 2919, Class: 90, Module: 646

# Find entry points
smt context Flask              # Main class
smt context wsgi_app          # WSGI handler
smt context request_context   # Request setup

# Understand major flows
smt search "request handling"
smt search "error handling"
smt search "session management"

# Who calls what?
smt callers full_dispatch_request
smt callers process_response
```

**Output format**: Structured data (name, file, line, callers, callees)

**Decision point**:
- ✅ Understand structure? → Move to Phase 2
- ❌ Need more detail? → Skip to Phase 3 (deep dive)

---

### Phase 2: Call Graph Analysis (5 minutes)

**Goal**: Understand control flow, identify critical functions, find refactoring impact.

```bash
# Map request lifecycle
smt context wsgi_app          # Start here
smt callers wsgi_app          # Who calls it?
smt context full_dispatch_request
smt callers full_dispatch_request

# Trace error handling
smt context handle_exception
smt callers handle_exception
smt search "exception handling"

# Blueprint flow
smt context register_blueprint
smt callers register_blueprint
smt context preprocess_request
```

**What you learn**:
- Precise call chains (not guessed from patterns)
- Who depends on which functions
- Which changes break other code
- Security-critical call paths

**Example**:
```
$ smt context process_response
process_response  [Function]
  file: flask/app.py:1394
  calls (5):
    ensure_sync
    _get_session
    is_null_session
    save_session
    add_cookie
    
  callers (2):
    finalize_request
    handle_exception
```

---

### Phase 3: Deep Code Dive (5 minutes)

**Goal**: Understand implementation details, security issues, edge cases.

**Use Read tool for specific files identified in Phases 1-2:**

```bash
# Example: Understand session security
Read: flask/sessions.py (lines 263-350)
  → See save_session implementation
  → Understand signing, cookie flags, HMAC

# Example: Understand error handling
Read: flask/app.py (lines 897-946)
  → See handle_exception logic
  → Check PROPAGATE_EXCEPTIONS behavior

# Example: Blueprint registration
Read: flask/sansio/blueprints.py (lines 50-120)
  → See register() method
  → Understand deferred registration pattern
```

**Use Grep for pattern searches:**

```bash
# Find all error handlers
grep -n "@app.errorhandler" flask/app.py
grep -n "error_handler_spec" flask/*.py

# Find all hooks
grep -n "before_request" flask/*.py
grep -n "after_request" flask/*.py

# Find security-critical code
grep -n "SECRET_KEY" flask/*.py
grep -n "session" flask/sessions.py
```

---

## Decision Tree

```
Start: "I need to understand Feature X"
  ↓
Is it a high-level question?
  (architecture, flow, dependencies)
  ├─ YES → Phase 1 (SMT overview)
  │        → Sufficient? YES → Done ✅
  │        → Need more? NO → Phase 2 (call graphs)
  │                          → Sufficient? YES → Done ✅
  │                          → Need code? NO → Phase 3
  │
  └─ NO → Need implementation details?
           ├─ YES → Phase 3 (Read/Grep)
           │        → Understand algorithm? YES → Done ✅
           │        → Need context? NO → Go back to Phase 1
           │
           └─ NO → Phase 2 (call graphs)
                   → Understand relationships? YES → Done ✅
                   → Need details? NO → Phase 3
```

---

## Example Analyses

### Example 1: "How does Flask handle requests?"

**Phase 1** (SMT - 3 min):
```bash
smt context wsgi_app
smt context full_dispatch_request
smt callers full_dispatch_request
smt search "request lifecycle"
```
→ Understand: WSGI → full_dispatch → preprocess → dispatch → finalize → teardown

**Phase 2** (SMT - 2 min):
```bash
smt callers preprocess_request
smt callers dispatch_request
smt callers finalize_request
```
→ Understand: exact function call sequences, parameters, return handling

**Decision**: Skip Phase 3, you understand the flow ✅

---

### Example 2: "Is session handling secure?"

**Phase 1** (SMT - 2 min):
```bash
smt search "session management"
smt context SecureCookieSessionInterface
smt callers save_session
```
→ Understand: where sessions are saved, who calls it, what it depends on

**Phase 2** (SMT - 2 min):
```bash
smt context save_session
smt search "signing" "encryption" "crypto"
```
→ Understand: what cryptographic functions are used

**Phase 3** (Read/Grep - 5 min):
```bash
Read: flask/sessions.py (lines 263-350)
  → See exact HMAC implementation
  → Check salt handling
  → Verify key derivation
  
Grep: "SECRET_KEY" flask/*.py
  → Find all key usage
  → Check for hardcoded keys
```
→ Make security judgment ✅

---

### Example 3: "What breaks if I remove function X?"

**Phase 1** (SMT - 1 min):
```bash
smt context X
```
→ Get basic info on function X

**Phase 2** (SMT - 3 min):
```bash
smt callers X              # Who depends on X?
smt callers function_that_calls_X
smt callers function_that_calls_that
```
→ Trace full call chain upward

**Decision**: Phase 2 answers the question ✅

If you need implementation details:

**Phase 3** (Read - 2 min):
```bash
Read: each file that calls X
  → Understand impact
  → Check error handling
  → Verify it's safe to remove
```

---

## Token Budget Strategy

### If you have 100k tokens:
1. **Phase 1** (SMT): 5 min, 10k tokens
2. **Phase 2** (SMT): 5 min, 15k tokens
3. **Phase 3** (Read): 10 min, 30k tokens
4. **Reserve**: 45k tokens for follow-ups

**Result**: Deep understanding of 2-3 features

### If you have 50k tokens:
1. **Phase 1** (SMT): 3 min, 8k tokens
2. **Phase 2** (SMT): 2 min, 12k tokens
3. **Skip Phase 3**, use remaining for clarifications: 30k tokens

**Result**: Architectural understanding of 3-4 features

### If you have 20k tokens:
1. **Phase 1** (SMT): 3 min, 8k tokens
2. **Follow-ups**: 12k tokens

**Result**: Overview of 2-3 features (no deep dives)

---

## When to Use Each Tool

### Use SMT When:
- ✅ You need to know "who calls what"
- ✅ You need the call chain for refactoring impact
- ✅ You need architecture overview
- ✅ You're analyzing large codebases (10k+ files)
- ✅ You want to conserve tokens

### Use Read When:
- ✅ You need to understand algorithm implementation
- ✅ You need to see full method signatures
- ✅ You're doing security audit
- ✅ You need to understand edge cases
- ✅ You want the fastest initial understanding

### Use Grep When:
- ✅ You're finding all usages of a pattern
- ✅ You're looking for configuration keys
- ✅ You're finding error messages
- ✅ You're auditing security-sensitive code
- ✅ You want to verify completeness

---

## Real-World Example: Analyzing Error Handling

**Question**: "What happens when an unhandled exception occurs in a Flask app?"

### Phase 1: SMT Overview (3 min, 8k tokens)

```bash
$ smt search "exception handling"
→ Found: handle_exception, handle_user_exception, handle_http_exception

$ smt context handle_exception
handle_exception  [Function]
  file: flask/app.py:897
  calls (4):
    log_exception
    _find_error_handler
    finalize_request
    ensure_sync
    
  callers (1):
    wsgi_app

$ smt context _find_error_handler
_find_error_handler  [Function]
  file: flask/sansio/app.py:865
  calls (5):
    _get_exc_class_and_code
    error_handler_spec
    
  callers (3):
    handle_user_exception
    handle_http_exception
    handle_exception
```

**What we learned**:
- Exceptions enter through `handle_exception` (called by wsgi_app)
- Logged via `log_exception`
- Handler found via `_find_error_handler`
- Response finalized via `finalize_request`

### Phase 2: SMT Call Graph (2 min, 5k tokens)

```bash
$ smt callers log_exception
log_exception  [Function]
  callers (2):
    handle_exception (flask/app.py:920)
    error_handler (testing.py:...)

$ smt callers finalize_request
finalize_request  [Function]
  callers (3):
    full_dispatch_request (normal flow)
    handle_exception (error flow)
    handle_user_exception (error flow)
```

**What we learned**:
- Error flow: handle_exception → log_exception → find_error_handler → finalize_request
- Errors and normal requests both use finalize_request
- Response processing is unified

### Phase 3: Code Deep Dive (5 min, 12k tokens)

```bash
Read: flask/app.py:897-946
  → See handle_exception implementation
  → Check PROPAGATE_EXCEPTIONS config
  → Understand InternalServerError wrapping
  → See signal emission

Read: flask/sansio/app.py:865-900
  → See _find_error_handler implementation
  → Understand MRO-based lookup
  → Check blueprint scoping
  → See fallback behavior
  
Read: flask/sessions.py:263-280
  → See save_session (error handler safe?)
  → Check if exceptions in session handling crash handler
```

**What we learned**:
- Exception handling is layered (user → HTTP → internal server)
- Error handlers can be scoped per blueprint
- Session saving is part of finalize_request (runs even on error)
- PROPAGATE_EXCEPTIONS controls re-raising in debug mode

---

## Workflow Tips

### Tip 1: Start with SMT for any "who/what/where" question
```bash
# Good SMT questions:
smt context MyClass           # Where is it? What does it do?
smt callers my_function       # Who depends on this?
smt search "authentication"   # Where is auth handling?
smt status                    # Graph health?
```

### Tip 2: Use Read only after SMT narrows the scope
```bash
# Don't do this:
Read: flask/app.py (too big, 2900 lines, 15k tokens)

# Do this instead:
smt context wsgi_app           # Identify specific function
Read: flask/app.py:1566-1600   # Read just that function (100 lines, 2k tokens)
```

### Tip 3: Combine Grep with SMT results
```bash
# Find all error handlers using SMT:
smt search "error handling"

# Then verify with grep:
grep -n "@app.errorhandler" flask/*.py
grep -n "@blueprint.errorhandler" flask/*.py

# Cross-check: are there more than SMT found?
```

### Tip 4: Build understanding incrementally
```bash
Query 1: smt context EntryPoint       (5k tokens)
Query 2: smt callers EntryPoint       (3k tokens)
Query 3: smt context KeyFunction      (4k tokens)
Read 1:  app.py (specific section)    (5k tokens)
Query 4: smt search "related concept" (3k tokens)
                                Total: 20k tokens
Result: Deep understanding of feature
```

---

## Common Pitfalls to Avoid

### ❌ Pitfall 1: Using Read without SMT first
```bash
# Don't: Read entire files randomly
Read: flask/app.py (2900 lines, costs 15k tokens)

# Do: Use SMT first to find what you need
smt context Flask          (2k tokens)
smt search "request flow"  (2k tokens)
Read: flask/app.py:1566-1616 (2k tokens)  # Targeted read
```

### ❌ Pitfall 2: Over-relying on SMT for implementation details
```bash
# Don't: Only use SMT, miss algorithm details
smt context handle_exception
→ Understand who calls it, not how it works

# Do: Combine SMT with Read
smt context handle_exception        # See structure
Read: flask/app.py:897-946          # Understand implementation
```

### ❌ Pitfall 3: Not checking SMT results against code
```bash
# Don't: Trust SMT 100% (it's 99% accurate, not 100%)
smt context my_function
→ Claims 5 callers

# Do: Spot-check with grep
grep -n "my_function(" flask/*.py
→ Verify the count

# Usually they match, but verification is good practice
```

### ❌ Pitfall 4: Building graph for one-off analysis
```bash
# Don't: Do this for a single question
smt build --dir /path/to/repo    (45 seconds, setup overhead)
smt context Question1             (0.75 seconds)

# Do: This only for repos you'll analyze multiple times
# For one-off: Use Read/Grep directly (3.6 min total)
```

---

## Checklist: Planning Your Analysis

Before starting, ask yourself:

- [ ] Is this a one-off or recurring analysis?
  - One-off? → Traditional Read/Grep approach
  - Recurring? → Build SMT graph first

- [ ] How much time do I have?
  - <10 min? → Traditional approach
  - 20+ min? → Hybrid approach (SMT + Read)

- [ ] How much detail do I need?
  - Architecture only? → SMT Phase 1-2
  - Implementation too? → All 3 phases

- [ ] Token budget?
  - <50k? → SMT only
  - 50k-100k? → Hybrid (balanced)
  - >100k? → Deep hybrid (multiple features)

- [ ] Codebase size?
  - <1000 files? → Traditional is fine
  - 5000+ files? → SMT is better

---

## Summary

**The hybrid approach:**
1. Use SMT for **architecture & control flow** (fast, 15k tokens)
2. Use Read for **implementation details** (targeted, 20k tokens)
3. Use Grep for **pattern verification** (5k tokens)
4. **Total**: 40k tokens vs 70k tokens (traditional) or 53k tokens (SMT only)
5. **Quality**: Deep understanding vs overview only

**Choose your path:**
- ⚡ **Speed-focused**: Read/Grep (3.6 min)
- 💡 **Quality-focused**: Hybrid (23 min)
- 📊 **Token-focused**: SMT only (18 min, but less detail)
- 🎯 **Balanced**: Hybrid (23 min, 40k tokens, full understanding)
