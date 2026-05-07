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

def classify_bash(cmd: str):
    cmd = cmd.strip()
    if cmd.startswith("smt "):
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "?"
        return f"smt:{sub}"
    for tool in ("grep", "sed", "find", "cat", "head", "tail", "awk", "findstr"):
        if cmd.startswith(tool) or f" {tool} " in cmd or f"|{tool}" in cmd or f"| {tool}" in cmd:
            return f"direct:{tool}"
    if cmd.startswith("git "):
        return "git"
    if cmd.startswith("python") or cmd.startswith("pip"):
        return "python"
    return "other"


def find_flag_errors(timeline):
    """Detect --compact/--brief used on commands that don't support them."""
    unsupported = {
        "search", "view", "list", "scope", "modules", "hot", "unused",
        "cycles", "bottleneck", "changes", "path", "status", "build", "sync", "grep",
    }
    bad = []
    for t in timeline:
        if t["name"] != "Bash":
            continue
        cmd = t["input"].get("command", "")
        m = re.match(r"smt\s+(\w+)", cmd)
        if not m:
            continue
        sub = m.group(1)
        if sub in unsupported and re.search(r"--compact|--brief|--span", cmd):
            bad.append(cmd.strip())
    return bad


def find_grep_flag_errors(timeline):
    """Detect smt grep called with --head_limit or --head (Exit code 2 unrecognized args)."""
    bad = []
    for t in timeline:
        if t["name"] != "Bash":
            continue
        cmd = t["input"].get("command", "").strip()
        if re.match(r"smt\s+grep\b", cmd) and re.search(r"--head(?:_limit)?", cmd):
            bad.append((cmd[:100], t["is_error"]))
    return bad


def find_scope_errors(timeline):
    """Detect smt scope called with errors."""
    bad = []
    for t in timeline:
        if t["name"] != "Bash" or not t["is_error"]:
            continue
        cmd = t["input"].get("command", "").strip()
        if cmd.startswith("smt scope"):
            bad.append((cmd, t["result"][:80]))
    return bad


def find_list_errors(timeline):
    """Detect smt list --module returning nothing despite graph having nodes."""
    bad = []
    for t in timeline:
        if t["name"] != "Bash":
            continue
        cmd = t["input"].get("command", "").strip()
        if cmd.startswith("smt list") and "No symbols found" in t["result"]:
            bad.append((cmd, t["result"][:80]))
    return bad


def find_lookup_regenerations(timeline):
    """Count times smt lookup triggered full embedding regeneration."""
    count = 0
    for t in timeline:
        if t["name"] == "Bash":
            cmd = t["input"].get("command", "").strip()
            if cmd.startswith("smt lookup") and "Generating embeddings" in t["result"]:
                count += 1
    return count


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
        flag_errors=find_flag_errors(timeline),
        grep_flag_errors=find_grep_flag_errors(timeline),
        scope_errors=find_scope_errors(timeline),
        list_errors=find_list_errors(timeline),
        regen_count=find_lookup_regenerations(timeline),
        pivot_turn=first_fallback_turn(timeline),
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

    # --- SMT-specific failures ---
    if s["grep_flag_errors"]:
        print(f"\nSMT GREP FLAG ERRORS  ({len(s['grep_flag_errors'])} calls)  [--head/--head_limit not supported; use --top]")
        for cmd, is_err in s["grep_flag_errors"]:
            status = "FAIL" if is_err else "ok"
            print(f"  [{status}] {cmd}")

    if s["flag_errors"]:
        print(f"\nINVALID FLAGS  ({len(s['flag_errors'])} calls)  [--compact/--brief on unsupported cmd]")
        for cmd in s["flag_errors"]:
            print(f"  {cmd[:90]}")

    if s["scope_errors"]:
        print(f"\nSMT SCOPE ERRORS  ({len(s['scope_errors'])} calls)")
        for cmd, res in s["scope_errors"]:
            print(f"  CMD: {cmd[:80]}")
            print(f"  ERR: {res[:60]}")

    if s["list_errors"]:
        print(f"\nSMT LIST EMPTY  ({len(s['list_errors'])} calls)")
        for cmd, _ in s["list_errors"]:
            print(f"  CMD: {cmd[:80]}")

    if s["regen_count"]:
        print(f"\nEMBEDDING REGENERATIONS: {s['regen_count']}  (smt build should pre-build FAISS index)")

    # --- Root causes ---
    causes = []
    if s["read_blocked"]:
        causes.append(f"[HIGH] {len(s['read_blocked'])} full-file Read blocks -> wasted turns waiting for hook denial")
    if s["grep_blocked"]:
        causes.append(f"[HIGH] {len(s['grep_blocked'])} Grep tool blocks -> hook forces smt grep; agent should use smt grep directly")
    if s["grep_flag_errors"]:
        causes.append(f"[HIGH] {len(s['grep_flag_errors'])} smt grep --head/--head_limit -> Exit code 2 -> agent falls back")
    if s["flag_errors"]:
        causes.append(f"[MED]  {len(s['flag_errors'])} --compact/--brief on unsupported commands")
    if s["scope_errors"]:
        causes.append(f"[MED]  {len(s['scope_errors'])} smt scope errors -> fallback to grep/sed")
    if s["list_errors"]:
        causes.append(f"[MED]  {len(s['list_errors'])} smt list --module returning empty")
    if s["regen_count"]:
        causes.append(f"[MED]  {s['regen_count']} embedding regeneration(s)")
    if not causes:
        causes.append("[NONE] No systematic failures detected")
    print(f"\nROOT CAUSES")
    for c in causes:
        print(f"  {c}")
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

        # New errors in s2 not seen in s1
        new_grep_flag = len(s2["grep_flag_errors"]) - len(s1["grep_flag_errors"])
        new_smt_err = s2["smt_err"] - s1["smt_err"]
        new_fallback = s2["fallback"] - s1["fallback"]
        new_read_blk = len(s2["read_blocked"]) - len(s1["read_blocked"])
        new_grep_blk = len(s2["grep_blocked"]) - len(s1["grep_blocked"])
        if verdict == "REGRESSED":
            print(f"\nREGRESSION CAUSES:")
            if new_grep_flag > 0:
                print(f"  [HIGH] +{new_grep_flag} smt grep --head/--head_limit errors (now fixed: added --head_limit alias)")
            if new_read_blk > 0:
                print(f"  [HIGH] +{new_read_blk} full-file Read blocks -> wasted turns")
            if new_grep_blk > 0:
                print(f"  [HIGH] +{new_grep_blk} Grep tool blocks -> agent should use smt grep directly")
            if new_smt_err > 0:
                print(f"  [MED]  +{new_smt_err} additional smt command errors")
            if new_fallback > 0:
                print(f"  [MED]  +{new_fallback} additional fallback bash calls")
            if len(set(tasks)) > 1:
                print(f"  [INFO] task prompt changed between runs -- broader task = more turns expected")
    print()

    # Individual session details
    for s in sessions:
        print_single(s)


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
    if len(groups) == 1 and len(list(groups.values())[0]) == 1:
        # Single file: just print the report
        print_single(analyze_one(paths[0]))
    else:
        # Multi-file: group by instance and compare
        smt_repo = str(Path(__file__).parent.parent)
        for instance, inst_paths in sorted(groups.items()):
            sessions = [analyze_one(p) for p in inst_paths]
            print_comparison(instance, sessions, repo=smt_repo)
