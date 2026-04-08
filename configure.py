#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save-my-tokens Setup - Phase-gated ONE COMMAND

Sets up dependencies and Docker for Neo4j with verification at each step.
After this, use `smt` CLI for all graph operations.
"""

import sys
import subprocess
import time
import urllib.request
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src/ to path for cli_utils import
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from cli_utils import Colors, print_header, print_pass, print_fail, print_warn

try:
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------

def phase_prerequisites() -> bool:
    """Phase 1: Verify prerequisites (Python + Docker)."""
    print_header("Phase 1: Prerequisites")

    # Check Python >= 3.11
    print("  Python version...", end=" ", flush=True)
    if sys.version_info >= (3, 11):
        print(f"{Colors.GREEN}[OK]{Colors.RESET} {sys.version_info.major}.{sys.version_info.minor}")
    else:
        print_fail(f"Python {sys.version_info.major}.{sys.version_info.minor} (need 3.11+)")
        return False

    # Check docker-compose (HARD BLOCK)
    print("  docker-compose...", end=" ", flush=True)
    try:
        result = subprocess.run(
            ['docker-compose', '--version'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"{Colors.GREEN}[OK]{Colors.RESET} installed")
        else:
            print_fail("docker-compose error (try: docker-compose --version)")
            print("    Install: https://docs.docker.com/compose/install/")
            return False
    except FileNotFoundError:
        print_fail("docker-compose not found")
        print("    Install: https://docs.docker.com/compose/install/")
        return False

    return True


def phase_install_packages() -> bool:
    """Phase 2: Install Python packages with verification."""
    print_header("Phase 2: Package Installation")

    # Critical packages: must verify import after install
    critical = {
        'torch': 'torch',
        'neo4j': 'neo4j',
        'loguru': 'loguru',
        'pydantic': 'pydantic',
        'sentence-transformers': 'sentence_transformers',
    }

    # Non-critical: install best-effort
    non_critical = [
        'tree-sitter',
        'tree-sitter-python',
        'tree-sitter-typescript',
        'faiss-cpu',
        'numpy',
        'pydantic-settings',
        'gitpython',
        'python-dotenv',
        'tqdm',
        'requests',
        'rich',
    ]

    # Install torch first with CPU wheels
    if RICH_AVAILABLE:
        console = Console()
        with console.status("  Installing torch (CPU)..."):
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'torch', 'torchvision',
                 '--index-url', 'https://download.pytorch.org/whl/cpu', '-q'],
                capture_output=True,
                timeout=120
            )
    else:
        print("  torch (CPU)...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'torch', 'torchvision',
             '--index-url', 'https://download.pytorch.org/whl/cpu', '-q'],
            capture_output=True,
            timeout=120
        )

    if result.returncode == 0:
        # Verify import
        verify = subprocess.run(
            [sys.executable, '-c', 'import torch'],
            capture_output=True,
            timeout=10
        )
        if verify.returncode == 0:
            print_pass("torch")
        else:
            print_fail("import torch failed after install")
            return False
    else:
        print_fail("pip install torch failed")
        if result.stderr:
            print(f"    {result.stderr.decode()[:200]}")
        return False

    # Install critical packages
    console = Console() if RICH_AVAILABLE else None
    for pip_name, import_name in critical.items():
        if pip_name == 'torch':
            continue  # Already installed

        if RICH_AVAILABLE and console:
            with console.status(f"  Installing {pip_name}..."):
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', pip_name, '-q'],
                    capture_output=True,
                    timeout=60
                )
        else:
            print(f"  {pip_name}...", end=" ", flush=True)
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', pip_name, '-q'],
                capture_output=True,
                timeout=60
            )

        if result.returncode == 0:
            # Verify import
            verify = subprocess.run(
                [sys.executable, '-c', f'import {import_name}'],
                capture_output=True,
                timeout=10
            )
            if verify.returncode == 0:
                print_pass(pip_name)
            else:
                print_fail(f"import {import_name} failed after install")
                return False
        else:
            print_fail(f"pip install {pip_name} failed")
            return False

    # Install non-critical packages (best-effort)
    print()
    for pkg in non_critical:
        if RICH_AVAILABLE and console:
            with console.status(f"  Installing {pkg} (optional)..."):
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', pkg, '-q'],
                    capture_output=True,
                    timeout=60
                )
        else:
            print(f"  {pkg}...", end=" ", flush=True)
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', pkg, '-q'],
                capture_output=True,
                timeout=60
            )

        if result.returncode == 0:
            print_pass(pkg)
        else:
            print_warn(f"{pkg} (optional, continuing)")

    return True


def phase_smt_install() -> bool:
    """Phase 3: Install SMT itself in editable mode."""
    print_header("Phase 3: SMT Installation")

    print("  pip install -e . (editable)...", end=" ", flush=True)
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-e', '.', '-q'],
        capture_output=True,
        cwd=Path.cwd(),
        timeout=60
    )
    if result.returncode == 0:
        print(f"{Colors.GREEN}[OK]{Colors.RESET}")
    else:
        print_fail("pip install -e . failed")
        if result.stderr:
            print(f"    {result.stderr.decode()[:200]}")
        return False

    # Verify smt CLI is accessible
    print("  smt --help...", end=" ", flush=True)
    result = subprocess.run(
        ['smt', '--help'],
        capture_output=True,
        timeout=10
    )
    if result.returncode == 0:
        print(f"{Colors.GREEN}[OK]{Colors.RESET}")
    else:
        print_warn("smt not on PATH — may need to restart terminal or use: python -m src.smt_cli")

    return True


def phase_env_setup() -> bool:
    """Phase 4: Create .env from .env.example if missing."""
    print_header("Phase 4: Environment Setup")

    env_file = Path('.env')
    env_example = Path('.env.example')

    if env_file.exists():
        print_pass(".env file already exists")
        return True

    if not env_example.exists():
        print_fail(".env.example not found — cannot create .env")
        return False

    # Copy .env.example to .env
    content = env_example.read_text(encoding='utf-8')

    # Optionally prompt for Neo4j password
    print()
    print("  Neo4j password setup:")
    print("    Default: 'password'")
    print("    Press Enter to use default, or type a new password")
    try:
        password = input("    Password: ").strip() or 'password'
    except (EOFError, KeyboardInterrupt):
        password = 'password'
        print("    (using default: password)")

    # Replace password if not default
    content = content.replace('NEO4J_PASSWORD=password', f'NEO4J_PASSWORD={password}')

    env_file.write_text(content, encoding='utf-8')
    print_pass(".env created")

    return True


def phase_verify() -> bool:
    """Phase 5: Verify all critical imports and files."""
    print_header("Phase 5: Verification")

    all_ok = True

    # Python version
    print_pass(f"Python {sys.version_info.major}.{sys.version_info.minor}")

    # .env exists
    if Path('.env').exists():
        print_pass(".env present")
    else:
        print_warn(".env missing (create manually or re-run Phase 4)")
        all_ok = False

    # docker-compose.yml exists
    if Path('docker-compose.yml').exists():
        print_pass("docker-compose.yml found")
    else:
        print_fail("docker-compose.yml missing")
        all_ok = False

    # src/ exists (optional but recommended)
    if Path('src').exists():
        print_pass("src/ directory found")
    else:
        print_warn("src/ not found (optional, use --dir flag with smt build)")

    # Verify critical imports
    print()
    for module in ['neo4j', 'loguru', 'sentence_transformers', 'pydantic', 'torch']:
        result = subprocess.run(
            [sys.executable, '-c', f'import {module}'],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            print_pass(f"import {module}")
        else:
            print_fail(f"import {module}")
            all_ok = False

    return all_ok


def phase_docker_start() -> bool:
    """Phase 6: Start Neo4j container and wait for readiness."""
    print_header("Phase 6: Docker / Neo4j")

    # Launch Docker
    print("  Starting Neo4j container...", end=" ", flush=True)
    result = subprocess.run(
        ['docker-compose', 'up', '-d', 'neo4j'],
        capture_output=True,
        timeout=30,
        cwd=Path.cwd()
    )
    if result.returncode != 0:
        print_fail("docker-compose up failed")
        if result.stderr:
            print(f"    {result.stderr.decode()[:200]}")
        return False
    print_pass("container started")

    # Wait for Neo4j (exponential backoff, spinner)
    max_wait = 60
    elapsed = 0
    attempt = 0
    neo4j_ready = False

    if RICH_AVAILABLE:
        console = Console()
        with console.status("  Waiting for Neo4j to be ready..."):
            while elapsed < max_wait:
                try:
                    urllib.request.urlopen('http://localhost:7474', timeout=2)
                    neo4j_ready = True
                    break
                except Exception:
                    attempt += 1
                    wait = min(0.5 * (2 ** (attempt - 1)), 8)
                    elapsed += wait
                    time.sleep(wait)
    else:
        print("  Waiting for Neo4j to be ready...", end=" ", flush=True)
        while elapsed < max_wait:
            try:
                urllib.request.urlopen('http://localhost:7474', timeout=2)
                neo4j_ready = True
                break
            except Exception:
                attempt += 1
                wait = min(0.5 * (2 ** (attempt - 1)), 8)
                elapsed += wait
                time.sleep(wait)
        if neo4j_ready:
            print()

    if neo4j_ready:
        print_pass("Neo4j reachable (http://localhost:7474)")
    else:
        print_fail(f"Neo4j did not become ready in {max_wait}s")
        print("    Check: docker-compose logs neo4j")
        return False

    return True


def phase_build_graph() -> bool:
    """Phase 7: Build the initial code graph."""
    print_header("Phase 7: Build Graph")

    # Determine source directory
    src_dir = Path('src') if Path('src').exists() else Path('.')
    print(f"  Source dir: {src_dir.resolve()}\n")

    result = subprocess.run(
        ['smt', 'build', '--dir', str(src_dir)],
        timeout=300
    )
    if result.returncode != 0:
        print_fail("Graph build failed")
        return False

    print_pass("Graph built successfully")
    return True


def run_setup():
    """Orchestrate all phases in sequence."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}SAVE-MY-TOKENS SETUP{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")

    phases = [
        ("Prerequisites", phase_prerequisites),
        ("Package Installation", phase_install_packages),
        ("SMT Installation", phase_smt_install),
        ("Environment Setup", phase_env_setup),
        ("Verification", phase_verify),
        ("Docker / Neo4j", phase_docker_start),
        ("Build Graph", phase_build_graph),
    ]

    results = []
    for name, fn in phases:
        try:
            ok = fn()
        except Exception as e:
            print_fail(f"Unexpected error: {e}")
            ok = False

        results.append((name, ok))

        if not ok:
            print(f"\n{Colors.RED}{Colors.BOLD}BLOCKED at {name}.{Colors.RESET}")
            print("Fix the issue above and re-run: python configure.py\n")
            return False

    # Summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] All 7 phases passed!{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

    print("All done! Neo4j is running and your code graph is ready.\n")
    print("Next steps:\n")
    print("  • Check graph status:")
    print("    smt status\n")
    print("  • Query the graph:")
    print("    smt definition <symbol>\n")
    print("  • See available commands:")
    print("    smt --help\n")

    return True


if __name__ == '__main__':
    success = run_setup()
    sys.exit(0 if success else 1)
