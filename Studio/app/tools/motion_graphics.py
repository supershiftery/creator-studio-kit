"""Motion graphics step (New Project / Project settings "Motion graphics", user 2026-10-22).   python motion_graphics.py <project>
Runs after the cutter and before the render. Writes <project>/Edit/studio/graphics/graphics.json:
    {"items": [{"type": "article", "file": ".../article.mp4", "raw": <source time it starts>, "dur": 11.0, ...}]}
The renderer (trim_render.py) lays every item over the edit at that moment (raw time -> edit time through the kept ranges).

Types (settings.graphics.type):
  article = the MacBook one-off's 3D news card: a real article page captured with Playwright, tilted in 3D, the camera
            pushes to each claim and a yellow marker sweeps over it. settings.graphics.url / .highlight are optional:
            without them Claude (CLI, web search) reads the transcript, finds an article that backs the video's main claim,
            and picks up to 3 exact phrases from it plus the spoken line the card should start on.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import chat  # noqa: E402  (claude_exe, MODEL)

KIT = Path(r"{{KIT}}/tools\intro_library\kit")
HF = "npx --yes hyperframes@0.8.180"
CARD_W = 760  # CSS px the captured column is shown at (screenshot is 2x)

proj = Path(sys.argv[1])
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings") or {}
G = S.get("graphics") or {}
work = proj / "Edit" / "studio"
out_dir = work / "graphics"
out_dir.mkdir(parents=True, exist_ok=True)
words = json.loads((work / "words.json").read_text(encoding="utf-8"))
keep = json.loads((work / "cuts" / "cuts.json").read_text(encoding="utf-8"))["keep"]


def say(msg):
    print(msg, flush=True)


def kept_lines():
    """the kept transcript as timed lines (raw seconds) for the planner"""
    lines, cur, t0 = [], [], None
    for w in words:
        if not any(s - 0.05 <= w["s"] <= e + 0.05 for s, e in keep):
            continue
        if t0 is None:
            t0 = w["s"]
        cur.append(w["w"])
        if w["w"][-1:] in ".!?" or len(cur) > 28:
            lines.append(f"[{t0:.1f}] {' '.join(cur)}"); cur, t0 = [], None
    if cur:
        lines.append(f"[{t0:.1f}] {' '.join(cur)}")
    return "\n".join(lines)


def plan_article():
    """Claude picks the article, the phrases to mark and the anchor line. Returns dict(url, highlight[], anchor)."""
    have_url, have_hl = G.get("url"), [h for h in (G.get("highlight") or []) if h]
    prompt = f"""You are adding ONE motion graphic to a tech/news video: a real news article shown as a 3D card with a yellow
highlighter over the key claim. Transcript of the edited video (seconds in the raw recording in brackets):

{kept_lines()[:16000]}

{"Use this article: " + have_url if have_url else "Search the web for a reputable news article (9to5Mac, MacRumors, The Verge, Engadget, Bloomberg, etc.) that backs the video's MAIN claim or rumour. Prefer the outlet the video itself shows or names."}
{"Highlight these phrases: " + json.dumps(have_hl) if have_hl else "Open the article and pick 1-3 short phrases (3-9 words) copied EXACTLY from its headline / opening paragraphs / bullet list that state the claim. The first one should be in the headline when possible."}
Pick the anchor: the spoken line where the card should appear (the moment the video starts talking about that claim).
Copy 4-8 consecutive words of it EXACTLY from the transcript.

Reply with ONLY a JSON object, no prose: {{"url": "...", "highlight": ["...", "..."], "anchor": "...", "why": "one short sentence"}}"""
    say("== planner (Claude + web search)")
    cmd = [chat.claude_exe(), "-p", prompt, "--model", chat.MODEL, "--output-format", "json", "--max-turns", "14",
           "--no-session-persistence", "--allowedTools", "WebSearch", "WebFetch"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, stdin=subprocess.DEVNULL)
    try:
        res = json.loads(r.stdout).get("result") or ""
    except ValueError:
        res = r.stdout or r.stderr
    if "Not logged in" in res or "/login" in res:
        raise SystemExit("The Claude Code CLI is not signed in (Revisions tab -> Sign in).")
    m = re.search(r"\{.*\}", res, re.S)
    if not m:
        raise SystemExit(f"planner gave no JSON: {res[:400]}")
    p = json.loads(m.group(0))
    if have_url:
        p["url"] = have_url
    if have_hl:
        p["highlight"] = have_hl
    say(f"   article: {p.get('url')}\n   highlight: {p.get('highlight')}\n   anchor: {p.get('anchor')!r}  ({p.get('why', '')})")
    return p


def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def anchor_time(anchor):
    """raw time of the anchor quote in words.json (best run of matching words, kept ranges only)"""
    target = [norm(x) for x in (anchor or "").split() if norm(x)]
    if not target:
        return None
    best, best_t = 0, None
    for i in range(len(words)):
        if not any(s - 0.05 <= words[i]["s"] <= e + 0.05 for s, e in keep):
            continue
        n = sum(1 for j, t in enumerate(target) if i + j < len(words) and norm(words[i + j]["w"]) == t)
        if n > best:
            best, best_t = n, words[i]["s"]
    return best_t if best >= max(2, len(target) // 2) else None


CAPTURE_JS = """(phrases) => {
  const hide = 'iframe,[id*=ad-],[class*=ad-slot],[class*=adthrive],[class*=cookie],[id*=cookie],[class*=consent],[id*=consent],.fc-consent-root,[class*=newsletter],[class*=popup],[class*=modal]';
  document.querySelectorAll(hide).forEach(e => e.style.setProperty('display', 'none', 'important'));
  const flat = s => s.replace(/[\\u2018\\u2019]/g, "'").replace(/[\\u201c\\u201d]/g, '"').replace(/\\s+/g, ' ').toLowerCase();
  const hits = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = []; let n; while ((n = walker.nextNode())) if (n.data.trim() && n.parentElement && n.parentElement.offsetParent) nodes.push(n);
  for (const ph of phrases) {
    const want = flat(ph); let done = false;
    for (const nd of nodes) {           // phrase inside one text node
      const i = flat(nd.data).indexOf(want); if (i < 0) continue;
      const r = document.createRange(); r.setStart(nd, i); r.setEnd(nd, Math.min(nd.data.length, i + ph.length));
      hits.push({ph, rects: [...r.getClientRects()].map(q => [q.x, q.y + scrollY, q.width, q.height])}); done = true; break;
    }
    if (!done) {                        // phrase across links / bold: mark the whole smallest element holding it
      let el = null; for (const e of document.querySelectorAll('h1,h2,h3,p,li,blockquote')) if (flat(e.innerText).includes(want)) { el = e; break; }
      if (el) { const q = el.getBoundingClientRect(); hits.push({ph, whole: true, rects: [[q.x, q.y + scrollY, q.width, Math.min(q.height, 60)]]}); }
    }
  }
  const h = document.querySelector('h1'); const hr = h ? h.getBoundingClientRect() : {x: 80, y: 200, width: 760};
  // the article column = the body paragraphs under the headline (NOT a wrapper, which often holds the sidebar too)
  let l = hr.x, r = hr.x + hr.width;
  for (const p of document.querySelectorAll('p, li')) {
    const q = p.getBoundingClientRect(); if (q.top + scrollY < hr.y || p.innerText.length < 60 || q.width < 200) continue;
    if (q.x > hr.x + 200 || q.x < hr.x - 200) continue;      // sidebar / footer blocks sit elsewhere
    l = Math.min(l, q.x); r = Math.max(r, q.x + q.width);
  }
  return {hits, h1: [hr.x, hr.y + scrollY, hr.width, hr.height], col: [l, r - l]};
}"""


def capture(url, phrases):
    from playwright.sync_api import sync_playwright
    say("== capture article page")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        info = pg.evaluate(CAPTURE_JS, phrases)
        pg.wait_for_timeout(800)
        pg.screenshot(path=str(out_dir / "page.png"), full_page=True)
        b.close()
    found = [h["ph"] for h in info["hits"]]
    say(f"   marked {len(found)}/{len(phrases)}: {found}")
    return info


def build_card(info):
    """crop the article column (headline -> last highlight) and turn the hit rects into card-relative boxes"""
    from PIL import Image
    im = Image.open(out_dir / "page.png")
    h1x, h1y, h1w, _ = info["h1"]
    cx, cw = info["col"]
    left = max(0.0, min(h1x, cx) - 24)
    width = min(max(h1w, cw) + 48, 900)
    top = max(0.0, h1y - 60)
    rects = [r for h in info["hits"] for r in h["rects"]]
    bottom = max([top + 900] + [r[1] + r[3] + 140 for r in rects])
    bottom = min(bottom, top + 2400, im.height / 2)
    card = im.crop((int(left * 2), int(top * 2), int((left + width) * 2), int(bottom * 2)))
    sc = CARD_W / width
    card = card.resize((CARD_W * 2, int(card.height * sc)), Image.LANCZOS)
    card.save(out_dir / "article" / "assets" / "card.png")
    groups = []
    for h in info["hits"]:
        boxes = [[(x - left) * sc - 5, (y - top) * sc - 1, w * sc + 10, hh * sc + 2] for x, y, w, hh in h["rects"] if w > 4]
        boxes = [b for b in boxes if b[1] > 0 and b[1] + b[3] < card.height / 2]
        if boxes:
            groups.append(boxes)
    return card.height / 2, groups


def article_html(card_h, groups):
    """the approved MacBook card motion, generalised to 1-3 highlight groups"""
    n = len(groups)
    dur = round(2.4 + 2.2 * max(n, 1) + 2.4, 2)
    hl = "\n".join(f'<div class="hl g{g}" style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{h:.0f}px"></div>'
                   for g, boxes in enumerate(groups) for x, y, w, h in boxes)
    stops = []
    for boxes in groups:
        x0 = min(b[0] for b in boxes); x1 = max(b[0] + b[2] for b in boxes)
        y0 = min(b[1] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
        z = max(1.3, min(2.15, 1500 / max(1, x1 - x0), 700 / max(1, y1 - y0)))
        stops.append([round((x0 + x1) / 2, 1), round((y0 + y1) / 2, 1), round(z, 2)])
    wide_z = round(min(0.78, 980 / card_h, 1500 / CARD_W), 3)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=1920, height=1080" />
<script src="assets/gsap.min.js"></script>
<style>
@font-face{{font-family:"Inter";src:url("assets/fonts/Inter.ttf") format("truetype");font-weight:100 900;}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1920px; height:1080px; overflow:hidden; background:#000; }}
#root {{ position:relative; width:100%; height:100%; overflow:hidden; background:radial-gradient(ellipse at 50% 45%, #1d1e26 0%, #0a0a0d 55%, #000 100%); }}
.glow {{ position:absolute; border-radius:50%; filter:blur(140px); opacity:.55; }}
#g1 {{ width:900px; height:700px; left:-150px; top:380px; background:#3a6cff; }}
#g2 {{ width:800px; height:640px; left:1200px; top:-160px; background:#c04dff; }}
#g3 {{ width:600px; height:500px; left:820px; top:700px; background:#ff7a3d; opacity:.3; }}
#cam {{ position:absolute; left:0; top:0; width:{CARD_W}px; height:{card_h:.0f}px; transform-origin:0 0; perspective:2600px; }}
#card {{ position:absolute; inset:0; transform-style:preserve-3d; border-radius:18px; background:#fff; box-shadow:0 60px 140px rgba(0,0,0,.65), 0 0 0 1px rgba(255,255,255,.08); }}
#card img {{ position:absolute; inset:0; width:100%; height:100%; border-radius:18px; display:block; }}
.hl {{ position:absolute; background:#ffe03a; mix-blend-mode:multiply; border-radius:4px; transform-origin:0 50%; transform:scaleX(0); }}
#src {{ position:absolute; left:72px; bottom:56px; font:600 26px "Inter"; color:rgba(255,255,255,.8); letter-spacing:.02em; opacity:0;
  padding:10px 20px; border-radius:999px; background:rgba(10,10,14,.82); }}
#src b {{ color:#fff; font-weight:800; }}
</style></head>
<body>
<div id="root" data-composition-id="article" data-start="0" data-width="1920" data-height="1080" data-duration="{dur}" data-fps="60">
  <div class="glow" id="g1"></div><div class="glow" id="g2"></div><div class="glow" id="g3"></div>
  <div id="cam"><div id="card"><img src="assets/card.png" alt="" />
{hl}
  </div></div>
  <div id="src">Source: <b>{{SOURCE}}</b></div>
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
const CH = {card_h:.1f}, DUR = {dur};
const at = (fx, fy, z) => ({{ x: 960 - z * fx, y: 540 - z * fy, scale: z }});
const wide = at({CARD_W / 2}, CH / 2, {wide_z});
const stops = {json.dumps(stops)};
gsap.set("#cam", at({CARD_W / 2}, CH / 2, {wide_z * 0.66:.3f}));
gsap.set("#card", {{ rotationX: 62, rotationY: -24, rotationZ: -10, y: 900, opacity: 0, transformOrigin: "50% 50%" }});
tl.to("#card", {{ rotationX: 12, rotationY: -16, rotationZ: -2, y: 0, opacity: 1, duration: 1.3, ease: "power3.out" }}, 0);
tl.to("#cam", {{ ...wide, duration: 1.3, ease: "power3.out" }}, 0);
tl.to("#src", {{ opacity: 1, duration: 0.5 }}, 0.8);
let t = 1.3;
stops.forEach(([fx, fy, z], i) => {{
  const tilt = i % 2 ? {{ rotationX: 4, rotationY: 6 }} : {{ rotationX: 6, rotationY: -7 }};
  tl.to("#cam", {{ ...at(fx, fy, z), duration: 1.1, ease: "power2.inOut" }}, t);
  tl.to("#card", {{ ...tilt, rotationZ: 0, duration: 1.1, ease: "power2.inOut" }}, t);
  const parts = gsap.utils.toArray(".g" + i), each = 0.7 / parts.length;
  parts.forEach((el, k) => tl.to(el, {{ scaleX: 1, duration: each, ease: k === parts.length - 1 ? "power2.out" : "none" }}, t + 1.1 + k * each));
  tl.to("#cam", {{ ...at(fx + 15, fy, z * 1.04), duration: 1.1, ease: "none" }}, t + 1.1);
  t += 2.2;
}});
tl.to("#cam", {{ ...wide, duration: 1.4, ease: "power3.inOut" }}, t);
tl.to("#card", {{ rotationX: 10, rotationY: 14, rotationZ: 1.5, duration: 1.4, ease: "power3.inOut" }}, t);
tl.to("#card", {{ rotationY: 18, duration: DUR - 0.6 - (t + 1.4), ease: "none" }}, t + 1.4);
tl.to("#card", {{ rotationY: 70, x: 900, opacity: 0, duration: 0.6, ease: "power2.in" }}, DUR - 0.6);
tl.to("#src", {{ opacity: 0, duration: 0.3 }}, DUR - 0.6);
tl.to("#g1", {{ x: 260, y: -120, duration: DUR, ease: "none" }}, 0);
tl.to("#g2", {{ x: -240, y: 140, duration: DUR, ease: "none" }}, 0);
tl.to("#g3", {{ x: -300, y: -60, duration: DUR, ease: "none" }}, 0);
tl.set({{}}, {{}}, DUR);
window.__timelines["article"] = tl;
</script></body></html>""", dur


def source_name(url):
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0])
    known = {"9to5mac.com": "9to5Mac", "macrumors.com": "MacRumors", "theverge.com": "The Verge", "engadget.com": "Engadget",
             "bloomberg.com": "Bloomberg", "macworld.com": "Macworld", "cultofmac.com": "Cult of Mac", "appleinsider.com": "AppleInsider",
             "techcrunch.com": "TechCrunch", "wired.com": "WIRED", "cnet.com": "CNET", "tomsguide.com": "Tom's Guide"}
    return known.get(host, host.split(".")[0].capitalize())


def make_article():
    p = plan_article()
    t0 = anchor_time(p.get("anchor"))
    if t0 is None:
        say("   anchor line not found in the transcript: placing the card on the first mention of the headline's key word")
        key = [norm(x) for x in (p["highlight"][0] if p.get("highlight") else "").split() if len(norm(x)) > 4]
        t0 = next((w["s"] for w in words if norm(w["w"]) in key and any(s <= w["s"] <= e for s, e in keep)), keep[0][0] + 10)
    proj_dir = out_dir / "article"
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    (proj_dir / "assets" / "fonts").mkdir(parents=True)
    shutil.copy(KIT / "gsap.min.js", proj_dir / "assets")
    shutil.copy(KIT / "fonts" / "Inter.ttf", proj_dir / "assets" / "fonts")
    shutil.copy(KIT / "hyperframes.json", proj_dir)
    (proj_dir / "package.json").write_text(json.dumps({"name": "article", "private": True, "type": "module"}), encoding="utf-8")
    info = capture(p["url"], p.get("highlight") or [])
    card_h, groups = build_card(info)
    if not groups:
        say("   none of the phrases are on the page: the card shows the article without a marker")
    html, dur = article_html(card_h, groups)
    (proj_dir / "index.html").write_text(html.replace("{SOURCE}", source_name(p["url"])), encoding="utf-8")
    say("== render (HyperFrames)")
    r = subprocess.run(f"{HF} render --quiet --quality standard -o renders/article.mp4", cwd=proj_dir, shell=True,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    mp4 = proj_dir / "renders" / "article.mp4"
    if r.returncode or not mp4.exists():
        raise SystemExit("HyperFrames render failed:\n" + (r.stdout + r.stderr)[-2000:])
    # start a beat before the anchor line so the card is up as the claim is said
    return {"type": "article", "file": str(mp4), "raw": round(max(keep[0][0], t0 - 0.25), 3), "dur": dur,
            "url": p["url"], "highlight": p.get("highlight"), "marked": len(groups), "anchor": p.get("anchor")}


MAKERS = {"article": make_article}
kind = G.get("type") or "article"
if kind not in MAKERS:
    raise SystemExit(f"unknown motion graphic type {kind!r} (have: {', '.join(MAKERS)})")
item = MAKERS[kind]()
(out_dir / "graphics.json").write_text(json.dumps({"items": [item]}, indent=1), encoding="utf-8")
say(f"wrote {out_dir / 'graphics.json'}: {kind} at raw {item['raw']:.1f}s for {item['dur']}s")
