"""SMT graph metric commands: cycles, hot, modules, complexity, bottleneck."""

from pathlib import Path

from src.cli._helpers import (
    _get_neo4j_client,
    _get_project_id,
    _require_git,
    _resolve_project_path,
)


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
