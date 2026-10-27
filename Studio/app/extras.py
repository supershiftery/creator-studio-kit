"""Extra features: QC report reader, Shorts, vocal scan, code cards, transcript search."""
import os
import re
import sys
from pathlib import Path

import jobs
import media
import store
from recipes import common
from recipes import get as recipe

TOOLS = Path(__file__).resolve().parent / "tools"
SCAN_FILE = store.DATA / "music-scan.json"


def py():
    return store.settings().get("python") or sys.executable


# ---------------------------------------------------------------- QC report (check_video.py output next to the render)
def qc_report(doc):
    outs = recipe(doc["type"]).outputs(doc)
    for rr in reversed(doc.get("renders", [])):
        if os.path.exists(rr["file"]) and rr["file"] not in [o["file"] for o in outs]:
            outs.append({"kind": rr["kind"], "file": rr["file"]})
    reports = []
    for o in outs:
        base = os.path.splitext(o["file"])[0] + "_check"
        rj = Path(base) / "report.json"
        if rj.exists():
            d = store.read_json(rj, {}) or {}
            flags = []
            for f in d.get("flags", []):
                sheet = str(Path(base) / f["sheet"]) if f.get("sheet") else ""
                flags.append({"type": f.get("type"), "t": f.get("t"), "end": f.get("end"), "note": f.get("note", ""), "sheet": sheet if os.path.exists(sheet) else ""})
            reports.append({"kind": o["kind"], "file": o["file"], "when": store.now() if False else __import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").localtime(rj.stat().st_mtime)),
                            "info": d.get("info"), "loudness": d.get("loudness"), "cuts": d.get("cuts"), "cuts_per_min": d.get("cuts_per_min"),
                            "format_issues": d.get("format_issues", []), "flags": flags, "counts": {k: sum(1 for f in flags if f["type"] == k) for k in sorted({f["type"] for f in flags})}})
    return {"reports": reports}


# ---------------------------------------------------------------- Shorts
def shorts_dir(doc):
    return Path(doc["path"]) / "Shorts"


def list_shorts(doc):
    d = shorts_dir(doc)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({"file": str(f), "name": f.name, "size": f.stat().st_size, "duration": media.cached_duration(str(f))})
    return out


def make_short(doc, raw0, raw1, side="center", name=""):
    """Cut [raw0, raw1] (recording seconds) out of the best render as a 9:16 Short."""
    r = recipe(doc["type"])
    info = r.timeline_info(doc)
    keep = info.get("keep") or []
    offset = info.get("offset", 0.0)
    outs = r.outputs(doc)
    src = next((o["file"] for o in reversed(outs) if o["kind"] == "final"), None) or next((o["file"] for o in reversed(outs)), None) or doc.get("source")
    if not src:
        raise ValueError("nothing rendered yet")
    if src == doc.get("source") or not keep:
        t0, t1 = raw0, raw1
    else:
        t0, t1 = common.source_to_output(keep, raw0, offset), common.source_to_output(keep, raw1, offset)
    if t1 - t0 < 1:
        raise ValueError("selection is shorter than a second in the edit (is it cut?)")
    d = shorts_dir(doc)
    d.mkdir(exist_ok=True)
    n = len(list(d.glob("*.mp4"))) + 1
    safe = store.safe_name(name) or f"short-{n:02d}"
    out = d / f"{safe}.mp4"
    step = {"id": "short", "label": f"Short {safe} ({t1 - t0:.0f} s, {side})", "cmd": [py(), "-X", "utf8", str(TOOLS / "short.py"), src, str(out), f"{t0:.3f}", f"{t1:.3f}", side], "force": True}
    job = jobs.Job(f"{doc['title']}: short", doc["id"], [step], kind="tools", minutes=(t1 - t0) / 60)
    jobs.start(job)
    return {"job": job.view(), "file": str(out), "from": src, "t0": round(t0, 2), "t1": round(t1, 2)}


# ---------------------------------------------------------------- music vocal scan
def scan_results():
    return store.read_json(SCAN_FILE, {}) or {}


def scan_music(paths):
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        raise ValueError("no files")
    step = {"id": "scan", "label": f"Vocal scan: {len(paths)} track(s)", "cmd": [py(), "-X", "utf8", str(TOOLS / "vocal_scan.py"), str(SCAN_FILE)] + paths, "force": True}
    job = jobs.Job("Music vocal scan", None, [step], kind="tools", minutes=len(paths))
    jobs.start(job)
    return {"job": job.view()}


# ---------------------------------------------------------------- code cards (gaming)
def render_cards(doc):
    if doc["type"] != "gaming":
        raise ValueError("cards are for gaming projects")
    if jobs.running_for(doc["id"]):
        raise ValueError("a job is already running for this project")
    step = {"id": "cards", "label": "Render code cards (HyperFrames)", "cmd": [py(), "-X", "utf8", str(TOOLS / "cards.py"), doc["path"]], "force": True}
    job = jobs.Job(f"{doc['title']}: cards", doc["id"], [step], kind="tools", minutes=1)
    jobs.start(job)
    return {"job": job.view()}


# ---------------------------------------------------------------- search every transcript
def words_of(doc):
    P = recipe(doc["type"]).paths(doc)
    wp = P.get("transcript") if doc["type"] == "review" else P.get("words")
    words = store.read_json(wp, []) if wp else []
    if isinstance(words, dict):
        words = words.get("words") or []
    return [{"w": w.get("w") or w.get("word", ""), "s": w.get("s", w.get("start", 0)), "e": w.get("e", w.get("end", 0))} for w in words]


def search(q, limit=60):
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"hits": []}
    hits = []
    for doc in store.all_projects():
        words = words_of(doc)
        if not words:
            continue
        toks = [re.sub(r"[^a-z0-9'$%]", "", w["w"].lower()) for w in words]
        seen = set()
        # match with and without spaces ("dragonforge" finds "dragon Forge")
        for sep, needle in ((" ", q), ("", q.replace(" ", ""))):
            text = sep.join(toks)
            starts, pos = [], 0
            for t in toks:
                starts.append(pos)
                pos += len(t) + len(sep)
            for m in re.finditer(re.escape(needle), text):
                i = max(0, min(len(starts) - 1, next((k for k, st in enumerate(starts) if st > m.start()), len(starts)) - 1))
                if (doc["id"], i) in seen:
                    continue
                seen.add((doc["id"], i))
                ctx = " ".join(w["w"] for w in words[max(0, i - 6):i + 10])
                hits.append({"id": doc["id"], "title": doc["title"], "type": doc["type"], "t": words[i]["s"], "context": ctx})
                if len(hits) >= limit:
                    return {"hits": sorted(hits, key=lambda h: (h["title"], h["t"]))}
    return {"hits": sorted(hits, key=lambda h: (h["title"], h["t"]))}
