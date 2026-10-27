"""Repeat audit of a FINISHED draft (dhgate watchb spread 2026-10-24: the cutter crashed, the old rules ran, and a draft full
of retakes went out as ready; the QC ran with --no-words, so nothing listened to what the draft SAYS. User: "I'm just still
seeing issues with the video").

    python draft_audit.py <project dir> [--video output/final.mp4] [--no-fix]

Transcribes what the draft actually plays (medium.en, word times) and flags:
  repeat    a 4+ word phrase (2+ content words) said again within 60 s of the draft
  stranded  a kept piece under 3 s with 5 s+ cut on both sides (a scrap of a bad take)
  ending    the draft ends on sound (a word cut off: "the word bye wasn't protected")
Each flag is mapped back to recording time (work/timeline.json). Clear retakes (the first try ends a kept piece and the
second try opens a later piece within 20 s of draft time) are FIXED: the first try goes into raw/audit_cuts.json (read by
edit_review like his extra_cuts) and ONE rebuild is started through Studio (work/audit_state.json caps it at one round).
Anything else is listed in output/draft_audit.md and the step exits 2, so the build shows as failed, never "ready".
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
STOP = set("a an the and or but so to of in on for at it its it's is are was be been i im i'm you your you're we our they this "
           "that these those with as if just like um uh yeah okay gonna going go get got do does did have has had can will would "
           "very really actually pretty much here there what which who how all any some one guys".split())
# phrases he says on purpose more than once (sign-off, greetings, his catch-phrases)
OK_PHRASES = ["link down below", "in the description", "hey guys", "what's up guys", "let's go ahead", "go ahead and",
              "make sure to", "as you can see", "you guys can see", "keep that in mind", "at the end of the day"]


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def transcribe(video):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    from whisper_gpu import load
    model = load("medium.en")[0]
    # NO stutter prompt: primed with "so, so I I was", medium.en invented "a bunch a bunch" where he said it once (watch
    # spreadsheet 2026-10-24, draft 5:39) and the audit failed a clean draft
    segs = model.transcribe(audio, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)[0]
    words = [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for sg in segs for w in (sg.words or [])]
    return words, audio


class Map:
    """draft (output) time <-> recording (source) time through the kept pieces."""

    def __init__(self, kept, offset=0.0):
        self.kept, self.offset, self.starts, acc = kept, offset, [], 0.0
        for a, b in kept:
            self.starts.append(acc)
            acc += b - a
        self.duration = acc

    def piece(self, t):
        t -= self.offset
        for k, ((a, b), o) in enumerate(zip(self.kept, self.starts)):
            if o <= t < o + (b - a):
                return k
        return len(self.kept) - 1

    def to_src(self, t):
        k = self.piece(t)
        return self.kept[k][0] + (t - self.offset - self.starts[k])


def find_repeats(words, window=60.0, n=6):
    toks = [norm(w["w"]) for w in words]
    seen, out = {}, []
    for i in range(len(toks) - n + 1):
        g = toks[i:i + n]
        if sum(1 for t in g if t and t not in STOP) < 2 or not all(g):
            continue
        phrase = " ".join(g)
        if any(p in phrase or phrase in p for p in OK_PHRASES):
            continue
        for j in seen.get(phrase, []):
            if words[i]["s"] - words[j]["s"] <= window and i - j >= n:
                out.append((j, i, phrase))
                break
        seen.setdefault(phrase, []).append(i)
    # a short phrase said twice BACK TO BACK ("starting off | starting off with", "this watch | this watch"): 2-3 words,
    # one of them a content word, the second right after the first (within 2.5 s)
    for k in (3, 2):
        for i in range(len(toks) - 2 * k + 1):
            a, b = toks[i:i + k], toks[i + k:i + 2 * k]
            if a == b and all(a) and any(t not in STOP for t in a) and words[i + k]["s"] - words[i + k - 1]["e"] < 2.5:
                out.append((i, i + k, " ".join(a)))
    out.sort()
    # one flag per pair of tries (overlapping n-grams of the same repeat collapse)
    merged = []
    for j, i, ph in out:
        if merged and i - merged[-1][1] <= n and j - merged[-1][0] <= n + 2:
            continue
        merged.append((j, i, ph))
    return merged


# a clip that ENDS on one of these (no punctuation after it) stops in the middle of a sentence: "...section below and you're |
# Then you'll be brought" (Uber october 2026-10-25), "be the babes the | So right in front of us" (bapesta 2026-10-25)
DANGLE = set("and but so or the a an to of for with as because that than then if when your you're i i'm we we're they "
             "is are was it's my this".split())


EMPHASIS = set("way very really so super much more too lots definitely extremely".split())


def mic_level(mic, t0, t1):
    seg = mic[max(0, int(t0 * 16000)):max(0, int(t1 * 16000))]
    return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9) if len(seg) else -99.0


def sentence_ends_at(heard, t):
    """the raw recording, re-transcribed around source time t: True when the word that ends at t closes a sentence and the
    next one opens a new one ("...anybody can go ahead and do it. | But I know", Uber 2026-10-25). He talks with no pause
    between sentences on phone videos, so his mic is loud at a CORRECT cut; "for personal use, it's actually..." (cologne,
    a real cut-off) has a comma and stays a problem."""
    ws = heard(t - 3.0, t + 1.5)
    before = [w for w in ws if w[2] <= t + 0.08]
    after = [w for w in ws if w[1] >= t - 0.08]
    return bool(before and after and re.search(r"[.?!]$", before[-1][0]) and after[0][0][:1].isupper())


def join_checks(kept, m, words, mic, heard=None, phone=False):
    """Listen at every cut (the 4 test videos of 2026-10-25 had 11 cut-join notes the repeat audit never heard):
    talking   his mic is still speaking at the last 0.1 s of a piece or the first 0.1 s of the next (a word cut off:
              cologne "for personal use", "sells really nicely"); measured on the clean mic, not the music mix
    dangle    the piece ends on a word that can't end a sentence ("and you're", "the")
    double    the same content word on both sides of the cut ("all my links ... simply | simply click here")"""
    flags = []
    speech = None
    if mic is not None and len(mic):
        win = mic[: len(mic) // 1600 * 1600].reshape(-1, 1600)
        db = 20 * np.log10(np.sqrt(np.mean(win ** 2, axis=1)) + 1e-9)
        speech = float(np.percentile(db, 80))   # his usual talking level (100 ms windows)
    for k in range(1, len(kept)):
        (a1, b1) = kept[k]
        # the real piece before this one: a section wipe (negative insert) sits between them at a section change
        # (bapesta 0:42 came right after the wipe and was skipped)
        p = k - 1
        while p >= 0 and kept[p][0] < 0:
            p -= 1
        if p < 0 or a1 < 0:
            continue
        a0, b0 = kept[p]
        if a1 - b0 < 0.3:
            # no cut here, but a SLIDE between the two halves of one clip must sit in a pause, not inside his words
            # (reselling spring 2026-10-25: product slides "cut off a word, transitions, even though I finished the sentence")
            if p < k - 1 and speech is not None and mic_level(mic, a1 - 0.1, a1 + 0.1) > speech - 6:
                J = m.starts[k] + m.offset
                flags.append({"kind": "join", "draft": [round(J, 2)], "src": [round(b0, 2), round(a1, 2)],
                              "phrase": " ".join(w["w"] for w in words if J - 2 < w["s"] < J + 2)[:120],
                              "why": "a section slide sits inside his speech (it chops the word): move it onto a cut or a pause"})
            continue   # no real cut (pieces that touch)
        J = m.starts[k] + m.offset
        before = [w for w in words if w["s"] < J - 0.05][-3:]
        after = [w for w in words if w["s"] >= J - 0.05][:3]
        why, loud, near, dangle, double = [], False, False, False, False
        if speech is not None:
            # measured in the audio that was CUT AWAY right past each edge: inside the clip the last word's own tail is
            # loud on every tight, correct cut (approved bapesta/prada finals flagged); speech that carries on past the
            # edge means the word or sentence went on and was cut off
            tail, head = mic_level(mic, b0 + 0.02, b0 + 0.14), mic_level(mic, a1 - 0.14, a1 - 0.02)
            for lv, txt, at in ((tail, "still talking at the cut", b0), (head, "next clip opens mid-word", a1)):
                if lv > speech - 8 and heard is not None and sentence_ends_at(heard, at):
                    continue   # a clean sentence break with no pause between the sentences
                if lv > speech - 8:
                    why.append(f"{txt} ({lv:.0f} dB vs talk {speech:.0f})")
                    near = True
                    loud = loud or lv >= speech - 3
        if before:
            last = before[-1]["w"]
            if norm(last) in DANGLE and not re.search(r"[.?!,]$", last) and J - before[-1]["e"] < 1.0:
                why.append(f'ends on "{last.strip()}"')
                dangle = True
        # a content word said twice in a row right at the cut, on both sides or just before it ("spreadsheet simply
        # simply | click here", bapesta 2:45)
        near_w = [norm(w["w"]) for w in before + after]
        for x, y in zip(near_w, near_w[1:]):
            # "way, way up", "very, very", "super super": his own emphasis, not a retake (reselling spring 4:37)
            if x and x == y and x not in STOP and x not in EMPHASIS:
                why.append(f'"{x}" twice at the cut')
                double = True
                break
        # stub: the clip OPENS on 1-3 words of a failed take, a pause, then a fresh sentence ("The Babista. | So right in
        # front of us is the box", bapesta 0:42; "Guinness in | but anyways guys", prada 3:10)
        stub = False
        if after:
            nxt = [w for w in words if w["s"] >= J - 0.05][:6]
            for n in range(1, 4):
                if n < len(nxt) and nxt[n]["s"] - nxt[n - 1]["e"] >= 0.35 and \
                        (nxt[n]["w"][:1].isupper() or norm(nxt[n]["w"]) in ("so", "but", "and", "now", "okay", "ok")):
                    why.append(f'clip opens on a stub "{" ".join(w["w"] for w in nxt[:n])}" then restarts')
                    stub = True
                    break
        if why:
            # tested 2026-10-25 on the 4 test videos' first drafts + approved finals: a dangling word ALONE was a fine
            # sentence split across the cut 6 times out of 6 on the approved cologne final, so it is only "listen";
            # his mic at full talk level at the edge, or mic + dangling word, or a doubled word = a real error
            # phone videos: he talks with no pause between sentences, so a loud mic at the edge alone was a false alarm
            # 3 times out of 5 on the approved Uber october edit; there it needs a dangling or doubled word too
            hard = (loud and not phone) or (near and dangle) or double or stub
            flags.append({"kind": "join" if hard else "listen", "draft": [round(J, 2)], "src": [round(b0, 2), round(a1, 2)],
                          "phrase": " ".join(w["w"] for w in before) + " | " + " ".join(w["w"] for w in after),
                          "why": "; ".join(why)})
    return flags


def meaning_check(project, words, kept, m):
    """An editor READS the draft (2026-10-25, bapesta 0:42: "OK, starting things off we do have | So right in front of us is
    the box" was him talking to himself, which no sound check hears). The brain gets what the draft says with a || at every
    cut and lists lines a viewer would find broken: abandoned or restarted sentences, self-talk, a line that makes no sense
    next to its neighbours. Always "listen" items (see the note at the bottom)."""
    try:
        from claude_brain import ask
    except Exception:  # noqa
        return []
    cuts = sorted(m.starts[k] + m.offset for k in range(1, len(kept)) if kept[k][0] >= 0 and kept[k - 1][0] >= 0)
    out, ci, last_min = [], 0, -1
    for w in words:
        while ci < len(cuts) and cuts[ci] <= w["s"]:
            out.append("||")
            ci += 1
        if int(w["s"] // 20) != last_min:   # a time stamp every 20 s so answers can point at a moment
            last_min = int(w["s"] // 20)
            out.append(f"[{int(w['s'] // 60)}:{int(w['s'] % 60):02d}]")
        out.append(w["w"])
    try:
        title = json.loads((project / "studio.json").read_text(encoding="utf-8")).get("title") or project.name
    except Exception:  # noqa
        title = project.name
    prompt = f"""You are the editor checking a DRAFT of the YouTube video "{title}" before the creator watches it. Below is
exactly what the draft says (Whisper transcript), with [m:ss] time marks and || where the editor made a cut.

{" ".join(out)}

List every place a viewer would hear something broken AT OR NEAR A CUT (||):
- a sentence that starts and is abandoned, then restarted in other words (only the finished try should stay)
- the creator talking to himself, not to the viewer ("ok starting things off we do have", "hold on", "my bad", "that's so bad")
- a stub of a failed take left before or after a cut ("my goodness man | But anyways guys")
- a sentence cut off before it finishes, or a cut that joins two halves that don't make sense together
- the same point said twice in a row
Real examples he sent back (talking to himself, not to the viewer; all were left in a draft):
  "OK, starting things off we do have || So right in front of us is the box"  (setting himself up, then the real line)
  "that is so bad, man" / "bro I promise" / "my goodness, man"  (reacting to his own take)
  "Next up" said quietly to himself before the real "Next up we have..."
  "let me text someone... what time is K-Shawn's party today?"  (talking to someone in the room)
  "so here's some of the on feet" while looking away from every camera  (old footage habit)
  "perfecting the shoes is very easy" muttered before "So click the link in the description below"
  "I gotta take these off"  (narrating what he is doing, not for the viewer)
NOT problems: a natural sentence that runs across a cut, lists said as lists, his catch-phrases, the greeting / sign-off.
"sure" = you would bet a cut there is wrong. Be strict: when the text reads fine, leave it out.
Answer only JSON: {{"problems": [{{"t": "<m:ss of the cut>", "type": "self_talk|abandoned|cut_off|repeat|other", "quote": "<the words around it, max 15>", "why": "<max 15 words>", "sure": true}}]}}
"self_talk" = words meant for himself or someone in the room, not for the viewer (like the real examples above)."""
    ans = ask("draft_audit_meaning", prompt, say=lambda *a: None)
    flags = []
    for p in (ans or {}).get("problems") or []:
        try:
            mm, ss = str(p["t"]).split(":")
            t = int(mm) * 60 + float(ss)
        except Exception:  # noqa
            continue
        near = min(cuts, key=lambda c: abs(c - t)) if cuts else t
        t = near if abs(near - t) <= 6 else t
        if kept[m.piece(t)][0] < 0:
            continue
        # listen only (tested 2026-10-25): it missed bapesta 0:42, re-found what join_checks already hears, and raised 3
        # unsure flags on the approved bapesta final, so it never fails a draft on its own
        # sure self-talk IS a problem (tested 2026-10-25: 5 real ones on the lv skatesta first draft, "what time is
        # K-Shawn's party", "I gotta shoot the B-roll"...; 0 on 8 approved finals). Every other type had sure flags on
        # approved finals too, so those stay listen-only
        selftalk = str(p.get("type", "")) == "self_talk" and bool(p.get("sure"))
        flags.append({"kind": "selftalk" if selftalk else "listen", "type": str(p.get("type", "")), "sure": bool(p.get("sure")),
                      "draft": [round(t, 2)], "src": [round(m.to_src(t), 2)],
                      "phrase": str(p.get("quote", ""))[:160],
                      "why": ("reads wrong (AI sure): " if p.get("sure") else "reads wrong: ") + str(p.get("why", ""))[:120]})
    return flags


GREETINGS = ["hey guys", "what's up guys", "whats up guys", "hello youtube", "{{REVIEW_CHANNEL}} here", "{{REVIEW_CHANNEL}} here", "shift reviews here",
             "reviews here"]
SIGNOFFS = ["pretty much it for today", "that's pretty much it", "thats pretty much it", "see you guys next time",
            "see you in the next one", "catch you guys in the next",
            # the outro line after it, said twice in sp5der 6:24 ("...if you guys enjoyed and we're able to figure out")
            "able to figure out", "you guys enjoyed"]


def bookend_checks(words, total):
    """The greeting and the sign-off (study of all 294 notes, 2026-10-25: wrong in 9+ videos; "hey guys" is whitelisted in
    the repeat check because he says it on purpose, so a doubled greeting was never caught):
    greeting  a greeting said twice in the first 2 minutes, within 30 s (amiri 0:19, cartier 0:27, skatesta 0:44)
    signoff   the sign-off said twice within 60 s (sp5der 6:24, s25 7:04, watchb 10:10)
    tail      picture running on after the last word: > 2 s after "bye" (cartier 5:22, rick owens, Uber 8:58)"""
    flags = []
    text = [norm(w["w"]) for w in words]

    def hits(phrases, lo=0.0, hi=1e9):
        out = []
        for i in range(len(text)):
            if not lo <= words[i]["s"] <= hi:
                continue
            for ph in phrases:
                k = ph.split()
                if text[i:i + len(k)] == [norm(x) for x in k]:
                    out.append((words[i]["s"], ph, i))
                    break
        return out
    def twice(found, window):
        """the same phrase twice within `window` s (each phrase against itself: "hey guys, {{REVIEW_CHANNEL}} here" twice)"""
        for ph in dict.fromkeys(p for _, p, _ in found):
            ts = [t for t, p, _ in found if p == ph]
            for t1, t2 in zip(ts, ts[1:]):
                if t2 - t1 <= window:
                    return t1, t2, ph
        return None
    # a "hey guys" is a greeting take only with its intro words right after ("hey guys, {{REVIEW_CHANNEL}} here", "welcome back"),
    # not "...and today hey guys we look"
    g_hits = [h for h in hits(GREETINGS, 0, 120)
              if not h[1].endswith("guys") or {"here", "welcome", "back"} & set(text[h[2] + 2:h[2] + 7])]
    g = twice(g_hits, 30)
    if g:
        flags.append({"kind": "greeting", "draft": [round(g[0], 2), round(g[1], 2)], "phrase": g[2],
                      "why": f'greeting said twice ({g[1] - g[0]:.1f} s apart): keep only the last clean take'})
    s = twice(hits(SIGNOFFS, max(0.0, total - 120)), 60)   # the outro lives in the last 2 minutes
    if s:
        flags.append({"kind": "signoff", "draft": [round(s[0], 2), round(s[1], 2)], "phrase": s[2],
                      "why": f'sign-off said twice ({s[1] - s[0]:.1f} s apart): keep the take that runs on into the outro'})
    if words:
        last = words[-1]
        byes = [w for w in words[-8:] if norm(w["w"]) in ("bye", "peace", "byebye")]
        end = (byes[-1] if byes else last)["e"]
        limit = 2.0 if byes else 3.5
        if total - end > limit:
            flags.append({"kind": "tail", "draft": [round(end, 2)], "phrase": " ".join(w["w"] for w in words[-5:]),
                          "why": f'video runs {total - end:.1f} s after the last word'
                                 + (' ("bye"): end ~1.3 s after it with the fade' if byes else '')})
    return flags


def is_phone(project):
    """phone_edit project (Uber / DoorDash / Shein): work/cuts.json "keep" + edit/main-draft.mp4 + work/mic.wav"""
    return not (project / "work" / "timeline.json").exists() and (project / "work" / "cuts.json").exists()


def audit(project, video=None, fix=True, timeline=None, offset=0.0):
    project = Path(project)
    if is_phone(project) and not timeline:
        # phone videos (2026-10-25: Uber october had 3 cut-join notes): main-draft.mp4 = the kept pieces back to back
        video = Path(video) if video else project / "edit" / "main-draft.mp4"
        kept = [tuple(k) for k in json.loads((project / "work" / "cuts.json").read_text(encoding="utf-8"))["keep"]]
        mic = project / "work" / "mic.wav"
    else:
        video = Path(video) if video else project / "output" / "final.mp4"
        tl = json.loads(Path(timeline or project / "work" / "timeline.json").read_text(encoding="utf-8"))
        # "rendered" = what plays, in order, including inserted transitions (negative = an insert with no recording time)
        kept = [tuple(k) for k in (tl.get("rendered") or tl["kept"])]
        mic = project / "work" / "mic16k.wav"
    m = Map(kept, offset)
    words, audio = transcribe(video)
    flags, fixes = [], []
    from whisper_gpu import load
    model = load("medium.en")[0]

    def heard_twice(a0, b1, ph):
        """a back-to-back repeat must be heard again in a short re-transcription of just that moment: the full-file pass
        invented "a bunch a bunch" (watch spreadsheet 2026-10-24, draft 5:39; a 6 s window heard it once)"""
        s0 = max(0.0, a0 - 2.0)
        seg = audio[int(s0 * 16000):int((b1 + 2.0) * 16000)]
        sg = model.transcribe(seg, vad_filter=False, condition_on_previous_text=False)[0]
        txt = " " + " ".join(norm(t) for x in sg for t in x.text.split()) + " "
        return txt.count(" " + ph + " ") >= 2
    for j, i, ph in find_repeats(words):
        a, b = words[j], words[i]
        if b["s"] - a["s"] <= 8.0 and not heard_twice(a["s"], words[min(i + len(ph.split()), len(words) - 1)]["e"], ph):
            continue
        pa, pb = m.piece(a["s"]), m.piece(b["s"])
        if kept[pa][0] < 0 or kept[pb][0] < 0:
            continue   # inside an inserted transition
        # the same words in two FINISHED, different sentences of one unbroken take are speech, not a retake (bapesta dhgate
        # 2026-10-25, 3:24/3:30: "...make sure that you either save this or join the discord. It would be really appreciative
        # because I want to make sure that you actually save the most money"): same kept piece, a sentence end between the
        # tries, and the words after each try differ
        k_ = len(ph.split())
        after = lambda x: [norm(w["w"]) for w in words[x + k_:x + k_ + 3]]
        if pa == pb and any(re.search(r"[.?!]$", w["w"]) for w in words[j + k_ - 1:i]) and \
                len(set(after(j)) & set(after(i))) <= 1:
            continue
        ctx = lambda k: " ".join(x["w"] for x in words[max(0, k - 3):k + 9])
        f = {"kind": "repeat", "draft": [round(a["s"], 2), round(b["s"], 2)], "src": [round(m.to_src(a["s"]), 2), round(m.to_src(b["s"]), 2)],
             "phrase": ph, "first": ctx(j), "second": ctx(i)}
        # clear retake: the first try is the END of its kept piece, the second try OPENS a later piece, close together
        first_tail = pa < pb and b["s"] - a["s"] <= 20.0
        opens = abs((m.starts[pb] + m.offset) - b["s"]) <= 1.5
        if first_tail and opens:
            s0 = m.to_src(a["s"]) - 0.05
            # back to the start of the first try's sentence inside its piece (the words before it in the same breath)
            k = j
            while k > 0 and m.piece(words[k - 1]["s"]) == pa and words[k]["s"] - words[k - 1]["e"] < 0.5 and j - k < 12:
                k -= 1
            s0 = m.to_src(words[k]["s"]) - 0.05 if k < j else s0
            fixes.append([round(s0, 3), round(kept[pa][1], 3)])
            f["fix"] = "cut the first try (source %.1f-%.1f)" % (fixes[-1][0], fixes[-1][1])
        flags.append(f)
    # stranded scraps
    for k, (a, b) in enumerate(kept):
        before = a - kept[k - 1][1] if k else 99
        after = kept[k + 1][0] - b if k + 1 < len(kept) else 99
        if a >= 0 and b - a < 3.0 and before >= 5.0 and after >= 5.0 and 0 < k < len(kept) - 1 and kept[k - 1][0] >= 0:
            o = m.starts[k]
            said = " ".join(w["w"] for w in words if o <= w["s"] < o + (b - a))
            flags.append({"kind": "stranded", "draft": [round(o, 2)], "src": [round(a, 2), round(b, 2)], "phrase": said})
    if mic.exists():
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mic), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True).stdout
        micpcm = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768

        def heard(t0, t1):
            t0 = max(0.0, t0)
            sg = model.transcribe(micpcm[int(t0 * 16000):int(t1 * 16000)], word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False)[0]
            return [(w.word.strip(), t0 + w.start, t0 + w.end) for x in sg for w in (x.words or [])]
        # the sentence-break re-listen only on phone videos: on reviews it hid two real cut-offs (cologne "for personal use."
        # and "It's | honestly", Whisper put a full stop where he carried on)
        phone = is_phone(project) and not timeline
        flags += join_checks(kept, m, words, micpcm, heard if phone else None, phone)
    else:
        flags += join_checks(kept, m, words, None)
    # clipped ending: his MIC is still talking in the last 150 ms of the last kept piece (the draft's own audio has music)
    lvl = -99.0
    if mic.exists():
        end = [k for k in kept if k[0] >= 0][-1][1]
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, end - 0.15):.3f}", "-t", "0.15", "-i", str(mic),
                              "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
        tail = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        lvl = 20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-9) if len(tail) else -99.0
    if lvl > -32:
        flags.append({"kind": "ending", "draft": [round(len(audio) / 16000, 2)], "src": [round(end, 2)],
                      "phrase": " ".join(w["w"] for w in words[-6:]), "level": round(float(lvl), 1)})
    for f in bookend_checks(words, len(audio) / 16000):
        f["src"] = [round(m.to_src(t), 2) for t in f["draft"]]
        # the repeat check may already hold the same doubled sign-off: one flag per moment
        if not any(x["kind"] == "repeat" and abs(x["draft"][-1] - f["draft"][-1]) < 3 for x in flags):
            flags.append(f)
    if not is_phone(project) or timeline:
        # which camera is on screen, measured from the picture (shown_cam.py): flashes + back-and-forth swaps
        try:
            import shown_cam
            cam_rows, kinds = shown_cam.shown(project, video, kept, offset), shown_cam.half_kinds(project)
            flags += shown_cam.camera_checks(cam_rows, kinds)
            # he holds the product up to the camera NOT on screen and the edit never switches (MediaPipe hands, both cameras)
            flags += shown_cam.hold_checks(cam_rows, shown_cam.hand_sizes(project, kept), kinds, kept)
            # he talks into one camera and the draft shows the other (head yaw from the edit's analysis.json, no new decode)
            flags += shown_cam.facing_checks(cam_rows, shown_cam.facing(project), kinds, offset=offset, duration=m.duration)
            flags += shown_cam.showing_checks(project, video, kept, offset, words, str(project / "work" / "showing_check.png"))
        except Exception as e:  # noqa: a camera check never breaks the audit
            print(f"camera check skipped: {e}")
    flags += meaning_check(project, words, kept, m)
    if is_phone(project) and not timeline:
        # phone videos repeat lines on purpose (each method re-says "pinned comment section below") and keep short real
        # lines between big cuts; on the approved Uber october edit both checks only raised false alarms
        for f in flags:
            if f["kind"] in ("repeat", "stranded"):
                f["why"], f["kind"] = f.get("why") or f["kind"], "listen"
    return flags, fixes, words


def main():
    project = Path(sys.argv[1])
    video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    # raw/audit_cuts.json is read by the review pipeline only; phone problems go to the revision AI (server.send_audit)
    fix = "--no-fix" not in sys.argv and not is_phone(project)
    flags, fixes, words = audit(project, video, fix)
    # raw/audit_ok.json: moments a person (or the revision AI) LISTENED to and found right, [{"src": s, "kind": k, "why":
    # "..."}] in source seconds. A flag there (same kind, any of its source times within 1.5 s) is shown as "listen" and
    # no longer fails the draft (top 5 reselling products spring 2026-10-25: two different "scroll down until you get to"
    # sentences and three joins with no silence to cut on blocked every rebuild; there was no way to say "checked")
    ok_f = project / "raw" / "audit_ok.json"
    oks = json.loads(ok_f.read_text(encoding="utf-8")) if ok_f.exists() else []
    for f in flags:
        hit = next((o for o in oks if o.get("kind", f["kind"]) == f["kind"]
                    and any(abs(t - o["src"]) <= 1.5 for t in f.get("src", []))), None)
        if hit and f["kind"] != "listen":
            f["why"] = f"checked, fine: {hit.get('why', '')}" + (f"; {f['why']}" if f.get("why") else "")
            f["kind"] = "listen"
    state_f = project / "work" / "audit_state.json"
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {"rounds": 0}
    flags.sort(key=lambda f: (f["kind"] == "listen", f["draft"][0]))
    lines = [f"# Draft audit: {sum(f['kind'] != 'listen' for f in flags)} problem(s), "
             f"{sum(f['kind'] == 'listen' for f in flags)} cut(s) to listen to", "",
             "What the draft actually SAYS (medium.en), checked for retakes left in, stranded scraps, words cut off or "
             "doubled at a cut, and a clipped ending.", ""]
    for f in flags:
        lines.append(f"- **{f['kind']}** draft {', '.join(f'{int(t // 60)}:{t % 60:04.1f}' for t in f['draft'])} "
                     f"(source {', '.join(f'{int(t // 60)}:{t % 60:04.1f}' for t in f['src'])}): \"{f.get('phrase', '')}\""
                     + (f" -> {f['fix']}" if f.get("fix") else "")
                     + (f" ({f['why']})" if f.get("why") else "")
                     + (f"\n  - 1st: {f['first']}\n  - 2nd: {f['second']}" if f["kind"] == "repeat" else ""))
    try:
        from claude_brain import brain_down
        down = brain_down()
    except Exception:  # noqa
        down = None
    if down:   # the AI checks (self-talk, reading, showing camera) silently returned nothing: say so first
        lines[1:1] = ["", f"⚠️ AI CHECKS DID NOT RUN: the AI provider has refused since {down['since']} (usage limit). "
                          "Self-talk, the reading check and the AI QC were skipped on this draft; rebuild once it is back.", ""]
    out = project / "output" / "draft_audit.md"
    (project / "work").mkdir(exist_ok=True)
    (project / "work" / "draft_audit.json").write_text(json.dumps(flags, indent=1), encoding="utf-8")
    rebuilt = False
    if fix and fixes and state["rounds"] < 1:
        af = project / "raw" / "audit_cuts.json"
        old = json.loads(af.read_text(encoding="utf-8")) if af.exists() else []
        new = [x for x in fixes if x not in old]
        if new:
            af.write_text(json.dumps(old + new, indent=1), encoding="utf-8")
            state["rounds"] += 1
            state_f.write_text(json.dumps(state), encoding="utf-8")
            pid = json.loads((project / "studio.json").read_text(encoding="utf-8"))["id"]
            try:
                req = urllib.request.Request(f"http://127.0.0.1:8765/api/project/run?id={pid}", json.dumps({"action": "draft"}).encode(),
                                             {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=30).read()
                rebuilt = True
                lines.append(f"\n{len(new)} clear retake(s) cut in raw/audit_cuts.json; a rebuild was started (one round only).")
            except Exception as e:  # noqa
                lines.append(f"\nCould not start the rebuild ({e}); run the draft again.")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    real = [f for f in flags if f["kind"] != "listen"]   # "listen" = worth a look at that cut, never fails the draft
    # stop the rebuild loop: after 3 failed audits in a row on one video the draft goes to HIM with what is left listed
    # (top 5 reselling spring 2026-10-25: 20 -> 17 -> 11 -> 8 -> 2 problems over 5 rebuilds of ~55 min each; user: "it
    # keeps re-rendering, we need to make it faster"). A passing audit resets the count.
    fails = state.get("fails", 0) + 1 if real else 0
    state["fails"] = fails
    state_f.write_text(json.dumps(state), encoding="utf-8")
    if real and not rebuilt and fails > 3:
        note = (f"\nAfter {fails - 1} failed audits in a row this draft is handed to you as is: the {len(real)} problem(s) "
                f"above are left for you to judge (no more automatic rebuilds).")
        out.write_text("\n".join(lines) + "\n" + note + "\n", encoding="utf-8")
        print(note)
        return
    if real and not rebuilt:
        print(f"\nDRAFT NOT READY: {len(real)} problem(s) in what the draft says; see {out}", file=sys.stderr)
        sys.exit(2)
    if rebuilt:
        sys.exit(2)   # this draft is superseded by the rebuild: never "ready"


if __name__ == "__main__":
    main()
