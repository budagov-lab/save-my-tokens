"""SMT query commands: context, definition, view, impact, grep."""

import re
import traceback
from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    _get_neo4j_client,
    _get_project_id,
    _get_validation,
    _require_git,
    _resolve_project_path,
)
from src.graph.neo4j_client import compute_depths as _compute_depths


def _resolve_dotted_name(client, symbol: str, project_id: str) -> Optional[str]:
    """Try to resolve 'Class.method' → stored name when exact match fails."""
    if '.' not in symbol:
        return None
    parent_hint, name_part = symbol.rsplit('.', 1)
    pid_clause = "AND n.project_id = $pid" if project_id else ""
    with client.driver.session() as s:
        row = s.run(
            f"MATCH (n {{name: $name}}) WHERE n.parent = $parent {pid_clause} "
            "RETURN n.name AS name LIMIT 1",
            name=name_part, parent=parent_hint, pid=project_id,
        ).single()
    return row["name"] if row else None


def cmd_context(symbol: str, depth: int = 1, callers: bool = False,
                file_filter: Optional[str] = None, compress: bool = False,
                compact: bool = False, brief: bool = False) -> int:
    from src.graph.compressor import compress_subgraph, format_compression_stats
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        max_depth = max(1, min(depth, 10))
        subgraph = client.get_bounded_subgraph(symbol, max_depth=max_depth, file_filter=file_filter)

        if not subgraph:
            resolved = _resolve_dotted_name(client, symbol, _get_project_id(project_path))
            if resolved:
                subgraph = client.get_bounded_subgraph(resolved, max_depth=max_depth, file_filter=file_filter)
        if not subgraph:
            pid_clause = "AND n.project_id = $pid" if _get_project_id(project_path) else ""
            _print_not_found(symbol, client, pid_clause, _get_project_id(project_path),
                             project_path, project_path / '.smt' / 'embeddings')
            client.driver.close()
            return 1

        root = subgraph["root"]
        nodes = subgraph["nodes"]
        edges = subgraph["edges"]

        labels = root.get("labels", [])
        if compact:
            print(f"{root.get('name')} [{', '.join(labels)}] {root.get('file', '?')}:{root.get('line', '?')}")
            if root.get("signature"):
                print(f"sig: {root.get('signature')}")
            if root.get("docstring") and not brief:
                print(f"doc: {root.get('docstring')[:120]}")
        else:
            print(f"\n{root.get('name')}  [{', '.join(labels)}]")
            print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")
            if root.get("signature"):
                print(f"  sig:  {root.get('signature')}")
            if root.get("docstring") and not brief:
                print(f"  doc:  {root.get('docstring')[:120]}")

        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        original_node_count = len(nodes)
        original_edge_count = len(edges)

        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e[0], e[1]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        outbound_calls = [e for e in edge_tuples if e[0] == symbol]
        if outbound_calls:
            if compact:
                call_names = ", ".join(e[1] for e in outbound_calls)
                print(f"calls({len(outbound_calls)}): {call_names}")
            else:
                print(f"\n  calls ({len(outbound_calls)}):")
                for edge in outbound_calls:
                    target = edge[1]
                    target_node = next((n for n in nodes if n["name"] == target), None)
                    file_str = target_node.get("file", "?") if target_node else "?"
                    file_base = Path(file_str).name if file_str != "?" else "?"
                    print(f"    {target}  ({file_base})")

        if cycle_groups:
            for cg in cycle_groups:
                cycle_str = " → ".join(cg.members[:3])
                if len(cg.members) > 3:
                    cycle_str += f" → ... ({len(cg.members)} total)"
                print(f"\n  [Cycle: {cycle_str}]")
                print(f"    {len(cg.members)} functions collapsed")

        if callers or depth > 1:
            with client.driver.session() as session:
                callers_data = session.run(
                    "MATCH (caller)-[:CALLS]->(n {name: $name}) RETURN caller.name AS name, caller.file AS file",
                    name=symbol
                ).data()
                if callers_data:
                    if compact:
                        caller_names = ", ".join(c['name'] for c in callers_data)
                        print(f"callers({len(callers_data)}): {caller_names}")
                    else:
                        print(f"\n  callers ({len(callers_data)}):")
                        for c in callers_data:
                            file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                            print(f"    {c['name']}  ({file_base})")

        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        try:
            from src.graph.validator import format_stale_files_line, format_validation_line
            validation = _get_validation(_resolve_project_path())
        except Exception as e:
            logger.debug(f"Validation check failed: {e}")
            validation = None

        if compact:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                stats_line = f"context: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            else:
                stats_line = f"nodes={len(nodes)} edges={len(edges)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            if validation:
                print(f"{stats_line}  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            else:
                print(stats_line)
        else:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                print(f"\n  context: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
                print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
            else:
                print(f"\n  context: nodes={len(nodes)} edges={len(edges)} depth={max_depth} "
                      f"cycles={len(cycle_groups)} ~tokens={token_estimate}")
            if validation:
                print(f"  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"cmd_context error: {traceback.format_exc()}")
        return 1


def _print_not_found(symbol: str, client, pid_clause: str, project_id: str, project_path, cache_dir) -> None:
    """Print 'not found' with graph name suggestions and semantic fallback.

    Used by context/impact/definition when all resolution attempts fail.
    """
    term = symbol.rsplit('.', 1)[-1]
    with client.driver.session() as s:
        suggestions = s.run(
            f"MATCH (n) WHERE toLower(n.name) CONTAINS toLower($term) {pid_clause} "
            "RETURN n.name AS name, n.parent AS parent, n.file AS file, labels(n)[0] AS type "
            "ORDER BY size(n.name) LIMIT 5",
            term=term, pid=project_id,
        ).data()

    print(f"Symbol '{symbol}' not found in graph.")
    if suggestions:
        print("  Did you mean:")
        for s in suggestions:
            qname = f"{s['parent']}.{s['name']}" if s.get('parent') else s['name']
            try:
                display = str(Path(s['file']).relative_to(project_path))
            except (ValueError, TypeError):
                display = s['file'] or '?'
            print(f"    {qname}  [{s['type']}]  ({display})")
    print(f"\n  Try: smt lookup \"{symbol}\"")


def _fallback_definition(session, symbol: str, pid_clause: str, project_id: str, project_path, cache_dir):
    """When exact name match fails: try Class.method split, then partial-name + semantic suggestions."""
    # Stage 1: user typed Class.method — split and match name + parent
    if '.' in symbol:
        parent_hint, name_part = symbol.rsplit('.', 1)
        fb = session.run(
            f"MATCH (n {{name: $name}}) "
            f"WHERE n.parent = $parent {pid_clause} "
            "RETURN n, CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END as priority "
            "ORDER BY priority LIMIT 1",
            name=name_part, parent=parent_hint, pid=project_id,
        ).single()
        if fb:
            return fb

        # Stage 1b: parent attribute may not be stored — try exact short-name match.
        # Covers cases like Session.resolve_redirects where the graph stores the node
        # as name="resolve_redirects" with no parent field set.
        fb = session.run(
            f"MATCH (n {{name: $name}}) WHERE 1=1 {pid_clause} "
            "RETURN n, CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END as priority "
            "ORDER BY priority LIMIT 1",
            name=name_part, pid=project_id,
        ).single()
        if fb:
            return fb

    # Stage 2: partial name match
    term = symbol.rsplit('.', 1)[-1]
    suggestions = session.run(
        f"MATCH (n) WHERE toLower(n.name) CONTAINS toLower($term) {pid_clause} "
        "RETURN n.name AS name, n.parent AS parent, n.file AS file, labels(n)[0] AS type "
        "ORDER BY size(n.name) LIMIT 5",
        term=term, pid=project_id,
    ).data()

    print(f"Symbol '{symbol}' not found in graph.")
    if suggestions:
        print("  Did you mean:")
        for s in suggestions:
            qname = f"{s['parent']}.{s['name']}" if s.get('parent') else s['name']
            try:
                display = str(Path(s['file']).relative_to(project_path))
            except (ValueError, TypeError):
                display = s['file'] or '?'
            print(f"    {qname}  [{s['type']}]  ({display})")
        print(f"\n  Or try: smt grep \"{term}\"")
    else:
        # Symbol not indexed — may not exist in this checkout or wasn't parsed.
        # Point to smt grep (searches names + docstrings) rather than smt lookup
        # (which requires embeddings and also fails for unknown symbols).
        print(f"  Try: smt grep \"{term}\"")
        if '.' in symbol:
            # Suggest scoping the likely parent file
            parent = symbol.rsplit('.', 1)[0]
            print(f"       smt scope <file.py>   (find which methods {parent!r} actually has)")
    return None


def cmd_definition(symbol: str, file_filter: Optional[str] = None,
                   compact: bool = False, brief: bool = False) -> int:
    """Fast definition lookup — just the signature and 1-hop callees."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        with client.driver.session() as session:
            if not file_filter:
                matches = session.run(
                    f"MATCH (n {{name: $name}}) WHERE 1=1 {pid_clause} "
                    "RETURN n.file AS file, labels(n)[0] AS type, n.line AS line ORDER BY n.file",
                    name=symbol, pid=project_id
                ).data()
                if len(matches) > 1:
                    print(f"Multiple symbols named '{symbol}' found — use --file to disambiguate:\n")
                    for m in matches:
                        try:
                            display = str(Path(m['file']).relative_to(project_path))
                        except (ValueError, TypeError):
                            display = m['file'] or '?'
                        print(f"  [{m['type']}]  {display}:{m['line']}")
                    print(f"\n  e.g.  smt definition {symbol} --file {Path(matches[0]['file']).name}")
                    return 1

            if file_filter:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE n.file CONTAINS $file {pid_clause}
                    RETURN n
                    LIMIT 1
                """
                node = session.run(query, name=symbol, file=file_filter, pid=project_id).single()
            else:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE 1=1 {pid_clause}
                    RETURN n,
                           CASE WHEN n:Function THEN 0
                                WHEN n:Class THEN 1
                                ELSE 2 END as priority
                    ORDER BY priority
                    LIMIT 1
                """
                node = session.run(query, name=symbol, pid=project_id).single()

            if not node:
                cache_dir = project_path / '.smt' / 'embeddings'
                node = _fallback_definition(session, symbol, pid_clause, project_id, project_path, cache_dir)
                if not node:
                    client.driver.close()
                    return 1

            n = node['n']
            if compact:
                print(f"{n.get('name')} [{', '.join(n.labels)}] {n.get('file', '?')}:{n.get('line', '?')}")
                if n.get('signature'):
                    print(f"sig: {n.get('signature')}")
                if n.get('docstring') and not brief:
                    print(f"doc: {n.get('docstring')[:120]}")
            else:
                print(f"\n{n.get('name')}  [{', '.join(n.labels)}]")
                print(f"  file: {n.get('file', '?')}:{n.get('line', '?')}")
                if n.get('signature'):
                    print(f"  sig:  {n.get('signature')}")
                if n.get('docstring') and not brief:
                    print(f"  doc:  {n.get('docstring')}")

            callee_pid = "{project_id: $pid}" if project_id else ""
            callees = session.run(
                f"MATCH (n {{name: $name}})-[:CALLS]->(callee {callee_pid}) "
                f"WHERE 1=1 {pid_clause} "
                "RETURN callee.name AS name, callee.file AS file",
                name=n.get('name'), pid=project_id
            ).data()
            if callees:
                if compact:
                    callee_names = ", ".join(c['name'] for c in callees)
                    print(f"calls({len(callees)}): {callee_names}")
                else:
                    print(f"\n  calls ({len(callees)}):")
                    for c in callees:
                        file_base = Path(c.get("file", "?")).name if c.get("file") else "?"
                        print(f"    {c['name']}  ({file_base})")

            try:
                validation = _get_validation(_resolve_project_path())
                from src.graph.validator import format_stale_files_line, format_validation_line
                if compact:
                    print(f"{format_validation_line(validation)}")
                else:
                    print(f"\n  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            except Exception as e:
                logger.debug(f"Validation check failed: {e}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"cmd_definition error: {traceback.format_exc()}")
        return 1


def cmd_view(symbol: str, file_filter: Optional[str] = None, context_lines: int = 0,
             compact: bool = False, brief: bool = False) -> int:
    """Show only the source lines for a symbol — graph lookup then targeted file read."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        with client.driver.session() as session:
            if file_filter:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE n.file CONTAINS $file {pid_clause}
                    RETURN n LIMIT 1
                """
                row = session.run(query, name=symbol, file=file_filter, pid=project_id).single()
            else:
                query = f"""
                    MATCH (n {{name: $name}})
                    WHERE 1=1 {pid_clause}
                    RETURN n,
                           CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END AS priority
                    ORDER BY priority LIMIT 1
                """
                row = session.run(query, name=symbol, pid=project_id).single()

            if not row and '.' in symbol and not any(
                symbol.endswith(ext) for ext in ('.py', '.ts', '.js', '.go', '.rs', '.java', '.tsx', '.jsx')
            ):
                # Dotted name like Class.method — retry with parent+name split
                left, right = symbol.rsplit('.', 1)
                fallback_q = f"""
                    MATCH (n {{name: $name}})
                    WHERE n.parent CONTAINS $parent {pid_clause}
                    RETURN n,
                           CASE WHEN n:Function THEN 0 WHEN n:Class THEN 1 ELSE 2 END AS priority
                    ORDER BY priority LIMIT 1
                """
                row = session.run(fallback_q, name=right, parent=left, pid=project_id).single()

        client.driver.close()

        if not row:
            _FILE_EXTS = ('.py', '.ts', '.js', '.go', '.rs', '.java', '.tsx', '.jsx')
            if any(symbol.endswith(ext) for ext in _FILE_EXTS) or '/' in symbol or '\\' in symbol:
                print(f"Symbol '{symbol}' not found — looks like a file path.")
                print(f"  smt view takes a symbol name, not a file path.")
                print(f"  Try: smt scope {Path(symbol).name}")
            else:
                print(f"Symbol '{symbol}' not found in graph.")
            return 1

        n = row["n"]
        file_path = n.get("file")
        line_start = n.get("line")
        line_end = n.get("end_line")

        if not file_path or not line_start:
            print(f"Symbol '{symbol}' has no file/line info in graph.")
            return 1

        if not Path(file_path).exists():
            print(f"File not found: {file_path}")
            return 1

        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        # Graph line numbers can be stale (1-2 commits behind). Scan ±20 lines for the
        # actual def/class to correct for drift before slicing the display window.
        sym_bare = symbol.rsplit(".", 1)[-1]  # strip Class. prefix if present
        search_start = max(0, line_start - 20)
        search_end = min(total, line_start + 20)
        for probe in range(search_start, search_end):
            stripped = lines[probe].lstrip()
            if stripped.startswith(f"def {sym_bare}(") or stripped.startswith(f"async def {sym_bare}(") \
                    or stripped.startswith(f"class {sym_bare}(") or stripped.startswith(f"class {sym_bare}:"):
                line_start = probe + 1  # correct to 1-indexed
                break

        # line numbers are 1-indexed; fall back to 30-line window if end_line missing
        start = max(0, line_start - 1 - context_lines)
        end = min(total, (line_end if line_end else line_start + 29) + context_lines)

        _LINE_CAP = 60
        truncated = compact and (end - start) > _LINE_CAP
        if truncated:
            end = start + _LINE_CAP

        label = f"{symbol}  [{', '.join(n.labels)}]"
        range_str = f"lines {start + 1}–{end}" + (f"  (end_line not in graph — showing window)" if not line_end else "")
        if truncated:
            range_str += f"  (truncated at {_LINE_CAP} lines — use Read with offset={start + 1} limit=120 for the full body)"
        print(f"\n{label}")
        print(f"  {file_path}:{line_start}  {range_str}\n")

        width = len(str(end))
        for i, text in enumerate(lines[start:end], start=start + 1):
            marker = ">" if i == line_start else " "
            print(f"  {marker} {str(i).rjust(width)}  {text}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"cmd_view error: {traceback.format_exc()}")
        return 1


def cmd_impact(symbol: str, max_depth: int = 3, compress: bool = False,
               compact: bool = False, brief: bool = False) -> int:
    """Impact analysis — what breaks if I change this symbol?"""
    from src.graph.compressor import compress_subgraph, format_compression_stats
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))

        impact_set = client.get_impact_graph(symbol, max_depth=max_depth)

        if not impact_set:
            resolved = _resolve_dotted_name(client, symbol, _get_project_id(project_path))
            if resolved:
                impact_set = client.get_impact_graph(resolved, max_depth=max_depth)
        if not impact_set:
            pid = _get_project_id(project_path)
            pid_clause = "AND n.project_id = $pid" if pid else ""
            _print_not_found(symbol, client, pid_clause, pid,
                             project_path, project_path / '.smt' / 'embeddings')
            client.driver.close()
            return 1

        root = impact_set["root"]
        nodes = impact_set["nodes"]
        edges = impact_set["edges"]

        labels = root.get("labels", [])
        total_callers = len([n for n in nodes if n["name"] != symbol])
        if compact:
            print(f"Impact: {root.get('name')} [{', '.join(labels)}] {total_callers} caller{'s' if total_callers != 1 else ''} | {root.get('file', '?')}:{root.get('line', '?')}")
        else:
            print(f"\nImpact: {root.get('name')}  [{', '.join(labels)}]  ({total_callers} caller{'s' if total_callers != 1 else ''})")
            print(f"  file: {root.get('file', '?')}:{root.get('line', '?')}")

        depths = _compute_depths(root.get('name', symbol), edges)

        callers_by_depth: dict[int, list[str]] = {}
        for n in nodes:
            node_name = n["name"]
            if node_name != symbol:
                d = depths.get(node_name, max_depth + 1)
                if d not in callers_by_depth:
                    callers_by_depth[d] = []
                callers_by_depth[d].append(node_name)

        for depth_level in sorted(callers_by_depth.keys()):
            callers_list = callers_by_depth[depth_level]
            if compact:
                print(f"depth{depth_level}({len(callers_list)}): {', '.join(sorted(callers_list))}")
            else:
                label = "direct callers" if depth_level == 1 else f"indirect callers — depth {depth_level}"
                print(f"\n  {label} ({len(callers_list)}):")
                for caller in sorted(callers_list):
                    caller_node = next((n for n in nodes if n["name"] == caller), None)
                    file_base = Path(caller_node.get("file", "?")).name if caller_node else "?"
                    print(f"    {caller}  ({file_base})")

        original_node_count = len(nodes)
        original_edge_count = len(edges)

        node_names = [n["name"] for n in nodes]
        edge_tuples = [(e["src"], e["dst"]) for e in edges]
        acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        compression_result = None
        if compress:
            cycle_members = {m for cg in cycle_groups for m in cg.members}
            compression_result = compress_subgraph(symbol, node_names, edge_tuples, cycle_members)
            nodes = [n for n in nodes if n["name"] in compression_result.nodes]
            edges = [(e["src"], e["dst"]) for e in edges
                    if (e["src"], e["dst"]) in compression_result.edges]
            depths = _compute_depths(root.get('name', symbol), edges)
            callers_by_depth = {}
            for n in nodes:
                node_name = n["name"]
                if node_name != symbol:
                    d = depths.get(node_name, max_depth + 1)
                    if d not in callers_by_depth:
                        callers_by_depth[d] = []
                    callers_by_depth[d].append(node_name)
            node_names = [n["name"] for n in nodes]
            edge_tuples = [(e[0], e[1]) for e in edges]
            acyclic_nodes, cycle_groups = detect_cycles(node_names, edge_tuples)

        if cycle_groups:
            for cg in cycle_groups:
                cycle_str = " → ".join(cg.members[:3])
                if len(cg.members) > 3:
                    cycle_str += f" → ... ({len(cg.members)} total)"
                print(f"\n  [Cycle: {cycle_str}]")
                print(f"    {len(cg.members)} functions in cycle — changing {symbol} affects the entire cycle")

        token_estimate = sum(len(n["name"]) + len(n.get("file", "")) + 30 for n in nodes) // 4

        try:
            from src.graph.validator import format_stale_files_line, format_validation_line
            validation = _get_validation(_resolve_project_path())
        except Exception as e:
            logger.debug(f"Validation check failed: {e}")
            validation = None

        if compact:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                stats_line = f"impact: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            else:
                stats_line = f"nodes={len(nodes)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}"
            if validation:
                print(f"{stats_line}  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)
            else:
                print(stats_line)
        else:
            if compression_result and compression_result.bridges:
                compression_line = format_compression_stats(original_node_count, original_edge_count,
                                                           compression_result)
                print(f"\n  impact: {compression_line} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
                print(f"  compressed: {len(compression_result.bridges)} bridge functions removed")
            else:
                print(f"\n  impact: nodes={len(nodes)} depth={max_depth} cycles={len(cycle_groups)} ~tokens={token_estimate}")
            if validation:
                print(f"  {format_validation_line(validation)}")
                stale = format_stale_files_line(validation)
                if stale:
                    print(stale)

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"cmd_impact error: {traceback.format_exc()}")
        return 1


def cmd_grep(pattern: str, field: Optional[str] = None,
             type_filter: Optional[str] = None, top: int = 20,
             module: Optional[str] = None) -> int:
    """Text search across symbol names, signatures, and docstrings in the graph."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    # Strip source-style prefixes agents tend to copy from grep output
    for prefix in ("def ", "class ", "async def "):
        if pattern.startswith(prefix):
            pattern = pattern[len(prefix):]
            break

    # Support | alternation (POSIX \| or plain |): split into OR-of-CONTAINS
    raw_alts = [p.strip() for p in re.split(r"\\?\|", pattern) if p.strip()]
    alts = raw_alts if len(raw_alts) > 1 else [pattern]

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""
        module_cond = "AND toLower(n.file) CONTAINS toLower($module)" if module else ""

        def _make_field_cond(pat_param: str) -> str:
            if field == "name":
                return f"toLower(n.name) CONTAINS toLower({pat_param})"
            elif field == "doc":
                return f"n.docstring IS NOT NULL AND toLower(n.docstring) CONTAINS toLower({pat_param})"
            return (
                f"(toLower(n.name) CONTAINS toLower({pat_param}) "
                f"OR (n.docstring IS NOT NULL AND toLower(n.docstring) CONTAINS toLower({pat_param})))"
            )

        if len(alts) == 1:
            field_cond = _make_field_cond("$pat")
            type_cond = f"AND n:{type_filter}" if type_filter else ""
            query = f"""
                MATCH (n)
                WHERE {field_cond} {type_cond} {module_cond} {pid_clause}
                RETURN n, labels(n)[0] AS ltype,
                       CASE WHEN toLower(n.name) CONTAINS toLower($pat) THEN 0 ELSE 1 END AS rank
                ORDER BY rank, n.file, n.line
                LIMIT $top
            """
            with client.driver.session() as session:
                rows = session.run(query, pat=alts[0], pid=project_id, top=top,
                                   module=module or "").data()
        else:
            # Multi-alternation: run a separate CONTAINS per term, union results
            seen_ids: set = set()
            rows = []
            type_cond = f"AND n:{type_filter}" if type_filter else ""
            with client.driver.session() as session:
                for alt in alts:
                    field_cond = _make_field_cond("$pat")
                    q = f"""
                        MATCH (n)
                        WHERE {field_cond} {type_cond} {module_cond} {pid_clause}
                        RETURN n, labels(n)[0] AS ltype,
                               CASE WHEN toLower(n.name) CONTAINS toLower($pat) THEN 0 ELSE 1 END AS rank
                        ORDER BY rank, n.file, n.line
                        LIMIT $top
                    """
                    for r in session.run(q, pat=alt, pid=project_id, top=top,
                                         module=module or "").data():
                        n = r["n"]
                        nid = (n.get("file"), n.get("name"), n.get("line"))
                        if nid not in seen_ids:
                            seen_ids.add(nid)
                            rows.append(r)

        client.driver.close()

        if not rows:
            print(f"No symbols matching '{pattern}'")
            return 0

        print(f"Grep: '{pattern}'  ({len(rows)} result{'s' if len(rows) != 1 else ''})\n")
        pat_lower = alts[0].lower()
        for row in rows:
            n = row["n"]
            sym_type = row["ltype"] or "?"
            name = n.get("name", "?")
            parent = n.get("parent")
            qname = f"{parent}.{name}" if parent else name
            try:
                file_display = str(Path(n.get("file", "?")).relative_to(project_path))
            except (ValueError, TypeError):
                file_display = n.get("file") or "?"

            print(f"  {qname}  [{sym_type}]")
            print(f"    {file_display}:{n.get('line', '?')}")

            for label, value in [("doc", n.get("docstring"))]:
                if value and pat_lower in value.lower():
                    idx = value.lower().index(pat_lower)
                    s = max(0, idx - 40)
                    e = min(len(value), idx + len(pat_lower) + 40)
                    snippet = value[s:e].replace("\n", " ")
                    if s > 0:
                        snippet = "..." + snippet
                    if e < len(value):
                        snippet += "..."
                    print(f"    {label}: {snippet}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"cmd_grep error: {traceback.format_exc()}")
        return 1


# ---------------------------------------------------------------------------
# orient
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "about", "after", "also", "around", "argument", "before", "between",
    "broad", "call", "calls", "change", "class", "code", "concept", "could",
    "define", "defined", "does", "entry", "every", "file", "files", "find",
    "first", "from", "function", "handle", "handles", "handling", "have",
    "here", "hook", "hooks", "implement", "implemented", "immediately",
    "improve", "into", "just", "library", "look", "main", "make", "method",
    "methods", "need", "only", "other", "place", "point", "points", "return",
    "should", "some", "struct", "structure", "symbol", "than", "that",
    "their", "then", "there", "these", "this", "those", "understand", "used",
    "using", "what", "when", "where", "which", "will", "with", "work",
    "would", "write", "your",
}


def cmd_orient(task_words: list, with_source: bool = False) -> int:
    """Pre-orient: extract symbol-like terms from task text and grep the graph for each.

    Designed to be run as the first command in the smt-analysis skill via:
        !`smt orient $ARGUMENTS --source`
    The output is injected into the skill prompt so the agent starts with
    relevant graph context already visible, reducing lookup turns.

    --source: also print smt view source for the top 2 Function/Class symbols found,
    so the agent has source bodies available without a follow-up Read call.
    """
    task = " ".join(task_words)

    # Extract CamelCase (likely class/method names) and long snake_case (likely function names).
    camel = re.findall(r'\b[A-Z][a-z][A-Za-z]{2,}\b', task)
    snake = re.findall(r'\b[a-z][a-z_]{4,}\b', task)
    candidates = camel + snake  # CamelCase first — more specific

    seen: set = set()
    terms: list = []
    for c in candidates:
        low = c.lower()
        if low not in _STOP_WORDS and low not in seen:
            seen.add(low)
            terms.append(c)
        if len(terms) >= 5:
            break

    if not terms:
        return 0  # nothing to orient on — agent will figure it out

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 0  # silently skip if not in a git repo

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""
        print("## Graph context (auto-extracted from task)\n")

        found_any = False
        top_symbols: list = []  # (name,) for source injection — max 2 Function/Class

        for term in terms:
            with client.driver.session() as session:
                # Match names only (not docstrings) so we find actual symbols,
                # not accidental docstring hits on common English words.
                rows = session.run(
                    f"""
                    MATCH (n)
                    WHERE toLower(n.name) CONTAINS toLower($pat)
                    AND NOT n:File AND NOT n:Module
                    {pid_clause}
                    RETURN n.name AS name, labels(n)[0] AS ltype, n.file AS file, n.line AS line
                    ORDER BY
                      CASE WHEN toLower(n.name) = toLower($pat) THEN 0 ELSE 1 END,
                      n.file
                    LIMIT 6
                    """,
                    pat=term, pid=project_id
                ).data()

            if not rows:
                continue

            found_any = True
            print(f"### {term}")
            for r in rows:
                try:
                    display = str(Path(r['file']).relative_to(project_path)) if r.get('file') else '?'
                except (ValueError, TypeError):
                    display = r.get('file') or '?'
                print(f"  {r['name']}  [{r['ltype']}]  {display}:{r.get('line', '?')}")
                # Collect exact-match Function/Class for source injection
                if (with_source
                        and len(top_symbols) < 2
                        and r['ltype'] in ('Function', 'Class')
                        and r['name'].lower() == term.lower()):
                    top_symbols.append(r['name'])
            print()

        if not found_any:
            print("(no graph matches for task terms — use smt grep manually)\n")

        # Source injection: show symbol bodies so agent has source without a Read call
        if with_source and top_symbols:
            print("## Auto-context (symbols found in this task)\n")
            for sym in top_symbols:
                print(f"```  smt view {sym}")
                cmd_view(sym)
                print("```\n")

        return 0
    except Exception as e:
        # orient is best-effort — never fail hard
        logger.debug(f"cmd_orient error: {e}")
        return 0
