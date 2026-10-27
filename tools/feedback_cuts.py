"""Loop step: turn check_video 'said twice' flags on a DRAFT into extra source cuts for take_cuts.py.
Usage: python feedback_cuts.py <draft_check/report.json> <cuts.json> <extra_cuts.json>
Draft time -> source time through cuts.json "keep" ranges. Appends, so every pass adds to the list."""
import json, os, re, sys
rep, cuts, extra_path = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
OK = {"very", "really", "bye", "no", "yeah", "ha", "go", "to", "that", "had", "is"}


def to_src(t):
    acc = 0.0
    for s, e in cuts["keep"]:
        if t < acc + (e - s):
            return s + (t - acc)
        acc += e - s
    return None


extra = json.load(open(extra_path)) if os.path.exists(extra_path) else []
for f in rep["flags"]:
    m = re.match(r'said twice: "(.+)"', f["note"])
    if f["type"] == "words" and m and m[1].split()[0] not in OK:
        s, e = to_src(f["t"]), to_src(f["end"] - 0.4)  # first word start -> second take start
        if s is not None and e is not None and e > s:
            extra.append({"s": round(s, 3), "e": round(e, 3), "why": "checker: " + f["note"]})
json.dump(extra, open(extra_path, "w"), indent=1)
print(len(extra), "extra cuts")
