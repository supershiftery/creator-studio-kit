"""KV Pixel Box intro, MOTION VARIATION GENERATOR (Top 5 Realms first).

User 2026-10-24: keep the KV look exactly (Minecraftia pixel-box words, white + one lime keyword, KV dirt, mascot) but
stop every intro looking like the same template. So the TEXT STYLE and BACKGROUND never change; what changes per
variant is the motion graphics:
  entry    how each word box lands        slam / drop / side / rise / spin / stamp
  trans    scene to scene                 whip / zoom / drop / cut / dirtwall (a dirt wall sweeps across) / tiles (dirt blocks fill + clear)
  layout   word-only beats                stack / left / stair / scatter
  frames   how footage sits on the dirt   3 of: card (tilted window) / split (half screen) / tv (3D tilted plane) /
                                          circle (round reveal) / strips (dirt strips slide off) / full (full screen, blurred under words)
  list     the game-mode list             row / full / fan / carousel / strips
  dirt     background motion              drift / zoom / tilt / pan
  mascot   how the mascot enters          slide / pop / peek
  xp       watch-to-the-end bar           kvbar / mcxp / blocks
  title    the end slam                   stack / left / big5
Any two variants differ on at least 5 of these 9 axes. Fixed in every variant (user liked them): the full-screen
"investigating" beat, the hard-cut realm montage, the XP fill + ding, Song of Storms (dubstep remix) with its drop
on "In today's video", KV SFX rules (soft pops, whip on scene entries, nothing stacked), no flashes, no cartoon FX.

  python kvgen.py list
  python kvgen.py build N
  python kvgen.py render N [N ...]   -> renders/realms-intro-kv2-NN-<slug>.mp4 (60 fps, mixed to -17 LUFS)
"""
import json, os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
DUR = 27.2
OV = 0.3          # scene overlap for transitions
GP = "assets/gameplay/"

# ---- the VO beats (word times from the transcript) ------------------------------------------------------------------
# groups: (t_in, t_out, [(size, [(word, t, key)])])  size: s m l xl
# Calm pass 2026-10-25 ("too busy ... too many things popping up"): ONE phrase per idea, ~23 pops in 27 s (0.85/s, the
# approved Top 10 intro's rate); filler lines ("On these", "We're gonna be", "Some of these game modes") are not on screen.
BEATS = [
    dict(kind="words", t0=0.0, t1=1.3, mascot=("pose4", 0.0),
         groups=[(0.05, 1.3, [("m", [("Minecraft", 0.05, 0)]), ("xl", [("Realms", 0.64, 1)])])]),
    dict(kind="clip", t0=1.3, t1=3.04, clip="c01-anarchy",
         groups=[(1.44, 3.04, [("l", [("Still", 1.44, 0), ("Going?", 1.44, 1)])])]),
    dict(kind="clip", t0=3.04, t1=4.8, clip="c03-people",
         groups=[(3.08, 3.86, [("m", [("Apparently...", 3.08, 0)])]),
                 (3.92, 4.8, [("l", [("People", 3.92, 0), ("Are", 3.92, 0), ("Hosting", 3.92, 1)])])]),
    dict(kind="clip", t0=4.8, t1=6.0, clip="c04-crate",
         groups=[(4.88, 6.0, [("l", [("Secret", 4.88, 1), ("Game", 4.88, 0), ("Modes", 4.88, 0)])])]),
    dict(kind="list", t0=6.0, t1=9.52, groups=[],
         items=[("Sky Gen", 6.32, "c05-skygen", "card-skygen", 0), ("Kit PvP", 7.36, "c06-kitpvp", "card-kitpvp", 0),
                ("Prisons!", 8.88, "c07-prisons", "card-prisons", 1)]),
    dict(kind="clip", t0=9.52, t1=11.44, clip="c08-limited", mascot=("pose3", 10.2),
         groups=[(10.0, 11.44, [("l", [("Limited", 10.0, 1), ("Servers", 10.0, 0)])])]),
    dict(kind="clip", t0=11.44, t1=13.44, clip="c09-players", sharp=True,
         groups=[(12.64, 13.44, [("l", [("Only", 12.64, 0), ("10", 12.64, 1), ("Players!", 12.64, 0)])])]),
    dict(kind="clip", t0=13.44, t1=15.86, clip="c10-trials", mascot=("pose4", 14.2),
         groups=[(13.84, 14.58, [("l", [("Really", 13.84, 0), ("Curious", 13.84, 1)])]),
                 (14.64, 15.86, [("l", [("What's", 14.64, 0), ("Going", 14.64, 0), ("On?", 14.64, 1)])])]),
    dict(kind="triple", t0=15.86, t1=18.16, clips=[("c11-dragonforge", 15.86), ("c12-lunar-portal", 16.48), ("c13-village", 17.12)],
         groups=[(16.48, 18.16, [("m", [("Bedrock", 16.48, 0), ("Edition", 16.48, 0)]), ("xl", [("Realms", 17.52, 1)])])]),
    dict(kind="words", t0=18.16, t1=19.12, mascot=("pose2", 18.2), drop=True,
         groups=[(18.16, 19.12, [("l", [("In", 18.16, 0), ("Today's", 18.16, 0), ("Video", 18.16, 1)])])]),
    dict(kind="fullsoft", t0=19.12, t1=21.04, clip="c15-charmander",
         groups=[(19.68, 21.04, [("xl", [("Investigating", 19.68, 1)]), ("m", [("Just", 20.32, 0), ("That!", 20.32, 0)])])]),
    dict(kind="xp", t0=21.04, t1=22.64,
         groups=[(21.04, 22.64, [("m", [("Watch", 21.04, 0), ("To", 21.04, 0), ("The", 21.04, 0), ("End", 21.04, 1)])])]),
    dict(kind="montage", t0=22.64, t1=25.8,
         clips=[("m0-rennmon", 22.64, 0.64), ("m1-lunar", 23.28, 0.72), ("m2-thunder", 24.0, 0.32),
                ("m3-spectrixious", 24.32, 0.48), ("m4-anarchy", 24.8, 0.24), ("m5-dragonforge", 25.04, 0.76)],
         groups=[(22.96, 24.9, [("m", [("Trust", 22.96, 0), ("Me", 22.96, 1)])]),
                 (25.04, 25.8, [("xl", [("Shock", 25.04, 0), ("You!", 25.04, 1)])])]),
    dict(kind="title", t0=25.8, t1=DUR, mascot=("pose1", 25.82),
         groups=[(25.84, DUR, [("xl", [("Top", 25.84, 0), ("5", 25.84, 1)]), ("xl", [("Realms!", 26.1, 0)])])]),
]
HERO = {"Realms", "Secret", "Limited", "10", "Curious", "On?", "Video", "Investigating", "End", "You!", "5", "Prisons!", "Going?", "Hosting"}
BIG = {"Secret", "10", "Investigating", "You!", "5"}   # the few words that get the bigger passby swoosh; the rest get soft pops
SIZES = {"s": 84, "m": 100, "l": 130, "xl": 170}

AX = {
    "entry": ["slam", "side", "rise"],                       # spin / stamp / bounce-drop removed 2026-10-25 (too jumpy)
    "trans": ["whip", "zoom", "drop", "cut", "dirtwall"],   # dirt-block tiles removed 2026-10-25 (flickery)
    "layout": ["stack", "left", "stair", "scatter"],
    "list": ["row", "fan", "carousel", "strips"],       # "full" removed 2026-10-25: full-screen cuts only in the end montage
    "dirt": ["drift", "zoom", "tilt", "pan"],
    "mascot": ["slide", "pop", "peek"],
    "xp": ["kvbar", "mcxp", "blocks"],
    "title": ["stack", "left", "big5"],
}
FRAMES = ["card", "split", "tv", "circle", "full"]   # strips removed 2026-10-25 (busy)

def variants(n=20, seed=11):
    rng = random.Random(seed)
    out, tries = [], 0
    while len(out) < n and tries < 50000:
        tries += 1
        v = {k: rng.choice(o) for k, o in AX.items()}
        v["frames"] = tuple(sorted(rng.sample(FRAMES, 3)))
        keys = list(AX) + ["frames"]
        if any(sum(v[k] == o[k] for k in keys) > 4 for o in out):
            continue
        out.append(v)
    for i, v in enumerate(out, 1):
        v["id"] = i
        v["slug"] = f"{v['entry']}-{v['trans']}-{v['layout']}-{v['list']}-{'+'.join(v['frames'])}"
    return out

# ---- layout helpers -----------------------------------------------------------------------------------------------
def wwidth(w, fs):
    return len(w) * 0.62 * fs + 70

def place(lines, cx, cy, maxw, mode, rng):
    """-> [(word, t, key, x, y, fs, rot)] centre positions for every word box"""
    # fit: shrink every size by the same factor if the widest line is too wide
    k = 1.0
    for size, ws in lines:
        fs = SIZES[size]
        w = sum(wwidth(x[0], fs) for x in ws) + 14 * (len(ws) - 1)
        k = min(k, maxw / w)
    rows = []
    for size, ws in lines:
        fs = round(SIZES[size] * k)
        rows.append((fs, ws, sum(wwidth(x[0], fs) for x in ws) + 14 * (len(ws) - 1)))
    heights = [fs * 1.62 for fs, _, _ in rows]
    y = cy - sum(heights) / 2
    out = []
    n = len(rows)
    for i, (fs, ws, lw) in enumerate(rows):
        yc = y + heights[i] / 2
        y += heights[i]
        if mode == "left":
            x0 = cx - maxw / 2 + 20
        elif mode == "stair":
            step = min(140, (maxw - lw) / max(1, n - 1)) if n > 1 else 0
            x0 = cx - lw / 2 + (i - (n - 1) / 2) * step
        else:
            x0 = cx - lw / 2
        if mode == "scatter":
            x0 += rng.uniform(-70, 70)
        rot = {"stack": [-2, 2, -1][i % 3], "left": -1.5, "stair": -3, "scatter": rng.choice([-5, -3, 3, 5])}[mode]
        for w, t, key in ws:
            ww = wwidth(w, fs)
            out.append((w, t, key, x0 + ww / 2, round(yc), fs, rot, ww))
            x0 += ww + 14
    # keep the whole group inside its area (and the frame): shrink the stair step / scatter if needed, then shift
    lo = min(x - ww / 2 for (_, _, _, x, _, _, _, ww) in out)
    hi = max(x + ww / 2 for (_, _, _, x, _, _, _, ww) in out)
    L, R = max(40, cx - maxw / 2), min(1880, cx + maxw / 2)
    if hi - lo > R - L:   # too wide after the stair offsets: pull every line toward the centre
        f = (R - L) / (hi - lo)
        mid = (lo + hi) / 2
        out = [(w, t, k_, mid + (x - mid) * f, y, round(fs * f), r, ww * f) for (w, t, k_, x, y, fs, r, ww) in out]
        lo, hi = mid + (lo - mid) * f, mid + (hi - mid) * f
    dx = (L - lo) if lo < L else (R - hi) if hi > R else 0
    return [(w, t, k_, round(x + dx), y, fs, r) for (w, t, k_, x, y, fs, r, ww) in out]

def wrap(lines, maxw):
    """a phrase too wide for its area goes onto two lines (keeps the text big beside the footage, same pop time)"""
    out = []
    for size, ws in lines:
        fs = SIZES[size]
        width = sum(wwidth(x[0], fs) for x in ws) + 14 * (len(ws) - 1)
        if len(ws) > 1 and width > maxw * 1.15:
            best = min(range(1, len(ws)), key=lambda c: max(sum(wwidth(x[0], fs) for x in ws[:c]), sum(wwidth(x[0], fs) for x in ws[c:])))
            out += [(size, ws[:best]), (size, ws[best:])]
        else:
            out.append((size, ws))
    return out

# ---- builder ------------------------------------------------------------------------------------------------------
class Build:
    def __init__(self, v):
        self.v, self.rng = v, random.Random(v["id"] * 97)
        self.html, self.js, self.sfx = [], [], []
        self.n = 0

    def uid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def words(self, groups, cx, cy, maxw, mode, last_t1):
        for (tin, tout, lines) in groups:
            lines = wrap(lines, maxw)
            ws = place(lines, cx, cy, maxw, mode, self.rng)
            ids = []
            # one pop per LINE, not per word (user 2026-10-25: "too many things popping up"; the approved Top 10 intro
            # slams ~0.8 phrases per second, the busy variants popped 2.2 single words per second)
            lines_ = {}
            for item in ws:
                lines_.setdefault(item[4], []).append(item)
            for y_, items in lines_.items():
                tl_ = min(it[1] for it in items)
                big = any(it[0] in BIG for it in items)
                hero = any(it[0] in HERO for it in items)
                for (w, t, key, x, y, fs, rot) in items:
                    i = self.uid("w")
                    ids.append(i)
                    self.html.append(f'<div class="kv" id="{i}" style="left:{x}px;top:{y}px;font-size:{fs}px"><span{" class=g" if key else ""}>{w}</span></div>')
                    self.js.append(f'enter("#{i}",{tl_},{rot},{1 if big else 0});')
                pop = "k_pop1.wav" if self.n % 2 else "k_pop2.wav"
                self.sfx.append((tl_, "k_passby.wav" if big else pop, 0.09 if big else 0.07, 1.2 if big else 0.45, 5 if big else 4 if hero else 1))
                if big:
                    self.js.append(f"shake({tl_ + 0.04},8,4);")
            if tout < last_t1 - 0.05:
                self.js.append(f'tl.to([{",".join(repr("#" + i) for i in ids)}],{{opacity:0,duration:0.08}},{round(tout - 0.08, 2)});')

    def mascot(self, pose, t, side, h=760):
        v = self.v
        i = self.uid("m")
        x = 1300 if side == "right" else 80
        if v["mascot"] == "peek":
            y, rot = 470, (-14 if side == "right" else 14)
            x = 1480 if side == "right" else -60
            self.html.append(f'<img class="masc" id="{i}" src="assets/kit/{pose}.png" style="left:{x}px;top:{y}px;height:{h + 120}px" />')
            self.js.append(f'tl.fromTo("#{i}",{{y:700,rotation:0,opacity:1}},{{y:0,rotation:{rot},opacity:1,duration:.34,ease:"back.out(1.5)"}},{t});')
        elif v["mascot"] == "pop":
            self.html.append(f'<img class="masc" id="{i}" src="assets/kit/{pose}.png" style="left:{x}px;top:{1080 - h - 20}px;height:{h}px" />')
            self.js.append(f'tl.fromTo("#{i}",{{scale:.2,y:300,opacity:0,transformOrigin:"50% 100%"}},{{scale:1,y:0,opacity:1,duration:.32,ease:"back.out(1.8)"}},{t});')
        else:
            dx = 600 if side == "right" else -600
            self.html.append(f'<img class="masc" id="{i}" src="assets/kit/{pose}.png" style="left:{x}px;top:{1080 - h - 20}px;height:{h}px" />')
            self.js.append(f'tl.fromTo("#{i}",{{x:{dx},rotation:{8 if dx > 0 else -8},opacity:0}},{{x:0,rotation:0,opacity:1,duration:.3,ease:"back.out(1.6)"}},{t});')

    def dirt(self, t0, d):
        i = self.uid("d")
        self.html.append(f'<div class="dirt" id="{i}"></div><div class="vig"></div>')
        m = self.v["dirt"]
        a, b = {"drift": ("{x:0,y:0}", "{x:-30,y:-20}"), "zoom": ("{scale:1}", "{scale:1.08}"),
                "tilt": ("{rotation:-4,scale:1.12}", "{rotation:-1.5,scale:1.12}"), "pan": ("{y:0}", "{y:-36}")}[m]
        self.js.append(f'tl.fromTo("#{i}",{a},Object.assign({b},{{duration:{d},ease:"none"}}),{t0});')

    def video(self, clip, t0, d, cls="clip", style="", track=3, mstart=0):
        i = self.uid("v")
        self.html.append(f'<video id="{i}" class="{cls}" src="{GP}{clip}.mp4" muted playsinline data-start="{t0}" data-duration="{d}" '
                         f'data-media-start="{mstart}" data-track-index="{track}" style="{style}"></video>')
        return i

    # ---- footage presentations ----
    def frame(self, kind, b, d, side):
        t0 = b["t0"]
        if kind == "full":
            vid = self.video(b["clip"], t0, d, "clip full" + ("" if b.get("sharp") else " soft"))
            self.js.append(f'tl.fromTo("#{vid}",{{scale:1.06}},{{scale:1.16,duration:{d},ease:"none"}},{t0});')
            return (960, 540, 1700)
        self.dirt(t0, d)
        if kind in ("card", "tv"):
            left = 760 if side == "right" else 60
            wrap = self.uid("f")
            style = f"left:{left}px;top:230px;width:1100px;height:619px"
            if kind == "tv":
                style += ";transform:perspective(1400px) rotateY(%ddeg)" % (-22 if side == "right" else 22)
            self.html.append(f'<div class="win" id="{wrap}" style="{style};opacity:0">')
            vid = self.video(b["clip"], t0, d)
            self.html.append("</div>")
            if kind == "card":
                r = -3 if side == "right" else 3
                self.js.append(f'tl.fromTo("#{wrap}",{{x:{900 if side == "right" else -900},rotation:{r * 4},opacity:1}},{{x:0,rotation:{r},opacity:1,duration:.32,ease:"power3.out"}},{t0 + 0.04});')
            else:
                self.js.append(f'tl.fromTo("#{wrap}",{{scale:.3,opacity:0}},{{scale:1,opacity:1,duration:.34,ease:"back.out(1.6)"}},{t0 + 0.04});')
            self.zoom_in(vid, b, d)
            return ((480, 560, 820) if side == "right" else (1440, 560, 820))
        if kind == "split":
            wrap = self.uid("f")
            left = 960 if side == "right" else 0
            self.html.append(f'<div id="{wrap}" style="position:absolute;left:{left}px;top:0;width:960px;height:1080px;overflow:hidden;border-{"left" if side == "right" else "right"}:12px solid #f8f8f8">')
            vid = self.video(b["clip"], t0, d, "clip full")
            self.html.append("</div>")
            self.js.append(f'tl.fromTo("#{wrap}",{{xPercent:{100 if side == "right" else -100}}},{{xPercent:0,duration:.3,ease:"power3.out"}},{t0 + 0.04});')
            self.zoom_in(vid, b, d)
            return ((480, 540, 820) if side == "right" else (1440, 540, 820))
        if kind == "circle":
            cx = 1300 if side == "right" else 620
            wrap = self.uid("f")
            self.html.append(f'<div id="{wrap}" style="position:absolute;inset:0;clip-path:circle(0px at {cx}px 540px)">')
            vid = self.video(b["clip"], t0, d, "clip full")
            self.html.append("</div>")
            ring = self.uid("r")
            self.html.append(f'<div id="{ring}" style="position:absolute;left:{cx}px;top:540px;width:0;height:0;border:12px solid #f8f8f8;border-radius:50%;transform:translate(-50%,-50%);box-shadow:10px 14px 0 rgba(20,20,24,.7)"></div>')
            self.js.append(f'tl.to("#{wrap}",{{clipPath:"circle(470px at {cx}px 540px)",duration:.34,ease:"back.out(1.4)"}},{t0 + 0.04});')
            self.js.append(f'tl.to("#{ring}",{{width:964,height:964,duration:.34,ease:"back.out(1.4)"}},{t0 + 0.04});')
            self.zoom_in(vid, b, d)
            return ((420, 560, 760) if side == "right" else (1500, 560, 760))
        # strips: the footage fills the screen, four dirt strips slide off it
        vid = self.video(b["clip"], t0, d, "clip full" + ("" if b.get("sharp") else " soft"))
        for k in range(4):
            s = self.uid("st")
            self.html.append(f'<div id="{s}" style="position:absolute;left:{k * 480}px;top:0;width:480px;height:1080px;overflow:hidden">'
                             f'<div class="dirt" style="left:{-k * 480 - 40}px"></div></div>')
            self.js.append(f'tl.to("#{s}",{{yPercent:{-100 if k % 2 else 100},duration:.3,ease:"power3.in"}},{t0 + 0.05 + k * 0.05});')
        self.zoom_in(vid, b, d)
        return (960, 540, 1700)

    def zoom_in(self, vid, b, d):
        if b.get("clip") == "c09-players":   # push in on "Players in TC (10)"
            self.js.append(f'tl.fromTo("#{vid}",{{scale:1}},{{scale:1.8,transformOrigin:"80% 28%",duration:{d},ease:"power1.inOut"}},{b["t0"]});')
        else:
            self.js.append(f'tl.fromTo("#{vid}",{{scale:1}},{{scale:1.1,duration:{d},ease:"none"}},{b["t0"]});')

    # ---- scenes ----
    def scene(self, idx, b, plan):
        v = self.v
        t0, t1 = b["t0"], b["t1"]
        last = idx == len(BEATS) - 1
        d = round(t1 - t0 + (0 if last else OV), 2)
        sid = f"s{idx}"
        # scenes hold <video>s, so they can't be timed elements: the timeline shows and hides them
        self.html.append(f'<div id="{sid}" class="layer" style="opacity:0">')
        self.js.append(f'tl.set("#{sid}",{{opacity:1}},{t0});')
        if not last:
            self.js.append(f'tl.set("#{sid}",{{opacity:0}},{round(t0 + d, 2)});')
        k = b["kind"]
        side = plan["side"][idx]
        mode = v["layout"]
        if k in ("words", "xp", "title"):
            self.dirt(t0, d)
            region = (760, 540, 1100) if b.get("mascot") else (960, 540, 1720)
            if k == "xp":
                region = (960, 420, 1600)
            if k == "title":
                region = {"stack": (740, 540, 1100), "left": (1180, 540, 1100), "big5": (960, 540, 1700)}[v["title"]]
                mode = "stack"
            if b.get("mascot"):
                ms = "left" if (k == "title" and v["title"] == "left") else "right"
                self.mascot(b["mascot"][0], b["mascot"][1], ms)
            if k == "title" and v["title"] == "big5":
                self.title_big5(b)
            else:
                self.words(b["groups"], *region, mode, t1)
            if k == "xp":
                self.xp()
        elif k in ("clip", "fullsoft"):
            fr = "full" if k == "fullsoft" else plan["frame"][idx]
            cx, cy, mw = self.frame(fr, b, d, side)
            if b.get("mascot") and fr in ("full", "strips"):
                self.mascot(b["mascot"][0], b["mascot"][1], "right")
                cx, mw = 760, 1100
            self.words(b["groups"], cx, cy, mw, "stack" if fr in ("full", "strips") else mode, t1)
        elif k == "triple":
            # 2026-10-25: was full-screen quick cuts + a dip to black. User: no black screen mid-intro, and full-screen
            # realm cuts must not appear twice (the end montage owns that look). Now: one framed window on the dirt
            # that flips between the realms on each word, text beside it, straight into the drop.
            self.dirt(t0, d)
            side = "right"
            wrap_ = self.uid("f")
            self.html.append(f'<div class="win" id="{wrap_}" style="left:820px;top:250px;width:1000px;height:563px;opacity:0">')
            vids = []
            for j, (clip, s_) in enumerate(b["clips"]):
                e = b["clips"][j + 1][1] if j < 2 else t1 + OV
                vids.append((self.video(clip, s_, round(e - s_, 2), track=3 + j % 2), s_, round(e - s_, 2)))
            self.html.append("</div>")
            self.js.append(f'tl.fromTo("#{wrap_}",{{x:900,rotation:-10,opacity:1}},{{x:0,rotation:-2,opacity:1,duration:.32,ease:"power3.out"}},{t0 + 0.02});')
            for j, (vid, s_, dd) in enumerate(vids):
                self.js.append(f'tl.fromTo("#{vid}",{{scale:1.12}},{{scale:1.0,duration:{dd},ease:"power1.out"}},{s_});')
                if j:   # each new realm: the window turns slightly, like flipping a card
                    self.js.append(f'tl.fromTo("#{wrap_}",{{rotationY:{-25 if j % 2 else 25}}},{{rotationY:0,duration:.28,ease:"power2.out"}},{s_});')
            self.words(b["groups"], 430, 540, 760, "stack", t1)
        elif k == "list":
            self.list_scene(b, d)
        elif k == "montage":
            for j, (clip, s, dd) in enumerate(b["clips"]):
                vid = self.video(clip, s, dd, "clip full", track=3 + j % 2)
                self.js.append(f'tl.fromTo("#{vid}",{{scale:1.16}},{{scale:1.0,duration:{dd},ease:"power1.out"}},{s});')
            self.js.append('tl.to("#cam",{filter:"none"},22.64);')
            pos = [(960, 190, 1500), (960, 540, 1700)]
            for g, (cx, cy, mw) in zip(b["groups"], pos):
                self.words([g], cx, cy, mw, "stack", 25.8 if g[1] >= 25.8 else 99)
        self.html.append("</div>")
        # entry transition
        if idx and not b.get("drop") and BEATS[idx - 1]["kind"] != "triple":
            self.transition(sid, f"s{idx - 1}", t0)
        elif b.get("drop"):
            self.js.append(f"punch({t0},1.08,.45);")

    def transition(self, sid, prev, t):
        tr = self.v["trans"]
        if tr == "whip":
            self.js.append(f'tl.fromTo("#{sid}",{{x:1920}},{{x:0,duration:.28,ease:"power3.out"}},{t});')
            self.js.append(f'tl.to("#{prev}",{{x:-700,duration:.28,ease:"power3.in"}},{t});')
        elif tr == "zoom":
            self.js.append(f'tl.fromTo("#{sid}",{{scale:1.5,opacity:0}},{{scale:1,opacity:1,duration:.26,ease:"power2.out"}},{t});')
        elif tr == "drop":
            self.js.append(f'tl.fromTo("#{sid}",{{y:-1080}},{{y:0,duration:.3,ease:"power3.out"}},{t});')
            self.js.append(f'tl.to("#{prev}",{{y:400,duration:.3,ease:"power3.in"}},{t});')
        elif tr == "cut":
            self.js.append(f"punch({t},1.06,.4);")
        elif tr == "dirtwall":
            self.js.append(f'tl.set("#{sid}",{{opacity:0}},{t - 0.001});tl.set("#{sid}",{{opacity:1}},{t + 0.15});')
            self.js.append(f'tl.fromTo("#wall",{{x:2000}},{{x:0,duration:.15,ease:"power2.in"}},{t});')
            self.js.append(f'tl.to("#wall",{{x:-2000,duration:.18,ease:"power2.out"}},{t + 0.15});')
        elif tr == "tiles":
            self.js.append(f'tl.set("#{sid}",{{opacity:0}},{t - 0.001});tl.set("#{sid}",{{opacity:1}},{t + 0.16});')
            self.js.append(f'tl.fromTo(".tile",{{scale:0}},{{scale:1.02,duration:.08,ease:"none",stagger:{{grid:[5,8],from:"start",amount:.08}}}},{t});')
            self.js.append(f'tl.to(".tile",{{scale:0,duration:.08,ease:"none",stagger:{{grid:[5,8],from:"end",amount:.08}}}},{t + 0.17});')
        if tr != "cut":
            self.sfx.append((t, "k_whip.wav", 0.11, 0.9, 3))

    def list_scene(self, b, d):
        v = self.v
        t0 = b["t0"]
        L = v["list"]
        if L == "full":
            for j, (label, t, clip, card, key) in enumerate(b["items"]):
                e = b["items"][j + 1][1] if j < 2 else b["t1"] + OV
                vid = self.video(clip, round(t - 0.06, 2), round(e - t + 0.06, 2), "clip full", track=3 + j % 2)
                self.js.append(f'tl.fromTo("#{vid}",{{scale:1.2,opacity:1}},{{scale:1.04,duration:{round(e - t, 2)},ease:"power1.out"}},{round(t - 0.06, 2)});')
            self.html.append('<div style="position:absolute;inset:0;background:linear-gradient(0deg,rgba(0,0,0,.35),transparent 40%)"></div>')
            self.words(b["groups"], 960, 150, 1500, "stack", 99)
            for j, (label, t, clip, card, key) in enumerate(b["items"]):
                e = b["items"][j + 1][1] if j < 2 else 99
                self.words([(t, e, [("xl", [(label, t, key)])])], 960, 820, 1500, "stack", 99)
            return
        self.dirt(t0, d)
        self.words(b["groups"], 960, 140, 1500, "stack", 99)
        n = len(b["items"])
        for j, (label, t, clip, card, key) in enumerate(b["items"]):
            w, h = 480, 566
            if L == "row":
                x, y, r, lx, ly = 180 + j * 540, 270, [-4, 3, -3][j], 420 + j * 540, 950
            elif L == "fan":
                x, y, r, lx, ly = 720 + (j - 1) * 430, 300, (j - 1) * 12, 960 + (j - 1) * 500, 960
            elif L == "carousel":
                x, y, r, lx, ly = 720, 250, 0, 960, 940
            else:   # strips: three tall columns side by side
                w, h = 600, 760
                x, y, r, lx, ly = 30 + j * 630, 230, 0, 330 + j * 630, 1010
            c = self.uid("card")
            self.html.append(f'<div class="win" id="{c}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;opacity:0">')
            self.video(card, round(t - 0.1, 2), round(b["t1"] + OV - t + 0.1, 2), track=3 + j % 3)
            self.html.append("</div>")
            if L == "row":
                self.js.append(f'tl.fromTo("#{c}",{{opacity:0,scale:1.7,rotation:{r * 4},y:-40}},{{opacity:1,scale:1,rotation:{r},y:0,duration:.2,ease:"back.out(2)"}},{t - 0.08});')
            elif L == "fan":
                self.js.append(f'tl.fromTo("#{c}",{{opacity:1,y:900,rotation:0,transformOrigin:"50% 140%"}},{{y:0,rotation:{r},opacity:1,duration:.3,ease:"back.out(1.5)"}},{t - 0.1});')
            elif L == "carousel":
                self.js.append(f'tl.fromTo("#{c}",{{opacity:1,x:1300,rotation:8}},{{x:0,rotation:0,opacity:1,duration:.3,ease:"power3.out"}},{t - 0.1});')
                if j < n - 1:
                    nxt = b["items"][j + 1][1]
                    self.js.append(f'tl.to("#{c}",{{x:-560,scale:.7,rotation:-6,duration:.3,ease:"power3.inOut"}},{nxt - 0.1});')
                    if j:
                        self.js.append(f'tl.to("#{c}",{{opacity:0,duration:.1}},{nxt - 0.05});')
            else:
                self.js.append(f'tl.fromTo("#{c}",{{opacity:1,yPercent:{120 if j % 2 else -120}}},{{yPercent:0,opacity:1,duration:.3,ease:"power3.out"}},{t - 0.1});')
            if L == "carousel":
                e = b["items"][j + 1][1] - 0.05 if j < n - 1 else 99
                self.words([(t, e, [("l", [(label, t, key)])])], lx, ly, 1200, "stack", 99)
            else:
                self.words([(t, 99, [("s", [(label, t, key)])])], lx, ly, 560, "stack", 99)
            self.js.append(f"punch({t},1.03,.3);")
            self.sfx.append((t - 0.08, "k_shutter.wav", 0.5, 0.35, 2))

    def xp(self):
        v = self.v
        if v["xp"] == "kvbar":
            self.html.append('<div id="xp" style="position:absolute;left:370px;top:700px;width:1180px;height:64px;opacity:0">'
                             '<div style="position:absolute;inset:0;background:#2a2530;filter:url(#kvbox)"></div>'
                             '<div id="xpf" style="position:absolute;inset:0;background:#88a800;transform-origin:0 50%;transform:scaleX(0)"></div>'
                             '<div style="position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 62px,rgba(20,20,24,.55) 62px 66px)"></div></div>')
        elif v["xp"] == "mcxp":
            self.html.append('<div id="xp" style="position:absolute;left:410px;top:720px;width:1100px;height:40px;opacity:0;background:#1d1f1a;border:6px solid #0b0b0b">'
                             '<div id="xpf" style="position:absolute;inset:0;background:#7ed321;transform-origin:0 50%;transform:scaleX(0)"></div>'
                             '<div style="position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 56px,rgba(0,0,0,.6) 56px 61px)"></div></div>'
                             '<div class="kv m" id="xplv" style="left:960px;top:640px"><span class="g">5</span></div>')
            self.js.append('tl.fromTo("#xplv",{scale:2,opacity:0},{scale:1,opacity:1,duration:.2,ease:"back.out(2.2)"},22.32);')
        else:   # blocks: ten dirt blocks turn to grass one by one
            cells = "".join(f'<div class="blk" style="left:{k * 118}px"><div class="grs" id="gb{k}"></div></div>' for k in range(10))
            self.html.append(f'<div id="xp" style="position:absolute;left:370px;top:690px;width:1180px;height:110px;opacity:0">{cells}</div><div id="xpf"></div>')
            self.js.append('for(let k=0;k<10;k++) tl.fromTo("#gb"+k,{scaleY:0},{scaleY:1,duration:.1,ease:"back.out(2)"},21.12+k*0.12);')
        self.js.append('tl.fromTo("#xp",{opacity:0,scale:1.4},{opacity:1,scale:1,duration:.16,ease:"back.out(2)"},21.06);')
        self.js.append('tl.fromTo("#xpf",{scaleX:0},{scaleX:1,duration:1.2,ease:"none"},21.12);')
        self.js.append('tl.fromTo("#xp",{scale:1.1},{scale:1,duration:.3,ease:"back.out(2)"},22.32);shake(22.34,8,4);')

    def title_big5(self, b):
        self.html.append('<div class="kv" id="t5" style="left:960px;top:560px;font-size:330px"><span class="g">5</span></div>'
                         '<div class="kv" id="ttop" style="left:960px;top:230px;font-size:150px"><span>Top</span></div>'
                         '<div class="kv" id="trl" style="left:960px;top:880px;font-size:150px"><span>Realms!</span></div>')
        self.js.append('enter("#ttop",25.84,-3,0);enter("#t5",25.96,2,1);enter("#trl",26.1,-2,0);shake(26.0,14,6);')
        self.sfx += [(25.84, "k_pop1.wav", 0.07, 0.45, 1), (25.96, "k_passby.wav", 0.09, 1.2, 5)]

    def run(self):
        v = self.v
        clip_idx = [i for i, b in enumerate(BEATS) if b["kind"] in ("clip",)]
        frames = list(v["frames"])
        self.rng.shuffle(frames)
        plan = {"frame": {}, "side": {}}
        for j, i in enumerate(clip_idx):
            f = frames[j % len(frames)]
            if f == "full" and BEATS[i].get("sharp"):
                f = frames[(j + 1) % len(frames)]
            plan["frame"][i] = f
            plan["side"][i] = "right" if j % 2 == 0 else "left"
        for i in range(len(BEATS)):
            plan["side"].setdefault(i, "right")
            plan["frame"].setdefault(i, "full")
        for i, b in enumerate(BEATS):
            self.scene(i, b, plan)
        return plan

ENTRY = {
    "slam": 'tl.fromTo(s,{scale:h?2.4:1.9,rotation:r*3+(r>=0?6:-6),opacity:0},{scale:1,rotation:r,opacity:1,duration:.2,ease:"back.out(2.2)"},t);',
    "drop": 'tl.fromTo(s,{y:-260,rotation:r*4,opacity:0},{y:0,rotation:r,opacity:1,duration:.3,ease:"bounce.out"},t);',
    "side": 'k++;tl.fromTo(s,{x:(k%2?-1:1)*700,rotation:(k%2?-1:1)*18,opacity:0},{x:0,rotation:r,opacity:1,duration:.24,ease:"back.out(1.8)"},t);',
    "rise": 'tl.fromTo(s,{y:240,scaleY:1.5,opacity:0},{y:0,scaleY:1,rotation:r,opacity:1,duration:.26,ease:"back.out(2)"},t);',
    "spin": 'tl.fromTo(s,{rotation:r-200,scale:.2,opacity:0},{rotation:r,scale:1,opacity:1,duration:.28,ease:"back.out(1.6)"},t);',
    "stamp": 'tl.fromTo(s,{scale:h?3.4:2.8,rotation:r,opacity:0},{scale:1,rotation:r,opacity:1,duration:.12,ease:"power4.in"},t);tl.fromTo(s,{y:0},{y:h?-10:-5,duration:.05,yoyo:true,repeat:1},t+.12);',
}

# ---- sound design follows the MUSIC'S TEMPO (user 2026-10-24: "too many sound effects back to back ... the music is
# slower so you have to be careful"). Measured on the approved Top 10 Servers KV intro (v7, "sound design matches
# perfectly"): 35 SFX in 31.6 s over an 89 BPM track = 0.75 SFX per beat, median gap 0.88 s. The first realms
# variants had 1.8 SFX/s, median gap 0.48 s, over a 70 BPM track. So: measure the beat, keep at most ~0.75 SFX per beat,
# never two closer than one beat (min 0.6 s), and spend the budget on the important hits first.
SFX_PER_BEAT = 0.75
MAX_PER_S = 0.95       # the approved intro sat at 1.1/s with a busier mix; never go above that

def music_beat(path):
    """beat period in seconds from onset autocorrelation (0.3-1.2 s = 50-200 BPM)"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "30", "-i", path, "-ac", "1", "-ar", "11025", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(float)
    h = 256
    e = np.array([np.sum(a[i:i + h] ** 2) for i in range(0, len(a) - h, h)])
    o = np.maximum(0, np.diff(np.log(e + 1)))
    o -= o.mean()
    ac = np.correlate(o, o, "full")[len(o) - 1:]
    lags = np.arange(len(ac)) * h / 11025
    m = (lags > 0.3) & (lags < 1.2)
    return float(lags[m][np.argmax(ac[m])])

def plan_sfx(cands, beat, dur=DUR):
    """cands (t, file, vol, len) -> the kept SFX. cands (t, file, vol, len, priority): big word 5 > key word 4 > scene whip 3 > list card 2 > plain word 1."""
    import math
    gap = beat * max(1, round(0.85 / beat))                  # whole beats, about 0.8-0.9 s
    budget = int(min(SFX_PER_BEAT / beat, MAX_PER_S) * dur)  # slow music: per beat; fast music: capped per second
    keep = [(21.12, "", 0, 0, 9), (22.32, "", 0, 0, 9)]   # placeholders: the XP fill + ding own their spots
    for c in sorted(cands, key=lambda c: (-c[4], c[0])):
        if len(keep) >= budget:
            break
        if 21.1 < c[0] < 22.5:               # the XP bar has its own sound
            continue
        g = gap * (1.25 if c[0] < 18.16 else 1.0)          # the quiet half before the drop breathes more
        if all(abs(c[0] - k[0]) >= g for k in keep):
            keep.append(c)
    return sorted(k[:4] for k in keep if k[1])

CSS = """
      @font-face { font-family: "MCF"; src: url("assets/kit/Minecraftia-Regular.ttf") format("truetype"); }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #000; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; background: #2f221d; }
      .layer { position: absolute; inset: 0; overflow: hidden; }
      .full { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
      .dirt { position: absolute; left: -40px; top: -40px; width: 2000px; height: 1160px; background: url("assets/kit/dirt2.png"); background-size: 1920px 1152px; image-rendering: pixelated; }
      .vig { position: absolute; inset: 0; background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.5) 100%); }
      .kv { position: absolute; display: flex; font-family: "MCF"; line-height: 1; white-space: nowrap; opacity: 0; }
      .kv span { display: inline-block; color: #f8f8f8; filter: url(#kvbox); padding: 0 22px; }
      .kv span.g { color: #88a800; }
      .masc { position: absolute; opacity: 0; }
      .win { position: absolute; overflow: hidden; border: 10px solid #f8f8f8; box-shadow: 12px 18px 0 rgba(20,20,24,.75); }
      .win video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
      .soft { filter: blur(12px) brightness(1.02) saturate(1.05); transform: scale(1.06); }
      #wall { position: absolute; left: -40px; top: -40px; width: 2000px; height: 1160px; background: url("assets/kit/dirt2.png"); background-size: 1920px 1152px; image-rendering: pixelated; box-shadow: -30px 0 0 #1b1410, 30px 0 0 #1b1410; }
      .tile { position: absolute; width: 240px; height: 216px; background: url("assets/kit/dirt2.png"); background-size: 1920px 1152px; image-rendering: pixelated; }
      .blk { position: absolute; top: 0; width: 108px; height: 108px; background: url("assets/kit/dirt2.png"); background-size: 960px 576px; image-rendering: pixelated; border: 6px solid #1b1410; }
      .grs { position: absolute; left: 0; right: 0; bottom: 0; height: 100%; background: #6aa53a; transform-origin: 50% 0; transform: scaleY(0); box-shadow: inset 0 -18px 0 rgba(0,0,0,.18); }
"""
FILTER = """<svg width="0" height="0" style="position:absolute">
      <filter id="kvbox" x="-30%" y="-60%" width="160%" height="230%" color-interpolation-filters="sRGB">
        <feMorphology in="SourceAlpha" operator="dilate" radius="42" result="big" />
        <feMorphology in="big" operator="erode" radius="29" result="d1" />
        <feMorphology in="big" operator="erode" radius="23" result="d2" />
        <feMorphology in="big" operator="erode" radius="16" result="d3" />
        <feOffset in="d3" dx="3" dy="16" result="sh" />
        <feFlood flood-color="#232327" /><feComposite in2="sh" operator="in" result="shc" />
        <feFlood flood-color="#f8b000" /><feComposite in2="d3" operator="in" result="o" />
        <feFlood flood-color="#f81010" /><feComposite in2="d2" operator="in" result="r" />
        <feFlood flood-color="#2a2530" /><feComposite in2="d1" operator="in" result="f" />
        <feMerge><feMergeNode in="shc" /><feMergeNode in="o" /><feMergeNode in="r" /><feMergeNode in="f" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
    </svg>"""
# Rainbow Road type beat (user 2026-10-24: Song of Storms didn't fit either), intro extended 3 bars so its drop lands on
# "In today's video" (18.16). Gains matched in LUFS to the approved Top 10 Servers bed: ~-33.6 under the VO, title ~-22.
MUSIC = ('{"version":1,"lanes":[{"target":"volume","points":[{"t":0,"v":0},{"t":0.4,"v":0.155},{"t":17.84,"v":0.155},{"t":17.9,"v":0},'
         '{"t":18.1,"v":0},{"t":18.16,"v":0.133},{"t":18.9,"v":0.12},{"t":19.4,"v":0.047},{"t":25.7,"v":0.047},{"t":25.84,"v":0.19},'
         '{"t":26.9,"v":0.18},{"t":27.2,"v":0}]}]}')

def build(v):
    bd = Build(v)
    plan = bd.run()
    keep = plan_sfx(bd.sfx, music_beat(os.path.join(HERE, "assets", "music.mp3")))
    keep = [s for s in keep if not (21.1 < s[0] < 22.5)]
    keep += [(21.12, "watch-to-the-end-xp-fill.wav", 0.26, 1.2), (22.32, "watch-to-the-end-xp-full.wav", 0.28, 0.58)]
    auds = [f'<audio id="sx{i}" src="assets/kit/sfx/{f}" data-start="{round(t, 2)}" data-duration="{d}" data-track-index="{30 + i % 12}" data-volume="{vol}"></audio>'
            for i, (t, f, vol, d) in enumerate(sorted(keep))]
    fx = ""
    if v["trans"] == "dirtwall":
        fx = '<div id="wall"></div>'
    elif v["trans"] == "tiles":
        fx = "".join(f'<div class="tile" style="left:{c * 240}px;top:{r * 216}px;background-position:{-c * 240}px {-r * 216}px"></div>'
                     for r in range(5) for c in range(8))
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <!-- GENERATED by kvgen.py: variant {v['id']} = {json.dumps({k: v[k] for k in list(AX) + ['frames']})}; edit kvgen.py, not this file -->
    <style>{CSS}    </style>
  </head>
  <body>
    {FILTER}
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1920" data-height="1080">
      <div id="cam" class="layer">
{chr(10).join(bd.html)}
      </div>
      <div id="fx" class="layer" style="pointer-events:none">{fx}</div>
      <audio id="vo" src="assets/vo-norm.wav" data-start="0" data-duration="25.93" data-track-index="10" data-volume="1"></audio>
      <audio id="music" src="assets/music.mp3" data-start="0" data-duration="{DUR}" data-track-index="11" data-volume="1" data-automation='{MUSIC}'></audio>
{chr(10).join(auds)}
    <script>
      const tl = gsap.timeline({{ paused: true }});
      gsap.set(".kv", {{ xPercent: -50, yPercent: -50 }});
      if (document.getElementById("wall")) gsap.set("#wall", {{ x: 2000 }});
      gsap.set(".tile", {{ scale: 0 }});
      let k = 0;
      const enter = (s, t, r, h) => {{ {ENTRY[v['entry']]} }};
      const punch = (t, s = 1.05, dur = 0.5) => tl.fromTo("#cam", {{ scale: s }}, {{ scale: 1, duration: dur, ease: "power3.out" }}, t);
      const shake = (t, amp = 10, n = 5) => {{
        for (let i = 0; i < n; i++) tl.to("#cam", {{ x: (i % 2 ? -1 : 1) * amp * (1 - i / n), y: ((i % 3) - 1) * amp * 0.6 * (1 - i / n), duration: 0.035, ease: "none" }}, t + i * 0.035);
        tl.to("#cam", {{ x: 0, y: 0, duration: 0.05 }}, t + n * 0.035);
      }};
{chr(10).join('      ' + x for x in bd.js)}
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = tl;
    </script>
    </div>
  </body>
</html>
"""
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return plan

def render(v):
    build(v)
    out = os.path.join(HERE, "renders", f"realms-intro-calm-{v['id']:02d}-{v['slug']}")
    t = time.time()
    r = subprocess.run("npx --yes hyperframes@0.8.180 render --fps 60 --output \"" + out + "-raw.mp4\"",
                       cwd=HERE, capture_output=True, shell=True)
    if r.returncode:
        print(r.stdout[-2000:].decode("utf-8", "replace"), r.stderr[-2000:].decode("utf-8", "replace"))
        return None
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
            print(f"{v['id']:2d} entry {v['entry']:6s} trans {v['trans']:8s} layout {v['layout']:7s} list {v['list']:8s} "
                  f"frames {'+'.join(v['frames']):20s} dirt {v['dirt']:5s} mascot {v['mascot']:5s} xp {v['xp']:6s} title {v['title']}")
        with open(os.path.join(HERE, "variants.json"), "w") as f:
            json.dump(vs, f, indent=1)
    elif a[0] == "build":
        print(build(vs[int(a[1]) - 1]))
    elif a[0] == "rendercfg":      # python kvgen.py rendercfg picks.json  (a list of variant dicts with id + slug)
        for v in json.load(open(a[1])):
            render(v)
    elif a[0] == "render":
        for i in a[1:]:
            render(vs[int(i) - 1])
