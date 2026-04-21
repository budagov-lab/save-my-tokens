"""SMT setup and onboarding commands."""

import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    SMT_DIR,
    Colors,
    _C,
    _ensure_smtignore,
    _fail,
    _get_neo4j_client,
    _get_project_id,
    _git_initial_commit,
    _ok,
    _warn,
)

# A2A agent card written to .claude/a2a/smt.json in target projects
_A2A_AGENT_CARD = {
    "name": "save-my-tokens",
    "description": (
        "Semantic code graph for efficient codebase exploration. "
        "Provides symbol lookup, dependency analysis, impact assessment, "
        "and semantic search via the smt CLI."
    ),
    "url": "local://smt-cli",
    "version": "1.0.0",
    "onboard": "cat .claude/skills/smt-analysis/a2a-onboard.md",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "skills": [
        {
            "id": "smt-definition",
            "name": "Symbol Definition",
            "description": "What is this symbol? Signature, docstring, immediate callees.",
            "invoke": "smt definition <symbol>",
        },
        {
            "id": "smt-context",
            "name": "Symbol Context",
            "description": "What do I need to work on this? Symbol + N-hop callees + callers.",
            "invoke": "smt context <symbol> [--depth N] [--compress]",
        },
        {
            "id": "smt-impact",
            "name": "Change Impact Analysis",
            "description": "What breaks if I change this? All callers grouped by distance.",
            "invoke": "smt impact <symbol> [--depth N]",
        },
        {
            "id": "smt-search",
            "name": "Semantic Code Search",
            "description": "Find symbols by meaning using local embeddings. No API calls.",
            "invoke": 'smt search "<query>"',
        },
        {
            "id": "smt-status",
            "name": "Graph Health Check",
            "description": "Graph freshness, node/edge counts, git alignment. Run at session start.",
            "invoke": "smt status",
        },
        {
            "id": "smt-analysis",
            "name": "Multi-Agent Analysis Harness",
            "description": "Single-agent pipeline: pre-flight → query → reason → report. Use for impact analysis, isolation analysis, or architecture audits.",
            "invoke": "/smt-analysis",
        },
        {
            "id": "smt-list",
            "name": "Symbol Listing",
            "description": "Enumerate all symbols in the graph, optionally filtered by module/file path.",
            "invoke": "smt list [--module <path-substring>]",
        },
        {
            "id": "smt-unused",
            "name": "Dead Code Detection",
            "description": "Find symbols with no callers — candidates for dead code removal.",
            "invoke": "smt unused",
        },
        {
            "id": "smt-cycles",
            "name": "Circular Dependency Detection",
            "description": "Find all circular dependencies in the call graph using Tarjan's SCC.",
            "invoke": "smt cycles",
        },
        {
            "id": "smt-hot",
            "name": "Coupling Hotspots",
            "description": "Most-called symbols ranked by unique caller count — find high-coupling hotspots.",
            "invoke": "smt hot [--top N]",
        },
        {
            "id": "smt-path",
            "name": "Dependency Path",
            "description": "Shortest dependency path between two symbols via CALLS edges.",
            "invoke": "smt path <A> <B>",
        },
        {
            "id": "smt-modules",
            "name": "Module Coupling Report",
            "description": "Files ranked by symbol count and cross-file coupling edges.",
            "invoke": "smt modules",
        },
        {
            "id": "smt-changes",
            "name": "Git Change Impact",
            "description": "Symbols in git-changed files with caller counts. Pinpoints which symbols changed by line range. Essential for PR review.",
            "invoke": "smt changes [RANGE]",
        },
        {
            "id": "smt-complexity",
            "name": "God Function Detector",
            "description": "Ranks symbols by fan-in × fan-out. High score = hard to refactor AND large blast radius.",
            "invoke": "smt complexity [--top N]",
        },
        {
            "id": "smt-scope",
            "name": "File Surface Analysis",
            "description": "Shows a file's public exports, imports from other files, and internal symbols. File-level architectural view.",
            "invoke": "smt scope <file-substring>",
        },
        {
            "id": "smt-bottleneck",
            "name": "Architectural Bottleneck",
            "description": "Symbols that bridge distinct file clusters. Bridge score = caller files × callee files (cross-file only). High score = structural chokepoint.",
            "invoke": "smt bottleneck [--top N]",
        },
        {
            "id": "smt-layer",
            "name": "Architecture Layer Guard",
            "description": "Detects forbidden dependency directions (e.g. parsers calling CLI). Configured via .smt_layers.json. Returns non-zero exit if violations found (CI-safe).",
            "invoke": "smt layer [--config PATH]",
        },
    ],
    "authentication": {"schemes": []},
}


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup(target_dir: Path) -> int:
    import shutil
    target_dir = target_dir.resolve()
    claude_dir = target_dir / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    print(f"Configuring SMT for: {target_dir}")

    # ------------------------------------------------------------------
    # 0. .claude/.smt_config — store project metadata for CLI
    # ------------------------------------------------------------------
    smt_config_file = claude_dir / '.smt_config'
    smt_config = {
        'project_dir': str(target_dir),
        'project_name': target_dir.name,
        'project_id': _get_project_id(target_dir),
        'default_depth': 2,
    }
    with open(smt_config_file, 'w', encoding='utf-8') as f:
        json.dump(smt_config, f, indent=2)
    print("  .claude/.smt_config    [OK]")

    # ------------------------------------------------------------------
    # 0a. .smtignore
    # ------------------------------------------------------------------
    _ensure_smtignore(target_dir)
    print("  .smtignore             [OK]")

    # ------------------------------------------------------------------
    # 0b. .gitignore — ensure .smt/ (embeddings cache) is ignored
    # ------------------------------------------------------------------
    gitignore_file = target_dir / '.gitignore'
    smt_ignore_entry = '.smt/'
    if gitignore_file.exists():
        content = gitignore_file.read_text(encoding='utf-8')
        if smt_ignore_entry not in content:
            with open(gitignore_file, 'a', encoding='utf-8') as f:
                f.write(f'\n# SMT embeddings cache\n{smt_ignore_entry}\n')
            print("  .gitignore             [OK] — added .smt/")
        else:
            print("  .gitignore             [OK] — .smt/ already ignored")
    else:
        gitignore_file.write_text(f'# SMT embeddings cache\n{smt_ignore_entry}\n', encoding='utf-8')
        print("  .gitignore             [OK] — created with .smt/")

    # ------------------------------------------------------------------
    # 1. .claude/settings.json
    # ------------------------------------------------------------------
    settings_file = claude_dir / 'settings.json'
    existing = {}
    if settings_file.exists():
        with open(settings_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'
    existing.setdefault('permissions', {})
    existing['permissions']['defaultMode'] = 'auto'
    smt_allow = ['Read', 'Edit(**)', 'Write(**)', 'Bash']
    current_allow = existing['permissions'].get('allow', [])
    existing['permissions']['allow'] = list(dict.fromkeys(current_allow + smt_allow))
    smt_deny = [
        'Bash(rm -rf:*)',
        'Bash(git reset --hard:*)',
        'Bash(git push --force:*)',
    ]
    current_deny = existing['permissions'].get('deny', [])
    existing['permissions']['deny'] = list(dict.fromkeys(current_deny + [
        r for r in smt_deny if r not in current_deny
    ]))
    existing.setdefault('env', {})
    existing['env']['SMT_DIR'] = str(SMT_DIR)
    existing['env']['SMT_PROJECT'] = target_dir.name
    existing['respectGitignore'] = True

    # PreToolUse hooks — inject SMT skill into Explorer, Planner, and Advisor
    _hook_cmd = "python .claude/hooks/smt_agent_hook.py"
    _hook_entry = {"type": "command", "command": _hook_cmd}
    _smt_hooks = [
        {"matcher": "Agent",   "hooks": [_hook_entry]},
        {"matcher": "advisor", "hooks": [_hook_entry]},
        {"matcher": "Read",    "hooks": [_hook_entry]},
        {"matcher": "Grep",    "hooks": [_hook_entry]},
    ]
    existing.setdefault('hooks', {})
    existing['hooks'].setdefault('PreToolUse', [])
    # Remove any stale SMT entries, then re-add fresh
    existing['hooks']['PreToolUse'] = [
        h for h in existing['hooks']['PreToolUse']
        if not any(hk.get('command') == _hook_cmd for hk in h.get('hooks', []))
    ] + _smt_hooks

    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2)
    print("  .claude/settings.json  [OK]")

    # ------------------------------------------------------------------
    # 2. .claude/skills/smt-analysis/ — copy the full harness from SMT repo
    # ------------------------------------------------------------------
    skills_dir = claude_dir / 'skills'
    smt_skill_src = SMT_DIR / '.claude' / 'skills' / 'smt-analysis'
    smt_skill_dst = skills_dir / 'smt-analysis'
    if smt_skill_src.exists():
        smt_skill_dst.mkdir(parents=True, exist_ok=True)
        copied = []
        for src_file in smt_skill_src.rglob('*'):
            if src_file.is_file():
                rel = src_file.relative_to(smt_skill_src)
                dst_file = smt_skill_dst / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dst_file))
                copied.append(rel)
        print(f"  .claude/skills/smt-analysis/ [OK] — {len(copied)} file(s)")
    else:
        print(f"  .claude/skills/smt-analysis/ [SKIP] — source not found at {smt_skill_src}")

    # ------------------------------------------------------------------
    # 2b. .claude/hooks/smt_agent_hook.py — PreToolUse hook script
    # ------------------------------------------------------------------
    hook_src = SMT_DIR / '.claude' / 'hooks' / 'smt_agent_hook.py'
    hook_dst_dir = claude_dir / 'hooks'
    if hook_src.exists():
        hook_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(hook_src), str(hook_dst_dir / 'smt_agent_hook.py'))
        print("  .claude/hooks/         [OK] — smt_agent_hook.py")
    else:
        print(f"  .claude/hooks/         [SKIP] — hook script not found at {hook_src}")

    # ------------------------------------------------------------------
    # 3. .claude/a2a/smt.json — A2A agent card
    # ------------------------------------------------------------------
    a2a_dir = claude_dir / 'a2a'
    a2a_dir.mkdir(parents=True, exist_ok=True)
    a2a_file = a2a_dir / 'smt.json'
    with open(a2a_file, 'w', encoding='utf-8') as f:
        json.dump(_A2A_AGENT_CARD, f, indent=2)
    print("  .claude/a2a/smt.json   [OK]")

    # ------------------------------------------------------------------
    # 4. Git hooks
    # ------------------------------------------------------------------
    cmd_setup_hooks(target_dir)

    # ------------------------------------------------------------------
    # 5. Git initial commit
    # ------------------------------------------------------------------
    if (target_dir / '.git').exists():
        try:
            _git_initial_commit(target_dir)
        except Exception as e:
            print(f"  git commit             [WARN] — {e}")

    print("\nSetup complete! Graph is synced with git.")
    print("  Every git commit will now auto-update the graph via post-commit hook.")
    print("  Manual sync: smt sync")
    print("  Graph status: smt status")

    return 0


# ---------------------------------------------------------------------------
# hooks
# ---------------------------------------------------------------------------

def cmd_setup_hooks(target_dir: Path) -> bool:
    """Install post-commit hook for automatic graph sync."""
    git_dir = target_dir / '.git'
    if not git_dir.exists():
        logger.warning(f".git not found in {target_dir}, skipping hook setup")
        return False

    hooks_dir = git_dir / 'hooks'
    if not hooks_dir.exists():
        logger.debug("Creating .git/hooks directory")
        hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_file = hooks_dir / 'post-commit'
    smt_marker = "# SMT: Auto-sync graph on commit"

    existing_content = ""
    if hook_file.exists():
        with open(hook_file, 'r', encoding='utf-8') as f:
            existing_content = f.read()

        if smt_marker in existing_content:
            logger.debug(f"SMT hook already installed in {hook_file}")
            return True

    smt_hook = f"""{smt_marker}
smt sync HEAD~1..HEAD >/dev/null 2>&1 &
exit 0
"""

    new_content = existing_content
    if existing_content and not existing_content.endswith('\n'):
        new_content += '\n'
    new_content += smt_hook

    with open(hook_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    st = hook_file.stat()
    hook_file.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    logger.info(f"Installed post-commit hook at {hook_file}")
    print("  .git/hooks/post-commit [OK] — Graph will sync after each commit")
    return True


def cmd_remove_hooks(target_dir: Path) -> bool:
    """Remove SMT post-commit hook."""
    git_dir = target_dir / '.git'
    hook_file = git_dir / 'hooks' / 'post-commit'

    if not hook_file.exists():
        logger.warning(f"Hook file not found: {hook_file}")
        return False

    with open(hook_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip_block = False
    for line in lines:
        if "# SMT: Auto-sync graph on commit" in line:
            skip_block = True
            continue
        if skip_block and line.strip() == "exit 0":
            skip_block = False
            continue
        if not skip_block:
            new_lines.append(line)

    if new_lines and any(line.strip() for line in new_lines):
        with open(hook_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        logger.info(f"Removed SMT hook from {hook_file}")
    else:
        hook_file.unlink()
        logger.info(f"Deleted empty hook file {hook_file}")

    return True
