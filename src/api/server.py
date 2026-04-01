"""Legacy FastAPI server - DEPRECATED. Use MCP server instead."""

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.query_service import QueryService
from src.config import settings
from src.__version__ import __version__
from src.embeddings import EmbeddingService
from src.graph import Neo4jClient
from src.parsers.symbol_index import SymbolIndex


def create_app(
    symbol_index: Optional[SymbolIndex] = None,
    query_service: Optional[QueryService] = None,
    embedding_service: Optional[EmbeddingService] = None,
) -> FastAPI:
    """Create minimal FastAPI application (health/stats only).

    DEPRECATED: Use MCP server (src/mcp_server/) instead. This is kept only
    for backward compatibility with health/stats endpoints.

    Args:
        symbol_index: Symbol index (created if not provided)
        query_service: Query service (created if not provided)
        embedding_service: Embedding service (created if not provided)
    """

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="[DEPRECATED] Use MCP server instead",
        docs_url=None,
        openapi_url=None,
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

    logger.info(f"Minimal FastAPI app (health/stats only): {settings.APP_NAME} v{__version__}")
    logger.warning("REST API endpoints deprecated. Use MCP server (src/mcp_server/) instead.")
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
