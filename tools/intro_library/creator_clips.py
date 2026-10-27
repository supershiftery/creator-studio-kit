"""Clips of OTHER creators for intro lines that talk about them (ultimate dhgate free reselling spreadsheet 2026-10-23,
"when I say other creators, other videos in an intro, we should be having videos ... of them": the intro had shown the same
YouTube-search scroll at 2, 4 and 8 s). Works for any topic: reselling creators for reselling videos, Minecraft YouTubers
for "all these other YouTubers / a bunch of videos of this mod".

    clips = creator_clips(queries, topic_words, n=4)   # -> [{"src", "handle", "title"}], one per creator

1. YouTube search (yt-dlp, metadata only) names the creators who rank for the topic. YouTube itself blocks video downloads
   from this PC ("Sign in to confirm you're not a bot"); that wall is never worked around.
2. Each creator's TikTok (same name; creator_sources.json adds known handles per topic) gives the video: a public post whose
   caption matches the topic, downloaded with yt-dlp.
3. A 4 s piece from ~30 % in becomes a 1920x1080 card: the vertical video centred on a blurred copy of itself, "@handle"
   credit bottom-left. MUTED (B-roll never carries their audio). H.264, cached in _cache/creators/.
Never the user's own channels, never blacklisted ones (creator_sources.json "never").
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "creators")
SOURCES = os.path.join(HERE, "creator_sources.json")
FONT = "C\\:/Windows/Fonts/arialbd.ttf"
YTDLP = ["yt-dlp", "--no-warnings", "--quiet"]


def _say(m):
    print(m, file=sys.stderr, flush=True)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load():
    try:
        return json.load(open(SOURCES, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_own(name, cfg=None):
    """one of HIS channels (creator_sources.json own = exact, own_contains = any name containing it: {{REVIEW_CHANNEL}}, Agent
    {{REVIEW_CHANNEL}}, ... 2026-10-26). screenrec.py hides the same channels from a filmed YouTube / TikTok search."""
    cfg = cfg if cfg is not None else _load()
    n = _norm(name)
    return bool(n) and (n in {_norm(x) for x in cfg.get("own", [])} or any(_norm(c) in n for c in cfg.get("own_contains", [])))


def _lookup():
    """handle -> list of its recent videos (cached a day: creators post often, captions decide the topic)."""
    p = os.path.join(CACHE, "handles.json")
    try:
        return p, json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return p, {}


def youtube_creators(queries, per=10):
    """Channel names that rank for the queries, most-viewed first (metadata only, no video)."""
    seen = {}
    for q in queries:
        r = subprocess.run(YTDLP + [f"ytsearch{per}:{q}", "--flat-playlist", "--print", "%(channel)s\t%(view_count)s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        for row in r.stdout.splitlines():
            name, _, views = row.partition("\t")
            if name and name != "NA":
                seen[name] = max(seen.get(name, 0), int(views) if views.isdigit() else 0)
    return [n for n, _ in sorted(seen.items(), key=lambda x: -x[1])]


def web_tiktok_handles(queries):
    """TikTok creators for the topic from DuckDuckGo's plain HTML results (tiktok.com/@handle links): YouTube channel names
    often aren't the TikTok handle. (Bing in headless Chromium returned no results, 2026-10-23.)"""
    import urllib.parse
    import urllib.request
    found = []
    for q in queries:
        req = urllib.request.Request("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(f"site:tiktok.com {q}"),
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"})
        try:
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception as e:
            _say(f"creators: web search failed for {q!r} ({e})")
            continue
        for a, b in re.findall(r"tiktok\.com(?:/|%2F)%40([A-Za-z0-9_.]{2,30})|tiktok\.com/@([A-Za-z0-9_.]{2,30})", html):
            h = (a or b).lower().rstrip(".")
            if h not in found:
                found.append(h)
    return found


def _has_video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def tiktok_videos(handle, cache, n=12):
    import time
    hit = cache.get(handle)
    if hit and time.time() - hit.get("at", 0) < 86400:
        return hit["videos"]
    r = subprocess.run(YTDLP + [f"https://www.tiktok.com/@{handle}", "--flat-playlist", "--playlist-end", str(n),
                                "--print", "%(id)s\t%(uploader)s\t%(duration)s\t%(title)s"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    vids = []
    for row in r.stdout.splitlines():
        parts = row.split("\t", 3)
        if len(parts) == 4 and parts[0].isdigit():
            vids.append({"id": parts[0], "uploader": parts[1], "dur": float(parts[2]) if parts[2] not in ("NA", "") else 0,
                         "title": parts[3]})
    cache[handle] = {"at": time.time(), "videos": vids}
    return vids


def _card(src, out, t, handle, seconds):
    vf = (f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:3,eq=brightness=-0.25[bg];"
          f"[0:v]scale=-2:1000,pad=iw+12:ih+12:6:6:white[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
          f"drawtext=fontfile='{FONT}':text='@{handle}':fontsize=44:fontcolor=white:borderw=3:bordercolor=black@0.8:x=60:y=H-100,"
          f"fps=30,format=yuv420p[v]")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-t", f"{seconds}", "-i", src, "-filter_complex", vf,
                        "-map", "[v]", "-an", "-c:v", "libx264", "-profile:v", "high", "-crf", "18", "-preset", "fast", out],
                       capture_output=True, text=True)
    if r.returncode and os.path.exists(out):
        os.remove(out)   # never leave a half-written card in the cache
    return not r.returncode and os.path.exists(out)


def triptych(clips, seconds=4.0):
    """Three portrait creator clips side by side in one 16:9 frame, popping in left to right, each with its @handle (user
    2026-10-23: "TikTok is portrait and our video is landscape ... add a few of them, like maybe three"). Background = the
    middle clip blurred. Returns the mp4 path or None."""
    if len(clips) < 3:
        return None
    clips = clips[:3]
    out = os.path.join(CACHE, "trip-" + hashlib.sha1(("v1|" + "|".join(f"{c['raw']}@{c['t']:.2f}" for c in clips)
                                                      + f"|{seconds}").encode()).hexdigest()[:12] + ".mp4")
    if os.path.exists(out):
        return out
    W, H, G = 540, 960, 60                   # 9:16 panels, 60 px gaps: 3*540 + 4*60 = 1860
    args = ["ffmpeg", "-v", "error", "-y"]
    for c in clips:
        args += ["-ss", f"{c['t']:.2f}", "-t", f"{seconds}", "-i", c["raw"]]
    fc = [f"[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:3,eq=brightness=-0.3,fps=30[bg]"]
    last = "bg"
    for k, c in enumerate(clips):
        fc.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
                  f"drawtext=fontfile='{FONT}':text='@{c['handle']}':fontsize=34:fontcolor=white:borderw=3:"
                  f"bordercolor=black@0.8:x=24:y=h-70,pad={W + 10}:{H + 10}:5:5:white[p{k}]")
        x = G + k * (W + G) + (1920 - (3 * W + 4 * G)) // 2 - 5
        fc.append(f"[{last}][p{k}]overlay=x={x}:y={(1080 - H) // 2 - 5}:enable='gte(t,{0.15 * k:.2f})'[o{k}]")
        last = f"o{k}"
    args += ["-filter_complex", ";".join(fc) + f";[{last}]format=yuv420p[v]", "-map", "[v]", "-t", f"{seconds}", "-an",
             "-c:v", "libx264", "-profile:v", "high", "-crf", "18", "-preset", "fast", out]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        _say(f"creators: triptych failed ({r.stderr[-200:]})")
        return None
    return out


YEAR_RE = re.compile(r"\b(19|20)\d\d\b|\b(january|february|march|april|june|july|august|september|october|november|december)\b", re.I)


def has_date(raw, t, seconds):
    """A year or month burned into the clip ("POV: Reselling in 2024" on @dkreps24's TikTok, reselling spreadsheet intro
    2026-10-23, no dates on screen ever): Windows OCR on three frames of the moment used. True = don't use it."""
    try:
        sys.path.insert(0, r"{{KIT}}/tools")
        import cv2
        import privacy_ocr
    except Exception:
        return False
    for dt in (0.3, seconds / 2, seconds - 0.3):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + dt:.2f}", "-i", raw, "-frames:v", "1", "-vf", "scale=-2:1280",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if not r.stdout:
            continue
        import numpy as np
        img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
        if img is not None and any(YEAR_RE.search(txt) for txt, _ in privacy_ocr.ocr(img)):
            return True
    return False


def youtube_clips(queries, need, n=3, seconds=3.0, exclude=()):
    """Real YouTube videos ABOUT the product, a muted piece of each, full frame with an "@channel" credit (remote test prada 2
    2026-10-26, 0:17: "we wanna use actual influencers ... grab videos from YouTube that we could've played right there for
    Prada sunglasses"). Section downloads work again (2026-10-26). Every `need` group must be named in the video title
    ("prada" AND "sunglass/glasses/shade"); one video per channel; never his own channels; a date on screen = skipped."""
    os.makedirs(CACHE, exist_ok=True)
    cfg = _load()
    never = {_norm(x) for x in cfg.get("never", [])} | {_norm(x) for x in cfg.get("own", [])} | {_norm(x) for x in exclude}
    rows = []
    for q in queries:
        r = subprocess.run(YTDLP + [f"ytsearch12:{q}", "--flat-playlist", "--print", "%(id)s\t%(duration)s\t%(channel)s\t%(title)s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        rows += [row.split("\t", 3) for row in r.stdout.splitlines() if row.count("\t") >= 3]
    out, chans = [], set()
    for vid, dur, chan, title in rows:
        if len(out) >= n:
            break
        d = float(dur) if dur.replace(".", "", 1).isdigit() else 0
        if not (30 <= d <= 1500) or _norm(chan) in never or is_own(chan, cfg) or _norm(chan) in chans or not chan or chan == "NA":
            continue
        if not all(any(x in title.lower() for x in grp) for grp in need):
            continue
        t = max(8.0, d * 0.3)
        raw = os.path.join(CACHE, f"yt-{vid}-{int(t)}.mp4")
        if not os.path.exists(raw):
            r = subprocess.run(YTDLP + ["-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]", "--download-sections",
                                        f"*{t:.1f}-{t + seconds + 1:.1f}", "-o", raw, f"https://www.youtube.com/watch?v={vid}"],
                               capture_output=True, text=True, errors="replace", timeout=240)
            if r.returncode or not os.path.exists(raw) or not _has_video(raw):
                _say(f"creators: YouTube {vid} ({chan}) download failed ({(r.stderr or '')[-120:].strip()})")
                continue
        if has_date(raw, 0.2, seconds):
            _say(f"creators: YouTube {chan} skipped, a year/month is on screen")
            continue
        handle = re.sub(r"\s+", "", chan)
        card = os.path.join(CACHE, f"ytcard-{hashlib.sha1(f'v1|{vid}|{t:.1f}|{seconds}'.encode()).hexdigest()[:12]}.mp4")
        if not os.path.exists(card):
            vf = (f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                  f"drawtext=fontfile='{FONT}':text='@{handle}':fontsize=44:fontcolor=white:borderw=3:bordercolor=black@0.8:x=60:y=H-100,"
                  f"fps=30,format=yuv420p")
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.2", "-t", f"{seconds}", "-i", raw, "-vf", vf, "-an",
                                "-c:v", "libx264", "-profile:v", "high", "-crf", "18", "-preset", "fast", card], capture_output=True, text=True)
            if r.returncode or not os.path.exists(card):
                if os.path.exists(card):
                    os.remove(card)
                continue
        chans.add(_norm(chan))
        out.append({"src": card, "raw": raw, "t": 0.2, "handle": handle, "title": title[:80]})
        _say(f"creators: YouTube @{handle} - {title[:60]!r}")
    return out


def creator_clips(queries, topic_words, n=4, seconds=4.0, exclude=(), need=()):
    """Up to n clips, each from a DIFFERENT creator, whose post caption names the topic (and one word of every `need` group)."""
    os.makedirs(CACHE, exist_ok=True)
    cfg = _load()
    never = {_norm(x) for x in cfg.get("never", [])} | {_norm(x) for x in cfg.get("own", [])} | {_norm(x) for x in exclude}
    topic = [w.lower() for w in topic_words if w]
    handles = []
    for key, hs in cfg.get("topics", {}).items():
        if any(key in w or w in key for w in topic):
            handles += hs
    try:
        names = youtube_creators(queries)
    except Exception as e:
        _say(f"creators: YouTube search failed ({e})")
        names = []
    # TikTok creators a web search finds for the topic first (real handles), then YouTube channel names without spaces
    # ("Kasper Resells" -> @kasperresells), which often aren't the handle
    handles += web_tiktok_handles(queries[:2])
    handles += [_norm(x) for x in names]
    handles = [h for h in dict.fromkeys(handles) if h and _norm(h) not in never and not is_own(h, cfg)]
    path, cache = _lookup()
    out, tries = [], 0
    for h in handles:
        if len(out) >= n or tries >= 30:
            break
        tries += 1
        try:
            vids = tiktok_videos(h, cache)
        except Exception as e:
            _say(f"creators: @{h} lookup failed ({e})")
            continue
        # the post has to be about the topic (Ace Movez's TikTok is "#emoney", not reselling): caption words decide
        on = [v for v in vids if v["dur"] >= 7 and any(w in v["title"].lower() for w in topic) and not YEAR_RE.search(v["title"])
              and all(any(x in v["title"].lower() for x in grp) for grp in need)]
        v = None
        for cand in on[:3]:   # photo slideshows come down as audio only: try the creator's next on-topic post
            raw = os.path.join(CACHE, f"{cand['id']}.mp4")
            if not os.path.exists(raw):
                r = subprocess.run(YTDLP + [f"https://www.tiktok.com/@{h}/video/{cand['id']}", "-o", raw],
                                   capture_output=True, text=True, errors="replace", timeout=180)
                if r.returncode or not os.path.exists(raw):
                    _say(f"creators: @{h} download failed ({r.stderr[-120:].strip()})")
                    continue
            if _has_video(raw):
                v = cand
                break
        if not v:
            continue
        t = max(1.0, min(v["dur"] * 0.3, v["dur"] - seconds - 0.5))
        if has_date(raw, t, seconds):
            _say(f"creators: @{h} skipped, a year/month is on screen")
            continue
        card = os.path.join(CACHE, f"card-{hashlib.sha1(f'v1|{v['id']}|{t:.2f}|{seconds}|{h}'.encode()).hexdigest()[:12]}.mp4")
        if not os.path.exists(card) and not _card(raw, card, t, h, seconds):
            _say(f"creators: @{h} card failed")
            continue
        out.append({"src": card, "raw": raw, "t": t, "handle": h, "title": v["title"][:80]})
        _say(f"creators: @{h} - {v['title'][:60]!r}")
    json.dump(cache, open(path, "w", encoding="utf-8"))
    return out


if __name__ == "__main__":
    print(json.dumps(creator_clips(sys.argv[1].split("|"), sys.argv[2].split(","), n=int(sys.argv[3]) if len(sys.argv) > 3 else 4), indent=1))
