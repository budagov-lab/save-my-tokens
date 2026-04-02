# SMT MCP Server - Practical Examples

**Real-world examples of how to use the graph API with Claude.**

---

## Example 1: Understand a Function Before Modifying It

### Scenario
You want to modify the `authenticate_user()` function but need to understand what it does and who uses it.

### Agent Conversation

**Agent:** "Show me the context for `authenticate_user` function"

```python
result = await mcp.call_tool("get_context", {
    "symbol_name": "authenticate_user",
    "depth": 2,
    "include_callers": True
})
```

**Response:**
```json
{
  "symbol": {
    "name": "authenticate_user",
    "type": "function",
    "file": "src/auth/core.py",
    "line": 45,
    "docstring": "Authenticate user with username/password. Returns token on success.",
    "node_id": "Function:authenticate_user:45"
  },
  "dependencies": [
    {
      "name": "hash_password",
      "type": "function",
      "file": "src/auth/crypto.py",
      "reason": "called by authenticate_user"
    },
    {
      "name": "User",
      "type": "class",
      "file": "src/models/user.py",
      "reason": "used in function body"
    }
  ],
  "callers": [
    {
      "name": "login_endpoint",
      "type": "function",
      "file": "src/api/routes.py",
      "reason": "calls authenticate_user"
    },
    {
      "name": "refresh_token",
      "type": "function",
      "file": "src/auth/core.py",
      "reason": "calls authenticate_user"
    }
  ],
  "token_estimate": 287
}
```

### What You Learned
- Function location: `src/auth/core.py` line 45
- What it calls: `hash_password`, uses `User` class
- Who calls it: `login_endpoint`, `refresh_token`
- Context size: 287 tokens (safe to pass to Claude's full reasoning)

---

## Example 2: Detect Breaking Changes Before Shipping

### Scenario
You refactored the `send_email()` function. Before shipping, check if existing callers will break.

### Agent Conversation

**Original Code:**
```python
def send_email(recipient: str, subject: str, body: str) -> bool:
    """Send email. Returns True if successful."""
    ...
```

**New Code:**
```python
def send_email(
    recipient: str,
    subject: str,
    body: str,
    cc: list | None = None,
    bcc: list | None = None,
    priority: str = "normal"
) -> dict:
    """Send email. Returns dict with status, message_id, delivery_time."""
    ...
```

**Agent asks:** "Are these changes compatible?"

```python
result = await mcp.call_tool("compare_contracts", {
    "symbol_name": "send_email",
    "old_source": old_code,
    "new_source": new_code
})
```

**Response:**
```json
{
  "symbol": "send_email",
  "is_compatible": false,
  "compatibility_score": 0.4,
  "breaking_changes": [
    {
      "type": "RETURN_TYPE_CHANGED",
      "severity": "HIGH",
      "impact": "Callers expecting bool will fail with dict",
      "affected_elements": ["return"],
      "old_value": "bool",
      "new_value": "dict"
    }
  ],
  "non_breaking_changes": [
    "Added optional parameter: cc",
    "Added optional parameter: bcc",
    "Added optional parameter: priority"
  ]
}
```

### Action Taken
Agent sees `is_compatible: false` and **automatically updates all callers**:
```python
# Before
if send_email(user.email, subject, body):
    log("Email sent")

# After (auto-generated)
result = send_email(user.email, subject, body)
if result.get("status") == "sent":
    log(f"Email sent: {result.get('message_id')}")
```

---

## Example 3: Find Code by Meaning (Semantic Search)

### Scenario
You need to find password validation logic, but don't know where it is.

### Agent Conversation

**Agent:** "Find password validation functions"

```python
result = await mcp.call_tool("semantic_search", {
    "query": "password validation strength check entropy",
    "top_k": 5
})
```

**Response:**
```json
{
  "results": [
    {
      "symbol": "validate_password_strength",
      "file": "src/auth/validators.py",
      "type": "function",
      "similarity": 0.92,
      "excerpt": "Validate password meets minimum requirements..."
    },
    {
      "symbol": "check_password_entropy",
      "file": "src/auth/crypto.py",
      "type": "function",
      "similarity": 0.85,
      "excerpt": "Calculate Shannon entropy of password..."
    },
    {
      "symbol": "PasswordPolicy",
      "file": "src/config.py",
      "type": "class",
      "similarity": 0.78,
      "excerpt": "Password policy configuration: min length, chars..."
    }
  ]
}
```

### Why This Matters
- **Without semantic search:** You'd grep for "password" and get 100+ matches
- **With semantic search:** You get the 5 most relevant functions ranked by similarity
- **Time savings:** Find the right code in seconds, not minutes

---

## Example 4: Check if Multiple Tasks Can Run in Parallel

### Scenario
You have 3 code modifications to make:
1. Refactor authentication system
2. Add email notifications
3. Update database schema

Can you do them in parallel or will they conflict?

### Agent Conversation

**Agent:** "Can I do these tasks in parallel?"

```python
result = await mcp.call_tool("validate_conflicts", {
    "tasks": [
        {
            "id": "refactor_auth",
            "target_symbols": ["authenticate_user", "refresh_token"],
            "dependency_symbols": []
        },
        {
            "id": "add_email_notifications",
            "target_symbols": ["send_email", "notify_user"],
            "dependency_symbols": ["authenticate_user"]
        },
        {
            "id": "update_db_schema",
            "target_symbols": ["User", "Session"],
            "dependency_symbols": []
        }
    ]
})
```

**Response:**
```json
{
  "tasks": ["refactor_auth", "add_email_notifications", "update_db_schema"],
  "direct_conflicts": [
    {
      "type": "direct_overlap",
      "task_a": "refactor_auth",
      "task_b": "add_email_notifications",
      "conflicting_symbols": ["authenticate_user"]
    }
  ],
  "dependency_conflicts": [
    {
      "type": "read_write_conflict",
      "task_a": "update_db_schema",
      "task_b": "refactor_auth",
      "reason": "refactor_auth reads User, update_db_schema modifies User"
    }
  ],
  "parallel_feasible": false,
  "recommendation": "refactor_auth must complete before add_email_notifications and update_db_schema"
}
```

### Execution Plan
Agent determines optimal order:
```
Phase 1: refactor_auth (must do first)
    ↓
Phase 2: add_email_notifications + update_db_schema (can run in parallel)
```

This saves time: sequential would take 30 min, parallel takes 20 min.

---

## Example 5: Analyze a Git Commit

### Scenario
You made changes and committed. What symbols did you actually modify?

### Agent Conversation

**Agent gets git diff and asks:** "Parse this commit"

```python
git_diff = subprocess.check_output(["git", "diff", "HEAD~1"]).decode()

result = await mcp.call_tool("parse_diff", {
    "diff_text": git_diff
})
```

**Response:**
```json
{
  "files": [
    {
      "file_path": "src/auth/core.py",
      "status": "modified",
      "added_lines": 15,
      "deleted_lines": 8
    },
    {
      "file_path": "tests/test_auth.py",
      "status": "modified",
      "added_lines": 42,
      "deleted_lines": 0
    }
  ],
  "total_files_changed": 2,
  "total_lines_added": 57,
  "total_lines_deleted": 8
}
```

### Apply Changes to Graph

**Agent then updates the graph:**

```python
result = await mcp.call_tool("apply_diff", {
    "diff": git_diff,
    "repo_path": "/path/to/repo"
})
```

**Response:**
```json
{
  "success": true,
  "delta": {
    "file": "src/auth/core.py",
    "added": [
      {
        "name": "validate_mfa_token",
        "type": "function"
      }
    ],
    "deleted": [],
    "modified": [
      {
        "name": "authenticate_user",
        "type": "function"
      }
    ]
  },
  "duration_ms": 42.3
}
```

---

## Example 6: Scheduled Task Execution

### Scenario
You have 10 refactoring tasks. Schedule and execute them with optimal parallelization.

### Agent Conversation

**Agent:** "Schedule and execute these tasks"

```python
tasks = [
    {"id": "t1", "target_symbols": ["validate_email"]},
    {"id": "t2", "target_symbols": ["validate_phone"], "dependency_symbols": ["validate_email"]},
    {"id": "t3", "target_symbols": ["validate_address"]},
    {"id": "t4", "target_symbols": ["send_confirmation"], "dependency_symbols": ["validate_email"]},
    # ... 6 more tasks
]

# Step 1: Build schedule
schedule_result = await mcp.call_tool("schedule_tasks", {
    "tasks": tasks
})
```

**Schedule Response:**
```json
{
  "phases": [
    ["t1", "t3"],           # Phase 1: independent tasks (parallel)
    ["t2", "t4"],           # Phase 2: depends on phase 1
    ["t5"],                 # Phase 3: depends on phase 2
    ["t6", "t7", "t8", "t9", "t10"]  # Phase 4: can all run in parallel
  ],
  "total_tasks": 10,
  "critical_path_length": 4,
  "parallelizable_pairs": 8
}
```

**Step 2: Execute**

```python
exec_result = await mcp.call_tool("execute_tasks", {
    "tasks": schedule_result["phases"],
    "max_retries": 3,
    "timeout_per_task": 30
})
```

**Execution Response:**
```json
{
  "total_tasks": 10,
  "succeeded": 10,
  "failed": 0,
  "results": {
    "t1": {"status": "success", "time_ms": 120},
    "t2": {"status": "success", "time_ms": 95},
    // ... more results
  },
  "total_time_ms": 2400,  # ~4 minutes instead of 15+ sequential
  "success_rate": 1.0
}
```

---

## Common Patterns

### Pattern 1: "Before I modify X, show me what depends on it"
```python
get_context("X", include_callers=True)
# → Who calls X? Don't break them.
```

### Pattern 2: "Is this change safe?"
```python
compare_contracts(old_code, new_code)
# → Breaking changes? Incompatibilities? Flag them.
```

### Pattern 3: "Find all password-related code"
```python
semantic_search("password validation")
# → Get ranked results by relevance, not grep output.
```

### Pattern 4: "Can I parallelize these changes?"
```python
validate_conflicts([task1, task2, task3])
# → Conflict detection before execution.
```

### Pattern 5: "What did I actually change?"
```python
parse_diff(git_diff)
# → File-level and symbol-level changes.
```

---

## Performance Expectations

| Operation | Size | Time |
|-----------|------|------|
| `get_context` | 10K LOC | <50ms |
| `get_subgraph` | 10K LOC | <100ms |
| `semantic_search` | 50K LOC | <500ms |
| `validate_conflicts` | 100 tasks | <200ms |
| `schedule_tasks` | 100 tasks | <100ms |
| `execute_tasks` (1 task) | - | 30ms-2s |
| `compare_contracts` | - | <100ms |

---

## Tips & Tricks

1. **Use depth parameter to control context size**
   - `depth=1`: Direct dependencies only (smallest, fastest)
   - `depth=2`: Dependencies of dependencies (medium)
   - `depth=3`: Full reachability (large, slower)

2. **Always check token_estimate before sending to Claude**
   - Estimate: 287 tokens ✅ Safe to pass
   - Estimate: 50,000 tokens ❌ Too large, use depth=1

3. **Semantic search is slower but more accurate**
   - Use for "find password validation" (broad)
   - Don't use for "find function `validate_password`" (use grep instead)

4. **Conflicts have reasons**
   - Read the `reason` field to understand why tasks conflict
   - Sometimes you can refactor to avoid conflicts

5. **Execution phases show optimal parallelization**
   - Fewer phases = better parallelization
   - More tasks per phase = more parallelism

---

**Next:** Read MCP_QUICK_START.md for setup instructions.
