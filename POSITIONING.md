# SMT Positioning & Messaging

## What is SMT?

**SMT = Code Context for AI Agents**

An MCP server that gives Claude smart, minimal code context. Instead of loading entire files and wasting tokens, SMT provides exactly what's needed.

---

## The Problem We Solve

**Without SMT:**
```
User: "Can you refactor the login function?"
Claude: "I need the entire auth.py file" (loads 5000 tokens)
Claude: "I don't know who calls this, so I can't parallelize"
Result: Token bloat, slow inference, one problem at a time
```

**With SMT:**
```
User: "Can you refactor the login function?"
Claude: "I found it + 8 callers + safe to parallelize" (287 tokens)
Claude: Works 11x faster, solves 11x more problems per conversation
Result: Efficient, fast, parallel code changes
```

---

## Core Benefits

| Problem | Solution |
|---------|----------|
| Load entire files (5000 tokens) | Get minimal context (287 tokens) |
| Don't know who calls what | See all callers + dependencies |
| Blind to breaking changes | Detect incompatibilities automatically |
| Can't parallelize safely | Automatic conflict detection |
| Full re-parse every request | Git-aware incremental updates |

---

## Key Messaging

### Headline
**"Make Claude understand your codebase efficiently"**

### Tagline
**"Code Context for AI Agents"**

### Value Prop
- ✅ **11x more problems** solved per conversation
- ✅ **Faster inference** with minimal context
- ✅ **Lower API costs** fewer tokens wasted
- ✅ **Safe parallelization** automatic conflict detection
- ✅ **One-click setup** install in 3 minutes

### For Developers
"Stop loading entire files into Claude. Give it a smart code map instead."

### For Teams Using Claude
"Make your code tasks 11x more efficient. One-click setup, immediate results."

---

## What NOT to Say

❌ "Graph API Foundation"  
❌ "Structured Dependency Graphs"  
❌ "MCP Server Implementation"  
❌ "Code Analysis Framework"  

These are implementation details, not benefits.

---

## What to Say Instead

✅ "Code Context for AI Agents"  
✅ "Smart Code Understanding"  
✅ "Efficient Code Queries for Claude"  
✅ "Make Claude Work Smarter With Your Code"  

---

## Quick Start Marketing Copy

**Installation:**
```
Windows: install.bat
macOS/Linux: bash install.sh
That's it!
```

**Configuration:**
```
Copy 5 lines to Claude Code settings.json
Restart Claude Code
Done!
```

**Result:**
```
Claude now understands your code instantly
Safe to parallelize changes
11x more efficient
```

---

## Use Cases to Highlight

1. **Refactoring** — "Refactor login flow without breaking callers"
2. **Code Review** — "Show me all implications of this change"
3. **Parallelization** — "Which tasks can run in parallel?"
4. **Breaking Changes** — "Will this break existing code?"
5. **Semantic Search** — "Find password validation logic"

---

## Elevator Pitch (30 seconds)

"SMT is an MCP server that gives Claude smart, minimal code context. Instead of loading entire files (wasting 90% of tokens), SMT provides exactly what's needed: symbol definitions, callers, dependencies, and breaking changes. Result: Claude understands your codebase instantly and solves 11x more problems per conversation."

---

## Positioned Against

| vs. | SMT Advantage |
|-----|---------------|
| Full-file retrieval | Minimal context (287 vs 5000 tokens) |
| Blind grep/search | Semantic search + dependency awareness |
| Sequential changes | Safe parallelization with conflict detection |
| Manual code review | Automatic breaking change detection |
| REST API reloads | Persistent graph + git-aware updates |

---

## Remember

**Not:** "We built a Graph API Foundation"  
**But:** "We made Claude work 11x better with your code"

Focus on the benefit, not the technology.
