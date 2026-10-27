"""His OWN footage of things he names, from his other videos (dhgate watchb spread 2026-10-24).

Two moments get it automatically:
- a footage CALLOUT: "I'll throw up some footage right now", "I'm going to throw up a video", "I have done a detailed
  review of this" (1:58: "I said I'll throw up some footage, but no footage shows on the screen ... it's in my drive";
  7:01: "the b-roll should be from our videos. If it doesn't have it, just skip it"). The thing is the product named in
  that line or the one before; no footage of it = no B-roll (never a stand-in).
- a LIST: three or more products / brands named in one breath ("everything from Rolex to AP's to Patek's to Apple
  watches", 0:31: "if I start listing things, then it should probably have the list of things, and B-roll if we have
  it"). Each name gets its own clip, cut on the word he says it, with the list building up on screen.

Footage comes from intro_library/product_library.find_clips ({{DRIVE_RAW}} + {{PROJECTS_ROOT}}\\*\\raw, a
vision check picks the moments the product is shown). The clips play silent, full frame (a side-by-side recording is
cropped to the half that shows it); they may cover the screen recording (he asked for them there)."""
import json
import re
import sys
from pathlib import Path

LIB = Path(r"{{KIT}}/tools\intro_library")
FONT = LIB / "kit" / "fonts" / "Anton-Regular.ttf"

CALLOUT = ["throw up some footage", "throw up footage", "throw up a video", "throw up a clip", "throw up the video",
           "throw up some clips", "put up some footage", "show you some footage", "pull up some footage",
           "done a detailed review", "did a detailed review", "done a review on", "did a review on", "have a video on",
           "made a video on", "did a video on"]
# names that count as a product / brand on their own (one word each; "apple watch" is joined below)
NAMES = {"rolex": "Rolex", "rolexes": "Rolex", "ap": "AP", "aps": "AP", "audemars": "AP", "patek": "Patek", "pateks": "Patek",
         "cartier": "Cartier", "omega": "Omega", "hublot": "Hublot", "datejust": "Rolex Datejust", "daytona": "Rolex Daytona",
         "airpods": "AirPods", "airpod": "AirPods", "cologne": "Cologne", "colognes": "Cologne", "hoodie": "Hoodie",
         "hoodies": "Hoodie", "sp5der": "Sp5der", "spider": "Sp5der", "jordans": "Jordans", "jordan": "Jordans",
         "yeezys": "Yeezys", "yeezy": "Yeezys", "prada": "Prada", "amiri": "Amiri", "asics": "Asics", "moncler": "Moncler"}
SEARCH = {"Rolex": "rolex", "AP": "aps", "Patek": "patek", "Apple Watch": "apple watch", "Rolex Datejust": "rolex",
          "Rolex Daytona": "rolex"}


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower()).replace("'s", "").rstrip("'")


def _names(words, a, b):
    """[(name, word_start)] of products named in [a, b), in order, first mention of each."""
    out, seen = [], set()
    ws = [w for w in words if a <= w["s"] < b]
    for i, w in enumerate(ws):
        t = _norm(w["w"])
        nm = None
        if t in ("apple",) and i + 1 < len(ws) and _norm(ws[i + 1]["w"]).startswith("watch"):
            nm = "Apple Watch"
        elif t in NAMES:
            nm = NAMES[t]
        if nm and nm not in seen:
            seen.add(nm)
            out.append((nm, w["s"]))
    return out


PHOTO = {"AP": "Audemars Piguet Royal Oak watch"}   # lists only: a brand he never filmed gets a real photo (Wikimedia)

# BRANDS he lists after a cue ("we got brands such as Creed, we got Dior Sauvage, you guys name it", dhgate cologne spread
# 2026-10-25, 0:44: "those are 2 types of colognes that should've been shown on screen ... the word brand, such as, or some
# variation ... some relevant B-roll should go up on the screen"). Two names after the cue are a list (three without one).
BRAND_CUE = re.compile(r"\bbrands? (?:such as|like|including)\b|\bsuch as\b|\bnames? like\b|\bwe (?:got|have) brands\b")
BRANDS = {"creed": "Creed", "aventus": "Creed", "dior": "Dior", "sauvage": "Dior Sauvage", "savage": "Dior Sauvage",
          "versace": "Versace", "chanel": "Chanel", "gucci": "Gucci", "ysl": "YSL", "armani": "Armani", "valentino": "Valentino",
          "xerjoff": "Xerjoff", "baccarat": "Baccarat Rouge", "lv": "Louis Vuitton", "vuitton": "Louis Vuitton",
          "burberry": "Burberry", "givenchy": "Givenchy", "hermes": "Hermes", "rolex": "Rolex", "cartier": "Cartier",
          "prada": "Prada", "amiri": "Amiri", "moncler": "Moncler", "nike": "Nike", "jordan": "Jordans", "jordans": "Jordans"}
# a real photo when he never filmed it: the Commons file title must hold every word of the query (pics.commons), so a
# brand whose only Commons hits are something else (Creed -> "Assassin's Creed") gets none
# a "File:" value = that exact Commons file: a search for "Dior Sauvage" returns "Eau Sauvage" (a different, clear-bottle
# fragrance from 1966), which the user rejected (dhgate cologne spread 2026-10-25: "let's just use the actual Dior Sauvage,
# the black bottle ... I don't know why we used a clear one"). The real dark Sauvage on Commons is its box.
BRAND_PHOTO = {"Dior Sauvage": "File:Dior Sauvage Verpackung.jpg", "Dior": "File:Dior Sauvage Verpackung.jpg", "Chanel": "Chanel perfume", "Versace": "Versace perfume",
               "Gucci": "Gucci perfume", "Rolex": "Rolex watch", "Cartier": "Cartier watch"}


def _brand_names(words, a, b):
    """[(name, word_start)] of brands in [a, b); "Dior Savage" is one name (Dior's Sauvage), first mention of each."""
    out, seen = [], set()
    ws = [w for w in words if a <= w["s"] < b]
    for i, w in enumerate(ws):
        t = _norm(w["w"])
        nm = BRANDS.get(t) or NAMES.get(t)
        if nm == "Dior" and i + 1 < len(ws) and _norm(ws[i + 1]["w"]) in ("sauvage", "savage"):
            nm = "Dior Sauvage"
        if nm == "Dior Sauvage" and i and _norm(ws[i - 1]["w"]) == "dior":
            continue
        if nm and nm not in seen:
            seen.add(nm)
            out.append((nm, w["s"]))
    return out


def _own_product_moment(name, project, words, used):
    """A moment of THIS recording where the product camera shows `name` while he says it (the bottle in his hand)."""
    try:
        rows = json.loads((project / "work" / "analysis.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    keys = [k for k, v in BRANDS.items() if v == name or (name == "Dior Sauvage" and v == "Dior")]
    # only the brand the video is ABOUT (said most often): "I'm thinking about getting some LV cologne" was said with the
    # Creed bottle in his hand, and that shot would have been labelled Louis Vuitton
    cnt = {}
    for w in words:
        b = BRANDS.get(_norm(w["w"]))
        if b:
            cnt[b] = cnt.get(b, 0) + 1
    if not cnt or max(cnt, key=cnt.get) != name.replace("Dior Sauvage", "Dior"):
        return None
    # the product camera's runs (>= 2.5 s, his face on the talking camera) anywhere in the recording, one vision look
    runs, cur = [], None
    for r in rows:
        ok = r.get("right") == "product" and r.get("left") == "cam"
        if ok and cur is None:
            cur = r["t"]
        elif not ok and cur is not None:
            if r["t"] - cur >= 2.5:
                runs.append((cur, r["t"]))
            cur = None
    if not runs:
        return None
    # 12 looks spread evenly over all the product-camera time (one run can be 3 minutes long)
    tot = sum(b - a for a, b in runs)
    cells, acc, k = [], 0.0, 0
    for a, b in runs:
        while k < 12 and acc + (b - a) > (k + 0.5) * tot / 12:
            cells.append((round(a + (k + 0.5) * tot / 12 - acc, 1), "right"))
            k += 1
        acc += b - a
    sys.path.insert(0, str(LIB))
    import product_library
    cam = str(project / "raw" / "camera.mp4")
    noun = " ".join(w for w in re.findall(r"[a-z0-9]+", project.name.lower())
                    if w not in ("dhgate", "spread", "spreadsheet", "review", "reviews", "best", "the", "v2"))
    for t, c in product_library.moments(cam, f"{name} {noun}".strip() + " (or its box)", cells=cells):
        if (cam, round(t)) not in used:
            used.add((cam, round(t)))
            return {"src": cam, "t": t, "crop": c}
    return None


def _commons_file(title, width=1400):
    """Thumbnail URL of one exact Commons file (None when it can't be read)."""
    import urllib.parse, urllib.request
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url",
                                "iiurlwidth": width, "format": "json"})
    try:
        req = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q,
                                     headers={"User-Agent": "StudioIntroLibrary/1.0 (personal video editing)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            pg = next(iter(json.load(r)["query"]["pages"].values()))
        return pg["imageinfo"][0]["thumburl"].split("?")[0]
    except Exception:
        return None


def _brand_clip(name, project, words, used):
    c = _clip(name, project, used) or _own_product_moment(name, project, words, used)
    if c:
        return c
    if name in BRAND_PHOTO:
        sys.path.insert(0, str(LIB))
        import pics
        q = BRAND_PHOTO[name]
        url = _commons_file(q) if q.startswith("File:") else ((pics.fetch(q) or {}).get("url"))
        f = pics.photo_clip(url, seconds=4.0) if url else None
        if f and (f, 0) not in used:
            used.add((f, 0))
            return {"src": f, "t": 0.0, "crop": None}
    return None


def _clip(name, project, used, photo=False):
    sys.path.insert(0, str(LIB))
    import product_library
    clips = product_library.find_clips(SEARCH.get(name, name.lower()), exclude=[project.name], n=6, max_files=4)
    if not clips:
        if photo and name in PHOTO:
            import pics
            hit = pics.fetch(PHOTO[name])
            f = pics.photo_clip(hit["url"], seconds=4.0) if hit else None
            if f:
                return {"src": f, "t": 0.0, "crop": None}
        return None
    fresh = [c for c in clips if (c["src"], round(c["t"])) not in used]
    # all moments used already: the same file a few seconds on (a second look, never the same frames)
    c = dict(fresh[0]) if fresh else dict(clips[0], t=clips[0]["t"] + 3.0 * (1 + sum(1 for u in used if u[0] == clips[0]["src"])))
    used.add((c["src"], round(c["t"])))
    return c


def _crop(c):
    return {"left": "crop=iw/2:ih:0:0", "right": "crop=iw/2:ih:iw/2:0"}.get(c.get("crop") or "", "")


def plan(project, words, tl, cfg, placed, checks):
    """Placed-clip dicts (broll.broll_filters format + crop/labels) for footage callouts and lists, in output time."""
    nc = cfg.get("named_broll", {})
    if not nc.get("enabled", True):
        return []
    kept = tl.kept
    inn = lambda t: any(a <= t < b for a, b in kept)
    kw = [w for w in words if inn(w["s"])]
    out, used, busy = [], set(), [(p["out_start"], p["out_start"] + p["length"]) for p in placed]
    free = lambda a, b: not any(a < y and b > x for x, y in busy)

    def add(c, o0, length, labels, why):
        if length < 0.6 or not free(o0, o0 + length):
            return False
        out.append({"slot": f"named{len(out)}", "file": c["src"], "src_start": round(float(c["t"]), 3), "src_len": round(length, 3),
                    "speed": 1.0, "out_start": round(o0, 3), "length": round(length, 3), "portrait": False, "on_cut": False,
                    "crop": _crop(c), "labels": labels, "named": why})
        busy.append((o0, o0 + length))
        return True

    # 0. brand lists after a cue ("brands such as Creed, we got Dior Sauvage"): >= 2 brands within 8 s of the cue, each
    # cut in on its name with the list building up on screen
    text0 = " ".join(_norm(w["w"]) for w in kw)
    brand_done = -1.0
    try:
        rows = json.loads((project / "work" / "analysis.json").read_text(encoding="utf-8"))
    except Exception:
        rows = []
    for m in BRAND_CUE.finditer(text0):
        ci = text0[:m.start()].count(" ")
        if ci >= len(kw) or not nc.get("brand_lists", True):
            continue
        t_cue = kw[ci]["s"]
        if t_cue < brand_done:   # "we got brands such as": one cue
            continue
        nm = _brand_names(kw, t_cue, t_cue + 8.0)
        if len(nm) < 2:
            continue
        brand_done = nm[-1][1] + 0.01
        # he is showing them on the screen recording ("we have some LV on here"): the screen IS the picture
        rs = [r for r in rows if t_cue <= r["t"] < nm[-1][1] + 1.0]
        if rs and sum(r.get("left") == "screen" or r.get("right") == "screen" for r in rs) > len(rs) / 2:
            checks.append(f"Brand list at {tl.to_out(nm[0][1]):.1f} s ({', '.join(n for n, _ in nm)}): over the screen "
                          "recording, he shows them there, no B-roll.")
            continue
        names = [n for n, _ in nm]
        times = [tl.to_out(t0) - 0.12 for _, t0 in nm]
        times[0] = min(times[0], tl.to_out(t_cue) - 0.12)   # the first picture goes up on "brands such as"
        o_end = tl.to_out(nm[-1][1]) + nc.get("list_last_seconds", 1.6)
        got = []
        for k, (n, t0) in enumerate(nm):
            c = _brand_clip(n, project, words, used)
            o1 = times[k + 1] if k + 1 < len(nm) else o_end
            if c is None:
                checks.append(f"Brand list: no footage or photo of {n}, skipped.")
                continue
            if add(c, times[k], o1 - times[k], {"list": names, "upto": k}, f"brands: {', '.join(names)}"):
                got.append(n)
        checks.append(f"Brand list at {tl.to_out(nm[0][1]):.1f} s (\"{m.group(0)}\"): {', '.join(names)}; on screen: "
                      f"{', '.join(got) or 'none'}.")

    # 1. lists: >= 3 names within 8 s of kept speech
    done = set()
    for i, w in enumerate(kw):
        if i in done:
            continue
        nm = _names(kw, w["s"], w["s"] + 8.0)
        if len(nm) < 3 or _names([w], w["s"], w["s"] + 0.01) == []:
            continue
        done |= {j for j, x in enumerate(kw) if w["s"] <= x["s"] < w["s"] + 8.0}
        names = [n for n, _ in nm]
        # each clip cuts in ON its name (0.12 s before the word), never later (watch spreadsheet round 2: a 1.2 s minimum
        # per name pushed the next clips back, AP 0.4 s / Patek 0.7 s / Apple Watch 1.15 s late: "it's popping up too
        # late ... when I say it, it's got to be locked"). A name said fast gets a short clip, not a late one.
        o_start = tl.to_out(nm[0][1]) - 0.12
        o_end = tl.to_out(nm[-1][1]) + nc.get("list_last_seconds", 1.6)
        times = [tl.to_out(t0) - 0.12 for _, t0 in nm]
        for k, (n, t0) in enumerate(nm):
            c = _clip(n, project, used, photo=True)
            o0 = times[k]
            o1 = times[k + 1] if k + 1 < len(nm) else o_end
            if c is None:
                checks.append(f"List B-roll: no footage of {n} in his videos, its name shows on the list only.")
                continue
            add(c, o0, o1 - o0, None, f"list: {', '.join(names)}")
        checks.append(f"List B-roll at {tl.to_out(nm[0][1]):.1f} s: {', '.join(names)} (clips cut on each name).")

    # 2. footage callouts
    text = " ".join(_norm(w["w"]) for w in kw)
    hits = sorted((text[:m.start()].count(" "), cue) for cue in CALLOUT
                  for m in re.finditer(r"\b" + re.escape(cue) + r"\b", text))
    last_t = -99.0
    for idx, cue in hits:
        if True:
            if idx >= len(kw) or kw[idx]["s"] - last_t < 12.0:
                continue   # one callout = one B-roll ("throw up some footage ... detailed reviews" said in one breath)
            t = last_t = kw[idx]["s"]
            # the thing: named in this line (8 s around the cue) first, else in the 12 s before (the list he just gave)
            nm = _names(kw, t - 8.0, t + 4.0) or _names(kw, t - 12.0, t + 6.0)
            if not nm:
                checks.append(f"Footage callout at {tl.to_out(t):.1f} s (\"{cue}\"): no product named near it, no B-roll.")
                continue
            o0 = tl.to_out(t) + 0.3
            each = nc.get("callout_seconds", 4.5) if len(nm) == 1 else nc.get("montage_each", 1.4)
            got = 0
            for n, _ in nm[:4]:
                c = _clip(n, project, used)
                if c is None:
                    checks.append(f"Footage callout at {tl.to_out(t):.1f} s: no footage of {n} in his videos, skipped.")
                    continue
                if add(c, o0, each, None, f"callout: {cue}"):
                    o0 += each
                    got += 1
            if got:
                checks.append(f"Footage callout at {tl.to_out(t):.1f} s (\"{cue}\"): {got} clip(s) of {', '.join(n for n, _ in nm[:4])} from his videos.")
    return out


def label_filter(c, W=1920, H=1080):
    """drawtext lines for a clip's labels: the list building up (current name yellow) or the product name."""
    lab = c.get("labels") or {}
    f = str(FONT).replace("\\", "/").replace(":", "\\:")
    esc = lambda s: s.replace("'", "").replace(":", "\\:")
    parts = []
    if "list" in lab:
        for k, n in enumerate(lab["list"][:lab["upto"] + 1]):
            col = "0xFFD23F" if k == lab["upto"] else "white"
            parts.append(f"drawtext=fontfile='{f}':text='{esc(n.upper())}':fontsize=78:fontcolor={col}:borderw=5:bordercolor=black@0.85"
                         f":x=90:y={140 + k * 104}")
    elif lab.get("name"):
        parts.append(f"drawtext=fontfile='{f}':text='{esc(lab['name'].upper())}':fontsize=84:fontcolor=white:borderw=5"
                     f":bordercolor=black@0.85:x=90:y=h-200")
    return ",".join(parts)
