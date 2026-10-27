r"""Privacy blur + checker: the user's home address / phone number must never be readable in a final video.

User rule (2026-10-20): when they say "blur the address" (or it simply shows on the phone), the final video MUST have it
blurred, and a checker proves it. No OCR on this machine, so we template-match the user's own address/number snippets
(the same in every video) on the phone crop at 4 fps, even while they scroll.

  python privacy.py find <source.mp4> <words.json> <out privacy.json> [--crop x,y,w,h]
      prints the spoken cues ("blur", "address", "my number") and finds every on-screen hit -> privacy.json
  python privacy.py check <render.mp4> <cuts.json> <privacy.json> [--scale 0.5]
      maps every hit into the render's timeline and FAILS any box that is still sharp (not blurred)
  python privacy.py apply <render.mp4> <cuts.json> <privacy.json> <out.mp4> [--scale 0.5]
      blurs every box in a second pass (use this; the ffmpeg overlay graph in filter() stalls with many boxes)

Templates: {{KIT}}/tools\privacy_templates\*.png (grayscale snippets cut from the user's phone screen).
Add new ones (new address, card number, email) the same way: crop the text from a frame, save it there.
"""
import glob
import json
import os
import re
import subprocess
import sys
from fractions import Fraction

import cv2
import numpy as np

TPL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privacy_templates")
CUES = ["blur", "address", "my number", "phone number", "personal info"]
CROP = (2628, 0, 504, 1080)  # phone mirror inside the 3840x1080 OBS capture (re-measure per video)


def phone_crop(src):
    """the phone as it sits in THIS recording (phone_edit/layout.phone_box) + 60 px each side. Uber codes october
    (2026-10-25): the phone was at x 2526, the fixed 2628 crop never saw its left 100 px, and his full name on the Uber
    account page went out unblurred once the PiP crop was fixed"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_edit"))
        from layout import phone_box
        x, y, w, h = phone_box(src)
    except Exception as err:
        print(f"privacy: phone not measured ({type(err).__name__}), using the fixed crop")
        x, y, w, h = CROP
    x0, x1 = max(1920, x - 60), min(3840, x + w + 60)
    return (x0, y, x1 - x0, h)
# box grows from the template hit to cover the whole field (2-line addresses): name -> (dx, dy, w, h)
GROW = {"cart-street": (-150, -6, 240, 62), "cart-deliver-to": (-6, -6, 240, 62), "checkout-home": (-8, -8, 300, 70), "phone-number": (-6, -6, 240, 42)}
FPS = 4


def ocr_grow(w, h):
    """box around an OCR'd address line -> (dx, dy, w, h): one line above and below too (an address wraps, and the
    half-scrolled-off line next to it is unreadable to OCR but not to a viewer: "...to Hidden" leaked 2026-10-21) and at
    least a full 'Deliver to <street>' width"""
    return (-6, -h - 8, max(w, 260) + 12, 3 * h + 16)


def templates():
    return [(os.path.splitext(os.path.basename(p))[0], cv2.imread(p, cv2.IMREAD_GRAYSCALE))
            for p in sorted(glob.glob(os.path.join(TPL_DIR, "*.png")))]


def find(src, words_path, out, crop=CROP):
    words = json.load(open(words_path, encoding="utf-8"))
    text = " ".join(w["w"].lower() for w in words)
    for cue in CUES:
        for m in re.finditer(re.escape(cue), text):
            k = text[:m.start()].count(" ")
            print(f'spoken cue "{cue}" at {words[k]["s"]:.1f} s: ...{" ".join(w["w"] for w in words[max(0, k - 6):k + 8])}...')
    x, y, w, h = crop
    tpls = templates()

    def scan(fps, ss=None, dur=None, extra=()):
        args = ["ffmpeg", "-v", "error"] + (["-ss", f"{ss:.3f}", "-t", f"{dur:.3f}"] if ss is not None else []) +                ["-i", src, "-vf", f"fps={fps},crop={w}:{h}:{x}:{y},format=gray", "-f", "rawvideo", "-"]
        p = subprocess.Popen(args, stdout=subprocess.PIPE)
        out, i, last, prev = [], 0, None, []
        while True:
            raw = p.stdout.read(w * h)
            if len(raw) < w * h:
                break
            fr = np.frombuffer(raw, np.uint8).reshape(h, w)
            small = cv2.resize(fr, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            if last is not None and float(cv2.absdiff(small, last).mean()) < 0.3:
                # phone screen did not move since the last frame: same boxes, no search (most frames of a tutorial)
                out.extend({**hp, "t": (ss or 0) + i / fps} for hp in prev)
                i += 1
                continue
            last, n0 = small, len(out)
            for name, t in list(tpls) + list(extra):
                # EVERY occurrence, not just the best one (several cart rows show the address at once)
                r = cv2.matchTemplate(fr, t, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(r > 0.75)
                taken = []
                for sc, my, mx in sorted(zip(r[ys, xs], ys, xs), reverse=True):
                    if any(abs(my - ty) < t.shape[0] and abs(mx - tx) < t.shape[1] for ty, tx in taken):
                        continue
                    taken.append((my, mx))
                    dx, dy, bw, bh = GROW.get(name) or (ocr_grow(t.shape[1], t.shape[0]) if name.startswith("ocr-address") else
                                                        (-6, -6, t.shape[1] + 12, t.shape[0] + 12))
                    out.append({"t": (ss or 0) + i / fps, "what": name, "score": round(float(sc), 2), "step": 1 / fps,
                                "box": [int(x + mx + dx), int(y + my + dy), int(bw), int(bh)]})
            prev = out[n0:]
            i += 1
        p.wait()
        return out

    def ocr_scan(fps):
        """the user's own addresses / real name read off the phone by OCR (privacy_terms.json), in ANY app. Frames
        where the phone did not change reuse the last reading. -> hits + text crops used as 30 fps templates"""
        import privacy_ocr
        terms = privacy_ocr.load_terms()
        if not any(terms[:3]) and not terms[3]:
            print("privacy: no privacy_terms.json terms, OCR pass skipped")
            return [], []
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},crop={w}:{h}:{x}:{y},format=gray", "-f", "rawvideo", "-"],
                             stdout=subprocess.PIPE)
        out, crops, i, last, boxes, n_ocr = [], [], 0, None, [], 0
        while True:
            raw = p.stdout.read(w * h)
            if len(raw) < w * h:
                break
            fr = np.frombuffer(raw, np.uint8).reshape(h, w)
            small = cv2.resize(fr, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            if last is None or float(cv2.absdiff(small, last).mean()) > 0.6:
                boxes = privacy_ocr.private_boxes(privacy_ocr.ocr(fr), terms)
                last, n_ocr = small, n_ocr + 1
                for what, (bx, by, bw, bh) in boxes:
                    c = fr[max(0, by - 2):by + bh + 2, max(0, bx - 2):bx + bw + 2]
                    near = [k for _, k, kt in crops if i / fps - kt < 3.0]
                    if c.shape[0] >= 8 and c.shape[1] >= 16 and not any(c.shape == k.shape and cv2.absdiff(c, k).mean() < 8 for k in near):
                        crops.append((f"ocr-{what}", c.copy(), i / fps))
            for what, (bx, by, bw, bh) in boxes:
                gx, gy, gw, gh = ocr_grow(bw, bh) if what == "address" else (-6, -6, bw + 12, bh + 12)
                out.append({"t": i / fps, "what": f"ocr-{what}", "score": 1.0, "step": 1 / fps,
                            "box": [int(x + bx + gx), int(y + by + gy), int(gw), int(gh)]})
            i += 1
        p.wait()
        print(f"privacy OCR: {i} frames, {n_ocr} read (the rest unchanged), {len(out)} private-text hits, {len(crops)} distinct snippets")
        return out, crops

    def screen_scan(fps=2):
        """the website / desktop half (work\\halves.json says when a half is a "screen"): OCR it for the user's terms too
        (Shein 2026-10-21: the checkout page sits on the left half, where the phone-only scan never looked)"""
        hp = os.path.join(os.path.dirname(os.path.abspath(out)), "halves.json")
        if not os.path.exists(hp):
            return []
        import privacy_ocr
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_edit"))
        import halves
        terms = privacy_ocr.load_terms()
        hf, kl, kr = halves.load(hp)
        hits = []
        for side, kinds, x0 in (("left", kl, 0), ("right", kr, 1920)):
            if "screen" not in kinds:
                continue
            p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},crop=1920:1080:{x0}:0,format=gray", "-f", "rawvideo", "-"],
                                 stdout=subprocess.PIPE)
            i, last, boxes, n_ocr = 0, None, [], 0
            while True:
                raw = p.stdout.read(1920 * 1080)
                if len(raw) < 1920 * 1080:
                    break
                t = i / fps
                k = kinds[min(int(t * hf), len(kinds) - 1)]
                if k == "screen":
                    fr = np.frombuffer(raw, np.uint8).reshape(1080, 1920)
                    small = cv2.resize(fr, (480, 270), interpolation=cv2.INTER_AREA)
                    if last is None or float(cv2.absdiff(small, last).mean()) > 0.6:
                        boxes = privacy_ocr.private_boxes(privacy_ocr.ocr(fr), terms)
                        last, n_ocr = small, n_ocr + 1
                    for what, (bx, by, bw, bh) in boxes:
                        gx, gy, gw, gh = ocr_grow(bw, bh) if what == "address" else (-6, -6, bw + 12, bh + 12)
                        hits.append({"t": t, "what": f"ocr-{what}", "score": 1.0, "step": 1 / fps,
                                     "box": [int(x0 + bx + gx), int(by + gy), int(gw), int(gh)]})
                else:
                    last, boxes = None, []
                i += 1
            p.wait()
            print(f"privacy OCR on the {side} screen half: {n_ocr} frames read, {len(hits)} private-text hits so far")
        return hits

    # pass 1: 4 fps over the whole video (Uber templates + OCR of the user's terms); pass 2: 30 fps around every hit,
    # matching the templates AND the exact text snippets OCR found, so boxes follow fast scrolls
    def rough_and_ocr(fps):
        """scan(fps) + ocr_scan(fps) from ONE decode of the phone crop (2026-10-22, faster first builds): the same frames,
        the same per-frame logic and thresholds as the two separate passes, so the same hits."""
        import privacy_ocr
        terms = privacy_ocr.load_terms()
        do_ocr = any(terms[:3]) or bool(terms[3])
        if not do_ocr:
            print("privacy: no privacy_terms.json terms, OCR pass skipped")
        import queue
        import threading
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},crop={w}:{h}:{x}:{y},format=gray", "-f", "rawvideo", "-"],
                             stdout=subprocess.PIPE)
        # one decode, two workers in parallel (each sees every frame in order, so the results match the two old passes)
        q_t, q_o = queue.Queue(maxsize=96), queue.Queue(maxsize=96)
        rough_, o_out, crops = [], [], []
        stats = {"n_ocr": 0, "i": 0}

        def templates_worker():
            t_last, t_prev = None, []
            while True:
                item = q_t.get()
                if item is None:
                    return
                i, fr, small = item
                if t_last is not None and float(cv2.absdiff(small, t_last).mean()) < 0.3:
                    rough_.extend({**hp, "t": i / fps} for hp in t_prev)
                    continue
                t_last, n0 = small, len(rough_)
                for name, t in list(tpls):
                    r = cv2.matchTemplate(fr, t, cv2.TM_CCOEFF_NORMED)
                    ys, xs = np.where(r > 0.75)
                    taken = []
                    for sc, my, mx in sorted(zip(r[ys, xs], ys, xs), reverse=True):
                        if any(abs(my - ty) < t.shape[0] and abs(mx - tx) < t.shape[1] for ty, tx in taken):
                            continue
                        taken.append((my, mx))
                        dx, dy, bw, bh = GROW.get(name) or (ocr_grow(t.shape[1], t.shape[0]) if name.startswith("ocr-address") else
                                                            (-6, -6, t.shape[1] + 12, t.shape[0] + 12))
                        rough_.append({"t": i / fps, "what": name, "score": round(float(sc), 2), "step": 1 / fps,
                                       "box": [int(x + mx + dx), int(y + my + dy), int(bw), int(bh)]})
                t_prev = rough_[n0:]

        def ocr_worker():
            o_last, boxes = None, []
            while True:
                item = q_o.get()
                if item is None:
                    return
                i, fr, small = item
                if o_last is None or float(cv2.absdiff(small, o_last).mean()) > 0.6:
                    boxes = privacy_ocr.private_boxes(privacy_ocr.ocr(fr), terms)
                    o_last = small
                    stats["n_ocr"] += 1
                    for what, (bx, by, bw, bh) in boxes:
                        c = fr[max(0, by - 2):by + bh + 2, max(0, bx - 2):bx + bw + 2]
                        near = [k for _, k, kt in crops if i / fps - kt < 3.0]
                        if c.shape[0] >= 8 and c.shape[1] >= 16 and not any(c.shape == k.shape and cv2.absdiff(c, k).mean() < 8 for k in near):
                            crops.append((f"ocr-{what}", c.copy(), i / fps))
                for what, (bx, by, bw, bh) in boxes:
                    gx, gy, gw, gh = ocr_grow(bw, bh) if what == "address" else (-6, -6, bw + 12, bh + 12)
                    o_out.append({"t": i / fps, "what": f"ocr-{what}", "score": 1.0, "step": 1 / fps,
                                  "box": [int(x + bx + gx), int(y + by + gy), int(gw), int(gh)]})

        workers = [threading.Thread(target=templates_worker, daemon=True)] + ([threading.Thread(target=ocr_worker, daemon=True)] if do_ocr else [])
        for th in workers:
            th.start()
        i = 0
        while True:
            raw = p.stdout.read(w * h)
            if len(raw) < w * h:
                break
            fr = np.frombuffer(raw, np.uint8).reshape(h, w)
            small = cv2.resize(fr, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            q_t.put((i, fr, small))
            if do_ocr:
                q_o.put((i, fr, small))
            i += 1
        p.wait()
        q_t.put(None)
        if do_ocr:
            q_o.put(None)
        for th in workers:
            th.join()
        n_ocr = stats["n_ocr"]
        if do_ocr:
            print(f"privacy OCR: {i} frames, {n_ocr} read (the rest unchanged), {len(o_out)} private-text hits, {len(crops)} distinct snippets")
        return rough_, o_out, crops

    import time as _time
    _t0 = _time.time()
    if os.environ.get("PRIVACY_FAST", "1") != "0":
        # one decode for templates + phone OCR, and the website-half OCR at the same time (its own decode + OCR engine)
        from concurrent.futures import ThreadPoolExecutor as _TPE
        with _TPE(2) as _ex:
            _scr = _ex.submit(screen_scan)
            rough, ocr_hits, ocr_crops = rough_and_ocr(FPS)
            ocr_hits += _scr.result()
        _t3 = _time.time()
        print(f"privacy timing: phone templates + OCR (one decode) with screen OCR alongside {_t3 - _t0:.0f}s", flush=True)
    else:
        rough = scan(FPS)
        _t1 = _time.time()
        ocr_hits, ocr_crops = ocr_scan(FPS)
        _t2 = _time.time()
        ocr_hits += screen_scan()
        _t3 = _time.time()
        print(f"privacy timing: templates {_t1 - _t0:.0f}s, phone OCR {_t2 - _t1:.0f}s, screen OCR {_t3 - _t2:.0f}s", flush=True)
    windows = []
    for hit in sorted(rough + ocr_hits, key=lambda r: r["t"]):
        a, b = hit["t"] - 1.0, hit["t"] + 1.0
        if windows and a <= windows[-1][1]:
            windows[-1][1] = b
        else:
            windows.append([max(0, a), b])
    # long windows (the address sits in an app's top bar for minutes) go in 4 s chunks, each with only its nearby snippets
    windows = [[a + k * 4.0, min(b, a + (k + 1) * 4.0)] for a, b in windows for k in range(int((b - a) // 4.0) + 1) if a + k * 4.0 < b]
    # OCR hits are kept as they are too (a motion-blurred frame can defeat the snippet match)
    # windows are independent: search them on many cores at once (matchTemplate + ffmpeg release the GIL; one at a
    # time this pass took ~6 of 8 min on a 19 min video)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(min(16, os.cpu_count() or 4)) as ex:
        found = ex.map(lambda ab: scan(30, ab[0], ab[1] - ab[0], [(n, k) for n, k, kt in ocr_crops if ab[0] - 1.5 <= kt <= ab[1] + 1.5]), windows)
        hits = [h_ for part in found for h_ in part] + ocr_hits
    print(f"privacy timing: 30 fps windows {_time.time() - _t3:.0f}s", flush=True)
    if not hits:
        for cue in CUES:
            if re.search(r"\b" + re.escape(cue) + r"\b", text):
                print(f'!! PRIVACY: you said "{cue}" but nothing private was found on screen. Check the video by eye '
                      f'(or add the text to privacy_terms.json) before uploading.')
                break
    # one item per detection, covering its frame (plus a hair), with margin for motion inside the frame
    items = [{"what": h_["what"], "s": round(max(0, h_["t"] - 1.6 * h_["step"]), 3), "e": round(h_["t"] + 1.6 * h_["step"], 3),
              "box": [h_["box"][0] - 10, h_["box"][1] - 14, h_["box"][2] + 20, h_["box"][3] + 28]} for h_ in hits]
    # one item per box that stays put: same box (within 3 px) in overlapping/touching times -> one longer item
    # (an address in a top bar for 30 s was ~900 one-frame items, which made apply crawl)
    merged = {}
    for it in sorted(items, key=lambda r: r["s"]):
        key = (it["what"].split("-")[0], tuple(v // 4 for v in it["box"]))
        m = merged.get(key)
        if m and it["s"] <= m["e"] + 0.05:
            m["e"] = max(m["e"], it["e"])
        else:
            if m:
                merged.setdefault("_done", []).append(m)
            merged[key] = dict(it)
    items = merged.pop("_done", []) + list(merged.values())
    items.sort(key=lambda r: r["s"])
    json.dump(items, open(out, "w"), indent=1)
    print(f"{len(rough)} rough hits in {len(windows)} windows -> {len(hits)} frame-accurate hits")
    for it in items:
        print(f'  {it["what"]:16s} {it["s"]:7.2f}-{it["e"]:7.2f}  box {it["box"]}')


def to_out(t, keep):
    acc = 0.0
    for s, e in keep:
        if s <= t < e:
            return acc + (t - s)
        acc += e - s
    return None


def out_spans(items, cuts):
    """Each item's source span mapped onto the render timeline (split where cuts remove parts of it)."""
    spans, acc = [], 0.0
    for s, e in cuts["keep"]:
        for it in items:
            # detection lags a screen change by a frame or two: every box starts 0.35 s early and ends 0.2 s late (the
            # Carts screen came up 0.35 s before a cut and that last frame showed the address, Doordash 6:25)
            a, b = max(s, it["s"] - 0.35), min(e, it["e"] + 0.2)
            if a < b:
                # a box starting just after a cut must cover the piece's FIRST frames too (the address showed for one
                # frame right after a seam at Doordash 6:25, 2026-10-21); same at a piece's end
                a = s if a - s < 0.35 else a
                b = e if e - b < 0.35 else b
                spans.append({**it, "os": acc + (a - s), "oe": acc + (b - s)})
        acc += e - s
    return spans


def filter(items, cuts, scale=0.5, src_w=3840):
    """[v] -> [vb]: blur every privacy box on the render timeline (call AFTER select/setpts/scale)."""
    chain, cur = [], "v"
    for k, sp in enumerate(out_spans(items, cuts)):
        bx, by, bw, bh = [int(round(v * scale)) for v in sp["box"]]
        chain.append(f"[{cur}]split[b{k}a][b{k}b];[b{k}b]crop={bw}:{bh}:{bx}:{by},boxblur=12:3[b{k}c];"
                     f"[b{k}a][b{k}c]overlay={bx}:{by}:enable='between(t,{sp['os']:.3f},{sp['oe']:.3f})'[p{k}]")
        cur = f"p{k}"
    return ";".join(chain), cur


def _blur_frame(fr, t, spans, fps, scale):
    n = 0
    for sp in spans:
        if sp["os"] - 0.6 / fps <= t <= sp["oe"] + 0.6 / fps:  # half-frame slack: seams land between frames
            x, y, bw, bh = [int(round(v * scale)) for v in sp["box"]]
            x, y = max(0, x), max(0, y)
            roi = fr[y:y + bh, x:x + bw]
            if roi.size:
                fr[y:y + bh, x:x + bw] = cv2.GaussianBlur(roi, (0, 0), 9)
                n += 1
    return n


def seam_spans(render, cuts, scale, n=4):
    """OCR the first and last n frames of every kept piece of the RENDER, whole frame. A screen that changes right at a
    cut (Carts list sliding in on the last frame before a cut, Doordash 6:25) is caught by no sampled detection; here
    every seam frame is read directly, and its boxes cover that frame only."""
    try:
        import privacy_ocr
    except Exception:
        return []
    terms = privacy_ocr.load_terms()
    if not any(terms[:3]) and not terms[3]:
        return []
    fps = cv2.VideoCapture(render).get(cv2.CAP_PROP_FPS) or 30
    out, acc = [], 0.0
    for s, e in cuts["keep"]:
        d = e - s
        # each seam frame gets only its OWN boxes (spread over 0.35 s they blurred the previous screen's content)
        for t in [acc + k / fps for k in range(n)] + [acc + d - (k + 1) / fps for k in range(n)]:
            a = b = t
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.4f}", "-i", render, "-frames:v", "1", "-vf", "format=gray",
                                  "-f", "rawvideo", "-"], capture_output=True).stdout
            w_ = int(3840 * scale) if len(raw) == int(3840 * scale) * int(1080 * scale) else None
            if not w_:
                continue
            fr = np.frombuffer(raw, np.uint8).reshape(int(1080 * scale), w_)
            for what, (bx, by, bw, bh) in privacy_ocr.private_boxes(privacy_ocr.ocr(fr), terms):
                gx, gy, gw, gh = ocr_grow(bw, bh) if what == "address" else (-6, -6, bw + 12, bh + 12)
                out.append({"what": f"seam-{what}", "os": a, "oe": b,
                            "box": [int((bx + gx) / scale), int((by + gy) / scale), int(gw / scale), int(gh / scale)]})
        acc += d
    print(f"privacy seams: read {len(cuts['keep']) * 2 * n} seam frames, {len(out)} boxes")
    return out


def apply(render, cuts_path, items_path, out, scale=0.5, cq="19"):
    """Second pass on a finished cut: Gaussian-blur every privacy box frame by frame (the 68-overlay ffmpeg graph
    stalled). Only the keyframe-to-keyframe pieces that hold a box are decoded and re-encoded (NVENC H.264 High
    yuv420p, same cq as the draft cut); everything else is stream-copied, so a video with nothing to blur costs a
    file copy instead of a full 4K re-encode (user 2026-10-21: the blur added 10-15 min per video)."""
    import shutil
    import tempfile
    cuts, items = json.load(open(cuts_path)), json.load(open(items_path))
    spans = out_spans(items, cuts) + seam_spans(render, cuts, scale)
    if not spans:
        shutil.copyfile(render, out)
        print(f"privacy apply: nothing to blur, copied -> {out}")
        return
    cap = cv2.VideoCapture(render)
    fps, w, h = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    # the frame rate comes from the stream's r_frame_rate, never from OpenCV: OpenCV reports avg_frame_rate
    # (30.001 on Uber codes october), the blurred piece got a 1/311980 time base and the concat stretched every
    # frame after it over 25 minutes (a frozen draft, 2026-10-25)
    rfr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", render],
                         capture_output=True, text=True).stdout.strip() or "30/1"
    fps = float(Fraction(rfr))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", render],
                               capture_output=True, text=True).stdout)
    pk = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", render],
                        capture_output=True, text=True).stdout.split()
    kfs = sorted(float(l.split(",")[0]) for l in pk if "K" in l.split(",")[1])
    tb = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=time_base", "-of", "csv=p=0", render],
                        capture_output=True, text=True).stdout.strip().replace("/", "\\/") or "1\\/15360"

    def copy_piece(a, b, pth):
        # stream copy keyframe a .. keyframe b; the draft has B-frames, so a plain -t also pulls in the next GOP's
        # first packets (3 extra frames per seam): drop every packet shown at or after b
        cut = (b - a) - 0.5 / fps
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.6f}", "-i", render, "-t", f"{b - a + 0.5:.6f}", "-map", "0:v", "-c", "copy",
                        "-bsf:v", f"noise=drop='gte(pts*{tb}\\,{cut:.6f})'", pth], check=True)
    # re-encode windows: from the keyframe at/before each box to the keyframe after it, merged when they touch
    wins = []
    for sp in sorted(spans, key=lambda s: s["os"]):
        a, b = sp["os"] - 1 / fps, sp["oe"] + 1 / fps
        ka = max([k for k in kfs if k <= a + 1e-6] or [0.0])
        kb = min([k for k in kfs if k > b] or [dur])
        if wins and ka <= wins[-1][1] + 1e-6:
            wins[-1][1] = max(wins[-1][1], kb)
        else:
            wins.append([ka, kb])
    tmp = tempfile.mkdtemp(prefix="privacy_", dir=os.path.dirname(os.path.abspath(out)))
    parts, pos, blurred, nfr = [], 0.0, 0, 0
    try:
        for k, (a, b) in enumerate(wins):
            if a > pos + 1e-6:  # untouched stretch: copy the packets as they are
                pth = os.path.join(tmp, f"c{k}.mp4")
                copy_piece(pos, a, pth)
                parts.append(pth)
            pth = os.path.join(tmp, f"b{k}.mp4")
            n = int(round((b - a) * fps))
            dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.6f}", "-i", render, "-frames:v", str(n), "-map", "0:v",
                                    "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
            enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
                                    "-i", "-", "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-cq", str(cq),
                                    "-video_track_timescale", tb.replace("\\/", "/").split("/")[-1], pth], stdin=subprocess.PIPE)
            i = 0
            while True:
                raw = dec.stdout.read(w * h * 3)
                if len(raw) < w * h * 3:
                    break
                fr = np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()
                blurred += _blur_frame(fr, a + i / fps, spans, fps, scale)
                enc.stdin.write(fr.tobytes())
                i += 1
            dec.wait()
            enc.stdin.close()
            if enc.wait() != 0:
                raise RuntimeError(f"encode of {a:.2f}-{b:.2f} failed")
            parts.append(pth)
            nfr += i
            pos = b
        if pos < dur - 0.5 / fps:
            pth = os.path.join(tmp, "tail.mp4")
            copy_piece(pos, dur + 1.0, pth)
            parts.append(pth)
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("".join(f"file '{p_}'\n" for p_ in parts))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", render, "-map", "0:v", "-map", "1:a",
                        "-c", "copy", out], check=True)
        # guard: the blurred file must have the render's frames over the render's length (a timebase mix-up
        # stretches the picture while the sound stays right, and every later stage builds a frozen video)
        vdur = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                                     "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip() or 0)
        if abs(vdur - dur) > 1.0:
            os.remove(out)
            raise RuntimeError(f"privacy apply: blurred video is {vdur:.1f} s, the cut is {dur:.1f} s (timestamps broken)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"privacy apply: re-encoded {len(wins)} piece(s), {nfr / fps:.1f} s of {dur:.1f} s, {blurred} box blurs -> {out}")


def sharpness(path, t, box):
    x, y, w, h = box
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                          "-vf", f"crop={w}:{h}:{x}:{y},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(raw) < w * h:
        return None
    return float(cv2.Laplacian(np.frombuffer(raw, np.uint8).reshape(h, w), cv2.CV_64F).var())


def check(render, cuts_path, items_path, scale=0.5):
    cuts, items = json.load(open(cuts_path)), json.load(open(items_path))
    bad, n = [], 0
    # box test: read frames exactly like apply() does (an ffmpeg -ss seek can land a frame off at 30 fps)
    spans = out_spans(items, cuts)
    cap = cv2.VideoCapture(render)
    fps, i = cap.get(cv2.CAP_PROP_FPS), 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = i / fps
        if True:
            g = None
            for sp in spans:
                if abs(t - (sp["os"] + sp["oe"]) / 2) <= 0.5 / fps:  # the frame each box was made for
                    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) if g is None else g
                    x, y, bw, bh = [max(0, int(round(v * scale))) for v in sp["box"]]
                    roi = g[y:y + bh, x:x + bw]
                    if roi.size:
                        n += 1
                        v = float(cv2.Laplacian(roi, cv2.CV_64F).var())
                        if v > 400:  # readable text ~7000; a blurred box with a button edge inside ~60-130
                            bad.append(f'{int(t // 60)}:{t % 60:05.2f}  {sp["what"]} NOT BLURRED (sharpness {v:.0f})')
        i += 1
    # sweep: any template still readable ANYWHERE on the phone (catches fields the finder never boxed)
    tpls = templates()
    cx, cy, cw, ch = [int(round(v * scale)) for v in CROP]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", render, "-vf", f"fps={FPS},crop={cw}:{ch}:{cx}:{cy},format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    k = 0
    while True:
        raw = p.stdout.read(cw * ch)
        if len(raw) < cw * ch:
            break
        fr = np.frombuffer(raw, np.uint8).reshape(ch, cw)
        for name, t in tpls:
            ts = cv2.resize(t, (max(1, int(t.shape[1] * scale)), max(1, int(t.shape[0] * scale))))
            if cv2.minMaxLoc(cv2.matchTemplate(fr, ts, cv2.TM_CCOEFF_NORMED))[1] > 0.8:
                tt = k / FPS
                bad.append(f'{int(tt // 60)}:{tt % 60:05.2f}  {name} READABLE on screen (sweep)')
        k += 1
    p.wait()
    print(f"privacy check: {n} box samples + {k} sweep frames, {len(bad)} problems")
    for b in bad:
        print("  FAIL", b)
    return not bad


if __name__ == "__main__":
    a = sys.argv[1:]
    sc = float(a[a.index("--scale") + 1]) if "--scale" in a else 0.5
    if a and a[0] == "find":
        crop = tuple(int(v) for v in a[a.index("--crop") + 1].split(",")) if "--crop" in a else phone_crop(a[1])
        find(a[1], a[2], a[3], crop)
    elif a and a[0] == "apply":
        apply(a[1], a[2], a[3], a[4], sc, a[a.index("--cq") + 1] if "--cq" in a else "19")
    elif a and a[0] == "check":
        sys.exit(0 if check(a[1], a[2], a[3], sc) else 1)
    else:
        print(__doc__)
