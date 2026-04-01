"""FastAPI application server for Graph API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import settings
from src.__version__ import __version__


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

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

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": __version__,
        }

    # Stats endpoint (placeholder)
    @app.get("/api/stats")
    async def get_stats():
        """Get graph statistics."""
        return {
            "nodes": 0,
            "edges": 0,
            "graph_size_mb": 0.0,
        }

    logger.info(f"FastAPI app created: {settings.APP_NAME} v{__version__}")
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        workers=settings.API_WORKERS,
    )
