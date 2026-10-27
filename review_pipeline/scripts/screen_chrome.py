"""Is the LEFT half a screen capture? Two checks the picture analysis (analyze.py lflat) misses:

1. chrome_rows: a desktop page full of photos (a Zillow listing, a store gallery) is not flat, so lflat < 0.52 read it as
   Camera A ("How I make $30k a month reselling" 2026-10-26, 8:34-8:56: the outro showed the Zillow page full screen and
   the fourplex listing had no face circle, "it forgot the transition back"). A screen capture has a browser / window
   bar along its top: the top 40 px are flat (>= 0.6 of pixels within 4 levels of the median) AND high-contrast (column
   std >= 25: tabs, text). A camera frame of the room measured 0.09 / 14-19, the desktop 0.77-0.79 / 33-35. Read at the
   key frames only (fast), cached in work/chrome.json. Only ever turns "cam" without his face into "screen".
2. idle_screens: a blank browser NEW TAB is never what he shows ($30k 7:56-8:20: "I'm on just a blank Firefox page, but
   that's not really what I was trying to showcase"). Windows OCR on a frame every ~4 s of each desktop run; a run that
   reads as a new-tab page goes to his face camera instead.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

# the new-tab page's own search box text only: a TAB TITLE "New Tab" or Firefox's "Import bookmarks" button can sit on any page
NEWTAB_RE = re.compile(r"search with google or enter address|search google or type a url|search or enter (web )?address", re.I)


def chrome_samples(cam, work, hw, hh):
    cache = Path(work) / "chrome.json"
    try:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("src") == str(cam) and d.get("mtime") == int(os.path.getmtime(cam)) and d.get("samples"):
            return d["samples"]
    except (OSError, ValueError, KeyError):
        pass
    ts = subprocess.run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0", "-show_entries",
                         "frame=pts_time", "-of", "csv=p=0", str(cam)], capture_output=True, text=True).stdout.split()
    r = subprocess.run(["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", str(cam), "-vf", f"crop={hw}:40:0:0,format=gray",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True)
    fr = np.frombuffer(r.stdout, np.uint8)
    n = len(fr) // (hw * 40)
    fr = fr[:n * hw * 40].reshape(n, 40, hw).astype(np.float32)
    out = []
    for t, f in zip(ts, fr):
        try:
            t = float(t.strip(","))
        except ValueError:
            continue
        out.append([round(t, 2), round(float((np.abs(f - np.median(f)) <= 4).mean()), 3), round(float(f.std(axis=0).mean()), 1)])
    if out:   # never cache an empty read (an ffmpeg option error read 0 frames and stuck: $30k 2026-10-26)
        cache.write_text(json.dumps({"src": str(cam), "mtime": int(os.path.getmtime(cam)), "samples": out}), encoding="utf-8")
    return out


def chrome_rows(rows, cam, work, hw, hh, checks, flat_min=0.6, std_min=25.0):
    """rows with left == "cam" and no face on Camera A, where the left top strip is window chrome -> left = "screen"."""
    if not rows or "left" not in rows[0]:
        return rows
    try:
        smp = chrome_samples(cam, work, hw, hh)
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Window-bar check failed ({type(e).__name__}: {str(e)[:100]}).")
        return rows
    if not smp:
        return rows
    ts = np.array([s[0] for s in smp])
    out, n = [], 0
    for r in rows:
        if r.get("left") == "cam" and r.get("fx") is None:
            i = int(np.argmin(np.abs(ts - r["t"])))
            if abs(ts[i] - r["t"]) <= 2.5 and smp[i][1] >= flat_min and smp[i][2] >= std_min:
                r = dict(r, left="screen")
                n += 1
        out.append(r)
    if n:
        checks.append(f"Desktop pages full of photos (a browser bar on top, no face) read as the screen, not Camera A: {n} rows.")
    return out


def idle_screens(cam, runs, hw, hh, checks, every=4.0):
    """(start, end) source ranges inside the desktop runs that show a blank new-tab page. The OCR runs in its OWN process:
    Windows OCR (winrt) loaded into the build process made the later CUDA Whisper load crash with an access violation
    (rule gate 2026-10-26: every approved video's --cuts-only replay died silently, exit 0xC0000005)."""
    if not runs:
        return []
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.abspath(__file__), "--idle", str(cam), str(hw), str(hh),
                        json.dumps([list(x) for x in runs]), str(every)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    try:
        return [tuple(x) for x in json.loads(r.stdout.strip().splitlines()[-1])]
    except (ValueError, IndexError):
        checks.append(f"Blank-page check failed: {(r.stderr or r.stdout).strip()[-160:]}")
        return []


def _idle_screens_here(cam, runs, hw, hh, checks, every=4.0):
    sys.path.insert(0, r"{{KIT}}/tools")
    try:
        import privacy_ocr
    except Exception as e:  # noqa
        checks.append(f"Blank-page check unavailable ({type(e).__name__}).")
        return []
    out = []
    for a, b in runs:
        t, cur = a + 0.3, None
        while t < b:
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(cam), "-frames:v", "1", "-vf",
                                f"crop={hw}:{hh}:0:0", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
            idle = False
            if len(r.stdout) == hw * hh * 3:
                img = np.frombuffer(r.stdout, np.uint8).reshape(hh, hw, 3)
                txt = " ".join(ln[0] for ln in privacy_ocr.ocr(img))
                idle = bool(NEWTAB_RE.search(txt)) and len(txt) < 900   # a new tab has little text; a page never says it
            if idle:
                cur = [max(a, t - every / 2), min(b, t + every / 2)] if cur is None else [cur[0], min(b, t + every / 2)]
            elif cur is not None:
                out.append(tuple(cur))
                cur = None
            t += every
        if cur is not None:
            out.append(tuple(cur))
    out = [(round(x, 2), round(y, 2)) for x, y in out if y - x >= 1.5]
    return out


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--idle":
    ck = []
    res = _idle_screens_here(sys.argv[2], [tuple(x) for x in json.loads(sys.argv[5])], int(sys.argv[3]), int(sys.argv[4]), ck,
                             float(sys.argv[6]) if len(sys.argv) > 6 else 4.0)
    print(json.dumps([list(x) for x in res]))
