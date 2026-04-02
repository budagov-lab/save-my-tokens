#!/usr/bin/env python3
"""
save-my-tokens Setup - ONE COMMAND

User runs:
    python setup.py

That's it. Everything else is automatic.
"""

import sys
import json
import subprocess
from pathlib import Path

def run_setup():
    """Run complete setup."""
    project_root = Path(__file__).parent
    
    print("\n" + "="*70)
    print("save-my-tokens (SMT) - ONE-COMMAND SETUP")
    print("="*70 + "\n")
    
    # Phase 0: Install packages
    print("[Phase 0] Installing Required Packages")
    print("-" * 70)
    
    core_packages = [
        'loguru',
        'neo4j',
        'tree-sitter',
        'mcp',
        'fastapi',
    ]
    
    for package in core_packages:
        print(f"  Installing {package}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package, '-q'],
            capture_output=True
        )
        print("[OK]" if result.returncode == 0 else "[WARN]")
    
    print()
    
    # Phase 1: Check prerequisites
    print("[Phase 1] Checking Prerequisites")
    print("-" * 70)
    
    # Check Neo4j
    print("  Checking Neo4j running...", end=" ", flush=True)
    try:
        result = subprocess.run(['curl', '-s', 'http://localhost:7474'], 
                              capture_output=True, timeout=2)
        print("[OK]" if result.returncode == 0 else "[FAIL]")
        if result.returncode != 0:
            print("\nERROR: Neo4j is not running!")
            print("Start with: docker-compose up -d neo4j\n")
            return False
    except:
        print("[FAIL]")
        print("\nERROR: Neo4j not accessible!")
        print("Start with: docker-compose up -d neo4j\n")
        return False
    
    # Check Python
    print("  Checking Python 3.10+...", end=" ", flush=True)
    if sys.version_info >= (3, 10):
        print("[OK]")
    else:
        print("[FAIL]")
        print(f"\nERROR: Python {sys.version_info.major}.{sys.version_info.minor} (need 3.10+)\n")
        return False
    
    print()
    
    # Phase 2: Build graph
    print("[Phase 2] Building Code Graph")
    print("-" * 70)
    
    print("  Checking if graph needs building...", end=" ", flush=True)
    try:
        from src.graph.neo4j_client import Neo4jClient
        client = Neo4jClient()
        stats = client.get_stats()
        client.close()
        
        if stats['node_count'] > 100:
            print(f"[OK] ({stats['node_count']} nodes already indexed)")
        else:
            print("[BUILD NEEDED]")
            print("  Building graph from source...", end=" ", flush=True)
            result = subprocess.run(
                [sys.executable, 'build_graph.py'],
                cwd=project_root,
                capture_output=True,
                timeout=300
            )
            print("[OK]" if result.returncode == 0 else "[FAIL]")
            if result.returncode != 0:
                print("  Try: python build_graph.py --check")
    except Exception as e:
        print(f"[ERROR] {e}")
    
    print()
    
    # Phase 3: Configure MCP
    print("[Phase 3] Configuring MCP")
    print("-" * 70)
    
    print("  Creating .mcp.json...", end=" ", flush=True)
    try:
        mcp_config = {
            "mcpServers": {
                "smt": {
                    "command": "python",
                    "args": [str(project_root / "run.py")]
                }
            }
        }
        mcp_file = project_root / '.mcp.json'
        with open(mcp_file, 'w') as f:
            json.dump(mcp_config, f, indent=2)
        print("[OK]")
    except Exception as e:
        print(f"[FAIL] {e}")
    
    print("  Creating workspace config...", end=" ", flush=True)
    try:
        workspace_dir = project_root / '.claude'
        workspace_dir.mkdir(exist_ok=True)
        
        workspace_config = {
            "mcp_enabled": True,
            "graph_auto_sync": True,
            "graph_base_path": "src",
            "neo4j_uri": "bolt://localhost:7687"
        }
        
        workspace_file = workspace_dir / 'workspace.json'
        with open(workspace_file, 'w') as f:
            json.dump(workspace_config, f, indent=2)
        print("[OK]")
    except Exception as e:
        print(f"[FAIL] {e}")
    
    print()
    
    # Success!
    print("="*70)
    print("SETUP COMPLETE!")
    print("="*70)
    print()
    print("What's next:")
    print("  1. Start MCP server: python run.py")
    print("  2. Open Claude Code with this project folder")
    print("  3. Ask Claude about your code naturally")
    print()
    print("Claude will automatically use SMT tools.")
    print()
    
    return True

if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
