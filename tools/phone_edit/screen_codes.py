"""Read every promo / invite code off the screen (user 2026-10-21: "any video with codes, capture them ... most of them are
found on the screen ... keep in mind promo codes change"). So codes are read from THIS video, never from an old list.

How: Windows OCR (privacy_ocr.ocr, local) on both halves of the cut at 1 fps. A code candidate is a 4-20 char token with no
spaces that has a digit, or is ALL CAPS and >= 7 long, that is not UI chrome (seen in > 40 % of samples) or a stop word.
It counts only when the user SAYS or SPELLS it within 25 s of it being on screen (fuzzy match against the spoken letters /
digits, "two five S T V..." -> "25stv"). Spellings are voted over every sighting, and the on-screen spelling wins.

Usage: python screen_codes.py <edit/cut-full.mp4> <edit/out_words.json> <out screen_codes.json> [app name]
Writes [{"code", "seen", "said", "sub"}] (times in the cut timeline). events.py turns each into its own code card.
"""
import collections
import difflib
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import privacy_ocr  # noqa: E402

STOP = {"CONTINUE", "APPLY", "REMOVE", "PAYPAL", "KLARNA", "AFTERPAY", "AFFIRM", "CHECKOUT", "SHIPPING", "SUBTOTAL", "COUPON",
        "COUPONS", "DISCOUNT", "SEARCH", "ACCOUNT", "PAYMENT", "SECURE", "MASTERCARD", "DISCOVER", "AMERICAN", "EXPRESS",
        "YOUTUBE", "DOWNLOAD", "INSTALL", "UPDATE", "SUBMIT", "REDEEM", "CANCEL", "SETTINGS", "PROMOTIONS", "RETURNS",
        "TRACKER", "SAFEKEY", "WOMENS", "LIMITED", "ANNUALLY", "QUARTERLY", "MEMBERSHIP", "SPECIAL", "OFFER", "DELIVERY"}
NUM = {"zero": "0", "oh": "0", "one": "1", "two": "2", "to": "2", "too": "2", "three": "3", "four": "4", "for": "4", "five": "5",
       "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "twenty": "20", "fifteen": "15", "thirty": "30"}


def frames(video, fps=1.0):
    """yield (t, 3840x1080 BGR) at fps."""
    w, h = 3840, 1080
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE)
    n = 0
    while True:
        buf = p.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        yield n / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        n += 1


def candidates(text):
    out = []
    for tok in re.findall(r"[A-Za-z0-9-]{4,20}", text):
        t = tok.strip("-")
        if len(t) < 4 or t.upper() in STOP or "-" in t[:1] or re.match(r"^\d-[A-Za-z]+$", t):   # "5-STAR" ratings
            continue
        has_d, has_l = any(c.isdigit() for c in t), any(c.isalpha() for c in t)
        if not has_l and len(t) < 5:
            continue
        # a year with one OCR'd letter is a date fragment, not a code (dhgate coupons 2026-10-24: "2024-10-01 to 2024-10-31"
        # on the code sheet came out as "202N" / "202B" and got code cards, matched by "October 2024" in the speech)
        if re.fullmatch(r"(19|20)\d{1,2}[A-Za-z]?|[A-Za-z]?(19|20)\d{2}", t):
            continue
        if (has_d and has_l) or (t.isupper() and len(t) >= 7) or (has_d and len(t) >= 5 and has_l):
            out.append(t)
    return out


def spoken_stream(ow, t0, t1):
    """the letters / digits said between t0 and t1: words as-is plus spelled letters and number words."""
    s = []
    for w in ow:
        if t0 <= w["o"] <= t1:
            x = re.sub(r"[^a-z0-9]", "", w["w"].lower())
            s.append(NUM.get(x, x))
    return "".join(s)


def spelled_stream(ow, t0, t1):
    """only what was SPELLED: single letters, digits and number words ("S H E I N 2 0 2 4", "V-I-R-G-O")."""
    s = []
    for w in ow:
        if t0 <= w["o"] <= t1:
            raw = w["w"].lower()
            x = re.sub(r"[^a-z0-9]", "", raw)
            if "-" in raw.strip("-") and all(len(p) <= 1 for p in re.split(r"-+", re.sub(r"[^a-z0-9-]", "", raw)) if p):
                s.append(x)            # "V-I-R-G-O"
            elif len(x) == 1 or x.isdigit() or x in NUM:
                s.append(NUM.get(x, x))
    return "".join(s)


CONFUSE = [("L", "I"), ("I", "L"), ("II", "1"), ("1", "I"), ("I", "1"), ("0", "O"), ("O", "0"), ("5", "S"), ("S", "5")]


def repair(code, stream):
    """fix OCR letter confusions (25STVANLA2 -> 25STVANIA2, TRENDSCHEYII -> TRENDSCHEY1) with what was said."""
    best, bs = code, said(code, stream)
    for a, b in CONFUSE:
        for i in range(len(code)):
            if code.startswith(a, i):
                v = code[:i] + b + code[i + len(a):]
                s = said(v, stream)
                if s > bs + 0.01:
                    best, bs = v, s
    return best


def said_as_code(code, ow, t0, t1):
    """the exact code is in what was said, as a code: "20 Garcia", "pH a I Th f est", "us to 4j2". Not when it is just
    one or two ordinary words ("new users" -> EWUSERS banner text, "shopping")."""
    c = re.sub(r"[^a-z0-9]", "", code.lower())
    ws = [w for w in ow if t0 <= w["o"] <= t1]
    toks = [NUM.get(re.sub(r"[^a-z0-9]", "", w["w"].lower()), re.sub(r"[^a-z0-9]", "", w["w"].lower())) for w in ws]
    for i in range(len(toks)):
        s = ""
        for j in range(i, min(len(toks), i + 12)):
            s += toks[j]
            if c in s:
                piece = toks[i:j + 1]
                if (len(piece) <= 2 and all(len(x) >= 3 and x.isalpha() for x in piece)) or (c.isalpha() and len(piece) < 3):
                    break   # plain words
                return True
            if len(s) > len(c) + 12:
                break
    return False


def said(code, stream):
    c = re.sub(r"[^a-z0-9]", "", code.lower())
    if not c or not stream:
        return 0.0
    if c in stream:
        return 1.0
    best = 0.0
    for L in (len(c) - 1, len(c), len(c) + 1, len(c) + 2):
        for i in range(0, max(1, len(stream) - L + 1)):
            r = difflib.SequenceMatcher(None, c, stream[i:i + L]).ratio()
            best = max(best, r)
    return best


def main(video, words_path, out_path, app=""):
    ow = json.load(open(words_path, encoding="utf-8-sig"))
    seen = collections.defaultdict(list)   # key (normalized) -> [(t, spelling)]
    # OCR cache by RAW recording time (user 2026-10-22: faster revisions). The cut is re-encoded on every revision, but each
    # output second still shows a fixed moment of the raw recording, so its OCR is reused; only newly kept footage is read.
    proj = os.path.dirname(os.path.dirname(os.path.abspath(video)))
    src = os.path.join(proj, "raw", "source.mp4")
    cache_path = os.path.join(proj, "work", "ocr_cache.json")
    try:
        keep = json.load(open(os.path.join(proj, "work", "cuts.json"), encoding="utf-8"))["keep"]
        sig = f"{os.path.getsize(src)}|{int(os.path.getmtime(src))}|v1"
    except Exception:
        keep, sig = [], None
    cache = {}
    if sig:
        try:
            got = json.load(open(cache_path, encoding="utf-8"))
            cache = got["frames"] if got.get("sig") == sig else {}
        except Exception:
            cache = {}

    def to_raw(t):
        acc = 0.0
        for a_, b_ in keep:
            if t < acc + (b_ - a_):
                return a_ + (t - acc)
            acc += b_ - a_
        return None
    n, fresh = 0, 0
    for t, img in frames(video):
        n += 1
        rt = to_raw(t) if sig else None
        for hi, half in enumerate((img[:, :1920], img[:, 1920:])):
            half = cv2.resize(half, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)   # 80 % browser zoom text is ~10 px
            if half.mean() < 8:
                continue
            ck = f"{round(rt * 2) / 2:.1f}|{hi}" if rt is not None else None
            if ck is not None and ck in cache:
                lines = cache[ck]
            else:
                lines = [[line, [list(w) for w in wds]] for line, wds in privacy_ocr.ocr(half)]
                fresh += 1
                if ck is not None:
                    cache[ck] = lines
            for line, wds in lines:
                box = None
                if wds:   # line box in 1920x1080 half pixels (the OCR ran at 1.5x), + which half: the zoom-in target
                    x0, y0 = min(w[1] for w in wds), min(w[2] for w in wds)
                    x1, y1 = max(w[1] + w[3] for w in wds), max(w[2] + w[4] for w in wds)
                    box = [hi, round(x0 / 1.5), round(y0 / 1.5), round((x1 - x0) / 1.5), round((y1 - y0) / 1.5)]
                for c in candidates(line):
                    seen[c.upper()].append((t, c, box))
    if sig:
        json.dump({"sig": sig, "frames": cache}, open(cache_path, "w", encoding="utf-8"))
    print(f"OCR: {fresh} half-frames read, {2 * n - fresh} from cache or dark")
    # merge one-letter OCR variants into the most-seen spelling
    keys = sorted(seen, key=lambda k: -len(seen[k]))
    groups = []
    for k in keys:
        for g in groups:
            if difflib.SequenceMatcher(None, k, g[0]).ratio() >= 0.85:
                g[1].extend(seen[k])
                break
        else:
            groups.append([k, list(seen[k])])
    codes = []
    for k, hits in groups:
        ts = sorted(h[0] for h in hits)
        if len(set(ts)) < 2 or len(set(ts)) > 0.4 * n:   # a flash, or UI chrome that is always there
            continue
        spelling = collections.Counter(h[1] for h in hits).most_common(1)[0][0]
        box = next((h[2] for h in sorted(hits, key=lambda h: h[0]) if h[2]), None)
        first = ts[0]
        words_s = spoken_stream(ow, first - 25, ts[-1] + 25)
        spelled = spelled_stream(ow, first - 25, ts[-1] + 25)
        spelling = repair(spelling.upper(), words_s)
        # the user spells every code out ("type it in exactly how you see: S H E I N 2 0 2 4"); a plain word that was only
        # SAID ("new users", "shopping", "ratings") is UI text, not a code
        sp = said(spelling, spelled)
        whole = said_as_code(spelling, ow, first - 25, ts[-1] + 25)
        if sp < 0.75 and not whole:
            continue
        score = max(sp, 1.0 if whole else 0)
        # when it is announced: the last "code" said before it showed up (<= 20 s), else when it showed up
        ann = [w["o"] for w in ow if w["o"] <= first + 6 and w["o"] >= first - 20 and w["w"].lower().strip(".,") in ("code", "codes")]
        t_said = ann[-1] if ann else first
        # what it gives: the first "N %" / "$N" said in the next 25 s
        sub = ""
        for i, w in enumerate(ow):
            if t_said <= w["o"] <= t_said + 25:
                m = re.match(r"^\$?(\d+)", w["w"])
                if m and (w["w"].startswith("$") or (i + 1 < len(ow) and ow[i + 1]["w"].startswith("%")) or w["w"].endswith("%")):
                    sub = (f"${m.group(1)} OFF" if w["w"].startswith("$") else f"{m.group(1)}% OFF")
                    break
        codes.append({"code": spelling.upper(), "seen": round(first, 2), "said": round(t_said, 2), "sub": sub, "score": round(score, 2), "box": box,
                      "app": app})
    codes.sort(key=lambda c: c["said"])
    # two codes announced at the same moment: keep the better-said one
    out = []
    for c in codes:
        if out and abs(c["said"] - out[-1]["said"]) < 2.5:
            if c["score"] > out[-1]["score"]:
                out[-1] = c
            continue
        out.append(c)
    # a shorter OCR fragment of a code carded in the last 25 s is that same code still on screen, not a new one
    # (dhgate coupons 2026-10-22: "DH2025Y", a clipped read of DH2025MAY..., got a card at an abandoned "for ... next code")
    def subseq(a, b):
        it = iter(b)
        return all(ch in it for ch in a)
    out = [c for c in out if not any(k is not c and len(k["code"]) > len(c["code"]) and subseq(c["code"], k["code"])
                                     and k["said"] <= c["said"] <= k["said"] + 25 for k in out)]
    # codes OCR could not read (tiny search-bar text): <out>.manual.json [{"code", "after": "words said just before it"}]
    man = out_path.replace(".json", ".manual.json")
    if os.path.exists(man):
        for m in json.load(open(man, encoding="utf-8-sig")):
            if m.get("reject"):   # {"code": "ARIZONA", "reject": true}: text OCR took for a code
                out = [c for c in out if c["code"] != m["code"]]
                continue
            if any(c["code"] == m["code"] for c in out):
                continue
            key = m["after"].lower().split()
            toks = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in ow]
            hit = next((i for i in range(len(toks)) if toks[i:i + len(key)] == key), None)
            if hit is not None:
                out.append({"code": m["code"], "seen": ow[hit]["o"], "said": ow[hit]["o"], "sub": m.get("sub", ""), "score": 1.0, "box": m.get("box"), "app": app})
        out.sort(key=lambda c: c["said"])
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=1)
    print(f"{len(out)} codes on screen:", ", ".join(f"{c['code']}@{c['said']:.0f}s" for c in out))
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
