"""Which kind of video is this recording? (gaming / phone / review) for the one-drop New Project flow.

Every type is recorded the same way (3840x1080 OBS side-by-side), so the file shape alone tells nothing. What does:
- what is said: the intro names the channel ("{{PHONE_CHANNEL}} here" = phone, "{{REVIEW_CHANNEL}} reviews here" = review,
  "Hello YouTube ... Minecraft" = gaming) and the topic words back it up (promo code / DHgate / realm ...)
- the right half: the phone mirror is a narrow strip on black; a game or the desk camera fills the frame
- length and where the file sits (60+ minute recordings are gaming, an {{GAMING_ROOT}} path is gaming)

Nothing matching (or a close call) = "other", the general talking / tech / screen video (plain trim edit), never gaming.

detect(path) -> {type (a CHANNEL type or "other"), confidence: high|medium|low, guess, scores, reasons, channel, title, heard}
The result is cached per file (media-cache.json) so reopening the New Project screen is instant.
"""
import json
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
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
# the general type (2026-10-29): a kit user's Apple touchscreen-laptop talk (plain 16:9) scored 0 everywhere, came back
# type None and New Project kept its "gaming" default -> Minecraft wipes. Anything that fits none of the creator types is
# "other": the plain trim / screen-recording edit (recipes/trim.py -> tools/trim_render.py), no channel graphics.
GENERAL = "other"
MIN_SCORE = 3   # below this the top type is a guess, not a match -> GENERAL
# gaming needs one of these (said, in the file name, or the Minecraft Videos folder); realm / server / mods / length alone
# also turn up in tech talk ("servers", "an hour long") and never make a video gaming on their own
GAMEPLAY_RX = r"\bminecraft\b|\bbedrock\b|\bmcpe\b|\bcobblemon\b"
VERSION = 8   # bump when the rules change so cached answers are worked out again (3: screen flag, 2026-10-22; 4: haul, 5: short, 2026-10-23; 6: general type; 7: camera layout + my types, 2026-10-29; 8: Minecraft hotbar on screen + 40 s listen)


def _right_half_black(path, info):
    """Share of near-black pixels at the outer sides of the right half (phone mirror on a black desktop -> ~0.9+)."""
    w, h = max(2, info["width"] // 8) * 2, max(2, info["height"] // 4) * 2
    def one(f):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-noaccurate_seek", "-ss", f"{info['duration'] * f:.2f}", "-i", str(path),
                              "-vf", f"crop=iw/2:ih:iw/2:0,scale={w}:{h}:flags=neighbor", "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, creationflags=media.CREATE_NO_WINDOW).stdout
        if len(raw) != w * h:
            return None
        a = np.frombuffer(raw, np.uint8).reshape(h, w)
        sides = np.concatenate([a[:, : w // 4], a[:, -(w // 4):]], axis=1)
        return float((sides < 18).mean())
    with ThreadPoolExecutor(max_workers=3) as ex:   # the three frames at once
        vals = [v for v in ex.map(one, (0.2, 0.45, 0.7)) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _hotbar(g):
    """g = gray picture of the game area, 1920 wide. The Minecraft hotbar: 9 equal square slots in a row, centred, near the
    bottom (above a Windows taskbar when the game is windowed). Found = a run of 9-11 evenly spaced full-height vertical
    edges (28-130 px apart), centred within 6 % of the middle, with the bar's top + bottom edges about one slot apart.
    Tested 2026-10-29: hit in every Minecraft recording, 0 of 90 reviews / phone / spreadsheet / desktop / Discord ones."""
    H, W = g.shape
    band = g[int(H * 0.62):, :].astype(np.float32)
    gx = np.abs(cv2.Sobel(band, cv2.CV_32F, 1, 0, ksize=3)) > 60
    gy = np.abs(cv2.Sobel(band, cv2.CV_32F, 0, 1, ksize=3)) > 60
    for y0 in range(0, band.shape[0] - 16, 4):
        pk = np.where(gx[y0:y0 + 16].mean(0) > 0.75)[0]
        if len(pk) < 9:
            continue
        cs, st, pv = [], pk[0], pk[0]   # runs of edge columns -> their centres
        for x in pk[1:]:
            if x - pv > 8:
                cs.append((st + pv) / 2)
                st = x
            pv = x
        cs = np.array(cs + [(st + pv) / 2])
        if len(cs) < 9:
            continue
        for i in range(len(cs)):
            for j in range(i + 1, min(i + 4, len(cs))):
                sp = cs[j] - cs[i]
                if not 28 <= sp <= 130:
                    continue
                run, x = [cs[i]], cs[i]
                while True:
                    nx = cs[np.abs(cs - (x + sp)) <= 3]
                    if not len(nx):
                        break
                    x = nx[0]
                    run.append(x)
                if not 9 <= len(run) <= 11 or abs((run[0] + run[-1]) / 2 / W - 0.5) > 0.06:
                    continue
                rows = gy[:, int(run[0]):int(run[-1])].mean(1)
                near = [yy for yy in range(max(0, y0 - int(sp * 1.3)), min(len(rows), y0 + 16 + int(sp * 1.3))) if rows[yy] > 0.7]
                if len(near) >= 2 and max(near) - min(near) >= sp * 0.6:
                    return True
    return False


def _game_hud(path, info, n=6):
    """Minecraft on screen? A few frames of the game area (right half of a side-by-side, else the whole picture), stops at
    the first frame with the hotbar. A Minecraft recording where "Minecraft" is never said (user 2026-10-29: a Cobblemon
    clip came back "other") is still gaming. ~0.2 s a frame."""
    side = media.layout_of(info) == "side-by-side"
    crop = "crop=iw/2:ih:iw/2:0," if side else ""
    gw = info["width"] // (2 if side else 1)
    h = int(round(info["height"] * 1920 / max(1, gw) / 2)) * 2
    def grab(k):
        t = info["duration"] * (0.1 + 0.8 * k / max(1, n - 1))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-noaccurate_seek", "-ss", f"{t:.2f}", "-i", str(path), "-vf", f"{crop}scale=1920:{h}:flags=area",
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, creationflags=media.CREATE_NO_WINDOW).stdout
        return len(raw) == 1920 * h and _hotbar(np.frombuffer(raw, np.uint8).reshape(h, 1920))
    with ThreadPoolExecutor(max_workers=n) as ex:   # all frames at once (round 2: one by one was 4-5 s on a 5K file)
        return any(ex.map(grab, range(n)))


_HUD = {}   # media.cache_key -> Minecraft hotbar seen


def _mic_track(path, info):
    if len(info["audio"]) > 1:
        lv = media.track_levels(path, ss=20, t=30)
        return max(range(len(lv)), key=lambda i: lv[i]) if lv else 0
    return 0


def _listen(path, info, spans=((0, 40),), best=None):
    """What is said in these (start, seconds) spans, from the loudest (mic) track. The opening 40 s holds the greeting +
    topic; detect() only asks for samples further in when that leaves a close call (was 2 min of audio = ~20 s a video)."""
    best = _mic_track(path, info) if best is None else best
    d = info["duration"]
    parts = []
    for ss, dur in spans:
        if ss >= d:
            continue
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


def detect(path, fresh=False, quick=False):
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
    hud = False
    info = media.probe(path) if Path(path).suffix.lower() != ".xml" else None
    vertical = False
    if info and info["duration"]:
        phone, why = _phone_meta(path)
        # a vertical recording is a Short (Studio type "short", user 2026-10-23): no other type is ever filmed upright
        vertical = _vertical(path)
        if vertical:
            add("short", 12, "vertical 9:16 recording")
            if info["duration"] <= 180:
                add("short", 2, f"{int(info['duration'])} s long")
        if phone and media.layout_of(info) != "side-by-side":
            add("haul", 4, why)   # reviews / phone-app / gaming are all OBS side-by-side; a phone camera file is a haul
        mirror = False
        if media.layout_of(info) == "side-by-side":
            # older hauls (#8-#21, the mulebuy / 15kg ones) were OBS side-by-side review-style recordings; the haul type is
            # the PHONE format (user 2026-10-23), so a side-by-side "haul" stays a review-pipeline video
            scores["haul"] -= 8
            reasons["haul"].append("OBS side-by-side (haul pipeline = phone recordings)")
            black = _right_half_black(path, info)
            mirror = black is not None and black >= 0.6
            if mirror:
                add("phone", 4, "phone mirror on the right")
        # the picture before the sound (user 2026-10-29: "clearly a gaming video", a Cobblemon clip where Minecraft is never
        # said came back "other" after ~20 s of listening): the hotbar on screen = Minecraft
        if not vertical and not mirror:
            try:   # kept per file: the quick answer and the full check right after it ask the same question
                hud = _HUD[k] if k in _HUD else _HUD.setdefault(k, _game_hud(path, info))
            except Exception:  # noqa: never blocks the guess
                hud = False
        if hud:
            add("gaming", 8, "Minecraft on screen (hotbar)")

    def words(text):
        for t, rules in WORDS.items():
            for rx, pts, why in rules:
                n = len(re.findall(rx, text, re.I))
                if n:
                    add(t, pts + min(n - 1, 2), why)   # repeats count a little, never swamp the channel name

    if quick:   # the picture-only answer New Project shows at once, while the full check listens
        return _decide(path, info, dict(scores), {t: list(r) for t, r in reasons.items()}, "", name, s, hud, quick=True)
    cam = {}   # the camera look (mediapipe, ~10 s on a 5K file) runs while Whisper listens, not after it
    cam_t = None
    # only when one of the user's own styles is tied to a camera layout (my_style): ~10 s on a 5K file for nothing otherwise
    try:
        import mystyle
        need_cam = any((t.get("style") or {}).get("layout") for t in mystyle.list_types())
    except Exception:  # noqa
        need_cam = False
    if info and info["duration"] and need_cam:
        def look():
            try:
                cam["r"] = media.camera_layout(path, n=8, info=info)["camera"]
            except Exception as e:  # noqa: never blocks the type guess
                cam["err"] = f"{type(e).__name__}: {e}"[:200]
        cam_t = threading.Thread(target=look, daemon=True)
        cam_t.start()
        base_scores, base_reasons = dict(scores), {t: list(r) for t, r in reasons.items()}
        try:
            mic = _mic_track(path, info)
            heard = " ".join(_listen(path, info, ((0, 40),), best=mic))
            words(heard)
            # still a close call on a longer video: two 25 s samples further in (no extra listening for clear answers)
            top2 = sorted(scores.values(), reverse=True)[:2]
            if info["duration"] >= 150 and not hud and not vertical and (top2[0] < 5 or top2[0] - top2[1] < 4):
                d = info["duration"]
                heard = (heard + " " + " ".join(_listen(path, info, ((d * 0.4, 25), (d * 0.7, 25)), best=mic))).strip()
                scores.update(base_scores)
                for t in reasons:
                    reasons[t] = list(base_reasons[t])
                words(heard)
        except Exception as e:  # noqa - no whisper -> still decide on the rest
            reasons["gaming"].append(f"(could not listen: {type(e).__name__})")
    out = _decide(path, info, scores, reasons, heard, name, s, hud)
    # what the camera shows (media.camera_layout: 1cam / 2cam / screen_cam / vertical / no_face) and the user's own video
    # types (my_style) that fit it, 2026-10-29
    if info and info["duration"] and not need_cam:
        try:
            import mystyle
            out["camera"], out["my_types"] = "unknown", mystyle.matches(out)
        except Exception:  # noqa
            pass
    if cam_t:
        cam_t.join()
        try:
            if "r" not in cam:
                raise RuntimeError(cam.get("err", "no answer"))
            out["camera"] = cam["r"]
            import mystyle
            out["my_types"] = mystyle.matches(out)
        except Exception as e:  # noqa: never blocks the type guess
            out["camera"], out["camera_error"] = "unknown", f"{type(e).__name__}: {e}"[:200]
    c.setdefault(k, {})["detect"] = out
    media._save_cache()
    return out


def _decide(path, info, scores, reasons, heard, name, s, hud, quick=False):
    """scores + reasons so far -> the answer New Project shows. quick = picture / file signals only (nothing heard yet)."""
    def add(t, pts, why):
        scores[t] += pts
        if why not in reasons[t]:
            reasons[t].append(why)

    # gaming only on a real gameplay signal (Minecraft said / in the name / on screen / the Minecraft Videos folder); then a
    # 45+ min recording backs it up. Without one, server / mods / "hello youtube" talk stays a hint (max 2, below MIN_SCORE)
    if hud or re.search(GAMEPLAY_RX, heard + " " + name, re.I) or "sits in Minecraft Videos" in reasons["gaming"]:
        if info and info["duration"] >= 45 * 60:
            add("gaming", 3, f"{int(info['duration'] // 60)} min long")
    elif scores["gaming"] > 2:
        scores["gaming"] = 2
        reasons["gaming"].append("no Minecraft / gameplay signal")

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
    if not quick and phone and set(ranked[:2]) == {"haul", "review"} and scores[ranked[0]] - scores[ranked[1]] < 4:
        k = _haul_check(path, info, heard)   # close call: the director looks at the frames
        if k:
            add(k, 3, f"AI look at the frames: {k}")
            ranked = sorted(scores, key=lambda t: -scores[t])
    top, second = ranked[0], ranked[1]
    margin = scores[top] - scores[second]
    confidence = "high" if scores[top] >= 5 and margin >= 4 else "medium" if scores[top] >= 3 and margin >= 2 else "low"
    single = bool(info and info["width"] and media.layout_of(info) == "single")
    # nothing matched (top < MIN_SCORE) or a close call (low): the general type, never the first key (gaming). A plain 16:9
    # talk with real speech and no creator signal IS the general type ("medium": one-click change); a side-by-side or a
    # silent file is a real don't-know ("low": New Project asks with the type cards)
    kind = GENERAL if scores[top] < MIN_SCORE or confidence == "low" else top
    if scores[top] < MIN_SCORE:
        confidence = "medium" if single and len(heard.strip()) >= 40 else "low"
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
    # a phone camera file / haul is never a "screen recording" (the haul pipeline does its own full-frame edit); a full-screen
    # Minecraft capture is gameplay, not a screen recording
    screen = single and (kind == GENERAL or top not in ("haul", "short", "gaming")) and not phone
    if kind == GENERAL:
        why = ["no channel name, Minecraft or product / app words heard" if scores[top] < MIN_SCORE else
               f"close call: {top} {scores[top]} vs {second} {scores[second]}"]
        why += ["plain 16:9 picture" if single else "OBS side-by-side" if info and media.layout_of(info) == "side-by-side" else ""]
        why += [] if heard.strip() or quick else ["no speech found in the samples"]
        out_reasons, channel = [w for w in why if w], ""
    else:
        out_reasons = reasons[top][:4]
    # guess = the closest creator type when it fell back to general (New Project marks that card "closest match")
    return {"v": VERSION, "screen": screen, "type": kind, "confidence": confidence, "quick": quick,
            "guess": top if kind == GENERAL and scores[top] > 0 else None,
            "scores": scores, "reasons": out_reasons, "channel": channel,
            "title": title_from(heard), "heard": heard[:300]}


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        print(p, json.dumps(detect(p, fresh=True), indent=1, ensure_ascii=False))
