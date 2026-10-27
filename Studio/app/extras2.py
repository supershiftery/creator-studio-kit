"""Second feature batch: one-shot Claude writing (descriptions, titles, short titles), thumbnail frame suggestions,
new-recording watcher, disk cleanup, edit stats, weekly report, VA copy pack, Shorts Factory."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import chat
import jobs
import media
import notify
import store
import tracker
from recipes import common
from recipes import get as recipe

TOOLS = Path(__file__).resolve().parent / "tools"
GAMING = Path(__file__).resolve().parent / "gaming"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def py():
    return store.settings().get("python") or sys.executable


# ---------------------------------------------------------------- one-shot Claude (Opus 5.5, no tools, no session)
def ask_once(prompt, cwd=None, timeout=300):
    # lean (2026-10-22): no CLAUDE.md / memory / hooks / skills / MCP; a plain -p call carried ~146k tokens of context
    cmd = [chat.claude_exe(), "-p", prompt, "--model", chat.MODEL, "--output-format", "json", "--max-turns", "1", "--no-session-persistence", "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands"]
    r = subprocess.run(cmd, cwd=cwd or str(store.HOME), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
    try:
        j = json.loads(r.stdout)
        out = j.get("result") or ""
    except ValueError:
        out = r.stdout or r.stderr
    if "Not logged in" in out or "/login" in out:
        raise RuntimeError("The Claude Code CLI is not signed in (Revisions tab → Sign in).")
    return out.strip()


def transcript_text(doc, limit=14000):
    P = recipe(doc["type"]).paths(doc)
    wp = P.get("transcript") if doc["type"] == "review" else P.get("words")
    words = store.read_json(wp, []) if wp else []
    if isinstance(words, dict):
        words = words.get("words") or []
    keep = common.keep_ranges(P["cuts"]) if P.get("cuts") else None
    out = []
    for w in words:
        s = w.get("s", w.get("start", 0))
        if keep and not any(a - 0.05 <= s <= b + 0.05 for a, b in keep):
            continue
        out.append(w.get("w") or w.get("word", ""))
    text = " ".join(out)
    return text[:limit] + (" …" if len(text) > limit else "")


def _channel_context(doc):
    bits = []
    if doc["type"] == "phone":
        codes = store.read_json(r"{{KIT}}/tools\phone_edit\codes.json", {}) or {}
        bits.append("The creator's own referral/promo codes (use the ones the video covers): " + json.dumps({k: v for k, v in codes.items() if not k.startswith("_")}))
    chap = ""
    if doc["type"] == "gaming":
        cp = recipe("gaming").paths(doc)["chapters"]
        if cp.exists():
            chap = cp.read_text(encoding="utf-8")
    if chap:
        bits.append("Chapters (keep these timestamps exactly):\n" + chap)
    return "\n".join(bits)


RULES = ("Rules: no years, months or dates anywhere (evergreen); plain text for YouTube "
         "(no markdown); keep any existing links and codes exactly as given; do not invent codes, links or prices.")


# the approved Top N description (user 2026-10-27: "as long as the main info, such as the links, are there and like the top
# five, top 10 format, that's like already good"): every Top N video's description follows its format
TOPN_TEMPLATE = r"{{GAMING_ROOT}}\Top 10 Minecraft Servers\YouTube description.txt"
LINK_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


def project_links(doc):
    """links the video's own files already hold (article pages, realm pages, the full-list page): never invented ones"""
    out = []
    root = Path(doc["path"])
    for f in list(root.glob("*.*")) + list(root.glob("Edit/*.*")) + list(root.glob("Shorts/*.txt")):
        n = f.name.lower()
        if f.suffix.lower() not in (".txt", ".md", ".json", ".csv") or "description" in n or n.startswith("studio") or f.stat().st_size > 2_000_000:
            continue
        out += LINK_RE.findall(f.read_text(encoding="utf-8", errors="replace"))
    out += [v for v in (doc.get("links") or {}).values() if isinstance(v, str) and v.startswith("http")]
    return [u.rstrip(".,;") for u in dict.fromkeys(out) if "youtu" not in u][:60]


def write_description(doc):
    d = doc["slots"].get("description")
    existing = Path(d).read_text(encoding="utf-8", errors="replace")[:4000] if d and os.path.exists(d) else ""
    fmt = ("Structure: a 2-3 line hook that says what the viewer gets, then the codes/links section if any, then chapters if given, "
           "then 3-6 relevant hashtags.")
    if re.search(r"\btop\s*\d+", doc["title"], re.I) and os.path.exists(TOPN_TEMPLATE):
        fmt = ("Follow the FORMAT of this approved Top N description (hook, the full-list link if known, the ranked list counting down "
               "with one link per entry, how to join if it applies, chapters, a comment question), with this video's own entries:\n---\n"
               + Path(TOPN_TEMPLATE).read_text(encoding="utf-8", errors="replace")[:2500] + "\n---")
    links = project_links(doc)
    prompt = (f"Write the YouTube description for the video '{doc['title']}' on the channel {doc.get('channel') or '?'} ({store.TYPES[doc['type']]['label']}).\n"
              f"{RULES} Use ONLY links from 'Known links'; an entry without a known link gets none.\n{fmt}\n"
              "Under 2500 characters. Reply with ONLY the description text.\n\n"
              + (f"Current description (keep its links/codes, improve the rest):\n{existing}\n\n" if existing else "")
              + "Known links:\n" + ("\n".join(links) or "none") + "\n\n"
              + _channel_context(doc) + "\n\nTranscript of the edited video:\n" + transcript_text(doc))
    return ask_once(prompt, cwd=doc["path"])


def title_ideas(doc):
    prompt = (f"Give 10 YouTube title options for this {store.TYPES[doc['type']]['label']} video (working title '{doc['title']}', channel {doc.get('channel') or '?'}). "
              "Mix curiosity, a concrete benefit or number, and the search phrase people type. Under 70 characters each, no dates or years, no clickbait lies, "
              "no emojis. Reply with ONLY the 10 titles, one per line, no numbering.\n\nTranscript:\n" + transcript_text(doc, 9000))
    out = ask_once(prompt, cwd=doc["path"])
    titles = [re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", l).strip().strip('"') for l in out.splitlines() if l.strip()]
    return [t for t in titles if 8 < len(t) < 110][:12]


# ---------------------------------------------------------------- thumbnail frame suggestions (face + sharpness)
def frame_suggestions(doc, n=12):
    import cv2
    import numpy as np
    outs = recipe(doc["type"]).outputs(doc)
    src = doc.get("source") or ""
    info = media.probe(src) if src else None
    sbs = media.layout_of(info) == "side-by-side"
    video = src if sbs else (outs[-1]["file"] if outs else src)
    if not video or not os.path.exists(video):
        raise ValueError("no footage yet")
    cache = Path(doc["path"]) / "Thumbnail" / "suggestions.json"
    key = f"{video}|{os.path.getmtime(video)}"
    old = store.read_json(cache, {}) or {}
    if old.get("key") == key and old.get("frames"):
        return old["frames"]
    W, H = (960, 270) if sbs else (640, 360)
    p = subprocess.run(["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", video, "-fps_mode", "vfr", "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True, creationflags=CREATE_NO_WINDOW)
    # timestamps of the keyframes
    pt = subprocess.run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0", "-show_entries", "frame=pts_time", "-of", "csv=p=0", video],
                        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW).stdout.split()
    times = [float(x) for x in pt if x.replace(".", "", 1).isdigit()]
    size = W * H * 3
    nfr = min(len(p.stdout) // size, len(times))
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    model = r"{{KIT}}/review_pipeline\models\face_landmarker.task"
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=model),
                                                                                output_face_blendshapes=True, num_faces=1))
    face_side = "left"   # the user's OBS profile: webcam left, screen right
    cands = []
    step = max(1, nfr // 400)
    for i in range(0, nfr, step):
        fr = np.frombuffer(p.stdout[i * size:(i + 1) * size], np.uint8).reshape(H, W, 3)
        halves = [("left", fr[:, :W // 2]), ("right", fr[:, W // 2:])] if sbs else [(None, fr)]
        for crop, img in halves:
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
            bright = float(g.mean())
            want_face = (not sbs) or crop == face_side
            expr, fa = 0.0, 0.0
            if want_face:
                res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))))
                if res.face_landmarks:
                    xs = [q.x for q in res.face_landmarks[0]]
                    ys = [q.y for q in res.face_landmarks[0]]
                    fa = (max(xs) - min(xs)) * (max(ys) - min(ys))
                    bs = {c.category_name: c.score for c in (res.face_blendshapes[0] if res.face_blendshapes else [])}
                    # thumbnail faces: mouth open, brows up, eyes wide, big smile
                    expr = (bs.get("jawOpen", 0) * 1.5 + bs.get("browInnerUp", 0) + (bs.get("eyeWideLeft", 0) + bs.get("eyeWideRight", 0)) / 2
                            + (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2)
            if sbs and not want_face:
                kind = "scene"
            elif fa > 0.02:
                kind = "face"
            elif sbs:
                continue
            else:
                kind = "scene"
            score = min(sharp, 1500) / 1500 * 2 + (expr * 4 + fa * 5 if kind == "face" else 0) - (2 if bright < 40 else 0)
            cands.append({"t": round(times[i], 2), "crop": crop, "kind": kind, "score": round(score, 3), "expr": round(expr, 2)})
    picked = []
    for kind_quota in (("face", n // 2), ("scene", n - n // 2)):
        kind, q = kind_quota
        for c in sorted([c for c in cands if c["kind"] == kind], key=lambda c: -c["score"]):
            if len([x for x in picked if x["kind"] == kind]) >= q:
                break
            if all(abs(c["t"] - x["t"]) > 20 for x in picked):
                picked.append(c)
    for c in picked:
        c["file"] = video
    cache.parent.mkdir(parents=True, exist_ok=True)
    store.write_json(cache, {"key": key, "frames": picked})
    return picked


# ---------------------------------------------------------------- new-recording watcher
WATCH = {"seen": None, "pending": {}, "new": []}


def _scan_recordings():
    out = {}
    for r in store.settings()["recordings"]:
        if os.path.isdir(r):
            for e in Path(r).iterdir():
                if e.is_file() and e.suffix.lower() == ".mp4":
                    try:
                        out[str(e)] = e.stat().st_size
                    except OSError:
                        pass
    return out


def watcher_loop():
    while True:
        try:
            now = _scan_recordings()
            if WATCH["seen"] is None:
                WATCH["seen"] = set(now)
            for path, size in now.items():
                if path in WATCH["seen"]:
                    continue
                prev = WATCH["pending"].get(path)
                if prev is not None and prev == size and size > 5_000_000:   # finished writing
                    WATCH["seen"].add(path)
                    WATCH["pending"].pop(path, None)
                    WATCH["new"].insert(0, {"path": path, "name": os.path.basename(path), "when": store.now()})
                    del WATCH["new"][10:]
                    dur = media.cached_duration(path)
                    notify.notify("New recording", f"{os.path.basename(path)} · {int(dur // 60)}:{int(dur % 60):02d}. Open {{STUDIO_NAME}} to start a project.")
                    threading.Thread(target=media.compute_label, args=(path,), daemon=True).start()
                else:
                    WATCH["pending"][path] = size
        except Exception:
            pass
        time.sleep(15)


def start_watcher():
    threading.Thread(target=watcher_loop, daemon=True).start()


def new_recordings():
    used = {(d.get("source") or "").lower() for d in store.all_projects()}
    return [dict(r, label=media.cached_label(r["path"])) for r in WATCH["new"] if r["path"].lower() not in used and os.path.exists(r["path"])]


# ---------------------------------------------------------------- disk cleanup (regenerable intermediates only)
def _cleanup_candidates(doc):
    p = Path(doc["path"])
    pats = {
        "gaming": ["Edit/studio/segs-*/*.mp4", "Edit/studio/body-*.mp4", "Edit/studio/broll-*.mp4", "Edit/studio/music-*.wav", "Edit/studio/music-tmp.wav"],
        "phone": ["edit/cut-full-noblur.mp4", "edit/build/*.wav", "edit/build/*.png", "draft-cut-*-halfsize.mp4", "edit/main-test.mp4"],
        "review": ["work/*.mp4", "work/*.wav"],
        "haul": ["Edit/studio/haul_voice.wav"],
        "short": ["Edit/studio/haul_voice.wav"],
    }[doc["type"]]
    files = []
    for pat in pats:
        for f in p.glob(pat):
            if f.is_file():
                files.append(f)
    # QC folders of renders that no longer exist / older drafts
    for d in list(p.glob("*_check")) + list(p.glob("Edit/*_check")) + list(p.glob("output/*_check")):
        stem = d.name[:-6]
        if not any((d.parent / (stem + ext)).exists() for ext in (".mp4",)):
            files += [f for f in d.rglob("*") if f.is_file()]
    keep = {str(Path(doc.get("source") or "")).lower()}
    return [f for f in files if str(f).lower() not in keep]


def cleanup_scan(doc):
    files = _cleanup_candidates(doc)
    total = sum(f.stat().st_size for f in files)
    by = {}
    for f in files:
        k = f.parent.name if f.parent != Path(doc["path"]) else "(project folder)"
        by.setdefault(k, [0, 0])
        by[k][0] += 1
        by[k][1] += f.stat().st_size
    return {"files": len(files), "bytes": total, "groups": [{"folder": k, "files": v[0], "bytes": v[1]} for k, v in sorted(by.items(), key=lambda x: -x[1][1])]}


def cleanup_run(doc):
    """Send the regenerable files to the Recycle Bin (recoverable), never a hard delete."""
    files = _cleanup_candidates(doc)
    if not files:
        return {"moved": 0, "bytes": 0}
    total = sum(f.stat().st_size for f in files)
    lst = store.DATA / "cleanup-list.txt"
    lst.write_text("\n".join(str(f) for f in files), encoding="utf-8")
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; Get-Content -LiteralPath '" + str(lst) + "' -Encoding UTF8 | ForEach-Object { "
          "if (Test-Path -LiteralPath $_) { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($_, 'OnlyErrorDialogs', 'SendToRecycleBin') } }")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=600)
    left = [f for f in files if f.exists()]
    return {"moved": len(files) - len(left), "bytes": total - sum(f.stat().st_size for f in left)}


# ---------------------------------------------------------------- edit stats
def edit_stats(doc):
    P = recipe(doc["type"]).paths(doc)
    cd = store.read_json(P.get("cuts"), None) if P.get("cuts") else None
    keep = common.keep_ranges(P["cuts"]) if P.get("cuts") else None
    if not keep:
        return None
    info = media.probe(doc["source"]) if doc.get("source") else None
    raw = (info or {}).get("duration") or (keep[-1][1] if keep else 0)
    kept = sum(b - a for a, b in keep)
    reasons = {}
    if isinstance(cd, dict):
        for c in cd.get("cuts", []) or []:
            why = (c.get("why") or "").lower()
            k = ("retake" if "retake" in why else "stuck line" if "stuck" in why else "mutter" if "mutter" in why else "aside" if "aside" in why else
                 "your notes" if "user note" in why else "outside sections" if "outside" in why else "silence" if "silence" in why else "stutter" if "stutter" in why else "other")
            reasons[k] = reasons.get(k, 0) + 1
    words = store.read_json(P.get("transcript") if doc["type"] == "review" else P.get("words"), []) or []
    if isinstance(words, dict):
        words = words.get("words") or []
    kept_words = sum(1 for w in words if any(a - 0.05 <= w.get("s", w.get("start", 0)) <= b + 0.05 for a, b in keep))
    pieces = len(keep)
    return {"raw": round(raw, 1), "kept": round(kept, 1), "cut_pct": round(100 * (1 - kept / raw), 1) if raw else 0, "pieces": pieces,
            "avg_piece": round(kept / pieces, 1) if pieces else 0, "longest_piece": round(max((b - a for a, b in keep), default=0), 1),
            "wpm": round(kept_words / (kept / 60)) if kept else 0, "reasons": reasons, "kept_words": kept_words}


# ---------------------------------------------------------------- weekly output report
def weekly_report(weeks=6):
    docs = store.all_projects()
    today = date.today()
    start = today - timedelta(days=today.weekday())
    rows = []
    for k in range(weeks - 1, -1, -1):
        ws = start - timedelta(weeks=k)
        we = ws + timedelta(days=6)
        shipped = [d for d in docs if tracker.stage(d) in ("shipped", "published") and (tracker.parse_date(d.get("shipped_on") or d.get("published_on") or "") or date(1970, 1, 1)) >= ws
                   and (tracker.parse_date(d.get("shipped_on") or d.get("published_on") or "") or date(1970, 1, 1)) <= we]
        builds = [b for d in docs for b in d.get("builds", []) if b.get("status") == "done" and ws <= (tracker.parse_date(b.get("when", "")) or date(1970, 1, 1)) <= we]
        rows.append({"week": str(ws), "label": ws.strftime("%b %d"), "shipped": len(shipped), "titles": [d["title"] for d in shipped],
                     "builds": len(builds), "build_min": round(sum(b["secs"] for b in builds) / 60), "footage_min": round(sum(b.get("minutes", 0) for b in builds))})
    allb = [b for d in docs for b in d.get("builds", []) if b.get("status") == "done" and b.get("minutes")]
    speed = round(sum(b["secs"] / 60 / b["minutes"] for b in allb) / len(allb), 2) if allb else None
    streak = 0
    for r in reversed(rows):
        if r["shipped"]:
            streak += 1
        else:
            break
    return {"weeks": rows, "speed": speed, "streak": streak, "total_shipped": sum(r["shipped"] for r in rows)}


# ---------------------------------------------------------------- copy pack for the VA
def va_pack(doc):
    r = recipe(doc["type"])
    outs = r.outputs(doc)
    final = next((o["file"] for o in reversed(outs) if o["kind"] == "final"), "")
    desc = ""
    d = doc["slots"].get("description")
    if d and os.path.exists(d):
        desc = Path(d).read_text(encoding="utf-8", errors="replace")
    lines = [f"TITLE: {doc.get('yt_title') or doc['title']}", f"CHANNEL: {doc.get('channel') or '?'}", "",
             "DESCRIPTION:", desc.strip() or "(not written yet)", ""]
    if final:
        lines.append(f"VIDEO FILE: {final}")
    drv = tracker.drive_status(doc)
    lines.append(f"DRIVE FOLDER: {drv['folder']}{'' if drv['exists'] else ' (not sent yet)'}")
    if doc["slots"].get("thumbnail"):
        lines.append(f"THUMBNAIL: {doc['slots']['thumbnail']}")
    sd = Path(doc["path"]) / "Shorts"
    shorts = sorted(sd.glob("*.mp4")) if sd.is_dir() else []
    if shorts:
        lines += ["", f"SHORTS ({len(shorts)}): set each one's Related video to the full upload"]
        for s in shorts:
            t = s.with_suffix(".txt")
            title = ""
            if t.exists():
                m = re.search(r"TITLE:\s*(.+)", t.read_text(encoding="utf-8", errors="replace"))
                title = m.group(1).strip() if m else ""
            lines.append(f"  - {s.name}{' · ' + title if title else ''}")
    return "\n".join(lines)


# ---------------------------------------------------------------- Shorts Factory
def factory_dir(doc):
    return Path(doc["path"]) / "Shorts"


def factory_state(doc):
    f = factory_dir(doc) / "factory.json"
    return store.read_json(f, {"moments": [], "render": "", "titles": {}}) or {"moments": [], "render": "", "titles": {}}


def _best_render(doc):
    """Final before draft; the app's own renders and hand-made ones registered on the project both count."""
    outs = list(recipe(doc["type"]).outputs(doc))
    have = {o["file"].lower() for o in outs}
    outs += [{"kind": r["kind"], "file": r["file"]} for r in doc.get("renders", []) if r["file"].lower() not in have]
    for kind in ("final", "draft"):
        cands = [o["file"] for o in outs if o["kind"] == kind and os.path.exists(o["file"])]
        if cands:
            return max(cands, key=os.path.getmtime), kind
    return None, None


def _intro_len(doc, render):
    """Seconds of motion intro at the start of the render (moments never start inside it)."""
    intro = doc["slots"].get("intro") or ""
    if doc["type"] == "phone":
        intro = str(Path(doc["path"]) / "edit" / "intro" / "renders" / "intro.mp4")
    return round(media.cached_duration(intro), 2) if intro and os.path.exists(intro) else 0.0


def factory_scan(doc, n=8):
    render, kind = _best_render(doc)
    if not render:
        raise ValueError("render a draft or final first")
    fd = factory_dir(doc)
    fd.mkdir(exist_ok=True)
    out = fd / "moments.json"
    # moments are measured on the transcript of the exact file they are cut from (no cut-list mapping that could drift)
    words_p = str(fd / (Path(render).stem + ".words.json"))
    steps = [{"id": "words", "label": "Transcript of the render (once per render)", "force": True,
              "cmd": [py(), "-X", "utf8", str(TOOLS / "transcribe_render.py"), render, words_p]},
             {"id": "moments", "label": f"Finding the best moments in the {kind}", "force": True,
              "cmd": [py(), "-X", "utf8", str(TOOLS / "moments.py"), doc["path"], render, words_p, "-", str(_intro_len(doc, render)), str(out), "--n", str(n)]}]

    def done(job):
        st = factory_state(doc)
        st["moments"] = store.read_json(out, []) or []
        st["render"] = render
        st["kind"] = kind
        store.write_json(fd / "factory.json", st)
    job = jobs.Job(f"{doc['title']}: shorts scan", doc["id"], steps, kind="tools", minutes=(media.cached_duration(render) or 600) / 60, on_done=done)
    jobs.start(job)
    return {"job": job.view()}


def factory_titles(doc):
    st = factory_state(doc)
    if not st["moments"]:
        raise ValueError("scan first")
    lst = "\n".join(f"{m['n']}. ({m['dur']:.0f}s) {m['text'][:500]}" for m in st["moments"])
    out = ask_once(f"These are candidate YouTube Shorts cut from the video '{doc['title']}'. For each, give a punchy Shorts title (under 60 characters, "
                   "no dates, no emojis, ends with #shorts) and a score 1-10 for how well it works as a standalone Short (hook in the first 2 seconds, "
                   "payoff, makes sense without context). Reply ONLY as lines 'N | score | title'.\n\n" + lst, cwd=doc["path"])
    titles = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(.+)", line)
        if m:
            titles[m.group(1)] = {"score": float(m.group(2)), "title": m.group(3).strip()}
    st["titles"] = titles
    store.write_json(factory_dir(doc) / "factory.json", st)
    return st


def factory_render(doc, picks, side="auto"):
    st = factory_state(doc)
    render = st.get("render") or _best_render(doc)[0]
    if not render:
        raise ValueError("no render")
    side = side if side != "auto" else {"gaming": "center", "phone": "left", "review": "center", "haul": "center", "short": "center"}[doc["type"]]
    steps = []
    fd = factory_dir(doc)
    for n in picks:
        m = next((x for x in st["moments"] if str(x["n"]) == str(n)), None)
        if not m:
            continue
        t = (st.get("titles") or {}).get(str(n), {}).get("title", "")
        slug = re.sub(r"[^a-z0-9]+", "-", (t or m["hook"]).lower().replace("#shorts", "")).strip("-")[:40] or f"moment-{n}"
        out = fd / f"m{int(n):02d}-{slug}.mp4"
        steps.append({"id": f"short{n}", "label": f"Short {n}: {(t or m['hook'])[:40]}", "force": True,
                      "cmd": [py(), "-X", "utf8", str(TOOLS / "short.py"), render, str(out), str(m["t0"]), str(m["t1"]), side]})
        txt = [f"TITLE: {t or m['hook'][:80]}", "DESCRIPTION:", f"Full video: {doc.get('yt_title') or doc['title']} (on the channel, link in the pinned comment)", "",
               "#shorts", "", "UPLOAD NOTES: set this Short's Related video to the full upload."]
        out.with_suffix(".txt").write_text("\n".join(txt), encoding="utf-8")
    if not steps:
        raise ValueError("pick at least one moment")
    job = jobs.Job(f"{doc['title']}: {len(steps)} shorts", doc["id"], steps, kind="tools", minutes=sum(1 for _ in steps) * 0.5)
    jobs.start(job)
    return {"job": job.view()}


def factory_gaming_package(doc, sections=None):
    """The polished gaming package (entry card, series badge, keyword pops, end card) from app/gaming/shorts.py."""
    if doc["type"] != "gaming":
        raise ValueError("gaming only")
    render, kind = _best_render(doc)
    if not render:
        raise ValueError("render first")
    cmd = [py(), "-X", "utf8", str(GAMING / "shorts.py"), doc["path"], kind, "--video", render]
    if sections:
        cmd += ["--sections", ",".join(sections)]
    job = jobs.Job(f"{doc['title']}: gaming shorts package", doc["id"], [{"id": "gshorts", "label": "Gaming Shorts package (one per section)", "cmd": cmd, "cwd": str(GAMING), "force": True}],
                   kind="tools", minutes=3)
    jobs.start(job)
    return {"job": job.view()}
