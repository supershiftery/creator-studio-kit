"""Shared bits for the gaming pipeline scripts. Every script: python <script>.py <project dir> [draft|final]
Work dir = <project>/Edit/studio (never the hand-made Edit/work of older projects)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
HERE = Path(__file__).resolve().parent
TOOLS = Path(r"{{KIT}}/tools")
ASSETS = Path(r"{{KIT}}/assets")
SFX_DIR = ASSETS / "Graphics" / "HyperFrames" / "servers-intro-oct" / "assets" / "sfx"
REALM_WIPE = ASSETS / "Graphics" / "HyperFrames" / "realm-transition" / "renders" / "realm-transition.mov"
SERVER_WIPE = ASSETS / "Graphics" / "HyperFrames" / "server-transition" / "renders" / "server-transition.mov"
DEFAULT_WIPE = REALM_WIPE   # kept for old imports; use wipe_for()
NVENC = ["-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p"]
FACE_MODEL = r"{{KIT}}/review_pipeline/models/face_landmarker.task"


def wipe_for(doc, project=None):
    """Section transition by video kind (user 2026-10-22): the Realms wipe is ONLY for Realms videos; servers and every
    other gaming list video get the server transition. settings.wipe overrides.
    Custom per-video transition (user 2026-10-24: "custom transition motion graphics ... for like each video", e.g. a Top 5
    dragon or Pokémon add-on video): a transparent MOV named *transition* in <project>/Graphics (not in _replaced/_test
    folders) is used automatically. Recipe: {{KIT}}/assets/Graphics/HyperFrames/_templates/transitions/README.md"""
    s = (doc.get("settings") or {}).get("wipe")
    if s and os.path.exists(s):
        return str(s)
    if project:
        g = Path(project) / "Graphics"
        own = sorted(m for m in g.rglob("*.mov") if "transition" in m.stem.lower()
                     and not any(x.lower().startswith(("_replaced", "_test", "_kv test")) for x in m.relative_to(g).parts[:-1])) if g.is_dir() else []
        if own:
            return str(own[0])
    realm = re.search(r"\brealms?\b", doc.get("title") or "", re.I)
    pick = REALM_WIPE if realm or not SERVER_WIPE.exists() else SERVER_WIPE
    return str(pick)


def face_box(video, half_x=0, n=20, t0=None, t1=None):
    """Median face centre (cx, cy) and height in the webcam half of an OBS capture (mediapipe face landmarker on n
    frames). None when no face is found (or mediapipe is missing)."""
    try:
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except ImportError:
        return None
    dur = duration(video)
    a, b = (t0 if t0 is not None else dur * 0.05), (t1 if t1 is not None else dur * 0.95)
    L = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=FACE_MODEL), num_faces=1))
    got = []
    for t in np.linspace(a, b, n):
        fr = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf",
                             f"crop=1920:1080:{half_x}:0,scale=960:540", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            capture_output=True, creationflags=CREATE_NO_WINDOW).stdout
        if len(fr) < 960 * 540 * 3:
            continue
        r = L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.frombuffer(fr, np.uint8).reshape(540, 960, 3).copy()))
        if r.face_landmarks:
            p = np.array([(q.x, q.y) for q in r.face_landmarks[0]])
            got.append(((p[:, 0].min() + p[:, 0].max()) / 2 * 1920, (p[:, 1].min() + p[:, 1].max()) / 2 * 1080, (p[:, 1].max() - p[:, 1].min()) * 1080))
    if len(got) < 3:
        return None
    m = np.median(np.array(got), 0)
    return float(m[0]), float(m[1]), float(m[2])


def framed_crop(crop, face, half_x=0, y_ratio=0.57):
    """Cam framing (user 2026-10-22: "I'm more over to the left this time ... the logic needs handling for framing"):
    move the head-and-shoulders box (w, h, x, y in the full frame) so the face is centred left-right and sits y_ratio
    down the box (where it sat in the approved Top 5 Realms edit), clamped inside the webcam half."""
    if not crop or not face:
        return crop
    w, h, x, y = crop
    cx, cy, _ = face
    nx = round(min(max(half_x + cx - w / 2, half_x), half_x + 1920 - w))
    ny = round(min(max(cy - h * y_ratio, 0), 1080 - h))
    return [w, h, nx, ny]


def run(cmd, check=True, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, **kw)
    if check and r.returncode:
        raise RuntimeError(f"{cmd[0]} failed:\n{r.stderr[-1500:]}")
    return r


def say(*a):
    print(*a, flush=True)


class Project:
    def __init__(self, path, mode="draft"):
        self.path = Path(path)
        self.mode = mode
        self.doc = json.loads((self.path / "studio.json").read_text(encoding="utf-8-sig"))
        self.settings = self.doc.get("settings", {})
        self.work = self.path / "Edit" / "studio"
        self.work.mkdir(parents=True, exist_ok=True)
        (self.path / "Edit").mkdir(exist_ok=True)
        self.src = self.doc.get("source") or ""
        self.W, self.H, self.FPS = (960, 540, 30) if mode == "draft" else (1920, 1080, 60)
        self.k = self.W / 1920

    def wf(self, name):
        return self.work / name

    def read(self, name, default=None):
        p = self.wf(name)
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else default

    def write(self, name, data):
        self.wf(name).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    @property
    def source_info(self):
        return self.read("source.json", {})

    @property
    def sections(self):
        return [tuple(s) for s in self.read("sections.json", [])]

    def section_of(self, t):
        # the section that really holds t wins; the 0.5 s slack is only a fallback. First-match-with-slack gave a piece
        # starting 0.4 s after #4 ended to #4, so #3's card, wipe and music came one piece late (Top 10 Servers
        # 2026-10-22: #3 31 s late, #1 PokéFind 47 s late with no transition and no Pokémon music where it starts)
        secs = self.sections
        for name, s, e in secs:
            if s <= t < e:
                return name
        for name, s, e in secs:
            if s - 0.5 <= t <= e + 0.5:
                return name
        return "?"

    @property
    def keep(self):
        d = self.read("cuts/cuts.json")
        return [list(x) for x in d["keep"]] if d else []

    @property
    def words(self):
        return self.read("words.json", [])

    def out_video(self):
        title = re.sub(r'[<>:"/\\|?*]', "", self.doc.get("title") or self.path.name).strip()
        return self.path / "Edit" / f"{title} {self.mode}.mp4"

    def game_crop(self):
        """ffmpeg crop expr for the gameplay area"""
        si = self.source_info
        return si.get("game_crop") or "iw:ih:0:0"

    def cam_crop(self):
        """(w, h, x, y) head-and-shoulders box inside the full frame, or None when there's no webcam"""
        si = self.source_info
        return tuple(si["cam_crop"]) if si.get("cam_crop") else None


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def lufs(path, af=""):
    err = run(["ffmpeg", "-nostats", "-i", str(path), "-af", (af + "," if af else "") + "ebur128=framelog=quiet", "-f", "null", "-"], check=False).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else -30.0


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], check=False)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0
