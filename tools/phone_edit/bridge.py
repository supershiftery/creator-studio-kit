"""Bridge app-mode gaps (user note, Uber Eats v2 5:54): while they read a survey question off the phone the screen barely
changes, so 'phone active' said talk mode and the phone vanished mid-demo. A gap between two app runs becomes app mode when
the phone is visible the whole gap AND (the gap is <= 12 s OR they refer to the screen in it).
Usage: python bridge.py <layout.json> <out_words.json> <phone visibility: raw source.mp4> <cuts.json>"""
import json, re, subprocess, sys
import numpy as np

CUES = ["as you can see", "you can see", "click", "tap", "select", "the following", "question", "here's", "here is", "right here",
        "type in", "this screen", "this tab", "scroll", "open it", "look at"]


def phone_bars(src):
    """Per-second brightness of the phone strip. Depends only on the recording, so it is kept in work/bridge_bars.npy
    (2026-10-24 speed pass: the full decode was ~50 s on every revision of dhgate coupons)."""
    import os
    st = os.stat(src)
    cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(src))), "work", "bridge_bars.npz")
    key = f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime_ns}"
    if os.path.exists(cache):
        try:
            z = np.load(cache)
            if str(z["key"]) == key:
                return z["bars"]
        except Exception:
            pass
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "fps=1,crop=600:1080:1920:0,scale=60:108,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    bars = np.frombuffer(raw, np.uint8).reshape(-1, 108, 60).astype(np.float32).mean(axis=(1, 2))
    if os.path.isdir(os.path.dirname(cache)):
        np.savez(cache, key=np.array(key), bars=bars)
    return bars


def phone_visible_out(src, K):
    bars = phone_bars(src)
    vis, acc = [], 0.0
    for s, e in K:
        for t in np.arange(s, e, 1.0):
            vis.append((acc + t - s, bars[min(int(t), len(bars) - 1)] <= 15))
        acc += e - s
    return vis


def bridge(layout_path, words_path, src, cuts_path):
    import os
    L = json.load(open(layout_path))
    evp = os.path.join(os.path.dirname(layout_path), "graphics", "events.json")
    wipes = [e["t"] + 0.35 for e in json.load(open(evp)) if e["kind"] == "wipe"] if os.path.exists(evp) else []
    ow = json.load(open(words_path))
    vis = phone_visible_out(src, json.load(open(cuts_path))["keep"])
    text = lambda a, b: " ".join(re.sub(r"[^a-z' ]", "", w["w"].lower()) for w in ow if a <= w["o"] < b)
    app = sorted(L["app"])
    out, bridged = [app[0]] if app else [], []
    for a, b in app[1:]:
        g0, g1 = out[-1][1], a
        seen = [v for t, v in vis if g0 <= t <= g1]
        visible = bool(seen) and all(seen)
        cue = any(c in text(g0, g1) for c in CUES)
        side = any(s0 < g1 and s1 > g0 for s0, s1 in L.get("side", []))
        crosses_section = any(g0 - 3 <= w <= g1 + 1 for w in wipes)  # section intros are talked to camera
        if visible and not side and not crosses_section and (g1 - g0 <= 12 or (cue and g1 - g0 <= 25)):
            bridged.append((round(g0, 2), round(g1, 2)))
            out[-1][1] = b
        else:
            out.append([a, b])
    L["app"] = out
    json.dump(L, open(layout_path, "w"), indent=1)
    print(f"bridged {len(bridged)} gaps: {bridged}; app runs {len(app)} -> {len(out)}")


if __name__ == "__main__":
    bridge(*sys.argv[1:5])
