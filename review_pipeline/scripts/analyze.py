"""Per-frame analysis at analysis_fps: head yaw on Camera A (left half) and what the right half shows
(side = side-angle camera with a face, screen = screen recording, product = product cam), plus whether the LEFT half is a
screen recording ("left": "screen") — some recordings put the desktop on the left and the face cam on the right
(dhgate asics, 2026-10-22: the whole buying walkthrough showed his face because only the right half was checked).
A half is a screen when it is mostly white OR mostly perfectly flat pixels (screen captures 0.43-0.87, camera footage
<= 0.24 — dark web pages fail the white test). Cached to work/analysis.json; old caches get the left-half fields backfilled."""
import json, math, subprocess, sys
from pathlib import Path
import numpy as np

W, H = 640, 360  # analysis size per half
SCREEN_WHITE, SCREEN_FLAT = 0.35, 0.35


def _white_flat(rgb):
    import cv2
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    white = float(((hsv[..., 1] < 30) & (hsv[..., 2] > 200)).mean())
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.int16)
    flat = float(((np.abs(np.diff(g, axis=1))[:-1, :] == 0) & (np.abs(np.diff(g, axis=0))[:, :-1] == 0)).mean())
    return white, flat


def is_screen(white, flat):
    return white > SCREEN_WHITE or flat > SCREEN_FLAT


def _backfill_left(project, fps, rows):
    """Add lwhite/lflat/left to a cached analysis (no face model needed: the left face is already in yaw)."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(project / "raw" / "camera.mp4"),
           "-vf", f"fps={fps},crop=iw/2:ih:0:0,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = W * H * 3
    for r in rows:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        white, flat = _white_flat(np.frombuffer(buf, np.uint8).reshape(H, W, 3))
        r["lwhite"], r["lflat"] = round(white, 3), round(flat, 3)
        r["left"] = "screen" if r["yaw"] is None and is_screen(white, flat) else "cam"
    p.kill()
    for r in rows:
        r.setdefault("left", "cam")
    return rows

def _yaw_from_matrix(m):
    m = np.array(m).reshape(4, 4)[:3, :3]
    return math.degrees(math.atan2(-m[2, 0], math.sqrt(m[0, 0] ** 2 + m[1, 0] ** 2)))

def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def analyze(project: Path, cfg: dict, skill: Path) -> list:
    """Cached rows; a cache that stops short of the recording is resumed from where it stopped (prada cups 2026-10-22:
    the scan ended at 10:37 of 22:05, so the whole buying walkthrough had no screen detection — the PC screen sat in the
    face circle and his face filled the frame)."""
    out = project / "work" / "analysis.json"
    fps = cfg["angles"]["analysis_fps"]
    dur = _duration(project / "raw" / "camera.mp4")
    if out.exists():
        rows = json.loads(out.read_text())
        if rows and "rfx" in rows[0]:
            if "left" not in rows[0]:
                rows = _backfill_left(project, fps, rows)
                out.write_text(json.dumps(rows))
            if dur and rows[-1]["t"] < dur - 2.0:
                print(f"analysis: cache ends at {rows[-1]['t']:.1f} s of {dur:.1f} s, resuming", flush=True)
                rows = rows + _scan(project, fps, skill, len(rows))
                out.write_text(json.dumps(rows))
            return rows
    rows = _scan(project, fps, skill, 0)
    if dur and rows and rows[-1]["t"] < dur - 2.0:   # the pipe ended early: one more go from where it stopped
        rows = rows + _scan(project, fps, skill, len(rows))
    out.write_text(json.dumps(rows))
    return rows


def _read_exact(stream, size):
    """A pipe read can come back short before EOF; keep reading until size bytes or real EOF."""
    buf = b""
    while len(buf) < size:
        chunk = stream.read(size - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _scan(project, fps, skill, first):
    """Analysis rows from frame index `first` (t = index / fps) to the end of the recording."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    import cv2
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(skill / "models" / "face_landmarker.task")),
                                        output_facial_transformation_matrixes=True, num_faces=1)
    lm_left = vision.FaceLandmarker.create_from_options(opts)
    lm_right = vision.FaceLandmarker.create_from_options(opts)
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{first / fps:.3f}"] if first else []) + ["-i", str(project / "raw" / "camera.mp4"),
           "-vf", f"fps={fps},scale={W*2}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    rows, i, size = [], first, W * 2 * H * 3
    while True:
        buf = _read_exact(p.stdout, size)
        if len(buf) < size:
            break
        f = np.frombuffer(buf, np.uint8).reshape(H, W * 2, 3)
        left, right = np.ascontiguousarray(f[:, :W]), np.ascontiguousarray(f[:, W:])
        row = {"t": round(i / fps, 3), "yaw": None, "fx": None, "fy": None, "rfx": None, "rfy": None}
        r = lm_left.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=left))
        if r.face_landmarks:
            row["yaw"] = round(_yaw_from_matrix(r.facial_transformation_matrixes[0]), 1)
            pts = r.face_landmarks[0]
            row["fx"] = round(sum(q.x for q in pts) / len(pts), 3)
            row["fy"] = round(sum(q.y for q in pts) / len(pts), 3)
        white, flat = _white_flat(right)
        lwhite, lflat = _white_flat(left)
        row["lwhite"], row["lflat"] = round(lwhite, 3), round(lflat, 3)
        row["left"] = "screen" if row["yaw"] is None and is_screen(lwhite, lflat) else "cam"
        rr = lm_right.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=right))
        if is_screen(white, flat):
            row["right"] = "screen"
        elif rr.face_landmarks:
            row["right"] = "side"
            q = rr.face_landmarks[0]
            row["rfx"] = round(sum(v.x for v in q) / len(q), 3)
            row["rfy"] = round(sum(v.y for v in q) / len(q), 3)
        else:
            row["right"] = "product"
        row["white"] = round(white, 3)
        rows.append(row)
        i += 1
    p.wait()
    return rows

if __name__ == "__main__":
    here = Path(__file__).parent
    cfg = json.loads((here / "config.json").read_text())
    rows = analyze(Path(sys.argv[1]), cfg, here.parent)
    print(len(rows), "frames")
