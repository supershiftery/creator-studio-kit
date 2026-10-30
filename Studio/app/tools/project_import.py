"""Read another editor's project file for the Train wizard (my_style): how the video was cut, without the footage.

    python project_import.py <file>     -> JSON summary

Reads, straight from the editor's own file:
  Premiere Pro (.prproj, or its XML), Filmora (.wfp), CapCut (draft_content.json / draft_info.json, unless encrypted),
  Kdenlive (.kdenlive) and Shotcut (.mlt),
and the exports every editor can make (File -> Export): XML (Premiere / Final Cut 7 / Resolve / Vegas), FCPXML (Final Cut Pro,
Resolve), EDL (Resolve, Vegas, Avid, Premiere, Media Composer), OpenTimelineIO (.otio: Resolve, Kdenlive).
DaVinci Resolve (.drp) and Vegas (.veg) keep their own files closed: read() says how to export the timeline instead.
Returns {"tool", "clips", "duration", "avg_clip_s", "cuts_per_min", "video_tracks", "transitions", "effects",
"texts": [{"t", "text"}], "markers"} - whatever the format holds.
"""
import gzip
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

PR_TICKS = 254016000000   # Premiere ticks a second


def _summary(tool, spans, tracks=0, transitions=None, effects=None, texts=None, markers=None):
    spans = sorted((a, b) for a, b in spans if b > a)
    dur = max((b for _, b in spans), default=0.0)
    lens = [b - a for a, b in spans]
    return {"tool": tool, "clips": len(spans), "duration": round(dur, 1),
            "avg_clip_s": round(sorted(lens)[len(lens) // 2], 2) if lens else None,
            "cuts_per_min": round(len(spans) / (dur / 60), 1) if dur else None, "video_tracks": tracks,
            "transitions": dict(Counter(transitions or []).most_common(8)), "effects": dict(Counter(effects or []).most_common(12)),
            "texts": (texts or [])[:30], "markers": (markers or [])[:30]}


def premiere(text):
    """.prproj XML: video clip items (ticks), effect display names, transition names, title / caption text where readable."""
    spans = [(int(a) / PR_TICKS, int(b) / PR_TICKS) for a, b in
             re.findall(r"<VideoClipTrackItem\b.*?<Start>(\d+)</Start>\s*<End>(\d+)</End>", text, re.S)]
    effects = [n for n in re.findall(r"<DisplayName>([^<]{2,60})</DisplayName>", text)
               if n not in ("Motion", "Opacity", "Time Remapping", "Volume", "Channel Volume", "Panner", "MPEG Source Settings")]
    trans = re.findall(r"<VideoTransitionTrackItem\b.*?<(?:DisplayName|Name)>([^<]+)<", text, re.S)
    # titles: Premiere keeps Essential Graphics text encoded inside the effect, so only the count of text layers is known
    # ("Text" / "Graphic" in effects); the frames of a finished video show what they say
    tracks = len(set(re.findall(r"<VideoClipTrack ObjectID=\"(\d+)\"", text))) or None
    markers = [{"t": None, "text": m.strip()[:120]} for m in re.findall(r"<Marker\b.*?<Name>([^<]+)</Name>", text, re.S)]
    return _summary("Premiere Pro", spans, tracks, trans, effects, [], markers)


def xmeml(root):
    """Premiere / Final Cut 7 XML export."""
    seq = root.find(".//sequence")
    rate = float((seq.findtext("rate/timebase") if seq is not None else None) or 30)
    spans, trans, effects, texts, markers = [], [], [], [], []
    tracks = root.findall(".//media/video/track")
    for tr in tracks:
        for ci in tr.findall("clipitem"):
            s, e = ci.findtext("start"), ci.findtext("end")
            if s and e and int(s) >= 0 and int(e) > 0:
                spans.append((int(s) / rate, int(e) / rate))
            effects += [f.findtext("name") for f in ci.findall("filter/effect") if f.findtext("name")]
        trans += [t.findtext("effect/name") for t in tr.findall("transitionitem") if t.findtext("effect/name")]
        for g in tr.findall("generatoritem"):
            val = " ".join(p.findtext("value") or "" for p in g.findall(".//parameter") if (p.findtext("name") or "").lower() in ("text", "str"))
            if val.strip():
                texts.append({"t": round(int(g.findtext("start") or 0) / rate, 2), "text": val.strip()[:160]})
    for m in root.findall(".//sequence/marker"):
        markers.append({"t": round(int(m.findtext("in") or 0) / rate, 2), "text": (m.findtext("name") or m.findtext("comment") or "")[:120]})
    return _summary("XML (Premiere / Final Cut 7)", spans, len(tracks), trans, effects, texts, markers)


def _fcp_t(v):
    """FCPXML time: "3600/30s", "12s", "1001/30000s"."""
    if not v:
        return 0.0
    v = v.rstrip("s")
    if "/" in v:
        a, b = v.split("/")
        return float(a) / float(b)
    return float(v)


def fcpxml(root):
    spans, trans, effects, texts, markers = [], [], [], [], []
    spine = root.find(".//spine")
    for el in (spine if spine is not None else []):
        off, dur = _fcp_t(el.get("offset")), _fcp_t(el.get("duration"))
        if el.tag in ("asset-clip", "clip", "video", "ref-clip", "sync-clip", "mc-clip"):
            spans.append((off, off + dur))
        elif el.tag == "transition":
            trans.append(el.get("name") or "transition")
        for t in el.iter("title"):
            txt = " ".join(x.text or "" for x in t.iter("text-style")).strip()
            if txt:
                texts.append({"t": round(_fcp_t(t.get("offset")), 2), "text": txt[:160]})
        effects += [f.get("name") for f in el.iter("filter-video") if f.get("name")]
        markers += [{"t": round(_fcp_t(m.get("start")), 2), "text": (m.get("value") or "")[:120]} for m in el.iter("marker")]
    return _summary("Final Cut Pro", spans, None, trans, effects, texts, markers)


def capcut(d):
    spans, trans, effects, texts = [], [], [], []
    mats = d.get("materials") or {}
    text_by_id = {}
    for t in mats.get("texts") or []:
        c = t.get("content") or ""
        try:
            c = json.loads(c).get("text", c)
        except (ValueError, AttributeError):
            pass
        text_by_id[t.get("id")] = re.sub(r"<[^>]+>|\[|\]", "", str(c))[:160]
    vtracks = [t for t in d.get("tracks") or [] if t.get("type") == "video"]
    for tr in d.get("tracks") or []:
        for s in tr.get("segments") or []:
            r = s.get("target_timerange") or {}
            a, b = r.get("start", 0) / 1e6, (r.get("start", 0) + r.get("duration", 0)) / 1e6
            if tr.get("type") == "video" and tr is vtracks[0]:
                spans.append((a, b))
            if tr.get("type") == "text" and text_by_id.get(s.get("material_id")):
                texts.append({"t": round(a, 2), "text": text_by_id[s["material_id"]]})
    trans = [t.get("name") or "transition" for t in mats.get("transitions") or []]
    effects = [e.get("name") for e in (mats.get("video_effects") or []) + (mats.get("effects") or []) if e.get("name")]
    if mats.get("speeds") and any(abs((s.get("speed") or 1) - 1) > 0.01 for s in mats["speeds"]):
        effects.append("speed change")
    texts.sort(key=lambda x: x["t"])
    return _summary("CapCut", spans, len(vtracks), trans, effects, texts)


def _strings(o, keys=("text", "content", "title", "subtitle"), out=None):
    """Short strings under text-like keys anywhere in a JSON tree (title / caption clips)."""
    out = [] if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and k.lower() in keys and 1 < len(v.strip()) < 300 and not v.strip().startswith(("{", "file:", "http")):
                out.append(v.strip())
            else:
                _strings(v, keys, out)
    elif isinstance(o, list):
        for v in o:
            _strings(v, keys, out)
    return out


def filmora(z):
    """Wondershare Filmora .wfp: a zip; the timeline is Medias/<timeline id>/timeline.wesproj (JSON, times in 100 ns)."""
    tl_name = next((n for n in z.namelist() if n.endswith("timeline.wesproj")), None)
    if not tl_name:
        raise ValueError("this Filmora project keeps no timeline inside (cloud project?): export the video and add it as a finished video")
    d = json.loads(z.read(tl_name))
    spans, effects, texts, vtracks = [], [], [], 0
    for tl in d.get("timelineInfos") or []:
        for tr in tl.get("trackInfos") or []:
            clips = tr.get("clipList") or []
            if tr.get("trackType") == 1:   # 1 = video, 2 = audio
                vtracks += 1
            for c in clips:
                a, b = (c.get("tlBegin") or 0) / 1e7, (c.get("tlEnd") or 0) / 1e7
                if tr.get("trackType") == 1 and c.get("type") == 1:
                    spans.append((a, b))
                effects += [e.get("name") for e in c.get("effectChainList") or []
                            if e.get("name") and e["name"] not in ("Basic", "BasicFollow", "Effect") and not e["name"].startswith("_")]
                if tr.get("trackType") not in (1, 2) or c.get("type") not in (1, 2):
                    texts += [{"t": round(a, 2), "text": s[:160]} for s in _strings(c)[:2]]
                sp = c.get("speed")
                sp = sp.get("speed", sp.get("value", 1)) if isinstance(sp, dict) else sp
                if isinstance(sp, (int, float)) and abs(sp - 1) > 0.01:
                    effects.append("speed change")
    return _summary("Filmora", spans, vtracks, None, effects, texts)


def edl(text):
    """CMX 3600 EDL: one event a line, record in/out timecodes; transitions as D / W codes."""
    fps = 30.0
    m = re.search(r"FCM:\s*(DROP|NON-DROP)", text)
    spans, trans = [], []
    tc = r"(\d\d):(\d\d):(\d\d)[:;](\d\d)"
    for line in text.splitlines():
        ev = re.match(rf"\s*\d+\s+\S+\s+(V\S*|A\S*|B)\s+(C|D|W\d+|K)\S*\s+(\d+\s+)?{tc}\s+{tc}\s+{tc}\s+{tc}", line)
        if not ev or not ev.group(1).startswith(("V", "B")):
            continue
        g = ev.groups()
        rec_in = [int(x) for x in g[11:15]]
        rec_out = [int(x) for x in g[15:19]]
        to_s = lambda h, mi, s, f: h * 3600 + mi * 60 + s + f / fps  # noqa: E731
        spans.append((to_s(*rec_in), to_s(*rec_out)))
        if g[1] != "C":
            trans.append("dissolve" if g[1] == "D" else "wipe" if g[1].startswith("W") else "key")
    if spans:   # record times usually start at 01:00:00:00
        t0 = min(a for a, _ in spans)
        spans = [(a - t0, b - t0) for a, b in spans]
    markers = [{"t": None, "text": x.strip()[:120]} for x in re.findall(r"\*\s*(?:LOC|COMMENT):\s*(.+)", text)][:30]
    return _summary("EDL" + (" (" + m.group(1).lower() + " frame)" if m else ""), spans, None, trans, None, None, markers)


def otio(d):
    """OpenTimelineIO JSON (Resolve, Kdenlive): Timeline -> Stack -> Tracks -> Clips / Transitions / Gaps."""
    spans, trans, effects, markers, vtracks = [], [], [], [], 0
    rt = lambda r: (r or {}).get("value", 0) / ((r or {}).get("rate") or 24)  # noqa: E731
    for tr in ((d.get("tracks") or {}).get("children") or []):
        if tr.get("kind") != "Video":
            continue
        vtracks += 1
        t = 0.0
        for c in tr.get("children") or []:
            sch = (c.get("OTIO_SCHEMA") or "").split(".")[0]
            dur = rt((c.get("source_range") or {}).get("duration"))
            if sch == "Transition":
                trans.append(c.get("transition_type") or c.get("name") or "transition")
                continue
            if sch == "Clip" and vtracks == 1:
                spans.append((t, t + dur))
            effects += [e.get("effect_name") or e.get("name") for e in c.get("effects") or [] if e.get("effect_name") or e.get("name")]
            markers += [{"t": round(t, 2), "text": (mk.get("name") or "")[:120]} for mk in c.get("markers") or []]
            t += dur
    return _summary("OpenTimelineIO", spans, vtracks, trans, effects, None, markers)


def mlt(root, tool):
    """Kdenlive / Shotcut (MLT XML): playlists of entries with in/out frames; titles are kdenlivetitle producers."""
    prof = root.find("profile")
    fps = float(prof.get("frame_rate_num", 25)) / float(prof.get("frame_rate_den", 1)) if prof is not None else 25.0

    def fr(v):
        if not v:
            return 0.0
        if ":" in v:   # "00:00:03.040" or "00:00:03:01"
            parts = v.replace(",", ".").split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2] if len(parts) == 3 else parts[2]) + \
                (float(parts[3]) / fps if len(parts) == 4 else 0)
        return float(v) / fps
    prods = {p.get("id"): p for p in root.iter("producer")} | {p.get("id"): p for p in root.iter("chain")}
    texts = []
    for p in prods.values():
        svc = next((x.text for x in p.findall("property") if x.get("name") == "mlt_service"), "")
        if svc in ("kdenlivetitle", "qtext", "dynamictext"):
            xml = next((x.text for x in p.findall("property") if x.get("name") in ("xmldata", "text", "argument")), "") or ""
            texts += [t.strip()[:160] for t in re.findall(r"<content[^>]*>([^<]+)</content>", xml) or [xml] if t.strip()]
    best = []
    for pl in root.iter("playlist"):
        t, spans = 0.0, []
        for e in pl:
            if e.tag == "blank":
                t += fr(e.get("length"))
            elif e.tag == "entry":
                d = fr(e.get("out")) - fr(e.get("in"))
                spans.append((t, t + d))
                t += d
        if len(spans) > len(best):
            best = spans
    trans = [next((x.text for x in tr.findall("property") if x.get("name") in ("kdenlive_id", "mlt_service")), "transition")
             for tr in root.iter("transition")]
    trans = [x for x in trans if x not in ("mix", "frei0r.cairoblend", "qtblend", "composite", "affine")]
    effects = [next((x.text for x in f.findall("property") if x.get("name") in ("kdenlive_id", "shotcut:filter", "mlt_service")), None)
               for f in root.iter("filter")]
    return _summary(tool, best, None, trans, [e for e in effects if e], [{"t": None, "text": x} for x in texts])


CLOSED = {".drp": "DaVinci Resolve keeps its project file closed. In Resolve: File > Export > Timeline > pick FCPXML (or EDL), "
                  "then add that file here.",
          ".drt": "DaVinci Resolve keeps its project file closed. In Resolve: File > Export > Timeline > pick FCPXML (or EDL), "
                  "then add that file here.",
          ".veg": "Vegas Pro keeps its project file closed. In Vegas: File > Export > Final Cut Pro 7 XML (or EDL), then add that file here.",
          ".aep": "After Effects projects hold graphics, not a cut: add the rendered graphic as a piece instead.",
          ".mlv": "Movavi keeps its project file closed: export the video and add it as a finished video.",
          ".wve": "Wondershare's older format is closed: open it in Filmora, save as .wfp, then add that."}


def read(path):
    p = Path(path)
    ext = p.suffix.lower()
    if ext in CLOSED:
        raise ValueError(CLOSED[ext])
    raw = p.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if raw[:2] == b"PK":   # a zip: Filmora .wfp (or a zipped export)
        z = zipfile.ZipFile(io.BytesIO(raw))
        if any(n.endswith("timeline.wesproj") or n.endswith("project_info.json") for n in z.namelist()):
            return filmora(z)
        inner = next((n for n in z.namelist() if n.lower().endswith((".fcpxml", ".xml", ".edl", ".otio"))), None)
        if inner:
            tmp = Path(sys.argv[0]).parent / "_import_tmp" / Path(inner).name
            tmp.parent.mkdir(exist_ok=True)
            tmp.write_bytes(z.read(inner))
            try:
                return read(tmp)
            finally:
                tmp.unlink(missing_ok=True)
        raise ValueError(f"{p.name}: a zip with no timeline this can read")
    if ext == ".edl" or raw.lstrip()[:6] == b"TITLE:":
        return edl(raw.decode("utf-8", "replace"))
    if ext == ".json" or ext == ".otio" or raw.lstrip()[:1] == b"{":
        try:
            d = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise ValueError("this CapCut draft is encrypted (newer CapCut versions): export the video instead and add it as a finished video")
        if str(d.get("OTIO_SCHEMA", "")).startswith("Timeline"):
            return otio(d)
        return capcut(d)
    text = raw.decode("utf-8", "replace")
    if "<PremiereData" in text[:2000]:
        return premiere(text)
    root = ET.fromstring(raw)
    if root.tag == "xmeml":
        return xmeml(root)
    if root.tag == "fcpxml":
        return fcpxml(root)
    if root.tag == "mlt":
        return mlt(root, "Kdenlive" if ext == ".kdenlive" or root.find(".//property[@name='kdenlive:docproperties.version']") is not None else "Shotcut")
    raise ValueError(f"{p.name}: not a project this can read. Export the timeline from your editor as XML, FCPXML or EDL "
                     "(File > Export), or add the finished video instead.")


PROJECT_EXT = {".prproj", ".wfp", ".xml", ".fcpxml", ".edl", ".otio", ".kdenlive", ".mlt", ".json", ".drp", ".drt", ".veg"}

if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(json.dumps(read(a), indent=1, ensure_ascii=False))
