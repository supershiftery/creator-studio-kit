"""His own footage of products he has already reviewed, found across ALL his recordings (ultimate dhgate free reselling
spreadsheet 2026-10-23, intro 0:19-0:32: "everything from spider hoodies to cologne to AirPod Maxes ... we have a spider video
inside of our Google Drive, you can just pull the spider hoodie from there, me showing it off ... we have a cologne video ...
AirPod Max videos ... the AirPod 4s, that's another video we did ... so we need a logic for this ... make sure that it matches
up to the item").

    find_clips(name, exclude=(), n=2) -> [{"src", "t", "crop", "tag", "for", "own_page"}]

1. Library: every video under {{DRIVE_RAW}} (his raw uploads, one folder per video) + {{PROJECTS_ROOT}}\\*\\raw\\camera.mp4
   (local copies seek faster), indexed by folder + file name (cached a day in _state/product_library.json).
2. Match: every key word of the named thing must be in the path ("spider hoodies" -> sp5der|spider + hoodie; "AirPod Maxes"
   -> airpod + max; "AirPod 4's" -> airpod + 4, and "max"/"pro" must NOT be there). Single-product folders first, short B-roll
   files first, the current project never.
3. Moments: 8 times across the video, each half of a side-by-side recording on its own, one contact sheet -> the pipeline
   brain (vision) names the cells where the product itself is shown (held up, worn, on the desk / turntable), not a person
   talking, not a screen. Cached per file + product in _state/product_moments.json.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "_state"
ROOTS = [Path(r"{{DRIVE_RAW}}")]
LOCAL = Path(r"{{PROJECTS_ROOT}}")
EXTS = {".mp4", ".mov", ".mkv", ".m4v"}
ALIASES = {"spider": ["sp5der", "spider"], "sp5der": ["sp5der", "spider"], "airpod": ["airpod", "air pod", "airpods"],
           "airpods": ["airpod", "air pod"], "max": ["max"], "maxes": ["max"], "cologne": ["cologne", "coologne", "clogne",
           "coogne", "bacurat", "baccarat", "creed", "fragrance", "perfume"], "colognes": ["cologne", "coologne", "clogne", "coogne"],
           "hoodie": ["hoodie", "hoodies", "sp5der", "spider"], "hoodies": ["hoodie", "sp5der", "spider"], "4": ["4"], "4s": ["4"],
           "4's": ["4"],
           # watch brands (dhgate watchb spread 2026-10-24: "Rolexes, APs, and even Pateks" found nothing, "rolexes" was
           # stemmed to "rolexe" and AP had no spelling, so one Cartier clip played 4 times: "we even have videos of those
           # in our Google Drive")
           "rolex": ["rolex", "datejust", "daytona", "submariner"], "rolexes": ["rolex", "datejust", "daytona", "submariner"],
           "ap": ["audemars", "royal oak", "piguet", "ap"], "aps": ["audemars", "royal oak", "piguet", "ap"],
           "audemars": ["audemars", "royal oak", "ap"], "patek": ["patek", "nautilus"], "pateks": ["patek", "nautilus"],
           "philippe": ["patek", "philippe", "nautilus"], "watches": ["watch"], "watch": ["watch"]}
EXCLUDE_IF = {"4": ["max", "pro"]}
OPTIONAL = {"watch", "philippe", "piguet"}   # key words that never decide the product alone (with a brand)    # "AirPod 4" never matches an AirPod Max / Pro video


def _log(m):
    print(f"product_library: {m}", file=sys.stderr, flush=True)


def index(max_age=86400):
    """[(path, duration_unknown)] of every video in the roots + local project cameras; cached."""
    STATE.mkdir(exist_ok=True)
    f = STATE / "product_library.json"
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        return json.loads(f.read_text(encoding="utf-8"))
    files = []
    for root in ROOTS:
        if root.exists():
            for dp, dn, fn in os.walk(root):
                if dp[len(str(root)):].count(os.sep) > 3:
                    continue
                files += [os.path.join(dp, x) for x in fn if os.path.splitext(x)[1].lower() in EXTS]
    for d in LOCAL.iterdir() if LOCAL.exists() else []:
        cam = d / "raw" / "camera.mp4"
        if cam.exists():
            files.append(str(cam))
    f.write_text(json.dumps(files, indent=0), encoding="utf-8")
    return files


def _keys(name):
    toks = [t for t in re.findall(r"[a-z0-9']+", name.lower()) if t not in ("the", "a", "and", "of", "even", "to")]
    # plain plurals go by canon() ("rolexes" -> "rolex", "watches" -> "watch"); rstrip("s") made "rolexe"
    return [ALIASES.get(t, [canon(t) if len(t) > 3 else t]) for t in toks], [x for t in toks for x in EXCLUDE_IF.get(t.rstrip("'s"), [])]


def candidates(name, exclude=()):
    keys, bad = _keys(name)
    out = []
    for p in index():
        if any(str(e).lower() in p.lower() for e in exclude if e):
            continue
        low = os.path.splitext(p.lower().replace("_", " "))[0]          # never the "4" of ".mp4"
        rel = low.split("raw videos")[-1] if "raw videos" in low else low.split("ai editing")[-1]
        hit = lambda a: re.search(rf"\b{re.escape(a)}\b", rel) if len(a) <= 2 else a in rel
        # a brand + a generic word ("Patek Philippe watch"): the generic word is optional, the folder is "dhgate patek"
        need = [alts for alts in keys if alts[0] not in OPTIONAL] or keys
        if all(any(hit(a) for a in alts) for alts in need) and not any(re.search(rf"\b{b}", rel) for b in bad):
            # rank: b-roll / short clips first, then the review's main file
            score = (0 if "b roll" in rel or "broll" in rel else 1, len(rel))
            out.append((score, p))
    return [p for _, p in sorted(out)]


def _probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", p], capture_output=True, text=True, timeout=120)
    j = json.loads(r.stdout or "{}")
    s = (j.get("streams") or [{}])[0]
    return s.get("width", 0), s.get("height", 0), float(j.get("format", {}).get("duration", 0) or 0)


def canon(name):
    """one spelling per product: lower case, no possessive/plural s ("AirPod Maxes" -> "airpod max", "airpod 4's" -> "airpod 4")."""
    toks = re.findall(r"[a-z0-9]+", re.sub(r"'s\b", "", name.lower()))
    return " ".join(t[:-2] if t.endswith("es") and len(t) > 4 and t[:-2].endswith("x") else t[:-1] if t.endswith("s") and len(t) > 3 else t
                    for t in toks)


def moments(path, name, n_times=8, cells=None):
    """[(t, crop)] where the product is shown, from the vision check (cached). cells: [(t, "left"|"right"|None)] to look
    at instead of the evenly spaced ones (named_broll: the product-camera runs of the video's own recording)."""
    STATE.mkdir(exist_ok=True)
    cf = STATE / "product_moments.json"
    cache = json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else {}
    key = f"{path}|{canon(name)}|nogear" + ("|cells:" + ",".join(f"{t}{c}" for t, c in cells) if cells else "")   # "airpod 4's" and "airpod 4" are one product: one look, one answer
    if key in cache:
        return [tuple(x) for x in cache[key]]
    try:
        w, h, dur = _probe(path)
    except Exception as e:
        _log(f"{path}: probe failed ({e})")
        return []
    if dur < 4:
        return []
    if not cells:
        halves = ["left", "right"] if w and h and w / h >= 2.5 else [None]
        times = [round(dur * (0.1 + 0.8 * k / max(1, n_times - 1)), 1) for k in range(n_times)] if dur > 20 else \
            [round(dur * f, 1) for f in (0.2, 0.5, 0.8)]
        cells = [(t, c) for t in times for c in halves]
    sys.path.insert(0, r"{{KIT}}/tools")
    import claude_brain
    tmp = Path(tempfile.mkdtemp(prefix="prodlib_"))
    found = []
    for s0 in range(0, len(cells), 12):
        group = cells[s0:s0 + 12]
        items = [(path, t, str(i + 1), {"left": "crop=iw/2:ih:0:0", "right": "crop=iw/2:ih:iw/2:0"}.get(c, ""))
                 for i, (t, c) in enumerate(group)]
        sheet = tmp / f"s{s0}.png"
        try:
            claude_brain.contact_sheet(items, str(sheet), cols=4, w=400)
        except Exception as e:
            _log(f"{path}: sheet failed ({e})")
            continue
        prompt = (f"The attached image is a grid of numbered frames from a product review video. List the numbers of the frames "
                  f"where a {name} is clearly shown as the subject: held up to the camera, worn, unboxed, or sitting on a desk or "
                  f"turntable in close-up. NOT frames that are mostly a person talking to the camera (even while wearing it: a muted "
                  f"talking shot looks like lip-sync), NOT computer screens or "
                  f"web pages, NOT empty rooms, NOT a different product, NOT frames where his recording gear shows: a small "
                  f"white action camera / camera on a tripod, clamp or stand in the shot (Best Mon Clear On DHG 2026-10-29: "
                  f"\"you never want to show the white camera there\"). Answer with ONLY JSON like {{\"show\": [2, 5]}}.")
        try:
            j = claude_brain.ask("product_moments", prompt, images=[str(sheet)])
        except Exception:
            j = None
        if isinstance(j, dict):
            for v in j.get("show", []):
                try:
                    found.append(group[int(v) - 1])
                except (ValueError, IndexError, TypeError):
                    pass
    cache[key] = found
    cf.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return found


def find_clips(name, exclude=(), n=2, max_files=2, word=None):
    """Footage items of `name` from his other videos: up to n moments, from different files when possible."""
    out = []
    for p in candidates(name, exclude)[:max_files]:
        for t, c in moments(p, name):
            if len(out) >= n:
                break
            if any(o["src"] == p and abs(o["t"] - t) < 20 for o in out):
                continue
            out.append({"src": p, "t": max(0.0, t - 1.0), "crop": c, "tag": f"product: {name} ({Path(p).parent.name})",
                        "kind": "broll", "for": [word or name.lower()], "own_page": True})
        if len(out) >= n:
            break
    if not out:
        _log(f"no footage of '{name}' found")
    return out


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        print(nm, json.dumps(find_clips(nm), indent=1))
