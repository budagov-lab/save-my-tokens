"""FastAPI application server for Graph API."""

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from src.api.query_service import QueryService
from src.config import settings
from src.__version__ import __version__
from src.embeddings import EmbeddingService
from src.graph import Neo4jClient
from src.parsers.symbol_index import SymbolIndex


# Request/Response models
class ContextRequest(BaseModel):
    """Request for context endpoint."""

    depth: Optional[int] = 1
    include_callers: Optional[bool] = False


class SubgraphRequest(BaseModel):
    """Request for subgraph endpoint."""

    depth: Optional[int] = 2


class SearchRequest(BaseModel):
    """Request for semantic search."""

    query: str
    top_k: Optional[int] = 5


class Task(BaseModel):
    """Task definition for conflict validation."""

    id: str
    target_symbols: List[str]


class ConflictValidationRequest(BaseModel):
    """Request for conflict validation."""

    tasks: List[Task]


def create_app(
    symbol_index: Optional[SymbolIndex] = None,
    query_service: Optional[QueryService] = None,
    embedding_service: Optional[EmbeddingService] = None,
) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        symbol_index: Symbol index (created if not provided)
        query_service: Query service (created if not provided)
        embedding_service: Embedding service (created if not provided)
    """

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="Graph API for Code Analysis and Agent Context Retrieval",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure logging
    logger.remove()  # Remove default handler
    logger.add(
        settings.LOGS_DIR / "app.log",
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="500 MB",
    )
    logger.add(
        lambda msg: print(msg, end=""),
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )

    # Initialize services
    if symbol_index is None:
        symbol_index = SymbolIndex()

    if embedding_service is None:
        try:
            embedding_service = EmbeddingService(symbol_index)
        except Exception as e:
            logger.warning(f"Could not initialize embedding service: {e}")
            embedding_service = None

    if query_service is None:
        try:
            neo4j_client = Neo4jClient()
            query_service = QueryService(symbol_index, neo4j_client, embedding_service)
        except Exception as e:
            logger.warning(f"Could not initialize Neo4j client: {e}. Running in demo mode.")
            neo4j_client = None
            query_service = QueryService(symbol_index, neo4j_client, embedding_service)  # type: ignore

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": __version__,
        }

    # Stats endpoint
    @app.get("/api/stats")
    async def get_stats():
        """Get graph statistics."""
        try:
            if neo4j_client:
                stats = neo4j_client.get_stats()
                return stats
        except Exception as e:
            logger.warning(f"Could not get Neo4j stats: {e}")

        return {
            "node_count": 0,
            "edge_count": 0,
        }

    # Endpoint 1: Get context for a symbol
    @app.get("/api/context/{symbol_name}")
    async def get_context(symbol_name: str, depth: int = 1, include_callers: bool = False):
        """Get minimal context for a symbol.

        Args:
            symbol_name: Name of the symbol
            depth: Maximum dependency depth (default: 1)
            include_callers: Include reverse dependencies/callers (default: False)

        Returns:
            Symbol info with dependencies and token count estimate
        """
        result = query_service.get_context(symbol_name, depth=depth, include_callers=include_callers)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # Endpoint 2: Get dependency subgraph
    @app.get("/api/subgraph/{symbol_name}")
    async def get_subgraph(symbol_name: str, depth: int = 2):
        """Get dependency subgraph for a symbol.

        Args:
            symbol_name: Name of the symbol
            depth: Maximum traversal depth (default: 2)

        Returns:
            Nodes and edges in the subgraph
        """
        result = query_service.get_subgraph(symbol_name, depth=depth)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # Endpoint 3: Semantic search
    @app.get("/api/search")
    async def search(query: str, top_k: int = 5):
        """Search for symbols matching query.

        Args:
            query: Search query (natural language or code)
            top_k: Number of top results to return (default: 5)

        Returns:
            Ranked list of matching symbols with similarity scores
        """
        result = query_service.semantic_search(query, top_k=top_k)
        return result

    # Endpoint 4: Validate conflicts
    @app.post("/api/validate-conflicts")
    async def validate_conflicts(request: ConflictValidationRequest):
        """Validate conflicts between parallel tasks.

        Args:
            request: ConflictValidationRequest with list of tasks

        Returns:
            Conflict report and parallel feasibility
        """
        tasks_data = [t.model_dump() for t in request.tasks]
        result = query_service.validate_conflicts(tasks_data)
        return result

    logger.info(f"FastAPI app created: {settings.APP_NAME} v{__version__}")
    return app


# Create application instance
app: FastAPI = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        workers=settings.API_WORKERS,
    )
