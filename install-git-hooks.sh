#!/bin/bash
# Install save-my-tokens git hooks for automatic graph syncing

echo "Installing git hooks for save-my-tokens..."

# Make hooks executable
chmod +x .git/hooks/post-commit
chmod +x .git/hooks/post-push

echo "[OK] post-commit hook installed"
echo "[OK] post-push hook installed"
echo ""
echo "Git hooks will now:"
echo "  1. Auto-sync graph after: git commit"
echo "  2. Auto-sync graph after: git push"
echo ""
echo "Requirements:"
echo "  - Neo4j must be running: docker-compose up -d neo4j"
echo "  - MCP server must be running: python run.py"
echo ""
echo "To uninstall hooks:"
echo "  rm .git/hooks/post-commit .git/hooks/post-push"
echo ""
echo "Graph syncing configured!"
