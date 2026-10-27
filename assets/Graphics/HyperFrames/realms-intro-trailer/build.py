"""Top 5 Realms intro, full-screen "trailer" style, as a VARIATION GENERATOR.

The beats (VO word times, which realm clip plays under which line) are fixed; every variant re-dresses them:
font, accent colour, text treatment, word entry animation, layout, clip-to-clip transition, frame overlay,
colour grade, camera move and XP-bar look. Variants are picked so any two differ on at least 4 of the 6 big axes,
so no two intros look like the same template with new clips.

  python build.py list                 # the 20 variants
  python build.py build 3              # write index.html for variant 3
  python build.py render 1 2 3 ...     # build + render + mix each into renders/realms-intro-v2-<nn>-<slug>.mp4
"""
import json, os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
DUR = 27.2

# ---- beats: clip, start, end, text groups [(t_in, t_out, size, [[(word, t, key)], ...])] ------------------------
B = [
    ("c01-anarchy", 0.00, 1.40, [(0.0, 1.40, "l", [[("MINECRAFT", 0.0, 0)], [("REALMS", 0.64, 1)]])]),
    ("c02-rennmon-street", 1.40, 3.04, [(1.44, 3.04, "xl", [[("STILL", 1.44, 0), ("GOING?", 2.0, 1)]])]),
    ("c03-people", 3.04, 4.80, [(3.04, 3.86, "l", [[("APPARENTLY...", 3.04, 0)]]),
                                (3.92, 4.80, "l", [[("PEOPLE", 3.92, 0), ("ARE", 4.24, 0)], [("HOSTING", 4.40, 1)]])]),
    ("c04-crate", 4.80, 6.24, [(4.88, 6.24, "xl", [[("SECRET", 4.88, 1)], [("GAME", 5.28, 0), ("MODES", 5.60, 0)]])]),
    ("c05-skygen", 6.24, 7.30, [(6.32, 7.30, "xl", [[("SKY", 6.32, 1), ("GEN", 6.48, 1)]])]),
    ("c06-kitpvp", 7.30, 8.80, [(7.36, 8.80, "xl", [[("KIT", 7.36, 1), ("PVP", 7.62, 1)]])]),
    ("c07-prisons", 8.80, 9.52, [(8.88, 9.52, "xl", [[("PRISONS", 8.88, 1)]])]),
    ("c08-limited", 9.52, 11.44, [(9.56, 11.44, "l", [[("ON", 9.56, 0), ("THESE", 9.76, 0)], [("LIMITED", 10.0, 1)], [("SERVERS", 10.64, 0)]])]),
    ("c09-players", 11.44, 13.44, [(11.92, 13.44, "l", [[("ONLY", 11.92, 0), ("UP", 12.32, 0), ("TO", 12.48, 0)], [("10", 12.64, 1), ("PLAYERS", 12.96, 0)]])]),
    ("c10-trials", 13.44, 15.86, [(13.84, 14.58, "l", [[("REALLY", 13.84, 0)], [("CURIOUS", 14.08, 1)]]),
                                  (14.64, 15.86, "l", [[("WHAT'S", 14.64, 0), ("REALLY", 14.96, 0)], [("GOING", 15.2, 0), ("ON?", 15.44, 1)]])]),
    ("c11-dragonforge", 15.86, 16.48, [(15.92, 16.48, "l", [[("MINECRAFT", 15.92, 0)]])]),
    ("c12-lunar-portal", 16.48, 17.12, [(16.48, 17.12, "l", [[("BEDROCK", 16.48, 0)]])]),
    ("c13-village", 17.12, 17.90, [(17.12, 17.90, "l", [[("EDITION", 17.12, 0)], [("REALMS", 17.52, 1)]])]),
    ("c14-starter", 18.16, 19.12, [(18.16, 19.12, "l", [[("IN", 18.16, 0), ("TODAY'S", 18.4, 0)], [("VIDEO", 18.8, 1)]])]),
    ("c15-charmander", 19.12, 21.04, [(19.12, 19.64, "m", [[("WE'RE", 19.12, 0), ("GONNA", 19.36, 0), ("BE", 19.52, 0)]]),
                                      (19.68, 21.04, "l", [[("INVESTIGATING", 19.68, 1)], [("JUST", 20.32, 0), ("THAT", 20.56, 0)]])]),
    ("c16-galaxy", 21.04, 22.64, [(21.04, 22.64, "l", [[("WATCH", 21.04, 0), ("TO", 21.84, 0), ("THE", 22.0, 0)], [("VERY", 22.16, 0), ("END", 22.32, 1)]])]),
    # 22.64 - 25.8 = the hard-cut realm montage (user liked it): always hard cuts, only its text is re-dressed
    ("montage", 22.64, 25.80, [(22.96, 23.58, "l", [[("TRUST", 22.96, 0), ("ME", 23.28, 1)]]),
                               (23.60, 24.98, "m", [[("SOME", 23.6, 0), ("OF", 23.76, 0), ("THESE", 23.84, 0)], [("GAME", 24.0, 0), ("MODES", 24.32, 0)]]),
                               (25.04, 25.80, "xl", [[("SHOCK", 25.04, 0), ("YOU!", 25.44, 1)]])]),
    ("c17-garden", 25.80, DUR, [(25.84, DUR, "xl", [[("TOP", 25.84, 0), ("5", 25.96, 1)], [("REALMS", 26.1, 0)]])]),
]
MONTAGE = [("m0-rennmon", 22.64, 0.64), ("m1-lunar", 23.28, 0.72), ("m2-thunder", 24.0, 0.32),
           ("m3-spectrixious", 24.32, 0.48), ("m4-anarchy", 24.8, 0.24), ("m5-dragonforge", 25.04, 0.76)]
HERO = {"REALMS", "SECRET", "LIMITED", "10", "CURIOUS", "ON?", "VIDEO", "INVESTIGATING", "END", "YOU!", "5"}

# ---- variation axes ------------------------------------------------------------------------------------------------
FONTS = {  # name: (file, avg glyph advance in em for upper case, css extra)
    "barlow": ("BarlowCondensed-BlackItalic.ttf", 0.50, ""),
    "anton": ("Anton-Regular.ttf", 0.50, ""),
    "bebas": ("BebasNeue-Regular.ttf", 0.42, "letter-spacing:.02em;"),
    "archivo": ("ArchivoBlack-Regular.ttf", 0.78, "letter-spacing:-.01em;"),
    "poppins": ("Poppins-Black.ttf", 0.74, "letter-spacing:-.02em;"),
    "lilita": ("LilitaOne-Regular.ttf", 0.56, ""),
    "luckiest": ("LuckiestGuy-Regular.ttf", 0.66, ""),
}
ACCENTS = {"violet": "#8b5cf6", "cyan": "#22d3ee", "gold": "#f5b301", "lime": "#9be22d", "coral": "#ff5a36", "pink": "#ff3d8b"}
TREATS = ["bar", "shadow", "stroke", "box", "outline"]
ENTRIES = ["rise", "punch", "blur", "swipe", "drop", "flip"]
LAYOUTS = ["center", "left", "lower", "stack"]
TRANS = ["push", "cut", "zoom", "wipe", "whip", "slide"]
OVERLAYS = ["none", "letterbox", "frame", "brackets"]
GRADES = ["natural", "punch", "cool", "warm"]
CAMS = ["push", "drift", "pull"]
XPS = ["mc", "pill", "line"]

def variants(n=20, seed=7):
    rng = random.Random(seed)
    out, tries = [], 0
    big = ["font", "accent", "treat", "entry", "layout", "trans"]
    while len(out) < n and tries < 20000:
        tries += 1
        v = {"font": rng.choice(list(FONTS)), "accent": rng.choice(list(ACCENTS)), "treat": rng.choice(TREATS),
             "entry": rng.choice(ENTRIES), "layout": rng.choice(LAYOUTS), "trans": rng.choice(TRANS),
             "overlay": rng.choice(OVERLAYS), "grade": rng.choice(GRADES), "cam": rng.choice(CAMS), "xp": rng.choice(XPS)}
        if v["layout"] == "stack" and FONTS[v["font"]][1] > 0.6:   # giant stacked words only work in condensed faces
            continue
        if any(sum(v[k] == o[k] for k in big) > 2 for o in out):  # every pair differs on >= 4 of the 6 big axes
            continue
        out.append(v)
    for i, v in enumerate(out, 1):
        v["id"] = i
        v["slug"] = f"{v['font']}-{v['treat']}-{v['entry']}-{v['layout']}-{v['trans']}-{v['accent']}"
    return out

# ---- HTML ----------------------------------------------------------------------------------------------------------
BASE = {"m": 104, "l": 150, "xl": 210}
LAYOUT_K = {"center": 1.0, "left": 1.0, "lower": 0.66, "stack": 1.3}
MAXW = {"center": 1720, "left": 1560, "lower": 1300, "stack": 1700}

def fit(size, lines, v):
    k = BASE[size] * LAYOUT_K[v["layout"]]
    if FONTS[v["font"]][1] > 0.6:
        k *= 0.82
    adv = FONTS[v["font"]][1]
    widest = max(sum(len(w) + 0.6 for w, _, _ in ln) for ln in lines)
    pad = 0.5 if v["treat"] in ("bar", "box") else 0.2
    need = (widest * adv + pad * len(max(lines, key=len))) * k
    return round(min(k, k * MAXW[v["layout"]] / need), 1) if need else k

def treat_css(v, acc):
    t = v["treat"]
    if t == "bar":
        return (".wi{color:#fff;text-shadow:0 .05em 0 rgba(0,0,0,.45)}"
                f".key .wi{{color:#fff;background:{acc};padding:0 .14em;text-shadow:none;box-shadow:.05em .06em 0 rgba(0,0,0,.4)}}")
    if t == "shadow":
        return f".wi{{color:#fff;text-shadow:.055em .055em 0 rgba(10,10,16,.85)}}.key .wi{{color:{acc}}}"
    if t == "stroke":
        return (".wi{color:#fff;-webkit-text-stroke:.07em #111;paint-order:stroke fill;text-shadow:0 .06em 0 rgba(0,0,0,.5)}"
                f".key .wi{{color:{acc}}}")
    if t == "box":
        return (f".ln{{background:rgba(12,12,18,.78);padding:.04em .22em .02em;border-left:.09em solid {acc}}}"
                f".wi{{color:#fff}}.key .wi{{color:{acc}}}")
    # outline: keyword hollow
    return (".wi{color:#fff;text-shadow:0 .05em .02em rgba(0,0,0,.6)}"
            f".key .wi{{color:transparent;-webkit-text-stroke:.045em {acc};text-shadow:0 0 .2em rgba(0,0,0,.35)}}")

def layout_css(v):
    L = v["layout"]
    if L == "center":
        return ".grp{left:960px;top:540px;transform:translate(-50%,-50%);text-align:center;align-items:center}"
    if L == "left":
        return ".grp{left:150px;top:560px;transform:translateY(-50%);text-align:left;align-items:flex-start}"
    if L == "lower":
        return ".grp{left:130px;bottom:150px;text-align:left;align-items:flex-start}"
    return ".grp{left:90px;top:540px;transform:translateY(-50%);text-align:left;align-items:flex-start;line-height:.86}"

def overlay_html(v, acc):
    o = v["overlay"]
    if o == "letterbox":
        return '<div class="ov" style="top:0;height:64px;background:#000"></div><div class="ov" style="bottom:0;height:64px;background:#000"></div>'
    if o == "frame":
        return '<div class="ov" style="inset:30px;border:4px solid rgba(255,255,255,.85)"></div>'
    if o == "brackets":
        s = f"position:absolute;width:120px;height:120px;border-color:{acc};border-style:solid;"
        return (f'<div class="ov" style="inset:0"><div style="{s}left:40px;top:40px;border-width:8px 0 0 8px"></div>'
                f'<div style="{s}right:40px;top:40px;border-width:8px 8px 0 0"></div>'
                f'<div style="{s}left:40px;bottom:40px;border-width:0 0 8px 8px"></div>'
                f'<div style="{s}right:40px;bottom:40px;border-width:0 8px 8px 0"></div></div>')
    return ""

GRADE_CSS = {"natural": "none", "punch": "saturate(1.25) contrast(1.08)", "cool": "saturate(1.05) hue-rotate(-8deg) brightness(.97)",
             "warm": "sepia(.14) saturate(1.18) brightness(1.02)"}

def xp_html(v, acc):
    pos = {"center": "left:560px;top:760px;width:800px", "left": "left:150px;top:790px;width:820px",
           "lower": "left:130px;top:960px;width:700px", "stack": "left:90px;top:860px;width:900px"}[v["layout"]]
    if v["xp"] == "mc":
        return (f'<div id="xp" style="position:absolute;{pos};height:34px;background:#1d1f1a;border:5px solid #0b0b0b;opacity:0">'
                '<div id="xpf" style="position:absolute;inset:0;background:#7ed321;transform-origin:0 50%;transform:scaleX(0)"></div>'
                '<div style="position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 40px,rgba(0,0,0,.6) 40px 44px)"></div></div>')
    if v["xp"] == "pill":
        return (f'<div id="xp" style="position:absolute;{pos};height:30px;border-radius:15px;background:rgba(255,255,255,.22);overflow:hidden;opacity:0">'
                f'<div id="xpf" style="position:absolute;inset:0;background:{acc};transform-origin:0 50%;transform:scaleX(0)"></div></div>')
    return (f'<div id="xp" style="position:absolute;{pos};height:12px;background:rgba(255,255,255,.25);opacity:0">'
            f'<div id="xpf" style="position:absolute;inset:0;background:{acc};transform-origin:0 50%;transform:scaleX(0)"></div></div>')

def build(v):
    acc = ACCENTS[v["accent"]]
    ffile, _, fextra = FONTS[v["font"]]
    vids, grps, js, sfx = [], [], [], []
    gi = 0
    TR = 0.32  # transition length; the outgoing clip stays on screen under the incoming one
    clip_beats = [b for b in B if b[0] != "montage"]
    for idx, (clip, t0, t1, groups) in enumerate(B):
        if clip == "montage":
            for name, s, d in MONTAGE:
                vids.append(f'<video id="v-{name}" class="clip vid" src="assets/gameplay/{name}.mp4" muted playsinline '
                            f'data-start="{s}" data-duration="{d}" data-media-start="0" data-track-index="{3 + MONTAGE.index((name, s, d)) % 2}"></video>')
                js.append(f'tl.fromTo("#v-{name}",{{scale:1.14}},{{scale:1,duration:{d},ease:"power1.out"}},{s});')
        else:
            nxt = B[idx + 1] if idx + 1 < len(B) else None
            hold = TR if (nxt and nxt[0] != "montage" and abs(nxt[1] - t1) < 0.01 and v["trans"] != "cut") else 0
            d = round(t1 - t0 + hold, 2)
            vid = f"v{idx}"
            vids.append(f'<video id="{vid}" class="clip vid" src="assets/gameplay/{clip}.mp4" muted playsinline '
                        f'data-start="{t0}" data-duration="{d}" data-media-start="0" data-track-index="{3 + idx % 2}"></video>')
            cam = {"push": ("{scale:1.0}", "{scale:1.09}"), "pull": ("{scale:1.12}", "{scale:1.0}"),
                   "drift": ("{scale:1.08,xPercent:-1.5}", "{scale:1.08,xPercent:1.5}")}[v["cam"]]
            if clip == "c09-players":   # push in on "Players in TC (10)"
                cam = ("{scale:1.0}", '{scale:1.9,transformOrigin:"80% 28%"}')
            js.append(f'tl.fromTo("#{vid}",{cam[0]},Object.assign({cam[1]},{{duration:{d},ease:"none"}}),{t0});')
            prev = B[idx - 1] if idx else None
            if idx and prev[0] != "montage" and abs(prev[2] - t0) < 0.01 and v["trans"] != "cut":
                tr = v["trans"]
                if tr == "push":
                    js.append(f'tl.fromTo("#{vid}",{{xPercent:100}},{{xPercent:0,duration:{TR},ease:"power3.inOut"}},{t0});')
                    js.append(f'tl.to("#v{idx-1}",{{xPercent:-35,duration:{TR},ease:"power3.inOut"}},{t0});')
                elif tr == "zoom":
                    js.append(f'tl.fromTo("#{vid}",{{opacity:0,scale:1.35}},{{opacity:1,scale:1.0,duration:{TR},ease:"power2.out"}},{t0});')
                elif tr == "wipe":
                    js.append(f'tl.fromTo("#{vid}",{{clipPath:"inset(0% 0% 0% 100%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:{TR},ease:"power3.inOut"}},{t0});')
                elif tr == "whip":
                    js.append(f'tl.fromTo("#{vid}",{{xPercent:100,filter:"blur(24px)"}},{{xPercent:0,filter:"blur(0px)",duration:0.24,ease:"power3.out"}},{t0});')
                    js.append(f'tl.to("#v{idx-1}",{{xPercent:-60,filter:"blur(24px)",duration:0.24,ease:"power3.in"}},{t0});')
                elif tr == "slide":
                    js.append(f'tl.fromTo("#{vid}",{{yPercent:100}},{{yPercent:0,duration:{TR},ease:"power3.inOut"}},{t0});')
                    js.append(f'tl.to("#v{idx-1}",{{yPercent:-30,duration:{TR},ease:"power3.inOut"}},{t0});')
                if tr != "cut":
                    sfx.append((t0, "k_whip.wav", 0.10, 0.9))
        for (gin, gout, size, lines) in groups:
            gi += 1
            fs = fit(size, lines, v)
            rows = []
            for ln in lines:
                ws = "".join(f'<span class="w{" key" if k else ""}"><span class="wi" data-t="{t}">{w}</span></span>' for w, t, k in ln)
                rows.append(f'<div class="ln">{ws}</div>')
            grps.append(f'<div id="g{gi}" class="clip grp" data-start="{gin}" data-duration="{round(gout - gin, 2)}" '
                        f'data-track-index="20" style="font-size:{fs}px">{"".join(rows)}</div>')
            for li, ln in enumerate(lines):
                for wi_, (w, t, k) in enumerate(ln):
                    sel = f"#g{gi} .ln:nth-child({li + 1}) .w:nth-child({wi_ + 1}) .wi"
                    js.append(f'enter("{sel}",{t},{1 if w in HERO else 0});')
                    sfx.append((t, "k_passby.wav" if w in HERO else ("k_pop1.wav" if (gi + wi_) % 2 else "k_pop2.wav"),
                                0.09 if w in HERO else 0.07, 1.2 if w in HERO else 0.45))
            if v["layout"] != "stack":
                js.append(f'tl.to("#g{gi}",{{opacity:0,duration:0.08}},{round(gout - 0.08, 2)});')
    # XP bar
    js.append('tl.fromTo("#xp",{opacity:0,scaleX:.6},{opacity:1,scaleX:1,duration:.16,ease:"power2.out"},21.06);')
    js.append('tl.fromTo("#xpf",{scaleX:0},{scaleX:1,duration:1.2,ease:"none"},21.12);')
    js.append('tl.fromTo("#xp",{scale:1.08},{scale:1,duration:.3,ease:"back.out(2)"},22.32);')
    js.append('tl.to("#xp",{opacity:0,duration:.08},22.56);')
    # thin out SFX: never two within 0.3 s (whip wins), pops quiet; XP fill + ding are the signature
    sfx.sort()
    keep = []
    for s in sfx:
        if keep and s[0] - keep[-1][0] < 0.3:
            if s[1] == "k_whip.wav" or (s[1] == "k_passby.wav" and keep[-1][1].startswith("k_pop")):
                keep[-1] = s
            continue
        keep.append(s)
    keep = [s for s in keep if not (21.1 < s[0] < 22.5)]
    keep += [(21.12, "watch-to-the-end-xp-fill.wav", 0.26, 1.2), (22.32, "watch-to-the-end-xp-full.wav", 0.28, 0.58)]
    auds = []
    for i, (t, f, vol, d) in enumerate(sorted(keep)):
        auds.append(f'<audio id="sx{i}" src="assets/sfx/{f}" data-start="{round(t, 2)}" data-duration="{d}" data-track-index="{30 + i % 10}" data-volume="{vol}"></audio>')

    entry = {
        "rise": 'tl.fromTo(s,{yPercent:115,opacity:1},{yPercent:0,opacity:1,duration:.26,ease:"power3.out"},t);',
        "punch": 'tl.fromTo(s,{scale:h?2.2:1.7,opacity:0},{scale:1,opacity:1,duration:.2,ease:"back.out(2.4)"},t);',
        "blur": 'tl.fromTo(s,{filter:"blur(18px)",scale:1.15,opacity:0},{filter:"blur(0px)",scale:1,opacity:1,duration:.24,ease:"power2.out"},t);',
        "swipe": 'tl.fromTo(s,{xPercent:-40,skewX:24,opacity:0},{xPercent:0,skewX:0,opacity:1,duration:.22,ease:"power3.out"},t);',
        "drop": 'tl.fromTo(s,{yPercent:-120,opacity:0},{yPercent:0,opacity:1,duration:.3,ease:"bounce.out"},t);',
        "flip": 'tl.fromTo(s,{rotationX:-95,opacity:0,transformOrigin:"50% 100%"},{rotationX:0,opacity:1,duration:.26,ease:"back.out(1.6)"},t);',
    }[v["entry"]]
    clipw = "overflow:hidden;" if v["entry"] == "rise" else ""
    shade = {"center": "radial-gradient(ellipse at center,rgba(0,0,0,.42) 0%,rgba(0,0,0,.18) 55%,rgba(0,0,0,.35) 100%)",
             "left": "linear-gradient(90deg,rgba(0,0,0,.55) 0%,rgba(0,0,0,.15) 60%,rgba(0,0,0,0) 100%)",
             "lower": "linear-gradient(0deg,rgba(0,0,0,.6) 0%,rgba(0,0,0,0) 45%)",
             "stack": "linear-gradient(90deg,rgba(0,0,0,.5) 0%,rgba(0,0,0,.1) 70%)"}[v["layout"]]
    music = ('{"version":1,"lanes":[{"target":"volume","points":[{"t":0,"v":0},{"t":0.4,"v":0.1},{"t":17.6,"v":0.1},{"t":17.86,"v":0},'
             '{"t":18.1,"v":0},{"t":18.16,"v":0.22},{"t":18.9,"v":0.2},{"t":19.4,"v":0.08},{"t":25.7,"v":0.08},{"t":25.84,"v":0.28},'
             '{"t":26.9,"v":0.26},{"t":27.2,"v":0}]}]}')
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <!-- GENERATED by build.py variant {v['id']} ({v['slug']}, overlay {v['overlay']}, grade {v['grade']}, cam {v['cam']}, xp {v['xp']}); edit build.py, not this file -->
    <style>
      @font-face {{ font-family: "F"; src: url("assets/fonts/{ffile}") format("truetype"); }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #000; }}
      .vid {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; filter: {GRADE_CSS[v['grade']]}; }}
      #shade {{ position: absolute; inset: 0; background: {shade}; }}
      .grp {{ position: absolute; display: flex; flex-direction: column; gap: .04em; font-family: "F"; line-height: .98; white-space: nowrap; {fextra} perspective: 800px; }}
      .ln {{ display: flex; gap: .22em; }}
      .w {{ display: inline-block; {clipw} padding: .04em .02em; }}
      .wi {{ display: inline-block; opacity: 0; }}
      {treat_css(v, acc)}
      {layout_css(v)}
      .ov {{ position: absolute; left: 0; right: 0; pointer-events: none; }}
      #dip {{ position: absolute; inset: 0; background: #000; opacity: 0; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1920" data-height="1080">
      {chr(10).join('      ' + x for x in vids).strip()}
      <div id="shade"></div>
      <div id="dip"></div>
      {chr(10).join('      ' + x for x in grps).strip()}
      {xp_html(v, acc)}
      {overlay_html(v, acc)}
      <audio id="vo" src="assets/vo-norm.wav" data-start="0" data-duration="25.93" data-track-index="10" data-volume="1"></audio>
      <audio id="music" src="assets/music.mp3" data-start="0" data-duration="{DUR}" data-track-index="11" data-volume="1" data-automation='{music}'></audio>
      {chr(10).join('      ' + x for x in auds).strip()}
    <script>
      const tl = gsap.timeline({{ paused: true }});
      const enter = (s, t, h) => {{ {entry} }};
      {chr(10).join('      ' + x for x in js).strip()}
      // the track's own break before the drop: a short dip to black
      tl.to("#dip", {{ opacity: 1, duration: 0.14 }}, 17.76); tl.set("#dip", {{ opacity: 0 }}, 18.16);
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = tl;
    </script>
    </div>
  </body>
</html>
"""
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return v

def render(v):
    build(v)
    out = os.path.join(HERE, "renders", f"realms-intro-v2-{v['id']:02d}-{v['slug']}")
    t = time.time()
    r = subprocess.run(["npx", "--yes", "hyperframes@0.8.180", "render", "--fps", "60", "--output", out + "-raw.mp4"],
                       cwd=HERE, capture_output=True, text=True, shell=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:]); return None
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out + "-raw.mp4", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-crf", "18", "-preset", "medium", "-af",
                    "acompressor=threshold=-24dB:ratio=3:attack=8:release=150:makeup=2,loudnorm=I=-17:TP=-1.5:LRA=5",
                    "-ar", "48000", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out + ".mp4"], check=True)
    os.remove(out + "-raw.mp4")
    print(f"v{v['id']:02d} {v['slug']} rendered in {time.time() - t:.0f}s", flush=True)
    return out + ".mp4"

if __name__ == "__main__":
    vs = variants()
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for v in vs:
            print(f"{v['id']:2d} {v['slug']:52s} {v['overlay']:9s} {v['grade']:8s} {v['cam']:6s} {v['xp']}")
        with open(os.path.join(HERE, "variants.json"), "w") as f:
            json.dump(vs, f, indent=1)
    elif a[0] == "build":
        print(build(vs[int(a[1]) - 1])["slug"])
    elif a[0] == "render":
        for i in a[1:]:
            render(vs[int(i) - 1])
