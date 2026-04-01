#!/usr/bin/env python
"""MCP server entry point for syt-graph.

Usage (stdio transport for agent subprocess):
    python run_mcp.py

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "syt-graph": {
          "command": "python",
          "args": ["/path/to/SYT/run_mcp.py"]
        }
      }
    }
"""
import sys
from pathlib import Path

# Ensure src is on the Python path when invoked from project root
sys.path.insert(0, str(Path(__file__).parent))

from src.mcp_server.entrypoint import main

if __name__ == "__main__":
    main()
