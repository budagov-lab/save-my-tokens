"""Unit tests for API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.query_service import QueryService
from src.api.server import create_app
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


@pytest.fixture
def symbol_index() -> SymbolIndex:
    """Create symbol index with test data."""
    index = SymbolIndex()
    index.add(
        Symbol(
            name="process_data",
            type="function",
            file="src/processor.py",
            line=1,
            column=0,
            docstring="Process incoming data",
        )
    )
    index.add(
        Symbol(
            name="validate_input",
            type="function",
            file="src/validator.py",
            line=10,
            column=0,
            docstring="Validate user input",
        )
    )
    index.add(
        Symbol(
            name="DataProcessor",
            type="class",
            file="src/processor.py",
            line=20,
            column=0,
            docstring="Main data processor class",
        )
    )
    return index


@pytest.fixture
def mock_neo4j_client() -> MagicMock:
    """Create mock Neo4j client."""
    mock = MagicMock()
    mock.get_stats.return_value = {"node_count": 5, "edge_count": 8}
    return mock


@pytest.fixture
def test_client(symbol_index: SymbolIndex, mock_neo4j_client: MagicMock) -> TestClient:
    """Create test FastAPI client with services."""
    query_service = QueryService(symbol_index, mock_neo4j_client)
    app = create_app(symbol_index=symbol_index, query_service=query_service)
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, test_client: TestClient) -> None:
        """Test health check returns ok status."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "app" in data


class TestStatsEndpoint:
    """Test stats endpoint."""

    def test_get_stats(self, test_client: TestClient) -> None:
        """Test stats endpoint returns graph stats."""
        response = test_client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "node_count" in data
        assert "edge_count" in data


class TestContextEndpoint:
    """Test context endpoint."""

    def test_get_context_found(self, test_client: TestClient) -> None:
        """Test getting context for existing symbol."""
        response = test_client.get("/api/context/process_data")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"]["name"] == "process_data"
        assert data["symbol"]["type"] == "function"
        assert "token_estimate" in data

    def test_get_context_not_found(self, test_client: TestClient) -> None:
        """Test getting context for non-existent symbol."""
        response = test_client.get("/api/context/nonexistent_function")
        assert response.status_code == 404

    def test_get_context_with_depth(self, test_client: TestClient) -> None:
        """Test context with custom depth parameter."""
        response = test_client.get("/api/context/process_data?depth=2")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"]["name"] == "process_data"

    def test_get_context_with_callers(self, test_client: TestClient) -> None:
        """Test context with include_callers parameter."""
        response = test_client.get("/api/context/process_data?include_callers=true")
        assert response.status_code == 200
        data = response.json()
        assert "callers" in data


class TestSubgraphEndpoint:
    """Test subgraph endpoint."""

    def test_get_subgraph_found(self, test_client: TestClient) -> None:
        """Test getting subgraph for existing symbol."""
        response = test_client.get("/api/subgraph/process_data")
        assert response.status_code == 200
        data = response.json()
        assert data["root_symbol"] == "process_data"
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 1

    def test_get_subgraph_not_found(self, test_client: TestClient) -> None:
        """Test getting subgraph for non-existent symbol."""
        response = test_client.get("/api/subgraph/nonexistent_function")
        assert response.status_code == 404

    def test_get_subgraph_with_depth(self, test_client: TestClient) -> None:
        """Test subgraph with custom depth."""
        response = test_client.get("/api/subgraph/DataProcessor?depth=3")
        assert response.status_code == 200
        data = response.json()
        assert data["depth"] == 3


class TestSearchEndpoint:
    """Test semantic search endpoint."""

    def test_search_basic(self, test_client: TestClient) -> None:
        """Test basic search query."""
        response = test_client.get("/api/search?query=process")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_with_top_k(self, test_client: TestClient) -> None:
        """Test search with custom top_k parameter."""
        response = test_client.get("/api/search?query=data&top_k=2")
        assert response.status_code == 200
        data = response.json()
        assert data["top_k"] == 2
        assert len(data["results"]) <= 2

    def test_search_no_results(self, test_client: TestClient) -> None:
        """Test search with no matching results."""
        response = test_client.get("/api/search?query=xyz123abc")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 0


class TestConflictValidationEndpoint:
    """Test conflict validation endpoint."""

    def test_validate_no_conflicts(self, test_client: TestClient) -> None:
        """Test validation with non-conflicting tasks."""
        payload = {
            "tasks": [
                {"id": "task_1", "target_symbols": ["process_data"]},
                {"id": "task_2", "target_symbols": ["validate_input"]},
            ]
        }
        response = test_client.post("/api/validate-conflicts", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["parallel_feasible"] is True
        assert len(data["direct_conflicts"]) == 0

    def test_validate_with_conflicts(self, test_client: TestClient) -> None:
        """Test validation with conflicting tasks."""
        payload = {
            "tasks": [
                {"id": "task_1", "target_symbols": ["process_data", "validate_input"]},
                {"id": "task_2", "target_symbols": ["validate_input", "DataProcessor"]},
            ]
        }
        response = test_client.post("/api/validate-conflicts", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["parallel_feasible"] is False
        assert len(data["direct_conflicts"]) > 0

    def test_validate_empty_tasks(self, test_client: TestClient) -> None:
        """Test validation with empty task list."""
        payload = {"tasks": []}
        response = test_client.post("/api/validate-conflicts", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["parallel_feasible"] is True
        assert len(data["direct_conflicts"]) == 0
