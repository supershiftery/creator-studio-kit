"""Build the intro-style gallery page + STYLES.md from styles.json.
python make_gallery.py  ->  _styles/intro_styles.html  +  ../STYLES.md
"""
import json, html, pathlib

HERE = pathlib.Path(__file__).parent
D = json.loads((HERE / "styles.json").read_text(encoding="utf-8"))
ART_URL = (HERE / "artifact_url.txt").read_text().strip() if (HERE / "artifact_url.txt").exists() else ""

# ---------- STYLES.md (for the director / me) ----------
md = ["# Intro style catalog (80 styles, 20 per type)", "",
      "Built 2026-10-25. Rules: `INTRO_RULES.md`. Data: `_styles/styles.json`. Gallery with his verdicts: "
      + (ART_URL or "(artifact link in _styles/artifact_url.txt)"), "",
      "A style is an editorial DEVICE layered over the type's approved text layer. Tier: safe = built from approved "
      "patterns, fresh = new but inside the rules, bold = test render first.", ""]
for tkey, t in D["types"].items():
    md += [f"## {t['label']}", "", f"Text layer: {t['layer']}", ""]
    for s in [s for s in D["styles"] if s["type"] == tkey]:
        md += [f"### {s['id']} {s['name']} ({s['tier']})", s["idea"], "",
               f"- Fits: {', '.join(s['fits'])}",
               f"- Assets: {', '.join(D['assets'][a]['label'] + (' (new)' if D['assets'][a]['status'] == 'new' else '') for a in s.get('assets', []))}",
               f"- Beats: hook: {s['beats'][0]} | problem: {s['beats'][1]} | turn: {s['beats'][2]} | payoff: {s['beats'][3]}",
               f"- Signature: {s['signature']}", f"- Footage: {s['footage']}",
               f"- Motion: {s['motion']} Sound: {s['sound']}", f"- Guard: {s['guard']}", ""]
(HERE.parent / "STYLES.md").write_text("\n".join(md), encoding="utf-8")

# ---------- gallery page ----------
data = json.dumps(D, ensure_ascii=False).replace("</", "<\\/")
page = (HERE / "gallery_template.html").read_text(encoding="utf-8").replace("/*__DATA__*/null", data)
(HERE / "intro_styles.html").write_text(page, encoding="utf-8")
print("wrote", HERE / "intro_styles.html", "and STYLES.md")
