"""Phone / app tutorial recipe: wraps {{KIT}}/tools\\phone_edit\\pipeline.py (the Uber Eats pipeline).
Project layout (what pipeline.py expects): raw/source.mp4 [+ raw/intro.wav], work/, edit/, output/<name> - DRAFT.mp4 + report.md
Final: build_main.py (full quality) + join.py -> output/<name> - FINAL.mp4
"""
import os
from pathlib import Path

from recipes import common as C

LABEL = "Phone / app tutorial"
# the pipeline's stages (what the progress bar counts) and what pipeline.py prints as it moves along:
# (pattern, label, stage, first-guess seconds per minute of footage; jobs.py replaces the guess with measured times)
STAGES = ["Transcript", "Trim", "Privacy + full-res cut", "Layout", "Graphics", "Intro", "Main video", "Join + privacy sweep + QC"]
PHASES = [(r"is the mic; transcribing", "Transcript (whisper)", "Transcript", 6.5), (r"take_cuts\.py", "Trim: bad takes, retakes, pauses", "Trim", 0.5),
          (r"take_review\.py", "Take review (Claude reads the cut)", "Trim", 1.5), (r"halves\.py", "Which half is cam / website / phone", "Privacy + full-res cut", 11.0),
          (r"privacy\.py.*find", "Privacy: finding the address", "Privacy + full-res cut", 3.0), (r"blank_phone\.py", "Dead phone screens", "Privacy + full-res cut", 1.0),
          (r"render_draft\.py", "Full-res cut", "Privacy + full-res cut", 6.0), (r"privacy\.py.*apply", "Privacy blur", "Privacy + full-res cut", 0.5),
          (r"layout\.py", "Layout: phone PiP / side cam", "Layout", 1.0),
          (r"events\.py", "Graphics plan", "Graphics", 0.2), (r"bridge\.py", "Graphics: phone timing", "Graphics", 0.5), (r"render_all\.py", "Rendering graphics (HyperFrames)", "Graphics", 2.0),
          (r"auto_intro\.py", "Intro from your VO", "Intro", 1.0), (r"hyperframes.*render|hyperframes\.cmd", "Rendering the intro", "Intro", 4.0),
          (r"build_main\.py", "Main video: compose + music", "Main video", 8.0), (r"join\.py", "Joining intro + main", "Join + privacy sweep + QC", 1.0),
          (r"^== privacy sweep", "Privacy sweep", "Join + privacy sweep + QC", 20.0), (r"^== QC check", "QC check", "Join + privacy sweep + QC", 2.0)]


def paths(doc):
    p = Path(doc["path"])
    name = p.name
    return {
        "raw": p / "raw", "work": p / "work", "edit": p / "edit", "output": p / "output",
        "source": p / "raw" / "source.mp4",
        "intro_vo": next(iter(sorted((p / "raw").glob("intro.*"))), None) if (p / "raw").is_dir() else None,
        "intro_mp4": p / "edit" / "intro" / "renders" / "intro.mp4",
        "draft": p / "output" / f"{name} - DRAFT.mp4",
        "final": p / "output" / f"{name} - FINAL.mp4",
        "report": p / "output" / "report.md",
        "cuts": p / "work" / "cuts.json",
        "cuts_md": p / "work" / "cuts.md",
        "extra": p / "work" / "extra_cuts.json",
        "words": p / "work" / "words.json",
        "log": p / "output" / "pipeline.log",
        "broll": p / "raw" / "broll",
        "thumb_dir": p / "thumbnail",
    }


def ingest(doc, slot, src):
    P = paths(doc)
    src = Path(src)
    if slot == "main":
        dest = C.store.copy_into(src, P["raw"], "source.mp4")
        doc["source"] = str(dest)
        doc["checklist"]["footage"] = True
    elif slot == "intro_vo":
        for old in P["raw"].glob("intro.*") if P["raw"].is_dir() else []:
            old.unlink()
        dest = C.store.copy_into(src, P["raw"], "intro" + src.suffix.lower())
        doc["slots"]["intro_vo"] = str(dest)
        doc["slots"]["intro"] = ""
        doc["checklist"]["intro"] = True
    elif slot == "intro":
        dest = C.store.copy_into(src, P["edit"] / "intro" / "renders", "intro.mp4")
        doc["slots"]["intro"] = str(dest)
        doc["checklist"]["intro"] = True
    elif slot == "broll":
        dest = C.store.copy_into(src, P["broll"])
        doc["slots"]["broll"] = sorted(set(doc["slots"].get("broll", []) + [str(dest)]))
    else:
        return None
    return str(dest)


def steps(doc):
    P = paths(doc)
    src = P["source"]
    out = [
        {"id": "transcribe", "label": "Mic track + transcript", "status": C.status_of([P["words"]], [src])},
        {"id": "cuts", "label": "Trim (take_cuts rules)", "status": C.status_of([P["cuts"]], [P["words"], P["extra"]])},
        {"id": "privacy", "label": "Privacy blur + full-res cut", "status": C.status_of([P["edit"] / "cut-full.mp4"], [P["cuts"]])},
        {"id": "layout", "label": "Layout (phone PiP / side cam)", "status": C.status_of([P["edit"] / "layout.json"], [P["cuts"]])},
        {"id": "graphics", "label": "Graphics (wipes, codes, stats)", "status": C.status_of([P["edit"] / "graphics" / "events.json"], [P["cuts"]])},
    ]
    if P["intro_vo"] or doc["slots"].get("intro"):
        out.append({"id": "intro", "label": "Intro (auto, from VO)" if P["intro_vo"] else "Intro (dropped MP4)",
                    "status": C.status_of([P["intro_mp4"]], [P["intro_vo"]] if P["intro_vo"] else [])})
    out.append({"id": "main", "label": "Main video (compose + music)", "status": C.status_of([P["edit"] / "main-draft.mp4"], [P["edit"] / "cut-full.mp4", P["edit"] / "layout.json"])})
    out.append({"id": "draft", "label": "Join + privacy sweep + QC → DRAFT", "status": C.status_of([P["draft"]], [P["edit"] / "main-draft.mp4", P["intro_mp4"]])})
    out.append({"id": "final", "label": "FINAL render (full quality)", "status": C.status_of([P["final"]], [P["draft"]])})
    return out


def job_steps(doc, action, force=False):
    P = paths(doc)
    py = C.python()
    proj = doc["path"]
    has_intro = bool(P["intro_vo"])
    phases = [ph for ph in PHASES if has_intro or ph[2] != "Intro"]
    stages = [s for s in STAGES if has_intro or s != "Intro"]
    if action in ("draft", "all"):
        # {"intro": "rebuild"} / intro notes reach the phone pipeline too (Uber codes october 2026-10-25: only the review
        # recipe passed it, so a phone intro fixed in the shared tools was reused as it was)
        return [{"id": "pipeline", "label": "phone_edit pipeline (resumes where it left off)", "cmd": [py, "-X", "utf8", str(C.PHONE_TOOLS / "pipeline.py"), proj],
                 "cwd": proj, "outputs": [], "inputs": [], "force": True, "phases": phases, "stages": stages,
                 "env": {"STUDIO_INTRO_REBUILD": "1" if (force or doc.get("intro_rebuild")) else "0"}},
                C.claude_qc_step(doc, P["draft"]), C.targets_step(doc, P["draft"]),
                # listens at every cut of the main edit (2026-10-25, Uber october: 3 cut-join notes); real problems go to
                # the revision AI through server.send_audit before he watches
                {"id": "audit", "label": "Draft audit (words cut off or doubled at a cut)", "cmd": [py, "-X", "utf8",
                 r"{{KIT}}/tools\draft_audit.py", proj], "cwd": proj, "force": True}]
    if action == "final":
        steps_ = []
        if not P["draft"].exists():
            steps_.append({"id": "pipeline", "label": "phone_edit pipeline first", "cmd": [py, "-X", "utf8", str(C.PHONE_TOOLS / "pipeline.py"), proj], "cwd": proj, "force": True,
                           "phases": phases, "stages": stages})
        steps_.append({"id": "main_full", "label": "Main video at full quality", "cmd": [py, "-X", "utf8", str(P["edit"] / "build_main.py")], "cwd": str(P["edit"]),
                       "outputs": [P["edit"] / "main.mp4"], "inputs": [P["edit"] / "cut-full.mp4", P["edit"] / "layout.json", P["edit"] / "graphics" / "events.json"], "force": force})
        if P["intro_vo"] or doc["slots"].get("intro"):
            steps_.append({"id": "join", "label": "Intro + main → FINAL", "cmd": [py, "-X", "utf8", str(C.PHONE_TOOLS / "join.py"), str(P["intro_mp4"]), str(P["edit"] / "main.mp4"), str(P["final"]), "--cq", "17"],
                           "cwd": proj, "outputs": [P["final"]], "inputs": [P["edit"] / "main.mp4", P["intro_mp4"]], "force": force})
        else:
            steps_.append({"id": "copy", "label": "FINAL", "cmd": [py, "-c", f"import shutil;shutil.copy(r'{P['edit'] / 'main.mp4'}', r'{P['final']}')"],
                           "outputs": [P["final"]], "inputs": [P["edit"] / "main.mp4"], "force": force})
        steps_.append({"id": "check", "label": "QC check (10 fps)", "cmd": [py, "-X", "utf8", str(C.CHECK_VIDEO), "check", str(P["final"]), "--sheets", "flags", "--no-words"],
                       "cwd": proj, "force": True})
        steps_.append(C.claude_qc_step(doc, P["final"]))
        steps_.append(C.targets_step(doc, P["final"]))
        return steps_
    if action == "revise":   # the user's plain-language draft notes -> exact cuts (revise.py, Opus) -> resumed rebuild
        return [{"id": "revise", "label": "Turning your notes into cuts (Opus 5.5)", "cmd": [py, "-X", "utf8", str(C.PHONE_TOOLS / "revise.py"), proj],
                 "cwd": proj, "force": True},
                {"id": "pipeline", "label": "phone_edit pipeline (rebuilds what the new cuts change)", "cmd": [py, "-X", "utf8", str(C.PHONE_TOOLS / "pipeline.py"), proj],
                 "cwd": proj, "outputs": [], "inputs": [], "force": True, "phases": phases, "stages": stages}]
    if action == "check":
        tgt = P["final"] if P["final"].exists() else P["draft"]
        return [{"id": "check", "label": "QC check (10 fps)", "cmd": [py, "-X", "utf8", str(C.CHECK_VIDEO), "check", str(tgt), "--sheets", "flags", "--no-words"], "cwd": proj, "force": True},
                C.claude_qc_step(doc, tgt)]
    raise ValueError(action)


def apply_notes(doc):
    """notes -> work/extra_cuts.json (source times). pipeline.py re-trims when the file is newer than cuts.json."""
    P = paths(doc)
    keep = C.keep_ranges(P["cuts"])
    offset = C.draft_offset(doc, P["intro_mp4"] if (P["intro_vo"] or doc["slots"].get("intro")) else None)
    for n in doc["notes"]:
        if "raw0" not in n and "unresolved" not in n:
            C.resolve_note(n, keep, offset)
    extra = C.extra_cuts_from_notes(doc["notes"])
    old = C.store.read_json(P["extra"], [])
    kept_old = [e for e in (old or []) if not str(e.get("why", "")).startswith("user note: ")]
    # only when the notes changed: rewriting the same list made every draft re-trim and re-run the take review (a fresh
    # Claude pass that can choose differently each time; dhgate coupons 2026-10-22 got back a "for ... next code" scrap)
    if (old or []) != kept_old + extra:
        C.write_json(P["extra"], kept_old + extra)
    return len(extra)


def outputs(doc):
    P = paths(doc)
    out = []
    if P["output"].is_dir():   # earlier revisions (DRAFT v1, v2 ...) first, so the current draft stays the latest
        for f in sorted(P["output"].glob("* - DRAFT v*.mp4"), key=lambda x: x.stat().st_mtime):
            out.append({"kind": "draft", "file": str(f)})
    for kind, p in (("draft", P["draft"]), ("final", P["final"])):
        if p.exists():
            out.append({"kind": kind, "file": str(p)})
    return out


def timeline_info(doc):
    P = paths(doc)
    keep = C.keep_ranges(P["cuts"])
    return {"keep": keep, "offset": C.draft_offset(doc, P["intro_mp4"]) if (P["intro_vo"] or doc["slots"].get("intro")) else 0.0,
            "report": C.read_report(P["report"]), "cuts_md": C.read_report(P["cuts_md"], 400)}
