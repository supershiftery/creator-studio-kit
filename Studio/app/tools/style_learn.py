"""New video type wizard: learn a style from 2-5 finished videos (+ one raw recording) -> my_style/types/<slug>.json + .md.

    python style_learn.py <my_style/_work/<job>>      (request.json there: {"name", "base", "examples": [...], "raw": ""})

Measured from the pictures and the sound (no AI): camera layout (media.camera_layout: 1cam / 2cam / screen_cam / vertical /
no_face), shot length + cuts a minute (frame-difference spikes, so jump cuts count too), pauses kept (silencedetect), zoom
cuts (face size jumping across a cut), the music bed (the loudness floor under the voice), head turns on one camera and
whether the edit cuts on them. Then Claude looks at frame sheets of every example (the intro seconds, spread frames, the
frames either side of a few cuts) with those numbers and fills in what only eyes can tell: captions on/off + style,
text-on-screen, transitions, intro style, section structure, music mood, and writes the type's short playbook.
Progress: status.json next to request.json (the wizard polls it). Without Claude the type is still made from the numbers.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import media  # noqa: E402
import mystyle  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else None
PRESETS = []
try:
    PRESETS = [p["key"] for p in json.loads((APP.parent / "ui" / "captions" / "presets.json").read_text(encoding="utf-8"))]
except (OSError, ValueError, KeyError):
    pass
MOODS = ("chill", "upbeat", "hype", "dark", "cinematic", "lo-fi")


def status(step, pct, **kw):
    print(f"[{pct:3.0f}%] {step}", flush=True)
    if WORK:
        done = kw.get("state") in ("done", "failed")
        try:
            mystyle._write(WORK / "status.json", {"state": kw.pop("state", "running"), "step": step, "pct": round(pct), **kw})
        except OSError:   # a progress line is never worth losing the training for; the last one has to arrive
            if done:
                raise


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW, **kw)


# ---------------------------------------------------------------- measurements
def cuts_of(path, fps=10):
    """Shot changes: spikes in the mean frame difference of a small grey copy (catches jump cuts, not only scene changes)."""
    import numpy as np
    W, H = 160, 90
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]).stdout
    n = len(raw) // (W * H)
    if n < 3:
        return []
    fr = np.frombuffer(raw[: n * W * H], np.uint8).reshape(n, H, W).astype(np.int16)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    med = float(np.median(d)) or 0.5
    thr = max(9.0, med * 4.5)
    cuts, last = [], -1.0
    for i in range(1, len(d) - 1):
        if d[i] > thr and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
            t = (i + 1) / fps
            if t - last >= 0.4:   # a fade / whip counts once
                cuts.append(round(t, 2))
                last = t
    return cuts


def pauses_of(path, info):
    """Pauses kept between words (0.25 s+) and the loudness floor (the music bed under the voice). A finished video has
    music under its pauses, so a pause = the voice band dropping toward the floor, not digital silence."""
    import numpy as np
    if not info.get("audio"):
        return {"pauses": [], "floor_db": None, "voice_db": None}
    pcm = run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]).stdout
    a = np.frombuffer(pcm[: len(pcm) // 2 * 2], np.int16).astype(np.float32) / 32768
    win = 400   # 50 ms
    k = len(a) // win
    if k < 20:
        return {"pauses": [], "floor_db": None, "voice_db": None}
    rms = np.sqrt((a[: k * win].reshape(k, win) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    voice = run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-af",
                 "highpass=f=300,lowpass=f=3400", "-f", "s16le", "-"]).stdout
    v = np.frombuffer(voice[: len(voice) // 2 * 2], np.int16).astype(np.float32) / 32768
    kv = min(k, len(v) // win)
    vdb = 20 * np.log10(np.sqrt((v[: kv * win].reshape(kv, win) ** 2).mean(axis=1) + 1e-12))
    lo, hi = np.percentile(vdb, 10), np.percentile(vdb, 90)
    quiet = vdb < lo + max(4.0, (hi - lo) * 0.35)
    pauses, run_n = [], 0
    for q in list(quiet) + [False]:
        if q:
            run_n += 1
        elif run_n:
            if run_n * 0.05 >= 0.25:
                pauses.append(round(run_n * 0.05, 2))
            run_n = 0
    return {"pauses": pauses, "floor_db": round(float(np.percentile(db, 12)), 1), "voice_db": round(float(np.percentile(db, 90)), 1)}


def zooms_at(path, cuts, limit=36):
    """Cuts where the same face gets 12%+ bigger or smaller = zoom / punch-in cuts."""
    z = n = 0
    step = max(1, len(cuts) // limit)
    for t in cuts[::step][:limit]:
        a, b = media.faces_at(path, max(0.0, t - 0.25), w=480), media.faces_at(path, t + 0.25, w=480)
        if not a or not b:
            continue
        fa, fb = max(a, key=lambda x: x["h"]), max(b, key=lambda x: x["h"])
        if abs(fa["cx"] - fb["cx"]) > 0.25:   # a different person / camera, not a zoom
            continue
        n += 1
        r = fb["h"] / max(fa["h"], 1e-3)
        z += r > 1.12 or r < 0.89
    return z, n


def measure(path, label, pct0, pct1, raw=False):
    info = media.probe(path)
    if not info or not info["duration"]:
        raise ValueError(f"can't read {Path(path).name}")
    dur = info["duration"]
    status(f"{label}: camera layout", pct0)
    cam = media.camera_layout(path, n=10, info=info)
    m = {"duration": round(dur, 1), "width": info["width"], "height": info["height"], "camera": cam["camera"],
         "frame": cam["frame"], "faces": cam["faces"], "face_h": cam["face_h"]}
    status(f"{label}: pauses + music bed", pct0 + (pct1 - pct0) * 0.25)
    ap = pauses_of(path, info)
    ps = sorted(ap["pauses"])
    m.update(pauses_per_min=round(len(ps) / (dur / 60), 2), median_pause_s=round(ps[len(ps) // 2], 2) if ps else 0.0,
             long_pauses_per_min=round(sum(p > 0.7 for p in ps) / (dur / 60), 2), floor_db=ap["floor_db"], voice_db=ap["voice_db"])
    if ap["floor_db"] is not None:
        gap = ap["voice_db"] - ap["floor_db"]
        m["music_bed"] = ap["floor_db"] > -52 and gap < 32
        m["music_energy"] = None if not m["music_bed"] else "high" if gap < 16 else "medium" if gap < 24 else "low"
    if raw:   # a raw recording: what they film (layout, turn habit, how much they pause), not how they cut
        if cam["camera"] == "1cam":
            status(f"{label}: head turns", pct0 + (pct1 - pct0) * 0.6)
            ht = media.head_turns(path, fps=2, t1=min(dur, 240))
            m.update(turns_per_min=ht["per_min"], turns=len(ht["turns"]))
        return m, []
    status(f"{label}: cuts", pct0 + (pct1 - pct0) * 0.45)
    cuts = cuts_of(path)
    m.update(cuts=len(cuts), cuts_per_min=round(len(cuts) / (dur / 60), 2), avg_shot_s=round(dur / (len(cuts) + 1), 2))
    status(f"{label}: zooms", pct0 + (pct1 - pct0) * 0.65)
    if cam["camera"] in ("1cam", "2cam", "screen_cam", "vertical"):
        z, n = zooms_at(path, cuts)
        m.update(zoom_cuts=z, zoom_checked=n, zooms_per_min=round(z / max(1, n) * len(cuts) / (dur / 60), 2) if n else 0.0)
    if cam["camera"] in ("1cam", "vertical"):
        status(f"{label}: head turns", pct0 + (pct1 - pct0) * 0.8)
        ht = media.head_turns(path, fps=2, t1=min(dur, 240))
        near = sum(1 for tr in ht["turns"] if any(abs(c - tr["t"]) < 0.8 for c in cuts))
        m.update(turns_per_min=ht["per_min"], turns=len(ht["turns"]), turns_cut=near)
    return m, cuts


def sheet(path, cuts, dur, out_png):
    """One labelled 4-column frame sheet: intro seconds, spread frames, both sides of a few cuts."""
    from PIL import Image, ImageDraw, ImageFont
    import io
    items = [(t, f"intro {t:.1f}s") for t in (0.3, 1.5, 3.0, 5.0, 8.0) if t < dur]
    items += [(dur * f, f"{dur * f / 60:.1f} min") for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.95)]
    for c in [c for c in cuts if c > 10][:: max(1, len(cuts) // 4)][:4]:
        items += [(c - 0.3, f"before cut {c:.1f}s"), (c + 0.3, f"after cut {c:.1f}s")]
    w, cols = 400, 4
    h = w * 9 // 16
    rows = (len(items) + cols - 1) // cols
    im = Image.new("RGB", (cols * w, rows * (h + 24)), (18, 18, 18))
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for n, (t, lab) in enumerate(items):
        x, y = (n % cols) * w, (n // cols) * (h + 24)
        raw = run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                   f"scale={w}:{h}:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "-"]).stdout
        try:
            fr = Image.open(io.BytesIO(raw)).convert("RGB")
            im.paste(fr, (x + (w - fr.width) // 2, y + (h - fr.height) // 2))
        except Exception:  # noqa: a frame that can't be read stays dark
            pass
        dr.text((x + 6, y + h + 3), lab, fill=(230, 230, 230), font=font)
    im.save(out_png)
    return out_png


# ---------------------------------------------------------------- Claude's look
PROMPT = """You are a senior video editor studying a creator's own editing style so an automatic editor can copy it.
They are making a custom video type called "{name}" built on the {base} pipeline. Below are numbers measured from {n}
finished example videos, then frame sheets of each (read every PNG with the Read tool: intro seconds, frames across the
video, and the frames either side of a few cuts).

MEASURED (per example):
{measured}
{raw}{extra}
Look at the sheets and decide what only eyes can tell. Turn every REFERENCE (a feature they want from another video), every
WISH, every PIECE and every repeated habit in the PAST NOTES into a rule for the whole type: a category rule ("open every
video with the scripture card, white text on black, 4 s"), never about one video's times or words. Project settings a rule
may set (only when it maps onto one): {keys}
Answer with JSON only:
{{"captions": {{"on": true|false, "style": one of {presets} or null}},
  "text_on_screen": "none" | "minimal" | "frequent",
  "text_style": "<a few words: font weight, colour, where on screen>",
  "transitions": "cut" | "dissolve" | "wipe" | "zoom" | "mixed",
  "intro": "cold_open" | "hook_title" | "title_card" | "none",
  "sections": "<one line: how the video is structured, e.g. hook -> 5 numbered sections -> outro>",
  "music_mood": one of {moods} or null,
  "zooms": "<one line: when they zoom / punch in, or none>",
  "layout_note": "<one line: what is on screen and where>",
  "rules": [{{"text": "<one sentence, imperative>", "category": one of {cats}, "settings": {{}}}}],
  "playbook": "<markdown, 8-14 short bullet lines: how to edit a video of this type in this style - pacing, pauses, camera, zooms, captions, text, music, transitions, intro, sections, the pieces. Concrete numbers from MEASURED. No names, no brands.>"}}"""


def ask_claude(name, base, measured, raw_m, sheets, extra=""):
    sys.path.insert(0, str(APP))
    import chat
    meas = "\n".join(f"- example {i + 1}: " + json.dumps({k: v for k, v in m.items() if k not in ("width", "height")}) for i, m in enumerate(measured)) \
        or "(no finished videos: go by the project files, references and wishes)"
    prompt = PROMPT.format(name=name, base=mystyle.BASE_LABELS.get(base, base), n=len(measured), measured=meas,
                           raw=("RAW RECORDING (how they film, before editing): " + json.dumps(raw_m) + "\n") if raw_m else "",
                           extra=extra, keys="; ".join(f"{k} = {v}" for k, v in mystyle.SETTING_KEYS.items()),
                           cats=json.dumps(list(mystyle.CATEGORIES)),
                           presets=json.dumps(PRESETS or ["bold", "karaoke", "minimal"]), moods=json.dumps(list(MOODS)))
    if base == "auto" or name == "their own style":
        prompt += ('\n\nThey did not say what kind of videos these are. Add to the JSON: "base": one of ' + json.dumps(list(mystyle.BASES)) +
                   " (" + "; ".join(f"{k} = {v}" for k, v in mystyle.BASE_LABELS.items()) + '; gaming only for gameplay with a voice over it; '
                   'talking when unsure), and "name": a short plain name for this style, 2-4 words, e.g. "Calm tech reviews".')
    prompt += "\n\nFrame sheets:\n" + "\n".join(f"- {s}" for s in sheets)
    cmd = [chat.claude_exe(), "-p", prompt, "--model", chat.MODEL, "--output-format", "json", "--max-turns", str(4 + len(sheets) * 2),
           "--no-session-persistence", "--tools", "Read", "--allowedTools", "Read", "--setting-sources", "", "--strict-mcp-config",
           "--disable-slash-commands"]
    r = subprocess.run(cmd, cwd=str(WORK), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                       creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
    try:
        out = json.loads(r.stdout).get("result") or ""
    except ValueError:
        out = r.stdout or r.stderr
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        print("claude gave no JSON:", out[:400])
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        print("claude JSON did not parse:", out[:400])
        return None


# ---------------------------------------------------------------- the type
def med(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    return round(xs[len(xs) // 2], 2) if xs else None


def build_style(measured, raw_m, look, projects=()):
    look = look or {}
    lay = Counter(m["camera"] for m in measured).most_common(1)[0][0] if measured else \
        (raw_m or {}).get("camera") if (raw_m or {}).get("camera") in mystyle.LAYOUTS else None
    shot, cpm = med([m.get("avg_shot_s") for m in measured]), med([m.get("cuts_per_min") for m in measured])
    if shot is None and projects:   # no finished video: the editor's project files give the pace
        shot, cpm = med([p.get("avg_clip_s") for p in projects]), med([p.get("cuts_per_min") for p in projects])
    mp, lpm = med([m.get("median_pause_s") for m in measured]), med([m.get("long_pauses_per_min") for m in measured])
    tight = "tight" if (mp is not None and mp < 0.4 and (lpm or 0) < 1.5) or (cpm or 0) >= 14 else \
        "loose" if (lpm or 0) >= 4 and (cpm or 0) < 5 else "natural"
    bed = [m.get("music_bed") for m in measured if m.get("music_bed") is not None]
    music_on = sum(bed) * 2 >= len(bed) if bed else None
    energy = Counter(m.get("music_energy") for m in measured if m.get("music_energy")).most_common(1)
    zpm = med([m.get("zooms_per_min") for m in measured])
    turns = [m for m in measured if m.get("turns")]
    tcut = sum(m.get("turns_cut", 0) for m in turns) / max(1, sum(m["turns"] for m in turns)) if turns else 0
    st = {
        "layout": lay,
        "pace": {"avg_shot_s": shot, "cuts_per_min": cpm, "pauses_per_min": med([m.get("pauses_per_min") for m in measured]),
                 "median_pause_s": mp, "long_pauses_per_min": lpm, "tightness": tight},
        "zooms": {"on": bool(zpm and zpm >= 0.5), "per_min": zpm, "note": look.get("zooms")},
        "music": {"on": music_on, "energy": energy[0][0] if energy else None,
                  "mood": look.get("music_mood") if look.get("music_mood") in MOODS else None},
        "head_turns": {"per_min": med([m.get("turns_per_min") for m in turns]) if turns else None,
                       "follow": "cut" if turns and tcut >= 0.4 else "off" if turns else None, "cut_share": round(tcut, 2) if turns else None},
        "measured": measured,
    }
    if projects:
        st["project_files"] = [{k: p.get(k) for k in ("tool", "clips", "avg_clip_s", "cuts_per_min", "transitions", "effects")} for p in projects]
        if not look.get("transitions"):
            tr = Counter(n for p in projects for n, c in (p.get("transitions") or {}).items() for _ in range(c))
            if tr:
                st["transitions"] = "dissolve" if "dissolve" in tr.most_common(1)[0][0].lower() else "mixed"
    if raw_m:
        st["raw"] = raw_m
        if raw_m.get("turns_per_min") and st["head_turns"]["follow"] is None:
            st["head_turns"]["per_min"] = raw_m["turns_per_min"]
    cap = look.get("captions") if isinstance(look.get("captions"), dict) else None
    if cap is not None:
        st["captions"] = {"on": bool(cap.get("on")), "style": cap.get("style") if cap.get("style") in PRESETS else None}
    for k in ("text_on_screen", "text_style", "transitions", "intro", "sections", "layout_note"):
        if look.get(k):
            st[k] = look[k]
    return st


def fallback_playbook(st):
    p = st["pace"]
    if not p.get("avg_shot_s"):
        return "- Follow the rules below; the type learns the rest from your revision notes."
    lines = [f"- Camera: {st['layout'] or 'any'}.",
             f"- Pace: a cut every {p['avg_shot_s']} s on average ({p['cuts_per_min']} a minute); pauses {p['tightness']} "
             f"(median kept pause {p['median_pause_s']} s).",
             f"- Zooms: {'about ' + str(st['zooms']['per_min']) + ' zoom cuts a minute' if st['zooms']['on'] else 'rare'}.",
             f"- Music: {'a ' + (st['music']['energy'] or '') + ' bed under the voice' if st['music']['on'] else 'none / very quiet'}."]
    if st["head_turns"].get("follow") == "cut":
        lines.append("- When the speaker turns their head, cut to the other angle.")
    return "\n".join(lines)


def fetch_links(links, room):
    """YouTube / TikTok / Instagram links (a video, a playlist, a channel) -> up to `room` local copies of the first 8 minutes in
    720p, only to measure and look at; deleted again when training ends. Returns (paths, a name for the style, problems)."""
    import creator_tools
    dl, paths, name, errs = WORK / "dl", [], "", []
    dl.mkdir(exist_ok=True)
    for url in links:
        if len(paths) >= room:
            break
        if re.search(r"youtube\.com/(@[^/]+|c/[^/]+|channel/[^/]+|user/[^/]+)/?(\?|$)", url):
            url = url.split("?")[0].rstrip("/") + "/videos"   # a channel's front page holds shelves, not its videos
        status(f"getting your examples ({len(paths)} of {room})", 1)
        r = subprocess.run(creator_tools._ytdlp() + [
            "--encoding", "utf-8", "--no-warnings", "--no-progress", "--ignore-errors", "--windows-filenames", "--yes-playlist",
            "--playlist-items", f"1:{room - len(paths)}", "-S", "res:720,vcodec:h264,acodec:aac", "--merge-output-format", "mp4",
            "--download-sections", "*0:00-8:00", "-P", str(dl), "-o", "%(autonumber)s-%(id)s.%(ext)s", "--print", "after_move:FILE %(filepath)s",
            "--print", "before_dl:NAME %(playlist_title)s|%(uploader)s", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL)
        got = 0
        for line in r.stdout.splitlines():
            if line.startswith("FILE ") and os.path.isfile(line[5:]):
                paths.append(line[5:])
                got += 1
            elif line.startswith("NAME ") and not name:
                pl, up = (line[5:].split("|") + [""])[:2]
                name = next((x for x in (up, pl) if x and x != "NA"), "")
        if not got:
            errs.append(f"{url}: " + ((r.stderr or "").strip().splitlines() or ["couldn't download it"])[-1][:160])
    return paths, name, errs


def pick_base(look, measured):
    """what the videos are closest to: Claude saw them; without Claude only vertical is sure, the rest is the plain trim (gaming
    and review add graphics and camera moves that a wrong guess would put on the wrong video)"""
    b = (look or {}).get("base")
    if b in mystyle.BASES:
        return b
    layouts = Counter(m.get("layout") for m in measured)
    return "short" if layouts and layouts.most_common(1)[0][0] == "vertical" else "talking"


def main():
    import project_import
    req = json.loads((WORK / "request.json").read_text(encoding="utf-8"))
    items = req.get("items") or [{"path": p, "kind": "finished"} for p in req.get("examples") or []] + \
        ([{"path": req["raw"], "kind": "raw"}] if req.get("raw") else [])
    auto_base, link_name, link_errs = req["base"] == "auto", "", []
    if req.get("links"):
        room = max(1, 5 - len([i for i in items if i["kind"] == "finished"]))
        got, link_name, link_errs = fetch_links(req["links"], room)
        items = items + [{"path": x, "kind": "finished"} for x in got]
        if not items and not (req.get("wishes") or "").strip():
            raise RuntimeError("couldn't get those links. " + "; ".join(link_errs)[:300])
    fin = [i for i in items if i["kind"] == "finished"]
    raws = [i for i in items if i["kind"] == "raw"][:1]
    refs = [i for i in items if i["kind"] == "reference"][:4]
    projs = [i for i in items if i["kind"] == "project"]
    pieces = [i for i in items if i["kind"] == "asset"]
    measured, sheets, extra = [], [], []
    heavy = len(fin) + len(raws) + len(refs) or 1
    span, at = 70 / heavy, 3.0
    for n, it in enumerate(fin, 1):
        m, cuts = measure(it["path"], f"finished video {n}", at, at + span)
        at += span
        measured.append(m)
        sheets.append(str(sheet(it["path"], cuts, m["duration"], WORK / f"sheet{n}.png")))
    raw_m = None
    for it in raws:
        raw_m, _ = measure(it["path"], "raw recording", at, at + span, raw=True)
        at += span
    for n, it in enumerate(refs, 1):   # a feature they want from another video: frames + what they said they want
        status(f"reference {n}: looking at it", at)
        info = media.probe(it["path"]) or {}
        s = str(sheet(it["path"], cuts_of(it["path"]) if (info.get("duration") or 0) < 900 else [], info.get("duration") or 10,
                      WORK / f"reference{n}.png"))
        sheets.append(s)
        extra.append(f"REFERENCE {n} ({s}): they want this from it: {it.get('note') or '(not said: work out the stand-out feature)'}")
        at += span
    projects = []
    for it in projs:
        status(f"reading {Path(it['path']).name}", min(at, 74))
        try:
            pj = project_import.read(it["path"])
            projects.append(pj)
            extra.append(f"EDITOR PROJECT FILE ({pj['tool']}): " + json.dumps(pj, ensure_ascii=False)[:2500])
        except Exception as e:  # noqa: one unreadable file never stops the rest
            extra.append(f"(a project file could not be read: {e})")
    if pieces:
        extra.append("PIECES they gave (files the type keeps): " + "; ".join(
            f"{Path(i['path']).name} -> {mystyle.ROLES.get(i.get('role') or 'use')}" + (f" ({i['note']})" if i.get("note") else "") for i in pieces))
    if (req.get("opening_text") or "").strip():
        extra.append("OPENING CARD: every video opens with this text on screen: " + req["opening_text"].strip()[:600])
    if (req.get("wishes") or "").strip():
        extra.append("WISHES (their own words, always do these): " + req["wishes"].strip()[:2000])
    if req.get("past_notes"):
        extra.append("PAST NOTES they wrote on videos made in the Studio:\n" + "\n".join(f"- {x}" for x in req["past_notes"][:60]))
    look = None
    if measured or extra:
        status("Claude is looking at everything", 76)
        try:
            look = ask_claude(req["name"] or "their own style", req["base"], measured, raw_m, sheets, "\n".join(extra) + ("\n" if extra else ""))
        except Exception as e:  # noqa: the numbers still make a type
            print("claude look failed:", type(e).__name__, e)
    status("writing your style", 95)
    st = build_style(measured, raw_m, look, projects)
    if auto_base and not req.get("slug"):
        req["base"] = pick_base(look, measured)
    if not req.get("name"):
        first = next((Path(i["path"]).stem for i in items if not i.get("from_project") and "dl" not in Path(i["path"]).parts[-2:-1]), "")
        req["name"] = ((look or {}).get("name") or (f"{link_name} style" if link_name else "") or (f"{first[:40]} style" if first else "My style")).strip()[:60]
    pb = (look or {}).get("playbook") or fallback_playbook(st)
    if req.get("slug"):   # teach an existing type more: new numbers replace the old, rules and pieces are added
        t = mystyle.load_type(req["slug"])
        if measured or projects:
            old = t.get("style") or {}
            t["style"] = {**old, **{k: v for k, v in st.items() if v not in (None, {}, [])}}
            t["settings"] = mystyle.style_settings(t)
        t["examples"] = int(t.get("examples") or 0) + len(measured)
        mystyle.save_type(t)
        if (look or {}).get("playbook"):
            (mystyle.TYPES / f"{t['slug']}.md").write_text(f"# {t['name']}\n\n{pb.strip()}\n", encoding="utf-8")
    else:
        t = mystyle.new_type(req["name"], req["base"], st, f"# {req['name']}\n\n{pb.strip()}\n", examples=len(measured), raw=bool(raws))
    for it in pieces:
        mystyle.add_asset(t["slug"], it["path"], it.get("role") or "use", it.get("dur"), it.get("note") or "")
    if (req.get("opening_text") or "").strip():
        png = WORK / "opening card.png"
        mystyle.opening_card(req["opening_text"], png, vertical=req["base"] == "short" or st.get("layout") == "vertical")
        mystyle.add_asset(t["slug"], str(png), "start", 4, "opening text card")
    rules = (look or {}).get("rules") if isinstance((look or {}).get("rules"), list) else None
    if rules is None:   # no Claude: wishes line by line, and the past notes that match a known kind of note
        rules = []
        for line in [x.strip(" -•") for x in (req.get("wishes") or "").splitlines() if x.strip()]:
            hit = next(((c, s) for rx, c, _, s in mystyle.FALLBACK if re.search(rx, line.lower())), ("other", {}))
            rules.append({"text": line[:300], "category": hit[0], "settings": hit[1]})
        for note in req.get("past_notes") or []:
            hit = next(((c, txt, s) for rx, c, txt, s in mystyle.FALLBACK if re.search(rx, note.lower())), None)
            if hit:
                rules.append({"text": hit[1], "category": hit[0], "settings": hit[2]})
    for r in rules:
        if isinstance(r, dict) and r.get("text"):
            mystyle.add_rule(t["slug"], {"text": str(r["text"])[:300],
                                         "category": r.get("category") if r.get("category") in mystyle.CATEGORIES else "other",
                                         "settings": {k: v for k, v in (r.get("settings") or {}).items() if k in mystyle.SETTING_KEYS},
                                         "how": "trained"})
    shutil.rmtree(WORK / "dl", ignore_errors=True)
    status("done", 100, state="done", slug=t["slug"], name=t["name"], claude=bool(look), link_errors=link_errs)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        shutil.rmtree(WORK / "dl", ignore_errors=True)
        status(f"failed: {type(e).__name__}: {e}", 100, state="failed")
        sys.exit(1)
