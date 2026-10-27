"""White explainer cards for vertical Shorts (Studio type "short", user 2026-10-23: "build the Joseph-style white explainer
cards + keyword visuals into the short type").   python short_cards.py <project>

The look (Joseph | Video Editing, "How to Edit a Viral Talking-Head Using ONLY AI (2026 Style)", 15:33-15:47): the talking
head cuts to full-screen WHITE cards every few seconds and back. A card = a dark headline with ONE blue keyword at the top
("the average american adult", "they want to see you fail."), black-and-white photos in torn-paper circles, small labels
under them ("obese", "divorced", "less than $1K"). Hard cuts in and out, things pop in, a slow push.

1. Plan: claude_brain task "short_cards" (Claude) reads the KEPT transcript (one line per sentence, edit times) plus the
   creator's script (project/script.txt or settings.script) and picks the lines that get a card: never the first line
   (the hook stays on the face), never two lines in a row, about 35-45 % of the Short on cards, each 1.6-3.0 s from the
   start of its line. Per card: headline (3-8 words, lowercase), keyword, 1-3 pictures (Wikimedia search + a word the file
   title must contain) and labels. Cached in Edit/studio/cards/plan.json on the transcript.
2. Pictures: Wikimedia Commons, then Openverse (open licences; credits in cards.json for the description; picture downloads
   are OK without asking). Every candidate is shown to the eyes model on one labelled sheet (claude_brain task
   "short_pics_check"); a wrong one (a tank for "how it drives") moves its slot to the next candidate / search, up to 4
   rounds. Grey-scaled, contrast up, cut into a circle with a torn white paper rim (PIL). A card with no good picture shows
   the headline bigger.
3. Render: ONE HyperFrames composition (1080x1920, 60 fps) with the cards back to back, cut into card_NN.mp4.
Writes Edit/studio/cards/cards.json: {"items": [{"raw_s", "raw_e", "file", "headline", "credits"}]} in RAW recording time;
haul_render.py (SHORT mode) maps raw -> edit time and lays each card over the edit, on top of the captions.
settings.short_cards = false turns the cards off (cards.json gets no items).
"""
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, r"{{KIT}}/tools")
sys.path.insert(0, r"{{KIT}}/tools\intro_library")
KIT = Path(r"{{KIT}}/tools\intro_library\kit")
HF = "npx --yes hyperframes@0.8.180"
W, H, FPS = 1080, 1920, 60

proj = Path(sys.argv[1])
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings") or {}
work = proj / "Edit" / "studio"
out_dir = work / "cards"
out_dir.mkdir(parents=True, exist_ok=True)
out_json = out_dir / "cards.json"


def say(*a):
    print(*a, flush=True)


if S.get("short_cards") is False:
    out_json.write_text(json.dumps({"items": [], "off": True}), encoding="utf-8")
    say("cards: off (settings.short_cards = false)")
    sys.exit(0)

keep = [list(x) for x in json.loads((work / "cuts" / "cuts.json").read_text(encoding="utf-8"))["keep"]]
words = json.loads((work / "words.json").read_text(encoding="utf-8"))
words = words["words"] if isinstance(words, dict) else words


def edit_time(t):
    acc = 0.0
    for s, e in keep:
        if t < s:
            return acc
        if t <= e:
            return acc + t - s
        acc += e - s
    return acc


out_len = sum(e - s for s, e in keep)
kw = [w for w in words if any(s <= (w["s"] + w["e"]) / 2 < e for s, e in keep)]
L, cur = [], []
for i, w in enumerate(kw):   # one line per sentence (or a long pause), in edit time
    cur.append(w)
    gap = kw[i + 1]["s"] - w["e"] if i + 1 < len(kw) else 9
    if re.search(r"[.?!]$", w["w"].strip()) or gap > 0.8 or len(cur) > 24:
        L.append({"raw_s": cur[0]["s"], "raw_e": cur[-1]["e"], "s": edit_time(cur[0]["s"]), "e": edit_time(cur[-1]["e"]),
                  "text": " ".join(x["w"].strip() for x in cur)})
        cur = []
if len(L) < 3:
    out_json.write_text(json.dumps({"items": []}), encoding="utf-8")
    sys.exit("cards: fewer than 3 kept lines, no cards")

script = S.get("script") or ""
if not script and (proj / "script.txt").exists():
    script = (proj / "script.txt").read_text(encoding="utf-8", errors="replace")

# ---- 1. plan
plan_p = out_dir / "plan.json"
key = hashlib.md5(json.dumps([[round(x["s"], 1), x["text"]] for x in L] + [script]).encode()).hexdigest()
plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
if plan.get("key") != key or plan.get("v") != 5:
    import claude_brain as B
    text = "\n".join(f"L{i} [{x['s']:.1f}-{x['e']:.1f} s] {x['text']}" for i, x in enumerate(L))
    prompt = f"""You are the editor of a vertical YouTube Short: a creator talking to the camera. The finished Short cuts from the
talking head to full-screen WHITE explainer cards and back, like the viral 2026 talking-head style: a dark headline with ONE
blue keyword at the top, black-and-white photos of the real things being talked about, small labels under the photos.

The Short is {out_len:.1f} s long. What is said, one line per sentence (line id, start-end in the Short, words):
{text}
""" + (f"\nThe creator's script (for meaning only, the spoken words above are what is in the video):\n{script[:2500]}\n" if script else "") + """
Choose the lines that get a card, and design each card.
- Never L0 (the hook stays on the face). Never two cards on consecutive lines (the face comes back in between).
- About 35-45 % of the Short on cards; a card lasts from its line's start for 1.6-3.0 s (shorter if the line is shorter).
- Pick lines that name THINGS or NUMBERS a viewer can picture (parts, products, places, people, prices), or the key claim.
- headline: 3-8 words, lowercase except names, says the point of that line in plain words (may quote it). keyword: ONE
  word of the headline that carries it (shown blue).
- pictures: 1-3 photos of the literal, concrete things (objects, vehicles, places, people), never abstract ideas ("looks",
  "feel", "travel") - for an abstract line show the concrete thing it is about. "query" = a photo search (Wikimedia
  Commons / Flickr) that finds a real PHOTO of it, ALWAYS naming the Short's subject with the part, because a bare part
  name finds railway cars and motorcycles (Lift Kit test: "leaf spring" -> a freight-car bogie): "pickup truck leaf springs",
  "truck shock absorber", "lifted truck suspension", "gas station pump"; "alt" = two more searches for the same thing,
  plainer each time (the last one may be just the subject, e.g. "lifted pickup truck"); "must" = ONE plain word that will be in the photo's file name (e.g. "truck",
  "spring", "shock", "pump"); "label" = 1-3 words shown under it, or "".
Also pick 3 or 4 PUNCH-INS on the face (never on a card line): the single word in a line that carries the point (a number,
a strong claim, a payoff). "word" = that word exactly as spoken.
"subject" = a photo search for the Short's main subject as a whole (e.g. "lifted pickup truck"): it fills any card whose
own photos can't be found.
Reply with ONLY JSON: {"subject": "...", "cards": [{"line": <n>, "dur": <seconds>, "headline": "...", "keyword": "...",
  "pictures": [{"query": "...", "alt": ["...", "..."], "must": "...", "label": "..."}]}],
  "punch": [{"line": <n>, "word": "..."}]}"""
    ans = B.ask("short_cards", prompt, say=say) or {}
    cards = []
    used = set()
    for c in ans.get("cards") or []:
        try:
            li = int(str(c.get("line")).lstrip("L"))
        except (TypeError, ValueError):
            continue
        # never over the hook: the first line and anything starting before the hook headline is gone (3.5 s; the Lift Kit
        # planner put a card on line 1 at 0:01.1, over "Why is everyone putting one on their truck?")
        if li <= 0 or li >= len(L) or L[li]["s"] < 3.5 or li in used or li - 1 in used or li + 1 in used:
            continue
        used.add(li)
        cards.append({"line": li, "dur": float(c.get("dur") or 2.2), "headline": str(c.get("headline") or "")[:70],
                      "keyword": str(c.get("keyword") or ""), "pictures": [p for p in (c.get("pictures") or [])[:3] if p.get("query")]})
    punch = []
    for p in ans.get("punch") or []:   # punch-ins on 3-4 key words (Grow with Alex: "punch in on 3 or 4 words")
        try:
            li = int(str(p.get("line")).lstrip("L"))
        except (TypeError, ValueError):
            continue
        if 0 <= li < len(L) and li not in used and len(punch) < 4:
            punch.append({"line": li, "word": str(p.get("word") or "")})
    plan = {"v": 5, "key": key, "subject": str(ans.get("subject") or ""), "cards": sorted(cards, key=lambda c: c["line"]), "punch": punch,
            "ai": bool(ans)}
    plan_p.write_text(json.dumps(plan, indent=1), encoding="utf-8")
if not plan["cards"]:
    out_json.write_text(json.dumps({"items": []}), encoding="utf-8")
    sys.exit("cards: the planner chose no cards")

# ---- 2. pictures: Wikimedia / Openverse photo, checked by the eyes model -> grey torn-paper circle
import pics   # noqa: E402  (intro_library: Wikimedia Commons search with the licence kept)

PIC_DIR = out_dir / "pics"
PIC_DIR.mkdir(exist_ok=True)


def drawing(path):
    """a line drawing / diagram / patent sheet (mostly white paper): the Lift Kit test found a tank-suspension drawing for
    "suspension travel" and a space-station model for "spacers" when the search ran without a required word"""
    im = ImageOps.grayscale(Image.open(path)).resize((200, 200))
    px = list(im.tobytes())
    return sum(p > 232 for p in px) / len(px) > 0.45 or sum(p > 205 for p in px) / len(px) > 0.6


def openverse(query, n=3):
    """open-licence photos (Flickr and others) from Openverse: much more than Wikimedia Commons for everyday things (Lift
    Kit 2026-10-23: Commons had no usable "pickup truck towing trailer"); licence + creator kept for the credits"""
    import urllib.parse
    q = urllib.parse.urlencode({"q": query, "page_size": 12, "license_type": "commercial", "mature": "false"})
    req = urllib.request.Request("https://api.openverse.org/v1/images/?" + q, headers={"User-Agent": pics.UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    out = []
    for x in d.get("results") or []:
        if (x.get("width") or 0) < 600 or (x.get("height") or 0) < 450:
            continue
        out.append({"url": x["url"], "title": x.get("title") or "", "artist": x.get("creator") or "", "license": (x.get("license") or "").upper(),
                    "page": x.get("foreign_landing_url") or "", "tags": [t.get("name", "") for t in x.get("tags") or []][:12]})
        if len(out) >= n:
            break
    return out


def candidates(query, must):
    """a search's candidate photos, best first: the Wikimedia hit whose file title holds `must`, then Openverse results
    whose title or tags hold it (or all of them when no word is given). Cached per search; downloaded on use."""
    k = hashlib.md5(f"{query}|{must}|v3".encode()).hexdigest()[:10]
    meta = PIC_DIR / f"{k}.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    got = []
    try:
        h = pics.commons(query, "photo", need=[must] if must else None)
        if h:
            got.append(h)
    except Exception as ex:  # noqa: one missing picture never stops the cards
        say(f"   Wikimedia search failed for '{query}': {type(ex).__name__}")
    try:
        got += [h for h in openverse(query) if not must or must in (h["title"] + " " + " ".join(h["tags"])).lower()]
    except Exception as ex:  # noqa
        say(f"   Openverse search failed for '{query}': {type(ex).__name__}")
    got = [h for h in got if not re.search(r"drawing|diagram|patent|sketch|scheme|model|toy|illustration|lego|cartoon", h.get("title", ""), re.I)]
    for n, h in enumerate(got):
        h.update({"query": query, "file": str(PIC_DIR / f"{k}_{n}.jpg")})
    meta.write_text(json.dumps(got, indent=1), encoding="utf-8")
    return got


def fetch_one(h):
    """download a candidate (once); None when it fails or is a drawing / mostly blank"""
    f = Path(h["file"])
    if not f.exists():
        try:
            req = urllib.request.Request(h["url"], headers={"User-Agent": pics.UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                f.write_bytes(r.read())
        except Exception:  # noqa
            return None
    try:
        return None if drawing(f) else h
    except Exception:  # noqa: not an image
        return None


def torn_circle(src, dst, size=760, seed=0):
    """grey photo in a circle with a torn white paper rim (Joseph's cards): centre-crop square, greyscale + contrast,
    a jagged circle mask, a jagged white rim a little wider, transparent outside"""
    rnd = random.Random(seed)
    im = Image.open(src).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, max(0, (im.height - s) // 2 - s // 12), (im.width + s) // 2, max(0, (im.height - s) // 2 - s // 12) + s))
    im = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1).convert("RGB").resize((size, size), Image.LANCZOS)

    def jag(r0, amp, n=140):
        ph = [rnd.uniform(0, math.tau) for _ in range(4)]
        pts = []
        for k in range(n):
            a = math.tau * k / n
            r = r0 + amp * (0.55 * math.sin(3 * a + ph[0]) + 0.3 * math.sin(7 * a + ph[1]) + 0.15 * math.sin(13 * a + ph[2])) + rnd.uniform(-amp, amp) * 0.6
            pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
        return pts
    pad = 46
    canvas = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    rim = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(rim).polygon([(x + pad, y + pad) for x, y in jag(size / 2 + 26, 9)], fill=255)
    rim = rim.filter(ImageFilter.GaussianBlur(0.8))
    canvas.paste((250, 250, 248, 255), (0, 0), rim)
    hole = Image.new("L", (size, size), 0)
    ImageDraw.Draw(hole).polygon(jag(size / 2 - 6, 7), fill=255)
    canvas.paste(im, (pad, pad), hole.filter(ImageFilter.GaussianBlur(0.6)))
    canvas.save(dst)


def check_sheet(cands):
    """the eyes model looks at every candidate picture (labelled P0, P1 ...) and says which do NOT show the intended thing
    (Lift Kit test 2026-10-23: a TANK for "how it drives", a blank drawing for "factory springs", a file title holding the
    word proves nothing). -> set of bad labels; empty when the check can't run (the pictures stay)"""
    if not cands:
        return set()
    cell, cols = 300, 4
    rows = math.ceil(len(cands) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 40)), "white")
    d_ = ImageDraw.Draw(sheet)
    for n, (lab, f, want) in enumerate(cands):
        im = ImageOps.fit(Image.open(f).convert("RGB"), (cell - 10, cell - 10))
        x, y = (n % cols) * cell, (n // cols) * (cell + 40)
        sheet.paste(im, (x + 5, y + 5))
        d_.text((x + 8, y + cell + 6), lab, fill="black")
    sp = out_dir / "pics_check.jpg"
    sheet.save(sp, quality=88)
    import claude_brain as B
    want = "\n".join(f"{lab}: should be a real photo of {w}" for lab, f, w in cands)
    ans = B.ask("short_pics_check", "Pictures picked for the explainer cards of a YouTube Short (shown black-and-white in circles). "
                "Each cell is labelled. For each label, is it a clear real PHOTO of the thing it should show, recognisable at a "
                "glance? Bad = a different thing (e.g. a tank or a toy instead of a pickup truck), a drawing / diagram / map / "
                "logo, mostly blank, or the thing too small to see.\n" + want +
                "\nReply ONLY JSON {\"bad\": [\"P0\", ...]}", images=[str(sp)], say=say) or {}
    return {str(x) for x in ans.get("bad") or []}


credits = []
slots = []   # every picture a card wants: its searches in order, the photo it ends with
for ci, c in enumerate(plan["cards"]):
    c["imgs"] = []
    for pi, p in enumerate(c["pictures"]):
        qs = [p["query"]] + [x for x in (p.get("alt") or []) if isinstance(x, str)][:2]   # the planner's other searches next
        slots.append({"ci": ci, "pi": pi, "p": p, "qs": qs, "pool": [], "hit": None, "done": False,
                      "want": f"{p.get('label') or p['query']} ({p['query']}; card: {c['headline']})"})
for rnd in range(3):   # a candidate per open slot, all checked on one sheet; a rejected one tries its next candidate / search
    cands = []
    for sl in slots:
        if sl["done"]:
            continue
        hit = None
        while not hit and (sl["pool"] or sl["qs"]):
            if not sl["pool"]:
                sl["pool"] = list(candidates(sl["qs"].pop(0), (sl["p"].get("must") or "").lower()))
                continue
            hit = fetch_one(sl["pool"].pop(0))
        if not hit:
            sl["done"] = True
            continue
        sl["hit"] = hit
        cands.append((f"P{len(cands)}", hit["file"], sl["want"], sl))
    if not cands:
        break
    bad = check_sheet([(lab, f, w) for lab, f, w, _ in cands])
    for lab, f, w, sl in cands:
        if lab in bad:
            say(f"   picture rejected by the eyes ({w[:60]}): {Path(f).name}")
            sl["hit"] = None
            sl["done"] = not sl["qs"] and not sl["pool"]
        else:
            sl["done"] = True
# a card left with no picture gets a photo of the Short's subject (each a different one, checked on a sheet like the rest)
bare = sorted({sl["ci"] for sl in slots} - {sl["ci"] for sl in slots if sl["hit"]} | {ci for ci, c in enumerate(plan["cards"]) if not c["pictures"]})
if bare and plan.get("subject"):
    pool = [h for h in candidates(plan["subject"], "") + candidates(plan["subject"] + " photo", "")]
    # never the same photo twice: compare by URL (two searches return the same photo under different cache names; the
    # Lift Kit draft showed one white Ram on three cards)
    used_u = {sl["hit"]["url"] for sl in slots if sl["hit"]}
    seen_u, pool_ = set(), []
    for h in pool:
        if h["url"] not in used_u and h["url"] not in seen_u:
            seen_u.add(h["url"])
            pool_.append(h)
    pool = pool_

    def look(f):
        """an 8x8 grey fingerprint: the same photo at two sizes / from two URLs matches"""
        return ImageOps.grayscale(Image.open(f)).resize((8, 8)).point(lambda v: v // 32).tobytes()
    used_looks = {look(sl["hit"]["file"]) for sl in slots if sl["hit"]}
    for rnd in range(2):
        cands = []
        for ci in bare:
            if any(sl["ci"] == ci and sl["hit"] for sl in slots):
                continue
            hit = None
            while pool and not hit:
                hit = fetch_one(pool.pop(0))
                if hit and look(hit["file"]) in used_looks:   # the same photo at another size / URL
                    hit = None
            if hit:
                used_looks.add(look(hit["file"]))
                sl = {"ci": ci, "pi": 9, "p": {"query": plan["subject"], "label": ""}, "hit": hit}
                cands.append((f"P{len(cands)}", hit["file"], f"{plan['subject']} (card: {plan['cards'][ci]['headline']})", sl))
        if not cands:
            break
        bad = check_sheet([(lab, f, w) for lab, f, w, _ in cands])
        for lab, f, w, sl in cands:
            if lab not in bad:
                slots.append(sl)
                say(f"   card {sl['ci'] + 1}: the subject photo stands in")
for sl in slots:
    c, hit = plan["cards"][sl["ci"]], sl["hit"]
    if not hit:
        say(f"   card {sl['ci'] + 1}: no good photo for '{sl['p']['query']}'")
        continue
    png = out_dir / f"c{sl['ci']}_{sl['pi']}.png"
    torn_circle(hit["file"], png, seed=sl["ci"] * 10 + sl["pi"])
    c["imgs"].append({"png": png.name, "label": sl["p"].get("label") or ""})
    credits.append({"title": hit.get("title"), "artist": hit.get("artist"), "license": hit.get("license"), "page": hit.get("page")})

# the user's own pictures win: <project>\pictures\<card number> <label>.jpg|png (e.g. "3 shock absorber.jpg"; numbers as in
# the cards log, 1 = the first card). A card with own pictures shows only those (up to 3), no search, no check.
# (Lift Kit 2026-10-23: the free photo pools had no truck shocks / springs / spacer blocks, and Higgsfield is gone.)
own_dir = proj / "pictures"
if own_dir.is_dir():
    own = {}
    for f in sorted(own_dir.iterdir()):
        m = re.match(r"(\d+)\s*[-_ ]?\s*(.*)$", f.stem)
        if m and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            own.setdefault(int(m.group(1)) - 1, []).append((f, m.group(2).strip()))
    for ci, fl in own.items():
        if 0 <= ci < len(plan["cards"]):
            plan["cards"][ci]["imgs"] = []
            for pi, (f, lab) in enumerate(fl[:3]):
                png = out_dir / f"c{ci}_own{pi}.png"
                torn_circle(f, png, seed=ci * 10 + pi)
                plan["cards"][ci]["imgs"].append({"png": png.name, "label": lab})
            say(f"   card {ci + 1}: {len(fl[:3])} own picture(s) from {own_dir.name}\\")

# ---- 3. one HyperFrames composition, cards back to back
hf = out_dir / "hf"
if hf.exists():
    shutil.rmtree(hf)
(hf / "assets" / "fonts").mkdir(parents=True)
shutil.copy(KIT / "gsap.min.js", hf / "assets")
shutil.copy(KIT / "fonts" / "Inter.ttf", hf / "assets" / "fonts")
shutil.copy(KIT / "hyperframes.json", hf)
(hf / "package.json").write_text(json.dumps({"name": "shortcards", "private": True, "type": "module"}), encoding="utf-8")

LAYOUT = {   # circle centres + diameters per picture count (1080x1920 card, headline on top)
    0: [],
    # everything stays above the bottom 20 % (y 1536: the Shorts title / buttons) and off the right edge (Grow with Alex,
    # "Learn 90% of Claude Video Editing", 2026-10-23: "nothing in the bottom 20% or right edge")
    1: [(540, 1040, 680)],
    2: [(330, 900, 500), (720, 1240, 500)],
    3: [(300, 830, 420), (750, 1020, 420), (420, 1270, 420)],
}
items, divs, t = [], [], 0.0
for ci, c in enumerate(plan["cards"]):
    ln = L[c["line"]]
    s_raw = ln["raw_s"]
    dur = max(1.6, min(3.0, c["dur"], (L[c["line"] + 1]["s"] if c["line"] + 1 < len(L) else out_len) - ln["s"] - 0.05))
    dur = round(dur * FPS) / FPS
    kwd = c["keyword"].lower().strip(".,!?")
    hw = []
    for w in c["headline"].split():
        safe = w.replace("&", "&amp;").replace("<", "&lt;")
        cls = "w k" if kwd and w.lower().strip(".,!?") == kwd else "w"
        hw.append(f'<span class="{cls}">{safe}</span>')
    big = " big" if not c["imgs"] else ""
    pics_html = ""
    for pi, (im, (x, y, d)) in enumerate(zip(c["imgs"], LAYOUT[len(c["imgs"])])):
        rot = (-5, 4, -3)[pi % 3]
        lab = f'<div class="lab">{im["label"]}</div>' if im["label"] else ""
        pics_html += (f'<div class="pic" style="left:{x - d / 2:.0f}px;top:{y - d / 2:.0f}px;width:{d}px;height:{d}px;--r:{rot}deg">'
                      f'<img src="assets/{im["png"]}" alt="" />{lab}</div>')
        shutil.copy(out_dir / im["png"], hf / "assets" / im["png"])
    divs.append(f'<div class="card" id="c{ci}"><div class="stage"><h1 class="hl{big}">{" ".join(hw)}</h1>{pics_html}</div></div>')
    items.append({"raw_s": round(s_raw, 3), "dur": dur, "t": round(t, 4), "headline": c["headline"], "line": ln["text"]})
    t += dur
total = round(t, 4)

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={W}, height={H}" />
<script src="assets/gsap.min.js"></script>
<style>
@font-face{{font-family:"Inter";src:url("assets/fonts/Inter.ttf") format("truetype");font-weight:100 900;}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#f6f6f3; }}
#root {{ position:relative; width:100%; height:100%; overflow:hidden; }}
.card {{ position:absolute; inset:0; visibility:hidden;
  background:radial-gradient(ellipse at 50% 42%, #ffffff 0%, #f4f4f1 60%, #e9e9e4 100%); }}
.stage {{ position:absolute; inset:0; transform-origin:50% 45%; }}
.hl {{ position:absolute; left:84px; right:84px; top:300px; font:800 92px/1.08 "Inter"; color:#141a2a; letter-spacing:-0.02em; }}
.hl.big {{ top:620px; font-size:124px; }}
.w {{ display:inline-block; opacity:0; transform:translateY(40px); }}
.k {{ color:#2b6fea; }}
.pic {{ position:absolute; transform:scale(.82) rotate(var(--r)); opacity:0; filter:drop-shadow(0 26px 34px rgba(0,0,0,.28)); }}
.pic img {{ width:100%; height:100%; display:block; }}
.lab {{ position:absolute; left:50%; bottom:-26px; transform:translateX(-50%) rotate(calc(var(--r) * -0.6)); white-space:nowrap;
  font:700 40px "Inter"; color:#141a2a; background:#fff; padding:8px 22px; border-radius:10px; box-shadow:0 8px 20px rgba(0,0,0,.18); }}
</style></head>
<body>
<div id="root" data-composition-id="shortcards" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total}" data-fps="{FPS}">
{''.join(divs)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
const cards = {json.dumps([[it["t"], it["dur"]] for it in items])};
cards.forEach(([t0, d], i) => {{
  const c = "#c" + i;
  tl.set(c, {{ visibility: "visible" }}, t0);
  tl.set(c, {{ visibility: "hidden" }}, t0 + d);
  // one thing moves at a time, eased, no bounce (Grow with Alex rules): the headline rises word by word, THEN each
  // picture eases in after the one before; only a slow push runs under it all
  tl.fromTo(c + " .stage", {{ scale: 1.0 }}, {{ scale: 1.03, duration: d, ease: "none" }}, t0);
  const nw = document.querySelectorAll(c + " .w").length;
  tl.to(c + " .w", {{ opacity: 1, y: 0, duration: 0.28, stagger: 0.045, ease: "power2.out" }}, t0 + 0.02);
  const p0 = t0 + 0.06 + Math.min(0.5, nw * 0.045);
  tl.to(c + " .pic", {{ opacity: 1, scale: 1, duration: 0.34, stagger: 0.26, ease: "power2.out" }}, p0);
}});
tl.set({{}}, {{}}, {total});
window.__timelines["shortcards"] = tl;
</script></body></html>"""
(hf / "index.html").write_text(html, encoding="utf-8")
html_md5 = hashlib.md5(html.encode()).hexdigest()
# punch-ins: the raw time of the chosen word in its line (the line start when the word isn't found), held to the line end
punch_raw = []
for p in plan.get("punch") or []:
    ln = L[p["line"]]
    tgt = re.sub(r"[^a-z0-9$%]", "", p["word"].lower())
    w0 = next((w for w in kw if ln["raw_s"] - 0.01 <= w["s"] <= ln["raw_e"] and re.sub(r"[^a-z0-9$%]", "", w["w"].lower()) == tgt), None)
    punch_raw.append({"raw_s": round(w0["s"] if w0 else ln["raw_s"], 3), "raw_e": round(ln["raw_e"], 3), "word": p["word"]})
prev = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else {}
if prev.get("html_md5") == html_md5 and all(Path(x.get("file") or "-").exists() for x in prev.get("items") or [None]):
    prev["punch"] = punch_raw
    out_json.write_text(json.dumps(prev, indent=1), encoding="utf-8")   # touch: newer than its inputs
    sys.exit(say(f"cards: unchanged ({len(items)} cards), render reused") or 0)
say(f"cards: {len(items)} cards, {total:.1f} s of {out_len:.1f} s ({100 * total / max(1, out_len):.0f} %), {len(credits)} pictures")
for it, c in zip(items, plan["cards"]):
    say(f"   {edit_time(it['raw_s']) // 60:.0f}:{edit_time(it['raw_s']) % 60:04.1f} {it['dur']:.1f}s '{c['headline']}' "
        f"[{', '.join(i['label'] or '-' for i in c['imgs'])}]")
say("== render (HyperFrames)")
r = subprocess.run(f"{HF} render --quiet --quality standard -o renders/cards.mp4", cwd=hf, shell=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
mp4 = hf / "renders" / "cards.mp4"
if r.returncode or not mp4.exists():
    sys.exit("HyperFrames render failed:\n" + (r.stdout + r.stderr)[-2000:])
for i, it in enumerate(items):   # one file per card, frame-exact (re-encoded)
    f = out_dir / f"card_{i:02d}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{it['t']:.4f}", "-i", str(mp4), "-t", f"{it['dur']:.4f}", "-an",
                    "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "16", "-pix_fmt", "yuv420p", "-r", str(FPS), str(f)], check=True)
    it["file"] = str(f)
    it["raw_e"] = None
out_json.write_text(json.dumps({"items": items, "credits": credits, "html_md5": html_md5, "punch": punch_raw}, indent=1), encoding="utf-8")
say(f"wrote {out_json}")
