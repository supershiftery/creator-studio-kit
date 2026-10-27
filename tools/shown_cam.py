"""Which camera is ON SCREEN in a finished review draft, measured from the picture (2026-10-25; study of all notes: camera
choice = ~30 notes in 13 videos, and the edit's own camera decision is not saved anywhere).

    from shown_cam import shown
    rows = shown(project, video, kept, offset)   # [(draft t, src t, "L"|"R"|"?", score)], every 0.5 s

The raw recording is the 3840x1080 side by side (two cameras, or a camera and the PC screen). Each draft frame is compared
with the LEFT and RIGHT half of the raw frame at the same recording time (gray 64x36, zero-mean correlation). Zooms and the
face circle lower the score but keep the ranking; B-roll, cards and graphics match neither half and come out "?"."""
import subprocess
from pathlib import Path

import numpy as np

FPS = 2
W, H = 64, 36


def _gray(path, w, h, fps=FPS, ss=None, t=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{ss:.3f}"] if ss else []) + ["-i", str(path)] + (["-t", f"{t:.3f}"] if t else []) + \
          ["-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def _corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def raw_video(project):
    p = Path(project) / "raw"
    for name in ("camera.mp4", "camera_original.mp4"):
        if (p / name).exists():
            return p / name
    return None


def shown(project, video, kept, offset=0.0, step=1.0 / FPS):
    from draft_audit import Map
    m = Map(kept, offset)
    raw = raw_video(project)
    dr = _gray(video, W, H)
    # only the kept pieces of the raw, each decoded from its own seek: a whole 27 min 4K decode came back short
    # (best sp5der hoodie, 16 GB) and most of it is cut anyway. Decoded ONCE (RGB 1280x360, shared with hand_sizes)
    # and shrunk here: two 4K decodes made the audit 8-12 min on the 37 min reselling recording
    pieces = {}
    for k, (a, b) in enumerate(kept):
        if a >= 0:
            rgb = raw_pieces(raw, a, b, k).astype(np.float32)
            g = rgb @ np.array([0.299, 0.587, 0.114], np.float32)               # (n, 360, 1280) gray
            pieces[k] = g.reshape(len(g), H, 10, W * 2, 10).mean(axis=(2, 4))  # 10x10 blocks -> (n, 36, 128)
    rows = []
    for i, f in enumerate(dr):
        t = i * step
        if t < offset or t >= offset + m.duration:
            continue
        k = m.piece(t)
        if kept[k][0] < 0:
            continue   # an insert (transition / cutaway)
        s = m.to_src(t)
        pr = pieces.get(k)
        j = int(round((s - kept[k][0]) * FPS))
        if pr is None or j >= len(pr):
            continue
        L, R = _corr(f, pr[j][:, :W]), _corr(f, pr[j][:, W:])
        best = max(L, R)
        lab = ("L" if L > R else "R") if best > 0.55 and abs(L - R) > 0.12 else "?"
        rows.append((round(t, 2), round(s, 2), lab, round(best, 2), k))
    return rows


SHOW_CUES = ["here's what", "here is what", "here is the", "here's the", "as you can see", "take a look", "look at this",
             "on feet", "on body", "close up", "up close", "check it out", "you can see", "this is what", "showing you",
             "show you guys"]


def _frame(path, t, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3) if len(raw) == w * h * 3 else np.zeros((h, w, 3), np.uint8)


def showing_checks(project, video, kept, offset, words, out_png, max_moments=12):
    """He SHOWS something (says "here's what it looks like", "as you can see", "on feet"...) and the draft must be on the
    camera that shows it (study 2026-10-25: jordan 3 1:53 "I'm holding the shoe up to my main camera, we need to swap to
    that one", cartier 0:54, rick owens 3:34, lv trainer 1:24; no switch happened, so camera_checks can't see it).
    One vision look for up to 12 moments: per row the draft frame | raw left camera | raw right camera."""
    from draft_audit import Map, norm
    from PIL import Image, ImageDraw
    m = Map(kept, offset)
    raw = raw_video(project)
    toks = [norm(w["w"]) for w in words]
    moments, last = [], -99.0
    for i in range(len(words)):
        for cue in SHOW_CUES:
            k = cue.split()
            if toks[i:i + len(k)] == [norm(x) for x in k] and words[i]["s"] - last > 8:
                t = words[i]["s"] + 1.2
                if offset <= t < offset + m.duration and kept[m.piece(t)][0] >= 0:
                    said = " ".join(w["w"] for w in words[max(0, i - 3):i + 9])
                    moments.append((t, m.to_src(t), said))
                    last = words[i]["s"]
                break
    moments = moments[:max_moments]
    if not moments:
        return []
    cw, ch = 320, 180
    sheet = Image.new("RGB", (cw * 3, (ch + 22) * len(moments)), "white")
    d = ImageDraw.Draw(sheet)
    for r, (t, s, said) in enumerate(moments):
        y = r * (ch + 22)
        full = _frame(raw, s, cw * 2, ch)
        for c, img in enumerate((_frame(video, t, cw, ch), full[:, :cw], full[:, cw:])):
            sheet.paste(Image.fromarray(img), (c * cw, y + 22))
        d.text((4, y + 4), f"#{r}  A = DRAFT   B = left camera   C = right camera", fill="black")
    sheet.save(out_png)
    rows = "\n".join(f"#{r} he says: \"{said}\"" for r, (t, s, said) in enumerate(moments))
    prompt = f"""A product review video. Each row of the sheet is one moment where he SHOWS something. A = what the edited
draft puts on screen; B and C = the two raw cameras at that same moment (one may be his PC screen).
{rows}
For each row: which of B / C shows best what he is showing (the product he holds up toward that camera, the shoes on his
feet, the box...)? Is A that camera (a zoom of it, or B-roll / a close-up of the same product, also counts as right)?
Wrong = A shows the other camera while B or C clearly shows the product being held up / worn toward it.
"sure" only when it is obvious. Answer only JSON: {{"rows": [{{"n": 0, "best": "B|C|either", "draft_ok": true, "sure": true, "why": "<max 15 words>"}}]}}"""
    try:
        from claude_brain import ask
        ans = ask("camera_check", prompt, images=[out_png], say=lambda *a: None) or {}
    except Exception:  # noqa
        return []
    flags = []
    for r in ans.get("rows") or []:
        try:
            n = int(r["n"])
        except Exception:  # noqa
            continue
        if n < len(moments) and not r.get("draft_ok", True) and r.get("best") in ("B", "C"):
            t, s, said = moments[n]
            # listen only (tested 2026-10-25): missed jordan 3 1:53 (no cue words there) and flagged approved prada 1:16
            # ("show you these on my face" = face cam is right) and cologne 4:16 (outro talk)
            flags.append({"kind": "listen", "draft": [round(t, 2)], "src": [round(s, 2)],
                          "phrase": said[:120], "why": f"he shows it to the {'left' if r['best'] == 'B' else 'right'} camera "
                                                      f"but the draft is on the other one: {str(r.get('why', ''))[:80]}"})
    return flags


# a problem: clean on all 8 approved finals (after the frame-edge fix), fires on jordan 3 1:47-2:08 when the camera is
# swapped to the wrong one (2026-10-25). The real no-switch drafts (cartier, rick owens, jordan) were never saved.
HOLD_KIND = "camera"


_PIECES = {}


def raw_pieces(raw, a, b, k):
    """one kept piece of the raw at 2 fps, RGB 1280x360, decoded once per audit (camera check + hand check share it)"""
    key = (str(raw), round(a, 3), round(b, 3))
    if key not in _PIECES:
        _PIECES[key] = _rgb_piece(raw, a, b, 1280, 360)
    return _PIECES[key]


def _rgb_piece(path, a, b, w, h, fps=FPS):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-i", str(path), "-t", f"{b - a + 0.6:.3f}", "-vf",
                          f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[:n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def hand_sizes(project, kept):
    """{(piece, frame index): (left, right)} = size of the biggest RAISED hand on each raw camera (MediaPipe, 2 fps)"""
    sys_path = r"{{KIT}}/review_pipeline\scripts"
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    import showing
    mp, lmk = showing._hands()
    if lmk is None:
        return {}
    raw, out = raw_video(project), {}
    for k, (a, b) in enumerate(kept):
        if a < 0:
            continue
        frames = raw_pieces(raw, a, b, k)
        _PIECES.pop((str(raw), round(a, 3), round(b, 3)), None)   # last user of the piece: free it (~1.4 MB a frame)
        for j, fr in enumerate(frames):
            sizes = []
            for half in (fr[:, :640], fr[:, 640:]):
                res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(half)))
                big = 0.0
                for lm in res.hand_landmarks:
                    ys, xs = [p.y for p in lm], [p.x for p in lm]
                    cx = (max(xs) + min(xs)) / 2
                    # raised into the upper half (as showing.py) and not at the frame edge: approved s25 2:58 = his
                    # clasped hands at the right edge of the desk camera while he talks to the front camera
                    if min(ys) < 0.55 and 0.15 <= cx <= 0.85:
                        big = max(big, (max(ys) - min(ys)) * (max(xs) - min(xs)))
                sizes.append(big)
            out[(k, j)] = tuple(sizes)
    return out


def hold_checks(rows, hands, kinds=None, kept=None, min_s=3.0, held=0.03, mean_held=0.05, none=0.01):
    """He holds the product up to the camera that is NOT on screen and the edit never switches (study 2026-10-25: jordan 3
    1:53 "I'm holding the shoe up to my main camera, we need to swap to that one", cartier 0:54, rick owens 3:34, lv
    trainer 1:24). A big raised hand (MediaPipe box area >= 0.05 of the frame, held for >= 3 s) on the other camera while
    the camera on screen shows no raised hand at all. Screens never count."""
    flags, run = [], []

    def close():
        # jordan 3 1:47-2:08 (shoe held up): 0.03-0.11 with dips, so a run continues above 0.03 and must AVERAGE 0.05
        if run and run[-1][0] - run[0][0] + 0.5 >= min_s and sum(x[3] for x in run) / len(run) >= mean_held:
            t, s, lab, _ = run[0]
            flags.append({"kind": HOLD_KIND, "draft": [round(t, 2)], "src": [round(s, 2)],
                          "why": f"he holds something up to the {'right' if lab == 'L' else 'left'} camera for "
                                 f"{run[-1][0] - t + 0.5:.0f} s but the draft stays on the other one: switch to it"})
        run.clear()
    for t, s, lab, sc, k in rows:
        j = int(round((s - kept[k][0]) * FPS)) if kept else None
        hs = hands.get((k, j))
        other = "R" if lab == "L" else "L"
        ok = lab in ("L", "R") and hs is not None and (not kinds or kinds(s, other) not in ("screen", "desktop", "pc"))
        if ok:
            on, off = (hs[0], hs[1]) if lab == "L" else (hs[1], hs[0])
            if off >= held and on <= none:
                if run and t - run[-1][0] > 1.01:
                    close()
                run.append((t, s, lab, off))
                continue
        close()
    close()
    return flags


def half_kinds(project):
    """recording time -> what each half shows ("cam" / "product" / "screen"...), from the edit's own analysis.json"""
    import json
    f = Path(project) / "work" / "analysis.json"
    if not f.exists():
        return None
    a = json.loads(f.read_text(encoding="utf-8"))
    ts = np.array([r["t"] for r in a])

    def at(s, side):
        r = a[int(np.clip(np.searchsorted(ts, s), 0, len(a) - 1))]
        return r.get("left" if side == "L" else "right")
    return at


def facing(project, front=12.0, turned=22.0):
    """recording time -> the camera he FACES, from the edit's own analysis.json (head yaw on camera A at 5 fps, face found on
    the right half): "L" = looking into camera A (|yaw| <= 12), "R" = turned well away from A (|yaw| >= 22) while the right
    half is the side camera and sees his face, None = anything else (screen, product cam, no face, looking down)"""
    import json
    f = Path(project) / "work" / "analysis.json"
    if not f.exists():
        return None
    a = json.loads(f.read_text(encoding="utf-8"))
    ts = np.array([r["t"] for r in a])

    def at(s):
        r = a[int(np.clip(np.searchsorted(ts, s), 0, len(a) - 1))]
        yaw = r.get("yaw")
        if yaw is None or r.get("left") != "cam":
            return None
        if abs(yaw) <= front:
            return "L"
        if abs(yaw) >= turned and r.get("rfx") is not None and r.get("right") == "side":
            return "R"
        return None
    return at


def facing_checks(rows, face_at, kinds=None, min_s=3.0, share=0.8, offset=0.0, duration=None, talk_s=60.0):
    """He turns to one camera and the draft stays on the other (reselling spring 2026-10-25, round 3: "around 0:20 / 0:41 I
    start on the side angle and turn to the main camera, and at 0:45 I turn to the side camera again. The edit should
    follow the camera I'm facing"). Only the two cameras that film HIM count: camera A and the right half as the side
    angle; the desk/product camera and the screen never do (showing the product there is normal)."""
    if not face_at:
        return []
    flags, run = [], []

    def close():
        known = [x for x in run if x[3] is not None]
        bad = [x for x in known if x[3] != x[2]]
        if bad and bad[-1][0] - bad[0][0] + 0.5 >= min_s and len(bad) >= share * len(known):
            t, s, lab, want = bad[0][:4]
            # a problem in the TALKING parts (first / last 60 s of the main edit: greeting, outro; spring draft 0:30.5 = main
            # 0:08 on the side camera while he talks into camera A, and the 12:18 outro note) and whenever camera A stays on
            # while he talks into the side camera. Showing the side angle while he talks into camera A in the middle is
            # listen only: approved prada glasses 1:18-1:47 (and spring 8:33) hold it ON PURPOSE to show the sunglasses on
            # his face (the "clean side-angle segment" he asked for in spring 9:32). Section bounds can't tell: they are a
            # fallback guess that put the spring greeting inside "review".
            main = t - offset
            talking = main < talk_s or (duration is not None and main > duration - talk_s)
            flags.append({"kind": "camera" if want == "R" or talking else "listen", "draft": [round(t, 2)], "src": [round(s, 2)],
                          "why": f"he talks into the {'right' if want == 'R' else 'left'} camera for "
                                 f"{bad[-1][0] - t + 0.5:.0f} s but the draft shows the "
                                 f"{'left' if lab == 'L' else 'right'} camera: follow the camera he looks into"})
        run.clear()
    for t, s, lab, sc, k in rows:
        side = lab == "R" and (not kinds or kinds(s, "R") == "side")
        front = lab == "L" and (not kinds or kinds(s, "L") == "cam")
        if not (side or front) or (run and (k != run[-1][4] or t - run[-1][0] > 1.01)):
            close()
            if not (side or front):
                continue
        want = face_at(s)
        if want is not None and want == lab and run and all(x[3] in (None, x[2]) for x in run[-2:]):
            close()      # back on the right camera for 1 s+: the stretch is over
        run.append((t, s, lab, want, k))
    close()
    return flags


def camera_checks(rows, kinds=None, flash_s=1.5, pingpong_s=25.0, min_flash=1.0):
    """Rules from his notes (study 2026-10-25), on the measured on-screen camera:
    flash      a camera on screen for < 1.5 s between other shots (bapesta 2:31: switched to the other camera right before
               the PC part, "only on the screen for a couple of seconds")
    pingpong   2+ switches between the two CAMERAS inside one continuous take within 25 s (sp5der 5:59 / 6:08 / 6:22:
               "we don't want to keep swapping between the 2 cameras")
    Switches to and from the PC screen are normal and never count."""
    # runs of one label; "?" (B-roll, cards) is skipped over
    runs = []
    for t, s, lab, sc, k in rows:
        if lab == "?":
            continue
        kind = kinds(s, lab) if kinds else "cam"
        if runs and runs[-1]["lab"] == lab and runs[-1]["k"] == k and t - runs[-1]["e"] <= 2.0:
            runs[-1]["e"] = t + 0.5
        else:
            runs.append({"lab": lab, "kind": kind, "s": t, "e": t + 0.5, "k": k, "src": s})
    camish = lambda r: r["kind"] not in ("screen", "desktop", "pc")
    flags = []
    for i, r in enumerate(runs):
        prev, nxt = (runs[i - 1] if i else None), (runs[i + 1] if i + 1 < len(runs) else None)
        # one 0.5 s sample is timing noise at a cut (approved finals: cologne, s25, jordan 3 all had one), so >= 1 s
        # a real flash pops in and back out (A-B-A, all cameras, one take); a screen -> face cam change with a punch-in
        # zoom read as 1 s of the other camera on the approved watchb final (4:46)
        if min_flash <= r["e"] - r["s"] < flash_s and prev and nxt and prev["lab"] == nxt["lab"] != r["lab"] \
                and prev["k"] == r["k"] == nxt["k"] and all(camish(x) for x in (prev, r, nxt)):
            flags.append({"kind": "camera", "draft": [round(r["s"], 2)], "src": [round(r["src"], 2)],
                          "why": f"camera flash: the other camera shows for only {r['e'] - r['s']:.1f} s"
                                 + (" right before a cut" if not nxt or nxt["k"] != r["k"] else "")})
    for i in range(len(runs) - 2):
        a, b, c = runs[i:i + 3]
        # the middle stretch must be on the NON-talking camera: front cam -> other cam -> front cam (sp5der 6:06, 14 s in a
        # try-on). The reverse (desk cam -> front cam while he holds the product up -> desk cam) is what he asks for:
        # approved prada glasses 1:16, cologne 1:29, lv skatesta 1:52
        if a["k"] == b["k"] == c["k"] and a["lab"] == c["lab"] != b["lab"] and all(camish(x) for x in (a, b, c)) \
                and c["s"] - a["e"] <= pingpong_s and b["e"] - b["s"] >= flash_s \
                and a["kind"] == c["kind"] == "cam" and b["kind"] != "cam":
            flags.append({"kind": "camera", "draft": [round(b["s"], 2)], "src": [round(b["src"], 2)],
                          "why": f"cameras switch back and forth in one take ({b['e'] - b['s']:.0f} s on the other camera, "
                                 f"then back): pick one camera for the stretch"})
    return flags
