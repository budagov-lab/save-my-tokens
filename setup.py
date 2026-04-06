#!/usr/bin/env python3
"""Setup script for smt-graph package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the main package version
__version__ = "0.1.0"

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="smt-graph",
    version=__version__,
    description="Code Context for AI Agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Claude Code",
    author_email="claude@anthropic.com",
    license="MIT",
    python_requires=">=3.11",
    packages=find_packages(include=['src', 'src.*']),
    package_dir={'': '.'},
    install_requires=[
        "tree-sitter>=0.20.4",
        "tree-sitter-python>=0.20.4",
        "tree-sitter-typescript>=0.20.4",
        "neo4j>=5.14.0",
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "sentence-transformers>=2.2.0",
        "faiss-cpu>=1.7.4",
        "numpy>=1.24.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "loguru>=0.7.0",
        "tqdm>=4.66.0",
        "requests>=2.28.0",
        "rich>=13.0.0",
    ],
    entry_points={
        'console_scripts': [
            'smt = src.smt_cli:main',
        ],
    },
)
