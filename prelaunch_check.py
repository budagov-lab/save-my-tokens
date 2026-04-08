#!/usr/bin/env python3
"""
Pre-launch validation for save-my-tokens.

Run this before configure.py or run.py to verify the environment is ready.
No dependencies required - uses only Python standard library.

Usage:
    python prelaunch_check.py
"""

import sys
import json
import subprocess
from pathlib import Path

# Add src/ to path for cli_utils import
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from cli_utils import Colors, print_header, print_pass, print_fail, print_warn


def check_python_version():
    """Check Python version is 3.10+."""
    print_header("Python Version")
    if sys.version_info >= (3, 10):
        print_pass(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return True
    else:
        print_fail(f"Python {sys.version_info.major}.{sys.version_info.minor} (need 3.10+)")
        return False


def check_file_syntax():
    """Check Python files have valid syntax."""
    print_header("File Syntax")
    files_to_check = ["run.py", "configure.py"]
    all_valid = True

    for file in files_to_check:
        if not Path(file).exists():
            print_warn(f"{file} not found")
            continue

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", file],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print_pass(f"{file} syntax valid")
        else:
            print_fail(f"{file} has syntax errors")
            all_valid = False

    return all_valid


def check_project_structure():
    """Check essential project directories exist."""
    print_header("Project Structure")
    required = {
        "src/": "Source code",
        "src/parsers/": "Parser modules",
        "src/graph/": "Graph modules",
        ".claude/": "Claude configuration",
        "tests/": "Test suite",
    }

    all_exist = True
    for path, desc in required.items():
        if Path(path).exists():
            print_pass(f"{desc}: {path}")
        else:
            print_fail(f"{desc}: {path} (missing)")
            all_exist = False

    return all_exist


def check_config_files():
    """Check Claude Code config files exist."""
    print_header("Claude Code Configuration")
    required_files = {
        ".claude/settings.json": "Claude Code settings",
        ".claude/workspace.json": "Workspace config",
    }

    all_exist = True
    for file, desc in required_files.items():
        if Path(file).exists():
            print_pass(f"{desc}: {file}")
        else:
            print_warn(f"{desc}: {file} (will be auto-created by run.py)")

    return True  # Don't fail if missing, they're auto-created


def check_dependencies():
    """Check optional dependencies."""
    print_header("Optional Dependencies")
    optional = {
        "loguru": "Logging",
        "neo4j": "Neo4j driver",
        "tree_sitter": "Tree-sitter parser",
        "sentence_transformers": "Embeddings",
        "pydantic": "Data validation",
    }

    installed = 0
    for module, desc in optional.items():
        try:
            __import__(module)
            print_pass(f"{desc}: {module}")
            installed += 1
        except ImportError:
            print_warn(f"{desc}: {module} (not installed - will install during setup)")

    return installed > 0


def check_git_repo():
    """Check git repository is valid."""
    print_header("Git Repository")

    # Check .git exists
    if not Path(".git").exists():
        print_fail(".git directory not found (not a git repo)")
        return False

    print_pass(".git directory exists")

    # Check git status
    try:
        result = subprocess.run(
            ["git", "config", "--list"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print_pass("git config is valid")
        else:
            print_fail("git config is invalid")
            return False
    except FileNotFoundError:
        print_warn("git command not found (optional)")
        return True

    return True


def check_documentation():
    """Check essential documentation exists."""
    print_header("Documentation")
    docs = {
        "README.md": "Project README",
        "CLAUDE.md": "Claude Code guide",
        "docker-compose.yml": "Docker configuration",
    }

    all_exist = True
    for file, desc in docs.items():
        if Path(file).exists():
            print_pass(f"{desc}: {file}")
        else:
            print_fail(f"{desc}: {file} (missing)")
            all_exist = False

    return all_exist


def check_docker():
    """Check Docker is installed (optional)."""
    print_header("Docker (Optional)")
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.decode().strip()
            print_pass(f"docker-compose installed: {version}")
            return True
        else:
            print_warn("docker-compose not found (required for Neo4j)")
            print("  Install from: https://docs.docker.com/compose/install/")
            return False
    except FileNotFoundError:
        print_warn("docker-compose not found (required for Neo4j)")
        print("  Install from: https://docs.docker.com/compose/install/")
        return False


def main():
    """Run all pre-launch checks."""
    print(f"\n{Colors.BOLD}save-my-tokens Pre-Launch Check{Colors.RESET}")
    print(f"{Colors.BOLD}================================{Colors.RESET}")

    checks = [
        ("Python Version", check_python_version),
        ("File Syntax", check_file_syntax),
        ("Project Structure", check_project_structure),
        ("Configuration Files", check_config_files),
        ("Optional Dependencies", check_dependencies),
        ("Git Repository", check_git_repo),
        ("Documentation", check_documentation),
        ("Docker", check_docker),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Error during {name}: {e}")
            results.append((name, False))

    # Summary
    print_header("Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        if result:
            print_pass(name)
        else:
            print_fail(name)

    print(f"\n{Colors.BOLD}Result: {passed}/{total} checks passed{Colors.RESET}\n")

    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}[OK] Ready for setup!{Colors.RESET}")
        print("Next steps:")
        print("  1. python configure.py")
        print("  2. python run.py")
        print("")
        return 0
    else:
        print(f"{Colors.YELLOW}{Colors.BOLD}[WARN] Some checks failed or skipped{Colors.RESET}")
        print("You can still run configure.py, but some features may not work.")
        print("")
        return 1


if __name__ == "__main__":
    sys.exit(main())
