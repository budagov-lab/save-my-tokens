"""Unit tests for configuration module."""

from pathlib import Path

from src.config import settings


def test_settings_exist():
    """Test that settings are properly initialized."""
    assert settings is not None
    assert settings.APP_NAME == "smt-graph"
    assert settings.NEO4J_USER == "neo4j"


def test_settings_paths():
    """Test that settings paths are properly configured."""
    assert isinstance(settings.PROJECT_ROOT, Path)
    assert isinstance(settings.DATA_DIR, Path)
    assert isinstance(settings.LOGS_DIR, Path)
    assert isinstance(settings.FIXTURES_DIR, Path)


def test_settings_directories_created(tmp_path):
    """Test that settings directories are created."""
    assert settings.LOGS_DIR.exists()
    assert settings.DATA_DIR.exists()


def test_api_configuration():
    """Test API configuration values."""
    assert settings.API_HOST == "0.0.0.0"
    assert settings.API_PORT == 8000
    assert isinstance(settings.API_RELOAD, bool)
