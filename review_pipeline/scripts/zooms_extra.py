"""Extra keyframed zooms (user 2026-10-22, dhgate asics):
- side_zooms: slow, subtle push-in / pull-out on the full-frame side-angle camera so a long talking shot never sits dead still.
- topic_zooms: when he talks about sizes or the bulk-buying discount over the store page, zoom onto that panel
  (size selector, "1 Piece+ / 2 Piece+ / 5 Piece+" price tiers). The panel is found with Windows OCR on the frame.
All events use the same eased envelope as the other zooms (zoom_filter in edit_review), so every move is keyframed."""
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, r"{{KIT}}/tools")


def _overlaps(a, b, events, key, margin=0.5):
    return any(key in e and a < e["end"] + margin and b > e["start"] - margin for e in events)


def side_zooms(rows, kept, full_a, left_screen, existing, cfg):
    """Source-time 'b' events on stretches where the right half (side angle) is the full picture."""
    zc = cfg["zooms"].get("side", {})
    if not zc.get("enabled", True):
        return []
    runs, start, last = [], None, None
    for r in rows:
        if r.get("right") == "side" and r.get("left") != "screen":
            if start is None:
                start = r["t"]
            last = r["t"]
        else:
            if start is not None:
                runs.append((start, last))
            start = None
    if start is not None:
        runs.append((start, last))
    spans = []
    for ra, rb in runs:
        for ka, kb in kept:   # an event never crosses a cut (output time would jump mid-move)
            lo, hi = max(ra, ka), min(rb, kb)
            if hi - lo >= zc.get("min_seconds", 4.0):
                spans.append((lo, hi))
    hidden = list(full_a) + list(left_screen)
    length, gap, ease = zc.get("hold_seconds", 6.0), zc.get("gap_seconds", 3.0), zc.get("ease_seconds", 1.5)
    zooms = zc.get("zooms", [1.08, 1.06])
    centres = zc.get("centres", [[0.5, 0.45], [0.52, 0.45]])
    events, k = [], 0
    for a, b in spans:
        t = a + 0.3
        while t + zc.get("min_seconds", 4.0) <= b:
            e = min(t + length, b - 0.2)
            if not _overlaps(t, e, existing + events, "b") and not any(t < hb and e > ha for ha, hb in hidden):
                c = centres[k % len(centres)]
                events.append({"kind": "side", "start": round(t, 2), "end": round(e, 2), "zoom": zooms[k % len(zooms)],
                               "ease": min(ease, (e - t) / 2), "b": c, "why": "side angle drift"})
                k += 1
            t = e + gap
    return events


def _frame(cam, t, x0, w, h):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(cam), "-frames:v", "1",
                        "-vf", f"crop={w}:{h}:{x0}:0", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    if len(r.stdout) != w * h * 3:
        return None
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3).copy()


def _panel_box(lines, topic, w, h):
    """Bounding box (x0, y0, x1, y1) in pixels of the panel the topic is about, or None."""
    def box(ws):
        return (min(x for _, x, _, _, _ in ws), min(y for _, _, y, _, _ in ws),
                max(x + bw for _, x, _, bw, _ in ws), max(y + bh for _, _, y, _, bh in ws))
    if topic == "bulk":
        # tier row: "US $35.99 / 1 Piece+  US $34.91 / 2 Piece+ ...". OCR drops some labels, so a row counts with
        # 2+ "N Piece" labels or 3+ prices side by side ("Min. Order: 1 Piece" alone is not the discount panel)
        items = []
        for text, ws in lines:
            if not ws:
                continue
            bx = box(ws)
            if re.search(r"\d+\s*(piece|pcs?)", text, re.I):
                items.append(("piece", bx))
            elif re.search(r"us\s*\$\s*\d", text, re.I) and bx[0] > w * 0.3:
                items.append(("price", bx))
        best = None
        for kind, ref in items:
            row = [(k, x) for k, x in items if abs(x[1] - ref[1]) <= 20]
            n_p = sum(1 for k, _ in row if k == "piece")
            n_d = sum(1 for k, _ in row if k == "price")
            if (n_p >= 2 or n_d >= 3) and (best is None or len(row) > len(best)):
                best = row
        if not best:
            return None
        xs = [x for _, x in best]
        y0, y1 = min(x[1] for x in xs), max(x[3] for x in xs)
        prices_only = all(k == "price" for k, _ in best)
        # labels sit under the prices, prices above the labels: pad toward the missing half
        return (min(x[0] for x in xs) - 20, y0 - (15 if prices_only else 55), max(x[2] for x in xs) + 20,
                y1 + (50 if prices_only else 15))
    if topic == "size":
        anchors = [box(ws) for text, ws in lines if ws and re.search(r"^\s*size\s*:|size guide|size chart", text, re.I)]
        if not anchors:
            return None
        a = min(anchors, key=lambda x: x[1])
        # selector + the options under it
        return (a[0] - 10, a[1] - 10, min(w, a[0] + 720), min(h, a[1] + 380))
    return None


SIZE_LINE = re.compile(r"\b(us|uk|eu|e-?ur)\s*[\dIO]", re.I)


def _dropdown_box(lines, w, h):
    """An OPEN size dropdown: 4+ stacked lines like 'Men US 9.5=UK 8.5=Eur 43' (left-aligned within 40 px), plus the
    'Size:' label / selector right above it. Returns (x0, y0, x1, y1) or None."""
    def box(ws):
        return (min(x for _, x, _, _, _ in ws), min(y for _, _, y, _, _ in ws),
                max(x + bw for _, x, _, bw, _ in ws), max(y + bh for _, _, y, _, bh in ws))
    items = [box(ws) for text, ws in lines if ws and "$" not in text and SIZE_LINE.search(text)]
    best = []
    for ref in items:
        col = [b for b in items if abs(b[0] - ref[0]) <= 40]
        if len(col) > len(best):
            best = col
    if len(best) < 4:
        return None
    x0, y0 = min(b[0] for b in best), min(b[1] for b in best)
    x1, y1 = max(b[2] for b in best), max(b[3] for b in best)
    lab = [box(ws) for text, ws in lines if ws and re.search(r"^\s*size\s*:", text, re.I)]
    lab = [b for b in lab if 0 <= y0 - b[1] <= 160 and abs(b[0] - x0) <= 80]
    if lab:
        y0 = min(y0, lab[0][1])
    return (max(0, x0 - 20), max(0, y0 - 12), min(w, x1 + 40), min(h, y1 + 14))


def dropdown_zooms(rows, kept, cam, half_w, half_h, existing, cfg, checks):
    """Zoom + highlight wherever he OPENS the size dropdown on the store page (prada cups 2026-10-22: "when I show
    them on screen in terms of a shoe size dropdown ... zoom in and highlight that ... only when I show the
    dropdown"). Found visually (OCR every 0.6 s over kept screen footage), not from the words."""
    zc = cfg["zooms"].get("topics", {})
    try:
        import privacy_ocr
    except Exception:
        return []
    screen = [r["t"] for r in rows if r.get("left") == "screen" or r.get("right") == "screen"]
    side = {r["t"]: ("a" if r.get("left") == "screen" else "b") for r in rows}
    events = []
    for ka, kb in kept:
        ts = [t for t in screen if ka + 0.2 <= t <= kb - 0.2][::3]   # every 0.6 s (rows are 5 fps)
        cur = []
        for t in ts + [None]:
            bx = None
            if t is not None:
                key = side.get(t, "a")
                img = _frame(cam, t, 0 if key == "a" else half_w, half_w, half_h)
                bx = _dropdown_box(privacy_ocr.ocr(img), half_w, half_h) if img is not None else None
            if bx and cur and abs(bx[1] - cur[-1][1][1]) <= 30 and abs(bx[0] - cur[-1][1][0]) <= 40 and t - cur[-1][0] <= 0.7:
                cur.append((t, bx, key))
                continue
            if len(cur) >= 3 and cur[-1][0] - cur[0][0] >= 1.2:   # open and still for >= ~1.5 s
                x0 = min(b[0] for _, b, _ in cur); y0 = min(b[1] for _, b, _ in cur)
                x1 = max(b[2] for _, b, _ in cur); y1 = max(b[3] for _, b, _ in cur)
                k = cur[0][2]
                a = max(cur[0][0] - 0.2, ka)
                b = min(cur[-1][0] + 0.4, kb - 0.1, a + zc.get("dropdown_max_seconds", 8.0))
                z = min(zc.get("fill", 0.8) * half_w / max(x1 - x0, 1), zc.get("fill", 0.8) * half_h / max(y1 - y0, 1))
                z = max(zc.get("min_zoom", 1.3), min(zc.get("max_zoom", 1.8), z))
                if b - a >= 1.5 and not _overlaps(a, b, existing + events, k):
                    events.append({"kind": "topic_size", "start": round(a, 2), "end": round(b, 2), "zoom": round(z, 2),
                                   "ease": zc.get("ease_seconds", 0.6), k: [round((x0 + x1) / 2 / half_w, 3), round((y0 + y1) / 2 / half_h, 3)],
                                   "why": "size dropdown open", "box": [int(x0), int(y0), int(x1), int(y1)], "highlight": True})
            cur = [(t, bx, key)] if bx else []
    if not events:
        checks.append("Size dropdown: never seen open (and still) on the screen, so no dropdown zoom.")
    return events


def topic_zooms(words, rows, kept, cam, half_w, half_h, existing, cfg, checks):
    """Source-time zoom events onto the screen panel he's talking about. Key 'a' when the screen is on the
    left half (that half is the full picture there), 'b' when it's on the right half."""
    zc = cfg["zooms"].get("topics", {})
    if not zc.get("enabled", True) or not rows:
        return []
    try:
        import privacy_ocr
    except Exception as e:  # OCR unavailable: no topic zooms, never a failed edit
        checks.append(f"Screen topic zooms skipped (OCR unavailable: {e}).")
        return []

    def norm(s):
        return re.sub(r"[^a-z0-9']", "", s.lower())

    def where(t):
        r = min(rows, key=lambda r: abs(r["t"] - t))
        return "a" if r.get("left") == "screen" else ("b" if r.get("right") == "screen" else None)

    events, last = [], -99.0
    for i, w in enumerate(words):
        if not any(a <= w["s"] < b for a, b in kept):
            continue
        for topic, cues in zc.get("cues", {}).items():
            if topic == "size" and zc.get("size_from", "dropdown") == "dropdown":
                continue   # sizes zoom only when the dropdown is open on screen (dropdown_zooms), not on the words
            hit = next((c for c in cues if [norm(x["w"]) for x in words[i:i + len(c.split())]] == [norm(x) for x in c.split()]), None)
            if not hit:
                continue
            a = w["s"] - 0.3
            if a < last + zc.get("min_gap_seconds", 10.0):
                continue
            key = where(w["s"])
            if key is None:
                continue
            clip_a, clip_end = next((ka, kb) for ka, kb in kept if ka <= w["s"] < kb)
            # the page scrolls while he talks: sample around the cue and keep the stretch where the panel sits still
            # and fully on screen (dhgate asics 2026-10-22: the tier row scrolled off ~1 s after "bulk")
            step, top_min = 0.5, zc.get("top_margin_px", 140)
            t0, t1 = max(clip_a + 0.2, w["s"] - zc.get("look_back_seconds", 5.0)), min(clip_end - 0.2, w["s"] + 6.0)
            samples, t = [], t0
            while t <= t1:
                img = _frame(cam, t, 0 if key == "a" else half_w, half_w, half_h)
                bx = _panel_box(privacy_ocr.ocr(img), topic, half_w, half_h) if img is not None else None
                samples.append((t, bx if bx and bx[1] >= top_min and bx[3] <= half_h - 60 else None))
                t += step
            runs, cur = [], []
            for t, bx in samples:
                if bx and cur and abs(bx[1] - cur[0][1][1]) <= 25 and abs(bx[0] - cur[0][1][0]) <= 40:
                    cur.append((t, bx))
                else:
                    if len(cur) >= 2:
                        runs.append(cur)
                    cur = [(t, bx)] if bx else []
            if len(cur) >= 2:
                runs.append(cur)
            runs = [r for r in runs if r[-1][0] - r[0][0] + step >= zc.get("min_still_seconds", 2.0)]
            if not runs:
                checks.append(f"Topic zoom '{hit}' at source {w['s']:.1f} s: no still {topic} panel on the screen, no zoom.")
                continue
            cue_win = (w["s"] - 1.0, w["s"] + 4.0)
            run = max(runs, key=lambda r: (min(r[-1][0] + step, cue_win[1]) - max(r[0][0], cue_win[0]), -abs(r[0][0] - w["s"])))
            x0 = min(bx[0] for _, bx in run); y0 = min(bx[1] for _, bx in run)
            x1 = max(bx[2] for _, bx in run); y1 = max(bx[3] for _, bx in run)
            fill = zc.get("fill", 0.8)
            z = min(fill * half_w / max(x1 - x0, 1), fill * half_h / max(y1 - y0, 1))
            z = max(zc.get("min_zoom", 1.3), min(zc.get("max_zoom", 1.8), z))
            a = max(run[0][0] - 0.2, clip_a)
            b = min(run[-1][0] + step * 0.5, a + zc.get("max_hold_seconds", 6.0), clip_end - 0.1)
            if b - a < 1.5 or _overlaps(a, b, existing + events, key):
                continue
            cx, cy = (x0 + x1) / 2 / half_w, (y0 + y1) / 2 / half_h
            events.append({"kind": f"topic_{topic}", "start": round(a, 2), "end": round(b, 2), "zoom": round(z, 2),
                           "ease": zc.get("ease_seconds", 0.6), key: [round(cx, 3), round(cy, 3)], "why": hit,
                           "box": [int(x0), int(y0), int(x1), int(y1)]})
            last = b
            break
    return events + dropdown_zooms(rows, kept, cam, half_w, half_h, existing + events, cfg, checks)


SPOKEN_STOP = set("that this with have from your they them then there their what when where which will would could should "
                  "about just like going gonna really pretty much also some these those here look looking guys okay yeah "
                  "want make sure basically actually".split())


SHORT_STOP = {"the", "and", "you", "for", "are", "was", "but", "its", "can", "all", "get", "got", "one", "see", "has", "had",
              "not", "now", "how", "why", "who", "our", "out", "off", "any", "too", "way", "his", "her", "him", "she", "yes",
              "did", "let", "put", "use", "say", "two", "new", "big", "own", "lot", "per"}


def spoken_text_zooms(words, rows, kept, cam, half_w, half_h, existing, cfg, checks):
    """Zoom onto what he READS OUT on the screen (dhgate watchb spread 2026-10-24, 1:10: "a spreadsheet with the name,
    followed by the picture, then a product link and then some more information ... that could have been zoomed in on,
    because there's something there that I was just talking about, and it was on screen"). Per sentence over the screen
    recording: OCR the screen in the middle of it; when >= 3 different words of the sentence (4+ letters, not filler)
    are on screen close together, zoom onto those words for that sentence (1.5-6 s), at most one every min_gap s."""
    zc = cfg["zooms"].get("spoken", {})
    if not zc.get("enabled", True) or not rows:
        return []
    try:
        import privacy_ocr
    except Exception as e:
        checks.append(f"Spoken-text zooms skipped (OCR unavailable: {e}).")
        return []
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

    def where(t):
        r = min(rows, key=lambda r: abs(r["t"] - t))
        return "a" if r.get("left") == "screen" else ("b" if r.get("right") == "screen" else None)

    sents, cur = [], []
    for k, w in enumerate(words):
        if not any(a <= w["s"] < b for a, b in kept):
            if cur:
                sents.append(cur)
            cur = []
            continue
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        # pieces of <= 5 s: a long walkthrough sentence scrolls past several things ("...the name followed by the
        # picture, then a product link ..." is one 17 s run with no pause)
        if w["w"][-1:] in ".?!" or nxt is None or nxt["s"] - w["e"] >= 0.6 or w["e"] - cur[0]["s"] >= 5.0:
            sents.append(cur)
            cur = []
    stem = lambda t: t[:-2] if t.endswith("es") and len(t) > 5 else t[:-1] if t.endswith("s") and len(t) > 4 else t
    # the video's own subject words are on every page ("watch" in a watch spreadsheet): they never decide a zoom
    topic = {stem(norm(x)) for x in re.findall(r"[A-Za-z]+", str(cfg.get("_project_name", "")))} | set(zc.get("ignore", []))
    events, last = [], -99.0
    for s in sents:
        a, b = s[0]["s"], s[-1]["e"]
        said = {stem(norm(w["w"])) for w in s if len(norm(w["w"])) >= 4} - SPOKEN_STOP - topic
        # 3-letter words count only as the START of a longer word on screen ("buy" -> BUYING PRICE)
        short = {norm(w["w"]) for w in s if len(norm(w["w"])) == 3} - SHORT_STOP - topic
        # min_gap only stops a zoom onto the SAME spot (checked below with the box): a different part of the page right
        # after is a new thing he reads out (top 5 reselling products spring 2026-10-25, 1:46: "buy price ... sell price"
        # came 1.9 s after the NAME/PICTURE/LINK zoom and was skipped)
        if len(said) < 2 or a < last + 1.5 or b - a < 1.2:
            continue
        key = where((a + b) / 2)
        if key is None or key != where(a) or key != where(b):
            continue
        clip = next(((ka, kb) for ka, kb in kept if ka <= a < kb), None)
        if not clip or b > clip[1]:
            continue
        img = _frame(cam, (a + b) / 2, 0 if key == "a" else half_w, half_w, half_h)
        if img is None:
            continue
        occ = {}
        # light text on a dark strip (spreadsheet header row NAME / PICTURE / LINK) is invisible to the OCR as is:
        # a second pass on an inverted, thresholded copy reads it
        import cv2
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inv = cv2.threshold(g, 200, 255, cv2.THRESH_BINARY_INV)[1]
        for _, ws in privacy_ocr.ocr(img) + privacy_ocr.ocr(inv):
            for wd, x, y, bw, bh in ws:
                t = stem(norm(wd))
                # a word he says may sit INSIDE the word on screen: "sell price" over the RESELLING PRICE column header,
                # "buy" / BUYING (same note): the spoken word (4+ letters) counts when the screen word contains it
                m = t if t in said else next((x for x in said if len(x) >= 4 and len(t) > len(x) and x in t), None)                     or next((x for x in short if len(t) > len(x) and t.startswith(x)), None)
                if m and y > zc.get("top_margin_px", 120):
                    occ.setdefault(m, []).append((x, y, x + bw, y + bh))
        # every place a word sits counts, and the tightest group wins: "sell" first matched the sheet TITLE ("{{REVIEW_CHANNEL}}'s
        # RESELLING SPREADSHEET"), 280 px above the BUYING PRICE / RESELLING PRICE header, so the zoom was skipped
        hits = {}
        for k0, boxes in occ.items():
            for b0 in boxes:
                cand = {k0: b0}
                for k1, bs in occ.items():
                    if k1 != k0:
                        q = min(bs, key=lambda q: abs(q[0] - b0[0]) + 2 * abs(q[1] - b0[1]))
                        if abs(q[0] - b0[0]) <= 600 and abs(q[1] - b0[1]) <= 250:   # only words near this one
                            cand[k1] = q
                area = lambda c: (max(v[2] for v in c.values()) - min(v[0] for v in c.values())) *                     (max(v[3] for v in c.values()) - min(v[1] for v in c.values()))
                if len(cand) > len(hits) or (len(cand) == len(hits) and hits and area(cand) < area(hits)):
                    hits = cand
        if len(hits) < 2:
            continue
        bx = list(hits.values())
        x0, y0 = min(v[0] for v in bx) - 30, min(v[1] for v in bx) - 30
        x1, y1 = max(v[2] for v in bx) + 30, max(v[3] for v in bx) + 30
        row = (y1 - y0) <= zc.get("row_px", 140)            # 2+ of his words in one row: a header / a label line
        tight = len(hits) >= 3 and (x1 - x0) * (y1 - y0) <= zc.get("max_area", 0.2) * half_w * half_h
        if not (row or tight):
            continue   # the words are all over the page (common words like "watch"): nothing to zoom onto
        if row:   # show the rows under a header too (the column contents he's describing)
            y1 = min(half_h - 60, y1 + zc.get("row_below_px", 380))
        fill = zc.get("fill", 0.75)
        z = min(fill * half_w / max(x1 - x0, 1), fill * half_h / max(y1 - y0, 1))
        z = max(zc.get("min_zoom", 1.3), min(zc.get("max_zoom", 1.7), z))
        za, zb = max(a - 0.3, clip[0]), min(b + 0.4, a + zc.get("max_hold_seconds", 6.0), clip[1] - 0.1)
        if zb - za < 1.5 or _overlaps(za, zb, existing + events, key):
            continue
        if events and za < last + zc.get("min_gap_seconds", 8.0):
            pb = events[-1]["box"]   # right after another zoom: only a DIFFERENT spot (< 30 % overlap)
            inter = max(0, min(x1, pb[2]) - max(x0, pb[0])) * max(0, min(y1, pb[3]) - max(y0, pb[1]))
            if inter > 0.3 * min((x1 - x0) * (y1 - y0), (pb[2] - pb[0]) * (pb[3] - pb[1])):
                continue
        events.append({"kind": "topic_spoken", "start": round(za, 2), "end": round(zb, 2), "zoom": round(z, 2),
                       "ease": zc.get("ease_seconds", 0.6), key: [round((x0 + x1) / 2 / half_w, 3), round((y0 + y1) / 2 / half_h, 3)],
                       "why": "reads out: " + ", ".join(sorted(hits)), "box": [int(x0), int(y0), int(x1), int(y1)]})
        last = zb
    if events:
        checks.append("Spoken-text zooms (he reads out what's on screen): " +
                      "; ".join(f"{e['start']:.1f} s ({e['why'][11:60]})" for e in events) + " (source).")
    return events
