"""Vertical Short from a finished render.  python short.py <in.mp4> <out.mp4> <start> <end> [center|left|right] [--cam x,y,w,h]
9:16 crop of a 16:9 render (center, or the left/right third), scaled to 1080x1920, loudnorm -14 LUFS / TP -1 (the user's
Shorts exception), H.264 High + AAC, +faststart."""
import subprocess
import sys

src, out, t0, t1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
side = sys.argv[5] if len(sys.argv) > 5 and not sys.argv[5].startswith("--") else "center"
x = {"center": "(iw-ih*9/16)/2", "left": "0", "right": "iw-ih*9/16"}.get(side, "(iw-ih*9/16)/2")
vf = f"crop=ih*9/16:ih:{x}:0,scale=1080:1920:flags=lanczos,fps=30,format=yuv420p"
cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", src, "-vf", vf,
       "-af", "loudnorm=I=-14:TP=-1:LRA=11,aresample=48000", "-c:v", "h264_nvenc", "-profile:v", "high", "-rc", "vbr", "-b:v", "0", "-cq", "19",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
if r.returncode:
    sys.exit(r.stderr[-800:])
print(f"short {t1 - t0:.1f}s ({side}) -> {out}")
