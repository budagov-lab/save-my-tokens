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
