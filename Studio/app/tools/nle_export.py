"""Export a project's current cut to a real video editor, linked to the ORIGINAL recording(s) (like Gling's export, 2026-10-29).

    python nle_export.py <project id> [xml|fcpxml|edl|otio|all]     -> writes <project>\\Editor export\\..., reads each back

What goes on the timeline (frame-exact, at the recording's own frame rate: 29.97 / 59.94 as 30000/1001 / 60000/1001):
  V1 / A1..An  the kept ranges of the recording back to back (every audio stream of the source on its own track: mic + game),
               a side-by-side OBS capture as ONE clip at its full size (the sequence is the recording's size, nothing cropped),
               the rendered intro in front when the draft has one, inserted clips (gaming settings.inserts) where the draft has them
  V2           B-roll notes ("broll 3:20 6s <clip>") at their times, the clip found by name in the project's B-roll
  A(n+1)       the music bed the last build used (timeline_info music), at the Studio's level
  markers      section names (gaming sections, haul / short chapters, "section" notes)
Formats: xml = Premiere Pro / Final Cut 7 XML (xmeml 5: Premiere, DaVinci Resolve, Vegas), fcpxml = FCPXML 1.9 (Resolve,
Final Cut Pro), edl = CMX 3600 (anything; one video track: V1 only, sections as LOC markers), otio = OpenTimelineIO (Resolve,
Kdenlive). CapCut and Filmora have no timeline import an outside app can write: NO_IMPORT says so and points to Resolve.
"""
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import media  # noqa: E402
import store  # noqa: E402
from recipes import common  # noqa: E402
from recipes import get as recipe  # noqa: E402

FORMATS = {
    "xml": {"label": "Premiere Pro / DaVinci Resolve / Vegas (XML)", "ext": ".xml", "suffix": "Premiere-Resolve"},
    "fcpxml": {"label": "Final Cut Pro / DaVinci Resolve (FCPXML)", "ext": ".fcpxml", "suffix": "FinalCut-Resolve"},
    "edl": {"label": "EDL (CMX 3600, any editor)", "ext": ".edl", "suffix": "EDL"},
    "otio": {"label": "OpenTimelineIO (.otio: Resolve, Kdenlive)", "ext": ".otio", "suffix": "OTIO"},
}
NO_IMPORT = {"capcut": "CapCut", "filmora": "Filmora"}
NO_IMPORT_MSG = ("{app} can't open a timeline made by another app (it has no XML / EDL import), so a cut can't be sent to it. "
                 "DaVinci Resolve is free and opens the Premiere / Resolve XML with every cut in place.")
RATES = [(24000, 1001), (24, 1), (25, 1), (30000, 1001), (30, 1), (50, 1), (60000, 1001), (60, 1)]
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".mts"}
MUSIC_DB = -22.0   # bed level when the build kept none (the Studio mixes beds around -22 .. -26 dB under the voice)


def rate_of(fps):
    """nearest editor frame rate as (num, den): phone VFR 59.83 -> 60000/1001, OBS 60 -> 60/1"""
    fps = fps or 30.0
    return min(RATES, key=lambda r: abs(r[0] / r[1] - fps))


def url_of(path, localhost=False):
    p = urllib.parse.quote(str(Path(path).resolve()).replace("\\", "/"), safe="/:")
    return ("file://localhost/" if localhost else "file:///") + p.lstrip("/")


class Timeline:
    """Everything in whole frames of the sequence rate, so no clip drifts against another."""

    def __init__(self, title, num, den, w, h):
        self.title, self.num, self.den, self.w, self.h = title, num, den, w, h
        self.fps = num / den
        self.v1, self.v2, self.music, self.markers, self.warnings = [], [], [], [], []
        self.sources = {}   # path -> probe

    def fr(self, t):
        return int(round(t * self.fps))

    def src(self, path):
        path = str(path)
        if path not in self.sources:
            info = media.probe(path)
            if not info:
                raise FileNotFoundError(f"can't read {path} (moved or deleted?)")
            self.sources[path] = info
        return self.sources[path]

    def src_frames(self, path):
        return int(self.src(path)["duration"] * self.fps)

    @property
    def n_audio(self):   # audio streams of the main recording = A1..An
        return max(1, len(self.src(self.main)["audio"]))

    @property
    def duration(self):
        return max([c["at"] + c["len"] for c in self.v1] or [0])


def _clip(path, inf, ln, at, **kw):
    return dict(src=str(path), inf=int(inf), len=int(ln), at=int(at), **kw)


def _inserts(doc):
    """inserted clips the gaming draft plays in the middle of the recording, in timeline order"""
    xs = [x for x in ((doc.get("settings") or {}).get("inserts") or []) + [n for n in doc.get("notes", []) if n.get("kind") == "insert"]
          if os.path.exists(x.get("file") or "") and x.get("at_raw") is not None]
    return sorted(xs, key=lambda x: float(x["at_raw"]))


def _broll_pool(doc, P):
    pool = [f for f in (doc.get("slots") or {}).get("broll", []) or [] if isinstance(f, str) and os.path.exists(f)]
    d = P.get("broll")
    if d and Path(d).is_dir():
        pool += [str(f) for f in sorted(Path(d).rglob("*")) if f.suffix.lower() in VIDEO_EXT and not f.name.startswith("_")]
    return pool


def build(doc):
    """The project's current cut as a Timeline."""
    r = recipe(doc["type"])
    P = r.paths(doc)
    main = doc.get("source") or ""
    if not os.path.exists(main):
        raise ValueError("this project has no recording yet")
    info = r.timeline_info(doc) or {}
    draft_keep = [tuple(k) for k in info.get("keep") or []] or (common.keep_ranges(P["cuts"]) if P.get("cuts") else None) or []
    if not draft_keep:
        raise ValueError("no cut yet: make a draft first (the export is the cut of the draft)")
    probe = media.probe(main)
    num, den = rate_of(probe.get("fps"))
    tl = Timeline(doc.get("title") or Path(doc["path"]).name, num, den, probe.get("width") or 1920, probe.get("height") or 1080)
    tl.main = main
    total_src = tl.src_frames(main)
    at = 0

    # the rendered intro in front (only when the draft has one: offset > 0)
    off = float(info.get("offset") or 0.0)
    if off > 0.5:
        intro = next((str(c) for c in ((doc.get("slots") or {}).get("intro"), P.get("intro_mp4"))
                      if c and Path(c).suffix.lower() in VIDEO_EXT and os.path.exists(c)), None)
        joined = P.get("final_intro")   # review: the intro only exists joined to the body: its first `off` seconds
        if not intro and joined and os.path.exists(joined) and tl.src(joined)["duration"] > off + 1:
            intro = str(joined)
        if intro:
            n = min(tl.src_frames(intro), tl.fr(off)) if intro == str(joined) else tl.src_frames(intro)
            tl.v1.append(_clip(intro, 0, n, 0, kind="intro"))
            at = n
        else:
            tl.warnings.append(f"the draft's {off:.1f} s intro isn't in the export (its file is made inside the build)")

    # V1: kept ranges + inserted clips; seg = (draft t0, draft t1, timeline frame of t0 or None when not in the export)
    inserts, k, segs, dropped, dt = _inserts(doc), 0, [], 0, 0.0
    for a, b in draft_keep:
        d = b - a
        if a >= 0:
            i0, i1 = max(0, tl.fr(a)), min(total_src, tl.fr(b))
            if i1 > i0:
                segs.append((dt, dt + d, at))
                tl.v1.append(_clip(main, i0, i1 - i0, at, kind="main"))
                at += i1 - i0
        else:   # a negative pseudo range = a clip the draft plays here (gaming insert / review cutaway)
            x = inserts[k] if k < len(inserts) else None
            src_in = float((x or {}).get("in") or 0)
            if x and tl.src(x["file"])["duration"] - src_in >= d - 0.5:   # the k-th insert fits the k-th pseudo range
                n = min(tl.fr(d), tl.src_frames(x["file"]) - tl.fr(src_in))
                segs.append((dt, dt + d, at))
                tl.v1.append(_clip(x["file"], tl.fr(src_in), n, at, kind="insert"))
                at += n
                k += 1
            else:
                segs.append((dt, dt + d, None))
                dropped += 1
        dt += d
    if dropped:
        tl.warnings.append(f"{dropped} short cutaway clip(s) of the draft aren't in the export: the build makes them, "
                           "they aren't part of your recording")
    body_end = dt

    def place(t):
        """draft (body) seconds -> timeline frame"""
        for d0, d1, f0 in segs:
            if t < d1 or (d0, d1) == segs[-1][:2]:
                if f0 is None:
                    nxt = next((s[2] for s in segs if s[0] >= d1 and s[2] is not None), at)
                    return nxt
                return f0 + tl.fr(max(0.0, min(t, d1) - d0))
        return at

    def from_raw(raw):
        return place(common.source_to_output(draft_keep, float(raw)))

    # markers: sections the draft knows
    seen = set()

    def mark(frame, name):
        name = (name or "").strip()
        if name and (frame, name) not in seen and 0 <= frame <= at:
            seen.add((frame, name))
            tl.markers.append({"at": frame, "name": name})
    if tl.v1 and tl.v1[0]["kind"] == "intro":
        mark(0, "Intro")
    if info.get("timeline"):
        for s in info["timeline"]:
            mark(place(float(s.get("t") or 0)), s.get("section"))
    elif info.get("haul_sections"):
        for s in info["haul_sections"]:
            mark(place(float(s[1] or 0)), s[0])
    else:
        for s in info.get("sections") or []:
            if isinstance(s, (list, tuple)) and len(s) >= 2 and s[1] is not None:
                mark(from_raw(s[1]), s[0])
    for n in doc.get("notes", []):
        if n.get("kind") == "section" and "raw0" in n:
            mark(from_raw(n["raw0"]), n.get("name") or n.get("text"))
    tl.markers.sort(key=lambda m: m["at"])

    # V2: B-roll notes
    pool = _broll_pool(doc, P)
    for n in doc.get("notes", []):
        if n.get("kind") != "broll" or "raw0" not in n or n.get("off"):
            continue
        want = (n.get("clip") or "").lower().strip()
        f = next((p for p in pool if want and want in Path(p).stem.lower()), None)
        f0 = from_raw(n["raw0"])
        ln = tl.fr(float(n.get("raw1", n["raw0"] + 5)) - float(n["raw0"]))
        if not f:
            tl.markers.append({"at": f0, "name": f"B-roll here: {n.get('clip') or '?'} (clip not found)"})
            continue
        ln = min(ln, tl.src_frames(f))
        if ln > 0:
            tl.v2.append(_clip(f, 0, ln, f0, kind="broll"))
    tl.v2.sort(key=lambda c: c["at"])

    # music bed: list [{s, e, track, gain_db, offset}] (haul / short, draft time) or gaming {section: {track, offset, chain}}
    mus = info.get("music") or {}

    def add_music(track, t0, t1, src_off=0.0, gain=None):
        if not (track and os.path.exists(track)) or t1 <= t0:
            return 0.0
        f0 = place(t0)
        n = min(tl.fr(t1 - t0), tl.src_frames(track) - tl.fr(src_off), at - f0)
        if n > 0:
            tl.music.append(_clip(track, tl.fr(src_off), n, f0, kind="music", gain_db=MUSIC_DB if gain is None else float(gain)))
        return max(0, n) / tl.fps
    if isinstance(mus, list):
        for m in mus:
            add_music(m.get("track"), float(m.get("s") or 0), float(m.get("e") or body_end), float(m.get("offset") or 0), m.get("gain_db"))
    elif isinstance(mus, dict) and info.get("timeline"):
        secs = info["timeline"]
        for i, s in enumerate(secs):
            m = mus.get(s.get("section"))
            if not isinstance(m, dict):
                continue
            pos, end = float(s.get("t") or 0), float(secs[i + 1]["t"]) if i + 1 < len(secs) else body_end
            for c in m.get("chain") or [m]:
                if pos >= end - 0.05:
                    break
                pos += add_music(c.get("track"), pos, end, float(c.get("offset") or 0), m.get("gain_db")) or (end - pos)
    tl.music.sort(key=lambda c: c["at"])
    return tl


# ---------------------------------------------------------------- writers
def _rate_el(parent, tl):
    r = ET.SubElement(parent, "rate")
    ET.SubElement(r, "timebase").text = str(round(tl.fps))
    ET.SubElement(r, "ntsc").text = "TRUE" if tl.den == 1001 else "FALSE"
    return r


def write_xmeml(tl):
    """Final Cut 7 / Premiere XML (xmeml version 5)."""
    root = ET.Element("xmeml", version="5")
    seq = ET.SubElement(root, "sequence", id="sequence-1")
    ET.SubElement(seq, "name").text = tl.title
    ET.SubElement(seq, "duration").text = str(tl.duration)
    _rate_el(seq, tl)
    tc = ET.SubElement(seq, "timecode")
    _rate_el(tc, tl)
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "NDF"
    med = ET.SubElement(seq, "media")
    files, ids = {}, {"clip": 0}

    def file_el(parent, path):
        if path in files:
            ET.SubElement(parent, "file", id=files[path])
            return
        files[path] = fid = f"file-{len(files) + 1}"
        info = tl.src(path)
        f = ET.SubElement(parent, "file", id=fid)
        ET.SubElement(f, "name").text = Path(path).name
        ET.SubElement(f, "pathurl").text = url_of(path, localhost=True)
        _rate_el(f, tl)
        ET.SubElement(f, "duration").text = str(tl.src_frames(path))
        fm = ET.SubElement(f, "media")
        if info.get("width"):
            sc = ET.SubElement(ET.SubElement(fm, "video"), "samplecharacteristics")
            _rate_el(sc, tl)
            ET.SubElement(sc, "width").text = str(info["width"])
            ET.SubElement(sc, "height").text = str(info["height"])
            ET.SubElement(sc, "anamorphic").text = "FALSE"
            ET.SubElement(sc, "pixelaspectratio").text = "square"
        for a in info.get("audio") or []:
            au = ET.SubElement(fm, "audio")
            sc = ET.SubElement(au, "samplecharacteristics")
            ET.SubElement(sc, "depth").text = "16"
            ET.SubElement(sc, "samplerate").text = "48000"
            ET.SubElement(au, "channelcount").text = str(a.get("channels") or 2)

    def clipitem(track, c, stream=None, gain_db=None):
        ids["clip"] += 1
        ci = ET.SubElement(track, "clipitem", id=f"clipitem-{ids['clip']}")
        ET.SubElement(ci, "name").text = Path(c["src"]).name
        ET.SubElement(ci, "enabled").text = "TRUE"
        ET.SubElement(ci, "duration").text = str(tl.src_frames(c["src"]))
        _rate_el(ci, tl)
        ET.SubElement(ci, "start").text = str(c["at"])
        ET.SubElement(ci, "end").text = str(c["at"] + c["len"])
        ET.SubElement(ci, "in").text = str(c["inf"])
        ET.SubElement(ci, "out").text = str(c["inf"] + c["len"])
        file_el(ci, c["src"])
        if stream is not None:
            st = ET.SubElement(ci, "sourcetrack")
            ET.SubElement(st, "mediatype").text = "audio"
            ET.SubElement(st, "trackindex").text = str(stream + 1)
        if gain_db is not None:
            eff = ET.SubElement(ET.SubElement(ci, "filter"), "effect")
            for k, v in (("name", "Audio Levels"), ("effectid", "audiolevels"), ("effectcategory", "audiolevels"),
                         ("effecttype", "audiolevels"), ("mediatype", "audio")):
                ET.SubElement(eff, k).text = v
            p = ET.SubElement(eff, "parameter", authoringApp="PremierePro")
            for k, v in (("parameterid", "level"), ("name", "Level"), ("valuemin", "0"), ("valuemax", "3.98109"),
                         ("value", f"{10 ** (gain_db / 20):.5f}")):
                ET.SubElement(p, k).text = v

    vid = ET.SubElement(med, "video")
    sc = ET.SubElement(ET.SubElement(vid, "format"), "samplecharacteristics")
    _rate_el(sc, tl)
    for k, v in (("width", tl.w), ("height", tl.h), ("anamorphic", "FALSE"), ("pixelaspectratio", "square"), ("fielddominance", "none")):
        ET.SubElement(sc, k).text = str(v)
    for clips in (tl.v1, tl.v2):
        if clips:
            tr = ET.SubElement(vid, "track")
            for c in clips:
                clipitem(tr, c)
    aud = ET.SubElement(med, "audio")
    ET.SubElement(aud, "numOutputChannels").text = "2"
    for s in range(tl.n_audio):
        tr = ET.SubElement(aud, "track")
        for c in tl.v1:
            n_src = len(tl.src(c["src"])["audio"])
            if s < n_src:
                clipitem(tr, c, stream=s)
    if tl.music:
        tr = ET.SubElement(aud, "track")
        for c in tl.music:
            clipitem(tr, c, stream=0, gain_db=c["gain_db"])
    for m in tl.markers:
        mk = ET.SubElement(seq, "marker")
        ET.SubElement(mk, "name").text = m["name"]
        ET.SubElement(mk, "comment").text = ""
        ET.SubElement(mk, "in").text = str(m["at"])
        ET.SubElement(mk, "out").text = "-1"
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_fcpxml(tl):
    """FCPXML 1.9: one spine of asset-clips (V1 + its audio), B-roll on lane 1, music on lane -1, markers on the spine clips."""
    fd = lambda f: f"{f * tl.den}/{tl.num}s" if f else "0s"  # noqa: E731  frames -> rational seconds
    root = ET.Element("fcpxml", version="1.9")
    res = ET.SubElement(root, "resources")
    rid = {"n": 0}
    fmts, assets = {}, {}

    def new_id():
        rid["n"] += 1
        return f"r{rid['n']}"

    def fmt(w, h, num, den):
        key = (w, h, num, den)
        if key not in fmts:
            fmts[key] = new_id()
            tok = {(24000, 1001): "2398", (30000, 1001): "2997", (60000, 1001): "5994"}.get((num, den), str(round(num / den)))
            std = {(1920, 1080): "1080p", (3840, 2160): "2160p", (1280, 720): "720p"}.get((w, h))
            a = {"id": fmts[key], "frameDuration": f"{den}/{num}s", "width": str(w), "height": str(h)}
            if std:
                a["name"] = f"FFVideoFormat{std}{tok}"
            ET.SubElement(res, "format", a)
        return fmts[key]
    seq_fmt = fmt(tl.w, tl.h, tl.num, tl.den)

    def asset(path):
        if path in assets:
            return assets[path]
        info = tl.src(path)
        aid = new_id()
        a = {"id": aid, "name": Path(path).stem, "start": "0s", "duration": fd(tl.src_frames(path))}
        if info.get("width"):
            n2, d2 = rate_of(info.get("fps"))
            a.update(hasVideo="1", format=seq_fmt if path == tl.main else fmt(info["width"], info["height"], n2, d2))
        else:
            a["hasVideo"] = "0"
        if info.get("audio"):
            a.update(hasAudio="1", audioSources=str(len(info["audio"])), audioChannels=str(info["audio"][0].get("channels") or 2),
                     audioRate="48000")
        else:
            a["hasAudio"] = "0"
        el = ET.SubElement(res, "asset", a)
        ET.SubElement(el, "media-rep", kind="original-media", src=url_of(path))
        assets[path] = aid
        return aid
    for c in tl.v1 + tl.v2 + tl.music:   # resources first, in a stable order
        asset(c["src"])
    res[:] = [e for e in res if e.tag == "format"] + [e for e in res if e.tag != "format"]   # formats before the assets using them
    lib = ET.SubElement(root, "library")
    ev = ET.SubElement(lib, "event", name="{{STUDIO_NAME}}")
    pr = ET.SubElement(ev, "project", name=tl.title)
    sq = ET.SubElement(pr, "sequence", format=seq_fmt, duration=fd(tl.duration), tcStart="0s", tcFormat="NDF",
                       audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(sq, "spine")
    parents = []
    for c in tl.v1:
        el = ET.SubElement(spine, "asset-clip", ref=asset(c["src"]), offset=fd(c["at"]), name=Path(c["src"]).stem,
                           start=fd(c["inf"]), duration=fd(c["len"]), tcFormat="NDF")
        parents.append((c, el, []))

    def parent_of(frame):
        for c, el, kids in parents:
            if c["at"] <= frame < c["at"] + c["len"]:
                return c, el, kids
        return parents[-1]
    for c in tl.v2 + tl.music:
        pc, el, kids = parent_of(c["at"])
        kids.append(("clip", c))
    for m in tl.markers:
        pc, el, kids = parent_of(m["at"])
        kids.append(("marker", m))
    for pc, el, kids in parents:   # connected clips before markers (DTD order); times in the parent's source time
        local = lambda f: fd(pc["inf"] + (f - pc["at"]))  # noqa: E731
        for kind, c in kids:
            if kind != "clip":
                continue
            a = {"ref": asset(c["src"]), "lane": "1" if c["kind"] == "broll" else "-1", "offset": local(c["at"]),
                 "name": Path(c["src"]).stem, "start": fd(c["inf"]), "duration": fd(c["len"]), "tcFormat": "NDF"}
            if c["kind"] == "broll":
                a["srcEnable"] = "video"
            cl = ET.SubElement(el, "asset-clip", a)
            if c.get("gain_db") is not None:
                ET.SubElement(cl, "adjust-volume", amount=f"{c['gain_db']:.1f}dB")
        for kind, m in kids:
            if kind == "marker":
                ET.SubElement(el, "marker", start=local(m["at"]), duration=fd(1), value=m["name"])
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _tc(f, base, hours=0):
    f += hours * 3600 * base
    return f"{f // (3600 * base):02d}:{f // (60 * base) % 60:02d}:{f // base % 60:02d}:{f % base:02d}"


def write_edl(tl):
    """CMX 3600: V1 + its audio (B), record from 01:00:00:00, clip names + paths as comments (Resolve relinks by them)."""
    base = round(tl.fps)
    title = re.sub(r"[^\w .#&()-]", "", tl.title)[:60] or "{{STUDIO_NAME}}"
    out = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for i, c in enumerate(tl.v1, 1):
        ch = "B" if tl.src(c["src"])["audio"] else "V"
        out.append(f"{i:03d}  AX       {ch:<5} C        {_tc(c['inf'], base)} {_tc(c['inf'] + c['len'], base)} "
                   f"{_tc(c['at'], base, 1)} {_tc(c['at'] + c['len'], base, 1)}")
        out.append(f"* FROM CLIP NAME: {Path(c['src']).name}")
        out.append(f"* SOURCE FILE: {c['src']}")
        for m in tl.markers:
            if c["at"] <= m["at"] < c["at"] + c["len"]:
                out.append(f"* LOC: {_tc(m['at'], base, 1)} YELLOW  {m['name']}")
        out.append("")
    return "\r\n".join(out) + "\r\n"


def write_otio(tl):
    """OpenTimelineIO JSON (schemas every reader since OTIO 0.12 opens): V1, V2, A1..An, music."""
    rt = lambda v: {"OTIO_SCHEMA": "RationalTime.1", "rate": tl.fps, "value": float(v)}  # noqa: E731
    tr = lambda s, d: {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(s), "duration": rt(d)}  # noqa: E731

    def clip(c, markers=()):
        return {"OTIO_SCHEMA": "Clip.1", "name": Path(c["src"]).name, "source_range": tr(c["inf"], c["len"]),
                "media_reference": {"OTIO_SCHEMA": "ExternalReference.1", "name": Path(c["src"]).name, "target_url": url_of(c["src"]),
                                    "available_range": tr(0, tl.src_frames(c["src"])), "metadata": {}},
                "effects": [], "markers": [{"OTIO_SCHEMA": "Marker.2", "name": m["name"], "color": "YELLOW", "comment": "",
                                            "marked_range": tr(c["inf"] + m["at"] - c["at"], 0), "metadata": {}} for m in markers],
                "enabled": True, "metadata": {"studio": {"gain_db": c["gain_db"]}} if c.get("gain_db") is not None else {}}

    def track(name, kind, clips, with_markers=False):
        kids, t = [], 0
        for c in clips:
            if c["at"] > t:
                kids.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": tr(0, c["at"] - t), "effects": [], "markers": [],
                             "enabled": True, "metadata": {}})
            ms = [m for m in tl.markers if c["at"] <= m["at"] < c["at"] + c["len"]] if with_markers else []
            kids.append(clip(c, ms))
            t = c["at"] + c["len"]
        return {"OTIO_SCHEMA": "Track.1", "name": name, "kind": kind, "children": kids, "source_range": None, "effects": [],
                "markers": [], "enabled": True, "metadata": {}}
    tracks = [track("V1", "Video", tl.v1, True)]
    if tl.v2:
        tracks.append(track("V2", "Video", tl.v2))
    tracks.append(track("A1", "Audio", tl.v1))   # OTIO names no audio stream: the first one; XML / FCPXML carry them all
    if tl.music:
        tracks.append(track("A2 music", "Audio", tl.music))
    d = {"OTIO_SCHEMA": "Timeline.1", "name": tl.title, "global_start_time": None, "metadata": {},
         "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks, "source_range": None, "effects": [],
                    "markers": [], "enabled": True, "metadata": {}}}
    return json.dumps(d, indent=1, ensure_ascii=False)


WRITERS = {"xml": write_xmeml, "fcpxml": write_fcpxml, "edl": write_edl, "otio": write_otio}


def expected(tl, fmt):
    """what project_import.read should find in the written file: clip count + length in seconds"""
    clips = len(tl.v1) + (len(tl.v2) if fmt == "xml" else 0)
    return clips, tl.duration / tl.fps


def readback(path, tl, fmt):
    sys.path.insert(0, str(APP / "tools"))
    import project_import
    got = project_import.read(path)
    want_n, want_s = expected(tl, fmt)
    # the reader counts whole-number frame rates (xmeml timebase 30 for 29.97, EDL timecode at 30): allow 0.2 % + 1 frame a clip
    tol = want_s * 0.002 + len(tl.v1) / tl.fps + 0.2
    if fmt == "edl" and round(tl.fps) != 30:
        # project_import.edl reads frames as 1/30 s whatever the rate (at 60 fps a clip ending on frame 0-29 of the next
        # second reads as ending before it starts and is dropped): read the record timecodes at the real rate instead
        base, tc = round(tl.fps), r"(\d\d):(\d\d):(\d\d):(\d\d)"
        ev = [[int(x) for x in m] for m in re.findall(rf"^\d{{3}}\s+\S+\s+\S+\s+C\s+{tc} {tc} {tc} {tc}", Path(path).read_text(encoding="utf-8"), re.M)]
        f = lambda g: ((g[0] - 1) * 3600 + g[1] * 60 + g[2]) * base + g[3]  # noqa: E731
        spans = [(f(e[8:12]), f(e[12:16])) for e in ev]
        gapless = all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1)) and all(b > a for a, b in spans)
        got = dict(got, clips=len(spans), duration=round((spans[-1][1] if spans else 0) / tl.fps, 1))
        tol = 1 / tl.fps + 0.05 if gapless else -1
    ok = got["clips"] == want_n and abs(got["duration"] - want_s) <= tol
    return {"ok": ok, "clips": got["clips"], "want_clips": want_n, "duration": got["duration"], "want_duration": round(want_s, 1),
            "markers": len(got.get("markers") or [])}


def export(doc, fmt="xml"):
    fmt = (fmt or "xml").lower()
    if fmt in NO_IMPORT:
        raise ValueError(NO_IMPORT_MSG.format(app=NO_IMPORT[fmt]))
    if fmt not in WRITERS:
        raise ValueError(f"unknown format {fmt}: pick one of {', '.join(WRITERS)}")
    tl = build(doc)
    folder = Path(doc["path"]) / "Editor export"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{store.safe_name(tl.title)} - {FORMATS[fmt]['suffix']}{FORMATS[fmt]['ext']}"
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(WRITERS[fmt](tl), encoding="utf-8", newline="")
    os.replace(tmp, out)
    try:
        check = readback(out, tl, fmt)
    except Exception as e:  # noqa: the export stands; the check says why it couldn't read it
        check = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"file": str(out), "folder": str(folder), "format": fmt, "label": FORMATS[fmt]["label"],
            "clips": len(tl.v1), "broll": len(tl.v2), "music": len(tl.music), "markers": len(tl.markers),
            "audio_tracks": tl.n_audio, "fps": f"{tl.num}/{tl.den}" if tl.den != 1 else str(tl.num), "size": f"{tl.w}x{tl.h}",
            "duration": round(tl.duration / tl.fps, 2), "warnings": tl.warnings, "check": check}


# ---------------------------------------------------------------- route
def api_export(q, body):
    doc = store.load(q.get("id", ""))
    if not doc:
        raise ValueError("no such project")
    return export(doc, (body or {}).get("format", "xml"))


def api_formats(q, body):
    return {"formats": [{"key": k, "label": v["label"]} for k, v in FORMATS.items()] +
                       [{"key": k, "label": f"{v} (no import: use Resolve)", "none": True} for k, v in NO_IMPORT.items()]}


ROUTES = {("POST", "project/nle-export"): api_export, ("GET", "nle-formats"): api_formats}

if __name__ == "__main__":
    d = store.load(sys.argv[1]) or next((x for x in store.all_projects() if x.get("title") == sys.argv[1]), None)
    if not d:
        sys.exit("no such project")
    for f in (WRITERS if len(sys.argv) < 3 or sys.argv[2] == "all" else [sys.argv[2]]):
        print(json.dumps(export(d, f), indent=1, ensure_ascii=False))
