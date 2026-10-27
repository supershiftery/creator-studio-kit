"""Product review recipe: wraps the product-review-edit skill's edit_review.py.
Project layout: raw/camera.mp4 (or raw/edit.xml from Gling), optional raw/screen.mp4, raw/broll/*, raw/music.txt, raw/extra_cuts.json
Output: output/final.mp4, output/preview_540p.mp4, output/report.md, output/broll_requests.md
"""
from pathlib import Path

from recipes import common as C

LABEL = "Product review"


def paths(doc):
    p = Path(doc["path"])
    raw = p / "raw"
    return {
        "raw": raw, "work": p / "work", "output": p / "output",
        "camera": raw / "camera.mp4", "xml": next(iter(sorted(raw.glob("*.xml"))), None) if raw.is_dir() else None,
        "screen": raw / "screen.mp4", "broll": raw / "broll",
        "extra": raw / "extra_cuts.json",
        "final": p / "output" / "final.mp4", "preview": p / "output" / "preview_540p.mp4",
        "final_intro": p / "output" / "final_intro.mp4", "preview_intro": p / "output" / "preview_intro_540p.mp4",
        "report": p / "output" / "report.md", "broll_req": p / "output" / "broll_requests.md",
        "cuts": p / "work" / "cuts.json", "transcript": p / "work" / "transcript.json",
        "log": p / "output" / "studio.log",
    }


def ingest(doc, slot, src):
    P = paths(doc)
    src = Path(src)
    if slot == "main":
        if src.suffix.lower() == ".xml":
            dest = C.store.copy_into(src, P["raw"], "edit.xml")
        else:
            dest = C.store.copy_into(src, P["raw"], "camera.mp4")
        doc["source"] = str(dest)
        doc["checklist"]["footage"] = True
    elif slot == "screen":
        dest = C.store.copy_into(src, P["raw"], "screen.mp4")
    elif slot == "broll" and _is_recording_part(src, P["camera"]):
        # a second two-camera recording (OBS continuation) is part of the video, not B-roll: edit_review.py (parts.py)
        # joins raw/parts/ after the main take (lv trainer 2026-10-23: it was cut in as raw split-screen "B-roll")
        dest = C.store.copy_into(src, P["raw"] / "parts")
        doc["slots"]["parts"] = sorted(set(doc["slots"].get("parts", []) + [str(dest)]))
    elif slot == "broll":
        dest = C.store.copy_into(src, P["broll"])
        doc["slots"]["broll"] = sorted(set(doc["slots"].get("broll", []) + [str(dest)]))
    elif slot in ("intro", "intro_vo"):
        # a VO becomes a motion-graphics intro, a finished MP4 is used as is; joined in front by tools\review_intro.py
        dest = C.store.copy_into(src, Path(doc["path"]) / "intro")
        doc["slots"][slot] = str(dest)
        doc["checklist"]["intro"] = True
    else:
        return None
    return str(dest)


def _wh(path):
    import json, subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        s = d["streams"][0]
        return s["width"], s["height"], float(d["format"]["duration"])
    except (ValueError, KeyError, IndexError):
        return None


def _is_recording_part(src, camera):
    """Same side-by-side size as the main recording (aspect >= 2.5) and >= 30 s = a part of the recording."""
    a = _wh(src)
    if not a or a[0] / a[1] < 2.5 or a[2] < 30:
        return False
    b = _wh(camera) if Path(camera).exists() else None
    return not b or (a[0], a[1]) == (b[0], b[1])


def steps(doc):
    P = paths(doc)
    src = P["xml"] or P["camera"]
    return [
        {"id": "source", "label": "Source (Gling XML or camera.mp4)", "status": "done" if (P["xml"] or P["camera"].exists()) else "missing"},
        {"id": "transcribe", "label": "Transcript", "status": C.status_of([P["transcript"]], [src])},
        {"id": "cuts", "label": "Cuts + sections + mic swap", "status": C.status_of([P["cuts"]], [P["transcript"], P["extra"]])},
        {"id": "final", "label": "Edit + render final.mp4", "status": C.status_of([P["final"]], [P["cuts"]])},
        {"id": "preview", "label": "540p preview", "status": C.status_of([P["preview"]], [P["final"]])},
    ]


# edit_review.py prints almost nothing (40+ silent minutes on sp5der 2026-10-23, bar frozen at 49%), so its phases are
# marked by the files it writes, in order: (log pattern or None, label, stage, first-guess seconds per footage minute,
# file under the project that appears when this phase STARTS). jobs.py learns the real phase times.
PHASES = [(None, "Transcript", "Transcript", 2.0, None),
          (None, "Camera angles (analysis)", "Camera angles (analysis)", 3.0, "work/transcript.json"),
          (r"^take review:", "Cuts + take review", "Cuts + take review", 1.0, "work/analysis.json"),
          (None, "Word + mid-sentence guards", "Word + mid-sentence guards", 0.8, "work/cuts.json"),
          (None, "Angles, zooms, B-roll", "Angles, zooms, B-roll", 0.5, "work/timeline.json"),
          (None, "Audio loudness pass", "Audio loudness pass", 0.4, "work/graph_audio.txt"),
          (None, "Rendering final.mp4", "Rendering final.mp4", 2.5, "work/graph_final.txt"),
          (None, "540p preview", "540p preview", 0.4, "output/preview_*p.mp4"),
          (None, "Report", "Report", 0.05, "output/report.md")]


def job_steps(doc, action, force=False):
    P = paths(doc)
    py = C.python()
    proj = doc["path"]
    script = str(C.REVIEW_SCRIPTS / "edit_review.py")
    if action in ("draft", "final", "all"):
        cmd = [py, "-X", "utf8", script, proj] + (["--fresh"] if force else [])
        return [{"id": "edit", "label": "edit_review.py (the review pipeline)", "cmd": cmd, "cwd": proj, "force": True,
                 "phases": PHASES, "stages": [ph[2] for ph in PHASES]},
                # share_gpu: the next video in line starts while this intro is planned, checked and rendered (jobs.SHARE)
                # intro lock (2026-10-24): a built intro is only re-made when this build may touch it (doc["intro_rebuild"],
                # set by start_build from a batch with intro notes / {"intro": "rebuild"}) or on a fresh build
                {"id": "intro", "label": "Intro from your VO + join", "cmd": [py, "-X", "utf8", str(C.store.APP / "tools" / "review_intro.py"), proj],
                 "cwd": proj, "force": True, "share_gpu": True,
                 "env": {"STUDIO_INTRO_LOCK": "1", "STUDIO_INTRO_REBUILD": "1" if (force or doc.get("intro_rebuild")) else "0"}},
                {"id": "check", "label": "QC check (10 fps)", "cmd": [py, "-X", "utf8", str(C.CHECK_VIDEO), "check", str(P["final"]), "--sheets", "flags", "--no-words"], "cwd": proj, "force": True},
                C.claude_qc_step(doc, P["final"]), C.targets_step(doc),
                # what the draft SAYS (2026-10-24, dhgate watchb spread: a draft full of retakes went out as ready): retakes
                # left in / stranded scraps / clipped ending; clear retakes are cut and ONE rebuild starts; anything else fails
                # this step (exit 2), so the draft is never shown as ready with them
                {"id": "audit", "label": "Draft audit (repeats, scraps, clipped end)", "cmd": [py, "-X", "utf8",
                 r"{{KIT}}/tools\draft_audit.py", proj], "cwd": proj, "force": True}]
    if action == "intro":
        # intro-only revision (user 2026-10-23: "if the rest of the video is perfectly fine, why are we still revising the
        # whole thing?"): output/final.mp4 is kept as it is, the intro is rendered again (one self-check fix round, not two),
        # joined back on and only the intro is QC-checked. The main edit (~5 min) and the whole-video checks are skipped.
        clip = Path(proj) / "intro" / "build" / "renders" / "intro.mp4"
        return [{"id": "intro", "label": "Intro only: render + join (main edit kept)", "cmd": [py, "-X", "utf8", str(C.store.APP / "tools" / "review_intro.py"), proj],
                 "cwd": proj, "force": True, "env": {"STUDIO_INTRO_ONLY": "1"}},
                {"id": "check", "label": "QC check of the intro (10 fps)", "cmd": [py, "-X", "utf8", str(C.CHECK_VIDEO), "check", str(clip), "--sheets", "flags", "--no-words"], "cwd": proj, "force": True},
                C.claude_qc_step(doc, clip)]
    if action == "shorts":
        # styled product-review Shorts from the approved final (user 2026-10-23, references unoakaoneway_ / cedaz_ / credcal):
        # tools/review_shorts.py -> <project>/Shorts/NN <name>.mp4 (listed in the Shorts tab)
        return [{"id": "shorts", "label": "Review Shorts (3, styled)", "cmd": [py, "-X", "utf8", str(C.store.APP / "tools" / "review_shorts.py"), proj, "--n",
                 str((doc.get("settings") or {}).get("review_shorts_n") or 3)], "cwd": proj, "force": True}]
    if action == "broll_plan":
        return [{"id": "broll_plan", "label": "B-roll shot list", "cmd": [py, "-X", "utf8", script, proj, "--broll-plan"], "cwd": proj, "force": True}]
    if action == "check":
        return [{"id": "check", "label": "QC check (10 fps)", "cmd": [py, "-X", "utf8", str(C.CHECK_VIDEO), "check", str(P["final"]), "--sheets", "flags", "--no-words"], "cwd": proj, "force": True},
                C.claude_qc_step(doc, P["final"])]
    raise ValueError(action)


def _keep(P):
    """The kept ranges of the draft as rendered: work/timeline.json (after word_guard moved edges off mid-word), else cuts.json."""
    tl = C.store.read_json(P["work"] / "timeline.json", None)
    # "rendered" = kept + each cutaway that plays with its own sound as a negative range (s25 ultra 2026-10-23)
    if isinstance(tl, dict) and tl.get("rendered"):
        return [tuple(k) for k in tl["rendered"]]
    return [tuple(k) for k in tl["kept"]] if isinstance(tl, dict) and tl.get("kept") else C.keep_ranges(P["cuts"])


def _offset(doc):
    """Seconds of intro in front of the body in the draft the user watches (2026-10-22: offset 0 put every note on a
    joined draft 19 s late — "hey guys" at 0:22 resolved to the box talk)."""
    P = paths(doc)
    if not (P["preview_intro"].exists() and (not P["final"].exists() or P["preview_intro"].stat().st_mtime >= P["final"].stat().st_mtime)):
        return 0.0
    slot = doc.get("slots", {}).get("intro") or ""
    intro = Path(slot) if slot.lower().endswith((".mp4", ".mov")) else Path(doc["path"]) / "intro" / "build" / "renders" / "intro.mp4"
    return C.draft_offset(doc, str(intro))


def apply_notes(doc):
    """cut notes -> raw/extra_cuts.json as [[a,b],...] source ranges (the skill's sanctioned way to remove a section)."""
    P = paths(doc)
    keep, off = _keep(P), _offset(doc)
    for n in doc["notes"]:
        if "raw0" not in n and "unresolved" not in n:
            C.resolve_note(n, keep, off)
    # The notes are the truth for what Studio wrote (2026-10-24, transcript cutter): extra_cuts.json used to be merged
    # forever, so un-cutting a sentence in the editor never brought it back. Ranges Studio wrote last time are listed in
    # raw/studio_extra.json and replaced with the current notes; ranges written by hand or by the revision AI stay.
    # Protect notes go to raw/extra_keeps.json (edit_review.py puts those back). Applied notes stay in, like phone.
    live = [n for n in doc["notes"] if "raw0" in n and not n.get("off") and n.get("status") != "failed"]
    cuts = {(round(n["raw0"], 3), round(n["raw1"], 3)) for n in live if n["kind"] == "cut"}
    keeps = {(round(n["raw0"], 3), round(n["raw1"], 3)) for n in live if n["kind"] == "protect"}
    side_path = P["extra"].parent / "studio_extra.json"
    side = C.store.read_json(side_path, None) or {"cuts": [], "keeps": []}   # first run: what is already there stays
    for key, path, now in (("cuts", P["extra"], cuts), ("keeps", P["extra"].parent / "extra_keeps.json", keeps)):
        old = {tuple(x) for x in (C.store.read_json(path, []) or []) if isinstance(x, list)}
        new = (old - {tuple(x) for x in side.get(key, [])}) | now
        if new != old:
            C.write_json(path, sorted([list(x) for x in new]))
        side[key] = sorted([list(x) for x in now])
    C.write_json(side_path, side)
    return len(cuts)


def outputs(doc):
    P = paths(doc)
    out = []
    fresh = lambda a, b: a.exists() and (not b.exists() or a.stat().st_mtime >= b.stat().st_mtime)   # the intro version, unless the edit is newer
    prev = P["preview_intro"] if fresh(P["preview_intro"], P["final"]) else P["preview"]
    fin = P["final_intro"] if fresh(P["final_intro"], P["final"]) else P["final"]
    if prev.exists():
        out.append({"kind": "draft", "file": str(prev)})
    if fin.exists():
        out.append({"kind": "final", "file": str(fin)})
    return out


def timeline_info(doc):
    P = paths(doc)
    return {"keep": _keep(P), "offset": _offset(doc), "report": C.read_report(P["report"]), "broll_requests": C.read_report(P["broll_req"], 80)}
