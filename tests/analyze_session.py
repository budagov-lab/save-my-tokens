#!/usr/bin/env python3
"""Analyze SMT session logs (.jsonl) for failure patterns and improvement insights."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_events(path: str):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def extract_timeline(events):
    """Return ordered list of (turn, role, tool_name, input, result, is_error)."""
    tool_map = {}  # id -> (name, input)
    result_map = {}  # id -> (content, is_error)

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
                    is_error = str(content).startswith("Exit code") and "Exit code 0" not in str(content)
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


def classify_bash(cmd: str):
    """Return category tag for a bash command."""
    cmd = cmd.strip()
    if cmd.startswith("smt "):
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "?"
        return f"smt:{sub}"
    for tool in ("grep", "sed", "find", "cat", "head", "tail", "awk"):
        if cmd.startswith(tool) or f" {tool} " in cmd or f"|{tool}" in cmd or f"| {tool}" in cmd:
            return f"direct:{tool}"
    if cmd.startswith("git "):
        return "git"
    if cmd.startswith("python") or cmd.startswith("pip"):
        return "python"
    return "other"


def find_flag_errors(timeline):
    """Detect --compact/--brief used on commands that don't support them."""
    bad = []
    unsupported = {"search", "view", "list", "scope", "modules", "hot", "unused",
                   "cycles", "bottleneck", "changes", "path", "status", "build", "sync"}
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


def find_scope_errors(timeline):
    """Detect smt scope called with dot-notation or missing extension."""
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


def compute_smt_vs_fallback(timeline):
    bash = [t for t in timeline if t["name"] == "Bash"]
    smt = [t for t in bash if t["input"].get("command", "").strip().startswith("smt ")]
    fallback = [t for t in bash if not t["input"].get("command", "").strip().startswith("smt ")]
    smt_ok = [t for t in smt if not t["is_error"]]
    smt_err = [t for t in smt if t["is_error"]]
    return bash, smt_ok, smt_err, fallback


def first_fallback_turn(timeline):
    """Turn number where first non-smt bash command appears."""
    for t in timeline:
        if t["name"] == "Bash" and not t["input"].get("command", "").strip().startswith("smt "):
            return t["turn"]
    return None


def find_search_regenerations(timeline):
    """Count times smt search triggered full embedding regeneration."""
    count = 0
    for t in timeline:
        if t["name"] == "Bash" and t["input"].get("command", "").strip().startswith("smt search"):
            if "Generating embeddings" in t["result"]:
                count += 1
    return count


def optimal_smt_path(task_hint: str = ""):
    """Suggest the optimal SMT lookup sequence for common patterns."""
    return [
        "smt scope <filename.py>      -> see all imports/exports at a glance",
        "smt context <symbol> --depth 2 --compact  -> understand call context",
        "smt definition <symbol> --compact --brief -> quick signature lookup",
    ]


def print_report(path: str):
    events = load_events(path)
    timeline = extract_timeline(events)

    bash, smt_ok, smt_err, fallback = compute_smt_vs_fallback(timeline)
    flag_errors = find_flag_errors(timeline)
    scope_errors = find_scope_errors(timeline)
    list_errors = find_list_errors(timeline)
    regen_count = find_search_regenerations(timeline)
    pivot_turn = first_fallback_turn(timeline)

    result_event = next((e for e in events if e.get("type") == "result"), None)
    outcome = result_event.get("subtype", "?") if result_event else "?"

    label = Path(path).stem
    print(f"{'='*70}")
    print(f"SESSION: {label}")
    print(f"OUTCOME: {outcome}")
    print(f"{'='*70}")
    print()

    # --- Call distribution ---
    print(f"CALL DISTRIBUTION  (total bash: {len(bash)})")
    print(f"  smt success   : {len(smt_ok):3d}  ({100*len(smt_ok)//max(len(bash),1):2d}%)")
    print(f"  smt errors    : {len(smt_err):3d}  ({100*len(smt_err)//max(len(bash),1):2d}%)")
    print(f"  fallback calls: {len(fallback):3d}  ({100*len(fallback)//max(len(bash),1):2d}%)")
    if pivot_turn:
        print(f"  agent pivoted to grep/sed at turn {pivot_turn}")
    print()

    # --- Failure breakdown ---
    if flag_errors:
        print(f"INVALID FLAGS  ({len(flag_errors)} calls)  [--compact/--brief on unsupported cmd]")
        for cmd in flag_errors:
            print(f"  {cmd[:90]}")
        print()

    if scope_errors:
        print(f"SMT SCOPE ERRORS  ({len(scope_errors)} calls)  [dot-notation or missing extension]")
        for cmd, res in scope_errors:
            print(f"  CMD: {cmd[:80]}")
            print(f"  ERR: {res[:60]}")
        print()

    if list_errors:
        print(f"SMT LIST EMPTY  ({len(list_errors)} calls)  [module path not matching stored paths]")
        for cmd, res in list_errors:
            print(f"  CMD: {cmd[:80]}")
        print()

    if regen_count:
        print(f"EMBEDDING REGENERATIONS: {regen_count}  (expected 0 after smt build pre-builds index)")
        print()

    # --- Fallback analysis ---
    if fallback:
        cats = Counter(classify_bash(t["input"].get("command", "")) for t in fallback)
        print(f"FALLBACK TOOL BREAKDOWN  ({len(fallback)} calls)")
        for cat, cnt in cats.most_common():
            print(f"  {cnt:3d}  {cat}")
        print()

    # --- What the optimal path would have been ---
    print("OPTIMAL SMT PATH FOR THIS TASK")
    print("  (exception handling analysis - find unwrapped imports)")
    for step in [
        "1. smt scope adapters.py          -> see all urllib3 imports and exports at a glance",
        "2. smt context HTTPAdapter.send --depth 2 --compact  -> exception handling context",
        "3. smt scope exceptions.py        -> confirm ContentDecodingError wraps DecodeError",
        "   Done in 3 turns instead of 41",
    ]:
        print(f"  {step}")
    print()

    # --- Root causes ---
    print("ROOT CAUSES (ranked by impact)")
    causes = []
    if flag_errors:
        causes.append(f"[HIGH] {len(flag_errors)} wasted turns: --compact/--brief on smt search/view")
    if scope_errors:
        causes.append(f"[HIGH] {len(scope_errors)} wasted turns: smt scope wrong syntax -> agent abandoned SMT at turn {pivot_turn}")
    if list_errors:
        causes.append(f"[MED]  {len(list_errors)} empty results: smt list --module path separator mismatch")
    if regen_count:
        causes.append(f"[MED]  {regen_count} embedding regeneration(s): FAISS index not pre-built by smt build")
    if not causes:
        causes.append("[NONE] No systematic failures detected")
    for c in causes:
        print(f"  {c}")
    print()

    # --- Fixes status ---
    print("FIX STATUS")
    print("  [DONE] --compact/--brief on search/view: SKILL.md updated with explicit warning")
    print("  [DONE] smt scope: slash normalization + extension fallback (navigation.py)")
    print("  [DONE] smt list --module: slash normalization fix applied (navigation.py)")
    print("  [DONE] embedding regeneration: smt build now pre-builds FAISS index (build.py)")
    print()


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(
        Path("tests/fixtures").glob("*.jsonl")
    )
    for p in paths:
        print_report(str(p))
