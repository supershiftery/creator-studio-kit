"""An APPROVED edit is the answer key for its recording (user 2026-10-26, after two laptop test builds of the approved
dhgae prada glasses came back with five bad takes it had cut: "we already cut this out before ... somehow you did it
again", and so the assistant is never handed a rebuild that quietly lost an approved fix).

When a video is approved (Studio "approved" tick or "Done: test video"), its final cut list (work/timeline.json "kept",
recording seconds) is stored under a fingerprint of the recording (raw/camera.mp4 and raw/camera_original.mp4, by
content, not name). Any later build of the same footage, under any project name:
  1. starts from those cuts (edit_review.py treats them like his own extra_keeps / extra_cuts; his notes on the new
     project still win), and
  2. is compared with them before it renders: footage the approved edit cut that plays again, or footage it kept that
     is now cut, STOPS the build (raw/config.json trimmer.allow_off_approved = true lets it through, marked).
The regression suite (--cuts-only) is not seeded: it has to test the pipeline itself.

    python approved_cuts.py build              # register every approved review project not on file yet
    python approved_cuts.py approve "<dir>"    # (re)register one project now (Studio calls this on approval)
    python approved_cuts.py check "<dir>"      # which approved edit this project's recording matches, if any
    python approved_cuts.py list
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "_state", "approved_cuts.json")
PROJECTS = r"{{KIT}}/Studio\data\projects.json"
MIN_DIFF = 1.0   # seconds: edge trims under this are padding / word-guard nudges, not a different edit


def _load(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def fingerprint(path):
    """the PICTURE of the first 30 s (video packets, stream copy) + the length: the same footage under any name, in ~0.2 s.
    Not the file bytes: the audio pass rewrites camera.mp4 (one-track boost / two-mic swap), so remote test prada 2's
    camera.mp4 had other bytes than the approved one while every video packet was the same."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy", "-t", "30", "-f", "md5", "-"],
                           capture_output=True, text=True, timeout=120)
        md5 = r.stdout.strip().partition("=")[2]
        d = duration(path)
        return f"{d:.1f}-{md5[:16]}" if md5 and d else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _recordings(project):
    """the project's recording files that share one timeline (camera_original only when it is as long as camera.mp4:
    a joined or pre-trimmed original is a different timeline)"""
    raw = os.path.join(project, "raw")
    cam = os.path.join(raw, "camera.mp4")
    out = [cam] if os.path.exists(cam) else []
    orig = os.path.join(raw, "camera_original.mp4")
    if os.path.exists(orig):
        dc, do = duration(cam) if out else None, duration(orig)
        if not out or (dc and do and abs(dc - do) < 0.1):
            out.append(orig)
    return out


def _save(reg):
    os.makedirs(os.path.dirname(REG), exist_ok=True)
    tmp = REG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=1)
    os.replace(tmp, REG)


def register(project, force=False, say=print):
    """store this approved project's final cut list as the answer key for its recording(s)"""
    project = os.path.abspath(project)
    doc = _load(os.path.join(project, "studio.json"), {})
    if not (doc.get("checklist") or {}).get("approved"):
        say(f"not approved, skipped: {project}")
        return None
    tl = _load(os.path.join(project, "work", "timeline.json"), {})
    if not tl.get("kept"):
        say(f"no work/timeline.json cut list, skipped: {project}")
        return None
    reg = _load(REG, {})
    fps = [f for f in (fingerprint(p) for p in _recordings(project)) if f]
    if not fps:
        say(f"no recording found, skipped: {project}")
        return None
    if not force and all(f in reg and reg[f]["path"].lower() == project.lower() for f in fps):
        return reg[fps[0]]   # a snapshot: rebuilding the approved project later never moves its own answer key
    entry = {"project": doc.get("id"), "title": doc.get("title") or os.path.basename(project), "path": project,
             "kept": [[round(a, 3), round(b, 3)] for a, b in tl["kept"]], "approved_at": time.strftime("%Y-%m-%d %H:%M"),
             "fingerprints": fps}
    for f in fps:
        reg[f] = entry
    _save(reg)
    say(f"answer key saved: {entry['title']} ({len(entry['kept'])} kept pieces, {len(fps)} fingerprint(s))")
    return entry


def lookup(project, cam=None):
    """the approved edit of this project's footage, or None"""
    reg = _load(REG, {})
    if not reg:
        return None
    files = ([str(cam)] if cam else []) + [os.path.join(str(project), "raw", n) for n in ("camera.mp4", "camera_original.mp4")]
    seen = set()
    for p in files:
        if p in seen or not os.path.exists(p):
            continue
        seen.add(p)
        f = fingerprint(p)
        if f in reg:
            return reg[f]
    return None


def _subtract(ranges, cuts):
    out = []
    for a, b in ranges:
        pieces = [(a, b)]
        for c, d in cuts:
            nxt = []
            for x, y in pieces:
                if d <= x or c >= y:
                    nxt.append((x, y))
                    continue
                if c > x:
                    nxt.append((x, c))
                if d < y:
                    nxt.append((d, y))
            pieces = nxt
        out += pieces
    return out


def compare(approved, kept, own_keeps=(), own_cuts=(), min_len=MIN_DIFF):
    """-> (plays_now, cut_now): ranges >= min_len that differ from the approved edit and are not explained by this
    project's own notes (raw/extra_keeps put footage back on purpose, raw/extra_cuts / audit cuts take it out)"""
    ap = [tuple(x) for x in approved]
    kp = [tuple(x) for x in kept]
    plays_now = _subtract(_subtract(kp, ap), [tuple(x) for x in own_keeps])
    cut_now = _subtract(_subtract(ap, kp), [tuple(x) for x in own_cuts])
    return ([r for r in plays_now if r[1] - r[0] >= min_len], [r for r in cut_now if r[1] - r[0] >= min_len])


def build(say=print):
    n = 0
    for p in _load(PROJECTS, []):
        path = p.get("path") if isinstance(p, dict) else None
        doc = _load(os.path.join(path, "studio.json"), {}) if path else {}
        if doc.get("type") == "review" and (doc.get("checklist") or {}).get("approved"):
            if register(path, say=lambda m: None):
                n += 1
    say(f"{n} approved review project(s) on file in {REG}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "build":
        build()
    elif cmd == "approve" and len(sys.argv) > 2:
        register(sys.argv[2], force="--force" in sys.argv)
    elif cmd == "check" and len(sys.argv) > 2:
        e = lookup(sys.argv[2])
        print(f"matches the approved edit of {e['title']} ({e['path']}, approved {e['approved_at']})" if e else "no approved edit of this footage")
    else:
        seen = {}
        for f, e in (_load(REG, {}) or {}).items():
            seen.setdefault(e["path"], e)
        for e in seen.values():
            print(f"{e['approved_at']}  {e['title']}  ({len(e['kept'])} pieces)  {e['path']}")


if __name__ == "__main__":
    main()
