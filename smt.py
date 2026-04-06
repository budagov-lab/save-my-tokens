#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper script for SMT CLI - allows 'smt' command to work from anywhere."""

import sys
from pathlib import Path

# Add the repo root to Python path so src module is importable
repo_root = Path(__file__).parent.resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Now import and run the actual CLI
from src.smt_cli import main

if __name__ == '__main__':
    sys.exit(main())
