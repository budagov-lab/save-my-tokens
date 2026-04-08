#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save-my-tokens Setup — One-Command Installation

Handles all setup steps:
1. Check Python 3.11+
2. Check docker-compose
3. Create .env from .env.example
4. Install packages (pip install -e ".[full]")
5. Start Neo4j container

After this, user can run: smt build
"""

import sys
import subprocess
import time
import urllib.request
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from cli_utils import Colors, print_header, print_pass, print_fail, print_warn

try:
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def step_check_python() -> bool:
    """Step 1: Verify Python 3.11+"""
    print_header("Step 1: Check Python 3.11+")

    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"  Python {version}...", end=" ", flush=True)

    if sys.version_info >= (3, 11):
        print_pass(version)
        return True
    else:
        print_fail(version)
        print(f"    {Colors.RED}ERROR: Python {version} found, but 3.11+ required.{Colors.RESET}")
        return False


def step_check_docker() -> bool:
    """Step 2: Verify docker-compose"""
    print_header("Step 2: Check docker-compose")

    print("  docker-compose...", end=" ", flush=True)
    try:
        result = subprocess.run(
            ['docker-compose', '--version'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print_pass("installed")
            return True
    except FileNotFoundError:
        pass

    print_fail("not found")
    print("    Install: https://docs.docker.com/compose/install/")
    return False


def step_create_env() -> bool:
    """Step 3: Create .env from .env.example"""
    print_header("Step 3: Environment Setup")

    project_dir = Path(__file__).parent
    env_file = project_dir / '.env'
    env_example = project_dir / '.env.example'

    if env_file.exists():
        print_pass(".env already exists")
        return True

    if not env_example.exists():
        print_fail(".env.example not found")
        return False

    # Copy template
    content = env_example.read_text(encoding='utf-8')

    # Prompt for Neo4j password
    print()
    print("  Neo4j password setup:")
    print("    Default: 'password'")
    print("    Press Enter to use default, or type a new password")
    try:
        password = input("    Password: ").strip() or 'password'
    except (EOFError, KeyboardInterrupt):
        password = 'password'
        print("    (using default)")

    content = content.replace('NEO4J_PASSWORD=password', f'NEO4J_PASSWORD={password}')
    env_file.write_text(content, encoding='utf-8')
    print_pass(".env created")

    return True


def step_install_packages() -> bool:
    """Step 4: Install packages with pip install -e ".[full]" """
    print_header("Step 4: Install Packages")

    project_dir = Path(__file__).parent

    print("  Running: pip install -e '.[full]'")
    print("  (You will see download progress, compilation status, etc.)\n")

    # Run pip with FULL OUTPUT visible to user
    # No capture, no quiet mode — everything is shown in real-time
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-e', '.[full]'],
        cwd=project_dir,
    )

    print()  # Blank line after pip

    if result.returncode != 0:
        print_fail("pip install failed")
        return False

    print_pass("Packages installed")

    # Verify smt command is available
    print()
    print("  Verifying smt command...", end=" ", flush=True)
    verify = subprocess.run(
        ['smt', '--help'],
        capture_output=True,
        timeout=10
    )
    if verify.returncode == 0:
        print_pass("accessible")
    else:
        print_warn("smt command may not be on PATH yet")
        print("    Restart terminal and try: smt --help")

    return True


def step_start_neo4j() -> bool:
    """Step 5: Start Neo4j container"""
    print_header("Step 5: Start Neo4j")

    project_dir = Path(__file__).parent

    print("  Starting docker-compose up -d neo4j...", end=" ", flush=True)
    result = subprocess.run(
        ['docker-compose', 'up', '-d', 'neo4j'],
        cwd=project_dir,
        capture_output=True,
        timeout=30
    )
    if result.returncode != 0:
        print_fail("failed")
        if result.stderr:
            print(f"    {result.stderr.decode()[:200]}")
        return False
    print_pass("container started")

    # Wait for Neo4j readiness
    print("  Waiting for Neo4j to be ready...", end=" ", flush=True)
    max_wait = 60
    elapsed = 0
    neo4j_ok = False

    for attempt in range(max_wait):
        try:
            urllib.request.urlopen('http://localhost:7474', timeout=2)
            neo4j_ok = True
            break
        except Exception:
            elapsed = attempt + 1
            time.sleep(1)

    if neo4j_ok:
        print_pass(f"ready ({elapsed}s)")
    else:
        print_fail(f"not ready after {max_wait}s")
        print("    Check: docker-compose logs neo4j")
        return False

    return True


def main() -> bool:
    """Run all setup steps in sequence."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}SAVE-MY-TOKENS SETUP{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

    steps = [
        ("Python 3.11+", step_check_python),
        ("docker-compose", step_check_docker),
        ("Environment", step_create_env),
        ("Packages", step_install_packages),
        ("Neo4j", step_start_neo4j),
    ]

    for name, fn in steps:
        try:
            ok = fn()
        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            ok = False

        if not ok:
            print(f"\n{Colors.RED}{Colors.BOLD}BLOCKED at {name}{Colors.RESET}")
            print("Fix the issue above and re-run: python setup.py\n")
            return False

    # Success
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}✓ SETUP COMPLETE!{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

    print("Neo4j is running and ready. Next steps:\n")
    print("  1. Build your code graph:")
    print("     smt build\n")
    print("  2. Check graph status:")
    print("     smt status\n")
    print("  3. Query your code:")
    print("     smt definition <symbol>")
    print("     smt context <symbol> --depth 2\n")
    print("  4. See all commands:")
    print("     smt --help\n")

    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
