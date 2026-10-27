"""Nothing happens on the desk camera while he talks (s25 ultra 2026-10-23, 4:00-4:28: "should have been a full facecam
video. There is nothing going on or being unboxed on the desk cam ... we need to add that as a talking video right there.
So no side facecam, just full cam on the main one"). The review layout puts the product camera full frame with his face in
the circle; while he only TALKS (the RAM / replica opinion), that shows an idle desk and a resting arm for half a minute.

    find_idle(project, cam, rows, kept, sections, left_screen, checks) -> [(s, e), ...] source seconds: Camera A full frame

1. Candidates: kept review/showcase stretches >= MIN_S on the product-camera layout (right half = product, not a screen on
   either half) with his face on Camera A most of the time (he talks to it).
2. Split into windows of ~WIN_S (and a window must barely move: median frame difference <= MOTION_MAX); three frames of the desk camera per window go on one contact sheet (12 windows per look) and
   the pipeline brain answers per window: is anything being HANDLED or SHOWN (hands on the product, the phone held up,
   unboxing), or is it an idle desk (an arm resting or gesturing at the edge, a product just lying there)?
   Raw motion can't tell: on s25 the idle desk scored like him scrolling the phone (camera noise, a gesturing arm).
3. Idle windows next to each other merge; runs >= MIN_S become Camera A full frame, no circle. Cached in work/idle_desk.json
   (delete to redo), listed in Check these. raw/config.json "idle_desk": {"enabled": false} turns it off.
"""
import json
import sys
import tempfile
from pathlib import Path

MIN_S = 6.0
WIN_S = 6.0
MIN_RUN = 12.0     # a switch to the talking camera holds at least this long (one 6 s idle window is not a talk)
MOTION_MAX = 4.0   # median frame difference (2 fps, 96x54 grey) of an idle desk: s25 idle 1.5-2.9, handling a cable 8.5


def _motion(cam, a, b):
    """Median mean-abs frame difference of the desk camera (right half) over [a, b]."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", str(cam), "-an", "-vf",
                          "fps=2,crop=iw/2:ih:iw/2:0,scale=96:54,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8)
    f = f[: len(f) // (96 * 54) * 96 * 54].reshape(-1, 54, 96).astype(np.float32)
    return float(np.median(np.abs(np.diff(f, axis=0)).mean(axis=(1, 2)))) if len(f) > 2 else 99.0


def _spans(rows, kept, sections, left_screen):
    secs = [(x["start"], x["end"]) for x in sections if x["name"] in ("review", "showcase")]
    good = []
    for r in rows:
        t = r["t"]
        ok = (r.get("right") == "product" and r.get("left") != "screen" and not any(a <= t <= b for a, b in left_screen)
              and any(a <= t <= b for a, b in kept) and any(a <= t <= b for a, b in secs))
        good.append((t, ok, r.get("fx") is not None))
    spans, cur = [], None
    for t, ok, face in good:
        if ok:
            if cur and t - cur[1] <= 1.0:
                cur[1] = t
                cur[2] += 1
                cur[3] += face
            else:
                if cur:
                    spans.append(cur)
                cur = [t, t, 1, int(face)]
        elif cur and t - cur[1] > 1.0:
            spans.append(cur)
            cur = None
    if cur:
        spans.append(cur)
    # split at cuts too: one kept piece at a time
    out = []
    for a, b, n, nf in spans:
        if nf / max(n, 1) < 0.7:
            continue
        for x, y in kept:
            s, e = max(a, x), min(b, y)
            if e - s >= MIN_S:
                out.append((s, e))
    return out


def _carry(ranges, kept, rows, left_screen, max_cut=0.5):
    """an idle run stops at its kept piece, but a piece too short to be looked at (< MIN_S) right after it, behind a
    sliver of a cut, is the same talk (lv skatesta 5:32, "the camera should not have switched back to the bottom camera
    because I'm still talking to the audience": idle to 629.78, a 0.09 s cut, then 4.3 s of the same still shoe on the desk
    camera). It goes with the run when every row there is the same picture: product cam, his face on Camera A."""
    out = []
    for a, b in ranges:
        for x, y in sorted(kept):
            if b - 0.05 <= x <= b + max_cut and y - x < MIN_S:
                rs = [r for r in rows if x <= r["t"] <= y]
                if rs and all(r.get("right") == "product" and r.get("fx") is not None and r.get("left") != "screen"
                              and not any(p <= r["t"] <= q for p, q in left_screen) for r in rs):
                    b = y
        out.append((a, b))
    return out


def find_idle(project, cam, rows, kept, sections, left_screen, cfg, checks):
    ic = cfg.get("idle_desk", {})
    if not ic.get("enabled", True) or not rows:
        return []
    work = project / "work"
    cache = work / "idle_desk.json"
    spans = _spans(rows, kept, sections, left_screen)
    key = [[round(a, 2), round(b, 2)] for a, b in spans]
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("spans") == key:
            if d.get("ranges"):
                checks.append("Idle desk camera while he talks (cached vision check): Camera A full frame, no circle at "
                              + ", ".join(f"{a // 60:.0f}:{a % 60:04.1f}-{b // 60:.0f}:{b % 60:04.1f}" for a, b in d["ranges"]) + " (source).")
            return _carry([tuple(r) for r in d.get("ranges", [])], kept, rows, left_screen)
    wins, span_of = [], []
    for si, (a, b) in enumerate(spans):
        n = max(1, round((b - a) / WIN_S))
        step = (b - a) / n
        wins += [(a + k * step, a + (k + 1) * step) for k in range(n)]
        span_of += [si] * n
    verdict = _look(cam, wins, checks) if wins else {}
    # both: the eyes say nothing is handled AND the desk camera barely moves (the eyes called him handling the charging
    # cable "idle"; the motion there was 3x an idle desk)
    motion = {k: round(_motion(cam, a, b), 2) for k, (a, b) in enumerate(wins) if verdict.get(k) is True}
    mx = cfg.get("idle_desk", {}).get("motion_max", MOTION_MAX)
    flag = [verdict.get(k) is True and motion.get(k, 99) <= mx for k in range(len(wins))]
    # a gesture or two inside an idle talk (the eyes still say idle, only the motion is up) doesn't flip back to the desk
    # camera for 11 s: up to 2 such windows between idle ones, inside the same kept stretch, count as idle
    for k in range(1, len(wins) - 1):
        if flag[k] or verdict.get(k) is not True:
            continue
        for g in (1, 2):
            if k + g - 1 < len(wins) - 1 and all(verdict.get(k + i) is True for i in range(g)) and flag[k - 1] and flag[k + g]                     and wins[k + g][0] - wins[k - 1][1] <= g * WIN_S * 1.5:
                for i in range(g):
                    flag[k + i] = True
                break
    # the eyes flip on single windows between runs (s25: the same 4:00-4:28 talk came back 7/7, then 5/7 idle): a kept
    # stretch where >= 60 % of the windows look idle and the desk camera barely moves overall is idle as a whole
    for si in range(len(spans)):
        ks = [k for k in range(len(wins)) if span_of[k] == si]
        if sum(verdict.get(k) is True for k in ks) / len(ks) >= 0.6:
            for k in ks:
                if k not in motion:
                    motion[k] = round(_motion(cam, *wins[k]), 2)
            ms = sorted(motion[k] for k in ks)
            if ms[len(ms) // 2] <= mx:
                for k in ks:
                    flag[k] = True
    idle = [w for k, w in enumerate(wins) if flag[k]]
    merged = []
    for a, b in idle:
        if merged and a - merged[-1][1] <= 0.05:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    ranges = [(round(a, 2), round(b, 2)) for a, b in merged if b - a >= cfg.get("idle_desk", {}).get("min_run_seconds", MIN_RUN)]
    complete = len(verdict) == len(wins)
    (cache if complete else work / "idle_desk.partial.json").write_text(json.dumps({"spans": key, "windows": [[round(a, 2), round(b, 2)] for a, b in wins],
                                 "idle": {str(k): v for k, v in verdict.items()},
                                 "motion": {str(k): v for k, v in motion.items()}, "ranges": ranges}, indent=1), encoding="utf-8")
    ranges = _carry(ranges, kept, rows, left_screen)
    if ranges:
        checks.append("Idle desk camera while he talks (vision check): Camera A full frame, no circle at "
                      + ", ".join(f"{a // 60:.0f}:{a % 60:04.1f}-{b // 60:.0f}:{b % 60:04.1f}" for a, b in ranges)
                      + f" (source; {len(wins)} windows looked at). Delete work/idle_desk.json to redo.")
    return ranges


def _look(cam, wins, checks, per_sheet=12):
    sys.path.insert(0, r"{{KIT}}/tools")
    try:
        import claude_brain
    except Exception as e:
        checks.append(f"Idle-desk check skipped ({type(e).__name__}).")
        return {}
    out = {}
    tmp = Path(tempfile.mkdtemp(prefix="idle_"))
    for s0 in range(0, len(wins), per_sheet):
        group = wins[s0:s0 + per_sheet]
        items = []
        for n, (a, b) in enumerate(group):
            for j, f in enumerate((0.15, 0.5, 0.85)):
                items.append((str(cam), a + (b - a) * f, f"{n + 1}{'abc'[j]}", "crop=iw/2:ih:iw/2:0"))
        sheet = tmp / f"sheet{s0}.png"
        claude_brain.contact_sheet(items, str(sheet), cols=6, w=320)
        prompt = ("The attached image is a grid of frames from the DESK camera of a product review (a camera looking down at "
                  "a desk). Frames 1a/1b/1c are three moments of window 1, 2a/2b/2c of window 2, and so on. For EACH window "
                  "number answer true if NOTHING is being handled or shown in that window: an idle desk, only an arm or hand "
                  "resting or gesturing at the edge, a product just lying there untouched. Answer false if hands are holding, "
                  "using, opening or showing a product or its box, or the phone screen is being used. Answer with ONLY JSON "
                  "like {\"1\": true, \"2\": false}.")
        j = None
        for attempt in range(3):   # the eyes/brain fail now and then (s25 round 2: no usable JSON on the 4:00-4:28 batch)
            try:
                j = claude_brain.ask("idle_desk_check", prompt + (" Reply with the JSON object only." if attempt else ""),
                                     images=[str(sheet)])
            except Exception:
                j = None
            if isinstance(j, dict):
                break
        if not isinstance(j, dict):
            checks.append("Idle-desk check: no answer for some windows; they keep the desk camera.")
            continue
        for n in range(len(group)):
            v = j.get(str(n + 1))
            out[s0 + n] = v is True or str(v).lower() == "true"
    return out
