"""Top-N countdown videos (top 5 reselling products spring 2026-10-25, user: "since this is a top 5 video and I go over 5
different products ... mark it with transitions, swooshes, and a card of number 5, number 4 ... number 1 ... this should be
for top 5 videos in general, not exclusive to Minecraft ... on brand with the reselling content ... the voiceover intro gets
its own music, the hey-guys intro gets its own, number 5, 4, 3, 2, 1 each get their own, the outro gets its own ... there is
also a bonus one, identify the bonus and give it a card with music too").

A countdown is the project title saying "top N" (or raw/config.json countdown.enabled). Items come from raw/countdown.json
([{"label": "#1", "name": "Spider Hoodie", "src": 310.0}, ..., {"label": "BONUS", "name": "T-Shirts", "src": 2108.7}],
source seconds) or are found in the kept words: product announcements ("the first item", "next up", "the last item",
"number three", "last but not least", "bonus item"), one per >= min_gap_seconds of finished video, numbered 1..N in the
order he says them, a "bonus" cue after them = BONUS. Each item point snaps to a kept clip start (a cut) so the slide never
lands mid-shot. Every item then gets: the section slide + whoosh (edit_review.splice_transitions), its own beat, and a
number card overlaid for a few seconds right after the slide.

Beds (all review videos, not only countdowns; same note: "we've been using the same music track, it's been looping for the
whole thing ... run them back to back, once one track ends we move on to the next"): a section longer than its beat no
longer hard-loops it; the next unused beat follows with a 2 s crossfade (make_beds)."""
import json
import re
import subprocess
from pathlib import Path

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
CUE = re.compile(r"\b((first|second|third|fourth|fifth|next|last|final)\s+(product|item|one|thing)s?|next up|"
                 r"number\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)|last but not least|lastly|"
                 r"bonus\s+(item|product|one))\b")
FONTS = Path(r"{{KIT}}/tools/intro_library/kit/fonts")


def top_n(title):
    m = re.search(r"\btop\s*(\d+|three|five|ten|seven)\b", title.lower())
    if not m:
        return 0
    v = m.group(1)
    return int(v) if v.isdigit() else WORDNUM.get(v, 0)


def _name_after(ws, i):
    """the product he names after the cue: up to 3 words after the first have/be/is/are/got/with, stopping at punctuation"""
    out, started = [], False
    for w in ws[i:i + 14]:
        t = re.sub(r"[^a-z0-9'-]", "", w["w"].lower())
        if not started:
            if t in ("have", "be", "is", "are", "got", "with"):
                started = True
            continue
        if t in ("the", "a", "an", "some", "our", "my", "going", "gonna", "to", "be", "actually", "pretty", "much", "do", "also",
                 "any", "type", "of", "kind") and not out:
            continue
        if t in ("and", "which", "that", "because", "so", "but"):
            break
        out.append(re.sub(r"[^A-Za-z0-9'-]", "", w["w"]))
        if w["w"].rstrip()[-1:] in ".,!?" or len(out) == 3:
            break
    return " ".join(x for x in out if x).title()


def find_items(project, words, kept, tl, cfg, checks):
    cc = cfg.get("countdown", {})
    title = project.name
    try:
        title = json.loads((project / "studio.json").read_text(encoding="utf-8")).get("title") or title
    except Exception:
        pass
    n = cc.get("n") or top_n(title)
    manual = project / "raw" / "countdown.json"
    # only a countdown video: the title says "top N", or he wrote raw/countdown.json (countdown.enabled false = off)
    if not cc.get("enabled", True) or not (n or manual.exists()):
        return []
    starts = sorted(a for a, b in kept)
    sn = cc.get("snap_seconds", 8.0)

    # pauses inside kept clips (>= 0.3 s between two kept words): where a slide may sit when no cut is near
    kw = sorted((w for w in words if any(a <= w["s"] < b for a, b in kept)), key=lambda w: w["s"])
    pauses = [round((x["e"] + y["s"]) / 2, 3) for x, y in zip(kw, kw[1:])
              if y["s"] - x["e"] >= 0.3 and any(a <= x["e"] and y["s"] <= b for a, b in kept)]

    def snap(t):
        """onto a cut: the clip start just before (<= sn s of video), else the next one (<= sn s; "...our bonus item of
        today, | which is going to be any type of t-shirt" reveals on the cut), else the nearest real PAUSE between two
        words. NEVER the raw time: it sat inside his words and the slide chopped them (reselling spring 2026-10-25: "the
        transitions ... are very choppy ... cuts off a word, transitions, even though I finished the sentence"; 6 of 7
        slides landed mid-word, e.g. "next up we have |AirPods", "the denim tier |shorts")"""
        before = [a for a in starts if a <= t + 0.3 and tl.to_out(t) - tl.to_out(a) <= sn]
        if before:
            return max(before)
        after = [a for a in starts if a > t and tl.to_out(a) - tl.to_out(t) <= sn]
        if after:
            return min(after)
        near = [p for p in pauses if abs(tl.to_out(p) - tl.to_out(t)) <= 12]
        if near:
            return min(near, key=lambda p: abs(p - t))
        return min(starts, key=lambda a: abs(tl.to_out(a) - tl.to_out(t)))
    if manual.exists():
        items = json.loads(manual.read_text(encoding="utf-8"))
        items = [dict(it, src=snap(float(it["src"]))) for it in items]
        checks.append("Countdown from raw/countdown.json: " + ", ".join(f"{it['label']} {it.get('name', '')}".strip() for it in items) + ".")
    else:
        # a word plays when it overlaps a kept piece: Whisper often starts the first word ("Next") just before the cut
        ws = [w for w in words if any(a - 0.5 <= w["s"] < b and w["e"] > a + 0.05 for a, b in kept)]
        text = " ".join(re.sub(r"[^a-z0-9' ]", "", w["w"].lower()) for w in ws)
        # char offset -> word index
        offs, pos = [], 0
        for w in ws:
            offs.append(pos)
            pos += len(re.sub(r"[^a-z0-9' ]", "", w["w"].lower())) + 1
        found = []
        for m in CUE.finditer(text):
            i = max(k for k, o in enumerate(offs) if o <= m.start())
            t = ws[i]["s"]
            # the sentence it sits in: back to the last full stop within 6 words
            j = i
            while j > 0 and i - j < 6 and not ws[j - 1]["w"].rstrip().endswith((".", "!", "?")):
                j -= 1
            t = snap(ws[j]["s"])
            bonus = "bonus" in m.group(0)
            if found and tl.to_out(t) - tl.to_out(found[-1]["src"]) < cc.get("min_gap_seconds", 45.0) and not (bonus and not found[-1]["bonus"]):
                continue
            found.append({"src": t, "bonus": bonus, "name": _name_after(ws, i)})
        main = [f for f in found if not f["bonus"]][: n or None]
        bon = [f for f in found if f["bonus"] and (not main or f["src"] > main[-1]["src"])][:1]
        items = [{"label": f"#{k + 1}", "name": f["name"], "src": f["src"]} for k, f in enumerate(main)]
        items += [{"label": "BONUS", "name": f["name"], "src": f["src"]} for f in bon]
        if n and len(main) != n:
            checks.append(f"Countdown: the title says top {n} but {len(main)} product announcement(s) were found; "
                          "check the cards or write raw/countdown.json.")
        if items:
            checks.append("Countdown found: " + ", ".join(f"{it['label']} {it['name']} @ {it['src']:.1f}" for it in items)
                          + " (source). Fix with raw/countdown.json if wrong.")
    # numbered 1..N in the ORDER he shows them, never a countdown (2026-10-25, top 5 reselling products spring: "number the
    # products 1, 2, 3, 4, 5 in the order I show them, not #5 down to #1; there isn't a real ranking, they are just 5 good
    # products ... every top-N product video"); a raw/countdown.json label is renumbered too, BONUS stays BONUS
    items = sorted(items, key=lambda x: x["src"])
    k = 0
    for it in items:
        if str(it.get("label", "")).upper() != "BONUS":
            k += 1
            it["label"] = f"#{k}"
    for it in items:
        it["out"] = round(tl.to_out(it["src"]), 3)
        it["key"] = "bonus" if it["label"].upper() == "BONUS" else "n" + re.sub(r"\D", "", it["label"])
    return sorted(items, key=lambda x: x["src"])


def plan(items, transitions, out_sections, duration):
    """music sections (output time) + the transitions list for a countdown: intro (hey guys) -> each item -> outro. The
    original intro->review / review->showcase slides go; the slide into the outro stays."""
    outro = next((tr for tr in transitions if tr["to"] == "outro"), None)
    o_start = outro["out"] if outro else next((s["start"] for s in out_sections if s["name"] == "outro"), duration)
    pts = [it for it in items if it["out"] < o_start - 5]
    secs, trans, prev = [], [], "intro"
    t0 = 0.0
    for it in pts:
        secs.append({"name": prev, "start": t0, "end": it["out"]})
        trans.append({"src": it["src"], "out": it["out"], "from": prev, "to": it["key"]})
        prev, t0 = it["key"], it["out"]
    secs.append({"name": prev, "start": t0, "end": o_start})
    if o_start < duration - 1:
        secs.append({"name": "outro", "start": o_start, "end": duration})
        if outro:
            trans.append(dict(outro, **{"from": prev}))
    return secs, trans


def make_card(work, label, name):
    """the number card: a dark rounded panel lower left, the number huge in Anton green, the product in Poppins Black caps"""
    from PIL import Image, ImageDraw, ImageFont
    work = Path(work)
    path = work / f"countdown_{re.sub(r'[^A-Za-z0-9]', '', label)}.png"
    W, H = 1920, 1080
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    big = ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), 230 if label.startswith("#") else 150)
    small = ImageFont.truetype(str(FONTS / "Poppins-Black.ttf"), 64)
    name = (name or "").upper()
    lw = d.textbbox((0, 0), label, font=big)
    nw = d.textbbox((0, 0), name, font=small) if name else (0, 0, 0, 0)
    pw = max(lw[2] - lw[0], nw[2] - nw[0]) + 120
    ph = (lw[3] - lw[1]) + (nw[3] - nw[1]) + (150 if name else 110)
    x0, y0 = 80, H - 80 - ph
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), radius=28, fill=(10, 12, 14, 205))
    d.rectangle((x0, y0 + 22, x0 + 12, y0 + ph - 22), fill=(61, 255, 122, 255))
    d.text((x0 + 60 - lw[0], y0 + 40 - lw[1]), label, font=big, fill=(61, 255, 122, 255))
    if name:
        d.text((x0 + 62 - nw[0], y0 + 40 + (lw[3] - lw[1]) + 34 - nw[1]), name, font=small, fill=(255, 255, 255, 255))
    im.save(path)
    return path


def card_filters(items, input0, last, hold):
    """overlay each card at its item's output time (right after the slide), sliding in from the left with a fade"""
    v = []
    for k, it in enumerate(items):
        T = it["out"]
        v.append(f"[{input0 + k}:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st={hold - 0.4:.2f}:d=0.4:alpha=1,"
                 f"setpts=PTS-STARTPTS+{T:.3f}/TB[cd{k}]")
        v.append(f"[{last}][cd{k}]overlay=x='-60*max(0,1-(t-{T:.3f})/0.35)':y=0:eof_action=pass[vcd{k}]")
        last = f"vcd{k}"
    return v, last


def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def make_beds(music, sections, work, checks, xfade=2.0, lead=1.0):
    """one bed per section: its own beat, and when the section outlasts it the next unused beat follows (crossfade) instead
    of the same track looping. music = [beat per section ..., spare beats ...]. Returns the bed paths (one per section)."""
    if not music:
        return music
    n = len(sections)
    own, spare = list(music[:n]), list(music[n:])
    mdir = Path(work) / "music"
    beds = []
    for i, s in enumerate(sections):
        need = s["end"] - s["start"] + lead + 1.0
        chain = [own[i % len(own)]]
        total = _dur(chain[0])
        pool = spare + [b for j, b in enumerate(own) if j != i and b not in chain]
        while total and total < need and pool:
            nxt = pool.pop(0)
            if nxt in spare:
                spare.remove(nxt)
            chain.append(nxt)
            total += _dur(nxt) - xfade
        if len(chain) == 1:
            beds.append(chain[0])
            continue
        out = mdir / f"bed_{i}_{s['name']}.m4a"
        inp, g, prev = [], [], "[0:a]"
        for b in chain:
            inp += ["-i", str(b)]
        for k in range(1, len(chain)):
            g.append(f"{prev}[{k}:a]acrossfade=d={xfade}:c1=tri:c2=tri[x{k}]")
            prev = f"[x{k}]"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", *inp, "-filter_complex", ";".join(g), "-map", prev,
                            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", str(out)], capture_output=True, text=True)
        if r.returncode == 0 and out.exists():
            beds.append(out)
            checks.append(f"Music {s['name']}: {s['end'] - s['start']:.0f} s plays " + " -> ".join(Path(b).stem[:40] for b in chain)
                          + " back to back (no looping).")
        else:
            beds.append(chain[0])
            checks.append(f"Music bed for {s['name']} failed ({r.stderr.strip()[-120:]}); its beat loops.")
    return beds
