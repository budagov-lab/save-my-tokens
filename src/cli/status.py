"""SMT status command: graph health check."""

import subprocess
import urllib.request

from src.cli._helpers import (
    _get_project_id,
    _get_services,
    _resolve_project_path,
)
from src.cli.docker import _docker_compose_cmd, SMT_DIR


def cmd_status() -> int:
    compose_file = SMT_DIR / 'docker-compose.yml'
    dc = _docker_compose_cmd()
    try:
        ps = subprocess.run(
            dc + ['-f', str(compose_file), 'ps', '--status', 'running', '-q', 'neo4j'],
            cwd=SMT_DIR, capture_output=True, text=True,
        )
        container_running = bool(ps.stdout.strip())
    except Exception:
        container_running = False
    print(f"Container:  {'running' if container_running else 'stopped'}")

    try:
        urllib.request.urlopen('http://localhost:7474', timeout=2)
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    print(f"Neo4j:  {'OK  (http://localhost:7474)' if neo4j_ok else 'NOT RUNNING'}")

    if not neo4j_ok:
        print("\nStart Neo4j with:  smt start")
        return 1

    try:
        settings, Neo4jClient, *_ = _get_services()
        project_path = _resolve_project_path()
        project_id = _get_project_id(project_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
        with client.driver.session() as session:
            if project_id:
                counts = session.run(
                    "MATCH (n {project_id: $pid}) RETURN labels(n)[0] AS label, count(n) AS cnt",
                    pid=project_id
                ).data()
                edge_count = session.run(
                    "MATCH (a {project_id: $pid})-[r]->(b {project_id: $pid}) RETURN count(r) AS cnt",
                    pid=project_id
                ).single()['cnt']
            else:
                counts = session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
                ).data()
                edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()['cnt']
        total = sum(r['cnt'] for r in counts)
        print(f"Graph:  {total} nodes, {edge_count} edges  (project: {project_path.name} [{project_id}])")
        for row in sorted(counts, key=lambda r: -r['cnt']):
            print(f"        {row['label']}: {row['cnt']}")

        if total == 0:
            print("\nGraph is empty. Build it with:  smt build")
            client.driver.close()
            return 1

        try:
            from src.graph.validator import (
                format_stale_files_line,
                format_validation_line,
                validate_graph,
            )
            validation = validate_graph(client, project_path)
            print(f"Head:   {format_validation_line(validation)}")
            stale = format_stale_files_line(validation)
            if stale:
                print(stale)
        except Exception:
            pass
        client.driver.close()
    except Exception as e:
        print(f"Graph:  ERROR — {e}")
        return 1

    return 0
