"""He holds a product up to the TALKING camera while his face stays in shot (ultimate dhgate free reselling spreadsheet
2026-10-23, 4:43 / 5:09 / 5:21: "I'm showing off some AirPods in the main camera ... I'm clearly showing off something in
my main camera compared to the desktop, so we may need to add some logic so it can swap between the cameras and webcam
scene"). find_holdups only catches a product that hides his face (a shoe, a bag); small things (an AirPods case, a box at
chin height) leave the face visible, so the layout stayed on the desktop with the circle.

    find_showing(project, cam, rows, kept, sections, left_screen, W, H, cfg, checks) -> [(s, e), ...] source seconds

1. MediaPipe hand landmarks on the talking camera (the right half where the desktop is on the left, else Camera A) at
   2 fps over the kept review/showcase footage: a hand raised into the upper half of the frame, big (close to the lens),
   for >= 1 s = a candidate.
2. One look per 12 candidates (pipeline brain, vision): is he HOLDING SOMETHING UP to show it, or only gesturing/pointing?
3. Confirmed runs, padded 0.3 s, merged, >= 1.2 s. Cached in work/showing.json (delete to redo); listed in Check these.
"""
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SKILL = Path(__file__).resolve().parent.parent
FPS = 2.0
SW, SH = 640, 360


def _hands():
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    model = SKILL / "models" / "hand_landmarker.task"
    if not model.exists():
        return None, None
    opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model)), num_hands=2,
                                        min_hand_detection_confidence=0.4)
    return mp, vision.HandLandmarker.create_from_options(opts)


def _raised(res, top=0.55, min_h=0.12):
    for lm in res.hand_landmarks:
        ys = [p.y for p in lm]
        if min(ys) < top and max(ys) - min(ys) >= min_h:
            return True
    return False


def find_showing(project, cam, rows, kept, sections, left_screen, W, H, cfg, checks):
    sc = cfg.get("showing", {})
    if not sc.get("enabled", True):
        return []
    work = project / "work"
    cache = work / "showing.json"
    def at_desk(a, b, on_left_):
        """his face on the talking camera for >= desk_face_share of the stretch. Showing = holding a product up WHILE his face
        stays in shot; in a try-on he stands away from the desk and the other camera is already filming him (best sp5der
        hoodie 2026-10-23, 3:38 / 6:14: "during the try-on the camera swapped to my main camera ... in a try-on, stay on the
        camera that is already filming it"; the talking camera saw his face 0 % of those stretches, desk talk 95-100 %)."""
        rs = [r for r in rows if a <= r["t"] <= b]
        if not rs:
            return True
        key = "rfx" if on_left_(a + (b - a) / 2) else "fx"
        return sum(r.get(key) is not None for r in rs) / len(rs) >= sc.get("desk_face_share", 0.4)

    on_left0 = lambda t: any(a <= t <= b for a, b in left_screen)
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        rs = [tuple(r) for r in d.get("ranges", [])]
        keep = [r for r in rs if at_desk(r[0], r[1], on_left0)]
        if len(keep) < len(rs):
            checks.append("Showing-to-camera: dropped " + ", ".join(f"{a // 60:.0f}:{a % 60:04.1f}-{b // 60:.0f}:{b % 60:04.1f}"
                          for a, b in rs if (a, b) not in keep) + " (source): no face on the talking camera = a try-on, the "
                          "camera already filming it stays.")
        return keep
    secs = [(x["start"], x["end"]) for x in sections if x["name"] in ("review", "showcase")]
    spans = [(max(a, sa), min(b, sb)) for a, b in kept for sa, sb in secs if min(b, sb) - max(a, sa) >= 1.0]
    if not spans:
        return []
    try:
        mp, lm = _hands()
    except Exception as e:
        checks.append(f"Showing-to-camera detection skipped (hand model: {type(e).__name__}).")
        return []
    if lm is None:
        checks.append("Showing-to-camera detection skipped (models/hand_landmarker.task missing).")
        return []
    hw = W // 2
    on_left = lambda t: any(a <= t <= b for a, b in left_screen)   # desktop on the left: he talks on the RIGHT camera
    # both halves, 2 fps, small: one decode of the whole recording
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(cam), "-vf", f"fps={FPS},scale={SW * 2}:{SH}", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = SW * 2 * SH * 3
    hits, k = [], 0
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        t = k / FPS
        k += 1
        if not any(a <= t <= b for a, b in spans):
            continue
        img = np.frombuffer(buf, np.uint8).reshape(SH, SW * 2, 3)
        half = img[:, SW:] if on_left(t) else img[:, :SW]
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(half)))
        if _raised(res):
            hits.append(t)
    proc.wait()
    # runs: hits <= 1 s apart, >= 1 s long
    runs = []
    for t in hits:
        if runs and t - runs[-1][1] <= 1.0:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    cands = [(a, b) for a, b in runs if b - a >= 1.0 - 1e-6]
    verdicts = _verify(project, cam, cands, on_left, checks) if cands else {}
    ok = [(a, b) for n, (a, b) in enumerate(cands) if verdicts.get(n) and at_desk(a, b, on_left)]
    pad = sc.get("pad_seconds", 0.3)
    merged = []
    for a, b in sorted(ok):
        a, b = a - pad, b + 1.0 / FPS + pad
        if merged and a <= merged[-1][1] + 1.0:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    ranges = [(round(max(a, x), 2), round(min(b, y), 2)) for a, b in merged for x, y in kept if min(b, y) - max(a, x) >= 1.2]
    cache.write_text(json.dumps({"candidates": cands, "verdicts": {str(k): v for k, v in verdicts.items()}, "ranges": ranges},
                                indent=1), encoding="utf-8")
    if ranges:
        checks.append("Showing something to the talking camera (hand up + vision check): that camera full frame, no circle at "
                      + ", ".join(f"{a // 60:.0f}:{a % 60:04.1f}-{b // 60:.0f}:{b % 60:04.1f}" for a, b in ranges)
                      + f" (source; {len(cands)} raised-hand moments looked at). Delete work/showing.json to redo.")
    return ranges


def _verify(project, cam, cands, on_left, checks, per_sheet=12):
    sys.path.insert(0, r"{{KIT}}/tools")
    try:
        import claude_brain
    except Exception as e:
        checks.append(f"Showing-to-camera: no vision check ({type(e).__name__}); nothing switched.")
        return {}
    out = {}
    tmp = Path(tempfile.mkdtemp(prefix="showing_"))
    for s0 in range(0, len(cands), per_sheet):
        group = cands[s0:s0 + per_sheet]
        items = []
        for n, (a, b) in enumerate(group):
            t = (a + b) / 2
            crop = "crop=iw/2:ih:iw/2:0" if on_left(t) else "crop=iw/2:ih:0:0"
            items.append((str(cam), t, str(n + 1), crop))
        sheet = tmp / f"sheet{s0}.png"
        claude_brain.contact_sheet(items, str(sheet), cols=4, w=400)
        prompt = ("The attached image is a grid of numbered frames from a webcam: a man at his desk talking to the camera. "
                  "For EACH number, answer true if he is HOLDING AN OBJECT UP to show it to the camera (a product, a box, an "
                  "earbuds case, a bottle, clothing, a phone held up facing the lens), false if his hands are empty or only "
                  "gesturing, pointing, adjusting the mic or resting. Answer with ONLY JSON like {\"1\": true, \"2\": false}.")
        try:
            j = claude_brain.ask("showing_check", prompt, images=[str(sheet)])
        except Exception:
            j = None
        if not isinstance(j, dict):
            checks.append("Showing-to-camera: the vision check gave no answer for some moments; those stay on the desktop layout.")
            continue
        for n in range(len(group)):
            v = j.get(str(n + 1))
            out[s0 + n] = v is True or str(v).lower() == "true"
    return out


LIST_STOP = {"but", "me", "so", "and", "guys", "yes", "yeah", "okay", "ok", "though", "now", "well", "again", "too", "actually",
             "like", "right", "it", "that", "this", "you", "i", "honestly", "anyways", "anyway", "again", "first", "then", "here",
             "there", "also", "though", "obviously", "basically", "literally", "man", "bro", "know", "see", "look"}


def find_pointing(project, rows, kept, words, sections, left_screen, cfg, checks):
    """He LISTS things on his fingers to the talking camera (top 5 products to resell in winter 2024, 2026-10-24, 8:39:
    "I'm basically pointing out different products with my hands, Denim Tears, Hellstar, Nike Tech ... have it zoom in for
    the main camera ... then it goes back to the webcam view how we had it before"). A raised-hand moment from
    find_showing (the vision check said "only gesturing") that overlaps a spoken LIST (>= 2 commas, each item <= 3 words:
    "Hellstar, Denim Tyr, Spider, and also Nike Techs.") = the talking camera full frame with a gentle punch-in for the list,
    then back to the layout before. Needs his face on the talking camera (not a try-on). Returns [(s, e, "a" | "b")]."""
    sc = cfg.get("showing", {})
    if not sc.get("pointing", True):
        return []
    try:
        d = json.loads((project / "work" / "showing.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cands = [tuple(c) for c in d.get("candidates", [])]
    if not cands:
        return []
    secs = [(x["start"], x["end"]) for x in sections if x["name"] in ("review", "showcase")]
    ws = sorted(words, key=lambda w: w["s"])
    lists = []
    for i, w in enumerate(ws):
        if not w["w"].strip().endswith(","):
            continue
        commas = [i]
        j = i
        while True:
            nxt = next((k for k in range(j + 1, min(j + 4, len(ws))) if ws[k]["w"].strip().endswith(",")), None)
            if nxt is None:
                break
            commas.append(nxt)
            j = nxt
        if len(commas) < 2 or (lists and lists[-1][2] >= i):
            continue
        # list ITEMS are names / things, not "$45, but trust me, it is worth" or "so, yeah, guys,"
        items = [re.sub(r"[^\w']", "", ws[k]["w"]).lower() for k in commas]
        if any(not x.isalpha() or x in LIST_STOP for x in items):
            continue
        k0 = i - 1 if i and ws[i - 1]["w"][:1].isupper() and not ws[i - 2]["w"].strip().endswith((".", "?", "!")) else i
        end = next((k for k in range(commas[-1] + 1, min(commas[-1] + 6, len(ws))) if ws[k]["w"].strip().endswith((".", "?", "!"))),
                   min(commas[-1] + 3, len(ws) - 1))
        lists.append((ws[k0]["s"], ws[end]["e"], commas[-1], " ".join(x["w"] for x in ws[k0:end + 1])))
    on_left = lambda t: any(a <= t <= b for a, b in left_screen)
    out, said = [], []
    for s, e, _, text in lists:
        if not any(a - 1.0 <= e and s <= b + 1.0 for a, b in cands) or not any(a <= s <= b for a, b in secs):
            continue
        s, e = s - 0.35, e + 0.5
        side = "b" if on_left((s + e) / 2) else "a"
        rs = [r for r in rows if s <= r["t"] <= e]
        key = "rfx" if side == "b" else "fx"
        if not rs or sum(r.get(key) is not None for r in rs) / len(rs) < sc.get("desk_face_share", 0.4):
            continue
        for a, b in kept:
            lo, hi = max(a, s), min(b, e)
            if hi - lo >= 1.2:
                out.append((round(lo, 2), round(hi, 2), side))
                said.append(f"{lo // 60:.0f}:{lo % 60:04.1f} \"{text[:60]}\"")
    if out:
        checks.append("Listing on his fingers to the talking camera (raised hand + a spoken list): that camera full frame with a "
                      "punch-in, then back, at " + "; ".join(said) + " (source). showing.pointing = false turns it off.")
    return out
