"""Shorts Factory, step 1: find the best 18-58 s moments in a finished edit (any video type).
python moments.py <project dir> <render.mp4> <words.json> <cuts.json> <offset_seconds> <out.json> [--n 8]

Works on the EDITED timeline: with a cut list, every raw-recording word is mapped through the kept ranges (+ the intro
length); with cuts "-" the words come from the render itself and are used as they are (the offset only marks the intro
to skip). Either way a moment is always continuous in the render. Scored on:
  - voice energy (render audio, 0.1 s RMS) above the video's own median   (people lean in when you get loud)
  - hype / urgency words ("insane", "free", "wait", "no way", "$25"...)  (the hook)
  - a strong opener (question, "this", "you", a number) vs a weak one ("and", "so", "but", "um")
  - ending on a finished sentence; no window inside the motion intro
Top windows are kept non-overlapping (>= 6 s apart). Output: [{t0, t1, dur, score, hook, text, reasons}]"""
import json
import re
import subprocess
import sys

import numpy as np

proj, video, words_p, cuts_p, offset, out_p = sys.argv[1:7]
offset = float(offset)
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 8
words = json.load(open(words_p, encoding="utf-8-sig")) if words_p and words_p != "-" else []
if isinstance(words, dict):
    words = words.get("words") or []
words = [{"w": w.get("w") or w.get("word", ""), "s": float(w.get("s", w.get("start", 0))), "e": float(w.get("e", w.get("end", 0)))} for w in words]
keep = []
if cuts_p and cuts_p != "-":
    try:
        cd = json.load(open(cuts_p, encoding="utf-8-sig"))
        keep = [tuple(x[:2]) for x in ((cd.get("keep") or cd.get("kept") or []) if isinstance(cd, dict) else cd)]
    except Exception:
        keep = []


def to_out(t):
    if not keep:
        return t   # no cut list: the words were transcribed from the render itself, so they are already render time (offset = intro to skip)
    acc = offset
    for a, b in keep:
        if t < a - 0.02:
            return None
        if t <= b + 0.02:
            return acc + max(0.0, t - a)
        acc += b - a
    return None


ow = []
for w in words:
    s, e = to_out(w["s"]), to_out(w["e"])
    if s is None or e is None or e < s:
        continue
    ow.append({"w": w["w"], "s": s, "e": e})
if len(ow) < 30:
    json.dump([], open(out_p, "w"))
    sys.exit("not enough transcript in the edit")
# audio energy of the render
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
hop = 800
env = 20 * np.log10(np.sqrt(np.convolve(a ** 2, np.ones(hop) / hop, "same")[::hop]) + 1e-6) if len(a) else np.zeros(1)
loud = env[env > -50]
med = float(np.median(loud)) if len(loud) else -30.0


def energy(t0, t1):
    seg = env[int(t0 * 10):max(int(t1 * 10), int(t0 * 10) + 1)]
    seg = seg[seg > -50]
    return float(np.percentile(seg, 80) - med) if len(seg) else -5.0


HYPE = re.compile(r"^(insane|crazy|wild|free|best|biggest|huge|massive|wow|whoa|epic|literally|secret|hack|cheap|money|cash|code|promo|discount|off|win|broken|op|legendary|rare|first|only|never|worst|scam|fake|real|wait|no|stop|look|watch|bro|dude|omg)$", re.I)
WEAK = re.compile(r"^(and|so|but|um|uh|like|then|also|or|because|anyway|anyways|okay|ok)$", re.I)
STRONG = re.compile(r"^(this|these|you|your|if|why|how|what|imagine|here|never|stop|watch|look|wait|did|do|the|number|\$?\d)", re.I)
# sentences
sents, cur = [], []
for i, w in enumerate(ow):
    cur.append(w)
    gap = ow[i + 1]["s"] - w["e"] if i + 1 < len(ow) else 9
    if w["w"].rstrip().endswith((".", "!", "?")) or gap > 0.8:
        sents.append(cur)
        cur = []
if cur:
    sents.append(cur)
cands = []
MIN, MAX, TARGET = 18.0, 58.0, 32.0
for i, s0 in enumerate(sents):
    t0 = s0[0]["s"]
    if t0 < offset + 1.0:
        continue
    first = re.sub(r"[^\w$]", "", s0[0]["w"])
    for j in range(i, min(i + 14, len(sents))):
        t1 = sents[j][-1]["e"]
        d = t1 - t0
        if d > MAX:
            break
        if d < MIN:
            continue
        ws = [w for k in range(i, j + 1) for w in sents[k]]
        text = " ".join(w["w"] for w in ws)
        hype = sum(1 for w in ws if HYPE.match(re.sub(r"[^\w$]", "", w["w"])) or "$" in w["w"])
        hook = " ".join(w["w"] for w in s0)
        reasons = []
        sc = 0.0
        en = energy(t0, t1)
        sc += en * 0.8
        if en > 3:
            reasons.append(f"loud +{en:.0f} dB")
        sc += min(hype, 6) * 1.2
        if hype:
            reasons.append(f"{hype} hype words")
        if WEAK.match(first):
            sc -= 3
        elif STRONG.match(first) or s0[-1]["w"].endswith("?"):
            sc += 2
            reasons.append("strong opener")
        if sents[j][-1]["w"].rstrip().endswith((".", "!", "?")):
            sc += 1
        sc -= abs(d - TARGET) / 10.0
        wpm = len(ws) / (d / 60)
        if wpm < 110:
            sc -= 2   # slow / lots of silence
        cands.append({"t0": round(t0 - 0.12, 2), "t1": round(t1 + 0.3, 2), "dur": round(d + 0.42, 1), "score": round(sc, 2), "hook": hook[:140],
                      "text": text[:900], "reasons": reasons})
cands.sort(key=lambda c: -c["score"])
picked = []
for c in cands:
    if all(c["t1"] + 6 < p["t0"] or c["t0"] > p["t1"] + 6 for p in picked):
        picked.append(c)
    if len(picked) >= N:
        break
picked.sort(key=lambda c: c["t0"])
for k, c in enumerate(picked, 1):
    c["n"] = k
json.dump(picked, open(out_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"{len(picked)} moments from {len(cands)} windows")
for c in picked:
    print(f"  {c['t0']:7.1f}-{c['t1']:7.1f}  {c['score']:5.1f}  {c['hook'][:70]}")
