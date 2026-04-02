"""Project isolation utilities for multi-project support."""

import os
from pathlib import Path
from loguru import logger


def get_project_name() -> str:
    """
    Get project name from environment or directory name.

    Priority:
    1. SMT_PROJECT env var
    2. Parent directory name (e.g., /Projects/my-app -> "my_app")
    3. Default: "smt_default"

    Returns:
        Project name (lowercase, alphanumeric + underscore)
    """
    # Check environment variable
    if os.getenv('SMT_PROJECT'):
        return os.getenv('SMT_PROJECT').lower()

    # Get from directory name
    try:
        project_dir = Path.cwd().name
        # Convert to valid database name (lowercase, alphanumeric + underscore)
        project_name = project_dir.lower().replace('-', '_').replace(' ', '_')
        # Remove non-alphanumeric (keep underscore)
        project_name = ''.join(c for c in project_name if c.isalnum() or c == '_')
        if project_name:
            return project_name
    except Exception as e:
        logger.debug(f"Could not get project name from directory: {e}")

    return "smt_default"


def set_project_database() -> None:
    """
    Set Neo4j database based on project name.

    Call this at startup to configure project isolation.
    """
    from src.config import settings

    project_name = get_project_name()
    settings.NEO4J_DATABASE = project_name
    logger.info(f"Using Neo4j database: {project_name}")


def get_database_name() -> str:
    """Get current Neo4j database name."""
    from src.config import settings

    return settings.NEO4J_DATABASE
