"""Pull the Creator Studio Kit's anonymous edit stats from the Cloudflare collector into {{PROJECTS_ROOT}}\\_shared_edits.

  rows.jsonl   every row ever pulled (one JSON per line, newest last)
  SUMMARY.md   per video type: videos, kept ratio, how often people add cuts the AI missed / undo cuts it made, revisions,
               plus the custom types people build (what new official types to make next)
The read key stays on this PC only (_tools/.shared_edits_admin_key), never in the kit.

    python pull_edit_stats.py          pull new rows + rewrite SUMMARY.md
"""
import json
import os
import statistics
import urllib.request
from collections import defaultdict

URL = "https://creator-studio-edits.superstudiot.workers.dev"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "_shared_edits")
ROWS = os.path.join(OUT, "rows.jsonl")
STATE = os.path.join(OUT, "_last_id.txt")


def key():
    with open(os.path.join(HERE, ".shared_edits_admin_key"), encoding="utf-8") as f:
        return f.read().strip()


def pull():
    os.makedirs(OUT, exist_ok=True)
    after = int(open(STATE).read().strip()) if os.path.exists(STATE) else 0
    new = 0
    while True:
        req = urllib.request.Request(f"{URL}/v1/export?after={after}&limit=200",
                                     headers={"authorization": "Bearer " + key(), "user-agent": "studio-pull"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.loads(r.read().decode())["rows"]
        if not rows:
            break
        with open(ROWS, "a", encoding="utf-8") as f:
            for row in rows:
                body = json.loads(row.pop("body"))
                row["edit"] = body.get("edit", {})
                f.write(json.dumps(row) + "\n")
                after = row["id"]
                new += 1
        with open(STATE, "w") as f:
            f.write(str(after))
    return new


def summary():
    by = defaultdict(list)
    customs = []
    installs = set()
    if os.path.exists(ROWS):
        for line in open(ROWS, encoding="utf-8"):
            row = json.loads(line)
            e = row.get("edit", {})
            if e.get("v") != 1:
                continue
            installs.add(row["install_id"])
            by[e.get("type") or "?"].append(e)
            if e.get("custom_type"):
                customs.append(e["custom_type"])

    def med(xs):
        return round(statistics.median(xs), 2) if xs else "-"

    lines = [f"# Kit edit stats\n\n{sum(len(v) for v in by.values())} finished videos from {len(installs)} installs.\n",
             "| type | videos | kept (median) | AI missed a cut (videos / median s) | AI cut too much (videos / median s) | revisions (median) |",
             "|---|---|---|---|---|---|"]
    for t, es in sorted(by.items(), key=lambda kv: -len(kv[1])):
        missed = [e for e in es if e.get("ai_missed_cuts_s")]
        over = [e for e in es if e.get("ai_overcut_s")]
        lines.append(f"| {t} | {len(es)} | {med([e['kept_ratio'] for e in es if e.get('kept_ratio')])} | "
                     f"{len(missed)} / {med([x for e in missed for x in e['ai_missed_cuts_s']])} | "
                     f"{len(over)} / {med([x for e in over for x in e['ai_overcut_s']])} | {med([e.get('revisions', 0) for e in es])} |")
    if customs:
        lines += ["\n## Custom types people built\n", "```", *[json.dumps(c) for c in customs[-50:]], "```"]
    with open(os.path.join(OUT, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    n = pull()
    summary()
    print(f"pulled {n} new row(s) -> {OUT}")
