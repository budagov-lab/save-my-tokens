"""SMT build command: parse source and persist graph to Neo4j."""

import json
from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    Colors,
    _C,
    _ensure_smtignore,
    _get_project_id,
    _get_services,
    _require_git,
)


def cmd_build(check: bool = False, clear: bool = False, target_dir: Optional[str] = None) -> int:
    from src.cli.status import cmd_status

    settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, _ = _get_services()

    if check:
        return cmd_status()

    if target_dir:
        target_path = Path(target_dir).resolve()
    else:
        cwd = Path.cwd()
        smt_config_file = cwd / '.claude' / '.smt_config'
        if smt_config_file.exists():
            try:
                with open(smt_config_file, 'r', encoding='utf-8') as f:
                    smt_config = json.load(f)
                    target_path = Path(smt_config['project_dir']).resolve()
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                target_path = cwd
        else:
            target_path = cwd

    if not _require_git(target_path):
        return 1

    _ensure_smtignore(target_path)

    src_dir = target_path

    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        if clear:
            print(f"{Colors.YELLOW}[WARN]{Colors.RESET} Clearing graph data for project: {target_path.name} [{project_id}]")
            client.clear_database()
            import shutil
            embeddings_dir = target_path / '.smt' / 'embeddings'
            if embeddings_dir.exists():
                shutil.rmtree(embeddings_dir)
                logger.info(f"Cleared embeddings cache: {embeddings_dir}")

        builder = GraphBuilder(str(src_dir), neo4j_client=client, project_id=project_id)
        builder.build()
        client.driver.close()
        print(f"Done. (project: {target_path.name} [{project_id}])")
        return cmd_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
