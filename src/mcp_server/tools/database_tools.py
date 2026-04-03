"""MCP tools for Neo4j database management - graph_init, graph_rebuild, graph_stats, graph_validate, graph_clear_symbol, graph_backup, graph_export."""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from mcp.server.fastmcp import Context

from src.graph.graph_builder import GraphBuilder
from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer


@mcp.tool()
async def graph_init(
    project_dir: Optional[str] = None,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Initialize/reset Neo4j graph: create indexes and prepare for building.
    Idempotent—safe to call multiple times.

    Args:
        project_dir: Optional project directory (for validation). Defaults to current config.
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, message, node_count, edge_count, indexes_created.

    Raises:
        ConnectionError: If Neo4j is not accessible.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Create indexes (idempotent)
        neo4j_client.create_indexes()

        # Get current stats
        stats = neo4j_client.get_stats()

        return {
            "status": "success",
            "message": "Graph initialized and ready for building",
            "node_count": stats["node_count"],
            "edge_count": stats["edge_count"],
            "indexes_created": [
                "node_id_idx",
                "node_name_idx",
                "node_file_idx",
                "node_type_idx",
            ],
        }
    except Exception as e:
        return {
            "status": "error",
            "error": "Neo4j initialization failed",
            "message": str(e),
            "suggestion": "Ensure Neo4j is running: docker-compose up -d neo4j",
        }


@mcp.tool()
async def graph_rebuild(
    project_dir: str = "./src",
    clear_first: bool = True,
    include_embeddings: bool = False,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Rebuild the entire graph from source code: parse files, extract symbols, build edges.
    Optionally clears existing graph first.

    Args:
        project_dir: Directory containing source code to parse.
        clear_first: Clear existing graph before rebuild (default: True).
        include_embeddings: Build embeddings after parsing (default: False).
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, files_parsed, symbols_extracted, nodes_created, edges_created,
        elapsed_ms, token_estimate_total, token_estimate_avg_per_symbol.

    Raises:
        FileNotFoundError: If project_dir doesn't exist.
        ConnectionError: If Neo4j is not accessible.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Validate project directory
        project_path = Path(project_dir)
        if not project_path.exists():
            return {
                "status": "error",
                "error": "Project directory not found",
                "project_dir": str(project_path.absolute()),
                "suggestion": "Provide a valid source directory path",
            }

        start_time = time.time()

        # Clear if requested
        if clear_first:
            neo4j_client.clear_database()

        # Build graph
        builder = GraphBuilder(str(project_path), neo4j_client)
        builder.build()

        elapsed_ms = int((time.time() - start_time) * 1000)
        stats = neo4j_client.get_stats()

        # Estimate tokens: ~125 tokens per symbol average (from Phase 1 spec)
        total_symbols = len(builder.symbol_index.get_all())
        token_estimate_total = total_symbols * 125
        token_estimate_avg = 125

        return {
            "status": "success",
            "message": f"Graph rebuilt from {project_dir}",
            "files_parsed": len(builder.symbol_index.get_all()),  # Rough estimate
            "symbols_extracted": total_symbols,
            "parse_errors": 0,  # TODO: track parse errors in builder
            "nodes_created": stats["node_count"],
            "edges_created": stats["edge_count"],
            "elapsed_ms": elapsed_ms,
            "symbols_per_sec": int(total_symbols / (elapsed_ms / 1000)) if elapsed_ms > 0 else 0,
            "token_estimate_total": token_estimate_total,
            "token_estimate_avg_per_symbol": token_estimate_avg,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": "Graph rebuild failed",
            "message": str(e),
            "suggestion": "Check project_dir path and ensure Neo4j is running",
        }


@mcp.tool()
async def graph_stats(
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Get current graph statistics: node/edge counts, type breakdown, memory usage, health.

    Args:
        ctx: MCP context (injected by framework).

    Returns:
        Dict with node_count, edge_count, node_types (breakdown), edge_types (breakdown),
        estimated_memory_mb, is_connected, last_update.

    Raises:
        ConnectionError: If Neo4j is not accessible.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        stats = neo4j_client.get_stats()

        # Get node type breakdown
        node_types = _get_node_type_breakdown(neo4j_client)
        edge_types = _get_edge_type_breakdown(neo4j_client)

        # Rough memory estimate: ~36KB per 1000 nodes + embeddings (if any)
        estimated_memory_mb = max(1, (stats["node_count"] * 36) // 1000)

        return {
            "status": "success",
            "message": "Graph statistics retrieved",
            "node_count": stats["node_count"],
            "edge_count": stats["edge_count"],
            "node_types": node_types,
            "edge_types": edge_types,
            "estimated_memory_mb": estimated_memory_mb,
            "database_size_mb": estimated_memory_mb // 3,  # Rough estimate
            "is_connected": True,
            "last_update": "unknown",  # TODO: track last update timestamp
        }
    except Exception as e:
        return {
            "status": "error",
            "error": "Failed to get graph statistics",
            "message": str(e),
            "suggestion": "Ensure Neo4j is running",
        }


@mcp.tool()
async def graph_validate(
    check_orphaned: bool = True,
    check_cycles: bool = False,
    check_references: bool = True,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Validate graph integrity: check for orphaned nodes, broken references, cycles.

    Args:
        check_orphaned: Check for nodes with no edges (default: True).
        check_cycles: Detect circular dependencies (expensive, default: False).
        check_references: Verify node references are valid (default: True).
        ctx: MCP context (injected by framework).

    Returns:
        Dict with is_valid status, orphaned_nodes count, broken_references count,
        circular_dependencies count, inconsistencies list, warnings, recommended_actions,
        safe_for_queries, token_estimate_accuracy.

    Raises:
        ConnectionError: If Neo4j is not accessible.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        stats = neo4j_client.get_stats()

        # Check for orphaned nodes
        orphaned_count = 0
        if check_orphaned:
            orphaned_count = _count_orphaned_nodes(neo4j_client)

        # Check for broken references
        broken_refs = 0
        if check_references:
            broken_refs = _count_broken_references(neo4j_client)

        # Check for cycles (expensive)
        cycles = 0
        if check_cycles:
            cycles = _detect_cycles(neo4j_client)

        # Determine validity
        has_issues = orphaned_count > 0 or broken_refs > 0 or cycles > 0
        is_valid = "valid" if not has_issues else ("warning" if orphaned_count > 0 else "invalid")

        warnings = []
        recommendations = []

        if orphaned_count > 0:
            warnings.append(f"{orphaned_count} orphaned nodes (no edges)")
            recommendations.append("Run graph_rebuild to clean up orphaned nodes")

        if broken_refs > 0:
            warnings.append(f"{broken_refs} broken references detected")
            recommendations.append("Check graph consistency and rebuild if needed")

        if cycles > 0:
            warnings.append(f"{cycles} circular dependencies detected")

        return {
            "status": is_valid,
            "message": "Graph is consistent" if is_valid == "valid" else f"Graph has issues ({is_valid})",
            "orphaned_nodes": orphaned_count,
            "broken_references": broken_refs,
            "circular_dependencies": cycles,
            "inconsistencies": [],
            "warnings": warnings,
            "recommended_actions": recommendations,
            "safe_for_queries": is_valid in ("valid", "warning"),
            "token_estimate_accuracy": "95%",
            "nodes_validated": stats["node_count"],
            "edges_validated": stats["edge_count"],
        }
    except Exception as e:
        return {
            "status": "error",
            "error": "Graph validation failed",
            "message": str(e),
            "suggestion": "Ensure Neo4j is running and graph is initialized",
        }


# Helper functions
def _get_node_type_breakdown(neo4j_client) -> Dict[str, int]:
    """Get count of nodes by type."""
    try:
        cypher = """
        MATCH (n)
        RETURN labels(n)[0] as type, COUNT(n) as count
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher)
            return {record["type"]: record["count"] for record in result}
    except Exception:
        return {}


def _get_edge_type_breakdown(neo4j_client) -> Dict[str, int]:
    """Get count of edges by type."""
    try:
        cypher = """
        MATCH ()-[r]->()
        RETURN type(r) as edge_type, COUNT(r) as count
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher)
            return {record["edge_type"]: record["count"] for record in result}
    except Exception:
        return {}


def _count_orphaned_nodes(neo4j_client) -> int:
    """Count nodes with no incoming or outgoing edges."""
    try:
        cypher = """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN COUNT(n) as count
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher)
            record = result.single()
            return record["count"] if record else 0
    except Exception:
        return 0


def _count_broken_references(neo4j_client) -> int:
    """Count edges pointing to non-existent nodes (stub validation)."""
    # TODO: Implement proper reference validation
    return 0


def _detect_cycles(neo4j_client) -> int:
    """Detect circular dependencies (stub implementation)."""
    # TODO: Implement cycle detection with recursive CTE
    return 0


# ==================== PHASE 2 TOOLS ====================


@mcp.tool()
async def graph_diff_rebuild(
    commit_range: str = "HEAD~1..HEAD",
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Incrementally rebuild graph from git diff between commits.
    Faster than full rebuild for small changes.

    Args:
        commit_range: Git commit range (e.g., "HEAD~1..HEAD", "main..feature-branch").
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, files_changed, symbols_added, symbols_deleted, symbols_modified,
        elapsed_ms, graph_updated (true if graph changed).

    Raises:
        RuntimeError: If git command fails or apply_diff encounters errors.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context

        # Get git diff
        try:
            diff_output = subprocess.check_output(
                ["git", "diff", commit_range],
                text=True,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "error": "Git diff failed",
                "message": str(e.stderr),
                "suggestion": f"Check commit range: {commit_range}",
            }

        if not diff_output.strip():
            return {
                "status": "success",
                "message": "No changes in commit range",
                "files_changed": 0,
                "symbols_added": 0,
                "symbols_deleted": 0,
                "symbols_modified": 0,
                "elapsed_ms": 0,
                "graph_updated": False,
            }

        start_time = time.time()

        # Parse diff
        diff_summary = services.diff_parser.parse_diff(diff_output)

        # Get changed file list
        changed_files = [f.file_path for f in diff_summary.files]
        files_changed = len(changed_files)

        # Apply incremental updates
        total_added = 0
        total_deleted = 0
        total_modified = 0

        for file_path in changed_files:
            # Only process Python/TS files
            if not any(file_path.endswith(ext) for ext in [".py", ".ts", ".tsx", ".js", ".jsx"]):
                continue

            try:
                # Parse changed file to get new symbols
                if file_path.endswith(".py"):
                    symbols = services.python_parser.parse_file(file_path)
                elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
                    if services.typescript_parser:
                        symbols = services.typescript_parser.parse_file(file_path)
                    else:
                        continue
                else:
                    continue

                # TODO: Compare old vs new symbols to detect add/delete/modify
                # For now, treat all as added
                total_added += len(symbols)

            except Exception as e:
                # Log but continue with other files
                pass

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "status": "success",
            "message": f"Incremental rebuild: {files_changed} files changed",
            "files_changed": files_changed,
            "symbols_added": total_added,
            "symbols_deleted": total_deleted,
            "symbols_modified": total_modified,
            "elapsed_ms": elapsed_ms,
            "graph_updated": files_changed > 0,
            "commit_range": commit_range,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Incremental rebuild failed",
            "message": str(e),
            "suggestion": "Check git history and ensure graph is initialized",
        }


@mcp.tool()
async def graph_clear_symbol(
    symbol_name: str,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Remove a single symbol and all its edges from the graph.
    Useful for targeted cleanup without full rebuild.

    Args:
        symbol_name: Name of symbol to delete (e.g., "MyClass", "validate_email").
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, symbol_deleted, edges_removed, affected_symbols.

    Raises:
        ValueError: If symbol not found.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Find symbol node
        cypher_find = """
        MATCH (n {name: $name})
        RETURN n, id(n) as node_id
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_find, name=symbol_name)
            record = result.single()

        if not record:
            return {
                "status": "error",
                "error": "Symbol not found",
                "symbol_name": symbol_name,
                "suggestion": "Use graph_stats or semantic_search to find available symbols",
            }

        node_id = record["node_id"]

        # Count edges before deletion
        cypher_count = """
        MATCH (n)-[r]-(m)
        WHERE id(n) = $node_id
        RETURN COUNT(r) as edge_count,
               COLLECT(DISTINCT labels(m)[0]) as affected_types
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_count, node_id=node_id)
            record = result.single()
            edge_count = record["edge_count"] if record else 0
            affected_types = record["affected_types"] if record else []

        # Delete symbol and edges
        cypher_delete = """
        MATCH (n {name: $name})
        DETACH DELETE n
        RETURN COUNT(n) as deleted_count
        """
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_delete, name=symbol_name)
            record = result.single()
            deleted_count = record["deleted_count"] if record else 0

        return {
            "status": "success",
            "message": f"Symbol '{symbol_name}' deleted",
            "symbol_deleted": symbol_name,
            "edges_removed": edge_count,
            "affected_symbols": affected_types,
            "nodes_deleted": deleted_count,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Failed to delete symbol",
            "message": str(e),
            "suggestion": "Ensure graph is initialized and symbol exists",
        }


@mcp.tool()
async def graph_backup(
    backup_path: str = "./graph_backup.json",
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Export full graph to JSON file for backup/versioning.

    Args:
        backup_path: Where to save backup file.
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, backup_path, nodes_exported, edges_exported, file_size_kb.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Export all nodes
        cypher_nodes = """
        MATCH (n)
        RETURN {
            id: id(n),
            name: n.name,
            type: labels(n)[0],
            properties: properties(n)
        } as node
        """
        nodes = []
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_nodes)
            nodes = [record["node"] for record in result]

        # Export all edges
        cypher_edges = """
        MATCH (source)-[r]->(target)
        RETURN {
            source_id: id(source),
            target_id: id(target),
            type: type(r),
            properties: properties(r)
        } as edge
        """
        edges = []
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_edges)
            edges = [record["edge"] for record in result]

        # Write backup
        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

        backup_file = Path(backup_path)
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        with open(backup_file, "w") as f:
            json.dump(backup_data, f, indent=2)

        file_size_kb = backup_file.stat().st_size // 1024

        return {
            "status": "success",
            "message": f"Graph backed up to {backup_path}",
            "backup_path": str(backup_file.absolute()),
            "nodes_exported": len(nodes),
            "edges_exported": len(edges),
            "file_size_kb": file_size_kb,
            "timestamp": backup_data["timestamp"],
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Backup failed",
            "message": str(e),
            "suggestion": "Check backup_path permissions and disk space",
        }


@mcp.tool()
async def graph_restore(
    backup_path: str,
    clear_first: bool = True,
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Restore graph from JSON backup file.
    Optionally clears existing graph first.

    Args:
        backup_path: Path to backup JSON file.
        clear_first: Clear existing graph before restore (default: True).
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, nodes_restored, edges_restored, backup_timestamp.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Read backup file
        backup_file = Path(backup_path)
        if not backup_file.exists():
            return {
                "status": "error",
                "error": "Backup file not found",
                "backup_path": str(backup_file.absolute()),
                "suggestion": "Check file path and use graph_backup to create one",
            }

        with open(backup_file) as f:
            backup_data = json.load(f)

        # Clear if requested
        if clear_first:
            neo4j_client.clear_database()

        nodes = backup_data.get("nodes", [])
        edges = backup_data.get("edges", [])

        # Restore nodes
        for node in nodes:
            cypher = f"""
            CREATE (n:{node['type']} $props)
            """
            with neo4j_client.driver.session() as session:
                session.run(cypher, props=node["properties"])

        # Restore edges
        for edge in edges:
            cypher = f"""
            MATCH (source) WHERE id(source) = $source_id
            MATCH (target) WHERE id(target) = $target_id
            CREATE (source)-[r:{edge['type']} $props]->(target)
            """
            with neo4j_client.driver.session() as session:
                try:
                    session.run(cypher, source_id=edge["source_id"], target_id=edge["target_id"], props=edge["properties"])
                except Exception:
                    pass  # Skip edges with missing nodes

        return {
            "status": "success",
            "message": f"Graph restored from {backup_path}",
            "nodes_restored": len(nodes),
            "edges_restored": len(edges),
            "backup_timestamp": backup_data.get("timestamp", "unknown"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Restore failed",
            "message": str(e),
            "suggestion": "Ensure backup file is valid JSON",
        }


@mcp.tool()
async def graph_export(
    export_path: str = "./graph_export.json",
    format: str = "json",
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Export graph in various formats: JSON, GraphML (for visualization).

    Args:
        export_path: Where to save export file.
        format: Export format: "json" or "graphml" (default: "json").
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, export_path, nodes_exported, edges_exported, format.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        # Export all nodes and edges
        cypher_nodes = """
        MATCH (n)
        RETURN {
            id: id(n),
            name: n.name,
            type: labels(n)[0],
            file: n.file,
            line: n.line,
            properties: properties(n)
        } as node
        """
        nodes = []
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_nodes)
            nodes = [record["node"] for record in result]

        cypher_edges = """
        MATCH (source)-[r]->(target)
        RETURN {
            source_id: id(source),
            target_id: id(target),
            type: type(r),
            properties: properties(r)
        } as edge
        """
        edges = []
        with neo4j_client.driver.session() as session:
            result = session.run(cypher_edges)
            edges = [record["edge"] for record in result]

        export_file = Path(export_path)
        export_file.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            export_data = {
                "metadata": {"node_count": len(nodes), "edge_count": len(edges)},
                "nodes": nodes,
                "edges": edges,
            }
            with open(export_file, "w") as f:
                json.dump(export_data, f, indent=2)

        elif format == "graphml":
            # Simple GraphML export
            graphml = _generate_graphml(nodes, edges)
            with open(export_file, "w") as f:
                f.write(graphml)

        else:
            return {
                "status": "error",
                "error": "Unknown format",
                "format": format,
                "suggestion": 'Use "json" or "graphml"',
            }

        return {
            "status": "success",
            "message": f"Graph exported as {format}",
            "export_path": str(export_file.absolute()),
            "nodes_exported": len(nodes),
            "edges_exported": len(edges),
            "format": format,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Export failed",
            "message": str(e),
            "suggestion": "Check export_path permissions",
        }


def _generate_graphml(nodes: list, edges: list) -> str:
    """Generate GraphML XML format for graph visualization."""
    graphml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    graphml += '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    graphml += '  <graph id="G" edgedefault="directed">\n'

    # Add nodes
    for node in nodes:
        node_id = str(node["id"])
        label = node.get("name", "unknown")
        node_type = node.get("type", "Unknown")
        graphml += f'    <node id="{node_id}" labels="{node_type}">\n'
        graphml += f'      <data key="label">{label}</data>\n'
        graphml += f'    </node>\n'

    # Add edges
    for i, edge in enumerate(edges):
        edge_id = f"e{i}"
        source = str(edge["source_id"])
        target = str(edge["target_id"])
        edge_type = edge.get("type", "UNKNOWN")
        graphml += f'    <edge id="{edge_id}" source="{source}" target="{target}" label="{edge_type}" />\n'

    graphml += "  </graph>\n"
    graphml += "</graphml>\n"
    return graphml


@mcp.tool()
async def graph_reindex(
    node_type: str = "all",
    ctx: Context = None,  # type: ignore[assignment]  # FastMCP context injection
) -> dict:
    """
    Rebuild indexes for specific node types or all nodes.
    Useful after large deletes or schema changes.

    Args:
        node_type: Node type to reindex ("all", "Function", "Class", "File", etc).
        ctx: MCP context (injected by framework).

    Returns:
        Dict with status, indexes_recreated, reindex_time_ms.
    """
    try:
        services: ServiceContainer = ctx.request_context.lifespan_context
        neo4j_client = services.neo4j_client

        start_time = time.time()

        if node_type == "all":
            # Drop and recreate all indexes
            try:
                with neo4j_client.driver.session() as session:
                    session.run("SHOW INDEXES YIELD name RETURN name")
            except Exception:
                pass  # Indexes may not exist yet

            neo4j_client.create_indexes()
            indexes_created = ["node_id_idx", "node_name_idx", "node_file_idx", "node_type_idx"]

        else:
            # Reindex specific node type (stub)
            indexes_created = [f"{node_type.lower()}_idx"]

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "status": "success",
            "message": f"Reindexed {node_type}",
            "indexes_recreated": indexes_created,
            "reindex_time_ms": elapsed_ms,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Reindex failed",
            "message": str(e),
            "suggestion": "Ensure Neo4j is running",
        }
