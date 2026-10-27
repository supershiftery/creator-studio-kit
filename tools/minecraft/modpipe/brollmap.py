"""Find Director add-on B-roll in a recording and say what every shot shows.

Shared by the B-roll watcher / `mc.py broll` (modpipe/stills.py) and {{STUDIO_NAME}}'s gaming step (gaming/broll.py).
No package imports, so Studio can load it by path.

What the Director puts on screen (scripts/camera.js + main.js):
- MAGENTA flash (~0.35 s) when a reel starts and when it ends.
- Right after the start flash, a 3-digit REEL CODE: three short flashes, each one of
  red/green/blue/yellow/cyan/white = digits 0-5 (base 6, most significant first). code = the reel's "code" in reels.js
  (permanent, from modpipe/reel_codes.json via director.write_reels), 0 = a custom
  sequence (/replay <mob>, /replayitem, seed tours). Recordings made before the code existed have no code.
- A fade to BLACK before every shot: that's where shots are split.
- A WHITE flash in the black when a shot couldn't be staged and was skipped, so the shot numbers stay in line.

Detection looks at the GAME area only: a side-by-side OBS capture (webcam left, game right) would dilute the flash
with the webcam. Every sampled frame is a 16x9 grid; a frame is a colour when nearly all its cells are that colour.
"""
import json
import re
import subprocess
from pathlib import Path

FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
REELS_JS = Path(r"{{KIT}}/tools/minecraft\Tools\Director add-on BP\scripts\reels.js")
SAMPLE_FPS = 10
W, H = 16, 9
DIGITS = ["red", "green", "blue", "yellow", "cyan", "white"]
EDGE_TRIM = 0.35        # drop the fade-out / fade-in darkening at both ends of a shot
MIN_SHOT = 2.0

RECIPES = {             # Director recipe -> words for clip names and the map
    "attackShow": "attack", "withPlayer": "with you", "faceIn": "face close-up", "closeOrbit": "close orbit",
    "lowHero": "low hero", "topDown": "top-down", "lineup": "line-up", "highOrbit": "high orbit",
    "craneDown": "crane down", "spiralUp": "spiral up", "arcPush": "arc push", "flyby": "flyby",
    "itemRow": "item row", "blockRow": "block row", "armorStand": "armor stand",
}


def reel_code(key: str) -> int:
    """Fallback only: reels now carry a permanent "code" from modpipe/reel_codes.json (this hash collided)."""
    h = 0
    for ch in key:
        h = (h * 31 + ord(ch)) % 215
    return h + 1


def load_reels(path: Path = REELS_JS) -> dict:
    try:
        src = path.read_text(encoding="utf-8")
        return json.loads(src[src.index("export const REELS = ") + len("export const REELS = "):].rstrip().rstrip(";"))
    except (OSError, ValueError):
        return {}


def game_crop(video) -> str | None:
    """ffmpeg crop for the game area: the right half of a 32:9 side-by-side capture, else the whole frame."""
    p = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in p.stdout.strip().split(",")[:2])
    except ValueError:
        return None
    return f"{w // 2}:{h}:{w // 2}:0" if w >= 3 * h else None


def _kind(px: bytes) -> str:
    n = W * H
    counts = {}
    for i in range(n):
        r, g, b = px[3 * i], px[3 * i + 1], px[3 * i + 2]
        if max(r, g, b) < 24:
            k = "black"
        elif min(r, g, b) > 200:
            k = "white"
        else:
            hi = [c > 170 for c in (r, g, b)]
            lo = [c < 90 for c in (r, g, b)]
            k = {(1, 0, 0): "red", (0, 1, 0): "green", (0, 0, 1): "blue", (1, 1, 0): "yellow",
                 (0, 1, 1): "cyan", (1, 0, 1): "magenta"}.get(tuple(int(x) for x in hi)) \
                if all(hi[j] or lo[j] for j in range(3)) else None
        if k:
            counts[k] = counts.get(k, 0) + 1
    if not counts:
        return "game"
    k, c = max(counts.items(), key=lambda kv: kv[1])
    return k if c >= (0.95 if k == "black" else 0.85) * n else "game"


def frames(video, crop=None) -> list[str]:
    """Kind of every sampled frame (index / SAMPLE_FPS = seconds)."""
    vf = (f"crop={crop}," if crop else "") + f"fps={SAMPLE_FPS},scale={W}:{H}:flags=area,format=rgb24"
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", str(video), "-vf", vf, "-an", "-f", "rawvideo", "-"],
                       capture_output=True)
    size = W * H * 3
    return [_kind(p.stdout[i * size:(i + 1) * size]) for i in range(len(p.stdout) // size)]


def _runs(kinds: list[str]) -> list[tuple[str, float, float]]:
    """(kind, start, end) stretches of the same kind."""
    out, start = [], 0
    for i in range(1, len(kinds) + 1):
        if i == len(kinds) or kinds[i] != kinds[start]:
            out.append((kinds[start], start / SAMPLE_FPS, i / SAMPLE_FPS))
            start = i
    return out


def _read_code(runs, i) -> tuple[int | None, float, int]:
    """Digits right after the start flash at runs[i]: (code, end time, next run index), code None if absent."""
    digits, j, t_end = [], i + 1, runs[i][2]
    while j < len(runs) and runs[j][1] - runs[i][2] < 3.0 and len(digits) < 3:
        k, a, b = runs[j]
        if k in DIGITS and b - a >= 0.15:
            digits.append(DIGITS.index(k))
            t_end = b
        elif k in ("black", "magenta"):
            break
        j += 1
    if len(digits) == 3:
        return digits[0] * 36 + digits[1] * 6 + digits[2], t_end, j
    return None, runs[i][2], i + 1


def _luma(video, crop, t0, dur) -> tuple[float, list[float]]:
    """(fps, mean brightness 0-255 of every frame) of the game area from t0, at the recording's own frame rate."""
    vf = (f"crop={crop}," if crop else "") + f"scale={W}:{H}:flags=area,format=gray"
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-ss", f"{max(0.0, t0):.3f}", "-t", f"{dur:.3f}", "-i", str(video),
                        "-vf", vf, "-an", "-f", "rawvideo", "-"], capture_output=True)
    n = W * H
    vals = [sum(p.stdout[i * n:(i + 1) * n]) / n for i in range(len(p.stdout) // n)]
    return (len(vals) / dur if dur > 0 else 0.0), vals


def refine_edges(video, crop, a: float, b: float) -> tuple[float, float]:
    """Exact shot edges with no black or pink left in: the 10 fps scan only knows a shot lies between a and b, and the
    Director's fades take 0.4 s each way. At full frame rate, the shot starts on the first frame back to (nearly) full
    brightness after the fade from black and ends on the last one before the fade out. Falls back to EDGE_TRIM."""
    def edge(t0, dur, from_end):
        fps, v = _luma(video, crop, t0, dur)
        if fps <= 0 or len(v) < 6:
            return None
        seq = v[::-1] if from_end else v
        ref = sorted(seq[-max(3, len(seq) // 4):])[len(seq[-max(3, len(seq) // 4):]) // 2]   # steady picture past the fade
        if ref < 30:
            return None                                    # a genuinely dark shot: can't tell the fade from the picture
        i = next((i for i, x in enumerate(seq) if x >= 0.94 * ref), None)
        if i is None:
            return None
        i += 2                                             # two frames of margin: the last fade frames are near-full but tinted
        return t0 + (dur - i / fps if from_end else i / fps)
    lead, look = 0.2, 1.3
    s = edge(a - lead, look, False)
    e = edge(b - look + lead, look, True)
    s = round(s if s is not None else a + EDGE_TRIM, 3)
    e = round(e if e is not None else b - EDGE_TRIM, 3)
    if e - s < MIN_SHOT:                                   # refining ate the shot: keep the safe fixed trim
        s, e = round(a + EDGE_TRIM, 3), round(b - EDGE_TRIM, 3)
    return s, e


def find_reels(video, crop="auto") -> list[dict]:
    """Every Director reel in the recording: {"start", "end", "code", "shots": [{"n", "start", "end"}]}.
    n = the shot's place in the reel's plan (1-based), counting skipped shots."""
    if crop == "auto":
        crop = game_crop(video)
    runs = _runs(frames(video, crop))
    reels, i, cur = [], 0, None
    while i < len(runs):
        k, a, b = runs[i]
        if k == "magenta" and b - a >= 0.15:
            code, t_code, nxt = _read_code(runs, i)
            if cur is not None and code is None:          # closing flash
                cur["end"] = a
                reels.append(cur)
                cur, i = None, i + 1
                continue
            if cur is not None:                           # a new start without an end (reel stopped off-camera)
                cur["end"] = a
                reels.append(cur)
            cur = {"start": a, "code": code, "body": t_code, "shots": [], "_n": 0, "_open": None}
            i = nxt
            continue
        if cur is not None and a >= cur["body"]:
            if k == "game":
                if b - a >= MIN_SHOT + 2 * EDGE_TRIM and runs[i - 1][0] == "black":
                    cur["_n"] += 1
                    s0, s1 = refine_edges(video, crop, a, b)
                    cur["shots"].append({"n": cur["_n"], "start": s0, "end": s1})
            elif k == "white" and b - a >= 0.15 and cur["shots"] is not None and runs[i - 1][0] == "black":
                cur["_n"] += 1                            # skipped shot
        i += 1
    if cur is not None:
        cur["end"] = len(runs) and runs[-1][2]
        reels.append(cur)
    for r in reels:
        r.pop("_n"), r.pop("_open"), r.pop("body")
        r["start"], r["end"] = round(r["start"], 2), round(r["end"], 2)
    return [r for r in reels if r["shots"]]


def _title(s: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_ ]+", s) if w)


def describe(reels: list[dict], catalog: dict | None = None) -> list[dict]:
    """Add what each shot shows. Reel = its code; old recordings without a code: the one reel whose plan has exactly
    that many shots (else unknown). Adds reel/reel_title/mapped ("code" | "shot count" | "") and per shot
    recipe/shot/subject/subject_id."""
    catalog = load_reels() if catalog is None else catalog
    by_code = {v.get("code") or reel_code(k): k for k, v in catalog.items()}   # reels.js "code" (registry), old hash otherwise
    for r in reels:
        key, how = None, ""
        if r.get("code"):
            key, how = by_code.get(r["code"]), "code"
        elif r.get("code") is None:
            last = max(s["n"] for s in r["shots"])
            fits = [k for k, v in catalog.items() if len(v.get("shots", [])) == last]
            if len(fits) == 1:
                key, how = fits[0], "shot count"
        reel = catalog.get(key) if key else None
        r.update(reel=key or ("custom" if r.get("code") == 0 else ""), mapped=how if reel else "",
                 reel_title=(reel or {}).get("title") or ("Custom B-roll" if r.get("code") == 0 else "B-roll"))
        plan = (reel or {}).get("shots", [])
        for s in r["shots"]:
            step = plan[s["n"] - 1] if 0 < s["n"] <= len(plan) else {}
            subj_key = step.get("subject")
            subj = (reel or {}).get("subjects", {}).get(subj_key, {}) if subj_key else {}
            recipe = step.get("recipe", "")
            s.update(recipe=recipe, shot=RECIPES.get(recipe, re.sub(r"(?<!^)([A-Z])", r" \1", recipe).lower()),
                     subject=subj.get("name") or (_title(subj_key) if subj_key else ""), subject_id=subj.get("id", ""))
    return reels


def clip_name(stem: str, reel: dict, shot: dict) -> str:
    """'<recording> - CobbleDrock 01 Charizard (attack)'; unmapped: '<recording> - reel1 shot01'."""
    if not reel.get("mapped"):
        return f"{stem} - {reel.get('reel_title', 'B-roll')} shot{shot['n']:02d}"
    what = " ".join(x for x in (shot.get("subject"), f"({shot['shot']})" if shot.get("shot") else "") if x)
    title = re.sub(r"\s*-\s*\d+ shots$", "", reel["reel_title"])   # "Pokemon (CobbleDrock) - 20 shots" -> "Pokemon (CobbleDrock)"
    return re.sub(r'[<>:"/\\|?*]', "", f"{stem} - {title} {shot['n']:02d} {what}".strip())


def write_map(rows: list[dict], path: Path) -> None:
    """B-roll map.csv: one row per clip (opens in Excel)."""
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["clip", "reel", "shot_no", "subject", "shot", "seconds", "recording", "from", "to", "mapped"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def map_rows(recording, reels: list[dict], clips: dict) -> list[dict]:
    """Rows for write_map / the sidecars. clips = {(reel index, shot n): clip path}."""
    rows = []
    for ri, r in enumerate(reels):
        for s in r["shots"]:
            clip = clips.get((ri, s["n"]))
            if not clip:
                continue
            rows.append({"clip": str(clip), "reel": r["reel_title"], "reel_key": r["reel"], "shot_no": s["n"],
                         "subject": s.get("subject", ""), "subject_id": s.get("subject_id", ""), "shot": s.get("shot", ""),
                         "seconds": round(s["end"] - s["start"], 1), "recording": str(recording),
                         "from": s["start"], "to": s["end"], "mapped": r["mapped"]})
    return rows


if __name__ == "__main__":   # python brollmap.py <recording>  -> print what's in it
    import sys
    for rec in sys.argv[1:]:
        found = describe(find_reels(rec))
        print(f"{Path(rec).name}: {len(found)} reel(s)")
        for r in found:
            print(f"  {r['start']:.1f}-{r['end']:.1f}s  {r['reel_title']} (code {r['code']}, mapped by {r['mapped'] or 'nothing'})")
            for s in r["shots"]:
                print(f"    {s['n']:2d}  {s['start']:7.1f}-{s['end']:7.1f}  {s.get('subject', '')} {s.get('shot', '')}")
