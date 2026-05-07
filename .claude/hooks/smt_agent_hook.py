#!/usr/bin/env python3
"""
PreToolUse hook — three responsibilities:

1. Agent (Explore)       → deny outright (too token-heavy; use SMT + direct tools)
2. advisor               → inject SMT skill via additionalContext
3. Read (full-file, src) → deny and suggest smt scope / smt view instead
4. Grep                  → deny and suggest smt search / smt definition instead
"""
import json
import os
import sys
from pathlib import Path

_SKILL_MD = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "smt-analysis", "SKILL.md")
)

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs"}


def load_skill() -> str:
    try:
        return open(_SKILL_MD, encoding="utf-8").read()
    except Exception:
        return ""


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    # ------------------------------------------------------------------
    # Agent spawns — block Explore outright
    # ------------------------------------------------------------------
    if tool_name == "Agent" and tool_input.get("subagent_type") == "Explore":
        _deny("Explore blocked. Use: smt definition/context/scope/grep instead.")
        return

    # ------------------------------------------------------------------
    # Advisor — inject skill as context
    # ------------------------------------------------------------------
    if tool_name == "advisor":
        skill = load_skill()
        if not skill:
            sys.exit(0)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "additionalContext": skill,
            }
        }))
        return

    # ------------------------------------------------------------------
    # Read — block full-file reads of source code files
    # ------------------------------------------------------------------
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        offset = tool_input.get("offset")  # set → targeted read, already located via SMT
        if offset is not None:
            sys.exit(0)  # targeted read — allow
        if Path(file_path).suffix not in _SOURCE_EXTS:
            sys.exit(0)  # not source code — allow
        name = Path(file_path).name
        stem = Path(file_path).stem
        _deny(
            f"Full-file read blocked. Use SMT first: smt scope {stem} / smt view <symbol> / smt grep \"<concept>\". "
            f"Then Read with offset+limit."
        )
        return

    # ------------------------------------------------------------------
    # Grep — block in favour of smt grep
    # ------------------------------------------------------------------
    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        short = pattern[:60].replace('"', '\\"')
        _deny(f'Grep blocked. Run: smt grep "{short}"')
        return


if __name__ == "__main__":
    main()
