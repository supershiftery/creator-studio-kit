"""Repeats you can only HEAR in the edit (s25 ultra 2026-10-23, round 2: "I said obviously twice", "3:15 'the phone, I'm
actually' ... 3:17 was the right take but you left the bad take in", "7:04 'but anyways guys that's pretty' ... we don't
want multiple takes of the same one"). The full-recording Whisper pass folds a restarted opener into one stretched word
("audio" 1491.3-1494.7 hid a second "obviously"), and a sign-off put back by one guard and another take kept by a second
guard only meet once the kept clips play back to back. So the kept audio is cut together exactly as it will play and
transcribed again; then:
  - the same 1-3 words twice in a row ("obviously, obviously", "I'm actually I'm actually", "in order in order") -> the
    first try goes (from its start to the start of the second); "very very", "really really" are how he talks;
  - the same >= 8-word line twice within 20 s of the edit ("but anyways guys that's pretty much it for today's video" x2)
    -> the first one goes (his rule: the last clean take).
    cuts = find_repeats(project, cam, kept, fps, checks) -> [(s, e)] source seconds
Cached in work/repeat_guard.json by the kept ranges.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

VERSION = 9   # 9: lead before the word; 8: cut end may move forward to the pause; 7: cuts run across joins; 6: holes heard in 3 windows; 5: no sentence end inside a restart phrase; 4: restarts need >= 4 words, no capitalised word between (top 5 products, regress); 3: "one to one | One" pair ends are not doubles (canada goose jacket); 2: holes re-heard with medium.en + 3-6 word restarts (top 5 products to resell in winter 2024)
TRAIL = {"the", "a", "an", "to", "of", "my", "in", "for", "and", "with", "your", "this", "that", "is", "on", "at", "it"}
MIN_LINE = 8   # 5 matched stock phrases in different lines ("we're gonna go ahead and", "at the end of the day")
PAIR_JOIN = {"to", "by", "on", "after", "for", "and", "or", "in", "over"}  # one to one, side by side, back to back
OK_DOUBLES = {"very", "really", "bye", "no", "yeah", "so", "ha", "go", "had", "that", "is", "much", "far", "too"}


def _n(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def _map(kept, fps):
    """output-time -> source-time through the frame-accurate clip lengths the render uses."""
    import math
    segs, acc = [], 0.0
    for a, b in kept:
        f0, f1 = math.ceil(round(a, 3) * fps - 1e-6), math.floor(round(b, 3) * fps + 1e-6)
        ln = max(0, f1 - f0 + 1) / fps
        segs.append((acc, acc + ln, f0 / fps))
        acc += ln

    def to_src(t):
        for o0, o1, fa in segs:
            if o0 <= t < o1:
                return fa + (t - o0)
        return None
    return to_src


def _on_quiet(project, kept, found, quiet_db=-42.0, win=0.02, reach=0.6):
    """the cut edges come from Whisper times on the JOINED audio (+-0.3 s): put them on measured quiet in work/mic16k.wav
    (lv skatesta 2026-10-24: a start 0.17 s before a clip end cut the "x" of "easy to go in and fi|x" when the first try of
    "on the bottom of the shoe" opened the next clip; an end inside "I wi|ll" left "will try" and air_guard then cut that
    sliver too). Start on loud audio -> forward to the next quiet (no quiet before its clip end = the cut starts at the
    join); end on loud audio -> back to the quiet before the word (not before its clip start)."""
    import wave
    try:
        w = wave.open(str(project / "work" / "mic16k.wav"))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return found
    n = int(win * sr)

    def db(t):
        x = a[max(0, int(t * sr)):max(0, int(t * sr)) + n]
        return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) if len(x) else -99.0

    def quiet_at(t):   # 3 windows (60 ms) of quiet from t on
        return all(db(t + k * win) < quiet_db for k in range(3))

    clip = lambda t: next(((x, y) for x, y in kept if x - 1e-3 <= t <= y + 1e-3), None)
    try:   # word starts of the recording: a cut that starts ON a word onset in connected speech has no quiet before it
        starts = [w["s"] for w in json.loads((project / "work" / "transcript.json").read_text(encoding="utf-8"))]
    except (OSError, ValueError, KeyError):
        starts = []
    out = []
    for s0, s1, why in found:
        c0 = clip(s0)
        # the doubled word begins right here ("do it and | Pretty | Pretty much": a 0.08 s sliver of "Pretty" at the clip end,
        # no pause before it in "and Pretty"): cut from its start (regress 2026-10-24, reselling spreadsheet 3:15)
        onset = next((x for x in starts if abs(x - s0) <= 0.1 and c0 and c0[0] <= x <= c0[1]), None)
        if onset is not None and c0 and c0[1] - onset <= 0.3:
            s0 = onset
        elif c0 and not quiet_at(s0 - 3 * win):
            # just after the onset of the repeated word (<= 0.15 s): back to the quiet before it; deeper in the sound it is
            # the previous word's ending: forward past it
            back = next((s0 - k * win for k in range(1, 8) if s0 - k * win >= c0[0] and quiet_at(s0 - k * win - 3 * win)), None)
            if back is not None:
                s0 = back
            else:
                t = s0
                while t < min(c0[1], s0 + reach) and not quiet_at(t):
                    t += win
                s0 = t if t < c0[1] and quiet_at(t) else c0[1]
        c1 = clip(s1)
        if c1 and abs(s1 - c1[1]) > 1e-3 and not quiet_at(s1 - 3 * win):   # a cut to the clip's own end stays there
            t = s1
            while t > max(c1[0], s1 - reach, s0) and not quiet_at(t - 3 * win):
                t -= win
            if t > c1[0] and quiet_at(t - 3 * win):
                s1 = t
            else:
                # no pause behind it: the pause just AHEAD (medium.en starts the second try's first word early, inside the
                # trailing "the..." of the first try, top 5 products 0:54): the cut ends where that pause ends
                f = s1
                while f < min(c1[1], s1 + reach) and not quiet_at(f):
                    f += win
                if f < c1[1] and quiet_at(f):
                    while f < c1[1] and quiet_at(f + win):
                        f += win
                    s1 = max(s1, f - 0.04)   # a breath of lead before the word
                else:
                    s1 = c1[0]
        if s1 > s0:
            out.append((round(s0, 3), round(s1, 3), why))
    return out


def _reheard(x, ws, checks, sr=16000, min_gap=1.0, voiced_db=-38.0, share=0.3, ctx=1.5):
    """small.en swallows a restarted phrase whole: "In order to | get" with 1.9 s of SPEECH between "to" and "get" (top 5
    products to resell in winter 2024: both doubles the user heard sat in such holes). A gap between two words >= min_gap
    with >= share of its 20 ms windows voiced is heard again with medium.en, with ctx s around it, and its words replace
    the stretch."""
    n = int(0.02 * sr)
    holes = []
    for a, b in zip(ws, ws[1:]):
        # Whisper stretches the word before the hole over it ("to" 27.5-29.3): measure from 0.4 s into that word
        g0 = min(a["e"], a["s"] + 0.4)
        if b["s"] - g0 >= min_gap:
            seg = x[int(g0 * sr):int(b["s"] * sr)]
            if len(seg) >= n:
                lv = 20 * np.log10(np.sqrt((seg[: len(seg) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)
                if (lv > voiced_db).mean() >= share:
                    holes.append((max(0.0, a["s"] - ctx), b["e"] + ctx))
    if not holes:
        return ws
    from whisper_gpu import load
    model, _ = load("medium.en")
    fixed = 0
    for t0, t1 in holes:
        # medium.en answers differently per window (the 26.0-31.0 window swallowed "in order to get to the" again, 26.0-30.9
        # heard it): three windows, the fullest answer counts
        # every window is judged on the same core (the hole + 0.4 s each side), only the core is replaced
        c0, c1 = t0 + ctx - 0.4, t1 - ctx + 0.4
        new = []
        for w0, w1 in ((t0, t1), (t0 + 0.5, t1 - 0.4), (c0 - 0.3, c1 + 0.3)):
            w0 = max(0.0, w0)
            segs, _ = model.transcribe(x[int(w0 * sr):int(w1 * sr)], word_timestamps=True, condition_on_previous_text=False,
                                       vad_filter=False)
            got = [{"w": w.word.strip(), "s": w0 + float(w.start), "e": w0 + float(w.end)} for sg in segs for w in sg.words]
            got = [w for w in got if c0 <= w["s"] < c1]
            if len(got) > len(new):
                new = got
        t0, t1 = c0 - 0.2, c1 + 0.2      # (the test below keeps its +-0.2 s margins)
        inside = [w for w in ws if t0 <= w["s"] < t1]
        if len(new) > len([w for w in inside if t0 + 0.2 <= w["s"] <= t1 - 0.2]):
            ws = [w for w in ws if not (t0 + 0.2 <= w["s"] <= t1 - 0.2)] + new
            ws.sort(key=lambda w: w["s"])
            fixed += 1
    if fixed:
        checks.append(f"Repeat guard: {fixed} stretch(es) where the quick transcript skipped speech were heard again (medium.en).")
    return ws


def find_repeats(project, cam, kept, fps, checks, window=20.0):
    work = project / "work"
    cache = work / "repeat_guard.json"
    key = [[round(a, 3), round(b, 3)] for a, b in kept]
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("kept") == key and d.get("v") == VERSION:
            if d["cuts"]:
                checks.append("Repeat guard (cached): cut the first try of " + "; ".join(d.get("why", [])) + ".")
            # caches from before _on_quiet get their edges put on quiet too (already-quiet edges stay where they are)
            return [(a, b) for a, b, _ in _on_quiet(project, kept, [(x[0], x[1], "") for x in d["cuts"]])]
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in kept)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(cam), "-vn", "-af", f"aselect='{sel}',asetpts=N/SR/TB",
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    sys.path.insert(0, r"{{KIT}}/tools")
    from whisper_gpu import load
    model, _ = load("small.en")
    segs, _ = model.transcribe(x, word_timestamps=True, condition_on_previous_text=False, vad_filter=False)
    ws = [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for sg in segs for w in sg.words]
    ws = _reheard(x, ws, checks)
    to_src = _map(kept, fps)
    n = [_n(w["w"]) for w in ws]
    found, i = [], 0
    while i < len(ws):
        hit = None
        for k in (3, 2, 1):
            if i + 2 * k > len(ws) or not all(n[i:i + 2 * k]):
                continue
            # ...not across a sentence end ("can you resell it? It is on the spreadsheet")
            # ...nor the end of an "X to X" pair ("one to one | One thing I will say", canada goose jacket 2026-10-24:
            # Whisper wrote "one-to" "-one" "One" and the second "One" opened the next sentence; "side by side | side")
            pair_end = "pairend" not in os.environ.get("RG_OFF", "") and k == 1 and (ws[i]["w"].startswith("-") or (i >= 2 and n[i - 2] == n[i] and n[i - 1] in PAIR_JOIN))
            if n[i:i + k] == n[i + k:i + 2 * k] and not (k == 1 and n[i] in OK_DOUBLES) and not pair_end \
                    and not re.search(r"[.?!]$", ws[i + k - 1]["w"]):
                hit = (i, i + k, f"doubled \"{' '.join(w['w'] for w in ws[i:i + k])}\"")
                break
        if hit is None:
            # a restart: the same 3-6 words again after <= 6 abandoned words, no comma / sentence end in between (top 5
            # products to resell in winter 2024, 0:54 "In order to get to the... In order to get to any of the products",
            # 2:13 "just to prove the quality, I decided to get my | just to prove the quality, I did buy three": "I literally
            # said it twice"). A comma in between is a parallel list ("a lot of dads, a lot of moms"), not a restart.
            # 3 words is how he talks ("it still has the rhinestones in it, so it still has attention to detail", sp5der;
            # "down to the mirror jeans ... once you get down to the", amiri): >= 4 words, <= 4 between for 4 words (<= 6 for
            # 5+), and a capitalised word in between (Whisper's sentence start: "So", "Once") ends it ("I drop the new finds
            # every single day. So pretty much like five finds every single day", reselling spreadsheet). All three were
            # approved edits the first version of this rule cut (regress suite).
            for k in (6, 5, 4):
                if hit or i + k > len(ws) or not all(n[i:i + k]):
                    continue
                for j in range(i + k + 1, min(i + k + (5 if k == 4 else 7), len(ws) - k + 1)):
                    # ...anywhere after its first word, and no sentence end inside the phrase either ("day. So" sat INSIDE
                    # the 5-word phrase "finds every single day so")
                    if any((w["w"][:1].isupper() and n[i + 1 + q] != "i") or re.search(r"[.?!]$", w["w"]) and not w["w"].endswith("...")
                           for q, w in enumerate(ws[i + 1:j])):
                        break
                    if ws[j]["s"] - ws[i]["s"] > 7.0:
                        break
                    # "the," / "the..." = trailed off on a function word: still a restart
                    if n[j:j + k] == n[i:i + k] and not any(re.search(r"[,.?!;:]$", w["w"]) and not w["w"].endswith("...")
                                                            and n[ws.index(w)] not in TRAIL for w in ws[i + k - 1:j]):
                        hit = (i, j, f"restart \"{' '.join(w['w'] for w in ws[i:j])}\"")
                        break
        if hit is None:
            # a whole line again: >= 5 words identical, the second start within `window` s
            for j in range(i + 5, len(ws)):
                if ws[j]["s"] - ws[i]["s"] > window:
                    break
                L = 0
                while j + L < len(ws) and i + L < j and n[i + L] and n[i + L] == n[j + L]:
                    L += 1
                if L >= MIN_LINE:
                    hit = (i, j, f"line said twice \"{' '.join(w['w'] for w in ws[i:i + L])}\"")
                    break
        if hit:
            a, b, why = hit
            s0, s1 = to_src(ws[a]["s"] - 0.03), to_src(ws[b]["s"] - 0.06)
            sm = to_src((ws[a]["s"] + ws[a]["e"]) / 2)
            c0 = next(((x0, y) for x0, y in kept if x0 <= (sm if sm is not None else -1) < y), None)
            if c0 and s0 is not None and s0 < c0[0]:
                s0 = c0[0]   # Whisper starts the word early, in the clip before: the try starts with its own clip
            # a second try in a LATER clip: the cut runs across the join (a first try can span it: "In order | to get to
            # the... in order to get to any", top 5 products to resell in winter 2024, 0:54)
            if s0 is not None and s1 is not None and s1 > s0:
                found.append((round(s0, 3), round(s1, 3), why))
            elif s0 is not None:   # the second try opens the next clip: cut the first try to the end of its clip
                e = next((y for x0, y in kept if x0 <= s0 < y), None)
                if e:
                    found.append((round(s0, 3), round(e, 3), why))
            i = b
        else:
            i += 1
    found = _on_quiet(project, kept, found)
    cuts = [(a, b) for a, b, _ in found]
    cache.write_text(json.dumps({"v": VERSION, "kept": key, "cuts": cuts, "why": [w for _, _, w in found],
                                 "words": [[w["w"], round(w["s"], 2)] for w in ws]}, indent=1), encoding="utf-8")
    if found:
        checks.append("Repeat guard (the edit transcribed as it plays): cut the first try of " + "; ".join(
            f"{w} at {a // 60:.0f}:{a % 60:04.1f}" for a, _, w in found) + " (source). Put one back with raw/extra_keeps.json.")
    return cuts
