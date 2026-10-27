"""Step 3: propose sections.json from the transcript (countdown cues), unless the user already saved one.
python sections.py <project> [--redo]
Sections: [["intro", s, e], ["#5 Name", s, e], ..., ["HM Name", s, e], ["#1 Name", s, e], ["outro", s, e]]
Everything outside a section is cut (the raw recording has setup, loading and dead time between realms).

Tuned on the Top 5 Realms recording (2026-10-21):
- a cue is "coming in at number N" / "at number N we have" / "the real number N"; "jump into the number N spot(s)" and
  "move on to the number one spots" are teasers, not cues
- the same rank said again later = the user re-did that entry on camera (official PvP was dropped for Anarchy Vanilla):
  the LAST one is the real section, the earlier one is kept as "? #N ..." so the user decides
- names = the capitalized words right after the cue ("we have Spectricious", "it's going to be Village City")
- the intro = the last "hello youtube / hey guys / what's up" take before the first cue, ending on "let's go / get into it"
- a rank that was never announced (#5 said as "which is going to be Dragon Forge") gets a "? #5" span between the intro
  and the next rank so nothing is silently lost
"""
import re
import sys

from glib import Project, fmt, say

P = Project(sys.argv[1])
if P.wf("sections.json").exists() and "--redo" not in sys.argv:
    say("sections.json exists (user-edited or earlier run), keeping it")
    sys.exit(0)
words = P.words
dur = P.source_info.get("duration") or (words[-1]["e"] if words else 0)
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
       "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10}
tok = [re.sub(r"[^a-z0-9'#]", "", w["w"].lower()) for w in words]
raw = [w["w"].strip(".,!?") for w in words]
NOT_NAMES = {"I", "I'm", "Minecraft", "Okay", "Thank", "You", "Pokemon", "Pokémon", "Bedrock", "Realm", "Realms", "SMP", "PvP", "So", "And", "But", "The", "This", "It", "Which", "For", "Coming", "Let's", "Now", "Hello", "YouTube"}


def known_names():
    """entry names this video can have: settings.names, else every server / realm / mod name in the add-on library
    (Whisper writes "talent MC", "Pokefine", "river network": matched letters-only and fuzzy, never by capitals)"""
    names = list(P.settings.get("names") or [])
    try:
        import json
        lib = json.loads(open(r"{{KIT}}/tools/minecraft\library.json", encoding="utf-8").read())
        for kind in ("servers", "mods", "clients"):
            names += [v.get("name") for v in (lib.get(kind) or {}).values() if isinstance(v, dict) and v.get("name")]
    except Exception:
        pass
    return [n for n in dict.fromkeys(names) if n and len(re.sub(r"[^a-z0-9]", "", n.lower())) >= 4]


KNOWN = known_names()


def known_after(i, span=22):
    """a known entry name said in the words after the cue, e.g. 'which is going to be Apple MC' -> 'AppleMC'"""
    import difflib
    flat = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in words[i:i + span]]
    best = (0.0, "")
    for n in KNOWN:
        key = re.sub(r"[^a-z0-9]", "", n.lower())
        for a in range(len(flat)):
            for b in range(a + 1, min(a + 4, len(flat)) + 1):
                r = difflib.SequenceMatcher(None, "".join(flat[a:b]), key).ratio()
                if r > best[0]:
                    best = (r, n)
    return best[1] if best[0] >= 0.8 else ""


def sentence_start(j):
    return j == 0 or words[j - 1]["w"].endswith((".", "!", "?"))


def name_after(i):
    """Capitalized words (not sentence starts) in the 12 words after the cue, e.g. 'Village City', 'Anarchy Vanilla'."""
    out = []
    for j in range(i, min(i + 14, len(words))):
        w = raw[j]
        if w and w[0].isupper() and w not in NOT_NAMES and not (sentence_start(j) and not out):
            out.append(w)
            if len(out) == 3 or words[j]["w"].endswith((".", ",", "!", "?")):
                break
        elif out:
            break
    return " ".join(out)


def phrase_at(i, phrases):
    s = " ".join(tok[i:i + 4])
    return any(s.startswith(p) for p in phrases)


cues = []   # (time, rank or "HM", name)
teasers = []   # "move on to the number seven spot": the cue when that rank is never announced for real
i = 0
while i < len(tok) - 1:
    t = tok[i]
    if t == "number" and tok[i + 1] in NUM:
        after = " ".join(tok[i + 2:i + 5])
        before = " ".join(tok[max(0, i - 4):i])
        teaser = after.startswith(("spot", "spots", "realm on", "pick")) or before.endswith(("into the", "on to the", "onto the", "to the"))
        real = any(x in before for x in ("coming in", "at number", "in at", "the real", "number", "is number")) or after.startswith(("we have", "we do", "is", "it's", "its", "which", "we got"))
        if not teaser and (real or before.endswith("the")):
            st = i   # start at "Coming in at / Next up at / At" when said just before "number N"
            for b in range(max(0, i - 5), i):
                if tok[b] in ("coming", "next", "obviously") and words[i]["s"] - words[b]["s"] < 4.0:
                    st = b
                    break
            cues.append((words[st]["s"], NUM[tok[i + 1]], known_after(i + 2) or name_after(i + 2)))
        elif teaser:   # "let's jump into number nine spots. Coming in, which is going to be River..." (Top 10 Servers)
            j = i + 2
            while j < len(words) - 1 and not words[j]["w"].endswith((".", "!", "?")) and words[j + 1]["s"] - words[j]["e"] < 1.0 and j - i < 10:
                j += 1
            teasers.append((words[min(j + 1, len(words) - 1)]["s"], NUM[tok[i + 1]], known_after(i + 2, 40) or name_after(j + 1)))
        i += 2
        continue
    if t == "honorable" and tok[i + 1].startswith("mention"):
        if not " ".join(tok[max(0, i - 3):i]).endswith(("to the", "into the", "onto the")):   # "move on to the honorable mention" = teaser
            cues.append((words[i]["s"], "HM", name_after(i + 2)))
        i += 2
        continue
    i += 1
# a rank that is only ever teased ("jump into the number eight spot ... which is going to be Apple MC") starts at the
# sentence after the tease (the tease itself closes the previous entry)
have = {r for _, r, _ in cues}
for t, rank, name in teasers:
    if rank not in have:
        cues.append((t, rank, name))
        have.add(rank)
cues.sort(key=lambda c: c[0])
# the same cue repeated within 90 s = a retake of the announcement: keep the LAST
seen = []
for t, rank, name in cues:
    if seen and seen[-1][1] == rank and t - seen[-1][0] < 90:
        seen[-1] = (t, rank, name or seen[-1][2])
    else:
        seen.append((t, rank, name))
cues = seen
# a rank said again much later = the entry was re-done on camera; the earlier span is kept but flagged with "?"
last_of = {}
for t, rank, name in cues:
    if rank != "HM":
        last_of[rank] = t
# intro: the last opener take before the first cue
OPENERS = ("hello youtube", "hey guys", "hey youtube", "whats up guys", "what's up guys", "whats up youtube", "what's up youtube", "welcome back", "hey everyone", "hello everyone")
first_cue = cues[0][0] if cues else dur
openers = [w["s"] for j, w in enumerate(words) if w["s"] < min(first_cue, dur * 0.5) and phrase_at(j, OPENERS)]
if openers:   # walk back over the same take: "Hello YouTube" 18.0 + "welcome back" 19.0 = one opener (Top 10 Servers cut "Hello")
    first = openers[-1]
    for o in reversed(openers[:-1]):
        if first - o <= 4.0:
            first = o
        else:
            break
    openers = openers[:openers.index(first)] + [first]
intro_start = max(0.0, openers[-1] - 0.3) if openers else 0.0
intro_end = None
if openers:
    j0 = next(j for j, w in enumerate(words) if w["s"] >= openers[-1])
    for j in range(j0, min(j0 + 400, len(words))):
        if words[j]["s"] - openers[-1] > 90:   # the "let's go" that ends the intro comes within ~1.5 min; later ones are setup chatter
            break
        if phrase_at(j, ("let's go", "lets go", "let's get into", "lets get into", "get started", "without further", "jump into", "let's dive", "lets dive", "let's begin", "get right into")):
            k = j
            while k < len(words) - 1 and not words[k]["w"].endswith((".", "!", "?")) and k - j < 12 and words[k + 1]["s"] - words[k]["e"] < 1.0:
                k += 1   # a pause ends the sentence too (Whisper often drops the period before a long silence)
            intro_end = min(words[k]["e"], words[k]["s"] + 1.5) + 0.2   # Whisper stretches the last word over a pause
            break
    if intro_end is None:
        intro_end = min(openers[-1] + 60, first_cue - 0.3)
# outro: the last sign-off phrase in the final 15 %
SIGN = ("wrap it up", "that's gonna be it", "thats gonna be it", "that's going to be it", "that is going to be it", "thank you for watching", "thanks for watching",
        "make sure to subscribe", "see you guys", "see you in the next", "peace out", "that's it for", "thats it for", "catch you", "until next time")
sign = [w["s"] for j, w in enumerate(words) if w["s"] > dur * 0.85 and phrase_at(j, SIGN)]
outro_start = min(sign) - 0.3 if sign else None
if outro_start is None:
    byes = [w["s"] for j, w in enumerate(words) if w["s"] > dur * 0.9 and tok[j] in ("bye", "peace")]
    outro_start = max(0.0, byes[-1] - 12) if byes else None
secs = []
if not cues:
    secs = [["main", intro_start, words[-1]["e"] + 0.5 if words else dur]]
else:
    if intro_end and intro_end - intro_start > 3:
        secs.append(["intro", round(intro_start, 2), round(min(intro_end, first_cue - 0.3), 2)])
    hm = 0
    for n, (t, rank, name) in enumerate(cues):
        nxt = cues[n + 1][0] - 0.3 if n + 1 < len(cues) else (outro_start - 0.3 if outro_start and outro_start > t else words[-1]["e"] + 0.5)
        if rank == "HM":
            hm += 1
            label = f"HM {name or hm}"
        else:
            label = f"#{rank} {name}".strip()
            if last_of.get(rank, t) > t:
                label = "? " + label + " (re-done later)"
        secs.append([label, round(t - 0.3, 2), round(nxt, 2)])
    # a rank never announced (e.g. #5 said as "which is going to be Dragon Forge"): a "?" span before the next lower rank
    ranks = sorted({r for _, r, _ in cues if r != "HM"})
    if ranks:
        top = max(ranks)
        want = top + 1
        first_rank_t = min(t for t, r, _ in cues if r != "HM")
        if (intro_end or 0) + 20 < first_rank_t - 5 and want <= 10:
            secs.append([f"? #{want} (check start)", round((intro_end or intro_start) + 0.5, 2), round(first_rank_t - 0.3, 2)])
    if outro_start and outro_start > cues[-1][0]:
        secs.append(["outro", round(outro_start, 2), round(words[-1]["e"] + 0.6, 2)])
secs.sort(key=lambda s: s[1])
P.write("sections.json", secs)
P.write("sections.auto.json", secs)
for s in secs:
    say(f"  {fmt(s[1])} - {fmt(s[2])}  {s[0]}")
say(f"{len(secs)} sections proposed (edit them in the app, then rebuild)")
