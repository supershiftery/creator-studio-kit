"""His intro text fixes (Studio Editor / Watch, 2026-10-29: "double-click the intro text, type it in, and it changes it").

A fix is {old, new}: every place the intro shows `old` (its spoken words, the line's key word, the title, the graphics'
labels) shows `new`. Fixes apply in order over the intro's UNFIXED data (<build>/intro_data.json, written by build_intro
before any fix), so a later fix or an undo always starts from the build itself.

retext(build, fixes) = the fast path: patch window.INTRO in <build>/index.html and render only (~4-5 min at 60 fps); no new AI plan,
the same shots. The word list keeps its length (each line points into it by index, kit.js K.lineWords), so a phrase with
a different word count is spread over the old words' slots and timings."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTRO_RE = re.compile(r"(<script>window\.INTRO = )(.*?)(;</script>)", re.S)
SKIP = {"words", "slots", "beats", "cam", "flashes", "seed", "dur", "accent", "template", "type", "scenes", "auto_pins", "pins"}


def norm(s):
    return re.sub(r"[^a-z0-9$%]+", " ", str(s).lower()).strip()


def _case(src, new):
    """the new text in the old one's case: SAD -> NEW, Sad -> New, sad -> new as typed"""
    if len(src) > 1 and src.isupper():
        return new.upper()
    if src[:1].isupper() and new[:1].islower():
        return new[:1].upper() + new[1:]
    return new


def _sub(s, old, new):
    if not isinstance(s, str) or not old:
        return s, 0
    if "/" in s or "\\" in s or re.search(r"\.(png|jpe?g|webp|mp4|mov|mp3|wav|svg|ttf)$", s, re.I):   # a file, not text
        return s, 0
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])", re.I)
    return pat.subn(lambda m: _case(m.group(0), new), s)


def _deep(x, old, new):
    """every text string in the intro data except the word list, file paths and timing"""
    n = 0
    if isinstance(x, dict):
        for k, v in list(x.items()):
            if k in SKIP or k in ("src", "file", "path", "url", "img", "logo", "icon"):
                continue
            if isinstance(v, str):
                x[k], c = _sub(v, old, new)
            else:
                c = _deep(v, old, new)
            n += c
    elif isinstance(x, list):
        for i, v in enumerate(x):
            if isinstance(v, str):
                x[i], c = _sub(v, old, new)
            else:
                c = _deep(v, old, new)
            n += c
    return n


def _words(W, old, new):
    """the spoken-word list: each run of words that reads `old` gets `new`, same number of words, same timings"""
    toks, nt = [norm(t) for t in old.split()], new.split()
    if not toks or not all(toks) or not W:
        return 0
    n, i = 0, 0
    while i + len(toks) <= len(W):
        seq = W[i:i + len(toks)]
        if [norm(w.get("w", "")) for w in seq] != toks:
            i += 1
            continue
        k = len(seq)
        parts = nt[:k - 1] + [" ".join(nt[k - 1:])] if len(nt) >= k else nt + [""] * (k - len(nt))
        for w, p in zip(seq, parts):
            raw = w.get("w", "")
            lead, trail = re.match(r"^\W*", raw).group(0), re.search(r"\W*$", raw).group(0)
            w["w"] = (lead + _case(raw.strip(".,!?;:'\"()"), p) + trail) if p else ""
        n += 1
        i += k
    return n


def apply(I, fixes):
    """I (window.INTRO) with his fixes applied in order; returns (new I, [(fix id, places changed)])"""
    I = json.loads(json.dumps(I))
    hits = []
    for f in fixes or []:
        old, new = str(f.get("old") or "").strip(), str(f.get("new") or "").strip()
        if not old or not new or old == new:
            continue
        c = _words(I.get("words") or [], old, new) + _deep(I, old, new)
        hits.append((f.get("id"), c))
    return I, hits


def read_intro(build):
    """the intro data as it is on screen now (window.INTRO in index.html), or None"""
    f = Path(build) / "index.html"
    if not f.exists():
        return None
    m = INTRO_RE.search(f.read_text(encoding="utf-8"))
    return json.loads(m.group(2)) if m else None


def _dump(I):
    return json.dumps(I).replace("</", "<\\/")   # his text can't close the script tag


def write_html(build, I):
    f = Path(build) / "index.html"
    txt = f.read_text(encoding="utf-8")
    m = INTRO_RE.search(txt)
    if not m:
        raise RuntimeError("index.html has no window.INTRO")
    f.write_text(txt[:m.start(2)] + _dump(I) + txt[m.end(2):], encoding="utf-8")


def saved_fixes(build):
    try:
        return json.loads((Path(build) / "text_fixes.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def same(a, b):
    key = lambda fx: [(f.get("old"), f.get("new")) for f in fx or []]   # noqa: E731
    return key(a) == key(b)


def retext(build, fixes, say=print, py=sys.executable):
    """patch the built intro's text and render it again (no new plan). The last good render stays if the render fails."""
    build = Path(build)
    orig = build / "intro_data.json"
    if not orig.exists():   # an intro built before this file existed: what is on screen now IS the unfixed build
        cur = read_intro(build)
        if cur is None:
            raise RuntimeError("no built intro to change")
        orig.write_text(json.dumps(cur), encoding="utf-8")
    I, hits = apply(json.loads(orig.read_text(encoding="utf-8")), fixes)
    for fid, c in hits:
        if not c:
            say(f"intro text: fix {fid} found nothing to change")
    write_html(build, I)
    m = re.search(r'data-fps="(\d+)"', (build / "index.html").read_text(encoding="utf-8"))
    intro = build / "renders" / "intro.mp4"
    keep = build / "renders" / "intro_before_text.mp4"
    if intro.exists():
        shutil.copy2(intro, keep)
    env = dict(os.environ, INTRO_FPS=m.group(1) if m else "30")
    say(f"intro text: {len(fixes or [])} fix(es) applied, rendering the intro again (same shots, no new plan)")
    r = subprocess.run([py, "-X", "utf8", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import build_intro; "
                        "build_intro.render_project(sys.argv[2])", str(HERE), str(build)], cwd=str(HERE), env=env)
    if r.returncode or not intro.exists() or intro.stat().st_size < 100000:
        if keep.exists():
            shutil.copy2(keep, intro)
        raise RuntimeError(f"intro text re-render failed ({r.returncode}); the previous intro is kept")
    keep.unlink(missing_ok=True)
    (build / "text_fixes.json").write_text(json.dumps(fixes or []), encoding="utf-8")
    return intro


if __name__ == "__main__":   # python text_fixes.py <build dir> '<fixes json>': dry run, prints what would change
    b, fx = sys.argv[1], json.loads(sys.argv[2])
    base = Path(b) / "intro_data.json"
    I0 = json.loads(base.read_text(encoding="utf-8")) if base.exists() else read_intro(b)
    I1, h = apply(I0, fx)
    print(h, I1.get("title"))
    for a, z in zip(I0["words"], I1["words"]):
        if a["w"] != z["w"]:
            print(f"  {a['s']:6.2f}  {a['w']!r} -> {z['w']!r}")
