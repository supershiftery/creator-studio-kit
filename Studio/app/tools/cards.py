"""Render realm/server code cards for a gaming project's sections.  python cards.py <project>
Reads studio.json settings.cards_codes {section name: code}, builds each card with the HyperFrames realm-code-card
project (typed code, Join click, lower third), renders a transparent MOV into <project>\\Graphics\\cards\\ and points
settings.cards[section] at it so assemble.py overlays it at the section start."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

proj = Path(sys.argv[1])
CARD = Path(r"{{KIT}}/assets\Graphics\HyperFrames\realm-code-card")
HF = "npx --yes hyperframes@0.8.180"
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
codes = {k: v.strip() for k, v in (doc.get("settings", {}).get("cards_codes") or {}).items() if v and v.strip()}
if not codes:
    sys.exit("no codes set (Sections tab → Code column)")
out_dir = proj / "Graphics" / "cards"
out_dir.mkdir(parents=True, exist_ok=True)
picks, hm = [], []
for name, code in codes.items():
    m = re.match(r"^\??\s*#(\d+)\s*(.*)", name)
    clean = re.sub(r"\s*\(.*?\)", "", name).strip()
    if m:
        picks.append({"rank": int(m.group(1)), "name": (m.group(2) or clean).strip(" ?") or clean, "code": code, "section": name})
    else:
        hm.append({"rank": 91 + len(hm), "name": re.sub(r"^HM\s*", "", clean) or clean, "code": code, "mention": True, "section": name})
pf = out_dir / "_picks.json"
pf.write_text(json.dumps(picks + hm, ensure_ascii=False, indent=1), encoding="utf-8")
cards = dict(doc.get("settings", {}).get("cards") or {})
for e in picks + hm:
    slug = re.sub(r"[^a-z0-9]+", "-", e["name"].lower()).strip("-") or "card"
    tag = f"hm{e['rank'] - 90}" if e.get("mention") else f"{e['rank']:02d}"
    mov = out_dir / f"code-card-{tag}-{slug}.mov"
    print(f"card {e['section']}: {e['name']} / {e['code']}", flush=True)
    r = subprocess.run([sys.executable, "-X", "utf8", str(CARD / "build.py"), str(e["rank"]), "--transparent", "--picks", str(pf)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(CARD))
    print("  " + (r.stdout or r.stderr).strip()[-300:], flush=True)
    if r.returncode:
        sys.exit("build.py failed")
    r = subprocess.run(f'{HF} render --quiet --format mov -o "{mov}"', shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(CARD))
    if r.returncode or not mov.exists():
        print((r.stdout + r.stderr)[-800:])
        sys.exit("hyperframes render failed")
    cards[e["section"]] = str(mov)
    print(f"  -> {mov.name}", flush=True)
doc.setdefault("settings", {})["cards"] = cards
(proj / "studio.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{len(picks) + len(hm)} cards rendered; rebuild the draft to overlay them")
