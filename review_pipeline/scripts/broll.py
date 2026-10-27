"""B-roll: find the moments worth covering, write the shot list to ask for, and place the clips I send.

Clips are always silent (their audio is never used), are sped up or slowed to fit the moment, get a light
grade and a slow push-in, and play full screen (the face circle is hidden while they're up)."""
import json, os, re, shutil, subprocess, tempfile
from pathlib import Path


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _sentences(words, a, b):
    out, cur = [], []
    for w in words:
        if w["s"] < a or w["s"] >= b:
            continue
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _segments(words, a, b, bc):
    """Split the review into the pairs/products I talk about. Returns [(start, end, label_colour)]."""
    trans = [t.split() for t in bc["product_transitions"]]
    cuts = [a]
    for i, w in enumerate(words):
        if not (a + 5 < w["s"] < b - 5):
            continue
        for t in trans:
            if [_norm(x["w"]) for x in words[i:i + len(t)]] == t and w["s"] - cuts[-1] > 20:
                cuts.append(w["s"])
                break
    cuts.append(b)
    # a re-said transition ("let's check out the higher end version ... [pause, retakes] so here's the higher end version")
    # is ONE product change: a part with < 40 words merges into the next (lv trainer 2026-10-23: an empty "product 2"
    # between the two takes made the white pair "product 3")
    k = 1
    while k < len(cuts) - 1:
        if sum(1 for w in words if cuts[k - 1] <= w["s"] < cuts[k]) < 40 and k > 1:
            cuts.pop(k)
        else:
            k += 1
    segs = []
    for s0, s1 in zip(cuts, cuts[1:]):
        colour = None
        seg = [w for w in words if s0 <= w["s"] < s1]
        for j, w in enumerate(seg):
            n = _norm(w["w"])
            nxt = _norm(seg[j + 1]["w"]) if j + 1 < len(seg) else ""
            if n in bc["colours"] and nxt not in bc["colour_part_words"]:  # "black backing" / "red bottom" describe a part
                colour = n
                break
        segs.append((s0, s1, colour))
    return segs


def product_segments(words, sections, bc):
    """The products over the WHOLE product part (review + showcase), not the review section alone: the fallback sections can
    leave the review nearly empty (lv trainer 2026-10-23: a 3 s monitor flash started the "showcase" at 2:26, so both
    trainers sat in it, auto_pair saw one product and the white pair's clips went over the black-and-white one)."""
    ps = [x for x in sections if x["name"] in ("review", "showcase")]
    return _segments(words, min(x["start"] for x in ps), max(x["end"] for x in ps), bc) if ps else []


def opened_at(words, s0, s1, bc, tl=None):
    """When he opens this product's box: the first KEPT opening cue in [s0, s1) ("let's go ahead and open this up", "pull
    this pull tab", "unboxing"), else None. No B-roll of the product before it (lv trainer 2026-10-23, 1:00-1:12: "I
    didn't even open the shoe box ... we never want to have B-roll of shoes before I actually open the shoe box")."""
    cues = [[_norm(x) for x in c.split()] for c in bc.get("open_cues", [])]
    for i, w in enumerate(words):
        if not (s0 <= w["s"] < s1) or not _kept(tl, w["s"]):
            continue
        toks = [_norm(x["w"]) for x in words[i:i + 8]]
        if toks[0].startswith("unbox") or any(toks[:len(c)] == c for c in cues):
            return w["s"]
    return None


def _moment_end(words, i, seg_end, bc, tl=None):
    """From word i, run to sentence ends until at least min_seconds, never past max_seconds or the pair's end.
    With a timeline the lengths are OUTPUT seconds (cut footage doesn't count): a moment measured in source time
    that crossed a cut came out 1.8 s long (dhgate asics 2026-10-22, the on-feet slot)."""
    out = (lambda t: tl.to_out(t)) if tl else (lambda t: t)
    a = words[i]["s"]
    oa = out(a)
    end = None
    for w in words[i:]:
        if w["s"] >= seg_end - 0.3 or out(w["e"]) - oa > bc["max_seconds"]:
            break
        end = w["e"]
        if re.search(r"[.!?]$", w["w"]) and out(w["e"]) - oa >= bc["min_seconds"]:
            break
    if end is None:
        return a
    if out(end) - oa < bc["min_seconds"] and not tl:
        end = min(a + bc["min_seconds"], seg_end - 0.2)
    return min(end, seg_end - 0.2)


def _kept(tl, t):
    return tl is None or any(a <= t < b for a, b in tl.kept)


# he is pointing at the live camera: B-roll over it hides what he shows (prada cups 2026-10-22: on-feet footage over
# "right here is the box", turntable over "hey guys")
DEICTIC = ["right here", "here is", "heres", "here's", "this is", "you can see", "as you can see", "look at"]


# the same pointing in his other wordings: "as you guys COULD see ON THE TOE BOX" got a B-roll clip over it (balenciaga
# track led review 2026-10-26, 2:40: "the B-roll covered what I was trying to point to ... show the B-roll after I'm done
# talking about the toe box"); the fixed phrase lists only knew "you can see"
SHOW_RE = re.compile(r"\b(you|yall|y'all)( guys| all)? (can|could|might|will) (see|tell|notice)\b|\b(if you|take a|have a|you'?ll) look\b|"
                     r"\bon the (toe ?box|tongue|heel|heel tab|sole|outsole|insole|midsole|tag|label|stitching|logo|box)\b|"
                     r"\bcheck (this|that|it) out\b|\bright (here|there)\b", re.I)


def _deictic(words, i):
    """True when the sentence that word i starts (first ~8 words) points at what's on camera."""
    toks = [_norm(x["w"]) for x in words[i:i + 8]]
    txt = " " + " ".join(toks) + " "
    return any(f" {_norm(d) if ' ' not in d else d} " in txt for d in DEICTIC) or bool(SHOW_RE.search(txt))


def _fits(a, b, others, bc, tl):
    """Long enough in the finished video and min_gap_seconds clear of every other slot."""
    out = (lambda t: tl.to_out(t)) if tl else (lambda t: t)
    gap = bc.get("min_gap_seconds", 1)
    if out(b) - out(a) < bc["min_seconds"] - 0.01:
        return False
    return not any(out(a) < out(p["end"]) + gap and out(b) > out(p["start"]) - gap for p in others)


def plan_slots(words, sections, tl, cfg, avoid=(), hard=()):
    """Moments to cover, per pair: on feet first, then showing it off on the turntable, the sole, the box.
    Each is 5-10 s, starts on the phrase that calls for it, and stays inside that pair's part of the review.
    avoid: source ranges B-roll never covers (screen, product held up to the front camera, the talking intro); hard: the
    part of those a line that NAMES the shot can't override either (screen, talking intro). A line that names the shot
    ("you can also see me with on feet footage right now", "I'll put it on the turntable so you can see exactly what it
    looks like") gets its clip even while he holds the product up (dhgate rick owens 2026-10-22, 2:05)."""
    bc = cfg["broll"]
    kinds = bc["kinds"]
    chosen = []
    for s in sections:
        if s["name"] not in bc["sections"]:
            continue
        # the same product split as auto_pair (review + showcase), so a clip's "pair" and a slot's pair always agree
        segs = product_segments(words, sections, bc) if s["name"] == "review" else _segments(words, s["start"], s["end"], bc)
        multi = len(segs) > 1
        for k, (s0, s1, colour) in enumerate(segs, 1):
            seg_words = [i for i, w in enumerate(words) if s0 <= w["s"] < s1 - 1.0]
            op = opened_at(words, s0, s1, bc, tl)   # nothing of the shoes before their box is open (box shots may)
            seg_words_all = seg_words
            picks = []
            for kind in bc["kind_order"]:
                seg_words = [i for i in seg_words_all if kind == "box" or op is None or words[i]["s"] >= op]
                done = False
                for ph in kinds[kind]["phrases"]:  # phrases are in priority order: strongest first
                    pw = [_norm(x) for x in ph.split()]
                    for i in seg_words:
                        if not _kept(tl, words[i]["s"]):
                            continue    # the phrase was cut out: nothing to cover there
                        if [_norm(x["w"]) for x in words[i:i + len(pw)]] == pw:
                            if kind in ("box", "sole") and _deictic(words, max(i - 4, 0)):
                                continue    # "right here is the box": the real box is on camera
                            a = words[i]["s"] - 0.1
                            b = _moment_end(words, i, s1, bc, tl)
                            if _blocked(a, b, hard):
                                continue    # the desktop / his talking intro is up there
                            if _fits(a, b, picks + chosen, bc, tl):
                                picks.append({"kind": kind, "start": round(a, 2), "end": round(b, 2), "i": i})
                                done = True
                                break
                    if done:
                        break  # one moment per kind per pair
                if not done and kind in bc.get("sprinkle_kinds", []):
                    # no phrase calls for it (or it was cut): sprinkle the shot in at a sentence start in this pair
                    # (user 2026-10-22: "if it doesn't have that clip, you might just want to sprinkle it in")
                    # Spaced out: the sentence start farthest (finished-video time) from the other slots and the section
                    # edges, never on a line where he points at the camera (prada cups 2026-10-22: "add the turntable
                    # footage somewhere, but not in this section. Let's just space it out")
                    out = (lambda t: tl.to_out(t)) if tl else (lambda t: t)
                    best, best_d = None, -1.0
                    for j, i in enumerate(seg_words):
                        if not _kept(tl, words[i]["s"]) or (j and not re.search(r"[.!?]$", words[seg_words[j - 1]]["w"])):
                            continue
                        if _deictic(words, i):
                            continue
                        a = words[i]["s"] - 0.1
                        b = _moment_end(words, i, s1, bc, tl)
                        if not _fits(a, b, picks + chosen, bc, tl) or _blocked(a, b, avoid) or _span_shows(words, a, b):
                            continue
                        marks = [out(s["start"]), out(s["end"])] + [out(p["start"]) for p in picks + chosen] + [out(p["end"]) for p in picks + chosen]
                        d = min(min(abs(out(a) - m), abs(out(b) - m)) for m in marks)
                        if d > best_d:
                            best, best_d = (a, b, i), d
                    if best:
                        picks.append({"kind": kind, "start": round(best[0], 2), "end": round(best[1], 2), "i": best[2], "sprinkled": True})
                if len(picks) >= bc["max_per_pair"]:
                    break
            for p in picks:
                who = f"Pair {k}" + (f" ({colour})" if colour else "") if multi else (colour.capitalize() + " pair" if colour else "The shoes")
                quote = " ".join(x["w"] for x in words[p["i"]:p["i"] + 14])
                chosen.append({"kind": p["kind"], "pair": k if multi else 1, "colour": colour, "sprinkled": p.get("sprinkled", False),
                               "shot": f"{who}: {kinds[p['kind']]['shot']}", "start": p["start"], "end": p["end"],
                               "quote": quote + ("..." if len(quote.split()) >= 14 else "")})
    chosen.sort(key=lambda c: c["start"])
    chosen = chosen[:bc["max_slots"]]
    for i, c in enumerate(chosen, 1):
        c["slot"] = i
        c["out_start"], c["out_end"] = round(tl.to_out(c["start"]), 2), round(tl.to_out(c["end"]), 2)
        # ending just short of a cut leaves a sliver of the old shot before the next one (dhgate asics 2:47: 0.3 s
        # of him looking down before the computer walkthrough): run on to the cut and hard-cut there instead
        clip = next(((ka, kb) for ka, kb in tl.kept if ka <= c["end"] <= kb), None)
        if clip:
            cut_out = tl.to_out(clip[1])
            if 0 < cut_out - c["out_end"] <= bc.get("snap_to_cut_seconds", 1.5):
                c["end"], c["out_end"], c["on_cut"] = clip[1], round(cut_out, 3), True
        c["seconds"] = round(c["out_end"] - c["out_start"], 1)
        c["name_hint"] = " ".join(x for x in [c["colour"], bc["kinds"][c["kind"]]["name_word"]] if x)
    return chosen


def write_requests(project, slots, fmt):
    L = ["# B-roll shot list", "",
         f"Drop clips in `{project / 'raw' / 'broll'}`. Name each one by slot number (`2.mov`) or describe it",
         "(`red feet.mov`, `white spin.mov`, `black sole.mov`, `box.mov`). Camera names like IMG_1234.mov work best when Claude matches them.",
         "Clips can be longer than needed: they're muted, fitted to 5-10 s, and graded automatically.", "",
         "| Slot | Time | Length | Shot | You're saying | Name it |", "|---|---|---|---|---|---|"]
    for s in slots:
        hint = f"`{s['slot']}.mov` or `{s.get('name_hint') or s['slot']}.mov`"
        L.append(f"| {s['slot']} | {fmt(s['out_start'])} | {s['seconds']} s | {s['shot']} | \"{s['quote']}\" | {hint} |")
    path = project / "output" / "broll_requests.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def _clip_tags(name, cfg):
    """Kind and colour words in a clip's file name, e.g. 'red feet' -> ('feet', 'red')."""
    bc = cfg["broll"]
    toks = re.findall(r"[a-z]+", name.lower())
    kind = next((k for k, v in bc["kinds"].items() for t in toks if t in v["file_words"]), None)
    colour = next((t for t in toks if t in bc["colours"]), None)
    return kind, colour


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    w, h = st.get("width", 1920), st.get("height", 1080)
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) == 90:
        w, h = h, w
    return w, h, float(d.get("format", {}).get("duration", 0) or 0)


def auto_label(project, cfg, checks):
    """Camera-named clips (IMG_0332.MOV) carry no kind in the name: look at 4 frames of each and ask Claude what it shows,
    then remember the answer in raw/broll.json as {"file", "kind", "colour", "why": "auto ..."} so it's done once and the
    user can correct it there (prada cups 2026-10-22: clips went in file order, on-feet footage landed on "here is the
    box" and the on-feet line got nothing; dhgate asics needed the same match by eye)."""
    bc = cfg["broll"]
    folder = project / "raw" / "broll"
    exts = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in exts]) if folder.exists() else []
    mfile = project / "raw" / "broll.json"
    known = json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else []
    named = {Path(m["file"]).name.lower() for m in known}
    todo = [p for p in files if p.name.lower() not in named and not re.match(r"(?:slot)?\s*\d+$", p.stem.lower())
            and _clip_tags(p.stem, cfg) == (None, None)]
    if not todo or os.environ.get("BROLL_AUTOLABEL") == "0":
        return
    kinds = {k: v["shot"] for k, v in bc["kinds"].items()}
    tmp = Path(tempfile.mkdtemp(prefix="broll_label_"))
    added = []
    for p in todo:
        _, _, dur = _probe(p)
        sheet = tmp / (p.stem + ".jpg")
        step = max(dur, 1.0) / 5
        # 4 frames at 20/40/60/80 % in a 2x2 sheet
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf",
                            f"fps=1/{step:.3f},scale=640:-2,tile=2x2", "-frames:v", "1", "-q:v", "4", str(sheet)],
                           capture_output=True, text=True)
        if not sheet.exists():
            checks.append(f"B-roll {p.name}: could not grab frames to label it ({r.stderr.strip()[:80]}).")
            continue
        # any product, not just sneakers; a product spinning on a turntable is "showcase" even when it sits in its open box
        # (dhgate cartier watch 2026-10-22: both watch spins were labelled "box" and then had no slot)
        prompt = (f"Read the image {sheet}. It is 4 frames from one B-roll clip for a product review video (shoes, watches, "
                  f"clothes, accessories). A product spinning on a turntable or shown close-up is 'showcase' even when it sits "
                  f"in its open box; 'box' is only the closed packaging / unboxing. "
                  f"Classify the clip as exactly one kind: " + "; ".join(f"{k} = {v}" for k, v in kinds.items()) +
                  "; other = none of these. Also give the product's main colour as one word, or null. "
                  'Answer with ONLY JSON: {"kind": "...", "colour": "...", "why": "<8 words on what you see>"}')
        # the pipeline brain ({{KIT}}/tools\claude_brain.py: Claude, cached;
        # 2026-10-22) instead of a full `claude -p` session per clip
        try:
            j = _brain().ask("broll_label", prompt.replace(f"Read the image {sheet}. It is", "The attached image is"), images=[str(sheet)])
            if not isinstance(j, dict):
                raise ValueError("no answer")
        except Exception as e:  # no key / timeout / odd answer: fall back to the old order rules
            checks.append(f"B-roll {p.name}: auto label failed ({type(e).__name__}), name it or add it to raw/broll.json.")
            continue
        kind = j.get("kind") if j.get("kind") in kinds else None
        # colour stays in "why" only: the slot plan guesses pair colours from the transcript ("black" for the white
        # Prada pair), and a mismatched colour would stop the kind match. Add "colour" by hand for multi-pair videos.
        entry = {"file": p.name, "kind": kind, "why": f"auto (frames, {j.get('colour') or '?'}): {j.get('why', '')}".strip()}
        added.append(entry)
        checks.append(f"B-roll {p.name}: auto-labelled '{kind or 'other'}' ({j.get('why', '')}). Fix in raw/broll.json if wrong.")
    shutil.rmtree(tmp, ignore_errors=True)
    if added:
        mfile.write_text(json.dumps(known + added, indent=1) + "\n", encoding="utf-8")


def _brain():
    import sys
    sys.path.insert(0, r"{{KIT}}/tools")
    import claude_brain
    return claude_brain


def auto_pair(project, words, sections, cam, rows, holdups, cfg, checks):
    """Which product each B-roll clip shows (dhgate rick owens 2026-10-22: three pairs, the clips went in file order, so the
    Vans spin landed in the low-top part and the low-top on-feet clip on the Vans "put it on the turntable" line). One
    look at a sheet: two frames of each product from his own cameras (the front camera while he holds it up, else the
    product camera) next to one frame of every clip; the brain names the pair per clip. Saved as "pair" in
    raw/broll.json (fix it there by hand if wrong). Only for videos with 2+ products."""
    bc = cfg["broll"]
    mfile = project / "raw" / "broll.json"
    if not mfile.exists() or os.environ.get("BROLL_AUTOLABEL") == "0":
        return
    entries = json.loads(mfile.read_text(encoding="utf-8"))
    todo = [m for m in entries if not m.get("pair") and m.get("slot") is None]
    segs = product_segments(words, sections, bc)
    if not todo or len(segs) < 2:
        return
    items, names = [], []
    for k, (s0, s1, _) in enumerate(segs, 1):
        # the front camera while he holds it up (the clearest look, longest showing first) AND the product camera: a short
        # "showing" can be him looking down at the desk with nothing in frame (rick owens pair 2)
        held = [(a, b) for a, b in holdups if s0 <= a < s1 and b - a >= 4]
        items += [(str(cam), (a + b) / 2, f"P{k} (product {k}, front cam)", "crop=iw/2:ih:0:0")
                  for a, b in sorted(held, key=lambda x: x[0] - x[1])[:2]]
        ts = [r["t"] for r in rows if s0 <= r["t"] < s1 and r.get("right") == "product"]
        items += [(str(cam), ts[int(len(ts) * f)], f"P{k} (product {k}, product cam)", "crop=iw/2:ih:iw/2:0")
                  for f in ((0.55,) if held else (0.4, 0.7)) if ts]
    for n, m in enumerate(todo, 1):
        p = project / "raw" / "broll" / m["file"]
        _, _, dur = _probe(p)
        items.append((str(p), dur / 2, f"C{n} {m['file']}"))
        names.append(m)
    sheet = project / "work" / "broll_pairs.png"
    try:
        B = _brain()
        B.contact_sheet(items, str(sheet), cols=4, w=420)
        prompt = (f"A product review video covers {len(segs)} products, in this order. The attached sheet shows each product as "
                  f"filmed by the creator (cells P1..P{len(segs)}) and one frame of each B-roll clip (cells C1..C{len(names)}). "
                  "For every clip, which product does it show? Compare the product itself: colour, material (canvas, suede, "
                  "leather), height (low/high top), sole and details; ignore the background. Answer 0 when no product matches. "
                  'Reply with ONLY JSON: {"clips": [{"c": 1, "product": 2, "why": "<8 words>"}]}')
        ans = B.ask("broll_pair", prompt, images=[str(sheet)])
    except Exception as e:
        checks.append(f"B-roll pair match failed ({type(e).__name__}: {str(e)[:80]}): clips go by kind only.")
        return
    for d in (ans or {}).get("clips", []) if isinstance(ans, dict) else []:
        try:
            m, k = names[int(d["c"]) - 1], int(d.get("product") or 0)
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if 1 <= k <= len(segs):
            m["pair"] = k
            m["why"] = (m.get("why", "") + f" | pair {k} auto: {d.get('why', '')}").strip(" |")
            checks.append(f"B-roll {m['file']}: shows product {k} ({d.get('why', '')}). Fix \"pair\" in raw/broll.json if wrong.")
    mfile.write_text(json.dumps(entries, indent=1) + "\n", encoding="utf-8")


def assign_clips(project, slots, cfg, checks, skip=(), no_sprinkle=()):
    """Match clips to slots: raw/broll.json mapping first, then files named by slot number, then leftovers in order.
    skip: clip names placed another way (in sync, or a cutaway with its sound) or dropped ("use": false).
    no_sprinkle: clips ABOUT a topic (camera test, app store): never a sprinkled filler, place_leftovers puts them over
    their topic."""
    bc = cfg["broll"]
    folder = project / "raw" / "broll"
    exts = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in exts]) if folder.exists() else []
    files = [p for p in files if p.name not in set(skip)]
    mapping = {}
    auto_label(project, cfg, checks)
    mfile = project / "raw" / "broll.json"
    if mfile.exists():
        # entries by slot number, or by kind ({"file": "IMG_0333.MOV", "kind": "feet"}): slot numbers move whenever the
        # cut changes, what the clip SHOWS doesn't (prada cups 2026-10-22)
        for m in json.loads(mfile.read_text(encoding="utf-8")):
            p = Path(m["file"]) if Path(m["file"]).is_absolute() else folder / m["file"]
            if p.name in set(skip):
                continue
            if m.get("slot") is not None:
                mapping[int(m["slot"])] = (p, float(m.get("start", 0)))
            elif m.get("kind"):  # kind null = "other": never placed on a literal slot
                # "pair": which product of the video the clip shows (1 = the first one he talks about); a clip only goes
                # to its own product's slots (dhgate rick owens 2026-10-22: the Vans spin went over the low-top section)
                sl = next((s for s in slots if s["slot"] not in mapping and s.get("kind") == m["kind"]
                           and (not m.get("pair") or s.get("pair") == int(m["pair"]))
                           and (not m.get("colour") or s.get("colour") in (None, m["colour"]))), None)
                if sl:
                    mapping[sl["slot"]] = (p, float(m.get("start", 0)))
    for p in files:
        num = re.match(r"(?:slot)?\s*(\d+)", p.stem.lower())
        if num and int(num.group(1)) not in mapping and any(s["slot"] == int(num.group(1)) for s in slots):
            mapping[int(num.group(1))] = (p, 0.0)
    # descriptive names: "red feet.mov" goes to the red pair's on-feet moment
    for p in files:
        if str(p) in {str(v[0]) for v in mapping.values()}:
            continue
        kind, colour = _clip_tags(p.stem, cfg)
        if not kind and not colour:
            continue
        best, best_score = None, 0
        for sl in slots:
            if sl["slot"] in mapping:
                continue
            score = (2 if kind and sl.get("kind") == kind else 0) + (2 if colour and sl.get("colour") == colour else 0)
            if kind and sl.get("kind") and sl.get("kind") != kind:
                score -= 3
            if colour and sl.get("colour") and sl.get("colour") != colour:
                score -= 3
            if score > best_score:
                best, best_score = sl, score
        if best:
            mapping[best["slot"]] = (p, 0.0)
    used = {str(v[0]) for v in mapping.values()}
    leftovers = [p for p in files if str(p) not in used]
    ent = {Path(m["file"]).name.lower(): m for m in (json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else [])}
    for s in slots:
        # an unidentified clip only goes where any shot of the shoes works (sprinkle kinds), never on a literal slot:
        # on-feet footage landed on "here is the box" (prada cups 2026-10-22)
        # ...and only a clip that could be this product's: a clip labelled for another product or another kind never fills
        # it (dhgate rick owens 2026-10-22: the low-top spin filled the Vans on-feet slot, over "hey guys")
        ok = [p for p in leftovers if not ent.get(p.name.lower(), {}).get("pair") or ent[p.name.lower()]["pair"] == s.get("pair")]
        ok = [p for p in ok if ent.get(p.name.lower(), {}).get("kind") in (None, s.get("kind"))]
        ok = [p for p in ok if p.name not in set(no_sprinkle)]
        if s["slot"] not in mapping and ok and s.get("kind") in bc.get("sprinkle_kinds", []):
            leftovers.remove(ok[0])
            mapping[s["slot"]] = (ok[0], 0.0)
            checks.append(f"B-roll slot {s['slot']}: no clip was named for it, so {mapping[s['slot']][0].name} was used. Check it fits.")
    placed = []
    for s in slots:
        if s["slot"] not in mapping:
            continue
        path, start = mapping[s["slot"]]
        p = _place(s, path, start, bc, checks)
        if p:
            placed.append(p)
    return placed, leftovers


def _place(s, path, start, bc, checks, speed=None):
    if speed:   # raw/broll.json "speed": a screen recording plays at its own pace (s25 ultra: the Play Store at 1x)
        w, h, dur = _probe(path)
        length = min(s["out_end"] - s["out_start"], max(0.0, dur - start) / speed)
        if length < 2.5:
            checks.append(f"B-roll slot {s['slot']}: {path.name} is too short from {start:.1f} s, slot left empty.")
            return None
        return {"slot": s["slot"], "file": str(path), "src_start": round(start, 3), "src_len": round(length * speed, 3),
                "speed": round(speed, 3), "out_start": s["out_start"], "length": round(length, 3), "portrait": w / max(h, 1) < 1.3,
                "on_cut": bool(s.get("on_cut")) and abs(length - (s["out_end"] - s["out_start"])) < 0.05}
    if True:
        if not path.exists():
            checks.append(f"B-roll slot {s['slot']}: {path.name} not found, slot left empty.")
            return None
        w, h, dur = _probe(path)
        usable = max(0.0, dur - start)
        if usable < 0.5:
            checks.append(f"B-roll slot {s['slot']}: {path.name} is too short, slot left empty.")
            return None
        length = s["out_end"] - s["out_start"]
        speed = usable / length
        if speed > bc["max_speed"]:
            speed = bc["max_speed"]
            start += (usable - length * speed) / 2  # use the middle of a long clip
        elif speed < bc["min_speed"]:
            speed = bc["min_speed"]
            length = usable / speed
            checks.append(f"B-roll slot {s['slot']}: {path.name} is short, so it covers {length:.1f} s instead of {s['seconds']} s.")
        return {"slot": s["slot"], "file": str(path), "src_start": round(start, 3), "src_len": round(length * speed, 3),
                "speed": round(speed, 3), "out_start": s["out_start"], "length": round(length, 3),
                "portrait": w / max(h, 1) < 1.3,
                "on_cut": bool(s.get("on_cut")) and abs(length - (s["out_end"] - s["out_start"])) < 0.05}


SHOWING = ["show you", "just like that", "like this", "looking like this", "showing you", "you can see", "as you can see", "look at", "right here", "here is", "here's", "heres", "this is what",
           # he is showing what came in the box (dhgate rick owens 2026-10-22: "at no point should we have B-roll if I'm
           # saying I'll let you guys read through it ... here's what's inside, we shouldn't have any B-roll over that")
           "read through", "let you guys read", "what's inside", "whats inside", "inside the box", "inside of the box", "comes with",
           "come with", "it has", "in the box"]


def _span_shows(words, a, b):
    """True when he shows something on camera anywhere inside [a, b] (SHOWING phrases)."""
    span = " " + " ".join(_norm(x["w"]) for x in words if a <= x["s"] < b) + " "
    return any(" " + " ".join(_norm(x) for x in d.split()) + " " in span for d in SHOWING) or bool(SHOW_RE.search(span))


def _blocked(a, b, avoid):
    """[a, b] (source) overlaps a stretch B-roll must never cover: the desktop/screen recording, or him holding the
    product up to the front camera (dhgate rick owens 2026-10-22: "B-roll should not go over desktop footage for the
    product reviews"; 3:34 he was showing the shoe on camera)."""
    return any(min(b, y) - max(a, x) > 0.3 for x, y in avoid or ())


OPENERS = {"so", "but", "now", "overall", "they", "also", "one", "if", "and"}


def place_leftovers(project, words, sections, tl, cfg, slots, placed, leftovers, checks, avoid=(), infos=None):
    """Every clip he gives ends up in the video (dhgate cartier watch 2026-10-22, 4:13: "I noticed you don't have any of
    the videos in this video. Please add the B-roll I gave you"). A clip no phrase slot took gets its own slot in the
    review OR showcase (here the review section was only the 24 s "hey guys" talk): a sentence start in kept footage,
    not a line where he points at the camera, 5-10 s, min_gap clear of the other slots; a sentence that names the clip's
    kind (box, watch, spin ...) wins, otherwise the one farthest from every other slot (spaced out). Never over the
    desktop or a product held up to the camera (avoid), never over him showing something; a clip with a "pair" in
    raw/broll.json stays inside that product's part of the review."""
    bc = cfg["broll"]
    mfile = project / "raw" / "broll.json"
    entries = {Path(m["file"]).name.lower(): m for m in (json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else [])}
    known = {k: m.get("kind") for k, m in entries.items()}
    out = (lambda t: tl.to_out(t))
    taken = list(slots)
    secs = [x for x in sections if x["name"] in bc.get("leftover_sections", ["review", "showcase"])]
    ws = words
    for path in leftovers:
        kind = known.get(path.name.lower()) or _clip_tags(path.stem, cfg)[0] or "showcase"
        kw = set()
        if kind in bc["kinds"]:
            kw = {kind, bc["kinds"][kind]["name_word"]} | set(bc["kinds"][kind]["file_words"])
        kw |= set(bc.get("product_words", []))
        # "at": a source time he pointed at in a note ("add the B-roll here", 4:13 in the draft) pins the clip to the
        # sentence start nearest it (within 10 s)
        at = entries.get(path.name.lower(), {}).get("at")
        pair = entries.get(path.name.lower(), {}).get("pair")
        # a clip ABOUT something (a camera test, the app store, setup screens) only plays while he talks about that
        # (s25 ultra 2026-10-23: "242, that B-roll shouldn't be there, I didn't talk about the camera yet"; "146 we don't
        # need that B-roll there because I didn't even turn on the phone yet")
        topics = (infos or {}).get(path.name, {}).get("topics") or []
        rng = None
        segs = product_segments(words, sections, bc)
        if pair:
            rng = segs[int(pair) - 1][:2] if 0 < int(pair) <= len(segs) else None
        # not before the product's box is open: its own pair's opening, else the first opening in the video
        ops = [opened_at(words, s0, s1, bc, tl) for s0, s1, _ in segs]
        op = ops[int(pair) - 1] if rng else next((o for o in ops if o is not None), None)
        if op is not None and kind != "box":
            rng = (max(op, rng[0]) if rng else op, rng[1] if rng else 1e9)
        best, best_score = None, -1e9
        for sec in secs:
            for i, w in enumerate(ws):
                if not (sec["start"] <= w["s"] < sec["end"] - bc["min_seconds"]) or not _kept(tl, w["s"]):
                    continue
                if rng and not (rng[0] <= w["s"] < rng[1] - bc["min_seconds"]):
                    continue    # the Vans clip goes in the Vans part, not wherever "vans" is said
                # sentence starts only. Whisper word output often has no punctuation and no gaps (end = next start), so a
                # pause (a gap, or a word stretched over one) or a sentence opener counts too
                prev = ws[i - 1] if i else None
                if prev and not (re.search(r"[.!?]$", prev["w"]) or w["s"] - prev["e"] >= 0.3 or prev["e"] - prev["s"] >= 0.6
                                 or _norm(w["w"]) in OPENERS):
                    continue
                if _deictic(ws, i):
                    continue
                a = w["s"] - 0.1
                b = _moment_end(ws, i, sec["end"], bc, tl)
                if not _fits(a, b, taken, bc, tl) or _blocked(a, b, avoid):
                    continue
                # nothing he shows on camera inside the covered stretch ("I'm going to show you guys", "you can see")
                if _span_shows(ws, a, b):
                    continue
                # ...said in the line the clip starts on (its first 20 kept words), not just somewhere in the covered span
                # (a slot over "I couldn't imagine it ..." whose end reached the Play Store line was not good enough)
                if topics and at is None:
                    head = [x for x in ws[max(0, i - 3):i + 40] if _kept(tl, x["s"]) and x["s"] >= a - 1.0][:23]
                    if not head or not _topic_said(head, head[0]["s"], head[-1]["s"] + 0.01, topics, bc, tl):
                        continue
                text = {_norm(x["w"]) for x in ws[i:i + 16]}
                marks = [out(sec["start"]), out(sec["end"])] + [out(p["start"]) for p in taken] + [out(p["end"]) for p in taken]
                score = min(60.0, min(min(abs(out(a) - m), abs(out(b) - m)) for m in marks)) + (25 if text & kw else 0)
                if at is not None:
                    if abs(a - float(at)) > 10:
                        continue
                    score = 1000 - abs(a - float(at))
                if score > best_score:
                    best, best_score = (a, b, i), score
        if not best:
            checks.append(f"B-roll clip {path.name} wasn't used (no free sentence start in the review/showcase"
                          + (f" where he talks about {'/'.join(topics)}" if topics else "") + ").")
            continue
        a, b, i = best
        sl = {"kind": kind, "pair": 1, "colour": None, "sprinkled": True, "shot": f"{path.stem} ({kind})", "start": round(a, 2), "end": round(b, 2),
              "quote": " ".join(x["w"] for x in ws[i:i + 14]), "slot": max([x["slot"] for x in taken] + [0]) + 1,
              "out_start": round(out(a), 2), "out_end": round(out(b), 2)}
        clip = next(((ka, kb) for ka, kb in tl.kept if ka <= b <= kb), None)
        if clip and 0 < out(clip[1]) - sl["out_end"] <= bc.get("snap_to_cut_seconds", 1.5):
            sl["end"], sl["out_end"], sl["on_cut"] = clip[1], round(out(clip[1]), 3), True
        sl["seconds"] = round(sl["out_end"] - sl["out_start"], 1)
        taken.append(sl)
        ent = entries.get(path.name.lower(), {})
        p = _place(sl, path, float(ent.get("start", 0.0)), bc, checks, speed=ent.get("speed"))
        if p:
            placed.append(p)
            checks.append(f"B-roll {path.name} ({kind}{', ' + '/'.join(topics) if topics else ''}) placed at {sl['out_start']:.1f} s (finished video) over \"{sl['quote'][:60]}...\". Check it fits.")
    return placed


def broll_filters(placed, first_input, base, cfg, W=1920, H=1080):
    """Filter lines that overlay each clip onto `base`; returns (lines, new_base_label)."""
    bc = cfg["broll"]
    lines, last = [], base
    fd = bc["fade_seconds"]
    for k, c in enumerate(placed):
        idx, L = first_input + k, c["length"]
        src_len = c["src_len"]
        if c.get("on_cut"):
            # frame rounding at the cut still let one frame of the old shot through: run 0.1 s past the cut
            L += 0.1
            src_len += 0.1 * c["speed"]
        pre = f"[{idx}:v]trim=start={c['src_start']}:duration={src_len:.3f},setpts=(PTS-STARTPTS)/{c['speed']},fps={cfg['output'].get('fps_render', 30)}"
        if c.get("crop"):   # one half of a side-by-side recording (named_broll)
            pre += "," + c["crop"]
        if c["portrait"]:
            lines.append(f"{pre},split=2[brbg{k}][brfg{k}]")
            lines.append(f"[brbg{k}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:2,eq=brightness=-0.08[brbgb{k}]")
            lines.append(f"[brfg{k}]scale=-2:{H}[brfgs{k}]")
            lines.append(f"[brbgb{k}][brfgs{k}]overlay=(W-w)/2:0[brfill{k}]")
        else:
            lines.append(f"{pre},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[brfill{k}]")
        z = f"(1+{bc['push_in'] - 1:.3f}*min(t/{L:.3f},1))"
        # on a cut: hard cut; his named clips (lists, "throw up some footage") cut straight from one to the next, on the word
        fout = "" if c.get("on_cut") or c.get("named") else f",fade=t=out:st={max(L - fd, 0):.3f}:d={fd}:alpha=1"
        sw, sh = f"2*trunc({W // 2}*{z})", f"2*trunc({H // 2}*{z})"
        lab = ""
        if c.get("labels"):   # the list building up / the product name (named_broll)
            import named_broll
            lab = named_broll.label_filter(c, W, H)
            lab = "," + lab if lab else ""
        lines.append(f"[brfill{k}]{bc['grade']},scale=w='{sw}':h='{sh}':eval=frame,"
                     f"crop={W}:{H}:x='({sw}-{W})/2':y='({sh}-{H})/2'{lab},format=yuva420p,fade=t=in:d={0.06 if c.get("named") else fd}:alpha=1{fout},"
                     f"setpts=PTS+{c['out_start']:.3f}/TB[br{k}]")
        lines.append(f"[{last}][br{k}]overlay=0:0:eof_action=pass[vb{k}]")
        last = f"vb{k}"
    return lines, last


# ---------------------------------------------------------------- what a clip SAYS (s25 ultra 2026-10-23)
# His clips are not only silent shots of the product: a phone filming its own setup screen while the desk mic records the
# same line ("there's a lot of end user agreements" = IMG_0827 at 0:59), a phone playing YouTube, and camera tests where he
# talks to the phone ("here is the audio quality from the phone ... clearer than the iPhone"). Their words decide where
# they go: in sync, over their topic only, or as a cutaway that plays WITH its sound.

DEMO_CUES = ["here is the", "heres the", "here is what", "heres what", "quality", "looks like",
             "front facing", "back camera", "rear camera", "camera test", "sound test", "audio test"]


def clip_words(project, files, checks):
    """Whisper words of each clip, cached in work/broll_words.json (by name + size)."""
    cache_f = project / "work" / "broll_words.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    todo = [p for p in files if cache.get(p.name, {}).get("size") != p.stat().st_size]
    if todo:
        try:
            import sys
            import numpy as np
            sys.path.insert(0, r"{{KIT}}/tools")
            from whisper_gpu import load
            model, _ = load("small.en")
            for p in todo:
                pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                                     capture_output=True).stdout
                a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
                ws, segs = [], []
                if len(a) > 16000:
                    out, _ = model.transcribe(a, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
                    for sg in out:
                        segs.append({"s": round(sg.start, 2), "e": round(sg.end, 2), "text": sg.text.strip()})
                        ws += [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in sg.words]
                cache[p.name] = {"size": p.stat().st_size, "words": ws, "segments": segs}
        except Exception as e:  # noqa: no whisper = the old silent-clip rules
            checks.append(f"B-roll clips could not be transcribed ({type(e).__name__}: {str(e)[:80]}); placed by picture only.")
        cache_f.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return {k: v for k, v in cache.items() if any(p.name == k for p in files)}


def clip_sync(cw, words, tl, min_run=8):   # 8: stock phrases ("we're gonna go ahead and peel") match at 5
    """Where the clip's audio says the SAME words as kept main footage (>= min_run in a row): the clip was filmed at the
    same moment, so it goes exactly there, at 1x. None otherwise."""
    if len(cw) < min_run:
        return None
    mn = [_norm(w["w"]) for w in words]
    cn = [_norm(w["w"]) for w in cw]
    pos = {}
    for j in range(len(mn) - 2):
        pos.setdefault(tuple(mn[j:j + 3]), []).append(j)
    best = None
    for i in range(len(cn) - 2):
        for j in pos.get(tuple(cn[i:i + 3]), []):
            n = 0
            while i + n < len(cn) and j + n < len(mn) and cn[i + n] == mn[j + n] and cn[i + n]:
                n += 1
            if n >= min_run and _kept(tl, words[j]["s"]) and (best is None or n > best[0]):
                best = (n, j, i)
    if not best:
        return None
    n, j, i = best
    return {"main": words[j]["s"], "clip": cw[i]["s"], "words": n, "i": j}


def clip_topics(entry, cw, bc):
    """Topics a clip is ABOUT, from its label ("phone screen setup pages") and its own words ("front facing camera")."""
    if entry.get("topics") is not None:
        return list(entry["topics"])
    text = " " + " ".join([_norm(x) for x in (entry.get("why") or "").split()] + [_norm(w["w"]) for w in cw[:80]]) + " "
    return [t for t, v in bc.get("topics", {}).items() if not t.startswith("_") and any(f" {x} " in text for x in v["clip_words"])]


def _topic_said(words, a, b, topics, bc, tl=None):
    """He talks about one of the clip's topics inside [a, b] (source), in KEPT footage (a span can cross a cut)."""
    span = " " + " ".join(_norm(x["w"]) for x in words if a <= x["s"] < b and _kept(tl, x["s"])) + " "
    return any(f" {x} " in span for t in topics for x in bc["topics"][t]["said"])


def is_demo(entry, cw):
    """He talks to the clip's own camera, showing something off ("here is the audio quality from the phone"): >= 20 words,
    a demo cue in its first 15 s. Such a clip never plays silent (a muted shot of him talking reads as lip-sync)."""
    if entry.get("insert") is not None:
        return bool(entry["insert"])
    if len(cw) < 20:
        return False
    head = " " + " ".join(_norm(w["w"]) for w in cw if w["s"] < 15) + " "
    return any(f" {c} " in head for c in DEMO_CUES)


VERDICT_CUES = ["final opinion", "my final", "final thoughts", "my verdict", "the verdict", "in conclusion", "overall i"]


def plan_inserts(project, words, sections, tl, cfg, infos, checks):
    """Demo clips that play WITH their own sound as a cutaway (s25 ultra 4:51: "before I say my final opinion on the phone
    I want to include ... me recording the camera quality. It has audio"): right before the verdict line ("my final
    opinion"), else at the end of the review. Several demo clips of the same thing = ONE ("let's not merge the 2 B-rolls,
    pick between the front facing camera or the one facing me"): raw/broll.json "insert": true picks, "use": false drops.
    Trimmed to "keep" [[a, b], ...] (clip seconds) when given, else to its whole sentences up to max_insert_seconds.
    Returns [{"file", "keep", "at" (source s), "out" (output s, before any insert), "len"}]."""
    bc = cfg["broll"]
    mfile = project / "raw" / "broll.json"
    entries = {Path(m["file"]).name.lower(): m for m in (json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else [])}
    demos = [n for n, inf in infos.items() if entries.get(n.lower(), {}).get("use", True) is not False and inf.get("demo")]
    if not demos:
        return []
    explicit = [n for n in demos if entries.get(n.lower(), {}).get("insert")]
    pick = explicit or [max(demos, key=lambda n: len(infos[n]["words"]))]
    for n in demos:
        if n not in pick:
            checks.append(f"B-roll {n}: another demo clip like {pick[0]}; only one plays (set \"insert\": true in "
                          f"raw/broll.json to pick it instead).")
    out = []
    for n in pick:
        e = entries.get(n.lower(), {})
        at = e.get("at")
        if at is None:
            for i, w in enumerate(words):
                if not _kept(tl, w["s"]):
                    continue
                txt = " ".join(_norm(x["w"]) for x in words[i:i + 3])
                if any(txt.startswith(c) for c in VERDICT_CUES):
                    at = w["s"]
                    break
        if at is None:
            rev = [s for s in sections if s["name"] in ("review", "showcase")]
            at = rev[0]["end"] if rev else None
        if at is None:
            continue
        # ON THE CUT when the line opens a kept clip (s25 ultra 4:27: "the clip ahead of this actually appears for a quick
        # second ... you spliced it too early": Whisper put "My" before the clip start, so the next word was used and
        # 0.13 s of "my final opinion" played before the cutaway), else at the sentence start inside the clip
        piece = next(((a, b) for a, b in tl.kept if b > float(at)), None)
        if piece is None:
            continue
        if piece[0] >= float(at) - 1.0:
            at = piece[0]
        else:
            nxt = next((w for w in words if w["s"] >= float(at) - 0.3 and _kept(tl, w["s"])), None)
            if nxt is None:
                continue
            at = max(nxt["s"] - 0.12, piece[0])
        keep = e.get("keep")
        if not keep:
            keep, tot = [], 0.0
            for sg in infos[n]["segments"]:
                if len(sg["text"].split()) < 4 or re.search(r"\b(oops|whoops)\b", sg["text"].lower()):
                    continue
                if tot + sg["e"] - sg["s"] > bc.get("max_insert_seconds", 30):
                    break
                keep.append([max(0, sg["s"] - 0.15), sg["e"] + 0.2])
                tot += sg["e"] - sg["s"] + 0.35
        merged = []
        for a, b in sorted([list(x) for x in keep]):
            if merged and a <= merged[-1][1] + 0.05:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        ln = sum(b - a for a, b in merged)
        o = round(round(tl.to_out(at) * 30) / 30, 3)
        out.append({"file": infos[n]["path"], "keep": merged, "at": round(at, 3), "out": o, "len": round(ln, 3)})
        checks.append(f"Cutaway WITH its sound: {n} ({ln:.1f} s, clip {', '.join(f'{a:.1f}-{b:.1f}' for a, b in merged)}) "
                      f"plays at {o:.1f} s (main edit) before \"{' '.join(w['w'] for w in words if w['s'] >= at)[:50]}\". Check it.")
    return out


def place_synced(project, words, tl, cfg, infos, placed, taken, checks, avoid=()):
    """Clips whose audio repeats kept main-camera words go right there, at 1x, in sync (the phone filmed its own
    end-user-agreement screens while he said so). Returns the names placed."""
    bc = cfg["broll"]
    done = []
    out = (lambda t: tl.to_out(t))
    for n, inf in infos.items():
        sy = inf.get("sync")
        if not sy or inf.get("demo"):
            continue
        i = sy["i"]
        # back to the start of the sentence the clip still covers
        while i > 0 and _kept(tl, words[i - 1]["s"]) and not re.search(r"[.!?]$", words[i - 1]["w"]) \
                and words[i]["s"] - words[i - 1]["e"] < 0.3 and sy["clip"] + (words[i - 1]["s"] - sy["main"]) >= 0:
            i -= 1
        a = words[i]["s"] - 0.1
        clip_start = sy["clip"] + (a - sy["main"])
        if clip_start < 0:
            a, clip_start = a - clip_start, 0.0
        piece_end = next((kb for ka, kb in tl.kept if ka <= a + 0.1 <= kb), a + bc["max_seconds"])
        b = _moment_end(words, i, piece_end + 0.3, bc, tl)
        _, _, dur = _probe(Path(inf["path"]))
        b = min(b, a + (dur - clip_start))
        if out(b) - out(a) < 2.5 or _blocked(a, b, avoid):
            checks.append(f"B-roll {n}: in sync with the main camera at {sy['main']:.1f} s (source) but too little kept footage "
                          "there; not placed.")
            continue
        sl = {"slot": max([x["slot"] for x in taken] + [0]) + 1, "kind": "synced", "start": round(a, 2), "end": round(b, 2),
              "out_start": round(out(a), 3), "out_end": round(out(b), 3)}
        clip = next(((ka, kb) for ka, kb in tl.kept if ka <= b <= kb), None)
        if clip and 0 <= out(clip[1]) - sl["out_end"] <= bc.get("snap_to_cut_seconds", 1.5) \
                and clip_start + out(clip[1]) - sl["out_start"] <= dur:
            sl["end"], sl["out_end"], sl["on_cut"] = clip[1], round(out(clip[1]), 3), True
        L = sl["out_end"] - sl["out_start"]
        w_, h_, _ = _probe(Path(inf["path"]))
        placed.append({"slot": sl["slot"], "file": inf["path"], "src_start": round(clip_start, 3), "src_len": round(L, 3),
                       "speed": 1.0, "out_start": sl["out_start"], "length": round(L, 3), "portrait": w_ / max(h_, 1) < 1.3,
                       "on_cut": bool(sl.get("on_cut"))})
        sl["seconds"] = round(L, 1)
        taken.append(sl)
        done.append(n)
        checks.append(f"B-roll {n} plays IN SYNC with the main camera ({sy['words']} words match) at {sl['out_start']:.1f} s "
                      f"over \"{' '.join(w['w'] for w in words[i:i + 10])}...\" (clip {clip_start:.1f} s, 1x).")
    return done


def clip_infos(project, words, tl, cfg, checks):
    """name -> {"path", "words", "segments", "sync", "demo", "topics"} for every clip in raw/broll."""
    bc = cfg["broll"]
    folder = project / "raw" / "broll"
    exts = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in exts]) if folder.exists() else []
    if not files:
        return {}
    mfile = project / "raw" / "broll.json"
    entries = {Path(m["file"]).name.lower(): m for m in (json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else [])}
    cws = clip_words(project, files, checks)
    infos = {}
    for p in files:
        e = entries.get(p.name.lower(), {})
        cw = cws.get(p.name, {}).get("words", [])
        sy = clip_sync(cw, words, tl) if e.get("sync", True) is not False else None
        infos[p.name] = {"path": str(p), "words": cw, "segments": cws.get(p.name, {}).get("segments", []), "sync": sy,
                         "demo": is_demo(e, cw) if e.get("insert") is not None else ((not sy) and is_demo(e, cw)),
                         "topics": clip_topics(e, cw, bc)}
    return infos
