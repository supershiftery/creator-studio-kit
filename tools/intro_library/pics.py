"""Real pictures for the real things a VO names (stores, cars, brands, products), so each line can show the literal thing.

Source: Wikimedia Commons (free licences; the credit is kept in pics.json next to the picture so it can go in the
YouTube description). Picture downloads for edits are allowed without asking (memory: picture-downloads-ok).
A per-video override list (beats.json: [{"match": "neiman marcus", "query": "...", "file": "local.jpg", "kind": "photo|logo"}])
wins over automatic search. Logos are used for brand pops, photos for places/objects.
"""
import hashlib, json, os, re, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "pics")
UA = "StudioIntroLibrary/1.0 (personal video editing; contact [EMAIL])"

# how to search for a thing the VO names: places want the storefront, brands want the logo
HINTS = {
    "neiman marcus": ("Neiman Marcus store", "photo"), "nordstrom": ("Nordstrom store", "photo"), "saks": ("Saks Fifth Avenue store", "photo"),
    "honda civic": ("Honda Civic", "photo"), "civic": ("Honda Civic", "photo"), "rolex": ("Rolex watch", "photo"), "airpods": ("AirPods", "photo"),
    "moncler": ("Moncler logo", "logo"), "palm angels": ("Palm Angels logo", "logo"), "north face": ("The North Face logo", "logo"),
    "ksubi": ("Ksubi logo", "logo"), "chrome hearts": ("Chrome Hearts logo", "logo"), "louis vuitton": ("Louis Vuitton logo", "logo"),
    "gucci": ("Gucci logo", "logo"), "prada": ("Prada logo", "logo"), "dior": ("Dior logo", "logo"), "balenciaga": ("Balenciaga logo", "logo"),
    "supreme": ("Supreme logo", "logo"), "nike": ("Nike logo", "logo"), "bape": ("A Bathing Ape logo", "logo"), "canada goose": ("Canada Goose logo", "logo"),
    "stone island": ("Stone Island logo", "logo"), "dhgate": ("DHgate logo", "logo"), "amazon": ("Amazon logo", "logo"),
    "minecraft": ("Minecraft logo", "logo"), "pixelmon": ("Pokemon logo", "logo"),
    "rimowa": ("Rimowa aluminium suitcase", "photo"),   # "Dior x Rimowa suitcase" (asics intro 2026-10-22): the suitcase, not the logo
    # brands that are also places/people: the PRODUCT (dhgate cartier watch 2026-10-22: "Cartier" alone found Parc national
    # de la Jacques-Cartier, "a picture of some scenic valley")
    "cartier": ("Cartier watch", "photo"), "omega": ("Omega watch", "photo"), "patek philippe": ("Patek Philippe watch", "photo"),
    "audemars piguet": ("Audemars Piguet watch", "photo"), "hermes": ("Hermes bag", "photo"), "chanel": ("Chanel logo", "logo"),
    # car comparisons ("the same price as a brand new Kia", same video: the line showed the store page and read as "IKEA").
    # 3-letter names are too short for the capitalised-word rule, so they must be listed here.
    "kia": ("Kia car", "photo"), "bmw": ("BMW car", "photo"), "toyota": ("Toyota car", "photo"), "tesla": ("Tesla car", "photo"),
    "mercedes": ("Mercedes-Benz car", "photo"), "ford": ("Ford car", "photo"), "hyundai": ("Hyundai car", "photo"),
    "lamborghini": ("Lamborghini car", "photo"), "ferrari": ("Ferrari car", "photo"), "porsche": ("Porsche car", "photo"),
}
SKIP = {"i", "in", "so", "but", "the", "we", "we're", "it's", "today's", "watch", "hey", "x", "and", "let's", "there", "this", "that", "these", "if", "my"}


def entities(W):
    """Spans of capitalised words (not sentence-initial filler) + known names; returns [(phrase, first word index)]."""
    out, i = [], 0
    txt = " ".join(re.sub(r"[^\w']", "", w["w"]).lower() for w in W)
    for name in sorted(HINTS, key=len, reverse=True):
        for m in re.finditer(r"\b" + re.escape(name) + r"s?\b", txt):
            idx = txt[: m.start()].count(" ")
            if not any(abs(idx - j) <= 1 and (name in p or p in name) for p, j in out):
                out.append((name, idx))
    while i < len(W):
        w = re.sub(r"[^\w']", "", W[i]["w"])
        if w[:1].isupper() and w.lower() not in SKIP and (i == 0 or not W[i - 1]["w"].endswith((".", "!", "?")) or len(w) > 3):
            j = i
            while j + 1 < len(W) and re.sub(r"[^\w']", "", W[j + 1]["w"])[:1].isupper():
                j += 1
            ph = " ".join(re.sub(r"[^\w']", "", W[k]["w"]) for k in range(i, j + 1)).lower()
            if len(ph) > 3 and not any(ph in p or p in ph for p, _ in out) and ph not in SKIP:
                out.append((ph, i))
            i = j + 1
        else:
            i += 1
    return sorted(out, key=lambda x: x[1])


def _read_meta(p):
    """A cache entry; a half-written one (a build killed mid-write, best sp5der hoodie 2026-10-23: "INTRO FAILED" on an
    empty stock json) counts as missing and is searched again."""
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        try:
            os.remove(p)
        except OSError:
            pass
        return {}


GENERIC_Q = {"logo", "store", "photo", "car", "a", "the", "of", "and", "aluminium", "bag"}


def commons(query, want="photo", need=None):
    """need: words that must ALL be in the file title (default: the query's own words minus generic ones). A bare
    "Cartier" search returned a Quebec park; a picture that isn't provably the thing is worse than no picture."""
    need = [w for w in (need if need is not None else re.findall(r"[a-z0-9]+", query.lower())) if w not in GENERIC_Q]
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
                                "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1400, "format": "json"})
    req = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    pages = sorted(d.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    best = None
    for p in pages:
        ii = p.get("imageinfo", [{}])[0]
        mime, w, h = ii.get("mime", ""), ii.get("width", 0), ii.get("height", 1)
        if "video" in mime or "pdf" in mime or not ii.get("thumburl"):
            continue
        if want == "logo" and not (mime.endswith("svg+xml") or "logo" in p["title"].lower()):
            continue
        if need and not all(n in p["title"].lower() for n in need):
            continue
        if want == "photo" and (mime.endswith("svg+xml") or w < 600 or w / max(1, h) < 0.7 or re.search(r"logo|map|diagram", p["title"], re.I)):
            continue
        meta = ii.get("extmetadata", {})
        best = {"url": ii["thumburl"], "title": p["title"], "license": meta.get("LicenseShortName", {}).get("value", ""),
                "artist": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()[:120], "page": ii.get("descriptionurl", "")}
        break
    return best


def fetch(query, want="photo"):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"{query}|{want}".encode()).hexdigest()[:10]
    meta_p = os.path.join(CACHE, key + ".json")
    if os.path.exists(meta_p):
        m = _read_meta(meta_p)
        return m if m.get("file") and os.path.exists(m["file"]) else None
    try:
        hit = commons(query, want)
    except Exception as e:
        hit = None
    if not hit:
        json.dump({"query": query, "file": None}, open(meta_p, "w"))
        return None
    ext = ".png" if want == "logo" else ".jpg"
    dst = os.path.join(CACHE, key + ext)
    req = urllib.request.Request(hit["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r, open(dst, "wb") as f:
        f.write(r.read())
    hit.update({"query": query, "kind": want, "file": dst})
    json.dump(hit, open(meta_p, "w"), indent=1)
    return hit


VIDEO_HINTS = {"honda civic": "Honda Civic", "civic": "Honda Civic", "neiman marcus": "Neiman Marcus", "rolex": "Rolex watch"}


def commons_video(query):
    """A short free-licence clip of the thing (Wikimedia Commons video search); returns a cached local file or None."""
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(("vid|" + query).encode()).hexdigest()[:10]
    meta_p = os.path.join(CACHE, key + ".json")
    if os.path.exists(meta_p):
        m = _read_meta(meta_p)
        return m if m.get("file") and os.path.exists(m["file"]) else None
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": query + " filetype:video", "gsrnamespace": 6, "gsrlimit": 8,
                                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "format": "json"})
    hit = None
    try:
        with urllib.request.urlopen(urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA}), timeout=25) as r:
            pages = sorted(json.load(r).get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        words = [w for w in query.lower().split() if len(w) > 2]
        for p in pages:
            ii = p.get("imageinfo", [{}])[0]
            dur = float(ii.get("duration") or 0)
            if ii.get("width", 0) >= 1280 and 3 <= dur <= 120 and all(w in p["title"].lower() for w in words):
                meta = ii.get("extmetadata", {})
                hit = {"url": ii["url"], "title": p["title"], "license": meta.get("LicenseShortName", {}).get("value", ""), "page": ii.get("descriptionurl", ""),
                       "artist": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()[:120], "dur": dur}
                break
    except Exception:
        hit = None
    if not hit:
        json.dump({"query": query, "file": None}, open(meta_p, "w"))
        return None
    raw = os.path.join(CACHE, key + ".src" + os.path.splitext(hit["url"])[1])
    with urllib.request.urlopen(urllib.request.Request(hit["url"], headers={"User-Agent": UA}), timeout=90) as r, open(raw, "wb") as f:
        f.write(r.read())
    dst = os.path.join(CACHE, key + ".mp4")
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-an", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst])
    hit.update({"query": query, "file": dst, "kind": "video"})
    json.dump(hit, open(meta_p, "w"), indent=1)
    return hit


# generic things a line can name -> a free stock search (Mixkit, free licence, no account); used only where the
# user's own B-roll has nothing for that line
CONCEPT_VIDEO = [  # travel talk is always B-roll (user, asics intro 2026-10-22: "just traveling should probably be b-roll")
                 (r"\btsa\b|security|checkpoint|customs", "airport security"), (r"airport|travel|traveling|traveled|flight|flying|vacation|\btrip\b", "airport"),
                 (r"airplane|\bplane\b|\bflew\b", "airplane"),
                 # no generic cash/banknote stock: price lines show the product (prada cups 2026-10-22: "there's no B-roll
                 # here, it's just cash and it's kind of boring"); the kinetic price word + register carry the money
                 (r"\bcomputer|laptop|online|website", "laptop online shopping"),
                 (r"\bpackage|shipping|delivered|delivery|order", "package delivery"), (r"\bmall|shopping|store\b", "shopping mall"),
                 (r"\bcar\b|drive|driving", "car driving city"), (r"\bhome\b|house", "front door home"), (r"\bphone\b|app\b", "smartphone hand"),
                 (r"\bfood|pizza|burger|hungry", "food delivery"), (r"\bclothes|clothing|fashion|outfit", "clothes rack fashion")]


# named non-product things a review VO says: always their own B-roll, never more product footage (s25 ultra 2026-10-23)
NAMED_STOCK = [(r"factor(y|ies)|manufactur|assembly line|sweatshop", "factory production line"),
               (r"warehouse", "warehouse boxes"), (r"\bworkers?\b", "factory production line")]


# EARNINGS lines show money (top 5 reselling products spring 2026-10-25, intro: "whenever I talk about money ('making
# upwards of $10,000', 'turn a profit', 'make lots of money for the summer') there is no money on screen. Show money: cash,
# a payout, a sold listing"). Only what he or people EARN: a product's PRICE keeps showing the product (prada cups rule
# below). Each earnings line takes the next query, so two lines never show the same clip.
EARN_RE = re.compile(r"\bmaking (upwards of |over |about |around )?\$?\s?\d|\$\s?\d[\d,]* (a|per) (month|week|day)\b|"
                     r"\b(per|a) month\b.*\b(effort|money|profit)|\bturn(ing)? a profit\b|\bprofit\b|"
                     r"\bmake (lots of |a lot of |good |some |real |easy )?money\b|\bcash(ing)? out\b|\bpayouts?\b|\bincome\b", re.I)
EARN_STOCK = ["counting money", "dollar bills table", "stack of money", "counting dollars", "hundred dollar bills", "money falling"]


NO_STOCK = re.compile(r"\b(cash|money|banknotes?|bills|dollars?|wallet|coins?)\b", re.I)


def stock_video(query, allow_cash=False, nth=0):
    """stock_one, and on a miss the same query with its last words dropped (s25 ultra 2026-10-23: "electronics factory"
    found the factory floor at 17:46, the next build asked for "electronics factory assembly", Mixkit had nothing, and the
    Chinese-factory line lost its B-roll). Never shorter than two words: one word is too vague to mean the line."""
    words = (query or "").split()
    for n in range(len(words), min(2, len(words)) - 1, -1):
        hit = stock_one(" ".join(words[:n]), allow_cash, nth)
        if hit:
            return hit
    return None


# Mixkit clips that do not read as their title on screen: never picked again
# 42135 "young woman pouring packing filler into a box" = a hand in pink confetti ($30k reselling 2026-10-26, 0:13-0:18)
BAD_STOCK = {"42135"}


def stock_one(query, allow_cash=False, nth=0):
    """First Mixkit clip whose title shares the most words with the query; cached 1080x1920-safe mp4 (720p source).
    nth > 0 = the nth-next match: the second half of a long shot gets ANOTHER clip of the same idea (lv skatesta 2026-10-24:
    one skater clip held 5.9 s across two lines, "lacking movement")."""
    # never generic cash stock, whoever asks (prada cups 2026-10-22 rule; the director and the self-check both picked "cash
    # on table" for "I don't have that money" in best sp5der hoodie 2026-10-23)
    if NO_STOCK.search(query or "") and not allow_cash:   # his own pin may ask for money B-roll (reselling spreadsheet)
        return None
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(("mixkit|" + query + (f"|{nth}" if nth else "")).encode()).hexdigest()[:10]
    meta_p = os.path.join(CACHE, key + ".json")
    if os.path.exists(meta_p):
        m = _read_meta(meta_p)
        if m.get("file") and os.path.exists(m["file"]):
            return m
        # a miss is only remembered for a day: one network blip used to block a query for good (reselling spreadsheet
        # 2026-10-23: all three self-check swaps said "nothing found" from cached misses)
        if time.time() - os.path.getmtime(meta_p) < 86400:
            return None
    hit = None
    try:
        url = "https://mixkit.co/free-stock-video/discover/" + urllib.parse.quote(query.replace(" ", "-")) + "/"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
            h = r.read().decode("utf-8", "replace")
        # item links look like /free-stock-video/<title-slug>-<id>/ ; the 720p file is assets.mixkit.co/videos/<id>/<id>-720.mp4
        vids = []
        for slug, vid in re.findall(r'/free-stock-video/([a-z0-9-]+?)-(\d+)/', h):
            if (slug, vid) not in vids and vid not in BAD_STOCK:
                vids.append((slug, vid))
        qw = set(query.lower().split())
        vids.sort(key=lambda v: -len(qw & set(v[0].split("-"))))
        if len(vids) > nth and qw & set(vids[nth][0].split("-")):
            slug, vid = vids[nth]
            hit = {"title": slug.replace("-", " "), "url": f"https://assets.mixkit.co/videos/{vid}/{vid}-720.mp4", "license": "Mixkit free license",
                   "page": f"https://mixkit.co/free-stock-video/{slug}-{vid}/", "artist": "Mixkit"}
    except Exception:
        hit = None
    if not hit:
        json.dump({"query": query, "file": None}, open(meta_p, "w"))
        return None
    raw = os.path.join(CACHE, key + ".src.mp4")
    try:   # a 403 on the file itself crashed the whole intro (s25 ultra 2026-10-23: "INTRO FAILED", draft shipped without one)
        with urllib.request.urlopen(urllib.request.Request(hit["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=90) as r, open(raw, "wb") as f:
            f.write(r.read())
    except Exception:
        if os.path.exists(raw):
            os.remove(raw)
        return None
    dst = os.path.join(CACHE, key + ".mp4")
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-an", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst])
    hit.update({"query": query, "file": dst, "kind": "video"})
    json.dump(hit, open(meta_p, "w"), indent=1)
    return hit


# lines that stay inside a travel story once it started (asics intro 2026-10-22: the TSA comments, "noticing my ASICS" and
# the Dior x Rimowa suitcase all showed the shoe; they belong to the airport scene)
STORY_VIDEO = [(r"\bcomments?\b|commenting|compliment|noticing|noticed|\bagents?\b|\bstaff\b", "airport security"),
               (r"suitcase|luggage|\bbags?\b|carry.?on", "airport")]
COMMENT = re.compile(r"\bcomments?\b|commenting|compliment(?:ed|ing|s)?\b|noticing|noticed")
REPORTED = re.compile(r"\b(?:said|told me|asked)\b(?: that)?(?: (?:they|it|those|these|the \w+))? (?:were|was|are|is|looked|look)? ?(.+)$", re.I)


def quotes_for_lines(L):
    """Speech bubbles for people the VO quotes: {line index: [quote]}. The bubble pops on the comment line with typing
    dots and fills with his own reported words ('very comfortable shoes') when he says them. Nothing is invented: no
    reported words -> the bubble keeps the dots."""
    out = {}
    for i, ln in enumerate(L):
        lw = ln["text"].lower()
        if not COMMENT.search(lw) or ln["role"] in ("go", "watch", "turn"):
            continue
        ctx = " ".join(L[j]["text"].lower() for j in range(max(0, i - 2), i + 1))
        who = "TSA AGENT" if re.search(r"\btsa\b", ctx) else ""
        q = {"who": who, "t": ln["s"], "text": "", "fill": None, "until": L[i + 1]["s"] if i + 1 < len(L) else None}
        for k in range(i, min(len(L), i + 3)):
            m = REPORTED.search(L[k]["text"].strip())
            if m and len(m.group(1).split()) >= 2:
                said = re.sub(r"[\s,.;:!?]+$", "", m.group(1))
                q.update(text=said[:1].upper() + said[1:] + "!", fill=L[k]["s"] if k > i else None,
                         until=L[k + 1]["s"] if k + 1 < len(L) else None)
                break
        out[i] = [q]
        break   # one quote moment per intro
    return out


def videos_for_lines(W, L, own=None):
    """Real clips for named things -> {line index: footage entry} used as that line's B-roll (beats a still photo)."""
    out, credits = {}, []
    for ph, wi in entities(W):
        q = VIDEO_HINTS.get(ph)
        if not q:
            continue
        li = next((i for i, ln in enumerate(L) if ln["wi"][0] <= wi <= ln["wi"][1]), None)
        hit = commons_video(q) if li is not None and li not in out else None
        if hit:
            out[li] = {"src": hit["file"], "t": 0.0, "tag": ph, "for": "", "entity": ph}
            credits.append(f"{hit['title'].replace('File:', '')} - {hit.get('artist') or 'Wikimedia Commons'} ({hit['license']}) {hit.get('page', '')}")
    # free stock B-roll for lines that name a generic thing the user's own clips don't cover (never more than 3 per intro)
    own = own or []
    n = 0
    for li, ln in enumerate(L):
        if li in out or n >= 3 or ln["role"] in ("go", "watch"):
            continue
        lw = ln["text"].lower()
        if any(k and k.lower() in lw for f in own for k in ([f.get("for")] if isinstance(f.get("for"), str) else f.get("for") or [])):
            continue
        q = next((q for pat, q in CONCEPT_VIDEO if re.search(pat, lw)), None)
        hit = stock_video(q) if q else None
        if hit:
            out[li] = {"src": hit["file"], "t": 0.5, "tag": q, "for": "", "entity": ""}
            credits.append(f"{hit['title']} - Mixkit ({hit['license']})")
            n += 1
    # once a travel story started, its people/luggage lines reuse those clips (a later part of the clip, not a new download)
    travel = [li for li, f in out.items() if f["tag"] in ("airport", "airport security", "airplane")]
    if travel:
        reuse = 0
        for li, ln in enumerate(L):
            if li in out or li < min(travel) or ln["role"] in ("go", "watch", "turn", "reveal"):
                continue
            q = next((q for pat, q in STORY_VIDEO if re.search(pat, ln["text"].lower())), None)
            hit = stock_video(q) if q else None
            if hit:
                reuse += 1
                out[li] = {"src": hit["file"], "t": 0.5 + 3.5 * reuse, "tag": q, "for": "", "entity": ""}
    return out, credits


def for_lines(W, L, out, overrides=None, skip=(), product=""):
    """Attach a picture to each line that names a real thing. Returns {line index: {src, kind, label, credit}}.
    product: what the video reviews ("watch"); a bare name without a hint is searched as "<name> <product>"."""
    ov = {o["match"].lower(): o for o in (overrides or [])}
    pics, credits, seen = {}, [], set()
    os.makedirs(os.path.join(out, "assets", "pics"), exist_ok=True)
    for ph, wi in entities(W):
        li = next((i for i, ln in enumerate(L) if ln["wi"][0] <= wi <= ln["wi"][1]), None)
        if li is None or ph in skip:
            continue
        o = ov.get(ph) or next((v for k, v in ov.items() if k in ph or ph in k), None)
        if o and o.get("skip"):
            continue
        if o and o.get("file"):
            hit = {"file": o["file"], "kind": o.get("kind", "photo"), "title": os.path.basename(o["file"]), "license": "own", "artist": ""}
        else:
            q, kind = (o["query"], o.get("kind", "photo")) if o else HINTS.get(ph, (f"{ph} {product}".strip() if " " not in ph else ph, "photo"))
            hit = fetch(q, kind)
        if not hit or hit["file"] in seen:   # the same picture twice in one intro is filler
            continue
        seen.add(hit["file"])
        name = os.path.basename(hit["file"])
        import shutil
        shutil.copy(hit["file"], os.path.join(out, "assets", "pics", name))
        entry = {"src": "assets/pics/" + name, "kind": hit["kind"], "label": ph, "t": W[wi]["s"]}
        pics.setdefault(li, [])
        if len(pics[li]) < 2:
            pics[li].append(entry)
        if hit.get("license") and hit["license"] != "own":
            credits.append(f"{hit['title'].replace('File:', '')} - {hit.get('artist') or 'Wikimedia Commons'} ({hit['license']}) {hit.get('page', '')}")
    json.dump({"pics": pics, "credits": sorted(set(credits))}, open(os.path.join(out, "pics.json"), "w"), indent=1)
    return pics


# ---------- people and places the VO names (best sp5der hoodie 2026-10-23: "I said places, Atlanta, Decatur, Dunwoody ...
# they need to be in the intro. And Young Thug: why is Young Thug not there? I said a whole person. The intro needs to
# understand context."). The old for_lines searched "atlanta hoodie" / "young thug's" on Commons and found nothing.
# Wikipedia tells a person from a place (description + coordinates); a disambiguation ("Decatur") is retried inside the
# region of a place already named ("the Atlanta area" -> "Decatur, Georgia"). Only Commons (free) lead images are used.
PERSON_RE = re.compile(r"\b(rapper|singer|songwriter|musician|actor|actress|comedian|athlete|player|footballer|boxer|wrestler|"
                       r"producer|dj|designer|entrepreneur|businessman|businesswoman|youtuber|influencer|streamer|politician|"
                       r"model|artist|chef|director|television personality|media personality)\b", re.I)
PLACE_RE = re.compile(r"\b(city|town|village|suburb|neighbou?rhood|county|state|capital|borough|district|area|region|"
                      r"country|island|municipality|community)\b", re.I)


def wiki_summary(title):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(("wiki|" + title).encode()).hexdigest()[:10]
    p = os.path.join(CACHE, key + ".json")
    if os.path.exists(p) and (d := _read_meta(p)):
        return d
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
            d = json.load(r)
    except Exception:
        d = {}
    json.dump(d, open(p, "w", encoding="utf-8"))
    return d


def resolve_entity(name, region=None):
    """{"type": "person"|"place", "name", "title", "region", "image"} or None (not a person/place, or no free picture)."""
    nm = re.sub(r"'s$|s'$", "", name.strip()).strip()
    pretty = " ".join(w[:1].upper() + w[1:] for w in nm.split())
    tries = [pretty] + ([f"{pretty}, {region}"] if region else [])
    for t in tries:
        d = wiki_summary(t)
        if not d or d.get("type") == "disambiguation":
            continue
        desc = d.get("description") or ""
        kind = "place" if d.get("coordinates") and PLACE_RE.search(desc) else "person" if PERSON_RE.search(desc) and not d.get("coordinates") else None
        if not kind:
            continue
        img = (d.get("originalimage") or d.get("thumbnail") or {}).get("source", "")
        if "/wikipedia/commons/" not in img:   # enwiki-local lead images are non-free (fair use): never
            img = ""
        m = re.search(r"\b(?:of|in)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", desc)
        return {"type": kind, "name": pretty, "title": d.get("title", pretty), "desc": desc, "image": img.split("?")[0],
                "region": m.group(1) if m and kind == "place" else None, "page": (d.get("content_urls") or {}).get("desktop", {}).get("page", "")}
    return None


def photo_clip(img_url, seconds=4.0, seed=0):
    """A still made into footage: full 16:9 frame, slow eased push-in (portrait photos sit on a blurred copy of themselves)."""
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"kb|{img_url}|{seconds}|{seed % 2}".encode()).hexdigest()[:10]
    dst = os.path.join(CACHE, key + ".mp4")
    if os.path.exists(dst):
        return dst
    ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1].lower() or ".jpg"
    raw = os.path.join(CACHE, key + ".src" + ext)
    try:
        if not os.path.exists(raw):
            with urllib.request.urlopen(urllib.request.Request(img_url, headers={"User-Agent": UA}), timeout=60) as r, open(raw, "wb") as f:
                f.write(r.read())
    except Exception:
        return None
    import subprocess
    n = int(seconds * 30)
    # zoom 1.0 -> 1.12 eased; odd seeds drift the other way so two photos in a row don't move alike
    zx = "iw/2-(iw/zoom/2)" if seed % 2 == 0 else "iw/2-(iw/zoom/2)+(iw/zoom)*0.04*on/%d" % n
    fc = ("[0:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,boxblur=40:2,eq=brightness=-0.12[bg];"
          "[0:v]scale=3840:2160:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p,"
          f"zoompan=z='1+0.12*(0.5-0.5*cos(PI*on/{n}))':x='{zx}':y='ih/2-(ih/zoom/2)':d={n}:s=1920x1080:fps=30")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", "1", "-i", raw, "-filter_complex", fc, "-frames:v", str(n),
                        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst], capture_output=True, text=True)
    return dst if not r.returncode and os.path.exists(dst) else None


# things that are ALSO a city / person on Wikipedia but in his videos are the product (dhgate cologne spread 2026-10-25,
# 0:00: "Cologne seems like the hottest new trend" got the Wikipedia photo of Cologne, Germany, the Rhine: "no picture of
# cologne, just shows water"). Whisper capitalises them at a sentence start. Never a person/place shot for these.
NOT_ENTITY = {"cologne", "colognes", "perfume", "jordan", "jordans", "supreme", "vans", "converse", "polo", "champion",
              "guess", "coach"}


def entity_footage(W, L):
    """{line index: footage} for every person / place the VO names, plus credits. The entry is forced (the line shows THAT),
    full=True (templates show it full frame, not as another small card) and named=True (the director can't replace it)."""
    out, credits, region, seen = {}, [], None, set()
    ents = entities(W)
    for ph, wi in ents:   # a first pass finds the region ("Atlanta" -> Georgia) so "Decatur" said earlier still resolves
        e = resolve_entity(ph)
        if e and e["type"] == "place" and e["region"]:
            region = e["region"]
            break
    for ph, wi in ents:
        li = next((i for i, ln in enumerate(L) if ln["wi"][0] <= wi <= ln["wi"][1]), None)
        if li is None or li in out or L[li]["role"] in ("go", "watch") or ph in HINTS or ph in NOT_ENTITY:
            continue
        e = resolve_entity(ph, region)
        if not e or not e["image"] or e["image"] in seen:
            continue
        clip = photo_clip(e["image"], seed=len(out))
        if not clip:
            continue
        seen.add(e["image"])
        out[li] = {"src": clip, "t": 0.0, "tag": f"{e['type']}: {e['name']}", "for": "", "entity": ph, "full": True, "named": True,
                   "label": e["name"].split(",")[0]}
        credits.append(f"{e['title']} (Wikipedia lead image, Wikimedia Commons) {e['page']}")
    return out, credits
