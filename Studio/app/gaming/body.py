"""Step 5: render every kept piece with its layout and join them into body-<mode>.mp4 (a port of the Top 5 Realms
build_edit.py, driven by studio.json instead of hard-coded paths).   python body.py <project> draft|final

Gaming rules (user notes 2026-10-20):
- NEVER a full-screen cam: gameplay fills the frame. The talking intro starts full-screen and keyframes the bordered
  cam box down into the TOP-LEFT corner over a B-roll reel.
- Corner cam: white border, always moving (one move per shot), big snap only on URGENT lines with a voice spike,
  gentle pop on hype lines, never on curious lines.
- Inventory / chest / menu panels get a quick eased zoom (ui.json).
- B-roll inserts (notes "broll 3:20 6s <clip>") play full-frame under the cam.
Audio = mic + game audio kept low (game_volume, default 0.3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from glib import NVENC, Project, duration, face_box, fmt, framed_crop, run, say

P = Project(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "draft")
W, H, FPS, k = P.W, P.H, P.FPS, P.k
SRC = P.src
SI = P.source_info
S = P.settings
OUT = P.work / f"segs-{P.mode}"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("seg*.mp4"):
    old.unlink()
keep = P.keep
if not keep:
    sys.exit("no cuts yet")
sections = P.sections
words = P.words
UI = P.read("ui.json", [])
GAME = P.game_crop()
GAME_WIN = S.get("game_crop_windowed") or "1771:996:1994:34"     # windowed Bedrock past the title bar + taskbar
WINDOWED = set(S.get("windowed_sections", []))
CAM = P.cam_crop()                                                # (w, h, x, y) in the full frame, or None
HALF_X = 1920 if SI.get("webcam_side") == "right" else 0


def frame_cam(video, crop):
    """the cam box re-centred on the face of THIS recording (cached in source.json by file + mtime);
    settings.cam_framing = false keeps the fixed box.
    No face in the webcam half = the cam was off (user 2026-10-22: "be smart enough to determine this video didn't have a
    face cam"): no corner cam, the game fills the frame. settings.no_cam true/false forces it either way."""
    if S.get("no_cam") is True:
        return None
    if not crop or SI.get("layout") != "side-by-side":
        return crop
    key = f"{video}|{os.path.getmtime(video):.0f}"
    cache = SI.setdefault("cam_framed", {})
    if key not in cache or "no_cam" not in cache[key]:
        face = face_box(video, HALF_X)
        try:
            import mediapipe  # noqa: F401  (face_box also returns None when mediapipe is missing: that is not "no cam")
            no_face = face is None
        except ImportError:
            no_face = False
        cache[key] = {"face": face, "no_cam": no_face,
                      "crop": framed_crop(list(crop), face, HALF_X) if face and S.get("cam_framing") is not False else list(crop)}
        P.write("source.json", SI)
    if cache[key]["no_cam"] and S.get("no_cam") is not False:
        say(f"no face in the webcam half of {Path(video).name}: cam was off, game full-frame (settings.no_cam=false to force the cam)")
        return None
    say(f"cam framing {Path(video).name}: face {cache[key]['face'] and [round(v) for v in cache[key]['face']]} -> box {cache[key]['crop']}")
    return tuple(cache[key]["crop"])


CAM = frame_cam(SRC, CAM)
GAME_VOL = float(S.get("game_volume", 0.3))
MIC, GAME_TRACK = SI.get("mic_track", 0), SI.get("game_track")
CW, CH = round(480 * k) // 2 * 2, round(440 * k) // 2 * 2
BORDER = max(2, round(6 * k))
MARGIN = round(40 * k)
X0, Y0 = round(60 * k), round(40 * k)
sec_of = P.section_of
URGENT = re.compile(r"^(wait what|wait wait|what is going on|whats going on|what is this|what the|hold on hold|hold on man|"
                    r"oh my goodness|oh no|no no|whoa whoa|whoa hold|is still on me|are you serious|wait a minute)")
HYPE = re.compile(r"^(this is crazy|this is insane|absolutely insane|this is absolutely|so crazy|thats crazy|crazy|insane)")
CALM = re.compile(r"(over here|inside of|for sale|lets see|check it out)")

_raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(P.wf("mic16k.wav")), "-f", "s16le", "-"], capture_output=True).stdout
_sig = (np.frombuffer(_raw, np.int16) / 32768.0) ** 2
_env = 20 * np.log10(np.sqrt(np.convolve(_sig, np.ones(1600) / 1600, "same"))[::1600] + 1e-6)   # 0.1 s dB


def spike(t0, t1):
    a, b = int(t0 * 10), max(int(t1 * 10), int(t0 * 10) + 1)
    loc = _env[max(0, a - 200):a + 200]
    return float(np.max(_env[a:b]) - np.median(loc[loc > -60])) if (loc > -60).any() and b <= len(_env) else 0.0


def outburst(t0, t1):
    """how far the line's peak is above the speaker's own LOUD talking nearby (90th percentile of voiced 0.1 s frames,
    +-20 s). spike() compares with the median, which quiet gaps drag down: a calm "let's see exactly what's going on"
    (Top 10 Servers 6:05) read as a 19.7 dB spike at normal talking level (-26 dB vs -24 dB p90). A real outburst
    ("what the heck, wait, we already leveled up", 8:15, user: "a good option for how it should be") peaks ~7 dB over p90."""
    a, b = int(t0 * 10), max(int(t1 * 10), int(t0 * 10) + 1)
    loc = _env[max(0, a - 200):a + 200]
    v = loc[loc > -60]
    return float(np.max(_env[a:b]) - np.percentile(v, 90)) if len(v) > 20 and b <= len(_env) else 0.0


# an URGENT phrase introduced like this is curiosity, not surprise ("let's see exactly what's going on")
CURIOUS = re.compile(r"(see|seeing|see exactly|find out|figure out|know|check|wonder|show you|tell you|about)$")


def reactions(s, e):
    """URGENT snap (tier 2) only on a real outburst: urgent words at the start of the phrase (not after "let's see"),
    a voice spike AND the peak >= 3 dB over their own loud talking (false hits <= 1.6, real >= 3.6 on Top 10 Servers), and room for the whole snap (1.4 s) before the cut,
    else the cut chops it mid-zoom and the next shot opens on a different size (6:05 -> 6:08 "random zoom ins")."""
    out, last = [], -99
    for i, w in enumerate(words):
        if not (s + 0.2 <= w["s"] <= e - 0.9) or w["s"] - last < 10:
            continue
        txt = " ".join(re.sub(r"[^a-z ]", "", x["w"].lower()) for x in words[i:i + 5])
        prev = " ".join(re.sub(r"[^a-z ]", "", x["w"].lower()) for x in words[max(0, i - 2):i])
        if CALM.search(txt) or re.search(r"(kind of|its|pretty)$", prev):
            continue
        end = words[min(i + 3, len(words) - 1)]["e"]
        if URGENT.match(txt) and not CURIOUS.search(prev) and e - w["s"] >= 1.4 and spike(w["s"], end) >= 5 \
                and outburst(w["s"], end) >= 3:
            out.append((round(w["s"] - s, 2), 2)); last = w["s"]
        elif HYPE.match(txt) and spike(w["s"], end) >= 3:
            out.append((round(w["s"] - s, 2), 1)); last = w["s"]
    return out[:3]


def _smooth(u):   # smoothstep 0..1, zero speed at both ends
    return f"(clip({u},0,1)*clip({u},0,1)*(3-2*clip({u},0,1)))"


def _out(u):      # ease-out cubic: fast start, soft landing
    return f"(1-pow(1-clip({u},0,1),3))"


def _bump(ta, attack, hold, release, snap=False):
    """0 -> 1 -> 0 envelope of a reaction: eased attack from ta, held until ta+hold, eased release back to the base move"""
    up = _out(f"(t-{ta})/{attack}") if snap else _smooth(f"(t-{ta})/{attack}")
    return f"({up}*{_smooth(f'({ta + hold + release}-t)/{release}')})"


def cam_program(i, s, e):
    """Every value is continuous and eased (user 2026-10-24: the cam zoom-in looked choppy at 4:18 and 4:53 of Top 10
    Servers): base moves use smoothstep instead of a linear ramp that stops dead, a reaction eases in, holds and eases
    back to the base move instead of jumping on and off, the urgent shake decays to 0."""
    move = i % 4
    Sx = [f"1+0.14*{_smooth('t/3')}",
          f"if(lt(t,0.35),1+0.3*pow(1-t/0.35,3),1+0.06*{_smooth('(t-0.35)/3')})",
          f"1.12-0.18*{_smooth('t/3')}",
          f"1+0.1*{_smooth('t/2.5')}"][move]
    A = f"-0.05*{_smooth('t/2')}" if move == 3 else "0"
    DX = "0"
    for n, (ta, tier) in enumerate(reactions(s, e)):
        sign = 1 if (i + n) % 2 else -1
        if tier == 2:   # big snap: 0.07 s ease-out attack, hold 1 s, 0.3 s ease back
            env = _bump(ta, 0.07, 1.0, 0.3, snap=True)
            Sx = f"({Sx})+(1.45-({Sx}))*{env}"
            A = f"({A})+({0.07 * sign}-({A}))*{env}"
            DX = f"({DX})+gte(t,{ta})*{round(10 * k, 1)}*sin((t-{ta})*95)*pow(1-clip((t-{ta})/0.3,0,1),2)"
        else:           # gentle pop
            env = _bump(ta, 0.12, 0.7, 0.3)
            Sx = f"({Sx})+(1.22-0.06*clip((t-{ta})/0.7,0,1)-({Sx}))*{env}"
    return Sx, A, DX


def cam_chain(Sx, A, extra_x="0", extra_y="0", crop=None):
    """the bordered cam box on a fixed transparent canvas, scaled + rotated + moved by ONE perspective transform with
    sub-pixel corners and cubic interpolation. The old per-frame scale rounded the size to 2 px (trunc(w/2)*2) and the
    overlay rounded x/y to whole pixels, so a slow zoom moved in 2 px jumps every 4-5 frames (stair steps at 60 fps).
    The canvas is overlaid at 0,0, so nothing is rounded per frame. Same anchor as before: the box grows from its top-left
    corner region (0.12 of the growth to the left/up) and rotates around its centre."""
    cw, ch, cx, cy = crop or CAM
    bw, bh = CW + 2 * BORDER, CH + 2 * BORDER
    pw, ph = bw + 2 * MARGIN, bh + 2 * MARGIN
    cvw, cvh = (X0 + round(bw * 1.75)) // 2 * 2, (Y0 + round(bh * 1.75)) // 2 * 2
    bx, by = MARGIN + bw / 2, MARGIN + bh / 2                       # box centre on the canvas
    tt = f"((in-1)/{FPS})"                                         # perspective has no t: frame count (1-based)
    sub = lambda x: re.sub(r"\bt\b", tt, x)
    head = f"st(0,{sub(Sx)});st(1,{sub(A)});st(2,{sub(extra_x)});st(3,{sub(extra_y)});"
    ccx = f"({X0}+ld(2)-{0.12 * pw:.3f}*(ld(0)-1)+{bw / 2:.3f}*ld(0))"
    ccy = f"({Y0}+ld(3)-{0.12 * ph:.3f}*(ld(0)-1)+{bh / 2:.3f}*ld(0))"
    pts = []
    for c, (qx, qy) in enumerate(((0, 0), (cvw, 0), (0, cvh), (cvw, cvh))):
        dx, dy = qx - bx, qy - by
        pts.append(f"x{c}='{head}{ccx}+ld(0)*({dx:.3f}*cos(ld(1))-({dy:.3f})*sin(ld(1)))'")
        pts.append(f"y{c}='{head}{ccy}+ld(0)*({dx:.3f}*sin(ld(1))+({dy:.3f})*cos(ld(1)))'")
    cam = (f"crop={cw}:{ch}:{cx}:{cy},scale={CW}:{CH}:flags=lanczos,pad={bw}:{bh}:{BORDER}:{BORDER}:color=white,"
           f"format=yuva444p,pad={cvw}:{cvh}:{MARGIN}:{MARGIN}:color=white@0,"
           f"perspective={':'.join(pts)}:sense=destination:interpolation=cubic:eval=frame")
    return cam, "0", "0"


def ui_zoom(s, e):
    hits = [u for u in UI if u["s"] < e and u["e"] > s]
    if not hits:
        return ""
    zs, xs, ys = [], "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    for u in hits:
        a, b = max(u["s"] - s, 0), min(u["e"] - s, e - s)
        bx, by, bw, bh = u["box"]
        zt = max(1.15, min(1.6, 1920 / (bw * 1.15), 1080 / (bh * 1.15)))
        cx, cy = (bx + bw / 2) * k, (by + bh / 2) * k
        zs.append(f"{zt - 1:.3f}*min(max((it-{a:.2f})/0.3,0),1)*min(max(({b:.2f}+0.3-it)/0.3,0),1)")
        xs = f"if(between(it,{a - 0.1:.2f},{b + 0.4:.2f}),{cx:.1f}-iw/zoom/2,{xs})"
        ys = f"if(between(it,{a - 0.1:.2f},{b + 0.4:.2f}),{cy:.1f}-ih/zoom/2,{ys})"
    z = "1+" + "+".join(zs)
    return (f",fps={FPS},zoompan=z='{z}':x='min(max({xs},0),iw-iw/zoom)':y='min(max({ys},0),ih-ih/zoom)'"
            f":d=1:s={W}x{H}:fps={FPS}")


# ---------------------------------------------------------------- B-roll sources
BMAP = {r["clip"]: r for r in (P.read("broll.json", {}) or {}).get("map", [])}   # broll.py: what each Director shot shows


def label_of(c):
    """'cobbledrock charizard attack <file name>' so notes like "broll 3:20 charizard" find the clip"""
    r = BMAP.get(c, {})
    return " ".join(x for x in (r.get("reel", ""), r.get("subject", ""), r.get("shot", ""), os.path.basename(c)) if x)


def broll_clips():
    """[(path, start, dur, label)] from the project's clips (dropped + detected), else the Director sidecar, else gameplay
    snippets from the recording."""
    clips = [c for c in P.doc.get("slots", {}).get("broll", []) if os.path.exists(c)]
    if clips:
        # intro reel order: a different subject each time instead of five shots of the same mob in a row
        by_subj = {}
        for c in clips:
            by_subj.setdefault(BMAP.get(c, {}).get("subject") or c, []).append(c)
        mixed = [lst[i] for i in range(max(map(len, by_subj.values()))) for lst in by_subj.values() if i < len(lst)]
        return [(c, 0.0, min(duration(c) or 4.0, 6.0), label_of(c)) for c in mixed]
    side = SRC + ".broll.json"
    if os.path.exists(side):
        try:
            sc = json.loads(open(side, encoding="utf-8").read())
            got = [(c, 0.0, min(duration(c) or 4.0, 6.0), os.path.basename(c)) for c in sc.get("clips", []) if os.path.exists(c)]
            if got:
                return got
        except Exception:
            pass
    # auto: a 4 s snippet from the middle of the longest piece of every non-intro section, UI panels avoided
    out = []
    for name, s0, e0 in sections:
        if name in ("intro", "outro"):
            continue
        pieces = [(a, b) for a, b in keep if a >= s0 - 0.5 and b <= e0 + 0.5 and b - a > 6]
        pieces.sort(key=lambda p: p[1] - p[0], reverse=True)
        for a, b in pieces[:2]:
            mid = (a + b) / 2
            if any(u["s"] < mid + 2 and u["e"] > mid - 2 for u in UI):
                mid = a + (b - a) * 0.3
            out.append((SRC, round(mid - 2, 2), 4.0, name))
    return out


BROLL = broll_clips()
say(f"B-roll pool: {len(BROLL)} clips ({'dropped/sidecar' if BROLL and BROLL[0][0] != SRC else 'auto from the recording'})")
# notes: "broll 3:20 6s <clip>" -> inserts in raw time
INSERTS = []
for n in P.doc.get("notes", []):
    if n.get("kind") == "broll" and "raw0" in n and not n.get("off"):   # every build, like cuts.py (done = used once)
        want = (n.get("clip") or "").lower()
        pick = next((c for c in BROLL if want and want in c[3].lower()), None)
        if pick is None and BROLL:
            pick = BROLL[len(INSERTS) % len(BROLL)]
        if pick:
            INSERTS.append((n["raw0"], n["raw1"], pick))


def auto_broll():
    """Put the Director's shots into the video by themselves (settings.broll_auto, default on; user 2026-10-22: "if it
    detects the pink B-roll it should automatically put that clip in"). Full-frame under the corner cam, at most
    broll_auto_len (4 s) each, in this order:
    1. where the narration names a clip's subject ("...and Charizard here") -> that clip, at that word;
    2. a clip filmed inside a countdown section belongs to that section -> spread over its kept talk, the first one at
       least 6 s in (the section card + announcement stay on gameplay).
    Never in the intro (it has the reel) or outro, only inside one kept piece, never over an inventory zoom or a manual
    "broll" note, broll_auto_gap (20 s) apart, every clip once, every subject at most twice, broll_per_section (3) max."""
    if not S.get("broll_auto", True) or not BMAP:
        return []
    LEN, GAP, PER = float(S.get("broll_auto_len", 4.0)), float(S.get("broll_auto_gap", 20.0)), int(S.get("broll_per_section", 3))
    pool = [c for c in BROLL if c[0] in BMAP]
    used, subj_n, sec_n, placed = set(), {}, {}, []

    def fits(t, d):
        piece = next(((a, b) for a, b in keep if a + 0.3 <= t and t + d <= b - 0.3), None)
        if not piece or sec_of(t) in ("intro", "outro", "?"):
            return False
        if any(u["s"] < t + d + 0.5 and u["e"] > t - 0.5 for u in UI) or any(r0 < t + d + 1 and r1 > t - 1 for r0, r1, _ in INSERTS):
            return False
        return all(abs(t - p[0]) >= GAP for p in placed)

    def place(t, c, why):
        d = min(LEN, c[2])
        if c[0] in used or not fits(t, d):
            return False
        subj = BMAP[c[0]].get("subject") or c[0]
        sec = sec_of(t)
        if subj_n.get(subj, 0) >= 2 or sec_n.get(sec, 0) >= PER:
            return False
        placed.append((round(t, 3), round(t + d, 3), c, why))
        used.add(c[0]); subj_n[subj] = subj_n.get(subj, 0) + 1; sec_n[sec] = sec_n.get(sec, 0) + 1
        return True

    # 1. spoken subject names (first word of 4+ letters: "Charizard", "Night Fury" -> "night")
    names = {}
    for c in pool:
        subj = (BMAP[c[0]].get("subject") or "").lower()
        key = next((w for w in re.findall(r"[a-z]+", subj) if len(w) >= 4), "")
        if key:
            names.setdefault(key, []).append(c)
    for w in words:
        key = re.sub(r"[^a-z]", "", w["w"].lower())
        for c in names.get(key, []) + names.get(key.rstrip("s"), []):
            if place(w["s"], c, f"said “{w['w'].strip()}”"):
                break
    # 2. home section: where in the recording the reel was filmed
    for name, s0, e0 in sections:
        if name in ("intro", "outro"):
            continue
        home = [c for c in pool if c[0] not in used and BMAP[c[0]].get("main") and s0 - 2 <= float(BMAP[c[0]]["from"]) <= e0 + 30]
        talk = [(a, b) for a, b in keep if a >= s0 - 0.5 and b <= e0 + 0.5 and b - a >= LEN + 1]
        if not home or not talk:
            continue
        total = sum(b - a for a, b in talk)
        n = min(len(home), PER)
        for j in range(n):                      # evenly through the section's kept time, the first 6 s left alone
            want = 6.0 + (total - 6.0) * (j + 0.5) / n
            acc = 0.0
            for a, b in talk:
                if acc + (b - a) >= want:
                    t = a + max(0.4, want - acc)
                    for tt in (t, t + 3, t - 3, t + 8, t - 8):
                        if place(min(tt, b - 0.4 - LEN), home[j], f"filmed in {name}"):
                            break
                    break
                acc += b - a
    return placed


for c in P.read("cover.json", []) or []:   # cuts.py: a talked-over loading screen at a join -> the arrival gameplay
    INSERTS.append((c["s"], c["e"], (SRC, c["from"], c["e"] - c["s"], "cover")))
    say(f"  cover {fmt(c['s'])}-{fmt(c['e'])} with gameplay from {fmt(c['from'])}")
AUTO = auto_broll()
for t0, t1, c, why in AUTO:
    INSERTS.append((t0, t1, c))
    say(f"  auto B-roll {fmt(t0)} ({sec_of(t0)}): {os.path.basename(c[0])} — {why}")
say(f"auto B-roll: {len(AUTO)} clips placed")
# notes {"kind": "insert", "file", "section", "where": "end"|"start"} -> a separate recording (same OBS scene, its own
# voice) spliced in as its own piece right after the section's last kept piece (or before its first). Added 2026-10-21 for
# the River SMP DM story recorded after the Top 10 Servers take.
def mic_of(path):
    """loudest audio track of a dropped clip"""
    n = len(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                           capture_output=True, text=True).stdout.split())
    best, loud = 0, -999.0
    for a in range(n):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", path, "-map", f"0:a:{a}", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        m = re.search(r"mean_volume: (-?[\d.]+)", r)
        if m and float(m.group(1)) > loud:
            best, loud = a, float(m.group(1))
    return best


def find_section(want):
    """section whose name contains the word, else the countdown section where the word is said most"""
    want = want.lower().strip()
    named = [s for s in sections if want and want in s[0].lower()]
    if named:
        return named[0]
    counted = [(sum(1 for w in words if s <= w["s"] <= e and want in w["w"].lower()), (n, s, e)) for n, s, e in sections
               if want and n not in ("intro", "outro")]
    counted = [c for c in counted if c[0]]
    return max(counted)[1] if counted else None


# settings.inserts = the same entries without a note (the notes API only takes cut/protect/broll/text)
INSERT_NOTES = P.doc.get("notes", []) + [dict(x, kind="insert") for x in S.get("inserts", []) or []]
CLIPS = {}   # keep index -> [(path, dur, mic, section, zooms)], rendered right after that piece (-1 = before piece 0)
# "at_raw": t puts the clip at that moment of the recording (user 2026-10-22: the River DM story goes where the
# section already talks about River): the kept piece holding t is split there. "zoom": [{"t0", "t1", "box": [x, y, w, h]}]
# (seconds into the clip, box in the clip's 1920x1080 game/screen half) eases in on something on screen, e.g. a DM.
for n in INSERT_NOTES:
    if n.get("kind") == "insert" and n.get("at_raw") is not None and os.path.exists(n.get("file") or ""):
        t = float(n["at_raw"])
        j = next((i for i, (a, b) in enumerate(keep) if a + 0.3 < t < b - 0.3), None)
        if j is not None:
            a, b = keep[j]
            keep[j:j + 1] = [[a, t], [t, b]]
CLIP_IN = {}   # file -> seconds skipped at its start ("in": dead air before the first word, Top 10 Servers 3:38)


def clip_len(n):
    return duration(n["file"]) - CLIP_IN.get(n["file"], 0.0)


def clip_zooms(n):   # zoom times are seconds into the original clip
    c = CLIP_IN.get(n["file"], 0.0)
    return [dict(z, t0=float(z["t0"]) - c, t1=float(z["t1"]) - c) for z in n.get("zoom") or []]


for n in INSERT_NOTES:
    if n.get("kind") != "insert" or not os.path.exists(n.get("file") or ""):
        continue
    if n.get("in"):
        CLIP_IN[n["file"]] = float(n["in"])
    if n.get("at_raw") is not None:
        t = float(n["at_raw"])
        j = next((i for i, (a, b) in enumerate(keep) if abs(b - t) < 0.35 or a <= t <= b), None)
        if j is None:   # the moment itself was cut: after the last piece that ends before it
            j = max((i for i, (a, b) in enumerate(keep) if b <= t), default=-1)
        CLIPS.setdefault(j, []).append((n["file"], clip_len(n), mic_of(n["file"]), sec_of(keep[max(j, 0)][0]), clip_zooms(n)))
        say(f"insert {Path(n['file']).name} ({clip_len(n):.1f} s) -> at raw {fmt(t)} ({sec_of(keep[max(j, 0)][0])})")
        continue
    sec_ = find_section(n.get("section") or "")
    if not sec_:
        say(f"insert {Path(n['file']).name}: no section matches '{n.get('section')}', skipped")
        continue
    idx = [i for i, p in enumerate(keep) if sec_of(p[0]) == sec_[0]]
    if not idx:
        say(f"insert {Path(n['file']).name}: section {sec_[0]} has no kept pieces, skipped")
        continue
    at_ = idx[0] - 1 if n.get("where") == "start" else idx[-1]
    CLIPS.setdefault(at_, []).append((n["file"], clip_len(n), mic_of(n["file"]), sec_[0], clip_zooms(n)))
    say(f"insert {Path(n['file']).name} ({duration(n['file']):.1f} s) -> {n.get('where', 'end')} of {sec_[0]}")
intro_keep = [p for p in keep if sec_of(p[0]) == "intro"]
intro_len = sum(e - s for s, e in intro_keep)


def reel_clips():
    """What plays behind the talking intro. Default "single" (user 2026-10-22, Top 10 Servers: "we should have just had
    the clip of me just playing on the featured server instead, no need to have a bunch of different ones"): one
    continuous stretch of gameplay from the first countdown section, the server the intro hands over to (its longest
    kept piece without a menu, past the announcement). settings.intro_reel = "mix" = the old reel of every section."""
    if S.get("intro_reel", "single") == "mix":
        return BROLL, 5.0
    ranked = [s for s in sections if s[0] not in ("intro", "outro") and not s[0].startswith("?")]
    if not ranked:
        return BROLL, 5.0
    name, s0, e0 = ranked[0]
    pieces = [(max(a, s0 + 8), b) for a, b in keep if a >= s0 - 0.5 and b <= e0 + 0.5 and b - max(a, s0 + 8) > 3]
    pieces.sort(key=lambda p: p[1] - p[0], reverse=True)
    out = []
    for a, b in pieces:
        free = a
        for u in sorted((u for u in UI if u["s"] < b and u["e"] > a), key=lambda u: u["s"]):
            if u["s"] - free > 3:
                out.append((SRC, round(free, 2), round(u["s"] - free, 2), name))
            free = max(free, u["e"] + 0.3)
        if b - free > 3:
            out.append((SRC, round(free, 2), round(b - free, 2), name))
        if sum(c[2] for c in out) >= intro_len + 0.5:
            break
    say(f"intro reel: {name} gameplay ({len(out)} stretch{'es' if len(out) != 1 else ''})")
    return (out or BROLL), 9999.0


def build_reel():
    """B-roll reel as long as the talking intro, scaled to the frame (reel_clips() decides what is in it)."""
    br = P.wf(f"broll-{P.mode}.mp4")
    pool, cap = reel_clips()
    if intro_len < 0.5 or not pool:
        return None
    cmd, parts, t, n = ["ffmpeg", "-v", "error", "-y"], [], 0.0, 0
    while t < intro_len + 0.2:
        path, st, d, _ = pool[n % len(pool)]
        d = min(d, cap, intro_len + 0.3 - t)
        if path == SRC:
            cmd += ["-ss", f"{st:.3f}", "-t", f"{d + 0.05:.3f}", "-i", SRC]
            parts.append(f"[{len(parts)}:v]crop={GAME},scale={W}:{H},fps={FPS},setsar=1,settb=AVTB,setpts=PTS-STARTPTS[b{len(parts)}];")
        else:
            cmd += ["-ss", f"{st:.3f}", "-t", f"{d + 0.05:.3f}", "-i", path]
            parts.append(f"[{len(parts)}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,settb=AVTB,setpts=PTS-STARTPTS[b{len(parts)}];")
        t += d
        n += 1
        if n > 60:
            break
    cmd += ["-filter_complex", "".join(parts) + "".join(f"[b{q}]" for q in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0,trim=0:{intro_len + 0.2:.3f}[v]",
            "-map", "[v]"] + NVENC + ["-cq", "20", str(br)]
    run(cmd)
    return br


REEL = build_reel()


def punch(i, s, sec):
    """Jump cuts inside a section (user 2026-10-22: "from clip to clip we need to do better on tightening up the
    transitions"): the gameplay after a real jump (> 0.6 s of recording removed) lands 5 % zoomed and eases back to
    1.0 in 0.3 s, so the cut reads as a deliberate punch instead of a skip. Not when a UI zoom is already moving,
    not on a split for an inserted clip. settings.cut_punch = false turns it off."""
    if S.get("cut_punch", True) is False or i == 0 or sec_of(keep[i - 1][0]) != sec or s - keep[i - 1][1] <= 0.6:
        return ""
    if any(u["s"] < s + 0.6 and u["e"] > s - 0.2 for u in UI):
        return ""
    z = f"(1+0.05*pow(max(0,1-t/0.3),2))"
    return f",scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}"


def render(i, piece, broll_at):
    s, e = piece
    d = e - s
    sec = sec_of(s)
    has_cam = CAM is not None
    inputs = ["-ss", f"{s:.4f}", "-t", f"{d:.4f}", "-i", SRC]
    vf = []
    n_in = 1
    first_intro = sec == "intro" and broll_at < 0.01 and REEL is not None and has_cam
    if sec == "intro" and REEL is not None:
        inputs += ["-ss", f"{broll_at:.3f}", "-t", f"{d:.4f}", "-i", str(REEL)]
        game = f"[{n_in}:v]scale={W}:{H},setsar=1[g0]"
        n_in += 1
        if has_cam:   # the webcam feeds the corner cam, plus the full-screen-to-corner move on the very first piece
            vf.append("[0:v]split[vb][vf]" if first_intro else "[0:v]null[vb]")
    else:
        g = GAME_WIN if sec in WINDOWED else GAME
        vf.append("[0:v]split[va][vb]" if has_cam else "[0:v]null[va]")
        game = f"[va]crop={g},scale={W}:{H},setsar=1{ui_zoom(s, e)}{punch(i, s, sec)}[g0]"
    vf.append(game)
    last_g = "g0"
    # B-roll inserts over the gameplay
    for n, (r0, r1, (path, st, cd, _)) in enumerate(x for x in INSERTS if x[0] < e and x[1] > s):
        a, b = max(r0 - s, 0), min(r1 - s, d)
        inputs += ["-ss", f"{st:.3f}", "-t", f"{b - a + 0.1:.3f}", "-i", path]
        if path == SRC:
            vf.append(f"[{n_in}:v]crop={GAME},scale={W}:{H},fps={FPS},setsar=1,setpts=PTS-STARTPTS+{a:.3f}/TB[bi{n}]")
        else:
            vf.append(f"[{n_in}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,setpts=PTS-STARTPTS+{a:.3f}/TB[bi{n}]")
        vf.append(f"[{last_g}][bi{n}]overlay=eof_action=pass:enable='between(t,{a:.3f},{b:.3f})'[gb{n}]")
        last_g = f"gb{n}"
        n_in += 1
    if has_cam:
        Sx, A, DX = cam_program(i, s, e)
        if first_intro:
            Sx, A = f"if(lt(t,0.7),1,{Sx})", f"if(lt(t,0.7),0,{A})"
        cam, ox, oy = cam_chain(Sx, A, extra_x=DX)
        vf.append(f"[vb]{cam}[c]")
        vf.append(f"[{last_g}][c]overlay=x='{ox}':y='{oy}':eval=frame" + (":enable='gte(t,0.7)'" if first_intro else "") + "[gc]")
        last = "gc"
        if first_intro:
            T = 0.7
            cw, ch, cx, cy = CAM
            bw, bh = CW + 2 * BORDER, CH + 2 * BORDER
            f0 = max(W / bw, H / bh) * 1.02
            p = f"(1-pow(1-min(t/{T},1),3))"
            F = f"({f0:.4f}+(1-{f0:.4f})*{p})"
            vf.append(f"[vf]crop={cw}:{ch}:{cx}:{cy},scale={CW}:{CH},pad={bw}:{bh}:{BORDER}:{BORDER}:color=white,"
                      f"scale=w='trunc({bw}*{F}/2)*2':h='trunc({bh}*{F}/2)*2':eval=frame[fs]")
            vf.append(f"[{last}][fs]overlay=x='(1-{p})*({W}-w)/2+{p}*{X0}':y='(1-{p})*({H}-h)/2+{p}*{Y0}':eval=frame:enable='lt(t,{T})'[v0]")
            last = "v0"
    else:
        last = last_g
    if i == len(keep) - 1:
        vf.append(f"[{last}]fade=t=out:st={max(0, d - 0.4):.3f}:d=0.4[fin]")
        last = "fin"
    vf.append(f"[{last}]fps={FPS}[v]")
    # 12-15 ms fades at both seams: a hard audio cut mid-waveform clicks and makes every join feel rougher than it is
    seam = f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.015):.3f}:d=0.015"
    if GAME_TRACK is not None and GAME_TRACK != MIC:
        af = f"[0:a:{MIC}]anull[m];[0:a:{GAME_TRACK}]volume={GAME_VOL}[gm];[m][gm]amix=inputs=2:normalize=0,aresample=48000,{seam}[a]"
    else:
        af = f"[0:a:{MIC}]aresample=48000,{seam}[a]"
    out = OUT / f"seg{i:03d}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(vf) + ";" + af, "-map", "[v]", "-map", "[a]"] + NVENC + [
        "-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "23" if P.mode == "draft" else "12", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{d:.4f}", str(out)]
    if cached(cmd, out):   # same piece, same filters, same inputs as an earlier build: reuse it (revisions, user 2026-10-22)
        return i, sec, d
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"seg {i} ({fmt(s)}): {r.stderr[-700:]}")
    store_cache(cmd, out)
    return i, sec, d


# ---- piece cache (user 2026-10-22: "faster output every single time I do a revision"). A revision usually changes a few
# pieces; the rest render to exactly the same command. The key is the whole ffmpeg command (times, filters, encode) minus
# the output name, plus size + mtime of every input file, so any real change re-renders. settings.seg_cache = false = off.
CACHE = OUT / "cache"
CACHE_ON = S.get("seg_cache", True) is not False
_hits = []


def _key(cmd):
    import hashlib
    parts = [c for c in cmd[:-1]]
    for j, c in enumerate(cmd[:-1]):
        if c == "-i" and j + 1 < len(cmd) and os.path.exists(cmd[j + 1]):
            st_ = os.stat(cmd[j + 1])
            parts.append(f"{st_.st_size}:{int(st_.st_mtime)}")
    return hashlib.sha1(" | ".join(parts).encode("utf-8")).hexdigest()


def cached(cmd, out):
    if not CACHE_ON:
        return False
    src_ = CACHE / (_key(cmd) + ".mp4")
    if src_.exists() and src_.stat().st_size > 1000:
        shutil.copyfile(src_, out)
        os.utime(src_)   # recently used: survives the clean-up
        _hits.append(out.name)
        return True
    return False


def store_cache(cmd, out):
    if CACHE_ON and out.exists():
        CACHE.mkdir(exist_ok=True)
        shutil.copyfile(out, CACHE / (_key(cmd) + ".mp4"))


def clip_zoom(zooms):
    """eased zoompan onto boxes of an inserted clip (0.5 s in, hold, 0.5 s out)"""
    if not zooms:
        return ""
    zs, xs, ys = [], "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    for z in zooms:
        a, b = float(z["t0"]), float(z["t1"])
        bx, by, bw, bh = z["box"]
        zt = max(1.1, min(2.6, 1920 / bw, 1080 / bh))
        cx, cy = (bx + bw / 2) * k, (by + bh / 2) * k
        ease = f"(1-pow(1-min(max((it-{a:.2f})/0.5,0),1),3))*min(max(({b:.2f}-it)/0.5,0),1)"
        zs.append(f"{zt - 1:.3f}*{ease}")
        xs = f"if(between(it,{a - 0.05:.2f},{b + 0.05:.2f}),{cx:.1f}-iw/zoom/2,{xs})"
        ys = f"if(between(it,{a - 0.05:.2f},{b + 0.05:.2f}),{cy:.1f}-ih/zoom/2,{ys})"
    return (f",fps={FPS},zoompan=z='1+{'+'.join(zs)}':x='min(max({xs},0),iw-iw/zoom)':y='min(max({ys},0),ih-ih/zoom)'"
            f":d=1:s={W}x{H}:fps={FPS}")


def render_clip(name, path, d, mic, sec, zooms, n):
    """an inserted recording: its game half full-frame, its webcam in the corner box (framed on its own face), its own
    voice only"""
    zf = clip_zoom(zooms)
    # the corner cam steps aside while the clip is zoomed on on-screen text (Top 10 Servers: it covered the DM's first
    # words); back 0.3 s before the zoom eases out
    off = [f"between(t,{float(z['t0']) + 0.35:.2f},{float(z['t1']) - 0.3:.2f})" for z in zooms]
    hide = f":enable='not({'+'.join(off)})'" if off else ""
    if CAM is not None:
        Sx, A, DX = cam_program(n, -1, -1)
        cam, ox, oy = cam_chain(Sx, A, extra_x=DX, crop=frame_cam(path, P.cam_crop()))
        vf = ["[0:v]split[va][vb]", f"[va]crop={GAME},scale={W}:{H},setsar=1{zf}[g0]", f"[vb]{cam}[c]",
              f"[g0][c]overlay=x='{ox}':y='{oy}':eval=frame{hide}[gc]", f"[gc]fps={FPS}[v]"]
    else:
        vf = [f"[0:v]crop={GAME},scale={W}:{H},setsar=1{zf},fps={FPS}[v]"]
    out = OUT / f"{name}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", f"{CLIP_IN[path]:.3f}"] if CLIP_IN.get(path) else []) + [
           "-i", path, "-filter_complex", ";".join(vf) + f";[0:a:{mic}]aresample=48000[a]",
           "-map", "[v]", "-map", "[a]"] + NVENC + ["-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "23" if P.mode == "draft" else "12",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{d:.4f}", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"insert {Path(path).name}: {r.stderr[-700:]}")
    return name, sec, d


def clip_name(i, j):
    return f"seg{i:03d}x{j}" if i >= 0 else f"seg000a{j}"


jobs, at = [], 0.0
for i, p in enumerate(keep):
    jobs.append((i, p, at if sec_of(p[0]) == "intro" else 0.0))
    if sec_of(p[0]) == "intro":
        at += p[1] - p[0]
clip_jobs = [(clip_name(i, j), path, d, mic, sec, zm, j) for i, lst in CLIPS.items() for j, (path, d, mic, sec, zm) in enumerate(lst)]
say(f"rendering {len(jobs)} pieces + {len(clip_jobs)} inserted clips at {W}x{H} {FPS} fps")
with ThreadPoolExecutor(4) as ex:
    done = sorted(ex.map(lambda a: render(*a), jobs))
    clips_done = {c[0]: c for c in ex.map(lambda a: render_clip(*a), clip_jobs)}
if CACHE_ON:
    say(f"piece cache: {len(_hits)} of {len(jobs)} pieces reused from earlier builds")
    if CACHE.is_dir():   # unused for 3 days = stale
        import time as _t
        for f_ in CACHE.glob("*.mp4"):
            if _t.time() - f_.stat().st_mtime > 3 * 86400:
                f_.unlink(missing_ok=True)
# timeline order: inserts go after their piece. In "keep" an insert is a negative pseudo range (-1e6*(k+1) ...) so every
# raw<->draft mapping (notes, editor, graphics) counts its length without it ever matching a real recording time.
order, keep_tl = [], []


def add_clips(i):
    for j in range(len(CLIPS.get(i, []))):
        name = clip_name(i, j)
        sec, d = clips_done[name][1], clips_done[name][2]
        order.append((name, sec, d))
        base = -1e6 * (len(order) + 1)
        keep_tl.append([base, round(base + d, 3)])


add_clips(-1)
for i, sec, d in done:
    order.append((f"seg{i:03d}", sec, d))
    keep_tl.append(list(keep[i]))
    add_clips(i)
t, starts, prev = 0.0, [], None
for name, sec, d in order:
    if sec != prev:
        starts.append({"section": sec, "t": round(t, 3)})
        prev = sec
    t += d
P.write(f"body-{P.mode}.json", {"duration": round(t, 3), "sections": starts, "pieces": [[n, s, round(d, 3)] for n, s, d in order],
                                "keep": keep_tl, "broll_reel": str(REEL) if REEL else "", "inserts": len(INSERTS), "clips": len(clip_jobs),
                                "auto_broll": [{"raw": t0, "len": round(t1 - t0, 2), "clip": c[0], "why": why} for t0, t1, c, why in AUTO]})
(OUT / "list.txt").write_text("".join(f"file '{n}.mp4'\n" for n, _, _ in order))
run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"), "-c", "copy", str(P.wf(f"body-{P.mode}.mp4"))])
say(f"body-{P.mode}.mp4  {t / 60:.2f} min, {len(done)} pieces")
for s_ in starts:
    say(f"  {fmt(s_['t'])}  {s_['section']}")
