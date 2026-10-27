"""Blur what pii_scan.py found, in the RECORDING itself (user 2026-10-23, friend's Chime video: email, phone, home address,
bank account + routing numbers on screen). Every hit's line box is padded and blurred from 0.75 s before to 0.75 s after
the frames it was seen in, so a page that fades in or scrolls is covered too.

    python pii_blur.py <source.mp4> <pii.json> <out.mp4> [--fps 2] [--map timeline-trim.json]   (--map: blur an EDIT)

Every frame is decoded, blurred where needed (strong Gaussian, unreadable) and re-encoded once (NVENC cq 16, near-lossless
for a screen recording); the audio is copied untouched. Run it on raw/source.mp4 BEFORE the edit, keep the original next
to it (never delete footage), and the whole pipeline only ever sees the blurred picture."""
import json
import subprocess
import sys

import cv2
import numpy as np

src, pj, out = sys.argv[1], sys.argv[2], sys.argv[3]
scan_fps = float(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else 2.0
PAD_T, PAD_X, PAD_Y = 0.75, 14, 10

probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate:format=duration", "-of", "json", src], capture_output=True, text=True).stdout)
W, H = probe["streams"][0]["width"], probe["streams"][0]["height"]
num, den = map(int, probe["streams"][0]["r_frame_rate"].split("/"))
fps = num / den
hits = json.load(open(pj, encoding="utf-8"))["hits"]
if "--map" in sys.argv:
    # the hits are in RECORDING time and <src> is the edit (tools/trim_render.py, user 2026-10-23: cut first, then privacy):
    # move each hit into edit time through the timeline's kept ranges + speed; hits in cut-out parts are dropped
    tl = json.load(open(sys.argv[sys.argv.index("--map") + 1], encoding="utf-8"))
    keep, speed = tl["keep"], float(tl.get("speed") or 1.0)

    def to_edit(t):
        acc = 0.0
        for s, e in keep:
            if s - 1.0 <= t <= e + 1.0:   # a hit just outside a piece (padding) still counts for that piece's edge
                return (acc + min(max(t, s), e) - s) / speed
            acc += e - s
        return None
    hits = [dict(h, t=te) for h in hits if (te := to_edit(h["t"])) is not None]
sx, sy = W / 1920, H / 1080   # the scan reads frames scaled to 1920x1080

# merge each box's sightings into time ranges: the same box seen again within 2 scan frames = one continuous range
regions = []   # [t0, t1, x, y, w, h]
for h in sorted(hits, key=lambda h: (tuple(h["box"]), h["t"])):
    x, y, w, hh = h["box"]
    if w <= 0 or hh <= 0:
        continue
    box = [int((x - PAD_X) * sx), int((y - PAD_Y) * sy), int((w + 2 * PAD_X) * sx), int((hh + 2 * PAD_Y) * sy)]
    t0, t1 = h["t"] - PAD_T, h["t"] + 1 / scan_fps + PAD_T
    for r in regions:
        if r[2:] == box and t0 <= r[1] + 2 / scan_fps:
            r[1] = max(r[1], t1)
            break
    else:
        regions.append([t0, t1] + box)
print(f"{len(hits)} hits -> {len(regions)} blur regions, {sum(r[1] - r[0] for r in regions):.0f} s of boxes", flush=True)

# decode at a CONSTANT frame rate: an OBS recording is variable-rate, and counting its frames as if they were constant made
# the Chime picture 205 s short (2027 vs 2232 s, 2026-10-23) and slid every blur box later and later. The fps filter
# keeps real timestamps, so frame n really is at n / fps and the output picture is as long as the sound.
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={num}/{den}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{num}/{den}", "-i", "-",
                        "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p",
                        "-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "16", "-c:a", "copy", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
n, blurred = 0, 0
size = W * H * 3
while True:
    b = dec.stdout.read(size)
    if len(b) < size:
        break
    t = n / fps
    act = [r for r in regions if r[0] <= t <= r[1]]
    if act:
        f = np.frombuffer(b, np.uint8).reshape(H, W, 3).copy()
        for _, _, x, y, w, hh in act:
            x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + hh)
            if x1 > x0 and y1 > y0:
                roi = f[y0:y1, x0:x1]
                small = cv2.resize(roi, (max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)), interpolation=cv2.INTER_AREA)
                f[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR), (0, 0), 6)
        b = f.tobytes()
        blurred += 1
    enc.stdin.write(b)
    n += 1
    if n % (int(fps) * 300) == 0:
        print(f"  {t / 60:.0f} min", flush=True)
enc.stdin.close()
enc.wait()
dec.wait()
print(f"blurred {blurred} of {n} frames -> {out}")
if enc.returncode:
    sys.exit(enc.returncode)
# never hand on a file whose picture and sound differ (the Chime draft froze after 7:37 when this went unnoticed)
lens = {}
for line in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.split():
    kind, _, d_ = line.partition(",")
    if d_ and d_ != "N/A":
        lens[kind] = float(d_)
if "video" in lens and "audio" in lens and abs(lens["video"] - lens["audio"]) > 1.0:
    sys.exit(f"pii_blur: picture {lens['video']:.1f} s but sound {lens['audio']:.1f} s in {out}: refusing it")
print(f"lengths ok: picture {lens.get('video', 0):.1f} s, sound {lens.get('audio', 0):.1f} s")
