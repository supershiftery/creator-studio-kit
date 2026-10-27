"""Which kind of video is this recording? (gaming / phone / review) for the one-drop New Project flow.

Every type is recorded the same way (3840x1080 OBS side-by-side), so the file shape alone tells nothing. What does:
- what is said: the intro names the channel ("{{PHONE_CHANNEL}} here" = phone, "{{REVIEW_CHANNEL}} reviews here" = review,
  "Hello YouTube ... Minecraft" = gaming) and the topic words back it up (promo code / DHgate / realm ...)
- the right half: the phone mirror is a narrow strip on black; a game or the desk camera fills the frame
- length and where the file sits (60+ minute recordings are gaming, an {{GAMING_ROOT}} path is gaming)

detect(path) -> {type, confidence: high|medium|low, scores, reasons, channel, title, heard}
The result is cached per file (media-cache.json) so reopening the New Project screen is instant.
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

import media
import speech
import store

# (regex, points, reason shown on the chip). Whisper spellings seen in real recordings are in the patterns.
WORDS = {
    "phone": [
        (r"\b{{PHONE_CHANNEL_RX}}\b", 5, "“{{PHONE_CHANNEL}} here”"),
        (r"\bpromo ?codes?\b", 3, "“promo code”"),
        (r"\b(?:uber ?eats|door ?dash|dash ?pass|shein|sheen|chime|grubhub|instacart|temu|lyft)\b", 2, "app name"),
        (r"\b(?:discount|referral|coupon) codes?\b|\bcheckout\b|\bin the app\b|\bdownload the app\b", 1, "app / checkout talk"),
    ],
    "review": [
        (r"\b{{REVIEW_CHANNEL_RX}}\b", 5, "“{{REVIEW_CHANNEL}} here”"),
        (r"\bd ?h ?(?:gate|g)\b|\bdhgate\b", 3, "“DHgate”"),
        (r"\bunbox(?:ing)?\b|\breceipt\b|\bseller\b|\bstitching\b|\breps?\b|\breplica\b|\b1 ?to ?1\b|\bone to one\b", 1, "product talk"),
        (r"\b(?:backpack|sunglasses|glasses|hoodie|sneakers?|shoes|jacket|rolex|cartier|chanel|supreme|louis|gucci|dior|alo)\b", 1, "product name"),
    ],
    # haul (user 2026-10-23): one long phone recording, many products back to back, no intro VO / no OBS side-by-side
    "haul": [
        (r"\bhauls?\b", 4, "“haul”"),
        (r"\b\d+ ?(?:kg|kgs|kilos?|kilograms?|pounds|lbs)\b|\b(?:thirty|twenty|fifteen|ten|twelve|eight|six) ?(?:kg|kilos?)\b", 2, "haul weight (kg)"),
        (r"\b(?:mule ?buy|ac ?buy|cn ?fans|kako ?buy|oops ?buy|hoobuy|allchinabuy|sugargoo|pandabuy|agent)\b|\bshipping\b", 1, "agent / shipping talk"),
        (r"\bnext (?:item|thing|piece|up|one)\b|\bthis next\b|\bmoving on\b|\bnext we (?:have|got)\b", 1, "products back to back"),
    ],
    "gaming": [
        (r"\bminecraft\b|\bbedrock\b|\bmcpe\b", 4, "“Minecraft”"),
        (r"\brealms?\b|\bservers?\b|\badd[- ]?ons?\b|\bmods?\b|\bmodpack\b|\bcobblemon\b|\bseeds?\b", 2, "realm / server / add-on talk"),
        (r"\bhello youtube\b", 1, "“Hello YouTube” opener"),
        (r"\bpok[eé]mon\b|\bpvp\b|\bdiamond\b|\bspawn\b|\bmobs?\b|\bcrouch\b", 1, "gameplay words"),
    ],
}
CHANNEL = {"gaming": "{{GAMING_CHANNEL}}", "phone": "{{PHONE_CHANNEL}}", "review": "{{REVIEW_CHANNEL}}", "haul": "{{REVIEW_CHANNEL}}", "short": "{{REVIEW_CHANNEL}}"}
VERSION = 5   # bump when the rules change so cached answers are worked out again (3: screen flag, 2026-10-22; 4: haul, 5: short, 2026-10-23)


def _right_half_black(path, info):
    """Share of near-black pixels at the outer sides of the right half (phone mirror on a black desktop -> ~0.9+)."""
    w, h = max(2, info["width"] // 8) * 2, max(2, info["height"] // 4) * 2
    vals = []
    for f in (0.2, 0.45, 0.7):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{info['duration'] * f:.2f}", "-i", str(path),
                              "-vf", f"crop=iw/2:ih:iw/2:0,scale={w}:{h}:flags=neighbor", "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, creationflags=media.CREATE_NO_WINDOW).stdout
        if len(raw) != w * h:
            continue
        a = np.frombuffer(raw, np.uint8).reshape(h, w)
        sides = np.concatenate([a[:, : w // 4], a[:, -(w // 4):]], axis=1)
        vals.append(float((sides < 18).mean()))
    return sum(vals) / len(vals) if vals else None


def _listen(path, info):
    """Opening minute + two 30 s samples further in, from the loudest (mic) track."""
    best = 0
    if len(info["audio"]) > 1:
        lv = media.track_levels(path, ss=20, t=30)
        best = max(range(len(lv)), key=lambda i: lv[i]) if lv else 0
    d = info["duration"]
    parts = []
    for ss, dur in ((0, 60), (d * 0.4, 30), (d * 0.7, 30)):
        if ss and d < 150:
            break   # short clip: the opening minute already covers it
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ss:.2f}", "-t", str(dur), "-i", str(path), "-map", f"0:a:{best}",
                              "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, creationflags=media.CREATE_NO_WINDOW).stdout
        a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        if len(a) < 16000:
            continue
        segs, _ = speech._model().transcribe(a, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        parts.append(" ".join(s.text.strip() for s in segs).strip())
    return parts


def title_from(text):
    """'... today I'm gonna be going over the best supreme backpack on DHG, but ...' -> 'Best Supreme Backpack On DHG'"""
    m = re.search(r"\b(?:today|in this video)\b[^.!?]{0,40}?\b(?:going over|showing you|talking about|reviewing|checking out|looking at)\s+(.{6,90}?)(?:[.!?,]|\s(?:but|and|because|so|this|which|i'm|i)\b)", text, re.I)
    if not m:
        return ""
    t = re.sub(r"^(?:the|a|an|exactly|some of)\s+", "", m.group(1).strip(), flags=re.I)
    t = re.sub(r"\b(19|20)\d\d\b", "", t)   # no dates in titles/graphics
    t = re.sub(r"\s+", " ", t).strip(" -")
    t = re.sub(r"(?:\s+(?:in|for|of|on|to|the|me|personally|these|this|will|be))+$", "", t, flags=re.I)
    if re.search(r"\b(?:guys|here|welcome)\b", t, re.I) or len(t) < 8:
        return ""   # caught the greeting, not the topic
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in t.split())


def _phone_meta(path):
    """phone camera file? (QuickTime / Android make + model tags; else a .MOV in HDR HLG or rotated) -> (is_phone, why)"""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream=codec_type,color_transfer:stream_side_data=rotation",
                        "-of", "json", str(path)], capture_output=True, text=True, creationflags=media.CREATE_NO_WINDOW)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        return False, ""
    tags = {k.lower(): str(v) for k, v in ((d.get("format") or {}).get("tags") or {}).items()}
    model = tags.get("com.apple.quicktime.model") or tags.get("com.android.model") or ""
    make = tags.get("com.apple.quicktime.make") or tags.get("com.android.manufacturer") or ""
    if model or make:
        return True, f"phone camera ({(make + ' ' + model).strip()})"
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    rot = any("rotation" in sd for sd in v.get("side_data_list") or [])
    if Path(path).suffix.lower() == ".mov" and (v.get("color_transfer") == "arib-std-b67" or rot):
        return True, "phone camera (.MOV, HDR / rotated)"
    return False, ""


def _haul_check(path, info, heard):
    """close call between haul and review on a phone file: the director (claude_brain: Claude) looks at a
    6-frame sheet + what was said. Many different products back to back = haul. -> "haul" | "review" | None"""
    try:
        import sys
        sys.path.insert(0, r"{{KIT}}/tools")
        import claude_brain as B
    except Exception:  # noqa
        return None
    import hashlib
    d = store.DATA / "detect"
    d.mkdir(exist_ok=True)
    sheet = d / (hashlib.sha1(media.cache_key(path).encode()).hexdigest()[:16] + "-sheet.jpg")
    if not sheet.exists():
        tiles = []
        for k, f in enumerate((0.08, 0.25, 0.4, 0.55, 0.7, 0.88)):
            t = sheet.with_name(f"{sheet.stem}-{k}.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{info['duration'] * f:.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                            "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2", str(t)],
                           creationflags=media.CREATE_NO_WINDOW)
            tiles.append(t)
        ins = [x for t in tiles if t.exists() for x in ("-i", str(t))]
        if len(ins) == 12:
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", "[0][1][2]hstack=3[a];[3][4][5]hstack=3[b];[a][b]vstack",
                            str(sheet)], creationflags=media.CREATE_NO_WINDOW)
        for t in tiles:
            t.unlink(missing_ok=True)
    if not sheet.exists():
        return None
    ans = B.ask("detect_haul", "Six frames spread across one video recording, plus what the creator says in it:\n" + heard[:1500] +
                "\n\nIs this a HAUL (one long phone recording showing MANY DIFFERENT products one after another: clothes, shoes, "
                "accessories from one order) or a REVIEW of one product? Reply ONLY JSON {\"kind\": \"haul\" or \"review\", \"products_seen\": <number>}",
                images=[str(sheet)]) or {}
    k = str(ans.get("kind") or "").lower()
    return k if k in ("haul", "review") else None


def _vertical(path):
    """upright picture as SHOWN (a phone stores portrait as 1920x1080 + a 90 degree rotation) -> True / False"""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation",
                        "-of", "json", str(path)], capture_output=True, text=True, creationflags=media.CREATE_NO_WINDOW)
    try:
        v = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    except ValueError:
        return False
    w, h = v.get("width") or 0, v.get("height") or 0
    rot = next((int(sd["rotation"]) for sd in v.get("side_data_list") or [] if "rotation" in sd), 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return h > w * 1.2


def detect(path, fresh=False):
    path = str(path)
    c = media._load_cache()
    k = media.cache_key(path)
    if not fresh and (c.get(k, {}).get("detect") or {}).get("v") == VERSION:
        return c[k]["detect"]
    scores = {t: 0 for t in CHANNEL}
    reasons = {t: [] for t in CHANNEL}

    def add(t, pts, why):
        scores[t] += pts
        if why not in reasons[t]:
            reasons[t].append(why)

    low = path.lower().replace("/", "\\")
    if Path(path).suffix.lower() == ".xml":
        add("review", 2, "Gling XML (review projects use these)")
    s = store.settings()
    if low.startswith(s["roots"]["gaming"].lower()):
        add("gaming", 4, "sits in Minecraft Videos")
    name = Path(path).stem.lower()
    # the folder counts for hauls: phone files are named IMG_6814.MOV, the folder says "30kg haul Dhgate"
    if re.search(r"\bhauls?\b", str(Path(path).parent).lower()):
        add("haul", 4, "folder says haul")
    for t, rules in WORDS.items():   # file names like "uber eats promo codes may 2025" / "dhgate chanel sunglasses"
        for rx, pts, why in rules:
            if re.search(rx, name, re.I):
                add(t, min(pts, 3), "file name")

    heard = ""
    info = media.probe(path) if Path(path).suffix.lower() != ".xml" else None
    if info and info["duration"]:
        if info["duration"] >= 45 * 60:
            add("gaming", 3, f"{int(info['duration'] // 60)} min long")
        phone, why = _phone_meta(path)
        # a vertical recording is a Short (Studio type "short", user 2026-10-23): no other type is ever filmed upright
        if _vertical(path):
            add("short", 12, "vertical 9:16 recording")
            if info["duration"] <= 180:
                add("short", 2, f"{int(info['duration'])} s long")
        if phone and media.layout_of(info) != "side-by-side":
            add("haul", 4, why)   # reviews / phone-app / gaming are all OBS side-by-side; a phone camera file is a haul
        if media.layout_of(info) == "side-by-side":
            # older hauls (#8-#21, the mulebuy / 15kg ones) were OBS side-by-side review-style recordings; the haul type is
            # the PHONE format (user 2026-10-23), so a side-by-side "haul" stays a review-pipeline video
            scores["haul"] -= 8
            reasons["haul"].append("OBS side-by-side (haul pipeline = phone recordings)")
            black = _right_half_black(path, info)
            if black is not None and black >= 0.6:
                add("phone", 4, "phone mirror on the right")
        try:
            parts = _listen(path, info)
        except Exception as e:  # noqa - no whisper -> still decide on the rest
            parts = []
            reasons["gaming"].append(f"(could not listen: {type(e).__name__})")
        heard = " ".join(parts)
        for t, rules in WORDS.items():
            for rx, pts, why in rules:
                n = len(re.findall(rx, heard, re.I))
                if n:
                    add(t, pts + min(n - 1, 2), why)   # repeats count a little, never swamp the channel name

    phone = bool(info and info["width"] and _phone_meta(path)[0])
    # weak haul talk alone ("next one") is not a haul (friend's "apple home lg" screen recording scored 1); a haul needs a
    # real signal (the word haul, a phone camera file, the folder)
    if scores["haul"] < 4:
        scores["haul"] = min(scores["haul"], 0)
    # reviews are always the OBS side-by-side; a plain 16:9 / phone file with real haul signals is the haul format even when
    # he says "{{REVIEW_CHANNEL}} here" (25kg haul part 1, 1920x1080 camera file: review 13 vs haul 11 before this)
    elif info and info["width"] and media.layout_of(info) != "side-by-side":
        add("haul", 4, "not the review side-by-side")
    ranked = sorted(scores, key=lambda t: -scores[t])
    if phone and set(ranked[:2]) == {"haul", "review"} and scores[ranked[0]] - scores[ranked[1]] < 4:
        k = _haul_check(path, info, heard)   # close call: the director looks at the frames
        if k:
            add(k, 3, f"AI look at the frames: {k}")
            ranked = sorted(scores, key=lambda t: -scores[t])
    top, second = ranked[0], ranked[1]
    margin = scores[top] - scores[second]
    confidence = "high" if scores[top] >= 5 and margin >= 4 else "medium" if scores[top] >= 3 and margin >= 2 else "low"
    channel = CHANNEL[top]
    if top == "haul":   # the channel = the Raw Videos folder it sits in ("Raw Videos\{{REVIEW_CHANNEL}}\...") when known
        m = re.search(r"raw videos[\\/]+([^\\/]+)", path, re.I)
        if m:
            f = m.group(1).strip().lower()
            names = {c["name"].lower(): c["name"] for c in s.get("channels", [])}
            alias = {"agent {{REVIEW_CHANNEL}}": "{{REVIEW_CHANNEL}}", "{{REVIEW_CHANNEL}} haul": "{{REVIEW_CHANNEL}}", "{{REVIEW_CHANNEL}} kicks": "{{REVIEW_CHANNEL}}"}
            channel = names.get(f) or alias.get(f) or channel
    for ch in store.settings().get("channels", []):   # a channel whose own name is said wins over the type default
        if top in ch.get("types", []) and re.search(r"\b" + re.escape(ch["name"].lower()) + r"\b", heard, re.I):
            channel = ch["name"]
    # every one of the user's own recordings is the 3840-wide OBS side-by-side (cam + screen); a plain 16:9 capture with
    # no cam (friend's "apple home lg", 1920x1080 website walkthrough, 2026-10-22) is a screen recording: full screen,
    # no cam box / phone layout. New Project ticks "Screen recording" from this.
    # a phone camera file / haul is never a "screen recording" (the haul pipeline does its own full-frame edit)
    screen = bool(info and info["width"] and media.layout_of(info) == "single") and top not in ("haul", "short") and not phone
    out = {"v": VERSION, "screen": screen, "type": top if scores[top] > 0 else None, "confidence": confidence if scores[top] > 0 else "low",
           "scores": scores, "reasons": reasons[top][:4], "channel": channel,
           "title": title_from(heard), "heard": heard[:300]}
    c.setdefault(k, {})["detect"] = out
    media._save_cache()
    return out


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        print(p, json.dumps(detect(p, fresh=True), indent=1, ensure_ascii=False))
