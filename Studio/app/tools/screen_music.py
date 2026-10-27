"""Phone-style music for screen-recording edits (settings.music_style = "beats"; user 2026-10-23, friend's Chime video:
"I don't want the same music throughout ... play the track, don't loop it, then the next track, or split it by segment").

    plan(words, keep, speed, out_len, work, joins=()) -> [{"s", "e", "track", "ss"}] in EDIT time

- sections: Claude (claude_brain) reads the kept transcript and names where the topic changes
  (cached in work/screen_sections.json); the joins between joined recordings count as section changes too
- music: the approved phone playlist (phone_edit/build_main.py PLAYLIST: whisper-checked, no vocals, no producer tags).
  A new beat starts at a section change once the current one has played 45 s, and always before a beat runs out
  (never looped). Every switch lands on a pause in the voice; trim_render crossfades 1.5 s across it.
- level: like the phone videos, the bed sits 15 LU under the voice (BED -31 vs voice -16)."""
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, r"{{KIT}}/tools")
import claude_brain as B   # noqa: E402

TB = r"{{MUSIC_ROOT}}/Type Beats"
PLAYLIST = [
    f"{TB}/Drake/Drake Type Beat - Family Matters (ECHOBEATS).mp3",
    f"{TB}/Drake/[FREE] DRAKE TYPE BEAT   KENDALL  .mp3",
    f"{TB}/Drake/FREE Drake Type Beat - DoTheMove (Prod. 20).mp3",
    f"{TB}/Drake/Drake x RnB Type Beat - Close To Me (ECHOBEATS).mp3",
]
# "chill" (settings.music_style = "chill", user 2026-10-23 Chime: "add some more chill music"): lo-fi / mellow beds,
# medium.en no-VAD checked: Interstellar Dreams clean (the approved MacBook bed), Autumn Jazz clean (only Whisper's usual
# made-up "see you in the next one" over silence). "Different People" REJECTED: real
# vocal sample. Sits further under the voice than the beats.
LOFI = r"{{MUSIC_ROOT}}/Type Beats/Lo-Fi"
POOLS = {"beats": (PLAYLIST, 15.0),
         # only smooth lo-fi: the type beats were "too hype for a Chime video" (user 2026-10-23), Close To Me too
         "chill": ([f"{LOFI}/Free LoFi Type Beat - Interstellar Dreams.mp3", f"{LOFI}/(FREE) Lo Fi Type Beat -Autumn Jazz.mp3"], 18.0)}
MIN_PART = 45.0   # a beat plays at least this long before a section change may switch it
UNDER_VOICE = 15.0


def usable(track):
    """seconds of real music: the end minus the quiet / fade-out tail (same as phone_edit/build_main.py)"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    db = 20 * np.log10(np.sqrt((a[:len(a) // 4000 * 4000].reshape(-1, 4000) ** 2).mean(1)) + 1e-9)
    on = np.where(db > np.median(db) - 14)[0]
    return (on[-1] + 1) * 0.5 if len(on) else len(a) / 8000


def lufs(path, ss=0.0, t=None, af=""):
    cmd = ["ffmpeg", "-v", "info", "-ss", f"{ss:.3f}"] + (["-t", f"{t:.3f}"] if t else []) + ["-i", str(path), "-af",
                                                                                               (af + "," if af else "") + "ebur128", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else -20.0


def edit_words(words, keep, speed):
    """the transcript words that survive the cut, in edit time"""
    out, acc = [], 0.0
    for s, e in keep:
        for w in words:
            if s <= w["s"] < e:
                out.append({"w": w["w"], "s": (acc + w["s"] - s) / speed, "e": (acc + min(w["e"], e) - s) / speed})
        acc += e - s
    return out


def sentences(W):
    """words -> lines that break on a sentence end or a pause over 0.6 s"""
    lines, cur = [], []
    for i, w in enumerate(W):
        cur.append(w)
        gap = W[i + 1]["s"] - w["e"] if i + 1 < len(W) else 9
        if re.search(r"[.?!]$", w["w"]) or gap > 0.6 or len(cur) > 40:
            lines.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
            cur = []
    return lines


def sections(W, out_len, work, say=print):
    """Claude: where the topic changes (edit-time line starts). Cached by transcript."""
    L = sentences(W)
    cache = os.path.join(work, "screen_sections.json")
    key = hashlib.md5(json.dumps([(round(x["s"], 1), x["text"]) for x in L]).encode()).hexdigest()
    if os.path.exists(cache):
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            return c["sections"]
    text = "\n".join(f"L{i} [{x['s'] // 60:.0f}:{x['s'] % 60:04.1f}] {x['text']}" for i, x in enumerate(L))
    prompt = f"""This is the transcript of a {out_len / 60:.1f}-minute YouTube tutorial (a screen recording, one creator talking).
Split it into its natural SECTIONS, the way chapters would be: where the creator moves to a new topic or step (e.g. intro,
what the offer is, signing up, verifying, the first deposit, getting the bonus, outro). Sections are usually 1-4 minutes;
never under 30 seconds. The first section starts at L0.

TRANSCRIPT (line number, time, words)
{text}

Reply with ONLY JSON: {{"sections":[{{"line":0,"name":"<2-4 words>"}}, ...]}}"""
    ans = B.ask("screen_sections", prompt, model="sonnet", say=say)
    secs = []
    for d in (ans or {}).get("sections") or []:
        try:
            i = int(str(d.get("line")).lstrip("L"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(L):
            secs.append({"t": round(L[i]["s"], 2), "name": str(d.get("name") or "")[:40]})
    secs = sorted({s["t"]: s for s in secs}.values(), key=lambda s: s["t"])
    json.dump({"key": key, "sections": secs}, open(cache, "w", encoding="utf-8"), indent=1)
    say(f"sections (Claude): " + ", ".join(f"{s['t'] // 60:.0f}:{s['t'] % 60:02.0f} {s['name']}" for s in secs))
    return secs


def pause_near(W, t, win=4.0):
    """the middle of the widest gap between words within win s of t (the music switches where nobody talks)"""
    best = None
    for a, b in zip(W, W[1:]):
        g0, g1 = a["e"], b["s"]
        if g1 - g0 >= 0.25 and abs((g0 + g1) / 2 - t) <= win:
            sc = (g1 - g0) - 0.15 * abs((g0 + g1) / 2 - t)
            if best is None or sc > best[0]:
                best = (sc, (g0 + g1) / 2)
    return best[1] if best else t


def plan(words, keep, speed, out_len, work, joins=(), seed=0, say=print, style="beats"):
    W = edit_words(words, keep, speed)
    secs = [s["t"] for s in sections(W, out_len, work, say)] if W else []
    bounds = sorted(set([round(t, 2) for t in secs + list(joins) if 20 < t < out_len - 20]))
    # the WHOLE {{MUSIC_ROOT}} library (user 2026-10-24: "we've been using the same tracks over and over again"; Chime 2026-10-23
    # "too much lo-fi"): music_lib fits beats to the title + transcript ("chill" = calm, lo-fi only one genre among
    # piano / cinematic / jazzy), skips the channel's last 15 videos; a re-render keeps its beats. POOLS = fallback.
    pool, lib = [], None
    try:
        import sys
        sys.path.insert(0, r"{{KIT}}/tools")
        import music_lib as lib
        pool = lib.pick_for(str(work), kind="screen", n=8, style=style, min_len=MIN_PART, role="main",
                            text=" ".join(w.get("w", "") for w in W) if W else None)
    except Exception as e:
        say(f"music_lib skipped: {type(e).__name__}: {str(e)[:160]}")
    if not pool:
        pool = [p for p in POOLS.get(style, POOLS["beats"])[0] if os.path.exists(p)]
        if not pool:
            return []
        pool = pool[seed % len(pool):] + pool[:seed % len(pool)]
    room = {p: usable(p) - 2.0 for p in pool}
    out, t, k = [], 0.0, 0
    while t < out_len - 0.5:
        track = pool[k % len(pool)]
        k += 1
        end_max = t + room[track]
        if end_max >= out_len:
            # the last beat reaches the end; still change at a section when this one has played long enough
            nxt = [b for b in bounds if t + MIN_PART <= b < out_len - MIN_PART * 0.6]
            e = pause_near(W, nxt[0]) if nxt else out_len
        else:
            nxt = [b for b in bounds if t + MIN_PART <= b <= end_max]
            e = pause_near(W, nxt[0]) if nxt else pause_near(W, end_max - 3.0, 3.0)
            e = min(e, end_max)
        if e - t < 5:
            e = min(out_len, t + room[track])
        out.append({"s": round(t, 3), "e": round(e, 3), "track": track})
        t = e
    say("music: " + "; ".join(f"{x['s'] // 60:.0f}:{x['s'] % 60:04.1f}-{x['e'] // 60:.0f}:{x['e'] % 60:04.1f} {os.path.basename(x['track'])[:34]}" for x in out))
    return out
