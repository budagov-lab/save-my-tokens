"""SMT query commands: context, definition, view, impact, grep."""

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
            print(f"Symbol '{symbol}' not found in graph.")
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


def _fallback_definition(session, symbol: str, pid_clause: str, project_id: str, project_path):
    """When exact name match fails: try Class.method split, then show partial-name suggestions."""
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

    # Stage 2: partial name match — show suggestions, return None
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
        print(f"\n  Or try: smt search \"{term}\"")
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
                node = _fallback_definition(session, symbol, pid_clause, project_id, project_path)
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


def cmd_view(symbol: str, file_filter: Optional[str] = None, context_lines: int = 0) -> int:
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

        # line numbers are 1-indexed; fall back to 30-line window if end_line missing
        start = max(0, line_start - 1 - context_lines)
        end = min(total, (line_end if line_end else line_start + 29) + context_lines)

        label = f"{symbol}  [{', '.join(n.labels)}]"
        range_str = f"lines {start + 1}–{end}" + (f"  (end_line not in graph — showing window)" if not line_end else "")
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
            print(f"Symbol '{symbol}' not found in graph.")
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
             type_filter: Optional[str] = None, top: int = 20) -> int:
    """Text search across symbol names, signatures, and docstrings in the graph."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    project_id = _get_project_id(project_path)
    try:
        client = _get_neo4j_client(project_id)
        pid_clause = "AND n.project_id = $pid" if project_id else ""

        if field == "name":
            field_cond = "toLower(n.name) CONTAINS toLower($pat)"
        elif field == "sig":
            field_cond = "n.signature IS NOT NULL AND toLower(n.signature) CONTAINS toLower($pat)"
        elif field == "doc":
            field_cond = "n.docstring IS NOT NULL AND toLower(n.docstring) CONTAINS toLower($pat)"
        else:
            field_cond = (
                "(toLower(n.name) CONTAINS toLower($pat) "
                "OR (n.signature IS NOT NULL AND toLower(n.signature) CONTAINS toLower($pat)) "
                "OR (n.docstring IS NOT NULL AND toLower(n.docstring) CONTAINS toLower($pat)))"
            )

        type_cond = f"AND n:{type_filter}" if type_filter else ""

        query = f"""
            MATCH (n)
            WHERE {field_cond} {type_cond} {pid_clause}
            RETURN n, labels(n)[0] AS ltype,
                   CASE WHEN toLower(n.name) CONTAINS toLower($pat) THEN 0 ELSE 1 END AS rank
            ORDER BY rank, n.file, n.line
            LIMIT $top
        """

        with client.driver.session() as session:
            rows = session.run(query, pat=pattern, pid=project_id, top=top).data()

        client.driver.close()

        if not rows:
            print(f"No symbols matching '{pattern}'")
            return 1

        print(f"Grep: '{pattern}'  ({len(rows)} result{'s' if len(rows) != 1 else ''})\n")
        pat_lower = pattern.lower()
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

            for label, value in [("sig", n.get("signature")), ("doc", n.get("docstring"))]:
                if value and pat_lower in value.lower():
                    idx = value.lower().index(pat_lower)
                    s = max(0, idx - 40)
                    e = min(len(value), idx + len(pattern) + 40)
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
