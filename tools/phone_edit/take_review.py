"""Take review: Claude reads the KEPT transcript (after take_cuts' automatic rules) and marks what word rules cannot see:
a section the user abandoned and redid in different words, a stray word left at a join, a line that is not part of the
video. Each mark becomes an exact cut placed on measured audio quiet at a sentence boundary, so the join sounds natural.
(User 2026-10-21, Doordash: the DashPass section, a failed cart attempt and a repeated "only downside" were redos in
different words; word overlap found 2 of 5 with 6 false hits.)

Usage: python take_review.py <project> [intro_len]     -> work/review_cuts.json (+ work/review.json: the raw answer, cached)
The gaming ({{STUDIO_NAME}} app\\gaming\\cuts.py) and product review (edit_review.py) trimmers call review() with
kind="gaming" / "review" and their own words / keep / audio (user 2026-10-21: same trimmer for all three video types).
Runs through the Claude Code CLI (the user's subscription, like the dashboard's Ask Claude tab), about one message a video.
"""
import hashlib, json, os, re, subprocess, sys
import numpy as np

CLAUDE = os.path.expanduser("~/.local/bin/claude.exe")
MODEL = "claude-opus-5-5"
LESSONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_lessons.md")

KINDS = {
    "phone": ("a YouTube tutorial (the creator, {{PHONE_CHANNEL}}, explains app promo codes / money methods while showing their "
              "phone or a website)", ""),
    "gaming": ("a Minecraft YouTube video ({{GAMING_CHANNEL}}: top 5 / top 10 realms, servers or add-ons, or one mod showcase) recorded "
               "while playing, webcam in the corner",
               "This is a GAMING video: reactions to what happens in the game, talking to players in chat, laughing, short "
               "exclamations and commentary while exploring are PART of the video, keep them. Never cut a rank announcement "
               "(\"coming in at number 3\", \"honorable mention\"), a realm / server code or IP, or the sign-off. A rank announced "
               "twice is already handled; only cut talk that is clearly abandoned and redone, or clearly not for the viewer "
               "(talking to someone in the room, setup trouble, notes to the editor).\n"),
    "review": ("a product review ({{REVIEW_CHANNEL}}: a DHgate / reseller product, unboxed and tried on, two cameras)",
               "This is a PRODUCT REVIEW: trying the item on, showing details close up and reacting to them is PART of the "
               "video, keep it. Never cut the price, where to buy it, the link / discount mention, the verdict or the "
               "sign-off.\n"),
    # haul (2026-10-23): one long phone recording, products shown back to back, no separate intro VO
    "haul": ("a HAUL video ({{REVIEW_CHANNEL}}: one long phone recording showing a pile of products he bought, one after another)",
             "This is a HAUL: showing each product, turning it over, reading tags and sizes, reacting to it and giving the "
             "price / where it came from are PART of the video, keep them. Never cut the greeting (\"hey guys\"), the haul "
             "total (weight, price, shipping), a product's first mention, or the outro and sign-off (\"anyways guys that's "
             "pretty much it ... peace\"). Only cut talk that is abandoned and redone, or clearly not for the viewer.\n"),
    # short (2026-10-23): a raw vertical recording edited as its own YouTube Short / TikTok, talking head first
    "short": ("a vertical SHORT (YouTube Shorts / TikTok, under a minute or so: the creator talks straight to the phone camera)",
              "This is a SHORT: every second has to earn its place, so cut harder than in a long video: false starts, a point "
              "said twice (keep the better one, usually the last), throat-clearing openers (\"so um basically\", \"okay so\") "
              "before the real first sentence. Never cut the HOOK (the first real sentence that makes the claim or asks the "
              "question), the payoff / punchline, a number or name the point depends on, or the closing line / call to action.\n"),
}

PROMPT = """You are reviewing the transcript of KIND_HERE. It was recorded in one long take; automatic rules already removed exact \
retakes, mumbling and pauses. Below is what is KEPT, one sentence per line: id, draft time, text. "[cut N s]" marks a join \
where material was already removed (for a review it may quote the last words said inside the cut: read them, a reset like "wait, these are the wrong shoes" means the part BEFORE that cut was the wrong take).

Find what still makes the video sound wrong, and nothing else:
1. ABANDONED + REDONE: the creator starts a line or a whole section, gives up (it did not work on the phone, they lost the \
thread, they said it wrong) and later says it again, often in different words. Keep the LAST version; cut from the first \
sentence of the abandoned try up to the first sentence of the redo. Typical signs: the same point made twice within a minute \
or so, a section re-introduced ("another way to save money is..." twice), a failed demo ("I already have this cart filled" \
then later "I'm going to make my cart real quick"). Once the first try is gone, the redo must not point back at it: \
"This is gonna be the real number 3", "let's try that again", "this time it worked", "okay so again" -> start the kept part \
AFTER that reference with to_text (or drop the words with a "words" entry), so the viewer never hears about a try they did \
not see (Top 5 Realms test 2026-10-21 kept "the real number 3" after cutting the abandoned #3).
2. STRAY WORDS at a join that break the sentence ("...you're not utilizing. to head over to the tab" -> drop "to"), or a \
fragment that never finishes ("One of the" then a different sentence).
3. NOT PART OF THE VIDEO: talking to someone else or to themself, notes to the editor ("blur that", "cut it", "run it back"), \
reactions to a problem with the setup, anything they would obviously not publish. Lines marked [not facing a camera] were \
said while no camera saw the creator's face. Such a line that only comments to themself, mumbled, often repeated ("So yeah, \
these are comfortable. I like these. I like these.") is self-talk: cut it. So is a short line announcing footage while \
not facing a camera ("Here's some of the on feet" at the desk: a note to themself while filming, there is no such clip; \
dhgate yeezy slides 2026-10-23, round 2: "that's not part of the video ... just me talking to myself"). Keep a \
[not facing a camera] line only when it carries real content for the viewer (a fact, the verdict, the price, a size tip).

KIND_RULES_HERE
Real examples from this creator's earlier app videos (their own review notes; same person on every channel), so you know \
their habits:
- "So this is why I don't really use DoorDash as much anymore, and another way that you can get cheap DoorDash is going \
to be by using the DashPass. This is pretty much your subscription service... HBO Max..." then later "Another way to save \
money on DoorDash is to go ahead and get the DashPass." -> keep "...as much anymore," and cut from "and another way" up to \
the later "Another way to save money" (a cut can start INSIDE a sentence, see from_text).
- "Once you're signed up, what's your signed up? All you got to do is go over to the phone" right before an unrelated \
join -> an abandoned line that leads nowhere: cut it.
- "The only downside with this is that they have a five dollar minimum cash out..." then "I cannot show that" (something \
private popped up) then "the only downside with this app is..." -> cut from the FIRST "The only downside" to the second.
- "One of the things that I do like about Eureka is they give you a free gift card" then "One thing that I do like about \
Eureka is they have a bunch of cash out methods" -> a redo: cut the first. A join that leaves "One of the" dangling is wrong.
- "...that you're probably not utilizing. to head over to the far right tab" -> drop the stray "to".

LESSONS_HERE
Rules: never cut a sentence that carries information found nowhere else. Keep the sentence on each side of a cut whole \
and grammatical. Prefer the later take. If unsure, leave it. Do NOT cut normal transitions, intros, the outro or \
call-to-actions.

Answer with ONLY a JSON object, no prose:
{"cuts": [{"from": "S12", "from_text": "and another way", "to": "S15", "to_text": "", "why": "short reason"}],
 "words": [{"sid": "S20", "drop": "to", "why": "short reason"}]}
"from" = sentence where the cut starts, "to" = sentence where what is KEPT resumes (after "from"). "from_text" (optional) = \
the exact words inside "from" where the cut starts (empty = the start of the sentence). "to_text" (optional) = the exact \
words inside "to" where the kept part starts (empty = its start). "words" removes the given word(s) from the START of that \
sentence only.

TRANSCRIPT
"""


def load_audio_env(work, audio=None):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", audio or os.path.join(work, "mic.wav"), "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    env = np.sqrt((a[:len(a) // 160 * 160].reshape(-1, 160) ** 2).mean(axis=1))  # 10 ms
    thr = max(float(np.percentile(env, 5)) * 3, 10 ** (-45 / 20))
    return env, thr


def edge(env, thr, lo, hi, prefer="late"):
    """a cut point between lo and hi (s): the middle of the longest quiet run, else the quietest 10 ms"""
    i0, i1 = int(lo * 100), max(int(lo * 100) + 1, int(hi * 100))
    seg = env[i0:i1]
    q = seg < thr
    best, cur, start = (0, None), 0, None
    for k, v in enumerate(q):
        if v:
            start = k if cur == 0 else start
            cur += 1
            if cur >= best[0]:
                best = (cur, start)
        else:
            cur = 0
    if best[0] >= 3:
        return (i0 + best[1] + best[0] // 2) / 100
    return (i0 + int(np.argmin(seg))) / 100 if len(seg) else lo


def kept_sentences(words, keep):
    mid = lambda w: (w["s"] + w["e"]) / 2
    kw, acc, joins = [], 0.0, set()
    for n, (s, e) in enumerate(keep):
        first = True
        for w in words:
            if s - 0.05 <= mid(w) < e:
                kw.append(dict(w, o=acc + mid(w) - s, piece=n, join=first and n > 0, cutlen=(s - keep[n - 1][1]) if n else 0))
                first = False
        acc += e - s
    sents, cur = [], []
    for i, w in enumerate(kw):
        if w["join"] and cur:
            sents.append(cur)
            cur = []
        cur.append(i)
        nx = kw[i + 1] if i + 1 < len(kw) else None
        if w["w"][-1:] in ".?!" or nx is None or nx["s"] - w["e"] >= 0.7:
            sents.append(cur)
            cur = []
    return kw, sents


def _covered(s, e, ranges):
    return sum(max(0.0, min(e, b) - max(s, a)) for a, b in ranges) / max(e - s, 1e-6)


def transcript_lines(kw, sents, intro_len, away=None, words=None, said_min=8.0, said_words=22):
    """away = source [s, e] ranges where no camera sees the creator's face: a sentence >= 70 % inside one is
    marked [not facing a camera], so self-talk can be told from a line to the viewer.
    words (review kind) = the whole transcript: a cut >= said_min s shows the last words said INSIDE it, so a reset that
    explains a wrong take ("wait, those aren't LV skates ... they're like cheap quality, hold on", lv skatesta 2026-10-24)
    tells the review that the walkthrough BEFORE the cut was the wrong take and the one after it is the redo."""
    lines = []
    for k, ix in enumerate(sents):
        w0 = kw[ix[0]]
        if w0["join"]:
            said = ""
            if words and w0["cutlen"] >= said_min:
                c0, c1 = w0["s"] - w0["cutlen"], w0["s"] - 0.05
                inside = [w["w"] for w in words if c0 + 0.05 <= w["s"] and w["e"] <= c1]
                if inside:
                    said = "; said in the cut: \"" + ("... " if len(inside) > said_words else "") + " ".join(inside[-said_words:]) + "\""
            lines.append(f"[cut {w0['cutlen']:.0f} s{said}]")
        t = w0["o"] + intro_len
        mark = " [not facing a camera]" if away and _covered(w0["s"], kw[ix[-1]]["e"], away) >= 0.7 else ""
        lines.append(f"S{k} {int(t // 60)}:{t % 60:04.1f} " + " ".join(kw[i]["w"] for i in ix) + mark)
    return "\n".join(lines)


def claude_exe():
    """the Claude Code CLI wherever it is installed, or None. The laptop has none at ~/.local/bin (remote test prada
    2026-10-26: WinError 2, the take review never ran and five bad takes reached the draft)."""
    import shutil
    for c in (os.environ.get("CLAUDE_EXE"), CLAUDE, os.path.expanduser("~/.local/bin/claude"),
              os.path.expandvars(r"%APPDATA%\npm\claude.cmd")):
        if c and os.path.exists(c):
            return c
    return shutil.which("claude")


def ask_claude(prompt, cwd):
    """Opus via the CLI, the prompt on STDIN (it was a command-line argument: long recordings broke Windows' 32k command
    line, "[WinError 206] The filename or extension is too long", and airpod maxes / $30k reselling / top 5 reselling
    spring 2026-10-25/26 went out with NO take review). Anything short of a real answer (CLI missing, not logged in, out of
    quota, an answer without "cuts", which used to pass as 0 cuts) goes to the brain chain IN THE SAME BUILD (Claude
    stream-json, then Claude) instead of failing it. Only when nothing answers does it raise (= BUILD STOPPED)."""
    exe = claude_exe()
    if exe:
        try:
            r = subprocess.run([exe, "-p", "--model", MODEL, "--output-format", "json", "--allowedTools", "", "--tools", "", "--setting-sources", "",
                                "--strict-mcp-config", "--disable-slash-commands"], input=prompt,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, cwd=cwd)
            j = json.loads(r.stdout or "{}")
            res = j.get("result") or ""
            m = re.search(r"\{.*\}", res, re.S)
            ans = json.loads(m.group(0)) if m else None
            if isinstance(ans, dict) and "cuts" in ans and not j.get("is_error"):
                return ans, j.get("total_cost_usd")
            print(f"take review: Claude CLI gave no usable answer ({(res or r.stderr or '')[-160:]!r}); asking the brain chain", flush=True)
        except Exception as e:  # noqa: any CLI trouble = the brain chain answers
            print(f"take review: Claude CLI failed ({type(e).__name__}: {str(e)[:160]}); asking the brain chain", flush=True)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import claude_brain
    ans = claude_brain.ask("take_review", prompt, model="opus", timeout=900)
    if not isinstance(ans, dict) or "cuts" not in ans:
        raise RuntimeError("the take review got no answer from Claude (CLI or brain) nor Claude")
    return ans, None


def lessons(kind="phone"):
    """review notes the user gave on earlier drafts, kept as examples for the next review (revise.py appends here).
    Every kind reads the phone notes (they are about how this creator talks); gaming / review add their own file."""
    out = []
    for f in [LESSONS] + ([LESSONS.replace(".md", f"_{kind}.md")] if kind != "phone" else []):
        if os.path.exists(f):
            out.append(open(f, encoding="utf-8").read().strip())
    return "\n".join(x for x in out if x)


def to_cuts(kw, sents, ans, env, thr, label):
    """Claude's sentence-level marks -> exact cuts on measured quiet ("user note" = take_cuts keeps the edges as is)"""
    sid = lambda s: int(re.sub(r"[^0-9]", "", str(s)) or -1)

    def find_in(ix, text):
        toks = [t for t in (re.sub(r"[^a-z0-9$']", "", x.lower()) for x in str(text or "").split()) if t]
        if not toks:
            return ix[0]
        ws = [re.sub(r"[^a-z0-9$']", "", kw[i]["w"].lower()) for i in ix]
        for p in range(len(ix)):
            if ws[p:p + len(toks)] == toks:
                return ix[p]
        return ix[0]

    def cut_point(i):
        cur, prev = kw[i], kw[i - 1] if i else None
        lo = prev["e"] if prev and prev["piece"] == cur["piece"] else cur["s"] - 0.4
        t = edge(env, thr, lo, cur["s"] + 0.05)
        if env[min(len(env) - 1, int(t * 100))] >= thr:
            # still on sound: Whisper put the word start early (Shein 0:55, "description below, | but": "but" was stamped
            # 351.04, really 351.55, and the cut clipped "below"). Look further, into the stamped word, for the real quiet
            t = edge(env, thr, lo, min(cur["e"], cur["s"] + 0.6))
        return t

    out = []
    for c in ans.get("cuts", []):
        a, b = sid(c.get("from")), sid(c.get("to"))
        if not (0 <= a <= b <= len(sents)):
            continue
        i0 = find_in(sents[a], c.get("from_text"))
        if b < len(sents):
            i1 = find_in(sents[b], c.get("to_text"))
            if i1 <= i0:
                continue
            e = cut_point(i1)
        else:
            i1, e = len(kw), kw[-1]["e"] + 0.3
        out.append({"s": round(cut_point(i0), 3), "e": round(e, 3), "why": f"user note ({label}): {c.get('why', '')}"[:200],
                    "text": " ".join(kw[i]["w"] for i in range(i0, i1))[:300]})
    for d in ans.get("words", []):
        k = sid(d.get("sid"))
        if not 0 <= k < len(sents):
            continue
        n, ix = len(str(d.get("drop", "")).split()), sents[k]
        if n < 1 or n >= len(ix):
            continue
        out.append({"s": round(kw[ix[0]]["s"] - 0.03, 3), "e": round(edge(env, thr, kw[ix[n - 1]]["e"] - 0.1, kw[ix[n]]["s"] + 0.08), 3),
                    "why": f"user note ({label}): drop '{d.get('drop')}' ({d.get('why', '')})"[:200]})
    return out


BROKEN_RE = re.compile(r"broken|lost in the cut|got cut|cut off|was cut|missing|dangl", re.I)


def restore_broken(out, words, keep, label="take review"):
    """A join the review calls BROKEN because an earlier cut took the end of a sentence ("'do not | But I actually got
    lucky' is broken; the 'come with a box' part was lost in the cut") is mended by putting back the words that finish the
    sentence, not by cutting the whole sentence (balenciaga track led review 2026-10-26: the published edit keeps
    "...do not actually come with a box, but I actually got lucky with this seller"; the draft lost 5 s and the point).
    The first <= 10 cut words up to a comma / full stop come back as a protect; the review's cut is dropped."""
    res = []
    for c in out:
        if not BROKEN_RE.search(c.get("why", "")) or "protect" in c:
            res.append(c)
            continue
        fixed = False
        for n in range(1, len(keep)):
            pe, ns = keep[n - 1][1], keep[n][0]
            if not (c["s"] < pe and ns <= c["e"] + 0.5 and ns - pe > 0.3):
                continue
            gone = [w for w in words if pe - 0.05 <= w["s"] < ns]
            j = next((k for k, w in enumerate(gone[:10]) if re.search(r"[,.!?]$", w["w"])), None)
            if j is None:
                break
            a, b = gone[0]["s"] - 0.02, gone[j]["e"] + 0.12
            res.append({"s": round(a, 3), "e": round(a, 3), "protect": [round(a, 3), round(b, 3)],
                        "why": f"user note ({label}): restored '{' '.join(w['w'] for w in gone[:j + 1])}' to mend a broken join"[:200]})
            # the rest of the stumble still goes: the cut now starts right after the restored words (the first fix dropped
            # it and "but yeah box," came back, balenciaga 1:51)
            if c["e"] - b > 0.3:
                res.append(dict(c, s=round(b, 3), why=(c["why"] + " (shrunk after the restored words)")[:200]))
            fixed = True
            break
        if not fixed:
            res.append(c)
    return res


def review(project, intro_len=0.0, kind="phone", work=None, words=None, keep=None, audio=None, away=None):
    """kind = phone | gaming | review. work = where review.json / review_cuts.json go; words = list or path
    (default work/words.json); keep = kept [s, e] ranges (default work/cuts.json "keep"); audio = mic track for the edges."""
    work = work or os.path.join(project, "work")
    # FROZEN after the first draft (user 2026-10-22: faster, steadier revisions). The user reviews draft 1 with these cuts
    # in it; later builds must only change what their notes say. Re-asking on every revision cost 30-60 s and chose
    # differently each time (an abandoned take came back in Top 10 Servers). The cuts are raw-recording times, so they stay
    # valid; the user's protect notes still win over them. TAKE_REVIEW=fresh (Studio settings.take_review = "fresh") re-asks.
    frozen = os.path.join(work, "review_cuts.json")
    if os.environ.get("TAKE_REVIEW", "freeze") != "fresh" and os.path.exists(frozen) and os.path.exists(os.path.join(work, "review.json")):
        out = json.load(open(frozen, encoding="utf-8"))
        print(f"take review: frozen after the first draft, reusing {len(out)} cuts (settings.take_review = \"fresh\" re-asks)")
        try:   # a broken-join cut frozen before restore_broken existed is mended now (same answer, better fix)
            w0 = words if isinstance(words, list) else json.load(open(words or os.path.join(work, "words.json"), encoding="utf-8"))
            w0 = w0.get("words", w0) if isinstance(w0, dict) else w0
            k0 = keep if keep is not None else json.load(open(os.path.join(work, "cuts.json")))["keep"]
            mended = restore_broken(out, w0, k0)
            if mended != out:
                json.dump(mended, open(frozen, "w"), indent=1)
                print("take review: mended a broken join by restoring words instead of cutting the sentence")
            out = mended
        except Exception as e:  # noqa: the frozen cuts still apply
            print(f"take review: restore check skipped ({type(e).__name__})")
        return out
    if not isinstance(words, list):
        words = json.load(open(words or os.path.join(work, "words.json"), encoding="utf-8"))
    if keep is None:
        keep = json.load(open(os.path.join(work, "cuts.json")))["keep"]
    kw, sents = kept_sentences(words, keep)
    text = transcript_lines(kw, sents, intro_len, away,   # away: no face on any camera (review kind)
                            words if kind == "review" else None)   # review: what he says inside a long cut
    les = lessons(kind)
    what, rules = KINDS[kind]
    prompt = (PROMPT.replace("KIND_HERE", what).replace("KIND_RULES_HERE", rules)
              .replace("LESSONS_HERE", ("More of their notes on later drafts:\n" + les + "\n") if les else "") + text)
    key = hashlib.sha1(prompt.encode()).hexdigest()
    cache = os.path.join(work, "review.json")
    old = json.load(open(cache)) if os.path.exists(cache) else {}
    if old.get("key") == key:
        ans = old["answer"]
    else:
        ans, cost = ask_claude(prompt, work)
        json.dump({"key": key, "answer": ans, "cost": cost}, open(cache, "w"), indent=1)
    env, thr = load_audio_env(work, audio)
    out = to_cuts(kw, sents, ans, env, thr, "take review")
    out = restore_broken(out, words, keep)
    json.dump(out, open(os.path.join(work, "review_cuts.json"), "w"), indent=1)
    print(f"take review: {len(ans.get('cuts', []))} sections, {len(ans.get('words', []))} stray words -> work/review_cuts.json")
    for c in out:
        print(f"  {c['s']:8.2f}-{c['e']:8.2f}  {c['why'][:90]}")
    return out


if __name__ == "__main__":
    review(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
