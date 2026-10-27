"""Where does the video really start? (user 2026-10-23, Chime video for a friend: no "hey guys" line, the recording opens
on warm-up talk to the editor, "All right, so this video is going to be about chime. Um, basically it's going to be like
a hundred dollar chime referral bonus... I haven't recorded one of these in a while", then switches into presenter voice:
"It's pretty crazy that if you watch till the end of this video you will get a $300 just for signing up to Chime.")
The friend's editor started the upload on that hook. The switch is heard, not said: the presenter line is LOUDER, more
PITCH-ANIMATED and FASTER than the mumbled warm-up before it.

find_opening(words, wav) -> {"s", "e", "why", "text", "kept"} cut from 0 to the hook, or None.
Only used when there is no greeting ("hey guys" / "hello youtube"); look at lines in the first 150 s, split on >= 1 s
pauses. A line is "on" when its score (z of loudness + pitch spread + word rate vs the first line) clears the bar; the hook
is the first "on" line that is followed by mostly "on" lines (the delivery stays up), and everything before it is
warm-up when the warm-up was clearly flatter."""
import json
import sys
import wave

import numpy as np

SR = 16000


def read_wav(path, t1):
    with wave.open(str(path), "rb") as f:
        sr, ch, n = f.getframerate(), f.getnchannels(), f.getnframes()
        raw = f.readframes(min(n, int(t1 * sr)))
    y = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        y = y.reshape(-1, ch).mean(1)
    return y, sr


def line_stats(y, sr, a, b):
    seg = y[int(a * sr):int(b * sr)]
    hop, win = int(0.02 * sr), int(0.04 * sr)
    if len(seg) < win * 3:
        return None
    frames = np.lib.stride_tricks.sliding_window_view(seg, win)[::hop]
    rms = np.sqrt((frames ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(rms)
    voiced = db > db.max() - 20
    loud = float(np.percentile(db[voiced], 80))
    # pitch per voiced frame: autocorrelation peak in 75-350 Hz
    f0 = []
    lo, hi = int(sr / 350), int(sr / 75)
    for fr in frames[voiced]:
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / ac[0] > 0.45:
            f0.append(sr / k)
    f0 = np.array(f0)
    spread = float((12 * np.log2(f0 / np.median(f0))).std()) if len(f0) > 10 else 0.0
    pitch = float(np.median(f0)) if len(f0) > 10 else 0.0
    return {"loud": loud, "spread": spread, "pitch": pitch}


def lines_of(words, t1=150.0, gap=1.0):
    out, cur = [], []
    for w in words:
        if w["s"] > t1:
            break
        if cur and w["s"] - cur[-1]["e"] >= gap:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def find_opening(words, wav, t1=150.0, verbose=False):
    lines = [ln for ln in lines_of(words, t1) if ln[-1]["e"] - ln[0]["s"] >= 1.0]
    if len(lines) < 3:
        return None
    y, sr = read_wav(wav, t1 + 5)
    rows = []
    for ln in lines:
        a, b = ln[0]["s"], ln[-1]["e"]
        st = line_stats(y, sr, a, b)
        if not st:
            continue
        st.update(s=a, e=b, rate=len(ln) / max(0.5, b - a), text=" ".join(w["w"] for w in ln))
        rows.append(st)
    if len(rows) < 3:
        return None
    base = rows[0]
    for r in rows:
        # dB over the opening line + semitones of pitch (higher, more animated) + word-rate gain, roughly equal weights
        r["score"] = (r["loud"] - base["loud"]) / 2.0 + 12 * np.log2(max(r["pitch"], 1) / max(base["pitch"], 1)) / 2.0 \
            + (r["spread"] - base["spread"]) / 1.0 + (r["rate"] - base["rate"]) / 1.0
        if verbose:
            print(f"  {r['s']:6.1f}-{r['e']:6.1f} loud {r['loud']:6.1f} pitch {r['pitch']:4.0f} spread {r['spread']:4.1f} "
                  f"rate {r['rate']:3.1f} score {r['score']:5.1f} | {r['text'][:60]}")
    ON = 2.5
    for k in range(1, len(rows)):
        nxt = rows[k:k + 4]
        if rows[k]["score"] >= ON and sum(r["score"] >= ON * 0.6 for r in nxt) >= max(2, len(nxt) - 1) \
                and all(r["score"] < ON for r in rows[:k]):
            hook = rows[k]
            return {"s": 0.0, "e": hook["s"], "why": "warm-up before the presenter voice starts (vocal delivery) REVIEW",
                    "text": " ".join(r["text"] for r in rows[:k]), "kept": hook["text"][:80] + " ..."}
    return None


if __name__ == "__main__":
    w = json.load(open(sys.argv[1], encoding="utf-8"))
    w = w["words"] if isinstance(w, dict) else w
    print(find_opening(w, sys.argv[2], verbose=True))
