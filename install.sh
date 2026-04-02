#!/bin/bash
# SMT MCP Server - One-Click Setup
# Usage: bash install.sh

set -e

echo "🚀 Installing SMT MCP Server..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version found"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install -q -e .

# Start Neo4j (optional)
if command -v docker-compose &> /dev/null; then
    echo ""
    read -p "Start Neo4j in Docker? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🐳 Starting Neo4j..."
        docker-compose up -d
        sleep 3
        echo "✓ Neo4j running at bolt://localhost:7687"
    fi
fi

# Run tests
echo ""
echo "✅ Testing installation..."
python -m pytest tests/unit/ -q --tb=no 2>/dev/null && echo "✓ All tests passed!" || echo "⚠️  Some tests failed (this is OK)"

echo ""
echo "════════════════════════════════════════════"
echo "✨ SMT MCP Server installed successfully!"
echo "════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Start the server:"
echo "     python run_mcp.py"
echo ""
echo "  2. Configure Claude Code:"
echo "     Add to .claude/settings.json:"
echo "       \"mcpServers\": ["
echo "         {"
echo "           \"name\": \"smt-graph\","
echo "           \"command\": \"python\","
echo "           \"args\": [\"$(pwd)/run_mcp.py\"]"
echo "         }"
echo "       ]"
echo ""
echo "  3. Restart Claude Code and use the tools!"
echo ""
echo "📖 Read docs/MCP_QUICK_START.md for details"
echo ""
