"""Join cleanup: the last pass over the kept clips, after every other cut guard (ultimate dhgate free reselling spreadsheet
round 2, 2026-10-23). Each rule looks at one join (the end of clip i, the start of clip i+1) the way an editor listens to it.

  redo   - B: the end of clip i is a start he abandoned and says again at the start of clip i+1 ("but trust me guys, it |
           but you can trust me when I say", 5:22; "you're looking to get some | you're looking to get some one-to-one
           sneakers", 8:46, the quiet "farther from the mic" tail; "in terms of where to resell cologne ... checking out |
           in terms of where to resell cologne ... Etsy", 11:11): the abandoned words go (the whole clip when all of it is
           redone).
           A: the CUT between them holds a retake of clip i's last words that goes on to finish the sentence ("these are going
           to be roughly | [as you see these are going to be roughly about ninety two dollars] | but it is worth", 7:28: the
           price was cut out): clip i stops before its try, clip i+1 opens on the retake.
           R: a 1-2 word false start at the clip end that the next clip opens with, after a conjunction or cut mid-word
           ("...a wide range of people and again, | Again, I do want to remind you", 9:20): the clip ends before it.
  conj   - "and | and" / "and | in" at a join sounds like a doubled "and" (2:41): the first one goes.
  dangle - a clip never ends on a function word ("I also want a green as | ...", 4:34; "talk to | them", 9:20 where "them"
           was clipped): the one word that completes it comes back, up to the next measured quiet.
  stub   - a clip never opens or closes mid-sound on the sliver of a word it cut ("...reselling one. | -ese | I made these",
           2:18; "-ts | They also do have", 3:55), and never opens on a lone leftover word before a long pause
           ("spreadsheet | 3 s | in terms of reselling", 9:57). Audio only.
`quiet_lines` (separate): stretches where he sat back from the mic (>= 6 dB under his usual speech) get lifted, capped.
"""
import math
import os
import re
import wave

import numpy as np

WIN = 0.02
VOICED, QUIET = -40.0, -42.0
CONJ = {"and", "but", "so", "or"}
SOUNDALIKE = {"and", "an", "in", "um", "uh"}
DANGLE = {"as", "the", "a", "an", "to", "of", "with", "for", "my", "your", "our", "their", "in", "on", "at", "from", "into",
          "is", "are", "be", "was", "were", "his", "her", "its"}


def _n(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def _same(a, b):
    if a == b:
        return True
    a2, b2 = a.rstrip("s"), b.rstrip("s")
    return a2 == b2 or (len(a2) >= 5 and len(b2) >= 5 and a2[:5] == b2[:5])


def _lcs(T, H):
    """length of the longest common subsequence + the index in H of the last matched word."""
    n, m = len(T), len(H)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            L[i + 1][j + 1] = L[i][j] + 1 if _same(T[i], H[j]) else max(L[i][j + 1], L[i + 1][j])
    i, j, last = n, m, -1
    while i and j:
        if _same(T[i - 1], H[j - 1]) and L[i][j] == L[i - 1][j - 1] + 1:
            last = max(last, j - 1)
            i, j = i - 1, j - 1
        elif L[i - 1][j] >= L[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return L[n][m], last


def levels(mic_path):
    w = wave.open(str(mic_path))
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    n = int(WIN * sr)
    return 20 * np.log10(np.sqrt((a[: len(a) // n * n].reshape(-1, n) ** 2).mean(axis=1)) + 1e-9)


class _Audio:
    def __init__(self, lv):
        self.lv = lv

    def at(self, t):
        i = int(t / WIN)
        return self.lv[i] if 0 <= i < len(self.lv) else -99.0

    def gap(self, lo, hi):
        """quietest 20 ms in [lo, hi], only when it is real quiet; else None."""
        i0, i1 = max(0, int(lo / WIN)), min(len(self.lv) - 1, int(hi / WIN))
        if i1 <= i0:
            return None
        k = i0 + int(np.argmin(self.lv[i0:i1 + 1]))
        return k * WIN + WIN / 2 if self.lv[k] < QUIET else None

    def longest_quiet(self, lo, hi, min_len=0.06):
        """(start, end) of the longest run of quiet windows in [lo, hi], at least min_len long; None if there is none."""
        i0, i1 = max(0, int(lo / WIN)), min(len(self.lv), int(hi / WIN) + 1)
        best, run0 = None, None
        for i in range(i0, i1 + 1):
            q = i < i1 and self.lv[i] < QUIET
            if q and run0 is None:
                run0 = i
            if not q and run0 is not None:
                if (i - run0) * WIN >= min_len and (best is None or i - run0 > best[1] - best[0]):
                    best = (run0, i)
                run0 = None
        return (best[0] * WIN, best[1] * WIN) if best else None

    def next_onset(self, t, limit):
        """first time >= t where 3 windows in a row are voiced."""
        i, end = int(t / WIN), min(len(self.lv) - 3, int(limit / WIN))
        while i < end:
            if self.lv[i] > VOICED and self.lv[i + 1] > VOICED and self.lv[i + 2] > VOICED:
                return i * WIN
            i += 1
        return None

    def quiet_run_after(self, t, need, limit):
        """start of the first run of `need` s of quiet after t (before limit)."""
        i, end, run = int(t / WIN), min(len(self.lv), int(limit / WIN)), 0
        while i < end:
            run = run + 1 if self.lv[i] < QUIET else 0
            if run * WIN >= need:
                return (i - run + 1) * WIN
            i += 1
        return None

    def quiet_run_before(self, t, need, limit):
        """end of the last run of `need` s of quiet before t (after limit)."""
        i, end, run = int(t / WIN) - 1, max(0, int(limit / WIN)), 0
        while i >= end:
            run = run + 1 if self.lv[i] < QUIET else 0
            if run * WIN >= need:
                return (i + run) * WIN
            i -= 1
        return None


def _dangle_ok(au, words, nw, k, a, b, c, head):
    """The clip's last function word ENDS its phrase, so word k must not come back (bapesta dhgate 2026-10-25, 2:03: "I love
    the colorways they're going with | especially when they're actually releasing..." got "espec-" put back, "something
    else at the back of the sentence"): he paused >= 0.2 s right where the clip ends, or word k runs straight on into more
    cut speech (putting it back would leave IT dangling)."""
    off = os.environ.get("RG_OFF", "")
    # a REAL pause: every 20 ms <= -46 dB for 0.2 s, starting by b + 0.1 (a soft "them" at -38..-46 dB after "talk to" is a
    # word, not a pause: reselling spreadsheet 9:20, regress 2026-10-25)
    i0, i1 = int(max(a, b - 0.1) / WIN), int(min(c, b + 0.1) / WIN)
    need = int(round(0.2 / WIN))
    if "dangpause" not in off and any(i + need <= len(au.lv) and (au.lv[i:i + need] <= -46).all() for i in range(i0, i1 + 1)):
        return True
    k2 = k + 1
    while k2 < len(words) and not nw[k2]:
        k2 += 1
    return "dangnext" not in off and k2 < len(words) and k2 not in head and words[k2]["s"] < c \
        and words[k2]["s"] - words[k]["e"] <= 0.15 and au.quiet_run_after(words[k]["e"] - 0.1, 0.12, words[k2]["s"] + 0.15) is None


def cleanup(kept, words, mic_path, checks, protect=()):
    try:
        au = _Audio(levels(mic_path))
    except Exception:
        return kept
    mid = lambda k: (words[k]["s"] + words[k]["e"]) / 2
    nw = [_n(w["w"]) for w in words]
    clips = [list(c) for c in kept]
    notes = []
    fmt = lambda t: f"{int(t // 60)}:{t % 60:04.1f}"

    def idx(a, b):
        return [k for k in range(len(words)) if a <= mid(k) <= b and nw[k]]

    def head_of(c, d, head):
        """first words heard after clip start c: a word straddling c (>= 0.05 s of it plays) counts, and when Whisper
        stretched a word over >= 1.5 s near the start (it swallowed a whole retake into "Etsy", 11:11) the opening is
        re-transcribed."""
        st = [k for k in range(len(words)) if words[k]["s"] < c < words[k]["e"] - 0.05 and nw[k] and k not in head]
        h = st[-1:] + head
        # the clip opened INSIDE speech (no 0.2 s of quiet just before it): the cut words it opened in the middle of are
        # part of what starts here ("but you can | trust you when I say", 5:22, where the restart began 0.4 s earlier)
        if au.quiet_run_before(c, 0.2, c - 0.35) is None:
            pre = [k for k in range(len(words)) if nw[k] and words[k]["e"] <= c + 0.05 and words[k]["e"] >= c - 1.2
                   and k not in h and not any(x <= mid(k) <= y for x, y in clips)][-3:]
            h = pre + h
        if any(words[k]["e"] - words[k]["s"] >= 1.5 and words[k]["s"] < c + 4 for k in h[:6]):
            heard = _retranscribe(mic_path, c, min(d, c + 6))
            if heard:
                return heard, [k for k in h if k in head]   # heard from c on: no prefix words in it
        return [nw[k] for k in h[:14]], h

    def end_before(k, lo):
        """a clip end just before word k: the start of the LONGEST real pause near Whisper's start of it (its times run
        early or late by ~0.4 s; the single quietest 20 ms was a dip inside "taken down" at 5:22), else its Whisper start."""
        r = au.longest_quiet(max(lo, words[k]["s"] - 0.35), words[k]["s"] + 0.5)
        return r[0] + 0.06 if r else words[k]["s"] - 0.02

    def start_before(k, lo):
        r = au.longest_quiet(max(lo, words[k]["s"] - 0.5), words[k]["s"] + 0.15)
        return max(r[0], r[1] - 0.12) if r else words[k]["s"] - 0.05

    i, b_done, dipped = 0, set(), set()
    while i < len(clips) - 1:
        a, b = clips[i]
        c, d = clips[i + 1]
        if any(pa <= a + 0.1 and b - 0.1 <= pb for pa, pb in protect):
            i += 1
            continue
        tail, head = idx(a, b), idx(c, d)
        if not tail or not head:
            i += 1
            continue
        H, head2 = head_of(c, d, head)
        done = False
        # R: a SHORT false start at the clip end that the next clip opens with: "...sell to a wide range of people and
        # again, | Again, I do want to remind you" (reselling spreadsheet 9:20, 2026-10-23: B needs 3+ words, so the
        # 1-2 word restart stayed and the stub rule even finished "again,"). The clip's last 1-2 words (counting the word
        # it ends inside) are the next clip's first words, after a conjunction or cut off mid-word: the clip ends before
        # them (and before the conjunction), on "people".
        ext = tail + [k for k in range(len(words)) if words[k]["s"] < b - 0.05 < words[k]["e"] and nw[k] and k not in tail][:1]
        for m in ((2, 1) if c not in b_done and os.environ.get("RG_OFF") != "restart" else ()):
            if len(ext) < m + 2 or len(H) < m or re.search(r"[.?!]$", words[ext[-1]]["w"]):
                continue
            if not all(_same(nw[ext[-m + j]], H[j]) for j in range(m)) or set(ext[-m:]) & set(head2):
                continue                                  # (one word split over the join is not a restart)
            s0 = len(ext) - m
            cut_in = ext[-1] not in tail                  # the clip ends inside the restart's last word
            if nw[ext[s0 - 1]] in CONJ:
                s0 -= 1
            elif not cut_in:
                continue                                  # "...the shoes | shoes are" without a break: a normal repeat
            nb = end_before(ext[s0], a)
            if nb - a < 1.0:
                continue
            # never move the end LATER: end_before can pick the pause AFTER a short word (bapesta dhgate 2026-10-25, 2:45:
            # "spreadsheet sim- | Simply click here" ended at 343.42 with "sim-" in it; the longest pause near Whisper's
            # "simply" was the one after it, the end moved to 343.82 and "simply" played twice). Re-listen for where the
            # restart's first word really starts and end on the deepest dip just before it.
            if nb >= b - 0.02 and "restartlate" not in os.environ.get("RG_OFF", ""):
                heard = _retranscribe(mic_path, max(a, b - 2.5), b + 0.8, timed=True)
                # the restart word is the LAST word heard before the end, in its final second (cartier 6:46: the stretched
                # trailing "you" wasn't audible, and the "you" of "get you in the right direction" was taken instead)
                before_b = [(w_, t) for w_, t in heard if t < b]
                t_r = before_b[-1][1] if before_b and _same(before_b[-1][0], nw[ext[s0]]) and before_b[-1][1] >= b - 1.0 else None
                if t_r is None:
                    continue
                i0, i1 = int(max(a, t_r - 0.25) / WIN), int((t_r + 0.03) / WIN)
                if i1 <= i0:
                    continue
                m_ = i0 + int(np.argmin(au.lv[i0:i1]))
                nb = m_ * WIN + WIN / 2
                dipped.add(round(nb, 3))   # the stub pass must not "finish" the word before it into the restart
                if nb - a < 1.0 or nb >= b - 0.02:
                    continue
            b_done.add(c)
            notes.append(f"short restart: \"{' '.join(words[x]['w'] for x in ext[s0:])}\" @ {fmt(words[ext[s0]]['s'])} "
                         f"is how the next clip opens: cut")
            clips[i][1] = round(nb, 3)
            if head2 and head2[0] not in head and words[head2[0]]["s"] < c:
                clips[i + 1][0] = round(start_before(head2[0], nb + 0.05), 3)
            done = True
            break
        if done:
            continue
        # B: abandoned tail, said again at the start of the next clip. The EXACT repeat wins (the largest k whose words are
        # all said again: 8:46 "...cop some of these shoes | you're looking to get some" -> only "you're looking to get some"
        # goes, not "some of these shoes" too); a looser match (60 %, or a short restart) only when there is none.
        # Once per join: a second pass on an already-cut join would eat into the sentence before it.
        def fits(k, loose):
            T = [nw[x] for x in tail[-k:]]
            # a PROMISE is not an abandoned start: "...put this on to show you exactly | what it looks like" then "So here's
            # what the hoodie looks like" is the setup and its delivery (best sp5der hoodie 2026-10-23, 1:56: "it just cuts at
            # 'what' ... keep the full 'show you exactly what it looks like'")
            before = [nw[x] for x in tail[max(0, len(tail) - k - 3):len(tail) - k]]
            if os.environ.get("RG_OFF") != "promise" and any(t in ("show", "showing", "tell", "see") for t in before) and T[0] in ("what", "how", "exactly", "where", "why"):
                return False
            # the restart's first word is one of the first two words heard, counted from the cut words the clip opened
            # inside AND from the clip's own first word ("[to get some] | if you're looking to get some" at 8:46: with
            # only the first, "some of these shoes you're looking to get some" matched and "cop some of these shoes" went)
            npre = max(0, len(head2) - len([k for k in head2 if k in head]))
            anchors = H[:2] + H[npre:npre + 2]   # either: the restart may begin in those cut words (5:22) or in the clip
            if not any(_same(T[0], h) for h in anchors) or not any(len(t) >= 4 for t in T):
                return False
            n, _ = _lcs(T, H[:k + 4])
            if not loose:
                return n >= (k - 1 if k >= 5 else k)
            # a FINISHED sentence is never an abandoned start, however alike the next one sounds (regression suite
            # 2026-10-23: "...move on to the next pair of Amiri jeans. | Next up, we do have the Mary jeans" and "...I already
            # had the Mary shirt on to go ahead and match the fit. | ...Mary bone runners as well to go ahead and complete
            # the fit" were cut from the APPROVED amiri jeans edit). Only the exact repeat above may cut one.
            if re.search(r"[.?!]$", words[tail[-1]]["w"]) and os.environ.get("RG_OFF") != "punct":
                return False
            # same opening word + a content word again ("but trust me guys, it | but you can trust ..."): a short restart
            short = k <= 6 and H and _same(T[0], H[0]) and n >= 2 and                 any(len(t) >= 4 and t not in DANGLE and any(_same(t, h) for h in H[1:k + 3]) for t in T[1:])
            return n >= max(3, math.ceil(0.6 * k)) or short
        ks = [] if c in b_done else             ([k for k in range(min(len(tail), 14), 2, -1) if fits(k, False)][:1] or
             [k for k in range(min(len(tail), 14), 2, -1) if fits(k, True)][:1])
        for k in ks:
            b_done.add(c)
            if True:
                if k == len(tail):
                    notes.append(f"redo: dropped {fmt(a)}-{fmt(b)} (\"{' '.join(words[x]['w'] for x in tail[:8])}...\" is said again next)")
                    clips.pop(i)
                else:
                    nb = end_before(tail[-k], a)
                    notes.append(f"redo: \"{' '.join(words[x]['w'] for x in tail[-k:])}\" @ {fmt(words[tail[-k]]['s'])} is said again at the next clip: cut")
                    clips[i][1] = round(nb, 3)
                nxt = i if k == len(tail) else i + 1
                # ...only when the restart runs on into the clip's own words. When the whole match sits in the cut words
                # before the clip, those words are ANOTHER abandoned try, not the start of this one (bapesta dhgate
                # 2026-10-25, 0:42: "...going to [be the babes the] | So right in front of us is going to be the box"; the
                # start was pulled back onto "be the babes the")
                npre = max(0, len(head2) - len([x for x in head2 if x in head]))
                own_hit = "redoown" in os.environ.get("RG_OFF", "") or \
                    _lcs([nw[x] for x in tail[-k:]], H[npre:npre + k + 4])[0] >= 1
                if own_hit and head2 and head2[0] not in head and nxt < len(clips) and words[head2[0]]["s"] < clips[nxt][0]:
                    # ...and the restart plays from its first word (the next clip had opened in its middle)
                    clips[nxt][0] = round(start_before(head2[0], (clips[nxt - 1][1] + 0.05) if nxt else 0.0), 3)
                done = True
                break
        if done:
            continue
        # A: the cut holds a retake of the tail that finishes the sentence, right up to the next clip
        cut = [x for x in range(tail[-1] + 1, head[0]) if nw[x]]
        if 3 <= len(cut) <= 24:
            C = [nw[x] for x in cut]
            for k in range(min(len(tail), 12), 2, -1):
                T = [nw[x] for x in tail[-k:]]
                hit = None
                for j in range(len(C)):
                    if not _same(C[j], T[0]):
                        continue
                    n, last = _lcs(T, C[j:j + k + 2])
                    rest = len(C) - (j + last + 1)
                    if n >= math.ceil(0.7 * k) and 1 <= rest <= 6:
                        hit, r0 = j, j + last + 1
                # words HE put back (raw/extra_keeps) are never swapped for another take (dhgate cologne spread 2026-10-25,
                # 1:55: his kept "just sold five bottles the past few days" became "sold five | the few days", the tail of
                # his own "cut it at the few days" note to the editor)
                if hit is not None and any(pa - 0.1 <= words[tail[-k]]["s"] and words[tail[-k]]["e"] <= pb + 0.1 for pa, pb in protect):
                    break
                if hit is not None:
                    nb = end_before(tail[-k], a)
                    if "retakedip" not in os.environ.get("RG_OFF", "") and au.longest_quiet(max(a, words[tail[-k]]["s"] - 0.35), words[tail[-k]]["s"] + 0.5) is None:
                        # no real pause before the retaken words: Whisper's start of them can be 0.2 s late (canada goose
                        # jacket 1:04, "collaboration that" -> "that" began at 143.84, Whisper said 144.02, and the clip kept
                        # it: "that | that they had"). End on the deepest dip (< -30 dB) just before Whisper's start.
                        i0, i1 = int(max(a, words[tail[-k]]["s"] - 0.35) / WIN), int((words[tail[-k]]["s"] + 0.04) / WIN)
                        if i1 > i0:
                            m = i0 + int(np.argmin(au.lv[i0:i1]))
                            if au.lv[m] < -30:
                                nb = m * WIN + WIN / 2
                                dipped.add(round(nb, 3))   # the stub pass must not "finish" Whisper's late word end here
                    nc = start_before(cut[hit], nb + 0.05)
                    # the words AFTER the retake that the next clip says again are an abandoned start of that clip ("that
                    # they had let's take a closer look let's | Let's take a closer look at the badge", canada goose jacket
                    # 1:04-1:11): the put-back stops before them, so the sentence runs "...that they had. | Let's take..."
                    R = C[r0:]
                    tail_cut = None
                    if "retakerest" not in os.environ.get("RG_OFF", "") and len(R) >= 2 and _same(R[0], H[0]) \
                            and _lcs(R, H[:len(R) + 3])[0] >= math.ceil(0.6 * len(R)):
                        tail_cut = end_before(cut[r0], nc + 0.3)
                    notes.append(f"retake: \"{' '.join(words[x]['w'] for x in tail[-k:])}\" @ {fmt(words[tail[-k]]['s'])} -> the later take "
                                 f"that finishes it (\"{' '.join(words[x]['w'] for x in cut[hit:r0 if tail_cut else None])}\")"
                                 + (f", without \"{' '.join(words[x]['w'] for x in cut[r0:])}\" (said again next)" if tail_cut else ""))
                    if tail_cut and tail_cut - nc >= 0.5:
                        clips[i][1] = round(nb, 3)
                        clips.insert(i + 1, [round(nc, 3), round(tail_cut, 3)])
                        b_done.add(c)
                    else:
                        clips[i][1], clips[i + 1][0] = round(nb, 3), round(nc, 3)
                    done = True
                    break
        if done:
            i += 1
            continue
        # conj: "and | and/in"
        if nw[tail[-1]] in CONJ and H and H[0] in SOUNDALIKE and len(tail) > 2:
            clips[i][1] = round(end_before(tail[-1], a), 3)
            if head2 and head2[0] not in head:   # the next clip had opened inside that word ("n" of "In"): open before it
                clips[i + 1][0] = round(start_before(head2[0], clips[i][1] + 0.05), 3)
            notes.append(f"doubled \"{words[tail[-1]]['w']} | {H[0]}\" @ {fmt(words[tail[-1]]['s'])}: the first one cut")
            i += 1
            continue
        # dangle: ends on a function word -> the word that completes it comes back, up to measured quiet
        k = tail[-1] + 1
        if nw[tail[-1]] in DANGLE and k < len(words) and k not in head and nw[k] and nw[k] not in DANGLE | CONJ \
                and words[k]["e"] - words[k]["s"] <= 0.9 and nw[k] != nw[head[0]] and not _dangle_ok(au, words, nw, k, a, b, c, head):
            q = au.quiet_run_after(max(b, words[k]["e"] - 0.2), 0.06, words[k]["e"] + 0.35)
            if q is not None and q < c:
                clips[i][1] = round(q + 0.06, 3)
                notes.append(f"\"{words[tail[-1]]['w']} | {words[k]['w']}\" @ {fmt(words[k]['s'])}: the end was cut off, \"{words[k]['w']}\" put back")
        i += 1

    # head stutter: a clip that opens on a false start said again right away ("in terms of | in terms of where to resell
    # cologne", 11:11, inside a stretch Whisper had swallowed into one word): it opens on the second try. Only checked
    # where Whisper's words can't be trusted (a word >= 1.5 s in the first 4 s), re-transcribed with times.
    for cl in clips:
        a, b = cl
        h = idx(a, min(b, a + 4))
        if not any(words[k]["e"] - words[k]["s"] >= 1.5 for k in h) or b - a < 3:
            continue
        heard = _retranscribe(mic_path, a, min(b, a + 6), timed=True)
        for k, o in ((4, 0), (3, 0), (2, 0), (4, 1), (3, 1), (2, 1)):
            # o = 1: the first try's opening word fell before the clip ("[in] terms of | in terms of where")
            if len(heard) >= 2 * k + o and all(_same(heard[j][0], heard[j + k + o][0]) for j in range(k)):
                t2 = heard[k + o - 1][1] if o else heard[k][1]
                g = au.longest_quiet(heard[k - 1][1], t2 + 0.1)
                cl[0] = round(max(g[0], g[1] - 0.12) if g else t2 - 0.1, 3)
                notes.append(f"false start \"{' '.join(w for w, _ in heard[:k + o])}\" said twice at a clip start {fmt(a)}: opens on the second")
                break

    # stub: mid-sound slivers and lone leftover words at clip edges (audio)
    for n, cl in enumerate(clips):
        a, b = cl
        if any(pa <= a + 0.1 and b - 0.1 <= pb for pa, pb in protect) or b - a < 2.0:
            continue
        if all(au.at(a + j * WIN) > VOICED for j in range(3)):            # opens mid-sound
            q = au.quiet_run_after(a, 0.1, a + 0.6)
            on = au.next_onset(q, b) if q is not None else None
            if on is not None and b - on > 1.0:
                notes.append(f"sliver at a clip start {fmt(a)} ({q - a:.2f} s of a cut word): starts at the next word")
                cl[0] = a = round(on - 0.12, 3)
        elif "softhead" not in os.environ.get("RG_OFF", ""):
            # opens on a SOFT leftover (the breathy tail of a cut take, -46..-28 dB, <= 0.4 s) then >= 0.2 s of quiet before
            # the real first word: Whisper put the retake's "hey" at the end of the first "guys" (dhgate lanvins 2026-10-26,
            # 0:26: "let's go | (sound) | hey guys, it's {{REVIEW_CHANNEL}}": "there's definitely a sound in between there")
            q = au.quiet_run_after(a, 0.2, a + 0.8)
            if q is not None and q - a >= 0.06:
                peak = max(au.at(a + j * WIN) for j in range(int((q - a) / WIN)))
                on = au.next_onset(q, b)
                if q - a <= 0.4 and -46 < peak < -28 and on is not None and b - on > 1.0:
                    notes.append(f"soft leftover at a clip start {fmt(a)} ({q - a:.2f} s, peak {peak:.0f} dB): starts at the next word")
                    cl[0] = a = round(on - 0.12, 3)
        on = au.next_onset(a, min(b, a + 1.5))
        if on is not None:                                               # a lone word, then a long pause
            q = au.quiet_run_after(on, 1.0, min(b, on + 1.8))
            q = q if q is not None and q - on <= 0.8 else None
            # a lone word (<= 0.8 s, then >= 1 s quiet), or a short mumbled leftover phrase (<= 2 s, then >= 1.5 s quiet):
            # 9:57 "the ones on the reselling spreadsheet | 2.9 s | in terms of reselling"
            if q is None:
                q2 = au.quiet_run_after(on, 1.5, min(b, on + 3.6))
                q = q2 if q2 is not None and q2 - on <= 2.0 else None
            if q is not None and q - on <= 2.0:
                on2 = au.next_onset(q, b)
                if on2 is not None and b - on2 > 2.0:
                    notes.append(f"lone word + {on2 - q:.1f} s pause at a clip start {fmt(a)}: starts at the sentence after it")
                    cl[0] = a = round(on2 - 0.12, 3)
        if n == len(clips) - 1:                                          # the sign-off end stays as it is
            continue
        if round(b, 3) in dipped:   # ended on purpose before a retaken word (canada goose 1:04: the finish rule re-added "that")
            continue
        if all(au.at(b - (j + 1) * WIN) > VOICED for j in range(3)):     # closes mid-sound
            # ...inside the clip's OWN last word, the end of a sentence or more than half of it said: finish the word
            # (regression suite 2026-10-23: the approved amiri jeans edit lost "match the fit." and "colorway." here)
            own = next((w for w in words if w["s"] < b - 0.05 < w["e"]), None)
            nxt_a = clips[n + 1][0]
            if os.environ.get("RG_OFF") != "finish" and own and (re.search(r"[.?!,]$", own["w"]) or b - own["s"] >= 0.5 * (own["e"] - own["s"])):
                q = au.quiet_run_after(own["e"] - 0.05, 0.06, min(own["e"] + 0.4, nxt_a - 0.05))
                end = (q + 0.04) if q is not None else min(own["e"] + 0.08, nxt_a - 0.05)
                # a sentence end runs straight into the next word (no 60 ms of quiet): the word ends at the first deep dip
                # (< -45 dB) right after it, not at a pause inside the NEXT word (dhgate cologne spread 2026-10-25, 2:04:
                # "for this scent. It's |" - the 40 ms dip after "scent" was too short, the end went to the gap between
                # "I" and "ts" and the clip said "It's")
                if "finishdip" not in os.environ.get("RG_OFF", "") and re.search(r"[.?!]$", own["w"]):
                    i0, i1 = int((own["e"] - 0.05) / WIN), int(min(own["e"] + 0.15, end) / WIN)
                    dip = next((i for i in range(i0, i1) if au.lv[i] < -45), None)
                    if dip is not None and dip * WIN + WIN < end:
                        end = dip * WIN + WIN
                if end > b:
                    notes.append(f"clip end {fmt(b)} inside '{own['w']}': finished the word ({fmt(end)})")
                    cl[1] = round(end, 3)
                    continue
            q = au.quiet_run_before(b, 0.1, b - 0.6)
            # a sliver trim removes SOUND, never a whole word that plays ("fit." / "colorway." sat between the quiet and
            # the clip end in the approved amiri jeans edit and were cut with the sliver)
            if os.environ.get("RG_OFF") != "whole" and q is not None and any(q < (w["s"] + w["e"]) / 2 < b - 0.02 for w in words):
                q = None
            # ...nor inside a word that STRADDLES that quiet: a stop consonant's closure ("cl" of "clean", 0.1 s of silence
            # INSIDE the word) read as the gap before the next word, and the clip said "very very cl-" (balenciaga track
            # led review 2026-10-26, 2:03: "my sentence gets cut off ... a weird jarring cut"). Then end at the quietest
            # frame after that word instead.
            strad = next((w for w in words if q is not None and w["s"] < q - 0.02 and w["e"] > q + 0.1 and w["s"] < b), None)
            if strad is not None and os.environ.get("RG_OFF") != "straddle":
                i0, i1 = int((strad["e"] - 0.06) / WIN), int((b - 0.02) / WIN)
                if i1 > i0:
                    best_i = min(range(i0, i1), key=lambda i: au.lv[i])
                    notes.append(f"clip end {fmt(b)}: the quiet at {fmt(q)} is inside '{strad['w']}', ends after it ({fmt(best_i * WIN + WIN)})")
                    cl[1] = round(best_i * WIN + WIN, 3)
                q = None
            if q is not None and q - a > 1.0:
                notes.append(f"sliver at a clip end {fmt(b)} ({b - q:.2f} s of the next word): ends before it")
                cl[1] = round(q - WIN + 0.05, 3)
    out = [(round(x, 3), round(y, 3)) for x, y in clips if y - x >= 0.5]
    if notes:
        checks.append("Join cleanup (source time): " + "; ".join(notes) + ".")
    return out


_MODEL = []


def _retranscribe(mic_path, a, b, timed=False):
    """normalised words heard in [a, b] of the 16 kHz mic file (faster-whisper, numpy input), [] on failure."""
    try:
        import sys
        sys.path.insert(0, r"{{KIT}}/tools")
        import whisper_gpu
        if not _MODEL:
            _MODEL.append(whisper_gpu.load("small.en")[0])
        w = wave.open(str(mic_path))
        sr = w.getframerate()
        w.setpos(int(a * sr))
        x = np.frombuffer(w.readframes(int((b - a) * sr)), np.int16).astype(np.float32) / 32768
        segs, _ = _MODEL[0].transcribe(x, word_timestamps=True, language="en")
        return [t for t in (_n(q.word) for s_ in segs for q in s_.words) if t] if not timed else             [(_n(q.word), a + q.start) for s_ in segs for q in s_.words if _n(q.word)]
    except Exception:
        return []


def loud_words(kept, mic_path, checks, over_db=6.0, step_db=3.0, win=0.5, step=0.25, max_cut=8.0):
    """The mirror of quiet_lines, on the voice's ENERGY per half second (what the ear compares, not the loudest
    syllables): (1) a stretch more than over_db above his typical half-second comes down to it; (2) a JUMP AT A CUT: the
    next clip's first second starting more than step_db hotter than the last 1.5 s of the clip before is brought down to
    match and eased back (balenciaga track led review 2026-10-26, 3:35: a quiet trailing line cut into a punchy retake
    "in ORDER to get", +5 dB at the join, "my voice gets weirdly loud ... I heard this before, fix this for good").
    Returns [(src_a, src_b, -dB)] for the quiet-line lift's gain envelope (0.15 s ramps)."""
    try:
        lv = levels(mic_path)
    except Exception:
        return []
    en = lambda a, b: (lambda seg: float(10 * np.log10(np.mean(10 ** (seg[seg > -45] / 10)))) if (seg > -45).mean() >= 0.4 else None)(
        lv[int(a / WIN):max(int(a / WIN) + 1, int(b / WIN))])
    wins = [(t, e) for a, b in kept for t in np.arange(a, b - win + 1e-6, step) if (e := en(t, t + win)) is not None]
    if len(wins) < 40:
        return []
    med = float(np.median([e for _, e in wins]))
    out = []
    for t, e in wins:
        if e > med + over_db:
            g = -min(max_cut, e - med - 2.0)
            if out and t <= out[-1][1] + 0.01:
                out[-1] = (out[-1][0], t + win, min(out[-1][2], g))
            else:
                out.append((t, t + win, g))
    steps = []
    # every clip's ENTRANCE (its first 0.6 s, often right after a section wipe's beat-only pause or a cut) is matched to the
    # clip before and to his typical level: the ear judges a word by what came just before it
    for j, (a1, b1) in enumerate(kept):
        after = en(a1, min(b1, a1 + 0.6))
        if after is None:
            continue
        before = en(max(kept[j - 1][0], kept[j - 1][1] - 1.5), kept[j - 1][1]) if j else None
        over = max(after - med - 3.0, (after - before - step_db) if before is not None else 0.0)
        if over > 0.5:
            steps.append((a1, min(b1, a1 + 1.2), -min(max_cut, over + 1.0)))
    merged = []   # overlapping stretches are ONE dip at the deepest gain (summed envelopes would go below zero)
    for x, y, g in sorted(out + steps):
        if merged and x <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], y), min(merged[-1][2], g))
        else:
            merged.append((x, y, g))
    out = [(round(x, 2), round(y, 2), round(g, 1)) for x, y, g in merged]
    if out:
        checks.append(f"Loud words / level jumps at cuts brought down (typical {med:.0f} dB, {len(steps)} jumps at cuts): " +
                      ", ".join(f"{int(x // 60)}:{x % 60:04.1f}-{int(y // 60)}:{y % 60:04.1f} {g:+.0f} dB" for x, y, g in out[:12])
                      + (" ..." if len(out) > 12 else "") + " (source).")
    return out


def quiet_lines(kept, mic_path, checks, drop_db=6.0, win=1.5, step=0.5, max_lift=9.0):
    """Stretches of kept speech >= drop_db under his usual speech level (he sat back from the mic, 8:46 "I was farther
    away from the mic, so we need some handling for that"): lifted by (difference - 1 dB), capped at max_lift.
    Returns [(src_a, src_b, dB)]."""
    try:
        lv = levels(mic_path)
    except Exception:
        return []
    voiced = np.concatenate([lv[int(a / WIN):int(b / WIN)] for a, b in kept]) if kept else np.array([])
    voiced = voiced[voiced > -45]
    if len(voiced) < 500:
        return []
    ref = float(np.percentile(voiced, 85))
    out = []
    for a, b in kept:
        t = a
        while t + win <= b + 1e-6:
            seg = lv[int(t / WIN):int((t + win) / WIN)]
            v = seg[seg > -45]
            if len(v) >= 0.3 * len(seg):
                p = float(np.percentile(v, 85))
                if p < ref - drop_db:
                    g = min(max_lift, ref - p - 1.0)
                    if out and t <= out[-1][1] + 0.01:
                        out[-1] = (out[-1][0], t + win, max(out[-1][2], g))
                    else:
                        out.append((t, t + win, g))
            t += step
    out = [(round(x, 2), round(y, 2), round(g, 1)) for x, y, g in out]
    if out:
        checks.append(f"Quiet lines lifted (he sat back from the mic; usual speech {ref:.0f} dB): " +
                      ", ".join(f"{int(x // 60)}:{x % 60:04.1f}-{int(y // 60)}:{y % 60:04.1f} +{g:.0f} dB" for x, y, g in out) + " (source).")
    return out
