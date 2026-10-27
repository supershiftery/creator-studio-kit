"""Parse a Gling/Premiere xmeml (v4/v5) or FCPXML export into (media_path, kept_ranges_seconds).

The XML is an edit decision list: clipitems carry <in>/<out> source times (frames at the
sequence timebase) and the <file><pathurl> of the ORIGINAL recording — which still has all
audio tracks (Focusrite + DJI), unlike the mp4 Gling renders out.
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path


def _rate(el):
    tb = float(el.findtext("rate/timebase") or 30)
    ntsc = (el.findtext("rate/ntsc") or "FALSE").strip().upper() == "TRUE"
    return tb * 1000 / 1001 if ntsc else tb


def _seconds(frames: float, rate: float) -> float:
    return frames / rate


def parse(xml_path: Path):
    """Returns (media_path: Path, kept: [(a, b) seconds in source time])."""
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    tag = root.tag.lower()

    if tag == "xmeml":
        return _parse_xmeml(root)
    if tag == "fcpxml":
        return _parse_fcpxml(root)
    raise ValueError(f"Unsupported XML edit list format: <{root.tag}>")


def _parse_xmeml(root):
    media = None
    for f in root.iter("file"):
        u = f.findtext("pathurl")
        if u:
            media = _url_to_path(u)
            break
    if media is None:
        raise ValueError("no <pathurl> in XML")

    rate = None
    clips = []
    for track in root.findall("./sequence/media/video/track"):
        for ci in track.findall("clipitem"):
            if rate is None:
                rate = _rate(ci)
            i, o = ci.findtext("in"), ci.findtext("out")
            if i is None or o is None:
                continue
            a, b = _seconds(float(i), rate), _seconds(float(o), rate)
            if b - a > 0.02:
                clips.append((a, b))
    if not clips:
        raise ValueError("no clipitems in XML")
    return media, _merge(clips)


def _parse_fcpxml(root):
    assets = {}
    for a in root.iter("asset"):
        src = a.get("src")
        if src:
            assets[a.get("id")] = (_url_to_path(src), a.get("format"))
    formats = {}
    for f in root.iter("format"):
        if f.get("id") and f.get("frameDuration"):
            m = re.match(r"(\d+)/(\d+)s", f["frameDuration"])
            if m:
                formats[f["id"]] = int(m.group(2)) / int(m.group(1))
    media = next((p for p, _ in assets.values()), None)
    if media is None:
        raise ValueError("no asset src in fcpxml")

    def frac(v):
        if v.endswith("s"):
            v = v[:-1]
        if "/" in v:
            n, d = v.split("/")
            return float(n) / float(d)
        return float(v)

    clips = []
    for ac in root.iter("asset-clip"):
        try:
            a, b = frac(ac.get("start")), frac(ac.get("start")) + frac(ac.get("duration"))
        except (TypeError, ZeroDivisionError):
            continue
        if b - a > 0.02:
            clips.append((a, b))
    if not clips:
        raise ValueError("no asset-clips in fcpxml")
    return media, _merge(clips)


def _merge(clips):
    clips.sort()
    out = []
    for a, b in clips:
        if out and a <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((round(a, 3), round(b, 3)))
    return out


def _url_to_path(u: str) -> Path:
    u = u.strip()
    if u.lower().startswith("file://"):
        u = urllib.parse.unquote(urllib.parse.urlparse(u).path)
        u = u.lstrip("/") if re.match(r"/[A-Za-z]:", u) else u
    return Path(urllib.parse.unquote(u))


def edges(kept):
    """All cut points (source time) — for snapping overlays onto cuts."""
    e = sorted({round(x, 3) for ab in kept for x in ab})
    return e


def snap(t: float, kept, max_dist: float = 1.0) -> float:
    """Nearest cut edge to t, if one is close enough."""
    best, bd = t, max_dist
    for e in edges(kept):
        if abs(e - t) < bd:
            best, bd = e, abs(e - t)
    return best


if __name__ == "__main__":
    import sys, json
    m, k = parse(Path(sys.argv[1]))
    print(m)
    print(json.dumps(k))
