"""Zoom in on what he talks about, for screen-recording edits (settings.zooms, user 2026-10-23 Chime: "we can zoom in on
things that he's talking about"). Small browser text on a 1080p capture is hard to read; a slow punch-in on the spot he
points at fixes that.

    plan(words, keep, speed, out_len, work, src, avoid=()) -> [{"s", "e", "cx", "cy", "z"}] in EDIT time, 1920x1080 coords

- WHEN: Claude (claude_brain) reads the kept transcript and picks the lines where he refers to something on
  the screen ("click Get SpotMe", "right here", "this page", a price or a button), at most one every ~20 s.
- WHERE: his mouse cursor in those seconds (a small isolated change between frames; scrolls and page loads are big changes
  and are ignored), so the zoom lands where he points. No cursor found = no zoom (a phone mirror has no cursor).
- Never during a privacy blur (`avoid`, edit-time ranges): the blur boxes are placed in unzoomed frame coordinates.
Cached in work/screen_zooms.json by transcript + cut."""
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, r"{{KIT}}/tools")
import claude_brain as B   # noqa: E402
import screen_music as SM   # noqa: E402

ZOOM = 1.55
RAMP = 0.6


def to_raw(t, keep, speed):
    t *= speed
    for s, e in keep:
        if t <= e - s:
            return s + t
        t -= e - s
    return keep[-1][1]


def cursor(src, a, b, cam_box=None):
    """last cursor position (1920x1080) in raw [a, b], or None"""
    import cv2
    W, H, fps = 960, 540, 6
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, a):.3f}", "-t", f"{b - a:.3f}", "-i", src, "-vf",
                        f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(p) // (W * H)
    fr = np.frombuffer(p[:n * W * H], np.uint8).reshape(n, H, W).astype(np.int16)
    found = None
    for k in range(1, n):
        d = (np.abs(fr[k] - fr[k - 1]) > 28).astype(np.uint8)
        if d.mean() > 0.02:          # a scroll or page load, not a cursor
            continue
        cnt, lab, st, cen = cv2.connectedComponentsWithStats(d, 8)
        for c in range(1, cnt):
            x, y, w, h, area = st[c]
            if 6 <= area <= 260 and w <= 26 and h <= 30:
                if cam_box and cam_box[0] <= x * 2 <= cam_box[2] and cam_box[1] <= y * 2 <= cam_box[3]:
                    continue
                # a cursor moves over a STILL page; camera footage (a face cam, his hands) changes all around the blob
                # (Chime 2026-10-23: the second recording's full-height cam gave "cursors" on his hands)
                x0, y0, x1, y1 = max(0, x - 40), max(0, y - 40), min(W, x + w + 40), min(H, y + h + 40)
                soft = np.abs(fr[k][y0:y1, x0:x1] - fr[k - 1][y0:y1, x0:x1]) > 6   # sensor noise / motion, not just the blob
                if int(soft.sum()) - int(area) * 3 > 60:
                    continue
                found = (float(cen[c][0] * 2), float(cen[c][1] * 2))
    return found


def plan(words, keep, speed, out_len, work, src, avoid=(), cam_box=(1255, 0, 1920, 375), say=print):
    W = SM.edit_words(words, keep, speed)
    L = SM.sentences(W)
    if not L:
        return []
    cache = os.path.join(work, "screen_zooms.json")
    key = hashlib.md5(json.dumps([[round(x["s"], 1), x["text"]] for x in L] + [keep]).encode()).hexdigest()
    if os.path.exists(cache):
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            return c["zooms"]
    text = "\n".join(f"L{i} [{x['s'] // 60:.0f}:{x['s'] % 60:04.1f}-{x['e'] // 60:.0f}:{x['e'] % 60:04.1f}] {x['text']}" for i, x in enumerate(L))
    prompt = f"""A {out_len / 60:.1f}-minute screen-recording tutorial: the creator talks over his browser / phone screen.
Pick the lines where a slow ZOOM onto the screen helps the viewer: he points at or names something visible right then
(a button he clicks, "right here", "this page", a price, a requirement on the page, a form field, a step to follow).
Not his intro talk to the camera, not general opinions, not sponsor chatter without anything shown. At most one zoom
every 20 seconds; 8-18 in total for a video this long.

TRANSCRIPT (line, time in the edit, words)
{text}

Reply with ONLY JSON: {{"zooms":[{{"line":12,"what":"<the thing on screen, 2-5 words>"}}, ...]}}"""
    ans = B.ask("screen_zooms", prompt, model="sonnet", say=say)
    picks = []
    for d in (ans or {}).get("zooms") or []:
        try:
            i = int(str(d.get("line")).lstrip("L"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(L):
            picks.append((i, str(d.get("what") or "")[:40]))
    zooms, last_end = [], -99.0
    for i, what in sorted(picks):
        s, e = L[i]["s"], L[i]["e"]
        e = min(max(e, s + 2.5), s + 7.0, out_len - 1.0)
        if s - last_end < 8 or any(a - 1.5 < e and s < b + 1.5 for a, b in avoid):
            continue
        ra, rb = to_raw(s - 1.5, keep, speed), to_raw(min(e, s + 3.0), keep, speed)
        if rb <= ra:
            continue
        pos = cursor(src, ra, rb, cam_box)
        if not pos:
            say(f"  zoom L{i} '{what}': no cursor, skipped")
            continue
        cx, cy = pos
        if cam_box:
            # the zoomed frame never slices the corner face cam (Chime 2026-10-23, 1:53: half his cam hung at the top):
            # slide the window clear of it, left or down, whichever moves it less while keeping the cursor inside
            ww, wh = 1920 / ZOOM, 1080 / ZOOM
            x0, y0 = min(max(cx - ww / 2, 0), 1920 - ww), min(max(cy - wh / 2, 0), 1080 - wh)
            if x0 + ww > cam_box[0] and y0 < cam_box[3]:
                opts = []
                nx = cam_box[0] - ww
                if nx >= 0 and pos[0] <= cam_box[0] - 20:
                    opts.append((x0 - nx, nx, y0))
                ny = min(cam_box[3], 1080 - wh)
                if pos[1] >= ny + 20:
                    opts.append((ny - y0, x0, ny))
                if opts:
                    _, x0, y0 = min(opts)
                cx, cy = x0 + ww / 2, y0 + wh / 2
        zooms.append({"s": round(s, 2), "e": round(e, 2), "cx": round(cx), "cy": round(cy), "z": ZOOM, "what": what})
        last_end = e
    json.dump({"key": key, "zooms": zooms}, open(cache, "w", encoding="utf-8"), indent=1)
    say(f"zooms: {len(zooms)} of {len(picks)} picked lines (" + ", ".join(f"{z['s'] // 60:.0f}:{z['s'] % 60:02.0f} {z['what']}" for z in zooms) + ")")
    return zooms


def filter_expr(zooms, fps, W=1920, H=1080):
    """zoompan expressions: zoom eases in over RAMP s, holds, eases out; x/y keep the cursor spot centred (clamped)"""
    if not zooms:
        return None
    ss = lambda a, b: f"((it-{a:.3f})/{b - a:.3f})"   # noqa: E731
    parts = []
    for z in zooms:
        a, b = z["s"], z["e"]
        up = f"clip({ss(a, a + RAMP)},0,1)"
        down = f"clip({ss(b - RAMP, b)},0,1)"
        k = f"(({up})*({up})*(3-2*({up})))*(1-(({down})*({down})*(3-2*({down}))))"
        parts.append(f"if(between(it,{a:.3f},{b:.3f}),{z['z'] - 1:.3f}*{k},0)")
    zexpr = "1+" + "+".join(parts)
    cx = "+".join(f"if(between(it,{z['s']:.3f},{z['e']:.3f}),{z['cx']},0)" for z in zooms)
    cy = "+".join(f"if(between(it,{z['s']:.3f},{z['e']:.3f}),{z['cy']},0)" for z in zooms)
    x = f"clip(({cx})-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(({cy})-ih/zoom/2,0,ih-ih/zoom)"
    return f"zoompan=z='{zexpr}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps:g}"
