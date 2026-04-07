"""Configuration for smt-graph application."""

from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore unknown environment variables
    )

    # Neo4j Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"  # WARNING: Change in production (use env var: NEO4J_PASSWORD)

    # Embedding Configuration
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    API_WORKERS: int = 1

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/smt-graph.log"

    # Application Configuration
    DEBUG: bool = True
    APP_NAME: str = "smt-graph"
    APP_VERSION: str = "0.1.0"

    # Project Isolation
    # Neo4j database name for this project (each project gets its own database)
    # Format: project_name (lowercase, alphanumeric + underscore)
    # NOTE: Neo4j Community Edition only supports the default "neo4j" database
    NEO4J_DATABASE: str = "neo4j"

    # Project paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    FIXTURES_DIR: Path = PROJECT_ROOT / "tests" / "fixtures"

    def __init__(self, **kwargs):
        """Initialize settings and ensure directories exist."""
        super().__init__(**kwargs)

        # Create necessary directories
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
