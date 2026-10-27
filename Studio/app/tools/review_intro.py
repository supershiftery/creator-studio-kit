"""Product review intro (2026-10-21, user: "these videos can accept intro... flexible for all videos"): after edit_review.py.
    python review_intro.py <project dir>
- the project's intro slot holds a VO (wav/mp3/m4a): build a motion-graphics intro with the intro library (build_intro.py
  --type review, liked templates R01 Smoke Words / R02 Grid Notebook), its footage slots filled with the product camera
  (RIGHT half of the 3840x1080 recording) from kept parts of the review section, then render it
- the intro slot holds a finished MP4: use it as is
- then intro + output/final.mp4 -> output/final_intro.mp4 (+ preview_intro_540p.mp4), the same join as the phone pipeline
No intro in the project = nothing to do. A failed intro never fails the edit: the draft without intro stays, the reason goes
to output/intro_report.txt."""
import json
import shutil
import os
import re
import subprocess
import sys
import traceback
import urllib.parse
from pathlib import Path

PROJ = Path(sys.argv[1])
OUT = PROJ / "output"
LIB = Path(r"{{KIT}}/tools\intro_library")
# screenrec re-records any cached page another video already used (top 5 products to resell in winter 2024, 0:18)
os.environ["SCREENREC_PROJECT"] = PROJ.name
JOIN = Path(r"{{KIT}}/tools\phone_edit\join.py")
PY = sys.executable
AUDIO = (".wav", ".mp3", ".m4a", ".aac", ".flac")
# Intro styles ROTATE across videos (user 2026-10-22: "I don't want to use the same type of intro every single time ... it becomes
# formulaic"). build_intro --template auto = least-recently-used review template (_state/rotation.json in the library); the liked
# ones go first in the very first cycle: R02 Grid Notebook, then R01 Smoke Words, then the rest.
FIRST_CYCLE = ["R02", "R01"]


def say(m):
    print(m, flush=True)


def stale(out, *ins):
    return not out.exists() or any(Path(i).exists() and Path(i).stat().st_mtime > out.stat().st_mtime for i in ins if i)


def keep_ranges():
    d = json.loads((PROJ / "work" / "cuts.json").read_text(encoding="utf-8")) if (PROJ / "work" / "cuts.json").exists() else None
    if isinstance(d, dict):
        return [tuple(x[:2]) for x in (d.get("keep") or d.get("kept") or [])]
    return [tuple(x[:2]) for x in (d or [])]


VIDEO = (".mp4", ".mov", ".m4v", ".mkv", ".webm")


def handled_span(p, dur, fps=5):
    """(start, end) of the part of a phone clip that is the product, not his hand on the phone: the motion at the start
    and end of a phone recording spikes when he presses record / picks the phone up (blurry floor, rug, ceiling).
    Motion = mean frame difference at 64x36; a spike = over max(25, 4x the clip's median) in the first / last 40 %."""
    import numpy as np
    a, b = 0.5, max(0.5, dur - 0.5)
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vf", f"fps={fps},scale=64:36,format=gray",
                            "-f", "rawvideo", "-"], capture_output=True, timeout=120)
        fr = np.frombuffer(r.stdout, np.uint8)
        fr = fr[:len(fr) // 2304 * 2304].reshape(-1, 36, 64).astype(np.float32)
        d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return a, b
    if len(d) < 10:
        return a, b
    thr = max(25.0, 4 * float(np.median(d)))
    n = len(d)
    head = [i for i in range(int(n * 0.4)) if d[i] > thr]
    tail = [i for i in range(int(n * 0.6), n) if d[i] > thr]
    if head:
        a = max(a, (head[-1] + 1) / fps + 0.4)
    if tail:
        b = min(b, tail[0] / fps - 0.4)
    return a, b


def own_broll(doc, n_max=8, step=3.2, per_clip=4):
    """His own B-roll clips (project slots / raw/broll) come FIRST: they are the real product, shot to be shown (dhgate
    cartier watch 2026-10-22, 0:08: "me just talking but I'm not talking, like lip syncing ... utilize the B-roll I gave
    you"). Several moments per clip, so a long turntable spin feeds more than one line."""
    files = [Path(p) for p in (doc.get("slots", {}).get("broll") or []) if Path(p).suffix.lower() in VIDEO and Path(p).exists()]
    files += [p for p in sorted((PROJ / "raw" / "broll").glob("*")) if p.suffix.lower() in VIDEO and p not in files] \
        if (PROJ / "raw" / "broll").is_dir() else []
    # clips he dropped ("use": false in raw/broll.json) stay out of the intro too: s25 ultra round 2, the front-camera test he
    # said not to use filled two intro beats with an extreme close-up of his eyes
    try:
        # ...and the demo clips that play as a cutaway WITH their sound ("insert": true, the camera test): a room / fridge
        # walk-through is not product footage (s25 ultra 0:16-0:19 "surprised" over a desk clock and a room)
        dropped = {Path(m["file"]).name.lower() for m in json.loads((PROJ / "raw" / "broll.json").read_text(encoding="utf-8"))
                   if m.get("use") is False or m.get("insert")}
    except (OSError, ValueError, KeyError):
        dropped = set()
    files = [p for p in files if p.name.lower() not in dropped]
    out = []
    for p in files:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                            "-of", "json", str(p)], capture_output=True, text=True)
        try:
            info = json.loads(r.stdout)
            dur = float(info["format"]["duration"])
            st = (info.get("streams") or [{}])[0]
        except (ValueError, KeyError):
            continue
        # a two-camera side-by-side recording (3840x1080) is never B-roll: it is a part of the recording (lv trainer
        # 2026-10-23: the continuation sat in raw/broll and showed both halves at 0:13, "no one should ever know my video
        # is split in two")
        if st.get("width") and st.get("height") and st["width"] / st["height"] >= 2.5:
            continue
        # never his hands starting / stopping the recording: the head and tail of a phone clip where he grabs the phone
        # (dhgate lanvins 2026-10-26, 0:20: the intro used IMG_0468 at 30.5 s = him picking the camera up, "anything would
        # be better than picking up the camera and not really showing it"). Measured, not a fixed trim.
        a, b = handled_span(p, dur)
        span = b - a
        if span < 2.0:
            continue
        k = max(1, min(per_clip, int((span - 0.5) // step)))
        out += [{"src": str(p), "t": round(a + j * (span - 2.6) / max(1, k - 1), 2) if k > 1 else round(a, 2), "tag": "product", "kind": "broll", "own": True}
                for j in range(k)]
    # interleave the clips (clip A, clip B, clip A ...) so two lines in a row never show the same spin
    by = {}
    for f in out:
        by.setdefault(f["src"], []).append(f)
    mixed = [f for grp in zip(*[iter(v) for v in by.values()]) for f in grp] if len(by) > 1 else out
    mixed += [f for f in out if f not in mixed]
    # one KIND of own clip (every clip a turntable spin) feeds at most 3 lines: 8 spin moments filled the whole first 8 s
    # of the jordan 3 intro (2026-10-23, "the videos of the B-roll from like 0:08 ... we just have to try something
    # different"); the rest comes from the product camera, real pages and pictures
    try:
        kinds = {e.get("file", "").lower(): e.get("kind") for e in json.loads((PROJ / "raw" / "broll.json").read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        kinds = {}
    ks = {kinds.get(Path(f["src"]).name.lower()) for f in mixed}
    if len(ks) == 1 and None not in ks:
        n_max = min(n_max, OWN_SAME_KIND_MAX)
    return mixed[:n_max]


def footage(src, doc=None):
    """His own B-roll first, then product-camera moments (right half, hands + product, no face) from kept review/showcase
    footage, then the store page. NEVER the talking camera: a muted shot of him talking reads as lip-sync."""
    secs = json.loads((PROJ / "work" / "sections.json").read_text(encoding="utf-8"))["sections"]
    rev = [s for s in secs if s["name"] in ("review", "showcase")]
    if not rev:
        return own_broll(doc or {}) + screen_footage(src)
    # at most 2 moments of each of his own clips when the product camera has footage too (lv skatesta 2026-10-24: one
    # turntable spin filled 6 of 11 intro shots, "you can see how the motion, everything's moving ... there's still more
    # things you could have done")
    own = own_broll(doc or {}, per_clip=2)
    keep = [(max(x, s["start"]), min(y, s["end"])) for s in rev for x, y in keep_ranges()
            if y > s["start"] and x < s["end"] and min(y, s["end"]) - max(x, s["start"]) >= 4.5]
    # only where the right half really shows the product AND no face (dhgate asics 2026-10-22: "comments about my ASICS"
    # showed his face). Rows are ~1 s apart: the old 0.25 s join tolerance never joined two rows, so there were no product
    # runs at all and the whole talking review section was used (dhgate cartier watch, lip-sync at 0:08).
    try:
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    step = min((b["t"] - a["t"] for a, b in zip(rows, rows[1:]) if b["t"] > a["t"]), default=1.0)
    runs = []
    for r in rows:
        # ...and only while he SITS at the desk, his face on Camera A: standing up in the jacket, the product camera films
        # his torso with no face either (top 5 products to resell in winter 2024, 0:22: "this clip of me just being on a side
        # angle makes no sense"; the same 423 s moment filled four slots)
        if r.get("right") == "product" and r.get("left") != "screen" and r.get("rfx") is None and r.get("fx") is not None:
            if runs and r["t"] - runs[-1][1] <= step * 1.5 + 0.01:
                runs[-1][1] = r["t"]
            else:
                runs.append([r["t"], r["t"]])
    keep = [(max(x, c), min(y, d)) for x, y in keep for c, d in runs if min(y, d) - max(x, c) >= 4.5]
    total = sum(y - x for x, y in keep)
    cam = []
    n = 6 if keep else 0
    for k in range(n):
        want, acc = total * (k + 0.5) / n, 0.0
        for x, y in keep:
            if acc + (y - x) >= want:
                t = min(x + (want - acc), y - 4.2)
                cam.append({"src": str(src), "t": round(max(x, t), 2), "crop": "right", "tag": "product", "kind": "broll"})
                break
            acc += y - x
    vo_text = vo_words_text(doc)
    # a TOPIC video that names several products (reselling: "AirPods, Spider Hoodies, and even cologne") has no one product:
    # him holding some item up to the talking camera is just his face on screen ($30k reselling 2026-10-26, 0:25: "I don't
    # know why I show up there"). The hold-up exception to "never the talking camera" is for single-product reviews.
    cam = ([] if multi_product(vo_text) else holdup_moments()) + show_moments(keep) + cam
    creators = creator_footage(vo_text, doc or {})
    web = (retail_footage(vo_text, doc or {}) + product_web_footage(vo_text, product_query(doc or {})))[:2]   # max 2 pages (jordan 3)
    # "influencers claiming the best link for Prada sunglasses" ALWAYS gets the YouTube search of that product, whatever
    # else covers the word (remote test prada 2026-10-26, 0:17: "you should've typed the video title into YouTube and then
    # scroll ... the best Prada sunglasses on DHgate"; the StockX + retail pages had used up the 2-page cap)
    m_who = re.search(WEB_FOR[0][0] + "|" + WEB_FOR[1][0], vo_text or "", re.I)
    who_product = _who_product(vo_text, m_who) if m_who and os.environ.get("RG_OFF") != "whoproduct" else None
    if who_product:
        web += web_footage(vo_text, n_max=1)
    # real creator clips replace the YouTube-search scrolls for the same words: two searches look like one scroll shown again
    # (reselling spreadsheet 2026-10-23); with creator clips at most one search scroll stays
    covered = {w for f in web + creators for w in f["for"]}
    # up to 3 searches now that each is a DIFFERENT query from a rotating bank (web_footage), not the same scroll again
    web += web_footage(vo_text, n_max=max(0, (1 if creators else 3) - len(web)), skip=covered)
    topic = topic_screen_footage(src, vo_text)
    # a screen-walkthrough video (spreadsheets, store pages) has no product camera: fill the rest with DIFFERENT pages from
    # the whole walkthrough (ultimate dhgate free reselling spreadsheet 2026-10-23: all 15 slots were the same AirPods-case
    # page, "there's no clips, no nothing going on")
    spread = diverse_screen_footage(src, avoid=[f["t"] for f in topic]) if not cam and not own else []
    if not cam and not own and not (web or topic or spread):
        say("intro: no product footage (no own B-roll, no product-camera stretch): pictures and graphics only")
    # everything of HIS (B-roll, product camera, his spreadsheets and store pages) is "own_page": build_intro keeps it off
    # lines that knock other resellers; those get competitor sites (ultimate dhgate free reselling spreadsheet 2026-10-23)
    mine = lambda fs: [dict(f, own_page=True) for f in fs]
    # the products the VO names, from his OTHER videos (ultimate dhgate free reselling spreadsheet 2026-10-23: "everything from
    # spider hoodies to cologne to AirPod Maxes ... we have a spider video in our Google Drive, pull the spider hoodie from
    # there ... make sure that it matches up to the item"), plus a smoke grid of all of them for "I'm going to show you it all"
    prod = product_footage(vo_text)
    grid = product_grid(prod)
    listing = listing_footage(src) if re.search(r"\bdh ?gate|\bdh[kd]\b|age gate", vo_text or "", re.I) else []
    count = countdown_footage(src, doc or {}, vo_text)
    plus = plus_footage(vo_text, doc or {})
    hype = hype_footage(vo_text, doc or {})
    return count + named_site_footage(vo_text, doc or {}) + mine(listing) + mine(own + cam) + mine(prod) + grid + hype + creators + plus + web + competitor_footage(vo_text) + \
        mine(_dedupe(topic + spread + screen_footage(src), src))


# "Top N" videos: the line that promises everything in the video ("in today's video I'm going to be giving you every single
# vendor link") shows the N products of the video, one quick numbered shot each with a hit on every one (top 5 products to
# resell in winter 2024, 2026-10-24: "every single vendor link, maybe we go over different products that were shown in the
# video ... show the 5 and then have sound effects trying to mark it"). Products = the last take of each "next / first /
# last product|item|one ... going to be (the) NAME" in the recording (retakes < 90 s apart are one product); the shot = the
# product camera while he sits at the desk (face on Camera A), else the screen (listing) half, in kept footage after it.
# intro/countdown.mp4 + countdown.json (hit offsets; build_intro puts a hit on each).
COUNT_RE = re.compile(r"^(?:our )?(next|first|last|final|1st) (product|item|one)\b")
COUNT_FOR = ["every single vendor link", "every vendor link", "in today's video", "every product", "every item", "all of them"]


COUNT_NAMES = [(r"\bnor ?face\b", "North Face"), (r"\bair ?pods?\b", "AirPod"), (r"\bmax is\b", "Max"), (r"\bspider\b", "Sp5der")]


def _count_products(words, kept):
    hits = []
    for i, w in enumerate(words):
        t = " ".join(x["w"] for x in words[i:i + 4]).lower()
        if not COUNT_RE.match(re.sub(r"[^a-z0-9' ]", "", t)):
            continue
        tail = " ".join(x["w"] for x in words[i:i + 18])
        # the first "going to be" that names something ("the first one I'm going to be going over is going to be the X")
        m = next((x for x in re.finditer(r"\b(?:going to be|gonna be)\s+(?:the |a |any (?:of the |type of )?)?([A-Za-z0-9' -]+?)"
                                         r"(?=[.,!?]| and\b| you\b| it\b| for\b| on\b| although\b| is\b| that\b| I\b|$)", tail)
                  if not re.match(r"(going|gonna|go)\b", x.group(1).strip(), re.I)), None)
        if m and m.group(1).strip():
            name = " ".join(m.group(1).split()[:3])
            for a, b in COUNT_NAMES:   # Whisper's spellings of brands
                name = re.sub(a, b, name, flags=re.I)
            hits.append((w["s"], name, any(a - 3 <= w["s"] <= b for a, b in kept)))
    groups = []
    for h in hits:
        if groups and h[0] - groups[-1][-1][0] < 90:
            groups[-1].append(h)
        else:
            groups.append([h])
    out = []
    for g in groups:
        k = [h for h in g if h[2]] or g
        out.append((k[-1][0], k[-1][1]))
    return out


# the browser bar (URLs carry years: ".../product/2023-new-negative-...") and the taskbar are cropped off a page shot
BAR = ",crop=1920:870:0:140,scale=1920:1080"


def countdown_footage(src, doc, vo_text, per=0.5):
    m = re.search(r"\btop (\d+)\b", (doc.get("title") or "").lower())
    if not m or not vo_text or not any(f in vo_text.lower() for f in COUNT_FOR):
        return []
    n = int(m.group(1))
    try:
        words = json.loads((PROJ / "work" / "transcript.json").read_text(encoding="utf-8"))
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    kept = keep_ranges()
    prods = _count_products(words, kept)
    cd_label, cd_shot = {}, {}
    # the main edit's countdown list wins (raw/countdown.json, edit_review countdown.py): the same items as the #5..#1 cards
    # (top 5 reselling products spring 2026-10-25: the transcript guess read "THE / SP5DER HOODIE / SHORTS")
    try:
        cd = json.loads((PROJ / "raw" / "countdown.json").read_text(encoding="utf-8"))
        cd = [(float(it["src"]), it.get("name") or it["label"]) for it in cd if str(it.get("label", "")).upper() != "BONUS"]
        if len(cd) >= 3:
            prods = cd
            # ...numbered like its cards
            raw_cd = [x for x in json.loads((PROJ / "raw" / "countdown.json").read_text(encoding="utf-8"))
                      if str(x.get("label", "")).upper() != "BONUS"]
            # 1..N in the order he shows them, like the main edit's cards (countdown.py; never a #5..#1 countdown)
            cd_label = {round(t, 2): f"#{k + 1}" for k, (t, _) in enumerate(sorted(cd))}
            # "shot": [t, "left"|"right"] = his pick for that item's reel shot (the auto pick for #5 Spider Hoodies was a
            # spreadsheet of AirPods rows)
            cd_shot = {round(t, 2): (float(it["shot"][0]), str(it["shot"][1])) for (t, _), it in zip(cd, raw_cd) if it.get("shot")}
    except (OSError, ValueError, KeyError):
        pass
    if len(prods) < 3:
        say(f"intro: countdown skipped ({len(prods)} products found in the recording)")
        return []
    prods = prods[-n:] if len(prods) > n else prods
    shots = []
    for k, (t0, name) in enumerate(prods):
        t1 = prods[k + 1][0] if k + 1 < len(prods) else t0 + 240
        span = [(max(a, t0), min(b, t1)) for a, b in kept if min(b, t1) - max(a, t0) >= 1.5]
        inside = lambda t: any(a + 0.3 <= t <= b - per - 0.3 for a, b in span)
        if round(t0, 2) in cd_shot:
            st, sd = cd_shot[round(t0, 2)]
            shots.append((st, sd, re.sub(r"[^A-Za-z0-9 ]", "", name).upper()[:22], "", cd_label.get(round(t0, 2), "")))
            continue
        # his listing page first ("every single vendor link"; the "product" camera of a new room films HIM: 3 of 5 shots
        # were his face), checked for dates; the product camera only when the product has no page on screen
        scr = [(r["t"], "right" if r.get("right") == "screen" else "left") for r in rows if inside(r["t"])
               and (r.get("right") == "screen" or r.get("left") == "screen")]
        cand, patch = [], ""
        for q in (0.5, 0.3, 0.7, 0.15, 0.85):
            if scr:
                c = scr[int(q * (len(scr) - 1))]
                try:
                    dated = _has_date(src, c[0] + per / 2, c[1], BAR)
                except Exception:
                    dated = False
                if not dated:
                    cand = [c]
                    patch = BAR
                    break
        if not cand and scr:   # dated everywhere (the year in a listing title): white patches over the dates, checked again
            for q in (0.5, 0.3, 0.7, 0.15, 0.85, 0.05, 0.95):
                c = scr[int(q * (len(scr) - 1))]
                try:
                    patch = BAR + _date_patches(src, [c[0] + 0.05, c[0] + per - 0.05], c[1], BAR)
                    if not _has_date(src, c[0] + per / 2, c[1], patch):
                        cand = [c]
                        break
                except Exception:
                    pass
                patch = ""
        if not cand:
            patch = ""
            cand = [(r["t"], "right") for r in rows if inside(r["t"]) and r.get("right") == "product" and r.get("rfx") is None
                    and r.get("fx") is not None and r.get("left") != "screen"]
        if not cand:
            continue
        t, side = cand[len(cand) // 2]
        shots.append((t, side, re.sub(r"[^A-Za-z0-9 ]", "", name).upper()[:22], patch, cd_label.get(round(t0, 2), "")))
    if len(shots) < 3:
        return []
    out = PROJ / "intro" / "countdown.mp4"
    # 22 was too much (top 5 reselling products spring 2026-10-26: "the blur is too much ... lessen the blur"): the picture
    # now reads as the product, the name a step blurrier so it still can't be read at a glance
    blur = int((doc.get("settings") or {}).get("countdown_blur", 10))   # 0 = sharp products (a channel that wants to show them)
    name_blur = int((doc.get("settings") or {}).get("countdown_name_blur", 16)) if blur else 0
    key = json.dumps([shots, per, 8, blur, name_blur])
    stamp = out.with_suffix(".json")
    try:
        same = json.loads(stamp.read_text(encoding="utf-8")).get("key") == key
    except (OSError, ValueError):
        same = False
    if not (out.exists() and same):
        work = PROJ / "intro" / "build_countdown"
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy(LIB / "kit" / "fonts" / "Anton-Regular.ttf", work / "font.ttf")
        args = ["ffmpeg", "-v", "error", "-y"]
        for t, side, *_ in shots:
            args += ["-ss", f"{t:.2f}", "-t", f"{per + 0.1:.2f}", "-i", str(src)]
        fc = []
        for k, (t, side, name, patch, lab) in enumerate(shots):
            x0 = "0" if side == "left" else "iw/2"
            # a quick push-in per shot, the number and the product name together in the TOP band, inside the template's
            # punch-in margin: the intro's own captions sit lower-middle and covered a bottom name bar (draft 3, 0:11)
            # setsar=1: a half-frame crop scaled to 1920x1080 carries SAR 36:29 and concat refused the mix (top 5 reselling
            # products spring 2026-10-25: every reel since the first one failed with "Invalid argument")
            fc.append(f"[{k}:v]crop=iw/2:ih:{x0}:0,scale=1920:1080{patch},setsar=1,fps=30,trim=0:{per},setpts=PTS-STARTPTS,"
                      f"scale=w='2*trunc(960*(1.10-0.10*t/{per}))':h='2*trunc(540*(1.10-0.10*t/{per}))':eval=frame,"
                      f"crop=1920:1080,setsar=1,eq=brightness=-0.06,"
                      # the products stay a TEASE: a strong blur on the picture and on the product name, so you can roughly
                      # tell what it is but not read or clearly see it; the number stays sharp (top 5 reselling products
                      # spring 2026-10-25: "we don't want to show off the products right away, people should have to watch
                      # to find out ... a rule for every top-N product video intro")
                      + (f"boxblur={blur}:2," if blur else "") +
                      f"drawbox=x=0:y=120:w=iw:h=230:color=black@0.6:t=fill,"
                      f"drawtext=fontfile=font.ttf:text='{lab or "#" + str(k + 1)}':fontsize=190:fontcolor=0x3DFF7A:borderw=8:bordercolor=black:x=200:y=137,"
                      f"drawtext=fontfile=font.ttf:text='{name}':fontsize=130:fontcolor=white:borderw=6:bordercolor=black:x=520:y=167"
                      + (f",split[a{k}][b{k}];[b{k}]crop=1400:200:500:150,boxblur={name_blur}:2[n{k}];"
                         f"[a{k}][n{k}]overlay=500:150[v{k}]" if blur else f"[v{k}]"))
        fc.append("".join(f"[v{k}]" for k in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0,format=yuv420p[out]")
        args += ["-filter_complex", ";".join(fc), "-map", "[out]", "-an", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt",
                 "yuv420p", "-crf", "18", "-preset", "fast", str(out)]
        r = subprocess.run(args, capture_output=True, text=True, cwd=str(work), timeout=600)
        if r.returncode or not out.exists():
            say(f"intro: countdown reel failed ({r.stderr[-300:]})")
            return []
        stamp.write_text(json.dumps({"key": key, "hits": [round(k * per, 3) for k in range(len(shots))],
                                     "products": [x[2] for x in shots]}), encoding="utf-8")
    say(f"intro: countdown of {len(shots)} products for the 'every single vendor link' line: " + ", ".join(x[2] for x in shots))
    return [{"src": str(out), "t": 0.0, "tag": "product countdown", "kind": "broll", "own_page": True, "no_stab": True,
             "for": COUNT_FOR, "hits": str(stamp), "must": True,
             "hold": round(len(json.loads(stamp.read_text(encoding="utf-8"))["hits"]) * per, 2)}]


# words that make a VO phrase a PRODUCT he could have reviewed before (the library match decides if footage exists)
PRODUCT_WORDS = {"hoodie", "hoodies", "spider", "sp5der", "cologne", "colognes", "perfume", "airpod", "airpods", "max", "maxes",
                 "watch", "watches", "sneakers", "shoes", "jeans", "belt", "bag", "bags", "sunglasses", "glasses", "iphone",
                 "phone", "suitcase", "jacket", "slides", "jordan", "jordans", "yeezy", "yeezys", "cartier", "rolex", "dior",
                 "prada", "chanel", "amiri", "asics", "moncler", "supreme", "backpack", "trainer", "trainers", "cups", "rick",
                 "owens", "lululemon", "alo", "north", "face", "essentials", "denim", "tears", "ultra",
                 "rolexes", "patek", "pateks", "ap", "aps", "audemars", "omega", "hublot"}
# a brand named in a list is its own product (dhgate watchb spread 2026-10-24: "Rolexes, APs, and even Pateks" became one
# phrase "rolexes aps" that no folder matches)
BRAND_WORDS = {"rolex", "rolexes", "patek", "pateks", "ap", "aps", "audemars", "omega", "hublot", "cartier"}
# a brand he has no video of gets a real photo of it (Wikimedia, free licence) instead of a clip of some other watch
BRAND_PHOTO = {"ap": "Audemars Piguet Royal Oak watch", "aps": "Audemars Piguet Royal Oak watch",
               "audemars": "Audemars Piguet Royal Oak watch", "rolex": "Rolex Submariner", "rolexes": "Rolex Submariner",
               "patek": "Patek Philippe Nautilus", "pateks": "Patek Philippe Nautilus", "omega": "Omega Speedmaster",
               "hublot": "Hublot watch"}
WATCH_VERB_NEXT = {"the", "this", "till", "until", "to", "it", "out", "my", "me", "all", "until", "them", "these", "closely"}
WATCH_VERB_PREV = {"to", "you", "i", "please", "and", "gonna", "should", "must", "go", "make", "sure", "just", "definitely"}
PRODUCT_STOP = {"the", "a", "and", "to", "of", "even", "from", "everything", "that", "literally", "just", "my", "your", "these"}


HEARD_AS = {}   # product word -> how Whisper wrote it in the VO (the clip's "for" word must match the VO line)


def product_phrases(vo_text):
    """Named products in the VO, in order: runs of <= 3 words around a product word ("spider hoodies", "airpod maxes",
    "airpod 4's", "cologne")."""
    toks = re.findall(r"[A-Za-z0-9']+", vo_text.lower())
    # Whisper hears "cologne" as "clone" ($30k reselling intro: "AirPods, Spider Hoodies, and even Clone"): inside a list of
    # products (a product word in the 6 words before) it is cologne; the spoken word is kept for placing the clip
    for k, t in enumerate(toks):
        if t in ("clone", "clones") and any(x in PRODUCT_WORDS for x in toks[max(0, k - 6):k]):
            toks[k] = "cologne"
            HEARD_AS["cologne"] = t
    # the BRAND said right before the product word belongs to it (bapesta dhgate 2026-10-25, intro 0:01: "the Bape hoodie
    # review" became "hoodie" and pulled his Sp5der hoodie, "that's the wrong one"): a capitalised word mid-sentence just
    # before a product word joins the phrase, so the library needs the brand in the folder name too ("dhgate bape hoodie")
    spans = list(re.finditer(r"[A-Za-z0-9']+", vo_text))
    brand_at = lambda k: (k > 0 and k == len(spans) - len(toks) + k and spans[k].group()[0].isupper()
                          and toks[k] not in PRODUCT_STOP | PRODUCT_WORDS | {"i", "i'm", "i've", "i'll"}
                          and not re.search(r"[.?!]\s*$", vo_text[:spans[k].start()]))
    out, i = [], 0
    while i < len(toks):
        # "watch" the verb is not a wristwatch (canada goose jacket 2026-10-24: "Watch the videos to the very end" got the
        # Cartier watch from another video)
        verb = toks[i] == "watch" and ((i + 1 < len(toks) and toks[i + 1] in WATCH_VERB_NEXT)
                                       or (i and toks[i - 1] in WATCH_VERB_PREV))
        if toks[i] in PRODUCT_WORDS and not verb:
            j = i
            # a comma ends the product: a LIST is several products ($30k reselling 2026-10-26, intro 0:20: "AirPods, Spider
            # Hoodies, and even Clone" became one phrase "airpods spider hoodies" that no folder matches, so the line showed a
            # supplier site; "when things are listed ... they should have pictures for them")
            sep = lambda k: vo_text[spans[k].end():spans[k + 1].start()] if k + 1 < len(spans) else ""
            while toks[i] not in BRAND_WORDS and j + 1 < len(toks) and j - i < 2 and toks[j + 1] not in PRODUCT_STOP and toks[j + 1] not in BRAND_WORDS and "," not in sep(j) and \
                    (toks[j + 1] in PRODUCT_WORDS or re.fullmatch(r"\d+('s|s)?", toks[j + 1])):
                j += 1
            i0 = i - 1 if os.environ.get("RG_OFF") != "brandprefix" and toks[i] not in BRAND_WORDS and brand_at(i - 1) \
                and not (out and out[-1].split()[-1] == toks[i - 1]) else i
            ph = " ".join(toks[i0:j + 1])
            # one product per spelling: "watches" and "watch" found the same Cartier wrist clip twice (dhgate watchb
            # spread 2026-10-24, intro 0:01 and 0:13)
            sing = lambda x: " ".join(t[:-2] if t.endswith("es") and len(t) > 5 else t[:-1] if t.endswith("s") and len(t) > 3 else t
                                      for t in x.split())
            if not any(sing(q) == sing(ph) for q in out):
                out.append(ph)
            i = j + 1
        else:
            i += 1
    return out


# words for the same kind of product (singular, as product_footage compares them)
OWN_SYN = [{"glasse", "sunglasse", "shade", "eyewear", "frame"}, {"shoe", "sneaker", "trainer", "kick"},
           {"hoodie", "sweatshirt", "jumper"}, {"jacket", "coat", "puffer"}, {"watch", "timepiece"}, {"slide", "sandal"}]


def _face_in_clip(c, span=3.0):
    """his face is on the cropped half of a raw two-camera recording during the clip (that project's work/analysis.json)"""
    src = Path(str(c.get("src", "")))
    if src.name.lower() != "camera.mp4" or c.get("crop") not in ("left", "right"):
        return False
    try:
        rows = json.loads((src.parent.parent / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    key = "fx" if c["crop"] == "left" else "rfx"
    t = float(c.get("t") or 0)
    near = [r for r in rows if t <= r.get("t", -1) <= t + span]
    return bool(near) and sum(r.get(key) is not None for r in near) > len(near) / 2


def product_footage(vo_text, per=2, max_products=5):
    if not vo_text:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import product_library
    except Exception as e:
        say(f"intro: product library unavailable ({e})")
        return []
    out = []
    # the video's OWN product is never pulled from another video (canada goose jacket 2026-10-24: "jacket" in the VO found
    # his black North Face puffer from "dhgate northface" and it played on 7 of 10 intro lines): its footage is this
    # recording's product camera / B-roll
    own = {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", PROJ.name.lower())}
    # ...the same thing in other words counts too (dhgae prada glasses 2026-10-25, 0:07: "prada sunglasses" vs the title's
    # "glasses" was "another product", so a muted talking shot of him in his everyday glasses from "prada glasses dhgate
    # {{REVIEW_CHANNEL}} finds" played under "they actually seem very stylish", "these are my normal glasses ... we need relevant clips")
    same = lambda w: (w in own or any(len(o) >= 4 and len(w) >= 4 and (o in w or w in o) for o in own)
                      or any(w in g and own & g for g in OWN_SYN))
    phrases = [ph for ph in product_phrases(vo_text)
               if not all(same(w.rstrip("s")) for w in re.findall(r"[a-z0-9]+", ph))][:max_products]
    for ph in phrases:
        clips = product_library.find_clips(ph, exclude=[PROJ.name], n=per, word=ph)
        if not clips and ph in BRAND_PHOTO:
            try:
                import pics
                hit = pics.fetch(BRAND_PHOTO[ph])
                clip = pics.photo_clip(hit["url"], seed=len(out)) if hit else None
                if clip:
                    clips = [{"src": clip, "t": 0.0, "tag": f"product: {ph} (photo)", "kind": "broll", "own_page": True}]
                    say(f"intro: '{ph}' -> no video of it, a real photo ({hit['title']})")
            except Exception as e:  # noqa: a missing photo never stops the intro
                say(f"intro: '{ph}' photo failed ({e})")
        # a phrase can span two VO lines ("everything from spider | hoodies to cologne"): its own words count too, unless
        # another product shares them ("airpod" is in both "airpod maxes" and "airpod 4's")
        own = [t for t in ph.split() if len(t) >= 5 and not any(t in q.split() for q in phrases if q != ph)]
        own += [HEARD_AS[t] for t in ph.split() if t in HEARD_AS]
        for c in clips:
            c["for"] = [ph] + own
        # never the same moment of the same file twice (two phrases can find one clip)
        clips = [c for c in clips if not any(o["src"] == c["src"] and abs(float(o["t"]) - float(c["t"])) < 3 for o in out)]
        # a LIST of products: never a clip from another video's TALKING camera with his face in it ($30k reselling
        # 2026-10-26, 0:23 / 0:31: him holding the cologne up to the face cam from "dhgate cologne spread", like the 0:25
        # "I don't know why I show up there")
        if len(phrases) >= 2 and os.environ.get("RG_OFF") != "multiproduct":
            clips = [c for c in clips if not _face_in_clip(c)]
        if clips:
            say(f"intro: '{ph}' -> {len(clips)} clip(s) from {', '.join(sorted({Path(c['src']).parent.name for c in clips}))}")
        out += clips
    return out


def product_grid(prod, seconds=4.0):
    """One clip per product in a 2x2 grid on smoke (the "smoke grid" he asked for), for the line that promises to show it all."""
    firsts, seen = [], set()
    for f in prod:
        if f["for"][0] not in seen:
            seen.add(f["for"][0])
            firsts.append(f)
    if len(firsts) < 3:
        return []
    firsts = firsts[:4]
    out = PROJ / "intro" / "product_grid.mp4"
    key = json.dumps([[f["src"], f["t"], f.get("crop")] for f in firsts])
    stamp = out.with_suffix(".json")
    if not (out.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == key):
        W, H, G = 860, 484, 40
        pos = [(G * 2, G), (W + G * 3, G), (G * 2, H + G * 2), (W + G * 3, H + G * 2)] if len(firsts) == 4 else \
              [(G, 298), (W + G * 2 - 230, 40), (W + G * 2 - 230, H + G * 2)]
        args = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", f"{seconds}", "-i", str(LIB / "kit" / "tex" / "smoke1.png")]
        for f in firsts:
            args += ["-ss", f"{f['t']:.2f}", "-t", f"{seconds}", "-i", f["src"]]
        fc = [f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p,"
              f"zoompan=z='1+0.0006*on':d=1:s=1920x1080:fps=30,eq=brightness=-0.45:contrast=1.1[bg]"]
        last = "bg"
        for k, f in enumerate(firsts):
            crop = {"left": "crop=iw/2:ih:0:0,", "right": "crop=iw/2:ih:iw/2:0,"}.get(f.get("crop") or "", "")
            fc.append(f"[{k + 1}:v]{crop}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
                      f"pad={W + 12}:{H + 12}:6:6:white[c{k}]")
            x, y = pos[k]
            fc.append(f"[{last}][c{k}]overlay={x - 6}:{y - 6}:enable='gte(t,{0.12 * k:.2f})'[g{k}]")
            last = f"g{k}"
        args += ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-t", f"{seconds}", "-an", "-c:v", "libx264",
                 "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast", str(out)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if r.returncode or not out.exists():
            say(f"intro: product grid failed ({r.stderr[-200:]})")
            return []
        stamp.write_text(key, encoding="utf-8")
    say(f"intro: smoke grid of {len(firsts)} products for the 'show you it all' line")
    return [{"src": str(out), "t": 0.0, "tag": "product grid", "kind": "broll", "own_page": True,
             "for": ["show you guys it all", "show you it all", "it all", "show you everything"]}]


# Lines that knock OTHER resellers ("influencers ... selling you poor quality vendor links", 0:08 of the reselling spreadsheet
# intro) show another reseller's site, scrolling their supplier list, never his own DHgate listings ("that might not be good
# for promotion, like saying that our links are bad"). Sites: raw/competitors.txt (one URL per line) + the library list
# intro_library/competitor_sites.json (his link piaresells.com, saved for future intros).
KNOCK_WORDS = ["influencer", "wrong path", "never had", "in hand", "vendor links", "rip you off", "gurus", "youtubers",
               "other resellers", "other people's links"]
# Product words ("scam", "fake", "poor quality") are NOT a knock: "to see if this quality is actually good or if it's a complete
# scam" got piaresells.com's vendor page (best sp5der hoodie 2026-10-23: "never show another reseller's vendor link page unless
# I'm saying they don't have it in hand"). build_intro.KNOCK_RE uses the same who-words.


COMP_LEDGER = LIB / "_state" / "competitor_sites_used.json"


def competitor_footage(vo_text, starts=(0, 400)):
    if not vo_text or not any(k in vo_text.lower() for k in KNOCK_WORDS):
        return []
    urls = []
    f = PROJ / "raw" / "competitors.txt"
    if f.exists():
        urls += re.findall(r"https?://\S+", f.read_text(encoding="utf-8", errors="ignore"))
    try:
        pool = json.loads((LIB / "competitor_sites.json").read_text(encoding="utf-8")).get("sites", [])
    except (OSError, ValueError):
        pool = []
    # ONE site per video, a different one for every video (remote test prada 2026-10-26: "scroll a new website for each
    # video ... you don't have to keep redoing it for the same video ... at least 10 that we can fall back to", every intro
    # had shown piaresells.com): this video's site from the ledger, else the least-used one; two scroll points of it
    if not urls and pool:
        try:
            led = json.loads(COMP_LEDGER.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            led = {}
        project = str(PROJ)
        mine = [u for u in pool if project in led.get(u, [])]
        pick = mine[0] if mine else min(pool, key=lambda u: (len(led.get(u, [])), pool.index(u)))
        if project not in led.get(pick, []):
            led.setdefault(pick, []).append(project)
            try:
                COMP_LEDGER.parent.mkdir(parents=True, exist_ok=True)
                COMP_LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
            except OSError:
                pass
        # the next ones in line stand by in case this one fails to load
        urls = [pick] + [u for u in sorted(pool, key=lambda u: len(led.get(u, []))) if u != pick]
    urls = list(dict.fromkeys(urls))
    try:
        sys.path.insert(0, str(LIB))
        import screenrec
    except Exception as e:
        say(f"intro: competitor pages unavailable ({e})")
        return []
    out = []
    for u in urls:
        for st in starts:
            mp4 = screenrec.record_page(u, seconds=4.0, start=st)
            if mp4:
                out.append({"src": mp4, "t": 0.0, "tag": f"screen recording: other reseller site {u}", "kind": "broll",
                            "for": KNOCK_WORDS})
        if out:
            break
    if out:
        say(f"intro: {len(out)} competitor-site scrolls for the lines about other resellers")
    return out


# Any website he NAMES in the intro gets a real scroll of THAT site on that line (2026-10-23, reselling spreadsheet 0:10:
# "these creators have Alibaba links ... put a screen capture of Alibaba"; "when I mention different websites inside of an
# intro, like Canva, we could literally scroll Canva's website"). intro_library/named_sites.json = names + how Whisper
# mishears them ("alley bobble") + a search page for the product / home page; raw/sites.txt ("alibaba https://...") pins the
# exact page for one project. A site with a human check is only recorded after he solved it once (screenrec.py --verify URL);
# otherwise it is skipped and intro_check reports the line.
def named_site_footage(vo_text, doc, n_max=2):
    if not vo_text:
        return []
    try:
        reg = json.loads((LIB / "named_sites.json").read_text(encoding="utf-8"))["sites"]
    except (OSError, ValueError, KeyError):
        return []
    pinned = {}
    f = PROJ / "raw" / "sites.txt"
    if f.exists():
        for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*([\w.-]+)\s*[:=]?\s*(https?://\S+)", ln)
            if m:
                pinned[m.group(1).lower()] = m.group(2)
    low = vo_text.lower()
    hits = []
    for key, s in reg.items():
        pos = [m.start() for a in s["aliases"] for m in re.finditer(r"\b" + re.escape(a) + r"\b", low)]
        if pos:
            hits.append((min(pos), key, s))
    if not hits:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import screenrec
    except Exception as e:
        say(f"intro: named-site recordings unavailable ({e})")
        return []
    q = product_query(doc)
    out = []
    for _, key, s in sorted(hits)[:n_max]:
        urls = [pinned[key]] if key in pinned else []
        if s.get("search") and q:
            urls.append(s["search"].format(q=urllib.parse.quote_plus(q), q_dash=re.sub(r"\s+", "-", q)))
        if s.get("home"):
            urls.append(s["home"])
        mp4 = None
        # walled sites (Alibaba, Amazon, Temu...) block every automated browser: no live try, straight to the recreation
        for u in ([] if s.get("wall") else urls):
            mp4 = screenrec.record_page(u, seconds=4.0)
            if mp4:
                say(f"intro: {key} page recorded for the line that names it ({u})")
                break
        if not mp4:
            mp4, u = recreated_site(key, s, vo_text, q), "recreated"
        if mp4:
            out.append({"src": mp4, "t": 0.0, "tag": f"screen recording: {key} {u}", "kind": "broll", "site": key,
                        "for": [key, (s.get("name") or "").lower()] + s["aliases"]})
        else:
            say(f"intro: {key} is named but neither the site nor a recreation could be made")
    return out


# The real site can't be filmed (human check, down, no network): rebuild its page locally in its own look and film that
# (intro_library/sitepage.py; user 2026-10-23: "Maybe we should recreate the page ... I want it automatic"). The project's
# raw/site_<key>.json = one real listing (his link's real title / prices / supplier); otherwise search results for the
# product, pictures from free sources (no invented prices).
def recreated_site(key, s, vo_text, q):
    try:
        sys.path.insert(0, str(LIB))
        import sitepage
        import pics
    except Exception as e:
        say(f"intro: site recreation unavailable ({e})")
        return None
    f = PROJ / "raw" / f"site_{key}.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except ValueError:
        data = None
    if not data:
        # one card per product he names, its picture from HIS other videos (the matched product clips), two moments each;
        # a free picture only for a product with no footage (never a name search alone: "cologne" found the city)
        out_dir = PROJ / "intro" / "build" / f"site_{key}"
        out_dir.mkdir(parents=True, exist_ok=True)
        names, imgs = [], []
        for c in product_footage(vo_text):   # one frame per clip, the product half of a side-by-side recording
            jpg = out_dir / f"{len(imgs):02d}.jpg"
            crop = {"left": "crop=iw/2:ih:0:0,", "right": "crop=iw/2:ih:iw/2:0,"}.get(c.get("crop"), "")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['t'] + 1.5:.2f}", "-i", str(c["src"]), "-frames:v", "1",
                            "-vf", crop + "scale=720:-2", str(jpg)])
            if jpg.exists():
                names.append(c["for"][0].title())
                imgs.append(str(jpg))
        if len(imgs) < 4 and q:
            for n in [q + " product", q]:
                h = pics.fetch(n, "photo")
                if h and h.get("file") and h["file"] not in imgs:
                    names.append(q.title())
                    imgs.append(h["file"])
                    break
        if not imgs:
            return None
        data = {"kind": "search", "query": names[0].lower(), "names": names, "images": imgs[:8]}
    data["images"] = [p for p in data.get("images", []) if os.path.exists(p)]
    if not data["images"]:
        return None
    mp4 = sitepage.recreate(key, data)
    if mp4:
        say(f"intro: {key} can't be filmed live: recreated its {data.get('kind', 'search')} page and filmed that")
    return mp4


# Lines about OTHER creators / videos ("these influencers", "all these YouTubers", "a bunch of videos of this mod") show real
# clips of those creators, one creator per shot, muted, "@handle" credit (ultimate dhgate free reselling spreadsheet
# 2026-10-23: the intro reused one YouTube-search scroll at 2, 4 and 8 s; "when I say other creators, other videos in an
# intro, we should be having videos ... of them"). intro_library/creator_clips.py finds them for the video's topic.
CREATOR_RE = re.compile(r"\b(influencers?|youtubers?|gurus?|creators?|tik ?tokers?|other (?:channels?|videos?|people|resellers?)|"
                        r"(?:a bunch|a lot|tons) of (?:videos|people|youtubers)|all these (?:videos|youtubers|creators|people))\b", re.I)
TOPIC_FILLER = set("ultimate free best top the a an my your new full complete guide review reviews honest spreadsheet list "
                   "video videos how to for and of on in with".split())


# More kinds of source (2026-10-25, "some intros just fall short ... we need different assets ... TikToks, articles, YouTube
# videos"; INTRO_RULES.md asset mix: 4+ kinds, his product <= 50%): intro_library/assets_plus.plus_footage (shared with the
# phone pipeline) = a YouTube thumbnail wall on "everyone / trending" lines, his viewers' real comments on "you guys asked"
# lines, an OpenStreetMap push-in for cities he names.
def plus_footage(vo_text, doc):
    try:
        sys.path.insert(0, str(LIB))
        import assets_plus
        return assets_plus.plus_footage(vo_text, doc.get("title") or "", doc.get("channel") or "", say=say)
    except Exception as e:
        say(f"intro: assets_plus unavailable ({e})")
        return []


# "X has risen in popularity / everyone's wearing them / blew up on TikTok" = real people wearing THAT product (maison mahara
# dhgae review 2026-10-26, 0:03-0:07: the director asked Mixkit for "street style sneakers" and got people dancing by a car
# and a parked moped, "this has like no relevance ... what is this?"). Mixkit has no designer sneakers; YouTube has people
# wearing them. The search name comes from the brain, because Whisper and his folder names misspell brands ("Mason Mahara"
# / "maison mahara" = Maison Mihara Yasuhiro).
HYPE_RE = re.compile(r"\b(popular(ity)?|trend(ing|y)|hyped?|viral|blew up|everyone'?s? (wearing|rocking)|"
                     r"(on|in) the streets?|street ?wear|all over (tik ?tok|instagram|social media))\b", re.I)


def search_name(vo_text, doc):
    """the product's real name for a web search ("Maison Mihara Yasuhiro sneakers"), from the title + voiceover. The brain
    names 3 spellings it could be; a spelling counts only when YouTube has >= 3 videos with its key word in the title, and the
    one that SOUNDS closest to what he said wins (one guess said "Maison Margiela" for "Mason Mahara", a different brand)."""
    import difflib
    try:
        sys.path.insert(0, str(LIB.parent))
        import claude_brain
        ans = claude_brain.ask("product_name", (
            f"Video title: {doc.get('title') or ''}\nVoiceover: {vo_text[:600]}\n\nThe title and the auto-transcript often MISSPELL "
            "the brand by sound (a speech-to-text guess, e.g. 'Valenciaga' for Balenciaga, 'Rick Owen' for Rick Owens). List the 3 "
            "most likely REAL products it could be, closest-sounding first, each with its official spelling as fans search it on "
            "YouTube (brand + model/type, 2-5 words, no 'DHgate', no 'review') and the ONE distinctive word of it that a video "
            'title about it would contain. JSON only: {"candidates": [{"name": "...", "must": "...", "heard_as": "<the words in '
            'the title/voiceover it matches>"}]}'), model="opus", timeout=120)
        cands = [c for c in (ans or {}).get("candidates", []) if isinstance(c, dict) and c.get("name") and c.get("must")]
    except Exception as e:  # noqa
        say(f"intro: product name lookup failed ({e})")
        return None, None
    heard = re.findall(r"[a-z0-9']+", f"{doc.get('title') or ''} {vo_text[:300]}".lower())
    best = None
    for c in cands:
        brand = [w for w in re.findall(r"[a-z0-9']+", c["name"].lower())][:2]
        sim = max((difflib.SequenceMatcher(None, " ".join(brand), " ".join(heard[i:i + len(brand)])).ratio()
                   for i in range(max(1, len(heard) - len(brand) + 1))), default=0)
        try:
            r = subprocess.run(["yt-dlp", "--no-warnings", "--quiet", f"ytsearch10:{c['name']}", "--flat-playlist", "--print", "%(title)s"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            hits = sum(1 for t in r.stdout.splitlines() if c["must"].lower() in t.lower())
        except Exception:  # noqa
            hits = 0
        say(f"intro: product name '{c['name']}' sounds {sim:.2f} like the VO, {hits}/10 YouTube titles say '{c['must']}'")
        if hits >= 3 and (best is None or sim > best[0]):
            best = (sim, c)
    if best:
        return best[1]["name"].strip(), best[1]["must"].strip().lower()
    return None, None


def multi_product(vo_text):
    """the VO names 2+ different products (a topic / list video, not one product's review)"""
    if os.environ.get("RG_OFF") == "multiproduct":
        return False
    try:
        return len({p for p in product_phrases(vo_text or "")}) >= 2
    except Exception:  # noqa
        return False


def hype_footage(vo_text, doc):
    m = HYPE_RE.search(vo_text or "")
    if not m or os.environ.get("RG_OFF") == "hype":
        return []
    # "these are the most popular items" after a LIST is about all of them: people wearing ONE of them is off ($30k reselling
    # 2026-10-26, 0:13-0:23: Apple AirPods Pro ads, a noise-cancelling graph and flying cars on a reselling intro)
    if multi_product(vo_text):
        say(f"intro: '{m.group(0)}' is about several products, no wearing clips")
        return []
    name, must = search_name(vo_text, doc)
    if not name:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import creator_clips
        yt = creator_clips.youtube_clips([f"{name} on feet", f"{name} outfit", f"{name} street style"], n=2,
                                         need=[[must]])
    except Exception as e:
        say(f"intro: hype clips unavailable ({e})")
        return []
    if yt:
        say(f"intro: {len(yt)} YouTube clips of people wearing {name} ({', '.join('@' + c['handle'] for c in yt)}) for '{m.group(0)}'")
    words = sorted({x.group(0).lower() for x in HYPE_RE.finditer(vo_text)})
    return [{"src": c["src"], "t": 0.0, "tag": f"creator clip: @{c['handle']} wearing {name} (YouTube)", "kind": "broll",
             "no_stab": True, "for": words, "creator": c["handle"]} for c in yt]


def creator_footage(vo_text, doc, n=7):
    m = CREATOR_RE.search(vo_text) if vo_text else None
    if not m:
        return []
    # the creators of the PRODUCT the influencer sentence names ("influencers claiming they have the best link for Prada
    # sunglasses"), not of the project title (remote test prada 2 2026-10-26, 0:17: the title "_remote test prada 2" searched
    # "remote test prada", found nobody, and the director put stock of a vlogger there: "we don't ever wanna use stock
    # footage of influencers ... grab videos of them for Prada sunglasses")
    about = _who_product(vo_text, m) if os.environ.get("RG_OFF") != "creatorproduct" else None
    if about:
        core = [w for w in re.findall(r"[a-z0-9]+", about.lower()) if w not in TOPIC_FILLER and not w.isdigit()]
    else:
        core = [w for w in re.findall(r"[a-z0-9]+", (doc.get("title") or "").lower()) if w not in TOPIC_FILLER and not w.isdigit()]
    if not core:
        return []
    stem = lambda w: re.sub(r"(ing|ers|er|s)$", "", w) if len(w) > 5 else w
    topic = list(dict.fromkeys(core + [stem(w) for w in core]))
    # posts naming the brand first ("#sunglasses" alone was any sunglasses account, not Prada), then the product word fills up
    brand_first = bool(about and len(core) > 1 and core[0] in BRANDS)
    main = core[-1]
    # the product word and its synonyms ("sunglass", "glasse", "shade"): a brand post must ALSO name the product (@peteyy16's
    # "Chrome Pradas" was a Prada shoe)
    prod = {re.sub(r"(es|s)$", "", main)} | next((g for g in OWN_SYN if stem(main) in g or re.sub(r"s$", "", main) in g), set())
    queries = ([f"{' '.join(core)} dhgate", f"dhgate {' '.join(core)} review", f"{' '.join(core)} review"] if about else
               [" ".join(core), f"how to start {main}", f"{' '.join(core)} for beginners"])
    try:
        sys.path.insert(0, str(LIB))
        import creator_clips
        brand = [core[0], BRANDS.get(core[0], core[0])] if about else []   # the brand's own account is not an influencer
        # a product review: real YouTube videos about THAT product, played full frame on the influencer line and the line
        # that runs on from it ("... have the best link for Prada sunglasses"); TikTok posts only when YouTube has none
        if about and os.environ.get("RG_OFF") != "ytcreators":
            yt = creator_clips.youtube_clips(queries[:2] + [f"{' '.join(core)} unboxing"], n=2, exclude=brand,
                                             need=([[core[0]], sorted(prod)] if brand_first else [sorted(prod)]))
            if yt:
                say(f"intro: {len(yt)} YouTube creator clips ({', '.join('@' + c['handle'] for c in yt)}) for the influencer line")
                words = sorted({m.group(0).lower() for m in CREATOR_RE.finditer(vo_text)} | {"best link", "claiming"})
                return [{"src": c["src"], "t": 0.0, "tag": f"creator clip: @{c['handle']} (YouTube)", "kind": "broll",
                         "no_stab": True, "for": words, "creator": c["handle"]} for c in yt]
        got = creator_clips.creator_clips(queries, [core[0]] if brand_first else topic, n=n, exclude=brand,
                                          need=[sorted(prod)] if brand_first else ())
        if brand_first and len(got) < 3:
            got += creator_clips.creator_clips(queries, sorted(prod), n=3 - len(got), exclude=brand + [c["handle"] for c in got])
    except Exception as e:
        say(f"intro: creator clips unavailable ({e})")
        return []
    # a product word would pull the creators onto HIS product lines ("review of the Prada sunglasses")
    words = sorted({m.group(0).lower() for m in CREATOR_RE.finditer(vo_text)} | (set() if about else {main, stem(main)}))
    if got:
        say(f"intro: {len(got)} creator clips ({', '.join('@' + c['handle'] for c in got)}) for the lines about other creators")
    # TikToks are portrait and the video is landscape: three creators side by side per shot (user 2026-10-23, "maybe
    # three"), every creator in one shot only; a leftover one or two get the single card (portrait on its blurred copy)
    # only on the hook / problem lines that talk about them: a spare 3-up landed on "sell them to your customers" (2026-10-23)
    roles = ["hook", "problem"]
    out = []
    while len(got) >= 3:
        trip, got = got[:3], got[3:]
        mp4 = creator_clips.triptych(trip)
        if mp4:
            out.append({"src": mp4, "t": 0.0, "tag": "creator clips: " + " ".join("@" + c["handle"] for c in trip),
                        "kind": "broll", "no_stab": True, "for": words, "roles": roles})
        else:
            got = trip + got
            break
    if out:   # leftovers stay out: the director chose the lone portrait card over the 3-ups (reselling spreadsheet 0:02)
        return out
    return [{"src": c["src"], "t": 0.0, "tag": f"creator clip: @{c['handle']}", "kind": "broll", "no_stab": True,
             "for": words, "creator": c["handle"], "roles": roles} for c in got]


def _dedupe(items, src, min_diff=10):
    """The same page never twice: screen moments whose cropped picture matches an earlier one (32x18 thumbnails, mean
    abs diff < min_diff) are dropped (reselling spreadsheet R01 build: the AirPods-case page came in as the store page
    twice AND as the 'airpod' topic, and showed 4 times)."""
    import numpy as np
    out, seen = [], []
    for f in items:
        side = f.get("crop")
        if side not in ("left", "right"):
            out.append(f)
            continue
        x0 = "0" if side == "left" else "iw/2"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{f['t'] + 1:.2f}", "-i", str(src), "-frames:v", "1", "-vf",
                              f"crop=iw/2:ih:{x0}:0,scale=1920:1080{f.get('vf', '')},scale=32:18", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True).stdout
        th = np.frombuffer(raw, np.uint8).astype(float) if len(raw) == 576 else None
        if th is not None and any(np.abs(th - o).mean() < min_diff for o in seen):
            say(f"intro: dropped a repeat of the same page ({f.get('tag')}, {f['t']:.1f} s)")
            continue
        if th is not None:
            seen.append(th)
        out.append(f)
    return out


def vo_words_text(doc):
    """The intro VO as text (build_intro's Whisper cache; transcribed now on a first build)."""
    build = PROJ / "intro" / "build"
    cache = build / "vo-words.json"
    try:
        if not cache.exists():
            slot = doc.get("slots", {}).get("intro_vo") or doc.get("slots", {}).get("intro") or ""
            if not slot or Path(slot).suffix.lower() not in AUDIO:
                return ""
            build.mkdir(parents=True, exist_ok=True)
            sys.path.insert(0, str(LIB))
            import build_intro
            build_intro.transcribe(slot, str(cache), "")
        return " ".join(w["w"] for w in json.loads(cache.read_text(encoding="utf-8")))
    except Exception as e:
        say(f"intro: VO words unavailable ({e})")
        return ""


# Lines about OTHER resellers get a real screen recording of YouTube search results (intro_library/screenrec.py, dates
# hidden): his published edit of the reselling spreadsheet video cut YouTube pages into the intro, and he asked for "new
# types of screen recordings ... like real editors" (2026-10-23, 0:07 "influencers putting you on the wrong path").
# trigger word in the VO -> search query; one recording per trigger, each "for" its word so it lands on that line.
# Each theme has a BANK of searches, rotated across videos (top 5 reselling products spring 2026-10-25, 0:02: "we should not be
# reusing the scroll ... you could find other reselling search queries, how to get started reselling, I tried reselling ...
# filter it to this month ... we can't keep using the same clip over and over, that's a dead giveaway"; every reselling
# intro had filmed "dhgate resell haul"). A query another video already used is skipped (_state/web_queries.json), the
# search is filtered to this month's uploads (screenrec "youtube_month"), and every theme the VO hits gets its own search,
# landing on its own line ("for" = the words that triggered it; 0:04 "$10,000 every single month" had no fitting shot).
WEB_FOR = [(r"\binfluencers?\b", ["dhgate reselling vendor links", "reselling influencer vendor list", "reselling plug vendors"]),
           (r"\b(youtubers?|gurus?)\b", ["reselling guru vendor list", "reselling course review", "reselling guru exposed"]),
           (r"\bvendors?\b", ["best dhgate reselling vendors", "dhgate vendors for resellers", "trusted reselling suppliers"]),
           (r"\btik ?toks?\b", ["reselling tiktok haul", "tiktok reselling side hustle", "tiktok shop reselling"]),
           (r"\$\s?\d[\d,]*|\b\d[\d,]* (dollars|bucks|grand)\b|\b(a|per) month\b|\bmake (lots of |a lot of |good )?money\b|\bprofit\b",
            ["how i make 10k a month reselling", "reselling income per month", "how much money reselling makes",
             "reselling profit breakdown", "my first month reselling results", "reselling side hustle earnings"]),
           (r"\b(which|what) (items|products)\b|\bitems? to resell\b|\bproducts? to resell\b|\bwhat to resell\b",
            ["best items to resell", "what to resell for profit", "top products to resell", "hot items to flip for profit",
             "what sells best on ebay", "best things to resell right now"]),
           (r"\bresell(ing|ers?)?\b|\bflip(ping)?\b|\bhop on\b|\bside hustle\b",
            ["how to start reselling", "i tried reselling for 30 days", "reselling for beginners", "is reselling worth it",
             "how to resell for profit", "reselling side hustle", "starting a reselling business"])]
QUERY_LEDGER = LIB / "_state" / "web_queries.json"


def _fresh_query(bank, project):
    """the first search of the bank no OTHER video used yet (this video keeps its own on a rebuild); all used = the least used"""
    try:
        led = json.loads(QUERY_LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        led = {}
    mine = [q for q in bank if project in led.get(q, [])]
    if mine:
        return mine[0], led
    q = min(bank, key=lambda x: (len(led.get(x, [])), bank.index(x)))
    return q, led


def _who_product(vo_text, m):
    """the named product of the sentence an influencer / youtuber word sits in ("... have the best link for Prada sunglasses")"""
    s = max(vo_text.rfind(c, 0, m.start()) for c in ".!?") + 1
    e = min([x for x in (vo_text.find(c, m.end()) for c in ".!?") if x >= 0] or [len(vo_text)])
    # ...and the CLAUSE: Whisper often writes no full stop, so "influencers make it seem very difficult ... you don't know
    # about, but in today's video ... reselling items such as AirPods" was one "sentence" and the influencer search became
    # "best airpods dhgate" ($30k reselling 2026-10-26, 0:07: "I didn't mention anything about AirPods yet")
    if os.environ.get("RG_OFF") != "whoclause":
        b = re.search(r",?\s*\b(but|however|in today'?s video|so today)\b", vo_text[m.end():e], re.I)
        if b:
            e = m.end() + b.start()
    ph = product_phrases(vo_text[s:e])
    return ph[0] if ph else None


def web_footage(vo_text, n_max=4, skip=()):
    if not vo_text:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import screenrec
    except Exception as e:
        say(f"intro: web screen recordings unavailable ({e})")
        return []
    project = str(PROJ)
    out = []
    for pat, bank in WEB_FOR:
        m = re.search(pat, vo_text, re.I)
        if not m or len(out) >= n_max or m.group(0).lower() in skip:
            continue    # skip: a product page already covers that word
        # the money bank is reselling INCOME: a product's retail price is not (maison mahara dhgae review 2026-10-26, 0:10-0:12:
        # "set you back around $500" got a "reselling income per month" YouTube scroll, "this is a Maison Mahara video, but
        # you have reselling scroll on YouTube"). Only when the voiceover is about reselling / making money at all.
        if bank is WEB_FOR[4][1] and not re.search(r"\bresell|\bflip(ping)?\b|\bprofit|\bincome\b|side hustle|\bmake (lots of |a lot of |good )?money\b|\b(a|per) month\b", vo_text, re.I):
            continue
        query, led = _fresh_query(bank, project)
        # "influencers claiming they have the best link for Prada sunglasses": search what the viewer would type, the
        # product of THAT sentence (remote test prada 2026-10-26, 0:17: "you should've typed the video title into YouTube
        # and then scroll ... relevant [videos] of the best Prada sunglasses on DHgate"; the bank's "dhgate reselling vendor
        # links" was off topic). Not ledgered: it belongs to this video.
        about = _who_product(vo_text, m) if bank is WEB_FOR[0][1] or bank is WEB_FOR[1][1] else None
        if about and os.environ.get("RG_OFF") != "whoproduct":
            query = f"best {about} dhgate"
            mp4 = screenrec.record_search(query, seconds=4.0)
            if mp4:
                out.append({"src": mp4, "t": 0.0, "tag": f"screen recording: YouTube search '{query}'", "kind": "broll",
                            "for": [m.group(0).lower()]})
                say(f"intro: web screen recording for '{m.group(0)}' ({query}, the product of that sentence)")
                continue
        mp4 = screenrec.record_search(query, seconds=4.0, site="youtube_month") or screenrec.record_search(query, seconds=4.0)
        if mp4:
            if project not in led.get(query, []):
                led.setdefault(query, []).append(project)
                try:
                    QUERY_LEDGER.parent.mkdir(parents=True, exist_ok=True)
                    QUERY_LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")
                except OSError:
                    pass
            out.append({"src": mp4, "t": 0.0, "tag": f"screen recording: YouTube search '{query}'", "kind": "broll", "for": [m.group(0).lower()]})
            say(f"intro: web screen recording for '{m.group(0)}' ({query})")
    return out


# Product reviews: the hype / resale lines get REAL pages, each its own recording (dhgate jordan 3 2026-10-23: the R09 intro
# held one listing card with turntable footage for 18 s, "it doesn't move ... no 3D motion graphics of like a page scroll or
# something. Go get articles. Do something different"). StockX search = the resale prices he complains about; Bing News =
# real headlines about resellers / sell-outs / resale prices (ages stripped by screenrec). No YouTube here: thumbnails carry
# years ("RELEASE DATES 2026") that no sanitizer can remove. (pattern, site, query template; {p} = the product, {first} = its
# first word, {kind} = "sneaker" for footwear; "|" = alternatives, a news page needs >= 3 stories)
PRODUCT_WEB = [(r"\bstock ?x\b|\bgoat\b", "stockx", "{p}"),
               (r"\bresell(ers?|ing)\b|\bbots?\b", "bing_news", "{kind} resellers bots"),
               (r"\bsold out\b|\bsell(s|ing)? out\b", "bing_news", "{p} sold out|air {p} sold out|{first}s sold out|{kind}s sold out in seconds"),
               (r"\bprice is (super |really |so |way )?(high|crazy|insane)\b|\boverpriced\b|\bresale price\b", "bing_news", "{p} resell price")]
FOOTWEAR = r"jordan|dunk|yeezy|nike|asics|sneaker|shoe|trainer|slide|vans|ugg|boot|air max|new balance|adidas|rick owens|lv trainer"


def product_query(doc):
    """The product as a search query ("dhgate jordan 3" -> "jordan 3"): the title without dhgate/review words, digits kept."""
    t = re.sub(r"\b(dh ?gate|review|reviews|honest|the|best|from|on)\b", " ", (doc.get("title") or "").lower())
    return re.sub(r"\s+", " ", t).strip()


OWN_SAME_KIND_MAX = 3

# The retail price line ("with one of them setting me back around $1000") shows the REAL product with real prices (lv
# skatesta 2026-10-24, his own edit: "$1,000, show some shoes from LV's website"). Brand sites wall automated browsers (Louis
# Vuitton: a human check in the browser, 403 to plain requests), so the product's StockX search (real pairs, real prices) is
# filmed. BRANDS: how the VO / the title write the brand -> its full name for the search.
BRANDS = {"lv": "louis vuitton", "louis vuitton": "louis vuitton", "gucci": "gucci", "dior": "dior", "prada": "prada",
          "balenciaga": "balenciaga", "rick owens": "rick owens", "amiri": "amiri", "chrome hearts": "chrome hearts",
          "off white": "off-white", "off-white": "off-white", "alexander mcqueen": "alexander mcqueen", "mcqueen": "alexander mcqueen",
          "givenchy": "givenchy", "versace": "versace", "bape": "bape", "cartier": "cartier", "rolex": "rolex", "hermes": "hermes",
          "yeezy": "yeezy", "jordan": "jordan", "nike": "nike", "asics": "asics", "golden goose": "golden goose",
          "maison margiela": "maison margiela"}
RETAIL_RE = re.compile(r"\b(setting|set|sets) (me|you|us) back\b|\bretails?\b|\bcosts?\b|\bprice tag\b|\bpaid\b|\bspent\b|"
                       r"\bspend\b|\bexpensive\b", re.I)
MONEY_RE = re.compile(r"\$\s?\d[\d,]*|\b\d[\d,]* ?(dollars|bucks|k)\b|\bthousand\b|\bgrand\b", re.I)
STOPW = set("the a an and has have had is are was were been always just really very honestly that these those this of from "
            "to for my your".split())


def brand_product(vo_text, doc):
    """"louis vuitton lv skate" from "The LV skates has always been ...": the first brand the VO names + the next word or two
    (the product line), singular; else the brand in the project title."""
    low = re.sub(r"[^a-z0-9 -]", " ", (vo_text or "").lower())
    hits = [(m.start(), a) for a in BRANDS for m in re.finditer(r"\b" + re.escape(a) + r"\b", low)]
    if not hits:
        low = re.sub(r"[^a-z0-9 -]", " ", (doc.get("title") or "").lower())
        hits = [(m.start(), a) for a in BRANDS for m in re.finditer(r"\b" + re.escape(a) + r"\b", low)]
    if not hits:
        return None
    pos, a = min(hits)
    after = []
    for w in low[pos + len(a):].split():
        if w in STOPW or w in BRANDS or len(after) >= 2:
            break
        after.append(re.sub(r"(?<=[a-z]{3})s$", "", w))
    full = BRANDS[a]
    return " ".join(dict.fromkeys([full] + ([a] if a != full else []) + after))


def retail_footage(vo_text, doc):
    if not vo_text:
        return []
    line = next((ln for ln in re.split(r"(?<=[.!?,])\s+", vo_text) if RETAIL_RE.search(ln) and MONEY_RE.search(ln)), None)
    q = brand_product(vo_text, doc) if line else None
    if not q:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import screenrec
    except Exception as e:
        say(f"intro: retail page unavailable ({e})")
        return []
    mp4 = screenrec.record_search(q, seconds=4.0, site="stockx")
    if not mp4:
        say(f"intro: no retail page for '{q}'")
        return []
    m = MONEY_RE.search(line)
    say(f"intro: retail line '{line.strip()[:60]}' -> StockX page '{q}'")
    return [{"src": mp4, "t": 0.0, "tag": f"screen recording: StockX page '{q}' (real pairs, real prices)", "kind": "broll",
             "for": list(dict.fromkeys([m.group(0).lower().replace(" ", "").rstrip(","), m.group(0).lower().rstrip(",")]
                                       + [x.group(0).lower() for x in RETAIL_RE.finditer(line)]))}]


# Product-camera moments where he SHOWS a detail (the box label with the size, the size tag, flipping the box over): the
# shots his own edit used in this intro (lv skatesta 2026-10-24, "I show the size tag"). Times come from his words in the
# KEPT review; the product camera must be on (right half = product, no face on it).
SHOW_RE = re.compile(r"(size tag|label|flip it over|size \d{1,2}\b|tag\b|on the bottom of the shoe|on the back|"
                     r"you can see it right here|pull tab)")


def holdup_moments(n_max=3, min_len=2.0):
    """Him holding the product up to the TALKING camera, face and product in one shot (dhgate cologne spread 2026-10-25,
    0:18: the product camera's wide desk shot was "too far away ... find a full face cam clip of me holding the bottle").
    The ranges are work/showing.json's, each confirmed by a vision look (showing.py), so this is the one exception to "never
    the talking camera": the product is the subject. The half is the one his face is on (the left camera unless the desktop
    recording sits there)."""
    try:
        sh = json.loads((PROJ / "work" / "showing.json").read_text(encoding="utf-8"))
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rng = sorted([tuple(r) for r in sh.get("ranges") or [] if r[1] - r[0] >= min_len], key=lambda r: r[0] - r[1])[:n_max]
    out = []
    for a, b in sorted(rng):
        near = [r for r in rows if a <= r["t"] <= b]
        half = "right" if near and sum(r.get("left") == "screen" for r in near) > len(near) / 2 else "left"
        out.append({"src": str(PROJ / "raw" / "camera.mp4"), "t": round(a + 0.3, 2), "crop": half,
                    "tag": "product: held up to the camera", "kind": "broll"})
    if out:
        say("intro: product held up to the talking camera at " + ", ".join(f"{f['t']:.0f}s" for f in out))
    return out


def show_moments(keep, n_max=3, clip=3.0):
    try:
        words = json.loads((PROJ / "work" / "transcript.json").read_text(encoding="utf-8"))
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    def cam_on(t):
        near = [r for r in rows if t <= r["t"] <= t + clip]
        return bool(near) and all(r.get("right") == "product" and r.get("rfx") is None and r.get("left") != "screen" for r in near)

    out, last = [], -99.0
    for i, w in enumerate(words):
        txt = re.sub(r"[^a-z0-9 ]", "", " ".join(x["w"] for x in words[i:i + 5]).lower())
        if w["s"] - last < 20 or not SHOW_RE.match(txt):
            continue
        t = w["s"] + 0.6
        if any(a <= t and t + clip <= b for a, b in keep) and cam_on(t):
            out.append({"src": str(PROJ / "raw" / "camera.mp4"), "t": round(t, 2), "crop": "right", "tag": "product detail",
                        "kind": "broll"})
            last = w["s"]
        if len(out) >= n_max:
            break
    if out:
        say(f"intro: {len(out)} product-camera detail shots (box label / size tag) at " + ", ".join(f"{f['t']:.0f}s" for f in out))
    return out
# at most 2 web pages per intro (jordan 3 2026-10-23, 0:12: four article/StockX pages in a row, "too many articles ... it
# just keeps showing over and over again ... cut that down"): PRODUCT_WEB is in priority order, the named site first


def product_web_footage(vo_text, product, n_max=2):
    if not vo_text or not product:
        return []
    try:
        sys.path.insert(0, str(LIB))
        import screenrec
    except Exception as e:
        say(f"intro: web screen recordings unavailable ({e})")
        return []
    kind = "sneaker" if re.search(FOOTWEAR, product) else product
    out = []
    for pat, site, q in PRODUCT_WEB:
        m = re.search(pat, vo_text, re.I)
        if not m or len(out) >= n_max:
            continue
        for query in q.format(p=product, kind=kind, first=product.split()[0]).split("|"):   # alternatives: the first page that has results
            mp4 = screenrec.record_search(query, seconds=3.5, site=site)
            if mp4:
                break
        if mp4:
            out.append({"src": mp4, "t": 0.0, "tag": f"screen recording: {site} page '{query}'", "kind": "broll", "for": [m.group(0).lower()]})
            say(f"intro: {site} recording for '{m.group(0)}' ({query})")
    return out


SKIP_TOPIC = set("about after again because before being best could every first going great really should something their there "
                 "these thing things think those through today video where which while would your youre gonna literally actually "
                 "extremely finding task especially trying selling place money hard earned exactly quality looking dropped giving "
                 "part crazy never stuff hand show everything bought product products customer customers resell reselling reseller "
                 "resellers influencers vendor vendors".split())


def _stem(w):
    w = re.sub(r"[^a-z0-9]", "", w.lower())
    return w[:-2] if w.endswith("es") and len(w) > 5 else w[:-1] if w.endswith("s") and len(w) > 4 else w


def _screen_rows():
    try:
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(r["t"], "left" if r.get("left") == "screen" else "right") for r in rows if r.get("left") == "screen" or r.get("right") == "screen"]


def _side_at(srows, t, tol=1.5):
    near = [s for x, s in srows if abs(x - t) <= tol]
    return max(set(near), key=near.count) if near else None


TOPIC_NOUNS = {_stem(w) for w in PRODUCT_WORDS | {"spreadsheet", "spreadsheets", "sheet", "linktree", "coupon", "coupons",
                                                   "airpod", "airpods", "maxes", "colognes", "perfume", "hoodie", "hoodies"}}


def _product_words():
    """Stems of the words that name THIS product (project title words + the product noun): "ultra", "phone"."""
    try:
        doc = json.loads((PROJ / "studio.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return set()
    ws = title_words(doc, "") + [product_noun(doc, "") or ""]
    return {_stem(w) for w in ws if len(w) >= 3}


def topic_screen_footage(src, vo_text, clip=3.0, n_max=8):
    """A thing the VO names ("spider hoodies", "cologne", "AirPod Maxes") gets the moment of the main recording where he
    talks about it on the screen (ultimate dhgate free reselling spreadsheet 2026-10-23): his own page of that product,
    date-free, "for" that word."""
    if not vo_text:
        return []
    try:
        words = json.loads((PROJ / "work" / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    srows, keep = _screen_rows(), keep_ranges()
    vo = [w for w in re.findall(r"[A-Za-z][A-Za-z']+", vo_text)]
    topics = []
    for w in vo:
        s = _stem(w)
        # only THINGS: product words and the screen nouns (best sp5der hoodie 2026-10-23: "honestly", "you'll" and "clothing"
        # each pulled a random page of the buying walkthrough into the intro)
        if len(s) >= 5 and s in TOPIC_NOUNS and s not in SKIP_TOPIC and s not in [t for t, _ in topics]:
            topics.append((s, w.lower()))
    # a VO word whose picture is somewhere else in the walkthrough: "giving it out for 100% FREE" = his Linktree with all the
    # free spreadsheets, the moment he says "link tree" (reselling spreadsheet 2026-10-23: "we could do something different
    # here"). Searched FIRST so the line gets it before the generic pages.
    cue_map = {"free": "tree"}
    topics = [(cue_map[w.lower()], w.lower()) for w in dict.fromkeys(vo) if w.lower() in cue_map] + topics
    out = []
    for s, word in topics:
        if len(out) >= n_max:
            break
        hits = [w["s"] for w in words if _stem(w["w"]) == s or (len(s) >= 6 and _stem(w["w"]).startswith(s))]
        for t in hits:
            t0 = max(0.0, t - 0.3)
            side = _side_at(srows, t0 + clip / 2)
            if not side or not any(x <= t0 and t0 + clip <= y for x, y in keep) or any(abs(t0 - o["t"]) < 4 for o in out):
                continue
            try:
                vf = next((v for v in SCREEN_VFS if not _blank(src, (t0, t0 + clip / 2, t0 + clip - 0.2), side, v) and not any(_has_date(src, x, side, v) for x in (t0, t0 + clip - 0.2))), None)
            except Exception:
                return out
            # his spreadsheet lists OTHER products (AirPods rows under "the S25 Ultra", s25 ultra 0:11): only for the words
            # that are about the sheet itself
            # ...and a PRODUCT word ("ultra", "phone") needs the product's listing on screen: his Studio link page under
            # "S25 Ultra" covered three intro lines (s25 ultra round 6)
            if vf and word not in ("spreadsheet", "spreadsheets", "sheet", "free", "tree"):
                kind = page_kind(src, t0 + clip / 2, side, vf)
                if kind == "sheet" or (kind != "listing" and _stem(word) in _product_words()):
                    continue
            # never his link-in-bio page for a topic word (dhgate watchb spread 2026-10-24: "watches" is a button on his
            # solo.to page, and its cartoon avatar card played under "APs and even Pateks")
            # (read on the FULL screen: the intro's crop cuts off the address bar that says "solo.to")
            if vf and word not in ("free", "tree") and page_kind(src, t0 + clip / 2, side, "") in ("links", "gone"):
                continue
            if vf:
                out.append({"src": str(src), "t": round(t0, 2), "crop": side, "vf": vf, "tag": f"screen: {word}", "kind": "broll", "for": [word]})
                say(f"intro: '{word}' -> his screen at {t0:.1f} s")
                break
    return out


# The DHgate line of the VO shows the product LISTING (s25 ultra 2026-10-23, 0:11 "...the S25 Ultra from DHgate": "that should
# have showed the product listing ... definitely don't show the spreadsheet, it was showing AirPods but I was talking about
# the S25"). Whisper writes DHgate as "DHK", "DHD", "the age gate".
LISTING_FOR = ["dhgate", "dh gate", "dhk", "dhd", "age gate", "listing"]
LISTING_RE = re.compile(r"add to cart|buy now|min\.? ?order|\bpieces?\b|\bsold\b|reviews?\b|quantity|shipping|\bcolou?r\b|store", re.I)
PRICE_RE = re.compile(r"us ?\$|\$ ?\d", re.I)
SHEET_RE = re.compile(r"buying price|resell(ing)? price|spread ?sheet|coupon codes|\bspread\b", re.I)
GONE_RE = re.compile(r"item not found|page not found|no longer available|has been removed|not available", re.I)


def _page_text(src, t, side, vf):
    """OCR text of the cropped screen frame (Windows OCR via _tools/privacy_ocr.py)."""
    import numpy as np
    sys.path.insert(0, r"{{KIT}}/tools")
    import privacy_ocr
    x0 = "0" if side == "left" else "iw/2"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                          "-vf", f"crop=iw/2:ih:{x0}:0,scale=1920:1080{vf}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    if len(raw) < 1920 * 1080 * 3:
        return ""
    return " ".join(text for text, _ in privacy_ocr.ocr(np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)))


# his own link-in-bio page (canada goose jacket 2026-10-24, ~0:07: the solo.to Studio page flashed in the intro, "a page with
# no context ... we need to have actual context"; s25 ultra 2026-10-23 said the same of it)
LINKS_RE = re.compile(r"solo\.to|linktr\.?ee|linktree|beacons\.ai|stan\.store|studio|my links|link in bio", re.I)


def page_kind(src, t, side, vf):
    """'listing' (a store product page: a price + cart/order/pieces/reviews words), 'sheet' (his spreadsheet: other
    products in rows), 'gone' (item not found), 'links' (his link-in-bio page) or 'other'."""
    txt = _page_text(src, t, side, vf)
    if GONE_RE.search(txt):
        return "gone"
    # link pages are recognised on the FULL screen: the intro crop (vf) cuts off the address bar that says "solo.to", and
    # his avatar page then passed as "other" twice (dhgate watchb spread 2026-10-24, under "APs" and "price tag")
    if LINKS_RE.search(txt) or (vf and LINKS_RE.search(_page_text(src, t, side, ""))):
        return "links"
    if SHEET_RE.search(txt):
        return "sheet"
    if PRICE_RE.search(txt) and LISTING_RE.search(txt):
        return "listing"
    return "other"


DATE_WORD = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?$|^20\d\d\b|^\d{1,2}/\d{1,2}(/\d{2,4})?$", re.I)


def _date_patches(src, ts, side, vf, pad=5):
    """White patches over every date word on the cropped page at the times ts (the listing's "2025" in the title, the
    delivery estimate "Jan. 30 - Feb. 4"): a drawbox chain to append to vf. A month word takes the number after it too."""
    import numpy as np
    sys.path.insert(0, r"{{KIT}}/tools")
    import privacy_ocr
    x0 = "0" if side == "left" else "iw/2"
    boxes = []
    for t in ts:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                              "-vf", f"crop=iw/2:ih:{x0}:0,scale=1920:1080{vf}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             capture_output=True).stdout
        if len(raw) < 1920 * 1080 * 3:
            continue
        for _, words in privacy_ocr.ocr(np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)):
            for k, (w, x, y, bw, bh) in enumerate(words):
                if DATE_WORD.search(w.strip(",;:()")):
                    if re.match(r"^[a-z]", w, re.I) and k + 1 < len(words):   # "Jan." + "30"
                        nx = words[k + 1]
                        bw = nx[1] + nx[3] - x
                    boxes.append((max(1, x - pad), max(1, y - pad), bw + 2 * pad, bh + 2 * pad))
    return "".join(f",drawbox=x={x}:y={y}:w={w}:h={h}:color=white:t=fill" for x, y, w, h in dict.fromkeys(boxes))


def listing_footage(src, n=2, clip=3.3, step=4.0):
    """His own screen recording of the product LISTING (the store page he walks through in the showcase), for the VO's
    DHgate line: kept, date-free, OCR-proven a listing, never his spreadsheet or an "item not found" page."""
    srows, keep = _screen_rows(), keep_ranges()
    out, last = [], -99.0
    for t, side in srows:
        if len(out) >= n:
            break
        if t - last < step or not any(x <= t and t + clip <= y for x, y in keep) or any(abs(t - o["t"]) < 8 for o in out):
            continue
        last = t
        try:
            vf = next((v for v in SCREEN_VFS if not _blank(src, (t, t + clip / 2, t + clip - 0.2), side, v)), None)
            if not vf or page_kind(src, t + clip / 2, side, vf) != "listing":
                continue
            # a listing carries dates (a "2025" in the title, the delivery estimate): white patches over them, then proven
            # date-free by a second OCR pass at the start, middle and end of the clip
            ts = (t, t + clip / 2, t + clip - 0.2)
            vf = vf + _date_patches(src, ts, side, vf)
            if any(_has_date(src, x, side, vf) for x in ts):
                continue
        except Exception as e:   # no OCR: no proof it is the listing
            say(f"intro: listing check skipped ({e})")
            return out
        out.append({"src": str(src), "t": round(t, 2), "crop": side, "vf": vf, "tag": "store listing", "kind": "broll",
                    "for": LISTING_FOR})
        say(f"intro: DHgate listing -> his screen at {t:.1f} s")
    return out


def diverse_screen_footage(src, avoid=(), n=8, clip=3.0):
    """n moments of his screen recording that look DIFFERENT from each other (16x9 thumbnails, farthest-first), spread
    over the whole kept walkthrough, date-free."""
    import numpy as np
    srows, keep = _screen_rows(), keep_ranges()
    cands = []
    last = -99.0
    for t, side in srows:
        if t - last >= 6 and any(x <= t and t + clip <= y for x, y in keep) and all(abs(t - a) > 6 for a in avoid):
            cands.append((t, side))
            last = t
    if not cands:
        return []
    thumbs = []
    for t, side in cands:
        x0 = "0" if side == "left" else "iw/2"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + 1:.2f}", "-i", str(src), "-frames:v", "1", "-vf",
                              f"crop=iw/2:ih:{x0}:0,scale=32:18", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        thumbs.append(np.frombuffer(raw, np.uint8).astype(float) if len(raw) == 576 else None)
    # never a blank / loading page: farthest-first loves outliers, and an empty white page is the biggest one (0:15 of the
    # first R01 build, "but I went out" over a white screen). A real page has text and pictures: thumbnail std >= 18
    idx = [i for i, th in enumerate(thumbs) if th is not None and th.std() >= 18]
    chosen = []
    while idx and len(chosen) < n * 2:
        if not chosen:
            k = idx[len(idx) // 2]
        else:
            k = max(idx, key=lambda i: min(np.abs(thumbs[i] - thumbs[c]).mean() for c in chosen))
            if min(np.abs(thumbs[k] - thumbs[c]).mean() for c in chosen) < 6:   # nothing new left to show
                break
        chosen.append(k)
        idx.remove(k)
    out = []
    for k in sorted(chosen, key=lambda i: cands[i][0]):
        if len(out) >= n:
            break
        t, side = cands[k]
        try:
            vf = next((v for v in SCREEN_VFS if not _blank(src, (t, t + clip / 2, t + clip - 0.2), side, v) and not any(_has_date(src, x, side, v) for x in (t, t + clip - 0.2))), None)
        except Exception:
            break
        # a walkthrough moment is a page about the PRODUCT: never his link page or a dead page anywhere in the clip (the
        # farthest-first pick loves them because they look different from every listing)
        if vf:
            try:
                kinds = {page_kind(src, x, side, vf) for x in (t, t + clip / 2, t + clip - 0.2)}
            except Exception:
                kinds = set()
            if kinds & {"links", "gone"}:
                say(f"intro: screen moment {t:.1f} s skipped ({'/'.join(sorted(kinds))} page, no context)")
                continue
            out.append({"src": str(src), "t": round(t, 2), "crop": side, "vf": vf, "tag": "screen walkthrough", "kind": "broll"})
    say(f"intro: {len(out)} different screen moments from the walkthrough")
    return out


# store/link lines in the VO ("I had the DHgate alternatives on", "where to get the DHgate ASICS") show the store page from
# his own screen recording, face-free (dhgate asics 2026-10-22). Browser bar + taskbar (clock/date) are cropped off.
SCREEN_FOR = ["dhgate", "where to get", "where to buy", "link", "website", "site", "store", "page", "online", "spreadsheet",
              # price lines show the product page, him scrolling it (prada cups 2026-10-22, 0:07 "a thousand dollars": "the product
              # view or product page would probably be better ... of me just scrolling on it")
              "dollars", "dollar", "bucks", "price"]
# in 1920x1080 space: the page without browser tabs/URL bar and taskbar; when that shows a date (store promos, delivery
# estimates sit low on the page), the upper part of the page (photo, title, price) at 1.5x
SCREEN_VFS = [",crop=1584:891:168:140,scale=1920:1080", ",crop=1280:720:320:150,scale=1920:1080"]
DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}\b|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b|\b20\d\d\b", re.I)


def _blank(src, ts, side, vf, min_std=18):
    """True when the CROPPED frame is (nearly) empty at any of ts: a white loading page, or a page whose content sits
    outside the crop (first R01 build of the reselling spreadsheet, 0:15: a plain white screen under "but I went out")."""
    import numpy as np
    x0 = "0" if side == "left" else "iw/2"
    for t in ts:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf",
                              f"crop=iw/2:ih:{x0}:0,scale=1920:1080{vf},scale=32:18", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True).stdout
        if len(raw) < 576 or np.frombuffer(raw, np.uint8).astype(float).std() < min_std:
            return True
    return False


def _has_date(src, t, side, vf):
    """OCR the cropped frame (Windows OCR via _tools/privacy_ocr.py): no dates on screen, ever."""
    import cv2
    import numpy as np
    sys.path.insert(0, r"{{KIT}}/tools")
    import privacy_ocr
    x0 = "0" if side == "left" else "iw/2"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                          "-vf", f"crop=iw/2:ih:{x0}:0,scale=1920:1080{vf}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    if len(raw) < 1920 * 1080 * 3:
        return True
    img = np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)
    return any(DATE_RE.search(text) for text, _ in privacy_ocr.ocr(img))


def screen_footage(src, n=2, clip=3.3):
    """n moments of a light (store-page) screen recording inside kept footage, from whichever half shows the screen,
    with no date anywhere in the cropped frame at the start or end of the clip."""
    try:
        rows = json.loads((PROJ / "work" / "analysis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    keep = keep_ranges()
    pool = []
    for r in rows:
        side = "left" if r.get("left") == "screen" else "right" if r.get("right") == "screen" else None
        white = r.get("lwhite" if side == "left" else "white") or 0
        if side and white > 0.35 and any(x <= r["t"] and r["t"] + clip <= y for x, y in keep):
            pool.append((r["t"], side))
    out, step = [], max(1, len(pool) // 40)
    # every candidate, starting from the middle third (the product page, not the first click), keep the first n clean ones
    order = pool[len(pool) // 3::step] + pool[:len(pool) // 3:step]
    for t, side in order:
        if len(out) >= n:
            break
        if any(abs(t - o["t"]) < 8 for o in out):
            continue
        try:
            vf = next((v for v in SCREEN_VFS if not _blank(src, (t, t + clip / 2, t + clip - 0.2), side, v) and not any(_has_date(src, x, side, v) for x in (t, t + clip / 2, t + clip - 0.2))), None)
        except Exception as e:   # no OCR = no way to prove the frame is date-free: leave the store page out
            say(f"intro: screen clips skipped (OCR unavailable: {e})")
            return []
        if vf:
            out.append({"src": str(src), "t": t, "crop": side, "vf": vf, "tag": "store page", "kind": "broll", "for": SCREEN_FOR})
    return sorted(out, key=lambda o: o["t"])


def reselling_template(doc):
    """Reselling / spreadsheet videos always use the reselling intro style, R01 Smoke Words, the one both approved
    reselling videos have (dhgate cologne spread 2026-10-25: R02 Grid Notebook came up in the rotation, "I don't like this
    whole style of intro template for the reselling videos ... follow our reselling template from the ultimate reselling
    video or the top 5 reselling products"). The rotation is for single-product reviews only."""
    t = f"{doc.get('title', '')} {doc.get('channel', '')}".lower()
    return "R01" if re.search(r"\bresell\w*|\bspread(sheet)?s?\b|\bresells\b", t) else ""


def prior_template(build):
    """A rebuild of the same project keeps its style (only a new video moves the rotation on)."""
    try:
        tid = json.loads((build / "intro.json").read_text(encoding="utf-8"))["template"]
    except Exception:
        return ""
    # ...unless he has turned that style off since (lv trainer 2026-10-23, R07's receipt: "the motion graphic just doesn't
    # seem as interesting"): then the rotation picks the next one
    for tj in (LIB / "templates" / "review").glob(f"{tid}-*/template.json"):
        if json.loads(tj.read_text(encoding="utf-8")).get("status", "ready") != "ready":
            return ""
    return tid


def prior_music(build, doc=None):
    """...and its music (amiri jeans 2026-10-22: a revision rebuild without --music moved the music rotation on and
    swapped the intro's beat between drafts), unless he asked for another one: settings.intro_music_skip lists the beats
    he turned down for this video (s25 ultra 2026-10-23, "let's try a different soundtrack"), the rotation picks a new one."""
    try:
        m = json.loads((build / "intro.json").read_text(encoding="utf-8")).get("music") or ""
        skip = {os.path.normcase(os.path.normpath(x)) for x in ((doc or {}).get("settings", {}).get("intro_music_skip") or [])}
        if m and os.path.normcase(os.path.normpath(m)) in skip:
            return ""
        return m if m and os.path.exists(m) else ""
    except Exception:
        return ""


# The product-review STYLE POOL (user 2026-10-26: "can we still have multiple styles" -> yes, but every style follows the
# same spine with footage full frame, a few approved styles only, picked to FIT the video, never the same twice in a row on
# a channel, and kept on revisions). The panel / card templates (R05 R06 R10 R13 ...) are out: they shrink the footage.
# checkerboard (the house formula, needs his avatar PNG) is not built yet: R21 stands in for it.
STYLE_POOL = {
    "R21": "smoke cloud",      # R01 engine + editor captions; story / news / default
    "R02": "grid notebook",    # comparisons, real vs fake, lists
    "R22": "crumpled paper",   # deals, codes, apps
}
STYLE_FIT = [("R02", r"\b(vs\.?|versus|compared?|comparison|real (one|pair)?s? (vs|and|or) (fake|rep)|difference|side by side|"
                     r"which (one|pair) is|best (and|vs) worst|top \d|ranking|ranked)\b"),
             ("R22", r"\b(promo|coupon|discount|code|codes|cash ?back|sign ?up bonus|referral|app|free (shipping|stuff))\b"),
             ("R21", r"\b(last week|heard|news|everyone'?s? (talking|buzzing)|story|scam|fake|caught|popular|hype)\b")]


def pick_style(doc):
    """The pool style that fits this video's voiceover / title best; never the one this channel's last video got."""
    hist_p = LIB / "_state" / "style_history.json"
    try:
        hist = json.loads(hist_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    ch = (doc.get("channel") or "?").strip()
    last = (hist.get(ch) or [None])[-1]
    text = f"{doc.get('title', '')} {vo_words_text(doc) or ''}".lower()
    ranked = [tid for tid, pat in STYLE_FIT if re.search(pat, text)] + ["R21", "R02", "R22"]
    order = list(dict.fromkeys(ranked))
    tid = next((t for t in order if t != last), order[0])
    hist.setdefault(ch, []).append(tid)
    hist[ch] = hist[ch][-10:]
    try:
        hist_p.parent.mkdir(exist_ok=True)
        hist_p.write_text(json.dumps(hist, indent=1), encoding="utf-8")
    except OSError:
        pass
    say(f"intro style: {tid} ({STYLE_POOL.get(tid, tid)}) for {ch} (fits: {', '.join(order[:3])}; last on this channel: {last or 'none'})")
    return tid


def next_template():
    """Least-recently-used review template; seeds the rotation so the first cycle starts with FIRST_CYCLE."""
    p = LIB / "_state" / "rotation.json"
    rot = json.loads(p.read_text()) if p.exists() else {}
    if "review" not in rot:
        ids = sorted(d.name.split("-")[0] for d in (LIB / "templates" / "review").iterdir() if (d / "template.json").exists())
        rot["review"] = FIRST_CYCLE + [i for i in ids if i not in FIRST_CYCLE]   # oldest first = picked first
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(rot, indent=1))
    return "auto"


def intro_title(doc, vo):
    """The on-screen intro title. A project named from the recording's first spoken words ("Okay guys, so I was just on
    River SMP and River actually just hit me u", prada cups 2026-10-22) put that sentence on the title card; then the
    VO's file name ("prada cups dhgate.wav"), which the user names after the video, is the better title."""
    title = (doc.get("title") or "").strip()
    stem = re.sub(r"[_-]+", " ", Path(vo).stem).strip()
    spoken = len(title.split()) > 6 or bool(re.search(r"[,?!]|\b(okay|guys|so i|i was|hey)\b", title.lower()))
    return stem if spoken and stem else title


def product_noun(doc, vo):
    """What kind of thing the video reviews ("dhgate cartier watch" -> "watch"): the picture search pairs a bare brand
    with it, so "Cartier" finds a Cartier watch, not Parc national de la Jacques-Cartier (dhgate cartier watch 0:00)."""
    words = title_words(doc, vo)
    return words[-1].rstrip("s") if words else ""


def title_words(doc, vo):
    """The project title's words without filler; the VO file name only when the title is a spoken sentence (amiri jeans
    2026-10-22: the VO "amiri jeas review.wav" came last and its typo made the product "jea")."""
    words = re.findall(r"[a-z]+", intro_title(doc, vo).lower())
    return [w for w in words if w not in ("dhgate", "review", "reviews", "honest", "the", "a", "best", "on", "from", "vs", "and")]


def product_brand(doc, vo):
    """The brand for the title lockup ("amiri jeans dhgate" -> "Amiri"): the title words before the product noun."""
    words = title_words(doc, vo)
    return " ".join(words[:-1]).title() if len(words) > 1 else ""


def main():
    doc = json.loads((PROJ / "studio.json").read_text(encoding="utf-8-sig"))
    slot = doc.get("slots", {}).get("intro_vo") or doc.get("slots", {}).get("intro") or ""
    if not slot:
        cands = sorted((PROJ / "intro").glob("*")) if (PROJ / "intro").is_dir() else []
        slot = str(next((c for c in cands if c.suffix.lower() in AUDIO + (".mp4", ".mov")), "") or "")
    if not slot or not os.path.exists(slot):
        say("no intro in this project: nothing to do")
        return
    final = OUT / "final.mp4"
    if not final.exists():
        raise SystemExit("output/final.mp4 is missing (edit_review.py first)")
    if Path(slot).suffix.lower() in AUDIO:
        build = PROJ / "intro" / "build"
        intro = build / "renders" / "intro.mp4"
        cam = PROJ / "raw" / "camera.mp4"
        # ...also when he asked for another style (settings.intro_template) or turned the built one off: the intro was
        # reused as it was (s25 ultra round 2: the Magazine Cover he rejected came back after R01 was set)
        try:
            built = json.loads((build / "intro.json").read_text(encoding="utf-8"))["template"]
        except Exception:
            built = ""
        want = doc.get("settings", {}).get("intro_template") or reselling_template(doc)
        restyle = bool(built) and ((want and want != built) or prior_template(build) != built)
        # ...or he turned its beat down (settings.intro_music_skip): the music is baked into the render
        try:
            had = json.loads((build / "intro.json").read_text(encoding="utf-8")).get("music") or ""
        except Exception:
            had = ""
        restyle = restyle or bool(had and not prior_music(build, doc))
        # ...or his pinned intro shots changed (settings.intro_pins, build_intro.apply_pins)
        pins = doc.get("settings", {}).get("intro_pins") or []
        try:
            had_pins = json.loads((build / "extra.json").read_text(encoding="utf-8")).get("pins") or []
        except Exception:
            had_pins = []
        restyle = restyle or pins != had_pins
        # ...and when the intro code itself changed since this render (s25 ultra round 5: four intro fixes never reached the
        # draft, the old intro was reused because only the VO / sections / B-roll were watched)
        code = [LIB / "build_intro.py", LIB / "director_rules.md", LIB / "pics.py", LIB / "kit" / "kit.js", Path(__file__),
                # the footage finders too (reselling spreadsheet 2026-10-23: the creator-clip date filter would not have
                # reached the draft, the intro was only rebuilt for build_intro/pics/kit changes)
                LIB / "creator_clips.py", LIB / "screenrec.py", LIB / "sitepage.py", LIB / "named_sites.json",
                PROJ / "raw" / "sites.txt", *sorted((PROJ / "raw").glob("site_*.json")),
                # ...and the templates themselves (watch spreadsheet 2026-10-24: an R01 scene.js fix never reached the draft,
                # the 16:44 intro was only re-joined), plus the check that re-pins shots
                LIB / "intro_check.py", *sorted((LIB / "templates").glob("*/*/scene.js")),
                *sorted((LIB / "templates").glob("*/*/template.json"))]
        # intro lock (user 2026-10-24: "speed up product reviews"): 47 of 60 review builds re-planned + re-rendered an intro
        # nobody had a note on (~8-10 min each), mostly because the shared intro code had changed that day. A built intro now
        # stays as it is unless this build may touch it (STUDIO_INTRO_REBUILD: intro-only revision, a batch with intro
        # notes, a fresh build, or {"intro": "rebuild"} on /api/project/run). A new VO or a style / music / pin change in
        # settings still rebuilds. STUDIO_INTRO_LOCK unset = a build started by older Studio code = the old rules.
        locked = (os.environ.get("STUDIO_INTRO_LOCK") == "1" and os.environ.get("STUDIO_INTRO_REBUILD") != "1"
                  and intro.exists() and intro.stat().st_size > 100000)
        if locked and not restyle and not stale(intro, slot):
            say("intro: kept as it is (locked: no note in this batch touches the intro)")
        elif restyle or stale(intro, slot) or (not locked and stale(
                intro, PROJ / "work" / "sections.json", *[str(p) for p in (PROJ / "raw" / "broll").glob("*")],
                *[str(c) for c in code if c.exists()])):
            tid = doc.get("settings", {}).get("intro_template") or reselling_template(doc) or prior_template(build) or pick_style(doc)
            # the intro matches the main video's frame rate (60 for a 60 fps recording; watch spreadsheet 2026-10-24:
            # "it still feels jittery", a 30 fps intro in front of a 60 fps main video)
            try:
                _fr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                                      "-of", "csv=p=0", str(cam)], capture_output=True, text=True).stdout.strip() or "30/1"
                _n, _d = _fr.split("/")
                os.environ["INTRO_FPS"] = "60" if float(_n) / float(_d or 1) >= 50 else "30"
            except Exception:  # noqa
                os.environ["INTRO_FPS"] = "30"
            foot = footage(cam, doc) if cam.exists() else own_broll(doc)
            build.mkdir(parents=True, exist_ok=True)
            fj = build / "footage.json"
            fj.write_text(json.dumps(foot, indent=1), encoding="utf-8")
            # the DHgate price from the main edit's price pop-up (work/price__<n>.png): the intro's "fraction of the cost"
            # line gets a retail-vs-DHgate price graphic (dhgate cartier watch 2026-10-22: "more motion graphics")
            ex = build / "extra.json"
            prices = sorted(int(m.group(1)) for p in (PROJ / "work").glob("price__*.png") if (m := re.match(r"price__(\d+)", p.stem)))
            # + his special requests from New Project (2026-10-23): the intro director follows the ones about the intro
            ex.write_text(json.dumps({"product_price": prices[0] if prices else None, "product": product_noun(doc, slot),
                                     "brand": product_brand(doc, slot), "requests": doc.get("settings", {}).get("requests", ""),
                                     "pins": pins, "avoid_music": doc.get("settings", {}).get("intro_music_skip") or []}),
                          encoding="utf-8")
            say(f"intro: building {tid} from {Path(slot).name} with {len(foot)} product clips")
            cmd = [PY, "-X", "utf8", str(LIB / "build_intro.py"), "--type", "review", "--template", tid, "--vo", slot,
                   "--title", intro_title(doc, slot), "--out", str(build), "--footage", str(fj), "--extra", str(ex),
                   "--render"] + (["--music", prior_music(build, doc)] if prior_music(build, doc) else [])
            r = subprocess.run(cmd, cwd=str(LIB))
            if r.returncode or not intro.exists():
                raise RuntimeError(f"build_intro.py failed ({r.returncode})")
            # the intro checks itself before he sees it (intro_library/intro_check.py, 2026-10-23: "the AI watches its own
            # intro line by line against the rules and fixes it before I ever see it"): every bad shot becomes a pin on its
            # words, re-rendered, checked once more. settings.intro_check = false switches it off.
            # OFF by default since 2026-10-26 (user: "turn off the auto rebuild since it is slowing us down"): the project
            # setting, else the machine's data/settings.json intro_check, else off
            try:
                _machine = json.loads((Path(__file__).resolve().parents[2] / "data" / "settings.json").read_text(encoding="utf-8"))
            except Exception:
                _machine = {}
            if doc.get("settings", {}).get("intro_check", _machine.get("intro_check", False)):
                try:
                    sys.path.insert(0, str(LIB))
                    import intro_check
                    # two fix rounds, the third look only reports (spreadsheet: round 2 found 3 more). An intro-only revision
                    # (STUDIO_INTRO_ONLY, his notes already direct the shots) gets one fix round: each round is a full re-render
                    # ...and so does a full revision that re-makes the intro because of his notes (STUDIO_INTRO_REBUILD=1,
                    # 2026-10-24 speed pass: watchb's revised intro took 12.5 min, three renders + two AI looks)
                    last = 2 if (os.environ.get("STUDIO_INTRO_ONLY") or os.environ.get("STUDIO_INTRO_REBUILD") == "1") else 3
                    for rnd in range(1, last + 1):
                        res = intro_check.check(str(build), say)
                        if not res["pins"] or rnd == last:
                            break
                        e = json.loads(ex.read_text(encoding="utf-8"))
                        have = {p["from"] for p in e.get("auto_pins", [])}
                        e["auto_pins"] = e.get("auto_pins", []) + [p for p in res["pins"] if p["from"] not in have]
                        ex.write_text(json.dumps(e), encoding="utf-8")
                        say(f"intro: self-check fixed {len(res['pins'])} shot(s), rendering again")
                        good = intro.with_name("intro_checked_prev.mp4")
                        shutil.copy2(intro, good)
                        # the first pass's plan is kept (build_intro --reuse-plan): only the flagged shots change, no new AI plan
                        r = subprocess.run(cmd + ["--reuse-plan"], cwd=str(LIB))
                        if r.returncode or not intro.exists() or intro.stat().st_size < 100000:
                            # a failed re-render keeps the last good intro (best sp5der hoodie 2026-10-23: the round-2
                            # re-render's encode died and the draft went out with NO intro)
                            shutil.copy2(good, intro)
                            say(f"intro: the self-check re-render failed ({r.returncode}); keeping the previous render")
                            break
                except RuntimeError:
                    raise
                except Exception as err:   # noqa: the check never stops a build
                    say(f"intro: self-check skipped ({type(err).__name__}: {str(err)[:120]})")
    else:
        intro = Path(slot)
        say(f"intro: using the finished intro {intro.name}")
    joined, prev = OUT / "final_intro.mp4", OUT / "preview_intro_540p.mp4"
    if stale(joined, intro, final):
        say("intro: joining intro + final")
        # a slide + whoosh from the intro into the talking part, like every segment change (s25 ultra 2026-10-23)
        subprocess.run([PY, "-X", "utf8", str(JOIN), str(intro), str(final), str(joined), "--cq", "17", "--slide", "0.3"], check=True)
    if stale(prev, joined):
        say("intro: 540p preview")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-vf", "scale=960:540", "-c:v", "h264_nvenc", "-profile:v", "high",
                        "-pix_fmt", "yuv420p", "-cq", "26", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(prev)], check=True)
    (OUT / "intro_report.txt").write_text(f"intro OK: {intro}\n", encoding="utf-8")
    say(f"intro: done -> {joined.name}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:   # the edit itself stays good: report, don't fail the build
        OUT.mkdir(exist_ok=True)
        (OUT / "intro_report.txt").write_text(f"intro FAILED: {e}\n\n{traceback.format_exc()}", encoding="utf-8")
        say(f"INTRO FAILED (draft kept without intro): {e}")
