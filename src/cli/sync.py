"""SMT sync command: incremental graph update from git commits."""

import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    _get_project_id,
    _get_services,
    _resolve_project_path,
)


def cmd_sync(commit_range: str = 'HEAD~1..HEAD', target_dir: Optional[str] = None) -> int:
    from src.cli.status import cmd_status

    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    try:
        target_path = Path(target_dir).resolve() if target_dir else _resolve_project_path()

        if not (target_path / '.git').exists():
            print(f"ERROR: No .git directory found in {target_path}")
            return 1

        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        index = SymbolIndex()
        cache_dir = target_path / '.smt' / 'embeddings'
        embedding_svc = EmbeddingService(index, cache_dir=cache_dir)

        updater = IncrementalSymbolUpdater(
            symbol_index=index,
            neo4j_client=client,
            embedding_service=embedding_svc,
            base_path=str(target_path),
        )

        # Guard: single-commit repo — nothing to diff, but record HEAD so validator shows fresh.
        if commit_range == 'HEAD~1..HEAD':
            count_result = subprocess.run(
                ['git', 'rev-list', '--count', 'HEAD'],
                cwd=str(target_path), capture_output=True, text=True,
            )
            if count_result.returncode == 0 and count_result.stdout.strip() == '1':
                try:
                    commit_meta = updater._get_commit_metadata('HEAD', str(target_path))
                    client.create_commit_node(commit_meta)
                    print("✓ Graph marked fresh (single-commit repository)")
                except Exception as e:
                    logger.warning(f"Could not record HEAD commit: {e}")
                    print("Nothing to sync — repository has only one commit.")
                client.driver.close()
                return cmd_status()

        success = updater.update_from_git(commit_range, repo_path=str(target_path))
        client.driver.close()

        if success:
            print("✓ Graph synced successfully")
            return cmd_status()
        else:
            print("✗ Graph sync failed — try: smt build --clear")
            return 1

    except Exception as e:
        logger.debug("cmd_sync error", exc_info=True)
        print(f"ERROR: {e}")
        return 1
