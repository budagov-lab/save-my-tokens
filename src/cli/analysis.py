"""SMT architecture analysis commands: cycles, hot, path, modules, changes, complexity, scope,
bottleneck, layer, breaking-changes, list, unused."""

import json
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    Colors,
    _get_neo4j_client,
    _get_project_id,
    _require_git,
    _resolve_project_path,
)

# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list(module: Optional[str] = None, type_filter: Optional[str] = None, limit: int = 0) -> int:
    """Enumerate all symbols in the graph, optionally filtered by file/module path and type."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    label_filter = type_filter.capitalize() if type_filter else None

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            conditions = ["NOT n:Commit", "n.file IS NOT NULL"]
            params: dict = {"pid": pid}
            if module:
                conditions.append("n.file CONTAINS $module")
                params["module"] = module
            if label_filter:
                conditions.append(f"n:{label_filter}")

            where_clause = " AND ".join(conditions)
            query = f"""
                MATCH (n {{project_id: $pid}})
                WHERE {where_clause}
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type
                ORDER BY n.file, n.line
            """
            rows = session.run(query, **params).data()

        if not rows:
            filters = []
            if module:
                filters.append(f"module={module!r}")
            if label_filter:
                filters.append(f"type={label_filter}")
            suffix = f" ({', '.join(filters)})" if filters else ""
            print(f"No symbols found{suffix}.")
            return 0

        total = len(rows)
        if limit and limit < total:
            rows = rows[:limit]

        from collections import defaultdict
        by_file: dict = defaultdict(list)
        for row in rows:
            by_file[row['file'] or '(unknown)'].append(row)

        filter_parts = []
        if module:
            filter_parts.append(f"module: {module!r}")
        if label_filter:
            filter_parts.append(f"type: {label_filter}")
        filter_note = f"  ({', '.join(filter_parts)})" if filter_parts else ""
        shown = f", showing first {limit}" if limit and limit < total else ""
        print(f"\n{total} symbols across {len(by_file)} files{filter_note}{shown}\n")

        for file_path in sorted(by_file):
            symbols = by_file[file_path]
            try:
                display = str(Path(file_path).relative_to(project_path))
            except ValueError:
                display = file_path
            print(f"  {display}  ({len(symbols)} symbols)")
            for sym in symbols:
                line_str = f":{sym['line']}" if sym['line'] else ""
                print(f"    {sym['name']:<40} [{sym['type']}]{line_str}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# unused
# ---------------------------------------------------------------------------

def cmd_unused(include_dunders: bool = False) -> int:
    """Find symbols with no callers — dead code candidates."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                  AND NOT ()-[:CALLS]->(n)
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type
                ORDER BY n.file, n.line
                """,
                pid=pid
            ).data()

        if not include_dunders:
            rows = [r for r in rows if not (r['name'] or '').startswith('__')]

        if not rows:
            print("No unused symbols found — everything is reachable.")
            return 0

        print(f"\n{len(rows)} symbols with no callers (potential dead code):\n")
        for row in rows:
            try:
                display = str(Path(row['file']).relative_to(project_path))
            except (ValueError, TypeError):
                display = Path(row['file'] or '?').name
            line_str = f":{row['line']}" if row['line'] else ""
            print(f"  {row['name']:<45} [{row['type']}]  {display}{line_str}")

        hint = ""
        if not include_dunders:
            hint = "  (dunder methods hidden — use --include-dunders to show them)\n"
        print(f"\n{hint}Note: entry points, public APIs, and test helpers are expected to have no in-graph callers.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------

def cmd_cycles() -> int:
    """Detect and display all circular dependencies in the graph."""
    from src.graph.cycle_detector import detect_cycles

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            node_rows = session.run(
                "MATCH (n {project_id: $pid}) WHERE NOT n:Commit RETURN n.name AS name",
                pid=pid
            ).data()
            edge_rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                RETURN a.name AS src, b.name AS dst
                """,
                pid=pid
            ).data()

        name_to_file: dict = {}
        with client.driver.session() as session2:
            file_rows = session2.run(
                "MATCH (n {project_id: $pid}) WHERE n.file IS NOT NULL RETURN n.name AS name, n.file AS file",
                pid=pid,
            ).data()
        for r in file_rows:
            if r['name']:
                name_to_file[r['name']] = r['file']

        node_names = [r['name'] for r in node_rows if r['name']]
        edge_tuples = [(r['src'], r['dst']) for r in edge_rows if r['src'] and r['dst']]

        _, cycle_groups = detect_cycles(node_names, edge_tuples)

        if not cycle_groups:
            print("No circular dependencies found.")
            return 0

        cycle_groups_sorted = sorted(cycle_groups, key=lambda cg: len(cg.members), reverse=True)

        print(f"\n{len(cycle_groups_sorted)} circular dependency group(s) (largest first):\n")
        for i, cg in enumerate(cycle_groups_sorted, 1):
            cycle_str = " -> ".join(cg.members) + f" -> {cg.members[0]}"
            print(f"  [{i}] {len(cg.members)} symbols in cycle:")
            print(f"       {cycle_str}")
            for sym in cg.members:
                f_path = name_to_file.get(sym, "")
                if f_path:
                    try:
                        f_display = str(Path(f_path).relative_to(project_path))
                    except ValueError:
                        f_display = f_path
                    print(f"         {sym:<40}  {f_display}")
            print()

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# hot
# ---------------------------------------------------------------------------

def cmd_hot(limit: int = 20) -> int:
    """Most-called symbols — coupling hotspots."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (caller {project_id: $pid})-[:CALLS]->(n {project_id: $pid})
                WHERE NOT n:Commit
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       count(DISTINCT caller) AS caller_count
                ORDER BY caller_count DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No call edges found — build the graph first: smt build")
            return 0

        print(f"\nTop {len(rows)} most-called symbols (coupling hotspots):\n")
        for i, row in enumerate(rows, 1):
            file_base = Path(row['file'] or '?').name
            print(f"  {i:2}. {row['name']:<45} [{row['type']}]  callers={row['caller_count']}  ({file_base})")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

def cmd_path(symbol_a: str, symbol_b: str) -> int:
    """Shortest dependency path between two symbols."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            result = session.run(
                """
                MATCH (a {name: $a, project_id: $pid}), (b {name: $b, project_id: $pid})
                MATCH path = shortestPath((a)-[:CALLS*]->(b))
                RETURN [node IN nodes(path) | node.name] AS path_names,
                       [node IN nodes(path) | node.file] AS path_files,
                       length(path) AS hops
                LIMIT 1
                """,
                a=symbol_a, b=symbol_b, pid=pid
            ).single()

        if not result:
            with client.driver.session() as session:
                a_cnt = session.run(
                    "MATCH (n {name: $name, project_id: $pid}) RETURN count(n) AS cnt",
                    name=symbol_a, pid=pid
                ).single()['cnt']
                b_cnt = session.run(
                    "MATCH (n {name: $name, project_id: $pid}) RETURN count(n) AS cnt",
                    name=symbol_b, pid=pid
                ).single()['cnt']

            if a_cnt == 0:
                print(f"Symbol '{symbol_a}' not found in graph.")
            elif b_cnt == 0:
                print(f"Symbol '{symbol_b}' not found in graph.")
            else:
                print(f"No dependency path found: {symbol_a} → {symbol_b}")
                print("  (no CALLS chain exists between these symbols in this direction)")
            return 1

        hops = result['hops']
        path_names = result['path_names']
        path_files = result['path_files']

        print(f"\nShortest path: {symbol_a} → {symbol_b}  ({hops} hop{'s' if hops != 1 else ''})\n")
        for i, (name, fpath) in enumerate(zip(path_names, path_files)):
            file_base = Path(fpath or '?').name
            arrow = "  →  " if i < len(path_names) - 1 else ""
            print(f"  [{i}] {name}  ({file_base}){arrow}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------

def cmd_modules() -> int:
    """Files ranked by symbol count and cross-file coupling."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            sym_rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND n.file IS NOT NULL
                RETURN n.file AS file, count(n) AS symbol_count
                ORDER BY symbol_count DESC
                """,
                pid=pid
            ).data()

            coupling_rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                WHERE a.file <> b.file AND a.file IS NOT NULL AND b.file IS NOT NULL
                UNWIND [a.file, b.file] AS file
                RETURN file, count(*) AS coupling
                """,
                pid=pid
            ).data()

        if not sym_rows:
            print("No symbols found — build the graph first: smt build")
            return 0

        coupling_map = {r['file']: r['coupling'] for r in coupling_rows}

        sorted_rows = sorted(
            sym_rows,
            key=lambda r: (-(coupling_map.get(r['file'], 0)), -r['symbol_count'])
        )

        print(f"\n{len(sorted_rows)} modules ranked by coupling:\n")
        col = 52
        print(f"  {'Module':<{col}} {'Symbols':>7}  {'Coupling':>8}")
        print(f"  {'-'*col} {'-'*7}  {'-'*8}")

        for row in sorted_rows:
            file_path = row['file'] or '(unknown)'
            try:
                display = str(Path(file_path).relative_to(project_path))
            except ValueError:
                display = Path(file_path).name
            coupling = coupling_map.get(row['file'], 0)
            if len(display) > col:
                display = "..." + display[-(col - 3):]
            print(f"  {display:<{col}} {row['symbol_count']:>7}  {coupling:>8}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------

def cmd_changes(commit_range: str = 'HEAD~1..HEAD') -> int:
    """Show symbols in git-changed files with caller impact, pinpointing changed lines."""
    import re

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        status_result = subprocess.run(
            ['git', 'diff', '--name-status', commit_range],
            cwd=project_path, capture_output=True, text=True
        )
        if status_result.returncode != 0:
            print(f"ERROR: git diff failed: {status_result.stderr.strip()}")
            print(f"  Make sure {commit_range!r} is a valid git range.")
            return 1

        file_statuses: dict = {}
        for line in status_result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split('\t')
            status = parts[0][0]
            fname = parts[-1]
            file_statuses[str(project_path / fname)] = status

        if not file_statuses:
            print(f"No file changes found in range: {commit_range}")
            return 0

        modified_abs = [p for p, s in file_statuses.items() if s == 'M']
        file_ranges: dict = {}
        if modified_abs:
            rel_files = [str(Path(f).relative_to(project_path)) for f in modified_abs]
            hunk_result = subprocess.run(
                ['git', 'diff', '--unified=0', commit_range, '--'] + rel_files,
                cwd=project_path, capture_output=True, text=True
            )
            current = None
            for line in hunk_result.stdout.splitlines():
                if line.startswith('+++ b/'):
                    current = str(project_path / line[6:].strip())
                elif line.startswith('@@') and current:
                    m = re.search(r'\+(\d+)(?:,(\d+))?', line)
                    if m:
                        start = int(m.group(1))
                        count = int(m.group(2)) if m.group(2) is not None else 1
                        if count > 0:
                            file_ranges.setdefault(current, []).append((start, start + count - 1))

        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file IN $files AND NOT n:Commit
                WITH n,
                     size([(caller {project_id: $pid})-[:CALLS]->(n) | caller]) AS caller_count
                RETURN n.name AS name, n.file AS file, n.line AS line,
                       labels(n)[0] AS type, caller_count
                ORDER BY n.file, n.line
                """,
                pid=pid, files=list(file_statuses.keys())
            ).data()

        if not rows:
            print(f"No indexed symbols found in changed files for range: {commit_range}")
            print(f"  {len(file_statuses)} file(s) changed — run 'smt build' if the graph is empty.")
            return 0

        from collections import defaultdict
        by_file: dict = defaultdict(list)
        for row in rows:
            by_file[row['file']].append(row)

        STATUS_LABEL = {'A': 'added', 'D': 'deleted', 'M': 'modified', 'R': 'renamed'}

        def sym_in_range(sym_line, ranges) -> bool:
            if not ranges or not sym_line:
                return False
            return any(s <= sym_line <= e for s, e in ranges)

        print(f"\nChanges: {commit_range}\n")

        total_changed_syms = 0
        for abs_path in sorted(by_file):
            syms = by_file[abs_path]
            status = file_statuses.get(abs_path, 'M')
            label = STATUS_LABEL.get(status, 'changed')
            try:
                display = str(Path(abs_path).relative_to(project_path))
            except ValueError:
                display = abs_path

            ranges = file_ranges.get(abs_path, [])

            if status in ('A', 'D'):
                direct = syms
                indirect: list = []
            else:
                direct = [s for s in syms if sym_in_range(s.get('line'), ranges)]
                indirect = [s for s in syms if not sym_in_range(s.get('line'), ranges)]

            total_changed_syms += len(direct)
            print(f"  {display}  [{label}]")

            if direct:
                direct.sort(key=lambda s: s['caller_count'], reverse=True)
                print(f"    changed ({len(direct)}):")
                for sym in direct:
                    callers = sym['caller_count']
                    impact = f"  <- {callers} caller{'s' if callers != 1 else ''}" if callers else ""
                    print(f"      {sym['name']:<42} [{sym['type']}]{impact}")

            if indirect and status == 'M':
                shown = indirect[:4]
                print(f"    unchanged in file ({len(indirect)}):")
                for sym in shown:
                    callers = sym['caller_count']
                    impact = f"  <- {callers}" if callers else ""
                    print(f"      {sym['name']:<42} [{sym['type']}]{impact}")
                if len(indirect) > 4:
                    print(f"      ... and {len(indirect) - 4} more")
            print()

        total_affected_callers = sum(
            s['caller_count'] for syms in by_file.values() for s in syms if s['caller_count']
        )
        print(f"  {total_changed_syms} directly-changed symbols across {len(by_file)} files"
              f"  ({total_affected_callers} total caller edges affected)")
        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        logger.debug("cmd_changes error", exc_info=True)
        return 1


# ---------------------------------------------------------------------------
# complexity
# ---------------------------------------------------------------------------

def cmd_complexity(limit: int = 20) -> int:
    """Rank symbols by fan-in × fan-out — identifies 'god functions'."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                WITH n,
                     size([(caller {project_id: $pid})-[:CALLS]->(n) | caller]) AS fan_in,
                     size([(n)-[:CALLS]->(callee {project_id: $pid}) | callee]) AS fan_out
                WHERE fan_in > 0 OR fan_out > 0
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       fan_in, fan_out, (fan_in * fan_out) AS score
                ORDER BY score DESC, fan_in DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No symbols with call edges found — build the graph first: smt build")
            return 0

        print(f"\nTop {len(rows)} by complexity (fan-in × fan-out):\n")
        print(f"  {'Symbol':<45} {'Type':<10} {'In':>4}  {'Out':>4}  {'Score':>6}  File")
        print(f"  {'-'*45} {'-'*10} {'-'*4}  {'-'*4}  {'-'*6}  ----")

        for row in rows:
            try:
                file_display = str(Path(row['file']).relative_to(project_path))
            except (ValueError, TypeError):
                file_display = Path(row['file'] or '?').name
            print(
                f"  {row['name']:<45} {row['type']:<10} "
                f"{row['fan_in']:>4}  {row['fan_out']:>4}  {row['score']:>6}  {file_display}"
            )

        print("\nScore = callers × callees.  High score = hard to refactor + large blast radius.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------

def cmd_scope(file_filter: str) -> int:
    """File-level surface analysis: exports, imports, internal symbols."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            file_rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file IS NOT NULL AND n.file CONTAINS $filter AND NOT n:Commit
                RETURN DISTINCT n.file AS file ORDER BY n.file
                """,
                pid=pid, filter=file_filter
            ).data()

        if not file_rows:
            print(f"No symbols found for file filter: {file_filter!r}")
            return 1

        if len(file_rows) > 1:
            print(f"Multiple files match {file_filter!r} — be more specific:\n")
            for r in file_rows[:10]:
                try:
                    print(f"  {Path(r['file']).relative_to(project_path)}")
                except ValueError:
                    print(f"  {r['file']}")
            return 1

        file_abs = file_rows[0]['file']
        try:
            display = str(Path(file_abs).relative_to(project_path))
        except ValueError:
            display = file_abs

        with client.driver.session() as session:
            all_syms = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file = $file AND NOT n:Commit
                RETURN n.name AS name, n.line AS line, labels(n)[0] AS type
                ORDER BY n.line
                """,
                pid=pid, file=file_abs
            ).data()

            exports = session.run(
                """
                MATCH (caller {project_id: $pid})-[:CALLS]->(n {project_id: $pid})
                WHERE n.file = $file AND caller.file <> $file
                RETURN n.name AS name, n.line AS line, labels(n)[0] AS type,
                       n.docstring AS docstring,
                       count(DISTINCT caller) AS external_callers,
                       collect(DISTINCT caller.file)[..3] AS sample_files
                ORDER BY external_callers DESC
                """,
                pid=pid, file=file_abs
            ).data()

            imports = session.run(
                """
                MATCH (n {project_id: $pid})-[:CALLS]->(dep {project_id: $pid})
                WHERE n.file = $file AND dep.file <> $file
                RETURN dep.name AS name, dep.file AS dep_file,
                       labels(dep)[0] AS type,
                       count(DISTINCT n) AS usage_count
                ORDER BY dep.file, dep.name
                """,
                pid=pid, file=file_abs
            ).data()

        exported_names = {r['name'] for r in exports}
        imported_names = {r['name'] for r in imports}
        internal_syms = [
            s for s in all_syms
            if s['name'] not in exported_names and s['name'] not in imported_names
        ]

        print(f"\nScope: {display}\n")
        print(f"  {len(all_syms)} symbols total  |  "
              f"{len(exports)} exported  |  "
              f"{len(imports)} imported  |  "
              f"{len(internal_syms)} internal\n")

        if exports:
            print(f"  exports — called by other files ({len(exports)}):")
            for r in exports:
                caller_files = [Path(f).name for f in (r.get('sample_files') or [])]
                suffix = (f"  <- {r['external_callers']} caller{'s' if r['external_callers'] != 1 else ''}"
                          f" ({', '.join(caller_files[:2])}{'...' if len(caller_files) > 2 else ''})")
                doc = r.get('docstring') or ''
                doc_line = doc.splitlines()[0].strip()[:60] if doc else ''
                doc_suffix = f"  # {doc_line}" if doc_line else ""
                print(f"    {r['name']:<45} [{r['type']}]{suffix}{doc_suffix}")

        if imports:
            from collections import defaultdict
            by_src: dict = defaultdict(list)
            for r in imports:
                by_src[r['dep_file']].append(r)
            print(f"\n  imports — calls into other files ({len(imports)} symbols from {len(by_src)} files):")
            for dep_file in sorted(by_src):
                deps = by_src[dep_file]
                try:
                    dep_display = str(Path(dep_file).relative_to(project_path))
                except ValueError:
                    dep_display = Path(dep_file).name
                print(f"    from {dep_display}:")
                for dep in deps:
                    print(f"      {dep['name']}  [{dep['type']}]")

        if internal_syms:
            print(f"\n  internal — not directly coupled across files ({len(internal_syms)}):")
            for sym in internal_syms:
                line_str = f":{sym['line']}" if sym['line'] else ""
                print(f"    {sym['name']:<45} [{sym['type']}]{line_str}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# bottleneck
# ---------------------------------------------------------------------------

def cmd_bottleneck(limit: int = 10) -> int:
    """Find architectural bottleneck nodes — symbols that bridge distinct file clusters."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE NOT n:Commit AND NOT n:File AND NOT n:Module
                OPTIONAL MATCH (caller {project_id: $pid})-[:CALLS]->(n)
                  WHERE caller.file <> n.file
                WITH n, collect(DISTINCT caller.file) AS caller_files
                OPTIONAL MATCH (n)-[:CALLS]->(callee {project_id: $pid})
                  WHERE callee.file <> n.file
                WITH n, caller_files, collect(DISTINCT callee.file) AS callee_files
                WHERE size(caller_files) > 0 AND size(callee_files) > 0
                RETURN n.name AS name, n.file AS file, labels(n)[0] AS type,
                       size(caller_files) AS caller_file_count,
                       size(callee_files) AS callee_file_count,
                       size(caller_files) * size(callee_files) AS bridge_score,
                       caller_files, callee_files
                ORDER BY bridge_score DESC
                LIMIT $limit
                """,
                pid=pid, limit=limit
            ).data()

        if not rows:
            print("No cross-file call edges found — the graph may be empty or all code is in one file.")
            return 0

        print(f"\nTop {limit} architectural bottlenecks (cross-file bridge score):\n")
        print(f"  {'Symbol':<45} {'Type':<10} {'Caller files':>12}  {'Callee files':>12}  {'Score':>6}")
        print(f"  {'-'*45} {'-'*10} {'-'*12}  {'-'*12}  {'-'*6}")

        for row in rows:
            file_base = Path(row['file'] or '?').name
            print(
                f"  {row['name']:<45} {row['type']:<10} "
                f"{row['caller_file_count']:>12}  {row['callee_file_count']:>12}  "
                f"{row['bridge_score']:>6}  ({file_base})"
            )
            caller_files = [Path(f).name for f in (row.get('caller_files') or [])[:3]]
            callee_files = [Path(f).name for f in (row.get('callee_files') or [])[:3]]
            if caller_files and callee_files:
                print(f"    {', '.join(caller_files)} --> [this] --> {', '.join(callee_files)}")

        print("\nScore = (distinct caller files) × (distinct callee files) via cross-file edges.")
        print("High score = structural bridge. Refactoring these requires coordinating across files.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# layer
# ---------------------------------------------------------------------------

_DEFAULT_LAYERS_CONFIG = {
    "_comment": (
        "Layers are ordered from highest (index 0) to lowest (last index). "
        "A layer may only call downward (higher index). "
        "Edit 'paths' to match your project layout — use file path substrings. "
        "Add 'allowlist' entries for intentional cross-layer dependencies."
    ),
    "layers": [
        {"name": "cli",      "paths": ["cli/", "cmd/", "main.py", "_cli.py"]},
        {"name": "api",      "paths": ["api/", "routes/", "views/", "handlers/"]},
        {"name": "services", "paths": ["services/", "usecases/", "application/"]},
        {"name": "domain",   "paths": ["domain/", "models/", "entities/"]},
        {"name": "infra",    "paths": ["db/", "repo", "storage/", "clients/"]},
        {"name": "config",   "paths": ["config.py", "settings.py", "config/"]},
    ],
    "allowlist": [
        # {"from": "infra", "to": "domain", "reason": "Repository returns domain entities"}
    ],
}


def cmd_layer(config_path: Optional[str] = None) -> int:
    """Detect architecture layer violations: calls from lower layers into higher ones."""
    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    cfg_file = Path(config_path) if config_path else project_path / '.smt_layers.json'
    if cfg_file.exists():
        with open(cfg_file, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        print(f"Layer config: {cfg_file}")
    else:
        cfg = _DEFAULT_LAYERS_CONFIG
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Created default layer config: {cfg_file}")
        print("Edit it to match your project layout, then re-run.\n")

    layers = cfg.get('layers', [])
    if not layers:
        print("ERROR: No layers defined in config.")
        return 1

    raw_allowlist = cfg.get('allowlist', [])
    allowlist: set = {(e['from'], e['to']) for e in raw_allowlist if 'from' in e and 'to' in e}

    def _file_layer(file_path: str) -> Optional[int]:
        for i, layer in enumerate(layers):
            for pattern in layer.get('paths', []):
                if pattern in file_path:
                    return i
        return None

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        with client.driver.session() as session:
            rows = session.run(
                """
                MATCH (a {project_id: $pid})-[:CALLS]->(b {project_id: $pid})
                WHERE a.file <> b.file
                  AND a.file IS NOT NULL AND b.file IS NOT NULL
                RETURN a.name AS src_name, a.file AS src_file,
                       b.name AS dst_name, b.file AS dst_file
                """,
                pid=pid
            ).data()

        if not rows:
            print("No cross-file call edges found in graph.")
            return 0

        violations = []
        allowed_violations = []
        unclassified_files: set = set()

        for row in rows:
            src_layer = _file_layer(row['src_file'])
            dst_layer = _file_layer(row['dst_file'])

            if src_layer is None:
                unclassified_files.add(row['src_file'])
            if dst_layer is None:
                unclassified_files.add(row['dst_file'])

            if src_layer is None or dst_layer is None:
                continue

            if src_layer > dst_layer:
                src_name = layers[src_layer]['name']
                dst_name = layers[dst_layer]['name']
                entry = {
                    'src_name': row['src_name'],
                    'src_file': row['src_file'],
                    'src_layer': src_name,
                    'dst_name': row['dst_name'],
                    'dst_file': row['dst_file'],
                    'dst_layer': dst_name,
                }
                if (src_name, dst_name) in allowlist:
                    allowed_violations.append(entry)
                else:
                    violations.append(entry)

        print("\nLayer stack (index 0 = top, can call downward only):\n")
        for i, layer in enumerate(layers):
            print(f"  [{i}] {layer['name']:<12} — {', '.join(layer['paths'])}")

        if not violations:
            print(f"\n{Colors.GREEN}[OK]{Colors.RESET}   No layer violations found.")
            if allowed_violations:
                print(f"  {len(allowed_violations)} allowlisted violation(s) suppressed.")
            return 0

        print(f"\n{Colors.RED}[FAIL]{Colors.RESET} {len(violations)} layer violation(s):\n")
        for v in violations[:20]:
            try:
                src_display = str(Path(v['src_file']).relative_to(project_path))
            except ValueError:
                src_display = v['src_file']
            try:
                dst_display = str(Path(v['dst_file']).relative_to(project_path))
            except ValueError:
                dst_display = v['dst_file']
            print(f"  [!] {v['src_layer']} -> {v['dst_layer']}  (forbidden: lower layer calls upper)")
            print(f"      {src_display}")
            print(f"      calls {dst_display}")
            print()

        if allowlist:
            print(f"  Allowlisted pairs (intentional): {', '.join(f'{a}->{b}' for a, b in sorted(allowlist))}")
            print(f"  Add to 'allowlist' in {cfg_file} to suppress a violation.")
        if unclassified_files:
            print(f"  {len(unclassified_files)} file(s) not matched by any layer (ignored).")
            print(f"  Add path patterns to {cfg_file} to classify them.")

        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


# ---------------------------------------------------------------------------
# breaking-changes
# ---------------------------------------------------------------------------

def cmd_breaking_changes(
    symbol: str,
    before_ref: str = "HEAD~1",
    after_ref: str = "HEAD",
) -> int:
    """Compare a function's contract between two git refs and report breaking changes."""
    from src.contracts.breaking_change_detector import BreakingChangeDetector
    from src.contracts.extractor import ContractExtractor
    from src.parsers.symbol import Symbol as SymbolObj

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id
        params: dict = {"name": symbol}
        pid_filter = "AND n.project_id = $pid" if pid else ""
        if pid:
            params["pid"] = pid

        with client.driver.session() as session:
            row = session.run(
                f"MATCH (n {{name: $name}}) WHERE n:Function {pid_filter} "
                "RETURN n.file AS file, n.line AS line, n.parent AS parent LIMIT 1",
                **params,
            ).single()
    except Exception as e:
        print(f"ERROR: Graph query failed: {e}")
        return 1

    if not row:
        print(f"Symbol '{symbol}' not found in graph (Functions only).")
        print("Hint: run `smt build` or `smt sync` to refresh the graph.")
        return 1

    file_path: str = row["file"]
    line: int = row["line"] or 1

    try:
        rel_path = str(Path(file_path).relative_to(project_path)).replace("\\", "/")
    except ValueError:
        rel_path = file_path.replace("\\", "/")

    def _git_show(ref: str, path: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(project_path), "show", f"{ref}:{path}"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"`git show {ref}:{path}` failed: {result.stderr.strip()}")
        return result.stdout

    try:
        before_src = _git_show(before_ref, rel_path)
        after_src = _git_show(after_ref, rel_path)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    parent_class = row.get("parent")
    sym_before = SymbolObj(name=symbol, type="function", file=file_path, line=line, column=0, parent=parent_class)
    sym_after  = SymbolObj(name=symbol, type="function", file=file_path, line=line, column=0, parent=parent_class)

    before_contract = ContractExtractor(before_src).extract_function_contract(sym_before)
    after_contract  = ContractExtractor(after_src).extract_function_contract(sym_after)

    if not before_contract:
        print(f"Could not extract contract for '{symbol}' at {before_ref}.")
        print("  (function may not be top-level, or file may not be Python)")
        return 1
    if not after_contract:
        print(f"Could not extract contract for '{symbol}' at {after_ref}.")
        print("  (function may not be top-level, or file may not be Python)")
        return 1

    comparison = BreakingChangeDetector().detect_breaking_changes(before_contract, after_contract)

    compat_color = Colors.GREEN if comparison.is_compatible else Colors.RED
    print(f"\nBreaking change analysis: {Colors.BOLD}{symbol}{Colors.RESET}")
    print(f"  {before_ref} → {after_ref}  |  {rel_path}:{line}")
    print(
        f"  Compatible: {compat_color}{'YES' if comparison.is_compatible else 'NO'}{Colors.RESET}"
        f"  (score: {comparison.compatibility_score:.2f})\n"
    )

    if comparison.breaking_changes:
        print(f"  {len(comparison.breaking_changes)} breaking change(s):\n")
        for bc in comparison.breaking_changes:
            sev_color = (
                Colors.RED if bc.severity == "HIGH"
                else Colors.YELLOW if bc.severity == "MEDIUM"
                else Colors.RESET
            )
            print(f"  [{sev_color}{bc.severity}{Colors.RESET}] {bc.type}")
            print(f"    {bc.impact}")
            if bc.affected_elements:
                print(f"    Affected: {', '.join(sorted(bc.affected_elements))}")
            print()
    else:
        print(f"  {Colors.GREEN}No breaking changes detected.{Colors.RESET}\n")

    if comparison.non_breaking_changes:
        print(f"  {len(comparison.non_breaking_changes)} non-breaking change(s):")
        for change in comparison.non_breaking_changes:
            print(f"    - {change}")
        print()

    return 0 if comparison.is_compatible else 1
