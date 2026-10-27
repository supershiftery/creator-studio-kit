"""The intro checks itself before he sees it (2026-10-23, user: "the AI watches its own intro line by line against the rules
and fixes it before I ever see it ... I want to be able to get it right the first time eventually").

    res = check(build_dir)          # -> {"problems": [...], "pins": [...], "ok": bool}; writes intro_check.json + .md

Two layers, cheapest first:
  1. measured, exact (no AI): black frames, a raw side-by-side recording on screen (the split-screen seam), judder (repeated
     frames inside a scroll), a product clip before its name is said, the same clip twice in a row, an empty slot.
  2. the eyes + brain (claude_brain task "intro_check", ~1 cent): one frame of the RENDER per shot, labelled with the words
     under it; does the shot show what he is saying, and is anything broken (wrong subject, a talking face, an empty box,
     unreadable text, a date)? Each bad shot comes back with a fix: a stock search, one of his product clips, or text only.
Every fix becomes a pin (build_intro.apply_pins) on that shot's words; review_intro.py re-renders and checks once more.
His own pins (settings.intro_pins) are never second-guessed by the brain: only measured breakage is reported on them.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import numpy as np  # noqa: E402


def _frames(path, fps=10, w=160, h=90, ss=None, t=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{ss:.2f}"] if ss else []) + ["-i", path] + (["-t", f"{t:.2f}"] if t else []) + \
          ["-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def _words(build):
    W = json.load(open(os.path.join(build, "vo-words.json"), encoding="utf-8"))
    return W if isinstance(W, list) else W.get("words", [])


def _norm(s):
    return re.sub(r"[^a-z0-9']", "", s.lower())


def _phrase(W, t0, t1=None, n=3):
    """The first n words said from t0 on (a pin's "from"/"to")."""
    ws = [w for w in W if w["s"] >= t0 - 0.12 and (t1 is None or w["s"] < t1)]
    return " ".join(_norm(w["w"]) for w in ws[:n] if _norm(w["w"])) or None


def black_frames(render, dur):
    """Stretches >= 0.2 s where the whole frame is (near) black: "it goes black, we can't do that" (lv trainer 0:18)."""
    F = _frames(render, fps=10)
    dark = [(f < 18).mean() > 0.985 and f.std() < 6 for f in F]
    out, start = [], None
    for k, d in enumerate(dark + [False]):
        t = k / 10
        if d and start is None:
            start = t
        elif not d and start is not None:
            if t - start >= 0.2 and start < dur - 0.6:   # the last half second fades out into the video on purpose
                out.append((round(start, 1), round(t, 1)))
            start = None
    return out


def seam(clip):
    """A raw 3840x1080 side-by-side recording squeezed into a slot shows two pictures with a hard vertical seam in the
    middle (lv trainer 0:13: "no one should know ever that my video is split in two")."""
    F = _frames(clip, fps=2, w=320, h=90)
    if not len(F):
        return False
    hits = 0
    for f in F:
        c = np.abs(f[:, 159] - f[:, 160]).mean()
        around = np.mean([np.abs(f[:, x] - f[:, x + 1]).mean() for x in (60, 100, 220, 260)]) + 1
        hits += c > 4 * around and c > 12
    return hits >= max(2, len(F) // 2)


def judder(clip):
    """Share of repeated frames inside motion (a scroll that goes move-stop-move: the reselling spreadsheet intro, "very shaky")."""
    import cv2
    F = _frames(clip, fps=30, w=240, h=135)
    if len(F) < 10:
        return 0.0
    d = np.array([cv2.phaseCorrelate(F[k], F[k + 1])[0][1] for k in range(len(F) - 1)])
    mv = np.abs(d) > 1.0
    dup = (np.abs(d) < 0.3) & np.r_[False, mv[:-1]] & np.r_[mv[1:], False]
    return float(dup.sum() / max(1, mv.sum())) if mv.sum() >= 8 else 0.0


def first_said(W, phrases):
    ws = [_norm(w["w"]) for w in W]
    best = None
    for ph in phrases or []:
        want = [_norm(x) for x in str(ph).split() if _norm(x)]
        for k in range(len(ws) - len(want) + 1):
            if want and ws[k:k + len(want)] == want:
                best = W[k]["s"] if best is None else min(best, W[k]["s"])
                break
    return best


LONG_HOLD = 3.5   # s: the approved intros' shots are <= ~3.1 s (studied 2026-10-24)


def _same_moment(a, b, near=2.5):
    """Two "src@t" sources show the same moment: same file, start times within `near` s."""
    if not a or not b:
        return False
    fa, _, ta = str(a).rpartition("@")
    fb, _, tb = str(b).rpartition("@")
    try:
        return os.path.normcase(fa) == os.path.normcase(fb) and abs(float(ta) - float(tb)) < near
    except ValueError:
        return a == b


def _same_page(a, b):
    """Two shots from ONE screen recording (a YouTube search scroll, a site page), at ANY moment: one use per intro
    (top 5 reselling spring 2026-10-25, again after the reselling spreadsheet: "we should not be reusing the scroll ...
    we can't keep using the same clip over and over again. That's a dead giveaway")."""
    if not all(str(x.get("tag", "")).lower().startswith("screen recording") for x in (a, b)):
        return False
    fa, fb = (str(x.get("from") or "").rpartition("@")[0] for x in (a, b))
    return bool(fa) and os.path.normcase(fa) == os.path.normcase(fb)


def _family(sl):
    """The kind of shot, for the no-3-in-a-row rule: web/screen pages, his product footage, stock, people/places, backdrop."""
    tag = str(sl.get("tag", "")).lower()
    if sl.get("backdrop"):
        return "backdrop"
    if tag.startswith(("screen", "store", "website", "web")) or "listing" in tag or "walkthrough" in tag:
        return "web page"
    if tag.startswith("product") or tag in ("hands", "unboxing"):
        return "product"
    if sl.get("full"):
        return "named"
    if tag.startswith("creator") or tag.startswith("youtube thumbnails"):
        return "creator"
    if tag.startswith("viewer comments"):
        return "comments"
    if tag.startswith("map:"):
        return "named"
    return "stock" if tag else None


NOT_NAMES = set("""you your youre you're we our they their them he she his her it its my me just like really very what when where
who why how all any every some one two three four five ten hundred thousand million first last best new old good great big
little more most much many other another because if then than there here now well also even still only never always
anyways anyway honestly literally actually basically guys let lets let's go going gonna got get make made take see look
come back down up out over into from with without for about after before not dont don't can't cant won't wont pretty
i im i'm ive i've ill i'll id i'd youtube guys okay ok so and but the a an this that these those today video videos
monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october
november december god lord bro yeah yes no dhgate dh dhk dhd dollar dollars usa us america american""".split())


def uncovered_names(I, W, build=None):
    # the lines' pictures live in pics.json (intro.json keeps only the line text/roles)
    pics = {}
    try:
        pics = json.load(open(os.path.join(build, "pics.json"), encoding="utf-8")).get("pics", {}) if build else {}
    except (OSError, ValueError):
        pass
    # the video's own product name: the title (newer builds save it) or the project folder (<project>/intro/build)
    proj = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(build)))) if build else ""
    title = " ".join([str(I.get(k) or "") for k in ("title", "sub")] + [proj]).lower()
    tw = {x for x in re.findall(r"[a-z0-9']+", title) if len(x) > 2}
    # shown ANYWHERE in the intro counts (the Cartier photo on the first line covers its second mention)
    everywhere = " ".join([str(sl.get(x, "")) for sl in I["slots"] for x in ("tag", "name", "from")] +
                          [str(p.get("label", "")) for ps in pics.values() for p in ps] +
                          [str(g.get("label", "")) for g in I.get("mg") or []]).lower()
    out, seen = [], set()
    prev_end = ""
    for k, w in enumerate(W):
        raw = str(w.get("w", "")).strip()
        word = re.sub(r"[^A-Za-z0-9'&-]", "", raw)
        starts = k == 0 or re.search(r"[.!?]$", str(W[k - 1].get("w", "")).strip())
        low = re.sub(r"'s$", "", word.lower()).strip("'")
        if not word or not word[0].isupper() or starts or len(low) < 3 or low in NOT_NAMES or low in title or low in seen:
            continue
        # part of the product's own model name ("Cartier Santos Skeleton"): next to a title word
        near = [re.sub(r"[^a-z0-9']", "", str(W[j].get("w", "")).lower()) for j in range(max(0, k - 2), min(len(W), k + 3)) if j != k]
        if any(x in tw for x in near) or low in everywhere or low.rstrip("s") in everywhere:
            continue
        t = w["s"]
        shots = [sl for sl in I["slots"] if sl["s"] - 0.4 <= t < sl["e"] + 0.4]
        li = next((j for j, ln in enumerate(I["lines"]) if ln["s"] - 0.05 <= t < ln.get("e", 1e9) + 0.05), None)
        ln = I["lines"][li] if li is not None else {}
        hay = " ".join([str(sl.get(x, "")) for sl in shots for x in ("tag", "name", "from")] +
                       [str(p.get("label", "")) + " " + str(p.get("src", "")) for p in (ln.get("pics") or pics.get(str(li)) or [])] +
                       [str(g.get("label", "")) for g in I.get("mg") or []]).lower()
        if low in hay or low.rstrip("s") in hay:
            continue
        seen.add(low)
        sl = min(shots, key=lambda x: abs(x["s"] - t)) if shots else None
        out.append({"kind": "name", "slot": sl["i"] if sl else None, "t": t,
                    "what": f"says \"{word}\" at {t:.1f} s but no shot shows {word}: show {word} itself (a photo, logo or clip)"})
    return out


def measured(build, I, W):
    """Layer 1: exact problems, each tied to a slot (or a time)."""
    render = os.path.join(build, "renders", "intro.mp4")
    probs = []
    for a, b in black_frames(render, I["dur"]):
        sl = next((s for s in I["slots"] if s["s"] <= a < s["e"]), None)
        probs.append({"kind": "black", "t": a, "e": b, "slot": sl["i"] if sl else None, "what": f"black screen {a}-{b} s"})
    prev = None
    foot = []
    try:
        foot = json.load(open(os.path.join(build, "footage.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for sl in I["slots"]:
        if not sl.get("src"):
            if not I["lines"][sl["line"]].get("type_only"):
                probs.append({"kind": "empty", "slot": sl["i"], "t": sl["s"], "what": "empty slot (placeholder box)"})
            continue
        clip = os.path.join(build, sl["src"])
        # a card template holds the clip's LAST frame (poster) after the shot: a dark one = a black card on screen
        # (asset-mix test 2026-10-25: a store-listing recording went dark in its tail, a black polaroid for ~2 s)
        poster = clip[:-4] + ".jpg"
        if os.path.exists(poster) and os.path.exists(clip):
            try:
                pb = float(_frames(poster, fps=1, w=32, h=18)[0].mean())
                cb = float(_frames(clip, fps=1, w=32, h=18, t=0.5)[0].mean())
                if cb > 80 and pb < 0.45 * cb:
                    probs.append({"kind": "black", "slot": sl["i"], "t": sl["e"], "what": f"the shot's last frame is dark (card shows a black frame after {sl['e']:.1f} s)"})
            except Exception:
                pass
        if os.path.exists(clip):
            if seam(clip):
                probs.append({"kind": "split", "slot": sl["i"], "t": sl["s"], "what": "two camera halves side by side (split screen)"})
            j = judder(clip)
            if j > 0.12:
                probs.append({"kind": "judder", "slot": sl["i"], "t": sl["s"], "what": f"shaky scroll: {j:.0%} repeated frames"})
        tag = str(sl.get("tag", ""))
        if tag.startswith("product:"):
            name = tag.split(":", 1)[1].split("(")[0].strip()
            fors = next((f.get("for") for f in foot if str(f.get("tag", "")).startswith("product:" + " " + name)), None) or [name]
            said = first_said(W, fors if isinstance(fors, list) else [fors])
            # a product shown on the line that leads into its name is fine (dhgate watchb spread 2026-10-24: the AP shot
            # 1.7 s before "APs" was "fixed" with generic shopping stock, then 9 s of a stock woman holding a card)
            if said is not None and sl["s"] < said - 2.5:
                probs.append({"kind": "early", "slot": sl["i"], "t": sl["s"],
                              "what": f"{name} shown at {sl['s']:.1f} s, before he says it ({said:.1f} s)"})
        key = (sl.get("src"), sl.get("tag"))
        if prev and key == prev and not sl.get("pinned"):
            probs.append({"kind": "repeat", "slot": sl["i"], "t": sl["s"], "what": "same clip as the shot right before it"})
        # ...and never ANYWHERE else in the intro (ultimate dhgate free reselling spreadsheet 2026-10-23: one YouTube-search
        # scroll at 2, 4 and 8 s, "we should never use the same clip twice in an intro, it wouldn't be compelling")
        # (the self-check's own swaps count too: only HIS pins may repeat; lv skatesta 2026-10-24 opened and closed on the same
        # spin because the first one was an auto pin)
        elif sl.get("from") and sl.get("pinned") != "his" and any(_same_moment(o.get("from"), sl["from"]) or _same_page(o, sl) for o in I["slots"] if o["i"] < sl["i"]):
            first = next(o for o in I["slots"] if _same_moment(o.get("from"), sl["from"]) or _same_page(o, sl))
            probs.append({"kind": "repeat", "slot": sl["i"], "t": sl["s"],
                          "what": f"same clip already shown at {first['s']:.1f} s ({sl.get('tag', '')})"})
        prev = key
        # one shot held too long reads as "lacking movement" (lv skatesta 2026-10-24: 5.9 s and 4.8 s stock shots). People /
        # places he names, his own pins and held clips may stay; the last shot runs under "let's go" by design
        last = sl["i"] == I["slots"][-1]["i"]
        if sl["e"] - sl["s"] > LONG_HOLD and not (sl.get("full") or sl.get("pinned") == "his" or last):
            probs.append({"kind": "long", "slot": sl["i"], "t": sl["s"],
                          "what": f"one shot held {sl['e'] - sl['s']:.1f} s ({sl.get('tag', '')}): cut to a second source"})
    # every NAME he says (a person, place, brand, store) gets a shot of it on its line (best sp5der hoodie 2026-10-23: "I said
    # places, Atlanta, Decatur, Dunwoody ... and Young Thug: why is Young Thug not there?"; cartier: IKEA). Names = capitalised
    # words Whisper wrote mid-sentence, minus the video's own product (its footage covers it) and everyday words.
    probs += uncovered_names(I, W, build)
    # four page / stock shots in a row read as "the same thing over and over" (dhgate jordan 3 2026-10-23: four article
    # pages in a row; canada goose 2026-10-24 draft: five screen walkthroughs 5.6-14 s). His own pins don't count.
    run = []
    for sl in I["slots"] + [None]:
        fam = _family(sl) if sl else None
        if sl and fam and run and _family(run[-1]) == fam and sl["s"] - run[-1]["e"] < 0.5:
            run.append(sl)
            continue
        mine = [x for x in run if x.get("pinned") != "his"]
        # his own product footage in a row is normal (every approved intro has 4-9); pages and stock are what repeat
        if len(run) >= 4 and len(mine) >= 2 and _family(run[0]) in ("web page", "stock"):
            probs.append({"kind": "same_kind", "slot": mine[-1]["i"], "t": run[0]["s"],
                          "what": f"{len(run)} {_family(run[0])} shots in a row ({run[0]['s']:.1f}-{run[-1]['e']:.1f} s): cut one to a different kind of shot"})
        run = [sl] if sl and fam else []
    # empty frame (dhgate coupons 2026-10-24: flat white halves, "it just wasn't exciting"); measured on the render
    if I.get("type") != "gaming" and os.path.exists(render):
        try:
            from intro_score import score
            m = score(render, W[-1]["e"] if W else None)["metrics"]
            if m.get("empty_frames", 0) > 0.25:   # half-empty frames: coupons 31% (boring), approved <= 2%
                probs.append({"kind": "blank", "slot": None, "t": m.get("emptiest_at"),
                              "what": f"{m['empty_frames']:.0%} of frames are more than half empty background (worst at {m['emptiest_at']} s): fill the frame"})
        except Exception as ex:   # the scorecard must never stop the check
            print("intro_score failed:", ex, file=sys.stderr)
    # source MIX (2026-10-25, "some intros just fall short ... we need different assets ... TikToks, articles, YouTube videos,
    # stock"): his "perfect" reselling spreadsheet intro = 4 kinds of source and 22% his own product footage; the "decent" ones
    # sit at 2 kinds and 70-100% product (s25 ultra: 9/9 shots the phone). Warning only (INTRO_RULES.md asset mix).
    if I.get("type") != "gaming":
        S = [sl for sl in I["slots"] if sl.get("src")]
        dur = sum(sl["e"] - sl["s"] for sl in S) or 1
        kinds = {_family(sl) for sl in S} - {None, "backdrop"}
        own = sum(sl["e"] - sl["s"] for sl in S if _family(sl) == "product") / dur
        if len(S) >= 6 and (len(kinds) < 3 or own > 0.6):
            probs.append({"kind": "mix", "slot": None, "t": 0,
                          "what": f"only {len(kinds)} kinds of source ({', '.join(sorted(kinds))}), {own:.0%} his product footage: bring in outside "
                                  f"assets (creator clips, a real page/article, real photos of names, stock that acts out a line); target 4+ kinds, product <= 50%"})
    # a website he NAMES must be on screen on its line (reselling spreadsheet 2026-10-23: "Alibaba links" over a YouTube
    # search; named_sites.json). Reported, not pinned: the page needs a recording (screenrec.py --verify for walled sites).
    try:
        reg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "named_sites.json"), encoding="utf-8"))["sites"]
    except (OSError, ValueError, KeyError):
        reg = {}
    for li, ln in enumerate(I["lines"]):
        low = (ln.get("text") or "").lower()
        for key, s in reg.items():
            names = [key, (s.get("name") or "").lower()] + s["aliases"]
            if not any(n and re.search(r"\b" + re.escape(n) + r"\b", low) for n in names):
                continue
            shots = [sl for sl in I["slots"] if sl["line"] == li]
            if not any(str(sl.get("tag", "")).startswith(f"screen recording: {key} ") for sl in shots):
                probs.append({"kind": "site", "slot": shots[0]["i"] if shots else None, "t": ln["s"],
                              "what": f"names {s.get('name') or key} at {ln['s']:.1f} s but doesn't show the site "
                                      f"(record it: screenrec.py --verify <page>)"})
    return probs


def eyes(build, I, W, probs, say):
    """Layer 2: one frame of the render per shot, judged against the words under it."""
    from claude_brain import ask, contact_sheet
    render = os.path.join(build, "renders", "intro.mp4")
    cells, rows = [], []
    for sl in I["slots"]:
        if sl["e"] - sl["s"] < 0.4:
            continue
        t = (sl["s"] + sl["e"]) / 2
        said = " ".join(w["w"] for w in W if sl["s"] - 0.1 <= w["s"] < sl["e"])
        cells.append((render, t, f"#{sl['i']} {sl['s']:.1f}-{sl['e']:.1f}s"))
        rows.append(f"#{sl['i']} {sl['s']:.1f}-{sl['e']:.1f} s | he says: \"{said}\" | clip: {sl.get('tag', '')}"
                    + (" | HIS OWN PICK (do not replace)" if sl.get("pinned") == "his" else "")
                    + (" | PLANNED for the named thing (only bad if broken)" if _planned(sl) else ""))
    if not cells:
        return []
    sheet = os.path.join(build, "intro_check_sheet.png")
    contact_sheet(cells, sheet, cols=4, w=360)
    found = "\n".join(f"- shot #{p['slot']}: {p['what']}" for p in probs if p.get("slot") is not None and p["kind"] != "long") or "- none"   # long holds: build_intro splits them
    proj = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(build))))
    topic = str(I.get("title") or proj)
    prompt = f"""You check a {I.get('type', 'review')} video intro BEFORE the creator sees it. Each cell of the attached sheet is one
frame from the middle of one shot of the rendered intro (motion graphics over clips). Under each shot, this is what he says:
{chr(10).join(rows)}

THE VIDEO IS ABOUT: "{topic}". Read every word in that sense: the product words mean THIS product, never a place, a person
or another thing with the same name. Wrong subject (2026-10-25, he had to send all of these back):
- "cologne" = the fragrance bottle, NEVER the German city or a river; "glasses" in a sunglasses review = THOSE sunglasses,
  never his everyday glasses; "Bape hoodie" = a Bape hoodie, never another brand's hoodie (Sp5der);
- a named product must be that exact product: Dior Sauvage (dark bottle) is NOT Eau Sauvage (clear bottle);
- a site or app he names (Uber Eats) is never a dashboard / notes / spreadsheet / survey page (Notion, Docs, Sheets);
- a random stock person (cooking, typing) for something he owns or orders is wrong: it must show THAT item or app.
Also bad (top 5 reselling spring 2026-10-25, "worse than all the other ones"):
- his face covered or awkward: rubbing his eyes, a box or hand in front of his face, mid-sneeze or mid-blink = bad;
- a money / profit / income line ("making $10,000", "turn a profit", "make money") over anything that is not money, a
  payout, a sales page or a price = wrong subject (use cash, a payout screen, a sold listing);
- "the top N items / products" over one random item: it must show the products of the video together or in quick turn;
- his empty desk, a blank background or text alone on a payoff line ("let's go", the title line) = boring.
- the FIRST line (the hook, first ~3 s) over the template's smoke / empty background or a bare microphone = bad: the
  hook needs real footage of what he says ("reselling is still booming" = resellers at a meetup / sneaker con, a crowd
  trading; reselling spring 2026-10-25: "2 seconds in doesn't have anything relevant ... just a microphone").

The measuring tools already found these problems:
{found}

A clip of a product he compares to (his iPhone) MAY start on the clause leading to its name ("and trust me after reviewing
the" -> iPhone): that is intended, not "too early" (s25 ultra 2026-10-23, he asked for it).
For every shot decide: does a viewer who hears those words see something that fits (literal beats clever), and is the frame
clean? Bad = wrong subject for the words, a product before he names it, a person talking with no sound, an empty/placeholder
box, a black or blank frame, two video halves side by side, unreadable mush, a date or year on screen, an ugly or confusing
picture. Every shot listed under "measuring tools" is bad. Shots marked HIS OWN PICK are only bad for measured breakage.
For each bad shot give ONE fix: {{"stock": "<2-4 word Mixkit search for a real video of what he says>"}} or
{{"product": "<product phrase he says, e.g. spider hoodies>"}} or {{"type": true}} (text only: ONLY for abstract words on a
shot that is not broken). A broken shot, a measured problem or a product shown too early ALWAYS gets a stock or product fix
(for "too early": what he says at that moment, e.g. "their quality" -> "hoodie fabric close up").
List ONLY the bad shots, no reasoning outside the JSON, max 25 words per "why". Answer exactly:
{{"bad": [{{"n": <shot number>, "why": "<short>", "fix": {{...}}}}], "summary": "<one line>"}}"""
    ans = ask("intro_check", prompt, images=[sheet], say=say)
    if not ans:
        return []
    return [b for b in (ans.get("bad") or [s for s in ans.get("shots", []) if not s.get("ok")]) if isinstance(b, dict)]


def _planned(sl):
    tag = str(sl.get("tag", ""))
    return tag in ("electronics factory", "factory production line", "warehouse boxes") or         (tag.startswith("product:") and sl.get("pinned") != "auto")


def check(build, say=print, use_ai=True):
    I = json.load(open(os.path.join(build, "intro.json"), encoding="utf-8"))
    W = _words(build)
    probs = measured(build, I, W)
    bad = eyes(build, I, W, probs, say) if use_ai else []
    by = {s["i"]: s for s in I["slots"]}
    pins, seen = [], set()
    for b in bad:
        sl = by.get(b.get("n"))
        fix = b.get("fix") or {}
        if not sl or sl["i"] in seen or not fix:
            continue
        if sl.get("pinned") == "his" and not any(p.get("slot") == sl["i"] for p in probs):
            continue   # his own pick, nothing measured wrong with it
        nxt = next((s for s in I["slots"] if s["s"] >= sl["e"] - 0.05 and s["i"] != sl["i"]), None)
        frm = _phrase(W, sl["s"], sl["e"])
        if not frm:
            continue
        # "at": where the shot is, so the fix lands on THIS "it's no secret", not the first one in the VO (dhgate watchb
        # spread 2026-10-24: a fix for the 6.9 s shot matched 0.0 s and put 8.6 s of stock over the opening)
        pin = {"from": frm, "auto": b.get("why", "")[:80], "at": round(float(sl["s"]), 2)}
        to = _phrase(W, sl["e"], None, n=2)
        if to and nxt:
            pin["to"] = to
        if fix.get("stock"):
            pin["stock"] = str(fix["stock"])[:60]
        elif fix.get("product"):
            pin["product"] = str(fix["product"])[:40]
        elif fix.get("type"):
            continue   # text-only needs the director; reported, not pinned
        else:
            continue
        pins.append(pin)
        seen.add(sl["i"])
    # half-empty frames are a WARNING only: his own approved Amazon intro (RKImkJFJwe4, {{PHONE_CHANNEL}}) is 50% big words on
    # a plain textured background. Reported in intro_check.md, never a failure on its own
    res = {"ok": not [p for p in probs if p["kind"] not in ("blank", "mix")] and not bad, "problems": probs, "ai_bad": bad, "pins": pins}
    json.dump(res, open(os.path.join(build, "intro_check.json"), "w", encoding="utf-8"), indent=1)
    lines = ["# Intro self-check", ""] + [f"- {'warning' if p['kind'] in ('blank', 'mix') else 'measured'}: {p['what']} (shot #{p.get('slot')})" for p in probs] + \
            [f"- AI: shot #{b.get('n')}: {b.get('why')} -> {b.get('fix')}" for b in bad] + \
            [f"- fix pinned: from \"{p['from']}\" -> {p.get('stock') or p.get('product')}" for p in pins]
    if res["ok"]:
        lines.append("- every shot fits its words, nothing broken")
    open(os.path.join(build, "intro_check.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    say(f"intro check: {len(probs)} measured, {len(bad)} AI-flagged, {len(pins)} fixes pinned")
    return res


if __name__ == "__main__":
    r = check(sys.argv[1], use_ai="--no-ai" not in sys.argv)
    print(json.dumps({k: r[k] for k in ("problems", "ai_bad", "pins")}, indent=1))
