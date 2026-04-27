"""SMT docker commands: start/stop Neo4j container."""

import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from src.cli._helpers import SMT_DIR

_NEO4J_CONTAINER = 'save-my-tokens-neo4j'

_dc_cmd: list | None = None


def _docker_compose_cmd() -> list:
    """Return the docker compose command — v2 ('docker compose') preferred, v1 fallback."""
    global _dc_cmd
    if _dc_cmd is None:
        result = subprocess.run(['docker', 'compose', 'version'], capture_output=True)
        _dc_cmd = ['docker', 'compose'] if result.returncode == 0 else ['docker-compose']
    return _dc_cmd


def _neo4j_bolt_ready(timeout: float = 2.0) -> bool:
    """Check if Neo4j is ready: bolt port (7687) accepts TCP AND HTTP API (7474) responds.

    The bolt port opens before Neo4j finishes initializing its database engine.
    Waiting for the HTTP endpoint ensures the server is actually ready for queries.
    """
    try:
        with socket.create_connection(('localhost', 7687), timeout=timeout):
            pass
    except OSError:
        return False
    try:
        urllib.request.urlopen('http://localhost:7474', timeout=timeout)
        return True
    except Exception:
        return False


def cmd_docker(action: str) -> int:
    compose_file = SMT_DIR / 'docker-compose.yml'
    if not compose_file.exists():
        print("ERROR: docker-compose.yml not found")
        return 1

    dc = _docker_compose_cmd()

    if action == 'up':
        subprocess.run(['docker', 'rm', _NEO4J_CONTAINER], capture_output=True)
        result = subprocess.run(
            dc + ['-f', str(compose_file), 'up', '-d', 'neo4j'],
            cwd=SMT_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr or ""
            if "pipe/dockerDesktopLinuxEngine" in stderr or "pipe/docker_engine" in stderr or "connect: no such file" in stderr:
                print("ERROR: Docker Desktop is not running.")
                print("  Fix: start Docker Desktop, then re-run: smt start")
            else:
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="")
            return result.returncode
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")

        print("Waiting for Neo4j to be ready...", flush=True)
        max_wait = 120
        elapsed = 0.0
        attempt = 0
        while elapsed < max_wait:
            check = subprocess.run(
                dc + ['-f', str(compose_file), 'ps', '--status', 'running', '-q', 'neo4j'],
                cwd=SMT_DIR, capture_output=True, text=True,
            )
            if check.returncode != 0 or not check.stdout.strip():
                print("ERROR: Neo4j container stopped unexpectedly.")
                print("  Check logs: docker logs save-my-tokens-neo4j")
                return 1
            if _neo4j_bolt_ready():
                print("Neo4j ready (bolt://localhost:7687) — run: smt build")
                return 0
            attempt += 1
            wait = min(0.5 * (2 ** (attempt - 1)), 8)
            elapsed += wait
            print(f"  still starting... ({int(elapsed)}s)", flush=True)
            time.sleep(wait)

        print(f"ERROR: Neo4j did not become ready in {max_wait}s")
        print("  Check container logs: docker logs save-my-tokens-neo4j")
        return 1

    elif action == 'down':
        result = subprocess.run(['docker', 'stop', _NEO4J_CONTAINER], cwd=SMT_DIR)
    elif action == 'status':
        result = subprocess.run(dc + ['-f', str(compose_file), 'ps'], cwd=SMT_DIR)
    else:
        print(f"Unknown docker action: {action}. Use: up, down, status")
        return 1

    return result.returncode
