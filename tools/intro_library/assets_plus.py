"""More kinds of intro source (2026-10-25, "some intros just fall short ... we need different assets ... TikToks, articles,
YouTube videos ... stock images"; INTRO_RULES.md asset mix: 4+ kinds per intro, his product <= 50%). Each function makes a
4 s 1920x1080 H.264 clip that MOVES (sub-pixel affine glide drawn per frame, never zoompan), cached in _cache/plus/:

    thumb_wall(queries, seconds=4.0, fps=60)       -> real YouTube thumbnails of the topic in a gliding wall
    comment_scroll(video, keywords, seconds=4.0)   -> real comments of one of HIS videos scrolling, the best match lit
    city_map(name, seconds=4.0)                    -> OpenStreetMap of a city he names, push-in to a pin + the name

Rules baked in: no dates/years (titles never drawn; thumbnails with a year in them are OCR-dropped), no emojis (stripped),
no usernames or avatars (blurred bars / plain circles), never his own channels or the "never" list (creator_sources.json),
city level only on maps (never an address), "(c) OpenStreetMap contributors" credit on the map (licence).
Reddit was tried: it blocks scripted requests here, so it is not a source (do not work around it).
CLI test:  python assets_plus.py wall "how to start reselling" | comments RxG43OY79A4 link,spreadsheet | map Atlanta
"""
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "plus")
UA = "StudioStudio-intro/1.0 (personal video tool; contact via YouTube)"
YTDLP = ["yt-dlp", "--no-warnings", "--quiet"]
W, H = 1920, 1080
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b|\b(jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d", re.I)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0001F1E6-\U0001F1FF\u200d]+")
BOLD = r"C:\Windows\Fonts\arialbd.ttf"
REG = r"C:\Windows\Fonts\arial.ttf"


def _say(m):
    print("[assets_plus]", m, file=sys.stderr)


def _key(*a):
    return hashlib.md5("|".join(map(str, a)).encode()).hexdigest()[:10]


def _get(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return r.read()


def _never():
    try:
        j = json.load(open(os.path.join(HERE, "creator_sources.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    out = set()
    for k in ("never", "own"):
        v = j.get(k) or []
        out |= {str(x).lower().lstrip("@") for x in (v if isinstance(v, list) else v.keys())}
    return out


def _has_year(img):
    """Windows OCR (privacy_ocr) on a PIL image: True = a year/month is printed on it."""
    try:
        sys.path.insert(0, r"{{KIT}}/tools")
        import cv2
        import numpy as np
        import privacy_ocr
        arr = cv2.cvtColor(np.array(img.convert("RGB").resize((img.width * 2, img.height * 2))), cv2.COLOR_RGB2BGR)
        return any(YEAR_RE.search(t) for t, _ in privacy_ocr.ocr(arr))
    except Exception as ex:   # OCR missing: keep the picture (titles are never drawn anyway)
        _say(f"ocr unavailable ({ex})")
        return False


def _encode(frames, out, fps):
    """Pipe PIL frames into a 1920x1080 H.264 High yuv420p file (CPU encoder: never collides with Studio's GPU queue)."""
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    return out if p.returncode == 0 and os.path.exists(out) else None


def _glide(canvas, t, z0, z1, c0, c1):
    """Sub-pixel camera on a big canvas: zoom z0->z1 and centre c0->c1 (canvas px), smoothstep eased. One affine
    resample per frame with bicubic filtering, so there is no whole-pixel stepping (on-time-broll-pops round 3)."""
    e = t * t * (3 - 2 * t)
    z = z0 + (z1 - z0) * e
    cx, cy = c0[0] + (c1[0] - c0[0]) * e, c0[1] + (c1[1] - c0[1]) * e
    s = 1 / z
    return canvas.transform((W, H), Image.AFFINE, (s, 0, cx - W / 2 * s, 0, s, cy - H / 2 * s), resample=Image.BICUBIC)


# ---------------------------------------------------------------- YouTube thumbnail wall
def _search(q, n):
    """(id, channel) of results whose TITLE has no year/month: the thumbnail usually repeats the title, and Windows OCR
    missed the stylised "Start reselling in 2026!" on the first test wall."""
    r = subprocess.run(YTDLP + [f"ytsearch{n}:{q}", "--flat-playlist", "--print", "%(id)s\t%(channel)s\t%(title)s"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
    rows = [row.split("\t") for row in r.stdout.splitlines() if row.count("\t") >= 2]
    return [(v, c) for v, c, t in rows if not YEAR_RE.search(t) and not re.search(r"\b20\d\d\b", t)]


def _thumb(vid):
    d = os.path.join(CACHE, "thumbs")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, vid + ".jpg")
    if not os.path.exists(p):
        for name in ("maxresdefault", "hq720", "hqdefault"):
            try:
                b = _get(f"https://i.ytimg.com/vi/{vid}/{name}.jpg")
            except Exception:
                continue
            im = Image.open(io.BytesIO(b)).convert("RGB")
            if im.width / im.height < 1.5:   # 4:3 letterboxed hqdefault -> its 16:9 middle
                h = im.width * 9 // 16
                im = im.crop((0, (im.height - h) // 2, im.width, (im.height - h) // 2 + h))
            im.resize((640, 360), Image.LANCZOS).save(p, quality=92)
            break
    return Image.open(p) if os.path.exists(p) else None


def thumb_wall(queries, seconds=4.0, fps=60, n=15, exclude=(), light=None):
    """Real thumbnails of what ranks for the topic, a 5x3+ wall gliding diagonally (one shot, ~1 kind of source).
    light = index of a tile to outline in the second half (the one the line is about), or None."""
    if isinstance(queries, str):
        queries = [queries]
    out = os.path.join(CACHE, f"wall_{_key(queries, seconds, fps, n, light)}.mp4")
    if os.path.exists(out):
        return out
    os.makedirs(CACHE, exist_ok=True)
    never, ex = _never(), set(exclude)
    ids = []
    for q in queries:
        for vid, ch in _search(q, n * 3):   # most reselling titles carry a year, so search wide
            # his own channels never sit in a wall about OTHER creators: "{{PHONE_CHANNEL}}" -> "studioreviews" contains
            # the listed "studio" (an exact-name check let it through)
            cn = re.sub(r"[^a-z0-9]", "", ch.lower())
            if vid not in ids and vid not in ex and not any(x and x in cn for x in never) and "blocked-channel-example" not in cn and "{{REVIEW_CHANNEL}}" not in cn:
                ids.append(vid)
    tiles = []
    for vid in ids:
        im = _thumb(vid)
        if im is None or _has_year(im):
            continue
        tiles.append(im)
        if len(tiles) >= n:
            break
    if len(tiles) < 8:
        _say(f"only {len(tiles)} usable thumbnails")
        return None
    cols, tw, th, gap = 5, 640, 360, 28
    rows = math.ceil(len(tiles) / cols)
    cw, ch = cols * tw + (cols + 1) * gap, rows * th + (rows + 1) * gap
    canvas = Image.new("RGB", (cw, ch), (14, 15, 18))
    d = ImageDraw.Draw(canvas)
    for i, im in enumerate(tiles):
        x, y = gap + (i % cols) * (tw + gap) + (tw // 2 if (i // cols) % 2 else 0) - tw // 4, gap + (i // cols) * (th + gap)
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw - 1, th - 1), 18, fill=255)
        canvas.paste(im, (x, y), mask)
    base = canvas.copy()
    z = max(W / cw, H / ch) * 1.35
    if light == "auto":   # the tile the camera ends on (an index could light a tile half off-screen)
        ex, ey = cw * 0.6, ch * 0.56
        pos = lambda i: (gap + (i % cols) * (tw + gap) + (tw // 2 if (i // cols) % 2 else 0) - tw // 4 + tw / 2,
                         gap + (i // cols) * (th + gap) + th / 2)
        light = min(range(len(tiles)), key=lambda i: (pos(i)[0] - ex) ** 2 + (pos(i)[1] - ey) ** 2)
    frames = []
    N = int(seconds * fps)
    for f in range(N):
        t = f / (N - 1)
        img = base
        if light is not None and t > 0.45 and light < len(tiles):
            img = base.copy()
            i = light
            x, y = gap + (i % cols) * (tw + gap) + (tw // 2 if (i // cols) % 2 else 0) - tw // 4, gap + (i // cols) * (th + gap)
            ImageDraw.Draw(img).rounded_rectangle((x - 8, y - 8, x + tw + 8, y + th + 8), 24, outline=(255, 214, 64),
                                                  width=int(6 + 4 * min(1, (t - 0.45) * 6)))
        frames.append(_glide(img, t, z, z * 1.08, (cw * 0.38, ch * 0.42), (cw * 0.6, ch * 0.56)))
    return _encode(frames, out, fps)


# ---------------------------------------------------------------- real comments of HIS video
def _comments(video, n=60):
    vid = video.split("v=")[-1][:11] if "youtu" in video else video
    p = os.path.join(CACHE, f"comments_{vid}.json")
    if not os.path.exists(p):
        os.makedirs(CACHE, exist_ok=True)
        tmp = os.path.join(CACHE, f"c_{vid}")
        subprocess.run(["yt-dlp", "--no-warnings", "--quiet", "--skip-download", "--write-comments", "--extractor-args",
                        f"youtube:max_comments={n},all,0;comment_sort=top", "-o", tmp + ".%(ext)s",
                        f"https://www.youtube.com/watch?v={vid}"], timeout=240)
        try:
            j = json.load(open(tmp + ".info.json", encoding="utf-8"))
        except (OSError, ValueError):
            return []
        keep = [{"text": c.get("text", ""), "likes": c.get("like_count") or 0} for c in j.get("comments", []) if c.get("parent") == "root"]
        json.dump(keep, open(p, "w", encoding="utf-8"))
        os.remove(tmp + ".info.json")
    return json.load(open(p, encoding="utf-8"))


SPAM_RE = re.compile(r"upwork|editor|hire|my channel|sub ?4 ?sub|whatsapp|telegram|http|www\.|\.com", re.I)
# his own intro must never show a viewer calling it fake / a scam, or swearing (first test: "ts is str8 up scamming")
NEG_RE = re.compile(r"\b(scam\w*|fake|fraud|lie|lying|liar|trash|garbage|worst|clickbait|bs|mf|wtf|fuck\w*|shit\w*|damn|"
                    r"bitch\w*|ass|hate|stupid|dumb|empty link|broken|doesn'?t work|not working|dead link)\b", re.I)
POS_RE = re.compile(r"\b(thank\w*|thx|love|helped|help(s|ful)?|legit|great|goat|fire|best|appreciate\w*|amazing|awesome|"
                    r"keep it up|w video|underrated|real one|valuable|game ?changer|life ?saver)\b", re.I)
ASK_RE = re.compile(r"\b(can you|could you|please|pls|do a video|make a video|review the|next video|part 2)\b", re.I)
COMPLAINT_RE = re.compile(r"\b(not in|no link|wrong|\bai\b|eyes|ship to|don'?t ship|refund|never arrived|still waiting|where is my)\b|\?\s*ai", re.I)


def _wrap(d, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if d.textlength(nxt, font=font) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    return lines + ([cur] if cur else [])


def comment_scroll(video, keywords=(), seconds=4.0, fps=60, n=6):
    """His viewers' real top comments (no names, no avatars, no emojis, no dates, no spam) scrolling up on a dark
    YouTube-style panel; the comment that best matches the line's keywords is outlined as it reaches the middle."""
    kws = [k.lower() for k in keywords]
    out = os.path.join(CACHE, f"comments_{_key(video, kws, seconds, fps, n)}.mp4")
    if os.path.exists(out):
        return out
    cs = []
    for c in _comments(video):
        t = re.sub(r"\s+", " ", EMOJI_RE.sub("", c["text"])).strip()
        if not (12 <= len(t) <= 150) or SPAM_RE.search(t) or NEG_RE.search(t) or YEAR_RE.search(t) or "@" in t:
            continue
        # only praise or a request for a video; complaints ("the links not in the spreadsheet") and jabs ("AI?") stay out
        pos, ask = bool(POS_RE.search(t)), bool(ASK_RE.search(t))
        if (pos or ask) and not COMPLAINT_RE.search(t):
            cs.append({"text": t, "likes": c["likes"], "hit": sum(k in t.lower() for k in kws) + ask})
    if len(cs) < 3:
        _say("not enough usable comments")
        return None
    best = max(cs, key=lambda c: (c["hit"], c["likes"]))
    others = [c for c in sorted(cs, key=lambda c: -c["likes"]) if c is not best][: n - 1]
    pick = others[: len(others) // 2] + [best] + others[len(others) // 2:]
    f_txt, f_meta = ImageFont.truetype(BOLD, 52), ImageFont.truetype(REG, 36)
    pw = 1760
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    blocks = [(c, _wrap(tmp, c["text"], f_txt, pw - 260)) for c in pick]
    ch = 120 + sum(110 + 58 * len(ls) for _, ls in blocks) + 120
    panel = Image.new("RGB", (pw, ch), (24, 24, 27))
    d = ImageDraw.Draw(panel)
    y, best_box = 100, None
    for c, ls in blocks:
        hue = int(_key(c["text"]), 16) % 360
        col = tuple(int(90 + 60 * math.cos(math.radians(hue + k * 120))) for k in range(3))
        d.ellipse((60, y, 160, y + 100), fill=col)
        bar = Image.new("RGBA", (300, 40), (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle((0, 0, 299, 39), 14, fill=(120, 120, 128, 255))
        panel.paste(bar.filter(ImageFilter.GaussianBlur(6)), (200, y + 4), bar.filter(ImageFilter.GaussianBlur(6)))
        for k, ln in enumerate(ls):
            d.text((200, y + 62 + 58 * k), ln, font=f_txt, fill=(241, 241, 241))
        yb = y + 62 + 58 * len(ls) + 10
        d.text((200, yb), f"\u25B2 {c['likes']}" if c["likes"] else "\u25B2", font=f_meta, fill=(170, 170, 176))
        if c is best:
            best_box = (30, y - 30, pw - 30, yb + 56)
        y = yb + 90
    bg = Image.new("RGB", (W, max(ch, H)), (12, 12, 14))
    bg.paste(panel, ((W - pw) // 2, 0))
    frames, N = [], int(seconds * fps)
    mid = (best_box[1] + best_box[3]) / 2
    for f in range(N):
        t = f / (N - 1)
        img = bg
        if t > 0.4:
            img = bg.copy()
            bx = (best_box[0] + (W - pw) // 2, best_box[1], best_box[2] + (W - pw) // 2, best_box[3])
            ImageDraw.Draw(img).rounded_rectangle(bx, 26, outline=(255, 214, 64), width=int(4 + 4 * min(1, (t - 0.4) * 5)))
        cy = max(H / 2, mid - 260) + (min(mid + 20, bg.height - H / 2) - max(H / 2, mid - 260)) * t
        frames.append(_glide(img, t, 1.0, 1.06, (W / 2, cy if t == 0 else cy), (W / 2, cy)))
    return _encode(frames, out, fps)


# ---------------------------------------------------------------- map of a city he names
def geocode(name, near=None):
    """A real city/town (Nominatim) or None. near = (lat, lon) of a city named earlier in the same VO: the search prefers
    places within ~2 degrees ("Atlanta, Decatur, Dunwoody" -> Decatur, Georgia, not Decatur, Illinois)."""
    q = {"q": name, "format": "json", "limit": 1, "featuretype": "city"}
    if near:
        q.update(viewbox=f"{near[1] - 2},{near[0] + 2},{near[1] + 2},{near[0] - 2}", bounded=1)
    try:
        hits = json.loads(_get("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(q)))
        if not hits and near:
            return geocode(name)
        hit = hits[0]
    except Exception as ex:
        _say(f"geocode failed for {name}: {ex}")
        return None
    # a real city / town only ("This" is a French village; a loose regex must not map somewhere random)
    kind, imp = hit.get("addresstype"), float(hit.get("importance") or 0)
    if not ((kind in ("city", "town", "municipality", "borough", "suburb") and imp >= 0.4) or (kind == "administrative" and imp >= 0.6)):
        _say(f"{name}: not a city ({kind}, importance {imp:.2f})")
        return None
    return float(hit["lat"]), float(hit["lon"])


def city_map(name, seconds=4.0, fps=60, zoom=11, near=None):
    """OpenStreetMap tiles around the city, slow push-in to a pin with the city name. City level only."""
    out = os.path.join(CACHE, f"map_{_key(name, seconds, fps, zoom, near)}.mp4")
    if os.path.exists(out):
        return out
    os.makedirs(os.path.join(CACHE, "tiles"), exist_ok=True)
    ll = geocode(name, near)
    if not ll:
        return None
    lat, lon = ll
    n = 2 ** zoom
    fx, fy = (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    tx, ty, cols, rows = int(fx) - 4, int(fy) - 3, 9, 7
    canvas = Image.new("RGB", (cols * 256, rows * 256), (230, 230, 230))
    for i in range(cols):
        for j in range(rows):
            p = os.path.join(CACHE, "tiles", f"{zoom}_{tx + i}_{ty + j}.png")
            if not os.path.exists(p):
                try:
                    open(p, "wb").write(_get(f"https://tile.openstreetmap.org/{zoom}/{tx + i}/{ty + j}.png"))
                except Exception:
                    continue
            canvas.paste(Image.open(p).convert("RGB"), (i * 256, j * 256))
    px, py = (fx - tx) * 256, (fy - ty) * 256
    # soften the map so the pin + name read first (still clearly a real map)
    canvas = Image.blend(canvas, Image.new("RGB", canvas.size, (18, 22, 30)), 0.18)
    f_city, f_cr = ImageFont.truetype(BOLD, 64), ImageFont.truetype(REG, 22)
    label = name.split(",")[0].upper()
    frames, N = [], int(seconds * fps)
    for f in range(N):
        t = f / (N - 1)
        img = canvas.copy()
        d = ImageDraw.Draw(img)
        r = 16 + 70 * ((t * 1.6) % 1)   # ring pulse
        a = int(255 * (1 - (t * 1.6) % 1))
        ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((px - r, py - r, px + r, py + r), outline=(232, 64, 60, a), width=6)
        img.paste(ring, (0, 0), ring)
        d.ellipse((px - 16, py - 16, px + 16, py + 16), fill=(232, 64, 60), outline=(255, 255, 255), width=5)
        if t > 0.15:
            k = min(1, (t - 0.15) * 5)
            tw = d.textlength(label, font=f_city)
            box = (px + 34, py - 50, px + 34 + tw + 48, py + 34)
            d.rounded_rectangle(box, 14, fill=(16, 18, 24))
            d.text((px + 58, py - 44 + (1 - k) * 12), label, font=f_city, fill=(255, 255, 255))
        fr = _glide(img, t, 1.15, 1.45, (px + 120, py + 40), (px + 150, py))
        ImageDraw.Draw(fr).text((W - 330, H - 40), "\u00A9 OpenStreetMap contributors", font=f_cr, fill=(60, 60, 60))
        frames.append(fr)
    return _encode(frames, out, fps)


# ---------------------------------------------------------------- which VO lines get which extra (shared by review + phone)
WALL_RE = re.compile(r"\b(every ?(?:one|body)(?: is| and their)?|all over (?:youtube|tik ?tok|the internet)|so many (?:videos|people)|"
                     r"a lot of people|people are (?:making|doing|talking|selling)|trending|blowing up|hottest|booming)\b", re.I)
COMMENT_RE = re.compile(r"\b(you guys (?:have been |keep |)(?:asked|asking|requested|wanted|begging)|in the comments|"
                        r"a lot of you|many of you|so many of you|you all asked|requested)\b", re.I)
CITY_RE = re.compile(r"\b(?:in|from|out of|around|to|of|like|even|near|the) ([A-Z][a-z]{2,}(?:[ -](?!So\b|And\b|But\b|The\b|I\b)[A-Z][a-z]{2,})?)(?=[\s,.!?]|$)")
NOT_CITY = {"Today", "DHgate", "Dhgate", "China", "America", "YouTube", "Amazon", "Google", "Spring", "Winter", "Summer", "Fall",
            "Christmas", "Black", "Friday", "{{REVIEW_CHANNEL}}", "Studio", "This", "That", "These", "Those", "There", "Here", "Them",
            "Now", "Then", "What", "Which", "Our", "Your", "My", "His", "Her", "Their", "All", "One", "Every", "Some",
            "Uber", "Eats", "DoorDash", "Shein", "Temu", "Chime", "Grubhub", "Instacart"}
FILLER = set("ultimate free best top the a an my your new full complete guide review reviews honest spreadsheet list "
             "video videos how to for and of on in with promo code codes coupon coupons".split())


def his_video(channel, topic):
    """His most-viewed recent upload on that channel whose title shares a topic word (the comment source)."""
    handle = re.sub(r"[^A-Za-z0-9]", "", channel or "")
    if not handle:
        return None
    r = subprocess.run(YTDLP + ["--flat-playlist", "--playlist-end", "30", "--print", "%(id)s\t%(view_count)s\t%(title)s",
                                f"https://www.youtube.com/@{handle}/videos"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
    rows = [x.split("\t") for x in r.stdout.splitlines() if x.count("\t") >= 2]
    views = lambda v: int(v) if v.isdigit() else 0
    hit = [x for x in rows if any(w in x[2].lower() for w in topic)]
    return max(hit or rows, key=lambda x: views(x[1]))[0] if rows else None


CREATOR_WORDS_RE = re.compile(r"\b(content creators?|creators?|youtubers?|influencers?|tik ?tokers?|gurus?|gatekeep\w*)\b", re.I)


def plus_footage(vo_text, title, channel="", say=_say, creators=False):
    """footage.json entries ({src, t, tag, kind, for, ...}) for the VO's lines: thumbnail wall, comments, city maps.
    creators=True (phone: no TikTok creator clips there) also puts the wall on "content creators are gatekeeping" lines
    (Shein: the wall of other creators' Shein promo-code videos IS those creators). Never raises."""
    if not vo_text:
        return []
    core = [w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if w not in FILLER and not w.isdigit()]
    out = []
    try:
        words = sorted({m.group(0).lower() for m in WALL_RE.finditer(vo_text)} |
                       ({m.group(0).lower() for m in CREATOR_WORDS_RE.finditer(vo_text)} if creators else set()))
        # the wall searches the WHOLE topic phrase ("uber eats promo codes"): "uber eats" alone filled it with driver vlogs
        topic = " ".join(w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if not w.isdigit() and w not in
                         {"best", "top", "ultimate", "free", "new", "my", "the", "a", "an", "honest", "full", "complete"})
        if words and topic:
            mp4 = thumb_wall([topic, topic + " explained"])
            if mp4:
                out.append({"src": mp4, "t": 0.0, "tag": "youtube thumbnails: " + " ".join(core), "kind": "broll",
                            "no_stab": True, "for": words, "roles": ["hook", "problem"]})
        words = sorted({m.group(0).lower() for m in COMMENT_RE.finditer(vo_text)})
        if words and channel:
            vid = his_video(channel, core)
            mp4 = comment_scroll(vid, core + ["thank", "review", "video"]) if vid else None
            if mp4:
                out.append({"src": mp4, "t": 0.0, "tag": f"viewer comments: {vid}", "kind": "broll", "no_stab": True,
                            "for": words, "own_page": True})
        near = None
        for city in dict.fromkeys(m.group(1) for m in CITY_RE.finditer(vo_text)):
            if city in NOT_CITY or city.lower() in core or len(out) >= 4:
                continue
            ll = geocode(city, near)
            near = near or ll
            mp4 = city_map(city, near=near if near != ll else None) if ll else None
            if mp4:
                out.append({"src": mp4, "t": 0.0, "tag": f"map: {city}", "kind": "broll", "no_stab": True, "for": [city.lower()]})
    except Exception as e:
        say(f"intro: extra sources failed ({e})")
    if out:
        say("intro: extra sources " + ", ".join(f["tag"] for f in out))
    return out


if __name__ == "__main__":
    kind, arg = sys.argv[1], sys.argv[2]
    if kind == "wall":
        print(thumb_wall([arg], light=7))
    elif kind == "comments":
        print(comment_scroll(arg, (sys.argv[3].split(",") if len(sys.argv) > 3 else ())))
    elif kind == "map":
        print(city_map(arg))
