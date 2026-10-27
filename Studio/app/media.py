"""ffprobe / ffmpeg helpers: probe, thumbnails, frames, audio track pick."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from store import DATA

THUMBS = DATA / "thumbs"
THUMBS.mkdir(exist_ok=True)
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=CREATE_NO_WINDOW, **kw)


_PROBES = {}   # (path, size, mtime) -> probe result


def probe(path):
    """{duration, width, height, fps, vcodec, audio: [{index, codec, channels}], size}. Kept per (path, size, mtime): the
    Studio page probed all 45 sources on every refresh, 5 s each load (user 2026-10-26: "takes about 15 seconds to load")."""
    p = str(path)
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (p, st.st_size, st.st_mtime)
    if key in _PROBES:
        return json.loads(json.dumps(_PROBES[key]))   # a copy: callers may change it
    out = _probe(p)
    if out:
        _PROBES[key] = out
    return json.loads(json.dumps(out)) if out else out


def _probe(p):
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", p])
    if r.returncode or not r.stdout:
        return None
    d = json.loads(r.stdout)
    out = {"duration": float(d.get("format", {}).get("duration") or 0), "size": os.path.getsize(p), "audio": [],
           "width": 0, "height": 0, "fps": 0, "vcodec": "", "pix_fmt": ""}
    for s in d.get("streams", []):
        if s["codec_type"] == "video" and not out["width"]:
            num, den = (s.get("r_frame_rate") or "0/1").split("/")
            out.update(width=s.get("width", 0), height=s.get("height", 0), vcodec=s.get("codec_name", ""),
                       pix_fmt=s.get("pix_fmt", ""), fps=round(float(num) / float(den or 1), 3))
        elif s["codec_type"] == "audio":
            out["audio"].append({"index": len(out["audio"]), "codec": s.get("codec_name"), "channels": s.get("channels")})
    return out


def layout_of(info):
    """side-by-side OBS capture (3840x1080 / 3840x1920) vs plain 16:9"""
    if not info or not info["width"]:
        return "unknown"
    return "side-by-side" if info["width"] >= 2 * info["height"] * 0.95 and info["width"] >= 3000 else "single"


def thumb(path, t=None, w=480, crop=None):
    """Cached JPEG thumbnail of a video/image. crop = 'left'|'right' half (for side-by-side captures)."""
    path = str(path)
    if not os.path.exists(path):
        return None
    key = hashlib.sha1(f"{path}|{os.path.getmtime(path)}|{t}|{w}|{crop}".encode()).hexdigest()[:16]
    out = THUMBS / f"{key}.jpg"
    if out.exists():
        return out
    ext = Path(path).suffix.lower()
    vf = []
    if crop == "left":
        vf.append("crop=iw/2:ih:0:0")
    elif crop == "right":
        vf.append("crop=iw/2:ih:iw/2:0")
    vf.append(f"scale={w}:-2")
    if ext in IMAGE_EXT:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", ",".join(vf), "-frames:v", "1", str(out)]
    else:
        if t is None:
            info = probe(path)
            t = min(max((info["duration"] if info else 0) * 0.12, 1.0), 600)
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path, "-vf", ",".join(vf), "-frames:v", "1", "-q:v", "4", str(out)]
    r = run(cmd)
    return out if out.exists() else None


def frame(path, t, out, w=None, crop_expr=None):
    vf = []
    if crop_expr:
        vf.append(f"crop={crop_expr}")
    if w:
        vf.append(f"scale={w}:-2")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path)]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-frames:v", "1", str(out)]
    return run(cmd).returncode == 0


def track_levels(path, ss=60, t=120):
    """mean dB per audio track (to find the mic = loudest, game = next)"""
    info = probe(path)
    if not info:
        return []
    out = []
    ss = min(ss, max(0, info["duration"] - t)) if info["duration"] > t else 0
    for a in info["audio"]:
        e = run(["ffmpeg", "-v", "info", "-ss", str(ss), "-t", str(t), "-i", str(path), "-map", f"0:a:{a['index']}",
                 "-af", "volumedetect", "-f", "null", "-"]).stderr
        m = re.search(r"mean_volume: (-?[\d.]+) dB", e)
        out.append(float(m.group(1)) if m else -99.0)
    return out


def is_h264(path):
    info = probe(path)
    return bool(info) and info["vcodec"] == "h264" and info["pix_fmt"] == "yuv420p"


def fmt_t(t):
    t = max(0, float(t or 0))
    return f"{int(t // 60)}:{int(t % 60):02d}"


def parse_t(s):
    """'1:22', '1:22.5', '82', '1h02m' -> seconds"""
    s = str(s).strip().lower()
    m = re.match(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi) * 60 + float(se)
    m = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(1))
    m = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?$", s)
    if m and any(m.groups()):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    raise ValueError(f"bad time {s!r}")


# ------------------------------------------------------------------ per-file cache (duration, spoken label)
CACHE = DATA / "media-cache.json"
_cache = None


def _load_cache():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache():
    try:
        CACHE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def cache_key(path):
    try:
        return f"{str(path).lower()}|{int(os.path.getmtime(path))}"
    except OSError:
        return str(path).lower()


def cached_duration(path):
    c = _load_cache()
    k = cache_key(path)
    if k in c and "duration" in c[k]:
        return c[k]["duration"]
    info = probe(path)
    d = round(info["duration"], 1) if info else 0
    c.setdefault(k, {})["duration"] = d
    _save_cache()
    return d


def cached_label(path):
    """The first thing said in the recording (so you can tell recordings apart). None until computed."""
    c = _load_cache()
    return c.get(cache_key(path), {}).get("label")


def compute_label(path, seconds=45):
    """Transcribe the opening of the loudest audio track and keep the first spoken sentence(s)."""
    c = _load_cache()
    k = cache_key(path)
    if c.get(k, {}).get("label") is not None:
        return c[k]["label"]
    label = ""
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        info = probe(path)
        best = 0
        if info and len(info["audio"]) > 1:
            lv = track_levels(path, ss=20, t=40)
            best = max(range(len(lv)), key=lambda i: lv[i]) if lv else 0
        raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(seconds), "-i", str(path), "-map", f"0:a:{best}", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, creationflags=CREATE_NO_WINDOW).stdout
        a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        if len(a) > 16000:
            m = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=4)
            segs, _ = m.transcribe(a, vad_filter=True, condition_on_previous_text=False)
            text = " ".join(sg.text.strip() for sg in segs).strip()
            text = re.sub(r"^(hello|hey|what's up|whats up|yo)\b[^.!?]*?(welcome back[^.!?]*?)?(video|channel)[.!?,]?\s*", "", text, flags=re.I)
            label = text[:140].strip() or "(no speech in the first 45 s)"
        else:
            label = "(no audio)"
    except Exception as e:  # noqa
        label = f"(label failed: {type(e).__name__})"
    c.setdefault(k, {})["label"] = label
    _save_cache()
    return label


def concat(paths, out):
    """Join several recordings into one file without re-encoding (same OBS profile). Returns out."""
    paths = [str(p) for p in paths]
    if len(paths) == 1:
        return paths[0]
    lst = Path(out).with_suffix(".concat.txt")
    lst.write_text("".join("file '" + p.replace("'", "'\\''") + "'\n" for p in paths), encoding="utf-8")
    r = run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)])
    if r.returncode:
        raise RuntimeError("could not join the recordings (different formats?): " + r.stderr[-400:])
    return str(out)
