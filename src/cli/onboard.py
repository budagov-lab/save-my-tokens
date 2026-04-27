"""SMT onboard command: guided setup, agent orientation, and health check."""

import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from src.cli._helpers import (
    _C,
    _fail,
    _get_neo4j_client,
    _ok,
    _warn,
)


def cmd_onboard(action: str, target_dir: Optional[Path] = None) -> int:
    """Guided onboarding: setup, orientation, or health check."""

    if action == 'project':
        from src.cli.build import cmd_build
        from src.cli.docker import cmd_docker
        from src.cli.status import cmd_status

        target = (target_dir or Path.cwd()).resolve()
        print(f"\n{_C.BOLD}SMT Project Onboarding: {target.name}{_C.RESET}\n")

        print("Step 1/3  Starting Neo4j...")
        rc = cmd_docker('up')
        if rc != 0:
            _fail("docker up failed — is Docker Desktop running?")
            print("  Fix: start Docker Desktop, then re-run: smt onboard project")
            return 1
        _ok("Neo4j is ready")

        print("\nStep 2/3  Building graph from source...")
        result = cmd_build(check=False, clear=False, target_dir=str(target))
        if result != 0:
            _fail("Graph build failed — check error above")
            return 1

        print("\nStep 3/3  Verifying graph health...")
        result = cmd_status()
        if result != 0:
            _fail("Status check failed")
            return 1

        print(f"\n{_C.GREEN}{_C.BOLD}Onboarding complete!{_C.RESET}")
        print("\nNext steps:")
        print("  smt context <SymbolName>   — explore a symbol's dependencies")
        print("  smt search \"your query\"    — semantic search by meaning")
        print("  smt impact <SymbolName>    — see what breaks if you change this")
        print("  smt status                 — check graph health")
        return 0

    elif action == 'agent':
        orientation = f"""\

{_C.BOLD}SMT AGENT ORIENTATION{_C.RESET}
save-my-tokens (SMT) exposes a semantic Neo4j graph of this codebase.
Use it instead of reading raw files.

{_C.BOLD}QUERY DECISION TABLE{_C.RESET}
Goal                          | Command
------------------------------|------------------------------------------
Understand what a symbol does | smt context <symbol>
See dependencies (2+ hops)    | smt context <symbol> --depth 2
See who calls a function      | smt context <symbol> --callers
Find code by topic/meaning    | smt search "description"
What breaks if I change this  | smt impact <symbol>
Check graph health            | smt status
Build graph from source       | smt build
Sync after recent commits     | smt sync HEAD~1..HEAD
Start Neo4j                   | smt start

{_C.BOLD}TOOL HIERARCHY (use in order){_C.RESET}
  Tier 1 (first)   — smt context / smt search / smt impact
  Tier 2 (verify)  — Grep, Glob
  Tier 3 (inspect) — Read (only after SMT locates the file)
  Tier 4 (avoid)   — Bash find/grep for exploration

{_C.BOLD}SESSION START CHECKLIST{_C.RESET}
  smt status   → node count > 0? Graph is ready.
  smt build    → if empty, build from src/
  smt sync     → if stale, sync after recent commits

{_C.BOLD}SKILLS FILES (in .claude/skills/){_C.RESET}
  agent-query-guide.md    — full decision tree
  graph-maintenance.md    — how to keep graph fresh
  project-onboarding.md   — setup guide for first-time users
"""
        print(orientation)
        return 0

    elif action == 'check':
        print(f"\n{_C.BOLD}SMT Health Check{_C.RESET}\n")
        exit_code = 0

        try:
            urllib.request.urlopen('http://localhost:7474', timeout=3)
            _ok("Neo4j reachable (http://localhost:7474)")
            neo4j_up = True
        except Exception:
            _fail("Neo4j not reachable — run: smt start")
            neo4j_up = False
            exit_code = 1

        if neo4j_up:
            try:
                client = _get_neo4j_client()
                with client.driver.session() as session:
                    result = session.run("MATCH (n) RETURN count(n) AS cnt")
                    total = result.single()['cnt']
                if total > 0:
                    _ok(f"Graph has {total} nodes")
                else:
                    _warn("Graph is empty — run: smt build")
                    exit_code = 1
            except Exception as e:
                _warn(f"Graph query failed: {str(e)[:80]}")
                exit_code = 1
        else:
            _warn("Graph check skipped (Neo4j not running)")

        if neo4j_up:
            try:
                from src.graph.validator import validate_graph
                client = _get_neo4j_client()
                repo_path = (target_dir or Path.cwd()).resolve()
                v = validate_graph(client, repo_path)
                if v.is_fresh:
                    _ok(f"Graph is fresh (HEAD: {v.git_head})")
                else:
                    _warn(f"Graph is {v.commits_behind} commit(s) behind — run: smt sync")
            except Exception as e:
                _warn(f"Staleness check skipped: {str(e)[:80]}")

        try:
            result = subprocess.run(
                [sys.executable, '-c', 'from sentence_transformers import SentenceTransformer'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                _ok("sentence_transformers importable")
            else:
                _warn("sentence_transformers not importable — semantic search disabled")
        except Exception:
            _warn("sentence_transformers check timed out")

        skills_dir = Path('.claude/skills')
        if skills_dir.exists() and any(skills_dir.glob('*.md')):
            skill_count = len(list(skills_dir.glob('*.md')))
            _ok(f".claude/skills/ has {skill_count} skill file(s)")
        else:
            _warn(".claude/skills/ missing or empty — run: smt setup --dir .")

        print()
        return exit_code

    else:
        print(f"Unknown onboard action: {action}")
        print("Usage: smt onboard project|agent|check [--dir PATH]")
        return 1
