"""Bad-take cutter for raw talking videos (promo-code / app tutorial videos: webcam left, PC/phone right).

Rules (from Duncan Rogoff's AI-editing guide, job 2 "the cut", + the product-review skill):
  - every word gets a timestamp (Whisper); KEEP THE LAST CLEAN TAKE of every line, cut the earlier tries
  - restart = the opening words of a phrase come back soon after (3 words if within 4 s, 5 words within 40 s)
  - intro: the LAST "hey guys ... here" take in the first 90 s wins, everything before it goes; with no greeting, the
    warm-up before the presenter voice kicks in (louder / higher / faster, opening.py) goes
  - asides to yourself ("cut that", "hold on", "nope") are cut but listed as REVIEW so the user can veto
  - silences over 0.6 s shrink to 0.2 s, except while the phone is being used on screen (those are listed)
  - cut points snap to video frames so picture and sound cut together (atrim drift lesson, product-review skill)

Usage:
  python take_cuts.py <words.json> <fps> <out_dir> [--duration S] [--extra extra_cuts.json] [--audio mic.wav] [--video src] [--no-mutters]
    words.json = [{"w","s","e"}] from faster-whisper word_timestamps (verbatim prompt, condition_on_previous_text=False)
  -> out_dir/cuts.json (keep ranges + every cut with reason) and out_dir/cuts.md (human review list)
"""
import difflib
import json
import os
import re
import sys

OK_DOUBLES = {"very", "really", "bye", "no", "yeah", "so", "ha", "go", "to", "that", "had", "is"}  # "very very easy" is how they talk
ASIDE_CUES = ["whoops", "i think i just want to", "i got the method", "screwed me", "i don't want to recommend", "cut that", "hold on", "nope", "let's do that", "oh shoot", "i forgot", "i'm just gonna trust",
              "i see what's going on", "that was the intro", "think that might be it", "what was i called",
              "should be blurred", "gets blurred", "is up dead",
              # notes to the editor + reactions to the setup (Doordash 2026-10-21: "you got to blur the address" made the draft)
              "blur the", "blur it", "blur that", "what the heck", "cut it", "run that whole thing back", "run this back",
              "run it back", "run that back", "leaking my address", "are all leaking", "my bad", "one more time",
              "set that up", "to my list"]  # notes to self about the setup (Shein 1:22 "I need to set that up. Let me")
TAKE_OPENERS = [("for", "next", "code"), ("for", "our", "next", "code"), ("for", "last", "code"), ("for", "our", "last", "code"),
                ("for", "the", "next", "code"), ("next", "code"), ("last", "code"), ("for", "next", "method"),
                ("for", "our", "next", "method"), ("for", "the", "next", "method"), ("our", "next", "code"), ("our", "last", "code")]
EDITOR_CUES = ["blur the", "blur it", "blur that", "cut it", "cut that", "run that whole thing back", "run this back", "run it back",
               "run that back", "leaking my address", "are all leaking"]


def norm(w):
    return re.sub(r"[^a-z0-9$]", "", w.lower())


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def phrase_starts(words):
    """Index of words that open a phrase: after a pause, or after sentence punctuation."""
    starts = {0}
    for i in range(1, len(words)):
        if words[i]["s"] - words[i - 1]["e"] >= 0.25 or words[i - 1]["w"][-1:] in ".?!,":
            starts.add(i)
    return starts


def abandoned(words, i, j, within=14):
    """A far-apart match only counts if the earlier try was dropped: it stops (pause >= 0.8 s) within a few
    words. Stock phrases ("you want to go ahead and ...") in fluent speech run on, so they are never cut."""
    for k in range(i + 1, min(j, i + within)):
        if words[k]["s"] - words[k - 1]["e"] >= 0.8:
            return True
    # or a whole sentence (<= 25 words) said, a pause, then said again
    return j - i <= 25 and words[j]["s"] - words[j - 1]["e"] >= 1.0


def narration(n, words, i, j):
    """A repeated opener is NOT a retake when the first try was finished: no pause before the repeat and the first
    try carries on with 3+ new words that the second doesn't repeat ("this was an anarchy world and then I started
    traveling over here and then I started seeing a lot more carnage", user note 2026-10-20, Top 5 Realms 5:03)."""
    if words[j]["s"] - words[j - 1]["e"] >= 0.8:
        return False
    m = 0
    while i + m < j and j + m < len(n) and n[i + m] == n[j + m]:
        m += 1
    extra = [x for x in n[i + m:j] if len(x) > 2]
    second = set(n[j + m:j + m + len(extra) + 4])
    return len(extra) >= 3 and len(set(extra) & second) <= len(extra) // 3


def find_restarts(words):
    n = [norm(w["w"]) for w in words]
    starts = phrase_starts(words)
    cuts, i = [], 0
    while i < len(words):
        i0 = i
        best = None
        for j in range(i + 3, len(words)):
            gap = words[j]["s"] - words[i]["s"]
            if gap > 75:
                break
            a8, b8 = n[i:i + 8], n[j:j + 8]
            same8 = sum(x == y for x, y in zip(a8, b8)) if len(a8) == 8 and len(b8) == 8 else 0
            if a8[:1] == b8[:1] and (same8 == 8 or (same8 == 7 and abandoned(words, i, j))):
                # 8 opening words identical = the same line again, even said fluently
                # ("it doesn't sound like a lot but you/it ..." 7 of 8 in fluent speech is NOT a retake)
                ok = True
            elif gap <= 6:
                # stutter restart, no pause needed: "when you are signing when you are signing up"
                ok = n[i:i + 3] == n[j:j + 3] and any(len(x) > 3 for x in n[i:i + 3]) and j - i <= 6
            elif i in starts:
                # same line started again after a while: first 3 words exact (gap <= 12 s), or 4 of the first 5
                # ("in order to do this method" vs "in order to do the method")
                a, b = n[i:i + 5], n[j:j + 5]
                ok = len(a) == 5 and len(b) == 5 and (
                    (gap <= 12 and a[:3] == b[:3] and any(len(x) > 3 for x in a[:3]) and abandoned(words, i, j))
                    or (sum(x == y for x, y in zip(a, b)) >= 4 and a[0] == b[0] and abandoned(words, i, j)))
            else:
                ok = False
            if not ok and gap <= 15 and j - i <= 30 and len(n[j:j + 10]) == 10 and n[i:i + 2] == n[j:j + 2] and                     (words[j]["s"] - words[j - 1]["e"] >= 0.8 or (j - i <= 8 and n[i:i + 3] == n[j:j + 3])):
                # 2 identical opening words (3 without a pause): one shared word cut real lines ("you're under 18 or |
                # you're just not able", lists like "you got Target, you got Amazon")
                # fuzzy restart: same first word + similar opening, after a pause (or a short false start).
                # Learned from the user's finished edit: "once you are signed up you want" -> "once you GUYS are signed up",
                # "also if you go here partner rewards" -> "also if you click on partner rewards",
                # "for next method it's going to be the app called eureka" -> "for the next app ... it's going to be eureka"
                r6 = difflib.SequenceMatcher(None, n[i:i + 6], n[j:j + 6]).ratio()
                r10 = difflib.SequenceMatcher(None, n[i:i + 10], n[j:j + 10]).ratio()
                ok = r6 >= 0.66 or r10 >= 0.55
                # a "first try" that FINISHED two or more sentences and is NOT said again as a whole is the line before,
                # not a false start: the Short hook "What is a lift kit? Why is everyone putting one on their truck? It's
                # not just about looks. ..." vs "A lift kit is exactly what it sounds like" (r6 0.67) cut the whole hook
                # (2026-10-23). A real redo repeats the whole take ("So what's a lift kit really? ... handles." ->
                # "So what is a lift kit really? ... feels.", ratio ~0.9), so it stays a retake.
                if ok and sum(words[q]["w"].strip()[-1:] in ".?!" for q in range(i, j)) >= 2 and \
                        difflib.SequenceMatcher(None, n[i:j], n[j:j + (j - i)]).ratio() < 0.5:
                    ok = False
            if ok and same8 != 8 and narration(n, words, i, j):
                ok = False
            # a "which is / aka / meaning ..." join with no pause is one sentence restating itself with NEW facts, not a
            # restart (maison mahara dhgae review 2026-10-26, 1:03: "these are going to be a size 44 which is | going to
            # be a size 10" read as a retake; the cut left "back to the shoes, | going to be a size 10" and the shoes
            # popped onto the mousepad: "such a jarring cut ... they just spawn in out of nowhere"). Same when the first
            # try holds a number the second never says: that is information, not a flub.
            if ok and j - i <= 14:
                lead = " ".join(n[max(i, j - 3):j])
                joined = words[j]["s"] - words[j - 1]["e"] < 0.5 and re.search(
                    r"\b(which is|which are|that is|that's|aka|meaning|or|basically|so)$", lead)
                nums_a = {x for x in n[i:j] if re.fullmatch(r"\d+", x)}
                nums_b = {x for x in n[j:j + (j - i) + 4] if re.fullmatch(r"\d+", x)}
                if joined or (nums_a and not nums_a <= nums_b):
                    ok = False
            if ok:
                best = j  # keep looking: the LAST matching restart in the chain wins
        if best is not None:
            best_raw = best
            # (no "slide back over identical words" step: it pulled a stray "for" from the previous broken take
            # into the kept one - "signing up for | for when you are signing up", user note 2026-10-20.
            # The sentence-start snap below handles the "hey guys shift reviews | here" case on its own.)
            # slide both takes back over an identical word, but ONLY if that word opens a phrase in the kept take
            # ("rewards. ALSO if you go | ALSO if you click" -> cut the 1st "also" too; without the guard it pulled a
            # stray "for" out of "signing up for | when you are", user notes 2026-10-20)
            hard0 = lambda q: q > 0 and (words[q]["s"] - words[q - 1]["e"] >= 0.25 or words[q - 1]["w"][-1:] in ".?!,")
            while i > 0 and best - 1 > i and n[i - 1] == n[best - 1] and (hard0(best - 1) or len(n[best - 1]) >= 4):
                i, best = i - 1, best - 1
            # and never start the kept take mid-phrase: snap its start back to its phrase start (<= 6 words)
            # (sentence starts only: a comma is not a start, "hey guys, | shift reviews" must stay whole)
            hard = lambda q: words[q]["s"] - words[q - 1]["e"] >= 0.25 or words[q - 1]["w"][-1:] in ".?!"
            p = best
            while p - 1 > i and not hard(p) and best - p < 10:  # 6 lost "but anyways guys, that's pretty much" (user note)
                p -= 1
            if hard(p):
                best = p
            # a differently-worded false start right before the chain goes too ("so the first method is going to be
            # to you want to hop on, so | in order to do the method"): back to the last clear stop (pause >= 1.5 s),
            # only if that fragment is short and never finished a sentence (user note, 2026-10-20)
            k = i
            while k > 0 and i - k < 20 and words[k]["s"] - words[k - 1]["e"] < 1.5 and words[k - 1]["w"][-1:] not in ".?!":
                k -= 1
            if k < i and i - k < 20 and (k == 0 or words[k]["s"] - words[k - 1]["e"] >= 1.5):
                i = k
            if best <= i0 and cuts and abs(cuts[-1]["e"] - words[i0]["s"]) < 0.01:
                # a 3rd (4th...) take of the same line: the slide-backs above put best back where this scan started, and
                # three takes in a row bounced between two of them forever (dhgate rick owens 2026-10-22: "Next up we do
                # have | Next up in front of us we do have | Next up in front of us. We do have"). The chain is ONE cut
                # from the first take's sentence start to the last take, never a leftover "Next up".
                c = cuts[-1]
                a = next(q for q in range(len(words)) if abs(words[q]["s"] - c["s"]) < 0.01)
                q = a
                while q > 0 and a - q < 6 and words[q]["s"] - words[q - 1]["e"] < 0.7 and words[q - 1]["w"][-1:] not in ".?!":
                    q -= 1
                if q < a and (q == 0 or words[q]["s"] - words[q - 1]["e"] >= 0.7 or words[q - 1]["w"][-1:] in ".?!"):
                    a = q
                c.update(s=words[a]["s"], e=words[best_raw]["s"], text=" ".join(w["w"] for w in words[a:best_raw]),
                         kept=" ".join(w["w"] for w in words[best_raw:best_raw + 8]) + " ...")
                i = best_raw
                continue
            cuts.append({"s": words[i]["s"], "e": words[best]["s"], "why": "retake",
                         "text": " ".join(w["w"] for w in words[i:best]),
                         "kept": " ".join(w["w"] for w in words[best:best + 8]) + " ..."})
            i = max(best, i0 + 1)   # never backwards (see the chain case above)
            continue
        i += 1
    return cuts


def find_stuck(words):
    """A 3-4 word phrase said 3+ times within 15 s = a stuck line ("take advantage of ... take advantage of ...
    take advantage of this"): cut from the 1st to the LAST time (user notes, 2026-10-20)."""
    n = [norm(w["w"]) for w in words]
    cuts, i = [], 0
    while i < len(words):
        done = False
        for k in (4, 3):
            g = n[i:i + k]
            # needs a real word: "is going to be" said 3 times in a row of code reads is not a stuck line (it cut the
            # opening of the last "20 Garcia" take, Shein 2026-10-21)
            if len(g) < k or not any(len(x) > 3 and x not in STOP for x in g):
                continue
            hits = [j for j in range(i, len(words) - k + 1) if words[j]["s"] - words[i]["s"] <= 15 and n[j:j + k] == g]
            # a stuck line restarts at once; "put IN THE CODE, head over to ... type IN THE CODE EXAMPLECODE ... type IN THE CODE"
            # is an explanation that reuses a phrase, and cutting it lost the code steps (Doordash 2026-10-21)
            if len(hits) >= 3 and max(b - a for a, b in zip(hits, hits[1:])) <= 12 + k:
                # keep the last time from the start of ITS sentence ("So I added this pizza | to my cart" lost the
                # opening, Doordash 2026-10-21): back up to a full stop or a pause, at most 10 words
                j = hits[-1]
                while j > hits[-2] + k and hits[-1] - j < 10 and words[j - 1]["w"][-1:] not in ".?!" and words[j]["s"] - words[j - 1]["e"] < 0.5:
                    j -= 1
                if not (words[j - 1]["w"][-1:] in ".?!" or words[j]["s"] - words[j - 1]["e"] >= 0.5):
                    j = hits[-1]
                cuts.append({"s": words[i]["s"], "e": words[j]["s"], "why": "stuck line (said 3+ times)",
                             "text": " ".join(w["w"] for w in words[i:j]),
                             "kept": " ".join(w["w"] for w in words[j:j + 8]) + " ..."})
                i, done = hits[-1], True
                break
        i += 1 if not done else 0
        if done:
            i += 1
    return cuts


def drop_orphans(words, cuts):
    """A kept piece under 9 words, cut on both sides by retake/aside/stuck cuts, that never ends a sentence AND
    stutters inside itself = leftover of a line never finished ("once you have once a brand new account").
    Without the stutter test it ate lead-ins like "take advantage of this | this is actually going to be"."""
    hard = sorted((c["s"], c["e"]) for c in cuts if not c["why"].startswith("silence"))
    out = []
    for (a0, a1), (b0, b1) in zip(hard, hard[1:]):
        mid = [w for w in words if a1 <= w["s"] < b0]
        toks = [norm(w["w"]) for w in mid]
        stutters = len(set(t for t in toks if len(t) > 2 and toks.count(t) > 1)) > 0  # "ONCE you have ONCE a"
        if 0 < len(mid) < 9 and stutters and not any(w["w"][-1:] in ".?!" for w in mid[:-1]) and b0 - a1 < 12:
            out.append({"s": a1, "e": b0, "why": "orphan fragment", "text": " ".join(w["w"] for w in mid), "kept": ""})
    return out


def find_mutters(words, audio_path, video=None, cuts=()):
    """Under-the-breath talk while they navigate ("what was I called", "how do you put in the code") is >= 8 dB
    quieter than their normal voice. Pause-bounded lines that quiet are cut (learned from the user's finished edit).
    With the video: a line >= 4 dB quiet while they look down at the phone / turn away on the webcam is an off-camera
    aside, and a short quiet line between two cut asides goes too (Doordash 2026-10-21: "Zilla, not Zilla", "Well Zach
    left", "I think I was trying to turn it" were 4-9 dB quiet, head down or turned, and made the draft)."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", audio_path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    def lvl(w):
        x = a[int(w["s"] * 16000):int(w["e"] * 16000)]
        return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) if len(x) else -99
    lv = [lvl(w) for w in words]
    ref = float(np.percentile(lv, 70))
    lines, cur = [], [0]
    for i in range(1, len(words)):
        if words[i]["s"] - words[i - 1]["e"] >= 0.6:
            lines.append(cur)
            cur = []
        cur.append(i)
    lines.append(cur)
    out, med, gone = [], [], []
    for ln in lines:
        m = float(np.median([lv[i] for i in ln]))
        med.append(m - ref)
        s, e = words[ln[0]]["s"], words[ln[-1]]["e"]
        gone.append(m < ref - 9 or any(c["s"] <= s + 0.05 and e - 0.05 <= c["e"] and not c["why"].startswith("silence") for c in cuts))
        if m < ref - 9 and len(ln) <= 25:
            out.append({"s": s, "e": e + 0.1, "why": f"mutter ({m - ref:.0f} dB) REVIEW",
                        "text": " ".join(words[i]["w"] for i in ln), "kept": ""})
    if not video:
        return out
    span = lambda ln: (words[ln[0]]["s"], words[ln[-1]]["e"])
    cand = [span(ln) for k, ln in enumerate(lines) if -9 <= med[k] <= -4 and len(ln) <= 30]
    # "facing the camera" = their head pose on normal-level lines (this rig: pitch ~18 facing, ~30 looking at the phone)
    normal = [span(ln) for k, ln in enumerate(lines) if med[k] >= -2 and len(ln) >= 8]
    normal = normal[::max(1, len(normal) // 15)][:15]
    poses = _head_poses(video, cand + normal) if cand else {}
    base = [pq for sp in normal for pq in poses.get(sp, [])]
    if len(base) < 6:
        return out
    my, mp_ = float(np.median([y for y, _ in base])), float(np.median([q for _, q in base]))
    for k, ln in enumerate(lines):
        s, e = span(ln)
        p = poses.get((s, e))
        if p and -9 <= med[k] <= -4:
            away = sum(1 for y, q in p if abs(y - my) >= 18 or q - mp_ >= 7)
            if away * 2 > len(p):
                gone[k] = True
                out.append({"s": s, "e": e + 0.1, "why": f"off-camera aside ({med[k]:.0f} dB, looking away) REVIEW",
                            "text": " ".join(words[i]["w"] for i in ln), "kept": ""})
    for k in range(1, len(lines) - 1):  # a short quiet line between two cut asides ("Well Zach left")
        ln = lines[k]
        if not gone[k] and gone[k - 1] and gone[k + 1] and len(ln) <= 6 and med[k] <= -3:
            out.append({"s": words[ln[0]]["s"], "e": words[ln[-1]]["e"] + 0.1, "why": f"between asides ({med[k]:.0f} dB) REVIEW",
                        "text": " ".join(words[i]["w"] for i in ln), "kept": ""})
    return out


def _head_poses(video, spans, crop="crop=1920:1080:0:0"):
    """(yaw, pitch) of the webcam face at 3 points of each span (left half of the OBS capture). Spans with no face
    (the screen is shown there) get nothing, so only the level rules apply to them."""
    import math
    import subprocess
    import numpy as np
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except ImportError:
        return {}
    L = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=r"{{KIT}}/review_pipeline/models/face_landmarker.task"),
        output_facial_transformation_matrixes=True, num_faces=1))
    out = {}
    for s, e in spans:
        got = []
        for t in np.linspace(s, e, 3):
            fr = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", f"{crop},scale=960:540",
                                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            if len(fr) < 960 * 540 * 3:
                continue
            r = L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.frombuffer(fr, np.uint8).reshape(540, 960, 3).copy()))
            if r.face_landmarks:
                m = np.array(r.facial_transformation_matrixes[0]).reshape(4, 4)[:3, :3]
                got.append((math.degrees(math.atan2(-m[2, 0], math.hypot(m[0, 0], m[1, 0]))), math.degrees(math.atan2(m[2, 1], m[2, 2]))))
        if len(got) >= 2:
            out[(s, e)] = got
    return out


STOP = set("a an the and or but so to of in on for at it its it's is are was be been i im i'm you your you're we our they this that these those with as if just like um uh yeah okay gonna going go get got do does did have has had can will would very really actually pretty much here there what which who how all any some one".split())


def find_resaid(words, window=180.0):
    """Same content said again later in DIFFERENT words = an earlier take of that part (learned from Gling's cuts on
    the alo video: "so in order to get aloe clothing, simply go over to solo.to" -> later "if you are wondering where
    to purchase aloe from... simply go over to solo.to slash shift three"). Sentences = pause/punctuation bounded."""
    sents, cur = [], []
    for k, w in enumerate(words):
        cur.append(k)
        nxt = words[k + 1] if k + 1 < len(words) else None
        if w["w"][-1:] in ".?!" or nxt is None or nxt["s"] - w["e"] >= 0.7:
            sents.append(cur)
            cur = []
    bag = lambda ix: {norm(words[k]["w"]) for k in ix} - STOP - {""}
    cuts = []
    for a in range(len(sents)):
        A = bag(sents[a])
        if len(A) < 5:
            continue
        for b in range(a + 1, len(sents)):
            if words[sents[b][0]]["s"] - words[sents[a][-1]]["e"] > window:
                break
            B = bag(sents[b])
            shared = A & B
            if len(B) >= 5 and len(shared) >= 4 and len(shared) / min(len(A), len(B)) >= 0.5:
                cuts.append({"s": words[sents[a][0]]["s"], "e": words[sents[a][-1]]["e"] + 0.05, "why": "re-said later",
                             "text": " ".join(words[k]["w"] for k in sents[a]),
                             "kept": " ".join(words[k]["w"] for k in sents[b][:10]) + " ..."})
                break
    return cuts


def _stem(w):
    w = norm(w)
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


RUNBACK_CUES = ["my bad", "my fault", "i didnt realize", "didnt realize", "wrong one", "thats wrong", "the wrong", "i messed up",
                "messed up", "start over", "start that over", "redo", "redo that", "do that again", "do it again", "run it back",
                "run that back", "run this back", "let me restart", "scratch that", "whoops", "oops",
                # the wrong product / page (lv skatesta 2026-10-24: "wait, those aren't LV skates though ... hold on")
                "wrong link", "wrong shoe", "wrong shoes", "wrong page", "wrong product", "wrong listing", "not the right",
                "arent the right", "those arent", "these arent the"]


def find_runback(words, kept, min_gap=60.0, max_run=240.0, opener_within=3, product_starts=()):
    """A whole stretch RUN BACK (s25 ultra 2026-10-23, 6:10-7:07: "we had that's a whole ran back section by accident ...
    I literally just jumped to 7:00 something and it was fixed"): he walks through a part (the link, the product page,
    bulk buying, colours), stops, resets for minutes (a cut >= min_gap s of recording), and starts the SAME part again in
    other words ("Once you have clicked on it, you're going to be brought to a page looking like this" -> "When you click
    on the link, you'll be brought to a page looking like this"). Runs on what is KEPT (after the trimmer), so the take
    review's single sentences don't count. To be safe, a run-back needs ALL of:
      - a long cut (>= min_gap s) between the two tries: he stopped and re-recorded,
      - one of the first `opener_within` kept sentences after that cut re-says a sentence of the stretch before it,
      - at least one MORE line of that stretch said again in the part after the cut (a whole part re-done, not one line),
      - the stretch (from the first re-said line to the cut) <= max_run s.
      - he says he got something wrong in the reset (RUNBACK_CUES), and no new product starts between the two tries.
    The earlier stretch is cut from the first re-said line; it is listed in Check these."""
    mid = lambda w: (w["s"] + w["e"]) / 2
    kw = [w for w in words if any(a <= mid(w) <= b for a, b in kept)]
    sents, cur = [], []
    for k, w in enumerate(kw):
        cur.append(w)
        nxt = kw[k + 1] if k + 1 < len(kw) else None
        if w["w"][-1:] in ".?!" or nxt is None or nxt["s"] - w["e"] >= 0.7:
            sents.append(cur)
            cur = []
    bag = lambda ws: {_stem(x["w"]) for x in ws} - STOP - {""}
    bags = [bag(x) for x in sents]

    def same(i, j, n=4, r=0.5):
        A, B = bags[i], bags[j]
        sh = A & B
        return len(A) >= 4 and len(B) >= 4 and len(sh) >= n and len(sh) / min(len(A), len(B)) >= r

    cuts = []
    gaps = [k for k in range(1, len(sents)) if sents[k][0]["s"] - sents[k - 1][-1]["e"] >= min_gap]
    for g in gaps:
        cut_start = sents[g - 1][-1]["e"]
        for j in range(g, min(g + opener_within, len(sents))):
            befores = [i for i in range(g - 1, -1, -1) if cut_start - sents[i][0]["s"] <= max_run and same(i, j)]
            if not befores:
                continue
            i0 = min(befores)
            # a new product starts in between: the same template line for the next product, not a redo (rick owens)
            if any(sents[i0][0]["s"] < p <= sents[j][0]["s"] for p in product_starts):
                continue
            after = range(j + 1, min(len(sents), j + 40))
            more = [(i, k) for i in range(i0 + 1, g) for k in after if same(i, k, n=2, r=0.4)]
            if not more:
                continue
            # ...and in the cut reset he says he got something wrong ("wait, my bad ... that's the S24 ... that's my fault").
            # Multi-product videos re-use the same template lines for every product ("We do have the Rick Owens ...",
            # "here's what the Amiri jeans look like on body") with a long try-on cut between: no mistake cue there
            # (tested on the 8 approved projects: only s25 ultra fires).
            gap = " " + " ".join(norm(x["w"]) for x in words if cut_start <= x["s"] < sents[g][0]["s"]) + " "
            if not any(f" {c} " in gap for c in RUNBACK_CUES):
                continue
            cuts.append({"s": sents[i0][0]["s"] - 0.05, "e": cut_start + 0.05, "why": "run-back: the same part re-done after a reset",
                         "text": " ".join(x["w"] for x in sents[i0])[:120],
                         "kept": " ".join(x["w"] for x in sents[j][:12]) + " ...",
                         "also": [" ".join(x["w"] for x in sents[i][:8]) for i, _ in more[:3]]})
            break
    return cuts + find_reopener(words, kept, product_starts=product_starts)


def find_reopener(words, kept, min_gap=3.0, look_back=90.0, product_starts=()):
    """A part RE-STARTED after a short reset, in other words (dhgate watchb spread 2026-10-24, 2:23 + 2:53: "One thing that
    you do want to pay attention to ... take advantage of the bulk buying discount ... save big money", a 7 s pause, then
    "One thing you do want to pay attention to, it's gonna be the bulk buying discount ... save big": "I've completely ran
    the whole thing back ... cut the first take and leave the second one"). find_runback needs a >= 60 s reset and a
    "my bad"; this one needs neither, so it asks for more proof instead. ALL of:
      - a pause / cut >= min_gap s in the kept footage, and the line after it opens the same way as a line he started
        <= look_back s before (its first 7 words, in order, >= 5 of them the same: an opener, not a shared topic word),
      - the earlier try is mid-flow (it never reached a new product: product_starts),
      - >= 3 more content words of the earlier try come back in the 40 words after the re-start (the same part re-done).
    The earlier try is cut from its opener (not the sentence start: "...amazing shipping" before it stays) to the pause."""
    from difflib import SequenceMatcher
    mid = lambda w: (w["s"] + w["e"]) / 2
    kw = [w for w in words if any(a <= mid(w) <= b for a, b in kept)]
    st = [_stem(w["w"]) for w in kw]
    cuts = []
    for g in range(1, len(kw)):
        if kw[g]["s"] - kw[g - 1]["e"] < min_gap:
            continue
        head = [x for x in st[g:g + 7] if x]
        if len(head) < 6:
            continue
        best = None
        for i in range(g - 1, -1, -1):
            if kw[g - 1]["e"] - kw[i]["s"] > look_back:
                break
            win = [x for x in st[i:i + 9] if x]
            m = SequenceMatcher(None, head, win, autojunk=False)
            same = sum(b.size for b in m.get_matching_blocks())
            # >= 4 words IN A ROW, 2+ of them content words: "you do want to pay attention" (6) is a re-start; "But you guys
            # can pretty much" / "But anyways guys, that's pretty much it" (lv trainer) and "here's what the hoodie" /
            # "here's what the pants" (sp5der, a new product) are not (regression replay 2026-10-24)
            run = max(m.get_matching_blocks(), key=lambda b: b.size)
            core = [x for x in head[run.a:run.a + run.size] if x not in STOP]
            if same >= 5 and st[i] == head[0] and run.size >= 4 and len(core) >= 2:
                best = i
        if best is None or any(kw[best]["s"] < p <= kw[g]["s"] for p in product_starts):
            continue
        before = {x for x in st[best + 7:g]} - STOP - {""}
        after = {x for x in st[g + 7:g + 47]} - STOP - {""}
        if len(before & after) < 3:
            continue
        # the re-start's first word may sit just outside the kept footage ("One | thing you do want"): the earlier try's same
        # word goes with it, or a lone "One" is left after "...amazing shipping"
        a = kw[best]["s"]
        raw_prev = [w for w in words if w["e"] <= kw[g]["s"] + 0.01 and kw[g]["s"] - w["s"] < 1.5]
        if best and raw_prev and _stem(raw_prev[-1]["w"]) == st[best - 1] and kw[best]["s"] - kw[best - 1]["e"] < 0.4:
            a = kw[best - 1]["s"]
        cuts.append({"s": a - 0.05, "e": kw[g - 1]["e"] + 0.05, "why": "run-back: re-started after a short reset",
                     "text": " ".join(x["w"] for x in kw[best:best + 16])[:120],
                     "kept": " ".join(x["w"] for x in kw[g:g + 12]) + " ...", "also": sorted(before & after)[:6]})
    return cuts


OPENERS = ("next up", "next method", "our next", "the next", "another way", "first method", "second method", "third method",
           "last method", "next way", "next one")


def find_reopened(words, window=25.0):
    """A section announced twice ("Next up we're gonna go over uber eats" ... "For the next method is going to be to
    use their competition"): ALWAYS cut the first announcement, from its start to the second one (user rule 2026-10-21:
    "obviously you should always cut the first")."""
    n = [norm(w["w"]) for w in words]
    starts = []
    for i in range(len(words) - 1):
        two = n[i] + " " + n[i + 1]
        # an opener begins a sentence: after a full stop or a pause
        new_sent = i == 0 or words[i - 1]["w"][-1:] in ".?!" or words[i]["s"] - words[i - 1]["e"] >= 0.5 or n[i - 1] in ("for", "so", "and")
        if two in OPENERS and new_sent:
            starts.append(i - 1 if i and n[i - 1] in ("for", "so", "and") else i)
    cuts = []
    for a, b in zip(starts, starts[1:]):
        if 2.0 < words[b]["s"] - words[a]["s"] <= window:
            cuts.append({"s": words[a]["s"], "e": words[b]["s"], "why": "section announced twice (cut the first)",
                         "text": " ".join(w["w"] for w in words[a:b]), "kept": " ".join(w["w"] for w in words[b:b + 10]) + " ..."})
    return cuts


def find_intro(words):
    n = [norm(w["w"]) for w in words]
    # "hey guys" (phone / review) or "hello youtube" (gaming intros: "Hello YouTube Hello YouTube welcome back to yet
    # again Hello YouTube welcome back..." kept every try before 2026-10-21)
    hits = [i for i in range(len(words) - 1) if (n[i], n[i + 1]) in (("hey", "guys"), ("hello", "youtube")) and words[i]["s"] < 90]
    if hits and words[hits[-1]]["s"] > 1:
        i = hits[-1]
        return {"s": 0.0, "e": words[i]["s"], "why": "pre-roll / earlier intro takes",
                "text": " ".join(w["w"] for w in words[:i]), "kept": " ".join(w["w"] for w in words[i:i + 8]) + " ..."}


def find_asides(words):
    """A pause-bounded line containing an aside cue."""
    lines, cur = [], [0]
    for i in range(1, len(words)):
        if words[i]["s"] - words[i - 1]["e"] >= 0.5:
            lines.append(cur)
            cur = []
        cur.append(i)
    lines.append(cur)
    out = []
    for ln in lines:
        text = " ".join(words[i]["w"] for i in ln)
        low = text.lower()
        cue = next((c for c in ASIDE_CUES if c in low), None)
        if cue and len(ln) <= 40:
            out.append({"s": words[ln[0]]["s"], "e": words[ln[-1]]["e"] + 0.1, "why": f"aside ('{cue}') REVIEW",
                        "text": text, "kept": ""})
        elif cue:
            # a long "line" (Whisper stretched a word over the pause: "go ahead and ... run that whole thing back"):
            # cut only the SENTENCE holding the cue (Doordash 2026-10-21)
            sent = []
            for i in ln:
                sent.append(i)
                if words[i]["w"][-1:] in ".?!" or i == ln[-1]:
                    st = " ".join(words[j]["w"] for j in sent)
                    # only spoken notes to the editor justify cutting a sentence out of a long line; reactions
                    # ("what the heck") inside a real explanation stay ("what the heck, why would you use Uber Eats")
                    c2 = next((c for c in EDITOR_CUES if c in st.lower()), None)
                    if c2 and len(sent) > 40:
                        # no full stop for 40+ words: from the cue back to the last real pause (word starts >= 1.5 s
                        # apart: Whisper stretches the word before a pause) or 12 words, to the sentence end
                        n0 = len(c2.split())
                        at = next(k for k in range(len(sent)) if c2 in " ".join(words[j]["w"] for j in sent[k:k + n0 + 2]).lower())
                        b = at
                        while b > 0 and at - b < 12 and words[sent[b]]["s"] - words[sent[b - 1]]["s"] < 1.5:
                            b -= 1
                        sent = sent[b:]
                        st = " ".join(words[j]["w"] for j in sent)
                    if c2 and len(sent) <= 40:
                        out.append({"s": words[sent[0]]["s"], "e": words[sent[-1]]["e"] + 0.1, "why": f"aside ('{c2}') REVIEW",
                                    "text": st, "kept": ""})
                    sent = []
    return out


def merge(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1] + 0.05:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


FILLER_SOUNDS = {"um", "umm", "uh", "uhh", "er", "erm", "hmm", "hm"}
FILLER_HEAVY = FILLER_SOUNDS | {"ah", "ahh", "mm"}


def find_fillers(words, level):
    """Filler words by speaker (user 2026-10-22: a friend says um / ya / alright a lot, the user doesn't use "and yeah" as
    filler any more, so one setting for everyone over-cut or under-cut). Levels:
      off   - nothing
      auto  - light or heavy, measured on this video (see below)
      light - the user's own channels: only um / uh / er / hmm sounds on their own
      heavy - talkers who fill: also ah / mm, "and / so / but yeah" bridging two sentences (MacBook one-off rules), and
              "yeah" / "ya" / "alright" said alone between pauses
    Needs a verbatim transcript to find most ums (small.en drops them). Cut edges are snapped to quiet like any content cut."""
    if level == "auto":
        # decided by the video, not by who it is (user 2026-10-23: "we shouldn't be filtering by friend"): heavy when the
        # talker uses the bridging / lone "yeah, alright" fillers often. Measured: friends' videos 2.2-2.8 a minute, the
        # user's own 0-0.06 (apple home lg, appletv2 vs dhgate coupons, Doordash, Shein, Uber)
        mins = max(1.0, (words[-1]["e"] - words[0]["s"]) / 60) if words else 1.0
        rate = (len(find_fillers(words, "heavy")) - len(find_fillers(words, "light"))) / mins
        level = "heavy" if rate >= 0.8 else "light"
        print(f"fillers auto: {rate:.2f} talk fillers a minute -> {level}")
    if level not in ("light", "heavy"):
        return []
    sounds = FILLER_SOUNDS if level == "light" else FILLER_HEAVY
    n = [norm(w["w"]) for w in words]
    gap = lambda i, j: words[j]["s"] - words[i]["e"]   # pause between word i and word j (j = i + 1)
    out = []
    for i, w in enumerate(words):
        nxt_s = min(words[i + 1]["s"], w["e"] + 0.25) if i + 1 < len(words) else w["e"] + 0.1  # a long pause after = the pause trimmer's job
        if n[i] in sounds:
            out.append({"s": w["s"], "e": nxt_s, "why": f"filler '{w['w']}'", "text": w["w"], "kept": ""})
        elif level == "heavy" and n[i] in ("yeah", "ya", "yea") and i and n[i - 1] in ("and", "so", "but") and gap(i - 1, i) < 0.4 \
                and words[i - 1]["w"][-1:] not in ".?!":
            out.append({"s": words[i - 1]["s"], "e": nxt_s, "why": f"filler '{words[i - 1]['w']} {w['w']}'",
                        "text": f"{words[i - 1]['w']} {w['w']}", "kept": ""})
        elif level == "heavy" and (n[i] in ("yeah", "ya", "yea", "alright") or (n[i] == "all" and i + 1 < len(words) and n[i + 1] == "right")):
            last = i + 1 if n[i] == "all" else i
            alone = (i == 0 or gap(i - 1, i) >= 0.3) and (last + 1 >= len(words) or gap(last, last + 1) >= 0.3)
            # "yeah" answering a question or "alright, let's go" opening a section carries meaning: only alone between pauses
            if alone and not (i and words[i - 1]["w"][-1:] == "?"):
                e = min(words[last + 1]["s"], words[last]["e"] + 0.25) if last + 1 < len(words) else words[last]["e"] + 0.1
                out.append({"s": w["s"], "e": e, "why": f"filler '{' '.join(x['w'] for x in words[i:last + 1])}'",
                            "text": " ".join(x["w"] for x in words[i:last + 1]), "kept": ""})
    return out


def main():
    words_path, fps, out_dir = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    words = [w for w in json.load(open(words_path, encoding="utf-8")) if norm(w["w"])]
    duration = float(sys.argv[sys.argv.index("--duration") + 1]) if "--duration" in sys.argv else words[-1]["e"] + 1
    cuts = []
    intro = find_intro(words)
    # the greeting the video opens on ("Hello YouTube" / "Hey guys", last take): guarded at the end, see below
    n_ = [norm(w["w"]) for w in words]
    g_hits = [i for i in range(len(words) - 1) if (n_[i], n_[i + 1]) in (("hey", "guys"), ("hello", "youtube")) and words[i]["s"] < 90]
    greet = (words[g_hits[-1]]["s"], words[g_hits[-1] + 1]["e"]) if g_hits else None
    if not intro and "--audio" in sys.argv and "--no-opening" not in sys.argv:
        # no greeting line: find where the presenter voice starts (louder / higher / faster than the warm-up to the
        # editor before it; Chime 2026-10-23, opening.py)
        try:
            from opening import find_opening
            intro = find_opening(words, sys.argv[sys.argv.index("--audio") + 1])
        except Exception as ex:  # noqa: a non-wav / unreadable track just skips the check
            print(f"opening check skipped ({type(ex).__name__}: {ex})")
    if intro:
        cuts.append(intro)
    cuts += find_restarts(words)
    cuts += find_asides(words)
    cuts += find_stuck(words)
    cuts += find_reopened(words)
    # filler level per speaker: --fillers off|light|heavy, else STUDIO_FILLERS (set by {{STUDIO_NAME}} from the channel /
    # project setting), else light
    level = sys.argv[sys.argv.index("--fillers") + 1] if "--fillers" in sys.argv else os.environ.get("STUDIO_FILLERS", "light")
    cuts += find_fillers(words, level)
    if "--resaid" in sys.argv:  # OFF by default: word overlap over-cut both test videos (Uber 8:34 -> 6:26, real
        cuts += find_resaid(words)  # sections lost). Same-content detection needs meaning, not shared words (TODO).
    if "--audio" in sys.argv and "--no-mutters" not in sys.argv:  # product reviews: try-on talk is quiet on purpose (away mic)
        cuts += find_mutters(words, sys.argv[sys.argv.index("--audio") + 1],
                             sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None, cuts)
    # one-word stutters: "once once", "to to", "this this" -> drop the first one
    n = [norm(w["w"]) for w in words]
    # ...but only a double medium.en hears too. small.en invents doubles: "because shipping is very expensive" came out as
    # "because shipping shipping is", and the stutter cut took "-cause shipp-" out of a clean sentence (dhgate coupons
    # 2026-10-24, draft 3:38 "a weird cut"). Each candidate is re-read once (+-0.6 s) and cached in <out>\stutter_check.json.
    # the out dir may not exist yet on a first run (dhgate watchb spread 2026-10-24: the cache write raised FileNotFoundError,
    # the whole trimmer failed and the draft fell back to the old rules: "so in order | so in order", "starting off" twice)
    os.makedirs(out_dir, exist_ok=True)
    _sc_path = os.path.join(out_dir, "stutter_check.json")
    _sc = json.load(open(_sc_path)) if os.path.exists(_sc_path) else {}
    _sc_model = []

    def stutter_heard(k):
        if "--audio" not in sys.argv:
            return True
        key = f"{words[k]['s']:.2f}|{n[k]}"
        if key not in _sc:
            try:
                import subprocess
                import numpy as np
                a0 = max(0.0, words[k]["s"] - 0.6)
                pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a0:.2f}", "-t", f"{words[k + 1]['e'] + 0.6 - a0:.2f}", "-i",
                                      sys.argv[sys.argv.index("--audio") + 1], "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
                if not _sc_model:
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    from whisper_gpu import load
                    _sc_model.append(load("medium.en")[0])
                segs = _sc_model[0].transcribe(np.frombuffer(pcm, np.int16).astype(np.float32) / 32768, condition_on_previous_text=False,
                                               vad_filter=False, initial_prompt="Um, so, so I I was, uh, the the thing is, like, like this.")[0]
                toks = [norm(t) for sg in segs for t in sg.text.split()]
                _sc[key] = any(a == b == n[k] for a, b in zip(toks, toks[1:]))
            except Exception as e:  # no model / no audio: the old behaviour (trust small.en)
                print(f"stutter check skipped: {e}")
                return True
            json.dump(_sc, open(_sc_path, "w"), indent=0)
        return _sc[key]
    for k in range(len(words) - 1):
        short = all(words[m]["e"] - words[m]["s"] <= 0.45 for m in (k, k + 1))  # "go out OUT" was really "out and cash out"
        across = words[k]["w"][-1:] in ".?!,"  # "do this. This is why" = two sentences, not a stutter
        # ...also when Whisper left out the full stop but capitalised the next sentence: "looking exactly like this This is
        # pretty much where" (Uber codes october 2026-10-25, 7:10: the stutter cut took "this", "it cuts this word off")
        across = across or (words[k]["w"][:1].islower() and words[k + 1]["w"][:1].isupper())
        tiny = len(n[k]) < 2  # "card holder, I I actually": cutting one "I" is a mid-sentence micro-cut (v15 2:57)
        if n[k] == n[k + 1] and n[k] not in OK_DOUBLES and short and not across and not tiny and words[k + 1]["s"] - words[k]["s"] < 1.5:
            if not stutter_heard(k):
                continue
            cuts.append({"s": words[k]["s"], "e": words[k + 1]["s"], "why": "stutter", "text": words[k]["w"], "kept": words[k + 1]["w"]})
    # fixes found by the checker on an earlier draft (feedback_cuts.py)
    prot = []
    if "--extra" in sys.argv and os.path.exists(sys.argv[sys.argv.index("--extra") + 1]):
        notes = json.load(open(sys.argv[sys.argv.index("--extra") + 1]))  # checker fixes must be confirmed in the RAW transcript (feedback_cuts)
        user = [n for n in notes if n["why"].startswith("user note")]
        # the user's own call wins: an auto cut that starts before a user-note cut and ends inside it would
        # remove words the user chose to keep ("you can easily | take advantage of")
        # a note may PROTECT words the user chose to keep ("protect": [s, e]); auto cuts touching them are dropped.
        # (A blanket "drop auto cuts ending inside a note" brought back half a broken take at 2:36, v14 note.)
        prot = [n["protect"] for n in user if "protect" in n]
        # an auto cut that is mostly protected words is dropped; one that only grazes a protect is trimmed around it
        # (Chime 2026-10-23: protecting a 2 s subscribe line dropped the 14-min cut it ended, and an abandoned
        # recording came back). Pieces left under 0.3 s go.
        def around(c, drop_mostly=True):
            hit = [(ps, pe) for ps, pe in prot if c["s"] < pe and c["e"] > ps]
            if not hit:
                return [c]
            if drop_mostly and sum(min(c["e"], pe) - max(c["s"], ps) for ps, pe in hit) >= 0.5 * (c["e"] - c["s"]):
                return []
            out_, t0 = [], c["s"]
            for ps, pe in sorted(hit):
                if ps - t0 >= 0.3:
                    out_.append(dict(c, s=t0, e=ps))
                t0 = max(t0, pe)
            if c["e"] - t0 >= 0.3:
                out_.append(dict(c, s=t0))
            return out_
        cuts = [p for c in cuts for p in around(c)]
        # take-review cuts are trimmed off a protected range instead of dropped (Shein 0:55: the review cut started
        # inside "below" and the protect note did not reach it), also when the protect sits inside the cut (Chime:
        # "If you're just a guy" inside an "abandoned fragment" review cut)
        notes = [p for c in notes for p in (around(c, drop_mostly=False) if "(take review)" in c["why"] else [c])]
        cuts += [dict(c, text=c["why"], kept="") for c in notes if c["e"] > c["s"] or "protect" in c]
    cuts += drop_orphans(words, cuts)
    # silences (user rule 2026-10-20: "let's not cut in between sentences", trims inside sentences felt snappy
    # and clipped words): between sentences a pause > 0.4 s shrinks to ~0.3 s; inside a sentence only a real stall
    # (>= 1.0 s) is trimmed, down to ~0.4 s. A gap >= 0.7 s counts as a sentence break (Whisper punctuation is unreliable).
    # pause style: --pauses natural|tight, else STUDIO_PAUSES ({{STUDIO_NAME}} settings.pauses), else natural.
    # tight = the jump-cut style of a friend's editor (Chime upload 2026-10-23, XzavierYT q_BtUmTQ_bw: same words at 1.00x
    # speed, 230 wpm vs our 200, only 29 gaps > 0.25 s in 9:14 vs our 88): every measured pause >= 0.2 s, between or
    # inside sentences, closes to ~0.1 s of air. Those trims are applied LAST, on the finished keep list (tight_holes
    # below): as ordinary cuts they split sentences into short pieces that the scrap / false-start rules then deleted
    # ("As somebody who made", "payroll tax, employment tax" went missing). The user's own channels stay natural.
    pauses = sys.argv[sys.argv.index("--pauses") + 1] if "--pauses" in sys.argv else os.environ.get("STUDIO_PAUSES", "natural")
    tight = pauses == "tight"
    tight_holes = []
    gaps = []
    for a, b in zip(words, words[1:]):
        gap = b["s"] - a["e"]
        boundary = a["w"][-1:] in ".?!" or gap >= 0.7
        if boundary and gap > 0.4:
            gaps.append((a["e"], b["s"], 0.15))
        elif not boundary and gap >= 1.0:
            gaps.append((a["e"], b["s"], 0.2))
    for a_e, b_s, keep_air in gaps:
        cuts.append({"s": a_e + keep_air, "e": b_s - keep_air, "why": "silence" + (" (LONG: phone demo?)" if b_s - a_e > 5 else ""),
                     "text": f"{b_s - a_e:.1f} s pause", "kept": "", "air": keep_air})
    # Whisper stretches word timings over pauses, so also measure real silence in the audio itself
    if "--audio" in sys.argv:
        import subprocess
        err = subprocess.run(["ffmpeg", "-v", "info", "-i", sys.argv[sys.argv.index("--audio") + 1],
                              "-af", "silencedetect=n=-42dB:d=0.45", "-f", "null", "-"],
                             capture_output=True, text=True, errors="replace").stderr
        for a, b in re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", err, re.S):
            a, b = float(a), float(b)
            long_stall = b - a >= 1.0  # a measured 1 s+ silence is a stall even if Whisper's word timings span it
            if not long_stall and not any(ga - 0.3 <= a and b <= gb + 0.3 for ga, gb, _ in gaps):
                continue  # short pause mid-sentence: leave it alone
            cuts.append({"s": a + 0.12, "e": b - 0.12, "why": "silence" + (" (LONG: phone demo?)" if b - a > 5 else ""),
                         "text": f"{b - a:.1f} s measured silence", "kept": "", "air": 0.2})
        if tight:
            err = subprocess.run(["ffmpeg", "-v", "info", "-i", sys.argv[sys.argv.index("--audio") + 1],
                                  "-af", "silencedetect=n=-40dB:d=0.2", "-f", "null", "-"],
                                 capture_output=True, text=True, errors="replace").stderr
            tight_holes = [(float(a) + 0.05, float(b) - 0.05)
                           for a, b in re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", err, re.S)]
        # dead air ABOVE -42 dB: a noisy room / mumbles under the breath sit at -35..-45 dB, so silencedetect misses them
        # and Whisper stretches one word over it (dhgate coupons 2026-10-22: "for" stamped 297.1-306.3, 9 s of nothing
        # in the draft). Any 1.5 s+ stretch with no sustained sound within 16 dB of the talking level is a stall.
        import numpy as np
        _raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[sys.argv.index("--audio") + 1], "-ac", "1", "-ar", "16000",
                               "-f", "s16le", "-"], capture_output=True).stdout
        _a = np.frombuffer(_raw, np.int16).astype(np.float32) / 32768
        _env = 20 * np.log10(np.sqrt(np.convolve(_a ** 2, np.ones(160) / 160, "same"))[::160] + 1e-9)   # 10 ms
        _talk = float(np.percentile(_env[_env > -45], 90)) if (_env > -45).any() else -15.0
        _sp = np.convolve((_env > _talk - 16).astype(int), np.ones(10, int), "same") >= 7   # sustained 100 ms
        _i, _n = 0, len(_sp)
        while _i < _n:
            if _sp[_i]:
                _i += 1
                continue
            _j = _i
            while _j < _n and not _sp[_j]:
                _j += 1
            a, b = _i / 100, _j / 100
            if b - a >= 1.5 and a > 0.5 and b < duration - 0.5:
                cuts.append({"s": a + 0.2, "e": b - 0.15, "why": "silence" + (" (LONG: phone demo?)" if b - a > 5 else ""),
                             "text": f"{b - a:.1f} s dead air (under {_talk - 16:.0f} dB)", "kept": "", "air": 0.2})
            _i = _j
    # the tail starts after the last real SOUND, not the last word Whisper wrote: a quick "Bye!" right after the sign-off is
    # often not transcribed (dhgate watchb spread 2026-10-24, 19:41.5: "the word bye wasn't protected there ... it's just
    # gone"; the tail cut began 0.5 s after "one-to-one"). Never cut the sign-off (playbook).
    tail = words[-1]["e"] + 0.5
    # ...but when the last word IS the sign-off ("Bye!"), it ends there: 1.3 s of air for the closing fade, never the mic
    # handling after it (Uber codes october 2026-10-25: 2 s of him reaching for the mic after "Bye", "there's still dead
    # space after the word bye", the fade ran over it)
    signoff = re.sub(r"[^a-z]", "", words[-1]["w"].lower()) in ("bye", "byebye", "peace", "later", "deuces")
    if signoff:
        tail = words[-1]["e"] + 1.3
    if "_sp" in dir() and not signoff:
        k0, k1 = int(words[-1]["e"] * 100), min(len(_sp), int((words[-1]["e"] + 2.5) * 100))
        snd = [k for k in range(k0, k1) if _sp[k]]
        if snd:
            tail = max(tail, snd[-1] / 100 + 0.4)
    cuts.append({"s": tail, "e": duration, "why": "tail", "text": "", "kept": ""})
    tail_at = tail   # (the join pass below reuses the name "tail")
    # a retake only wins when the later take is really there: one muttered away from the mic is dead air and gets cut too,
    # and both tries were gone (dhgate watchb spread 2026-10-24, 3:10: "...tap in with the Pateks before | There's also";
    # the far "Before they're all" was the retake: "you can literally hear the microphone ... like I was talking to myself")
    dead = [(x["s"], x["e"]) for x in cuts if x["why"].startswith("silence") and "dead air" in x.get("text", "")]
    def _muttered(c):
        # measured on the mic, not on Whisper's word times: in the coupons video he reads codes slowly ("D... H... twenty
        # twenty four") and Whisper stretched those words over pauses that the dead-air pass cut, so a normal-volume
        # retake looked "muttered" (other session, 2026-10-24: 3 approved retakes flipped, 4:13 -> 5:43). Off-mic = the
        # later try's loudest part sits 12 dB+ under his talking level.
        if "_env" not in dir() and "_env" not in globals():
            return False
        # only a SHORT redo (<= 20 s cut): the coupons "retakes" were whole 60 s code sections
        nxt = [w for w in words if c["e"] - 0.05 <= w["s"] < c["e"] + 3.0][:4]
        if not nxt or not dead or c["e"] - c["s"] > 20.0:
            return False
        # the LOUDEST moment of the later try (to 1 s past its 4th word; Whisper stretches words over pauses)
        a0, b0 = int(c["e"] * 100), int((nxt[-1]["e"] + 1.0) * 100)
        seg = _env[a0:max(b0, a0 + 1)]
        return len(seg) > 0 and float(np.percentile(seg, 98)) < _talk - 12

    for c in [c for c in cuts if c["why"] == "retake" and _muttered(c)]:
        cuts.remove(c)
        print(f"retake kept: the later try after {fmt(c['s'])} \"{c['text'][:40]}\" is muttered off-mic (dead air), the first take stays")

    # move every content-cut edge to the quietest 10 ms of real audio near the word boundary: Whisper's word
    # starts are a little off at seams, which either left a stray "for" or clipped "Hey" / "In" / "when"
    if "--audio" in sys.argv:
        import subprocess
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[sys.argv.index("--audio") + 1], "-ac", "1", "-ar", "16000",
                              "-f", "s16le", "-"], capture_output=True).stdout
        aud = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        env = np.sqrt(np.convolve(aud ** 2, np.ones(160) / 160, "same"))[::160]  # 10 ms RMS

        floor = float(np.percentile(env, 15))
        thr = max(floor * 3, 10 ** (-45 / 20))  # "quiet" = within ~10 dB of the room's noise floor (about -62 dB here)

        def first_quiet(t, lo, hi):   # cut START: first quiet 10 ms at/after the last kept word
            for k in range(max(0, int((t + lo) * 100)), min(len(env), int((t + hi) * 100))):
                if env[k] < thr:
                    return k / 100
            a, b = max(0, int((t + lo) * 100)), min(len(env), int((t + hi) * 100))
            return (a + int(np.argmin(env[a:b]))) / 100 if b > a else t  # words run together: quietest dip

        def last_quiet(t, lo, hi):    # cut END: last quiet 10 ms before the next kept word
            for k in range(min(len(env) - 1, int((t + hi) * 100)), max(0, int((t + lo) * 100)), -1):
                if env[k] < thr:
                    return k / 100
            a, b = max(0, int((t + lo) * 100)), min(len(env), int((t + hi) * 100))
            return (a + int(np.argmin(env[a:b]))) / 100 if b > a else t
        for c in cuts:
            if c["why"].startswith("tail"):
                continue
            if c["why"].startswith("silence"):
                # pause trims: from the first quiet moment to the last one (taps/clicks inside get removed too),
                # keeping 70 ms of air next to each word
                a0, b0 = int(c["s"] * 100), int(c["e"] * 100)
                # only real quiet counts: runs of >= 80 ms (a 10 ms dip inside muttering is not a pause)
                qm = env[a0:b0] < thr
                runs_ = np.convolve(qm.astype(int), np.ones(8, int), "valid") == 8
                q = np.where(runs_)[0]
                q = np.concatenate([q, q[-1:] + 7]) if len(q) else q
                if len(q):
                    air = c.get("air", 0.15) - 0.05
                    c["s"], c["e"] = (a0 + q[0]) / 100 + air, (a0 + q[-1]) / 100 - air
                else:
                    c["e"] = c["s"]
            elif c["why"].startswith("filler"):
                # a filler sits inside running speech: both edges on the quietest 10 ms next to it (MacBook one-off rule);
                # "last quiet before" walked back past the filler and left nothing to cut
                dip_ = lambda lo, hi: (max(0, int(lo * 100)) + int(np.argmin(env[max(0, int(lo * 100)):int(hi * 100) + 1]))) / 100
                c["s"], c["e"] = dip_(c["s"] - 0.08, c["s"] + 0.04), dip_(c["e"] - 0.06, c["e"] + 0.08)
            elif c["why"].startswith("user note"):
                pass  # the user's own cut points are exact: no snapping (it pulled "take advantage | of" back to a dip)
            else:
                # a kept word Whisper stretched over a pause (> 0.6 s) really starts near its END: end the cut there, or
                # whatever was said in the pause leaks in ("wild | Cool. So we made it", user note 2026-10-20, Realms 2:15)
                kw = next((w for w in words if abs(w["s"] - c["e"]) < 0.02), None)
                if kw and kw["e"] - kw["s"] > 0.6:
                    c["e"] = kw["e"] - 0.35
                # content cuts: never start or end on sound ("promotion|s" was clipped, user note 2026-10-20)
                s0 = c["s"]
                c["s"], c["e"] = last_quiet(c["s"], -0.3, 0.03), last_quiet(c["e"], -0.45, 0.03)  # quiet BEFORE the first removed word and BEFORE the first kept word
                # ...never INSIDE the last kept word: when Whisper writes the removed word late, that quiet sits before
                # the kept word's middle and the cut took the kept word (Uber codes october 2026-10-25, 7:10: "page looking
                # like | ...", the "this" was gone: "like this. This is pretty much" with only a 40 ms gap before "This").
                # Then the first quiet after the kept word's end wins (up to 0.15 s past where the removed word was written)
                pw = next((w for w in reversed(words) if w["s"] < s0 - 0.05 and w["e"] <= s0 + 0.02), None)
                # (only a word Whisper timed as a real word, >= 0.15 s: squeezed 40 ms words are its guesses, not timing)
                if pw and pw["e"] - pw["s"] >= 0.15 and c["s"] < (pw["s"] + pw["e"]) / 2:
                    fwd = [k for k in range(int(pw["e"] * 100), min(len(env), int((s0 + 0.15) * 100))) if env[k] < thr]
                    if fwd:
                        c["s"] = fwd[0] / 100
    snap = lambda t: round(t * fps) / fps
    removed = merge([[snap(c["s"]), snap(c["e"])] for c in cuts if c["e"] > c["s"]])
    keep, t = [], 0.0
    for s, e in removed:
        if s > t:
            keep.append([round(t, 4), round(s, 4)])
        t = max(t, e)
    if t < duration:
        keep.append([round(t, 4), round(snap(duration), 4)])
    # a kept piece with no words in it is just tapping/breath between two cut lines: drop it
    # (a word counts by its MIDDLE: one starting right on the edge belongs to the cut after it, "Pizza," 2026-10-21)
    inside = lambda k, w: k[0] - 0.05 <= (w["s"] + w["e"]) / 2 < k[1]
    keep = [k for k in keep if k[1] - k[0] >= 0.15 and any(inside(k, w) for w in words)]
    # a scrap under 1.2 s with < 3 words between two cuts is never a real line (lone "So" at v13 0:27, heard as "okay")
    keep = [k for k in keep if k[1] - k[0] >= 1.2 or sum(1 for w in words if inside(k, w)) >= 3]
    # a <= 3-word scrap repeated in the next kept piece's opening words is a false start: "So once | once you were on the
    # app", "you're signed up | your signed up? All you..." played as stutters (Doordash 2026-10-21)
    kw = lambda k: [norm(w["w"]) for w in words if inside(k, w)]
    def false_start(i):
        a = kw(keep[i])
        b = kw(keep[i + 1])[:4] if i + 1 < len(keep) else []
        # distinct words: "payroll tax, employment tax," | "business tax..." matched "tax" twice (Chime 2026-10-23)
        return (0 < len(a) <= 4 and (a[-1:] == b[:1] or sum(1 for t in set(a) if t in b and len(t) > 1) >= min(2, len(set(a))))) or \
            (0 < len(a) <= 6 and len(b) >= 2 and a[:2] == b[:2])  # "Next up is going to be | Next up we're gonna..."
    keep = [k for i, k in enumerate(keep) if not false_start(i)]
    # ...and a scrap whose words come back in ANY kept piece of the next 45 s, not just the next one: he tries a line a few
    # times with other scraps in between (dhgate watchb spread 2026-10-24, 11:36: "Rolex Datejust | here is a watch | Rolex
    # Datejust especially the celebration one"; 12:45: "let's move on to Iced Out | Edition | I want to talk about Iced Out
    # watches | Let's talk about Iced Out watches": "I was trying to say Datejust a few times, it didn't work ... cut out
    # bad takes like that"). The scrap is <= 8 words / 4 s and every content word of it is in that later opening.
    def tried_again(i):
        k = keep[i]
        a = {_stem(t) for t in kw(k)} - STOP - {""}
        if not a or len(kw(k)) > 8 or k[1] - k[0] > 4.0:
            return False
        for j in range(i + 1, len(keep)):
            if keep[j][0] - k[1] > 45:
                break
            if a <= {_stem(t) for t in kw(keep[j])[:20]}:
                return True
        return False
    drop = [i for i in range(len(keep) - 1) if tried_again(i)]
    for i in drop:
        print(f"scrap dropped (said again within 45 s): {fmt(keep[i][0])} \"{' '.join(kw(keep[i]))}\"")
    keep = [k for i, k in enumerate(keep) if i not in drop]
    # a piece that opens on the TAIL of a sentence whose start was cut ("...best case | scenario. I just want to show you")
    # starts at the next sentence instead (Doordash 2026-10-21)
    for i, k in enumerate(keep):
        ins = [w for w in words if inside(k, w)]
        prev = [w for w in words if (w["s"] + w["e"]) / 2 < k[0] - 0.05]
        if i and ins and prev and prev[-1]["w"][-1:] not in ".?!" and ins[0]["w"][:1].islower():
            # only a 1-2 word stray tail; "to my cart. This will..." after a stuck-line cut is a real line
            end = next((j for j in range(min(2, len(ins) - 1)) if ins[j]["w"][-1:] in ".?!"), None)
            if end is not None:
                # start in the GAP after the full stop (inside the word, the edge repair pulled it back: "case scenario.")
                k[0] = round(snap(max(k[0], ins[end]["e"], ins[end + 1]["s"] - 0.15)), 4)
            else:
                # the opposite case: the kept take lost its OPENING words ("[For next code is] going to be 20 Garcia",
                # "[for last code is] going to be us to 4j2", Shein 2026-10-21). Walk back <= 8 words to a section opener
                # said without a pause, and start there.
                back = prev[-8:]
                toks = [norm(w["w"]) for w in back]
                for j in range(len(back)):
                    seq = tuple(toks[j:j + 4])
                    if any(seq[:len(o)] == o for o in TAKE_OPENERS) and all(
                            back[m + 1]["s"] - back[m]["e"] < 1.2 for m in range(j, len(back) - 1)) and ins[0]["s"] - back[-1]["e"] < 1.2:
                        lo = max(back[j]["s"] - 0.12, keep[i - 1][1] + 0.05)
                        k[0] = round(snap(lo), 4)
                        break
    # overlapping cut rules can leave an edge INSIDE a kept word ("In|order"): move it ONCE to that word's boundary
    # (looping over every word cascaded: "go | Once | you" all got pulled in, user note 2026-10-20)
    def dip(lo, hi):
        if "--audio" not in sys.argv:
            return (lo + hi) / 2
        a_, b_ = max(0, int(lo * 100)), min(len(env), int(hi * 100) + 1)
        return (a_ + int(np.argmin(env[a_:b_]))) / 100 if b_ > a_ else lo
    user_edges = [t for c in cuts if c["why"].startswith("user note") for t in (snap(c["s"]), snap(c["e"]))]
    for k in keep:
        if any(abs(k[0] - t) < 0.05 for t in user_edges) or any(abs(k[1] - t) < 0.05 for t in user_edges):
            continue  # the user said exactly where to cut: leave it
        # (an edge at the very end of the file has no audio after it: empty slice = not loud)
        loud = lambda t: "--audio" in sys.argv and env[max(0, int(t * 100) - 1):int(t * 100) + 2].size > 0 and \
            float(np.max(env[max(0, int(t * 100) - 1):int(t * 100) + 2])) > thr * 4
        # only when the edge really sits on sound: Whisper stretches words over silences ("just" across a 2.3 s stall)
        w0 = next((w for w in words if w["s"] + 0.1 < k[0] < w["e"] - 0.03), None) if loud(k[0]) else None
        if w0:
            k[0] = round(snap(dip(w0["s"] - 0.15, w0["s"] + 0.05)), 4)
        w1 = next((w for w in words if w["s"] + 0.1 < k[1] < w["e"] - 0.1 and (k[1] - w["s"]) > (w["e"] - k[1])), None) if loud(k[1]) else None
        if w1:
            k[1] = round(snap(dip(w1["e"] - 0.1, w1["e"] + 0.15)), 4)
    # tighten every seam: a kept piece ends ~0.15 s after its LAST real word and starts ~0.15 s before its FIRST one.
    # Anything else at a seam is an untranscribed "uh" (heard as "okay", v11 6:27) or a held pause (v11 kept ~9 s of
    # these at seams). User-note edges are left alone.
    if "--audio" in sys.argv:
        for k in keep:
            a_, b_ = int(k[0] * 100), int(k[1] * 100)
            loud_idx = np.where(env[a_:b_] > thr)[0]
            # ignore single 10 ms ticks: real sound = 3+ loud frames in a 50 ms window
            if len(loud_idx):
                dense = [i for i in loud_idx if np.sum((loud_idx >= i) & (loud_idx < i + 5)) >= 3]
                if dense:
                    first_loud, last_loud = (a_ + dense[0]) / 100, (a_ + dense[-1] + 4) / 100
                    if not any(abs(k[0] - t) < 0.05 for t in user_edges):
                        k[0] = round(snap(max(k[0], first_loud - 0.15)), 4)
                    if not any(abs(k[1] - t) < 0.05 for t in user_edges):
                        k[1] = round(snap(min(k[1], last_loud + 0.15)), 4)
        # scrap at a join (user 2026-10-21, Doordash v2): a piece must not open on the fading tail of a cut word (2:15 "to"
        # tail before "head over") or on a short burst the transcript never caught ("wait, whoa, hold on" heard as
        # "hello", then a pause, then the real line at 8:14). If a piece opens with a burst < 0.9 s, then >= 0.35 s of
        # quiet, and that burst holds <= 2 words / only fillers, start at the real speech. Applies to user-note edges too.
        FILL = {"so", "okay", "ok", "um", "uh", "oh", "wait", "whoa", "hello", "hmm", "alright", "yeah", "and", "to", "the"}
        for i, k in enumerate(keep):
            # the FIRST piece too, but only for a burst with NO words in it (Uber codes october 2026-10-25: 1.3 s of him
            # setting up the mic, then "Hey guys": "it's just blank space ... me literally setting up my mic")
            first = i == 0
            a_, lim = int(k[0] * 100), min(int(k[1] * 100), int(k[0] * 100) + 250)  # 2.5 s: the pause after the scrap can be long
            # (the opening: mic handling fades out around -45 dB, the room floor, so "quiet" there is 6 dB higher)
            loud = env[a_:lim] > (thr * 2 if first else thr)
            if not loud.any():
                continue
            # the first real pause (>= 0.35 s) that starts within the opening 0.9 s; a fading tail = a burst < 0.2 s
            # followed by any quiet
            pauses, r = [], 0
            while r < len(loud):
                if not loud[r]:
                    s_ = r
                    while r < len(loud) and not loud[r]:
                        r += 1
                    if r < len(loud) and s_ > 0:
                        pauses.append((s_, r))
                else:
                    r += 1
            # a real pause first ("wait, whoa, hold on" has a 30 ms dip inside it), else a fading tail
            real = [(s_, r_) for s_, r_ in pauses if r_ - s_ >= 35 and s_ < (200 if first else 90)]
            tail = [] if first else [(s_, r_) for s_, r_ in pauses if r_ - s_ >= 3 and s_ < 20]
            if not (real or tail):
                continue
            q0, q1 = (real or tail)[0]
            burst = q0 / 100
            inside = [norm(w["w"]) for w in words if k[0] - 0.05 <= (w["s"] + w["e"]) / 2 < k[0] + burst + 0.05]
            if first and (inside or any(abs(k[0] - t) < 0.05 for t in user_edges)):
                continue
            if len(inside) <= 2 or all(t in FILL for t in inside):
                # walk back from where it gets loud to where the (soft) next word really begins: a quiet "The" before
                # "only downside" stayed under the threshold
                on = a_ + q1
                while on > a_ + q0 and env[on - 1] > (thr * 2 if first else thr / 3):
                    on -= 1
                k[0] = round(snap(on / 100 - 0.1), 4)
        # sign-off: the last piece runs to the end of the last sound within 3 s ("Bye." after "...shift free reviews" was
        # never transcribed and got trimmed as noise, user 2026-10-21)
        # a transcribed "Bye" already ends the video (tail above), unless the last piece stops INSIDE that word: Top 10 Servers
        # (2026-10-26 regression replay): the sections end (4145.03) fell inside "bye" (4144.45-4145.31) and its audible end
        # (4145.10-4145.28) was cut, "...for Shift3MC by-". Then it still runs through the bye's sound, never past the tail.
        if keep and (not signoff or keep[-1][1] < words[-1]["e"]):
            k = keep[-1]
            b_ = int(k[1] * 100)
            seg = env[b_:b_ + 300] > thr
            # the FIRST burst after the end (the "bye"), up to the next 0.3 s of quiet; not every noise in 3 s (reaching
            # for the camera after it)
            st = next((i for i in range(len(seg) - 4) if seg[i:i + 5].sum() >= 3), None)
            if st is not None:
                en = st
                while en < len(seg) and seg[en:en + 30].any():
                    en += 1
                k[1] = round(snap(min(duration, tail_at if signoff else duration, (b_ + en) / 100 + 0.35)), 4)
    # the greeting is the creator's intro and always plays in full: no edge rule may start a piece inside it (Top 10
    # Servers 2026-10-22: the draft opened on "...Tube, welcome back"; "hello" is in the scrap FILL list above and the
    # piece started in the 10 ms dip between "Hello" and "YouTube"). Whisper's start can be early or late: start 0.25 s
    # before it, never inside the previous piece.
    if greet:
        for i, k in enumerate(keep):
            if greet[0] - 0.3 < k[0] < greet[1] and k[1] > greet[1]:
                lo = keep[i - 1][1] + 0.05 if i else 0.0
                k[0] = round(snap(max(lo, greet[0] - 0.25)), 4)
                break
    # edge moves can make neighbours overlap (682-685.5 vs 684.9-705.6 would play a moment twice): merge them
    keep.sort()
    merged = []
    for k in keep:
        if merged and k[0] <= merged[-1][1] + 0.02:
            merged[-1][1] = max(merged[-1][1], k[1])
        else:
            merged.append(list(k))
    keep = merged
    # dead air at a join (dhgate coupons 2026-10-22, 0:48: ~1 s of nothing between "dive right into this" and "In order to"):
    # the seam tightening above counts anything over -45 dB as sound, so breaths / room tone at both edges stayed, and it
    # skips take-review edges as if the user had set them. Here SPEECH = 100 ms+ within 20 dB of the talking level (single
    # clicks / breaths before "In order" were -28 dB blips, talking is ~-12 dB on 10 ms frames); when the quiet
    # either side of a join adds up to more than 0.5 s, the join keeps 0.2 s after the last word and 0.15 s before the next.
    # Only the user's own notes (not the take review) keep their exact edges.
    if "--audio" in sys.argv and len(keep) > 1:
        env_db = 20 * np.log10(env + 1e-9)
        talk_lvl = float(np.percentile(env_db[env_db > -45], 90)) if (env_db > -45).any() else -15.0
        sp = 10 ** ((talk_lvl - 20) / 20)
        exact = [t for c in cuts if c["why"].startswith("user note") and "take review" not in c["why"] for t in (snap(c["s"]), snap(c["e"]))]
        mine = lambda t: any(abs(t - u) < 0.05 for u in exact)

        def speech(a_, b_):   # 10 ms frames inside sustained speech: 7+ loud frames in the 100 ms around them
            seg = env[a_:b_] > sp
            if not seg.any():
                return []
            dense = np.convolve(seg.astype(int), np.ones(10, int), "same") >= 7
            return np.where(dense & seg)[0]
        tight = 0
        # tight pause style: ~0.1 s at a join (0.06 after the last word, 0.05 before the next), like the pauses inside
        a_after, a_before, slack = (0.06, 0.05, 0.15) if pauses == "tight" else (0.2, 0.15, 0.5)
        for i in range(1, len(keep)):
            pk, nk = keep[i - 1], keep[i]
            pa, pb, na, nb = int(pk[0] * 100), int(pk[1] * 100), int(nk[0] * 100), int(nk[1] * 100)
            ps, ns = speech(pa, pb), speech(na, nb)
            if not len(ps) or not len(ns):
                continue
            last_sp, first_sp = (pa + ps[-1] + 3) / 100, (na + ns[0] - 3) / 100   # the 100 ms window sits ~30 ms inside the word
            # a breath / sigh / mouse noise after the piece's LAST word is not speech even when it is within 20 dB of the
            # talking level (dhgate coupons 2026-10-24, draft 2:36: "...than buying in bulk." then 1.4 s of -27..-40 dB
            # breath held the join open, "just a blank space"). Past the last transcribed word, only sound within 8 dB of
            # that word's own level counts; the end then sits on the quietest 10 ms 0.12-0.4 s after the word.
            lw = [w for w in words if pk[0] <= (w["s"] + w["e"]) / 2 < pk[1]]
            if lw and not mine(pk[1]) and last_sp > lw[-1]["e"] + 0.35:
                we = lw[-1]["e"]
                wl = float(np.percentile(env_db[max(pa, int(lw[-1]["s"] * 100)):int(we * 100) + 1], 90))
                tail = env_db[int(we * 100) + 10:pb]
                loud_t = np.convolve((tail > wl - 8).astype(int), np.ones(10, int), "same") >= 7
                if not loud_t.any():
                    lo_, hi_ = int((we + 0.12) * 100), int((we + 0.4) * 100)
                    last_sp = (lo_ + int(np.argmin(env[lo_:hi_]))) / 100 - a_after
            if (pk[1] - last_sp) + (first_sp - nk[0]) <= slack:
                continue
            if not mine(pk[1]) and pk[1] - last_sp > a_after:
                pk[1] = round(snap(last_sp + a_after), 4)
            if not mine(nk[0]) and first_sp - nk[0] > a_before:
                nk[0] = round(snap(first_sp - a_before), 4)
            tight += 1
        print(f"join air: {tight} joins tightened to <= 0.35 s of quiet (speech = within 20 dB of {talk_lvl:.0f} dB)")
    if tight_holes:
        # tight pauses (see "pause style" above): every measured pause inside a finished piece closes to ~0.1 s
        # holes closer than 0.3 s merge (a click between two quiet runs left 0.1 s slivers of room tone as pieces)
        holes = []
        for h in sorted(tight_holes):
            if holes and h[0] - holes[-1][1] < 0.3:
                holes[-1] = (holes[-1][0], max(holes[-1][1], h[1]))
            else:
                holes.append(h)
        split, n_h, saved = [], 0, 0.0
        for s0, e0 in keep:
            t0 = s0
            for hs, he in (h for h in holes if s0 + 0.1 <= h[0] and h[1] <= e0 - 0.1):
                hs, he = snap(hs), snap(he)
                if he - hs < 1 / fps or hs <= t0:
                    continue
                split.append([round(t0, 4), round(hs, 4)])
                t0 = he
                n_h += 1
                saved += he - hs
            split.append([round(t0, 4), round(e0, 4)])
        keep = [k for k in split if k[1] - k[0] >= 0.3 or any(k[0] <= (w["s"] + w["e"]) / 2 < k[1] for w in words)]
        print(f"tight pauses: {n_h} pauses closed inside pieces ({saved:.1f} s)")
    kept_len = sum(e - s for s, e in keep)
    clipped = []
    if "--audio" in sys.argv:
        for s0, e0 in keep:
            for t, side in ((s0, "start"), (e0, "end")):
                k = int(t * 100)
                lvl = float(np.max(env[max(0, k - 1):k + 2])) if env[max(0, k - 1):k + 2].size else 0  # +-10 ms
                if lvl > thr * 4 and 0.5 < t < duration - 0.5:
                    clipped.append((round(t, 2), side, round(20 * np.log10(lvl + 1e-9), 1)))
        print(f"seam check: {len(keep) * 2} cut edges, {len(clipped)} land on sound (possible clipped word)")
        for c in clipped[:15]:
            print("   CLIPPED?", c)

    # a user PROTECT is a promise, whatever the heuristics above did: put back any part of it that ended up cut
    # (Top 10 Servers round 2: "which is going to" was protected but the opens-mid-sentence rule moved the piece's
    # start past it, so #9 played "...number 9 spot. Be River SMP")
    if prot:
        def minus(segs, holes):
            for hs, he in holes:
                segs = [x for a_, b_ in segs for x in ([a_, min(b_, hs)], [max(a_, he), b_]) if x[1] - x[0] > 0.05]
            return segs
        user_cuts = [(c["s"], c["e"]) for c in cuts if c.get("why", "").startswith("user note") and c["e"] > c["s"]]
        # a protect promises WORDS, not the pauses between them: measured silences stay cut (Chime 2026-10-23: the
        # referral-pitch protect brought back a 5.3 s dead pause after "I'll get a free $100 too.")
        user_cuts += [(c["s"], c["e"]) for c in cuts if c.get("why", "").startswith("silence") and c["e"] - c["s"] >= 0.1]
        user_cuts += [h for h in tight_holes if h[1] - h[0] >= 0.1]
        back = []
        for ps, pe in prot:   # only the parts nothing kept and no user CUT note removed on purpose
            for a_, b_ in minus(minus([[ps, pe]], [tuple(k) for k in keep]), user_cuts):
                if b_ - a_ >= 0.3:
                    back.append([round(snap(a_), 4), round(snap(b_), 4)])
        if back:
            merged = []
            for k in sorted([list(k) for k in keep] + back):
                if merged and k[0] <= merged[-1][1] + 0.05:
                    merged[-1][1] = max(merged[-1][1], k[1])
                else:
                    merged.append(k)
            keep = merged
            kept_len = sum(e - s for s, e in keep)
            print(f"protect notes restored: {len(back)} range(s) the automatic rules had cut")
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"fps": fps, "keep": keep, "cuts": sorted(cuts, key=lambda c: c["s"])},
              open(os.path.join(out_dir, "cuts.json"), "w", encoding="utf-8"), indent=1)
    lines = [f"# Cut list", "", f"{fmt(duration)} raw -> {fmt(kept_len)} kept, {len(keep)} pieces", "",
             "| raw time | reason | cut words | next kept words |", "|---|---|---|---|"]
    for c in sorted(cuts, key=lambda c: c["s"]):
        if c["why"] == "silence":
            continue
        lines.append(f"| {fmt(c['s'])}-{fmt(c['e'])} | {c['why']} | {c['text'][:220]} | {c['kept'][:80]} |")
    open(os.path.join(out_dir, "cuts.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{fmt(duration)} -> {fmt(kept_len)} ({len(keep)} pieces); "
          f"{sum(c['why'] == 'retake' for c in cuts)} retakes, {sum('aside' in c['why'] for c in cuts)} asides, {sum(c['why'].startswith('filler') for c in cuts)} fillers ({level})")


if __name__ == "__main__":
    main()
