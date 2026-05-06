"""SMT search and explain commands."""

from pathlib import Path
from typing import Optional

from src.cli._helpers import (
    _get_embedding_service,
    _get_project_id,
    _get_neo4j_client,
    _require_git,
    _resolve_project_path,
)


def cmd_search(query: str, top_k: int = 5, follow: Optional[str] = None) -> int:
    from src.config import settings

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        cache_dir = project_path / '.smt' / 'embeddings'
        svc = _get_embedding_service(cache_dir)

        if not svc.load_index():
            print(f"Embeddings index not found — run: smt build --embeddings")
            return 1

        results = svc.search(query, top_k=top_k)

        if not results:
            if not svc.index:
                print(f"No results for '{query}' (embeddings unavailable — see warning above)")
            else:
                print(f"No results for '{query}'")
            return 0

        print(f"\nSearch: {query!r}  (top {len(results)})\n")
        for sym, score in results:
            print(f"  {sym.name}  [{sym.type}]  score={score:.3f}")
            print(f"    {sym.file}:{sym.line}")
            if sym.docstring:
                print(f"    {sym.docstring[:80]}")

        if follow and results:
            from src.cli.query import cmd_context, cmd_impact
            top_name = results[0][0].name
            print(f"\n--- {follow}: {top_name} ---")
            if follow == 'context':
                return cmd_context(top_name, depth=2)
            elif follow == 'impact':
                return cmd_impact(top_name, max_depth=3)

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def cmd_lookup(query: str, compact: bool = False, brief: bool = False) -> int:
    """Unified resolver: exact match → dot-notation → semantic search. Always returns the best hit."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    pid_clause = "AND n.project_id = $pid" if project_id else ""

    try:
        client = _get_neo4j_client(project_id)
        row = None
        via = None

        with client.driver.session() as session:
            # Stage 1: exact name match
            row = session.run(
                f"MATCH (n {{name: $name}}) WHERE 1=1 {pid_clause} "
                "WITH n, CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END AS p "
                "ORDER BY p LIMIT 1 "
                "OPTIONAL MATCH (caller)-[:CALLS]->(n) "
                "OPTIONAL MATCH (n)-[:CALLS]->(callee) "
                "RETURN n, count(DISTINCT caller) AS ncallers, "
                "collect(DISTINCT callee.name)[..5] AS callees",
                name=query, pid=project_id,
            ).single()
            if row:
                via = "exact"

            # Stage 2: dot-notation split (Class.method)
            if not row and '.' in query:
                parent, name = query.rsplit('.', 1)
                row = session.run(
                    f"MATCH (n {{name: $name}}) WHERE n.parent = $parent {pid_clause} "
                    "OPTIONAL MATCH (caller)-[:CALLS]->(n) "
                    "OPTIONAL MATCH (n)-[:CALLS]->(callee) "
                    "RETURN n, count(DISTINCT caller) AS ncallers, "
                    "collect(DISTINCT callee.name)[..5] AS callees LIMIT 1",
                    name=name, parent=parent, pid=project_id,
                ).single()
                if row:
                    via = "dot-notation"

            # Stage 3: partial-name graph suggestions (no embeddings needed)
            if not row:
                term = query.rsplit('.', 1)[-1]
                suggestions = session.run(
                    f"MATCH (n) WHERE toLower(n.name) CONTAINS toLower($term) {pid_clause} "
                    "RETURN n.name AS name, n.parent AS parent, n.file AS file, labels(n)[0] AS type "
                    "ORDER BY size(n.name) LIMIT 5",
                    term=term, pid=project_id,
                ).data()
                if suggestions:
                    via = "partial-name"
                    best = suggestions[0]
                    resolved_name = f"{best['parent']}.{best['name']}" if best.get('parent') else best['name']
                    row = session.run(
                        f"MATCH (n {{name: $name}}) WHERE 1=1 {pid_clause} "
                        "WITH n, CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END AS p "
                        "ORDER BY p LIMIT 1 "
                        "OPTIONAL MATCH (caller)-[:CALLS]->(n) "
                        "OPTIONAL MATCH (n)-[:CALLS]->(callee) "
                        "RETURN n, count(DISTINCT caller) AS ncallers, "
                        "collect(DISTINCT callee.name)[..5] AS callees",
                        name=best['name'], pid=project_id,
                    ).single()

        client.driver.close()

        if not row:
            print(f"No match found for '{query}'")
            print(f"  Try: smt grep \"{query}\" or smt search \"{query}\"")
            return 1

        n = row["n"]
        ncallers = row["ncallers"] or 0
        callees = [c for c in (row["callees"] or []) if c]
        labels = list(n.labels)
        file_str = n.get("file", "?")
        try:
            display = str(Path(file_str).relative_to(project_path))
        except (ValueError, TypeError):
            display = file_str

        if compact:
            via_note = f" [{via}]" if via != "exact" else ""
            print(f"Lookup: {n['name']}  [{', '.join(labels)}]{via_note}  {display}:{n.get('line', '?')}")
            if n.get("signature"):
                print(f"sig: {n.get('signature')}")
        else:
            via_note = f"\n  via: {via}" if via != "exact" else ""
            print(f"\nLookup: {query!r} → {n['name']}  [{', '.join(labels)}]{via_note}")
            print(f"  {display}:{n.get('line', '?')}")
            if n.get("signature") and not brief:
                print(f"  sig: {n.get('signature')}")
            if n.get("docstring") and not brief:
                first_line = n.get("docstring", "").splitlines()[0].strip()[:120]
                print(f"  doc: {first_line}")

        if ncallers:
            print(f"\n  callers: {ncallers}")
        if callees:
            print(f"  calls ({len(callees)}): {', '.join(callees)}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def cmd_explain(symbol: str, depth: int = 2) -> int:
    """Print a Claude-ready explanation prompt for a symbol."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        subgraph = client.get_bounded_subgraph(symbol, max_depth=max(1, min(depth, 5)))
    except Exception as e:
        print(f"ERROR: Could not query graph — {e}")
        return 1

    if not subgraph:
        print(f"Symbol '{symbol}' not found in graph. Run 'smt build' first.")
        return 1

    root = subgraph.get("root", {})
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])

    print(f"# Context: {symbol}")
    print("# (paste this to Claude and ask it to explain)")
    print()
    print(f"Symbol : {root.get('name')}  ({root.get('type')})")
    print(f"File   : {root.get('file')}:{root.get('line')}")
    if root.get('docstring'):
        print(f"Docstr : {root['docstring'][:400]}")
    print()
    print(f"Graph  : {len(nodes)} nodes, {len(edges)} edges (depth={depth})")
    for edge in edges:
        src = edge.get('src', '?')
        tgt = edge.get('dst', '?')
        print(f"  {src} --[CALLS]--> {tgt}")
    print()
    print(f"Prompt : Explain what '{symbol}' does, its role in the architecture,")
    print("         and what to be aware of before modifying it.")
    return 0
