"""Mention cutaways for HyperFrames Minecraft edits.

When the voiceover mentions a feature ("raid dens", "gym leaders"), the edit cuts to a visual for it.
Each mention picks its visual in this order:
  1. footage  - a clip from the user's own recording   {"src": "footage/rec.mp4", "in": 123.4}
  2. images   - pictures grabbed online (official sources, credited)   [{"src": "assets/broll/x.png", "credit": "via CurseForge"}]
  3. placeholder - a block-texture panel labelled "GAMEPLAY GOES HERE"
Missing files fall through to the next option, so a project always builds.

Usage:
  python mentions.py suggest <transcript.json> [--vocab vocab.txt]   # find mentions in a transcript
  python mentions.py build <project_dir>                             # mentions.json -> index.html
"""
import json
import os
import re
import sys

DEFAULT_VOCAB = [
    "raid dens", "raid den", "trading systems", "trading", "gym leaders", "gym leader", "gyms",
    "legendaries", "legendary", "mega evolution", "shiny", "starter", "pokedex", "poke balls",
    "pokemon centre", "pokemon center", "battle tower", "elite four", "fishing", "breeding",
]
PALETTES = [["#e2b4ff", "#a85cff"], ["#a6ff8a", "#2fbf3a"], ["#ffe14a", "#ffb400"], ["#8fe8ff", "#1fa8e0"], ["#ffb0a0", "#ff4a2a"]]
TEXTURES = ["amethyst", "planks", "bricks", "stone", "dirt"]


def suggest(transcript_path, vocab_path=None):
    words = json.load(open(transcript_path, encoding="utf-8"))
    vocab = DEFAULT_VOCAB
    if vocab_path:
        vocab = [l.strip().lower() for l in open(vocab_path, encoding="utf-8") if l.strip()]
    norm = [re.sub(r"[^a-z0-9]", "", w["text"].lower()) for w in words]
    found, used = [], set()
    for phrase in sorted(vocab, key=lambda p: -len(p.split())):
        parts = [re.sub(r"[^a-z0-9]", "", p) for p in phrase.split()]
        for i in range(len(norm) - len(parts) + 1):
            if norm[i:i + len(parts)] == parts and not any(j in used for j in range(i, i + len(parts))):
                used.update(range(i, i + len(parts)))
                found.append({"phrase": phrase, "hit": round(words[i]["start"], 2), "end": round(words[i + len(parts) - 1]["end"], 2)})
    found.sort(key=lambda f: f["hit"])
    out = []
    for k, f in enumerate(found):
        nxt = found[k + 1]["hit"] if k + 1 < len(found) else f["end"] + 1.5
        out.append({
            "id": re.sub(r"[^a-z0-9]+", "-", f["phrase"]).strip("-"),
            "label": f["phrase"].upper(), "start": f["hit"], "end": round(nxt, 2), "hit": f["hit"],
            "colors": PALETTES[k % len(PALETTES)], "texture": TEXTURES[k % len(TEXTURES)], "check": True,
            "footage": None, "images": [],
        })
    print(json.dumps(out, indent=2))


def _exists(project, src):
    return src and os.path.exists(os.path.join(project, src))


def build(project):
    mentions = json.load(open(os.path.join(project, "mentions.json"), encoding="utf-8"))
    html, data = [], []
    for i, m in enumerate(mentions):
        mid, st, en = m["id"], float(m["start"]), float(m["end"])
        dur = round(en - st, 3)
        footage = m.get("footage")
        images = [im for im in (m.get("images") or []) if _exists(project, im.get("src"))]
        slides = []
        if footage and _exists(project, footage.get("src")):
            kind = "footage"
            html.append(
                f'        <video id="m-{mid}-v" class="clip layer fill ment" src="{footage["src"]}" muted playsinline '
                f'data-start="{st}" data-duration="{dur}" data-media-start="{footage.get("in", 0)}" data-track-index="1"></video>')
        elif images:
            kind = "images"
            n = len(images)
            for k, im in enumerate(images):
                s0 = round(st + dur * k / n, 3)
                d0 = round(dur / n, 3)
                sid = f"m-{mid}-{k}"
                slides.append({"id": sid, "start": s0, "dur": d0, "credit": im.get("credit", "")})
                html.append(
                    f'        <div id="{sid}" class="clip layer ment" data-start="{s0}" data-duration="{d0}" data-track-index="1">'
                    f'<img class="m-blur" src="{im["src"]}" alt="" /><img class="m-img" src="{im["src"]}" alt="{m["label"]}" /></div>')
        else:
            kind = "placeholder"
            html.append(
                f'        <div id="m-{mid}-p" class="clip layer ment" data-start="{st}" data-duration="{dur}" data-track-index="1">'
                f'<canvas class="slot-tex" data-tex="{m.get("texture", "stone")}" data-seed="{11 + i * 13}"></canvas></div>')
        chip = ""
        if kind == "placeholder":
            chip = f'<div class="chip">GAMEPLAY GOES HERE · {m["label"]}</div>'
        elif kind == "images":
            credits = sorted({s["credit"] for s in slides if s["credit"]})
            if credits:
                chip = f'<div class="credit">{" / ".join(credits)}</div>'
        html.append(
            f'        <div id="m-{mid}-ov" class="clip layer ment-ov" data-start="{st}" data-duration="{dur}" data-track-index="9">'
            f'<div class="slot-shade"></div>{chip}<div class="kw center" id="kw-{mid}"></div></div>')
        data.append({"id": mid, "label": m["label"], "colors": m.get("colors", PALETTES[i % 5]), "start": st, "end": en,
                     "hit": float(m.get("hit", st)), "check": bool(m.get("check", True)), "short": m.get("short", m["label"]),
                     "kind": kind, "slides": slides})
    path = os.path.join(project, "index.html")
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"(<!-- MENTIONS:START -->\n).*?(\s*<!-- MENTIONS:END -->)", lambda mm: mm.group(1) + "\n".join(html) + mm.group(2), s, flags=re.S)
    s = re.sub(r"(/\* MENTIONS:DATA \*/).*?(/\* MENTIONS:END \*/)",
               lambda mm: mm.group(1) + " const MENTIONS = " + json.dumps(data) + "; " + mm.group(2), s, flags=re.S)
    open(path, "w", encoding="utf-8").write(s)
    for d in data:
        print(f'{d["id"]:<16} {d["start"]:>6}-{d["end"]:<6} {d["kind"]}')


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "suggest":
        suggest(sys.argv[2], sys.argv[sys.argv.index("--vocab") + 1] if "--vocab" in sys.argv else None)
    elif sys.argv[1] == "build":
        build(sys.argv[2])
