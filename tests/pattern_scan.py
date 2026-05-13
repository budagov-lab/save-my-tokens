
"""One-shot: enumerate every failure pattern across all 12 sessions."""
import json, glob, re
from pathlib import Path
from collections import defaultdict

def load(f):
    return [json.loads(l) for l in open(f, encoding="utf-8")]

def get_timeline(events):
    tool_map, result_map = {}, {}
    for e in events:
        if e.get("type") == "assistant":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "tool_use":
                    tool_map[m["id"]] = (m.get("name", ""), m.get("input", {}))
        elif e.get("type") == "user":
            for m in e.get("message", {}).get("content", []):
                if isinstance(m, dict) and m.get("type") == "tool_result":
                    tid = m.get("tool_use_id", "")
                    c = m.get("content", "")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    explicit = m.get("is_error")
                    if explicit is True:
                        err = True
                    elif explicit is False:
                        err = False
                    else:
                        err = str(c).startswith("Exit code") and "Exit code 0" not in str(c)
                    result_map[tid] = (str(c), err)
    tl = []
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
            result, err = result_map.get(tid, ("", False))
            tl.append({"turn": turn, "name": name, "input": inp, "result": result, "is_error": err})
    return tl

files = sorted(glob.glob("C:/Users/LENOVO/Desktop/Projects/bench/SWE_Context_lite/runs/*.jsonl"))
patterns = defaultdict(list)

for f in files:
    stem = Path(f).stem
    m = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})$", stem)
    ts = f"{m.group(2)}:{m.group(3)}" if m else stem
    inst = stem.split("__smt__")[0].replace("psf__requests-", "")
    sess = f"{inst}@{ts}"
    evts = load(f)
    tl = get_timeline(evts)

    for t in tl:
        name = t["name"]
        inp = t["input"]
        result = t["result"]
        err = t["is_error"]

        if name == "Bash":
            cmd = inp.get("command", "").strip()

            if err and "not found in graph" in result and re.match(r"smt (definition|view|lookup)", cmd):
                sym = re.search(r"smt (?:definition|view|lookup)\s+\"?([^\s\"]+)", cmd)
                s = sym.group(1) if sym else "?"
                patterns["P01: symbol_not_found_in_graph"].append((sess, s, ""))

            if err and re.search(r"smt view.*--depth", cmd):
                patterns["P02: smt_view_with_depth_flag"].append((sess, cmd[:80], ""))

            grep_part = re.split(r"\s+&&\s+|\s+\|\s+", cmd)[0]
            if err and re.match(r"smt grep", cmd) and re.search(r"--compact|--head(?:_limit)?", grep_part):
                patterns["P03: smt_grep_wrong_flag"].append((sess, cmd[:80], ""))

            if err and re.search(r"smt (impact|grep)\b.*--file", cmd):
                patterns["P04: unsupported_file_flag_on_impact_grep"].append((sess, cmd[:80], ""))

            if err and "Multiple symbols" in result:
                patterns["P05: multiple_symbols_ambiguity"].append((sess, cmd[:80], ""))

            if err and re.match(r"cd\s+", cmd) and ("No such file" in result or "bash: line" in result):
                patterns["P06: cd_to_bad_path"].append((sess, cmd[:80], ""))

            if err and re.search(r"(grep|find|cat|head)\b.*[A-Z]:\\\\", cmd):
                patterns["P07: win_backslash_path_in_bash"].append((sess, cmd[:80], ""))

            if err and re.search(r"findstr|Get-Content|Select-String", cmd):
                patterns["P08: windows_cmd_tools_in_bash"].append((sess, cmd[:80], ""))

            if err and "smt scope" in cmd and "Multiple files match" in result:
                patterns["P09: smt_scope_ambiguous_filename"].append((sess, cmd[:80], ""))

            if err and "python-dotenv could not parse" in result:
                patterns["P10: dotenv_parse_error"].append((sess, cmd[:80], ""))

            if err and "File not found" in result and "smt view" in cmd:
                patterns["P11: smt_view_source_file_missing"].append((sess, cmd[:80], result[:80]))

            if err and "pytest" in cmd and "ImportError" in result:
                patterns["P12: pytest_broken_in_benchmark"].append((sess, cmd[:80], ""))

            if err and "/mnt/c/" in cmd:
                patterns["P13: wsl_path_on_windows"].append((sess, cmd[:80], ""))

            if not err and "|" in cmd and re.match(r"smt\s+", cmd):
                if re.search(r"--output_mode", cmd):
                    patterns["P14: pipe_masks_smt_flag_error"].append((sess, cmd[:80], ""))

            if err and "smt grep" in cmd and re.search(r'--output_mode', cmd):
                patterns["P14b: smt_grep_output_mode_flag"].append((sess, cmd[:80], ""))

        elif name == "Read":
            fp = inp.get("file_path", "")
            offset = inp.get("offset", None)
            fname = Path(fp).name if fp else "?"

            if err and "EISDIR" in result:
                patterns["P15: read_directory_eisdir"].append((sess, fp[-60:], ""))

            if err and "Full-file read blocked" in result:
                if offset == "" or offset == 0:
                    patterns["P16: read_blocked_empty_string_offset"].append(
                        (sess, fname, f"offset={repr(offset)}")
                    )
                else:
                    patterns["P17: read_blocked_no_offset"].append((sess, fname, ""))

        elif name == "Grep":
            if err and "Grep blocked" in result:
                patterns["P18: grep_tool_blocked_by_hook"].append(
                    (sess, inp.get("pattern", "")[:60], "")
                )

for key in sorted(patterns.keys()):
    items = patterns[key]
    print(f"\n[{key}]  count={len(items)}")
    for sess, desc, note in items[:5]:
        print(f"  [{sess}]  {desc}")
        if note:
            print(f"           note: {note}")
    if len(items) > 5:
        print(f"  ... +{len(items)-5} more")
