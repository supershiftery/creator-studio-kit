"""Trim only (New Project option, any video type; user 2026-10-22): transcript -> the cutter (take_cuts rules + take review)
-> the recording with only the kept pieces (tools/trim_render.py). No intro, layout, graphics, music or privacy pass.
Reuses the gaming steps (prep, transcribe, cuts), which work on any recording; their work dir is <project>/Edit/studio.
recipes.get() routes a project here when settings.trim_only is set."""
import re
from pathlib import Path

from recipes import common as C

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def on(doc):
    # screen recordings (no cam, plain 16:9: user 2026-10-22, friend's "apple home lg" got the phone layout's cam box and
    # half-screen crop) take this path too: trim + full screen + music bed, see tools/trim_render.py
    st = doc.get("settings") or {}
    # gaming without a cam stays a gaming edit (full-screen game, no corner cam: settings.no_cam / source.json has_cam)
    return bool(st.get("trim_only") or (st.get("screen") and doc.get("type") not in ("gaming", "haul")))


def paths(doc):
    p = Path(doc["path"])
    w = p / "Edit" / "studio"
    title = re.sub(r'[<>:"/\\|?*]', "", doc.get("title") or p.name).strip()
    return {"work": w, "source_json": w / "source.json", "mic": w / "mic16k.wav", "words": w / "words.json", "transcript": w / "words.json",
            "cuts": w / "cuts" / "cuts.json", "cuts_md": w / "cuts" / "cuts.md", "timeline": w / "timeline-trim.json",
            "trimmed": p / (f"{title} - EDIT.mp4" if (doc.get("settings") or {}).get("screen") else f"{title} - TRIMMED.mp4"),
            "graphics": w / "graphics" / "graphics.json", "log": w / "studio.log"}


def graphics_on(doc):
    """Motion graphics (user 2026-10-22): screen-recording edits only for now; tools/motion_graphics.py.
    Only the cut list makes it stale (not studio.json), so notes don't re-run the web planner; the Motion graphics button forces it."""
    st = doc.get("settings") or {}
    return bool(st.get("screen") and (st.get("graphics") or {}).get("on"))


def privacy_on(doc):
    """Privacy for screen-recording edits (user 2026-10-23, a friend's Chime sign-up showed his bank + routing numbers,
    address, phone and emails): cut first, scan only the kept parts (tools/pii_scan.py --ranges, cached per frame), blur
    them inside the render (trim_render.py -> pii_blur.py), then scan the finished edit (tools/pii_check.py)."""
    st = doc.get("settings") or {}
    return bool(st.get("screen") and st.get("privacy") is not False)


def steps(doc):
    P = paths(doc)
    src = doc.get("source") or ""
    sj = Path(doc["path"]) / "studio.json"
    return [
        {"id": "prep", "label": "Probe recording, pick the mic track", "status": C.status_of([P["source_json"], P["mic"]], [src])},
        {"id": "transcribe", "label": "Transcript (faster-whisper)", "status": C.status_of([P["words"]], [P["mic"]])},
        {"id": "cuts", "label": "Cutter (take_cuts rules + take review)", "status": C.status_of([P["cuts"]], [P["words"], sj])},
    ] + ([{"id": "graphics", "label": "Motion graphics (" + ((doc.get("settings") or {}).get("graphics") or {}).get("type", "article") + ")",
            "status": C.status_of([P["graphics"]], [P["cuts"]])}] if graphics_on(doc) else []) + [
        {"id": "trim", "label": "TRIMMED render (no layout, no music)", "status": C.status_of([P["trimmed"]], [P["cuts"], sj] + ([P["graphics"]] if graphics_on(doc) else []))},
    ]


def _py(doc, sid, label, script, outputs, inputs, force, cwd=C.GAMING):
    return {"id": sid, "label": label, "cmd": [C.python(), "-X", "utf8", str(Path(cwd) / script), doc["path"]], "cwd": str(cwd),
            "outputs": [str(o) for o in outputs], "inputs": [str(i) for i in inputs if i], "force": force}


def job_steps(doc, action, force=False):
    P = paths(doc)
    src = doc.get("source") or ""
    sj = Path(doc["path"]) / "studio.json"
    base = [
        _py(doc, "prep", "Probe + mic track", "prep.py", [P["source_json"], P["mic"]], [src], False),
        _py(doc, "transcribe", "Transcript", "transcribe.py", [P["words"]], [P["mic"]], False),
        _py(doc, "cuts", "Cutter", "cuts.py", [P["cuts"]], [P["words"], sj], force),
    ]
    if action in ("prep", "transcribe", "cuts"):
        return base[:["prep", "transcribe", "cuts"].index(action) + 1]
    if action == "graphics" and graphics_on(doc):
        return base + [_py(doc, "graphics", "Motion graphics", "motion_graphics.py", [P["graphics"]], [P["cuts"], sj], True, TOOLS_DIR)]
    if action in ("draft", "final", "all"):
        if graphics_on(doc):
            base = base + [_py(doc, "graphics", "Motion graphics", "motion_graphics.py", [P["graphics"]], [P["cuts"]], force, TOOLS_DIR)]
        pii = P["work"] / "pii.json"
        if privacy_on(doc):   # only the kept parts; frames scanned before are remembered in pii.json (light: no GPU)
            base = base + [{"id": "privacy", "label": "Privacy scan (kept parts)", "light": True, "force": True, "cwd": str(TOOLS_DIR),
                            "cmd": [C.python(), "-X", "utf8", str(TOOLS_DIR / "pii_scan.py"), src, str(pii), "--ranges", str(P["cuts"]), "--fps", "2"]}]
        return base + [_py(doc, "trim", "Screen edit render (full screen + music)" if (doc.get("settings") or {}).get("screen") else "TRIMMED render", "trim_render.py", [P["trimmed"]], [P["cuts"], sj] + ([P["graphics"]] if graphics_on(doc) else []) + ([pii] if privacy_on(doc) else []), force, TOOLS_DIR),
                       # QC before "Draft ready": the user watches what the notice points at
                       {"id": "check", "label": "QC check (10 fps)", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(P["trimmed"]),
                        "--sheets", "flags", "--no-words"], "cwd": doc["path"], "force": True}] + \
            ([{"id": "privacy_check", "label": "Privacy check of the edit", "light": True, "force": True, "no_retry": True, "cwd": str(TOOLS_DIR),
               "cmd": [C.python(), "-X", "utf8", str(TOOLS_DIR / "pii_check.py"), doc["path"]]}] if privacy_on(doc) else [])
    if action == "check":
        return [{"id": "check", "label": "QC check", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(P["trimmed"]), "--sheets", "flags",
                 "--no-words"], "cwd": doc["path"], "force": True}]
    raise ValueError(f"{action} isn't available on a trim-only project")


def apply_notes(doc):
    """cut / protect notes (times in the TRIMMED video) -> raw times; cuts.py applies them on the next build"""
    tl = C.store.read_json(paths(doc)["timeline"]) or {}
    keep = [tuple(x) for x in tl.get("keep") or []] or C.keep_ranges(paths(doc)["cuts"]) or []
    sp = float(tl.get("speed") or 1.0)
    n = 0
    for note in doc["notes"]:
        if "raw0" not in note and "unresolved" not in note:
            seen = {k: note[k] for k in ("t0", "t1") if k in note}
            if sp != 1:   # the user watched a sped-up video: its clock runs sp times faster than the kept recording
                note.update({k: v * sp for k, v in seen.items()})
            C.resolve_note(note, keep, 0.0)
            note.update(seen)                     # the note keeps the times the user typed
            n += 1
    return n


def outputs(doc):
    P = paths(doc)
    return [{"kind": "trimmed", "file": str(P["trimmed"])}] if P["trimmed"].exists() else []


def timeline_info(doc):
    P = paths(doc)
    tl = C.store.read_json(P["timeline"]) or {}
    return {"keep": tl.get("keep") or C.keep_ranges(P["cuts"]) or [], "offset": 0.0, "sections": [], "timeline": [], "music": {}, "cards": {},
            "cuts_md": C.read_report(P["cuts_md"], 400), "chapters": "", "source": C.store.read_json(P["source_json"], {}),
            "has_words": P["words"].exists()}
