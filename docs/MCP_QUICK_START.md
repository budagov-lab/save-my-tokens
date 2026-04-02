# SYT MCP Server - Quick Start Guide

**Get your code analysis graph working with Claude in 10 minutes.**

---

## Table of Contents
1. [Installation](#installation)
2. [Start the Server](#start-the-server)
3. [Claude Desktop Integration](#claude-desktop-integration)
4. [Claude Code Integration](#claude-code-integration)
5. [Using the Tools](#using-the-tools)
6. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites
- Python 3.11+
- Git
- Claude Desktop or Claude Code

### Step 1: Clone & Setup (3 minutes)

```bash
# Clone the repository
git clone https://github.com/budagov-lab/save-my-tokens.git
cd save-my-tokens

# Create virtual environment
python -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Step 2: (Optional) Start Neo4j

For full functionality, start Neo4j in Docker:

```bash
docker-compose up -d
```

This enables:
- Persistent graph storage
- Complex dependency queries
- Breaking change detection

**Without Neo4j:** The server runs in "offline mode" with in-memory graph (data lost on restart).

### Step 3: Verify Installation

```bash
# Run tests to confirm everything works
pytest tests/ -v

# Should see: 520 passed, 12 skipped
```

---

## Start the Server

### Option A: Direct (for development)

```bash
python run_mcp.py
```

This starts the MCP server on stdio (pipes data to Claude).

### Option B: Via Claude Code CLI

```bash
claude code --mcp /path/to/save-my-tokens/run_mcp.py
```

---

## Claude Desktop Integration

### 1. Find Your Config File

**macOS:**
```bash
~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```bash
~/.config/Claude/claude_desktop_config.json
```

### 2. Add SYT Server

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "syt-graph": {
      "command": "python",
      "args": ["/absolute/path/to/save-my-tokens/run_mcp.py"]
    }
  }
}
```

**⚠️ IMPORTANT:** Use **absolute path** (not relative)

### 3. Restart Claude Desktop

Close and reopen Claude Desktop. You should see "syt-graph" in the model selector bottom-right.

### 4. Test Connection

In Claude Desktop, you'll now see a hammer icon 🔨 in the input area when the server is connected.

---

## Claude Code Integration

### 1. Start the Server

```bash
python run_mcp.py
```

### 2. Use with Claude Code

```bash
claude code --mcp syt-graph
```

Or configure it in `.claude/settings.json`:

```json
{
  "mcpServers": [
    {
      "name": "syt-graph",
      "command": "python",
      "args": ["/path/to/save-my-tokens/run_mcp.py"]
    }
  ]
}
```

---

## Using the Tools

Once connected, Claude can use **10 MCP tools** for code analysis.

### Tool Categories

#### 1️⃣ **Graph Queries** (get code context)

**`get_context`** — Get a symbol's definition + what it calls + what calls it
```
Agent: "Show me the context for the `process_data` function"
Result: Function signature, 287 tokens vs 5000+ for full file
```

**`get_subgraph`** — Full dependency graph for a symbol
```
Agent: "What's the complete dependency tree for `validate_token`?"
Result: All functions it calls, all functions that call it (DAG)
```

**`semantic_search`** — Find code by meaning, not just name
```
Agent: "Find password validation logic"
Result: Ranked list of matching functions with similarity scores
```

**`validate_conflicts`** — Check if tasks can run in parallel
```
Agent: "Can I modify A and B at the same time?"
Result: Conflicts detected or "safe to parallelize"
```

#### 2️⃣ **Contracts & Breaking Changes** (detect incompatibilities)

**`extract_contract`** — Parse function signature, types, docstring
```
Agent: "What's the contract for `send_email()`?"
Result: Parameters, return type, exceptions, preconditions
```

**`compare_contracts`** — Detect breaking changes before modifying
```
Agent: "Is this new version of `API.fetch()` compatible?"
Result: Breaking changes detected (severity: HIGH) or "compatible"
```

#### 3️⃣ **Incremental Updates** (handle git changes)

**`parse_diff`** — Parse git diff to identify changed files
```
Agent: "What files changed in this commit?"
Result: Added/modified/deleted files with line counts
```

**`apply_diff`** — Update graph from file changes transactionally
```
Agent: "Update graph after renaming `old_func` to `new_func`"
Result: Graph updated atomically, or rolled back if error
```

#### 4️⃣ **Task Scheduling** (parallelize modifications)

**`schedule_tasks`** — Build execution plan with parallelization
```
Agent: "Plan these 10 modifications optimally"
Result: [[task1, task2], [task3, task4, task5], ...] (phases)
```

**`execute_tasks`** — Run tasks with conflict detection, retries
```
Agent: "Execute the plan with timeout handling"
Result: Per-task results, success rate, timing
```

---

## Example Workflow

### Scenario: Refactor authentication system

```
1. Agent calls get_context("validate_token")
   → Finds all functions that call validate_token (callers)
   → Finds all functions validate_token calls (dependencies)

2. Agent calls extract_contract("validate_token")
   → Gets signature: (token: str, check_expiry: bool = True) -> bool
   → Gets preconditions: token must be non-empty
   → Gets raises: InvalidTokenError, ExpiredTokenError

3. Agent modifies the code locally:
   → New signature: (token: str, check_expiry: bool = True, user_id: str | None = None) -> dict

4. Agent calls compare_contracts(old, new)
   → Detects: PARAMETER_ADDED (non-breaking, has default)
   → Detects: RETURN_TYPE_CHANGED (int → dict) → BREAKING
   → Result: is_compatible=False, breaking_changes=[...]

5. Agent updates callers to handle new return type

6. Agent calls schedule_tasks([
     {id: "t1", target: ["validate_token"]},
     {id: "t2", target: ["login"], dependency: ["validate_token"]},
     {id: "t3", target: ["refresh_token"], dependency: ["validate_token"]},
     {id: "t4", target: ["logout"]}
   ])
   → Result: phases = [[t1], [t2, t3], [t4]]
   → t1 must run first, then t2+t3 in parallel, then t4

7. Agent calls execute_tasks(plan)
   → Runs all tasks with retries, timeout handling
   → Returns: 4/4 succeeded, 0 failures
```

---

## Troubleshooting

### "MCP server not appearing in Claude Desktop"

**Check:**
1. Is Python 3.11+ installed? `python --version`
2. Is path absolute (not relative)? ✅ `/home/user/save-my-tokens` ❌ `~/save-my-tokens`
3. Did you restart Claude Desktop after editing config?
4. Does the file exist? `ls /path/to/run_mcp.py`

**Try:**
```bash
# Test the server directly
python run_mcp.py
# Should start without errors
```

### "Neo4j connection error"

**If running without Docker:**

```bash
# Check if Neo4j is running
docker-compose ps

# Start it
docker-compose up -d

# Or disable Neo4j (server will run in offline mode)
# Just don't call tools that require it
```

### "tree-sitter-typescript not installed"

TypeScript parser tests are optional. The server will still work, just skip TS files.

To enable TypeScript:
```bash
pip install tree-sitter-typescript
```

### "Timeout on large queries"

Queries take longer on big codebases. This is expected.
- 10K LOC: <100ms
- 50K LOC: <500ms
- 200K LOC: 1-2s

### "Memory usage growing"

The graph stays in memory for the session. To free memory:
```bash
# Restart the server
python run_mcp.py
```

---

## Architecture Overview

```
┌──────────────────────────────────┐
│   Claude Desktop / Code          │
│   (Agent asks questions)         │
└────────────┬─────────────────────┘
             │ (MCP Protocol)
             ↓
┌──────────────────────────────────┐
│   MCP Server (run_mcp.py)        │
│   - Tools: get_context, etc.     │
│   - Session management           │
└────────────┬─────────────────────┘
             │
    ┌────────┴────────┐
    ↓                 ↓
┌────────────┐  ┌──────────────┐
│ Symbol     │  │ Neo4j Graph  │
│ Index      │  │ (optional)   │
│ (in-memory)│  │              │
└────────────┘  └──────────────┘
```

**Key:** 
- **Symbol Index** — Parsed code structure (always loaded)
- **Neo4j** — Persistent graph (optional, for full features)

---

## What's Next?

1. **Read the README** for high-level overview
2. **Check FEATURE4_SCHEDULING_GUIDE.md** for task scheduling details
3. **Explore the docs/** folder for architecture & API specs
4. **Ask Claude** — Use the tools! That's what they're for.

---

## Quick Reference: Tool Usage

| Tool | Purpose | Example |
|------|---------|---------|
| `get_context` | Get symbol info + dependencies | `get_context("login", depth=2)` |
| `get_subgraph` | Full dependency graph | `get_subgraph("process_data", depth=3)` |
| `semantic_search` | Find by meaning | `semantic_search("password validation")` |
| `validate_conflicts` | Check if tasks parallel-safe | `validate_conflicts([task1, task2])` |
| `extract_contract` | Parse function signature | `extract_contract("auth.py", "validate_token")` |
| `compare_contracts` | Detect breaking changes | `compare_contracts(old_code, new_code)` |
| `parse_diff` | Parse git diff | `parse_diff(git_output)` |
| `apply_diff` | Update graph from changes | `apply_diff(delta)` |
| `schedule_tasks` | Build execution plan | `schedule_tasks(task_list)` |
| `execute_tasks` | Run tasks in parallel | `execute_tasks(plan)` |

---

**Questions?** Check the docs/ folder or open an issue on GitHub.

**Ready to go?** Start the server and ask Claude to analyze your code!
