# 🚀 SMT MCP Server - Installation

**Get started in 3 minutes. One command. Done.**

---

## Quick Install

### Windows
```cmd
install.bat
```

### macOS / Linux
```bash
bash install.sh
```

That's it! The script will:
1. ✅ Check Python (3.11+)
2. ✅ Create virtual environment
3. ✅ Install dependencies
4. ✅ Optionally start Neo4j (Docker)
5. ✅ Run tests to verify everything works

---

## Manual Setup (if scripts don't work)

```bash
# 1. Clone
git clone https://github.com/budagov-lab/smt-graph.git
cd smt-graph

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate  # Windows

# 3. Install
pip install -e .

# 4. (Optional) Start Neo4j
docker-compose up -d

# 5. Done!
```

---

## Connect to Claude Code

### Step 1: Find your settings file

**macOS:**
```
~/Library/Application Support/Claude/.claude/settings.json
```

**Windows:**
```
%APPDATA%\Claude\.claude\settings.json
```

**Linux:**
```
~/.claude/settings.json
```

### Step 2: Add this to settings.json

```json
{
  "mcpServers": [
    {
      "name": "smt-graph",
      "command": "python",
      "args": ["/path/to/smt-graph/run_mcp.py"]
    }
  ]
}
```

Replace `/path/to/smt-graph` with your actual path.

### Step 3: Restart Claude Code

Close and restart Claude Code. Done! 🎉

---

## Test It Works

In Claude Code, you should see a hammer icon 🔨 when the MCP server connects.

Try asking:
```
"Analyze the main.py file - show me the context for the main() function"
```

Claude will now query the graph instead of loading the whole file!

---

## What if something breaks?

### "Python not found"
Install Python 3.11+ from https://python.org

### "Docker not found"
That's OK - the server works without Neo4j (offline mode).
Install Docker if you want persistent storage: https://docker.com

### "MCP Server not appearing in Claude Code"
1. Make sure path is absolute (not relative)
2. Restart Claude Code
3. Check the settings file exists

### "Tests failed"
This is OK - the server still works. 
Run it: `python run_mcp.py`

---

## What's Next?

Now that it's installed:

1. **Read:** [docs/MCP_EXAMPLES.md](docs/MCP_EXAMPLES.md) - See 6 real examples
2. **Use:** Start asking Claude Code about your code!
3. **Reference:** [docs/MCP_CHEATSHEET.md](docs/MCP_CHEATSHEET.md) - Keep handy

---

## One-Line Start

After installation, just run:

```bash
python run_mcp.py
```

That's the server. Claude Code will connect automatically.

---

**Questions?** Check [docs/MCP_QUICK_START.md](docs/MCP_QUICK_START.md) for detailed troubleshooting.
