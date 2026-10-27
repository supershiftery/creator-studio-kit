"""Layout map for a phone-tutorial cut: when to show the app layout and when the side camera.
Usage: python layout.py <raw source.mp4> <work/cuts.json> <out layout.json>
  app  = phone visible (black bars beside it) and the phone changes within -1.5/+2.5 s; merge gaps < 4 s; drop runs < 3 s
  side = right half shows the 2nd camera (no black bars) and head yaw <= -18 deg (or no face) for >= 1.2 s
Head yaw uses the product-review skill's mediapipe face_landmarker model."""
import json, math, os, subprocess, sys
import numpy as np

FACE_MODEL = r"{{KIT}}/review_pipeline/models/face_landmarker.task"
PHONE = (2628, 0, 504, 1080)


def cached(name, src, compute):
    """raw-timeline analyses depend only on the recording, never on the cut list: keep them in work/layout_<name>.pkl
    keyed by the file's size + mtime, so a revision (new cuts) skips the full-video decodes (user 2026-10-22: faster revisions)"""
    import pickle
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(src))), "work", f"layout_{name}.pkl")
    sig = (os.path.getsize(src), int(os.path.getmtime(src)), name)
    try:
        with open(path, "rb") as fh:
            got = pickle.load(fh)
        if got.get("sig") == sig:
            return got["value"]
    except Exception:
        pass
    value = compute()
    try:
        with open(path, "wb") as fh:
            pickle.dump({"sig": sig, "value": value}, fh)
    except OSError:
        pass
    return value


def keep_map(K):
    def to_out(t):
        acc = 0.0
        for s, e in K:
            if s <= t < e:
                return acc + t - s
            acc += e - s
    return to_out


def phone_box(src):
    """where the phone mirror sits in THIS recording (x, 0, w, 1080): the most common bbox of pixels > 12 in the right half,
    one frame per 10 s, phone-shaped widths only. PHONE was hard-coded from the first Uber video (x 2628); on Uber codes
    october (2026-10-25) the phone sat at x 2526, so the PiP cut off the phone's left 100 px and showed a black strip."""
    def scan():
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "fps=0.1,crop=1920:1080:1920:0,scale=960:270,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        fr = np.frombuffer(raw[:len(raw) // (960 * 270) * 960 * 270], np.uint8).reshape(-1, 270, 960)
        boxes = {}
        for g in fr:
            cols = np.where((g > 12).mean(axis=0) > 0.3)[0]
            if len(cols) and 190 <= (cols.max() - cols.min() + 1) <= 320:   # 380-640 px wide = a phone, not a camera / page
                k = (int(cols.min()) * 2 + 1920, int(cols.max() - cols.min() + 1) * 2)
                boxes[k] = boxes.get(k, 0) + 1
        return max(boxes, key=boxes.get) if boxes else None
    got = cached("phonebox", src, scan)
    if not got:
        return PHONE
    x, w = got
    w = w + (w % 2)
    return (x, 0, w, 1080)


def phone_activity(src, K, crop=PHONE):
    x, y, w, h = crop
    W, H = 126, 270

    def scan():
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=4,crop={w}:{h}:{x}:{y},scale={W}:{H},format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        f_ = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
        bw = max(100, min(600, x - 1926))   # the black bar left of the phone (600 px when the phone sits at 2628)
        raw2 = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=1,crop={bw}:1080:1920:0,scale=60:108,format=gray",
                               "-f", "rawvideo", "-"], capture_output=True).stdout
        return (np.r_[0, np.abs(np.diff(f_, axis=0)).mean(axis=(1, 2))],
                np.frombuffer(raw2, np.uint8).reshape(-1, 108, 60).astype(np.float32).mean(axis=(1, 2)))
    diff, bars = cached(f"phone_{x}_{y}_{w}_{h}", src, scan)
    f = diff   # only its length is used below
    out, acc = [], 0.0
    for s, e in K:
        for t in np.arange(s, e, 0.25):
            i = int(t * 4)
            if i < len(f):
                out.append((acc + (t - s), float(diff[i]), float(bars[min(int(t), len(bars) - 1)])))
        acc += e - s
    return out, acc


def head_yaw(src, fps=3):
    return cached(f"yaw_{fps}", src, lambda: _head_yaw(src, fps))


def _head_yaw(src, fps=3):
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=FACE_MODEL),
                                        output_facial_transformation_matrixes=True, num_faces=1)
    L = vision.FaceLandmarker.create_from_options(opts)
    W, H = 640, 360   # was 640x180: a squashed face was missed on most frames, so turns never registered (Shein 0:17)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},crop=1920:1080:0:0,scale={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    rows, i = [], 0
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        img = np.ascontiguousarray(np.frombuffer(b, np.uint8).reshape(H, W, 3))
        r = L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img))
        yaw = None
        if r.face_landmarks:
            m = np.array(r.facial_transformation_matrixes[0]).reshape(4, 4)[:3, :3]
            yaw = math.degrees(math.atan2(-m[2, 0], math.sqrt(m[0, 0] ** 2 + m[1, 0] ** 2)))
        rows.append((i / fps, yaw))
        i += 1
    p.wait()
    return rows


def build(src, cuts_path, out_path):
    K = json.load(open(cuts_path))["keep"]
    to_out = keep_map(K)
    box = phone_box(src)
    # build_main crops the phone PiP from this (edit\phone_box.json)
    json.dump({"x": box[0], "y": box[1], "w": box[2], "h": box[3]},
              open(os.path.join(os.path.dirname(os.path.abspath(out_path)), "phone_box.json"), "w"))
    print(f"layout: phone mirror at x {box[0]}, {box[2]} px wide")
    act, dur = phone_activity(src, K, box)
    a = np.array(act)
    t, diff, phone = a[:, 0], a[:, 1], a[:, 2] <= 15
    cam_right = {round(x, 2): not p for x, p in zip(t, phone)}

    def right_is_cam(o):
        i = int(np.argmin(np.abs(t - o)))
        return not phone[i]
    turn = []
    for st, yaw in head_yaw(src):
        o = to_out(st)
        if o is not None:
            turn.append((o, (yaw is None or yaw <= -18) and right_is_cam(o)))
    turn.sort()
    side, cur = [], None
    for o, v in turn:
        if v and cur is None:
            cur = [o, o]
        elif v:
            cur[1] = o
        elif cur and o - cur[1] > 0.7:
            if cur[1] - cur[0] >= 1.2:
                side.append([round(cur[0] - 0.2, 2), round(cur[1] + 0.35, 2)])
            cur = None
    if cur and cur[1] - cur[0] >= 1.2:
        side.append([round(cur[0] - 0.2, 2), round(min(dur, cur[1] + 0.35), 2)])
    active = np.zeros(len(a), bool)
    for i in range(len(a)):
        w = (t > t[i] - 1.5) & (t < t[i] + 2.5)
        active[i] = phone[i] and diff[w].max() > 8
    app, cur = [], None
    for i in range(len(a)):
        if active[i] and cur is None:
            cur = [t[i], t[i]]
        elif active[i]:
            cur[1] = t[i]
        elif cur is not None and t[i] - cur[1] > 4:
            app.append(cur)
            cur = None
    if cur:
        app.append(cur)
    app = [[round(float(x), 2), round(float(y) + 0.25, 2)] for x, y in app if y - x >= 3]
    # the phone stays on from its first app moment to the last whenever it is visible (user 2026-10-21: "the phone should
    # always be on all the time when I'm talking ... until the very end", the outro drops it)
    vis = runs_of(t, phone, 4, 3)
    app = [[a, b] for a, b in vis if any(x < b and a < y for x, y in app)] or app
    outro = outro_time(cuts_path)
    if outro is not None:
        app = [[a, min(b, outro)] for a, b in app if a < outro - 2]
    lay = {"side": side, "app": app, "dur": dur, "web": [], "camr": []}
    hp = os.path.join(os.path.dirname(os.path.abspath(cuts_path)), "halves.json")
    if os.path.exists(hp):
        lay.update(screen_modes(src, K, hp))
        lay["web"] = drop_workspace(lay["web"], os.path.join(os.path.dirname(os.path.abspath(out_path)), "cut-full-noblur.mp4"),
                                    seams=[float(x) for x in np.cumsum([e - s for s, e in K])])
        outro = outro_time(cuts_path)
        if outro is not None:
            lay["web"] = [[a, min(b, outro), s] for a, b, s in lay["web"] if a < outro - 2]
        # the 2nd-camera "side" shot only exists when BOTH halves are cameras (a website half is not a side camera)
        # (TRIMMED to the both-cameras part, not dropped: the Shein opening ran 0.3 s into the website and was lost whole)
        busy = sorted([[a, b] for a, b in lay["camr"]] + [[a, b] for a, b, _ in lay["web"]])
        kept = []
        for s0, s1 in side:
            pieces = [[s0, s1]]
            for a, b in busy:
                nxt = []
                for x, y in pieces:
                    if b <= x or a >= y:
                        nxt.append([x, y])
                        continue
                    if a > x:
                        nxt.append([x, a])
                    if b < y:
                        nxt.append([b, y])
                pieces = nxt
            kept += [[round(x, 2), round(y, 2)] for x, y in pieces if y - x >= 1.2]
        lay["side"] = kept
    json.dump(lay, open(out_path, "w"), indent=1)
    print(f"layout: {len(app)} app runs ({sum(y - x for x, y in app):.0f} s), side camera {lay['side']}, "
          f"website runs {len(lay['web'])} ({sum(b - a for a, b, _ in lay['web']):.0f} s), cam on the right {sum(b - a for a, b in lay['camr']):.0f} s")


def drop_workspace(web, cut, step=2.0, seams=()):
    """website runs minus the stretches that show his own workspace tools (Notion, Google Docs ...: intro_footage.workspace).
    Uber codes october 2026-10-25: his Notion dashboard was the "website" for the first 25 s of the main video and opened
    the intro; it is not the topic, so the face cam stays full there."""
    if not web or not os.path.exists(cut):
        return web
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from intro_footage import workspace
    out = []
    for a, b, s in web:
        ts = [float(t) for t in np.arange(a + 0.5, b, step)]
        bad = [workspace(cut, s, t) for t in ts]
        if not any(bad):
            out.append([a, b, s])
            continue
        print(f"layout: website {a:.1f}-{b:.1f} s ({s}) shows a workspace page at {[round(t, 1) for t, x in zip(ts, bad) if x]}")

        def edge(t0, t1, to_good):
            """where the page changes between samples t0 and t1 (0.25 s steps), on the cut seam there if there is one
            (Uber codes october 2026-10-25, 0:47: the 2 s samples left 0.8 s of Notion before the cut to the Uber Eats page,
            a "flash of another frame")"""
            sm = next((x for x in seams if t0 < x <= t1 + 0.05), None)
            if sm is not None:
                return sm
            for u in np.arange(t0 + 0.25, t1, 0.25):
                if workspace(cut, s, float(u)) != to_good:
                    return float(u) if to_good else float(u) - 0.25
            return t1 if to_good else t0
        cur = None
        for i, (t, x) in enumerate(zip(ts, bad)):
            if not x and cur is None:
                cur = [a if i == 0 else edge(ts[i - 1], t, True), t]
            elif not x:
                cur[1] = t
            elif cur is not None:
                out.append([round(cur[0], 2), round(edge(ts[i - 1], t, False), 2), s])
                cur = None
        if cur is not None:
            out.append([round(cur[0], 2), b, s])
    return [[a, b, s] for a, b, s in out if b - a >= 2.5]


def outro_time(cuts_path):
    """cut-timeline time of the sign-off ("anyways guys, that's pretty much it"): phone and website leave the screen there."""
    wp = os.path.join(os.path.dirname(os.path.abspath(cuts_path)), "words.json")
    if not os.path.exists(wp):
        return None
    to_out = keep_map(json.load(open(cuts_path))["keep"])
    ws = [w for w in json.load(open(wp, encoding="utf-8")) if to_out(w["s"]) is not None]
    toks = [w["w"].lower().strip(".,!?") for w in ws]
    hits = [i for i in range(len(toks) - 1) if toks[i] in ("anyways", "anyway") and toks[i + 1] == "guys"]
    if not hits or to_out(ws[hits[-1]]["s"]) < 0.7 * to_out(ws[-1]["s"]):
        return None
    return round(to_out(ws[hits[-1]]["s"]) - 0.3, 2)


def runs_of(t, flags, gap, min_len, tail=0.25):
    out, cur = [], None
    for x, f in zip(t, flags):
        if f and cur is None:
            cur = [x, x]
        elif f:
            cur[1] = x
        elif cur is not None and x - cur[1] > gap:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return [[round(float(a), 2), round(float(b) + tail, 2)] for a, b in out if b - a >= min_len]


def screen_modes(src, K, halves_path):
    """Recordings where one half is a website/desktop (halves.json): which half is the face cam per moment ("camr" =
    cam on the RIGHT), and "web" runs = the website changes within -1.5/+2.5 s, so it is shown big with the face cam
    in a corner card (Shein 2026-10-21: website left + cam right for 26 min; Doordash 1:40-2:41 the same)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import halves
    hf, kl, kr = halves.load(halves_path)
    # (a full-video decode for per-half motion used to run here; nothing read its result since the website became
    # "shown the whole time that half shows it", so it was removed for speed, 2026-10-22)
    t_out, camr, web_l, web_r, acc = [], [], [], [], 0.0
    cam_side = "left"
    for s, e in K:
        for t in np.arange(s, e, 0.25):
            sec = min(int(t * hf), len(kl) - 1)
            l, r = kl[sec], kr[sec]
            cam_side = "left" if l == "cam" else ("right" if r == "cam" else cam_side)
            t_out.append(acc + t - s)
            camr.append(cam_side == "right")
            # the website stays up the WHOLE time that half shows it, not only while it changes (user 2026-10-21:
            # "the face cam is full screen but doesn't show the promo codes that were on the website"; keep it consistent)
            web_l.append(l == "screen")
            web_r.append(r == "screen")
        acc += e - s
    web = [[a, b, "left"] for a, b in runs_of(t_out, web_l, 6, 2.5)] + [[a, b, "right"] for a, b in runs_of(t_out, web_r, 6, 2.5)]
    return {"web": sorted(web), "camr": runs_of(t_out, camr, 0.5, 0.5, 0.0)}


if __name__ == "__main__":
    if sys.argv[1] == "--warm":   # pipeline.py starts this first: fills the raw-video caches while other steps run
        head_yaw(sys.argv[2])
        phone_activity(sys.argv[2], [])
        print("layout caches warm")
    else:
        build(sys.argv[1], sys.argv[2], sys.argv[3])
