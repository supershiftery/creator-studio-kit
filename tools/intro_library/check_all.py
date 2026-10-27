"""Fast pre-flight: build each template on its demo VO (no render) and run `hyperframes check`; print errors only.
    python check_all.py [IDs...]"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_intro as B  # noqa: E402
from make_gallery import DEMO  # noqa: E402

ids = sys.argv[1:]
for t in B.templates():
    if ids and t["id"] not in ids:
        continue
    if t.get("external"):
        continue
    d = DEMO[t["type"]]
    out = os.path.join(HERE, "_work", "demo", f"{t['type']}-{t['id']}")
    try:
        B.build(t["type"], t["id"], d["vo"], d["title"], out, d["sub"], d["footage"], d["music"])
    except Exception as e:
        print(t["id"], "BUILD FAILED", e)
        continue
    r = subprocess.run(f"{B.HF} check", cwd=out, shell=True, capture_output=True, text=True, errors="replace")
    txt = r.stdout + r.stderr
    errs = [ln.strip() for ln in txt.splitlines() if re.search(r"✗ [a-z_]+:|Error|error:|TypeError|ReferenceError|SyntaxError|template error", ln)
            and "nth-of-type" not in ln and "0 errors" not in ln]
    print(t["id"], "OK" if not errs else "ISSUES:\n   " + "\n   ".join(errs[:8]))
