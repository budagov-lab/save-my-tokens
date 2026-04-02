"""Service container for MCP server - singleton management and lifecycle."""

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from src.agent.execution_engine import create_default_execution_engine
from src.agent.execution_engine import ParallelExecutionEngine
from src.agent.scheduler import TaskScheduler
from src.api.query_service import QueryService
from src.embeddings.embedding_service import EmbeddingService
from src.graph.neo4j_client import Neo4jClient
from src.incremental.diff_parser import DiffParser
from src.incremental.updater import IncrementalSymbolUpdater
from src.parsers.symbol_index import SymbolIndex


@dataclass
class ServiceContainer:
    """Central service container - holds all singletons for the MCP server."""

    symbol_index: SymbolIndex
    query_service: QueryService
    updater: Optional[IncrementalSymbolUpdater]
    diff_parser: DiffParser
    scheduler: TaskScheduler
    execution_engine: ParallelExecutionEngine
    neo4j_client: Optional[Neo4jClient]
    embedding_service: Optional[EmbeddingService]


def build_services() -> ServiceContainer:
    """
    Construct all singletons in dependency order.

    Called once at MCP server startup. Optional dependencies (Neo4j, embeddings)
    are wrapped in try/except; failures log a warning and set the service to None
    rather than crashing. This allows offline mode or graceful degradation.

    Returns:
        ServiceContainer with all services initialized.
    """
    logger.info("Initializing MCP services...")

    # Always create symbol index
    symbol_index = SymbolIndex()
    logger.debug("Created SymbolIndex")

    # Optional: Neo4j
    neo4j_client: Optional[Neo4jClient] = None
    try:
        neo4j_client = Neo4jClient()
        logger.info("Connected to Neo4j")
    except Exception as e:
        logger.warning(f"Neo4j unavailable, running in offline mode: {e}")

    # Optional: EmbeddingService
    embedding_service: Optional[EmbeddingService] = None
    try:
        embedding_service = EmbeddingService(symbol_index)
        logger.info("Initialized EmbeddingService")
    except Exception as e:
        logger.warning(f"EmbeddingService unavailable (no FAISS/OpenAI key?): {e}")

    # Core services
    query_service = QueryService(symbol_index, neo4j_client, embedding_service)
    logger.debug("Created QueryService")

    # IncrementalSymbolUpdater requires Neo4j (raises RuntimeError if None)
    if neo4j_client is None:
        updater = None  # type: ignore[assignment]
        logger.warning("Neo4j unavailable: incremental updates disabled")
    else:
        updater = IncrementalSymbolUpdater(symbol_index, neo4j_client)
        logger.debug("Created IncrementalSymbolUpdater")

    diff_parser = DiffParser()
    logger.debug("Created DiffParser")

    scheduler = TaskScheduler()
    logger.debug("Created TaskScheduler")

    execution_engine = create_default_execution_engine(max_workers=4)
    logger.debug("Created ParallelExecutionEngine")

    logger.info("MCP services initialized successfully")

    return ServiceContainer(
        symbol_index=symbol_index,
        query_service=query_service,
        updater=updater,
        diff_parser=diff_parser,
        scheduler=scheduler,
        execution_engine=execution_engine,
        neo4j_client=neo4j_client,
        embedding_service=embedding_service,
    )


async def teardown_services(container: ServiceContainer) -> None:
    """
    Teardown singletons that hold resources.

    Called once at MCP server shutdown. Safely handles None services.

    Args:
        container: ServiceContainer to teardown.
    """
    logger.info("Shutting down MCP services...")

    if container.neo4j_client is not None:
        try:
            container.neo4j_client.close()
            logger.info("Closed Neo4j connection")
        except Exception as e:
            logger.error(f"Error closing Neo4j: {e}")

    logger.info("MCP services shut down")
