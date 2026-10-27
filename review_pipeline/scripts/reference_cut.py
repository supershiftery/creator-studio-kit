"""His PUBLISHED edit of the same recording is the answer key (ultimate dhgate free reselling spreadsheet 2026-10-23, 2:15:
"I mentioned a bunch of spreadsheets ... shoes bags watches ... it kind of cut. We might want to study the actual video,
this might be smarter. I want to drop a link here so you can actually study it"). Older back-catalog videos were already
edited and uploaded; when he gives the YouTube link (raw/reference.txt, or a youtube link in the Studio notes), the
video's subtitles are aligned word by word against the raw transcript:
  - a stretch his edit kept but ours cut (>= MIN_RUN words in a row) is put back (the trimmer had dropped 114 s of the
    spreadsheet-columns walkthrough after a spoken "cut it out there");
  - a word ours kept at a clip EDGE that his edit doesn't have is cut ("I'm actually able to do it and Pretty | Pretty much
    in the membership", 1:40: "it cuts itself off").
Monotonic alignment (numpy DP): matching words in a row cost 0, skipping a subtitle word costs 1, jumping over raw words
(a cut) costs JUMP, so it prefers whole takes; among identical takes the LATER one wins (his rule: the last clean take).
The intro VO isn't in the recording: its subtitle words just get skipped.

    ranges = reference_ranges(project, words)  -> {"keep": [(s, e)...], "cut": [(s, e)...]} in source seconds (cached)
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

JUMP = 3.0
MIN_RUN = 4


def _norm(w):
    w = w.lower().replace("’", "'")
    w = re.sub(r"[^a-z0-9']", "", w)
    return {"gonna": "going", "wanna": "want", "cuz": "because", "ok": "okay"}.get(w, w)


def _same(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    a2, b2 = a.rstrip("s").replace("'", ""), b.rstrip("s").replace("'", "")
    if a2 == b2:
        return True
    return len(a2) >= 5 and len(b2) >= 5 and a2[:5] == b2[:5]


def reference_url(project):
    f = project / "raw" / "reference.txt"
    if f.exists():
        m = re.search(r"https?://\S+", f.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(0)
    try:   # a YouTube link he dropped in the Studio notes
        doc = json.loads((project / "studio.json").read_text(encoding="utf-8-sig"))
        for n in doc.get("notes", []):
            m = re.search(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+", n.get("text", ""))
            if m:
                return m.group(0)
    except (OSError, ValueError):
        pass
    return None


def subtitle_words(project, url):
    """Word list from YouTube's English (auto) subtitles, de-duplicated (auto subs repeat each line twice)."""
    ref = project / "work" / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    srt = next(iter(sorted(ref.glob("*.srt"))), None)
    if srt is None:
        subprocess.run(["yt-dlp", "-q", "--no-playlist", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
                        "--convert-subs", "srt", "-o", str(ref / "ref.%(ext)s"), url], capture_output=True, text=True, timeout=300)
        srt = next(iter(sorted(ref.glob("*.srt"))), None)
    if srt is None:
        return []
    seen, words = set(), []
    for block in srt.read_text(encoding="utf-8", errors="ignore").strip().split("\n\n"):
        lines = [x.strip() for x in block.split("\n")]
        if len(lines) < 3:
            continue
        txt = [x for x in lines[2:] if x]
        if not txt or txt[-1] in seen:
            continue
        seen.add(txt[-1])
        words += [w for w in (_norm(x) for x in re.sub(r"\[.*?\]", " ", txt[-1]).split()) if w]
    return words


def align(ref, raw):
    """ref, raw: normalised word lists. Returns {raw index: ref index} of matched words."""
    n, m = len(ref), len(raw)
    INF = 1e9
    C = np.full(m + 1, INF)
    C[0] = 0.0
    C[1:] = JUMP          # alignment may start anywhere in the recording: one jump
    C[0] = 0.0
    back = np.zeros((n + 1, m + 1), np.int8)      # 0 = skip ref word, 1 = contiguous match, 2 = jump then match
    jfrom = np.zeros((n + 1, m + 1), np.int32)
    cache = {}
    idx = np.arange(m + 1)
    for i in range(1, n + 1):
        w = ref[i - 1]
        if w not in cache:
            cache[w] = np.array([_same(w, r) for r in raw], bool)
        match = cache[w]                                                # match[j-1]: ref i-1 == raw j-1
        prev = C
        new = prev + 1.0                                                # skip the subtitle word
        b = np.zeros(m + 1, np.int8)
        cont = np.full(m + 1, INF)
        cont[1:] = np.where(match, prev[:-1], INF)                      # raw j-1 right after the last match
        better = cont < new
        new = np.where(better, cont, new)
        b[better] = 1
        # jump: best prev[k] for k < j-1, the LATEST such k on ties (= the later take)
        pm = np.minimum.accumulate(prev)
        arg = np.maximum.accumulate(np.where(prev <= pm, idx, 0)).astype(np.int32)
        jump = np.full(m + 1, INF)
        jump[2:] = np.where(match[1:], pm[:-2] + JUMP, INF)
        bj = jump < new
        new = np.where(bj, jump, new)
        b[bj] = 2
        jf = np.zeros(m + 1, np.int32)
        jf[2:] = arg[:-2]
        back[i], jfrom[i] = b, jf
        C = new
    # end anywhere: best final column
    j = int(len(C) - 1 - np.argmin(C[::-1]))
    pairs = {}
    for i in range(n, 0, -1):
        b = back[i][j]
        if b == 0:
            continue
        pairs[j - 1] = i - 1
        j = j - 1 if b == 1 else int(jfrom[i][j])
    return pairs


def reference_ranges(project, words, kept, checks):
    """keep / cut source ranges from his published edit; {} when there is no reference."""
    work = project / "work"
    cache = work / "reference_cut.json"
    url = reference_url(project)
    if not url:
        return {}
    d = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if d.get("url") == url and d.get("n_words") == len(words) and "pairs" in d:
        pairs = {int(k): v for k, v in d["pairs"].items()}
        ref = d["ref"]
    else:
        ref = subtitle_words(project, url)
        if len(ref) < 50:
            checks.append(f"Reference video {url}: no usable subtitles, its edit was not compared.")
            return {}
        pairs = align(ref, [_norm(w["w"]) for w in words])
    matched = np.zeros(len(words), bool)
    matched[list(pairs)] = True
    mid = lambda k: (words[k]["s"] + words[k]["e"]) / 2

    # runs of matched raw words (consecutive indices) = what his edit plays; runs <= 1.5 s apart join
    runs, i = [], 0
    while i < len(words):
        if matched[i]:
            j = i
            # up to 2 unmatched words inside a passage stay in it (Whisper's "D pop" vs the subtitles' "Depop")
            # ...but a long silence ends a passage even between neighbouring words (s25 ultra: the bulk-buying talk and a
            # sign-off take 7 s later came back as ONE range, 7 s of dead air included)
            while j + 1 < len(words) and words[j + 1]["s"] - words[j]["e"] <= 1.5 and (matched[j + 1] or any(j + g < len(words) and matched[j + g] and
                                                               words[j + g]["s"] - words[j]["e"] <= 1.5 for g in (2, 3))):
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    keep = []
    for i, j in runs:
        ks = [k for k in range(i, j + 1) if matched[k]]
        missing = [k for k in ks if not any(a <= mid(k) <= b for a, b in kept)]
        if len(missing) < MIN_RUN:
            continue
        far = min((min(abs(words[i]["s"] - y), abs(words[j]["e"] - x)) for x, y in kept), default=0)
        # a short run far from everything we kept is a chance match (pre-roll "I'm gonna go over every single" against
        # a line of the intro VO): only whole passages may come back from far away
        # (s25 ultra: "The audio from this is" 6 s from kept footage matched words of a different line and came back as a
        # dangling half sentence: a short run must touch kept footage, <= 1.5 s, to extend it)
        if len(ks) < 8 and far > 1.5:
            continue
        # ...and a short run in the pre-roll before the kept opening is an earlier intro take echoing his intro VO (s25 ultra:
        # "today I'm gonna be going over the" from a dropped take 7 s before "Hey guys")
        if len(ks) < 8 and kept and words[j]["e"] <= kept[0][0]:
            continue
        # a lone word or two cut off from the passage by a long pause is a leftover of another take, not part of it
        # (9:57: "...version | spreadsheet | 3 s | in terms of reselling"): trim edge pieces of <= 2 words behind a pause
        # >= 1 s (a gap, or a word Whisper stretched over it)
        pause = lambda k: words[k + 1]["s"] - words[k]["e"] >= 1.0 or words[k + 1]["e"] - words[k + 1]["s"] >= 1.2
        while j - i >= 3 and any(pause(k) for k in range(i, min(i + 2, j))):
            i = next(k for k in range(i, min(i + 2, j)) if pause(k)) + 1
        while j - i >= 3 and any(pause(k) for k in range(max(i, j - 2), j)):
            j = next(k for k in range(j - 1, max(i, j - 2) - 1, -1) if pause(k))
        # a first word stretched over the pause starts from its last 0.5 s (air_guard then finds the real onset)
        s0 = words[i]["e"] - 0.5 if words[i]["e"] - words[i]["s"] > 0.8 else words[i]["s"]
        keep.append((round(s0, 3), round(words[j]["e"], 3)))
    try:
        his_cuts = [tuple(x) for x in json.loads((project / "raw" / "extra_cuts.json").read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        his_cuts = []
    cut = unplayed(words, kept, keep, pairs, ref, matched, his_cuts)   # (edge words are trimmed AFTER the cut guards: trim_edges())
    d = {"url": url, "n_words": len(words), "matched": int(matched.sum()), "ref_words": len(ref),
         "keep": keep, "cut": cut, "ref": ref, "pairs": {str(k): int(v) for k, v in pairs.items()}}
    cache.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d


CUT_MIN_WORDS = 8


def unplayed(words, kept, keep, pairs, ref, matched, his_cuts=()):
    """Passages OURS plays that his published edit never plays (s25 ultra 2026-10-23: he gave the link "for reference"; the
    draft kept the pen fragments, the Wi-Fi setup, a 0:42-0:49 aside, a whole run-back walkthrough, all absent from his
    upload). A run of >= CUT_MIN_WORDS kept words with no subtitle match (cuts in between don't break it, a matched word
    does) is cut when its content is not in his edit at all (< 30 % of its word triples appear in the subtitles), or when
    it is there but through ANOTHER take that also plays (the same line twice). Short runs (a stutter, one Whisper-garbled
    sentence: "They did they did decide the double boxes" never matched the subtitles) are left to the trimmer."""
    mid = lambda k: (words[k]["s"] + words[k]["e"]) / 2
    # ...and what HE cut (raw/extra_cuts) doesn't play: s25 round 2 cut the sign-off take his upload used, and the other
    # take was still cut here as its "duplicate", so the video lost the sign-off line altogether
    plays = lambda k: any(a <= mid(k) <= b for a, b in list(kept) + list(keep)) and not any(a <= mid(k) <= b for a, b in his_cuts)
    idx = [k for k in range(len(words)) if plays(k)]
    tri = lambda seq: {tuple(seq[i:i + 3]) for i in range(len(seq) - 2)}
    ref_tri = {}
    for i in range(len(ref) - 2):
        ref_tri.setdefault(tuple(ref[i:i + 3]), []).append(i)
    inv = {}
    for r, q in pairs.items():
        inv.setdefault(q, []).append(r)
    out, run = [], []
    for k in idx + [None]:
        if k is not None and not matched[k]:
            run.append(k)
            continue
        if len(run) >= CUT_MIN_WORDS and words[run[-1]]["e"] - words[run[0]]["s"] >= 2.0:
            seq = [_norm(words[x]["w"]) for x in run]
            ts = tri(seq)
            hit = [t for t in ts if t in ref_tri]
            share = len(hit) / max(1, len(ts))
            dup = False
            if share >= 0.3:   # in his edit, but from another take: is that take playing too?
                others = {r for t in hit for q in ref_tri[t] for d in range(3) for r in inv.get(q + d, [])}
                dup = any(plays(r) for r in others if r not in run)
            if share < 0.3 or dup:
                out.append((round(words[run[0]]["s"] - 0.05, 3), round(words[run[-1]]["e"] + 0.05, 3)))
        run = []
    return out


def _levels(mic_path):
    import wave
    w = wave.open(str(mic_path))
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    n = int(0.02 * sr)
    lv = 20 * np.log10(np.sqrt((a[: len(a) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)
    return lv   # one value per 20 ms


def trim_edges(d, words, kept, mic_path, checks, max_words=3):
    """After every cut guard (word_guard runs an end inside a word on to the phrase end, which put the cut "Pretty" back
    at 1:40): words at a clip EDGE that his published edit does not play there are trimmed, but only when his edit goes
    straight from the matched word before them to the matched word after them ("but you can | trust you", where his edit
    used the other take's "but you could", keeps its words). The new edge sits on the quietest 20 ms between the words,
    measured, not on Whisper's times."""
    if not d or "pairs" not in d:
        return kept
    pairs = {int(k): v for k, v in d["pairs"].items()}
    ref = d["ref"]
    matched = np.zeros(len(words), bool)
    matched[list(pairs)] = True
    try:
        lv = _levels(mic_path)
    except Exception:
        return kept
    mid = lambda k: (words[k]["s"] + words[k]["e"]) / 2

    def dip(lo, hi):
        i0, i1 = max(0, int(lo / 0.02)), min(len(lv) - 1, int(hi / 0.02))
        if i1 <= i0:
            return None
        k = i0 + int(np.argmin(lv[i0:i1 + 1]))
        # a real gap only: connected speech has no quiet between the words, and a cut there leaves half a word ("these"
        # tail at 2:18, "n" of "In" at 2:41 that sounded like a second "and"): then the word stays
        return k * 0.02 + 0.01 if lv[k] < -40 else None

    play = list(dict.fromkeys(k for a, b in kept for k in range(len(words)) if a <= mid(k) <= b))
    pos = {k: n for n, k in enumerate(play)}
    out, done = [], []
    for a, b in kept:
        idx = [k for k in play if a <= mid(k) <= b]
        na, nb = a, b
        for start_side, seq in ((True, idx), (False, idx[::-1])):
            run = []
            for k in seq:
                if matched[k]:
                    break
                run.append(k)
            if not (0 < len(run) <= max_words and len(run) < len(idx)):
                continue
            ks = sorted(run, key=lambda k: pos[k])
            before = [k for k in play[:pos[ks[0]]] if matched[k]]
            after = [k for k in play[pos[ks[-1]] + 1:] if matched[k]]
            if not before or not after:
                continue
            p, q = pairs[before[-1]], pairs[after[0]]
            if not (1 <= q - p <= 2 and not any(_same(x, _norm(words[k]["w"])) for x in ref[p + 1:q] for k in ks)):
                continue
            # only a DOUBLED word left at the edge ("do it and Pretty | Pretty much"): auto subtitles drop or merge short
            # words, so a clean word they don't show is not proof it's extra (s25 ultra: "Sam song" vs the subtitles'
            # "Samsung" and the answer "Yes," were trimmed off "Samsung Galaxy S25 Ultra" / "Yes, it is slow")
            near = [_norm(words[k]["w"]) for k in (play[pos[ks[-1]] + 1:pos[ks[-1]] + 4] if start_side is False
                                                     else play[max(0, pos[ks[0]] - 3):pos[ks[0]]])]
            near += [_norm(words[k]["w"]) for k in (play[max(0, pos[ks[0]] - 3):pos[ks[0]]] if start_side is False
                                                      else play[pos[ks[-1]] + 1:pos[ks[-1]] + 4])]
            if not any(_same(_norm(words[k]["w"]), x) for k in ks for x in near):
                continue
            i0, i1 = min(ks), max(ks)
            if start_side and i1 + 1 < len(words):     # the clip now opens at the dip before the first word it keeps
                c = dip(words[i1]["e"] - 0.15, words[i1 + 1]["s"] + 0.15)
                if c is None:
                    continue
                na = c
            elif not start_side and i0 > 0:             # ...or closes at the dip after the last word it keeps
                c = dip(words[i0 - 1]["e"] - 0.15, words[i0]["s"] + 0.15)
                if c is None:
                    continue
                nb = c
            else:
                continue
            done.append(f"{' '.join(words[k]['w'] for k in ks)} @ {words[i0]['s']:.1f}")
        if nb - na >= 0.5:
            out.append((round(na, 3), round(nb, 3)))
        else:
            out.append((a, b))
    if done:
        checks.append("Edge words his published edit skips, trimmed at the measured gap: " + "; ".join(done) + " (source s).")
    return out
