"""Extracts the agent runs for the website and the runs/ folder.

    python3 tools/extract_runs.py <codex_archive> <claude_archive>

Each archive is the agent's /workspace folder plus its session transcript (``transcript.jsonl``) as saved
after the run. Writes, per agent:
  runs/<run>/code/         the final code (Python files the agent wrote, without scratch experiments)
  runs/<run>/results/      final evaluation results and the agent's own RESULTS/REPORT documents
  runs/<run>/log.md        key conversation log (prompts, the agent's own narration, commands it ran)
  docs/data/run_<agent>.js iterations (results per environment, observations, change summary), log, code
  docs/data/diff_<agent>.js unified code diffs between consecutive snapshots
Standard library only.
"""

import datetime as dt
import difflib
import glob
import json
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENVS = [
    "LiftRedBox-v0", "RedBoxOnRack-v0", "RedBoxUnderRack-v0", "RedBoxUnderRack-v1", "RedBoxToBlueSpot-v0",
    "RedBoxToBlueSpot-v1", "PackRack-v0", "PackRack-v1", "PackRack-v2",
]
LOCAL_UTC_OFFSET = dt.timedelta(hours=-4)  # file mtimes on the host are EDT; transcripts are UTC


def mtime_utc(path):
    return (dt.datetime.fromtimestamp(os.path.getmtime(path)) - LOCAL_UTC_OFFSET).replace(tzinfo=dt.timezone.utc)


def parse_ts(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def env_of(name):
    name = name.split("/")[-1]
    return name if name in ENVS else None


def tally(records):
    out = {}
    for r in records:
        e = env_of(r.get("env") or r.get("env_id") or "")
        if e is None:
            continue
        s, n = out.get(e, (0, 0))
        out[e] = (s + bool(r.get("success")), n + 1)
    return {e: list(v) for e, v in out.items()}


def read_results(path):
    if path.endswith(".log"):
        recs = []
        for line in open(path):
            m = re.match(r"(OK|FAIL)\s+(\S+)", line)
            if m:
                recs.append({"env": m.group(2), "success": m.group(1) == "OK"})
        return recs
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in open(path) if l.strip()]
    data = json.load(open(path))
    return data if isinstance(data, list) else data.get("episodes", [])


# ---------------------------------------------------------------------------- transcripts


def claude_log(path):
    entries = []
    for line in open(path):
        d = json.loads(line)
        ts = d.get("timestamp")
        m = d.get("message")
        if not ts or not isinstance(m, dict):
            continue
        content = m.get("content")
        if d.get("type") == "user" and isinstance(content, str):
            text = re.sub(r"</?pasted_content[^>]*>", "", content).strip()
            if text and not text.startswith("[Image"):
                entries.append({"t": ts, "who": "user", "text": text})
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            if d.get("type") == "assistant" and b.get("type") == "text" and b["text"].strip():
                entries.append({"t": ts, "who": "agent", "text": b["text"].strip()})
            elif d.get("type") == "assistant" and b.get("type") == "tool_use":
                inp = b.get("input", {})
                cmd = inp.get("command") or inp.get("file_path") or json.dumps(inp)[:200]
                entries.append({"t": ts, "who": "tool", "tool": b.get("name"), "text": cmd})
            elif d.get("type") == "user" and b.get("type") == "text" and not b["text"].startswith(("<", "[Image")):
                entries.append({"t": ts, "who": "user", "text": b["text"]})
    return entries


CMD_RE = re.compile(r'cmd:"((?:[^"\\]|\\.)*)"')


def codex_log(path):
    entries = []
    for line in open(path):
        d = json.loads(line)
        ts, p = d.get("timestamp"), d.get("payload", {})
        if not ts:
            continue
        if p.get("type") == "message" and p.get("role") in ("user", "assistant"):
            text = "".join(c.get("text", "") for c in p.get("content", [])).strip()
            if not text or text.startswith("<"):
                continue
            entries.append({"t": ts, "who": "agent" if p["role"] == "assistant" else "user", "text": text})
        elif p.get("type") == "custom_tool_call":
            raw = p.get("input") or ""
            cmds = [bytes(c, "utf-8").decode("unicode_escape", "ignore") for c in CMD_RE.findall(raw)]
            if "apply_patch" in raw or p.get("name") == "apply_patch":
                files = re.findall(r"\*\*\* (?:Add|Update|Delete) File: (\S+)", raw)
                entries.append({"t": ts, "who": "tool", "tool": "edit", "text": "edit " + ", ".join(files or ["file"])})
            for c in cmds:
                entries.append({"t": ts, "who": "tool", "tool": "shell", "text": c})
    return entries


def narration_between(log, start, end):
    return [e["text"] for e in log if e["who"] == "agent" and start <= parse_ts(e["t"]) <= end]


# ---------------------------------------------------------------------------- code and diffs


def read_tree(root, patterns):
    files = {}
    for pat in patterns:
        for p in sorted(glob.glob(os.path.join(root, pat), recursive=True)):
            if "__pycache__" in p or not os.path.isfile(p):
                continue
            files[os.path.relpath(p, root)] = open(p, errors="replace").read()
    return files


def diff_trees(old, new):
    out, added, removed = [], 0, 0
    for path in sorted(set(old) | set(new)):
        a, b = old.get(path, "").splitlines(), new.get(path, "").splitlines()
        if a == b:
            continue
        lines = list(difflib.unified_diff(a, b, "a/" + path, "b/" + path, lineterm="", n=2))
        added += sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed += sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        out.append({"path": path, "diff": "\n".join(lines)})
    return out, added, removed


def write_md_log(log, path, title):
    with open(path, "w") as f:
        f.write(f"# {title}: key conversation log\n\nPrompts, the agent's own narration, and the commands it ran "
                "(command output omitted). Times are UTC.\n\n")
        for e in log:
            t = e["t"][11:19]
            if e["who"] == "user":
                f.write(f"\n### {t} · user\n\n{e['text']}\n\n")
            elif e["who"] == "agent":
                f.write(f"**{t} · agent:** {e['text']}\n\n")
            else:
                cmd = e["text"].strip().splitlines()[0][:200] if e["text"].strip() else ""
                f.write(f"- `{t}` {e.get('tool', 'tool')}: `{cmd}`\n")


# ---------------------------------------------------------------------------- agents


def claude(archive):
    ws = os.path.join(archive, "workspace")
    log = claude_log(os.path.join(archive, "transcript.jsonl"))
    res = os.path.join(ws, "results")
    report = open(os.path.join(ws, "REPORT.md")).read()
    rows = [r for r in report.splitlines() if re.match(r"\| \d+ \|", r)]
    described = {}
    for r in rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        described[int(cells[0])] = {"changed": cells[1], "seeds": cells[2], "reported": cells[3]}
    runs = [
        (1, "iter1_packrack.json", None), (2, "iter2_packrack.json", None), (3, "iter3_all.log", None),
        (4, "iter4_all.log", None), (5, "iter5_all.json", "iter5_all_solutions"),
        (6, "iter6_all.json", "iter6_all_solutions"), (7, "iter7_all.json", "iter7_all_solutions"),
        ("held-out", "heldout_all.json", "heldout_all_solutions"), (8, "iter8_all40.json", "iter8_all40_solutions"),
        (9, "iter9_all40.json", "iter9_all40_solutions"), (10, "final_iter10_all60.json", "final_iter10_all60_solutions"),
        (11, "final_iter11_bluespot60.json", "final_iter11_bluespot60_solutions"),
    ]
    start = parse_ts(log[0]["t"])
    iterations, diffs, prev_code, prev_time = [], [], None, start
    for n, fname, snap in runs:
        path = os.path.join(res, fname)
        when = mtime_utc(path)
        code = read_tree(os.path.join(res, snap), ["*.py"]) if snap else None
        diff, added, removed = ([], 0, 0)
        if code is not None and prev_code is not None:
            diff, added, removed = diff_trees(prev_code, code)
        info = described.get(n, {}) if isinstance(n, int) else {
            "changed": "No code change: the cycle-7 code on 20 seeds per environment it had never run.",
            "seeds": "20 held-out", "reported": ""}
        iterations.append({
            "n": n, "label": f"cycle {n}" if isinstance(n, int) else "held-out check", "time": when.isoformat(),
            "minutes": round((when - start).total_seconds() / 60), "results": tally(read_results(path)),
            "changed": info.get("changed", ""), "seeds": info.get("seeds", ""),
            "observed": narration_between(log, prev_time, when), "diff_index": len(diffs) if diff else None,
            "lines_added": added, "lines_removed": removed, "snapshot": bool(snap),
        })
        if diff:
            diffs.append(diff)
        if code is not None:
            prev_code = code
        prev_time = when
    code = read_tree(ws, ["solutions/*.py", "*.py"])
    return log, iterations, diffs, code


def codex(archive):
    ws = os.path.join(archive, "workspace")
    dev = os.path.join(ws, "development")
    log = codex_log(os.path.join(archive, "transcripts", "interactive_goal_session.jsonl"))
    start = parse_ts(log[0]["t"])
    evals = [p for p in glob.glob(os.path.join(dev, "*.jsonl")) if os.path.getsize(p) > 0]
    evals.append(os.path.join(ws, "results.jsonl"))
    evals = sorted(evals, key=os.path.getmtime)
    snaps = sorted(glob.glob(os.path.join(dev, "controllers_*.py")) + [os.path.join(ws, "controllers.py")],
                   key=os.path.getmtime)
    iterations, diffs, prev_code, prev_time = [], [], None, start
    used = set()
    for i, path in enumerate(evals, 1):
        when = mtime_utc(path)
        snap = [s for s in snaps if os.path.getmtime(s) <= os.path.getmtime(path) and s not in used]
        code, diff, added, removed = None, [], 0, 0
        if snap:
            latest = snap[-1]
            used.update(snap)
            code = {"controllers.py": open(latest).read()}
            if os.path.exists(os.path.join(ws, "tool_control.py")) and latest.endswith("workspace/controllers.py"):
                code["tool_control.py"] = open(os.path.join(ws, "tool_control.py")).read()
            if prev_code is not None:
                diff, added, removed = diff_trees(prev_code, code)
        recs = read_results(path)
        iterations.append({
            "n": i, "label": os.path.basename(path).replace(".jsonl", ""), "time": when.isoformat(),
            "minutes": round((when - start).total_seconds() / 60), "results": tally(recs),
            "changed": f"code snapshot {os.path.basename(snap[-1])}" if snap else "same code as the previous run",
            "seeds": f"{len(recs)} episodes", "observed": narration_between(log, prev_time, when),
            "diff_index": len(diffs) if diff else None, "lines_added": added, "lines_removed": removed,
            "snapshot": bool(snap),
        })
        if diff:
            diffs.append(diff)
        if code is not None:
            prev_code = code
        prev_time = when
    code = read_tree(ws, ["solutions/*.py", "*.py"])
    return log, iterations, diffs, code


def export(agent, run_dir, archive, log, iterations, diffs, code, title):
    os.makedirs(os.path.join(REPO, "docs", "data"), exist_ok=True)
    dest = os.path.join(REPO, "runs", run_dir)
    if os.path.exists(os.path.join(dest, "code")):
        shutil.rmtree(os.path.join(dest, "code"))
    for rel, text in code.items():
        p = os.path.join(dest, "code", rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    os.makedirs(os.path.join(dest, "results"), exist_ok=True)
    ws = os.path.join(archive, "workspace")
    for name in ("RESULTS.md", "REPORT.md", "NOTES.md", "STATUS.md", "results.jsonl", "results.jsonl.summary.json",
                 "failure_analysis.json", "results/final.json", "results/scene_seeds.json", "results/videos.json"):
        if os.path.exists(os.path.join(ws, name)):
            shutil.copy(os.path.join(ws, name), os.path.join(dest, "results", os.path.basename(name)))
    write_md_log(log, os.path.join(dest, "log.md"), title)
    with open(os.path.join(REPO, "docs", "data", f"run_{agent}.js"), "w") as f:
        f.write(f"window.RUNS = window.RUNS || {{}}; window.RUNS[{json.dumps(agent)}] = ")
        json.dump({"iterations": iterations, "log": log, "code": code}, f, separators=(",", ":"))
        f.write(";\n")
    with open(os.path.join(REPO, "docs", "data", f"diff_{agent}.js"), "w") as f:
        f.write(f"window.DIFFS = window.DIFFS || {{}}; window.DIFFS[{json.dumps(agent)}] = ")
        json.dump(diffs, f, separators=(",", ":"))
        f.write(";\n")
    n_agent = sum(e["who"] == "agent" for e in log)
    n_tool = sum(e["who"] == "tool" for e in log)
    print(f"{agent}: {len(iterations)} iterations, {len(diffs)} diffs, {len(code)} code files, "
          f"log {n_agent} narration / {n_tool} commands")


if __name__ == "__main__":
    codex_archive, claude_archive = sys.argv[1], sys.argv[2]
    export("codex", "codex-gpt6-astra", codex_archive, *codex(codex_archive), "Codex (GPT-6-Astra, medium)")
    export("claude", "claude-opus-5.5", claude_archive, *claude(claude_archive), "Claude Code (Opus 5.5, medium)")
