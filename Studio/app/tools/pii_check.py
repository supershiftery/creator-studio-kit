"""Last privacy check on a screen-recording edit, before "Draft ready" (user 2026-10-23: cut first, then privacy; a scan of
the finished draft is the safety net). Scans the whole edit at 2 fps with pii_scan's patterns; text the blur already
covers can't be read, so any hit is something still readable.

    python pii_check.py <project>

A hit FAILS the step (the build stops before "Draft ready") and is added, in recording time, to Edit/studio/pii.json, so
the next build blurs it. A false alarm (a long number that isn't private) can be waved through for this project with
settings.privacy_ok = ["<masked text as printed>", ...]."""
import json
import subprocess
import sys
from pathlib import Path

proj = Path(sys.argv[1])
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
work = proj / "Edit" / "studio"
tl = json.loads((work / "timeline-trim.json").read_text(encoding="utf-8"))
out = Path(tl["out"])
scan = work / "pii_check.json"
here = Path(__file__).resolve().parent
r = subprocess.run([sys.executable, "-X", "utf8", str(here / "pii_scan.py"), str(out), str(scan), "--fps", "2"])
if r.returncode:
    sys.exit(r.returncode)
ok = set((doc.get("settings") or {}).get("privacy_ok") or [])
hits = [h for h in json.loads(scan.read_text(encoding="utf-8"))["hits"] if h["masked"] not in ok]
if not hits:
    print("privacy check: nothing readable in the edit")
    sys.exit(0)
keep, speed = tl["keep"], float(tl.get("speed") or 1.0)


def to_raw(t):
    t *= speed
    for s, e in keep:
        if t <= e - s:
            return s + t
        t -= e - s
    return keep[-1][1]


pj = work / "pii.json"
d = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else {"hits": []}
d["hits"] += [dict(h, t=round(to_raw(h["t"]), 2), from_check=True) for h in hits]
pj.write_text(json.dumps(d), encoding="utf-8")
for h in hits[:20]:
    print(f"!! still readable at {h['t'] // 60:.0f}:{h['t'] % 60:04.1f}: {h['kind']} {h['masked']}")
print(f"privacy check FAILED: {len(hits)} readable spot(s). They are added to the blur list: build again and they get blurred "
      f"(a false alarm can be allowed with settings.privacy_ok).")
sys.exit(1)
