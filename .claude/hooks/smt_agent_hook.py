#!/usr/bin/env python3
"""
PreToolUse hook — five responsibilities:

1. Agent (Explore)       → deny outright (too token-heavy)
2. advisor               → inject SMT skill via additionalContext
3. Read (full-file, src) → whitelist small files; redirect large files with smt scope output
4. Grep                  → deny and suggest smt grep
5. Bash (Windows tools)  → intercept findstr/Get-Content/Select-String, run smt grep
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).parent
_PROJECT_ROOT = _HOOK_DIR.parent.parent
_SKILL_MD = os.path.normpath(str(_HOOK_DIR / ".." / "skills" / "smt-analysis" / "SKILL.md"))

# Venv Python for running smt commands inside the hook
_VENV_PYTHON = (
    _PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else _PROJECT_ROOT / "venv" / "bin" / "python"
)
_SMT_CLI = _PROJECT_ROOT / "src" / "smt_cli.py"

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs"}

# Small pure-definition files — no graph traversal adds value; always allow direct Read
_SMALL_FILE_WHITELIST = {
    "exceptions.py", "hooks.py", "compat.py", "auth.py",
    "structures.py", "status_codes.py", "cookies.py",
}
_SMALL_FILE_LINE_LIMIT = 80  # also allow files short enough to fit in one screen

def _win_tool_invoked(cmd: str):
    """Return (True, tool_name) only when findstr/Get-Content/Select-String is
    the actual command being run — not when the word appears inside a string arg
    (e.g. a git commit message)."""
    # Strip any leading 'cd [/d] path &&' chains (common in benchmark sessions)
    stripped = re.sub(
        r'^(?:cd\s+(?:/d\s+)?(?:"[^"]*"|\S+)\s*&&\s*)+', '', cmd.strip(), flags=re.IGNORECASE
    )
    m = re.match(r'(findstr|Get-Content|Select-String)\b', stripped, re.IGNORECASE)
    if m:
        return True, m.group(1)
    # Piped form: some_cmd | Select-String "pattern"
    m = re.search(r'\|\s*(Select-String)\b', cmd, re.IGNORECASE)
    if m:
        return True, m.group(1)
    return False, ""


def _run_smt(*args: str, timeout: int = 12) -> str:
    """Run a smt command via the project venv and return stdout."""
    try:
        r = subprocess.run(
            [str(_VENV_PYTHON), str(_SMT_CLI)] + list(args),
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_PROJECT_ROOT),
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


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


def _extract_win_pattern(cmd: str) -> str:
    """Pull the search term out of a findstr / Select-String command."""
    # findstr /flags "pattern" file  or  findstr /C:"pattern"
    m = re.search(r'findstr(?:\s+/\w+)*\s+(?:/C:)?["\']((?:[^"\'\\]|\\.)+)["\']', cmd, re.IGNORECASE)
    if m:
        return m.group(1)
    # findstr /flags pattern  (unquoted)
    m = re.search(r'findstr(?:\s+/\w+)*\s+([^"\'\/\s|\\][^\s|\\]+)', cmd, re.IGNORECASE)
    if m and not m.group(1).startswith('/'):
        return m.group(1)
    # Select-String -Pattern "pattern"
    m = re.search(r'-Pattern\s+["\']((?:[^"\'\\]|\\.)+)["\']', cmd, re.IGNORECASE)
    if m:
        return m.group(1)
    # ... | Select-String "pattern"  (piped, no flag)
    m = re.search(r'Select-String\s+["\']((?:[^"\'\\]|\\.)+)["\']', cmd, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


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
    # Read — gate full-file source reads
    # ------------------------------------------------------------------
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        offset = tool_input.get("offset")

        if offset is not None:
            sys.exit(0)  # targeted read with offset — already located via SMT, allow

        p = Path(file_path)
        if p.suffix not in _SOURCE_EXTS:
            sys.exit(0)  # not source code — allow

        # Whitelist: small well-known definition-only files
        if p.name in _SMALL_FILE_WHITELIST:
            sys.exit(0)

        # Also allow any file short enough to read in full without waste
        try:
            line_count = sum(1 for _ in open(file_path, encoding="utf-8", errors="replace"))
            if line_count <= _SMALL_FILE_LINE_LIMIT:
                sys.exit(0)
        except Exception:
            pass

        # Larger source files: run smt scope and return the result inline
        # so the agent gets the symbol list without consuming an extra turn.
        scope_out = _run_smt("scope", file_path)
        if scope_out:
            _deny(
                f"Full-file Read intercepted — here is smt scope for {p.name}:\n\n"
                f"{scope_out}\n\n"
                f"Next: smt view <symbol>  to see source lines. "
                f"Or: Read with offset+limit once you know the line number."
            )
        else:
            stem = p.stem
            _deny(
                f"Full-file read blocked. Use SMT first: smt scope {stem} / smt view <symbol>. "
                f"Then Read with offset+limit."
            )
        return

    # ------------------------------------------------------------------
    # Grep — redirect to smt grep
    # ------------------------------------------------------------------
    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        short = pattern[:60].replace('"', '\\"')
        _deny(f'Grep blocked. Run: smt grep "{short}"')
        return

    # ------------------------------------------------------------------
    # Bash — intercept Windows-only search/read tools
    # ------------------------------------------------------------------
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        is_win, tool_matched = _win_tool_invoked(cmd)
        if not is_win:
            sys.exit(0)  # normal bash command — allow

        pattern = _extract_win_pattern(cmd)

        if pattern:
            grep_out = _run_smt("grep", pattern)
            if grep_out:
                _deny(
                    f"{tool_matched} blocked — smt grep result for '{pattern}':\n\n"
                    f"{grep_out}\n\n"
                    f"Next: smt view <symbol> to see the source body."
                )
                return

        _deny(
            f"{tool_matched} not available in this environment. "
            f"Use smt grep \"<pattern>\" instead."
        )
        return


if __name__ == "__main__":
    main()
