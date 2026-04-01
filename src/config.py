"""Configuration for save-my-tokens application."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Neo4j Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # OpenAI Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_EMBEDDINGS: str = "text-embedding-3-small"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    API_WORKERS: int = 1

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/save-my-tokens.log"

    # Application Configuration
    DEBUG: bool = True
    APP_NAME: str = "save-my-tokens"
    APP_VERSION: str = "0.1.0"

    # Project paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    FIXTURES_DIR: Path = PROJECT_ROOT / "tests" / "fixtures"

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def __init__(self, **kwargs):
        """Initialize settings and ensure directories exist."""
        super().__init__(**kwargs)
        # Create necessary directories
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
