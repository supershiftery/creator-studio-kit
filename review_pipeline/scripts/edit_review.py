"""Unattended product review edit. Usage: python edit_review.py <project folder> [--fresh] [--broll-plan]

--broll-plan only writes output/broll_requests.md (the B-roll shot list to ask for) and stops.

Steps are cached in <project>/work/*.json and skipped when present (unless --fresh).
All tunables live in config.json next to this file; a project may override any of them in raw/config.json.
"""
import json, math, os, re, shutil, subprocess, sys, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
from transcribe import transcribe  # noqa: E402
from analyze import analyze  # noqa: E402
from cursor import track_cursor, cursor_at  # noqa: E402
import broll  # noqa: E402
import callouts  # noqa: E402
import countdown  # noqa: E402
import audio_mix  # noqa: E402
import xml_cuts  # noqa: E402
import zooms_extra  # noqa: E402
import showing  # noqa: E402
import reference_cut  # noqa: E402
import idle_desk  # noqa: E402
import joins  # noqa: E402
import screen_chrome  # noqa: E402

OUT_W, OUT_H = 1920, 1080
# output frame rate: 60 when his recording is 60 fps (watch spreadsheet 2026-10-24: "it still feels like it's jittering
# ... the clips will basically play and then they'll jump ... this goes for the screen recordings as well": rendering a
# 60 fps screen recording at 30 dropped every other frame, so each mouse-wheel scroll step doubled). Set in main().
FPS = 30


# ---------------------------------------------------------------- helpers
def deep_merge(a, b):
    for k, v in b.items():
        a[k] = deep_merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


def load_json(p, default=None):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else default


def save_json(p, data):
    Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                        "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"], float(d["format"]["duration"])


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def subtract(ranges, cuts):
    """ranges minus cuts, both lists of (a, b)."""
    out = []
    for a, b in ranges:
        segs = [(a, b)]
        for ca, cb in sorted(cuts):
            nxt = []
            for sa, sb in segs:
                if cb <= sa or ca >= sb:
                    nxt.append((sa, sb))
                else:
                    if ca > sa:
                        nxt.append((sa, ca))
                    if cb < sb:
                        nxt.append((cb, sb))
            segs = nxt
        out += segs
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > 0.05]


def _norm(t):
    return re.sub(r"[^a-z0-9']", "", t.lower())


SIGNOFF = ["pretty much it for today", "thats it for today", "that is it for today", "it for todays video", "see you in the next",
           "catch you in the next", "peace out"]


def signoff_guard(kept, words, duration, checks):
    """The sign-off always plays (user 2026-10-22, prada cups 4:25: "I say, that's pretty much it for today's video. You cut
    all of that off"): the AI take review folded the last take of it into a 'shipping times' aside as a 'stray video'.
    The LAST sign-off in the final 25% of the recording is put back from its sentence start (back to a >= 0.35 s pause,
    at most 3 s) to the phrase end, joined to the next kept piece when that starts within 1.5 s."""
    nrm = lambda w: re.sub(r"[^a-z0-9 ]", "", w.lower())
    toks = [nrm(w["w"]) for w in words]
    hit = None
    for i in range(len(words)):
        if words[i]["s"] < duration * 0.75:
            continue
        txt = " ".join(toks[i:i + 6])
        for ph in SIGNOFF:
            if txt.startswith(ph.split()[0]) and ph in txt:
                hit = (i, i + len(ph.split()) - 1)
    if hit is None:
        return kept
    i, j = hit
    while j + 1 < len(words) and words[j + 1]["s"] - words[j]["e"] < 0.35 and not re.search(r"[.!?]$", words[j]["w"]) and j - i < 8:
        j += 1                                            # finish the phrase ("... today's video")
    a = i
    while a > 0 and words[a]["s"] - words[a - 1]["e"] < 0.35 and words[i]["s"] - words[a - 1]["s"] <= 3.0:
        a -= 1                                            # back to the sentence start ("But anyways guys, ...")
    s, e = words[a]["s"] - 0.08, words[j]["e"] + 0.1
    if any(x <= s + 0.3 and e - 0.15 <= y for x, y in kept):   # already plays (a clip edge a breath away is fine)
        return kept
    nxt = next((x for x, y in kept if x >= e - 0.01), None)
    if nxt is not None and nxt - e <= 1.5:
        e = nxt
    merged = []
    for x, y in sorted(kept + [(s, e)]):
        if merged and x <= merged[-1][1] + 0.01:
            merged[-1] = (merged[-1][0], max(merged[-1][1], y))
        else:
            merged.append((x, y))
    checks.append(f"Sign-off put back: '{' '.join(w['w'] for w in words[a:j + 1])}' ({fmt(s)}-{fmt(e)} source) had been cut.")
    return merged


def word_guard(kept, words, checks, named_cuts=(), tail=0.12, max_word=0.8, joined=0.12, max_run=1.6):
    """No kept edge inside a spoken word (dhgate asics 2026-10-22: 'dive right in[to it]' and 'right now [so]' were
    clipped mid-word and he heard it). An end inside a word runs on to the end of that phrase (following words closer
    than `joined`, at most max_run s) + a short tail; a start inside a word moves back to the word's start. Both are
    capped at the neighbouring kept piece. Left alone: words longer than max_word (Whisper stretching a word over a
    pause), words mostly inside the cut, and words a cut names as what it removed (named_cuts: (s, e, text), e.g. the
    false start 'There's') — those are deliberate."""
    out = [list(k) for k in kept]
    fixed = []
    words = sorted((w for w in words if w["e"] - w["s"] <= max_word), key=lambda w: w["s"])

    def named(w):
        # the cut's first word, a word it quotes ("drop 'guys' (stray word before 'hey guys')"), or a word it covers
        # >= 80 %: deliberate (dhgate cartier watch 0:27: a start pulled back into the dropped 'guys' = "hey guys" twice)
        for cs, ce, text in named_cuts:
            quoted = re.findall(r"'([^']+)'", text or "")
            toks = [_norm(x) for x in (text or "").split()[:1]] + ([_norm(quoted[0].split()[0])] if quoted and quoted[0].split() else [])
            if abs(cs - w["s"]) < 0.4 and _norm(w["w"]) in toks:
                return True
            if min(ce, w["e"]) - max(cs, w["s"]) >= 0.8 * (w["e"] - w["s"]):
                return True
        return False

    starts = sorted(cs for cs, ce, text in named_cuts)

    def opens_on(nw, after):
        # a cut that starts inside the word before nw and whose text opens with nw itself
        return any(after <= cs <= nw["s"] + 0.05 and _norm(text.split()[0]) == _norm(nw["w"])
                   for cs, ce, text in named_cuts if (text or "").split())

    for i, k in enumerate(out):
        prev_end = out[i - 1][1] if i else 0.0
        next_start = out[i + 1][0] if i + 1 < len(out) else float("inf")
        for j, w in enumerate(words):
            s, e = w["s"], w["e"]
            tol = min(0.04, (e - s) * 0.2)
            if s + tol < k[1] < e - tol and (k[1] - s) >= 0.5 * (e - s) and not named(w):
                run_end = e
                for nw in words[j + 1:]:  # finish the phrase: 'into' -> 'into it.'
                    if nw["s"] - run_end > joined or nw["e"] - e > max_run:
                        break
                    # never run on into a retake the trimmer cut: "what we're here for is | going to be the watch itself"
                    # ran on through the cut first take, then the second take said it again (dhgate cartier watch 1:03)
                    if any(k[1] - 0.15 <= cs <= nw["s"] + 0.05 for cs in starts):
                        break
                    run_end = nw["e"]
                new = round(min(run_end + tail, next_start - 0.02), 3)
                if new > k[1]:
                    fixed.append(f"{fmt(k[1])} end inside '{w['w'].strip()}' -> {fmt(new)}")
                    k[1] = new
            elif "wordnext" not in os.environ.get("RG_OFF", "") and s + tol < k[1] < e - tol and not named(w) and j + 1 < len(words) and opens_on(words[j + 1], s):
                # the cut says it removes from the NEXT word on ("Me personally, I don't have many..."), but its edge
                # landed early inside this one: "...if they're complete tr|" (canada goose jacket 2026-10-24, 0:36, "my word
                # gets cut off"): only 0.17 s of the 0.46 s "trash" played, so the half-word rule above left it. Finish
                # this word only, up to where the cut's own first word starts.
                new = round(min(e, words[j + 1]["s"], next_start - 0.02), 3)
                if new > k[1]:
                    fixed.append(f"{fmt(k[1])} end inside '{w['w'].strip()}' (the cut starts at '{words[j + 1]['w'].strip()}') -> {fmt(new)}")
                    k[1] = new
            if s + tol < k[0] < e - tol and named(w):   # inside a word that was cut on purpose: start after it
                new = round(min(e + 0.02, k[1] - 0.5), 3)
                if new > k[0]:
                    fixed.append(f"{fmt(k[0])} start inside cut word '{w['w'].strip()}' -> {fmt(new)}")
                    k[0] = new
            elif s + tol < k[0] < e - tol and (e - k[0]) >= 0.5 * (e - s):
                new = round(max(s - 0.05, prev_end + 0.02), 3)
                if new < k[0]:
                    fixed.append(f"{fmt(k[0])} start inside '{w['w'].strip()}' -> {fmt(new)}")
                    k[0] = new
    if fixed:
        checks.append(f"Word guard moved {len(fixed)} cut edge(s) off mid-word (source time): " + "; ".join(fixed))
    return [tuple(k) for k in out]


def pad_guard(kept, words, checks, protect=(), head=0.5, tail=0.7, keep_head=0.2, keep_tail=0.3, max_word=0.8, max_trim=2.5):
    """No dead air at a join (dhgate cartier watch 2026-10-22, 5:04: "there's like a giant pause [before 'anyways guys'] ...
    protect that word obviously but we don't want that much space. We got to be careful when joining these clips"; 2:24:
    1.6 s of him reaching for the receipt after "keep that in mind"). A kept piece opens at most `head` s before its first
    word and closes at most `tail` s after its last; anything more is trimmed to keep_head / keep_tail. A word Whisper
    stretched over a pause (> max_word) counts only from its last 0.4 s. Ranges in raw/extra_keeps.json (silent scrolls he
    wants) are left alone. Runs before edge_guard, which then puts every edge on measured quiet."""
    ws = sorted(words, key=lambda w: w["s"])
    out, moved = [], []
    for a, b in kept:
        inside = [w for w in ws if w["e"] > a + 0.15 and w["s"] < b - 0.15]   # not a word that merely touches the edge
        if not inside or any(pa <= a + 0.1 and b - 0.1 <= pb for pa, pb in protect):
            out.append((a, b))
            continue
        f, l = inside[0], inside[-1]
        fs = max(f["s"], f["e"] - 0.4) if f["e"] - f["s"] > max_word else f["s"]
        le = min(l["e"], l["s"] + 0.4) if l["e"] - l["s"] > max_word else l["e"]
        # longer silent stretches (> max_trim) are a silent demo the trimmer kept on purpose (a clasp, a scroll): leave them
        a2 = round(fs - keep_head, 3) if head < fs - a <= max_trim else a
        b2 = round(le + keep_tail, 3) if tail < b - le <= max_trim else b
        # an edge HE set with raw/extra_keeps stays: Whisper can lose the word there (s25 ultra 2:36, "Obviously" before
        # "audio issues" was folded into a 3.4 s "audio", so the put-back start looked like 2 s of dead air and went;
        # air_guard still trims what is measured silent)
        if any(pa - 0.05 <= a <= pa + 0.05 for pa, pb in protect):
            a2 = a
        if any(pb - 0.05 <= b <= pb + 0.05 for pa, pb in protect):
            b2 = b
        if b2 - a2 < 0.5:
            out.append((a, b))
            continue
        if (a2, b2) != (a, b):
            moved.append(f"{fmt(a)}-{fmt(b)} -> {fmt(a2)}-{fmt(b2)}")
        out.append((a2, b2))
    if moved:
        checks.append("Pad guard trimmed dead air at clip joins (source time): " + "; ".join(moved))
    return out


CLOSERS = ["bye", "peace", "peace out", "see you next time", "see you guys next time", "see you in the next one", "catch you later"]


def end_guard(kept, words, duration, checks, after=0.4, mic=None):
    """The video ends on his last goodbye (dhgate cartier watch 2026-10-22, 5:22: "when I said bye, the video continued for
    2 more seconds ... the video should obviously end at bye. That usually ends at bye"). The last closer ("bye", "peace
    out", "see you next time") in the final 10 % of the recording, inside kept footage, ends the edit `after` s past it;
    whatever he says once he's done ("oh my goodness, okay now I gotta get this order") is cut."""
    toks = [_norm(w["w"]).replace("-", "") for w in words]
    hit = None
    for i, w in enumerate(words):
        if w["s"] < duration * 0.9:
            continue
        for c in CLOSERS:
            cw = c.split()
            if toks[i:i + len(cw)] == cw and any(x <= w["s"] <= y for x, y in kept):
                hit = i + len(cw) - 1
    if hit is None:
        return kept
    # "see you guys next time in the next video for Not {{REVIEW_CHANNEL}}": the sentence the closer is in finishes (regression suite
    # 2026-10-23: the approved prada cups edit ended on "...in the next"). Only a run straight on (<= 0.6 s gaps) that names
    # the next video; a "bye" then "oh my goodness, okay now..." still ends on the bye.
    j, run = hit, []
    while j + 1 < len(words) and len(run) < 8 and words[j + 1]["s"] - words[j]["e"] <= 0.6 and not re.search(r"[.!?]$", words[j]["w"]):
        j += 1
        run.append(j)
    if run and any(toks[x] in ("video", "videos", "one", "episode") for x in run):
        last = next((x for x in run if re.search(r"[.!?]$", words[x]["w"])), run[-1])
        hit = last
    end = round(words[hit]["e"] + after, 3)
    nxt = words[hit + 1]["s"] if hit + 1 < len(words) else None
    if nxt is not None and nxt < end:
        end = round(max(words[hit]["e"] + 0.1, (words[hit]["e"] + nxt) / 2), 3)
    # a quick "Bye!" after the sign-off is often not transcribed (dhgate watchb spread 2026-10-24, 19:41.5: "the word bye
    # wasn't protected there ... it's just gone"): the end runs on through voiced sound right after (<= 1.5 s, gaps
    # < 0.5 s), measured on the mic, when no transcribed word comes next
    # ...and a closer said straight on to the end ("...for {{REVIEW_CHANNEL}} one-to-one" ended on "-to") finishes its run of speech
    # (only the channel name: "one-to-one", "{{REVIEW_CHANNEL}}"; never past a "bye" - cartier: "bye | oh my goodness, okay
    # now I gotta get this order" stays cut, regression replay 2026-10-24)
    NAME_TOK = re.compile(r"^-?(one|to|1|{{REVIEW_CHANNEL}}|{{REVIEW_CHANNEL}}|reviews?|resells?|finds|kicks|haul|profit)$")
    ref = hit
    while toks[hit] not in ("bye", "byebye", "peace", "later") and ref + 1 < len(words) and             words[ref + 1]["s"] - words[ref]["e"] < 0.4 and NAME_TOK.match(_norm(words[ref + 1]["w"])):
        ref += 1
    if ref != hit and ref + 1 >= len(words):
        hit, end = ref, max(end, round(words[ref]["e"] + after, 3))
        nxt = None
    if mic is not None and (nxt is None or nxt > end + 1.5):
        try:
            import wave
            w_ = wave.open(str(mic))
            sr = w_.getframerate()
            w_.setpos(int(words[hit]["e"] * sr))
            a_ = np.frombuffer(w_.readframes(int(2.0 * sr)), np.int16).astype(np.float32) / 32768
            n_ = int(0.02 * sr)
            lv = 20 * np.log10(np.sqrt((a_[: len(a_) // n_ * n_].reshape(-1, n_) ** 2).mean(axis=1)) + 1e-9)
            last_k, gap = None, 0
            for k_, v in enumerate(lv[: int(1.5 / 0.02)]):
                if v > -35:
                    last_k, gap = k_, 0
                else:
                    gap += 1
                    if last_k is not None and gap * 0.02 > 0.5:
                        break
            if last_k is not None:
                end = max(end, round(words[hit]["e"] + (last_k + 1) * 0.02 + 0.3, 3))
        except Exception:  # noqa
            pass
    out = [(a, min(b, end)) for a, b in kept if a < end - 0.3]
    if out != [tuple(k) for k in kept]:
        checks.append(f"End guard: the video ends on '{words[hit]['w']}' ({fmt(words[hit]['e'])} source); "
                      f"{sum(b - a for a, b in kept) - sum(b - a for a, b in out):.1f} s after it cut.")
    return out


def fragment_guard(kept, words, checks, keeps=(), gap=0.3, lookahead=0.5, max_piece=8.0, tail=0.12, max_tail=1.0, cuts=()):
    """No kept piece ends on a sentence that runs on into the cut (prada cups 3:31: "...the best one available, these |
    then you'll be brought to" — a weird half-word and a jump; "let's not do that for future videos"). Such an end is
    pulled back to the last phrase boundary in the piece (punctuation or a pause >= gap) when what hangs after it is a
    short tail (<= max_tail s, e.g. "these"); a short piece (<= max_piece) with no boundary at all is a run-on fragment
    and is dropped. Longer tails are only flagged (cutting them would change what he says). Every move goes to Check these."""
    words = sorted(words, key=lambda w: w["s"])
    out, moved = [], []
    for i, (a, b) in enumerate(kept):
        if i == len(kept) - 1:
            out.append((a, b))
            continue
        pw = [w for w in words if a - 0.05 <= w["s"] and w["e"] <= b + 0.15]
        cont = [w for w in words if b - 0.05 <= w["s"] <= b + lookahead and w["s"] < kept[i + 1][0] - 0.05 and w not in pw]
        # an end he set with raw/extra_keeps is his call (yeezy slides: "Here's some of the on feet | in terms of size",
        # Whisper ran "feet in" together, so the piece he kept read as a run-on and was dropped)
        # ...and so is an end where HIS raw/extra_cuts starts (dhgate cologne spread 2026-10-25, 2:47: "cut after 'as you
        # can see'"; small.en wrote no full stop there, so the 6.5 s piece he kept was dropped as a run-on fragment)
        if (not pw or not cont or re.search(r"[.!?]$", pw[-1]["w"]) or any(abs(b - kb) < 0.05 for ka, kb in keeps)
                or any(abs(b - ca) < 0.3 for ca, cb in cuts)):
            out.append((a, b))
            continue
        cut_at = None
        for j in range(len(pw) - 1, -1, -1):
            nxt_s = pw[j + 1]["s"] if j + 1 < len(pw) else None
            if pw[j]["e"] - a >= 1.0 and (re.search(r"[.!?,]$", pw[j]["w"]) or (nxt_s is not None and nxt_s - pw[j]["e"] >= gap)):
                cut_at = pw[j]["e"]
                break
        if cut_at is not None and cut_at < b - 0.2 and b - cut_at <= max_tail + 0.15:
            out.append((a, round(min(cut_at + tail, b), 3)))
            moved.append(f"{fmt(b)} ran on into the cut -> ends {fmt(cut_at + tail)} after '{[w for w in pw if w['e'] == cut_at][0]['w']}'")
        elif cut_at is None and b - a <= max_piece:
            moved.append(f"{fmt(a)}-{fmt(b)} dropped (a run-on fragment with no phrase end before the cut)")
        else:
            out.append((a, b))
            moved.append(f"{fmt(b)} may end mid-sentence into the cut: listen to it")
    if moved:
        checks.append(f"Fragment guard (source time): " + "; ".join(moved))
    return out


def greeting_guard(kept, words, checks, window=20.0, min_piece=0.6, pad=0.12):
    """The video opens on his LAST "hey guys" only, and no sliver under min_piece s survives anywhere (amiri jeans
    2026-10-22, 0:19: a 0.2 s "guys" of the second take played before the third, "I say hey guys twice")."""
    if not kept:
        return kept
    t0 = kept[0][0]
    heys = [w["s"] for i, w in enumerate(words[:-1]) if t0 - 1.0 <= w["s"] <= t0 + window and norm(w["w"]) == "hey"
            and norm(words[i + 1]["w"]).startswith("guy") and any(a <= w["e"] and words[i + 1]["s"] <= b for a, b in kept)]
    if len(heys) > 1:
        start = heys[-1] - pad
        dropped = [(a, b) for a, b in kept if b <= start]
        kept = [(max(a, start), b) for a, b in kept if b > start]
        checks.append(f"Greeting said {len(heys)} times: the video opens on the last \"hey guys\" at {fmt(heys[-1])} (source)"
                      + (f", {len(dropped)} piece(s) before it dropped." if dropped else "."))
    short = [(a, b) for a, b in kept if b - a < min_piece]
    if short:
        checks.append("Dropped sliver(s) under %.1f s: %s (source)." % (min_piece, ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in short)))
    return [(a, b) for a, b in kept if b - a >= min_piece]


def _abandoned_cuts(project):
    """take-review cuts of a take he ABANDONED and did again (work/trim/review_cuts.json, "why": "abandoned box intro ...
    redone in S6"): [(s, e)]"""
    rc = load_json(project / "work" / "trim" / "review_cuts.json") or []
    return [(c["s"], c["e"]) for c in rc if isinstance(c, dict) and re.search(r"abandon", c.get("why", ""), re.I)
            and re.search(r"redone|redo|retake|again|later take|restart", c.get("why", ""), re.I)]


# words that carry no content on their own: a stranded piece made only of these is a tag-on scrap ("Yeah, as you can see")
FILLER_WORDS = {"yeah", "yea", "yep", "okay", "ok", "so", "um", "uh", "alright", "oh", "as", "you", "can", "see", "look",
                "at", "right", "here", "there", "it", "that", "this", "like", "and", "but", "guys", "just", "man", "well"}


def orphan_guard(kept, words, checks, keeps=(), max_piece=2.0, near=3.0, far=20.0, deliberate=(), abandoned=()):
    """A short piece stranded between cuts is the leftover edge of a removed chunk (amiri jeans 2026-10-22, 2:42: a
    1.4 s "...there we go" from "let me take these off" flashed up between a 3.6 s and an 85 s cut, "that's not part
    of the video"). A piece <= max_piece s with a cut >= near s on one side and >= far s on the other is dropped;
    other stranded short pieces are only listed (dhgate rick owens: "here's what's inside", 9 s cuts each side, is real)."""
    out, flagged = [], []
    for i, (a, b) in enumerate(kept):
        gl = a - kept[i - 1][1] if i else 1e9
        gr = kept[i + 1][0] - b if i + 1 < len(kept) else 1e9
        text = " ".join(w["w"] for w in words if a <= w["s"] < b)
        # a piece with NO word in it is a mumble, not a line: stranded beside any real cut (top 5 products to resell in
        # winter 2024, 7:06: a 1.6 s mutter while holding the AirPods Max up, 2.9 s cut before it and 79 s after, "I just
        # have something about a listing, I don't know what I said there ... another error"; near was 3.0)
        nr = 1.0 if not text.strip() else near
        # a filler-led tag-on ("Yeah, as you can see.") right after a FINISHED sentence and before a big cut is the scrap of
        # an abandoned take whatever the cut before it (top 5 reselling products spring 2026-10-25, 8:29: "...especially for
        # the springtime. | Yeah, as you can see. | [82 s cut] Next up", 1.3 s cut before it; "how did this bad take make it
        # through ... add a rule for this")
        prev_w = [w for w in words if out and out[-1][0] <= w["s"] < out[-1][1]]
        nwf = lambda s_: re.sub(r"[^a-z']", "", s_.lower())
        tag_on = (far <= gr < 1e8 and 0 < len(text.split()) <= 6 and prev_w and prev_w[-1]["w"].rstrip().endswith((".", "!", "?"))
                  and all(nwf(x) in FILLER_WORDS for x in text.split()) and os.environ.get("RG_OFF") != "fillertail")
        if tag_on:
            nr = 0.0
        # right BEFORE a take-review cut of an abandoned take he did again (>= 20 s, the whole piece then >= 45 s from the next
        # clip), an unfinished lone line of up to 3.5 s is that take's first sentence (bapesta dhgate 2026-10-25, 0:42:
        # "Okay, starting things off, we do have the Bapesta though, so" between an 8.9 s and a 60 s cut; the take review cut
        # the "abandoned box intro ... redone" from its 2nd sentence on: "this was me talking to myself ... doesn't make sense
        # for the actual script of the video"). His voice level there (-23.8 dB P85) is inside his normal range, so no
        # voice-profile test can tell it. Cut shape alone can't either: the approved reselling spreadsheet's "anyways, let's
        # go jump right into the first spreadsheet" (8.4 s / 56 s cuts) is real; there the big cut is the trimmer's, not an
        # abandoned-take cut.
        mp = 3.5 if 45.0 <= gr < 1e8 and len(text.split()) <= 12 and not re.search(r"[.!?]$", text.strip()) \
            and any(abs(ca - b) <= 0.6 and cb - ca >= 20.0 for ca, cb in abandoned) \
            and os.environ.get("RG_OFF") != "orphanlong" else max_piece
        if b - a <= mp and min(gl, gr) >= nr and not any(ka < b and a < kb for ka, kb in keeps):
            # never his greeting, never the edge of a cut HE asked for (dhgate jordan 3 2026-10-23: his raw/extra_cuts
            # removed the tangent after "Hey guys, {{REVIEW_CHANNEL}} here." and this guard then dropped the greeting itself as a
            # "stranded piece"): only leftovers of the trimmer's own cuts are dropped
            mine = any(ca <= a + 0.6 and a - 0.6 <= cb or ca <= b + 0.6 and b - 0.6 <= cb for ca, cb in deliberate)
            greeting = a < 60 and re.search(r"\b(hey|hello|what's up|whats up|yo)\b.*\bguys\b|\bguys\b.*\bhere\b", text.lower())
            if max(gl, gr) >= far and min(gl, gr) < 1e8 and not mine and not greeting:
                checks.append(f"Dropped stranded {b - a:.1f} s piece {fmt(a)}-{fmt(b)} (source) between big cuts: \"{text}\".")
                # a filler-only tag-on: its first half often closes the piece before ("...springtime. Yeah. | as you can
                # see"): that piece then ends on its last real sentence
                if tag_on and out:
                    ends = [k for k, w in enumerate(prev_w[:-1]) if w["w"].rstrip().endswith((".", "!", "?"))]
                    if ends and all(nwf(w["w"]) in FILLER_WORDS for w in prev_w[ends[-1] + 1:]):
                        out[-1] = (out[-1][0], round(min(out[-1][1], prev_w[ends[-1]]["e"] + 0.15), 3))
                        checks.append(f"...and its lead-in \"{' '.join(w['w'] for w in prev_w[ends[-1] + 1:])}\" at the end of the "
                                      f"piece before went with it (now ends {fmt(out[-1][1])}).")
                # ...and when that piece was the take KEPT of a line said twice, the line must not vanish: the earlier take
                # that starts right where the clip before ends goes back on, up to its sentence end (dhgate cologne spread
                # 2026-10-25, 0:58: the take review kept the later "it's kind of that good", this guard dropped it, and the
                # clip ended on "...for personal use. It's |", "you never finish the sentence, you just cut me off")
                if out and gl <= 8.0:
                    pa, pb = out[-1]
                    nw = lambda s_: re.sub(r"[^a-z']", "", s_.lower())
                    gw = [w for w in words if pb - 0.3 <= w["s"] < a]
                    end = next((k for k, w in enumerate(gw) if w["w"].rstrip().endswith((".", "!", "?"))), None)
                    pwords = {nw(x) for x in text.split()} - {""}
                    if (end is not None and gw and gw[0]["s"] <= pb + 0.5 and gw[end]["e"] - pb <= 3.0
                            and len(pwords & {nw(w["w"]) for w in gw[:end + 1]}) >= 2):
                        out[-1] = (pa, round(gw[end]["e"] + 0.15, 3))
                        checks.append(f"...its earlier take finishes the sentence instead: {fmt(pb)}-{fmt(out[-1][1])} \""
                                      + " ".join(w["w"] for w in gw[:end + 1]) + "\" put back (source).")
                continue
            flagged.append(f"{fmt(a)}-{fmt(b)} \"{text}\"")
        out.append((a, b))
    if flagged:
        checks.append("Short stranded piece(s) kept, check they belong: " + "; ".join(flagged) + " (source).")
    return out


def walkoff_guard(kept, mic_path, rows, checks, protect=(), quiet_db=-42.0, min_silent=2.5, keep=0.3, max_face=0.4, lone_s=1.2,
                  win=0.02):
    """A silent stretch at a clip edge where he walks out of (or into) the shot is not a silent demo (best sp5der hoodie
    2026-10-23, 4:20: "after 'I'll show you guys where to get them from' it left in a clip of me walking away ... that
    section didn't make sense to keep"; 4.6 s after "from" with nobody in either camera). pad_guard / air_guard leave quiet
    longer than 2.5 s alone on purpose (a silent scroll, a clasp being shown), so this one decides by the PICTURE: a silent
    head/tail > min_silent with no screen recording on either half and his face on neither camera for > max_face of it is
    trimmed to `keep` s. His raw/extra_keeps and the video's very start/end are left alone."""
    import wave
    try:
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return kept
    n = int(win * sr)

    def empty(t0, t1):
        rs = [r for r in rows if t0 <= r["t"] <= t1]
        if len(rs) < 3 or any(r.get("left") == "screen" or r.get("right") == "screen" for r in rs):
            return False
        face = sum(1 for r in rs if r.get("fx") is not None or r.get("rfx") is not None or r.get("rfx_face") is not None)
        return face / len(rs) <= max_face

    out, moved = [], []
    for i, (s, e) in enumerate(kept):
        if any(pa <= s + 0.1 and e - 0.1 <= pb for pa, pb in protect) or e - s < 1.0:
            out.append((s, e))
            continue
        seg = a[int(s * sr):int(e * sr)]
        lv = 20 * np.log10(np.sqrt((seg[: len(seg) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)
        loud = lv > quiet_db
        on = np.where(loud[:-2] & loud[1:-1] & loud[2:])[0]
        if not len(on):
            out.append((s, e))
            continue
        head, tail = on[0] * win, (len(lv) - 1 - (on[-1] + 2)) * win
        s2, e2 = s, e
        if i and head > min_silent and empty(s, s + head):
            s2 = s + head - keep
        if i + 1 < len(kept) and tail > min_silent and empty(e - tail, e):
            e2 = e - tail + keep
        # ...or a lone word after / before the empty gap (4:20: the join cleanup put a stray "Okay," at 781.2 back on the
        # end, which dragged the 4 s of nobody in shot in with it): <= lone_s of voice past the gap goes with the gap
        runs, r0 = [], None
        for k, q in enumerate(list(~loud) + [False]):
            if q and r0 is None:
                r0 = k
            elif not q and r0 is not None:
                if (k - r0) * win > min_silent:
                    runs.append((s + r0 * win, s + k * win))
                r0 = None
        if runs and i + 1 < len(kept) and e2 == e and e - runs[-1][1] <= lone_s and empty(*runs[-1]):
            e2 = runs[-1][0] + keep
        if runs and i and s2 == s and runs[0][0] - s <= lone_s and empty(*runs[0]):
            s2 = runs[0][1] - 0.12
        if (s2, e2) != (s, e) and e2 - s2 >= 0.5:
            moved.append(f"{fmt(s)}-{fmt(e)} -> {fmt(s2)}-{fmt(e2)}")
            out.append((round(s2, 3), round(e2, 3)))
        else:
            out.append((s, e))
    if moved:
        checks.append("Walk-off guard trimmed silent edges with nobody in shot and no screen (source): " + "; ".join(moved))
    return out


def hum_guard(kept, mic_path, checks, look=2.5, min_burst=0.15, max_hum=1.2, min_quiet=0.3, voiced_db=-35.0,
              quiet_db=-42.0, mid_db=-8.0, win=0.01):
    """A kept piece never opens on a closed-mouth hum ("mmm" before "anyways guys", dhgate yeezy slides 2:46, 2026-10-23:
    "it's not like a word but it's like a sound before"). Whisper wrote it as a word ("But"), so only the AUDIO tells:
    the first voiced burst of a piece, <= max_hum long, followed by >= min_quiet of quiet, with under mid_db of its energy
    in 300-1000 Hz is cut: the piece starts just before the speech after the quiet. A closed mouth puts everything under
    300 Hz (the hum: -12.6 dB in 300-1000 Hz); every open vowel has its first formant there (-1.8..-4.8 dB, even nasal
    "in order to" in s25 ultra, which a high-frequency test could not tell from the hum). Tested on all 195 kept clip
    starts of 10 review projects. Listed in Check these."""
    import wave
    try:
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return kept
    n = int(win * sr)
    out = []
    for s, e in kept:
        i0, i1 = int(s * sr), int(min(e, s + look) * sr)
        seg = a[i0:i1]
        lv = 20 * np.log10(np.sqrt((seg[: len(seg) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9) if len(seg) >= n else np.array([])
        on = np.where(lv > voiced_db)[0]
        new = s
        if len(on):
            b0, k, run = on[0], on[0], 0
            while k < len(lv):                     # burst end = start of the first quiet run >= min_quiet
                run = run + 1 if lv[k] < quiet_db else 0
                if run * win >= min_quiet:
                    break
                k += 1
            q0 = k - run + 1
            if k < len(lv) and min_burst <= (q0 - b0) * win <= max_hum:
                k2 = k
                while k2 < len(lv) and lv[k2] < quiet_db:
                    k2 += 1                        # end of the quiet = next speech
                burst = a[i0 + b0 * n: i0 + q0 * n]
                F = np.abs(np.fft.rfft(burst * np.hanning(len(burst)))) ** 2
                f = np.fft.rfftfreq(len(burst), 1 / sr)
                ratio = 10 * np.log10(F[(f > 300) & (f <= 1000)].sum() / max(F[f > 80].sum(), 1e-12) + 1e-12)
                if ratio < mid_db and k2 < len(lv) and e - (s + k2 * win) > 1.0:
                    new = s + max(q0 * win, k2 * win - 0.08)
                    checks.append(f"Hum cut at a clip start: {fmt(s)}-{fmt(new)} source ({(q0 - b0) * win:.2f} s, "
                                  f"{ratio:.0f} dB in 300-1000 Hz: a closed-mouth 'mmm', not a word).")
        out.append((round(new, 3), e))
    return out


AIR = {"before": 0.08, "after": 0.14}   # config.json joins.air_before / air_after; a project's raw/config.json overrides


def air_guard(kept, mic_path, checks, protect=(), quiet_db=-42.0, keep_head=None, keep_tail=None, min_trim=0.1, max_air=2.5, win=0.02):
    """Dead air at a join, MEASURED (ultimate dhgate free reselling spreadsheet 2026-10-23, 0:39: "too much spacing between
    the join and the actual entry ... literally 2 seconds"; 1:08 / 1:19 "we got to tighten up these cuts but we don't want
    to cut off words"). pad_guard works on Whisper times, and Whisper stretches the first word back over the pause ("Hey"
    at 66.4 s, his voice starts at 67.08): the main edit opened on 0.96 s of silence after the intro. Here each kept piece
    opens keep_head s before the first voiced audio (3+ windows over quiet_db) and closes keep_tail s after the last.
    Quiet longer than max_air is a silent demo the trimmer kept on purpose (a scroll): left alone, like his extra_keeps.
    0.08 + 0.14 s since maison mahara 2026-10-26 (0:30 "the best Maison Miharas on DHgate | I'm actually really excited":
    0.12 + 0.2 = 0.32 s of air still read as "too much spacing"); the soft-ending rule below keeps word tails safe."""
    import wave
    keep_head = AIR["before"] if keep_head is None else keep_head
    keep_tail = AIR["after"] if keep_tail is None else keep_tail
    try:
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return kept
    n = int(win * sr)
    out, moved = [], []
    for s, e in kept:
        if any(pa <= s + 0.1 and e - 0.1 <= pb for pa, pb in protect) or e - s < 1.0:
            out.append((s, e))
            continue
        seg = a[int(s * sr):int(e * sr)]
        lv = 20 * np.log10(np.sqrt((seg[: len(seg) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)
        loud = lv > quiet_db
        on = np.where(loud[:-2] & loud[1:-1] & loud[2:])[0]
        if not len(on):
            out.append((s, e))
            continue
        # a word's soft ending (the "-ks" of "fix", an "s", a breathy "-th") sits under quiet_db: the tail counts from where
        # that decay reaches the room floor, not from the last loud window (lv skatesta 4:25: "easy to go in and fi[x]",
        # the -37..-42 dB "x" was trimmed off). Soft = 6 dB over this clip's floor and >= quiet_db - 8, max 0.3 s on, through
        # sound that DECAYS or is hiss (>= half its energy over 2.5 kHz: s, x, f, th). A voiced rise of 4 dB over the lowest
        # level so far is the next word's onset (connected speech at a cut: "do it and | Pretty" grew a sliver of "Pretty" and
        # the join cleanup then cut "and Pretty", regress 2026-10-24)
        last = on[-1] + 2
        soft = max(quiet_db - 8.0, float(np.percentile(lv, 10)) + 6.0)

        def hiss(k):
            x = seg[k * n:(k + 1) * n]
            p = np.abs(np.fft.rfft(x)) ** 2 if len(x) == n else None
            return p is not None and p[int(len(p) * 2500 / (sr / 2)):].sum() >= 0.5 * (p.sum() + 1e-12)

        ok = lambda k, low: lv[k] > soft and (lv[k] <= low + 4.0 or hiss(k))
        j, low = last, float(lv[min(last, len(lv) - 1)])
        while j + 1 < len(lv) and (j + 1 - last) * win <= 0.3 and (ok(j + 1, low) or (j + 2 < len(lv) and ok(j + 2, low))):
            j += 1
            low = min(low, float(lv[j]))
        head, tail = on[0] * win, (len(lv) - 1 - j) * win
        s2 = s + head - keep_head if min_trim + keep_head <= head <= max_air else s
        e2 = e - tail + keep_tail if min_trim + keep_tail <= tail <= max_air and (s, e) != kept[-1] else e   # the end fade stays
        if e2 - s2 < 0.5:
            out.append((s, e))
            continue
        if (s2, e2) != (s, e):
            moved.append(f"{fmt(s)}-{fmt(e)} -> {fmt(s2)}-{fmt(e2)}")
        out.append((round(s2, 3), round(e2, 3)))
    if moved:
        checks.append(f"Air guard trimmed measured silence at {len(moved)} clip edges (heads to {keep_head} s, tails to {keep_tail} s).")
    return out


def edge_guard(kept, mic_path, words, checks, loud_db=-30.0, quiet_db=-45.0, reach=0.35, win=0.02):
    """Every kept edge on MEASURED quiet, not on Whisper's word times (prada cups 3:31: a clip started 0.08 s into a loud
    "Then" whose Whisper time said it was already over — a clipped half-word, "a weird clip of a sound"). An edge on
    loud audio moves to the nearest quiet (>= 3 windows under quiet_db) within reach: a start moves FORWARD past a
    doubled word ("Then | then you'll") and back otherwise (keep the whole word); an end moves forward (finish the word)."""
    import wave
    try:
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return kept
    n = int(win * sr)

    def db(t):
        x = a[max(0, int(t * sr)):max(0, int(t * sr)) + n]
        return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) if len(x) else -99.0

    def quiet_at(t):
        return all(db(t + k * win) < quiet_db for k in range(3))

    def find(t, direction):
        k = 0.0
        while k <= reach:
            c = t + direction * k
            if quiet_at(c if direction > 0 else c - 3 * win):
                return round(c, 3)
            k += win
        # no 60 ms of quiet (he runs straight into the next word: "the price you have to pay. It's gonna be", dhgate jordan
        # 3 2026-10-23, 4:00 "the word pay gets weirdly cut off"): the quietest 20 ms gap between the words, when it is a
        # real dip (< quiet_db + 5)
        best, best_db, k = None, quiet_db + 5, 0.0
        while k <= reach:
            c = t + direction * k
            d = db(c if direction > 0 else c - win)
            if d < best_db:
                best, best_db = round(c, 3), d
            k += win
        return best

    words = sorted(words, key=lambda x: x["s"])
    out, moved = [], []
    for i, (s0, e0) in enumerate(kept):
        lo = out[-1][1] + 0.05 if out else 0.0
        hi = kept[i + 1][0] - 0.05 if i + 1 < len(kept) else float("inf")
        s1, e1 = s0, e0
        # a start just after a consonant burst counts as loud too ("diving" opened 0.03 s into its "d", dhgate jordan 3 1:00)
        if db(s0) > loud_db or db(s0 - win) > loud_db - 6:
            here = [x for x in words if x["s"] - 0.3 <= s0 <= x["e"] + 0.1]
            nxt = [x for x in words if x["s"] > s0][:1]
            doubled = here and nxt and _norm(here[0]["w"]) == _norm(nxt[0]["w"])
            fwd, back = find(s0, +1), find(s0, -1)
            # never back over a WHOLE word that ends before the start: that word was cut on purpose (word_guard put the
            # start after a cut "...and ten"; going back replayed it, dhgate jordan 3 8:21)
            if back is not None and any(back + 0.05 < x["e"] <= s0 + 0.03 for x in words):
                # ...the quietest 20 ms between that cut word and the start instead (regression suite 2026-10-23: with no
                # way back the start went FORWARD onto quiet inside the first word: approved yeezy slides lost "we're" of
                # "we're here for the shoe itself", cartier "I want" of "I want to talk about shipping")
                limit = max(x["e"] for x in words if back + 0.05 < x["e"] <= s0 + 0.03)
                cands = [limit + k * win for k in range(int(max(0.0, s0 - limit) / win) + 1)]
                back = round(min(cands, key=lambda t: db(t - win)), 3) if cands else None
                if back is not None and db(back - win) > quiet_db + 10:
                    back = s0   # no real dip: leave the start where it is
            # forward ONLY past a doubled word; otherwise back (or stay): forward onto quiet can be inside the first word
            c = fwd if doubled and fwd is not None else (back if back is not None and back >= lo else None)
            if c is not None and lo <= c < e0 - 0.5:
                s1 = c
        if db(e0 - win) > loud_db:
            c = find(e0, +1)
            if c is not None and c <= hi:
                e1 = c
        if (s1, e1) != (s0, e0):
            moved.append(f"{fmt(s0)}-{fmt(e0)} -> {fmt(s1)}-{fmt(e1)}")
        out.append((s1, e1))
    if moved:
        checks.append("Edge guard moved clip edges off loud audio onto measured quiet (source time): " + "; ".join(moved))
    return out


def midstart_guard(kept, mic_path, checks, cache_path, deliberate=(), tools=r"{{KIT}}/tools", quiet_db=-42.0,
                   gap_s=0.25, look=1.0, min_cut=1.0, min_words=3, max_back=4.0, win=0.02):
    """A kept piece never opens in the middle of a sentence (lv trainer 2026-10-23, 5:06: "in order to get to the LV
    Trainer link, it's honestly pretty easy, all you gotta do | is click the direct link" — the clip opened on "is").
    He ran straight through, so edge_guard settled on a 20 ms dip between two words, and the full-file Whisper had
    turned that stretch into "I ... I ... In order Below", so word_guard had nothing to go on. Here: a start after a
    real cut (>= min_cut) with no gap_s of quiet in the look s before it sits inside speech. That speech run (back to
    the last 0.4 s pause, never before the previous piece) is re-transcribed with medium.en; the words since its last
    sentence end ("tail") are put back when there are >= min_words of them, they span <= max_back s, and no two of
    them in a row are said again just after the start (that is a retake: "in terms of shipping it will take about |
    in terms of shipping..." stays cut). Longer tails are only listed in Check these. Tested on the 10 review projects'
    timelines: every retake/false start left alone. Cached in work/midstart.json by start time."""
    import wave
    try:
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except Exception:
        return kept
    n = int(win * sr)
    lv = 20 * np.log10(np.sqrt((a[: len(a) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)
    cache = load_json(cache_path) or {}
    norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())  # noqa: E731
    model, out, fixed, flagged, moved = None, [kept[0]] if kept else [], [], [], []
    for i, (s, e) in enumerate(kept[1:], 1):
        k = int(s / win)
        q = best = 0
        for x in lv[max(0, k - int(look / win)):k]:
            q = q + 1 if x < quiet_db else 0
            best = max(best, q)
        prev_end = out[-1][1]
        if best * win >= gap_s or s - prev_end < min_cut or any(da - 0.05 <= s <= db + 0.05 for da, db in deliberate):
            out.append((s, e))
            continue
        j, q = k, 0
        while j > 0 and k - j < 8 / win:                 # back to the last 0.4 s pause = start of this speech run
            j -= 1
            q = q + 1 if lv[j] < quiet_db else 0
            if q * win >= 0.4:
                break
        rs = max((j + q) * win, prev_end)
        if s - rs < 0.3:
            out.append((s, e))
            continue
        key = f"{s:.2f}|12"   # |12: transcribed 12 s on (was 4 s), so a retake said a few seconds later is heard too
        if key not in cache:
            try:
                if model is None:
                    sys.path.insert(0, str(tools))
                    import whisper_gpu
                    model, _dev = whisper_gpu.load("medium.en")
                t0 = rs - 0.1
                segs, _ = model.transcribe(a[int(t0 * sr):int(min(e, s + 12) * sr)], word_timestamps=True, vad_filter=False,
                                           language="en", beam_size=5, condition_on_previous_text=False)
                cache[key] = [[round(t0 + x.start, 3), round(t0 + x.end, 3), x.word.strip()] for sg in segs for x in sg.words]
            except Exception as ex:  # noqa: the guard must never stop a build
                checks.append(f"Mid-sentence check failed at {fmt(s)} ({type(ex).__name__}: {str(ex)[:100]}).")
                out.append((s, e))
                continue
        ws = cache[key]
        pre = [x for x in ws if x[1] <= s + 0.06]
        post_all = [norm(x[2]) for x in ws if x[1] > s + 0.06][:40]
        post = post_all[:12]
        # a sentence also starts at an opener after a comma (dhgae prada glasses 2026-10-25, 2:24: "...all the items here, |
        # but you do want to | go over to the section" lost its "but you do want to", the comma did not count)
        opener = lambda ix: (ix + 1 < len(pre) and re.search(r",$", pre[ix][2])
                             and norm(pre[ix + 1][2]) in ("but", "so", "and", "now", "then", "because", "also", "plus"))
        cut = max([ix + 1 for ix, x in enumerate(pre) if re.search(r"[.?!]$", x[2]) or opener(ix)] or [0])
        full_stop = cut > 0 and bool(re.search(r"[.?!]$", pre[cut - 1][2]))
        tail = pre[cut:]
        tn = [norm(x[2]) for x in tail]
        retake = set(zip(tn, tn[1:])) & set(zip(post, post[1:]))
        # ...or said again a little later, after another sentence (best sp5der hoodie 2026-10-23, 6:24 "Hope you guys enjoyed
        # and we're gonna figure | out" was put back, then "But anyways guys, that's pretty much it ... If you guys enjoyed and
        # we're able to go to figure out" = the real take; "a bad take that's in there"): >= 2 of its word pairs again
        retake = retake or len(set(zip(tn, tn[1:])) & set(zip(post_all, post_all[1:]))) >= 2
        said = " ".join(x[2] for x in tail)
        # after a real sentence end (. ? !) even 1-2 words of the new sentence go back (0:57 "...quality issues. It | does have"
        # opened inside "It"); a comma + opener still needs min_words (watchb spread, approved: "...on the website, but | use
        # Apple Pay" must NOT get its lone "but" back, "then | use Apple Pay" is right); a lone word said again right after is
        # a stutter, never put back
        need = 1 if full_stop and not (len(tail) == 1 and post[:1] == tn[:1]) and "mssent" not in os.environ.get("RG_OFF", "") else min_words
        # ...unless the clip opens on the stub of an abandoned try: "...pretty much it. Oh | my goodness, man | But anyways" must
        # skip forward, not get its "Oh" back (the 1-word put-back alone reopened the 3:10 sign-off on "Oh my goodness, man")
        if need < min_words and len(tail) < min_words and "msforward" not in os.environ.get("RG_OFF", "") \
                and _midstart_forward(s, e, ws, lv, quiet_db, gap_s, win, norm):
            need = min_words
        if len(tail) < need or retake:
            # nothing to put back: the clip opens on the STUB of an abandoned try. Skip it FORWARD to the next real pause
            # when a new sentence starts there (dhgae prada glasses 2026-10-25, 3:10: the sign-off retakes ended "...pretty
            # much it. Oh my goodness, man | But anyways guys, that's pretty much it" and the clip opened on "my goodness,
            # man", an audible error before the clean take). Only a stub of <= 4 words / 1.5 s, never past the clip.
            fw = None if "msforward" in os.environ.get("RG_OFF", "") else _midstart_forward(s, e, ws, lv, quiet_db, gap_s, win, norm)
            if fw:
                moved.append(f"{fmt(s)} -> {fmt(fw[0])} (dropped \"{fw[1]}\" | {fw[2]})")
                out.append((round(fw[0], 3), e))
            else:
                out.append((s, e))
            continue
        # the whole run is one sentence: open on the MEASURED pause (Whisper put "in" 0.1 s after the voice started)
        new = max(rs - 0.1 if cut == 0 else tail[0][0] - 0.1, prev_end + 0.05)
        if full_stop and len(tail) < min_words:
            # a short put-back opens on the quietest 20 ms right before its first word ("it. It" runs together: 0.1 s before
            # Whisper's start was still inside the "t" of "it.")
            lo, hi = int((tail[0][0] - 0.15) / win), int((tail[0][0] + 0.05) / win)
            if hi > lo:
                new = max((lo + int(np.argmin(lv[lo:hi]))) * win, prev_end + 0.05)
        if s - new > max_back:
            flagged.append(f"{fmt(s)} (\"...{said[-60:]} | {' '.join(post[:5])}\", {s - new:.1f} s back)")
            out.append((s, e))
            continue
        fixed.append(f"{fmt(s)} -> {fmt(new)} (\"{said[-70:]} | {' '.join(post[:4])}\")")
        out.append((round(new, 3), e))
    save_json(cache_path, cache)
    if fixed:
        checks.append("Mid-sentence starts put back to the sentence start (source): " + "; ".join(fixed) + ".")
    if flagged:
        checks.append("Clip(s) may open mid-sentence, too far back to fix automatically (check, raw/extra_keeps.json): "
                      + "; ".join(flagged) + ".")
    if moved:
        checks.append("Clip(s) opened on the stub of an abandoned try, start moved forward to the next sentence (source): "
                      + "; ".join(moved) + ".")
    return out


def _midstart_forward(s, e, ws, lv, quiet_db, gap_s, win, norm, max_words=4, max_s=1.5):
    """(new start, dropped words, next word) when the clip opening at s sits on a <= max_words stub that ends on a
    measured pause (>= gap_s under quiet_db) within max_s, followed by a new sentence (the stub ends on . , ! ? or the
    next word is capitalised and not "I"); else None."""
    k, n = int(s / win), len(lv)
    p0 = p1 = None
    j, run = k, 0
    while j < min(n, k + int(max_s / win)):
        if lv[j] < quiet_db:
            run += 1
            if run * win >= gap_s:
                p0 = (j - run + 1) * win
                while j < n and lv[j] < quiet_db:
                    j += 1
                p1 = j * win
                break
        else:
            run = 0
        j += 1
    if p0 is None or p1 > e - 1.0:
        return None
    frag = [x for x in ws if x[1] > s + 0.06 and x[0] < p0 + 0.05]
    nxt = next((x for x in ws if x[0] >= p0 - 0.15 and x not in frag), None)
    if not frag or len(frag) > max_words or nxt is None:
        return None
    new_sent = re.search(r"[.,!?]$", frag[-1][2]) or (nxt[2][:1].isupper() and norm(nxt[2]) not in ("i", "i'm", "i'll", "i've", "i'd"))
    if not new_sent:
        return None
    return max(p0 + 0.02, p1 - 0.12), " ".join(x[2] for x in frag), nxt[2]


def snap_angles(angles, kept, tol=0.5):
    """A camera switch within tol s of a cut moves onto the cut, so no camera shows for a few frames at a clip's edge
    (prada cups 0:39: the side angle ended 0.05 s before the cut — two frames of the close-up camera, "a weird webcam
    that pops up out of nowhere ... flashes for a quick second")."""
    out = [dict(g) for g in angles]
    for g1, g2 in zip(out, out[1:]):
        x = g1["end"]
        clip = next(((a, b) for a, b in kept if a <= x <= b), None)
        if not clip:
            continue
        if x - clip[0] < tol:
            x = clip[0]
        elif clip[1] - x < tol:
            x = clip[1]
        g1["end"] = g2["start"] = round(x, 3)
    return [g for g in out if g["end"] > g["start"]]


def noface_share(rows, kept, a, b):
    """Share of kept frames in [a, b] where Camera A sees no face (and the left half is not the screen)."""
    pts = [r for r in rows if a <= r["t"] <= b and any(x <= r["t"] <= y for x, y in kept)]
    return sum(1 for r in pts if r.get("fx") is None and r.get("left") != "screen") / len(pts) if pts else 0.0


def away_runs(rows, kept, quiet, min_s=8.0, glimpse=1.0):
    """Kept stretches inside the quiet-mic ranges where Camera A has no face for >= min_s (a face glimpse <= `glimpse` s
    does not end a run): he left the desk to try the product on."""
    out, start, seen = [], None, None
    pts = [r for r in rows if r.get("left") != "screen" and any(a <= r["t"] <= b for a, b in quiet)]
    for r in pts + [{"t": 1e9, "fx": 0}]:
        if r.get("fx") is None and (start is None or r["t"] - last <= 1.0):
            start, seen = (start if start is not None else r["t"]), None
        elif start is not None and r.get("fx") is not None and r["t"] - last <= 1.0 and (seen is None or r["t"] - seen < glimpse):
            seen = seen if seen is not None else r["t"]
        elif start is not None:
            end = seen if seen is not None else last
            if end - start >= min_s:
                out.append((start, end))
            start, seen = (r["t"], None) if r.get("fx") is None else (None, None)
        last = r["t"]
    return [(max(a, x), min(b, y)) for a, b in out for x, y in kept if min(b, y) - max(a, x) > 0.5]


def rightcam_share(rows, kept, a, b):
    """Share of kept frames in [a, b] where the right (try-on) camera films HIM: the side angle, or his face on it."""
    pts = [r for r in rows if a <= r["t"] <= b and any(x <= r["t"] <= y for x, y in kept)]
    return sum(1 for r in pts if r.get("right") == "side" or r.get("rfx") is not None) / len(pts) if pts else 0.0


class Timeline:
    """Maps source time to output time through the kept ranges."""

    def __init__(self, kept, fps=30):
        # FRAME-accurate: the render keeps the source frames n/fps inside each clip (fps=30, then select between(t,a,b)
        # with a, b written to 3 decimals), so a clip lasts (its frame count)/fps, not b - a. Second-exact offsets drifted
        # up to a frame per cut and the layout switched a frame off the picture cut: a flash of the wrong camera at
        # seams (prada cups 2026-10-22, "a weird webcam that pops up ... flashes for a quick second").
        self.kept, self.fps = kept, fps
        self.offsets, self.first, self.lens, acc = [], [], [], 0.0
        for a, b in kept:
            f0, f1 = math.ceil(round(a, 3) * fps - 1e-6), math.floor(round(b, 3) * fps + 1e-6)
            n = max(0, f1 - f0 + 1)
            self.offsets.append(acc)
            self.first.append(f0 / fps)
            self.lens.append(n / fps)
            acc += n / fps
        self.duration = acc

    def to_out(self, t):
        for (a, b), off, fa, ln in zip(self.kept, self.offsets, self.first, self.lens):
            if t < a:
                return off
            if t <= b:
                return off + min(max(t - fa, 0.0), ln)
        return self.duration

    def intervals(self, ranges):
        out = []
        for ra, rb in ranges:
            for (a, b), off, fa, ln in zip(self.kept, self.offsets, self.first, self.lens):
                lo, hi = max(a, ra), min(b, rb)
                if b - a > 0.5 and ((hi <= a + 0.12 and rb < b) or (lo >= b - 0.12 and ra > a)):
                    continue    # only the first/last ~3 frames of a clip: the snapped neighbour layout covers them
                if hi > lo:
                    # a range reaching a clip edge runs to that clip's first/last frame exactly
                    # ...and so does one starting/ending within ~3 frames of it: the analysis rows are 0.2 s apart, so a
                    # layout run that opens on the first row after a cut left 1 frame of the previous layout at the seam
                    # (lv trainer 2026-10-23, 4:46.8: one frame of the front camera before the side camera shot)
                    o_lo = off if lo <= a + 0.12 else off + min(max(lo - fa, 0.0), ln)
                    o_hi = off + ln if hi >= b - 0.12 else off + min(max(hi - fa, 0.0), ln)
                    if o_hi > o_lo:
                        out.append((o_lo, o_hi))
        merged = []
        for a, b in sorted(out):
            if merged and a <= merged[-1][1] + 1e-3:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged


def enable_expr(intervals):
    if not intervals:
        return "0"
    # half-open [a, b): an interval ends ON a cut, and between() also took the first frame of the NEXT clip — a one-frame
    # flash of the old layout at the seam (prada cups 4:31, "wrong webcam for a second")
    # frame times are n/30 and the bounds are sums of n/30: a float hair under the bound dropped the first frame
    return "+".join(f"gte(t,{a - 0.001:.4f})*lt(t,{b - 0.001:.4f})" for a, b in intervals)


# ---------------------------------------------------------------- step 2: sections
def find_sections(words, rows, duration, cfg, checks):
    sc, mk = cfg["sections"], cfg["markers"]
    names = sc["names"]
    phrase = mk["phrase"].split()
    hits = []
    for i in range(len(words) - len(phrase) + 1):
        if [norm(w["w"]) for w in words[i:i + len(phrase)]] == phrase:
            hits.append((words[i]["s"], words[i + len(phrase) - 1]["e"]))
    marker_cuts = [(a - mk["pad_seconds"], b + mk["pad_seconds"]) for a, b in hits]
    if len(hits) == mk["expected_count"]:
        bounds = [0.0] + [(a + b) / 2 for a, b in hits] + [duration]
        method = "spoken markers"
    else:
        checks.append(f"Found {len(hits)} \"{mk['phrase']}\" markers instead of {mk['expected_count']}; "
                      "sections were found from the right-half picture and the transcript instead. Check the section times below.")
        bounds = fallback_bounds(words, rows, duration, sc)
        method = "fallback (picture + transcript)"
        marker_cuts = []  # don't cut stray phrases when the structure is guessed
    secs = [{"name": n, "start": round(bounds[i], 2), "end": round(bounds[i + 1], 2)} for i, n in enumerate(names)]
    return {"method": method, "markers": hits, "marker_cuts": marker_cuts, "sections": secs}


def absorb_flashes(ranges, kept, min_s):
    """No shot under min_s of KEPT footage (top 5 reselling products spring 2026-10-25, 10:05: "it literally flashes for like
    a second ... we need detection for that"): a gap shorter than that between two ranges is filled, then a range shorter
    than that is dropped. Lengths count kept time only, so a cut inside a gap doesn't make it look long."""
    def kept_len(a, b):
        return sum(max(0.0, min(b, kb) - max(a, ka)) for ka, kb in kept)
    out = []
    for a, b in sorted(ranges):
        if out and (a <= out[-1][1] or kept_len(out[-1][1], a) < min_s):
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return [(a, b) for a, b in out if kept_len(a, b) >= min_s]


def runs_of(rows, key):
    runs = []
    for r in rows:
        if runs and runs[-1][0] == r[key]:
            runs[-1][2] = r["t"]
        else:
            runs.append([r[key], r["t"], r["t"]])
    return runs


def fallback_bounds(words, rows, duration, sc):
    minrun = sc["min_run_seconds"]
    runs = [r for r in runs_of(rows, "right") if r[2] - r[1] >= minrun]
    # review starts where the talking-intro side angle gives way to the product camera: side runs with short gaps
    # (< 8 s) are one talking block; the first such block >= 10 s ends the intro. Pre-roll before it doesn't count
    # (prada cups 2026-10-22: a product shot at 0:04 of pre-roll made the whole "hey guys" intro a review section, so
    # it got the face circle and turntable B-roll — "I'm talking to the audience here")
    blocks = []
    for k, a, b in runs:
        if k != "side":
            continue
        if blocks and a - blocks[-1][1] < 8.0:
            blocks[-1][1] = b
        else:
            blocks.append([a, b])
    talk = next((bl for bl in blocks if bl[1] - bl[0] >= 10.0 and bl[0] < duration * 0.4), None)
    if talk:
        review = next((r[1] for r in runs if r[0] != "side" and r[1] >= talk[1] - 0.5), talk[1])
    else:
        review = next((r[1] for r in runs if r[0] != "side" and r[1] > 1), duration * 0.1)
    # ...but never mid-sentence: the product camera came up while he still talked to the viewer ("a lot of people are
    # asking me how is the quality? I'm gonna show you guys right now"), so the layout swapped to the product camera and the
    # circle 3 s early (dhgate jordan 3 2026-10-23, 1:00 "that transitioned too early"). The review starts after the
    # first pause >= 0.7 s within 6 s.
    for a, b in zip(words, words[1:]):
        if a["e"] > review and b["s"] - a["e"] >= 0.7:
            if a["e"] - review <= 6.0:
                review = a["e"] + 0.1
            break
    # outro starts where the side angle returns for good at the end
    outro = duration * 0.92
    side_end = runs and runs[-1][0] == "side" and runs[-1][1] > review
    if side_end:
        outro = runs[-1][1]
    left_at = lambda t: next((r.get("left") for r in rows if r["t"] >= t), None)
    if not side_end or left_at(outro) == "screen":
        # no side angle at the end, or the desktop is still up on the LEFT half while the right camera films him (that
        # reads "side" too): the outro is his sign-off, "anyways guys, that's pretty much it for today's video" (dhgate
        # jordan 3 2026-10-23: the outro started on "this one only goes up to size 12" over the listing). The LAST
        # sign-off (earlier takes get cut).
        toks = [norm(w["w"]).replace("'", "") for w in words]
        hit = None
        for i in range(len(toks)):
            for cue in sc.get("outro_cues", ["pretty much it for today", "thats it for today", "thats all for today"]):
                cw = cue.split()
                if len(toks[i:i + len(cw)]) == len(cw) and all(t.startswith(c) for t, c in zip(toks[i:i + len(cw)], cw)) \
                        and words[i]["s"] > review:
                    hit = i
        if hit is not None and words[hit]["s"] >= duration * 0.6:
            j = hit
            while j > 0 and toks[j - 1] in ("but", "anyways", "anyway", "guys", "so", "alright", "and", "okay", "thats") \
                    and words[hit]["s"] - words[j - 1]["s"] < 3.0:
                j -= 1
            outro = words[j]["s"] - 0.1
    # showcase: first screen run, pulled back to the sentence that introduces it
    # a real buying walkthrough is a long screen run: a 3 s flash of the monitor (lv trainer 2026-10-23, 2:26 source) made
    # the whole product review a "showcase", so the review section was empty and B-roll pairs could not be told apart
    # The screen can be on EITHER half (dhgate jordan 3: the listing on the left, him on the right camera).
    smin = sc.get("showcase_min_screen_seconds", 10.0)
    lmin = [r for r in runs_of(rows, "left") if r[2] - r[1] >= minrun] if rows and "left" in rows[0] else []
    screen = min((r[1] for r in runs + lmin if r[0] == "screen" and review < r[1] < outro and r[2] - r[1] >= smin), default=None)
    if screen is None:
        screen = review + (outro - review) * 0.55
    show = screen
    text = [(norm(w["w"]), w["s"]) for w in words]
    for cue in sc["fallback_showcase_cues"]:
        cw = cue.split()
        for i in range(len(text) - len(cw) + 1):
            if [x[0] for x in text[i:i + len(cw)]] == cw and screen - sc["cue_window_seconds"] <= text[i][1] <= screen:
                # walk back to the start of that sentence
                j = i
                while j > 0 and not re.search(r"[.!?]$", words[j - 1]["w"]) and text[i][1] - words[j - 1]["s"] < 6:
                    j -= 1
                show = min(show, words[j]["s"])
                break
    return [0.0, review, max(review + 1, show), outro, duration]


# ---------------------------------------------------------------- step 3: pacing
def find_cuts(words, duration, marker_cuts, cfg, checks):
    pc = cfg["pacing"]
    cuts = list(marker_cuts)
    if not pc.get("enabled", True):
        checks.append("Pacing cuts (silences, retakes, start/end trim) were switched off for this project in raw/config.json.")
    elif words:
        head = max(0.0, words[0]["s"] - pc["head_pad_seconds"])
        tail = min(duration, words[-1]["e"] + pc["tail_pad_seconds"])
        cuts += [(0, head), (tail, duration)]
        half = pc["silence_keep_seconds"] / 2
        for a, b in zip(words, words[1:]):
            if b["s"] - a["e"] > pc["silence_min_seconds"]:
                cuts.append((a["e"] + half, b["s"] - half))
        # retakes: a sentence whose opening words repeat in the next sentence is dropped
        sents, cur = [], []
        for w in words:
            cur.append(w)
            if re.search(r"[.!?]$", w["w"]):
                sents.append(cur)
                cur = []
        if cur:
            sents.append(cur)
        n = pc["retake_match_words"]
        for s1, s2 in zip(sents, sents[1:]):
            k1, k2 = [norm(w["w"]) for w in s1[:n]], [norm(w["w"]) for w in s2[:n]]
            if len(k1) == n and k1 == k2:
                cuts.append((s1[0]["s"] - 0.05, s2[0]["s"] - 0.05))
    kept = subtract([(0.0, duration)], cuts)
    return {"kept": kept, "removed_seconds": max(0.0, round(duration - sum(b - a for a, b in kept), 2))}


def _mic16k(project, cam):
    mic = project / "work" / "mic16k.wav"
    if not mic.exists() or mic.stat().st_mtime < cam.stat().st_mtime:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(mic)], check=True)
    return mic


def no_face_ranges(project, cfg, min_seconds=1.0):
    """Source ranges where NO camera sees him facing it (Camera A: no face or head turned > turn_degrees; right camera:
    no face). The take review marks lines said there [not facing a camera] so it can tell self-talk ("so yeah these are
    comfortable, I like these, I like these" muttered over the on-feet shot, dhgate yeezy slides 2026-10-23) from a line
    to the viewer."""
    rows = load_json(project / "work" / "analysis.json", []) or []
    turn = cfg.get("angles", {}).get("turn_degrees", 25)
    out, start, last = [], None, None
    for r in rows:
        yaw = r.get("yaw")
        away = (yaw is None or abs(yaw) > turn) and r.get("rfx") is None
        if away and start is None:
            start = r["t"]
        elif not away and start is not None:
            if r["t"] - start >= min_seconds:
                out.append([start, r["t"]])
            start = None
        last = r["t"]
    if start is not None and last - start >= min_seconds:
        out.append([start, last])
    return out


def take_review_marks(project, cam, keep, cfg, checks):
    """Claude reads the KEPT transcript for lines abandoned and redone in different words, fragments left at a join and
    talk not meant for the viewer (the phone pipeline's take_review.py, kind="review"). -> [[s, e], ...] source time.
    Cached in work/trim/review.json by transcript, so a rebuild with nothing new costs nothing."""
    tc = cfg.get("trimmer", {})
    if not tc.get("take_review", True):
        return []
    try:
        sys.path.insert(0, str(Path(tc.get("tools", r"{{KIT}}/tools")) / "phone_edit"))
        import take_review
        (project / "work" / "trim").mkdir(exist_ok=True)
        marks = take_review.review(str(project), 0.0, kind="review", work=str(project / "work" / "trim"),
                                   words=str(project / "work" / "transcript.json"), keep=[list(k) for k in keep],
                                   audio=str(_mic16k(project, cam)), away=no_face_ranges(project, cfg))
        (project / "work" / "review_status.json").unlink(missing_ok=True)
        return marks
    except Exception as e:
        try:
            (project / "work" / "review_status.json").write_text(json.dumps({"take_review": "failed", "why": str(e)[:300]}),
                                                                 encoding="utf-8")
        except OSError:
            pass
        # a failed take review STOPS the build (remote test prada 2026-10-26: no claude.exe on the laptop, the draft went out
        # with five bad takes the approved build of the same recording had cut, "we already cut this out before").
        # raw/config.json trimmer.allow_unreviewed lets the rule-based cut through on purpose, marked NOT REVIEWED.
        if not tc.get("allow_unreviewed", False):
            print(f"BUILD STOPPED: the AI take review failed, so this draft would keep every abandoned / redone take.\n"
                  f"{type(e).__name__}: {str(e)[-1200:]}", file=sys.stderr, flush=True)
            raise SystemExit(3)
        checks.insert(0, f"NOT REVIEWED: the AI take review failed ({type(e).__name__}: {str(e)[:160]}), so abandoned / "
                         "redone lines the rules can't see may still be in. Rebuild before sending this draft.")
        return []


def trim_take_cuts(project, cam, duration, marker_cuts, cfg, checks):
    """The shared trimmer of all three video types ({{KIT}}/tools\\take_cuts.py: last clean take, restarts, stuck
    lines, asides, re-opened sections, stutters, silences, cut edges on measured quiet), then the take review, then the
    cut again with its marks (user 2026-10-21: "get this up to speed for all three"). The section markers go in as exact cuts."""
    tc = cfg.get("trimmer", {})
    tools = Path(tc.get("tools", r"{{KIT}}/tools"))
    work = project / "work"
    mic = _mic16k(project, cam)
    fps = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(cam)],
                         capture_output=True, text=True).stdout.strip() or "30/1"
    num, den = fps.split("/")
    fps = round(float(num) / float(den or 1), 3)
    extra = [{"s": round(a, 3), "e": round(b, 3), "why": "user note: section marker"} for a, b in marker_cuts]

    def run(extra_list):
        save_json(work / "trim_extra.json", extra_list)
        cmd = [sys.executable, "-X", "utf8", str(tools / "take_cuts.py"), str(work / "transcript.json"), f"{fps:g}", str(work / "trim"),
               "--duration", f"{duration:.3f}", "--extra", str(work / "trim_extra.json"), "--audio", str(mic), "--no-mutters"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            raise RuntimeError(r.stderr[-800:])
        print(r.stdout[-1500:])
        return [tuple(k) for k in load_json(work / "trim" / "cuts.json")["keep"]]

    keep = run(extra)
    marks = take_review_marks(project, cam, keep, cfg, checks)
    if marks:
        keep = run(extra + marks)
    checks.append(f"Trim: shared take_cuts rules{f' + take review ({len(marks)} cuts)' if marks else ''}; full list in work/trim/cuts.md.")
    return {"kept": [[round(a, 3), round(b, 3)] for a, b in keep], "trimmer": "take_cuts", "take_review": len(marks),
            "removed_seconds": max(0.0, round(duration - sum(b - a for a, b in keep), 2))}


# ---------------------------------------------------------------- step 4: angles
DESK_RE = re.compile(r"\b(mouse ?pads?|desk ?mats?|desk ?pads?|my desk|desk setup|my setup|keyboard|room decor)\b", re.I)


def desk_angles(angles, words, checks, lead=2.5, chain=10.0, max_len=15.0):
    """Something ON HIS DESK he points out ("point out my brand new mousepad ... a KAWS inspired mousepad", his hand on
    it) is shown on the desk camera (B, with the face circle), from ~2.5 s before the first mention to the end of the
    sentence with the last mention (mentions <= 10 s apart chain, max 15 s). maison mahara 2026-10-26, 0:45: "we might
    want to show the other camera for this ... I'm literally putting my hand on it"."""
    if not angles or not any(g["cam"] == "B" for g in angles):
        return angles
    hits = [i for i in range(len(words)) if DESK_RE.search(" ".join(w["w"] for w in words[i:i + 2]).replace(".", "").replace(",", ""))]
    # only when he SHOWS it ("point out my brand new mousepad"), never while looking for it ("where's my mouse pad",
    # "so where's my keyboard?" in self-talk)
    def showing_it(i):
        before = " ".join(w["w"] for w in words[max(0, i - 7):i + 1]).lower()
        return re.search(r"point out|show (you|off)|check (it |this )?out|brand new|look at|talk about|this is", before) and "where" not in before
    hits = [i for i in hits if showing_it(i) or any(abs(words[i]["s"] - words[k]["s"]) <= chain and showing_it(k) for k in hits if k < i)]
    spans, i = [], 0
    while i < len(hits):
        j = i
        while j + 1 < len(hits) and words[hits[j + 1]]["s"] - words[hits[j]]["s"] <= chain:
            j += 1
        a = next(w["s"] for w in words if w["s"] >= words[hits[i]]["s"] - lead)
        k = hits[j]
        while k < len(words) - 1 and not re.search(r"[.?!]$", words[k]["w"]) and words[k + 1]["s"] - words[hits[j]]["s"] < 4:
            k += 1
        b = min(words[k]["e"] + 0.15, a + max_len)
        spans.append((round(a, 2), round(b, 2)))
        i = j + 1
    if not spans:
        return angles
    out = []
    for g in angles:
        pieces = [(g["start"], g["end"])]
        for a, b in spans:
            pieces = [q for x, y in pieces for q in ((x, min(y, a)), (max(x, b), y)) if q[1] - q[0] > 0.01]
        out += [{**g, "start": x, "end": y} for x, y in pieces]
    out += [{"cam": "B", "start": a, "end": b, "why": "desk"} for a, b in spans]
    out.sort(key=lambda g: g["start"])
    checks.append("Desk camera for something on his desk: " + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in spans) + " (source).")
    return out


def find_angles(rows, sections, cfg):
    ac, sign = cfg["angles"], cfg["camera"]["turn_sign"]
    full = [(s["start"], s["end"]) for s in sections if s["name"] in ("intro", "outro")]
    step = 1.0 / ac["analysis_fps"]

    def in_full(t):
        return any(a <= t < b for a, b in full)

    # Hysteresis (user 2026-10-22, prada cups 4:35: turned to the side camera at ~30 deg, his head eased to ~13 deg on "to be
    # honest with you guys" and the edit cut to the main camera for 2.4 s): turning past turn_degrees picks the side
    # camera; it is only left when he is clearly back to the front (under release_degrees) for release_seconds, or the
    # side camera / section ends. A lost face (yaw None) keeps the current camera.
    rel_deg, rel_s = ac.get("release_degrees", 10), ac.get("release_seconds", 3.0)
    raw, on_b, front_since = [], False, None
    for r in rows:
        y = r["yaw"] * sign if r["yaw"] is not None else None
        ok = r["right"] == "side" and in_full(r["t"])
        if not ok:
            on_b, front_since = False, None
        elif not on_b:
            if y is not None and y > ac["turn_degrees"]:
                on_b, front_since = True, None
        elif y is not None and y < rel_deg:
            front_since = r["t"] if front_since is None else front_since
            if r["t"] - front_since >= rel_s:
                on_b = False
                raw = [[("A" if rt >= front_since else c), rt, re_] for c, rt, re_ in raw]   # the switch lands where he turned back
        else:
            front_since = None
        raw.append(["B" if on_b else "A", r["t"], r["t"] + step])
    segs = []
    for cam, a, b in raw:
        if segs and segs[-1][0] == cam:
            segs[-1][2] = b
        else:
            segs.append([cam, a, b])
    # drop short turns, then enforce the minimum shot length
    segs = [[("A" if c == "B" and b - a < ac["min_turn_seconds"] else c), a, b] for c, a, b in segs]
    merged = []
    for c, a, b in segs:
        if merged and (merged[-1][0] == c or b - a < ac["min_shot_seconds"]):
            merged[-1][2] = b
        else:
            merged.append([c, a, b])
    if len(merged) > 1 and merged[0][2] - merged[0][1] < ac["min_shot_seconds"]:
        merged[1][1] = merged[0][1]
        merged.pop(0)
    # a side-camera shot that opens on the first analysis row of an intro/outro starts AT the section start: the section
    # boundary falls between rows, and the gap showed one frame of the front camera inside the side shot (lv trainer
    # 2026-10-23, 4:07 "there's a flash ... it just flashed": outro at 572.15, side camera from the row at 572.2)
    for k, m in enumerate(merged):
        fs = next((a for a, _ in full if 0 < m[1] - a <= 2 * step + 0.01), None)
        if m[0] == "B" and fs is not None:
            m[1] = fs
            if k:
                merged[k - 1][2] = fs
    return [{"cam": c, "start": round(a, 2), "end": round(b, 2)} for c, a, b in merged]


# ---------------------------------------------------------------- face-full cutaways ("here they are on my face")
def find_face_full(words, sections, a_ranges, cfg):
    """Source-time ranges where a cue sentence ('on my face', 'what they look like on'...)
    cuts to full-frame Camera A instead of the circle. Only where Camera A is live."""
    fc = cfg.get("face_full", {})
    if not fc.get("enabled"):
        return []
    out, last = [], -1e9
    for s in sections:
        if s["name"] not in fc.get("sections", ["review", "showcase"]):
            continue
        sw = [i for i, w in enumerate(words) if s["start"] + 0.5 <= w["s"] < s["end"] - 1.0]
        if not sw:
            continue
        sub = words[sw[0]:sw[-1] + 1]
        for i, _cue in _cue_hits(sub, fc["cues"]):
            gi = sw[0] + i
            a = words[gi]["s"] - 0.2
            if a < last + fc.get("min_gap_seconds", 20):
                continue
            b = min(max(_sentence_end(words, gi, fc.get("max_hold_seconds", 5)),
                        a + fc.get("min_hold_seconds", 2)), s["end"] - 0.2)
            out.append((a, b))
            last = b
    kept = []
    for a, b in out:
        for fa, fb in a_ranges:
            lo, hi = max(a, fa), min(b, fb)
            if hi - lo > 0.3:
                kept.append((round(lo, 2), round(hi, 2)))
    return kept


# ---------------------------------------------------------------- step 6: subscribe
def find_holdups(rows, kept, sections, checks, min_s=1.5, max_s=60.0, near=1.5, glimpse=1.5):
    """He holds something up to Camera A (dhgate cartier watch 2026-10-22, 0:54: the Cartier bag held up to the front
    camera while the product camera showed an empty desk: "we need to swap the camera over ... I was obviously trying to
    showcase something there. Then it needs to swap back to the face cam view and the hand cam view"). Camera A loses his
    face for min_s..max_s while he sits at the desk (face on Camera A within `near` s before AND after, no face on the
    right camera) in the review/showcase: Camera A full frame for that stretch, circle off, then back. Returns ranges.
    A showing can be long and his face peeks over the shoe now and then (dhgate rick owens 2026-10-22, 3:34-3:56 "I am
    showing the shoe in my other cam so swap there": 40 s with 1 s face glimpses; the old 15 s cap missed it and the
    product camera showed an empty box): glimpses <= `glimpse` s don't end a showing, and it may run up to max_s."""
    secs = [(x["start"], x["end"]) for x in sections if x["name"] in ("review", "showcase")]
    out, start, before, seen_at, peeks = [], None, None, None, 0
    for r in rows:
        lost = r.get("fx") is None and r.get("left") == "cam" and r.get("right") != "screen" and r.get("rfx") is None
        if lost:
            if start is None:
                start, peeks = r["t"], 0
            if seen_at is not None:
                peeks += 1
            seen_at = None
        elif start is not None and r.get("fx") is not None and r.get("right") != "screen" and r.get("rfx") is None and \
                (seen_at is None or r["t"] - seen_at < glimpse):
            seen_at = seen_at if seen_at is not None else r["t"]   # a glimpse of his face over the shoe: still showing
        else:
            end = seen_at if seen_at is not None else r["t"]
            # his face peeking over the shoe proves he is at the desk showing it: such a showing may run up to 3x max_s
            # (lv trainer 2026-10-23, 3:24-4:46 source: 82 s of the trainer held up to the front camera with one glimpse
            # at 4:10; the 60 s cap dropped the whole showing, so the product camera showed an empty box)
            cap = max_s * 3 if peeks else max_s
            if start is not None and before is not None and start - before <= near and min_s <= end - start <= cap:
                out.append((start, end))
            start, seen_at = None, None
            if r.get("fx") is not None:
                before = r["t"]
    # one showing = one shot (dhgate jordan 3 2026-10-23): his face peeking over the shoe for 2.2 s split a showing in two and
    # the product camera's empty box flashed in between (2:16, "not sure why it switched back ... keep it on the main
    # camera"), and a showing that ended 1.9 s before the cut flashed the product camera for "where you can find these"
    # (2:51). Showings <= bridge s apart merge; an edge <= bridge s from its clip's edge runs on to the cut.
    bridge = 3.0
    merged = []
    for a, b in sorted(out):
        if merged and a - merged[-1][1] <= bridge:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    res = []
    for a, b in merged:
        for x, y in kept:
            for sa, sb in secs:
                lo, hi = max(a, x, sa), min(b, y, sb)
                if hi - lo >= min_s:
                    if lo - max(x, sa) <= bridge:
                        lo = max(x, sa)
                    if min(y, sb) - hi <= bridge:
                        hi = min(y, sb)
                    res.append((round(lo, 2), round(hi, 2)))
    if res:
        checks.append("Held up to the front camera (no face on Camera A, he's at the desk): Camera A full frame at "
                      + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in res) + " (source). Check he's showing something there.")
    return res


def run_to_cut(ranges, kept, checks=None, bridge=3.0):
    """A camera shot never switches in the last / first `bridge` s of a clip: the shot runs on to the cut (bapesta dhgate
    2026-10-25, 2:31: he showed the shoe to the front camera, "so let's check it out", the showing ended 0.5 s before the
    cut into the PC walkthrough and the product camera flashed in right before the slide, "it's too late to transition ...
    we need logic for this"). Hold-ups already did this (find_holdups, dhgate jordan 3); showing.py ranges did not.
    Ranges <= bridge s apart in one clip merge into one shot."""
    if os.environ.get("RG_OFF") == "runtocut":
        return ranges
    out, moved = [], []
    for a, b in sorted(ranges):
        clip = next(((x, y) for x, y in kept if x - 0.05 <= (a + b) / 2 <= y + 0.05), None)
        a2, b2 = a, b
        if clip:
            if 0 < a - clip[0] <= bridge:
                a2 = clip[0]
            if 0 < clip[1] - b <= bridge:
                b2 = clip[1]
        if out and clip and a2 - out[-1][1] <= bridge and clip[0] <= out[-1][1] <= clip[1]:
            out[-1] = (out[-1][0], max(b2, out[-1][1]))
        else:
            out.append((a2, b2))
        if (a2, b2) != (a, b):
            moved.append(f"{fmt(a)}-{fmt(b)} -> {fmt(a2)}-{fmt(b2)}")
    if moved and checks is not None:
        checks.append("Showing shots run on to the cut (no camera switch in a clip's last/first 3 s): " + ", ".join(moved) + " (source).")
    return [(round(a, 3), round(b, 3)) for a, b in out]


def find_subscribes(words, tl, cfg, checks=None):
    """subscribe.mov just before every kept "subscribe". The animation never runs over a cut into the next clip (s25 ultra
    2026-10-23, 0:24: "it still has the animation, so it carries over to the other clip ... just have it earlier"): when it
    would, it starts earlier so it ends ~0.15 s before the cut; a clip too short to hold it gets none."""
    sc = cfg["subscribe"]
    L = sc.get("anim_seconds") or (probe_duration(SKILL / "assets" / "subscribe.mov") or 5.0)
    out, last = [], -1e9
    for w in words:
        if norm(w["w"]).startswith(sc["match"]):
            clip = next(((a, b) for a, b in tl.kept if a <= w["s"] < b), None)
            if clip is None:        # said in cut footage: no animation
                continue
            c0, c1 = tl.to_out(clip[0]), tl.to_out(clip[1] - 1e-3)
            t = max(c0, tl.to_out(w["s"]) - sc["lead_seconds"])
            if t + L > c1 - 0.15:
                t = c1 - 0.15 - L
                if t < c0:
                    if checks is not None:
                        checks.append(f"Subscribe animation skipped at {fmt(w['s'])} (source): its clip is shorter than the "
                                      f"{L:.1f} s animation, it would run over the cut.")
                    continue
            if t - last >= sc["min_gap_seconds"] and t < tl.duration - 1:
                out.append({"word": w["w"], "source": w["s"], "out": round(t, 2)})
                last = t
    return out


def probe_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- step 7: music
def pick_music(project, cfg, checks, n=None):
    if os.environ.get("STUDIO_NO_MUSIC") == "1":   # {{STUDIO_NAME}} New Project "Music" unticked
        checks.append("Music is off for this project ({{STUDIO_NAME}} setting).")
        return []
    mc = cfg["music"]
    # n beats: one per music section (a countdown has intro + N items + bonus + outro) plus spares for back-to-back beds
    names = list(range(n)) if n else cfg["sections"]["names"]
    override = project / "raw" / "music.txt"
    folders = [Path(os.path.expanduser(f)) for f in mc.get("folders", [mc["folder"]])]
    folder = folders[0]  # music.txt names are resolved against the first folder
    hist_path = SKILL / "work" / "music_history.json"
    history = load_json(hist_path, [])
    picks = []
    if override.exists():
        for line in override.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                p = Path(line) if Path(line).is_absolute() else folder / line
                if p.exists():
                    picks.append(p)
                else:
                    checks.append(f"music.txt names a beat that wasn't found: {line}")
    if len(picks) < len(names):
        # the WHOLE {{MUSIC_ROOT}} library (user 2026-10-24: "we've been using the same tracks over and over again, like probably
        # the same 10"): music_lib fits type beats to the product / brand vibe from the title + transcript, vocal-scanned,
        # none from the channel's last 15 videos, different artists per section; a re-render keeps its beats. The old
        # newest-download pool below (it gave three videos the same vaitsez beats on 2026-10-24) is only the fallback.
        try:
            sys.path.insert(0, r"{{KIT}}/tools")
            import music_lib
            # raw/config.json music.skip: beats turned down for this video (a voice-like chop at its start played SOLO
            # during the BONUS slide, top 5 reselling products spring 2026-10-25, 10:24 "a stray bit of my voice"):
            # a re-render drops them and picks fresh ones
            lib = music_lib.pick_for(str(project), n=len(names) - len(picks), min_len=40, role="main", exclude=[str(p) for p in picks],
                                     avoid=[str(x) for x in mc.get("skip", [])])
            picks += [Path(t) for t in lib]
        except Exception as e:
            checks.append(f"Music library picker skipped ({type(e).__name__}: {str(e)[:120]}); used the old type-beat pool.")
    if len(picks) < len(names):
        mine = [h for h in history if h.get("project") == str(project)]
        others = [h for h in history if h.get("project") != str(project)]
        last = set(others[-1]["beats"]) if others else set()
        pool = sorted([p for f in folders for p in f.rglob("*")
                       if p.is_file() and p.suffix.lower() in mc["extensions"]
                       and (mc["match"] in p.name.lower() or mc["match"] in str(f).lower())],
                      key=lambda p: p.stat().st_mtime, reverse=True)
        try:   # copyright-claimed beats are retired for good (Studio Uploads, 2026-10-26)
            pool = [p for p in pool if not music_lib.retired(p)]
        except Exception:  # noqa
            pass
        fresh = [p for p in pool if p.name not in last and p not in picks]
        if mine:  # re-render of the same project keeps its beats
            keep = [f / n for n in mine[-1]["beats"] for f in folders if (f / n).exists()]
            fresh = keep + [p for p in fresh if p not in keep]
        if len(picks) + len(fresh) < len(names):
            fresh += [p for p in pool if p not in fresh and p not in picks]
            checks.append("Not enough new type beats in Downloads, so a beat from the last video was reused.")
        picks += fresh[:len(names) - len(picks)]
    if not picks:
        checks.append("No type beats found in Downloads; the video has no music.")
        return []
    while len(picks) < len(names):
        picks.append(picks[len(picks) % len(picks)])
        checks.append("Fewer than four beats available, so a beat repeats across sections.")
    mdir = project / "work" / "music"
    mdir.mkdir(parents=True, exist_ok=True)
    local = []
    for p in picks:
        dst = mdir / p.name
        if not dst.exists():
            shutil.copy2(p, dst)
        local.append(dst)
    return local


def log_music(project, beats):
    hist_path = SKILL / "work" / "music_history.json"
    hist_path.parent.mkdir(exist_ok=True)
    history = load_json(hist_path, [])
    history = [h for h in history if h.get("project") != str(project)]
    history.append({"project": str(project), "date": time.strftime("%Y-%m-%d"), "beats": [b.name for b in beats]})
    save_json(hist_path, history)


def measure_lufs(path, seconds=None, prefilter=""):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path)]
    if seconds:
        cmd += ["-t", str(seconds)]
    af = f"{prefilter},ebur128" if prefilter else "ebur128"
    r = subprocess.run(cmd + ["-vn", "-af", af, "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -23.0


def voice_eq(project, kept, cfg, checks):
    """Tone-match the voice to his earlier finals: measure the bass (<low_hz) and presence (>high_hz) band levels relative
    to the full voice over the kept footage, correct each toward its target with a capped shelf. Cached in levels.json."""
    vc = cfg.get("voice_eq", {})
    if not vc.get("enabled"):
        return ""
    path = project / "work" / "levels.json"
    lv = load_json(path, {})
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in kept)
    if "voice_bands" not in lv:
        def mean(band):
            r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(project / "raw" / "camera.mp4"), "-vn", "-map", "0:a:0",
                                "-af", f"aselect='{sel}'{',' + band if band else ''},volumedetect", "-f", "null", "-"], capture_output=True, text=True)
            m = re.findall(r"mean_volume:\s*(-?[\d.]+)", r.stderr)
            return float(m[-1]) if m else None
        full, lo, hi = mean(""), mean(f"lowpass=f={vc['low_hz']}"), mean(f"highpass=f={vc['high_hz']}")
        lv["voice_bands"] = {"low": round(lo - full, 2), "high": round(hi - full, 2)} if None not in (full, lo, hi) else {}
        save_json(path, lv)
    b = lv["voice_bands"]
    if not b:
        return ""
    tol = vc["tolerance_db"]
    cut = b["low"] - vc["target_low_db"]
    boost = vc["target_high_db"] - b["high"]
    cut = min(cut, vc["max_cut_db"]) if cut > tol else 0.0
    boost = min(boost, vc["max_boost_db"]) if boost > tol else 0.0
    f = []
    if cut:
        f.append(f"lowshelf=f={vc['low_hz']}:g={-cut:.1f}")
    if boost:
        f.append(f"highshelf=f={vc['high_hz']}:g={boost:.1f}")
    if f:
        checks.append(f"Voice tone matched to earlier videos (bass {b['low']:+.1f} dB, presence {b['high']:+.1f} dB vs the voice): "
                      f"{'bass -%.1f dB' % cut if cut else ''}{', ' if cut and boost else ''}{'presence +%.1f dB' % boost if boost else ''}.")
    return ",".join(f)


def levels(project, music, cfg):
    """Integrated loudness of the voice and each beat, cached in work/levels.json."""
    path = project / "work" / "levels.json"
    lv = load_json(path, {})
    if "voice" not in lv:
        lv["voice"] = measure_lufs(project / "raw" / "camera.mp4")
    for b in music:
        if b.name not in lv:
            lv[b.name] = measure_lufs(b, 240)
    save_json(path, lv)
    return lv



# ---------------------------------------------------------------- zooms (face punch-ins, cursor zooms on the screen)
def _sentence_end(words, i, limit):
    t0 = words[i]["s"]
    for w in words[i:]:
        if w["e"] - t0 > limit:
            return t0 + limit
        if re.search(r"[.!?]$", w["w"]):
            return w["e"]
    return words[-1]["e"]


def _cue_hits(words, cues):
    """(word index, cue) for each cue match; multi-word cues first so 'right here' wins over 'here'."""
    hits = {}
    for cue in sorted(cues, key=lambda c: -len(c.split())):
        cw = cue.split()
        for i in range(len(words) - len(cw) + 1):
            got = [norm(w["w"]) for w in words[i:i + len(cw)]]
            ok = got[0].startswith(cw[0]) if len(cw) == 1 else got == cw
            if ok and not any(abs(i - j) < 3 for j in hits):
                hits[i] = cue
    return sorted(hits.items())


def _face_centre(rows, a, b, kx, ky):
    pts = [(r[kx], r[ky]) for r in rows if a <= r["t"] <= b and r.get(kx) is not None]
    if not pts:
        return None
    return float(np.median([p[0] for p in pts])), float(np.median([p[1] for p in pts]))


def find_zooms(words, rows, sections, cursor_pts, cfg):
    zc = cfg["zooms"]
    events = []
    for s in sections:
        sw = [i for i, w in enumerate(words) if s["start"] + 0.5 <= w["s"] < s["end"] - 1.0]
        if not sw:
            continue
        lo, hi = sw[0], sw[-1] + 1
        sub = words[lo:hi]
        if s["name"] in zc["face_sections"]:
            hits = {lo + i for i, _ in _cue_hits(sub, zc["face_cues"])}
            # sentence starts as filler so the shot never sits still too long
            starts = {lo + i for i, w in enumerate(sub) if i == 0 or re.search(r"[.!?]$", sub[i - 1]["w"])}
            last_end, last_start = s["start"] - 99, s["start"] - 99
            for i in sorted(hits | starts):
                a = words[i]["s"] - 0.1
                if a < last_end + zc["face_min_gap_seconds"]:
                    continue
                if i not in hits and a < last_start + zc["face_every_seconds"]:
                    continue
                b = min(max(_sentence_end(words, i, zc["face_max_hold_seconds"]), a + zc["face_min_hold_seconds"]), s["end"] - 0.2)
                if b - a < zc["face_min_hold_seconds"]:
                    continue
                ca = cb = tuple(zc["face_center"])  # centred punch-in looks natural on both angles
                events.append({"kind": "face", "start": round(a, 2), "end": round(b, 2), "zoom": zc["face_zoom"],
                               "ease": zc["face_ease_seconds"], "a": [round(x, 3) for x in ca], "b": [round(x, 3) for x in cb],
                               "why": words[i]["w"]})
                last_end, last_start = b, a
        if s["name"] in zc["screen_sections"]:
            last_end = s["start"] - 99
            for i, cue in _cue_hits(sub, zc["screen_cues"]):
                i += lo
                a = words[i]["s"] - 0.3
                if a < last_end + zc["screen_min_gap_seconds"]:
                    continue
                pos = cursor_at(cursor_pts, a - 0.5, a + zc["screen_settle_seconds"], zc["screen_min_moves"])
                if pos is None:
                    continue
                b = min(max(_sentence_end(words, i, zc["screen_max_hold_seconds"]), a + zc["screen_min_hold_seconds"]), s["end"] - 0.2)
                events.append({"kind": "screen", "start": round(a, 2), "end": round(b, 2), "zoom": zc["screen_zoom"],
                               "ease": zc["screen_ease_seconds"], "b": [round(pos[0], 3), round(pos[1], 3)], "why": cue})
                last_end = b
    return events


def _ease(a, b, r):
    """0..1 envelope: smoothstep up over r seconds from a, hold, smoothstep down over r seconds to b."""
    up = f"clip((t-{a:.3f})/{r:.3f},0,1)"
    dn = f"clip(({b:.3f}-t)/{r:.3f},0,1)"
    return f"({up}*{up}*(3-2*{up})*{dn}*{dn}*(3-2*{dn}))"


def zoom_filter(events, key, tl):
    """scale+crop chain that zooms one 1920x1080 stream through its events (output time)."""
    evs, wins = [], []
    for e in events:
        if key not in e:
            continue
        a, b = tl.to_out(e["start"]), tl.to_out(e["end"])
        r = min(e["ease"], (b - a) / 2)
        if b - a > 0.3:
            evs.append((_ease(a, b, r), e["zoom"], e[key][0], e[key][1]))
            wins.append((a, b))
    if not evs:
        return ""
    z = "1" + "".join(f"+{zm - 1:.3f}*{env}" for env, zm, _, _ in evs)
    cx = "0.5" + "".join(f"+{x - 0.5:.3f}*{env}" for env, _, x, _ in evs)
    cy = "0.5" + "".join(f"+{y - 0.5:.3f}*{env}" for env, _, _, y in evs)
    # SMOOTH, sub-pixel (watch spreadsheet 2026-10-24: "the screen recording feels like it's jumping all over the place
    # ... the keyframing feels a little bit choppy"): the old per-frame scale rounded the size to 2 px and the crop to whole
    # pixels, so a zoom moved in pixel steps. One perspective transform maps the zoom window (float corners, cubic) onto
    # the frame, the way gaming/body.py moves its cam. The stream is fps=30 from 0 (setpts=N/30/TB): t = (in-1)/30.
    tt = f"((in-1)/{FPS})"
    sub = lambda x: re.sub(r"(?<![a-z_])t(?![a-z_])", tt, x)
    head = f"st(0,{sub(z)});st(1,{sub(cx)});st(2,{sub(cy)});"
    ww, hh_ = f"({OUT_W}/ld(0))", f"({OUT_H}/ld(0))"
    X = f"clip(ld(1)*{OUT_W}-{ww}/2,0,{OUT_W}-{ww})"
    Y = f"clip(ld(2)*{OUT_H}-{hh_}/2,0,{OUT_H}-{hh_})"
    pts = [f"x0='{head}{X}'", f"y0='{head}{Y}'", f"x1='{head}{X}+{ww}'", f"y1='{head}{Y}'",
           f"x2='{head}{X}'", f"y2='{head}{Y}+{hh_}'", f"x3='{head}{X}+{ww}'", f"y3='{head}{Y}+{hh_}'"]
    # only inside the zoom windows (2026-10-25 profiling, bapesta: this warp ran on BOTH cameras on every frame and was
    # ~73 % of the render, 58 s vs 16 s for 60 s of video; between zooms it is the identity, so skipping it is the same picture)
    en = "+".join(f"between(t,{a - 0.05:.3f},{b + 0.05:.3f})" for a, b in wins)
    return f",perspective={':'.join(pts)}:sense=source:interpolation=cubic:eval=frame:enable='{en}'"


def highlight_filter(events, key, tl, sx=1.0, sy=1.0, oy=0):
    """Green outline around a panel a zoom points at (events with "highlight" and a half-frame pixel "box"); drawn
    BEFORE the zoom so it scales with the picture (prada cups 2026-10-22: "zoom in and highlight" the size dropdown)."""
    out = ""
    for e in events:
        if key not in e or not e.get("highlight") or not e.get("box"):
            continue
        a, b = tl.to_out(e["start"]) + e["ease"] * 0.6, tl.to_out(e["end"]) - e["ease"] * 0.6
        if b - a < 0.5:
            continue
        x0, y0, x1, y1 = e["box"]
        out += (f",drawbox=x={int(x0 * sx)}:y={int((y0 - oy) * sy)}:w={int((x1 - x0) * sx)}:h={int((y1 - y0) * sy)}"
                f":color=0x3DFF7A@0.95:t=5:enable='between(t,{a:.3f},{b:.3f})'")
    return out


# ---------------------------------------------------------------- step 5 helpers: circle art
def make_circle_art(work, cfg):
    import cv2
    fc = cfg["face_cam"]
    d, bw = fc["diameter_px"], fc["border_px"]
    ss = 4  # supersample for smooth edges
    mask = np.zeros((d * ss, d * ss), np.uint8)
    cv2.circle(mask, (d * ss // 2, d * ss // 2), d * ss // 2 - ss, 255, -1, cv2.LINE_AA)
    mask = cv2.resize(mask, (d, d), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(work / "circle_mask.png"), mask)
    # frame = soft shadow + white disc, face circle sits on top of it
    pad = fc["shadow_blur_px"] * 2 + fc["shadow_offset_px"]
    outer = d + 2 * bw
    size = outer + 2 * pad
    rgba = np.zeros((size, size, 4), np.float32)
    c = size // 2
    shadow = np.zeros((size * ss, size * ss), np.uint8)
    cv2.circle(shadow, (c * ss, (c + fc["shadow_offset_px"]) * ss), outer * ss // 2, 255, -1, cv2.LINE_AA)
    shadow = cv2.resize(shadow, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    k = fc["shadow_blur_px"] * 2 + 1
    shadow = cv2.GaussianBlur(shadow, (k, k), 0) * fc["shadow_opacity"]
    disc = np.zeros((size * ss, size * ss), np.uint8)
    cv2.circle(disc, (c * ss, c * ss), outer * ss // 2, 255, -1, cv2.LINE_AA)
    disc = cv2.resize(disc, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    alpha = disc + shadow * (1 - disc)
    color = 255.0 if fc["border_color"] == "white" else 0.0
    rgb = np.where(alpha[..., None] > 0, (disc[..., None] * color) / np.maximum(alpha[..., None], 1e-6), 0)
    rgba[..., :3] = rgb
    rgba[..., 3] = alpha * 255
    cv2.imwrite(str(work / "circle_frame.png"), cv2.cvtColor(rgba.clip(0, 255).astype(np.uint8), cv2.COLOR_RGBA2BGRA))
    return pad


# ---------------------------------------------------------------- step 8: render
def pick_encoder(cfg):
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    rc = cfg["render"]
    if sys.platform == "darwin" and "h264_videotoolbox" in enc:
        return "h264_videotoolbox", rc["videotoolbox"]
    if "h264_nvenc" in enc:
        test = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2", "-c:v", "h264_nvenc",
                               "-f", "null", "-"], capture_output=True)
        if test.returncode == 0:
            return "h264_nvenc", rc["nvenc"]
    return "libx264", rc["fallback"]


def edge_margins(cam, W, H, duration, work, checks, n=14, look=24, pad=2):
    """Foreign strips at the edges of each half, measured (ultimate dhgate free reselling spreadsheet 2026-10-23, 1:58: "my
    video is like pixels off on the right ... you don't see that blue on the side ... an editor would have cropped that
    in"; the OBS screen capture had the webcam bleeding 6 px into its right edge, an old-recording layout slip). On n frames
    across the video, for every edge of both halves: the widest band (<= look px) whose inner border is a hard jump (> 5x
    the usual column-to-column change). The median width over the frames + pad px is cropped off, 16:9 kept (build_graph).
    Cached in work/edges.json; delete it to re-measure. Returns {"a": (l, r, t, b), "b": (...)}."""
    f = work / "edges.json"
    if f.exists():
        d = load_json(f)
        return {k: tuple(v) for k, v in d.items()}
    hw = W // 2
    frames = []
    for t in np.linspace(min(60, duration * 0.05), max(duration - 60, duration * 0.95), n):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.1f}", "-i", str(cam), "-frames:v", "1", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) == W * H * 3:
            frames.append(np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.int16))
    out = {}
    for key, x0 in (("a", 0), ("b", hw)):
        m = []
        for edge in "lrtb":
            widths = []
            for fr in frames:
                img = fr[:, x0:x0 + hw]
                band = {"l": img[:, :look + 8], "r": img[:, ::-1][:, :look + 8],
                        "t": img[:look + 8].transpose(1, 0, 2), "b": img[::-1][:look + 8].transpose(1, 0, 2)}[edge]
                d = np.abs(np.diff(band, axis=1)).mean(axis=(0, 2))
                base = np.median(d[12:]) + 1
                w = [k + 1 for k in range(look) if d[k] > max(12, 5 * base)]
                widths.append(max(w) if w else 0)
            # the strip can belong to ONE OBS scene only (dhgate yeezy slides 1:36, 2026-10-23: the side-camera scene had the
            # front camera bleeding 6 px into its left edge, the product-cam and screen scenes had none, so the median
            # over all frames was 0 and nothing was cropped, "part of the other camera that's wanting to jump"). A strip
            # seen on >= 20 % of the frames is cropped at its usual width; cropping it where it isn't costs ~0.4 % zoom.
            nz = [w for w in widths if w > 0]
            med = int(np.median(nz)) if len(nz) >= max(2, 0.2 * len(widths)) else 0
            m.append(med + pad if med > 0 else 0)
        out[key] = tuple(m)
    save_json(f, {k: list(v) for k, v in out.items()})
    for key, (l, r, t, b) in out.items():
        if l or r or t or b:
            checks.append(f"Edge strip on the {'left' if key == 'a' else 'right'} half cropped off: left {l}, right {r}, top {t}, "
                          f"bottom {b} px (work/edges.json).")
    return out


def piece_frames(a, b):
    """frames select(between(t,a,b)) keeps from an fps=FPS stream that starts at 0"""
    import math
    return max(0, math.floor(b * FPS + 1e-6) - math.ceil(a * FPS - 1e-6) + 1)


def build_graph(ctx, loudnorm):
    cfg, tl = ctx["cfg"], ctx["tl"]
    fc, sc, mc = cfg["face_cam"], cfg["subscribe"], cfg["music"]
    hw, hh = ctx["half_w"], ctx["half_h"]
    kept = ctx["kept"]
    trimmed = len(kept) > 1 or kept[0][0] > 0.01 or kept[0][1] < ctx["duration"] - 0.01
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in kept)
    v, a = [], []

    # video: cut, split into the two cameras
    pieces = ctx.get("piece_inputs") if trimmed else None
    if pieces:
        # each kept piece is its own seeked input (render: piece_inputs): only the kept footage is decoded, not the whole
        # recording up to its last kept moment (2026-10-25: 37 min of 4K decoded to keep 13 on reselling spring). Same
        # frames as select(between): frames k/FPS with ceil(a*FPS) <= k <= floor(b*FPS); audio = 48000/FPS samples a frame
        for i, (idx, (pa, pb)) in enumerate(zip(pieces, kept)):
            n = piece_frames(pa, pb)
            v.append(f"[{idx}:v]fps={FPS},trim=end_frame={n},setpts=PTS-STARTPTS[pv{i}]")
        v.append("".join(f"[pv{i}]" for i in range(len(pieces))) +
                 f"concat=n={len(pieces)}:v=1:a=0,setpts=N/{FPS}/TB,split=2[sa][sb]")
    else:
        vsel = f",select='{sel}',setpts=N/{FPS}/TB" if trimmed else ",setpts=PTS-STARTPTS"
        v.append(f"[0:v]fps={FPS}{vsel},split=2[sa][sb]")

    def half_crop(key):
        """16:9 crop of one half, inside the foreign strips at its edges (edge_margins: the webcam bleeding 6 px into the
        screen capture, ultimate dhgate free reselling spreadsheet 1:58 "pixels off on the right ... an editor would have
        cropped that in")."""
        l, r, t, b = ctx.get("edges", {}).get(key, (0, 0, 0, 0))
        aw, ah = hw - l - r, hh - t - b
        cw = min(aw, round(ah * 16 / 9)) // 2 * 2
        ch = min(ah, round(cw * 9 / 16)) // 2 * 2
        x = l + (aw - cw) // 2 + (hw if key == "b" else 0)
        y = int(min(max(ctx["face_y"] * hh - ch / 2, t), hh - b - ch))
        return f"crop={cw}:{ch}:{x}:{y}", dict(sx=OUT_W / cw, sy=OUT_H / ch, oy=y)

    ca, hla = half_crop("a")
    cb, hlb = half_crop("b")
    v.append(f"[sa]{ca},scale={OUT_W}:{OUT_H},split=2[camAz][camAc]")
    v.append(f"[camAz]null{highlight_filter(ctx['zooms'], 'a', tl, **hla)}{zoom_filter(ctx['zooms'], 'a', tl)}[camA]")
    swap = ctx.get("expr_pipB", "0") != "0"   # face circle from the right camera (screen on the left half)
    if swap:
        v.append(f"[sb]{cb},scale={OUT_W}:{OUT_H},split=2[camBz][camBc]")
        v.append(f"[camBz]null{highlight_filter(ctx['zooms'], 'b', tl, **hlb)}{zoom_filter(ctx['zooms'], 'b', tl)}[camB]")
    else:
        v.append(f"[sb]{cb},scale={OUT_W}:{OUT_H}{highlight_filter(ctx['zooms'], 'b', tl, **hlb)}{zoom_filter(ctx['zooms'], 'b', tl)}[camB]")
    v.append(f"[camB][camA]overlay=0:0:enable='{ctx['expr_fullA']}'[v1]")
    # face circle (Camera A, cropped around the face)
    d = fc["diameter_px"]
    side = int(OUT_H * fc["face_zoom"])
    fx = int(min(max(ctx["face_x"] * OUT_W - side / 2, 0), OUT_W - side))
    fy = int(min(max(ctx["face_y_circle"] * OUT_H - side / 2, 0), OUT_H - side))
    v.append(f"[camAc]crop={side}:{side}:{fx}:{fy},scale={d}:{d},format=yuva420p[facesq]")
    v.append(f"[2:v]format=gray,scale={d}:{d}{',split=2[cmask][cmaskB]' if swap else '[cmask]'}")
    v.append("[facesq][cmask]alphamerge[face]")
    if swap:
        bx = int(min(max(ctx["rface_x"] * OUT_W - side / 2, 0), OUT_W - side))
        by = int(min(max(ctx["rface_y"] * OUT_H - side / 2, 0), OUT_H - side))
        v.append(f"[camBc]crop={side}:{side}:{bx}:{by},scale={d}:{d},format=yuva420p[facesqB]")
        v.append("[facesqB][cmaskB]alphamerge[faceB]")
    m, bw, pad = fc["margin_px"], fc["border_px"], ctx["circle_pad"]
    bl, base = broll.broll_filters(ctx["broll"], ctx.get("broll_input0", 0), "v1", cfg)
    v += bl
    frame = f"{ctx['expr_pip']}+{ctx['expr_pipB']}" if swap else ctx["expr_pip"]
    v.append(f"[{base}][1:v]overlay={m - pad}:{m - pad}:enable='{frame}'[v2]")
    v.append(f"[v2][face]overlay={m + bw}:{m + bw}:enable='{ctx['expr_pip']}'[v3]")
    last = "v3"
    if swap:
        v.append(f"[v3][faceB]overlay={m + bw}:{m + bw}:enable='{ctx['expr_pipB']}'[v3b]")
        last = "v3b"
    sw, shh = int(OUT_W * sc["scale"]) // 2 * 2, int(OUT_H * sc["scale"]) // 2 * 2
    sx, sy = (OUT_W - sw) // 2, int(sc["center_y"] - shh / 2)
    for k, s in enumerate(ctx["subs"]):
        idx = ctx["sub_input0"] + k
        v.append(f"[{idx}:v]scale={sw}:{shh},format=yuva420p,setpts=PTS-STARTPTS+{s['out']:.3f}/TB[sub{k}]")
        v.append(f"[{last}][sub{k}]overlay={sx}:{sy}:eof_action=pass[vs{k}]")
        last = f"vs{k}"
    fd, dur = cfg["output"]["fade_seconds"], tl.duration
    fin = "" if ctx.get("intro_joined") else f",fade=t=in:d={fd}"   # an intro is joined in front: cut in clean, no dip to black
    fades = f"{fin},fade=t=out:st={dur - fd:.3f}:d={fd}" if fd > 0 else ""
    hold = cfg["output"].get("end_hold_seconds", 0)
    if hold > 0:   # the last frame holds and fades to black AFTER his last word (rick owens 2026-10-22: "once I say I'll be
        # wearing them out today, let's just end the video there and then fade it to black"; the next word started 0.02 s later)
        # the held frame + fade are added after the render (render: end_hold), on the finished file: inside this graph tpad
        # never fired (the picture still stopped 1.2 s before the audio, two tries)
        fades = fin
    pl, last = callouts.price_filters(ctx["prices"], ctx.get("price_input0", 0), last, cfg)
    v += pl
    if ctx.get("countdown"):
        cv, last = countdown.card_filters(ctx["countdown"], ctx.get("card_input0", 0), last,
                                          cfg.get("countdown", {}).get("card_seconds", 3.0))
        v += cv
    # setsar=1: the camera crops are not exactly 16:9, so scale left final.mp4 at SAR 4311:4312 (square pixels everywhere
    # else; the odd SAR broke every wipe splice 10-24/25)
    v.append(f"[{last}]setsar=1,format=yuv420p{fades}[vout]")

    # audio: voice, ducked music per section, subscribe bells
    # the sound keeps exactly the frames the picture keeps (ceil(a*FPS)..floor(b*FPS), each 1/FPS long): exact a..b lost up
    # to a frame per clip against the picture, 0.125 s by 10:00 of top 5 reselling products spring (2026-10-26), so the
    # Timeline-placed bonus slide went in after the next clip's first sound ("today, wh- [slide] -ich is going")
    import math
    fsel = "+".join(f"between(t,{math.ceil(a * FPS - 1e-6) / FPS:.4f},{(math.floor(b * FPS + 1e-6) + 1) / FPS - 1e-5:.5f})"
                    for a, b in kept)
    asel = f",aselect='{fsel}',asetpts=N/SR/TB" if trimmed else ",asetpts=PTS-STARTPTS"
    ref = ctx["levels"]["voice"]  # music is set relative to the voice; the voice itself is not boosted here
    veq = f",{ctx['voice_eq']}" if ctx.get("voice_eq") else ""
    vcomp = ctx["cfg"].get("voice_comp", {})
    if vcomp.get("enabled", True):
        # gentle leveler so a take recorded hotter than the one before doesn't jump at the cut
        # (dhgate asics 2026-10-22 at 1:06: +4-6 dB step into "We do have the shoe box")
        veq += (f",acompressor=threshold={vcomp.get('threshold_db', -26)}dB:ratio={vcomp.get('ratio', 3)}"
                f":attack={vcomp.get('attack_ms', 10)}:release={vcomp.get('release_ms', 300)}:makeup={vcomp.get('makeup_db', 2)}dB")
    lift = ctx.get("voice_lift") or []
    if lift:   # quiet lines (he sat back from the mic): a gain envelope with 0.15 s ramps, before the leveler
        terms = "+".join(f"{10 ** (g / 20) - 1:.3f}*clip(min((t-{x - 0.15:.2f})/0.15,({y + 0.15:.2f}-t)/0.15),0,1)" for x, y, g in lift)
        veq = f",volume='max(0.2,1+{terms})':eval=frame" + veq
    if pieces:
        # the SOUND still comes from the whole recording through aselect (an audio-only input, cheap to decode): per-piece
        # seeked audio drifted up to 87 ms late against his lips by the end of bapesta (old way within +-14 ms, measured
        # against the raw mic 2026-10-25). Only the 4K picture decode was worth cutting
        a.append(f"[{ctx['audio_input']}:a]aformat=sample_rates=48000:channel_layouts=stereo{asel}{veq},asplit=2[voice][scin]")
    else:
        a.append(f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo{asel}{veq},asplit=2[voice][scin]")
    mix = ["[voice]"]
    if ctx["music"]:
        parts = []
        for i, (sec, beat_idx) in enumerate(zip(ctx.get("music_sections") or ctx["out_sections"], ctx["music_inputs"])):
            ln = sec["end"] - sec["start"]
            if ln <= 0.5:
                continue
            fo = min(mc["fade_out_seconds"], ln / 2)
            beat = ctx["music"][ctx["music_inputs"].index(beat_idx)]
            db = mc["idle_db"].get(sec["name"], -14) + ref - ctx["levels"][beat.name]
            ctx.setdefault("beat_db", {})[sec["name"]] = (str(beat), db)
            # a transition into this section already played the beat's first seconds on its own: carry on from there
            skip = ctx["cfg"].get("transitions", {}).get("seconds", 0.5)                 if any(tr["to"] == sec["name"] for tr in ctx.get("transitions") or []) else 0.0
            fin_d = 0.05 if skip else mc["fade_in_seconds"]
            # every beat goes through a peak limiter first: a clipped impact (+2.3 dBFS at 124.5 s of a trap beat) got through
            # the duck's attack under his voice as "a weird split-second blip ... it pops up out of nowhere" (best sp5der
            # hoodie 2026-10-23, 6:30 "how confident you are with it")
            lim = mc.get("bed_limit", 0.5)
            # a cutaway with its own sound inside this section (s25 ultra 2026-10-23, 4:25: "we need logic to keep the music
            # going ... it shouldn't have a section without music"): the beat plays ON under the cutaway (splice_inserts mixes
            # that stretch in, ducked under its voice), so here the same stretch is skipped and the beat carries on after it
            # from where the cutaway left it, no repeated or jumped bars
            gap, hole = 0.0, ""
            for ins in sorted(ctx.get("inserts") or [], key=lambda x: x["out"]):
                if sec["start"] < ins["out"] < sec["end"]:
                    rel = ins["out"] - sec["start"]
                    ctx.setdefault("insert_music", {})[round(ins["out"], 3)] = (str(beat), db, skip + rel + gap)
                    # each aselect sees the timeline the one before it already shortened: the hole sits at rel
                    hole += f"aselect='not(between(t,{rel:.3f},{rel + ins['len']:.3f}))',asetpts=N/SR/TB,"
                    gap += ins["len"]
            a.append(f"[{beat_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     + (f"alimiter=limit={lim}:attack=1:release=60:level=0:asc=1," if lim else "") +
                     f"atrim={skip}:{skip + ln + gap:.3f},asetpts=PTS-STARTPTS,{hole}"
                     f"afade=t=in:d={fin_d},afade=t=out:st={ln - fo:.3f}:d={fo:.3f},volume={db:.2f}dB,"
                     f"adelay={int(sec['start'] * 1000)}:all=1[m{i}]")
            parts.append(f"[m{i}]")
        a.append(f"{''.join(parts)}amix=inputs={len(parts)}:normalize=0:duration=longest[mus]")
        a.append(f"[mus][scin]sidechaincompress=threshold={mc['duck_threshold']}:ratio={mc['duck_ratio']}:"
                 f"attack={mc['duck_attack_ms']}:release={mc['duck_release_ms']}[mduck]")
        mix.append("[mduck]")
    else:
        a.append("[scin]anullsink")
    for k, s in enumerate(ctx["subs"]):
        idx = ctx["sub_input0"] + k
        a.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={sc['bell_db']}dB,"
                 f"adelay={int(s['out'] * 1000)}:all=1[bell{k}]")
        mix.append(f"[bell{k}]")
    cl, labels = callouts.price_audio(ctx["prices"], ctx.get("price_input0", 0), cfg)
    a += cl
    mix += labels
    if ctx.get("pops"):
        import pop_sfx
        pl_, plab = pop_sfx.filters(ctx["pops"], ctx["pop_input0"])
        a += pl_
        mix += plab
    a.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,{loudnorm}[aout]")
    return v, a


def splice_inserts(final, inserts, ctx, checks, W=OUT_W, H=OUT_H):
    """Cutaways that play WITH their own sound (broll.plan_inserts; s25 ultra 2026-10-23, the camera test before "my final
    opinion"): the main edit pauses at each insert point (a sentence start), the clip's kept pieces play full screen (a 4:3
    phone clip sits on a blurred copy of itself) at the main edit's loudness, then the main edit carries on. Done on the
    finished file, so every overlay time inside the main graph stays as it is. Returns [(out, len)] of the inserts."""
    if not inserts:
        return []
    cfg = ctx["cfg"]
    work = final.parent.parent / "work"
    enc_name, enc = pick_encoder(cfg)
    target = measure_lufs(final)
    bc = cfg["broll"]
    made = []
    for k, ins in enumerate(sorted(inserts, key=lambda x: x["out"])):
        seg = work / f"insert_{k}.mp4"
        v, a, n = [], [], len(ins["keep"])
        for j, (s0, s1) in enumerate(ins["keep"]):
            v.append(f"[0:v]trim=start={s0:.3f}:end={s1:.3f},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[iv{j}]")
            a.append(f"[0:a]atrim=start={s0:.3f}:end={s1:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"afade=t=in:d=0.06,afade=t=out:st={max(0.0, s1 - s0 - 0.08):.3f}:d=0.08[ia{j}]")
        g = v + a + ["".join(f"[iv{j}][ia{j}]" for j in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]",
                     f"[cv]split=2[bg][fg]",
                     f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:2,eq=brightness=-0.08[bgb]",
                     f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease,{bc['grade']}[fgs]",
                     f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[vo]",
                     f"[ca]loudnorm=I={target:.1f}:TP=-1.5:LRA=11,aresample=48000[ao]"]
        extra_in = []
        bed = (ctx.get("insert_music") or {}).get(round(ins["out"], 3))
        if bed:   # the section's beat keeps going under the cutaway, ducked under its voice like the main edit
            mc = cfg["music"]
            gain = ctx.get("loudness", {}).get("gain", 0.0)
            ln_i = ins["len"]
            extra_in = ["-stream_loop", "-1", "-i", bed[0]]   # looped like the main render: the offset is past one play
            g[-1] = f"[ca]loudnorm=I={target:.1f}:TP=-1.5:LRA=11,aresample=48000,asplit=2[iv][isc]"
            lim = mc.get("bed_limit", 0.5)
            g += [f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                  + (f"alimiter=limit={lim}:attack=1:release=60:level=0:asc=1," if lim else "") +
                  f"atrim={bed[2]:.3f}:{bed[2] + ln_i + 0.5:.3f},"
                  f"asetpts=PTS-STARTPTS,volume={bed[1] + gain:.2f}dB[ibed]",
                  f"[ibed][isc]sidechaincompress=threshold={mc['duck_threshold']}:ratio={mc['duck_ratio']}:"
                  f"attack={mc['duck_attack_ms']}:release={mc['duck_release_ms']}[iduck]",
                  f"[iv][iduck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.84:level=0[ao]"]
        r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", ins["file"], *extra_in, "-filter_complex", ";".join(g),
                            "-map", "[vo]", "-map", "[ao]", *enc, "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
                            "-b:a", cfg["output"]["audio_bitrate"], "-ar", "48000", str(seg)], capture_output=True, text=True)
        if r.returncode != 0 or not seg.exists():
            checks.append(f"Cutaway {Path(ins['file']).name} could not be rendered ({r.stderr.strip()[-160:]}); left out.")
            continue
        made.append((ins, seg, probe_duration(seg) or ins["len"]))
    if not made:
        return []
    total = probe_duration(final)
    inputs, v, a, parts, t0 = ["-i", str(final)], [], [], [], 0.0
    cuts = [m[0]["out"] for m in made] + [total]
    for j, t1 in enumerate(cuts):
        fi = "afade=t=in:d=0.08," if j else ""
        fo = f",afade=t=out:st={max(0.0, t1 - t0 - 0.1):.3f}:d=0.1" if j < len(made) else ""
        # setsar=1 on BOTH sides: final.mp4 can carry SAR 4311:4312 and concat refuses unequal SARs (-22)
        v.append(f"[0:v]trim=start={t0:.3f}:end={t1:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[mv{j}]")
        a.append(f"[0:a]atrim=start={t0:.3f}:end={t1:.3f},asetpts=PTS-STARTPTS,{fi}aformat=sample_rates=48000:channel_layouts=stereo{fo}[ma{j}]")
        parts.append(f"[mv{j}][ma{j}]")
        if j < len(made):
            inputs += ["-i", str(made[j][1])]
            v.append(f"[{j + 1}:v]setsar=1,format=yuv420p[cv{j}]")
            parts.append(f"[cv{j}][{j + 1}:a]")
        t0 = t1
    g = v + a + ["".join(parts) + f"concat=n={len(parts)}:v=1:a=1[vo][ao]"]
    tmp = final.with_name("final_spliced.mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g),
                        "-map", "[vo]", "-map", "[ao]", *enc, "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
                        "-b:a", cfg["output"]["audio_bitrate"], "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        print(f"!! Cutaway splice failed: {r.stderr.strip()[-300:]}")
        checks.insert(0, f"⚠️ NOT DONE: cutaway splice failed ({r.stderr.strip()[-200:]}); the video has no cutaway.")
        return []
    tmp.replace(final)
    return [(m[0]["out"], round(m[2], 3)) for m in made]


def section_transitions(sections, kept, rows, tl, cfg):
    """Where the video changes segment (s25 ultra 2026-10-23, user: "the intro gets its own audio, then that small portion,
    then the product showcase on the desktop, then the final outro ... make up transitions for these segments ... a slide
    effect ... this should be a rule going forward"). One point per section change, always ON a cut (never mid-sentence):
    the kept clip start nearest the section start; for the showcase the first kept clip that opens on the desktop
    recording (the fallback put the s25 showcase start inside "can you resell it? It is on the spreadsheet", the desktop
    only appears 100 s later). Returns [{"src", "out", "from", "to"}]."""
    tc = cfg.get("transitions", {})
    if not tc.get("enabled", True):
        return []
    starts = [a for a, b in kept[1:]]
    out = []
    for prev, s in zip(sections, sections[1:]):
        t = None
        if s["name"] == "showcase":
            scr = lambda a: any(a - 0.1 <= r["t"] <= a + 2.0 and (r.get("right") == "screen" or r.get("left") == "screen") for r in rows)
            t = next((a for a in starts if a >= s["start"] - 30 and a <= s["start"] + tc.get("showcase_reach_seconds", 180) and scr(a)), None)
        if t is None:
            near = [a for a in starts if abs(tl.to_out(a) - tl.to_out(s["start"])) <= tc.get("snap_seconds", 12)]
            t = min(near, key=lambda a: abs(tl.to_out(a) - tl.to_out(s["start"]))) if near else None
        if t is None or (out and t <= out[-1]["src"]):
            continue
        out.append({"src": round(t, 3), "out": round(tl.to_out(t), 3), "from": prev["name"], "to": s["name"]})
    return out


def _true_cut(final, T, reach=0.25):
    """The timestamp of the first frame of the NEW shot near T, read from the frames' own pts (s25 ultra, rounds 4 and 5:
    one frame of the desktop flashed before the slide; a seek + fps filter put the guess one frame late twice). The
    biggest frame difference within +-reach; T itself when nothing changes there."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(final), "-vf",
                        f"trim=start={max(0, T - reach):.3f}:end={T + reach:.3f},showinfo,scale=64:36,format=gray",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True)
    pts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr.decode(errors="replace"))]
    f = np.frombuffer(r.stdout, np.uint8)
    f = f[: len(f) // 2304 * 2304].reshape(-1, 36, 64).astype(np.float32)
    n = min(len(f), len(pts))
    if n < 3:
        return T
    d = np.abs(np.diff(f[:n], axis=0)).mean(axis=(1, 2))
    k = int(np.argmax(d))
    # half a frame BEFORE the new shot's pts: rounding 315.1667 up to 315.167 kept that frame in "everything before T"
    return round(pts[k + 1] - 1 / 60, 4) if d[k] > 12 else T


def splice_transitions(final, ctx, checks, W=OUT_W, H=OUT_H):
    """The slide between segments, spliced into the finished file like a cutaway: the last frame of the old segment slides
    out to the left while the first frame of the new one slides in, a white line riding the seam, a whoosh, and the new
    segment's beat playing on its own for those `seconds` (its music in the main render starts that far in, so the beat
    runs on seamlessly under his voice). The music switch is HEARD at the change, not just a beat ducked 20 dB under
    the voice. Returns [(final time before this splice, seconds)]."""
    trans = ctx.get("transitions") or []
    if not trans:
        return []
    cfg = ctx["cfg"]
    tc = cfg.get("transitions", {})
    d = tc.get("seconds", 0.5)
    work = final.parent.parent / "work"
    enc_name, enc = pick_encoder(cfg)
    gain = ctx.get("loudness", {}).get("gain", 0.0)
    whoosh = Path(tc.get("sfx", r"{{KIT}}/tools\intro_library\kit\sfx\whoosh-short.mp3"))
    shift = lambda t: t + sum(ln for o, ln in (ctx.get("inserted") or []) if o <= t + 1e-3)   # cutaways before it
    made = []
    for k, tr in enumerate(trans):
        # reach 1 frame (0.07 still let a motion frame 4 frames late win; the voice starts 0.06 s after that cut), not
        # 0.25 s: the cut time is frame-accurate already, and between two shots of the SAME camera the
        # biggest frame change can sit inside the next clip, so the slide went in after its first sound ("bonus item of
        # today, wi- [slide] which", top 5 reselling products spring 2026-10-25, 10:28 "be careful with half-words at a cut")
        T = _true_cut(final, round(round(shift(tr["out"]) * 30) / 30, 3), reach=cfg.get("transitions", {}).get("cut_reach", 0.02))
        a_png, b_png, clip = work / f"trans_{k}_a.png", work / f"trans_{k}_b.png", work / f"trans_{k}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, T - 0.05):.3f}", "-i", str(final), "-frames:v", "1", str(a_png)])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{T + 0.02:.3f}", "-i", str(final), "-frames:v", "1", str(b_png)])
        beat = (ctx.get("beat_db") or {}).get(tr["to"])
        inputs = ["-loop", "1", "-t", f"{d}", "-i", str(a_png), "-loop", "1", "-t", f"{d}", "-i", str(b_png)]
        g = [f"[0:v]fps={FPS},scale={W}:{H},format=yuv420p,setsar=1[ta]", f"[1:v]fps={FPS},scale={W}:{H},format=yuv420p,setsar=1[tb]",
             f"[ta][tb]xfade=transition=slideleft:duration={d}:offset=0,"
             f"drawbox=x='iw*(1-t/{d})-6':y=0:w=12:h=ih:color=white@0.9:t=fill,format=yuv420p[vo]"]
        mix = []
        if whoosh.exists():
            inputs += ["-i", str(whoosh)]
            g.append(f"[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={tc.get('sfx_db', -8) + gain:.2f}dB,"
                     f"apad=whole_dur={d},atrim=0:{d}[sw]")
            mix.append("[sw]")
        if beat:
            inputs += ["-i", beat[0]]
            g.append(f"[{3 if whoosh.exists() else 2}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"alimiter=limit=0.5:attack=1:release=60:level=0:asc=1,"   # the same bed limiter as the main mix
                     f"atrim=0:{d},asetpts=PTS-STARTPTS,afade=t=in:d=0.08,volume={beat[1] + gain:.2f}dB[bt]")
            mix.append("[bt]")
        if mix:
            g.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0,apad=whole_dur={d},atrim=0:{d},alimiter=limit=0.84:level=0[ao]")
        else:
            g.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d}[ao]")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[vo]",
                            "-map", "[ao]", "-t", f"{d}", *enc, "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
                            "-b:a", cfg["output"]["audio_bitrate"], "-ar", "48000", str(clip)], capture_output=True, text=True)
        if r.returncode != 0 or not clip.exists():
            checks.append(f"Transition {tr['from']} -> {tr['to']} could not be rendered ({r.stderr.strip()[-160:]}); hard cut there.")
            continue
        made.append((tr, T, clip, probe_duration(clip) or d))
    if not made:
        return []
    total = probe_duration(final)
    inputs, v, a, parts, t0 = ["-i", str(final)], [], [], [], 0.0
    cuts = [m[1] for m in made] + [total]
    for j, t1 in enumerate(cuts):
        # setsar=1 on BOTH sides: final.mp4 can carry SAR 4311:4312 and concat refuses unequal SARs (-22),
        # which silently turned every wipe into a hard cut (10-24/25: prada glasses, cologne, canada goose, lv skatesta)
        v.append(f"[0:v]trim=start={t0:.3f}:end={t1:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[mv{j}]")
        a.append(f"[0:a]atrim=start={t0:.3f}:end={t1:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[ma{j}]")
        parts.append(f"[mv{j}][ma{j}]")
        if j < len(made):
            inputs += ["-i", str(made[j][2])]
            v.append(f"[{j + 1}:v]setsar=1,format=yuv420p[tv{j}]")
            parts.append(f"[tv{j}][{j + 1}:a]")
        t0 = t1
    g = v + a + ["".join(parts) + f"concat=n={len(parts)}:v=1:a=1[vo][ao]"]
    tmp = final.with_name("final_trans.mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g),
                        "-map", "[vo]", "-map", "[ao]", *enc, "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
                        "-b:a", cfg["output"]["audio_bitrate"], "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        print(f"!! Transition splice failed: {r.stderr.strip()[-300:]}")
        checks.insert(0, f"⚠️ NOT DONE: transition splice failed ({r.stderr.strip()[-200:]}); hard cuts between segments.")
        return []
    tmp.replace(final)
    checks.append("Segment transitions (slide + whoosh + the new beat on its own for "
                  f"{d} s): " + ", ".join(f"{m[0]['from']} -> {m[0]['to']} at {fmt(m[1])}" for m in made) + " (main edit).")
    return [(m[0]["out"], round(m[3], 3)) for m in made]


def has_intro(project):
    """The Studio joins an intro in front of final.mp4 (intro VO or finished intro in studio.json). Then the main edit must
    not fade in from black: it showed as a dip right after the title card (prada cups 2026-10-22, "the black screen ... let's go")."""
    try:
        slots = json.loads((project / "studio.json").read_text(encoding="utf-8-sig")).get("slots", {})
        return bool(slots.get("intro") or slots.get("intro_vo"))
    except (OSError, ValueError):
        return False


def render(project, ctx, checks):
    cfg = ctx["cfg"]
    work, out = project / "work", project / "output"
    dur = ctx["tl"].duration
    # read the recording only up to just past the last kept moment: the picture ends there (an end hold can clone the
    # last frame; dhgate rick owens 2026-10-22 the hold never fired while ffmpeg was still reading 16 more minutes)
    cam = str(project / "raw" / "camera.mp4")
    kept = ctx["kept"]
    # ON (tested 2026-10-25 on bapesta, old vs new: same 14 987 frames and length, lip sync identical at every piece
    # against the raw mic, frames identical but a 1-frame motion offset inside one B-roll clip; render 357 -> 333 s, more
    # on long, heavily cut recordings). render.piece_inputs false or REVIEW_PIECE_INPUTS=0 = the old whole-file read
    use_pieces = cfg.get("render", {}).get("piece_inputs", True) and os.environ.get("REVIEW_PIECE_INPUTS") != "0" \
        and len(kept) > 1
    # input 0 = the whole recording (old way) or only its first kept piece; the other pieces go LAST (below), so every
    # other input keeps its number
    first = (["-ss", f"{kept[0][0]:.3f}", "-t", f"{kept[0][1] - kept[0][0] + 1.0:.3f}", "-i", cam] if use_pieces
             else ["-t", f"{kept[-1][1] + 1.0:.3f}", "-i", cam])
    inputs = [*first,
              "-loop", "1", "-t", f"{dur:.3f}", "-i", str(work / "circle_frame.png"),
              "-loop", "1", "-t", f"{dur:.3f}", "-i", str(work / "circle_mask.png")]
    def n_inputs():
        return inputs.count("-i")
    ctx["music_inputs"] = []
    for b in ctx["music"]:
        ctx["music_inputs"].append(n_inputs())
        inputs += ["-stream_loop", "-1", "-i", str(b)]
    # a quiet, rotating pop sound on each clip of his own footage (pop_sfx, watch spreadsheet 2026-10-24)
    import pop_sfx
    ctx["pops"] = pop_sfx.plan(ctx["broll"]) if cfg["broll"].get("pop_sfx", True) else []
    ctx["pop_input0"] = n_inputs()
    for s_ in ctx["pops"]:
        inputs += ["-i", s_["file"]]
    ctx["sub_input0"] = n_inputs()
    for _ in ctx["subs"]:
        inputs += ["-i", str(SKILL / "assets" / "subscribe.mov")]
    ctx["price_input0"] = n_inputs()
    for pr in ctx["prices"]:
        inputs += ["-loop", "1", "-t", f"{pr.get('hold', cfg['price']['hold_seconds'])}", "-i", pr["card"], "-i", str(pr.get("sound") or ctx["cash"])]
    ctx["card_input0"] = n_inputs()   # countdown number cards (countdown.py)
    for it in ctx.get("countdown") or []:
        inputs += ["-loop", "1", "-t", f"{cfg.get('countdown', {}).get('card_seconds', 3.0):.2f}", "-i", it["card"]]
    ctx["broll_input0"] = n_inputs()
    for c in ctx["broll"]:
        if c.get("named"):   # a moment deep inside another 20-min recording: seek the input, don't decode up to it
            inputs += ["-ss", f"{c['src_start']:.3f}", "-i", c["file"]]
            c["src_start"] = 0.0
        else:
            inputs += ["-i", c["file"]]
    ctx["piece_inputs"] = None
    if use_pieces:
        ctx["piece_inputs"] = [0]
        for a_, b_ in kept[1:]:
            ctx["piece_inputs"].append(n_inputs())
            inputs += ["-ss", f"{a_:.3f}", "-t", f"{b_ - a_ + 1.0:.3f}", "-i", cam]
        ctx["audio_input"] = n_inputs()   # the whole recording's sound, picture not decoded (-vn)
        inputs += ["-vn", "-t", f"{kept[-1][1] + 1.0:.3f}", "-i", cam]

    lufs, tp = cfg["output"]["loudness_lufs"], cfg["render"]["true_peak"]
    # pass 1 (audio only): measure the mix loudness; the final gain moves toward the target
    # but never boosts more than max_boost_db and never turns the video down
    _, a1 = build_graph(ctx, f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json")
    g1 = work / "graph_audio.txt"
    g1.write_text(";\n".join(a1), encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *inputs, "-/filter_complex", str(g1),
                        "-map", "[aout]", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)
    boost = cfg["output"]["max_boost_db"]
    if m:
        measured = float(json.loads(m.group(0))["input_i"])
        gain = min(max(lufs - measured, 0.0), boost)
    else:
        measured, gain = None, 0.0
        checks.append("Loudness measurement failed; the volume was left as recorded.")
    ctx["loudness"] = {"measured": measured, "gain": round(gain, 2)}
    limit = 10 ** (tp / 20)
    ln = f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=false:attack=5:release=50"

    # pass 2: the one full-quality render
    fd = cfg["output"]["fade_seconds"]
    afin = "" if ctx.get("intro_joined") else f",afade=t=in:d={fd}"
    afades = f"{afin},afade=t=out:st={dur - fd:.3f}:d={fd}" if fd > 0 else ""
    hold = cfg["output"].get("end_hold_seconds", 0)
    if hold > 0:   # silence under the held last frame; the music fades with the picture
        afades = f"{afin},apad=pad_dur={hold},afade=t=out:st={dur:.3f}:d={hold}"
    v, a = build_graph(ctx, ln + afades + ",aresample=48000")
    g2 = work / "graph_final.txt"
    g2.write_text(";\n".join(v + a), encoding="utf-8")
    enc_name, enc = pick_encoder(cfg)
    ctx["encoder"] = enc_name
    final = out / "final.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-stats", "-y", *inputs, "-/filter_complex", str(g2),
           "-map", "[vout]", "-map", "[aout]", *enc, "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", cfg["output"]["audio_bitrate"], "-sn", "-movflags", "+faststart",
           "-t", f"{dur + max(0, hold):.3f}", str(final)]
    (work / "render_cmd.json").write_text(json.dumps(cmd), encoding="utf-8")   # replayable (speed profiling)
    t_render = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    ctx["render_seconds"] = round(time.time() - t_render, 1)
    if r.returncode != 0:
        (work / "render_error.txt").write_text(r.stderr, encoding="utf-8")
        raise RuntimeError("Final render failed; see work/render_error.txt")
    if hold > 0:   # hold the last frame and fade it to black under the padded audio (video re-encoded, audio copied)
        held = out / "final_hold.mp4"
        r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(final), "-vf",
                            f"tpad=stop_mode=clone:stop_duration={hold},fade=t=out:st={dur:.3f}:d={hold},format=yuv420p",
                            *enc, "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "copy", "-movflags", "+faststart", str(held)],
                           capture_output=True, text=True)
        if r.returncode == 0 and held.exists():
            held.replace(final)
        else:
            checks.append(f"End hold failed ({r.stderr.strip()[-160:]}); the video ends without the fade to black.")
    ctx["inserted"] = splice_inserts(final, ctx.get("inserts", []), ctx, checks)   # cutaways with their own sound
    ctx["trans_made"] = splice_transitions(final, ctx, checks)                       # slides between the segments
    ph = cfg["output"]["preview_height"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vf", f"scale=-2:{ph}", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-sn",
                    str(out / f"preview_{ph}p.mp4")], check=True)
    return final


# ---------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fresh = "--fresh" in sys.argv
    project = Path(args[0]).resolve()
    work, out = project / "work", project / "output"
    work.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    cfg = deep_merge(load_json(HERE / "config.json"), load_json(project / "raw" / "config.json", {}))
    AIR.update(before=cfg.get("joins", {}).get("air_before", AIR["before"]), after=cfg.get("joins", {}).get("air_after", AIR["after"]))
    checks = []
    # the rule gate (2026-10-26): say so when this build runs on pipeline code that has not passed rule_gate.py yet
    try:
        sys.path.insert(0, "{{KIT}}/tools/regress")
        import rule_gate
        ug = [os.path.basename(f) for f in rule_gate.ungated_files() if f.endswith((".py", ".js", ".json"))]
        if ug:
            checks.append(f"Built on ungated code ({len(ug)} file(s) not through the rule gate yet: {', '.join(sorted(set(ug))[:8])}).")
    except Exception:  # noqa: never stops a build
        pass
    cam = project / "raw" / "camera.mp4"
    xml_file = next(iter(sorted((project / "raw").glob("*.xml"))), None) or \
        next(iter(sorted((project / "raw").glob("*.fcpxml"))), None)
    xml_kept = None
    if xml_file:
        xml_media, xml_kept = xml_cuts.parse(xml_file)     # Gling edit list -> original file (all audio tracks)
        override = project / "raw" / "source.mp4"          # manual override: use THIS as the source
        if override.exists():                              # (e.g. the original was replaced/damaged)
            xml_media = override
            checks.append("Using raw/source.mp4 as the source instead of the file named in the XML.")
        else:
            sib = xml_media.with_suffix(".mkv")            # OBS originals exist as .mp4 + .mkv;
            if sib.exists():                               # the mkv may carry MORE audio tracks
                import audio_mix as _am
                if _am.audio_stream_count(sib) > _am.audio_stream_count(xml_media):
                    xml_media = sib
                    checks.append(f"Using {sib.name} (more audio tracks than the mp4 named in the XML).")
        checks.append(f"Edit list from {xml_file.name}: cuts from Gling applied to the original file ({xml_media.name}).")
    if not cam.exists() and not xml_file:
        (out / "report.md").write_text("# Report\n\n## Check these\n- raw/camera.mp4 is missing, so nothing was edited.\n")
        print(f"Stopped: raw/camera.mp4 missing. Report: {out / 'report.md'} (1 item in Check these)")
        return
    if not xml_file:
        # a recording in several files (main take + OBS continuation): join them first (lv trainer 2026-10-23, parts.py)
        import parts
        parts.ensure_joined(project, checks)
    if fresh:
        for f in ["transcript.json", "analysis.json", "sections.json", "cuts.json", "angles.json", "zooms.json", "cursor.json", "levels.json", "broll_plan.json"]:
            (work / f).unlink(missing_ok=True)
        audio_mix.restore_original(project)
    if xml_file:
        audio_mix.ensure_source(project, xml_media)   # link the original first; the mic mix is
                                                    # decided AFTER analysis knows the screen start
    else:
        audio_mix.ensure_mixed(project, cfg, checks, kept=xml_kept)  # two-mic swap (DJI when the main mic drops)
    if (project / "raw" / "screen.mp4").exists():
        checks.append("raw/screen.mp4 exists but this script uses the screen shown in the camera file's right half; "
                      "the separate screen recording was not used.")

    W, H, duration = probe(cam)
    half_w, half_h = W // 2, H

    words = transcribe(project, cfg)                       # step 1
    rows = analyze(project, cfg, SKILL)                    # face + right-half analysis
    rows = screen_chrome.chrome_rows(rows, cam, work, half_w, half_h, checks)   # photo-heavy desktop pages = the screen
    # desktop on the LEFT half, face cam on the right (dhgate asics 2026-10-22: the buying walkthrough showed his face
    # instead of the screen): those stretches count as the screen picture everywhere (sections, try-on end, circle
    # rules), and the layout swaps halves there — full-frame left half, face circle from the right camera
    # >= 3 s: a white dust bag held up to Camera A for 1 s read as a screen and swapped the layout (prada cups 2026-10-22,
    # "swipes over to my full facecam but still has the facecam")
    lmin = cfg["face_cam"].get("left_screen_min_seconds", 3.0)
    left_screen = [(a, b) for k, a, b in runs_of(rows, "left") if k == "screen" and b - a >= lmin] if rows and "left" in rows[0] else []
    # a < 1.5 s "camera" blip INSIDE a desktop stretch is a misread (the shoe photo on the store page read as his face),
    # not the camera coming back: the stretches either side are one (maison mahara dhgae review 2026-10-26, 3:41: "my
    # webcam disappears" - the layout swapped back for 0.8 s and the face circle showed the store page)
    gmax = cfg["face_cam"].get("left_screen_gap_merge_seconds", 1.5)
    merged_ls = []
    for a, b in left_screen:
        if merged_ls and a - merged_ls[-1][1] <= gmax:
            merged_ls[-1] = (merged_ls[-1][0], b)
        else:
            merged_ls.append((a, b))
    left_screen = merged_ls
    # ...and a SHORT bright run that is not pixel-flat, with his face on Camera A just before and after, is a product held
    # right up to the lens (top 5 reselling products spring 2026-10-25, 10:05: pink shorts read as the desktop for 3.6 s,
    # the layout swapped and a 1 s desk-camera flash followed, "we need detection for quick flashes"). Screen captures are
    # flat >= 0.57 (desktop 0.62, link pages 0.85); held fabric peaked at 0.51. Fired on no approved review.
    lp = cfg["face_cam"].get("left_screen_product_max_seconds", 8.0)
    held = [(a, b) for a, b in left_screen if b - a < lp
            and float(np.median([r.get("lflat") or 0 for r in rows if a <= r["t"] <= b])) < 0.52
            and any(r.get("fx") is not None for r in rows if a - 3 <= r["t"] < a)
            and any(r.get("fx") is not None for r in rows if b < r["t"] <= b + 3)]
    if held:
        left_screen = [x for x in left_screen if x not in held]
        rows = [dict(r, left="cam") if any(a <= r["t"] <= b for a, b in held) else r for r in rows]
        checks.append("Bright close-ups held up to Camera A (not the desktop): "
                      + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in held) + " (source).")
    rows = [dict(r, right="screen", rfx_face=r.get("rfx"), rfy_face=r.get("rfy")) if any(a <= r["t"] <= b for a, b in left_screen) else r
            for r in rows]
    # a blank browser new tab on the desktop half is never the shot: his talking camera instead ($30k 2026-10-26, 7:56)
    idle_scr = []
    try:
        ic = load_json(work / "idle_screens.json") or {}
        if ic.get("runs") == [list(x) for x in left_screen]:
            idle_scr = [tuple(x) for x in ic.get("idle", [])]
        else:
            idle_scr = screen_chrome.idle_screens(cam, left_screen, half_w, half_h, checks)
            save_json(work / "idle_screens.json", {"runs": [list(x) for x in left_screen], "idle": [list(x) for x in idle_scr]})
        if idle_scr:
            checks.append("Blank browser page on the desktop, his camera instead: " + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in idle_scr) + " (source).")
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Blank-page check failed ({type(e).__name__}: {str(e)[:100]}).")

    sec = load_json(work / "sections.json")                # step 2
    if sec is None:
        sec = find_sections(words, rows, duration, cfg, checks)
        save_json(work / "sections.json", sec)
    elif sec["method"].startswith("fallback"):
        checks.append(f"Sections came from the fallback (no 3 \"next section\" markers). Check the section times below.")

    cuts = load_json(work / "cuts.json")                   # step 3
    # a cut list from the OLD rules because the shared trimmer failed is never a cache: the next run tries the trimmer
    # again (lv skatesta 2026-10-24: the first run froze, the retry reused the fallback cuts, so the draft had no take review,
    # no self-talk cuts, the pre-roll and every retake fragment, and the failure message was lost with the first run)
    if cuts is not None and cuts.get("trimmer") == "legacy-fallback" and xml_kept is None:
        checks.append(f"The cut list on file came from the old silence/retake rules (shared trimmer failed earlier: "
                      f"{cuts.get('fallback_reason', '?')[:160]}); trying the shared trimmer again.")
        cuts = None
    # same for a cut list made while the take review failed: it is never a cache (remote test prada 2026-10-26: the rebuild
    # reused it and the NOT REVIEWED line vanished from the report)
    if cuts is not None and (load_json(work / "review_status.json") or {}).get("take_review") == "failed":
        checks.append("The cut list on file was made while the AI take review failed; cutting again with the review.")
        cuts = None
    if cuts is None:
        if xml_kept is not None:
            # Gling already decided the cuts; only the spoken "next section" markers come out on top
            keptx = subtract(xml_kept, sec["marker_cuts"])
            # Gling only removes takes it can match word for word; the take review catches redos in different words
            marks = take_review_marks(project, cam, keptx, cfg, checks)
            if marks:
                keptx = subtract(keptx, [(m["s"], m["e"]) for m in marks])
                checks.append(f"Take review removed {len(marks)} abandoned / redone lines on top of the Gling cuts.")
            cuts = {"kept": [[round(a, 3), round(b, 3)] for a, b in keptx], "take_review": len(marks),
                    "removed_seconds": round(duration - sum(b - a for a, b in keptx), 2)}
        elif cfg["pacing"].get("enabled", True) and cfg.get("trimmer", {}).get("engine", "take_cuts") == "take_cuts":
            try:
                cuts = trim_take_cuts(project, cam, duration, sec["marker_cuts"], cfg, checks)
            except Exception as e:
                # a failed trimmer STOPS the build (dhgate watchb spread 2026-10-24: take_cuts crashed, the old rules ran
                # instead and skipped the take review, and a draft full of retakes was sent as ready: "I'm still seeing
                # issues"). The old rules only run when raw/config.json sets trimmer.allow_fallback on purpose.
                if not cfg.get("trimmer", {}).get("allow_fallback", False):
                    print(f"BUILD STOPPED: the cutter (take_cuts.py) failed, so this draft would keep every retake.\n"
                          f"{type(e).__name__}: {str(e)[-1200:]}", file=sys.stderr, flush=True)
                    raise SystemExit(3)
                checks.append(f"Shared trimmer failed ({type(e).__name__}: {str(e)[:200]}); used the old silence/retake rules instead.")
                cuts = find_cuts(words, duration, sec["marker_cuts"], cfg, checks)
                cuts.update(trimmer="legacy-fallback", fallback_reason=f"{type(e).__name__}: {str(e)[:300]}")
        else:
            cuts = find_cuts(words, duration, sec["marker_cuts"], cfg, checks)
        save_json(work / "cuts.json", cuts)
    elif not cfg["pacing"].get("enabled", True):
        checks.append("Pacing cuts were switched off for this project in raw/config.json.")
    # always start from the TRIMMER's list ("base_kept"), never from a list his extra_cuts were already taken out of: the
    # cache used to be overwritten after subtracting raw/extra_cuts, so emptying extra_cuts never brought the footage back
    # (dhgate jordan 3 2026-10-23, round 3: the 25 s hype talk stayed cut after the cut note was removed)
    kept = [tuple(k) for k in cuts.get("base_kept", cuts["kept"])]
    base_kept = [list(k) for k in kept]
    # raw/extra_keeps.json: source ranges put BACK (e.g. the silent scroll between "scroll down to Prada" and "once you
    # get to Prada", prada cups 2026-10-22: cutting it jumped the page mid-scroll). Applied before extra_cuts.
    extra_keeps = load_json(project / "raw" / "extra_keeps.json")
    extra_cuts = load_json(project / "raw" / "extra_cuts.json")  # his manual removals (source time), idempotent, survives --fresh
    # retakes the draft audit HEARD in the last draft ({{KIT}}/tools\draft_audit.py, 2026-10-24): treated like his cuts
    audit_cuts = load_json(project / "raw" / "audit_cuts.json")
    if audit_cuts:
        extra_cuts = (extra_cuts or []) + [list(x) for x in audit_cuts]
        checks.append(f"Draft audit cuts applied (raw/audit_cuts.json): {len(audit_cuts)} retake(s) heard in the last draft.")
    # his PUBLISHED edit of this recording, when he gives the link (raw/reference.txt or a YouTube link in the Studio notes):
    # what it plays and ours cut comes back, a dangling edge word it skips goes (ultimate dhgate free reselling spreadsheet
    # 2026-10-23: the trimmer had cut 114 s of the spreadsheet-columns walkthrough; "study the actual video, this might be
    # smarter"). Treated exactly like his own extra_keeps / extra_cuts.
    refd = reference_cut.reference_ranges(project, words, kept, checks)
    if refd:
        # what his upload never plays is cut (reference_cut.unplayed), except what he put back himself in raw/extra_keeps
        # (s25 ultra 2026-10-23: his note keeps "I'm actually really happy that they did include this case", the upload doesn't)
        refcut = subtract([tuple(r) for r in refd["cut"]], [tuple(x) for x in (extra_keeps or [])])
        extra_keeps = (extra_keeps or []) + [list(r) for r in refd["keep"]]
        extra_cuts = (extra_cuts or []) + [list(r) for r in refcut]
        checks.append(f"Compared with his published edit ({refd['url']}, {refd['matched']} of {refd['ref_words']} subtitle words "
                      f"found): put back " + (", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in refd["keep"]) or "nothing")
                      + "; cut what it never plays: " + (", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in refcut) or "nothing")
                      + " (source).")
    # an APPROVED edit of this same footage (any project name; {{KIT}}/tools\approved_cuts.py, user 2026-10-26: two
    # laptop rebuilds of the approved dhgae prada glasses came back with five bad takes it had cut, "we already cut this
    # out before ... somehow you did it again"): its final cut list is the answer key. Start from it exactly like his own
    # keeps / cuts; this project's own raw/extra_keeps and extra_cuts (his notes) still win. Not in --cuts-only: the
    # regression suite must test the pipeline itself, not copy the answer back.
    own_keeps = [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])]
    own_cuts = [tuple(x) for x in (extra_cuts or [])]
    approved = None
    # (APPROVED_GUARD_TEST=1 turns it on in --cuts-only, to replay the guard itself on every approved project)
    if ("--cuts-only" not in sys.argv or os.environ.get("APPROVED_GUARD_TEST")) and cfg.get("trimmer", {}).get("approved_guard", True):
        try:
            sys.path.insert(0, str(Path(cfg.get("trimmer", {}).get("tools", r"{{KIT}}/tools"))))
            import approved_cuts
            approved = approved_cuts.lookup(project, cam)
        except Exception as e:  # noqa: the guard never breaks a build by itself
            checks.append(f"Approved-edit lookup failed ({type(e).__name__}: {str(e)[:120]}); built without it.")
    if approved:
        akeep = [tuple(x) for x in approved["kept"]]
        acut = subtract(subtract([(0.0, duration)], akeep), own_keeps)
        extra_keeps = (extra_keeps or []) + [list(r) for r in subtract(akeep, own_cuts)]
        extra_cuts = (extra_cuts or []) + [list(r) for r in acut]
        checks.insert(0, f"APPROVED FOOTAGE: this recording was approved as \"{approved['title']}\" (answer key on file "
                         f"{approved['approved_at']}); started from its {len(akeep)} kept pieces, plus this project's own notes.")
    if extra_keeps:
        merged = []
        for a, b in sorted(kept + [tuple(x) for x in extra_keeps]):
            if merged and a <= merged[-1][1] + 0.01:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        kept = merged
    if extra_cuts or extra_keeps:
        kept = subtract(kept, [tuple(x) for x in (extra_cuts or [])])
        cuts = dict(cuts, kept=[[round(a, 3), round(b, 3)] for a, b in kept], base_kept=base_kept,   # keeps "trimmer" etc.
                    removed_seconds=round(duration - sum(b - a for a, b in kept), 2))
        save_json(work / "cuts.json", cuts)
    elif cuts.get("base_kept") and cuts["kept"] != cuts["base_kept"]:   # his last extra cut/keep was removed: back to the trimmer's list
        cuts = dict(cuts, kept=base_kept)
        save_json(work / "cuts.json", cuts)
    # a whole part RUN BACK after a reset (s25 ultra 2026-10-23, 6:10-7:07: the link / product page / bulk walkthrough said,
    # "wait, my bad, that's the S24", minutes of fixing, then the same walkthrough again): the earlier try goes. Runs on the
    # kept footage (after the trimmer + his keeps/cuts); safe rules in take_cuts.find_runback. raw/extra_keeps win.
    if cfg.get("trimmer", {}).get("runback", True):
        try:
            sys.path.insert(0, str(Path(cfg.get("trimmer", {}).get("tools", r"{{KIT}}/tools"))))
            import take_cuts as _tc
            pstarts = [a for a, _b, _c in broll.product_segments(words, sec["sections"], cfg["broll"])][1:]
            rb = _tc.find_runback(words, kept, product_starts=pstarts)
            if extra_keeps:
                rb = [dict(c, s=a, e=b) for c in rb for a, b in subtract([(c["s"], c["e"])], [tuple(x) for x in extra_keeps])]
            if rb:
                kept = subtract(kept, [(c["s"], c["e"]) for c in rb])
                extra_cuts = (extra_cuts or []) + [[c["s"], c["e"]] for c in rb]
                for c in rb:
                    checks.append(f"Run-back cut {fmt(c['s'])}-{fmt(c['e'])} (source): \"{c['text'][:70]}\" is done again after a "
                                  f"reset (\"{c['kept'][:50]}\"; also re-said: {'; '.join(x[:30] for x in c['also'])}). Put it back with "
                                  "raw/extra_keeps.json if it was a real part.")
        except Exception as e:  # noqa: the detector must never stop a build
            checks.append(f"Run-back check failed ({type(e).__name__}: {str(e)[:120]}).")
    named_cuts = [(c["s"], c["e"], c.get("text", "")) for c in (load_json(work / "trim" / "cuts.json") or {}).get("cuts", [])]
    named_cuts += [(c["s"], c["e"], c.get("text", "")) for c in (load_json(work / "trim_extra.json") or [])]
    # his extra_keeps beat the trimmer: a word he put back is not "cut on purpose" (yeezy slides 1:28: the start of the
    # kept "In terms of sizing, I do recommend" sat in the trimmer's retake cut, so word_guard moved it past "In")...
    if extra_keeps:
        named_cuts = [(a, b, t if a == cs else "") for cs, ce, t in named_cuts
                      for a, b in subtract([(cs, ce)], [tuple(x) for x in extra_keeps])]
    # ...and his extra_cuts are deliberate: never pull a start back into a word he removed
    named_cuts += [(a, b, "") for a, b in (extra_cuts or [])]
    kept = signoff_guard(kept, words, duration, checks)  # the last "that's pretty much it for today's video" always plays
    if extra_cuts:                                       # ...but his own removals win over the put-back
        kept = subtract(kept, [tuple(x) for x in extra_cuts])
    kept = word_guard(kept, words, checks, named_cuts)  # never end or start a clip in the middle of a word
    kept = pad_guard(kept, words, checks, [tuple(x) for x in (extra_keeps or [])])   # no dead air at a join
    kept = end_guard(kept, words, duration, checks, mic=_mic16k(project, cam))     # the video ends on his last "bye"
    kept = fragment_guard(kept, words, checks, [tuple(x) for x in (extra_keeps or [])], cuts=[tuple(x) for x in (extra_cuts or [])])  # no clip ends on a run-on sentence
    kept = edge_guard(kept, _mic16k(project, cam), words, checks)   # every edge on measured quiet
    kept = midstart_guard(kept, _mic16k(project, cam), checks, work / "midstart.json",   # no clip opens mid-sentence
                          deliberate=[tuple(x) for x in (load_json(project / "raw" / "extra_cuts.json") or [])],
                          tools=cfg.get("trimmer", {}).get("tools", r"{{KIT}}/tools"))
    kept = hum_guard(kept, _mic16k(project, cam), checks)  # no clip opens on a "mmm" (low-HF burst, then a pause)
    kept = air_guard(kept, _mic16k(project, cam), checks,   # measured dead air at joins (his own silent keeps exempt)
                     [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])])
    kept = greeting_guard(kept, words, checks)          # a doubled "hey guys" keeps only the last one
    kept = orphan_guard(kept, words, checks, [tuple(x) for x in (extra_keeps or [])],   # no stranded slivers from a cut chunk
                        deliberate=[tuple(x) for x in (load_json(project / "raw" / "extra_cuts.json") or [])],
                        abandoned=_abandoned_cuts(project))
    # repeats only audible in the edit itself ("obviously, obviously", two sign-off takes from two guards): transcribe the
    # kept audio as it will play, cut the first try (s25 ultra round 2, repeat_guard.py), then tighten the new joins
    if cfg.get("trimmer", {}).get("repeat_guard", True):
        try:
            import repeat_guard
            rc = repeat_guard.find_repeats(project, cam, kept, 30, checks)
            # his raw/extra_keeps win, as the guard's own message promises (top 5 reselling products spring 2026-10-25,
            # 11:51: "you could do this with Palm Angels, you could do this with anything you could imagine" is a list, not
            # a restart; the guard cut it as one and left "really really c- | angels you could", "the word was just cut
            # randomly"): a repeat cut lying >= 80 % inside one of his keeps is dropped. Only mostly-inside: rick owens' keep
            # [1274.9, 1275.31] put back one "in" and overlaps 44 % of the right cut of the stumble before it (regress)
            ek = [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])]
            dropped = [(a, b) for a, b in rc
                       if b > a and sum(max(0.0, min(b, kb) - max(a, ka)) for ka, kb in ek) >= 0.8 * (b - a)]
            if dropped and "repeatkeep" not in os.environ.get("RG_OFF", ""):
                rc = [x for x in rc if x not in dropped]
                checks.append("Repeat guard cut(s) inside raw/extra_keeps left alone: "
                              + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in dropped) + " (source).")
            if rc:
                kept = [(a, b) for a, b in subtract(kept, rc) if b - a >= 0.3]
                kept = air_guard(kept, _mic16k(project, cam), checks, [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])])
        except Exception as e:  # noqa: never stops a build
            checks.append(f"Repeat guard failed ({type(e).__name__}: {str(e)[:120]}).")
    if refd:   # last: edge words his published edit doesn't play ("do it and Pretty | Pretty much"), cut at the measured gap
        kept = reference_cut.trim_edges(refd, words, kept, _mic16k(project, cam), checks)
    # the very last pass: each join listened to like an editor (joins.py): abandoned starts said again, a retake in the cut
    # that finishes the sentence (a cut-out price), "and | and", a clip ending on "as"/"to", slivers of cut words, a lone
    # word before a long pause (reselling spreadsheet round 2, 2026-10-23)
    kept = joins.cleanup(kept, words, _mic16k(project, cam), checks,
                         [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])])
    # the cleanup moves edges after air_guard ran: tighten the new joins too (8:46 had 1.2 s of quiet between "these shoes"
    # and "if you're looking" once the redo was cut)
    kept = air_guard(kept, _mic16k(project, cam), [],
                     [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])])
    # the cleanup can cut the end off a short piece ("Now I do want to show you what the | higher quality version looks
    # like" was a redo, best sp5der hoodie 2026-10-23, 5:59): what is left is a stranded lead-in, so check for orphans again
    kept = orphan_guard(kept, words, checks, [tuple(x) for x in (extra_keeps or [])],
                        deliberate=[tuple(x) for x in (load_json(project / "raw" / "extra_cuts.json") or [])],
                        abandoned=_abandoned_cuts(project))
    kept = walkoff_guard(kept, _mic16k(project, cam), rows, checks,   # silent tails of him walking out of the shot
                         [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])])
    global FPS
    try:
        _sf = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                              "-of", "csv=p=0", str(cam)], capture_output=True, text=True).stdout.strip() or "30/1"
        _n, _d = _sf.split("/")
        src_fps = float(_n) / float(_d or 1)
    except Exception:  # noqa
        src_fps = 30.0
    FPS = 60 if (cfg["output"].get("fps_follow_source", True) and src_fps >= 50) else int(cfg["output"].get("fps", 30))
    cfg["output"]["fps_render"] = FPS
    checks.append(f"Frame rate: {FPS} fps (recording {src_fps:.0f} fps).")
    # FINAL READ: a second take review of the FINISHED script, after every cut and guard, before anything renders (user
    # 2026-10-26: "this video shouldn't even have reached me ... it should have been able to read the whole script"). The
    # first review runs before the guards and can't see the fragments / run-ons they leave. Frozen like the first one
    # (work/final_read/review_cuts.json): revision builds reuse the first draft's read and only change what his notes say.
    # Approved footage skips it (the answer key decides); --cuts-only skips it (regression replays never ask an AI).
    if not approved and ("--cuts-only" not in sys.argv or os.environ.get("FINAL_READ_TEST")) and cfg.get("trimmer", {}).get("final_read", True):
        try:
            sys.path.insert(0, str(Path(cfg.get("trimmer", {}).get("tools", r"{{KIT}}/tools")) / "phone_edit"))
            import take_review
            fr = work / "final_read"
            fr.mkdir(exist_ok=True)
            marks = take_review.review(str(project), 0.0, kind="review", work=str(fr), words=str(work / "transcript.json"),
                                       keep=[list(k) for k in kept], audio=str(_mic16k(project, cam)), away=no_face_ranges(project, cfg))
            ek = [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])]   # his put-backs win
            # a "leftover stub" the mic says is a WHOLE line stays (maison mahara dhgae review 2026-10-26, 4:19: Whisper merged
            # the first try and the retake of "in terms of sizing, these shoes are true to size" into one sentence and gave
            # the retake only "size.", so the read called the clean 2.6 s retake a stub: "that was a continuous clip ... a
            # false alarm"). Kept audio with > 1 s more speech than the words Whisper put there = words Whisper lost.
            env, thr = take_review.load_audio_env(str(fr), str(_mic16k(project, cam)))
            spoke = lambda a, b: sum(1 for i in range(int(a * 100), int(b * 100)) if i < len(env) and env[i] >= thr) / 100.0
            # words COUNTED at ~0.35 s each, not their stamped lengths: Whisper stretched "to" over the whole 2.3 s retake, so
            # the stamped times "covered" the speech and the first version of this rule never fired
            worded = lambda a, b: 0.35 * sum(1 for w in words if a <= (w["s"] + w["e"]) / 2 < b)
            whole = []
            for m in marks:
                inside = [(max(x, m["s"]), min(y, m["e"])) for x, y in kept if min(y, m["e"]) > max(x, m["s"])]
                lost = sum(spoke(a, b) - worded(a, b) for a, b in inside)
                if lost > 1.0:
                    whole.append(m)
                    checks.append(f"Final read wanted to cut {fmt(m['s'])}-{fmt(m['e'])} ({m['why'][:60]}), but the mic has "
                                  f"{lost:.1f} s more speech there than Whisper's words: a whole line Whisper merged, kept.")
            marks = [m for m in marks if m not in whole]
            fcut = subtract([(m["s"], m["e"]) for m in marks], ek)
            if fcut:
                kept = subtract(kept, fcut)
                checks.insert(0, f"Final read of the finished script removed {len(fcut)} more piece(s): "
                              + "; ".join(f"{fmt(m['s'])}-{fmt(m['e'])} ({m['why'][:70]})" for m in marks[:6]) + " (source).")
            else:
                checks.append("Final read of the finished script: nothing more to cut.")
        except Exception as e:  # noqa: the first take review is already mandatory; this second read never stops a build
            checks.insert(0, f"FINAL READ DID NOT RUN ({type(e).__name__}: {str(e)[:140]}): only the first take review checked this script.")
    if approved:
        # the final cut list (after every guard) must still be the approved one, apart from his own notes on this project
        own_keeps += [tuple(x) for x in (load_json(project / "raw" / "extra_keeps.json") or [])]
        own_cuts += [tuple(x) for x in (load_json(project / "raw" / "extra_cuts.json") or [])] + \
                    [tuple(x) for x in (load_json(project / "raw" / "audit_cuts.json") or [])]
        more, less = approved_cuts.compare(approved["kept"], kept, own_keeps, own_cuts)
        if more or less:
            def _said(a, b):
                return " ".join(w["w"] for w in words if a <= w["s"] < b)[:90]
            lines = [f"  plays, but the approved edit cut it: {fmt(a)}-{fmt(b)} \"{_said(a, b)}\"" for a, b in more] + \
                    [f"  cut, but the approved edit kept it: {fmt(a)}-{fmt(b)} \"{_said(a, b)}\"" for a, b in less]
            msg = (f"this footage was approved as \"{approved['title']}\", and this build differs from it where no note "
                   f"asked for a change (recording times):\n" + "\n".join(lines))
            if not cfg.get("trimmer", {}).get("allow_off_approved", False):
                # put the approved cuts back IN THIS BUILD instead of stopping it (user 2026-10-26: "we should catch it
                # first try", a stop meant a whole rebuild). His own notes on this project still win.
                merged = []
                for a, b in sorted(subtract([tuple(x) for x in approved["kept"]], own_cuts) + list(own_keeps)):
                    if merged and a <= merged[-1][1] + 0.01:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                    else:
                        merged.append((a, b))
                kept = subtract(merged, own_cuts)
                print(f"approved edit restored: {msg}", flush=True)
                checks.insert(0, "APPROVED CUTS RESTORED (a step moved them; fix that step): " + msg)
            else:
                checks.insert(0, "OFF THE APPROVED EDIT (allowed by raw/config.json): " + msg)
        else:
            checks.insert(0, f"Matches the approved edit of \"{approved['title']}\" (apart from this project's own notes).")
    tl = Timeline(kept, FPS)
    # the kept ranges as rendered: the Studio maps the user's draft times through these (cuts.json is before word_guard)
    save_json(work / "timeline.json", {"kept": [[round(a, 3), round(b, 3)] for a, b in kept]})
    if "--cuts-only" in sys.argv:   # the regression suite (_tools/regress): the cut decisions only, no render
        save_json(work / "cuts_only_checks.json", checks)
        print(f"cuts-only: {len(kept)} kept pieces")
        return

    if xml_file and not (work / "audio_mix.json").exists():
        # block mic mix: DJI for the whole try-on block (first real away segment -> the cut
        # where the computer segment starts), condenser elsewhere. Boundaries snap to Gling cuts.
        screen_runs, s_start, s_last = [], None, None
        for r in rows:
            if r.get("right") == "screen":
                if s_start is None:
                    s_start = r["t"]
                s_last = r["t"]
            else:
                if s_start is not None and s_last - s_start >= 2.0:
                    screen_runs.append((s_start, s_last))
                s_start = None
        if s_start is not None and s_last - s_start >= 2.0:
            screen_runs.append((s_start, s_last))
        audio_mix.apply_block_mix(project, cfg, checks, xml_media, kept, screen_runs)
        (work / "levels.json").unlink(missing_ok=True)  # voice level changed with the mix

    angles = load_json(work / "angles.json")               # step 4
    if angles is None:
        angles = find_angles(rows, sec["sections"], cfg)
        save_json(work / "angles.json", angles)
    angles = desk_angles(angles, words, checks)

    zooms = []                                             # zooms (optional)
    if cfg.get("zooms", {}).get("enabled"):
        zooms = load_json(work / "zooms.json")
        if zooms is None:
            screen_ranges = [(x["start"], x["end"]) for x in sec["sections"] if x["name"] in cfg["zooms"]["screen_sections"]]
            pts = track_cursor(project, cfg, screen_ranges, half_w, half_h)
            zooms = find_zooms(words, rows, sec["sections"], pts, cfg)
            # cursor zooms are measured on the right half: none where the screen is on the left
            zooms = [z for z in zooms if z["kind"] != "screen" or not any(a <= z["start"] <= b for a, b in left_screen)]
            save_json(work / "zooms.json", zooms)

    # B-roll never covers the desktop recording or a product he holds up to the front camera (dhgate rick owens
    # 2026-10-22: "B-roll should not go over desktop footage"; 3:34 "I am showing the shoe in my other cam")
    holdups = find_holdups(rows, kept, sec["sections"], checks)
    # ...and a small product held up with his face still in shot (AirPods case at chin height, ultimate dhgate free reselling
    # spreadsheet 4:43 / 5:09 / 5:21): hand landmarks + a vision check (showing.py). Desktop on the left = he talks on the
    # right camera: that camera goes full frame there (shows_b, taken out of the swap layout below)
    shows = showing.find_showing(project, cam, rows, kept, sec["sections"], left_screen, W, H, cfg, checks)
    shows = run_to_cut(shows, kept, checks)
    shows_b =[(max(a, x), min(b, y)) for a, b in shows for x, y in left_screen if min(b, y) > max(a, x)]
    holdups = sorted(holdups + subtract(shows, shows_b))
    # ...and a list counted off on his fingers to the talking camera (top 5 products to resell in winter 2024, 8:39: "I'm
    # pointing out different products with my hands ... zoom in for the main camera, then back to the webcam view"):
    # that camera full frame with a punch-in for the list (showing.find_pointing), the layout before comes back after
    try:
        points = showing.find_pointing(project, rows, kept, words, sec["sections"], left_screen, cfg, checks)
    except Exception as e:  # noqa: never stops a build
        points = []
        checks.append(f"Pointing check failed ({type(e).__name__}: {str(e)[:100]}).")
    shows_b = sorted(shows_b + [(a, b) for a, b, k in points if k == "b"])
    holdups = sorted(holdups + [(a, b) for a, b, k in points if k == "a"])
    hard = [(a, b) for k, a, b in runs_of(rows, "right") if k == "screen"]
    # the talking intro: everything before the product camera first shows a product. The fallback sections can put his
    # "hey guys" inside the review (dhgate rick owens 2026-10-22: an on-feet slot over "welcome back to yet again another video")
    first_product = next((r["t"] for r in rows if r.get("right") == "product" and any(x <= r["t"] <= y for x, y in kept)), None)
    if first_product:
        hard.append((0.0, first_product))
    avoid = holdups + shows_b + hard
    slots = load_json(work / "broll_plan.json")            # b-roll
    if slots is None:
        slots = broll.plan_slots(words, sec["sections"], tl, cfg, avoid, hard)
        save_json(work / "broll_plan.json", slots)
    if "--broll-plan" in sys.argv:
        req = broll.write_requests(project, slots, fmt)
        print(f"B-roll shot list: {req} ({len(slots)} slots)")
        return
    if cfg["broll"]["enabled"]:   # what each clip shows (kind), then which product (pair) - before matching them to slots
        broll.auto_label(project, cfg, checks)
        broll.auto_pair(project, words, sec["sections"], cam, rows, holdups, cfg, checks)
    # what each clip SAYS (s25 ultra 2026-10-23): filmed in sync with the main camera -> exactly there at 1x; a demo where he
    # talks to the clip's camera ("here is the audio quality from the phone") -> a cutaway WITH its sound before the
    # verdict, never a silent overlay; a clip ABOUT a topic -> only over a line about that topic (place_leftovers)
    infos, inserts, skip, synced_placed, taken = {}, [], set(), [], list(slots)
    if cfg["broll"]["enabled"]:
        infos = broll.clip_infos(project, words, tl, cfg, checks)
        inserts = broll.plan_inserts(project, words, sec["sections"], tl, cfg, infos, checks)
        ents = {Path(m["file"]).name.lower(): m for m in (load_json(project / "raw" / "broll.json") or [])}
        dropped = {n for n in infos if ents.get(n.lower(), {}).get("use", True) is False}
        for n in sorted(dropped):
            checks.append(f"B-roll {n} not used (\"use\": false in raw/broll.json).")
        skip = dropped | {n for n, i in infos.items() if i.get("demo")}
        skip |= set(broll.place_synced(project, words, tl, cfg, {n: i for n, i in infos.items() if n not in skip},
                                       synced_placed, taken, checks, avoid))
    placed, leftovers = broll.assign_clips(project, slots, cfg, checks, skip,
                                             [n for n, i in infos.items() if i.get("topics")]) if cfg["broll"]["enabled"] else ([], [])
    placed += synced_placed
    if leftovers:   # every clip he gives is used: the ones no phrase slot took get their own spaced-out slot
        # only FILLED slots keep clips apart: an empty "showcase" slot on the Play Store line blocked the Play Store clip
        filled = {c["slot"] for c in placed}
        taken = [s for s in taken if s["slot"] in filled or s.get("kind") == "synced"]
        placed = broll.place_leftovers(project, words, sec["sections"], tl, cfg, taken, placed, leftovers, checks, avoid, infos)
    # his own footage of what he names: "I'll throw up some footage" and lists of products (named_broll, dhgate watchb
    # spread 2026-10-24); from his other videos only, nothing when there is none
    try:
        import named_broll
        nb = named_broll.plan(project, words, tl, cfg, placed, checks)
        placed = sorted(placed + nb, key=lambda c: c["out_start"])
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Named B-roll failed ({type(e).__name__}: {str(e)[:160]}).")
    # an overlay never runs across a cutaway insert point (the picture would jump into the insert mid-shot)
    for ins in inserts:
        keep_p = []
        for c in placed:
            if c["out_start"] < ins["out"] < c["out_start"] + c["length"]:
                L = ins["out"] - c["out_start"] - 0.05
                if L < 2.5:
                    checks.append(f"B-roll {Path(c['file']).name} dropped: it would run into the cutaway at {ins['out']:.1f} s.")
                    continue
                c = dict(c, length=round(L, 3), src_len=round(L * c["speed"], 3), on_cut=True)
            keep_p.append(c)
        placed = keep_p
    if cfg["broll"]["enabled"] and slots and not placed:
        checks.append("No B-roll clips were found in raw/broll, so the video has no B-roll.")

    # step 5: layout expressions in output time
    # outro_layout "wide_pip" (prada cups 2026-10-22, "4:34 it's just a full screen, let's not do that ... keep the
    # orientation from 4:47 but with the circular face cam top left"): the outro shows the right camera (wide angle) with
    # the face circle instead of full-frame Camera A
    # wide_pip is RETIRED (user 2026-10-22, prada cups 4:25-end: "why would the face cam pop up when I have another main
    # camera on screen"): a face circle never sits on a camera shot of him. The setting is ignored; outro = "full".
    outro_pip = False
    full_ranges = [(s["start"], s["end"]) for s in sec["sections"] if s["name"] in (("intro",) if outro_pip else ("intro", "outro"))]
    pip_ranges = [(s["start"], s["end"]) for s in sec["sections"] if s["name"] in (("review", "showcase", "outro") if outro_pip else ("review", "showcase"))]
    outro_rng = [(s["start"], s["end"]) for s in sec["sections"] if s["name"] == "outro"] if outro_pip else []
    angles = snap_angles(angles, kept)
    a_ranges = [(g["start"], g["end"]) for g in angles if g["cam"] == "A"]
    full_a = [(max(a, fa), min(b, fb)) for a, b in a_ranges for fa, fb in full_ranges if min(b, fb) > max(a, fa)]
    face_full = find_face_full(words, sec["sections"], a_ranges, cfg)   # "on my face" cutaways
    face_full += holdups                                                    # things held up to Camera A
    # he only TALKS while the desk camera shows an idle desk (s25 ultra 4:00-4:28, "should have been a full facecam video,
    # nothing going on or being unboxed on the desk cam"): Camera A full frame, no circle (idle_desk.py)
    try:
        face_full += idle_desk.find_idle(project, cam, rows, kept, sec["sections"], left_screen, cfg, checks)
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Idle-desk check failed ({type(e).__name__}: {str(e)[:100]}).")
    # follow the camera he FACES outside the intro/outro too (top 5 reselling products spring 2026-10-25, 0:20-0:46: "I
    # start on the side angle and turn to the main camera, and at 0:45 I turn to the side camera again. The edit should
    # follow the camera I'm facing"; his hey-guys talk sat in the fallback "review" section, where find_angles never runs,
    # so the side camera held for the whole talk). Where the right camera is the SIDE angle of him and he faces Camera A
    # (|yaw| < front_max_degrees, face found) for >= front_min_seconds: Camera A full. Turned to the side camera = the
    # default right camera full. Not over the desktop (left_screen) and never a product-camera shot (right "product").
    # Only in his TALKING intro: up to the first kept product-camera / screen shot of >= 5 s. Later, facing the front while
    # the side angle is up is a try-on he shows on purpose (approved dhgae prada glasses 5:13-6:03: front-facing in the
    # sunglasses, kept on the side camera, "use the side angle when I was turned ... with the sunglasses on").
    fm, fmin = cfg["face_cam"].get("front_max_degrees", 18.0), cfg["face_cam"].get("front_min_seconds", 3.0)
    pruns, cur_ = [], None
    for r in rows:
        if not any(a <= r["t"] < b for a, b in kept):
            continue
        if r.get("right") in ("product", "screen") or r.get("left") == "screen":
            if cur_ is not None and r["t"] - cur_[1] <= 1.0:
                cur_[1] = r["t"]
            else:
                cur_ = [r["t"], r["t"]]
                pruns.append(cur_)
    talk_end = next((a for a, b in pruns if b - a >= 5.0), 0.0)
    mid_secs = [(s["start"], min(s["end"], talk_end)) for s in sec["sections"] if s["name"] in ("review", "showcase")
                and s["start"] < talk_end]
    # talking videos with no product to try on (reselling channel): follow the camera he faces the WHOLE video ($30k
    # 2026-10-26, 5:17: "it's been using [the side angle] the whole time ... I'm mainly pointed at the main camera")
    if (load_json(project / "studio.json") or {}).get("channel", "") in cfg["face_cam"].get("follow_facing_channels", ["{{REVIEW_CHANNEL}}"]):
        mid_secs = [(s["start"], s["end"]) for s in sec["sections"] if s["name"] in ("review", "showcase")]
    front, cur_ = [], None
    for r in rows:
        ok = (r.get("right") == "side" and r.get("fx") is not None and r.get("yaw") is not None and abs(r["yaw"]) < fm
              and any(a <= r["t"] < b for a, b in mid_secs))
        if ok:
            if cur_ is not None and r["t"] - cur_[1] <= 0.9:
                cur_[1] = r["t"]
            else:
                cur_ = [r["t"], r["t"]]
                front.append(cur_)
    front = [(a, b + 0.2) for a, b in front if b - a >= fmin and "facefront" not in os.environ.get("RG_OFF", "")]
    front = subtract(front, left_screen)
    if front:
        face_full += [(xml_cuts.snap(a, kept, max_dist=1.0), xml_cuts.snap(b, kept, max_dist=1.0)) for a, b in front]
        checks.append("He faces the front camera while the side angle is up: Camera A full at "
                      + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in front) + " (source).")
    amix = load_json(work / "audio_mix.json")  # away-from-mic segments (try-on, full body): no circle there
    screen_starts = [r2["t"] for r1, r2 in zip(rows, rows[1:])
                     if r1.get("right") != "screen" and r2.get("right") == "screen"]
    if amix and cfg.get("audio_mix", {}).get("hide_facecam", True):
        acfg = cfg.get("audio_mix", {})
        hide = [tuple(r) for r in amix.get("hide_ranges", [])]
        if acfg.get("hide_block", True):
            # once a real try-on block starts (>= hide_block_min_seconds), the circle stays off
            # for the whole block until the showcase picture — no popping back mid-try-on
            starts = [a for a, b in hide if b - a >= acfg.get("hide_block_min_seconds", 8.0)]
            if starts:
                end = next((x for x in screen_starts if x > starts[0]), None)
                if end is not None:
                    # a block is a try-on only if he really leaves Camera A in the kept part (dhgate asics: no face 23%
                    # of the time); sitting at the desk unboxing is not (prada cups 2026-10-22: 6%, and a quiet pre-roll
                    # pause before the first kept clip had started a block that hid the circle from 0:53 to 1:48)
                    share = noface_share(rows, kept, starts[0], end)
                    # ...AND the try-on camera actually films him (side angle, or his face on the right camera): holding
                    # the shoes up in front of his face at the desk also loses Camera A's face (dhgate rick owens 2026-10-22:
                    # 58% no-face, right camera 99% "product" and his face on it 1% -> the circle was off for the whole
                    # review, "at 0:54 you didn't have my face cam ... these unboxing parts on the desk need a facecam").
                    # A real try-on: asics 97% / 26% of the block.
                    seen = rightcam_share(rows, kept, starts[0], end)
                    if share >= acfg.get("hide_block_min_noface", 0.15) and seen >= acfg.get("hide_block_min_rightcam", 0.15):
                        hide = [(starts[0], end)]
                    else:
                        # ...but the stretches where he really LEFT the desk still lose the circle (amiri jeans 2026-10-22,
                        # 1:12 and 3:01: several pairs tried on in one long quiet-mic block; the try-on camera films his
                        # legs, not his face, so the block read "films him 0%" and the circle sat over every try-on, "do not
                        # have that ever happen again"): Camera A without his face for >= away_min_seconds (glimpses
                        # <= 1 s don't break it) inside a quiet-mic range = a try-on stretch, circle off.
                        # not only inside quiet-mic ranges: the condenser still caught him on the star-jeans try-on (src
                        # 7:54-8:31, empty desk on Camera A, circle stayed). Things held up to Camera A are not try-ons.
                        away = subtract(away_runs(rows, kept, [(0.0, 1e9)], acfg.get("away_min_seconds", 8.0)), holdups)
                        checks.append(f"Quiet-mic stretch {fmt(starts[0])}-{fmt(end)} (source) is not one try-on block ({share:.0%} of frames "
                                      f"without his face on Camera A, the try-on camera films his face {seen:.0%} of the time); the circle is "
                                      f"off only where he left the desk: " + (", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in away) or "nowhere") + " (source).")
                        hide = away
        snap_d = acfg.get("block_snap_seconds", 10.0) if xml_file else 1.0  # audio detection lags the visual step-away
        hide = [(xml_cuts.snap(a, kept, max_dist=snap_d), xml_cuts.snap(b, kept, max_dist=snap_d)) for a, b in hide]  # circle leaves ON a cut
        pip_ranges = subtract(pip_ranges, hide)
        face_full = subtract(face_full, hide)  # no Camera-A cutaway inside the try-on block (Go 3S is the shot)
    full_a += face_full
    # raw/extra_full.json: source ranges he pointed at that must be Camera A full frame, no circle (amiri jeans 2026-10-22,
    # 2:24: he holds the jeans up to the front camera while the product camera films an empty desk, "it's supposed to be
    # the main camera"). Same mapping as extra_cuts: his output time -> source through work/timeline.json.
    extra_full = [tuple(r) for r in load_json(project / "raw" / "extra_full.json", [])]
    if extra_full:
        full_a += extra_full
        pip_ranges = subtract(pip_ranges, extra_full)
        checks.append("Camera A full frame by hand (raw/extra_full.json): " + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in extra_full) + " (source).")
    # NO FACE, NO CIRCLE (canada goose jacket 2026-10-24, 1:38 / 1:53 / 2:12: "I'm literally standing up ... you don't
    # detect a face on screen ... the face cam should basically be gone"): he stood in front of the desk camera showing a
    # big jacket for 5 min, Camera A filmed his torso, there was no quiet-mic try-on block (he kept talking into the
    # condenser), so the circle showed an orange crop the whole review. Camera A without his face for >= 20 s (glimpses
    # <= 1 s don't break it), minus hold-ups (those are Camera A full anyway) = no circle, the product/right camera full.
    # 20 s on purpose: every approved review's longer no-face runs already had no circle (try-ons, hold-ups); the asics
    # desk shot whose circle shows him behind a shoe is a 15 s run (MediaPipe misses a face half behind the product).
    nf_min = cfg["face_cam"].get("noface_hide_seconds", 20.0)
    if nf_min:
        noface = [(xml_cuts.snap(a, kept, max_dist=1.0), xml_cuts.snap(b, kept, max_dist=1.0))
                  for a, b in subtract(away_runs(rows, kept, [(0.0, 1e9)], nf_min), holdups)]
        noface = [(a, b) for a, b in noface if b - a > 0.5]
        if noface:
            pip_ranges = subtract(pip_ranges, noface)
            checks.append(f"No face on Camera A for >= {nf_min:.0f} s (he stood up / left the desk cam), face circle off: "
                          + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in noface) + " (source).")
    if True:  # ALWAYS: no circle while he's turned to the side camera (was cfg hide_on_turn; never optional now)
        # also in a wide_pip outro: turned to the side camera = that camera full, no circle (prada cups 4:31, "when I turn
        # to the left here, obviously this is the full screen camera section")
        pip_ranges = subtract(pip_ranges, [(g["start"], g["end"]) for g in angles if g["cam"] == "B"])
    hide_cues = cfg["face_cam"].get("hide_from_cues", [])  # e.g. "another angle": circle off until the showcase picture
    b_segs = [(g["start"], g["end"]) for g in angles if g["cam"] == "B"]
    for s in sec["sections"]:
        for i in range(len(words)):
            if s["start"] <= words[i]["s"] < s["end"]:
                for cue in hide_cues:
                    cw = cue.split()
                    if [norm(w["w"]) for w in words[i:i + len(cw)]] == cw:
                        t = words[i]["s"]
                        # cut the circle ON the angle switch, not on the words: snap to an
                        # angle change within 3 s of the cue — the right half flipping to the
                        # side camera, or a head-turn switch, whichever is closest
                        switch_cuts = [ba for ba, _ in b_segs]
                        switch_cuts += [r2["t"] for r1, r2 in zip(rows, rows[1:])
                                        if r1.get("right") != "side" and r2.get("right") == "side"]
                        near = [c for c in switch_cuts if abs(c - t) <= 3]
                        if near:
                            t = min(near, key=lambda c: abs(c - t))
                        # stay off until the actual showcase picture (right half becomes the
                        # screen recording); the guessed section boundary is often a bit early
                        end = next((x for x in screen_starts if x > t), s["end"])
                        pip_ranges = subtract(pip_ranges, [(t, end)])
    pip_ranges = subtract(pip_ranges, face_full)
    # Camera A full frame only where Camera A is a camera: with the desktop on the LEFT half he talks to the RIGHT camera, so
    # the talking-head sections show that camera full (dhgate jordan 3 2026-10-23, 4:17 to the end: the outro showed the
    # store page full screen, "uses the wrong camera ... I don't know where the actual camera went"). Default layer = right.
    full_a = subtract(full_a, left_screen)
    # screen on the left half: the left half goes full frame, the circle comes from the right camera
    swap = [(max(a, sa), min(b, sb)) for a, b in left_screen for sa, sb in
            [(s["start"], s["end"]) for s in sec["sections"] if s["name"] in ("review", "showcase")] if min(b, sb) > max(a, sa)]
    swap = subtract(swap, shows_b)               # showing something to the right camera: that camera full, no circle
    pip_ranges = subtract(pip_ranges, shows_b)
    swap = subtract(swap, idle_scr)              # blank new tab: his camera full, no circle
    pip_ranges = subtract(pip_ranges, idle_scr)
    # ...and so do his raw/extra_full ranges over the desktop: "show the camera" means the right camera there, never the
    # still store page (top 5 reselling products spring 2026-10-25, 17:03: the AirPods case shown to the right camera
    # for 13 s while the draft held the listing; the swap put the page back over his extra_full)
    swap = subtract(swap, extra_full)
    full_a += swap
    if cfg["face_cam"].get("hide_when_side", True):  # side/wide angle in frame: no circle at all
        side_runs, start, last = [], None, None
        for r in rows:
            if r.get("right") == "side":
                if start is None:
                    start = r["t"]
                last = r["t"]
            else:
                if start is not None:
                    side_runs.append((start, last))
                start = None
        if start is not None:
            side_runs.append((start, last))
        # the side camera HOLDS through short breaks: holding the shoes up in front of his face makes the right camera
        # lose his face for < 1 s, the row reads "product" and the circle flashed on over the side camera footage
        # (dhgate yeezy slides 1:26, 2026-10-23: "we should never have that face cam over the footage of another high
        # quality camera"; 26 such breaks in that recording). Real product shots on the desk run far longer. Bridge
        # first, then the >= 1 s minimum, so a stretch flickering side/product every row counts as the side camera too.
        bridge = cfg["face_cam"].get("side_bridge_seconds", 3.0)
        merged_side = []
        for a, b in side_runs:
            if merged_side and a - merged_side[-1][1] <= bridge:
                merged_side[-1] = (merged_side[-1][0], b)
            else:
                merged_side.append((a, b))
        side_runs = [(a, b + 0.2) for a, b in merged_side if b - a >= 1.0]   # the run lasts until the next row
        pip_ranges = subtract(pip_ranges, side_runs)   # side angle on screen = no circle, in every section
    # raw/extra_side.json: source ranges that must show the RIGHT (side) camera full, no circle (top 5 reselling products
    # spring 2026-10-25: 9:32 he turns to show the side of the sunglasses and the right camera loses his face for 6 s, so
    # the circle came back over that shot; 12:18 he talks to the side camera at ~20 deg, under turn_degrees)
    extra_side = [tuple(r) for r in load_json(project / "raw" / "extra_side.json", [])]
    if extra_side:
        full_a = subtract(full_a, extra_side)
        pip_ranges = subtract(pip_ranges, extra_side)
        swap = subtract(swap, extra_side)
        checks.append("Side camera full by hand (raw/extra_side.json): " + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in extra_side) + " (source).")
    # last: no camera flash and no circle blink shorter than min_shot_seconds (absorb_flashes)
    min_shot = cfg["face_cam"].get("min_shot_seconds", 1.2)
    if min_shot:
        fa0, pr0 = full_a, pip_ranges
        full_a = absorb_flashes(full_a, kept, min_shot)
        pip_ranges = absorb_flashes(pip_ranges, kept, min_shot)
        if sum(b - a for a, b in fa0) != sum(b - a for a, b in full_a) or sum(b - a for a, b in pr0) != sum(b - a for a, b in pip_ranges):
            checks.append(f"Camera flashes / circle blinks under {min_shot} s absorbed into the shots around them.")
    switches =sum(1 for g1, g2 in zip(angles, angles[1:]) if g1["cam"] != g2["cam"])
    pip_b = [(max(a, sa), min(b, sb)) for a, b in pip_ranges for sa, sb in swap if min(b, sb) > max(a, sa)]
    # the right camera loses him when he leans in to the PC: no circle of an empty chair (prada cups 2026-10-22 scroll)
    gone = [(a, b) for k, a, b in runs_of([dict(r, rgone=r.get("rfx_face") is None) for r in rows], "rgone") if k and b - a >= 1.5]
    pip_b = subtract(pip_b, gone)
    pip_ranges = subtract(pip_ranges, swap)
    rfx = [r["rfx_face"] for r in rows if r.get("rfx_face") is not None]
    rfy = [r["rfy_face"] for r in rows if r.get("rfy_face") is not None]
    if swap:
        checks.append(f"Screen recording on the LEFT half for {sum(b - a for a, b in swap):.0f} s (camera on the right): "
                      "those parts show the left half full frame with the face circle from the right camera. Check them.")
    fx = [r["fx"] for r in rows if r["fx"] is not None]
    fy = [r["fy"] for r in rows if r["fy"] is not None]
    if not fx:
        checks.append("No face found on Camera A; the face circle is centred on the frame.")
    if cfg.get("zooms", {}).get("enabled"):
        # keyframed extras (2026-10-22): slow drift on the full side angle + zoom onto the store-page panel he's
        # talking about (sizes, bulk tiers). Topic zooms are cached (OCR); side drift is recomputed every run.
        topic = load_json(work / "topic_zooms.json")
        if topic is None:
            topic = zooms_extra.topic_zooms(words, rows, kept, cam, half_w, half_h, zooms, cfg, checks)
            try:   # what he reads out on the screen (dhgate watchb spread 2026-10-24)
                topic += zooms_extra.spoken_text_zooms(words, rows, kept, cam, half_w, half_h, zooms + topic,
                                                       dict(cfg, _project_name=project.name), checks)
            except Exception as e:  # noqa: never stops a build
                checks.append(f"Spoken-text zooms failed ({type(e).__name__}: {str(e)[:120]}).")
            save_json(work / "topic_zooms.json", topic)
        zooms = zooms + topic
        zooms = zooms + zooms_extra.side_zooms(rows, kept, full_a, left_screen, zooms, cfg)
    if points:   # the punch-in on the talking camera for a list on his fingers, centred a little under his face (the hands)
        zooms = [z for z in zooms if not any(z["start"] < b and a < z["end"] for a, b, _ in points)]
        for a, b, k in points:
            rs = [r for r in rows if a <= r["t"] <= b and r.get("rfx" if k == "b" else "fx") is not None]
            cx = float(np.median([r["rfx" if k == "b" else "fx"] for r in rs])) if rs else 0.5
            cy = float(np.median([r["rfy" if k == "b" else "fy"] for r in rs])) if rs else 0.4
            zooms.append({"kind": "point", "start": a, "end": b, "zoom": cfg.get("showing", {}).get("point_zoom", 1.2),
                          "ease": 0.45, k: [round(min(max(cx, 0.3), 0.7), 3), round(min(max(cy + 0.12, 0.35), 0.65), 3)],
                          "why": "list on his fingers"})
    pad = make_circle_art(work, cfg)

    # step 6
    subs = []
    if (SKILL / "assets" / "subscribe.mov").exists():
        subs = find_subscribes(words, tl, cfg, checks)
    else:
        checks.append("assets/subscribe.mov is missing, so no subscribe animations were added.")

    prices, cash = [], None                                # price callouts
    if cfg.get("price", {}).get("enabled"):
        prices = callouts.find_prices(words, tl, cfg, sections=sec["sections"])
        cash = callouts.price_sound(SKILL, cfg)
        for pr in prices:
            pr["card"] = str(callouts.make_card(work, pr["text"], cfg))
    # spoken math ("four times twelve" -> "$4 x 12 = $48", dhgate cologne spread 2026-10-25) rides the same pop-up + sound
    try:
        maths = callouts.find_math(words, tl, cfg, taken=prices)
        if maths:
            cash = cash or callouts.price_sound(SKILL, cfg)
            for mt in maths:
                mt["card"] = str(callouts.make_math_card(work, mt["text"], cfg))
                checks.append(f"Math on screen at {mt['out']:.1f} s: \"{mt['said']}\" -> {mt['text']}.")
            prices = sorted(prices + maths, key=lambda x: x["out"])
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Math callout failed ({type(e).__name__}: {str(e)[:120]}).")
    # spoken ratings ("an 8 out of 10" -> a gold "RATING 8/10" card + its own bell, user 2026-10-26) ride the same pop-up
    try:
        rates = callouts.find_ratings(words, tl, cfg, taken=prices)
        if rates:
            bell = str(callouts.make_rating_sound(SKILL / "assets" / "sfx_rating.wav"))
            for rt in rates:
                rt["card"] = str(callouts.make_rating_card(work, rt["text"], cfg))
                rt["sound"] = bell
                checks.append(f"Rating on screen at {rt['out']:.1f} s: \"{rt['said']}\" -> {rt['text']}.")
            cash = cash or callouts.price_sound(SKILL, cfg)
            prices = sorted(prices + rates, key=lambda x: x["out"])
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Rating callout failed ({type(e).__name__}: {str(e)[:120]}).")
    # the greeting callout on the TALKING intro ("HEY GUYS / {{REVIEW_CHANNEL}} REVIEWS / WELCOME BACK" + the channel's avatar pop,
    # channel study 2026-10-26; user: "at the beginning of the talking intro not the voice over one")
    try:
        doc = load_json(project / "studio.json") or {}
        greet = callouts.find_greeting(words, tl, doc.get("channel", ""), within=cfg.get("greeting", {}).get("within_seconds", 25))
        av = callouts.avatar_for(doc.get("channel", ""), SKILL)
        if greet and cfg.get("greeting", {}).get("enabled", True):
            quiet = str(callouts.make_silence(SKILL / "assets" / "sfx_silence.wav"))
            # a quick swish with the slide-in, like his editors (spectrum of Amiri Jeans / LV Trainer: a short broadband
            # whoosh as the avatar enters); the synthetic pop was "not a big fan" (maison mahara 2026-10-26)
            # ...but the full-level Fast Swish was "too abrasive" ($30k reselling 2026-10-26); his published greetings (Best
            # Free Dhgate Reselling Spreadsheet 0:44) carry only a faint ~0.1 s air under his voice: a 0.4 s soft breath
            # whoosh, 4.2 kHz low-pass, peak -7 dB (sfx_greet_soft.wav, from Swoosh Pack "Breath Whoosh")
            swish = SKILL / "assets" / "sfx_greet_soft.wav"
            if not swish.exists():
                swish = SKILL / "assets" / "sfx_greet_swish.wav"
            pop = str(swish if swish.exists() else callouts.make_pop_sound(SKILL / "assets" / "sfx_pop.wav"))
            kept_g, gc = [], cfg.get("greeting", {})
            for g in greet:
                if g["kind"] == "avatar":
                    if not av:
                        continue
                    g.update(card=str(callouts.make_avatar_card(work, av)), center=gc.get("avatar_center", [0.71, 0.48]), motion="slide_right", sound=gc.get("avatar_sound") or pop, sound_db=gc.get("avatar_sound_db", -14))   # RIGHT side, 400 px, slides in from the right edge like his editors (Amiri Jeans + LV Trainer measured frame by frame 2026-10-26); x .71: between the first .62 ("too close to me") and .77 ("a little too far off to the right", maison mahara 2026-10-26)
                else:
                    g.update(card=str(callouts.make_caption_card(work, g["text"], cfg)), center=[0.5, 0.88], sound=quiet)
                kept_g.append(g)
            cash = cash or callouts.price_sound(SKILL, cfg)
            prices = sorted(prices + kept_g, key=lambda x: x["out"])
            checks.append("Greeting callout: " + ", ".join(f"{g['text']} @ {g['out']:.1f} s" for g in kept_g) + ".")
    except Exception as e:  # noqa: never stops a build
        checks.append(f"Greeting callout failed ({type(e).__name__}: {str(e)[:120]}).")

    # step 7
    out_sections = [{"name": s["name"], "start": round(tl.to_out(s["start"]), 2), "end": round(tl.to_out(s["end"]), 2)}
                    for s in sec["sections"]]
    # segment changes sit on a cut with a slide transition, and each segment's beat starts exactly there
    transitions = section_transitions(sec["sections"], kept, rows, tl, cfg)
    for tr in transitions:
        for i in range(1, len(out_sections)):
            if out_sections[i]["name"] == tr["to"]:
                out_sections[i]["start"] = out_sections[i - 1]["end"] = tr["out"]
    # a top-N countdown (countdown.py): a slide, a number card and its own beat per item (intro -> #5 .. #1 -> bonus -> outro)
    cd_items, music_sections = [], None
    try:
        cd_items = countdown.find_items(project, words, kept, tl, cfg, checks)
        if cd_items:
            music_sections, transitions = countdown.plan(cd_items, transitions, out_sections, tl.duration)
            for it in cd_items:
                it["card"] = str(countdown.make_card(work, it["label"], it.get("name", "")))
    except Exception as e:  # noqa: never stops a build
        cd_items, music_sections = [], None
        checks.append(f"Countdown failed ({type(e).__name__}: {str(e)[:140]}); plain sections used.")
    msecs = music_sections or out_sections
    # beats back to back, never one track looping under a long section: one beat per section plus spares to chain
    music = pick_music(project, cfg, checks, n=len(msecs) + cfg["music"].get("spare_beats", 3))
    try:
        music = countdown.make_beds(music, msecs, work, checks, lead=cfg.get("transitions", {}).get("seconds", 0.5))
    except Exception as e:  # noqa: never stops a build
        music = music[:len(msecs)]
        checks.append(f"Back-to-back music beds failed ({type(e).__name__}: {str(e)[:120]}); beats loop.")
    ctx = {
        "intro_joined": has_intro(project),
        "cfg": cfg, "tl": tl, "kept": kept, "duration": duration, "half_w": half_w, "half_h": half_h,
        "face_x": float(np.median(fx)) if fx else 0.5,
        "face_y": float(np.median(fy)) if fy else 0.5,
        "edges": edge_margins(cam, W, H, duration, work, checks),
        "face_y_circle": float(np.median(fy)) if fy else 0.5,
        "expr_fullA": enable_expr(tl.intervals(full_a)),
        # face circle: review/showcase only, and never on top of B-roll
        # the circle comes back on the SAME frame as the desk camera after a B-roll (balenciaga track led review
        # 2026-10-26, 2:07: hidden 0.15 s longer after an on-cut B-roll, "the face cam jumps in later ... it should be
        # snapped on exactly the same second"); one frame of margin only
        "expr_pip": enable_expr(subtract(tl.intervals(pip_ranges), [(c["out_start"], c["out_start"] + c["length"] + (1 / FPS if c.get("on_cut") else 0)) for c in placed])),
        "expr_pipB": enable_expr(subtract(tl.intervals(pip_b), [(c["out_start"], c["out_start"] + c["length"] + (1 / FPS if c.get("on_cut") else 0)) for c in placed])),
        "rface_x": float(np.median(rfx)) if rfx else 0.5, "rface_y": float(np.median(rfy)) if rfy else 0.5,
        "circle_pad": pad, "subs": subs, "music": music, "out_sections": out_sections,
        "music_sections": music_sections, "countdown": cd_items,
        "voice_eq": voice_eq(project, kept, cfg, checks),
        # stretches where he sat back from the mic, lifted (output time)
        # quiet lines lifted + loud words / hot clip entrances brought down (balenciaga 2026-10-26, 3:35)
        "voice_lift": [(tl.to_out(x), tl.to_out(y), g) for x, y, g in
                       joins.quiet_lines(kept, _mic16k(project, cam), checks) + joins.loud_words(kept, _mic16k(project, cam), checks)],
        "levels": levels(project, music, cfg), "zooms": zooms, "broll": placed, "prices": prices, "cash": cash,
        "inserts": inserts, "transitions": transitions,
    }
    if "--plan-only" in sys.argv:   # everything up to the render (layout, countdown, music beds) checked without encoding
        save_json(work / "plan_only.json", {
            "full_a": tl.intervals(full_a), "pip": tl.intervals(pip_ranges), "swap": tl.intervals(swap),
            "transitions": transitions, "countdown": cd_items, "music_sections": music_sections,
            "music": [str(m) for m in music], "checks": checks})
        print(f"plan-only: {len(transitions)} transitions, {len(cd_items)} countdown cards, {len(music)} beds")
        return
    final = render(project, ctx, checks)                   # step 8
    if ctx.get("inserted") or ctx.get("trans_made"):
        # the draft as he watches it: kept ranges with each cutaway as a negative range (the Studio's convention for inserted
        # clips, gaming body.py), so his draft times after a cutaway still map to the right recording time
        rendered, ins = [], sorted(ctx.get("inserted") or [])
        tmade = {tr["src"]: ln for tr in transitions for o, ln in (ctx.get("trans_made") or []) if abs(o - tr["out"]) < 1e-3}
        for a, b in kept:
            if round(a, 3) in tmade:   # the slide plays right before this clip
                rendered.append([round(-2000 - tmade[round(a, 3)], 3), -2000.0])
            # a slide on a PAUSE inside this clip (countdown.snap when no cut is near): the clip is split around it, so
            # his draft times after it still map to the right recording time
            for s_, ln in sorted((s_, ln) for s_, ln in tmade.items() if a + 1e-3 < s_ < b - 1e-3):
                rendered.append([round(a, 3), round(s_, 3)])
                rendered.append([round(-2000 - ln, 3), -2000.0])
                a = s_
            for o, ln in ins:
                at = next((i["at"] for i in inserts if abs(i["out"] - o) < 1e-3), None)
                if at is not None and a <= at < b:
                    if at > a:
                        rendered.append([round(a, 3), round(at, 3)])
                    rendered.append([round(-1000 - ln, 3), -1000.0])
                    a = at
            rendered.append([round(a, 3), round(b, 3)])
        save_json(work / "timeline.json", {"kept": [[round(a, 3), round(b, 3)] for a, b in kept], "rendered": rendered,
                                            "inserts": [{"out": o, "len": ln} for o, ln in ins],
                                            "transitions": [{"out": o, "len": ln} for o, ln in ctx.get("trans_made") or []]})
    if music:
        log_music(project, music)

    # report
    names = {"intro": "Intro", "review": "Product review", "showcase": "Showcase", "outro": "Outro"}
    L = ["# Edit report", "", f"- Source: `{cam}` ({W}x{H}, {fmt(duration)})",
         f"- Output: `{final}` ({fmt(tl.duration + sum(x[1] for x in (ctx.get('inserted') or []) + (ctx.get('trans_made') or [])))}), preview `output/preview_{cfg['output']['preview_height']}p.mp4`",
         f"- Encoder: {ctx['encoder']}", "", f"## Sections ({sec['method']})", "",
         "| Section | Final video | Source |", "|---|---|---|"]
    for s, o in zip(sec["sections"], out_sections):
        L.append(f"| {names.get(s['name'], s['name'])} | {fmt(o['start'])} – {fmt(o['end'])} | {fmt(s['start'])} – {fmt(s['end'])} |")
    L += ["", "## Edit", "", f"- Cut: {cuts['removed_seconds'] / 60:.1f} min ({cuts['removed_seconds']:.1f} s)",
          f"- Camera switches: {switches}",
          f"- Full-face cutaways (\"on my face\"): {len(face_full)}",
          f"- Face circle hidden during head turns: {'yes' if cfg['face_cam'].get('hide_on_turn') else 'no'}"]
    nf, ns = sum(1 for z in zooms if z["kind"] == "face"), sum(1 for z in zooms if z["kind"] == "screen")
    nd = sum(1 for z in zooms if z["kind"] == "side")
    tz = [z for z in zooms if z["kind"].startswith("topic_")]
    L.append(f"- Zooms: {nf} face punch-ins, {ns} cursor zooms on the screen, {nd} side-angle drifts, {len(tz)} screen topic zooms"
             + "".join(f"\n  - {fmt(tl.to_out(z['start']))} {z['kind'][6:]} panel ({z['zoom']}x, \"{z['why']}\")" for z in tz)
             if cfg.get("zooms", {}).get("enabled") else "- Zooms: off")
    lo = ctx.get("loudness", {})
    if lo.get("measured") is not None:
        L.append(f"- Volume: mix measured {lo['measured']:.1f} LUFS, raised {lo['gain']:.1f} dB (max {cfg['output']['max_boost_db']} dB, never lowered)")
    L.append(f"- B-roll: {len(placed)} of {len(slots)} slots filled" + "".join(
        f"\n  - Slot {c['slot']} at {fmt(c['out_start'])}: {Path(c['file']).name} ({c['length']:.1f} s, {c['speed']:.2f}x speed)" for c in placed))
    L.append(f"- Price callouts: {len(prices)}" + "".join(f"\n  - {fmt(pr['out'])}: {pr['text']}" for pr in prices))
    L.append(f"- Subscribe animations: {len(subs)}" + ("".join(f"\n  - {fmt(s['out'])} (\"{s['word']}\")" for s in subs)))
    L.append("- Beats:" + "".join(f"\n  - {names.get(s['name'], s['name'])}: {b.name}" for s, b in zip(ctx.get("music_sections") or sec["sections"], music)) if music else "- Beats: none")
    if ctx.get("countdown"):
        L.append("- Countdown: " + ", ".join(f"{it['label']} {it.get('name', '')} at {fmt(it['out'])}".strip() for it in ctx["countdown"]))
    # Check these = only what needs a look or a decision; the rest is a log of what the guards already did (2026-10-25:
    # lists ran 18-27 items, mostly "guard moved X", so the real ones got lost)
    need, done = [], []
    for c in checks:
        (need if needs_look(c) else done).append(c)
    L += ["", f"## Check these ({len(need)})", ""] + ([f"- {c}" for c in need] or ["- Nothing flagged."])
    L += ["", f"## What the edit did ({len(done)})", ""] + [f"- {c}" for c in done]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Done: {final} ({len(need)} item{'s' if len(need) != 1 else ''} in Check these, {len(done)} logged)")


NEEDS_LOOK = ("not done", "failed", "could not", "couldn't", "check ", "check them", "check the", "listen", "not reviewed",
              "missing", " may ", "?", "fallback", "stopped", "wrong", "error", "left out", "not found", "unresolved")


def needs_look(line):
    """a Check these line that asks for a look (a failure, a guess, something to listen to); FYI lines and the guards'
    'moved / trimmed / dropped / put back' logs are not"""
    low = line.lower()
    if low.startswith("fyi"):
        return False
    return any(k in low for k in NEEDS_LOOK)


if __name__ == "__main__":
    main()
