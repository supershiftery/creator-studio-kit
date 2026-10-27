"""Last privacy gate on a FINISHED edit: search every frame (4 fps) of the whole picture for the user's address/phone
templates at each phone scale the layouts use. Any match = the address is readable somewhere -> fail.
Usage: python final_privacy_sweep.py <final.mp4> [--scales 0.926,0.833]
  0.926 = main app layout (phone 1000 px tall from 1080), 0.833 = intro phone (900 px)."""
import glob, os, subprocess, sys
import cv2
import numpy as np

path = sys.argv[1]
scales = [float(s) for s in (sys.argv[sys.argv.index("--scales") + 1].split(",") if "--scales" in sys.argv else ["0.926", "0.889", "0.833"])]
tpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privacy_templates")
tpls = []
for p in sorted(glob.glob(os.path.join(tpl_dir, "*.png"))):
    t = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    for s in scales:
        tpls.append((os.path.basename(p)[:-4], s, cv2.resize(t, (max(8, int(t.shape[1] * s)), max(8, int(t.shape[0] * s))))))
W, H, FPS = 1920, 1080, 4
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                     stdout=subprocess.PIPE)


def one(item):
    i, fr = item
    out = []
    for name, s, t in tpls:
        sc = cv2.minMaxLoc(cv2.matchTemplate(fr, t, cv2.TM_CCOEFF_NORMED))[1]
        if sc > 0.8:
            out.append((i / FPS, name, s, round(float(sc), 2)))
    return out


# same frames, templates and threshold as before, matched on every core at once (single-threaded it cost ~100 s per
# minute of video; user 2026-10-21: the privacy steps added 10-15 min per video). OpenCV releases the GIL.
from concurrent.futures import ThreadPoolExecutor
cv2.setNumThreads(1)
bad, i, batch = [], 0, []
with ThreadPoolExecutor(min(32, os.cpu_count() or 4)) as ex:
    while True:
        raw = p.stdout.read(W * H)
        if len(raw) == W * H:
            batch.append((i, np.frombuffer(raw, np.uint8).reshape(H, W)))
            i += 1
        if batch and (len(batch) >= 128 or len(raw) < W * H):
            for r in ex.map(one, batch):
                bad.extend(r)
            batch = []
        if len(raw) < W * H:
            break
p.wait()
print(f"final privacy sweep: {i} frames x {len(tpls)} templates, {len(bad)} readable hits")
for b in bad[:20]:
    print(f"  FAIL {int(b[0] // 60)}:{b[0] % 60:05.2f} {b[1]} at scale {b[2]} (match {b[3]})")

# OCR: the user's own addresses / real name (privacy_terms.json) readable anywhere in the picture, in any app
# (the templates above only know Uber Eats screens; user 2026-10-21). 2 fps over the whole frame.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import privacy_ocr  # noqa: E402
terms = privacy_ocr.load_terms()
bad_ocr, k = [], 0
if any(terms[:3]) or terms[3]:
    OF = 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={OF},scale={W}:{H},format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    while True:
        raw = p.stdout.read(W * H)
        if len(raw) < W * H:
            break
        fr = np.frombuffer(raw, np.uint8).reshape(H, W)
        lines_ = privacy_ocr.ocr(fr)
        for what, box in privacy_ocr.private_boxes(lines_, terms, strict=True):
            # a blurred box can still OCR as garbage, but never as the real words: any hit here is readable text
            txt = next((t for t, ws in lines_ if ws and min(w[1] for w in ws) == box[0] and min(w[2] for w in ws) == box[1]), "?")
            bad_ocr.append((k / OF, what, box, txt))
        k += 1
    p.wait()
print(f"final privacy OCR: {k} frames read, {len(bad_ocr)} private-text hits")
for t, what, box, txt in bad_ocr[:20]:
    print(f"  FAIL {int(t // 60)}:{t % 60:05.2f} {what} READABLE at x={box[0]} y={box[1]}: \"{txt}\"")
sys.exit(1 if bad or bad_ocr else 0)
