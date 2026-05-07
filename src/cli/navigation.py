"""SMT navigation commands: list, path, scope."""

import sys
from pathlib import Path
from typing import Optional

from src.cli._helpers import (
    _get_neo4j_client,
    _get_project_id,
    _require_git,
    _resolve_project_path,
)


def cmd_list(module: Optional[str] = None, type_filter: Optional[str] = None, limit: int = 0) -> int:
    """Enumerate all symbols in the graph, optionally filtered by file/module path and type."""
    import os as _os

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
                params["module"] = module.replace("/", _os.sep).replace("\\", _os.sep)
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
            if module and not any(sep in module for sep in ('/', '\\', '.py', '.ts', '.go', '.rs', '.java')):
                print(f"  Tip: --module expects a file path segment (e.g. 'requests/models.py'), not a symbol or class name.")
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


def cmd_scope(file_filter: str, dir_filter: Optional[str] = None) -> int:
    """File-level surface analysis: exports, imports, internal symbols."""
    import os as _os

    project_path = _resolve_project_path()
    if not _require_git(project_path):
        return 1

    # Normalize path separators so forward-slash input matches OS-native stored paths,
    # then try common extensions if the caller omitted one (e.g. "exceptions" → "exceptions.py").
    normalized = file_filter.replace("/", _os.sep).replace("\\", _os.sep)

    try:
        client = _get_neo4j_client(_get_project_id(project_path))
        pid = client.project_id

        def _run_filter(session, f: str):
            return session.run(
                """
                MATCH (n {project_id: $pid})
                WHERE n.file IS NOT NULL AND n.file CONTAINS $filter AND NOT n:Commit
                RETURN DISTINCT n.file AS file ORDER BY n.file
                """,
                pid=pid, filter=f
            ).data()

        with client.driver.session() as session:
            file_rows = _run_filter(session, normalized)
            if not file_rows and not Path(normalized).suffix:
                for ext in ('.py', '.ts', '.tsx', '.js', '.go', '.rs', '.java'):
                    file_rows = _run_filter(session, normalized + ext)
                    if file_rows:
                        break
            if not file_rows and Path(normalized).suffix:
                # Extension-based CONTAINS can miss on separator/encoding variations.
                # Fall back to stem-only search and post-filter by extension.
                stem = Path(normalized).stem
                ext = Path(normalized).suffix
                stem_rows = _run_filter(session, stem)
                file_rows = [r for r in stem_rows if r['file'].endswith(ext)]
                if not file_rows:
                    file_rows = stem_rows  # accept any stem match rather than nothing

        if not file_rows:
            print(f"No symbols found for file filter: {file_filter!r}")
            if not Path(normalized).suffix:
                print(f"  Tip: include the file extension (e.g. '{file_filter}.py')")
            else:
                stem = Path(normalized).stem
                print(f"  Tip: file not indexed — try: smt list --module {stem}")
            return 1

        if len(file_rows) > 1 and dir_filter:
            dir_norm = dir_filter.replace("/", _os.sep).replace("\\", _os.sep)
            filtered = [r for r in file_rows if dir_norm in r['file']]
            if filtered:
                file_rows = filtered

        if len(file_rows) > 1:
            print(f"Multiple files match {file_filter!r} — be more specific:\n")
            for r in file_rows[:10]:
                try:
                    print(f"  {Path(r['file']).relative_to(project_path)}")
                except ValueError:
                    print(f"  {r['file']}")
            print(f"\n  Use: smt scope {file_filter} --dir <path-fragment>")
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

        out = []
        out.append(f"\nScope: {display}\n")
        out.append(f"  {len(all_syms)} symbols total  |  "
                   f"{len(exports)} exported  |  "
                   f"{len(imports)} imported  |  "
                   f"{len(internal_syms)} internal\n")

        if exports:
            out.append(f"  exports — called by other files ({len(exports)}):\n")
            for r in exports:
                caller_files = [Path(f).name for f in (r.get('sample_files') or [])]
                suffix = (f"  <- {r['external_callers']} caller{'s' if r['external_callers'] != 1 else ''}"
                          f" ({', '.join(caller_files[:2])}{'...' if len(caller_files) > 2 else ''})")
                doc = r.get('docstring') or ''
                doc_line = doc.splitlines()[0].strip()[:60] if doc else ''
                doc_suffix = f"  # {doc_line}" if doc_line else ""
                out.append(f"    {r['name']:<45} [{r['type']}]{suffix}{doc_suffix}\n")

        if imports:
            from collections import defaultdict
            by_src: dict = defaultdict(list)
            for r in imports:
                by_src[r['dep_file']].append(r)
            out.append(f"\n  imports — calls into other files ({len(imports)} symbols from {len(by_src)} files):\n")
            for dep_file in sorted(by_src):
                deps = by_src[dep_file]
                try:
                    dep_display = str(Path(dep_file).relative_to(project_path))
                except ValueError:
                    dep_display = Path(dep_file).name
                out.append(f"    from {dep_display}:\n")
                for dep in deps:
                    out.append(f"      {dep['name']}  [{dep['type']}]\n")

        if internal_syms:
            import os as _os2
            if _os2.environ.get("SMT_AGENT"):
                out.append(f"\n  internal — not coupled across files ({len(internal_syms)} symbols)\n")
                out.append(f"  (use smt list --module {Path(display).name} to enumerate)\n")
            else:
                out.append(f"\n  internal — not directly coupled across files ({len(internal_syms)}):\n")
                for sym in internal_syms:
                    line_str = f":{sym['line']}" if sym['line'] else ""
                    out.append(f"    {sym['name']:<45} [{sym['type']}]{line_str}\n")

        print("".join(out), end="")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
