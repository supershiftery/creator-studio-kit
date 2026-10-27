"""Step 7: YouTube chapters from where each section sits in the finished edit.
python chapters.py <project> draft|final
Updates the project's description file in place: existing "m:ss #N ..." lines get the real times; a description
without chapter lines gets a Chapters block appended. Also writes Edit/studio/chapters.txt."""
import os
import re
import sys

from glib import Project, say

P = Project(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "draft")
tl = P.read(f"timeline-{P.mode}.json")
if not tl:
    sys.exit("assemble first")
st = {s["section"]: s["t_final"] for s in tl["sections"]}
fmt = lambda x: f"{int(x // 60)}:{int(x % 60):02d}"
lines = ["0:00 Intro"] if st.get("intro", 0) == 0 or tl["intro"] > 0 else []
first_hm = next((t for k, t in st.items() if k.startswith("HM")), None)
for name, t in st.items():
    if name == "intro":
        continue
    if name.startswith("HM"):
        continue
    clean = re.sub(r"\s*\(.*?\)", "", re.sub(r"^\?\s*", "", name)).strip()   # "? #5 (check start)" -> "#5"
    if not clean:
        continue
    label = re.sub(r"^#(\d+)\s*", r"#\1 ", clean).strip() if clean.startswith("#") else clean.capitalize()
    if name == "outro":
        label = "Outro"
    lines.append(f"{fmt(t)} {label}")
if first_hm is not None:
    lines.append(f"{fmt(first_hm)} Honorable mentions")
lines.sort(key=lambda l: (int(l.split()[0].split(":")[0]) * 60 + int(l.split()[0].split(":")[1])))
P.wf("chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
desc = P.doc.get("slots", {}).get("description") or str(P.path / "youtube-description.txt")
if os.path.exists(desc):
    txt = open(desc, encoding="utf-8").read()
    # the chapter block is REPLACED as a whole (Top 10 Servers 2026-10-22: re-timing only the lines already there kept
    # the first draft's broken list, 5 chapters ending "#2 Apparently", all the way to the final on Drive)
    rows = txt.split("\n")
    idx = [i for i, l in enumerate(rows) if re.match(r"\d+:\d\d\s", l.strip())]
    changed = 0
    if idx:
        rows[idx[0]:idx[-1] + 1] = lines
        txt2 = "\n".join(rows)
        changed = len(lines)
    else:
        txt2 = txt.rstrip("\n") + "\n\nChapters\n" + "\n".join(lines) + "\n"
    open(desc, "w", encoding="utf-8").write(txt2)
    say(f"description updated ({changed or 'chapters block added'}): {desc}")
else:
    (P.path / "youtube-description.txt").write_text("Chapters\n" + "\n".join(lines) + "\n", encoding="utf-8")
    say("no description yet: wrote youtube-description.txt with the chapters")
print("\n".join(lines))
