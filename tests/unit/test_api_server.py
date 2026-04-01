"""Unit tests for minimal API server (health/stats only).

NOTE: Full REST API endpoints (context, subgraph, search, validate-conflicts)
have been removed in favor of MCP server. Only health/stats endpoints remain.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "app" in data


def test_stats_endpoint(client):
    """Test stats endpoint."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "node_count" in data
    assert "edge_count" in data


def test_rest_api_removed(client):
    """Verify deprecated REST API endpoints are removed."""
    # All these should return 404
    assert client.get("/api/context/test").status_code == 404
    assert client.get("/api/subgraph/test").status_code == 404
    assert client.get("/api/search?query=test").status_code == 404
    assert client.post("/api/validate-conflicts", json={"tasks": []}).status_code == 404


def test_openapi_disabled(client):
    """Verify OpenAPI schema is disabled (minimal API)."""
    response = client.get("/openapi.json")
    # Disabled in create_app
    assert response.status_code == 404
