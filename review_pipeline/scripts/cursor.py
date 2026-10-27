"""Mouse cursor track for the screen recording in the right half, cached to work/cursor.json.
Template-free: between consecutive frames, a small isolated change is the cursor moving; big changes
(scrolling, page loads) are ignored. A moving cursor leaves two marks in the difference (where it was and
where it is now), so when there are two, the one farther from the last known position is the new spot."""
import json, subprocess
from pathlib import Path
import numpy as np


def _groups(stats, cents, blobs, join):
    """Cluster nearby blobs; returns list of (cx, cy, x0, y0, x1, y1)."""
    groups = []
    for k in blobs:
        x0, y0, w, h = stats[k, 0], stats[k, 1], stats[k, 2], stats[k, 3]
        for g in groups:
            if x0 <= g[4] + join and x0 + w >= g[2] - join and y0 <= g[5] + join and y0 + h >= g[3] - join:
                g[2], g[3], g[4], g[5] = min(g[2], x0), min(g[3], y0), max(g[4], x0 + w), max(g[5], y0 + h)
                break
        else:
            groups.append([0, 0, x0, y0, x0 + w, y0 + h])
    for g in groups:
        g[0], g[1] = (g[2] + g[4]) / 2, (g[3] + g[5]) / 2
    return groups


def track_cursor(project: Path, cfg: dict, ranges, half_w: int, half_h: int) -> list:
    out = project / "work" / "cursor.json"
    if out.exists():
        pts = json.loads(out.read_text())
        if not pts or pts[0].get("v") == 3:
            return pts
    import cv2
    zc = cfg["zooms"]
    fps, W, H = zc["cursor_fps"], 960, 540
    box = zc["cursor_max_box"] * W / 1920
    pts = []
    for a, b in ranges:
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(project / "raw" / "camera.mp4"),
               "-vf", f"crop={half_w}:{half_h}:{half_w}:0,fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        prev, last, i = None, None, 0
        while True:
            buf = p.stdout.read(W * H)
            if len(buf) < W * H:
                break
            f = np.frombuffer(buf, np.uint8).reshape(H, W)
            if prev is not None:
                mask = (cv2.absdiff(f, prev) > 40).astype(np.uint8)
                mask[int(H * 0.94):] = 0  # taskbar clock
                mask[:int(H * 0.08)] = 0  # browser tabs / address bar (page loads, spinners)
                mask[:, int(W * 0.985):] = 0  # scrollbar
                changed = int(mask.sum())
                if 0 < changed < box * box * 2:
                    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
                    blobs = [k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] >= 6]
                    groups = [g for g in _groups(stats, cents, blobs, box * 0.3) if g[4] - g[2] <= box and g[5] - g[3] <= box]
                    if 1 <= len(groups) <= 2:
                        if len(groups) == 2 and last is not None:
                            g = max(groups, key=lambda g: (g[0] - last[0]) ** 2 + (g[1] - last[1]) ** 2)
                        elif len(groups) == 2:
                            g = None  # can't tell old from new yet
                        else:
                            g = groups[0]
                        if g is not None:
                            last = (g[0], g[1])
                            pts.append({"t": round(a + i / fps, 2), "x": round(g[0] / W, 4), "y": round(g[1] / H, 4), "v": 3})
            prev, i = f, i + 1
        p.wait()
    out.write_text(json.dumps(pts))
    return pts


def cursor_at(pts, t0, t1, min_moves=1):
    """Where the mouse settles in [t0, t1]: the median of its last few positions there.
    None unless it actually moved at least min_moves times (i.e. I was pointing at something)."""
    inside = [p for p in pts if t0 <= p["t"] <= t1 and 0.08 <= p["y"] < 0.94]
    if len(inside) < min_moves:
        return None
    tail = inside[-3:]
    return float(np.median([p["x"] for p in tail])), float(np.median([p["y"] for p in tail]))
