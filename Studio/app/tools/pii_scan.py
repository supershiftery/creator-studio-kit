"""Generic personal-info scan for screen recordings (user 2026-10-23, a friend's Chime sign-up: the screen-recording edit
has no privacy pass, and the phone pipeline's blur only knows the user's OWN address/name). Reads the render with Windows'
built-in OCR (privacy_ocr.py, local, free) and flags text SHAPED like private info, whoever it belongs to.

    python pii_scan.py <video.mp4> <out.json> [--fps 1] [--from s] [--to s]

out.json: {"hits": [{"t", "kind", "masked", "box": [x, y, w, h]}], "frames": n}. Values are MASKED in the output and the
log (never write someone's SSN into a file or a chat); the box is what a blur would cover."""
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, r"{{KIT}}/tools")
import privacy_ocr as O   # noqa: E402

VERSION = 2   # bump when PATTERNS change: cached scans are redone
STREET = r"(st|street|rd|road|ave|avenue|dr|drive|ln|lane|ct|court|blvd|boulevard|way|pl|place|cir|circle|ter|terrace|pkwy|hwy|apt|unit|suite)"
PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")),
    ("card / account number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("routing / account number", re.compile(r"(?i)\b(routing|account|acct)\b\D{0,20}\d{6,}")),
    ("phone", re.compile(r"(?:\+?1[ .-]?)?\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("street address", re.compile(rf"(?i)\b\d{{2,6}}\s+(?:[a-z0-9]+\s+){{1,3}}{STREET}\b\.?")),
    # grid addresses ("2421 N 400 E", Utah; the Chime video's address was missed by the street-word rule), "Apt N3", ST 12345
    ("street address", re.compile(r"(?i)\b\d{1,6}\s+[NSEW]\.?\s+\d{1,5}\s+[NSEW]\b|\b(apt|unit|suite)\s*#?\s*[a-z]?\d+\b")),
    ("street address", re.compile(r"\b[A-Z]{2},?\s+\d{5}(?:-\d{4})?\b")),   # state + ZIP (capitals only)
    # a long number on its own line (routing number under its label: "Routing number" / "031101279")
    ("routing / account number", re.compile(r"^\s*\d{8,19}\s*$")),
    ("date of birth", re.compile(r"(?i)\b(birth|dob|born)\b.{0,25}\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")),
]


def mask(s):
    return re.sub(r"[0-9]", "#", re.sub(r"(?<=\w)[A-Za-z](?=\w)", "*", s))


def frames(path, fps, t0, t1):
    w, h = 1920, 1080
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0:.2f}"] + (["-to", f"{t1:.2f}"] if t1 else []) + \
          ["-i", path, "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    k = 0
    while True:
        b = p.stdout.read(w * h)
        if len(b) < w * h:
            break
        yield t0 + k / fps, np.frombuffer(b, np.uint8).reshape(h, w)
        k += 1


def scan(path, fps, t0, t1, hits, n=0):
    for t, img in frames(path, fps, t0, t1):
        n += 1
        for text, words in O.ocr(img):
            for kind, rx in PATTERNS:
                m = rx.search(text)
                if not m:
                    continue
                xs = [x for _, x, _, _, _ in words] or [0]
                box = [min(xs), min(y for _, _, y, _, _ in words), max(x + ww for _, x, _, ww, _ in words) - min(xs),
                       max(y + hh for _, _, y, _, hh in words) - min(y for _, _, y, _, _ in words)] if words else [0, 0, 0, 0]
                hits.append({"t": round(t, 2), "kind": kind, "masked": mask(m.group(0)), "box": box})
                break
        if n % 120 == 0:
            print(f"  {t / 60:.0f} min, {n} frames scanned, {len(hits)} hits", flush=True)
    return n


def main():
    path, out = sys.argv[1], sys.argv[2]
    arg = lambda k, d: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    fps, t0, t1 = arg("--fps", 1.0), arg("--from", 0.0), arg("--to", 0.0)
    hits, n = [], 0
    if "--ranges" in sys.argv:
        # only the parts the cut keeps (user 2026-10-23: "cut first, then run the privacy checker, less frames"), and every
        # scanned frame is remembered in <out>: a revision that brings footage back scans only those new seconds
        rj = json.load(open(sys.argv[sys.argv.index("--ranges") + 1], encoding="utf-8"))
        keep = rj["keep"] if isinstance(rj, dict) else rj
        old = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
        if old.get("fps") == fps and old.get("version") == VERSION:
            hits, seen = old.get("hits", []), set(old.get("seen", []))
        else:
            seen = set()
        # 4.5 s before each piece: trim_render's midstart guard may open a piece up to 4 s earlier
        want = sorted({k for s, e in keep for k in range(int((s - 4.5) * fps), int((e + 1.0) * fps) + 1) if k >= 0})
        todo = [k for k in want if k not in seen]
        runs = []
        for k in todo:
            if runs and k == runs[-1][1] + 1:
                runs[-1][1] = k
            else:
                runs.append([k, k])
        print(f"privacy scan: {len(want)} frames in the kept parts, {len(todo)} not scanned yet ({len(runs)} stretches)", flush=True)
        for k0, k1 in runs:
            n = scan(path, fps, k0 / fps, (k1 + 1) / fps, hits, n)
        seen |= set(todo)
        if todo or not os.path.exists(out):   # untouched when nothing new: the render's input stays up to date
            json.dump({"version": VERSION, "fps": fps, "seen": sorted(seen), "hits": hits, "frames": len(seen)}, open(out, "w", encoding="utf-8"))
        # report only what lands in the kept parts
        hits = [h for h in hits if any(s - 4.5 <= h["t"] <= e + 1.0 for s, e in keep)]
    else:
        n = scan(path, fps, t0, t1, hits)
        json.dump({"hits": hits, "frames": n}, open(out, "w", encoding="utf-8"), indent=1)
    kinds = {}
    for h_ in hits:
        kinds.setdefault(h_["kind"], []).append(h_["t"])
    print(f"pii scan: {n} frames scanned now, {len(hits)} hits")
    for k, ts in kinds.items():
        print(f"  {k}: {len(ts)} frames, first at {ts[0] // 60:.0f}:{ts[0] % 60:04.1f}, last at {ts[-1] // 60:.0f}:{ts[-1] % 60:04.1f}")


if __name__ == "__main__":
    main()
