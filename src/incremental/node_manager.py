"""Neo4j node CRUD helpers for incremental graph updates."""

from typing import Any, Dict, List

from loguru import logger

from src.graph.neo4j_client import Neo4jClient
from src.parsers.symbol import Symbol


LABEL_TO_SYM_TYPE: Dict[str, str] = {
    "Function": "function",
    "Class": "class",
    "Variable": "variable",
    "Module": "import",
    "Type": "type",
    "Interface": "interface",
}


def symbol_type_to_label(sym_type: str) -> str:
    """Map Symbol.type string ('function', 'class', …) to Neo4j label."""
    mapping = {
        "function": "Function",
        "class": "Class",
        "variable": "Variable",
        "import": "Module",
        "type": "Type",
        "interface": "Interface",
    }
    return mapping.get(sym_type, "Variable")


def query_symbols_in_file(neo4j: Neo4jClient, file_path: str) -> List[Symbol]:
    """Query Neo4j for all symbol nodes in a file."""
    pid = neo4j.project_id or ""
    pid_filter = "AND n.project_id = $pid" if pid else ""
    query = f"""
    MATCH (n)
    WHERE n.file = $file AND n.name IS NOT NULL
          AND NOT n:File AND NOT n:Commit
          {pid_filter}
    RETURN n.name AS name, n.type AS ntype, n.file AS file,
           n.line AS line, n.column AS col, n.parent AS parent
    """
    params: Dict[str, Any] = {"file": file_path}
    if pid:
        params["pid"] = pid
    symbols: List[Symbol] = []
    with neo4j.driver.session() as session:
        for row in session.run(query, **params):
            sym_type = LABEL_TO_SYM_TYPE.get(row["ntype"] or "", "variable")
            symbols.append(Symbol(
                name=row["name"],
                type=sym_type,
                file=row["file"],
                line=row["line"] or 1,
                column=row["col"] or 0,
                parent=row["parent"],
            ))
    return symbols


def delete_symbol_node(tx, neo4j: Neo4jClient, file_path: str, symbol_name: str) -> None:
    """Delete a symbol node and all its edges from Neo4j (DETACH DELETE)."""
    pid = neo4j.project_id or ""
    pid_clause = "AND n.project_id = $pid" if pid else ""
    query = f"MATCH (n {{file: $file, name: $name}}) WHERE 1=1 {pid_clause} DETACH DELETE n"
    params: Dict[str, Any] = {"file": file_path, "name": symbol_name}
    if pid:
        params["pid"] = pid
    tx.run(query, **params)
    logger.debug(f"Deleted node for {symbol_name} in {file_path}")


def create_symbol_node(tx, neo4j: Neo4jClient, symbol: Symbol) -> None:
    """Create or update a symbol node in Neo4j using the correct label."""
    label = symbol_type_to_label(symbol.type)
    pid = neo4j.project_id or ""
    node_id = symbol.node_id or f"{symbol.type}:{symbol.file}:{symbol.line}:{symbol.name}"
    query = f"""
    MERGE (n:{label} {{node_id: $node_id}})
    SET n.name = $name,
        n.type = $label,
        n.file = $file,
        n.line = $line,
        n.column = $column,
        n.parent = $parent,
        n.project_id = $pid
    """
    tx.run(
        query,
        node_id=node_id,
        name=symbol.name,
        label=label,
        file=symbol.file,
        line=symbol.line,
        column=symbol.column,
        parent=symbol.parent or "",
        pid=pid,
    )
    logger.debug(f"Created/updated node for {symbol.qualified_name}")
