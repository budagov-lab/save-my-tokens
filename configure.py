#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save-my-tokens Setup - ONE COMMAND

Sets up dependencies and Docker for Neo4j.
After this, use `smt` CLI for all graph operations.
"""

import sys
import subprocess
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def check_prerequisites() -> bool:
    print("[Checking Prerequisites]")
    print("-" * 60)

    print("  Python version...", end=" ", flush=True)
    if sys.version_info >= (3, 10):
        print(f"[OK] {sys.version_info.major}.{sys.version_info.minor}")
    else:
        print(f"[FAIL] Need 3.10+, have {sys.version_info.major}.{sys.version_info.minor}")
        return False

    print("  Docker...", end=" ", flush=True)
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, timeout=3)
        print("[OK]" if result.returncode == 0 else "[WARN - needed for Neo4j]")
    except FileNotFoundError:
        print("[WARN - needed for Neo4j]")

    print()
    return True


def install_packages() -> bool:
    print("[Installing Packages]")
    print("-" * 60)

    # Install torch/torchvision first with specific versions to avoid compatibility issues
    # SentenceTransformers depends on these and they must be compatible
    print("  torch (CPU, compatible version)...", end=" ", flush=True)
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cpu', '-q'],
        capture_output=True
    )
    print("[OK]" if result.returncode == 0 else "[WARN]")

    packages = [
        'loguru',
        'neo4j',
        'tree-sitter',
        'tree-sitter-python',
        'tree-sitter-typescript',
        'sentence-transformers',
        'faiss-cpu',
        'numpy',
        'pydantic',
        'pydantic-settings',
        'gitpython',
        'python-dotenv',
        'tqdm',
        'requests',
        'rich',
    ]

    for package in packages:
        print(f"  {package}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package, '-q'],
            capture_output=True
        )
        print("[OK]" if result.returncode == 0 else "[WARN]")

    # Install SMT itself in editable mode so 'smt' command works globally
    print("  smt (editable install)...", end=" ", flush=True)
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-e', '.', '-q'],
        capture_output=True,
        cwd=Path.cwd()
    )
    print("[OK]" if result.returncode == 0 else "[WARN]")

    print()
    return True


def run_setup():
    project_root = Path.cwd()

    print("\n" + "=" * 60)
    print("  SAVE-MY-TOKENS SETUP")
    print("=" * 60)
    print()

    if not check_prerequisites():
        return False

    if not install_packages():
        return False

    print("=" * 60)
    print("[SUCCESS] Setup complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print()
    print("  1. Start Neo4j:")
    print("     smt docker up")
    print()
    print("  2. Setup your project:")
    print("     smt setup --dir /path/to/your/project")
    print()
    print("  3. Build the graph:")
    print("     smt build")
    print()
    print("  4. Query (from anywhere):")
    print("     smt status")
    print("     smt search \"your query\"")
    print("     smt context MyFunction")
    print()
    return True


if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
