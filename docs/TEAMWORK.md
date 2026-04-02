# Teamwork with SMT - GitHub Integration

SMT supports collaborative workflows on GitHub. When your team works on the same repo, SMT automatically tracks:

- Pull requests and branches
- Who's working on what
- Collaboration context per developer

## Setup: Enable GitHub Integration

### 1. Create GitHub Personal Access Token

```bash
# Go to: https://github.com/settings/tokens
# Create new token with:
#   - repo (full control of repositories)
#   - read:org
# Copy the token
```

### 2. Set Environment Variable

```bash
export GITHUB_TOKEN=ghp_xxxxxx
python run.py
```

Or add to `.env`:
```
GITHUB_TOKEN=ghp_xxxxxx
```

## How It Works

### Single Repo, Multiple Developers

When developers work on same GitHub repo:

```
Repository: save-my-tokens (main branch)
├── Developer A (branch: feature/auth)
│   └── SMT loads: save_my_tokens graph
├── Developer B (branch: fix/bug-123)
│   └── SMT loads: save_my_tokens graph
└── Main branch (CI/CD)
    └── SMT loads: save_my_tokens graph
```

**All use same graph**, but SMT tracks which branch/PR each developer is on.

### Check Status with GitHub Context

```bash
# Main branch
python run.py graph --check
# Output:
#   Database: save_my_tokens
#   Branch: main
#   Open PRs: 3

# On PR branch
git checkout feature/auth
python run.py graph --check
# Output:
#   Database: save_my_tokens
#   Branch: feature/auth
#   Pull Request: #42 - Add authentication
#   Author: alice
```

## Collaboration Scenarios

### Scenario 1: Code Review on Pull Request

```
Alice creates PR #42: Add authentication
├── SMT shows: PR #42, author alice
├── Bob reviews code
└── Claude can analyze: "Show me the auth changes in this PR"
    → SMT provides context scoped to PR branch
```

### Scenario 2: Parallel Development

```
Main branch:
├── Graph state: 653 nodes, 776 edges
├── Team members: Alice (PR #40), Bob (PR #41), Carol (PR #42)
└── Each PR: separate branch, same graph namespace
```

SMT prevents conflicts by:
- Tracking which branch/PR is active
- Showing who's working on what
- Graph updates when branches merge

### Scenario 3: Code Review Bot

```python
# Future: Automated code review
gh pr comment --body "SMT Analysis: Your changes affect 3 functions"
```

## Multi-Project Teams

If your team manages multiple GitHub repos:

```
Organization:
├── repo1 (save-my-tokens)
│   └── Graph: smt_default or save_my_tokens
├── repo2 (other-project)
│   └── Graph: other_project
└── repo3 (backend)
    └── Graph: backend
```

Each repo has separate graph automatically.

## Without GitHub Token

SMT works fine without GitHub integration:

```bash
python run.py graph --check
# Output:
#   Database: syt
#   Branch: main
#   Open PRs: 0 (not fetched)
```

No GitHub features, but graph still works normally.

## What's Tracked

With GitHub integration enabled, SMT sees:

```
Pull Request Info:
├── Number (#42)
├── Title ("Add authentication")
├── Author (alice)
├── Branch (feature/auth)
└── State (open/closed)

Current Context:
├── Current branch
├── Is it a PR branch?
├── Related PR (if any)
└── Open PRs count
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | Personal access token for GitHub API |
| `SMT_PROJECT` | Override project name (else uses directory) |

## Troubleshooting

**"GitHub integration not configured"**
- Set `GITHUB_TOKEN` environment variable
- Requires `gh` CLI installed (from GitHub)

**PR shows "Open PRs: 0" but there are PRs**
- GitHub token may not have correct permissions
- Token may be expired
- Run: `gh auth status` to check

**Can't fetch branch info**
- You're not in a git repository
- Or git remote is not GitHub

## Coming Soon

- [ ] Auto-graph updates when PR is merged
- [ ] Conflict detection between PRs
- [ ] Team analytics: who changed what
- [ ] Code review insights from graph
