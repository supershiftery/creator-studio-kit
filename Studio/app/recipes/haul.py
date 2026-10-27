"""Haul recipe (user 2026-10-23): one long phone recording (iPhone .MOV / .mp4, often several clips) showing a bunch of
products, no separate intro VO and no OBS side-by-side.
Steps: normalise (tools/haul_normalise.py: every clip -> 1080p60 SDR H.264 + AAC, stream durations checked, joined into
raw/source.mp4) -> prep / transcribe / cuts (the gaming steps, which work on any recording: take_cuts + take review kind
"haul") -> render (tools/haul_render.py: midstart guard, greeting/outro detection, type beats per section, Doug captions on
the intro only) -> QC check (10 fps) -> AI QC -> targets check.
Project layout: raw/clips/<the phone clips>, raw/clips/norm/ (normalised clips + clips.json), raw/source.mp4,
Edit/studio/ (source.json, words.json, cuts/, haul_structure.json, timeline-haul.json), "<title> - DRAFT.mp4" / "- FINAL.mp4"."""
import re
from pathlib import Path

from recipes import common as C

LABEL = "Haul"
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def paths(doc):
    p = Path(doc["path"])
    w = p / "Edit" / "studio"
    title = re.sub(r'[<>:"/\\|?*]', "", doc.get("title") or p.name).strip()
    return {"raw": p / "raw", "clips": p / "raw" / "clips", "source": p / "raw" / "source.mp4", "norm": p / "raw" / "clips" / "norm" / "clips.json",
            "work": w, "source_json": w / "source.json", "mic": w / "mic16k.wav", "words": w / "words.json", "transcript": w / "words.json",
            "cuts": w / "cuts" / "cuts.json", "cuts_md": w / "cuts" / "cuts.md", "timeline": w / "timeline-haul.json",
            "structure": w / "haul_structure.json",
            "draft": p / f"{title} - DRAFT.mp4", "final": p / f"{title} - FINAL.mp4", "log": w / "studio.log"}


def ingest(doc, slot, src):
    """main = one more phone clip (kept in the order added; joined by the normalise step, never by stream copy: the clips
    can differ in frame rate, size and HDR)"""
    P = paths(doc)
    src = Path(src)
    if slot == "main":
        n = len(doc["slots"].get("clips") or []) + 1
        dest = C.store.copy_into(src, P["clips"], f"{n:02d} {src.name}")
        doc["slots"]["clips"] = (doc["slots"].get("clips") or []) + [str(dest)]
        doc["source"] = str(P["source"])
        doc["checklist"]["footage"] = True
    elif slot == "broll":
        dest = C.store.copy_into(src, P["raw"] / "broll")
        doc["slots"]["broll"] = sorted(set(doc["slots"].get("broll", []) + [str(dest)]))
    else:
        return None
    return str(dest)


def steps(doc):
    P = paths(doc)
    clips = (doc.get("slots") or {}).get("clips") or []
    sj = Path(doc["path"]) / "studio.json"
    return [
        {"id": "normalise", "label": "Normalise clips (1080p60 SDR H.264, stream lengths checked)", "status": C.status_of([P["source"], P["norm"]], clips)},
        {"id": "prep", "label": "Probe recording, pick the mic track", "status": C.status_of([P["source_json"], P["mic"]], [P["source"]])},
        {"id": "transcribe", "label": "Transcript (faster-whisper)", "status": C.status_of([P["words"]], [P["mic"]])},
        {"id": "cuts", "label": "Cutter (take_cuts rules + take review)", "status": C.status_of([P["cuts"]], [P["words"], sj])},
        {"id": "render", "label": "Haul render (intro/outro, type beats, Doug intro captions)", "status": C.status_of([P["draft"]], [P["cuts"], sj])},
    ]


def _py(sid, label, script, proj, outputs, inputs, force, cwd, extra=()):
    return {"id": sid, "label": label, "cmd": [C.python(), "-X", "utf8", str(Path(cwd) / script), proj, *extra], "cwd": str(cwd),
            "outputs": [str(o) for o in outputs], "inputs": [str(i) for i in inputs if i], "force": force}


def job_steps(doc, action, force=False):
    P = paths(doc)
    proj = doc["path"]
    sj = Path(proj) / "studio.json"
    clips = (doc.get("slots") or {}).get("clips") or []
    base = [
        _py("normalise", "Normalise clips (1080p60 SDR, stream lengths checked)", "haul_normalise.py", proj, [P["source"], P["norm"]], clips, False, TOOLS_DIR),
        _py("prep", "Probe + mic track", "prep.py", proj, [P["source_json"], P["mic"]], [P["source"]], False, C.GAMING),
        _py("transcribe", "Transcript", "transcribe.py", proj, [P["words"]], [P["mic"]], False, C.GAMING),
        _py("cuts", "Cutter", "cuts.py", proj, [P["cuts"]], [P["words"], sj], force, C.GAMING),
    ]
    ids = [b["id"] for b in base]
    if action in ids:
        return base[:ids.index(action) + 1]
    if action in ("draft", "final", "all"):
        final = action != "draft"
        vid = P["final"] if final else P["draft"]
        return base + [
            _py("render", "Haul render (FINAL 1080p60)" if final else "Haul render (half-size draft)", "haul_render.py", proj, [vid], [P["cuts"], sj],
                True, TOOLS_DIR, () if final else ("--draft",)),
            {"id": "check", "label": "QC check (10 fps)", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(vid), "--sheets", "flags",
             "--no-words"], "cwd": proj, "force": True},
            C.claude_qc_step(doc, vid), C.targets_step(doc, vid)]
    if action == "check":
        vid = C.latest([P["final"], P["draft"]]) or P["draft"]
        return [{"id": "check", "label": "QC check (10 fps)", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(vid), "--sheets", "flags",
                 "--no-words"], "cwd": proj, "force": True}, C.claude_qc_step(doc, vid)]
    raise ValueError(f"{action} isn't available on a haul project")


def _keep(P):
    tl = C.store.read_json(P["timeline"]) or {}
    return [tuple(x) for x in tl.get("keep") or []] or C.keep_ranges(P["cuts"]) or []


def apply_notes(doc):
    """cut / protect notes (times in the draft) -> raw times; cuts.py applies them on the next build (no intro in front)"""
    keep = _keep(paths(doc))
    n = 0
    for note in doc["notes"]:
        if "raw0" not in note and "unresolved" not in note:
            C.resolve_note(note, keep, 0.0)
            n += 1
    return n


def outputs(doc):
    P = paths(doc)
    out = []
    if P["draft"].exists():
        out.append({"kind": "draft", "file": str(P["draft"])})
    if P["final"].exists():
        out.append({"kind": "final", "file": str(P["final"])})
    return out


def timeline_info(doc):
    P = paths(doc)
    tl = C.store.read_json(P["timeline"]) or {}
    secs = tl.get("sections") or []
    # [name, start, end] in DRAFT time; ends filled from the next start
    full = []
    for i, s in enumerate(secs):
        e = s[2] if s[2] is not None else (secs[i + 1][1] if i + 1 < len(secs) else sum(b - a for a, b in tl.get("keep") or []))
        full.append([s[0], s[1], e])
    return {"keep": _keep(P), "offset": 0.0, "sections": [], "haul_sections": full, "timeline": [], "music": tl.get("music") or [],
            "cards": {}, "cuts_md": C.read_report(P["cuts_md"], 400), "chapters": "", "source": C.store.read_json(P["source_json"], {}),
            "has_words": P["words"].exists(), "intro_end": tl.get("intro_end"), "outro_start": tl.get("outro_start")}
