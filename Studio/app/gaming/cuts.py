"""Step 4: the cutter. Notes + "outside sections" -> extra_cuts.json, then take_cuts.py (the approved trimming rules),
then UI-panel detection for inventory zooms.   python cuts.py <project>"""
import json
import os
import subprocess
import sys

import numpy as np

from glib import Project, TOOLS, fmt, run, say

P = Project(sys.argv[1])
dur = P.source_info["duration"]
secs = P.sections
extra = []
TRIM_ONLY = bool(P.settings.get("trim_only"))   # New Project "Trim only": any video type, no sections, no panels
HAUL = P.doc.get("type") in ("haul", "short")   # (short = vertical Short, same full-frame path) haul (phone product haul, 2026-10-23): the take review's "haul" rules, no game panels
# everything outside the sections is cut (no sections = nothing is "outside": trim-only projects and early builds)
t = 0.0
for name, s, e in sorted(secs, key=lambda x: x[1]):
    if s - t > 0.05:
        extra.append({"s": round(t, 3), "e": round(s, 3), "why": "outside sections"})
    t = max(t, e)
if secs and dur - t > 0.05:
    extra.append({"s": round(t, 3), "e": round(dur, 3), "why": "outside sections"})
# user notes with raw times (resolved by the app from the draft the user watched). EVERY build applies them: the cut
# list is rebuilt from the transcript each time, and "done" only means a build has used the note. Skipping done notes
# dropped them all from the next build (Top 10 Servers 2026-10-22: "Hello YouTube" clipped again, the #9 splice lost).
# A note the user switched off has "off": true.
for n in P.doc.get("notes", []):
    if n.get("off") or "raw0" not in n:
        continue
    if n["kind"] == "cut":
        extra.append({"s": n["raw0"], "e": n["raw1"], "why": "user note: " + n["text"]})
    elif n["kind"] == "protect":
        extra.append({"s": n["raw0"], "e": n["raw0"], "why": "user note: " + n["text"], "protect": [n["raw0"], n["raw1"]]})
# Director reels filmed inside the recording (broll.py): pink, black fades and the shots never play as gameplay; the shots
# come back cut clean as placed B-roll (body.py). From the "starting in 3..." countdown (3 s before the pink) to just after
# the closing pink. settings.broll_keep_reels = true leaves them in.
if not P.settings.get("broll_keep_reels"):
    for a, b in (P.read("broll.json", {}) or {}).get("reels", []):
        extra.append({"s": round(max(0.0, a - 3.2), 3), "e": round(min(dur, b + 0.7), 3), "why": "Director B-roll reel (used as B-roll)"})
for pr in P.settings.get("protect", []):   # [[s, e], ...] raw ranges the cutter must never touch
    extra.append({"s": pr[0], "e": pr[0], "why": "protected (settings)", "protect": [pr[0], pr[1]]})
P.write("extra_cuts.json", extra)
say(f"{len(extra)} extra cuts/protects ({sum(1 for x in extra if x['why'] == 'outside sections')} outside sections)")
(P.work / "cuts").mkdir(exist_ok=True)
fps = P.source_info.get("fps") or 60


if P.settings.get("pauses"):   # natural | tight (jump-cut pacing, take_cuts.py); set here so it works without an app restart
    os.environ["STUDIO_PAUSES"] = P.settings["pauses"]


def take_cuts(extra_file):
    r = subprocess.run([sys.executable, "-X", "utf8", str(TOOLS / "take_cuts.py"), str(P.wf("words.json")), f"{fps:g}", str(P.work / "cuts"),
                        "--duration", f"{dur:.3f}", "--extra", str(extra_file), "--audio", str(P.wf("mic16k.wav"))],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-6000:])
    if r.returncode:
        print(r.stderr[-3000:])
        sys.exit("take_cuts failed")


take_cuts(P.wf("extra_cuts.json"))
# take review (same pass as the phone pipeline, user 2026-10-21): Claude reads the KEPT transcript for lines abandoned and
# redone in different words, fragments left at a join, talk not meant for the viewer; then the cut again with its marks.
# Cached by transcript (cuts\review.json), so a rebuild with nothing new costs nothing. settings.take_review = false turns it off.
if P.settings.get("take_review", True) and P.keep:
    if P.settings.get("take_review") == "fresh":   # the review is frozen after draft 1 unless asked (take_review.py)
        os.environ["TAKE_REVIEW"] = "fresh"
    try:
        sys.path.insert(0, str(TOOLS / "phone_edit"))
        import take_review
        marks = take_review.review(str(P.path), 0.0, kind=P.doc.get("type") if (TRIM_ONLY or HAUL) else "gaming", work=str(P.work / "cuts"), words=str(P.wf("words.json")),
                                   keep=P.keep, audio=str(P.wf("mic16k.wav")))
        prot = [x["protect"] for x in extra if "protect" in x]
        # the user's protects win: a mark that is mostly protected words goes; one that only contains / grazes a protect
        # stays and take_cuts trims it around the protect (Chime 2026-10-23: dropping "broken fragments 1210-1248" for a
        # 2 s protect at its end brought "Where was this" back)
        marks = [m for m in marks if sum(max(0.0, min(m["e"], pe) - max(m["s"], ps)) for ps, pe in prot) < 0.5 * (m["e"] - m["s"])]
        if marks:
            P.write("extra_all.json", extra + marks)
            take_cuts(P.wf("extra_all.json"))
        say(f"take review: {len(marks)} cuts")
    except SystemExit:
        raise
    except Exception as e:  # no Claude sign-in / no network: the rules-only cut stands
        say(f"take review skipped: {type(e).__name__}: {e}")
keep = P.keep
say(f"kept {sum(e - s for s, e in keep) / 60:.1f} min in {len(keep)} pieces")

if TRIM_ONLY or HAUL:   # no layouts in a trim-only / haul render, so no inventory zooms to find
    P.write("ui.json", [])
    sys.exit(0)
# ---- UI panels (inventory / chest / menu) -> ui.json for the quick zooms (gaming rule, 2026-10-20)
FW, FH, RATE = 192, 108, 4
crop = P.game_crop()


def panel(fr):
    r_, g, b = (fr[..., c].astype(int) for c in range(3))
    grey = (np.abs(r_ - g) < 10) & (np.abs(g - b) < 10)
    light = grey & (r_ > 150) & (r_ < 225)
    rows, cols = light.mean(1), light.mean(0)
    ys, xs = np.where(rows > 0.18)[0], np.where(cols > 0.18)[0]
    if len(ys) < 12 or len(xs) < 20:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    box = light[y0:y1 + 1, x0:x1 + 1]
    cx = (x0 + x1) / 2
    if (box.mean() < 0.35 or not (0.18 < w / FW < 0.7) or not (0.2 < h / FH < 0.9) or abs(cx - FW / 2) > FW * 0.15 or y1 > FH * 0.9):
        return None
    return (int(x0), int(y0), int(w), int(h))


ui, dead, cover = [], [], []
WORDS = P.words
# per-piece frame scan cache (user 2026-10-22: faster revisions). A piece of the raw recording always shows the same frames,
# so its panel boxes / frozen / flat flags are kept by its raw range and reused when a revision keeps that piece again.
_scan_file = P.work / "cuts" / "frame_scan.json"
_sig = f"{P.src}|{os.path.getsize(P.src)}|{int(os.path.getmtime(P.src))}|{crop}|{FW}x{FH}@{RATE}|v1"
SCAN = (P.read("cuts/frame_scan.json", {}) or {})
SCAN = SCAN.get("pieces", {}) if SCAN.get("sig") == _sig else {}
_scan_new = 0
if P.settings.get("ui_zooms", True) or P.settings.get("cut_loading", True):
    for s, e in keep:
        if P.section_of(s) in ("intro", "outro") or e - s < 1.0:
            continue
        ck = f"{s:.3f}-{e:.3f}"
        if ck not in SCAN:
            buf = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", P.src, "-vf",
                                  f"crop={crop},scale={FW}:{FH},fps={RATE}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            n = len(buf) // (FW * FH * 3)
            frames = np.frombuffer(buf[:n * FW * FH * 3], np.uint8).reshape(-1, FH, FW, 3) if n else np.zeros((0, FH, FW, 3), np.uint8)
            g_ = frames.mean(3) if n else []
            SCAN[ck] = {"hits": [list(h) if h else None for h in (panel(f) for f in frames)],
                        "still": [False] + [float(np.abs(g_[q] - g_[q - 1]).mean()) < 0.6 for q in range(1, n)] if n else [],
                        "flat": [float(f[8:-8, 8:-8].std()) < 7.0 for f in g_] if n else []}
            _scan_new += 1
        if not SCAN[ck]["hits"] and not SCAN[ck]["still"]:
            continue
        hits = SCAN[ck]["hits"] if P.settings.get("ui_zooms", True) else []
        k = 0
        while k < len(hits):
            if hits[k] is None:
                k += 1
                continue
            j = k
            while j + 1 < len(hits) and (hits[j + 1] is not None or (j + 2 < len(hits) and hits[j + 2] is not None)):
                j += 1
            if (j - k + 1) / RATE >= 1.2:
                bs = np.array([h for h in hits[k:j + 1] if h is not None])
                x0, y0 = bs[:, 0].min(), bs[:, 1].min()
                x1, y1 = (bs[:, 0] + bs[:, 2]).max(), (bs[:, 1] + bs[:, 3]).max()
                sc = 1920 / FW
                ui.append({"s": round(s + k / RATE, 2), "e": round(s + (j + 1) / RATE, 2), "section": P.section_of(s),
                           "box": [int(x0 * sc), int(y0 * sc), int((x1 - x0) * sc), int((y1 - y0) * sc)]})
            k = j + 1
        # dead space (user 2026-10-22, Top 10 Servers 6:11: a frozen server-selector frame, then a loading screen, with
        # "be on the server" said over it): frames that don't change (mean diff < 0.6) or are one flat colour (loading).
        # Runs >= 0.75 s with no word over them are cut. Talked-over runs at a piece edge (the join) get covered by
        # the gameplay that follows (an L-cut: the voice keeps going, the picture is already on the server); frozen
        # runs mid-piece stay (that is a menu being explained), and so does anything over a detected UI panel.
        if P.settings.get("cut_loading", True):
            still, flat = SCAN[ck]["still"], SCAN[ck]["flat"]
            bad = [a_ or b_ for a_, b_ in zip(still, flat)]
            k = 0
            while k < len(bad):
                if not bad[k]:
                    k += 1
                    continue
                j = k
                while j + 1 < len(bad) and bad[j + 1]:
                    j += 1
                a_, b_ = s + max(k - 1, 0) / RATE, s + (j + 1) / RATE
                nflat = sum(flat[k:j + 1])   # a real loading screen, not a still menu or standing while talking
                k = j + 1
                if b_ - a_ < 0.75:
                    continue
                talk = any(w["s"] < b_ and w["e"] > a_ for w in WORDS)
                if any(u_["s"] < b_ and u_["e"] > a_ for u_ in ui):
                    continue
                if not talk:
                    dead.append((round(max(s, a_), 3), round(min(e, b_ + 0.05), 3)))
                elif (a_ - s < 0.3 or e - b_ < 0.3) and nflat >= 2:   # still frames while talking are normal (Top 10 Servers: 17 false covers)
                    cover.append({"s": round(a_, 3), "e": round(min(e, b_ + 0.1), 3), "edge": "start" if a_ - s < 0.3 else "end"})
P.write("ui.json", ui)
P.write("cuts/frame_scan.json", {"sig": _sig, "pieces": SCAN})
say(f"{len(ui)} UI panels for zooms (frame scan: {_scan_new} new pieces decoded, {len(SCAN) - _scan_new} from cache)")


def live_after(t, need, limit=120.0):
    """first raw time after t where `need` seconds of real gameplay (changing, not one flat colour) were recorded but
    not kept: the arrival on the server that the silence cut removed, used to cover a talked-over loading screen"""
    kept = P.keep
    for c0 in np.arange(t, min(t + limit, dur - need), 10.0):
        buf = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{c0:.2f}", "-t", "10.5", "-i", P.src, "-vf",
                              f"crop={crop},scale={FW}:{FH},fps=2", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        n_ = len(buf) // (FW * FH)
        g = np.frombuffer(buf[:n_ * FW * FH], np.uint8).reshape(-1, FH, FW).astype(float)
        live = [q > 0 and np.abs(g[q] - g[q - 1]).mean() >= 0.6 and g[q][8:-8, 8:-8].std() >= 7.0 for q in range(len(g))]
        run_ = 0
        for q, ok in enumerate(live):
            run_ = run_ + 1 if ok else 0
            t0 = c0 + (q + 1 - run_) / 2
            if run_ / 2 >= need + 0.5 and not any(a < t0 + need and b > t0 for a, b in kept):
                return round(t0 + 0.25, 2)
    return None


for c in cover:
    c["from"] = live_after(c["e"], c["e"] - c["s"])
cover = [c for c in cover if c["from"] is not None]
P.write("cover.json", cover)
if cover:
    say(f"{len(cover)} talked-over loading screens covered with the arrival gameplay: " + ", ".join(f"{fmt(c['s'])}<-{fmt(c['from'])}" for c in cover))
if dead:
    d = P.read("cuts/cuts.json")
    out = []
    for a, b in d["keep"]:
        for x, y in sorted(dead):
            if x < b and y > a:
                if x - a >= 0.3:
                    out.append([a, x])
                a = max(a, y)
        if b - a >= 0.3:
            out.append([a, b])
    d["keep"] = out
    d["cuts"] += [{"s": x, "e": y, "why": "loading screen (no talk)", "text": "", "kept": ""} for x, y in dead]
    P.write("cuts/cuts.json", d)
    say(f"{len(dead)} loading screens cut ({sum(y - x for x, y in dead):.1f} s)")
