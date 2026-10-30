"""Teach the pipeline brain (Claude) to reason like the senior editor (2026-10-22).

Fine-tuning isn't possible, so it's taught the way a new editor is: a written playbook (teach/playbook.md) plus worked
examples of approved decisions (<kit>/my_style/examples/<task>/*.json, kept by every update; kits before v4 kept them in
teach/examples, copied over on first run), which claude_brain puts in front of every prompt
(newest examples first, examples_per_prompt in brain.json).

    python teach.py add <task> [--from <cache file>|latest] [--answer <json>] --title "..." --lesson "..."
        <task>: intro_director | intro_picture_check | draft_qc
        --from    the brain call to learn from (default: the newest cached call of that task): its exact prompt and
                  what the eyes saw become the example input
        --answer  the RIGHT answer when the brain's own one was corrected (a director.json, a report.json with Claude
                  verdicts, or the answer JSON itself); without it the brain's own answer is kept as approved
    python teach.py list [task]
    python teach.py compare <director.json A> <director.json B>      (line-by-line diff of two intro plans)
"""
import argparse
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_state", "claude_cache")
sys.path.insert(0, HERE)
import claude_brain  # noqa: E402
EX = claude_brain.EXAMPLES   # <kit>/my_style/examples: kept by every update
claude_brain.migrate_examples()


def latest(task):
    files = glob.glob(os.path.join(CACHE, f"{task}-*.json"))
    files = [f for f in files if json.load(open(f, encoding="utf-8")).get("prompt")]
    if not files:
        raise SystemExit(f"no cached {task} call with a saved prompt yet (run the pipeline once)")
    return max(files, key=os.path.getmtime)


def answer_from(path, task):
    d = json.load(open(path, encoding="utf-8"))
    if task == "intro_director" and "plan" in d:   # director.json -> the answer shape the prompt asks for
        lines = [dict({"i": int(i)}, **{k: v for k, v in p.items()}) for i, p in sorted(d["plan"].items(), key=lambda x: int(x[0]))]
        return {"lines": lines, "notes": d.get("notes", "")}
    if task == "draft_qc" and "flags" in d and any("claude" in f for f in d["flags"]):   # a reviewed report.json
        return {"flags": [{"n": n, "verdict": f["claude"]["verdict"], "why": f["claude"]["why"], "fix": f["claude"].get("fix", "")}
                          for n, f in enumerate(d["flags"]) if "claude" in f], "summary": d.get("claude_summary", "")}
    return d


def add(a):
    src = latest(a.task) if a.src in (None, "latest") else a.src
    c = json.load(open(src, encoding="utf-8"))
    inp = c["prompt"] + (f"\n\nWHAT THE ATTACHED IMAGE(S) SHOW (described cell by cell by your vision assistant):\n{c['seen']}" if c.get("seen") else "")
    out = answer_from(a.answer, a.task) if a.answer else json.loads(re.search(r"[\[{].*[\]}]", c["text"], re.S).group(0))
    os.makedirs(os.path.join(EX, a.task), exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (a.title or "example").lower()).strip("-")[:40]
    p = os.path.join(EX, a.task, f"{time.strftime('%Y%m%d-%H%M')}-{slug}.json")
    json.dump({"title": a.title, "lesson": a.lesson, "input": inp, "output": out, "from": os.path.basename(src),
               "corrected": bool(a.answer), "added": time.strftime("%Y-%m-%d %H:%M")}, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("example saved:", p)


def ls(a):
    for task in sorted(os.listdir(EX)) if os.path.isdir(EX) else []:
        if a.task and task != a.task:
            continue
        for f in sorted(glob.glob(os.path.join(EX, task, "*.json"))):
            d = json.load(open(f, encoding="utf-8"))
            print(f"{task:20} {d.get('added', ''):16} {'corrected' if d.get('corrected') else 'approved ':9} {d.get('title', '')}")


def compare(a):
    A, B_ = (json.load(open(p, encoding="utf-8"))["plan"] for p in (a.a, a.b))
    same = 0
    for i in sorted(set(A) | set(B_), key=int):
        x, y = A.get(i, {}), B_.get(i, {})
        kx = (x.get("show"), (x.get("clips") or [None])[0], x.get("query"))
        ky = (y.get("show"), (y.get("clips") or [None])[0], y.get("query"))
        same += kx == ky
        print(f"L{i}: {'=' if kx == ky else '≠'}  A {kx}  |  B {ky}")
    print(f"{same}/{len(set(A) | set(B_))} lines the same")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add")
    p.add_argument("task")
    p.add_argument("--from", dest="src")
    p.add_argument("--answer")
    p.add_argument("--title", default="")
    p.add_argument("--lesson", default="")
    p = sp.add_parser("list")
    p.add_argument("task", nargs="?")
    p = sp.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    a = ap.parse_args()
    {"add": add, "list": ls, "compare": compare}[a.cmd](a)
