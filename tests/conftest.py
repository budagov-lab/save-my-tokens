"""Pytest configuration and fixtures for tests."""

import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def fixtures_dir(project_root):
    """Get test fixtures directory."""
    return project_root / "tests" / "fixtures"


@pytest.fixture
def sample_python_code():
    """Sample Python code for testing parser."""
    return '''
def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!"

class Calculator:
    """Simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

import os
from typing import Dict, List
'''


@pytest.fixture
def sample_typescript_code():
    """Sample TypeScript code for testing parser."""
    return '''
function greet(name: string): string {
  return `Hello, ${name}!`;
}

class Calculator {
  add(a: number, b: number): number {
    return a + b;
  }

  multiply(a: number, b: number): number {
    return a * b;
  }
}

import { readFile } from "fs";
import type { Config } from "./types";
'''
