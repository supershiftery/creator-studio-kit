"""Shared recipe helpers: the Python to use, tool paths, output->source time mapping, note parsing."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import media  # noqa: E402
import store  # noqa: E402

TOOLS = Path(r"{{KIT}}/tools")
PHONE_TOOLS = TOOLS / "phone_edit"
REVIEW_SCRIPTS = Path(r"{{KIT}}/review_pipeline\scripts")
CHECK_VIDEO = Path(r"{{KIT}}/assets\Tools\check_video.py")
TARGETS_CHECK = Path(__file__).resolve().parent.parent / "tools" / "targets_check.py"
CLAUDE_REVIEW = Path(__file__).resolve().parent.parent / "tools" / "claude_review.py"
GAMING = Path(__file__).resolve().parents[1] / "gaming"


def python():
    return store.settings().get("python") or sys.executable


def exists(p):
    return bool(p) and os.path.exists(str(p))


def status_of(outputs, inputs=()):
    outs = [str(o) for o in outputs if o]
    if not outs:
        return "n/a"
    if not all(os.path.exists(o) for o in outs):
        return "missing"
    t = min(os.path.getmtime(o) for o in outs)
    if any(exists(i) and os.path.getmtime(str(i)) > t + 0.5 for i in inputs):
        return "stale"
    return "done"


def keep_ranges(cuts_path):
    d = store.read_json(cuts_path)
    if d is None:
        return None
    if isinstance(d, dict):
        return [tuple(x[:2]) for x in (d.get("keep") or d.get("kept") or [])]
    return [tuple(x) for x in d]


def output_to_source(keep, t, offset=0.0):
    """edited-timeline time -> raw recording time through the kept ranges (offset = intro length in front)."""
    t = t - offset
    if t < 0:
        return None
    acc = 0.0
    for a, b in keep:
        if t <= acc + (b - a):
            return round(a + (t - acc), 3)
        acc += b - a
    return None


def source_to_output(keep, raw, offset=0.0):
    acc = 0.0
    for a, b in keep:
        if raw < a:
            return round(offset + acc, 3)
        if raw <= b:
            return round(offset + acc + raw - a, 3)
        acc += b - a
    return round(offset + acc, 3)


TIME = r"(\d+:\d{2}(?::\d{2})?(?:\.\d+)?|\d+(?:\.\d+)?s?)"


def parse_note(text):
    """Free text note -> {"kind", "t0", "t1", "clip", "text"} (times in the timeline the user watched: the draft).
    Examples:  cut 1:22-1:30 | 1:22 - 1:30 clipped word | protect 2:03-2:10 | keep 2:03-2:10 |
               broll 3:20 6s <clip name> | broll 3:20-3:26 <clip> | section #5 Dragonforge 11:09-15:30 | anything else = text
    """
    t = text.strip()
    low = t.lower()
    rng = re.search(TIME + r"\s*(?:-|–|to)\s*" + TIME, low)
    single = re.search(TIME, low)

    def sec(s):
        return media.parse_t(s.rstrip("s"))

    if low.startswith(("note", "@")):
        n = {"kind": "text", "text": t}
        if rng:
            n["t0"], n["t1"] = sec(rng.group(1)), sec(rng.group(2))
        elif single:
            n["t0"] = sec(single.group(1))
        return n
    if low.startswith(("protect", "keep")) and rng:
        return {"kind": "protect", "t0": sec(rng.group(1)), "t1": sec(rng.group(2)), "text": t}
    if low.startswith(("broll", "b-roll", "b roll")):
        rest = re.sub(r"^(b-?\s?roll)\s*", "", t, flags=re.I)
        # a spoken sentence that happens to open with "B-roll" is a revision for Claude, not a command (jordan 3 2026-10-23:
        # talk notes kept turning into "B-roll at <now>"); a command is the time + a short clip name
        spare = re.sub(TIME + r"\s*(?:-|–|to)\s*" + TIME + "|" + TIME + r"|\b(?:at|for|over|from|seconds?|secs?)\b", " ", rest.lower()).split()
        if len(spare) > 6:
            n = {"kind": "text", "text": t}
            if rng:
                n["t0"], n["t1"] = sec(rng.group(1)), sec(rng.group(2))
            elif single:
                n["t0"] = sec(single.group(1))
            return n
        if rng:
            t0, t1 = sec(rng.group(1)), sec(rng.group(2))
            clip = re.sub(TIME + r"\s*(?:-|–|to)\s*" + TIME, "", rest, count=1, flags=re.I).strip()
        elif single:
            t0 = sec(single.group(1))
            clip = re.sub(TIME, "", rest, count=1, flags=re.I)
            dm = re.search(r"(\d+(?:\.\d+)?)\s*s(?:ec)?\b", clip, re.I)
            t1 = t0 + (float(dm.group(1)) if dm else 5.0)
            if dm:
                clip = clip[:dm.start()] + clip[dm.end():]
            clip = clip.strip()
        else:
            return {"kind": "text", "text": t}
        return {"kind": "broll", "t0": t0, "t1": t1, "clip": clip, "text": t}
    if low.startswith("section") and rng:
        name = re.sub(r"^section\s*", "", t, flags=re.I)
        name = re.sub(TIME + r"\s*(?:-|–|to)\s*" + TIME, "", name, flags=re.I).strip(" :-")
        return {"kind": "section", "t0": sec(rng.group(1)), "t1": sec(rng.group(2)), "name": name, "text": t}
    # a bare command ("cut 1:22-1:30", "1:22-1:30") goes straight to the cutter; anything said in words is a revision
    # for Claude, who reads the whole sentence (user, 2026-10-21: "2:00-2:05 there's a clip that doesn't belong" is a note, not a cut)
    wordy = len(re.sub(TIME + r"\s*(?:-|–|to)\s*" + TIME + "|" + TIME + r"|\bcut\b", " ", low).split()) > 3
    if wordy and (rng or single):
        n = {"kind": "text", "text": t}
        if rng:
            n["t0"], n["t1"] = sec(rng.group(1)), sec(rng.group(2))
        else:
            n["t0"] = sec(single.group(1))
        return n
    if rng:
        return {"kind": "cut", "t0": sec(rng.group(1)), "t1": sec(rng.group(2)), "text": t}
    if low.startswith("cut") and single:
        t0 = sec(single.group(1))
        return {"kind": "cut", "t0": t0, "t1": t0 + 1.0, "text": t}
    return {"kind": "text", "text": t}


def resolve_note(note, keep, offset):
    """Attach raw (recording) times to a parsed note using the timeline of the draft the user watched."""
    if note.get("kind") == "text" and "t0" in note and keep is not None:   # a note for Claude: keep its recording times too
        r0 = output_to_source(keep, note["t0"], offset)
        r1 = output_to_source(keep, note.get("t1", note["t0"] + 1), offset)
        if r0 is not None:
            note["raw0"], note["raw1"] = r0, r1 if r1 is not None else r0 + 1
        return note
    if note.get("kind") in ("cut", "protect", "broll", "section") and keep is not None:
        r0 = output_to_source(keep, note["t0"], offset)
        r1 = output_to_source(keep, note["t1"], offset)
        if r0 is not None and r1 is not None and (r0 < 0 or r1 < 0):   # negative = an inserted clip (gaming body.py)
            note["unresolved"] = "inside an inserted clip, not the recording"
        elif r0 is not None and r1 is not None and r1 > r0:
            note["raw0"], note["raw1"] = r0, r1
        else:
            note["unresolved"] = "outside the edited footage (inside the intro?)"
    return note


def extra_cuts_from_notes(notes):
    """notes -> take_cuts.py extra_cuts.json entries (raw times). Protects are zero-length cuts with a protect range.
    Applied ("done") notes stay in: extra_cuts.json is rewritten from the notes every time, so skipping them un-did every
    earlier cut on the next build (the Shein 1:39 / 2:00 / 4:13 notes came back that way). Removing a note removes its cut."""
    out = []
    for n in notes:
        if "raw0" not in n:
            continue
        if n["kind"] == "cut":
            out.append({"s": n["raw0"], "e": n["raw1"], "why": "user note: " + n["text"]})
        elif n["kind"] == "protect":
            out.append({"s": n["raw0"], "e": n["raw0"], "why": "user note: " + n["text"], "protect": [n["raw0"], n["raw1"]]})
    return out


def draft_offset(doc, intro_path):
    """Seconds of intro in front of the body in the draft the user watched."""
    if intro_path and os.path.exists(intro_path):
        info = media.probe(intro_path)
        return info["duration"] if info else 0.0
    return 0.0


def latest(paths):
    paths = [p for p in paths if exists(p)]
    return max(paths, key=lambda p: os.path.getmtime(str(p))) if paths else None


def read_report(path, n=40):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[:n]
    except OSError:
        return []


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def claude_qc_step(doc, video):
    """Claude reviews the QC flags of the render just checked (tools/claude_review.py): fine / REAL + a suggested note.
    No flags = no call; never fails the build. Off per project with settings.claude = False (CLAUDE_BRAIN=0)."""
    return {"id": "claude_qc", "label": "AI reviews the QC flags (Claude)", "cmd": [python(), "-X", "utf8", str(CLAUDE_REVIEW), doc["id"], str(video)],
            "cwd": doc["path"], "force": True}


def targets_step(doc, video=None):
    """playbook targets (tools/targets.json, measured from the approved finals): intro length, time to first content,
    section lengths, visual pace, loudness, kept %, talk speed -> "<video> targets.md". Flags only, never fails (user 2026-10-22)."""
    cmd = [python(), "-X", "utf8", str(TARGETS_CHECK), doc["path"]] + ([str(video)] if video else [])
    # light (2026-10-24): it reads numbers off the finished file, no GPU; as the last step after the AI QC review it kept
    # the render slot for up to 5 min while the next video waited
    return {"id": "targets", "label": "Targets check (vs the approved finals)", "cmd": cmd, "cwd": doc["path"], "force": True,
            "light": True}
