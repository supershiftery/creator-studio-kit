"""Step 1: look at the recording, pick the mic and game audio tracks, extract the mic, write source.json.
python prep.py <project>"""
import json
import os
import re
import sys

from glib import Project, run, say

P = Project(sys.argv[1])
src = P.src
if not src:
    sys.exit("no main footage in this project yet")
d = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", src]).stdout)
v = next(s for s in d["streams"] if s["codec_type"] == "video")
audio = [s for s in d["streams"] if s["codec_type"] == "audio"]
W, H = v["width"], v["height"]
num, den = v["r_frame_rate"].split("/")
dur = float(d["format"]["duration"])
S = P.settings
# layout: a 3840x1080 OBS side-by-side = webcam on one half, game on the other (user's profile: webcam LEFT)
side = S.get("webcam_side")
if W >= 2 * H * 0.95 and W >= 3000:
    side = side or "left"
    half = W // 2
    if side == "left":
        game_crop, cam_x = f"{half}:{H}:{half}:0", 0
    else:
        game_crop, cam_x = f"{half}:{H}:0:0", half
    cw, ch, cx, cy = S.get("cam_crop") or (1000, 917, 700, 20)      # head-and-shoulders box inside the 1920x1080 webcam half
    sc = half / 1920
    cam_crop = [round(cw * sc), round(ch * sc), round(cam_x + cx * sc), round(cy * sc)]
    layout = "side-by-side"
else:
    side = side or "none"
    game_crop, cam_crop, layout = f"{W}:{H}:0:0", (list(S["cam_crop_abs"]) if S.get("cam_crop_abs") else None), "single"
if S.get("game_crop"):
    game_crop = S["game_crop"]
# audio: mic = loudest track in the middle of the recording, game = the other track that isn't silent
levels = []
mid = max(0, min(dur / 2, dur - 120))
for i, a in enumerate(audio):
    e = run(["ffmpeg", "-v", "info", "-ss", f"{mid:.1f}", "-t", "120", "-i", src, "-map", f"0:a:{i}", "-af", "volumedetect", "-f", "null", "-"], check=False).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", e)
    levels.append(float(m.group(1)) if m else -99.0)
order = sorted(range(len(levels)), key=lambda i: -levels[i])
mic = S.get("mic_track") if S.get("mic_track") is not None else (order[0] if order else 0)
game = S.get("game_track")
if game is None:
    game = next((i for i in order[1:] if levels[i] > -88), None)   # game audio sits low (-70..-85 dB mean) but a dead track is < -90
say(f"{W}x{H} {float(num) / float(den):.0f} fps, {dur / 60:.1f} min, layout {layout}, webcam {side}; audio levels {levels} -> mic {mic}, game {game}")
mic_wav = P.wf("mic16k.wav")
prev = P.source_info
if not (mic_wav.exists() and prev.get("src") == src and prev.get("mic_track") == mic and mic_wav.stat().st_mtime >= os.path.getmtime(src)):
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", f"0:a:{mic}", "-ac", "1", "-ar", "16000", str(mic_wav)])
else:
    say("mic16k.wav is current, kept (so the transcript stays valid)")
P.write("source.json", {"src": src, "duration": dur, "width": W, "height": H, "fps": float(num) / float(den), "layout": layout,
                        "webcam_side": side, "game_crop": game_crop, "cam_crop": cam_crop, "mic_track": mic, "game_track": game,
                        "audio_levels": levels})
say("source.json written")
