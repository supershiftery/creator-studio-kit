"""Product-review Shorts from a finished review (user 2026-10-23: "Can I get product review shorts? ... lets try on spp5der
hoodie video main video and bake this into your studio").   python review_shorts.py <project> [--n 3] [--render <mp4>]

The look, from the user's 3 references (TikTok, studied 2026-10-23):
- unoakaoneway_ (Blue Band AP watch, 29 s): product pushed close to the lens in hand, cuts every ~2 s between the product
  and him talking, a small fixed text tag at the top.
- cedaz_ (23 s): talking head with glowing neon graphics on top; split screen (face top, website bottom) for the page.
- credcal (Yeezy NSLTD boots, 19.5 s): cuts every ~1.2 s, detail close-ups, big green product title for the first 3 s,
  a blue name pill, small white ALL-CAPS captions, "LINK IN MY BIO" at the end.
So: 20-40 s, built from the review's best lines (hook -> details / try-on -> price / verdict), a punch-in or cut every
1-2 s, green product title + blue pill up top for the first ~3 s, short caps captions, a "LINK IN BIO" close.

1. Words of the render itself (tools/transcribe_render.py) -> lines (sentences) with render times.
2. Plan: claude_brain task "review_shorts" (Claude) picks N Shorts, each 3-7 line ranges in story order, a title
   (product, 2-4 words), a pill (e.g. "DHGATE $45"), a file name. Cached in Shorts/plan.json on the transcript.
3. Picture: every sentence is a clip; each clip is classified from a frame (MediaPipe face landmarker + page whiteness):
   camera = a steady 9:16 crop centred on the biggest face (centre when none), alternating 1.0 / 1.12 punch-in per
   sentence for the fast pace; screen (website, spreadsheet) = the page fitted to the width on a blurred copy of itself.
   1080x1920 30 fps (the render's rate), lanczos + light sharpen.
4. Captions (preset "pop_v": Poppins Black caps, green spoken word), title + pill (0-3.2 s), "LINK IN BIO" (last 2.5 s).
   Audio = the render's own mix (voice + music), 30 ms fades at every join, -14 LUFS / -1 dBTP (the Shorts exception),
   H.264 High yuv420p + AAC. Output: <project>/Shorts/<nn> <name>.mp4 + .txt (title, description, link back), so they
   list in Studio's Shorts tab.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
sys.path.insert(0, r"{{KIT}}/tools")
import captions as CAPS   # noqa: E402

proj = Path(sys.argv[1])
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings") or {}
out_dir = proj / "Shorts"
work = out_dir / "_work"
work.mkdir(parents=True, exist_ok=True)
W, H, FPS = 1080, 1920, 30
FM = r"{{KIT}}/review_pipeline/models/face_landmarker.task"


def say(*a):
    print(*a, flush=True)


if "--render" in sys.argv:
    render = Path(sys.argv[sys.argv.index("--render") + 1])
else:
    cands = [proj / "output" / "final_intro.mp4", proj / "output" / "final.mp4"] + sorted(proj.glob("output/*DRAFT*.mp4"))
    render = next((c for c in cands if c.exists()), None)
if not render or not render.exists():
    sys.exit("no finished render to cut Shorts from (output/final_intro.mp4 or final.mp4)")
say(f"render: {render.name}")


def probe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


R_DUR = probe_dur(render)

# ---- 1. words of the render
words_p = work / f"words_{render.stem}.json"
subprocess.run([sys.executable, "-X", "utf8", str(APP / "tools" / "transcribe_render.py"), str(render), str(words_p)], check=True)
words = json.loads(words_p.read_text(encoding="utf-8"))
words = words["words"] if isinstance(words, dict) else words
words = [{"w": (w.get("w") or w.get("word") or "").strip(), "s": float(w.get("s", w.get("start", 0))), "e": float(w.get("e", w.get("end", 0)))}
         for w in words]
words = [w for w in words if w["w"]]
L, cur = [], []
for i, w in enumerate(words):
    cur.append(w)
    gap = words[i + 1]["s"] - w["e"] if i + 1 < len(words) else 9
    if re.search(r"[.?!]$", w["w"]) or gap > 0.7 or len(cur) > 22:
        L.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur), "words": cur})
        cur = []
say(f"{len(L)} lines in {R_DUR / 60:.1f} min")

# ---- 2. plan
plan_p = out_dir / "plan.json"
key = hashlib.md5(json.dumps([[round(x["s"], 1), x["text"]] for x in L] + [N, "v2"]).encode()).hexdigest()
plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
if plan.get("key") != key:
    import claude_brain as B
    text = "\n".join(f"L{i} [{x['s']:.1f}-{x['e']:.1f}] {x['text']}" for i, x in enumerate(L))
    prompt = f"""This is the transcript of a finished YouTube PRODUCT REVIEW ("{doc.get('title', proj.name)}"), one line per sentence
with its time in the video. Cut it into {N} different vertical Shorts (TikTok / YouTube Shorts) in the fast product-review
style: hook first, then the best details / try-on / quality points, then the price or the verdict.

{text}

For each Short choose 3-7 SEGMENTS, each a range of whole lines (first and last line id, inclusive), in story order, total
20-40 seconds. The FIRST segment must be a hook that works with no context (a bold claim, a question, a surprise, a
price) said while he is ON CAMERA (holding / wearing the product, not reading a website). At most ONE short segment
(<= 5 s) may be while a website / spreadsheet is on screen, and only for the price. Prefer lines about how it looks, fits, feels, quality, price, where to buy. Skip greetings, "subscribe", sponsor
talk, anything that only makes sense while a website is on screen (unless it says the price), and lines that end
mid-thought. Each Short should feel complete. The {N} Shorts should use mostly different lines.
- title: the product in 2-4 words, CAPS (e.g. "SP5DER HOODIE"); pill: 1-3 words shown in a small tag (e.g. "DHGATE $45",
  "WORTH IT?"); name: a short file name (3-5 words); caption: a TikTok caption line (no hashtags).
Reply with ONLY JSON: {{"shorts": [{{"segments": [[<first line>, <last line>], ...], "title": "...", "pill": "...",
"name": "...", "caption": "..."}}]}}"""
    ans = B.ask("review_shorts", prompt, say=say) or {}
    shorts = []
    for sh in ans.get("shorts") or []:
        segs = []
        for sg in sh.get("segments") or []:
            try:
                a, b = int(str(sg[0]).lstrip("L")), int(str(sg[1]).lstrip("L"))
            except (TypeError, ValueError, IndexError):
                continue
            if 0 <= a <= b < len(L):
                segs.append([a, b])
        if segs:
            shorts.append({**{k: str(sh.get(k) or "")[:60] for k in ("title", "pill", "name", "caption")}, "segments": segs})
    plan = {"key": key, "shorts": shorts[:N]}
    plan_p.write_text(json.dumps(plan, indent=1), encoding="utf-8")
if not plan["shorts"]:
    sys.exit("the planner chose no Shorts")

# ---- 3. clip classification (one frame per sentence)
lm = None
try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=FM), num_faces=3))
except Exception as ex:  # noqa: no face finder -> centre crops
    say(f"face finder unavailable ({type(ex).__name__}): centre crops")
look_cache = {}


def look(t):
    """-> ("camera", cx, cy) | ("screen", None, None) for the render frame at t (1920x1080)"""
    k = round(t, 1)
    if k in look_cache:
        return look_cache[k]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(render), "-frames:v", "1", "-vf", "scale=960:540",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    res = ("camera", 960.0, 540.0)
    if len(raw) == 960 * 540 * 3:
        img = np.frombuffer(raw, np.uint8).reshape(540, 960, 3)
        grey = img.mean(2)
        white = float((grey > 225).mean())
        f_ = img.astype(np.float32) / 255
        mx, mn = f_.max(2), f_.min(2)
        sat = float(np.where(mx > 0.05, (mx - mn) / np.maximum(mx, 1e-6), 0).mean())
        faces = []
        if lm is not None:
            r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img.copy()))
            for f in r.face_landmarks or []:
                xs, ys = [q.x for q in f], [q.y for q in f]
                faces.append(((min(xs) + max(xs)) / 2 * 1920, (min(ys) + max(ys)) / 2 * 1080, (max(ys) - min(ys)) * 1080))
        big = [f for f in faces if f[2] > 1080 * 0.13]
        # a page: lots of white, or only the small face-cam circle (top-left) on a busy frame
        # a page: lots of white; or grey (dark UI pages: the link list / spreadsheet in the Sp5der review measured saturation
        # 0.08-0.14, his purple-lit room 0.47-0.86) with no big face; or only the small face-cam circle at the top left
        if white > 0.22 or (not big and sat < 0.25) or (faces and not big and all(f[0] < 520 and f[1] < 420 for f in faces)):
            res = ("screen", None, None)
        elif big:
            f = max(big, key=lambda f: f[2])
            res = ("camera", f[0], f[1])
    look_cache[k] = res
    return res


def crop_at(cx, cy, zoom):
    cw, ch = 1080 * 9 / 16 / zoom, 1080 / zoom
    x = min(max(cx - cw / 2, 0), 1920 - cw)
    # punched in: the face stays at ~35 % from the top (the first build cut the top of his head off); no face: centre
    y = 0 if zoom <= 1 else min(max((cy - ch * 0.35) if cy is not None else (1080 - ch) / 2, 0), 1080 - ch)
    return f"crop={cw:.0f}:{ch:.0f}:{x:.0f}:{y:.0f},scale={W}:{H}:flags=lanczos"


def clip_vf(kind, cx, cy, zoom, flips=()):
    """camera: steady crop on the face, punched in 1.12x during `flips` (clip-time ranges): a picture change every ~1.6 s
    like the references (credcal cuts every ~1.2 s)"""
    if kind == "camera":
        base = f"split[p0][p1];[p0]{crop_at(cx, cy, 1.0)}[c0];[p1]{crop_at(cx, cy, 1.12)}[c1];"
        en = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in flips) or "0"
        return base + f"[c0][c1]overlay=0:0:enable='{en}',unsharp=5:5:0.6:5:5:0.0,setsar=1,fps={FPS},format=yuv420p"
    if kind == "screen":   # the page fitted to the width on a blurred copy; punched in 1.35x on the page centre during `flips`
        en = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in flips) or "0"
        return (f"split=3[a][b][z];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,eq=brightness=-0.12[bg];"
                f"[b]scale={W}:-2:flags=lanczos[fg];[z]crop=iw/1.35:ih/1.35,scale={W}:-2:flags=lanczos[fz];"
                f"[bg][fg]overlay=0:(H-h)/2-60[s1];[s1][fz]overlay=0:(H-h)/2-60:enable='{en}',setsar=1,fps={FPS},format=yuv420p")
    cw, ch = 1080 * 9 / 16 / zoom, 1080 / zoom
    x = min(max(cx - cw / 2, 0), 1920 - cw)
    y = min(max(cy - ch * 0.42, 0), 1080 - ch) if zoom > 1 else 0
    return (f"crop={cw:.0f}:{ch:.0f}:{x:.0f}:{y:.0f},scale={W}:{H}:flags=lanczos,unsharp=5:5:0.6:5:5:0.0,setsar=1,"
            f"fps={FPS},format=yuv420p")


# ---- 4. build each Short
CAPS.PRESETS.setdefault("pop_v", {"label": "Pop vertical · Poppins Black caps", "fonts": [("Poppins Black", 0), ("Anton", 0)],
                                  "size": 100 / 1920, "color": "FFFFFF", "outline": 10 / 1920, "shadow": 3 / 1920, "caps": True,
                                  "words": 3, "chars": 13, "hl": "7CFF4F", "margin": .30, "pop": 108})
made = []
for si, sh in enumerate(plan["shorts"]):
    name = re.sub(r'[<>:"/\\|?*]', "", sh["name"] or f"short {si + 1}").strip()[:50]
    out = out_dir / f"{si + 1:02d} {name}.mp4"
    clips, t_out, ewords = [], 0.0, []
    for a, b in sh["segments"]:
        for li in range(a, b + 1):
            ln = L[li]
            # the clip runs from just before the first word to just after the last (into the next pause, max 0.25 s)
            s0 = max(0.0, ln["s"] - 0.08)
            nxt = L[li + 1]["s"] if li + 1 < len(L) else R_DUR
            e0 = min(ln["e"] + 0.25, (ln["e"] + nxt) / 2 if nxt > ln["e"] else ln["e"] + 0.1, R_DUR)
            clips.append({"s": s0, "e": e0, "line": li, "seg": (a, b), "pic": None})
    for c in clips:
        c["kind"], c["cx"], c["cy"] = look((c["s"] + c["e"]) / 2)
    # at most ~6 s of website / spreadsheet per Short (Sp5der test: the planner put 9 s of the DHgate page in Short 1 although
    # told <= 5 s). Dropping the sentences lost the price and left a sentence starting mid-phrase, so the words STAY and the
    # extra screen sentences play over the nearest on-camera moment of the review instead (the price said over the hoodie,
    # like credcal talks over his close-ups); a picture already used in this Short is never taken twice.
    used_pic = [(c["s"], c["e"]) for c in clips if c["kind"] == "camera"]
    budget = 6.0
    for c in clips:
        if c["kind"] != "screen":
            continue
        d = c["e"] - c["s"]
        if budget >= d:
            budget -= d
            continue
        best = None
        for off in sorted([x * 1.0 for x in range(-60, 61, 2)], key=abs):
            t0 = c["s"] + off
            if t0 < 0 or t0 + d > R_DUR or any(t0 < b_ and a_ < t0 + d for a_, b_ in used_pic):
                continue
            k_, x_, y_ = look(t0 + d / 2)
            if k_ == "camera" and look(t0 + 0.2)[0] == "camera":
                best = (t0, x_, y_)
                break
        if best:
            c["pic"], c["kind"], c["cx"], c["cy"] = best[0], "camera", best[1], best[2]
            used_pic.append((best[0], best[0] + d))
            say(f"   short {si + 1}: L{c['line']} (screen) plays over the camera at {best[0] // 60:.0f}:{best[0] % 60:04.1f}")
    for k, c in enumerate(clips):
        kind, cx, cy = c["kind"], c["cx"], c["cy"]
        c.update(cx=cx if cx is not None else 960.0, zoom=1.0)
        # punch-in flips inside the clip: every other ~1.6 s stretch, cut on a word gap
        bounds, last = [c["s"]], c["s"]
        lw = [w for w in L[c["line"]]["words"] if c["s"] <= w["s"] < c["e"]]
        for x_, y_ in zip(lw, lw[1:]):
            g = (x_["e"] + y_["s"]) / 2
            if g - last >= 1.4 and c["e"] - g >= 0.8:
                bounds.append(g)
                last = g
        bounds.append(c["e"])
        start_in = (k % 2 == 1)   # alternate the starting framing from clip to clip so every join changes the picture
        c["flips"] = [(a - c["s"], b - c["s"]) for j, (a, b) in enumerate(zip(bounds, bounds[1:])) if (j % 2 == 1) != start_in]
        for w in L[c["line"]]["words"]:
            if c["s"] <= w["s"] < c["e"]:
                ewords.append({"w": w["w"], "s": t_out + w["s"] - c["s"], "e": t_out + min(w["e"], c["e"]) - c["s"]})
        c["t"] = t_out
        t_out += c["e"] - c["s"]
    total = t_out
    parts = []
    for k, c in enumerate(clips):
        pf = work / f"s{si}_{k:02d}.mp4"
        d = c["e"] - c["s"]
        pic_t = c["pic"] if c.get("pic") is not None else c["s"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{pic_t:.3f}", "-t", f"{d:.3f}", "-i", str(render),
                        "-ss", f"{c['s']:.3f}", "-t", f"{d:.3f}", "-i", str(render),
                        "-filter_complex", f"[0:v]{clip_vf(c['kind'], c['cx'], c['cy'], c['zoom'], c['flips'])}[v];"
                                           f"[1:a]afade=t=in:st=0:d=0.03,afade=t=out:st={max(0, d - 0.03):.3f}:d=0.03,aresample=48000[a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "16", "-c:a", "pcm_s16le",
                        str(pf.with_suffix(".mov"))], check=True)
        parts.append(pf.with_suffix(".mov"))
    lst = work / f"s{si}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    joined = work / f"s{si}_joined.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)

    # captions + title / pill (first 3.2 s) + LINK IN BIO (last 2.5 s)
    ass = CAPS.build_ass(ewords, W, H, "pop_v")
    lines_ = ass.splitlines()
    k0 = next(i for i, ln in enumerate(lines_) if ln.startswith("[Events]"))
    fam = CAPS.font_for("pop_v")[0]
    extra_styles = [
        f"Style: Title,{fam},150,&H004FFF7C,&H004FFF7C,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,10,5,8,50,50,250,1",
        f"Style: Pill,{fam},64,&H00FFFFFF,&H00FFFFFF,&H00E8862B,&H00E8862B,-1,0,0,0,100,100,0,0,3,16,0,8,60,60,450,1",
        f"Style: Cta,{fam},96,&H004FFF7C,&H004FFF7C,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,4,8,60,60,330,1",
    ]
    tt = min(3.2, total)
    ev = [f"Dialogue: 2,{CAPS._t(0)},{CAPS._t(tt)},Title,,0,0,0,,{{\\fad(80,150)}}{sh['title'].upper()}"]
    if sh.get("pill"):
        ev.append(f"Dialogue: 2,{CAPS._t(0.15)},{CAPS._t(tt)},Pill,,0,0,0,,{{\\fad(80,150)}}{sh['pill'].upper()}")
    ev.append(f"Dialogue: 2,{CAPS._t(max(0, total - 2.5))},{CAPS._t(total)},Cta,,0,0,0,,{{\\fad(120,0)}}LINK IN BIO")
    # style lines go before [Events]; the extra dialogue after the caption events
    lines_ = lines_[:k0] + extra_styles + lines_[k0:] + ev
    ass_p = work / f"s{si}.ass"
    ass_p.write_text("\n".join(lines_) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-vf", CAPS._filt(ass_p) + ",format=yuv420p",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.84:level=false",
                    "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "17",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True, cwd=str(work))
    cams = sum(c["kind"] == "camera" for c in clips)
    say(f"short {si + 1}: '{sh['title']}' {total:.1f} s, {len(clips)} clips ({cams} camera / {len(clips) - cams} screen), "
        f"segments {sh['segments']} -> {out.name}")
    (out.with_suffix(".txt")).write_text(
        f"{sh['title']}\n\n{sh.get('caption', '')}\n\nFull review: {doc.get('title', proj.name)} (link the long video / Related video)\n",
        encoding="utf-8")
    made.append({"file": str(out), "dur": round(total, 2), "title": sh["title"], "pill": sh.get("pill"), "segments": sh["segments"]})
(out_dir / "shorts.json").write_text(json.dumps({"render": str(render), "shorts": made}, indent=1), encoding="utf-8")
say(f"wrote {len(made)} Shorts to {out_dir}")
