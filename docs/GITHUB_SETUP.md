# Connect SMT with GitHub - Step by Step

## What You Need

1. GitHub account (free or paid)
2. GitHub Personal Access Token (for PR tracking)
3. `gh` CLI tool (optional, for advanced features)

## Step 1: Create GitHub Personal Access Token

This lets SMT see your pull requests and branches.

### Option A: Using GitHub Web UI

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name it: `smt-graph`
4. Select permissions:
   - `repo` (full control of repositories)
   - `read:org` (read organization info)
5. Click "Generate token"
6. **Copy the token** (you won't see it again!)

### Option B: Using GitHub CLI

```bash
gh auth login
# Follow prompts to authenticate
```

## Step 2: Set Environment Variable

### Windows (PowerShell)

```powershell
$env:GITHUB_TOKEN = "ghp_xxxxxxxxx"
python run.py
```

### Windows (Command Prompt)

```cmd
set GITHUB_TOKEN=ghp_xxxxxxxxx
python run.py
```

### macOS / Linux (Bash)

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxx
python run.py
```

### Make it Permanent

Create `.env` file in project root:

```
GITHUB_TOKEN=ghp_xxxxxxxxx
GITHUB_USER=your_github_username
```

Then run:
```bash
python run.py
```

## Step 3: Verify Connection

```bash
python run.py graph --check
```

**Output should show:**
```
Database: save_my_tokens
Branch: main
Open PRs: 2  ← GitHub is connected!
Status: READY FOR MCP
```

**If you see "Open PRs: 0" but there ARE PRs:**
- Token might not have right permissions
- Repository URL might not be GitHub
- Run: `gh auth status` to check

## Step 4: Use GitHub Integration

### Check Status on Current Branch

```bash
git checkout feature/auth
python run.py graph --check
```

**Output:**
```
Database: save_my_tokens
Branch: feature/auth
Pull Request: #42 - Add authentication
Author: alice
Status: READY FOR MCP
```

### See All Open PRs

```bash
python run.py graph --check
```

Shows count of open PRs and which branch you're on.

### Work on Different Branches

```bash
# Main branch
git checkout main
python run.py graph --check
# Output: Branch: main, Open PRs: 2

# Feature branch
git checkout feature/new-feature
python run.py graph --check
# Output: Branch: feature/new-feature, PR: #45

# Another feature
git checkout fix/bug-123
python run.py graph --check
# Output: Branch: fix/bug-123, PR: #46
```

## Step 5: Configure for Team

### For Your Team Repository

Add to project `.env.example` (commit to git):

```
# GitHub integration (optional)
# Get token from: https://github.com/settings/tokens
GITHUB_TOKEN=your_token_here
```

Tell your team:
1. Create their own GitHub token
2. Add to their `.env` file (don't commit!)
3. Run `python run.py`

## Advanced: Claude Integration

### In Claude Code / Claude Desktop

SMT automatically shows GitHub context:

```
When you ask Claude:
"Show me the auth changes in PR #42"

Claude sees:
├── Current branch: feature/auth
├── PR info: #42 - Add authentication
├── Author: alice
└── Graph context: relevant symbols

Claude can then:
✓ Analyze code in PR
✓ Check for conflicts
✓ Review with full context
```

## Troubleshooting

### "GitHub integration not configured"

```bash
# Check if token is set
echo $GITHUB_TOKEN

# If empty, set it:
export GITHUB_TOKEN=ghp_xxx
python run.py
```

### "gh: command not found"

Install GitHub CLI:

**Windows (with Homebrew):**
```bash
brew install gh
```

**Windows (with Winget):**
```bash
winget install GitHub.cli
```

**macOS:**
```bash
brew install gh
```

**Linux:**
```bash
sudo apt install gh
```

### "Database does not exist"

Run once to build:
```bash
python run.py
```

Then check:
```bash
python run.py graph --check
```

### Token shows wrong permissions

1. Go to: https://github.com/settings/tokens
2. Click on your token
3. Verify these are checked:
   - `repo` (all options)
   - `read:org`
4. If not, click "Update token" and add them

### Can't see PRs

```bash
# Check GitHub CLI authentication
gh auth status

# Should show:
# Logged in to github.com as [username]

# If not logged in:
gh auth login
```

## What SMT Tracks

With GitHub connected, SMT shows:

```
✓ Current git branch
✓ Is it a PR branch? (yes/no)
✓ PR number (if PR exists)
✓ PR title
✓ PR author
✓ All open PRs count
```

## Security Notes

**Never commit your token!**

```bash
# GOOD - token in environment
export GITHUB_TOKEN=ghp_xxx
python run.py

# GOOD - token in .env (gitignored)
# .env file (not committed)

# BAD - hardcoding token in run.py
# python run.py --token=ghp_xxx

# BAD - committing .env with token
git add .env    # NO! Will leak token
```

## Next Steps

1. ✅ Create GitHub token
2. ✅ Set GITHUB_TOKEN env var
3. ✅ Run `python run.py graph --check`
4. ✅ Verify PR info shows
5. ✅ Start using with team

Then SMT knows your PR context automatically!

## Quick Reference

| Command | What it shows |
|---------|--------------|
| `python run.py` | Start SMT (builds graph) |
| `python run.py graph --check` | Status + GitHub PR info |
| `gh auth status` | Check GitHub login |
| `gh pr list` | See all PRs in repo |
| `git branch` | Show current branch |
| `git checkout feature/xxx` | Switch branch |

## Complete Workflow

```bash
# Setup (one-time)
export GITHUB_TOKEN=ghp_xxx
docker-compose up -d neo4j

# Daily use
cd /path/to/repo
python run.py              # Auto-builds + loads GitHub info
python run.py graph --check  # See PR status

# When switching branches
git checkout feature/auth
python run.py graph --check  # Shows PR #42 info

# Push changes (as usual)
git add .
git commit -m "message"
git push origin feature/auth
```

Done! SMT is now connected to GitHub and tracks PR context automatically.
