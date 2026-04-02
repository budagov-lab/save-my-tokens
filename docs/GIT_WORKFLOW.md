# Git Workflow for SMT Teams

## The Rule: Push Git, Not Neo4j

**What gets pushed to GitHub:**
- ✅ Source code (src/)
- ✅ Git commits (automatically tracked)
- ✅ Configuration files (run.py, .mcp.json, pyproject.toml)
- ✅ Documentation (docs/)

**What stays local (NOT pushed):**
- ❌ Neo4j database (data/)
- ❌ Virtual environment (venv/)
- ❌ Logs (logs/)
- ❌ Environment variables (.env)

## Why?

```
GitHub stores: CODE (text, versioned, mergeable)
Neo4j stores: GRAPH (data, local index, built from code)

Neo4j is DERIVED from code - rebuild it, don't sync it!
```

## Team Workflow

### Developer 1 (Alice)

```bash
# Clone repo
git clone https://github.com/org/save-my-tokens.git
cd save-my-tokens

# Set up locally
docker-compose up -d neo4j
python run.py                    # Builds graph on Alice's machine

# Make changes
git checkout -b feature/auth
# ... edit code ...
git add src/auth.py
git commit -m "feat: Add authentication"
git push origin feature/auth     # Push to GitHub

# What happened:
# ✓ Git: alice-commit uploaded
# ✓ Neo4j: updated locally (NOT pushed)
```

### Developer 2 (Bob)

```bash
# Clone repo
git clone https://github.com/org/save-my-tokens.git
cd save-my-tokens

# Set up locally
docker-compose up -d neo4j
python run.py                    # Builds SAME graph on Bob's machine

# See Alice's changes
git pull origin feature/auth

# Bob's Neo4j automatically has Alice's code changes
# because it rebuilds from latest git commits!
```

## The Key Insight

```
Git commits → Python run.py → Neo4j graph

When Bob does:
  git pull origin feature/auth
  
His Neo4j graph automatically knows about Alice's changes.
Why? Because run.py reads git commits and builds graph!
```

## Merging Pull Requests

```
Alice's PR #42: feat/auth
├── Code changes: 3 files modified
├── Git: commits ready to merge
├── Neo4j: Alice's local graph updated
└── When merged:
    ├── Git: commits merged to main
    ├── GitHub: shows merged
    └── Bob's next pull: gets new code
        → python run.py rebuilds his graph
```

## No Merge Conflicts for Graph

Unlike code, the graph can't have merge conflicts:

```
Code merge conflict:
  ✗ Alice changes line 50
  ✗ Bob changes line 50
  → Git: CONFLICT - manual merge needed

Graph (Neo4j):
  ✓ Alice changes code → her graph updates
  ✓ Bob changes code → his graph updates
  ✓ When merged: whoever runs python run.py gets latest
  → NO CONFLICT - both have same graph after rebuild
```

## Continuous Integration / CD

```
GitHub Actions (future):
  1. Code pushed
  2. Tests run (check code)
  3. No graph testing needed!
     (graph is deterministic: same code = same graph)
  4. Merge approved
```

## Complete Team Workflow

```
Day 1:
  Alice: git clone → docker-compose up → python run.py
  Bob:   git clone → docker-compose up → python run.py
  Carol: git clone → docker-compose up → python run.py

Day 2 (Alice works):
  Alice:
    ├── git checkout -b feature/auth
    ├── edit src/auth.py
    ├── python run.py (auto-updates graph)
    ├── git add + commit + push
    └── Create PR #1

  Bob:
    ├── sees PR #1 on GitHub
    ├── git pull origin feature/auth
    ├── python run.py (gets Alice's graph)
    └── Reviews code in Claude with full context

  Carol:
    ├── stays on main
    ├── git pull origin main
    └── python run.py (baseline graph)

Day 3 (PR merged):
  GitHub:
    ├── PR #1 approved
    ├── Merge to main
    └── Alice's commits now in main

  Everyone:
    git pull origin main
    python run.py
    → All have same graph now!
```

## Summary

| Item | Where | Why |
|------|-------|-----|
| Source code | GitHub | Versioned, mergeable |
| Git commits | GitHub | Project history |
| Run scripts | GitHub | Needed for setup |
| Neo4j data | Local only | Rebuilt from code |
| Logs | Local only | Developer-specific |
| .env secrets | Local only | Security (.gitignore) |

**The magic:** Graph auto-syncs because it's built from git commits!

## Commands Cheat Sheet

```bash
# Setup (new developer)
git clone repo
docker-compose up -d neo4j
python run.py

# Make changes
git checkout -b feature/xxx
# ... edit ...
git add .
git commit -m "message"
git push origin feature/xxx

# Update from team
git pull origin main
python run.py    # Graph auto-updates

# Check status
python run.py graph --check
```

## Why This Works

Because SMT graph is **deterministic**:

```
Same code + same commits = same graph

No sync needed. No merge conflicts. No data loss.
Just rebuild from source of truth: git commits.
```
