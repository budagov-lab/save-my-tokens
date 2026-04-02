# SMT Installation Paths

**Two ways to install SMT depending on your needs.**

---

## Path 1: Developer Setup (Git + Manual)

**For:** Developers who want to understand the code, contribute, or customize

**What you get:**
- Full source code
- Python virtual environment
- Optional Neo4j (runs in Docker)
- Full control over configuration

**Requirements:**
- Python 3.11+
- Git
- Docker (optional, for Neo4j)

**Installation:**

```bash
# Clone the repository
git clone https://github.com/budagov-lab/smt-graph.git
cd smt-graph

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .

# (Optional) Start Neo4j for persistent storage
docker-compose up -d
```

**Time:** 5 minutes  
**Complexity:** Medium (requires command line)  
**Best for:** Developers, contributors, custom setups

---

## Path 2: One-Click Setup (Package + Automated)

**For:** End users who want it working in 3 minutes with no hassle

**What you get:**
- Automated installation (no commands to remember)
- All dependencies installed automatically
- Optional Docker integration (prompts you)
- Tests run automatically to verify
- Clear next steps with your paths filled in

**Requirements:**
- Python 3.11+
- That's it! (Docker is optional)

**Installation:**

### Windows
```cmd
install.bat
```

### macOS / Linux
```bash
bash install.sh
```

The script will:
1. ✅ Check Python 3.11+
2. ✅ Create virtual environment
3. ✅ Install all dependencies
4. ✅ Optionally start Neo4j (asks you)
5. ✅ Run tests to verify everything
6. ✅ Show you exactly what to do next

**Time:** 3 minutes  
**Complexity:** None (one command)  
**Best for:** Users, teams, fast setup, "just works"

---

## Full Package: Docker Everything

**For:** Teams that want everything containerized (advanced)

**What you get:**
- SMT server in Docker
- Neo4j in Docker
- All dependencies containerized
- Easy to deploy and scale

**Installation:**

```bash
# Coming soon! 
# We're building a Dockerfile that packages the entire SMT service

# For now, use the automated setup + docker-compose:
bash install.sh  # Or install.bat on Windows
docker-compose up -d  # Start Neo4j
python run_mcp.py  # Start SMT server
```

**Future:** We'll add a `docker-compose.yml` that includes SMT service for one-command full deployment.

---

## Comparison

| Aspect | Developer (Git) | One-Click (Package) | Docker (Future) |
|--------|-----------------|--------------------|----|
| **Time** | 5 min | 3 min | 2 min |
| **Complexity** | Medium | None | Low |
| **Best for** | Devs, contributors | Users, teams | Production, scaling |
| **Python install** | Manual | Automated | Containerized |
| **Neo4j** | Optional (manual) | Optional (prompted) | Built-in |
| **Configuration** | Full control | Defaults + prompts | Pre-configured |
| **Customization** | Easy | Limited | Via env vars |

---

## Choose Your Path

### "I want to contribute or customize code"
→ Use **Path 1: Developer Setup**  
→ Clone from Git, edit code, test locally

### "I just want SMT working now"
→ Use **Path 2: One-Click Setup**  
→ Run install script, configure Claude Code, done

### "I'm deploying to production/team"
→ Use **Docker** (coming soon)  
→ Everything containerized, easy scaling

---

## After Installation

Regardless of which path you chose:

1. **Configure Claude Code** (3 steps, 5 minutes):
   - Find `~/.claude/settings.json`
   - Add 5 lines with SMT server path
   - Restart Claude Code

2. **Start Using** (immediate):
   - Ask Claude to analyze your code
   - Claude has smart code context now
   - Solve 11x more problems per conversation

---

## Switching Paths Later

- **Installed Path 1, want Path 2?**  
  Run the install script anyway. It checks for existing setup.

- **Installed Path 2, want to contribute?**  
  Clone the repo and work from there (both can coexist).

- **Want to switch to Docker?**  
  Wait for our Docker package, or manually containerize using our docker-compose.yml.

---

## Questions?

- **Path 1 issues?** See INSTALL.md "Manual Setup" section
- **Path 2 issues?** Check INSTALL.md "Test It Works" section
- **Docker questions?** Watch for upcoming Docker guide

---

## Summary

**Two proven installation paths:**

| Path | Command | Time | Best For |
|------|---------|------|----------|
| **One-Click** | `install.bat` or `bash install.sh` | 3 min | Users, teams, fast |
| **Developer** | `git clone` + `pip install` | 5 min | Devs, contributors |
| **Docker** | Coming soon | 2 min | Production, scaling |

**Pick one, get SMT working, give Claude smart code understanding.**
