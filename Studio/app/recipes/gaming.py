"""Gaming / Minecraft recipe: the generalized Top 5 Realms pipeline in app/gaming/*.py.
Project home: {{GAMING_ROOT}}\\<title>\\ (the mc.py content folder); work in Edit\\studio\\; outputs in Edit\\.
The recording stays where OBS put it ({{RECORDINGS}}): it's referenced, not copied (60+ min files)."""
import os
from pathlib import Path

from recipes import common as C

LABEL = "Gaming / Minecraft"


def paths(doc):
    p = Path(doc["path"])
    w = p / "Edit" / "studio"
    title = C.store.safe_name(doc.get("title") or p.name)
    return {
        "work": w, "edit": p / "Edit",
        "source_json": w / "source.json", "mic": w / "mic16k.wav", "words": w / "words.json",
        "sections": w / "sections.json", "extra": w / "extra_cuts.json", "cuts": w / "cuts" / "cuts.json", "cuts_md": w / "cuts" / "cuts.md",
        "ui": w / "ui.json",
        "body_draft": w / "body-draft.mp4", "body_final": w / "body-final.mp4",
        "draft": p / "Edit" / f"{title} draft.mp4", "final": p / "Edit" / f"{title} final.mp4",
        "timeline_draft": w / "timeline-draft.json", "timeline_final": w / "timeline-final.json",
        "chapters": w / "chapters.txt", "log": w / "studio.log",
        "broll": p / "B-roll", "intro_dir": p / "Intro", "graphics": p / "Graphics", "thumb_dir": p / "Thumbnail",
        "description": Path(doc["slots"].get("description") or (p / "youtube-description.txt")),
    }


def ingest(doc, slot, src):
    P = paths(doc)
    src = Path(src)
    if slot == "main":
        doc["source"] = str(src)            # referenced in place
        doc["checklist"]["footage"] = True
        dest = src
    elif slot == "intro":
        dest = C.store.copy_into(src, P["intro_dir"])
        doc["slots"]["intro"] = str(dest)
        doc["checklist"]["intro"] = True
    elif slot == "intro_vo":
        dest = C.store.copy_into(src, P["intro_dir"], "intro-vo" + src.suffix.lower())
        doc["slots"]["intro_vo"] = str(dest)
    elif slot == "broll":
        dest = C.store.copy_into(src, P["broll"])
        doc["slots"]["broll"] = sorted(set(doc["slots"].get("broll", []) + [str(dest)]))
    elif slot == "card":
        dest = C.store.copy_into(src, P["graphics"] / "cards")
    else:
        return None
    return str(dest)


def steps(doc):
    P = paths(doc)
    src = doc.get("source") or ""
    S = doc.get("settings", {})
    st = [
        {"id": "prep", "label": "Probe recording, pick mic + game tracks", "status": C.status_of([P["source_json"], P["mic"]], [src])},
        {"id": "broll", "label": "B-roll (pink-flash reels)", "status": C.status_of([P["work"] / "broll.json"], [src])},
        {"id": "transcribe", "label": "Transcript (faster-whisper)", "status": C.status_of([P["words"]], [P["mic"]])},
        {"id": "sections", "label": "Sections (intro, #N…, HM, outro)", "status": C.status_of([P["sections"]], [P["words"]])},
        {"id": "cuts", "label": "Cutter (take_cuts rules + take review) + UI panels", "status": C.status_of([P["cuts"], P["ui"]], [P["words"], P["sections"], Path(doc["path"]) / "studio.json"])},
        {"id": "body", "label": "Body: corner cam, B-roll reel, zooms", "status": C.status_of([P["body_draft"]], [P["cuts"], P["ui"]])},
        {"id": "assemble", "label": "Assemble: intro, wipes, cards, music → DRAFT", "status": C.status_of([P["draft"]], [P["body_draft"], doc["slots"].get("intro") or ""])},
        {"id": "chapters", "label": "YouTube chapters → description", "status": C.status_of([P["chapters"]], [P["timeline_draft"]])},
        {"id": "final", "label": "FINAL 1080p60 render", "status": C.status_of([P["final"]], [P["cuts"]])},
    ]
    return st


def _py_step(doc, sid, label, script, args, outputs, inputs, force):
    P = paths(doc)
    return {"id": sid, "label": label, "cmd": [C.python(), "-X", "utf8", str(C.GAMING / script), doc["path"]] + args,
            "cwd": str(C.GAMING), "outputs": [str(o) for o in outputs], "inputs": [str(i) for i in inputs if i], "force": force}


def job_steps(doc, action, force=False):
    P = paths(doc)
    src = doc.get("source") or ""
    sj = Path(doc["path"]) / "studio.json"
    mode = "final" if action == "final" else "draft"
    body = P["body_final"] if mode == "final" else P["body_draft"]
    out = P["final"] if mode == "final" else P["draft"]
    tl = P["timeline_final"] if mode == "final" else P["timeline_draft"]
    base = [
        _py_step(doc, "prep", "Probe + mic track", "prep.py", [], [P["source_json"], P["mic"]], [src], force and action == "prep"),
        # the B-roll scan decodes the whole recording on the CPU while transcription runs on the GPU: in parallel (2026-10-22)
        dict(_py_step(doc, "broll", "B-roll from the Director's pink flashes", "broll.py", [], [P["work"] / "broll.json"], [src, sj], force and action == "broll"),
             background=action != "broll"),
        _py_step(doc, "transcribe", "Transcript", "transcribe.py", [], [P["words"]], [P["mic"]], force and action == "transcribe"),
        _py_step(doc, "sections", "Sections", "sections.py", ["--redo"] if action == "sections" else [], [P["sections"]], [P["words"]], action == "sections"),
        dict(_py_step(doc, "cuts", "Cutter + UI panels", "cuts.py", [], [P["cuts"], P["ui"]], [P["words"], P["sections"], sj, P["work"] / "broll.json"], force),
             wait_for=["broll"]),
    ]
    if action in ("prep", "broll", "transcribe", "sections", "cuts"):
        idx = ["prep", "broll", "transcribe", "sections", "cuts"].index(action)
        return base[:idx + 1]
    if action in ("draft", "final", "all"):
        intro = doc["slots"].get("intro") or ""
        broll_inputs = [c for c in doc["slots"].get("broll", [])]
        steps_ = base + [
            _py_step(doc, "body", f"Body ({mode})", "body.py", [mode], [body], [P["cuts"], P["ui"], sj, P["work"] / "broll.json"] + broll_inputs, force),
            _py_step(doc, "assemble", f"Assemble ({mode})", "assemble.py", [mode], [out, tl], [body, intro, sj], force),
            _py_step(doc, "chapters", "Chapters", "chapters.py", [mode], [], [], True),
        ]
        protect = "0.02,0.02,0.29,0.46"   # the corner cam box as fractions of the frame
        steps_.append({"id": "check", "label": "QC check (10 fps, flags only)", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(out), "--sheets", "flags", "--no-words", "--protect", protect],
                       "cwd": doc["path"], "force": True})
        steps_.append(C.claude_qc_step(doc, out))
        steps_.append(C.targets_step(doc, out))
        return steps_
    if action == "chapters_only":
        mode = "final" if P["timeline_final"].exists() and not P["timeline_draft"].exists() else "draft"
        return [_py_step(doc, "chapters", "Chapters", "chapters.py", [mode], [], [], True)]
    if action == "check":
        tgt = P["final"] if P["final"].exists() else P["draft"]
        return [{"id": "check", "label": "QC check", "cmd": [C.python(), "-X", "utf8", str(C.CHECK_VIDEO), "check", str(tgt), "--sheets", "flags", "--no-words"], "cwd": doc["path"], "force": True},
                C.claude_qc_step(doc, tgt)]
    raise ValueError(action)


def apply_notes(doc):
    """Resolve note times against the last draft (intro + body) so cuts.py can read raw times from studio.json."""
    P = paths(doc)
    tl = C.store.read_json(P["timeline_draft"]) or C.store.read_json(P["timeline_final"])
    keep = [tuple(x) for x in tl["keep"]] if tl else C.keep_ranges(P["cuts"])
    offset = tl["intro"] if tl else 0.0
    n = 0
    for note in doc["notes"]:
        if "raw0" not in note and "unresolved" not in note:
            C.resolve_note(note, keep, offset)
            n += 1
    # section notes rewrite sections.json directly
    secs = C.store.read_json(P["sections"], []) or []
    changed = False
    for note in doc["notes"]:
        if note.get("kind") == "section" and "raw0" in note and not note.get("done"):
            name = note.get("name") or f"section {len(secs) + 1}"
            secs = [s for s in secs if s[0] != name] + [[name, note["raw0"], note["raw1"]]]
            note["done"] = True
            changed = True
    if changed:
        secs.sort(key=lambda s: s[1])
        C.write_json(P["sections"], secs)
    return n


def outputs(doc):
    P = paths(doc)
    return [{"kind": k, "file": str(p)} for k, p in (("draft", P["draft"]), ("final", P["final"])) if p.exists()]


def timeline_info(doc):
    P = paths(doc)
    tl = C.store.read_json(P["timeline_draft"]) or {}
    return {"keep": tl.get("keep") or C.keep_ranges(P["cuts"]), "offset": tl.get("intro", 0.0), "sections": C.store.read_json(P["sections"], []),
            "timeline": tl.get("sections", []), "music": tl.get("music", {}), "cards": tl.get("cards", {}),
            "cuts_md": C.read_report(P["cuts_md"], 400), "chapters": C.read_report(P["chapters"], 30),
            "source": C.store.read_json(P["source_json"], {}), "has_words": P["words"].exists()}
