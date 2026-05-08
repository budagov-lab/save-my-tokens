#!/usr/bin/env python3
"""
Hook handler for PreToolUse and PostToolUse events.

PreToolUse responsibilities:
1. Agent (Explore)       → deny outright (too token-heavy)
2. advisor               → inject SMT skill via additionalContext
3. Read (full-file, src) → allow small files (≤ LINE_LIMIT); redirect large files with
                           smt list + smt view bodies so agent gets source inline
4. Grep                  → deny and suggest smt grep
5. Bash (Windows tools)  → intercept findstr/Get-Content/Select-String, run smt grep

PostToolUse responsibilities:
6. Skill (smt-analysis)  → inject follow-up reminder: use smt view, not Read
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

_SMT_CLI = _PROJECT_ROOT / "src" / "smt_cli.py"

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs"}

_SMALL_FILE_LINE_LIMIT = 80  # files this short are allowed through — no graph traversal needed

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
    """Run a smt command using the Python that is already running this hook.

    sys.executable is whatever Python launched the hook process — if Claude Code
    was started with the SMT venv active, that's already the right interpreter
    with all dependencies. No path hunting needed.

    Falls back to the project-local smt_cli.py if found, or 'smt' in PATH.
    """
    if _SMT_CLI.exists():
        # Same project or venv — use the hook's own Python interpreter
        cmd = [sys.executable, str(_SMT_CLI)] + list(args)
    else:
        # Deployed to another project (e.g. benchmark) — find smt in PATH
        import shutil
        found = shutil.which("smt") or shutil.which("smt.bat")
        if not found:
            return ""
        cmd = [found] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(_PROJECT_ROOT))
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _top_symbols_from_file(file_path: str, max_syms: int = 2) -> list:
    """Return up to max_syms Function/Class symbol names from a file via smt list."""
    out = _run_smt("list", "--module", file_path)
    if not out:
        return []
    syms = []
    for line in out.splitlines():
        m = re.match(r'\s+(\w+)\s+\[(?:Function|Class)\]', line)
        if m:
            syms.append(m.group(1))
            if len(syms) >= max_syms:
                break
    return syms


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


def _inject(context: str) -> None:
    """Inject additional context after a PostToolUse event (no blocking)."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
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

    # ------------------------------------------------------------------
    # UserPromptSubmit — capture original user question before agent paraphrases it.
    # Only writes on the FIRST message of each session; follow-up messages in the
    # same session are ignored so the original task stays as the ground truth.
    # ------------------------------------------------------------------
    if event.get("hook_event_name") == "UserPromptSubmit":
        prompt = event.get("prompt", "").strip()
        session_id = event.get("session_id", "")
        if prompt:
            task_file = _PROJECT_ROOT / ".smt" / "task.txt"
            session_file = _PROJECT_ROOT / ".smt" / "task_session.txt"
            try:
                task_file.parent.mkdir(exist_ok=True)
                current_session = session_file.read_text(encoding="utf-8").strip() if session_file.exists() else ""
                if current_session != session_id:
                    # New session — write task and record session id
                    task_file.write_text(prompt, encoding="utf-8")
                    session_file.write_text(session_id, encoding="utf-8")
                # Same session — keep the original first message, ignore this one
            except Exception:
                pass
        sys.exit(0)

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    # ------------------------------------------------------------------
    # PostToolUse — event has tool_response; PreToolUse does not
    # ------------------------------------------------------------------
    if "tool_response" in event:
        if tool_name == "Skill" and tool_input.get("skill") == "smt-analysis":
            # Clear task files so the next user message is treated as a new task
            for fname in ("task.txt", "task_session.txt"):
                try:
                    (_PROJECT_ROOT / ".smt" / fname).unlink(missing_ok=True)
                except Exception:
                    pass
            _inject(
                "─── SMT reminder ───\n"
                "You now have graph context. For source lines use smt view <symbol> — "
                "not the Read tool.\n"
                "smt view returns exact source with line numbers and needs no offset.\n"
                "────────────────────"
            )
        return

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

        # Allow any file short enough to read in full without waste
        try:
            line_count = sum(1 for _ in open(file_path, encoding="utf-8", errors="replace"))
            if line_count <= _SMALL_FILE_LINE_LIMIT:
                sys.exit(0)
        except Exception:
            pass

        # Larger source files: run smt list + smt view for top symbols,
        # returning everything inline so the agent needs no follow-up calls.
        parts = []
        scope_out = _run_smt("scope", file_path)
        if scope_out:
            parts.append(scope_out)

        top_syms = _top_symbols_from_file(file_path)
        for sym in top_syms:
            view_out = _run_smt("view", sym)
            if view_out:
                parts.append(f"--- smt view {sym} ---\n{view_out}")

        if parts:
            body = "\n\n".join(parts)
            _deny(
                f"Full-file Read intercepted — SMT output for {p.name}:\n\n"
                f"{body}\n\n"
                f"You have scope + source above. Use smt view <symbol> for more."
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
