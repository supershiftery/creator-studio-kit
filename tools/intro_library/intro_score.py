"""Intro scorecard: measures a rendered intro the way he judges one, against the intros he approved (2026-10-24).

He wants 0 intro revisions. His "boring" notes come down to things a render shows by itself, whatever the template:
  - one shot held too long / the same clip coming back (lv skatesta 2026-10-24: "reusing the same clip over and over
    again, basically spinning it ... lacking movement"),
  - empty frame (dhgate coupons 2026-10-24: "lacking motion and different types of stuff going on"; flat white halves),
  - nothing moving.
Full-frame vs boxed is NOT the deciding thing: lv skatesta was full-frame and boring, the boxed Jordan 3 was approved.

    python intro_score.py <intro.mp4> [--vo-end 24.4] [--json out.json]
    python intro_score.py --calibrate        # the studied set: approved vs boring, prints the table + pass/fail
    from intro_score import score; r = score(mp4, vo_end)   # {"metrics", "problems", "ok"}

Every problem names its time, so the build can fix that shot (intro_check pins) before he sees it.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

FPS = 10
W, H = 192, 108

# Targets from the studied set (calibrate below). Each = (metric, limit, which way is bad, what to tell the fixer).
TARGETS = [
    ("longest_hold", 4.0, "above", "one shot holds {v:.1f} s at {t:.1f}s: split it with a second source (shot length cap)"),
    ("holds_over_3s", 2, "above", "{v:.0f} shots hold longer than 3 s: give those lines a second shot"),
    ("repeat_share", 0.20, "above", "{v:.0%} of the intro is a clip shown before (first repeat at {t:.1f}s): use a new source"),
    ("empty_share", 0.45, "above", "{v:.0%} of the frame is flat empty background on average: fill it (footage full frame / a big graphic)"),
    ("empty_frames", 0.25, "above", "{v:.0%} of frames are more than half empty (worst at {t:.1f}s)"),
    ("still_share", 0.25, "above", "{v:.0%} of frames are near-still: add a glide / push-in"),
    ("shots_per_10s", 3.0, "below", "only {v:.1f} shot changes per 10 s: aim for 3-6"),
]


def _frames(path, t=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path] + (["-t", f"{t:.2f}"] if t else []) + \
          ["-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.float32)


def _thumb(f):
    """16x9 colour thumbnail, brightness-normalised: the 'which clip is this' fingerprint."""
    t = f.reshape(9, H // 9, 16, W // 16, 3).mean(axis=(1, 3))
    return (t - t.mean()) / (t.std() + 1e-3)


def _empty(f):
    """Share of 12x12 blocks that are flat (no detail): plain backgrounds, blank paper, black."""
    g = f.mean(axis=2)
    B = 12
    c = g[:H // B * B, :W // B * B].reshape(H // B, B, W // B, B).std(axis=(1, 3))
    return float((c < 3.0).mean())


def shots_of(F):
    """Shot boundaries: a big change against 0.3 s earlier (survives the 0.3 s dissolves), at least 0.5 s apart."""
    T = np.array([_thumb(f) for f in F])
    lag = 3
    d = np.zeros(len(F))
    for k in range(lag, len(F)):
        d[k] = np.abs(T[k] - T[k - lag]).mean()
    cuts, last = [0], -99
    thr = max(0.55, np.percentile(d, 70))
    for k in range(lag, len(F)):
        if d[k] > thr and d[k] >= d[max(0, k - 2):k + 3].max() and k - last >= 5:
            cuts.append(max(0, k - 1))
            last = k
    cuts.append(len(F))
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1) if cuts[i + 1] - cuts[i] >= 2], T


def score(path, vo_end=None):
    end = vo_end + 0.3 if vo_end else None
    F = _frames(path, end)
    n = len(F)
    if n < 20:
        return {"metrics": {}, "problems": ["render too short to score"], "ok": False}
    dur = n / FPS
    S, T = shots_of(F)
    lens = [(b - a) / FPS for a, b in S]
    # repeats: a shot whose middle looks like an earlier shot that isn't its neighbour (same clip back again)
    mids = [T[(a + b) // 2] for a, b in S]
    rep_secs, first_rep = 0.0, None
    for i in range(len(S)):
        for j in range(i - 1):
            if np.abs(mids[i] - mids[j]).mean() < 0.35:
                rep_secs += lens[i]
                first_rep = first_rep if first_rep is not None else S[i][0] / FPS
                break
    E = np.array([_empty(f) for f in F])
    g = F.mean(axis=3)
    diff = np.r_[np.abs(np.diff(g, axis=0)).mean(axis=(1, 2)), 99]
    longest = int(np.argmax(lens))
    m = {
        "dur": round(dur, 1),
        "shots": len(S),
        "shots_per_10s": round(len(S) / dur * 10, 2),
        "median_shot": round(float(np.median(lens)), 2),
        "longest_hold": round(max(lens), 2),
        "longest_at": round(S[longest][0] / FPS, 1),
        "holds_over_3s": int(sum(l > 3.0 for l in lens)),
        "repeat_share": round(rep_secs / dur, 3),
        "first_repeat_at": first_rep,
        "empty_share": round(float(E.mean()), 3),
        "empty_frames": round(float((E > 0.5).mean()), 3),
        "emptiest_at": round(float(np.argmax(E)) / FPS, 1),
        "still_share": round(float((diff < 0.6).mean()), 3),
    }
    at = {"longest_hold": m["longest_at"], "repeat_share": first_rep or 0, "empty_frames": m["emptiest_at"]}
    probs = []
    for k, lim, way, msg in TARGETS:
        v = m[k]
        if (way == "above" and v > lim) or (way == "below" and v < lim):
            probs.append({"metric": k, "value": v, "limit": lim, "t": at.get(k), "say": msg.format(v=v, t=at.get(k) or 0)})
    return {"metrics": m, "problems": probs, "ok": not probs}


# --- calibration: his verdicts on real intros (2026-10-24) ---
AE = "{{PROJECTS_ROOT}}/"
STUDY = [
    # (label, path, verdict) verdict: good = he approved / named it good; bad = he called it boring / repetitive
    ("reselling spreadsheet (best)", AE + "ultimate dhgate free reselling spreadsheet/intro/build/renders/intro.mp4", "good"),
    ("amiri jeans", AE + "amiri jeans dhgate/intro/build/renders/intro.mp4", "good"),
    ("prada cups", AE + "dhgate prada cups/intro/build/renders/intro.mp4", "good"),
    ("rick owens", AE + "dhgate rick owens/intro/build/renders/intro.mp4", "good"),
    ("lv trainer", AE + "lv trainer/intro/build/renders/intro.mp4", "good"),
    ("cartier watch", AE + "dhgate cartier watch/intro/build/renders/intro.mp4", "good"),
    ("top 10 servers", "{{GAMING_ROOT}}/Top 10 Minecraft Servers/Intro/servers-intro-top10-norisers.mp4", "good"),
    ("lv skatesta", AE + "lv skatesta/intro/build/renders/intro.mp4", "bad"),
    ("dhgate coupons (10-24 draft)", AE + "Dhgate coupon codes/edit/intro/renders/intro.mp4", "bad"),
]


def vo_end_of(mp4):
    """The last spoken word from the build's vo-words.json (next to renders/), or intro_end's cache."""
    d = os.path.dirname(os.path.dirname(mp4))
    for p in (os.path.join(d, "vo-words.json"), mp4[:-4] + ".vo-end.json"):
        if os.path.exists(p):
            W_ = json.load(open(p, encoding="utf-8"))
            if isinstance(W_, dict) and "end" in W_:
                return W_["end"]
            W_ = W_ if isinstance(W_, list) else W_.get("words", [])
            if W_:
                return W_[-1]["e"]
    return None


def calibrate():
    keys = ["shots_per_10s", "median_shot", "longest_hold", "holds_over_3s", "repeat_share", "empty_share", "empty_frames", "still_share"]
    print("intro".ljust(30), "verdict", " ".join(k[:12].rjust(12) for k in keys), " score")
    right = 0
    for lab, p, v in STUDY:
        if not os.path.exists(p):
            print(lab.ljust(30), "missing", p)
            continue
        r = score(p, vo_end_of(p))
        m = r["metrics"]
        ok = "PASS" if r["ok"] else "FAIL(" + ",".join(x["metric"] for x in r["problems"]) + ")"
        right += (r["ok"] == (v == "good"))
        print(lab.ljust(30), v.ljust(7), " ".join(str(m.get(k)).rjust(12) for k in keys), " ", ok)
    print(f"agrees with his verdict on {right}/{len(STUDY)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4", nargs="?")
    ap.add_argument("--vo-end", type=float)
    ap.add_argument("--json")
    ap.add_argument("--calibrate", action="store_true")
    a = ap.parse_args()
    if a.calibrate:
        calibrate()
        sys.exit(0)
    r = score(a.mp4, a.vo_end if a.vo_end else vo_end_of(a.mp4))
    print(json.dumps(r["metrics"], indent=1))
    for p in r["problems"]:
        print("  x", p["say"])
    print("PASS" if r["ok"] else "FAIL")
    if a.json:
        json.dump(r, open(a.json, "w", encoding="utf-8"), indent=1)
