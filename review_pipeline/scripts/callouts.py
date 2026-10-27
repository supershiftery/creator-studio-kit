"""Price callouts: when I say a dollar amount, the price pops up on screen in green with a cash register sound."""
import json, math, re, subprocess
from pathlib import Path

import numpy as np


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


WORD_NUM = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


def find_prices(words, tl, cfg, sections=None):
    pc = cfg["price"]
    allowed = None
    if sections and pc.get("sections"):
        allowed = [(s["start"], s["end"]) for s in sections if s["name"] in pc["sections"]]
    hits = []
    for i, w in enumerate(words):
        if allowed is not None and not any(a <= w["s"] < b for a, b in allowed):
            continue  # only count prices said while reviewing/showing the product, not intro context
        # only prices that are IN the video: a cut-out "$62" used to land on the next kept clip (prada cups 2026-10-22,
        # "not sure why there's a price tag here" over the link talk)
        if not any(a <= w["s"] and w["e"] <= b for a, b in tl.kept):
            continue
        m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)", w["w"])
        amount = m.group(1) if m else None
        nw = [_norm(x["w"]) for x in words[i + 1:i + 3]]
        if amount is None and _norm(w["w"]) == "hundred" and nw and nw[0] in ("dollars", "dollar", "bucks") and i:
            mult = WORD_NUM.get(_norm(words[i - 1]["w"]))   # "around a hundred dollars" = $100
            amount = str(mult * 100) if mult else None
        if amount is None and re.fullmatch(r"\d[\d,]*(?:\.\d+)?[.,!?]?", w["w"]):
            nxt = [_norm(x["w"]) for x in words[i + 1:i + 1 + pc["context_words"]]]
            before = [_norm(x["w"]) for x in words[max(0, i - pc["context_words_before"]):i]]
            prev = before[-1] if before else ""
            raw_next = words[i + 1]["w"] if i + 1 < len(words) else ""
            not_price = (prev in ("size", "us", "eu", "not") or "out" in nxt[:2] or raw_next.startswith("%")
                         or "%" in w["w"] or (nxt and nxt[0] in ("sure", "percent")))
            if nxt and nxt[0] in ("dollars", "dollar", "bucks"):
                amount = w["w"].rstrip(".,!?")
            elif not not_price and (any(k in nxt for k in pc["context_keys"]) or any(k in before for k in pc["context_keys_before"])):
                amount = w["w"].rstrip(".,!?")  # "140 is a reasonable price" / "it's going to cost 55"
        if amount is None:
            continue
        amount = amount.rstrip(".,")
        if amount.endswith(".0") or amount.endswith(".00"):
            amount = amount.split(".")[0]
        t = max(0.0, tl.to_out(w["s"]) - pc["lead_seconds"])
        if hits and t - hits[-1]["out"] < pc["min_gap_seconds"]:
            continue
        if t > tl.duration - pc["hold_seconds"]:
            continue
        hits.append({"text": f"${amount}", "source": w["s"], "out": round(t, 2), "said": w["w"]})
    return hits[:pc["max_per_video"]]  # one per video by default: the first time I say a price


# spoken MATH on screen (dhgate cologne spread 2026-10-25, 3:06: "four times twelve is going to be almost fifty dollars
# off ... for this video and future ones, that type of mathematical equation would be helpful to add in"): "<a> times <b>"
# (also "x", "multiplied by") with numbers on both sides, in kept footage, pops up as "$4 x 12 = $48" in the price style.
NUMS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
        "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}


def _number(w):
    """(value, is_dollars) of one spoken number word ("$4", "12", "twelve"), else None."""
    m = re.fullmatch(r"(\$)?(\d[\d,]*(?:\.\d+)?)[.,!?]?", w.strip())
    if m:
        return float(m.group(2).replace(",", "")), bool(m.group(1))
    v = NUMS.get(_norm(w))
    return (float(v), False) if v is not None else None


def _fmt(v):
    return f"{v:,.2f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"


def find_math(words, tl, cfg, taken=()):
    """[{text, source, out, hold, math}] for every "<a> times <b>" he says in kept footage, >= 8 s apart."""
    mc = cfg.get("math", {})
    if not mc.get("enabled", True):
        return []
    inn = lambda w: any(a <= w["s"] and w["e"] <= b for a, b in tl.kept)
    hits = []
    for i in range(1, len(words) - 1):
        op = _norm(words[i]["w"])
        j = i + 1
        if op == "multiplied" and j < len(words) and _norm(words[j]["w"]) == "by":
            j += 1
        elif op not in ("times", "x"):
            continue
        if j >= len(words):
            continue
        a, b = _number(words[i - 1]["w"]), _number(words[j]["w"])
        if not a or not b or not (inn(words[i - 1]) and inn(words[j])) or a[0] <= 0 or b[0] <= 0:
            continue   # "a lot of times", "three times a day": not math
        # dollars: "$4" itself, or "4 dollars" / "$4" said in the 10 s before ("a four dollar discount ... four times twelve")
        near = [w for w in words if words[i - 1]["s"] - 10 <= w["s"] < words[i - 1]["s"]]
        dollars = a[1] or any(
            (_number(w["w"]) or (None,))[0] == a[0] and (w["w"].startswith("$") or (k + 1 < len(near) and _norm(near[k + 1]["w"]) in ("dollar", "dollars", "bucks")))
            for k, w in enumerate(near))
        res = a[0] * b[0]
        cur = "$" if dollars else ""
        text = f"{cur}{_fmt(a[0])} × {_fmt(b[0])} = {cur}{_fmt(res)}"
        t = max(0.0, tl.to_out(words[i - 1]["s"]) - 0.1)
        if any(abs(t - h["out"]) < mc.get("min_gap_seconds", 8) for h in hits + list(taken)):
            continue
        hits.append({"text": text, "source": words[i - 1]["s"], "out": round(t, 2), "said": " ".join(x["w"] for x in words[i - 1:j + 1]),
                     "hold": mc.get("hold_seconds", 3.4), "math": True})
    return hits[:mc.get("max_per_video", 4)]


RATING_DEFAULTS = {"enabled": True, "hold_seconds": 3.0, "min_gap_seconds": 8, "max_per_video": 3, "font_size": 200,
                   "color": "0xFFD43B", "outline_color": "0x3A2A00", "outline_px": 12, "label": "RATING", "sound_db": -13}


def find_ratings(words, tl, cfg, taken=()):
    """[{text, source, out, hold, rating}] for every score he gives in kept footage: "an 8 out of 10", "9.5 out of ten",
    "8/10" (user 2026-10-26: "when I say this shoe is an 8 out of 10 ... put something on screen ... with an audible sound,
    kind of like the price call out ... seem like a human person's editing this video")."""
    rc = {**RATING_DEFAULTS, **cfg.get("rating", {})}
    if not rc["enabled"]:
        return []
    inn = lambda w: any(a <= w["s"] and w["e"] <= b for a, b in tl.kept)
    hits = []
    for i, w in enumerate(words):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)/(10|5)[.,!?]?", w["w"].strip())
        if m:
            score, top, j = float(m.group(1)), int(m.group(2)), i
        elif i + 3 < len(words) and _norm(words[i + 1]["w"]) == "out" and _norm(words[i + 2]["w"]) == "of":
            a, b = _number(w["w"]), _number(words[i + 3]["w"])
            if not a or not b or b[0] not in (5, 10):
                continue
            score, top, j = a[0], int(b[0]), i + 3
        else:
            continue
        if not (0 < score <= top) or not inn(w) or not inn(words[j]):
            continue
        t = max(0.0, tl.to_out(w["s"]) - 0.05)
        if any(abs(t - h["out"]) < rc["min_gap_seconds"] for h in hits + list(taken)):
            continue
        hits.append({"text": f"{_fmt(score)}/{top}", "source": w["s"], "out": round(t, 2), "hold": rc["hold_seconds"],
                     "said": " ".join(x["w"] for x in words[max(0, i - 2):j + 1]), "rating": True})
    return hits[:rc["max_per_video"]]


def make_rating_card(work: Path, text: str, cfg) -> Path:
    """'RATING' over a big gold '8/10', the price card's look in the review channels' yellow."""
    rc = {**RATING_DEFAULTS, **cfg.get("rating", {})}
    font = next((f for f in cfg["price"]["fonts"] if Path(f).exists()), None)
    out = work / f"rating_{re.sub(r'[^0-9A-Za-z]', '_', text)}.png"
    if out.exists():
        return out
    ff = f":fontfile='{_ffpath(font)}'" if font else ""
    big = text.replace("/", "\\/").replace(":", "\\:")
    draw = (f"drawtext=text='{rc['label']}':fontsize={rc['font_size'] // 3}:fontcolor=white:borderw=7:bordercolor={rc['outline_color']}:"
            f"x=(w-text_w)/2:y=30{ff},"
            f"drawtext=text='{big}':fontsize={rc['font_size']}:fontcolor={rc['color']}:borderw={rc['outline_px']}:"
            f"bordercolor={rc['outline_color']}:shadowcolor=black@0.45:shadowx=8:shadowy=10:x=(w-text_w)/2:y=110{ff}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00000000:s=1100x380,format=rgba",
                    "-vf", draw, "-frames:v", "1", str(out)], check=True)
    return out


def make_rating_sound(path: Path):
    """A short three-note bell arpeggio (C6 E6 G6), bright and light: a 'score reveal', not the price chime, no bass
    hit, no riser (sound rules), and not the gaming XP sound."""
    if path.exists():
        return path
    sr, dur = 48000, 1.0
    t = np.arange(int(sr * dur)) / sr

    def bell(start, f0, amp, decay):
        tt = np.clip(t - start, 0, None)
        on = (t >= start).astype(float)
        return on * amp * np.clip(tt / 0.003, 0, 1) * (np.sin(2 * math.pi * f0 * tt) + 0.3 * np.sin(4 * math.pi * f0 * tt)) * np.exp(-decay * tt)

    y = bell(0.0, 1046.5, 0.45, 8) + bell(0.07, 1318.5, 0.45, 8) + bell(0.14, 1568.0, 0.55, 5)
    y /= np.max(np.abs(y)) / 0.6
    d = int(sr * 0.007)
    st = np.stack([y, np.concatenate([np.zeros(d), y[:-d]])], 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "-",
                    "-af", "aecho=0.8:0.4:30|55:0.15|0.08", str(path)], input=(st * 32767).astype("<i2").tobytes(), check=True)
    return path


# The greeting callout of his editors' videos (channel study 2026-10-26: "HEY GUYS / NOT {{REVIEW_CHANNEL}} / WELCOME BACK / ANOTHER
# VIDEO" in yellow outlined captions while his cartoon avatar pops in), on the TALKING intro, never the voiceover intro
# (user: "add that call out at the beginning of the talking intro not the voice over one"). Avatars = the channels' own
# YouTube avatars in assets/avatars.
AVATARS = {"not {{REVIEW_CHANNEL}}": "Not{{REVIEW_CHANNEL}}", "{{REVIEW_CHANNEL}} reviews": "{{REVIEW_CHANNEL}}Reviews", "{{REVIEW_CHANNEL}} 1to1": "{{REVIEW_CHANNEL}}1to1",
           "{{REVIEW_CHANNEL}} resells": "{{REVIEW_CHANNEL}}Resells", "studio reviews": "studioreviews"}
GREET = [("hey guys", r"^((hey|yo|whats up) )?guys\b"), ("welcome back", r"^welcome back"), ("to yet again", r"^to yet again"),
         ("another video", r"^another (video|one)"), ("in today's video", r"^in today'?s video")]
CHANNEL_SAID = r"^(not {{REVIEW_CHANNEL}}+|{{REVIEW_CHANNEL}}+ reviews?|{{REVIEW_CHANNEL}}+ (1|one) ?to ?(1|one)|{{REVIEW_CHANNEL}}+ resells?|{{REVIEW_CHANNEL}}+ (finds|fines|kicks|profit)|agent {{REVIEW_CHANNEL}}+|shift(e|a)ry( reviews)?)"


def avatar_for(channel, skill: Path):
    c = (channel or "").strip().lower()
    name = AVATARS.get(c) or ("{{REVIEW_CHANNEL}}Reviews" if c.startswith("{{REVIEW_CHANNEL}}") else None)
    p = skill / "assets" / "avatars" / f"{name}.jpg" if name else None
    return p if p and p.exists() else None


def find_greeting(words, tl, channel, within=25.0):
    """[{text, out, hold, kind}] for his greeting in the first `within` s of the main video: each phrase on its word, held
    to the next one; "avatar" where he says the channel's name (or with "hey guys" when he never says it)."""
    inn = lambda w: any(a <= w["s"] and w["e"] <= b for a, b in tl.kept)
    ks = [w for w in words if inn(w) and tl.to_out(w["s"]) <= within]
    low = [_norm(w["w"]) for w in ks]
    hits = []
    i = 0
    while i < len(ks):
        tail = " ".join(low[i:i + 5])
        m = re.match(CHANNEL_SAID, tail)
        if m:
            n = len(m.group(0).split())
            said = m.group(0)
            canon = next((v for k, v in (("not", "NOT {{REVIEW_CHANNEL}}"), ("review", "{{REVIEW_CHANNEL}} REVIEWS"), ("one", "{{REVIEW_CHANNEL}} 1TO1"), (" 1", "{{REVIEW_CHANNEL}} 1TO1"),
                                         ("resell", "{{REVIEW_CHANNEL}} RESELLS"), ("find", "{{REVIEW_CHANNEL}} FINDS"), ("fine", "{{REVIEW_CHANNEL}} FINDS"),
                                         ("kick", "{{REVIEW_CHANNEL}} KICKS"), ("profit", "{{REVIEW_CHANNEL}} PROFIT"), ("agent", "AGENT {{REVIEW_CHANNEL}}"),
                                         ("shift", "STUDIO")) if k in said), said.upper())
            hits.append({"text": canon, "t": ks[i]["s"], "kind": "channel"})
            i += n
            continue
        for label, pat in GREET:
            m = re.match(pat, tail)
            if m:
                n = len(m.group(0).split())
                hits.append({"text": label.upper().replace("TODAY'S", "TODAY'S"), "t": ks[i]["s"], "kind": "phrase"})
                i += n - 1
                break
        i += 1
    if not any(h["kind"] == "phrase" and h["text"] == "HEY GUYS" for h in hits):
        return []   # no greeting at the top of the talking part: nothing to call out
    out = []
    for k, h in enumerate(hits[:5]):
        t = round(max(0.0, tl.to_out(h["t"]) - 0.04), 2)
        nxt = tl.to_out(hits[k + 1]["t"]) if k + 1 < len(hits[:5]) else t + 1.3
        out.append({"text": h["text"], "out": t, "hold": round(min(1.6, max(0.6, nxt - t)), 2), "kind": h["kind"], "greet": True})
    if out:
        a = next((h for h in out if h["kind"] == "channel"), out[0])
        out.append({"text": "avatar", "out": a["out"], "hold": 2.4, "kind": "avatar", "greet": True})
    return out


def make_caption_card(work: Path, text: str, cfg) -> Path:
    """His editors' greeting caption: white condensed letters, thick black outline, a soft shadow."""
    # white, black outline, tall condensed letters, like his editors' "HEY GUYS / NOT {{REVIEW_CHANNEL}}" ({{REVIEW_CHANNEL}} 2 Bape hoodie, 0:20)
    font = next((f for f in ["C:/Windows/Fonts/impact.ttf"] + cfg["price"]["fonts"] if Path(f).exists()), None)
    out = work / f"greet2_{re.sub(r'[^0-9A-Za-z]', '_', text)}.png"
    if out.exists():
        return out
    esc = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
    draw = (f"drawtext=text='{esc}':fontsize=124:fontcolor=white:borderw=9:bordercolor=black:"
            f"shadowcolor=black@0.5:shadowx=6:shadowy=8:x=(w-text_w)/2:y=(h-text_h)/2")
    if font:
        draw += f":fontfile='{_ffpath(font)}'"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00000000:s=1500x220,format=rgba",
                    "-vf", draw, "-frames:v", "1", str(out)], check=True)
    return out


def make_avatar_card(work: Path, avatar: Path, size: int = 400) -> Path:
    """The channel avatar as a white-ringed circle. 400 px = what his editors use (~0.37 of frame height,
    measured frame by frame on Amiri Jeans + LV Trainer 2026-10-26)."""
    out = work / f"avatar{size}_{avatar.stem}.png"
    if out.exists():
        return out
    c, inner, outer = size / 2, size / 2 - 12 * size / 300, size / 2 - 2 * size / 300
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(avatar), "-vf",
                    f"scale={size}:{size},format=rgba,geq=r='if(lt(hypot(X-{c},Y-{c}),{inner}),r(X,Y),255)':g='if(lt(hypot(X-{c},Y-{c}),{inner}),g(X,Y),255)':"
                    f"b='if(lt(hypot(X-{c},Y-{c}),{inner}),b(X,Y),255)':a='if(lt(hypot(X-{c},Y-{c}),{outer}),255,0)'",
                    "-frames:v", "1", str(out)], check=True)
    return out


def make_pop_sound(path: Path):
    """A soft, short 'pop' for the avatar (no bass hit, no riser)."""
    if path.exists():
        return path
    sr, dur = 48000, 0.25
    t = np.arange(int(sr * dur)) / sr
    f = 900 * np.exp(-t * 9) + 380
    y = np.sin(2 * math.pi * np.cumsum(f) / sr) * np.exp(-t * 22) * 0.6
    st = np.stack([y, y], 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "-", str(path)],
                   input=(st * 32767).astype("<i2").tobytes(), check=True)
    return path


def make_silence(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.2", str(path)], check=True)
    return path


def make_math_card(work: Path, text: str, cfg) -> Path:
    """The equation in the price style, on a wider card (an equation is ~13 characters)."""
    pc = cfg["price"]
    font = next((f for f in pc["fonts"] if Path(f).exists()), None)
    out = work / f"math_{re.sub(r'[^0-9A-Za-z]', '_', text)}.png"
    if out.exists():
        return out
    esc = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    draw = (f"drawtext=text='{esc}':fontsize={cfg.get('math', {}).get('font_size', 150)}:fontcolor={pc['color']}:"
            f"borderw={pc['outline_px']}:bordercolor={pc['outline_color']}:"
            f"shadowcolor=black@0.45:shadowx=8:shadowy=10:x=(w-text_w)/2:y=(h-text_h)/2")
    if font:
        draw += f":fontfile='{_ffpath(font)}'"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00000000:s=1760x320,format=rgba",
                    "-vf", draw, "-frames:v", "1", str(out)], check=True)
    return out


def _ffpath(p):
    return str(p).replace("\\", "/").replace(":", "\\:")


def make_card(work: Path, text: str, cfg) -> Path:
    """Transparent PNG of the price: bold green text, dark green outline, soft shadow."""
    pc = cfg["price"]
    font = next((f for f in pc["fonts"] if Path(f).exists()), None)
    safe = re.sub(r"[^0-9A-Za-z]", "_", text)
    out = work / f"price_{safe}.png"
    if out.exists():
        return out
    esc = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    draw = (f"drawtext=text='{esc}':fontsize={pc['font_size']}:fontcolor={pc['color']}:"
            f"borderw={pc['outline_px']}:bordercolor={pc['outline_color']}:"
            f"shadowcolor=black@0.45:shadowx=8:shadowy=10:x=(w-text_w)/2:y=(h-text_h)/2")
    if font:
        draw += f":fontfile='{_ffpath(font)}'"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00000000:s=1100x360,format=rgba",
                    "-vf", draw, "-frames:v", "1", str(out)], check=True)
    return out


def make_chime_sound(path: Path):
    """Synthesised 'payment approved' chime (Apple Pay style, not Apple's sound): two soft bright notes, rising."""
    if path.exists():
        return path
    sr, dur = 48000, 1.1
    t = np.arange(int(sr * dur)) / sr

    def note(start, f0, amp, decay):
        tt = np.clip(t - start, 0, None)
        on = (t >= start).astype(float)
        attack = np.clip(tt / 0.004, 0, 1)
        tone = np.sin(2 * math.pi * f0 * tt) + 0.12 * np.sin(4 * math.pi * f0 * tt) + 0.04 * np.sin(6 * math.pi * f0 * tt)
        return on * amp * attack * tone * np.exp(-decay * tt)

    y = note(0.0, 1318.5, 0.55, 9.0) + note(0.10, 1975.5, 0.6, 6.0)  # E6 then B6
    y /= np.max(np.abs(y)) / 0.6
    d = int(sr * 0.006)
    st = np.stack([y, np.concatenate([np.zeros(d), y[:-d]])], 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "-",
                    "-af", "aecho=0.8:0.4:35|60:0.15|0.08", str(path)], input=(st * 32767).astype("<i2").tobytes(), check=True)
    return path


def price_sound(skill: Path, cfg) -> Path:
    """assets/cash.wav if I dropped my own there; otherwise the chosen built-in.
    'rotate' alternates chime/register each video (state in work/cash_sound_state.json)."""
    own = skill / "assets" / "cash.wav"
    if own.exists():
        return own
    sound = cfg["price"].get("sound", "chime")
    if sound == "rotate":
        state = skill / "work" / "cash_sound_state.json"
        last = ""
        if state.exists():
            try:
                last = json.loads(state.read_text()).get("last", "")
            except Exception:
                pass
        sound = "register" if last == "chime" else "chime"
        state.parent.mkdir(exist_ok=True)
        state.write_text(json.dumps({"last": sound}))
    if sound == "register":
        return make_cash_sound(skill / "assets" / "sfx_register.wav")
    return make_chime_sound(skill / "assets" / "sfx_chime.wav")


def make_cash_sound(path: Path):
    """Synthesised cash register 'cha-ching': drawer clack, then two bright bell strikes. Replace the file to use your own."""
    if path.exists():
        return path
    sr, dur = 48000, 1.4
    t = np.arange(int(sr * dur)) / sr
    rng = np.random.default_rng(7)
    y = np.zeros_like(t)
    # drawer clack: short filtered noise burst + low thump
    clack = rng.standard_normal(len(t)) * np.exp(-55 * t) * (t < 0.09)
    clack = np.convolve(clack, np.ones(6) / 6, mode="same")
    y += 0.35 * clack + 0.25 * np.sin(2 * math.pi * 140 * t) * np.exp(-30 * t)

    def bell(start, f0, amp, decay):
        tt = np.clip(t - start, 0, None)
        on = (t >= start).astype(float)
        partials = [(1.0, 1.0), (2.0, 0.45), (2.76, 0.3), (5.4, 0.12)]
        return on * amp * sum(a * np.sin(2 * math.pi * f0 * r * tt) for r, a in partials) * np.exp(-decay * tt)

    y += bell(0.07, 1760, 0.32, 7)   # "cha"
    y += bell(0.19, 2637, 0.40, 4.5)  # "ching"
    y /= np.max(np.abs(y)) / 0.7
    # tiny stereo spread and room
    left = y
    right = np.concatenate([np.zeros(int(sr * 0.008)), y[:-int(sr * 0.008)]])
    st = np.stack([left, right], 1)
    pcm = (st * 32767).astype("<i2").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "-",
                    "-af", "aecho=0.8:0.5:40|70:0.18|0.1", str(path)], input=pcm, check=True)
    return path


def price_filters(prices, first_input, base, cfg, W=1920, H=1080):
    """Video lines overlaying each price card (pop-in, hold, fade) onto `base`; returns (lines, new_base)."""
    pc = cfg["price"]
    lines, last = [], base
    fo = 0.3
    for k, p in enumerate(prices):
        hold = p.get("hold", pc["hold_seconds"])
        idx = first_input + 2 * k
        cx, cy = p.get("center", pc["center"])[0] * W, p.get("center", pc["center"])[1] * H
        if p.get("motion") == "slide_right":
            # his editors' avatar move: slides in from off the right edge, ease-out ~0.45 s, no scale pop, quick fade out
            lines.append(f"[{idx}:v]format=rgba,fade=t=out:st={hold - 0.12:.2f}:d=0.12:alpha=1,"
                         f"setpts=PTS-STARTPTS+{p['out']:.3f}/TB[pr{k}]")
            u = f"min(1,max(0,(t-{p['out']:.3f})/0.45))"
            x = f"{cx:.0f}-w/2+({W}+4-({cx:.0f}-w/2))*pow(1-{u},3)"
            lines.append(f"[{last}][pr{k}]overlay=x='{x}':y='{cy:.0f}-h/2':eval=frame:eof_action=pass[vp{k}]")
            last = f"vp{k}"
            continue
        # pop: 0.55x -> 1.12x overshoot -> 1.0x in 0.28 s
        s = "if(lt(t,0.16),0.55+0.57*t/0.16,if(lt(t,0.28),1.12-0.12*(t-0.16)/0.12,1))"
        lines.append(f"[{idx}:v]format=rgba,scale=w='2*trunc(iw*{s}/2)':h='2*trunc(ih*{s}/2)':eval=frame,"
                     f"fade=t=in:d=0.08:alpha=1,fade=t=out:st={hold - fo:.2f}:d={fo}:alpha=1,"
                     f"setpts=PTS-STARTPTS+{p['out']:.3f}/TB[pr{k}]")
        lines.append(f"[{last}][pr{k}]overlay=x='{cx:.0f}-w/2':y='{cy:.0f}-h/2':eval=frame:eof_action=pass[vp{k}]")
        last = f"vp{k}"
    return lines, last


def price_audio(prices, first_input, cfg):
    pc = cfg["price"]
    lines, labels = [], []
    for k, p in enumerate(prices):
        idx = first_input + 2 * k + 1
        db = ({**RATING_DEFAULTS, **cfg.get("rating", {})}["sound_db"] if p.get("rating") else
              p.get("sound_db", pc["cash_db"]))
        lines.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={db}dB,"
                     f"adelay={int(p['out'] * 1000)}:all=1[cash{k}]")
        labels.append(f"[cash{k}]")
    return lines, labels
