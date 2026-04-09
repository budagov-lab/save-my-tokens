#!/usr/bin/env python3
"""
CLI utilities for colored output and status messages.

Stdlib-only module (no external dependencies).
Used by configure.py, prelaunch_check.py, and smt_cli.py.
"""


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")


def print_pass(text: str) -> None:
    """Print a passing check."""
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {text}", flush=True)


def print_fail(text: str) -> None:
    """Print a failing check."""
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {text}", flush=True)


def print_warn(text: str) -> None:
    """Print a warning."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {text}", flush=True)
