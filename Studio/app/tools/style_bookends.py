"""A custom video type's own pieces on every build (my_style assets): what goes at the start (an opening card / clip), at the
end, and a logo in the corner. Runs on the finished render, in place, before the QC check.

    python style_bookends.py <project> <video>

The type's assets are in my_style/types/<slug>/assets (roles in the type file: start | end | logo). A render this already
finished (same size + time as last run) is left alone, so a pipeline that re-uses its last render never gets two openings.
Output: H.264 High yuv420p + AAC, same size / fps as the video.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import media  # noqa: E402
import mystyle  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
IMG = {".png", ".jpg", ".jpeg", ".webp"}


def sig(p):
    st = os.stat(p)
    return [st.st_size, round(st.st_mtime, 2)]


def encoder():
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "18", "-profile:v", "high"] if "h264_nvenc" in r.stdout else \
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-profile:v", "high"]


def main(project, video):
    doc = json.loads((Path(project) / "studio.json").read_text(encoding="utf-8"))
    doc["path"] = project
    t = mystyle.type_of(doc)
    assets = [a for a in (t or {}).get("assets") or [] if a.get("role") in ("start", "end", "logo")]
    state_p = Path(project) / "_style" / "bookends.json"
    state = mystyle._read(state_p, {}) or {}
    if not assets:
        print("no start / end / logo pieces in this type")
        return
    if not os.path.exists(video):
        sys.exit(f"no render at {video}")
    if state.get("video") == str(video) and state.get("sig") == sig(video):
        print("already has this type's opening / ending (same render as last time)")
        return
    adir = mystyle.TYPES / t["slug"] / "assets"
    keep = Path(project) / "_style" / "clean"
    keep.mkdir(parents=True, exist_ok=True)
    clean = keep / Path(video).name   # the render without the type's pieces, kept (the input of this step)
    info = media.probe(video)
    W, H, fps = info["width"], info["height"], info["fps"] or 30
    ins, parts, fc, n = [], [], [], 0

    def seg(path, dur):
        nonlocal n
        p = str(adir / path)
        if Path(p).suffix.lower() in IMG:
            ins.extend(["-loop", "1", "-t", f"{dur:.2f}", "-i", p, "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=48000:cl=stereo"])
            v, a = n, n + 1
            n += 2
        else:
            ins.extend(["-i", p])
            v, a = n, n
            n += 1
            if not media.probe(p).get("audio"):
                ins.extend(["-f", "lavfi", "-t", f"{media.probe(p)['duration']:.2f}", "-i", "anullsrc=r=48000:cl=stereo"])
                a = n
                n += 1
        k = len(parts)
        fc.append(f"[{v}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={fps},setsar=1,format=yuv420p[v{k}]")
        fc.append(f"[{a}:a]aresample=48000,aformat=channel_layouts=stereo[a{k}]")
        parts.append(k)

    for a in [a for a in assets if a["role"] == "start"]:
        seg(a["file"], float(a.get("dur") or 4))
    main_i = n
    ins.extend(["-i", str(clean)])
    n += 1
    logo = next((a for a in assets if a["role"] == "logo"), None)
    k = len(parts)
    mv = f"[{main_i}:v]fps={fps},setsar=1,format=yuv420p"
    if logo:
        ins.extend(["-i", str(adir / logo["file"])])
        li = n
        n += 1
        lw = int(min(W, H * 16 / 9) * 0.11) // 2 * 2   # sized off a 16:9 frame: a 3840-wide side-by-side gets a normal logo
        fc.append(f"[{li}:v]scale={lw}:-2,format=rgba,colorchannelmixer=aa=0.85[lg]")
        fc.append(f"{mv}[mv];[mv][lg]overlay=W-w-{int(W * 0.025)}:{int(H * 0.035)}[v{k}]")
    else:
        fc.append(f"{mv}[v{k}]")
    fc.append(f"[{main_i}:a]aresample=48000,aformat=channel_layouts=stereo[a{k}]")
    parts.append(k)
    for a in [a for a in assets if a["role"] == "end"]:
        seg(a["file"], float(a.get("dur") or 4))
    fc.append("".join(f"[v{k}][a{k}]" for k in parts) + f"concat=n={len(parts)}:v=1:a=1[vo][ao]")
    os.replace(video, clean)
    cmd = ["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]", *encoder(),
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video)]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    if r.returncode:
        os.replace(clean, video)
        sys.exit("adding the type's opening / ending failed: " + r.stderr[-800:])
    mystyle._write(state_p, {"video": str(video), "sig": sig(video), "clean": str(clean),
                             "pieces": [{"role": a["role"], "file": a["file"]} for a in assets]})
    print(f"added: {', '.join(a['role'] + ' ' + a['file'] for a in assets)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
