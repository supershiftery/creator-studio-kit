"""Summary Shorts (style 2, user direction 2026-10-21): "what it is + what it does", cut from the RAW side-by-side
recording with the FACE CAM stacked on top of the gameplay, best parts only, own music.

    python shorts_summary.py <project dir> [--work <dir>] [--sections "#4 ThunderCloud,..."] [--len 26]

Per ranked section it builds 3 beats from words that survived the edit (cuts/cuts.json keep ranges):
  1. WHAT IT IS  - the first sentence group that names the entry (or "number N"), 4-8 s
  2+3. WHAT IT DOES - the two strongest 6-10 s moments (voice spikes + hype words), chronological
Layout 1080x1920: cam 1080x810 on top (4:3 crop of the webcam), gameplay 1080x1110 below (centre crop of the
game window), entry card over the seam, series badge, keyword pops over the game, 2.5 s end card (link-back).
Audio: mic normalised to -16 LUFS + a game OST bed from music_pool.json about 18 LU under it.
Output: <project>\\Shorts\\summary\\<nn>-<slug>.mp4 + .txt
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glib import HERE, NVENC, Project, duration, lufs, run, say  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--work")
ap.add_argument("--sections")
ap.add_argument("--len", type=float, default=50.0, help="target length; the 160K+ commentary Shorts in the study ran 47-58 s")
ap.add_argument("--game-crop", default="", help="crop w:h:x:y of the game window inside the raw frame (default: windowed Bedrock 1771:996:1994:34)")
args = ap.parse_args()

P = Project(args.project, "final")
WORK = Path(args.work) if args.work else P.work
OUT = P.path / "Shorts" / "summary"
OUT.mkdir(parents=True, exist_ok=True)
TMP = WORK / "shorts-summary-tmp"
TMP.mkdir(exist_ok=True)


def J(name, default=None):
    p = WORK / name
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else default


SRC = Path(P.doc.get("source") or J("source.json", {}).get("src", ""))
SI = J("source.json", {})
keep = [list(x) for x in (J("cuts/cuts.json") or {"keep": []})["keep"]]
words = J("words.json", [])
sections = [tuple(s) for s in J("sections.json", [])]
UI = J("ui.json", []) or []
if not (SRC.exists() and keep and words and sections):
    sys.exit(f"need the raw recording ({SRC}), cuts/cuts.json, words.json and sections.json in {WORK}")
CAM = tuple(SI.get("cam_crop") or (1000, 917, 700, 20))
GAME = args.game_crop or SI.get("game_crop") or P.settings.get("game_crop_windowed") or "1771:996:1994:34"
MIC_TRACK = int(SI.get("mic_track") or 0)
POOL = json.loads((HERE / "music_pool.json").read_text(encoding="utf-8-sig"))


def kept(t):
    return any(s - 0.02 <= t <= e + 0.02 for s, e in keep)


# ---------------------------------------------------------------- voice energy
_env = None
mic = WORK / "mic16k.wav"
if mic.exists():
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mic), "-f", "s16le", "-"], capture_output=True).stdout
    sig = (np.frombuffer(raw, np.int16) / 32768.0) ** 2
    _env = 20 * np.log10(np.sqrt(np.convolve(sig, np.ones(1600) / 1600, "same"))[::1600] + 1e-6)


def spike(t0, t1):
    if _env is None:
        return 0.0
    a, b = int(t0 * 10), max(int(t1 * 10), int(t0 * 10) + 1)
    if b > len(_env):
        return 0.0
    loc = _env[max(0, a - 300):a + 300]
    loc = loc[loc > -60]
    return float(np.max(_env[a:b]) - np.median(loc)) if len(loc) else 0.0


HYPE = re.compile(r"^(insane|crazy|wild|bro|literally|free|best|biggest|huge|massive|wow|whoa|what|look|dude|no way|oh my|hold on|wait|bruh|op|epic|fire)", re.I)
POPWORDS = {"insane", "crazy", "wild", "free", "best", "huge", "massive", "wow", "whoa", "epic", "fire", "op", "literally", "biggest", "look"}
SENT_END = re.compile(r"[.!?]$")
TITLE = re.sub(r"\s*\((19|20)\d\d\)\s*", " ", P.doc.get("title") or P.path.name).strip()

research = {}
RES = Path(r"{{KIT}}/tools/minecraft\Research")
for f in sorted(RES.glob("*.json")) if RES.exists() else []:
    try:
        d = json.loads(f.read_text(encoding="utf-8-sig"))
        if isinstance(d, list) and d and isinstance(d[0], dict) and "rank" in d[0] and "name" in d[0]:
            for e in d:
                research.setdefault(e["name"].lower(), e)
    except Exception:
        continue


def entry_info(name):
    m = re.match(r"^(#(\d+)|HM)\s+(.*)$", name)
    rank = f"#{m.group(2)}" if m and m.group(2) else "HM"
    label = (m.group(3) if m else name).strip()
    key = label.lower()
    r = research.get(key) or next((v for k, v in research.items() if k.startswith(key) or key.startswith(k) or k.split()[0] == key.split()[0]), {})
    cat = r.get("category") or r.get("mode") or ""
    if rank == "HM":
        cat = ("HONORABLE MENTION · " + cat) if cat else "HONORABLE MENTION"
    return rank, label[:18], cat[:44], TITLE.upper().replace("MINECRAFT ", ""), r


# ---------------------------------------------------------------- beats
def sentences(ws, pause=0.45):
    """[(i, j)] index ranges of speech groups: a group ends on punctuation or on a measured pause >= `pause` s
    (small.en punctuates sparsely, and a pause is the one place a cut never clips a word)"""
    out, i = [], 0
    for j, w in enumerate(ws):
        gap = (ws[j + 1]["s"] - w["e"]) if j + 1 < len(ws) else 9
        if SENT_END.search(w["w"]) or gap >= pause or j == len(ws) - 1:
            out.append((i, j))
            i = j + 1
    return out


def grow(ws, sents, k, lo, hi):
    """extend sentence k forward by WHOLE sentences until the span is within [lo, hi] seconds.
    Never cuts inside a sentence (user: 'we can't have my words getting cut off'); a lone sentence longer
    than hi is kept whole up to hi + 8 s."""
    i, j = sents[k]
    kk = k
    while ws[j]["e"] - ws[i]["s"] < lo and kk + 1 < len(sents):
        nj = sents[kk + 1][1]
        if ws[nj]["e"] - ws[i]["s"] > hi and ws[j]["e"] - ws[i]["s"] >= lo * 0.6:
            break
        kk += 1
        j = nj
    if ws[j]["e"] - ws[i]["s"] > hi + 8:
        # one long breathless group: end it at the biggest pause inside the window instead of dropping it
        best, bj = 0.0, None
        for q in range(i + 3, j):
            if ws[q]["e"] - ws[i]["s"] > hi:
                break
            gap = ws[q + 1]["s"] - ws[q]["e"]
            if gap > best:
                best, bj = gap, q
        if bj is None or best < 0.08:
            return None
        j = bj
    if ws[j]["e"] - ws[i]["s"] < lo * 0.6:
        return None
    return snap(ws, i, j)


def snap(ws, i, j):
    """clip edges on measured silence around the first and last word (whisper word times run tight)"""
    a, b = ws[i]["s"], ws[j]["e"]
    prev_end = ws[i - 1]["e"] if i > 0 else a - 1
    a0 = max(a - 0.35, prev_end + 0.04)
    nxt = ws[j + 1]["s"] if j + 1 < len(ws) else b + 2
    b0 = min(b + 0.9, nxt - 0.04)
    if _env is not None:
        seg = _env[int(b * 10):int(b0 * 10) + 1]
        loc = _env[max(0, int(b * 10) - 300):int(b * 10) + 300]
        loc = loc[loc > -60]
        thr = (np.median(loc) - 12) if len(loc) else -45
        for n, v in enumerate(seg):
            if n >= 3 and v < thr:                 # at least 0.3 s of tail, then the first quiet frame
                b0 = b + n / 10
                break
    return a0, max(b0, b + 0.3)


def beats_for(name, s, e, label, target):
    ws = [w for w in words if s <= w["s"] and w["e"] <= e and kept(w["s"])]
    if len(ws) < 20:
        say(f"   {name}: only {len(ws)} kept words")
        return None
    sents = sentences(ws)
    low = [re.sub(r"[^a-z0-9 ]", "", " ".join(x["w"] for x in ws[i:j + 1]).lower()) for i, j in sents]
    lab = label.lower().split()[0]
    # beat 1 starts at least 10 s into the section: the Join Realm screen (with the code typed on it) sits before
    # that, and the user never wants a realm code on screen in a Short (the link-back is the point)
    late = [k for k, (i, j) in enumerate(sents) if ws[i]["s"] - s >= 10]
    if not late:
        return None
    k1 = next((k for k in late if lab in low[k] or re.search(r"\bnumber (one|two|three|four|five|six|seven|eight|nine|ten|\d)\b", low[k]) or "honorable mention" in low[k]), late[0])
    b1 = grow(ws, sents, k1, 6, 10) or next((g for k in late if (g := grow(ws, sents, k, 6, 10))), None)
    if not b1:
        say(f"   {name}: no opening beat")
        return None
    cands = []
    for k, (i, j) in enumerate(sents):
        if k == k1 or ws[i]["s"] - s < 10:
            continue
        g = grow(ws, sents, k, 8, 12)
        if not g:
            continue
        a, b = g
        if a < b1[1] and b > b1[0]:
            continue
        txt = [re.sub(r"[^a-z ]", "", w["w"].lower()) for w in ws if a <= w["s"] <= b]
        hype = sum(1 for q, t in enumerate(txt) if HYPE.match(" ".join(txt[q:q + 2])))
        menu = sum(max(0.0, min(u["e"], b) - max(u["s"], a)) for u in UI)
        cands.append((hype * 2 + spike(a, b) * 0.6 + min(menu, 3) * 0.5, a, b))
    cands.sort(reverse=True)
    picked, total = [], b1[1] - b1[0]
    for sc, a, b in cands:
        if any(a < pb and b > pa for _, pa, pb in picked):
            continue
        picked.append((sc, a, b))
        total += b - a
        if total >= target - 4 or len(picked) == 5:
            break
    beats = [b1] + sorted((a, b) for _, a, b in picked)
    # still short of the target: extend beats forward by whole sentences (max 18 s a beat) until it fits
    ends = {sents[k][1]: k for k in range(len(sents))}
    changed = True
    while total < target - 4 and changed:
        changed = False
        for bi, (a, b) in enumerate(beats):
            jw = next((j for j in range(len(ws)) if abs(ws[j]["e"] - b) < 1.0 or (ws[j]["e"] <= b and (j + 1 == len(ws) or ws[j + 1]["s"] > b))), None)
            if jw is None or jw not in ends or ends[jw] + 1 >= len(sents):
                continue
            ni, nj = sents[ends[jw] + 1]
            nxt_end = snap(ws, ni, nj)[1]
            if nxt_end - a > 18 or any(o != bi and oa < nxt_end and b < ob for o, (oa, ob) in enumerate(beats)):
                continue
            total += nxt_end - b
            beats[bi] = (a, nxt_end)
            changed = True
            if total >= target - 4:
                break
    say(f"   {name}: {len(sents)} sentence groups, {len(cands)} candidates, {len(beats)} beats, {total:.1f} s")
    return beats, ws, total


# ---------------------------------------------------------------- render
FONT_B = "C\\:/Windows/Fonts/segoeuib.ttf"
FONT_P = "C\\:/Windows/Fonts/impact.ttf"


def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "%%").replace(",", "\\,")


cw, ch, cx, cy = CAM
cam4x3_h = min(ch, int(cw * 3 / 4))
cam_filter = f"crop={cw}:{cam4x3_h}:{cx}:{cy + max(0, (ch - cam4x3_h) // 3)},scale=1080:810:flags=lanczos"
gw, gh, gx, gy = (int(v) for v in GAME.split(":"))
gh2 = int(gh * 0.86) // 2 * 2                      # top 86%: the hotbar and chat strip fall outside
tw = int(gh2 * 1080 / 1110) // 2 * 2
game_filter = f"crop={gw}:{gh}:{gx}:{gy},crop={tw}:{gh2}:{(gw - tw) // 2}:0,scale=1080:1110:flags=lanczos"


from difflib import SequenceMatcher  # noqa: E402

CODE_RE = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9_-]{9,16}$")
NOT_CODES = {"EXAMPLECODE", "starter", "legendary", "legendarybonus", "position"}   # gamertag + UI words the OCR garbles into code-like junk
KNOWN = {str(v.get("code", "")).lower() for v in research.values()} | {str(v.get("placeholder", {}).get("code", "")).lower() for v in research.values()}
OCR_PS1 = HERE / "ocr_frames.ps1"
OCR_W = 960


def code_boxes(a, b, idx):
    """[(t_rel, x, y, w, h)] of realm-code / invite-looking text in the Short's game area during raw [a, b]
    (user rule: never a realm code on screen; the link-back is the point). Windows OCR at 2 fps."""
    fdir = TMP / f"ocr-{idx}"
    for old in fdir.glob("*") if fdir.exists() else []:
        old.unlink()
    fdir.mkdir(exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(SRC),
         "-vf", f"{game_filter.rsplit(',scale', 1)[0]},scale={OCR_W}:-1,fps=2", str(fdir / "f%04d.png")])
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OCR_PS1), str(fdir)],
                       capture_output=True, text=True, errors="replace")
    hits, k = [], 1080 / OCR_W
    for line in r.stdout.splitlines():
        p = line.split("\t")
        if len(p) != 6:
            continue
        fn, txt, x, y, w, h = p
        t = (int(fn[1:5]) - 1) / 2.0
        clean = re.sub(r"[^A-Za-z0-9_/.-]", "", txt)
        lc = clean.lower()
        if not clean or any(SequenceMatcher(None, lc, bad).ratio() >= 0.6 for bad in NOT_CODES):
            continue
        fuzzy = any(c and len(c) >= 9 and abs(len(c) - len(lc)) <= 3 and SequenceMatcher(None, lc, c).ratio() >= 0.45 for c in KNOWN)   # pixel fonts OCR badly
        if (CODE_RE.match(clean) and sum(ch.isdigit() for ch in clean) >= 2) or "gg/" in lc or lc in KNOWN or fuzzy:
            hits.append((t, int(int(x) * k) - 10, int(int(y) * k) + 810 - 8, int(int(w) * k) + 20, int(int(h) * k) + 16))
    # merge detections of the same on-screen text into one span: a panel stays open longer than OCR catches it
    spans = []
    for t, x, y, w, h in sorted(hits):
        for sp in spans:
            if abs(sp["x"] + sp["w"] / 2 - (x + w / 2)) < 80 and abs(sp["y"] - y) < 40 and t - sp["t1"] <= 3.0:
                sp["t1"] = t
                sp["x"], sp["y"] = min(sp["x"], x), min(sp["y"], y)
                sp["w"], sp["h"] = max(sp["w"], w), max(sp["h"], h)
                break
        else:
            spans.append({"t0": t, "t1": t, "x": x, "y": y, "w": w, "h": h})
    return [(sp["t0"] - 0.8, sp["t1"] + 0.8, sp["x"], sp["y"], sp["w"], sp["h"]) for sp in spans]


def render_beat(idx, a, b, out):
    d = b - a
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(SRC),
           "-filter_complex", f"[0:v]split[c][g];[c]{cam_filter}[cam];[g]{game_filter}[game];[cam][game]vstack,setsar=1,fps=60[v]",
           "-map", "[v]", "-map", f"0:a:{MIC_TRACK}", *NVENC, "-rc", "vbr", "-cq", "17", "-b:v", "0", "-c:a", "pcm_s16le", str(out)]
    run(cmd)
    return duration(out)


def pick_music(cat, n):
    pool = POOL.get("pokemon") if re.search(r"pok|cobble|pixelmon", cat, re.I) else (POOL.get("shorts") or POOL.get("general", []))
    pool = [t for t in pool if t.get("mood") not in ("intro", "outro")] or pool
    return pool[n % len(pool)] if pool else None


results = []
targets = [x.strip() for x in args.sections.split(",")] if args.sections else None
n = 0
for name, s, e in sections:
    if name in ("intro", "outro") or not re.match(r"^(#\d+|HM)\b", name) or (targets and name not in targets):
        continue
    rank, label, cat, series, info = entry_info(name)
    if info.get("needs_new_code"):
        say(f"HOLD {name}: needs a new code")
        continue
    got = beats_for(name, s, e, label, args.len)
    if not got:
        say(f"skip {name}: not enough kept speech")
        continue
    beats, ws, total = got
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    nn = f"{int(rank[1:]):02d}" if rank.startswith("#") else f"hm{n}"
    parts, at, pops, marks = [], 0.0, [], []
    masks = []
    for i, (a, b) in enumerate(beats):
        p = TMP / f"{nn}-beat{i}.mov"
        d = render_beat(i, a, b, p)
        masks += [(at + t0, at + t1, x, y, w, h) for t0, t1, x, y, w, h in code_boxes(a, b, f"{nn}-{i}")]
        for w in ws:
            clean = re.sub(r"[^a-z]", "", w["w"].lower())
            if a <= w["s"] <= b and clean in POPWORDS and (not pops or at + (w["s"] - a) - pops[-1][0] >= 2.5) and len(pops) < 6:
                pops.append((at + (w["s"] - a), clean))
        marks.append(at)
        parts.append(p)
        at += d
    D = at
    (TMP / f"{nn}-list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    joined = TMP / f"{nn}-joined.mov"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(TMP / f"{nn}-list.txt"), "-c", "copy", str(joined)])
    # music bed
    m = pick_music(cat, n)
    vg = -14.0 - lufs(joined)          # Shorts play louder than long-form; the bed sits ~18 LU under
    if m and Path(m["track"]).exists():
        bed = TMP / f"{nn}-bed.wav"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(m.get("offset", 0)), "-t", f"{D + 1:.2f}", "-i", m["track"], "-ac", "2", "-ar", "48000", str(bed)])
        bg = -32.0 - lufs(bed)
        amix = (f"[0:a]volume={vg:.2f}dB[v0];[1:a]volume={bg:.2f}dB,afade=t=in:d=0.6,afade=t=out:st={max(D - 1.2, 0):.2f}:d=1.2[m0];"
                f"[v0][m0]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.84:level=0[a]")
        ain = ["-i", str(bed)]
    else:
        amix = f"[0:a]volume={vg:.2f}dB,alimiter=limit=0.84:level=0[a]"
        ain = []
    # graphics
    e0 = max(D - 2.5, 0)
    on = f":enable='lt(t,{e0:.2f})'"
    g = [f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x101010@0.97:t=fill:enable='between(t,{t0:.2f},{t1:.2f})'"
         for t0, t1, x, y, w, h in masks]
    g += [f"drawbox=x=0:y=790:w=iw:h=6:color=white@0.9:t=fill",
         f"drawbox=x=60:y=740:w=960:h=120:color=black@0.72:t=fill{on}",
         f"drawbox=x=60:y=740:w=960:h=120:color=white@0.9:t=4{on}",
         f"drawtext=fontfile='{FONT_B}':text='{esc(rank)}':fontcolor=0xFFD54A:fontsize=50:x=96:y=756{on}",
         f"drawtext=fontfile='{FONT_B}':text='{esc(label.upper())}':fontcolor=white:fontsize=52:x={96 + 34 * len(rank) + 36}:y=754{on}"]
    if cat:
        g.append(f"drawtext=fontfile='{FONT_B}':text='{esc(cat.upper())}':fontcolor=0xFFD54A:fontsize=30:x=96:y=816{on}")
    g.append(f"drawtext=fontfile='{FONT_B}':text='{esc(series)}':fontcolor=white:fontsize=34:box=1:boxcolor=black@0.55:boxborderw=12:x=60:y=1500")
    for i, t0 in enumerate(marks):
        tag = "WHAT IT IS" if i == 0 else f"WHAT IT DOES · {i}"
        g.append(f"drawtext=fontfile='{FONT_B}':text='{esc(tag)}':fontcolor=black:fontsize=34:box=1:boxcolor=0xFFD54A:boxborderw=12:x=60:y=880:enable='between(t,{t0:.2f},{t0 + 2.2:.2f})'")
    for t0, word in pops:
        g.append(f"drawtext=fontfile='{FONT_P}':text='{esc(word.upper())}':fontcolor=0xFFD54A:bordercolor=black:borderw=8:fontsize=140:x=(w-tw)/2:y=1250:enable='between(t,{t0:.2f},{t0 + 0.7:.2f})'")
    g += [f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.55:t=fill:enable='gte(t,{e0:.2f})'",
          f"drawtext=fontfile='{FONT_B}':text='FULL VIDEO':fontcolor=0xFFD54A:fontsize=120:x=(w-tw)/2:y=640:enable='gte(t,{e0:.2f})'",
          f"drawtext=fontfile='{FONT_B}':text='ON THE CHANNEL':fontcolor=white:fontsize=84:x=(w-tw)/2:y=780:enable='gte(t,{e0:.2f})'",
          f"drawtext=fontfile='{FONT_B}':text='{esc(TITLE)}':fontcolor=white:fontsize=46:box=1:boxcolor=black@0.5:boxborderw=18:x=(w-tw)/2:y=920:enable='gte(t,{e0:.2f})'"]
    out = OUT / f"{nn}-{slug}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), *ain, "-filter_complex", "[0:v]" + ",".join(g) + ",format=yuv420p[v];" + amix,
         "-map", "[v]", "-map", "[a]", *NVENC, "-rc", "vbr", "-cq", "19", "-b:v", "0", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    say(f"{name}: {len(beats)} beats {[f'{a:.0f}-{b:.0f}' for a, b in beats]} = {D:.1f} s, {len(pops)} pops, {len(masks)} code masks, music {Path(m['track']).stem[:30] if m else 'none'} -> {out.name}")
    hub = info.get("listings") or ""
    out.with_suffix(".txt").write_text("\n".join([
        f"TITLE: {label}: what this Bedrock realm is and what it does #shorts",
        "DESCRIPTION:", f"Full video: {TITLE} (on the channel, link in the pinned comment)", (f"{label} page: {hub}" if hub else ""),
        "#minecraft #minecraftbedrock #realms #shorts", "",
        "UPLOAD NOTES: set this Short's 'Related video' to the full upload in YouTube Studio and pin a comment with the full video link."]), encoding="utf-8")
    results.append({"section": name, "file": str(out), "beats": beats, "duration": round(D, 2), "pops": pops, "music": m, "masks": masks})
    n += 1

(OUT / "shorts-summary.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
say(f"{len(results)} summary shorts -> {OUT}")
