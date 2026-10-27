"""Render every template (or some) on its type's demo VO and rebuild the browsable gallery.

    python make_gallery.py                 all templates, skip ones whose preview is newer than the template files
    python make_gallery.py R01 P03 G09     just these (always re-rendered)
    python make_gallery.py --page          only rewrite gallery/index.html
Outputs: gallery/previews/<ID>.mp4 (960x540 H.264 preview with sound), gallery/posters/<ID>.jpg (4-moment strip), gallery/index.html
"""
import json, os, subprocess, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_intro as B  # noqa: E402

AUD = r"{{VO_FOLDER}}"
DEMO = {
    "review": {"vo": AUD + "/dhgate moncler.wav", "title": "DHGATE MONCLER", "sub": "Scam or steal?", "footage": os.path.join(HERE, "_work", "moncler-broll.json"),
               "music": r"{{MUSIC_ROOT}}/Type Beats/Drake/[FREE] Drake x Iceman Type Beat - ''Name''.mp3"},
    "phone": {"vo": AUD + "/doordash test.wav", "title": "DOORDASH", "sub": "", "footage": os.path.join(HERE, "_work", "doordash-footage.json"), "music": r"{{MUSIC_ROOT}}/Type Beats/Drake/Drake Type Beat - Family Matters (ECHOBEATS).mp3"},
    "gaming": {"vo": AUD + "/top 10 servers october.wav", "title": "TOP 10 SERVERS", "sub": "UNDERRATED", "footage": None,
               "music": r"{{KIT}}/assets/Graphics/HyperFrames/servers-intro-oct/assets/music-ultrashooters.mp3"},
}
GAL = os.path.join(HERE, "gallery")
TYPE_NAME = {"gaming": "Gaming · {{GAMING_CHANNEL}}", "phone": "Phone / app codes · {{PHONE_CHANNEL}}", "review": "Product review · {{REVIEW_CHANNEL}}"}


def newest(d):
    return max(os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)


def render_one(t):
    d = DEMO[t["type"]]
    out = os.path.join(HERE, "_work", "demo", f"{t['type']}-{t['id']}")
    os.makedirs(out, exist_ok=True)
    B.build(t["type"], t["id"], d["vo"], d["title"], out, d["sub"], d["footage"], d["music"])
    mp4 = B.render_project(out, "looks")
    for sub in ("previews", "posters"):
        os.makedirs(os.path.join(GAL, sub), exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4], capture_output=True, text=True).stdout)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", "scale=960:540", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "26",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", os.path.join(GAL, "previews", t["id"] + ".mp4")], check=True)
    # poster: four moments (hook, problem, reveal, title) side by side
    ts = [dur * f for f in (0.08, 0.35, 0.68, 0.94)]
    ins = sum([["-ss", f"{x:.2f}", "-i", mp4] for x in ts], [])
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins + ["-filter_complex", "".join(f"[{i}:v]scale=480:270[v{i}];" for i in range(4)) +
                    "[v0][v1][v2][v3]hstack=4", "-frames:v", "1", "-q:v", "4", os.path.join(GAL, "posters", t["id"] + ".jpg")], check=True)
    meta = {"dur": round(dur, 1), "out": out}
    json.dump(meta, open(os.path.join(GAL, "previews", t["id"] + ".json"), "w"))
    print("gallery:", t["id"], round(dur, 1), "s")


def page():
    ts = B.templates()
    cards = {}
    for t in ts:
        if not os.path.exists(os.path.join(GAL, "previews", t["id"] + ".mp4")):
            continue
        cards.setdefault(t["type"], []).append(t)
    sec = []
    for k in ("review", "phone", "gaming"):
        items = cards.get(k, [])
        cs = "".join(f"""
      <article class="card" id="{t['id']}">
        <video src="previews/{t['id']}.mp4" poster="posters/{t['id']}.jpg" controls preload="none" playsinline></video>
        <div class="meta"><span class="id">{t['id']}</span><h3>{html.escape(t.get('name', ''))}</h3></div>
        <p>{html.escape(t.get('blurb', ''))}</p>
        <code>python build_intro.py --type {k} --template {t['id']} --vo &lt;vo.wav&gt; --title "..." --out &lt;dir&gt; --render</code>
      </article>""" for t in items)
        sec.append(f'<section><h2>{TYPE_NAME[k]} <small>{len(items)} / 20</small></h2><div class="grid">{cs}</div></section>')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Intro Library</title>
<style>
:root {{ --bg:#0e0f12; --card:#17191e; --ink:#eef0f4; --mute:#9aa0ab; --acc:#3dff7a; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 "Segoe UI",system-ui,sans-serif; }}
header {{ padding:28px 24px 8px; max-width:1500px; margin:auto; }} h1 {{ margin:0; font-size:28px; }} header p {{ color:var(--mute); margin:6px 0 0; }}
section {{ max-width:1500px; margin:auto; padding:10px 24px 30px; }} h2 {{ font-size:20px; border-bottom:1px solid #2a2d35; padding-bottom:8px; }} h2 small {{ color:var(--mute); font-weight:400; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:18px; }}
.card {{ background:var(--card); border-radius:14px; overflow:hidden; border:1px solid #23262e; }}
.card video {{ width:100%; aspect-ratio:16/9; display:block; background:#000; }}
.meta {{ display:flex; gap:10px; align-items:center; padding:12px 14px 0; }} .meta h3 {{ margin:0; font-size:17px; }}
.id {{ background:var(--acc); color:#000; font-weight:800; border-radius:6px; padding:1px 8px; font-size:13px; }}
.card p {{ color:var(--mute); margin:8px 14px; font-size:14px; }} code {{ display:block; margin:0 14px 14px; color:#7fd3ff; font-size:11.5px; word-break:break-all; }}
@media (max-width:520px) {{ .grid {{ grid-template-columns:1fr; }} header, section {{ padding-left:16px; padding-right:16px; }} }}
</style></head><body>
<header><h1>Intro Library</h1><p>Each template shown on its type's demo VO (review: the Moncler VO + Moncler B-roll; phone: DoorDash test VO; gaming: Top 10 Servers VO with labelled gameplay slots). Every template re-times itself to any new VO.</p></header>
{''.join(sec)}
</body></html>"""
    open(os.path.join(GAL, "index.html"), "w", encoding="utf-8").write(doc)
    print("page:", os.path.join(GAL, "index.html"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--page" not in sys.argv:
        for t in B.templates():
            if args and t["id"] not in args:
                continue
            pv = os.path.join(GAL, "previews", t["id"] + ".mp4")
            if not args and os.path.exists(pv) and os.path.getmtime(pv) > max(newest(t["dir"]), os.path.getmtime(os.path.join(HERE, "kit", "kit.js"))):
                continue
            try:
                render_one(t)
            except SystemExit as e:
                print("FAILED", t["id"], e)
    page()
