"""Find dead phone screens (app loading / blank gray / black) in a raw phone-tutorial recording.
User note 2026-10-20 (v10 2:18): "a weird clip... just dead space" = the gray loading screen between app pages.
Detail score = mean horizontal pixel difference on the phone body; real screens > 3, loading/blank < 2.
Usage: python blank_phone.py <source.mp4> <words.json> <out.json> [--crop x,y,w,h]
Output runs >= 0.2 s with the words spoken during them (no words -> cut; words -> hold the last good phone frame)."""
import json, subprocess, sys
import numpy as np
src, words_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
x, y, w, h = [int(v) for v in sys.argv[sys.argv.index("--crop") + 1].split(",")] if "--crop" in sys.argv else (2628, 0, 504, 1080)
W, H = 126, 270
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=10,crop={w}:{h}:{x}:{y},scale={W}:{H},format=gray",
                      "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
det = []
while True:
    raw = p.stdout.read(W * H)
    if len(raw) < W * H:
        break
    fr = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32)[30:240]
    det.append(float(np.abs(np.diff(fr, axis=1)).mean()))
p.wait()
blank = np.array(det) < 2.0
words = json.load(open(words_path, encoding="utf-8"))
runs, i = [], 0
while i < len(blank):
    if blank[i]:
        j = i
        while j + 1 < len(blank) and blank[j + 1]:
            j += 1
        if j - i >= 1:
            s, e = i / 10 - 0.05, (j + 1) / 10 + 0.05
            talk = [wd["w"] for wd in words if wd["s"] < e and wd["e"] > s]
            runs.append({"s": round(s, 2), "e": round(e, 2), "words": " ".join(talk),
                         "fix": "hold last phone frame" if talk else "cut"})
        i = j + 1
    else:
        i += 1
json.dump(runs, open(out, "w"), indent=1)
print(f"{len(runs)} dead-screen runs")
for r in runs:
    print(f'  {r["s"]:7.2f}-{r["e"]:7.2f}  {r["fix"]:22s} {r["words"][:60]}')
