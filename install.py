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
import shutil
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
    print("  NOTE: This installs torch (~2GB). It will look stuck for several minutes.")
    print("  Do NOT cancel — let it finish.\n")

    # Run pip with output visible to user. stdout.flush() prevents interleaving
    # with parent-process buffered output on Windows.
    sys.stdout.flush()
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

    # Tear down any stale containers (preserves named volumes / data)
    # This fixes the "Neo4j already running (pid:X)" error from stale PID files
    print("  Removing stale containers...", end=" ", flush=True)
    subprocess.run(
        ['docker-compose', 'down'],
        cwd=project_dir,
        capture_output=True,
        timeout=30
    )
    print_pass("done")

    print("  Starting Neo4j container...", end=" ", flush=True)
    result = subprocess.run(
        ['docker-compose', 'up', '-d', 'neo4j'],
        cwd=project_dir,
        capture_output=True,
        timeout=30
    )
    if result.returncode != 0:
        print_fail("failed")
        stderr = result.stderr.decode(errors='replace')
        if stderr:
            print(f"    {stderr[:300]}")
        return False
    print_pass("container started")

    # Wait for Neo4j HTTP endpoint — first boot can take 90+ seconds
    print("  Waiting for Neo4j to be ready (up to 120s)...", end=" ", flush=True)
    max_wait = 120
    neo4j_ok = False

    for elapsed in range(max_wait):
        try:
            urllib.request.urlopen('http://localhost:7474', timeout=2)
            neo4j_ok = True
            break
        except Exception:
            time.sleep(1)

    if neo4j_ok:
        print_pass(f"ready ({elapsed}s)")
    else:
        print_fail(f"not ready after {max_wait}s")
        print("    Check: docker-compose logs neo4j")
        return False

    return True


def _venv_python(venv_dir: Path) -> Path:
    """Return path to python executable inside a venv."""
    if sys.platform == 'win32':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'


def _remove_broken_venv(venv_dir: Path) -> None:
    """Delete a broken venv directory so the next run starts clean."""
    print(f"  Removing broken venv at {venv_dir} ...")
    shutil.rmtree(venv_dir, ignore_errors=True)
    if venv_dir.exists():
        print_warn("Could not remove venv automatically. Delete it manually:")
        print(f"    rmdir /s /q venv   (Windows)")
        print(f"    rm -rf venv        (Mac/Linux)")


def step_setup_venv() -> bool:
    """Step 0: Create virtual environment, bootstrap pip, then self-reinvoke."""
    print_header("Step 0: Virtual Environment")

    project_dir = Path(__file__).parent
    venv_dir = project_dir / 'venv'

    # --- Already exists: check health, reinvoke or recreate ---
    if venv_dir.exists():
        python = _venv_python(venv_dir)
        healthy = False
        if python.exists():
            pip_check = subprocess.run(
                [str(python), '-m', 'pip', '--version'],
                capture_output=True, timeout=10
            )
            healthy = pip_check.returncode == 0

        if healthy:
            # Healthy venv — reinvoke setup inside it (transparent to user)
            print_pass("venv exists and has pip — continuing inside it...")
            sys.stdout.flush()
            result = subprocess.run([str(python), __file__])
            sys.exit(result.returncode)

        # Broken or incomplete venv — delete and fall through to create fresh
        print_warn("venv exists but is broken — recreating...")
        _remove_broken_venv(venv_dir)
        if venv_dir.exists():
            print_fail("Could not remove broken venv. Delete it manually and re-run:")
            print("    rmdir /s /q venv   (Windows)")
            print("    rm -rf venv        (Mac/Linux)")
            return False
        print_pass("broken venv removed")

    # --- Create bare venv (no --upgrade-deps: avoids silent network hang) ---
    print(f"  Creating virtual environment at {venv_dir}")
    print("  (Running: python -m venv venv — no network needed)\n", flush=True)

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'venv', str(venv_dir)],
            cwd=project_dir,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print_fail("venv creation timed out (>60s)")
        print("    Possible causes: slow disk, anti-virus scanning, permissions")
        shutil.rmtree(venv_dir, ignore_errors=True)
        return False
    except Exception as e:
        print_fail(f"venv creation error: {e}")
        return False

    if result.returncode != 0 or not venv_dir.exists():
        print_fail("venv creation failed")
        shutil.rmtree(venv_dir, ignore_errors=True)
        return False

    # --- Bootstrap pip via ensurepip (offline, uses Python's bundled pip) ---
    python = _venv_python(venv_dir)
    print("  Bootstrapping pip (offline, no network)...", end=" ", flush=True)
    ensurepip = subprocess.run(
        [str(python), '-m', 'ensurepip', '--upgrade'],
        capture_output=True, timeout=30
    )
    if ensurepip.returncode != 0:
        print_fail("ensurepip failed")
        err = ensurepip.stderr.decode(errors='replace').strip()
        if err:
            print(f"    {err}")
        print()
        print("    This usually means your Python is missing ensurepip.")
        print("    MS Store Python does not include it.")
        print("    Fix: install Python from https://python.org/downloads/")
        _remove_broken_venv(venv_dir)
        return False
    print_pass("pip bootstrapped")

    # --- Final sanity check ---
    pip_check = subprocess.run(
        [str(python), '-m', 'pip', '--version'],
        capture_output=True, timeout=10
    )
    if pip_check.returncode != 0:
        print_fail("pip still not working after ensurepip")
        _remove_broken_venv(venv_dir)
        return False

    print_pass("Virtual environment ready")

    # --- Create bash-compatible smt shim (alongside smt.bat for Git Bash / WSL) ---
    smt_bash = project_dir / 'smt'
    smt_bash_content = (
        "#!/usr/bin/env bash\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'exec "$SCRIPT_DIR/venv/Scripts/python.exe" "$SCRIPT_DIR/src/smt_cli.py" "$@"\n'
    )
    smt_bash.write_text(smt_bash_content)
    try:
        smt_bash.chmod(0o755)
    except Exception:
        pass

    # --- Self-reinvoke inside the new venv — no manual activation needed ---
    print("\n  Restarting setup inside virtual environment...\n", flush=True)
    sys.stdout.flush()
    result = subprocess.run([str(python), __file__])
    sys.exit(result.returncode)


def main() -> bool:
    """Run all setup steps in sequence."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}SAVE-MY-TOKENS SETUP{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

    # Check if we're already in a venv
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )

    if not in_venv:
        # step_setup_venv() creates the venv then calls sys.exit() after
        # re-invoking install.py inside it — so this path never returns True.
        ok = step_setup_venv()
        if not ok:
            return False
        # Should be unreachable (step_setup_venv exits via sys.exit)
        return False

    # Running inside a venv — verify pip is functional before proceeding
    print("  Running inside virtual environment")
    pip_check = subprocess.run(
        [sys.executable, '-m', 'pip', '--version'],
        capture_output=True,
        timeout=10
    )
    if pip_check.returncode != 0:
        print_fail("pip is broken in this venv!")
        print()
        # Auto-delete the broken project-local venv so the next run recreates it.
        # We can't self-reinvoke here because sys.executable IS the broken venv python.
        project_dir = Path(__file__).parent
        venv_dir = project_dir / 'venv'
        if venv_dir.exists():
            _remove_broken_venv(venv_dir)
            print()
        print("  Deactivate this venv, then re-run install.py with your system Python:")
        print("    deactivate")
        print("    python install.py")
        return False
    print()

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
            print("Fix the issue above and re-run: python install.py\n")
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
