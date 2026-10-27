"""Recordings that come in more than one file: join them into ONE raw/camera.mp4 before anything else runs.

lv trainer 2026-10-23: the review was recorded as "lv trainer dhate.mp4" (the main take) plus an OBS continuation
"2025-12-16 07-41-25.mp4" (the purchase walkthrough + outro, 312 s). The continuation is under the 700 MB "main" size, so
it landed in raw/broll; the B-roll picker cut it in as a raw side-by-side clip ("it's literally the raw footage ... it's
split") and the intro used it too (0:13, "no one should ever know my video is split in two").

Rules:
- A side-by-side recording (aspect >= 2.5, e.g. 3840x1080) with the SAME size as the main recording and >= 30 s is a
  part of the recording, never B-roll. Found in raw/broll it is MOVED to raw/parts/ (never deleted). raw/parts/ can also
  be filled by hand (drop the extra recording there).
- Order = recording start time: the OBS file name ("2025-12-16 07-41-25") when it has one, else modified time minus
  duration (OBS writes the file until the recording stops). The Drive upload time is NOT used (several files are
  often uploaded together).
- The main recording moves to raw/parts/ too; raw/camera.mp4 becomes the stream-copy concat of all parts (all audio
  tracks kept, so the mic swap still works). raw/parts/parts.json records the order and each part's start offset.
- Every cache built from the old camera.mp4 (transcript, analysis, cuts, mix, trim + take review ...) is moved to
  work/_before_join/ so the whole pipeline re-runs on the joined file. Part 1's times do not change, so
  raw/extra_cuts.json etc. stay valid for part 1.
"""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

VIDEO = {".mp4", ".mov", ".mkv", ".m4v"}
SIDE_ASPECT = 2.5
MIN_PART_SECONDS = 30.0
CACHES = ["transcript.json", "analysis.json", "sections.json", "cuts.json", "angles.json", "zooms.json", "cursor.json",
          "levels.json", "broll_plan.json", "audio_mix.json", "mic16k.wav", "topic_zooms.json", "trim_extra.json",
          "timeline.json", "trim"]


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return None
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        return None
    return {"w": v.get("width"), "h": v.get("height"), "vcodec": v.get("codec_name"), "fps": v.get("r_frame_rate"),
            "audio": [s.get("codec_name") for s in d["streams"] if s.get("codec_type") == "audio"],
            "dur": float(d.get("format", {}).get("duration") or 0)}


def is_side_by_side(info):
    return bool(info and info["w"] and info["h"] and info["w"] / info["h"] >= SIDE_ASPECT)


def is_part(info, ref):
    return is_side_by_side(info) and ref and (info["w"], info["h"]) == (ref["w"], ref["h"]) and info["dur"] >= MIN_PART_SECONDS


def obs_start(name):
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)[ _T](\d\d)-(\d\d)-(\d\d)", name)
    return time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1)) if m else None


def start_time(p, info):
    return obs_start(p.name) or (p.stat().st_mtime - (info or {}).get("dur", 0))


def _move(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError:
            time.sleep(1.5 * (i + 1))
    shutil.move(str(src), str(dst))


def ensure_joined(project: Path, checks: list):
    """Collect the parts, join them into raw/camera.mp4 when the set changed. Returns True when a (re)join happened."""
    raw, work = project / "raw", project / "work"
    pdir = raw / "parts"
    state_p = pdir / "parts.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    base = raw / "camera_original.mp4" if (raw / "camera_original.mp4").exists() else raw / "camera.mp4"
    if state.get("order"):   # already joined once: the main lives in raw/parts
        ref = probe(pdir / state["order"][0])
    else:
        ref = probe(base) if base.exists() else None
    if not ref or not is_side_by_side(ref):
        return False
    # 1. side-by-side recordings dropped as B-roll are parts of the recording
    moved = []
    if (raw / "broll").is_dir():
        for p in sorted((raw / "broll").iterdir()):
            if p.suffix.lower() in VIDEO and is_part(probe(p), ref):
                _move(p, pdir / p.name)
                moved.append(p.name)
    if moved:
        bj = raw / "broll.json"   # its auto label for the moved file goes too
        if bj.exists():
            try:
                lab = json.loads(bj.read_text(encoding="utf-8"))
                bj.write_text(json.dumps([x for x in lab if x.get("file") not in moved], indent=1), encoding="utf-8")
            except (ValueError, AttributeError):
                pass
        checks.append(f"{', '.join(moved)} is a second two-camera recording, not B-roll: moved to raw/parts/ and joined "
                      f"after the main recording.")
    extras = [p for p in sorted(pdir.glob("*")) if p.suffix.lower() in VIDEO and p.name not in state.get("order", [])] if pdir.is_dir() else []
    if not extras:
        return False
    # 2. the main recording joins the parts folder (first join only)
    if not state.get("order"):
        main = pdir / ("main - " + (project.name + ".mp4"))
        _move(base, main)
        if base.name == "camera_original.mp4" and (raw / "camera.mp4").exists():
            _move(raw / "camera.mp4", work / "_before_join" / "camera_mixed_old.mp4")   # the old one-part mic mix
        names = [main.name]
    else:
        names = list(state["order"])
        if (raw / "camera_original.mp4").exists():   # a re-join: the previous joined file (and its mix) are rebuilt
            _move(raw / "camera_original.mp4", work / "_before_join" / "camera_joined_old.mp4")
        (raw / "camera.mp4").unlink(missing_ok=True)
    infos = {n: probe(pdir / n) for n in names + [p.name for p in extras]}
    keep_first = names[:1]   # the main take stays first; everything else by recording start time
    rest = sorted(set(infos) - set(keep_first), key=lambda n: start_time(pdir / n, infos[n]))
    order = keep_first + rest
    bad = [n for n in order if (infos[n]["w"], infos[n]["h"], infos[n]["vcodec"], infos[n]["fps"], len(infos[n]["audio"]))
           != (ref["w"], ref["h"], ref["vcodec"], ref["fps"], len(ref["audio"]))]
    lst = pdir / "concat.txt"
    lst.write_text("".join(f"file '{(pdir / n).as_posix()}'\n" for n in order), encoding="utf-8")
    tmp = raw / "camera.joining.mp4"
    if bad:   # different format: re-encode to the main's format so the concat is clean
        checks.append(f"Parts with a different format were re-encoded before joining: {', '.join(bad)}.")
        ins = sum([["-i", str(pdir / n)] for n in order], [])
        na = len(ref["audio"])
        chains = "".join(f"[{i}:v]scale={ref['w']}:{ref['h']},fps={ref['fps']},setsar=1[v{i}];" for i in range(len(order)))
        concat = "".join(f"[v{i}]" + "".join(f"[{i}:a:{k}]" for k in range(na)) for i in range(len(order)))
        fc = chains + concat + f"concat=n={len(order)}:v=1:a={na}[v]" + "".join(f"[a{k}]" for k in range(na))
        cmd = ["ffmpeg", "-v", "error", "-y"] + ins + ["-filter_complex", fc, "-map", "[v]"] + sum([["-map", f"[a{k}]"] for k in range(na)], []) + \
              ["-c:v", "h264_nvenc", "-cq", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(tmp)]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0", "-c", "copy",
               "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True)
    _move(tmp, raw / "camera.mp4")
    offs, acc = [], 0.0
    for n in order:
        offs.append(round(acc, 3))
        acc += infos[n]["dur"]
    state = {"order": order, "offsets": offs, "joined": time.strftime("%Y-%m-%d %H:%M")}
    state_p.write_text(json.dumps(state, indent=1), encoding="utf-8")
    # 3. every cache of the old camera.mp4 goes aside: the whole edit re-runs on the joined recording
    old = work / "_before_join" / time.strftime("%Y%m%d-%H%M%S")
    for f in CACHES:
        if (work / f).exists():
            _move(work / f, old / f)
    checks.append("Recording joined from " + " + ".join(f"{n} (at {o / 60:.1f} min)" for n, o in zip(order, offs)) +
                  "; transcript, analysis, cuts, mic mix and take review were redone on the joined file.")
    return True
