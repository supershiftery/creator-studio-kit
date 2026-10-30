"""Burned-in captions (user 2026-10-23: "build out a caption setting ... off by default ... preset fonts ... the fonts that
everyone uses"). OFF unless the project has settings.captions = {"on": true, "style": "<preset>"}; the user's standing rule is
no captions (gaming: no bottom captions, reviews never), so this only ever runs when ticked per project.

    python captions.py <project dir> <video.mp4>     burn into the render in place (the step recipes/__init__.py adds)
    python captions.py --restore <project dir> <video.mp4>   clean render back (review intro-only re-join)
    python captions.py --previews                    ui/captions/<preset>.png + presets.json (the New Project dropdown)
    python captions.py --sample <video> <out.mp4> --style bold [--t0 60 --t1 90]   try a style on a piece of any video

Words come from the render itself (GPU whisper, {{KIT}}/tools\\whisper_gpu.py), so they match whatever the pipeline
cut, joined or sped up. The uncaptioned render is kept in <project>\\_captions\\ so changing the style (or turning captions
off) re-burns / restores without rebuilding. Skips the intro (it has its own titles) unless settings.captions.intro = true.
Output: H.264 High yuv420p (NVENC, cq 17 finals / 21 drafts), audio copied (AAC).

Presets (research 2026-10-23): Montserrat is the most used caption font (Submagic: 61% of 2M short + long videos), bold
weight, white with a black outline; "pop" styles show 1-3 words in caps with the spoken word highlighted (Hormozi = Montserrat
Black + yellow, MrBeast = Komika Axis); long-form subtitles are one line of a phrase; YouTube's own CC = Roboto on a black box.
A font that isn't in app\\fonts falls back down its list (Montserrat -> Poppins, Komika Axis -> Bangers -> Anton,
The Bold Font -> Anton); drop the .ttf into app\\fonts and re-run --previews."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FONTS = APP / "fonts"
UI_DIR = APP.parent / "ui" / "captions"
sys.path.insert(0, r"{{KIT}}/tools")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import caption_fixes as CF   # noqa: E402  AI typo pass + the editor's manual fixes (2026-10-29)

# family names as libass sees them (nameID 1) -> the file that has to be in app\fonts
FONT_FILES = {"Montserrat Black": "Montserrat-Black.ttf", "Montserrat ExtraBold": "Montserrat-ExtraBold.ttf", "Montserrat": "Montserrat-Bold.ttf",
              "Komika Axis": "KOMIKAX_.ttf", "Bangers": "Bangers-Regular.ttf", "The Bold Font": "THEBOLDFONT.ttf", "Anton": "Anton-Regular.ttf",
              "Poppins Black": "Poppins-Black.ttf", "Poppins ExtraBold": "Poppins-ExtraBold.ttf", "Poppins": "Poppins-Bold.ttf",
              "Roboto Medium": "Roboto-Medium.ttf", "Roboto": "Roboto-Bold.ttf", "Bebas Neue": "BebasNeue-Regular.ttf",
              "Poppins SemiBold": "Poppins-SemiBold.ttf", "Poppins Medium": "Poppins-Medium.ttf", "Courier Prime": "CourierPrime-Bold.ttf"}

# size / outline / shadow / margin are fractions of the video height; colours are RGB hex. Pop styles sit at 22 % up,
# above the lower-third graphics (phone code card, gaming IP cards, Shein test 2026-10-23); subtitle styles stay low.
PRESETS = {
    "clean": {"label": "Clean subtitles · Montserrat Bold", "fonts": [("Montserrat", 1), ("Poppins", 1)], "size": .074, "color": "FFFFFF",
              "outline": .006, "shadow": .003, "caps": False, "words": 7, "chars": 38, "hl": None, "margin": .07},
    "bold": {"label": "Bold pop (Hormozi) · Montserrat Black", "fonts": [("Montserrat Black", 0), ("Poppins Black", 0)], "size": .088, "color": "FFFFFF",
             "outline": .009, "shadow": .004, "caps": True, "words": 3, "chars": 18, "hl": "FFD60A", "margin": .22},
    "beast": {"label": "MrBeast style · Komika Axis", "fonts": [("Komika Axis", 0), ("Bangers", 0), ("Anton", 0)], "size": .09, "color": "FFFFFF",
              "outline": .008, "shadow": .005, "caps": True, "words": 2, "chars": 14, "hl": "4BFF5A", "margin": .22, "pop": 112},
    "boldfont": {"label": "The Bold Font · tall caps", "fonts": [("The Bold Font", 0), ("Anton", 0)], "size": .1, "color": "FFFFFF",
                 "outline": .006, "shadow": .003, "caps": True, "words": 3, "chars": 18, "hl": "FF3B3B", "margin": .22},
    # Gling's "Doug" preset, copied from Gling's own source (C:\Program Files\Gling\resources\app.asar, captions presets,
    # 2026-10-23): Anton, fontSize 110 x 1.5 = 165 px on the video's own canvas (1080p), white, black stroke lineWidth 32
    # (half of it, 16 px, lands outside the glyph), black shadow offset 2/2, not caps; the spoken word takes mainColor /
    # secondaryColor / tertiaryColor in turn per caption group (red #FF0000 -> yellow #FFFF00 -> green #00FF00 -> red...).
    # The whole group shows at once (no word-by-word reveal), the current word coloured. Haul intros use it (user 2026-10-23).
    "doug": {"label": "Doug (Gling) · Anton, red/yellow/green", "fonts": [("Anton", 0)], "size": 165 / 1080, "color": "FFFFFF",
             "outline": 16 / 1080, "shadow": 2 / 1080, "caps": False, "words": 3, "chars": 20, "hl": "FF0000",
             "hl_cycle": ["FF0000", "FFFF00", "00FF00"], "pop": 100, "margin": .1, "no_orphan": True},
    # Doug on a vertical Short (1080x1920, user 2026-10-23): sizes here are fractions of the HEIGHT, so the 1080p numbers
    # would come out 293 px tall. Same look at 120 px Anton (Anton is narrow: 16 chars fit 1080 wide with the side margins),
    # 12 px outline, raised to 30 % up so the Shorts title / buttons at the bottom don't cover it.
    "doug_v": {"label": "Doug vertical (Short) · Anton, red/yellow/green", "fonts": [("Anton", 0)], "size": 120 / 1920, "color": "FFFFFF",
               "outline": 12 / 1920, "shadow": 2 / 1920, "caps": False, "words": 3, "chars": 16, "hl": "FF0000",
               "hl_cycle": ["FF0000", "FFFF00", "00FF00"], "pop": 100, "margin": .30, "no_orphan": True, "pick": False},
    "youtube": {"label": "YouTube CC box · Roboto", "fonts": [("Roboto Medium", 0), ("Roboto", 1)], "size": .064, "color": "FFFFFF",
                "outline": .008, "shadow": 0, "caps": False, "words": 8, "chars": 42, "hl": None, "margin": .06, "box": "000000", "box_alpha": 0x40},
    # 2026-10-29 (friends asked for the caption looks popular on YouTube / Shorts now): free Google Fonts only (Poppins,
    # Anton, Bebas Neue, Courier Prime; OFL files in app\fonts). Clean looks only: no bursts, emojis, shakes or bounces
    # (no-corny-effects rule); the one animation is a 90 ms scale-in on "single". "low": sits at the bottom, so the picker
    # greys it out on gaming projects (no bottom captions on Minecraft videos).
    "single": {"label": "One word · big pop", "fonts": [("Poppins Black", 0), ("Anton", 0)], "size": .11, "color": "FFFFFF",
               "outline": .009, "shadow": .004, "caps": True, "words": 1, "chars": 14, "hl": None, "margin": .22, "anim": (80, 90)},
    "karaoke": {"label": "Karaoke fill · Poppins ExtraBold", "fonts": [("Poppins ExtraBold", 0), ("Poppins", 1)], "size": .072, "color": "FFFFFF",
                "outline": .007, "shadow": .003, "caps": True, "words": 4, "chars": 24, "hl": "FFC83D", "margin": .22, "karaoke": True},
    "highlighter": {"label": "Highlighter box · spoken word on purple", "fonts": [("Poppins ExtraBold", 0), ("Poppins", 1)], "size": .076, "color": "FFFFFF",
                    "outline": .007, "shadow": .003, "caps": True, "words": 3, "chars": 20, "hl": "FFFFFF", "margin": .22,
                    "word_box": "7C3AED", "box_pad": .012},
    "keywords": {"label": "Two-tone keywords · Anton", "fonts": [("Anton", 0)], "size": .1, "color": "FFFFFF",
                 "outline": .007, "shadow": .004, "caps": True, "words": 4, "chars": 22, "hl": "FFB020", "margin": .22, "keywords": True},
    "neon": {"label": "Soft neon glow · Bebas Neue", "fonts": [("Bebas Neue", 0), ("Anton", 0)], "size": .1, "color": "FFFFFF",
             "outline": .002, "shadow": 0, "caps": True, "words": 3, "chars": 20, "hl": None, "margin": .22, "outline_color": "38E8FF",
             "glow": "00C8FF", "glow_size": .014, "spacing": .002},
    "podcast": {"label": "Podcast lower captions · Poppins SemiBold", "fonts": [("Poppins SemiBold", 0), ("Poppins", 1)], "size": .066, "color": "B8B8B8",
                "outline": .003, "shadow": .003, "caps": False, "words": 8, "chars": 40, "hl": "FFFFFF", "pop": 100, "margin": .07, "low": True},
    "minimal": {"label": "Minimal caps · Poppins Medium", "fonts": [("Poppins Medium", 0), ("Poppins", 1)], "size": .062, "color": "FFFFFF",
                "outline": .002, "shadow": .002, "caps": True, "words": 5, "chars": 30, "hl": None, "margin": .08, "spacing": .004, "low": True},
    "typewriter": {"label": "Typewriter · Courier Prime", "fonts": [("Courier Prime", 1), ("Roboto", 1)], "size": .066, "color": "FFFFFF",
                   "outline": .012, "shadow": 0, "caps": False, "words": 5, "chars": 26, "hl": None, "margin": .1, "box": "000000",
                   "box_alpha": 0x50, "reveal": True, "low": True},
}
for _k in ("clean", "youtube"):   # the older subtitle looks sit at the bottom too
    PRESETS[_k]["low"] = True
for _k in ("single", "karaoke", "highlighter", "keywords", "neon", "podcast", "minimal", "typewriter"):
    PRESETS[_k]["fit"] = True
# sizes: the first Chime captions (Arial 64 px at 1080p = .059) were "very small" (user 2026-10-23), so every preset is
# bigger than that; the default is the most used pop look
DEFAULT = "bold"


def style_for(settings):
    """the preset key a project's settings ask for (settings.captions = true | {"on", "style"}); None = captions off"""
    cfg = (settings or {}).get("captions")
    cfg = {"on": True} if cfg is True else (cfg or {})
    if not cfg.get("on"):
        return None
    return cfg.get("style") if cfg.get("style") in PRESETS else DEFAULT


def where_of(settings):
    """where the captions go: "all" (whole video) | "bookends" (intro and ending only); the editor's Captions tab + New Project"""
    cfg = (settings or {}).get("captions")
    return cfg.get("where") if isinstance(cfg, dict) and cfg.get("where") == "bookends" else "all"


def keep_where(words, settings, dur=None, head=0.0):
    """"Intro and ending only" (user 2026-10-29: some people want the intro and ending, some the whole video): the words in
    the opening (the intro, at least 15 s) and the last 30 s (at most the last 10 %) keep their captions; the rest go."""
    if where_of(settings) != "bookends" or not words:
        return words
    dur = dur or max(w["e"] for w in words)
    head, tail = max(head, 15.0), dur - min(30.0, dur * 0.1)
    return [w for w in words if w["s"] < head or w["s"] >= tail]


def font_for(preset):
    for fam, bold in PRESETS[preset]["fonts"]:
        if (FONTS / FONT_FILES.get(fam, "-")).exists():
            return fam, bold
    return PRESETS[preset]["fonts"][-1]


def _bgr(rgb, alpha=0):
    return f"&H{alpha:02X}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def _t(sec):
    sec = max(0.0, sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def chunks(words, P):
    """words [{w,s,e}] -> caption groups: max words / chars per preset, new group after a sentence end or a 0.6 s pause"""
    out, cur = [], []
    merged = []
    for w in words:   # Whisper splits "30" "%", "designer" ".com", "don" "'t": glue them back (as tools/trim_render.py does)
        txt = w["w"].strip()
        if not txt:
            continue
        if merged and (txt[0] in ".%-'’," or txt.startswith("'")) and w["s"] - merged[-1]["e"] < .3:
            merged[-1] = {**merged[-1], "w": merged[-1]["w"] + txt, "e": w["e"]}
        else:
            merged.append({**w, "w": txt})
    for w in merged:
        txt = w["w"]
        if cur and (len(cur) >= P["words"] or len(" ".join(x["w"] for x in cur + [w])) > P["chars"] or w["s"] - cur[-1]["e"] > .6
                    or re.search(r"[.?!]$", cur[-1]["w"])):
            out.append(cur)
            cur = []
        cur.append({**w, "w": txt})
    if cur:
        out.append(cur)
    if P.get("no_orphan"):   # a lone sentence-ending word ("it.") joins the group before it (haul intro, 2026-10-23)
        merged_out = []
        for g in out:
            if (merged_out and len(g) == 1 and re.search(r"[.?!]$", g[0]["w"]) and len(merged_out[-1]) <= P["words"]
                    and not re.search(r"[.?!]$", merged_out[-1][-1]["w"]) and g[0]["s"] - merged_out[-1][-1]["e"] < .5
                    and len(" ".join(x["w"] for x in merged_out[-1] + g)) <= P["chars"] + 6):
                merged_out[-1] = merged_out[-1] + g
            else:
                merged_out.append(g)
        out = merged_out
    return out


def _shown(txt, P):
    if P["caps"]:   # pop styles: caps, no trailing commas / full stops (keep ? and !)
        txt = re.sub(r"[,.;:]+$", "", txt).upper()
    return txt.replace("{", "(").replace("}", ")")


STOP = set("a an the and or but so if of to in on at by for with from as is are was were be been am i you he she it we they me my "
           "your his her its our their this that these those there here just like really very do does did have has had not no yes "
           "can could will would should what when where who how why all some any one get got go going gonna wanna let lets im it's "
           "i'm you're that's don't dont about into out up down then than them".split())


def _keyword(txts):
    """two-tone styles: the one word in a group worth colouring (numbers / prices first, then the longest non-filler word)"""
    best, score = None, 0
    for k, t in enumerate(txts):
        bare = re.sub(r"[^\w$%]", "", t).lower()
        if not bare or bare in STOP:
            continue
        s = len(bare) + (10 if re.search(r"[\d$%]", bare) else 0)
        if s > score and (len(bare) >= 4 or s >= 10):
            best, score = k, s
    return best


def build_ass(words, w, h, preset, start=0.0, margin=None, quiet=(), shown=None):
    """shown: a list that gets each caption group as it is drawn ({s, e, text}) for the editor (captions.json)"""
    P = PRESETS[preset]
    fam, bold = font_for(preset)
    box = "box" in P
    mv = round((P['margin'] if margin is None else margin) * h)
    # "fit" styles size off the short side, so a vertical 1080x1920 Short gets the same look as 1080p (not 1.8x wider text)
    u = min(w, h) if P.get("fit") else h
    spacing = round(P.get("spacing", 0) * u)
    # karaoke: libass fills SecondaryColour -> PrimaryColour as each word is said ({\kf}), so the fill colour goes first
    prim, sec = (P["hl"], P["color"]) if P.get("karaoke") else (P["color"], P["color"])
    outc = _bgr(P.get("outline_color", "000000"))

    def style(name, prim, sec, outline_c, back_c, border, outline, shadow):
        return (f"Style: {name},{fam},{round(P['size'] * u)},{prim},{sec},{outline_c},{back_c},{-1 if bold else 0},0,0,0,100,100,{spacing},0,"
                f"{border},{outline},{shadow},2,{round(.06 * w)},{round(.06 * w)},{mv},1")
    styles = [style("Cap", _bgr(prim), _bgr(sec), _bgr(P.get('box', '000000'), P.get('box_alpha', 0)) if box else outc,
                    '&H80000000' if not box else _bgr('000000', 0xFF), 3 if box else 1, max(1, round(P['outline'] * u)), round(P['shadow'] * u))]
    if P.get("word_box"):   # opaque box (BorderStyle 3) behind the spoken word only: the other words in that layer are invisible
        styles.append(style("Box", _bgr(P["hl"]), _bgr(P["hl"]), _bgr(P["word_box"]), _bgr("000000", 0xFF), 3, max(1, round(P["box_pad"] * u)), 0))
    if P.get("glow"):   # wide blurred outline under the text, the text itself invisible in that layer
        styles.append(style("Glow", _bgr(P["color"], 0xFF), _bgr(P["color"], 0xFF), _bgr(P["glow"], 0x30), _bgr("000000", 0xFF), 1,
                            max(1, round(P["glow_size"] * u)), 0))
    head = ("[Script Info]\nScriptType: v4.00+\nWrapStyle: " + ("0" if P.get("fit") else "2") + "\nScaledBorderAndShadow: yes\n"   # fit: wraps on a narrow Short
            f"PlayResX: {w}\nPlayResY: {h}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + "\n".join(styles) + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev = []
    hide = "{\\alpha&HFF&}"
    groups = chunks([x for x in words if x["s"] >= start and not any(q0 - .2 <= x["s"] < q1 for q0, q1 in quiet)], P)
    for i, g in enumerate(groups):
        g0 = g[0]["s"]
        nxt = groups[i + 1][0]["s"] if i + 1 < len(groups) else g[-1]["e"] + 1
        g1 = min(g[-1]["e"] + .3, nxt)
        txts = [_shown(x["w"], P) for x in g]
        if shown is not None:
            shown.append({"s": round(g0, 3), "e": round(g1, 3), "text": " ".join(txts)})
        if P.get("glow"):
            ev.append(f"Dialogue: 0,{_t(g0)},{_t(g1)},Glow,,0,0,0,,{{\\blur{max(2, round(P['glow_size'] * u * .8))}}}{' '.join(txts)}")
        if P.get("karaoke"):   # one event; each word fills over the time until the next word starts
            parts = []
            for j, x in enumerate(g):
                d = (g[j + 1]["s"] if j + 1 < len(g) else x["e"]) - x["s"]
                parts.append(f"{{\\kf{max(1, round(d * 100))}}}{txts[j]}")
            ev.append(f"Dialogue: 1,{_t(g0)},{_t(g1)},Cap,,0,0,0,,{' '.join(parts)}")
            continue
        if P.get("reveal"):   # typewriter: each word appears as it's said; the unsaid ones hold their place, invisible
            for j, x in enumerate(g):
                a = g0 if j == 0 else x["s"]
                b = g[j + 1]["s"] if j + 1 < len(g) else g1
                if b - a < .01:
                    continue
                said, rest = " ".join(txts[:j + 1]), " ".join(txts[j + 1:])
                ev.append(f"Dialogue: 1,{_t(a)},{_t(b)},Cap,,0,0,0,,{said}" + (f" {hide}{rest}" if rest else ""))
            continue
        if P.get("anim"):   # quick scale-in on each new caption (single word style)
            s0, ms = P["anim"]
            ev.append(f"Dialogue: 1,{_t(g0)},{_t(g1)},Cap,,0,0,0,,{{\\fscx{s0}\\fscy{s0}\\t(0,{ms},\\fscx100\\fscy100)}}{' '.join(txts)}")
            continue
        if P.get("keywords"):   # two-tone: the group's keyword stays coloured the whole time
            k = _keyword(txts)
            parts = [f"{{\\c{_bgr(P['hl'])}}}{t}{{\\c{_bgr(P['color'])}}}" if j == k else t for j, t in enumerate(txts)]
            ev.append(f"Dialogue: 1,{_t(g0)},{_t(g1)},Cap,,0,0,0,,{' '.join(parts)}")
            continue
        if not P["hl"]:
            ev.append(f"Dialogue: 1,{_t(g0)},{_t(g1)},Cap,,0,0,0,,{' '.join(txts)}")
            continue
        if P.get("word_box"):
            for j, x in enumerate(g):
                a = g0 if j == 0 else x["s"]
                b = g[j + 1]["s"] if j + 1 < len(g) else g1
                if b - a < .01:
                    continue
                # the spaces round the spoken word stay hidden too (a visible space glyph draws its own box sliver)
                before, after = " ".join(txts[:j]), " ".join(txts[j + 1:])
                boxed = (hide + before + " " if before else "") + "{\\r}" + txts[j] + (hide + " " + after if after else "")
                plain = " ".join(hide + t + "{\\r}" if k == j else t for k, t in enumerate(txts))
                ev.append(f"Dialogue: 0,{_t(a)},{_t(b)},Box,,0,0,0,,{boxed}")
                ev.append(f"Dialogue: 1,{_t(a)},{_t(b)},Cap,,0,0,0,,{plain}")
            continue
        for j, x in enumerate(g):   # one event per spoken word: that word coloured (and popped), the rest plain
            a = g0 if j == 0 else x["s"]
            b = g[j + 1]["s"] if j + 1 < len(g) else g1
            if b - a < .01:
                continue
            pop = P.get("pop", 106)
            hl = P["hl_cycle"][i % len(P["hl_cycle"])] if P.get("hl_cycle") else P["hl"]   # Doug: colour per group
            tag = f"{{\\c{_bgr(hl)}" + (f"\\fscx{pop}\\fscy{pop}" if pop != 100 else "") + "}"
            parts = [f"{tag}{t}{{\\r}}" if k == j else t for k, t in enumerate(txts)]
            ev.append(f"Dialogue: 0,{_t(a)},{_t(b)},Cap,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(ev) + "\n"


def _filt(ass):
    esc = lambda p: str(p).replace("\\", "/").replace(":", "\\:")   # noqa: E731
    return f"ass='{esc(ass)}':fontsdir='{esc(FONTS)}'"


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(video)],
                       capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    return s["width"], s["height"]


def transcribe(video, cache, vocab=()):
    st = os.stat(video)
    key = f"{st.st_size}:{int(st.st_mtime)}"
    old = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
    if old.get("key") == key:
        return old["words"]
    import numpy as np
    from whisper_gpu import load
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    model, where = load("medium.en")
    if where.startswith("cpu"):
        model, where = load("small.en")
    print(f"captions: transcribing the render ({len(a) / 16000 / 60:.1f} min, whisper {where})", flush=True)
    segs, _ = model.transcribe(a, word_timestamps=True, condition_on_previous_text=False, vad_filter=True, language="en",
                             hotwords=", ".join(vocab) or None)   # project vocabulary (brand names) spelled right
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in (s.words or [])]
    json.dump({"key": key, "words": words}, open(cache, "w", encoding="utf-8"))
    print(f"captions: {len(words)} words", flush=True)
    return words


def burn(src, dst, ass, final, t0=None, t1=None):
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats"] + (["-ss", str(t0)] if t0 is not None else []) + ["-i", str(src)] + \
          (["-t", str(t1 - t0)] if t1 is not None else []) + \
          ["-map", "0:v:0", "-map", "0:a?", "-vf", _filt(ass) + ",format=yuv420p", "-c:v", "h264_nvenc", "-profile:v", "high", "-preset", "p5",
           "-rc", "vbr", "-cq", "17" if final else "21", "-b:v", "0", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dst)]
    if t0 is not None:   # a sample piece: audio re-encoded so the cut is clean
        cmd[cmd.index("-c:a") + 1] = "aac"
    subprocess.run(cmd, check=True)


def _intro_end(proj):
    """seconds of intro at the head of the render (the intro has its own titles); 0 when unknown"""
    try:
        sys.path.insert(0, str(APP))
        import store
        import recipes
        doc = store.read_json(Path(proj) / "studio.json")
        return float(recipes.get(doc["type"]).timeline_info(doc).get("offset") or 0)
    except Exception as e:  # noqa
        print(f"captions: intro length unknown ({type(e).__name__}), captioning from the start")
        return 0.0


def restore(proj, video):
    """put the clean render back if the file is still the one we burned (before a step that edits the render in place)"""
    proj, video = Path(proj), Path(video)
    work = proj / "_captions"
    state_f = work / "state.json"
    state = json.load(open(state_f, encoding="utf-8")) if state_f.exists() else {}
    me, clean = state.get(video.name) or {}, work / f"clean - {video.name}"
    vst = video.stat() if video.exists() else None
    if vst and me.get("size") == vst.st_size and me.get("mtime") == int(vst.st_mtime) and clean.exists():
        os.replace(clean, video)
        state.pop(video.name, None)
        json.dump(state, open(state_f, "w"), indent=1)
        print("captions: clean render put back")
    else:
        print("captions: nothing to restore")


def _quiet(proj, offset):
    """render-time windows where a big graphic owns the bottom of the frame: the phone pipeline's promo-code card
    (edit/graphics/events.json, main-video times + the intro). Captions pause there (Shein test 2026-10-23: they sat on the card)."""
    f = Path(proj) / "edit" / "graphics" / "events.json"
    try:
        ev = json.load(open(f, encoding="utf-8")) if f.exists() else []
        return [(e["t"] + offset, e["t"] + e["dur"] + offset) for e in ev if e.get("kind") == "code"]
    except Exception:  # noqa
        return []


def run(proj, video):
    proj, video = Path(proj), Path(video)
    doc = json.load(open(proj / "studio.json", encoding="utf-8"))
    cfg = (doc.get("settings") or {}).get("captions") or {}
    cfg = {"on": True} if cfg is True else cfg   # older projects stored a plain true
    vocab = (doc.get("settings") or {}).get("vocabulary") or []
    work = proj / "_captions"
    state_f = work / "state.json"
    state = json.load(open(state_f, encoding="utf-8")) if state_f.exists() else {}
    me = state.get(video.name) or {}
    clean = work / f"clean - {video.name}"
    vst = video.stat() if video.exists() else None
    ours = bool(vst and me.get("size") == vst.st_size and me.get("mtime") == int(vst.st_mtime))   # the render is the one we burned
    if not cfg.get("on"):
        if ours and clean.exists():   # captions turned off after a burn: put the clean render back
            os.replace(clean, video)
            state.pop(video.name, None)
            json.dump(state, open(state_f, "w"), indent=1)
            print("captions off: restored the render without captions")
        else:
            print("captions off for this project")
        return
    style = style_for(doc.get("settings"))
    where = where_of(doc.get("settings"))
    intro = bool(cfg.get("intro")) or where == "bookends"   # "intro and ending only" includes the intro
    fsig = CF.signature(doc)   # new manual fixes / undone AI fixes re-burn the render from its clean copy
    if ours and me.get("style") == style and me.get("intro") == intro and me.get("where", "all") == where and me.get("fixes", fsig) == fsig:
        print(f"captions already burned ({style})")
        return
    work.mkdir(exist_ok=True)
    if not ours:   # a fresh render: keep it as the clean source
        os.replace(video, clean)
    off = _intro_end(proj)
    start = 0.0 if intro else off
    words, changes = CF.apply(transcribe(clean, work / f"words - {video.stem}.json", vocab), doc)   # AI typo pass + the editor's fixes
    words = keep_where(words, doc.get("settings"), head=off)
    w, h = probe(clean)
    ass = work / f"{video.stem}.ass"
    quiet = _quiet(proj, off)
    shown = []
    ass.write_text(build_ass(words, w, h, style, start, quiet=quiet, shown=shown), encoding="utf-8")
    CF.record(proj, video.name, words, shown, changes, style)
    fam = font_for(style)[0]
    print(f"captions: {PRESETS[style]['label']} (font {fam}), {w}x{h}, from {start:.1f} s, paused over {len(quiet)} code cards", flush=True)
    tmp = video.with_name(video.stem + " .captions-tmp.mp4")
    try:
        burn(clean, tmp, ass, final="draft" not in video.name.lower())
        os.replace(tmp, video)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        if not video.exists():
            os.replace(clean, video)   # never leave the project without its render
        raise
    st = video.stat()
    state[video.name] = {"size": st.st_size, "mtime": int(st.st_mtime), "style": style, "intro": intro, "where": where, "font": fam,
                         "fixes": fsig}
    json.dump(state, open(state_f, "w"), indent=1)
    print(f"captions burned into {video.name}")


def previews():
    """one PNG per preset on a dark gradient (what libass really draws with the fonts that are installed)"""
    UI_DIR.mkdir(parents=True, exist_ok=True)
    sample = [("This", 0, .3), ("is", .3, .5), ("how", .5, .8), ("your", .8, 1.1), ("captions", 1.1, 1.6), ("look", 1.6, 2.0)]
    meta = []
    for key, P in PRESETS.items():
        words = [{"w": a, "s": s, "e": e} for a, s, e in sample]
        ass_txt = build_ass(words, 640, 360, key, margin=.36)   # same height in every preview
        # show the frame where the 2nd word is spoken (highlight styles) / the whole line (phrase styles)
        ass_f = UI_DIR / f"{key}.ass"
        ass_f.write_text(ass_txt, encoding="utf-8")
        at = 1.3 if P["hl"] else .9
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "gradients=s=640x360:c0=0x2b3a55:c1=0x6b4c3b:x0=0:y0=0:x1=640:y1=360:d=3",
                        "-ss", str(at), "-frames:v", "1", "-vf", _filt(ass_f) + ",crop=640:120:0:150", str(UI_DIR / f"{key}.png")], check=True)
        ass_f.unlink()
        fam = font_for(key)[0]
        meta.append({"key": key, "label": P["label"], "font": fam, "wanted": P["fonts"][0][0], "png": f"captions/{key}.png",
                     "low": bool(P.get("low")), "pick": P.get("pick", True)})
    json.dump(meta, open(UI_DIR / "presets.json", "w"), indent=1)
    print("\n".join(f"{m['key']}: {m['font']}" + ("" if m["font"] == m["wanted"] else f" (stand-in for {m['wanted']})") for m in meta))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--previews"]:
        previews()
    elif a[:1] == ["--restore"]:
        restore(a[1], a[2])
    elif a[:1] == ["--sample"]:
        src, out = a[1], Path(a[2])
        style = a[a.index("--style") + 1] if "--style" in a else DEFAULT
        t0 = float(a[a.index("--t0") + 1]) if "--t0" in a else 0.0
        t1 = float(a[a.index("--t1") + 1]) if "--t1" in a else t0 + 30
        words = [dict(x, s=x["s"] - t0, e=x["e"] - t0) for x in transcribe(src, str(out.with_suffix(".words.json"))) if t0 <= x["s"] < t1]
        w, h = probe(src)
        ass = out.with_suffix(".ass")
        ass.write_text(build_ass(words, w, h, style), encoding="utf-8")
        burn(src, out, ass, final=True, t0=t0, t1=t1)
        print(f"sample: {out}")
    else:
        run(a[0], a[1])
