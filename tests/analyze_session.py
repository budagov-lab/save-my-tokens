#!/usr/bin/env python3
"""Analyze SMT benchmark session logs (.jsonl) for failure patterns and regression causes.

Usage:
  python tests/analyze_session.py                       # all files in default runs dir
  python tests/analyze_session.py <file_or_dir> ...     # explicit paths
"""

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Windows consoles default to cp1251; force UTF-8 so em-dashes and task strings render.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUNS_DIR = Path("C:/Users/LENOVO/Desktop/Projects/bench/SWE_Context_lite/runs")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_events(path: str):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def extract_task(events) -> str:
    """Extract the task description from the SMT Analyst system prompt."""
    for e in events:
        if e.get("type") == "user":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "text":
                    text = m.get("text", "")
                    match = re.search(r"\*\*Task:\*\*\s*(.+?)(?:\n|$)", text)
                    if match:
                        return match.group(1).strip()
    # T23+ format: no **Task:** user message — fall back to first smt-analysis Skill call args
    for e in events:
        if e.get("type") == "assistant":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "tool_use" and m.get("name") == "Skill":
                    if m.get("input", {}).get("skill") == "smt-analysis":
                        args = m["input"].get("args", "")
                        if args:
                            return str(args)[:200]
    return "?"


def extract_skill_md(events) -> str:
    """Return the full SKILL.md system prompt text (the SMT Analyst block)."""
    for e in events:
        if e.get("type") == "user":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "text" and "SMT Analyst" in m.get("text", ""):
                    return m["text"]
    return ""


# ---------------------------------------------------------------------------
# Timeline extraction
# ---------------------------------------------------------------------------

def extract_timeline(events):
    """Return ordered list of tool-call dicts: turn, name, input, result, is_error."""
    tool_map = {}
    result_map = {}

    for e in events:
        if e.get("type") == "assistant":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "tool_use":
                    tool_map[m["id"]] = (m.get("name", ""), m.get("input", {}))
        elif e.get("type") == "user":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "tool_result":
                    tid = m.get("tool_use_id", "")
                    content = m.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict)
                        )
                    # Prefer explicit is_error field; fall back to Exit code pattern
                    explicit = m.get("is_error")
                    if explicit is True:
                        is_error = True
                    elif explicit is False:
                        is_error = False
                    else:
                        is_error = (
                            str(content).startswith("Exit code")
                            and "Exit code 0" not in str(content)
                        )
                    result_map[tid] = (str(content), is_error)

    timeline = []
    turn = 0
    for e in events:
        if e.get("type") != "assistant":
            continue
        turn += 1
        for m in e.get("message", {}).get("content", []):
            if not isinstance(m, dict) or m.get("type") != "tool_use":
                continue
            tid = m["id"]
            name, inp = tool_map.get(tid, ("?", {}))
            result, is_error = result_map.get(tid, ("(no result)", False))
            timeline.append(
                dict(turn=turn, name=name, input=inp, result=result, is_error=is_error)
            )
    return timeline


# ---------------------------------------------------------------------------
# Analysis helpers — Bash / SMT
# ---------------------------------------------------------------------------

def compute_smt_vs_fallback(timeline):
    bash = [t for t in timeline if t["name"] == "Bash"]
    smt = [t for t in bash if t["input"].get("command", "").strip().startswith("smt ")]
    fallback = [t for t in bash if not t["input"].get("command", "").strip().startswith("smt ")]
    smt_ok = [t for t in smt if not t["is_error"]]
    smt_err = [t for t in smt if t["is_error"]]
    return bash, smt_ok, smt_err, fallback


def first_fallback_turn(timeline):
    for t in timeline:
        if t["name"] == "Bash" and not t["input"].get("command", "").strip().startswith("smt "):
            return t["turn"]
    return None


def smt_subcommand_counts(timeline):
    counts = Counter()
    for t in timeline:
        if t["name"] != "Bash":
            continue
        cmd = t["input"].get("command", "").strip()
        m = re.match(r"smt\s+(\w[\w-]*)", cmd)
        if m:
            counts[m.group(1)] += 1
    return counts


def smt_abandonment_turn(timeline):
    """Return the turn where agent stops using smt entirely and never comes back."""
    last_smt = None
    last_bash = None
    for t in timeline:
        if t["name"] != "Bash":
            continue
        cmd = t["input"].get("command", "").strip()
        last_bash = t["turn"]
        if cmd.startswith("smt "):
            last_smt = t["turn"]
    if last_smt is None:
        return 1
    if last_bash and last_bash > last_smt + 4:
        return last_smt
    return None


# ---------------------------------------------------------------------------
# 18-pattern detector suite
# ---------------------------------------------------------------------------

def _bash_errs(timeline):
    return [t for t in timeline if t["name"] == "Bash" and t["is_error"]]

def _bash_all(timeline):
    return [t for t in timeline if t["name"] == "Bash"]


def detect_P01_symbol_not_found(timeline):
    """smt definition/view/lookup returning 'not found in graph'."""
    hits = []
    for t in _bash_errs(timeline):
        cmd = t["input"].get("command", "").strip()
        if re.match(r"smt\s+(definition|view|lookup)\b", cmd) and "not found in graph" in t["result"]:
            sym = re.search(r"smt\s+\w+\s+\"?([^\s\"]+)", cmd)
            hits.append(sym.group(1) if sym else cmd[:60])
    return hits


def detect_P02_view_depth_flag(timeline):
    """smt view called with --depth (not supported; use smt context)."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if re.search(r"smt\s+view\b.*--depth", t["input"].get("command",""))]


def detect_P03_grep_wrong_flag(timeline):
    """smt grep with --compact / --head / --head_limit (now fixed with alias for --head)."""
    hits = []
    for t in _bash_all(timeline):
        cmd = t["input"].get("command", "").strip()
        if not re.match(r"smt\s+grep\b", cmd):
            continue
        # Only inspect the grep portion — stop at ' && ' or ' | ' so chained commands like
        # "smt grep X && smt context X --compact" don't produce false positives.
        # Use spaced separators to avoid splitting on \| inside quoted grep patterns.
        grep_part = re.split(r"\s+&&\s+|\s+\|\s+", cmd)[0]
        if re.search(r"--compact|--head(?:_limit)?", grep_part):
            hits.append((cmd[:80], t["is_error"]))
    return hits


def detect_P04_unsupported_file_flag(timeline):
    """--file flag used on smt impact/lookup/grep (only valid on definition/view/context)."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if re.search(r"smt\s+(impact|grep|lookup)\b.*--file", t["input"].get("command",""))]


def detect_P05_multiple_symbols(timeline):
    """smt definition/view returning 'Multiple symbols named X'."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if "Multiple symbols" in t["result"]]


def detect_P06_cd_bad_path(timeline):
    """cd to nonexistent path (skills dir, /smt, /tmp/smt-work, etc.)."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if re.match(r"cd\s+", t["input"].get("command","").strip())
            and ("No such file" in t["result"] or "bash: line" in t["result"])]


def detect_P07_backslash_path(timeline):
    """Unquoted Windows backslash path fed to bash grep/find/cat/head — bash strips the backslashes."""
    hits = []
    for t in _bash_errs(timeline):
        cmd = t["input"].get("command", "").strip()
        # unquoted C:\ path: not preceded by a quote
        if re.search(r"(?<!\")(grep|find|cat|head)\b[^\"]*[A-Z]:\\", cmd):
            hits.append(cmd[:80])
    return hits


def detect_P08_windows_cmd_tools(timeline):
    """findstr / Get-Content / Select-String used in bash (only work in PowerShell/CMD)."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if re.search(r"\b(findstr|Get-Content|Select-String)\b", t["input"].get("command",""))]


def detect_P09_scope_ambiguous(timeline):
    """smt scope <basename> matching multiple files — need full relative path."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if "smt scope" in t["input"].get("command","")
            and "Multiple files match" in t["result"]]


def detect_P10_dotenv_errors(timeline):
    """python-dotenv parse error crashing all smt commands in this project."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if "python-dotenv could not parse" in t["result"]]


def detect_P11_view_file_missing(timeline):
    """smt view symbol that exists in graph but whose source file is missing on disk."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if re.search(r"smt\s+view\b", t["input"].get("command",""))
            and "File not found" in t["result"]]


def detect_P12_pytest_broken(timeline):
    """pytest run fails with ImportError in conftest — benchmark env can't run tests."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if "pytest" in t["input"].get("command","") and "ImportError" in t["result"]]


def detect_P13_wsl_path(timeline):
    """/mnt/c/ paths used on native Windows bash — WSL path format doesn't exist here."""
    return [t["input"].get("command","")[:80] for t in _bash_errs(timeline)
            if "/mnt/c/" in t["input"].get("command","")]


def detect_P14_pipe_masks_error(timeline):
    """smt command piped to head/grep: if smt exits non-zero, head exits 0 masking the error."""
    hits = []
    for t in _bash_all(timeline):
        cmd = t["input"].get("command", "").strip()
        if not t["is_error"] and re.match(r"smt\s+", cmd) and "|" in cmd:
            if re.search(r"--output_mode\b", cmd):
                hits.append(cmd[:80])
    return hits


def detect_P15_read_directory(timeline):
    """Read tool called on a directory path instead of a file."""
    return [t["input"].get("file_path","")[-60:] for t in timeline
            if t["name"] == "Read" and t["is_error"] and "EISDIR" in t["result"]]


def detect_P16_read_empty_offset(timeline):
    """Read blocked: agent passed offset='' (empty string) — hook treats it as no offset."""
    hits = []
    for t in timeline:
        if t["name"] != "Read" or not t["is_error"]:
            continue
        if "Full-file read blocked" not in t["result"]:
            continue
        offset = t["input"].get("offset", None)
        if offset == "" or offset == 0:
            fp = Path(t["input"].get("file_path","")).name
            hits.append(f"{fp} (offset={repr(offset)})")
    return hits


def detect_P17_read_blocked(timeline):
    """Read blocked: no offset provided — hook requires SMT lookup first."""
    hits = []
    for t in timeline:
        if t["name"] != "Read" or not t["is_error"]:
            continue
        if "Full-file read blocked" not in t["result"]:
            continue
        offset = t["input"].get("offset", None)
        if offset not in ("", 0):
            fp = Path(t["input"].get("file_path","")).name
            hits.append(fp)
    return hits


def detect_P18_grep_tool_blocked(timeline):
    """Grep tool blocked by hook — agent should use 'smt grep' directly."""
    hits = []
    for t in timeline:
        if t["name"] == "Grep" and t["is_error"] and "Grep blocked" in t["result"]:
            hits.append(t["input"].get("pattern","")[:60])
    return hits


def detect_P19_lookup_regen(timeline):
    """smt lookup triggered full embedding re-generation (FAISS not pre-built)."""
    return sum(1 for t in _bash_all(timeline)
               if t["input"].get("command","").strip().startswith("smt lookup")
               and "Generating embeddings" in t["result"])


def detect_P20_list_empty(timeline):
    """smt list --module returning nothing despite graph having nodes."""
    return [t["input"].get("command","")[:80] for t in _bash_all(timeline)
            if t["input"].get("command","").strip().startswith("smt list")
            and "No symbols found" in t["result"]]


# Aggregate all patterns into one dict for a session
def detect_all_patterns(timeline) -> dict:
    return {
        "P01_symbol_not_found":    detect_P01_symbol_not_found(timeline),
        "P02_view_depth_flag":     detect_P02_view_depth_flag(timeline),
        "P03_grep_wrong_flag":     detect_P03_grep_wrong_flag(timeline),
        "P04_unsupported_file":    detect_P04_unsupported_file_flag(timeline),
        "P05_multiple_symbols":    detect_P05_multiple_symbols(timeline),
        "P06_cd_bad_path":         detect_P06_cd_bad_path(timeline),
        "P07_backslash_path":      detect_P07_backslash_path(timeline),
        "P08_windows_cmd_tools":   detect_P08_windows_cmd_tools(timeline),
        "P09_scope_ambiguous":     detect_P09_scope_ambiguous(timeline),
        "P10_dotenv_errors":       detect_P10_dotenv_errors(timeline),
        "P11_view_file_missing":   detect_P11_view_file_missing(timeline),
        "P12_pytest_broken":       detect_P12_pytest_broken(timeline),
        "P13_wsl_path":            detect_P13_wsl_path(timeline),
        "P14_pipe_masks_error":    detect_P14_pipe_masks_error(timeline),
        "P15_read_directory":      detect_P15_read_directory(timeline),
        "P16_read_empty_offset":   detect_P16_read_empty_offset(timeline),
        "P17_read_blocked":        detect_P17_read_blocked(timeline),
        "P18_grep_tool_blocked":   detect_P18_grep_tool_blocked(timeline),
        "P19_lookup_regen":        detect_P19_lookup_regen(timeline),
        "P20_list_empty":          detect_P20_list_empty(timeline),
    }


# Pattern metadata: description and severity
_PATTERN_META = {
    "P01_symbol_not_found":  ("HIGH", "smt definition/view/lookup -> symbol not found in graph (class method naming mismatch)"),
    "P02_view_depth_flag":   ("MED",  "smt view --depth not supported; use smt context --depth instead"),
    "P03_grep_wrong_flag":   ("HIGH", "smt grep with --compact/--head/--head_limit (now fixed with --top alias)"),
    "P04_unsupported_file":  ("MED",  "--file flag used on smt impact/grep/lookup (only valid on definition/view/context)"),
    "P05_multiple_symbols":  ("MED",  "smt definition/view ambiguous: Multiple symbols named X -> add --file"),
    "P06_cd_bad_path":       ("HIGH", "cd to nonexistent path before smt -> smt runs in wrong dir or fails"),
    "P07_backslash_path":    ("HIGH", "unquoted C:\\ path in bash -> backslashes stripped -> file not found"),
    "P08_windows_cmd_tools": ("HIGH", "findstr/Get-Content/Select-String in bash -> command not found"),
    "P09_scope_ambiguous":   ("HIGH", "smt scope <basename> matches multiple files -> use full relative path"),
    "P10_dotenv_errors":     ("CRIT", "python-dotenv parse error -> every smt command fails in this project"),
    "P11_view_file_missing": ("MED",  "smt view: symbol in graph but source file missing from benchmark checkout"),
    "P12_pytest_broken":     ("LOW",  "pytest conftest ImportError -> can't run tests in benchmark env"),
    "P13_wsl_path":          ("MED",  "/mnt/c/ path used on native Windows bash (not WSL)"),
    "P14_pipe_masks_error":  ("MED",  "smt cmd | head: if smt fails, head exits 0 masking the error"),
    "P15_read_directory":    ("MED",  "Read tool called on a directory path -> EISDIR"),
    "P16_read_empty_offset": ("HIGH", "Read with offset='' (empty string) blocked same as full-file read"),
    "P17_read_blocked":      ("HIGH", "Read without offset blocked by hook -> agent needs smt first"),
    "P18_grep_tool_blocked": ("HIGH", "Grep tool blocked by hook -> use smt grep directly"),
    "P19_lookup_regen":      ("MED",  "smt lookup triggered embedding regeneration (run smt build first)"),
    "P20_list_empty":        ("LOW",  "smt list --module returning empty (path/module name mismatch)"),
}


# Legacy aliases for backward compat with existing callers
def find_scope_ambiguous(timeline):
    return detect_P09_scope_ambiguous(timeline)

def find_dotenv_errors(timeline):
    return len(detect_P10_dotenv_errors(timeline))

def find_cd_errors(timeline):
    return detect_P06_cd_bad_path(timeline)

def find_path_errors(timeline):
    return detect_P07_backslash_path(timeline)

def find_scope_errors(timeline):
    hits = []
    for t in timeline:
        if t["name"] != "Bash" or not t["is_error"]:
            continue
        cmd = t["input"].get("command", "").strip()
        if cmd.startswith("smt scope"):
            hits.append((cmd, t["result"][:80]))
    return hits

def find_list_errors(timeline):
    return [(c, "") for c in detect_P20_list_empty(timeline)]

def find_lookup_regenerations(timeline):
    return detect_P19_lookup_regen(timeline)

def find_grep_flag_errors(timeline):
    return detect_P03_grep_wrong_flag(timeline)

def find_flag_errors(timeline):
    return []  # subsumed by P03/P04


# ---------------------------------------------------------------------------
# Analysis helpers — non-Bash tools
# ---------------------------------------------------------------------------

def analyze_read_calls(timeline):
    """Categorize Read calls: full-file blocks, partial reads (offset/limit), successful."""
    blocked, partial, ok = [], [], []
    for t in timeline:
        if t["name"] != "Read":
            continue
        inp = t["input"]
        fp = inp.get("file_path", "")
        fname = Path(fp).name if fp else "?"
        has_offset = "offset" in inp or "limit" in inp
        if t["is_error"] or "Full-file read blocked" in t["result"]:
            blocked.append(fname)
        elif has_offset:
            partial.append(fname)
        else:
            ok.append(fname)
    return blocked, partial, ok


def analyze_grep_calls(timeline):
    """Classify Grep tool calls: hook-blocked vs successful."""
    blocked, ok = [], []
    for t in timeline:
        if t["name"] != "Grep":
            continue
        pat = t["input"].get("pattern", "")
        path = t["input"].get("path", "")
        label = f'pattern="{pat[:50]}"' + (f' path={path}' if path else '')
        if t["is_error"] or "Grep blocked" in t["result"]:
            blocked.append(label)
        else:
            ok.append(label)
    return blocked, ok


def analyze_skill_calls(timeline):
    """Return list of (skill_name, args, success) for Skill tool calls."""
    calls = []
    for t in timeline:
        if t["name"] != "Skill":
            continue
        skill = t["input"].get("skill", "?")
        args = t["input"].get("args", "")
        calls.append((skill, str(args)[:80], not t["is_error"]))
    return calls


def analyze_edit_calls(timeline):
    """Return list of files touched by Edit/Write tool calls."""
    edits = []
    for t in timeline:
        if t["name"] not in ("Edit", "Write"):
            continue
        fp = t["input"].get("file_path", "?")
        fname = Path(fp).name if fp != "?" else "?"
        edits.append((t["name"], fname, not t["is_error"]))
    return edits


def analyze_glob_calls(timeline):
    """Return list of (pattern, success) for Glob calls."""
    calls = []
    for t in timeline:
        if t["name"] != "Glob":
            continue
        pat = t["input"].get("pattern", "?")
        calls.append((pat, not t["is_error"]))
    return calls


def tool_call_summary(timeline):
    """Return Counter of {tool_name: total} and {tool_name: errors}."""
    totals = Counter()
    errors = Counter()
    for t in timeline:
        totals[t["name"]] += 1
        if t["is_error"]:
            errors[t["name"]] += 1
    return totals, errors


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_log_between(after_iso: str, before_iso: str, repo: str = ".") -> list:
    """Return list of (hash, date, subject) for commits in the time window."""
    try:
        out = subprocess.check_output(
            ["git", "-C", repo, "log", "--oneline",
             f"--after={after_iso}", f"--before={before_iso}",
             "--format=%h %ai %s"],
            stderr=subprocess.DEVNULL, text=True
        )
        lines = [l.strip() for l in out.strip().splitlines() if l.strip()]
        return lines
    except Exception:
        return []


def parse_ts(stem: str) -> str:
    """Extract ISO timestamp from filename stem like psf__requests-863__smt__2026-05-07T15-52-18."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})$", stem)
    if m:
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}"
    return ""


# ---------------------------------------------------------------------------
# Single-session report
# ---------------------------------------------------------------------------

def analyze_one(path: str) -> dict:
    events = load_events(path)
    timeline = extract_timeline(events)
    task = extract_task(events)
    skill_md = extract_skill_md(events)

    bash, smt_ok, smt_err, fallback = compute_smt_vs_fallback(timeline)
    result_event = next((e for e in events if e.get("type") == "result"), None)
    totals, errors = tool_call_summary(timeline)
    read_blocked, read_partial, read_ok = analyze_read_calls(timeline)
    grep_blocked, grep_ok = analyze_grep_calls(timeline)
    patterns = detect_all_patterns(timeline)

    return dict(
        path=path,
        stem=Path(path).stem,
        task=task,
        skill_md=skill_md,
        outcome=result_event.get("subtype", "?") if result_event else "?",
        turns=result_event.get("num_turns") if result_event else None,
        cost=result_event.get("total_cost_usd") if result_event else None,
        cache_read=(result_event or {}).get("usage", {}).get("cache_read_input_tokens", 0),
        output_tokens=(result_event or {}).get("usage", {}).get("output_tokens", 0),
        # Bash / SMT
        smt_ok=len(smt_ok),
        smt_err=len(smt_err),
        fallback=len(fallback),
        smt_counts=smt_subcommand_counts(timeline),
        pivot_turn=first_fallback_turn(timeline),
        abandonment_turn=smt_abandonment_turn(timeline),
        # Legacy single-field accessors (used by print_single)
        flag_errors=find_flag_errors(timeline),
        grep_flag_errors=find_grep_flag_errors(timeline),
        scope_errors=find_scope_errors(timeline),
        scope_ambiguous=find_scope_ambiguous(timeline),
        list_errors=find_list_errors(timeline),
        regen_count=find_lookup_regenerations(timeline),
        cd_errors=find_cd_errors(timeline),
        path_errors=find_path_errors(timeline),
        dotenv_errors=find_dotenv_errors(timeline),
        # All tools
        tool_totals=totals,
        tool_errors=errors,
        read_blocked=read_blocked,
        read_partial=read_partial,
        read_ok=read_ok,
        grep_blocked=grep_blocked,
        grep_ok=grep_ok,
        skill_calls=analyze_skill_calls(timeline),
        edit_calls=analyze_edit_calls(timeline),
        glob_calls=analyze_glob_calls(timeline),
        # Full 20-pattern hit dict
        patterns=patterns,
        timeline=timeline,
    )


# ---------------------------------------------------------------------------
# Cross-session comparison
# ---------------------------------------------------------------------------

def group_by_instance(paths):
    """Group file paths by instance name, return {instance: [sorted paths]}."""
    groups = defaultdict(list)
    for p in paths:
        stem = Path(p).stem
        # psf__requests-863__smt__2026-05-07T15-52-18
        m = re.match(r"(.+?)__smt__(.+)$", stem)
        if m:
            groups[m.group(1)].append(p)
        else:
            groups[stem].append(p)
    # Sort each group by timestamp
    for k in groups:
        groups[k].sort(key=lambda p: parse_ts(Path(p).stem))
    return dict(groups)


def diff_skill_md(md1: str, md2: str) -> list:
    """Return list of lines added in md2 vs md1 (simple line diff)."""
    set1 = set(md1.splitlines())
    set2 = set(md2.splitlines())
    return sorted(set2 - set1)


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_single(s: dict):
    label = Path(s["path"]).stem
    print(f"{'='*70}")
    print(f"SESSION: {label}")
    print(f"OUTCOME: {s['outcome']}  |  turns={s['turns']}  |  cost=${s['cost']:.4f}")
    print(f"TASK:    {s['task']}")
    print(f"{'='*70}")

    # --- All-tool summary ---
    totals = s["tool_totals"]
    errors = s["tool_errors"]
    total_calls = sum(totals.values())
    print(f"\nALL TOOL CALLS  (total: {total_calls})")
    for tool, count in totals.most_common():
        err = errors.get(tool, 0)
        err_str = f"  {err} err" if err else ""
        print(f"  {tool:<12} {count:3d}{err_str}")

    # --- Bash / SMT breakdown ---
    bash_total = s["smt_ok"] + s["smt_err"] + s["fallback"]
    print(f"\nBASH BREAKDOWN  (total: {bash_total})")
    print(f"  smt success   : {s['smt_ok']:3d}")
    print(f"  smt errors    : {s['smt_err']:3d}")
    print(f"  fallback bash : {s['fallback']:3d}")
    if s["pivot_turn"]:
        print(f"  first fallback at turn {s['pivot_turn']}")
    if s["smt_counts"]:
        print(f"  smt breakdown : {dict(s['smt_counts'])}")

    # --- Read tool ---
    read_total = len(s["read_blocked"]) + len(s["read_partial"]) + len(s["read_ok"])
    if read_total:
        print(f"\nREAD CALLS  (total: {read_total})")
        print(f"  ok (no offset)  : {len(s['read_ok']):3d}  {s['read_ok'][:5]}")
        print(f"  partial (offset): {len(s['read_partial']):3d}  {s['read_partial'][:5]}")
        if s["read_blocked"]:
            print(f"  BLOCKED         : {len(s['read_blocked']):3d}  [full-file read without SMT first]")
            for f in s["read_blocked"][:5]:
                print(f"    {f}")

    # --- Grep tool ---
    grep_total = len(s["grep_blocked"]) + len(s["grep_ok"])
    if grep_total:
        print(f"\nGREP TOOL CALLS  (total: {grep_total})")
        if s["grep_ok"]:
            print(f"  ok      : {len(s['grep_ok']):3d}")
        if s["grep_blocked"]:
            print(f"  BLOCKED : {len(s['grep_blocked']):3d}  [hook redirects to smt grep]")
            for label in s["grep_blocked"][:5]:
                print(f"    {label}")

    # --- Skill calls ---
    if s["skill_calls"]:
        print(f"\nSKILL CALLS  (total: {len(s['skill_calls'])})")
        for skill, args, ok in s["skill_calls"]:
            status = "ok " if ok else "ERR"
            print(f"  [{status}] {skill}  args={args[:70]}")

    # --- Edit / Write ---
    if s["edit_calls"]:
        print(f"\nEDIT/WRITE CALLS  (total: {len(s['edit_calls'])})")
        for tool, fname, ok in s["edit_calls"]:
            status = "ok " if ok else "ERR"
            print(f"  [{status}] {tool:<5}  {fname}")

    # --- Glob ---
    if s["glob_calls"]:
        print(f"\nGLOB CALLS  (total: {len(s['glob_calls'])})")
        for pat, ok in s["glob_calls"]:
            status = "ok " if ok else "ERR"
            print(f"  [{status}] {pat}")

    # --- All 20 patterns ---
    pats = s["patterns"]
    has_any = any(
        (len(v) if isinstance(v, list) else v) > 0
        for v in pats.values()
    )
    if has_any:
        print(f"\nFAILURE PATTERNS  (20-pattern suite)")
        for key, hits in pats.items():
            n = len(hits) if isinstance(hits, list) else hits
            if not n:
                continue
            sev, desc = _PATTERN_META.get(key, ("?", key))
            print(f"  [{sev}] {key}  x{n}")
            print(f"         {desc}")
            examples = hits if isinstance(hits, list) else []
            for ex in examples[:2]:
                print(f"         -> {str(ex)[:90]}")

    aband = s.get("abandonment_turn")
    if aband:
        print(f"\nSMT ABANDONMENT at turn {aband}: agent stopped using smt and switched to grep/sed/Read loops")

    print()


def print_comparison(instance: str, sessions: list, repo: str = "."):
    """Print a before/after comparison for two or more sessions of the same instance."""
    print(f"\n{'#'*70}")
    print(f"# INSTANCE: {instance}  ({len(sessions)} sessions)")
    print(f"{'#'*70}")

    # Summary table
    print(f"\n{'Session':<45} {'turns':>5} {'cost':>8} {'smt_ok':>6} {'smt_err':>7} {'fallbk':>6} {'rd_blk':>6} {'gr_blk':>6}")
    print("-" * 95)
    for s in sessions:
        ts = parse_ts(s["stem"]) or s["stem"][-19:]
        turns = str(s["turns"]) if s["turns"] is not None else "?"
        cost = f"${s['cost']:.4f}" if s["cost"] is not None else "?"
        rb = len(s["read_blocked"])
        gb = len(s["grep_blocked"])
        print(f"  {ts:<43} {turns:>5} {cost:>8} {s['smt_ok']:>6} {s['smt_err']:>7} {s['fallback']:>6} {rb:>6} {gb:>6}")

    # Task differences
    tasks = [s["task"] for s in sessions]
    if len(set(tasks)) > 1:
        print(f"\nTASK DIFFERENCES (non-identical prompts across runs):")
        for i, s in enumerate(sessions):
            ts = parse_ts(s["stem"]) or s["stem"]
            print(f"  [{ts}] {s['task'][:100]}")
    else:
        print(f"\nTASK: {tasks[0][:100]} (identical across runs)")

    # Git changes between first and last session
    if len(sessions) >= 2:
        t_first = parse_ts(sessions[0]["stem"])
        t_last = parse_ts(sessions[-1]["stem"])
        if t_first and t_last:
            commits = git_log_between(t_first, t_last, repo)
            print(f"\nGIT COMMITS between {t_first} and {t_last}:")
            if commits:
                for c in commits:
                    print(f"  {c}")
            else:
                print("  (none — same code base)")

    # SKILL.md diff between first and last
    if len(sessions) >= 2:
        added = diff_skill_md(sessions[0]["skill_md"], sessions[-1]["skill_md"])
        removed_lines = diff_skill_md(sessions[-1]["skill_md"], sessions[0]["skill_md"])
        if added or removed_lines:
            print(f"\nSKILL.md CHANGES (first -> last):")
            for l in added[:10]:
                if l.strip():
                    print(f"  + {l[:100]}")
            for l in removed_lines[:10]:
                if l.strip():
                    print(f"  - {l[:100]}")
        else:
            print(f"\nSKILL.md: identical across runs")

    # Regression analysis (compare each pair)
    if len(sessions) >= 2:
        s1, s2 = sessions[0], sessions[-1]
        c1 = s1["cost"] or 0
        c2 = s2["cost"] or 0
        delta_cost = c2 - c1
        delta_turns = (s2["turns"] or 0) - (s1["turns"] or 0)
        verdict = "IMPROVED" if delta_cost < -0.005 else "REGRESSED" if delta_cost > 0.005 else "SIMILAR"
        print(f"\nVERDICT: {verdict}  (dcost={delta_cost:+.4f}, dturns={delta_turns:+d})")

        # New pattern hits in s2 vs s1
        if verdict == "REGRESSED":
            print(f"\nREGRESSION CAUSES (pattern deltas):")
            p1, p2 = s1["patterns"], s2["patterns"]
            any_cause = False
            for key in sorted(p1.keys()):
                v1 = len(p1[key]) if isinstance(p1[key], list) else p1[key]
                v2 = len(p2[key]) if isinstance(p2[key], list) else p2[key]
                delta = v2 - v1
                if delta > 0:
                    sev, desc = _PATTERN_META.get(key, ("?", key))
                    print(f"  [{sev}] {key}: {v1} -> {v2} (+{delta})")
                    print(f"         {desc}")
                    any_cause = True
            if not any_cause:
                if len(set(tasks)) > 1:
                    print(f"  [INFO] No pattern increase — task prompt was broader (more exploration expected)")
                else:
                    print(f"  [INFO] No pattern increase detected — likely LLM variance")
    print()

    # Individual session details
    for s in sessions:
        print_single(s)


# ---------------------------------------------------------------------------
# Global cross-batch report
# ---------------------------------------------------------------------------

# Metric name -> (key_in_session, how_to_count)
# Each metric extracts a scalar from an analyzed session dict.
def _pat_count(s, key):
    v = s["patterns"].get(key, [])
    return len(v) if isinstance(v, list) else v

_METRICS = [
    # Top-level
    ("cost_usd",      lambda s: s["cost"] or 0),
    ("turns",         lambda s: s["turns"] or 0),
    ("total_calls",   lambda s: sum(s["tool_totals"].values())),
    ("total_errors",  lambda s: sum(s["tool_errors"].values())),
    # Tool breakdown
    ("Bash",          lambda s: s["tool_totals"].get("Bash", 0)),
    ("Read",          lambda s: s["tool_totals"].get("Read", 0)),
    ("Skill",         lambda s: s["tool_totals"].get("Skill", 0)),
    ("Edit",          lambda s: s["tool_totals"].get("Edit", 0)),
    ("Grep_tool",     lambda s: s["tool_totals"].get("Grep", 0)),
    ("smt_ok",        lambda s: s["smt_ok"]),
    ("smt_err",       lambda s: s["smt_err"]),
    ("bash_fallback", lambda s: s["fallback"]),
    # 20 patterns
] + [(k, lambda s, k=k: _pat_count(s, k)) for k in sorted(_PATTERN_META.keys())]


def _batch_label(s: dict) -> str:
    """Return date+hour label like '05-07T15' for grouping sessions into batches."""
    ts = parse_ts(s["stem"])
    return ts[5:13] if ts else "??"   # "MM-DDTHH" — unique per hour, sorts chronologically


def print_global_report(all_sessions: list):
    """Print a cross-batch comparison table for every tool-call metric."""
    # Group into batches by date+hour (chronological, cross-midnight safe)
    batch_map: dict = defaultdict(list)
    for s in all_sessions:
        batch_map[_batch_label(s)].append(s)

    # Sort batches by the earliest session timestamp they contain (chronological order)
    batches = sorted(batch_map.keys(), key=lambda lbl: min(parse_ts(s["stem"]) for s in batch_map[lbl]))
    if len(batches) < 2:
        return  # nothing to compare

    # Compare baseline (first) vs latest (last); intermediate batches appear in matrix rows
    b1_label = batches[0]
    b2_label = batches[-1]
    b1, b2 = batch_map[b1_label], batch_map[b2_label]

    def agg(sessions, fn):
        vals = [fn(s) for s in sessions]
        return sum(vals), sum(vals) / max(len(vals), 1)

    print("=" * 70)
    print(f"GLOBAL CROSS-BATCH COMPARISON  ({len(batches)} batches: {', '.join(batches)})")
    if len(batches) > 2:
        mid = ', '.join(batches[1:-1])
        print(f"  Baseline={b1_label}  Latest={b2_label}  (intermediate: {mid})")
    print("=" * 70)
    print(f"\n{'Metric':<20} {'batch '+b1_label+' total':>16} {'avg':>6}  {'batch '+b2_label+' total':>16} {'avg':>6}  {'trend':>8}")
    print("-" * 80)

    regressions = []
    improvements = []

    for name, fn in _METRICS:
        t1, a1 = agg(b1, fn)
        t2, a2 = agg(b2, fn)
        if name in ("cost_usd",):
            v1, v2 = f"${t1:.3f}", f"${t2:.3f}"
            a1s, a2s = f"${a1:.3f}", f"${a2:.3f}"
        else:
            v1, v2 = str(int(t1)), str(int(t2))
            a1s, a2s = f"{a1:.1f}", f"{a2:.1f}"

        delta = t2 - t1
        if abs(delta) < 0.001:
            trend = "="
        elif delta > 0:
            if t1 < 0.001:
                trend = f"+{int(t2)} NEW"
            else:
                pct = 100 * delta / t1
                trend = f"+{pct:.0f}%"
            if name not in ("total_calls", "Bash", "Read", "smt_ok", "Edit", "Read_partial"):
                regressions.append((name, t1, t2, delta))
        else:
            if t1 < 0.001:
                trend = "="
            else:
                pct = 100 * abs(delta) / t1
                trend = f"-{pct:.0f}%"
            if name in ("smt_ok",):
                regressions.append((name, t1, t2, delta))
            else:
                improvements.append((name, t1, t2, abs(delta)))

        print(f"  {name:<18} {v1:>16} {a1s:>6}  {v2:>16} {a2s:>6}  {trend:>8}")

    # Per-session pattern hit matrix
    pat_keys = sorted(_PATTERN_META.keys())
    hdr = f"  {'session':<30}"
    for k in pat_keys:
        hdr += f" {k[1:3]:>3}"
    hdr += f" | {'err':>4} {'cost':>7} {'turns':>5}"
    print(f"\nPER-SESSION PATTERN MATRIX  (column = P01..P20, value = hit count)")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for s in all_sessions:
        ts = parse_ts(s["stem"])
        inst = s["stem"].split("__smt__")[0].replace("psf__requests-", "")
        label = f"{inst}  {ts[11:]}"
        row = f"  {label:<30}"
        total_hits = 0
        for k in pat_keys:
            n = _pat_count(s, k)
            total_hits += n
            row += f" {n if n else '.':>3}"
        total_err = sum(s["tool_errors"].values())
        cost_s = f"${s['cost']:.4f}" if s["cost"] else "?"
        row += f" | {total_err:>4} {cost_s:>7} {str(s['turns'] or '?'):>5}"
        print(row)

    # Git commit timelines between every consecutive batch pair
    smt_repo = str(Path(__file__).parent.parent)
    for i in range(len(batches) - 1):
        ba_label, bb_label = batches[i], batches[i + 1]
        ba, bb = batch_map[ba_label], batch_map[bb_label]
        t_a_last = max((parse_ts(s["stem"]) for s in ba), default="")
        t_b_first = min((parse_ts(s["stem"]) for s in bb), default="")
        if not (t_a_last and t_b_first):
            continue
        commits = git_log_between(t_a_last, t_b_first, smt_repo)
        print(f"\nGIT COMMITS  batch {ba_label} -> {bb_label}  ({t_a_last} … {t_b_first}):")
        if commits:
            for c in commits:
                print(f"  {c}")
            for c in commits:
                msg = c.lower()
                affects = []
                if "scope" in msg:
                    affects.append("P09_scope_ambiguous")
                if "skill" in msg or "shell" in msg or "cd" in msg:
                    affects.append("P06_cd_bad_path")
                if "grep" in msg:
                    affects.append("P03_grep_wrong_flag")
                if "dotenv" in msg or ".env" in msg:
                    affects.append("P10_dotenv_errors")
                if "orient" in msg or "argument" in msg:
                    affects.append("skill_ERR_parens")
                if affects:
                    print(f"    -> likely affects: {', '.join(affects)}")
        else:
            print("  (none)")

    # Summary verdict (baseline vs latest)
    print(f"\nSUMMARY  ({b1_label} -> {b2_label})")
    if regressions:
        regressions.sort(key=lambda x: x[3], reverse=True)
        print(f"  WORSE  ({len(regressions)} metrics):")
        for name, v1, v2, delta in regressions:
            v1s = f"${v1:.3f}" if name == "cost_usd" else str(int(v1))
            v2s = f"${v2:.3f}" if name == "cost_usd" else str(int(v2))
            sev = _PATTERN_META.get(name, ("?", ""))[0] if name in _PATTERN_META else ""
            sev_tag = f"[{sev}] " if sev else ""
            ds  = f"+${delta:.3f}" if name == "cost_usd" else f"+{int(delta)}"
            print(f"    {sev_tag}{name:<22} {v1s:>6} -> {v2s:<6}  ({ds})")
    if improvements:
        improvements.sort(key=lambda x: x[3], reverse=True)
        print(f"  BETTER ({len(improvements)} metrics):")
        for name, v1, v2, delta in improvements:
            v1s = f"${v1:.3f}" if name == "cost_usd" else str(int(v1))
            v2s = f"${v2:.3f}" if name == "cost_usd" else str(int(v2))
            ds  = f"-${delta:.3f}" if name == "cost_usd" else f"-{int(delta)}"
            print(f"    {name:<26} {v1s:>6} -> {v2s:<6}  ({ds})")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def collect_paths(args) -> list:
    paths = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.jsonl")))
        elif p.is_file():
            paths.append(p)
        else:
            print(f"Warning: {arg} not found", file=sys.stderr)
    return [str(p) for p in paths]


if __name__ == "__main__":
    raw_args = sys.argv[1:]
    if raw_args:
        paths = collect_paths(raw_args)
    else:
        paths = collect_paths([RUNS_DIR])

    if not paths:
        print(f"No .jsonl files found. Pass a directory or file path as argument.")
        sys.exit(1)

    groups = group_by_instance(paths)
    all_sessions = [analyze_one(p) for inst_paths in groups.values() for p in inst_paths]

    if len(groups) == 1 and len(list(groups.values())[0]) == 1:
        print_single(all_sessions[0])
    else:
        smt_repo = str(Path(__file__).parent.parent)
        # Global report first
        print_global_report(all_sessions)
        # Then per-instance detail
        for instance, inst_paths in sorted(groups.items()):
            inst_sessions = [s for s in all_sessions if s["stem"].startswith(instance)]
            inst_sessions.sort(key=lambda s: parse_ts(s["stem"]))
            print_comparison(instance, inst_sessions, repo=smt_repo)
