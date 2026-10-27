"""Auto-Shorts from a finished gaming edit (Top N / countdown / showcase).

    python shorts.py <project dir> [final|draft] [--video <final.mp4>] [--work <dir>] [--sections "#4 ThunderCloud,#2 ..."] [--len 24]

For every ranked section it picks the strongest 18-32 s window (voice spikes + hype words, sentence-bounded,
inside one section), crops the FINAL render to 9:16 (the gameplay centre; the corner cam falls outside the crop),
and layers the Shorts package studied on 2026-10-21 (Tradissh / ItsArenZ / supermj767 pattern):
  - pinned entry card at the top for the whole short ("#4 · THUNDERCLOUD" + category line),
  - series badge above the YouTube UI zone ("TOP 5 BEDROCK REALMS"),
  - up to 6 keyword pops on hype words (no bottom captions: user rule),
  - a 3 s end card: "FULL VIDEO ON THE CHANNEL" + the long-form title (the link-back; the VA also sets the
    Short's Related video in YouTube Studio).
Audio is the final's own mix. Output: <project>\\Shorts\\<nn>-<slug>.mp4 + .txt (title, description, tags) + shorts.json.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glib import NVENC, Project, run, say  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("mode", nargs="?", default="final")
ap.add_argument("--video")
ap.add_argument("--work", help="work dir holding cuts/cuts.json, words.json, mic16k.wav, timeline-<mode>.json (default Edit/studio)")
ap.add_argument("--sections", help="comma list of section names to render (default: every ranked one)")
ap.add_argument("--len", type=float, default=24.0, help="target length in seconds (18-32)")
ap.add_argument("--max", type=int, default=99)
args = ap.parse_args()

P = Project(args.project, args.mode)
WORK = Path(args.work) if args.work else P.work
VIDEO = Path(args.video) if args.video else P.out_video()
if not VIDEO.exists():
    sys.exit(f"final video not found: {VIDEO}")
OUT = P.path / "Shorts"
OUT.mkdir(exist_ok=True)


def J(name, default=None):
    p = WORK / name
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else default


keep = [list(x) for x in (J("cuts/cuts.json") or {"keep": []})["keep"]]
words = J("words.json", [])
sections = [tuple(s) for s in J("sections.json", [])]
tl = J(f"timeline-{args.mode}.json") or J("timeline-final.json") or {"intro": 0.0}
INTRO = float(tl.get("intro", 0.0))
UI = J("ui.json", []) or []
if not (keep and words and sections):
    sys.exit(f"need cuts/cuts.json, words.json and sections.json in {WORK}")

# ---------------------------------------------------------------- raw time -> final time
def raw_to_final(t):
    at = 0.0
    for s, e in keep:
        if s - 0.02 <= t <= e + 0.02:
            return INTRO + at + (t - s)
        at += e - s
    return None


def section_of(t):
    for name, s, e in sections:
        if s - 0.5 <= t <= e + 0.5:
            return name
    return "?"


# ---------------------------------------------------------------- voice energy (0.1 s dB), same as body.py
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


# ---------------------------------------------------------------- menu / loading / join-screen detector on the FINAL video
# one pass at 2 fps: per-frame average saturation. Gameplay is colourful; the Join Realm dialog, loading and pause
# screens are grey, so a window whose first seconds sit under the saturation floor is penalised hard.
def sat_scan():
    cache = WORK / "shorts-scan.json"
    if cache.exists():
        return json.loads(cache.read_text())
    say("scanning the final for grey menu screens (one-time)")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(VIDEO), "-vf", "fps=2,scale=96:-1,signalstats,metadata=print:file=-",
                        "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    sats, t = [], None
    for line in r.stdout.splitlines():
        if "pts_time:" in line:
            t = float(line.split("pts_time:")[1].split()[0])
        elif "signalstats.SATAVG=" in line and t is not None:
            sats.append([round(t, 2), float(line.split("=")[1])])
    cache.write_text(json.dumps(sats))
    return sats


SAT = sat_scan()


def grey_seconds(f0, f1, floor):
    return 0.5 * sum(1 for t, s in SAT if f0 <= t <= f1 and s < floor)


def sat_floor(f0, f1):
    """Menus are much greyer than this section's own gameplay: 60% of the section's median saturation."""
    v = sorted(s for t, s in SAT if f0 <= t <= f1)
    return 0.6 * v[len(v) // 2] if v else 0.0


HYPE = re.compile(r"^(insane|crazy|wild|bro|literally|free|best|biggest|huge|massive|wow|whoa|what|look|dude|no way|oh my|hold on|wait|bruh|op|epic|fire|w\b)", re.I)
POPWORDS = {"insane", "crazy", "wild", "free", "best", "huge", "massive", "wow", "whoa", "epic", "fire", "op", "literally", "biggest", "look"}
SENT_END = re.compile(r"[.!?]$")


# ---------------------------------------------------------------- pick the window per section
def ranked_sections():
    out = []
    for name, s, e in sections:
        if name in ("intro", "outro") or not re.match(r"^(#\d+|HM)\b", name):
            continue
        if args.sections and name not in [x.strip() for x in args.sections.split(",")]:
            continue
        out.append((name, s, e))
    return out


def best_window(s, e, target):
    ws = [w for w in words if s <= w["s"] and w["e"] <= e and raw_to_final(w["s"]) is not None]
    if len(ws) < 12:
        return None
    starts = [i for i, w in enumerate(ws) if i == 0 or SENT_END.search(ws[i - 1]["w"])]
    late = [i for i in starts if ws[i]["s"] - s >= 12]          # the join screen / loading sits at the top of every section
    starts = late or starts
    fs, fe = raw_to_final(ws[0]["s"]), raw_to_final(ws[-1]["e"])
    floor = sat_floor(fs, fe)
    best = None
    for i in starts:
        j = i
        while j + 1 < len(ws) and ws[j + 1]["e"] - ws[i]["s"] <= target + 8:
            j += 1
            if ws[j]["e"] - ws[i]["s"] >= target - 6 and SENT_END.search(ws[j]["w"]):
                f0, f1 = raw_to_final(ws[i]["s"]), raw_to_final(ws[j]["e"])
                if f0 is None or f1 is None or not (18 <= f1 - f0 <= 32):
                    continue
                txt = [re.sub(r"[^a-z ]", "", w["w"].lower()) for w in ws[i:j + 1]]
                hype = sum(1 for k, t in enumerate(txt) if HYPE.match(" ".join(txt[k:k + 2])))
                sp = max(spike(w["s"], w["e"]) for w in ws[i:j + 1])
                score = hype * 2 + sp * 0.6 - abs((f1 - f0) - target) * 0.15
                score -= 2.5 * grey_seconds(f0, min(f0 + 4, f1), floor) + 0.8 * grey_seconds(f0 + 4, f1, floor)   # menus, join screen, loading
                score -= 3 * sum(max(0.0, min(u["e"], ws[j]["e"]) - max(u["s"], ws[i]["s"])) for u in UI)   # menus open on screen
                if best is None or score > best[0]:
                    best = (score, ws[i]["s"], ws[j]["e"], ws[i:j + 1])
    return best


# ---------------------------------------------------------------- names and research
TITLE = re.sub(r"\s*\((19|20)\d\d\)\s*", " ", P.doc.get("title") or P.path.name).strip()     # no dates in graphics
research = {}
for f in sorted(Path(r"{{KIT}}/tools/minecraft\Research").glob("*.json")) if Path(r"{{KIT}}/tools/minecraft\Research").exists() else []:
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
    if len(label) > 18:
        label = label[:17] + "…"
    key = label.lower()
    r = research.get(key) or next((v for k, v in research.items() if k.startswith(key) or key.startswith(k) or k.split()[0] == key.split()[0]), {})
    cat = r.get("category") or r.get("mode") or ""
    if rank == "HM":
        cat = ("HONORABLE MENTION · " + cat) if cat else "HONORABLE MENTION"
    if len(cat) > 44:
        cat = cat[:43] + "…"
    series = TITLE.upper().replace("MINECRAFT ", "")
    return rank, label, cat, series, r


FONT_B = "C\\:/Windows/Fonts/segoeuib.ttf" if Path("C:/Windows/Fonts/segoeuib.ttf").exists() else "C\\:/Windows/Fonts/arialbd.ttf"
FONT_P = "C\\:/Windows/Fonts/impact.ttf"


def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "%%").replace(",", "\\,")


def build_filter(d, rank, label, cat, series, pops, wide_spans=()):
    # base: centre 9:16 crop of the 16:9 final, up to 1080x1920
    # top 85% of the frame only: the hotbar, chat and the bottom-left cam snaps fall outside; nudged right of centre
    f = ["[0:v]split=3[s0][s1][s2]",
         "[s0]crop=ih*0.85*9/16:ih*0.85:(iw-ih*0.85*9/16)/2+60:0,scale=1080:1920:flags=lanczos,setsar=1[c]"]
    chain = "[c]"
    if wide_spans:
        # menu open: the full 16:9 frame (1080x608) floats mid-frame over a blurred, darkened copy of the crop
        en = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in wide_spans)
        f += ["[s1]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,boxblur=30:4,eq=brightness=-0.25[bg]",
              "[s2]scale=1080:-2,setsar=1,pad=1080:1920:0:(oh-ih)/2:color=black@0[wide]",
              f"[bg][wide]overlay=0:0:format=auto[w]",
              f"[c][w]overlay=0:0:enable='{en}'[b]"]
        chain = "[b]"
    else:
        f.append("[s1]nullsink"); f.append("[s2]nullsink")
    # top pinned entry card (y 150-330), dark box, white rank + name, gold category
    card = [
        f"drawbox=x=60:y=150:w=960:h=180:color=black@0.62:t=fill",
        f"drawbox=x=60:y=150:w=960:h=180:color=white@0.9:t=4",
        f"drawtext=fontfile='{FONT_B}':text='{esc(rank)}':fontcolor=0xFFD54A:fontsize=54:x=100:y=178",
        f"drawtext=fontfile='{FONT_B}':text='{esc(label.upper())}':fontcolor=white:fontsize=58:x=100+tw_rank:y=176".replace("x=100+tw_rank", f"x={100 + 36 * len(rank) + 40}"),
    ]
    if cat:
        card.append(f"drawtext=fontfile='{FONT_B}':text='{esc(cat.upper())}':fontcolor=0xFFD54A:fontsize=34:x=100:y=258")
    # series badge above the Shorts UI zone (keep clear of the bottom ~330 px and the right ~160 px)
    card.append(f"drawtext=fontfile='{FONT_B}':text='{esc(series)}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.55:boxborderw=14:x=60:y=1480")
    # keyword pops: 0.7 s, impact, yellow with black border, low centre
    for t0, word in pops:
        card.append(f"drawtext=fontfile='{FONT_P}':text='{esc(word.upper())}':fontcolor=0xFFD54A:bordercolor=black:borderw=8:fontsize=150:"
                    f"x=(w-tw)/2:y=1180:enable='between(t,{t0:.2f},{t0 + 0.7:.2f})'")
    # end card: last 3 s
    e0 = max(d - 3.0, 0)
    card += [
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.55:t=fill:enable='gte(t,{e0:.2f})'",
        f"drawtext=fontfile='{FONT_B}':text='FULL VIDEO':fontcolor=0xFFD54A:fontsize=120:x=(w-tw)/2:y=640:enable='gte(t,{e0:.2f})'",
        f"drawtext=fontfile='{FONT_B}':text='ON THE CHANNEL':fontcolor=white:fontsize=84:x=(w-tw)/2:y=780:enable='gte(t,{e0:.2f})'",
        f"drawtext=fontfile='{FONT_B}':text='{esc(TITLE)}':fontcolor=white:fontsize=46:box=1:boxcolor=black@0.5:boxborderw=18:x=(w-tw)/2:y=920:enable='gte(t,{e0:.2f})'",
    ]
    f.append(chain + ",".join(card) + ",format=yuv420p[v]")
    return ";".join(f)


results = []
for n, (name, s, e) in enumerate(ranked_sections()[: args.max]):
    win = best_window(s, e, args.len)
    if not win:
        say(f"skip {name}: not enough speech")
        continue
    score, r0, r1, ws = win
    f0, f1 = raw_to_final(r0) - 0.15, raw_to_final(r1) + 0.35
    d = round(f1 - f0, 3)
    rank, label, cat, series, info = entry_info(name)
    if info.get("needs_new_code"):
        say(f"HOLD {name}: research says it needs a new code, no short until the user gives one")
        continue
    pops, last = [], -9
    for w in ws:
        t = raw_to_final(w["s"])
        clean = re.sub(r"[^a-z]", "", w["w"].lower())
        if clean in POPWORDS and t - f0 - last >= 2.5 and len(pops) < 6:
            pops.append((t - f0, clean))
            last = t - f0
    # menu spans inside this window (ui.json is raw time) -> short time, padded 0.3 s each side
    wide = []
    for u in UI:
        a, b = raw_to_final(u["s"]), raw_to_final(u["e"])
        if a is None or b is None or b < f0 or a > f1:
            continue
        wide.append((max(a - f0 - 0.3, 0), min(b - f0 + 0.3, d)))
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    nn = f"{int(rank[1:]):02d}" if rank.startswith("#") else f"hm{n}"
    out = OUT / f"{nn}-{slug}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{f0:.3f}", "-t", f"{d:.3f}", "-i", str(VIDEO),
           "-filter_complex", build_filter(d, rank, label, cat, series, pops, wide), "-map", "[v]", "-map", "0:a",
           *NVENC, "-rc", "vbr", "-cq", "19", "-b:v", "0", "-r", "60", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    say(f"{name}: final {f0:.1f}-{f1:.1f} ({d:.1f} s, score {score:.1f}, {len(pops)} pops, {len(wide)} menu spans) -> {out.name}")
    run(cmd)
    code_line = ""
    if info.get("placeholder"):
        code_line = f"Code expired at upload time; try {info['placeholder']['name']} instead (link below)."
    hub = info.get("listings") or ""
    text = "\n".join([
        f"TITLE: {label} is the {rank} Bedrock realm you need to try #shorts" if rank.startswith("#") else f"TITLE: {label}: honorable mention Bedrock realm #shorts",
        f"DESCRIPTION:",
        f"Full video: {TITLE} (on the channel, link in the pinned comment)",
        (f"{label} page: {hub}" if hub else ""),
        code_line,
        "#minecraft #minecraftbedrock #realms #shorts",
        "",
        "UPLOAD NOTES: In YouTube Studio set this Short's 'Related video' to the full upload, and pin a comment with the full video link.",
    ])
    out.with_suffix(".txt").write_text(text, encoding="utf-8")
    results.append({"section": name, "file": str(out), "final_start": round(f0, 2), "final_end": round(f1, 2), "duration": d,
                    "score": round(score, 2), "pops": pops, "words": " ".join(w["w"] for w in ws)})

(OUT / "shorts.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
say(f"{len(results)} shorts -> {OUT}")
