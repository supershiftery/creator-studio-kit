"""Intro first, then the main video (user rule). Usage: python join.py <intro.mp4> <main.mp4> <out.mp4> [--cq N]
--cq: drafts 21 (default); finals 17, otherwise the join re-encode undoes the cq 19 main render (Shein final 2026-10-21)."""
import re, subprocess, sys
intro, main, out = sys.argv[1:4]
CQ = sys.argv[sys.argv.index("--cq") + 1] if "--cq" in sys.argv else "21"


def lufs(path):
    e = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, errors="replace").stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", e)[-1])


# one fixed gain per part to -16 LUFS (no dynamic leveling: it pumped, user note v1) + a peak limiter
g_main = -16.0 - lufs(main)
# the joined file keeps the MAIN video's frame rate (60 for a 60 fps review recording, watch spreadsheet 2026-10-24:
# "it still feels like it's jittering ... the screen recordings as well"); phone videos stay 30
_fr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", main],
                     capture_output=True, text=True).stdout.strip() or "30/1"
FR = 60 if eval(_fr.replace("/", "/float(") + ")" if "/" in _fr else _fr) >= 50 else 30
g_intro = -16.5 - lufs(intro)
g = (f"[0:v]fps={FR},format=yuv420p,setsar=1[v0];[1:v]fps={FR},format=yuv420p,setsar=1[v1];"
     f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={g_intro:.2f}dB,alimiter=limit=0.84:level=0[a0];"
     f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={g_main:.2f}dB,alimiter=limit=0.84:level=0[a1];"
     "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][ac];[ac]alimiter=limit=0.79:level=0[a]")
# the LAST limiter sits after everything that adds up (the slide's overlap + whoosh) at -2 dBFS: AAC adds inter-sample
# peaks over the 0.84 part limiters (lv skatesta 2026-10-24: main -5.9, intro -1.4, joined -0.0 dBTP, target <= -1)
extra = []
if "--slide" in sys.argv:
    # --slide [seconds]: the intro slides out left as the main video slides in, a white line on the seam, a whoosh (review
    # videos, s25 ultra 2026-10-23: "make up transitions for these segments ... a slide effect"). The slide OVERLAPS the
    # intro's last moment: no frozen frames, no added seconds (reselling spreadsheet 2026-10-23: "we shouldn't add extra
    # seconds, we just want to jump right into the video"); the main audio starts at full level under the slide.
    i = sys.argv.index("--slide")
    d = float(sys.argv[i + 1]) if i + 1 < len(sys.argv) and re.match(r"^[\d.]+$", sys.argv[i + 1]) else 0.3
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", intro],
                               capture_output=True, text=True).stdout.strip())
    off = max(0.0, dur - d)
    sfx = r"{{KIT}}/tools\intro_library\kit\sfx\whoosh-short.mp3"
    extra = ["-i", sfx]
    g = (f"[0:v]fps={FR},scale=1920:1080,format=yuv420p,setsar=1[v0];[1:v]fps={FR},scale=1920:1080,format=yuv420p,setsar=1[v1];"
         f"[v0][v1]xfade=transition=slideleft:duration={d}:offset={off:.3f},"
         f"drawbox=x='iw*(1-(t-{off:.3f})/{d})-6':y=0:w=12:h=ih:color=white@0.9:t=fill:enable='between(t,{off:.3f},{off + d:.3f})'[v];"
         f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={g_intro:.2f}dB,alimiter=limit=0.84:level=0[a0];"
         f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={g_main:.2f}dB,alimiter=limit=0.84:level=0[a1];"
         f"[a0][a1]acrossfade=d={d}:c1=tri:c2=nofade[ax];"
         f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume=-6dB,adelay={int(off * 1000)}|{int(off * 1000)}[at];"
         "[ax][at]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.79:level=0[a]")
subprocess.run(["ffmpeg", "-v", "error", "-stats", "-y", "-i", intro, "-i", main, *extra, "-filter_complex", g, "-map", "[v]", "-map", "[a]",
                "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-cq", CQ, "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-movflags", "+faststart", out], check=True)
print("wrote", out, f"(gain intro {g_intro:+.1f} dB, main {g_main:+.1f} dB)")
