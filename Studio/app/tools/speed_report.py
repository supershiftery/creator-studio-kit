"""Revision speed report (2026-10-24 speed pass): for every revision batch, how many builds it ran, the minutes waited in
the render line, each build's step times and the whole batch from "notes sent" to its last build, so each speedup can be
read off real batches instead of guessed. Reads studio.json (builds) + studio-chat.json (run) of every project.
    python speed_report.py [--since "2026-10-24 13:54"] [--md out.md]"""
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS = HERE.parent.parent / "data" / "projects.json"


def ts(s):
    try:
        return datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def main():
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "2026-10-24 13:54"
    rows = []
    for p in json.loads(PROJECTS.read_text(encoding="utf-8")):
        folder = Path(p.get("path") or "")
        sj, cj = folder / "studio.json", folder / "studio-chat.json"
        if not sj.exists():
            continue
        doc = json.loads(sj.read_text(encoding="utf-8-sig"))
        run = (json.loads(cj.read_text(encoding="utf-8")).get("run") or {}) if cj.exists() else {}
        builds = [b for b in doc.get("builds", []) if b.get("when", "") >= since and b.get("action") in ("draft", "revise", "intro", "all")]
        if not builds:
            continue
        in_run = [b for b in builds if run.get("started") and b.get("when", "") >= run["started"]]
        start, end = ts(run.get("started")), ts(builds[-1].get("when"))
        rows.append({"title": doc.get("title"), "type": doc.get("type"), "run": run.get("state"), "notes": len(run.get("nids", [])),
                     "batch_min": round((end - start).total_seconds() / 60) if start and end and in_run else None,
                     "builds": [{"when": b["when"], "action": b["action"], "status": b.get("status"), "min": round((b.get("secs") or 0) / 60, 1),
                                 "waited": round((b.get("waited") or 0) / 60, 1),
                                 "steps": {s["id"]: round((s.get("secs") or 0) / 60, 1) for s in b.get("steps", [])}} for b in builds],
                     "in_run": len(in_run)})
    out = [f"# Revision speed since {since}", ""]
    for r in sorted(rows, key=lambda r: r["builds"][-1]["when"]):
        out.append(f"## {r['title']} ({r['type']}): {len(r['builds'])} build(s)"
                   + (f", batch of {r['notes']} notes: {r['in_run']} build(s) in the batch, {r['batch_min']} min from sent to last build"
                      f" (run {r['run']})" if r["notes"] else ""))
        for b in r["builds"]:
            steps = ", ".join(f"{k} {v}" for k, v in b["steps"].items())
            out.append(f"- {b['when']} {b['action']} {b['status']}: {b['min']} min built, {b['waited']} min in line | {steps}")
        out.append("")
    text = "\n".join(out)
    print(text)
    if "--md" in sys.argv:
        Path(sys.argv[sys.argv.index("--md") + 1]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
