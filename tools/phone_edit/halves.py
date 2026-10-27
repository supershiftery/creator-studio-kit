"""What each half of the 3840x1080 OBS capture shows, second by second: "cam" (a face), "phone" (the phone mirror: a
bright column between black bars) or "screen" (a website / desktop). Recordings switch layouts per section (Shein
2026-10-21: website left + face cam right, then face cam left + phone right; Doordash: website left for a minute), so
layout, privacy and the compositor read this instead of assuming webcam-left / phone-right.
Usage: python halves.py <source.mp4> <out work/halves.json>     -> {"fps": 1, "left": [...], "right": [...]}"""
import json, subprocess, sys
import numpy as np

FACE_MODEL = r"{{KIT}}/review_pipeline/models/face_landmarker.task"
W, H = 480, 270  # each half, downscaled


def classify(src, fps=1):
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    L = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=FACE_MODEL), num_faces=1, min_face_detection_confidence=0.5))
    # neighbor scaling keeps the camera's sensor noise (averaging would make camera pixels look flat like a web page)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},scale={2 * W}:{H}:flags=neighbor", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    out = {"fps": fps, "left": [], "right": []}
    while True:
        b = p.stdout.read(2 * W * H * 3)
        if len(b) < 2 * W * H * 3:
            break
        fr = np.frombuffer(b, np.uint8).reshape(H, 2 * W, 3)
        for side, half in (("left", fr[:, :W]), ("right", fr[:, W:])):
            out[side].append(kind(half, L, mp))
    p.wait()
    return out


def kind(half, L, mp):
    g = half.mean(axis=2)
    cols = (g > 12).mean(axis=0)  # share of lit pixels per column
    lit = np.where(cols > 0.3)[0]
    # phone mirror: one lit band of 15-45 % of the width, black on both sides
    if len(lit) and 0.12 < (lit[-1] - lit[0] + 1) / W < 0.45 and cols[:lit[0]].mean() < 0.05 and cols[lit[-1] + 1:].mean() < 0.05:
        return "phone"
    # a web page / desktop has large areas of EXACTLY one colour; a camera never does (sensor noise), even when the face
    # is turned away or looking down at the phone (the face test alone flipped the Shein webcam to "screen" all the time)
    if flat_share(g) > 0.12:
        return "screen"
    r = L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(half)))
    return "cam" if r.face_landmarks or flat_share(g) < 0.03 else "screen"


def flat_share(g, b=6):
    h, w = (g.shape[0] // b) * b, (g.shape[1] // b) * b
    blocks = g[:h, :w].reshape(h // b, b, w // b, b).transpose(0, 2, 1, 3).reshape(-1, b * b)
    return float((blocks.std(axis=1) < 0.5).mean())


def smooth(seq, k=2):
    """majority over +-k seconds (a face missed for one frame while looking down stays "cam")"""
    out = []
    for i in range(len(seq)):
        w = seq[max(0, i - k):i + k + 1]
        out.append(max(set(w), key=w.count))
    return out


def load(path):
    d = json.load(open(path))
    return d["fps"], smooth(d["left"]), smooth(d["right"])


if __name__ == "__main__":
    d = classify(sys.argv[1])
    json.dump(d, open(sys.argv[2], "w"))
    for side in ("left", "right"):
        s = smooth(d[side])
        print(side, {k: s.count(k) for k in set(s)})
